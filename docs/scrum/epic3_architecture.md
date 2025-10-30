🧭 Epic 3 — Python/OR-Tools Architecture (Theory → Contracts)



\## 1. Goal

To finalize the \*\*architecture and interfaces\*\* of the Opmed optimization system so that development proceeds rapidly and consistently, with no redesign required.  

All components — from data loading to solver orchestration — must be formally defined and traceable to \*\*T1.1.5 (Logical Interaction Scheme)\*\* and \*\*Theoretical\_Model.md\*\*.



---



\## 2. Artifacts

\- \*\*ARCHITECTURE.md\*\* — main system architecture document.  

\- \*\*docs/schemas.md\*\* — data and interface schemas.  

\- \*\*ADRs/\*\* — Architectural Decision Records (global repository in project root).  

\- \*\*/docs/diagrams/\*\* — system diagrams (context, container, dataflow, sequence).  



---



\## 3. Global Definition of Done (DoD)

\- Architecture is fully aligned with theoretical model and solver logic.  

\- All module interfaces are fixed, typed, and validated.  

\- No undefined or “grey” zones remain in module boundaries.  

\- The structure supports reproducibility, logging, validation, and future extensions.



---



\## 4. Structure of the Epic



\### 3.1 (Must) ADR Decisions



\*\*3.1.1 — Initialize ADR Registry and Template\*\*  

Create `/ADRs/` folder at repository root, add `\_TEMPLATE.md` and `README.md`.  

Each ADR includes: \*\*Context, Decision, Alternatives, Consequences, Status\*\*.



\*\*3.1.2 — ADR-001: Solver Choice (CP-SAT vs MILP/CP/SMT)\*\*  

Formal justification for choosing CP-SAT to handle interval constraints, Boolean logic, and piecewise-linear costs.  

Reject MILP (time discretization overhead), classical CP (no hybrid logic), and SMT (scalability issues).



\*\*3.1.3 — ADR-002: Time Representation (Δt = 5 min, integer scale)\*\*  

Adopt TIME\_UNIT = 5 minutes, store timestamps as integer ticks, define I/O conversion formulas, and ensure rounding errors ≤ 1%.



\*\*3.1.4 — ADR-003: Module Boundaries and Directory Structure\*\*  

Fix Python package layout:



opmed/

├── dataloader/

├── solver\_core/

├── validator/

├── visualizer/

├── metrics/

configs/

data/{input,output}/

Include a draft container diagram and table of module responsibilities.



\*\*3.1.5 — ADR-004: Configuration Management (YAML + Pydantic)\*\*  

Define structure of `config.yaml`, required and optional keys, Pydantic models for validation, and default values for all solver parameters.



\*\*3.1.6 — ADR-005: Data Formats (surgeries.csv, solution.csv)\*\*  

Specify columns, data types, time zones, and null-value handling.  

Provide two format tables and examples of valid rows.



\*\*3.1.7 — ADR-006: Logging and Metrics (JSONL + metrics.json)\*\*  

Describe solver log structure: seed, OR-Tools version, parameters, and output metrics schema (`metrics.json`).



\*\*3.1.8 — ADR-007: Reproducibility (seed, versions, determinism)\*\*  

Define policy for seed fixation, dependency pinning, dataset hash logging, and reproducibility checklist.



\*\*3.1.9 — ADR-008: Error Handling and Input Validation\*\*  

List error classes: `InputError`, `ConfigError`, `ModelBuildError`, `SolveError`.  

Provide mapping: error type → source → message → action.



---



\### 3.2 (Must) Interface Contracts



\*\*3.2.1 — Data Schemas (Pydantic):\*\*  

Define models `Surgery`, `Config`, and `SolutionRow`.  

All fields from theoretical formulation are fixed with explicit TZ/Δt conversion rules.



3.2.2 — DataLoader Interface

Signatures:

load\_config(path: Path) -> Config

load\_surgeries(path: Path, time\_unit: int) -> list\[Surgery]

Contracts: guarantees sorting and normalization to integer time ticks (Δt). Output: ARCHITECTURE.md (API specification). Criterion: pre- and postconditions defined, error cases listed.



3.2.3 — ModelBuilder (SolverCore) Interface

Signatures:

build\_model(surgeries: list\[Surgery], cfg: Config) -> CpSatModelBundle

where CpSatModelBundle = {model, vars, aux}

Contracts: explicitly lists created variables (IntervalVar/BoolVar) and invariants. Output: ARCHITECTURE.md. Criterion: all theoretical constraints are enumerated and mapped.



3.2.4 — Optimizer Interface

Signatures:

solve(bundle: CpSatModelBundle, cfg: Config) -> SolveResult

SolveResult = {status, objective, assignments, logs, metrics}

Contracts: defines the exact content of metrics/logs and status codes. Output: ARCHITECTURE.md. Criterion: status automaton covers INFEASIBLE/OPTIMAL/FEASIBLE/UNKNOWN.



3.2.5 — Validator Interface

Signatures:

validate\_assignments(assignments, surgeries, cfg) -> ValidationReport

Contracts: full checklist (NoOverlap, BUFFER, SHIFT\_MIN/MAX, Utilization). Output: ARCHITECTURE.md. Criterion: validation\_report.json schema fixed.



3.2.6 — Visualizer Interface

Signatures:

plot\_schedule(assignments, surgeries, cfg, out\_path: Path) -> Path

Contracts: axes/legend/colors by room, DPI/size constraints. Output: ARCHITECTURE.md. Criterion: guarantees PNG is saved.



3.2.7 — Metrics \& Logger Interface

Signatures:

collect\_metrics(result: SolveResult, cfg: Config) -> MetricsDict

write\_metrics(metrics: dict, out\_path: Path) -> Path

Contracts: keys include total\_cost, utilization, runtime, num\_anesthetists. Output: ARCHITECTURE.md. Criterion: format aligned with ADRs/ADR-006.



3.2.8 — Orchestration Interface (run.py)

Signature:

run(config\_path: Path, surgeries\_path: Path, output\_dir: Path) -> RunArtifacts

Contracts: declares output artifacts (solution.csv, metrics.json, solver.log, solution\_plot.png, validation\_report.json). Output: ARCHITECTURE.md. Criterion: call order and module interaction are described.



3.2.9 — Exception Hierarchy

Classes: OpmedError -> {ConfigError, DataError, ModelError, SolveError, ValidationError, VisualizationError}.

Output: ARCHITECTURE.md (Errors section). Criterion: mapping table: exception → source → message → exit code.



3.3 (Should) Diagrams (minimal notation)

3.3.1 — C4: Context

Task: system context diagram within the ecosystem (user/CI/files). Output: /docs/diagrams/context.png. Criterion: 4–6 blocks with labeled interactions.

3.3.2 — C4: Container

Task: container diagram of opmed package modules. Output: /docs/diagrams/container.png. Criterion: modules and their data dependencies.

3.3.3 — Data Flow (ETL → CP-SAT → Reports)

Task: data flow from surgeries.csv/config.yaml to artifacts. Output: /docs/diagrams/dataflow.png. Criterion: sources, transforms, sinks.

3.3.4 — Sequence: run()

Task: sequence from run() to artifact saving. Output: /docs/diagrams/sequence\_run.png. Criterion: logging/validation touchpoints shown.

3.3.5 — Export

Task: save PNGs and embed thumbnails in ARCHITECTURE.md. Criterion: images render locally in MD.



3.4 (Could) Extensions Plan (arch-doc section)

3.4.1 — Multi-day: schema/interface changes

Task: add Day index and rolling-horizon hooks in interfaces. Output: section in ARCHITECTURE.md (“Future Extensions”). Criterion: new fields and affected interfaces listed.

3.4.2 — Handover: variables and validator

Task: propose z\[a1,a2,s], handover buffers, validator impact. Output: same section. Criterion: at least one constraint and one validation rule.

3.4.3 — Stochastic: scenarios and Optimizer hook

Task: slot for scenario generation and metric aggregation. Output: same section. Criterion: extension point in interfaces described.

3.4.4 — Extension config flags

Task: new keys in config.yaml (disabled by default). Criterion: keys and defaults enumerated.

3.4.5 — Risk/complexity assessment

Task: short table of impact on complexity/time. Criterion: implementation priority defined (after Epics 7–10).





