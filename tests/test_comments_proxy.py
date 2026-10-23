"""F09: browser comment traffic stays same-origin behind a server-side proxy.

The upstream base is fixed by the server environment, every forwarded route is
whitelisted per method, and neither the site session cookie nor any upstream
cookie/redirect header crosses the boundary.  A recording upstream stands in for
the Cloudflare Worker so the tests stay offline.
"""
from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from javsp_web import comments_proxy, storage

PROXY = '/api/comments'


class RecordingUpstream:
    """Local stand-in for the comment Worker that records every request."""

    def __init__(self):
        self.records: list[dict] = []
        self.responder = lambda record: (200, {'ok': True}, {})
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def log_error(self, *args):
                pass

            def handle_one_request(self):
                try:
                    super().handle_one_request()
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True

            def serve(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length) if length else b''
                record = {
                    'method': self.command,
                    'path': self.path,
                    'headers': {key.lower(): value for key, value in self.headers.items()},
                    'body': body,
                }
                outer.records.append(record)
                status, payload, headers = outer.responder(record)
                raw = payload if isinstance(payload, bytes) else (b'' if payload is None else json.dumps(payload).encode())
                content_type = next((value for key, value in headers.items() if key.lower() == 'content-type'), 'application/json; charset=utf-8')
                self.send_response(status)
                for key, value in headers.items():
                    if key.lower() != 'content-type':
                        self.send_header(key, value)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)

            do_GET = serve
            do_POST = serve
            do_DELETE = serve
            do_PUT = serve

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.upstream = RecordingUpstream()
        self.addCleanup(self.upstream.close)
        environment = patch.dict(os.environ, {'JAVSP_COMMENTS_URL': self.upstream.url, 'JAVSP_COMMENTS_VERIFY_URL': ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = FastAPI()
        self.app.include_router(comments_proxy.router)
        self.client = TestClient(self.app)
        self.login()
        self.addCleanup(lambda: self.app.dependency_overrides.clear())

    def login(self, role='operator'):
        self.app.dependency_overrides[comments_proxy.current_user] = lambda: {'username': 'operator', 'role': role}

    def logout(self):
        self.app.dependency_overrides.pop(comments_proxy.current_user, None)

    def test_site_login_is_the_gate_before_any_forwarding(self):
        self.logout()
        response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.upstream.records, [])

    def test_empty_upstream_disables_the_whole_proxy(self):
        with patch.dict(os.environ, {'JAVSP_COMMENTS_URL': ''}):
            for method, path in [('get', 'api/config'), ('get', 'api/threads/ABC-001/comments'), ('post', 'api/me/logout')]:
                response = getattr(self.client, method)(f'{PROXY}/{path}', **({'json': {}} if method == 'post' else {}))
                self.assertEqual(response.status_code, 503, path)
                self.assertEqual(response.json()['detail'], '评论服务未启用。')
        self.assertEqual(self.upstream.records, [])

    def test_whitelisted_routes_reach_the_upstream_verbatim(self):
        cases = [
            ('get', 'api/config', None),
            ('get', 'api/threads/ABC-001/comments', None),
            ('post', 'api/threads/ABC-001/comments', {'body': 'hello', 'turnstile_token': 'proof'}),
            ('post', 'api/comments/42/like', {'liked': True}),
            ('post', 'api/comments/42/reports', {'reason': 'spam'}),
            ('delete', 'api/comments/42', None),
            ('post', 'api/identity', {'username': 'apecme', 'pin': '123456', 'mode': 'login'}),
            ('get', 'api/me/profile', None),
            ('post', 'api/me/profile', {'avatar_id': ''}),
            ('get', 'api/me/comments', None),
            ('post', 'api/me/logout', {}),
            ('post', 'api/me/logout-all', {}),
            ('post', 'api/me/pin', {'pin': '123456', 'new_pin': '654321'}),
        ]
        for method, path, payload in cases:
            with self.subTest(route=path, method=method):
                records = len(self.upstream.records)
                response = getattr(self.client, method)(f'{PROXY}/{path}', **({'json': payload} if payload is not None else {}))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(self.upstream.records), records + 1)
                record = self.upstream.records[-1]
                self.assertEqual(record['method'], method.upper())
                self.assertEqual(record['path'], '/' + path)
                if payload is not None:
                    self.assertEqual(json.loads(record['body'] or b'{}'), payload)

    def test_admin_escapes_and_method_confusion_are_refused(self):
        blocked = [
            ('get', 'api/admin/settings', 403),
            ('post', 'api/admin/settings', 403),
            ('get', 'api/admin', 403),
            ('get', 'https://evil.example/api/config', 403),
            ('get', 'api/threads/ABC-001/comments/extra', 403),
            ('get', 'api/threads/ABC%2F001/comments', 403),
            ('get', 'api/threads/ABC%2e001/comments', 403),
            ('get', 'api/threads/..%2fadmin%2fsettings/comments', 403),
            ('get', 'api/configX', 403),
            ('get', 'api/me/profile/../../admin', 403),
            ('get', '', 403),
            ('put', 'api/config', 405),
            ('patch', 'api/config', 405),
            ('options', 'api/config', 405),
        ]
        for method, path, status in blocked:
            with self.subTest(route=path, method=method):
                response = getattr(self.client, method)(f'{PROXY}/{path}')
                self.assertEqual(response.status_code, status, path)
        self.assertEqual(self.upstream.records, [])

    def test_query_parameters_are_limited_to_paging(self):
        response = self.client.get(f'{PROXY}/api/threads/ABC-001/comments?limit=20&before=17')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upstream.records[-1]['path'], '/api/threads/ABC-001/comments?before=17&limit=20')
        for query in ('evil=1', 'before=3&callback=https://evil.example', 'limit=abc', 'limit=5&limit=6', 'limit='):
            with self.subTest(query=query):
                records = len(self.upstream.records)
                response = self.client.get(f'{PROXY}/api/threads/ABC-001/comments?{query}')
                self.assertEqual(response.status_code, 400, query)
                self.assertEqual(len(self.upstream.records), records)
        response = self.client.get(f'{PROXY}/api/config?limit=5')
        self.assertEqual(response.status_code, 403)

        history = self.client.get(f'{PROXY}/api/me/comments?before=99')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(self.upstream.records[-1]['path'], '/api/me/comments?before=99')

        body_on_get = self.client.request('GET', f'{PROXY}/api/config', content=b'{}', headers={'content-type': 'application/json'})
        self.assertEqual(body_on_get.status_code, 400)

    def test_site_credentials_and_proxy_headers_never_reach_the_upstream(self):
        response = self.client.get(f'{PROXY}/api/me/profile', headers={
            'cookie': 'javsp_web_session=site-session-secret',
            'authorization': 'Bearer site-secret',
            'x-forwarded-for': '203.0.113.9',
            'cf-connecting-ip': '203.0.113.9',
            'x-real-ip': '203.0.113.9',
            'origin': 'https://app.example',
            'referer': 'https://app.example/',
            'x-user-token': 'A' * 43,
        })
        self.assertEqual(response.status_code, 200)
        headers = self.upstream.records[-1]['headers']
        self.assertEqual(headers['x-user-token'], 'A' * 43)
        for name in ('cookie', 'authorization', 'x-forwarded-for', 'cf-connecting-ip', 'x-real-ip', 'origin', 'referer'):
            self.assertNotIn(name, headers)
        self.assertEqual(self.client.cookies.get('javsp_web_session'), None)

    def test_malformed_identity_tokens_are_refused(self):
        for token in ('short', 'a b', 'A' * 201, 'token;path=/'):
            with self.subTest(token=token):
                response = self.client.get(f'{PROXY}/api/me/profile', headers={'x-user-token': token})
                self.assertEqual(response.status_code, 400, token)
        self.assertEqual(self.upstream.records, [])

    def test_delete_token_only_travels_on_comment_deletion(self):
        token = 'a' * 72
        response = self.client.delete(f'{PROXY}/api/comments/42', headers={'x-delete-token': token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upstream.records[-1]['headers']['x-delete-token'], token)
        refused = self.client.post(f'{PROXY}/api/threads/ABC-001/comments', json={'body': 'x'}, headers={'x-delete-token': token})
        self.assertEqual(refused.status_code, 400)

    def test_upstream_cookies_and_redirects_never_reach_the_browser(self):
        self.upstream.responder = lambda record: (200, {'ok': True}, {'Set-Cookie': 'upstream=1; Path=/', 'Location': 'https://evil.example/'})
        response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('set-cookie', response.headers)
        self.assertNotIn('location', response.headers)

        self.upstream.responder = lambda record: (302, b'', {'Location': 'https://evil.example/steal'})
        response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('location', response.headers)
        self.assertNotIn('evil.example', response.text)

    def test_upstream_status_and_retry_after_are_preserved(self):
        for status in (400, 401, 403, 404, 409, 413, 415, 428, 429, 500):
            with self.subTest(status=status):
                self.upstream.responder = lambda record, posted=status: (posted, {'detail': '上游说明', 'challenge': {'action': 'comment'}}, {'Retry-After': '42'})
                response = self.client.post(f'{PROXY}/api/threads/ABC-001/comments', json={'body': 'x'})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()['detail'], '上游说明')
                self.assertEqual(response.json()['challenge'], {'action': 'comment'})
                if status == 428:
                    self.assertEqual(response.headers['retry-after'], '42')

    def test_unreachable_upstream_is_reported_without_internal_details(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            closed_port = probe.getsockname()[1]
        with patch.dict(os.environ, {'JAVSP_COMMENTS_URL': f'http://127.0.0.1:{closed_port}'}):
            response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['detail'], '无法连接评论服务，请稍后重试。')
        self.assertNotIn(str(closed_port), response.text)
        self.assertNotIn('ConnectionError', response.text)

    def test_upstream_timeout_is_a_readable_504(self):
        def slow(record):
            time.sleep(0.6)
            return (200, {'ok': True}, {})
        self.upstream.responder = slow
        with patch.object(comments_proxy, 'TIMEOUT', (0.15, 0.15)):
            response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()['detail'], '评论服务响应超时，请稍后重试。')

    def test_request_and_response_sizes_are_bounded(self):
        oversized = b'x' * (comments_proxy.MAX_REQUEST_BYTES + 1)
        response = self.client.post(f'{PROXY}/api/threads/ABC-001/comments', content=oversized, headers={'content-type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.upstream.records, [])

        refusal = self.client.post(f'{PROXY}/api/threads/ABC-001/comments', content=b'{}', headers={'content-type': 'text/plain'})
        self.assertEqual(refusal.status_code, 415)

        self.upstream.responder = lambda record: (200, {'items': ['x' * 400] * 20}, {})
        with patch.object(comments_proxy, 'MAX_RESPONSE_BYTES', 1024):
            response = self.client.get(f'{PROXY}/api/me/comments')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['detail'], '评论服务响应过大，请稍后重试。')

    def test_non_json_upstream_bodies_are_refused_instead_of_relayed(self):
        self.upstream.responder = lambda record: (403, b'<html>cloudflare challenge</html>', {'Content-Type': 'text/html'})
        response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('challenge', response.text)

    def test_empty_upstream_body_keeps_its_status(self):
        self.upstream.responder = lambda record: (204, None, {})
        response = self.client.delete(f'{PROXY}/api/comments/42')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='comments-runtime-')
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        previous = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(previous):
                self.enterContext(patch.object(storage, name, folder / value.relative_to(previous)))
        storage.ensure_seed_data()
        from javsp_web import server
        self.server = server
        self.client = TestClient(server.app)
        self.enterContext(patch.dict(os.environ, {}, clear=False))
        self.server.app.dependency_overrides[self.server.current_user] = lambda: {'username': 'operator', 'role': 'operator'}
        self.addCleanup(self.server.app.dependency_overrides.pop, self.server.current_user, None)

    def runtime(self):
        response = self.client.get('/api/runtime')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_public_comment_api_is_same_origin_and_verification_keeps_its_own_origin(self):
        os.environ['JAVSP_COMMENTS_URL'] = 'https://comments.example/'
        os.environ.pop('JAVSP_COMMENTS_VERIFY_URL', None)
        data = self.runtime()
        self.assertEqual(data['comments_url'], PROXY)
        self.assertEqual(data['comments_verify_url'], 'https://comments.example')

        os.environ['JAVSP_COMMENTS_VERIFY_URL'] = 'https://verify.example/'
        data = self.runtime()
        self.assertEqual(data['comments_url'], PROXY)
        self.assertEqual(data['comments_verify_url'], 'https://verify.example')

    def test_unset_upstream_keeps_the_built_in_default(self):
        os.environ.pop('JAVSP_COMMENTS_URL', None)
        os.environ.pop('JAVSP_COMMENTS_VERIFY_URL', None)
        data = self.runtime()
        self.assertEqual(data['comments_url'], PROXY)
        self.assertEqual(data['comments_verify_url'], comments_proxy.DEFAULT_UPSTREAM)

    def test_disabled_or_invalid_upstream_hides_comments_entirely(self):
        for value in ('', '  ', 'ftp://comments.example', 'https://user:pass@comments.example', 'comments.example'):
            with self.subTest(value=value):
                os.environ['JAVSP_COMMENTS_URL'] = value
                data = self.runtime()
                self.assertEqual(data['comments_url'], '')
                self.assertEqual(data['comments_verify_url'], '')

    def test_server_mounts_the_proxy_router(self):
        upstream = RecordingUpstream()
        self.addCleanup(upstream.close)
        os.environ['JAVSP_COMMENTS_URL'] = upstream.url
        response = self.client.get(f'{PROXY}/api/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(upstream.records[-1]['path'], '/api/config')


if __name__ == '__main__':
    unittest.main()
