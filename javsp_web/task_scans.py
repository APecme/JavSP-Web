"""Persisted scan jobs: never inspect a media mount in the submission request."""
from __future__ import annotations

from pathlib import Path
import os
import time
import uuid

from .timeutils import now_iso


class ScanCancelled(Exception):
    pass


def submit_scan(input_directory: str, preset_id: str = "default", input_files: list[str] | None = None) -> dict:
    from . import tasks

    # abspath is lexical; exists/is_file/resolve may block on network mounts.
    paths = input_files if input_files is not None else [input_directory]
    if not paths or any(not isinstance(path, str) or not path.strip() or "\0" in path for path in paths):
        raise ValueError("请选择目录或视频文件")
    paths = list(dict.fromkeys(os.path.abspath(os.path.expanduser(path.strip())) for path in paths))
    task_id = uuid.uuid4().hex[:12]
    name = f"扫描：{len(paths)} 个所选文件" if input_files is not None else f"扫描：{Path(paths[0]).name or paths[0]}"
    task = {
        "id": task_id, "task_type": "scan", "name": name, "file_name": name,
        "input_directory": paths[0], "input_files": paths if input_files is not None else None,
        "preset_id": preset_id, "preset_name": preset_id, "source": "manual",
        "status": "queued", "created_at": now_iso(), "started_at": None, "finished_at": None,
        "batch_id": task_id, "task_concurrency": 1, "size_bytes": 0, "error": None,
        "scan": {"discovered_files": 0, "created_tasks": 0, "message": "等待后台扫描；挂载盘响应较慢时请勿重复提交"},
        "log_tail": ["已接收扫描请求，等待后台读取目录或所选文件"],
    }
    tasks._persist(task)
    tasks._enqueue_task(task)
    return task


def decorate_scan(task: dict) -> dict:
    """Scan polling/cancellation must not stat the path that is being scanned."""
    task.update(title="", cover_count=0, fanart_count=0, image_retry_available=False,
                restore_available=False, progress={}, log_entries=[])
    return task


def discard_prepared(prepared: list[dict]) -> None:
    from . import tasks
    for task in prepared:
        tasks._logs.pop(task["id"], None)
        try:
            Path(task["config_path"]).unlink(missing_ok=True)
        except OSError:
            pass


def run_scan(task: dict) -> None:
    from . import tasks
    from .task_store import upsert_many

    task_id = task["id"]
    prepared = []
    committed = False
    last_progress = 0.0

    def check_cancelled():
        if task_id in tasks._cancelled_tasks or task_id in tasks._deleted_tasks:
            raise ScanCancelled()

    def progress(count, message):
        nonlocal last_progress
        with tasks._queue_condition:
            check_cancelled()
            now = time.monotonic()
            if now - last_progress < 0.5:
                return
            last_progress = now
            task["scan"].update(discovered_files=count, message=message)
            task["log_tail"] = (task.get("log_tail", []) + [message])[-200:]
            tasks._persist(task)

    try:
        with tasks._queue_condition:
            check_cancelled()
            task.update(status="running", started_at=now_iso())
            task["scan"].update(discovered_files=0, created_tasks=0, message="正在读取输入路径；网络挂载盘可能需要较长时间")
            tasks._persist(task)
        prepared = tasks._prepare_tasks(
            task["input_directory"], task["preset_id"], input_files=task.get("input_files"),
            batch_id=task_id, on_progress=progress,
        )
        # No mount I/O inside this lock. Cancellation and committing children
        # are mutually exclusive; restart sees either the scan or its children.
        with tasks._queue_condition:
            check_cancelled()
            count = len(prepared)
            message = f"扫描完成，已创建 {count} 个影片任务（分 P 文件已合并）"
            task.update(status="succeeded", finished_at=now_iso())
            task["scan"].update(created_tasks=count, discovered_files=sum(len(t.get("input_files") or [t["input_directory"]]) for t in prepared), message=message)
            task["log_tail"].append(message)
            upsert_many([*prepared, task])
            committed = True
            for child in prepared:
                tasks._enqueue_task(child)
    except ScanCancelled:
        # cancel_task has already persisted the cancellation. Never recreate
        # a cancelled scan that the user deleted while mount I/O was blocked.
        pass
    except Exception as exc:
        with tasks._queue_condition:
            if task_id not in tasks._cancelled_tasks and task_id not in tasks._deleted_tasks:
                message = f"扫描失败：{exc}"
                task.update(status="failed", finished_at=now_iso(), error=message)
                task["scan"]["message"] = message
                task["log_tail"].append(message)
                tasks._persist(task)
    finally:
        if not committed:
            discard_prepared(prepared)
        with tasks._queue_condition:
            tasks._cancelled_tasks.discard(task_id)
            tasks._deleted_tasks.discard(task_id)
