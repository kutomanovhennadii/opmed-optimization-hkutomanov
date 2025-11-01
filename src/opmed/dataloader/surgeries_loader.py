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
    CSV → LoadResult[Surgery].

    Правила:
      - Формат: UTF-8 CSV, delimiter=','
      - Обязательные колонки: surgery_id, start_time, end_time
      - Парсинг времени: datetime.fromisoformat() (без нормализации в UTC)
      - Валидация по строкам (row-level):
          * пустой surgery_id        → issue + продолжаем
          * unparsable datetime      → issue + продолжаем
          * start_time >= end_time   → issue + продолжаем
          * duplicate surgery_id     → issue + продолжаем (оставляем ПЕРВУЮ валидную запись)
      - По завершении:
          * если есть issues → success=False, surgeries=[], errors=[...]
          * иначе            → success=True, surgeries отсортированы по start_time

    Фатальные ошибки (raise DataError сразу):
      - отсутствует файл / недоступен
      - отсутствует заголовок CSV
      - отсутствуют обязательные колонки
    """

    REQUIRED_COLUMNS = ("surgery_id", "start_time", "end_time")

    def load(self, path: Path, time_unit: float | None = None) -> LoadResult:
        rows = self._read_csv(path)
        result = self._rows_to_result(rows)
        self._report_summary(path, result)
        return result

    # ------------------------------
    # Internal helpers
    # ------------------------------
    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        if not isinstance(path, Path):
            raise DataError(
                message=f"Invalid path type: expected pathlib.Path, got {type(path).__name__}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Pass a pathlib.Path pointing to surgeries.csv",
            )
        if not path.exists():
            raise DataError(
                message=f"Input CSV not found: {path}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Verify file path and ensure the CSV is present.",
            )

        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=",")
                if reader.fieldnames is None:
                    raise DataError(
                        message="CSV has no header row.",
                        source="SurgeriesLoader._read_csv",
                        suggested_action="Ensure the first line contains column names.",
                    )
                header = tuple((name or "").strip() for name in reader.fieldnames)
                self._validate_header(header)
                return [self._strip_row(r) for r in reader]
        except OSError as e:
            raise DataError(
                message=f"Unable to read CSV: {e}",
                source="SurgeriesLoader._read_csv",
                suggested_action="Check file permissions and that the file is not locked.",
            ) from e

    def _validate_header(self, header: Iterable[str]) -> None:
        missing = [c for c in self.REQUIRED_COLUMNS if c not in header]
        if missing:
            raise DataError(
                message=f"Invalid CSV header: missing required column(s): {', '.join(missing)}",
                source="SurgeriesLoader._validate_header",
                suggested_action="Add required columns: surgery_id,start_time,end_time",
            )

    def _strip_row(self, row: dict[str, str]) -> dict[str, str]:
        return {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

    def _rows_to_result(self, rows: list[dict[str, str]]) -> LoadResult:
        issues: list[dict[str, Any]] = []
        surgeries: list[Surgery] = []
        seen_ids: set[str] = set()

        for idx, row in enumerate(rows, start=2):  # header = line 1
            sid_raw = row.get("surgery_id") or ""
            start_raw = row.get("start_time") or ""
            end_raw = row.get("end_time") or ""

            # empty id
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

            # parse datetimes
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

            # non-positive duration
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

            # duplicates: keep first valid, later are issues
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

            # construct model
            try:
                s = Surgery(surgery_id=sid_raw, start_time=start_dt, end_time=end_dt)
            except Exception as e:
                # schema mismatch (маловероятно при предыдущих проверках)
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

        if issues:
            # при наличии issues — останавливаем конвейер; отдаём структурированный отчёт
            return LoadResult(
                success=False,
                surgeries=[],
                errors=issues,
                total_rows=len(rows),
                kept_rows=0,
            )

        surgeries.sort(key=lambda s: s.start_time)
        return LoadResult(
            success=True,
            surgeries=surgeries,
            errors=[],
            total_rows=len(rows),
            kept_rows=len(surgeries),
        )

    def _report_summary(self, path: Path, result: LoadResult) -> None:
        if result.success:
            logger.info(
                "SurgeriesLoader OK: kept=%d/%d from %s",
                result.kept_rows,
                result.total_rows,
                path,
            )
        else:
            # агрегируем по типам
            counts: dict[str, int] = {}
            for it in result.errors:
                counts[it["kind"]] = counts.get(it["kind"], 0) + 1
            summary = ", ".join(f"{k}={v}" for k, v in counts.items())
            logger.error(
                "SurgeriesLoader failed: %d issue(s) across %d row(s) in %s [%s]",
                len(result.errors),
                result.total_rows,
                path,
                summary or "no-summary",
            )
