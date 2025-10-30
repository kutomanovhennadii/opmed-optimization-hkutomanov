\# 🗂️ Architectural Decision Records (ADR Registry)



This directory contains all formal architectural decisions made during the Opmed optimization system development.



Each ADR documents \*why\* a particular choice was made, \*what alternatives\* were considered, and \*what consequences\* follow from that decision.



\## 📖 ADR Index



| ID | Title | Status | Date | Summary |

|----|--------|---------|------|----------|

| ADR-001 | Solver Choice (CP-SAT vs MILP/CP/SMT) 	    | Accepted| 2025-10-30 | CP-SAT chosen for hybrid Boolean + interval optimization |

| ADR-002 | Time Representation (Δt = 5 min, integer scale) | Planned | – 	   | Discretize time to integer ticks for reproducibility |

| ADR-003 | Module Boundaries and Directory Structure 	    | Planned | –          | Define opmed package layout and module roles |

| ADR-004 | Configuration Management (YAML + Pydantic) 	    | Planned | – 	   | Specify config structure and defaults |

| ADR-005 | Data Formats (surgeries.csv / solution.csv)     | Planned | – 	   | Define schemas and validation rules |

| ADR-006 | Logging and Metrics 			    | Planned | – 	   | JSONL + metrics.json formats |

| ADR-007 | Reproducibility 				    | Planned | – 	   | Seeds, dependency pinning, hash logging |

| ADR-008 | Error Handling and Validation 		    | Planned | – 	   | Unified exception hierarchy |



> New ADRs must follow the `\_TEMPLATE.md` format.

> File names use the pattern `ADR-###-short-title.md`.



\## 🧭 Conventions



\- \*\*Status\*\* values: `Proposed`, `Accepted`, `Superseded`, `Deprecated`.

\- Decisions are immutable once accepted; corrections require a new ADR.

\- All ADRs reference related documents (Epics, T-tasks, or code modules).

\- When code changes require a new architectural assumption, create a new ADR instead of editing old ones.
