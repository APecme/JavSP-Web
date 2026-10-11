import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from javsp_web import __version__, app_supervisor, app_update, storage, updater


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
        self.enterContext(patch.object(app_supervisor, 'IMAGE_FILE', self.root / 'base-image.json'))
        self.enterContext(patch.object(app_supervisor, 'JOB_FILE', self.root / 'job.json'))
        self.enterContext(patch.object(storage, 'DATA_DIR', self.root))
        self.enterContext(patch.object(storage, 'UPDATE_SETTINGS_FILE', self.root / 'update-settings.json'))
        self.enterContext(patch.object(storage, 'ensure_seed_data'))
        self.enterContext(patch.dict(os.environ, {'JAVSP_WEB_APP_SUPERVISOR': '1'}, clear=False))
        os.environ.pop('JAVSP_WEB_UPDATE_MODE', None)
        os.environ.pop('JAVSP_WEB_BASE_RELEASE_LABEL', None)
        os.environ.pop('JAVSP_WEB_BASE_RELEASE_COMMIT', None)
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260923000000'
        os.environ['JAVSP_WEB_RELEASE_COMMIT'] = 'b' * 40
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
        self.assertEqual(updater.capability()['mode'], 'app')
        self.assertNotIn('reason', updater.capability())

    def test_web_apply_schedules_app_update_without_docker_client(self):
        target = dict(self.info, image='example@sha256:' + 'b' * 64, available=True, channel='bata', error='')
        with patch.object(updater, 'capability', return_value={'supported': True, 'mode': 'app'}), patch.object(updater, 'check', return_value=target), patch.object(updater, 'job', return_value={}), patch.object(updater, 'active_tasks', return_value=False), patch.object(app_update, 'schedule') as schedule:
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

    def launch(self):
        child = MagicMock()
        child.wait.return_value = 0
        with patch.object(app_supervisor.subprocess, 'Popen', return_value=child) as popen, patch.object(app_supervisor, 'health_ready', return_value=True), patch.object(app_supervisor.signal, 'signal'):
            self.assertEqual(app_supervisor.run(), 0)
        return popen.call_args.kwargs

    def install_update(self, target=None):
        self.mock_repository(self.archive())
        info = dict(self.info, target=target or self.info['target'])
        app_update.install(info)
        return info

    def test_same_image_restarts_preserve_installed_update_and_preferences(self):
        info = self.install_update()
        storage.save_update_settings({'experience_program': True, 'auto_update': True})
        for _ in range(2):
            launched = self.launch()
            self.assertEqual(launched['cwd'], self.apps / info['target'])
            self.assertEqual(launched['env']['JAVSP_WEB_RELEASE_LABEL'], info['target'])
            self.assertEqual(launched['env']['JAVSP_WEB_BASE_RELEASE_LABEL'], 'bata.20260923000000')
            self.assertEqual(launched['env']['JAVSP_WEB_BASE_RELEASE_COMMIT'], 'b' * 40)
            self.assertTrue(storage.get_update_settings()['auto_update'])
            self.assertTrue(storage.get_update_settings()['experience_program'])

    def test_same_stable_image_preserves_deliberately_installed_beta(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.37'
        info = self.install_update()
        storage.save_update_settings({'experience_program': True})
        for _ in range(2):
            launched = self.launch()
            self.assertEqual(launched['cwd'], self.apps / info['target'])
            self.assertTrue(storage.get_update_settings()['experience_program'])
        # The updater runs in the child, whose active release differs from the base.
        with patch.dict(os.environ, launched['env']):
            app_update.install(dict(info, target='bata.20260925000000'))
        self.assertEqual(app_supervisor.read_state()['base_image']['label'], '1.1.37')
        self.assertEqual(self.launch()['cwd'], self.apps / 'bata.20260925000000')

    def test_beta_to_stable_image_clears_saved_beta_selection(self):
        self.install_update()
        storage.save_update_settings({'experience_program': True, 'auto_update': True})
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting'})
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.39'
        os.environ['JAVSP_WEB_RELEASE_COMMIT'] = 'c' * 40
        launched = self.launch()
        self.assertEqual(launched['cwd'], self.base)
        self.assertEqual(launched['env']['JAVSP_WEB_RELEASE_LABEL'], 'v1.1.39')
        self.assertIsNone(app_supervisor.read_state()['current'])
        self.assertFalse(storage.get_update_settings()['experience_program'])
        self.assertTrue(storage.get_update_settings()['auto_update'])
        self.assertEqual(updater.channel(), 'stable')
        self.assertEqual(storage._read_json(app_supervisor.JOB_FILE, {})['status'], 'interrupted')
        self.assertEqual(self.launch()['cwd'], self.base)

    def test_older_updater_state_writer_preserves_cross_channel_choice_on_same_image(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.37'
        first = self.install_update()
        storage.save_update_settings({'experience_program': True})
        self.launch()
        self.assertEqual(storage._read_json(app_supervisor.IMAGE_FILE, {})['label'], '1.1.37')
        second = dict(first, target='bata.20260925000000')
        app_update.stage(second)
        # A previously released child updater writes only the original fields.
        app_supervisor.save_state({
            'current': second['target'], 'commit': second['commit'],
            'previous': first['target'], 'previous_commit': first['commit'], 'pending': True,
        })
        storage._write_json(app_supervisor.JOB_FILE, {'mode': 'app', 'status': 'restarting'})
        for _ in range(2):
            self.assertEqual(self.launch()['cwd'], self.apps / second['target'])
            self.assertTrue(storage.get_update_settings()['experience_program'])
        self.assertEqual(app_supervisor.read_state()['base_image']['label'], '1.1.37')
        self.assertEqual(storage._read_json(app_supervisor.JOB_FILE, {})['status'], 'updated')

    def test_recorded_image_change_wins_when_older_updater_omits_binding(self):
        for before, after in [('v1.1.37', 'v1.1.39'), ('bata.20260923000000', 'bata.20260924000000')]:
            with self.subTest(before=before, after=after):
                os.environ['JAVSP_WEB_RELEASE_LABEL'] = before
                app_supervisor.IMAGE_FILE.unlink(missing_ok=True)
                self.install_update(target='bata.20260925000000')
                self.launch()
                legacy = app_supervisor.read_state()
                legacy.pop('base_image')
                app_supervisor.save_state(legacy)
                os.environ['JAVSP_WEB_RELEASE_LABEL'] = after
                self.assertEqual(self.launch()['cwd'], self.base)
                self.assertEqual(storage._read_json(app_supervisor.IMAGE_FILE, {})['label'], after.lstrip('vV'))
                self.assertEqual(updater.channel(), 'bata' if after.startswith('bata.') else 'stable')

    def test_new_image_wins_even_when_saved_update_has_a_newer_version(self):
        self.install_update(target='bata.20261011000000')
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20261010000000'
        self.assertEqual(self.launch()['cwd'], self.base)
        self.assertTrue(storage.get_update_settings()['experience_program'])

    def test_same_channel_stable_image_upgrade_uses_new_image(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.37'
        self.install_update(target='1.1.38')
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.39'
        self.assertEqual(self.launch()['cwd'], self.base)

    def test_changed_commit_or_dependency_declarations_replace_saved_update(self):
        for change in ('commit', 'dependencies'):
            with self.subTest(change=change):
                self.install_update()
                if change == 'commit':
                    os.environ['JAVSP_WEB_RELEASE_COMMIT'] = 'c' * 40
                else:
                    (self.base / 'requirements.txt').write_bytes(b'fastapi==2\n')
                self.assertEqual(self.launch()['cwd'], self.base)

    def test_legacy_state_keeps_only_newer_update_in_same_channel(self):
        cases = [
            ('bata.20260923000000', 'bata.20260924044117', True),
            ('bata.20260925000000', 'bata.20260924044117', False),
            ('v1.1.37', '1.1.38', True),
            ('v1.1.39', '1.1.38', False),
            ('v1.1.39', 'bata.20260924044117', False),
            ('bata.20260923000000', '1.1.39', False),
        ]
        for base_label, target, preserve in cases:
            with self.subTest(base=base_label, target=target):
                os.environ['JAVSP_WEB_RELEASE_LABEL'] = base_label
                info = self.install_update(target=target)
                legacy = app_supervisor.read_state()
                legacy.pop('base_image')
                legacy['pending'] = False
                app_supervisor.save_state(legacy)
                app_supervisor.IMAGE_FILE.unlink(missing_ok=True)
                storage._write_json(storage.UPDATE_SETTINGS_FILE, {'experience_program': True})
                expected = self.apps / target if preserve else self.base
                self.assertEqual(self.launch()['cwd'], expected)
                self.assertEqual(self.launch()['cwd'], expected, 'migration must be persisted')
                self.assertEqual(app_supervisor.read_state()['base_image']['label'], base_label.lstrip('vV'))
                if not preserve:
                    self.assertEqual(updater.channel(), 'bata' if base_label.startswith('bata.') else 'stable')

    def test_first_stable_image_launch_resets_unbound_beta_preference(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.39'
        storage.save_update_settings({'experience_program': True, 'auto_update': True})
        self.assertEqual(self.launch()['cwd'], self.base)
        self.assertFalse(storage.get_update_settings()['experience_program'])
        # A fresh, explicit opt-in on this image must survive subsequent restarts.
        storage.save_update_settings({'experience_program': True})
        self.launch()
        self.assertTrue(storage.get_update_settings()['experience_program'])

    def test_unlabeled_image_health_uses_package_version(self):
        os.environ.pop('JAVSP_WEB_RELEASE_LABEL')
        with patch.object(app_supervisor, 'health_ready', return_value=True) as ready:
            child = MagicMock()
            child.wait.return_value = 0
            with patch.object(app_supervisor.subprocess, 'Popen', return_value=child), patch.object(app_supervisor.signal, 'signal'):
                self.assertEqual(app_supervisor.run(), 0)
        self.assertEqual(ready.call_args.args[1], __version__)


if __name__ == '__main__':
    unittest.main()
