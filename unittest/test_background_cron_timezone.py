from datetime import datetime, timezone

from javsp.webapp.tasks import _compute_next_run


def test_compute_next_run_uses_local_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    base_dt = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)

    next_run = _compute_next_run("10 0 * * *", base_dt)

    assert next_run == "2025-01-01T16:10:00+00:00"


def test_compute_next_run_respects_utc_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    base_dt = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)

    next_run = _compute_next_run("10 0 * * *", base_dt)

    assert next_run == "2025-01-02T00:10:00+00:00"
