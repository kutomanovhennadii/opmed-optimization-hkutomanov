\## Context

The Opmed optimization system consists of multiple modules that transform raw input data into validated, visualized optimization results.

To ensure scalability, reproducibility, and parallel development, a clear directory layout and module boundary definition are required.



This decision defines the Python package structure, assigns responsibilities to each submodule, and aligns the software architecture with the theoretical model (Theoretical\_Model.md) and logical flow (T1.1.5).



Without formal boundaries, code coupling would increase, testing would become inconsistent, and reproducibility would degrade.



\## Decision

Adopt the following top-level directory layout for the Opmed repository:



src/

├── dataloader/

│   ├── \_\_init\_\_.py

│   └── loader.py

├── solver\_core/

│   ├── \_\_init\_\_.py

│   └── model\_builder.py

├── optimizer/

│   ├── \_\_init\_\_.py

│   └── optimizer.py

├── validator/

│   ├── \_\_init\_\_.py

│   └── validator.py

├── visualizer/

│   ├── \_\_init\_\_.py

│   └── visualizer.py

├── metrics/

│   ├── \_\_init\_\_.py

│   └── metrics\_logger.py

└── \_\_main\_\_.py  (entry point)



Additional directories at the project root:



configs/

data/

&nbsp;├── input/

&nbsp;└── output/

docs/

&nbsp;├── diagrams/

&nbsp;└── schemas.md

ADRs/

tests/



\### Module responsibilities



| Module | Role | Input | Output |

|--------|------|--------|--------|

| dataloader | Read and validate input data (CSV, YAML) | surgeries.csv, config.yaml | Surgery list, Config object |

| solver\_core | Build CP-SAT model with constraints and objective | Surgery list, Config | CpSatModelBundle |

| optimizer | Solve model and produce assignments | CpSatModelBundle | SolveResult |

| validator | Check constraints, buffers, shift limits | SolveResult, Config | ValidationReport |

| visualizer | Render schedule plots and tables | Assignments, Config | solution\_plot.png |

| metrics | Aggregate and write metrics and logs | SolveResult | metrics.json, solver.log |



The entire execution chain is orchestrated by run.py (to be defined later).



\## Alternatives

1\. Flat monolithic structure  

&nbsp;  Pros: simple for prototypes.  

&nbsp;  Cons: poor modularity, difficult testing, low reusability.



2\. Multi-repo architecture (each module separate repo)  

&nbsp;  Pros: strict isolation.  

&nbsp;  Cons: heavy management overhead, unnecessary complexity for a single solver pipeline.



3\. Plugin-style dynamic imports  

&nbsp;  Pros: extensible.  

&nbsp;  Cons: overkill for stable, fixed pipeline.



The proposed structure is a balanced monorepo layout supporting modular imports, unit testing, and CI/CD automation.



\## Consequences

\- Modular boundaries are now fixed; each component can be tested independently.  

\- Simplified orchestration: clear data flow from input to output.  

\- Future extensions (multi-day, stochastic) can be implemented by adding subpackages under solver\_core/ or optimizer/.  

\- Enables static type checking (mypy) and API documentation generation.  

\- Encourages reproducibility through isolated I/O per module.



Risk: slight overhead for smaller experimental scripts, but outweighed by architectural clarity.



\## Status

Status: Accepted  

Date: 2025-10-30  

Authors: Algorithm Research Team  

Related Tasks: Epic 3 -> 3.1.4, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision formalizes the Opmed Python package structure and establishes clear module boundaries to ensure scalable, maintainable development.

"@ | Out-File -Encoding ascii "C:\\Repository\\opmed-optimization\\ADRs\\ADR-003-module-boundaries.md"



