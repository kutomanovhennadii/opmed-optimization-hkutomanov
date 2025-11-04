# scripts/gen_synthetic_data.py
from __future__ import annotations

import csv
import math
import random
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

"""
Synthetic surgery generator (single-run → single CSV file).

Design (per spec):
- Parameters are hard-coded as constants below (no CLI args).
- Time discretization: 5 minutes (ticks).
- For each operating room we generate a sequential chain of surgeries:
    start at 00:00 on EPOCH day, each surgery has random duration (0 < d ≤ 12h),
    then a random gap (5 min .. 2 h), and so on until the horizon ends.
- The global start of the covered period is 00:00 (EPOCH), but individual surgeries
  in different rooms start later according to the per-room chain.
- Overlaps across rooms are allowed; within a room there are no overlaps by construction.
- Output CSV columns (ADR-005): surgery_id,start_time,end_time (ISO-8601, UTC, tz-aware)

Edit the constants in the "CONFIG" section to produce different datasets
(number of rooms, horizon length in days, output filename, duration/gap ranges).
"""

# =========================
# CONFIG — EDIT THESE
# =========================
ROOMS: int = 16  # number of operating rooms (>= 1)
DAYS: int = 3  # horizon length in whole days (>= 1)
OUTPUT: str = f"data/input/synthetic_{DAYS}d_{ROOMS}r.csv"  # output CSV path

# Duration and gap constraints (minutes), all must be multiples of TICK_MINUTES
TICK_MINUTES: int = 5
MIN_DURATION_MIN: int = 30  # > 0
MAX_DURATION_MIN: int = 5 * 60  # ≤ 12 hours
MIN_GAP_MIN: int = 5  # between surgeries in the same room
MAX_GAP_MIN: int = 2 * 60

# Fixed epoch for 00:00 reference (tz-aware UTC)
EPOCH: datetime = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# Deterministic generation
RANDOM_SEED: int = 42
# =========================


@dataclass(frozen=True, slots=True)
class SurgeryRow:
    surgery_id: str
    start_time: datetime
    end_time: datetime


def _ensure_dirs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _is_multiple_of_tick(minutes: int) -> bool:
    return minutes % TICK_MINUTES == 0


def _rand_duration_minutes() -> int:
    """Random duration in minutes, strictly > 0 and ≤ MAX_DURATION_MIN, quantized by tick."""
    # Use an integer number of ticks in [min_ticks, max_ticks]
    min_ticks = math.ceil(MIN_DURATION_MIN / TICK_MINUTES)
    max_ticks = math.floor(MAX_DURATION_MIN / TICK_MINUTES)
    ticks = random.randint(min_ticks, max_ticks)
    return ticks * TICK_MINUTES


def _rand_gap_minutes() -> int:
    """Random gap after a surgery, quantized by tick."""
    min_ticks = max(1, math.ceil(MIN_GAP_MIN / TICK_MINUTES))
    max_ticks = max(1, math.floor(MAX_GAP_MIN / TICK_MINUTES))
    ticks = random.randint(min_ticks, max_ticks)
    return ticks * TICK_MINUTES


def _generate_room_chain(
    room_index: int,
    start_epoch: datetime,
    horizon_minutes: int,
    start_id_counter: int,
) -> tuple[list[SurgeryRow], int]:
    """
    Generate a sequential chain of surgeries for a single room within [0, horizon_minutes].

    Returns:
        (rows, next_id_counter)
    """
    rows: list[SurgeryRow] = []
    t_cursor_min = 0
    sid = start_id_counter

    while t_cursor_min < horizon_minutes:
        duration_min = _rand_duration_minutes()
        # Clip duration to horizon end; if remaining is too small for MIN_DURATION_MIN — stop.
        remaining = horizon_minutes - t_cursor_min
        if remaining < MIN_DURATION_MIN:
            break
        if duration_min > remaining:
            # Fit the last surgery exactly to the horizon if it still respects MIN_DURATION_MIN
            duration_min = remaining - ((remaining - MIN_DURATION_MIN) % TICK_MINUTES)
            # Re-check in case remaining == MIN_DURATION_MIN-ε rounded
            if duration_min < MIN_DURATION_MIN:
                break

        start_dt = start_epoch + timedelta(minutes=t_cursor_min)
        end_dt = start_epoch + timedelta(minutes=t_cursor_min + duration_min)

        sid += 1
        rows.append(SurgeryRow(surgery_id=f"S{sid:05d}", start_time=start_dt, end_time=end_dt))

        # Advance cursor by a gap; if exceeds horizon, loop will end
        gap_min = _rand_gap_minutes()
        t_cursor_min += duration_min + gap_min

    return rows, sid


def _write_csv(path: Path, rows: Iterable[SurgeryRow]) -> None:
    _ensure_dirs(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["surgery_id", "start_time", "end_time"])
        for r in rows:
            # datetime.isoformat() includes "+00:00" for tz-aware UTC
            writer.writerow([r.surgery_id, r.start_time.isoformat(), r.end_time.isoformat()])


def _validate_config_or_die() -> None:
    problems: list[str] = []
    if ROOMS < 1:
        problems.append("ROOMS must be >= 1")
    if DAYS < 1:
        problems.append("DAYS must be >= 1")
    if MIN_DURATION_MIN <= 0:
        problems.append("MIN_DURATION_MIN must be > 0")
    if MAX_DURATION_MIN < MIN_DURATION_MIN:
        problems.append("MAX_DURATION_MIN must be >= MIN_DURATION_MIN")
    if not all(
        _is_multiple_of_tick(x)
        for x in (MIN_DURATION_MIN, MAX_DURATION_MIN, MIN_GAP_MIN, MAX_GAP_MIN)
    ):
        problems.append(
            "MIN/MAX duration and gap must be multiples of TICK_MINUTES "
            f"(current tick={TICK_MINUTES} min)"
        )
    if problems:
        msg = "Invalid generator configuration:\n- " + "\n- ".join(problems)
        print(msg, file=sys.stderr)
        sys.exit(2)


def main() -> int:
    _validate_config_or_die()
    random.seed(RANDOM_SEED)

    output = Path(OUTPUT)
    horizon_minutes = DAYS * 24 * 60

    all_rows: list[SurgeryRow] = []
    id_counter = 0

    # Generate per-room sequential chains
    for room_idx in range(ROOMS):
        rows, id_counter = _generate_room_chain(
            room_index=room_idx,
            start_epoch=EPOCH,
            horizon_minutes=horizon_minutes,
            start_id_counter=id_counter,
        )
        all_rows.extend(rows)

    # Sort globally by start_time for convenience
    all_rows.sort(key=lambda r: (r.start_time, r.end_time, r.surgery_id))

    _write_csv(output, all_rows)

    # Simple progress logging
    total = len(all_rows)
    total_hours = (all_rows[-1].end_time - EPOCH).total_seconds() / 3600 if total else 0.0
    print(
        f"[GEN] rooms={ROOMS}, days={DAYS}, surgeries={total}, "
        f"horizon_hours={DAYS*24}, last_end≈{total_hours:.2f}h"
    )
    print(f"[GEN] wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
