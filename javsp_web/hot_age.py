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
                'message': state.get('message', ''),
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
        _jobs[id] = {'running': True, 'started': time.monotonic(), 'message': '正在读取并核对原站年龄声明…'}
        try:
            threading.Thread(target=_run, args=(id, on_result), name='hot-age-' + id, daemon=True).start()
        except Exception:
            _jobs[id]['running'] = False
            raise ValueError('无法启动确认任务，请稍后重试') from None
        return status(id)


def _run(id, on_result):
    started = time.monotonic()
    result = {'checked_at': '', 'http_status': None, 'responded': False}
    try:
        from .storage import get_cookiecloud_settings
        from .cookiecloud import get_synced_cookies, CookieCloudError
        cookie_domains = None
        if get_cookiecloud_settings().get('enabled'):
            try:
                cookie_domains = get_synced_cookies()
            except CookieCloudError:
                raise NetworkError('cookiecloud_error', 'CookieCloud 同步失败，请检查配置') from None
        with requests.Session() as session:
            session.cookies.update(cookies(id))
            code, url, page = read_html(BY_ID[id]['url'], session=session, cookie_domains=cookie_domains, allowed_hosts=_hosts(id))
            state, message = classify(code, url, page)
            if state == 'age_gate':
                flow = action(id, url, page)
                if not flow:
                    raise NetworkError('age_gate', '未识别到可安全提交的普通年龄声明，请在原站确认或使用 CookieCloud')
                method, destination, form = flow
                code, url, page = read_html(destination, session=session, request_method=method,
                                           form_data=form, cookie_domains=cookie_domains, allowed_hosts=_hosts(id))
                state, message = classify(code, url, page)
                # Always recheck the original source with the returned cookie jar.
                if state not in ('challenge', 'region_blocked', 'denied', 'http_error'):
                    code, url, page = read_html(BY_ID[id]['url'], session=session, cookie_domains=cookie_domains, allowed_hosts=_hosts(id))
                    state, message = classify(code, url, page)
            if state == 'ok':
                jar = requests.cookies.RequestsCookieJar()
                for cookie in session.cookies:
                    domain = cookie.domain.lstrip('.').lower()
                    if (cookie.name and len(cookie.value) <= 8192 and
                            domain in _cookie_domains(id)):
                        jar.set_cookie(copy.copy(cookie))
                with _LOCK:
                    _sessions[id] = {'expires': time.monotonic() + TTL, 'jar': jar}
                message = '已提交/核对年龄声明并重检，普通网页可达；会话仅保存在服务内存'
            elif state == 'age_gate':
                message = '已尝试确认，但原站仍要求年龄确认；请在原站操作或使用 CookieCloud'
            result.update(state=state, message=message, http_status=code, responded=True)
    except NetworkError as error:
        result.update(state=error.state, message=error.message)
    except Exception:
        result.update(state='error', message='确认未完成，请在原站操作或使用 CookieCloud')
    finally:
        from datetime import datetime, timezone
        result['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        # Publish the fresh connection result BEFORE marking the task finished.
        # A polling client must never see done + stale age_gate at the boundary.
        try:
            on_result(id, result)
        finally:
            with _LOCK:
                _jobs[id].update(running=False, message=result['message'])
