from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import quote

import requests
from Crypto.Cipher import AES


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


def _unpad_pkcs7(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty plaintext")
    size = data[-1]
    if not 1 <= size <= AES.block_size or data[-size:] != bytes([size]) * size:
        raise ValueError("invalid padding")
    return data[:-size]


def _decrypt_legacy(encrypted: str, uuid: str, password: str) -> dict[str, Any]:
    raw = base64.b64decode(encrypted)
    if len(raw) < 32 or raw[:8] != b"Salted__":
        raise ValueError("invalid CryptoJS dynamic-IV payload")
    salt, ciphertext = raw[8:16], raw[16:]
    passphrase = hashlib.md5(f"{uuid}-{password}".encode("utf-8")).hexdigest()[:16].encode("utf-8")
    key_iv, previous = b"", b""
    while len(key_iv) < 48:
        previous = hashlib.md5(previous + passphrase + salt).digest()
        key_iv += previous
    plaintext = _unpad_pkcs7(AES.new(key_iv[:32], AES.MODE_CBC, key_iv[32:48]).decrypt(ciphertext))
    result = json.loads(plaintext.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("decrypted data is not an object")
    return result


def _decrypt_fixed_iv(encrypted: str, uuid: str, password: str) -> dict[str, Any]:
    raw = base64.b64decode(encrypted)
    key = hashlib.md5(f"{uuid}-{password}".encode("utf-8")).hexdigest()[:16].encode("utf-8")
    plaintext = _unpad_pkcs7(AES.new(key, AES.MODE_CBC, b"\0" * 16).decrypt(raw))
    result = json.loads(plaintext.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("decrypted data is not an object")
    return result


def _decode_payload(response: requests.Response, uuid: str, password: str, configured_crypto_type: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {"encrypted": text}
    if isinstance(payload, str):
        payload = {"encrypted": payload}
    if not isinstance(payload, dict):
        raise CookieCloudError("CookieCloud 返回的数据格式无效")
    if not payload.get("encrypted"):
        return payload
    crypto_type = configured_crypto_type if configured_crypto_type != "auto" else str(payload.get("crypto_type") or "legacy")
    try:
        if crypto_type == "aes-128-cbc-fixed":
            return _decrypt_fixed_iv(str(payload["encrypted"]), uuid, password)
        return _decrypt_legacy(str(payload["encrypted"]), uuid, password)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        label = "AES-128-CBC（固定 IV）" if crypto_type == "aes-128-cbc-fixed" else "CryptoJS（动态 IV）"
        raise CookieCloudError(f"CookieCloud {label} 解密失败，请检查 UUID、密码和加密类型") from exc


def fetch_cookiecloud(settings: dict[str, Any], timeout: float = 15) -> dict[str, dict[str, str]]:
    server_url = str(settings.get("server_url") or "")
    uuid = str(settings.get("uuid") or "")
    password = str(settings.get("password") or "")
    crypto_type = str(settings.get("crypto_type") or "auto")
    if not (server_url and uuid and password):
        raise CookieCloudError("请完整填写 CookieCloud 服务地址、UUID 和密码")
    try:
        response = requests.get(
            cookiecloud_url(server_url, uuid),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = _decode_payload(response, uuid, password, crypto_type)
    except requests.RequestException as exc:
        # requests may include the complete URL in its exception text. The
        # CookieCloud password is a query parameter for compatibility, so do
        # not let an operational error expose it in a task log or API response.
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status_code}" if status_code else "网络请求失败"
        raise CookieCloudError(f"无法连接 CookieCloud：{detail}") from exc
    except CookieCloudError:
        raise

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
