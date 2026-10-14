from __future__ import annotations

import time
import os
import socket
import struct
import re
import hashlib
import threading
from urllib.parse import quote
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests

from .storage import list_media_servers, list_path_mappings


def _docker_host_gateway() -> str | None:
    """Return Docker's current bridge gateway without relying on a DNS alias."""
    try:
        with open("/proc/net/route", encoding="ascii") as routes:
            for line in routes.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except (OSError, ValueError, struct.error):
        return None
    return None


def _service_url(server: dict) -> str:
    """Resolve Docker-local localhost to the container's host bridge gateway."""
    value = str(server.get("url") or "").strip().rstrip("/")
    in_docker = os.path.exists("/.dockerenv") or os.environ.get("JAVSP_WEB_DOCKER") == "1"
    parsed = urlsplit(value)
    if not in_docker or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return value
    host = _docker_host_gateway() or "host.docker.internal"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment)).rstrip("/")


def _headers(server: dict) -> dict[str, str]:
    key = str(server.get("api_key") or "").strip()
    headers = {"Accept": "application/json"}
    if key:
        headers["X-Emby-Token"] = key
        if server.get("type") == "jellyfin":
            headers["Authorization"] = ('MediaBrowser Client="JavSP Web", Device="Server", '
                                        'DeviceId="javsp-web", Version="1.0", Token="' + key.replace('"', '') + '"')
    return headers


def _params(server: dict, **params: object) -> dict[str, object]:
    return dict(params)


def connection_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        reason = {401: "认证未通过，请确认密钥属于当前服务器且未被撤销", 403: "密钥没有读取媒体库的权限"}.get(status, "请检查服务地址与权限")
        return f"HTTP {status}：{reason}"
    if isinstance(exc, requests.Timeout):
        return "请求超时，请检查服务地址与网络"
    return "无法读取媒体服务器，请检查地址、网络及返回数据"


def sync_media_server(server: dict) -> dict:
    libraries = [str(value) for value in (server.get("libraries") or []) if str(value).strip()]
    targets = libraries or [None]
    for library_id in targets:
        params = _params(server)
        if library_id:
            params["LibraryId"] = library_id
        response = requests.post(f"{_service_url(server)}/Library/Refresh", params=params, headers=_headers(server), timeout=30)
        response.raise_for_status()
    return {"id": server["id"], "name": server["name"], "ok": True, "message": "媒体库扫描已启动"}


def list_media_libraries(server: dict) -> list[dict]:
    response = requests.get(
        f"{_service_url(server)}/Library/VirtualFolders",
        params=_params(server),
        headers=_headers(server),
        timeout=20,
    )
    if response.status_code in (401, 403) and server.get("type") == "jellyfin":
        response = requests.get(f"{_service_url(server)}/Library/MediaFolders", headers=_headers(server), timeout=20)
    response.raise_for_status()
    libraries = []
    data = response.json() or []
    for item in data.get("Items", []) if isinstance(data, dict) else data:
        if not isinstance(item, dict):
            continue
        libraries.append({"id": str(item.get("ItemId") or item.get("Id") or item.get("Name") or ""), "name": str(item.get("Name") or item.get("CollectionType") or "未命名媒体库"),
                          "locations": list(item.get("Locations") or ([item["Path"]] if item.get("Path") else []))})
    return [item for item in libraries if item["id"]]


_LIBRARY_CACHE: dict[str, tuple[float, list[dict]]] = {}
_LIBRARY_CACHE_SECONDS = 300
_LIBRARY_FAILURE_SECONDS = 60


def _local_roots(root: str, mappings: list[dict]) -> list[str]:
    """Translate a media-server library path into the paths JavSP writes to."""
    normalize = lambda value: str(value or "").replace("\\", "/").rstrip("/")
    root = normalize(root)
    roots = [root] if root else []
    for mapping in mappings:
        remote, local = normalize(mapping.get("source_path")), normalize(mapping.get("target_path"))
        if remote and local and (root.casefold() == remote.casefold() or root.casefold().startswith(remote.casefold() + "/")):
            roots.append(local + root[len(remote):])
    return list(dict.fromkeys(roots))


def overview_libraries() -> list[dict]:
    """Selected media libraries with local folder roots, cached to keep overview polling cheap."""
    mappings = list_path_mappings()
    result = []
    for server in list_media_servers():
        if not server.get("url") or not server.get("api_key"):
            continue
        cache_key = "|".join([str(server.get("id")), str(server.get("url")), str(server.get("api_key")), ",".join(map(str, server.get("libraries") or []))])
        cached = _LIBRARY_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            libraries = cached[1]
        else:
            try:
                libraries = list_media_libraries(server)
                _LIBRARY_CACHE[cache_key] = (time.monotonic() + _LIBRARY_CACHE_SECONDS, libraries)
            except (OSError, ValueError, requests.RequestException):
                libraries = cached[1] if cached else []
                _LIBRARY_CACHE[cache_key] = (time.monotonic() + _LIBRARY_FAILURE_SECONDS, libraries)
        selected = set(server.get("libraries") or [])
        for library in libraries:
            if selected and library["id"] not in selected:
                continue
            roots = [local for root in library.get("locations") or [] for local in _local_roots(root, mappings)]
            result.append({"key": f"{server['id']}:{library['id']}", "name": library["name"], "server": server.get("name", ""), "roots": roots})
    return result


def playback_links(task: dict) -> list[dict]:
    """Match output paths to selected libraries, then resolve the server's item page."""
    output = (task.get("progress") or {}).get("output") or {}
    folder = str(output.get("save_dir") or task.get("input_directory") or "")
    identifier = str(((task.get("progress") or {}).get("metadata") or {}).get("dvdid") or "")
    normalize = lambda value: str(value).replace("\\", "/").rstrip("/").casefold()
    paths = [normalize(folder)]
    for value in (task.get('file_organizer') or {}).get('organized_files') or []:
        parent = normalize(value).rsplit('/', 1)[0]
        if parent:
            paths.append(parent)
    for mapping in list_path_mappings():
        local, remote = normalize(mapping.get("target_path")), normalize(mapping.get("source_path"))
        if local and (paths[0] == local or paths[0].startswith(local + "/")):
            paths.append(remote + paths[0][len(local):])
    links = []
    for server in list_media_servers():
        external = urlsplit(str(server.get("external_url") or server.get('url') or "").strip())
        if external.scheme not in ("http", "https") or not external.netloc:
            continue
        base_path = external.path.rstrip("/")
        for suffix in ("/web/index.html", "/web"):
            if base_path.endswith(suffix):
                base_path = base_path[:-len(suffix)]
                break
        base = urlunsplit((external.scheme, external.netloc, base_path, "", ""))
        libraries = list_media_libraries(server)
        selected = set(server.get("libraries") or [])
        matched = [library for library in libraries if (not selected or library["id"] in selected)
                   and any(path == normalize(root) or path.startswith(normalize(root) + "/")
                           for path in paths for root in library.get("locations", []) if root)]
        reference = task.get('media_reference') or {}
        if reference and reference.get('server_id') != server['id']:
            continue
        if not matched and identifier:
            matched = [library for library in libraries if not selected or library['id'] in selected]
        if reference:
            matched = [library for library in libraries if library['id'] == reference.get('library_id') and (not selected or library['id'] in selected)]
        for library in matched:
            if reference:
                items = [{'Id': reference['item_id'], 'Path': folder + '/video'}]
            else:
                response = requests.get(f"{_service_url(server)}/Items", headers=_headers(server),
                                    params={"ParentId": library["id"], "Recursive": "true", "IncludeItemTypes": "Movie", "SearchTerm": identifier,
                                            "Fields": "Path,ProviderIds", "Limit": 100}, timeout=20)
                response.raise_for_status()
                items = response.json().get("Items", [])
            exact = [item for item in items if normalize(item.get("Path") or "").rsplit("/", 1)[0] in paths]
            if not exact and identifier:
                token = re.compile(r"(?<![a-z0-9])" + re.escape(identifier).replace(r'\-', r'[-_ ]?') + r"(?![a-z0-9])", re.I)
                exact = [item for item in items if token.search(str(item.get("Path") or '') + ' ' + str(item.get('Name') or ''))]
            if len(exact) != 1 or not exact[0].get("Id"):
                continue
            info = requests.get(f"{_service_url(server)}/System/Info", headers=_headers(server), timeout=20)
            info.raise_for_status()
            query = urlencode({"id": exact[0]["Id"], "serverId": info.json().get("Id", "")})
            if server.get("type") == "jellyfin":
                url = base + "/web/#/details?" + query
            else:
                url = base + "/web/index.html#!/item?" + query
            links.append({"name": server["name"] + " · " + library["name"], "url": url})
    return links


_FILM_CACHE = {}
_FILM_LOCK = threading.RLock()


def clear_catalog_cache():
    with _FILM_LOCK:
        _FILM_CACHE.clear()
        _LIBRARY_CACHE.clear()


def _movie_summary(server, library, item):
    path = str(item.get('Path') or '').replace('\\', '/')
    title = str(item.get('Name') or '')
    identifier_text = path.rsplit('/', 1)[-1] + ' ' + title + ' ' + path.rsplit('/', 2)[-2] if '/' in path else path + ' ' + title
    match = re.search(r'(?<![A-Za-z0-9])([A-Za-z]{2,12})[-_ ]?(\d{2,8})(?!\d)', identifier_text)
    identifier = str((item.get('ProviderIds') or {}).get('JavSPDVDID') or ((match[1].upper() + '-' + match[2]) if match else ''))
    fc2 = re.search(r'\bFC2[-_ ]*(?:PPV[-_ ]*)?(\d{4,9})\b', identifier_text, re.I)
    if fc2 and not (item.get('ProviderIds') or {}).get('JavSPDVDID'):
        identifier = 'FC2-' + fc2[1]
    metadata = {'dvdid': identifier, 'title': title,
                'actress': [p['Name'] for p in item.get('People') or [] if p.get('Type') == 'Actor' and p.get('Name')],
                'director': ' / '.join(p['Name'] for p in item.get('People') or [] if p.get('Type') == 'Director' and p.get('Name')),
                'producer': ' / '.join(s['Name'] for s in item.get('Studios') or [] if s.get('Name')),
                'publisher': str((item.get('ProviderIds') or {}).get('JavSPPublisher') or ''), 'publish_date': str(item.get('PremiereDate') or item.get('ProductionYear') or '')[:10]}
    key = hashlib.sha256((str(server['id']) + ':' + str(item['Id'])).encode()).hexdigest()[:24]
    return {'id': 'media-' + key, 'name': title, 'title': title, 'file_name': path.rsplit('/', 1)[-1] or title,
            'input_directory': path, 'status': 'succeeded', 'source': 'media', 'task_type': 'media',
            'created_at': item.get('DateCreated') or '', 'updated_at': item.get('DateLastSaved') or '',
            'preset_name': server.get('name', '') + ' · ' + library['name'],
            'cover_count': int(bool((item.get('ImageTags') or {}).get('Primary'))),
            'fanart_count': len(item.get('BackdropImageTags') or []), 'log_entries': [], 'log_tail': [],
            'media_reference': {'server_id': server['id'], 'library_id': library['id'], 'item_id': str(item['Id'])},
            'library_keys': [str(server['id']) + ':' + library['id']],
            'progress': {'metadata': metadata, 'output': {'save_dir': path.rsplit('/', 1)[0] if '/' in path else ''}, 'images': {}}}


def catalog_movies():
    """Read every bound library, including films never scraped by this app."""
    movies, errors = [], []
    with _FILM_LOCK:
        for server in list_media_servers():
            if not server.get('url') or not server.get('api_key'):
                continue
            key = (server['id'], server['url'], server['api_key'], tuple(map(str, server.get('libraries') or [])))
            cached = _FILM_CACHE.get(key)
            if cached and cached[0] > time.monotonic():
                movies.extend(cached[1]); errors.extend(cached[2]); continue
            records, failures = [], []
            try:
                selected = set(map(str, server.get('libraries') or []))
                for library in list_media_libraries(server):
                    if selected and library['id'] not in selected:
                        continue
                    offset = 0
                    while True:
                        response = requests.get(f'{_service_url(server)}/Items', headers=_headers(server), timeout=30,
                            params={'ParentId': library['id'], 'Recursive': 'true', 'IncludeItemTypes': 'Movie',
                                    'Fields': 'Path,People,Studios,DateCreated,DateLastSaved,ProviderIds',
                                    'StartIndex': offset, 'Limit': 1000, 'EnableTotalRecordCount': 'true'})
                        response.raise_for_status()
                        data = response.json()
                        batch = data.get('Items') or []
                        records.extend(_movie_summary(server, library, item) for item in batch if item.get('Id'))
                        offset += len(batch)
                        if not batch or ('TotalRecordCount' in data and offset >= int(data['TotalRecordCount'])) or ('TotalRecordCount' not in data and len(batch) < 1000):
                            break
            except (OSError, ValueError, requests.RequestException) as exc:
                failures.append(server.get('name', '媒体服务器') + '：' + connection_error(exc))
                records = cached[1] if cached else []
            _FILM_CACHE[key] = (time.monotonic() + (60 if failures else 300), records, failures)
            movies.extend(records); errors.extend(failures)
    return movies, errors


def catalog_task(task_id):
    if not task_id.startswith('media-'):
        return None
    return next((item for item in catalog_movies()[0] if item['id'] == task_id), None)


def _catalog_target(task_id):
    task = catalog_task(task_id)
    if not task:
        raise ValueError('媒体库影片不存在或已取消绑定')
    ref = task['media_reference']
    server = next(item for item in list_media_servers() if item['id'] == ref['server_id'])
    return task, server, f"{_service_url(server)}/Items/{quote(ref['item_id'], safe='')}"


def catalog_image(task_id, kind, index=0, content=None, delete=False):
    task, server, base = _catalog_target(task_id)
    role = 'Primary' if kind == 'cover' else 'Backdrop'
    url = base + '/Images/' + role
    if content is None:
        url += '/' + str(index)
    headers = _headers(server)
    if delete:
        response = requests.delete(url, headers=headers, timeout=20)
    elif content is not None:
        headers['Content-Type'] = 'image/jpeg'
        response = requests.post(url + ('/' + str(index) if index >= 0 else ''), headers=headers,
                                 data=content, timeout=30)
    else:
        response = requests.get(url, headers=headers, params={'MaxWidth': 1200}, timeout=20)
    response.raise_for_status()
    if delete or content is not None:
        clear_catalog_cache()
    return response


def update_catalog_metadata(task_id, values):
    task, server, url = _catalog_target(task_id)
    response = requests.get(f'{_service_url(server)}/Items', headers=_headers(server), timeout=20,
                            params={'Ids': task['media_reference']['item_id'], 'Fields': 'People,Studios,ProviderIds,Overview,Genres,Tags,PremiereDate'})
    response.raise_for_status()
    items = response.json().get('Items') or []
    if len(items) != 1:
        raise ValueError('媒体库影片不存在')
    item = items[0]
    people = [p for p in item.get('People') or [] if p.get('Type') not in ('Actor', 'Director')]
    people += [{'Name': name, 'Type': 'Actor'} for name in values.get('actress') or []]
    if values.get('director'):
        people.append({'Name': values['director'], 'Type': 'Director'})
    item.update(Name=values.get('title', ''), People=people,
                Studios=[{'Name': values['producer']}] if values.get('producer') else [],
                PremiereDate=values.get('publish_date') or None)
    item.setdefault('ProviderIds', {}).update(JavSPDVDID=values.get('dvdid') or '', JavSPPublisher=values.get('publisher') or '')
    response = requests.post(url, headers=_headers(server), json=item, timeout=30)
    response.raise_for_status()
    clear_catalog_cache()
    return {'metadata': values, 'nfo_path': ''}


def auto_sync_media_servers() -> None:
    for server in list_media_servers():
        if not server.get("auto_scan"):
            continue
        try:
            delay = max(0, min(86400, int(server.get("auto_scan_delay", 0) or 0)))
            if delay:
                time.sleep(delay)
            sync_media_server(server)
        except (OSError, requests.RequestException):
            continue
