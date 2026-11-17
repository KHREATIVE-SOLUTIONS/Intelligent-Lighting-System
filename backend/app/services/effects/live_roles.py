"""
Fixture roles for the live renderer
===================================

A lighting designer does not run every fixture the same way. Beams carry the
movement and the chase. Washes are the bed: a steady field of a second colour
that the beams cut through. Bars are eye candy with a pattern of their own.
Strobes stay dark until there is something to accent.

Before this, every fixture that could not move was given the same level on
every frame, so a rig of bars, pars and strobes read as one flat block pumping
with the music - and a strobe glowed white all night.

Two rules keep these roles from making the show less safe:

* **Redistribute, never add.** A role shapes a family's level downward from
  what it had, and moves light between fixtures rather than raising the total,
  so the rig's overall brightness swings no more than it did.
* **Strobes only ever flash when the governed accent flash is on.** They add no
  flash of their own.
"""

from __future__ import annotations

import colorsys
import math
from typing import Dict, Tuple

BEAM = "beam"       # moving heads: movement and the chase
WASH = "wash"       # moving washes: a steady bed from above
BED = "bed"         # static washes and pars: a steady bed from the room
BAR = "bar"         # LED bars: their own pattern
ACCENT = "accent"   # strobes: dark until an accent

# A moving wash holds this fraction of the section's level, steady. A bed sits
# under the beams so they cut through it. It also must not be brighter than
# the chase it replaced: at 0.9 the rig was brighter through a build than it
# had been, which took 0.02 off the step into the drop and failed the drop
# anticipation contract. 0.8 is level with the old chase; 0.7 leaves margin.
WASH_LEVEL = 0.7

# Beats for one pass of the bar pattern. A section with no entry has no bar
# pattern: the breakdown is calm and the drop is one sustained look.
BAR_CYCLE_BEATS: Dict[str, float] = {"verse": 4.0, "buildup": 2.0, "chorus": 2.0}
BAR_FLOOR = 0.2

# The bed breathes by this much, over two bars.
BED_BREATH = 0.15
BED_BREATH_BEATS = 8.0

# How far round the wheel the bed's colour sits from the beams' colour. Close
# by in the quiet sections, opposite when the song is at its biggest.
SECONDARY_HUE_SHIFT_DEG: Dict[str, float] = {
    "breakdown": 30.0, "verse": 40.0, "buildup": 60.0, "chorus": 150.0, "drop": 180.0,
}
DEFAULT_HUE_SHIFT_DEG = 40.0


def role_for(fixture_type: str, moves: bool, rig_has_beams: bool) -> str:
    """The part a fixture plays, from what it is and what else is in the rig."""
    kind = str(fixture_type or "").lower()
    if kind == "strobe":
        return ACCENT
    if kind in ("bar", "led_bar"):
        return BAR
    if moves:
        # A moving wash is the bed only if something else carries the chase.
        # On a rig whose only moving lights are washes, they are the beams.
        return WASH if (kind == "wash" and rig_has_beams) else BEAM
    return BED


def bar_shape(u: float, row_index: int, beats: float, section: str) -> float:
    """A bar's share of its level, 0..1: a pulse running from the centre of the
    row out to both ends, with alternate rows answering each other."""
    cycle = BAR_CYCLE_BEATS.get(section)
    if not cycle:
        return 1.0
    phase = float(beats) / cycle - 0.5 * abs(float(u)) + 0.5 * (int(row_index) % 2)
    wave = 0.5 + 0.5 * math.cos(2.0 * math.pi * phase)
    return BAR_FLOOR + (1.0 - BAR_FLOOR) * wave * wave


def bed_shape(row_index: int, beats: float) -> float:
    """A bed fixture's share of its level: alternate rows breathe against each
    other, so the bed moves while its total stays level."""
    sign = 1.0 if int(row_index) % 2 == 0 else -1.0
    return (1.0 - BED_BREATH) + BED_BREATH * sign * math.sin(2.0 * math.pi * float(beats) / BED_BREATH_BEATS)


def secondary_colour(r: float, g: float, b: float, section: str) -> Tuple[float, float, float]:
    """The bed's colour: the beams' colour turned round the wheel, same
    saturation and brightness."""
    h, s, v = colorsys.rgb_to_hsv(max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
    shift = SECONDARY_HUE_SHIFT_DEG.get(section, DEFAULT_HUE_SHIFT_DEG) / 360.0
    return colorsys.hsv_to_rgb((h + shift) % 1.0, s, v)


def truss_places(fixtures) -> Dict[str, Tuple[float, int]]:
    """Each fixture's place on its row: (u, row_index).

    Rows are fixtures sharing a depth. `u` runs -1 at the left end to +1 at the
    right, about the row's own centre, so mirrored fixtures have opposite `u`.
    """
    rows: Dict[float, list] = {}
    for fx in fixtures:
        rows.setdefault(round(float(getattr(fx, "z", 0.0)), 2), []).append(fx)
    places: Dict[str, Tuple[float, int]] = {}
    for row_index, z in enumerate(sorted(rows)):
        xs = [float(getattr(fx, "x", 0.0)) for fx in rows[z]]
        mid = (min(xs) + max(xs)) / 2.0
        half = (max(xs) - min(xs)) / 2.0
        for fx, x in zip(rows[z], xs):
            places[str(fx.id)] = ((x - mid) / half if half > 1e-6 else 0.0, row_index)
    return places
