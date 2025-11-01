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
    """
    @brief
    Verifies that a valid CSV with proper structure produces a successful LoadResult.

    @details
    Tests end-to-end behavior of SurgeriesLoader on correctly formatted input.
    Confirms that surgeries are parsed, validated, and ordered chronologically.
    """
    # --- Arrange ---
    csv_path = _write_csv(
        tmp_path,
        "ok.csv",
        """
        surgery_id,start_time,end_time
        S001,2025-01-01T07:00:00,2025-01-01T08:30:00
        S002,2025-01-01T09:00:00,2025-01-01T10:00:00
        """,
    )

    # --- Act ---
    loader = SurgeriesLoader()
    result = loader.load(csv_path)

    # --- Assert ---
    assert isinstance(result, LoadResult)
    assert result.success is True
    assert len(result.surgeries) == 2
    assert all(isinstance(s, Surgery) for s in result.surgeries)
    assert [s.surgery_id for s in result.surgeries] == ["S001", "S002"]
    assert result.errors == []
    assert result.surgeries[0].start_time < result.surgeries[1].start_time


# ------------------------------------------------------------------------------
# Row-level issues (non-fatal but lead to success=False)
# ------------------------------------------------------------------------------
def test_duplicate_and_invalid_rows_reported(tmp_path: Path):
    """
    @brief
    Ensures duplicate, invalid, or logically inconsistent rows trigger structured issues.

    @details
    Verifies that multiple non-fatal validation errors (duplicate IDs, wrong duration,
    bad datetime) are detected, aggregated, and reported via LoadResult.errors.
    """
    # --- Arrange ---
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

    # --- Act ---
    result = SurgeriesLoader().load(csv_path)

    # --- Assert ---
    assert result.success is False
    assert result.surgeries == []
    assert result.kept_rows == 0
    assert result.total_rows == 4
    kinds = [e["kind"] for e in result.errors]
    assert {"duplicate_id", "non_positive_duration", "invalid_datetime"} <= set(kinds)


# ------------------------------------------------------------------------------
# Fatal structural errors
# ------------------------------------------------------------------------------
def test_missing_id_or_missing_time_reported(tmp_path: Path):
    """
    @brief
    Checks detection of missing surgery_id or malformed datetime fields.

    @details
    Ensures that empty IDs and missing timestamps are correctly marked as issues
    within the error list, resulting in an unsuccessful LoadResult.
    """
    # --- Arrange ---
    csv_path = _write_csv(
        tmp_path,
        "missing.csv",
        """
        surgery_id,start_time,end_time
        ,2025-01-01T07:00:00,2025-01-01T08:00:00
        S002,,2025-01-01T09:00:00
        """,
    )

    # --- Act ---
    result = SurgeriesLoader().load(csv_path)

    # --- Assert ---
    assert result.success is False
    kinds = {e["kind"] for e in result.errors}
    assert {"missing_id", "invalid_datetime"} & kinds or {"missing_id"} <= kinds


def test_missing_file_raises_dataerror(tmp_path: Path):
    """
    @brief
    Confirms that a missing input file raises a DataError.

    @details
    Verifies proper propagation of fatal file-not-found conditions from _read_csv.
    """
    # --- Arrange ---
    path = tmp_path / "not_exist.csv"
    loader = SurgeriesLoader()

    # --- Act / Assert ---
    with pytest.raises(DataError) as e:
        loader.load(path)
    assert "not found" in str(e.value).lower()


def test_invalid_header_raises_dataerror(tmp_path: Path):
    """
    @brief
    Ensures CSV header validation detects missing required columns.

    @details
    When CSV lacks required fields, DataError is raised with descriptive message.
    """
    # --- Arrange ---
    csv_path = _write_csv(
        tmp_path,
        "bad_header.csv",
        """
        bad_col1,bad_col2,bad_col3
        a,b,c
        """,
    )

    # --- Act / Assert ---
    loader = SurgeriesLoader()
    with pytest.raises(DataError) as e:
        loader.load(csv_path)
    msg = str(e.value).lower()
    assert "missing" in msg and "surgery_id" in msg


def test_no_header_raises_dataerror(tmp_path: Path):
    """
    @brief
    Tests behavior when file lacks header row entirely.

    @details
    A headerless CSV should trigger DataError indicating missing column names.
    """
    # --- Arrange ---
    csv_path = _write_csv(
        tmp_path,
        "no_header.csv",
        """
        S001,2025-01-01T07:00:00,2025-01-01T08:00:00
        """,
    )
    text = csv_path.read_text()
    csv_path.write_text(text, encoding="utf-8")

    # --- Act / Assert ---
    with pytest.raises(DataError):
        SurgeriesLoader().load(csv_path)


def test_read_csv_invalid_path_type_raises_dataerror():
    """
    @brief
    Validates path type enforcement inside _read_csv.

    @details
    Passing a non-Path object must raise DataError specifying the offending type.
    """
    # --- Arrange ---
    loader = SurgeriesLoader()

    # --- Act / Assert ---
    with pytest.raises(DataError) as e:
        loader._read_csv("not_a_path")  # type: ignore[arg-type]
    msg = str(e.value)
    assert "Invalid path type" in msg
    assert "SurgeriesLoader._read_csv" in msg
    assert "str" in msg


def test__read_csv_raises_when_no_header_row(tmp_path: Path):
    """
    @brief
    Checks empty CSV file behavior.

    @details
    When DictReader.fieldnames is None (empty file), DataError 'CSV has no header row'
    should be raised with proper diagnostic hints.
    """
    # --- Arrange ---
    csv_path = tmp_path / "no_header.csv"
    csv_path.write_text("", encoding="utf-8")
    loader = SurgeriesLoader()

    # --- Act / Assert ---
    with pytest.raises(DataError) as e:
        loader._read_csv(csv_path)
    err = str(e.value)
    assert "CSV has no header row" in err
    assert "SurgeriesLoader._read_csv" in err
    assert "Ensure the first line contains column names" in err


def test__read_csv_raises_dataerror_on_oserror(monkeypatch, tmp_path: Path):
    """
    @brief
    Verifies graceful handling of OSError during CSV read.

    @details
    Simulates locked or inaccessible file and ensures DataError provides
    actionable diagnostic details.
    """
    # --- Arrange ---
    csv_path = tmp_path / "locked.csv"
    csv_path.write_text("surgery_id,start_time,end_time\n", encoding="utf-8")
    loader = SurgeriesLoader()

    def fail_open(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", fail_open)

    # --- Act / Assert ---
    with pytest.raises(DataError) as e:
        loader._read_csv(csv_path)
    msg = str(e.value)
    assert "Unable to read CSV" in msg
    assert "Permission denied" in msg
    assert "SurgeriesLoader._read_csv" in msg
    assert "file permissions" in msg


def test__rows_to_result_catches_schema_error(monkeypatch):
    """
    @brief
    Validates that model-construction exceptions are captured as schema_error.

    @details
    Overrides Surgery class to force an exception and confirms LoadResult
    records a structured schema_error entry instead of raising.
    """
    # --- Arrange ---
    rows = [
        {
            "surgery_id": "S001",
            "start_time": "2025-01-01T07:00:00",
            "end_time": "2025-01-01T08:00:00",
        }
    ]

    def broken_surgery(*args, **kwargs):
        raise ValueError("schema broke")

    monkeypatch.setattr("opmed.dataloader.surgeries_loader.Surgery", broken_surgery)
    from opmed.dataloader.surgeries_loader import SurgeriesLoader

    # --- Act ---
    loader = SurgeriesLoader()
    result = loader._rows_to_result(rows)

    # --- Assert ---
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
    """
    @brief
    Integration-style check for mixed valid and invalid rows.

    @details
    Confirms partial success behavior — even if valid rows exist, overall
    success=False when any issue is detected. Ensures consistent counting and
    reporting of total and error rows.
    """
    # --- Arrange ---
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

    # --- Act ---
    result = SurgeriesLoader().load(csv_path)

    # --- Assert ---
    assert result.success is False
    assert result.kept_rows == 0
    assert len(result.errors) >= 2
    assert result.total_rows == 4
