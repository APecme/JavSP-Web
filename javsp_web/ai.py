from __future__ import annotations

import json
import re
import threading
import time
from typing import Literal
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import storage


class AIError(ValueError):
    pass


class AISettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    provider: Literal["openai", "compatible", "deepseek", "ollama", "anthropic"] = "compatible"
    base_url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False
    timeout: int = Field(default=60, ge=10, le=120)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip().rstrip("/")
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("LLM URL 必须是无账号、查询参数的 HTTP(S) API 基础地址")
        return value

    @field_validator("model")
    @classmethod
    def trim_model(cls, value):
        return value.strip()


_settings_lock = threading.RLock()


def settings(include_key=False):
    with _settings_lock:
        saved = storage._read_json(storage.DATA_DIR / "ai-settings.json", {})
        result = AISettings().model_dump() | saved
    result.pop("clear_api_key", None)
    if not include_key:
        result["has_api_key"] = bool(result.pop("api_key", None))
    return result


def merge_settings(body: AISettings):
    merged = settings(True) | body.model_dump(exclude={"api_key", "clear_api_key"})
    if body.clear_api_key:
        merged["api_key"] = ""
    elif body.api_key and body.api_key.strip():
        merged["api_key"] = body.api_key.strip()
    return merged


def validate_connection(config):
    if not config["base_url"] or not config["model"]:
        raise AIError("请填写 LLM URL 和模型名称")
    if config["provider"] not in ("ollama", "compatible") and not config.get("api_key"):
        raise AIError("请填写 API KEY")


def save_settings(body):
    with _settings_lock:
        merged = merge_settings(body)
        if merged["enabled"]:
            validate_connection(merged)
        storage._write_json(storage.DATA_DIR / "ai-settings.json", merged)
        return settings()


def redact(value, secret=""):
    if isinstance(value, dict):
        return {key: "[已隐藏]" if re.search(r"password|passwd|api.?key|token|cookie|authorization|secret", key, re.I)
                else redact(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, str):
        if secret:
            value = value.replace(secret, "[已隐藏]")
        value = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[已隐藏]@", value)
        value = re.sub(r"(?i)((?:api[_-]?key|password|token|secret|authorization)\s*['\"]?\s*[:=]\s*['\"]?)[^\s'\"&,;]+", r"\1[已隐藏]", value)
        return value
    return value


def _anthropic_messages(messages):
    converted = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "tool":
            role = "user"
            content = [{"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]}]
        else:
            content = [{"type": "text", "text": message["content"]}] if message.get("content") else []
            for call in message.get("tool_calls", []):
                content.append({"type": "tool_use", "id": call["id"], "name": call["function"]["name"],
                                "input": json.loads(call["function"]["arguments"])})
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"].extend(content)
        else:
            converted.append({"role": role, "content": content})
    return converted


def complete(config, messages, tools=None):
    validate_connection(config)
    anthropic = config["provider"] == "anthropic"
    suffix = "/messages" if anthropic else "/chat/completions"
    base = config["base_url"].rstrip("/")
    if base.endswith(suffix):
        endpoint = base
    else:
        endpoint = base + suffix
    headers = {"Content-Type": "application/json"}
    if anthropic:
        headers.update({"x-api-key": config.get("api_key", ""), "anthropic-version": "2023-06-01"})
        payload = {"model": config["model"], "max_tokens": 4096,
                   "system": "\n".join(item["content"] for item in messages if item["role"] == "system"),
                   "messages": _anthropic_messages(messages)}
        if tools:
            payload["tools"] = [{"name": tool["function"]["name"], "description": tool["function"]["description"],
                                 "input_schema": tool["function"]["parameters"]} for tool in tools]
    else:
        if config.get("api_key"):
            headers["Authorization"] = "Bearer " + config["api_key"]
        payload = {"model": config["model"], "messages": messages, "max_tokens": 4096, "stream": False}
        if tools:
            payload["tools"] = tools
    deadline = time.monotonic() + config["timeout"] + 10
    try:
        with requests.post(endpoint, headers=headers, json=payload, timeout=(10, config["timeout"]),
                           allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                reason = {401: "API KEY 无效", 403: "访问被拒绝", 404: "请检查 LLM URL 和模型名称",
                          429: "请求限流或额度不足"}.get(response.status_code, "请检查服务状态和模型是否支持工具调用")
                raise AIError(f"LLM 请求失败（HTTP {response.status_code}）：{reason}")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if time.monotonic() > deadline:
                    raise AIError("LLM 请求超时，请缩小请求范围后重试")
                if size > 2_000_000:
                    raise AIError("LLM 响应过大，请缩小请求范围")
                chunks.append(chunk)
            result = json.loads(b"".join(chunks))
        if anthropic:
            if result.get("stop_reason") == "max_tokens":
                raise AIError("模型输出被截断，请缩小请求范围后重试")
            content = result["content"]
            message = {"role": "assistant", "content": "\n".join(item["text"] for item in content if item["type"] == "text")}
            calls = [{"id": item["id"], "type": "function", "function": {"name": item["name"], "arguments": json.dumps(item["input"], ensure_ascii=False)}}
                     for item in content if item["type"] == "tool_use"]
        else:
            choice = result["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AIError("模型输出被截断，请缩小请求范围后重试")
            raw = choice["message"]
            message = {"role": "assistant", "content": raw.get("content") or ""}
            if isinstance(raw.get("reasoning_content"), str):
                message["reasoning_content"] = raw["reasoning_content"]
            calls = raw.get("tool_calls") or []
        if not isinstance(message["content"], str) or not isinstance(calls, list):
            raise AIError("LLM 返回的消息格式无效")
        if calls:
            for call in calls:
                if not isinstance(call["id"], str) or not isinstance(call["function"]["name"], str):
                    raise AIError("LLM 返回的工具调用格式无效")
                if not isinstance(json.loads(call["function"]["arguments"]), dict):
                    raise AIError("LLM 工具参数必须是对象")
            message["tool_calls"] = calls
        elif not message["content"].strip():
            raise AIError("LLM 未返回内容")
        return message
    except requests.Timeout as exc:
        raise AIError("LLM 请求超时，请检查网络或增加超时时间") from exc
    except requests.RequestException as exc:
        raise AIError("无法连接 LLM，请检查地址、网络和证书") from exc
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise AIError("LLM 响应格式不兼容，请选择支持工具调用的模型和正确的提供商协议") from exc
