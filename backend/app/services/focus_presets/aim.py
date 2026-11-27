"""
Aiming one moving head at one point
===================================

Pure maths: a head's place, how it is hung, its pan and tilt travel and its
invert and swap, and a point in the room, in; the pan and tilt that put the
beam on the point, in degrees and in DMX, out. No database, no rig, no device.
docs/FOCUS_PRESETS.md.

The forward model is the 3D view's, so a focus computed here lands where the
view would draw it (frontend/src/components/rig/previs/beamThrow.ts):

- In the head's own frame, pan 0 tilt 0 is straight down its own axis (-Y).
  The beam is (-sin t sin p, -cos t, -sin t cos p): tilt leans it, pan turns
  the lean about the head's own vertical.
- That frame is turned by the rig's rotation_z, then rotation_x, then
  rotation_y (the yaw), all in degrees: `hangBeam` in the view.
- A head standing on the floor is the same head turned over: one more half
  turn about its own X before everything else, so tilt 0 points at the
  ceiling. (The 3D view does not turn a floor-standing mover over; this does.)

Degrees here are physical: how far the yoke and head turn from the centre of
their travel. DMX follows the view's decoding (`readBeamState`):

    value = 0.5 + degrees / range, over 0-1, then x65535 (16 bit) or x255

after the invert and swap:

- `pan_invert` / `tilt_invert` flip the physical axis of that name (the
  rig's `pan_invert` and `tilt_invert` tags, as the view reads them).
- `swap` means the head was set (in its own menu) to swap pan and tilt: the
  pan channel carries the tilt axis's value, as a fraction of the tilt travel,
  and the tilt channel carries the pan axis's, as a fraction of the pan travel.

Of the solutions that reach the point inside both travels, the one nearest pan
centre is chosen (then the smaller tilt, then the lower pan, so the choice is
the same on every machine).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

Vec3 = Tuple[float, float, float]

# Below this length a beam has no direction worth aiming: the point is the head.
MIN_THROW_M = 0.01
# A direction this close to the head's own axis has no pan worth choosing.
AXIS_EPS = 1e-9
# Slack on the end of a travel, in degrees, for round-off.
RANGE_EPS_DEG = 1e-6


@dataclass(frozen=True)
class Head:
    """One moving head, as the aiming maths needs it."""

    position: Vec3
    # The rig's rotation_x, rotation_y (yaw) and rotation_z, degrees.
    rotation: Vec3 = (0.0, 0.0, 0.0)
    # Base on the floor, lens up: turned over from hung.
    standing: bool = False
    # Full travel, degrees: 540 is 270 either side of centre.
    pan_range: float = 540.0
    tilt_range: float = 270.0
    pan_invert: bool = False
    tilt_invert: bool = False
    swap: bool = False
    # 16-bit when the mode has the fine channel for that axis.
    pan_fine: bool = True
    tilt_fine: bool = True


@dataclass(frozen=True)
class Aim:
    """Where to send a head so its beam lands on a point."""

    reachable: bool
    # Plain words for why not, or "" when it is reachable.
    reason: str
    throw_m: float
    # Physical degrees from centre, the chosen solution. For an unreachable
    # point: the solution that came nearest, which is outside a travel.
    pan_deg: Optional[float] = None
    tilt_deg: Optional[float] = None
    # Degrees as a console's Pan and Tilt attributes take them: what goes out
    # on the pan and tilt channels, invert and swap applied, each over its own
    # channel's travel.
    pan_attr_deg: Optional[float] = None
    tilt_attr_deg: Optional[float] = None
    # DMX on the pan and tilt channels (coarse 0-255; fine 0-255 or None).
    pan_dmx: Optional[int] = None
    pan_fine_dmx: Optional[int] = None
    tilt_dmx: Optional[int] = None
    tilt_fine_dmx: Optional[int] = None


# ---------------------------------------------------------------------------
# Turns, exactly as hangBeam applies them.
# ---------------------------------------------------------------------------

def _rz(v: Vec3, deg: float) -> Vec3:
    if deg == 0:
        return v
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    x, y, z = v
    return (x * c - y * s, x * s + y * c, z)


def _rx(v: Vec3, deg: float) -> Vec3:
    if deg == 0:
        return v
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    x, y, z = v
    return (x, y * c - z * s, y * s + z * c)


def _ry(v: Vec3, deg: float) -> Vec3:
    if deg == 0:
        return v
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    x, y, z = v
    return (x * c + z * s, y, -x * s + z * c)


def _turn_over(v: Vec3) -> Vec3:
    """Half a turn about X: a hung head made a standing one. Its own inverse."""
    x, y, z = v
    return (x, -y, -z)


def to_world(head: Head, local: Vec3) -> Vec3:
    rx, yaw, rz = head.rotation
    v = _turn_over(local) if head.standing else local
    return _ry(_rx(_rz(v, rz), rx), yaw)


def to_local(head: Head, world: Vec3) -> Vec3:
    rx, yaw, rz = head.rotation
    v = _rz(_rx(_ry(world, -yaw), -rx), -rz)
    return _turn_over(v) if head.standing else v


def local_beam(pan_deg: float, tilt_deg: float) -> Vec3:
    """The beam in the head's own frame (beamDirection with no lens-up)."""
    p, t = math.radians(pan_deg), math.radians(tilt_deg)
    lean = math.sin(t)
    return (-lean * math.sin(p), -math.cos(t), -lean * math.cos(p))


def beam_direction(head: Head, pan_deg: float, tilt_deg: float) -> Vec3:
    """Where the beam points in the room for physical pan and tilt."""
    return to_world(head, local_beam(pan_deg, tilt_deg))


# ---------------------------------------------------------------------------
# DMX
# ---------------------------------------------------------------------------

def _norm(deg: float, travel: float) -> float:
    return min(1.0, max(0.0, 0.5 + deg / travel)) if travel > 0 else 0.5


def _dmx(norm: float, fine: bool) -> Tuple[int, Optional[int]]:
    if fine:
        value = int(round(norm * 65535))
        return value >> 8, value & 0xFF
    return int(round(norm * 255)), None


def _channels(head: Head, pan_deg: float, tilt_deg: float) -> Tuple[float, float]:
    """The 0-1 values on the pan and tilt channels."""
    pan_axis = _norm(-pan_deg if head.pan_invert else pan_deg, head.pan_range)
    tilt_axis = _norm(-tilt_deg if head.tilt_invert else tilt_deg, head.tilt_range)
    return (tilt_axis, pan_axis) if head.swap else (pan_axis, tilt_axis)


# ---------------------------------------------------------------------------
# Aiming
# ---------------------------------------------------------------------------

def _solutions(local: Vec3) -> List[Tuple[float, float]]:
    """Every (pan, tilt) in degrees that points the head's axis along `local`,
    over pan from -1080 to 1080: more than any head travels."""
    x, y, z = local
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, -y))))
    # Along the head's own axis (either way) pan does nothing: take centre.
    pan = 0.0 if math.hypot(x, z) < AXIS_EPS else math.degrees(math.atan2(-x, -z))
    out: List[Tuple[float, float]] = []
    for turns in range(-3, 4):
        out.append((pan + 360.0 * turns, tilt))
        if tilt > 0:
            out.append((pan + 180.0 + 360.0 * turns, -tilt))
    return out


def _excess(deg: float, travel: float) -> float:
    """Degrees past the end of a travel; 0 inside it."""
    return max(0.0, abs(deg) - travel / 2.0)


def _key(solution: Tuple[float, float]) -> Tuple[float, float, float, float]:
    pan, tilt = solution
    return (round(abs(pan), 6), round(abs(tilt), 6), round(pan, 6), round(tilt, 6))


def _clean(deg: float) -> float:
    return round(deg, 6) + 0.0


def aim(head: Head, target: Vec3) -> Aim:
    """Pan and tilt that put the head's beam on `target`, or why none can."""
    dx, dy, dz = (target[i] - head.position[i] for i in range(3))
    throw = math.sqrt(dx * dx + dy * dy + dz * dz)
    if throw < MIN_THROW_M:
        return Aim(False, "the point is where the fixture is", round(throw, 4))
    if head.pan_range <= 0 or head.tilt_range <= 0:
        return Aim(False, "the fixture has no pan or no tilt travel", round(throw, 4))

    local = to_local(head, (dx / throw, dy / throw, dz / throw))
    solutions = _solutions(local)
    inside = [
        s for s in solutions
        if abs(s[0]) <= head.pan_range / 2.0 + RANGE_EPS_DEG and abs(s[1]) <= head.tilt_range / 2.0 + RANGE_EPS_DEG
    ]
    if inside:
        pan, tilt = min(inside, key=_key)
        pan = max(-head.pan_range / 2.0, min(head.pan_range / 2.0, pan))
        tilt = max(-head.tilt_range / 2.0, min(head.tilt_range / 2.0, tilt))
        pan_norm, tilt_norm = _channels(head, pan, tilt)
        pan_coarse, pan_fine = _dmx(pan_norm, head.pan_fine)
        tilt_coarse, tilt_fine = _dmx(tilt_norm, head.tilt_fine)
        return Aim(
            True, "", round(throw, 4),
            pan_deg=_clean(pan), tilt_deg=_clean(tilt),
            pan_attr_deg=_clean((pan_norm - 0.5) * head.pan_range),
            tilt_attr_deg=_clean((tilt_norm - 0.5) * head.tilt_range),
            pan_dmx=pan_coarse, pan_fine_dmx=pan_fine, tilt_dmx=tilt_coarse, tilt_fine_dmx=tilt_fine,
        )

    # Nothing inside both travels: say what the nearest one would need.
    pan, tilt = min(
        solutions,
        key=lambda s: (
            round(_excess(s[0], head.pan_range) + _excess(s[1], head.tilt_range), 6),
        ) + _key(s),
    )
    needs = []
    if _excess(tilt, head.tilt_range) > 0:
        needs.append(f"tilt {abs(tilt):.1f} degrees from centre, and it reaches {head.tilt_range / 2.0:.1f}")
    if _excess(pan, head.pan_range) > 0:
        needs.append(f"pan {abs(pan):.1f} degrees from centre, and it reaches {head.pan_range / 2.0:.1f}")
    return Aim(
        False, "out of reach: it needs " + "; ".join(needs), round(throw, 4),
        pan_deg=_clean(pan), tilt_deg=_clean(tilt),
    )
