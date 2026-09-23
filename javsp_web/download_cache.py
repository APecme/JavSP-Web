"""Single-flight downloader snapshots; slow endpoints never block a page request."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import threading
import time

from .qbittorrent import list_downloads
from .timeutils import now_iso

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='download-snapshot')
_lock = threading.Lock()
_entries = {}


def _key(settings):
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def _refresh(key, settings):
    try:
        result = dict(items=list_downloads(settings), error=None, updated_at=now_iso())
    except Exception as exc:
        result = dict(items=[], error=str(exc), updated_at=None)
    with _lock:
        if key in _entries:
            _entries[key].update(result, refreshing=False, checked=time.monotonic())


def snapshots(settings_list):
    with _lock:
        keys = {_key(settings) for settings in settings_list}
        for key in list(_entries):
            if key not in keys:
                del _entries[key]
        result = []
        for settings in settings_list:
            key = _key(settings)
            entry = _entries.setdefault(key, dict(items=[], error=None, updated_at=None, checked=0, refreshing=False))
            if not entry['refreshing'] and (not entry['checked'] or time.monotonic() - entry['checked'] >= 5):
                entry['refreshing'] = True
                _pool.submit(_refresh, key, copy.deepcopy(settings))
            result.append(dict(id=settings['id'], name=settings['name'], **copy.deepcopy(entry)))
        return result
