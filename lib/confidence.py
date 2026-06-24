# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Pure confidence math — one impulse up, one exponential curve down.

Design principle #3: confidence is a function of usage *timestamps*, not an event
accumulator. Everything here is a pure function of (baseline, idle_days) — order-
independent, idempotent, and concurrency-safe by construction. No I/O, no config
reads: callers pass tunables in, so this module is trivially simulatable (see
tests/test_confidence_sim.py).

Two operations, identical for every engram regardless of channel:

  reinforce(c)            -- one use-event: diminishing-returns step toward CEIL.
                             Replaces the old hard min(0.95, c+0.02) wall.
  decay(base, idle_days)  -- exponential pull toward FLOOR after a grace period,
                             recomputed from the at-last-use baseline so it never
                             compounds across maintenance runs.

Equilibrium property: an engram used every D days settles where the per-use impulse
balances D days of decay, so equilibrium confidence encodes usage frequency for free
(daily-used settle high, monthly-used drift toward the floor).
"""

from __future__ import annotations

import math


def reinforce(confidence: float, alpha: float, ceiling: float) -> float:
    """One use-event impulse: move a fraction ALPHA of the remaining headroom.

    Diminishing returns — the closer to the ceiling, the smaller the step — so
    load-bearing engrams approach but never pile at a hard wall.
    """
    return round(confidence + alpha * (ceiling - confidence), 3)


def decay(
    base: float,
    idle_days: int,
    floor: float,
    half_life_days: float,
    grace_days: int,
) -> float:
    """Exponential decay of ``base`` toward ``floor`` after ``grace_days`` idle.

    Pure function of ``idle_days`` (= today - last_used), NOT of the previously
    decayed value — callers pass the at-last-use baseline every time, so running
    maintenance twice, or skipping days, yields the same result. Decay is measured
    from the end of the grace window, so there is no discontinuous jump at the edge.
    """
    if idle_days <= grace_days:
        return round(base, 3)
    if half_life_days <= 0:
        return round(base, 3)
    lam = math.log(2) / half_life_days
    effective_days = idle_days - grace_days
    return round(floor + (base - floor) * math.exp(-lam * effective_days), 3)
