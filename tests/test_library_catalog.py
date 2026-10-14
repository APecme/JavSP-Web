import copy
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from javsp_web import library, media, storage, tasks
from scripts.sync_gfriends import catalog_from_tree
from tests import test_media
from tests import test_task_store


class CatalogTests(unittest.TestCase):
    response = test_media.MediaTests.response
    def setUp(self):
        test_media.MediaTests.setUp(self)
        media.clear_catalog_cache()
        self.addCleanup(media.clear_catalog_cache)

    def test_movie_pagination_and_selection_include_unscraped_films(self):
        libraries = [{'id': 'movies', 'name': 'Movies', 'locations': []}, {'id': 'unbound', 'name': 'Other', 'locations': []}]
        def upstream(url, **kwargs):
            offset = kwargs['params']['StartIndex']
            batch = [{'Id': str(i), 'Name': f'ABC-{i:04}', 'Path': f'/media/ABC-{i:04}/video.mkv',
                      'ImageTags': {'Primary': 'tag'}, 'People': [{'Type': 'Actor', 'Name': 'Alice'}]} for i in range(offset, min(offset + 1000, 1003))]
            return self.response({'Items': batch, 'TotalRecordCount': 1003})
        with patch.object(media, 'list_media_servers', return_value=[self.server]), \
             patch.object(media, 'list_media_libraries', return_value=libraries), patch.object(media.requests, 'get', side_effect=upstream) as get:
            movies, errors = media.catalog_movies()
            self.assertEqual(len(movies), 1003)
            self.assertEqual(errors, [])
            self.assertEqual(movies[0]['progress']['metadata']['actress'], ['Alice'])
            self.assertEqual(movies[0]['cover_count'], 1)
            self.assertEqual(media.catalog_movies()[0], movies)
            self.assertEqual(get.call_count, 2)
            self.assertTrue(all(call.kwargs['params']['ParentId'] == 'movies' for call in get.call_args_list))

    def test_identifier_fallback_with_different_container_paths(self):
        libraries = [{'id': 'movies', 'name': 'Movies', 'locations': ['/server/movies']}]
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_path_mappings', return_value=[]), \
             patch.object(media, 'list_media_libraries', return_value=libraries), \
             patch.object(media.requests, 'get', side_effect=[self.response({'Items': [{'Id': '42', 'Path': '/server/movies/ABC123.mkv'}]}), self.response({'Id': 'real'})]):
            result = media.playback_links({'input_directory': '/container/output/ABC-123', 'progress': {'metadata': {'dvdid': 'ABC-123'}}})
            self.assertIn('id=42', result[0]['url'])

    def test_media_reference_plays_without_filename_or_path_matching(self):
        libraries = [{'id': 'movies', 'name': 'Movies', 'locations': []}]
        task = {'media_reference': {'server_id': self.server['id'], 'library_id': 'movies', 'item_id': '42'}, 'input_directory': '/arbitrary.mkv'}
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_path_mappings', return_value=[]), \
             patch.object(media, 'list_media_libraries', return_value=libraries), patch.object(media.requests, 'get', return_value=self.response({'Id': 'real'})) as get:
            self.assertIn('id=42', media.playback_links(task)[0]['url'])
            self.assertEqual(get.call_count, 1)

    def test_failed_catalog_read_exposes_error_instead_of_silent_empty(self):
        import requests
        with patch.object(media, 'list_media_servers', return_value=[self.server]), patch.object(media, 'list_media_libraries', side_effect=requests.ConnectionError()):
            movies, errors = media.catalog_movies()
            self.assertEqual(movies, [])
            self.assertIn('Cinema', errors[0])


class LibraryIntegrationTests(unittest.TestCase):
    setUp = test_task_store.TaskStoreTests.setUp
    item = test_task_store.TaskStoreTests.item
    def test_catalog_counts_and_prefix_filters_with_no_scrape_history(self):
        libraries = [{'key': 's:l', 'name': 'Movies', 'roots': []}]
        film = {'id': 'media-42', 'title': 'A film', 'cover_count': 0, 'library_keys': ['s:l'],
                'progress': {'metadata': {'dvdid': 'SSIS-123', 'producer': 'Not the prefix', 'actress': ['Alice']}}}
        with patch.object(media, 'catalog_movies', return_value=([film], [])):
            groups = library.overview_groups('library', 0, 12, '', libraries)
            self.assertEqual(groups['groups'][0]['count'], 1)
            groups = library.overview_groups('producer', 0, 12, '', libraries)
            self.assertEqual(groups['groups'][0]['name'], 'SSIS')
            self.assertEqual(library.overview_page(24, 0, libraries, group_by='producer', group='SSIS')['total'], 1)
            self.assertEqual(library.overview_page(24, 0, libraries, group_by='library', group='s:l')['total'], 1)

    def test_artwork_add_replace_remove_updates_counts_and_keeps_backups(self):
        self.folder.joinpath('movie').mkdir()
        storage.save_tasks([self.item(image_output={'save_dir': str(self.folder / 'movie')})])
        buffer = io.BytesIO()
        Image.new('RGB', (30, 40), 'red').save(buffer, 'PNG')
        content = buffer.getvalue()
        for kind, getter, count in [('cover', tasks.get_cover_path, 'cover_count'), ('fanart', tasks.get_fanart_path, 'fanart_count')]:
            tasks.edit_task_artwork('one', kind, -1, content)
            first = getter('one', 0)
            self.assertTrue(first.is_file())
            tasks.edit_task_artwork('one', kind, 0, content)
            self.assertEqual(tasks.get_task('one')[count], 1)
            self.assertEqual(tasks.list_task_summaries(24)['items'][0][count], 1)
            tasks.edit_task_artwork('one', kind, 0, delete=True)
            self.assertIsNone(getter('one', 0))
            self.assertEqual(tasks.get_task('one')[count], 0)
            self.assertTrue(list(first.parent.joinpath('.javsp-artwork-backup').glob('*')))
        self.assertEqual(library.overview_page(24, 0, [])['total'], 1)


class GfriendsTests(unittest.TestCase):
    def test_aliases_use_the_highest_quality_provider_and_safe_urls(self):
        result = catalog_from_tree({'Content': {'A': {'Alice.jpg': 'Alice.jpg?t=1'}, 'Best Quality': {'Alice.jpg': 'AI-Fix-Alice.jpg?t=2', '爱丽丝.jpg': 'AI-Fix-Alice.jpg?t=2', '../bad.jpg': '../bad.jpg'}}})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['url'], result[1]['url'])
        self.assertIn('/Best%20Quality/AI-Fix-Alice.jpg?t=2', result[0]['url'])
        self.assertEqual(len(result[0]['id']), 16)


if __name__ == '__main__':
    unittest.main()
