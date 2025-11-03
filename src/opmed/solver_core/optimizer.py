from __future__ import annotations

from opmed.schemas.models import Config, SolutionRow
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
        """Executes the solver and returns enriched SolveResult."""
        result, solver, runtime = self._core.solve(bundle)

        # 1️⃣ Преобразовать индексы в структурированные строки расписания
        structured = self._to_solution_rows(result.get("assignments"), bundle)

        # 2️⃣ Сохранить артефакты
        final_result = self._store.persist(
            result={**result, "assignments": structured},
            solver=solver,
            runtime=runtime,
            bundle=bundle,
            assignment=result.get("assignments"),
        )

        # 3️⃣ Вернуть итог с готовыми SolutionRow
        final_result["assignments"] = structured
        final_result["solution_rows"] = [row.model_dump() for row in structured]
        return final_result

    def _to_solution_rows(
        self,
        assignments: dict[str, list[tuple[int, int]]] | None,
        bundle: CpSatModelBundle,
    ) -> list[SolutionRow]:
        """
        Converts index-based assignments into canonical SolutionRow objects.

        Args:
            assignments: Dict like {"x": [(s,a)], "y": [(s,r)]}.
            bundle: Model bundle containing surgeries list.

        Returns:
            List of SolutionRow ready for validation/visualization/export.
        """
        if not assignments:
            return []

        surgeries = bundle.get("surgeries", [])
        rows: list[SolutionRow] = []

        for s_idx, a_idx in assignments.get("x", []):
            surgery = surgeries[s_idx]
            # Находим комнату по индексу операции, если есть
            r_match = next((r_idx for (s, r_idx) in assignments.get("y", []) if s == s_idx), None)
            room_id = f"R{r_match}" if r_match is not None else "R0"

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
