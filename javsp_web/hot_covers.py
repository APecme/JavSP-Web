"""Registered hot-list cover images only; no arbitrary-URL image proxy.

Remote raster bytes are bounded, decoded and re-encoded as JPEG. The bounded
process-local registry/cache is rebuilt from source lists, never user URLs.
"""
from __future__ import annotations

import hashlib
import io
import threading
import time
import warnings
from collections import OrderedDict
from urllib.parse import urljoin, urlsplit

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from .hot_network import PublicAdapter
from .hot_settings import network_options

MAX_BYTES = 5_000_000
MAX_PIXELS = 16_000_000
MAX_COVERS = 128
MAX_CACHE_BYTES = 24_000_000
MAX_REGISTERED = 2000
CACHE_SECONDS = 1800
FAILURE_SECONDS = 30
_LOCK = threading.RLock()
_CAPACITY = threading.BoundedSemaphore(4)
_registry = OrderedDict()
_cache = OrderedDict()
_failures = {}
_inflight = {}


class CoverError(Exception):
    pass


def safe_image_url(value, base):
    try:
        url = urljoin(base, str(value or '').strip())
        parsed = urlsplit(url)
        if (not value or len(url) > 2048 or parsed.scheme != 'https' or not parsed.hostname
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment):
            return ''
        if any(word in parsed.path.lower() for word in ('loading_', 'placeholder', 'website_building', '/logo.')):
            return ''
        return url
    except ValueError:
        return ''


def register(source_id, url, referer):
    url = safe_image_url(url, referer)
    if not url:
        return ''
    token = hashlib.sha256((source_id + '\n' + url + '\n' + referer).encode()).hexdigest()
    with _LOCK:
        _registry[token] = (url, referer)
        _registry.move_to_end(token)
        while len(_registry) > MAX_REGISTERED:
            removed, _ = _registry.popitem(last=False)
            _cache.pop(removed, None)
            _failures.pop(removed, None)
    return '/api/hot/covers/' + token + '.jpg'


def image_from_card(source_id, card, base):
    candidates = []
    if source_id == 'fd2ppv':
        # Prefer the product photo list to any actress-avatar img tags.
        for text in card.xpath('.//div[contains(@class,"work-photos")]/text()'):
            candidates.extend(text.splitlines()[:3])
    # Only called for verified product-card regions, not banner/ad containers.
    for image in card.xpath('.//img'):
        candidates.extend(image.get(key) for key in ('data-src', 'data-original', 'data-lazy-src', 'src')
                          if image.get(key))
    for candidate in candidates:
        url = safe_image_url(candidate, base)
        if url:
            return register(source_id, url, base)
    return ''


def _download(url, referer):
    options = network_options()
    duration = min(25, options['timeout_seconds'])
    deadline = time.monotonic() + duration
    # Do not forward CookieCloud, age-session cookies, authentication or browser
    # headers to arbitrary CDN origins. Only a public source Referer is sent.
    try:
        with requests.Session() as session:
            session.trust_env = False
            adapter = PublicAdapter()
            session.mount('https://', adapter)
            session.mount('http://', adapter)  # Reject HTTPS -> HTTP downgrade.
            session.headers.update({'Accept': 'image/jpeg,image/png,image/webp,image/gif;q=0.8',
                                    'User-Agent': 'Mozilla/5.0 JavSP-Web/Hot-Cover',
                                    'Accept-Encoding': 'identity'})
            for hop in range(5):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CoverError('封面读取超时')
                session.cookies.clear()
                kwargs = {'proxies': {'http': options['proxy_url'], 'https': options['proxy_url']}} if options['proxy_url'] else {}
                with session.get(url, headers={'Referer': referer}, stream=True, allow_redirects=False,
                                 timeout=(min(5, remaining), min(10, remaining)), **kwargs) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        target = safe_image_url(response.headers.get('Location', ''), url)
                        if not target or hop == 4:
                            raise CoverError('封面跳转无效')
                        url = target
                        continue
                    if response.status_code != 200:
                        raise CoverError('来源封面暂不可用')
                    content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
                    if content_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp', 'application/octet-stream'):
                        raise CoverError('来源没有返回可用图片')
                    try:
                        if int(response.headers.get('Content-Length', 0)) > MAX_BYTES:
                            raise CoverError('封面超过读取上限')
                    except ValueError:
                        raise CoverError('封面响应无效') from None
                    data = bytearray()
                    while True:
                        if time.monotonic() > deadline:
                            raise CoverError('封面读取超时')
                        chunk = response.raw.read1(16384, decode_content=True)
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise CoverError('封面超过读取上限')
                    return _jpeg(bytes(data))
    except CoverError:
        raise
    except Exception:
        raise CoverError('封面加载失败，请稍后重试') from None


def _jpeg(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if (original.format not in ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP') or
                        original.width * original.height > MAX_PIXELS):
                    raise CoverError('封面尺寸或格式不受支持')
                original.seek(0)
                original.load()
                image = ImageOps.exif_transpose(original)
                image.thumbnail((640, 800))
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    alpha = image.convert('RGBA')
                    rgb = Image.new('RGB', alpha.size, (242, 244, 247))
                    rgb.paste(alpha, mask=alpha.getchannel('A'))
                    image = rgb
                else:
                    image = image.convert('RGB')
                result = io.BytesIO()
                image.save(result, 'JPEG', quality=83, optimize=True)
                return result.getvalue()
    except CoverError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        raise CoverError('封面不是可解码图片') from None


def get_cover(token):
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        raise KeyError(token)
    with _LOCK:
        source = _registry.get(token)
        if not source:
            raise KeyError(token)
        cached = _cache.get(token)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            _cache.move_to_end(token)
            return cached[1]
        if token in _failures and time.monotonic() - _failures[token] < FAILURE_SECONDS:
            raise CoverError('来源封面暂不可用，请30秒后重试')
        if token in _inflight:
            event, owner = _inflight[token], False
        else:
            event, owner = threading.Event(), True
            _inflight[token] = event
    if not owner:
        if not event.wait(28):
            raise CoverError('封面正在读取，请稍后重试')
        with _LOCK:
            cached = _cache.get(token)
            if cached:
                return cached[1]
        raise CoverError('封面加载失败，请稍后重试')
    try:
        if not _CAPACITY.acquire(timeout=3):
            raise CoverError('封面请求较多，请稍后重试')
        try:
            data = _download(*source)
        finally:
            _CAPACITY.release()
        with _LOCK:
            _cache[token] = (time.monotonic(), data)
            _cache.move_to_end(token)
            while len(_cache) > MAX_COVERS or sum(len(value[1]) for value in _cache.values()) > MAX_CACHE_BYTES:
                _cache.popitem(last=False)
            _failures.pop(token, None)
        return data
    except CoverError:
        with _LOCK:
            _failures[token] = time.monotonic()
        raise
    finally:
        with _LOCK:
            _inflight.pop(token, None)
            event.set()
