from __future__ import annotations

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer, SolveResult


def _mini_config() -> Config:
    """
    Creates a minimal Config for quick solver tests.
    Uses two rooms, short 3-second time limit, single thread, and fixed random seed.
    Ensures fast, deterministic runs suitable for unit tests.
    """
    cfg = Config()
    cfg.rooms_max = 2  # minimal room count for lightweight model
    cfg.solver.max_time_in_seconds = 3  # very short solving window
    cfg.solver.num_workers = 1  # enforce single-threaded determinism
    cfg.solver.search_branching = "AUTOMATIC"
    cfg.solver.random_seed = 42  # fixed seed for reproducible results
    return cfg


def _mini_surgeries() -> list[Surgery]:
    """
    Produces a tiny synthetic set of surgeries for test runs.
    Returns three short, non-overlapping surgeries to guarantee quick feasibility.
    """
    return [
        # (1) Morning case 08:00-09:00
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        # (2) Second case after 10-minute gap
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:10:00Z",
            end_time="2025-01-01T10:00:00Z",
        ),
        # (3) Final short case mid-morning
        Surgery(
            surgery_id="s3",
            start_time="2025-01-01T10:30:00Z",
            end_time="2025-01-01T11:15:00Z",
        ),
    ]


def test_optimizer_solve_feasible_and_objective_present(tmp_path, monkeypatch) -> None:
    """
    End-to-end smoke test: verifies optimizer feasibility and valid objective,
    with optional suppression of ResultStore file outputs.
    """
    SAVE_ARTIFACTS = False  # toggle to True for manual debugging with disk output

    # --- Arrange ---
    cfg = _mini_config()
    surgeries = _mini_surgeries()
    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle = builder.build()

    # --- Optional: silence ResultStore side-effects ---
    if not SAVE_ARTIFACTS:
        # redirect cwd to temp dir to isolate any accidental writes
        monkeypatch.chdir(tmp_path)

        # import ResultStore dynamically to avoid circular import at top-level
        import opmed.solver_core.result_store as result_store_mod

        # patch out writing functions (no disk I/O)
        monkeypatch.setattr(result_store_mod.ResultStore, "_write_metrics", lambda *a, **k: None)
        monkeypatch.setattr(result_store_mod.ResultStore, "_write_solver_log", lambda *a, **k: None)
        if hasattr(result_store_mod.ResultStore, "_write_config_snapshot"):
            monkeypatch.setattr(
                result_store_mod.ResultStore, "_write_config_snapshot", lambda *a, **k: None
            )
        if hasattr(result_store_mod.ResultStore, "_write_solution"):
            monkeypatch.setattr(
                result_store_mod.ResultStore, "_write_solution", lambda *a, **k: None
            )

    # --- Act ---
    opt = Optimizer(cfg)
    res: SolveResult = opt.solve(bundle)

    # --- Assert ---
    assert res["status"] in ("FEASIBLE", "OPTIMAL")
    assert res["objective"] is not None
    assert isinstance(res["assignment"], dict)
    assert "x" in res["assignment"] and "y" in res["assignment"]
