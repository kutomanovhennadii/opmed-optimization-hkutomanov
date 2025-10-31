from __future__ import annotations

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import CpSatModelBundle, ModelBuilder


def test_modelbuilder_stub_instantiation() -> None:
    """Ensure ModelBuilder can be instantiated and build() returns a valid bundle."""
    # Minimal config and synthetic surgeries
    cfg = Config()
    surgeries = [
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:30:00Z",
            end_time="2025-01-01T10:30:00Z",
        ),
    ]

    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle: CpSatModelBundle = builder.build()

    assert isinstance(bundle, dict)
    for key in ("model", "vars", "aux"):
        assert key in bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_builder() -> ModelBuilder:
    """Create a ModelBuilder instance with two synthetic surgeries."""
    cfg = Config()
    surgeries = [
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:30:00Z",
            end_time="2025-01-01T10:30:00Z",
        ),
    ]
    return ModelBuilder(cfg=cfg, surgeries=surgeries)


# ---------------------------------------------------------------------------
# Unit-level tests for private methods
# ---------------------------------------------------------------------------


def test_init_variable_groups_creates_required_keys() -> None:
    builder = _make_builder()
    builder._init_variable_groups()

    keys = builder.vars.keys()
    assert {"x", "y", "interval"} == set(keys)
    assert all(isinstance(v, dict) for v in builder.vars.values())


def test_create_intervals_builds_one_interval_per_surgery() -> None:
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()

    intervals = builder.vars["interval"]
    assert len(intervals) == len(builder.surgeries)
    for var in intervals.values():
        assert isinstance(var, cp_model.IntervalVar)


def test_create_boolean_vars_builds_expected_structure() -> None:
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_boolean_vars()

    x_vars = builder.vars["x"]
    y_vars = builder.vars["y"]

    assert len(x_vars) > 0
    assert len(y_vars) > 0
    assert all(isinstance(v, cp_model.IntVar) for v in x_vars.values())
    assert all(isinstance(v, cp_model.IntVar) for v in y_vars.values())

    # Names must be unique
    all_names = {v.Name() for v in x_vars.values()} | {v.Name() for v in y_vars.values()}
    assert len(all_names) == len(x_vars) + len(y_vars)


# ---------------------------------------------------------------------------
# Integration test (expandable with later build steps)
# ---------------------------------------------------------------------------


def test_build_integration_creates_valid_bundle() -> None:
    """Smoke test for build() — verifies orchestration of all internal steps."""
    builder = _make_builder()
    bundle = builder.build()

    assert isinstance(bundle["model"], cp_model.CpModel)
    assert {"x", "y", "interval"} <= set(bundle["vars"].keys())
    assert isinstance(bundle["aux"], dict)
    assert len(bundle["vars"]["interval"]) == len(builder.surgeries)
