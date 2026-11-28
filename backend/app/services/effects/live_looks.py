"""
Looks for the live renderer: a position, a motion on top, and who moves when
=============================================================================

A movement only looks good from a good starting position, and the starting
position has to be uniform and symmetric on whatever rig is in the room. So a
look is built the way a console builds one - a position palette with an effect
laid over it - with one difference that makes it independent of the rig:

**a position is a point in the room for each head to aim at, not a pair of
angles.** "All centre" is every beam converging on one spot. "Cross" is each
side aiming across the centre line. The same angles on a truss twice as wide
would land somewhere else; the same points land in the same place.

Four layers:

* **Rig model** (`build_rig`): each moving head's place on its truss, which way
  its truss leans to face the room, and the point the rig plays to.
* **Position** (`POSITIONS`): a target point per head.
* **Motion**: the target moved in time, relative to the head, so its size is an
  angle and a share of the throw rather than a distance. `tilt` lengthens and
  shortens the throw, `sweep` swings it side to side, `circle` does both, and
  `fly` crosses from one position to another.
* **Phase**: every head together, a ripple from the centre of the truss
  outward, or alternate trusses opposite each other.

`aim` turns a target into pan and tilt for a head hanging at a known spot.

**Which look, when** is not decided here. Every sensible combination of the
layers is generated below as a named movement, and the look library
(`look_library`, through `live_library`) chooses among its own tagged looks
and names the movement each one uses.

Conventions, in the engine's degrees (0 is the DMX centre of each axis), and
matching the 3D view's `YXZ` head rotation:

* pan 0, tilt 0 points straight down.
* The beam's direction is (-sin t * sin p, -cos t, -sin t * cos p) for tilt t
  and pan p, with the body's yaw added to the pan. Negative tilt leans the beam
  downstage, toward the audience (+Z).
* Every beam direction has two pan/tilt answers. A head keeps the same one for
  the life of the rig: a truss that leans downstage tilts negative, one that
  leans back upstage tilts positive. Swapping answers mid-show would swing a
  lit beam round the room, so targets are always kept on the side of the head
  its truss faces, where pan stays inside a quarter turn either way.
* A target is never allowed under the head itself. Straight down is where pan
  stops meaning anything, and a circle round that point would spin the head.

Left and right heads at the same distance from centre always get mirrored
targets, so every look here is mirror-symmetric by construction.
tests/unit/test_live_looks.py holds that, on every demo rig.

What this cannot know: how a real head is hung. The yaw comes from the rig's
`rotation_y`; a head mounted upside down or with pan reversed needs a
per-fixture invert the engine does not have yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float, float]


# How far from vertical a beam may lean. 68 keeps a long throw off the
# horizontal, where it would be in the audience's eyes.
LEAN_MAX_DEG = 68.0
# Where a truss rests: its beams land this far in front of it, as a share of
# its height (tan 22 deg).
REST_THROW = 0.40
# A target is never closer to the point under the head than this share of the
# head's height.
MIN_THROW = 0.12
# How far out the outermost head of a fan lands, and how far across the centre
# line a crossed head aims, as a share of height and of its own offset.
FAN_SPREAD = 0.60
CROSS_REACH = 0.50


@dataclass(frozen=True)
class Head:
    """One moving head, as the looks need to know it."""

    fid: str
    x: float
    y: float
    z: float
    u: float                 # place on its truss: -1 left end, 0 centre, +1 right end
    row: int                 # which truss, upstage to downstage
    row_dir: float           # -1: the truss leans downstage (+Z). +1: it leans back upstage.
    yaw: float = 0.0         # degrees the body is turned; 0 faces downstage
    pan_range: float = 540.0
    tilt_range: float = 270.0

    @property
    def forward(self) -> float:
        """+1 or -1: the Z direction this head's truss faces."""
        return -1.0 if self.row_dir > 0 else 1.0


@dataclass(frozen=True)
class Rig:
    heads: Tuple[Head, ...]
    x_mid: float
    focus: Point             # the point the rig plays to
    by_id: Dict[str, Head]


def build_rig(fixtures: Sequence) -> Rig:
    """Read the geometry the looks need off any set of moving fixtures.

    Rows are fixtures sharing a depth. A row downstage of the middle leans back
    upstage; the rest lean downstage. The focus sits between the two groups, so
    every row has it in front of it - or, on a rig that all leans one way, a
    resting throw in front of the most downstage row.
    """
    rows: Dict[float, list] = {}
    for fx in fixtures:
        rows.setdefault(round(float(getattr(fx, "z", 0.0)), 2), []).append(fx)
    keys = sorted(rows)
    if not keys:
        return Rig((), 0.0, (0.0, 0.0, 0.0), {})

    z_mid = (keys[0] + keys[-1]) / 2.0
    z_half = (keys[-1] - keys[0]) / 2.0
    all_x = [float(getattr(fx, "x", 0.0)) for fx in fixtures]
    x_mid = (min(all_x) + max(all_x)) / 2.0

    heads: List[Head] = []
    downstage_leaning: List[Tuple[float, float]] = []   # (z, height) of rows that lean downstage
    upstage_leaning: List[float] = []
    for row_index, z in enumerate(keys):
        members = sorted(rows[z], key=lambda f: (float(getattr(f, "x", 0.0)), str(getattr(f, "id", ""))))
        xs = [float(getattr(f, "x", 0.0)) for f in members]
        row_mid = (min(xs) + max(xs)) / 2.0
        row_half = (max(xs) - min(xs)) / 2.0
        leans_upstage = z_half > 0.0 and (z - z_mid) > 0.33 * z_half
        height = sum(float(getattr(f, "y", 0.0)) for f in members) / len(members)
        if leans_upstage:
            upstage_leaning.append(z)
        else:
            downstage_leaning.append((z, height))
        for fx, x in zip(members, xs):
            heads.append(Head(
                fid=str(fx.id), x=x, y=float(getattr(fx, "y", 0.0)), z=z,
                u=(x - row_mid) / row_half if row_half > 1e-6 else 0.0,
                row=row_index, row_dir=1.0 if leans_upstage else -1.0,
                yaw=float(getattr(fx, "yaw", 0.0) or 0.0),
                pan_range=float(getattr(fx, "pan_range", 540.0) or 540.0),
                tilt_range=float(getattr(fx, "tilt_range", 270.0) or 270.0),
            ))

    if downstage_leaning and upstage_leaning:
        focus_z = (max(z for z, _ in downstage_leaning) + min(upstage_leaning)) / 2.0
    elif downstage_leaning:
        z, height = max(downstage_leaning)
        focus_z = z + REST_THROW * max(height, 1.0) * 2.0
    else:
        focus_z = min(upstage_leaning) - REST_THROW * 2.0
    return Rig(tuple(heads), x_mid, (x_mid, 0.0, focus_z), {h.fid: h for h in heads})


# ---------------------------------------------------------------------------
# Positions: a floor point for each head
# ---------------------------------------------------------------------------

def _rest_z(head: Head) -> float:
    return head.z + head.forward * REST_THROW * max(head.y, 1.0)


def position_centre(head: Head, rig: Rig) -> Point:
    """Every beam to one point: the floor the rig plays to."""
    return rig.focus


def position_columns(head: Head, rig: Rig) -> Point:
    """Parallel beams, each leaning the same way in front of its own truss."""
    return (head.x, 0.0, _rest_z(head))


def position_fan(head: Head, rig: Rig) -> Point:
    """Beams splayed outward, further the further a head is from centre."""
    return (head.x + head.u * FAN_SPREAD * max(head.y, 1.0), 0.0, _rest_z(head))


def position_cross(head: Head, rig: Rig) -> Point:
    """Each side aims across the centre line, so mirrored beams make an X."""
    return (rig.x_mid - (head.x - rig.x_mid) * CROSS_REACH, 0.0, _rest_z(head))


POSITIONS = {
    "centre": position_centre,
    "columns": position_columns,
    "fan": position_fan,
    "cross": position_cross,
}


# ---------------------------------------------------------------------------
# Looks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Look:
    position: str
    motion: str                   # hold | tilt | sweep | circle | fly
    phase: str = "unison"         # unison | ripple | rows
    to: Optional[str] = None      # for `fly`: the position it flies out to


PHASES: Tuple[str, ...] = ("unison", "ripple", "rows")
# A fly-out crosses between two positions; these are the crossings worth making.
FLY_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("centre", "fan"), ("columns", "fan"), ("columns", "cross"), ("centre", "columns"),
)


def _generate_looks() -> Dict[str, Look]:
    """Every sensible combination of the layers, named for what it is."""
    looks: Dict[str, Look] = {}
    for position in POSITIONS:
        looks[f"{position}_hold"] = Look(position, "hold", "unison")
        for motion in ("tilt", "sweep", "circle"):
            for phase in PHASES:
                looks[f"{position}_{motion}_{phase}"] = Look(position, motion, phase)
    for start, end in FLY_PAIRS:
        looks[f"{start}_fly_{end}"] = Look(start, "fly", "unison", to=end)
    return looks


LOOKS: Dict[str, Look] = _generate_looks()
DEFAULT_LOOK = "columns_tilt_rows"


@dataclass(frozen=True)
class SectionMotion:
    """How big and how slow a section moves."""

    size: float          # scales every motion; 1.0 is a chorus
    cycle_beats: float   # beats for one full movement; whole bars, so moves end on a bar line
    # A slow mirrored drift laid under every look but a fly-out, so even a
    # held position breathes: the two halves of a truss pan opposite ways by
    # up to `drift_pan_deg`, and every beam leans out and back by up to
    # `drift_tilt_deg`, once every `drift_cycle_beats` (whole bars, locked to
    # the beat clock). Zero is no drift, the looks exactly as designed.
    drift_pan_deg: float = 0.0
    drift_tilt_deg: float = 0.0
    drift_cycle_beats: float = 16.0


SECTION_MOTION: Dict[str, SectionMotion] = {
    "breakdown": SectionMotion(size=0.5, cycle_beats=16.0),
    "verse": SectionMotion(size=0.7, cycle_beats=8.0),
    "buildup": SectionMotion(size=0.85, cycle_beats=8.0),
    "chorus": SectionMotion(size=1.0, cycle_beats=4.0),
    "drop": SectionMotion(size=1.2, cycle_beats=4.0),
}
DEFAULT_MOTION = SECTION_MOTION["verse"]

# At size 1.0: a tilt leans the beam this many degrees further out and back
# in, and a sweep swings it this many degrees either side.
#
# A tilt used to stretch the throw by a share of its length (0.40), which on a
# truss resting 22 degrees off vertical was 16 degrees of travel: a third of
# what the looks were designed with (the April engine's tilts swung 20 to 55
# degrees). It is set in degrees now, so it is the same swing on every rig.
TILT_DEG = 18.0
# However large a look and a section make it, never more than this either way.
# The quickest look in the library (speed 1.5) then tilts at 164 degrees a
# second at 174 BPM, inside the 180 a head has.
TILT_MAX_DEG = 24.0
# A tilt comes no closer to straight down than this and leans no further out
# than this, so the swing is never flattened against straight down or the
# lean limit. The outward figure is what keeps a fanned beam inside the room:
# at 66 the look sheet had the outer beams of a fan landing past the walls on
# five of the seven demo rigs.
LEAN_IN_DEG = 8.0
TILT_OUT_LEAN_DEG = 50.0
SWEEP_DEG = 28.0


def _phase(look: Look, head: Head) -> float:
    if look.phase == "ripple":
        return -math.pi * abs(head.u)
    if look.phase == "rows":
        return math.pi * head.row
    return 0.0


def head_target(
    look_name: str,
    head: Head,
    rig: Rig,
    beats: float,
    motion: SectionMotion = DEFAULT_MOTION,
    speed: float = 1.0,
    amp: float = 1.0,
) -> Point:
    """The floor point a head aims at, at this moment of this look."""
    look = LOOKS.get(look_name) or LOOKS[DEFAULT_LOOK]
    base = POSITIONS[look.position](head, rig)

    cycle = max(0.5, float(motion.cycle_beats) / max(0.1, float(speed)))
    theta = 2.0 * math.pi * (float(beats) / cycle) + _phase(look, head)
    size = float(motion.size) * float(amp)

    if look.motion == "fly":
        # A fly-out is a crossing between two positions, made in pan and tilt
        # (see `_fly`). This is where it starts.
        return _keep_in_front(head, base)

    drifting = float(motion.drift_pan_deg) > 0.0 or float(motion.drift_tilt_deg) > 0.0
    if look.motion == "hold" and not drifting:
        return _keep_in_front(head, base)

    # The throw, as seen from above: from the point under the head to the target.
    gx, gz = base[0] - head.x, base[2] - head.z
    # Mirrored: the two halves of the truss swing opposite ways. A centre
    # head has no side, so it swings with the right-hand half.
    turn = -1.0 if head.u < -1e-6 else 1.0
    stretch, swing = 1.0, 0.0
    if look.motion in ("tilt", "circle"):
        wave = math.cos(theta) if look.motion == "circle" else math.sin(theta)
        stretch = _tilt_stretch(math.hypot(gx, gz), head.y - base[1], size, wave)
    if look.motion in ("sweep", "circle"):
        swing = turn * head.forward * math.radians(SWEEP_DEG * size) * math.sin(theta)
    if drifting:
        # Beat-locked and independent of the look's speed, so a slow look
        # still breathes on the tempo. Pan and tilt a quarter cycle apart
        # make a smooth ellipse, never a stop-start.
        d_theta = 2.0 * math.pi * float(beats) / max(1.0, float(motion.drift_cycle_beats))
        swing += turn * head.forward * math.radians(float(motion.drift_pan_deg)) * math.sin(d_theta)
        if float(motion.drift_tilt_deg) > 0.0:
            stretch *= _tilt_stretch(math.hypot(gx, gz), head.y - base[1],
                                     float(motion.drift_tilt_deg) / TILT_DEG, math.cos(d_theta))
    cos_s, sin_s = math.cos(swing), math.sin(swing)
    rx = (gx * cos_s + gz * sin_s) * stretch
    rz = (-gx * sin_s + gz * cos_s) * stretch
    return _keep_in_front(head, (head.x + rx, base[1], head.z + rz))


def _tilt_stretch(throw: float, drop: float, size: float, wave: float) -> float:
    """How much longer or shorter the throw is, for a tilt at `wave` (-1..1).

    The beam leans out from its resting angle by up to `TILT_DEG` x size and
    back in by the same, in degrees. Where the room for that runs out - close
    to straight down, or close to the lean limit - that side of the swing is
    shorter rather than flattened, and the beam still passes through its
    resting position, so the position the look starts from is the one drawn.
    """
    if throw < 1e-9 or drop < 1e-9:
        return 1.0
    rest = math.degrees(math.atan2(throw, drop))
    swing = min(TILT_MAX_DEG, TILT_DEG * max(0.0, size))
    if wave >= 0.0:
        # Out to the limit, and never less far than the old share-of-the-throw
        # stretch went: a beam already leaning near the limit (all centre, a
        # cross) would otherwise travel less than it used to.
        old_reach = math.degrees(math.atan(
            min(1.8, 1.0 + 0.40 * max(0.0, size)) * math.tan(math.radians(rest)))) - rest
        room = min(max(TILT_OUT_LEAN_DEG - rest, old_reach), (LEAN_MAX_DEG - 2.0) - rest)
    else:
        room = rest - LEAN_IN_DEG
    lean = rest + min(swing, max(0.0, room)) * wave
    return math.tan(math.radians(lean)) / math.tan(math.radians(rest))


def _keep_in_front(head: Head, target: Point) -> Point:
    """Hold a target on the side its truss faces, clear of straight down."""
    least = MIN_THROW * max(head.y, 1.0)
    ahead = (target[2] - head.z) * head.forward
    if ahead < least:
        return (target[0], target[1], head.z + head.forward * least)
    return target


# ---------------------------------------------------------------------------
# Aim
# ---------------------------------------------------------------------------

def aim(head: Head, target: Point) -> Tuple[float, float]:
    """(pan, tilt) in engine degrees that put this head's beam on the target."""
    dx, dy, dz = target[0] - head.x, target[1] - head.y, target[2] - head.z
    lean = math.degrees(math.atan2(math.hypot(dx, dz), -dy))
    lean = max(0.0, min(LEAN_MAX_DEG, lean))
    if head.row_dir > 0:
        # Leans upstage: positive tilt, and the pan that points it there.
        pan_world, tilt = math.degrees(math.atan2(-dx, -dz)), lean
    else:
        pan_world, tilt = math.degrees(math.atan2(dx, dz)), -lean
    pan = (pan_world - head.yaw + 180.0) % 360.0 - 180.0
    half_pan, half_tilt = head.pan_range / 2.0, head.tilt_range / 2.0
    return (max(-half_pan, min(half_pan, pan)), max(-half_tilt, min(half_tilt, tilt)))


def beam_direction(pan: float, tilt: float, yaw: float = 0.0) -> Point:
    """Unit vector a beam points along, for a pan and tilt in engine degrees."""
    p, t = math.radians(pan + yaw), math.radians(tilt)
    return (-math.sin(t) * math.sin(p), -math.cos(t), -math.sin(t) * math.cos(p))


def landing(head: Head, pan: float, tilt: float) -> Optional[Point]:
    """Where a beam meets the floor, or None if it never comes down."""
    dx, dy, dz = beam_direction(pan, tilt, head.yaw)
    if dy >= -1e-6:
        return None
    reach = head.y / -dy
    return (head.x + dx * reach, 0.0, head.z + dz * reach)


def head_pan_tilt(
    look_name: str,
    head: Head,
    rig: Rig,
    beats: float,
    motion: SectionMotion = DEFAULT_MOTION,
    speed: float = 1.0,
    amp: float = 1.0,
) -> Tuple[float, float]:
    """The pan and tilt for one head at one moment of a look."""
    look = LOOKS.get(look_name) or LOOKS[DEFAULT_LOOK]
    if look.motion == "fly":
        return _fly(look, head, rig, beats, motion, speed, amp)
    return aim(head, head_target(look_name, head, rig, beats, motion, speed, amp))


# ---------------------------------------------------------------------------
# Speed: no look faster than a head can turn
# ---------------------------------------------------------------------------

# Samples across one cycle when measuring how fast a look turns a head.
_RATE_SAMPLES = 48
# A look is fitted to the tempo when it is taken and then runs for a phrase.
# This much is kept back for the tempo drifting upward meanwhile, and for the
# measurement being a sample.
SPEED_HEADROOM = 0.95
_PEAK_RATE_CACHE: Dict[tuple, Tuple[float, float]] = {}


def peak_rates(look_name: str, rig: Rig, motion: SectionMotion, amp: float = 1.0) -> Tuple[float, float]:
    """The fastest any head pans and tilts in a look, in degrees per beat at speed 1.

    A look's angle is a function of beats x speed, so its rate at any speed
    and tempo is this times the speed times beats per second, exactly.
    """
    key = (look_name, rig.heads, motion, round(float(amp), 3))
    cached = _PEAK_RATE_CACHE.get(key)
    if cached is not None:
        return cached
    look = LOOKS.get(look_name) or LOOKS[DEFAULT_LOOK]
    peak_pan = peak_tilt = 0.0
    drifting = look.motion != "fly" and (float(motion.drift_pan_deg) > 0.0 or float(motion.drift_tilt_deg) > 0.0)
    if (look.motion != "hold" or drifting) and rig.heads:
        span = float(motion.cycle_beats) * (2.0 if look.motion == "fly" else 1.0)
        if drifting:
            # One whole period of look and drift together, so the closing
            # sample is the first one again and not a false jump.
            a, b = int(round(span)), int(round(max(1.0, float(motion.drift_cycle_beats))))
            span = float(a * b // math.gcd(a, b)) if a > 0 and b > 0 else max(span, float(b))
            if look.motion == "hold":
                span = float(b)
        samples = int(min(4 * _RATE_SAMPLES, max(_RATE_SAMPLES, round(_RATE_SAMPLES * span / max(1.0, float(motion.cycle_beats))))))
        step = span / samples
        for head in rig.heads:
            first = last = head_pan_tilt(look_name, head, rig, 0.0, motion, 1.0, amp)
            for i in range(1, samples + 1):
                now = first if i == samples else head_pan_tilt(look_name, head, rig, i * step, motion, 1.0, amp)
                peak_pan = max(peak_pan, abs(now[0] - last[0]) / step)
                peak_tilt = max(peak_tilt, abs(now[1] - last[1]) / step)
                last = now
    if len(_PEAK_RATE_CACHE) > 512:
        _PEAK_RATE_CACHE.clear()
    _PEAK_RATE_CACHE[key] = (peak_pan, peak_tilt)
    return peak_pan, peak_tilt


def speed_fit(
    look_name: str,
    rig: Rig,
    motion: SectionMotion,
    speed: float,
    amp: float,
    bpm: float,
    max_pan_deg_per_s: float,
    max_tilt_deg_per_s: float,
) -> float:
    """What to multiply a look's speed by so no head is asked to outrun itself.

    1.0 when the look is already within what a head can do at this tempo,
    which is every look in the library at ordinary tempos. Never above 1.0:
    this slows a look that is too fast and never speeds one up.
    """
    pan_per_beat, tilt_per_beat = peak_rates(look_name, rig, motion, amp)
    beats_per_s = max(0.0, float(bpm)) / 60.0 * max(0.0, float(speed))
    fit = 1.0
    for per_beat, limit in ((pan_per_beat, max_pan_deg_per_s), (tilt_per_beat, max_tilt_deg_per_s)):
        asked = per_beat * beats_per_s
        allowed = SPEED_HEADROOM * float(limit)
        if asked > allowed > 0.0:
            fit = min(fit, allowed / asked)
    return fit


def _fly(look: Look, head: Head, rig: Rig, beats: float, motion: SectionMotion,
         speed: float, amp: float) -> Tuple[float, float]:
    """Gathered, then out, then back: the whole rig breathes between two positions.

    The crossing is made in pan and tilt, the way a console crossfades two
    position palettes, and over two of the section's cycles. Moving the target
    point instead drags it past the foot of the head, where a small step on the
    floor is a large turn of the pan: on the demo rigs that asked for 340 to
    620 degrees a second, which no head can do.
    """
    start = aim(head, _keep_in_front(head, POSITIONS[look.position](head, rig)))
    end = aim(head, _keep_in_front(head, POSITIONS[look.to or "fan"](head, rig)))
    cycle = max(1.0, 2.0 * float(motion.cycle_beats) / max(0.1, float(speed)))
    theta = 2.0 * math.pi * (float(beats) / cycle) + _phase(look, head)
    reach = min(1.0, 0.6 + 0.4 * float(motion.size) * float(amp))
    opened = (0.5 - 0.5 * math.cos(theta)) * reach
    return (start[0] + (end[0] - start[0]) * opened, start[1] + (end[1] - start[1]) * opened)
