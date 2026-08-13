from __future__ import annotations

import time
import os
import re
import socket
import struct
from urllib.parse import quote, urlsplit, urlunsplit

import requests

from .storage import list_media_servers


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
    key = str(server.get("api_key") or "")
    return {"X-Emby-Token": key} if key else {}


def _params(server: dict, **params: object) -> dict[str, object]:
    result = dict(params)
    key = str(server.get("api_key") or "")
    if key:
        result["api_key"] = key
    return result


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
    response.raise_for_status()
    libraries = []
    for item in response.json() or []:
        if not isinstance(item, dict):
            continue
        libraries.append({"id": str(item.get("ItemId") or item.get("Id") or item.get("Name") or ""), "name": str(item.get("Name") or item.get("CollectionType") or "未命名媒体库")})
    return [item for item in libraries if item["id"]]


def _task_search_terms(task: dict) -> list[str]:
    metadata = (task.get("progress") or {}).get("metadata") or {}
    terms = [str(metadata.get("dvdid") or "").strip(), str(metadata.get("title") or task.get("title") or "").strip()]
    for value in (task.get("input_directory"), task.get("file_name"), task.get("name")):
        match = re.search(r"(?<!\d)(\d{6}[-_]\d{2,3}|[A-Za-z]{2,10}[-_]\d{2,5})(?!\d)", str(value or ""))
        if match:
            terms.append(match.group(1).replace("_", "-"))
    return list(dict.fromkeys(term for term in terms if term))


def _search_server(server: dict, task: dict) -> tuple[dict | None, str]:
    terms = _task_search_terms(task)
    if not terms:
        return None, ""
    library_ids = [str(value) for value in server.get("libraries") or [] if str(value).strip()] or [None]
    for term in terms:
        for library_id in library_ids:
            params = _params(server, SearchTerm=term, IncludeItemTypes="Movie,Video", Recursive="true", Limit=10)
            if library_id:
                params["ParentId"] = library_id
            response = requests.get(f"{_service_url(server)}/Items", params=params, headers=_headers(server), timeout=20)
            response.raise_for_status()
            items = response.json().get("Items") or []
            valid_items = [item for item in items if isinstance(item, dict) and item.get("Id")]
            if len(valid_items) == 1:
                return valid_items[0], term
    return None, terms[0]


def media_links_for_task(task: dict) -> list[dict]:
    links: list[dict] = []
    for server in list_media_servers():
        try:
            item, term = _search_server(server, task)
            base = server.get("external_url") or server["url"]
            link = {
                "id": server["id"],
                "name": server["name"],
                "type": server["type"],
                "found": bool(item),
                "unique_match": bool(item),
                "title": (item or {}).get("Name") or "",
                "play_url": f"{base}/web/index.html#!/details?id={quote(str(item['Id']))}" if item and item.get("Id") else "",
                "search_url": f"{base}/web/index.html#!/search.html?query={quote(term)}" if term else "",
            }
            links.append(link)
        except (OSError, requests.RequestException, ValueError) as exc:
            links.append({"id": server["id"], "name": server["name"], "type": server["type"], "found": False, "error": str(exc)})
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
