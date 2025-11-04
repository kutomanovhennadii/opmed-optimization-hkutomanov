from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from opmed.errors import DataError
from opmed.metrics.logger import (
    _atomic_write_text,
    _utc_now_hms,
    write_metrics,
    write_solver_log,
)

# --------------------------
# write_metrics
# --------------------------


def test_write_metrics_writes_json_and_overwrites(tmp_path):
    """
    @brief
    Verifies that write_metrics() creates and overwrites metrics.json correctly.

    @details
    The test writes two consecutive JSON files and ensures that
    the second call replaces the previous one without residual content.
    """
    # --- Arrange ---
    out_dir = tmp_path / "out"

    # --- Act ---
    p1 = write_metrics({"a": 1, "b": "x"}, out_dir)
    text1 = p1.read_text(encoding="utf-8")
    obj1 = json.loads(text1)

    # --- Assert ---
    assert p1.name == "metrics.json"
    assert obj1 == {"a": 1, "b": "x"}

    # --- Act (overwrite) ---
    p2 = write_metrics({"a": 2, "c": True}, out_dir)
    text2 = p2.read_text(encoding="utf-8")
    obj2 = json.loads(text2)

    # --- Assert ---
    assert p2 == p1
    assert obj2 == {"a": 2, "c": True}


def test_write_metrics_rejects_non_dict(tmp_path):
    """
    @brief
    Ensures that write_metrics() rejects non-dict inputs.

    @details
    Passing a list instead of a dictionary must raise DataError.
    """
    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        write_metrics(["not", "a", "dict"], tmp_path)
    assert "metrics must be a dict" in str(ei.value)


def test_write_metrics_non_serializable_raises(tmp_path):
    """
    @brief
    Ensures that non-serializable objects trigger DataError.

    @details
    Attempts to serialize an object without JSON representation should fail.
    """

    class Bad:
        pass

    with pytest.raises(DataError) as ei:
        write_metrics({"ok": 1, "bad": Bad()}, tmp_path)
    msg = str(ei.value)
    assert "metrics not JSON-serializable" in msg
    assert "metrics.write_metrics" in msg


# --------------------------
# _atomic_write_text
# --------------------------


def test_atomic_write_text_failure_raises_and_cleans_tmp(tmp_path, monkeypatch):
    """
    @brief
    Forces os.replace() to fail and verifies DataError and cleanup.

    @details
    Simulates a failure during atomic file replacement and checks
    that the temporary file is properly removed afterward.
    """
    target = tmp_path / "folder" / "file.txt"
    tmp_created = tmp_path / "folder" / "file.txt.tmp-for-test"

    # --- Arrange ---
    # Mock mkstemp to control temporary file name
    def fake_mkstemp(prefix, dir):
        os.makedirs(dir, exist_ok=True)
        f = open(tmp_created, "w", encoding="utf-8")
        f.close()
        fd = os.open(tmp_created, os.O_RDWR)
        return fd, str(tmp_created)

    monkeypatch.setattr("tempfile.mkstemp", fake_mkstemp)

    # Mock os.replace to raise an exception
    def boom_replace(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(os, "replace", boom_replace)

    # --- Act & Assert ---
    with pytest.raises(DataError) as ei:
        _atomic_write_text(target, "payload", encoding="utf-8")

    msg = str(ei.value)
    assert "atomic write failed" in msg
    assert "metrics._atomic_write_text" in msg

    # The temporary file must be removed after failure
    assert not tmp_created.exists()


# --------------------------
# write_solver_log
# --------------------------


def test_write_solver_log_full_info(tmp_path, monkeypatch):
    """
    @brief
    Full scenario: solver log includes parameters, version, and ResponseStats.

    @details
    Verifies that all major sections of the log (metadata, parameters,
    OR-Tools version, and solver statistics) are written correctly.
    """
    # --- Arrange ---
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-01-01 12:34:56")
    import opmed.metrics.logger as logger_mod

    monkeypatch.setattr(logger_mod.ortools, "__version__", "9.99.fake", raising=False)

    cfg = SimpleNamespace(
        solver=SimpleNamespace(
            num_workers=4,
            max_time_in_seconds=12.5,
            random_seed=777,
            search_branching="AUTOMATIC",
        )
    )

    class Solver:
        def ResponseStats(self):
            return "CpSolverStatus: OPTIMAL\nObjective: 42\nWall time: 0.12s"

    # --- Act ---
    path = write_solver_log(Solver(), cfg, tmp_path / "logs")
    text = path.read_text(encoding="utf-8")

    # --- Assert ---
    assert "[2025-01-01 12:34:56] INFO Starting CP-SAT solver" in text
    assert "Parameters: workers=4, time_limit=12.5s, seed=777, search_branching=AUTOMATIC" in text
    assert "OR-Tools version: 9.99.fake" in text
    assert "ResponseStats snippet: CpSolverStatus: OPTIMAL" in text
    assert "CpSolverStatus: OPTIMAL" in text
    assert "Objective: 42" in text
    assert "Wall time: 0.12s" in text
    assert text.endswith("\n")


def test_write_solver_log_no_responsestats(tmp_path, monkeypatch):
    """
    @brief
    Verifies log behavior when solver lacks ResponseStats() method.

    @details
    Ensures that the log still writes a completion message even when
    ResponseStats() is not implemented.
    """
    # --- Arrange ---
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-02-02 00:00:00")
    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=1))

    class Solver:
        pass

    # --- Act ---
    path = write_solver_log(Solver(), cfg, tmp_path / "logs2")
    text = path.read_text(encoding="utf-8")

    # --- Assert ---
    assert "Solver finished (no ResponseStats available)" in text


def test_write_solver_log_responsestats_raises(tmp_path, monkeypatch):
    """
    @brief
    Ensures robustness when ResponseStats() raises an exception.

    @details
    Even if the solver fails to return statistics, the log must include a warning.
    """
    # --- Arrange ---
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-03-03 03:03:03")
    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=2))

    class Solver:
        def ResponseStats(self):
            raise RuntimeError("boom")

    # --- Act ---
    path = write_solver_log(Solver(), cfg, tmp_path / "logs3")
    text = path.read_text(encoding="utf-8")

    # --- Assert ---
    assert "WARN Failed to read ResponseStats()" in text


def test_write_solver_log_params_block_robust(tmp_path, monkeypatch):
    """
    @brief
    Ensures that missing cfg.solver block does not break log creation.

    @details
    If accessing cfg.solver raises an exception, the log is still written successfully.
    """
    # --- Arrange ---
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-04-04 04:04:04")

    class BadCfg:
        @property
        def solver(self):
            raise RuntimeError("no cfg.solver")

    class Solver:
        def ResponseStats(self):
            return "CpSolverStatus: FEASIBLE\nObjective: 1"

    # --- Act ---
    path = write_solver_log(Solver(), BadCfg(), tmp_path / "logs4")
    text = path.read_text(encoding="utf-8")

    # --- Assert ---
    assert "Starting CP-SAT solver" in text
    assert "Parameters:" not in text
    assert "CpSolverStatus: FEASIBLE" in text


def test_write_solver_log_version_block_robust(tmp_path, monkeypatch):
    """
    @brief
    Ensures that missing ortools.__version__ does not block log writing.

    @details
    When accessing ortools version fails, the log omits the version block but completes normally.
    """
    # --- Arrange ---
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-05-05 05:05:05")
    import opmed.metrics.logger as logger_mod

    class BadOrtools:
        def __getattr__(self, name):
            raise RuntimeError("no version")

    monkeypatch.setattr(logger_mod, "ortools", BadOrtools())
    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=1))

    class Solver:
        pass

    # --- Act ---
    path = write_solver_log(Solver(), cfg, tmp_path / "logs5")
    text = path.read_text(encoding="utf-8")

    # --- Assert ---
    assert "OR-Tools version:" not in text
    assert "Starting CP-SAT solver" in text


def test_utc_now_hms_format():
    """
    @brief
    Validates the timestamp format returned by _utc_now_hms().

    @details
    Ensures the function returns a string in format YYYY-MM-DD HH:MM:SS (19 chars).
    """
    # --- Act ---
    s = _utc_now_hms()

    # --- Assert ---
    assert isinstance(s, str)
    assert len(s) == 19
    assert s[4] == "-" and s[7] == "-" and s[10] == " " and s[13] == ":" and s[16] == ":"
