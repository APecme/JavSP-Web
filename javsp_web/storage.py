from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
from pathlib import Path
from typing import Any

import yaml

from .timeutils import now_iso


IS_FROZEN = getattr(sys, "frozen", False)
ROOT_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent.parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
DATA_DIR = Path(os.environ.get("JAVSP_WEB_DATA_DIR", ROOT_DIR / "data"))
VENDOR_DIR = Path(os.environ.get("JAVSP_VENDOR_DIR", BUNDLE_DIR / "vendor" / "JavSP"))
CONFIG_FILE = DATA_DIR / "config.yml"
USERS_FILE = DATA_DIR / "users.json"
TASKS_FILE = DATA_DIR / "tasks.json"
PRESETS_FILE = DATA_DIR / "presets.json"
QBITTORRENT_FILE = DATA_DIR / "qbittorrent.json"
QBITTORRENT_MANAGEMENT_FILE = DATA_DIR / "qbittorrent-management.json"
PATH_MAPPINGS_FILE = DATA_DIR / "path-mappings.json"
AUTO_SCRAPE_HISTORY_FILE = DATA_DIR / "auto-scrape-history.json"
AUTO_SCRAPE_SCHEDULES_FILE = DATA_DIR / "auto-scrape-schedules.json"
MEDIA_SERVERS_FILE = DATA_DIR / "media-servers.json"
COOKIECLOUD_FILE = DATA_DIR / "cookiecloud.json"
CUSTOM_CRAWLERS_DIR = DATA_DIR / "crawlers"
CRAWLER_SETTINGS_FILE = DATA_DIR / "crawler-settings.json"
_lock = threading.RLock()


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240_000).hex()
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def ensure_seed_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_CRAWLERS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        users = _read_json(USERS_FILE, None)
        if not isinstance(users, list) or not users:
            _write_json(
                USERS_FILE,
                [{"username": "admin", "password": hash_password("admin"), "role": "admin", "created_at": now_iso()}],
            )
        if not CONFIG_FILE.exists():
            source = VENDOR_DIR / "config.yml"
            if source.exists():
                CONFIG_FILE.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                CONFIG_FILE.write_text("scanner:\n  input_directory: null\n  manual: false\n", encoding="utf-8")
        if not TASKS_FILE.exists():
            _write_json(TASKS_FILE, [])
        if not PRESETS_FILE.exists():
            config_content = CONFIG_FILE.read_text(encoding="utf-8")
            config_values = yaml.safe_load(config_content) or {}
            _write_json(
                PRESETS_FILE,
                [{
                    "id": "default",
                    "name": "默认配置",
                    "mode": "form",
                    "content": config_content,
                    "form": config_values if isinstance(config_values, dict) else {},
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }],
            )


def list_users() -> list[dict[str, Any]]:
    ensure_seed_data()
    with _lock:
        users = _read_json(USERS_FILE, [])
        return [{k: v for k, v in item.items() if k != "password"} for item in users]


def find_user(username: str) -> dict[str, Any] | None:
    ensure_seed_data()
    with _lock:
        for user in _read_json(USERS_FILE, []):
            if user.get("username") == username:
                return user
    return None


def upsert_user(username: str, password: str | None, role: str = "operator", old_username: str | None = None) -> None:
    ensure_seed_data()
    with _lock:
        users = _read_json(USERS_FILE, [])
        existing = next((u for u in users if u.get("username") == (old_username or username)), None)
        if existing is None:
            users.append({"username": username, "password": hash_password(password or ""), "role": role, "created_at": now_iso()})
        else:
            existing["username"] = username
            existing["role"] = role
            if password:
                existing["password"] = hash_password(password)
        _write_json(USERS_FILE, users)


def delete_user(username: str) -> bool:
    ensure_seed_data()
    with _lock:
        users = _read_json(USERS_FILE, [])
        if len(users) <= 1:
            return False
        filtered = [u for u in users if u.get("username") != username]
        if len(filtered) == len(users):
            return False
        _write_json(USERS_FILE, filtered)
        return True


def read_config() -> str:
    ensure_seed_data()
    return CONFIG_FILE.read_text(encoding="utf-8")


def get_disabled_built_in_crawlers() -> set[str]:
    with _lock:
        settings = _read_json(CRAWLER_SETTINGS_FILE, {})
        names = settings.get("disabled_built_ins", []) if isinstance(settings, dict) else []
        return {str(name).strip() for name in names if str(name).strip()}


def save_disabled_built_in_crawlers(names: set[str]) -> None:
    with _lock:
        _write_json(CRAWLER_SETTINGS_FILE, {"disabled_built_ins": sorted(names)})


def write_config(content: str) -> None:
    ensure_seed_data()
    temp = CONFIG_FILE.with_suffix(".yml.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(CONFIG_FILE)


def load_tasks() -> list[dict[str, Any]]:
    ensure_seed_data()
    return _read_json(TASKS_FILE, [])


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    with _lock:
        _write_json(TASKS_FILE, tasks)


def list_presets() -> list[dict[str, Any]]:
    ensure_seed_data()
    with _lock:
        return list(reversed(_read_json(PRESETS_FILE, [])))


def get_preset(preset_id: str) -> dict[str, Any] | None:
    ensure_seed_data()
    with _lock:
        return next((item for item in _read_json(PRESETS_FILE, []) if item.get("id") == preset_id), None)


def save_preset(preset: dict[str, Any]) -> None:
    ensure_seed_data()
    with _lock:
        presets = _read_json(PRESETS_FILE, [])
        presets = [item for item in presets if item.get("id") != preset["id"]]
        presets.append(preset)
        _write_json(PRESETS_FILE, presets)


def delete_preset(preset_id: str) -> bool:
    ensure_seed_data()
    if preset_id == "default":
        return False
    with _lock:
        presets = _read_json(PRESETS_FILE, [])
        filtered = [item for item in presets if item.get("id") != preset_id]
        if len(filtered) == len(presets):
            return False
        _write_json(PRESETS_FILE, filtered)
        return True


def get_qbittorrent_settings() -> dict[str, Any]:
    """Compatibility accessor for the first configured downloader."""
    downloaders = list_downloaders()
    return downloaders[0] if downloaders else {}


def _normalize_downloader(item: dict[str, Any]) -> dict[str, Any] | None:
    downloader_id = str(item.get("id") or "").strip()
    url = str(item.get("url") or "").strip()
    if not downloader_id or not url:
        return None
    return {
        "id": downloader_id,
        "name": str(item.get("name") or "qBittorrent").strip() or "qBittorrent",
        "type": "qbittorrent",
        "url": url.rstrip("/"),
        "username": str(item.get("username") or ""),
        "password": str(item.get("password") or ""),
    }


def list_downloaders() -> list[dict[str, Any]]:
    ensure_seed_data()
    with _lock:
        stored = _read_json(QBITTORRENT_FILE, {})
        if isinstance(stored, dict) and isinstance(stored.get("downloaders"), list):
            source = stored["downloaders"]
        elif isinstance(stored, dict) and stored.get("url"):
            # Upgrade the original single-connection format without losing its password.
            source = [{**stored, "id": stored.get("id") or "qbittorrent-default", "name": stored.get("name") or "qBittorrent"}]
        else:
            source = []
        return [normalized for item in source if isinstance(item, dict) and (normalized := _normalize_downloader(item))]


def save_qbittorrent_settings(settings: dict[str, Any]) -> None:
    """Compatibility writer that replaces the primary downloader."""
    current = list_downloaders()
    replacement = _normalize_downloader({**settings, "id": settings.get("id") or (current[0]["id"] if current else "qbittorrent-default"), "name": settings.get("name") or (current[0]["name"] if current else "qBittorrent")})
    if replacement:
        if current:
            current[0] = replacement
        else:
            current = [replacement]
    save_downloaders(current)


def save_downloaders(downloaders: list[dict[str, Any]]) -> None:
    ensure_seed_data()
    with _lock:
        _write_json(QBITTORRENT_FILE, {"downloaders": downloaders})


def get_qbittorrent_management() -> dict[str, Any]:
    ensure_seed_data()
    with _lock:
        settings = _read_json(QBITTORRENT_MANAGEMENT_FILE, {})
        return settings if isinstance(settings, dict) else {}


def save_qbittorrent_management(settings: dict[str, Any]) -> None:
    ensure_seed_data()
    with _lock:
        _write_json(QBITTORRENT_MANAGEMENT_FILE, settings)


def list_path_mappings() -> list[dict[str, str]]:
    ensure_seed_data()
    with _lock:
        stored = _read_json(PATH_MAPPINGS_FILE, [])
        source = stored.get("mappings", []) if isinstance(stored, dict) else stored
        mappings = []
        for item in source:
            if not isinstance(item, dict):
                continue
            source_path = str(item.get("source_path") or "").strip()
            target_path = str(item.get("target_path") or "").strip()
            if source_path and target_path:
                mappings.append({"id": str(item.get("id") or secrets.token_hex(8)), "source_path": source_path, "target_path": target_path})
        return mappings


def save_path_mappings(mappings: list[dict[str, str]]) -> None:
    ensure_seed_data()
    with _lock:
        _write_json(PATH_MAPPINGS_FILE, {"mappings": mappings})


def load_auto_scrape_history() -> dict[str, Any]:
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_HISTORY_FILE, {})
        return stored if isinstance(stored, dict) else {}


def save_auto_scrape_history(history: dict[str, Any]) -> None:
    ensure_seed_data()
    with _lock:
        recent = dict(list(history.items())[-1000:])
        _write_json(AUTO_SCRAPE_HISTORY_FILE, recent)


def _normalize_auto_scrape_schedule(item: dict[str, Any]) -> dict[str, Any] | None:
    schedule_id = str(item.get("id") or "").strip()
    cron = str(item.get("cron") or "").strip()
    input_directory = str(item.get("input_directory") or "").strip()
    preset_id = str(item.get("preset_id") or "default").strip() or "default"
    if not schedule_id or not cron or not input_directory:
        return None
    runs = []
    for run in item.get("runs") or []:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id") or "").strip()
        if not run_id:
            continue
        runs.append({
            "id": run_id,
            "started_at": str(run.get("started_at") or ""),
            "result": str(run.get("result") or ""),
            "task_ids": [str(task_id) for task_id in (run.get("task_ids") or []) if str(task_id).strip()],
        })
    return {
        "id": schedule_id,
        "name": str(item.get("name") or "自动刮削规则").strip() or "自动刮削规则",
        "enabled": bool(item.get("enabled", True)),
        "cron": cron,
        "input_directory": input_directory,
        "preset_id": preset_id,
        "created_at": str(item.get("created_at") or now_iso()),
        "updated_at": str(item.get("updated_at") or now_iso()),
        "last_run_key": str(item.get("last_run_key") or ""),
        "last_run_at": str(item.get("last_run_at") or ""),
        "last_result": str(item.get("last_result") or ""),
        "runs": runs,
    }


def list_auto_scrape_schedules() -> list[dict[str, Any]]:
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_SCHEDULES_FILE, [])
        source = stored.get("schedules", []) if isinstance(stored, dict) else stored
        return [normalized for item in source if isinstance(item, dict) and (normalized := _normalize_auto_scrape_schedule(item))]


def save_auto_scrape_schedules(schedules: list[dict[str, Any]]) -> None:
    ensure_seed_data()
    with _lock:
        _write_json(AUTO_SCRAPE_SCHEDULES_FILE, {"schedules": schedules})


def claim_auto_scrape_schedule_run(schedule_id: str, minute_key: str) -> dict[str, Any] | None:
    """Atomically reserve a due minute so one schedule cannot run twice."""
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_SCHEDULES_FILE, [])
        source = stored.get("schedules", []) if isinstance(stored, dict) else stored
        changed = False
        claimed: dict[str, Any] | None = None
        for item in source:
            if not isinstance(item, dict) or str(item.get("id") or "") != schedule_id:
                continue
            if str(item.get("last_run_key") or "") == minute_key:
                break
            item["last_run_key"] = minute_key
            item["last_run_at"] = now_iso()
            item["last_result"] = "正在创建刮削任务"
            runs = item.get("runs") if isinstance(item.get("runs"), list) else []
            runs.append({"id": minute_key, "started_at": item["last_run_at"], "result": item["last_result"], "task_ids": []})
            item["runs"] = runs
            item["updated_at"] = now_iso()
            claimed = _normalize_auto_scrape_schedule(item)
            changed = True
            break
        if changed:
            _write_json(AUTO_SCRAPE_SCHEDULES_FILE, {"schedules": source})
        return claimed


def skip_auto_scrape_schedule_run(schedule_id: str, minute_key: str, result: str) -> dict[str, Any] | None:
    """Record a skipped run and reserve its minute so the scheduler will not retry it."""
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_SCHEDULES_FILE, [])
        source = stored.get("schedules", []) if isinstance(stored, dict) else stored
        for item in source:
            if not isinstance(item, dict) or str(item.get("id") or "") != schedule_id:
                continue
            if str(item.get("last_run_key") or "") == minute_key:
                return None
            timestamp = now_iso()
            item["last_run_key"] = minute_key
            item["last_run_at"] = timestamp
            item["last_result"] = result[:500]
            runs = item.get("runs") if isinstance(item.get("runs"), list) else []
            runs.append({"id": minute_key, "started_at": timestamp, "result": item["last_result"], "task_ids": []})
            item["runs"] = runs
            item["updated_at"] = timestamp
            _write_json(AUTO_SCRAPE_SCHEDULES_FILE, {"schedules": source})
            return _normalize_auto_scrape_schedule(item)
    return None


def record_auto_scrape_schedule_result(schedule_id: str, result: str, task_ids: list[str] | None = None) -> None:
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_SCHEDULES_FILE, [])
        source = stored.get("schedules", []) if isinstance(stored, dict) else stored
        for item in source:
            if isinstance(item, dict) and str(item.get("id") or "") == schedule_id:
                item["last_result"] = result[:500]
                item["updated_at"] = now_iso()
                runs = item.get("runs") if isinstance(item.get("runs"), list) else []
                latest = next((run for run in reversed(runs) if isinstance(run, dict) and str(run.get("id") or "") == str(item.get("last_run_key") or "")), None)
                if latest is not None:
                    latest["result"] = item["last_result"]
                    if task_ids is not None:
                        latest["task_ids"] = [str(task_id) for task_id in task_ids]
                item["runs"] = runs
                _write_json(AUTO_SCRAPE_SCHEDULES_FILE, {"schedules": source})
                return


def delete_auto_scrape_schedule_run(schedule_id: str, run_id: str) -> bool:
    """Remove only a saved run record; its tasks and media remain untouched."""
    ensure_seed_data()
    with _lock:
        stored = _read_json(AUTO_SCRAPE_SCHEDULES_FILE, [])
        source = stored.get("schedules", []) if isinstance(stored, dict) else stored
        for item in source:
            if not isinstance(item, dict) or str(item.get("id") or "") != schedule_id:
                continue
            runs = item.get("runs") if isinstance(item.get("runs"), list) else []
            remaining = [run for run in runs if not (isinstance(run, dict) and str(run.get("id") or "") == run_id)]
            if len(remaining) == len(runs):
                return False
            item["runs"] = remaining
            item["updated_at"] = now_iso()
            _write_json(AUTO_SCRAPE_SCHEDULES_FILE, {"schedules": source})
            return True
    return False


def _normalize_media_server(item: dict[str, Any]) -> dict[str, Any] | None:
    server_id = str(item.get("id") or "").strip()
    name = str(item.get("name") or "").strip()
    url = str(item.get("url") or "").strip().rstrip("/")
    server_type = str(item.get("type") or "emby").strip().lower()
    if not server_id or not name or not url or server_type not in {"emby", "jellyfin"}:
        return None
    return {
        "id": server_id,
        "name": name,
        "type": server_type,
        "url": url,
        "external_url": str(item.get("external_url") or "").strip().rstrip("/"),
        "api_key": str(item.get("api_key") or "").strip(),
        "auto_scan": bool(item.get("auto_scan")),
        "auto_scan_delay": max(0, min(86400, int(item.get("auto_scan_delay", 0) or 0))),
        "libraries": [str(value) for value in (item.get("libraries") or []) if str(value).strip()],
    }


def list_media_servers() -> list[dict[str, Any]]:
    ensure_seed_data()
    with _lock:
        stored = _read_json(MEDIA_SERVERS_FILE, [])
        source = stored.get("servers", []) if isinstance(stored, dict) else stored
        return [normalized for item in source if isinstance(item, dict) and (normalized := _normalize_media_server(item))]


def save_media_servers(servers: list[dict[str, Any]]) -> None:
    ensure_seed_data()
    with _lock:
        _write_json(MEDIA_SERVERS_FILE, {"servers": servers})


def get_cookiecloud_settings(include_password: bool = False) -> dict[str, Any]:
    ensure_seed_data()
    with _lock:
        saved = _read_json(COOKIECLOUD_FILE, {})
        saved = saved if isinstance(saved, dict) else {}
        password = str(saved.get("password") or "")
        result = {
            "enabled": bool(saved.get("enabled")),
            "server_url": str(saved.get("server_url") or ""),
            "uuid": str(saved.get("uuid") or ""),
            "crypto_type": str(saved.get("crypto_type") or "auto"),
            "has_password": bool(password),
            "updated_at": str(saved.get("updated_at") or ""),
        }
        if include_password:
            result["password"] = password
        return result


def save_cookiecloud_settings(settings: dict[str, Any]) -> dict[str, Any]:
    ensure_seed_data()
    with _lock:
        existing = _read_json(COOKIECLOUD_FILE, {})
        existing = existing if isinstance(existing, dict) else {}
        password = str(settings.get("password") or existing.get("password") or "")
        if settings.get("clear_password"):
            password = ""
        saved = {
            "enabled": bool(settings.get("enabled")),
            "server_url": str(settings.get("server_url") or "").strip().rstrip("/"),
            "uuid": str(settings.get("uuid") or "").strip(),
            "crypto_type": str(settings.get("crypto_type") or existing.get("crypto_type") or "auto"),
            "password": password,
            "updated_at": now_iso(),
        }
        _write_json(COOKIECLOUD_FILE, saved)
    return get_cookiecloud_settings()
