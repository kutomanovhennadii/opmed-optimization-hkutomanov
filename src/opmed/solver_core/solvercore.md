Opmed SolverCore

Purpose
SolverCore implements the complete cycle of building, solving, and saving results for the optimization task of allocating anesthesiologists and operating rooms. It serves as the core that unifies three solver modules and one model-building module. The architecture ensures determinism, traceability, and readiness for subsequent hyperparameter optimization (via the grid tuner).

Modular Structure
src/opmed/solver_core/
├── model_builder.py     # generation of CP-SAT model
├── optimizer.py         # facade API (entry point)
├── solver_runner.py     # configuration and execution of CP-SAT solver
└── result_store.py      # saving artifacts and metrics

1. model_builder.py — model construction
Class ModelBuilder
Creates the CP-SAT mathematical model from input data (Config, list[Surgery]).

Main steps:
_init_variable_groups() — initializes containers x, y, interval, active.
_create_intervals() — fixed time intervals of surgeries (in UTC).
_create_boolean_vars() — boolean assignment variables:
x[s,a] — surgery s performed by anesthesiologist a;
y[s,r] — surgery s takes place in room r.
_add_constraints() — structural constraints:
NoOverlap for rooms and anesthesiologists,
inter-room transition buffer,
shift duration bounds (minimum/maximum hours).
_add_objective_piecewise_cost() — piecewise objective function:
cost[a] = max(SHIFT_MIN, duration_a) + 0.5 × max(0, duration_a − SHIFT_OVERTIME)
soft minimization of the number of active anesthesiologists (+ Σ active[a]).
Output:
CpSatModelBundle = {"model", "vars", "aux", "surgeries"} — ready-to-solve model, variable dictionaries, and time metadata.

2. optimizer.py — facade layer
Class Optimizer
Single entry point for external code and tests. Orchestrates the interaction of SolverRunner and ResultStore.

Main logic:
solve(bundle: CpSatModelBundle) -> SolveResult
calls SolverRunner to solve the model;
passes the result to ResultStore for artifact saving;
returns a summary dictionary:
{
    "status": str,
    "objective": float,
    "runtime": float,
    "assignment": {"x": list[(s,a)], "y": list[(s,r)]},
    "solution_path": str | None
}
Supports determinism by fixing the seed and solver parameters. Logs OR-Tools version and key parameters before execution.

3. solver_runner.py — configuration and execution of CP-SAT
Class SolverRunner
Encapsulates interaction with ortools.sat.python.cp_model.CpSolver.

Main functions:
_make_solver() — creates CpSolver, enables log_search_progress.
_apply_parameters() — applies cfg.solver settings:
num_search_workers, max_time_in_seconds, random_seed, search_branching.
_solve_model() — calls solver.Solve(model) and returns status.
_extract_assignments() — reads BoolVar values (0/1) and returns lists (s,a) and (s,r).
_status_name() — maps OR-Tools numeric codes to human-readable statuses.
Result is returned to Optimizer as SolveResult with fields: status_code, objective_value, runtime, assignment.

4. result_store.py — saving artifacts
Class ResultStore
Handles creation of reproducible output files and logs. Receives SolveResult, cfg, solver, bundle.

Main methods:
_write_solution() — CSV file solution_<exp?>_<timestamp>.csv (surgery_id, anesthetist_id, room_id, start_time, end_time).
_write_solver_log() — detailed text report solver_<exp?>_<timestamp>.log including OR-Tools version, seed, parameters, ResponseStats.
_write_metrics() — JSON summary metrics_<exp?>_<timestamp>.json (status, objective, runtime, solver parameters).
_log_solver_info() — console INFO header of the run.
_write_config_snapshot() (optional) — save current cfg to config_snapshot_*.json.
Control flags:
cfg.metrics.save_metrics / cfg.metrics.save_solver_log
self.write_artifacts — global switch for enabling/disabling saving.
All files are named by UTC timestamp and, if available, experiment name (cfg.experiment.name), ensuring uniqueness and preventing overwrite.

Module Interaction
        ┌────────────────────┐
        │  ModelBuilder      │
        │  build()           │
        └────────┬───────────┘
                 │ CpSatModelBundle
                 ▼
        ┌────────────────────┐
        │  Optimizer         │
        │  solve(bundle)     │
        └────────┬───────────┘
                 │ delegates
                 ▼
        ┌────────────────────┐
        │  SolverRunner      │
        │  configure+Solve() │
        └────────┬───────────┘
                 │ results
                 ▼
        ┌────────────────────┐
        │  ResultStore       │
        │  write_*() logs    │
        └────────────────────┘

Usage
In production flow:
    builder = ModelBuilder(cfg, surgeries)
    bundle = builder.build()
    opt = Optimizer(cfg)
    result = opt.solve(bundle)

In tuning mode:
Optimizer is used inside parameter sweeps (tune_grid.yaml), where ResultStore captures metrics for each configuration.

Summary
SolverCore is a self-contained, reproducible optimization layer of Opmed: from constructing the CP-SAT model to writing metrics and logs. Each module has a single responsibility, and their interaction follows the principle Builder → Runner → Store.
