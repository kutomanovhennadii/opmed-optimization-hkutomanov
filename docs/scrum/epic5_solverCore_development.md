Epic 5 — SolverCore Development
Goal: Obtain a minimally working prototype: CP-SAT → schedule → valid metrics.
Artifacts: src/opmed/solver_core/{model_builder.py, optimizer.py}, tests/solver_core/test_solvercore.py, data/synthetic/small_surgeries.csv, data/output/metrics.json
DoD: On synthetic data, the solver produces a schedule without overlaps and creates metrics.json.

5.1 (Must) ModelBuilder — CP-SAT model creation

5.1.1 — ModelBuilder class stub
Create class ModelBuilder in model_builder.py.
    class ModelBuilder:
        def __init__(self, cfg: Config, surgeries: list[Surgery]): ...
        def build(self) -> CpSatModelBundle: ...
Define container CpSatModelBundle = dict[str, Any] (model, vars, aux).
Criterion: import possible, test instantiation does not fail.

5.1.2 — Intervals and boolean variables
Implement in build():
IntervalVar — for each operation (start, duration, end).
BoolVar — x[s,a] (anesthesiologist assignment), y[s,r] (room).
Criterion: CpModel is created and all variables are built without errors.

5.1.3 — Constraints
Add:
For each room: NoOverlap(intervals_in_room).
For each anesthesiologist: NoOverlap(intervals_by_anesth).
Inter-room buffer: if room₁ ≠ room₂, start₂ ≥ end₁ + BUFFER.
Shift duration: SHIFT_MIN ≤ duration_a ≤ SHIFT_MAX.
Criterion: model builds without ValueError; len(model.constraints) > 0.

5.1.4 — Test ModelBuilder
tests/solver_core/test_model_builder.py: create 3–4 synthetic operations; check the number of variables and constraints; ensure at least one NoOverlap exists.
Criterion: pytest tests/solver_core/test_model_builder.py passes.

5.2 (Must) Objective function — piecewise cost

5.2.1 — Implement cost calculation
In model_builder.py: add duration_a = end_a – start_a; cost[a] = max(SHIFT_MIN, duration_a) + 0.5 × max(0, duration_a – 9) using AddMaxEquality.
Criterion: model has a linear objective without errors.

5.2.2 — Add objective to model
model.Minimize(sum(cost[a])).
Criterion: objective present (model.Proto().objective not empty).

5.2.3 — Test objective
In test_model_builder.py: check that the objective exists and coefficients are positive (>0).
Criterion: test passes.

5.3 (Must) Optimizer — solver execution

5.3.1 — Create Optimizer class
optimizer.py:
    class Optimizer:
        def __init__(self, cfg: Config): ...
        def solve(self, bundle: CpSatModelBundle) -> SolveResult: ...
where SolveResult = dict[str, Any] (assignment, status, objective, runtime).
Criterion: class imports successfully.

5.3.2 — Configure CP-SAT parameters
Apply from cfg: num_workers, max_time_in_seconds, search_branching, random_seed. solver.parameters.log_search_progress = True.
Criterion: parameters apply without errors.

5.3.3 — Extract results
When status in (FEASIBLE, OPTIMAL): collect assignments x[s,a], y[s,r]; compute objective_value, runtime; return SolveResult.
Criterion: on small dataset, valid result obtained.

5.3.4 — Test Optimizer
tests/solver_core/test_optimizer.py: build mini-model (3 operations, 2 rooms); solve; check status in (FEASIBLE, OPTIMAL) and presence of objective_value.
Criterion: test completes in ≤ 5 seconds.

5.4 (Should) Determinism and logging

5.4.1 — Save parameters and version
In Optimizer.solve: save seed, ORTOOLS_VERSION, parameters; log to data/output/solver.log.
Criterion: file created, contains version and seed.

5.4.2 — Save metrics
After solving: metrics = {"objective": obj, "runtime": time, "status": status}; write to data/output/metrics.json.
Criterion: file exists, valid JSON.

5.4.3 — Test metrics
Verify that metrics.json is created and contains required keys.
Criterion: pytest passes.

5.5 (Could) LNS/portfolio mode

5.5.1 — Parametric mode
Add to cfg: "solver_mode": "portfolio" or "lns". For lns — set use_lns=True and mix random_seed.
Criterion: two modes logged separately.

5.5.2 — Test mode switching
Verify: with different modes, parameters change but model remains valid.
Criterion: both runs FEASIBLE.

5.6 (Must) Integration test “model → solver → metrics”

5.6.1 — Synthetic data
data/synthetic/small_surgeries.csv: 5–6 operations, varied times.
Criterion: valid CSV for DataLoader.

5.6.2 — End-to-end test
tests/solver_core/test_end_to_end.py: load CSV; build model; run Optimizer; verify that metrics.json exists and utilization > 0.
Criterion: full cycle completes without exceptions.
