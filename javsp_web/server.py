from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from croniter import croniter
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .auth import SESSION_COOKIE, create_session, current_user, remove_session, require_admin
from .config_validation import load_base_config, validate_config_data
from .storage import (
    delete_preset,
    claim_auto_scrape_schedule_run,
    delete_user,
    ensure_seed_data,
    find_user,
    get_preset,
    get_qbittorrent_settings,
    get_qbittorrent_management,
    IS_FROZEN,
    list_presets,
    list_auto_scrape_schedules,
    list_downloaders,
    list_path_mappings,
    list_media_servers,
    list_users,
    now_iso,
    read_config,
    record_auto_scrape_schedule_result,
    skip_auto_scrape_schedule_run,
    load_auto_scrape_history,
    save_preset,
    save_qbittorrent_settings,
    save_downloaders,
    save_path_mappings,
    save_auto_scrape_history,
    save_auto_scrape_schedules,
    save_media_servers,
    save_qbittorrent_management,
    upsert_user,
    verify_password,
    write_config,
)
from .qbittorrent import QbittorrentError, delete_torrent, list_downloads, set_share_limits, set_torrent_transfer_limits, test_connection
from .media import list_media_libraries, media_links_for_task, sync_media_server
from .tasks import active_schedule_task_ids, cancel_task, create_tasks, delete_task, get_cover_path, get_fanart_path, get_task, list_tasks, recover_interrupted_tasks, retry_task_images, restore_task_files, search_google_cover, select_google_cover
from .timeutils import local_now, timezone_name


ensure_seed_data()
recover_interrupted_tasks()
app = FastAPI(title="JavSP WEB", version=__version__)
WEB_DIR = Path(__file__).resolve().parent / "web"


@app.middleware("http")
async def disable_asset_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
IS_DOCKER = Path("/.dockerenv").exists() or os.environ.get("JAVSP_WEB_DOCKER") == "1"
CONTAINER_BROWSE_ROOT = Path("/")
VIDEO_EXTENSIONS = {".3gp", ".avi", ".f4v", ".flv", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv", ".strm", ".mpg"}
_auto_scrape_run_lock = threading.RLock()


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(default=None, max_length=256)
    password_confirm: str | None = Field(default=None, max_length=256)
    role: str = "operator"
    old_username: str | None = None


class ConfigBody(BaseModel):
    content: str = Field(min_length=1)


class CrawlerConfigBody(BaseModel):
    selection: dict[str, list[str]]


class TaskBody(BaseModel):
    input_directory: str = Field(min_length=1)
    preset_id: str = "default"


class PresetBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["yaml", "form"] = "form"
    content: str | None = None
    form: dict = Field(default_factory=dict)
    task_concurrency: int = Field(default=1, ge=1, le=32)


class PresetConvertBody(BaseModel):
    mode: Literal["yaml", "form"]
    content: str | None = None
    form: dict = Field(default_factory=dict)


class PathSelectBody(BaseModel):
    kind: Literal["file", "directory"] = "file"


class QbittorrentSettingsBody(BaseModel):
    url: str = Field(min_length=1, max_length=512)
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=256)


class DownloaderBody(QbittorrentSettingsBody):
    name: str = Field(min_length=1, max_length=80)


class MediaServerBody(BaseModel):
    server_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    type: Literal["emby", "jellyfin"] = "emby"
    url: str = Field(min_length=1, max_length=512)
    external_url: str = Field(default="", max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    auto_scan: bool = False
    auto_scan_delay: int = Field(default=0, ge=0, le=86400)
    libraries: list[str] = Field(default_factory=list, max_length=100)


class AutoScrapeRuleBody(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    tags: str = Field(default="", max_length=512)
    category: str = Field(default="", max_length=256)
    preset_id: str = Field(default="default", max_length=128)


class AutoScrapeScheduleBody(BaseModel):
    name: str = Field(default="", max_length=80)
    enabled: bool = True
    cron: str = Field(min_length=1, max_length=160)
    input_directory: str = Field(min_length=1, max_length=2048)
    preset_id: str = Field(default="default", max_length=128)


class QbittorrentManagementBody(BaseModel):
    takeover_enabled: bool = False
    takeover_tags: str = Field(default="", max_length=512)
    takeover_category: str = Field(default="", max_length=256)
    ratio_limit: float = Field(default=-1, ge=-1, le=100000)
    seeding_time_limit: int = Field(default=-1, ge=-1, le=10_000_000)
    inactive_seeding_time_limit: int = Field(default=-1, ge=-1, le=10_000_000)
    download_limit_kib: int = Field(default=-1, ge=-1, le=10_000_000)
    upload_limit_kib: int = Field(default=-1, ge=-1, le=10_000_000)
    auto_remove: bool = False
    auto_scrape_enabled: bool = False
    auto_scrape_tags: str = Field(default="", max_length=512)
    auto_scrape_category: str = Field(default="", max_length=256)
    auto_scrape_preset_id: str = "default"
    auto_scrape_rules: list[AutoScrapeRuleBody] = Field(default_factory=list, max_length=100)


class PathMappingBody(BaseModel):
    source_path: str = Field(min_length=1, max_length=1024)
    target_path: str = Field(min_length=1, max_length=1024)


class PathMappingsBody(BaseModel):
    mappings: list[PathMappingBody] = Field(default_factory=list, max_length=100)


@app.get("/api/runtime")
def runtime(_: dict = Depends(current_user)) -> dict:
    return {"deployment": "docker" if IS_DOCKER else ("exe" if IS_FROZEN else "python"), "docker": IS_DOCKER, "version": __version__, "timezone": timezone_name()}


@app.post("/api/path/select")
def select_path(body: PathSelectBody, _: dict = Depends(current_user)) -> dict:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if body.kind == "directory":
            selected = filedialog.askdirectory(title="选择待刮削目录")
        else:
            selected = filedialog.askopenfilename(
                title="选择待刮削视频文件",
                filetypes=[("视频文件", "*.3gp *.avi *.f4v *.flv *.iso *.m2ts *.m4v *.mkv *.mov *.mp4 *.mpeg *.rm *.rmvb *.ts *.vob *.webm *.wmv *.strm *.mpg"), ("所有文件", "*.*")],
            )
        root.destroy()
        return {"path": selected or None}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"无法打开系统选择窗口: {exc}") from exc


@app.get("/api/path/options")
def path_options(_: dict = Depends(current_user)) -> list[dict]:
    """Compatibility endpoint kept for older Web clients.

    It intentionally exposes only the first level. New clients use
    ``/api/path/browse`` to navigate one directory at a time.
    """
    if not IS_DOCKER:
        return []
    root = CONTAINER_BROWSE_ROOT
    if not root.exists():
        return []
    options = [{"path": "/", "kind": "directory"}]
    try:
        for item in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
            if item.is_dir() or (item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS):
                options.append({"path": item.as_posix(), "kind": "directory" if item.is_dir() else "file"})
    except OSError:
        return options
    return options


def _container_browse_path(path: str | None) -> Path:
    """Resolve an absolute or root-relative path inside the container."""
    root = CONTAINER_BROWSE_ROOT.resolve()
    requested = str(path or root).strip()
    requested_path = Path(requested)
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="路径必须位于容器文件系统内") from exc
    return resolved


@app.get("/api/path/browse")
def browse_path(path: str = Query(default="/", max_length=2048), _: dict = Depends(current_user)) -> dict:
    if not IS_DOCKER:
        raise HTTPException(status_code=400, detail="当前部署方式不需要浏览容器路径")
    current = _container_browse_path(path)
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=400, detail="目录不存在或不可访问")
    root = CONTAINER_BROWSE_ROOT.resolve()
    entries: list[dict] = []
    try:
        children = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        for item in children:
            resolved = item.resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if item.is_dir():
                entries.append({"name": item.name, "path": resolved.as_posix(), "kind": "directory"})
            elif item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                entries.append({"name": item.name, "path": resolved.as_posix(), "kind": "file"})
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法读取目录: {exc}") from exc
    parent = current.parent if current != root else None
    return {"path": current.as_posix(), "parent": parent.as_posix() if parent else None, "entries": entries}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/public-info")
def public_info() -> dict:
    return {"name": "JavSP WEB", "version": __version__}


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(WEB_DIR / "login.html")


@app.get("/")
def index_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(WEB_DIR / "assets" / "javsp-logo.ico", headers={"Cache-Control": "no-cache"})


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response) -> dict:
    user = find_user(body.username)
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    response.set_cookie(SESSION_COOKIE, create_session(user["username"]), httponly=True, samesite="lax", max_age=43200)
    return {"username": user["username"], "role": user.get("role", "operator")}


@app.post("/api/auth/logout")
def logout(response: Response, cookie_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    remove_session(cookie_token)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user


@app.get("/api/users")
def users(_: dict = Depends(require_admin)) -> list[dict]:
    return list_users()


def _validate_password_change(body: UserBody, required: bool = False) -> None:
    if required and not body.password:
        raise HTTPException(status_code=400, detail="新用户必须设置密码")
    if body.password and body.password != body.password_confirm:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")


@app.post("/api/users")
def create_user(body: UserBody, _: dict = Depends(require_admin)) -> dict:
    if find_user(body.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    _validate_password_change(body, required=True)
    upsert_user(body.username, body.password, body.role)
    return {"ok": True}


@app.put("/api/users/{username}")
def update_user(username: str, body: UserBody, _: dict = Depends(require_admin)) -> dict:
    if not find_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    _validate_password_change(body)
    if body.username != username and find_user(body.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    upsert_user(body.username, body.password, body.role, old_username=username)
    return {"ok": True}


@app.delete("/api/users/{username}")
def remove_user(username: str, user: dict = Depends(require_admin)) -> dict:
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    if not delete_user(username):
        raise HTTPException(status_code=400, detail="至少保留一个用户")
    return {"ok": True}


@app.get("/api/presets")
def presets(_: dict = Depends(current_user)) -> list[dict]:
    return [_public_preset(item) for item in list_presets()]


@app.post("/api/presets/convert")
def convert_preset(body: PresetConvertBody, _: dict = Depends(current_user)) -> dict:
    base = _base_config()
    if body.mode == "yaml":
        if not body.content:
            raise HTTPException(status_code=400, detail="YAML 内容不能为空")
        try:
            parsed = yaml.safe_load(body.content) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=400, detail=f"YAML 格式错误: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")
        try:
            validate_config_data(_deep_merge(base, parsed))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"form": _deep_merge(base, parsed)}
    form = _normalize_form(body.form, base)
    try:
        validate_config_data(_deep_merge(base, form))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"content": yaml.safe_dump(_deep_merge(base, form), allow_unicode=True, sort_keys=False)}


def _prepare_preset(body: PresetBody) -> dict:
    base = _base_config()
    if body.mode == "yaml":
        if not body.content:
            raise HTTPException(status_code=400, detail="YAML 预设不能为空")
        try:
            parsed = yaml.safe_load(body.content)
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=400, detail=f"YAML 格式错误: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")
        form = {}
    else:
        form = _normalize_form(body.form, base)
        parsed = form
    try:
        validate_config_data(_deep_merge(base, parsed))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"form": form, "parsed": parsed}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _drop_empty_strings(value):
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _drop_empty_strings(item)) is not None
        }
    if isinstance(value, list):
        return [_drop_empty_strings(item) for item in value]
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _coerce_like(value, template):
    if isinstance(value, dict):
        template = template if isinstance(template, dict) else {}
        return {key: _coerce_like(item, template.get(key)) for key, item in value.items()}
    if isinstance(value, str):
        if isinstance(template, str):
            return value
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            parsed = value
        if parsed is None and value.strip() not in {"", "null", "~"}:
            return value
        return parsed
    return value


def _base_config() -> dict:
    return load_base_config()


_CRAWLER_IDS = {
    "airav", "avsox", "avwiki", "dl_getchu", "fanza", "fc2", "fc2fan", "fc2ppvdb", "gyutto",
    "jav321", "javbus", "javdb", "javlib", "javmenu", "mgstage", "njav", "prestige", "arzon", "arzon_iv",
}
_CRAWLER_GROUPS = {"normal", "fc2", "cid", "getchu", "gyutto"}


def _validated_crawler_selection(selection: dict[str, list[str]]) -> dict[str, list[str]]:
    if set(selection) != _CRAWLER_GROUPS:
        raise HTTPException(status_code=400, detail="爬虫配置必须包含普通影片、FC2、CID、Getchu 和 Gyutto 五类")
    cleaned: dict[str, list[str]] = {}
    for group, crawlers in selection.items():
        if not isinstance(crawlers, list) or not all(isinstance(item, str) and item in _CRAWLER_IDS for item in crawlers):
            raise HTTPException(status_code=400, detail=f"{group} 包含不支持的爬虫")
        if len(crawlers) != len(set(crawlers)):
            raise HTTPException(status_code=400, detail=f"{group} 不能重复添加同一爬虫")
        cleaned[group] = crawlers
    return cleaned


def _normalize_form(form: dict, base: dict | None = None) -> dict:
    base = base or _base_config()
    normalized = {}
    for section, value in form.items():
        if not isinstance(value, (str, dict)):
            raise HTTPException(status_code=400, detail=f"分类 {section} 必须是 YAML 文本或对象")
        if isinstance(value, str):
            try:
                value = yaml.safe_load(value) or {}
            except yaml.YAMLError as exc:
                raise HTTPException(status_code=400, detail=f"分类 {section} 的 YAML 格式错误: {exc}") from exc
        if not isinstance(value, dict):
            raise HTTPException(status_code=400, detail=f"分类 {section} 的根节点必须是对象")
        value = _drop_empty_strings(value) or {}
        normalized[section] = _coerce_like(value, base.get(section, {}))
    return normalized


def _public_preset(preset: dict) -> dict:
    result = dict(preset)
    try:
        result["task_concurrency"] = max(1, min(32, int(result.get("task_concurrency", 1))))
    except (TypeError, ValueError):
        result["task_concurrency"] = 1
    base = _base_config()
    if result.get("mode") == "form":
        result["form_text"] = {
            section: yaml.safe_dump(value or {}, allow_unicode=True, sort_keys=False)
            for section, value in (result.get("form") or {}).items()
        }
        result["form_values"] = _deep_merge(base, result.get("form") or {})
    elif result.get("content"):
        try:
            parsed = yaml.safe_load(result["content"]) or {}
        except yaml.YAMLError:
            parsed = {}
        if isinstance(parsed, dict):
            result["form_text"] = {
                section: yaml.safe_dump(value or {}, allow_unicode=True, sort_keys=False)
                for section, value in parsed.items()
                if isinstance(value, dict)
            }
            result["form_values"] = _deep_merge(base, parsed)
    if "form_values" not in result:
        result["form_values"] = base
    return result


@app.post("/api/presets")
def create_preset(body: PresetBody, _: dict = Depends(require_admin)) -> dict:
    prepared = _prepare_preset(body)
    form = prepared["form"]
    preset = {
        "id": uuid.uuid4().hex[:10],
        "name": body.name,
        "mode": body.mode,
        "content": body.content or "",
        "form": form,
        "task_concurrency": body.task_concurrency,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    save_preset(preset)
    return _public_preset(preset)


@app.put("/api/presets/{preset_id}")
def update_preset(preset_id: str, body: PresetBody, _: dict = Depends(require_admin)) -> dict:
    current = get_preset(preset_id)
    if not current:
        raise HTTPException(status_code=404, detail="预设不存在")
    prepared = _prepare_preset(body)
    form = prepared["form"]
    current.update({"name": body.name, "mode": body.mode, "content": body.content or "", "form": form, "task_concurrency": body.task_concurrency, "updated_at": now_iso()})
    save_preset(current)
    return _public_preset(current)


@app.delete("/api/presets/{preset_id}")
def remove_preset(preset_id: str, _: dict = Depends(require_admin)) -> dict:
    if not delete_preset(preset_id):
        raise HTTPException(status_code=400, detail="默认预设不能删除，或预设不存在")
    return {"ok": True}


# Kept as a compatibility API for integrations. The web UI uses presets instead.
@app.get("/api/config")
def get_config(_: dict = Depends(current_user)) -> dict:
    content = read_config()
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        parsed = {"_error": str(exc)}
    return {"content": content, "parsed": parsed}


@app.get("/api/crawler-config")
def get_crawler_config(_: dict = Depends(current_user)) -> dict:
    crawler = _base_config().get("crawler") or {}
    selection = crawler.get("selection") or {}
    return {"selection": {group: list(selection.get(group) or []) for group in sorted(_CRAWLER_GROUPS)}, "available": sorted(_CRAWLER_IDS)}


@app.put("/api/crawler-config")
def update_crawler_config(body: CrawlerConfigBody, _: dict = Depends(require_admin)) -> dict:
    selection = _validated_crawler_selection(body.selection)
    try:
        current = yaml.safe_load(read_config()) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"配置文件格式错误: {exc}") from exc
    if not isinstance(current, dict):
        raise HTTPException(status_code=400, detail="配置根节点必须是对象")
    current.setdefault("crawler", {})["selection"] = selection
    try:
        validate_config_data(_deep_merge(_base_config(), {"crawler": {"selection": selection}}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_config(yaml.safe_dump(current, allow_unicode=True, sort_keys=False))
    return {"ok": True, "selection": selection}


@app.put("/api/config")
def update_config(body: ConfigBody, _: dict = Depends(require_admin)) -> dict:
    try:
        parsed = yaml.safe_load(body.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 格式错误: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")
    try:
        validate_config_data(_deep_merge(_base_config(), parsed))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_config(body.content)
    return {"ok": True}


@app.get("/api/tasks")
def tasks(_: dict = Depends(current_user)) -> list[dict]:
    # Older task records predate the source marker. Recover their origin from
    # retained schedule and download-auto-scrape records so queues stay split.
    scheduled_ids = {
        str(task_id)
        for schedule in list_auto_scrape_schedules()
        for run in schedule.get("runs") or []
        for task_id in run.get("task_ids") or []
    }
    download_ids = {
        str(task_id)
        for entry in load_auto_scrape_history().values()
        if isinstance(entry, dict)
        for task_id in entry.get("task_ids") or []
    }
    items = list_tasks()
    for item in items:
        if item.get("source"):
            continue
        item["source"] = "schedule" if item.get("id") in scheduled_ids else ("download" if item.get("id") in download_ids else "manual")
    return items


@app.post("/api/tasks", status_code=202)
def start_task(body: TaskBody, _: dict = Depends(current_user)) -> dict:
    try:
        tasks = create_tasks(body.input_directory, body.preset_id)
        return {"tasks": tasks, "count": len(tasks)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}")
def task(task_id: str, _: dict = Depends(current_user)) -> dict:
    item = get_task(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    return item


@app.get("/api/tasks/{task_id}/cover/{index:int}")
def task_cover(task_id: str, index: int, _: dict = Depends(current_user)) -> FileResponse:
    path = get_cover_path(task_id, index)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="封面不存在")
    return FileResponse(path)


@app.get("/api/tasks/{task_id}/fanart/{index:int}")
def task_fanart(task_id: str, index: int, _: dict = Depends(current_user)) -> FileResponse:
    path = get_fanart_path(task_id, index)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="剧照不存在")
    return FileResponse(path)


@app.get("/api/tasks/{task_id}/media-links")
def task_media_links(task_id: str, _: dict = Depends(current_user)) -> dict:
    item = get_task(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"links": media_links_for_task(item)}


def _public_media_server(server: dict) -> dict:
    return {
        "id": server.get("id", ""),
        "name": server.get("name", ""),
        "type": server.get("type", "emby"),
        "url": server.get("url", ""),
        "external_url": server.get("external_url", ""),
        "api_key_set": bool(server.get("api_key")),
        "auto_scan": bool(server.get("auto_scan")),
        "auto_scan_delay": int(server.get("auto_scan_delay", 0) or 0),
        "libraries": list(server.get("libraries") or []),
    }


def _media_server_from_body(body: MediaServerBody, current: dict | None = None) -> dict:
    current = current or {}
    return {
        "id": current.get("id") or uuid.uuid4().hex,
        "name": body.name.strip(),
        "type": body.type,
        "url": body.url.strip().rstrip("/"),
        "external_url": body.external_url.strip().rstrip("/"),
        "api_key": body.api_key.strip() if body.api_key else current.get("api_key", ""),
        "auto_scan": body.auto_scan,
        "auto_scan_delay": body.auto_scan_delay,
        "libraries": [str(value).strip() for value in body.libraries if str(value).strip()],
    }


def _validate_media_server(server: dict, require_library: bool = True) -> None:
    try:
        libraries = list_media_libraries(server)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"媒体服务器连接失败: {exc}") from exc
    available = {item["id"] for item in libraries}
    selected = set(server.get("libraries") or [])
    if require_library and available and not selected:
        raise HTTPException(status_code=400, detail="请选择要管理的媒体库")
    if selected - available:
        raise HTTPException(status_code=400, detail="选择的媒体库不存在或已失效，请重新读取")
    server["available_libraries"] = libraries


def _find_media_server(server_id: str) -> tuple[int, dict] | tuple[None, None]:
    for index, server in enumerate(list_media_servers()):
        if server.get("id") == server_id:
            return index, server
    return None, None


@app.get("/api/media-servers")
def get_media_servers(_: dict = Depends(require_admin)) -> list[dict]:
    return [_public_media_server(server) for server in list_media_servers()]


@app.post("/api/media-servers")
def create_media_server(body: MediaServerBody, _: dict = Depends(require_admin)) -> dict:
    server = _media_server_from_body(body)
    _validate_media_server(server)
    server.pop("available_libraries", None)
    servers = list_media_servers()
    servers.append(server)
    save_media_servers(servers)
    return _public_media_server(server)


@app.put("/api/media-servers/{server_id}")
def update_media_server(server_id: str, body: MediaServerBody, _: dict = Depends(require_admin)) -> dict:
    index, current = _find_media_server(server_id)
    if current is None or index is None:
        raise HTTPException(status_code=404, detail="媒体服务器不存在")
    server = _media_server_from_body(body, current)
    _validate_media_server(server)
    server.pop("available_libraries", None)
    servers = list_media_servers()
    servers[index] = server
    save_media_servers(servers)
    return _public_media_server(server)


@app.delete("/api/media-servers/{server_id}")
def remove_media_server(server_id: str, _: dict = Depends(require_admin)) -> dict:
    servers = [server for server in list_media_servers() if server.get("id") != server_id]
    if len(servers) == len(list_media_servers()):
        raise HTTPException(status_code=404, detail="媒体服务器不存在")
    save_media_servers(servers)
    return {"ok": True}


@app.post("/api/media-servers/{server_id}/sync")
def sync_configured_media_server(server_id: str, _: dict = Depends(require_admin)) -> dict:
    _, server = _find_media_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="媒体服务器不存在")
    try:
        return sync_media_server(server)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"媒体库同步失败: {exc}") from exc


@app.post("/api/media-servers/libraries")
def probe_media_server_libraries(body: MediaServerBody, _: dict = Depends(require_admin)) -> dict:
    current = {}
    if body.server_id:
        _, current = _find_media_server(body.server_id)
        current = current or {}
    server = _media_server_from_body(body, current)
    try:
        return {"libraries": list_media_libraries(server)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"媒体服务器连接失败: {exc}") from exc


def _public_qbittorrent_settings(settings: dict) -> dict:
    return {
        "url": settings.get("url", "http://127.0.0.1:8080"),
        "username": settings.get("username", ""),
        "password_set": bool(settings.get("password")),
    }


def _qbittorrent_settings_from_body(body: QbittorrentSettingsBody, current: dict) -> dict:
    return {
        "url": body.url.strip().rstrip("/"),
        "username": body.username.strip(),
        "password": body.password if body.password else current.get("password", ""),
    }


@app.get("/api/qbittorrent/settings")
def get_qbittorrent_config(_: dict = Depends(require_admin)) -> dict:
    return _public_qbittorrent_settings(get_qbittorrent_settings())


@app.put("/api/qbittorrent/settings")
def update_qbittorrent_config(body: QbittorrentSettingsBody, _: dict = Depends(require_admin)) -> dict:
    current = get_qbittorrent_settings()
    settings = _qbittorrent_settings_from_body(body, current)
    try:
        test_connection(settings)
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_qbittorrent_settings(settings)
    return _public_qbittorrent_settings(settings)


@app.post("/api/qbittorrent/test")
def test_qbittorrent_config(body: QbittorrentSettingsBody, _: dict = Depends(require_admin)) -> dict:
    current = get_qbittorrent_settings()
    try:
        result = test_connection(_qbittorrent_settings_from_body(body, current))
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


def _public_downloader(settings: dict) -> dict:
    return {
        "id": settings.get("id", ""),
        "name": settings.get("name", "qBittorrent"),
        "type": "qbittorrent",
        "url": settings.get("url", ""),
        "username": settings.get("username", ""),
        "password_set": bool(settings.get("password")),
    }


def _downloader_from_body(body: DownloaderBody, current: dict | None = None) -> dict:
    current = current or {}
    return {
        "id": current.get("id") or uuid.uuid4().hex,
        "name": body.name.strip(),
        "type": "qbittorrent",
        "url": body.url.strip().rstrip("/"),
        "username": body.username.strip(),
        "password": body.password if body.password else current.get("password", ""),
    }


def _find_downloader(downloader_id: str) -> tuple[int, dict] | tuple[None, None]:
    for index, downloader in enumerate(list_downloaders()):
        if downloader.get("id") == downloader_id:
            return index, downloader
    return None, None


@app.get("/api/downloaders")
def get_downloaders(_: dict = Depends(require_admin)) -> list[dict]:
    return [_public_downloader(downloader) for downloader in list_downloaders()]


@app.post("/api/downloaders")
def create_downloader(body: DownloaderBody, _: dict = Depends(require_admin)) -> dict:
    downloader = _downloader_from_body(body)
    try:
        test_connection(downloader)
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    downloaders = list_downloaders()
    downloaders.append(downloader)
    save_downloaders(downloaders)
    return _public_downloader(downloader)


@app.put("/api/downloaders/{downloader_id}")
def update_downloader(downloader_id: str, body: DownloaderBody, _: dict = Depends(require_admin)) -> dict:
    index, current = _find_downloader(downloader_id)
    if current is None or index is None:
        raise HTTPException(status_code=404, detail="下载器不存在")
    downloader = _downloader_from_body(body, current)
    try:
        test_connection(downloader)
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    downloaders = list_downloaders()
    downloaders[index] = downloader
    save_downloaders(downloaders)
    return _public_downloader(downloader)


@app.post("/api/downloaders/test")
def test_downloader(body: DownloaderBody, _: dict = Depends(require_admin)) -> dict:
    try:
        result = test_connection(_downloader_from_body(body))
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/downloaders/{downloader_id}/test")
def test_saved_downloader(downloader_id: str, body: DownloaderBody, _: dict = Depends(require_admin)) -> dict:
    _, current = _find_downloader(downloader_id)
    if current is None:
        raise HTTPException(status_code=404, detail="下载器不存在")
    try:
        result = test_connection(_downloader_from_body(body, current))
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.delete("/api/downloaders/{downloader_id}")
def remove_downloader(downloader_id: str, _: dict = Depends(require_admin)) -> dict:
    downloaders = list_downloaders()
    filtered = [downloader for downloader in downloaders if downloader.get("id") != downloader_id]
    if len(filtered) == len(downloaders):
        raise HTTPException(status_code=404, detail="下载器不存在")
    save_downloaders(filtered)
    return {"ok": True}


def _public_qbittorrent_management(settings: dict) -> dict:
    rules = _auto_scrape_rules(settings)
    first_rule = rules[0] if rules else {"enabled": False, "tags": "", "category": "", "preset_id": "default"}
    return {
        "takeover_enabled": bool(settings.get("takeover_enabled")),
        "takeover_tags": settings.get("takeover_tags", ""),
        "takeover_category": settings.get("takeover_category", ""),
        "ratio_limit": settings.get("ratio_limit", -1),
        "seeding_time_limit": settings.get("seeding_time_limit", -1),
        "inactive_seeding_time_limit": settings.get("inactive_seeding_time_limit", -1),
        "download_limit_kib": settings.get("download_limit_kib", -1),
        "upload_limit_kib": settings.get("upload_limit_kib", -1),
        "auto_remove": bool(settings.get("auto_remove")),
        # Keep the legacy values in responses for clients from older packaged builds.
        "auto_scrape_enabled": bool(first_rule.get("enabled")),
        "auto_scrape_tags": first_rule.get("tags", ""),
        "auto_scrape_category": first_rule.get("category", ""),
        "auto_scrape_preset_id": first_rule.get("preset_id", "default"),
        "auto_scrape_rules": rules,
    }


def _managed_download(item: dict, management: dict) -> bool:
    if not management.get("takeover_enabled"):
        return False
    tags = {value.strip() for value in str(management.get("takeover_tags") or "").split(",") if value.strip()}
    item_tags = {value.strip() for value in str(item.get("tags") or "").split(",") if value.strip()}
    category = str(management.get("takeover_category") or "").strip()
    return (not tags or bool(tags & item_tags)) and (not category or item.get("category") == category)


def _auto_scrape_rules(management: dict) -> list[dict]:
    """Return the new multi-rule representation, upgrading a legacy saved rule."""
    rules: list[dict] = []
    raw_rules = management.get("auto_scrape_rules")
    if isinstance(raw_rules, list):
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            rules.append({
                "id": str(raw.get("id") or uuid.uuid4().hex[:12]),
                "enabled": bool(raw.get("enabled", True)),
                "tags": str(raw.get("tags") or "").strip(),
                "category": str(raw.get("category") or "").strip(),
                "preset_id": str(raw.get("preset_id") or "default").strip() or "default",
            })
    if not rules and management.get("auto_scrape_enabled"):
        rules.append({
            "id": "legacy-default",
            "enabled": True,
            "tags": str(management.get("auto_scrape_tags") or "").strip(),
            "category": str(management.get("auto_scrape_category") or "").strip(),
            "preset_id": str(management.get("auto_scrape_preset_id") or "default").strip() or "default",
        })
    return rules


def _auto_scrape_match(item: dict, rule: dict) -> bool:
    if not rule.get("enabled") or float(item.get("progress", 0) or 0) < 100:
        return False
    tags = {value.strip() for value in str(rule.get("tags") or "").split(",") if value.strip()}
    item_tags = {value.strip() for value in str(item.get("tags") or "").split(",") if value.strip()}
    category = str(rule.get("category") or "").strip()
    return (not tags or bool(tags & item_tags)) and (not category or item.get("category") == category)


def _map_download_path(source_path: str, mappings: list[dict]) -> str:
    source = str(source_path or "").strip().replace("\\", "/").rstrip("/")
    if not source:
        return ""
    for mapping in sorted(mappings, key=lambda item: len(str(item.get("source_path") or "")), reverse=True):
        source_root = str(mapping.get("source_path") or "").strip().replace("\\", "/").rstrip("/")
        target_root = str(mapping.get("target_path") or "").strip().rstrip("/\\")
        if not source_root or not target_root:
            continue
        insensitive = os.name == "nt" or ":" in source_root
        compared_source = source.lower() if insensitive else source
        compared_root = source_root.lower() if insensitive else source_root
        if compared_source == compared_root or compared_source.startswith(compared_root + "/"):
            suffix = source[len(source_root):].lstrip("/")
            return os.path.normpath(os.path.join(target_root, *suffix.split("/"))) if suffix else os.path.normpath(target_root)
    return source_path


def _auto_scrape_downloads(downloader: dict, downloads: list[dict], management: dict) -> None:
    rules = [rule for rule in _auto_scrape_rules(management) if rule.get("enabled")]
    if not rules:
        return
    mappings = list_path_mappings()
    history = load_auto_scrape_history()
    changed = False
    for item in downloads:
        # A completed download starts at most one scrape. The first matching rule
        # defines the preset so broad fallback rules can safely be placed last.
        rule = next((candidate for candidate in rules if _auto_scrape_match(item, candidate)), None)
        if rule is None:
            continue
        key = f"{downloader.get('id')}:{item.get('hash')}"
        if key in history:
            continue
        preset_id = rule["preset_id"]
        if not get_preset(preset_id):
            continue
        mapped_path = _map_download_path(str(item.get("content_path") or ""), mappings)
        if not mapped_path or not os.path.exists(mapped_path):
            continue
        try:
            created = create_tasks(mapped_path, preset_id, source="download")
        except ValueError:
            continue
        history[key] = {"created_at": now_iso(), "path": mapped_path, "preset_id": preset_id, "task_ids": [task["id"] for task in created]}
        changed = True
    if changed:
        save_auto_scrape_history(history)


def _auto_remove_downloads(settings: dict, downloads: list[dict], management: dict) -> list[str]:
    removed: list[str] = []
    for item in downloads:
        if not management.get("auto_remove") or item.get("progress", 0) < 100:
            continue
        ratio_limit = float(management.get("ratio_limit", -1))
        seed_limit = int(management.get("seeding_time_limit", -1))
        inactive_limit = int(management.get("inactive_seeding_time_limit", -1))
        reached = (ratio_limit >= 0 and item.get("ratio", 0) >= ratio_limit) or (seed_limit >= 0 and item.get("seeding_time", 0) >= seed_limit * 60) or (inactive_limit >= 0 and item.get("inactive_seeding_time", 0) >= inactive_limit * 60)
        if reached:
            delete_torrent(settings, item["hash"])
            removed.append(item["hash"])
    return removed


@app.get("/api/downloads/settings")
def get_download_management(_: dict = Depends(require_admin)) -> dict:
    return _public_qbittorrent_management(get_qbittorrent_management())


@app.put("/api/downloads/settings")
def update_download_management(body: QbittorrentManagementBody, _: dict = Depends(require_admin)) -> dict:
    management = body.model_dump()
    management["takeover_tags"] = management["takeover_tags"].strip()
    management["takeover_category"] = management["takeover_category"].strip()
    rules: list[dict] = []
    seen_rule_ids: set[str] = set()
    for rule in body.auto_scrape_rules:
        rule_id = (rule.id or uuid.uuid4().hex[:12]).strip()
        if not rule_id or rule_id in seen_rule_ids:
            rule_id = uuid.uuid4().hex[:12]
        seen_rule_ids.add(rule_id)
        preset_id = rule.preset_id.strip() or "default"
        if not get_preset(preset_id):
            raise HTTPException(status_code=400, detail="指定的刮削预设不存在")
        rules.append({
            "id": rule_id,
            "enabled": rule.enabled,
            "tags": rule.tags.strip(),
            "category": rule.category.strip(),
            "preset_id": preset_id,
        })
    management["auto_scrape_rules"] = rules
    # Preserve a meaningful legacy snapshot for an older executable sharing data.
    first_rule = rules[0] if rules else {"enabled": False, "tags": "", "category": "", "preset_id": "default"}
    management["auto_scrape_enabled"] = bool(first_rule["enabled"])
    management["auto_scrape_tags"] = first_rule["tags"]
    management["auto_scrape_category"] = first_rule["category"]
    management["auto_scrape_preset_id"] = first_rule["preset_id"]
    save_qbittorrent_management(management)
    return _public_qbittorrent_management(management)


@app.get("/api/downloads")
def downloads(_: dict = Depends(current_user)) -> dict:
    management = get_qbittorrent_management()
    result: list[dict] = []
    for settings in list_downloaders():
        try:
            items = list_downloads(settings)
            for item in items:
                item["managed"] = _managed_download(item, management)
            managed_items = [item for item in items if item["managed"]]
            if management.get("takeover_enabled"):
                _auto_remove_downloads(settings, managed_items, management)
            result.append({"id": settings["id"], "name": settings["name"], "items": items, "error": None})
        except QbittorrentError as exc:
            # One unavailable endpoint must not hide tasks from the other downloaders.
            result.append({"id": settings["id"], "name": settings["name"], "items": [], "error": str(exc)})
    return {"takeover_enabled": bool(management.get("takeover_enabled")), "downloaders": result}


@app.get("/api/path-mappings")
def get_path_mappings(_: dict = Depends(require_admin)) -> dict:
    return {"mappings": list_path_mappings()}


@app.put("/api/path-mappings")
def update_path_mappings(body: PathMappingsBody, _: dict = Depends(require_admin)) -> dict:
    mappings = [{"id": uuid.uuid4().hex[:12], "source_path": item.source_path.strip(), "target_path": item.target_path.strip()} for item in body.mappings]
    save_path_mappings(mappings)
    return {"mappings": mappings}


@app.delete("/api/downloads/{downloader_id}/{torrent_hash}")
def remove_managed_download(downloader_id: str, torrent_hash: str, _: dict = Depends(require_admin)) -> dict:
    management = get_qbittorrent_management()
    _, settings = _find_downloader(downloader_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="下载器不存在")
    try:
        managed_hashes = {item["hash"] for item in list_downloads(settings) if _managed_download(item, management)}
        if torrent_hash not in managed_hashes:
            raise HTTPException(status_code=404, detail="该任务不在当前接管范围内")
        delete_torrent(settings, torrent_hash)
    except QbittorrentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


def _schedule_next_run(cron: str) -> str | None:
    try:
        return croniter(cron, local_now()).get_next(datetime).isoformat(timespec="minutes")
    except (TypeError, ValueError, KeyError):
        return None


def _public_auto_scrape_schedule(schedule: dict) -> dict:
    return {**schedule, "next_run_at": _schedule_next_run(str(schedule.get("cron") or ""))}


def _validate_auto_scrape_schedule(body: AutoScrapeScheduleBody) -> tuple[str, str, str]:
    cron = body.cron.strip()
    input_directory = body.input_directory.strip()
    preset_id = body.preset_id.strip() or "default"
    if not croniter.is_valid(cron):
        raise HTTPException(status_code=400, detail="Cron 表达式无效，请使用标准五段格式，例如：0 2 * * *")
    path = Path(os.path.abspath(os.path.expanduser(input_directory)))
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="自动刮削目录不存在或不是文件夹")
    if not get_preset(preset_id):
        raise HTTPException(status_code=400, detail="指定的刮削预设不存在")
    return cron, str(path), preset_id


def _find_auto_scrape_schedule(schedule_id: str) -> tuple[int, dict | None]:
    schedules = list_auto_scrape_schedules()
    for index, schedule in enumerate(schedules):
        if schedule.get("id") == schedule_id:
            return index, schedule
    return -1, None


def _run_auto_scrape_schedule(schedule_id: str, run_key: str) -> tuple[dict, list[dict]]:
    # A slow scrape must not cause the same cron rule to pile up new batches.
    # The lock also closes the small race between the active-task check and creation.
    with _auto_scrape_run_lock:
        active_ids = active_schedule_task_ids(schedule_id)
        if active_ids:
            skipped = skip_auto_scrape_schedule_run(schedule_id, run_key, "上一次定时刮削尚未完成，已跳过本次运行")
            if not skipped:
                raise ValueError("本次定时运行已处理")
            return skipped, []
        claimed = claim_auto_scrape_schedule_run(schedule_id, run_key)
        if not claimed:
            raise ValueError("无法创建定时自动刮削运行记录")
        try:
            created = create_tasks(
                str(claimed["input_directory"]),
                str(claimed["preset_id"]),
                source="schedule",
                schedule_id=str(claimed["id"]),
            )
        except ValueError as exc:
            record_auto_scrape_schedule_result(str(claimed["id"]), f"执行失败：{exc}")
            raise
        except Exception as exc:  # noqa: BLE001
            record_auto_scrape_schedule_result(str(claimed["id"]), f"执行异常：{exc}")
            raise
        record_auto_scrape_schedule_result(str(claimed["id"]), f"已创建 {len(created)} 个任务", [str(task["id"]) for task in created])
        return claimed, created


@app.get("/api/auto-scrape-schedules")
def get_auto_scrape_schedules(_: dict = Depends(require_admin)) -> list[dict]:
    return [_public_auto_scrape_schedule(schedule) for schedule in list_auto_scrape_schedules()]


@app.post("/api/auto-scrape-schedules")
def create_auto_scrape_schedule(body: AutoScrapeScheduleBody, _: dict = Depends(require_admin)) -> dict:
    cron, input_directory, preset_id = _validate_auto_scrape_schedule(body)
    schedules = list_auto_scrape_schedules()
    now = now_iso()
    schedule = {
        "id": uuid.uuid4().hex[:12],
        "name": body.name.strip() or Path(input_directory).name or "自动刮削规则",
        "enabled": body.enabled,
        "cron": cron,
        "input_directory": input_directory,
        "preset_id": preset_id,
        "created_at": now,
        "updated_at": now,
        "last_run_key": "",
        "last_run_at": "",
        "last_result": "尚未执行",
        "runs": [],
    }
    schedules.append(schedule)
    save_auto_scrape_schedules(schedules)
    return _public_auto_scrape_schedule(schedule)


@app.put("/api/auto-scrape-schedules/{schedule_id}")
def update_auto_scrape_schedule(schedule_id: str, body: AutoScrapeScheduleBody, _: dict = Depends(require_admin)) -> dict:
    cron, input_directory, preset_id = _validate_auto_scrape_schedule(body)
    index, existing = _find_auto_scrape_schedule(schedule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="自动刮削规则不存在")
    schedules = list_auto_scrape_schedules()
    schedule = {
        **existing,
        "name": body.name.strip() or Path(input_directory).name or "自动刮削规则",
        "enabled": body.enabled,
        "cron": cron,
        "input_directory": input_directory,
        "preset_id": preset_id,
        "updated_at": now_iso(),
    }
    schedules[index] = schedule
    save_auto_scrape_schedules(schedules)
    return _public_auto_scrape_schedule(schedule)


@app.post("/api/auto-scrape-schedules/{schedule_id}/run", status_code=202)
def run_auto_scrape_schedule_now(schedule_id: str, _: dict = Depends(require_admin)) -> dict:
    _, schedule = _find_auto_scrape_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="自动刮削规则不存在")
    try:
        claimed, created = _run_auto_scrape_schedule(schedule_id, f"manual-{uuid.uuid4().hex}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    skipped = not created and claimed.get("last_result") == "上一次定时刮削尚未完成，已跳过本次运行"
    return {"schedule_id": schedule_id, "run_id": claimed["last_run_key"], "count": len(created), "task_ids": [task["id"] for task in created], "skipped": skipped, "message": claimed.get("last_result", "")}


@app.delete("/api/auto-scrape-schedules/{schedule_id}")
def delete_auto_scrape_schedule(schedule_id: str, _: dict = Depends(require_admin)) -> dict:
    schedules = list_auto_scrape_schedules()
    filtered = [schedule for schedule in schedules if schedule.get("id") != schedule_id]
    if len(filtered) == len(schedules):
        raise HTTPException(status_code=404, detail="自动刮削规则不存在")
    save_auto_scrape_schedules(filtered)
    return {"ok": True}


def _auto_scrape_schedule_worker() -> None:
    while True:
        now = local_now()
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        for schedule in list_auto_scrape_schedules():
            if not schedule.get("enabled"):
                continue
            try:
                due = croniter.match(str(schedule.get("cron") or ""), now)
            except (TypeError, ValueError, KeyError):
                continue
            if not due:
                continue
            try:
                _run_auto_scrape_schedule(str(schedule["id"]), minute_key)
            except Exception:
                # The execution helper has already saved the failure detail.
                continue
        # Wake frequently enough after start-up, while the minute claim prevents repeats.
        time.sleep(10)


threading.Thread(target=_auto_scrape_schedule_worker, name="auto-scrape-scheduler", daemon=True).start()


def _qbittorrent_management_worker() -> None:
    while True:
        try:
            management = get_qbittorrent_management()
            if management.get("takeover_enabled") or any(rule.get("enabled") for rule in _auto_scrape_rules(management)):
                for settings in list_downloaders():
                    try:
                        downloads = list_downloads(settings)
                        managed = [item for item in downloads if _managed_download(item, management)]
                        if management.get("takeover_enabled"):
                            for item in managed:
                                set_torrent_transfer_limits(
                                    settings,
                                    item["hash"],
                                    int(management.get("download_limit_kib", -1)),
                                    int(management.get("upload_limit_kib", -1)),
                                )
                                set_share_limits(settings, item["hash"], management)
                            _auto_remove_downloads(settings, managed, management)
                        _auto_scrape_downloads(settings, downloads, management)
                    except QbittorrentError:
                        continue
        except QbittorrentError:
            pass
        time.sleep(60)


threading.Thread(target=_qbittorrent_management_worker, name="qbittorrent-management", daemon=True).start()


@app.post("/api/tasks/{task_id}/cancel")
def stop_task(task_id: str, _: dict = Depends(current_user)) -> dict:
    if not cancel_task(task_id):
        raise HTTPException(status_code=400, detail="任务当前不可取消")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/images/retry")
def retry_images(task_id: str, _: dict = Depends(current_user)) -> dict:
    if not retry_task_images(task_id):
        raise HTTPException(status_code=400, detail="该任务没有可重新下载的失败图片，或图片重试正在进行")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/cover/google-search", status_code=202)
def search_task_cover_with_google(task_id: str, _: dict = Depends(current_user)) -> dict:
    if not search_google_cover(task_id):
        raise HTTPException(status_code=400, detail="任务不存在、封面已存在，或 Google 搜索正在进行")
    return {"ok": True}


@app.get("/api/tasks/{task_id}/cover/google-candidates")
def google_cover_candidates(task_id: str, _: dict = Depends(current_user)) -> dict:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"candidates": task.get("google_cover_candidates") or [], "status": task.get("google_cover_search_status") or "idle", "error": task.get("google_cover_search_error") or ""}


@app.post("/api/tasks/{task_id}/cover/google-select")
def select_task_cover_with_google(task_id: str, body: dict, _: dict = Depends(current_user)) -> dict:
    candidate_id = str(body.get("candidate_id") or "")
    if not candidate_id or not select_google_cover(task_id, candidate_id):
        raise HTTPException(status_code=400, detail="封面候选项无效或下载正在进行")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/restore")
def restore_files(task_id: str, _: dict = Depends(current_user)) -> dict:
    if not restore_task_files(task_id):
        raise HTTPException(status_code=400, detail="无法还原：原文件已存在、整理后文件不存在，或任务没有完整的整理记录")
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: str, _: dict = Depends(current_user)) -> dict:
    if not delete_task(task_id):
        raise HTTPException(status_code=400, detail="任务不存在或仍在运行，请先停止任务")
    return {"ok": True}


def run() -> None:
    import uvicorn

    uvicorn.run(
        "javsp_web.server:app",
        host=os.environ.get("JAVSP_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("JAVSP_WEB_PORT", "8090")),
        reload=False,
    )


if __name__ == "__main__":
    run()
