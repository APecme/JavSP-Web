"""User-facing YAML and AI parameter errors stay readable and omit inputs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import yaml

from javsp_web import ai, ai_tools, storage, tasks
from javsp_web.config_validation import yaml_error_message


class ErrorMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('threading.Thread.start'), patch.object(tasks, 'recover_interrupted_tasks'):
            from javsp_web import server
        cls.server = server

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.dict(self.server.app.dependency_overrides, {
            self.server.current_user: lambda: {'username': 'error-test', 'role': 'admin'},
        }))
        self.enterContext(patch.object(self.server, '_base_config', return_value={}))
        self.client = TestClient(self.server.app)
        self.addCleanup(self.client.close)
        self.invalid_yaml = 'translator:\n  fields: [private-test-secret,,]\n'

    def assert_safe(self, message):
        self.assertNotIn('private-test-secret', message)
        self.assertNotIn('Input should', message)
        self.assertNotIn('while parsing', message)

    def test_yaml_write_endpoints_report_coordinates_without_source(self):
        requests = [
            ('POST', '/api/presets/convert', {'mode': 'yaml', 'content': self.invalid_yaml}),
            ('POST', '/api/presets', {'name': '测试预设', 'mode': 'yaml', 'content': self.invalid_yaml}),
            ('PUT', '/api/config', {'content': self.invalid_yaml}),
        ]
        column = self.invalid_yaml.splitlines()[1].index(',,') + 2
        for method, url, payload in requests:
            with self.subTest(url=url):
                response = self.client.request(method, url, json=payload)
                self.assertEqual(response.status_code, 400, response.text)
                detail = response.json()['detail']
                self.assertIn(f'第 2 行，第 {column} 列', detail)
                self.assertIn('请检查缩进、冒号、括号和特殊字符', detail)
                self.assert_safe(detail)

    def test_yaml_form_group_names_are_readable_and_unknown_names_not_echoed(self):
        for section, expected in (('translator', '翻译器的 YAML'), ('private-test-secret', '配置分组的 YAML')):
            with self.subTest(section=section):
                response = self.client.post('/api/presets/convert', json={
                    'mode': 'form', 'form': {section: self.invalid_yaml},
                })
                self.assertEqual(response.status_code, 400, response.text)
                detail = response.json()['detail']
                self.assertIn(expected, detail)
                self.assertIn('第 2 行', detail)
                self.assert_safe(detail)

    def test_config_read_keeps_editor_content_but_sanitizes_parse_error(self):
        with patch.object(self.server, 'read_config', return_value=self.invalid_yaml):
            response = self.client.get('/api/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['content'], self.invalid_yaml)
        self.assert_safe(response.json()['parsed']['_error'])
        self.assertIn('第 2 行', response.json()['parsed']['_error'])

    def test_yaml_errors_without_coordinates_do_not_invent_them(self):
        message = yaml_error_message(yaml.YAMLError('private-test-secret'))
        self.assertEqual(message, 'YAML 格式错误，请检查缩进、冒号、括号和特殊字符。')

    def parameter_error(self, model, values):
        with self.assertRaises(ValidationError) as caught:
            model.model_validate(values)
        message = ai_tools.error_message(caught.exception)
        self.assertTrue(message.startswith('AI 生成的参数不符合要求：'))
        self.assert_safe(message)
        return message

    def test_ai_search_parameter_types_and_bounds_are_translated(self):
        message = self.parameter_error(ai_tools.TaskSearch, {'query': {'private-test-secret': 1}, 'limit': 0})
        self.assertIn('搜索内容：请输入文本', message)
        self.assertIn('返回条数：请输入不小于 1 的数字', message)
        message = self.parameter_error(ai_tools.TaskSearch, {'limit': 31})
        self.assertIn('返回条数：请输入不大于 30 的数字', message)

    def test_ai_action_missing_fields_lists_and_unknown_keys_are_translated(self):
        message = self.parameter_error(ai_tools.PresetChange, {'changes': [], 'private-test-secret': 'private-test-secret'})
        self.assertIn('预设 ID：此项不能为空', message)
        self.assertIn('要修改的配置：请按“配置项: 内容”的形式填写', message)
        self.assertIn('自定义配置项：此配置项不受支持', message)
        message = self.parameter_error(self.server.TaskMetadataBody, {
            'actress': [{'private-test-secret': 'private-test-secret'}], 'apply_to_folder': 'private-test-secret',
        })
        self.assertIn('演员 / 第 1 项：请输入文本', message)
        self.assertIn('同时更新文件夹中的 NFO：请选择是或否', message)

    def test_other_ai_error_categories_keep_existing_behavior(self):
        self.assertEqual(ai_tools.error_message(ai.AIError('预设不存在')), '预设不存在')
        self.assertEqual(ai_tools.error_message(HTTPException(409, '操作已处理')), '操作已处理')
        self.assertEqual(ai_tools.error_message(RuntimeError('private-test-secret')), '工具执行失败，请检查参数及项目日志')


if __name__ == '__main__':
    unittest.main()
