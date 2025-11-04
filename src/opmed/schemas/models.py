# src/opmed/schemas/models.py
"""
@brief
Pydantic data models for the Opmed optimization project.

@details
Defines three canonical model types:
    - Surgery: represents a single input surgery record (from surgeries.csv)
    - Config: runtime configuration (from config.yaml), including nested SolverConfig
    - SolutionRow: represents one output record (for solution.csv)

Models strictly follow the field names and types specified in docs/schemas.md.
They remain intentionally lightweight — no heavy validators — to ensure stable
JSON Schema generation via `.model_json_schema()`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class _StrictBaseModel(BaseModel):
    """
    @brief
    Base model enforcing strict defaults for configuration and data contracts.

    @details
    Forbids unknown fields and preserves exact naming rules.
    Designed as a foundation for all other Opmed models.
    """

    model_config = {
        "extra": "forbid",  # Reject unknown fields
        "populate_by_name": True,  # Allow population by field name
        "use_enum_values": True,  # Export raw enum values if enums appear later
    }


class Surgery(_StrictBaseModel):
    """
    @brief
    Represents one surgery record from surgeries.csv.

    @details
    Contains start/end timestamps and optional duration and room ID.
    Intended for pre-validation and schedule generation steps.

    @params
        surgery_id : str
            Unique identifier of the surgery.
        start_time : datetime
            Surgery start time (ISO-8601 UTC unless Config.timezone provided).
        end_time : datetime
            Surgery end time (ISO-8601 UTC unless Config.timezone provided).
    """

    surgery_id: str = Field(..., description="Unique identifier")
    start_time: datetime = Field(..., description="Surgery start time (ISO-8601)")
    end_time: datetime = Field(..., description="Surgery end time (ISO-8601)")


# ------------------------------------------------------------
# Runtime I/O control block
# ------------------------------------------------------------
class IOPolicy(BaseModel):
    """
    @brief
    Controls runtime behavior for artifact and log writing.

    @details
    Used by orchestrator and ResultStore to determine whether to
    write metrics, configuration snapshots, and solver logs.
    """

    write_artifacts: bool = Field(
        True,
        description="If False, disables writing solution.json, metrics.json, config_snapshot.json.",
    )
    write_solver_logs: bool = Field(
        False,
        description="If True, writes detailed OR-Tools logs to solver.log.",
    )


class SolverConfig(_StrictBaseModel):
    """
    @brief
    Complete CP-SAT solver configuration.

    @details
    Compatible with tuning interface v3.2.10.
    Covers both production parameters and all hyperparameters used for tuning.
    Default values are chosen for stable and reproducible runs.
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


class VisualConfig(BaseModel):
    """
    @brief
    Visualization parameters for plot rendering.

    @details
    Defines figure dimensions and DPI for matplotlib visualizations.
    """

    width: float = Field(19.0, description="Figure width in inches")
    height: float = Field(10.0, description="Figure height in inches")
    dpi: int = Field(150, description="Output figure DPI")


class ExperimentConfig(BaseModel):
    """
    @brief
    Metadata describing the experiment or run context.

    @details
    Used for tagging, naming, and describing experiments.
    """

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class ValidationConfig(BaseModel):
    """
    @brief
    Controls behavior of validation subsystem.

    @details
    Determines whether to generate a report and whether warnings
    should be treated as failures.
    """

    write_report: bool = True
    fail_on_warnings: bool = False


class MetricsConfig(BaseModel):
    """
    @brief
    Controls metrics persistence.

    @details
    Flags for saving metrics.json and solver logs.
    """

    save_metrics: bool = True
    save_solver_log: bool = True


class VisualizationConfig(BaseModel):
    """
    @brief
    Visualization output configuration.

    @details
    Controls figure saving and rendering quality.
    """

    save_plot: bool = True
    dpi: int = 120


class Config(_StrictBaseModel):
    """
    @brief
    Represents the full runtime configuration loaded from config.yaml.

    @details
    Combines solver, visualization, validation, and experiment settings.
    Provides all parameters necessary for reproducible optimization runs.
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

    activation_penalty: float = Field(
        0.0,
        ge=0.0,
        description=(
            "Weight (penalty) added to the objective function for each active anesthesiologist; "
            "0 disables this term."
        ),
    )

    timezone: str = Field("UTC", description="IANA timezone name, e.g. 'UTC'")
    solver: SolverConfig = Field(default_factory=SolverConfig.model_construct)
    visual: VisualConfig = Field(default_factory=VisualConfig.model_construct)

    # --- additional fields for YAML support ---
    surgeries_csv: str | None = None
    output_dir: str | None = "data/output"
    io_policy: IOPolicy = Field(default_factory=IOPolicy.model_construct)
    validation: ValidationConfig = Field(default_factory=ValidationConfig.model_construct)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig.model_construct)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig.model_construct)
    experiment: ExperimentConfig = Field(default_factory=ExperimentConfig.model_construct)


class SolutionRow(_StrictBaseModel):
    """
    @brief
    Represents one record in solution.csv.

    @details
    Defines the output schedule assignment for a single surgery,
    including anesthetist and room allocation.
    """

    surgery_id: str = Field(..., description="Surgery identifier (must exist in input)")
    start_time: datetime = Field(..., description="Scheduled start time (ISO-8601)")
    end_time: datetime = Field(..., description="Scheduled end time (ISO-8601)")
    anesthetist_id: str = Field(..., description="Assigned anesthesiologist ID")
    room_id: str = Field(..., description="Assigned operating room ID")


__all__ = ["Surgery", "Config", "SolutionRow", "SolverConfig"]
