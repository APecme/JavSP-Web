from typing import Dict, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
import secrets

from .settings import load_web_settings, save_web_settings

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_COOKIE_NAME = "javsp_session"
SESSION_STORE: Dict[str, str] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    username: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    username: Optional[str] = None
    password: str


def get_current_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> UserInfo:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    username = SESSION_STORE.get(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return UserInfo(username=username)


@router.post("/login", response_model=UserInfo)
def login(body: LoginRequest, response: Response) -> UserInfo:
    settings = load_web_settings()
    if body.username != settings["username"] or body.password != settings["password"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = secrets.token_urlsafe(32)
    SESSION_STORE[token] = body.username
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
    )
    return UserInfo(username=body.username)


@router.post("/logout")
def logout(response: Response, token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> Dict[str, bool]:
    if token:
        SESSION_STORE.pop(token, None)
        response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
def me(current: UserInfo = Depends(get_current_user)) -> UserInfo:
    return current


@router.post("/password")
def change_password(
    payload: ChangePasswordRequest,
    current: UserInfo = Depends(get_current_user),
) -> Dict[str, bool]:
    settings = load_web_settings()
    if payload.old_password != settings["password"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    new_username = payload.username or settings["username"]
    save_web_settings(new_username, payload.password)
    return {"ok": True}
