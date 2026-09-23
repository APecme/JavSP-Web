import unittest
from unittest.mock import patch

from javsp_web import download_cache as cache


class DownloadCacheTests(unittest.TestCase):
    def test_nonblocking_single_flight_and_configuration_invalidation(self):
        settings = [{'id': 'one', 'name': 'test', 'url': 'https://example.test'}]
        with patch.object(cache, '_entries', {}), patch.object(cache, '_pool') as pool, \
             patch.object(cache, 'list_downloads', return_value=[{'hash': 'abc'}]) as fetch:
            first = cache.snapshots(settings)
            self.assertTrue(first[0]['refreshing'])
            self.assertEqual(first[0]['items'], [])
            cache.snapshots(settings)
            fetch.assert_not_called()
            self.assertEqual(pool.submit.call_count, 1)
            fn, *args = pool.submit.call_args.args
            fn(*args)
            result = cache.snapshots(settings)
            self.assertEqual(result[0]['items'], [{'hash': 'abc'}])
            self.assertIsNotNone(result[0]['updated_at'])
            result[0]['items'].clear()
            self.assertEqual(len(cache.snapshots(settings)[0]['items']), 1)
            cache.snapshots([settings[0] | {'url': 'https://changed.test'}])
            self.assertEqual(pool.submit.call_count, 2)
            self.assertEqual(len(cache._entries), 1)

    def test_failure_releases_refresh_and_can_retry(self):
        with patch.object(cache, '_entries', {}), patch.object(cache, '_pool') as pool, \
             patch.object(cache, 'list_downloads', side_effect=RuntimeError('offline')):
            settings = [{'id': 'one', 'name': 'test'}]
            cache.snapshots(settings)
            fn, *args = pool.submit.call_args.args
            fn(*args)
            result = cache.snapshots(settings)[0]
            self.assertFalse(result['refreshing'])
            self.assertEqual(result['error'], 'offline')
            cache._entries[cache._key(settings[0])]['checked'] -= 10
            cache.snapshots(settings)
            self.assertEqual(pool.submit.call_count, 2)
