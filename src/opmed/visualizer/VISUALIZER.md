# Visualizer Module

## Purpose
The **Visualizer** module converts solver results (`assignments`) into a human-readable schedule diagram. It provides a graphical representation of anesthesiologists' workloads and room allocations over time.
This component closes the visual feedback loop of the Opmed pipeline:

    DataLoader → ModelBuilder → Optimizer → Validator → Visualizer → Metrics

## Main Entry Point
**Function:**
    plot_schedule(assignments, surgeries, cfg, out_path: Path) -> Path
**Location:**
    src/opmed/visualizer/plot.py
**Dependencies:**
- matplotlib (Agg backend for headless environments)
- seaborn, colorcet (used internally by client-provided plot_day_schedule())

## Function Description
`plot_schedule()` renders a schedule plot and saves it as a `.png` file.

**Arguments:**

| Argument | Type | Description |
|-----------|------|-------------|
| `assignments` | `pd.DataFrame` or iterable of `SolutionRow` / `dict` | Solver output with columns: `surgery_id`, `start_time`, `end_time`, `anesthetist_id`, `room_id`. |
| `surgeries` | any | Currently unused; reserved for future consistency checks. |
| `cfg` | `Config` | Configuration model; may include visual parameters under `cfg.visual.{width,height,dpi}`. |
| `out_path` | `Path` | Path to save PNG (e.g., `data/output/solution_plot.png`). |

**Returns:**
Path to the generated `.png` image.

**Raises:**
- `DataError` – invalid or missing columns, inconsistent timestamps.
- `VisualizationError` – image cannot be saved or Matplotlib backend fails.

## Output
By default, the plot is saved to:
data/output/solution_plot.png
This file remains after each solver run and is overwritten unless timestamped directories are used.

## Integration with the Orchestrator (scripts/run.py)
In the orchestrator pipeline:
    cfg = load_config("configs/base.yaml")
    surgeries = load_surgeries("data/input/surgeries.csv", cfg.time_unit)
    bundle = ModelBuilder(cfg, surgeries).build()
    result = Optimizer(cfg).solve(bundle)
    report = validate_assignments(result["assignments"], surgeries, cfg)

    # Visualization step
    plot_path = plot_schedule(
        result["assignments"],
        surgeries,
        cfg,
        Path("data/output/solution_plot.png")
    )
    print(f"Schedule visualization saved to: {plot_path}")

This step runs after validation and before metrics collection to ensure both human-readable and numerical summaries are available.

## Manual Usage (for researchers)
You can run the visualizer independently:
    import pandas as pd
    from pathlib import Path
    from opmed.visualizer.plot import plot_schedule
    from opmed.schemas.models import Config

    df = pd.read_csv("data/output/solution.csv")
    cfg = Config()
    plot_schedule(df, surgeries=None, cfg=cfg, out_path=Path("data/output/manual_plot.png"))

The function does not open a GUI window. It writes `manual_plot.png` to disk and returns its path.

## Rendering Details
Internally, the visualizer delegates rendering to:
    plot_day_schedule(df)
This function is defined in the Opmed package. It handles:
- X-axis: time (hours)
- Y-axis: anesthetists
- Color: room_id
- Text labels: surgery index
Rendering is deterministic and compatible with CI environments.

## Developer Notes
- Backend forced to Agg for headless CI.
- All file writes are UTF-8 and atomic.
- plt.tight_layout() errors are safely ignored.
- 100% test coverage, including fallback logic for .dict(), .model_dump(), and KeyError recovery.

## Expected Artifacts
File | Description
---- | -----------
data/output/solution_plot.png | Visualized OR schedule (core artifact)
data/output/metrics.json | Numerical summary of utilization and cost
data/output/validation_report.json | Structural correctness check

All are produced in an end-to-end pipeline run.

## Example Visualization
Example rendered output:
 ┌─────────────────────────────────────────────── Time (hours) ────────────────────────────────────────────────┐
 │                                                                                                             │
 │  Anesthetist A |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■                                                       │
 │  Anesthetist B |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■    │
 │                                                                                                             │
 └─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

## Troubleshooting
Symptom | Cause | Solution
--------|--------|----------
VisualizationError: Cannot create output directory | Output path unwritable | Check permissions or use local data/output path.
DataError: Missing columns in assignments | Input CSV missing headers | Ensure required columns are present.
Image blank or unreadable | Empty DataFrame or identical timestamps | Inspect solver output, ensure durations > 0.
GUI window appears unexpectedly | Wrong backend | Force matplotlib.use("Agg") in config or environment.

## Summary
The Visualizer translates machine-optimized schedules into compact, interpretable images. It produces a persistent artifact (`solution_plot.png`) complementing numerical metrics, serving both solver validation and presentation in reports or demos.
