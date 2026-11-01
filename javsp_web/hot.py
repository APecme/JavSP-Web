"""Hot-page lists and single-flight, bounded background connectivity batches.

Only fixed HTML sources are read. Cached results are process-local and expire;
failures preserve the last successful list and are never treated as empty lists.
"""
from __future__ import annotations

import copy
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import lxml.html

from .hot_network import NetworkError, classify, read_html
from .hot_sources import BY_ID, FEEDS, SOURCES
from .hot_catalog import merge_items
from .hot_covers import image_from_card
from . import hot_age
from .hot_settings import network_options, public_network

CHECK_COOLDOWN = 60
FEED_COOLDOWN = 120
CACHE_SECONDS = 1800
MAX_ITEMS = 40
_LOCK = threading.RLock()
_check = {}
_checks = {}
_single_checks = {}
_check_revisions = {}
_feed_job = {}
_cache = {}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _idle():
    return {'running': False, 'completed': 0, 'total': 0, 'started_at': '', 'finished_at': ''}


def _public_job(job, cooldown):
    result = {key: value for key, value in (job or _idle()).items() if key != 'started_mono'}
    result['retry_after'] = max(0, round(cooldown - (time.monotonic() - job.get('started_mono', -cooldown)))) if job else 0
    return result


def connections():
    with _LOCK:
        return {'job': _public_job(_check, CHECK_COOLDOWN), 'network_mode': 'default_preset', 'network': public_network(),
                'sources': [dict(BY_ID[id], probing=_single_checks.get(id, {}).get('running', False), age=hot_age.status(id), result=copy.deepcopy(_checks.get(id, {
                    'state': 'unchecked', 'message': '尚未检测', 'checked_at': '', 'http_status': None,
                    'elapsed_ms': None, 'responded': False}))) for id, _, _ in SOURCES]}


def _probe(source):
    start = time.monotonic()
    result = {'checked_at': now(), 'http_status': None, 'responded': False}
    try:
        code, url, text = _read_source(hot_age.source_url(source['id']), source['id'])
        state, message = classify(code, url, text)
        result.update(state=state, message=message, http_status=code, responded=True, reachable=200 <= code < 400)
    except NetworkError as error:
        result.update(state=error.state, message=error.message)
    except Exception:
        result.update(state='error', message='检测未完成，请重试')
    result['elapsed_ms'] = round((time.monotonic() - start) * 1000)
    return result


def _run_checks():
    try:
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix='hot-probe') as pool:
            with _LOCK:
                revisions = dict(_check_revisions)
            pending = {pool.submit(_probe, BY_ID[id]): id for id, _, _ in SOURCES}
            for future in as_completed(pending):
                id = pending[future]
                try:
                    result = future.result()
                except Exception:
                    result = {'state': 'error', 'message': '检测失败', 'checked_at': now(),
                              'http_status': None, 'elapsed_ms': None, 'responded': False}
                with _LOCK:
                    age_status = hot_age.status(id)
                    newer = _checks.get(id, {}).get('checked_at', '') > result.get('checked_at', '')
                    if not age_status.get('running') and not newer and _check_revisions.get(id, 0) == revisions.get(id, 0):
                        _checks[id] = result
                    _check['completed'] += 1
    finally:
        with _LOCK:
            _check.update(running=False, finished_at=now())


def start_checks():
    with _LOCK:
        if _check.get('running'):
            return connections()
        if _public_job(_check, CHECK_COOLDOWN)['retry_after']:
            return connections()
        _check.clear()
        _check.update(running=True, completed=0, total=len(SOURCES), started_at=now(),
                      finished_at='', started_mono=time.monotonic())
        try:
            threading.Thread(target=_run_checks, name='hot-check-batch', daemon=True).start()
        except Exception:
            _check.update(running=False, finished_at=now())
            raise
        return connections()


def retry_source(id):
    if id not in BY_ID:
        raise ValueError('站点不存在')
    with _LOCK:
        current = _single_checks.get(id, {})
        if current.get('running'):
            return connections()
        if sum(bool(job.get('running')) for job in _single_checks.values()) >= 3:
            raise ValueError('单站重测最多同时3站，请稍后再试')
        if _check.get('running') or hot_age.status(id)['running']:
            raise ValueError('站点正在检测或确认年龄，请等待当前任务结束')
        if time.monotonic() - current.get('started', -30) < 30:
            raise ValueError('单站重测请间隔30秒')
        _single_checks[id] = {'running': True, 'started': time.monotonic()}
        version = _check_revisions.get(id, 0)
        def run():
            try:
                result = _probe(BY_ID[id])
                with _LOCK:
                    if not hot_age.status(id)['running'] and _check_revisions.get(id, 0) == version:
                        _checks[id] = result
            finally:
                with _LOCK:
                    _single_checks[id]['running'] = False
        try:
            threading.Thread(target=run, name='hot-retry-' + id, daemon=True).start()
        except Exception:
            _single_checks[id]['running'] = False
            raise ValueError('无法开始重测，请稍后再试') from None
        return connections()


def _text(node, xpath):
    values = node.xpath(xpath)
    return ' '.join(' '.join(x.itertext()) if hasattr(x, 'itertext') else str(x) for x in values).strip()


def _date(text):
    match = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', text)
    if not match:
        return ''
    try:
        return datetime(*(int(x) for x in match.groups())).date().isoformat()
    except ValueError:
        return ''


def _item(id, category, url, title, identifier, date='', rank=None):
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != urlsplit(BY_ID[id]['url']).hostname:
        return None
    if not title or not identifier:
        return None
    return {'actors': [], 'tags': [], 'studio': '', 'seller': '', 'date_kind': '来源日期',
            'id': id + ':' + identifier, 'source_id': id, 'source_name': BY_ID[id]['name'],
            'category': category, 'url': url, 'title': title[:500], 'identifier': identifier[:80],
            'date': date, 'rank': rank, 'cover': ''}


def parse_feed(id, category, sort, page, url):
    """Extract only verified list regions. No arbitrary anchors/advertising fallback."""
    try:
        tree = lxml.html.fromstring(page)
    except (ValueError, lxml.etree.ParserError):
        raise NetworkError('parse_error', '无法解析来源页面') from None
    items = []
    cls = lambda name: f"contains(concat(' ',normalize-space(@class),' '),' {name} ')"
    if id == 'fd2ppv':
        seen = set()
        for card in tree.xpath(f'//div[{cls("artist-card")}]'):
            hrefs = card.xpath('.//h3/a[starts-with(@href,"/articles/")]/@href')
            if not hrefs or hrefs[0] in seen:
                continue
            match = re.fullmatch(r'/articles/(\d+)', hrefs[0])
            if not match:
                continue
            kind = 'uncensored' if card.xpath('.//i[contains(@class,"icon-mosaic_free")]') else (
                'censored' if card.xpath('.//i[contains(@class,"icon-mosaic_yes")]') else 'unknown')
            item = _item(id, kind, urljoin(url, hrefs[0]),
                         _text(card, './/div[contains(@class,"artist-content")]/a'), 'FC2-' + match[1],
                         _date(_text(card, './/div[contains(@class,"artist-release")]')),
                         len(items) + 1 if sort == 'hot' else None)
            if not item:
                continue
            item['cover'] = image_from_card(id, card, url)
            item['tags'] = [_text(a, '.')[:60] for a in card.xpath('.//div[contains(@class,"artist-tags")]/a')][:15]
            item['actors'] = [_text(a, '.')[:80] for a in card.xpath('.//div[contains(@class,"articles-avatar")]//a') if _text(a, '.')][:15]
            for metric, icon in [('views', 'remove_red_eye'), ('favorites', 'icon-favorite'), ('comments', 'textsms')]:
                raw = _text(card, f'.//div[{cls("stat-item")}][.//i[contains(@class,"{icon}")]]/span[contains(@class,"stat-value")]')
                if raw.isdigit():
                    item[metric] = int(raw)
            items.append(item)
            seen.add(hrefs[0])
    elif id == 'freejavbt':
        for card in tree.xpath(f'//div[{cls("card")}]'):
            identifier = _text(card, f'.//*[{cls("card-title")}]')
            title = _text(card, f'.//*[{cls("card-text")}]')
            hrefs = card.xpath('.//div[contains(@class,"card-body")]/a/@href')
            # Exclude sponsored/non-product cards; do not normalize invented IDs.
            if not re.fullmatch(r'[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+', identifier) or not hrefs:
                continue
            item = _item(id, category, urljoin(url, hrefs[0]), title, identifier,
                         _date(_text(card, './/span[contains(@class,"text-muted")]')),
                         len(items) + 1 if sort == 'hot' else None)
            if item:
                item['cover'] = image_from_card(id, card, url)
                item['tags'] = [_text(tag, '.').lstrip('#')[:60] for tag in card.xpath('.//div[contains(@class,"video-list-item-genres")]/span') if _text(tag, '.').strip()][:15]
                items.append(item)
    elif id in ('faleno', 'dahlia'):
        if sort == 'hot':
            if id == 'faleno':
                cards = tree.xpath(f'//div[{cls("box_ranking01")}]//div[{cls("waku_ranking01")}]')
            else:
                cards = tree.xpath(f'//div[{cls("ranking-box")}]')
        else:
            # Verified release banners have a main_text date. Do not select all
            # /works/ links: doing so would mix ads and rankings into latest.
            cards = tree.xpath('//a[contains(@href,"/works/") and .//*[contains(@class,"main_text")]]')
        seen = set()
        for card in cards:
            hrefs = [card.get('href')] if sort == 'latest' else card.xpath('.//a[contains(@href,"/works/")]/@href')
            if not hrefs:
                continue
            href = urljoin(url, hrefs[0])
            match = re.search(r'/works/([a-z]+)(\d+)/?$', urlsplit(href).path, re.I)
            if not match or href in seen:
                continue
            identifier = f'{match[1].upper()}-{match[2]}'
            if sort == 'hot':
                title = _text(card, f'.//*[{cls("text_name")}]//a' if id == 'faleno'
                              else f'.//*[{cls("ranking-title")}]//a')
                date = _date(_text(card, './/div[contains(@class,"text_ranking01")][span[contains(text(),"配信日")]]/p')) if id == 'faleno' else ''
                rank = len(items) + 1
            else:
                title = _text(card, './/img/@alt')
                # Desktop and mobile banners repeat alt text; take the first.
                alts = card.xpath('.//img/@alt')
                title = alts[0].strip() if alts else title
                date, rank = _date(_text(card, './/*[contains(@class,"main_text")]')), None
                if not date:
                    continue
            item = _item(id, category, href, title, identifier, date, rank)
            if item:
                item['cover'] = image_from_card(id, card, url)
                item['studio'] = BY_ID[id]['name']
                item['date_kind'] = '配信日期'
                actor = _text(card, './/div[contains(@class,"text_ranking01")][span[contains(text(),"出演女優")]]/p') if id == 'faleno' else _text(card, './/div[contains(@class,"ranking-actress")]/div')
                item['actors'] = [a.strip() for a in re.split(r'[/／、]', actor) if a.strip()][:15]
                seen.add(href)
                items.append(item)
    if not items:
        raise NetworkError('parse_error', '未识别到作品列表；可能是页面变更或访问拦截')
    # Sort actual list dates, put unknown dates last; never call index "heat".
    if sort == 'latest':
        items.sort(key=lambda item: item['date'], reverse=True)
    return items[:MAX_ITEMS]


def _read_source(url, source_id=None):
    from .storage import get_cookiecloud_settings
    from .cookiecloud import get_synced_cookies, CookieCloudError
    cookie_domains = None
    if get_cookiecloud_settings().get('enabled'):
        try:
            cookie_domains = get_synced_cookies()
        except CookieCloudError:
            raise NetworkError('cookiecloud_error', 'CookieCloud 同步失败，请在系统设置测试连接并立即同步') from None
    if source_id in hot_age.SUPPORTED:
        return hot_age.read_automatically(source_id, url, reader=read_html, cookie_domains=cookie_domains, **network_options())
    jar = hot_age.cookies(source_id) if source_id else None
    options = network_options()
    if cookie_domains is not None:
        options['cookie_domains'] = cookie_domains
    if jar:
        import requests
        with requests.Session() as session:
            session.cookies.update(jar)
            return read_html(url, session=session, **options)
    return read_html(url, **options)


def confirm_age(source_id, confirmed):
    def record(id, result):
        with _LOCK:
            _check_revisions[id] = _check_revisions.get(id, 0) + 1
            _checks[id] = result
    with _LOCK:
        if _single_checks.get(source_id, {}).get('running'):
            raise ValueError('该站正在重测，请完成后再确认年龄')
        return hot_age.start(source_id, confirmed, record)


def _refresh_feed(feed):
    id, category, sort, url, label = feed
    try:
        code, final_url, page = _read_source(url, id)
        state, message = classify(code, final_url, page)
        if state != 'ok':
            raise NetworkError(state, message)
        items = parse_feed(id, category, sort, page, final_url)
        return {'items': items, 'fetched_at': now(), 'success_mono': time.monotonic(),
                'state': 'ok', 'message': '', 'checked_at': now()}
    except NetworkError as error:
        return {'state': error.state, 'message': error.message, 'checked_at': now()}
    except Exception:
        return {'state': 'error', 'message': '来源读取失败', 'checked_at': now()}


def _selected(category, sort):
    return [feed for feed in FEEDS if feed[2] == sort and (category == 'all' or feed[1] in (category, 'all'))]


def _key(feed):
    return ':'.join(feed[:3])


def films(category='all', sort='latest'):
    with _LOCK:
        groups = []
        for feed in _selected(category, sort):
            id, kind, _, url, label = feed
            cached = _cache.get(_key(feed), {})
            groups.append({'id': _key(feed), 'source_id': id, 'source_name': BY_ID[id]['name'],
                           'category': kind, 'label': label, 'url': url,
                           'items': [copy.deepcopy(i) for i in cached.get('items', []) if category == 'all' or i['category'] == category],
                           'state': cached.get('state', 'not_loaded'),
                           'message': cached.get('message', '尚未获取列表'),
                           'fetched_at': cached.get('fetched_at', ''),
                           'checked_at': cached.get('checked_at', ''),
                           'stale': bool(cached.get('items') and (cached.get('state') != 'ok' or
                               time.monotonic() - cached.get('success_mono', 0) > CACHE_SECONDS))})
        items = merge_items(groups, sort)
        return {'category': category, 'sort': sort, 'groups': groups, 'items': items,
                'total': len(items),
                'job': _public_job(_feed_job, FEED_COOLDOWN),
                'notice': '统一展示4站已接入作品并按可信番号去重；最新按日期降序，最热按来源名次交错排列，不是统一销量/评分。未知码类仅在全部显示。'}


def _run_feeds(feeds):
    try:
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix='hot-list') as pool:
            pending = {pool.submit(_refresh_feed, feed): feed for feed in feeds}
            for future in as_completed(pending):
                feed = pending[future]
                try:
                    result = future.result()
                except Exception:
                    result = {'state': 'error', 'message': '来源读取失败', 'checked_at': now()}
                with _LOCK:
                    _cache[_key(feed)] = dict(_cache.get(_key(feed), {}), **result)
                    _feed_job['completed'] += 1
    finally:
        with _LOCK:
            _feed_job.update(running=False, finished_at=now())


def refresh_films(category='all', sort='latest'):
    with _LOCK:
        if _feed_job.get('running'):
            return films(category, sort)
        # Cooldown per feed, not per filter: switching tabs can fetch a new feed,
        # repeatedly switching tabs cannot force the same external requests.
        feeds = [f for f in _selected(category, sort)
                 if time.monotonic() - _cache.get(_key(f), {}).get('attempt_mono', -FEED_COOLDOWN) >= FEED_COOLDOWN]
        if not feeds:
            return films(category, sort)
        start = time.monotonic()
        for feed in feeds:
            _cache.setdefault(_key(feed), {})['attempt_mono'] = start
        _feed_job.clear()
        _feed_job.update(running=True, completed=0, total=len(feeds), started_at=now(),
                         finished_at='', started_mono=start)
        try:
            threading.Thread(target=_run_feeds, args=(feeds,), name='hot-feed-batch', daemon=True).start()
        except Exception:
            _feed_job.update(running=False, finished_at=now())
            for feed in feeds:
                _cache[_key(feed)].pop('attempt_mono', None)
            raise
        return films(category, sort)
