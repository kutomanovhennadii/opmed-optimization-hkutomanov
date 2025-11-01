from __future__ import annotations

from opmed.schemas.models import Config
from opmed.solver_core.optimizer_core import CpSatModelBundle, OptimizerCore, SolveResult
from opmed.solver_core.result_store import ResultStore


class Optimizer:
    """
    Facade providing a simple and stable public interface for solving models.

    Responsibilities:
        - Delegates solving to OptimizerCore (pure compute logic)
        - Delegates artifact/log writing to ResultStore (side effects)

    Public API:
        solve(bundle) -> SolveResult
    """

    def __init__(self, cfg: Config) -> None:
        """
        Initializes the optimizer facade with configuration.

        Args:
            cfg: Global configuration object used by both core and store.
        """
        # (1) Store configuration reference
        self.cfg = cfg

        # (2) Initialize internal components:
        #     OptimizerCore handles computation, ResultStore handles persistence
        self._core = OptimizerCore(cfg)
        self._store = ResultStore(cfg)

    def solve(self, bundle: CpSatModelBundle) -> SolveResult:
        """
        Executes full optimization flow:
            1. Runs the CP-SAT solver via OptimizerCore
            2. Persists results and artifacts via ResultStore

        Args:
            bundle: Model bundle containing CpModel and variables.

        Returns:
            Final SolveResult dictionary, possibly extended with 'solution_path'.
        """
        # (1) Run solver and capture result, solver instance, and runtime
        result, solver, runtime = self._core.solve(bundle)

        # (2) Extract variable assignments from result (if any)
        assignment = result.get("assignment")

        # (3) Persist artifacts and logs based on I/O policy, return final result
        final_result = self._store.persist(
            result=result,
            solver=solver,
            runtime=runtime,
            bundle=bundle,
            assignment=assignment if assignment else None,
        )
        return final_result
