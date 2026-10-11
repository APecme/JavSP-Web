"""Offline coverage of shared AI translation settings and the scrape pipeline."""
import ast
import copy
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp.config import Translator
from javsp.datatype import MovieInfo
from javsp.web import translate as translator
from javsp_web import ai, ai_skills, ai_translate, storage, tasks


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.config = ai.AISettings(enabled=True, search_enabled=False,
                                    base_url='https://llm.test/v1', model='translation-model',
                                    api_key='private-translation-key', system_prompt='CHAT ONLY PROMPT').model_dump()
        self.enterContext(patch.object(ai, 'settings', return_value=self.config))
        self.skill = self.enterContext(patch.object(ai_skills, 'read', return_value={'source': 'Translation skill marker'}))
        self.complete = self.enterContext(patch.object(ai, 'complete', return_value={
            'role': 'assistant', 'content': json.dumps({'title': '演员A 在 TEST-001 的旅途', 'plot': '旅途简介'})}))
        self.fields = SimpleNamespace(title=True, plot=True)
        self.info = MovieInfo('TEST-001')
        self.info.title = '演员A in TEST-001 on a journey'
        self.info.plot = 'A journey synopsis'
        self.info.actress = ['演员A', 'Absent Actor']

    def test_translation_uses_shared_ai_switch_selected_fields_and_skill_without_search(self):
        ai_translate.translate_movie(self.info, self.fields)
        self.assertEqual(self.info.title, '演员A 在 TEST-001 的旅途')
        self.assertEqual(self.info.plot, '旅途简介')
        self.assertEqual(self.info.ori_title, '演员A in TEST-001 on a journey')
        self.assertEqual(self.info.ori_plot, 'A journey synopsis')
        self.skill.assert_called_once_with('javsp-translate')
        config, messages = self.complete.call_args.args
        self.assertTrue(config['enabled'])
        self.assertFalse(config['search_enabled'])
        self.assertEqual(len(self.complete.call_args.args), 2)
        self.assertIn('Translation skill marker', messages[0]['content'])
        self.assertNotIn('CHAT ONLY PROMPT', messages[0]['content'])
        payload = json.loads(messages[1]['content'])
        self.assertEqual(payload['target_language'], 'zh-CN')
        self.assertEqual(set(payload['fields']), {'title', 'plot'})
        self.assertEqual(payload['identifier'], 'TEST-001')

    def test_field_selection_preserves_unselected_fields(self):
        self.fields.plot = False
        self.complete.return_value['content'] = json.dumps({'title': '演员A 在 TEST-001 的旅途'})
        ai_translate.translate_movie(self.info, self.fields)
        self.assertEqual(self.info.plot, 'A journey synopsis')
        self.assertFalse(hasattr(self.info, 'ori_plot'))
        self.assertEqual(set(json.loads(self.complete.call_args.args[1][1]['content'])['fields']), {'title'})

    def test_empty_unselected_and_previously_translated_fields_do_not_call_ai(self):
        for title, plot, fields, existing in (
            ('', None, self.fields, False),
            ('Title', 'Plot', SimpleNamespace(title=False, plot=False), False),
            ('Title', 'Plot', self.fields, True),
        ):
            with self.subTest(title=title, existing=existing):
                self.info.title, self.info.plot = title, plot
                if existing:
                    self.info.ori_title, self.info.ori_plot = 'Original title', 'Original plot'
                ai_translate.translate_movie(self.info, fields)
        self.complete.assert_not_called()
        self.skill.assert_not_called()

    def test_invalid_response_never_partially_changes_metadata_or_echoes_response(self):
        responses = [
            '', 'not json private-translation-key', '[]', '{}', '{"title":"valid"}',
            '{"title":"valid","plot":null}', '{"title":"valid","plot":"   "}',
            '{"title":"valid","plot":4}', '{"title":"valid","plot":"valid","extra":"bad"}',
            '{"title":"one","title":"two","plot":"valid"}',
            '```json\n{"title":"valid","plot":"valid"}\n```',
        ]
        before = copy.deepcopy(vars(self.info))
        for content in responses:
            with self.subTest(content=content):
                self.complete.return_value = {'content': content}
                with self.assertRaises(ai.AIError) as caught:
                    ai_translate.translate_movie(self.info, self.fields)
                self.assertEqual(vars(self.info), before)
                self.assertNotIn('private-translation-key', str(caught.exception))
        self.complete.return_value = {'content': json.dumps({'title': 'valid', 'plot': 'valid'}),
                                      'tool_calls': [{'function': {'name': 'unexpected'}}]}
        with self.assertRaisesRegex(ai.AIError, '工具调用'):
            ai_translate.translate_movie(self.info, self.fields)
        self.assertEqual(vars(self.info), before)

    def test_original_actor_and_identifier_are_preserved_only_when_present(self):
        for title in ('演员B 在 TEST-001 的旅途', '演员A 在 TEST-002 的旅途'):
            with self.subTest(title=title):
                self.complete.return_value['content'] = json.dumps({'title': title, 'plot': '旅途简介'})
                with self.assertRaisesRegex(ai.AIError, '演员名或番号'):
                    ai_translate.translate_movie(self.info, self.fields)
                self.assertIsNone(self.info.ori_title)
                self.assertFalse(hasattr(self.info, 'ori_plot'))
        self.info.title = 'A journey'
        self.complete.return_value['content'] = json.dumps({'title': '一次旅途', 'plot': '旅途简介'})
        ai_translate.translate_movie(self.info, self.fields)
        self.assertEqual(self.info.title, '一次旅途')

    def test_actor_protection_ignores_ambiguous_characters_and_latin_substrings(self):
        for actor, source, translated in (
            ('優', '女優の旅', '演员的旅途'),
            ('Ann', 'Annual journey', '每年的旅途'),
            ('Ann', 'Ann visits the city', 'Ann的城市之旅'),
            ('Chloé', 'Chloé visits the city', 'Chloé的城市之旅'),
        ):
            with self.subTest(actor=actor, source=source):
                info = MovieInfo('TEST-001')
                info.title, info.actress = source, [actor]
                self.complete.return_value['content'] = json.dumps({'title': translated})
                ai_translate.translate_movie(info, self.fields)
                self.assertEqual(info.title, translated)
        for actor, source, translated in (
            ('Ann', 'Ann visits the city', 'Anna的城市之旅'),
            ('Chloé', 'Chloé visits the city', '城市之旅'),
            ('山田優', '山田優の旅', '演员的旅途'),
        ):
            with self.subTest(actor=actor, source=source):
                info = MovieInfo('TEST-001')
                info.title, info.actress = source, [actor]
                self.complete.return_value['content'] = json.dumps({'title': translated})
                with self.assertRaisesRegex(ai.AIError, '演员名或番号'):
                    ai_translate.translate_movie(info, self.fields)
                self.assertIsNone(info.ori_title)

    def test_missing_skill_and_provider_errors_stop_before_metadata_changes(self):
        self.skill.side_effect = ai.AIError('Skill 不存在或已删除')
        with self.assertRaisesRegex(ai.AIError, 'javsp-translate.*恢复'):
            ai_translate.translate_movie(self.info, self.fields)
        self.complete.assert_not_called()
        self.skill.side_effect = None
        self.complete.side_effect = ai.AIError('LLM 请求超时，请检查网络或增加超时时间')
        with self.assertRaisesRegex(ai.AIError, '超时'):
            ai_translate.translate_movie(self.info, self.fields)
        self.assertIsNone(self.info.ori_title)
        self.assertFalse(hasattr(self.info, 'ori_plot'))

    def test_disabled_global_switch_never_calls_skill_or_llm(self):
        self.config['enabled'] = False
        self.config['translation_enabled'] = True
        with self.assertRaisesRegex(ai.AIError, '未启用 AI 刮削'):
            ai_translate.translate_movie(self.info, self.fields)
        self.skill.assert_not_called()
        self.complete.assert_not_called()

    def test_ai_selection_never_falls_back_to_existing_engine(self):
        config = SimpleNamespace(translator=SimpleNamespace(ai_enabled=True, engine='existing', fields=self.fields))
        with patch.object(translator, 'Cfg', return_value=config), patch.object(translator, 'translate', return_value={'trans': 'Legacy'}) as legacy:
            self.assertTrue(translator.translate_movie_info(self.info))
            legacy.assert_not_called()
            self.config['enabled'] = False
            self.info = MovieInfo('TEST-002')
            self.info.title, self.info.plot = 'Title', 'Plot'
            with self.assertRaisesRegex(ValueError, 'AI 翻译失败.*未启用 AI 刮削'):
                translator.translate_movie_info(self.info)
            legacy.assert_not_called()
            self.assertEqual(self.info.title, 'Title')
            self.assertTrue(config.translator.ai_enabled)
            config.translator.ai_enabled = False
            self.assertTrue(translator.translate_movie_info(self.info))
            self.assertEqual(legacy.call_count, 2)
            self.assertEqual(self.info.title, 'Legacy')

    def test_global_disable_with_null_engine_reports_unavailable_ai(self):
        self.config['enabled'] = False
        config = SimpleNamespace(translator=SimpleNamespace(ai_enabled=True, engine=None, fields=self.fields))
        before = copy.deepcopy(vars(self.info))
        with patch.object(translator, 'Cfg', return_value=config):
            with self.assertRaisesRegex(ValueError, 'AI 翻译失败.*未启用 AI 刮削'):
                translator.translate_movie_info(self.info)
        self.assertEqual(vars(self.info), before)
        self.assertTrue(config.translator.ai_enabled)
        self.complete.assert_not_called()

    def test_legacy_configs_need_no_web_ai_import_and_null_engine_stays_disabled(self):
        # The ordinary JavSP path must not acquire a web dependency.
        config = SimpleNamespace(translator=SimpleNamespace(engine=None, fields=self.fields))
        with patch.object(translator, 'Cfg', return_value=config), patch.object(ai_translate, 'enabled') as enabled:
            self.assertTrue(translator.translate_movie_info(self.info))
        enabled.assert_not_called()
        self.complete.assert_not_called()
        parsed = Translator.model_validate({'engine': None, 'fields': {'title': True, 'plot': True}})
        self.assertFalse(parsed.ai_enabled)

    def test_ai_failure_is_an_actionable_task_failure(self):
        config = SimpleNamespace(translator=SimpleNamespace(ai_enabled=True, engine='existing', fields=self.fields))
        self.complete.side_effect = ai.AIError('AI 翻译未返回所需字段的有效 JSON 译文，未应用结果')
        with patch.object(translator, 'Cfg', return_value=config), patch.object(translator, 'translate') as legacy:
            with self.assertRaisesRegex(ValueError, 'AI 翻译失败.*未应用结果'):
                translator.translate_movie_info(self.info)
            legacy.assert_not_called()
        self.assertIsNone(self.info.ori_title)

    def test_ai_mode_does_not_load_inactive_engine_settings(self):
        source = {'ai_enabled': True, 'engine': {'name': 'openai', 'url': ''},
                  'fields': {'title': True, 'plot': False}}
        parsed = Translator.model_validate(source)
        self.assertIsNone(parsed.engine)
        self.assertEqual(source['engine'], {'name': 'openai', 'url': ''})
        with self.assertRaises(ValidationError):
            Translator.model_validate({**source, 'ai_enabled': False})


class TranslationProviderErrorTests(unittest.TestCase):
    def test_failure_guidance_matches_requested_model_capability(self):
        config = ai.AISettings(base_url='https://llm.test/v1', model='model').model_dump()
        definition = {'type': 'function', 'function': {'name': 'test', 'parameters': {'type': 'object'}}}
        for tools, expected in ((None, '文本生成'), ([definition], '工具调用')):
            for status in (200, 500):
                with self.subTest(tools=bool(tools), status=status):
                    response = Mock(status_code=status)
                    response.iter_content.return_value = [b'{"error":"private-key"}']
                    context = Mock(__enter__=Mock(return_value=response), __exit__=Mock(return_value=False))
                    with patch.object(ai.requests, 'post', return_value=context), self.assertRaises(ai.AIError) as caught:
                        ai.complete(config, [{'role': 'user', 'content': 'test'}], tools)
                    self.assertIn(expected, str(caught.exception))
                    self.assertNotIn('private-key', str(caught.exception))
                    if tools is None:
                        self.assertNotIn('工具调用', str(caught.exception))


class TranslationSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        with patch('threading.Thread.start'), patch.object(tasks, 'recover_interrupted_tasks'):
            from javsp_web import server
        self.server = server
        self.user = {'username': 'translation-admin', 'role': 'admin'}
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: self.user}))
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)

    def test_shared_ai_enablement_and_runtime_with_masked_secret(self):
        storage._write_json(storage.DATA_DIR / 'ai-settings.json', {'enabled': False})
        self.assertNotIn('translation_enabled', self.client.get('/api/ai/settings').json())
        response = self.client.put('/api/ai/settings', json={'enabled': True})
        self.assertEqual(response.status_code, 400)
        self.assertIn('模型 API 地址', response.text)
        response = self.client.put('/api/ai/settings', json={
            'enabled': True, 'provider': 'openai',
            'base_url': 'https://llm.test/v1', 'model': 'model', 'api_key': 'translation-secret'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('translation_enabled', response.json())
        self.assertTrue(response.json()['enabled'])
        self.assertTrue(ai_translate.enabled())
        self.assertTrue(response.json()['has_api_key'])
        self.assertNotIn('translation-secret', response.text)
        self.assertEqual(ai.settings(True)['api_key'], 'translation-secret')
        response = self.client.get('/api/runtime')
        self.assertNotIn('ai_translation_enabled', response.json())
        self.assertTrue(response.json()['ai_enabled'])
        self.client.put('/api/ai/settings', json={'model': 'changed'})
        self.assertTrue(ai.settings()['enabled'])

    def test_preset_keeps_inactive_engine_and_validates_only_when_selected(self):
        engine = {'name': 'openai', 'url': '', 'model': 'saved-model'}
        response = self.client.post('/api/presets', json={
            'name': 'AI only', 'mode': 'form',
            'form': {'translator': {'ai_enabled': True, 'engine': engine}}})
        self.assertEqual(response.status_code, 200, response.text)
        saved = next(item for item in self.client.get('/api/presets').json() if item['id'] == response.json()['id'])
        self.assertEqual(saved['form_values']['translator']['engine']['model'], 'saved-model')
        response = self.client.put('/api/presets/' + saved['id'], json={
            'name': 'AI only', 'mode': 'form',
            'form': {'translator': {'ai_enabled': False, 'engine': engine}}})
        self.assertEqual(response.status_code, 400, response.text)

    def test_obsolete_translation_switch_is_ignored_without_enabling_ai(self):
        self.assertNotIn('translation_enabled', ai.AISettings.model_json_schema()['properties'])
        for enabled, obsolete in ((False, True), (True, False)):
            with self.subTest(enabled=enabled, obsolete=obsolete):
                saved = {'enabled': enabled, 'translation_enabled': obsolete,
                         'base_url': 'https://llm.test/v1', 'model': 'old-model', 'api_key': 'saved-secret'}
                storage._write_json(storage.DATA_DIR / 'ai-settings.json', saved)
                self.assertEqual(ai_translate.enabled(), enabled)
                self.assertNotIn('translation_enabled', self.client.get('/api/ai/settings').json())
                response = self.client.put('/api/ai/settings', json={'translation_enabled': not obsolete, 'model': 'updated-model'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['enabled'], enabled)
                self.assertNotIn('translation_enabled', response.json())
                persisted = storage._read_json(storage.DATA_DIR / 'ai-settings.json', {})
                self.assertNotIn('translation_enabled', persisted)
                self.assertEqual(persisted['enabled'], enabled)
                self.assertEqual(persisted['api_key'], 'saved-secret')
        self.assertEqual(self.client.put('/api/ai/settings', json={'unknown_switch': True}).status_code, 422)

    def test_connection_checks_tools_even_when_a_legacy_client_sends_the_obsolete_switch(self):
        for payload in ({'enabled': True}, {'translation_enabled': True, 'enabled': False}):
            with self.subTest(payload=payload):
                with patch.object(ai, 'complete', return_value={'content': '', 'tool_calls': [{'function': {'name': 'connection_test'}}]}) as complete:
                    response = self.client.post('/api/ai/test', json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['tools_supported'])
                self.assertEqual(complete.call_args.args[2][0]['function']['name'], 'connection_test')
                self.assertNotIn('translation_enabled', complete.call_args.args[0])

    def test_real_skill_is_read_each_run_and_deleted_skill_blocks_translation(self):
        ai.save_settings(ai.AISettings(enabled=True, base_url='https://llm.test/v1', model='model'))
        fields = SimpleNamespace(title=True, plot=False)
        def movie():
            info = MovieInfo('TEST-001')
            info.title = 'A journey'
            return info
        with patch.object(ai, 'complete', return_value={'content': '{"title":"旅途"}'}) as complete:
            ai_translate.translate_movie(movie(), fields)
            self.assertIn(ai_skills.read('javsp-translate')['source'], complete.call_args.args[1][0]['content'])
            ai_skills.delete('javsp-translate')
            complete.reset_mock()
            with self.assertRaisesRegex(ai.AIError, 'javsp-translate.*恢复'):
                ai_translate.translate_movie(movie(), fields)
            complete.assert_not_called()
            source = '---\nname: javsp-translate\ndescription: Custom translation rules\n---\nKeep a distinct custom translation marker.\n'
            ai_skills.save(source)
            ai_translate.translate_movie(movie(), fields)
            self.assertIn('distinct custom translation marker', complete.call_args.args[1][0]['content'])


class TranslationPipelineTests(unittest.TestCase):
    def test_ai_translation_without_legacy_engine_runs_and_failure_prevents_output(self):
        config = SimpleNamespace(translator=SimpleNamespace(ai_enabled=True, engine=None),
                                 crawler=SimpleNamespace(selection={'normal': ['test']}),
                                 summarizer=SimpleNamespace(extra_fanarts=SimpleNamespace(enabled=False)))
        movie = SimpleNamespace(files=[], dvdid='TEST-001', cid=None, data_src='normal', info=SimpleNamespace())
        translate = Mock(side_effect=ValueError('AI 翻译失败：译文缺少字段，未应用结果'))
        output = Mock()
        events = []
        namespace = dict(os=os, Cfg=lambda: config, logger=logging.getLogger('translation-test'),
                         tqdm=lambda *args, **kwargs: args[0] if args else Mock(),
                         progress_enabled=lambda: True, progress_event=lambda stage, **values: events.append((stage, values)),
                         parallel_crawler=Mock(return_value={'test': object()}), info_summary=Mock(return_value=True),
                         fallback_media_type_id=lambda: 'normal', translate_movie_info=translate, generate_names=output)
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'RunNormalMode')
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'translation-worker-test', 'exec'), namespace)
        # Even with system AI disabled, the selected translation stage must run
        # and report failure rather than silently skipping it and writing files.
        with patch.object(ai_translate, 'enabled', return_value=False), self.assertRaises(RuntimeError):
            namespace['RunNormalMode']([movie])
        translate.assert_called_once_with(movie.info)
        output.assert_not_called()
        self.assertTrue(any('AI 翻译失败' in values.get('error', '') for _, values in events))


if __name__ == '__main__':
    unittest.main()
