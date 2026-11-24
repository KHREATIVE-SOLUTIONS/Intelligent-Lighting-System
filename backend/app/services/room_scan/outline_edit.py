"""
Editing a stored room's walls by hand
=====================================

A room scan traces the floor of a room that is not a box as an outline, and
takes any other room for a box. Either can be wrong: a wall the scan leaked
through, a corner cut off, an alcove it never saw, a ceiling read too high.
This redraws the walls of the shell stored on a rig: the whole outline at
once, or one corner moved, added on a wall or taken out, and the room's
height (docs/ROOM_SCAN.md).

Pure, like edit.py: a shell goes in and a new shell comes out, and the one
given is never changed. The caller keeps the one given for its undo
(edit_undo.py).

Where the room is: the rig's axes do not move. A scan puts the origin at the
middle of the floor; an edit to the walls leaves it where it was, because
every fixture, raised area and truss is stored against it. `room.width` and
`room.depth` are then the box round the new outline that is centred on the
origin: twice the furthest a wall reaches either side. That is the box a
scan writes (its outline is centred), and the one every reader that holds a
thing "to the room's box" already takes it for (edit.py, fixture_position.py).

A box room carries no outline, and is still one after an edit that leaves it
one: four corners square to the room and centred on the origin are stored as
a width and a depth. Anything else is stored as `room.outline`.

Nothing here moves a fixture or an item of the room. What the new walls leave
outside is reported instead (`outside_report`), for a person to deal with.
"""

import copy
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .edit import (
    ANY_ROOM_HEIGHT_MAX_M, ANY_ROOM_SIZE_MAX_M, KINDS, ShellEditError, _metres, _mm, _number, area_corners,
    item_name,
)

Corner = Tuple[float, float]

CORNERS_MIN = 3
CORNERS_MAX = 64
# A wall shorter than this is two corners in one place, not a wall. Well under
# the shortest a scan traces (it merges runs under 0.4 m, and fitting corners
# to walls can shorten one further: extract.find_outline), so that a scanned
# room is never refused for a wall nobody touched.
WALL_MIN_M = 0.1
# No one wall longer than a room may be a side. Corner to corner of the
# largest room is further than this.
WALL_MAX_M = 2 * ANY_ROOM_SIZE_MAX_M
# The room, wall to wall, each way: what the views will draw as a room at all
# (previs/outline.ts `usableRoom`, fixture_position.position_outline).
ROOM_SIDE_MIN_M = 1.0
ROOM_SIDE_MAX_M = 2 * ANY_ROOM_SIZE_MAX_M
ROOM_AREA_MIN_M2 = 1.0
ROOM_HEIGHT_MIN_M = 1.5
ROOM_HEIGHT_MAX_M = ANY_ROOM_HEIGHT_MAX_M

WALLS_BY_HAND = "Walls set by hand."
HEIGHT_BY_HAND = "Height set by hand."

# A thing this close to a wall is on it, not outside it: a drag in the 2D
# plan holds a fixture exactly on the wall, and which side of a line a point
# on that line falls is not worth a warning.
ON_WALL_SLACK_M = 0.01
# How finely a truss is walked when asking whether any of it is outside.
SAMPLE_STEP_M = 0.25
RING_SAMPLES = 24

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Reading the stored walls
# ---------------------------------------------------------------------------

def _scanned(shell: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The room of a scanned shell, or the refusal that says there is none."""
    if not isinstance(shell, dict) or shell.get("source") != "scan":
        raise ShellEditError(404, "This rig has no scanned room stored, so there are no walls to edit.")
    room = shell.get("room")
    if not isinstance(room, dict):
        raise ShellEditError(409, "The stored room has no size, so it has no walls to edit. Read the scan again.")
    return room


def _stored_outline(room: Dict[str, Any]) -> Optional[List[Corner]]:
    raw = room.get("outline")
    if not isinstance(raw, list) or len(raw) < CORNERS_MIN:
        return None
    corners: List[Corner] = []
    for corner in raw:
        if not isinstance(corner, dict) or not _number(corner.get("x")) or not _number(corner.get("z")):
            return None
        corners.append((float(corner["x"]), float(corner["z"])))
    return corners


def room_corners(shell: Optional[Dict[str, Any]]) -> Tuple[List[Corner], bool]:
    """(the corners of the room's floor in order, whether the room is a box).

    A box room's are its four, clockwise seen from above from upstage stage
    right: the order the 2D plan draws them in, so corner 2 here is corner 2
    there. Refused for a rig with no scanned room, and for a room with
    neither an outline nor a size.
    """
    room = _scanned(shell)
    outline = _stored_outline(room)
    if outline is not None:
        return outline, False
    width, depth = room.get("width"), room.get("depth")
    if not (_number(width) and _number(depth) and width > 0 and depth > 0):
        raise ShellEditError(409, "The stored room has no size, so it has no walls to edit. Read the scan again.")
    half_w, half_d = width / 2.0, depth / 2.0
    return [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)], True


def corner_points(corners: Sequence[Corner]) -> List[Dict[str, float]]:
    """Corners as they are stored and answered: `{x, z}`, to the millimetre."""
    return [{"x": _mm(x), "z": _mm(z)} for x, z in corners]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def outline_area(corners: Sequence[Corner]) -> float:
    """Signed area on the plan: positive for corners in clockwise order seen from above."""
    twice = 0.0
    for (ax, az), (bx, bz) in zip(corners, list(corners[1:]) + list(corners[:1])):
        twice += ax * bz - bx * az
    return twice / 2.0


def _side(p: Corner, q: Corner, r: Corner) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _between(p: Corner, q: Corner, r: Corner) -> bool:
    """Whether r, known to be on the line through p and q, is on the stretch between them."""
    return (min(p[0], q[0]) - _EPS <= r[0] <= max(p[0], q[0]) + _EPS
            and min(p[1], q[1]) - _EPS <= r[1] <= max(p[1], q[1]) + _EPS)


def _meet(a: Corner, b: Corner, c: Corner, d: Corner) -> bool:
    """Whether two walls cross or touch anywhere, their ends included."""
    s1, s2, s3, s4 = _side(a, b, c), _side(a, b, d), _side(c, d, a), _side(c, d, b)
    if ((s1 > _EPS and s2 < -_EPS) or (s1 < -_EPS and s2 > _EPS)) and \
            ((s3 > _EPS and s4 < -_EPS) or (s3 < -_EPS and s4 > _EPS)):
        return True
    return ((abs(s1) <= _EPS and _between(a, b, c)) or (abs(s2) <= _EPS and _between(a, b, d))
            or (abs(s3) <= _EPS and _between(c, d, a)) or (abs(s4) <= _EPS and _between(c, d, b)))


def crossing_walls(corners: Sequence[Corner]) -> Optional[Tuple[int, int]]:
    """The first two walls that cross, touch or fold back on each other, or None.

    A wall is numbered by the corner it starts at, from 0. Two walls that
    share a corner meet there and nowhere else, unless one doubles back along
    the other. Three corners in a straight line are two walls end to end, and
    are let through: a corner added half way along a wall is exactly that.
    """
    count = len(corners)
    for i in range(count):
        a, b = corners[i], corners[(i + 1) % count]
        for j in range(i + 1, count):
            c, d = corners[j], corners[(j + 1) % count]
            if j == i + 1 or (i == 0 and j == count - 1):
                # Neighbours. The corner they share, and the far end of each.
                shared, p, q = (b, a, d) if j == i + 1 else (a, b, c)
                back = (p[0] - shared[0]) * (q[0] - shared[0]) + (p[1] - shared[1]) * (q[1] - shared[1])
                if abs(_side(shared, p, q)) <= _EPS and back > _EPS:
                    return i, j
                continue
            if _meet(a, b, c, d):
                return i, j
    return None


def inside(corners: Sequence[Corner], x: float, z: float) -> bool:
    """Whether a point on the plan is inside the walls (fixture_position.inside_outline's rule)."""
    within = False
    for (ax, az), (bx, bz) in zip(corners, list(corners[1:]) + list(corners[:1])):
        if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
            within = not within
    return within


def distance_to_walls(corners: Sequence[Corner], x: float, z: float) -> float:
    nearest = math.inf
    for (ax, az), (bx, bz) in zip(corners, list(corners[1:]) + list(corners[:1])):
        dx, dz = bx - ax, bz - az
        length_sq = dx * dx + dz * dz
        along = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / length_sq)) if length_sq > 0 else 0.0
        nearest = min(nearest, math.hypot(x - (ax + along * dx), z - (az + along * dz)))
    return nearest


def within_walls(corners: Sequence[Corner], x: float, z: float, slack: float = ON_WALL_SLACK_M) -> bool:
    """Inside the walls, or on one: within `slack` of it."""
    return inside(corners, x, z) or distance_to_walls(corners, x, z) <= slack


# ---------------------------------------------------------------------------
# What walls a room can have
# ---------------------------------------------------------------------------

def _pair(corner: Any, number: int) -> Corner:
    """One corner as sent: `[x, z]` or `{x, z}`, in metres."""
    if isinstance(corner, dict):
        x, z = corner.get("x"), corner.get("z")
    elif isinstance(corner, (list, tuple)) and len(corner) == 2:
        x, z = corner
    else:
        raise ShellEditError(422, f"Corner {number} must be two numbers, [x, z], in metres.")
    if not _number(x) or not _number(z):
        raise ShellEditError(422, f"Corner {number} must be two numbers of metres; a corner cannot be left out or be infinite.")
    return _mm(x), _mm(z)


def clean_corners(corners: Any) -> List[Corner]:
    """Corners as sent, to the millimetre, refused when they are not a list of 3 to 64 pairs of numbers."""
    if not isinstance(corners, (list, tuple)):
        raise ShellEditError(422, "The walls must be a list of corners, each [x, z] in metres.")
    if not CORNERS_MIN <= len(corners) <= CORNERS_MAX:
        raise ShellEditError(
            422,
            f"A room has between {CORNERS_MIN} and {CORNERS_MAX} corners; {len(corners)} "
            f"{'was' if len(corners) == 1 else 'were'} given.",
        )
    return [_pair(corner, number) for number, corner in enumerate(corners, start=1)]


def check_walls(corners: Sequence[Corner]) -> List[Corner]:
    """Corners that make a room, clockwise seen from above; refused, in a sentence, when they do not.

    Corners given the other way round are turned to run clockwise, the first
    corner staying the first, which is how a scan writes them.
    """
    count = len(corners)
    if not CORNERS_MIN <= count <= CORNERS_MAX:
        raise ShellEditError(422, f"A room has between {CORNERS_MIN} and {CORNERS_MAX} corners; this would have {count}.")
    for number, (x, z) in enumerate(corners, start=1):
        if abs(x) > ANY_ROOM_SIZE_MAX_M or abs(z) > ANY_ROOM_SIZE_MAX_M:
            raise ShellEditError(
                422,
                f"Corner {number} would be {_metres(max(abs(x), abs(z)))} m from the middle of the floor; "
                f"the most is {_metres(ANY_ROOM_SIZE_MAX_M)} m.",
            )
    for i in range(count):
        (ax, az), (bx, bz) = corners[i], corners[(i + 1) % count]
        length = math.hypot(bx - ax, bz - az)
        if length < WALL_MIN_M - _EPS:
            raise ShellEditError(
                422,
                f"Corners {i + 1} and {(i + 1) % count + 1} would be {_metres(length)} m apart. "
                f"A wall is at least {_metres(WALL_MIN_M)} m long: move one of them, or delete it.",
            )
        if length > WALL_MAX_M + _EPS:
            raise ShellEditError(
                422,
                f"The wall from corner {i + 1} to corner {(i + 1) % count + 1} would be {_metres(length)} m long. "
                f"A wall is at most {_metres(WALL_MAX_M)} m.",
            )
    crossing = crossing_walls(corners)
    if crossing is not None:
        first, second = crossing
        raise ShellEditError(
            422,
            f"The walls would cross: the wall from corner {first + 1} to corner {(first + 1) % count + 1} "
            f"would meet the wall from corner {second + 1} to corner {(second + 1) % count + 1}. "
            "A room's walls cannot cross or touch each other.",
        )
    area = outline_area(corners)
    if abs(area) < ROOM_AREA_MIN_M2:
        raise ShellEditError(
            422, f"That would leave a floor of {abs(area):.2f} m2. A room needs at least {_metres(ROOM_AREA_MIN_M2)} m2.",
        )
    xs, zs = [x for x, _ in corners], [z for _, z in corners]
    for span, way in ((max(xs) - min(xs), "across"), (max(zs) - min(zs), "from upstage to downstage")):
        if span < ROOM_SIDE_MIN_M - _EPS or span > ROOM_SIDE_MAX_M + _EPS:
            raise ShellEditError(
                422,
                f"That would make the room {_metres(span)} m {way}. "
                f"It must be between {_metres(ROOM_SIDE_MIN_M)} m and {_metres(ROOM_SIDE_MAX_M)} m.",
            )
    ordered = list(corners)
    if area < 0:
        ordered = [ordered[0]] + ordered[:0:-1]
    return ordered


def _is_box(corners: Sequence[Corner]) -> Optional[Tuple[float, float]]:
    """(width, depth) when the corners are a box square to the room and centred on the origin, else None."""
    if len(corners) != 4:
        return None
    half_w, half_d = abs(corners[0][0]), abs(corners[0][1])
    if half_w <= 0 or half_d <= 0:
        return None
    wanted = {(_mm(sx * half_w), _mm(sz * half_d)) for sx in (-1, 1) for sz in (-1, 1)}
    if {(_mm(x), _mm(z)) for x, z in corners} != wanted:
        return None
    return _mm(2 * half_w), _mm(2 * half_d)


def _mark(room: Dict[str, Any], mark: str) -> None:
    room["suggested"] = False
    basis = str(room.get("basis") or "").strip()
    if mark not in basis:
        room["basis"] = f"{basis} {mark}".strip()


def clean_height(value: Any) -> float:
    if not _number(value):
        raise ShellEditError(422, "The room's height must be a number of metres.")
    height = _mm(value)
    if height < ROOM_HEIGHT_MIN_M - _EPS or height > ROOM_HEIGHT_MAX_M + _EPS:
        raise ShellEditError(
            422,
            f"The room's height must be between {_metres(ROOM_HEIGHT_MIN_M)} m and "
            f"{_metres(ROOM_HEIGHT_MAX_M)} m; {_metres(height)} m is not.",
        )
    return height


# ---------------------------------------------------------------------------
# The edits
# ---------------------------------------------------------------------------

def _same(a: Sequence[Corner], b: Sequence[Corner]) -> bool:
    return len(a) == len(b) and all(_mm(p[0]) == _mm(q[0]) and _mm(p[1]) == _mm(q[1]) for p, q in zip(a, b))


def set_outline(
    shell: Optional[Dict[str, Any]], corners: Any = None, height: Any = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """(the shell with its walls redrawn, its height set, or both; what was done, or None when nothing changed).

    `corners` is every corner of the floor in order, each `[x, z]` in metres
    in the rig's axes; the last is joined back to the first. `height` is floor
    to ceiling. Either may be left out and is then kept.

    The room's box is worked out again from the corners, as a scan works it
    out from the outline it traced. Nothing else in the room is touched: no
    raised area, truss or ring moves, so the hanging heights, which are
    counted from the trusses, stand as they were.
    """
    _scanned(shell)
    if corners is None and height is None:
        raise ShellEditError(422, "Nothing to change: give the corners of the walls, a height, or both.")
    stored, _ = room_corners(shell)
    wanted = check_walls(clean_corners(corners)) if corners is not None else None
    high = clean_height(height) if height is not None else None
    return _write(shell, stored, wanted, high, "Walls redrawn")


def _write(
    shell: Dict[str, Any], stored: Sequence[Corner], wanted: Optional[Sequence[Corner]],
    height: Optional[float], words: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    edited = copy.deepcopy(shell)
    room = edited["room"]
    done: List[str] = []

    # The same box listed from another corner is the same box: it has no corners stored to renumber.
    same_box = wanted is not None and _is_box(wanted) is not None and _is_box(wanted) == _is_box(stored)
    if wanted is not None and not same_box and not _same(stored, wanted):
        box = _is_box(wanted)
        if box is not None:
            room.pop("outline", None)
            room["width"], room["depth"] = box
        else:
            room["outline"] = corner_points(wanted)
            # The box round the outline that is centred on the origin, which has not moved.
            room["width"] = _mm(2 * max(abs(x) for x, _ in wanted))
            room["depth"] = _mm(2 * max(abs(z) for _, z in wanted))
        _mark(room, WALLS_BY_HAND)
        done.append(words)

    if height is not None:
        had = room.get("height")
        if not _number(had) or _mm(had) != height:
            room["height"] = height
            _mark(room, HEIGHT_BY_HAND)
            done.append(f"Room height set to {_metres(height)} m")

    if not done:
        return edited, None
    label = done[0] if len(done) == 1 else f"{done[0]} and {done[1][0].lower()}{done[1][1:]}"
    return edited, label


def _corner_at(corners: Sequence[Corner], index: int) -> None:
    if index < 0 or index >= len(corners):
        raise ShellEditError(
            404,
            f"The room has no corner number {index + 1} (it has {len(corners)}). "
            "It may have been changed elsewhere: load the rig again.",
        )


def _renumbered(index: int, before: Sequence[Corner], after: Sequence[Corner]) -> int:
    """Where a corner is in walls that `check_walls` may have turned to run clockwise."""
    if list(after) == list(before):
        return index
    return (len(before) - index) % len(before)


def move_corner(
    shell: Optional[Dict[str, Any]], index: int, x: Any = None, z: Any = None,
) -> Tuple[Dict[str, Any], Optional[str], int]:
    """(the shell with one corner moved, what was done or None, the corner's place afterwards)."""
    stored, _ = room_corners(shell)
    _corner_at(stored, index)
    if x is None and z is None:
        raise ShellEditError(422, "Nothing to change: say where the corner goes, x and z in metres.")
    for value in (x, z):
        if value is not None and not _number(value):
            raise ShellEditError(422, "A corner must be a number of metres across and a number of metres in depth.")
    wanted = list(stored)
    wanted[index] = (_mm(stored[index][0] if x is None else x), _mm(stored[index][1] if z is None else z))
    checked = check_walls(wanted)
    edited, done = _write(shell, stored, checked, None, f"Walls: corner {index + 1} moved")
    return edited, done, _renumbered(index, wanted, checked)


def insert_corner(
    shell: Optional[Dict[str, Any]], after: int, x: Any = None, z: Any = None,
) -> Tuple[Dict[str, Any], Optional[str], int]:
    """(the shell with a corner added on the wall that leaves corner `after`, what was done, the new corner's place).

    With no place given it goes half way along that wall, where it changes
    nothing about the room until it is moved.
    """
    stored, _ = room_corners(shell)
    _corner_at(stored, after)
    if len(stored) >= CORNERS_MAX:
        raise ShellEditError(409, f"The room already has {len(stored)} corners, which is as many as it can have. Delete one first.")
    if (x is None) != (z is None):
        raise ShellEditError(422, "Say where the new corner goes with both x and z, or with neither for half way along the wall.")
    for value in (x, z):
        if value is not None and not _number(value):
            raise ShellEditError(422, "A corner must be a number of metres across and a number of metres in depth.")
    start, end = stored[after], stored[(after + 1) % len(stored)]
    new = (_mm((start[0] + end[0]) / 2.0), _mm((start[1] + end[1]) / 2.0)) if x is None else (_mm(x), _mm(z))
    wanted = list(stored[:after + 1]) + [new] + list(stored[after + 1:])
    checked = check_walls(wanted)
    edited, done = _write(shell, stored, checked, None, f"Walls: corner added after corner {after + 1}")
    return edited, done, _renumbered(after + 1, wanted, checked)


def delete_corner(shell: Optional[Dict[str, Any]], index: int) -> Tuple[Dict[str, Any], Optional[str]]:
    """(the shell with one corner taken out, what was done). The corners after it move up one place."""
    stored, _ = room_corners(shell)
    _corner_at(stored, index)
    if len(stored) <= CORNERS_MIN:
        raise ShellEditError(409, f"A room needs at least {CORNERS_MIN} corners, and this one has {len(stored)}. Move a corner instead.")
    wanted = list(stored[:index]) + list(stored[index + 1:])
    return _write(shell, stored, check_walls(wanted), None, f"Walls: corner {index + 1} deleted")


# ---------------------------------------------------------------------------
# What the walls leave outside
# ---------------------------------------------------------------------------

OUTSIDE = "outside the walls"
PARTLY_OUTSIDE = "partly outside the walls"
ABOVE = "above the ceiling"


def _item_points(kind: str, item: Dict[str, Any]) -> List[Corner]:
    """Points of an item on the plan to ask the walls about; none when its numbers are missing."""
    if kind == "risers":
        values = [item.get(key) for key in ("center_x", "center_z", "width", "depth")]
        if not all(_number(value) for value in values):
            return []
        # Its middle and its four corners where they are, turned to the heading it stands at.
        return [(float(values[0]), float(values[1]))] + area_corners(item)
    if kind == "truss_lines":
        ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
        if not all(_number(end) for end in ends):
            return []
        steps = max(1, int(math.ceil(math.hypot(ends[2] - ends[0], ends[3] - ends[1]) / SAMPLE_STEP_M)))
        return [
            (ends[0] + (ends[2] - ends[0]) * k / steps, ends[1] + (ends[3] - ends[1]) * k / steps)
            for k in range(steps + 1)
        ]
    values = [item.get(key) for key in ("center_x", "center_z", "radius")]
    if not all(_number(value) for value in values):
        return []
    return [(values[0], values[1])] + [
        (values[0] + values[2] * math.cos(2 * math.pi * k / RING_SAMPLES),
         values[1] + values[2] * math.sin(2 * math.pi * k / RING_SAMPLES))
        for k in range(RING_SAMPLES)
    ]


def _item_top(kind: str, item: Dict[str, Any]) -> Optional[float]:
    """The height an item has to fit under the ceiling: a raised area's deck, a truss's underside."""
    height = item.get("height")
    if not _number(height):
        return None
    if kind == "risers":
        base = item.get("base_height")
        return height + (base if _number(base) and base > 0 else 0.0)
    return float(height)


def _plan_reason(corners: Sequence[Corner], points: Sequence[Corner]) -> Optional[str]:
    if not points:
        return None
    out = sum(1 for x, z in points if not within_walls(corners, x, z))
    if out == 0:
        return None
    return OUTSIDE if out == len(points) else PARTLY_OUTSIDE


def outside_report(
    shell: Optional[Dict[str, Any]], fixtures: Iterable[Any] = (), before: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """What the room's walls and ceiling leave outside, as they now stand. Nothing is moved.

    `items`: each raised area, overhead line and ring any part of which is
    beyond a wall ("partly outside the walls", or "outside the walls" when
    all of it is), or whose deck or underside is above the ceiling, by the
    list it is stored in and its place there. `fixtures`: each fixture whose
    place on the plan is beyond a wall, or that hangs above the ceiling, by
    its id. On a wall, to the centimetre, is inside.

    With `before` (the same report for the room as it was) each entry says
    whether it was `already_outside` then; without, none is said to be.
    """
    empty = {"items": [], "fixtures": [], "count": 0}
    try:
        corners, _ = room_corners(shell)
    except ShellEditError:
        return empty
    room = shell["room"]
    ceiling = float(room["height"]) if _number(room.get("height")) and room["height"] > 0 else None

    def reasons(plan: Optional[str], top: Optional[float]) -> List[str]:
        found = [plan] if plan else []
        if ceiling is not None and top is not None and top > ceiling + ON_WALL_SLACK_M:
            found.append(ABOVE)
        return found

    was_items = {(entry["kind"], entry["index"]) for entry in (before or {}).get("items", [])}
    was_fixtures = {entry["rig_fixture_id"] for entry in (before or {}).get("fixtures", [])}

    items: List[Dict[str, Any]] = []
    for kind in KINDS:
        stored = shell.get(kind)
        for index, item in enumerate(stored if isinstance(stored, list) else []):
            if not isinstance(item, dict):
                continue
            found = reasons(_plan_reason(corners, _item_points(kind, item)), _item_top(kind, item))
            if found:
                items.append({
                    "kind": kind, "index": index, "name": item_name(kind, item),
                    "reason": " and ".join(found),
                    "already_outside": (kind, index) in was_items,
                })

    listed: List[Dict[str, Any]] = []
    for fixture in fixtures:
        x, y, z = (getattr(fixture, key, None) for key in ("position_x", "position_y", "position_z"))
        plan = OUTSIDE if _number(x) and _number(z) and not within_walls(corners, x, z) else None
        found = reasons(plan, float(y) if _number(y) else None)
        if found:
            fixture_id = getattr(fixture, "id", None)
            listed.append({
                "rig_fixture_id": fixture_id,
                "name": getattr(fixture, "name", None) or f"Fixture {fixture_id}",
                "position": {"x": x, "y": y, "z": z},
                "reason": " and ".join(found),
                "already_outside": fixture_id in was_fixtures,
            })

    return {"items": items, "fixtures": listed, "count": len(items) + len(listed)}


def outside_words(report: Dict[str, Any]) -> str:
    """One sentence on what a change to the walls left outside them, for a message."""
    count = report.get("count", 0)
    if not count:
        return "Nothing in the room or the rig is outside the walls."
    new = sum(1 for entry in report["items"] + report["fixtures"] if not entry.get("already_outside"))
    things = f"{count} thing{'s are' if count != 1 else ' is'} now outside the walls or above the ceiling"
    if new == 0:
        return f"{things}, as before the change. Nothing was moved."
    return f"{things} ({new} of them since this change). Nothing was moved: check them."
