"""Offline regressions for missing fields, retry policy and log presentation."""
import ast
import copy
import io
import json
import logging
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

import lxml.html
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor' / 'JavSP'))

from javsp_web.task_logs import build_log_entries, log_text
from javsp.datatype import MovieInfo
from javsp.web import fc2, javmenu
from javsp.web.mirrors import get_with_mirror_fallback
from javsp.web.exceptions import (MovieNotFoundError, MovieDuplicateError, SiteBlocked,
                                  SitePermissionError, CredentialError, WebsiteError)


def event(stage, **values):
    return 'JAVSP_PROGRESS ' + json.dumps(dict(stage=stage, **values), ensure_ascii=False)


def success_log():
    lines = ['任务已排队: /video/BBAN-601.strm', 'CookieCloud 已同步：11 个站点，30 条 Cookie',
             '==================================', '# Jav Scraper Package: 1.8.0',
             event('scan', status='running'), '扫描影片文件...',
             event('scan', status='completed', total=1), event('movie', status='running', index=1, total=1),
             event('metadata', dvdid='BBAN-601')]
    for source in ('javbus', 'javdb', 't66y'):
        lines.append(event('crawler', name=source, status='running'))
        lines.extend(event('crawler', name=source, status='retrying', attempt=i, reason='connection timeout') for i in (1, 2))
        lines.append(event('crawler', name=source, status='success' if source == 't66y' else 'failed', reason='' if source == 't66y' else 'SSLError CERTIFICATE_VERIFY_FAILED'))
    lines += [event('summary', done=0), event('summary', done=1), event('metadata', dvdid='BBAN-601', title='演示影片'),
              event('images', kind='cover', done=0, total=1), event('images', kind='cover', done=1, total=1)]
    for i in range(12):
        lines += [event('images', kind='fanart', done=i, total=12, status='downloading', current=i+1),
                  event('images', kind='fanart', done=i+1, total=12, status='completed', current=i+1)]
    return lines + [event('movie', status='completed', total=1), event('task', status='completed', total=1), 'JavSP 执行完成']


class LogTests(unittest.TestCase):
    def test_process_failure_reason_uses_structured_movie_error(self):
        from javsp_web.tasks import _process_failure_reason

        lines = [
            event('images', kind='fanart', done=0, total=10),
            event('movie', status='failed', error='[WinError 183] 文件已存在'),
        ]
        self.assertEqual(_process_failure_reason(lines), '[WinError 183] 文件已存在')

    def test_process_failure_reason_falls_back_to_log_message(self):
        from javsp_web.tasks import _process_failure_reason

        self.assertEqual(_process_failure_reason(['影片刮削失败: extrafanart 已存在']), 'extrafanart 已存在')

    def test_file_exists_failure_is_actionable(self):
        rows = build_log_entries([], 'failed', '[WinError 183] 文件已存在')
        self.assertIn('extrafanart', '\n'.join(log_text(rows)))

    def test_worker_keeps_traceback_in_rotating_diagnostic_file(self):
        with tempfile.TemporaryDirectory() as folder:
            logfile = Path(folder) / 'task.log'
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'vendor/JavSP'), JAVSP_PROGRESS='1', JAVSP_DIAGNOSTIC_LOG=str(logfile))
            code = "import javsp.__main__ as worker\ntry:\n raise ValueError('diagnostic-test')\nexcept ValueError:\n worker.logger.debug('parser failed', exc_info=True)\nworker.progress_event('task', status='completed')\n"
            result = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT / 'vendor/JavSP', capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            self.assertIn('Traceback', logfile.read_text(encoding='utf-8'))
            self.assertNotIn(b'Traceback', result.stdout + result.stderr)
            self.assertIn(b'JAVSP_PROGRESS', result.stdout)

    def test_task_response_does_not_overwrite_stored_events(self):
        from javsp_web import tasks
        original = success_log()
        record = dict(id='log-test', input_directory='/not-a-real-video/TEST-001.strm', status='succeeded', log_tail=original)
        with patch.object(tasks, 'load_tasks', return_value=[copy.deepcopy(record)]):
            response = tasks.get_task('log-test')
        self.assertTrue(response['log_entries'])
        self.assertEqual(response['progress']['images']['fanart_done'], 12)
        self.assertNotIn('JAVSP_PROGRESS', '\n'.join(response['log_tail']))
        self.assertEqual(original, success_log())

    def test_one_failed_result_and_active_image_retry(self):
        lines = [event('movie', status='running', index=1, total=1), event('movie', status='failed', error='抓取器均未获取到影片信息')]
        rows = build_log_entries(lines, 'failed', '抓取器均未获取到影片信息')
        self.assertEqual(sum(r['group'] == 'result' for r in rows), 1)
        rows = build_log_entries([event('image_retry', status='running')], 'succeeded', image_retry_running=True)
        self.assertTrue(any(r['group'] == 'images' and r['level'] == 'running' for r in rows))

    def test_concurrent_events_are_complete_lines(self):
        from javsp import progress
        output = io.StringIO()
        with patch.object(progress, 'enabled', return_value=True), patch.object(progress.sys, 'stdout', output):
            workers = [threading.Thread(target=lambda: [progress.emit('crawler', name='test', index=i) for i in range(50)]) for _ in range(4)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 200)
        for line in lines:
            self.assertEqual(json.loads(line.removeprefix('JAVSP_PROGRESS '))['name'], 'test')

    def test_success_is_compact_with_source_failures(self):
        rows = build_log_entries(success_log(), 'succeeded')
        self.assertLessEqual(len(rows), 13)
        self.assertEqual(len([r for r in rows if r['group'] == 'sources']), 3)
        self.assertEqual(len([r for r in rows if r['group'] == 'images']), 2)
        self.assertEqual(len([r for r in rows if r['group'] == 'result']), 1)
        text = '\n'.join(log_text(rows))
        self.assertIn('12/12', text)
        self.assertIn('HTTPS 证书验证失败', text)
        self.assertNotIn('正在重试', text)
        self.assertNotIn('Jav Scraper Package', text)

    def test_traceback_is_hidden_but_actionable_failure_remains(self):
        lines = ['list index out of range', 'Traceback (most recent call last):',
                 'File "/app/fc2.py", line 59, in parse_data', 'x = list[0]', '^^^^', 'IndexError: list index out of range',
                 event('crawler', name='fc2', status='failed', reason='list index out of range')]
        text = '\n'.join(log_text(build_log_entries(lines, 'failed', '抓取器均未获取到影片信息')))
        self.assertNotIn('Traceback', text)
        self.assertNotIn('list[0]', text)
        self.assertIn('页面缺少预期字段', text)
        self.assertIn('所有数据源', text)

    def test_fanart_failure_not_erased_by_later_progress(self):
        lines = [event('images', kind='fanart', done=0, total=3, status='failed', current=1, error='timeout'),
                 event('images', kind='fanart', done=3, total=3)]
        rows = build_log_entries(lines)
        self.assertIn('已下载 2/3 · 1 张失败', '\n'.join(log_text(rows)))
        self.assertTrue(any('第 1 张' in r['message'] for r in rows))

    def test_movie_scopes_and_unknown_warnings_survive(self):
        lines = []
        for i in (1, 2):
            lines += [event('movie', status='running', index=i, total=2), event('crawler', name='fc2', status='success')]
        lines += ['磁盘空间不足', '磁盘空间不足']
        rows = build_log_entries(lines)
        self.assertEqual(len([r for r in rows if r['group'] == 'sources']), 2)
        self.assertEqual(sum('磁盘空间不足' in r['message'] for r in rows), 1)


class ParserTests(unittest.TestCase):
    def test_fc2_missing_optional_fields_preserves_title_and_cover(self):
        html = lxml.html.fromstring('''<div class="extra items_article_left">
          <div class="items_article_headerInfo extra"><h3>演示标题</h3></div>
          <div class="items_article_MainitemThumb"><span><img src="https://example.com/cover.jpg"></span></div>
        </div>''')
        movie = MovieInfo('FC2-4971063')
        response = requests.Response()
        response.url = 'https://adult.contents.fc2.com/article/4971063/'
        with patch.object(fc2, 'request_get', return_value=response), patch.object(fc2, 'resp2html', return_value=html):
            fc2.parse_data(movie)
        self.assertEqual(movie.title, '演示标题')
        self.assertEqual(movie.cover, 'https://example.com/cover.jpg')
        self.assertIsNone(movie.publish_date)

    def test_javmenu_missing_container_is_semantic_error(self):
        response = requests.Response()
        response.url = 'https://mrzyx.xyz/TEST-001'
        for content, exception in [('<html>unknown page</html>', WebsiteError), ('<html>Just a moment</html>', SiteBlocked)]:
            with patch.object(javmenu.request, 'get', return_value=response), patch.object(javmenu, 'resp2html', return_value=lxml.html.fromstring(content)):
                with self.assertRaises(exception):
                    javmenu.parse_data(MovieInfo('TEST-001'))

    def test_javmenu_reordered_classes_and_optional_fields(self):
        response = requests.Response()
        response.url = 'https://mrzyx.xyz/TEST-001/'
        response.history = [requests.Response()]
        html = lxml.html.fromstring('<div class="px-0 extra col-md-9"><h1>TEST-001 演示标题</h1><div class="single-video"></div></div>')
        movie = MovieInfo('TEST-001')
        with patch.object(javmenu.request, 'get', return_value=response), patch.object(javmenu, 'resp2html', return_value=html):
            javmenu.parse_data(movie)
        self.assertEqual(movie.title, '演示标题')


class RetryTests(unittest.TestCase):
    def test_mirror_fallback_keeps_tls_and_reselects_request_host(self):
        get = Mock(side_effect=[requests.exceptions.SSLError(), 'ok'])
        result = get_with_mirror_fallback(get, 'https://mirror.test/search?q=TEST-001', 'https://mirror.test/', 'https://official.test', delay_raise=True)
        self.assertEqual(result, 'ok')
        self.assertEqual(get.call_args.args[0], 'https://official.test/search?q=TEST-001')
        self.assertEqual(get.call_args.kwargs, {'delay_raise': True})

    def test_unrelated_host_and_failing_official_are_not_bypassed(self):
        for source in ('https://unrelated.test/item', 'https://official.test/item'):
            get = Mock(side_effect=requests.exceptions.SSLError())
            with self.assertRaises(requests.exceptions.SSLError):
                get_with_mirror_fallback(get, source, 'https://mirror.test', 'https://official.test')
            self.assertEqual(get.call_count, 1)
        get = Mock(side_effect=requests.exceptions.SSLError())
        with self.assertRaises(requests.exceptions.SSLError):
            get_with_mirror_fallback(get, 'https://mirror.test/item', 'https://mirror.test', 'https://official.test')
        self.assertEqual(get.call_count, 2)

    def run_wrapper(self, error):
        # Load the actual worker function without starting the CLI application.
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        parallel = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parallel_crawler')
        wrapper = next(n for n in parallel.body if isinstance(n, ast.FunctionDef) and n.name == 'wrapper')
        module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
        events, calls, complete = [], [], []
        namespace = dict(globals(), logger=logging.getLogger('test'), tqdm=type('DummyTqdm', (), {}), tqdm_bar=None, progress_enabled=lambda: True,
                         progress_event=lambda stage, **kw: events.append(kw), mark_crawler_complete=lambda: complete.append(True))
        exec(compile(module, 'crawler-wrapper', 'exec'), namespace)
        def parser(info):
            calls.append(True)
            raise error
        namespace['wrapper'](parser, MovieInfo('TEST-001'), 3)
        self.assertEqual(complete, [True])
        return calls, events

    def test_forbidden_and_tls_are_not_retried(self):
        response = requests.Response()
        response.status_code = 403
        for error in (requests.HTTPError('403 Forbidden', response=response), requests.exceptions.SSLError('CERTIFICATE_VERIFY_FAILED'), IndexError('list index out of range'), WebsiteError('页面结构变化')):
            calls, events = self.run_wrapper(error)
            self.assertEqual(len(calls), 1)
            self.assertEqual(events[-1]['status'], 'failed')
            self.assertNotIn('retrying', [e['status'] for e in events])

    def test_transient_timeout_retries_without_phantom_last_retry(self):
        calls, events = self.run_wrapper(requests.exceptions.Timeout('timed out'))
        self.assertEqual(len(calls), 3)
        self.assertEqual([e['status'] for e in events], ['running', 'retrying', 'retrying', 'failed'])


if __name__ == '__main__':
    unittest.main()
