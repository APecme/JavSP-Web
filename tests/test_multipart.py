"""Offline regressions for multipart discovery, task manifests and organization."""
import ast
import copy
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp.config import Cfg
from javsp.datatype import MovieInfo
from javsp.file import scan_movies
from javsp.multipart import group_files, part_number
from javsp_web import tasks


class MultipartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = yaml.safe_load((ROOT / 'vendor/JavSP/config.yml').read_text(encoding='utf-8'))
        self.data['scanner'].update(minimum_size=10, input_files=None, skip_nfo_dir=False)
        self.config = Cfg.model_validate(self.data)
        for module in ('javsp.avid', 'javsp.file'):
            self.enterContext(patch(f'{module}.Cfg', side_effect=lambda: self.config))

    def files(self, *names):
        result = []
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'x' * 20)
            result.append(path)
        return result

    def test_numeric_parts_and_aliases(self):
        paths = self.files('FC2PPV-4953812-10.mp4', 'FC2-PPV-4953812-02.mkv', 'FC2-4953812-1.mp4')
        self.assertEqual(group_files(paths, self.config.scanner), [[paths[2], paths[1], paths[0]]])
        movies = scan_movies(str(self.root))
        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0].part_numbers, [1, 2, 10])

    def test_parts_before_quality_suffix(self):
        paths = self.files('masex.tv@aqumam00046_1_8k.strm', 'masex.tv@aqumam00046_2_8k.strm')
        self.assertEqual([part_number(path, self.config.scanner) for path in paths], [1, 2])
        self.assertEqual(group_files(paths, self.config.scanner), [paths])

    def test_p_suffix_parts_share_identity_and_one_movie(self):
        for stem in ('FC2-4953812', 'ssni00123'):
            with self.subTest(stem=stem):
                paths = self.files(f'{stem}-P1.strm', f'{stem}-P2.strm')
                self.assertEqual([part_number(path, self.config.scanner) for path in paths], [1, 2])
                self.assertEqual(group_files(paths, self.config.scanner), [paths])
                self.data['scanner']['input_files'] = list(map(str, paths))
                self.config = Cfg.model_validate(self.data)
                movies = scan_movies(str(paths[0]))
                self.assertEqual(len(movies), 1)
                self.assertEqual(movies[0].part_numbers, [1, 2])

    def test_p_part_suffix_does_not_truncate_cid_prefixes_ending_in_p(self):
        from javsp.multipart import media_identity
        for cid in ('118abp00123', 'abp00123', 'sdmp00123', 'h_1234abp00123'):
            with self.subTest(cid=cid):
                self.assertEqual(media_identity(cid + '.mp4', self.config.scanner), ('cid', cid))
                self.assertIsNone(part_number(cid + '.mp4', self.config.scanner))
                for suffix in ('-P1', '_P2'):
                    self.assertEqual(media_identity(cid + suffix + '.mp4', self.config.scanner), ('cid', cid))

    def test_identifiers_are_not_parts(self):
        for name in ('ABC-123.mp4', 'FC2-4953812.mp4', '080826_01.mp4', 'HEYDOUGA-1234-123.mp4'):
            with self.subTest(name=name):
                self.assertIsNone(part_number(self.root / 'ABC-123' / name, self.config.scanner))
        for name, number in [('ABC-123-CD12.mp4', 12), ('ABC-123-part2.mp4', 2), ('ssni00123-10.mp4', 10), ('ssni00123-CD12.mp4', 12), ('ssni00123-pt2.mp4', 2)]:
            with self.subTest(name=name):
                self.assertEqual(part_number(name, self.config.scanner), number)

    def test_letter_parts_and_numbered_strm_copies(self):
        paths = self.files('SAVR-619-B.strm', 'SAVR-619-A.strm')
        self.assertEqual([part_number(path, self.config.scanner) for path in paths], [2, 1])
        self.assertEqual(group_files(paths, self.config.scanner), [[paths[1], paths[0]]])
        for delimiter in ('-', '_', '.', ' '):
            path = self.root / f'SAVR-619{delimiter}b.strm'
            self.assertEqual(part_number(path, self.config.scanner), 2)
        copy, original = self.files('AVSA-223(1).strm', 'AVSA-223.strm')
        original.write_text('https://media.example/file?a=1\r\n', encoding='utf-8')
        copy.write_text('\ufeffhttps://media.example/file?a=1\n', encoding='utf-8')
        self.assertEqual(group_files([copy, original], self.config.scanner), [[original]])
        self.assertEqual(part_number(self.root / 'SAVR-619-B(1).strm', self.config.scanner), 2)
        self.assertIsNone(part_number(self.root / 'SAVR-619B.strm', self.config.scanner))

    def test_numbered_copy_conflict_is_not_suppressed(self):
        copy, original = self.files('AVSA-223(1).strm', 'AVSA-223.strm')
        original.write_text('https://media.example/a', encoding='utf-8')
        copy.write_text('https://media.example/b', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '链接内容不同'):
            group_files([copy, original], self.config.scanner)
        only = self.root / 'OTHER-456(2).strm'
        only.write_text('https://media.example/c', encoding='utf-8')
        self.assertEqual(group_files([only], self.config.scanner), [[only]])

    def test_skipping_conflicts_keeps_the_rest_of_the_batch(self):
        from javsp.multipart import group_files_skipping_conflicts
        # One broken group (unparseable part number) plus two healthy movies.
        broken = self.files('FC2-4953812.mp4', 'FC2-4953812-1.mp4')
        good_a = self.files('SAVR-619-A.strm', 'SAVR-619-B.strm')
        good_b = self.files('ABC-123.mp4')
        groups, conflicts = group_files_skipping_conflicts(
            broken + good_a + good_b, self.config.scanner)
        names = {path.name for paths in groups for path in paths}
        self.assertNotIn('FC2-4953812.mp4', names)
        self.assertNotIn('FC2-4953812-1.mp4', names)
        self.assertEqual(names, {'SAVR-619-A.strm', 'SAVR-619-B.strm', 'ABC-123.mp4'})
        self.assertEqual(len(conflicts), 1)
        self.assertIn('已跳过该组文件', conflicts[0])
        self.assertIn('FC2-4953812.mp4', conflicts[0])
        # A conflicting numbered copy no longer aborts the batch either.
        copy, original = self.files('AVSA-223(1).strm', 'AVSA-223.strm')
        original.write_text('https://media.example/a', encoding='utf-8')
        copy.write_text('https://media.example/b', encoding='utf-8')
        keeper = self.files('ABC-456.mp4')[0]
        groups, conflicts = group_files_skipping_conflicts(
            [copy, original] + [keeper], self.config.scanner)
        self.assertEqual([path.name for paths in groups for path in paths], ['ABC-456.mp4'])
        self.assertEqual(len(conflicts), 1)
        self.assertIn('重复下载候选冲突', conflicts[0])
        self.assertTrue(copy.exists() and original.exists())

    def test_copy_safety_matrix_and_mixed_parts(self):
        from javsp.multipart import inspect_download_copy
        original, duplicate = self.files('hhd800.com@AVSA-223.strm', 'hhd800.com@AVSA-223(1).strm')
        for content in ('', 'not a link', b'\xff', 'https://example.test/a?token=2'):
            with self.subTest(content_type=type(content).__name__):
                original.write_text('https://example.test/a?token=1', encoding='utf-8')
                duplicate.write_bytes(content if isinstance(content, bytes) else content.encode())
                self.assertFalse(inspect_download_copy(duplicate)['duplicate'])
                with self.assertRaisesRegex(ValueError, '保留文件'):
                    group_files([original, duplicate], self.config.scanner)
                self.assertTrue(original.exists() and duplicate.exists())
        with patch.object(Path, 'read_text', side_effect=OSError('unreadable')):
            self.assertFalse(inspect_download_copy(duplicate)['duplicate'])
        a, b, acopy, bcopy = self.files('SAVR-619-A.strm', 'SAVR-619-B.strm', 'SAVR-619-A(1).strm', 'SAVR-619-B(1).strm')
        for path in (a, b, acopy, bcopy):
            path.write_text('https://example.test/same', encoding='utf-8')
        self.assertEqual(group_files([bcopy, b, acopy, a], self.config.scanner), [[a, b]])
        numeric = self.files('SAVR-619-1.strm')[0]
        with self.assertRaisesRegex(ValueError, '重复'):
            group_files([a, numeric], self.config.scanner)
        self.data['scanner']['input_files'] = list(map(str, [bcopy, b, acopy, a]))
        self.config = Cfg.model_validate(self.data)
        movie = scan_movies(str(self.root))[0]
        self.assertEqual(list(map(str, movie.files)), list(map(str, [a, b])))
        self.assertEqual(movie.part_numbers, [1, 2])

    def test_letter_edges_configuration_and_single_retry(self):
        for name in ('SAVR-619AB.strm', 'SAVR-619-AB.strm', 'no-id-A.strm'):
            self.assertIsNone(part_number(self.root / name, self.config.scanner))
        self.assertEqual(part_number('SAVR-619-B-1080p.strm', self.config.scanner), 2)
        b = self.files('SAVR-619-B(1).strm')[0]
        movie = scan_movies(str(b))[0]
        self.assertEqual(movie.part_numbers, [2])
        config = copy.deepcopy(self.data)
        config['scanner']['media_types'] = [
            {'id': 'custom', 'name': 'Custom', 'priority': 100,
             'pattern': r'CUSTOM(?P<avid>\d+-[A-Z])', 'avid_format': '{avid}'},
            {'id': 'normal', 'name': 'Normal', 'detector': 'fallback'},
        ]
        self.assertIsNone(part_number('CUSTOM123-A.strm', Cfg.model_validate(config).scanner))

    def test_web_user_examples_manifest_and_skip_log(self):
        a, b, original, duplicate = self.files('SAVR-619-A.strm', 'SAVR-619-B.strm', 'hhd800.com@AVSA-223.strm', 'hhd800.com@AVSA-223(1).strm')
        for path in (original, duplicate):
            path.write_text('https://example.test/stream', encoding='utf-8')
        created, _ = self.create_web_tasks()
        self.assertEqual(len(created), 2)
        manifests = [task['input_files'] for task in created]
        self.assertIn(list(map(str, [a, b])), manifests)
        self.assertIn([str(original)], manifests)
        self.assertTrue(any('跳过重复副本' in line for task in created for line in task['log_tail']))
        self.assertTrue(duplicate.exists())

    def test_copy_skip_log_is_attributed_to_the_owning_task_only(self):
        a, acopy, x, xcopy = self.files(
            'SAVR-619-A.strm', 'SAVR-619-A(1).strm', 'ABP-123.strm', 'ABP-123(1).strm')
        for path in (a, acopy):
            path.write_text('https://example.test/one', encoding='utf-8')
        for path in (x, xcopy):
            path.write_text('https://example.test/two', encoding='utf-8')
        created, _ = self.create_web_tasks()
        self.assertEqual(len(created), 2)
        logs = {Path(task['input_files'][0]).name: task['log_tail'] for task in created}
        self.assertEqual([line for line in logs['SAVR-619-A.strm'] if line.startswith('跳过重复副本')],
                         ['跳过重复副本：SAVR-619-A(1).strm → SAVR-619-A.strm'])
        self.assertEqual([line for line in logs['ABP-123.strm'] if line.startswith('跳过重复副本')],
                         ['跳过重复副本：ABP-123(1).strm → ABP-123.strm'])
        every_line = [line for lines in logs.values() for line in lines]
        self.assertEqual(sum('跳过重复副本' in line for line in every_line), 2,
                         '副本提示不得向所有任务重复追加')
        self.assertFalse(any('example.test' in line for line in every_line), '任务日志不得包含链接内容')

    def test_single_file_copy_skip_log_stays_on_the_new_task(self):
        original, duplicate = self.files('MIDE-001.strm', 'MIDE-001(1).strm')
        for path in (original, duplicate):
            path.write_text('https://example.test/single', encoding='utf-8')
        created, _ = self.create_web_tasks(duplicate)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]['input_files'], None)
        self.assertEqual([line for line in created[0]['log_tail'] if line.startswith('跳过重复副本')],
                         ['跳过重复副本：MIDE-001(1).strm → MIDE-001.strm'])
        self.assertFalse(any('example.test' in line for line in created[0]['log_tail']))

    def test_duplicates_rejected_and_directories_separate(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2PPV-4953812-01.mkv')
        with self.assertRaisesRegex(ValueError, '重复'):
            group_files(paths, self.config.scanner)
        separate = self.files('other/FC2-4953812-2.mp4')
        self.assertEqual(len(group_files([paths[0], separate[0]], self.config.scanner)), 2)

    def test_preset_identifier_rules_do_not_change_global_config(self):
        data = copy.deepcopy(self.data)
        data['scanner']['media_types'] = [
            {'id': 'custom', 'name': 'Custom', 'priority': 100, 'pattern': r'CUSTOM(?P<avid>\d+)', 'avid_format': 'X-{avid}'},
            {'id': 'normal', 'name': 'Normal', 'detector': 'fallback'},
        ]
        scanner = Cfg.model_validate(data).scanner
        paths = self.files('CUSTOM123-1.mp4', 'CUSTOM123-2.mp4')
        self.assertEqual(group_files(paths, scanner), [paths])
        from javsp.multipart import media_identity
        self.assertEqual(media_identity(paths[0], scanner), ('dvdid', 'x-123'))
        self.assertNotEqual(media_identity(paths[0], self.config.scanner), ('dvdid', 'x-123'))

    def test_single_video_and_hard_link_parts(self):
        single = self.files('ABC-123.mp4')[0]
        movie = scan_movies(str(single))[0]
        output = self.root / 'organized'
        output.mkdir()
        movie.save_dir, movie.basename = str(output), movie.dvdid
        movie.rename_files()
        self.assertTrue((output / 'ABC-123.mp4').is_file())
        paths = self.files('FC2-4953812-1.strm', 'FC2-4953812-2.strm')
        self.data['scanner']['input_files'] = list(map(str, paths))
        self.config = Cfg.model_validate(self.data)
        movie = scan_movies(str(paths[0]))[0]
        movie.save_dir, movie.basename = str(output), movie.dvdid
        movie.rename_files(use_hardlink=True)
        self.assertTrue(all(path.exists() for path in paths))
        for number, original in enumerate(paths, 1):
            self.assertTrue(os.path.samefile(original, output / f'FC2-4953812-CD{number}.strm'))

    def test_cross_drive_log_path_does_not_abort_file_organization(self):
        for hard_link in (False, True):
            with self.subTest(hard_link=hard_link):
                incoming = f'incoming-{hard_link}'
                paths = self.files(f'{incoming}/FC2-4953812-1.mp4',
                                   f'{incoming}/FC2-4953812-2.mp4')
                movie = scan_movies(str(paths[0].parent))[0]
                output = self.root / f'output-{hard_link}'
                output.mkdir()
                movie.save_dir, movie.basename = str(output), movie.dvdid
                destinations = [output / f'FC2-4953812-CD{number}.mp4'
                                for number in (1, 2)]
                for destination in destinations:
                    destination.write_bytes(b'old video')
                # Windows cannot make a C: path relative to an F: cwd.
                # Simulate only that logging boundary; keep file I/O real.
                with patch('javsp.datatype.os.path.relpath', side_effect=ValueError(
                        "path is on mount 'C:', start on mount 'F:'")), \
                     self.assertLogs('javsp.datatype', level='INFO') as logs:
                    movie.rename_files(use_hardlink=hard_link, policy='always')
                self.assertEqual(movie.new_paths, list(map(str, destinations)))
                for source, destination in zip(paths, destinations):
                    self.assertEqual(destination.read_bytes(), b'x' * 20)
                    self.assertEqual(source.exists(), hard_link)
                    if hard_link:
                        self.assertTrue(os.path.samefile(source, destination))
                    self.assertTrue(any(str(source) in line for line in logs.output))
                self.assertFalse(list(output.glob('.javsp-backup-*')))

    def test_manifest_excludes_siblings_and_keeps_small_tail(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4', 'ABC-123.mp4')
        paths[1].write_bytes(b'x')
        self.data['scanner']['input_files'] = list(map(str, paths[:2]))
        self.config = Cfg.model_validate(self.data)
        movies = scan_movies(str(paths[0]))
        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0].files, list(map(str, paths[:2])))
        paths[1].unlink()
        with self.assertRaises(FileNotFoundError):
            scan_movies(str(paths[0]))

    def create_web_tasks(self, path=None, selected=None):
        with patch.object(tasks, '_preset_config_data', return_value=(copy.deepcopy(self.data), {'name': 'Test'})), \
             patch.object(tasks, '_preset_task_concurrency', return_value=2), \
             patch.object(tasks, 'DATA_DIR', self.root / 'state'), \
             patch.object(tasks, '_logs', {}), \
             patch.object(tasks, '_persist'), patch('javsp_web.task_store.upsert_many'), \
             patch.object(tasks, '_enqueue_task') as thread:
            result = tasks.create_tasks(
                str(path or self.root), source='schedule', schedule_id='schedule-test',
                input_files=None if selected is None else [str(item) for item in selected])
        return result, thread

    def test_explicit_only_copy_selection_reports_the_skip_without_adding_the_original(self):
        original, duplicate = self.files('hhd800.com@AVSA-223.strm', 'hhd800.com@AVSA-223(1).strm')
        for path in (original, duplicate):
            path.write_text('https://example.test/only-copy', encoding='utf-8')
        with self.assertRaises(tasks.NoScrapeTasksError) as caught:
            self.create_web_tasks(selected=[duplicate])
        message = str(caught.exception)
        self.assertIn('已跳过重复副本，无可处理文件', message)
        self.assertIn('hhd800.com@AVSA-223(1).strm → hhd800.com@AVSA-223.strm', message)
        self.assertNotIn('最小匹配文件大小', message, '只选副本时不得误报文件大小不符')
        self.assertNotIn('example.test', message, '提示不得包含链接内容')
        self.assertTrue(original.exists() and duplicate.exists(), '两个文件都保留原处')

    def test_web_creates_one_task_per_movie_with_persisted_manifest(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4', 'ABC-123.mp4')
        paths[0].write_bytes(b'x')
        created, thread = self.create_web_tasks()
        self.assertEqual(len(created), 2)
        self.assertEqual(thread.call_count, 2)
        task = next(item for item in created if len(item['input_files']) == 2)
        self.assertEqual(task['size_bytes'], 21)
        self.assertEqual(task['source'], 'schedule')
        self.assertEqual(task['schedule_id'], 'schedule-test')
        config = yaml.safe_load(Path(task['config_path']).read_text(encoding='utf-8'))
        self.assertEqual(config['scanner']['input_files'], list(map(str, paths[:2])))
        self.config = Cfg.model_validate(config)
        self.assertEqual(scan_movies(task['input_directory'])[0].part_numbers, [1, 2])

    def test_web_ambiguity_skips_problem_files_and_scrapes_the_rest(self):
        self.files('ABC-123.mp4', 'FC2-4953812-1.mp4', 'FC2PPV-4953812-1.mkv')
        created, thread = self.create_web_tasks()
        self.assertEqual(len(created), 1, '分 P 问题只跳过问题文件，健康影片继续')
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(Path(created[0]['input_directory']).name, 'ABC-123.mp4')

    def test_remaining_part_keeps_number_and_does_not_overwrite(self):
        paths = self.files('FC2-4953812-1.mp4')
        movie = scan_movies(str(paths[0]))[0]
        output = self.root / 'organized'
        output.mkdir()
        movie.save_dir, movie.basename = str(output), movie.dvdid
        existing = output / 'FC2-4953812-CD2.mp4'
        existing.write_bytes(b'existing')
        movie.rename_files()
        self.assertEqual((output / 'FC2-4953812-CD1.mp4').read_bytes(), b'x' * 20)
        self.assertEqual(existing.read_bytes(), b'existing')

    def test_collision_checked_before_any_part_moves(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4')
        movie = scan_movies(str(self.root))[0]
        output = self.root / 'organized'
        output.mkdir()
        movie.save_dir, movie.basename = str(output), movie.dvdid
        (output / 'FC2-4953812-CD2.mp4').write_bytes(b'existing')
        movie.rename_files()
        self.assertTrue(all(path.exists() for path in paths))
        self.assertFalse((output / 'FC2-4953812-CD1.mp4').exists())
        self.assertEqual((output / 'FC2-4953812-CD2.mp4').read_bytes(), b'existing')

    def test_existing_movie_policies_and_equal_versions(self):
        for policy, size, newer, replaced in [('never', 5, True, False), ('always', 40, False, True),
                                              ('larger', 5, False, True), ('larger', 40, True, False),
                                              ('larger', 20, True, False), ('newer', 40, True, True),
                                              ('newer', 5, False, False)]:
            with self.subTest(policy=policy, size=size, newer=newer):
                source = self.files('incoming/ABC-123.mp4')[0]
                movie = scan_movies(str(source))[0]
                output = self.root / 'organized'
                output.mkdir(exist_ok=True)
                target = output / 'ABC-123.mp4'
                target.write_bytes(b'o' * size)
                os.utime(source, (200, 200))
                os.utime(target, (100 if newer else 300, 100 if newer else 300))
                movie.save_dir, movie.basename = str(output), 'ABC-123'
                movie.rename_files(policy=policy)
                self.assertEqual(target.read_bytes(), b'x' * 20 if replaced else b'o' * size)
                self.assertEqual(source.exists(), not replaced)

    def test_overwrite_failure_restores_all_parts_and_existing_videos(self):
        paths = self.files('incoming/FC2-4953812-1.mp4', 'incoming/FC2-4953812-2.mp4')
        movie = scan_movies(str(paths[0].parent))[0]
        output = self.root / 'organized'
        output.mkdir()
        targets = [output / f'FC2-4953812-CD{number}.mp4' for number in (1, 2)]
        for target in targets:
            target.write_bytes(b'original')
        movie.save_dir, movie.basename = str(output), movie.dvdid
        import shutil
        real_move = shutil.move
        def move(src, dst):
            if str(src) == str(paths[1]):
                raise OSError('simulated failure')
            return real_move(src, dst)
        with patch('javsp.datatype.shutil.move', side_effect=move), self.assertRaises(OSError):
            movie.rename_files(policy='always')
        self.assertTrue(all(path.read_bytes() == b'x' * 20 for path in paths))
        self.assertTrue(all(path.read_bytes() == b'original' for path in targets))
        self.assertFalse(list(output.glob('.javsp-backup-*')))

    def test_cross_drive_log_path_does_not_interrupt_organization(self):
        for hardlink in (False, True):
            with self.subTest(hardlink=hardlink):
                source = self.files(f'incoming-{hardlink}/ABC-123.mp4')[0]
                movie = scan_movies(str(source))[0]
                output = self.root / f'output-{hardlink}'
                output.mkdir()
                target = output / 'ABC-123.mp4'
                target.write_bytes(b'old video')
                movie.save_dir, movie.basename = str(output), 'ABC-123'
                # Windows cannot express a C: media path relative to an F: cwd.
                with patch('javsp.datatype.os.path.relpath', side_effect=ValueError(
                        "path is on mount 'C:', start on mount 'F:'")):
                    movie.rename_files(use_hardlink=hardlink, policy='always')
                self.assertEqual(target.read_bytes(), b'x' * 20)
                self.assertEqual(movie.new_paths, [str(target)])
                self.assertEqual(source.exists(), hardlink)
                if hardlink:
                    self.assertTrue(os.path.samefile(source, target))
                self.assertFalse(list(output.glob('.javsp-backup-*')))

    def test_never_preserves_existing_artwork_before_downloads(self):
        source = self.files('incoming/ABC-123.mp4')[0]
        movie = scan_movies(str(source))[0]
        output = self.root / 'organized'
        output.mkdir()
        poster = output / 'poster.jpg'
        poster.write_bytes(b'original image')
        movie.save_dir, movie.basename, movie.poster_file = str(output), 'ABC-123', str(poster)
        self.assertFalse(movie.prepare_organization('never'))
        self.assertEqual(poster.read_bytes(), b'original image')
        self.assertTrue(source.exists())

    def test_existing_version_with_different_extension_is_compared(self):
        source = self.files('incoming/ABC-123.mp4')[0]
        movie = scan_movies(str(source))[0]
        output = self.root / 'organized'
        output.mkdir()
        old = output / 'ABC-123.mkv'
        old.write_bytes(b'o' * 40)
        movie.save_dir, movie.basename = str(output), 'ABC-123'
        movie.rename_files(policy='larger')
        self.assertTrue(source.exists())
        self.assertFalse((output / 'ABC-123.mp4').exists())
        movie.rename_files(policy='always')
        self.assertFalse(old.exists())
        self.assertEqual((output / 'ABC-123.mp4').read_bytes(), b'x' * 20)

    def test_never_preserves_alternate_cover_formats_and_stills(self):
        source = self.files('incoming/ABC-123.mp4')[0]
        for asset in ('poster.png', 'extrafanart/0.png'):
            with self.subTest(asset=asset):
                movie = scan_movies(str(source))[0]
                output = self.root / asset.replace('/', '-')
                existing = output / asset
                existing.parent.mkdir(parents=True)
                existing.write_bytes(b'original image')
                movie.save_dir, movie.basename = str(output), 'ABC-123'
                movie.poster_file = str(output / 'poster.jpg')
                self.assertFalse(movie.prepare_organization('never'))
                self.assertEqual(existing.read_bytes(), b'original image')
                self.assertTrue(source.exists())

    def test_existing_extrafanart_reaches_organization(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4')
        movie = scan_movies(str(self.root))[0]
        output = self.root / 'organized'
        (output / 'extrafanart').mkdir(parents=True)
        sentinel = output / 'extrafanart/keep.txt'
        sentinel.write_text('keep', encoding='utf-8')
        movie.save_dir, movie.basename = str(output), movie.dvdid
        movie.fanart_file, movie.poster_file, movie.nfo_file = [str(output / name) for name in ('fanart.jpg', 'poster.jpg', 'movie.nfo')]
        movie.info = MovieInfo(movie.dvdid)
        movie.info.title = 'Test'
        movie.info.big_covers = []
        movie.info.covers = []
        movie.info.preview_pics = ['https://example.test/image.png']
        self.data['translator']['engine'] = None
        self.data['summarizer']['extra_fanarts']['enabled'] = True
        self.data['summarizer']['move_files'] = True
        self.data['summarizer']['path']['hard_link'] = False
        config = Cfg.model_validate(self.data)
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'RunNormalMode')
        events = []
        namespace = dict(os=os, time=Mock(), Cfg=lambda: config, logger=logging.getLogger('multipart-test'),
                         tqdm=lambda *args, **kwargs: args[0] if args else Mock(), progress_enabled=lambda: True,
                         progress_event=lambda stage, **kwargs: events.append((stage, kwargs)),
                         fallback_media_type_id=lambda: 'normal', parallel_crawler=lambda *args: [movie.info],
                         info_summary=lambda *args: True, generate_names=lambda *args: None,
                         download_cover=lambda *args, **kwargs: None, download=lambda *args: {},
                         valid_pic=lambda *args: True, get_fmt_size=lambda *args: '1 B',
                         get_pic_size=lambda *args: (1, 1), write_nfo=Mock())
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'RunNormalMode', 'exec'), namespace)
        self.assertEqual(namespace['RunNormalMode']([movie]), [movie])
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')
        self.assertTrue((output / 'FC2-4953812-CD1.mp4').exists())
        self.assertTrue((output / 'FC2-4953812-CD2.mp4').exists())
        self.assertTrue(any(stage == 'movie' and event.get('status') == 'completed' for stage, event in events))


if __name__ == '__main__':
    unittest.main()
