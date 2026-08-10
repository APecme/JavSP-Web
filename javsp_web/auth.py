from __future__ import annotations

import secrets
import threading
import time

from fastapi import Cookie, Depends, HTTPException, status

from .storage import find_user

SESSION_COOKIE = "javsp_web_session"
_sessions: dict[str, tuple[str, float]] = {}
_session_lock = threading.RLock()


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _session_lock:
        _sessions[token] = (username, time.time() + 60 * 60 * 12)
    return token


def remove_session(token: str | None) -> None:
    if token:
        with _session_lock:
            _sessions.pop(token, None)


def current_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    with _session_lock:
        record = _sessions.get(token)
        if not record or record[1] < time.time():
            _sessions.pop(token, None)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user = find_user(record[0])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return {"username": user["username"], "role": user.get("role", "operator")}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
