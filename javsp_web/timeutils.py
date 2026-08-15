from __future__ import annotations

import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 packaged builds
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Shanghai"


def timezone_name() -> str:
    return os.environ.get("JAVSP_WEB_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE


def local_now() -> datetime:
    try:
        zone = ZoneInfo(timezone_name())
    except ZoneInfoNotFoundError:
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.now(zone)


def now_iso() -> str:
    return local_now().isoformat()
