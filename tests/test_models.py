from datetime import datetime

import pytest

from opmed.schemas.models import Config, SolutionRow, SolverConfig, Surgery

# --- Cross-version UTC alias: Py 3.11.4+ has datetime.UTC; older use timezone.utc.
try:
    UTC = datetime.UTC  # type: ignore[attr-defined]
except AttributeError:
    from zoneinfo import ZoneInfo

    UTC = ZoneInfo("UTC")


def test_surgery_model_valid():
    s = Surgery(
        surgery_id="S001",
        start_time=datetime(2025, 10, 29, 8, 30, tzinfo=UTC),
        end_time=datetime(2025, 10, 29, 10, 15, tzinfo=UTC),
        duration=1.75,
        room_hint="A1",
    )
    assert s.surgery_id == "S001"
    assert s.duration == pytest.approx(1.75)
    assert s.start_time < s.end_time


def test_config_and_solver_defaults():
    cfg = Config()
    assert isinstance(cfg.solver, SolverConfig)
    assert cfg.rooms_max == 20
    assert cfg.solver.search_branching == "AUTOMATIC"

    data = cfg.model_dump()
    assert "solver" in data


def test_solution_row_schema_and_serialization():
    sol = SolutionRow(
        surgery_id="S001",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        anesthetist_id="A01",
        room_id="R1",
    )
    assert "surgery_id" in sol.model_dump()

    schema = SolutionRow.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
