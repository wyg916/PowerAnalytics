from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.api.v1.endpoints import forecast as forecast_endpoint
from backend.app.core import config
from backend.app.core.security import CurrentUser
from backend.app.schemas import ForecastRunRequest
from backend.app.workers import dispatcher


def test_celery_mode_requires_celery(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "celery")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "celery_available", lambda: False)
    try:
        try:
            dispatcher.enqueue_task("knowledge_import", {})
        except RuntimeError as exc:
            assert "TASK_EXECUTION_MODE=celery" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()


def test_auto_mode_requires_live_queue_without_creating_pending_record(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "auto")
    config.reset_settings_cache()
    saved: list[dict] = []
    monkeypatch.setattr(dispatcher, "celery_queue_available", lambda _queue: False)
    monkeypatch.setattr(
        dispatcher, "save_task_record", lambda *args, **kwargs: saved.append(kwargs) or True
    )
    try:
        with pytest.raises(RuntimeError, match="TASK_EXECUTION_MODE=auto"):
            dispatcher.enqueue_task("price_predict", {})
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert saved == []


def test_local_thread_mode_uses_specialized_thread(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "local_thread")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "celery_available", lambda: True)
    monkeypatch.setattr(dispatcher, "save_task_record", lambda *args, **kwargs: True)

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(dispatcher.threading, "Thread", FakeThread)
    try:
        result = dispatcher.enqueue_task("embedding_refresh", {})
        assert result["execution_mode"] == "local_thread"
        assert result["status"] == "pending"
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()


def test_celery_mode_rejects_missing_target_queue_before_record_creation(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "celery")
    monkeypatch.setenv("FORECAST_CELERY_QUEUE", "forecast_final_rc")
    config.reset_settings_cache()
    saved: list[dict] = []
    monkeypatch.setattr(dispatcher, "celery_queue_available", lambda queue: False)
    monkeypatch.setattr(
        dispatcher, "save_task_record", lambda *args, **kwargs: saved.append(kwargs) or True
    )
    try:
        with pytest.raises(RuntimeError, match="forecast_final_rc"):
            dispatcher.enqueue_task("today_analysis", {})
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        monkeypatch.delenv("FORECAST_CELERY_QUEUE", raising=False)
        config.reset_settings_cache()

    assert saved == []


def test_celery_mode_dispatches_to_verified_forecast_queue(monkeypatch):
    from backend.app.workers import tasks

    monkeypatch.setenv("TASK_EXECUTION_MODE", "celery")
    monkeypatch.setenv("FORECAST_CELERY_QUEUE", "forecast_final_rc")
    config.reset_settings_cache()
    submitted: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "celery_queue_available",
        lambda queue: queue == "forecast_final_rc",
    )
    monkeypatch.setattr(
        dispatcher, "find_active_idempotent_task", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(dispatcher, "save_task_record", lambda *args, **kwargs: True)
    monkeypatch.setattr(dispatcher, "append_task_log", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        tasks.run_command_task,
        "apply_async",
        lambda *args, **kwargs: submitted.append(kwargs)
        or SimpleNamespace(id="celery-test-id"),
    )
    try:
        result = dispatcher.enqueue_task("today_analysis", {})
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        monkeypatch.delenv("FORECAST_CELERY_QUEUE", raising=False)
        config.reset_settings_cache()

    assert result["queue_name"] == "forecast_final_rc"
    assert result["run_id"].startswith("run_")
    assert result["celery_task_id"] == "celery-test-id"
    assert result["status"] == "queued"
    assert submitted[0]["queue"] == "forecast_final_rc"


def test_health_check_dispatches_to_real_worker_lifecycle_task(monkeypatch):
    from backend.app.workers import tasks

    monkeypatch.setenv("TASK_EXECUTION_MODE", "auto")
    config.reset_settings_cache()
    submitted: list[dict] = []
    saved: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        dispatcher,
        "celery_queue_available",
        lambda queue: queue == "default",
    )
    monkeypatch.setattr(
        dispatcher, "find_active_idempotent_task", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        dispatcher,
        "save_task_record",
        lambda record, *, status, **kwargs: saved.append((status, dict(record))) or True,
    )
    monkeypatch.setattr(dispatcher, "append_task_log", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        tasks.health_check_task,
        "apply_async",
        lambda *args, **kwargs: submitted.append({"args": args, **kwargs})
        or SimpleNamespace(id="celery-health-id"),
    )
    try:
        result = dispatcher.enqueue_task(
            "health_check", {"force_new": True, "idempotency_key": "worker-probe-1"}
        )
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert result["status"] == "queued"
    assert result["celery_task_id"] == "celery-health-id"
    assert result["queue_name"] == "default"
    assert result["run_id"].startswith("run_")
    assert submitted[0]["queue"] == "default"
    assert len(submitted[0]["args"]) == 3
    assert [status for status, _record in saved] == ["pending", "queued"]


def test_health_check_task_keeps_probe_compatibility_and_persists_managed_runs(
    monkeypatch,
):
    from backend.app.workers import tasks

    lightweight = tasks.health_check_task()
    assert lightweight["status"] == "ok"
    assert lightweight["worker_id"]

    captured: dict = {}

    def fake_run_python_task(**kwargs):
        captured.update(kwargs)
        return {"task_id": kwargs["task_id"], "status": "success"}

    monkeypatch.setattr(tasks, "_run_python_task", fake_run_python_task)
    managed = tasks.health_check_task(
        "task_worker_probe", "run_worker_probe", {"acceptance": True}
    )

    assert managed == {"task_id": "task_worker_probe", "status": "success"}
    assert captured["kind"] == "health_check"
    assert captured["payload"] == {"acceptance": True}


def test_forecast_endpoint_returns_503_when_worker_queue_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        forecast_endpoint,
        "enqueue_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("queue unavailable")),
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/forecast/run",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        }
    )
    user = CurrentUser(
        user_id="analyst-id",
        username="analyst",
        role="analyst",
        permissions=["forecast:run"],
        auth_mode="unit_test",
    )

    with pytest.raises(HTTPException) as exc_info:
        forecast_endpoint.run_forecast(
            ForecastRunRequest(mode="refresh_fast_forecast"), request, user
        )

    assert exc_info.value.status_code == 503
    assert "队列当前不可用" in str(exc_info.value.detail)


@pytest.mark.parametrize("mode", ["fast_forecast", "refresh_fast_forecast"])
def test_forecast_endpoint_routes_formal_worker_and_preserves_idempotency(
    monkeypatch, mode
):
    submitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        forecast_endpoint,
        "enqueue_task",
        lambda kind, payload: submitted.append((kind, payload))
        or {"task_id": "task_formal", "status": "pending"},
    )
    monkeypatch.setattr(forecast_endpoint, "write_audit_log", lambda **kwargs: None)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/forecast/run",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        }
    )
    user = CurrentUser(
        user_id="analyst-id",
        username="analyst",
        role="analyst",
        permissions=["forecast:run"],
        auth_mode="unit_test",
    )

    result = forecast_endpoint.run_forecast(
        ForecastRunRequest(
            mode=mode,
            idempotency_key="forecast-request-001",
        ),
        request,
        user,
    )

    assert result["task_id"] == "task_formal"
    assert submitted == [
        ("forecast_run", {"idempotency_key": "forecast-request-001"})
    ]
