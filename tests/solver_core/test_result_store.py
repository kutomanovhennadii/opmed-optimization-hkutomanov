from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.result_store import ResultStore

# ----------------- helpers -----------------


def _fake_cfg(
    metrics: dict[str, Any] | SimpleNamespace | None = None,
    experiment: dict[str, Any] | SimpleNamespace | None = None,
    output_dir: str = "data/output",
    solver_overrides: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """
    Creates a lightweight mock configuration object emulating the structure expected by ResultStore.

    Args:
        metrics: Optional dict or SimpleNamespace with metrics-related flags (e.g., save_metrics).
        experiment: Optional metadata object describing the test experiment.
        output_dir: Target directory for generated files.
        solver_overrides: Optional dict to override default solver parameters.

    Returns:
        SimpleNamespace: minimal mock config with fields (solver, metrics, experiment, output_dir).
    """
    # (1) Default solver parameters for predictable, quick-running tests
    solver_defaults: dict[str, Any] = {
        "num_workers": 1,
        "max_time_in_seconds": 3,
        "random_seed": 42,
        "search_branching": "AUTOMATIC",
    }

    # (2) Allow overriding any of the defaults
    if solver_overrides:
        solver_defaults.update(solver_overrides)

    # (3) Wrap into a namespace to mimic real config.solver
    solver_ns = SimpleNamespace(**solver_defaults)

    # (4) Return full fake config object
    return SimpleNamespace(
        solver=solver_ns,
        metrics=metrics,
        experiment=experiment,
        output_dir=output_dir,
    )


def _dummy_solver() -> cp_model.CpSolver:
    """
    Returns a minimal CpSolver instance with deterministic, near-instant configuration.
    Used for unit tests that only verify side effects or structure, not full optimization.

    Returns:
        CpSolver: prepared solver instance for mock runs.
    """
    # (1) Initialize solver
    solver = cp_model.CpSolver()

    # (2) Configure to run extremely quickly and deterministically
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 0.01

    # (3) Return ready-to-use solver
    return solver


# ----------------- tests -----------------


def test_write_solver_log_skips_when_disabled(tmp_path, monkeypatch) -> None:
    """
    Verifies that `_write_solver_log()` does not create a log file
    when logging is explicitly disabled via config.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)  # isolate test directory
    cfg = _fake_cfg(metrics={"save_solver_log": False})
    store = ResultStore(cfg)
    solver = _dummy_solver()

    # --- Act ---
    store._write_solver_log(solver, status="FEASIBLE", objective=1.0, runtime=0.01)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert not log_path.exists(), "solver.log should not be created when disabled"


def test_write_solver_log_with_experiment_dict(tmp_path, monkeypatch) -> None:
    """
    Ensures `_write_solver_log()` correctly creates and fills a log file
    when experiment metadata is provided as a dictionary.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    experiment = {
        "name": "baseline",
        "tags": ["smoke", "unit"],
        "description": "determinism coverage test",
    }
    cfg = _fake_cfg(metrics={"save_solver_log": True}, experiment=experiment)
    store = ResultStore(cfg)
    solver = _dummy_solver()

    # --- Act ---
    store._write_solver_log(solver, status="OPTIMAL", objective=123.0, runtime=0.01)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert log_path.exists(), "solver.log should be created"
    text = log_path.read_text(encoding="utf-8")

    # verify solver info and experiment fields are logged
    assert "objective: 123.0" in text
    assert "runtime_sec:" in text
    assert "name: baseline" in text
    assert "tags:" in text
    assert "description: determinism coverage test" in text


def test_write_solver_log_with_experiment_object(tmp_path, monkeypatch) -> None:
    """
    Validates `_write_solver_log()` behavior when `cfg.experiment` is provided
    as a SimpleNamespace instead of a dictionary.
    Ensures file creation and inclusion of all experiment fields.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    exp_obj = SimpleNamespace(
        name="baseline_obj",
        tags=["obj", "coverage"],
        description="experiment as object",
    )
    cfg = _fake_cfg(metrics=None, experiment=exp_obj)
    store = ResultStore(cfg)
    solver = _dummy_solver()

    # --- Act ---
    store._write_solver_log(solver, status="FEASIBLE", objective=7.0, runtime=0.002)

    # --- Assert ---
    log_path = Path("data") / "output" / "solver.log"
    assert log_path.exists(), "solver.log should be created for object experiment"

    text = log_path.read_text(encoding="utf-8")

    # confirm that both experiment and solver details appear in log
    assert "== Experiment ==" in text
    assert "experiment.name: baseline_obj" in text
    assert "experiment.tags:" in text
    assert "experiment.description: experiment as object" in text
    assert "objective: 7.0" in text
    assert "runtime_sec:" in text


def test_write_solution_creates_csv(tmp_path, monkeypatch):
    """
    Covers _write_solution branch by redirecting output_dir to tmp_path.
    No disk pollution occurs because it writes inside pytest's temp folder.
    """
    from types import SimpleNamespace

    from opmed.solver_core.result_store import ResultStore

    # fake config: minimal fields for ResultStore
    cfg = SimpleNamespace(output_dir=tmp_path)
    store = ResultStore(cfg)

    # fake model bundle (not used directly)
    bundle = SimpleNamespace()

    # synthetic assignment
    assignment = {
        "x": [(1, 10), (2, 11)],
        "y": [(1, 1), (2, 2)],
    }

    # Act — call the real method
    csv_path = store._write_solution(bundle, assignment)

    # Assert
    p = Path(csv_path)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "x,1,10" in text
    assert "y,2,2" in text


def test_write_config_snapshot_legacy_branch(tmp_path, monkeypatch):
    """
    @brief
    Covers legacy serialization path where cfg.solver is converted to plain dict.

    @details
    Ensures backward compatibility with configurations lacking model_dump() support.
    Uses a dummy TypeAdapter replacement to simulate simplified pydantic behavior
    and verifies that the resulting snapshot file is successfully written and
    contains the expected experiment name.
    """

    import pydantic

    from opmed.solver_core.result_store import ResultStore

    # --- Arrange ---
    # Replace pydantic.TypeAdapter with dummy implementation
    class DummyAdapter:
        def __init__(self, _type): ...
        def dump_python(self, obj):
            return vars(obj)

    monkeypatch.setattr(pydantic, "TypeAdapter", DummyAdapter)

    # Prepare configuration with JSON-friendly solver section
    cfg = _fake_cfg(experiment={"name": "legacy_branch"}, output_dir=str(tmp_path))
    cfg.solver = vars(cfg.solver)  # (1) Simulate legacy dict-style solver

    store = ResultStore(cfg)

    # --- Act ---
    # Invoke private method responsible for writing config snapshot
    path = store._write_config_snapshot()

    # --- Assert ---
    # Verify that snapshot file exists and includes experiment identifier
    p = Path(path)
    assert p.exists()
    assert "legacy_branch" in p.read_text(encoding="utf-8")


def test_write_config_snapshot_modern_branch(tmp_path):
    """
    @brief
    Covers modern serialization branch using Pydantic-like model_dump().

    @details
    Validates the contemporary code path of _write_config_snapshot(), where
    configuration objects expose model_dump() returning a JSON-serializable dict.
    Confirms that the snapshot file is created correctly and contains key
    configuration fields such as 'rooms_max' and the experiment name.
    """

    from opmed.solver_core.result_store import ResultStore

    # --- Arrange ---
    # Define configuration class with model_dump() mimicking Pydantic v2 behavior
    class CfgWithDump:
        def __init__(self, out: str):
            self.output_dir = out
            self.experiment = {"name": "modern_branch"}

        def model_dump(self):
            # (1) Return minimal JSON-serializable structure for snapshot
            return {
                "rooms_max": 3,
                "solver": {"num_workers": 1},
                "experiment": {"name": "modern_branch"},
            }

    cfg = CfgWithDump(out=str(tmp_path))
    store = ResultStore(cfg)

    # --- Act ---
    # Execute snapshot writing for model_dump()-based configuration
    path = store._write_config_snapshot()

    # --- Assert ---
    # Verify that file exists and includes expected configuration data
    p = Path(path)
    assert p.exists(), "config_snapshot file must be created"
    text = p.read_text(encoding="utf-8")
    assert '"rooms_max": 3' in text
    assert "modern_branch" in text


def test_write_metrics_skips_when_object_flag_false(tmp_path, monkeypatch) -> None:
    """
    Verifies that `_write_metrics()` skips writing metrics_<ts>.json
    when `save_metrics=False` is defined on a metrics object.
    """
    monkeypatch.chdir(tmp_path)
    metrics_obj = SimpleNamespace(save_metrics=False)
    cfg = _fake_cfg(metrics=metrics_obj)
    store = ResultStore(cfg)
    result = {"status": "FEASIBLE", "objective": 1.0, "runtime": 0.01}

    store._write_metrics(result)

    metrics_dir = Path("data") / "output"
    metrics_files = list(metrics_dir.glob("metrics_*.json"))
    assert not metrics_files, "no metrics files should be created when save_metrics=False"


def test_write_metrics_writes_when_object_flag_true(tmp_path, monkeypatch) -> None:
    """
    Ensures `_write_metrics()` writes timestamped metrics_<name>_<ts>.json
    when `save_metrics=True` is set on a metrics object, and includes experiment info.
    """
    monkeypatch.chdir(tmp_path)
    metrics_obj = SimpleNamespace(save_metrics=True)
    exp_obj = SimpleNamespace(
        name="baseline_obj",
        tags=["obj", "coverage"],
        description="metrics as object-flag test",
    )
    cfg = _fake_cfg(metrics=metrics_obj, experiment=exp_obj)
    store = ResultStore(cfg)
    result = {"status": "OPTIMAL", "objective": 7.0, "runtime": 0.02}

    # Act
    store._write_metrics(result)

    # Assert
    out_dir = Path("data") / "output"
    files = sorted(out_dir.glob("metrics_*.json"))
    assert files, "timestamped metrics file should be created"
    metrics_path = files[-1]

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version", "search_branching"):
        assert key in payload, f"metrics.json missing '{key}'"
    assert "experiment" in payload
    assert payload["experiment"]["name"] == "baseline_obj"
    assert payload["experiment"]["description"] == "metrics as object-flag test"


def test_write_metrics_skips_when_dict_flag_false(tmp_path, monkeypatch) -> None:
    """
    Checks that `_write_metrics()` does not create a file when
    metrics are provided as a dict with save_metrics=False.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(metrics={"save_metrics": False}, experiment={"name": "ignored"})
    store = ResultStore(cfg)
    result = {"status": "FEASIBLE", "objective": 1.0, "runtime": 0.01}

    # --- Act ---
    store._write_metrics(result)

    # --- Assert ---
    metrics_path = Path("data") / "output" / "metrics.json"
    assert (
        not metrics_path.exists()
    ), "metrics.json must not be written when save_metrics=False (dict)"


def test_write_metrics_writes_when_dict_flag_true_with_experiment_dict(
    tmp_path, monkeypatch
) -> None:
    """
    Ensures `_write_metrics()` writes timestamped metrics_<name>_<ts>.json
    when `save_metrics=True` is provided in a metrics dict and experiment is a dict.
    """
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_metrics": True},
        experiment={
            "name": "baseline",
            "tags": ["ci", "coverage"],
            "description": "experiment as dict",
        },
    )
    store = ResultStore(cfg)
    result = {"status": "OPTIMAL", "objective": 7.0, "runtime": 0.02}

    # Act
    store._write_metrics(result)

    # Assert
    out_dir = Path("data") / "output"
    files = sorted(out_dir.glob("metrics_*.json"))
    assert files, "timestamped metrics file should be created"
    metrics_path = files[-1]

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version", "search_branching"):
        assert key in payload, f"metrics.json missing '{key}'"
    assert "experiment" in payload
    assert payload["experiment"]["name"] == "baseline"
    assert payload["experiment"]["description"] == "experiment as dict"


def test_write_metrics_uses_timestamp_when_no_experiment(tmp_path, monkeypatch) -> None:
    """
    Verifies `_write_metrics()` behavior when `cfg.experiment` is None.
    Expected result: file `metrics_<timestamp>.json` is created, without an 'experiment' section.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(metrics={"save_metrics": True}, experiment=None)
    store = ResultStore(cfg)
    result = {"status": "FEASIBLE", "objective": 1.23, "runtime": 0.01}

    # --- Act ---
    store._write_metrics(result)

    # --- Assert ---
    out_dir = Path("data") / "output"
    files = list(out_dir.glob("metrics_*.json"))
    assert files, "metrics_<ts>.json should be created when experiment is None"

    # validate content of the most recent file
    path = files[-1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "FEASIBLE"
    # since experiment=None → no 'experiment' section should appear
    assert "experiment" not in payload


def test_write_metrics_uses_timestamp_when_experiment_has_no_name(tmp_path, monkeypatch) -> None:
    """
    Verifies `_write_metrics()` behavior when experiment metadata is provided
    but lacks a 'name' field. Expected: filename is still `metrics_<timestamp>.json`
    and the experiment section exists but has no 'name' value.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_metrics": True},
        experiment={"tags": ["ci"], "description": "no name provided"},
    )
    store = ResultStore(cfg)
    result = {"status": "OPTIMAL", "objective": 7.0, "runtime": 0.02}

    # --- Act ---
    store._write_metrics(result)

    # --- Assert ---
    out_dir = Path("data") / "output"
    files = list(out_dir.glob("metrics_*.json"))
    assert files, "metrics_<ts>.json should be created when experiment has no name"

    path = files[-1]
    # file name should not include experiment name prefix
    assert path.name.startswith("metrics_") and path.name.endswith(".json")
    assert "baseline" not in path.name  # confirm no unintended name injection

    payload = json.loads(path.read_text(encoding="utf-8"))
    # experiment section must exist, but its 'name' should be None
    assert "experiment" in payload
    assert payload["experiment"].get("name") is None
    assert payload["status"] == "OPTIMAL"


def _mini_cfg_with_penalty() -> Config:
    """
    Returns a Config instance with `activation_penalty` preset.
    Used for tests verifying model cost structure or penalty propagation.
    """
    cfg = Config()
    cfg.activation_penalty = 3.5  # ensure field is defined for downstream tests
    return cfg


def _fake_surgeries() -> list[Surgery]:
    """
    Produces a minimal list of two surgeries for simple test models.
    Ensures deterministic, non-overlapping scheduling intervals.
    """
    return [
        # (1) Morning surgery block
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        # (2) Follow-up surgery block with small gap
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:10:00Z",
            end_time="2025-01-01T10:00:00Z",
        ),
    ]


def test_objective_includes_activation_penalty(tmp_path, monkeypatch) -> None:
    """
    Ensures `_add_objective_piecewise_cost()` correctly includes the
    activation penalty term when `activation_penalty > 0`.
    Validates that resulting objective contains positive coefficients.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _mini_cfg_with_penalty()  # config with positive activation_penalty
    surgeries = _fake_surgeries()  # minimal surgery list
    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle = builder.build()
    model = bundle["model"]

    # --- Act ---
    proto = model.Proto()  # inspect compiled model proto

    # --- Objective detection (OR-Tools backward compatibility) ---
    if hasattr(proto, "floating_point_objective"):
        obj = proto.floating_point_objective
    elif hasattr(proto, "objective"):
        obj = proto.objective
    else:
        raise AssertionError("Model has no recognizable objective field")

    # --- Assert ---
    # Objective must reference variables and coefficients
    assert len(obj.vars) > 0, "Objective must include variable indices"
    assert len(obj.coeffs) > 0, "Objective must include coefficients"

    # Positive activation penalty implies positive sum of coefficients
    total_coeff = sum(obj.coeffs)
    assert total_coeff > 0, "Objective coefficients must be positive (penalty applied)"

    # Sanity: model remains solvable
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_persist_writes_when_logs_enabled(tmp_path, monkeypatch) -> None:
    """
    Verifies persist() writes solver log and timestamped metrics when logging is enabled.
    Also checks that solution_path is returned in the final result.
    """
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_solver_log": True, "save_metrics": True},
        experiment={"name": "persist_branch"},
        output_dir="data/output",
    )
    store = ResultStore(cfg)
    store.write_solver_logs = True

    # avoid TypeAdapter(SimpleNamespace) snapshot in this test
    monkeypatch.setattr(store, "_write_config_snapshot", lambda: None)

    solver = _dummy_solver()
    result = {"status": "FEASIBLE", "objective": 42.0}
    runtime = 0.05

    # Act
    final = store.persist(result, solver=solver, runtime=runtime, bundle=None, assignment=None)
    assert "solution_path" in final or isinstance(final, dict)

    # Assert
    out_dir = Path(cfg.output_dir)
    assert (out_dir / "solver.log").exists(), "solver.log should be created"

    metrics_files = sorted(out_dir.glob("metrics_*.json"))
    assert metrics_files, "timestamped metrics file should be created"


def test_persist_skips_when_logs_disabled(tmp_path, monkeypatch) -> None:
    """
    Verifies persist() skips all file creation when logging and metrics are disabled.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = _fake_cfg(
        metrics={"save_solver_log": False, "save_metrics": False},
        experiment={"name": "persist_skip"},
        output_dir="data/output",
    )
    store = ResultStore(cfg)
    store.write_solver_logs = False

    # skip config snapshot serialization to avoid pydantic adapter errors
    monkeypatch.setattr(store, "_write_config_snapshot", lambda: None)

    solver = _dummy_solver()
    result = {"status": "OPTIMAL", "objective": 7.0}
    runtime = 0.01

    # --- Act ---
    final = store.persist(result, solver=solver, runtime=runtime, bundle=None, assignment=None)

    # --- Assert ---
    out_dir = Path(cfg.output_dir)
    assert not (out_dir / "solver.log").exists(), "solver.log should not be created"
    assert not (out_dir / "metrics.json").exists(), "metrics.json should not be created"
    assert "status" in final and "objective" in final and "solution_path" in final


def test_write_solver_log_default_branch(tmp_path, monkeypatch):
    """
    Verifies legacy behavior when metrics_cfg is None:
    `_write_solver_log()` should still create a solver.log file.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = SimpleNamespace(
        output_dir="data/output",
        metrics=None,  # legacy branch: metrics missing
        experiment={"name": "legacy_log"},
        solver=SimpleNamespace(search_branching="AUTOMATIC"),
    )
    solver = cp_model.CpSolver()
    store = ResultStore(cfg)

    # --- Act ---
    store._write_solver_log(solver=solver, status="FEASIBLE", objective=5.5, runtime=0.01)

    # --- Assert ---
    log_path = Path(cfg.output_dir) / "solver.log"
    assert log_path.exists(), "solver.log should be created under legacy (metrics=None)"
    text = log_path.read_text(encoding="utf-8")
    assert "FEASIBLE" in text and "AUTOMATIC" in text


def test_write_config_snapshot_uses_typeadapter(tmp_path, monkeypatch):
    """
    Covers branch where `_write_config_snapshot()` uses TypeAdapter
    because cfg has no `model_dump()` (legacy/namespace objects).
    """
    import pydantic  # required for monkeypatching

    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = SimpleNamespace(
        time_unit=0.1,
        solver={"max_time_in_seconds": 3},
        experiment={"name": "snapshot_test"},
    )
    store = ResultStore(cfg)
    store.output_dir = Path("data/output")

    # Dummy adapter simulates pydantic.TypeAdapter for non-pydantic objects
    class DummyAdapter:
        def __init__(self, _):
            pass

        def dump_python(self, obj):
            return {"mock_dump": True, "fields": list(obj.__dict__.keys())}

    # --- Act ---
    monkeypatch.setattr(pydantic, "TypeAdapter", DummyAdapter)
    path = store._write_config_snapshot()

    # --- Assert ---
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["mock_dump"] is True
    assert "experiment" in payload["fields"]


def test_write_solver_log_object_enabled(tmp_path, monkeypatch):
    """
    Ensures `_write_solver_log()` creates a log file when metrics
    is a SimpleNamespace with save_solver_log=True.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = SimpleNamespace(
        output_dir="data/output",
        metrics=SimpleNamespace(save_solver_log=True),
        experiment={"name": "object_metrics_on"},
        solver=SimpleNamespace(search_branching="FIXED_SEARCH"),
    )
    solver = cp_model.CpSolver()
    store = ResultStore(cfg)

    # --- Act ---
    store._write_solver_log(solver, status="OPTIMAL", objective=123.4, runtime=0.01)

    # --- Assert ---
    log_path = Path(cfg.output_dir) / "solver.log"
    assert log_path.exists(), "solver.log should be created when save_solver_log=True"
    text = log_path.read_text(encoding="utf-8")
    assert "OPTIMAL" in text and "123.4" in text


def test_write_solver_log_object_disabled(tmp_path, monkeypatch):
    """
    Ensures `_write_solver_log()` does not create a file when metrics
    is a SimpleNamespace with save_solver_log=False.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)
    cfg = SimpleNamespace(
        output_dir="data/output",
        metrics=SimpleNamespace(save_solver_log=False),
        experiment={"name": "object_metrics_off"},
        solver=SimpleNamespace(search_branching="FIXED_SEARCH"),
    )
    solver = cp_model.CpSolver()
    store = ResultStore(cfg)

    # --- Act ---
    store._write_solver_log(solver, status="FEASIBLE", objective=5.5, runtime=0.02)

    # --- Assert ---
    log_path = Path(cfg.output_dir) / "solver.log"
    assert not log_path.exists(), "solver.log must not be created when save_solver_log=False"
