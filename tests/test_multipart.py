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

    def test_identifiers_are_not_parts(self):
        for name in ('ABC-123.mp4', 'FC2-4953812.mp4', '080826_01.mp4', 'HEYDOUGA-1234-123.mp4'):
            with self.subTest(name=name):
                self.assertIsNone(part_number(self.root / 'ABC-123' / name, self.config.scanner))
        for name, number in [('ABC-123-CD12.mp4', 12), ('ABC-123-part2.mp4', 2), ('ssni00123-10.mp4', 10), ('ssni00123-CD12.mp4', 12), ('ssni00123-pt2.mp4', 2)]:
            with self.subTest(name=name):
                self.assertEqual(part_number(name, self.config.scanner), number)

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

    def create_web_tasks(self):
        with patch.object(tasks, '_preset_config_data', return_value=(copy.deepcopy(self.data), {'name': 'Test'})), \
             patch.object(tasks, '_preset_task_concurrency', return_value=2), \
             patch.object(tasks, 'DATA_DIR', self.root / 'state'), \
             patch.object(tasks, '_logs', {}), \
             patch.object(tasks, '_persist'), patch('javsp_web.task_store.upsert_many'), \
             patch.object(tasks, '_enqueue_task') as thread:
            result = tasks.create_tasks(str(self.root), source='schedule', schedule_id='schedule-test')
        return result, thread

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

    def test_web_ambiguity_does_not_start_any_tasks(self):
        self.files('ABC-123.mp4', 'FC2-4953812-1.mp4', 'FC2PPV-4953812-1.mkv')
        with patch.object(tasks, 'create_task') as create:
            with self.assertRaises(ValueError):
                self.create_web_tasks()
            create.assert_not_called()

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
        with self.assertRaises(FileExistsError):
            movie.rename_files()
        self.assertTrue(all(path.exists() for path in paths))

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
