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


class OverviewDeduplicationTests(unittest.TestCase):
    def film(self, id, folder, source=None, identifier='ABC-123', created='2026-10-19'):
        film = {'id': id, 'created_at': created, 'status': 'succeeded', 'cover_count': 1,
                'progress': {'metadata': {'dvdid': identifier}, 'output': {'save_dir': folder}}}
        if source:
            film.update(input_directory=source, preset_id='p', task_ids=[id])
        else:
            film.update(task_type='media', library_keys=['server:movies'],
                        media_reference={'server_id': 'server', 'library_id': 'movies', 'item_id': id})
        return film

    def collect(self, local, remote, mappings=None):
        self.local_before = copy.deepcopy(local)
        self.remote_before = copy.deepcopy(remote)
        with patch.object(library.task_store, 'page', return_value={'items': local, 'metrics': {'total': 7}}), \
             patch.object(library.media, 'catalog_movies', return_value=(remote, [])), \
             patch.object(library.media, 'list_path_mappings', return_value=mappings or []):
            result = library._collection([])
        self.assertEqual(local, self.local_before)
        self.assertEqual(remote, self.remote_before)
        return result[0]

    def test_mount_prefix_only_difference_merges_history_with_media(self):
        local = self.film('scrape', '/video/movies/category/ABC-123', '/download/ABC-123.strm')
        remote = self.film('media', '/media/movies/category/ABC-123')
        items = self.collect([local], [remote])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], 'scrape')
        self.assertEqual(items[0]['media_reference']['item_id'], 'media')
        self.assertEqual(items[0]['library_keys'], ['server:movies'])

    def test_same_source_title_and_fc2_alias_changes_keep_one_card_and_all_history(self):
        new = self.film('new', '/video/movies/category/FC2-1234567-new title', '/download/same.strm', 'FC2-1234567')
        old = self.film('old', '/video/movies/category/FC2-PPV-1234567-old title', '/download/same.strm', 'FC2-PPV-1234567', '2026-10-18')
        old['task_ids'] = ['old', 'older']
        movies = [self.film('new-media', '/media/movies/category/FC2-1234567-new title', identifier='FC2-1234567'),
                  self.film('old-media', '/media/movies/category/FC2-PPV-1234567-old title', identifier='FC2-1234567')]
        items = self.collect([new, old], movies)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], 'new')
        self.assertEqual(set(items[0]['task_ids']), {'new', 'old', 'older'})
        self.assertEqual(len(items[0]['media_references']), 2)

    def test_different_sources_categories_presets_and_identifiers_stay_separate(self):
        a = self.film('a', '/video/movies/one/ABC-123', '/download/a.strm')
        b = self.film('b', '/video/movies/two/ABC-123', '/download/b.strm')
        c = self.film('c', '/media/movies/three/ABC-123')
        self.assertEqual(len(self.collect([a,b], [c])), 3)
        b['input_directory'] = a['input_directory']; b['preset_id'] = 'other'
        self.assertEqual(len(self.collect([a,b], [])), 2)
        remote = self.film('different', '/media/movies/one/ABC-123', identifier='OTHER-123')
        self.assertEqual(len(self.collect([a], [remote])), 2)

    def test_ambiguous_relative_path_and_multiple_servers_do_not_collapse_editions(self):
        a = self.film('a', '/disk1/movies/category/ABC-123', '/download/a.strm')
        b = self.film('b', '/disk2/movies/category/ABC-123', '/download/b.strm')
        remote = self.film('media', '/media/movies/category/ABC-123')
        self.assertEqual(len(self.collect([a,b], [remote])), 3)
        other = copy.deepcopy(remote); other['id'] = 'other'; other['media_reference']['server_id'] = 'other'
        self.assertEqual(len(self.collect([a], [remote,other])), 2)

    def test_overlapping_explicit_mappings_do_not_count_one_match_twice(self):
        local = self.film('a', '/video/movies/category/ABC-123', '/download/a.strm')
        remote = self.film('media', '/video/movies/category/ABC-123')
        mappings = [{'source_path':'/video', 'target_path':'/video'}]
        self.assertEqual(len(self.collect([local], [remote], mappings)), 1)

    def test_different_media_items_in_one_folder_are_kept(self):
        local = self.film('local', '/video/movies/category/ABC-123', '/download/ABC-123.strm')
        first = self.film('part-one', '/media/movies/category/ABC-123')
        second = self.film('part-two', '/media/movies/category/ABC-123')
        self.assertEqual(len(self.collect([local], [first, second])), 2)

    def test_same_source_with_different_output_parent_remains_separate(self):
        a = self.film('a', '/video/movies/one/ABC-123', '/download/ABC-123.strm')
        b = self.film('b', '/video/movies/two/ABC-123', '/download/ABC-123.strm')
        self.assertEqual(len(self.collect([a,b], [])), 2)

    def test_merge_happens_before_paging_and_updates_library_counts(self):
        local = self.film('scrape', '/video/movies/category/ABC-123', '/download/ABC-123.strm')
        remote = self.film('media', '/media/movies/category/ABC-123')
        with patch.object(library.task_store, 'page', return_value={'items':[local], 'metrics':{}}), \
             patch.object(library.media, 'catalog_movies', return_value=([remote], [])), \
             patch.object(library.media, 'list_path_mappings', return_value=[]):
            page = library.overview_page(1, 0, [], group_by='library', group='server:movies')
            groups = library.overview_groups('all', 0, 12, '', [])
        self.assertEqual(page['total'], 1)
        self.assertEqual(len(page['items']), 1)
        self.assertEqual(groups['all']['count'], 1)

    def test_duplicate_remote_item_from_overlapping_libraries_merges_library_keys(self):
        a = self.film('a', '/media/movies/category/ABC-123')
        b = copy.deepcopy(a); b['id'] = 'b'; b['library_keys'] = ['server:other']; b['media_reference']['library_id'] = 'other'
        items = self.collect([], [a,b])
        self.assertEqual(len(items), 1)
        self.assertEqual(set(items[0]['library_keys']), {'server:movies','server:other'})


class GfriendsTests(unittest.TestCase):
    def test_actress_scope_pages_full_directory_with_counts_outside_current_page(self):
        films = [{'id':'f1','progress':{'metadata':{'actress':['Zelda']}}}]
        catalog = {'a':{'id':'a','name':'Alice','source':'gfriends'},
                   'z':{'id':'z','name':'Zelda','source':'gfriends'}}
        with patch.object(library, '_collection', return_value=(films, {}, [])), \
             patch('javsp_web.library.avatar_directory', return_value=catalog, create=True):
            first = library.overview_groups('actress', 0, 1, '', [], actress_scope='all')
            second = library.overview_groups('actress', 1, 1, '', [], actress_scope='all')
            existing = library.overview_groups('actress', 0, 12, '', [], actress_scope='existing')
        self.assertEqual(first['total'], 2)
        self.assertEqual(len(first['groups']), 1)
        self.assertEqual(first['groups'][0]['name'], 'Zelda')
        self.assertEqual(first['groups'][0]['count'], 1)
        self.assertEqual(first['groups'][0]['avatar_id'], 'z')
        self.assertEqual(second['groups'][0]['name'], 'Alice')
        self.assertEqual(second['groups'][0]['count'], 0)
        self.assertEqual([g['name'] for g in existing['groups']], ['Zelda'])

    def test_actress_directory_works_without_films_and_searches_before_paging(self):
        catalog = {name:{'id':name,'name':name,'source':'gfriends'} for name in ['Alice','Bea']}
        with patch.object(library, '_collection', return_value=([], {}, [])), \
             patch('javsp_web.library.avatar_directory', return_value=catalog, create=True):
            result = library.overview_groups('actress', 0, 1, 'bea', [], actress_scope='all')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['groups'][0]['key'], 'Bea')
        self.assertEqual(result['groups'][0]['count'], 0)

    def test_aliases_use_the_highest_quality_provider_and_safe_urls(self):
        result = catalog_from_tree({'Content': {'A': {'Alice.jpg': 'Alice.jpg?t=1'}, 'Best Quality': {'Alice.jpg': 'AI-Fix-Alice.jpg?t=2', '爱丽丝.jpg': 'AI-Fix-Alice.jpg?t=2', '../bad.jpg': '../bad.jpg'}}})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['url'], result[1]['url'])
        self.assertIn('/Best%20Quality/AI-Fix-Alice.jpg?t=2', result[0]['url'])
        self.assertEqual(len(result[0]['id']), 16)


if __name__ == '__main__':
    unittest.main()
