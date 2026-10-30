"""GET /api/crawler-config/stats: sites, rules, task statistics and caching."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import storage, tasks, task_store  # noqa: E402


class CrawlerStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.object(tasks, 'DATA_DIR', self.folder))
        self.enterContext(patch.object(tasks, '_TASK_COVERS_DIR', self.folder / 'task-covers'))
        self.enterContext(patch.object(tasks, '_logs', {}))
        storage.ensure_seed_data()
        task_store._ready.clear()
        self.server = None

    def tearDown(self):
        if self.server is not None:
            self.server._crawler_stats_cache.clear()

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        server._crawler_stats_cache.clear()
        self.enterContext(patch.dict(server.app.dependency_overrides, {
            server.current_user: lambda: {'username': 'test', 'role': 'admin'},
            server.require_admin: lambda: {'username': 'test', 'role': 'admin'},
        }))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def task(self, task_id, created_at, crawlers=None, status='succeeded'):
        # label -> raw JAVSP_PROGRESS status, mirroring the parser label set
        # in tasks.py: 完成(success) 失败(failed) 未找到(not_found) 重复(duplicate)
        raw_status = {'完成': 'success', '失败': 'failed', '未找到': 'not_found', '重复': 'duplicate'}
        lines = []
        for name, label in (crawlers or {}).items():
            lines.append('JAVSP_PROGRESS ' + json.dumps(
                {'stage': 'crawler', 'name': name, 'status': raw_status.get(label, 'success')}))
        item = dict(id=task_id, created_at=created_at, status=status,
                    input_directory=str(self.folder / (task_id + '.mp4')), file_name=task_id,
                    size_bytes=1024, log_tail=lines)
        tasks._persist(item)
        return item

    # ------------------------------------------------------------------ tests

    def test_no_data_returns_empty_counters(self):
        body = self.client().get('/api/crawler-config/stats').json()
        self.assertEqual(body['window_days'], 30)
        self.assertTrue(body['crawlers'])
        for entry in body['crawlers'].values():
            self.assertEqual(entry['scrapes'], 0)
            self.assertIsNone(entry['success_rate'])
            self.assertIsNone(entry['last_success_at'])
            self.assertIsNone(entry['last_failure_at'])
            self.assertEqual(entry['tasks'], 0)
            self.assertEqual(entry['rules'], [])

    def test_success_failure_misses_and_rate(self):
        recent = '2099-01-01T00:00:00+00:00'
        self.task('t1', recent, {'javdb': '完成', 'javbus': '失败', 'airav': '未找到'})
        self.task('t2', recent, {'javdb': '完成', 'airav': '未找到'})
        self.task('t3', recent, {'javdb': '失败', 'airav': '未找到'})
        self.task('old', '2000-01-01T00:00:00+00:00', {'javdb': '失败'})  # outside window
        body = self.client().get('/api/crawler-config/stats').json()
        javdb = body['crawlers']['javdb']
        self.assertEqual((javdb['scrapes'], javdb['attempts'], javdb['success'], javdb['failure'], javdb['misses']), (3, 3, 2, 1, 0))
        # success_rate = 完成 / (完成 + 失败); misses are excluded from the denominator.
        self.assertEqual(javdb['success_rate'], 0.6667)
        self.assertEqual(javdb['tasks'], 3)
        self.assertEqual(javdb['last_success_at'], recent)
        self.assertEqual(javdb['last_failure_at'], recent)
        airav = body['crawlers']['airav']
        self.assertEqual((airav['scrapes'], airav['attempts'], airav['success'], airav['failure'], airav['misses']), (3, 3, 0, 0, 3))
        # all-miss must not read as a 0% success rate; there were no failures.
        self.assertIsNone(airav['success_rate'])
        self.assertIsNone(airav['last_failure_at'])
        javbus = body['crawlers']['javbus']
        self.assertEqual((javbus['scrapes'], javbus['success'], javbus['failure'], javbus['misses']), (1, 0, 1, 0))
        self.assertEqual(javbus['success_rate'], 0.0)
        self.assertEqual(javbus['tasks'], 1)

    def test_retry_and_unknown_labels_are_attempts_only(self):
        # 重试 events are rewritten by the parser into final labels, but a task
        # whose log ends mid-retry keeps them; such labels must not touch
        # success/failure/misses or the success rate.
        lines = ['JAVSP_PROGRESS ' + json.dumps({'stage': 'crawler', 'name': 'javdb', 'status': 'retrying', 'attempt': 1, 'total': 2}),
                 'JAVSP_PROGRESS ' + json.dumps({'stage': 'crawler', 'name': 'javbus', 'status': 'duplicate'})]
        tasks._persist(dict(id='t-retry', created_at='2099-01-01T00:00:00+00:00', status='failed',
                            input_directory=str(self.folder / 'r.mp4'), file_name='r', size_bytes=1, log_tail=lines))
        body = self.client().get('/api/crawler-config/stats').json()
        for name in ('javdb', 'javbus'):
            entry = body['crawlers'][name]
            self.assertEqual(entry['attempts'], 1)
            self.assertEqual((entry['success'], entry['failure'], entry['misses']), (0, 0, 0))
            self.assertEqual(entry['scrapes'], 0)
            self.assertIsNone(entry['success_rate'])

    def server_module(self):
        if self.server is None:
            self.client()  # imports the server module under test
        return self.server

    def test_site_extraction_from_crawler_source(self):
        server = self.server_module()
        with patch.object(server, '_crawler_source', return_value={'name': 'demo', 'kind': 'custom', 'source': 'url = "https://example.com/a"\nref = "https://www.google.com/x"\nother = "https://mirror.example.org"'}):
            self.assertEqual(server._extract_crawler_sites('demo'), ['example.com', 'mirror.example.org'])

    def test_built_in_site_extraction_and_limits(self):
        server = self.server_module()
        javdb = server._extract_crawler_sites('javdb')
        self.assertIn('javdb.com', javdb)
        self.assertLessEqual(len(javdb), 5)
        fanza = server._extract_crawler_sites('fanza')
        self.assertIn('www.dmm.co.jp', fanza)
        self.assertNotIn('www.zhihu.com', fanza)  # comment links must not leak in

    def test_rules_associated_through_preset_selection(self):
        import yaml
        from javsp_web import directory_watch
        directory_watch.stop_scheduler()
        self.addCleanup(directory_watch.stop_scheduler)
        content = yaml.safe_dump({'crawler': {'selection': {'normal': ['javdb', 'javbus'], 'fc2': ['fc2']}}})
        storage.save_preset({'id': 'stats-preset', 'name': '统计测试', 'mode': 'yaml', 'content': content})
        directory_watch.write_rules([
            {'id': 'rule-1', 'name': '电影目录', 'path': str(self.folder / 'movies'), 'preset_id': 'stats-preset', 'enabled': True},
            {'id': 'rule-2', 'name': '另一目录', 'path': str(self.folder / 'fc2'), 'preset_id': 'default'},
        ])
        body = self.client().get('/api/crawler-config/stats').json()
        rules = body['crawlers']['javdb']['rules']
        # rule-1 (stats-preset) plus rule-2 (seeded default preset also selects javdb)
        self.assertIn({'id': 'rule-1', 'name': '电影目录'}, rules)
        self.assertIn({'id': 'rule-2', 'name': '另一目录'}, rules)
        # fc2 appears in both selections
        fc2_rules = body['crawlers']['fc2']['rules']
        self.assertIn({'id': 'rule-1', 'name': '电影目录'}, fc2_rules)
        self.assertIn({'id': 'rule-2', 'name': '另一目录'}, fc2_rules)
        # arzon is referenced by neither preset
        self.assertEqual(body['crawlers']['arzon']['rules'], [])

    def test_stats_cached_for_30_seconds(self):
        self.task('t1', '2099-01-01T00:00:00+00:00', {'javdb': '完成'})
        client = self.client()
        first = client.get('/api/crawler-config/stats').json()
        # New data must not appear while the cache is warm.
        self.task('t2', '2099-01-02T00:00:00+00:00', {'javdb': '失败'})
        second = client.get('/api/crawler-config/stats').json()
        self.assertEqual(second['crawlers']['javdb']['scrapes'], first['crawlers']['javdb']['scrapes'])
        # Expiry (monotonic clock jump) recomputes from the store.
        self.server._crawler_stats_cache['stats'] = (self.server._crawler_stats_cache['stats'][0] - 60.0, first)
        third = client.get('/api/crawler-config/stats').json()
        self.assertEqual(third['crawlers']['javdb']['scrapes'], 2)
        self.assertEqual(third['crawlers']['javdb']['failure'], 1)

    def test_runtime_comments_url_is_same_origin(self):
        body = self.client().get('/api/runtime').json()
        self.assertEqual(body['comments_url'], '/api/comments')
        self.assertTrue(body['comments_verify_url'].startswith(('http://', 'https://')))

    def test_download_auto_scrape_endpoints_removed(self):
        client = self.client()
        self.assertIn(client.post('/api/downloads/auto-scrape/path-check', json={'tags': '', 'category': ''}).status_code, (404, 405))
        self.assertEqual(client.get('/api/download-auto-scrape-runs').status_code, 404)

    def test_legacy_history_file_still_loadable(self):
        # Historical download-auto-scrape records keep their task source mapping.
        storage.AUTO_SCRAPE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        storage.AUTO_SCRAPE_HISTORY_FILE.write_text(json.dumps({'dl1:hash': {'id': 'dl1:hash', 'task_ids': ['t1']}}), encoding='utf-8')
        self.assertEqual(task_store.load(['t1']), [])
        history = storage.load_auto_scrape_history()
        self.assertIn('dl1:hash', history)


if __name__ == '__main__':
    unittest.main()
