from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import opmed.solver_core.result_store as result_store_mod  # для monkeypatch
from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer


def _synthetic_surgeries() -> list[Surgery]:
    """
    Generates a small synthetic dataset of sequential surgeries for testing.

    Returns:
        List[Surgery]: Six synthetic surgeries spaced by 45 min, each 30 min long.
    """
    # (1) Base timestamp for the first surgery (UTC)
    base = datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)
    surgeries: list[Surgery] = []

    # (2) Build six consecutive surgeries with slight overlaps/gaps
    for i in range(6):
        start = base + timedelta(minutes=45 * i)
        end = start + timedelta(minutes=30)
        surgeries.append(
            Surgery(
                surgery_id=f"s{i+1}",
                start_time=start,
                end_time=end,
            )
        )

    # (3) Persist a small CSV to the same path as production code expects
    out_dir = Path("data") / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"synthetic_small_surgeries_{ts}.csv"

    # (4) Write simple CSV with ISO timestamps
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        import csv as _csv

        w = _csv.writer(f)
        w.writerow(["surgery_id", "start_time", "end_time", "duration", "room_id"])
        for s in surgeries:
            w.writerow([s.surgery_id, s.start_time.isoformat(), s.end_time.isoformat(), "", ""])

    # (5) Return in-memory objects for direct test use
    return surgeries


def test_end_to_end_model_solver_metrics(tmp_path: Path, monkeypatch) -> None:
    """
    End-to-end integration test: model → solver → metrics.

    Two execution modes:
        SAVE_ARTIFACTS = False → fast CI run, no file output
        SAVE_ARTIFACTS = True  → writes real artifacts and validates them
    """
    SAVE_ARTIFACTS = False  # toggle mode

    # ARRANGE — configuration and environment setup
    cfg = Config.model_construct()
    cfg.rooms_max = 3
    cfg.solver.num_workers = 1
    cfg.solver.max_time_in_seconds = 5
    cfg.solver.random_seed = 0
    cfg.solver.search_branching = "AUTOMATIC"

    if SAVE_ARTIFACTS:
        monkeypatch.chdir(tmp_path)
        # mute all ResultStore side-effects for clean CI run
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

    # ACT — generate sample surgeries and solve model
    surgeries = _synthetic_surgeries()
    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle = builder.build()
    opt = Optimizer(cfg)
    result = opt.solve(bundle)

    # ASSERT — verify solver result and optional artifacts
    assert result["status"] in ("FEASIBLE", "OPTIMAL")

    if not SAVE_ARTIFACTS:
        # quick sanity: objective should be non-negative
        assert result["objective"] is None or float(result["objective"]) >= 0.0
        return

    # Debug mode: ensure artifact files exist and contain expected keys
    out_dir = Path("data") / "output"
    metrics_path = out_dir / "metrics.json"
    log_path = out_dir / "solver.log"

    assert metrics_path.exists(), "metrics.json should be created"
    assert log_path.exists(), "solver.log should be created"

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    for key in ("status", "objective", "runtime", "ortools_version"):
        assert key in payload

    objective_value = float(payload["objective"])
    assert objective_value > 0.0

    # Derived sanity metric: utilization ratio must be positive
    total_hours = sum((s.end_time - s.start_time).total_seconds() / 3600.0 for s in surgeries)
    utilization = total_hours / objective_value
    assert utilization > 0.0
