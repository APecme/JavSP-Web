import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from confz import validate_all_configs

from javsp.config import Cfg
from javsp.lib import resource_path
from .auth import get_current_user, UserInfo


router = APIRouter(prefix="/rules", tags=["rules"])


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_update(dict(base[key]), value)
        else:
            base[key] = value
    return base


@router.get("/global")
async def get_global_rules(
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    cfg = Cfg()
    try:
        data = cfg.model_dump()  # type: ignore[attr-defined]
    except AttributeError:
        # 兼容旧版 pydantic/confz
        data = cfg.dict()  # type: ignore[no-any-return]
    return data


@router.put("/global", status_code=status.HTTP_200_OK)
async def update_global_rules(
    payload: Dict[str, Any],
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, str]:
    try:
        cfg = Cfg()
        try:
            current = cfg.model_dump()  # type: ignore[attr-defined]
        except AttributeError:
            # 兼容旧版 pydantic/confz
            current = cfg.dict()  # type: ignore[no-any-return]
        merged = _deep_update(current, payload)
        try:
            validated = Cfg.model_validate(merged)  # type: ignore[attr-defined]
        except AttributeError:
            # 兼容旧版 Pydantic / ConfZ，退回到 parse_obj
            validated = Cfg.parse_obj(merged)  # type: ignore[no-untyped-call]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    cfg_path = Path(resource_path("data/config.yml"))
    try:
        try:
            # 使用 Pydantic v2 的 JSON 模式导出，确保 Duration 等类型可序列化
            data = validated.model_dump(mode="json")  # type: ignore[attr-defined]
            body = json.dumps(data, ensure_ascii=False, indent=2)
        except AttributeError:
            # 兼容 Pydantic v1：直接使用 .json() 导出为 JSON 字符串
            body = validated.json(ensure_ascii=False, indent=2)  # type: ignore[no-untyped-call]
        cfg_path.write_text(body + "\n", encoding="utf-8")
    except OSError as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 写入成功后，通过 ConfZ 强制重新加载全部配置单例，确保 Cfg() 使用最新的配置源
    try:
        validate_all_configs(force_reload=True)
    except Exception:
        # 出现异常时忽略内存重载失败，磁盘上的配置已写入，不影响后续进程重启后的加载
        pass

    return {"status": "ok"}
