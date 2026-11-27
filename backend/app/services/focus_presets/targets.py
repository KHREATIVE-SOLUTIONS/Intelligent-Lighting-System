"""
The points a room gives to focus on
===================================

Default targets read from a rig's stored room (`rigs.room_shell`) and the
custom points a person added to the rig (`rigs.focus_targets`). Pure: a shell
and a list in, targets out. docs/FOCUS_PRESETS.md.

Coordinates are the rig's own stage axes, metres: X across, Y up from the
floor, -Z upstage (the booth end), +Z downstage (the crowd end). The room's box
is centred on the origin, as the room scan stores it.

A target gives each head its own point: most give every head the same one, the
audience line spreads the heads along it, and "straight down" is the floor under
each head. A target the room cannot place is kept, with `skipped` saying why in
plain words, so a table can show it was looked for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]

# Head height of a standing crowd, metres: where the audience line is.
AUDIENCE_HEIGHT_M = 1.7
# A DJ standing on a booth riser: chest height above its deck.
DJ_ABOVE_DECK_M = 1.2
# The share of the crowd area's width the audience line spans.
AUDIENCE_SPAN = 0.8

# Custom targets: how many a rig keeps, how long a name, how far from the origin.
MAX_CUSTOM_TARGETS = 50
MAX_NAME_LENGTH = 60
MAX_COORD_M = 500.0

KIND_POINT = "point"   # every head on the same point
KIND_LINE = "line"     # heads spread along a line, in order across X
KIND_BELOW = "below"   # the floor under each head


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    kind: str
    # Where the point came from, in words ("DJ booth raised area 2").
    source: str = ""
    # KIND_POINT: the point. KIND_LINE: the two ends, left (-X) first.
    point: Optional[Vec3] = None
    line: Optional[Tuple[Vec3, Vec3]] = None
    custom: bool = False
    skipped: str = ""

    def points_for(self, positions: Sequence[Vec3]) -> List[Optional[Vec3]]:
        """One point for each head position given, in the order given."""
        if self.skipped:
            return [None for _ in positions]
        if self.kind == KIND_POINT:
            return [self.point for _ in positions]
        if self.kind == KIND_BELOW:
            return [(p[0], 0.0, p[2]) for p in positions]
        # The line: heads in order across X (then depth, then as given) take
        # evenly spaced places along it, so the beams fan out without crossing.
        (ax, ay, az), (bx, by, bz) = self.line  # type: ignore[misc]
        order = sorted(range(len(positions)), key=lambda i: (round(positions[i][0], 6), round(positions[i][2], 6), i))
        out: List[Optional[Vec3]] = [None] * len(positions)
        for place, i in enumerate(order):
            f = (place + 0.5) / len(order)
            out[i] = (_r(ax + (bx - ax) * f), _r(ay + (by - ay) * f), _r(az + (bz - az) * f))
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key, "name": self.name, "kind": self.kind, "source": self.source,
            "point": list(self.point) if self.point else None,
            "line": [list(self.line[0]), list(self.line[1])] if self.line else None,
            "custom": self.custom, "skipped": self.skipped,
        }


def _r(value: float) -> float:
    return round(float(value), 4) + 0.0


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _room(shell: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    room = shell.get("room") if isinstance(shell.get("room"), dict) else {}
    width, depth = _num(room.get("width")), _num(room.get("depth"))
    return (width if width and width > 0 else None), (depth if depth and depth > 0 else None)


def _box(item: Any) -> Optional[Dict[str, float]]:
    """A raised area or booth box: centre, size and the height of its top. None when it lacks one."""
    if not isinstance(item, dict):
        return None
    cx, cz = _num(item.get("center_x")), _num(item.get("center_z"))
    if cx is None or cz is None:
        return None
    base = _num(item.get("base_height")) or 0.0
    height = _num(item.get("height")) or 0.0
    return {
        "x": cx, "z": cz,
        "width": max(0.0, _num(item.get("width")) or 0.0),
        "depth": max(0.0, _num(item.get("depth")) or 0.0),
        "top": max(0.0, base) + max(0.0, height),
    }


def _risers(shell: Dict[str, Any]) -> List[Any]:
    risers = shell.get("risers")
    return risers if isinstance(risers, list) else []


def _dj_booth(shell: Dict[str, Any]) -> Target:
    name = "DJ booth"
    for place, item in enumerate(_risers(shell)):
        if isinstance(item, dict) and item.get("is_dj_booth") is True:
            box = _box(item)
            if box:
                return Target("dj_booth", name, KIND_POINT,
                              source=f"the raised area marked as the DJ booth (raised area {place + 1}), "
                                     f"{DJ_ABOVE_DECK_M} m above its deck",
                              point=(_r(box["x"]), _r(box["top"] + DJ_ABOVE_DECK_M), _r(box["z"])))
    box = _box(shell.get("dj_booth"))
    if box:
        return Target("dj_booth", name, KIND_POINT, source="the rig's DJ booth, at the top of the booth",
                      point=(_r(box["x"]), _r(box["top"]), _r(box["z"])))
    return Target("dj_booth", name, KIND_POINT,
                  skipped="No raised area is marked as the DJ booth and the room has no booth. "
                          "Mark the booth's raised area in the room editor.")


def _dance_floor_disc(shell: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    disc = shell.get("dance_floor")
    if not isinstance(disc, dict):
        return None
    cx, cz, radius = _num(disc.get("center_x")), _num(disc.get("center_z")), _num(disc.get("radius"))
    if cx is None or cz is None or not radius or radius <= 0:
        return None
    return cx, cz, radius


def _stage_front_z(shell: Dict[str, Any]) -> Optional[float]:
    """The downstage edge of the first stage, else of the DJ booth: where the crowd area starts."""
    for item in _risers(shell):
        if isinstance(item, dict) and item.get("kind") == "stage":
            box = _box(item)
            if box:
                return box["z"] + box["depth"] / 2.0
    return None


def _crowd(shell: Dict[str, Any]) -> Tuple[Optional[Tuple[float, float, float]], str]:
    """(centre x, centre z, half width) of the crowd area, and where it came from; None and why not."""
    disc = _dance_floor_disc(shell)
    if disc:
        return disc, "the dance floor"
    width, depth = _room(shell)
    if width is None or depth is None:
        return None, ("The room has no width and depth and no dance floor is marked. "
                      "Read a room scan or give the room its size.")
    front = _stage_front_z(shell)
    downstage = depth / 2.0
    if front is not None and front < downstage:
        return ((0.0, (front + downstage) / 2.0, width / 2.0),
                "the room between the stage front and the downstage wall")
    return (0.0, 0.0, width / 2.0), "the room's floor, centred"


def _dance_floor(shell: Dict[str, Any]) -> Target:
    crowd, source = _crowd(shell)
    if crowd is None:
        return Target("dance_floor", "Dance floor centre", KIND_POINT, skipped=source)
    cx, cz, _ = crowd
    return Target("dance_floor", "Dance floor centre", KIND_POINT, source=f"the centre of {source}, on the floor",
                  point=(_r(cx), 0.0, _r(cz)))


def _audience(shell: Dict[str, Any]) -> Target:
    crowd, source = _crowd(shell)
    if crowd is None:
        return Target("audience", "Audience", KIND_LINE, skipped=source)
    cx, cz, half = crowd
    reach = half * AUDIENCE_SPAN
    return Target("audience", "Audience", KIND_LINE,
                  source=f"a line across {source} at {AUDIENCE_HEIGHT_M} m, the heads spread along it",
                  line=((_r(cx - reach), AUDIENCE_HEIGHT_M, _r(cz)), (_r(cx + reach), AUDIENCE_HEIGHT_M, _r(cz))))


def _stage_front(shell: Dict[str, Any]) -> Target:
    name = "Stage front"
    for place, item in enumerate(_risers(shell)):
        if isinstance(item, dict) and item.get("kind") == "stage":
            box = _box(item)
            if box:
                return Target("stage_front", name, KIND_POINT,
                              source=f"the middle of the downstage edge of the stage (raised area {place + 1}), "
                                     f"{DJ_ABOVE_DECK_M} m above its deck",
                              point=(_r(box["x"]), _r(box["top"] + DJ_ABOVE_DECK_M), _r(box["z"] + box["depth"] / 2.0)))
    for place, item in enumerate(_risers(shell)):
        if isinstance(item, dict) and item.get("is_dj_booth") is True:
            box = _box(item)
            if box:
                return Target("stage_front", "Booth front", KIND_POINT,
                              source=f"the middle of the downstage edge of the DJ booth (raised area {place + 1}), "
                                     "at its deck",
                              point=(_r(box["x"]), _r(box["top"]), _r(box["z"] + box["depth"] / 2.0)))
    box = _box(shell.get("dj_booth"))
    if box:
        return Target("stage_front", "Booth front", KIND_POINT,
                      source="the middle of the front of the rig's DJ booth, at its top",
                      point=(_r(box["x"]), _r(box["top"]), _r(box["z"] + box["depth"] / 2.0)))
    return Target("stage_front", name, KIND_POINT,
                  skipped="The room has no stage and no DJ booth. Add the stage as a raised area of kind stage.")


def default_targets(shell: Optional[Dict[str, Any]]) -> List[Target]:
    """The five default targets, in a fixed order, each placed or skipped with a reason."""
    shell = shell if isinstance(shell, dict) else {}
    return [
        _dj_booth(shell),
        _dance_floor(shell),
        _audience(shell),
        _stage_front(shell),
        Target("straight_down", "Straight down", KIND_BELOW, source="the floor under each head"),
    ]


# ---------------------------------------------------------------------------
# Custom targets, stored on the rig as a list of {id, name, x, y, z}.
# ---------------------------------------------------------------------------

class TargetError(ValueError):
    pass


def clean_name(name: Any) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise TargetError("Give the target a name.")
    if len(text) > MAX_NAME_LENGTH:
        raise TargetError(f"A target's name is at most {MAX_NAME_LENGTH} characters.")
    return text


def clean_point(x: Any, y: Any, z: Any) -> Vec3:
    out = []
    for axis, value in (("x", x), ("y", y), ("z", z)):
        number = _num(value)
        if number is None:
            raise TargetError(f"{axis} must be a number of metres.")
        if abs(number) > MAX_COORD_M:
            raise TargetError(f"{axis} is {number:g} m from the middle of the room; at most {MAX_COORD_M:g} m is taken.")
        out.append(_r(number))
    if out[1] < 0:
        raise TargetError("y is height above the floor and cannot be below it.")
    return out[0], out[1], out[2]


def stored_custom(value: Any) -> List[Dict[str, Any]]:
    """The rig's stored custom targets, any malformed entry left out."""
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        try:
            point = clean_point(item.get("x"), item.get("y"), item.get("z"))
            name = clean_name(item.get("name"))
        except TargetError:
            continue
        out.append({"id": item["id"], "name": name, "x": point[0], "y": point[1], "z": point[2]})
    return out


def add_custom(stored: Any, name: Any, x: Any, y: Any, z: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """A new list with one more target, and that target. The list given is not changed."""
    current = stored_custom(stored)
    if len(current) >= MAX_CUSTOM_TARGETS:
        raise TargetError(f"A rig keeps at most {MAX_CUSTOM_TARGETS} custom targets. Remove one first.")
    point = clean_point(x, y, z)
    item = {"id": max([t["id"] for t in current] + [0]) + 1, "name": clean_name(name),
            "x": point[0], "y": point[1], "z": point[2]}
    return current + [item], item


def remove_custom(stored: Any, target_id: int) -> Optional[List[Dict[str, Any]]]:
    """A new list without that target, or None when there is no such target."""
    current = stored_custom(stored)
    kept = [t for t in current if t["id"] != target_id]
    return None if len(kept) == len(current) else kept


def custom_targets(stored: Any) -> List[Target]:
    return [
        Target(f"custom_{t['id']}", t["name"], KIND_POINT, source="a point added by hand",
               point=(t["x"], t["y"], t["z"]), custom=True)
        for t in stored_custom(stored)
    ]


def all_targets(shell: Optional[Dict[str, Any]], stored: Any) -> List[Target]:
    return default_targets(shell) + custom_targets(stored)
