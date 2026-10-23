"""Same-origin proxy for the public comment service.

The browser only ever talks to this site.  The upstream base is fixed by the
server environment (``JAVSP_COMMENTS_URL``), every forwarded route is
whitelisted per method below, and the upstream path is rebuilt from the matched
route instead of being relayed verbatim.  The site session cookie is the gate
for using the proxy and is never forwarded, and upstream cookies/redirects are
never handed back to the browser.

Deployment note: behind this proxy the comment service sees this server's
egress address, so its per-IP rate limits apply to all site users together.
We deliberately do not forge ``CF-Connecting-IP`` or any other forwarding
header to work around that.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from .auth import current_user

DEFAULT_UPSTREAM = "https://comments.rtioo.com"
PROXY_PREFIX = "/api/comments"

TIMEOUT = (5.0, 10.0)
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_INFLIGHT = 16
_CHUNK = 8192
_PAGING_KEYS = ("before", "limit")

_UNAVAILABLE = "评论服务未启用。"
_FORBIDDEN = "评论请求不被允许。"
_METHOD_NOT_ALLOWED = "评论请求方法不被允许。"
_BAD_QUERY = "评论请求参数无效。"
_BAD_BODY = "评论请求无效。"
_BODY_TOO_LARGE = "评论请求内容过大。"
_NOT_JSON_REQUEST = "请使用 JSON 提交评论。"
_BAD_IDENTITY = "评论身份凭证无效。"
_BAD_DELETE_TOKEN = "评论删除凭证无效。"
_TIMEOUT = "评论服务响应超时，请稍后重试。"
_NETWORK = "无法连接评论服务，请稍后重试。"
_TOO_LARGE = "评论服务响应过大，请稍后重试。"
_BAD_RESPONSE = "评论服务暂时不可用，请稍后重试。"
_BUSY = "评论服务繁忙，请稍后重试。"

_INFLIGHT = threading.BoundedSemaphore(MAX_INFLIGHT)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,200}")
_DELETE_TOKEN = re.compile(r"[A-Za-z0-9-]{16,200}")
_POSITIVE_INT = re.compile(r"[0-9]{1,18}")
_RETRY_AFTER = re.compile(r"[0-9]{1,6}")
_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_COMMENT_ID = r"[0-9]{1,18}"


def _clean_base(raw: object) -> str:
    """Return a usable http(s) base without credentials, query or fragment."""
    value = str(raw or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return ""
    if parts.query or parts.fragment:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def upstream_base() -> str:
    return _clean_base(os.environ.get("JAVSP_COMMENTS_URL", DEFAULT_UPSTREAM))


def verify_base() -> str:
    """Cloudflare Turnstile binds the challenge to its own hostname, so the
    verification page keeps living on the comment service origin (or a
    dedicated one) instead of being relayed through this deployment."""
    return _clean_base(os.environ.get("JAVSP_COMMENTS_VERIFY_URL", "")) or upstream_base()


def runtime_entry() -> dict:
    if not upstream_base():
        return {"comments_url": "", "comments_verify_url": ""}
    return {"comments_url": PROXY_PREFIX, "comments_verify_url": verify_base()}


def _thread_path(match: re.Match[str]) -> str:
    return "api/threads/" + quote(match.group(1), safe="") + "/comments"


def _comment_path(match: re.Match[str]) -> str:
    return "api/comments/" + str(int(match.group(1)))


def _comment_action(match: re.Match[str]) -> str:
    return _comment_path(match) + "/" + match.group(2)


@dataclass(frozen=True)
class _Rule:
    name: str
    methods: tuple[str, ...]
    pattern: re.Pattern[str]
    build: Callable[[re.Match[str]], str]
    paging: bool = False


_RULES: tuple[_Rule, ...] = (
    _Rule("config", ("GET",), re.compile(r"api/config"), lambda match: "api/config"),
    _Rule("threads", ("GET", "POST"), re.compile(r"api/threads/(" + _IDENTIFIER + r")/comments"), _thread_path, paging=True),
    _Rule("like", ("POST",), re.compile(r"api/comments/(" + _COMMENT_ID + r")/(like)"), _comment_action),
    _Rule("reports", ("POST",), re.compile(r"api/comments/(" + _COMMENT_ID + r")/(reports)"), _comment_action),
    _Rule("comment", ("DELETE",), re.compile(r"api/comments/(" + _COMMENT_ID + r")"), _comment_path),
    _Rule("identity", ("POST",), re.compile(r"api/identity"), lambda match: "api/identity"),
    _Rule("profile", ("GET", "POST"), re.compile(r"api/me/profile"), lambda match: "api/me/profile"),
    _Rule("history", ("GET",), re.compile(r"api/me/comments"), lambda match: "api/me/comments", paging=True),
    _Rule("logout", ("POST",), re.compile(r"api/me/logout"), lambda match: "api/me/logout"),
    _Rule("logout-all", ("POST",), re.compile(r"api/me/logout-all"), lambda match: "api/me/logout-all"),
    _Rule("pin", ("POST",), re.compile(r"api/me/pin"), lambda match: "api/me/pin"),
)


class _ProxyError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _match_rule(method: str, path: str) -> tuple[_Rule, re.Match[str]]:
    known_path = False
    for rule in _RULES:
        match = rule.pattern.fullmatch(path)
        if not match:
            continue
        if method in rule.methods:
            return rule, match
        known_path = True
    raise HTTPException(405 if known_path else 403, _METHOD_NOT_ALLOWED if known_path else _FORBIDDEN)


def _proxy_query(rule: _Rule, raw: str) -> str:
    if not raw:
        return ""
    if not rule.paging:
        raise HTTPException(403, _FORBIDDEN)
    values: dict[str, str] = {}
    for key, value in parse_qsl(raw, keep_blank_values=True):
        if key not in _PAGING_KEYS or key in values or not _POSITIVE_INT.fullmatch(value):
            raise HTTPException(400, _BAD_QUERY)
        values[key] = value
    return urlencode([(key, values[key]) for key in _PAGING_KEYS if key in values])


async def _proxy_body(request: Request, method: str) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise HTTPException(413, _BODY_TOO_LARGE)
    # Read incrementally so a chunked body without Content-Length cannot buffer
    # unbounded data in the event loop.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(413, _BODY_TOO_LARGE)
    if not body:
        return b""
    if method != "POST":
        raise HTTPException(400, _BAD_BODY)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, _NOT_JSON_REQUEST)
    return bytes(body)


def _proxy_headers(request: Request, rule: _Rule, has_body: bool) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "JavSP-Web comments-proxy"}
    if has_body:
        headers["Content-Type"] = "application/json"
    token = (request.headers.get("x-user-token") or "").strip()
    if token:
        if not _TOKEN.fullmatch(token):
            raise HTTPException(400, _BAD_IDENTITY)
        headers["X-User-Token"] = token
    delete_token = (request.headers.get("x-delete-token") or "").strip()
    if delete_token:
        if rule.name != "comment" or not _DELETE_TOKEN.fullmatch(delete_token):
            raise HTTPException(400, _BAD_DELETE_TOKEN)
        headers["X-Delete-Token"] = delete_token
    return headers


def _forward(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes, object]:
    if not _INFLIGHT.acquire(timeout=10):
        raise _ProxyError(503, _BUSY)
    try:
        with requests.request(method, url, headers=headers, data=body or None, timeout=TIMEOUT, allow_redirects=False, stream=True) as response:
            if 300 <= response.status_code < 400:
                raise _ProxyError(502, _BAD_RESPONSE)
            content = bytearray()
            for chunk in response.iter_content(_CHUNK):
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise _ProxyError(502, _TOO_LARGE)
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content and content_type != "application/json":
                raise _ProxyError(502, _BAD_RESPONSE)
            return response.status_code, bytes(content), response.headers
    finally:
        _INFLIGHT.release()


router = APIRouter()


@router.api_route(PROXY_PREFIX + "/{upstream_path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"], include_in_schema=False)
async def comment_proxy(upstream_path: str, request: Request, _: dict = Depends(current_user)) -> Response:
    base = upstream_base()
    if not base:
        raise HTTPException(503, _UNAVAILABLE)
    rule, match = _match_rule(request.method, upstream_path)
    query = _proxy_query(rule, request.url.query)
    body = await _proxy_body(request, request.method)
    headers = _proxy_headers(request, rule, bool(body))
    target = f"{base}/{rule.build(match)}" + (f"?{query}" if query else "")
    try:
        status_code, content, upstream_headers = await run_in_threadpool(_forward, request.method, target, headers, body)
    except requests.Timeout:
        raise HTTPException(504, _TIMEOUT) from None
    except requests.RequestException:
        raise HTTPException(502, _NETWORK) from None
    except _ProxyError as error:
        raise HTTPException(error.status_code, error.detail) from None
    response = Response(content=content, status_code=status_code, media_type="application/json")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    retry_after = (upstream_headers.get("Retry-After") or "").strip()
    if _RETRY_AFTER.fullmatch(retry_after):
        response.headers["Retry-After"] = retry_after
    return response
