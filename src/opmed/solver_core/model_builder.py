"""
ModelBuilder: CP-SAT model construction for Opmed.

Builds fixed-time intervals, decision grids (x, y), and core constraints:
- NoOverlap by rooms and anesthesiologists (optional intervals)
- Inter-room buffer as logical forbiddance (same anesth ⇒ same room for “dangerous” pairs)
- Shift duration bounds linked to assigned surgeries (t_min/t_max/active)
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model

from opmed.schemas.models import Config, Surgery

logger = logging.getLogger(__name__)

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
        self._add_constraints()
        self._add_objective_piecewise_cost()

        return {
            "model": self.model,
            "vars": self.vars,
            "aux": self.aux,
            "surgeries": self.surgeries,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_variable_groups(self) -> None:
        """
        @brief
        Initializes the primary container `self.vars`, a nested dictionary
        used to organize all CP-SAT decision variables created by the model builder.

        @details
        This structure acts as a registry that groups together different types of
        variables — interval, assignment, and activity flags — under separate keys.
        It allows other methods to populate or reference them consistently.

        Variable groups:
            - "interval": cp_model.IntervalVar objects representing surgery time blocks.
            - "x": cp_model.BoolVar grid [surgery, anesthesiologist], defining assignment
                   of anesthesiologists to surgeries.
            - "y": cp_model.BoolVar grid [surgery, room], defining which room each
                   surgery is assigned to.
            - "active": Optional BoolVar flags, reserved for future constraints (e.g., active/inactive surgeries).

        @params
        None (relies on class attributes such as self.model).

        @returns
        None. Initializes `self.vars` and logs the result.

        @raises
        None explicitly. Any inconsistency in key naming will later cause KeyErrors
        during variable population, so this structure must stay synchronized
        with the creation methods (`_create_intervals`, `_create_boolean_vars`, etc.).
        """

        # (1) Define top-level groups for variable storage
        #     Each sub-dict will later hold variables indexed by tuple or int keys.
        self.vars = {"x": {}, "y": {}, "interval": {}, "active": {}}

        # (2) Log which variable groups are now available for population
        logger.debug("Initialized variable groups: %s", list(self.vars.keys()))

    def _create_intervals(self) -> None:
        """
        @brief
        Creates one **fixed CP-SAT IntervalVar** per surgery based on its known start and end times.
        Unlike standard interval variables, these are *not decision variables* — they represent
        immutable real-world time slots. The intervals are registered in `self.vars["interval"]`.

        @details
        Each surgery has pre-defined start_time and end_time in absolute UTC datetimes.
        This method converts those times into discrete "ticks" according to the configured
        time resolution (`cfg.time_unit`), determines the model’s origin timestamp
        (midnight of the earliest surgery day), and creates OR-Tools FixedSizeIntervalVars.
        It also stores auxiliary temporal data (`start_ticks`, `end_ticks`, `max_time_ticks`)
        inside `self.aux` for later use (e.g., buffer constraints, time horizon).

        @params
        None (uses instance attributes):
            - self.cfg.time_unit : float
                Fraction of an hour representing one tick (e.g., 0.25 for 15 min).
            - self.surgeries : list[Surgery]
                Collection of surgery records with start_time and end_time fields.
            - self.model : cp_model.CpModel
                The CP-SAT model instance where intervals will be created.

        @returns
        None. All results are written into:
            - self.vars["interval"] : dict[int, cp_model.IntervalVar]
            - self.aux["t_origin"], ["ticks_per_hour"], ["start_ticks"], ["end_ticks"], etc.

        @raises
        None explicitly, but logs warnings for surgeries with zero or negative duration
        (which are auto-corrected to duration = 1 tick).
        """

        # (1) Guard clause: handle the case with no surgeries to avoid empty iteration
        if not self.surgeries:
            logger.warning("No surgeries provided, skipping interval creation.")
            return

        # (2) Convert time resolution (e.g., 0.25 h per tick → 4 ticks/hour)
        ticks_per_hour = int(round(1 / self.cfg.time_unit))

        # (3) Determine model’s time origin (t=0): midnight of earliest surgery day (UTC)
        min_start_time = min(s.start_time for s in self.surgeries)
        t_origin = min_start_time.replace(hour=0, minute=0, second=0, microsecond=0)

        # (4) Store origin and resolution info for later back-conversion to datetime
        self.aux["t_origin"] = t_origin
        self.aux["ticks_per_hour"] = ticks_per_hour

        # (5) Prepare containers for converted tick-based start/end coordinates
        start_ticks_list: list[int] = []
        end_ticks_list: list[int] = []
        max_tick = 0

        # (6) Iterate over surgeries and construct corresponding fixed intervals
        for s_idx, surgery in enumerate(self.surgeries):
            # (6.1) Compute elapsed seconds from origin for start and end
            start_seconds = (surgery.start_time - t_origin).total_seconds()
            end_seconds = (surgery.end_time - t_origin).total_seconds()

            # (6.2) Convert seconds to discrete ticks
            start_ticks = int(round((start_seconds / 3600) * ticks_per_hour))
            end_ticks = int(round((end_seconds / 3600) * ticks_per_hour))
            duration_ticks = end_ticks - start_ticks

            # (6.3) Guard against zero or negative durations due to rounding errors
            if duration_ticks <= 0:
                logger.warning(
                    "Surgery %s at %s has non-positive duration (%d ticks). "
                    "Forcing duration to 1 tick.",
                    surgery.surgery_id,
                    surgery.start_time,
                    duration_ticks,
                )
                duration_ticks = 1
                end_ticks = start_ticks + 1

            # (6.4) Create a fixed-size CP-SAT interval variable (immutable time window)
            interval_var = self.model.NewFixedSizeIntervalVar(
                start_ticks,
                duration_ticks,
                f"interval_s{s_idx}",
            )
            self.vars["interval"][s_idx] = interval_var

            # (6.5) Record converted coordinates
            start_ticks_list.append(start_ticks)
            end_ticks_list.append(end_ticks)

            # (6.6) Update maximum tick for overall model horizon
            if end_ticks > max_tick:
                max_tick = end_ticks

        # (7) Store time-related data for use in later model-building steps
        self.aux["start_ticks"] = start_ticks_list
        self.aux["end_ticks"] = end_ticks_list
        self.aux["max_time_ticks"] = max_tick
        self.aux["buffer_ticks"] = int(round(self.cfg.buffer / self.cfg.time_unit))

        # (8) Log creation summary for traceability and debugging
        logger.debug(
            "Created %d FixedSizeIntervalVar objects (fixed time, horizon=%d ticks)",
            len(self.surgeries),
            max_tick,
        )

    def _create_boolean_vars(self) -> None:
        """
        @brief
        Creates the binary (boolean) decision variables that represent assignment
        relationships in the CP-SAT scheduling model.

        @details
        Two main grids of BoolVars are generated:
            - **x[s,a]**: equals 1 if anesthesiologist `a` is assigned to surgery `s`;
              0 otherwise. This grid allows modeling of who performs each surgery.
            - **y[s,r]**: equals 1 if surgery `s` is assigned to room `r`; 0 otherwise.
              This grid encodes spatial allocation of surgeries to operating rooms.

        These boolean variables form the basis of the model’s assignment and exclusivity
        constraints (e.g., “each surgery has exactly one anesthesiologist and one room”,
        “no anesthesiologist can perform two surgeries at once,” etc.).

        @params
        None (uses instance attributes):
            - self.surgeries : list[Surgery]
                The list of surgeries to be scheduled.
            - self.cfg.rooms_max : int
                The number of available operating rooms from configuration.
            - self.model : cp_model.CpModel
                OR-Tools model object used to instantiate BoolVars.

        @returns
        None. The created BoolVars are stored in `self.vars["x"]` and `self.vars["y"]`.

        @raises
        None explicitly. Logs debugging information with grid dimensions.
        """

        # (1) Determine logical upper bounds for variable grids:
        #     - maximum possible number of anesthesiologists (one per surgery)
        #     - number of available operating rooms (from configuration)
        max_anesth = len(self.surgeries)
        num_rooms = self.cfg.rooms_max

        # (2) Create BoolVars for anesthesiologist assignments: x[s,a]
        #     Represents "anesthesiologist a is assigned to surgery s"
        for s_idx in range(len(self.surgeries)):
            for a_idx in range(max_anesth):
                # (2.1) Create a uniquely named BoolVar and register in the dict
                self.vars["x"][(s_idx, a_idx)] = self.model.NewBoolVar(f"x_s{s_idx}_a{a_idx}")

        # (3) Create BoolVars for room assignments: y[s,r]
        #     Represents "surgery s is assigned to room r"
        for s_idx in range(len(self.surgeries)):
            for r_idx in range(num_rooms):
                # (3.1) Create a uniquely named BoolVar and register in the dict
                self.vars["y"][(s_idx, r_idx)] = self.model.NewBoolVar(f"y_s{s_idx}_r{r_idx}")

        # (4) Log creation summary with grid sizes for traceability
        logger.debug(
            "Created BoolVar grids: x[%d×%d] (surgeries×anesth), y[%d×%d] (surgeries×rooms)",
            len(self.surgeries),
            max_anesth,
            len(self.surgeries),
            num_rooms,
        )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def _add_constraints(self) -> None:
        """
        @brief
        Aggregates and applies all major structural constraints that define
        the feasible region of the CP-SAT scheduling model.

        @details
        This method orchestrates the sequential addition of constraint families
        responsible for ensuring logical and temporal consistency in the model.
        Each called helper method encapsulates a particular rule or domain restriction:

            - `_add_assignment_cardinality()`:
                Enforces that each surgery is assigned to exactly one anesthesiologist
                and exactly one room (sum-to-one rules for assignment grids).

            - `_add_room_nooverlap()`:
                Ensures that no two surgeries share the same room during overlapping times.

            - `_add_anesth_nooverlap()`:
                Prevents a single anesthesiologist from being assigned to overlapping surgeries.

            - `_add_buffer_constraints()`:
                Inserts time buffers between consecutive surgeries for hygiene or setup.

            - `_add_shift_duration_bounds()`:
                Enforces working time limits (e.g., max shift length, overtime bounds).

        @params
        None (relies on instance state — model, variables, config).

        @returns
        None. Modifies the internal CP-SAT model in place by adding constraints.

        @raises
        None explicitly, but consistency issues in sub-methods (e.g. missing variables)
        may raise KeyError or ValueError during model assembly.
        """

        # (1) Log start of constraint-building phase
        logger.debug("Building structural constraints…")

        # (2) Apply "sum-to-one" constraints on assignment grids (who & where)
        self._add_assignment_cardinality()

        # (3) Add non-overlap constraints for operating rooms
        self._add_room_nooverlap()

        # (4) Add non-overlap constraints for anesthesiologists
        self._add_anesth_nooverlap()

        # (5) Add setup/cleanup buffers between consecutive surgeries
        self._add_buffer_constraints()

        # (6) Add shift-level duration and overtime limits
        self._add_shift_duration_bounds()

        # (7) Log total number of constraints added to the model
        logger.debug(
            "Completed constraint assembly; total constraints: %d",
            len(self.model.Proto().constraints),
        )

    def _add_assignment_cardinality(self) -> None:
        """
        @brief
        Enforces that every surgery is assigned to exactly one anesthesiologist
        and exactly one operating room.

        @details
        Uses the "sum-to-one" pattern typical for assignment problems:
            ∑ₐ x[s,a] = 1    — each surgery has exactly one anesthesiologist
            ∑ᵣ y[s,r] = 1    — each surgery takes exactly one room

        These constraints guarantee mutual exclusivity and ensure that
        all surgeries are properly staffed and located. Must be called
        after `_create_boolean_vars()` to ensure the variables exist.

        @params
        None (operates on internal model state).

        @returns
        None. Adds constraints directly to the CP-SAT model.
        """

        # (1) Validate input data and derive configuration limits
        num_surgeries = len(self.surgeries)
        if num_surgeries == 0:
            logger.debug("No surgeries; skipping assignment cardinality.")
            return

        max_anesth = num_surgeries
        num_rooms = self.cfg.rooms_max

        # (2) For each surgery, add ExactlyOne constraints for both dimensions
        for s_idx in range(num_surgeries):
            # Build lists of BoolVars for anesthesiologist and room assignment
            anesth_vars = [self.vars["x"][(s_idx, a_idx)] for a_idx in range(max_anesth)]
            room_vars = [self.vars["y"][(s_idx, r_idx)] for r_idx in range(num_rooms)]

            # Add “sum-to-one” constraints for this surgery
            self.model.AddExactlyOne(anesth_vars)
            self.model.AddExactlyOne(room_vars)

        # (3) Log summary information for debugging
        logger.debug(
            "Added ExactlyOne constraints for %d surgeries (rooms & anesthesiologists)",
            num_surgeries,
        )

    def _add_room_nooverlap(self) -> None:
        """
        @brief
        Prevents time conflicts between surgeries assigned to the same room
        by applying per-room non-overlap constraints.

        @details
        Each room `r` has an associated list of *optional intervals*,
        one for every surgery `s`. These intervals are activated
        only when the assignment variable `y[s,r] = 1`, meaning
        that surgery `s` is placed in room `r`.

        OR-Tools' `AddNoOverlap()` constraint is then applied to
        each room’s list of active intervals, ensuring that no two
        simultaneously assigned surgeries overlap in time within
        the same physical room.

        Implementation steps:
            1. Iterate over all rooms defined in configuration.
            2. For each room, collect a list of optional intervals
               conditioned on `y[s,r]`.
            3. Apply `AddNoOverlap(optional_intervals)` to enforce
               temporal exclusivity within that room.

        @params
        None (relies on internal state: `self.model`, `self.vars`, `self.cfg`).

        @returns
        None. Adds constraints directly to the CP-SAT model.
        """

        # (1) Retrieve number of available rooms from configuration
        num_rooms = self.cfg.rooms_max

        # (2) Loop through all rooms and build NoOverlap constraints
        for r_idx in range(num_rooms):
            # Collect all optional intervals corresponding to this room
            optional_intervals = []

            for s_idx in range(len(self.surgeries)):
                # The Boolean “switch”: surgery s_idx assigned to room r_idx?
                y_var = self.vars["y"][(s_idx, r_idx)]

                # The base fixed interval representing the surgery time window
                base_interval = self.vars["interval"][s_idx]

                # Create a conditional interval that becomes active only if y[s,r] = 1
                opt_interval = self.model.NewOptionalIntervalVar(
                    base_interval.StartExpr(),  # fixed start tick
                    base_interval.SizeExpr(),  # fixed duration
                    base_interval.EndExpr(),  # fixed end tick
                    y_var,  # activation flag
                    f"interval_s{s_idx}_r{r_idx}",
                )
                optional_intervals.append(opt_interval)

            # Apply non-overlap rule: no two active intervals in the same room may intersect
            self.model.AddNoOverlap(optional_intervals)

        # (3) Log summary for debugging and verification
        logger.debug("Added NoOverlap constraints for %d rooms", num_rooms)

    def _add_anesth_nooverlap(self) -> None:
        """
        @brief
        Ensures that no anesthesiologist is assigned to overlapping surgeries.

        @details
        For each potential anesthesiologist `a`, a set of optional intervals
        is created—one per surgery `s`. Each interval becomes active only if
        the corresponding assignment variable `x[s,a] = 1`, indicating that
        anesthesiologist `a` performs surgery `s`.

        Applying `AddNoOverlap(optional_intervals)` for every anesthesiologist
        guarantees that two active surgeries assigned to the same person cannot
        overlap in time. This enforces the physical constraint that one
        anesthesiologist can handle only one surgery at a time.

        The model uses as many anesthesiologists as there are surgeries, letting
        the solver implicitly choose how many are actually utilized.

        @params
        None (relies on internal state: `self.model`, `self.vars`, `self.surgeries`).

        @returns
        None. Adds NoOverlap constraints to the CP-SAT model.
        """

        # (1) Define the number of potential anesthesiologists (equal to # of surgeries)
        max_anesth = len(self.surgeries)

        # (2) For each anesthesiologist, build and apply a NoOverlap constraint
        for a_idx in range(max_anesth):
            optional_intervals = []

            # Collect optional intervals representing all surgeries possibly assigned to a_idx
            for s_idx in range(len(self.surgeries)):
                x_var = self.vars["x"][(s_idx, a_idx)]
                base_interval = self.vars["interval"][s_idx]

                opt_interval = self.model.NewOptionalIntervalVar(
                    base_interval.StartExpr(),  # fixed start tick
                    base_interval.SizeExpr(),  # fixed duration
                    base_interval.EndExpr(),  # fixed end tick
                    x_var,  # activation condition
                    f"interval_s{s_idx}_a{a_idx}",
                )
                optional_intervals.append(opt_interval)

            # Add mutual exclusion constraint for this anesthesiologist
            self.model.AddNoOverlap(optional_intervals)

        # (3) Log how many anesthesiologist constraints were created
        logger.debug(
            "Added NoOverlap constraints for %d potential anesthesiologists",
            len(self.surgeries),
        )

    def _add_buffer_constraints(self) -> None:
        """
        @brief
        Enforces safety buffers between surgeries assigned to the same anesthesiologist
        but located in different rooms too close in time. (Optimized version)

        @details
        Logical rule implemented:
            For each pair of surgeries (s1, s2) such that
                s1.end ≤ s2.start < s1.end + BUFFER,
            enforce:
                (x[s1,a] ∧ x[s2,a]) → same_room(s1, s2)

        This optimized variant prevents combinatorial explosion.
        The "same_room" Boolean is computed once per surgery pair, not per anesthesiologist.
        """

        # (1) Retrieve timing parameters and constants
        buffer_ticks = self.aux["buffer_ticks"]
        max_anesth = len(self.surgeries)
        num_rooms = self.cfg.rooms_max

        # (2) Access precomputed start/end ticks from self.aux
        start_ticks = self.aux["start_ticks"]
        end_ticks = self.aux["end_ticks"]

        # (3) Identify “dangerous” pairs violating the buffer time rule
        dangerous_pairs: list[tuple[int, int]] = []
        for s1_idx in range(len(self.surgeries)):
            for s2_idx in range(len(self.surgeries)):
                if s1_idx == s2_idx:
                    continue
                s1_end = end_ticks[s1_idx]
                s2_start = start_ticks[s2_idx]
                if s1_end <= s2_start < s1_end + buffer_ticks:
                    dangerous_pairs.append((s1_idx, s2_idx))

        if not dangerous_pairs:
            logger.debug("No dangerous surgery pairs found; skipping buffer constraints.")
            return

        logger.debug(
            "Detected %d potentially conflicting surgery pairs (buffer=%d ticks)",
            len(dangerous_pairs),
            buffer_ticks,
        )

        # (4) For each “dangerous pair” first compute the shared-room flag
        for s1, s2 in dangerous_pairs:

            # --- Manager creates a “sticker” ---
            # Boolean B: both surgeries share the same room.
            b_same_room = self.model.NewBoolVar(f"b_sameR_s{s1}_s{s2}")
            both_in_room_vars = []

            for r_idx in range(num_rooms):
                b_both_in_r = self.model.NewBoolVar(f"b_both_r{r_idx}_s{s1}_s{s2}")

                # Use AddBoolAnd for logical conjunction instead of separate implications
                self.model.AddBoolAnd(
                    [self.vars["y"][(s1, r_idx)], self.vars["y"][(s2, r_idx)]]
                ).OnlyEnforceIf(b_both_in_r)
                self.model.AddBoolOr(
                    [self.vars["y"][(s1, r_idx)].Not(), self.vars["y"][(s2, r_idx)].Not()]
                ).OnlyEnforceIf(b_both_in_r.Not())

                both_in_room_vars.append(b_both_in_r)

            # Aggregate “same room” condition
            self.model.AddBoolOr(both_in_room_vars).OnlyEnforceIf(b_same_room)
            self.model.Add(sum(both_in_room_vars) == 0).OnlyEnforceIf(b_same_room.Not())

            # (5) Iterate over anesthesiologists and apply the implication rule
            for a_idx in range(max_anesth):

                # --- Manager checks the employee ---
                # Boolean A: both surgeries assigned to the same anesthesiologist
                b_same_anesth_lit = self.model.NewBoolVar(f"b_sameA_lit_a{a_idx}_s{s1}_s{s2}")
                self.model.AddBoolAnd(
                    [self.vars["x"][(s1, a_idx)], self.vars["x"][(s2, a_idx)]]
                ).OnlyEnforceIf(b_same_anesth_lit)

                # (6) Core logical rule: if same anesth (A) → must share same room (B)
                self.model.AddImplication(b_same_anesth_lit, b_same_room)

        # (7) Log summary
        logger.debug(
            "Added OPTIMIZED buffer consistency rules for %d pairs",
            len(dangerous_pairs),
        )

    def _add_shift_duration_bounds(self) -> None:
        """
        @brief
        Adds lower and upper bounds on anesthesiologists’ working shifts.

        @details
        Uses AddMinEquality / AddMaxEquality so that t_min[a] and t_max[a]
        reflect the earliest and latest assigned surgeries.
        """

        # (1) Compute shift duration parameters in ticks
        ticks_per_hour = int(round(1 / self.cfg.time_unit))
        shift_max = int(round(self.cfg.shift_max * ticks_per_hour))
        max_anesth = len(self.surgeries)

        start_ticks = self.aux["start_ticks"]
        end_ticks = self.aux["end_ticks"]
        horizon = self.aux["max_time_ticks"]

        self.vars["t_min"] = {}
        self.vars["t_max"] = {}
        self.vars["active"] = {}

        # (2) Create variables and constraints per anesthesiologist
        for a_idx in range(max_anesth):
            t_min = self.model.NewIntVar(0, horizon, f"tmin_a{a_idx}")
            t_max = self.model.NewIntVar(0, horizon, f"tmax_a{a_idx}")
            active = self.model.NewBoolVar(f"active_a{a_idx}")

            self.vars["t_min"][a_idx] = t_min
            self.vars["t_max"][a_idx] = t_max
            self.vars["active"][a_idx] = active

            # (3) Determine active status via assigned surgeries
            x_vars = [self.vars["x"][(s_idx, a_idx)] for s_idx in range(len(self.surgeries))]
            self.model.AddBoolOr(x_vars).OnlyEnforceIf(active)
            for x in x_vars:
                self.model.Add(x == 0).OnlyEnforceIf(active.Not())
                self.model.AddImplication(x, active)

            # (4) Compute t_min/t_max proxies using assigned intervals
            start_candidates = []
            end_candidates = []
            for s_idx in range(len(self.surgeries)):
                start_var = self.model.NewIntVar(0, horizon, f"start_a{a_idx}_s{s_idx}")
                end_var = self.model.NewIntVar(0, horizon, f"end_a{a_idx}_s{s_idx}")
                self.model.Add(start_var == start_ticks[s_idx]).OnlyEnforceIf(
                    self.vars["x"][(s_idx, a_idx)]
                )
                self.model.Add(start_var == horizon).OnlyEnforceIf(
                    self.vars["x"][(s_idx, a_idx)].Not()
                )
                self.model.Add(end_var == end_ticks[s_idx]).OnlyEnforceIf(
                    self.vars["x"][(s_idx, a_idx)]
                )
                self.model.Add(end_var == 0).OnlyEnforceIf(self.vars["x"][(s_idx, a_idx)].Not())
                start_candidates.append(start_var)
                end_candidates.append(end_var)

            # Cannot apply .OnlyEnforceIf to AddMin/MaxEquality.
            # Proxy variables ensure unconditional equality.
            t_min_active = self.model.NewIntVar(0, horizon, f"tmin_active_a{a_idx}")
            t_max_active = self.model.NewIntVar(0, horizon, f"tmax_active_a{a_idx}")

            self.model.AddMinEquality(t_min_active, start_candidates)
            self.model.AddMaxEquality(t_max_active, end_candidates)

            self.model.Add(t_min == t_min_active).OnlyEnforceIf(active)
            self.model.Add(t_max == t_max_active).OnlyEnforceIf(active)

            # (5) Enforce shift duration bounds
            self.model.Add(t_max - t_min <= shift_max).OnlyEnforceIf(active)

            self.model.Add(t_min == 0).OnlyEnforceIf(active.Not())
            self.model.Add(t_max == 0).OnlyEnforceIf(active.Not())

        logger.debug(
            "Added strict shift duration bounds (AddMinEquality/AddMaxEquality) for %d anesthesiologists",
            max_anesth,
        )

    # ------------------------------------------------------------------
    # Objective Function
    # ------------------------------------------------------------------

    def _add_objective_piecewise_cost(self) -> None:
        """
        @brief
        Builds a piecewise-linear cost function for anesthesiologist shifts
        and sets it as the model’s objective to minimize total workload cost.

        @details
        Each anesthesiologist a has shift duration (t_max[a] - t_min[a]).
        The cost models pay and overtime penalties:
            cost[a] = max(SHIFT_MIN, duration) + 0.5 * max(0, duration - SHIFT_OVERTIME)
        scaled by 2 to keep integer arithmetic.

        For inactive anesthesiologists, cost2[a] = 0.
        """

        # (1) Convert config parameters from hours to ticks
        ticks_per_hour = int(round(1 / self.cfg.time_unit))
        shift_min = int(round(self.cfg.shift_min * ticks_per_hour))
        shift_overtime = int(round(self.cfg.shift_overtime * ticks_per_hour))
        max_anesth = len(self.surgeries)
        horizon = self.aux["max_time_ticks"]

        # (2) Initialize storage for cost variables
        self.vars.setdefault("cost", {})
        cost_terms: list[cp_model.IntVar] = []

        # (3) Build cost structure per anesthesiologist
        for a_idx in range(max_anesth):
            t_min = self.vars["t_min"][a_idx]
            t_max = self.vars["t_max"][a_idx]
            active = self.vars["active"][a_idx]

            # (3.1) Compute shift duration
            duration = self.model.NewIntVar(0, horizon, f"duration_a{a_idx}")
            self.model.Add(duration == t_max - t_min)

            # (3.2) Base part: at least SHIFT_MIN
            base_part = self.model.NewIntVar(0, horizon, f"base_a{a_idx}")
            self.model.AddMaxEquality(base_part, [duration, shift_min])

            # (3.3) Overtime part: positive excess beyond SHIFT_OVERTIME
            ov_diff = self.model.NewIntVar(-horizon, horizon, f"ov_diff_a{a_idx}")
            self.model.Add(ov_diff == duration - shift_overtime)
            overtime_part = self.model.NewIntVar(0, horizon, f"overtime_a{a_idx}")
            self.model.AddMaxEquality(overtime_part, [ov_diff, 0])

            # (3.4) Combine scaled cost
            cost2 = self.model.NewIntVar(0, 3 * horizon, f"cost2_a{a_idx}")
            self.model.Add(cost2 == 2 * base_part + overtime_part).OnlyEnforceIf(active)
            self.model.Add(cost2 == 0).OnlyEnforceIf(active.Not())

            self.vars["cost"][a_idx] = cost2
            cost_terms.append(cost2)

        # (4) Define global objective
        activation_penalty: int = getattr(self.cfg, "activation_penalty", 0) or 0
        shortfall_penalty_coeff = int(round(activation_penalty / self.cfg.time_unit))
        shortfall_terms: list[cp_model.IntVar] = []

        for a_idx in range(max_anesth):
            active = self.vars["active"][a_idx]
            duration = self.model.NewIntVar(0, horizon, f"dur_copy_a{a_idx}")
            self.model.Add(duration == self.vars["t_max"][a_idx] - self.vars["t_min"][a_idx])
            shortfall = self.model.NewIntVar(0, shift_min, f"shortfall_a{a_idx}")
            diff = self.model.NewIntVar(-horizon, horizon, f"short_diff_a{a_idx}")
            self.model.Add(diff == shift_min - duration)
            self.model.AddMaxEquality(shortfall, [diff, 0])
            penalty_term = self.model.NewIntVar(
                0, shift_min * shortfall_penalty_coeff, f"penalty_short_a{a_idx}"
            )
            # Penalty applied only if anesthesiologist is active
            self.model.Add(penalty_term == shortfall * shortfall_penalty_coeff).OnlyEnforceIf(
                active
            )
            self.model.Add(penalty_term == 0).OnlyEnforceIf(active.Not())
            shortfall_terms.append(penalty_term)

        if activation_penalty == 0:
            # Variant 1 — baseline objective
            logger.debug("Objective: TotalShiftCost (activation_penalty=0)")
            self.model.Minimize(sum(cost_terms) + sum(shortfall_terms))
        else:
            # Variant 2 — extended objective with activation and room penalties
            active_vars = list(self.vars.get("active", {}).values())
            num_rooms = self.cfg.rooms_max
            room_used_vars = []

            for r_idx in range(num_rooms):
                b_room_used = self.model.NewBoolVar(f"room_used_r{r_idx}")
                self.model.AddBoolOr(
                    [self.vars["y"][(s_idx, r_idx)] for s_idx in range(len(self.surgeries))]
                ).OnlyEnforceIf(b_room_used)
                for s_idx in range(len(self.surgeries)):
                    self.model.Add(self.vars["y"][(s_idx, r_idx)] == 0).OnlyEnforceIf(
                        b_room_used.Not()
                    )
                room_used_vars.append(b_room_used)

            logger.debug(
                "Objective: TotalShiftCostWithActivation (activation_penalty=%s, active_vars=%d, rooms=%d)",
                activation_penalty,
                len(active_vars),
                len(room_used_vars),
            )

            total_cost = (
                sum(cost_terms)
                + sum(shortfall_terms)
                + activation_penalty * sum(active_vars)
                + activation_penalty * sum(room_used_vars)
            )
            self.model.Minimize(total_cost)

        # (5) Log completion
        logger.debug(
            "Added piecewise cost objective for %d anesthesiologists (conditional on active)",
            max_anesth,
        )
