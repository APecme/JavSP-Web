from __future__ import annotations

import sys
from typing import Any

import yaml

from .storage import VENDOR_DIR, read_config


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_base_config() -> dict:
    defaults = {}
    try:
        defaults = yaml.safe_load((VENDOR_DIR / "config.yml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        pass
    try:
        local = yaml.safe_load(read_config()) or {}
    except yaml.YAMLError:
        local = {}
    return _merge(defaults if isinstance(defaults, dict) else {}, local if isinstance(local, dict) else {})


def validate_config_data(data: Any) -> None:
    """Validate a merged JavSP config with the embedded project's own model."""
    if not isinstance(data, dict):
        raise ValueError("配置根节点必须是对象")
    vendor_path = str(VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    try:
        from javsp.config import Cfg
        from pydantic import ValidationError

        Cfg.model_validate(data)
    except ValidationError as exc:
        details = []
        field_labels = {"network": "网络", "proxy_server": "代理服务器", "proxy_free": "免代理站点", "retry": "重试次数", "timeout": "请求超时"}
        for error in exc.errors():
            parts = [str(part) for part in error.get("loc", ())]
            location = " / ".join(field_labels.get(part, part) for part in parts) or "配置"
            message = "请输入完整的网址，例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:7890" if error.get("type") == "url_parsing" else error.get("msg", "值无效")
            details.append(f"{location}: {message}")
        raise ValueError("配置校验失败: " + "; ".join(details)) from exc
    except (ImportError, ModuleNotFoundError) as exc:
        raise ValueError(f"无法加载 JavSP 配置模型: {exc}") from exc
