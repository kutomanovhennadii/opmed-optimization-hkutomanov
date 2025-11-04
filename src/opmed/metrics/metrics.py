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
    @brief
    Builds a JSON-serializable dictionary of solver run metrics.

    @details
    Requires a schedule with timestamps (solution.csv / assignments_df / solution_rows).
    Exceptions follow ADR-008 (DataError / ValidationError).
    """
    _require_result_schema(result)

    status = str(result.get("status", "UNKNOWN") or "UNKNOWN")

    assignments = result.get("assignments")
    if not assignments:
        # (1) No solution → return an empty metrics report without loading schedule DataFrame
        runtime_raw = result.get("runtime", 0.0)
        runtime_sec = (
            float(runtime_raw)
            if isinstance(runtime_raw, (int | float | str)) and runtime_raw not in (None, "")
            else 0.0
        )

        # (2) Collect basic solver information
        solver_info = {
            "engine": "CP-SAT",
            "num_workers": int(getattr(getattr(cfg, "solver", object()), "num_workers", 0)),
            "seed": int(getattr(getattr(cfg, "solver", object()), "random_seed", 0)),
        }
        try:
            solver_info["version"] = getattr(ortools, "__version__", "unknown")
        except Exception:
            pass

        # (3) Compose minimal metrics dictionary
        metrics = {
            "timestamp": _utc_now_iso(),
            "solver_status": status,
            "total_cost": 0.0,
            "utilization": 0.0,
            "runtime_sec": runtime_sec,
            "num_anesthetists": 0,
            "num_rooms_used": 0,
            "num_surgeries": 0,
            "solver": solver_info,
        }

        json.dumps(metrics, ensure_ascii=False)
        return metrics

    # (4) Extract objective and runtime values
    objective_raw = result.get("objective", 0.0)
    total_cost = (
        float(objective_raw)
        if isinstance(objective_raw, (int | float | str)) and objective_raw not in (None, "")
        else 0.0
    )

    runtime_raw = result.get("runtime", 0.0)
    runtime_sec = (
        float(runtime_raw)
        if isinstance(runtime_raw, (int | float | str)) and runtime_raw not in (None, "")
        else 0.0
    )

    # (5) Load schedule DataFrame (used for utilization and counts)
    df = _load_schedule_dataframe(result)

    # (6) Compute counts for surgeries, anesthetists, and rooms
    num_surgeries, num_anesthetists, num_rooms = _compute_counts(result, df)

    # (7) Compute utilization according to Theoretical_Model / ADR-006
    utilization = _compute_utilization(df, cfg)

    # (8) Collect solver information again for completeness
    solver_info = {
        "engine": "CP-SAT",
        "num_workers": int(getattr(getattr(cfg, "solver", object()), "num_workers", 0)),
        "seed": int(getattr(getattr(cfg, "solver", object()), "random_seed", 0)),
    }
    try:
        solver_info["version"] = getattr(ortools, "__version__", "unknown")
    except Exception:
        pass

    # (9) Assemble final metrics structure
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

    # (10) Validate numerical integrity and serializability
    _assert_no_nans(metrics)
    json.dumps(metrics, ensure_ascii=False)
    return metrics


# ----------------- internal -----------------


def _require_result_schema(result: dict[str, Any]) -> None:
    """
    @brief
    Ensures that the result dictionary contains required keys and correct types.

    @details
    Supports both 'assignments' (preferred) and legacy 'assignment' key.
    Raises DataError if required keys or expected value types are missing.
    """
    # (1) Backward compatibility with legacy key name
    if "assignments" not in result and "assignment" in result:
        result["assignments"] = result["assignment"]

    # (2) Validate key presence
    required = ["status", "objective", "runtime", "assignments"]
    missing = [k for k in required if k not in result]
    if missing:
        raise DataError(
            f"Missing SolveResult keys: {', '.join(missing)}",
            source="metrics.collect_metrics",
            suggested_action="Ensure Optimizer returns the standard result dictionary with 'assignments'.",
        )

    # (3) Validate type of 'assignments'
    val = result["assignments"]
    if not isinstance(val, (dict | list)):
        raise DataError(
            "result['assignments'] must be a dict or list of SolutionRow.",
            source="metrics.collect_metrics",
            suggested_action="Return {'x': [...], 'y': [...]} or structured SolutionRow list.",
        )


def _load_schedule_dataframe(result: dict[str, Any]) -> pd.DataFrame:
    """
    @brief
    Loads the schedule DataFrame with required columns.

    @details
    Columns required: surgery_id, start_time, end_time, anesthetist_id, room_id.
    Priority of sources:
        (1) result['solution_path'] → CSV file
        (2) result['assignments_df'] → pandas DataFrame
        (3) result['solution_rows'] → list[dict]
    Raises DataError if no suitable schedule found.
    """
    # (1) Try reading from CSV
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

    # (2) Use assignments_df if provided
    df = result.get("assignments_df")
    if df is not None:
        return _normalize_df(df)

    # (3) Use solution_rows if available
    rows = result.get("solution_rows")
    if rows is not None:
        return _normalize_df(pd.DataFrame(rows))

    # (4) No valid schedule found
    raise DataError(
        "Schedule with timestamps not found to compute utilization.",
        source="metrics.collect_metrics",
        suggested_action="Provide result['solution_path'] to CSV or 'assignments_df'/'solution_rows'.",
    )


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    @brief
    Normalizes and validates the schedule DataFrame.

    @details
    Ensures required columns exist and timestamps are parsed as UTC.
    Raises DataError on missing columns or parsing failure,
    and ValidationError if any non-positive durations are found.
    """
    # (1) Validate required columns
    required = {"surgery_id", "start_time", "end_time", "anesthetist_id", "room_id"}
    missing = required - set(map(str, df.columns))
    if missing:
        raise DataError(
            "Schedule is missing columns: " + ", ".join(sorted(missing)),
            source="metrics.collect_metrics",
            suggested_action="Ensure solution.csv / DataFrame has required columns.",
        )

    # (2) Copy and convert timestamps to UTC
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

    # (3) Validate positive durations
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
    """
    @brief
    Computes basic entity counts from the schedule.

    @details
    Returns number of surgeries, anesthetists, and rooms.
    """
    n_s = int(len(df))
    n_a = int(df["anesthetist_id"].nunique())
    n_r = int(df["room_id"].nunique())
    return n_s, n_a, n_r


def _compute_utilization(df: pd.DataFrame, cfg: Any) -> float:
    """
    @brief
    Computes utilization ratio for anesthetists.

    @details
    Formula follows Theoretical_Model / ADR-006:
        utilization = total_surgery_hours / total_cost_hours.
    Considers shift_min, shift_overtime, and overtime_multiplier parameters.
    Raises DataError if computed value is non-finite.
    """
    # (1) Compute total surgery duration in hours
    dur_hours = (df["end_time"] - df["start_time"]).dt.total_seconds() / 3600.0
    total_surgery_hours = float(dur_hours.sum())

    # (2) Retrieve configuration parameters
    shift_min = float(getattr(cfg, "shift_min", 5.0))
    shift_overtime = float(getattr(cfg, "shift_overtime", 9.0))
    m = float(getattr(cfg, "overtime_multiplier", 1.5))

    # (3) Aggregate anesthetist spans
    per_a = df.groupby("anesthetist_id", as_index=False).agg(
        start=("start_time", "min"), end=("end_time", "max")
    )
    span_hours = (per_a["end"] - per_a["start"]).dt.total_seconds() / 3600.0

    # (4) Compute effective total cost hours
    total_cost_hours = 0.0
    for d in span_hours.to_numpy():
        d = float(d)
        base = max(shift_min, d)
        overtime = max(0.0, d - shift_overtime)
        total_cost_hours += base + (m - 1.0) * overtime

    # (5) Handle edge cases and compute utilization
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
    """
    @brief
    Validates that object contains no NaN or infinite values.

    @details
    Recursively traverses dicts, lists, and tuples to ensure all numeric
    values are finite. Raises DataError on detection.
    """
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
    """
    @brief
    Returns current UTC timestamp in ISO-8601 format (Z-suffix).

    @details
    Microseconds are stripped to keep deterministic filenames and logs.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _f(x: float) -> float:
    """
    @brief
    Normalizes floating-point precision.

    @details
    Converts tiny absolute values (<1e-15) to zero to avoid noise in metrics.
    """
    return 0.0 if abs(x) < 1e-15 else float(x)
