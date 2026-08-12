from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import yaml
import requests
from PIL import Image, ImageOps

from .storage import DATA_DIR, IS_FROZEN, VENDOR_DIR, get_preset, load_tasks, read_config, save_tasks
from .config_validation import load_base_config, validate_config_data
from .timeutils import now_iso


_lock = threading.RLock()
_queue_condition = threading.Condition(_lock)
_processes: dict[str, subprocess.Popen] = {}
_batch_running: dict[str, int] = {}
_logs: dict[str, list[str]] = {}
_deleted_tasks: set[str] = set()
_cancelled_tasks: set[str] = set()
_VIDEO_EXTENSIONS = {".3gp", ".avi", ".f4v", ".flv", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv", ".strm", ".mpg"}
_PROGRESS_RE = re.compile(r"^(?P<key>[^:]{1,120}):\s+(?P<percent>\d{1,3})%.*?(?:(?P<done>\d+)\s*/\s*(?P<total>\d+))?")
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_TQDM_RE = re.compile(r"\d{1,3}%\|.*(?:\||$)|\b\d+(?:\.\d+)?(?:[KMGT]?i?B|B)\s*\[\d{2}:\d{2}")
_CRAWLER_TQDM_RE = re.compile(r"^(?P<name>javsp\.web\.[^:]+):\s*(?P<message>.*?)\s*:\s*\d{1,3}%\|")
_IMAGE_TRANSFER_RE = re.compile(r"^(?:Downloading extrafanart \d+ from url:|[^\s:]+\.(?:jpg|jpeg|png|webp):\s*\d+(?:\.\d+)?[KMGT]?i?B)", re.IGNORECASE)
_NATIVE_PROGRESS_LOG_RE = re.compile(r"^已下载剧照\s+\d+/\d+:")
_MAX_LOG_LINES = 5000
_MAX_DISPLAY_LOG_LINES = 1500
_BYTE_SIZE_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[kmgtpe]?i?b)?\s*$", re.IGNORECASE)


def _decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _task_name(input_path: str) -> str:
    path = Path(input_path)
    if path.is_file():
        return path.stem
    if path.is_dir():
        try:
            videos = sorted(
                (item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in _VIDEO_EXTENSIONS),
                key=lambda item: str(item).lower(),
            )
            if videos:
                return videos[0].stem
        except OSError:
            pass
    return path.stem if path.suffix.lower() in _VIDEO_EXTENSIONS else (path.name or input_path)


def _file_size(input_path: str) -> int:
    try:
        path = Path(input_path)
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _preset_task_concurrency(preset_id: str) -> int:
    preset = get_preset(preset_id) or get_preset("default") or {}
    try:
        return max(1, min(32, int(preset.get("task_concurrency", 1))))
    except (TypeError, ValueError):
        return 1


def _preset_config_data(preset_id: str) -> tuple[dict, dict]:
    preset = get_preset(preset_id) or get_preset("default")
    if not preset:
        raise ValueError("没有可用的刮削预设")
    try:
        data = load_base_config()
        if preset.get("mode") == "yaml":
            preset_data = yaml.safe_load(preset.get("content", "")) or {}
            data = _deep_merge(data, preset_data)
        else:
            data = _deep_merge(data, preset.get("form") or {})
    except yaml.YAMLError as exc:
        raise ValueError(f"预设 YAML 格式错误: {exc}") from exc
    try:
        validate_config_data(data)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    return data, preset


def _minimum_size_bytes(config_data: dict) -> int:
    value = (config_data.get("scanner") or {}).get("minimum_size", 0)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = _BYTE_SIZE_RE.match(str(value))
    if not match:
        raise ValueError("预设中的最小匹配文件大小无效")
    units = {"": 1, "b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4, "pb": 1000**5,
             "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4, "pib": 1024**5}
    unit = (match.group("unit") or "").lower()
    if unit not in units:
        raise ValueError("预设中的最小匹配文件大小无效")
    return int(float(match.group("value")) * units[unit])


def _clean_log_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    progress_indexes: dict[str, int] = {}
    for raw in lines:
        for part in raw.replace("\r", "\n").splitlines():
            line = part.strip()
            if not line:
                continue
            crawler_progress = _CRAWLER_TQDM_RE.match(line)
            if crawler_progress:
                # Web workers emit a structured crawler event for this state.
                # Retaining the terminal redraw would reintroduce tqdm noise.
                continue
            elif _IMAGE_TRANSFER_RE.match(line) or _TQDM_RE.search(line):
                continue
            if cleaned and cleaned[-1] == line:
                continue
            match = _PROGRESS_RE.match(line)
            if match:
                key = match.group("key").strip()
                if key in progress_indexes:
                    cleaned[progress_indexes[key]] = line
                    continue
                progress_indexes[key] = len(cleaned)
            cleaned.append(line)
    return cleaned


def _progress_from_logs(lines: list[str]) -> dict:
    crawlers: dict[str, str] = {}
    crawler_details: dict[str, dict] = {}
    stages = {"concurrent": {"percent": 0, "done": 0, "total": 0}, "summary": {"percent": 0, "done": 0, "total": 0}, "images": {"percent": 0, "done": 0, "total": 0}}
    metadata: dict[str, object] = {}
    images = {"cover_done": 0, "fanart_done": 0, "fanart_total": 0, "failed": False, "errors": []}
    image_sources: dict[str, object] = {}
    output: dict[str, str] = {}
    for line in lines:
        event_marker = line.find("JAVSP_PROGRESS ")
        if event_marker >= 0:
            try:
                event = json.loads(line[event_marker + len("JAVSP_PROGRESS "):])
            except json.JSONDecodeError:
                event = {}
            stage = event.get("stage")
            if stage in {"concurrent", "summary"}:
                stages[stage] = {"percent": round((event.get("done", 0) / event.get("total", 1)) * 100) if event.get("total") else 0, "done": event.get("done", 0), "total": event.get("total", 0)}
            elif stage == "images":
                done = int(event.get("done", 0) or 0)
                total = int(event.get("total", 0) or 0)
                if event.get("kind") == "cover":
                    images["cover_done"] = min(done, 1)
                elif event.get("kind") == "fanart":
                    images["fanart_done"] = max(images["fanart_done"], done)
                    images["fanart_total"] = max(images["fanart_total"], total)
                if event.get("status") == "failed":
                    images["failed"] = True
                    images["errors"].append({"kind": event.get("kind"), "current": event.get("current"), "error": str(event.get("error") or "图片下载失败")})
                combined_done = images["cover_done"] + images["fanart_done"]
                combined_total = 1 + images["fanart_total"]
                stages["images"] = {"percent": round((combined_done / combined_total) * 100) if combined_total else 0, "done": combined_done, "total": combined_total}
            elif stage == "image_retry" and event.get("status") == "running":
                images["failed"] = False
                images["errors"] = []
            elif stage == "crawler" and event.get("name"):
                crawler_name = str(event["name"]).removeprefix("javsp.web.")
                status_labels = {"success": "完成", "failed": "失败", "not_found": "未找到", "duplicate": "重复"}
                if event.get("status") == "retrying":
                    crawlers[crawler_name] = f"重试 {event.get('attempt', 0)}/{event.get('total', '?')}"
                else:
                    crawlers[crawler_name] = status_labels.get(event.get("status"), "抓取中")
                crawler_details[crawler_name] = {key: value for key, value in event.items() if key in {"status", "dvdid", "title", "url", "reason", "attempt", "total"} and value not in (None, "")}
            elif stage == "metadata":
                metadata = {key: value for key, value in event.items() if key in {"dvdid", "title", "actress", "director", "producer", "publisher", "publish_date"}}
            elif stage == "image_sources":
                image_sources = {"cover_urls": list(event.get("cover_urls") or []), "preview_pics": list(event.get("preview_pics") or [])}
            elif stage == "output":
                output = {key: str(event.get(key) or "") for key in {"save_dir", "fanart_file", "poster_file"}}
            continue
        match = _PROGRESS_RE.match(line)
        if not match:
            continue
        percent = int(match.group("percent"))
        counts = re.search(r"(\d+)\s*/\s*(\d+)", line)
        done = int(counts.group(1)) if counts else 0
        total = int(counts.group(2)) if counts else 0
        key = match.group("key").strip()
        if "并发" in key or "Crawler" in key or key.startswith("javsp.web."):
            stages["concurrent"] = {"percent": percent, "done": done, "total": total}
            if key.startswith("javsp.web."):
                crawlers[key.removeprefix("javsp.web.")] = "完成" if "完成" in line else ("重试中" if "重试" in line else "抓取中")
        elif "汇总" in key or "整理" in key:
            stages["summary"] = {"percent": percent, "done": done, "total": total}
        elif "下载" in key or "Downloading" in key or key.lower().endswith((".jpg", ".png", ".webp")):
            stages["images"] = {"percent": percent, "done": done, "total": total}
    return {"stages": stages, "crawlers": crawlers, "crawler_details": crawler_details, "metadata": metadata, "images": images, "image_sources": image_sources, "output": output}


def _progress_event_message(event: dict) -> str | None:
    stage = event.get("stage")
    status = event.get("status")
    if stage == "scan":
        return "开始扫描影片文件" if status == "running" else f"扫描完成，识别到 {event.get('total', 0)} 部影片"
    if stage == "movie":
        if status == "running":
            files = "、".join(event.get("files") or [])
            return f"开始刮削 {event.get('index', 0)}/{event.get('total', 0)}: {files}".rstrip(": ")
        if status == "completed":
            title = event.get("title") or ""
            return f"影片刮削完成{': ' + title if title else ''}"
        if status == "failed":
            return f"影片刮削失败: {event.get('error') or '未知错误'}"
    if stage == "task" and status == "completed":
        return f"全部任务完成，共处理 {event.get('total', 0)} 部影片"
    if stage == "crawler":
        name = str(event.get("name") or "").removeprefix("javsp.web.")
        labels = {"running": "开始抓取", "success": "抓取完成", "failed": "抓取失败", "not_found": "未找到影片", "duplicate": "发现重复结果"}
        if status == "retrying":
            return f"{name}: 网络异常，正在重试（{event.get('attempt', 0)}/{event.get('total', '?')}）"
        return f"{name}: {labels.get(status, '抓取中')}" if name else None
    if stage == "summary":
        return "开始汇总影片数据" if not event.get("done") else "影片数据汇总完成"
    if stage == "metadata":
        title = event.get("title") or ""
        dvdid = event.get("dvdid") or ""
        return f"已取得影片信息{': ' + dvdid if dvdid else ''}{' - ' + title if title else ''}"
    if stage == "images":
        kind = event.get("kind")
        if kind == "cover":
            if status == "failed":
                return f"封面下载失败: {event.get('error') or '未知错误'}"
            return "开始下载封面" if not event.get("done") else "封面下载完成"
        if kind == "fanart":
            if status == "failed":
                return f"剧照下载失败（第 {event.get('current') or '?'} 张）: {event.get('error') or '未知错误'}"
            done, total = event.get("done", 0), event.get("total", 0)
            if event.get("status") == "downloading":
                return f"开始下载剧照 {event.get('current', done + 1)}/{total}"
            return f"剧照下载进度: {done}/{total}"
    if stage == "image_retry":
        labels = {"running": "正在重新下载图片", "completed": "图片重新下载完成", "failed": "图片重新下载失败"}
        return labels.get(status, "正在重新下载图片") + (f": {event.get('error')}" if event.get("error") else "")
    return None


def _display_log_lines(lines: list[str]) -> list[str]:
    display: list[str] = []
    for line in lines:
        event_marker = line.find("JAVSP_PROGRESS ")
        if event_marker >= 0:
            try:
                event = json.loads(line[event_marker + len("JAVSP_PROGRESS "):])
            except json.JSONDecodeError:
                continue
            message = _progress_event_message(event)
            if message and (not display or display[-1] != message):
                display.append(message)
            continue
        if not _PROGRESS_RE.match(line) and not _IMAGE_TRANSFER_RE.match(line) and not _TQDM_RE.search(line) and not _NATIVE_PROGRESS_LOG_RE.match(line):
            display.append(line)
    return display


def _cover_paths(input_path: str, output: dict | None = None) -> list[Path]:
    target = Path(input_path)
    poster_value = str((output or {}).get("poster_file") or "").strip()
    poster_file = Path(poster_value) if poster_value else None
    if poster_file and poster_file.is_file():
        return [poster_file]
    root_value = str((output or {}).get("save_dir") or "").strip()
    configured_root = Path(root_value) if root_value else None
    if configured_root and configured_root.is_dir():
        root = configured_root
        recursive = True
    elif target.is_dir():
        root = target
        recursive = True
    else:
        root = target.parent
        recursive = False
    found: list[Path] = []
    try:
        candidates = root.rglob("*") if recursive else root.glob("poster.jpg")
        for item in candidates:
            if item.is_file() and item.name.lower() == "poster.jpg" and len(item.relative_to(root).parts) <= 5:
                found.append(item)
            if len(found) >= 24:
                break
    except OSError:
        return []
    return sorted(found, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:12]


def _fanart_paths(input_path: str, output: dict | None = None) -> list[Path]:
    target = Path(input_path)
    root_value = str((output or {}).get("save_dir") or "").strip()
    configured_root = Path(root_value) if root_value else None
    if configured_root and configured_root.is_dir():
        root = configured_root
        recursive = False
    elif target.is_dir():
        root = target
        recursive = True
    else:
        root = target.parent
        recursive = False
    found: list[Path] = []
    try:
        candidates = root.rglob("*") if recursive else root.glob("extrafanart/*")
        for item in candidates:
            if item.is_file() and item.suffix.lower() in _IMAGE_EXTENSIONS and item.parent.name.lower() == "extrafanart" and len(item.relative_to(root).parts) <= 6:
                found.append(item)
            if len(found) >= 48:
                break
    except OSError:
        return []
    return sorted(found, key=lambda item: item.name.lower())


def _persist(task: dict) -> None:
    with _lock:
        tasks = [item for item in load_tasks() if item.get("id") != task["id"]]
        tasks.append(task)
        save_tasks(tasks)


def list_tasks() -> list[dict]:
    with _lock:
        items = load_tasks()
        for item in items:
            item["file_name"] = _task_name(item.get("input_directory", ""))
            item["size_bytes"] = _file_size(item.get("input_directory", ""))
            cleaned_logs = _clean_log_lines((_logs.get(item["id"]) or item.get("log_tail") or [])[-_MAX_LOG_LINES:])
            item["progress"] = _progress_from_logs(cleaned_logs)
            image_progress = item["progress"]
            item["title"] = item["progress"]["metadata"].get("title") or ""
            item["name"] = item["title"] if item.get("status") == "succeeded" and item["title"] else item["file_name"]
            item["log_tail"] = _display_log_lines(cleaned_logs)[-_MAX_DISPLAY_LOG_LINES:]
            if item.get("status") == "succeeded":
                for key in ("concurrent", "summary"):
                    stage = item["progress"]["stages"][key]
                    stage["percent"] = 100
                    if not stage["total"]:
                        stage["done"], stage["total"] = 1, 1
                images = item["progress"]["images"]
                image_stage = item["progress"]["stages"]["images"]
                if not images["failed"]:
                    image_stage["percent"] = 100
                    if not image_stage["total"]:
                        image_stage["done"], image_stage["total"] = 1, 1
                    images["cover_done"] = max(images["cover_done"], 1)
                    if images["fanart_total"]:
                        images["fanart_done"] = images["fanart_total"]
            output = image_progress.get("output") or {}
            item["cover_count"] = len(_cover_paths(item.get("input_directory", ""), output))
            item["fanart_count"] = len(_fanart_paths(item.get("input_directory", ""), output))
            sources = image_progress.get("image_sources", {})
            has_image_source = bool(sources.get("cover_urls") or sources.get("preview_pics"))
            expected_fanart = len(sources.get("preview_pics") or [])
            images_incomplete = (
                bool(sources.get("cover_urls")) and not item["cover_count"]
            ) or (expected_fanart and item["fanart_count"] < expected_fanart)
            item["image_retry_available"] = bool(
                has_image_source
                and output.get("fanart_file")
                and images_incomplete
                and not item.get("image_retry_running")
            )
        return list(reversed(items))


def get_task(task_id: str) -> dict | None:
    return next((task for task in list_tasks() if task["id"] == task_id), None)


def active_schedule_task_ids(schedule_id: str) -> list[str]:
    """Return unfinished tasks created by one scheduled rule."""
    with _lock:
        return [
            str(task["id"])
            for task in load_tasks()
            if str(task.get("schedule_id") or "") == schedule_id
            and (task.get("status") in {"queued", "running"} or task.get("image_retry_running"))
        ]


def get_cover_path(task_id: str, index: int) -> Path | None:
    task = next((item for item in load_tasks() if item.get("id") == task_id), None)
    if not task or index < 0:
        return None
    progress = _progress_from_logs(_clean_log_lines((_logs.get(task_id) or task.get("log_tail") or [])[-_MAX_LOG_LINES:]))
    paths = _cover_paths(task.get("input_directory", ""), progress.get("output") or {})
    return paths[index] if index < len(paths) else None


def get_fanart_path(task_id: str, index: int) -> Path | None:
    task = next((item for item in load_tasks() if item.get("id") == task_id), None)
    if not task or index < 0:
        return None
    progress = _progress_from_logs(_clean_log_lines((_logs.get(task_id) or task.get("log_tail") or [])[-_MAX_LOG_LINES:]))
    paths = _fanart_paths(task.get("input_directory", ""), progress.get("output") or {})
    return paths[index] if index < len(paths) else None


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_task_config(task_id: str, input_directory: str, preset_id: str) -> tuple[Path, str]:
    data, preset = _preset_config_data(preset_id)
    scanner = data.setdefault("scanner", {})
    scanner["input_directory"] = input_directory
    scanner["manual"] = False
    path = DATA_DIR / "task-config" / f"{task_id}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path, str(preset.get("name") or preset_id)


def create_task(
    input_directory: str,
    preset_id: str = "default",
    *,
    batch_id: str | None = None,
    task_concurrency: int | None = None,
    source: str = "manual",
    schedule_id: str | None = None,
) -> dict:
    input_directory = os.path.abspath(os.path.expanduser(input_directory.strip()))
    if not input_directory or not os.path.exists(input_directory):
        raise ValueError("输入路径不存在")
    if not os.path.isdir(input_directory) and not os.path.isfile(input_directory):
        raise ValueError("输入路径不是目录或文件")
    config_data, _ = _preset_config_data(preset_id)
    minimum_size = _minimum_size_bytes(config_data)
    if os.path.isfile(input_directory) and os.path.getsize(input_directory) < minimum_size:
        raise ValueError(f"影片文件小于预设的最小匹配文件大小，未创建任务（至少 {minimum_size} 字节）")
    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id,
        "name": _task_name(input_directory),
        "input_directory": input_directory,
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "return_code": None,
        "error": None,
        "batch_id": batch_id or task_id,
        "task_concurrency": task_concurrency or _preset_task_concurrency(preset_id),
        "source": source,
        "schedule_id": schedule_id,
    }
    config_path, preset_name = _build_task_config(task_id, input_directory, preset_id)
    task["config_path"] = str(config_path)
    task["preset_id"] = preset_id
    task["preset_name"] = preset_name
    _logs[task_id] = [f"任务已排队: {input_directory}"]
    _persist(task)
    thread = threading.Thread(target=_run_task, args=(task,), daemon=True)
    thread.start()
    return task


def create_tasks(
    input_directory: str,
    preset_id: str = "default",
    *,
    source: str = "manual",
    schedule_id: str | None = None,
) -> list[dict]:
    input_path = Path(os.path.abspath(os.path.expanduser(input_directory.strip())))
    if not input_path.exists():
        raise ValueError("输入路径不存在")
    config_data, _ = _preset_config_data(preset_id)
    minimum_size = _minimum_size_bytes(config_data)
    concurrency = _preset_task_concurrency(preset_id)
    batch_id = uuid.uuid4().hex[:12]
    if input_path.is_file():
        if input_path.stat().st_size < minimum_size:
            raise ValueError(f"影片文件小于预设的最小匹配文件大小，未创建任务（至少 {minimum_size} 字节）")
        return [create_task(str(input_path), preset_id, batch_id=batch_id, task_concurrency=concurrency, source=source, schedule_id=schedule_id)]
    if not input_path.is_dir():
        raise ValueError("输入路径不是目录或文件")
    try:
        video_files = sorted(
            (
                item for item in input_path.rglob("*")
                if item.is_file() and item.suffix.lower() in _VIDEO_EXTENSIONS and item.stat().st_size >= minimum_size
            ),
            key=lambda item: str(item).lower(),
        )
    except OSError as exc:
        raise ValueError(f"无法读取输入目录: {exc}") from exc
    if not video_files:
        raise ValueError("输入目录中未找到符合预设最小匹配文件大小的影片文件")
    return [
        create_task(str(video), preset_id, batch_id=batch_id, task_concurrency=concurrency, source=source, schedule_id=schedule_id)
        for video in video_files
    ]


def _run_task(task: dict) -> None:
    batch_id = str(task.get("batch_id") or task["id"])
    try:
        concurrency = max(1, min(32, int(task.get("task_concurrency", 1))))
    except (TypeError, ValueError):
        concurrency = 1
    acquired_slot = False
    with _queue_condition:
        while _batch_running.get(batch_id, 0) >= concurrency:
            if task["id"] in _deleted_tasks:
                _deleted_tasks.discard(task["id"])
                return
            if task["id"] in _cancelled_tasks:
                _cancelled_tasks.discard(task["id"])
                return
            _queue_condition.wait()
        if task["id"] in _deleted_tasks:
            _deleted_tasks.discard(task["id"])
            return
        if task["id"] in _cancelled_tasks:
            _cancelled_tasks.discard(task["id"])
            return
        _batch_running[batch_id] = _batch_running.get(batch_id, 0) + 1
        acquired_slot = True
    task["status"] = "running"
    task["started_at"] = now_iso()
    _persist(task)
    command = [sys.executable, "--run-javsp", "-c", task["config_path"]] if IS_FROZEN else [sys.executable, "-m", "javsp", "-c", task["config_path"]]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(VENDOR_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    # The embedded worker reports structured events; terminal tqdm redraws are disabled.
    env["JAVSP_PROGRESS"] = "1"
    try:
        # Keep process creation and cancellation registration atomic so a queued
        # task cannot start after it has been cancelled.
        with _lock:
            if task["id"] in _cancelled_tasks:
                return
            process = subprocess.Popen(
                command,
                cwd=str(VENDOR_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
            )
            _processes[task["id"]] = process
        assert process.stdout is not None
        for raw_line in process.stdout:
            decoded = _decode_output(raw_line)
            segments = decoded.split("\r")
            line = next((part for part in reversed(segments) if part.strip()), "").rstrip("\n")
            if not line:
                continue
            logs = _logs.setdefault(task["id"], [])
            if logs and logs[-1] == line:
                continue
            logs.append(line)
            _logs[task["id"]] = _clean_log_lines(logs)[-_MAX_LOG_LINES:]
            task["log_tail"] = _logs[task["id"]]
            task["progress"] = _progress_from_logs(task["log_tail"])
            if len(logs) % 20 == 0:
                _persist(task)
        code = process.wait()
        task["return_code"] = code
        cancelled = task["id"] in _cancelled_tasks or task.get("status") == "cancelled"
        task["status"] = "cancelled" if cancelled else ("succeeded" if code == 0 else "failed")
        if cancelled:
            task["error"] = None
            _logs.setdefault(task["id"], []).append("任务已停止")
        elif code == 0:
            _logs.setdefault(task["id"], []).append("JavSP 执行完成")
        else:
            task["error"] = f"JavSP 退出码: {code}"
            _logs.setdefault(task["id"], []).append(f"JavSP 执行失败，退出码: {code}")
    except Exception as exc:  # noqa: BLE001
        task["status"] = "failed"
        task["error"] = str(exc)
        _logs.setdefault(task["id"], []).append(f"启动失败: {exc}")
    finally:
        task["finished_at"] = now_iso()
        task["log_tail"] = _clean_log_lines(_logs.get(task["id"], []))[-_MAX_LOG_LINES:]
        task["progress"] = _progress_from_logs(task["log_tail"])
        _processes.pop(task["id"], None)
        _cancelled_tasks.discard(task["id"])
        _persist(task)
        if task.get("status") == "succeeded":
            try:
                from .media import auto_sync_media_servers

                threading.Thread(target=auto_sync_media_servers, name=f"media-sync-{task['id']}", daemon=True).start()
            except ImportError:
                pass
        if acquired_slot:
            with _queue_condition:
                remaining = _batch_running.get(batch_id, 1) - 1
                if remaining > 0:
                    _batch_running[batch_id] = remaining
                else:
                    _batch_running.pop(batch_id, None)
                _queue_condition.notify_all()


def _append_task_event(task: dict, stage: str, **payload: object) -> None:
    line = "JAVSP_PROGRESS " + json.dumps({"stage": stage, **payload}, ensure_ascii=False, separators=(",", ":"))
    logs = _logs.setdefault(task["id"], list(task.get("log_tail") or []))
    logs.append(line)
    _logs[task["id"]] = _clean_log_lines(logs)[-_MAX_LOG_LINES:]
    task["log_tail"] = _logs[task["id"]]
    task["progress"] = _progress_from_logs(task["log_tail"])


def _download_retry_image(url: str, destination: Path) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError("图片地址无效")
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "JavSP-WEB/0.1", "Referer": url[:url.find("/", 8) + 1]}
    response = requests.get(url, headers=headers, timeout=45, stream=True)
    response.raise_for_status()
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with temporary.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    file.write(chunk)
        with Image.open(temporary) as image:
            image.verify()
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _rebuild_retry_poster(fanart_file: Path, poster_file: Path) -> None:
    with Image.open(fanart_file) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        target_width = min(image.width, max(1, round(image.height * 2 / 3)))
        left = max(0, (image.width - target_width) // 2)
        poster = image.crop((left, 0, left + target_width, image.height))
        poster_file.parent.mkdir(parents=True, exist_ok=True)
        poster.save(poster_file)


def _retry_task_images(task: dict, progress: dict) -> None:
    errors: list[str] = []
    sources = progress["image_sources"]
    output = progress["output"]
    cover_urls = [str(url) for url in sources.get("cover_urls", []) if url]
    preview_pics = [str(url) for url in sources.get("preview_pics", []) if url]
    fanart_file = Path(output["fanart_file"])
    poster_file = Path(output.get("poster_file") or fanart_file.with_name("poster" + fanart_file.suffix))
    save_dir = Path(output.get("save_dir") or fanart_file.parent)
    try:
        _append_task_event(task, "image_retry", status="running")
        cover_downloaded = not cover_urls
        cover_errors: list[str] = []
        if cover_urls:
            _append_task_event(task, "images", kind="cover", done=0, total=1, status="downloading")
            for url in cover_urls:
                try:
                    _download_retry_image(url, fanart_file)
                    _rebuild_retry_poster(fanart_file, poster_file)
                    cover_downloaded = True
                    _append_task_event(task, "images", kind="cover", done=1, total=1, status="completed")
                    break
                except Exception as exc:  # noqa: BLE001
                    cover_errors.append(f"封面：{exc}")
            if not cover_downloaded:
                errors.extend(cover_errors or ["封面：未能下载有效封面"])
                _append_task_event(task, "images", kind="cover", done=0, total=1, status="failed", error=cover_errors[-1] if cover_errors else "未能下载有效封面")

        fanart_dir = save_dir / "extrafanart"
        fanart_done = 0
        for index, url in enumerate(preview_pics):
            _append_task_event(task, "images", kind="fanart", done=fanart_done, total=len(preview_pics), status="downloading", current=index + 1)
            try:
                _download_retry_image(url, fanart_dir / f"{index}.png")
                fanart_done += 1
                _append_task_event(task, "images", kind="fanart", done=fanart_done, total=len(preview_pics), status="completed", current=index + 1)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"剧照 {index + 1}：{exc}")
                _append_task_event(task, "images", kind="fanart", done=fanart_done, total=len(preview_pics), status="failed", current=index + 1, error=str(exc))

        if errors:
            _append_task_event(task, "image_retry", status="failed", error="；".join(errors[-3:]))
        else:
            _append_task_event(task, "image_retry", status="completed")
    except Exception as exc:  # noqa: BLE001
        _append_task_event(task, "image_retry", status="failed", error=str(exc))
    finally:
        task["image_retry_running"] = False
        task["image_retry_finished_at"] = now_iso()
        _persist(task)


def retry_task_images(task_id: str) -> bool:
    with _lock:
        task = next((item for item in load_tasks() if item.get("id") == task_id), None)
        if not task or task.get("status") == "running" or task.get("image_retry_running"):
            return False
        raw_logs = _clean_log_lines((_logs.get(task_id) or task.get("log_tail") or [])[-_MAX_LOG_LINES:])
        progress = _progress_from_logs(raw_logs)
        sources = progress["image_sources"]
        output = progress["output"]
        has_image_source = bool(sources.get("cover_urls") or sources.get("preview_pics"))
        if not (has_image_source and output.get("fanart_file")):
            return False
        task["image_retry_running"] = True
        _logs[task_id] = raw_logs
        _persist(task)
    threading.Thread(target=_retry_task_images, args=(task, progress), name=f"image-retry-{task_id}", daemon=True).start()
    return True


def cancel_task(task_id: str) -> bool:
    with _queue_condition:
        task = get_task(task_id)
        if not task or task.get("status") not in {"queued", "running"}:
            return False
        _cancelled_tasks.add(task_id)
        process = _processes.get(task_id)
        if process and process.poll() is None:
            process.terminate()
        task["status"] = "cancelled"
        task["finished_at"] = now_iso()
        task["error"] = None
        _logs.setdefault(task_id, list(task.get("log_tail") or [])).append("任务已停止")
        task["log_tail"] = _clean_log_lines(_logs[task_id])[-_MAX_LOG_LINES:]
        _persist(task)
        _queue_condition.notify_all()
        return True


def recover_interrupted_tasks() -> int:
    """Mark tasks left running by a previous service process as cancelled."""
    with _queue_condition:
        tasks = load_tasks()
        changed = 0
        for task in tasks:
            if task.get("status") != "running":
                continue
            task["status"] = "cancelled"
            task["finished_at"] = now_iso()
            task["error"] = "服务重启后任务已中止"
            logs = _logs.setdefault(str(task.get("id") or ""), list(task.get("log_tail") or []))
            logs.append("服务重启，任务已中止")
            task["log_tail"] = _clean_log_lines(logs)[-_MAX_LOG_LINES:]
            changed += 1
        if changed:
            save_tasks(tasks)
            _queue_condition.notify_all()
        return changed


def delete_task(task_id: str) -> bool:
    with _lock:
        if task_id in _processes:
            return False
        tasks = load_tasks()
        task = next((item for item in tasks if item.get("id") == task_id), None)
        if not task or task.get("status") == "running":
            return False
        if task.get("status") == "queued":
            _deleted_tasks.add(task_id)
        save_tasks([item for item in tasks if item.get("id") != task_id])
        _logs.pop(task_id, None)
        config_path = task.get("config_path")
        if config_path:
            try:
                path = Path(config_path).resolve()
                folder = (DATA_DIR / "task-config").resolve()
                if path.parent == folder:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        return True


def clean_task_configs() -> None:
    folder = DATA_DIR / "task-config"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
