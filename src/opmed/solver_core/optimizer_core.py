from __future__ import annotations

import logging
import time
from typing import Any

import ortools
from ortools.sat.python import cp_model

from opmed.schemas.models import Config

logger = logging.getLogger(__name__)

ORTOOLS_VERSION: str = getattr(ortools, "__version__", "unknown")

SolveResult = dict[str, Any]
CpSatModelBundle = dict[str, Any]


class OptimizerCore:
    """
    Core optimization engine: configures CpSolver, solves the CP-SAT model,
    and extracts assignments. Performs no file I/O or side effects.

    Public interface:
        solve(bundle) -> (result: SolveResult, solver: CpSolver, runtime: float)

    SolveResult fields:
        - assignment: {"x": [(s,a)], "y": [(s,r)]}
        - status: solver status name
        - objective: objective value or None
        - runtime: total solver runtime in seconds
    """

    def __init__(self, cfg: Config) -> None:
        """
        Initializes the optimizer with configuration.

        Args:
            cfg: Global Config object containing solver settings.
        """
        self.cfg = cfg

    def solve(self, bundle: CpSatModelBundle) -> tuple[SolveResult, cp_model.CpSolver, float]:
        """
        Solves the provided model bundle using OR-Tools CP-SAT.

        Args:
            bundle: CpSatModelBundle containing "model" and "vars" keys.

        Returns:
            Tuple of (SolveResult, solver instance, runtime seconds).
        """
        # (1) Create solver instance and apply configuration parameters
        solver = self._make_solver()
        self._apply_parameters(solver)

        # (2) Measure runtime while solving
        t0 = time.perf_counter()
        status_code = self._solve_model(solver, bundle["model"])
        t1 = time.perf_counter()
        runtime = t1 - t0

        # (3) Decode solver status and prepare placeholders
        status = self._status_name(status_code)
        objective_value: float | None = None
        assignment: dict[str, Any] = {"x": [], "y": []}

        # (4) If solution is feasible/optimal → extract assignments and objective
        if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            assignment = self._extract_assignments(solver, bundle)
            objective_value = solver.ObjectiveValue()

        # (5) Construct final result dictionary
        result: SolveResult = {
            "assignment": assignment,
            "status": status,
            "objective": objective_value,
            "runtime": runtime,
        }
        return result, solver, runtime

    # -------------------- Internal helpers (pure logic) --------------------

    def _make_solver(self) -> cp_model.CpSolver:
        """
        Creates and configures a new CpSolver instance.
        """
        # (1) Basic solver setup with progress logging enabled
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = True
        return solver

    def _apply_parameters(self, solver: cp_model.CpSolver) -> None:
        """
        Applies solver configuration parameters from cfg.solver.

        Args:
            solver: Target CpSolver instance to modify.
        """
        # (1) Retrieve parameters object from solver
        params = solver.parameters

        # (2) Number of parallel workers
        num_workers = getattr(self.cfg.solver, "num_workers", 0)
        if isinstance(num_workers, int) and num_workers >= 0:
            params.num_search_workers = num_workers

        # (3) Maximum runtime limit
        max_time = getattr(self.cfg.solver, "max_time_in_seconds", None)
        if isinstance(max_time, (int | float)) and max_time is not None and max_time >= 0:
            params.max_time_in_seconds = float(max_time)

        # (4) Random seed for reproducibility
        seed = getattr(self.cfg.solver, "random_seed", None)
        if isinstance(seed, int) and seed >= 0:
            params.random_seed = seed

        # (5) Search branching strategy
        branching = str(getattr(self.cfg.solver, "search_branching", "AUTOMATIC")).upper()
        mapping = {
            "AUTOMATIC": cp_model.AUTOMATIC_SEARCH,
            "PORTFOLIO": cp_model.PORTFOLIO_SEARCH,
            "FIXED_SEARCH": cp_model.FIXED_SEARCH,
        }
        params.search_branching = mapping.get(branching, cp_model.AUTOMATIC_SEARCH)

        # (6) Console logging flag
        log_to_stdout = getattr(self.cfg.solver, "log_to_stdout", True)
        params.log_to_stdout = bool(log_to_stdout)

    def _solve_model(
        self, solver: cp_model.CpSolver, model: cp_model.CpModel
    ) -> cp_model.CpSolverStatus:  # type: ignore[name-defined]
        """
        Executes the solve call on the provided model.
        """
        # (1) Direct call to OR-Tools solver
        return solver.Solve(model)

    def _extract_assignments(
        self, solver: cp_model.CpSolver, bundle: CpSatModelBundle
    ) -> dict[str, Any]:
        """
        Extracts binary assignment decisions (x, y) from solver variables.

        Args:
            solver: CpSolver instance with solution loaded.
            bundle: Model bundle containing variable dictionaries.

        Returns:
            Dict with keys 'x' and 'y', each holding list of active pairs.
        """
        # (1) Initialize output lists
        vars_dict = bundle["vars"]
        assign_x: list[tuple[int, int]] = []
        assign_y: list[tuple[int, int]] = []

        # (2) Collect active anesthesiologist assignments
        for (s_idx, a_idx), var in vars_dict.get("x", {}).items():
            if solver.Value(var) == 1:
                assign_x.append((int(s_idx), int(a_idx)))

        # (3) Collect active room assignments
        for (s_idx, r_idx), var in vars_dict.get("y", {}).items():
            if solver.Value(var) == 1:
                assign_y.append((int(s_idx), int(r_idx)))

        return {"x": assign_x, "y": assign_y}

    def _status_name(self, status_code: cp_model.CpSolverStatus) -> str:  # type: ignore[name-defined]
        """
        Converts solver status code to human-readable string.

        Args:
            status_code: OR-Tools status enum value.

        Returns:
            Textual status name (OPTIMAL, FEASIBLE, etc.).
        """
        # (1) Map numeric status code to string
        mapping = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }
        return mapping.get(status_code, f"STATUS_{int(status_code)}")
