"""
Fixture positions suggested from a scanned room
===============================================

A rig laid out on a stage template has every fixture at a guess
(`position_source:template`, `position_unconfirmed`: see FLASH_AND_TAP.md). A
scanned room knows things the template did not: how high the truss hangs, where
the stage is, where the walls are. This moves the guesses to agree with it.

Only guesses are moved. A fixture a person has tapped or confirmed, one that
was measured in a file, and one fitted between two tapped ends are never
touched: each of those knows more about the room than a scan does.

A row moves as one piece wherever it can. The fit that flash-and-tap offers
needs a row's guesses to lie on a straight line, and a row moved rigidly is
still one. The exception is a truss that does not run across the room: a row
drawn across it cannot be slid under it, so it is laid out along it.

    Overhead rows (1.9 m and up)
        to the nearest thing the scan found overhead.
        A line across the room: its height, its depth, and along it far enough
        to hang under it, as one piece.
        A line at any other heading, or a ring: onto it, spaced evenly in
        address order. Along a line the row keeps the sense it had (which end
        its first address is at); round a ring the first address is upstage
        and the rest follow clockwise seen from above. Fixtures of the group
        that a scan may not move keep their places in the count. A row on a
        ring is no longer straight, so flash-and-tap's row fit does not apply
        to it.
        With no line or ring, to the height of the lowest hanging band. With
        nothing found overhead, only brought down to hang under the ceiling.
    Floor rows standing where the scan found a stage
        up onto the stage, and in from its edges.
    Every row
        inside the walls.

What comes back is still a guess, and is still tagged as one: flash-and-tap and
dragging are what turn it into a position.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.venue_import.apply import SOURCE_TEMPLATE, is_unconfirmed, position_source

# Added to a moved fixture's tags, so a guess that a scan has shifted can be
# told from one straight off the template.
TAG_SCAN_HINT = "position_hint:room_scan"

OVERHEAD_FROM = 1.9
CEILING_DROP = 0.3
WALL_CLEARANCE = 0.2
STAGE_EDGE_CLEARANCE = 0.3
MOVED_IF_OVER = 0.01
# A line within this of straight across the room takes a row as one piece.
ACROSS_WITHIN_DEG = 2.0
# A fixture this close to a line or ring, and to its height, is on it.
ON_SHAPE_M = 0.05
# Fixtures closer than this along a line or round a ring are worth a note.
CROWDED_UNDER = 0.3

Point = Tuple[float, float, float]


@dataclass
class SuggestedMove:
    rig_fixture_id: int
    name: str
    group: str
    from_position: Point
    to_position: Point
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        def point(p: Point) -> Dict[str, float]:
            return {"x": p[0], "y": p[1], "z": p[2]}

        return {
            "rig_fixture_id": self.rig_fixture_id,
            "name": self.name,
            "group": self.group,
            "from": point(self.from_position),
            "to": point(self.to_position),
            "reason": self.reason,
            # Like every part of the shell: a guess moved to a better guess.
            "suggested": True,
        }


def movable(fixture: Any) -> bool:
    """A template guess nobody has confirmed: the only kind of position a scan may move."""
    tags = getattr(fixture, "tags", None) or []
    return is_unconfirmed(tags) and position_source(tags) == SOURCE_TEMPLATE


def _position(fixture: Any) -> Point:
    return (
        float(getattr(fixture, "position_x", 0.0) or 0.0),
        float(getattr(fixture, "position_y", 0.0) or 0.0),
        float(getattr(fixture, "position_z", 0.0) or 0.0),
    )


def _fit(low: float, high: float, floor: float, ceiling: float) -> Optional[float]:
    """The smallest shift that puts [low, high] inside [floor, ceiling], or None if it is too long."""
    if high - low > ceiling - floor + 1e-9:
        return None
    if low < floor:
        return floor - low
    if high > ceiling:
        return ceiling - high
    return 0.0


def _centre_shift(low: float, high: float, floor: float, ceiling: float) -> float:
    return (floor + ceiling) / 2.0 - (low + high) / 2.0


# ---------------------------------------------------------------------------
# Truss at an angle, and rings
# ---------------------------------------------------------------------------

def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _usable_line(line: Any) -> bool:
    if not isinstance(line, dict):
        return False
    ends = [_number(line.get(key)) for key in ("x1", "z1", "x2", "z2", "height")]
    return None not in ends and math.hypot(ends[2] - ends[0], ends[3] - ends[1]) > 0.2


def _usable_ring(ring: Any) -> bool:
    if not isinstance(ring, dict):
        return False
    values = [_number(ring.get(key)) for key in ("center_x", "center_z", "radius", "height")]
    return None not in values and values[2] > 0.2


def _runs_across(line: Dict[str, Any]) -> bool:
    """Whether a line runs across the room, read from its ends: a shell stored before headings were written has no other say."""
    run_x, run_z = float(line["x2"]) - float(line["x1"]), float(line["z2"]) - float(line["z1"])
    return abs(run_z) <= abs(run_x) * math.tan(math.radians(ACROSS_WITHIN_DEG))


def _to_segment(x: float, z: float, line: Dict[str, Any]) -> float:
    ax, az, bx, bz = (float(line[key]) for key in ("x1", "z1", "x2", "z2"))
    run_x, run_z = bx - ax, bz - az
    along = max(0.0, min(1.0, ((x - ax) * run_x + (z - az) * run_z) / (run_x * run_x + run_z * run_z)))
    return math.hypot(x - (ax + along * run_x), z - (az + along * run_z))


def _to_ring(x: float, z: float, ring: Dict[str, Any]) -> float:
    return abs(math.hypot(x - float(ring["center_x"]), z - float(ring["center_z"])) - float(ring["radius"]))


def _on_shape(shape: Dict[str, Any], fixture: Any) -> bool:
    """Whether a fixture already hangs on this line or ring, at its height."""
    x, y, z = _position(fixture)
    off = _to_ring(x, z, shape) if "radius" in shape else _to_segment(x, z, shape)
    return off <= ON_SHAPE_M and abs(y - float(shape["height"])) <= ON_SHAPE_M


def _run_length(shape: Dict[str, Any]) -> float:
    if "radius" in shape:
        return 2.0 * math.pi * float(shape["radius"])
    return math.hypot(float(shape["x2"]) - float(shape["x1"]), float(shape["z2"]) - float(shape["z1"]))


def _nearest_shape(
    members: Sequence[Any], x: float, z: float,
    across: Sequence[Dict[str, Any]], angled: Sequence[Dict[str, Any]], rings: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The angled line or ring an overhead row belongs on, or None when a line across the room (or nothing) is nearer.

    A row already laid on one stays on it: its middle is then in the middle of
    the line or of the ring, which may be no nearer than something else.
    """
    for shape in list(angled) + list(rings):
        if all(_on_shape(shape, fixture) for fixture in members):
            return shape
    best: Optional[Dict[str, Any]] = None
    nearest = min((abs(float(line["z1"]) - z) for line in across), default=math.inf)
    for line in angled:
        off = _to_segment(x, z, line)
        if off < nearest - 1e-9:
            best, nearest = line, off
    for ring in rings:
        # A row drawn straight through the ring's middle belongs on it as much as one under its arc.
        middle = math.hypot(x - float(ring["center_x"]), z - float(ring["center_z"]))
        off = min(middle, _to_ring(x, z, ring))
        if off < nearest - 1e-9:
            best, nearest = ring, off
    return best


def _address_order(fixture: Any) -> Tuple[int, int, int]:
    return (
        int(getattr(fixture, "universe", 0) or 0),
        int(getattr(fixture, "dmx_address", 0) or 0),
        int(getattr(fixture, "id", 0) or 0),
    )


def _whole_row(fixtures: Sequence[Any], members: Sequence[Any]) -> List[Any]:
    """Every fixture of the row in address order: for a group, the ones a scan may not move as well.

    They keep their places in the count, so the guesses are laid out round the
    places a person has already settled and not across them.
    """
    group = (getattr(members[0], "group_name", None) or "").strip()
    row = list(members) if not group else [
        f for f in fixtures if (getattr(f, "group_name", None) or "").strip() == group
    ]
    return sorted(row, key=_address_order)


def _spots_on(shape: Dict[str, Any], row: Sequence[Any]) -> Dict[int, Tuple[float, float]]:
    """Where each fixture of a row goes on a line or ring: evenly spaced, in address order. Keyed by id()."""
    count = len(row)
    if "radius" in shape:
        # From upstage, clockwise seen from above, as the 3D view counts round a ring.
        cx, cz, radius = float(shape["center_x"]), float(shape["center_z"]), float(shape["radius"])
        return {
            id(fixture): (
                cx + radius * math.sin(2.0 * math.pi * k / count),
                cz - radius * math.cos(2.0 * math.pi * k / count),
            )
            for k, fixture in enumerate(row)
        }
    ax, az, bx, bz = (float(shape[key]) for key in ("x1", "z1", "x2", "z2"))
    run_x, run_z = bx - ax, bz - az
    # The row keeps its own sense: if its addresses ran from stage left to
    # stage right before, they still do.
    along = [(_position(f)[0] - ax) * run_x + (_position(f)[2] - az) * run_z for f in row]
    middle, mean_along = (count - 1) / 2.0, sum(along) / count
    backwards = sum((k - middle) * (a - mean_along) for k, a in enumerate(along)) < -1e-9
    spots = {}
    for k, fixture in enumerate(row):
        share = (k + 0.5) / count
        if backwards:
            share = 1.0 - share
        spots[id(fixture)] = (ax + run_x * share, az + run_z * share)
    return spots


def suggest_positions(fixtures: Sequence[Any], shell: Optional[Dict[str, Any]]) -> Tuple[List[SuggestedMove], List[str]]:
    """(moves, notes). Fixtures are rig fixtures, or anything with the same attributes."""
    notes: List[str] = []
    if not shell:
        return [], notes
    room = shell.get("room") or {}
    # Lines across the room take a row as one piece. A line at any other
    # heading, and a ring, has the row laid out along it.
    found_lines = [l for l in (shell.get("truss_lines") or []) if _usable_line(l)]
    lines = [l for l in found_lines if _runs_across(l)]
    angled = [l for l in found_lines if not _runs_across(l)]
    rings = [r for r in (shell.get("truss_rings") or []) if _usable_ring(r)]
    bands = shell.get("hanging_bands") or []
    stage = next((r for r in (shell.get("risers") or []) if r.get("kind") == "stage"), None)
    half_width = float(room.get("width") or 0.0) / 2.0
    half_depth = float(room.get("depth") or 0.0) / 2.0
    ceiling = float(room.get("height") or 0.0)

    candidates = [f for f in fixtures if movable(f)]
    skipped = sum(1 for f in fixtures if is_unconfirmed(getattr(f, "tags", None)) and not movable(f))
    if skipped:
        notes.append(
            f"{skipped} unconfirmed fixture{'s' if skipped != 1 else ''} fitted between tapped ends "
            "or placed by another source were left where they are."
        )
    if not candidates:
        return [], notes

    rows: Dict[str, List[Any]] = {}
    for fixture in candidates:
        x, y, z = _position(fixture)
        group = (getattr(fixture, "group_name", None) or "").strip()
        # Ungrouped fixtures are a row by standing at one height and depth,
        # which they no longer do once laid along an angle or round a ring.
        # One already hanging on such a line is where a scan would put it.
        if not group and any(_on_shape(shape, fixture) for shape in angled + rings):
            continue
        key = group or f"@ y{round(y, 1)} z{round(z, 1)}"
        rows.setdefault(key, []).append(fixture)

    moves: List[SuggestedMove] = []
    for key, members in rows.items():
        points = [_position(f) for f in members]
        xs, ys, zs = [p[0] for p in points], [p[1] for p in points], [p[2] for p in points]
        mean_y, mean_z = sum(ys) / len(ys), sum(zs) / len(zs)
        dx = dy = dz = 0.0
        reasons: List[str] = []
        label = key if not key.startswith("@ ") else "an ungrouped row"

        if mean_y >= OVERHEAD_FROM:
            mean_x = sum(xs) / len(xs)
            shaped = _nearest_shape(members, mean_x, mean_z, lines, angled, rings)
            if shaped is not None:
                # A truss at an angle or a ring: the row is laid out along it.
                whole_row = _whole_row(fixtures, members)
                spots = _spots_on(shaped, whole_row)
                height = float(shaped["height"])
                name = shaped.get("name") or ("the ring" if "radius" in shaped else "the angled line")
                reason = f"Moved onto {name} at {height:.2f} m, spaced evenly in address order."
                reach = _run_length(shaped)
                if len(whole_row) > 1 and reach / len(whole_row) < CROWDED_UNDER:
                    notes.append(
                        f"{label}: {len(whole_row)} fixtures on {name} ({reach:.1f} m round or along) "
                        f"are {reach / len(whole_row):.2f} m apart; check that the row belongs there."
                    )
                for fixture, (x, y, z) in zip(members, points):
                    to_x, to_z = spots[id(fixture)]
                    to = (round(to_x, 3) + 0.0, round(max(0.0, height + (y - mean_y)), 3) + 0.0, round(to_z, 3) + 0.0)
                    if max(abs(to[0] - x), abs(to[1] - y), abs(to[2] - z)) <= MOVED_IF_OVER:
                        continue
                    moves.append(SuggestedMove(
                        rig_fixture_id=int(getattr(fixture, "id", 0) or 0),
                        name=str(getattr(fixture, "name", "") or ""),
                        group=str(getattr(fixture, "group_name", "") or ""),
                        from_position=(round(x, 3), round(y, 3), round(z, 3)),
                        to_position=to,
                        reason=reason,
                    ))
                continue
            if lines:
                line = min(lines, key=lambda l: abs(float(l["z1"]) - mean_z))
                dz = float(line["z1"]) - mean_z
                dy = float(line["height"]) - mean_y
                x1, x2 = sorted((float(line["x1"]), float(line["x2"])))
                shift = _fit(min(xs), max(xs), x1, x2)
                if shift is None:
                    dx = _centre_shift(min(xs), max(xs), x1, x2)
                    notes.append(
                        f"{label}: the row is {max(xs) - min(xs):.1f} m long and {line['name']} is "
                        f"{x2 - x1:.1f} m; it was centred on the line and overhangs it."
                    )
                else:
                    dx = shift
                reasons.append(f"under {line['name']} at {float(line['height']):.2f} m")
            elif bands:
                height = float(min(b["height"] for b in bands))
                dy = height - mean_y
                reasons.append(f"to the hanging height found at {height:.2f} m")
            elif ceiling > 0 and max(ys) > ceiling - CEILING_DROP:
                dy = (ceiling - CEILING_DROP) - max(ys)
                reasons.append(f"down to hang under the {ceiling:.2f} m ceiling")
        elif stage is not None:
            sx0 = float(stage["center_x"]) - float(stage["width"]) / 2.0
            sx1 = float(stage["center_x"]) + float(stage["width"]) / 2.0
            sz0 = float(stage["center_z"]) - float(stage["depth"]) / 2.0
            sz1 = float(stage["center_z"]) + float(stage["depth"]) / 2.0
            centre_x = (min(xs) + max(xs)) / 2.0
            if mean_z <= sz1 and sx0 <= centre_x <= sx1:
                # Drawn lower than the stage's own top: it was standing on a
                # floor that is not there. Once lifted it is above the top, so
                # a second scan does not lift it again.
                if mean_y < float(stage["height"]):
                    dy = float(stage["height"])
                edge = STAGE_EDGE_CLEARANCE
                shift = _fit(min(zs), max(zs), sz0 + edge, sz1 - edge)
                dz = shift if shift is not None else (sz1 - edge) - max(zs)
                shift = _fit(min(xs), max(xs), sx0 + edge, sx1 - edge)
                if shift is None:
                    notes.append(
                        f"{label}: the row is wider than the {stage.get('name', 'stage').lower()} "
                        "the scan found; it was left overhanging the sides."
                    )
                else:
                    dx = shift
                reasons.append(f"onto the {stage.get('name', 'stage').lower()} ({float(stage['height']):.2f} m up)")

        # Whatever else happened, a row belongs inside the room.
        if half_width > 0 and half_depth > 0:
            for axis, low, high, half in (
                ("x", min(xs) + dx, max(xs) + dx, half_width),
                ("z", min(zs) + dz, max(zs) + dz, half_depth),
            ):
                shift = _fit(low, high, -half + WALL_CLEARANCE, half - WALL_CLEARANCE)
                if shift is None:
                    notes.append(f"{label}: the row is longer than the room the scan found; check the scan's scale.")
                elif abs(shift) > 1e-9:
                    if axis == "x":
                        dx += shift
                    else:
                        dz += shift
                    if "inside the walls" not in reasons:
                        reasons.append("inside the walls")

        # One shift for the whole row, to the centimetre: the row stays the shape it was.
        dx, dy, dz = round(dx, 2), round(dy, 2), round(dz, 2)
        if max(abs(dx), abs(dy), abs(dz)) <= MOVED_IF_OVER:
            continue
        reason = "Moved " + ", ".join(reasons) + "."
        for fixture, (x, y, z) in zip(members, points):
            moves.append(SuggestedMove(
                rig_fixture_id=int(getattr(fixture, "id", 0) or 0),
                name=str(getattr(fixture, "name", "") or ""),
                group=str(getattr(fixture, "group_name", "") or ""),
                from_position=(round(x, 3), round(y, 3), round(z, 3)),
                to_position=(round(x + dx, 4) + 0.0, round(max(0.0, y + dy), 4) + 0.0, round(z + dz, 4) + 0.0),
                reason=reason,
            ))
    return moves, notes
