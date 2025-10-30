\# ADR-002 - Time Representation (Δt = 5 min, integer scale)



\## Context

The optimization model relies on temporal reasoning: surgeries have fixed start and end times, anesthesiologists work shifts of limited duration, and buffers (15 min) separate consecutive operations.



Floating-point arithmetic can introduce rounding drift and break constraint propagation, especially in cumulative sums or when comparing adjacent intervals.

A uniform integer-tick time scale is therefore required for reproducible constraint solving and validation.



Theoretical\_Model.md and T1.1.8 define the base discretization parameter:

TIME\_UNIT = 0.0833 h (≈ 5 minutes)



\## Decision

Represent all time values internally as integers in units of Δt = 5 minutes.



Formally:

tick = round((timestamp - day\_start) / Δt)



Thus:

\- Input layer (DataLoader) converts timestamps to integer ticks.

\- Solver layer (ModelBuilder) works exclusively in ticks.

\- Output layer (Visualizer, Validator) converts back to human-readable datetimes.



All arithmetic on durations, buffers, and shift limits will use integer ticks:

SHIFT\_MIN = 5h = 60 ticks

SHIFT\_MAX = 12h = 144 ticks

BUFFER = 0.25h = 3 ticks



\## Alternatives



1\. Continuous (float) time

Pros: simpler for quick prototypes.

Cons: floating-point drift, infeasibility under tight equality, inconsistent rounding between Python and OR-Tools.



2\. Coarser discretization (15 min)

Pros: faster solving.

Cons: reduced precision, may misplace short surgeries and buffers.



3\. Finer discretization (1 min)

Pros: more precise.

Cons: combinatorial blow-up; 12x more variables and clauses.



The 5-minute resolution offers the best balance between accuracy, solver performance, and human interpretability.



\## Consequences

\- Determinism: all times are integer, reproducible across runs and systems.

\- Performance: model size remains manageable (<= 288 ticks/day).

\- Validation: direct integer comparison avoids floating errors.

\- Conversion Layer: DataLoader and Validator must implement bidirectional conversions (to\_ticks, to\_datetime).

\- Config Control: TIME\_UNIT retained in config.yaml but defaulted to 5 minutes.



Risk: extreme rounding (e.g., 2.5-minute surgeries) may introduce ±Δt quantization error; acceptable within validation tolerance < 1%.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.3, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision standardizes the internal temporal representation and guarantees reproducible scheduling and validation across all Opmed modules.
