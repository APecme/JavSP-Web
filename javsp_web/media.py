from __future__ import annotations

import time
import os
import socket
import struct
import re
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
            if roots:
                result.append({"key": f"{server['id']}:{library['id']}", "name": library["name"], "server": server.get("name", ""), "roots": roots})
    return result


def playback_links(task: dict) -> list[dict]:
    """Match output paths to selected libraries, then resolve the server's item page."""
    output = (task.get("progress") or {}).get("output") or {}
    folder = str(output.get("save_dir") or task.get("input_directory") or "")
    identifier = str(((task.get("progress") or {}).get("metadata") or {}).get("dvdid") or "")
    normalize = lambda value: str(value).replace("\\", "/").rstrip("/").casefold()
    paths = [normalize(folder)]
    for mapping in list_path_mappings():
        local, remote = normalize(mapping.get("target_path")), normalize(mapping.get("source_path"))
        if local and (paths[0] == local or paths[0].startswith(local + "/")):
            paths.append(remote + paths[0][len(local):])
    links = []
    for server in list_media_servers():
        external = urlsplit(str(server.get("external_url") or "").strip())
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
        if not matched:
            continue
        for library in matched:
            response = requests.get(f"{_service_url(server)}/Items", headers=_headers(server),
                                    params={"ParentId": library["id"], "Recursive": "true", "IncludeItemTypes": "Movie", "SearchTerm": identifier,
                                            "Fields": "Path,ProviderIds", "Limit": 100}, timeout=20)
            response.raise_for_status()
            items = response.json().get("Items", [])
            exact = [item for item in items if normalize(item.get("Path") or "").rsplit("/", 1)[0] in paths]
            if not exact and identifier:
                token = re.compile(r"(?<![a-z0-9])" + re.escape(identifier) + r"(?![a-z0-9])", re.I)
                exact = [item for item in items if token.search(str(item.get("Path") or item.get("Name") or ""))]
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
