import copy
from collections import deque
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import storage, tasks, task_store, artwork


class TaskStoreTests(unittest.TestCase):
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

    def item(self, task_id='one', status='succeeded', **kw):
        return dict(id=task_id, created_at='2026-09-23T12:00:00+00:00', status=status,
                    input_directory=str(self.folder / (task_id + '.mp4')), file_name=task_id,
                    size_bytes=1024**3, log_tail=['JAVSP_PROGRESS ' + json.dumps({'stage': 'metadata', 'title': task_id, 'dvdid': 'ABC-123'})], **kw)

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def test_json_import_backup_and_deleted_history_does_not_reappear(self):
        record = self.item()
        content = json.dumps([record], ensure_ascii=False)
        storage.TASKS_FILE.write_text(content, encoding='utf-8')
        self.assertEqual(storage.load_tasks(), [record | {'source': 'manual'}])
        self.assertEqual((self.folder / 'tasks.pre-sqlite.json').read_text(encoding='utf-8'), content)
        self.assertTrue(storage.delete_task_record('one'))
        task_store._ready.discard(str(storage.TASKS_DB_FILE.resolve()))
        self.assertEqual(storage.load_tasks(), [])
        self.assertEqual(storage.TASKS_FILE.read_text(encoding='utf-8'), content)

    def test_invalid_json_does_not_mark_import_complete(self):
        storage.TASKS_FILE.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            storage.load_tasks()
        storage.TASKS_FILE.write_text(json.dumps([self.item()]), encoding='utf-8')
        self.assertEqual(len(storage.load_tasks()), 1)

    def test_duplicate_ids_abort_import(self):
        storage.TASKS_FILE.write_text(json.dumps([self.item(), self.item()]), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重复'):
            storage.load_tasks()

    def test_row_update_logs_separation_and_concurrent_writes(self):
        records = [self.item(str(i)) for i in range(20)]
        storage.save_tasks(records)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(storage.upsert_task, [record | {'error': record['id']} for record in records]))
        self.assertEqual(len(storage.load_tasks()), 20)
        for record in storage.load_tasks():
            self.assertEqual(record['error'], record['id'])
        with task_store.connection() as db:
            self.assertNotIn('log_tail', json.loads(db.execute('SELECT payload FROM tasks LIMIT 1').fetchone()[0]))
            self.assertEqual(db.execute('SELECT count(*) FROM task_logs').fetchone()[0], 20)
        storage.delete_task_record('1')
        with task_store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM task_logs').fetchone()[0], 19)

    def test_global_filters_before_pagination_and_queue_order(self):
        records = [self.item(str(i), source='manual') for i in range(120)]
        records[110]['metadata_override'] = {'title': 'Hidden unique title', 'actress': ['Alice']}
        records[111]['status'] = 'running'
        records[111]['created_at'] = '2020-01-01T00:00:00Z'
        storage.save_tasks(records)
        result = tasks.list_task_summaries(10, 0, view='manual')
        self.assertEqual(result['items'][0]['id'], '111')
        self.assertEqual(result['total'], 120)
        result = tasks.list_task_summaries(10, 0, view='manual', query='alice', field='actress')
        self.assertEqual([item['id'] for item in result['items']], ['110'])
        self.assertEqual(tasks.list_task_summaries(10, 0, size_min=1025)['total'], 0)
        self.assertEqual(tasks.list_task_summaries(10, 0, date_from='2026-01-01T00:00:00Z')['total'], 119)
        self.assertEqual(tasks.list_task_summaries(10, 9999)['offset'], 110)

    def test_overview_groups_before_paginating_and_global_metrics(self):
        records = [self.item(str(i), image_sources={'cover_urls': ['https://example.test/cover']}) for i in range(30)]
        for record in records[:3]:
            record['image_output'] = {'save_dir': '/shared', 'fanart_file': '/shared/fanart.jpg'}
        records[1]['status'] = 'failed'
        records.append(self.item('active', status='queued'))
        storage.save_tasks(records)
        result = tasks.list_task_summaries(10, 0, view='overview')
        self.assertEqual(result['total'], 28)
        self.assertEqual(result['metrics']['total'], 31)
        self.assertEqual(result['metrics']['running'], 1)
        pages = [tasks.list_task_summaries(10, offset, view='overview')['items'] for offset in (0, 10, 20)]
        combined = [item for page in pages for item in page]
        self.assertEqual(len(combined), 28)
        group = next(item for item in combined if len(item['task_ids']) == 3)
        self.assertEqual(set(group['task_ids']), {'0', '1', '2'})
        self.assertEqual(group['status'], 'succeeded')

    def test_metadata_update_and_detail_touch_one_record(self):
        storage.save_tasks([self.item('one'), self.item('two')])
        with patch.object(tasks, 'save_tasks', side_effect=AssertionError('full rewrite')), patch.object(tasks, 'load_tasks', wraps=storage.load_tasks) as load:
            tasks.update_task_metadata('one', {'title': 'Updated'}, False)
            self.assertEqual(tasks.get_task('one')['title'], 'Updated')
            load.assert_called_once_with({'one'})
        self.assertEqual(tasks.get_task('two')['title'], 'two')

    def test_cover_lookup_never_loads_history_or_logs_for_new_records(self):
        from PIL import Image
        path = self.folder / 'poster.jpg'
        Image.new('RGB', (800, 1200)).save(path)
        storage.upsert_task(self.item(image_output={'poster_file': str(path), 'fanart_file': str(path), 'save_dir': str(self.folder)}))
        with patch.object(tasks, 'load_tasks', side_effect=AssertionError('full read')), patch.object(tasks, '_task_progress', side_effect=AssertionError('log parse')):
            self.assertEqual(tasks.get_cover_path('one', 0), path)

    def test_update_api_exposes_cached_check_and_worker_status(self):
        self.enterContext(patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': 'v1.1.36'}))
        client = self.client()
        from javsp_web import updater
        storage.save_update_settings({'experience_program': False})
        updater.write_state('check', {'channel': 'stable', 'current': updater.current_version(), 'available': True, 'target': '1.1.37'})
        with patch.object(updater, 'capability', return_value={'supported': True}), patch.object(updater, 'job', return_value={'status': 'pulling', 'message': '正在拉取目标镜像'}):
            response = client.get('/api/update')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['target'], '1.1.37')
        self.assertEqual(response.json()['job']['status'], 'pulling')

    def test_joining_experience_program_applies_immediately_without_auto_update(self):
        self.enterContext(patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': 'v1.1.36'}))
        client = self.client()
        from javsp_web import updater
        storage.save_update_settings({'experience_program': False, 'auto_update': False})
        with patch.object(updater, 'apply', return_value={'status': 'scheduled', 'target': 'bata.20260924044117'}) as apply:
            response = client.put('/api/update/settings', json={'experience_program': True, 'auto_update': False})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['settings']['experience_program'])
        self.assertEqual(response.json()['activation']['status'], 'scheduled')
        apply.assert_called_once_with()

    def test_joining_experience_program_reports_install_error_and_keeps_setting(self):
        self.enterContext(patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': 'v1.1.36'}))
        client = self.client()
        from javsp_web import updater
        storage.save_update_settings({'experience_program': False})
        with patch.object(updater, 'apply', side_effect=updater.UpdateError('需要手动更新镜像')):
            response = client.put('/api/update/settings', json={'experience_program': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['activation_error'], '需要手动更新镜像')
        self.assertTrue(storage.get_update_settings()['experience_program'])

    def test_api_page_etag_thumbnail_and_version(self):
        client = self.client()
        from PIL import Image
        path = self.folder / 'poster.jpg'
        Image.new('RGB', (800, 1200), 'red').save(path)
        storage.upsert_task(self.item(image_output={'poster_file': str(path), 'fanart_file': str(path), 'save_dir': str(self.folder)}))
        response = client.get('/api/tasks?limit=10&view=manual')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(client.get('/api/tasks?limit=10&view=manual', headers={'If-None-Match': response.headers['etag']}).status_code, 304)
        cover = client.get('/api/tasks/one/cover/0?thumbnail=true')
        self.assertEqual(cover.status_code, 200)
        import io
        with Image.open(io.BytesIO(cover.content)) as image:
            self.assertLessEqual(image.width, 360)
            self.assertLessEqual(image.height, 540)
        self.assertEqual(client.get('/api/tasks/one/cover/0?thumbnail=true', headers={'If-None-Match': cover.headers['etag']}).status_code, 304)
        Image.new('RGB', (801, 1200), 'blue').save(path)
        fresh = client.get('/api/tasks/one/cover/0?thumbnail=true', headers={'If-None-Match': cover.headers['etag']})
        self.assertEqual(fresh.status_code, 200)
        self.assertNotEqual(fresh.headers['etag'], cover.headers['etag'])
        with patch.object(self.server, 'RELEASE_LABEL', 'vv1.1.36'):
            runtime = client.get('/api/runtime').json()
            self.assertEqual(runtime['version'], '1.1.36')
            self.assertEqual(runtime['app_version'], '1.1.36')
        asset = client.get('/assets/app.js?v=' + self.server.ASSET_VERSION)
        self.assertIn('immutable', asset.headers['cache-control'])
        self.assertNotIn('immutable', client.get('/assets/app.js?v=wrong').headers['cache-control'])
        self.assertIn(self.server.ASSET_VERSION, client.get('/login').text)

    def test_pending_dispatch_respects_batch_and_uses_fixed_workers(self):
        records = [self.item('a', status='queued', batch_id='batch1', task_concurrency=1),
                   self.item('b', status='queued', batch_id='batch1', task_concurrency=1),
                   self.item('c', status='queued', batch_id='batch2', task_concurrency=1)]
        with patch.object(tasks, '_pending_tasks', deque()), patch.object(tasks, '_worker_threads', []), \
             patch.object(tasks, '_worker_batches', {}), patch.object(tasks.threading, 'Thread') as thread:
            for record in records:
                tasks._enqueue_task(record)
            self.assertEqual(thread.call_count, tasks._GLOBAL_TASK_LIMIT)
            self.assertEqual(tasks._take_pending_task()[0]['id'], 'a')
            self.assertEqual(tasks._take_pending_task()[0]['id'], 'c')
            self.assertIsNone(tasks._take_pending_task())
            tasks._worker_batches['batch1'] = 0
            self.assertEqual(tasks._take_pending_task()[0]['id'], 'b')

    def test_worker_releases_reservation_when_persistence_fails(self):
        record = self.item(status='queued')
        class StopWorker(BaseException):
            pass
        with patch.object(tasks, '_worker_batches', {'batch': 1}), \
             patch.object(tasks, '_take_pending_task', side_effect=[(record, 'batch'), StopWorker]), \
             patch.object(tasks, '_run_task', side_effect=OSError('disk error')), \
             patch.object(tasks, '_persist', side_effect=OSError('disk error')), \
             patch.object(tasks.logging, 'exception'):
            with self.assertRaises(StopWorker):
                tasks._task_worker()
            self.assertEqual(tasks._worker_batches, {})

    def test_bulk_insert_is_atomic(self):
        storage.upsert_task(self.item('existing'))
        with self.assertRaises(KeyError):
            task_store.upsert_many([self.item('new'), {}])
        self.assertEqual([item['id'] for item in storage.load_tasks()], ['existing'])

    def test_rollback_export_preserves_raw_logs_and_never_overwrites(self):
        from scripts.export_task_history import export
        records = [self.item('one'), self.item('two')]
        task_store.upsert_many(records)
        destination = self.folder / 'rollback.json'
        self.assertEqual(export(storage.TASKS_DB_FILE, destination), 2)
        self.assertEqual(json.loads(destination.read_text(encoding='utf-8')), records)
        with self.assertRaises(FileExistsError):
            export(storage.TASKS_DB_FILE, destination)

    def test_recovery_only_changes_interrupted_records(self):
        task_store.upsert_many([self.item('done'), self.item('interrupted', status='running')])
        with patch.object(tasks, '_enqueue_task') as enqueue:
            self.assertEqual(tasks.recover_interrupted_tasks(), 1)
            self.assertEqual(enqueue.call_args.args[0]['id'], 'interrupted')
        self.assertEqual(storage.get_task_record('done')['status'], 'succeeded')
        self.assertEqual(storage.get_task_record('interrupted')['status'], 'queued')
        self.assertNotIn('done', tasks._logs)


if __name__ == '__main__':
    unittest.main()
