from __future__ import annotations

import json
import logging
import time
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


class Optimizer:
    """
    CP-SAT runner: configures the solver, runs it, and extracts a structured result.

    Public API:
     - solve(bundle) -> SolveResult

    Internal helpers split for single responsibility:
     - _make_solver()
     - _apply_parameters(solver)
     - _solve_model(solver, model)
     - _extract_assignments(solver, bundle) -> (assign_x, assign_y)
     - _status_name(status_code) -> str
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # -------------------- Public --------------------

    def solve(self, bundle: CpSatModelBundle) -> SolveResult:
        """
        Run CP-SAT on the provided model bundle and return a structured SolveResult.

        SolveResult fields:
         - assignment: {"x": list[(s,a)], "y": list[(s,r)]}
         - status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | ...
         - objective: float | None
         - runtime: float (seconds)
        """
        solver = self._make_solver()
        self._apply_parameters(solver)

        self._log_solver_info(solver)

        t0 = time.perf_counter()
        status_code = self._solve_model(solver, bundle["model"])
        t1 = time.perf_counter()

        status = self._status_name(status_code)
        objective_value = None
        assignment: dict[str, Any] = {"x": [], "y": []}

        if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            assignment = self._extract_assignments(solver, bundle)
            # Note: objective could be scaled internally; we expose as-is.
            objective_value = solver.ObjectiveValue()

        result: SolveResult = {
            "assignment": assignment,
            "status": status,
            "objective": objective_value,
            "runtime": t1 - t0,
        }

        self._write_solver_log(solver, status, objective_value, t1 - t0)
        self._write_metrics(result)

        return result

    # -------------------- Internals --------------------

    def _make_solver(self) -> cp_model.CpSolver:
        """
        @brief
        Initializes and configures a new CP-SAT solver instance.

        @details
        Creates an instance of `cp_model.CpSolver`, applies baseline parameters,
        and returns it for use in optimization.
        By default, internal search progress logging is enabled, allowing the solver
        to output real-time statistics (e.g., conflicts, branches, bounds, solution count)
        during the search process. This aids in debugging, profiling, and transparency
        of solver behavior, as required by Step 5.3.2 of the design spec.

        @returns
            A fully initialized `cp_model.CpSolver` object ready for use in
            model solving and optimization.
        """

        # (1) Instantiate a new CP-SAT solver
        solver = cp_model.CpSolver()

        # (2) Enable detailed progress logging to stdout (useful for debugging and metrics)
        solver.parameters.log_search_progress = True

        # (3) Return configured solver instance
        return solver

    def _apply_parameters(self, solver: cp_model.CpSolver) -> None:
        """
        @brief
        Applies runtime configuration parameters from `self.cfg.solver` to the given CP-SAT solver instance.

        @details
        This method transfers user-defined or configuration-level solver options
        into the `cp_model.CpSolverParameters` structure. It ensures that
        resource utilization, runtime limits, and search behavior conform to
        the system configuration. Only valid, non-negative, and type-safe values
        are applied — invalid or missing entries are ignored to preserve defaults.

        Applied parameter groups:
          • **num_search_workers** — number of parallel workers used by the solver
            (`0` means automatic parallelism).
          • **max_time_in_seconds** — global time limit for the solving process.
          • **random_seed** — deterministic seed for reproducibility of results.
          • **search_branching** — search strategy:
                - "AUTOMATIC" (default)
                - "PORTFOLIO" (multi-heuristic approach)
                - "FIXED_SEARCH" (single heuristic sequence)

        @params
            solver : cp_model.CpSolver
                Solver instance to which configuration parameters are applied.

        @returns
            None. Modifies solver parameters in place.
        """

        # (1) Shortcut reference for readability
        params = solver.parameters

        # (2) Configure number of parallel workers (thread count)
        num_workers = getattr(self.cfg.solver, "num_workers", 0)
        if isinstance(num_workers, int) and num_workers >= 0:
            params.num_search_workers = num_workers

        # (3) Set global solving time limit (in seconds)
        max_time = getattr(self.cfg.solver, "max_time_in_seconds", None)
        if isinstance(max_time, (int | float)) and max_time is not None and max_time >= 0:
            params.max_time_in_seconds = float(max_time)

        # (4) Apply random seed for deterministic reproducibility
        seed = getattr(self.cfg.solver, "random_seed", None)
        if isinstance(seed, int) and seed >= 0:
            params.random_seed = seed

        # (5) Choose search branching strategy based on configuration string
        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()

        # (6) Map string value to OR-Tools constants (normalized to uppercase)
        mapping = {
            "AUTOMATIC": cp_model.AUTOMATIC_SEARCH,
            "PORTFOLIO": cp_model.PORTFOLIO_SEARCH,
            "FIXED_SEARCH": cp_model.FIXED_SEARCH,
        }

        # (7) Apply branching strategy; fallback to AUTOMATIC if invalid
        params.search_branching = mapping.get(branching, cp_model.AUTOMATIC_SEARCH)

        # (8) Log parameters
        log_to_stdout = getattr(self.cfg.solver, "log_to_stdout", True)
        params.log_to_stdout = bool(log_to_stdout)

    def _solve_model(
        self, solver: cp_model.CpSolver, model: cp_model.CpModel
    ) -> cp_model.CpSolverStatus:  # type: ignore[name-defined]
        """
        @brief
        Executes the CP-SAT solving process for the given model instance.

        @details
        This method invokes the OR-Tools solver’s `Solve()` routine to compute
        an optimal or feasible solution for the provided `cp_model.CpModel`.
        The result is returned as an integer status code defined by OR-Tools,
        such as:
            - cp_model.OPTIMAL
            - cp_model.FEASIBLE
            - cp_model.INFEASIBLE
            - cp_model.MODEL_INVALID
            - cp_model.UNKNOWN

        The status can be later used to interpret solver outcome or extract
        variable assignments from `solver.Value(var)`.

        @params
            solver : cp_model.CpSolver
                A configured solver instance (parameters already applied).
            model : cp_model.CpModel
                The compiled constraint programming model to be solved.

        @returns
            int — status code representing the solver result.
        """

        # (1) Invoke OR-Tools solver to find a feasible or optimal solution
        return solver.Solve(model)

    def _extract_assignments(
        self, solver: cp_model.CpSolver, bundle: CpSatModelBundle
    ) -> dict[str, Any]:
        """
        @brief
        Extracts the final assignment tuples from the solved CP-SAT model,
        returning which anesthesiologists and rooms were selected for each surgery.

        @details
        Iterates through all Boolean decision variables in the model and collects
        those that were assigned the value `1` by the solver.
        Specifically:
          • `x[s,a] = 1` → anesthesiologist `a` is assigned to surgery `s`
          • `y[s,r] = 1` → surgery `s` is assigned to room `r`

        OR-Tools represents BoolVars as IntVars (domain {0,1}), so `solver.Value(var)`
        simply returns an integer 0 or 1. The result is formatted as two lists of
        index tuples: one for `(s_idx, a_idx)` and another for `(s_idx, r_idx)`.

        @params
            solver : cp_model.CpSolver
                The solver instance containing the evaluated variable assignments.
            bundle : CpSatModelBundle
                Dictionary containing the model and its registered variable groups.

        @returns
            Dict[str, Any] — a dictionary with two lists:
                {
                    "x": [(s_idx, a_idx), ...],
                    "y": [(s_idx, r_idx), ...]
                }
            representing the final discrete assignment decisions.
        """

        vars_dict = bundle["vars"]
        assign_x = []
        assign_y = []

        # (1) Collect assigned anesthesiologists (x[s,a] == 1)
        for (s_idx, a_idx), var in vars_dict.get("x", {}).items():
            # OR-Tools BoolVar is IntVar; Value() returns 0 or 1
            if solver.Value(var) == 1:
                assign_x.append((int(s_idx), int(a_idx)))

        # (2) Collect assigned rooms (y[s,r] == 1)
        for (s_idx, r_idx), var in vars_dict.get("y", {}).items():
            if solver.Value(var) == 1:
                assign_y.append((int(s_idx), int(r_idx)))

        # (3) Return both assignment sets as structured output
        return {"x": assign_x, "y": assign_y}

    def _status_name(self, status_code: int) -> str:
        """
        @brief
        Converts an OR-Tools solver status code into a human-readable string label.

        @details
        OR-Tools represents solver outcomes as integer constants
        (e.g., `cp_model.OPTIMAL`, `cp_model.FEASIBLE`), but does not
        provide a direct name lookup in Python.
        This helper emulates that mapping for readability and logging.
        If the status code is unknown, a generic label `"STATUS_<code>"`
        is returned.

        Typical values:
            - cp_model.OPTIMAL → "OPTIMAL"
            - cp_model.FEASIBLE → "FEASIBLE"
            - cp_model.INFEASIBLE → "INFEASIBLE"
            - cp_model.MODEL_INVALID → "MODEL_INVALID"
            - cp_model.UNKNOWN → "UNKNOWN"

        @params
            status_code : int
                The integer solver status returned by `solver.Solve()`.

        @returns
            str — canonical status name or fallback "STATUS_<code>" string.
        """

        # (1) Define explicit mapping of OR-Tools status codes to labels
        mapping = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }

        # (2) Return readable name, or generic fallback for unknown codes
        return mapping.get(status_code, f"STATUS_{status_code}")

    def _log_solver_info(self, solver: cp_model.CpSolver) -> None:
        """
        @brief
        Logs a short header with solver configuration and OR-Tools version,
        providing traceability for each optimization run.

        @details
        This method prints a concise summary of the solver’s configuration,
        such as the number of workers, time limit, branching mode, and random seed.
        The goal is to make solver behavior reproducible and auditable
        by preserving the parameters used in each run.
        The debug log additionally outputs the full text of applied solver parameters.

        Typical example log:
            INFO  Solver start (ortools=9.10.4067, workers=1, max_time=10, branching=AUTOMATIC, seed=42)
            DEBUG Applied parameters:
            max_time_in_seconds: 10
            num_search_workers: 1
            search_branching: AUTOMATIC_SEARCH
            ...

        @params
            solver : cp_model.CpSolver
                The solver instance whose parameter configuration will be logged.

        @returns
            None. Produces INFO and DEBUG log messages for traceability.
        """

        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()
        logger.info(
            "Solver start (ortools=%s, workers=%s, max_time=%s, branching=%s, seed=%s)",
            ORTOOLS_VERSION,
            getattr(self.cfg.solver, "num_workers", 0),
            getattr(self.cfg.solver, "max_time_in_seconds", None),
            branching,
            getattr(self.cfg.solver, "random_seed", None),
        )
        logger.debug("Applied parameters:\n%s", str(solver.parameters))

    def _write_solver_log(
        self,
        solver: cp_model.CpSolver,
        status: str,
        objective: float | None,
        runtime: float,
    ) -> None:
        """
        @brief
        Writes a complete textual solver report to `<output_dir>/solver.log`,
        capturing configuration, parameters, results, and performance metrics.

        @details
        This method generates a structured and timestamped log file
        describing each optimization run. It records:
          - Environment info (ORTools version, search strategy, random seed)
          - Configured solver parameters
          - Experiment metadata (if present in cfg.experiment)
          - Solver outcome (status, objective, runtime)
          - Full solver `ResponseStats` summary

        The log file is stored in the directory `cfg.output_dir`
        (default: `"data/output"`). Logging can be disabled via
        `cfg.metrics.save_solver_log = False`.

        Example file contents:
            [2025-10-31T15:20:18Z] SOLVER RUN
            ortools_version: 9.10.4067
            random_seed: 42
            num_workers: 1
            max_time_in_seconds: 3
            search_branching: AUTOMATIC
            experiment.name: baseline
            experiment.tags: test,smoke
            experiment.description: Quick feasibility check

            == Parameters ==
            num_search_workers: 1
            max_time_in_seconds: 3
            search_branching: AUTOMATIC_SEARCH

            == Result ==
            status: OPTIMAL
            objective: 145.0
            runtime_sec: 0.331250

            == ResponseStats ==
            ...

        @params
            solver : cp_model.CpSolver
                The solver instance containing final parameters and statistics.
            status : str
                The solver’s final status name ("FEASIBLE", "OPTIMAL", etc.).
            objective : float | None
                The value of the objective function (if defined).
            runtime : float
                The total runtime of the solver in seconds.

        @returns
            None. Creates a persistent textual log for reproducibility.
        """

        # (1) Determine output directory and ensure it exists
        output_dir = Path(getattr(self.cfg, "output_dir", "data/output"))

        # (2) Resolve whether to save solver log from cfg.metrics
        metrics_cfg = getattr(self.cfg, "metrics", None)
        if isinstance(metrics_cfg, dict):
            save_solver_log = bool(metrics_cfg.get("save_solver_log", True))
        else:
            save_solver_log = (
                True if metrics_cfg is None else bool(getattr(metrics_cfg, "save_solver_log", True))
            )
        if not save_solver_log:
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "solver.log"

        # (3) Extract solver and configuration metadata
        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()
        seed = getattr(self.cfg.solver, "random_seed", None)
        num_workers = getattr(self.cfg.solver, "num_workers", None)
        max_time = getattr(self.cfg.solver, "max_time_in_seconds", None)
        exp = getattr(self.cfg, "experiment", None)

        # (4) Construct timestamped header with experiment info
        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        header = [
            f"[{ts}] SOLVER RUN",
            f"ortools_version: {ORTOOLS_VERSION}",
            f"random_seed: {seed}",
            f"num_workers: {num_workers}",
            f"max_time_in_seconds: {max_time}",
            f"search_branching: {branching}",
        ]
        if exp is not None:
            if isinstance(exp, dict):
                exp_name = exp.get("name")
                exp_tags = exp.get("tags")
                exp_desc = exp.get("description")
            else:
                exp_name = getattr(exp, "name", None)
                exp_tags = getattr(exp, "tags", None)
                exp_desc = getattr(exp, "description", None)
            header.append(f"experiment.name: {exp_name}")
            header.append(f"experiment.tags: {exp_tags}")
            header.append(f"experiment.description: {exp_desc}")

        # (5) Compose the solver results and detailed stats
        body_lines = [
            "",
            "== Parameters ==",
            str(solver.parameters),
            "",
            "== Result ==",
            f"status: {status}",
            f"objective: {objective}",
            f"runtime_sec: {runtime:.6f}",
            "",
            "== ResponseStats ==",
        ]

        try:
            body_lines.append(solver.ResponseStats())
        except RuntimeError:
            body_lines.append("<no ResponseStats: solve() has not been called>")
        body_lines.append("")

        # (6) Write the log file
        with log_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(header + body_lines))
            f.write("\n")

        # (7) Debug confirmation
        logger.debug("Solver log written to %s", str(log_path))

    def _write_metrics(self, result: dict[str, object]) -> None:
        """
        @brief
        Saves structured solver metrics to `<output_dir>/metrics.json`
        for downstream analysis or automated evaluation.

        @details
        This method generates a JSON file summarizing the solver’s
        configuration, runtime, and results.
        It provides a reproducible, machine-readable artifact
        that can be parsed by dashboards, pipelines, or CI jobs.

        The metrics file includes:
          - solver status and objective value,
          - runtime duration,
          - key solver parameters (workers, branching, seed, time limit),
          - OR-Tools version,
          - optional experiment metadata (if present in cfg.experiment).

        The output file is written to `cfg.output_dir` (default: `data/output`).
        Saving can be disabled by setting `cfg.metrics.save_metrics = False`.

        Example output (`metrics.json`):
            {
              "status": "OPTIMAL",
              "objective": 145.0,
              "runtime": 0.33125,
              "num_workers": 1,
              "random_seed": 42,
              "search_branching": "AUTOMATIC",
              "max_time_in_seconds": 3,
              "ortools_version": "9.10.4067",
              "experiment": {
                "name": "baseline",
                "tags": ["smoke", "ci"],
                "description": "Minimal reproducible test"
              }
            }

        @params
            result : dict[str, object]
                Dictionary containing solver output fields:
                status, objective, runtime, etc.

        @returns
            None. Writes the JSON metrics file and logs the output path.
        """

        # (1) Determine output directory and ensure it exists
        output_dir = Path(getattr(self.cfg, "output_dir", "data/output"))

        # (2) Respect configuration flag for saving metrics
        metrics_cfg = getattr(self.cfg, "metrics", None)
        if isinstance(metrics_cfg, dict):
            save_metrics = bool(metrics_cfg.get("save_metrics", True))
        else:
            save_metrics = (
                True if metrics_cfg is None else bool(getattr(metrics_cfg, "save_metrics", True))
            )
        if not save_metrics:
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = output_dir / "metrics.json"

        # (3) Assemble the JSON payload
        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()
        payload = {
            "status": result.get("status"),
            "objective": result.get("objective"),
            "runtime": result.get("runtime"),
            "num_workers": getattr(self.cfg.solver, "num_workers", None),
            "random_seed": getattr(self.cfg.solver, "random_seed", None),
            "search_branching": branching,
            "max_time_in_seconds": getattr(self.cfg.solver, "max_time_in_seconds", None),
            "ortools_version": ORTOOLS_VERSION,
        }

        # (4) Optional experiment metadata
        exp = getattr(self.cfg, "experiment", None)
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

        # (5) Write the JSON file
        with metrics_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

        # (6) Debug confirmation
        logger.debug("Metrics written to %s", str(metrics_path))
