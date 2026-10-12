import unittest
from unittest.mock import Mock, patch

import requests

from javsp_web import media


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.server = {'id': 'local-config-id', 'name': 'Cinema', 'type': 'jellyfin',
                       'url': 'http://media.test:8096', 'external_url': 'https://play.test/jellyfin',
                       'api_key': 'test-secret', 'libraries': ['movies']}

    def response(self, data, status=200):
        response = Mock(status_code=status)
        response.json.return_value = data
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError('secret in upstream URL', response=response)
        return response

    def test_jellyfin_uses_standard_auth_and_no_query_key(self):
        with patch.object(media.requests, 'get', return_value=self.response([{'ItemId': 'movies', 'Name': 'Movies', 'Locations': ['/media/movies']}])) as get:
            libraries = media.list_media_libraries(self.server)
        headers = get.call_args.kwargs['headers']
        self.assertIn('Token="test-secret"', headers['Authorization'])
        self.assertEqual(headers['X-Emby-Token'], 'test-secret')
        self.assertNotIn('api_key', get.call_args.kwargs['params'])
        self.assertEqual(libraries[0]['locations'], ['/media/movies'])

    def test_jellyfin_media_folders_fallback(self):
        with patch.object(media.requests, 'get', side_effect=[self.response({}, 403), self.response({'Items': [{'Id': 'movies', 'Name': 'Movies', 'Path': '/media/movies'}]})]) as get:
            libraries = media.list_media_libraries(self.server)
        self.assertTrue(get.call_args.args[0].endswith('/Library/MediaFolders'))
        self.assertEqual(libraries[0]['id'], 'movies')

    def test_playback_uses_bound_library_external_url_and_real_server_id(self):
        task = {'progress': {'output': {'save_dir': 'F:/organized/ABC-123'}, 'metadata': {'dvdid': 'ABC-123'}}}
        libraries = [{'id': 'movies', 'name': 'Movies', 'locations': ['/media/movies']}]
        mappings = [{'source_path': '/media/movies', 'target_path': 'F:/organized'}]
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_path_mappings', return_value=mappings), \
             patch.object(media, 'list_media_libraries', return_value=libraries), \
             patch.object(media.requests, 'get', side_effect=[self.response({'Items': [{'Id': 'movie-123', 'Path': '/media/movies/ABC-123/video.mkv'}]}), self.response({'Id': 'real-server-id'})]) as get:
            links = media.playback_links(task)
        self.assertEqual(links[0]['url'], 'https://play.test/jellyfin/web/#/details?id=movie-123&serverId=real-server-id')
        self.assertEqual(get.call_args_list[0].kwargs['params']['ParentId'], 'movies')
        self.assertNotIn('test-secret', links[0]['url'])

    def test_playback_does_not_use_unbound_libraries_or_partial_path_prefix(self):
        for folder, selected in [('/media/movies-other/ABC-123', ['movies']), ('/media/movies/ABC-123', ['other'])]:
            with patch.object(media, 'list_media_servers', return_value=[self.server | {'libraries': selected}]), \
                 patch.object(media, 'list_path_mappings', return_value=[]), \
                 patch.object(media, 'list_media_libraries', return_value=[{'id': 'movies', 'name': 'Movies', 'locations': ['/media/movies']}]), \
                 patch.object(media.requests, 'get') as get:
                self.assertEqual(media.playback_links({'input_directory': folder}), [])
                get.assert_not_called()

    def test_playback_accepts_external_web_page_urls(self):
        for kind, route in [('jellyfin', '/web/#/details?'), ('emby', '/web/index.html#!/item?')]:
            for suffix in ('', '/web/', '/web/index.html#!/home'):
                with self.subTest(kind=kind, suffix=suffix), \
                     patch.object(media, 'list_media_servers', return_value=[self.server | {'type': kind, 'external_url': 'https://play.test/proxy' + suffix}]), \
                     patch.object(media, 'list_path_mappings', return_value=[]), \
                     patch.object(media, 'list_media_libraries', return_value=[{'id': 'movies', 'name': 'Movies', 'locations': ['/movies']}]), \
                     patch.object(media.requests, 'get', side_effect=[self.response({'Items': [{'Id': '1', 'Path': '/movies/ABC-123/video.mkv'}]}), self.response({'Id': 'server'})]):
                    links = media.playback_links({'input_directory': '/movies/ABC-123'})
                self.assertEqual(links[0]['url'], 'https://play.test/proxy' + route + 'id=1&serverId=server')

    def test_overview_libraries_map_paths_and_cache_lookups(self):
        media._LIBRARY_CACHE.clear()
        self.addCleanup(media._LIBRARY_CACHE.clear)
        libraries = [{'id': 'movies', 'name': 'Movies', 'locations': ['/media/movies']}, {'id': 'tv', 'name': 'TV', 'locations': ['/media/tv']}]
        mappings = [{'source_path': '/media', 'target_path': 'F:\\organized'}]
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_path_mappings', return_value=mappings), \
                patch.object(media, 'list_media_libraries', return_value=libraries) as lookup:
            first = media.overview_libraries()
            second = media.overview_libraries()
        lookup.assert_called_once()
        self.assertEqual(first, second)
        self.assertEqual(first, [{'key': 'local-config-id:movies', 'name': 'Movies', 'server': 'Cinema', 'roots': ['/media/movies', 'F:/organized/movies']}])
        media._LIBRARY_CACHE.clear()
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_path_mappings', return_value=[]), \
                patch.object(media, 'list_media_libraries', side_effect=requests.ConnectionError('down')):
            self.assertEqual(media.overview_libraries(), [])

    def test_connection_errors_do_not_leak_credentials(self):
        error = requests.HTTPError('secret URL', response=Mock(status_code=401))
        self.assertIn('401', media.connection_error(error))
        self.assertNotIn('secret', media.connection_error(error))
        self.assertNotIn('secret', media.connection_error(requests.ConnectionError('secret URL')))


if __name__ == '__main__':
    unittest.main()
