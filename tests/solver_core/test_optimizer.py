from __future__ import annotations

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer, SolveResult


def _mini_config() -> Config:
    """
    @brief
    Creates a minimal configuration object for fast solver tests.

    @details
    Generates a compact `Config` with:
      • only two available rooms,
      • a very short time limit (3 seconds),
      • single-threaded solver execution,
      • fixed random seed for reproducibility.

    This configuration reduces solver complexity while preserving
    realistic parameter structure for end-to-end tests.

    @returns
        Config — lightweight configuration instance suitable for unit tests.
    """
    cfg = Config()
    cfg.rooms_max = 2  # small number of rooms for speed
    cfg.solver.max_time_in_seconds = 3  # quick limit to avoid long solves
    cfg.solver.num_workers = 1  # deterministic single-threaded mode
    cfg.solver.search_branching = "AUTOMATIC"
    cfg.solver.random_seed = 42
    return cfg


def _mini_surgeries() -> list[Surgery]:
    """
    @brief
    Produces a compact synthetic dataset of surgeries for test runs.

    @details
    Returns three fixed, non-overlapping surgeries within a single day.
    These short intervals simulate realistic scheduling inputs without
    introducing conflicts, allowing the model to reach feasibility quickly.

    @returns
        list[Surgery] — three surgery records with ISO-8601 timestamps.
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


def test_optimizer_solve_feasible_and_objective_present() -> None:
    """
    @brief
    End-to-end smoke test verifying that the optimizer produces
    a feasible (or optimal) schedule and a valid objective function.

    @details
    Steps:
      1. Build a minimal model using `_mini_config()` and `_mini_surgeries()`.
      2. Run the `Optimizer.solve()` routine.
      3. Confirm that:
         - The solver status is FEASIBLE or OPTIMAL.
         - The objective field is present and non-null.
         - The assignment dictionary (`x`, `y`) contains valid results.

    This test ensures correct integration between model construction
    and solver execution, verifying that all core subsystems interact
    coherently under time-limited solving conditions.

    @returns
        None. Assertions validate the model’s solvability and output integrity.
    """

    # --- Arrange ---
    cfg = _mini_config()
    surgeries = _mini_surgeries()

    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle = builder.build()
    assert isinstance(bundle["model"], cp_model.CpModel)  # sanity check

    # --- Act ---
    opt = Optimizer(cfg)
    res: SolveResult = opt.solve(bundle)

    # --- Assert ---
    assert res["status"] in ("FEASIBLE", "OPTIMAL")
    assert res["objective"] is not None
    assert isinstance(res["assignment"], dict)
    assert "x" in res["assignment"] and "y" in res["assignment"]
