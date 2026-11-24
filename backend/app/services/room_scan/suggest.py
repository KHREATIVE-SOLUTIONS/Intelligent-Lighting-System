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
        A stage that stands at a heading (`heading_deg`, which a scan measures
        for a stage turned clear of the room's walls, and Edit Room sets by
        hand) takes its rows turned with it: the row is fitted to the stage as
        it would be to one standing square, then swung about the stage's
        middle by the heading, so it is parallel to the turned edges and as
        far from them, and each fixture is turned as far (`turn_deg`, taken
        off its `rotation_y`). A row a scan has already moved (TAG_SCAN_HINT)
        is read as already laid on the turned stage: it is only fitted, never
        swung again. A stage at heading 0, or with none, is the old rule.
    Every row
        inside the walls. In a room that is not a box (an L, a cut corner)
        that is its floor outline and not the box round it: a row with a guess
        outside the outline, in the notch of an L say, is shifted as one piece
        by the least that puts every guess of it inside and clear of the
        walls. Only a row that fits nowhere in one piece has its guesses
        brought inside one by one, and a note says so.

What comes back is still a guess, and is still tagged as one: flash-and-tap and
dragging are what turn it into a position.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.services.venue_import.apply import SOURCE_TEMPLATE, is_unconfirmed, position_source

from .carry import _swung, _wrap_heading
from .edit import area_heading
from .extract import clear_of_outline, inside_outline, outline_area

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
# A row brought inside a floor outline is shifted by a whole number of these.
OUTLINE_STEP = 0.05
# Ungrouped fixtures a scan has swung onto a turned stage are one row while
# each is within this of the next, from the stage's back to its front.
SWUNG_ROW_GAP = 0.05
# What a stage must store, as numbers, for a row to be put onto it.
STAGE_NUMBERS = ("center_x", "center_z", "width", "depth", "height")

Point = Tuple[float, float, float]


@dataclass
class SuggestedMove:
    rig_fixture_id: int
    name: str
    group: str
    from_position: Point
    to_position: Point
    reason: str
    # Degrees the fixture is turned with a stage that stands at a heading,
    # clockwise seen from above. 0 for every move a room standing square makes.
    turn_deg: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        def point(p: Point) -> Dict[str, float]:
            return {"x": p[0], "y": p[1], "z": p[2]}

        out = {
            "rig_fixture_id": self.rig_fixture_id,
            "name": self.name,
            "group": self.group,
            "from": point(self.from_position),
            "to": point(self.to_position),
            "reason": self.reason,
            # Like every part of the shell: a guess moved to a better guess.
            "suggested": True,
        }
        # Only a move that turns says so: every other move reads as it always did.
        if self.turn_deg:
            out["turn_deg"] = self.turn_deg
        return out


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


# ---------------------------------------------------------------------------
# A room that is not a box
# ---------------------------------------------------------------------------

def _floor_outline(room: Dict[str, Any]) -> Optional[np.ndarray]:
    """The room's floor outline as an N by 2 array of (x, z) corners, or None for a box.

    None as well for an outline that is not one (too few corners, a number
    missing, no area), which is then a box to this as it is to everything
    else: the same rule as `position_outline` in fixture_position.py.
    """
    raw = room.get("outline")
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    corners: List[Tuple[float, float]] = []
    for corner in raw:
        if not isinstance(corner, dict):
            return None
        pair = (corner.get("x"), corner.get("z"))
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in pair):
            return None
        corners.append((float(pair[0]), float(pair[1])))
    outline = np.array(corners, dtype=np.float64)
    if not abs(outline_area(outline)) >= 1.0:
        return None
    return outline


def _all_inside(xs: Sequence[float], zs: Sequence[float], outline: np.ndarray) -> bool:
    return bool(inside_outline(np.asarray(xs, dtype=np.float64), np.asarray(zs, dtype=np.float64), outline).all())


def _shift_into_outline(
    xs: Sequence[float], zs: Sequence[float], outline: np.ndarray,
) -> Optional[Tuple[float, float]]:
    """The least shift that puts every one of these points inside the outline, clear of its walls.

    One shift for all of them, so a row stays the shape it was. It is a whole
    number of OUTLINE_STEP each way, and leaves every point WALL_CLEARANCE from
    the nearest wall, which is further inside than the test that sends a row
    here asks for: a row brought in once is not brought in again. Of two
    shifts as short, the one that changes depth less wins, then the one
    further upstage, then stage right. None when the points fit nowhere.
    """
    px, pz = np.asarray(xs, dtype=np.float64), np.asarray(zs, dtype=np.float64)
    x_min, z_min = outline.min(axis=0)
    x_max, z_max = outline.max(axis=0)
    # No shift further than this can help: it would carry a point across the whole room.
    furthest = max(x_max - px.min(), px.max() - x_min, z_max - pz.min(), pz.max() - z_min, OUTLINE_STEP)
    clear = WALL_CLEARANCE - 1e-6
    reach = 1.0
    while True:
        steps = int(math.ceil(min(reach, furthest) / OUTLINE_STEP))
        offsets = np.arange(-steps, steps + 1, dtype=np.float64) * OUTLINE_STEP
        shift_x, shift_z = (grid.ravel() for grid in np.meshgrid(offsets, offsets, indexing="ij"))
        fits = np.ones(len(shift_x), dtype=bool)
        for x, z in zip(px, pz):
            fits &= clear_of_outline(x + shift_x, z + shift_z, outline, clear)
            if not fits.any():
                break
        if fits.any():
            fx, fz = shift_x[fits], shift_z[fits]
            length = np.round(np.hypot(fx, fz), 6)
            best = np.lexsort((fx, fz, np.abs(fz), length))[0]
            # Anything nearer than the square's half side has been tried, so this is the nearest there is.
            if length[best] <= steps * OUTLINE_STEP + 1e-9 or reach >= furthest:
                return round(float(fx[best]), 2) + 0.0, round(float(fz[best]), 2) + 0.0
        if reach >= furthest:
            return None
        reach *= 2.0


# ---------------------------------------------------------------------------
# A stage that stands at a heading
# ---------------------------------------------------------------------------

def turned_rotation(rotation_y: Any, turn_deg: float) -> float:
    """A fixture's `rotation_y` after it is turned `turn_deg` clockwise seen from above.

    `rotation_y` turns +Z towards +X and a heading turns +X towards +Z, the
    other way round, so the turn comes off it: the rule carry.py turns a
    fixture by when the stage under it is turned by hand.
    """
    stored = _number(rotation_y)
    return _wrap_heading((stored if stored is not None else 0.0) - turn_deg)


def _stage_heading(stage: Any) -> float:
    """The heading the suggestion's stage stands at; 0 when it stores none or is not a box that can be turned."""
    if not isinstance(stage, dict):
        return 0.0
    if any(_number(stage.get(key)) is None for key in STAGE_NUMBERS):
        return 0.0
    return area_heading(stage)


def _already_laid(members: Sequence[Any]) -> bool:
    """Whether a scan has moved any fixture of this row before: such a row is never swung a second time."""
    return any(TAG_SCAN_HINT in (getattr(f, "tags", None) or []) for f in members)


def _onto_turned_stage(
    members: Sequence[Any], points: Sequence[Point], stage: Dict[str, Any], heading: float, label: str,
    half_width: float, half_depth: float, ceiling: float, outline: Optional[np.ndarray], notes: List[str],
) -> Optional[List[SuggestedMove]]:
    """The moves that put a floor row onto a stage standing at a heading, or None when the row is not the stage's.

    The row is read in the stage's own two ways, along its width (u) and from
    its back to its front (v), fitted there by the rule for a stage that
    stands square, and put back turned. A row no scan has moved was drawn as
    though the stage stood square: its place from the stage's middle is taken
    as it is, and the whole row is swung by the heading, each fixture turned
    with it. A row a scan has moved is already turned: it is un-swung to be
    read, and nothing is turned again.
    """
    cx, cz = float(stage["center_x"]), float(stage["center_z"])
    half_w, half_d = float(stage["width"]) / 2.0, float(stage["depth"]) / 2.0
    laid = _already_laid(members)
    turn = 0.0 if laid else heading
    local = [
        _swung(x - cx, z - cz, -heading) if laid else (x - cx, z - cz)
        for x, _, z in points
    ]
    us, vs, ys = [p[0] for p in local], [p[1] for p in local], [p[1] for p in points]
    centre_u, mean_v, mean_y = (min(us) + max(us)) / 2.0, sum(vs) / len(vs), sum(ys) / len(ys)
    # The square rule's test, in the stage's own ways: behind its front edge and over its width.
    if not (mean_v <= half_d and -half_w <= centre_u <= half_w):
        return None

    stage_base = _number(stage.get("base_height"))
    stage_top = float(stage["height"]) + (stage_base if stage_base is not None and stage_base > 0 else 0.0)
    stage_name = str(stage.get("name") or "stage").lower()
    dy = stage_top if mean_y < stage_top else 0.0
    edge = STAGE_EDGE_CLEARANCE

    def lay(row: Sequence[Tuple[float, float]]) -> Tuple[List[float], List[float], bool, List[str]]:
        """A row given in the stage's own ways, fitted to the stage, turned and held to the room.

        (x of each, z of each, whether the walls moved any of it, what to say.)
        """
        said: List[str] = []
        row_u, row_v = [p[0] for p in row], [p[1] for p in row]
        shift = _fit(min(row_v), max(row_v), -half_d + edge, half_d - edge)
        dv = shift if shift is not None else (half_d - edge) - max(row_v)
        du = 0.0
        shift = _fit(min(row_u), max(row_u), -half_w + edge, half_w - edge)
        if shift is None:
            said.append(
                f"{label}: the row is wider than the {stage_name} the scan found; it was left overhanging the sides."
            )
        else:
            du = shift
        du, dv = round(du, 2), round(dv, 2)
        # Where each stands in the room once the row is on the turned stage.
        placed = [_swung(u + du, v + dv, heading) for u, v in row]
        to_x, to_z = [cx + p[0] for p in placed], [cz + p[1] for p in placed]

        # Whatever else happened, a row belongs inside the room: as one piece
        # where it fits, and a guess at a time where it does not.
        moved = False
        if half_width > 0 and half_depth > 0:
            for along, half in ((to_x, half_width), (to_z, half_depth)):
                low, high = -half + WALL_CLEARANCE, half - WALL_CLEARANCE
                shift = _fit(min(along), max(along), low, high)
                if shift is None:
                    said.append(f"{label}: the row is longer than the room the scan found; check the scan's scale.")
                    held = [min(max(value, low), high) if low <= high else 0.0 for value in along]
                else:
                    held = [value + shift for value in along]
                if any(abs(a - b) > 1e-9 for a, b in zip(held, along)):
                    moved = True
                along[:] = held
        if outline is not None and not _all_inside(to_x, to_z, outline):
            inward = _shift_into_outline(to_x, to_z, outline)
            if inward is not None:
                to_x, to_z = [x + inward[0] for x in to_x], [z + inward[1] for z in to_z]
                moved = True
            else:
                alone = 0
                for index, (x, z) in enumerate(zip(to_x, to_z)):
                    if _all_inside([x], [z], outline):
                        continue
                    own = _shift_into_outline([x], [z], outline)
                    if own is not None:
                        to_x[index], to_z[index] = x + own[0], z + own[1]
                        alone += 1
                if alone:
                    moved = True
                    said.append(
                        f"{label}: the row does not fit inside the room's walls in one piece; "
                        f"{alone} of its fixtures were brought inside on their own, "
                        "so it is no longer a straight row."
                    )
        return to_x, to_z, moved, said

    def within_walls(row_x: Sequence[float], row_z: Sequence[float]) -> bool:
        """Whether a row as it stands is inside the room, to the millimetre a stored position is rounded to."""
        slack = 0.002
        if half_width > 0 and half_depth > 0:
            if max(abs(x) for x in row_x) > half_width - WALL_CLEARANCE + slack:
                return False
            if max(abs(z) for z in row_z) > half_depth - WALL_CLEARANCE + slack:
                return False
        return outline is None or _all_inside(row_x, row_z, outline)

    # A fit to a turned stage and a hold to the room's walls pull along
    # different ways, so doing both again need not give the same place again.
    # Where the walls moved the row, it is settled here and now: the stage's
    # rule is asked once more from where the walls left it, and its answer is
    # taken if the walls let it stand. And a row a scan has laid that the
    # walls would move again, though it stands inside them, stays where it is:
    # the same scan read twice moves nothing the second time.
    at_x, at_z, walls, said = lay(local)
    if walls:
        here_x, here_z = [p[0] for p in points], [p[2] for p in points]
        if laid and within_walls(here_x, here_z):
            at_x, at_z, walls, said = here_x, here_z, False, []
        else:
            again = lay([_swung(x - cx, z - cz, -heading) for x, z in zip(at_x, at_z)])
            if not again[2]:
                at_x, at_z = again[0], again[1]
    notes.extend(note for note in said if note not in notes)
    reasons = [
        f"onto the {stage_name} ({stage_top:.2f} m up), which stands turned {heading:g} degrees"
        + (" and turned with it" if turn else "")
    ]
    if walls:
        reasons.append("inside the walls")

    # Lifted onto the stage, and never into the drop under the ceiling.
    top = max(ceiling - CEILING_DROP, 0.0) if ceiling > 0 else math.inf
    to_y = [max(0.0, min(y + dy, top)) for y in ys]
    if any(y + dy > top for y in ys):
        reasons.append(f"under the {ceiling:.2f} m ceiling")

    targets = [
        (round(x, 3) + 0.0, round(y, 3) + 0.0, round(z, 3) + 0.0)
        for x, y, z in zip(at_x, to_y, at_z)
    ]
    # The whole row moves or none of it does, and a row that is turned always does.
    if not turn and all(
        max(abs(to[0] - x), abs(to[1] - y), abs(to[2] - z)) <= MOVED_IF_OVER
        for to, (x, y, z) in zip(targets, points)
    ):
        return []
    reason = "Moved " + ", ".join(reasons) + "."
    return [
        SuggestedMove(
            rig_fixture_id=int(getattr(fixture, "id", 0) or 0),
            name=str(getattr(fixture, "name", "") or ""),
            group=str(getattr(fixture, "group_name", "") or ""),
            from_position=(round(x, 3), round(y, 3), round(z, 3)),
            to_position=to,
            reason=reason,
            turn_deg=turn,
        )
        for fixture, (x, y, z), to in zip(members, points, targets)
    ]


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
    # A stage with a number missing (no height, say) cannot be stood on: the
    # row is held to the room as though the scan had found no stage.
    if stage is not None and any(_number(stage.get(key)) is None for key in STAGE_NUMBERS):
        stage = None
    # 0 for a stage that stands square, as every one did before a heading could be stored.
    stage_heading = _stage_heading(stage)
    half_width = float(room.get("width") or 0.0) / 2.0
    half_depth = float(room.get("depth") or 0.0) / 2.0
    ceiling = float(room.get("height") or 0.0)
    # Only a room that is not a box has one. A box room is held to its box, as it always was.
    outline = _floor_outline(room) if isinstance(room, dict) else None

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
    swung_loose: List[Tuple[float, float, int, Any]] = []
    for fixture in candidates:
        x, y, z = _position(fixture)
        group = (getattr(fixture, "group_name", None) or "").strip()
        # Ungrouped fixtures are a row by standing at one height and depth,
        # which they no longer do once laid along an angle or round a ring.
        # One already hanging on such a line is where a scan would put it.
        if not group and any(_on_shape(shape, fixture) for shape in angled + rings):
            continue
        # A floor row a scan has swung onto a stage at a heading stands at one
        # depth of the stage, not of the room: it is still one row, told below
        # by its depth from the stage's back to its front.
        if (
            not group and stage is not None and stage_heading != 0.0 and y < OVERHEAD_FROM
            and TAG_SCAN_HINT in (getattr(fixture, "tags", None) or [])
        ):
            own_depth = _swung(x - float(stage["center_x"]), z - float(stage["center_z"]), -stage_heading)[1]
            swung_loose.append((round(y, 1), own_depth, len(swung_loose), fixture))
            continue
        key = group or f"@ y{round(y, 1)} z{round(z, 1)}"
        rows.setdefault(key, []).append(fixture)

    # Those are rows by standing together, not by a rounded depth: a stored
    # place is rounded to the millimetre, and wherever a rounding cuts, a row
    # at that depth would be read as two. A new row starts at a gap.
    previous: Optional[Tuple[float, float]] = None
    swung_rows: List[List[Tuple[int, Any]]] = []
    for height, own_depth, order, fixture in sorted(swung_loose, key=lambda item: item[:3]):
        if previous is None or height != previous[0] or own_depth - previous[1] > SWUNG_ROW_GAP:
            swung_rows.append([])
        previous = (height, own_depth)
        swung_rows[-1].append((order, fixture))
    for number, row in enumerate(swung_rows):
        # In the order the rig gave them, as every other row is.
        rows[f"@ swung onto the stage, row {number}"] = [fixture for _, fixture in sorted(row, key=lambda item: item[0])]

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
                    to_x, to_z = round(spots[id(fixture)][0], 3), round(spots[id(fixture)][1], 3)
                    why = reason
                    # A truss the scan found hangs inside the walls. One in a
                    # stored shell that reaches beyond the floor outline would
                    # leave a guess outside the room: that one comes inside.
                    if outline is not None and not _all_inside([to_x], [to_z], outline):
                        inward = _shift_into_outline([to_x], [to_z], outline)
                        if inward is not None:
                            to_x, to_z = round(to_x + inward[0], 3), round(to_z + inward[1], 3)
                            why = reason[:-1] + ", then inside the walls."
                    to = (to_x + 0.0, round(max(0.0, height + (y - mean_y)), 3) + 0.0, to_z + 0.0)
                    if max(abs(to[0] - x), abs(to[1] - y), abs(to[2] - z)) <= MOVED_IF_OVER:
                        continue
                    moves.append(SuggestedMove(
                        rig_fixture_id=int(getattr(fixture, "id", 0) or 0),
                        name=str(getattr(fixture, "name", "") or ""),
                        group=str(getattr(fixture, "group_name", "") or ""),
                        from_position=(round(x, 3), round(y, 3), round(z, 3)),
                        to_position=to,
                        reason=why,
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
        elif stage is not None and stage_heading != 0.0:
            # A stage at a heading: the row goes onto it turned, by a rule of its own.
            turned = _onto_turned_stage(
                members, points, stage, stage_heading, label, half_width, half_depth, ceiling, outline, notes,
            )
            if turned is not None:
                moves.extend(turned)
                continue
        elif stage is not None:
            sx0 =float(stage["center_x"]) - float(stage["width"]) / 2.0
            sx1 = float(stage["center_x"]) + float(stage["width"]) / 2.0
            sz0 = float(stage["center_z"]) - float(stage["depth"]) / 2.0
            sz1 = float(stage["center_z"]) + float(stage["depth"]) / 2.0
            centre_x = (min(xs) + max(xs)) / 2.0
            # Its top: a stage that floats (`base_height`, set by hand) starts above the floor.
            stage_base = stage.get("base_height")
            stage_top = float(stage["height"]) + (
                float(stage_base) if isinstance(stage_base, (int, float)) and not isinstance(stage_base, bool)
                and stage_base > 0 else 0.0
            )
            if mean_z <= sz1 and sx0 <= centre_x <= sx1:
                # Drawn lower than the stage's own top: it was standing on a
                # floor that is not there. Once lifted it is above the top, so
                # a second scan does not lift it again.
                if mean_y < stage_top:
                    dy = stage_top
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
                reasons.append(f"onto the {stage.get('name', 'stage').lower()} ({stage_top:.2f} m up)")

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

        # The box is not the room when the room has a floor outline: a row
        # inside the box can still stand in the notch of an L, outside the
        # walls. It comes inside as one piece where it can.
        own: Dict[int, Tuple[float, float]] = {}
        if outline is not None:
            at_x, at_z = [x + dx for x in xs], [z + dz for z in zs]
            if not _all_inside(at_x, at_z, outline):
                inward = _shift_into_outline(at_x, at_z, outline)
                if inward is not None:
                    dx, dz = round(dx + inward[0], 2), round(dz + inward[1], 2)
                else:
                    # It fits nowhere in one piece: each guess outside the walls comes in on its own.
                    for index, (x, z) in enumerate(zip(at_x, at_z)):
                        if _all_inside([x], [z], outline):
                            continue
                        alone = _shift_into_outline([x], [z], outline)
                        if alone is not None:
                            own[index] = alone
                    if own:
                        notes.append(
                            f"{label}: the row does not fit inside the room's walls in one piece; "
                            f"{len(own)} of its fixtures were brought inside on their own, "
                            "so it is no longer a straight row."
                        )
                if (inward is not None or own) and "inside the walls" not in reasons:
                    reasons.append("inside the walls")

        reason = "Moved " + ", ".join(reasons) + "."
        for index, (fixture, (x, y, z)) in enumerate(zip(members, points)):
            # One shift for the whole row, and a guess's own only where the row could not be kept whole.
            own_x, own_z = own.get(index, (0.0, 0.0))
            # Told by the shift itself, never by where it lands: every fixture
            # of a row shifted whole moves or none does.
            if max(abs(dx + own_x), abs(dy), abs(dz + own_z)) <= MOVED_IF_OVER:
                continue
            to = (round(x + dx + own_x, 4) + 0.0, round(max(0.0, y + dy), 4) + 0.0, round(z + dz + own_z, 4) + 0.0)
            moves.append(SuggestedMove(
                rig_fixture_id=int(getattr(fixture, "id", 0) or 0),
                name=str(getattr(fixture, "name", "") or ""),
                group=str(getattr(fixture, "group_name", "") or ""),
                from_position=(round(x, 3), round(y, 3), round(z, 3)),
                to_position=to,
                reason=reason,
            ))
    return moves, notes
