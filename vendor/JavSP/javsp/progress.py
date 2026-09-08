"""Machine-readable progress events for non-interactive integrations."""

from __future__ import annotations

import json
import os
import sys
import threading


EVENT_PREFIX = "JAVSP_PROGRESS "
_output_lock = threading.Lock()


def enabled() -> bool:
    """Return whether the caller requested Web/control-plane progress output."""
    return os.environ.get("JAVSP_PROGRESS", "").strip().lower() in {"1", "true", "yes", "on"}


def emit(stage: str, **payload: object) -> None:
    """Write one newline-delimited event without affecting normal CLI output."""
    if not enabled():
        return
    line = EVENT_PREFIX + json.dumps({"stage": stage, **payload}, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _output_lock:
        sys.stdout.write(line)
        sys.stdout.flush()
