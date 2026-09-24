from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .config import APP_VERSION, PROJECT_ROOT


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def source_fingerprint(root: Path = PROJECT_ROOT) -> str:
    normalized = os.path.normcase(str(root.resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def source_alembic_heads() -> tuple[str, ...]:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))
    except Exception:
        return ()


@lru_cache(maxsize=1)
def database_alembic_current() -> tuple[str, ...]:
    attested = os.environ.get("APP_DATABASE_ALEMBIC_CURRENT", "").strip()
    if attested:
        try:
            values = json.loads(attested)
        except json.JSONDecodeError:
            return ()
        if not isinstance(values, list) or not values:
            return ()
        revisions = tuple(sorted(str(value) for value in values))
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", value) for value in revisions):
            return ()
        return revisions
    if not os.environ.get("DATABASE_URL", "").strip():
        return ()
    try:
        from .db.session import get_engine

        with get_engine().connect() as connection:
            rows = connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            return tuple(sorted(str(value) for value in rows))
    except Exception:
        return ()


@lru_cache(maxsize=1)
def source_identity() -> dict[str, Any]:
    sha = os.environ.get("APP_GIT_SHA", "").strip() or _git("rev-parse", "HEAD")
    branch = os.environ.get("APP_GIT_BRANCH", "").strip() or _git("branch", "--show-current")
    dirty_override = os.environ.get("APP_WORKTREE_DIRTY", "").strip().lower()
    if dirty_override:
        dirty = dirty_override in {"1", "true", "yes", "on"}
    else:
        dirty = _git("status", "--porcelain", "--untracked-files=no") not in {"", "unknown"}
    build_id = os.environ.get("APP_BUILD_ID", "").strip() or f"{APP_VERSION.lstrip('v')}+{sha[:12]}"
    return {
        "version": APP_VERSION,
        "git_sha": sha,
        "git_branch": branch,
        "build_id": build_id,
        "working_tree_dirty": dirty,
        "source_fingerprint": source_fingerprint(),
        "alembic_head": list(source_alembic_heads()),
    }


def runtime_identity_payload() -> dict[str, Any]:
    payload = dict(source_identity())
    current = list(database_alembic_current())
    payload["alembic_current"] = current
    payload["alembic_match"] = bool(current) and current == payload["alembic_head"]
    payload["database_revision_source"] = (
        os.environ.get("APP_DATABASE_REVISION_SOURCE", "").strip()
        or ("runtime_database" if current else "unavailable")
    )
    return payload
