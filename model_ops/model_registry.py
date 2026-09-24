from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from backend.app.services.model_fact_service import DEFAULT_MODEL_DOMAIN, ModelFactError, ModelFactService


MODEL_TRAINING_DATABASE_URL_ENV = "MODEL_TRAINING_DATABASE_URL"
MODEL_TRAINING_DATABASE_USER = "beta10d_forecast_login"
MODEL_TRAINING_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "postgres"})


def create_model_training_engine() -> Engine:
    """创建只用于训练输入读取与 Candidate 登记的受限 PostgreSQL 连接。"""

    raw_url = os.environ.get(MODEL_TRAINING_DATABASE_URL_ENV, "").strip()
    if not raw_url:
        raise ModelFactError("显式重训缺少独立 MODEL_TRAINING_DATABASE_URL")
    try:
        parsed = make_url(raw_url)
    except Exception as exc:
        raise ModelFactError("MODEL_TRAINING_DATABASE_URL 格式无效") from exc
    if not parsed.drivername.startswith("postgresql"):
        raise ModelFactError("显式重训只允许 PostgreSQL")
    if str(parsed.host or "").lower() not in MODEL_TRAINING_ALLOWED_HOSTS:
        raise ModelFactError("显式重训数据库目标不在本机/受控 Compose 范围")
    if parsed.username != MODEL_TRAINING_DATABASE_USER:
        raise ModelFactError("显式重训必须使用 beta10d_forecast_login 受限身份")

    try:
        engine = create_engine(raw_url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            identity = conn.execute(
                text(
                    "SELECT current_user, session_user, r.rolsuper, r.rolcreatedb, "
                    "r.rolcreaterole, r.rolreplication, r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                )
            ).mappings().one()
    except Exception as exc:
        raise ModelFactError("显式重训 PostgreSQL 连接或身份核验失败") from exc
    privileged = any(
        bool(identity[name])
        for name in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")
    )
    if (
        identity["current_user"] != MODEL_TRAINING_DATABASE_USER
        or identity["session_user"] != MODEL_TRAINING_DATABASE_USER
        or privileged
    ):
        engine.dispose()
        raise ModelFactError("显式重训 PostgreSQL 身份不满足最小权限门禁")
    return engine


def load_artifact_manifest(artifact_dir: str | Path) -> dict[str, Any]:
    path = Path(artifact_dir) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 artifact manifest：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_artifact_hash_manifest(artifact_dir: str | Path) -> str:
    root = Path(artifact_dir)
    hash_manifest_path = root / "sha256_manifest.json"
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path == hash_manifest_path:
            continue
        entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not entries:
        raise ModelFactError("模型 artifact 目录没有可校验文件")
    artifact_hash = hashlib.sha256(
        json.dumps(entries, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "algorithm": "SHA-256",
        "artifact_hash": artifact_hash,
        "files": entries,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if hash_manifest_path.exists():
        if hash_manifest_path.read_text(encoding="utf-8") != serialized:
            raise ModelFactError("已有 sha256_manifest.json 与当前 artifact 不一致")
    else:
        hash_manifest_path.write_text(serialized, encoding="utf-8")
    return artifact_hash


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _preferred_metric_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    if "模型" in df.columns:
        preferred = df[df["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
    if "RMSE" in df.columns:
        return df.sort_values("RMSE").iloc[0].to_dict()
    return df.iloc[0].to_dict()


def _preferred_peak_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("peak_spike_metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if "模型" in df.columns:
        preferred = df[df["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
    return df.iloc[0].to_dict()


def _find_key(row: dict[str, Any], contains: list[str]) -> Any:
    for key, value in row.items():
        if all(part in str(key) for part in contains):
            return value
    return None


def register_model_artifact(config: dict[str, Any], artifact_dir: str | Path, status: str = "candidate") -> str:
    """把模型 artifact 写入 model_registry。

    迁移必须由显式部署流程提前执行；注册不会隐式迁移或激活。
    """

    if str(status or "candidate").strip().lower() != "candidate":
        raise ModelFactError("新 artifact 只能登记为 Candidate，不能自动晋升")
    manifest = load_artifact_manifest(artifact_dir)
    metrics_path = Path(artifact_dir) / "metrics.json"
    training_path = Path(artifact_dir) / "training_config.json"
    schema_path = Path(artifact_dir) / "input_schema.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    training = json.loads(training_path.read_text(encoding="utf-8")) if training_path.exists() else {}
    input_schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}
    model_version = manifest["model_version"]
    artifact_hash = write_artifact_hash_manifest(artifact_dir)
    declared_artifact_hash = str(manifest.get("artifact_hash") or "").strip()
    if declared_artifact_hash and declared_artifact_hash != artifact_hash:
        raise ModelFactError("manifest 声明的 artifact_hash 与静态文件校验结果不一致")
    model_role = "blended"
    metric_row = _preferred_metric_row(metrics)
    peak_row = _preferred_peak_row(metrics)
    train_start_date = None
    train_end_date = None
    try:
        datasets = training.get("datasets") or []
        train_window = next((item for item in datasets if item.get("name") == "train"), None)
        if train_window:
            train_start_date = pd.to_datetime(train_window.get("start_datetime"), errors="coerce")
            train_end_date = pd.to_datetime(train_window.get("end_datetime"), errors="coerce")
            train_start_date = None if pd.isna(train_start_date) else train_start_date.date()
            train_end_date = None if pd.isna(train_end_date) else train_end_date.date()
    except Exception:
        train_start_date = None
        train_end_date = None
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(manifest.get("domain") or training.get("domain") or model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(
        manifest.get("target_name")
        or training.get("target_name")
        or input_schema.get("target_col")
        or model_cfg.get("target_name")
        or ""
    ).strip()
    if not domain or not target_name:
        raise ModelFactError("artifact 元数据缺少 domain 或 target_name")
    schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest() if schema_path.exists() else None
    engine = create_model_training_engine()
    try:
        ModelFactService(engine).register_candidate(
            {
                "model_id": str(manifest.get("model_id") or model_version),
                "model_version": model_version,
                "domain": domain,
                "target_name": target_name,
                "model_role": model_role,
                "artifact_id": str(manifest.get("artifact_id") or f"artifact_{artifact_hash[:24]}"),
                "artifact_path": str(Path(artifact_dir).resolve()),
                "artifact_hash": artifact_hash,
                "feature_version": training.get("feature_version") or metrics.get("feature_version") or input_schema.get("feature_version"),
                "schema_hash": manifest.get("schema_hash") or schema_hash,
                "source_type": "training",
                "train_start_date": train_start_date,
                "train_end_date": train_end_date,
                "test_mae": _safe_float(metric_row.get("MAE")),
                "test_rmse": _safe_float(metric_row.get("RMSE")),
                "peak_rmse": _safe_float(_find_key(peak_row, ["高峰", "RMSE"])),
                "spike_rmse": _safe_float(_find_key(peak_row, ["尖峰", "RMSE"])),
            }
        )
    finally:
        engine.dispose()
    return model_version
