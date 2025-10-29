# 🧠 Epic 2 — Theoretical Framework

## 1. Purpose
The purpose of this epic is to establish the **theoretical foundation** of the optimization model for anesthesiologist allocation.  
This stage defines the formal mathematical model, identifies the optimization class, analyzes algorithmic approaches, and develops a consistent theoretical justification for all subsequent architectural and implementation steps.

---

## 2. Scope
Epic 2 covers all theoretical, mathematical, and algorithmic work necessary before implementation.  
It bridges the analytical problem definition (Epic 1) and the software architecture design (Epic 3).

Theoretical outputs will include:
- A complete formal model of the optimization task.  
- Comparison of applicable algorithmic methods (CP-SAT, MILP, LNS, metaheuristics).  
- A framework for parameter tuning and performance estimation.  
- The final consolidated document `Theoretical_Model.md`.

---

## 3. Stories and Tasks

### 📘 Story 2.1 — Basic Theoretical Solution
Formulate the core mathematical model of the problem, including all sets, variables, functions, and boundaries.

**Tasks**
- **T2.1.1** — Formal definition of sets, mappings, and variables.  
- **T2.1.2** — Definition of the cost function and auxiliary metrics.  
- **T2.1.3** — Classification of the problem by computational complexity.  
- **T2.1.4** — Theoretical justification of the chosen method (CP-SAT).  
- **T2.1.5** — Definition of the theoretical validation protocol.

**Deliverable:**  
`/docs/scrum/epic2_theoretical_framework/story2_1_basic_theoretical_solution/*.md`

---

### 📗 Story 2.2 — Academic Algorithmic Study
Survey algorithmic alternatives and theoretical optimizations applicable to the model.

**Tasks**
- **T2.2.1** — Comparative analysis of CP-SAT, MILP, LNS, and evolutionary heuristics.  
- **T2.2.2** — Theoretical background for hyperparameter selection and solver tuning.  
- **T2.2.3** — Analysis of time discretization and rounding effects on solution quality.  
- **T2.2.4** — Literature review of resource-constrained scheduling heuristics.  
- **T2.2.5** — Theoretical guidelines for hybrid optimization strategies.

**Deliverable:**  
`/docs/scrum/epic2_theoretical_framework/story2_2_academic_algorithms_study/*.md`

---

### 📙 Story 2.3 — Theoretical Model Documentation
Consolidate and finalize the theoretical results into a single cohesive document.

**Tasks**
- **T2.3.1** — Summarize all formulas, assumptions, and derivations.  
- **T2.3.2** — Provide a full formal definition of the optimization model.  
- **T2.3.3** — Analyze model validity and stability.  
- **T2.3.4** — Outline future extensions (multi-day, handover, stochastic optimization).  
- **T2.3.5** — Assemble final document `Theoretical_Model.md`.

**Deliverable:**  
`/docs/scrum/epic2_theoretical_framework/story2_3_theoretical_description/*.md`

---

## 4. Integration with Project Roadmap
- **Inputs:** Outputs from Epic 1 (`Problem_Formulation.md`, variable definitions, constraints).  
- **Outputs:** Theoretical model and algorithmic recommendations for Epic 3 (architecture).  
- **Dependencies:** None beyond completion of Epic 1.  
- **Downstream impact:** Epic 3 (Solver architecture), Epic 4 (Development planning).

---

## 5. Expected Artifacts
- Markdown documents for all stories and tasks.  
- Final theoretical report `Theoretical_Model.md`.  
- Diagrams and visual models (where needed).  
- Citations to academic literature (appendix in Story 2.2).  
- Updated glossary of terms and variable definitions.

---

## 6. Success Criteria
Epic 2 is considered **complete** when:
- The optimization model is fully defined and theoretically validated.  
- The selected algorithm (CP-SAT) is justified with complexity analysis.  
- Parameter tuning framework is described and approved.  
- Theoretical_Model.md is finalized and committed to the repository.
