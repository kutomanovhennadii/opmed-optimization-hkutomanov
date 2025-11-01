Epic 6 — Subsystems: DataLoader, Validator, Visualizer, Metrics
Goal: Close the loop “data → solution → validation → visualization → metrics” on top of the completed SolverCore (Epic 5).
Global reference documents (read at epic start): docs/scrum/epic1_problem_formulation/T1.1.5_Logical_Interaction_Scheme.md — logical flow scheme; docs/scrum/epic2_theoretical_framework/Theoretical_Model.md — formalization of constraints/metrics; docs/ARCHITECTURE/ARCHITECTURE.md — module interfaces (from Epic 3); docs/ADRs/ADR-004-config-management.md, ADR-005-io-formats.md, ADR-006-logging-metrics.md, ADR-008-errors-validation.md.

6.1 (Must) DataLoader — input reading and normalization

6.1.1 — Configuration loading
Read before starting: ADR-004-config-management.md, section Config in ARCHITECTURE.md.
Code: src/opmed/dataloader/loader.py
load_config(path: Path) -> Config (Pydantic model), validate required fields, apply defaults.
Output: working function handling errors (raises ConfigError).
DoD: invalid YAML → clear message; valid → returns Config.

6.1.2 — Surgery loading (CSV → internal format)
Read: ADR-005-io-formats.md, Surgery/TimeUnit in ARCHITECTURE.md, Time in Theoretical_Model.md.
Code: src/opmed/dataloader/loader.py
load_surgeries(path: Path, time_unit: int) -> list[Surgery]
Rules: start < end, duration > 0, sorted by start, converted to integer ticks.
Output: list of Surgery (Pydantic).
DoD: bad rows or empty fields → DataError with row number.

6.1.3 — DataLoader tests
Read: ADR-008-errors-validation.md (error messages).
Tests: tests/dataloader/test_loader.py
Positive: valid CSV/YAML → correct models.
Negative: start >= end, empty surgery_id, malformed YAML.
DoD: pytest -q tests/dataloader/test_loader.py passes.

6.2 (Must) Validator — schedule correctness check

6.2.1 — Constraint validation (rooms, anesthesiologists, buffers, shifts)
Read: Theoretical_Model.md (Constraints), ARCHITECTURE.md (Validator interface), ADR-008-errors-validation.md.
Code: src/opmed/validator/validator.py
validate_assignments(assignments, surgeries, cfg) -> ValidationReport
Checks:
No overlaps per room.
No overlaps per anesthesiologist.
Inter-room buffer respected (BUFFER, only if room₁ ≠ room₂).
Shift duration in [SHIFT_MIN, SHIFT_MAX].
(Optional) Utilization ≥ cfg.utilization_target — as warning.
Output: ValidationReport (dict with valid: bool, errors: [], warnings: [], metrics: {...}), written to data/output/validation_report.json.
DoD: on any error, report lists exact IDs of conflicting operations.

6.2.2 — Validator tests
Read: ADR-005-io-formats.md (IDs), Theoretical_Model.md (BUFFER/SHIFT).
Tests: tests/validator/test_validator.py
Scenario: explicit time conflict in one room → valid=False, 1 error.
Scenario: room switch without buffer → violation recorded.
Shift longer than MAX → error; shorter than MIN → error.
DoD: tests pass, diagnostics have no vague messages.

6.3 (Should) Visualizer — schedule diagram

6.3.1 — Schedule rendering (anesthesiologists on Y, time on X, color = rooms)
Read: ARCHITECTURE.md (Visualizer interface), ADR-005-io-formats.md (solution columns), style from docs/CODESTYLE.md if available.
Code: src/opmed/visualizer/plot.py
plot_schedule(assignments, surgeries, cfg, out_path: Path) -> Path
Use matplotlib (no seaborn). DPI ~150, room legend, time labels.
Output: data/output/solution_plot.png.
DoD: readable image, distinct room colors, labeled axes.

6.3.2 — Visualizer test (smoke)
Read: ARCHITECTURE.md (assignments format).
Test: tests/visualizer/test_plot.py
Generate minimal schedule in memory and plot.
Check PNG exists and size > 0 bytes.
DoD: test passes, no GUI backend (use Agg by default).

6.4 (Must) Metrics & Logger — metric and log collection

6.4.1 — Metric collection
Read: Theoretical_Model.md (Utilization, Cost), ADR-006-logging-metrics.md (keys).
Code: src/opmed/metrics/metrics.py
collect_metrics(result: SolveResult, cfg: Config) -> dict
Keys: total_cost, utilization, runtime_seconds, status, num_anesthetists, num_rooms_used, num_surgeries.
Utilization = Σ(duration_surgeries)/Σ(cost_anesthesiologists).
Output: dict with metrics.
DoD: correct types, no NaN/None values.

6.4.2 — Writing metrics and logs
Read: ADR-006-logging-metrics.md.
Code: src/opmed/metrics/logger.py
write_metrics(metrics: dict, out_dir: Path) -> Path → data/output/metrics.json
write_solver_log(solver, cfg, out_dir: Path) -> Path → data/output/solver.log (OR-Tools version, seed, parameters).
Output: metrics.json, solver.log.
DoD: both writes atomic, UTF-8, reruns overwrite files.

6.4.3 — Metrics & Logger tests
Read: ARCHITECTURE.md (SolveResult format).
Test: tests/metrics/test_metrics_logger.py
Simulate SolveResult and check field correctness; write files; read back and compare keys.
DoD: test passes, JSON valid.

6.5 (Could) Solution export to solution.csv (standard format)

6.5.1 — Solution export
Read: ADR-005-io-formats.md (column specification).
Code: add to src/opmed/metrics/metrics.py or create src/opmed/metrics/export.py
write_solution_csv(assignments, out_path: Path) -> Path
Columns: surgery_id, start_time, end_time, anesthetist_id, room_id (ISO-8601 times).
Output: data/output/solution.csv.
DoD: CSV readable by pandas.read_csv with default parameters.

6.5.2 — Export test
Test: tests/metrics/test_export_solution.py
On a toy assignments, check column correctness and row count.
DoD: test passes.

6.6 (Must) Mini-integration: run → validate → visualize → metrics

6.6.1 — Orchestrator script (stub update)
Read: ARCHITECTURE.md (sequence run), T1.1.5 Logical Scheme.
Code: scripts/run.py
Pipeline:
    cfg = load_config(...)
    surgeries = load_surgeries(...)
    bundle = ModelBuilder(cfg, surgeries).build()
    res = Optimizer(cfg).solve(bundle)
    report = validate_assignments(res["assignments"], surgeries, cfg) → validation_report.json
    plot_schedule(..., out_path="data/output/solution_plot.png")
    metrics = collect_metrics(res, cfg) → metrics.json
    write_solution_csv(res["assignments"], "data/output/solution.csv")
Output: complete artifact set in data/output/.
DoD: script runs on data/synthetic/small_surgeries.csv in <10 sec.

6.6.2 — Integration test (smoke)
Read: Theoretical_Model.md (validity), ARCHITECTURE.md (contracts).
Test: tests/test_end_to_end_pipeline.py
Run via module functions (no subprocess): assemble pipeline in test on mini-CSV; check presence of validation_report.json, metrics.json, solution_plot.png, solution.csv.
DoD: test passes; validation_report.valid not False.
