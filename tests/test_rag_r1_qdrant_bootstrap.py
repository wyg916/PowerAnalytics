from pathlib import Path

import pytest

from scripts.rag_r1_qdrant_bootstrap import (
    PROJECT_ROOT,
    QdrantBootstrapError,
    validate_digest,
    validate_root,
)


def test_digest_gate_accepts_only_sha256():
    digest = "sha256:" + "a" * 64
    assert validate_digest(digest) == digest
    for invalid in ("", "latest", "sha256:unset", "sha256:" + "g" * 64):
        with pytest.raises(QdrantBootstrapError, match="digest_invalid"):
            validate_digest(invalid)


def test_root_gate_requires_new_absolute_well_formed_path_outside_repository(tmp_path: Path):
    root = tmp_path / "rag-r1" / "qdrant"
    assert validate_root(root) == root.resolve()
    with pytest.raises(QdrantBootstrapError, match="must_be_absolute"):
        validate_root(Path("rag-r1/qdrant"))
    with pytest.raises(QdrantBootstrapError, match="layout_invalid"):
        validate_root(tmp_path / "qdrant")
    with pytest.raises(QdrantBootstrapError, match="outside_repository"):
        validate_root(PROJECT_ROOT / ".runtime" / "rag-r1" / "qdrant")


def test_existing_root_is_never_overwritten(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "exists", lambda _path: True)
    with pytest.raises(QdrantBootstrapError, match="already_exists"):
        validate_root(tmp_path / "rag-r1" / "qdrant")
