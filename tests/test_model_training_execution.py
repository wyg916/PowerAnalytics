from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import main_daily_run
from backend.app.core.security import CurrentUser
from backend.app.repositories import model_repository
from backend.app.services.model_fact_service import ModelFactError
from backend.app.workers import dispatcher, tasks
from model_ops import model_registry
from services import prediction_service


def _args(**overrides) -> argparse.Namespace:
    values = {
        "model_auto_optimize": False,
        "retrain_model": False,
        "refresh_data": False,
        "fast_forecast": False,
        "skip_prediction": False,
        "prediction_report_only": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_explicit_retrain_runs_training_only_without_report_dispatch() -> None:
    assert main_daily_run.build_sequence(_args(retrain_model=True)) == [
        "01_run_prediction.py"
    ]


def _prediction_paths(tmp_path: Path) -> SimpleNamespace:
    engine_script = tmp_path / "engine.py"
    engine_script.write_text("# controlled test engine", encoding="utf-8")
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return SimpleNamespace(
        root_dir=tmp_path,
        engine_script=engine_script,
        result_table_dir=result_dir,
        data_dir=data_dir,
    )


def _patch_prediction_dependencies(monkeypatch, paths, events: list[tuple]):
    monkeypatch.setattr(prediction_service, "get_pipeline_paths", lambda _config: paths)
    monkeypatch.setattr(
        prediction_service,
        "run_prediction_engine",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        prediction_service,
        "_export_retrain_inputs_from_postgres",
        lambda *args, **kwargs: {"master_rows": 8760},
    )
    monkeypatch.setattr(
        prediction_service, "sync_result_tables_to_database", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        prediction_service,
        "save_pipeline_event",
        lambda *args, **kwargs: events.append(args),
    )


def test_explicit_retrain_fails_when_expected_candidate_artifact_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    paths = _prediction_paths(tmp_path)
    events: list[tuple] = []
    _patch_prediction_dependencies(monkeypatch, paths, events)

    with pytest.raises(RuntimeError, match="未生成预期 artifact"):
        prediction_service.run_prediction(
            config={},
            run_context={"run_id": "run_training_missing", "run_mode": "retrain_model"},
            log=lambda _message: None,
        )

    assert any(item[1] == "candidate_registration" and item[2] == "failed" for item in events)


def test_explicit_retrain_requires_successful_candidate_registration(
    monkeypatch, tmp_path: Path
) -> None:
    paths = _prediction_paths(tmp_path)
    artifact_dir = paths.root_dir / "model_artifacts" / "model_run_training_ok"
    events: list[tuple] = []
    _patch_prediction_dependencies(monkeypatch, paths, events)
    monkeypatch.setattr(
        prediction_service,
        "run_prediction_engine",
        lambda *args, **kwargs: (
            artifact_dir.mkdir(parents=True),
            SimpleNamespace(returncode=0),
        )[1],
    )
    monkeypatch.setattr(
        prediction_service,
        "register_model_artifact",
        lambda *args, **kwargs: "model_run_training_ok",
    )
    monkeypatch.setattr(prediction_service, "register_strategy_result", lambda *args, **kwargs: None)

    result = prediction_service.run_prediction(
        config={},
        run_context={"run_id": "run_training_ok", "run_mode": "retrain_model"},
        log=lambda _message: None,
    )

    assert result.returncode == 0
    assert any(item[1] == "candidate_registration" and item[2] == "completed" for item in events)


def test_model_center_start_uses_real_dispatcher_instead_of_manual_pending(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dispatcher,
        "enqueue_task",
        lambda kind, payload: {
            "task_id": "task_training_real",
            "run_id": "run_training_real",
            "status": "queued",
            "kind": kind,
            "payload": payload,
            "queue_name": "forecast_final_rc",
            "celery_task_id": "celery-training-real",
        },
    )
    monkeypatch.setattr(
        model_repository,
        "record_model_event",
        lambda **kwargs: {"available": True, "event_id": "event-training-real"},
    )
    user = CurrentUser(
        user_id="admin-1",
        username="admin",
        role="admin",
        permissions=["model:manage"],
        auth_mode="unit_test",
    )

    result = model_repository.start_model_training(
        user=user,
        payload={"reason": "controlled training"},
    )

    assert result["status"] == "queued"
    assert result["kind"] == "retrain_model"
    assert result["celery_task_id"] == "celery-training-real"
    assert result["event_recorded"] is True


def test_command_worker_propagates_task_run_identity(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}
    saved_records: list[dict] = []

    class FakeProcess:
        returncode = 0

        def poll(self):
            return 0

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(tasks, "command_for_kind", lambda _kind: ["python", "training.py"])
    monkeypatch.setattr(tasks, "project_paths", lambda: SimpleNamespace(log_dir=tmp_path))
    monkeypatch.setattr(
        tasks,
        "save_task_record",
        lambda record, *args, **kwargs: saved_records.append(record) or True,
    )
    monkeypatch.setattr(tasks, "append_task_log", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        tasks,
        "get_task_record",
        lambda _task_id: {
            "timeout_seconds": 60,
            "payload": {"rolling_backtest": False, "reason": "unit"},
            "queue_name": "forecast_final_rc",
            "celery_task_id": "celery-training-identity",
        },
    )
    monkeypatch.setattr(tasks.subprocess, "Popen", fake_popen)

    result = tasks.run_command_task(
        "retrain_model", "task_training_identity", "run_training_identity"
    )

    assert result["status"] == "success"
    assert captured["env"]["PIPELINE_RUN_ID"] == "run_training_identity"
    assert captured["env"]["PIPELINE_TASK_ID"] == "task_training_identity"
    assert captured["env"]["ENABLE_ROLLING_BACKTEST"] == "0"
    assert saved_records[0]["payload"]["reason"] == "unit"
    assert saved_records[-1]["payload"]["rolling_backtest"] is False
    assert result["queue_name"] == "forecast_final_rc"
    assert result["celery_task_id"] == "celery-training-identity"
    assert all(record["queue_name"] == "forecast_final_rc" for record in saved_records)
    assert all(record["celery_task_id"] == "celery-training-identity" for record in saved_records)


def test_dispatcher_generates_collision_resistant_run_identity(monkeypatch) -> None:
    generated = dispatcher.generate_run_id()
    assert generated.startswith("run_")
    assert len(generated) > 30


def test_retrain_workspace_is_unique_and_run_scoped() -> None:
    config = {"paths": {}}
    root = main_daily_run.configure_retrain_workspace(config, "run_contract_20260830")

    assert root.name == "run_contract_20260830"
    assert config["paths"]["data_dir"] == str(root / "input")
    assert config["paths"]["result_table_dir"] == str(root / "results" / "结果表")

    with pytest.raises(SystemExit, match="非法字符"):
        main_daily_run.configure_retrain_workspace({"paths": {}}, "../escape")


def test_training_database_identity_is_required_before_connection(monkeypatch) -> None:
    monkeypatch.delenv(model_registry.MODEL_TRAINING_DATABASE_URL_ENV, raising=False)
    with pytest.raises(ModelFactError, match="缺少独立"):
        model_registry.create_model_training_engine()

    monkeypatch.setenv(
        model_registry.MODEL_TRAINING_DATABASE_URL_ENV,
        "postgresql+psycopg://beta10d_app_login:masked@localhost:5432/postgres",
    )
    with pytest.raises(ModelFactError, match="受限身份"):
        model_registry.create_model_training_engine()


def test_artifact_hash_manifest_is_static_and_fail_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "model_run_hash"
    artifact.mkdir()
    (artifact / "manifest.json").write_text('{"model_version":"model_run_hash"}', encoding="utf-8")
    (artifact / "base_model.joblib").write_bytes(b"newly-trained-model-bytes")

    first_hash = model_registry.write_artifact_hash_manifest(artifact)
    second_hash = model_registry.write_artifact_hash_manifest(artifact)
    assert first_hash == second_hash
    assert len(first_hash) == 64

    (artifact / "base_model.joblib").write_bytes(b"changed")
    with pytest.raises(ModelFactError, match="不一致"):
        model_registry.write_artifact_hash_manifest(artifact)


def test_candidate_registration_rejects_stale_declared_artifact_hash(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "model_run_declared_hash"
    artifact.mkdir()
    (artifact / "manifest.json").write_text(
        '{"model_version":"model_run_declared_hash","artifact_hash":"stale"}',
        encoding="utf-8",
    )
    (artifact / "metrics.json").write_text("{}", encoding="utf-8")
    (artifact / "base_model.joblib").write_bytes(b"newly-trained-model-bytes")

    with pytest.raises(ModelFactError, match="静态文件校验结果不一致"):
        model_registry.register_model_artifact({}, artifact)


def _load_training_engine(monkeypatch, tmp_path: Path):
    engine_path = Path(__file__).resolve().parents[1] / "高峰尖刺增强版_电力市场电价预测与智能分析系统_v4_fix1.py"
    monkeypatch.setenv("PIPELINE_RESULT_DIR", str(tmp_path / "engine-results"))
    spec = importlib.util.spec_from_file_location("training_engine_under_test", engine_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forward_forecast_inherits_error_memory_without_nan_fill(monkeypatch, tmp_path: Path) -> None:
    engine = _load_training_engine(monkeypatch, tmp_path)
    history_index = pd.date_range("2026-01-01", periods=240, freq="h")
    history = pd.DataFrame(
        {
            "datetime": history_index,
            "da_price": np.linspace(40.0, 80.0, len(history_index)),
            "forecast_load": np.linspace(1000.0, 1100.0, len(history_index)),
            "actual_load": np.linspace(995.0, 1095.0, len(history_index)),
            "temperature": 20.0,
            "wind_speed": 5.0,
            "precipitation": 0.0,
            "price_spread_rt_minus_da": 1.0,
        }
    )
    history = engine.run_full_feature_engineering(history)
    history.loc[history.index[-1], "hour_bias_mean"] = 1.25
    history.loc[history.index[-1], "scenario_mae"] = 2.5
    history.loc[history.index[-1], "historical_under_predict_rate"] = 0.4

    target_index = pd.date_range(history["datetime"].max() + pd.Timedelta(hours=1), periods=24, freq="h")
    future_base = pd.DataFrame(
        {
            "datetime": target_index,
            "forecast_load": 1105.0,
            "actual_load": 1100.0,
            "temperature": 21.0,
            "wind_speed": 4.0,
            "precipitation": 0.0,
            "price_spread_rt_minus_da": 1.0,
            "forecast_load_source": "controlled-test",
            "future_weather_source": "controlled-test",
            "actual_load_proxy_source": "controlled-test",
            "rt_spread_proxy_source": "controlled-test",
        }
    )
    monkeypatch.setattr(engine, "build_formal_forward_base_frame", lambda *_args: future_base.copy())

    class ConstantRegressor:
        def predict(self, frame):
            return np.full(len(frame), 60.0)

    class ConstantClassifier:
        def predict_proba(self, frame):
            return np.column_stack([np.full(len(frame), 0.8), np.full(len(frame), 0.2)])

    features = ["hour", "hour_bias_mean", "scenario_mae", "historical_under_predict_rate"]
    artifacts = {
        "final_base_model": ConstantRegressor(),
        "final_peak_model": ConstantRegressor(),
        "final_classifier": ConstantClassifier(),
        "final_p90_model": None,
        "best_alpha": 0.0,
        "best_floor": 0.0,
        "best_spike_threshold": 0.5,
    }

    result, snapshot = engine.generate_formal_forward_forecast(history, features, artifacts, history)

    assert len(result) == 24
    assert len(snapshot) == 24
    assert result["剩余缺失特征数量"].sum() == 0
    assert snapshot[features].notna().all().all()
    assert snapshot.iloc[0]["hour_bias_mean"] == pytest.approx(1.25)
    assert snapshot.iloc[0]["scenario_mae"] == pytest.approx(2.5)
    assert snapshot.iloc[0]["historical_under_predict_rate"] == pytest.approx(0.4)
