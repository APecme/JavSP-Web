from __future__ import annotations

import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


class QbittorrentError(RuntimeError):
    pass


def _connection_error(*_: object, **__: object) -> QbittorrentError:
    return QbittorrentError("无法连接 qBittorrent，请检查服务地址后重试")


def _base_url(settings: dict) -> str:
    value = str(settings.get("url") or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise QbittorrentError("qBittorrent 地址必须是完整 URL，例如 http://127.0.0.1:8080")
    return value


def _open(settings: dict):
    base_url = _base_url(settings)
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "JavSP-WEB/0.1",
        "Referer": f"{base_url}/",
        "Origin": base_url,
    }
    username = str(settings.get("username") or "")
    password = str(settings.get("password") or "")
    if not username or not password:
        raise QbittorrentError("请先填写 qBittorrent 用户名和密码")
    payload = urlencode({"username": username, "password": password}).encode("utf-8")
    request = Request(f"{base_url}/api/v2/auth/login", data=payload, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=8) as response:
            result = response.read().decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise QbittorrentError(f"qBittorrent 拒绝登录（HTTP {exc.code}）：{detail or '请检查 Web UI 地址、用户名和反向代理设置'}") from exc
    except (URLError, TimeoutError) as exc:
        raise _connection_error(base_url, exc) from exc
    if result == "Fails.":
        raise QbittorrentError("qBittorrent 用户名或密码错误")
    # Some HTTPS reverse proxies strip the qB login body while preserving SID.
    # The authenticated API request below is the authoritative verification.
    if result == "":
        return base_url, opener, headers
    if result != "Ok.":
        raise QbittorrentError(f"qBittorrent 登录响应异常：{result or '空响应'}")
    return base_url, opener, headers


def _request(opener, url: str, headers: dict[str, str], *, data: dict | None = None) -> bytes:
    encoded = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=encoded, headers=headers, method="POST" if data is not None else "GET")
    try:
        with opener.open(request, timeout=10) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise QbittorrentError(f"qBittorrent API 请求失败（HTTP {exc.code}）：{detail or '请检查认证方式与 Web UI 地址'}") from exc
    except (URLError, TimeoutError) as exc:
        raise _connection_error(url, exc, api=True) from exc


def test_connection(settings: dict) -> dict:
    try:
        base_url, opener, headers = _open(settings)
        version = _request(opener, f"{base_url}/api/v2/app/version", headers).decode("utf-8", errors="replace").strip()
    except QbittorrentError as exc:
        if "HTTP 403" in str(exc):
            raise QbittorrentError("登录后会话未被 qBittorrent 接受。请确认反向代理保留 SID Cookie，并将服务地址填写为 Web UI 根地址。") from exc
        raise
    return {"version": version}


def list_downloads(settings: dict) -> list[dict]:
    base_url, opener, headers = _open(settings)
    try:
        records = json.loads(_request(opener, f"{base_url}/api/v2/torrents/info?filter=all", headers).decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise QbittorrentError("qBittorrent 返回的下载列表格式无效") from exc
    if not isinstance(records, list):
        raise QbittorrentError("qBittorrent 返回的下载列表格式无效")
    return [
        {
            "hash": item.get("hash", ""),
            "name": item.get("name", ""),
            "progress": round(float(item.get("progress", 0) or 0) * 100, 1),
            "state": item.get("state", ""),
            "size": int(item.get("size", 0) or 0),
            "seeds": int(item.get("num_seeds", 0) or 0),
            "peers": int(item.get("num_leechs", 0) or 0),
            "eta": int(item.get("eta", 0) or 0),
            "popularity": float(item.get("popularity", 0) or 0),
            "added_on": int(item.get("added_on", 0) or 0),
            "completed_on": int(item.get("completion_on", 0) or 0),
            "download_speed": int(item.get("dlspeed", 0) or 0),
            "upload_speed": int(item.get("upspeed", 0) or 0),
            "ratio": float(item.get("ratio", 0) or 0),
            "seeding_time": int(item.get("seeding_time", 0) or 0),
            "inactive_seeding_time": int(item.get("inactive_seeding_time", 0) or 0),
            "tags": item.get("tags", ""),
            "category": item.get("category", ""),
            "content_path": item.get("content_path") or item.get("save_path") or "",
        }
        for item in records
        if isinstance(item, dict)
    ]


def set_share_limits(settings: dict, torrent_hash: str, rule: dict) -> None:
    base_url, opener, headers = _open(settings)
    _request(opener, f"{base_url}/api/v2/torrents/setShareLimits", headers, data={
        "hashes": torrent_hash,
        "ratioLimit": rule.get("ratio_limit", -1),
        "seedingTimeLimit": rule.get("seeding_time_limit", -1),
        "inactiveSeedingTimeLimit": rule.get("inactive_seeding_time_limit", -1),
    })


def set_torrent_transfer_limits(settings: dict, torrent_hash: str, download_limit_kib: int, upload_limit_kib: int) -> None:
    """Set transfer limits for one torrent. Negative values mean unlimited."""
    base_url, opener, headers = _open(settings)
    download_bytes = 0 if download_limit_kib < 0 else download_limit_kib * 1024
    upload_bytes = 0 if upload_limit_kib < 0 else upload_limit_kib * 1024
    data = {"hashes": torrent_hash, "limit": download_bytes}
    _request(opener, f"{base_url}/api/v2/torrents/setDownloadLimit", headers, data=data)
    data["limit"] = upload_bytes
    _request(opener, f"{base_url}/api/v2/torrents/setUploadLimit", headers, data=data)


def delete_torrent(settings: dict, torrent_hash: str) -> None:
    base_url, opener, headers = _open(settings)
    _request(opener, f"{base_url}/api/v2/torrents/delete", headers, data={"hashes": torrent_hash, "deleteFiles": "false"})
