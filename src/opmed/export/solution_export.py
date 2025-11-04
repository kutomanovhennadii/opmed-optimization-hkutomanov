from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opmed.errors import DataError  # ADR-008: project-level errors

_REQUIRED_COLUMNS = ("surgery_id", "start_time", "end_time", "anesthetist_id", "room_id")


def _to_records(assignments: Any) -> list[Mapping[str, Any]]:
    """
    @brief
    Converts various input formats into a list of mapping objects.

    @details
    Accepts standard iterable sources like list[dict] or generators.
    Explicitly rejects plain dict to prevent accidental iteration
    over keys. Each row must represent a mapping with required columns.

    @params
        assignments : Any
            Input container of assignment records.

    @returns
        List of mappings with normalized structure.

    @raises
        DataError if input is unsupported or contains non-mapping items.
    """
    # (1) Direct passthrough for list[Mapping]
    if isinstance(assignments, list):
        if not assignments:
            return []
        if isinstance(assignments[0], Mapping):
            return assignments

    # (2) Reject plain dict (keys are iterable — unsafe)
    if isinstance(assignments, dict):
        raise DataError(
            "Unsupported assignments type.",
            source="export.write_solution_csv",
            suggested_action="Use list[dict] with required columns.",
        )

    # (3) Convert iterable of mappings into list
    if isinstance(assignments, Iterable):
        out: list[Mapping[str, Any]] = []
        for row in assignments:
            if not isinstance(row, Mapping):
                raise DataError(
                    "Each assignment must be a mapping with required columns.",
                    source="export.write_solution_csv",
                    suggested_action="Provide assignments as list[dict] with required columns.",
                )
            out.append(row)
        return out

    # (4) Reject anything else
    raise DataError(
        "Unsupported assignments type.",
        source="export.write_solution_csv",
        suggested_action="Use list[dict] with required columns.",
    )


def _ensure_columns(row: Mapping[str, Any]) -> None:
    """
    @brief
    Verifies that a row contains all required columns.

    @details
    Each export record must include every column defined in
    _REQUIRED_COLUMNS. Missing any of them triggers DataError.

    @params
        row : Mapping[str, Any]
            Single assignment row to validate.

    @raises
        DataError if required columns are missing.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in row]
    if missing:
        raise DataError(
            f"Missing required column(s): {', '.join(missing)}",
            source="export.write_solution_csv",
            suggested_action="Ensure assignments contain columns: surgery_id,start_time,end_time,anesthetist_id,room_id",
        )


def _parse_iso_tz_aware(value: Any, field_name: str) -> datetime:
    """
    @brief
    Parses a timezone-aware ISO-8601 datetime or validates an existing one.

    @details
    Accepts both datetime objects and strings. Naive datetimes
    (without tzinfo) are rejected. The 'Z' suffix is interpreted as UTC.
    Returns normalized UTC datetime.

    @params
        value : Any
            Input datetime or ISO-8601 string.
        field_name : str
            Name of the field (for error context).

    @returns
        datetime with UTC timezone.

    @raises
        DataError if value cannot be parsed or lacks timezone info.
    """
    # (1) Accept datetime instances with tzinfo
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DataError(
                f"{field_name} must include timezone (tz-aware).",
                source="export.write_solution_csv",
                suggested_action="Provide timezone-aware datetime (e.g., '+00:00').",
            )
        return value.astimezone(timezone.utc)

    # (2) Parse ISO-8601 string
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception as e:
            raise DataError(
                f"{field_name} is not a valid ISO-8601 datetime: {value!r}",
                source="export.write_solution_csv",
                suggested_action="Use ISO-8601 with timezone, e.g. '2025-01-01T08:00:00+00:00'.",
            ) from e
        if dt.tzinfo is None:
            raise DataError(
                f"{field_name} must include timezone (tz-aware).",
                source="export.write_solution_csv",
                suggested_action="Provide timezone-aware datetimes (e.g., '...+00:00').",
            )
        return dt.astimezone(timezone.utc)

    # (3) Reject invalid types
    raise DataError(
        f"{field_name} must be datetime-like or ISO-8601 string.",
        source="export.write_solution_csv",
        suggested_action="Pass datetime with timezone or ISO-8601 string with timezone.",
    )


def _as_str(value: Any, field_name: str) -> str:
    """
    @brief
    Converts a field value to string representation.

    @details
    Ensures that each exportable field can be safely converted
    to string for CSV serialization.

    @params
        value : Any
            Input field value.
        field_name : str
            Name of the field (for error reporting).

    @returns
        Stringified representation of value.

    @raises
        DataError if value cannot be converted to string.
    """
    try:
        return str(value)
    except Exception as e:
        raise DataError(
            f"{field_name} must be convertible to string.",
            source="export.write_solution_csv",
            suggested_action=f"Ensure {field_name} is a scalar value (e.g., 'A1', 'R2').",
        ) from e


def _validate_no_duplicate_surgery_ids(rows: Sequence[Mapping[str, Any]]) -> None:
    """
    @brief
    Ensures that each surgery_id is unique in the export dataset.

    @details
    Duplicate surgery_id values indicate corrupted or merged results
    and are disallowed. Validation is performed before sorting or writing.

    @params
        rows : Sequence[Mapping[str, Any]]
            Sequence of validated assignment mappings.

    @raises
        DataError if duplicate surgery_id is detected.
    """
    # (1) Build a uniqueness set and detect duplicates
    seen: set[str] = set()
    for r in rows:
        sid = str(r["surgery_id"])
        if sid in seen:
            raise DataError(
                f"Duplicate surgery_id detected: {sid}",
                source="export.write_solution_csv",
                suggested_action="Ensure unique surgery_id per row in export.",
            )
        seen.add(sid)


def write_solution_csv(assignments: Any, out_path: Path) -> Path:
    """
    @brief
    Exports assignment solution data into a structured CSV file.

    @details
    Writes records with required columns:
    surgery_id,start_time,end_time,anesthetist_id,room_id.
    The file is encoded in UTF-8 and readable by pandas.read_csv.
    Timestamps are normalized to UTC and serialized in ISO-8601 format.
    Output is atomically written to prevent corruption.

    @params
        assignments : Any
            Iterable or list of dict records.
        out_path : Path
            Destination CSV file path.

    @returns
        Path to the successfully written CSV file.

    @raises
        DataError for structural or typing issues.
    """
    # (1) Normalize input to a list of dict-like records
    records = _to_records(assignments)

    # (2) Validate record structure (allow empty input)
    for row in records:
        _ensure_columns(row)

    # (3) Check for duplicate surgery_id values
    _validate_no_duplicate_surgery_ids(records)

    # (4) Normalize field types and prepare for sorting
    normalized: list[dict[str, str]] = []
    for row in records:
        surgery_id = _as_str(row["surgery_id"], "surgery_id")
        anesth_id = _as_str(row["anesthetist_id"], "anesthetist_id")
        room_id = _as_str(row["room_id"], "room_id")
        start_dt = _parse_iso_tz_aware(row["start_time"], "start_time")
        end_dt = _parse_iso_tz_aware(row["end_time"], "end_time")

        normalized.append(
            {
                "surgery_id": surgery_id,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "anesthetist_id": anesth_id,
                "room_id": room_id,
            }
        )

    # (5) Sort rows by anesthetist_id and start_time
    # normalized.sort(key=lambda r: (r["anesthetist_id"], r["start_time"]))

    # (6) Ensure output directory exists
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # (7) Atomic write via temporary file replacement
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), suffix=".tmp", text=True)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_REQUIRED_COLUMNS)
            writer.writeheader()
            for row in normalized:
                writer.writerow(row)
        os.replace(tmp_name, out_path)
    except Exception:
        # (8) Cleanup temp file on any failure
        try:
            os.remove(tmp_name)
        except Exception:
            pass
        raise

    # (9) Return final output path
    return out_path
