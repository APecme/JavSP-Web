import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from javsp_web import storage, updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, root / value.relative_to(old)))
        self.enterContext(patch.dict(os.environ, {}, clear=False))
        os.environ.pop('JAVSP_WEB_RELEASE_LABEL', None)

    def test_settings_default_to_stable_and_experience_selects_bata(self):
        self.assertFalse(storage.get_update_settings()['experience_program'])
        settings = storage.save_update_settings({'experience_program': True, 'auto_update': True})
        self.assertTrue(settings['experience_program'])
        self.assertTrue(settings['check_enabled'])
        self.assertEqual(updater.channel(), 'bata')

    def test_beta_default_allows_persisted_opt_out(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260924044117'
        self.assertTrue(storage.get_update_settings()['experience_program'])
        self.assertFalse(storage.save_update_settings({'experience_program': False})['experience_program'])
        self.assertFalse(storage.get_update_settings()['experience_program'])
        storage.save_update_settings({'check_enabled': True})
        self.assertEqual(updater.channel(), 'stable')

    def test_stable_check_compares_image_embedded_version(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'v1.1.37'
        target = {'target': '1.1.38', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'latest'}
        with patch.object(updater, 'registry_target', return_value=target):
            result = updater.check(force=True)
        self.assertTrue(result['available'])
        self.assertEqual(result['current'], '1.1.37')
        self.assertEqual(result['target'], '1.1.38')

    def test_beta_check_switches_from_stable(self):
        storage.save_update_settings({'experience_program': True})
        target = {'target': 'bata.20260923190000', 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'bata'}
        with patch.object(updater, 'registry_target', return_value=target):
            result = updater.check(force=True)
        self.assertTrue(result['available'])
        self.assertTrue(result['switching_channel'])

    def test_beta_opt_out_offers_current_or_older_stable_release(self):
        os.environ['JAVSP_WEB_RELEASE_LABEL'] = 'bata.20260924044117'
        storage.save_update_settings({'experience_program': False})
        for version in (updater.__version__, '1.1.37'):
            target = {'target': version, 'image': 'example@sha256:' + 'a' * 64, 'image_id': 'sha256:' + 'b' * 64, 'tag': 'latest'}
            with patch.object(updater, 'registry_target', return_value=target) as registry:
                result = updater.check(force=True)
            registry.assert_called_once_with('latest')
            self.assertTrue(result['available'])
            self.assertTrue(result['switching_channel'])
            self.assertEqual(result['channel'], 'stable')

    def test_apply_uses_app_supervisor_without_docker_permissions(self):
        storage.save_update_settings({'experience_program': True, 'auto_update': False})
        target = {'target': 'bata.20260924044117', 'image': 'example@sha256:' + 'a' * 64, 'channel': 'bata', 'available': True}
        with patch.object(updater, 'capability', return_value={'supported': True}), patch.object(updater, 'active_tasks', return_value=False), patch.object(updater, 'check', return_value=target), patch.object(updater.app_update, 'schedule') as schedule:
            result = updater.apply()
        self.assertEqual(result['mode'], 'app')
        self.assertEqual(result['status'], 'scheduled')
        schedule.assert_called_once()

    def test_apply_refuses_without_supervisor(self):
        with patch.object(updater, 'capability', return_value={'supported': False, 'reason': '请手动更新镜像'}), patch.object(updater, 'active_tasks', return_value=False):
            with self.assertRaisesRegex(updater.UpdateError, '手动更新镜像'):
                updater.apply()


if __name__ == '__main__':
    unittest.main()
