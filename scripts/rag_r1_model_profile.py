from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMBEDDING_ROOT = (PROJECT_ROOT / "bge-large-zh-v1.5").resolve()
RERANKER_ROOT = (PROJECT_ROOT / "bge-reranker-v2-m3").resolve()
QDRANT_ROOT_SUFFIX = ("rag-r1", "qdrant")


class ModelProfileError(RuntimeError):
    pass


def _external_qdrant_root(root: Path) -> Path:
    if not root.is_absolute():
        raise ModelProfileError("model_profile_qdrant_root_must_be_absolute")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ModelProfileError("model_profile_qdrant_root_unavailable") from exc
    if (
        resolved.parent == resolved
        or tuple(part.casefold() for part in resolved.parts[-2:]) != QDRANT_ROOT_SUFFIX
    ):
        raise ModelProfileError("model_profile_qdrant_root_invalid")
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return resolved
    raise ModelProfileError("model_profile_qdrant_root_must_be_external")


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelProfileError("model_profile_evidence_invalid") from exc
    if not isinstance(value, dict) or value.get("status") != "PASS":
        raise ModelProfileError("model_profile_evidence_not_pass")
    return value


def render_profile(
    admission: Mapping[str, Any],
    smoke: Mapping[str, Any],
    *,
    embedding_root: Path,
    reranker_root: Path,
    qdrant_root: Path,
) -> tuple[str, dict[str, str]]:
    versions = {
        role: str(admission["models"][role]["version"])
        for role in ("embedding", "reranker")
    }
    for role, version in versions.items():
        runtime = smoke.get("models", {}).get(role, {})
        if runtime.get("status") != "PASS" or runtime.get("version") != version:
            raise ModelProfileError(f"model_profile_runtime_mismatch:{role}")
        if runtime.get("fallback_used") is not False or runtime.get("network_calls") != 0:
            raise ModelProfileError(f"model_profile_runtime_unsafe:{role}")
    values = {
        "APP_ENV": "test",
        "RAG_ENABLED": "1",
        "RAG_PROFILE": "enterprise",
        "RAG_FILE_FALLBACK_ENABLED": "0",
        "RAG_EMBEDDING_PROVIDER": "sentence_transformers",
        "RAG_EMBEDDING_MODEL": "BAAI/bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_NAME": "BAAI/bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_PATH": embedding_root.as_posix(),
        "RAG_EMBEDDING_DIM": "1024",
        "RAG_EMBEDDING_EXPECTED_DIM": "1024",
        "RAG_EMBEDDING_VERSION": versions["embedding"],
        "RAG_EMBEDDING_EXPECTED_VERSION": versions["embedding"],
        "RAG_EMBEDDING_ALLOW_FALLBACK": "0",
        "RAG_EMBEDDING_FALLBACK_PROVIDER": "disabled",
        "RAG_RERANK_ENABLED": "1",
        "RAG_RERANK_PROVIDER": "bge",
        "RAG_RERANK_MODEL": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_NAME": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_PATH": reranker_root.as_posix(),
        "RAG_RERANK_DEVICE": "cpu",
        "RAG_RERANK_BATCH_SIZE": "8",
        "RAG_RERANK_MAX_LENGTH": "128",
        "RAG_RERANK_VERSION": versions["reranker"],
        "RAG_RERANK_EXPECTED_VERSION": versions["reranker"],
        "RAG_RERANK_FALLBACK_PROVIDER": "disabled",
        "RAG_RELEASE_ID": "RAG-R1",
        "RAG_QDRANT_COLLECTION": "rag_chunks_RAG-R1",
        "RAG_QDRANT_ALIAS": "rag_chunks_current",
        "RAG_PROCESS_ROLE": "api",
        "RAG_QDRANT_ACCESS_MODE": "read_only",
        "RAG_QDRANT_TLS_ENABLED": "1",
        "RAG_QDRANT_STRICT_MODE": "1",
        "RAG_QDRANT_URL": "https://127.0.0.1:6333",
        "RAG_QDRANT_TLS_CA_PATH": (qdrant_root / "tls" / "ca-cert.pem").as_posix(),
        "RAG_QDRANT_IMAGE_VERSION": "1.18.2",
    }
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", versions


def _acl(path: Path) -> str:
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
    )
    row = next(csv.reader([identity.stdout.strip()]))
    account, sid = row[0], row[1]
    completed = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{account}:F",
            "/grant:r",
            "SYSTEM:F",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise ModelProfileError("model_profile_acl_failed")
    return hashlib.sha256(sid.encode()).hexdigest()


def create_profile(
    admission: Path,
    smoke: Path,
    output: Path,
    *,
    qdrant_root: Path,
    embedding_root: Path = EMBEDDING_ROOT,
    reranker_root: Path = RERANKER_ROOT,
) -> dict[str, Any]:
    qdrant_root = _external_qdrant_root(qdrant_root)
    expected_ca_path = qdrant_root / "tls" / "ca-cert.pem"
    try:
        ca_path = expected_ca_path.resolve(strict=True)
    except OSError as exc:
        raise ModelProfileError("model_profile_qdrant_ca_unavailable") from exc
    if ca_path != expected_ca_path or not ca_path.is_file():
        raise ModelProfileError("model_profile_qdrant_ca_unavailable")
    if not embedding_root.is_absolute() or not reranker_root.is_absolute():
        raise ModelProfileError("model_profile_model_root_must_be_absolute")
    try:
        embedding_root = embedding_root.resolve(strict=True)
        reranker_root = reranker_root.resolve(strict=True)
    except OSError as exc:
        raise ModelProfileError("model_profile_model_root_unavailable") from exc
    if embedding_root.name != "bge-large-zh-v1.5" or reranker_root.name != "bge-reranker-v2-m3":
        raise ModelProfileError("model_profile_model_root_invalid")
    output = output.resolve()
    expected_output = qdrant_root / "secrets" / "model-profile.env"
    if output != expected_output or output.exists() or not output.parent.is_dir():
        raise ModelProfileError("model_profile_output_rejected")
    content, versions = render_profile(
        _load(admission),
        _load(smoke),
        embedding_root=embedding_root,
        reranker_root=reranker_root,
        qdrant_root=qdrant_root,
    )
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    sid_hash = _acl(output)
    return {
        "status": "PASS",
        "output": str(output),
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "versions": versions,
        "acl_applied": True,
        "principal_sid_sha256": sid_hash,
        "secret_values_written": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create admitted RAG-R1 model profile")
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--qdrant-root", type=Path, required=True)
    parser.add_argument("--embedding-root", type=Path, default=EMBEDDING_ROOT)
    parser.add_argument("--reranker-root", type=Path, default=RERANKER_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        output = args.output or args.qdrant_root / "secrets" / "model-profile.env"
        result = create_profile(
            args.admission,
            args.smoke,
            output,
            qdrant_root=args.qdrant_root,
            embedding_root=args.embedding_root,
            reranker_root=args.reranker_root,
        )
    except Exception as exc:
        print(f"RAG-R1 model profile FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
