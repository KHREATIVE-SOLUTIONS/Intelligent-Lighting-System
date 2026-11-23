"""
Fixtures that follow their truss
================================

A truss line or ring of a stored room that is moved, raised, lowered, turned or
resized by hand (edit.py) takes the fixtures hung on it along: a rigger who
says the truss is half a metre further upstage means the lights on it too
(docs/ROOM_SCAN.md).

Which fixtures hang on it is the rule the views already go by (`hangsOn` in
frontend/src/components/rig/rowMove2d.ts, `hangsFrom` in previs/layout.ts): a
fixture within 0.3 m of the line or of the ring's circle on the plan, and
within 0.6 m of its underside in height. A fixture that hangs within reach of
two of the room's trusses belongs to the nearer, and to the one listed first
when they are as near.

What a carried fixture keeps is its place on the truss:

- a **move** shifts it by what the truss's middle shifted;
- a **height** raises or lowers it by the same amount, so one hung 0.2 m under
  the truss still is;
- a **turn** of a line swings it about the line's middle, by the smaller of
  the two turns that give the new heading (a line has no front), and turns its
  own heading (`rotation_y`) with it, so a light square to the truss stays
  square to it;
- a **length** spreads or closes its place along the line about the middle,
  and keeps how far it is off to the side;
- a **radius** keeps its angle round the ring and how far it is inside or
  outside the truss.

Nothing else about a fixture is touched: not its patch, its mode, its tags or
its group. A guess that is carried is still a guess.

Pure apart from `apply_moves` and `put_back`, which set attributes on the
fixtures they are given. Nothing here touches the database session, the engine
or a device.
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .edit import KINDS, OUTSIDE_MARGIN_M, ShellEditError, _metres, _mm, _number, _room, item_name

# How far off a truss's line on the plan, and off its underside in height, a
# fixture still hangs from it (previs/layout.ts HANGER_REACH, HANGER_HEIGHT_WINDOW).
HANG_REACH_M = 0.3
HANG_HEIGHT_WINDOW_M = 0.6

# The lists of a room that fixtures hang from, in the order the views read them.
HANGING_KINDS: Tuple[str, ...] = ("truss_lines", "truss_rings")

# A line or ring shorter or smaller than this is not drawn and nothing hangs from it (previs/roomShell.ts).
USABLE_OVER_M = 0.2

# A turn under this is rounding, not a turn (edit.py takes a heading to a tenth of a degree).
TURN_OVER_DEG = 0.05
# A length or radius that differs by less is the same one (edit.py stores to the millimetre).
SIZE_OVER_M = 0.0005
# A fixture that would shift by less than this is left exactly where it is.
SHIFT_OVER_M = 0.0005

# Two positions closer than this are the same position (undo.SAME_PLACE_M).
SAME_PLACE_M = 0.005

# How many of the fixtures a refusal names before it says "and N more".
NAMED_MAX = 3

# The keys of an item that say where it is and how big: a change to none of them carries nothing.
GEOMETRY_KEYS: Tuple[str, ...] = ("x1", "z1", "x2", "z2", "center_x", "center_z", "radius", "height")


def _usable(kind: str, item: Any) -> bool:
    """Whether an item is one fixtures can hang from: every number there, and big enough to be drawn."""
    if not isinstance(item, dict) or not _number(item.get("height")):
        return False
    if kind == "truss_lines":
        ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
        return all(_number(end) for end in ends) and math.hypot(ends[2] - ends[0], ends[3] - ends[1]) > USABLE_OVER_M
    values = [item.get(key) for key in ("center_x", "center_z", "radius")]
    return all(_number(value) for value in values) and values[2] > USABLE_OVER_M


def plan_distance(kind: str, item: Dict[str, Any], x: float, z: float) -> float:
    """How far a point on the plan is from a line (between its ends) or from a ring's circle."""
    if kind == "truss_lines":
        ax, az, bx, bz = (float(item[key]) for key in ("x1", "z1", "x2", "z2"))
        run_x, run_z = bx - ax, bz - az
        along = max(0.0, min(1.0, ((x - ax) * run_x + (z - az) * run_z) / (run_x * run_x + run_z * run_z)))
        return math.hypot(x - (ax + along * run_x), z - (az + along * run_z))
    return abs(math.hypot(x - float(item["center_x"]), z - float(item["center_z"])) - float(item["radius"]))


def _place(fixture: Any) -> Optional[Tuple[float, float, float]]:
    """Where a fixture is, or None when it has no position that is three numbers."""
    place = tuple(getattr(fixture, key, None) for key in ("position_x", "position_y", "position_z"))
    return (float(place[0]), float(place[1]), float(place[2])) if all(_number(value) for value in place) else None


def _reach(kind: str, item: Any, place: Tuple[float, float, float]) -> Optional[float]:
    """How far a fixture is from an item on the plan when it hangs from it, else None."""
    # The slack is for arithmetic only: 0.3 m to the side must not fail for being 0.30000000000000004.
    if not _usable(kind, item) or abs(place[1] - float(item["height"])) > HANG_HEIGHT_WINDOW_M + 1e-9:
        return None
    off = plan_distance(kind, item, place[0], place[2])
    return off if off <= HANG_REACH_M + 1e-9 else None


def hangs_on(kind: str, item: Any, fixture: Any) -> bool:
    """Whether a fixture hangs from this line or ring: within reach of it on the plan and of its height."""
    place = _place(fixture)
    return place is not None and _reach(kind, item, place) is not None


def hung_fixtures(shell: Optional[Dict[str, Any]], kind: str, index: int, fixtures: Sequence[Any]) -> List[Any]:
    """The fixtures hung on one line or ring of a room, in the order they were given.

    A fixture within reach of more than one of the room's lines and rings
    hangs on the nearest, and on the one listed first when two are as near:
    where two trusses cross, each keeps its own lights.
    """
    if kind not in HANGING_KINDS or not isinstance(shell, dict):
        return []
    hangers: List[Tuple[str, int, Any]] = [
        (list_name, place, item)
        for list_name in HANGING_KINDS
        for place, item in enumerate(shell.get(list_name) if isinstance(shell.get(list_name), list) else [])
    ]
    hung: List[Any] = []
    for fixture in fixtures:
        place = _place(fixture)
        if place is None:
            continue
        best: Optional[Tuple[float, str, int]] = None
        for list_name, at, item in hangers:
            off = _reach(list_name, item, place)
            if off is not None and (best is None or off < best[0] - 1e-9):
                best = (off, list_name, at)
        if best is not None and (best[1], best[2]) == (kind, index):
            hung.append(fixture)
    return hung


def _fold_turn(degrees: float) -> float:
    """A turn of a line as the smaller of the two that give it: over -90 and up to 90 degrees."""
    turn = math.fmod(degrees, 180.0)
    if turn > 90.0:
        turn -= 180.0
    elif turn <= -90.0:
        turn += 180.0
    return turn


def _wrap_heading(degrees: float) -> float:
    """A fixture's heading over -180 and up to 180 degrees, to a thousandth, with no negative zero."""
    heading = math.fmod(degrees, 360.0)
    if heading > 180.0:
        heading -= 360.0
    elif heading <= -180.0:
        heading += 360.0
    return round(heading, 3) + 0.0


def line_turn(before: Dict[str, Any], after: Dict[str, Any]) -> float:
    """How far a line was turned, in degrees clockwise seen from above; 0 for less than rounding.

    Read from its ends, which are written from stage right to stage left
    whichever way it was turned: the same line can be stored with its ends
    swapped, and that is not half a turn.
    """
    was = math.degrees(math.atan2(before["z2"] - before["z1"], before["x2"] - before["x1"]))
    now = math.degrees(math.atan2(after["z2"] - after["z1"], after["x2"] - after["x1"]))
    turn = _fold_turn(now - was)
    return turn if abs(turn) >= TURN_OVER_DEG else 0.0


def _point(place: Tuple[float, float, float], heading: float) -> Dict[str, float]:
    return {"x": place[0], "y": place[1], "z": place[2], "rotation_y": heading}


def carried_moves(
    shell: Optional[Dict[str, Any]], kind: str, index: int, after: Dict[str, Any], fixtures: Sequence[Any],
) -> List[Dict[str, Any]]:
    """Where the fixtures hung on an item go when it becomes `after`. Nothing is written.

    `shell` is the room before the edit and `after` the item as the edit
    stored it, so a middle the edit held to the room, or brought in to fit, is
    the one the fixtures follow. Each move is {rig_fixture_id, name, from, to},
    `from` and `to` each {x, y, z, rotation_y}; `from` is the fixture's values
    exactly as stored. A fixture that would not shift is left out.
    """
    if kind not in HANGING_KINDS or not isinstance(shell, dict):
        return []
    items = shell.get(kind)
    if not isinstance(items, list) or index < 0 or index >= len(items):
        return []
    before = items[index]
    if not _usable(kind, before) or not _usable(kind, after):
        return []
    if all(before.get(key) == after.get(key) for key in GEOMETRY_KEYS):
        return []

    rise = float(after["height"]) - float(before["height"])
    if kind == "truss_lines":
        was_x, was_z = (before["x1"] + before["x2"]) / 2.0, (before["z1"] + before["z2"]) / 2.0
        now_x, now_z = (after["x1"] + after["x2"]) / 2.0, (after["z1"] + after["z2"]) / 2.0
        run_x, run_z = before["x2"] - before["x1"], before["z2"] - before["z1"]
        was_long = math.hypot(run_x, run_z)
        now_long = math.hypot(after["x2"] - after["x1"], after["z2"] - after["z1"])
        stretch = now_long / was_long if abs(now_long - was_long) >= SIZE_OVER_M else 1.0
        turn = line_turn(before, after)
        # Along the line as it was, and square to it; then the same two as the line now runs.
        along_x, along_z = run_x / was_long, run_z / was_long
        cos, sin = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        to_along_x, to_along_z = along_x * cos - along_z * sin, along_x * sin + along_z * cos
    else:
        was_x, was_z, now_x, now_z = before["center_x"], before["center_z"], after["center_x"], after["center_z"]
        grow = after["radius"] - before["radius"] if abs(after["radius"] - before["radius"]) >= SIZE_OVER_M else 0.0
        turn = 0.0

    moves: List[Dict[str, Any]] = []
    for fixture in hung_fixtures(shell, kind, index, fixtures):
        x, y, z = _place(fixture)
        off_x, off_z = x - was_x, z - was_z
        if kind == "truss_lines":
            along = (off_x * along_x + off_z * along_z) * stretch
            aside = -off_x * along_z + off_z * along_x
            to_x = now_x + along * to_along_x - aside * to_along_z
            to_z = now_z + along * to_along_z + aside * to_along_x
        else:
            out = math.hypot(off_x, off_z)
            # At the very middle of a ring there is no angle to keep.
            share = max(0.0, out + grow) / out if out > 1e-9 else 0.0
            to_x, to_z = now_x + off_x * share, now_z + off_z * share
        to_y = y + rise

        stored_heading = getattr(fixture, "rotation_y", None)
        heading = float(stored_heading) if _number(stored_heading) else 0.0
        # rotation_y turns +Z towards +X; a line's heading turns +X towards +Z: the other way round.
        to_heading = _wrap_heading(heading - turn) if turn else stored_heading

        shifted = max(abs(to_x - x), abs(to_y - y), abs(to_z - z)) >= SHIFT_OVER_M
        if not shifted and to_heading == stored_heading:
            continue
        fixture_id = getattr(fixture, "id", None)
        moves.append({
            "rig_fixture_id": fixture_id,
            "name": getattr(fixture, "name", None) or f"Fixture {fixture_id}",
            "from": {
                "x": getattr(fixture, "position_x"), "y": getattr(fixture, "position_y"),
                "z": getattr(fixture, "position_z"), "rotation_y": stored_heading,
            },
            "to": _point((_mm(to_x), _mm(to_y), _mm(to_z)) if shifted else (x, y, z), to_heading),
        })
    return moves


def refuse_outside(shell: Dict[str, Any], kind: str, item: Dict[str, Any], moves: Sequence[Dict[str, Any]]) -> None:
    """Refuse an edit that would carry a fixture out of the room's box and the margin round it, or through the floor.

    The whole edit is refused, the truss's included: half a row carried and
    half left behind is worse than neither. A room with no size along an axis
    holds nothing along it.
    """
    width, depth, ceiling = _room(shell)

    def out(to: Dict[str, float]) -> bool:
        return (
            (width is not None and abs(to["x"]) > width / 2.0 + OUTSIDE_MARGIN_M + 1e-9)
            or (depth is not None and abs(to["z"]) > depth / 2.0 + OUTSIDE_MARGIN_M + 1e-9)
            or to["y"] < -1e-9
            or (ceiling is not None and to["y"] > ceiling + OUTSIDE_MARGIN_M + 1e-9)
        )

    outside = [move for move in moves if out(move["to"])]
    if not outside:
        return
    named = ", ".join(
        f"{move['name']} to {_metres(move['to']['x'])}, {_metres(move['to']['y'])}, {_metres(move['to']['z'])}"
        for move in outside[:NAMED_MAX]
    )
    more = len(outside) - NAMED_MAX
    count = len(outside)
    raise ShellEditError(
        422,
        f"That would carry {count} fixture{'' if count == 1 else 's'} hung on {item_name(kind, item)} "
        f"out of the room and the {_metres(OUTSIDE_MARGIN_M)} m round it, or through the floor "
        f"({named}{f', and {more} more' if more > 0 else ''}; across, height, depth in metres). "
        f"Nothing was changed. Change the {KINDS[kind]} by less, "
        "or leave its fixtures where they are (carry_fixtures false) and move them afterwards.",
    )


def apply_moves(fixtures: Sequence[Any], moves: Sequence[Dict[str, Any]]) -> None:
    """Put each carried fixture where its move says. Its position and heading only: no tag, no patch."""
    by_id = {getattr(fixture, "id", None): fixture for fixture in fixtures}
    for move in moves:
        fixture, to = by_id[move["rig_fixture_id"]], move["to"]
        fixture.position_x, fixture.position_y, fixture.position_z = to["x"], to["y"], to["z"]
        if to["rotation_y"] != move["from"]["rotation_y"]:
            fixture.rotation_y = to["rotation_y"]


def put_back(fixtures: Sequence[Any], moves: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Take back the moves an undone edit carried: (the fixtures put back, the ones left alone and why).

    A fixture goes back to exactly what it had (`from`), but only while it
    still stands where the edit left it. One a person has moved since, or
    taken out of the rig, is left alone and reported, as the scan's own undo
    does (undo.py): an undo takes back the edit, not what was done after it.
    """
    by_id = {getattr(fixture, "id", None): fixture for fixture in fixtures}
    restored: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for move in moves if isinstance(moves, list) else []:
        if not isinstance(move, dict):
            continue
        fixture_id = move.get("rig_fixture_id")
        fixture = by_id.get(fixture_id)
        name = getattr(fixture, "name", None) or move.get("name") or f"Fixture {fixture_id}"

        def skip(reason: str) -> None:
            skipped.append({"rig_fixture_id": fixture_id, "name": name, "reason": reason})

        if fixture is None:
            skip("it is no longer in the rig")
            continue
        came_from, went_to = move.get("from"), move.get("to")
        if not isinstance(came_from, dict) or not isinstance(went_to, dict) or not all(
            _number(point.get(key)) for point in (came_from, went_to) for key in ("x", "y", "z")
        ):
            skip("the record of its move cannot be read")
            continue
        here = _place(fixture)
        if here is None or any(abs(here[n] - went_to[key]) > SAME_PLACE_M for n, key in enumerate(("x", "y", "z"))):
            skip("it was moved since")
            continue
        fixture.position_x, fixture.position_y, fixture.position_z = came_from["x"], came_from["y"], came_from["z"]
        if came_from.get("rotation_y") != went_to.get("rotation_y"):
            fixture.rotation_y = came_from.get("rotation_y")
        restored.append({"rig_fixture_id": fixture_id, "name": name, "from": went_to, "to": came_from})
    return restored, skipped


def _lights(count: int) -> str:
    return f"{count} fixture{'' if count == 1 else 's'}"


def carried_words(kind: str, item: Dict[str, Any], count: int, asked: bool) -> str:
    """One sentence on what an edit did to the fixtures, for its answer."""
    if kind not in HANGING_KINDS:
        return "No fixture was moved."
    if not asked:
        return f"The fixtures hung on {item_name(kind, item)} were left where they are, as asked."
    if count == 0:
        return "No fixture was moved: none that hangs on it had to move."
    return f"{_lights(count)} hung on {item_name(kind, item)} moved with it."


def put_back_words(restored: int, skipped: int) -> str:
    """One sentence on what an undo did to the fixtures an edit carried."""
    if restored == 0 and skipped == 0:
        return "No fixture was moved."
    parts = [
        f"{_lights(restored)} put back where {'it' if restored == 1 else 'they'} hung before it."
        if restored else "No fixture was put back."
    ]
    if skipped:
        parts.append(f"{_lights(skipped)} left alone, because {'it has' if skipped == 1 else 'they have'} been moved since.")
    return " ".join(parts)
