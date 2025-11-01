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
    Post-load reaction layer for the orchestrator.

    Задачи:
      - принять LoadResult
      - если success=False → записать подробный отчёт об ошибках в JSON, вернуть None
      - если success=True  → вернуть list[Surgery] для следующего шага

    JSON-отчёт:
      output_dir / "load_errors.json"
      [
        { "kind": "...", "line_no": 5, "surgery_id": "S001", "message": "..." },
        ...
      ]
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def handle(self, result: LoadResult) -> list[Surgery] | None:
        if result.success:
            logger.info("PostLoad: %d surgeries ready for SolverCore.", result.kept_rows)
            return result.surgeries

        self._ensure_dir(self.output_dir)
        out_path = self.output_dir / "load_errors.json"
        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result.errors, f, ensure_ascii=False, indent=2)
            logger.error(
                "PostLoad: input validation failed — %d issue(s). See %s",
                len(result.errors),
                out_path,
            )
        except OSError as e:
            logger.error("PostLoad: failed to write error report: %s", e)

        return None

    # ------------------------------
    # Internal
    # ------------------------------
    def _ensure_dir(self, d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
