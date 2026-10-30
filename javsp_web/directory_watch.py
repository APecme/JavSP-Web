"""目录监控（directory watch）: bounded polling of a mounted folder.

Design notes
------------
* Everything lives in this module: rule persistence, the observation/commit
  ledger and the scheduler thread. ``server.py`` only includes the router and
  starts/stops the scheduler.
* Polling (``os.scandir``) is the only portable option across Docker, Windows
  and NAS mounts; there is no inotify dependency.
* A file enters the existing ``create_tasks`` queue only after its signature
  (relative path + size + mtime_ns) has been unchanged for ``stable_seconds``.
  The signature of every submitted (or deliberately skipped) file is persisted,
  so a restart or a second scan never re-queues it.
* Nothing here holds the task worker lock or the event loop: scans run in a
  daemon scheduler thread (or a request thread-pool worker for the manual
  "scan now" action) and call ``create_tasks`` which owns the queue locks.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .timeutils import now_iso

try:  # cron drives the schedule trigger; the package ships with the web app
    from croniter import croniter
except ImportError:  # pragma: no cover - croniter is a hard dependency in practice
    croniter = None

log = logging.getLogger("javsp.web.directory_watch")

DEFAULT_POLL_SECONDS = 30
DEFAULT_STABLE_SECONDS = 60
MIN_POLL_SECONDS = 5
MAX_POLL_SECONDS = 3600
MIN_STABLE_SECONDS = 0
MAX_STABLE_SECONDS = 86400
DEFAULT_MAX_TASKS_PER_SCAN = 20
MIN_TASKS_PER_SCAN = 1
MAX_TASKS_PER_SCAN = 100
MAX_RULES = 50
# The ledger stores one entry per handled file; a long-lived rule must not grow
# the state file without bound.
MAX_COMMITTED_ENTRIES = 20000
MAX_EXCLUDE_PATTERNS = 50
MAX_EXCLUDE_LENGTH = 200
STATE_VERSION = 1
MIGRATION_VERSION = 1
TRIGGERS = ("watch", "schedule")

VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".f4v", ".flv", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4",
    ".mpeg", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv", ".strm", ".mpg",
}
# Download clients keep the real name and append their own suffix while writing.
TEMP_SUFFIXES = (
    ".!qb", ".part", ".partial", ".tmp", ".crdownload", ".download", ".downloading",
    ".aria2", ".!ut", ".bc!", ".td", ".filepart", ".opdownload", ".incomplete",
)

_lock = threading.RLock()
_rule_locks: dict[str, threading.Lock] = {}


class RuleError(ValueError):
    """Validation or lookup failure that maps to HTTP 400/404."""


class PresetError(RuleError):
    """The rule points at a preset that no longer exists."""


# --------------------------------------------------------------------- store
def _data_dir() -> Path:
    from . import storage

    return Path(storage.DATA_DIR)


def _rules_file() -> Path:
    return _data_dir() / "directory-watch-rules.json"


def _state_file() -> Path:
    return _data_dir() / "directory-watch-state.json"


def _atomic_write(path: Path, payload) -> None:
    """Write JSON so a crash leaves either the old or the new file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory)
    except OSError:
        pass
    finally:
        os.close(directory)


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _normalize_stored_rule(item: dict) -> dict | None:
    rule_id = str(item.get("id") or "")
    path = str(item.get("path") or "")
    if not rule_id or not path:
        return None
    try:
        trigger = str(item.get("trigger") or "watch")
        if trigger not in TRIGGERS:
            trigger = "watch"
        return {
            "id": rule_id,
            "name": str(item.get("name") or Path(path).name or "目录监控"),
            "enabled": bool(item.get("enabled", True)),
            "trigger": trigger,
            "path": path,
            "preset_id": str(item.get("preset_id") or "default"),
            "recursive": bool(item.get("recursive", True)),
            "exclude": [str(pattern) for pattern in (item.get("exclude") or []) if isinstance(pattern, str)],
            "include_existing": bool(item.get("include_existing", False)),
            "poll_seconds": _clamp(int(item.get("poll_seconds", DEFAULT_POLL_SECONDS)), MIN_POLL_SECONDS, MAX_POLL_SECONDS),
            "stable_seconds": _clamp(int(item.get("stable_seconds", DEFAULT_STABLE_SECONDS)), MIN_STABLE_SECONDS, MAX_STABLE_SECONDS),
            "max_tasks_per_scan": _clamp(int(item.get("max_tasks_per_scan", DEFAULT_MAX_TASKS_PER_SCAN)), MIN_TASKS_PER_SCAN, MAX_TASKS_PER_SCAN),
            "cron": _normalize_cron(str(item.get("cron") or "")) if trigger == "schedule" else "",
            "migrated": bool(item.get("migrated", False)),
            "legacy_schedule": dict(item.get("legacy_schedule") or {}),
            "timezone": str(item.get("timezone") or ""),
            "generation": int(item.get("generation", 1)),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        }
    except (TypeError, ValueError):
        return None


def _normalize_cron(raw: str) -> str:
    """A stored cron must stay valid; an invalid one is dropped, not fatal."""
    cron = (raw or "").strip()
    if not cron:
        return ""
    try:
        if croniter is not None and croniter.is_valid(cron):
            return cron
    except (TypeError, ValueError, KeyError):
        pass
    return ""


def read_rules() -> list[dict]:
    stored = _read_json(_rules_file(), {"rules": []})
    source = stored.get("rules") if isinstance(stored, dict) else stored
    if not isinstance(source, list):
        return []
    rules = []
    for item in source:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_stored_rule(item)
        if normalized:
            rules.append(normalized)
    return rules


def write_rules(rules: list[dict]) -> None:
    stored = _read_json(_rules_file(), {})
    metadata = {key: value for key, value in stored.items() if key != "rules"} if isinstance(stored, dict) else {}
    _atomic_write(_rules_file(), {**metadata, "version": STATE_VERSION, "rules": rules})


def get_rule(rule_id: str) -> dict | None:
    return next((rule for rule in read_rules() if rule["id"] == rule_id), None)


def read_state() -> dict:
    stored = _read_json(_state_file(), {"version": STATE_VERSION, "rules": {}})
    if not isinstance(stored, dict) or not isinstance(stored.get("rules"), dict):
        stored = {"version": STATE_VERSION, "rules": {}}
    stored.setdefault("version", STATE_VERSION)
    return stored


def write_state(state: dict) -> None:
    _atomic_write(_state_file(), state)


def _rule_state_entry(state: dict, rule_id: str) -> dict:
    entry = state["rules"].setdefault(rule_id, {})
    entry.setdefault("committed", {})
    entry.setdefault("observed", {})
    entry.setdefault("initial_scan_done", False)
    entry.setdefault("submitted_total", 0)
    entry.setdefault("skipped_total", 0)
    entry.setdefault("last_state", "")
    entry.setdefault("last_message", "")
    entry.setdefault("last_error", "")
    entry.setdefault("last_scan_ts", 0.0)
    entry.setdefault("last_scan_at", "")
    entry.setdefault("last_submitted_at", "")
    entry.setdefault("last_submitted_count", 0)
    entry.setdefault("last_skipped_reason", "")
    return entry


# ---------------------------------------------------------------- validation
def _normalize_exclude(raw) -> list[str]:
    patterns = raw if isinstance(raw, list) else []
    if len(patterns) > MAX_EXCLUDE_PATTERNS:
        raise RuleError(f"排除规则最多 {MAX_EXCLUDE_PATTERNS} 条")
    cleaned: list[str] = []
    for value in patterns:
        pattern = str(value or "").strip()
        if not pattern:
            continue
        if len(pattern) > MAX_EXCLUDE_LENGTH:
            raise RuleError("排除规则过长")
        if "\0" in pattern:
            raise RuleError("排除规则包含无效字符")
        normalized = pattern.replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("~") or ":" in normalized.split("/")[0]:
            raise RuleError("排除规则请填写相对于监控目录的路径或文件名，不要使用绝对路径")
        if ".." in normalized.split("/"):
            raise RuleError("排除规则不能包含 \"..\"")
        cleaned.append(normalized.strip("/"))
    return list(dict.fromkeys(cleaned))


def _normalize_int(value, default: int, low: int, high: int, label: str) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RuleError(f"{label}必须是整数") from exc
    if number < low or number > high:
        raise RuleError(f"{label}需在 {low} 到 {high} 之间")
    return number


def _normalize_optional_int(value, default: int, low: int, high: int, label: str) -> int:
    """Treat an unset or zero value as "not configured" and fall back to the default.

    Watch（监控新增）只需要目录 + 预设；时间/间隔字段可以整体省略。对最小值
    大于 0 的字段，0 也不可能是有意填写的合法值，因此同样视为未填写。
    明确填写的越界值（例如 3 秒扫描间隔）仍然报错，不会被静默纠正。
    """
    if value in (None, "", 0) and low > 0:
        return default
    return _normalize_int(value, default, low, high, label)


def _resolved(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(os.path.abspath(path))


def _is_inside(path: str, parent: str) -> bool:
    if not path or not parent:
        return False
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


def _check_overlap(rule: dict, others: list[dict]) -> None:
    if rule.get("trigger") == "schedule":
        return  # overlapping cron full scans are guarded at submission time
    current = _resolved(rule["path"])
    for other in others:
        if other["id"] == rule["id"] or not other.get("enabled") or other.get("trigger") == "schedule":
            continue
        candidate = _resolved(other["path"])
        if current == candidate or _is_inside(current, candidate) or _is_inside(candidate, current):
            raise RuleError(f"监控目录与规则「{other.get('name') or other['id']}」重叠，同一个文件只会被监控一次")


def normalize_payload(payload: dict, *, rule_id: str | None = None, others: list[dict] | None = None) -> dict:
    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        raise RuleError("请填写要监控的目录")
    if "\0" in raw_path:
        raise RuleError("目录路径包含无效字符")
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        raise RuleError("请填写绝对路径，例如 /media/movies 或 D:\\Videos")
    path = os.path.abspath(expanded)
    if not os.path.isdir(path):
        raise RuleError("监控目录不存在或不是文件夹，请确认路径已挂载到容器内")
    if _is_inside(_resolved(path), _resolved(str(_data_dir()))):
        raise RuleError("监控目录不能是应用数据目录")
    preset_id = str(payload.get("preset_id") or "default").strip() or "default"
    from . import storage

    if not storage.get_preset(preset_id):
        raise RuleError("指定的刮削预设不存在")
    trigger = str(payload.get("trigger") or "watch").strip().lower()
    if trigger not in TRIGGERS:
        raise RuleError("触发方式只能是 watch（监控新增）或 schedule（定时全量）")
    cron = ""
    if trigger == "schedule":
        cron = str(payload.get("cron") or "").strip()
        if croniter is None or len(cron.split()) != 5 or not croniter.is_valid(cron):
            raise RuleError("Cron 表达式无效，请使用标准五段格式，例如：0 2 * * *")
    # watch（监控新增）不要求调度时间；cron/interval 字段缺省时用默认值，
    # 只有 schedule（定时全量）必须提供 cron。字段在返回结构里始终保留。
    rule = {
        "id": rule_id or uuid.uuid4().hex[:12],
        "name": str(payload.get("name") or "").strip()[:80] or Path(path).name or "目录监控",
        "enabled": bool(payload.get("enabled", True)),
        "trigger": trigger,
        "path": path,
        "preset_id": preset_id,
        "recursive": bool(payload.get("recursive", True)),
        "exclude": _normalize_exclude(payload.get("exclude")),
        "include_existing": bool(payload.get("include_existing", False)),
        "poll_seconds": _normalize_optional_int(
            payload.get("poll_seconds"), DEFAULT_POLL_SECONDS, MIN_POLL_SECONDS, MAX_POLL_SECONDS, "扫描间隔"),
        "stable_seconds": _normalize_int(
            payload.get("stable_seconds"), DEFAULT_STABLE_SECONDS, MIN_STABLE_SECONDS, MAX_STABLE_SECONDS, "稳定等待时间"),
        "max_tasks_per_scan": _normalize_optional_int(
            payload.get("max_tasks_per_scan"), DEFAULT_MAX_TASKS_PER_SCAN, MIN_TASKS_PER_SCAN, MAX_TASKS_PER_SCAN,
            "单次最多提交任务数"),
        "cron": cron,
    }
    if others is not None:
        _check_overlap(rule, others)
    return rule


# ---------------------------------------------------------------- rule CRUD
def create_rule(payload: dict) -> dict:
    with _lock:
        rules = read_rules()
        if len(rules) >= MAX_RULES:
            raise RuleError(f"最多只能添加 {MAX_RULES} 条目录监控规则")
        rule = normalize_payload(payload, others=rules)
        stamp = now_iso()
        rule.update(generation=1, created_at=stamp, updated_at=stamp)
        rules.append(rule)
        write_rules(rules)
    _baseline_rule(rule)
    _wake_scheduler()
    return rule


def update_rule(rule_id: str, payload: dict) -> dict:
    with _lock:
        rules = read_rules()
        index = next((position for position, rule in enumerate(rules) if rule["id"] == rule_id), None)
        if index is None:
            raise RuleError("目录监控规则不存在")
        existing = rules[index]
        merged = {
            "name": payload.get("name", existing["name"]),
            "enabled": payload.get("enabled", existing["enabled"]),
            "trigger": payload.get("trigger", existing.get("trigger") or "watch"),
            "path": payload.get("path", existing["path"]),
            "preset_id": payload.get("preset_id", existing["preset_id"]),
            "recursive": payload.get("recursive", existing["recursive"]),
            "exclude": payload.get("exclude", existing["exclude"]),
            "include_existing": payload.get("include_existing", existing["include_existing"]),
            "poll_seconds": payload.get("poll_seconds", existing["poll_seconds"]),
            "stable_seconds": payload.get("stable_seconds", existing["stable_seconds"]),
            "max_tasks_per_scan": payload.get("max_tasks_per_scan", existing["max_tasks_per_scan"]),
            "cron": payload.get("cron", existing.get("cron") or ""),
        }
        rule = normalize_payload(merged, rule_id=rule_id, others=rules)
        rule.update(
            migrated=existing.get("migrated", False),
            legacy_schedule=existing.get("legacy_schedule") or {},
            timezone=existing.get("timezone") or "",
            generation=existing.get("generation", 1) + 1,
            created_at=existing.get("created_at", ""),
            updated_at=now_iso(),
        )
        rules[index] = rule
        write_rules(rules)
        state = read_state()
        # A new target folder, preset or exclusion list invalidates the old
        # ledger; the next scan rebuilds a baseline instead of re-queueing files.
        previous = state["rules"].get(rule_id) or {}
        # Editing cannot erase history, minute claims or active reservations.
        state["rules"][rule_id] = {key: value for key, value in previous.items()
            if key.startswith("schedule_") or key in {"last_schedule_run_key", "inflight", "deleted_run_ids"}}
        write_state(state)
    _baseline_rule(rule)
    _wake_scheduler()
    return rule


def delete_rule(rule_id: str) -> bool:
    with _lock:
        rules = read_rules()
        remaining = [rule for rule in rules if rule["id"] != rule_id]
        if len(remaining) == len(rules):
            return False
        write_rules(remaining)
        state = read_state()
        state["rules"].pop(rule_id, None)
        write_state(state)
    return True


def set_rule_enabled(rule_id: str, enabled: bool) -> dict:
    with _lock:
        rules = read_rules()
        rule = next((item for item in rules if item["id"] == rule_id), None)
        if rule is None:
            raise RuleError("目录监控规则不存在")
        rule["enabled"] = bool(enabled)
        rule["updated_at"] = now_iso()
        write_rules(rules)
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        if not enabled:
            entry["last_state"] = "disabled"
            entry["last_message"] = "规则已暂停，不再扫描新文件"
            # Pausing keeps the ledger: resuming must not re-queue known files.
            write_state(state)
    _wake_scheduler()
    return rule


def reset_rule_state(rule_id: str) -> dict:
    with _lock:
        rule = get_rule(rule_id)
        if rule is None:
            raise RuleError("目录监控规则不存在")
        state = read_state()
        state["rules"].pop(rule_id, None)
        write_state(state)
    _baseline_rule(rule)
    return rule


# ------------------------------------------------------------- legacy migration
def migrate_legacy_schedules() -> dict:
    """Atomically import all legacy schedules, metadata and history snapshots.

    Rules, stable ID mapping and the migration version share one replace, so an
    interruption cannot leave a version stamp without its rules/history. A
    mapping tombstone survives rule deletion and prevents resurrection on restart.
    Offline folders and missing presets are preserved, not silently discarded.
    """
    from . import storage
    from .timeutils import timezone_name

    report = {"checked": 0, "imported": 0, "skipped_existing": 0, "skipped_invalid": 0}
    with _lock:
        schedules = storage.list_auto_scrape_schedules()
        stored = _read_json(_rules_file(), {})
        metadata = dict(stored) if isinstance(stored, dict) else {}
        mapping = dict(metadata.get("legacy_schedule_ids") or {})
        rules = read_rules()
        report["checked"] = len(schedules)
        for schedule in schedules:
            legacy_id = str(schedule["id"])
            if legacy_id in mapping:
                report["skipped_existing"] += 1
                continue
            existing = next((rule for rule in rules if rule["id"] == legacy_id), None)
            if existing and existing.get("trigger") == "schedule":
                # Recover imports written by the earlier partial implementation.
                existing.setdefault("legacy_schedule", {})
                if not existing["legacy_schedule"]:
                    existing["legacy_schedule"] = schedule
                existing["migrated"] = True
                mapping[legacy_id] = existing["id"]
                report["skipped_existing"] += 1
                continue
            target_id = legacy_id
            if existing:
                target_id = "schedule-" + hashlib.sha256(legacy_id.encode()).hexdigest()[:20]
                while any(rule["id"] == target_id for rule in rules):
                    target_id += "-legacy"
            rule = _normalize_stored_rule({
                "id": target_id, "name": schedule.get("name"),
                "enabled": schedule.get("enabled", True), "trigger": "schedule",
                "path": schedule["input_directory"], "preset_id": schedule.get("preset_id"),
                "cron": schedule.get("cron"), "migrated": True,
                "timezone": schedule.get("timezone") or timezone_name(),
                "legacy_schedule": schedule,
                "created_at": schedule.get("created_at"), "updated_at": schedule.get("updated_at"),
            })
            if rule is None:
                report["skipped_invalid"] += 1
                continue
            rules.append(rule)
            mapping[legacy_id] = target_id
            report["imported"] += 1
        _atomic_write(_rules_file(), {**metadata, "version": STATE_VERSION,
            "migration_version": MIGRATION_VERSION, "legacy_schedule_ids": mapping, "rules": rules})
    return report


def schedule_history(rule_id: str) -> dict:
    """One legacy-shaped history view shared by the unified and old APIs."""
    with _lock:
        rule = get_rule(rule_id)
        if rule is None:
            raise RuleError("规则不存在")
        legacy = rule.get("legacy_schedule") or {}
        entry = read_state()["rules"].get(rule_id) or {}
        deleted = set(entry.get("deleted_run_ids") or [])
        runs = {str(run["id"]): dict(run) for run in legacy.get("runs") or [] if run.get("id")}
        for run in entry.get("schedule_runs") or []:
            key = str(run.get("id") or run.get("run_key") or "")
            if key:
                runs[key] = {**run, "id": key, "started_at": run.get("started_at") or run.get("at") or ""}
        return {"runs": [run for key, run in runs.items() if key not in deleted],
            "last_run_key": entry.get("last_schedule_run_key", legacy.get("last_run_key", "")),
            "last_run_at": entry.get("last_scan_at") or legacy.get("last_run_at") or "",
            "last_result": entry.get("last_message") or legacy.get("last_result") or "尚未执行"}


def delete_schedule_run(rule_id: str, run_id: str) -> bool:
    with _lock:
        if not get_rule(rule_id) or not any(run["id"] == run_id for run in schedule_history(rule_id)["runs"]):
            return False
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        entry["deleted_run_ids"] = list(dict.fromkeys([*(entry.get("deleted_run_ids") or []), run_id]))
        write_state(state)
        return True


# ------------------------------------------------------------------ reporting
def _rule_status(rule: dict, entry: dict) -> dict:
    state = "ok"
    if not rule.get("enabled"):
        state = "disabled"
    elif entry.get("last_state") in {"offline", "error"}:
        state = entry["last_state"]
    elif rule.get("trigger") != "schedule" and not entry.get("initial_scan_done"):
        state = "initializing"
    message = entry.get("last_message") or ""
    skipped = int(entry.get("skipped_total") or 0)
    if skipped and entry.get("last_skipped_reason"):
        # A skip detail must stay visible: the reason is why nothing happened.
        message = _join(message, [f"已有 {skipped} 个文件未通过预设检查：{entry['last_skipped_reason']}"])
    return {
        "state": state,
        "message": message,
        "pending": len(entry.get("observed") or {}),
        "committed": len(entry.get("committed") or {}),
        "submitted_total": int(entry.get("submitted_total") or 0),
        "skipped_total": skipped,
        "last_scan_at": entry.get("last_scan_at") or "",
        "last_submitted_at": entry.get("last_submitted_at") or "",
        "last_submitted_count": int(entry.get("last_submitted_count") or 0),
        "last_error": entry.get("last_error") or "",
    }


def list_rule_reports() -> list[dict]:
    state = read_state()
    reports = []
    for rule in read_rules():
        entry = state["rules"].get(rule["id"]) or {}
        reports.append({**rule, "status": _rule_status(rule, entry),
                        **({"history": schedule_history(rule["id"]), "next_run_at": next_schedule_run(rule)}
                           if rule.get("trigger") == "schedule" else {})})
    return reports


def rule_report(rule_id: str) -> dict | None:
    state = read_state()
    rule = get_rule(rule_id)
    if rule is None:
        return None
    return {**rule, "status": _rule_status(rule, state["rules"].get(rule_id) or {}),
            **({"history": schedule_history(rule_id), "next_run_at": next_schedule_run(rule)}
               if rule.get("trigger") == "schedule" else {})}


def limits() -> dict:
    return {
        "poll_seconds": {"default": DEFAULT_POLL_SECONDS, "min": MIN_POLL_SECONDS, "max": MAX_POLL_SECONDS},
        "stable_seconds": {"default": DEFAULT_STABLE_SECONDS, "min": MIN_STABLE_SECONDS, "max": MAX_STABLE_SECONDS},
        "max_tasks_per_scan": {
            "default": DEFAULT_MAX_TASKS_PER_SCAN, "min": MIN_TASKS_PER_SCAN, "max": MAX_TASKS_PER_SCAN,
        },
        "max_rules": MAX_RULES,
    }


# ------------------------------------------------------------------- scanner
@dataclass
class _PresetContext:
    config_data: dict
    extensions: set[str]
    folder_patterns: list[re.Pattern]
    output_names: set[str]


def _preset_context(rule: dict) -> _PresetContext:
    """Video extensions, ignored-folder regexes and the output folder name."""
    from . import storage

    if not storage.get_preset(rule["preset_id"]):
        raise PresetError("指定的刮削预设不存在或已被删除，请重新选择预设")
    from . import tasks

    try:
        config_data, _ = tasks._preset_config_data(rule["preset_id"])
    except ValueError as exc:
        raise PresetError(f"刮削预设不可用：{exc}") from exc
    scanner = config_data.get("scanner") or {}
    extensions = {str(item).lower() for item in (scanner.get("filename_extensions") or []) if str(item).startswith(".")}
    patterns: list[re.Pattern] = []
    for raw in scanner.get("ignored_folder_name_pattern") or []:
        try:
            patterns.append(re.compile(str(raw)))
        except re.error:
            continue
    output_names: set[str] = set()
    pattern = str(((config_data.get("summarizer") or {}).get("path") or {}).get("output_folder_pattern") or "")
    literal = pattern.split("{", 1)[0].strip("/")
    if literal:
        output_names.add(literal.split("/")[0].casefold())
    return _PresetContext(config_data, extensions or set(VIDEO_EXTENSIONS), patterns, output_names)


def _is_temp_name(name: str) -> bool:
    lowered = name.casefold()
    if lowered.startswith("."):
        return True
    if any(lowered.endswith(suffix) for suffix in TEMP_SUFFIXES):
        return True
    return ".tmp." in lowered


def _matches_exclude(rule: dict, name: str, rel: str) -> bool:
    for pattern in rule.get("exclude") or []:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern):
            return True
    return False


def _walk(rule: dict, context: _PresetContext):
    """Return ({rel: (path, size, mtime_ns)}, [problems])."""
    root = Path(rule["path"])
    files: dict[str, tuple[Path, int, int]] = {}
    problems: list[str] = []
    data_root = _resolved(str(_data_dir()))
    stack: list[tuple[Path, str]] = [(root, "")]
    visited: set[tuple[int, int]] = set()
    while stack:
        directory, prefix = stack.pop()
        try:
            stats = os.stat(directory)
        except OSError as exc:
            problems.append(f"无法访问目录 {prefix or '.'}：{exc.strerror or exc}")
            continue
        marker = (getattr(stats, "st_dev", 0), getattr(stats, "st_ino", 0))
        if marker in visited:
            continue  # a bind mount or symlink that loops back into itself
        visited.add(marker)
        try:
            entries = list(os.scandir(directory))
        except PermissionError:
            problems.append(f"无法读取目录 {prefix or '.'}：权限不足")
            continue
        except OSError as exc:
            problems.append(f"无法读取目录 {prefix or '.'}：{exc.strerror or exc}")
            continue
        for entry in entries:
            name = entry.name
            rel = f"{prefix}/{name}" if prefix else name
            try:
                is_symlink = entry.is_symlink()
                if is_symlink and entry.is_dir():
                    continue  # never follow directory symlinks: loops stay impossible
                if entry.is_dir(follow_symlinks=False):
                    if not rule.get("recursive", True):
                        continue
                    if _matches_exclude(rule, name, rel):
                        continue
                    if any(pattern.search(name) for pattern in context.folder_patterns):
                        continue
                    if name.casefold() in context.output_names:
                        continue
                    if _is_inside(_resolved(entry.path), data_root):
                        continue
                    stack.append((Path(entry.path), rel))
                    continue
                if _is_temp_name(name):
                    continue
                if Path(name).suffix.lower() not in context.extensions:
                    continue
                if _matches_exclude(rule, name, rel):
                    continue
                stats = entry.stat()  # follows a symlinked file so the target signature counts
                if not os.path.isfile(entry.path):
                    continue
                files[rel] = (Path(entry.path), int(stats.st_size), int(stats.st_mtime_ns))
            except FileNotFoundError:
                continue  # a dangling symlink or a file that moved mid-scan
            except OSError as exc:
                problems.append(f"无法读取 {rel}：{exc.strerror or exc}")
    return files, problems


def _copy_checks(files: dict) -> dict:
    """Read copy candidates outside the ledger lock; never persist their links."""
    vendor_dir = str(_vendor_dir())
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    from javsp.download_copy import copy_original, inspect_download_copy

    checks = {}
    for rel, (path, _, _) in files.items():
        if path.suffix.lower() != ".strm" or copy_original(path) is None:
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = None
        checks[rel] = {"content_hash": digest, "verdict": inspect_download_copy(path)}
    return checks


def _duplicate_record(size: int, mtime: int, check: dict, previous: dict | None = None) -> dict | None:
    """A verified unchanged copy stays skipped even after its original moves."""
    digest = check.get("content_hash")
    verdict = check.get("verdict")
    if (previous and previous.get("status") == "duplicate" and digest
            and previous.get("content_hash") == digest
            and (verdict is None or verdict.get("duplicate"))):
        return {**previous, "size": size, "mtime_ns": mtime}
    if digest and verdict and verdict.get("duplicate"):
        return {
            **_file_entry(size, mtime, status="duplicate", reason=verdict["reason"]),
            "original": verdict["original"], "content_hash": digest,
        }
    return None


def _copy_skip_messages(files: dict, copy_checks: dict, committed: dict) -> list[str]:
    """User-visible prompts for copies verified in this pass, never repeated.

    Only the file names are rendered; the ledger keeps the relationship and the
    reason, and links never reach the message.
    """
    messages = []
    for rel in sorted(files):
        check = copy_checks.get(rel)
        if not check:
            continue
        verdict = check.get("verdict")
        if not verdict or not verdict.get("duplicate"):
            continue
        previous = committed.get(rel)
        if (previous and previous.get("status") == "duplicate"
                and previous.get("content_hash") == check.get("content_hash")):
            continue  # already reported by an earlier poll
        messages.append(f"跳过重复副本：{Path(rel).name} → {Path(verdict['original']).name}")
    return messages


def _duplicate_summary(messages: list[str]) -> str:
    if len(messages) <= 3:
        return "；".join(messages)
    return "；".join(messages[:3]) + f"；另有 {len(messages) - 3} 个重复副本已跳过"


def _baseline_files(files: dict, committed: dict, copy_checks: dict) -> dict:
    baseline = {}
    for rel, (_, size, mtime) in files.items():
        if rel in committed:
            continue
        check = copy_checks.get(rel)
        record = _duplicate_record(size, mtime, check) if check else None
        if record is None:
            record = _file_entry(size, mtime, status="baseline")
            if check:
                record["content_hash"] = check.get("content_hash")
        baseline[rel] = record
    return baseline


def _identity_groups(paths: dict[str, Path], config_data: dict) -> dict[tuple, list[str]]:
    """Group paths the same way ``create_tasks`` groups multipart parts."""
    vendor_dir = str(_vendor_dir())
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    try:
        from javsp.config import Cfg
        from javsp.multipart import media_identity

        scanner = Cfg.model_validate(config_data).scanner
    except Exception:  # noqa: BLE001 - grouping is a nicety, not a precondition
        log.debug("multipart grouping unavailable", exc_info=True)
        return {("path", rel): [rel] for rel in paths}
    groups: dict[tuple, list[str]] = {}
    for rel, path in paths.items():
        try:
            kind, avid = media_identity(str(path), scanner)
            key = (str(path.parent), kind, avid) if avid else ("path", str(path))
        except Exception:  # noqa: BLE001
            key = ("path", str(path))
        groups.setdefault(key, []).append(rel)
    return groups


def _vendor_dir() -> Path:
    from . import storage

    return Path(storage.VENDOR_DIR)


def _task_active(task_id: str) -> bool:
    """Is the task created for this file still waiting or running?

    Reads the raw store record: ``tasks.get_task`` decorates the task and may
    stat the media mount, which a polling watcher must never do.
    """
    if not task_id:
        return False
    try:
        from .task_store import load as load_task_records

        records = load_task_records([task_id])
    except Exception:  # noqa: BLE001 - a broken store must not wedge the watcher
        return True
    if not records:
        return False
    return str(records[0].get("status") or "") in {"queued", "running"}


def _file_entry(size: int, mtime_ns: int, *, status: str, task_id: str = "", reason: str = "") -> dict:
    return {
        "size": int(size), "mtime_ns": int(mtime_ns), "status": status,
        "task_id": task_id, "reason": reason, "at": now_iso(),
    }


def _display_time(stamp: float) -> str:
    if not stamp:
        return ""
    try:
        return datetime.fromtimestamp(stamp).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return ""


def _rule_lock(rule_id: str) -> threading.Lock:
    with _lock:
        return _rule_locks.setdefault(rule_id, threading.Lock())


def _rule_still_current(rule_id: str, generation: int) -> bool:
    current = get_rule(rule_id)
    return bool(current) and bool(current.get("enabled")) and int(current.get("generation", 0)) == int(generation)


def _prune_inflight(entry: dict, stamp: float, files: dict | None = None) -> None:
    """Keep inflight claims only for files still present in the watched folder.

    A finished task's claim stays on purpose: an overlapping rule must not
    re-submit the file just because its own ledger has not seen it. When the
    file disappears (moved by the scraper or deleted) the claim is dropped so
    the map never grows without bound.
    """
    inflight = entry.get("inflight")
    if not inflight:
        return
    if files is None:
        return
    for path in list(inflight):
        held = inflight.get(path)
        if not isinstance(held, dict):
            inflight.pop(path, None)
            continue
        present = any(_resolved(str(value[0])) == path for value in files.values())
        if not present:
            inflight.pop(path, None)


def _submit(rule: dict, paths: list[Path]) -> list[dict]:
    from . import tasks

    return tasks.create_tasks(
        str(paths[0]),
        rule["preset_id"],
        source="directory_watch",
        input_files=[str(path) for path in paths],
    )


_submit_guard_lock = threading.Lock()
_live_reservations: dict[str, str] = {}
# An inflight reservation without a task id (the window between the guard
# check and create_tasks) blocks other rules for at most this long.
_INFLIGHT_PENDING_TTL = 300.0


def _path_signature(path: str) -> list[int] | None:
    try:
        stat = os.stat(path)
        return [stat.st_size, stat.st_mtime_ns]
    except OSError:
        return None


def _active_paths() -> set[str]:
    # The task store is authoritative even after disabling/deleting/editing its
    # originating rule. Raw records avoid decoration and media-mount stat calls.
    from .task_store import recoverable
    return {_resolved(str(path)) for task in recoverable()
            if task.get("status") in {"queued", "running"} and task.get("task_type") != "scan"
            for path in task.get("input_files") or [task.get("input_directory")]
            if path}


def _active_group_overlap(paths: list[Path], active: set[str], preset_id: str = "default") -> bool:
    norm = {_resolved(str(path)) for path in paths}
    if not active:
        return False
    if norm & active:
        return True
    # A late B part must not race an active A part of the same movie.
    try:
        config = _preset_context({"preset_id": preset_id}).config_data
        all_paths = {path: Path(path) for path in norm | active}
        return any(set(members) & norm and set(members) & active
                   for members in _identity_groups(all_paths, config).values())
    except Exception:
        log.exception("active multipart identity check failed")
        raise  # fail closed rather than submit overlapping tasks


def _claimed_elsewhere(rule_id: str, paths: list[Path]) -> str | None:
    """Atomically check raw queued/running tasks and reserve normalized paths."""
    norm = {_resolved(str(path)) for path in paths}
    stamp = time.time()
    with _submit_guard_lock, _lock:
        state = read_state()
        pending = set(_live_reservations) | {path for entry in state["rules"].values()
                   for path, held in (entry.get("inflight") or {}).items()
                   if not held.get("task") and stamp - float(held.get("at") or 0) < _INFLIGHT_PENDING_TTL}
        if _active_group_overlap(paths, _active_paths() | pending, (get_rule(rule_id) or {}).get("preset_id", "default")):
            return "文件或分 P 组已有排队/运行中的任务"
        state = read_state()
        for other_id, other_entry in state["rules"].items():
            for path, held in (other_entry.get("inflight") or {}).items():
                if path not in norm:
                    continue
                task_id = held.get("task")
                if not task_id:
                    if stamp - float(held.get("at") or 0) < _INFLIGHT_PENDING_TTL:
                        return "文件正在由另一扫描提交"
                    continue
                from .task_store import record as task_record
                task = task_record(task_id, logs=False)
                if task and task.get("status") in {"queued", "running"}:
                    return "文件已有排队/运行中的任务"
                # Successful watch signatures suppress another watch rule, but
                # never impose a persistent dedup ledger on cron full scans.
                if (other_id != rule_id and task and task.get("status") == "succeeded"
                        and held.get("signature") == _path_signature(path)):
                    return "文件已由其他监控规则处理"
        entry = _rule_state_entry(state, rule_id)
        inflight = entry.setdefault("inflight", {})
        for path in norm:
            inflight[path] = {"task": "", "at": stamp}
            _live_reservations[path] = rule_id
        write_state(state)
    return None


def _release_pending(rule_id: str, paths: list[Path]) -> None:
    with _submit_guard_lock, _lock:
        state = read_state()
        entry = state["rules"].get(rule_id) or {}
        inflight = entry.get("inflight") or {}
        for path in paths:
            key = _resolved(str(path))
            if _live_reservations.get(key) == rule_id:
                _live_reservations.pop(key, None)
            if not (inflight.get(key) or {}).get("task"):
                inflight.pop(key, None)
        write_state(state)


def _mark_inflight(rule_id: str, paths: list[Path], task_by_path: dict[str, str]) -> None:
    with _submit_guard_lock, _lock:
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        inflight = entry.setdefault("inflight", {})
        normalized_tasks = {_resolved(path): task for path, task in task_by_path.items()}
        for path in paths:
            key = _resolved(str(path))
            _live_reservations.pop(key, None)
            inflight[key] = {"task": str(normalized_tasks.get(key, "")), "at": time.time(),
                             "signature": _path_signature(key)}
        write_state(state)


def _baseline_rule(rule: dict) -> dict:
    """Record the folder as it is now so only later additions are processed.

    The walk runs outside every lock (the API calls this from the request thread
    pool). A failure leaves the baseline unset, so the first scan retries it
    instead of silently treating the whole folder as new.
    """
    result = {"baselined": 0, "state": "ok", "message": ""}
    if rule.get("trigger") == "schedule":
        return result  # full scans have no watch baseline or success ledger
    if not rule.get("enabled"):
        message = "规则已暂停，启用后建立基线"
        _record_failure(rule["id"], time.time(), "disabled", message)
        result.update(state="disabled", message=message)
        return result
    try:
        context = _preset_context(rule)
    except PresetError as exc:
        _record_failure(rule["id"], time.time(), "error", str(exc))
        result.update(state="error", message=str(exc))
        return result
    if not Path(rule["path"]).is_dir():
        message = "监控目录不可访问（可能已离线或未挂载），已保留观察状态并等待恢复"
        _record_failure(rule["id"], time.time(), "offline", message)
        result.update(state="offline", message=message)
        return result
    if rule.get("include_existing"):
        with _lock:
            state = read_state()
            entry = _rule_state_entry(state, rule["id"])
            message = "已设置处理已有文件：首次扫描会把目录中已有的文件加入队列"
            entry.update(initial_scan_done=True, last_state="ok", last_error="", last_message=message)
            write_state(state)
        result.update(state="ok", message=message)
        return result
    files, problems = _walk(rule, context)
    copy_checks = _copy_checks(files)
    stamp = time.time()
    with _lock:
        state = read_state()
        entry = _rule_state_entry(state, rule["id"])
        committed = entry["committed"]
        duplicate_messages = _copy_skip_messages(files, copy_checks, committed)
        baseline = _baseline_files(files, committed, copy_checks)
        committed.update(baseline)
        entry["initial_scan_done"] = True
        entry["last_state"] = "error" if problems else "ok"
        entry["last_error"] = "；".join(problems)[:500]
        message = f"已建立基线：{len(baseline)} 个已有文件不会重复处理，此后只提交新增或变化的文件"
        notes = list(problems)
        if duplicate_messages:
            notes.append(_duplicate_summary(duplicate_messages))
        entry["last_message"] = _join(message, notes)
        entry["last_scan_at"] = _display_time(stamp)
        entry["last_scan_ts"] = stamp
        write_state(state)
    result.update(baselined=len(baseline), state=entry["last_state"], message=entry["last_message"])
    return result


# ------------------------------------------------------------------- scanning
def scan_rule(rule_id: str, *, now: float | None = None) -> dict:
    """Run one bounded scan pass for a single rule.

    ``now`` is injectable so tests and the scheduler share one code path.
    """
    stamp = time.time() if now is None else float(now)
    lock = _rule_lock(rule_id)
    if not lock.acquire(blocking=False):
        return {
            "rule_id": rule_id, "state": "scanning", "submitted": [], "submitted_count": 0,
            "pending": 0, "baselined": 0, "skipped": 0, "skipped_run": True,
            "message": "该规则正在扫描，已跳过本次触发",
        }
    try:
        rule = get_rule(rule_id)
        if rule is None:
            raise RuleError("目录监控规则不存在")
        if rule.get("trigger") == "schedule":
            return {"rule_id": rule_id, "state": "ok", "submitted": [], "submitted_count": 0,
                    "message": "定时规则仅通过定时全量触发", "skipped_run": True}
        return _scan(rule_id, stamp)
    finally:
        lock.release()


def _record_failure(rule_id: str, stamp: float, state: str, message: str) -> None:
    with _lock:
        state_file = read_state()
        entry = _rule_state_entry(state_file, rule_id)
        entry.update(
            last_state=state, last_error=message, last_message=message,
            last_scan_at=_display_time(stamp), last_scan_ts=stamp,
        )
        write_state(state_file)


def _evaluate(committed: dict, observed: dict, files: dict, stamp: float, stable_window: float,
              copy_checks: dict | None = None):
    """Return (known, candidates); the observation ledger is updated in place."""
    known: dict[str, tuple[Path, int, int]] = {}
    candidates: list[str] = []
    for rel, (path, size, mtime) in files.items():
        record = committed.get(rel)
        check = (copy_checks or {}).get(rel)
        if check:
            duplicate = _duplicate_record(size, mtime, check, record)
            if duplicate:
                committed[rel] = duplicate
                observed.pop(rel, None)
                continue  # never include a copy in a late multipart group
        hash_unchanged = not check or (
            check.get("content_hash") is not None
            and record and record.get("status") != "duplicate"
            and record.get("content_hash") == check["content_hash"]
        )
        if record and record.get("task_id"):
            from .task_store import record as task_record
            task = task_record(record["task_id"], logs=False)
            if not task or task.get("status") in {"failed", "cancelled"}:
                committed.pop(rel, None)
                record = None  # failed is not a successful signature; retry after stability
        if record and hash_unchanged and int(record.get("size", -1)) == size and int(record.get("mtime_ns", -1)) == mtime:
            observed.pop(rel, None)
            known[rel] = (path, size, mtime)  # already handled, but a late part may cite it
            continue
        pending = observed.get(rel)
        if (not pending or int(pending.get("size", -1)) != size
                or int(pending.get("mtime_ns", -1)) != mtime
                or (check and pending.get("content_hash") != check.get("content_hash"))):
            pending = {"size": size, "mtime_ns": mtime, "first_seen": stamp}
            if check:
                pending["content_hash"] = check.get("content_hash")
            observed[rel] = pending
        if stamp - float(pending.get("first_seen", stamp)) >= stable_window:
            known[rel] = (path, size, mtime)
            candidates.append(rel)
    for rel in [item for item in observed if item not in files]:
        observed.pop(rel, None)
    if len(committed) > MAX_COMMITTED_ENTRIES:
        # Only prune records for files that are gone right now; a temporarily
        # offline mount never reaches this point (the scan returns "offline").
        for rel in [item for item in committed if item not in files]:
            committed.pop(rel, None)
    return known, candidates


def _commit_files(rule_id: str, known: dict, rels: list[str], *, status: str,
                  task_by_rel: dict | None = None, reason: str = "") -> None:
    """Persist the verdict for one submission group (short critical section)."""
    tasks = task_by_rel or {}
    with _lock:
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        for rel in rels:
            _, size, mtime = known[rel]
            entry["committed"][rel] = _file_entry(
                size, mtime, status=status, task_id=tasks.get(rel, ""), reason=reason)
            pending = entry["observed"].pop(rel, None)
            if pending and "content_hash" in pending:
                entry["committed"][rel]["content_hash"] = pending["content_hash"]
        write_state(state)


def _pending_count(rule_id: str) -> int:
    with _lock:
        return len((read_state()["rules"].get(rule_id) or {}).get("observed") or {})


def _record_scan_summary(rule_id: str, stamp: float, *, state: str, message: str, error: str = "",
                         skipped_reason: str = "", submitted: int = 0, skipped: int = 0) -> None:
    with _lock:
        state_file = read_state()
        entry = _rule_state_entry(state_file, rule_id)
        entry["last_state"] = state
        entry["last_message"] = message
        entry["last_error"] = error[:500]
        if skipped_reason:
            entry["last_skipped_reason"] = skipped_reason[:300]
        if submitted:
            entry["submitted_total"] = int(entry.get("submitted_total") or 0) + submitted
            entry["last_submitted_at"] = _display_time(stamp)
            entry["last_submitted_count"] = submitted
        if skipped:
            entry["skipped_total"] = int(entry.get("skipped_total") or 0) + skipped
        entry["last_scan_at"] = _display_time(stamp)
        entry["last_scan_ts"] = stamp
        write_state(state_file)


def _scan(rule_id: str, stamp: float) -> dict:
    result = {
        "rule_id": rule_id, "state": "ok", "submitted": [], "submitted_count": 0,
        "pending": 0, "baselined": 0, "skipped": 0, "message": "", "skipped_run": False,
    }
    rule = get_rule(rule_id)
    if rule is None:
        raise RuleError("目录监控规则不存在")
    if not rule.get("enabled"):
        message = "规则已暂停，不再扫描新文件"
        _record_failure(rule_id, stamp, "disabled", message)
        result.update(state="disabled", message=message)
        return result

    try:
        context = _preset_context(rule)
    except PresetError as exc:
        _record_failure(rule_id, stamp, "error", str(exc))
        result.update(state="error", message=str(exc))
        return result

    if not Path(rule["path"]).is_dir():
        message = "监控目录不可访问（可能已离线或未挂载），已保留观察状态并等待恢复"
        _record_failure(rule_id, stamp, "offline", message)
        result.update(state="offline", message=message)
        return result

    files, problems = _walk(rule, context)
    copy_checks = _copy_checks(files)

    # 1. Evaluate signatures and persist the ledger. Never runs a task submission
    #    while holding the lock.
    with _lock:
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        committed = entry["committed"]
        observed = entry["observed"]

        if not entry.get("initial_scan_done") and not rule.get("include_existing"):
            duplicate_messages = _copy_skip_messages(files, copy_checks, committed)
            baseline = _baseline_files(files, committed, copy_checks)
            committed.update(baseline)
            entry["observed"] = {}
            entry["initial_scan_done"] = True
            entry["last_state"] = "error" if problems else "ok"
            entry["last_error"] = "；".join(problems)[:500]
            message = f"首次扫描完成：{len(baseline)} 个已有文件记为基线，此后只处理新增或变化的文件"
            notes = list(problems)
            if duplicate_messages:
                notes.append(_duplicate_summary(duplicate_messages))
            entry["last_message"] = _join(message, notes)
            entry["last_scan_at"] = _display_time(stamp)
            entry["last_scan_ts"] = stamp
            write_state(state)
            result.update(baselined=len(baseline), state=entry["last_state"], message=entry["last_message"])
            return result

        entry["initial_scan_done"] = True
        duplicate_messages = _copy_skip_messages(files, copy_checks, committed)
        known, candidates = _evaluate(
            committed, observed, files, stamp, float(rule["stable_seconds"] or 0), copy_checks)
        # Keep inflight claims only for files that still exist in the folder;
        # dropped files release their cross-rule reservation.
        _prune_inflight(entry, stamp, files)
        committed_snapshot = {rel: dict(value) for rel, value in committed.items()}
        write_state(state)

    # 2. Submit outside the lock: ``create_tasks`` writes configs, touches the
    #    task store and may import the vendor scanner.
    submitted_ids: list[str] = []
    submitted_count = 0
    skipped = 0
    waiting = 0
    failures: list[str] = []
    skip_reasons: list[str] = []
    if candidates:
        cap = int(rule["max_tasks_per_scan"])
        groups = _identity_groups({rel: value[0] for rel, value in files.items()
                                   if committed_snapshot.get(rel, {}).get("status") != "duplicate"}, context.config_data)
        key_of = {rel: key for key, members in groups.items() for rel in members}
        candidate_keys = list(dict.fromkeys(key_of.get(rel, ("path", rel)) for rel in candidates))
        for key in sorted(candidate_keys, key=str):
            if submitted_count >= cap:
                break
            # A late multipart part joins its already known siblings, exactly
            # like a manual multi-select scan.
            members = groups.get(key, [key[1]])
            if any(rel not in known for rel in members):
                waiting += 1
                continue  # every part must pass its own stability window
            paths = sorted(members)
            if not paths:
                continue
            if any(committed_snapshot.get(rel, {}).get("task_id")
                   and _task_active(committed_snapshot[rel]["task_id"]) for rel in paths):
                waiting += 1
                continue
            if not _rule_still_current(rule_id, rule.get("generation", 1)):
                failures.append("规则已修改或暂停，已停止本次提交")
                result["skipped_run"] = True
                break
            blocked = _claimed_elsewhere(rule_id, [known[rel][0] for rel in paths])
            if blocked:
                waiting += 1
                continue
            try:
                created = _submit(rule, [known[rel][0] for rel in paths])
            except Exception as exc:  # noqa: BLE001
                _release_pending(rule_id, [known[rel][0] for rel in paths])
                from .tasks import NoScrapeTasksError

                reason = str(exc) or exc.__class__.__name__
                if isinstance(exc, (NoScrapeTasksError, ValueError)):
                    _commit_files(rule_id, known, paths, status="skipped", reason=reason)
                    skipped += 1
                    skip_reasons.append(reason)
                    continue
                failures.append(f"创建任务失败：{reason}")
                break
            if not created:
                _release_pending(rule_id, [known[rel][0] for rel in paths])
                _commit_files(rule_id, known, paths, status="skipped", reason="未生成任务")
                skipped += 1
                continue
            by_path = {
                os.path.normcase(str(path)): str(task["id"])
                for task in created
                for path in (task.get("input_files") or [task.get("input_directory")])
            }
            fallback = str(created[0]["id"])
            _mark_inflight(rule_id, [known[rel][0] for rel in paths],
                           {str(path): by_path.get(os.path.normcase(str(path)), fallback) for path in [known[rel][0] for rel in paths]})
            _commit_files(
                rule_id, known, paths, status="submitted",
                task_by_rel={
                    rel: by_path.get(os.path.normcase(str(known[rel][0])), fallback) for rel in paths
                },
            )
            submitted_ids.extend(str(task["id"]) for task in created)
            submitted_count += len(created)

    problems = failures + problems
    pending = _pending_count(rule_id)
    message = _scan_message(submitted_count, waiting, skipped, pending, problems, skip_reasons,
                            duplicate_messages)
    state_name = "error" if problems else "ok"
    _record_scan_summary(
        rule_id, stamp, state=state_name, message=message,
        error="；".join(skip_reasons + problems), skipped_reason=skip_reasons[0] if skip_reasons else "",
        submitted=submitted_count, skipped=skipped,
    )
    result.update(
        submitted=submitted_ids,
        submitted_count=submitted_count,
        pending=pending,
        skipped=skipped,
        state=state_name,
        message=message,
    )
    return result


def _join(message: str, problems: list[str]) -> str:
    return f"{message}；{'；'.join(problems)[:300]}" if problems else message


def _scan_message(submitted: int, waiting: int, skipped: int, pending: int,
                  problems: list[str], skip_reasons: list[str] | None = None,
                  duplicate_messages: list[str] | None = None) -> str:
    parts: list[str] = []
    if submitted:
        parts.append(f"已提交 {submitted} 个任务")
    if waiting:
        parts.append(f"{waiting} 个变化文件等待现有任务完成后再提交")
    if skipped:
        detail = f"（{skip_reasons[0]}）" if skip_reasons else "（已记录，不重复尝试）"
        parts.append(f"{skipped} 个文件未提交{detail}")
    if duplicate_messages:
        parts.append(_duplicate_summary(duplicate_messages))
    if pending:
        parts.append(f"{pending} 个文件正在等待稳定")
    if problems:
        parts.append("；".join(problems)[:300])
    if not parts:
        parts.append("未发现新增或变化的文件")
    return "，".join(parts)


# --------------------------------------------------------- scheduled triggers
_schedule_run_lock = threading.RLock()


def _local_now():
    from .timeutils import local_now

    return local_now()


def _submit_schedule(rule: dict) -> list[dict]:
    from . import tasks
    from .task_store import upsert_many
    from .task_scans import discard_prepared

    # Preserve cron's full directory scan, grouping and preset semantics. Filter
    # only active overlaps, under the same guard used by watch reservations.
    prepared = tasks._prepare_tasks(str(rule["path"]), rule["preset_id"],
                                    source="schedule", schedule_id=str(rule["id"]))
    accepted, discarded = [], []
    persisted = False
    try:
        with _submit_guard_lock:
            active = _active_paths()
            with _lock:
                state = read_state()
                pending = set(_live_reservations) | {path for entry in state["rules"].values()
                           for path, held in (entry.get("inflight") or {}).items()
                           if not held.get("task") and time.time() - float(held.get("at") or 0) < _INFLIGHT_PENDING_TTL}
            for task in prepared:
                paths = [Path(path) for path in task.get("input_files") or [task["input_directory"]]]
                if _active_group_overlap(paths, active | pending, rule["preset_id"]):
                    discarded.append(task)
                else:
                    accepted.append(task)
            if not _rule_still_current(rule["id"], rule.get("generation", 1)):
                raise RuleError("规则已修改或暂停，已停止本次提交")
            upsert_many(accepted)
            persisted = True
            for task in accepted:
                tasks._enqueue_task(task)
    except BaseException:
        discard_prepared([task for task in prepared if not persisted or task not in accepted])
        raise
    discard_prepared(discarded)
    return accepted


def run_schedule_rule(rule_id: str, run_key: str) -> dict:
    """One cron-triggered full scan, mirroring the legacy minute-key semantics.

    The minute key is claimed atomically in the unified state file before any
    task creation, and a run whose previous batch is still queued/running is
    skipped (recorded, not retried) exactly like the legacy worker did.
    """
    from . import tasks

    rule = get_rule(rule_id)
    if rule is None or rule.get("trigger") != "schedule":
        raise RuleError("定时规则不存在")
    if not rule.get("enabled"):
        return {"rule_id": rule_id, "run_key": run_key, "state": "disabled", "created": 0, "message": "规则已暂停"}
    with _schedule_run_lock:
        with _lock:
            state = read_state()
            entry = _rule_state_entry(state, rule_id)
            if str(entry.get("last_schedule_run_key", (rule.get("legacy_schedule") or {}).get("last_run_key")) or "") == run_key:
                return {"rule_id": rule_id, "run_key": run_key, "state": "duplicate", "created": 0, "message": "本次触发已处理"}
            if tasks.active_schedule_task_ids(rule_id) or any(
                    _task_active(str(task_id)) for run in (rule.get("legacy_schedule") or {}).get("runs") or []
                    for task_id in run.get("task_ids") or []):
                entry["last_schedule_run_key"] = run_key
                entry["last_state"] = "ok"
                entry["last_message"] = "上一次定时刮削尚未完成，已跳过本次运行"
                entry["last_scan_at"] = now_iso()
                entry.setdefault("schedule_runs", []).append({"run_key": run_key, "result": entry["last_message"],
                    "task_ids": [], "state": "skipped", "at": now_iso()})
                write_state(state)
                return {"rule_id": rule_id, "run_key": run_key, "state": "skipped", "created": 0,
                        "message": entry["last_message"]}
            entry["last_schedule_run_key"] = run_key
            entry["last_scan_at"] = now_iso()
            entry["last_message"] = "正在创建刮削任务"
            entry["schedule_in_progress"] = {"run_key": run_key, "at": now_iso()}
            write_state(state)
        created: list[dict] = []
        state_name = "ok"
        message = ""
        try:
            created = _submit_schedule(rule)
            message = f"已创建 {len(created)} 个任务"
        except Exception as exc:  # noqa: BLE001
            from .tasks import NoScrapeTasksError

            if isinstance(exc, NoScrapeTasksError):
                message = "未发现符合条件的影片，已跳过本次运行"
            else:
                state_name = "error"
                message = f"执行失败：{exc}"
        if _record_schedule_result(rule_id, run_key, state_name, message, [task["id"] for task in created]):
            return {"rule_id": rule_id, "run_key": run_key, "state": state_name, "created": len(created),
                    "task_ids": [str(task["id"]) for task in created], "message": message}
        return {"rule_id": rule_id, "run_key": run_key, "state": "duplicate", "created": 0, "message": "本次触发已处理"}


def _record_schedule_result(rule_id: str, run_key: str, state_name: str, message: str, task_ids: list[str]) -> bool:
    """Persist the run verdict; empty scans keep the minute claim but no entry."""
    with _lock:
        state = read_state()
        entry = _rule_state_entry(state, rule_id)
        runs = entry.setdefault("schedule_runs", [])
        if any(str(run.get("run_key") or "") == run_key for run in runs):
            return False
        if task_ids or state_name == "error":
            runs.append({
                "run_key": run_key, "result": message[:500], "task_ids": [str(item) for item in task_ids],
                "state": state_name, "at": now_iso(),
            })
            entry["schedule_runs"] = runs
        entry.pop("schedule_in_progress", None)
        entry["last_state"] = state_name
        entry["last_error"] = message[:500] if state_name == "error" else ""
        entry["last_message"] = message[:500]
        entry["last_scan_at"] = now_iso()
        write_state(state)
        return True


def _rule_moment(rule: dict, moment):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    zone = rule.get("timezone")
    if not zone:
        return moment
    try:
        return moment.astimezone(ZoneInfo(zone))
    except (ValueError, ZoneInfoNotFoundError):
        return moment


def recover_schedule_runs() -> None:
    """Finalize interrupted claims; keep persisted task associations visible."""
    from .task_store import load
    with _schedule_run_lock, _lock:
        state = read_state()
        changed = False
        for rule_id, entry in state["rules"].items():
            claim = entry.get("schedule_in_progress")
            if not claim:
                continue
            task_ids = [str(task["id"]) for task in load()
                        if task.get("schedule_id") == rule_id
                        and str(task.get("created_at") or "") >= str(claim.get("at") or "")]
            entry.setdefault("schedule_runs", []).append({"run_key": claim["run_key"], "at": claim.get("at"),
                "task_ids": task_ids, "state": "interrupted", "result": "服务中断，已恢复关联任务；后续按计划继续"})
            entry.pop("schedule_in_progress", None)
            entry["last_message"] = "服务中断，已恢复关联任务；后续按计划继续"
            changed = True
        if changed:
            write_state(state)


def next_schedule_run(rule: dict) -> str:
    from datetime import datetime

    cron = str(rule.get("cron") or "")
    if not cron or croniter is None:
        return ""
    try:
        return croniter(cron, _rule_moment(rule, _local_now())).get_next(datetime).isoformat(timespec="minutes")
    except (TypeError, ValueError, KeyError):
        return ""


# ----------------------------------------------------------------- scheduler
class Scheduler:
    """Daemon thread that polls enabled rules on their own interval."""

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = max(0.05, float(poll_interval))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._due: dict[str, float] = {}
        self._lock = threading.RLock()
        self._restart_requested = False

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.ident is not None and thread.is_alive()
                    and not self._stop.is_set())

    def start(self) -> "Scheduler":
        with self._lock:
            thread = self._thread
            if thread is not None and thread.ident is not None and thread.is_alive():
                if not self._stop.is_set():
                    return self
                # A previous stop() timed out while this worker was still busy.
                # Keep that single worker and let it resume: creating another
                # thread here would run two pollers side by side.
                self._restart_requested = True
                return self
            self._restart_requested = False
            self._stop.clear()
            self._wake.clear()
            self._thread = threading.Thread(target=self._run, name="directory-watch", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the worker to exit, keeping its reference while it is still alive."""
        with self._lock:
            # The most recent stop() wins: cancel any pending restart intent so
            # a later stop() after start() lets the worker exit for good.
            self._restart_requested = False
            self._stop.set()
            self._wake.set()
            thread = self._thread
            if thread is None:
                return
            if thread.ident is None:
                # Created but never started (callers that patch Thread.start).
                if self._thread is thread:
                    self._thread = None
                return
            if thread is threading.current_thread():
                # stop() from a scan hook: the worker leaves after this pass.
                return
        thread.join(max(0.0, float(timeout)))
        if thread.is_alive():
            return  # a later start() must reuse this worker, not add a second
        with self._lock:
            # A concurrent start() may have installed a new thread meanwhile.
            if self._thread is thread:
                self._thread = None

    def wake(self) -> None:
        """Shorten the idle wait so rule edits apply within a moment."""
        self._wake.set()

    def run_due(self, now: float | None = None) -> list[dict]:
        stamp = time.time() if now is None else float(now)
        results = []
        for rule in read_rules():
            if not rule.get("enabled"):
                self._due.pop(rule["id"], None)
                continue
            if rule.get("trigger") == "schedule":
                continue  # cron rules fire from run_schedules()
            if stamp < self._due.get(rule["id"], 0.0):
                continue
            self._due[rule["id"]] = stamp + float(rule["poll_seconds"])
            try:
                results.append(scan_rule(rule["id"], now=stamp))
            except RuleError:
                continue
            except Exception:  # noqa: BLE001 - one bad rule must not stop the loop
                log.exception("directory watch scan failed for %s", rule["id"])
        return results

    def run_schedules(self, now=None) -> list[dict]:
        """Fire schedule rules whose cron matches the current minute."""
        if croniter is None:
            return []
        moment = _local_now() if now is None else now
        results = []
        for rule in read_rules():
            if rule.get("trigger") != "schedule" or not rule.get("enabled"):
                continue
            try:
                rule_moment = _rule_moment(rule, moment)
                due = croniter.match(str(rule.get("cron") or ""), rule_moment)
            except (TypeError, ValueError, KeyError):
                continue
            if not due:
                continue
            try:
                results.append(run_schedule_rule(rule["id"], rule_moment.strftime("%Y-%m-%dT%H:%M")))
            except RuleError:
                continue
            except Exception:  # noqa: BLE001
                log.exception("scheduled scrape failed for %s", rule["id"])
        return results

    def _run(self) -> None:
        while True:
            while not self._stop.is_set():
                try:
                    self.run_due()
                    self.run_schedules()
                except Exception:  # noqa: BLE001
                    log.exception("directory watch scheduler pass failed")
                if self._stop.is_set():
                    break
                self._wake.wait(self.poll_interval)
                self._wake.clear()
            with self._lock:
                if not self._restart_requested:
                    return
                # start() was called while this worker was still stopping, so
                # this thread resumes instead of a second one being spawned.
                self._restart_requested = False
                self._stop.clear()
                self._wake.clear()


_scheduler = Scheduler()
_scheduler_enabled = False


def start_scheduler() -> Scheduler:
    global _scheduler_enabled
    if not _scheduler_enabled:
        # Fold legacy schedules in before the first pass; idempotent and safe
        # to repeat on every start (an already-imported id is never touched).
        try:
            migrate_legacy_schedules()
            recover_schedule_runs()
        except Exception:  # noqa: BLE001 - migration must never block startup
            log.exception("legacy schedule migration failed")
    _scheduler_enabled = True
    _scheduler.start()
    return _scheduler


def stop_scheduler(timeout: float = 5.0) -> None:
    global _scheduler_enabled
    _scheduler_enabled = False
    _scheduler.stop(timeout)


def scheduler_state() -> dict:
    return {
        "directory_watch_enabled": _scheduler_enabled,
        "thread_running": _scheduler.running,
        "poll_interval": _scheduler.poll_interval,
        "schedule_trigger": True,  # cron rules are handled by the same thread
    }


def _wake_scheduler() -> None:
    if _scheduler.running:
        _scheduler.wake()


def reset_runtime() -> None:
    """Drop in-process state (used by tests and by an explicit restart)."""
    stop_scheduler()
    with _lock:
        _rule_locks.clear()
    with _submit_guard_lock:
        _live_reservations.clear()
    with _scheduler._lock:
        _scheduler._restart_requested = False
    _scheduler._due.clear()
    _scheduler._wake.clear()
