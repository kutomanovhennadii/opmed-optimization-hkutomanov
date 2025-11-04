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
    @brief
    Writes metrics.json atomically in UTF-8 encoding.

    @details
    Validates that the input is a serializable dictionary,
    dumps it to JSON with sorted keys and indentation,
    and performs atomic replacement of the target file.
    Ensures that repeated executions overwrite the same file cleanly.

    @params
        metrics : dict[str, Any]
            Dictionary containing solver metrics (numeric and textual values).
        out_dir : Path
            Directory where metrics.json will be created.

    @returns
        Path to the created metrics.json file.

    @raises
        DataError
            If input is not a dict or JSON serialization fails.
    """
    if not isinstance(metrics, dict):
        raise DataError("metrics must be a dict", source="metrics.write_metrics")

    # (1) Validate JSON serializability to ensure safe persistence
    try:
        payload = json.dumps(metrics, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception as e:
        raise DataError(
            f"metrics not JSON-serializable: {e}",
            source="metrics.write_metrics",
            suggested_action="Ensure metrics values are primitives (str/float/int/bool).",
        )

    # (2) Ensure output directory exists
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # (3) Atomically write validated payload
    target = out_dir / "metrics.json"
    _atomic_write_text(target, payload, encoding="utf-8")
    return target


def write_solver_log(solver: Any, cfg: Any, out_dir: Path) -> Path:
    """
    @brief
    Writes solver.log atomically with contextual metadata.

    @details
    Records solver parameters, timestamp, and OR-Tools version if available.
    Attempts to capture the solver’s textual statistics via ResponseStats().
    Produces a readable log suitable for debugging or experiment tracing.

    @params
        solver : Any
            Solver object returned by the optimizer.
        cfg : Any
            Configuration object containing solver parameters.
        out_dir : Path
            Directory where solver.log will be stored.

    @returns
        Path to the created solver.log file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "solver.log"

    # (1) Initialize log lines
    now = _utc_now_hms()
    lines = [f"[{now}] INFO Starting CP-SAT solver"]

    # (2) Extract solver parameters from configuration
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

    # (3) Add OR-Tools version if accessible
    try:
        ver = getattr(ortools, "__version__", "unknown")
        lines.append(f"[{now}] INFO OR-Tools version: {ver}")
    except Exception:
        pass

    # (4) Append solver statistics if ResponseStats() is available
    try:
        stats = getattr(solver, "ResponseStats", None)
        if callable(stats):
            text = solver.ResponseStats()
            lines.append(f"[{now}] INFO ResponseStats snippet: {text.splitlines()[0]}")
            lines.append("")  # spacing for readability
            lines.append(text)
        else:
            lines.append(f"[{now}] INFO Solver finished (no ResponseStats available)")
    except Exception:
        lines.append(f"[{now}] WARN Failed to read ResponseStats()")

    # (5) Finalize payload and write atomically
    payload = "\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else "")
    _atomic_write_text(target, payload, encoding="utf-8")
    return target


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    @brief
    Performs atomic text file writing using a temporary file swap.

    @details
    Writes text to a temporary file within the same directory, then replaces
    the destination in a single filesystem operation. Guarantees consistency
    even if the process crashes mid-write.

    @params
        path : Path
            Target file path to overwrite.
        text : str
            File content to write.
        encoding : str
            Encoding to use when writing the file (default: UTF-8).

    @raises
        DataError
            On write or rename failure.
    """
    path = Path(path)
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # (1) Create temporary file near the target for atomicity
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=str(tmp_dir))
    try:
        with open(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp_path, path)  # atomic replacement on most systems
    except Exception as e:
        # (2) Clean up temp file on error
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
    """
    @brief
    Returns current UTC timestamp in human-readable format.

    @details
    Provides a concise timestamp string (YYYY-MM-DD HH:MM:SS)
    for consistent log prefixing across Opmed components.

    @returns
        String with UTC timestamp.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
