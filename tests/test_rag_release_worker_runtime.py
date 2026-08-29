from __future__ import annotations

import hashlib
import json

import pytest

from backend.app.services.knowledge_enterprise_service import EnterpriseKnowledgeUnavailable
from backend.app.services.rag_release_service import REQUIRED_RELEASE_GATES
from backend.app.services import rag_release_worker_runtime as runtime_module
from backend.app.services.rag_release_worker_runtime import QdrantReleaseAdmin, _gate_rows


def _report() -> dict:
    return {
        "release_id": "RAG-R1",
        "gates": [
            {"gate": name, "passed": True, "reason": ""}
            for name in sorted(REQUIRED_RELEASE_GATES)
        ],
    }


def test_gate_report_requires_the_exact_mandatory_set() -> None:
    rows = _gate_rows(_report(), "RAG-R1")
    assert {row.gate for row in rows} == REQUIRED_RELEASE_GATES
    assert all(row.passed and not row.reason for row in rows)


@pytest.mark.parametrize("mutation,reason", [
    ("missing", "incomplete"),
    ("failed", "failed"),
    ("duplicate", "duplicate"),
    ("wrong_release", "release_mismatch"),
])
def test_gate_report_fails_closed(mutation: str, reason: str) -> None:
    report = _report()
    if mutation == "missing":
        report["gates"].pop()
    elif mutation == "failed":
        report["gates"][0]["passed"] = False
    elif mutation == "duplicate":
        report["gates"].append(dict(report["gates"][0]))
    else:
        report["release_id"] = "RAG-R2"
    with pytest.raises(EnterpriseKnowledgeUnavailable, match=reason):
        _gate_rows(report, "RAG-R1")


def test_gate_report_hash_is_canonical_and_reproducible() -> None:
    report = _report()
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == hashlib.sha256(encoded).hexdigest()


def test_qdrant_admin_requires_explicit_external_trust_root(monkeypatch, tmp_path) -> None:
    root = tmp_path / "rag-r1" / "qdrant"
    (root / "secrets").mkdir(parents=True)
    (root / "tls").mkdir()
    env_file = root / "secrets" / "runtime.env"
    env_file.write_text(
        f"RAG_R1_QDRANT_ROOT={root.as_posix()}\n"
        "QDRANT_ADMIN_API_KEY=admin-test-only\n"
        "QDRANT_READ_ONLY_API_KEY=reader-test-only\n",
        encoding="utf-8",
    )
    (root / "tls" / "ca-cert.pem").write_text("test-ca", encoding="ascii")
    monkeypatch.setenv("RAG_RELEASE_ALLOWED_QDRANT_ROOT", str(root))
    monkeypatch.setattr(runtime_module.ssl, "create_default_context", lambda **_: object())

    admin = QdrantReleaseAdmin(env_file)

    assert admin.endpoint == "https://127.0.0.1:6333"
    monkeypatch.setenv("RAG_RELEASE_ALLOWED_QDRANT_ROOT", str(tmp_path / "other" / "rag-r1" / "qdrant"))
    with pytest.raises(EnterpriseKnowledgeUnavailable):
        QdrantReleaseAdmin(env_file)
