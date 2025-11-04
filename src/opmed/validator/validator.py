# src/opmed/validator/validator.py
from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Unified error system (ADR-008)
# The project is expected to contain src/opmed/errors.py with class ValidationError
from opmed.errors import ValidationError

# Canonical data models (docs/schemas + models.py)
from opmed.schemas.models import Config, SolutionRow, Surgery

logger = logging.getLogger(__name__)


# ----------------------------
# AUXILIARY STRUCTURES / FUNCTIONS
# ----------------------------
@dataclass(frozen=True)
class Interval:
    """
    @brief
    Lightweight container representing a single time interval.

    @details
    Holds start and end timestamps together with the surgery identifier
    and optional contextual metadata (e.g., room_id, anesthetist_id).
    Used for local validation and overlap detection within the model builder.
    """

    start: datetime
    end: datetime
    surgery_id: str
    extra: dict[str, Any]  # e.g., {"room_id": "..."} or {"anesthetist_id": "..."}


def _ensure_timezone(dt: datetime) -> datetime:
    """
    @brief
    Ensure datetime object is timezone-aware.

    @details
    Guards against naive datetime instances by assigning UTC timezone.
    Although all datetimes are expected to be aware by contract,
    this function provides an extra safety layer.

    @params
        dt : datetime
            Input datetime instance.

    @returns
        A timezone-aware datetime object (converted to UTC if naive).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _hours(delta: timedelta) -> float:
    """
    @brief
    Convert timedelta to fractional hours.

    @details
    Computes total duration in hours as a floating-point value,
    used in workload and shift-length calculations.

    @params
        delta : timedelta
            Duration interval.

    @returns
        Equivalent duration in hours.
    """
    return delta.total_seconds() / 3600.0


def _sorted_intervals(rows: Iterable[SolutionRow], extra: dict[str, Any]) -> list[Interval]:
    """
    @brief
    Build and sort a list of Interval objects.

    @details
    Constructs Interval instances from raw solution rows and sorts them
    by start time. Ensures all timestamps are timezone-aware to maintain
    temporal consistency during validation.

    @params
        rows : Iterable[SolutionRow]
            Source rows containing start and end timestamps.
        extra : dict[str, Any]
            Context metadata propagated into each Interval.

    @returns
        List of Interval objects sorted by start time.
    """
    # (1) Collect validated time intervals
    intervals: list[Interval] = []
    for row in rows:
        start = _ensure_timezone(row.start_time)
        end = _ensure_timezone(row.end_time)
        intervals.append(Interval(start=start, end=end, surgery_id=row.surgery_id, extra=extra))

    # (2) Sort intervals chronologically by start timestamp
    intervals.sort(key=lambda it: it.start)
    return intervals


# ---------------------------
# VALIDATOR CLASS (instance core)
# ----------------------------
class Validator:
    """
    @brief
    Post-solution schedule validator.

    @details
    Performs structural and logical validation of the produced schedule.
    Includes integrity verification, overlap detection (rooms and anesthetists),
    inter-room buffer enforcement, shift boundary compliance, surgery duration
    limits, and computation of utilization metrics.

    Raises ValidationError only for corrupted input structures.
    Business-rule violations are collected into the validation report.
    The main lifecycle method always returns a structured report instead of
    raising errors.
    """

    # ---------- Constructor ----------
    def __init__(
        self, assignments: list[SolutionRow], surgeries: list[Surgery], cfg: Config
    ) -> None:
        """
        @brief
        Initialize validation context.

        @details
        Prepares internal state for validation by storing assignments, surgeries,
        and configuration. Builds quick-access dictionaries and initializes
        accumulators for errors, warnings, and metrics.

        @params
            assignments : list[SolutionRow]
                The final assignment records produced by the solver.
            surgeries : list[Surgery]
                Static surgery definitions with expected times and attributes.
            cfg : Config
                Runtime configuration governing validation parameters.
        """
        self.assignments = assignments
        self.surgeries = surgeries
        self.cfg = cfg

        # (1) Build lookup dictionary for fast access by surgery_id
        self.surgery_by_id: dict[str, Surgery] = {s.surgery_id: s for s in surgeries}

        # (2) Initialize accumulators for validation outcomes
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.checks: dict[str, bool] = {}
        self.metrics: dict[str, Any] = {}

    # ---------- Public lifecycle API ----------
    def run_all_checks(self) -> None:
        """
        @brief
        Execute the full validation sequence.

        @details
        Runs all validation routines in priority order.
        Integrity checks always run first to prevent cascading failures.
        If data integrity fails, subsequent logical checks are skipped and
        marked as unavailable in the final report.
        """
        # (1) Validate basic data integrity before other checks
        self._check_data_integrity()  # V7

        # (2) Skip further checks if integrity fails
        if not self.checks.get("DataIntegrity", True):
            self.checks.update(
                {
                    "RoomOverlap": False,
                    "NoOverlap": False,
                    "Buffer": False,
                    "ShiftLimits": False,
                    "DurationLimits": False,
                    "Utilization": False,
                }
            )
            return

        # (3) Execute logical validation passes in deterministic order
        self._check_room_overlaps()  # V2
        self._check_no_overlap()  # V1
        self._check_buffer_between_rooms()  # V3
        self._check_shift_limits()  # V4
        self._check_surgery_duration_limit()  # V6
        self._compute_metrics_and_utilization()  # V5

    def build_report(self) -> dict[str, Any]:
        """
        @brief
        Assemble validation results into a structured dictionary.

        @details
        Combines validation outcomes, collected messages, and computed metrics
        into a serializable structure. The report is used both for output and
        downstream analysis. No files are written at this stage.

        @returns
            A complete ValidationReport represented as a dictionary.
        """
        # (1) Define mandatory checks contributing to overall validity
        # mandatory = [
        #     "NoOverlap",
        #     "RoomOverlap",
        #     "Buffer",
        #     "ShiftLimits",
        #     "DurationLimits",
        #     "DataIntegrity",
        # ]

        # (2) Compute global validity flag
        # Treat certain checks as "soft" (do not invalidate the solution)
        critical_checks = ["DataIntegrity", "RoomOverlap", "NoOverlap", "DurationLimits"]
        # soft_checks = ["Buffer", "ShiftLimits", "Utilization"]

        critical_ok = all(self.checks.get(name, True) for name in critical_checks)
        has_fatal_error = any(e["check"] in critical_checks for e in self.errors)

        # Solution is valid if all critical checks passed and no fatal errors found.
        # Soft rule violations are tolerated (reported as errors but not invalidating).
        is_valid = critical_ok and not has_fatal_error

        # (3) Construct report dictionary
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "valid": bool(is_valid),
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
            "checks": self.checks,
        }

    def save_report(
        self,
        report: dict[str, Any],
        out_dir: Path | None = None,
        filename: str = "validation_report.json",
    ) -> Path:
        """
        Writes the report atomically to disk.

        Args:
            report: Validation report dictionary.
            out_dir: Target directory (defaults to 'data/output').
            filename: Target filename (default 'validation_report.json').

        Returns:
            Path to the written JSON file.
        """
        target_dir = out_dir or Path("data/output")
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / filename

        tmp_path = final_path.with_suffix(".tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            tmp_path.replace(final_path)
        except Exception as e:
            raise ValidationError(
                f"Failed to write validation report: {e}",
                source="Validator.save_report",
                suggested_action="Check disk permissions and free space.",
            )

        logger.info("Validation report saved: %s", final_path)
        return final_path

    # ---------- Checks (SRP: each check in a separate method) ----------
    def _check_data_integrity(self) -> None:
        """
        @brief
        Validate structural and semantic integrity of assignment data (V7).

        @details
        Ensures that all input assignments are well-typed, uniquely identified,
        consistent with surgery inputs, and contain unmodified start/end times.
        This check guards against malformed data before deeper logical validation.

        @raises
            ValidationError: Raised if assignments are empty or IDs do not match
            known surgeries.
        """
        ok = True
        seen_ids: set[str] = set()
        invalid_time_ids: set[str] = set()

        # (1) Validate field types and datetime formats
        for row in self.assignments:
            if (
                not isinstance(row.surgery_id, str)
                or not isinstance(row.anesthetist_id, str)
                or not isinstance(row.room_id, str)
            ):
                ok = False
                self._add_error(
                    check="DataIntegrity",
                    message="Invalid field types in assignment row",
                    entities={"surgery_id": getattr(row, "surgery_id", None)},
                    suggested_action="Ensure surgery_id, anesthetist_id, room_id are strings",
                )

            if not isinstance(row.start_time, datetime) or not isinstance(row.end_time, datetime):
                ok = False
                self._add_error(
                    check="DataIntegrity",
                    message="start_time/end_time must be datetime with timezone",
                    entities={"surgery_id": getattr(row, "surgery_id", None)},
                    suggested_action="Provide ISO-8601 datetimes with timezone (UTC by default)",
                )
                # (1.1) Mark invalid timestamps to skip in later comparison
                sid = getattr(row, "surgery_id", None)
                if isinstance(sid, str):
                    invalid_time_ids.add(sid)
                continue

        # (2) Detect duplicate surgery identifiers
        for row in self.assignments:
            if row.surgery_id in seen_ids:
                ok = False
                self._add_error(
                    check="DataIntegrity",
                    message=f"Duplicate surgery_id in assignments: {row.surgery_id}",
                    entities={"surgery_id": row.surgery_id},
                    suggested_action="Each input surgery must be assigned exactly once",
                )
            seen_ids.add(row.surgery_id)

        # (3) Compare ID sets between input and solution
        input_ids = set(self.surgery_by_id.keys())
        assigned_ids = set(a.surgery_id for a in self.assignments)

        missing_ids = sorted(list(input_ids - assigned_ids))
        extra_ids = sorted(list(assigned_ids - input_ids))

        # (4) Report missing IDs (surgery not assigned)
        if missing_ids:
            ok = False
            self._add_error(
                check="DataIntegrity",
                message=f"Missing surgeries in assignments: {missing_ids[:5]}{'...' if len(missing_ids) > 5 else ''}",
                entities={"missing_count": len(missing_ids)},
                suggested_action="Every input surgery must appear in the solution",
            )

        # (5) Report extra IDs (unknown surgery references)
        if extra_ids:
            ok = False
            self._add_error(
                check="DataIntegrity",
                message=f"Unknown surgeries in assignments: {extra_ids[:5]}{'...' if len(extra_ids) > 5 else ''}",
                entities={"extra_count": len(extra_ids)},
                suggested_action="Remove unknown IDs; they must match surgeries.csv",
            )

        # (6) Verify fixed surgery times
        for row in self.assignments:
            # Skip invalid or previously flagged rows
            sid = getattr(row, "surgery_id", None)
            if sid in invalid_time_ids:
                continue

            src = self.surgery_by_id.get(row.surgery_id)
            if src is None:
                continue  # already flagged as extra ID

            a_start = _ensure_timezone(row.start_time)
            a_end = _ensure_timezone(row.end_time)
            s_start = _ensure_timezone(src.start_time)
            s_end = _ensure_timezone(src.end_time)

            if a_start != s_start or a_end != s_end:
                ok = False
                self._add_error(
                    check="DataIntegrity",
                    message=(
                        f"Assignment times must equal input surgery times for {row.surgery_id} "
                        f"(got {a_start.isoformat()}–{a_end.isoformat()}, "
                        f"expected {s_start.isoformat()}–{s_end.isoformat()})"
                    ),
                    entities={"surgery_id": row.surgery_id},
                    suggested_action="Do not change surgery start/end in solution",
                )

        self.checks["DataIntegrity"] = ok

        # (7) Critical integrity failure — abort validation pipeline
        if (
            len(self.assignments) == 0
            or len(assigned_ids) == 0
            or len(assigned_ids & input_ids) == 0
        ):
            raise ValidationError(
                message="Malformed inputs for validator: empty or non-matching assignments",
                source="validator._check_data_integrity",
                suggested_action="Verify solution.csv contains known surgery_ids",
            )

    def _check_no_overlap(self) -> None:
        """
        @brief
        Validate non-overlapping schedule per anesthetist (V1).

        @details
        Ensures that each anesthetist is assigned to surgeries with
        non-overlapping time intervals. Surgeries are grouped by
        anesthetist_id and checked chronologically.
        Violations are logged in the validation report but do not
        raise exceptions.
        """
        ok = True

        # (1) Group surgeries by anesthetist
        grouped: dict[str, list[Any]] = {}
        for row in self.assignments:
            grouped.setdefault(row.anesthetist_id, []).append(row)

        # (2) Detect intra-group overlaps
        for anesth_id, rows in grouped.items():
            rows_sorted = sorted(rows, key=lambda r: _ensure_timezone(r.start_time))
            for i in range(len(rows_sorted) - 1):
                end_i = _ensure_timezone(rows_sorted[i].end_time)
                start_next = _ensure_timezone(rows_sorted[i + 1].start_time)

                # (2.1) If the next surgery starts before the previous ends, mark overlap
                if start_next < end_i:
                    ok = False
                    self._add_error(
                        check="NoOverlap",
                        message=(
                            f"Anesthetist {anesth_id} has overlapping surgeries "
                            f"({rows_sorted[i].surgery_id}, {rows_sorted[i + 1].surgery_id})"
                        ),
                        entities={
                            "anesthetist_id": anesth_id,
                            "surgery_ids": [
                                rows_sorted[i].surgery_id,
                                rows_sorted[i + 1].surgery_id,
                            ],
                        },
                        suggested_action="Reassign surgeries to avoid overlap for same anesthetist",
                    )

        self.checks["NoOverlap"] = ok

    def _check_room_overlaps(self) -> None:
        """
        @brief
        Validate non-overlapping surgeries within the same room (V2).

        @details
        Ensures that surgeries assigned to a single room do not overlap in time.
        Builds chronological intervals per room and checks adjacency boundaries.
        Overlaps indicate scheduling conflicts that violate room exclusivity.
        """
        ok = True

        # (1) Group surgeries by operating room
        rows_by_room = defaultdict(list)
        for row in self.assignments:
            rows_by_room[row.room_id].append(row)

        # (2) Sort intervals within each room and check temporal conflicts
        for room_id, rows in rows_by_room.items():
            intervals = _sorted_intervals(rows, {"room_id": room_id})
            for prev, cur in zip(intervals, intervals[1:]):
                if cur.start < prev.end:
                    ok = False
                    self._add_error(
                        check="RoomOverlap",
                        message="Two surgeries overlap in the same room",
                        entities={
                            "room_id": room_id,
                            "surgery_ids": [prev.surgery_id, cur.surgery_id],
                        },
                        suggested_action="Move one surgery to a different time or room",
                    )

        self.checks["RoomOverlap"] = ok

    def _check_anesthetist_overlaps(self) -> None:
        """
        @brief
        Validate non-overlapping surgeries per anesthetist (V1).

        @details
        Ensures that each anesthetist is assigned only to one active surgery at a time.
        Groups surgeries by anesthetist and checks for temporal overlap.
        Equivalent to logical constraint: no simultaneous assignments per anesthetist.
        """
        ok = True

        # (1) Group surgeries by anesthetist
        rows_by_anesthetist = defaultdict(list)
        for row in self.assignments:
            rows_by_anesthetist[row.anesthetist_id].append(row)

        # (2) Check sequential intervals for overlap
        for anesthetist_id, rows in rows_by_anesthetist.items():
            intervals = _sorted_intervals(rows, {"anesthetist_id": anesthetist_id})
            for prev, cur in zip(intervals, intervals[1:]):
                if cur.start < prev.end:
                    ok = False
                    self._add_error(
                        check="NoOverlap",
                        message="Anesthetist has overlapping surgeries",
                        entities={
                            "anesthetist_id": anesthetist_id,
                            "surgery_ids": [prev.surgery_id, cur.surgery_id],
                        },
                        suggested_action="Reassign surgeries to avoid overlap for the same anesthetist",
                    )

        self.checks["NoOverlap"] = ok

    def _check_buffer_between_rooms(self) -> None:
        """
        @brief
        Enforce minimum buffer time between room switches (V3).

        @details
        Verifies that when an anesthetist changes rooms between consecutive surgeries,
        the time gap between surgeries is at least the configured buffer (in hours).
        The rule enforces transition and setup time constraints between rooms.
        """
        ok = True
        buffer_required_h = float(self.cfg.buffer)

        # (1) Group surgeries by anesthetist
        rows_by_anesthetist = defaultdict(list)
        for row in self.assignments:
            rows_by_anesthetist[row.anesthetist_id].append(row)

        # (2) Check consecutive surgeries per anesthetist for room-switch gaps
        for anesthetist_id, rows in rows_by_anesthetist.items():
            rows_sorted = sorted(rows, key=lambda r: _ensure_timezone(r.start_time))
            for prev, cur in zip(rows_sorted, rows_sorted[1:]):
                # (2.1) Only evaluate when switching rooms
                if prev.room_id != cur.room_id:
                    prev_end = _ensure_timezone(prev.end_time)
                    cur_start = _ensure_timezone(cur.start_time)
                    gap_h = _hours(cur_start - prev_end)

                    # (2.2) Record insufficient buffer as violation
                    if gap_h < buffer_required_h:
                        ok = False
                        self._add_error(
                            check="Buffer",
                            message="Insufficient buffer when switching rooms",
                            entities={
                                "anesthetist_id": anesthetist_id,
                                "surgery_ids": [prev.surgery_id, cur.surgery_id],
                                "gap_hours": round(gap_h, 3),
                                "required_hours": buffer_required_h,
                            },
                            suggested_action="Increase the gap or keep consecutive surgeries in the same room",
                        )

        self.checks["Buffer"] = ok

    def _check_shift_limits(self) -> None:
        """
        @brief
        Validate anesthetist shift duration boundaries (V4).

        @details
        Ensures that each anesthetist’s total shift length is within
        [SHIFT_MIN, SHIFT_MAX] hours as defined in configuration.
        Detects underfilled or overlong shifts that violate operational constraints.
        """
        ok = True
        shift_min_h = float(self.cfg.shift_min)
        shift_max_h = float(self.cfg.shift_max)

        # (1) Group assignments per anesthetist
        rows_by_anesthetist = defaultdict(list)
        for row in self.assignments:
            rows_by_anesthetist[row.anesthetist_id].append(row)

        # (2) Compute and verify total shift length
        for anesthetist_id, rows in rows_by_anesthetist.items():
            starts = [_ensure_timezone(r.start_time) for r in rows]
            ends = [_ensure_timezone(r.end_time) for r in rows]
            shift_start = min(starts)
            shift_end = max(ends)
            shift_hours = _hours(shift_end - shift_start)

            # (2.1) Flag shifts that fall outside allowed range
            if shift_hours > shift_max_h:
                ok = False
                self._add_error(
                    check="ShiftLimits",
                    message="Shift duration exceeds maximum limit",
                    entities={
                        "anesthetist_id": anesthetist_id,
                        "duration_hours": round(shift_hours, 3),
                        "limit": shift_max_h,
                    },
                    suggested_action="Reassign or split to keep shifts ≤ SHIFT_MAX",
                )
            elif shift_hours < shift_min_h:
                # Shorter than minimum — legal, but issue a warning
                self._add_warning(
                    check="ShiftLimits",
                    message="Shift shorter than minimum (paid as 5h per spec)",
                    entities={
                        "anesthetist_id": anesthetist_id,
                        "duration_hours": round(shift_hours, 3),
                        "min_pay_hours": shift_min_h,
                    },
                )

        self.checks["ShiftLimits"] = ok

    def _check_surgery_duration_limit(self) -> None:
        """
        @brief
        Validate maximum surgery duration constraint (V6).

        @details
        Checks whether each surgery’s duration does not exceed the configured
        upper bound (cfg.shift_max). Only applied when
        cfg.enforce_surgery_duration_limit is enabled.
        """
        if not bool(self.cfg.enforce_surgery_duration_limit):
            self.checks["DurationLimits"] = True
            return

        ok = True
        limit_hours = float(self.cfg.shift_max)

        # (1) Validate duration for each surgery
        for s in self.surgeries:
            start = _ensure_timezone(s.start_time)
            end = _ensure_timezone(s.end_time)
            dur_hours = _hours(end - start)

            # (1.1) Flag surgeries exceeding the maximum duration
            if dur_hours > limit_hours:
                ok = False
                self._add_error(
                    check="DurationLimits",
                    message=(
                        f"Surgery {s.surgery_id} exceeds maximum allowed duration "
                        f"({round(dur_hours, 3)}h > {round(limit_hours, 3)}h)"
                    ),
                    entities={
                        "surgery_id": s.surgery_id,
                        "duration_hours": round(dur_hours, 6),
                        "limit_hours": round(limit_hours, 6),
                    },
                    suggested_action="Reject or split surgeries that exceed maximum duration",
                )

        self.checks["DurationLimits"] = ok

    def _compute_metrics_and_utilization(self) -> None:
        """
        @brief
        Compute operational metrics and utilization ratio (V5).

        @details
        Aggregates high-level performance indicators for the current schedule:
          - total_cost calculated via piecewise overtime formula;
          - utilization = Σ(duration_surgeries) / total_cost;
          - counts of resources and workload indicators.
        Low utilization triggers a warning rather than a validation error.
        """
        # (1) Compute total surgery hours
        total_surgeries_hours = 0.0
        for s in self.surgeries:
            start = _ensure_timezone(s.start_time)
            end = _ensure_timezone(s.end_time)
            total_surgeries_hours += max(_hours(end - start), 0.0)

        # (2) Group assignments per anesthetist
        rows_by_anesthetist = defaultdict(list)
        for row in self.assignments:
            rows_by_anesthetist[row.anesthetist_id].append(row)

        shift_min_h = float(self.cfg.shift_min)
        overtime_threshold_h = float(self.cfg.shift_overtime)
        overtime_multiplier = float(self.cfg.overtime_multiplier)

        total_cost = 0.0
        num_anesthetists = 0
        rooms_used: set[str] = set()

        # (3) Compute cost per anesthetist using piecewise cost model
        for anesthetist_rows in rows_by_anesthetist.values():
            if not anesthetist_rows:  # pragma: no cover
                continue

            num_anesthetists += 1
            for r in anesthetist_rows:
                rooms_used.add(r.room_id)

            starts = [_ensure_timezone(r.start_time) for r in anesthetist_rows]
            ends = [_ensure_timezone(r.end_time) for r in anesthetist_rows]
            shift_start = min(starts)
            shift_end = max(ends)
            shift_hours = max(_hours(shift_end - shift_start), 0.0)

            base = max(shift_min_h, shift_hours)
            overtime = max(0.0, shift_hours - overtime_threshold_h)
            cost = base + (overtime_multiplier - 1.0) * overtime
            total_cost += cost

        # (4) Compute utilization ratio and store metrics
        utilization_target = float(self.cfg.utilization_target)
        utilization = (total_surgeries_hours / total_cost) if total_cost > 0.0 else 0.0

        self.metrics.update(
            {
                "total_cost": round(total_cost, 6),
                "utilization": round(utilization, 6),
                "runtime_seconds": None,  # validator does not track solver runtime
                "num_anesthetists": num_anesthetists,
                "num_rooms_used": len(rooms_used),
                "num_surgeries": len(self.surgeries),
                "num_assignments": len(self.assignments),
            }
        )

        # (5) Generate warnings for under-target utilization
        if utilization_target > 0 and utilization < utilization_target:
            self._add_warning(
                check="Utilization",
                message="Utilization is below target",
                entities={"value": round(utilization, 6), "target": utilization_target},
                suggested_action="Re-optimize with different parameters or adjust assignments",
            )
            self.checks["Utilization"] = False
        else:
            self.checks["Utilization"] = True

        # (6) Record total count of detected violations
        self.metrics["num_violations"] = len(self.errors)

    # ---------- Utilities for diagnostic kit ----------
    def _add_error(
        self,
        check: str,
        message: str,
        entities: dict[str, Any] | None = None,
        suggested_action: str | None = None,
    ) -> None:
        """
        @brief
        Append a structured error entry to the validation report.

        @details
        Records a validation failure with its check identifier, human-readable
        message, affected entities, and optional recovery suggestion.
        Errors represent strict violations of validation rules that affect
        schedule correctness or data consistency.

        @params
            check : str
                Validation check identifier (e.g., "NoOverlap", "DataIntegrity").
            message : str
                Descriptive message explaining the detected issue.
            entities : dict[str, Any] | None
                Optional contextual data, such as involved surgery or room IDs.
            suggested_action : str | None
                Optional recommended remediation or corrective action.
        """
        # (1) Construct error record payload
        payload: dict[str, Any] = {"check": check, "message": message}
        if entities:
            payload["entities"] = entities
        if suggested_action:
            payload["suggested_action"] = suggested_action

        # (2) Append to accumulated error list
        self.errors.append(payload)

    def _add_warning(
        self,
        check: str,
        message: str,
        entities: dict[str, Any] | None = None,
        suggested_action: str | None = None,
    ) -> None:
        """
        @brief
        Append a structured warning entry to the validation report.

        @details
        Records non-critical observations or performance deviations detected
        during validation. Warnings signal quality or efficiency issues that do
        not invalidate the schedule but may require review.

        @params
            check : str
                Validation check identifier related to this warning.
            message : str
                Description of the observed condition.
            entities : dict[str, Any] | None
                Optional context for debugging (e.g., anesthetist_id, value).
            suggested_action : str | None
                Optional suggestion for mitigating or improving the issue.
        """
        # (1) Construct warning record payload
        payload: dict[str, Any] = {"check": check, "message": message}
        if entities:
            payload["entities"] = entities
        if suggested_action:
            payload["suggested_action"] = suggested_action

        # (2) Append to accumulated warning list
        self.warnings.append(payload)


# ----------------------------
# THIN FACADE (static script call)
# ----------------------------
def validate_assignments(
    assignments: list[SolutionRow],
    surgeries: list[Surgery],
    cfg: Config,
    *,
    write_report: bool = True,
    out_dir: Path | None = None,
    filename: str = "validation_report.json",
) -> dict[str, Any]:
    """
    @brief
    High-level convenience wrapper for schedule validation.

    @details
    Creates a Validator instance, executes the full validation pipeline,
    builds a structured ValidationReport, and optionally writes it to disk
    as a JSON file. Always returns the in-memory report object regardless
    of write mode.

    @params
        assignments : list[SolutionRow]
            Solver-produced assignment rows to validate.
        surgeries : list[Surgery]
            Reference surgery definitions used for consistency checks.
        cfg : Config
            Runtime configuration containing validation parameters.
        write_report : bool
            If True, persist the generated report as a timestamped JSON file.
        out_dir : Path | None
            Optional custom output directory for saved reports.
        filename : str
            Base filename for the generated report before timestamping.

    @returns
        ValidationReport as a dictionary structure containing
        all checks, metrics, and messages.
    """
    # (1) Initialize validator instance with input data
    validator = Validator(assignments, surgeries, cfg)

    # (2) Execute full validation workflow
    validator.run_all_checks()

    # (3) Build final structured report
    report = validator.build_report()

    # (4) Optionally persist the report to disk
    if write_report:
        validator.save_report(report, out_dir=out_dir, filename=filename)

    # (5) Always return report dictionary
    return report
