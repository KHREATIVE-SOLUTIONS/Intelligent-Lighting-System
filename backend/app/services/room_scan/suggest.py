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

A row moves as one piece. The fit that flash-and-tap offers needs a row's
guesses to lie on a straight line, and a row moved rigidly is still one. So no
fixture is moved on its own, and nothing is respaced.

    Overhead rows (1.9 m and up)
        to the nearest overhead line the scan found that runs across the room:
        its height, its depth, and along it far enough to hang under it. With
        no such line, to the height of the lowest hanging band. With nothing
        found overhead, only brought down to hang under the ceiling.
    Floor rows standing where the scan found a stage
        up onto the stage, and in from its edges.
    Every row
        inside the walls.

What comes back is still a guess, and is still tagged as one: flash-and-tap and
dragging are what turn it into a position.
"""

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


def suggest_positions(fixtures: Sequence[Any], shell: Optional[Dict[str, Any]]) -> Tuple[List[SuggestedMove], List[str]]:
    """(moves, notes). Fixtures are rig fixtures, or anything with the same attributes."""
    notes: List[str] = []
    if not shell:
        return [], notes
    room = shell.get("room") or {}
    lines = [l for l in (shell.get("truss_lines") or []) if l.get("axis") == "x"]
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
        key = (getattr(fixture, "group_name", None) or "").strip() or f"@ y{round(y, 1)} z{round(z, 1)}"
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
