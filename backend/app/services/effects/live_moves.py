"""
How fast a moving head may be asked to move
===========================================

The looks themselves - positions, motions, who moves when - live in
`live_looks`. This is the last step before a pan and tilt reach a fixture: the
engine never asks for a bigger move in one frame than a head can make, so the
wire never carries a step a fixture has to chase, and a change of look is a
glide rather than a jump.
"""

from __future__ import annotations

# What a moving head can do, in degrees per second.
MAX_PAN_DEG_PER_S = 240.0
MAX_TILT_DEG_PER_S = 180.0


def slew(previous: float, target: float, max_rate_deg_per_s: float, dt: float) -> float:
    """Move from `previous` toward `target` no faster than a head can travel."""
    if not (0.0 < dt <= 0.25):
        dt = 1.0 / 60.0
    step = max_rate_deg_per_s * dt
    delta = target - previous
    if delta > step:
        return previous + step
    if delta < -step:
        return previous - step
    return target
