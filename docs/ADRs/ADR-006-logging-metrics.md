\## Context

The Opmed optimization system requires transparent and reproducible tracking of solver runs.

Each experiment should produce a consistent set of logs and metrics to support performance comparison, validation, and debugging.



Historically, solver output was printed to console without structured logging, which made it difficult to analyze results or reproduce experiments.

To enable integration with MLflow, CI/CD pipelines, and reproducibility checks, we must formalize the logging and metrics structure.



\## Decision

Adopt two complementary logging formats:

1\. \*\*solver.log\*\* - human-readable text stream (runtime messages, solver parameters, status).

2\. \*\*metrics.json / metrics.jsonl\*\* - structured JSON summary for automated parsing.



\### Log content (solver.log)

Each solver run produces a timestamped log file under data/output/.

Example (truncated):

\[2025-10-30 11:20:41] INFO Starting CP-SAT solver

\[2025-10-30 11:20:41] INFO Parameters: workers=8, time\_limit=60s, seed=42

\[2025-10-30 11:21:02] INFO Status: OPTIMAL, Objective=185.0

\[2025-10-30 11:21:02] INFO Runtime=21.6 sec, Utilization=0.83



The file must always include:

\- timestamp

\- log level (INFO, WARN, ERROR)

\- event description

\- optional key=value pairs (e.g., objective=185.0)



\### Metrics file (metrics.json)

A structured JSON dictionary capturing core performance metrics and metadata.



Example:

{

"timestamp": "2025-10-30T11:21:02",

"solver\_status": "OPTIMAL",

"total\_cost": 185.0,

"utilization": 0.83,

"runtime\_sec": 21.6,

"num\_anesthetists": 14,

"seed": 42,

"solver": {

"engine": "CP-SAT",

"version": "9.10",

"num\_workers": 8

}

}



If multiple experiments are executed (e.g., hyperparameter tuning), each run appends a line to `metrics.jsonl` in JSON Lines format for MLflow ingestion.



\### File locations

All logs are written under:



data/output/run\_<timestamp>/

solver.log

metrics.json

solution.csv

validation\_report.json

## Alternatives

1\. \*\*Plain text logs only\*\*  

&nbsp;  Pros: simplest to implement.  

&nbsp;  Cons: hard to parse, not machine-readable.



2\. \*\*Database storage (e.g., SQLite)\*\*  

&nbsp;  Pros: queryable history.  

&nbsp;  Cons: adds complexity, not ideal for portable runs.



3\. \*\*CSV metrics\*\*  

&nbsp;  Pros: lightweight.  

&nbsp;  Cons: poor extensibility for nested metadata.



JSON and JSONL balance human readability with structured parsing.



\## Consequences

\- Each solver execution is traceable and reproducible.

\- Facilitates MLflow experiment tracking and CI/CD validation.

\- Enables automated aggregation of runtime performance.

\- Provides human-readable and machine-readable artifacts simultaneously.

\- Easy to extend with new metrics (e.g., fairness, robustness).



Risk: log files may grow large for multi-run experiments; mitigated by rotating logs or archiving via MLflow.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.7, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision defines JSONL and metrics.json as the official logging and metrics standards for the Opmed optimization framework, ensuring consistent traceability and integration with MLOps tools.



