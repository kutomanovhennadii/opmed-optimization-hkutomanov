from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer


def _mini_config() -> Config:
    """
    @brief
    Creates a lightweight solver configuration for fast, deterministic test runs.

    @details
    This helper function initializes a minimal `Config` object
    with small search space and low runtime limit.
    It is primarily used in integration tests to ensure
    reproducible solver behavior under controlled conditions.

    Specific adjustments:
      - `rooms_max = 2` to reduce model complexity.
      - `num_workers = 1` to avoid nondeterminism from parallel search.
      - `max_time_in_seconds = 3` for fast termination.
      - `search_branching = "AUTOMATIC"` for simplicity.
      - `random_seed = 42` for reproducibility.

    @returns
        Config : a fully initialized, minimal configuration for testing.
    """
    cfg = Config()
    cfg.rooms_max = 2
    cfg.solver.num_workers = 1
    cfg.solver.max_time_in_seconds = 3
    cfg.solver.search_branching = "AUTOMATIC"
    cfg.solver.random_seed = 42
    return cfg


def _mini_surgeries() -> list[Surgery]:
    """
    @brief
    Generates a small set of fixed-time surgeries for solver smoke tests.

    @details
    Provides three simple, non-overlapping surgeries occurring
    within the same day.
    These surgeries are minimal but sufficient to trigger all
    solver constraints and output generation (metrics and logs).

    @returns
        list[Surgery] : three Surgery objects with fixed UTC timestamps.
    """
    return [
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:10:00Z",
            end_time="2025-01-01T10:00:00Z",
        ),
        Surgery(
            surgery_id="s3",
            start_time="2025-01-01T10:30:00Z",
            end_time="2025-01-01T11:15:00Z",
        ),
    ]


def test_optimizer_writes_metrics_and_log(tmp_path, monkeypatch) -> None:
    """
    @brief
    Integration test ensuring that `Optimizer.solve()` produces
    persistent artifacts: `metrics.json` and `solver.log`.

    @details
    The test validates end-to-end behavior of the optimizer:
      1. Runs a short optimization inside an isolated temporary directory.
      2. Confirms that both `metrics.json` and `solver.log` are created.
      3. Verifies that the JSON file is valid and contains core fields:
         `"status"`, `"objective"`, `"runtime"`, and `"ortools_version"`.
      4. Checks that the log file includes both the OR-Tools version and seed.
      5. Ensures that the final solver result is FEASIBLE or OPTIMAL.

    @params
        tmp_path : pytest-provided temporary directory for test isolation.
        monkeypatch : fixture used to change the working directory safely.

    @returns
        None. The test asserts successful artifact generation and basic validity.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _mini_config()
    surgeries = _mini_surgeries()

    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle = builder.build()
    assert isinstance(bundle["model"], cp_model.CpModel)

    opt = Optimizer(cfg)

    # --- Act ---
    res = opt.solve(bundle)

    # --- Assert ---
    out_dir = Path("data") / "output"
    metrics_path = out_dir / "metrics.json"
    log_path = out_dir / "solver.log"

    # Files must exist
    assert metrics_path.exists(), "metrics.json not found"
    assert log_path.exists(), "solver.log not found"

    # Validate JSON contents
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version"):
        assert key in payload, f"metrics.json missing '{key}'"

    # Log file must contain key header lines
    log_text = log_path.read_text(encoding="utf-8")
    assert "ortools_version:" in log_text
    assert "random_seed:" in log_text

    # Ensure solver produced a feasible or optimal result
    assert res["status"] in ("FEASIBLE", "OPTIMAL")


def _dummy_solver() -> cp_model.CpSolver:
    """
    @brief
    Creates a minimal dummy instance of `cp_model.CpSolver` for unit testing.

    @details
    The dummy solver is configured for near-instant execution and reproducibility.
    It uses a single worker and a 0.1-second timeout, making it ideal
    for testing logging and configuration behavior without performing
    actual heavy optimization.

    Configuration:
      - `num_search_workers = 1` — deterministic single-threaded mode.
      - `max_time_in_seconds = 0.1` — ensures test finishes quickly.

    @returns
        cp_model.CpSolver : a lightweight, test-friendly solver.
    """
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 0.1
    return solver


def _fake_cfg(
    metrics: dict[str, Any] | None = None,
    experiment: dict[str, Any] | None = None,
    output_dir: str = "data/output",
    solver_overrides: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """
    @brief
    Constructs a mock configuration object compatible with `Optimizer`
    for isolated testing of logging and metrics output.

    @details
    This helper simulates the minimal structure expected by the optimizer,
    avoiding the need to instantiate a full `Config` schema.
    It behaves like a simplified configuration container with nested namespaces:
      - `.solver` — holds solver-related attributes such as workers, limits, and seeds.
      - `.metrics` — optional dict controlling whether logs/metrics are saved.
      - `.experiment` — optional dict with metadata fields (`name`, `tags`, `description`).
      - `.output_dir` — path to store solver artifacts.

    This approach allows unit tests to easily vary combinations of flags
    and verify conditional file writing without dependency on global settings.

    @params
        metrics : dict[str, Any] | None
            Optional flags controlling saving behavior (e.g., `{"save_solver_log": False}`).
        experiment : dict[str, Any] | None
            Metadata for experiment info included in logs.
        output_dir : str
            Target directory for artifacts (default `"data/output"`).
        solver_overrides : dict[str, Any] | None
            Optional overrides for default solver parameters.

    @returns
        SimpleNamespace : A lightweight, self-contained configuration stub
        suitable for direct use in `Optimizer(cfg)` during testing.
    """
    # (1) Define default solver parameters for reproducibility
    solver_defaults: dict[str, Any] = {
        "num_workers": 1,
        "max_time_in_seconds": 3,
        "random_seed": 42,
        "search_branching": "AUTOMATIC",
    }

    # (2) Allow test cases to override selected solver fields
    if solver_overrides:
        solver_defaults.update(solver_overrides)

    # (3) Wrap solver parameters in a namespace for attribute access
    solver_ns = SimpleNamespace(**solver_defaults)

    # (4) Build and return a complete configuration namespace
    return SimpleNamespace(
        solver=solver_ns,
        metrics=metrics,
        experiment=experiment,
        output_dir=output_dir,
    )


def test_write_solver_log_skips_when_disabled(tmp_path, monkeypatch) -> None:
    """
    @brief
    Ensures `_write_solver_log()` correctly skips file creation when
    `cfg.metrics.save_solver_log=False` is provided as a dictionary.

    @details
    This test verifies conditional behavior of log writing:
      - A temporary directory is used as the working directory.
      - The configuration explicitly disables log saving via a dict flag.
      - The method should **not** create `data/output/solver.log`.

    It confirms that the conditional guard inside `_write_solver_log()`
    respects configuration flags and avoids unnecessary file I/O.

    @params
        tmp_path : pytest-provided temporary directory for isolation.
        monkeypatch : fixture for temporarily changing working directory.

    @returns
        None. The test asserts that no solver log file is written.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(metrics={"save_solver_log": False})
    opt = Optimizer(cfg)
    solver = _dummy_solver()

    # --- Act ---
    opt._write_solver_log(solver, status="FEASIBLE", objective=1.0, runtime=0.01)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert not log_path.exists(), "solver.log should not be created when disabled"


def test_write_solver_log_with_experiment_dict(tmp_path, monkeypatch) -> None:
    """
    @brief
    Validates that `_write_solver_log()` writes a complete, correctly
    formatted log when `cfg.experiment` is a dictionary containing metadata.

    @details
    The test covers:
      - File creation in an isolated temporary working directory.
      - Proper inclusion of experiment fields: name, tags, and description.
      - Correct formatting of solver result fields such as `objective`
        and `runtime_sec`.

    This ensures that dictionary-based configuration of experiments is
    serialized properly and included in the log output.

    @params
        tmp_path : pytest fixture providing a temporary working directory.
        monkeypatch : fixture for switching the current working directory.

    @returns
        None. The test asserts presence and correctness of the written log file.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    experiment = {
        "name": "baseline",
        "tags": ["smoke", "unit"],
        "description": "determinism coverage test",
    }
    cfg = _fake_cfg(metrics={"save_solver_log": True}, experiment=experiment)
    opt = Optimizer(cfg)
    solver = _dummy_solver()

    # --- Act ---
    opt._write_solver_log(solver, status="OPTIMAL", objective=123.0, runtime=0.01)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert log_path.exists(), "solver.log should be created"

    text = log_path.read_text(encoding="utf-8")
    assert "experiment.name: baseline" in text
    assert "experiment.tags:" in text
    assert "experiment.description:" in text
    assert "objective: 123.0" in text
    assert "runtime_sec:" in text


def test_write_solver_log_with_experiment_object(tmp_path, monkeypatch) -> None:
    """
    @brief
    Validates `_write_solver_log()` behavior when `cfg.experiment` is provided
    as an **object (SimpleNamespace)** rather than a dictionary.

    @details
    This test covers the alternative branch of implementation:
      - `exp is not None` and not a dict → attributes accessed via `getattr`.
      - Ensures experiment fields (`name`, `tags`, `description`) appear in the output.
      - Confirms the log file is created under the default `"data/output"` directory.

    The test uses a lightweight solver and relies on the default behavior:
    when `metrics=None`, saving solver logs defaults to `True`.

    @params
        tmp_path : pytest-provided temporary directory used as isolated environment.
        monkeypatch : fixture to redirect working directory for safe I/O.

    @returns
        None. Asserts the solver log exists and contains experiment object data.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)

    exp_obj = SimpleNamespace(
        name="baseline_obj",
        tags=["obj", "coverage"],
        description="experiment as object",
    )
    cfg = _fake_cfg(metrics=None, experiment=exp_obj)
    opt = Optimizer(cfg)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 0.01

    # --- Act ---
    opt._write_solver_log(solver, status="FEASIBLE", objective=7.0, runtime=0.002)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert log_path.exists(), "solver.log should be created for object experiment"

    text = log_path.read_text(encoding="utf-8")
    assert "experiment.name: baseline_obj" in text
    assert "experiment.tags:" in text
    assert "experiment.description: experiment as object" in text
    assert "objective: 7.0" in text


def test_write_metrics_skips_when_object_flag_false(tmp_path, monkeypatch) -> None:
    """
    @brief
    Ensures `_write_metrics()` respects the `save_metrics=False` flag
    when `cfg.metrics` is an **object**, not a dictionary.

    @details
    This test executes the alternate branch of `_write_metrics()` that handles
    object-style metric configurations. When `metrics` is an instance with
    `save_metrics=False`, the method must **not** create any output files.

    It verifies that:
      - The default path `data/output/metrics.json` remains absent.
      - No unintended directories or artifacts are created.

    @params
        tmp_path : pytest temporary directory for isolated I/O.
        monkeypatch : fixture used to change the working directory.

    @returns
        None. Asserts that no metrics file is produced.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    metrics_obj = SimpleNamespace(save_metrics=False)
    cfg = _fake_cfg(metrics=metrics_obj)

    opt = Optimizer(cfg)
    result = {"status": "FEASIBLE", "objective": 1.0, "runtime": 0.01}

    # --- Act ---
    opt._write_metrics(result)

    # --- Assert ---
    metrics_path = Path("data") / "output" / "metrics.json"
    assert (
        not metrics_path.exists()
    ), "metrics.json must not be written when save_metrics=False (object)"


def test_write_metrics_writes_when_object_flag_true(tmp_path, monkeypatch) -> None:
    """
    @brief
    Ensures that `_write_metrics()` correctly writes a JSON file when
    `cfg.metrics` is an **object** (not a dict) with `save_metrics=True`.

    @details
    This test validates the branch of the implementation where metrics
    configuration is provided as an object (e.g., SimpleNamespace), not a dictionary.
    When `save_metrics=True`, the method should produce a valid JSON file
    containing both solver metrics and embedded experiment metadata.

    The test verifies:
      - File creation under `data/output/metrics.json`.
      - Presence of all expected top-level fields.
      - Proper serialization of an experiment object with `name` and `description`.

    @params
        tmp_path : pytest fixture providing isolated working directory.
        monkeypatch : fixture to switch the current directory to tmp_path.

    @returns
        None. Asserts file creation and content correctness.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    metrics_obj = SimpleNamespace(save_metrics=True)
    exp_obj = SimpleNamespace(
        name="baseline_obj",
        tags=["obj", "coverage"],
        description="metrics as object-flag test",
    )
    cfg = _fake_cfg(metrics=metrics_obj, experiment=exp_obj)
    opt = Optimizer(cfg)
    result = {"status": "OPTIMAL", "objective": 7.0, "runtime": 0.02}

    # --- Act ---
    opt._write_metrics(result)

    # --- Assert ---
    metrics_path = Path("data") / "output" / "metrics.json"
    assert metrics_path.exists(), "metrics.json should be written with object save_metrics=True"

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version", "search_branching"):
        assert key in payload, f"metrics.json missing '{key}'"

    assert "experiment" in payload
    assert payload["experiment"]["name"] == "baseline_obj"
    assert payload["experiment"]["description"] == "metrics as object-flag test"


def test_write_metrics_skips_when_dict_flag_false(tmp_path, monkeypatch) -> None:
    """
    @brief
    Verifies that `_write_metrics()` skips writing the metrics file when
    `cfg.metrics` is a dictionary with `"save_metrics": False`.

    @details
    Covers the branch where the configuration is explicitly provided as a dict
    and disables metrics output. The function must exit early and not create
    any JSON files, ensuring conditional logic behaves correctly.

    @params
        tmp_path : pytest-provided temporary directory for isolation.
        monkeypatch : fixture used to change the working directory.

    @returns
        None. Asserts absence of the metrics file.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_metrics": False},
        experiment={"name": "ignored"},
    )
    opt = Optimizer(cfg)
    result = {"status": "FEASIBLE", "objective": 1.0, "runtime": 0.01}

    # --- Act ---
    opt._write_metrics(result)

    # --- Assert ---
    metrics_path = Path("data") / "output" / "metrics.json"
    assert (
        not metrics_path.exists()
    ), "metrics.json must not be written when save_metrics=False (dict)"


def test_write_metrics_writes_when_dict_flag_true_with_experiment_dict(
    tmp_path, monkeypatch
) -> None:
    """
    @brief
    Ensures that `_write_metrics()` writes a valid `metrics.json` file
    when `cfg.metrics` is a **dict** with `"save_metrics": True`, and
    `cfg.experiment` is also provided as a dictionary.

    @details
    The test validates correct serialization of both metrics and experiment data:
      - Metrics file is created in the expected directory.
      - Mandatory keys (`status`, `objective`, `runtime`, etc.) are present.
      - Experiment section is embedded correctly with dict-style metadata.

    @params
        tmp_path : pytest fixture providing temporary isolated directory.
        monkeypatch : fixture for adjusting working directory context.

    @returns
        None. The test asserts file existence and correctness of serialized JSON.
    """

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_metrics": True},
        experiment={
            "name": "baseline",
            "tags": ["ci", "coverage"],
            "description": "experiment as dict",
        },
    )
    opt = Optimizer(cfg)
    result = {"status": "OPTIMAL", "objective": 7.0, "runtime": 0.02}

    # --- Act ---
    opt._write_metrics(result)

    # --- Assert ---
    metrics_path = Path("data") / "output" / "metrics.json"
    assert metrics_path.exists(), "metrics.json should be written when save_metrics=True (dict)"

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version", "search_branching"):
        assert key in payload, f"metrics.json missing '{key}'"

    assert "experiment" in payload
    assert payload["experiment"]["name"] == "baseline"
    assert payload["experiment"]["description"] == "experiment as dict"
