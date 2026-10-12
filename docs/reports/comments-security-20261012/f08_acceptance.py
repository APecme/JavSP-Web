"""F07/F08 main-app acceptance, executed inside the javsp-web container.

Uses a throwaway operator to verify the comment-session clear endpoint and that
the served page/script contain the sign-out, PIN change and handle-login UI.
"""
import json
import re
import secrets
import urllib.request
from urllib.error import HTTPError

from javsp_web import storage

BASE = 'http://127.0.0.1:8090'


def request(method, path, cookie=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={'Content-Type': 'application/json'})
    if cookie:
        req.add_header('Cookie', cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, response.read().decode(), response.headers.get('Set-Cookie') or ''
    except HTTPError as exc:
        return exc.code, exc.read().decode(), ''


username = 'f08probe' + secrets.token_hex(4)
password = secrets.token_urlsafe(24)
result = {'ok': False}
storage.upsert_user(username, password, 'operator')
try:
    status, _, set_cookie = request('POST', '/api/auth/login', body={'username': username, 'password': password})
    cookie = set_cookie.split(';', 1)[0]
    result['login'] = status
    result['clear_anonymous'] = request('DELETE', '/api/profile/community')[0]
    fake = secrets.token_urlsafe(48)
    status, body, _ = request('PUT', '/api/profile/community', cookie, {'display_name': 'probe#AB12', 'comment_username': 'probe', 'avatar_id': '', 'comment_token': fake})
    result['set_identity'] = status
    status, body, _ = request('DELETE', '/api/profile/community', cookie)
    cleared = json.loads(body) if status == 200 else {}
    result['clear'] = status
    result['cleared_identity_not_ready'] = cleared.get('identity_ready') is False
    result['cleared_token_rotated'] = bool(cleared.get('comment_token')) and cleared.get('comment_token') != fake
    status, page, _ = request('GET', '/', cookie)
    result['page_has_signout_ui'] = all(marker in page for marker in ('identity-logout', 'identity-logout-all', 'value="pin"', 'maxlength="29"'))
    script_path = re.search(r'src="(/[^"]*community\.js[^"]*)"', page)
    script = request('GET', script_path.group(1), cookie)[1] if script_path else ''
    result['script_has_endpoints'] = all(marker in script for marker in ('/api/me/logout-all', '/api/me/pin', "method:'DELETE'"))
    request('POST', '/api/auth/logout', cookie)
    result['ok'] = (result['login'] == 200 and result['clear_anonymous'] == 401 and result['set_identity'] == 200
                    and result['clear'] == 200 and result['cleared_identity_not_ready'] and result['cleared_token_rotated']
                    and result['page_has_signout_ui'] and result['script_has_endpoints'])
finally:
    result['probe_user_removed'] = storage.delete_user(username) and storage.find_user(username) is None
    result['ok'] = result['ok'] and result['probe_user_removed']
print(json.dumps(result))
