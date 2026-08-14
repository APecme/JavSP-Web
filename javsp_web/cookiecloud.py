from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


class CookieCloudError(RuntimeError):
    """A user-facing CookieCloud synchronization error."""


def cookiecloud_url(server_url: str, uuid: str) -> str:
    base = server_url.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise CookieCloudError("CookieCloud 服务地址必须以 http:// 或 https:// 开头")
    if not uuid.strip():
        raise CookieCloudError("请填写 CookieCloud UUID")
    return f"{base}/get/{quote(uuid.strip(), safe='')}"


def _cookie_pairs(cookie_data: Any) -> dict[str, dict[str, str]]:
    """Normalize CookieCloud's domain-keyed cookie collection for JavSP."""
    result: dict[str, dict[str, str]] = {}

    def add(domain: Any, item: Any) -> None:
        if not isinstance(item, dict):
            return
        host = str(item.get("domain") or domain or "").strip().lstrip(".").lower()
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        if host and name and value is not None:
            result.setdefault(host, {})[name] = str(value)

    if isinstance(cookie_data, dict):
        for domain, entries in cookie_data.items():
            if isinstance(entries, dict) and "name" in entries:
                add(domain, entries)
            elif isinstance(entries, dict):
                for name, value in entries.items():
                    if isinstance(value, dict):
                        add(domain, value)
                    elif value is not None:
                        result.setdefault(str(domain).lstrip(".").lower(), {})[str(name)] = str(value)
            elif isinstance(entries, list):
                for entry in entries:
                    add(domain, entry)
    elif isinstance(cookie_data, list):
        for entry in cookie_data:
            add("", entry)
    return {domain: cookies for domain, cookies in result.items() if cookies}


def fetch_cookiecloud(settings: dict[str, Any], timeout: float = 15) -> dict[str, dict[str, str]]:
    server_url = str(settings.get("server_url") or "")
    uuid = str(settings.get("uuid") or "")
    password = str(settings.get("password") or "")
    if not (server_url and uuid and password):
        raise CookieCloudError("请完整填写 CookieCloud 服务地址、UUID 和密码")
    try:
        response = requests.get(
            cookiecloud_url(server_url, uuid),
            params={"password": password},
            headers={"CookieCloud-Password": password},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        # requests may include the complete URL in its exception text. The
        # CookieCloud password is a query parameter for compatibility, so do
        # not let an operational error expose it in a task log or API response.
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status_code}" if status_code else "网络请求失败"
        raise CookieCloudError(f"无法连接 CookieCloud：{detail}") from exc
    except ValueError as exc:
        raise CookieCloudError("CookieCloud 返回的不是 JSON 数据") from exc

    if not isinstance(payload, dict):
        raise CookieCloudError("CookieCloud 返回的数据格式无效")
    cookie_data = payload.get("cookie_data")
    if cookie_data is None and isinstance(payload.get("data"), (dict, list)):
        cookie_data = payload["data"]
    cookies = _cookie_pairs(cookie_data)
    if not cookies:
        message = str(payload.get("message") or payload.get("msg") or "CookieCloud 未返回可用 Cookie")
        raise CookieCloudError(message)
    return cookies


def cookiecloud_summary(cookies: dict[str, dict[str, str]]) -> dict[str, int]:
    return {"domains": len(cookies), "cookies": sum(len(values) for values in cookies.values())}
