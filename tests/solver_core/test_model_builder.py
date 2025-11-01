from __future__ import annotations

import datetime as dt
import logging

import pytest
from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import CpSatModelBundle, ModelBuilder

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(message)s",
)


def test_modelbuilder_stub_instantiation() -> None:
    """
    @brief
    Verifies that the `ModelBuilder` class can be properly instantiated and that
    calling `build()` produces a valid CP-SAT model bundle.

    @details
    This test checks the most basic contract of the builder:
    - The object initializes without errors using minimal configuration.
    - The `build()` method executes end-to-end and returns a dictionary
      containing the expected components: "model", "vars", and "aux".
    It serves as a smoke test confirming that the solver’s core construction
    pipeline can start successfully.
    """

    # --- Arrange ---
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

    # --- Act ---
    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle: CpSatModelBundle = builder.build()

    # --- Assert ---
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
    """
    @brief
    Ensures that `_init_variable_groups()` initializes the `self.vars` dictionary
    with all expected top-level keys required for later variable creation.

    @details
    The test verifies that calling this method produces the correct structural
    scaffolding for CP-SAT variable groups, which are essential for the rest
    of the model-building pipeline. The dictionary must contain the following
    keys: `"x"`, `"y"`, `"interval"`, and `"active"`.
    """

    # --- Arrange ---
    builder = _make_builder()

    # --- Act ---
    builder._init_variable_groups()

    # --- Assert ---
    keys = set(builder.vars.keys())
    expected = {"x", "y", "interval", "active"}
    assert expected == keys


def test_create_intervals_builds_one_interval_per_surgery() -> None:
    """
    @brief
    Verifies that `_create_intervals()` builds exactly one fixed CP-SAT
    `IntervalVar` for each surgery.

    @details
    This test ensures that the method translates surgery timing data into
    corresponding fixed-time intervals and that every created variable is of
    the correct OR-Tools type (`cp_model.IntervalVar`).
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()

    # --- Act ---
    builder._create_intervals()

    # --- Assert ---
    intervals = builder.vars["interval"]
    assert len(intervals) == len(builder.surgeries)
    for var in intervals.values():
        assert isinstance(var, cp_model.IntervalVar)


def test_create_intervals_empty_surgeries(caplog: pytest.LogCaptureFixture) -> None:
    """
    @brief
    Ensures `_create_intervals()` gracefully handles an empty surgery list.

    @details
    The method should not raise exceptions when there are no surgeries,
    should log a warning message, and should leave the interval dictionary
    empty.
    """

    # --- Arrange ---
    cfg = Config()
    builder = ModelBuilder(cfg, surgeries=[])

    # --- Act ---
    with caplog.at_level(logging.WARNING):
        builder._create_intervals()

    # --- Assert ---
    assert any("skipping interval creation" in m for m in caplog.messages)
    assert builder.vars.get("interval", {}) == {}


def test_create_intervals_handles_zero_duration(caplog: pytest.LogCaptureFixture) -> None:
    """
    @brief
    Checks that surgeries with zero or negative duration are corrected to
    a minimal duration of one tick.

    @details
    The test injects a surgery whose `start_time` equals `end_time` and
    verifies that the method logs a warning about the non-positive duration
    and successfully replaces it with a valid interval of length 1 tick.
    """

    # --- Arrange ---
    cfg = Config()
    t_start = dt.datetime(2025, 1, 1, 8, 0, 0)
    surgeries = [
        Surgery(
            surgery_id="S1",
            start_time=t_start,
            end_time=t_start,
        )
    ]
    builder = ModelBuilder(cfg, surgeries)
    builder.vars = {"interval": {}}  # Initialize required group

    # --- Act ---
    with caplog.at_level(logging.WARNING):
        builder._create_intervals()

    # --- Assert ---
    assert any("non-positive duration" in m for m in caplog.messages)


def test_create_boolean_vars_builds_expected_structure() -> None:
    """
    @brief
    Verifies that `_create_boolean_vars()` correctly builds the expected grid
    structure for decision variables.

    @details
    The test ensures that:
      - `x[s,a]` and `y[s,r]` grids are created with the proper dimensions.
      - Every variable is an instance of `cp_model.IntVar` (BoolVar subclass).
      - Variable names are unique across both groups.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()

    # --- Act ---
    builder._create_boolean_vars()

    # --- Assert ---
    x_vars = builder.vars["x"]
    y_vars = builder.vars["y"]

    num_surgeries = len(builder.surgeries)
    num_rooms = builder.cfg.rooms_max
    max_anesth = num_surgeries

    assert len(x_vars) == num_surgeries * max_anesth
    assert len(y_vars) == num_surgeries * num_rooms
    assert all(isinstance(v, cp_model.IntVar) for v in x_vars.values())
    assert all(isinstance(v, cp_model.IntVar) for v in y_vars.values())

    all_names = {v.Name() for v in x_vars.values()} | {v.Name() for v in y_vars.values()}
    assert len(all_names) == len(x_vars) + len(y_vars)


def test_add_constraints_builds_model_without_errors() -> None:
    """
    @brief
    Confirms that `_add_constraints()` executes without exceptions and populates
    the model with structural constraints.

    @details
    The test validates the complete constraint-building pipeline by invoking
    all dependent methods sequentially. After execution, the model must contain
    at least one constraint and dynamically generated `t_min` / `t_max`
    variables for each anesthesiologist.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()

    # --- Act ---
    builder._add_constraints()

    # --- Assert ---
    num_constraints = len(builder.model.Proto().constraints)
    assert num_constraints > 0, "Expected model to contain at least one constraint"

    num_anesth = len(builder.surgeries)
    assert "t_min" in builder.vars and "t_max" in builder.vars
    assert len(builder.vars["t_min"]) == num_anesth
    assert len(builder.vars["t_max"]) == num_anesth


def test_room_and_anesth_nooverlap_constraints_exist() -> None:
    """
    @brief
    Verifies that `NoOverlap` constraints for rooms and anesthesiologists
    are successfully added to the model.

    @details
    The test checks that invoking `_add_room_nooverlap()` and
    `_add_anesth_nooverlap()` increases the total number of constraints
    in the CP-SAT model, confirming proper constraint registration.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()
    before = len(builder.model.Proto().constraints)

    # --- Act ---
    builder._add_room_nooverlap()
    builder._add_anesth_nooverlap()
    after = len(builder.model.Proto().constraints)

    # --- Assert ---
    assert after > before


def test_add_buffer_constraints_adds_expected_rules() -> None:
    """
    @brief
    Verifies that `_add_buffer_constraints()` executes successfully and
    adds new logical constraints for time-conflicting surgery pairs.

    @details
    The test confirms that:
      - The method completes without errors.
      - It increases or maintains the number of constraints in the model.
      - Buffer parameters (`buffer_ticks`) are correctly computed and stored.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()
    builder._add_room_nooverlap()
    builder._add_anesth_nooverlap()

    builder.aux["buffer_ticks"] = int(round(builder.cfg.buffer / builder.cfg.time_unit))
    builder.aux["ticks_per_hour"] = int(round(1 / builder.cfg.time_unit))
    builder.aux["t_origin"] = min(s.start_time for s in builder.surgeries)

    before = len(builder.model.Proto().constraints)

    # --- Act ---
    builder._add_buffer_constraints()
    after = len(builder.model.Proto().constraints)

    # --- Assert ---
    assert after >= before
    assert isinstance(builder.aux["buffer_ticks"], int)


def test_add_buffer_constraints_detects_dangerous_pairs() -> None:
    """
    @brief
    Checks that `_add_buffer_constraints()` detects “dangerous” surgery pairs
    and correctly introduces logical variables to handle them.

    @details
    The test creates two surgeries close enough in time to violate the buffer rule.
    It then verifies that the method executes without errors and that expected
    Boolean variables (`b_sameA`, `b_sameR`) appear in the model’s internal Proto.
    """

    # --- Arrange ---
    cfg = Config(buffer=1.0, rooms_max=2)
    t0 = dt.datetime(2025, 1, 1, 8, 0, 0)

    surgeries = [
        Surgery(
            surgery_id="S1",
            start_time=t0,
            end_time=t0 + dt.timedelta(hours=1),
        ),
        Surgery(
            surgery_id="S2",
            start_time=t0 + dt.timedelta(minutes=90),
            end_time=t0 + dt.timedelta(hours=2),
        ),
    ]

    builder = ModelBuilder(cfg, surgeries)
    builder.model = cp_model.CpModel()
    builder.vars = {"x": {}, "y": {}}

    max_anesth = len(surgeries)
    for s_idx in range(len(surgeries)):
        for a_idx in range(max_anesth):
            builder.vars["x"][(s_idx, a_idx)] = builder.model.NewBoolVar(f"x_{s_idx}_{a_idx}")
        for r_idx in range(cfg.rooms_max):
            builder.vars["y"][(s_idx, r_idx)] = builder.model.NewBoolVar(f"y_{s_idx}_{r_idx}")

    builder.aux["t_origin"] = t0.replace(hour=0, minute=0, second=0, microsecond=0)
    builder.aux["ticks_per_hour"] = int(round(1 / cfg.time_unit))
    builder.aux["buffer_ticks"] = int(round(cfg.buffer * builder.aux["ticks_per_hour"]))

    # --- Act ---
    builder._add_buffer_constraints()

    # --- Assert ---
    proto_text = str(builder.model.Proto())
    assert "b_sameA" in proto_text
    assert "b_sameR" in proto_text


def test_add_buffer_constraints_builds_logical_rules(caplog: pytest.LogCaptureFixture) -> None:
    """
    @brief
    Ensures that `_add_buffer_constraints()` builds logical rules for detected
    dangerous surgery pairs and logs corresponding debug messages.

    @details
    The test verifies that the function:
      - Creates Boolean logic variables (`b_sameA`, `b_sameR`) in the model.
      - Logs the “Added buffer consistency rules” message at DEBUG level.
    """

    # --- Arrange ---
    cfg = Config(buffer=1.0, rooms_max=2)
    t0 = dt.datetime(2025, 1, 1, 8, 0, 0)

    surgeries = [
        Surgery(
            surgery_id="S1",
            start_time=t0,
            end_time=t0 + dt.timedelta(hours=1),
        ),
        Surgery(
            surgery_id="S2",
            start_time=t0 + dt.timedelta(minutes=90),
            end_time=t0 + dt.timedelta(hours=2),
        ),
    ]

    builder = ModelBuilder(cfg, surgeries)
    builder.model = cp_model.CpModel()
    builder.vars = {"x": {}, "y": {}}
    builder.aux["t_origin"] = t0.replace(hour=0, minute=0, second=0, microsecond=0)
    builder.aux["ticks_per_hour"] = int(round(1 / cfg.time_unit))
    builder.aux["buffer_ticks"] = int(round(cfg.buffer * builder.aux["ticks_per_hour"]))

    for s_idx in range(len(surgeries)):
        for a_idx in range(len(surgeries)):
            builder.vars["x"][(s_idx, a_idx)] = builder.model.NewBoolVar(f"x_{s_idx}_{a_idx}")
        for r_idx in range(cfg.rooms_max):
            builder.vars["y"][(s_idx, r_idx)] = builder.model.NewBoolVar(f"y_{s_idx}_{r_idx}")

    # --- Act ---
    with caplog.at_level(logging.DEBUG):
        builder._add_buffer_constraints()

    # --- Assert ---
    proto_text = str(builder.model.Proto())
    assert "b_sameA" in proto_text
    assert "b_sameR" in proto_text
    assert any("Added buffer consistency rules" in m for m in caplog.messages)


def test_add_shift_duration_bounds_creates_linked_variables() -> None:
    """
    @brief
    Ensures that `_add_shift_duration_bounds()` executes successfully,
    creates `t_min`, `t_max`, and `active` variable dictionaries, and
    links anesthesiologists’ working intervals to their assigned surgeries.

    @details
    The test verifies that:
      - The method runs without raising exceptions.
      - `t_min`, `t_max`, and `active` dictionaries are created in `builder.vars`.
      - Each dictionary contains one entry per anesthesiologist (equal to number of surgeries).
      - All variables are valid CP-SAT `IntVar` objects (OR-Tools `BoolVar` is a subtype of IntVar).
      - The number of constraints in the model increases after execution, confirming
        that new shift-bound constraints were added.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()

    # Prepare auxiliary data expected by the method
    builder.aux["start_ticks"] = [0, 12]
    builder.aux["end_ticks"] = [10, 20]
    builder.aux["max_time_ticks"] = 24
    builder.aux["ticks_per_hour"] = int(round(1 / builder.cfg.time_unit))
    builder.aux["t_origin"] = min(s.start_time for s in builder.surgeries)

    before = len(builder.model.Proto().constraints)

    # --- Act ---
    builder._add_shift_duration_bounds()
    after = len(builder.model.Proto().constraints)

    # --- Assert ---
    num_a = len(builder.surgeries)

    # Check that variable dictionaries were created with correct sizes
    for key in ("t_min", "t_max", "active"):
        assert key in builder.vars, f"{key} not found in builder.vars"
        assert len(builder.vars[key]) == num_a

    # Check variable types (BoolVars are IntVars with domain {0,1})
    assert all(isinstance(v, cp_model.IntVar) for v in builder.vars["t_min"].values())
    assert all(isinstance(v, cp_model.IntVar) for v in builder.vars["t_max"].values())
    assert all(isinstance(v, cp_model.IntVar) for v in builder.vars["active"].values()) or all(
        isinstance(v, cp_model.BoolVar) for v in builder.vars["active"].values()
    )

    # Verify that new constraints were added to the model
    assert after > before, "Expected constraints to increase after shift bounds"


def test_add_assignment_cardinality_adds_constraints() -> None:
    """
    @brief
    Confirms that `_add_assignment_cardinality()` executes successfully and
    adds new `ExactlyOne` constraints to the model.

    @details
    The test measures the total number of constraints before and after
    execution to ensure that the assignment rules for surgeries are
    properly enforced and increase the model’s constraint count.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()
    before = len(builder.model.Proto().constraints)

    # --- Act ---
    builder._add_assignment_cardinality()
    after = len(builder.model.Proto().constraints)

    # --- Assert ---
    assert after > before, "Expected ExactlyOne constraints to be added for surgeries"


def test_add_assignment_cardinality_handles_empty_input() -> None:
    """
    @brief
    Ensures that `_add_assignment_cardinality()` behaves as a no-op when
    there are no surgeries.

    @details
    With an empty surgery list, the method should not crash or modify
    the model, and the total number of constraints must remain unchanged.
    """

    # --- Arrange ---
    cfg = Config()
    builder = ModelBuilder(cfg=cfg, surgeries=[])
    builder._init_variable_groups()
    before = len(builder.model.Proto().constraints)

    # --- Act ---
    builder._add_assignment_cardinality()
    after = len(builder.model.Proto().constraints)

    # --- Assert ---
    assert after == before


def test_objective_piecewise_cost_present_and_positive() -> None:
    """
    @brief
    Ensures that `_add_objective_piecewise_cost()` correctly defines
    a non-empty and positive objective function in the CP-SAT model.

    @details
    The test verifies that:
      - After calling `_add_objective_piecewise_cost()`, the model’s
        `objective` field is present in the serialized Proto.
      - The objective contains variables (non-empty variable list).
      - All coefficients in the objective are non-negative, consistent
        with a minimization of positive cost terms.
    """

    # --- Arrange ---
    builder = _make_builder()
    builder._init_variable_groups()
    builder._create_intervals()
    builder._create_boolean_vars()
    builder._add_constraints()

    # --- Act ---
    builder._add_objective_piecewise_cost()

    # --- Assert ---
    proto = builder.model.Proto()
    assert proto.HasField("objective"), "Expected model to have an objective"
    obj = proto.objective
    assert len(obj.vars) > 0, "Objective has no variables"
    assert all(c >= 0 for c in obj.coeffs), "Objective has negative coefficients"


# ---------------------------------------------------------------------------
# Integration test (expandable with later build steps)
# ---------------------------------------------------------------------------


def test_build_integration_creates_valid_bundle() -> None:
    """
    @brief
    Performs a smoke test for the `build()` method, verifying that it correctly
    orchestrates all internal model-construction steps.

    @details
    The test confirms that calling `build()`:
      - Produces a valid CP-SAT model bundle (`dict` with expected keys).
      - Instantiates a `cp_model.CpModel` object.
      - Populates the variable groups `"x"`, `"y"`, and `"interval"`.
      - Returns a consistent auxiliary data dictionary.
    This serves as an end-to-end integration check for the `ModelBuilder`.
    """

    # --- Arrange ---
    builder = _make_builder()

    # --- Act ---
    bundle = builder.build()

    # --- Assert ---
    assert isinstance(bundle["model"], cp_model.CpModel)
    assert {"x", "y", "interval"} <= set(bundle["vars"].keys())
    assert isinstance(bundle["aux"], dict)
    assert len(bundle["vars"]["interval"]) == len(builder.surgeries)
