"""Single-process login admission and explicit reverse-proxy trust."""
from __future__ import annotations

import ipaddress
import math
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field

from fastapi import HTTPException, Request


def _ip(value: str) -> str:
    if "%" in value:
        raise ValueError("Scoped addresses are not accepted")
    address = ipaddress.ip_address(value.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


# No proxy is trusted unless explicitly configured. Exact IPs only, no wildcards.
TRUSTED_PROXIES = frozenset(
    _ip(value) for value in os.environ.get("JAVSP_WEB_TRUSTED_PROXIES", "").split(",") if value.strip()
)


def login_context(request: Request) -> tuple[str, bool]:
    peer = request.client.host if request.client else "unknown"
    try:
        peer = _ip(peer)
    except ValueError:
        pass
    secure = request.url.scheme == "https"
    client_ip = peer
    if peer in TRUSTED_PROXIES:
        real_ip = request.headers.getlist("x-real-ip")
        if len(real_ip) == 1:
            try:
                client_ip = _ip(real_ip[0])
            except ValueError:
                pass
        proto = request.headers.getlist("x-forwarded-proto")
        secure = secure or (len(proto) == 1 and proto[0].strip().lower() == "https")
    return client_ip, secure


@dataclass
class _Bucket:
    failures: deque = field(default_factory=deque)
    pending: int = 0


@dataclass
class _Attempt:
    success: bool = False


class LoginLimiter:
    """Reserve before hashing; refund successes without erasing other failures.

    Unexpired failures are never evicted to admit attacker-controlled new keys.
    The deployed server has one process; multiple workers need a shared store.
    """

    def __init__(self, ip_limit=30, username_limit=10, window=300, max_keys=4096, clock=time.monotonic):
        self.ip_limit = ip_limit
        self.username_limit = username_limit
        self.window = window
        self.max_keys = max_keys
        self.clock = clock
        self._buckets = {}
        self._lock = threading.Lock()

    def _prune(self, bucket, now):
        while bucket.failures and bucket.failures[0] <= now - self.window:
            bucket.failures.popleft()

    @staticmethod
    def _reject(seconds):
        raise HTTPException(429, "登录失败次数过多，请稍后重试", headers={"Retry-After": str(max(1, math.ceil(seconds)))})

    @contextmanager
    def attempt(self, client_ip: str, username: str):
        keys = (("ip", client_ip), ("username", username))
        limits = (self.ip_limit, self.username_limit)
        with self._lock:
            now = self.clock()
            for key, limit in zip(keys, limits):
                bucket = self._buckets.get(key)
                if bucket is not None:
                    self._prune(bucket, now)
                    if len(bucket.failures) + bucket.pending >= limit:
                        self._reject(bucket.failures[0] + self.window - now if bucket.failures else 1)
            missing = sum(key not in self._buckets for key in keys)
            if len(self._buckets) + missing > self.max_keys:
                for key, bucket in list(self._buckets.items()):
                    self._prune(bucket, now)
                    if not bucket.pending and not bucket.failures:
                        del self._buckets[key]
                missing = sum(key not in self._buckets for key in keys)
                if len(self._buckets) + missing > self.max_keys:
                    self._reject(self.window)
            buckets = [self._buckets.setdefault(key, _Bucket()) for key in keys]
            for bucket in buckets:
                bucket.pending += 1
        attempt = _Attempt()
        try:
            yield attempt
        finally:
            with self._lock:
                now = self.clock()
                for key, bucket in zip(keys, buckets):
                    bucket.pending -= 1
                    self._prune(bucket, now)
                    if not attempt.success:
                        bucket.failures.append(now)
                    if not bucket.pending and not bucket.failures:
                        del self._buckets[key]


login_limiter = LoginLimiter()
