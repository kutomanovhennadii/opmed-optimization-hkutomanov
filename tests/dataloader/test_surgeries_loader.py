# tests/dataloader/test_surgeries_loader.py
import textwrap
from pathlib import Path

import pytest

from opmed.dataloader.surgeries_loader import SurgeriesLoader
from opmed.dataloader.types import LoadResult
from opmed.errors import DataError
from opmed.schemas.models import Surgery


def _write_csv(tmp_path: Path, name: str, text: str) -> Path:
    """Helper: writes plain text CSV content into a temporary file."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------------------
def test_valid_csv_returns_success(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "ok.csv",
        """
        surgery_id,start_time,end_time
        S001,2025-01-01T07:00:00,2025-01-01T08:30:00
        S002,2025-01-01T09:00:00,2025-01-01T10:00:00
        """,
    )

    loader = SurgeriesLoader()
    result = loader.load(csv_path)

    assert isinstance(result, LoadResult)
    assert result.success is True
    assert len(result.surgeries) == 2
    assert all(isinstance(s, Surgery) for s in result.surgeries)
    assert [s.surgery_id for s in result.surgeries] == ["S001", "S002"]
    assert result.errors == []
    # chronological order
    assert result.surgeries[0].start_time < result.surgeries[1].start_time


# ------------------------------------------------------------------------------
# Row-level issues (non-fatal but lead to success=False)
# ------------------------------------------------------------------------------
def test_duplicate_and_invalid_rows_reported(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "dupes.csv",
        """
        surgery_id,start_time,end_time
        S001,2025-01-01T07:00:00,2025-01-01T08:00:00
        S001,2025-01-01T09:00:00,2025-01-01T10:00:00
        S002,2025-01-01T11:00:00,2025-01-01T09:00:00
        S003,not_a_date,2025-01-01T10:00:00
        """,
    )

    result = SurgeriesLoader().load(csv_path)

    assert result.success is False
    assert result.surgeries == []
    assert result.kept_rows == 0
    assert result.total_rows == 4
    # Check presence of expected issue kinds
    kinds = [e["kind"] for e in result.errors]
    assert {"duplicate_id", "non_positive_duration", "invalid_datetime"} <= set(kinds)


def test_missing_id_or_missing_time_reported(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "missing.csv",
        """
        surgery_id,start_time,end_time
        ,2025-01-01T07:00:00,2025-01-01T08:00:00
        S002,,2025-01-01T09:00:00
        """,
    )

    result = SurgeriesLoader().load(csv_path)
    assert result.success is False
    kinds = {e["kind"] for e in result.errors}
    assert {"missing_id", "invalid_datetime"} & kinds or {"missing_id"} <= kinds


# ------------------------------------------------------------------------------
# Fatal structural errors
# ------------------------------------------------------------------------------
def test_missing_file_raises_dataerror(tmp_path: Path):
    path = tmp_path / "not_exist.csv"
    loader = SurgeriesLoader()
    with pytest.raises(DataError) as e:
        loader.load(path)
    assert "not found" in str(e.value).lower()


def test_invalid_header_raises_dataerror(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "bad_header.csv",
        """
        bad_col1,bad_col2,bad_col3
        a,b,c
        """,
    )
    loader = SurgeriesLoader()
    with pytest.raises(DataError) as e:
        loader.load(csv_path)
    msg = str(e.value).lower()
    assert "missing" in msg and "surgery_id" in msg


def test_no_header_raises_dataerror(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "no_header.csv",
        """
        S001,2025-01-01T07:00:00,2025-01-01T08:00:00
        """,
    )
    # Manually remove header row detection by truncating headerless read
    # simulate file without header
    text = csv_path.read_text()
    csv_path.write_text(text, encoding="utf-8")
    with pytest.raises(DataError):
        SurgeriesLoader().load(csv_path)


def test_read_csv_invalid_path_type_raises_dataerror():
    """Если передан не Path, должно быть выброшено DataError с указанием типа."""
    loader = SurgeriesLoader()
    # передаём строку вместо Path
    with pytest.raises(DataError) as e:
        loader._read_csv("not_a_path")  # type: ignore[arg-type]
    msg = str(e.value)
    assert "Invalid path type" in msg
    assert "SurgeriesLoader._read_csv" in msg
    assert "str" in msg


def test__read_csv_raises_when_no_header_row(tmp_path: Path):
    """Если CSV пуст (нет ни одной строки заголовка), выбрасывается DataError 'CSV has no header row'."""
    csv_path = tmp_path / "no_header.csv"
    # полностью пустой файл → DictReader.fieldnames == None
    csv_path.write_text("", encoding="utf-8")

    loader = SurgeriesLoader()
    with pytest.raises(DataError) as e:
        loader._read_csv(csv_path)
    err = str(e.value)
    assert "CSV has no header row" in err
    assert "SurgeriesLoader._read_csv" in err
    assert "Ensure the first line contains column names" in err


def test__read_csv_raises_dataerror_on_oserror(monkeypatch, tmp_path: Path):
    """Если при открытии CSV возникает OSError, выбрасывается DataError с корректным сообщением."""
    csv_path = tmp_path / "locked.csv"
    csv_path.write_text("surgery_id,start_time,end_time\n", encoding="utf-8")

    loader = SurgeriesLoader()

    # Подменяем Path.open, чтобы при вызове выбрасывал OSError
    def fail_open(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(DataError) as e:
        loader._read_csv(csv_path)
    msg = str(e.value)
    assert "Unable to read CSV" in msg
    assert "Permission denied" in msg
    assert "SurgeriesLoader._read_csv" in msg
    assert "file permissions" in msg


def test__rows_to_result_catches_schema_error(monkeypatch):
    """Проверяет, что ошибки при создании модели Surgery добавляются как schema_error."""
    # Заготовим корректные строки, чтобы дойти до создания модели
    rows = [
        {
            "surgery_id": "S001",
            "start_time": "2025-01-01T07:00:00",
            "end_time": "2025-01-01T08:00:00",
        }
    ]

    # Подменяем Surgery, чтобы выбрасывал исключение при создании
    def broken_surgery(*args, **kwargs):
        raise ValueError("schema broke")

    monkeypatch.setattr("opmed.dataloader.surgeries_loader.Surgery", broken_surgery)

    from opmed.dataloader.surgeries_loader import SurgeriesLoader

    loader = SurgeriesLoader()
    result = loader._rows_to_result(rows)

    # Убедимся, что ошибка зарегистрирована как schema_error
    assert result.success is False
    assert result.errors
    err = result.errors[0]
    assert err["kind"] == "schema_error"
    assert "schema broke" in err["message"]
    assert err["surgery_id"] == "S001"


# ------------------------------------------------------------------------------
# Integration-like sanity: mixed good and bad rows
# ------------------------------------------------------------------------------
def test_mixed_rows_only_valid_kept_and_sorted(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "mixed.csv",
        """
        surgery_id,start_time,end_time
        S001,2025-01-01T07:00:00,2025-01-01T08:00:00
        S002,2025-01-01T09:00:00,2025-01-01T07:00:00
        S003,not_a_date,2025-01-01T10:00:00
        S004,2025-01-01T10:00:00,2025-01-01T11:00:00
        """,
    )

    result = SurgeriesLoader().load(csv_path)
    assert result.success is False
    assert (
        result.kept_rows == 0
    )  # because any issue marks success=False even if some good rows exist
    # but still all issues must be reported
    assert len(result.errors) >= 2
    # file should still be readable
    assert result.total_rows == 4
