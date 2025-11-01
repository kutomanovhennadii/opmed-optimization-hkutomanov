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
    """При success=True handler возвращает список операций и не создаёт JSON."""
    caplog.set_level(logging.INFO)
    result = LoadResult(
        success=True,
        surgeries=_fake_surgeries(),
        total_rows=2,
        kept_rows=2,
    )

    handler = LoadResultHandler(output_dir=tmp_path)
    surgeries = handler.handle(result)

    assert surgeries is result.surgeries
    assert isinstance(surgeries[0], Surgery)
    assert not (tmp_path / "load_errors.json").exists()
    assert "ready for SolverCore" in caplog.text


def test_handle_failure_writes_json_and_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """При success=False handler пишет JSON и возвращает None."""
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
    output = handler.handle(result)

    assert output is None
    out_file = tmp_path / "load_errors.json"
    assert out_file.exists(), "Файл отчёта должен быть создан"
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["kind"] == "duplicate_id"
    assert len(data) == len(errors)
    assert "input validation failed" in caplog.text


def test_handle_failure_json_write_error(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """Если не удалось записать JSON, handler логирует ошибку и продолжает безопасно."""
    caplog.set_level(logging.ERROR)
    result = LoadResult(
        success=False,
        surgeries=[],
        errors=[{"kind": "duplicate_id", "line_no": 1, "surgery_id": "S001", "message": "dup"}],
        total_rows=1,
        kept_rows=0,
    )

    # Симулируем отказ записи (PermissionError)
    def fail_open(*_, **__):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", fail_open)

    handler = LoadResultHandler(output_dir=tmp_path)
    out = handler.handle(result)

    assert out is None
    assert "failed to write error report" in caplog.text.lower()
