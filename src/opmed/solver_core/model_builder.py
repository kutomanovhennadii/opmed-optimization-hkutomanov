"""
model_builder.py — placeholder module for Opmed project.
@brief Auto-generated stub.
@remarks To be implemented in future Epics.
"""

from __future__ import annotations

from typing import Any

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery

CpSatModelBundle = dict[str, Any]


class ModelBuilder:
    """
    Constructs the CP-SAT model for anesthesiologist scheduling.

    Step 5.1.2: create IntervalVar for each surgery and BoolVar for
    anesthesiologist/room assignment.
    """

    def __init__(self, cfg: Config, surgeries: list[Surgery]) -> None:
        """Initialize ModelBuilder with configuration and validated surgeries."""
        self.cfg = cfg
        self.surgeries = surgeries
        self.model = cp_model.CpModel()
        self.vars: dict[str, Any] = {}
        self.aux: dict[str, Any] = {}

    def build(self) -> CpSatModelBundle:
        """Main entry point for building the CP-SAT model."""
        self._init_variable_groups()
        self._create_intervals()
        self._create_boolean_vars()
        # Placeholders for next steps:
        # self._add_constraints()
        # self._add_objective()
        return {"model": self.model, "vars": self.vars, "aux": self.aux}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_variable_groups(self) -> None:
        """Initialize variable groups dictionary."""
        self.vars = {"x": {}, "y": {}, "interval": {}}

    def _create_intervals(self) -> None:
        """Create IntervalVar for each surgery (start, duration, end)."""
        ticks_per_hour = int(round(1 / self.cfg.time_unit))

        for s_idx, surgery in enumerate(self.surgeries):
            duration_hours = (surgery.end_time - surgery.start_time).total_seconds() / 3600
            duration_ticks = int(round(duration_hours * ticks_per_hour))

            start_var = self.model.NewIntVar(0, 24 * ticks_per_hour, f"start_s{s_idx}")
            end_var = self.model.NewIntVar(0, 24 * ticks_per_hour, f"end_s{s_idx}")

            interval_var = self.model.NewIntervalVar(
                start_var, duration_ticks, end_var, f"interval_s{s_idx}"
            )
            self.vars["interval"][s_idx] = interval_var

    def _create_boolean_vars(self) -> None:
        """Create BoolVar for surgery–anesthesiologist and surgery–room mapping."""
        num_anesth = 3  # placeholder; dynamic creation will come later
        num_rooms = min(self.cfg.rooms_max, 3)

        for s_idx in range(len(self.surgeries)):
            for a_idx in range(num_anesth):
                self.vars["x"][(s_idx, a_idx)] = self.model.NewBoolVar(f"x_s{s_idx}_a{a_idx}")

        for s_idx in range(len(self.surgeries)):
            for r_idx in range(num_rooms):
                self.vars["y"][(s_idx, r_idx)] = self.model.NewBoolVar(f"y_s{s_idx}_r{r_idx}")
