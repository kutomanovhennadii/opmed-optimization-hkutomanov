import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from opmed.errors import DataError, ValidationError

# ВАЖНО: импортируем правильный модуль (metrics.py)
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
# Вспомогательные утилиты
# -------------------------


def _fake_cfg(
    shift_min=5.0,
    shift_overtime=9.0,
    overtime_multiplier=1.5,
    solver_num_workers=2,
    solver_seed=123,
):
    return SimpleNamespace(
        shift_min=shift_min,
        shift_overtime=shift_overtime,
        overtime_multiplier=overtime_multiplier,
        solver=SimpleNamespace(num_workers=solver_num_workers, random_seed=solver_seed),
    )


def _df_sample(utc_start: datetime) -> pd.DataFrame:
    # Два кейса, один анестезиолог, две комнаты — по часу каждый
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
    # Минимально валидный SolveResult
    return {
        "status": "FEASIBLE",
        "objective": 123.0,
        "runtime": 0.42,
        "assignment": {"x": [], "y": []},
    }


# -------------------------
# Тесты _normalize_df
# -------------------------


def test_normalize_df_ok_converts_to_utc_and_types():
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)
    out = _normalize_df(df)
    # Проверка колонок
    assert set(["surgery_id", "start_time", "end_time", "anesthetist_id", "room_id"]).issubset(
        set(out.columns)
    )
    # Времена — timezone-aware UTC
    assert str(out["start_time"].dtype) == "datetime64[ns, UTC]"
    assert str(out["end_time"].dtype) == "datetime64[ns, UTC]"
    # Типы ID — строки (object)
    assert out["surgery_id"].dtype == "object"
    assert out["anesthetist_id"].dtype == "object"
    assert out["room_id"].dtype == "object"


def test_normalize_df_missing_columns_raises_data_error():
    df = pd.DataFrame({"surgery_id": ["s1"], "start_time": ["2025-01-01T08:00:00Z"]})
    with pytest.raises(DataError) as ei:
        _normalize_df(df)
    assert "Schedule is missing columns" in str(ei.value)


def test_normalize_df_bad_datetime_raises_data_error():
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["NOT_A_TIME"],
            "end_time": ["2025-01-01T09:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    with pytest.raises(DataError) as ei:
        _normalize_df(df)
    assert "Datetime parse failed" in str(ei.value)


def test_normalize_df_non_positive_duration_raises_validation_error():
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["2025-01-01T08:00:00Z"],
            "end_time": ["2025-01-01T08:00:00Z"],
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    with pytest.raises(ValidationError) as ei:
        _normalize_df(df)
    assert "Non-positive durations" in str(ei.value)


# -------------------------
# Тесты _compute_counts
# -------------------------


def test_compute_counts_counts_unique_ids():
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _normalize_df(_df_sample(start))
    n_s, n_a, n_r = _compute_counts(_result_base(), df)
    assert n_s == 2
    assert n_a == 1
    assert n_r == 2


# -------------------------
# Тесты _compute_utilization
# -------------------------


def test_compute_utilization_basic_formula():
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _normalize_df(_df_sample(start))
    # total_surgery_hours = 2
    # span = 2.5h; base = max(5, 2.5)=5; overtime=0; total_cost=5 => util=0.4
    cfg = _fake_cfg(shift_min=5.0, shift_overtime=9.0, overtime_multiplier=1.5)
    util = _compute_utilization(df, cfg)
    assert abs(util - 0.4) < 1e-9


def test_compute_utilization_with_overtime_multiplier():
    df = pd.DataFrame(
        {
            "surgery_id": ["s1"],
            "start_time": ["2025-01-01T08:00:00Z"],
            "end_time": ["2025-01-01T20:00:00Z"],  # 12h
            "anesthetist_id": ["a1"],
            "room_id": ["r1"],
        }
    )
    df = _normalize_df(df)
    # total_surgery_hours = 12; span=12; base=12; overtime=3; m=1.5 => cost=13.5 => util=12/13.5
    cfg = _fake_cfg(shift_min=5.0, shift_overtime=9.0, overtime_multiplier=1.5)
    util = _compute_utilization(df, cfg)
    assert abs(util - (12.0 / 13.5)) < 1e-9


def test_compute_utilization_empty_df_returns_zero():
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
    assert _compute_utilization(df, cfg) == 0.0


# -------------------------
# Тесты _assert_no_nans
# -------------------------


def test_assert_no_nans_passes_on_clean_structures():
    _assert_no_nans({"a": 1.0, "b": [2.0, 3.0], "c": {"d": 4.0}})


def test_assert_no_nans_raises_on_nan():
    with pytest.raises(DataError):
        _assert_no_nans(float("nan"))


def test_assert_no_nans_raises_on_inf():
    with pytest.raises(DataError):
        _assert_no_nans(float("inf"))


def test_assert_no_nans_raises_on_none():
    with pytest.raises(DataError):
        _assert_no_nans(None)


# -------------------------
# Тесты _utc_now_iso и _f
# -------------------------


def test_utc_now_iso_format():
    s = _utc_now_iso()
    assert s.endswith("Z")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    assert dt.microsecond == 0


def test_f_small_number_zeroing_and_passthrough():
    assert _f(1e-16) == 0.0
    assert _f(-1e-16) == 0.0
    assert _f(1e-12) == 1e-12
    assert _f(-1e-12) == -1e-12


# -------------------------
# Тесты collect_metrics (публичный API)
# -------------------------


def test_collect_metrics_from_dataframe(monkeypatch):
    import opmed.metrics.metrics as metric_mod

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)
    # фиксируем timestamp для стабильности снапшотов
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    cfg = _fake_cfg()

    out = collect_metrics(base, cfg)
    assert out["timestamp"] == "2025-01-01T00:00:00Z"
    assert out["solver_status"] == "FEASIBLE"
    assert isinstance(out["total_cost"], float)
    assert isinstance(out["runtime_sec"], float)
    assert out["num_surgeries"] == 2
    assert out["num_anesthetists"] == 1
    assert out["num_rooms_used"] == 2
    s = out["solver"]
    assert s["engine"] == "CP-SAT"
    assert s["num_workers"] == 2
    assert s["seed"] == 123
    json.dumps(out, ensure_ascii=False)  # сериализуемость


def test_collect_metrics_from_rows_list(monkeypatch):
    import opmed.metrics.metrics as metric_mod

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)
    base["solution_rows"] = df.to_dict(orient="records")
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-02-02T00:00:00Z")
    cfg = _fake_cfg(solver_num_workers=8, solver_seed=77)

    out = collect_metrics(base, cfg)
    assert out["timestamp"] == "2025-02-02T00:00:00Z"
    assert out["num_surgeries"] == 2
    assert out["solver"]["num_workers"] == 8
    assert out["solver"]["seed"] == 77


def test_collect_metrics_from_csv(tmp_path, monkeypatch):
    import opmed.metrics.metrics as metric_mod

    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df = _df_sample(start)
    p = tmp_path / "solution.csv"
    df.to_csv(p, index=False, encoding="utf-8")

    base = _result_base()
    base["solution_path"] = str(p)

    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-03-03T00:00:00Z")
    cfg = _fake_cfg()

    out = collect_metrics(base, cfg)
    assert out["timestamp"] == "2025-03-03T00:00:00Z"
    assert out["num_surgeries"] == 2


def test_collect_metrics_prefers_csv_when_present(tmp_path, monkeypatch):
    import opmed.metrics.metrics as metric_mod

    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    df_df = _df_sample(start)

    # CSV с иным содержимым (1 операция)
    df_csv = df_df.iloc[:1].copy()
    p = tmp_path / "solution.csv"
    df_csv.to_csv(p, index=False, encoding="utf-8")

    base = _result_base()
    base["solution_path"] = str(p)
    base["assignments_df"] = df_df  # должен быть проигнорирован

    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-04-04T00:00:00Z")
    cfg = _fake_cfg()

    out = collect_metrics(base, cfg)
    assert out["num_surgeries"] == 1  # использован CSV


def test_collect_metrics_missing_required_keys_raises():
    bad = {"status": "FEASIBLE", "runtime": 0.1, "assignment": {"x": [], "y": []}}
    with pytest.raises(DataError) as ei:
        collect_metrics(bad, _fake_cfg())
    assert "Missing SolveResult keys" in str(ei.value)


def test_collect_metrics_assignment_must_be_dict():
    bad = _result_base()
    bad["assignment"] = ["not", "a", "dict"]
    with pytest.raises(DataError) as ei:
        collect_metrics(bad, _fake_cfg())
    assert "result['assignment'] must be a dict" in str(ei.value)


def test_collect_metrics_csv_with_bad_datetime_raises_data_error(tmp_path):
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

    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())
    assert "Datetime parse failed" in str(ei.value)


def test_collect_metrics_when_no_schedule_sources_raises_data_error():
    base = _result_base()
    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())
    assert "Schedule with timestamps not found" in str(ei.value)


def test_collect_metrics_handles_empty_schedule_utilization_zero(monkeypatch):
    import opmed.metrics.metrics as metric_mod

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

    out = collect_metrics(base, cfg)
    assert out["utilization"] == 0.0
    assert out["num_surgeries"] == 0
    assert out["num_anesthetists"] == 0
    assert out["num_rooms_used"] == 0


def test_collect_metrics_solver_version_present(monkeypatch):
    import opmed.metrics.metrics as metric_mod

    # фиксируем время
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-06-06T00:00:00Z")
    # подставим версию ortools
    monkeypatch.setattr(metric_mod.ortools, "__version__", "9.99.fake", raising=False)

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)

    out = collect_metrics(base, _fake_cfg())
    assert out["solver"]["version"] == "9.99.fake"


def test_collect_metrics_solver_version_raises_exception(monkeypatch):
    """
    Ветка 45-46: проверка обработки исключения при получении версии ortools.
    """
    import opmed.metrics.metrics as metric_mod

    # Подменим ortools на объект с __getattr__ выбрасывающим исключение
    class BadOrtools:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    monkeypatch.setattr(metric_mod, "ortools", BadOrtools())
    monkeypatch.setattr(metric_mod, "_utc_now_iso", lambda: "2025-07-07T00:00:00Z")

    base = _result_base()
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    base["assignments_df"] = _df_sample(start)

    # Не должно выбросить
    out = collect_metrics(base, _fake_cfg())
    assert out["solver"]["engine"] == "CP-SAT"
    assert "version" not in out["solver"]


def test_load_schedule_dataframe_raises_dataerror_on_bad_csv(tmp_path, monkeypatch):
    """
    Проверяет, что при ошибке чтения CSV в _load_schedule_dataframe
    выбрасывается DataError (ветка except Exception: ...).
    """
    import opmed.metrics.metrics as metric_mod

    # Создаем файл, который существует, но вызывает ошибку при чтении
    bad_csv = tmp_path / "bad_solution.csv"
    bad_csv.write_text("corrupted,data\n1,2\n", encoding="utf-8")

    # Переопределяем pd.read_csv, чтобы он гарантированно выбросил исключение
    def broken_read_csv(path):
        raise ValueError("Simulated CSV read failure")

    monkeypatch.setattr(metric_mod.pd, "read_csv", broken_read_csv)

    base = _result_base()
    base["solution_path"] = str(bad_csv)

    # Проверяем, что collect_metrics ловит ValueError и выбрасывает DataError
    with pytest.raises(DataError) as ei:
        collect_metrics(base, _fake_cfg())

    msg = str(ei.value)
    assert "Failed to read solution CSV" in msg
    assert "Validate solution.csv encoding and columns" in msg


def test_compute_utilization_raises_non_finite(monkeypatch):
    """
    Проверка ветки выброса DataError, когда utilization не конечен.
    """
    import opmed.metrics.metrics as metric_mod

    # Подготовим корректный df, чтобы пройти всю математику до конца
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

    # Патчим math.isfinite, чтобы вернуть False — имитация NaN/inf
    monkeypatch.setattr(metric_mod.math, "isfinite", lambda x: False)

    with pytest.raises(DataError) as ei:
        _ = metric_mod._compute_utilization(df, _fake_cfg())

    msg = str(ei.value)
    assert "Utilization computed as non-finite value" in msg
    assert "Inspect input schedule" in msg
