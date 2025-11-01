# src/opmed/dataloader/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opmed.schemas.models import Surgery


@dataclass(slots=True)
class LoadResult:
    """
    Structured result of a data loading step.

    Fields:
        success: True if no row-level issues were found, False otherwise.
        surgeries: Validated surgeries ready for SolverCore (empty if success=False).
        errors: List of issue dicts with per-row context (used for reporting).
                Each item contains at least: kind, line_no, message, surgery_id (may be None).
        total_rows: Total number of data rows observed in the CSV (excludes header).
        kept_rows: Number of successfully parsed surgeries (len(surgeries)).
    """

    success: bool
    surgeries: list[Surgery] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    kept_rows: int = 0
