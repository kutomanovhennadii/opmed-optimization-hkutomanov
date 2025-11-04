# HYPERPARAMETER TUNING PROCESS (Epic 7.3)

## Overview
This document describes the automated hyperparameter tuning process implemented in scripts/tune.py. The tuner systematically explores combinations of solver and model parameters, runs the full optimization pipeline for each combination, and records results for later analysis.
Two modes of operation are supported: Default and Stress. The mode is controlled by the global flag IS_STRESS_TUNE at the top of the script.

---

## Mode Selection via IS_STRESS_TUNE
The flag IS_STRESS_TUNE determines which configuration files, datasets, and output directories will be used.

### Default Mode (IS_STRESS_TUNE = False)
Used for exploratory and demonstration tuning runs.
* Grid file: config/tune_grid.yaml
* Output directory: data/output/tune/
* Run prefix: run-
* Typical datasets: small or medium synthetic samples
* Goal: identify promising parameter combinations quickly

### Stress Mode (IS_STRESS_TUNE = True)
Used for robustness testing under high workload and tight constraints.
* Grid file: config/tune_grid_stress.yaml
* Output directory: data/output/tune-stress/
* Run prefix: stress-run-
* Typical datasets: stress or large-scale synthetic scenarios
* Goal: evaluate solver stability and constraint satisfaction under extreme conditions

The flag affects:
1. Which YAML grid file is loaded
2. Which datasets are used
3. Where artifacts and results are written
4. The naming of run directories and CSV files

Switching the flag requires no code modification—only toggling the Boolean value at the top of tune.py.

---

## Execution Flow

### 1. Initialization
Logging is configured with timestamps and INFO verbosity. The script resolves the active mode and prepares paths for the base configuration, tuning grid, and output directory.

### 2. Configuration Loading
Two YAML files are read:
* Base configuration: config/config.yaml
* Parameter grid: tune_grid.yaml or tune_grid_stress.yaml
Both are parsed with yaml.safe_load(). Syntax or file errors stop execution with a clear diagnostic.

### 3. Grid Expansion
The function generate_combinations() extracts parameter lists from model.grid and solver.grid sections of the tuning YAML. It computes the Cartesian product of all combinations, producing one parameter dictionary per run—each representing one tuning experiment.

### 4. Dataset Iteration
Datasets are listed in the datasets field of the tuning grid YAML. The tuner iterates through every dataset × parameter combination. A unique run ID (run-0001, run-0002, etc.) is assigned, and a dedicated output subfolder is created for isolation.

### 5. Temporary Config Generation
apply_run_config() creates a temporary YAML config for each run by merging:
* The base configuration
* Global overrides from the context section of the grid YAML
* The specific parameter combination

Additional enforced parameters:
* output_dir → run’s folder
* validation.write_report = True
* metrics.save_metrics = True
* visualization.save_plot = True

The resulting config_run.yaml is written to the run directory.

### 6. Pipeline Execution
Each generated configuration is passed to run_pipeline() from scripts/run.py. This executes the full sequence: load → solve → validate → visualize → export.

### 7. Metrics Collection
After completion:
* Core metrics (status, runtime, validity) come from run_pipeline()
* Supplementary metrics are read from metrics.json via get_metrics_from_file()
* All values are written incrementally to the tuning CSV to preserve progress even if later runs fail.

### 8. Error Handling
* Controlled issues (invalid data, infeasible solver state) raise OpmedError and mark PIPELINE_ERROR.
* Unhandled exceptions are marked CRASH.
* The tuner logs the event and continues, ensuring full grid coverage.

### 9. Results Aggregation
Each CSV record includes: run_id, dataset, tuned parameters, status, utilization, runtime_sec, total_cost, num_anesthetists, num_rooms_used, and is_valid.
CSV paths:
* data/output/tune/tuning_results.csv (default)
* data/output/tune-stress/stress-tuning_results.csv (stress)

### 10. Completion
Upon completion, the tuner reports elapsed time and result paths. All run artifacts (metrics.json, validation_report.json, solution.csv, plots, logs) remain in their respective folders.

---

## Usage
Run from the repository root:
    poetry run python -m scripts.tune
To switch between modes, edit:
    IS_STRESS_TUNE = False   → default tuning
    IS_STRESS_TUNE = True    → stress tuning

---

## Output Structure
Each tuning session produces:
* Master CSV with all combinations and metrics
* One subfolder per run with its artifacts
* Comprehensive log of progress and performance

---

## Typical Analysis Workflow
1. Open the resulting CSV in a spreadsheet or notebook.
2. Filter by is_valid = True to remove infeasible solutions.
3. Sort by utilization (desc) or total_cost (asc).
4. Inspect the corresponding run folder for metrics.json, validation_report.json, and plots.
5. Select the most robust configuration and rename its config_run.yaml as best_config.yaml for future runs.

---

## Exit Codes
0 — tuning completed successfully
1 — controlled or critical failure (missing config, broken pipeline)

---

## Summary
The hyperparameter tuner provides a fully automated framework for structured experimentation within the Opmed optimization project.
Through the IS_STRESS_TUNE flag, it can switch seamlessly between exploratory and robustness workflows.
Incremental result writing ensures reproducibility and resilience even in multi-hour tuning sessions.
