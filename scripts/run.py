# scripts/run.py
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opmed.dataloader.config_loader import ConfigLoader
from opmed.dataloader.postload_handler import LoadResultHandler
from opmed.dataloader.surgeries_loader import SurgeriesLoader

# --- Opmed imports
from opmed.errors import ConfigError, DataError, OpmedError, ValidationError  # noqa: F401
from opmed.export.solution_export import write_solution_csv
from opmed.metrics.logger import write_metrics, write_solver_log
from opmed.metrics.metrics import collect_metrics
from opmed.schemas.models import SolutionRow
from opmed.solver_core.model_builder import ModelBuilder
from opmed.solver_core.optimizer import Optimizer
from opmed.validator import validate_assignments
from opmed.visualizer.plot import plot_schedule


def _setup_logging() -> None:
    """
    @brief
    Initializes global logging configuration.

    @details
    Sets the default logging level to INFO and defines a simple console format.
    This function ensures consistent message formatting across the pipeline.
    """
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _parse_args() -> argparse.Namespace:
    """
    @brief
    Parses command-line arguments for the Opmed execution pipeline.

    @details
    Creates an argument parser with three configurable parameters:
    - config path (YAML),
    - input CSV path,
    - output directory for generated artifacts.

    Returns a Namespace containing parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="opmed-run",
        description="Run the Opmed optimization pipeline: load → solve → validate → visualize → metrics → export",
    )

    # (1) Config path argument
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml)",
    )

    # (2) Input CSV path argument
    parser.add_argument(
        "--input",
        type=str,
        default="data/synthetic/small_surgeries.csv",
        help="Path to surgeries CSV (default: data/synthetic/small_surgeries.csv)",
    )

    # (3) Output directory argument
    parser.add_argument(
        "--output",
        type=str,
        default="data/output",
        help="Output directory for artifacts (default: data/output)",
    )

    return parser.parse_args()


def _rename_anesthetists(assignments: Sequence[SolutionRow]) -> list[SolutionRow]:
    """
    @brief
    Sorts assignments chronologically and renames anesthetist_id sequentially (A001, A002, ...).

    @details
    Takes a sequence of SolutionRow objects and sorts them in ascending order by 'start_time'.
    Builds a mapping of original anesthetist identifiers to standardized sequential IDs
    (A001, A002, A003, ...), reflecting the chronological order of operations.
    Returns a new sorted list with updated anesthetist_id values.

    @params
        assignments : Sequence[SolutionRow]
            List or sequence of SolutionRow objects representing scheduled surgeries.

    @returns
        A new list of SolutionRow objects sorted by start_time and renamed according to
        their chronological order.
    """
    if not assignments:
        return []

    # (1) Sort a copy of the list by start time (ascending)
    sorted_assignments = sorted(assignments, key=lambda a: a.start_time)

    # (2) Collect unique old IDs in chronological order
    old_ids_in_order: list[str] = []
    seen_ids: set[str] = set()
    for row in sorted_assignments:
        old_id = row.anesthetist_id
        if not isinstance(old_id, str):
            old_id = str(old_id)
        if old_id not in seen_ids:
            seen_ids.add(old_id)
            old_ids_in_order.append(old_id)

    # (3) Build mapping old → standardized sequential IDs
    id_mapping: dict[str, str] = {
        old_id: f"A{i + 1:03d}" for i, old_id in enumerate(old_ids_in_order)
    }

    # (4) Apply mapping to the sorted list (creates renamed records)
    for row in sorted_assignments:
        key = str(row.anesthetist_id)
        row.anesthetist_id = id_mapping[key]

    return sorted_assignments


def run_pipeline(config_path: Path, input_path: Path, output_dir: Path) -> dict[str, Any]:
    """
    @brief
    Executes the full Opmed optimization pipeline.

    @details
    Performs sequential steps:
    (1) Load configuration and input data.
    (2) Build and solve the scheduling model using CP-SAT.
    (3) Validate solution, collect metrics, and visualize.
    (4) Export all artifacts and return summary metadata.
    Designed to raise OpmedError on controlled failures,
    allowing integration in batch or service workflows.

    @params
        config_path : Path
            Path to the YAML configuration file.
        input_path : Path
            Path to the surgeries CSV file.
        output_dir : Path
            Directory for storing pipeline outputs.

    @returns
        Dictionary containing validity flag, objective value,
        solver runtime, and artifact file paths.

    @raises
        OpmedError
            On configuration, validation, or data issues.
    """
    # (1) Start timer and prepare output directory
    t0 = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)

    # (2) Load configuration and input data
    logging.info("Loading config: %s", config_path)
    cfg = ConfigLoader().load(config_path)

    logging.info("Loading surgeries: %s", input_path)
    loader = SurgeriesLoader()
    load_result = loader.load(input_path)
    surgeries = LoadResultHandler(output_dir=output_dir).handle(load_result)

    # (3) Handle loading errors
    load_errors_path: Path | None = None
    if surgeries is None:
        load_errors_path = output_dir / "load_errors.json"
        raise DataError(
            message=f"Surgeries load failed — see {load_errors_path.as_posix()}",
            source="scripts.run",
            suggested_action="Fix CSV issues reported in load_errors.json and rerun the pipeline.",
        )

    # (4) Build model and run solver
    logging.info("Building CP-SAT model…")
    bundle = ModelBuilder(cfg, surgeries).build()

    logging.info("Solving…")
    optimizer = Optimizer(cfg)
    res: dict[str, Any] = optimizer.solve(bundle)

    status = (res.get("status") or "").upper()
    objective = res.get("objective")
    runtime = res.get("runtime")

    # (5) Validate solution and produce report
    logging.info("Validating assignments…")
    validation_report_path = output_dir / "validation_report.json"

    if status not in ("OPTIMAL", "FEASIBLE"):
        logging.warning("Solver finished with status=%s — no valid solution found", status)
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
        report = validate_assignments(
            res.get("assignments"), surgeries, cfg, write_report=True, out_dir=output_dir
        )
        valid = bool(report.get("valid", False))
        if not valid:
            logging.warning("Validation failed (valid=False). Visualization will be skipped.")

    # (6) Normalize assignments and replace anesthetist IDs
    assignments_raw = res.get("assignments")
    if assignments_raw:
        if not isinstance(assignments_raw, list) or (
            assignments_raw and not isinstance(assignments_raw[0], dict)
        ):
            try:
                assignments_dicts = [a.model_dump() for a in assignments_raw]
            except AttributeError:
                assignments_dicts = assignments_raw
        else:
            assignments_dicts = assignments_raw

        assignments_for_std = copy.deepcopy(assignments_dicts)
        logging.info("Standardizing Anesthetist IDs (A001, A002, ...) for all artifacts.")
        _rename_anesthetists(assignments_for_std)
        res["assignments"] = assignments_for_std

    # (7) Visualization step (only for valid solutions)
    plot_path: Path | None = None
    if valid:
        logging.info("Rendering schedule plot…")
        plot_path = plot_schedule(
            res.get("assignments"),
            surgeries,
            cfg,
            out_path=output_dir / "solution_plot.png",
        )
    else:
        logging.info("Skipping visualization due to invalid validation report or infeasible solve.")

    # (8) Metrics collection and solver log export
    logging.info("Collecting metrics…")
    summary = collect_metrics(res, cfg)
    metrics_path = write_metrics(summary, out_dir=output_dir)

    solver_log_path: Path | None = None
    try:
        solver_log_path = write_solver_log(res.get("solver"), cfg, out_dir=output_dir)
    except OpmedError as e:
        logging.warning("Solver log not written: %s", e)

    # (9) Export solution CSV
    logging.info("Exporting solution.csv…")
    assignments = res.get("assignments")
    if assignments and not isinstance(assignments[0], dict):
        assignments = [a.model_dump() for a in assignments]
    solution_csv_path = write_solution_csv(assignments or [], out_path=output_dir / "solution.csv")

    # (10) Final summary and runtime reporting
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
    """
    @brief
    CLI entry point for executing the full Opmed pipeline.

    @details
    Configures logging, parses CLI arguments, and invokes run_pipeline().
    Handles controlled (OpmedError) and unexpected exceptions,
    returning numeric exit codes suitable for shell integration:
      0 – success (valid result)
      1 – controlled failure (data/config/validation)
      2 – unexpected crash
    """
    _setup_logging()
    args = _parse_args()

    config_path = Path(args.config)
    input_path = Path(args.input)
    output_dir = Path(args.output)

    try:
        result = run_pipeline(config_path, input_path, output_dir)
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
        logging.error(str(e))
        return 1
    except Exception:
        logging.error("Unexpected error occurred:")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
