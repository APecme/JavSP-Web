import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from javsp_web import cookiecloud, storage


class CookieCloudSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, root / value.relative_to(old)))
        self.enterContext(patch.object(cookiecloud, '_snapshot', {}))
        self.clock = self.enterContext(patch.object(cookiecloud.time, 'time', return_value=10000))
        self.settings = dict(enabled=True, server_url='https://cloud.test', uuid='test', password='private-password',
                             crypto_type='auto', sync_interval_minutes=5)
        storage.save_cookiecloud_settings(self.settings)
        self.fetch = self.enterContext(patch.object(cookiecloud, 'fetch_cookiecloud', return_value={'example.com': {'session': 'private-cookie'}}))

    def test_interval_round_trip_validation_and_legacy_default(self):
        self.assertEqual(storage.get_cookiecloud_settings()['sync_interval_minutes'], 5)
        storage._write_json(storage.COOKIECLOUD_FILE, {'sync_interval_minutes': 'invalid'})
        self.assertEqual(storage.get_cookiecloud_settings()['sync_interval_minutes'], 30)
        storage._write_json(storage.COOKIECLOUD_FILE, {})
        self.assertEqual(storage.get_cookiecloud_settings()['sync_interval_minutes'], 30)

    def test_shared_snapshot_expires_and_manual_sync_bypasses_interval(self):
        first = cookiecloud.get_synced_cookies()
        first['example.com']['session'] = 'do-not-mutate-shared-data'
        self.assertEqual(cookiecloud.get_synced_cookies()['example.com']['session'], 'private-cookie')
        self.fetch.assert_called_once()
        self.clock.return_value = 10299
        cookiecloud.scheduler_tick()
        self.fetch.assert_called_once()
        self.clock.return_value = 10300
        cookiecloud.scheduler_tick()
        self.assertEqual(self.fetch.call_count, 2)
        cookiecloud.get_synced_cookies(force=True)
        self.assertEqual(self.fetch.call_count, 3)
        status = cookiecloud.sync_status()
        self.assertTrue(status['last_sync_at'])
        self.assertTrue(status['next_sync_at'])
        self.assertEqual(status['domains'], 1)
        self.assertNotIn('private', str(status))

    def test_concurrent_consumers_only_sync_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: cookiecloud.get_synced_cookies(), range(5)))
        self.fetch.assert_called_once()
        self.assertTrue(all(item['example.com']['session'] == 'private-cookie' for item in results))

    def test_disable_and_configuration_change_invalidate_old_snapshot(self):
        cookiecloud.get_synced_cookies()
        storage.save_cookiecloud_settings(self.settings | {'enabled': False})
        self.assertEqual(cookiecloud.get_synced_cookies(), {})
        self.assertEqual(cookiecloud.sync_status()['last_sync_at'], '')
        storage.save_cookiecloud_settings(self.settings | {'uuid': 'new-account'})
        self.fetch.return_value = {'other.test': {'new': 'new-cookie'}}
        self.assertNotIn('example.com', cookiecloud.get_synced_cookies())
        self.assertEqual(self.fetch.call_count, 2)

    def test_failure_preserves_last_success_but_reports_error_and_retries(self):
        cookiecloud.get_synced_cookies()
        before = cookiecloud.sync_status()['last_sync_at']
        self.clock.return_value = 10300
        self.fetch.side_effect = cookiecloud.CookieCloudError('private-password and remote-body')
        cookiecloud.scheduler_tick()
        status = cookiecloud.sync_status()
        self.assertEqual(status['last_sync_at'], before)
        self.assertIn('同步失败', status['last_error'])
        self.assertNotIn('private', str(status))
        cookiecloud.scheduler_tick()
        self.assertEqual(self.fetch.call_count, 2)
        self.fetch.side_effect = None
        self.clock.return_value = 10360
        cookiecloud.scheduler_tick()
        self.assertEqual(self.fetch.call_count, 3)
        self.assertEqual(cookiecloud.sync_status()['last_error'], '')

    def test_changed_settings_during_network_request_cannot_install_old_credentials(self):
        def change(*args, **kwargs):
            storage.save_cookiecloud_settings(self.settings | {'uuid': 'changed'})
            return {'example.com': {'session': 'old-account'}}
        self.fetch.side_effect = change
        with self.assertRaisesRegex(cookiecloud.CookieCloudError, '配置已更改'):
            cookiecloud.get_synced_cookies()
        self.assertEqual(cookiecloud.sync_status()['domains'], 0)


if __name__ == '__main__':
    unittest.main()
