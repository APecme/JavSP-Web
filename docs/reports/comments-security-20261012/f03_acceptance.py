"""F03 production acceptance, executed inside the javsp-web container.

Creates a throwaway operator, reads presets/config over HTTP, and verifies no
credential value from the real configuration is returned. Prints counts only.
"""
import json
import re
import secrets
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urlsplit

import yaml

from javsp_web import storage

BASE = 'http://127.0.0.1:8090'
SENSITIVE = re.compile(r'pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key|app[_-]?(?:id|key|secret)|'
                       r'cookies?|authori[sz]ation|credential|private[_-]?key|session|signature|uuid', re.I)


def collect(value, key='', inherited=False, found=None):
    found = set() if found is None else found
    sensitive = inherited or bool(key and SENSITIVE.search(key))
    if isinstance(value, dict):
        for k, v in value.items():
            collect(v, str(k), sensitive, found)
    elif isinstance(value, list):
        for v in value:
            collect(v, key, sensitive, found)
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value)
        if sensitive and len(text) >= 4:
            found.add(text)
        if isinstance(value, str):
            try:
                parts = urlsplit(text)
                if parts.password and len(parts.password) >= 3:
                    found.add(parts.password)
            except ValueError:
                pass
    return found


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


secrets_found = set()
sources = [yaml.safe_load(storage.read_config()) or {}]
for preset in storage.list_presets():
    sources.append(preset.get('form') or {})
    try:
        sources.append(yaml.safe_load(preset.get('content') or '') or {})
    except yaml.YAMLError:
        pass
for source in sources:
    collect(source, found=secrets_found)

username = 'f03probe' + secrets.token_hex(4)
password = secrets.token_urlsafe(24)
result = {'ok': False, 'secret_values_checked': len(secrets_found)}
storage.upsert_user(username, password, 'operator')
try:
    status, _, set_cookie = request('POST', '/api/auth/login', body={'username': username, 'password': password})
    cookie = set_cookie.split(';', 1)[0]
    result['operator_login'] = status
    presets_status, presets_body, _ = request('GET', '/api/presets', cookie)
    presets = json.loads(presets_body) if presets_status == 200 else []
    result['presets_status'] = presets_status
    result['presets_count'] = len(presets)
    result['presets_all_redacted'] = bool(presets) and all(item.get('redacted') is True for item in presets)
    result['presets_leaked_values'] = sum(1 for value in secrets_found if value in presets_body)
    convert_status, convert_body, _ = request('POST', '/api/presets/convert', cookie, {'mode': 'yaml', 'content': 'network:\n  retry: 3\n'})
    result['convert_status'] = convert_status
    result['convert_leaked_values'] = sum(1 for value in secrets_found if value in convert_body)
    result['config_status'] = request('GET', '/api/config', cookie)[0]
    result['crawler_source_status'] = request('GET', '/api/crawler-config/javbus', cookie)[0]
    result['crawler_names_status'] = request('GET', '/api/crawler-config/names', cookie)[0]
    request('POST', '/api/auth/logout', cookie)
    result['ok'] = (result['operator_login'] == 200 and presets_status == 200 and result['presets_all_redacted']
                    and result['presets_leaked_values'] == 0 and convert_status == 200 and result['convert_leaked_values'] == 0
                    and result['config_status'] == 403 and result['crawler_source_status'] == 403
                    and result['crawler_names_status'] == 200)
finally:
    result['probe_user_removed'] = storage.delete_user(username) and storage.find_user(username) is None
    result['ok'] = result['ok'] and result['probe_user_removed']
print(json.dumps(result))
