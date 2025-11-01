# src/opmed/dataloader/postload_handler.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from opmed.dataloader.types import LoadResult
from opmed.schemas.models import Surgery

logger = logging.getLogger(__name__)


class LoadResultHandler:
    """
    @brief
    Handles the LoadResult after CSV parsing and writes diagnostic reports if needed.

    @details
    This post-processing layer receives a LoadResult from the data loader.
    If the load succeeded, it returns the validated list of Surgery instances.
    If the load failed, it creates a JSON error report summarizing per-row issues
    and returns None. This allows the orchestrator to halt the pipeline gracefully
    while preserving detailed error context for debugging and traceability.
    """

    def __init__(self, output_dir: Path) -> None:
        """
        @brief
        Initializes handler with output directory for error reporting.

        @details
        Stores the target directory path used to write JSON error reports.
        The directory will be created automatically if it does not exist.
        """
        self.output_dir = output_dir

    def handle(self, result: LoadResult) -> list[Surgery] | None:
        """
        @brief
        Processes LoadResult and produces either data for SolverCore or an error report.

        @details
        When the load result indicates success, the validated surgeries are passed
        downstream. If validation failed, a detailed JSON report containing
        all encountered issues is written to 'load_errors.json' inside output_dir.
        Any I/O failure during report creation is logged but does not raise further.
        """
        # (1) Success path — pass validated data downstream
        if result.success:
            logger.info("PostLoad: %d surgeries ready for SolverCore.", result.kept_rows)
            return result.surgeries

        # (2) Failure path — ensure directory and prepare JSON report
        self._ensure_dir(self.output_dir)
        out_path = self.output_dir / "load_errors.json"

        try:
            # (3) Serialize structured errors into JSON file
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result.errors, f, ensure_ascii=False, indent=2)

            # (4) Log summary with reference to output file
            logger.error(
                "PostLoad: input validation failed — %d issue(s). See %s",
                len(result.errors),
                out_path,
            )
        except OSError as e:
            # (5) Gracefully log if report writing fails
            logger.error("PostLoad: failed to write error report: %s", e)

        # (6) Return None to indicate blocked downstream processing
        return None

    def _ensure_dir(self, d: Path) -> None:
        """
        @brief
        Ensures existence of the output directory.

        @details
        Creates directory structure recursively if missing.
        Safe to call multiple times due to 'exist_ok=True'.
        """
        d.mkdir(parents=True, exist_ok=True)
