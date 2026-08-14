from __future__ import annotations

import time
import os
import socket
import struct
from urllib.parse import urlsplit, urlunsplit

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
