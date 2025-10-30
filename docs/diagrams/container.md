\# C4 Container Diagrams — Opmed Optimization System



This document provides four ASCII-style container diagrams representing the internal structure of the Opmed Optimization System.

Each diagram corresponds to a distinct layer of the architecture: control, core processing, tuning, and external context.

All diagrams follow vertical flow (top to bottom) for clarity and data consistency.



---



\## Container A — Control Layer



\[User]

│

▼

\[Makefile]

│

├── make run

├── make tune

└── make test

│

▼

\[run.py] ─────▶ \[tune\_solver.py]



yaml

Копировать код



\*\*Description:\*\*

The Control Layer represents how the system is executed locally.

A user triggers one of several make targets, which delegate to the corresponding orchestration scripts — `run.py` for optimization,

`tune\_solver.py` for solver tuning, and `make test` for local validation.



---



\## Container B — Core Processing Layer



\[DataLoader]

│

▼

\[ModelBuilder]

│

▼

\[Optimizer]

│

▼

\[Validator]

├──▶ \[Visualizer]

▼

\[Metrics]



yaml

Копировать код



\*\*Description:\*\*

The Core Processing Layer defines the main functional modules of the `opmed` package.

Data flows sequentially from input loading to model construction, solving, validation, visualization, and metrics aggregation.

Each module passes validated artifacts downward, ensuring deterministic and reproducible execution.



---



\## Container C — Tuning Layer



\[TuneSolver]

│

▼

(run.py)

│

▼

\[Metrics]

│

▼

\[solver\_tuning\_report.json]



yaml

Копировать код



\*\*Description:\*\*

The Tuning Layer performs repeated invocations of the orchestrator (`run.py`) with different solver hyperparameters.

It collects `metrics.json` from each run, aggregates results, and produces two artifacts:

`solver\_tuning\_report.json` (summary of averages and rankings) and `recommended\_solver\_config.yaml`.



---



\## Container D — External Context Layer



pgsql

Копировать код

&nbsp;    ┌────────────────────────────┐

&nbsp;    │      Local File System     │

&nbsp;    │ config.yaml, surgeries.csv │

&nbsp;    │ solution.csv, metrics.json │

&nbsp;    └──────────────┬─────────────┘

&nbsp;                   │

\[User] ─────▶ \[Opmed System] ─────▶ \[OR-Tools CP-SAT Solver]



pgsql

Копировать код



\*\*Description:\*\*

The External Context Layer illustrates the system’s environment.

The user provides configuration and input data via the local file system,

the Opmed System interacts with OR-Tools for solving,

and results are stored back to disk for review.



---



\*\*File:\*\* `/docs/diagrams/container.md`

\*\*Maintained by:\*\* Architecture \& Integration team

\*\*Last updated:\*\* $(Get-Date -Format "2025-10-30")
