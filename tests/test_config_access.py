"""F03: operators can use presets but never read credentials stored in configuration."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from javsp_web import server, storage

SECRETS = ['proxy-pass-7731', 'sk-translate-9911', 'cookie-value-4410', 'baidu-app-5521', 'query-key-6612', 'global-pass-8842']


class ConfigAccessTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='f03-config-'))
        previous = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(previous):
                self.enterContext(patch.object(storage, name, Path(directory) / value.relative_to(previous)))
        storage.ensure_seed_data()
        storage.write_config(yaml.safe_dump({
            'network': {'proxy_server': 'socks5://global:global-pass-8842@127.0.0.1:1080'},
        }))
        storage.save_preset({'id': 'form-secret', 'name': '表单预设', 'mode': 'form', 'task_concurrency': 2, 'form': {
            'network': {'proxy_server': 'http://user:proxy-pass-7731@proxy.local:8080'},
            'translator': {'engine': {'name': 'openai', 'url': 'https://api.example.com/v1?api_key=query-key-6612&model=x',
                                      'api_key': 'sk-translate-9911'}},
            'crawler': {'cookies': {'javdb': '_jdb_session=cookie-value-4410'}},
        }})
        storage.save_preset({'id': 'yaml-secret', 'name': 'YAML 预设', 'mode': 'yaml', 'content': yaml.safe_dump({
            'translator': {'engine': {'name': 'baidu', 'app_id': 'baidu-app-5521', 'api_key': 'sk-translate-9911'}},
            'network': {'retry': 5},
        })})
        self.client = self.enterContext(TestClient(server.app))
        previous_overrides = dict(server.app.dependency_overrides)
        self.addCleanup(lambda: (server.app.dependency_overrides.clear(), server.app.dependency_overrides.update(previous_overrides)))

    def as_role(self, role):
        server.app.dependency_overrides[server.current_user] = lambda: {'username': role, 'role': role}

    def assert_no_secret(self, text):
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_operator_preset_list_is_redacted_but_usable(self):
        self.as_role('operator')
        response = self.client.get('/api/presets')
        self.assertEqual(response.status_code, 200)
        self.assert_no_secret(response.text)
        presets = {item['id']: item for item in response.json()}
        self.assertEqual({'default', 'form-secret', 'yaml-secret'} <= set(presets), True)
        form = presets['form-secret']
        self.assertTrue(form['redacted'])
        self.assertEqual(form['name'], '表单预设')
        self.assertEqual(form['task_concurrency'], 2)
        self.assertEqual(form['form_values']['network']['proxy_server'], 'http://********@proxy.local:8080')
        self.assertEqual(form['form_values']['translator']['engine']['api_key'], '********')
        self.assertIn('api_key=********', form['form_values']['translator']['engine']['url'])
        self.assertIn('model=x', form['form_values']['translator']['engine']['url'])
        self.assertEqual(form['form_values']['crawler']['cookies']['javdb'], '********')
        # Non-secret settings stay visible so operators can understand a preset.
        self.assertEqual(presets['yaml-secret']['form_values']['network']['retry'], 5)
        self.assertEqual(yaml.safe_load(presets['yaml-secret']['content'])['translator']['engine']['name'], 'baidu')
        # Inherited global config secrets are masked as well.
        self.assertEqual(presets['yaml-secret']['form_values']['network']['proxy_server'], 'socks5://********@127.0.0.1:1080')

    def test_operator_cannot_read_raw_config_or_crawler_source(self):
        self.as_role('operator')
        self.assertEqual(self.client.get('/api/config').status_code, 403)
        self.assertEqual(self.client.get('/api/crawler-config/javbus').status_code, 403)
        names = self.client.get('/api/crawler-config/names')
        self.assertEqual(names.status_code, 200)
        self.assertNotIn('source', json.dumps(names.json()))

    def test_operator_convert_does_not_reveal_base_config(self):
        self.as_role('operator')
        reply = self.client.post('/api/presets/convert', json={'mode': 'yaml', 'content': 'network:\n  retry: 4\n'})
        self.assertEqual(reply.status_code, 200)
        self.assert_no_secret(reply.text)
        self.assertEqual(reply.json()['form']['network']['retry'], 4)
        reply = self.client.post('/api/presets/convert', json={'mode': 'form', 'form': {'network': {'retry': 3}}})
        self.assertEqual(reply.status_code, 200)
        self.assert_no_secret(reply.text)

    def test_operator_cannot_write_presets_or_config(self):
        self.as_role('operator')
        self.assertEqual(self.client.put('/api/config', json={'content': 'a: 1'}).status_code, 403)
        self.assertEqual(self.client.post('/api/presets', json={'name': 'x', 'mode': 'form', 'form': {}}).status_code, 403)

    def test_admin_still_reads_full_configuration(self):
        self.as_role('admin')
        presets = self.client.get('/api/presets')
        self.assertIn('sk-translate-9911', presets.text)
        self.assertIn('proxy-pass-7731', presets.text)
        self.assertNotIn('redacted', presets.text)
        config = self.client.get('/api/config')
        self.assertEqual(config.status_code, 200)
        self.assertIn('global-pass-8842', config.text)
        self.assertEqual(self.client.get('/api/crawler-config/javbus').status_code, 200)

    def test_redaction_helpers(self):
        value = {'cookies': {'a': ['x', {'b': 'y'}]}, 'enabled': True, 'token': None, 'password': '', 'retry': 3}
        self.assertEqual(server._redact_config(value), {'cookies': {'a': ['********', {'b': '********'}]}, 'enabled': True,
                                                       'token': None, 'password': '', 'retry': 3})
        self.assertEqual(server._redacted_yaml('not: [valid'), '')
        self.assertEqual(server._redacted_yaml('- list'), '')


if __name__ == '__main__':
    unittest.main()
