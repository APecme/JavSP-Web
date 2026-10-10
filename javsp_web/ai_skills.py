from __future__ import annotations

from pathlib import Path
import re
import threading

import yaml

from . import storage
from .ai import AIError


SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_lock = threading.RLock()


def _settings():
    return storage._read_json(storage.DATA_DIR / "ai-skills.json", {"custom": {}, "disabled": []})


def _metadata(source):
    parts = re.fullmatch(r"---\n(.*?)\n---\n(.*)", source, re.S)
    if not parts:
        raise AIError("Skill 需要包含 name、description 的 YAML 头部")
    try:
        metadata = yaml.safe_load(parts.group(1))
    except yaml.YAMLError as exc:
        raise AIError("Skill 的 YAML 头部格式错误") from exc
    if not isinstance(metadata, dict) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", str(metadata.get("name", ""))):
        raise AIError("Skill 名称仅支持小写字母、数字和连字符，最多 64 个字符")
    description = metadata.get("description")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise AIError("请提供 1 至 1024 字符的 Skill 描述")
    if not parts.group(2).strip():
        raise AIError("Skill 正文不能为空")
    return {"name": metadata["name"], "description": description.strip()}


def catalog():
    with _lock:
        settings = _settings()
        items = {}
        for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            if path.parent.name not in settings["disabled"]:
                source = path.read_text(encoding="utf-8")
                items[path.parent.name] = _metadata(source) | {"source": source, "kind": "built-in"}
        for name, source in settings["custom"].items():
            items[name] = _metadata(source) | {"source": source, "kind": "custom"}
        return list(items.values())


def read(name):
    item = next((item for item in catalog() if item["name"] == name), None)
    if not item:
        raise AIError("Skill 不存在或已删除")
    return item


def save(source):
    source = source.replace("\r\n", "\n").strip() + "\n"
    metadata = _metadata(source)
    with _lock:
        settings = _settings()
        settings["custom"][metadata["name"]] = source
        if len(settings["custom"]) > 30 or sum(len(value) for value in settings["custom"].values()) > 200000:
            raise AIError("自定义 Skills 最多 30 项，总内容不能超过 200000 字符")
        storage._write_json(storage.DATA_DIR / "ai-skills.json", settings)
    return read(metadata["name"])


def delete(name):
    read(name)
    with _lock:
        settings = _settings()
        settings["custom"].pop(name, None)
        if name not in settings["disabled"]:
            settings["disabled"].append(name)
        storage._write_json(storage.DATA_DIR / "ai-skills.json", settings)


def restore_defaults():
    with _lock:
        settings = _settings()
        settings["disabled"] = []
        storage._write_json(storage.DATA_DIR / "ai-skills.json", settings)
