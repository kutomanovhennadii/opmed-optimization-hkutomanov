\## Context

The Opmed optimization framework processes multiple interconnected modules (DataLoader, ModelBuilder, Optimizer, Validator, etc.).

Each stage can fail due to invalid input data, missing configuration keys, solver infeasibility, or plotting errors.



Historically, Python's generic exceptions were used inconsistently, making debugging difficult and log messages unclear.

To support reliable CI/CD automation, structured error reporting and standardized exception classes are required.



\## Decision

Adopt a unified exception hierarchy rooted in a base class `OpmedError`, with specific subclasses for each failure category.



\### Exception hierarchy
OpmedError

├── ConfigError # invalid or missing config.yaml keys

├── DataError # malformed or inconsistent input data

├── ModelError # issues while building CP-SAT model

├── SolveError # solver returned infeasible or timeout

├── ValidationError # failed schedule validation

└── VisualizationError # errors in rendering plots or figures

### Exception handling policy

\- All modules must raise only these defined exceptions.

\- Each exception includes:

&nbsp; - message (human-readable)

&nbsp; - source (module name)

&nbsp; - suggested\_action (string)

\- Exceptions are logged in `solver.log` with timestamp and level.

\- CLI or orchestration layer (`run.py`) captures all exceptions and writes a summary to `validation\_report.json`.



\### Example error message
{

"timestamp": "2025-10-30T14:22:08",

"error\_type": "DataError",

"source": "dataloader.loader",

"message": "Negative duration detected for surgery S014",

"suggested\_action": "Verify start and end timestamps in surgeries.csv"

}



\### Validator integration

\- If any ValidationError is raised, the `valid` field in validation\_report.json must be set to false.

\- All other errors propagate up to the orchestration layer and stop execution gracefully.



\## Alternatives

1\. \*\*Generic Python exceptions\*\*

&nbsp;  Pros: simpler to implement.

&nbsp;  Cons: hard to distinguish between logic and data errors; poor logging structure.



2\. \*\*External logging library with automatic wrapping\*\*

&nbsp;  Pros: consistent logs.

&nbsp;  Cons: adds external dependency overhead; unclear exception semantics.



3\. \*\*Return codes instead of exceptions\*\*

&nbsp;  Pros: explicit control flow.

&nbsp;  Cons: verbose, breaks Pythonic error handling.



The chosen model provides clarity, structure, and simplicity for developers and CI/CD systems.



\## Consequences

\- All failures become predictable and traceable through structured logs.

\- Improves debugging and automated issue classification.

\- Simplifies monitoring dashboards (e.g., MLflow can group results by error type).

\- Prevents partial or silent failures in pipelines.



Risk: strict enforcement requires unit testing and code reviews to ensure consistency.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.9, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision defines the unified error handling and validation strategy for all Opmed components, ensuring reliability, clarity, and consistent failure management across the optimization pipeline.
