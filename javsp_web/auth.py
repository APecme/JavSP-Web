from __future__ import annotations

import secrets
import threading
import time

from fastapi import Cookie, Depends, HTTPException, status

from .storage import find_user_by_id

SESSION_COOKIE = "javsp_web_session"
_sessions: dict[str, tuple[str, str, float]] = {}
_session_lock = threading.RLock()


def create_session(user: dict) -> str:
    """Bind to the exact account snapshot whose password was verified."""
    token = secrets.token_urlsafe(32)
    with _session_lock:
        _sessions[token] = (user["user_id"], user["auth_version"], time.time() + 60 * 60 * 12)
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
        if not record or len(record) != 3 or record[2] <= time.time():
            _sessions.pop(token, None)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user = find_user_by_id(record[0])
    if not user or user.get("auth_version") != record[1]:
        remove_session(token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    return {"username": user["username"], "role": user.get("role", "operator")}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
