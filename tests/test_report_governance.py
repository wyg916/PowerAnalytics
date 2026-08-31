from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from starlette.requests import Request

from backend.app.api.v1.endpoints import report as report_endpoint
from backend.app.core import security
from backend.app.core.security import CurrentUser
from backend.app.services import task_business_handlers
from backend.app.services.report_generation_service import (
    _safe_report_id,
    _versioned_report_id,
)
from backend.app.services.report_governance_service import (
    ReportGovernanceError,
    list_report_review_events,
    transition_report,
    validate_report_transition,
)


def _user(username: str, *permissions: str, role: str = "reviewer") -> CurrentUser:
    return CurrentUser(
        user_id=f"user-{username}",
        username=username,
        role=role,
        permissions=list(permissions),
        auth_mode="test",
    )


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_transition_requires_explicit_comment(action: str) -> None:
    with pytest.raises(ReportGovernanceError) as caught:
        validate_report_transition(
            current_status="ready",
            action=action,
            actor=_user("reviewer-a", "report:review"),
            comment="",
        )
    assert caught.value.code == "report_review_comment_required"
    assert caught.value.status_code == 400


def test_publish_requires_approved_non_stale_report_and_publish_permission() -> None:
    with pytest.raises(ReportGovernanceError) as wrong_state:
        validate_report_transition(
            current_status="ready",
            action="publish",
            actor=_user("publisher", "report:publish"),
            comment="",
        )
    assert wrong_state.value.code == "report_transition_conflict"

    with pytest.raises(ReportGovernanceError) as stale:
        validate_report_transition(
            current_status="approved",
            action="publish",
            actor=_user("publisher", "report:publish"),
            comment="",
            metadata={"is_stale": True},
        )
    assert stale.value.code == "stale_report_cannot_publish"

    with pytest.raises(ReportGovernanceError) as denied:
        validate_report_transition(
            current_status="approved",
            action="publish",
            actor=_user("reviewer-a", "report:review"),
            comment="",
        )
    assert denied.value.code == "report_permission_denied"

    assert validate_report_transition(
        current_status="approved",
        action="publish",
        actor=_user("publisher", "report:publish"),
        comment="",
    ) == ("published", False)


def test_actor_spoof_and_self_approval_are_rejected() -> None:
    actor = _user("reviewer-a", "report:review")
    with pytest.raises(ReportGovernanceError) as spoofed:
        validate_report_transition(
            current_status="ready",
            action="approve",
            actor=actor,
            comment="核验通过",
            requested_reviewer="admin",
        )
    assert spoofed.value.code == "report_actor_mismatch"

    with pytest.raises(ReportGovernanceError) as self_approval:
        validate_report_transition(
            current_status="ready",
            action="approve",
            actor=actor,
            comment="核验通过",
            metadata={"created_by": "reviewer-a"},
        )
    assert self_approval.value.code == "report_self_approval_forbidden"


def test_dynamic_role_configuration_cannot_escalate_static_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(
        security,
        "list_role_permissions",
        lambda: [{"role_id": "analyst", "permissions": ["report:read", "report:review", "report:publish"]}],
    )
    resolved = security.permissions_for_role("analyst")
    assert "report:read" in resolved
    assert "report:review" not in resolved
    assert "report:publish" not in resolved

    monkeypatch.setattr(
        security,
        "list_role_permissions",
        lambda: [{"role_id": "admin", "permissions": ["report:publish"]}],
    )
    assert security.permissions_for_role("admin") == []


def test_regenerate_enqueues_exact_rejected_report_lineage(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        report_endpoint,
        "report_status",
        lambda report_id: {
            "report_id": report_id,
            "run_id": "run-accepted-24h",
            "report_type": "weekly",
            "status": "rejected",
            "metadata": {"region": "华东"},
        },
    )

    def enqueue(kind: str, payload: dict):
        captured.update({"kind": kind, "payload": payload})
        return {"task_id": "task-version-2", "status": "pending"}

    monkeypatch.setattr(report_endpoint, "enqueue_task", enqueue)
    monkeypatch.setattr(report_endpoint, "write_audit_log", lambda **_: True)
    result = report_endpoint.report_regenerate(
        "report-v1",
        _request(),
        _user("analyst-a", "report:generate", role="analyst"),
    )

    assert result["accepted"] is True
    assert captured["kind"] == "report_generate"
    assert captured["payload"] == {
        "run_id": "run-accepted-24h",
        "report_type": "weekly",
        "region": "华东",
        "source_report_id": "report-v1",
        "regenerate": True,
        "requested_by": "analyst-a",
    }


def test_report_task_handler_forwards_regeneration_contract(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(task_business_handlers, "postgres_engine", lambda: Mock())

    def generate(_engine, **kwargs):
        captured.update(kwargs)
        return {"report_id": "report-v2", "run_id": "run-accepted-24h", "idempotent": False}

    monkeypatch.setattr(task_business_handlers, "generate_operational_report", generate)
    task_business_handlers.run_report_daily(
        {
            "run_id": "run-accepted-24h",
            "report_type": "weekly",
            "source_report_id": "report-v1",
            "requested_by": "analyst-a",
        }
    )
    assert captured["source_report_id"] == "report-v1"
    assert captured["requested_by"] == "analyst-a"


def test_versioned_report_ids_fit_database_contract() -> None:
    root = _safe_report_id("run-" + "x" * 200, "operation_decision")
    versioned = _versioned_report_id(root, 12)
    assert len(root) <= 64
    assert len(versioned) <= 64
    assert versioned.endswith("_v12")


def test_local_postgres_transition_is_atomic_auditable_and_idempotent() -> None:
    url = os.getenv("REPORT_GOVERNANCE_ACCEPTANCE_URL", "").strip()
    if not url:
        pytest.skip("REPORT_GOVERNANCE_ACCEPTANCE_URL is not configured")
    engine = create_engine(url, future=True)
    report_id = f"audit_rpt_{uuid.uuid4().hex[:20]}"
    invalid_id = f"audit_invalid_{uuid.uuid4().hex[:16]}"
    reviewer = _user("audit-reviewer", "report:review")
    publisher = _user("audit-publisher", "report:publish", role="admin")
    metadata = json.dumps({"created_by": "audit-generator", "is_stale": False})
    connection = engine.connect()
    outer_transaction = connection.begin()

    class RollbackOnlyEngine:
        @contextmanager
        def begin(self):
            savepoint = connection.begin_nested()
            try:
                yield connection
            except Exception:
                savepoint.rollback()
                raise
            else:
                savepoint.commit()

        @contextmanager
        def connect(self):
            yield connection

    controlled_engine = RollbackOnlyEngine()
    try:
        connection.execute(
            text(
                """
                INSERT INTO report_runs (
                    report_id, run_id, title, status, report_type,
                    metadata_json, content_json, generated_at
                ) VALUES (
                    :report_id, 'audit-run-governance', '报告治理受控验收记录',
                    'ready', 'daily', CAST(:metadata AS jsonb), CAST('{}' AS jsonb),
                    CURRENT_TIMESTAMP
                )
                """
            ),
            [{"report_id": value, "metadata": metadata} for value in (report_id, invalid_id)],
        )
        approved = transition_report(
            report_id,
            action="approve",
            actor=reviewer,
            comment="受控验收：预测事实与报告摘要已核对。",
            engine=controlled_engine,
        )
        published = transition_report(
            report_id,
            action="publish",
            actor=publisher,
            comment="受控验收发布。",
            engine=controlled_engine,
        )
        repeated = transition_report(
            report_id,
            action="publish",
            actor=publisher,
            comment="重复请求不应新增治理事件。",
            engine=controlled_engine,
        )
        with pytest.raises(ReportGovernanceError) as invalid:
            transition_report(
                invalid_id,
                action="publish",
                actor=publisher,
                comment="非法直接发布。",
                engine=controlled_engine,
            )
        events = list_report_review_events(report_id, engine=controlled_engine)
        states = dict(
            connection.execute(
                text("SELECT report_id, status FROM report_runs WHERE report_id IN (:valid, :invalid)"),
                {"valid": report_id, "invalid": invalid_id},
            ).all()
        )
        invalid_events = connection.execute(
            text("SELECT COUNT(*) FROM report_reviews WHERE report_id=:report_id"),
            {"report_id": invalid_id},
        ).scalar_one()
        assert approved["transition_applied"] is True
        assert published["transition_applied"] is True
        assert repeated["idempotent"] is True
        assert invalid.value.code == "report_transition_conflict"
        assert states == {report_id: "published", invalid_id: "ready"}
        assert invalid_events == 0
        assert len(events) == 2
        assert {event["reviewer"] for event in events} == {"audit-reviewer", "audit-publisher"}
    finally:
        outer_transaction.rollback()
        connection.close()
        with engine.connect() as verification:
            residual = verification.execute(
                text("SELECT COUNT(*) FROM report_runs WHERE report_id IN (:valid, :invalid)"),
                {"valid": report_id, "invalid": invalid_id},
            ).scalar_one()
        engine.dispose()
    assert residual == 0
