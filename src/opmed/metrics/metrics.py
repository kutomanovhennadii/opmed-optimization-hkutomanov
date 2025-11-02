# src/opmed/metrics/metrics.py
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ortools
import pandas as pd

from opmed.errors import DataError, ValidationError


def collect_metrics(result: dict[str, Any], cfg: Any) -> dict[str, Any]:
    """
    Возвращает JSON-сериализуемый dict метрик запуска решателя.
    Требует расписание с временными метками (solution.csv / assignments_df / solution_rows).
    Исключения соответствуют ADR-008 (DataError / ValidationError).
    """
    _require_result_schema(result)

    status = str(result["status"])
    total_cost = float(result.get("objective", 0.0))
    runtime_sec = float(result.get("runtime", 0.0))

    # Получаем датафрейм расписания (нужен для utilization и счётчиков)
    df = _load_schedule_dataframe(result)

    # Счётчики
    num_surgeries, num_anesthetists, num_rooms = _compute_counts(result, df)

    # Utilization по формуле из Theoretical_Model / ADR-006
    utilization = _compute_utilization(df, cfg)

    # Инфо о солвере
    solver_info = {
        "engine": "CP-SAT",
        "num_workers": int(getattr(getattr(cfg, "solver", object()), "num_workers", 0)),
        "seed": int(getattr(getattr(cfg, "solver", object()), "random_seed", 0)),
    }
    try:
        solver_info["version"] = getattr(ortools, "__version__", "unknown")
    except Exception:
        pass

    metrics = {
        "timestamp": _utc_now_iso(),
        "solver_status": status,
        "total_cost": _f(total_cost),
        "utilization": _f(utilization),
        "runtime_sec": _f(runtime_sec),
        "num_anesthetists": int(num_anesthetists),
        "num_rooms_used": int(num_rooms),
        "num_surgeries": int(num_surgeries),
        "solver": solver_info,
    }

    _assert_no_nans(metrics)
    json.dumps(metrics, ensure_ascii=False)  # проверка сериализуемости
    return metrics


# ----------------- internal -----------------


def _require_result_schema(result: dict[str, Any]) -> None:
    required = ["status", "objective", "runtime", "assignment"]
    missing = [k for k in required if k not in result]
    if missing:
        raise DataError(
            f"Missing SolveResult keys: {', '.join(missing)}",
            source="metrics.collect_metrics",
            suggested_action="Ensure Optimizer returns the standard result dictionary.",
        )
    if not isinstance(result["assignment"], dict):
        raise DataError(
            "result['assignment'] must be a dict",
            source="metrics.collect_metrics",
            suggested_action="Return {'x': [...], 'y': [...]} as described in solvercore.md.",
        )


def _load_schedule_dataframe(result: dict[str, Any]) -> pd.DataFrame:
    """
    Ищем расписание с колонками: surgery_id, start_time, end_time, anesthetist_id, room_id.
    Приоритет:
      1) result['solution_path'] -> CSV
      2) result['assignments_df'] (pandas.DataFrame)
      3) result['solution_rows'] (list[dict])
    """
    # 1) CSV
    solution_path = result.get("solution_path")
    if solution_path:
        p = Path(str(solution_path))
        if p.exists() and p.is_file():
            try:
                df = pd.read_csv(p)
            except Exception as e:
                raise DataError(
                    f"Failed to read solution CSV: {e}",
                    source="metrics.collect_metrics",
                    suggested_action="Validate solution.csv encoding and columns.",
                )
            return _normalize_df(df)

    # 2) DataFrame
    df = result.get("assignments_df")
    if df is not None:
        return _normalize_df(df)

    # 3) Rows list
    rows = result.get("solution_rows")
    if rows is not None:
        return _normalize_df(pd.DataFrame(rows))

    # Ничего пригодного не нашли
    raise DataError(
        "Schedule with timestamps not found to compute utilization.",
        source="metrics.collect_metrics",
        suggested_action="Provide result['solution_path'] to CSV or 'assignments_df'/'solution_rows'.",
    )


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    required = {"surgery_id", "start_time", "end_time", "anesthetist_id", "room_id"}
    missing = required - set(map(str, df.columns))
    if missing:
        raise DataError(
            "Schedule is missing columns: " + ", ".join(sorted(missing)),
            source="metrics.collect_metrics",
            suggested_action="Ensure solution.csv / DataFrame has required columns.",
        )
    df = df.copy()
    try:
        ts_start = pd.to_datetime(df["start_time"], utc=True, errors="raise")
        ts_end = pd.to_datetime(df["end_time"], utc=True, errors="raise")
    except Exception as e:
        raise DataError(
            f"Datetime parse failed: {e}",
            source="metrics.collect_metrics",
            suggested_action="Use ISO-8601 timestamps with timezone.",
        )
    df["start_time"] = ts_start.dt.tz_convert("UTC")
    df["end_time"] = ts_end.dt.tz_convert("UTC")
    df["surgery_id"] = df["surgery_id"].astype(str)
    df["anesthetist_id"] = df["anesthetist_id"].astype(str)
    df["room_id"] = df["room_id"].astype(str)

    bad_mask = ~(df["end_time"] > df["start_time"])
    if bool(bad_mask.any()):
        bad = df.loc[bad_mask, "surgery_id"].astype(str).tolist()
        raise ValidationError(
            f"Non-positive durations for surgeries: {bad}",
            source="metrics.collect_metrics",
            suggested_action="Fix start_time/end_time values.",
        )
    return df


def _compute_counts(result: dict[str, Any], df: pd.DataFrame) -> tuple[int, int, int]:
    n_s = int(len(df))
    n_a = int(df["anesthetist_id"].nunique())
    n_r = int(df["room_id"].nunique())
    return n_s, n_a, n_r


def _compute_utilization(df: pd.DataFrame, cfg: Any) -> float:
    # Σ(duration_surgeries) (часы)
    dur_hours = (df["end_time"] - df["start_time"]).dt.total_seconds() / 3600.0
    total_surgery_hours = float(dur_hours.sum())

    shift_min = float(getattr(cfg, "shift_min", 5.0))
    shift_overtime = float(getattr(cfg, "shift_overtime", 9.0))
    m = float(getattr(cfg, "overtime_multiplier", 1.5))

    per_a = df.groupby("anesthetist_id", as_index=False).agg(
        start=("start_time", "min"), end=("end_time", "max")
    )
    span_hours = (per_a["end"] - per_a["start"]).dt.total_seconds() / 3600.0

    total_cost_hours = 0.0
    for d in span_hours.to_numpy():
        d = float(d)
        base = max(shift_min, d)
        overtime = max(0.0, d - shift_overtime)
        total_cost_hours += base + (m - 1.0) * overtime

    if total_cost_hours <= 0.0:
        return 0.0

    util = total_surgery_hours / total_cost_hours
    if not math.isfinite(util):
        raise DataError(
            "Utilization computed as non-finite value.",
            source="metrics.collect_metrics",
            suggested_action="Inspect input schedule; check times and units.",
        )
    return float(util)


def _assert_no_nans(obj: Any) -> None:
    if obj is None:
        raise DataError("None encountered in metrics", source="metrics.collect_metrics")
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise DataError("NaN/Inf encountered in metrics", source="metrics.collect_metrics")
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_no_nans(v)
    elif isinstance(obj, (list | tuple)):
        for v in obj:
            _assert_no_nans(v)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _f(x: float) -> float:
    return 0.0 if abs(x) < 1e-15 else float(x)
