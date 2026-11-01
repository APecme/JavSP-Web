"""Explicit adult self-declaration only; no automated ID/login/captcha solving.

Fixed per-site flows must be present in the current age-gate HTML before any
submission. Cookies are process-local, source-scoped and expire after 12 hours.
"""
from __future__ import annotations

import copy
import threading
import time
from urllib.parse import urljoin, urlsplit, parse_qs

import lxml.html
import requests

from .hot_sources import BY_ID
from .hot_network import read_html, classify, NetworkError
from .hot_settings import network_options

SUPPORTED = {'dmm', 'fanza', 'giga', 'xcity', 'javbus', 'aventertainments'}
_LOCK = threading.RLock()
_sessions = {}
_jobs = {}
TTL = 12 * 3600
COOLDOWN = 60


def _hosts(id):
    if id in ('dmm', 'fanza'):
        return {'www.dmm.co.jp', 'video.dmm.co.jp'}
    return {urlsplit(BY_ID[id]['url']).hostname}


def _cookie_domains(id):
    # Explicit parent domains, not arbitrary suffixes such as co.jp/com.
    if id in ('dmm', 'fanza'):
        return {'www.dmm.co.jp', 'video.dmm.co.jp', 'dmm.co.jp'}
    host = next(iter(_hosts(id)))
    return {host, host.removeprefix('www.')}


def cookies(id):
    with _LOCK:
        state = _sessions.get(id, {})
        if time.monotonic() >= state.get('expires', 0):
            _sessions.pop(id, None)
            return requests.cookies.RequestsCookieJar()
        return copy.deepcopy(state['jar'])


def status(id):
    with _LOCK:
        state = _jobs.get(id, {})
        return {'supported': id in SUPPORTED, 'running': state.get('running', False),
                'message': state.get('message', ''), 'phase': state.get('phase', 'idle'),
                'completed_at': state.get('completed_at', ''), 'success': state.get('success', False),
                'retry_after': max(0, int(COOLDOWN - (time.monotonic() - state.get('started', -COOLDOWN))))}


def action(id, url, text):
    """Return only a previously verified first-party action found on this page."""
    try:
        tree = lxml.html.fromstring(text)
    except (ValueError, lxml.etree.ParserError):
        return None
    for a in tree.xpath('//a[@href]'):
        href = urljoin(url, a.get('href'))
        p = urlsplit(href)
        if p.scheme != 'https' or p.hostname not in _hosts(id) or p.username or p.password or p.port not in (None,443):
            continue
        qs = parse_qs(p.query)
        if id in ('dmm', 'fanza') and p.hostname == 'www.dmm.co.jp' and p.path == '/age_check/=/declared=yes/':
            targets = qs.get('rurl', [])
            expected = BY_ID[id]['url'] if id == 'dmm' else 'https://www.dmm.co.jp/top/'
            if targets != [expected]:
                continue
            return 'GET', href, None
        if id == 'giga' and p.path == '/cookie_set.php' and not p.query:
            return 'GET', href, None
        if id == 'xcity' and p.path == '/' and qs.get('over18') == ['ok'] and qs.get('r') == ['/']:
            return 'GET', href, None
        if id == 'aventertainments' and p.path == '/dvd/index' and qs == {'lang':['2'],'cat':['29']}:
            return 'GET', href, None
    if id == 'javbus' and urlsplit(url).hostname == 'www.javbus.com':
        for form in tree.xpath('//form[@id="form1"]'):
            destination = urljoin(url, form.get('action') or url)
            p = urlsplit(destination)
            # Only this known single-checkbox self-declaration; reject additional
            # required inputs, CAPTCHA, ID upload, login or changed submission.
            inputs = form.xpath('.//input|.//select|.//textarea|.//button')
            if (p.scheme != 'https' or p.netloc != 'www.javbus.com'
                    or p.path != '/doc/driver-verify' or (form.get('method') or '').lower() != 'post'):
                continue
            check = form.xpath('.//input[@type="checkbox" and not(@name)]')
            submit = form.xpath('.//input[@type="submit" and @name="Submit" and @value="確認"]')
            if len(inputs) == 2 and len(check) == 1 and len(submit) == 1 and '成年' in form.text_content():
                return 'POST', destination, {'Submit': '確認'}
    return None


def start(id, confirmed, on_result):
    if id not in BY_ID:
        raise ValueError('站点不存在')
    if not confirmed:
        raise ValueError('请先确认已达到该站点要求的法定年龄')
    if id not in SUPPORTED:
        raise ValueError('此站尚未适配普通年龄声明，请在原站操作或使用 CookieCloud')
    with _LOCK:
        if _jobs.get(id, {}).get('running'):
            return status(id)
        if status(id)['retry_after']:
            raise ValueError('该站确认正在冷却，请稍后重试')
        _jobs[id] = {'running': True, 'started': time.monotonic(), 'message': '正在读取并核对原站年龄声明…', 'phase': 'reading', 'success': False}
        try:
            threading.Thread(target=_run, args=(id, on_result), name='hot-age-' + id, daemon=True).start()
        except Exception:
            _jobs[id]['running'] = False
            raise ValueError('无法启动确认任务，请稍后重试') from None
        return status(id)


def _phase(id, phase, message):
    with _LOCK:
        _jobs[id].update(phase=phase, message=message)


def source_url(id):
    with _LOCK:
        state = _sessions.get(id, {})
        if state.get('expires', 0) > time.monotonic():
            return state.get('verified_url') or BY_ID[id]['url']
    return BY_ID[id]['url']


def _run(id, on_result):
    started = time.monotonic()
    result = {'checked_at': '', 'http_status': None, 'responded': False, 'reachable': False}
    verified_url = BY_ID[id]['url']
    try:
        from .storage import get_cookiecloud_settings
        from .cookiecloud import get_synced_cookies, CookieCloudError
        cookie_domains = None
        options = network_options()
        if get_cookiecloud_settings().get('enabled'):
            try:
                cookie_domains = get_synced_cookies()
            except CookieCloudError:
                raise NetworkError('cookiecloud_error', 'CookieCloud 同步失败，请检查配置') from None
        with requests.Session() as session:
            session.cookies.update(cookies(id))
            initial = source_url(id)
            _phase(id, 'reading', '正在读取原站年龄页面…')
            code, url, page = read_html(initial, session=session, cookie_domains=cookie_domains,
                                       allowed_hosts=_hosts(id), **options)
            state, message = classify(code, url, page)
            if state == 'age_gate':
                flow = action(id, url, page)
                if not flow:
                    raise NetworkError('age_gate', '当前页面确认方式未适配或已改变，请在原站完成后使用 CookieCloud')
                method, destination, form = flow
                session.headers['Referer'] = url
                if method == 'POST':
                    p = urlsplit(url)
                    session.headers['Origin'] = p.scheme + '://' + p.netloc
                _phase(id, 'submitting', '已核对原站声明，正在提交确认…')
                code, url, page = read_html(destination, session=session, request_method=method,
                                           form_data=form, cookie_domains=cookie_domains,
                                           allowed_hosts=_hosts(id), **options)
                state, message = classify(code, url, page)
                if state not in ('challenge', 'region_blocked', 'denied', 'http_error'):
                    _phase(id, 'verifying', '已提交，正在使用同一会话验证网页…')
                    # AV Entertainment root is a permanent language/age landing
                    # page: its original first-party entry, not '/', is the proof.
                    verified_url = destination if id == 'aventertainments' else BY_ID[id]['url']
                    code, url, page = read_html(verified_url, session=session, cookie_domains=cookie_domains,
                                               allowed_hosts=_hosts(id), **options)
                    state, message = classify(code, url, page)
            if state in ('ok', 'js_shell'):
                jar = requests.cookies.RequestsCookieJar()
                for cookie in session.cookies:
                    domain = cookie.domain.lstrip('.').lower()
                    if cookie.name and len(cookie.value) <= 8192 and domain in _cookie_domains(id):
                        jar.set_cookie(copy.copy(cookie))
                with _LOCK:
                    _sessions[id] = {'expires': time.monotonic() + TTL, 'jar': jar, 'verified_url': verified_url}
                message = ('年龄声明已验证，HTTP 已连通；页面仍需 JavaScript 渲染' if state == 'js_shell' else
                           '年龄声明已验证并重检成功；服务端会话已保存')
            elif state == 'age_gate':
                message = '原站仍返回年龄页；本次确认未生效，请在原站完成后使用 CookieCloud'
            result.update(state=state, message=message, http_status=code, responded=True,
                          reachable=200 <= code < 400)
    except NetworkError as error:
        result.update(state=error.state, message=error.message)
    except Exception:
        result.update(state='error', message='确认未完成，请在原站操作或使用 CookieCloud')
    finally:
        from datetime import datetime, timezone
        result['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        try:
            on_result(id, result)
        finally:
            with _LOCK:
                _jobs[id].update(running=False, message=result['message'], phase='finished',
                                 success=result['state'] in ('ok', 'js_shell'), completed_at=result['checked_at'])
