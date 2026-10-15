from __future__ import annotations

from backend.app.core import config
from backend.app.workers import dispatcher


def test_task_runtime_health_contains_queue_and_worker_state(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "celery")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "redis_available", lambda: True)
    monkeypatch.setattr(dispatcher, "celery_available", lambda: True)
    monkeypatch.setattr(
        dispatcher,
        "_celery_runtime_snapshot",
        lambda: {
            "available": True,
            "source": "celery_inspect",
            "active_workers": ["worker-1"],
            "registered_tasks": ["power_trading.run_price_predict_task"],
            "active_count": 0,
            "reserved_count": 0,
            "scheduled_count": 0,
            "active_queues": [
                "default",
                "data_sync",
                "embedding",
                "price_predict",
                "rag",
                "report",
                "report_daily",
            ],
        },
    )
    monkeypatch.setattr(
        dispatcher,
        "task_runtime_summary",
        lambda: {
            "active_workers": ["worker-1"],
            "queue_summary": [{"queue_name": "embedding", "pending": 1, "running": 2, "failed": 0, "timeout": 0}],
            "status_counts": {"running": 2, "pending": 1, "failed": 1, "timeout": 1},
            "running_task_count": 2,
            "pending_task_count": 1,
            "failed_task_count": 1,
            "timeout_task_count": 1,
        },
    )
    try:
        health = dispatcher.task_runtime_health()
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert health["ok"] is True
    assert health["dispatch_ready"] is True
    assert health["execution_mode"] == "celery"
    assert health["redis"]["ok"] is True
    assert health["celery"]["ok"] is True
    assert health["active_workers"] == ["worker-1"]
    assert health["queue_summary"][0]["queue_name"] == "embedding"
    assert health["running_task_count"] == 2
    assert health["pending_task_count"] == 1
    assert health["celery"]["missing_queues"] == []


def test_auto_health_fails_when_a_required_business_queue_is_missing(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "auto")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "redis_available", lambda: True)
    monkeypatch.setattr(dispatcher, "celery_available", lambda: True)
    monkeypatch.setattr(
        dispatcher,
        "_celery_runtime_snapshot",
        lambda: {
            "available": True,
            "source": "celery_inspect",
            "active_workers": ["health-worker"],
            "active_queues": ["default"],
        },
    )
    monkeypatch.setattr(dispatcher, "task_runtime_summary", lambda: {})
    try:
        health = dispatcher.task_runtime_health()
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert health["ok"] is False
    assert health["dispatch_ready"] is False
    assert "default" not in health["celery"]["missing_queues"]
    assert "data_sync" in health["celery"]["missing_queues"]
    assert "required Celery queues are unavailable" in health["message"]


def test_auto_health_is_unavailable_without_live_worker_and_ignores_db_snapshot(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "auto")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "redis_available", lambda: True)
    monkeypatch.setattr(dispatcher, "celery_available", lambda: True)
    monkeypatch.setattr(
        dispatcher,
        "_celery_runtime_snapshot",
        lambda: {"available": False, "source": "celery_inspect", "active_workers": []},
    )
    monkeypatch.setattr(
        dispatcher,
        "task_runtime_summary",
        lambda: {"active_workers": ["stale-db-worker"], "pending_task_count": 2},
    )
    try:
        health = dispatcher.task_runtime_health()
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert health["ok"] is False
    assert health["dispatch_ready"] is False
    assert health["active_workers"] == []
    assert health["celery"]["db_snapshot_workers"] == ["stale-db-worker"]
    assert "no active Celery worker" in health["message"]
