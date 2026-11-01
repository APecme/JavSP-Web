"""Offline tests: no real sites, credentials, media files or task workers."""
import copy
import io
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from javsp_web import hot, hot_network, hot_router
from javsp_web.auth import current_user
from javsp_web.hot_sources import BY_ID, FEEDS, SOURCES


FALENO = '''<html><title>FALENO</title><body>
<a href="https://ad.invalid/works/ad999/">ad</a>
<a href="/top/works/fns002/"><img alt="Second release"><div class="main_text">2026/10/2 配信開始</div></a>
<a href="/top/works/fns003/"><img alt="New release"><div class="main_text">2026/10/12 配信開始</div></a>
<div class="box_ranking01">
<div class="waku_ranking01"><div class="text_name"><a href="/top/works/fns002/">First in source rank</a></div><div class="text_ranking01"><span>配信日</span><p>2026/10/2</p></div></div>
<div class="waku_ranking01"><div class="text_name"><a href="/top/works/fns001/">Older but second rank</a></div><div class="text_ranking01"><span>配信日</span><p>2025/1/1</p></div></div>
</div></body></html>'''
DAHLIA = '''<html><title>DAHLIA</title><body>
<a href="/works/dldss002/"><img alt="Release"><div class="main_text">2026/10/20 配信開始</div></a>
<div class="ranking-box"><div class="ranking-title"><a href="/works/dldss001/">Ranked release</a></div><div class="ranking-number">1</div></div>
<div class="ranking-box"><div class="ranking-title"><a href="/works/dldss001/">Duplicate mobile</a></div></div>
<div class="ranking-box"><div class="ranking-title"><a href="https://evil.invalid/works/x001/">off-site</a></div></div>
</body></html>'''
FREE = '''<html><title>Latest works</title><body>
<div class="card"><a href="https://ad.invalid">Ad</a></div>
<div class="card"><div class="card-body"><a href="/ja/ABC-123"><h5 class="card-title">ABC-123</h5><p class="card-text">Product title &amp; metadata</p><span class="text-muted">2026-10-02</span></a></div></div>
<div class="card"><div class="card-body"><a href="/ja/XYZ-456"><h5 class="card-title">XYZ-456</h5><p class="card-text">New product</p><span class="text-muted">2026-10-12</span></a></div></div>
<div class="card"><div class="card-body"><a href="https://evil.invalid/ja/EVIL-1"><h5 class="card-title">EVIL-1</h5><p class="card-text">Do not follow</p></a></div></div>
</body></html>'''


class HotTests(unittest.TestCase):
    def setUp(self):
        for name in ('_check', '_checks', '_feed_job', '_cache'):
            self.enterContext(patch.object(hot, name, {}))

    def test_runtime_sources_match_all_thirty_researched_urls(self):
        # Runtime tests must also work in the release image, which deliberately
        # ships application code but not the research documentation directory.
        catalog_path = Path(__file__).resolve().parents[1] / 'docs/hot-sources/catalog.json'
        if catalog_path.is_file():
            catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
            self.assertEqual({s['id']: s['url'] for s in catalog['sources']},
                             {id: url for id, name, url in SOURCES})
        self.assertEqual(len(SOURCES), 30)
        self.assertTrue(all(url.startswith('https://') for _, _, url in SOURCES))
        self.assertEqual(len(BY_ID), 30)
        self.assertEqual(len(FEEDS), 8)

    def test_latest_parsing_sorts_real_dates_not_source_order(self):
        items = hot.parse_feed('faleno', 'censored', 'latest', FALENO, BY_ID['faleno']['url'])
        self.assertEqual([i['identifier'] for i in items], ['FNS-003', 'FNS-002'])
        self.assertTrue(all(i['rank'] is None for i in items))
        self.assertEqual(items[0]['date'], '2026-10-12')
        self.assertNotIn('ad.invalid', str(items))

    def test_hot_preserves_source_order_and_does_not_sort_by_release_date(self):
        items = hot.parse_feed('faleno', 'censored', 'hot', FALENO, BY_ID['faleno']['url'])
        self.assertEqual([i['identifier'] for i in items], ['FNS-002', 'FNS-001'])
        self.assertEqual([i['rank'] for i in items], [1, 2])

    def test_dahlia_deduplicates_mobile_and_blocks_offsite_cards(self):
        items = hot.parse_feed('dahlia', 'censored', 'hot', DAHLIA, BY_ID['dahlia']['url'])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['identifier'], 'DLDSS-001')
        self.assertEqual(items[0]['date'], '')
        self.assertEqual(hot.parse_feed('dahlia', 'censored', 'latest', DAHLIA,
                                       BY_ID['dahlia']['url'])[0]['date'], '2026-10-20')

    def test_freejavbt_uses_product_cards_not_ads_and_source_category(self):
        latest = hot.parse_feed('freejavbt', 'uncensored', 'latest', FREE, BY_ID['freejavbt']['url'])
        ranked = hot.parse_feed('freejavbt', 'uncensored', 'hot', FREE, BY_ID['freejavbt']['url'])
        self.assertEqual([i['identifier'] for i in latest], ['XYZ-456', 'ABC-123'])
        self.assertEqual([i['identifier'] for i in ranked], ['ABC-123', 'XYZ-456'])
        self.assertTrue(all(i['category'] == 'uncensored' for i in latest))
        self.assertNotIn('evil.invalid', str(ranked))

    def test_invalid_date_and_changed_layout_are_not_fake_empty_success(self):
        self.assertEqual(hot._date('2026/99/12'), '')
        with self.assertRaisesRegex(hot_network.NetworkError, '未识别'):
            hot.parse_feed('faleno', 'censored', 'hot', '<html>changed layout</html>', BY_ID['faleno']['url'])

    def test_filters_are_separate_and_get_never_reads_network(self):
        with patch.object(hot, 'read_html') as network:
            self.assertEqual(len(hot.films('all', 'latest')['groups']), 4)
            self.assertEqual(len(hot.films('censored', 'hot')['groups']), 3)
            uncensored = hot.films('uncensored', 'hot')
            self.assertEqual(len(uncensored['groups']), 1)
            self.assertEqual(uncensored['groups'][0]['category'], 'uncensored')
            self.assertEqual(uncensored['total'], 0)
            self.assertEqual(len(hot.connections()['sources']), 30)
            network.assert_not_called()

    def test_failed_refresh_keeps_last_success_and_marks_stale(self):
        feed = FEEDS[1]
        hot._feed_job.update(completed=0, running=True)
        with patch.object(hot, 'read_html', return_value=(200, feed[3], FALENO)):
            hot._run_feeds([feed])
        good = copy.deepcopy(hot.films('censored', 'hot')['groups'][0])
        # FEEDS ordering: faleno appears first in both views.
        self.assertEqual(good['state'], 'ok')
        self.assertFalse(good['stale'])
        with patch.object(hot, 'read_html', side_effect=hot_network.NetworkError('timeout', '读取超时')):
            hot._run_feeds([feed])
        bad = hot.films('censored', 'hot')['groups'][0]
        self.assertEqual(bad['items'], good['items'])
        self.assertEqual(bad['fetched_at'], good['fetched_at'])
        self.assertEqual(bad['state'], 'timeout')
        self.assertTrue(bad['stale'])
        # Response is a detached copy.
        bad['items'].clear()
        self.assertTrue(hot.films('censored', 'hot')['groups'][0]['items'])

    def test_age_gate_response_does_not_run_parser(self):
        with patch.object(hot, 'read_html', return_value=(200, 'https://www.dmm.co.jp/age_check/', '<title>年齢認証</title>')):
            with patch.object(hot, 'parse_feed') as parse:
                result = hot._refresh_feed(FEEDS[0])
        self.assertEqual(result['state'], 'age_gate')
        self.assertNotIn('items', result)
        parse.assert_not_called()

    def test_connectivity_is_single_flight_and_rate_limited(self):
        with patch.object(hot.threading, 'Thread') as thread:
            first = hot.start_checks()
            second = hot.start_checks()
            self.assertTrue(first['job']['running'])
            self.assertEqual(second['job']['total'], 30)
            self.assertEqual(thread.call_count, 1)
            hot._check['running'] = False
            hot.start_checks()
            self.assertEqual(thread.call_count, 1)

    def test_feed_cooldown_per_key_and_single_flight_across_filters(self):
        with patch.object(hot.threading, 'Thread') as thread:
            hot.refresh_films('uncensored', 'hot')
            self.assertEqual(thread.call_count, 1)
            hot.refresh_films('censored', 'latest')
            self.assertEqual(thread.call_count, 1)
            hot._feed_job['running'] = False
            hot.refresh_films('uncensored', 'hot')
            self.assertEqual(thread.call_count, 1)
            hot.refresh_films('censored', 'latest')
            self.assertEqual(thread.call_count, 2)

    def test_check_batch_detects_every_source_and_keeps_previous_on_start(self):
        hot._checks['avbase'] = {'state': 'ok'}
        with patch.object(hot.threading, 'Thread'):
            hot.start_checks()
        self.assertEqual(hot.connections()['sources'][0]['result']['state'], 'ok')
        with patch.object(hot, '_probe', return_value={'state': 'ok', 'responded': True}) as probe:
            hot._run_checks()
        self.assertEqual(probe.call_count, 30)
        result = hot.connections()
        self.assertFalse(result['job']['running'])
        self.assertEqual(result['job']['completed'], 30)
        self.assertTrue(result['job']['finished_at'])

    def test_check_error_is_sanitized_and_records_latency(self):
        with patch.object(hot, 'read_html', side_effect=RuntimeError('password=secret')):
            result = hot._probe(BY_ID['avbase'])
        self.assertEqual(result['state'], 'error')
        self.assertNotIn('secret', str(result))
        self.assertIsInstance(result['elapsed_ms'], int)
        self.assertFalse(result['responded'])


class ClassificationTests(unittest.TestCase):
    def test_gates_are_distinct_from_http_ok(self):
        for code, url, html, expected in [
            (200, 'https://test.invalid/', '<title>Works</title><p>Browse releases here</p>', 'ok'),
            (200, 'https://test.invalid/', '<p>Due to copyright restrictions, access to this site is prohibited in the country where your internet is located.</p>', 'region_blocked'),
            (403, 'https://test.invalid/', '<h1>公式サイト 一時停止のお知らせ</h1><p>臨時サーバーメンテナンス</p>', 'maintenance'),
            (200, 'https://test.invalid/age_check/', '<title>FANZA</title>', 'age_gate'),
            (200, 'https://test.invalid/', '<script src="forsale.min.js"></script>', 'parking'),
            (403, 'https://test.invalid/', '<title>Just a moment...</title>', 'challenge'),
            (200, 'https://test.invalid/', '<div id="javu-site-index"></div>', 'js_shell'),
            (200, 'https://test.invalid/', '<p>Works</p><script>challenge-platform captcha telemetry</script>', 'ok'),
            (403, 'https://test.invalid/', '<p>Forbidden</p>', 'denied'),
            (429, 'https://test.invalid/', '<p>slow down</p>', 'rate_limited'),
            (503, 'https://test.invalid/', '<p>offline</p>', 'http_error'),
        ]:
            with self.subTest(expected=expected):
                self.assertEqual(hot_network.classify(code, url, html)[0], expected)


class NetworkTests(unittest.TestCase):
    def addresses(self, ip):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))]

    def test_resolve_rejects_private_and_mixed_dns_and_credentials(self):
        for ips in [['127.0.0.1'], ['169.254.169.254'], ['10.0.0.1'], ['8.8.8.8', '192.168.0.1']]:
            with self.subTest(ips=ips), patch.object(socket, 'getaddrinfo', return_value=sum([self.addresses(ip) for ip in ips], [])):
                with self.assertRaises(hot_network.NetworkError):
                    hot_network.resolve_public('https://example.invalid/')
        for url in ['http://example.invalid/', 'https://user:pass@example.invalid/', 'https://example.invalid:8080/', 'file:///etc/passwd']:
            with self.assertRaises(hot_network.NetworkError):
                hot_network.resolve_public(url)

    def test_dns_failure_is_distinct_and_public_address_is_returned(self):
        with patch.object(socket, 'getaddrinfo', side_effect=socket.gaierror()):
            with self.assertRaises(hot_network.NetworkError) as cm:
                hot_network.resolve_public('https://example.invalid/')
            self.assertEqual(cm.exception.state, 'dns_error')
        with patch.object(socket, 'getaddrinfo', return_value=self.addresses('8.8.8.8')):
            self.assertEqual(hot_network.resolve_public('https://example.invalid/')[1], '8.8.8.8')

    def test_redirect_to_http_cannot_fall_back_to_default_transport(self):
        # Real Session dispatch through the actual mounted adapters; no sockets.
        response = requests.Response()
        response.status_code = 302
        response.headers['Location'] = 'http://127.0.0.1/private'
        response._content = b''
        with patch.object(hot_network, 'resolve_public', side_effect=[
                (hot_network.urlsplit('https://example.invalid/'), '8.8.8.8'),
                hot_network.NetworkError('unsafe_redirect', 'blocked')]) as resolve:
            with patch.object(hot_network.PinnedTLSAdapter, 'send', return_value=response) as transport:
                with self.assertRaises(hot_network.NetworkError) as cm:
                    hot_network.read_html('https://example.invalid/')
        self.assertEqual(cm.exception.state, 'unsafe_redirect')
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(resolve.call_args.args[0], 'http://127.0.0.1/private')

    def test_transport_pins_address_and_keeps_hostname_for_tls_and_host(self):
        with patch.object(hot_network, 'resolve_public', return_value=(hot_network.urlsplit('https://example.invalid/path'), '8.8.8.8')):
            with patch.object(hot_network, 'PinnedTLSAdapter') as tls:
                response = MagicMock()
                tls.return_value.send.return_value = response
                adapter = hot_network.PublicAdapter()
                request = requests.Request('GET', 'https://example.invalid/path').prepare()
                result = adapter.send(request, verify=True)
                wire = tls.return_value.send.call_args.args[0]
                self.assertEqual(wire.url, 'https://8.8.8.8/path')
                self.assertEqual(wire.headers['Host'], 'example.invalid')
                self.assertEqual(result.url, request.url)
                tls.assert_called_once_with('example.invalid')
                self.assertTrue(tls.return_value.send.call_args.kwargs['verify'])
                adapter.close()

    def session(self, response_list):
        session = MagicMock()
        session.__enter__.return_value = session
        responses = []
        for code, headers, body in response_list:
            r = MagicMock(status_code=code, headers=headers)
            r.__enter__.return_value = r
            raw = io.BytesIO(body)
            r.raw.read1.side_effect = lambda n, decode_content=True, raw=raw: raw.read(n)
            responses.append(r)
        session.get.side_effect = responses
        return session

    def test_read_is_streamed_anonymous_no_environment_proxy_or_auto_redirect(self):
        session = self.session([(200, {'Content-Type': 'text/html; charset=utf-8'}, '<p>网页</p>'.encode())])
        with patch.object(hot_network.requests, 'Session', return_value=session):
            self.assertEqual(hot_network.read_html('https://example.invalid/')[2], '<p>网页</p>')
        self.assertFalse(session.trust_env)
        kwargs = session.get.call_args.kwargs
        self.assertTrue(kwargs['stream'])
        self.assertFalse(kwargs['allow_redirects'])
        session.cookies.clear.assert_called_once()
        self.assertNotIn('cookies', kwargs)
        self.assertLessEqual(kwargs['timeout'][0], 5)

    def test_redirect_each_hop_uses_pinned_adapter_and_has_limit(self):
        session = self.session([(302, {'Location': '/next'}, b''), (200, {'Content-Type': 'text/html'}, b'ok')])
        with patch.object(hot_network.requests, 'Session', return_value=session):
            result = hot_network.read_html('https://example.invalid/')
        self.assertEqual(result[1], 'https://example.invalid/next')
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.cookies.clear.call_count, 2)
        session = self.session([(302, {'Location': '/'}, b'')] * 5)
        with patch.object(hot_network.requests, 'Session', return_value=session):
            with self.assertRaises(hot_network.NetworkError) as cm:
                hot_network.read_html('https://example.invalid/')
        self.assertEqual(cm.exception.state, 'redirect_error')

    def test_slow_read_deadline_and_urllib3_timeout_are_reported(self):
        session = self.session([(200, {'Content-Type': 'text/html'}, b'hello')])
        with patch.object(hot_network.requests, 'Session', return_value=session), patch.object(hot_network.time, 'monotonic', side_effect=[0, 0, 21]):
            with self.assertRaises(hot_network.NetworkError) as cm:
                hot_network.read_html('https://example.invalid/')
        self.assertEqual(cm.exception.state, 'timeout')
        # urllib3 errors can escape raw.read1 rather than requests' iter_content.
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = hot_network.ReadTimeoutError(None, '/', 'secret detail')
        with patch.object(hot_network.requests, 'Session', return_value=session):
            with self.assertRaises(hot_network.NetworkError) as cm:
                hot_network.read_html('https://example.invalid/')
        self.assertEqual(cm.exception.state, 'timeout')
        self.assertNotIn('secret', str(cm.exception))

    def test_size_limit_and_non_html_and_tls_failures_are_safe(self):
        for responses, expected in [
            ([(200, {'Content-Type': 'text/html'}, b'x' * 11)], 'too_large'),
            ([(200, {'Content-Type': 'video/mp4'}, b'video')], 'not_html'),
        ]:
            with self.subTest(expected=expected):
                with patch.object(hot_network.requests, 'Session', return_value=self.session(responses)), patch.object(hot_network, 'MAX_BYTES', 10):
                    with self.assertRaises(hot_network.NetworkError) as cm:
                        hot_network.read_html('https://example.invalid/')
                self.assertEqual(cm.exception.state, expected)
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = requests.exceptions.SSLError('private-password')
        with patch.object(hot_network.requests, 'Session', return_value=session):
            with self.assertRaises(hot_network.NetworkError) as cm:
                hot_network.read_html('https://example.invalid/')
        self.assertEqual(cm.exception.state, 'tls_error')
        self.assertNotIn('password', str(cm.exception))


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(hot_router.router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def login(self, role='operator'):
        self.app.dependency_overrides[current_user] = lambda: {'username': 'test', 'role': role}

    def test_anonymous_get_and_post_denied_before_work(self):
        with patch.object(hot, 'start_checks') as checks, patch.object(hot, 'refresh_films') as refresh:
            for path, method in [('/connections', 'GET'), ('/films', 'GET'), ('/connections', 'POST'), ('/refresh', 'POST')]:
                response = self.client.request(method, '/api/hot' + path, json={} if method == 'POST' else None)
                self.assertEqual(response.status_code, 401)
            checks.assert_not_called()
            refresh.assert_not_called()

    def test_operator_can_read_and_refresh_but_not_batch_check(self):
        self.login()
        with patch.object(hot, 'connections', return_value={'sources': []}):
            result = self.client.get('/api/hot/connections')
        self.assertFalse(result.json()['can_check'])
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        with patch.object(hot, 'start_checks') as start:
            self.assertEqual(self.client.post('/api/hot/connections', json={}).status_code, 403)
            start.assert_not_called()
        with patch.object(hot, 'refresh_films', return_value={}) as refresh:
            self.assertEqual(self.client.post('/api/hot/refresh', json={'category': 'uncensored', 'sort': 'hot'}).status_code, 202)
            refresh.assert_called_once_with('uncensored', 'hot')

    def test_admin_check_is_explicit_and_rejects_arbitrary_urls(self):
        self.login('admin')
        with patch.object(hot, 'start_checks', return_value={'sources': []}) as start:
            self.assertEqual(self.client.post('/api/hot/connections', json={'url': 'http://127.0.0.1'}).status_code, 422)
            start.assert_not_called()
            self.assertEqual(self.client.post('/api/hot/connections', json={}).status_code, 202)
            start.assert_called_once()

    def test_filter_validation_rejects_unsupported_values(self):
        self.login()
        for query in ['category=other', 'sort=random']:
            self.assertEqual(self.client.get('/api/hot/films?' + query).status_code, 422)
        for payload in [{'category': 'other'}, {'sort': 'random'}, {'url': 'https://arbitrary.invalid'}]:
            self.assertEqual(self.client.post('/api/hot/refresh', json=payload).status_code, 422)
        with patch.object(hot, 'films', return_value={'total': 0}) as films:
            self.assertEqual(self.client.get('/api/hot/films?category=censored&sort=hot').status_code, 200)
            films.assert_called_once_with('censored', 'hot')


if __name__ == '__main__':
    unittest.main()
