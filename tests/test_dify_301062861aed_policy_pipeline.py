"""Offline policy-to-log tests using real organization and worker logic."""
import ast
import copy
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor' / 'JavSP'))

from javsp import datatype
from javsp.datatype import Movie, MovieInfo
from javsp_web.task_logs import build_log_entries

LABELS = {'never': '不覆盖', 'always': '总是覆盖',
          'larger': '仅覆盖较大文件', 'newer': '仅覆盖较新文件'}


def event_lines(events):
    return ['JAVSP_PROGRESS ' + json.dumps(dict(stage=stage, **values), ensure_ascii=False)
            for stage, values in events]


def result_rows(lines, status='succeeded'):
    return [row for row in build_log_entries(lines, status) if row['group'] == 'result']


class PolicyPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'vendor' / 'JavSP' / 'javsp' / '__main__.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls.worker_node = next(node for node in tree.body
                               if isinstance(node, ast.FunctionDef)
                               and node.name == 'RunNormalMode')

    def make_movie(self, root, incoming_size=12, existing_size=12,
                   incoming_time=2000000000, existing_time=2000000000):
        incoming = root / 'incoming'
        output = root / 'output'
        incoming.mkdir()
        output.mkdir()
        source = incoming / 'TEST-001.mkv'
        destination = output / 'TEST-001.mkv'
        source.write_bytes(b'N' * incoming_size)
        if existing_size is not None:
            destination.write_bytes(b'O' * existing_size)
            os.utime(destination, ns=(existing_time, existing_time))
        os.utime(source, ns=(incoming_time, incoming_time))
        movie = Movie('TEST-001')
        movie.files = [str(source)]
        movie.basename = 'TEST-001'
        movie.save_dir = str(output)
        movie.nfo_file = str(output / 'TEST-001.nfo')
        movie.fanart_file = str(output / 'fanart.jpg')
        movie.poster_file = str(output / 'poster.jpg')
        movie.info = MovieInfo('TEST-001')
        movie.info.title = 'Pipeline test'
        movie.info.covers = []
        movie.info.big_covers = []
        movie.info.preview_pics = []
        return movie, source, destination

    def run_worker(self, movies, policy):
        events = []
        emit = lambda stage, **values: events.append((stage, values))
        download = Mock(return_value=None)
        write = Mock()
        config = SimpleNamespace(
            translator=SimpleNamespace(ai_enabled=False, engine=None),
            crawler=SimpleNamespace(selection={'normal': ['stub']},
                                    ai_enabled=False, sleep_after_scraping=timedelta(0)),
            summarizer=SimpleNamespace(
                existing_file_policy=policy, move_files=True,
                extra_fanarts=SimpleNamespace(enabled=False),
                cover=SimpleNamespace(highres=False),
                path=SimpleNamespace(hard_link=False)))
        namespace = dict(
            Cfg=lambda: config, os=os, time=time, Duration=timedelta,
            logger=logging.getLogger('dify-policy-pipeline'),
            tqdm=lambda *args, **kwargs: args[0] if args else Mock(),
            progress_enabled=lambda: True, progress_event=emit,
            fallback_media_type_id=lambda: 'normal',
            parallel_crawler=lambda *args: {'stub': object()},
            info_summary=lambda *args: True, generate_names=lambda movie: None,
            download_cover=download, write_nfo=write)
        module = ast.Module(body=[copy.deepcopy(self.worker_node)], type_ignores=[])
        exec(compile(module, 'actual-RunNormalMode', 'exec'), namespace)
        with patch.object(datatype, 'progress_event', emit):
            returned = namespace['RunNormalMode'](movies)
        self.assertEqual([id(movie) for movie in returned], [id(movie) for movie in movies])
        self.assertFalse(any(stage == 'movie' and values.get('status') == 'failed'
                             for stage, values in events))
        return events, download, write

    def test_real_policy_decisions_reach_worker_events_and_result(self):
        for policy in LABELS:
            for relation in (-1, 0, 1):
                with self.subTest(policy=policy, relation=relation):
                    with tempfile.TemporaryDirectory() as folder:
                        size = 12 + relation if policy == 'larger' else 12
                        stamp = 2000000000 + relation * 1000000000 if policy == 'newer' else 2000000000
                        movie, source, destination = self.make_movie(
                            Path(folder), incoming_size=size, incoming_time=stamp)
                        source_before = source.read_bytes()
                        destination_before = destination.read_bytes()
                        replaced = policy == 'always' or (policy in ('larger', 'newer') and relation > 0)
                        events, download, write = self.run_worker([movie], policy)
                        rows = result_rows(event_lines(events))
                        self.assertEqual(len(rows), 1)
                        if replaced:
                            organizers = [values for stage, values in events if stage == 'file_organizer']
                            self.assertEqual(len(organizers), 1)
                            self.assertEqual(organizers[0]['policy'], policy)
                            self.assertIs(organizers[0]['replaced_existing'], True)
                            self.assertEqual(destination.read_bytes(), source_before)
                            self.assertFalse(source.exists())
                            self.assertEqual(rows[0]['message'], '已覆盖已有影片（' + LABELS[policy] + '）')
                            self.assertEqual(rows[0]['level'], 'success')
                            download.assert_called_once()
                            write.assert_called_once_with(movie.info, movie.nfo_file)
                        else:
                            skips = [values for stage, values in events if stage == 'organization']
                            self.assertEqual(skips, [dict(status='skipped', policy=policy, reason='existing_video')])
                            self.assertFalse(any(stage == 'file_organizer' for stage, values in events))
                            self.assertEqual(source.read_bytes(), source_before)
                            self.assertEqual(destination.read_bytes(), destination_before)
                            self.assertEqual(rows[0]['message'], '已跳过整理 · 保留已有影片（' + LABELS[policy] + '）')
                            self.assertEqual(rows[0]['level'], 'info')
                            download.assert_not_called()
                            write.assert_not_called()
                        self.assertNotIn('任务完成', rows[0]['message'])
                        self.assertNotIn('影片刮削完成', rows[0]['message'])
                        self.assertFalse(list(Path(movie.save_dir).glob('.javsp-backup-*')))

    def test_asset_only_skip_does_not_invent_existing_video(self):
        with tempfile.TemporaryDirectory() as folder:
            movie, source, destination = self.make_movie(Path(folder), existing_size=None)
            metadata = Path(movie.nfo_file)
            metadata.write_bytes(b'old metadata')
            events, download, write = self.run_worker([movie], 'never')
            skips = [values for stage, values in events if stage == 'organization']
            self.assertEqual(skips, [dict(status='skipped', policy='never', reason='existing_assets')])
            self.assertEqual(result_rows(event_lines(events))[0]['message'],
                             '已跳过整理 · 保留已有资料与图片（不覆盖）')
            self.assertEqual(source.read_bytes(), b'N' * 12)
            self.assertEqual(metadata.read_bytes(), b'old metadata')
            self.assertFalse(destination.exists())
            download.assert_not_called()
            write.assert_not_called()

    def test_duplicate_preparation_events_collapse_to_one_result(self):
        with tempfile.TemporaryDirectory() as folder:
            movie, source, destination = self.make_movie(Path(folder))
            events = [('movie', dict(status='running', index=1, total=1))]
            emit = lambda stage, **values: events.append((stage, values))
            with patch.object(datatype, 'progress_event', emit):
                self.assertFalse(movie.prepare_organization('larger'))
                self.assertFalse(movie.prepare_organization('larger', include_assets=False))
            self.assertEqual(sum(stage == 'organization' for stage, values in events), 2)
            rows = result_rows(event_lines(events))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['message'], '已跳过整理 · 保留已有影片（仅覆盖较大文件）')
            self.assertEqual(source.read_bytes(), b'N' * 12)
            self.assertEqual(destination.read_bytes(), b'O' * 12)

    def test_multi_movie_pipeline_keeps_each_actual_disposition(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / 'first'
            second = root / 'second'
            first.mkdir()
            second.mkdir()
            retained, _, _ = self.make_movie(first, incoming_size=12)
            replaced, _, _ = self.make_movie(second, incoming_size=13)
            events, download, write = self.run_worker([retained, replaced], 'larger')
            lines = event_lines(events)
            rows = result_rows(lines)
            self.assertEqual([row['message'] for row in rows], [
                '已跳过整理 · 保留已有影片（仅覆盖较大文件）',
                '已覆盖已有影片（仅覆盖较大文件）', '任务完成'])
            self.assertEqual(rows[-1]['detail'], '跳过 1 部 · 覆盖 1 部')
            self.assertEqual(download.call_count, 1)
            self.assertEqual(write.call_count, 1)
            for status, message, level in [('failed', '任务失败', 'error'),
                                           ('cancelled', '任务已停止', 'muted')]:
                terminal = result_rows(lines, status)
                self.assertEqual(terminal[-1]['message'], message)
                self.assertEqual(terminal[-1]['level'], level)
                self.assertFalse(any('已覆盖' in row['message'] for row in terminal))


if __name__ == '__main__':
    unittest.main()
