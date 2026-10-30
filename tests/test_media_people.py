"""演员头像刮削（Gfriends）测试：mock HTTP 模拟 /Items、/Persons 与图片上传。"""
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import media_people, storage


def response(data=None, status=200, content=b'', raise_error=False):
    mock = Mock()
    mock.status_code = status
    mock.json.return_value = data if data is not None else {}
    mock.content = content
    if raise_error:
        import requests as real_requests
        mock.raise_for_status = Mock(side_effect=real_requests.HTTPError(f'{status}'))
    else:
        mock.raise_for_status = Mock()
    return mock


class MediaPeopleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.object(media_people, 'DATA_DIR', self.folder))
        self.server = {'id': 'srv1', 'name': 'Cinema', 'type': 'jellyfin',
                       'url': 'http://media.test:8096', 'api_key': 'k',
                       'libraries': ['lib1']}
        # 内置头像目录换成假演员（含括号别名），指向临时 webp 文件。
        # _avatar_content 按 _ASSET_ROOT + '/assets/avatars/<id>.webp' 解析路径。
        avatar_dir = self.folder / 'assets' / 'avatars'
        avatar_dir.mkdir(parents=True)
        catalog = {}
        for idx, name in enumerate(['波多野結衣', '三上悠亜', '天然美月（天然かのん）']):
            avatar_id = f'a{idx}'
            Image.new('RGB', (40, 40), 'red').save(avatar_dir / f'{avatar_id}.webp', 'WEBP')
            catalog[avatar_id] = {'id': avatar_id, 'name': name,
                                  'url': f'/assets/avatars/{avatar_id}.webp'}
        self.enterContext(patch.object(media_people, '_ASSET_ROOT', self.folder))
        self.enterContext(patch.object(media_people.avatars, 'avatar_directory',
                                       lambda: catalog))
        self.enterContext(patch.object(media_people, '_ALIAS_FILE',
                                       ROOT / 'vendor/JavSP/data/actress_alias.json'))
        media_people._build_lookup.cache_clear()
        self.addCleanup(media_people._build_lookup.cache_clear)
        self.enterContext(patch.object(media_people, '_scrapes', {}))
        self.uploads = []
        # 库内影片 Cast：只有女优「波多野結衣」和别名形式的「三上悠亜」在范围内；
        # 男演员/配音/导演不在库内影片 Cast 里，即便 /Persons 里有也不处理。
        self.cast_names = ['波多野 結衣', '三上悠亜', '深田えいみ']

    def run_scrape(self, persons, has_image_ids=(), upload_fail=False, cast_names=None):
        """同步执行一次完整刮削，返回 (stats, log_text)。"""
        uploaded = self.uploads
        cast = set(cast_names if cast_names is not None else self.cast_names)

        def fake_get(url, **kwargs):
            if '/Persons' in url:
                return response({'Items': persons, 'TotalRecordCount': len(persons)})
            if '/Items' in url and kwargs.get('params', {}).get('IncludeItemTypes') == 'Movie':
                # 库内影片：每部影片返回一份 People（Cast + 导演）。
                people = [{'Name': name, 'Type': 'Actor', 'Role': ''} for name in cast]
                people.append({'Name': '某导演', 'Type': 'Director', 'Role': 'Director'})
                return response({'Items': [{'Id': 'm1', 'People': people}],
                                  'TotalRecordCount': 1})
            for person in persons:
                if person['Id'] in url:
                    has = person['Id'] in has_image_ids
                    return response(status=200 if has else 404, content=b'img' if has else b'')
            return response(status=404)

        def fake_post(url, headers=None, data=None, **kwargs):
            uploaded.append((url, data))
            if upload_fail:
                return response(status=500, raise_error=True)
            return response(status=204)

        with patch.object(media_people.requests, 'get', side_effect=fake_get), \
             patch.object(media_people.requests, 'post', side_effect=fake_post):
            media_people._run_scrape(self.server)
        stats = media_people._scrapes['srv1']['stats']
        log = '\n'.join(media_people.read_log('srv1'))
        return stats, log

    # ------------------------------------------------------------------ 范围控制

    def test_out_of_scope_male_actors_are_ignored(self):
        # /Persons 返回全库人员（含男演员、配音、导演），但只有库内影片 Cast 进范围。
        persons = [
            {'Id': 'p1', 'Name': '波多野結衣'},      # 在范围内
            {'Id': 'p2', 'Name': '高田忧希'},        # 男声优，不在库内 Cast
            {'Id': 'p3', 'Name': '鸟海浩辅'},        # 配音，不在库内 Cast
            {'Id': 'p4', 'Name': '魏翔'},            # 中国演员，不在库内 Cast
        ]
        stats, log = self.run_scrape(persons)
        self.assertIn('范围内演员：1/4', log)
        self.assertEqual(stats['created'], 1)  # 只有 p1 上传
        self.assertEqual([u[0] for u in self.uploads], ['http://media.test:8096/Items/p1/Images/Primary'])
        # 范围外的人不进任何失败/未匹配计数。
        self.assertEqual(stats['unmatched'], 0)
        self.assertEqual(stats['failed'], 0)

    def test_director_in_item_people_is_excluded(self):
        # 影片 People 里 Type=Director 的不进 Cast 名字集合。
        persons = [{'Id': 'p1', 'Name': '波多野結衣'}, {'Id': 'p9', 'Name': '某导演'}]
        stats, log = self.run_scrape(persons)
        self.assertIn('范围内演员：1/2', log)

    # ------------------------------------------------------------------ 匹配归一化

    def test_exact_name_match(self):
        stats, _ = self.run_scrape([{'Id': 'p1', 'Name': '波多野結衣'}])
        self.assertEqual(stats['created'], 1)

    def test_space_and_traditional_folding_match(self):
        # 库内 Cast 名字带空格「波多野 結衣」（繁体），/Persons 名字也带空格。
        stats, _ = self.run_scrape([{'Id': 'p1', 'Name': '波多野 結衣'}])
        self.assertEqual(stats['created'], 1)

    def test_hiragana_katakana_and_alias_match(self):
        # 「三上悠亜」在库内 Cast 中；用别名/假名折叠命中（真实 alias 表里有三上悠亜）。
        stats, _ = self.run_scrape([{'Id': 'p1', 'Name': '三上悠亜'}])
        self.assertEqual(stats['created'], 1)

    def test_parenthesized_alias_match(self):
        # Gfriends 名字带括号别名「天然美月（天然かのん）」，库内用别名「天然かのん」。
        stats, _ = self.run_scrape([{'Id': 'p1', 'Name': '天然かのん'}],
                                   cast_names=['天然かのん'])
        self.assertEqual(stats['created'], 1)

    # ------------------------------------------------------------------ 计数口径

    def test_has_avatar_skips(self):
        persons = [{'Id': 'p1', 'Name': '波多野結衣'}, {'Id': 'p2', 'Name': '三上悠亜'}]
        stats, log = self.run_scrape(persons, has_image_ids={'p1', 'p2'})
        self.assertEqual(stats['skipped'], 2)
        self.assertEqual(stats['created'], 0)
        self.assertEqual(self.uploads, [])
        self.assertIn('跳过：波多野結衣', log)

    def test_in_scope_unmatched_counts_unmatched_not_failed(self):
        # 在范围内但 Gfriends 无匹配 → unmatched，不是 failed；名字进示例列表。
        persons = [{'Id': 'p1', 'Name': '波多野結衣'}, {'Id': 'p2', 'Name': '三上悠亜'},
                   {'Id': 'p9', 'Name': '深田えいみ'}]
        stats, log = self.run_scrape(persons)
        self.assertEqual(stats['created'], 2)
        self.assertEqual(stats['unmatched'], 1)
        self.assertEqual(stats['failed'], 0)
        state = media_people.scrape_state(self.server)
        self.assertEqual(state['unmatched'], ['深田えいみ'])
        self.assertIn('未匹配示例：深田えいみ', log)

    def test_upload_failure_retries_and_counts_failed(self):
        calls = []
        def fake_post(url, headers=None, data=None, **kwargs):
            calls.append(url)
            return response(status=500, raise_error=True)
        persons = [{'Id': 'p1', 'Name': '波多野結衣'}]

        def fake_get(url, **kwargs):
            if '/Persons' in url:
                return response({'Items': persons, 'TotalRecordCount': 1})
            if '/Items' in url and kwargs.get('params', {}).get('IncludeItemTypes') == 'Movie':
                people = [{'Name': '波多野結衣', 'Type': 'Actor', 'Role': ''}]
                return response({'Items': [{'Id': 'm1', 'People': people}], 'TotalRecordCount': 1})
            return response(status=404)

        with patch.object(media_people.requests, 'get', side_effect=fake_get), \
             patch.object(media_people.requests, 'post', side_effect=fake_post), \
             patch.object(media_people, 'UPLOAD_RETRY_DELAY', 0):
            media_people._run_scrape(self.server)
        stats = media_people._scrapes['srv1']['stats']
        self.assertEqual(len(calls), 3)  # 3 次重试
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['unmatched'], 0)
        log = '\n'.join(media_people.read_log('srv1'))
        self.assertIn('失败：波多野結衣', log)

    # ------------------------------------------------------------------ 日志与时间格式

    def test_log_lines_and_summary_use_local_datetime_format(self):
        stats, log = self.run_scrape([{'Id': 'p1', 'Name': '波多野結衣'}])
        # 每行形如 [2026-01-02 03:04:05]，不允许 ISO 的 T / 微秒 / 时区。
        pattern = re.compile(r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ')
        for line in media_people.read_log('srv1'):
            self.assertRegex(line, pattern)
        self.assertIn('完成：范围 1，', log)  # 尾部统计摘要（范围内人数）
        state = media_people.scrape_state(self.server)
        self.assertRegex(state['last_run_at'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')

    def test_summary_counts_all_categories(self):
        persons = [{'Id': 'p1', 'Name': '波多野結衣'}, {'Id': 'p2', 'Name': '三上悠亜'},
                   {'Id': 'p3', 'Name': '深田えいみ'}]
        stats, log = self.run_scrape(persons, has_image_ids={'p2'})
        self.assertEqual((stats['created'], stats['skipped'], stats['unmatched'], stats['failed']),
                         (1, 1, 1, 0))
        self.assertIn('新建 1', log)
        self.assertIn('跳过 1', log)
        self.assertIn('未匹配 1', log)
        self.assertIn('失败 0', log)

    def test_log_persists_and_read_log_returns_last_lines(self):
        self.run_scrape([{'Id': 'p1', 'Name': '波多野結衣'}])
        log_file = self.folder / 'media-people-scrape' / 'srv1.log'
        self.assertTrue(log_file.is_file())
        lines = media_people.read_log('srv1')
        self.assertTrue(lines)
        self.assertIn('开始刮削', lines[0])
        self.assertTrue(any('完成' in line for line in lines))
        self.assertLessEqual(len(lines), media_people.MAX_LOG_LINES)
        # 重启（状态清空）后日志仍可读。
        with patch.object(media_people, '_scrapes', {}):
            self.assertEqual(media_people.read_log('srv1'), lines)

    # ------------------------------------------------------------------ 并发与状态

    def test_start_scrape_rejects_concurrent_run(self):
        with patch.object(media_people, '_scrapes',
                          {'srv1': {'running': True}}):
            result = media_people.start_scrape(self.server)
        self.assertEqual(result, {'started': False, 'running': True})

    def test_start_scrape_spawns_thread_and_finishes(self):
        with patch.object(media_people.threading, 'Thread') as thread_cls:
            result = media_people.start_scrape(self.server)
        self.assertEqual(result, {'started': True})
        thread_cls.assert_called_once()
        thread_cls.return_value.start.assert_called_once()
        self.assertTrue(media_people.is_running('srv1'))
        # 后台线程结束后状态翻转。
        media_people._scrapes['srv1']['running'] = False
        self.assertFalse(media_people.is_running('srv1'))

    def test_scrape_state_shape(self):
        self.server['people_scrape'] = {'enabled': True}
        state = media_people.scrape_state(self.server)
        self.assertTrue(state['enabled'])
        self.assertFalse(state['running'])
        self.assertEqual(state['stats'],
                         {'created': 0, 'updated': 0, 'skipped': 0,
                          'unmatched': 0, 'failed': 0})
        self.assertEqual(state['unmatched'], [])
        self.assertEqual(state['log'], [])


class MediaPeopleRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.object(media_people, 'DATA_DIR', self.folder))
        self.enterContext(patch.object(media_people, '_scrapes', {}))
        storage.save_media_servers([{'id': 'srv1', 'name': 'Cinema', 'type': 'jellyfin',
                                     'url': 'http://media.test:8096', 'api_key': 'k',
                                     'libraries': ['lib1']}])

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        self.enterContext(patch.dict(server.app.dependency_overrides,
                                     {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def test_toggle_saves_to_server_record(self):
        client = self.client()
        result = client.put('/api/media-servers/srv1/people-scrape', json={'enabled': True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['enabled'])
        stored = storage.list_media_servers()[0]
        self.assertEqual(stored['people_scrape'], {'enabled': True})
        # 关掉再开，确保往返。
        client.put('/api/media-servers/srv1/people-scrape', json={'enabled': False})
        self.assertFalse(storage.list_media_servers()[0]['people_scrape']['enabled'])

    def test_run_starts_scrape_and_concurrent_run_returns_409(self):
        client = self.client()
        with patch.object(media_people, 'start_scrape',
                          side_effect=[{'started': True}, {'started': False, 'running': True}]):
            first = client.post('/api/media-servers/srv1/people-scrape/run')
            second = client.post('/api/media-servers/srv1/people-scrape/run')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), {'started': True})
        self.assertEqual(second.status_code, 409)
        self.assertIn('进行中', second.json()['detail'])

    def test_state_endpoint_reports_toggle_log_and_unmatched(self):
        client = self.client()
        client.put('/api/media-servers/srv1/people-scrape', json={'enabled': True})
        with patch.object(media_people, 'scrape_state',
                          return_value={'enabled': True, 'running': False,
                                        'last_run_at': '2026-01-02 03:04:05',
                                        'stats': {'created': 0, 'updated': 0, 'skipped': 0,
                                                  'unmatched': 0, 'failed': 0},
                                        'unmatched': ['某演员'],
                                        'log': ['[2026-01-02 03:04:05] 开始刮削']}):
            result = client.get('/api/media-servers/srv1/people-scrape')
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertTrue(body['enabled'])
        self.assertEqual(body['unmatched'], ['某演员'])
        self.assertEqual(len(body['log']), 1)

    def test_unknown_server_returns_404(self):
        client = self.client()
        self.assertEqual(client.get('/api/media-servers/nope/people-scrape').status_code, 404)
        self.assertEqual(client.put('/api/media-servers/nope/people-scrape',
                                    json={'enabled': True}).status_code, 404)
        self.assertEqual(client.post('/api/media-servers/nope/people-scrape/run').status_code, 404)


if __name__ == '__main__':
    unittest.main()


class PeopleScrapeStateTests(unittest.TestCase):
    """状态持久化与旧日志时间格式。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.enterContext(patch.object(media_people, 'DATA_DIR', self.folder))
        self.enterContext(patch.object(media_people, '_scrapes', {}))
        self.server = {'id': 'srv-state', 'name': 'Cinema', 'type': 'jellyfin',
                       'url': 'http://media.test:8096', 'api_key': 'k', 'libraries': [],
                       'people_scrape': {'enabled': True}}

    def test_state_survives_process_restart(self):
        media_people._save_state('srv-state', {
            'started_at': '2026-10-24 12:00:00', 'finished_at': '2026-10-24 12:00:13',
            'stats': {'created': 3, 'updated': 0, 'skipped': 95, 'unmatched': 12, 'failed': 1},
            'unmatched': ['某演员'],
        })
        # 模拟重启：内存清空后再读
        media_people._scrapes.clear()
        state = media_people.scrape_state(self.server)
        self.assertEqual(state['last_run_at'], '2026-10-24 12:00:13')
        self.assertEqual(state['stats']['unmatched'], 12)
        self.assertEqual(state['unmatched'], ['某演员'])
        self.assertFalse(state['running'])

    def test_legacy_iso_log_lines_are_reformatted(self):
        folder = media_people._server_scrape_dir('srv-state')
        folder.mkdir(parents=True, exist_ok=True)
        media_people._log_file('srv-state').write_text(
            '[2026-10-24T12:59:21.957140+08:00] 未匹配：高榕\n'
            '[2026-10-24 13:00:00] 完成：范围 10\n', encoding='utf-8')
        lines = media_people.read_log('srv-state')
        self.assertEqual(lines[0], '[2026-10-24 12:59:21] 未匹配：高榕')
        self.assertEqual(lines[1], '[2026-10-24 13:00:00] 完成：范围 10')
