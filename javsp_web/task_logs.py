"""Readable task logs, derived from events without changing stored diagnostics."""
from __future__ import annotations

import json
import re


def readable_error(value: object) -> str:
    text = str(value or "未知错误").strip()
    if "CERTIFICATE_VERIFY_FAILED" in text or "certificate verify failed" in text:
        return "HTTPS 证书验证失败，请检查系统 CA、代理证书及站点证书链"
    if "403" in text or "Forbidden" in text:
        return "站点拒绝访问（403），请检查代理出口及该域名的 CookieCloud 登录状态"
    if "401" in text:
        return "站点要求登录，请检查该域名的 CookieCloud 登录状态"
    if "429" in text:
        return "请求过于频繁，请稍后重试"
    if "list index out of range" in text or "IndexError" in text:
        return "页面缺少预期字段，可能是页面结构变化或返回了验证页"
    if "未找到影片" in text:
        return "未找到匹配影片"
    if "个抓取器均未获取到影片信息" in text or text == "抓取器均未获取到影片信息":
        return "所有数据源均未取得影片信息，请查看站点结果"
    if "timed out" in text.lower() or "Timeout" in text:
        return "连接或读取超时，请检查网络后重试"
    # URLs in errors may contain query credentials. Source links belong to metadata.
    text = re.sub(r"https?://\S+", "[站点地址]", text)
    return re.sub(r"\s+", " ", text)[:260]


def build_log_entries(lines: list[str], status: str = "", error: str = "", image_retry_running: bool = False) -> list[dict]:
    entries: dict[str, dict] = {}
    scope = "0"
    failures: set[int] = set()
    structured = any("JAVSP_PROGRESS " in line for line in lines)
    traceback = False

    def put(key, group, message, level="info", detail=""):
        entries[f"{scope}:{key}"] = dict(group=group, message=message, level=level, detail=detail)

    for raw in lines:
        line = raw.strip()
        marker = line.find("JAVSP_PROGRESS ")
        if marker >= 0:
            traceback = False
            try:
                event = json.loads(line[marker + 15:])
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            stage, state = event.get("stage"), event.get("status")
            if stage == "notice":
                put("notice:" + str(event.get("message")), "notes", readable_error(event.get("message")), "info")
            elif stage == "movie" and state == "running":
                scope = str(event.get("index", len(entries)))
                failures = set()
                put("movie", "process", f"刮削影片 {event.get('index', 1)}/{event.get('total', 1)}")
            elif stage == "scan":
                put("scan", "process", "正在扫描影片" if state == "running" else f"扫描完成 · {event.get('total', 0)} 部影片", "running" if state == "running" else "success")
            elif stage == "metadata":
                title = event.get("title")
                put("metadata", "process", f"{event.get('dvdid') or '影片'}" + (f" · {title}" if title else " · 已识别番号"), "success" if title else "info")
            elif stage == "crawler":
                name = str(event.get("name") or "").removeprefix("javsp.web.")
                labels = {"running": "抓取中", "success": "已取得资料", "failed": "失败", "not_found": "未找到", "duplicate": "存在多个匹配结果", "retrying": "正在重试"}
                level = {"running": "running", "retrying": "running", "success": "success", "failed": "warning", "not_found": "muted", "duplicate": "warning"}.get(state, "info")
                detail = readable_error(event["reason"]) if event.get("reason") and state != "not_found" else ""
                if state == "retrying":
                    detail = f"第 {event.get('attempt', 1)} 次重试 · {detail}"
                put(f"crawler:{name}", "sources", f"{name} · {labels.get(state, '抓取中')}", level, detail)
            elif stage == "summary":
                put("summary", "process", "资料汇总完成" if event.get("done") else "正在汇总资料", "success" if event.get("done") else "running")
            elif stage == "images":
                kind = event.get("kind")
                done, total = int(event.get("done") or 0), int(event.get("total") or 0)
                if kind == "cover":
                    put("cover", "images", "封面下载失败" if state == "failed" else "封面已下载" if done else "正在下载封面", "warning" if state == "failed" else "success" if done else "running", readable_error(event.get("error")) if state == "failed" else "")
                elif kind == "fanart":
                    current = int(event.get("current") or 0)
                    if state == "failed":
                        failures.add(current)
                        put(f"fanart-error:{current}", "images", f"第 {current} 张剧照下载失败", "warning", readable_error(event.get("error")))
                    elif state == "completed":
                        failures.discard(current)
                        entries.pop(f"{scope}:fanart-error:{current}", None)
                    downloaded = max(0, done - sum(1 for index in failures if index <= done))
                    put("fanart", "images", f"剧照 · 已下载 {downloaded}/{total}" + (f" · {len(failures)} 张失败" if failures else ""), "warning" if failures else "success" if done == total else "running")
            elif stage == "image_retry":
                if state == "running":
                    scope += ":retry"
                    failures = set()
                put("image-retry", "images", {"running": "正在重新下载图片", "completed": "图片重新下载完成", "failed": "图片重新下载失败"}.get(state, "重新下载图片"), "warning" if state == "failed" else "success" if state == "completed" else "running", readable_error(event.get("error")) if event.get("error") else "")
            elif stage == "movie" and state in {"failed", "completed"}:
                put("movie-result", "result", "影片刮削失败" if state == "failed" else "影片刮削完成", "error" if state == "failed" else "success", readable_error(event.get("error")) if state == "failed" else "")
            elif stage == "task":
                put("task-result", "result", f"任务完成 · 共处理 {event.get('total', 0)} 部影片", "success")
            continue
        if not line or re.fullmatch(r"[=\-~^\s]+", line) or line.startswith("# Jav Scraper Package"):
            continue
        if line.startswith("Traceback (most recent call last)") or line.startswith('File "'):
            traceback = True
            continue
        if traceback:
            if re.match(r"\w*(Error|Exception):", line):
                traceback = False
            continue
        if re.match(r'(File "|\w*(Error|Exception):|list index out of range)', line):
            continue
        if structured and (re.match(r"^(开始扫描|扫描影片文件|扫描完成|开始刮削|已取得影片信息|开始汇总|影片数据汇总|开始下载|封面下载完成|剧照下载进度|已下载剧照|影片刮削完成|影片刮削失败|全部任务完成|JavSP 执行完成|\d+ 部影片刮削失败|抓取器均未获取到影片信息)", line) or re.match(r"^(?:javsp\.web\.)?[\w]+:\s*(?:开始抓取|抓取完成|抓取失败|网络异常|未找到影片)", line)):
            continue
        # Unknown warnings and user actions remain visible and are deduplicated.
        put("text:" + line, "notes", readable_error(line), "warning" if any(word in line for word in ("失败", "无法", "异常", "错误")) else "info")

    if status in {"succeeded", "failed", "cancelled"}:
        # One task outcome, while retaining per-film failures in multi-film tasks.
        movie_count = sum(key.endswith(":movie") for key in entries)
        for key in list(entries):
            if key.endswith(":task-result") or (key.endswith(":movie-result") and (movie_count <= 1 or entries[key]["level"] == "success")):
                del entries[key]
        put("task-result", "result", {"succeeded": "任务完成", "failed": "任务失败", "cancelled": "任务已停止"}[status], {"succeeded": "success", "failed": "error", "cancelled": "muted"}[status], readable_error(error) if error and status == "failed" else "")
        for entry in entries.values():
            if entry["level"] == "running" and not (image_retry_running and entry['group'] == 'images'):
                entry.update(level="muted", detail="任务已结束，未收到此步骤的完成结果")
    return list(entries.values())


def log_text(entries: list[dict]) -> list[str]:
    return [entry["message"] + ("：" + entry["detail"] if entry.get("detail") else "") for entry in entries]
