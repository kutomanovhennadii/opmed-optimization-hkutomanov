# src/opmed/metrics/logger.py
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ortools

from opmed.errors import DataError


def write_metrics(metrics: dict[str, Any], out_dir: Path) -> Path:
    """
    Пишет metrics.json (UTF-8) атомарно. Повторный запуск перезаписывает файл.
    DoD: валидный JSON; без NaN/None.
    """
    if not isinstance(metrics, dict):
        raise DataError("metrics must be a dict", source="metrics.write_metrics")

    # проверяем сериализуемость заранее (и нормальные типы)
    try:
        payload = json.dumps(metrics, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception as e:
        raise DataError(
            f"metrics not JSON-serializable: {e}",
            source="metrics.write_metrics",
            suggested_action="Ensure metrics values are primitives (str/float/int/bool).",
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "metrics.json"
    _atomic_write_text(target, payload, encoding="utf-8")
    return target


def write_solver_log(solver: Any, cfg: Any, out_dir: Path) -> Path:
    """
    Пишет solver.log (UTF-8) атомарно. Повторный запуск перезаписывает файл.
    Лог содержит: timestamp, параметры, версию OR-Tools (если доступна), статус/объектив/время.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "solver.log"

    # собираем строки лога
    lines = []
    now = _utc_now_hms()
    lines.append(f"[{now}] INFO Starting CP-SAT solver")

    # Параметры солвера из cfg.solver
    try:
        s_cfg = getattr(cfg, "solver")
        workers = getattr(s_cfg, "num_workers", None)
        tlimit = getattr(s_cfg, "max_time_in_seconds", None)
        seed = getattr(s_cfg, "random_seed", None)
        branching = getattr(s_cfg, "search_branching", None)
        lines.append(
            f"[{now}] INFO Parameters: workers={workers}, time_limit={tlimit}s, seed={seed}, search_branching={branching}"
        )
    except Exception:
        pass

    # Версия OR-Tools (если импортируется)
    try:
        ver = getattr(ortools, "__version__", "unknown")
        lines.append(f"[{now}] INFO OR-Tools version: {ver}")
    except Exception:
        pass

    # Если у нас есть solver с ResponseStats() — добавим финальную строку статуса
    try:
        # Некоторые обёртки cp-solver возвращают текстовую статистику
        stats = getattr(solver, "ResponseStats", None)
        if callable(stats):
            text = solver.ResponseStats()
            # Поищем ключевые элементы для удобства
            # (это просто дополнение; сам текст кладём целиком ниже)
            lines.append(f"[{now}] INFO ResponseStats snippet: {text.splitlines()[0]}")
            lines.append("")  # пустая строка
            lines.append(text)
        else:
            # fallback: если у нас нет текстовой статистики, просто отмечаем завершение
            lines.append(f"[{now}] INFO Solver finished (no ResponseStats available)")
    except Exception:
        lines.append(f"[{now}] WARN Failed to read ResponseStats()")

    payload = "\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else "")

    _atomic_write_text(target, payload, encoding="utf-8")
    return target


# ----------------- internal -----------------


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    Кроссплатформенная атомарная запись: через временный файл и замену.
    """
    path = Path(path)
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Временный файл рядом с целевым (важно для атомарности в пределах FS)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=str(tmp_dir))
    try:
        with open(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp_path, path)  # атомарная замена на большинстве ОС
    except Exception as e:
        # Чистим временный файл при ошибке
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        finally:
            raise DataError(
                f"atomic write failed for {path}: {e}",
                source="metrics._atomic_write_text",
                suggested_action="Check output directory permissions and disk space.",
            )


def _utc_now_hms() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
