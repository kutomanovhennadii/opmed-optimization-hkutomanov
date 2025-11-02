# Validator Subsystem

## Purpose
The **Validator** module performs post-solution verification of the generated schedule. It ensures that the solver’s output (`assignments`) is **consistent, legal, and traceable** before being visualized or written to disk.

Validator closes the logical loop in the system pipeline:

    DataLoader → ModelBuilder → Optimizer → Validator → Visualizer → Metrics

The module accepts:
- a list of `Surgery` objects (immutable source truth),
- a list of `SolutionRow` objects (the solver's proposed schedule),
- and a configuration model `Config`.

It produces a structured validation report (`validation_report.json`) and exposes a programmatic API for orchestration.

## Key Design Principles
1. **Single Responsibility** – each validation rule is implemented in its own `_check_*` method.
2. **Determinism** – identical inputs always yield identical results.
3. **Non-intrusive behavior** – the validator never mutates data, only inspects it.
4. **Fail-safe semantics** – even when data are malformed, the validator returns a structured report instead of crashing.

## Main Class: `Validator`

### Constructor
    Validator(assignments: list[SolutionRow], surgeries: list[Surgery], cfg: Config)
Prepares in-memory indexes and initializes report buffers (errors, warnings, checks, metrics).

### Core Lifecycle
    validator = Validator(assignments, surgeries, cfg)
    validator.run_all_checks()
    report = validator.build_report()
    path = validator.save_report(report)

#### run_all_checks()
Executes all validation passes in order:
- `_check_data_integrity()` — verifies field types, unique IDs, matching start/end times.
- `_check_room_overlaps()` — ensures no two surgeries overlap in the same room.
- `_check_anesthetist_overlaps()` — ensures an anesthesiologist does not serve two surgeries simultaneously.
- `_check_buffer_between_rooms()` — enforces a buffer (cfg.buffer hours) when changing rooms.
- `_check_shift_limits()` — ensures each anesthesiologist's shift duration is within [SHIFT_MIN, SHIFT_MAX].
- `_check_surgery_duration_limit()` — validates each surgery duration against allowed limits if enabled.
- `_compute_metrics_and_utilization()` — aggregates runtime metrics, utilization, and derived statistics.

If any critical integrity error is found, subsequent logical checks are skipped, and the report marks those checks as None.

#### build_report()
Returns a dictionary with the structure:
    {
      "timestamp": "...",
      "valid": true,
      "errors": [],
      "warnings": [],
      "metrics": {...},
      "checks": {
        "DataIntegrity": true,
        "RoomOverlap": true,
        "NoOverlap": true,
        "Buffer": true,
        "ShiftLimits": true,
        "DurationLimits": true,
        "Utilization": true
      }
    }

#### save_report()
Writes the report atomically to data/output/validation_report_<timestamp>.json.

### Behavior on Validation Failure
Even if validation fails, the validator returns a complete structured report with `valid = False`. The orchestrator must interpret this flag and decide whether to stop the pipeline or retry optimization.

## Public Facade Function
Convenience entry point:
    from opmed.validator import validate_assignments
    report = validate_assignments(
        assignments,
        surgeries,
        cfg,
        write_report=True,
        out_dir=Path("data/output")
    )
This function instantiates the Validator, executes all checks, collects the report, and optionally writes it to disk. It never raises exceptions for business-level violations—only for malformed inputs (type or structural errors).

## Error Model
All critical errors are represented through `ValidationError` (in opmed.errors):
    class ValidationError(Exception):
        def __init__(self, message: str, source: str, suggested_action: str)

Non-fatal rule violations are accumulated in `self.errors` as structured dictionaries:
    {
      "check": "ShiftLimits",
      "message": "Shift duration outside allowed limits",
      "entities": {"anesthetist_id": "A1", "duration_hours": 13.0},
      "suggested_action": "Rebalance assignments to keep shifts within [SHIFT_MIN, SHIFT_MAX]"
    }
Warnings are stored similarly under `self.warnings`.

## Orchestrator Integration
The orchestrator (in scripts/run.py) uses the validator deterministically as a post-step:
    cfg = load_config(...)
    surgeries = load_surgeries(...)
    bundle = ModelBuilder(cfg, surgeries).build()
    result = Optimizer(cfg).solve(bundle)

    # 1️⃣ Validate
    report = validate_assignments(
        result["assignments"], surgeries, cfg, write_report=True
    )

    # 2️⃣ Decision logic
    if not report["valid"]:
        logger.warning("Validation failed — skipping visualization and export")
        # optionally re-run solver or raise event
    else:
        plot_schedule(result["assignments"], surgeries, cfg, Path("data/output/solution_plot.png"))
        metrics = collect_metrics(result, cfg)
        write_metrics(metrics, Path("data/output"))

Thus, the validator acts as a gatekeeper:
If the schedule is valid → proceed to visualization, metrics, and export.
If invalid → stop and return detailed diagnostics to the orchestrator for recovery or user feedback.

## Output Files
File | Purpose
---- | --------
data/output/validation_report_<timestamp>.json | Structured report with all checks, errors, warnings, and metrics
data/output/solver.log | (written separately by Metrics/Logger) — solver parameters and OR-Tools version
data/output/metrics.json | (written by Metrics subsystem) — numeric summary of utilization and cost

## DoD (Definition of Done)
- pytest -q tests/validator/test_validator.py passes entirely.
- Report contains consistent JSON with valid=True for correct data.
- Orchestrator correctly interprets invalid outputs and halts subsequent modules.
- Coverage of src/opmed/validator/validator.py ≥ 95%.

**Status:** Stable
**Maintainer:** SolverCore team (Validation module)
**Depends on:** opmed.schemas.models, opmed.errors, ADR-008, ARCHITECTURE.md
