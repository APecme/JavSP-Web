import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import artwork, asset_version, storage, tasks


class AssetVersionFunctionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.assets = self.folder / 'assets'
        self.assets.mkdir()
        (self.assets / 'app.js').write_text('console.log("one");')
        (self.assets / 'theme.css').write_text('body{}')

    def version(self):
        return asset_version.current_asset_version(self.assets)

    def count_reads(self):
        original = asset_version._read_bytes
        names = []

        def counting(path):
            names.append(Path(path).name)
            return original(path)

        return patch.object(asset_version, '_read_bytes', side_effect=counting), names

    def test_stable_version_and_unchanged_requests_do_not_reread_bytes(self):
        first = self.version()
        counter, names = self.count_reads()
        with counter:
            second = self.version()
        self.assertEqual(first, second)
        self.assertEqual(names, [])

    def test_inplace_same_length_edit_with_preserved_mtime_changes_version(self):
        first = self.version()
        path = self.assets / 'app.js'
        old = path.read_bytes()
        replacement = old.replace(b'o', b'0')
        self.assertEqual(len(replacement), len(old))
        stat = path.stat()
        with open(path, 'r+b') as handle:
            handle.write(replacement)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        second = self.version()
        self.assertNotEqual(first, second)
        counter, names = self.count_reads()
        with counter:
            self.assertEqual(self.version(), second)
        self.assertEqual(names, [])

    def test_add_and_delete_change_version_and_deletion_restores_previous(self):
        first = self.version()
        (self.assets / 'new.js').write_text('added')
        second = self.version()
        self.assertNotEqual(first, second)
        (self.assets / 'new.js').unlink()
        third = self.version()
        self.assertNotEqual(second, third)
        self.assertEqual(third, first)

    def test_single_file_change_only_rereads_that_file(self):
        self.version()
        (self.assets / 'theme.css').write_text('body{color:red}')
        counter, names = self.count_reads()
        with counter:
            self.version()
        self.assertEqual(names, ['theme.css'])

    def test_missing_assets_directory_yields_a_stable_version(self):
        for path in self.assets.iterdir():
            path.unlink()
        self.assets.rmdir()
        first = self.version()
        second = self.version()
        self.assertIsInstance(first, str)
        self.assertTrue(first)
        self.assertEqual(first, second)

    def test_concurrent_readers_agree_on_one_version(self):
        observed = []
        errors = []

        def worker():
            try:
                for _ in range(25):
                    observed.append(self.version())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(set(observed), {self.version()})


class ServerAssetVersionTests(unittest.TestCase):
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
        self.enterContext(patch.object(artwork, 'DATA_DIR', self.folder))
        self.web = self.folder / 'web'
        (self.web / 'assets').mkdir(parents=True)
        (self.web / 'index.html').write_text('<script src="/assets/app.js?v=__ASSET_VERSION__"></script>')
        (self.web / 'login.html').write_text('<link href="/assets/app.css?v=__ASSET_VERSION__">')
        (self.web / 'assets' / 'app.js').write_text('one')

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def test_index_and_login_share_version_and_refresh_after_asset_change(self):
        client = self.client()
        with patch.object(self.server, 'WEB_DIR', self.web):
            index = client.get('/')
            login = client.get('/login')
            first = self.server.asset_version()
            self.assertIn(f'v={first}', index.text)
            self.assertIn(f'v={first}', login.text)
            self.assertEqual(getattr(self.server, 'ASSET_VERSION'), first)
            self.assertNotIn('__ASSET_VERSION__', index.text)
            self.assertNotIn('__ASSET_VERSION__', login.text)
            (self.web / 'assets' / 'app.js').write_text('two')
            refreshed = client.get('/')
            second = self.server.asset_version()
            self.assertNotEqual(second, first)
            self.assertIn(f'v={second}', refreshed.text)
            self.assertNotIn(f'v={first}', refreshed.text)
            self.assertIn('immutable', client.get('/assets/app.js?v=' + second).headers['cache-control'])
            # 旧版本号 URL 也带 v，按版本化语义同样长缓存；refreshed 的
            # index 已不再引用它，浏览器不会再请求旧 URL。
            stale = client.get('/assets/app.js?v=' + first)
            self.assertEqual(stale.headers['cache-control'],
                             'public, max-age=31536000, immutable')
            self.assertEqual(stale.status_code, 200)

    def test_unversioned_and_unauthenticated_asset_requests_are_revalidated(self):
        client = self.client()
        with patch.object(self.server, 'WEB_DIR', self.web):
            unversioned = client.get('/assets/app.js')
            self.assertEqual(unversioned.status_code, 200)
            self.assertEqual(unversioned.headers['cache-control'], 'public, no-cache')

    def test_missing_asset_with_current_version_is_not_long_cached(self):
        client = self.client()
        with patch.object(self.server, 'WEB_DIR', self.web):
            current = self.server.asset_version()
            missing = client.get('/assets/does-not-exist.js?v=' + current)
            self.assertEqual(missing.status_code, 404)
            self.assertNotIn('immutable', missing.headers['cache-control'])
            self.assertEqual(missing.headers['cache-control'], 'public, no-cache')

    def test_conditional_304_with_current_version_stays_immutable(self):
        client = self.client()
        with patch.object(self.server, 'WEB_DIR', self.web):
            current = self.server.asset_version()
            first = client.get('/assets/app.js?v=' + current)
            second = client.get('/assets/app.js?v=' + current, headers={'If-None-Match': first.headers.get('etag', '')})
            if second.status_code == 304:
                self.assertIn('immutable', second.headers['cache-control'])


if __name__ == '__main__':
    unittest.main()
