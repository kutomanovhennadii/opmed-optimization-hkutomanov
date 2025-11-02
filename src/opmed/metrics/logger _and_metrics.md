# Opmed Metrics & Logger — User and Orchestrator Guide

**Modules:**
- src/opmed/metrics/metrics.py — collection and computation of metrics (cost, utilization, runtime)
- src/opmed/metrics/logger.py — writing artifacts: metrics.json, solver.log

---

## 1. Purpose of the Metrics subsystem
The subsystem handles the final stage after solving the optimization task:
> collect metrics, record solver parameters, and save all outputs as stable files.

It is used by:
- **Orchestrator** — automatically, after each computation.
- **User manually** — for analyzing results of a local run.

---

## 2. Files created by the subsystem

| File | Format | Purpose |
|------|---------|----------|
| metrics.json | JSON | Final solution metrics: cost, utilization, runtime, etc. |
| solver.log | text | Debug information about OR-Tools parameters and execution. |

Both files are written atomically — first to a temporary file, then replaced to avoid data corruption.

---

## 3. Usage in the pipeline (for orchestrator)

After completing the `build → solve → validate` cycle, the orchestrator calls:

    from pathlib import Path
    from opmed.metrics import metrics, logger

    result = Optimizer(cfg).solve(bundle)

    if report["valid"]:
        # 1. Collect metrics
        summary = metrics.collect_metrics(result, cfg)

        # 2. Write metrics and log
        logger.write_metrics(summary, Path(cfg.output_dir))
        logger.write_solver_log(result["solver"], cfg, Path(cfg.output_dir))

Result:

    data/output/
    ├── metrics.json
    └── solver.log

---

## 4. Manual usage (for user)

The user can call the same functions in an interactive Python or Jupyter environment:

    from pathlib import Path
    from opmed.metrics.metrics import collect_metrics
    from opmed.metrics.logger import write_metrics, write_solver_log

    # Collect metrics after solver execution
    summary = collect_metrics(result, cfg)

    # Save artifacts
    write_metrics(summary, Path("data/output"))
    write_solver_log(result["solver"], cfg, Path("data/output"))

    print("Artifacts saved in data/output/")

---

## 5. Module metrics.py: metrics collection

Function: collect_metrics(result: SolveResult, cfg: Config) -> dict
Computes core indicators from solver results:

| Key | Description |
|-----|--------------|
| total_cost | Total shift cost |
| utilization | Utilization (sum of surgery durations / payable time) |
| runtime_seconds | Solver runtime |
| status | Solver status (OPTIMAL, FEASIBLE, etc.) |
| num_anesthetists | Number of anesthesiologists used |
| num_rooms_used | Number of operating rooms actually used |
| num_surgeries | Total number of surgeries |

Features:
- Validates absence of NaN, None.
- Returns a regular dict ready for JSON serialization.
- Raises DataError on computation issues.

Example:

    from opmed.metrics.metrics import collect_metrics
    metrics = collect_metrics(result, cfg)
    print(metrics)

Example output:

    {
      "total_cost": 185.0,
      "utilization": 0.83,
      "runtime_seconds": 4.21,
      "status": "OPTIMAL",
      "num_anesthetists": 14,
      "num_rooms_used": 8,
      "num_surgeries": 70
    }

---

## 6. Module logger.py: artifact writing

### 6.1. write_metrics(metrics: dict, out_dir: Path) -> Path
- Ensures the argument is a dict.
- Serializes to valid JSON (UTF-8).
- Writes metrics.json atomically.
- Overwrites on each run.

Errors:

| Error | Cause | Solution |
|--------|--------|-----------|
| DataError("metrics must be a dict") | Non-dict argument passed | Pass a regular dict |
| DataError("metrics not JSON-serializable") | Invalid types (NaN, None, complex) | Convert values to primitive types |

Example:

    write_metrics(metrics, Path("data/output"))

---

### 6.2. write_solver_log(solver, cfg, out_dir: Path) -> Path
Creates solver.log with the following blocks:

    [2025-11-02 17:00:00] INFO Starting CP-SAT solver
    [2025-11-02 17:00:00] INFO Parameters: workers=4, time_limit=60s, seed=0, search_branching=AUTOMATIC
    [2025-11-02 17:00:00] INFO OR-Tools version: 9.10.4067
    [2025-11-02 17:00:01] INFO ResponseStats snippet: CpSolverStatus = OPTIMAL
    CpSolverStatus = OPTIMAL
    ObjectiveValue = 185.0
    WallTime = 1.04s

If the solver lacks a ResponseStats() method, the log contains:

    INFO Solver finished (no ResponseStats available)

Errors:

| Error | Cause | Solution |
|--------|--------|-----------|
| DataError("atomic write failed") | Write error (no permissions, disk full) | Check permissions and disk space |

---

### 6.3. _atomic_write_text(path, text, encoding="utf-8")
Internal atomic writing function:
- Creates a temporary file via tempfile.mkstemp.
- Writes the content there.
- Replaces the original via os.replace().
This ensures that if a crash or disk failure occurs, the file will not be corrupted.

---

## 7. User scenarios

### 7.1. Checking artifacts after computation
    cat data/output/metrics.json
    cat data/output/solver.log

### 7.2. Manual re-write
The user can recreate artifacts from saved results:

    from opmed.metrics import metrics, logger
    import json

    res = json.load(open("data/output/solution.json"))
    summary = metrics.collect_metrics(res, cfg)
    logger.write_metrics(summary, Path("data/output"))

---

## 8. Integration with CI/CD and MLflow
metrics.json is read by the build system for reporting.
solver.log is attached to MLflow artifacts for traceability.
The orchestrator must ensure both functions complete without exceptions.
In case of DataError, it should issue a warning and finish the pipeline gracefully.

---

## 9. Troubleshooting

| Symptom | Possible cause | Solution |
|----------|----------------|-----------|
| metrics.json not created | out_dir does not exist | Check cfg.output_dir path |
| Empty solver.log | Solver does not provide ResponseStats() | Acceptable; log still records header |
| DataError exception | Serialization or write error | Check value types and directory permissions |

---

## 10. Definition of Done (DoD)
✅ metrics.json contains correct numeric values.
✅ solver.log is readable and includes solver parameters.
✅ Re-run safely overwrites files.
✅ Works identically for orchestrator and manual usage.
