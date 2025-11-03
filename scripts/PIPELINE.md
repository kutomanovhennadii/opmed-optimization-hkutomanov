# Opmed Optimization Pipeline — User & Tuner Guide

**Module:** `scripts/run.py`
**Primary entrypoint:** `run_pipeline(config_path, input_path, output_dir)`

---

## 1. Purpose
The Opmed Optimization Pipeline orchestrates the full lifecycle from input data to validated output artifacts. It transforms static surgery schedules into optimized anesthesiologist and room allocations, verifies compliance with all operational constraints, and emits structured results for analysis, visualization, and metric tracking.

---

## 2. Overview
    +-------------------+      +------------------+      +----------------+      +----------------+
    |  ConfigLoader     | -->  |  SurgeriesLoader | -->  |  ModelBuilder  | -->  |   Optimizer    |
    +-------------------+      +------------------+      +----------------+      +----------------+
                                                                         ↓
                                                 +-----------------------------------------------+
                                                 |             Validator & Visualizer            |
                                                 +-----------------------------------------------+
                                                                         ↓
                                                       +---------------------------------+
                                                       |      Metrics & Exporters        |
                                                       +---------------------------------+

---

## 3. Execution Flow

### 3.1 For Users (Analysts / Clients)
Typical usage:
    poetry run python scripts/run.py --config config/config.yaml --input data/input/surgeries.csv --output data/output/

The pipeline automatically performs these steps:

1. **Load Configuration**
   Reads YAML configuration (`ConfigLoader`) with business rules, solver settings, and artifact policies.

2. **Load Input Surgeries**
   Validates CSV structure, converts times to UTC ISO-8601 datetimes, and builds structured `Surgery` objects.

3. **Model Building**
   The `ModelBuilder` constructs the CP-SAT model with interval and boolean variables:
   - `x[s,a]` — surgery–anesthesiologist assignments
   - `y[s,r]` — surgery–room assignments
   - Interval and NoOverlap constraints per anesthesiologist and per room
   - Piecewise-linear cost model (base + overtime)

4. **Solving**
   The `Optimizer` executes the CP-SAT solver with configured parameters (multi-threaded search, max_time, seed).
   Solver logs are written to `data/output/solver.log`.

5. **Validation**
   The `Validator` runs logical and temporal checks:
   DataIntegrity, RoomOverlap, NoOverlap, Buffer, ShiftLimits, DurationLimits, Utilization.
   The result is serialized to `validation_report.json`.

6. **Visualization**
   If the solution is valid, a visual Gantt-style chart is produced as `solution_plot.png`.

7. **Metrics & Export**
   - Metrics summary written to `metrics.json`
   - Canonical schedule serialized to `solution.csv`
   - All artifacts grouped in the output directory

---

## 4. Output Artifacts
| Artifact | Path | Description |
|-----------|------|-------------|
| `validation_report.json` | data/output/ | Full structured validation report (errors, warnings, metrics). |
| `solution.csv` | data/output/ | Canonical schedule with `surgery_id,start_time,end_time,anesthetist_id,room_id`. |
| `solution_plot.png` | data/output/ | Colored Gantt chart (x=time, y=anesthesiologist). |
| `metrics.json` | data/output/ | Aggregated performance metrics and solver info. |
| `solver.log` | data/output/ | Raw OR-Tools output and timing summary. |

---

## 5. Validation Semantics
- **Critical checks:** DataIntegrity, RoomOverlap, NoOverlap, DurationLimits → if any fail, `valid=false`.
- **Soft checks:** Buffer, ShiftLimits, Utilization → only warnings, do not affect overall validity.
A solution with small buffer gaps or short shifts is considered valid though suboptimal.

---

## 6. For Tuners (Developers / Researchers)

### 6.1 Adjustable Parameters
All optimization levers live in `config/config.yaml`:
    shift_min: 5.0
    shift_max: 12.0
    shift_overtime: 9.0
    overtime_multiplier: 1.5
    buffer: 0.25
    activation_penalty: 5.0
    rooms_max: 20
    solver:
      max_time_in_seconds: 60
      num_workers: 8
      random_seed: 42
      log_to_stdout: true

Key tunable levers:
- `activation_penalty` — regularizes the number of active anesthesiologists.
- `buffer` — enforces transition safety between rooms.
- `shift_min`, `shift_max`, `shift_overtime` — control feasible workload intervals.
- `utilization_target` — used by validator to mark underutilized solutions.

### 6.2 Optimization Target
Objective function (simplified):
    total_cost = Σ_a [ max(shift_min, duration_a)
                     + 0.5 * max(0, duration_a - shift_overtime) ]
                 + activation_penalty * Σ active[a]
                 + activation_penalty * Σ room_used[r]

The solver minimizes `total_cost`.
Utilization is then defined as:
    utilization = (Σ surgery_durations) / total_cost

### 6.3 Failure Modes & Debugging
- If `status = UNKNOWN` or `MODEL_INVALID`: check configuration bounds or over-constrained model.
- If `validation_report.valid = false`: open `validation_report.json` to identify failing checks.
- If no `solution_plot.png` appears: ensure Validator deems the solution valid and that `visualization.save_plot=true`.

---

## 7. Reproducibility
Every run records:
- OR-Tools version
- Solver parameters (num_workers, seed, branching)
- Config snapshot (`config_snapshot_<ts>.json`)
- Metrics and runtime statistics
These ensure deterministic reruns and auditability of all experiments.

---

## 8. Exit Criteria
The pipeline completes successfully when:
- `validation_report.valid == true`
- All artifacts are written to the output directory
- Utilization ≥ 0.8

Otherwise, the pipeline terminates gracefully with:
WARNING: Validation failed (valid=False). Visualization will be skipped.
    while still providing metrics and partial artifacts for debugging.

---

## 9. Practical Notes
- The entire system is CP-SAT–based; small parameter changes can drastically alter feasibility.
- Always inspect both `validation_report.json` and `solver.log` together — they form the ground truth of correctness and efficiency.
- For tuning experiments, use distinct output directories per run to avoid artifact overwriting.

---

*Document version: 2025-11-03 — maintained by Opmed Optimization Core Team.*
