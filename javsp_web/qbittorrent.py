from __future__ import annotations

import json
import errno
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


class QbittorrentError(RuntimeError):
    pass


def _connection_error(base_url: str, exc: Exception, *, api: bool = False) -> QbittorrentError:
    """Make container network errors actionable instead of implying bad credentials."""
    host = (urlparse(base_url).hostname or "").lower()
    reason = getattr(exc, "reason", exc)
    err_no = getattr(reason, "errno", None)
    prefix = "qBittorrent API 请求失败" if api else "无法连接 qBittorrent"
    detail = f"{prefix}：{exc}"
    if host in {"127.0.0.1", "::1", "localhost"}:
        return QbittorrentError(
            f"{detail}。127.0.0.1 指向运行 JavSP WEB 的设备；Docker 部署时它指向 JavSP WEB 容器，并不是 qBittorrent。"
            "请使用同一 Docker 网络中的 qBittorrent 服务名（例如 http://qbittorrent:8080）、可访问的域名，"
            "或已配置 host-gateway 的 http://host.docker.internal:端口。"
        )
    if err_no in {errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ECONNREFUSED, errno.ETIMEDOUT}:
        return QbittorrentError(
            f"{detail}。连接由部署 JavSP WEB 的服务器或容器发起，而不是浏览器发起。"
            "请确认该运行环境可路由到此地址、qBittorrent Web UI 监听了可访问接口，并放行对应防火墙/反向代理规则。"
        )
    return QbittorrentError(detail)


def _host_gateway_url(base_url: str) -> str | None:
    """Use Docker's host gateway when a host-LAN address is hairpin-blocked."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if host in {"127.0.0.1", "::1", "localhost", "host.docker.internal"}:
        return None
    netloc = "host.docker.internal"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


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
        gateway_url = _host_gateway_url(base_url)
        if not gateway_url:
            raise _connection_error(base_url, exc) from exc
        # Docker hosts can reject a container's connection to their LAN IP
        # (hairpin routing), while host-gateway remains reachable.
        gateway_headers = {**headers, "Referer": f"{gateway_url}/", "Origin": gateway_url}
        gateway_request = Request(f"{gateway_url}/api/v2/auth/login", data=payload, headers=gateway_headers, method="POST")
        try:
            with opener.open(gateway_request, timeout=8) as response:
                result = response.read().decode("utf-8", errors="replace").strip()
            base_url, headers = gateway_url, gateway_headers
        except (URLError, TimeoutError) as gateway_exc:
            raise QbittorrentError(
                f"{_connection_error(base_url, exc)} 同时已尝试 Docker 宿主机网关 {gateway_url}，仍无法连接：{gateway_exc}。"
                "请确认 qBittorrent Web UI 监听 0.0.0.0（而非仅 127.0.0.1），且 Docker 容器与 qB 所在网络之间允许访问该端口。"
            ) from gateway_exc
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


def delete_torrent(settings: dict, torrent_hash: str) -> None:
    base_url, opener, headers = _open(settings)
    _request(opener, f"{base_url}/api/v2/torrents/delete", headers, data={"hashes": torrent_hash, "deleteFiles": "false"})
