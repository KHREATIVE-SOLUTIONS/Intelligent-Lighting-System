"""
A look's dimmer effect, on the live renderer
============================================

Every look in the look library names a dimmer effect and a chase style: a
chase running forward, bouncing or opening from the centre; alternate heads
swapping on the beat; a spot going round the rig; a ramp. Until now the live
renderer ignored them and ran one chase of its own under every look, so two
looks could move differently and were always lit the same way.

The shapes here are the ones the April 2026 engine performed (commit fada2e3,
`_update_fixtures_rebuild`, "Layer 3: dimmer effects"), carried over onto the
beat clock and onto each head's place on its truss:

* ``static``           every beam level.
* ``chase``            a spot travelling along each truss, `chase_width` wide,
                       once every `chase_beats`: ``forward``, ``bounce`` (there
                       and back) or ``center_out`` (from the middle of the
                       truss to both ends).
* ``circular``         a wider spot going round the whole rig: along one truss
                       and back along the next.
* ``ramp``             a soft-edged bar sweeping across and back over twice
                       `chase_beats`.
* ``odd_even``         alternate heads swap on every beat.
* ``kick_clap``        the same swap, the other way round. It was written to
                       follow real kick and snare hits, with this beat-clock
                       swap as its fallback. The drum detector that fed it was
                       measured and cannot separate drums, so the fallback is
                       what runs.
* ``left_right_kick``  the left half and the right half of the rig swap on
                       every beat. Same history as ``kick_clap``.

**What is not here.** How bright a look is (`base_dimmer`, `chase_intensity`),
its bumps, its strobe and blinder modes, its colour and its fixture groups.
The shapes are normalised to a peak of one and the level comes from the
renderer, as before.

**The rule that keeps this safe: redistribute, never add.** `levels` takes a
ceiling - the mean the beams had under the renderer's own chase on that frame
- and fits the look's shape to it: scaled down if it averages more, filled
from underneath if it averages less. The beams' mean is never above the
ceiling and no head is ever above one. So a look moves light between heads;
nothing here can make a section brighter or add a flash. Alternating effects cross over a short ramp,
with the two halves always summing to one, so the rig's total does not blink
when they swap.

Effects that open from the centre (``center_out``) and ``static`` light left
and right alike. The others are meant not to: a spot travels from one end to
the other, sides take turns, neighbours alternate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence

# Effects this module performs. Anything else is treated as ``static``.
EFFECTS = ("static", "chase", "circular", "ramp", "odd_even", "kick_clap", "left_right_kick")
DIRECTIONS = ("forward", "bounce", "center_out", "none")

# An alternating effect crosses from one half to the other over this many
# beats, centred on the beat line: about 55 ms at 128 BPM. Long enough that no
# head snaps from black to full in one frame, short enough to read as a swap.
EDGE_BEATS = 0.12

# How much of the gap under the ceiling is filled when a look's shape lights
# fewer heads than the chase it replaces. 1.0 holds the beams' total where it
# was, so a look changes the picture and not how bright the room is. 0.0 is
# the shape alone on black: more contrast, and on the bench a chorus 30%
# dimmer (rig mean 0.089 to 0.062), on a show already too dim.
FILL = 1.0

# A change of look crosses from the old shape to the new one over this many
# beats, so the phrase line is a change of picture and not a jump in level.
CROSSFADE_BEATS = 2.0


@dataclass(frozen=True)
class BeamPlace:
    """Where one beam sits, as the effects need to know it."""

    along: float   # 0 at the left end of its truss, 1 at the right end
    lap: float     # the same, as an evenly spaced slot on a loop: for a spot that wraps
    out: float     # 0 at the centre of its truss, 1 at either end
    side: int      # -1 left of centre, +1 right. A centre head counts as right.
    step: int      # 0 or 1: alternate heads along the truss
    ring: float    # 0..1 round the whole rig: along one truss, back along the next


@dataclass(frozen=True)
class DimmerLook:
    """The part of a library look this module performs."""

    effect: str = "static"
    direction: str = "forward"
    beats: float = 4.0     # beats for one pass of a chase
    width: float = 0.22    # width of the chase spot, as a share of the truss


STATIC = DimmerLook()


def dimmer_of(look) -> DimmerLook:
    """A library look's dimmer effect and chase style. None is a level rig."""
    if look is None:
        return STATIC
    effect = str(getattr(look, "dimmer_effect", "") or "static").lower()
    direction = str(getattr(look, "chase_direction", "") or "forward").lower()
    return DimmerLook(
        effect=effect if effect in EFFECTS else "static",
        direction=direction if direction in DIRECTIONS else "forward",
        beats=max(0.25, float(getattr(look, "chase_beats", 4.0) or 4.0)),
        width=max(0.05, min(1.0, float(getattr(look, "chase_width", 0.22) or 0.22))),
    )


def beam_places(fixtures: Sequence) -> Dict[str, BeamPlace]:
    """Each beam's place on its truss and round the rig.

    Rows are fixtures sharing a depth, left to right. Alternate heads are
    neighbours along the truss, starting the other way round on the next
    truss, so the two halves of an odd/even swap are the same size (or one
    head apart on a rig with an odd number). Counting from the centre outward
    instead would mirror left and right, and was tried: on a truss of six it
    makes halves of four and two, and the rig's total blinks on every beat.
    """
    rows: Dict[float, list] = {}
    for fx in fixtures:
        rows.setdefault(round(float(getattr(fx, "z", 0.0)), 2), []).append(fx)
    total = sum(len(members) for members in rows.values())
    places: Dict[str, BeamPlace] = {}
    seen = 0
    for row_index, z in enumerate(sorted(rows)):
        members = sorted(rows[z], key=lambda f: (float(getattr(f, "x", 0.0)), str(getattr(f, "id", ""))))
        xs = [float(getattr(f, "x", 0.0)) for f in members]
        mid = (min(xs) + max(xs)) / 2.0
        half = (max(xs) - min(xs)) / 2.0
        count = len(members)
        us = [((x - mid) / half if half > 1e-6 else 0.0) for x in xs]
        for rank, (fx, u) in enumerate(zip(members, us)):
            # Round the rig: left to right on one truss, right to left on the next.
            around = rank if row_index % 2 == 0 else (count - 1 - rank)
            places[str(fx.id)] = BeamPlace(
                along=(u + 1.0) / 2.0,
                lap=(rank + 0.5) / count,
                out=abs(u),
                side=-1 if u < -1e-6 else 1,
                step=(rank + row_index) % 2,
                ring=(seen + around + 0.5) / max(1, total),
            )
        seen += count
    return places


def _triangle(phase: float) -> float:
    """0 to 1 and back to 0 over one cycle."""
    phase = phase % 1.0
    return 2.0 * phase if phase <= 0.5 else 2.0 - 2.0 * phase


def _alternate(beats: float) -> float:
    """1 through even beats and 0 through odd ones, crossing over `EDGE_BEATS`.

    The crossing is centred on the beat line and is linear, so this and its
    complement always sum to one.
    """
    x = float(beats) % 2.0
    half = EDGE_BEATS / 2.0
    if x < half:
        return 0.5 + x / (2.0 * half)
    if x < 1.0 - half:
        return 1.0
    if x < 1.0 + half:
        return 0.5 - (x - 1.0) / (2.0 * half)
    if x < 2.0 - half:
        return 0.0
    return 0.5 + (x - 2.0) / (2.0 * half)


def _spot(distance: float, width: float) -> float:
    return math.exp(-(distance * distance) / (2.0 * width * width))


def share(look: DimmerLook, place: BeamPlace, beats: float) -> float:
    """One beam's share of the look's shape at this moment, 0..1, before the ceiling."""
    effect = look.effect
    if effect == "chase":
        position = (float(beats) / look.beats) % 1.0
        if look.direction == "bounce":
            distance = abs(place.along - _triangle(position))
        elif look.direction == "center_out":
            distance = abs(place.out - position)
            distance = min(distance, 1.0 - distance)
        else:
            distance = abs(place.lap - position)
            distance = min(distance, 1.0 - distance)
        return _spot(distance, look.width)
    if effect == "circular":
        wrapped = ((float(beats) / look.beats) + place.ring) % 1.0
        return (1.0 - abs(2.0 * wrapped - 1.0)) ** 2
    if effect == "ramp":
        progress = _triangle(float(beats) / (2.0 * look.beats))
        where = place.out if look.direction == "center_out" else place.along
        return max(0.0, 1.0 - abs(where - progress) * 3.0)
    if effect == "odd_even":
        gate = _alternate(beats)
        return gate if place.step == 0 else 1.0 - gate
    if effect == "kick_clap":
        gate = _alternate(beats)
        return gate if place.step == 1 else 1.0 - gate
    if effect == "left_right_kick":
        gate = _alternate(beats)
        return gate if place.side < 0 else 1.0 - gate
    return 1.0


def levels(
    look: DimmerLook,
    places: Mapping[str, BeamPlace],
    beats: float,
    ceiling_mean: float,
) -> Dict[str, float]:
    """Every beam's level under a look, as a share of the moment's energy.

    `ceiling_mean` is the most the beams may average. A shape that averages
    more is scaled down to it. One that averages less - a narrow chase lights
    one head in six - is filled from underneath toward it (`FILL`), every
    beam lifted by the same share of its distance from full, so the brightest
    stays the brightest and none goes above one. The beams' mean is never
    above the ceiling either way.
    """
    if not places:
        return {}
    shares = {fid: max(0.0, min(1.0, share(look, place, beats))) for fid, place in places.items()}
    mean = sum(shares.values()) / len(shares)
    ceiling = max(0.0, min(1.0, float(ceiling_mean)))
    if mean > ceiling:
        gain = ceiling / mean
        return {fid: value * gain for fid, value in shares.items()}
    if mean < ceiling and mean < 1.0 and FILL > 0.0:
        lift = min(1.0, FILL) * (ceiling - mean) / (1.0 - mean)
        return {fid: value + (1.0 - value) * lift for fid, value in shares.items()}
    return shares


def crossfaded(
    look: DimmerLook,
    previous: Optional[DimmerLook],
    places: Mapping[str, BeamPlace],
    beats: float,
    changed_at_beats: float,
    ceiling_mean: float,
) -> Dict[str, float]:
    """`levels`, crossing from the previous look's shape for `CROSSFADE_BEATS`.

    Both shapes sit under the ceiling, so every mix of them does.
    """
    now = levels(look, places, beats, ceiling_mean)
    if previous is None or previous == look:
        return now
    mix = (float(beats) - float(changed_at_beats)) / CROSSFADE_BEATS
    if mix >= 1.0:
        return now
    mix = max(0.0, mix)
    before = levels(previous, places, beats, ceiling_mean)
    return {fid: before.get(fid, 0.0) * (1.0 - mix) + value * mix for fid, value in now.items()}
