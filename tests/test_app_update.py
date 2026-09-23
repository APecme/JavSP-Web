import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from javsp_web import app_supervisor, app_update, storage, updater


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.base.mkdir()
        (self.base / 'Dockerfile').write_bytes(b'FROM python:3.12-slim\n')
        (self.base / 'requirements.txt').write_bytes(b'fastapi==1\n')
        self.apps = self.root / 'apps'
        self.enterContext(patch.object(app_supervisor, 'BASE_ROOT', self.base))
        self.enterContext(patch.object(app_supervisor, 'APP_DIR', self.apps))
        self.enterContext(patch.object(app_supervisor, 'STATE_FILE', self.root / 'state.json'))
        self.enterContext(patch.object(app_supervisor, 'JOB_FILE', self.root / 'job.json'))
        self.enterContext(patch.object(storage, 'DATA_DIR', self.root))
        self.enterContext(patch.dict(os.environ, {'JAVSP_WEB_APP_SUPERVISOR': '1'}, clear=False))
        os.environ.pop('JAVSP_WEB_UPDATE_MODE', None)
        self.commit = 'a' * 40
        self.info = {'target': 'bata.20260924044117', 'commit': self.commit}
        self.files = {
            'Dockerfile': b'FROM python:3.12-slim\n',
            'requirements.txt': b'fastapi==1\n',
            'javsp_web/server.py': b'print("healthy")\n',
            'javsp_web/app_supervisor.py': b'print("supervisor")\n',
            'vendor/JavSP/config.yml': b'scanner: {}\n',
        }

    def archive(self, files=None):
        files = files or self.files
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            for name, content in files.items():
                package.writestr('APecme-JavSP-Web-abc/' + name, content)
        archive = self.root / 'download.zip'
        archive.write_bytes(buffer.getvalue())
        return archive

    def mock_repository(self, archive):
        tree = {'truncated': False, 'tree': [
            {'path': name, 'type': 'blob', 'sha': app_update.git_blob_sha(content)}
            for name, content in self.files.items()
        ]}
        def get_json(url):
            return {'sha': self.commit, 'tree': {'sha': 'b' * 40}} if '/commits/' in url else tree
        self.enterContext(patch.object(app_update, 'get_json', side_effect=get_json))
        self.enterContext(patch.object(app_update, 'download_archive', side_effect=lambda commit, path: shutil.copyfile(archive, path)))

    def test_download_verifies_git_blobs_and_switches_state(self):
        self.mock_repository(self.archive())
        app_update.install(self.info)
        state = app_supervisor.read_state()
        self.assertEqual(state['current'], self.info['target'])
        self.assertEqual(state['commit'], self.commit)
        self.assertTrue(state['pending'])
        self.assertEqual((app_supervisor.root_for(self.info['target']) / 'javsp_web/server.py').read_bytes(), self.files['javsp_web/server.py'])

    def test_rejects_changed_dependencies_without_switching(self):
        changed = dict(self.files, **{'requirements.txt': b'fastapi==2\n'})
        self.files = changed
        self.mock_repository(self.archive(changed))
        with self.assertRaisesRegex(ValueError, '手动更新 Docker 镜像'):
            app_update.install(self.info)
        self.assertEqual(app_supervisor.read_state(), {})

    def test_rejects_mismatched_git_blob(self):
        archive = self.archive()
        self.files['javsp_web/server.py'] = b'expected other content'
        self.mock_repository(archive)
        with self.assertRaisesRegex(ValueError, '校验失败'):
            app_update.install(self.info)
        self.assertEqual(app_supervisor.read_state(), {})

    def test_rejects_path_traversal(self):
        archive = self.archive(dict(self.files, **{'../escape.py': b'bad'}))
        self.mock_repository(archive)
        with self.assertRaisesRegex(ValueError, '不安全路径'):
            app_update.install(self.info)
        self.assertFalse((self.root / 'escape.py').exists())

    def test_supervisor_marks_healthy_update_complete(self):
        self.mock_repository(self.archive())
        app_update.install(self.info)
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting'})
        child = MagicMock()
        child.wait.return_value = 0
        with patch.object(app_supervisor.subprocess, 'Popen', return_value=child), patch.object(app_supervisor, 'health_ready', return_value=True), patch.object(app_supervisor.signal, 'signal'):
            self.assertEqual(app_supervisor.run(), 0)
        self.assertFalse(app_supervisor.read_state()['pending'])
        self.assertEqual(storage._read_json(app_supervisor.JOB_FILE, {})['status'], 'updated')

    def test_supervisor_rolls_back_failed_start(self):
        self.mock_repository(self.archive())
        app_update.install(self.info)
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting'})
        failed = MagicMock()
        failed.poll.return_value = 1
        base = MagicMock()
        base.wait.return_value = 0
        with patch.object(app_supervisor.subprocess, 'Popen', side_effect=[failed, base]), patch.object(app_supervisor, 'health_ready', side_effect=[False, True]), patch.object(app_supervisor.signal, 'signal'):
            self.assertEqual(app_supervisor.run(), 0)
        self.assertIsNone(app_supervisor.read_state()['current'])
        self.assertEqual(storage._read_json(app_supervisor.JOB_FILE, {})['status'], 'rolled_back')

    def test_app_mode_does_not_require_docker_socket(self):
        self.assertTrue(app_update.enabled())
        with patch.object(updater, 'enabled', return_value=False):
            self.assertEqual(updater.capability()['mode'], 'app')

    def test_web_apply_schedules_app_update_without_docker_client(self):
        target = dict(self.info, image='example@sha256:' + 'b' * 64, available=True, channel='bata', error='')
        with patch.object(updater, 'capability', return_value={'supported': True, 'mode': 'app'}), patch.object(updater, 'check', return_value=target), patch.object(updater, 'job', return_value={}), patch.object(updater, 'active_tasks', return_value=False), patch.object(updater, 'docker_client', side_effect=AssertionError('Docker socket not needed')), patch.object(app_update, 'schedule') as schedule:
            result = updater.apply()
        self.assertEqual(result['mode'], 'app')
        schedule.assert_called_once()

    def test_supervisor_normalizes_formal_image_label_for_health(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.37'
        child = MagicMock()
        child.wait.return_value = 0
        with patch.object(app_supervisor.subprocess, 'Popen', return_value=child), patch.object(app_supervisor, 'health_ready', return_value=True) as ready, patch.object(app_supervisor.signal, 'signal'):
            self.assertEqual(app_supervisor.run(), 0)
        self.assertEqual(ready.call_args.args[1], '1.1.37')


if __name__ == '__main__':
    unittest.main()
