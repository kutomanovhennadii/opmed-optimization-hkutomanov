\## Context

The Opmed optimization system must produce identical results when run on the same data, configuration, and environment.

Reproducibility is essential for scientific validation, regulatory compliance, and MLOps experiment tracking.



Randomized solver search strategies (CP-SAT) and environmental differences (package versions, CPU parallelism) can cause non-deterministic results if not controlled.

This decision formalizes how seeds, dependency versions, and dataset hashes are managed and logged.



\## Decision

All solver runs must be \*\*deterministic and reproducible\*\* through controlled configuration and logging.



\### Reproducibility policy

1\. Each experiment must define a fixed random seed (`solver.random\_seed`) in `config.yaml`.

2\. OR-Tools version, Python version, and OS metadata must be logged in `metrics.json`.

3\. Input data files (surgeries.csv, config.yaml) must include SHA256 hashes in the output metadata.

4\. The runtime environment must pin dependencies via `requirements.txt` or `poetry.lock`.

5\. All randomization must come exclusively from controlled seeds passed into CP-SAT and NumPy.



\### Example metadata (logged in metrics.json)

"environment": {

"python\_version": "3.11.6",

"ortools\_version": "9.10",

"platform": "Windows-11-x64",

"num\_workers": 8,

"random\_seed": 42,

"dataset\_hash": "e3f1a5b2c71a..."

}



\### Valida### Validation of determinism

\- Running the same configuration twice must produce identical:

&nbsp; - solver\_status

&nbsp; - total\_cost

&nbsp; - utilization

&nbsp; - assignments (surgery -> anesthetist mapping)

\- Validation scripts compare outputs using file hashes and JSON diffs.



\## Alternatives

1\. \*\*Uncontrolled random seeds\*\*

&nbsp;  Pros: slightly better search diversity.

&nbsp;  Cons: non-reproducible, fails regulatory and scientific standards.



2\. \*\*External random state management\*\*

&nbsp;  Pros: flexible across modules.

&nbsp;  Cons: adds unnecessary complexity for single-solver workflow.



3\. \*\*Fully deterministic single-thread runs\*\*

&nbsp;  Pros: strict reproducibility.

&nbsp;  Cons: slower performance; multi-thread reproducibility acceptable with fixed seed.



The selected approach balances determinism and performance.



\## Consequences

\- Every result is traceable to an exact environment and dataset.

\- Facilitates MLflow integration and experiment comparison.

\- Enables CI/CD regression testing with hash-based validation.

\- Supports reproducible publication of benchmark results.



Risk: dependency updates may silently alter solver behavior; mitigated through explicit version pinning and change logs.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.8, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision establishes deterministic reproducibility as a core quality principle of the Opmed optimization framework, enforced through seed fixation, dependency versioning, and data hashing.

"@ | Out-File -Encoding ascii "C:\\Repository\\opmed-optimization\\ADRs\\ADR-007-reproducibility.md"













