# result_store.py
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import ortools
from ortools.sat.python import cp_model

from opmed.schemas.models import Config

logger = logging.getLogger(__name__)
ORTOOLS_VERSION: str = getattr(ortools, "__version__", "unknown")

SolveResult = dict[str, Any]
CpSatModelBundle = dict[str, Any]


class ResultStore:
    """
    Единая точка побочных эффектов (артефакты/логи).
    Управляется конфигом:
      io_policy.write_artifacts: bool (default True)
      io_policy.write_solver_logs: bool (default False)

    Методы не знают бизнес-логики оптимизации — только запись.
    """

    def __init__(self, cfg: Config) -> None:
        """
        Initializes ResultStore, the unified interface for writing solver artifacts and logs.

        Args:
            cfg: Global configuration object. Must optionally define:
                - io_policy.write_artifacts (bool)
                - io_policy.write_solver_logs (bool)
                - output_dir (str, optional path for outputs)

        Notes:
            If writing is enabled, the output directory is created automatically.
        """
        # (1) Store config reference
        self.cfg = cfg

        # (2) Resolve I/O policy flags (supports both nested io_policy and legacy direct attributes)
        io_policy = getattr(cfg, "io_policy", None)
        self.write_artifacts = getattr(
            io_policy, "write_artifacts", getattr(cfg, "write_artifacts", True)
        )
        self.write_solver_logs = getattr(
            io_policy, "write_solver_logs", getattr(cfg, "write_solver_logs", False)
        )

        # (3) Prepare output directory and create it if writing is enabled
        self.output_dir = Path(getattr(self.cfg, "output_dir", "data/output"))
        if self.write_artifacts or self.write_solver_logs:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    # --------------- Public facade ---------------

    def persist(
        self,
        result: SolveResult,
        solver: cp_model.CpSolver | None,
        runtime: float,
        bundle: CpSatModelBundle | None,
        assignment: dict[str, Any] | None,
    ) -> SolveResult:
        """
        Persists artifacts (metrics, logs, and solutions) according to I/O policy.

        Args:
            result: Final solver result dict.
            solver: Optional CpSolver instance, used for logging.
            runtime: Total solver runtime in seconds.
            bundle: Optional model bundle for solution export.
            assignment: Optional variable assignment dict.

        Returns:
            Updated result dict with optional 'solution_path'.
        """
        # (0) Initialize placeholder for safety
        solution_path: str | None = None

        # (1) Write solver log if enabled
        if self.write_solver_logs and solver is not None:
            self._write_solver_log(solver, result["status"], result.get("objective"), runtime)

        # (2) Write metrics and solution artifacts if enabled
        if self.write_artifacts:
            self._write_metrics(result)
            if bundle and assignment:
                solution_path = self._write_solution(bundle, assignment)
            self._write_config_snapshot()

        # (3) Return augmented result
        result = dict(result)
        result["solution_path"] = solution_path
        return result

    # --------------- Private writers ---------------

    def _write_solution(self, bundle: CpSatModelBundle, assignment: dict[str, Any]) -> str:
        """
        Writes a simple CSV file with variable assignments (x/y pairs).
        Used to visualize which anesthesiologist and room were assigned to each surgery.

        Args:
            bundle: Model bundle (not used directly here, but kept for consistency).
            assignment: Dict with keys 'x' and 'y', each holding index pairs.

        Returns:
            Absolute path to the written CSV file.
        """
        # (1) Generate timestamped file name inside output directory
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = self.output_dir / f"solution_{ts}.csv"

        # (2) Build CSV content from assignment pairs
        lines = ["type,s_index,second_index"]
        for s, a in assignment.get("x", []):
            lines.append(f"x,{s},{a}")
        for s, r in assignment.get("y", []):
            lines.append(f"y,{s},{r}")

        # (3) Write content to file and log the result
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.debug("Solution written to %s", str(path))
        return str(path)

    def _write_metrics(self, result: SolveResult) -> None:
        """
        Writes solver metrics to timestamped 'metrics_<name>_<timestamp>.json' if enabled.

        Example:
            metrics_baseline_20251101T135845Z.json
        """
        # (1) Determine if metrics saving is enabled
        metrics_cfg = getattr(self.cfg, "metrics", None)
        if isinstance(metrics_cfg, dict):
            save_metrics = bool(metrics_cfg.get("save_metrics", True))
        else:
            save_metrics = (
                True if metrics_cfg is None else bool(getattr(metrics_cfg, "save_metrics", True))
            )
        if not self.write_artifacts or not save_metrics:
            return

        # (2) Timestamped file name
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        exp = getattr(self.cfg, "experiment", None)

        if exp is not None:
            exp_name = exp.get("name") if isinstance(exp, dict) else getattr(exp, "name", None)
            if exp_name:
                safe_name = str(exp_name).replace(" ", "_")
                filename = f"metrics_{safe_name}_{ts}.json"
            else:
                filename = f"metrics_{ts}.json"
        else:
            filename = f"metrics_{ts}.json"

        path = self.output_dir / filename

        # (3) Prepare metrics payload
        payload = {
            "status": result.get("status"),
            "objective": result.get("objective"),
            "runtime": result.get("runtime"),
            "num_workers": getattr(self.cfg.solver, "num_workers", None),
            "random_seed": getattr(self.cfg.solver, "random_seed", None),
            "search_branching": str(
                getattr(self.cfg.solver, "search_branching", "AUTOMATIC")
            ).upper(),
            "max_time_in_seconds": getattr(self.cfg.solver, "max_time_in_seconds", None),
            "ortools_version": ORTOOLS_VERSION,
        }

        # (4) Attach optional experiment info if present
        if exp is not None:
            if isinstance(exp, dict):
                payload["experiment"] = {
                    "name": exp.get("name"),
                    "tags": exp.get("tags"),
                    "description": exp.get("description"),
                }
            else:
                payload["experiment"] = {
                    "name": getattr(exp, "name", None),
                    "tags": getattr(exp, "tags", None),
                    "description": getattr(exp, "description", None),
                }

        # (5) Write JSON to disk and log confirmation
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

        logger.debug("Metrics written to %s", str(path))

    def _write_solver_log(
        self,
        solver: cp_model.CpSolver,
        status: str,
        objective: float | None,
        runtime: float,
    ) -> None:
        """
        Writes a detailed solver log to 'solver.log' when enabled by configuration.

        Respects:
            - cfg.metrics.save_solver_log (legacy flag)
            - io_policy.write_solver_logs (new unified flag)

        Args:
            solver: CpSolver instance used for solving the model.
            status: String representation of solver status.
            objective: Final objective value, if available.
            runtime: Solver runtime in seconds.
        """
        # (1) Determine if log writing is enabled (merge legacy and new flags)
        metrics_cfg = getattr(self.cfg, "metrics", None)
        if isinstance(metrics_cfg, dict):
            save_solver_log = bool(metrics_cfg.get("save_solver_log", True))
        elif metrics_cfg is None:
            save_solver_log = True
        else:
            save_solver_log = bool(getattr(metrics_cfg, "save_solver_log", True))

        if not (save_solver_log or self.write_solver_logs):
            return

        # (2) Prepare log file path and basic solver parameters
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "solver.log"

        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()
        seed = getattr(self.cfg.solver, "random_seed", None)
        num_workers = getattr(self.cfg.solver, "num_workers", None)
        max_time = getattr(self.cfg.solver, "max_time_in_seconds", None)

        # (3) Compose log lines: metadata, parameters, and results
        lines = [
            f"[{ts}] SOLVER RUN",
            f"ortools_version: {ORTOOLS_VERSION}",
            f"random_seed: {seed}",
            f"num_workers: {num_workers}",
            f"max_time_in_seconds: {max_time}",
            f"search_branching: {branching}",
            "",
            "== Parameters ==",
            str(solver.parameters),
            "",
            "== Result ==",
            f"status: {status}",
            f"objective: {objective}",
            f"runtime_sec: {runtime:.6f}",
        ]

        # (4) Add optional experiment section
        exp = getattr(self.cfg, "experiment", None)
        if exp:
            lines.append("")
            lines.append("== Experiment ==")
            if isinstance(exp, dict):
                for k, v in exp.items():
                    lines.append(f"experiment.{k}: {v}")
            else:
                for k in ("name", "tags", "description"):
                    lines.append(f"experiment.{k}: {getattr(exp, k, None)}")

        # (5) Append solver statistics safely
        lines.append("")
        lines.append("== ResponseStats ==")
        try:
            lines.append(solver.ResponseStats())
        except RuntimeError:
            lines.append("<no ResponseStats: solve() has not been called>")

        # (6) Write log file and confirm
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.debug("Solver log written to %s", str(path))

    def _write_config_snapshot(self) -> str:
        """
        Saves a quick JSON snapshot of the current config for reproducibility.

        Args:
            None

        Returns:
            Path to the created snapshot file.
        """
        # (1) Prepare timestamped filename with experiment name if present
        from pydantic import TypeAdapter

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        exp = getattr(self.cfg, "experiment", None)
        name = (exp.get("name") if isinstance(exp, dict) else getattr(exp, "name", None)) or "run"
        path = self.output_dir / f"config_snapshot_{name}_{ts}.json"

        # (2) Serialize config (supports both modern and legacy pydantic versions)
        if hasattr(self.cfg, "model_dump"):
            data = self.cfg.model_dump()
        else:
            data = TypeAdapter(type(self.cfg)).dump_python(self.cfg)

        # (3) Write JSON snapshot and log success
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        logger.debug("Config snapshot written to %s", str(path))
        return str(path)
