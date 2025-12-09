from pathlib import Path
import json
from typing import Dict

from javsp.lib import resource_path

# 将密码文件保存到 data 目录，确保在 Docker 容器重建时能够持久化
SETTINGS_FILE = Path(resource_path("data/web_settings.json"))
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def load_web_settings() -> Dict[str, str]:
    # 确保目录存在
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        return {"username": DEFAULT_USERNAME, "password": DEFAULT_PASSWORD}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"username": DEFAULT_USERNAME, "password": DEFAULT_PASSWORD}
    username = data.get("username") or DEFAULT_USERNAME
    password = data.get("password") or DEFAULT_PASSWORD
    return {"username": username, "password": password}


def save_web_settings(username: str, password: str) -> None:
    # 确保目录存在
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"username": username, "password": password}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
