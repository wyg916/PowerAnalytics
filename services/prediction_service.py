from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd
from sqlalchemy import text

from automation_common import format_duration, get_pipeline_paths, get_run_context, load_config, setup_run_logger
from database_utils import (
    export_prediction_inputs_from_database,
    save_pipeline_event,
    sync_result_tables_to_database,
    write_excel_snapshot,
)
from model_ops.model_registry import create_model_training_engine, register_model_artifact
from model_ops.prediction_tracker import build_prediction_tracking_frame, track_future_prediction_file, write_prediction_tracking
from model_ops.strategy_memory import register_strategy_result
from prediction_engine.fast_forecast import forecast_with_saved_model
from prediction_engine.pipeline import run_prediction_engine


LogFunc = Callable[[str], None] | None


@dataclass
class PredictionRunResult:
    engine_script: Path
    result_table_dir: Path
    elapsed: str
    returncode: int


def _export_retrain_inputs_from_postgres(data_dir: Path, log: LogFunc = None) -> dict[str, Any]:
    """从受限 PostgreSQL 事实表生成本次 run 独占的训练输入快照。"""

    if data_dir.exists():
        raise FileExistsError(f"显式重训输入目录已存在，拒绝覆盖：{data_dir}")
    engine = create_model_training_engine()
    try:
        with engine.connect() as conn:
            market = pd.read_sql(
                text(
                    """
                    SELECT datetime,
                           MAX(da_price) FILTER (WHERE da_price IS NOT NULL) AS da_price,
                           MAX(rt_price) FILTER (WHERE rt_price IS NOT NULL) AS rt_price
                    FROM raw_market
                    GROUP BY datetime
                    ORDER BY datetime
                    """
                ),
                conn,
            )
            load = pd.read_sql(
                text(
                    """
                    SELECT datetime,
                           MAX(actual_load) FILTER (WHERE actual_load IS NOT NULL) AS actual_load,
                           MAX(forecast_load) FILTER (WHERE forecast_load IS NOT NULL) AS forecast_load,
                           MAX(NULLIF(raw_json->>'forecast_evaluated_at', '')::timestamp)
                               FILTER (WHERE forecast_load IS NOT NULL) AS forecast_evaluated_at,
                           MAX(NULLIF(raw_json->>'forecast_evaluated_at_utc', '')::timestamptz)
                               FILTER (WHERE forecast_load IS NOT NULL) AS forecast_evaluated_at_utc
                    FROM raw_load
                    GROUP BY datetime
                    ORDER BY datetime
                    """
                ),
                conn,
            )
            weather = pd.read_sql(
                text(
                    """
                    SELECT datetime,
                           MAX(temperature) FILTER (WHERE temperature IS NOT NULL) AS temperature,
                           MAX(wind_speed) FILTER (WHERE wind_speed IS NOT NULL) AS wind_speed,
                           MAX(NULLIF(raw_json->>'precipitation', '')::double precision)
                               FILTER (WHERE raw_json->>'precipitation' IS NOT NULL) AS precipitation
                    FROM raw_weather
                    GROUP BY datetime
                    ORDER BY datetime
                    """
                ),
                conn,
            )
    finally:
        engine.dispose()

    master = market.merge(load[["datetime", "actual_load", "forecast_load"]], on="datetime", how="inner")
    master = master.merge(weather, on="datetime", how="inner")
    master["price_spread_rt_minus_da"] = master["rt_price"] - master["da_price"]
    required = ["da_price", "actual_load", "forecast_load", "temperature", "wind_speed", "precipitation"]
    master = master.dropna(subset=required).sort_values("datetime").drop_duplicates("datetime", keep="last")
    forecast = load.dropna(subset=["forecast_load"]).sort_values("datetime").drop_duplicates("datetime", keep="last")
    if len(master) < 8760:
        raise RuntimeError(f"PostgreSQL 训练主表有效记录不足：{len(master)} < 8760")
    if master["datetime"].duplicated().any() or forecast["datetime"].duplicated().any():
        raise RuntimeError("PostgreSQL 训练输入存在重复小时")
    if master[required].isna().any().any():
        raise RuntimeError("PostgreSQL 训练主表核心字段存在空值")

    data_dir.mkdir(parents=True, exist_ok=False)
    write_excel_snapshot(data_dir / "master_table.xlsx", master.reset_index(drop=True))
    write_excel_snapshot(data_dir / "forecast_load_selected.xlsx", forecast.reset_index(drop=True))
    summary = {
        "master_rows": int(len(master)),
        "forecast_rows": int(len(forecast)),
        "start": str(pd.to_datetime(master["datetime"]).min()),
        "end": str(pd.to_datetime(master["datetime"]).max()),
        "source": "postgresql.raw_market+raw_load+raw_weather",
        "database_identity": "beta10d_forecast_login",
    }
    if log:
        log(
            "显式重训输入已从受限 PostgreSQL 导出："
            f"主表 {summary['master_rows']} 行，负荷预测 {summary['forecast_rows']} 行，"
            f"范围 {summary['start']} 至 {summary['end']}。"
        )
    return summary


def _is_fast_mode(env: Mapping[str, str] | None, explicit: bool) -> bool:
    return explicit or bool(env and str(env.get("PIPELINE_FORECAST_MODE", "")).strip().lower() == "fast")


def _write_fast_prediction_tracking(config: dict[str, Any], result, context: dict[str, Any], log: LogFunc = None) -> None:
    if not result.future_result_path.exists():
        return
    future_result = pd.read_excel(result.future_result_path, engine="openpyxl")
    tracking_df = build_prediction_tracking_frame(
        future_result,
        run_id=context["run_id"],
        model_version=result.model_version,
        feature_version=result.feature_version,
    )
    write_prediction_tracking(config, tracking_df, run_id=context["run_id"], log=log)


def _run_fast_forecast(config: dict[str, Any], context: dict[str, Any], paths, log: LogFunc = None) -> PredictionRunResult:
    start = time.perf_counter()
    if log:
        log("启用快速预测模式：加载 Active 模型，不重新训练。")
    result = forecast_with_saved_model(config, run_context=context, log=log)
    elapsed = format_duration(time.perf_counter() - start)
    if log:
        log(f"Active 模型快速预测完成，耗时：{elapsed}。")
    save_pipeline_event(config, "fast_forecast", "completed", f"Active 模型快速预测完成，记录数：{result.rows}", context)

    if log:
        log("同步快速预测结果数据表到数据库。")
    sync_result_tables_to_database(
        paths.result_table_dir,
        config,
        run_context=context,
        log=log,
        filenames=[
            "18_未来24小时预测结果_正式版.xlsx",
            "18_未来24小时预测输入特征_正式版.xlsx",
            "19_业务统计摘要.xlsx",
        ],
    )
    save_pipeline_event(config, "prediction_results_sync", "completed", "快速预测结果数据表已同步到数据库", context)
    _write_fast_prediction_tracking(config, result, context, log=log)
    return PredictionRunResult(paths.engine_script, paths.result_table_dir, elapsed, 0)


def run_prediction(
    config: dict[str, Any] | None = None,
    run_context: dict[str, Any] | None = None,
    log: LogFunc = None,
    env: Mapping[str, str] | None = None,
    fast_forecast: bool = False,
) -> PredictionRunResult:
    config = config or load_config()
    paths = get_pipeline_paths(config)
    context = run_context or get_run_context()
    strict_candidate_registration = str(context.get("run_mode") or "").strip() == "retrain_model"
    if log is None:
        log, _ = setup_run_logger(paths.log_dir, "01_run_prediction")

    if not paths.engine_script.exists():
        raise FileNotFoundError(f"未找到预测引擎脚本：{paths.engine_script}")

    artifact_dir = paths.root_dir / "model_artifacts" / f"model_{context['run_id']}"
    if strict_candidate_registration:
        if artifact_dir.exists():
            raise FileExistsError(f"显式重训 artifact 目录已存在，拒绝覆盖：{artifact_dir}")
        log("通过 prediction_service 从受限 PostgreSQL 导出本次 run 独占训练输入。")
        export_summary = _export_retrain_inputs_from_postgres(paths.data_dir, log=log)
        save_pipeline_event(
            config,
            "prediction_input_export",
            "completed",
            f"受限 PostgreSQL 训练输入已导出，主表 {export_summary['master_rows']} 行",
            context,
        )
    else:
        log("通过 prediction_service 导出预测输入数据。")
        export_prediction_inputs_from_database(paths.data_dir, config, log=log)
        save_pipeline_event(config, "prediction_input_export", "completed", "已从数据库导出预测输入", context)

    if _is_fast_mode(env, fast_forecast):
        return _run_fast_forecast(config, context, paths, log=log)

    start = time.perf_counter()
    log(f"通过 prediction_engine.pipeline 执行完整训练预测引擎：{paths.engine_script.name}")
    completed = run_prediction_engine(paths.engine_script, cwd=paths.root_dir, env=env)
    if completed.returncode != 0:
        save_pipeline_event(config, "prediction_engine", "failed", f"返回码：{completed.returncode}", context)
        raise SystemExit(completed.returncode)

    elapsed = format_duration(time.perf_counter() - start)
    log(f"预测引擎执行完成，耗时：{elapsed}。")
    save_pipeline_event(config, "prediction_engine", "completed", f"预测引擎执行完成，耗时：{elapsed}", context)

    log("同步预测结果数据表到数据库。")
    sync_result_tables_to_database(paths.result_table_dir, config, run_context=context, log=log)
    save_pipeline_event(config, "prediction_results_sync", "completed", "预测结果数据表已同步到数据库", context)

    future_result_path = paths.result_table_dir / "18_未来24小时预测结果_正式版.xlsx"
    candidate_version = ""
    if artifact_dir.exists():
        try:
            candidate_version = register_model_artifact(config, artifact_dir, status="candidate")
            log(f"模型 artifact 已登记为 candidate：{candidate_version}")
            register_strategy_result(config, artifact_dir, log=log)
            if future_result_path.exists():
                track_future_prediction_file(config, future_result_path, artifact_dir, context["run_id"], log=log)
        except Exception as exc:
            if strict_candidate_registration:
                save_pipeline_event(
                    config,
                    "candidate_registration",
                    "failed",
                    "显式重训未能登记 Candidate，训练任务失败关闭",
                    context,
                )
                raise RuntimeError("显式重训未能登记 Candidate，任务已失败关闭") from exc
            log(f"模型注册、策略记忆或预测追踪写入失败，不影响普通预测主流程：{exc}")
    else:
        if strict_candidate_registration:
            save_pipeline_event(
                config,
                "candidate_registration",
                "failed",
                "显式重训未生成预期 artifact 目录",
                context,
            )
            raise RuntimeError(f"显式重训未生成预期 artifact 目录：{artifact_dir}")
        log(f"未发现本次模型 artifact 目录，跳过模型注册：{artifact_dir}")

    if strict_candidate_registration:
        if not candidate_version:
            raise RuntimeError("显式重训没有生成可登记的 Candidate")
        save_pipeline_event(
            config,
            "candidate_registration",
            "completed",
            f"Candidate 已登记：{candidate_version}",
            context,
        )

    return PredictionRunResult(paths.engine_script, paths.result_table_dir, elapsed, completed.returncode)
