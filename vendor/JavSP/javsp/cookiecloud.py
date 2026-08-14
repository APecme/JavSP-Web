"""CookieCloud cookie bridge for a single JavSP worker process."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


_cached_path = None
_cached_mtime = None
_cached_cookies = {}


def _load_cookies():
    global _cached_path, _cached_mtime, _cached_cookies
    path_text = os.environ.get("JAVSP_COOKIECLOUD_FILE", "")
    if not path_text:
        return {}
    path = Path(path_text)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _cached_path == path and _cached_mtime == mtime:
        return _cached_cookies
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    normalized = {}
    if isinstance(loaded, dict):
        for domain, values in loaded.items():
            if not isinstance(values, dict):
                continue
            host = str(domain).strip().lstrip(".").lower()
            cookies = {str(name): str(value) for name, value in values.items() if str(name) and value is not None}
            if host and cookies:
                normalized[host] = cookies
    _cached_path, _cached_mtime, _cached_cookies = path, mtime, normalized
    return normalized


def cookies_for_url(url):
    """Return CookieCloud cookies whose domain matches *url*."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return {}
    matches = [(domain, cookies) for domain, cookies in _load_cookies().items() if host == domain or host.endswith("." + domain)]
    result = {}
    for _, cookies in sorted(matches, key=lambda item: len(item[0])):
        result.update(cookies)
    return result
