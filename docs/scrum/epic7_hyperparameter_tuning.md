Epic 7 — Synthetic Data and Hyperparameter Tuning
Goal: Demonstrate realism, run quick config tuning, record the report, and select best_config.yaml.
Artifacts: data/input/synthetic_*.csv, configs/{config.yaml,tune_grid.yaml,best_config.yaml}, data/output/tune/*, docs/RESULTS_tuning.md.
Reference documents:
docs/ARCHITECTURE/ARCHITECTURE.md — contract of run() and metrics format.
docs/ADRs/ADR-004-config-management.md — structure of config.yaml.
docs/ADRs/ADR-006-logging-metrics.md — logging and metrics rules.
docs/scrum/epic2_theoretical_framework/Theoretical_Model.md — definitions of Utilization and Cost.

7.1 (Must) Synthetic Data — Realism and Metric Validation (without developing a generator)

Task 7.1.1 — Dataset Passport and Sanity Checks
Input: 3 CSV datasets, Theoretical_Model.md (metrics), ARCHITECTURE.md (input format).
Actions:
Create script scripts/sanity_synth.py, which for each CSV computes:
number of surgeries, duration distributions (mean/median/quantiles), daily windows, and preliminary load (approximate upper Utilization per room).
Save the summary to data/output/sanity_synth_summary.csv and append a short Markdown “Datasets” section in docs/RESULTS_tuning.md.
Output: sanity_synth_summary.csv, updated docs/RESULTS_tuning.md.
DoD: script runs in under 10s; each dataset has a summary row.

Task 7.1.2 — Quick e2e Run on Each Dataset
Input: scripts/run.py, configs/config.yaml.
Actions:
Run the full pipeline on three CSVs using the default config.
Aggregate key metrics (total_cost, utilization, runtime_seconds, status) into data/output/tune/baseline_metrics.csv.
Output: baseline_metrics.csv + links in docs/RESULTS_tuning.md.
DoD: all three runs FEASIBLE/OPTIMAL; table populated.

7.2 (Must) Dataset Typing and Usage Profiles

Task 7.2.1 — Naming and Profiles
Input: results of 7.1, ARCHITECTURE.md.
Actions:
Fix correspondences:
small → synthetic_1d_1r.csv
medium → synthetic_2d_2r.csv
stress → synthetic_3d_8r.csv
Describe a “usage profile” for each dataset (smoke, demo, stress-limit).
Add section “Dataset Profiles” to docs/RESULTS_tuning.md.
Output: updated docs/RESULTS_tuning.md.
DoD: each profile described in 3–6 sentences; linked to baseline metrics.

Task 7.2.2 — Makefile Aliases (Convenience Targets)
Input: Makefile, scripts/run.py.
Actions:
Add targets: run-small, run-medium, run-stress — each calls scripts/run.py with the respective input and common configs/config.yaml.
Output: working Makefile targets.
DoD: make run-small / run-medium / run-stress complete successfully.

7.3 (Should) Mini Tuning Loop (workers, time_limit, branching)

Task 7.3.1 — Define Parameter Grid
Input: ADR-004-config-management.md (solver keys), ARCHITECTURE.md.
Actions:
Create configs/tune_grid.yaml, for example:
    datasets:
      - data/input/synthetic_1d_1r.csv
      - data/input/synthetic_2d_2r.csv
      - data/input/synthetic_3d_8r.csv
    grid:
      num_workers: [1, 4, 8]
      max_time_in_seconds: [5, 15, 30]
      search_branching: ["AUTOMATIC", "FIXED_SEARCH", "PORTFOLIO"]
      random_seed: [42]
    repeats: 1
    objective: "total_cost"  # primary
Output: configs/tune_grid.yaml.
DoD: YAML is valid and consistent with code.

Task 7.3.2 — Implement scripts/tune.py
Input: scripts/run.py (as orchestrator reference), structures from ARCHITECTURE.md.
Actions:
Parse tune_grid.yaml and iterate over all combinations, for each:
run pipeline (model → solver → validation → metrics)
append result to data/output/tune/tuning_results.csv.
Row format: dataset, num_workers, time_limit, search_branching, seed, status, total_cost, utilization, runtime_seconds, timestamp.
Output: scripts/tune.py, data/output/tune/tuning_results.csv.
DoD: runs without errors on all combinations; completes small dataset in minutes.
Mini-test: tests/tuning/test_tune_smoke.py — one small run (1–2 combos) → tuning_results.csv exists and has ≥1 row.

Task 7.3.3 — Select Best Config and Export best_config.yaml
Input: tuning_results.csv, objective criterion from tune_grid.yaml (default total_cost, tiebreak by runtime_seconds).
Actions:
Write scripts/select_best_config.py: parse tuning_results.csv, aggregate per dataset (or globally), and save configs/best_config.yaml with solver parameter fields.
In docs/RESULTS_tuning.md create a comparison table (top 5 results) and short summary.
Output: configs/best_config.yaml, updated docs/RESULTS_tuning.md.
DoD: best_config.yaml reproducible; report explains selection.

Task 7.3.4 — Makefile Target “tune”
Input: current Makefile.
Actions:
Update targets:
    make tune      # runs scripts/tune.py with configs/tune_grid.yaml
    make tune-best # runs select_best_config.py and prints best_config.yaml path
Output: updated Makefile.
DoD: both targets run without manual parameters.
