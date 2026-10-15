from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.core.security import CurrentUser
from backend.app.repositories.base import (
    dumps_json,
    loads_json,
    mapping_dict,
    mapping_list,
    postgres_engine,
)


ACTION_TARGET = {
    "approve": "approved",
    "reject": "rejected",
    "publish": "published",
}
REVIEWABLE_STATES = {"draft", "ready", "pending", "reviewing"}


class ReportGovernanceError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def validate_report_transition(
    *,
    current_status: str,
    action: str,
    actor: CurrentUser,
    comment: str,
    metadata: dict[str, Any] | None = None,
    requested_reviewer: str = "",
) -> tuple[str, bool]:
    normalized_action = str(action or "").strip().lower()
    target = ACTION_TARGET.get(normalized_action)
    if target is None:
        raise ReportGovernanceError(
            "report_action_invalid", "不支持的报告状态操作。", status_code=400
        )
    if not actor.username.strip():
        raise ReportGovernanceError(
            "report_actor_required", "当前登录身份不可用。", status_code=401
        )
    claimed = str(requested_reviewer or "").strip()
    if claimed and claimed != actor.username:
        raise ReportGovernanceError(
            "report_actor_mismatch",
            "审核人必须与当前登录身份一致。",
            status_code=403,
        )
    required_permission = (
        "report:publish" if normalized_action == "publish" else "report:review"
    )
    if not actor.has_permission(required_permission):
        raise ReportGovernanceError(
            "report_permission_denied",
            f"缺少权限：{required_permission}",
            status_code=403,
        )

    current = str(current_status or "").strip().lower()
    if current == target:
        return target, True
    if normalized_action in {"approve", "reject"}:
        if current not in REVIEWABLE_STATES:
            raise ReportGovernanceError(
                "report_transition_conflict",
                f"报告状态 {current or 'unknown'} 不允许执行 {normalized_action}。",
                status_code=409,
            )
        if not str(comment or "").strip():
            raise ReportGovernanceError(
                "report_review_comment_required",
                "通过或驳回报告必须填写审核意见。",
                status_code=400,
            )
        creator = str((metadata or {}).get("created_by") or "").strip()
        if normalized_action == "approve" and creator and creator == actor.username:
            raise ReportGovernanceError(
                "report_self_approval_forbidden",
                "报告创建人不能审核通过自己的报告。",
                status_code=409,
            )
    elif current != "approved":
        raise ReportGovernanceError(
            "report_transition_conflict",
            "只有已通过的报告可以发布。",
            status_code=409,
        )
    if normalized_action == "publish" and bool((metadata or {}).get("is_stale")):
        raise ReportGovernanceError(
            "stale_report_cannot_publish",
            "历史过期报告只能用于审计，不能发布。",
            status_code=409,
        )
    return target, False


def _review_columns(connection) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(false))
              AND table_name = 'report_reviews'
            """
        )
    ).mappings().all()
    return {str(row.get("column_name")) for row in rows}


def transition_report(
    report_id: str,
    *,
    action: str,
    actor: CurrentUser,
    comment: str = "",
    requested_reviewer: str = "",
    engine: Engine | None = None,
) -> dict[str, Any]:
    database = engine or postgres_engine()
    if database is None:
        raise ReportGovernanceError(
            "report_database_unavailable",
            "报告数据库不可用，状态没有变更。",
            status_code=503,
        )
    try:
        with database.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT report_id, run_id, status, metadata_json
                    FROM report_runs
                    WHERE report_id = :report_id
                    FOR UPDATE
                    """
                ),
                {"report_id": report_id},
            ).mappings().first()
            if row is None:
                raise ReportGovernanceError(
                    "report_not_found", "报告不存在。", status_code=404
                )
            report = mapping_dict(row)
            metadata = loads_json(report.get("metadata_json"), default={})
            metadata = metadata if isinstance(metadata, dict) else {}
            target, idempotent = validate_report_transition(
                current_status=str(report.get("status") or ""),
                action=action,
                actor=actor,
                comment=comment,
                metadata=metadata,
                requested_reviewer=requested_reviewer,
            )
            previous = str(report.get("status") or "")
            if idempotent:
                return {
                    "ok": True,
                    "report_id": report_id,
                    "run_id": report.get("run_id"),
                    "previous_status": previous,
                    "status": target,
                    "action": action,
                    "actor": actor.username,
                    "transition_applied": False,
                    "idempotent": True,
                }

            columns = _review_columns(connection)
            status_column = "status" if "status" in columns else "action"
            comment_column = (
                "review_comment" if "review_comment" in columns else "comment"
            )
            required = {"report_id", "reviewer", status_column, comment_column}
            if not required.issubset(columns):
                raise ReportGovernanceError(
                    "report_review_schema_incompatible",
                    "报告审核表结构不兼容，状态没有变更。",
                    status_code=503,
                )
            version = int(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM report_reviews WHERE report_id=:report_id"
                    ),
                    {"report_id": report_id},
                ).scalar_one()
                or 0
            ) + 1
            event_id = f"report_event_{uuid.uuid4().hex}"
            event_metadata = {
                "event_id": event_id,
                "source": "report_governance_service",
                "action": action,
                "previous_status": previous,
                "status": target,
                "actor_user_id": actor.user_id,
                "actor_role": actor.role,
                "tenant_id": actor.tenant_id,
                "workspace_id": actor.workspace_id,
                "version": version,
            }
            fields = ["report_id", "reviewer", status_column, comment_column]
            values = [":report_id", ":reviewer", ":event_status", ":comment"]
            params: dict[str, Any] = {
                "report_id": report_id,
                "reviewer": actor.username,
                "event_status": target,
                "comment": str(comment or "").strip(),
            }
            if "run_id" in columns:
                fields.append("run_id")
                values.append(":run_id")
                params["run_id"] = report.get("run_id")
            if "version" in columns:
                fields.append("version")
                values.append(":version")
                params["version"] = version
            if "metadata_json" in columns:
                fields.append("metadata_json")
                values.append("CAST(:event_metadata AS jsonb)")
                params["event_metadata"] = dumps_json(event_metadata)
            connection.execute(
                text(
                    f"INSERT INTO report_reviews ({', '.join(fields)}) "
                    f"VALUES ({', '.join(values)})"
                ),
                params,
            )
            updated = connection.execute(
                text(
                    """
                    UPDATE report_runs
                    SET status=:status, updated_at=CURRENT_TIMESTAMP
                    WHERE report_id=:report_id AND status=:previous_status
                    """
                ),
                {
                    "status": target,
                    "report_id": report_id,
                    "previous_status": previous,
                },
            )
            if updated.rowcount != 1:
                raise ReportGovernanceError(
                    "report_concurrent_transition",
                    "报告状态已被其他操作更新，请刷新后重试。",
                    status_code=409,
                )
        return {
            "ok": True,
            "report_id": report_id,
            "run_id": report.get("run_id"),
            "previous_status": previous,
            "status": target,
            "action": action,
            "actor": actor.username,
            "event_id": event_id,
            "event_version": version,
            "transition_applied": True,
            "idempotent": False,
        }
    except ReportGovernanceError:
        raise
    except Exception as exc:
        raise ReportGovernanceError(
            "report_transition_failed",
            "报告状态写入失败，事务已回滚。",
            status_code=503,
        ) from exc


def list_report_review_events(
    report_id: str, *, engine: Engine | None = None
) -> list[dict[str, Any]]:
    database = engine or postgres_engine()
    if database is None:
        raise ReportGovernanceError(
            "report_database_unavailable", "报告数据库不可用。", status_code=503
        )
    try:
        with database.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM report_runs WHERE report_id=:report_id"),
                {"report_id": report_id},
            ).first()
            if exists is None:
                raise ReportGovernanceError(
                    "report_not_found", "报告不存在。", status_code=404
                )
            columns = _review_columns(connection)
            status_column = "status" if "status" in columns else "action"
            comment_column = (
                "review_comment" if "review_comment" in columns else "comment"
            )
            updated_column = "updated_at" if "updated_at" in columns else "created_at"
            version_expression = "version" if "version" in columns else "NULL AS version"
            metadata_expression = (
                "metadata_json" if "metadata_json" in columns else "NULL AS metadata_json"
            )
            rows = connection.execute(
                text(
                    f"""
                    SELECT report_id, {status_column} AS status, reviewer,
                           {comment_column} AS review_comment,
                           {version_expression}, {metadata_expression},
                           created_at, {updated_column} AS updated_at
                    FROM report_reviews
                    WHERE report_id=:report_id
                    ORDER BY {updated_column} DESC, created_at DESC
                    """
                ),
                {"report_id": report_id},
            ).mappings().all()
        return mapping_list(rows)
    except ReportGovernanceError:
        raise
    except Exception as exc:
        raise ReportGovernanceError(
            "report_reviews_read_failed", "报告审核记录读取失败。", status_code=503
        ) from exc
