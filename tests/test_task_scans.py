"""Manual scans must stay responsive while a mounted filesystem is blocked."""
import copy
from collections import deque
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))
from javsp_web import storage, tasks, task_scans, task_store


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.root / 'state' / value.relative_to(old)))
        self.enterContext(patch.object(tasks, 'DATA_DIR', self.root / 'state'))
        self.enterContext(patch.object(tasks, '_TASK_COVERS_DIR', self.root / 'state/task-covers'))
        self.enterContext(patch.object(tasks, '_logs', {}))
        self.enterContext(patch.object(tasks, '_cancelled_tasks', set()))
        self.enterContext(patch.object(tasks, '_deleted_tasks', set()))
        self.enterContext(patch.object(tasks, '_processes', {}))
        self.enterContext(patch.object(tasks, '_pending_tasks', deque()))
        self.enterContext(patch.object(tasks, '_worker_batches', {}))
        self.enqueue = self.enterContext(patch.object(tasks, '_enqueue_task'))
        self.config = yaml.safe_load((ROOT / 'vendor/JavSP/config.yml').read_text(encoding='utf-8'))
        self.config['scanner'].update(minimum_size=10, input_files=None, skip_nfo_dir=False)
        self.enterContext(patch.object(tasks, '_preset_config_data', side_effect=lambda _: (copy.deepcopy(self.config), {'name': 'Test', 'task_concurrency': 1})))
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        from fastapi.testclient import TestClient
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)

    def files(self, *names):
        folder = self.root / 'mount'
        folder.mkdir(exist_ok=True)
        paths = []
        for name in names:
            path = folder / name
            path.write_bytes(b'x' * 20)
            paths.append(path)
        return paths

    def submit(self, path, selected=None):
        body = dict(input_directory=str(path), preset_id='default')
        if selected is not None:
            body['input_files'] = list(map(str, selected))
        response = self.client.post('/api/tasks', json=body)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertTrue(response.json()['scan'])
        return response.json()['tasks'][0]

    def children(self, scan):
        return [item for item in storage.load_tasks() if item['id'] != scan['id']]

    def test_submission_polling_and_cancel_never_stat_mount(self):
        mount = self.root / 'unresponsive-mount'
        original_stat = Path.stat

        def stat(path, *args, **kwargs):
            if path == mount:
                raise AssertionError('request touched media mount')
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, 'stat', stat), patch.object(tasks, '_task_name', side_effect=AssertionError('scanned while naming')):
            scan = self.submit(mount)
            response = self.client.get('/api/tasks?limit=20&view=manual')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['items'][0]['task_type'], 'scan')
            self.assertEqual(self.client.get('/api/tasks/' + scan['id']).status_code, 200)
            self.assertEqual(self.client.post('/api/tasks/' + scan['id'] + '/cancel').status_code, 200)

    def blocked_scan(self):
        files = self.files('ABC-123.mp4')
        mount = files[0].parent
        entered, release = threading.Event(), threading.Event()
        workers = []
        original_rglob = Path.rglob

        def rglob(path, *args, **kwargs):
            if path == mount:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('test scan was not released')
            return original_rglob(path, *args, **kwargs)

        def enqueue(task):
            if task.get('task_type') == 'scan':
                worker = threading.Thread(target=tasks._run_task, args=(task,), daemon=True)
                workers.append(worker)
                worker.start()

        self.enqueue.side_effect = enqueue
        self.enterContext(patch.object(Path, 'rglob', rglob))

        def cleanup():
            release.set()
            for worker in workers:
                worker.join(3)
                self.assertFalse(worker.is_alive())

        self.addCleanup(cleanup)
        start = time.monotonic()
        scan = self.submit(mount)
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertTrue(entered.wait(2))
        self.assertFalse(release.is_set())
        return scan, release, workers

    def test_blocked_directory_returns_202_and_polling_works_before_io_finishes(self):
        scan, release, workers = self.blocked_scan()
        start = time.monotonic()
        detail = self.client.get('/api/tasks/' + scan['id']).json()
        self.assertEqual(detail['status'], 'running')
        self.assertLess(time.monotonic() - start, 1)
        self.assertFalse(release.is_set())
        release.set()
        workers[0].join(3)
        self.assertFalse(workers[0].is_alive())
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'succeeded')
        self.assertEqual(len(self.children(scan)), 1)

    def test_cancel_and_delete_blocked_scan_never_enqueues_or_resurrects(self):
        scan, release, workers = self.blocked_scan()
        self.assertEqual(self.client.post('/api/tasks/' + scan['id'] + '/cancel').status_code, 200)
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'cancelled')
        self.assertEqual(self.client.delete('/api/tasks/' + scan['id']).status_code, 200)
        release.set()
        workers[0].join(3)
        self.assertFalse(workers[0].is_alive())
        self.assertEqual(storage.load_tasks(), [])
        self.assertEqual(self.enqueue.call_count, 1)

    def test_multiselect_groups_parts_keeps_small_tail_and_shares_concurrency(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4', 'ABC-123.mp4')
        paths[1].write_bytes(b'x')
        scan = self.submit(paths[0], [*paths, paths[0]])
        tasks._run_task(scan)
        children = self.children(scan)
        self.assertEqual(len(children), 2)
        multipart = next(task for task in children if len(task['input_files']) == 2)
        self.assertEqual(multipart['input_files'], list(map(str, paths[:2])))
        self.assertEqual({task['batch_id'] for task in children}, {scan['id']})
        self.assertEqual({task['task_concurrency'] for task in children}, {1})
        tasks._pending_tasks.extend(children)
        first, batch = tasks._take_pending_task()
        self.assertIsNone(tasks._take_pending_task())
        tasks._worker_batches[batch] -= 1
        self.assertIsNotNone(tasks._take_pending_task())
        finished = storage.get_task_record(scan['id'])
        self.assertEqual(finished['scan']['created_tasks'], 2)
        self.assertEqual(finished['scan']['discovered_files'], 3)

    def test_multiselect_falls_back_when_mount_realpath_is_unsupported(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2-4953812-2.mp4')
        scan = self.submit(paths[0], paths)
        original_realpath = tasks.os.path.realpath

        def realpath(path, *args, **kwargs):
            if str(path).startswith(str(paths[0].parent)):
                raise OSError(1005, '底层设备不工作')
            return original_realpath(path)

        with patch.object(tasks.os.path, 'realpath', side_effect=realpath):
            tasks._run_task(scan)
        children = self.children(scan)
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'succeeded')
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['input_files'], list(map(str, paths)))

    def test_single_file_still_creates_one_scrape_task(self):
        video = self.files('ABC-123.mp4')[0]
        scan = self.submit(video)
        tasks._run_task(scan)
        children = self.children(scan)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['input_directory'], str(video))
        self.assertEqual(children[0]['status'], 'queued')

    def test_missing_path_and_empty_directory_are_visible_failures(self):
        for folder in [self.root / 'missing', self.root / 'empty']:
            if folder.name == 'empty':
                folder.mkdir()
            scan = self.submit(folder)
            tasks._run_task(scan)
            result = storage.get_task_record(scan['id'])
            self.assertEqual(result['status'], 'failed')
            self.assertIn('扫描失败', result['error'])
            self.assertEqual(result['scan']['created_tasks'], 0)

    def test_network_enumeration_error_is_recorded_without_partial_batch(self):
        video = self.files('ABC-123.mp4')[0]
        scan = self.submit(video.parent)
        with patch.object(Path, 'rglob', side_effect=OSError('network disconnected')):
            tasks._run_task(scan)
        self.assertIn('network disconnected', storage.get_task_record(scan['id'])['error'])
        self.assertEqual(self.children(scan), [])

    def test_ambiguous_parts_fail_before_any_child_starts(self):
        paths = self.files('FC2-4953812-1.mp4', 'FC2PPV-4953812-01.mkv')
        scan = self.submit(paths[0], paths)
        tasks._run_task(scan)
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'failed')
        self.assertEqual(self.children(scan), [])
        self.assertEqual(self.enqueue.call_count, 1)

    def test_cancellation_after_preparation_discards_config_and_children(self):
        video = self.files('ABC-123.mp4')[0]
        scan = self.submit(video)
        original = tasks._prepare_tasks

        def prepare(*args, **kwargs):
            prepared = original(*args, **kwargs)
            self.assertTrue(tasks.cancel_task(scan['id']))
            return prepared

        with patch.object(tasks, '_prepare_tasks', side_effect=prepare):
            tasks._run_task(scan)
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'cancelled')
        self.assertEqual(self.children(scan), [])
        self.assertEqual(list((self.root / 'state/task-config').glob('*.yml')), [])

    def test_restart_resumes_uncommitted_scan_and_not_completed_scan(self):
        video = self.files('ABC-123.mp4')[0]
        scan = self.submit(video)
        scan['status'] = 'running'
        tasks._persist(scan)
        self.enqueue.reset_mock()
        self.assertEqual(tasks.recover_interrupted_tasks(), 1)
        restored = self.enqueue.call_args.args[0]
        self.assertEqual(restored['task_type'], 'scan')
        tasks._run_task(restored)
        self.assertEqual(storage.get_task_record(scan['id'])['status'], 'succeeded')
        self.enqueue.reset_mock()
        tasks.recover_interrupted_tasks()
        self.assertTrue(all(call.args[0].get('task_type') != 'scan' for call in self.enqueue.call_args_list))
        self.assertEqual(len(self.children(scan)), 1)

    def test_empty_selection_and_blank_paths_are_rejected(self):
        self.assertEqual(self.client.post('/api/tasks', json={'input_directory': 'x', 'input_files': []}).status_code, 422)
        self.assertEqual(self.client.post('/api/tasks', json={'input_directory': 'x', 'input_files': [' ']}).status_code, 400)

    def test_multiselect_dialog_cleanup_and_single_endpoint_compatibility(self):
        self.assertEqual(sum(getattr(route, 'path', None) == '/api/path/select-multi'
                             and 'POST' in getattr(route, 'methods', set())
                             for route in self.client.app.routes), 1)
        root = Mock()
        dialog = types.ModuleType('tkinter.filedialog')
        dialog.askopenfilenames = Mock(return_value=('X:/one.mp4', 'X:/two.mp4'))
        dialog.askopenfilename = Mock(return_value='X:/one.mp4')
        tk = types.ModuleType('tkinter')
        tk.Tk = Mock(return_value=root)
        tk.filedialog = dialog
        with patch.dict(sys.modules, {'tkinter': tk, 'tkinter.filedialog': dialog}), patch.object(self.server, 'IS_DOCKER', False):
            self.assertEqual(self.client.post('/api/path/select-multi', json={'kind': 'file'}).json()['paths'], ['X:/one.mp4', 'X:/two.mp4'])
            self.assertEqual(self.client.post('/api/path/select', json={'kind': 'file'}).json()['path'], 'X:/one.mp4')
            dialog.askopenfilenames.side_effect = RuntimeError('dialog failed')
            self.assertEqual(self.client.post('/api/path/select-multi', json={'kind': 'file'}).status_code, 500)
        self.assertEqual(root.destroy.call_count, 3)
        self.assertFalse(self.server._native_path_lock.locked())


if __name__ == '__main__':
    unittest.main()
