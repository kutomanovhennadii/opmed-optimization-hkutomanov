import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.run import _rename_anesthetists, run_pipeline


@pytest.mark.skip(reason="Heavy integration test — use only for manual inspection.")
@pytest.mark.live
def test_run_pipeline_live_creates_real_artifacts():
    """
    @brief
    Full live integration test that executes the real optimization pipeline.

    @details
    Runs the complete pipeline using actual configuration and input data,
    generating real artifacts in data/output/ for manual visual inspection.
    Ensures that every expected artifact is produced and valid.
    """

    cfg_path = Path("config/config.yaml")
    input_path = Path("data/input/synthetic_2d_2r.csv")
    output_dir = Path("data/output")

    # --- Arrange ---
    # Verify input assets exist before launching the pipeline
    assert cfg_path.exists(), f"Config file not found: {cfg_path}"
    assert input_path.exists(), f"Input CSV not found: {input_path}"

    # --- Act ---
    # Execute the full optimization pipeline with given configuration
    result = run_pipeline(cfg_path, input_path, output_dir)
    arts = result["artifacts"]

    print("\n[Artifacts created]")
    for name, path in arts.items():
        if path:
            print(f"{name:>20}: {Path(path).resolve()}")

    # --- Assert ---
    # Basic artifact existence checks
    val_report = arts["validation_report"]
    metrics = arts["metrics"]
    solution = arts["solution_csv"]

    assert val_report and Path(val_report).exists()
    assert metrics and Path(metrics).exists()
    assert solution and Path(solution).exists()

    # Load validation and metrics reports to confirm correctness
    with open(val_report, encoding="utf-8") as f:
        report = json.load(f)
    print(f"\nValidation valid={report['valid']}")

    with open(metrics, encoding="utf-8") as f:
        summary = json.load(f)
    print(f"Utilization={summary.get('utilization')} total_cost={summary.get('total_cost')}")

    # Conditionally verify plot generation only for valid schedules
    if report["valid"]:
        plot = arts.get("solution_plot")
        assert plot and Path(plot).exists()
        print(f"Plot: {plot}")
    else:
        print("Plot skipped (invalid schedule)")

    print("\n[Pipeline completed successfully]")


# ----------------------------------------------------------------------------------
# Lightweight pipeline smoke-test (default)
# ----------------------------------------------------------------------------------
class _FakeOptimizer:
    def __init__(self, cfg):
        """Minimal stub optimizer for pipeline smoke testing."""
        ...

    def solve(self, bundle):
        """
        @brief
        Returns a dummy SolveResult structure.

        @details
        Simulates solver interface by returning a minimal result dictionary
        without performing any optimization.
        """
        return {
            "status": "DUMMY",
            "objective": 0.0,
            "runtime": 0.01,
            "assignments": [],
            "solver": None,
        }


def test_run_pipeline_stub(monkeypatch, tmp_path):
    """
    @brief
    Lightweight smoke test for pipeline execution.

    @details
    Verifies that the pipeline structure, configuration loading,
    and artifact collection complete without invoking CP-SAT or raising errors.
    """

    from scripts import run

    # --- Arrange ---
    # Replace the real optimizer with the stub implementation
    monkeypatch.setattr(run, "Optimizer", _FakeOptimizer)

    cfg_path = Path("config/config.yaml")
    input_path = Path("data/input/synthetic_2d_2r.csv")
    output_dir = tmp_path / "out"

    # --- Act ---
    result = run_pipeline(cfg_path, input_path, output_dir)

    # --- Assert ---
    assert isinstance(result, dict)
    assert "artifacts" in result
    assert "valid" in result
    assert result["status"] == "DUMMY"
    print("Pipeline stub test passed — no solver invoked.")


def _dt(h, m=0):
    """
    @brief
    Helper utility to quickly create UTC datetime values.

    @details
    Simplifies time definition in tests for consistent timezone handling.
    """
    return datetime(2025, 1, 1, h, m, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------------
# Tests for anesthetist renaming logic
# ----------------------------------------------------------------------------------
def test_rename_anesthetists_basic_ordering_on_models():
    """
    @brief
    Tests that anesthetist IDs are reassigned according to chronological order.

    @details
    Ensures that surgeries are sorted by start time and
    that sequential anesthetist IDs (A001, A002, ...) are generated consistently.
    """

    # --- Arrange ---
    rows = [
        {
            "surgery_id": "s2",
            "start_time": _dt(10),
            "end_time": _dt(11),
            "anesthetist_id": "B",
            "room_id": "R2",
        },
        {
            "surgery_id": "s1",
            "start_time": _dt(8),
            "end_time": _dt(9),
            "anesthetist_id": "A",
            "room_id": "R1",
        },
        {
            "surgery_id": "s3",
            "start_time": _dt(12),
            "end_time": _dt(13),
            "anesthetist_id": "C",
            "room_id": "R3",
        },
    ]

    # --- Act ---
    out = _rename_anesthetists(rows)

    # --- Assert ---
    # Verify chronological ordering and correct ID reassignment
    assert [r["surgery_id"] for r in out] == ["s1", "s2", "s3"]
    assert [r["anesthetist_id"] for r in out] == ["A001", "A002", "A003"]


def test_rename_anesthetists_repeated_ids_on_models():
    """
    @brief
    Tests consistent handling of repeated anesthetist IDs.

    @details
    Ensures that identical input IDs receive the same new label
    and that numbering remains stable across multiple repetitions.
    """

    # --- Arrange ---
    rows = [
        {
            "surgery_id": "s1",
            "start_time": _dt(9),
            "end_time": _dt(10),
            "anesthetist_id": "X",
            "room_id": "R1",
        },
        {
            "surgery_id": "s2",
            "start_time": _dt(11),
            "end_time": _dt(12),
            "anesthetist_id": "X",
            "room_id": "R2",
        },
        {
            "surgery_id": "s3",
            "start_time": _dt(13),
            "end_time": _dt(14),
            "anesthetist_id": "Y",
            "room_id": "R3",
        },
    ]

    # --- Act ---
    out = _rename_anesthetists(rows)

    # --- Assert ---
    ids = [r["anesthetist_id"] for r in out]
    assert ids.count("A001") == 2
    assert "A002" in ids
    assert set(ids) <= {"A001", "A002"}


def test_rename_anesthetists_empty_list_on_models():
    """
    @brief
    Tests graceful handling of empty input list.

    @details
    Ensures that no exceptions are raised and the result remains empty.
    """
    assert _rename_anesthetists([]) == []
