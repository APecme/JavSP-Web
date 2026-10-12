"""F10 production acceptance inside the container; no credentials in output.

Set F10_PUBLIC_URL to the actual HTTPS entrypoint for the proxy/cookie probe.
Only throwaway operators receive failed logins; existing users are untouched.
"""
import json
import os
import secrets
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener

from javsp_web import storage
from javsp_web.auth import SESSION_COOKIE
from javsp_web.login_security import TRUSTED_PROXIES

LOCAL = 'http://127.0.0.1:8090'
PUBLIC = os.environ['F10_PUBLIC_URL'].rstrip('/')
assert urlsplit(PUBLIC).scheme == 'https', 'HTTPS public URL required'
opener = build_opener(ProxyHandler({}))


def request(base, path, body=None, cookie=None, headers=None):
    headers = {'Content-Type': 'application/json', **(headers or {})}
    if cookie:
        headers['Cookie'] = cookie
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        response = opener.open(req, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        response.read()
        return response.status, response.headers


def login(base, username, password, headers=None):
    return request(base, '/api/auth/login', {'username': username, 'password': password}, headers=headers)


def cookie(headers):
    parsed = SimpleCookie()
    parsed.load(headers.get('Set-Cookie', ''))
    return parsed[SESSION_COOKIE]


users = ['f10probe' + secrets.token_hex(6) for _ in range(2)]
password = secrets.token_urlsafe(32)
result = {'ok': False, 'trusted_proxy_exact': TRUSTED_PROXIES == frozenset({'192.168.0.1'})}
created = []
try:
    for username in users:
        storage.upsert_user(username, password, 'operator')
        created.append(username)
    status, headers = login(PUBLIC, users[0], password)
    result['https_login'] = status
    session = cookie(headers)
    result['https_cookie_flags'] = (bool(session['secure']) and bool(session['httponly'])
                                     and session['samesite'].lower() == 'lax' and session['max-age'] == '43200')
    token = SESSION_COOKIE + '=' + session.value
    result['https_session_works'] = request(PUBLIC, '/api/auth/me', cookie=token)[0] == 200
    status, headers = request(PUBLIC, '/api/auth/logout', {}, cookie=token)
    result['https_logout'] = status == 200 and bool(cookie(headers)['secure'])
    result['logout_revokes_session'] = request(PUBLIC, '/api/auth/me', cookie=token)[0] == 401
    forged = {'X-Forwarded-Proto': 'https', 'X-Real-IP': '198.51.100.77', 'X-Forwarded-For': '192.168.0.1'}
    status, headers = login(LOCAL, users[0], password, forged)
    session = cookie(headers)
    result['loopback_spoof_ignored'] = status == 200 and not session['secure']
    token = SESSION_COOKIE + '=' + session.value
    result['direct_http_session_works'] = request(LOCAL, '/api/auth/me', cookie=token)[0] == 200
    request(LOCAL, '/api/auth/logout', {}, cookie=token)
    failures = [login(LOCAL, users[0], 'deliberately-wrong', forged)[0] for _ in range(10)]
    result['ten_failures_are_401'] = failures == [401] * 10
    status, headers = login(LOCAL, users[0], password, forged)
    result['eleventh_before_hash_limit'] = status == 429 and 0 < int(headers.get('Retry-After', '0')) <= 300
    # Different network path cannot bypass the username limit.
    result['username_limit_across_proxy'] = login(PUBLIC, users[0], password)[0] == 429
    status, headers = login(PUBLIC, users[1], password)
    result['other_user_can_login'] = status == 200
    if status == 200:
        request(PUBLIC, '/api/auth/logout', {}, cookie=SESSION_COOKIE + '=' + cookie(headers).value)
    result['ok'] = result['https_login'] == 200 and all(value is True for key, value in result.items() if key not in ('ok', 'https_login'))
finally:
    removed = [storage.delete_user(username) and storage.find_user(username) is None for username in created]
    result['probe_users_removed'] = len(removed) == 2 and all(removed)
    result['ok'] = result['ok'] and result['probe_users_removed']
print(json.dumps(result))
