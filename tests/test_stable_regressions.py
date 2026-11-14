import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor/JavSP')]
from javsp.config import Cfg, OpenAITranslateEngine
from javsp.datatype import Movie, MovieInfo
from javsp.web import translate as tr
from javsp_web import tasks

class StableRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = yaml.safe_load((ROOT / 'vendor/JavSP/config.yml').read_text(encoding='utf-8'))
        self.data['scanner']['minimum_size'] = 0
        self.data['scanner']['skip_nfo_dir'] = False

    def file(self, name):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'video content')
        return p

    def test_scan_ignores_nested_output_and_ignored_root(self):
        good = self.file('incoming/ABC-123.mp4')
        bad = self.file('incoming/#整理完成/actor/DEF-456.mp4')
        with patch.object(tasks, '_preset_config_data', return_value=(self.data, {})), patch.object(tasks, 'create_task', side_effect=lambda path, *a, **kw: {'path': path, 'input_directory': path}):
            found = tasks._prepare_tasks(str(good.parent), 'default')
            self.assertEqual([t['path'] for t in found], [str(good)])
            with self.assertRaises(tasks.NoScrapeTasksError):
                tasks._prepare_tasks(str(bad.parent), 'default')

    def test_scan_skip_nfo_and_empty_ignore_patterns(self):
        good = self.file('input/ABC-123.mp4')
        bad = self.file('input/done/DEF-456.mp4')
        bad.with_suffix('.nfo').write_text('<movie/>')
        self.data['scanner'].update(skip_nfo_dir=True, ignored_folder_name_pattern=[])
        with patch.object(tasks, '_preset_config_data', return_value=(self.data, {})), patch.object(tasks, 'create_task', side_effect=lambda path, *a, **kw: {'path': path, 'input_directory': path}):
            self.assertEqual([t['path'] for t in tasks._prepare_tasks(str(good.parent), 'default')], [str(good)])

    def test_openai_prompt_temperature_and_repetition_guard(self):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'message': {'content': '正常中文标题'}, 'finish_reason': 'stop'}]}
        with patch.object(tr.requests, 'post', return_value=response) as post:
            self.assertEqual(tr.openai_translate('日本語タイトル', 'https://example.test', 'key', 'model'), '正常中文标题')
            self.assertEqual(post.call_args.kwargs['json']['temperature'], 0.1)
            self.assertIn('翻译', post.call_args.kwargs['json']['messages'][0]['content'])
            response.json.return_value['choices'][0]['message']['content'] = '嗯，我明白了。\n' + '……\n' * 100
            result = tr.openai_translate('日本語タイトル', 'https://example.test', 'key', 'model')
            self.assertIsInstance(result, dict)
            self.assertIn('error_code', result)

    def test_invalid_title_falls_back_without_changing_original(self):
        engine = OpenAITranslateEngine(name='openai', url='https://example.test', api_key='key', model='sakura')
        self.data['translator'].update(engine=engine.model_dump(mode='json'), fields={'title': True, 'plot': False})
        info = MovieInfo('ABC-123'); info.title = '日本語タイトル'
        with patch.object(tr, 'Cfg', return_value=Cfg.model_validate(self.data)), patch.object(tr, 'openai_translate', return_value={'error_code': 'invalid_translation', 'error_msg': '重复文本'}):
            self.assertTrue(tr.translate_movie_info(info))
            self.assertEqual(info.title, '日本語タイトル')
            self.assertIsNone(info.ori_title)

    def test_symlink_creation_rerun_and_source_preserved(self):
        source = self.file('source/ABC-123.mp4')
        out = self.root / 'output'; out.mkdir()
        m = Movie('ABC-123'); m.files = [str(source)]; m.save_dir = str(out); m.basename = 'ABC-123'
        try:
            m.rename_files(use_symlink=True)
        except OSError as exc:
            if getattr(exc.__cause__, 'winerror', None) == 1314:
                self.skipTest('Windows process lacks symlink privilege; real links tested in Linux container')
            raise
        target = out / source.name
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.read_bytes(), source.read_bytes())
        m.rename_files(use_symlink=True)
        self.assertTrue(source.is_file())

    def test_symlink_rollback_preserves_sources(self):
        paths = [self.file('source/ABC-123-1.mp4'), self.file('source/ABC-123-2.mp4')]
        out = self.root / 'output'; out.mkdir()
        m = Movie('ABC-123'); m.files = list(map(str, paths)); m.save_dir = str(out); m.basename = 'ABC-123'
        real = os.link if os.name == 'nt' else os.symlink
        def link(src, dst):
            if src == str(paths[1]): raise OSError('simulated link failure')
            real(src, dst)
        with patch('javsp.datatype.os.symlink', side_effect=link), self.assertRaises(OSError):
            m.rename_files(use_symlink=True)
        self.assertTrue(all(p.exists() for p in paths))
        self.assertEqual(list(out.iterdir()), [])

    def test_symlink_config_exclusive(self):
        self.data['summarizer']['path'].update(soft_link=True, hard_link=True)
        with self.assertRaises(ValueError): Cfg.model_validate(self.data)

    def test_output_directory_idempotent_and_absolute_override(self):
        from javsp.organization import output_directory
        source = self.file('incoming/#整理完成/演员/[ABC-123] 旧标题/ABC-123.mp4')
        pattern = '#整理完成/{actress}/[{num}] {title}'
        formatted = '#整理完成/演员/[ABC-123] 新标题'
        self.assertEqual(Path(output_directory(str(source), formatted, pattern, 'ABC-123')), source.parent)
        self.assertEqual(output_directory(str(source), str(self.root / 'explicit'), pattern, 'ABC-123'), str(self.root / 'explicit'))
        truncated = self.file('incoming/#整理完成/演员/[ABC-123]/ABC-123.mp4')
        self.assertEqual(Path(output_directory(str(truncated), formatted, pattern, 'ABC-123')), truncated.parent)
        normalized = self.file('incoming/output/ABC-123/ABC-123.mp4')
        self.assertEqual(Path(output_directory(str(normalized), 'output/ABC-123', './output/{num}', 'ABC-123')), normalized.parent)
        fresh = self.file('fresh/ABC-123.mp4')
        self.assertEqual(output_directory(str(fresh), formatted, pattern, 'ABC-123'), formatted)

    def test_claude_translation_remains_compatible(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'content': [{'text': '译文'}]}
        with patch.object(tr.requests, 'post', return_value=reply):
            self.assertEqual(tr.claude_translate('原文', 'key'), '译文')

    def test_openai_rejects_empty_truncated_long_and_nonstring_responses(self):
        reply = Mock(status_code=200)
        with patch.object(tr.requests, 'post', return_value=reply):
            for text, finish in [('', 'stop'), ('正常但截断', 'length'), ('长' * 500, 'stop'), (None, 'stop'), ('a\nb\nc\nd', 'stop')]:
                reply.json.return_value = {'choices': [{'message': {'content': text}, 'finish_reason': finish}]}
                self.assertEqual(tr.openai_translate('短标题', 'https://example.test', 'key', 'model', field='title')['error_code'], 'invalid_translation')

    def test_openai_config_temperature_bounds_and_forwarding(self):
        for invalid in [-0.1, 2.1, float('nan')]:
            with self.assertRaises(ValueError):
                OpenAITranslateEngine(name='openai', url='https://example.test', api_key='key', model='model', temperature=invalid)
        engine = OpenAITranslateEngine(name='openai', url='https://example.test', api_key='key', model='model', temperature=0)
        with patch.object(tr, 'openai_translate', return_value='译文') as call:
            self.assertEqual(tr.translate('标题', engine, field='title')['trans'], '译文')
            self.assertEqual(call.call_args.kwargs, {'temperature': 0, 'field': 'title'})

    def test_output_matching_nfo_mismatched_nfo_and_other_identifier(self):
        from javsp.organization import output_directory
        source = self.file('organized/ABC-123.mp4')
        nfo = source.with_suffix('.nfo')
        nfo.write_text('<movie><num>ABC-123</num></movie>')
        self.assertEqual(output_directory(str(source), 'new/ABC-123', 'new/{num}', 'ABC-123'), 'new/ABC-123')
        nfo.write_text('<movie><num>XYZ-999</num></movie>')
        self.assertEqual(output_directory(str(source), 'new/ABC-123', 'new/{num}', 'ABC-123'), 'new/ABC-123')
        other = self.file('#整理完成/演员/[XYZ-999] 标题/ABC-123.mp4')
        self.assertEqual(output_directory(str(other), 'new/ABC-123', '#整理完成/{actress}/[{num}] {title}', 'ABC-123'), 'new/ABC-123')

    def test_generate_names_and_three_rescrapes_remain_in_place(self):
        import ast
        import logging
        from javsp.file import replace_illegal_chars, get_remaining_path_len
        source = self.file('incoming/#整理完成/演员/[ABC-123] old/ABC-123.mp4')
        config = Cfg.model_validate(self.data)
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate_names')
        env = dict(Movie=Movie, os=os, Cfg=lambda: config, logging=logging, logger=logging.getLogger('test'),
                   replace_illegal_chars=replace_illegal_chars, get_remaining_path_len=get_remaining_path_len,
                   split_by_punc=lambda text: [text])
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'generate_names', 'exec'), env)
        with patch('javsp.datatype.Cfg', return_value=config), patch('javsp.file.Cfg', return_value=config):
            for i in range(3):
                m = Movie('ABC-123'); m.files = [str(source)]
                m.info = MovieInfo('ABC-123'); m.info.title = f'new title {i}'; m.info.actress=['演员']
                env['generate_names'](m)
                self.assertEqual(Path(m.save_dir), source.parent)
                m.rename_files(policy='always')
                self.assertEqual(list(map(Path, m.new_paths)), [source])
                self.assertTrue(source.is_file())

if __name__ == '__main__': unittest.main()
