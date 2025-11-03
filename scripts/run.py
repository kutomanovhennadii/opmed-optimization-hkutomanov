# scripts/run.py
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from opmed.dataloader.config_loader import ConfigLoader
from opmed.dataloader.postload_handler import LoadResultHandler
from opmed.dataloader.surgeries_loader import SurgeriesLoader

# --- Opmed imports (по нашим интерфейсам) ---
from opmed.errors import ConfigError, DataError, OpmedError, ValidationError  # noqa: F401
from opmed.export.solution_export import write_solution_csv
from opmed.metrics.logger import write_metrics, write_solver_log
from opmed.metrics.metrics import collect_metrics
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer
from opmed.validator import validate_assignments
from opmed.visualizer.plot import plot_schedule


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="opmed-run",
        description="Run the Opmed optimization pipeline: load → solve → validate → visualize → metrics → export",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/synthetic/small_surgeries.csv",
        help="Path to surgeries CSV (default: data/synthetic/small_surgeries.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/output",
        help="Output directory for artifacts (default: data/output)",
    )
    return parser.parse_args()


def run_pipeline(
    config_path: Path,
    input_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """
    Исполняет весь конвейер Opmed и возвращает словарь с путями артефактов и ключевыми показателями.
    Не завершает процесс сам по себе — поднимает OpmedError при фатальных ошибках загрузки/конфигурации.

    Args:
        config_path: путь к YAML конфигурации.
        input_path: путь к CSV с операциями.
        output_dir: директория для артефактов (будет создана).

    Returns:
        {
          "valid": bool,
          "status": str | None,
          "objective": float | None,
          "runtime_seconds": float | None,
          "artifacts": {
              "validation_report": Path | None,
              "metrics": Path | None,
              "solver_log": Path | None,
              "solution_csv": Path | None,
              "solution_plot": Path | None,   # None если визуализация пропущена
              "load_errors": Path | None,     # присутствует только при ошибках загрузки
          }
        }

    Raises:
        OpmedError: при проблемах конфигурации/чтения/структуры входных данных.
    """
    t0 = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1) Load config ---
    logging.info("Loading config: %s", config_path)
    cfg = ConfigLoader().load(config_path)

    # --- 2) Load surgeries (с батч-репортингом ошибок) ---
    logging.info("Loading surgeries: %s", input_path)
    loader = SurgeriesLoader()
    load_result = loader.load(input_path)
    surgeries = LoadResultHandler(output_dir=output_dir).handle(load_result)
    load_errors_path: Path | None = None
    if surgeries is None:
        # Файл создан пост-обработчиком при ошибках
        load_errors_path = output_dir / "load_errors.json"
        # Для переиспользуемого пайплайна бросаем контролируемую ошибку
        raise DataError(
            message=f"Surgeries load failed — see {load_errors_path.as_posix()}",
            source="scripts.run",
            suggested_action="Fix CSV issues reported in load_errors.json and rerun the pipeline.",
        )

    # --- 3) Build model ---
    logging.info("Building CP-SAT model…")
    bundle = ModelBuilder(cfg, surgeries).build()

    # --- 4) Solve ---
    logging.info("Solving…")
    optimizer = Optimizer(cfg)
    res: dict[str, Any] = optimizer.solve(bundle)

    status = (res.get("status") or "").upper()
    objective = res.get("objective")
    runtime = res.get("runtime")

    # --- 5) Validate ---
    logging.info("Validating assignments…")

    # Новая логика: мягкая обработка статусов решателя без исключений.
    # Если нет допустимого решения — пишем минимальный validation_report.json сами
    # и помечаем valid=False, визуализацию пропускаем.
    validation_report_path = output_dir / "validation_report.json"
    valid: bool
    report: dict[str, Any]

    if status not in ("OPTIMAL", "FEASIBLE"):
        logging.warning("Solver finished with status=%s — no valid solution found", status)

        # минимальный отчёт, который объясняет причину
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report = {
            "timestamp": ts,
            "valid": False,
            "errors": [
                {
                    "check": "SolverStatus",
                    "message": f"No feasible solution found (status={status})",
                    "entities": {},
                    "suggested_action": "Inspect model constraints and data consistency",
                }
            ],
            "warnings": [],
            "metrics": {
                "num_surgeries": len(surgeries),
                "status": status,
                "objective": objective,
                "runtime_seconds": runtime,
            },
            "checks": {"SolverStatus": False},
        }
        validation_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        valid = False
    else:
        # обычный путь: валидируем фактические назначения и пишем полноценный отчёт
        report = validate_assignments(
            res.get("assignments"), surgeries, cfg, write_report=True, out_dir=output_dir
        )
        valid = bool(report.get("valid", False))
        if not valid:
            logging.warning("Validation failed (valid=False). Visualization will be skipped.")

    # --- 6) Visualize (только если валидно) ---
    plot_path: Path | None = None
    if valid:
        logging.info("Rendering schedule plot…")
        plot_path = plot_schedule(
            res.get("assignments"),
            surgeries,
            cfg,
            out_path=output_dir / "solution_plot.png",
        )
        logging.info("Plot saved: %s", plot_path)
    else:
        logging.info("Skipping visualization due to invalid validation report or infeasible solve.")

    # --- 7) Metrics & logs (всегда собираем) ---
    logging.info("Collecting metrics…")
    summary = collect_metrics(res, cfg)
    metrics_path = write_metrics(summary, out_dir=output_dir)
    logging.info("Metrics saved: %s", metrics_path)

    solver_log_path: Path | None = None
    solver_obj = res.get("solver")
    try:
        solver_log_path = write_solver_log(solver_obj, cfg, out_dir=output_dir)
        logging.info("Solver log saved: %s", solver_log_path)
    except OpmedError as e:
        # Не фейлим пайплайн из-за невозможности записать лог
        logging.warning("Solver log not written: %s", e)

    # --- 8) Export solution CSV (делаем всегда; полезно для анализа) ---
    logging.info("Exporting solution.csv…")
    assignments = res.get("assignments")

    # преобразуем SolutionRow → dict, если нужно
    if assignments and not isinstance(assignments[0], dict):
        assignments = [a.model_dump() for a in assignments]

    # при отсутствии решения — пишем пустой CSV с заголовком
    if not assignments:
        assignments = []

    solution_csv_path = write_solution_csv(assignments, out_path=output_dir / "solution.csv")
    logging.info("Solution CSV saved: %s", solution_csv_path)

    dt = time.perf_counter() - t0
    logging.info("Pipeline finished in %.2f s", dt)

    artifacts = {
        "validation_report": validation_report_path if validation_report_path.exists() else None,
        "metrics": metrics_path,
        "solver_log": solver_log_path,
        "solution_csv": solution_csv_path,
        "solution_plot": plot_path,
        "load_errors": load_errors_path,
    }

    return {
        "valid": valid,
        "status": status or None,
        "objective": objective,
        "runtime_seconds": runtime,
        "artifacts": artifacts,
    }


def main() -> int:
    _setup_logging()
    args = _parse_args()

    config_path = Path(args.config)
    input_path = Path(args.input)
    output_dir = Path(args.output)

    try:
        result = run_pipeline(config_path, input_path, output_dir)

        # Итоговый вывод и код возврата
        arts = result["artifacts"]
        logging.info(
            "Artifacts in %s: %s%s%s%s",
            output_dir.as_posix(),
            "validation_report.json, " if arts.get("validation_report") else "",
            "metrics.json, " if arts.get("metrics") else "",
            "solver.log, " if arts.get("solver_log") else "",
            "solution.csv"
            + (", solution_plot.png" if arts.get("solution_plot") else " (plot skipped)"),
        )

        return 0 if result.get("valid") else 1

    except OpmedError as e:
        # Контролируемые ошибки (ConfigError/DataError/ValidationError/…)
        logging.error(str(e))
        return 1
    except Exception:
        # Неконтролируемый сбой — показываем трейсбек для отладки
        logging.error("Unexpected error occurred:")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
