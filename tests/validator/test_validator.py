# tests/validator/test_validator.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from opmed.errors import ValidationError
from opmed.schemas.models import Config, SolutionRow, Surgery
from opmed.validator.validator import Validator, _ensure_timezone, validate_assignments


# -----------------------------
# HELPER FACTORIES
# -----------------------------
def dt(h: int, m: int = 0) -> datetime:
    """
    @brief
    Create a timezone-aware UTC datetime for test consistency.

    @details
    Returns a datetime on a fixed reference date (2025-01-01) in UTC.
    Simplifies creation of deterministic timestamps in test cases.

    @params
        h : int
            Hour component.
        m : int
            Minute component (default: 0).

    @returns
        UTC datetime object for 2025-01-01 at (h:m).
    """
    return datetime(2025, 1, 1, h, m, tzinfo=timezone.utc)


def mk_surgery(sid: str, start: datetime, end: datetime) -> Surgery:
    """
    @brief
    Factory function to construct a Surgery instance.

    @details
    Provides a minimal Surgery object for use in validation and
    overlap tests without requiring full input parsing.

    @params
        sid : str
            Surgery identifier.
        start : datetime
            Start time (timezone-aware).
        end : datetime
            End time (timezone-aware).

    @returns
        Surgery object with specified ID and timestamps.
    """
    return Surgery(surgery_id=sid, start_time=start, end_time=end)


def mk_assignment(sid: str, start: datetime, end: datetime, aid: str, room: str) -> SolutionRow:
    """
    @brief
    Factory function to construct a SolutionRow assignment.

    @details
    Creates a minimal assignment linking a surgery to an anesthetist
    and room, used for unit tests of Validator behavior.

    @params
        sid : str
            Surgery identifier.
        start : datetime
            Start timestamp (timezone-aware).
        end : datetime
            End timestamp (timezone-aware).
        aid : str
            Anesthetist identifier.
        room : str
            Room identifier.

    @returns
        SolutionRow object for test input.
    """
    return SolutionRow(
        surgery_id=sid,
        start_time=start,
        end_time=end,
        anesthetist_id=aid,
        room_id=room,
    )


def test_ensure_timezone_adds_utc_if_missing() -> None:
    """
    @brief
    Verify that naive datetimes are converted to UTC.

    @details
    Tests that _ensure_timezone() adds UTC tzinfo to naive
    datetime objects without altering clock time.
    """
    # --- Arrange ---
    naive = datetime(2025, 1, 1, 10, 30)  # without tzinfo

    # --- Act ---
    aware = _ensure_timezone(naive)

    # --- Assert ---
    # Should become timezone-aware
    assert aware.tzinfo is timezone.utc
    # Clock time must remain unchanged
    assert aware.hour == naive.hour and aware.minute == naive.minute


def test_ensure_timezone_returns_same_if_already_aware() -> None:
    """
    @brief
    Verify that _ensure_timezone() preserves aware datetimes.

    @details
    Confirms that an already UTC-aware datetime is returned
    unchanged by reference or value.
    """
    # --- Arrange ---
    original = datetime(2025, 1, 1, 10, 30, tzinfo=timezone.utc)

    # --- Act ---
    result = _ensure_timezone(original)

    # --- Assert ---
    # Must be identical or equal in value
    assert result is original or result == original
    assert result.tzinfo is timezone.utc


# -----------------------------
# V2 — RoomOverlap
# -----------------------------
def test_room_overlap_violation() -> None:
    """
    @brief
    Verify detection of overlapping surgeries within the same room (V2).

    @details
    Creates two surgeries assigned to the same room with overlapping time ranges.
    Validator is expected to flag a "RoomOverlap" error and mark the report as invalid.
    """
    # --- Arrange ---
    cfg = Config()  # default buffer=0.25, shift_min=5, shift_max=12
    s1 = mk_surgery("S1", dt(8, 0), dt(10, 0))
    s2 = mk_surgery("S2", dt(9, 30), dt(11, 0))
    surgeries = [s1, s2]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A2", "R1"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["RoomOverlap"] is False
    assert report["valid"] is False
    assert any(e["check"] == "RoomOverlap" for e in report["errors"])


# -----------------------------
# V1 — NoOverlap
# -----------------------------
def test_anesthetist_overlap_violation() -> None:
    """
    @brief
    Verify detection of overlapping surgeries for the same anesthetist (V1).

    @details
    Builds a case where a single anesthetist is assigned to two surgeries
    with overlapping time intervals in different rooms.
    Validator must detect a "NoOverlap" violation.
    """
    # --- Arrange ---
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(10, 0))
    s2 = mk_surgery("S2", dt(9, 30), dt(11, 0))
    surgeries = [s1, s2]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R2"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["NoOverlap"] is False
    assert report["valid"] is False
    assert any(e["check"] == "NoOverlap" for e in report["errors"])


# -----------------------------
# V3 — Buffer (interior)
# -----------------------------
def test_buffer_violation_between_rooms() -> None:
    """
    @brief
    Verify insufficient buffer detection when switching rooms (V3).

    @details
    Creates two consecutive surgeries for the same anesthetist in different rooms
    with a gap smaller than the required buffer (cfg.buffer). Validator must detect
    the violation and include detailed buffer gap information in the error entities.
    """
    # --- Arrange ---
    cfg = Config(buffer=0.25)  # 15 minutes buffer
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    s2 = mk_surgery("S2", dt(9, 5), dt(10, 0))  # gap ~ 5 min < 15 min buffer
    surgeries = [s1, s2]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R2"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["Buffer"] is False
    err = next(e for e in report["errors"] if e["check"] == "Buffer")
    assert err["entities"]["anesthetist_id"] == "A1"
    assert err["entities"]["required_hours"] == pytest.approx(0.25)


# -----------------------------
# V4 — ShiftLimits (longer than MAX)
# -----------------------------
def test_shift_limits_violation_too_long() -> None:
    """
    @brief
    Verify detection of shift duration exceeding upper bound (V4).

    @details
    Builds a scenario where a single anesthetist has two surgeries spaced
    far apart, resulting in a total shift length of 12.5 hours, exceeding
    the configured maximum (12.0h). Validator should flag a "ShiftLimits"
    violation.
    """
    # --- Arrange ---
    cfg = Config(shift_min=5.0, shift_max=12.0)
    s1 = mk_surgery("S1", dt(8, 0), dt(12, 0))
    s2 = mk_surgery("S2", dt(19, 0), dt(20, 30))
    surgeries = [s1, s2]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R2"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["ShiftLimits"] is False
    assert any(e["check"] == "ShiftLimits" for e in report["errors"])


# -----------------------------
# V6 — Duration Limits (on/off)
# -----------------------------
def test_surgery_duration_limit_disabled_and_enabled() -> None:
    """
    @brief
    Verify both branches of _check_surgery_duration_limit() (V6).

    @details
    (1) When enforcement is disabled, validation must pass unconditionally.
    (2) When enabled, long surgeries must be flagged as violations.
    """
    # --- (1) Enforcement disabled ---
    cfg = Config(enforce_surgery_duration_limit=False, shift_max=12.0)
    s = mk_surgery("S1", dt(8, 0), dt(22, 0))  # 14h, but limit disabled
    v = Validator([mk_assignment("S1", s.start_time, s.end_time, "A1", "R1")], [s], cfg)

    # --- Act ---
    v._check_surgery_duration_limit()

    # --- Assert ---
    assert v.checks["DurationLimits"] is True
    assert v.errors == []

    # --- (2) Enforcement enabled ---
    cfg2 = Config(enforce_surgery_duration_limit=True, shift_max=12.0)
    s2 = mk_surgery("S2", dt(8, 0), dt(22, 0))  # 14h, exceeds limit
    v2 = Validator([mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R1")], [s2], cfg2)

    # --- Act ---
    v2._check_surgery_duration_limit()

    # --- Assert ---
    assert v2.checks["DurationLimits"] is False
    assert any(
        e.get("check") == "DurationLimits"
        and e.get("entities", {}).get("surgery_id") == "S2"
        and abs(e.get("entities", {}).get("duration_hours", 0) - 14.0) < 0.1
        and abs(e.get("entities", {}).get("limit_hours", 0) - 12.0) < 0.1
        for e in v2.errors
    ), f"DurationLimits error not found, got: {v2.errors}"


# -----------------------------
# V6 — DurationLimits (operation > 12 hours)
# -----------------------------
def test_surgery_duration_limits_violation() -> None:
    """
    @brief
    Verify duration limit violation detection for long surgeries (V6).

    @details
    Tests that a surgery lasting longer than the allowed maximum (13h > 12h)
    triggers a DurationLimits validation failure.
    """
    # --- Arrange ---
    cfg = Config(shift_max=12.0, enforce_surgery_duration_limit=True)
    s1 = mk_surgery("S1", dt(8, 0), dt(21, 0))  # 13h surgery
    surgeries = [s1]
    assignments = [mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1")]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["DurationLimits"] is False
    assert any(e["check"] == "DurationLimits" for e in report["errors"])


# -----------------------------
# V5 — Utilization (warning, not an error)
# -----------------------------
def test_utilization_warning_but_valid() -> None:
    """
    @brief
    Verify that low utilization produces a warning but keeps report valid (V5).

    @details
    Creates short surgeries within long shifts to yield a low utilization ratio.
    All strict validation checks must pass, but utilization should trigger
    a warning rather than an error.
    """
    # --- Arrange ---
    cfg = Config(utilization_target=0.8, buffer=0.25, shift_min=5.0, shift_max=12.0)
    s1 = mk_surgery("S1", dt(8, 0), dt(8, 15))
    s2 = mk_surgery("S2", dt(12, 45), dt(13, 0))
    s3 = mk_surgery("S3", dt(8, 0), dt(8, 15))
    s4 = mk_surgery("S4", dt(12, 45), dt(13, 0))
    surgeries = [s1, s2, s3, s4]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R1"),
        mk_assignment("S3", s3.start_time, s3.end_time, "A2", "R2"),
        mk_assignment("S4", s4.start_time, s4.end_time, "A2", "R2"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["RoomOverlap"] is True
    assert report["checks"]["NoOverlap"] is True
    assert report["checks"]["Buffer"] is True
    assert report["checks"]["ShiftLimits"] is True
    assert report["checks"]["DurationLimits"] is True
    assert report["checks"]["Utilization"] is False
    assert any(w["check"] == "Utilization" for w in report["warnings"])
    assert report["valid"] is True


# -----------------------------
# V7 — DataIntegrity: Duplicate ID
# -----------------------------
def test_data_integrity_duplicate_id() -> None:
    """
    @brief
    Verify detection of duplicate surgery_id entries (V7).

    @details
    Provides two assignments with the same surgery_id to ensure
    the validator flags the duplication as a DataIntegrity violation.
    """
    # --- Arrange ---
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    surgeries = [s1]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S1", s1.start_time, s1.end_time, "A2", "R2"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["DataIntegrity"] is False
    assert any(
        e["check"] == "DataIntegrity" and "Duplicate surgery_id" in e["message"]
        for e in report["errors"]
    )
    assert report["valid"] is False


# -----------------------------
# V7 — DataIntegrity: Time Inconsistency
# -----------------------------
def test_data_integrity_assignment_time_mismatch() -> None:
    """
    @brief
    Verify detection of mismatched surgery start/end times (V7).

    @details
    Modifies assignment times to differ from input surgeries.
    Validator must detect the violation and log a DataIntegrity error.
    """
    # --- Arrange ---
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(10, 0))
    surgeries = [s1]
    assignments = [mk_assignment("S1", dt(8, 30), dt(9, 45), "A1", "R1")]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["DataIntegrity"] is False
    assert any(
        e["check"] == "DataIntegrity" and "must equal input surgery times" in e["message"]
        for e in report["errors"]
    )
    assert report["valid"] is False


# -----------------------------
# V7 — DataIntegrity: Invalid field types
# -----------------------------
def test_data_integrity_invalid_field_types(monkeypatch) -> None:
    """
    @brief
    Verify type validation of assignment fields (V7).

    @details
    Constructs a malformed assignment using SimpleNamespace to bypass
    schema validation. Ensures that incorrect types (e.g., int instead of str)
    are detected and reported as DataIntegrity violations.
    """
    # --- Arrange ---
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    surgeries = [s1]

    bad_assignment = SimpleNamespace(
        surgery_id="S1",
        start_time=s1.start_time,
        end_time=s1.end_time,
        anesthetist_id=123,  # invalid type
        room_id="R1",
    )

    # --- Act ---
    v = Validator(assignments=[bad_assignment], surgeries=surgeries, cfg=cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert ---
    assert report["checks"]["DataIntegrity"] is False
    err = next(e for e in report["errors"] if e["check"] == "DataIntegrity")
    assert "Invalid field types in assignment row" in err["message"]
    assert err["entities"]["surgery_id"] == "S1"
    assert report["valid"] is False


def test_data_integrity_invalid_datetime_fields() -> None:
    """
    @brief
    Verify that invalid datetime field types are detected (V7).

    @details
    Creates an assignment where start_time and end_time have incorrect
    types (string and None). Validator must flag a DataIntegrity error
    mentioning datetime type requirements.
    """
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    surgeries = [s1]

    # Forge an assignment with invalid start_time/end_time types
    bad_assignment = SimpleNamespace(
        surgery_id="S1",
        start_time="2025-01-01T08:00",  # invalid type (str)
        end_time=None,  # invalid type (None)
        anesthetist_id="A1",
        room_id="R1",
    )

    v = Validator(assignments=[bad_assignment], surgeries=surgeries, cfg=cfg)
    v.run_all_checks()
    report = v.build_report()

    # Verify that datetime type error is recorded
    assert report["checks"]["DataIntegrity"] is False
    err = next(
        e for e in report["errors"] if e["check"] == "DataIntegrity" and "datetime" in e["message"]
    )
    assert "start_time/end_time must be datetime with timezone" in err["message"]
    assert err["entities"]["surgery_id"] == "S1"
    assert report["valid"] is False


def test_data_integrity_extra_ids_not_in_input() -> None:
    """
    @brief
    Verify detection of extra surgery IDs not present in input (V7).

    @details
    Adds an assignment with a surgery ID (S2) missing from input surgeries.
    Validator must report a DataIntegrity error describing the unknown IDs.
    """
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    surgeries = [s1]

    # Add an extra surgery (S2) not present in input
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", dt(9, 0), dt(10, 0), "A2", "R2"),  # extra surgery
    ]

    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # Verify that DataIntegrity check catches unknown IDs
    assert report["checks"]["DataIntegrity"] is False
    err = next(
        e
        for e in report["errors"]
        if e["check"] == "DataIntegrity" and "Unknown surgeries" in e["message"]
    )
    assert err["entities"]["extra_count"] == 1
    assert "S2" in err["message"]
    assert report["valid"] is False


def test_anesthetist_overlaps_detects_conflict_direct_call() -> None:
    """
    @brief
    Verify that _check_anesthetist_overlaps() detects anesthetist conflicts.

    @details
    Calls the overlap checker directly with overlapping surgeries
    assigned to the same anesthetist. The method should record a
    NoOverlap violation referencing that anesthetist.
    """
    cfg = Config()
    s1 = mk_surgery("S1", dt(8, 0), dt(10, 0))
    s2 = mk_surgery("S2", dt(9, 30), dt(11, 0))
    surgeries = [s1, s2]

    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R2"),
    ]

    v = Validator(assignments, surgeries, cfg)
    v._check_anesthetist_overlaps()

    assert v.checks["NoOverlap"] is False
    assert any("A1" in err["message"] or "Anesthetist" in err["message"] for err in v.errors)


# -----------------------------
# ValidationError on critically malformed input
# -----------------------------
def test_raises_validation_error_on_empty_assignments() -> None:
    """
    @brief
    Verify that Validator raises ValidationError on empty assignments.

    @details
    Creates a configuration with valid surgeries but no assignments.
    The _check_data_integrity() method should raise ValidationError
    due to absence of matching assignment entries.
    """
    cfg = Config()
    surgeries = [mk_surgery("S1", dt(8, 0), dt(9, 0))]
    assignments: list[SolutionRow] = []

    with pytest.raises(ValidationError):
        v = Validator(assignments, surgeries, cfg)
        v.run_all_checks()  # _check_data_integrity should raise an exception


# -----------------------------
# Smoke test for a valid scenario
# -----------------------------
def test_smoke_valid_and_report_file_written(tmp_path: Path) -> None:
    """
    @brief
    End-to-end smoke test for a valid scheduling scenario.

    @details
    Builds a consistent set of surgeries and assignments with all
    constraints satisfied. Ensures that the validator marks the result
    as valid, writes the report to disk, and produces a properly
    timestamped JSON file.
    """
    cfg = Config(utilization_target=0.8, buffer=0.25, shift_min=5.0, shift_max=12.0)

    # One anesthetist, 5-hour shift, total surgery duration ~4.5h → utilization ~0.9
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 30))  # 1.5h
    s2 = mk_surgery("S2", dt(9, 45), dt(11, 45))  # 2.0h
    s3 = mk_surgery("S3", dt(12, 0), dt(13, 0))  # 1.0h
    surgeries = [s1, s2, s3]
    assignments = [
        mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1"),
        mk_assignment("S2", s2.start_time, s2.end_time, "A1", "R1"),
        mk_assignment("S3", s3.start_time, s3.end_time, "A1", "R1"),
    ]

    # --- Act ---
    v = Validator(assignments, surgeries, cfg)
    v.run_all_checks()
    report = v.build_report()

    # --- Assert (in-memory validation) ---
    assert report["valid"] is True
    assert all(
        report["checks"][k]
        for k in [
            "DataIntegrity",
            "RoomOverlap",
            "NoOverlap",
            "Buffer",
            "ShiftLimits",
            "DurationLimits",
        ]
    )

    # --- Act (write report to disk) ---
    path = v.save_report(report, out_dir=tmp_path)

    # --- Assert (file existence and validity) ---
    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("validation_report_")
    assert path.name.endswith(".json")

    # File must be valid JSON
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["valid"] is True

    # Verify timestamp pattern in filename (YYYYMMDD_HHMMSS)
    m = re.match(r"validation_report_\d{8}_\d{6}\.json", path.name)
    assert m is not None


# -----------------------------
# Facade validate_assignments: write enabled
# -----------------------------
def test_facade_validate_assignments_writes_file(tmp_path: Path) -> None:
    """
    @brief
    Verify facade validate_assignments() writes JSON report when enabled.

    @details
    Runs the top-level helper with write_report=True and ensures that
    a timestamped validation_report_*.json file is created and marked valid.
    """
    # --- Arrange ---
    cfg = Config(shift_min=1.0)  # minimal shift to make one surgery valid
    s1 = mk_surgery("S1", dt(8, 0), dt(9, 0))
    surgeries = [s1]
    assignments = [mk_assignment("S1", s1.start_time, s1.end_time, "A1", "R1")]

    # --- Act ---
    report = validate_assignments(assignments, surgeries, cfg, write_report=True, out_dir=tmp_path)

    # --- Assert ---
    assert report["valid"] is True

    files = list(tmp_path.glob("validation_report_*.json"))
    assert len(files) == 1
    assert files[0].exists()
