# Opmed Export Subsystem — User and Orchestrator Guide

**Module:** `src/opmed/export/solution_export.py`
**Primary Function:** `write_solution_csv(assignments, out_path: Path) -> Path`

---

## 1. Purpose
The export subsystem finalizes the Opmed optimization pipeline by serializing solved schedules into a canonical `solution.csv` file. It ensures full compliance with the I/O standard described in ADR-005 and guarantees that exported results can be reloaded into any analytics or validation workflow without additional parameters or formatting adjustments. This module acts as the bridge between the SolverCore output (`assignments`) and all subsequent stages — Validator, Visualizer, and Metrics.

---

## 2. Responsibilities
`solution_export` has a single, focused responsibility — to convert structured solver assignments into a human- and machine-readable CSV artifact.

| Aspect | Description |
|--------|--------------|
| **Input** | Solver output — list of dictionaries (or equivalent iterable) containing surgery assignments. |
| **Validation** | Structural and semantic verification of required fields and time formats. |
| **Serialization** | Converts time fields to ISO-8601 UTC with explicit timezone. |
| **Output** | `data/output/solution.csv` — standardized, reproducible, directly parsable by `pandas.read_csv()`. |

---

## 3. CSV Specification

### Columns
| Column | Type | Description |
|---------|------|-------------|
| `surgery_id` | `str` | Unique identifier of the surgery. |
| `start_time` | `datetime (ISO-8601, UTC)` | Fixed start timestamp of the surgery. |
| `end_time` | `datetime (ISO-8601, UTC)` | Fixed end timestamp of the surgery. |
| `anesthetist_id` | `str` | Identifier of the assigned anesthesiologist. |
| `room_id` | `str` | Identifier of the operating room. |

### Formatting Rules
- Encoding: UTF-8
- Separator: Comma (`,`)
- Header line included
- Sorted by `anesthetist_id`, then `start_time`
- Time values always contain explicit timezone `+00:00`
- Compatible with:
    import pandas as pd
    df = pd.read_csv("data/output/solution.csv")

---

## 4. Typical Usage

### From Orchestrator (scripts/run.py)
    from pathlib import Path
    from opmed.export import write_solution_csv

    # After solver returns assignments
    assignments = solver_result["assignments"]

    # Export to standard output location
    out_path = Path("data/output/solution.csv")
    write_solution_csv(assignments, out_path)

The orchestrator guarantees that the exported file is:
- Synchronized with the current experiment directory.
- Overwritten on each run (atomic write via temp file replacement).
- Available for subsequent visualization (`plot_schedule`) and validation (`validate_assignments`).

### Manual Use by User
    from datetime import datetime, timezone
    from pathlib import Path
    from opmed.export.solution_export import write_solution_csv

    data = [
        {
            "surgery_id": "S001",
            "start_time": datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc),
            "end_time": datetime(2025, 11, 2, 10, 0, tzinfo=timezone.utc),
            "anesthetist_id": "A1",
            "room_id": "R1",
        }
    ]

    write_solution_csv(data, Path("data/output/solution_manual.csv"))

Result:
    data/output/solution_manual.csv
    │
    ├── surgery_id,start_time,end_time,anesthetist_id,room_id
    ├── S001,2025-11-02T08:00:00+00:00,2025-11-02T10:00:00+00:00,A1,R1

---

## 5. Error Handling
The module follows the ADR-008 structured error model. All exceptions derive from `OpmedError`, specifically `DataError`.

| Error Type | Condition | Example Message |
|-------------|------------|----------------|
| `DataError` | Missing required columns | "Missing required column(s): room_id" |
| `DataError` | Non-timezone-aware datetime | "start_time must include timezone (tz-aware)." |
| `DataError` | Duplicate surgery IDs | "Duplicate surgery_id detected: S014" |
| `DataError` | Unsupported input type | "Unsupported assignments type." |

All raised exceptions include:
    {
      "error_type": "DataError",
      "source": "export.write_solution_csv",
      "suggested_action": "Ensure all records contain valid ISO-8601 timestamps and required columns."
    }

---

## 6. Integration Notes

### For Orchestrator
- Always call `write_solution_csv()` after successful validation and metric collection.
- Use the same `data/output/` folder as other artifacts (`metrics.json`, `solver.log`).
- The function is idempotent — repeated calls with the same input yield identical files.

### For Users and Analysts
- Files exported by this module are guaranteed to comply with ADR-005; they can be safely shared, version-controlled, or reloaded into notebooks.
- No custom CSV parameters are needed when reading.
- Timestamps are always in UTC, enabling cross-time-zone reproducibility.

---

## 7. Implementation Highlights
- Atomic write pattern: file is first written to a temporary `.tmp` file, then atomically renamed to target path.
- Defensive validation: each record validated field-by-field before serialization.
- Dependency-free: relies only on the Python standard library.
- Deterministic output: sorted consistently, reproducible byte-for-byte across runs.

---

## 8. Recommended Workflow Placement
    load_config() ─┐
    load_surgeries() ─┬──> build_model() ─┬──> solve() ─┬──> validate_assignments()
                      │                   │             │
                      │                   │             └──> collect_metrics()
                      │                   │
                      │                   └──> plot_schedule()
                      │
                      └──> write_solution_csv()  ←  current module

The export step finalizes the pipeline, ensuring that the generated CSV serves as the canonical artifact of each run.

---

## 9. Summary
The `solution_export` module provides a reliable and deterministic mechanism for producing the official solution artifact of every optimization run. Its strict adherence to Opmed’s ADR specifications ensures consistent structure across experiments, immediate usability in all downstream components, and reproducible experiment tracking within CI/CD or MLflow workflows.
