from __future__ import annotations

from opmed.schemas.models import Config, SolutionRow
from opmed.solver_core.optimizer_core import CpSatModelBundle, OptimizerCore, SolveResult
from opmed.solver_core.result_store import ResultStore


class Optimizer:
    """
    @brief
    Facade providing a unified and stable interface for running optimization.

    @details
    Acts as a coordinator that separates compute logic and side effects.
    Responsibilities:
        - Delegates computation to OptimizerCore (pure solver logic)
        - Delegates artifact and log persistence to ResultStore

    Public API:
        solve(bundle) -> SolveResult
    """

    def __init__(self, cfg: Config) -> None:
        """
        @brief
        Initializes the optimizer facade with configuration.

        @details
        Stores the configuration reference and prepares internal subsystems.
        OptimizerCore performs computation, ResultStore handles output artifacts.

        @params
            cfg : Config
                Global configuration shared by core and result store.
        """
        # (1) Store configuration reference
        self.cfg = cfg

        # (2) Initialize internal components
        # OptimizerCore handles solving logic; ResultStore handles persistence
        self._core = OptimizerCore(cfg)
        self._store = ResultStore(cfg)

    def solve(self, bundle: CpSatModelBundle) -> SolveResult:
        """
        @brief
        Executes the solver and returns an enriched SolveResult structure.

        @details
        Runs the optimization core, transforms raw assignments into
        structured SolutionRow objects, and persists all resulting artifacts.

        @params
            bundle : CpSatModelBundle
                The model bundle containing data, constraints, and solver inputs.

        @returns
            SolveResult dictionary enriched with structured assignments and artifacts.
        """
        result, solver, runtime = self._core.solve(bundle)

        # (1) Transform index-based results into structured schedule rows
        structured = self._to_solution_rows(result.get("assignments"), bundle)

        # (2) Persist artifacts and logs via ResultStore
        final_result = self._store.persist(
            result={**result, "assignments": structured},
            solver=solver,
            runtime=runtime,
            bundle=bundle,
            assignment=result.get("assignments"),
        )

        # (3) Enrich and return final result with SolutionRow representations
        final_result["assignments"] = structured
        final_result["solution_rows"] = [row.model_dump() for row in structured]
        return final_result

    def _to_solution_rows(
        self,
        assignments: dict[str, list[tuple[int, int]]] | None,
        bundle: CpSatModelBundle,
    ) -> list[SolutionRow]:
        """
        @brief
        Converts index-based assignment results into canonical SolutionRow objects.

        @details
        Maps solver variable indices to human-readable identifiers.
        This step reconstructs the final schedule, associating surgeries
        with anesthesiologists and rooms.

        @params
            assignments : dict[str, list[tuple[int, int]]] | None
                Mappings of surgery indices to anesthetists and rooms (x, y).
            bundle : CpSatModelBundle
                Model data bundle containing the list of Surgery objects.

        @returns
            List[SolutionRow] — validated and structured schedule rows.
        """
        if not assignments:
            return []

        surgeries = bundle.get("surgeries", [])
        rows: list[SolutionRow] = []

        # (1) Convert index-based assignments to SolutionRow objects
        for s_idx, a_idx in assignments.get("x", []):
            surgery = surgeries[s_idx]

            # (2) Find matching room index for this surgery, if any
            r_match = next((r_idx for (s, r_idx) in assignments.get("y", []) if s == s_idx), None)
            room_id = f"R{r_match}" if r_match is not None else "R0"

            # (3) Build structured SolutionRow entry
            rows.append(
                SolutionRow(
                    surgery_id=surgery.surgery_id,
                    start_time=surgery.start_time,
                    end_time=surgery.end_time,
                    anesthetist_id=f"A{a_idx}",
                    room_id=room_id,
                )
            )
        return rows
