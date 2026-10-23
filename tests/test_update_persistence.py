"""Restart persistence for verified code-only app updates.

These tests model container/device restarts: every launch is a fresh supervisor
decision read from the data volume, never from state kept in memory.
"""
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from javsp_web import app_supervisor, app_update, storage, updater


class UpdatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.base.mkdir()
        (self.base / 'Dockerfile').write_bytes(b'FROM python:3.12-slim\n')
        (self.base / 'requirements.txt').write_bytes(b'fastapi==1\n')
        self.apps = self.root / 'apps'
        self.data = self.root / 'data'
        self.enterContext(patch.object(app_supervisor, 'BASE_ROOT', self.base))
        self.enterContext(patch.object(app_supervisor, 'APP_DIR', self.apps))
        self.enterContext(patch.object(app_supervisor, 'STATE_FILE', self.data / 'updates' / 'app-current.json'))
        self.enterContext(patch.object(app_supervisor, 'IMAGE_FILE', self.data / 'updates' / 'base-image.json'))
        self.enterContext(patch.object(app_supervisor, 'JOB_FILE', self.data / 'updates' / 'job.json'))
        self.enterContext(patch.object(storage, 'DATA_DIR', self.data))
        self.enterContext(patch.object(storage, 'UPDATE_SETTINGS_FILE', self.data / 'update-settings.json'))
        self.enterContext(patch.object(storage, 'ensure_seed_data'))
        self.enterContext(patch.object(app_supervisor.signal, 'signal'))
        self.enterContext(patch.dict(os.environ, {
            'JAVSP_WEB_APP_SUPERVISOR': '1',
            'JAVSP_WEB_RELEASE_LABEL': 'bata.20260923000000',
            'JAVSP_WEB_RELEASE_COMMIT': 'b' * 40,
        }, clear=False))
        for key in ('JAVSP_WEB_BASE_RELEASE_LABEL', 'JAVSP_WEB_BASE_RELEASE_COMMIT'):
            os.environ.pop(key, None)
        self.commit = 'a' * 40
        self.info = {'target': 'bata.20260924044117', 'commit': self.commit}
        self.files = {
            'Dockerfile': b'FROM python:3.12-slim\n',
            'requirements.txt': b'fastapi==1\n',
            'javsp_web/server.py': b'print("healthy")\n',
            'javsp_web/app_supervisor.py': b'print("supervisor")\n',
            'vendor/JavSP/config.yml': b'scanner: {}\n',
        }

    # -- fixtures -----------------------------------------------------------
    def archive(self, files=None):
        files = files or self.files
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            for name, content in files.items():
                package.writestr('APecme-JavSP-Web-abc/' + name, content)
        path = self.root / 'download.zip'
        path.write_bytes(buffer.getvalue())
        return path

    def mock_repository(self, files=None):
        files = files or self.files
        download = self.archive(files)

        def get_json(url):
            if '/commits/' in url:
                return {'sha': self.commit, 'tree': {'sha': 'b' * 40}}
            return {'truncated': False, 'tree': [
                {'path': name, 'type': 'blob', 'sha': app_update.git_blob_sha(content)}
                for name, content in files.items()
            ]}

        self.enterContext(patch.object(app_update, 'get_json', side_effect=get_json))
        self.enterContext(patch.object(app_update, 'download_archive', side_effect=lambda commit, path: shutil.copyfile(download, path)))

    def install(self, target=None, files=None):
        self.mock_repository(files)
        info = dict(self.info, target=target or self.info['target'])
        app_update.install(info)
        return info

    def launch(self, health=True):
        """One supervisor start-up: the only state it may trust is on the volume.

        ``health`` may be a list of per-attempt results when a launch is
        expected to fall back from the update to an earlier version.
        """
        child = MagicMock()
        child.poll.return_value = None
        child.wait.return_value = 0
        ready = patch.object(app_supervisor, 'health_ready', return_value=health)
        if isinstance(health, list):
            ready = patch.object(app_supervisor, 'health_ready', side_effect=health)
        with patch.object(app_supervisor.subprocess, 'Popen', return_value=child) as popen, ready:
            code = app_supervisor.run()
        return code, popen.call_args.kwargs

    def job(self):
        return storage._read_json(app_supervisor.JOB_FILE, {})

    # -- crash recovery -----------------------------------------------------
    def test_crashed_download_does_not_block_future_updates_forever(self):
        self.launch()  # steady state: base image identity is recorded
        storage._write_json(app_supervisor.JOB_FILE, {
            'mode': 'app', 'status': 'downloading', 'message': '正在下载并校验更新文件',
            'id': 'crashed', 'target': self.info['target'],
        })
        self.launch()  # container restarted after the update thread died
        self.assertEqual(self.job()['status'], 'interrupted')
        self.assertIn('中断', self.job()['message'])
        self.assertFalse(updater.busy())
        target = dict(self.info, image='example@sha256:' + 'b' * 64, available=True, channel='bata', error='')
        with patch.object(updater, 'capability', return_value={'supported': True}), \
                patch.object(updater, 'check', return_value=target), \
                patch.object(updater, 'active_tasks', return_value=False), \
                patch.object(app_update, 'schedule') as schedule:
            updater.apply()  # must no longer be refused as "already updating"
        schedule.assert_called_once()

    def test_pending_install_is_left_for_the_health_check_to_settle(self):
        self.install()
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting', 'id': 'x'})
        self.launch()
        self.assertEqual(self.job()['status'], 'updated')
        self.assertFalse(app_supervisor.read_state()['pending'])

    def test_rolled_back_pending_install_reports_the_failure_reason(self):
        self.install()
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting', 'id': 'x'})
        self.launch(health=False)
        job = self.job()
        self.assertEqual(job['status'], 'rolled_back')
        self.assertIn('启动', job['message'])
        self.assertIsNone(app_supervisor.read_state()['current'])

    # -- parent/child metadata consistency ----------------------------------
    def running_overlay(self, label='bata.20260923120000'):
        """A container already running an installed overlay, as an older
        supervisor would launch it: no base metadata in the child environment."""
        app_supervisor.save_state({'current': label, 'commit': 'b' * 40, 'previous': None,
                                   'previous_commit': '', 'pending': False})
        return patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': label, 'JAVSP_WEB_RELEASE_COMMIT': 'b' * 40})

    def test_child_without_base_metadata_does_not_bind_the_overlay_as_the_base(self):
        # Second update installed by a child whose supervisor is too old to pass
        # base release metadata: its own label is the overlay, never the image.
        with self.running_overlay():
            self.install()
        binding = app_supervisor.read_state()['base_image']
        self.assertEqual(binding['label'], '')
        self.assertTrue(binding['files_sha256'])
        code, launched = self.launch()
        self.assertEqual(code, 0)
        self.assertEqual(launched['cwd'], self.apps / self.info['target'])
        state = app_supervisor.read_state()
        self.assertEqual(state['current'], self.info['target'])
        self.assertEqual(state['base_image']['label'], 'bata.20260923000000')
        # A second independent cycle still runs the update.
        self.assertEqual(self.launch()[1]['cwd'], self.apps / self.info['target'])

    def test_unknown_binding_is_discarded_when_the_image_build_files_change(self):
        with self.running_overlay():
            self.install()
        (self.base / 'requirements.txt').write_bytes(b'fastapi==2\n')
        self.assertEqual(self.launch()[1]['cwd'], self.base)
        self.assertIsNone(app_supervisor.read_state()['current'])

    def test_install_reuses_the_recorded_image_binding_without_base_metadata(self):
        self.launch()  # the supervisor records the real image identity
        with self.running_overlay():
            self.install()
        self.assertEqual(app_supervisor.read_state()['base_image']['label'], 'bata.20260923000000')
        self.assertEqual(self.launch()[1]['cwd'], self.apps / self.info['target'])

    def test_stale_parent_release_label_is_not_copied_into_the_child(self):
        launched = self.launch()[1]
        self.assertEqual(launched['env']['JAVSP_WEB_BASE_RELEASE_LABEL'], 'bata.20260923000000')
        self.assertEqual(self.launch()[1]['env']['JAVSP_WEB_RELEASE_LABEL'], 'bata.20260923000000')
        self.install()
        launched = self.launch()[1]
        self.assertEqual(launched['env']['JAVSP_WEB_RELEASE_LABEL'], self.info['target'])
        self.assertEqual(launched['env']['JAVSP_WEB_BASE_RELEASE_LABEL'], 'bata.20260923000000')

    # -- corrupted and stray update copies ----------------------------------
    def test_corrupted_staged_version_is_downloaded_again(self):
        broken = self.apps / self.info['target'] / 'javsp_web'
        broken.mkdir(parents=True)
        (broken / 'server.py').write_bytes(b'partial')
        self.install()
        root = app_supervisor.root_for(self.info['target'])
        self.assertEqual((root / 'javsp_web/server.py').read_bytes(), self.files['javsp_web/server.py'])
        self.assertEqual(app_supervisor.read_state()['current'], self.info['target'])

    def test_stray_file_occupying_a_version_name_is_replaced(self):
        self.apps.mkdir(parents=True)
        (self.apps / self.info['target']).write_bytes(b'junk')
        self.install()
        self.assertTrue((self.apps / self.info['target']).is_dir())

    def test_incomplete_update_copy_is_reported_as_value_error(self):
        partial = self.apps / 'bata.20260925000000' / 'javsp_web'
        partial.mkdir(parents=True)
        (partial / 'server.py').write_bytes(b'only server\n')
        with self.assertRaisesRegex(ValueError, '更新文件不完整'):
            app_supervisor.root_for('bata.20260925000000')

    def test_corrupted_current_version_rolls_back_to_the_previous_version(self):
        first = self.install()
        self.launch()
        second = dict(self.info, target='bata.20260925000000')
        with patch.dict(os.environ, self.launch()[1]['env']):
            app_update.install(second)
        self.launch()
        (self.apps / second['target'] / 'javsp_web' / 'server.py').unlink()
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting',
                                                     'id': 'x', 'target': second['target']})
        code, launched = self.launch()
        self.assertEqual(code, 0)
        self.assertEqual(launched['cwd'], self.apps / first['target'])
        self.assertEqual(launched['env']['JAVSP_WEB_RELEASE_LABEL'], first['target'])
        state = app_supervisor.read_state()
        self.assertEqual(state['current'], first['target'])
        self.assertIsNone(state['previous'])
        self.assertEqual(self.job()['status'], 'rolled_back')
        self.assertIn('上一版本', self.job()['message'])
        # The choice survives the next restart.
        self.assertEqual(self.launch()[1]['cwd'], self.apps / first['target'])

    def test_corrupted_current_version_rolls_back_to_base_and_stays(self):
        self.install()
        self.launch()
        (self.apps / self.info['target'] / 'Dockerfile').unlink()
        self.assertEqual(self.launch()[1]['cwd'], self.base)
        self.assertIsNone(app_supervisor.read_state()['current'])
        self.assertEqual(self.launch()[1]['cwd'], self.base)

    # -- rollback semantics -------------------------------------------------
    def test_rollback_target_survives_the_next_restart(self):
        first = self.install()
        self.launch()
        second = dict(self.info, target='bata.20260925000000')
        with patch.dict(os.environ, self.launch()[1]['env']):
            app_update.install(second)
        self.launch(health=[False, True])
        self.assertEqual(app_supervisor.read_state()['current'], first['target'])
        self.assertEqual(self.launch()[1]['cwd'], self.apps / first['target'])
        self.assertIsNone(app_supervisor.read_state()['previous'])

    # -- version reporting --------------------------------------------------
    def test_status_separates_image_selection_and_target(self):
        self.install()
        child_env = {'JAVSP_WEB_RELEASE_LABEL': self.info['target'],
                     'JAVSP_WEB_BASE_RELEASE_LABEL': 'bata.20260923000000',
                     'JAVSP_WEB_BASE_RELEASE_COMMIT': 'b' * 40}
        with patch.object(updater, 'check', return_value={}), patch.dict(os.environ, child_env):
            result = updater.status()
        self.assertEqual(result['base']['label'], 'bata.20260923000000')
        self.assertEqual(result['selected'], self.info['target'])
        self.assertEqual(result['current'], self.info['target'])
        self.assertTrue(result['pending'])


if __name__ == '__main__':
    unittest.main()
