# tests/metrics/test_export_solution.py
from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opmed.errors import DataError
from opmed.export.solution_export import (
    _as_str,
    _parse_iso_tz_aware,
    _to_records,
    write_solution_csv,
)

# --- Helpers -----------------------------------------------------------------


def _read_csv(path: Path) -> list[dict[str, str]]:
    """
    @brief
    Reads a CSV file back into memory for structural verification.

    @details
    This helper is used in tests to re-read exported CSV files
    without relying on pandas. It ensures the column order and
    field names match the export specification exactly.

    @params
        path : Path
            Path to the CSV file to read.

    @returns
        List of dictionaries representing each CSV row.
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _iso(dt: datetime) -> str:
    """
    @brief
    Converts datetime to UTC ISO-8601 string with timezone.

    @details
    Ensures timestamps in tests are serialized exactly as the
    export routine expects — UTC-based and timezone-aware.
    """
    return dt.astimezone(timezone.utc).isoformat()


# --- Positive cases -----------------------------------------------------------


def test_write_solution_csv_happy_path_list(tmp_path: Path) -> None:
    """
    @brief
    Verifies successful export for a valid list of assignment records.

    @details
    Simulates two surgeries assigned to the same anesthetist in chronological
    order. Ensures CSV is created, header matches specification, and rows are
    sorted by anesthetist_id then start_time with ISO-8601 UTC timestamps.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"

    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=2)
    t2 = t1 + timedelta(minutes=30)
    t3 = t2 + timedelta(hours=1, minutes=30)

    assignments = [
        {
            "surgery_id": "S002",
            "start_time": _iso(t2),
            "end_time": _iso(t3),
            "anesthetist_id": "A1",
            "room_id": "R2",
        },
        {
            "surgery_id": "S001",
            "start_time": _iso(t0),
            "end_time": _iso(t1),
            "anesthetist_id": "A1",
            "room_id": "R1",
        },
    ]

    # --- Act ---
    out_path = write_solution_csv(assignments, out)

    # --- Assert ---
    # Verify output file was written successfully
    assert out_path == out
    assert out.exists()

    # Reload to verify column order and content
    rows = _read_csv(out)
    assert [c for c in rows[0].keys()] == [
        "surgery_id",
        "start_time",
        "end_time",
        "anesthetist_id",
        "room_id",
    ], "Header/columns order must match spec"

    # Sorted by anesthetist_id then start_time
    assert [r["surgery_id"] for r in rows] == ["S001", "S002"]

    # ISO strings must include timezone information
    assert rows[0]["start_time"].endswith("+00:00")
    assert rows[0]["end_time"].endswith("+00:00")


def test_write_solution_csv_accepts_generator(tmp_path: Path) -> None:
    """
    @brief
    Confirms that generator input is accepted and exported correctly.

    @details
    Verifies that write_solution_csv can handle generator-based
    assignment streams, producing identical CSV output as with lists.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"

    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    def gen():
        yield {
            "surgery_id": "S10",
            "start_time": _iso(t0),
            "end_time": _iso(t1),
            "anesthetist_id": "A0",
            "room_id": "R1",
        }

    # --- Act ---
    write_solution_csv(gen(), out)

    # --- Assert ---
    rows = _read_csv(out)
    assert len(rows) == 1
    assert rows[0]["surgery_id"] == "S10"


def test_write_solution_csv_creates_parent_directory(tmp_path: Path) -> None:
    """
    @brief
    Ensures output directories are created automatically.

    @details
    Validates that write_solution_csv creates all missing parent folders
    before writing the CSV, guaranteeing portability and atomic safety.
    """
    # --- Arrange ---
    nested = tmp_path / "data" / "output" / "solution.csv"
    t0 = datetime(2025, 11, 2, 9, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=2)
    data = [
        {
            "surgery_id": "S01",
            "start_time": _iso(t0),
            "end_time": _iso(t1),
            "anesthetist_id": "A5",
            "room_id": "R3",
        }
    ]

    # --- Act ---
    write_solution_csv(data, nested)

    # --- Assert ---
    assert nested.exists()
    rows = _read_csv(nested)
    assert len(rows) == 1


def test_write_solution_csv_empty_writes_header_only(tmp_path: Path) -> None:
    """
    @brief
    Verifies behavior for empty input — header-only CSV.

    @details
    An empty assignment list must still produce a valid CSV file
    with only the header row, preserving column structure.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"

    # --- Act ---
    write_solution_csv([], out)

    # --- Assert ---
    rows = _read_csv(out)
    assert rows == []  # zero data rows
    with out.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
    assert header_line == "surgery_id,start_time,end_time,anesthetist_id,room_id"


def test_write_solution_csv_accepts_Z_suffix_and_converts_to_utc(tmp_path: Path) -> None:
    """
    @brief
    Accepts ISO timestamps with 'Z' suffix and converts them to UTC.

    @details
    Confirms that ISO-8601 datetimes with 'Z' are recognized as UTC
    and serialized with '+00:00' suffix in the resulting CSV.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    data = [
        {
            "surgery_id": "S01",
            "start_time": "2025-11-02T08:00:00Z",
            "end_time": "2025-11-02T10:00:00Z",
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act ---
    write_solution_csv(data, out)

    # --- Assert ---
    rows = _read_csv(out)
    assert rows[0]["start_time"].endswith("+00:00")
    assert rows[0]["end_time"].endswith("+00:00")


def test_write_solution_csv_converts_non_utc_tz_to_utc(tmp_path: Path) -> None:
    """
    @brief
    Converts non-UTC timezone datetimes to UTC in output.

    @details
    Ensures timestamps with arbitrary timezones are normalized
    to UTC before being written to the final CSV file.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    data = [
        {
            "surgery_id": "S01",
            "start_time": "2025-11-02T10:00:00+02:00",
            "end_time": "2025-11-02T12:00:00+02:00",
            "anesthetist_id": "A1",
            "room_id": "R2",
        }
    ]

    # --- Act ---
    write_solution_csv(data, out)

    # --- Assert ---
    rows = _read_csv(out)
    assert rows[0]["start_time"].endswith("+00:00")
    assert rows[0]["end_time"].endswith("+00:00")


def test_write_solution_csv_pandas_read_csv_default_works(tmp_path: Path) -> None:
    """
    @brief
    Confirms pandas.read_csv works without additional parameters.

    @details
    Validates that the exported CSV is fully compatible with default
    pandas parsing (no parse_dates or custom encodings required),
    preserving column order and ISO-8601 string representation.
    """
    # --- Arrange ---
    import pandas as pd

    out = tmp_path / "solution.csv"
    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=2)
    data = [
        {
            "surgery_id": "S01",
            "start_time": _iso(t0),
            "end_time": _iso(t1),
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act ---
    write_solution_csv(data, out)
    df = pd.read_csv(out)  # default parser, no special options

    # --- Assert ---
    assert list(df.columns) == [
        "surgery_id",
        "start_time",
        "end_time",
        "anesthetist_id",
        "room_id",
    ]
    assert len(df) == 1
    assert isinstance(df["start_time"].iloc[0], str)


# --- Negative cases -----------------------------------------------------------


def test_write_solution_csv_missing_required_column(tmp_path: Path) -> None:
    """
    @brief
    Raises DataError when required column is missing.

    @details
    Validates that write_solution_csv detects incomplete records
    and reports which mandatory column is absent in the input data.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    bad = [
        {
            # "surgery_id": "S01",  # intentionally omitted
            "start_time": "2025-11-02T08:00:00+00:00",
            "end_time": "2025-11-02T10:00:00+00:00",
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        write_solution_csv(bad, out)
    assert "Missing required column" in str(ex.value)


def test_write_solution_csv_invalid_datetime_string(tmp_path: Path) -> None:
    """
    @brief
    Raises DataError for invalid ISO-8601 datetime strings.

    @details
    Ensures that malformed datetime inputs are rejected and
    a descriptive message is returned to the user.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    bad = [
        {
            "surgery_id": "S01",
            "start_time": "not-a-datetime",
            "end_time": "2025-11-02T10:00:00+00:00",
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        write_solution_csv(bad, out)
    assert "is not a valid ISO-8601 datetime" in str(ex.value)


def test_write_solution_csv_naive_datetime_raises(tmp_path: Path) -> None:
    """
    @brief
    Rejects naive datetime objects lacking timezone info.

    @details
    Confirms that datetime values without tzinfo trigger
    DataError, ensuring timezone-awareness for all timestamps.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    naive_start = datetime(2025, 11, 2, 8, 0)  # no tzinfo
    naive_end = datetime(2025, 11, 2, 10, 0)
    bad = [
        {
            "surgery_id": "S01",
            "start_time": naive_start,
            "end_time": naive_end,
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        write_solution_csv(bad, out)
    msg = str(ex.value)
    assert "must include timezone" in msg or "timezone-aware" in msg


def test_write_solution_csv_duplicate_surgery_id(tmp_path: Path) -> None:
    """
    @brief
    Detects duplicate surgery_id values and raises DataError.

    @details
    Prevents duplicate records from being exported. This check
    ensures each surgery is represented by exactly one row.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=2)
    data = [
        {
            "surgery_id": "S01",
            "start_time": _iso(t0),
            "end_time": _iso(t1),
            "anesthetist_id": "A1",
            "room_id": "R1",
        },
        {
            "surgery_id": "S01",  # duplicate
            "start_time": _iso(t0 + timedelta(hours=3)),
            "end_time": _iso(t1 + timedelta(hours=3)),
            "anesthetist_id": "A2",
            "room_id": "R2",
        },
    ]

    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        write_solution_csv(data, out)
    assert "Duplicate surgery_id detected" in str(ex.value)


def test_write_solution_csv_unsupported_input_type(tmp_path: Path) -> None:
    """
    @brief
    Raises DataError for unsupported input data types.

    @details
    Verifies that non-iterable or invalid assignment containers,
    such as dict objects, are explicitly rejected by the exporter.
    """
    # --- Arrange / Act / Assert ---
    out = tmp_path / "solution.csv"
    with pytest.raises(DataError) as ex:
        write_solution_csv({"not": "a list"}, out)  # type: ignore[arg-type]
    assert "Unsupported assignments type" in str(ex.value)


# --- exception --------------------------------------------------------------------


class DummyFD:
    """
    @brief
    Dummy file descriptor used to simulate I/O failure.

    @details
    Mimics os.fdopen() context manager that raises OSError when entering
    the context, allowing controlled testing of error-handling branches.
    """

    def __enter__(self):
        raise OSError("cannot open file")

    def __exit__(self, *args):
        return False


def test_write_solution_csv_handles_internal_io_exception(tmp_path: Path, monkeypatch) -> None:
    """
    @brief
    Ensures temporary files are removed when internal I/O fails.

    @details
    Mocks os.fdopen to raise OSError inside the try block of
    write_solution_csv. Confirms that the temporary file is removed
    and the exception propagates outward.
    """
    # --- Arrange ---
    out = tmp_path / "solution.csv"
    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0.replace(hour=10)

    data = [
        {
            "surgery_id": "S01",
            "start_time": t0.isoformat(),
            "end_time": t1.isoformat(),
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    removed = {}
    real_remove = os.remove

    def fake_remove(name: str):
        removed["called"] = name
        return real_remove(name) if Path(name).exists() else None

    monkeypatch.setattr(os, "fdopen", lambda *a, **kw: DummyFD())
    monkeypatch.setattr(os, "remove", fake_remove)

    # --- Act / Assert ---
    with pytest.raises(OSError):
        write_solution_csv(data, out)

    # Ensure cleanup was attempted and no output file created
    assert "called" in removed
    assert not out.exists()


def test_write_solution_csv_to_project_output() -> None:
    """
    @brief
    Live integration test writing directly into project output directory.

    @details
    Executes the full export pipeline using actual filesystem paths
    under data/output to confirm correct operation and permissions.
    """
    # --- Arrange ---
    base = Path(r"C:\Repository\opmed-optimization\data\output")
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / "solution_test.csv"

    t0 = datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=2)

    data = [
        {
            "surgery_id": "S001",
            "start_time": t0.isoformat(),
            "end_time": t1.isoformat(),
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    # --- Act ---
    result = write_solution_csv(data, out_path)

    # --- Assert ---
    print(f"CSV created at: {result}")


def test_to_records_iterable_with_non_mapping_elements_raises() -> None:
    """
    @brief
    Raises DataError when iterable elements are not mappings.

    @details
    Validates that _to_records enforces mapping type for every
    element of iterable input, ensuring data consistency.
    """
    # --- Arrange / Act / Assert ---
    data = [1, 2, 3]
    with pytest.raises(DataError) as ex:
        _to_records(data)
    msg = str(ex.value)
    assert "Each assignment must be a mapping" in msg
    assert "Provide assignments as list[dict]" in msg


@pytest.mark.parametrize(
    "bad_input",
    [
        {"a": 1},  # plain dict
        123,  # number
        None,  # NoneType
    ],
)
def test_to_records_unsupported_type_raises(bad_input) -> None:
    """
    @brief
    Raises DataError for unsupported input types.

    @details
    Tests various invalid inputs (dict, int, None) to ensure
    _to_records explicitly rejects them with proper diagnostic.
    """
    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        _to_records(bad_input)
    msg = str(ex.value)
    assert "Unsupported assignments type" in msg
    assert "Use list[dict] with required columns" in msg


def test_to_records_string_is_iterable_but_not_mapping() -> None:
    """
    @brief
    Rejects string input even though it is iterable.

    @details
    Confirms that _to_records distinguishes between true
    iterables of mappings and scalar iterables like strings,
    raising DataError accordingly.
    """
    # --- Act / Assert ---
    with pytest.raises(DataError) as ex:
        _to_records("string")
    msg = str(ex.value)
    assert "Each assignment must be a mapping" in msg


# -----_parse_iso_tz_aware------------------------------------------------------------


def test_parse_iso_tz_aware_raises_on_naive_datetime() -> None:
    """
    @brief
    Raises DataError for naive datetime without tzinfo.

    @details
    Validates that _parse_iso_tz_aware rejects datetime objects
    missing timezone information and reports the proper context.
    """
    # --- Arrange / Act / Assert ---
    naive = datetime(2025, 11, 2, 8, 0)
    with pytest.raises(DataError) as ex:
        _parse_iso_tz_aware(naive, "start_time")
    msg = str(ex.value)
    assert "must include timezone" in msg
    assert "export.write_solution_csv" in msg


def test_parse_iso_tz_aware_raises_on_invalid_string() -> None:
    """
    @brief
    Raises DataError for invalid ISO-8601 string.

    @details
    Ensures that malformed string inputs that cannot be parsed
    as ISO-8601 datetimes are rejected with clear diagnostics.
    """
    # --- Arrange / Act / Assert ---
    bad = "not-a-date"
    with pytest.raises(DataError) as ex:
        _parse_iso_tz_aware(bad, "start_time")
    msg = str(ex.value)
    assert "is not a valid ISO-8601 datetime" in msg
    assert "Use ISO-8601 with timezone" in msg


def test_parse_iso_tz_aware_raises_on_string_without_tz() -> None:
    """
    @brief
    Raises DataError for ISO string missing timezone.

    @details
    Confirms that timezone-less ISO strings are not accepted,
    enforcing full tz-awareness policy for all timestamp fields.
    """
    # --- Arrange / Act / Assert ---
    no_tz = "2025-11-02T08:00:00"
    with pytest.raises(DataError) as ex:
        _parse_iso_tz_aware(no_tz, "end_time")
    msg = str(ex.value)
    assert "must include timezone" in msg
    assert "Provide timezone-aware datetimes" in msg


def test_parse_iso_tz_aware_raises_on_unsupported_type() -> None:
    """
    @brief
    Raises DataError for unsupported non-string, non-datetime types.

    @details
    Verifies that arbitrary data types such as integers trigger
    an error message explaining valid input expectations.
    """
    # --- Arrange / Act / Assert ---
    with pytest.raises(DataError) as ex:
        _parse_iso_tz_aware(12345, "start_time")
    msg = str(ex.value)
    assert "must be datetime-like or ISO-8601 string" in msg
    assert "Pass datetime with timezone" in msg


def test_parse_iso_tz_aware_valid_Z_suffix_converts_to_utc() -> None:
    """
    @brief
    Accepts ISO string with 'Z' suffix and converts to UTC.

    @details
    Checks that 'Z' is correctly interpreted as UTC and the
    resulting datetime is timezone-aware and normalized.
    """
    # --- Act ---
    result = _parse_iso_tz_aware("2025-11-02T08:00:00Z", "start_time")

    # --- Assert ---
    assert isinstance(result, datetime)
    assert result.tzinfo == timezone.utc
    assert result.hour == 8


def test_parse_iso_tz_aware_datetime_with_tz_returns_utc() -> None:
    """
    @brief
    Converts timezone-aware datetime to UTC.

    @details
    Ensures that input datetimes with arbitrary tzinfo are normalized
    to UTC and returned as new objects, preserving equivalence.
    """
    # --- Arrange ---
    local = datetime(2025, 11, 2, 10, 0, tzinfo=timezone(timedelta(hours=2)))

    # --- Act ---
    result = _parse_iso_tz_aware(local, "start_time")

    # --- Assert ---
    assert isinstance(result, datetime)
    assert result.tzinfo == timezone.utc
    assert result.hour == 8
    assert result is not local


# --- _as_str ---------------------------------------------------------------------


class BadStr:
    """
    @brief
    Test class whose __str__ method always raises an exception.

    @details
    Used to simulate conversion failure during stringification,
    allowing validation of _as_str error handling behavior.
    """

    def __str__(self):
        raise RuntimeError("cannot convert to string")


def test_as_str_raises_dataerror_when_str_fails() -> None:
    """
    @brief
    Raises DataError when str(value) raises an exception.

    @details
    Ensures that _as_str correctly captures any exception thrown
    by __str__ and re-raises it as a DataError with a clear message
    including the affected field name and recovery suggestion.
    """
    # --- Arrange / Act / Assert ---
    bad_value = BadStr()
    with pytest.raises(DataError) as ex:
        _as_str(bad_value, "room_id")
    msg = str(ex.value)
    assert "must be convertible to string" in msg
    assert "export.write_solution_csv" in msg
    assert "Ensure room_id is a scalar value" in msg
