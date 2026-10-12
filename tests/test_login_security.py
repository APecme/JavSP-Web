"""F10: exercise real handlers, admission races, and proxy trust boundaries."""
import ast
import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from javsp_web import auth, login_security, storage
from tests.test_auth_sessions import handlers


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='f10-auth-'))
        previous = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(previous):
                self.enterContext(patch.object(storage, name, Path(directory) / value.relative_to(previous)))
        self.enterContext(patch.object(auth, '_sessions', {}))
        self.enterContext(patch.object(login_security, 'TRUSTED_PROXIES', frozenset({'192.168.0.1'})))
        storage.upsert_user('alice', 'correct-password', 'operator')
        self.ns = handlers()
        self.now = 1000.0
        self.limiter = login_security.LoginLimiter(clock=lambda: self.now)
        self.ns['login_limiter'] = self.limiter
        self.app = FastAPI()
        self.app.post('/login')(self.ns['login'])
        self.app.post('/logout')(self.ns['logout'])
        self.app.get('/me')(self.ns['me'])
        self.client = self.client_for('192.168.0.1')

    def client_for(self, host, scheme='http'):
        return self.enterContext(TestClient(self.app, client=(host, 12345), base_url=scheme + '://testserver'))

    def login(self, username='alice', password='wrong', ip='198.51.100.10', client=None, headers=None):
        return (client or self.client).post('/login', json={'username': username, 'password': password},
                                          headers=headers or {'X-Real-IP': ip, 'X-Forwarded-Proto': 'https'})

    def test_username_failures_across_ips_reject_before_lookup_and_hash(self):
        for i in range(10):
            self.assertEqual(self.login(ip=f'198.51.100.{i}').status_code, 401)
        with patch.dict(self.ns, {'find_user': unittest.mock.Mock(), 'verify_password': unittest.mock.Mock()}):
            response = self.login(password='correct-password', ip='203.0.113.1')
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['Retry-After'], '300')
            self.ns['find_user'].assert_not_called()
            self.ns['verify_password'].assert_not_called()
        self.assertEqual(self.login('another-user', ip='203.0.113.1').status_code, 401)
        self.now += 300
        self.assertEqual(self.login(password='correct-password').status_code, 200)

    def test_ip_failures_across_names_and_missing_users_are_counted(self):
        for i in range(30):
            self.assertEqual(self.login(username=f'missing-{i}').status_code, 401)
        with patch.dict(self.ns, {'verify_password': unittest.mock.Mock()}):
            self.assertEqual(self.login(password='correct-password').status_code, 429)
            self.ns['verify_password'].assert_not_called()
        self.assertEqual(self.login(password='correct-password', ip='203.0.113.2').status_code, 200)

    def test_successes_refund_only_their_reservation(self):
        self.assertEqual(self.login().status_code, 401)
        for _ in range(35):
            self.assertEqual(self.login(password='correct-password').status_code, 200)
        for _ in range(9):
            self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_untrusted_headers_cannot_rotate_ip_or_set_secure(self):
        client = self.client_for('192.168.0.77')
        response = self.login(password='correct-password', client=client)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('secure', response.headers['set-cookie'].lower())
        for i in range(30):
            self.assertEqual(self.login(username=f'unknown-{i}', ip=f'203.0.113.{i}', client=client).status_code, 401)
        self.assertEqual(self.login(password='correct-password', client=client).status_code, 429)

    def test_secure_cookie_https_proxy_and_logout(self):
        proxied = self.login(password='correct-password')
        self.assertIn('secure', proxied.headers['set-cookie'].lower())
        client = self.client_for('192.168.0.1', 'https')
        response = self.login(password='correct-password', client=client)
        cookie = response.headers['set-cookie'].lower()
        for flag in ('secure', 'httponly', 'samesite=lax', 'max-age=43200', 'path=/'):
            self.assertIn(flag, cookie)
        self.assertEqual(client.get('/me').status_code, 200)
        response = client.post('/logout', headers={'X-Forwarded-Proto': 'https'})
        self.assertIn('secure', response.headers['set-cookie'].lower())
        self.assertEqual(client.get('/me').status_code, 401)

    def test_direct_tls_sets_secure_without_proxy_trust(self):
        client = self.client_for('192.168.0.77', 'https')
        response = self.login(password='correct-password', client=client, headers={'X-Forwarded-Proto': 'http'})
        self.assertIn('secure', response.headers['set-cookie'].lower())
        self.assertEqual(client.get('/me').status_code, 200)

    def test_direct_http_login_and_logout_remain_usable(self):
        client = self.client_for('127.0.0.1')
        response = self.login(password='correct-password', client=client)
        self.assertNotIn('secure', response.headers['set-cookie'].lower())
        self.assertEqual(client.get('/me').status_code, 200)
        self.assertEqual(client.post('/logout').status_code, 200)
        self.assertEqual(client.get('/me').status_code, 401)

    def test_proxy_context_handles_malformed_duplicate_and_spoofed_headers(self):
        def context(peer, headers, scheme='http'):
            return login_security.login_context(Request({'type': 'http', 'scheme': scheme, 'path': '/',
                'server': ('test', 80), 'client': (peer, 12), 'headers': headers}))
        self.assertEqual(context('192.168.0.1', [(b'x-real-ip', b'::ffff:198.51.100.1'),
                                                (b'x-forwarded-proto', b'https')]), ('198.51.100.1', True))
        for value in (b'bad', b'1.2.3.4, 5.6.7.8', b'fe80::1%eth0'):
            self.assertEqual(context('192.168.0.1', [(b'x-real-ip', value)]), ('192.168.0.1', False))
        duplicate = [(b'x-real-ip', b'1.2.3.4'), (b'x-real-ip', b'5.6.7.8'),
                     (b'x-forwarded-proto', b'https'), (b'x-forwarded-proto', b'http')]
        self.assertEqual(context('192.168.0.1', duplicate), ('192.168.0.1', False))
        self.assertEqual(context('127.0.0.1', [(b'x-forwarded-for', b'192.168.0.1'),
                                             (b'x-forwarded-proto', b'https')]), ('127.0.0.1', False))
        self.assertEqual(context('192.168.0.1', [(b'x-forwarded-proto', b'http')], 'https'), ('192.168.0.1', True))
        with patch.object(login_security, 'TRUSTED_PROXIES', frozenset()):
            self.assertEqual(context('192.168.0.1', [(b'x-forwarded-proto', b'https')]), ('192.168.0.1', False))

    def test_parallel_admission_reserves_before_password_verification(self):
        entered = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        calls = []
        def verify(*_):
            with lock:
                calls.append(1)
                if len(calls) == 10:
                    entered.set()
            self.assertTrue(release.wait(10))
            return False
        def attempt(index):
            from fastapi import Response
            request = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'headers': [],
                               'server': ('test', 80), 'client': (f'203.0.113.{index}', 123)})
            try:
                self.ns['login'](self.ns['LoginBody'](username='alice', password='wrong'), Response(), request)
            except HTTPException as exc:
                return exc.status_code
        with patch.dict(self.ns, {'verify_password': verify}), concurrent.futures.ThreadPoolExecutor(max_workers=11) as pool:
            futures = [pool.submit(attempt, i) for i in range(10)]
            try:
                self.assertTrue(entered.wait(10))
                self.assertEqual(pool.submit(attempt, 11).result(5), 429)
                self.assertEqual(len(calls), 10)
                self.now += 301  # In-flight reservations must not expire while hashing.
                self.assertEqual(pool.submit(attempt, 12).result(5), 429)
            finally:
                release.set()
            self.assertEqual([f.result() for f in futures], [401] * 10)

    def test_memory_bound_does_not_evict_live_limits_and_recovers(self):
        limiter = login_security.LoginLimiter(max_keys=4, clock=lambda: self.now)
        for i in range(2):
            with limiter.attempt(str(i), str(i)):
                pass
        with self.assertRaises(HTTPException) as raised:
            with limiter.attempt('new', 'new'):
                self.fail('capacity limit bypassed')
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(len(limiter._buckets), 4)
        self.now += 301
        with limiter.attempt('new', 'new') as attempt:
            attempt.success = True
        self.assertFalse(limiter._buckets)

    def test_exception_releases_pending_reservation(self):
        with self.assertRaises(RuntimeError):
            with self.limiter.attempt('ip', 'alice'):
                raise RuntimeError('simulated failure')
        self.assertTrue(all(bucket.pending == 0 for bucket in self.limiter._buckets.values()))

    def test_initial_admin_login_change_password_and_relogin(self):
        client = self.client_for('127.0.0.1')
        self.assertEqual(self.login('admin', 'admin', client=client).status_code, 200)
        storage.upsert_user('admin', 'new-initial-password', 'admin')
        self.assertEqual(client.get('/me').status_code, 401)
        self.assertEqual(self.login('admin', 'admin', client=client).status_code, 401)
        self.assertEqual(self.login('admin', 'new-initial-password', client=client).status_code, 200)

    def test_server_entrypoint_preserves_socket_peer(self):
        source = Path(storage.__file__).with_name('server.py')
        node = next(n for n in ast.parse(source.read_text(encoding='utf8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'run')
        namespace = {'os': __import__('os')}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        with patch('uvicorn.run') as run:
            namespace['run']()
            self.assertIs(run.call_args.kwargs['proxy_headers'], False)


if __name__ == '__main__':
    unittest.main()
