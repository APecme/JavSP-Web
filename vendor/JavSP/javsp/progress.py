"""Machine-readable progress events for non-interactive integrations."""

from __future__ import annotations

import json
import os


EVENT_PREFIX = "JAVSP_PROGRESS "


def enabled() -> bool:
    """Return whether the caller requested Web/control-plane progress output."""
    return os.environ.get("JAVSP_PROGRESS", "").strip().lower() in {"1", "true", "yes", "on"}


def emit(stage: str, **payload: object) -> None:
    """Write one newline-delimited event without affecting normal CLI output."""
    if not enabled():
        return
    print(EVENT_PREFIX + json.dumps({"stage": stage, **payload}, ensure_ascii=False, separators=(",", ":")), flush=True)
