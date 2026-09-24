"""align persisted built-in roles with the runtime permission ceilings

Revision ID: 0024_role_permissions_v2
Revises: 0023_model_center_facts
Create Date: 2026-08-30
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0024_role_permissions_v2"
down_revision = "0023_model_center_facts"
branch_labels = None
depends_on = None


LEGACY_DEFAULTS = {
    "analyst": [
        "dashboard:read", "forecast:read", "forecast:run", "data:read",
        "data:sync", "task:read", "task:run", "assistant:use",
        "knowledge:read", "knowledge:write", "report:read",
        "report:generate", "report:review", "model:read",
    ],
    "developer": [
        "dashboard:read", "forecast:read", "data:read", "task:read",
        "assistant:use", "assistant:debug", "knowledge:read", "report:read",
        "model:read", "trace:read", "security:read",
    ],
    "viewer": [
        "dashboard:read", "forecast:read", "data:read", "assistant:use",
        "knowledge:read", "report:read", "model:read", "task:read",
    ],
    "reviewer": ["strategy:read", "strategy:review"],
    "operator": [
        "dashboard:read", "forecast:read", "forecast:run", "data:read",
        "task:read", "task:run", "assistant:use", "knowledge:read",
        "report:read", "report:generate",
    ],
}

# A previous controlled remediation expanded reviewer from the original
# strategy-only default to this exact report/strategy subset.  It is a known
# product default, not an arbitrary tenant customization, so it is safe to
# advance while all other non-matching role configurations remain untouched.
INTERMEDIATE_DEFAULTS = {
    "reviewer": [
        "report:download", "report:read", "report:review",
        "strategy:read", "strategy:review",
    ],
}

RUNTIME_DEFAULTS = {
    "analyst": [
        "assistant:export", "assistant:use", "auth:self", "dashboard:read",
        "data:export", "data:query", "data:read", "data:sync",
        "forecast:read", "forecast:run", "knowledge:export",
        "knowledge:read", "model:read", "report:download",
        "report:generate", "report:read", "strategy:generate",
        "strategy:read", "strategy:submit", "task:read",
    ],
    "developer": [
        "assistant:debug", "assistant:export", "assistant:use", "audit:read",
        "auth:self", "dashboard:read", "data:export", "data:query",
        "data:read", "forecast:read", "knowledge:diagnose",
        "knowledge:export", "knowledge:read", "model:export", "model:read",
        "report:download", "report:read", "security:read", "settings:read",
        "strategy:read", "system:diagnostics", "task:diagnostics",
        "task:read", "trace:read", "user:read",
    ],
    "viewer": [
        "auth:self", "dashboard:read", "forecast:read", "knowledge:read",
        "report:read", "strategy:read",
    ],
    "reviewer": [
        "auth:self", "dashboard:read", "forecast:read", "knowledge:publish",
        "knowledge:read", "knowledge:write", "report:download",
        "report:read", "report:review", "strategy:read", "strategy:review",
    ],
    "operator": [
        "assistant:export", "assistant:use", "auth:self", "dashboard:read",
        "data:export", "data:query", "data:read", "data:sync",
        "forecast:read", "forecast:run", "knowledge:export",
        "knowledge:read", "model:read", "report:download",
        "report:generate", "report:read", "strategy:generate",
        "strategy:read", "strategy:submit", "task:read",
    ],
}


def _replace_defaults(source: dict[str, list[str]], target: dict[str, list[str]]) -> None:
    connection = op.get_bind()
    statement = sa.text(
        """
        UPDATE roles
        SET permissions_json = CAST(:target AS jsonb), updated_at = CURRENT_TIMESTAMP
        WHERE role_id = :role_id
          AND permissions_json = CAST(:source AS jsonb)
        """
    )
    for role_id, source_permissions in source.items():
        connection.execute(
            statement,
            {
                "role_id": role_id,
                "source": json.dumps(source_permissions, separators=(",", ":")),
                "target": json.dumps(target[role_id], separators=(",", ":")),
            },
        )


def upgrade() -> None:
    _replace_defaults(LEGACY_DEFAULTS, RUNTIME_DEFAULTS)
    _replace_defaults(INTERMEDIATE_DEFAULTS, RUNTIME_DEFAULTS)


def downgrade() -> None:
    _replace_defaults(RUNTIME_DEFAULTS, LEGACY_DEFAULTS)
