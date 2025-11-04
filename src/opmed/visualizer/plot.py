# src/opmed/visualizer/plot.py
"""
Visualizer adapter that wraps the client-provided plotting code.

Responsibilities:
- Validate/normalize 'assignments' input (columns, dtypes).
- Enforce headless backend (Agg) and figure export parameters (DPI, size).
- Call client function plot_day_schedule(schedule: pd.DataFrame) as-is.
- Save PNG to the requested out_path and return that Path.
"""

from __future__ import annotations

# --- Standard library ---
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import colorcet as cc

# --- Third-party (no pyplot here!) ---
import matplotlib
import pandas as pd
import seaborn as sns

# --- Project imports ---
from opmed.errors import DataError, VisualizationError
from opmed.schemas.models import Config

# (1) Enforce headless backend for environments without display
matplotlib.use("Agg")


def plot_day_schedule(schedule: pd.DataFrame) -> None:
    """
    @brief
    Client-provided plotting routine preserved verbatim.

    @details
    Renders daily schedule visualization:
        - Y-axis: anesthetist_id categories.
        - X-axis: time of day (hours from start).
        - Color: room_id.
        - Label: sequential index.
    The routine defines its own figure size and layout, and is executed unchanged
    to preserve client behavior.

    @params
        schedule : pd.DataFrame
            Must include: start_time, end_time, anesthetist_id, room_id.
    """
    from matplotlib import pyplot as plt

    # (1) Create figure and axes
    fig, ax = plt.subplots(nrows=1, ncols=1)
    fig.set_size_inches(w=2 * 9.5, h=2 * 5)
    fig.tight_layout(pad=1.7)

    # (2) Prepare category mapping for anesthetists
    resources_set = set(schedule["anesthetist_id"])
    resources = sorted(resources_set, key=lambda x: (len(x), x), reverse=True)
    resource_mapping = {resource: i for i, resource in enumerate(resources)}

    # (3) Compute time intervals in hours from earliest timestamp (continuous timeline)
    t0 = schedule["start_time"].min()
    intervals_start = (schedule["start_time"] - t0).dt.total_seconds().div(3600)
    intervals_end = (schedule["end_time"] - t0).dt.total_seconds().div(3600)
    intervals = list(zip(intervals_start, intervals_end))

    # (4) Build color palette per room_id
    palette = sns.color_palette(cc.glasbey_dark, n_colors=len(schedule))
    palette = [(c[0] * 0.9, c[1] * 0.9, c[2] * 0.9) for c in palette]
    cases_colors = {case_id: palette[i] for i, case_id in enumerate(set(schedule["room_id"]))}

    # (5) Draw horizontal bars for each assignment (label = surgery_id)
    for room_id, anesthetist, evt, sid in zip(
        schedule["room_id"], schedule["anesthetist_id"], intervals, schedule["surgery_id"]
    ):
        label = str(sid)
        ax.barh(
            resource_mapping[anesthetist],
            width=evt[1] - evt[0],
            left=evt[0],
            linewidth=1,
            edgecolor="black",
            color=cases_colors[room_id],
        )
        try:
            ax.text(
                (evt[0] + evt[1]) / 2,
                resource_mapping[anesthetist],
                label,
                color="black",
                va="center",
                ha="center",
                fontsize=8,
            )
        except Exception as e:
            print(f"skip label {label}: {e}")

    # (6) Configure axes and labels
    ax.set_yticks(range(len(resources)))
    ax.set_yticklabels([f"{r}" for r in resources])
    ax.set_ylabel("anesthetist_id".replace("_", " "))
    ax.title.set_text(f'Total {len(set(schedule["anesthetist_id"]))} anesthetists')


# =========================
# Adapter / Wrapper
# =========================

REQUIRED_COLUMNS = ["surgery_id", "start_time", "end_time", "anesthetist_id", "room_id"]
CLIENT_REQUIRED_COLUMNS = ["start_time", "end_time", "anesthetist_id", "room_id"]


def _as_dataframe(assignments: Any) -> pd.DataFrame:
    """
    @brief
    Convert heterogeneous assignment containers into a pandas DataFrame.

    @details
    Accepts pandas.DataFrame, list[SolutionRow], list[dict], or Mapping.
    Extracts attributes via model_dump(), dict(), or __dict__.
    Raises DataError on unsupported container type.

    @params
        assignments : Any
            Input container with assignment data.

    @returns
        pd.DataFrame containing normalized rows with dict-like structure.

    @raises
        DataError if the container type is unsupported.
    """
    if isinstance(assignments, pd.DataFrame):
        return assignments.copy()

    # (1) Handle iterable of objects or dicts
    if isinstance(assignments, Iterable) and not isinstance(assignments, (str | bytes | Mapping)):
        rows: list[dict[str, Any]] = []
        for item in assignments:
            if hasattr(item, "model_dump"):
                rows.append(item.model_dump())
            elif hasattr(item, "dict"):
                rows.append(item.dict())
            elif isinstance(item, Mapping):
                rows.append(dict(item))
            else:
                # (1.1) Fallback: generic object with __dict__
                rows.append(dict(vars(item)))
        return pd.DataFrame(rows)

    # (2) Single mapping treated as one-row DataFrame
    if isinstance(assignments, Mapping):
        return pd.DataFrame([dict(assignments)])

    # (3) Unsupported container type
    raise DataError(
        "Unsupported 'assignments' container type for visualization",
        source="visualizer.plot._as_dataframe",
        suggested_action="Pass pandas.DataFrame, list[SolutionRow], list[dict], or a mapping",
    )


def _normalize_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    @brief
    Validate structure and datatypes of the assignments DataFrame.

    @details
    Ensures presence of required columns and logical integrity:
        - Converts timestamps to datetime.
        - Enforces string dtype for IDs.
        - Validates that end_time > start_time.
        - Sorts by anesthetist_id and start_time.

    @params
        df : pd.DataFrame
            Assignments DataFrame to normalize.

    @returns
        Validated and sorted DataFrame.

    @raises
        DataError on missing columns, invalid timestamps, or non-positive durations.
    """
    # (1) Check required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(
            f"Missing required columns: {missing}",
            source="visualizer.plot._normalize_and_validate",
            suggested_action="Ensure solver outputs include surgery_id, start_time, end_time, anesthetist_id, room_id",
        )

    # (2) Convert timestamps
    try:
        df["start_time"] = pd.to_datetime(df["start_time"], utc=False, errors="raise")
        df["end_time"] = pd.to_datetime(df["end_time"], utc=False, errors="raise")
    except Exception as exc:  # pragma: no cover
        raise DataError(
            f"Failed to parse start_time/end_time as datetimes: {exc}",
            source="visualizer.plot._normalize_and_validate",
            suggested_action="Provide ISO-8601 timestamps in assignments (with or without timezone)",
        )

    # (3) Enforce categorical string types
    for col in ("anesthetist_id", "room_id", "surgery_id"):
        df[col] = df[col].astype("string")

    # (4) Check duration validity
    bad = df["end_time"] <= df["start_time"]
    if bool(bad.any()):
        raise DataError(
            "Found non-positive durations (end_time <= start_time) in assignments",
            source="visualizer.plot._normalize_and_validate",
            suggested_action="Fix invalid rows before visualization",
        )

    # (5) Stable sort by anesthetist and time
    df = df.sort_values(["anesthetist_id", "start_time"], kind="stable", ignore_index=True)
    return df


def _extract_visual_params(cfg: Config | Any) -> tuple[float, float, int]:
    """
    @brief
    Extract visual rendering parameters from configuration.

    @details
    Reads cfg.visual.{width, height, dpi} if available, otherwise falls back
    to default values suitable for PNG export.

    @params
        cfg : Config | Any
            Configuration or config-like object.

    @returns
        Tuple (width, height, dpi) for figure rendering.
    """
    width, height, dpi = 19.0, 10.0, 150
    visual = getattr(cfg, "visual", None)
    if visual is not None:
        width = float(getattr(visual, "width", width))
        height = float(getattr(visual, "height", height))
        dpi = int(getattr(visual, "dpi", dpi))
    return width, height, dpi


def plot_schedule(assignments: Any, surgeries: Any, cfg: Config | Any, out_path: Path) -> Path:
    """
    @brief
    High-level adapter to render schedule visualization and save to PNG.

    @details
    Acts as a wrapper around client-provided plot_day_schedule().
    Steps:
        (1) Normalize assignments into DataFrame.
        (2) Validate structure and datatypes.
        (3) Ensure output directory exists.
        (4) Extract visual parameters from configuration.
        (5) Call client plotting function with normalized input.
        (6) Save resulting figure to PNG.

    @params
        assignments : Any
            Assignments data container (DataFrame, list, or mapping).
        surgeries : Any
            Placeholder for future consistency checks; currently unused.
        cfg : Config | Any
            Configuration object with optional visual section.
        out_path : Path
            Destination path for PNG output.

    @returns
        Path to saved PNG file.

    @raises
        DataError, VisualizationError, IOError depending on failure mode.
    """
    from matplotlib import pyplot as plt

    # (1) Normalize and validate input
    df = _as_dataframe(assignments)
    df = _normalize_and_validate(df)

    # (2) Prepare output directory
    out_path = Path(out_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # pragma: no cover
        raise VisualizationError(
            f"Cannot create output directory: {out_path.parent} ({exc})",
            source="visualizer.plot.plot_schedule",
            suggested_action="Check filesystem permissions or choose another output path",
        )

    # (3) Extract figure parameters (width, height, dpi)
    width, height, dpi = _extract_visual_params(cfg)

    # (4) Invoke client plotting function
    try:
        plot_day_schedule(df[CLIENT_REQUIRED_COLUMNS + ["surgery_id"]])
    except KeyError:
        plot_day_schedule(df[CLIENT_REQUIRED_COLUMNS])
    except Exception as exc:  # pragma: no cover
        raise VisualizationError(
            f"Client plotting function failed: {exc}",
            source="visualizer.plot.plot_schedule",
            suggested_action="Verify client function compatibility and input dtypes",
        )

    # (5) Export rendered figure to PNG
    try:
        # (5.1) Attempt layout tightening (non-critical)
        try:
            plt.tight_layout()
        except Exception:
            # Tight layout failures are non-fatal and intentionally ignored
            pass

        # (5.2) Save figure with enforced DPI and bbox
        plt.savefig(out_path, dpi=dpi, bbox_inches="tight")
        plt.close()
    except PermissionError as exc:  # pragma: no cover
        raise VisualizationError(
            f"Permission denied writing figure: {out_path} ({exc})",
            source="visualizer.plot.plot_schedule",
            suggested_action="Close viewers using the file or change output location",
        )
    except Exception as exc:  # pragma: no cover
        raise VisualizationError(
            f"Failed to save figure: {exc}",
            source="visualizer.plot.plot_schedule",
            suggested_action="Check disk space and image backend settings",
        )

    # (6) Return absolute path to saved image
    return out_path.resolve()
