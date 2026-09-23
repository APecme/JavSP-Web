import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from javsp_web import storage, update_worker, updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.enterContext(patch.object(storage, 'DATA_DIR', root))
        self.enterContext(patch.object(storage, 'UPDATE_SETTINGS_FILE', root / 'update-settings.json'))
        self.enterContext(patch.object(updater, 'REPOSITORY', 'example/javsp-web'))
        self.enterContext(patch.dict(os.environ, {}, clear=False))
        os.environ.pop('JAVSP_WEB_RELEASE_LABEL', None)

    def test_settings_default_to_stable_and_experience_selects_bata(self):
        self.assertFalse(storage.get_update_settings()['experience_program'])
        settings = storage.save_update_settings({'experience_program': True, 'auto_update': True})
        self.assertTrue(settings['experience_program'])
        self.assertTrue(settings['check_enabled'])
        self.assertEqual(updater.channel(), 'bata')

    def test_beta_image_defaults_to_beta_channel_without_overriding_saved_choice(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260924044117'
        self.assertTrue(storage.get_update_settings()['experience_program'])
        storage.save_update_settings({'experience_program': False})
        self.assertFalse(storage.get_update_settings()['experience_program'])

    def test_stable_check_compares_image_embedded_version(self):
        with patch.object(updater, 'enabled', return_value=False), patch.object(updater, 'registry_target', return_value={'target': '1.1.37', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'latest'}):
            result = updater.check(force=True)
        self.assertTrue(result['available'])
        self.assertEqual(result['target'], '1.1.37')

    def test_beta_check_switches_from_stable(self):
        with patch.object(storage, 'get_update_settings', return_value={'experience_program': True, 'check_enabled': True, 'auto_update': False, 'check_interval_hours': 24, 'last_check_at': '', 'last_result': {}}), patch.object(updater, 'enabled', return_value=False), patch.object(updater, 'registry_target', return_value={'target': 'bata.20260923190000', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'bata'}), patch.object(updater, 'current_version', return_value='1.1.36'):
            result = updater.check(force=True)
        self.assertTrue(result['available'])
        self.assertTrue(result['switching_channel'])

    def test_beta_image_does_not_claim_older_stable_image_as_update(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260924044117'
        storage.save_update_settings({'experience_program': False})
        target = {'target': '1.1.36', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'latest'}
        with patch.object(updater, 'enabled', return_value=False), patch.object(updater, 'registry_target', return_value=target):
            result = updater.check(force=True)
        self.assertFalse(result['available'])
        self.assertTrue(result['switching_channel'])

    def test_beta_image_detects_newer_stable_release(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260924044117'
        storage.save_update_settings({'experience_program': False})
        target = {'target': '1.1.37', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'latest'}
        with patch.object(updater, 'enabled', return_value=False), patch.object(updater, 'registry_target', return_value=target):
            result = updater.check(force=True)
        self.assertTrue(result['available'])

    def test_apply_refuses_without_docker_capability(self):
        with patch.object(updater, 'capability', return_value={'supported': False, 'reason': '未挂载 Docker'}):
            with self.assertRaises(updater.UpdateError):
                updater.apply()

    def worker_client(self):
        source = MagicMock()
        source.name = 'javsp-web'
        source.status = 'running'
        source.attrs = {
            'Config': {'Labels': {'io.javsp-web.self-update': 'true'}, 'Image': 'example/javsp-web:bata'},
            'HostConfig': {'Binds': ['/host/data:/app/data:rw']},
        }
        source.rename.side_effect = lambda name: setattr(source, 'name', name)
        replacement = MagicMock()
        replacement.status = 'running'
        replacement.exec_run.return_value.exit_code = 0
        client = MagicMock()
        client.containers.get.side_effect = lambda identity: source if identity == 'old-id' else replacement
        client.api.create_container_from_config.return_value = {'Id': 'new-id'}
        os.environ['JAVSP_WEB_UPDATE_SOURCE'] = 'old-id'
        os.environ['JAVSP_WEB_UPDATE_TARGET'] = 'example/javsp-web@sha256:' + 'a' * 64
        job_path = storage.DATA_DIR / 'updates' / 'job.json'
        storage._write_json(job_path, {'helper_id': 'helper-id', 'status': 'scheduled'})
        return client, source, replacement, job_path

    def test_worker_pulls_before_stopping_and_keeps_data_volume(self):
        client, source, _, job_path = self.worker_client()
        order = []
        client.images.pull.side_effect = lambda target: order.append('pull')
        source.stop.side_effect = lambda **kwargs: order.append('stop')
        with patch.object(update_worker.docker, 'from_env', return_value=client), patch.object(update_worker.time, 'sleep'):
            update_worker.run('job-id')
        self.assertEqual(order, ['pull', 'stop'])
        created = client.api.create_container_from_config.call_args
        self.assertEqual(created.args[0]['Image'], os.environ['JAVSP_WEB_UPDATE_TARGET'])
        self.assertEqual(created.args[0]['HostConfig']['Binds'], ['/host/data:/app/data:rw'])
        self.assertEqual(created.kwargs['name'], 'javsp-web')
        source.remove.assert_called_once_with(v=False, force=True)
        result = storage._read_json(job_path, {})
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(result['helper_id'], 'helper-id')

    def test_worker_pull_failure_does_not_stop_old_container(self):
        client, source, _, job_path = self.worker_client()
        client.images.pull.side_effect = RuntimeError('download failed')
        with patch.object(update_worker.docker, 'from_env', return_value=client):
            update_worker.run('job-id')
        source.stop.assert_not_called()
        client.api.create_container_from_config.assert_not_called()
        result = storage._read_json(job_path, {})
        self.assertEqual(result['status'], 'failed')
        self.assertIn('download failed', result['message'])

    def test_worker_removes_failed_replacement_before_rollback(self):
        client, source, replacement, job_path = self.worker_client()
        order = []
        replacement.remove.side_effect = lambda **kwargs: order.append('remove replacement')
        source.rename.side_effect = lambda name: (order.append('restore name' if name == 'javsp-web' else 'backup name'), setattr(source, 'name', name))
        client.api.start.side_effect = RuntimeError('startup failed')
        with patch.object(update_worker.docker, 'from_env', return_value=client):
            update_worker.run('job-id')
        self.assertLess(order.index('remove replacement'), order.index('restore name'))
        replacement.remove.assert_called_once_with(v=False, force=True)
        self.assertEqual(source.name, 'javsp-web')
        self.assertEqual(storage._read_json(job_path, {})['status'], 'rolled_back')

    def test_worker_rejects_anonymous_data_volume(self):
        with self.assertRaisesRegex(RuntimeError, '/app/data'):
            update_worker.validate_container({'Config': {'Labels': {'io.javsp-web.self-update': 'true'}}, 'Mounts': [{'Destination': '/app/data', 'Type': 'volume'}], 'HostConfig': {'Binds': []}})

    def test_worker_health_failure_rolls_back(self):
        client, source, replacement, job_path = self.worker_client()
        replacement.exec_run.return_value.exit_code = 1
        with patch.object(update_worker.docker, 'from_env', return_value=client), patch.object(update_worker.time, 'sleep'):
            update_worker.run('job-id')
        self.assertEqual(replacement.exec_run.call_count, 15)
        replacement.remove.assert_called_once_with(v=False, force=True)
        self.assertEqual(source.name, 'javsp-web')
        self.assertEqual(storage._read_json(job_path, {})['status'], 'rolled_back')

    def test_helper_does_not_duplicate_compose_socket_mount(self):
        binds = ['/host/data:/app/data:rw', '/var/run/docker.sock:/var/run/docker.sock:rw']
        attrs = {'Config': {'Image': 'example/javsp-web:bata'}, 'HostConfig': {'Binds': binds}}
        with patch.object(update_worker.docker, 'APIClient') as api_client:
            update_worker.helper_config(attrs, 'job-id', 'old-id', 'example/javsp-web@sha256:' + 'a' * 64, '/app/data')
        self.assertEqual(api_client.return_value.create_host_config.call_args.kwargs['binds'], binds)


if __name__ == '__main__':
    unittest.main()
