# scripts/tune.py
"""
Hyperparameter tuning script for Opmed.

Implements Epic 7, Task 7.3.2.
Uses the IS_STRESS_TUNE flag to switch between default tuning and focused stress tuning.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml

# --- Imports from our project ---
try:
    from opmed.errors import OpmedError
    from opmed.schemas.models import Config  # noqa: F401
    from scripts.run import run_pipeline
except ImportError:
    print(
        "Error: Failed to import 'opmed' or 'scripts.run'. "
        "Ensure you run the script from the project root using 'poetry run python -m ...'.",
        file=sys.stderr,
    )
    sys.exit(1)


# ===============================================
# CONFIGURATION FLAGS
# ===============================================

# Set this flag to True to switch to the stress tuning configuration.
# False uses the default/medium tuning configuration.
IS_STRESS_TUNE: bool = True

# Default (IS_STRESS_TUNE = False) Paths
DEFAULT_BASE_CONFIG_PATH = Path("config/config.yaml")
DEFAULT_TUNE_GRID_PATH = Path("config/tune_grid.yaml")
DEFAULT_OUTPUT_DIR_NAME = "tune"
DEFAULT_RUN_PREFIX = ""

# Stress Tuning (IS_STRESS_TUNE = True) Paths
STRESS_TUNE_GRID_PATH = Path("config/tune_grid_stress.yaml")
STRESS_OUTPUT_DIR_NAME = "tune-stress"
STRESS_RUN_PREFIX = "stress-"


# --- Constants (defined dynamically based on flag) ---
# These will hold the *actual* paths used in main()
BASE_CONFIG_PATH: Path
TUNE_GRID_PATH: Path
TUNE_OUTPUT_DIR: Path


def setup_logging() -> None:
    """
    @brief
    Configures global logging output to stdout.

    @details
    Sets timestamped log messages with INFO verbosity.
    Provides consistent temporal context across all tuning stages.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_yaml_config(path: Path) -> dict[str, Any]:
    """
    @brief
    Loads a YAML configuration file into a dictionary.

    @details
    Reads and parses a UTF-8 encoded YAML file.
    On file absence or malformed syntax, logs an error
    and raises an exception with localized diagnostic text.

    @params
        path : Path
            Path to the YAML configuration file.

    @returns
        Parsed configuration dictionary.

    @raises
        FileNotFoundError
            If the configuration file does not exist.
        yaml.YAMLError
            If the file cannot be parsed correctly.
    """
    if not path.exists():
        logging.error(f"Configuration file not found: {path}")
        raise FileNotFoundError(f"Configuration file not found: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML in {path}: {e}")
        raise


def set_nested_key(config_dict: dict, key: str, value: Any) -> None:
    """
    @brief
    Assigns a value to a nested key in a dictionary using dotted notation.

    @details
    Traverses nested dictionaries, creating intermediate levels as needed.
    Used to override deep configuration fields programmatically.

    Example:
        set_nested_key(cfg, 'solver.num_workers', 8)
        → cfg['solver']['num_workers'] = 8

    @params
        config_dict : dict
            Target configuration dictionary to modify.
        key : str
            Dotted key path (e.g., "solver.num_workers").
        value : Any
            Value to assign.
    """
    keys = key.split(".")
    d = config_dict
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def generate_combinations(tune_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """
    @brief
    Expands all parameter combinations defined in a tuning grid.

    @details
    Reads `model.grid` and `solver.grid` sections from tune_grid.yaml.
    Produces the Cartesian product of parameter lists.
    Returns one dictionary per configuration combination.

    @params
        tune_cfg : dict[str, Any]
            Parsed tuning configuration from YAML.

    @returns
        List of parameter dictionaries to evaluate.
    """
    grid_params = {}

    # (1) Collect model-level parameters
    model_grid = tune_cfg.get("model", {}).get("grid", {})
    grid_params.update(model_grid)

    # (2) Collect solver-level parameters with prefixing
    solver_grid = tune_cfg.get("solver", {}).get("grid", {})
    for key, values in solver_grid.items():
        grid_params[f"solver.{key}"] = values

    # (3) Handle empty grid case
    if not grid_params:
        logging.warning("The grid in tune_grid.yaml is empty. 1 combination will be used.")
        return [{}]

    # (4) Compute Cartesian product of all grid dimensions
    keys, value_lists = zip(*grid_params.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*value_lists)]

    logging.info(f"Generated {len(combinations)} parameter combinations.")
    return combinations


def apply_run_config(
    base_cfg: dict[str, Any],
    context: dict[str, Any],
    combo: dict[str, Any],
    run_output_dir: Path,
) -> Path:
    """
    @brief
    Produces a temporary run configuration for a tuning iteration.

    @details
    Combines the base configuration, global context overrides, and specific
    hyperparameter combination. Forces output directories and reporting options.
    Writes the resulting YAML to disk and returns its path.

    @params
        base_cfg : dict[str, Any]
            Base configuration template.
        context : dict[str, Any]
            Global key-value overrides applied to all runs.
        combo : dict[str, Any]
            Specific parameter combination for this run.
        run_output_dir : Path
            Directory where the temporary config will be stored.

    @returns
        Path to the generated temporary YAML configuration file.
    """
    # (1) Deep-copy configuration safely via JSON round-trip
    run_cfg = json.loads(json.dumps(base_cfg))

    # (2) Apply global context parameters
    for key, value in context.items():
        set_nested_key(run_cfg, key, value)

    # (3) Apply combination-specific parameters
    for key, value in combo.items():
        set_nested_key(run_cfg, key, value)

    # (4) Force output directory and artifact flags
    run_cfg["output_dir"] = str(run_output_dir)
    set_nested_key(run_cfg, "validation.write_report", True)
    set_nested_key(run_cfg, "metrics.save_metrics", True)
    set_nested_key(run_cfg, "visualization.save_plot", True)

    # (5) Write final config to disk
    temp_config_path = run_output_dir / "config_run.yaml"
    try:
        with temp_config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(run_cfg, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logging.error(f"Failed to write temporary config {temp_config_path}: {e}")
        raise

    return temp_config_path


def get_metrics_from_file(metrics_path: Path | str | None) -> dict[str, Any]:
    """
    @brief
    Reads and filters metrics from a metrics.json file.

    @details
    Returns a lightweight subset of numerical indicators relevant for tuning
    analysis. Silently ignores missing or invalid files to preserve loop stability.

    @params
        metrics_path : Path | str | None
            Path to metrics.json file.

    @returns
        Dictionary with selected metrics fields, or an empty dict if unavailable.
    """
    if not metrics_path or not Path(metrics_path).exists():
        return {}

    try:
        data = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
        return {
            "utilization": data.get("utilization"),
            "total_cost": data.get("total_cost"),
            "num_anesthetists": data.get("num_anesthetists"),
            "num_rooms_used": data.get("num_rooms_used"),
        }
    except Exception:
        return {}


def main() -> int:
    """
    @brief
    Main entry point for automated hyperparameter tuning.

    @details
    Executes the full tuning workflow:
      (1) Load base and grid configurations.
      (2) Generate all parameter combinations.
      (3) For each dataset × combination, run the Opmed pipeline,
          collect metrics, and record results to CSV.
    Handles both default and stress test modes based on flags.
    Returns process exit code for shell integration.

    @returns
        0 on success, non-zero on controlled or critical failure.
    """
    setup_logging()
    t_start = time.perf_counter()

    # (1) Resolve configuration mode and paths
    global BASE_CONFIG_PATH, TUNE_GRID_PATH, TUNE_OUTPUT_DIR
    if IS_STRESS_TUNE:
        logging.info("Running in STRESS mode. Output will be isolated.")
        BASE_CONFIG_PATH = DEFAULT_BASE_CONFIG_PATH
        TUNE_GRID_PATH = STRESS_TUNE_GRID_PATH
        TUNE_OUTPUT_DIR = Path(f"data/output/{STRESS_OUTPUT_DIR_NAME}")
        run_prefix = STRESS_RUN_PREFIX
    else:
        logging.info("Running in DEFAULT mode.")
        BASE_CONFIG_PATH = DEFAULT_BASE_CONFIG_PATH
        TUNE_GRID_PATH = DEFAULT_TUNE_GRID_PATH
        TUNE_OUTPUT_DIR = Path(f"data/output/{DEFAULT_OUTPUT_DIR_NAME}")
        run_prefix = DEFAULT_RUN_PREFIX

    RESULTS_CSV_PATH = TUNE_OUTPUT_DIR / f"{run_prefix}tuning_results.csv"

    try:
        # (2) Load configurations
        base_cfg = load_yaml_config(BASE_CONFIG_PATH)
        tune_cfg = load_yaml_config(TUNE_GRID_PATH)

        datasets = tune_cfg.get("datasets", [])
        if not datasets:
            logging.error("'datasets' key not found in tune_grid.yaml. Stopping.")
            return 1

        context = tune_cfg.get("context", {})
        combinations = generate_combinations(tune_cfg)
        TUNE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # (3) Prepare CSV writer
        header = ["run_id", "dataset"]
        header.extend(combinations[0].keys())
        header.extend(
            [
                "status",
                "utilization",
                "runtime_sec",
                "total_cost",
                "num_anesthetists",
                "num_rooms_used",
                "is_valid",
            ]
        )

        total_runs = len(datasets) * len(combinations)
        logging.info(
            f"Total runs: {total_runs} ({len(datasets)} datasets x {len(combinations)} combinations)"
        )

        # (4) Run tuning loop
        with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=header, extrasaction="ignore")
            writer.writeheader()

            run_id_counter = 0
            for dataset_path_str in datasets:
                dataset_path = Path(dataset_path_str)
                if not dataset_path.exists():
                    logging.warning(f"Skipping: dataset not found {dataset_path}")
                    continue

                for combo in combinations:
                    run_id_counter += 1
                    run_id_str = f"{run_prefix}run-{run_id_counter:04d}"
                    log_prefix = (
                        f"[{run_id_counter}/{total_runs}] {run_id_str} ({dataset_path.name})"
                    )
                    logging.info(f"--- {log_prefix} ---")

                    # (5) Prepare isolated run directory
                    run_output_dir = TUNE_OUTPUT_DIR / run_id_str
                    if run_output_dir.exists():
                        shutil.rmtree(run_output_dir)
                    run_output_dir.mkdir()

                    csv_row = {"run_id": run_id_str, "dataset": dataset_path.name}
                    csv_row.update(combo)
                    metrics: dict[str, Any] = {}

                    try:
                        # (6) Build per-run config and execute pipeline
                        temp_config_path = apply_run_config(
                            base_cfg, context, combo, run_output_dir
                        )
                        result = run_pipeline(
                            config_path=temp_config_path,
                            input_path=dataset_path,
                            output_dir=run_output_dir,
                        )

                        # (7) Collect metrics
                        status = result.get("status", "UNKNOWN")
                        runtime = result.get("runtime_seconds")
                        is_valid = result.get("valid", False)
                        metrics.update(
                            {"status": status, "runtime_sec": runtime, "is_valid": is_valid}
                        )

                        if not is_valid:
                            logging.warning(f"{log_prefix} Solution is INVALID (status={status}).")

                        # Merge with metrics.json contents
                        metrics_path = result["artifacts"].get("metrics")
                        file_metrics = get_metrics_from_file(metrics_path)
                        metrics.update(file_metrics)

                    except OpmedError as e:
                        logging.error(f"{log_prefix} FAILED (OpmedError): {e}")
                        metrics = {"status": "PIPELINE_ERROR", "is_valid": False}
                    except Exception as e:
                        logging.error(f"{log_prefix} CRASHED (Exception): {e}", exc_info=True)
                        metrics = {"status": "CRASH", "is_valid": False}

                    # (8) Write results incrementally
                    csv_row.update(metrics)
                    writer.writerow(csv_row)
                    csv_file.flush()

    except Exception as e:
        logging.error(f"Critical tuner error: {e}", exc_info=True)
        return 1
    finally:
        t_end = time.perf_counter()
        logging.info(f"--- Tuning finished in {(t_end - t_start):.2f} sec. ---")
        logging.info(f"Results saved to: {RESULTS_CSV_PATH}")
        logging.info(f"Artifacts directory: {TUNE_OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
