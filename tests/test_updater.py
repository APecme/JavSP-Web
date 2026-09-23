import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from javsp_web import storage, updater


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

    def test_apply_refuses_without_docker_capability(self):
        with patch.object(updater, 'capability', return_value={'supported': False, 'reason': '未挂载 Docker'}):
            with self.assertRaises(updater.UpdateError):
                updater.apply()


if __name__ == '__main__':
    unittest.main()
