"""Regressions for policy dispositions and legacy task logs."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor' / 'JavSP'))

from javsp_web.task_logs import build_log_entries, log_text


def event(stage, **values):
    return 'JAVSP_PROGRESS ' + json.dumps(dict(stage=stage, **values), ensure_ascii=False)


def movie_lines(disposition, index=1, total=1):
    return [event('movie', status='running', index=index, total=total),
            disposition, event('movie', status='completed', index=index, total=total)]


def results(lines, status='succeeded', **kwargs):
    return [row for row in build_log_entries(lines, status, **kwargs) if row['group'] == 'result']


class OrganizationLogTests(unittest.TestCase):
    def test_skip_policies(self):
        for policy, label in [('never', '不覆盖'), ('always', '总是覆盖'),
                              ('larger', '仅覆盖较大文件'), ('newer', '仅覆盖较新文件')]:
            with self.subTest(policy=policy):
                lines = movie_lines(event('organization', status='skipped', policy=policy, reason='existing_video'))
                lines.append(event('task', status='completed', total=1))
                rows = results(lines)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['message'], f'已跳过整理 · 保留已有影片（{label}）')
                self.assertEqual(rows[0]['level'], 'info')
                text = '\n'.join(log_text(rows))
                self.assertNotIn('影片刮削完成', text)
                self.assertNotIn('任务完成', text)

    def test_replacement_policies_and_no_conflict(self):
        for policy, label in [('always', '总是覆盖'), ('larger', '仅覆盖较大文件'), ('newer', '仅覆盖较新文件')]:
            with self.subTest(policy=policy):
                rows = results(movie_lines(event('file_organizer', replaced_existing=True, policy=policy)))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['message'], f'已覆盖已有影片（{label}）')
                self.assertEqual(rows[0]['level'], 'success')
        rows = results(movie_lines(event('file_organizer', replaced_existing=False, policy='always')))
        self.assertEqual(rows[0]['message'], '任务完成')

    def test_legacy_text_and_retained_event(self):
        text = '保留已有资料与图片，跳过本次整理（never）'
        rows = build_log_entries([text], 'succeeded')
        self.assertTrue(any(row['group'] == 'notes' and row['message'] == text for row in rows))
        self.assertEqual(results([text])[0]['message'], '已跳过整理 · 保留已有资料与图片（不覆盖）')
        rows = results([event('movie', status='completed', retained_existing=True, total=1)])
        self.assertEqual(rows[0]['message'], '已跳过整理 · 保留已有')
        rows = results(movie_lines('保留已有影片，跳过本次整理（larger）: /video/old.mkv'))
        self.assertIn('仅覆盖较大文件', rows[0]['message'])

    def test_legacy_retained_without_reason_is_neutral(self):
        for reason in [None, 'unknown', {'bad': True}]:
            with self.subTest(reason=reason):
                lines = [event('movie', status='completed', retained_existing=True, reason=reason, total=1)]
                for status in ['', 'succeeded']:
                    rows = results(lines, status)
                    self.assertEqual(rows[0]['message'], '已跳过整理 · 保留已有')
                    self.assertNotIn('影片', rows[0]['message'])
                    self.assertNotIn('资料与图片', rows[0]['message'])

    def test_retained_event_preserves_known_asset_reason(self):
        lines = movie_lines('保留已有资料与图片，跳过本次整理（never）')
        lines[-1] = event('movie', status='completed', retained_existing=True, total=1)
        self.assertEqual(results(lines)[0]['message'], '已跳过整理 · 保留已有资料与图片（不覆盖）')
        lines = [event('movie', status='completed', retained_existing=True,
                       reason='existing_assets', policy='never', total=1)]
        self.assertEqual(results(lines)[0]['message'], '已跳过整理 · 保留已有资料与图片（不覆盖）')

    def test_legacy_replacement_without_policy(self):
        rows = results(movie_lines(event('file_organizer', replaced_existing=True)))
        self.assertEqual(rows[0]['message'], '已覆盖已有影片')

    def test_multi_movie_keeps_dispositions_and_counts(self):
        lines = movie_lines(event('organization', status='skipped', policy='never'), 1, 3)
        lines += movie_lines(event('file_organizer', replaced_existing=True, policy='newer'), 2, 3)
        lines += movie_lines(event('file_organizer', replaced_existing=False), 3, 3)
        lines.append(event('task', status='completed', total=3))
        rows = results(lines)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['message'], '任务完成')
        self.assertEqual(rows[-1]['detail'], '跳过 1 部 · 覆盖 1 部')
        self.assertTrue(any('已跳过整理' in row['message'] for row in rows))
        self.assertTrue(any('已覆盖已有影片' in row['message'] for row in rows))
        self.assertFalse(any(row['message'] == '影片刮削完成' for row in rows))

    def test_multi_movie_skip_and_normal(self):
        lines = movie_lines(event('organization', status='skipped', policy='never'), 1, 2)
        lines += [event('movie', status='running', index=2, total=2), event('movie', status='completed', index=2, total=2)]
        rows = results(lines)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['message'], '任务完成')
        self.assertEqual(rows[-1]['detail'], '跳过 1 部 · 覆盖 0 部')

    def test_failed_and_cancelled_outcomes_unchanged(self):
        for disposition in [event('organization', status='skipped', policy='never'),
                            event('file_organizer', replaced_existing=True, policy='always')]:
            lines = movie_lines(disposition)
            for status, message, level in [('failed', '任务失败', 'error'), ('cancelled', '任务已停止', 'muted')]:
                with self.subTest(status=status, disposition=disposition):
                    rows = results(lines, status, error='connection timed out')
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]['message'], message)
                    self.assertEqual(rows[0]['level'], level)
                    self.assertEqual(rows[0]['detail'], '连接或读取超时，请检查网络后重试' if status == 'failed' else '')

    def test_movie_failure_does_not_show_replacement(self):
        lines = [event('movie', status='running', index=1, total=2),
                 event('file_organizer', replaced_existing=True, policy='always'),
                 event('movie', status='failed', error='connection timed out'),
                 event('movie', status='running', index=2, total=2),
                 event('movie', status='completed')]
        rows = results(lines, 'failed')
        self.assertEqual([row['message'] for row in rows], ['影片刮削失败', '任务失败'])

    def test_last_disposition_wins_and_duplicates_are_merged(self):
        lines = [event('movie', status='running', index=1, total=1),
                 event('organization', status='skipped', policy='never'),
                 event('organization', status='skipped', policy='never'),
                 event('file_organizer', replaced_existing=True, policy='always'),
                 event('movie', status='completed')]
        self.assertEqual(results(lines)[0]['message'], '已覆盖已有影片（总是覆盖）')
        lines.insert(-1, event('organization', status='skipped', policy='larger'))
        self.assertEqual(results(lines)[0]['message'], '已跳过整理 · 保留已有（仅覆盖较大文件）')

    def test_skip_without_completion_and_image_retry_scope(self):
        lines = [event('organization', status='skipped', policy='never', reason='existing_assets')]
        self.assertEqual(results(lines)[0]['message'], '已跳过整理 · 保留已有资料与图片（不覆盖）')
        lines.append(event('image_retry', status='running'))
        rows = build_log_entries(lines, 'succeeded', image_retry_running=True)
        self.assertTrue(any(row['group'] == 'images' and row['level'] == 'running' for row in rows))
        self.assertTrue(any(row['group'] == 'result' and '资料与图片' in row['message'] for row in rows))

    def test_unknown_or_malformed_policy_is_safe(self):
        for policy, suffix in [('custom', '（custom）'), (None, ''), ({'bad': True}, ''), (['never'], '')]:
            with self.subTest(policy=policy):
                rows = results(movie_lines(event('file_organizer', replaced_existing=True, policy=policy)))
                self.assertEqual(rows[0]['message'], '已覆盖已有影片' + suffix)

    def test_live_result_and_plain_history(self):
        lines = movie_lines(event('file_organizer', replaced_existing=True, policy='larger'))
        lines.append(event('task', status='completed', total=1))
        rows = results(lines, '')
        self.assertTrue(all(row['message'] == '已覆盖已有影片（仅覆盖较大文件）' for row in rows))
        rows = results([event('movie', status='completed'), event('task', status='completed', total=1)])
        self.assertEqual(rows, [dict(group='result', message='任务完成', level='success', detail='')])

    def test_input_events_are_not_modified(self):
        lines = movie_lines(event('organization', status='skipped', policy='never'))
        original = copy.deepcopy(lines)
        build_log_entries(lines, 'succeeded')
        self.assertEqual(lines, original)

    def test_trimmed_history_uses_stored_replacement_without_policy(self):
        organizer = {'replaced_existing': True, 'original_files': ['/incoming/TEST.mkv'],
                     'organized_files': ['/output/TEST.mkv'], 'policy': 'always'}
        original = copy.deepcopy(organizer)
        for lines in [[], [event('movie', status='completed', total=1),
                           event('task', status='completed', total=1)],
                      [event('image_retry', status='running')]]:
            with self.subTest(lines=lines):
                rows = results(lines, organizer=organizer)
                self.assertEqual(rows, [dict(group='result', message='已覆盖已有影片', level='success', detail='')])
        self.assertEqual(organizer, original)

    def test_explicit_log_outcome_wins_over_stored_replacement(self):
        organizer = {'replaced_existing': True}
        lines = movie_lines(event('organization', status='skipped', policy='never', reason='existing_assets'))
        self.assertEqual(results(lines, organizer=organizer)[0]['message'],
                         '已跳过整理 · 保留已有资料与图片（不覆盖）')
        lines = movie_lines(event('file_organizer', replaced_existing=True, policy='newer'))
        self.assertEqual(results(lines, organizer=organizer)[0]['message'], '已覆盖已有影片（仅覆盖较新文件）')
        lines = [event('movie', status='completed', retained_existing=True, total=1)]
        self.assertEqual(results(lines, organizer=organizer)[0]['message'], '已跳过整理 · 保留已有')

    def test_stored_replacement_does_not_override_other_task_states(self):
        for status, message, level in [('failed', '任务失败', 'error'), ('cancelled', '任务已停止', 'muted')]:
            rows = results([], status, organizer={'replaced_existing': True}, error='connection timed out')
            self.assertEqual(rows[0]['message'], message)
            self.assertEqual(rows[0]['level'], level)
        self.assertEqual(results([], '', organizer={'replaced_existing': True}), [])

    def test_stored_replacement_is_not_a_multi_movie_summary(self):
        for lines in [[event('task', status='completed', total=2)],
                      [event('movie', status='running', index=1),
                       event('movie', status='running', index=2)]]:
            rows = results(lines, organizer={'replaced_existing': True})
            self.assertEqual(rows[-1]['message'], '任务完成')
            self.assertEqual(rows[-1]['detail'], '')

    def test_missing_or_invalid_organizer_keeps_original_result(self):
        for organizer in [None, {}, [], 'invalid', {'replaced_existing': False}, {'replaced_existing': 'false'}]:
            with self.subTest(organizer=organizer):
                self.assertEqual(results([], organizer=organizer)[0]['message'], '任务完成')
        rows = results([event('movie', status='failed', total=1)], organizer={'replaced_existing': True})
        self.assertEqual(rows[0]['message'], '任务完成')

    def test_task_detail_passes_stored_organizer_without_mutating_record(self):
        from javsp_web import tasks
        record = dict(id='organization-history-test', input_directory='/missing/TEST.mkv',
                      file_name='TEST.mkv', size_bytes=0, status='succeeded',
                      log_tail=[event('task', status='completed', total=1)],
                      file_organizer={'replaced_existing': True})
        original = copy.deepcopy(record)
        progress = dict(metadata={}, stages={key: dict(percent=0, done=0, total=0)
                                             for key in ('concurrent', 'summary', 'images')},
                        images=dict(failed=False, fanart_total=0, fanart_done=0),
                        crawler_details={}, output={})
        with patch.object(tasks, '_logs', {}), \
             patch.object(tasks, '_task_progress', return_value=progress), \
             patch.object(tasks, '_artwork_availability', return_value={}):
            response = tasks._decorate_task(copy.deepcopy(record))
        self.assertEqual(response['status'], 'succeeded')
        self.assertEqual(response['log_tail'], ['已覆盖已有影片'])
        self.assertEqual(response['log_entries'], [dict(group='result', message='已覆盖已有影片', level='success', detail='')])
        self.assertEqual(record, original)


class OrganizationEventTests(unittest.TestCase):
    def test_real_prepare_emits_video_and_asset_skip_events(self):
        from javsp.datatype import Movie
        from javsp import progress
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'incoming.mkv'
            source.write_bytes(b'incoming')
            output = root / 'output'
            output.mkdir()
            existing = output / 'TEST-001.mkv'
            existing.write_bytes(b'existing')
            movie = Movie('TEST-001')
            movie.files = [str(source)]
            movie.save_dir = str(output)
            movie.basename = 'TEST-001'
            movie.nfo_file = str(output / 'TEST-001.nfo')
            movie.fanart_file = str(output / 'fanart.jpg')
            movie.poster_file = str(output / 'poster.jpg')
            capture = io.StringIO()
            with patch.dict(os.environ, {'JAVSP_PROGRESS': '1'}), patch.object(progress.sys, 'stdout', capture):
                self.assertFalse(movie.prepare_organization('never'))
                existing.unlink()
                Path(movie.nfo_file).write_text('existing metadata', encoding='utf-8')
                self.assertFalse(movie.prepare_organization('never'))
            events = [json.loads(line.removeprefix('JAVSP_PROGRESS ')) for line in capture.getvalue().splitlines()]
            self.assertEqual(events, [dict(stage='organization', status='skipped', policy='never', reason='existing_video'),
                                      dict(stage='organization', status='skipped', policy='never', reason='existing_assets')])
            self.assertEqual(source.read_bytes(), b'incoming')
            capture = io.StringIO()
            with patch.dict(os.environ, {'JAVSP_PROGRESS': '0'}), patch.object(progress.sys, 'stdout', capture):
                self.assertFalse(movie.prepare_organization('never'))
            self.assertEqual(capture.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
