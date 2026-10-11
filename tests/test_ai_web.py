import json
import socket
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import requests

from javsp_web import ai, ai_web, config_validation, storage


class WebPageTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(ai, 'settings', return_value={'enabled': True, 'search_enabled': True, 'search_timeout': 10}))
        self.enterContext(patch.object(config_validation, 'load_base_config', return_value={'network': {'proxy_server': 'http://proxy.test:8080'}}))
        self.enterContext(patch.object(storage, 'get_cookiecloud_settings', return_value={'enabled': True}))
        self.sync = self.enterContext(patch.object(ai_web, 'fetch_cookiecloud', return_value={
            'example.com': {'session': 'private-login-value'}, 'other.test': {'session': 'other-login-value'}}))
        self.dns = self.enterContext(patch.object(ai_web.socket, 'getaddrinfo', return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]))
        self.fetch = self.enterContext(patch.object(ai_web, '_request', return_value=(200, '', b'<html><title>Test</title><p>Page</p></html>', None)))

    def test_gbk_html_structure_images_and_cookie_redaction(self):
        body = '''<html><head><meta charset="gbk"><title>测试页面</title></head><body>
        <script>private-script</script><form><input type="password" value="form-secret"></form>
        <meta name="csrf-token" content="meta-secret"><!-- comment-secret -->
        <div id="content" onclick="alert(1)">正文 private-login-value
        <a href="/thread/123">帖子</a><img data-src="/cover.jpg"></div></body></html>'''
        self.fetch.return_value = (200, '', body.encode('gbk'), None)
        result = ai_web.read_webpage('https://example.com/search')
        self.assertEqual(result['title'], '测试页面')
        self.assertIn('id="content"', result['html'])
        self.assertEqual(result['links'][0]['url'], 'https://example.com/thread/123')
        self.assertEqual(result['images'], ['https://example.com/cover.jpg'])
        serialized = json.dumps(result, ensure_ascii=False)
        for secret in ('private-login-value', 'form-secret', 'private-script', 'meta-secret', 'comment-secret', 'onclick'):
            self.assertNotIn(secret, serialized)
        self.assertTrue(result['authentication_used'])
        self.assertIn('登录表单', result['notice'])
        self.assertEqual(self.fetch.call_args.args[4], {'session': 'private-login-value'})
        self.assertEqual(self.fetch.call_args.args[3]['https'], 'http://proxy.test:8080')

    def test_redirects_reselect_cookies_and_reject_private_destination(self):
        self.fetch.side_effect = [(302, 'https://unrelated.test/page', b'', None), (200, '', b'<p>Public</p>', None)]
        self.assertFalse(ai_web.read_webpage('https://example.com')['authentication_used'])
        self.assertEqual(self.fetch.call_args.args[4], {})
        self.fetch.reset_mock()
        self.fetch.side_effect = None
        self.fetch.return_value = (302, 'http://127.0.0.1/admin', b'', None)
        public = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        private = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))
        self.dns.side_effect = [[public], [private]]
        with self.assertRaisesRegex(ai.AIError, '内网'):
            ai_web.read_webpage('https://example.com')
        self.fetch.assert_called_once()

    def test_disabled_network_and_invalid_addresses_do_not_sync_or_fetch(self):
        with patch.object(ai, 'settings', return_value={'enabled': True, 'search_enabled': False}):
            with self.assertRaisesRegex(ai.AIError, '联网搜索'):
                ai_web.read_webpage('https://example.com')
        for url in ('file:///tmp/config', 'https://user:password@example.com', 'https://example.com:8090'):
            with self.assertRaises(ai.AIError):
                ai_web.read_webpage(url)
        self.sync.assert_not_called()
        self.fetch.assert_not_called()

    def test_cookie_opt_out_and_http_never_send_login_information(self):
        ai_web.read_webpage('https://example.com', use_cookiecloud=False)
        self.sync.assert_not_called()
        self.assertEqual(self.fetch.call_args.args[4], {})
        ai_web.read_webpage('http://example.com')
        self.assertEqual(self.fetch.call_args.args[4], {})

    def test_long_html_paging_and_xpath(self):
        body = '<html><body><nav>' + 'x' * 10000 + '</nav><article id="post">Target</article></body></html>'
        self.fetch.return_value = (200, '', body.encode(), None)
        first = ai_web.read_webpage('https://example.com')
        second = ai_web.read_webpage('https://example.com', offset=first['next_offset'])
        self.assertTrue(first['truncated'])
        self.assertFalse(second['truncated'])
        self.assertIn('Target', second['html'])
        selected = ai_web.read_webpage('https://example.com', selector='//*[@id="post"]')
        self.assertEqual(selected['html'], '<article id="post">Target</article>')
        with self.assertRaisesRegex(ai.AIError, 'XPath'):
            ai_web.read_webpage('https://example.com', selector='string(//article)')

    def test_result_budget_preserves_pagination(self):
        body = '<html><body>' + ''.join('<a href="https://example.com/' + 'x' * 750 + '">Link</a>' for _ in range(40)) + '</body></html>'
        self.fetch.return_value = (200, '', body.encode(), None)
        result = ai_web.read_webpage('https://example.com')
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 22000)
        self.assertIsNotNone(result['next_offset'])

    def test_transport_pins_ip_and_keeps_host_and_tls_name(self):
        # Exercise the real transport setup without a live request.
        with patch.object(ai_web, '_read_response', return_value=(200, '', b'page', None)) as read:
            with requests.Session() as session:
                with patch.object(ai_web.requests, 'Session', return_value=session):
                    ORIGINAL_REQUEST('https://example.com/page', urlsplit('https://example.com/page'), '93.184.216.34', {}, {}, 10)
                self.assertFalse(session.trust_env)
                adapter = session.get_adapter('https://example.com')
                self.assertEqual(adapter.poolmanager.connection_pool_kw['assert_hostname'], 'example.com')
                self.assertEqual(adapter.poolmanager.connection_pool_kw['server_hostname'], 'example.com')
                self.assertEqual(read.call_args.args[1], 'https://93.184.216.34/page')

    def test_transport_rejects_binary_oversized_and_auth_errors(self):
        for status, content_type, chunks, expected in (
            (403, 'text/html', [], '拒绝访问'),
            (200, 'image/jpeg', [], '不是 HTML'),
            (200, 'text/html', [b'x' * (ai_web.MAX_BYTES + 1)], '过大'),
        ):
            response = MagicMock(status_code=status, is_redirect=False, headers={'Content-Type': content_type})
            response.__enter__.return_value = response
            response.iter_content.return_value = iter(chunks)
            session = MagicMock()
            session.get.return_value = response
            with self.assertRaisesRegex(ai.AIError, expected):
                ai_web._read_response(session, 'https://93.184.216.34', urlsplit('https://example.com'), {}, {}, 10)
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            self.assertTrue(session.get.call_args.kwargs['stream'])
            self.assertEqual(session.get.call_args.kwargs['headers']['Host'], 'example.com')


ORIGINAL_REQUEST = ai_web._request

if __name__ == '__main__':
    unittest.main()
