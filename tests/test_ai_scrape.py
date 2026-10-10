import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import ai, ai_scrape


class AIScrapeTests(unittest.TestCase):
    def setUp(self):
        self.config = {'enabled': True, 'provider': 'compatible', 'base_url': 'https://llm.test/v1', 'model': 'demo', 'timeout': 60}
        self.sources = [{'url': 'https://example.test/movie/FNS-262', 'text': 'FNS-262 Verified title Actor 2026-09-01', 'images': ['https://example.test/FNS-262_1200.jpg']}]
        self.fields = {'dvdid': 'FNS-262', 'title': 'Verified title', 'source_url': self.sources[0]['url'], 'cover': self.sources[0]['images'][0], 'actress': ['Actor', 'Invented actor']}
        self.enterContext(patch.object(ai, 'settings', return_value=self.config))
        self.collect = self.enterContext(patch.object(ai_scrape, 'collect_sources', return_value=self.sources))
        self.enterContext(patch.object(ai_scrape, '_public_target', return_value=True))

    def extract(self, fields):
        with patch.object(ai, 'complete', return_value={'role': 'assistant', 'content': json.dumps(fields)}):
            return ai_scrape.lookup('FNS-262', {'https': 'http://proxy.test'})

    def test_verified_extraction_filters_unsupported_optional_fields(self):
        result = self.extract(self.fields | {'director': 'Unknown person'})
        self.assertEqual(result['title'], 'Verified title')
        self.assertEqual(result['actress'], ['Actor'])
        self.assertIsNone(result['director'])
        self.assertEqual(result['url'], self.sources[0]['url'])
        self.collect.assert_called_once_with('FNS-262', {'https': 'http://proxy.test'}, self.config)

    def test_rejects_wrong_identifier_source_title_and_invented_image(self):
        for changed in ({'dvdid': 'FNS-263'}, {'source_url': 'https://other.test'}, {'title': 'Invented title'}, {'cover': 'https://example.test/invented.jpg'}):
            with self.subTest(changed=changed), self.assertRaises(ai.AIError):
                self.extract(self.fields | changed)

    def test_disabled_never_calls_llm_or_search(self):
        self.config['enabled'] = False
        with patch.object(ai, 'complete') as complete, self.assertRaises(ai.AIError):
            ai_scrape.lookup('FNS-262')
        self.collect.assert_not_called()
        complete.assert_not_called()


class SourceTests(unittest.TestCase):
    def test_disabled_search_does_not_make_requests(self):
        with patch.object(ai_scrape, '_fetch') as fetch, self.assertRaises(ai.AIError):
            ai_scrape.search_web('test', config={'search_enabled': False})
        fetch.assert_not_called()

    def test_searxng_parameters_timeout_and_result_limit(self):
        raw = json.dumps({'results': [{'url': 'https://public.test/one', 'title': 'one', 'content': 'first'},
                                      {'url': 'https://public.test/two', 'title': 'two', 'content': 'second'}]}).encode()
        config = {'search_provider': 'searxng', 'search_url': 'http://search.local:8080', 'search_results': 1, 'search_timeout': 7}
        with patch.object(ai_scrape, '_public_target', return_value=True), patch.object(ai_scrape, '_fetch', return_value=('url', raw)) as fetch:
            result = ai_scrape.search_web('query', {'https': 'proxy'}, config)
        self.assertEqual(len(result), 1)
        self.assertIn('/search?q=query&format=json', fetch.call_args.args[0])
        self.assertEqual(fetch.call_args.kwargs, {'timeout': 7, 'trusted_service': True})

    def test_page_and_text_limits_used(self):
        results = [{'url': 'https://example.test/FNS-262', 'title': 'FNS-262', 'snippet': ''}] * 2
        page = ('<html>FNS-262 ' + 'content ' * 500 + '</html>').encode()
        with patch.object(ai_scrape, 'search_web', return_value=results), patch.object(ai_scrape, '_fetch', return_value=(results[0]['url'], page)) as fetch:
            sources = ai_scrape.collect_sources('FNS-262', config={'search_pages': 1, 'search_page_chars': 1000, 'search_timeout': 8})
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(sources[0]['text']), 1000)
        self.assertEqual(fetch.call_args.kwargs['timeout'], 8)

    def test_extract_page_and_lazy_images_from_search_results(self):
        rss = b'<rss><channel><item><title>FNS-262</title><link>https://example.test/FNS-262</link></item></channel></rss>'
        page = b'<html><body><h1>FNS-262 Verified title</h1><img data-src="/FNS-262_1200.jpg"><script>unsafe instructions</script></body></html>'
        with patch.object(ai_scrape, '_public_target', return_value=True), patch.object(ai, 'settings', return_value={}), patch.object(ai_scrape, '_fetch', side_effect=[('https://bing.test', rss), ('https://example.test/FNS-262', page)]):
            result = ai_scrape.collect_sources('FNS-262')
        self.assertEqual(result[0]['images'], ['https://example.test/FNS-262_1200.jpg'])
        self.assertNotIn('unsafe instructions', result[0]['text'])

    def test_private_redirect_is_blocked(self):
        response = Mock()
        response.is_redirect = True
        response.headers = {'Location': 'http://127.0.0.1/private'}
        context = Mock(__enter__=Mock(return_value=response), __exit__=Mock(return_value=False))
        with patch.object(ai_scrape, '_public_target', side_effect=[True, False]), patch.object(ai_scrape.requests, 'get', return_value=context) as get:
            with self.assertRaises(ai.AIError):
                ai_scrape._fetch('https://public.test', {})
            self.assertEqual(get.call_count, 1)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_private_and_credential_urls_rejected(self):
        for url in ('http://user:pass@example.com', 'http://127.0.0.1:8080/', 'file:///etc/passwd'):
            with self.subTest(url=url):
                self.assertFalse(ai_scrape._public_target(url))
        with patch.object(ai_scrape.socket, 'getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 80))]):
            self.assertFalse(ai_scrape._public_target('https://example.test'))


class WorkerSelectionTests(unittest.TestCase):
    def run_selection(self, enabled, fallback, source_info, globally_enabled=True, ai_error=None):
        movie = SimpleNamespace(files=[], dvdid='TEST-001', cid=None, data_src='normal')
        config = SimpleNamespace(crawler=SimpleNamespace(ai_enabled=enabled, ai_fallback_only=fallback, required_keys=['title', 'cover'], selection={'normal': ['site']}),
                                 translator=SimpleNamespace(engine=None), summarizer=SimpleNamespace(extra_fanarts=SimpleNamespace(enabled=False)))
        summary = Mock(return_value=False)
        crawler = Mock(return_value=source_info)
        events = []
        namespace = dict(Cfg=lambda: config, logger=Mock(), tqdm=lambda *args, **kwargs: args[0] if args else Mock(),
                         progress_enabled=lambda: True, progress_event=lambda stage, **values: events.append((stage, values)),
                         parallel_crawler=crawler, info_summary=summary, fallback_media_type_id=lambda: 'normal', read_proxy=lambda: {})
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'RunNormalMode')
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'ai-worker-test', 'exec'), namespace)
        with patch.object(ai_scrape, 'enabled', return_value=globally_enabled), patch.object(ai_scrape, 'scrape_movie', return_value=SimpleNamespace(title='Title', cover='https://cover.test'), side_effect=ai_error) as scrape:
            with self.assertRaises(RuntimeError):
                namespace['RunNormalMode']([movie])
        return crawler, scrape, summary, events

    def test_direct_ai_skips_crawlers(self):
        crawler, scrape, summary, _ = self.run_selection(True, False, {})
        crawler.assert_not_called()
        scrape.assert_called_once()
        self.assertIn('ai', summary.call_args.args[1])

    def test_fallback_runs_on_empty_or_missing_required_data(self):
        for info in ({}, {'site': SimpleNamespace(title='Title', cover=None)}):
            with self.subTest(info=info):
                crawler, scrape, summary, _ = self.run_selection(True, True, info)
                crawler.assert_called_once()
                scrape.assert_called_once()
                self.assertIn('ai', summary.call_args.args[1])

    def test_success_or_disabled_ai_keeps_normal_path(self):
        info = {'site': SimpleNamespace(title='Title', cover='https://cover.test')}
        for enabled, fallback, global_enabled in ((True, True, True), (False, True, True), (True, False, False)):
            with self.subTest(enabled=enabled, fallback=fallback, global_enabled=global_enabled):
                crawler, scrape, _, _ = self.run_selection(enabled, fallback, info, global_enabled)
                crawler.assert_called_once()
                scrape.assert_not_called()

    def test_ai_failure_has_explicit_event_and_no_summary(self):
        _, _, summary, events = self.run_selection(True, True, {}, ai_error=ai.AIError('没有有效来源'))
        summary.assert_not_called()
        self.assertTrue(any(stage == 'crawler' and values.get('status') == 'failed' and values.get('name') == 'AI 刮削' for stage, values in events))
        self.assertTrue(any('没有有效来源' in values.get('error', '') for stage, values in events))


if __name__ == '__main__':
    unittest.main()
