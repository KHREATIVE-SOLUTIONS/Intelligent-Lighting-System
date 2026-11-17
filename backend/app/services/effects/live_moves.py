"""
Movement vocabulary for the live renderer
==========================================

The positions a lighting designer programs on a console: symmetric tilts,
mirrored circles, fans that sweep, beams that fly out. Each is built on the
truss's own centre line rather than on a fixture's place in a list, which is
what makes a look symmetric: a head knows how far it is from centre and which
side it is on, pan is mirrored across the centre and tilt is shared.

Conventions, in the engine's degrees (0 is the DMX centre of each axis):

* pan 0, tilt 0 is the head pointing straight down.
* Tilt leans the beam along the room's depth. Negative tilt leans it downstage,
  toward the audience (+Z); positive leans it upstage. This is the previs's
  convention. A real head can be hung either way round, which is what a
  per-fixture invert is for - the engine does not have one yet.
* `u` is a head's place on its truss: -1 at the left end, 0 at centre, +1 at the
  right end. Mirrored heads have opposite `u`.
* `row_dir` is which way a truss leans to face the room: -1 for a truss that
  leans downstage (upstage and centre trusses), +1 for a downstage truss that
  leans back toward the booth. Fanning outward needs the pan sign flipped with
  it, because pan turns whichever way the head is leaning.

Every pattern returns a lean from vertical and a pan. Left and right heads
with the same |u| always get the same lean and opposite pan, so every pattern
here is mirror-symmetric by construction. tests/unit/test_live_moves.py holds
that property.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

PATTERNS: Tuple[str, ...] = (
    "sym_tilt", "tilt_ripple", "circle", "figure8", "fan_sweep", "fly_out",
)
DEFAULT_PATTERN = "sym_tilt"


@dataclass(frozen=True)
class SectionMotion:
    """How big and how slow a section moves."""

    pan_amp: float      # degrees of pan swing in circles and sweeps
    tilt_amp: float     # degrees of tilt swing about the aim
    fan: float          # degrees the outermost head is fanned out
    cycle_beats: float  # beats for one full movement; whole bars, so moves end on a bar line


# Bigger and slower than the wiggle these replaced. A move that takes a bar or
# two and covers real distance reads as designed; a two-beat cycle over twenty
# degrees reads as jitter.
SECTION_MOTION: Dict[str, SectionMotion] = {
    "breakdown": SectionMotion(pan_amp=14.0, tilt_amp=10.0, fan=20.0, cycle_beats=16.0),
    "verse": SectionMotion(pan_amp=22.0, tilt_amp=16.0, fan=30.0, cycle_beats=8.0),
    "buildup": SectionMotion(pan_amp=30.0, tilt_amp=22.0, fan=40.0, cycle_beats=8.0),
    "chorus": SectionMotion(pan_amp=34.0, tilt_amp=24.0, fan=45.0, cycle_beats=4.0),
    "drop": SectionMotion(pan_amp=42.0, tilt_amp=30.0, fan=55.0, cycle_beats=4.0),
}
DEFAULT_MOTION = SECTION_MOTION["verse"]

SECTION_POOLS: Dict[str, Tuple[str, ...]] = {
    "breakdown": ("sym_tilt", "fan_sweep"),
    "verse": ("sym_tilt", "circle", "fan_sweep", "tilt_ripple"),
    "buildup": ("fly_out", "circle", "tilt_ripple"),
    "chorus": ("circle", "fan_sweep", "figure8", "sym_tilt"),
    "drop": ("fly_out", "circle", "figure8"),
}
DEFAULT_POOL: Tuple[str, ...] = ("sym_tilt", "circle", "fan_sweep", "figure8", "tilt_ripple")

# Where a truss rests: leaning this far toward the room, so the beams land on
# the floor in front of it rather than straight down onto the truss's shadow.
AIM_DEG = 22.0
# How far from vertical a beam may lean. A little past vertical the other way
# is allowed so a swing can cross straight-down; 68 keeps a fly-out off the
# horizontal, where it would be in the audience's eyes.
LEAN_MIN_DEG = -8.0
LEAN_MAX_DEG = 68.0
FLY_IN_LEAN_DEG = 6.0

# What a moving head can do. The engine never asks for more, so the wire never
# carries a step a fixture has to chase, and a change of pattern is a glide.
MAX_PAN_DEG_PER_S = 240.0
MAX_TILT_DEG_PER_S = 180.0


def head_target(
    pattern: str,
    *,
    u: float,
    row_dir: float,
    row_index: int,
    beats: float,
    motion: SectionMotion,
    speed: float = 1.0,
    amp: float = 1.0,
) -> Tuple[float, float]:
    """(pan, tilt) in engine degrees for one head at one moment.

    `beats` is the engine's beat clock, so every movement is in time. `speed`
    and `amp` are the club style's lean on the section's own motion.
    """
    u = max(-1.0, min(1.0, float(u)))
    spread = abs(u)
    # The way a head turns in a circle or sweep. A centre head has no side, so
    # it turns with the right-hand half rather than standing still.
    turn = -1.0 if u < -1e-6 else 1.0
    row_dir = 1.0 if row_dir > 0 else -1.0

    cycle = max(0.5, float(motion.cycle_beats) / max(0.1, float(speed)))
    theta = 2.0 * math.pi * (float(beats) / cycle)
    pan_amp = motion.pan_amp * amp
    tilt_amp = motion.tilt_amp * amp
    fan = motion.fan * amp

    if pattern == "circle":
        # Mirrored circles: the two halves of the truss turn opposite ways.
        # Successive trusses run a quarter turn apart, for depth.
        th = theta + row_index * (math.pi / 2.0)
        out = 0.6 * fan * u + turn * pan_amp * math.sin(th)
        lean = AIM_DEG + tilt_amp * math.cos(th)
    elif pattern == "figure8":
        th = theta + row_index * (math.pi / 2.0)
        out = 0.5 * fan * u + turn * pan_amp * math.sin(th)
        lean = AIM_DEG + 0.8 * tilt_amp * math.sin(2.0 * th)
    elif pattern == "fan_sweep":
        # The fan opens and closes: beams sweep out to the walls and back in
        # together, with a slow nod so the sweep is not flat.
        out = fan * u + turn * pan_amp * math.sin(theta)
        lean = AIM_DEG + 0.3 * tilt_amp * math.cos(theta)
    elif pattern == "fly_out":
        # Beams gather under the truss, then fly up and out over the room, and
        # come back. The whole rig breathes together.
        opened = 0.5 - 0.5 * math.cos(theta)
        out = u * (0.15 * fan + 1.6 * fan * opened)
        lean = FLY_IN_LEAN_DEG + (AIM_DEG + 1.6 * tilt_amp - FLY_IN_LEAN_DEG) * opened
    elif pattern == "tilt_ripple":
        # A tilt that starts at the centre of the truss and runs out to both
        # ends at once.
        out = 0.9 * fan * u
        lean = AIM_DEG + tilt_amp * math.sin(theta - math.pi * spread)
    else:  # sym_tilt, and anything unrecognised
        # Every head on a truss tilts together, held in a static fan.
        # Alternate trusses run opposite, so one rises as the next falls.
        out = 0.9 * fan * u
        lean = AIM_DEG + tilt_amp * math.sin(theta + row_index * math.pi)

    lean = max(LEAN_MIN_DEG, min(LEAN_MAX_DEG, lean))
    # Leaning downstage is negative tilt. Pan turns the way the head leans, so
    # fanning outward flips with the truss's direction.
    return (-row_dir * out, row_dir * lean)


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
