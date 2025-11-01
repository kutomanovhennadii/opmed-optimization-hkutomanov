# src/opmed/dataloader/surgeries_loader.py
from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from opmed.dataloader.types import LoadResult
from opmed.errors import DataError
from opmed.schemas.models import Surgery

logger = logging.getLogger(__name__)


class SurgeriesLoader:
    """
    @brief
    Loads surgical schedule data from a UTF-8 CSV file and converts it into a LoadResult[Surgery].

    @details
    This loader parses a tabular input of surgeries, validates each record, and
    converts valid rows into Surgery model instances. Input rows are processed
    one by one with per-row validation; invalid records are logged as issues but
    do not interrupt the parsing pipeline. The process ensures deterministic
    ordering of results and consistent error reporting. Raises DataError only
    for fatal I/O or header problems.
    """

    REQUIRED_COLUMNS = ("surgery_id", "start_time", "end_time")

    def load(self, path: Path, time_unit: float | None = None) -> LoadResult:
        """
        @brief
        Entry point for loading and validating surgeries from a CSV file.

        @details
        Executes a full read-parse-validate-report pipeline:
        (1) reads CSV rows from disk,
        (2) converts them into domain models with validation,
        (3) logs summary information to the global logger.
        Raises DataError for any fatal issue (e.g., missing file, invalid header).
        """
        # (1) Read CSV into list of dictionaries
        rows = self._read_csv(path)

        # (2) Convert raw rows to structured LoadResult
        result = self._rows_to_result(rows)

        # (3) Log summary information
        self._report_summary(path, result)
        return result

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        """
        @brief
        Reads the surgeries CSV file and returns parsed rows as dictionaries.

        @details
        Performs type and existence checks on the input path, opens the file as UTF-8
        text, validates the header, and strips whitespace in each row.
        Raises DataError immediately if file is missing, inaccessible, or malformed.
        """
        # (1) Validate path type
        if not isinstance(path, Path):
            raise DataError(
                message=f"Invalid path type: expected pathlib.Path, got {type(path).__name__}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Pass a pathlib.Path pointing to surgeries.csv",
            )

        # (2) Verify file existence
        if not path.exists():
            raise DataError(
                message=f"Input CSV not found: {path}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Verify file path and ensure the CSV is present.",
            )

        # (3) Open and read CSV content
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=",")
                if reader.fieldnames is None:
                    raise DataError(
                        message="CSV has no header row.",
                        source="SurgeriesLoader._read_csv",
                        suggested_action="Ensure the first line contains column names.",
                    )

                # (4) Normalize header and validate structure
                header = tuple((name or "").strip() for name in reader.fieldnames)
                self._validate_header(header)

                # (5) Return cleaned list of rows
                return [self._strip_row(r) for r in reader]

        # (6) Catch I/O errors
        except OSError as e:
            raise DataError(
                message=f"Unable to read CSV: {e}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Check file permissions and that the file is not locked.",
            ) from e

    def _validate_header(self, header: Iterable[str]) -> None:
        """
        @brief
        Ensures the CSV header contains all required columns.

        @details
        Checks that mandatory fields (surgery_id, start_time, end_time) exist in
        the header. Raises DataError if any are missing.
        """
        missing = [c for c in self.REQUIRED_COLUMNS if c not in header]
        if missing:
            raise DataError(
                message=f"Invalid CSV header: missing required column(s): {', '.join(missing)}",
                source="SurgeriesLoader._validate_header",
                suggested_action="Add required columns: surgery_id,start_time,end_time",
            )

    def _strip_row(self, row: dict[str, str]) -> dict[str, str]:
        """
        @brief
        Strips whitespace from all string values in a row dictionary.

        @details
        Ensures consistency in field comparison and downstream validation by
        cleaning extra spaces introduced by inconsistent CSV formatting.
        """
        return {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

    def _rows_to_result(self, rows: list[dict[str, str]]) -> LoadResult:
        """
        @brief
        Converts validated CSV rows into a LoadResult containing Surgery models.

        @details
        Iterates over rows, performing field-level validation for missing IDs,
        datetime parsing, duration consistency, and duplicates. For invalid rows,
        structured issues are recorded. Returns a successful LoadResult only if
        no issues occurred; otherwise returns an error summary with empty data.
        """
        # (1) Initialize accumulators
        issues: list[dict[str, Any]] = []
        surgeries: list[Surgery] = []
        seen_ids: set[str] = set()

        # (2) Process rows sequentially (line numbering starts from 2 due to header)
        for idx, row in enumerate(rows, start=2):
            sid_raw = row.get("surgery_id") or ""
            start_raw = row.get("start_time") or ""
            end_raw = row.get("end_time") or ""

            # (3) Validate presence of surgery_id
            if not sid_raw:
                issues.append(
                    {
                        "kind": "missing_id",
                        "line_no": idx,
                        "surgery_id": None,
                        "message": "Missing surgery_id",
                    }
                )
                continue

            # (4) Parse start and end timestamps
            try:
                start_dt = datetime.fromisoformat(start_raw)
                end_dt = datetime.fromisoformat(end_raw)
            except Exception as e:
                issues.append(
                    {
                        "kind": "invalid_datetime",
                        "line_no": idx,
                        "surgery_id": sid_raw,
                        "message": f"Invalid datetime format: {e}",
                    }
                )
                continue

            # (5) Verify temporal ordering (start < end)
            if not (start_dt < end_dt):
                issues.append(
                    {
                        "kind": "non_positive_duration",
                        "line_no": idx,
                        "surgery_id": sid_raw,
                        "message": "start_time >= end_time",
                    }
                )
                continue

            # (6) Check for duplicate surgery IDs
            if sid_raw in seen_ids:
                issues.append(
                    {
                        "kind": "duplicate_id",
                        "line_no": idx,
                        "surgery_id": sid_raw,
                        "message": "Duplicate surgery_id (later occurrence skipped)",
                    }
                )
                continue

            # (7) Construct Surgery model instance
            try:
                s = Surgery(surgery_id=sid_raw, start_time=start_dt, end_time=end_dt)
            except Exception as e:
                issues.append(
                    {
                        "kind": "schema_error",
                        "line_no": idx,
                        "surgery_id": sid_raw,
                        "message": f"Surgery model construction failed: {e}",
                    }
                )
                continue

            surgeries.append(s)
            seen_ids.add(sid_raw)

        # (8) Finalize result depending on issue presence
        if issues:
            return LoadResult(
                success=False,
                surgeries=[],
                errors=issues,
                total_rows=len(rows),
                kept_rows=0,
            )

        # (9) Sort surgeries by start time for deterministic output
        surgeries.sort(key=lambda s: s.start_time)
        return LoadResult(
            success=True,
            surgeries=surgeries,
            errors=[],
            total_rows=len(rows),
            kept_rows=len(surgeries),
        )

    def _report_summary(self, path: Path, result: LoadResult) -> None:
        """
        @brief
        Logs a summary of loading results to the global logger.

        @details
        Aggregates and reports the number and types of issues encountered
        during the CSV loading process. Produces concise human-readable
        feedback in both success and failure cases.
        """
        # (1) Successful case
        if result.success:
            logger.info(
                "SurgeriesLoader OK: kept=%d/%d from %s",
                result.kept_rows,
                result.total_rows,
                path,
            )
        else:
            # (2) Aggregate issues by kind for concise reporting
            counts: dict[str, int] = {}
            for it in result.errors:
                counts[it["kind"]] = counts.get(it["kind"], 0) + 1

            # (3) Build summary string and log
            summary = ", ".join(f"{k}={v}" for k, v in counts.items())
            logger.error(
                "SurgeriesLoader failed: %d issue(s) across %d row(s) in %s [%s]",
                len(result.errors),
                result.total_rows,
                path,
                summary or "no-summary",
            )
