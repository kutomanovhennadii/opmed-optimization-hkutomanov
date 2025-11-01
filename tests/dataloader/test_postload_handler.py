# tests/dataloader/test_postload_handler.py
import json
import logging
from pathlib import Path

import pytest

from opmed.dataloader.postload_handler import LoadResultHandler
from opmed.dataloader.types import LoadResult
from opmed.schemas.models import Surgery


def _fake_surgeries():
    return [
        Surgery(
            surgery_id="S001",
            start_time="2025-01-01T07:00:00",
            end_time="2025-01-01T08:00:00",
        ),
        Surgery(
            surgery_id="S002",
            start_time="2025-01-01T09:00:00",
            end_time="2025-01-01T10:00:00",
        ),
    ]


def test_handle_success_returns_surgeries(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """
    @brief
    Validates normal success branch of LoadResultHandler.

    @details
    Ensures that when LoadResult indicates success=True, the handler returns
    the same list of Surgery instances, does not create any JSON error file,
    and logs informational message about SolverCore readiness.
    """
    # --- Arrange ---
    caplog.set_level(logging.INFO)
    result = LoadResult(
        success=True,
        surgeries=_fake_surgeries(),
        total_rows=2,
        kept_rows=2,
    )
    handler = LoadResultHandler(output_dir=tmp_path)

    # --- Act ---
    surgeries = handler.handle(result)

    # --- Assert ---
    assert surgeries is result.surgeries
    assert isinstance(surgeries[0], Surgery)
    assert not (tmp_path / "load_errors.json").exists()
    assert "ready for SolverCore" in caplog.text


def test_handle_failure_writes_json_and_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """
    @brief
    Verifies failure branch behavior — JSON report creation and None return.

    @details
    When LoadResult.success=False, handler must generate load_errors.json
    containing structured list of issues, return None, and log error summary.
    """
    # --- Arrange ---
    caplog.set_level(logging.ERROR)
    errors = [
        {"kind": "duplicate_id", "line_no": 5, "surgery_id": "S001", "message": "Duplicate"},
        {"kind": "invalid_datetime", "line_no": 8, "surgery_id": "S002", "message": "Bad time"},
    ]
    result = LoadResult(
        success=False,
        surgeries=[],
        errors=errors,
        total_rows=10,
        kept_rows=0,
    )
    handler = LoadResultHandler(output_dir=tmp_path)

    # --- Act ---
    output = handler.handle(result)

    # --- Assert ---
    assert output is None
    out_file = tmp_path / "load_errors.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["kind"] == "duplicate_id"
    assert len(data) == len(errors)
    assert "input validation failed" in caplog.text


def test_handle_failure_json_write_error(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """
    @brief
    Confirms robust error handling when JSON report writing fails.

    @details
    Simulates I/O failure (PermissionError) during JSON serialization.
    The handler must log the issue and continue safely without raising.
    """
    # --- Arrange ---
    caplog.set_level(logging.ERROR)
    result = LoadResult(
        success=False,
        surgeries=[],
        errors=[{"kind": "duplicate_id", "line_no": 1, "surgery_id": "S001", "message": "dup"}],
        total_rows=1,
        kept_rows=0,
    )

    def fail_open(*_, **__):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", fail_open)
    handler = LoadResultHandler(output_dir=tmp_path)

    # --- Act ---
    out = handler.handle(result)

    # --- Assert ---
    assert out is None
    assert "failed to write error report" in caplog.text.lower()
