"""Readable preset validation errors without changing the underlying rules."""
import copy
from pathlib import Path
import unittest

import yaml

from javsp_web.config_validation import validate_config_data


class ConfigValidationMessagesTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'vendor/JavSP/config.yml'
        self.config = yaml.safe_load(source.read_text(encoding='utf-8'))

    def error(self):
        with self.assertRaises(ValueError) as caught:
            validate_config_data(self.config)
        message = str(caught.exception)
        self.assertNotIn('Input should', message)
        self.assertNotIn('private-test-secret', message)
        return message

    def test_valid_config_is_accepted_without_mutation(self):
        self.config['translator']['fields']['plot'] = False
        original = copy.deepcopy(self.config)
        validate_config_data(self.config)
        self.assertEqual(self.config, original)

    def test_media_type_list_and_boolean_errors_name_the_fields(self):
        self.config['scanner']['media_types'] = 'private-test-secret'
        self.config['translator']['fields']['plot'] = 'private-test-secret'
        message = self.error()
        self.assertIn('扫描器 / 影片分类：请填写列表', message)
        self.assertIn('翻译器 / 翻译字段 / 剧情简介：请选择是或否', message)

    def test_numeric_type_and_bounds_are_explained(self):
        self.config['network']['retry'] = -1
        self.config['summarizer']['path']['length_maximum'] = 0
        self.config['summarizer']['path']['max_actress_count'] = 'private-test-secret'
        message = self.error()
        self.assertIn('重试次数：请输入不小于 0 的数字', message)
        self.assertIn('最大文件路径长度：请输入大于 0 的数字', message)
        self.assertIn('最多包含的演员人数：请输入整数', message)

    def test_field_lengths_ids_and_choices_do_not_echo_values(self):
        self.config['scanner']['media_types'] = [{
            'id': 'private-test-secret', 'name': 'private-test-secret' * 8,
            'detector': 'private-test-secret', 'identifier_kind': 'private-test-secret',
        }]
        self.config['translator']['engine'] = {'name': 'private-test-secret'}
        message = self.error()
        self.assertIn('影片分类 / 第 1 项 / 分类 ID：请以小写字母开头', message)
        self.assertIn('名称：最多填写 80 个字符', message)
        self.assertIn('识别方式：请选择支持的选项', message)
        self.assertIn('编号类型：请选择支持的选项', message)
        self.assertIn('引擎配置：不支持此引擎', message)

    def test_credentials_urls_and_dynamic_dictionary_keys_are_not_echoed(self):
        self.config['translator']['engine'] = {
            'name': 'openai', 'api_key': ['private-test-secret'],
            'url': 'private-test-secret', 'model': 'example-model',
        }
        self.config['network']['proxy_free'] = {'private-test-secret': 'private-test-secret'}
        self.config['network']['proxy_server'] = 'private-test-secret'
        message = self.error()
        self.assertIn('API 密钥：请输入文本', message)
        self.assertIn('接口地址：请输入完整的网址', message)
        self.assertIn('代理服务器：请输入完整的网址，例如 http://127.0.0.1:7890', message)
        self.assertIn('免代理站点 / 自定义配置项', message)

    def test_size_duration_and_required_fields_have_actionable_hints(self):
        self.config['scanner']['minimum_size'] = 'private-test-secret'
        self.config['network']['timeout'] = 'private-test-secret'
        del self.config['translator']['fields']['title']
        message = self.error()
        self.assertIn('最小文件大小：请填写文件大小，例如 232MiB 或 1GB', message)
        self.assertIn('请求超时：请填写有效时长，例如 PT10S 表示 10 秒', message)
        self.assertIn('翻译字段 / 标题：此项不能为空', message)

    def test_existing_custom_media_rules_remain_specific(self):
        self.config['scanner']['media_types'] = []
        self.assertIn('必须且只能保留一个兜底影片分类', self.error())
        self.config['scanner']['media_types'] = [{
            'id': 'custom', 'name': '自定义', 'detector': 'regex',
            'pattern': 'private-test-secret', 'avid_format': '{avid}',
        }]
        self.assertIn('影片分类识别规则必须包含命名捕获组 (?P<avid>...)', self.error())
        self.config['scanner']['media_types'][0]['pattern'] = '(?P<avid>private-test-secret['
        self.assertIn('影片分类规则无效，请检查文件名识别规则和番号格式', self.error())


if __name__ == '__main__':
    unittest.main()
