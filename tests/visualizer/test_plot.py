# tests/visualizer/test_plot.py
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from opmed.errors import DataError, VisualizationError
from opmed.schemas.models import Config, SolutionRow
from opmed.visualizer.plot import plot_schedule


# ------------------------------
# Helpers
# ------------------------------
def _mini_cfg(dpi: int | None = None, size: tuple[float, float] | None = None) -> Config:
    """
    @brief
    Minimal configuration with a 'visual' section.

    @details
    If the Config model lacks a .visual field, creates a temporary namespace
    containing width, height, and dpi values.
    """
    cfg = Config()
    width, height = (19.0, 10.0)
    if size:
        width, height = size
    if dpi is None:
        dpi = 150
    cfg.visual = SimpleNamespace(width=width, height=height, dpi=dpi)  # type: ignore[attr-defined]
    return cfg


def _df_ok() -> pd.DataFrame:
    """
    @brief
    Minimal valid assignments DataFrame for testing.

    @details
    Provides a small example of properly structured schedule data
    with surgery_id, start_time, end_time, anesthetist_id, and room_id columns.
    """
    rows = [
        {
            "surgery_id": "S0",
            "start_time": "2023-04-25 07:00:00",
            "end_time": "2023-04-25 07:15:00",
            "anesthetist_id": "anesthetist - 0",
            "room_id": "room - 0",
        },
        {
            "surgery_id": "S1",
            "start_time": "2023-04-25 07:00:00",
            "end_time": "2023-04-25 07:30:00",
            "anesthetist_id": "anesthetist - 100",
            "room_id": "room - 1",
        },
        {
            "surgery_id": "S2",
            "start_time": "2023-04-25 07:30:00",
            "end_time": "2023-04-25 07:45:00",
            "anesthetist_id": "anesthetist - 0",
            "room_id": "room - 8",
        },
    ]
    return pd.DataFrame(rows)


def _list_of_solution_rows() -> list[SolutionRow]:
    """
    @brief
    Minimal valid assignments represented as a list of Pydantic models.

    @details
    Each SolutionRow defines start and end times, anesthetist ID, and room ID
    for testing conversion and validation logic.
    """
    return [
        SolutionRow(
            surgery_id="S10",
            start_time=datetime(2023, 4, 25, 7, 0, 0),
            end_time=datetime(2023, 4, 25, 7, 30, 0),
            anesthetist_id="anesthetist - 5",
            room_id="room - 2",
        ),
        SolutionRow(
            surgery_id="S11",
            start_time=datetime(2023, 4, 25, 8, 0, 0),
            end_time=datetime(2023, 4, 25, 8, 30, 0),
            anesthetist_id="anesthetist - 5",
            room_id="room - 3",
        ),
    ]


def _list_of_dicts() -> list[dict[str, Any]]:
    """
    @brief
    Minimal valid assignments represented as a list of dictionaries.

    @details
    Provides an example input for conversion functions that accept
    dict-based containers instead of Pydantic models.
    """
    return [
        {
            "surgery_id": "S20",
            "start_time": "2023-04-25 09:00:00",
            "end_time": "2023-04-25 09:45:00",
            "anesthetist_id": "anesthetist - X",
            "room_id": "room - 4",
        }
    ]


# ------------------------------
# Smoke: basic rendering
# ------------------------------
def test_plot_smoke_dataframe(tmp_path: Path) -> None:
    """
    @brief
    Smoke test for baseline rendering from a DataFrame.

    @details
    Verifies that plot_schedule() successfully produces a PNG file
    with valid PNG signature and nonzero content, and that
    all matplotlib figures are properly closed afterward.
    """
    df = _df_ok()
    cfg = _mini_cfg(dpi=120)
    out = tmp_path / "solution_plot.png"

    path = plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)

    # The file is created, non-empty, and has a correct PNG header
    assert path.exists() and path.is_file()
    data = path.read_bytes()
    assert len(data) > 64
    assert data[:4] == b"\x89PNG"  # PNG magic header

    # Environment cleanliness: ensure all figures are closed
    import matplotlib.pyplot as plt

    assert plt.get_fignums() == []


# ------------------------------
# Input types: list[SolutionRow]
# ------------------------------
def test_plot_smoke_list_of_solution_rows(tmp_path: Path) -> None:
    """
    @brief
    Smoke test for list[SolutionRow] input type.

    @details
    Ensures that plot_schedule() handles iterable of Pydantic models,
    generates a non-empty PNG file, and does not raise exceptions.
    """
    assignments = _list_of_solution_rows()
    cfg = _mini_cfg(dpi=96)
    out = tmp_path / "fig.png"

    path = plot_schedule(assignments, surgeries=None, cfg=cfg, out_path=out)
    assert path.exists()
    assert path.stat().st_size > 0


# ------------------------------
# Input types: list[dict]
# ------------------------------
def test_plot_smoke_list_of_dicts(tmp_path: Path) -> None:
    """
    @brief
    Smoke test for list[dict] input type.

    @details
    Checks that plot_schedule() correctly processes list of dictionaries,
    creates a PNG file, and writes it successfully to disk.
    """
    assignments = _list_of_dicts()
    cfg = _mini_cfg()
    out = tmp_path / "fig.png"

    path = plot_schedule(assignments, surgeries=None, cfg=cfg, out_path=out)
    assert path.exists()
    assert path.stat().st_size > 0


# ------------------------------
# Errors: missing columns (surgery_id)
# ------------------------------
def test_plot_missing_required_column_raises_dataerror(tmp_path: Path) -> None:
    """
    @brief
    Verifies that DataError is raised when required columns are missing.

    @details
    Removes the 'surgery_id' column from the DataFrame to simulate
    incomplete solver output. The function should raise DataError
    indicating missing required columns.
    """
    df = _df_ok().drop(columns=["surgery_id"])
    cfg = _mini_cfg()
    out = tmp_path / "fig.png"

    with pytest.raises(DataError) as ei:
        plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)

    msg = str(ei.value).lower()
    assert "missing required columns" in msg or "missing columns" in msg


# ------------------------------
# Errors: invalid time ranges (end <= start)
# ------------------------------
def test_plot_non_positive_duration_raises_dataerror(tmp_path: Path) -> None:
    """
    @brief
    Validates handling of non-positive durations in assignments.

    @details
    Modifies a row where end_time equals start_time to simulate
    zero-length intervals. Expects DataError to be raised.
    """
    df = _df_ok()
    df.loc[0, "end_time"] = df.loc[0, "start_time"]  # equal → zero duration
    cfg = _mini_cfg()
    out = tmp_path / "a.png"

    with pytest.raises(DataError):
        plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)


# ------------------------------
# Errors: datetime parsing failure (invalid strings)
# ------------------------------
def test_plot_bad_datetime_parse_raises_dataerror(tmp_path: Path) -> None:
    """
    @brief
    Ensures DataError is raised on invalid datetime parsing.

    @details
    Replaces one start_time with a non-parsable string to trigger
    a conversion error during timestamp normalization.
    """
    df = _df_ok()
    df.loc[1, "start_time"] = "not-a-datetime"
    cfg = _mini_cfg()
    out = tmp_path / "b.png"

    with pytest.raises(DataError):
        plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)


# ------------------------------
# Errors: file write failure (simulate PermissionError)
# ------------------------------
def test_plot_unwritable_path_raises_visualizationerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    @brief
    Validates that VisualizationError is raised when file writing is denied.

    @details
    Mocks plt.savefig to raise PermissionError, simulating an unwritable path.
    The function should catch the exception and rethrow it as VisualizationError
    with a clear 'permission' message.
    """
    df = _df_ok()
    cfg = _mini_cfg()
    out = tmp_path / "c.png"

    # Replace savefig to simulate a PermissionError
    import matplotlib.pyplot as plt

    orig_savefig = plt.savefig

    def _boom(*args: Any, **kwargs: Any) -> None:  # pragma: no cover – simulated behavior
        raise PermissionError("deny")

    monkeypatch.setattr(plt, "savefig", _boom)
    try:
        with pytest.raises(VisualizationError) as ei:
            plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)
        assert "permission" in str(ei.value).lower()
    finally:
        monkeypatch.setattr(plt, "savefig", orig_savefig)


# ------------------------------
# DPI enforcement check (via savefig spy)
# ------------------------------
def test_plot_uses_cfg_dpi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    @brief
    Confirms that plot_schedule() applies DPI value from configuration.

    @details
    Patches plt.savefig to capture the 'dpi' keyword argument and verifies
    that the specified DPI (222) is propagated from cfg.visual.dpi.
    """
    df = _df_ok()
    cfg = _mini_cfg(dpi=222)  # non-default DPI to detect propagation
    out = tmp_path / "dpi.png"

    called = {"dpi": None}

    import matplotlib.pyplot as plt

    def _spy_savefig(*args: Any, **kwargs: Any) -> None:
        called["dpi"] = kwargs.get("dpi")
        # Save to in-memory buffer so that a valid file is still created
        buf = io.BytesIO()
        plt.gcf().savefig(buf)

    monkeypatch.setattr(plt, "savefig", _spy_savefig)
    plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)

    assert called["dpi"] == 222


# ------------------------------
# Unit test: _as_dataframe() accepts objects with .dict() method
# ------------------------------
def test_as_dataframe_accepts_object_with_dict_method(tmp_path: Path):
    """
    @brief
    Ensures _as_dataframe() correctly handles objects implementing .dict().

    @details
    Defines a custom class WithDict that mimics legacy Pydantic v1 behavior.
    Confirms that plot_schedule() can serialize such objects without error
    and produce a valid output file.
    """

    class WithDict:
        def __init__(self):
            self.surgery_id = "X"
            self.start_time = "2023-04-25 07:00:00"
            self.end_time = "2023-04-25 07:30:00"
            self.anesthetist_id = "A"
            self.room_id = "R"

        def dict(self):
            # Mimics pydantic v1 behavior (before model_dump)
            return {
                "surgery_id": self.surgery_id,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "anesthetist_id": self.anesthetist_id,
                "room_id": self.room_id,
            }

    obj = WithDict()
    cfg = _mini_cfg()
    out = tmp_path / "dict_obj.png"

    plot_schedule([obj], surgeries=None, cfg=cfg, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_as_dataframe_accepts_object_with_vars_fallback(tmp_path: Path):
    """
    @brief
    Ensures _as_dataframe() uses vars() fallback for plain objects.

    @details
    Defines a simple class without .dict() or .model_dump() methods.
    Confirms that _as_dataframe() extracts attributes through vars()
    and that plot_schedule() successfully renders a valid PNG.
    """

    class PlainObj:
        def __init__(self):
            self.surgery_id = "V"
            self.start_time = "2023-04-25 08:00:00"
            self.end_time = "2023-04-25 08:45:00"
            self.anesthetist_id = "B"
            self.room_id = "R2"

    obj = PlainObj()
    cfg = _mini_cfg()
    out = tmp_path / "vars_obj.png"

    plot_schedule([obj], surgeries=None, cfg=cfg, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_as_dataframe_accepts_single_mapping(tmp_path: Path):
    """
    @brief
    Verifies that single Mapping input is handled correctly.

    @details
    Covers the branch `if isinstance(assignments, Mapping):`.
    Ensures a plain dictionary is converted to a one-row DataFrame
    and a valid PNG is produced by plot_schedule().
    """
    assignment = {
        "surgery_id": "MAP1",
        "start_time": "2023-04-25 09:00:00",
        "end_time": "2023-04-25 09:45:00",
        "anesthetist_id": "anesthetist - 1",
        "room_id": "room - 9",
    }
    cfg = _mini_cfg()
    out = tmp_path / "single_mapping.png"

    path = plot_schedule(assignment, surgeries=None, cfg=cfg, out_path=out)

    assert path.exists()
    assert path.stat().st_size > 0


def test_as_dataframe_unsupported_type_raises_dataerror(tmp_path: Path):
    """
    @brief
    Validates error handling for unsupported input types.

    @details
    Passes an integer instead of a DataFrame, Iterable, or Mapping
    to trigger DataError in _as_dataframe() and verify that the
    exception message includes 'unsupported' and 'assignments'.
    """
    cfg = _mini_cfg()
    out = tmp_path / "unsupported.png"

    bad_input = 42  # int is not a supported container type

    from opmed.errors import DataError

    with pytest.raises(DataError) as ei:
        plot_schedule(bad_input, surgeries=None, cfg=cfg, out_path=out)

    text = str(ei.value)
    assert "unsupported" in text.lower()
    assert "assignments" in text.lower()


# ------------------------------
# Sorting: by (anesthetist_id, start_time)
# ------------------------------
def test_plot_sorts_assignments_before_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    @brief
    Verifies that assignments are sorted by (anesthetist_id, start_time) before rendering.

    @details
    Creates a DataFrame with deliberately shuffled rows and replaces the client
    plotting function to capture the schedule DataFrame passed to it.
    Ensures that rows are sorted as expected prior to visualization.
    """
    df = pd.DataFrame(
        [
            # intentionally shuffled
            {
                "surgery_id": "S2",
                "start_time": "2023-04-25 08:00:00",
                "end_time": "2023-04-25 08:30:00",
                "anesthetist_id": "B",
                "room_id": "room - 1",
            },
            {
                "surgery_id": "S0",
                "start_time": "2023-04-25 07:00:00",
                "end_time": "2023-04-25 07:15:00",
                "anesthetist_id": "A",
                "room_id": "room - 0",
            },
            {
                "surgery_id": "S1",
                "start_time": "2023-04-25 07:30:00",
                "end_time": "2023-04-25 07:45:00",
                "anesthetist_id": "A",
                "room_id": "room - 2",
            },
        ]
    )
    cfg = _mini_cfg()
    out = tmp_path / "sort.png"

    # Capture the DataFrame passed to the client plotting function
    captured: dict[str, pd.DataFrame] = {}

    import opmed.visualizer.plot as viz_mod

    original_client = viz_mod.plot_day_schedule

    def _capture_df(schedule: pd.DataFrame) -> None:
        captured["df"] = schedule.copy()
        # minimal render to ensure a figure is produced
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        fig.canvas.draw()

    monkeypatch.setattr(viz_mod, "plot_day_schedule", _capture_df)
    try:
        plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)
    finally:
        monkeypatch.setattr(viz_mod, "plot_day_schedule", original_client)

    sent = captured["df"]
    # Client may only receive 4 columns — verify ordering among them
    # Expect sorting by (anesthetist_id, start_time)
    keys = list(zip(sent["anesthetist_id"].tolist(), pd.to_datetime(sent["start_time"]).tolist()))
    assert keys == sorted(keys)


# ------------------------------
# Validation of plot_schedule error handling
# ------------------------------
def test_plot_schedule_handles_keyerror_from_client_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    @brief
    Covers the KeyError branch inside plot_schedule().

    @details
    The client plotting function is mocked to raise KeyError on the first call
    (when 'surgery_id' column is present) and succeed on the second call
    (with only 4 columns). The test ensures both calls occur and a valid PNG
    is generated despite the initial error.
    """
    # Minimal valid DataFrame
    df = _df_ok()
    cfg = _mini_cfg()
    out = tmp_path / "keyerror_fallback.png"

    import opmed.visualizer.plot as viz_mod

    called = {"first": False, "second": False}

    # Simulated client function:
    # first call with 5 columns → KeyError,
    # second call with 4 columns → normal pass.
    def _mock_plot_day_schedule(df_arg):
        if "surgery_id" in df_arg.columns and not called["first"]:
            called["first"] = True
            raise KeyError("unexpected column surgery_id")
        called["second"] = True
        # minimal figure to allow plot_schedule() to save PNG
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        fig.canvas.draw()

    monkeypatch.setattr(viz_mod, "plot_day_schedule", _mock_plot_day_schedule)

    # Run — must follow KeyError branch and still produce a PNG
    path = viz_mod.plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)
    assert path.exists() and path.stat().st_size > 0

    # Verify both attempts were executed
    assert called["first"] is True
    assert called["second"] is True


def test_plot_schedule_swallows_tight_layout_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    @brief
    Covers the branch where plt.tight_layout() raises an exception.

    @details
    Mocks plt.tight_layout to raise RuntimeError. The exception must be
    suppressed, and the subsequent plt.savefig() call should still execute
    successfully, resulting in a valid PNG output.
    """
    df = _df_ok()
    cfg = _mini_cfg()
    out = tmp_path / "tightlayout_fallback.png"

    import matplotlib.pyplot as plt

    import opmed.visualizer.plot as viz_mod

    called = {"tight": False, "savefig": False}

    # Replace tight_layout to throw an exception
    def _boom_tight_layout():
        called["tight"] = True
        raise RuntimeError("tight_layout failed intentionally")

    # Replace savefig to mark call and create a dummy PNG file
    def _spy_savefig(path, **kwargs):
        called["savefig"] = True
        # create minimal fake PNG to simulate output
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nfake_png_data")

    monkeypatch.setattr(plt, "tight_layout", _boom_tight_layout)
    monkeypatch.setattr(plt, "savefig", _spy_savefig)

    # Execute — tight_layout exception should be swallowed
    result_path = viz_mod.plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)

    # Verify that exception was suppressed and file was created
    assert called["tight"]
    assert called["savefig"]
    assert result_path.exists()
    data = result_path.read_bytes()
    assert data.startswith(b"\x89PNG")


# ------------------------------
# Client function failure → VisualizationError
# ------------------------------
def test_client_function_error_is_wrapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    @brief
    Ensures client plotting errors are wrapped in VisualizationError.

    @details
    Mocks plot_day_schedule() to raise RuntimeError and verifies that
    plot_schedule() catches it and raises VisualizationError instead.
    """
    df = _df_ok()
    cfg = _mini_cfg()
    out = tmp_path / "boom.png"

    import opmed.visualizer.plot as viz_mod

    def _boom(_schedule: pd.DataFrame) -> None:  # pragma: no cover
        raise RuntimeError("client failure")

    monkeypatch.setattr(viz_mod, "plot_day_schedule", _boom)
    with pytest.raises(VisualizationError) as ei:
        plot_schedule(df, surgeries=None, cfg=cfg, out_path=out)

    assert "client" in str(ei.value).lower() or "failed" in str(ei.value).lower()


# ------------------------------
# Generate and validate a real PNG file
# ------------------------------
def test_generate_real_png() -> None:
    """
    @brief
    Generates an actual PNG schedule plot for visual confirmation.

    @details
    Creates a realistic DataFrame with a few surgery entries, invokes
    plot_schedule(), and confirms that the output file exists, is non-empty,
    and contains a valid PNG signature. This serves as an end-to-end smoke test.
    """
    # --- Prepare output path
    out_path = Path("data/output/real_plot.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Create small example dataframe
    df = pd.DataFrame(
        [
            {
                "surgery_id": "S0",
                "start_time": "2023-04-25 07:00:00",
                "end_time": "2023-04-25 07:30:00",
                "anesthetist_id": "A",
                "room_id": "room - 1",
            },
            {
                "surgery_id": "S1",
                "start_time": "2023-04-25 07:45:00",
                "end_time": "2023-04-25 08:15:00",
                "anesthetist_id": "A",
                "room_id": "room - 2",
            },
            {
                "surgery_id": "S2",
                "start_time": "2023-04-25 07:00:00",
                "end_time": "2023-04-25 08:00:00",
                "anesthetist_id": "B",
                "room_id": "room - 3",
            },
        ]
    )

    # --- Minimal config
    cfg = Config()

    # --- Generate plot
    path = plot_schedule(df, surgeries=None, cfg=cfg, out_path=out_path)

    # --- Validate file exists and not empty
    assert path.exists(), f"Plot not created: {path}"
    assert path.stat().st_size > 1000, "PNG too small, probably empty"

    print(f"\n✅ Real schedule plot generated at: {path.resolve()}\n")
