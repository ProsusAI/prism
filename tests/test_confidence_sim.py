# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Simulation harness for the confidence protocol (confidence_plan.md §8).

Validates the *pure math* (lib/confidence.py) against synthetic multi-day,
multi-session usage traces BEFORE it is wired into live mechanics. Models exactly
what reinforce_entries + cmd_maintain will do:

  - a use_event fires reinforce(), daily-idempotent (>=1 session/day == 1 impulse);
  - the live confidence is decay(confidence_base, idle_days since last_used);
  - reinforce recomputes the current value from the base first, so an engram that
    decayed before being used again builds its impulse on the decayed value.

Assertions (the plan's §8 acceptance criteria):
  A. No inflation under N parallel sessions/day (1 session == 10 sessions).
  B. Equilibrium confidence tracks usage frequency (daily > weekly > monthly).
  C. Rotation: an abandoned engram decays monotonically and crosses the archive
     threshold (leaves prism.md); a steadily-hot one does not.
  D. No flap: a steadily-used engram settles into a tight band (no oscillation).

Run: python3 -m tests.test_confidence_sim   (or pytest)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.confidence import decay, reinforce  # noqa: E402

# Default tunables under test (mirror config.py DEFAULT_CONFIG).
ALPHA = 0.15
CEIL = 1.0
FLOOR = 0.1
HALF_LIFE_DAYS = 28      # decay_half_life_weeks = 4
GRACE = 3
ARCHIVE_THRESHOLD = 0.2  # config archive_threshold


class Engram:
    """Mirror of an index entry's confidence state under the new protocol."""

    def __init__(self, start: float = 0.5):
        self.base = start          # confidence_base: value at last use-event
        self.last_used = 0         # day index of last use (0 = "created on day 0")
        self.confidence = start    # live/effective confidence

    def use(self, day: int) -> None:
        """A use_event (overlap-detected or MCP retrieval), daily-idempotent."""
        if self.last_used == day:
            return  # already credited today -- kills multi-session inflation
        current = decay(self.base, day - self.last_used, FLOOR, HALF_LIFE_DAYS, GRACE)
        self.base = reinforce(current, ALPHA, CEIL)
        self.last_used = day
        self.confidence = self.base

    def maintain(self, day: int) -> None:
        """Daily decay pass -- pure function of idle days, never compounds."""
        self.confidence = decay(self.base, day - self.last_used, FLOOR, HALF_LIFE_DAYS, GRACE)


def run_trace(use_days: set[int], sessions_per_use_day: int, horizon: int, start: float = 0.5):
    """Simulate one engram over `horizon` days. Returns the daily confidence series."""
    e = Engram(start)
    series = []
    for day in range(1, horizon + 1):
        if day in use_days:
            for _ in range(sessions_per_use_day):  # N parallel sessions same day
                e.use(day)
        e.maintain(day)
        series.append(e.confidence)
    return series


def _every(n: int, horizon: int) -> set[int]:
    return {d for d in range(1, horizon + 1) if d % n == 0}


def test_a_no_parallel_session_inflation():
    horizon = 60
    days = _every(1, horizon)  # used every day
    one = run_trace(days, sessions_per_use_day=1, horizon=horizon)
    ten = run_trace(days, sessions_per_use_day=10, horizon=horizon)
    assert one == ten, "parallel sessions inflated confidence (daily guard broken)"


def test_b_equilibrium_tracks_frequency():
    horizon = 90
    daily = run_trace(_every(1, horizon), 1, horizon)[-1]
    weekly = run_trace(_every(7, horizon), 1, horizon)[-1]
    monthly = run_trace(_every(30, horizon), 1, horizon)[-1]
    assert daily > weekly > monthly, f"frequency not encoded: {daily=} {weekly=} {monthly=}"


def test_c_rotation_abandoned_vs_hot():
    horizon = 180
    # Hot: used daily the whole time.
    hot = run_trace(_every(1, horizon), 1, horizon)
    # Abandoned: used daily for the first 20 days, then never again.
    abandoned_days = {d for d in range(1, 21)}
    ab = run_trace(abandoned_days, 1, horizon)

    # Hot stays well above the archive line for the entire run.
    assert min(hot[30:]) > ARCHIVE_THRESHOLD, "hot engram dipped below archive threshold"
    # Abandoned decays monotonically after abandonment...
    tail = ab[25:]
    assert all(b <= a + 1e-9 for a, b in zip(tail, tail[1:])), "abandoned engram not monotonic"
    # ...and eventually crosses the archive threshold (rotates out).
    crossed = next((d for d, c in enumerate(ab, 1) if c < ARCHIVE_THRESHOLD), None)
    assert crossed is not None, "abandoned engram never crossed archive threshold"
    assert ab[-1] < hot[-1], "abandoned not clearly below hot at horizon"
    return crossed


def test_d_no_flap_steady_engram():
    horizon = 120
    series = run_trace(_every(1, horizon), 1, horizon)
    band = series[-30:]
    assert max(band) - min(band) < 0.01, f"steady engram oscillated: band={max(band) - min(band):.4f}"


if __name__ == "__main__":
    test_a_no_parallel_session_inflation()
    test_b_equilibrium_tracks_frequency()
    crossed = test_c_rotation_abandoned_vs_hot()
    test_d_no_flap_steady_engram()

    # Summary table for the human.
    H = 90
    daily = run_trace(_every(1, H), 1, H)[-1]
    weekly = run_trace(_every(7, H), 1, H)[-1]
    monthly = run_trace(_every(30, H), 1, H)[-1]
    print("All assertions passed.\n")
    print(f"  Equilibrium @ {H}d (ALPHA={ALPHA}, half-life={HALF_LIFE_DAYS}d, "
          f"grace={GRACE}, floor={FLOOR}):")
    print(f"    daily-used   : {daily:.3f}")
    print(f"    weekly-used  : {weekly:.3f}")
    print(f"    monthly-used : {monthly:.3f}")
    print(f"  Abandoned-after-20d engram crosses archive ({ARCHIVE_THRESHOLD}) on day {crossed}.")
