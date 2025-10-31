# src/opmed/schemas/models.py
"""
Pydantic data models for Opmed optimization project.

This module defines three canonical models:
- Surgery:      one input surgery record (from surgeries.csv)
- Config:       runtime configuration (from config.yaml), including nested SolverConfig
- SolutionRow:  one output row (for solution.csv)

Models follow the field names and types specified in docs/schemas.md.
They are intentionally lightweight (no heavy validators) to serve as a stable source
for JSON Schema generation via .model_json_schema().
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class _StrictBaseModel(BaseModel):
    """Base model with strict-ish defaults suitable for config/data contracts."""

    model_config = {
        "extra": "forbid",  # Reject unknown fields
        "populate_by_name": True,  # Allow population by field_name
        "use_enum_values": True,  # Export raw enum values if enums appear later
    }


class Surgery(_StrictBaseModel):
    """
    Represents a single surgery entry from surgeries.csv.

    Fields:
        surgery_id: Unique identifier of the surgery.
        start_time: Surgery start time (ISO-8601, expected UTC unless Config.timezone provided).
        end_time:   Surgery end time   (ISO-8601, expected UTC unless Config.timezone provided).
        duration:   Optional duration in hours; may be computed as (end_time – start_time).
        room_id:  Optional preferred operating-room label.
    """

    surgery_id: str = Field(..., description="Unique identifier")
    start_time: datetime = Field(..., description="Surgery start time (ISO-8601)")
    end_time: datetime = Field(..., description="Surgery end time (ISO-8601)")
    duration: float | None = Field(
        None, description="Duration in hours; optional if computable from timestamps"
    )
    room_id: str | None = Field(None, description="Preferred operating room label (optional)")


class SolverConfig(_StrictBaseModel):
    """
    Full CP-SAT solver configuration (compatible with tuning interface 3.2.10).

    Covers both production parameters and all hyperparameters used for tuning.
    Default values are chosen for safe, reproducible production runs.
    """

    # --- Basic controls ---
    search_branching: str = Field(
        "AUTOMATIC", description="Search strategy: AUTOMATIC | PORTFOLIO | FIXED_SEARCH"
    )
    num_workers: int = Field(4, ge=0, description="Parallel workers (threads)")
    max_time_in_seconds: int = Field(60, ge=0, description="Solver time limit (seconds)")
    random_seed: int = Field(0, ge=0, description="Random seed for reproducibility")

    # --- Presolve and linearization ---
    cp_model_presolve: bool = Field(
        True, description="Enable presolver before search (default: True)"
    )
    linearization_level: int = Field(
        0, ge=0, le=2, description="Level of linearization: 0 = off, 1 = basic, 2 = aggressive"
    )

    # --- Stop criteria / optimality ---
    stop_after_first_solution: bool = Field(
        False, description="Stop immediately after first feasible solution"
    )
    stop_after_presolve: bool = Field(
        False, description="Stop after presolve phase (diagnostics only)"
    )
    relative_gap_limit: float = Field(
        0.0, ge=0.0, le=1.0, description="Relative optimality gap tolerance (0 = exact)"
    )
    absolute_gap_limit: float = Field(0.0, ge=0.0, description="Absolute optimality gap tolerance")

    # --- Heuristics and randomization ---
    use_optional_variables: bool = Field(
        False, description="Allow optional variables for stochastic branching"
    )
    search_randomization_tolerance: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Tolerance for randomization in search heuristics (0 = deterministic)",
    )

    # --- Resource limits ---
    max_num_conflicts: int | None = Field(
        None, ge=1, description="Maximum allowed number of conflicts before stop"
    )
    max_num_branches: int | None = Field(
        None, ge=1, description="Maximum number of branches before stop"
    )
    max_memory_in_mb: int | None = Field(None, ge=128, description="Memory limit for solver (MB)")
    max_delta: float = Field(
        0.0, ge=0.0, description="Relative improvement threshold (anytime search)"
    )

    # --- SAT-level and internal processing ---
    use_sat_inprocessing: bool = Field(True, description="Enable SAT in-processing during search")

    # --- Logging / debug ---
    log_to_stdout: bool = Field(True, description="Print solver logs to stdout")


class Config(_StrictBaseModel):
    """
    Runtime configuration loaded from config.yaml.
    """

    time_unit: float = Field(0.0833, gt=0.0, description="Tick size in hours (5 min = 1/12 h)")
    rooms_max: int = Field(20, ge=1, description="Maximum number of operating rooms")
    shift_min: float = Field(5.0, gt=0.0, description="Minimum shift length (hours)")
    shift_max: float = Field(12.0, gt=0.0, description="Maximum shift length (hours)")
    shift_overtime: float = Field(9.0, ge=0.0, description="Overtime threshold (hours)")
    overtime_multiplier: float = Field(1.5, ge=1.0, description="Overtime cost multiplier")
    buffer: float = Field(
        0.25, gt=0.0, description="Room-change buffer in hours (e.g. 0.25 = 15 min)"
    )
    utilization_target: float = Field(
        0.8, ge=0.0, le=1.0, description="Required minimum utilization (0..1)"
    )
    enforce_surgery_duration_limit: bool = Field(
        True, description="Reject surgeries longer than shift_max if True"
    )
    timezone: str = Field("UTC", description="IANA timezone name, e.g. 'UTC'")
    solver: SolverConfig = Field(default_factory=SolverConfig.model_construct)


class SolutionRow(_StrictBaseModel):
    """
    Represents one record in solution.csv.
    """

    surgery_id: str = Field(..., description="Surgery identifier (must exist in input)")
    start_time: datetime = Field(..., description="Scheduled start time (ISO-8601)")
    end_time: datetime = Field(..., description="Scheduled end time (ISO-8601)")
    anesthetist_id: str = Field(..., description="Assigned anesthesiologist ID")
    room_id: str = Field(..., description="Assigned operating room ID")


__all__ = ["Surgery", "Config", "SolutionRow", "SolverConfig"]
