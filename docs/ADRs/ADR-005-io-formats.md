\## Context

The Opmed optimization workflow depends on well-defined and reproducible data exchange between modules.

All processing starts with input surgeries.csv and ends with output solution.csv, both serving as standardized artifacts for validation, visualization, and further analytics.



Unstructured or inconsistent CSV formats may cause runtime errors, incorrect parsing, or failed validation.

To ensure deterministic behavior and compatibility with MLOps pipelines, explicit data schemas are required.



\## Decision

Define canonical CSV formats with strict columns, types, and null-handling rules.



\### Input file: surgeries.csv

Each row represents a single surgery with a fixed start and end time.



| Field | Type | Required | Description |

|--------|------|-----------|-------------|

| surgery\_id | string | yes | Unique identifier for each surgery |

| start\_time | datetime (ISO-8601) | yes | Start timestamp (e.g., 2025-10-29T08:30:00) |

| end\_time | datetime (ISO-8601) | yes | End timestamp |

| duration | float (hours) | optional | Computed if not provided |

| room\_hint | string | optional | Preferred room (if available) |



Validation rules:

\- start\_time < end\_time

\- duration = (end\_time - start\_time)

\- All timestamps must include timezone or default to local config setting

\- File encoding: UTF-8, separator: comma (,)



Example:

surgery\_id,start\_time,end\_time,duration,room\_hint

S001,2025-10-29T08:30:00,2025-10-29T10:15:00,1.75,A1

S002,2025-10-29T09:45:00,2025-10-29T12:00:00,2.25,A2



\### Output file: solution.csv

Each row represents an assigned surgery after optimization.



| Field | Type | Description |

|--------|------|-------------|

| surgery\_id | string | Identifier matching the input record |

| start\_time | datetime | Scheduled start |

| end\_time | datetime | Scheduled end |

| anesthetist\_id | string | Assigned anesthesiologist |

| room\_id | string | Assigned operating room |



Validation rules:

\- All surgery\_id values must match those in surgeries.csv

\- No duplicate surgery\_id

\- No overlapping intervals per anesthetist\_id or room\_id

\- Buffer (>=15 min) enforced for room switches

\- Output sorted by anesthetist\_id and start\_time



File encoding: UTF-8, separator: comma (,)



\### Auxiliary files

\- metrics.json : stores cost, utilization, and runtime

\- solver.log : text log from CP-SAT engine

\- validation\_report.json : constraint-level validation results



\## Alternatives

1\. JSON or Parquet input files

&nbsp;  Pros: type safety and hierarchical structure.

&nbsp;  Cons: less readable, harder for manual inspection.



2\. Excel (.xlsx)

&nbsp;  Pros: easy for non-technical users.

&nbsp;  Cons: inconsistent parsing, poor version control, binary format not ideal for Git.



3\. TSV (tab-separated)

&nbsp;  Pros: simpler for some locales.

&nbsp;  Cons: no major advantage over CSV, less compatible with standard tooling.



CSV remains the best compromise for readability, portability, and reproducibility.



\## Consequences

\- Clear data schema improves validation and automated testing.

\- Guarantees full compatibility across Python modules and external tools.

\- Facilitates CI/CD validation and dataset versioning.

\- Enables seamless migration to structured storage (e.g., Parquet) later.



Risk: users must follow schema strictly; mitigated via DataLoader validation.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.6, T1.1.8 (Problem Formulation Summary), T1.1.5 (Logical Scheme)



This decision standardizes the input/output CSV formats, ensuring reproducible and validated data exchange across all stages of the Opmed optimization pipeline.
