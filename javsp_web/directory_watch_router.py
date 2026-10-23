"""管理员 API：目录监控规则、运行状态与手动扫描。

All scan work happens outside the request's event loop (``def`` endpoints run in
the thread pool) and never under the task worker lock: the module only calls the
existing ``create_tasks`` queue API.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import directory_watch
from .auth import require_admin

router = APIRouter(prefix="/api/directory-watch", dependencies=[Depends(require_admin)])


class DirectoryWatchRuleBody(BaseModel):
    name: str = Field(default="", max_length=80)
    enabled: bool = True
    trigger: str = Field(default="watch", max_length=16)
    cron: str = Field(default="", max_length=128)
    path: str = Field(default="", max_length=2048)
    preset_id: str = Field(default="default", max_length=64)
    recursive: bool = True
    exclude: list[str] = Field(default_factory=list, max_length=directory_watch.MAX_EXCLUDE_PATTERNS)
    include_existing: bool = False
    poll_seconds: int | None = None
    stable_seconds: int | None = None
    max_tasks_per_scan: int | None = None


def _payload(body: DirectoryWatchRuleBody) -> dict:
    # Only send what the caller set, so PUT stays a partial update.
    return body.model_dump(exclude_unset=True)


def _require_rule(rule_id: str) -> dict:
    rule = directory_watch.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录监控规则不存在")
    return rule


@router.get("/rules")
def list_directory_watch_rules(_: dict = Depends(require_admin)) -> dict:
    return {
        "rules": directory_watch.list_rule_reports(),
        "limits": directory_watch.limits(),
        "scheduler": directory_watch.scheduler_state(),
    }


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_directory_watch_rule(body: DirectoryWatchRuleBody, _: dict = Depends(require_admin)) -> dict:
    try:
        rule = directory_watch.create_rule(_payload(body))
    except directory_watch.RuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return directory_watch.rule_report(rule["id"]) or rule


@router.put("/rules/{rule_id}")
def update_directory_watch_rule(rule_id: str, body: DirectoryWatchRuleBody, _: dict = Depends(require_admin)) -> dict:
    _require_rule(rule_id)
    try:
        rule = directory_watch.update_rule(rule_id, _payload(body))
    except directory_watch.RuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return directory_watch.rule_report(rule["id"]) or rule


@router.delete("/rules/{rule_id}")
def delete_directory_watch_rule(rule_id: str, _: dict = Depends(require_admin)) -> dict:
    if not directory_watch.delete_rule(rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录监控规则不存在")
    return {"ok": True}


@router.post("/rules/{rule_id}/pause")
def pause_directory_watch_rule(rule_id: str, _: dict = Depends(require_admin)) -> dict:
    return _set_enabled(rule_id, False)


@router.post("/rules/{rule_id}/resume")
def resume_directory_watch_rule(rule_id: str, _: dict = Depends(require_admin)) -> dict:
    return _set_enabled(rule_id, True)


def _set_enabled(rule_id: str, enabled: bool) -> dict:
    _require_rule(rule_id)
    try:
        rule = directory_watch.set_rule_enabled(rule_id, enabled)
    except directory_watch.RuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return directory_watch.rule_report(rule["id"]) or rule


@router.post("/rules/{rule_id}/scan")
def scan_directory_watch_rule(rule_id: str, _: dict = Depends(require_admin)) -> dict:
    rule = _require_rule(rule_id)
    try:
        if rule.get("trigger") == "schedule":
            result = directory_watch.run_schedule_rule(rule_id, "manual-" + uuid.uuid4().hex)
        else:
            result = directory_watch.scan_rule(rule_id)
    except directory_watch.RuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {**result, "rule": directory_watch.rule_report(rule_id)}


@router.post("/rules/{rule_id}/reset")
def reset_directory_watch_rule(rule_id: str, _: dict = Depends(require_admin)) -> dict:
    existing = _require_rule(rule_id)
    if existing.get("trigger") == "schedule":
        raise HTTPException(status_code=400, detail="定时规则不使用观察台账")
    try:
        rule = directory_watch.reset_rule_state(rule_id)
    except directory_watch.RuleError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return directory_watch.rule_report(rule["id"]) or rule
