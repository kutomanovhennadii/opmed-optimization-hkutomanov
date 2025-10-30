\# ADR-001 — Solver Choice (CP-SAT vs MILP/CP/SMT)



\## 🧩 Context

The Opmed optimization system solves the anesthesiologist and operating room allocation problem — a hybrid of \*\*temporal scheduling\*\* and \*\*resource assignment\*\* with mixed logical and linear constraints.  

The solver must:

\- Handle interval variables and temporal reasoning,

\- Enforce logical relations (`NoOverlap`, buffers, exclusive resources),

\- Support linear objectives with piecewise cost (overtime multiplier),

\- Offer reproducibility, scalability, and transparent integration into Python.



During Epic 2 (Theoretical Model.md), the model was formulated with Boolean assignment variables and interval constraints.  

The architectural decision is now required to confirm the computational engine to be used for implementation and future MLOps orchestration.



---



\## 💡 Decision

Use \*\*Google OR-Tools CP-SAT\*\* as the primary solver for all optimization modules.  

CP-SAT (Constraint Programming + SAT hybrid) provides:

\- IntervalVar and NoOverlap constructs for time reasoning,

\- Exact Boolean logic with clause learning,

\- Linear and piecewise-linear objective functions,

\- Deterministic, reproducible solving via seed control,

\- Efficient multi-core search (portfolio of strategies).



All model construction functions (`ModelBuilder`, `Optimizer`) will map directly to CP-SAT’s Python API.  

Alternative solvers may only be added later as research extensions (e.g., MILP back-end for benchmarking).



---



\## 🔁 Alternatives



\### 1. MILP (Mixed-Integer Linear Programming)

\*\*Pros:\*\* mature solvers (Gurobi, CPLEX), strong optimality proofs.  

\*\*Cons:\*\* requires explicit time discretization → combinatorial explosion; poor handling of interval and Boolean logic; expensive commercial licensing.



\### 2. Classical CP (Constraint Programming without SAT)

\*\*Pros:\*\* elegant propagation; expressive modeling.  

\*\*Cons:\*\* lacks hybrid Boolean reasoning and linear cost handling; weaker scalability for mixed integer objectives.



\### 3. SMT (Satisfiability Modulo Theories)

\*\*Pros:\*\* flexible symbolic reasoning.  

\*\*Cons:\*\* poor numeric optimization support; not optimized for scheduling or piecewise costs; fragile performance for large datasets.



CP-SAT unifies the advantages of these families while avoiding their major drawbacks.



---



\## ⚙️ Consequences

\- \*\*Architecture:\*\* SolverCore module binds to `ortools.sat.python.cp\_model`.

\- \*\*Performance:\*\* Enables efficient handling of hundreds of surgeries using interval propagation.

\- \*\*Maintainability:\*\* Stable Google library, open-source, Python-native.

\- \*\*Reproducibility:\*\* Deterministic seeds and solver logs; easy to track via MLflow.

\- \*\*Extensibility:\*\* Allows future integration of learning-enhanced search (reinforcement-guided branching).



Potential risk: migration to other solvers would require re-encoding interval logic, though model abstraction can mitigate this.



---



\## 📅 Status

| Field | Value |

|-------|-------|

| \*\*Status\*\* | Accepted |

| \*\*Date\*\* | 2025-10-30 |

| \*\*Authors\*\* | Algorithm Research Team |

| \*\*Related Tasks\*\* | Epic 3 → 3.1.2, T2.3.5 (Theoretical Model.md) |



---



\*This decision establishes CP-SAT as the formal computation core of the Opmed optimization framework.\*



