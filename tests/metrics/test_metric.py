import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from opmed.errors import DataError, ValidationError

# IMPORTANT: import the correct module (metrics.py)
from opmed.metrics.metrics import (
    _assert_no_nans,
    _compute_counts,
    _compute_utilization,
    _f,
    _normalize_df,
    _utc_now_iso,
    collect_metrics,
)

# -------------------------
# Helper utilities
# -------------------------


def _fake_cfg(
    shift_min=5.0,
    shift_overtime=9.0,
    overtime_multiplier=1.5,
    solver_num_workers=2,
    solver_seed=123,
):
    """
    @brief
    Creates a simplified configuration stub for tests.

    @details
    Returns a SimpleNamespace mimicking the real config structure,
    including solver parameters and shift thresholds.
    """
    return SimpleNamespace(
        shift_min=shift_min,
        shift_overtime=shift_overtime,
        overtime_multiplier=overtime_multiplier,
        solver=SimpleNamespace(num_workers=solver_num_workers, random_seed=solver_seed),
    )


def _df_sample(utc_start: datetime) -> pd.DataFrame:
    """
    @brief
    Builds a minimal synthetic DataFrame with two surgeries.

    @details
    One anesthetist works in two rooms, each for one hour.
    Start times and end times are UTC ISO strings.
    """
    return pd.DataFrame(
        {
            "surgery_id": ["s1", "s2"],
            "start_time": [
                utc_start.isoformat(),
                (utc_start + timedelta(hours=1, minutes=30)).isoformat(),
            ],
            "end_time": [
                (utc_start + timedelta(hours=1)).isoformat(),
                (utc_start + timedelta(hours=2, minutes=30)).isoformat(),
            ],
            "anesthetist_id": ["a1", "a1"],
            "room_id": ["r1", "r2"],
        }
    )


def _result_base() -> dict:
    """
    @brief
    Creates a minimal valid SolveResult dictionary.

    @details
    Mimics a feasible optimization result with basic fields:
    status, objective, runtime, and empty assignment.
    """
    return {
        "status": "FEASIBLE",
        "objective": 123.0,
        "runtime": 0.42,
        "assignment": {"x": [], "y": []},
    }


# -------------------------
# Tests for _normalize_df
# -------------------------


def test_normalize_df_ok_converts_to_utc_and_types():
    """
    @brief
    Ensures _normalize_df correctly converts columns and datatypes.

    @details
    Verifies that all expected columns are present, datetime fields are timezone-aware (UTC),
    and ID columns remain strings.
    """
    # --- Arrange ---
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)

    # --- Act ---
    out = _normalize_df(df)

    # --- Assert ---
    # Columns check
    assert set(["surgery_id", "start_time", "end_time", "anesthetist_id", "room_id"]).issubset(
        set(out.columns)
    )
    # Time columns — timezone-aware UTC
    assert str(out["start_time"].dtype) == "datetime64[ns, UTC]"
    assert str(out["end_time"].dtype) == "datetime64[ns, UTC]"
    # ID types — string (object)
    assert out["surgery_id"].dtype == "object"
    assert out["anesthetist_id"].dtype == "object"
    assert out["room_id"].dtype == "object"


def test_normalize_df_missing_columns_raises_data_error():
    """
    @brief
    Raises DataError if required columns are missing.

    @details
    Provides a DataFrame without 'end_time' and other fields,
    expecting a descriptive DataError.
    """
    # --- Arrange ---
    df = pd.DataFrame({"surgery_id": ["s1"], "start_time": ["2025-01-01T08:00:00Z"]})

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        _normalize_df(df)
    assert "Schedule is missing columns" in str(ei.value)


def test_normalize_df_bad_datetime_raises_data_error():
    """
    @brief
    Raises DataError on unparseable datetime strings.

    @details
    Verifies that invalid datetime values trigger a validation error,
    confirming that timestamp parsing is enforced.
    """
    # --- Arrange ---
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["NOT_A_TIME"],
            "end_time": ["2025-01-01T09:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        _normalize_df(df)
    assert "Datetime parse failed" in str(ei.value)


def test_normalize_df_non_positive_duration_raises_validation_error():
    """
    @brief
    Raises ValidationError when duration is non-positive.

    @details
    Ensures the validator rejects identical start and end timestamps.
    """
    # --- Arrange ---
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["2025-01-01T08:00:00Z"],
            "end_time": ["2025-01-01T08:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )

    # --- Act & Assert ---
    with pytest.raises(ValidationError) as ei:
        _normalize_df(df)
    assert "Non-positive durations" in str(ei.value)


# -------------------------
# Tests for _compute_counts
# -------------------------


def test_compute_counts_counts_unique_ids():
    """
    @brief
    Counts unique IDs correctly.

    @details
    Checks that _compute_counts returns accurate counts of surgeries,
    anesthetists, and rooms from a normalized dataset.
    """
    # --- Arrange ---
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _normalize_df(_df_sample(start))

    # --- Act ---
    n_s, n_a, n_r = _compute_counts(_result_base(), df)

    # --- Assert ---
    assert n_s == 2
    assert n_a == 1
    assert n_r == 2


# -------------------------
# Tests for _compute_utilization
# -------------------------


def test_compute_utilization_basic_formula():
    """
    @brief
    Verifies basic utilization formula without overtime.

    @details
    total_surgery_hours = 2
    total_span = 2.5h
    base = max(5, 2.5) = 5
    overtime = 0
    total_cost = 5
    utilization = 2 / 5 = 0.4
    """
    # --- Arrange ---
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _normalize_df(_df_sample(start))
    cfg = _fake_cfg(shift_min=5.0, shift_overtime=9.0, overtime_multiplier=1.5)

    # --- Act ---
    util = _compute_utilization(df, cfg)

    # --- Assert ---
    assert abs(util - 0.4) < 1e-9


def test_compute_utilization_with_overtime_multiplier():
    """
    @brief
    Validates utilization computation when overtime applies.

    @details
    total_surgery_hours = 12
    span = 12
    base = 12
    overtime = 3
    multiplier = 1.5
    total_cost = 13.5
    utilization = 12 / 13.5
    """
    # --- Arrange ---
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["2025-01-01T08:00:00Z"],
            "end_time": ["2025-01-01T20:00:00Z"],  # 12 hours
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    df = _normalize_df(df)
    cfg = _fake_cfg(shift_min=5.0, shift_overtime=9.0, overtime_multiplier=1.5)

    # --- Act ---
    util = _compute_utilization(df, cfg)

    # --- Assert ---
    assert abs(util - (12.0 / 13.5)) < 1e-9


def test_compute_utilization_empty_df_returns_zero():
    """
    @brief
    Ensures zero utilization for an empty dataset.

    @details
    An empty DataFrame should lead to zero computed utilization,
    as there are no surgeries to accumulate total hours.
    """
    # --- Arrange ---
    df = _normalize_df(
        pd.DataFrame(
            {
                "surgery_id": [],
                "start_time": [],
                "end_time": [],
                "anesthetist_id": [],
                "room_id": [],
            }
        )
    )
    cfg = _fake_cfg()

    # --- Act & Assert ---
    assert _compute_utilization(df, cfg) == 0.0


# -------------------------
# Tests for _assert_no_nans
# -------------------------


def test_assert_no_nans_passes_on_clean_structures():
    """
    @brief
    Passes on clean nested structures without NaN, inf, or None.

    @details
    Ensures recursive traversal handles dicts and lists correctly.
    """
    # --- Act & Assert ---
    _assert_no_nans({"a": 1.0, "b": [2.0, 3.0], "c": {"d": 4.0}})


def test_assert_no_nans_raises_on_nan():
    """
    @brief
    Raises DataError when encountering NaN.

    @details
    Validates that the guard clause detects invalid numeric values.
    """
    # --- Act & Assert ---
    with pytest.raises(DataError):
        _assert_no_nans(float("nan"))


def test_assert_no_nans_raises_on_inf():
    """
    @brief
    Raises DataError when encountering infinity.

    @details
    Infinite numeric values must trigger a DataError.
    """
    # --- Act & Assert ---
    with pytest.raises(DataError):
        _assert_no_nans(float("inf"))


def test_assert_no_nans_raises_on_none():
    """
    @brief
    Raises DataError when encountering None.

    @details
    Ensures the validator rejects None values in any structure.
    """
    # --- Act & Assert ---
    with pytest.raises(DataError):
        _assert_no_nans(None)


# -------------------------
# Tests for _utc_now_iso and _f
# -------------------------


def test_utc_now_iso_format():
    """
    @brief
    Confirms ISO formatting and timezone correctness of _utc_now_iso().

    @details
    Checks for trailing 'Z', timezone awareness, and microsecond precision zeroing.
    """
    # --- Act ---
    s = _utc_now_iso()
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))

    # --- Assert ---
    assert s.endswith("Z")
    assert dt.tzinfo is not None
    assert dt.microsecond == 0


def test_f_small_number_zeroing_and_passthrough():
    """
    @brief
    Ensures _f() zeroes out tiny numbers and passes larger ones unchanged.

    @details
    Numbers smaller than 1e-15 in magnitude are floored to 0.0.
    """
    # --- Act & Assert ---
    assert _f(1e-16) == 0.0
    assert _f(-1e-16) == 0.0
    assert _f(1e-12) == 1e-12
    assert _f(-1e-12) == -1e-12


# -------------------------
# Tests for collect_metrics (public API)
# -------------------------


def test_collect_metrics_from_dataframe(monkeypatch):
    """
    @brief
    Validates collect_metrics() when input is a populated DataFrame.

    @details
    Ensures that all derived fields (timestamp, solver info, counts, etc.)
    are computed correctly and that the result is JSON-serializable.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)

    # Fix timestamp for snapshot stability
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    cfg = _fake_cfg()

    # --- Act ---
    out = collect_metrics(base, cfg)

    # --- Assert ---
    assert out["timestamp"] == "2025-01-01T00:00:00Z"
    assert out["solver_status"] == "FEASIBLE"
    assert isinstance(out["total_cost"], float)
    assert isinstance(out["runtime_sec"], float)
    assert out["num_surgeries"] == 2
    assert out["num_anesthetists"] == 1
    assert out["num_rooms_used"] == 2

    solver_info = out["solver"]
    assert solver_info["engine"] == "CP-SAT"
    assert solver_info["num_workers"] == 2
    assert solver_info["seed"] == 123

    # Must be JSON-serializable
    json.dumps(out, ensure_ascii=False)


def test_collect_metrics_from_rows_list(monkeypatch):
    """
    @brief
    Validates collect_metrics() with solution rows passed as list of dicts.

    @details
    Confirms that collect_metrics reconstructs a DataFrame internally,
    computes metrics correctly, and reflects the solver configuration.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)
    base["solution_rows"] = df.to_dict(orient="records")

    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-02-02T00:00:00Z")
    cfg = _fake_cfg(solver_num_workers=8, solver_seed=77)

    # --- Act ---
    out = collect_metrics(base, cfg)

    # --- Assert ---
    assert out["timestamp"] == "2025-02-02T00:00:00Z"
    assert out["num_surgeries"] == 2
    assert out["solver"]["num_workers"] == 8
    assert out["solver"]["seed"] == 77


def test_collect_metrics_from_csv(tmp_path, monkeypatch):
    """
    @brief
    Validates collect_metrics() when reading from a CSV file.

    @details
    Ensures that metrics are derived from the CSV when the solution_path key is provided.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)
    p = tmp_path / "solution.csv"
    df.to_csv(p, index=False, encoding="utf-8")

    base = _result_base()
    base["solution_path"] = str(p)

    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-03-03T00:00:00Z")
    cfg = _fake_cfg()

    # --- Act ---
    out = collect_metrics(base, cfg)

    # --- Assert ---
    assert out["timestamp"] == "2025-03-03T00:00:00Z"
    assert out["num_surgeries"] == 2


def test_collect_metrics_prefers_csv_when_present(tmp_path, monkeypatch):
    """
    @brief
    Ensures that CSV source has priority over in-memory DataFrame.

    @details
    When both `solution_path` and `assignments_df` exist,
    the function must load the CSV and ignore the DataFrame content.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df_df = _df_sample(start)

    # Create a CSV with different content (1 surgery only)
    df_csv = df_df.iloc[:1].copy()
    p = tmp_path / "solution.csv"
    df_csv.to_csv(p, index=False, encoding="utf-8")

    base = _result_base()
    base["solution_path"] = str(p)
    base["assignments_df"] = df_df  # should be ignored

    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-04-04T00:00:00Z")
    cfg = _fake_cfg()

    # --- Act ---
    out = collect_metrics(base, cfg)

    # --- Assert ---
    assert out["num_surgeries"] == 1  # CSV was used


def test_collect_metrics_missing_required_keys_raises():
    """
    @brief
    Raises DataError if SolveResult lacks required keys.

    @details
    Ensures that the function fails fast when mandatory fields like
    objective or assignment are missing from the result dictionary.
    """
    # --- Arrange ---
    bad = {"status": "FEASIBLE", "runtime": 0.1, "assignment": {"x": [], "y": []}}

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        collect_metrics(bad, _fake_cfg())

    assert "Missing SolveResult keys" in str(ei.value)


def test_collect_metrics_assignment_must_be_dict():
    """
    @brief
    Raises DataError when assignment field is not a dictionary.

    @details
    Ensures the validation correctly rejects any non-dict structure
    and provides a descriptive error message indicating missing timestamps.
    """
    # --- Arrange ---
    bad = _result_base()
    bad["assignment"] = ["not", "a", "dict"]

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        collect_metrics(bad, _fake_cfg())

    msg = str(ei.value)
    assert "Schedule with timestamps not found" in msg
    assert "metrics.collect_metrics" in msg


def test_collect_metrics_csv_with_bad_datetime_raises_data_error(tmp_path):
    """
    @brief
    Raises DataError when CSV contains invalid datetime strings.

    @details
    Confirms that malformed timestamps trigger parsing failure detection.
    """
    # --- Arrange ---
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["BAD_TIME"],
            "end_time": ["2025-01-01T09:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    p = tmp_path / "solution.csv"
    df.to_csv(p, index=False, encoding="utf-8")

    base = _result_base()
    base["solution_path"] = str(p)

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())
    assert "Datetime parse failed" in str(ei.value)


def test_collect_metrics_when_no_schedule_sources_raises_data_error():
    """
    @brief
    Raises DataError when no schedule sources are provided.

    @details
    Ensures the collector refuses to operate without valid DataFrame,
    rows list, or CSV file source.
    """
    # --- Arrange ---
    base = _result_base()

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())
    assert "Schedule with timestamps not found" in str(ei.value)


def test_collect_metrics_handles_empty_schedule_utilization_zero(monkeypatch):
    """
    @brief
    Handles empty schedule gracefully with zero utilization.

    @details
    Verifies that collect_metrics() returns zeros for all count metrics
    when an empty DataFrame is provided.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    base = _result_base()
    empty = pd.DataFrame(
        {
            "surgery_id": [],
            "start_time": [],
            "end_time": [],
            "anesthetist_id": [],
            "room_id": [],
        }
    )
    base["assignments_df"] = empty
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-05-05T00:00:00Z")
    cfg = _fake_cfg()

    # --- Act ---
    out = collect_metrics(base, cfg)

    # --- Assert ---
    assert out["utilization"] == 0.0
    assert out["num_surgeries"] == 0
    assert out["num_anesthetists"] == 0
    assert out["num_rooms_used"] == 0


def test_collect_metrics_solver_version_present(monkeypatch):
    """
    @brief
    Includes solver version field when available.

    @details
    Confirms that collect_metrics() extracts ortools.__version__
    and stores it in solver metadata.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-06-06T00:00:00Z")
    monkeypatch.setattr(metric_mod.ortools, "__version__", "9.99.fake", raising=False)

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)

    # --- Act ---
    out = collect_metrics(base, _fake_cfg())

    # --- Assert ---
    assert out["solver"]["version"] == "9.99.fake"


def test_collect_metrics_solver_version_raises_exception(monkeypatch):
    """
    @brief
    Handles exception raised when reading ortools version.

    @details
    Confirms that collect_metrics() continues gracefully if
    accessing ortools.__version__ fails, omitting the field.
    """
    import opmed.metrics.metrics as metric_mod

    class BadOrtools:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    # --- Arrange ---
    monkeypatch.setattr(metric_mod, "ortools", BadOrtools())
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-07-07T00:00:00Z")

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)

    # --- Act ---
    out = collect_metrics(base, _fake_cfg())

    # --- Assert ---
    assert out["solver"]["engine"] == "CP-SAT"
    assert "version" not in out["solver"]


def test_load_schedule_dataframe_raises_dataerror_on_bad_csv(tmp_path, monkeypatch):
    """
    @brief
    Raises DataError when CSV reading fails inside _load_schedule_dataframe.

    @details
    Simulates ValueError from pandas.read_csv and ensures
    the exception is wrapped in a DataError with a clear message.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    bad_csv = tmp_path / "bad_solution.csv"
    bad_csv.write_text("corrupted,data\n1,2\n", encoding="utf-8")

    def broken_read_csv(path):
        raise ValueError("Simulated CSV read failure")

    monkeypatch.setattr(metric_mod.pd, "read_csv", broken_read_csv)

    base = _result_base()
    base["solution_path"] = str(bad_csv)

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())

    msg = str(ei.value)
    assert "Failed to read solution CSV" in msg
    assert "Validate solution.csv encoding and columns" in msg


def test_compute_utilization_raises_non_finite(monkeypatch):
    """
    @brief
    Raises DataError when utilization value is non-finite.

    @details
    Simulates NaN/inf result by patching math.isfinite to return False.
    Ensures DataError includes diagnostic message for input schedule.
    """
    import opmed.metrics.metrics as metric_mod

    # --- Arrange ---
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["2025-01-01T08:00:00Z"],
            "end_time": ["2025-01-01T10:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    df = _normalize_df(df)

    # Force math.isfinite to fail check
    monkeypatch.setattr(metric_mod.math, "isfinite", lambda x: False)

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        _ = metric_mod._compute_utilization(df, _fake_cfg())

    msg = str(ei.value)
    assert "Utilization computed as non-finite value" in msg
    assert "Inspect input schedule" in msg
