"""
Editing a stored room by hand
=============================

A room scan suggests a stage, risers, a booth, trusses and rings of truss. A
person looking at the room knows better: the "Booth or counter" is the bar, the
truss is half a metre further upstage, the "riser" is a flight case somebody
left on the floor. This renames, moves, resizes, raises, turns and deletes one
of those at a time in the shell stored on a rig, and adds one the scan missed
(docs/ROOM_SCAN.md).

Pure: a shell goes in and a new shell comes out, and the one given is never
changed. That matters to the caller, whose column is plain JSON: a change made
in place to what was loaded is never written. It is also what makes an undo
cheap: the shell as it was is still whole after every edit (edit_undo.py).

What an item is addressed by is the list it is stored in and its place in that
list (`truss_lines`, 1). The lists carry no ids, and the views leave out items
they cannot draw, so a place on the plan is not a place in the list.

Nothing here moves a fixture. Whether the fixtures hung on a truss, or standing
on a raised area, go with it when it is moved, raised, turned or resized is
the caller's to decide, with carry.py, from the item as it was and as this
leaves it. A fixture hung on a deleted truss stays where it is.

A raised area can also be made another kind (a riser a stage, a stage a booth)
and be given a base height, so that a balcony or mezzanine floats: its deck is
then `base_height + height` above the floor. Its place in its list is kept.

What is held to the room: a plain move holds the middle of an item to the
room's box and a margin round it, as it always did. A change of size or
heading, and an added item, hold the whole of it there (`_fit`): a size that
cannot fit is refused, and the middle is brought in until the rest does.

A truss or ring that is raised, lowered, added or deleted is kept counted in
`hanging_bands`, which a scan's suggestion hangs rows by (suggest.py).
"""

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

# The lists of a scanned shell that can be edited, and what one item is called.
KINDS: Dict[str, str] = {
    "risers": "raised area",
    "truss_lines": "overhead line",
    "truss_rings": "overhead ring",
}

NAME_MAX = 60

# How far past the room's own box an item may be put: the margin a fixture's
# position is held to (fixture_position.OUTSIDE_MARGIN_M).
OUTSIDE_MARGIN_M = 2.0

MOVED_BY_HAND = "Moved by hand."
RESIZED_BY_HAND = "Resized by hand."
ADDED_BY_HAND = "Added by hand."
KIND_BY_HAND = "Kind set by hand."

# Slack when deciding which hanging-height band a truss was counted in: the
# shell's heights are rounded to the centimetre.
BAND_SLACK_M = 0.011

# What a raised area can be, and what one is called when it is given no name.
RISER_KINDS: Dict[str, str] = {
    "stage": "Stage",
    "riser": "Riser",
    "booth": "Booth or counter",
}

# The size fields each list takes. Any other is refused for that list.
SIZE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "risers": ("width", "depth", "height", "base_height", "heading_deg"),
    "truss_lines": ("length", "height", "heading_deg"),
    "truss_rings": ("radius", "height"),
}
# The size fields an added item can go without: a line runs across the room, and a raised area stands on the
# floor, square to the room.
OPTIONAL_SIZES: Tuple[str, ...] = ("heading_deg", "base_height")
FIELD_WORDS: Dict[str, str] = {
    "base_height": "base height",
    "width": "width",
    "depth": "depth",
    "length": "length",
    "radius": "radius",
    "height": "height",
    "heading_deg": "heading",
}

# Limits, in metres. The least sizes are above what the views will draw (a
# line over 0.2 m long, a ring over 0.2 m in radius: previs/roomShell.ts).
SIDE_MIN_M = 0.3            # a raised area's width or depth
DECK_MIN_M = 0.05           # a raised area's height above its base
DECK_MAX_M = 3.0
BASE_MAX_M = 10.0           # how far above the floor a raised area's underside can float
LINE_MIN_M = 0.5
RING_MIN_RADIUS_M = 0.3
HANG_MIN_M = 0.5            # the underside of a truss or ring
# Where the room has no size stored to hold a thing to.
ANY_ROOM_SIZE_MAX_M = 100.0
ANY_ROOM_HEIGHT_MAX_M = 30.0
# A heading is taken either way round, and no further.
HEADING_LIMIT_DEG = 360.0
# A line within this of across the room, or of upstage to downstage, is called that (extract.AXIS_SNAP_DEG).
AXIS_SNAP_DEG = 2.0
# How deep an added truss is taken to be, underside to top, and how wide.
ADDED_TRUSS_DEPTH_M = 0.3
# How many of one kind a room can hold.
ITEMS_MAX = 50

BAND_BASIS_LINES = "scan: long thin objects hanging clear of the walls at this height"
BAND_BASIS_RING = "scan: a ring hanging clear of the walls at this height"
BAND_BASIS_HAND = "by hand: a truss or ring set to hang at this height"


class ShellEditError(Exception):
    """An edit that cannot be made. `status` is the HTTP status that says why."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _number(value: Any) -> bool:
    # A bool is an int to Python, and is not a number here.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _mm(value: float) -> float:
    """Rounded to the millimetre, with no negative zero."""
    return round(float(value), 3) + 0.0


def _metres(value: float) -> str:
    """A length for a sentence: to the millimetre, with no trailing noughts."""
    return f"{_mm(value):g}"


def _editable(shell: Optional[Dict[str, Any]], kind: str) -> None:
    """Refuse a list that is not one of the three, and a rig with no scanned room."""
    if kind not in KINDS:
        raise ShellEditError(404, f"'{kind}' is not part of a room that can be edited. Use one of: {', '.join(KINDS)}.")
    if not isinstance(shell, dict) or shell.get("source") != "scan":
        raise ShellEditError(404, "This rig has no scanned room stored, so there is nothing to edit.")


def _find(shell: Optional[Dict[str, Any]], kind: str, index: int) -> Dict[str, Any]:
    """The stored item, or the refusal that says why there is none."""
    _editable(shell, kind)
    items = shell.get(kind)
    count = len(items) if isinstance(items, list) else 0
    if index < 0 or index >= count or not isinstance(items[index], dict):
        raise ShellEditError(
            404,
            f"The stored room has no {KINDS[kind]} number {index + 1} "
            f"(it has {count}). It may have been changed elsewhere: load the rig again.",
        )
    return items[index]


def item_centre(kind: str, item: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """The middle of an item on the plan, or None when its numbers are not all there.

    A raised area's and a ring's own centre; for a line, half way between its ends.
    """
    if kind == "truss_lines":
        ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
        if not all(_number(end) for end in ends):
            return None
        return (ends[0] + ends[2]) / 2.0, (ends[1] + ends[3]) / 2.0
    centre = (item.get("center_x"), item.get("center_z"))
    if not all(_number(value) for value in centre):
        return None
    return float(centre[0]), float(centre[1])


def _room(shell: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(width, depth, height) of the room's box; None for each it does not have."""
    room = shell.get("room") if isinstance(shell.get("room"), dict) else {}

    def size(key: str) -> Optional[float]:
        value = room.get(key)
        return float(value) if _number(value) and value > 0 else None

    return size("width"), size("depth"), size("height")


def _held(shell: Dict[str, Any], x: float, z: float, half_x: float = 0.0, half_z: float = 0.0) -> Tuple[float, float]:
    """A centre held so that the item reaches no further than the room's box and the margin round it.

    `half_x` and `half_z` are how far the item reaches either side of its
    centre; left at nothing, only the centre is held. Left alone along an axis
    the room has no size for.
    """
    width, depth, _ = _room(shell)
    if width is not None:
        limit = max(0.0, width / 2.0 + OUTSIDE_MARGIN_M - half_x)
        x = max(-limit, min(limit, x))
    if depth is not None:
        limit = max(0.0, depth / 2.0 + OUTSIDE_MARGIN_M - half_z)
        z = max(-limit, min(limit, z))
    return x, z


def _fit(shell: Dict[str, Any], kind: str, x: float, z: float, half_x: float, half_z: float) -> Tuple[float, float]:
    """A centre at which the whole of an item is inside the room's box and its margin.

    Refused when it is too big to be: no centre would do.
    """
    width, depth, _ = _room(shell)
    for size, half, way in ((width, half_x, "across"), (depth, half_z, "from upstage to downstage")):
        most = (size + 2 * OUTSIDE_MARGIN_M) if size is not None else ANY_ROOM_SIZE_MAX_M
        if 2 * half > most + 1e-9:
            raise ShellEditError(
                422,
                f"That would make the {KINDS[kind]} {_metres(2 * half)} m {way}, and "
                + (f"the room and the {_metres(OUTSIDE_MARGIN_M)} m round it have room for {_metres(most)} m."
                   if size is not None else f"the most is {_metres(most)} m."),
            )
    return _held(shell, x, z, half_x, half_z)


def clean_name(name: str) -> str:
    """A name as it is stored: trimmed, one line, with something in it."""
    cleaned = " ".join(str(name).split())
    if not cleaned:
        raise ShellEditError(422, "A name needs at least one letter or number.")
    if len(cleaned) > NAME_MAX:
        raise ShellEditError(422, f"A name can be at most {NAME_MAX} characters; this one is {len(cleaned)}.")
    return cleaned


# ---------------------------------------------------------------------------
# Sizes, heights and headings
# ---------------------------------------------------------------------------

def _riser_kind(kind: str, riser_kind: Any) -> None:
    """Refuse a kind that is not a raised area's, or that is asked of a truss."""
    if riser_kind is None:
        return
    if kind != "risers":
        raise ShellEditError(422, f"Only a raised area is a stage, riser or booth; this is a {KINDS[kind]}.")
    if not isinstance(riser_kind, str) or riser_kind not in RISER_KINDS:
        raise ShellEditError(422, f"A raised area is one of: {', '.join(RISER_KINDS)}.")


def _given_sizes(kind: str, sizes: Dict[str, Any]) -> Dict[str, float]:
    """The size fields that were given, refused when one is not this list's or is not a number."""
    given: Dict[str, float] = {}
    for key, value in sizes.items():
        if value is None:
            continue
        if key not in SIZE_FIELDS[kind]:
            takes = ", ".join(FIELD_WORDS[field] for field in SIZE_FIELDS[kind])
            raise ShellEditError(
                422, f"A {KINDS[kind]} has no {FIELD_WORDS[key]} to set. It takes: {takes}."
            )
        if not _number(value):
            raise ShellEditError(
                422,
                f"A {FIELD_WORDS[key]} must be a number of "
                f"{'degrees' if key == 'heading_deg' else 'metres'}.",
            )
        given[key] = float(value)
    return given


def _in_range(kind: str, key: str, value: float, least: float, most: float) -> float:
    """The value to the millimetre, refused when it is outside its limits."""
    value = _mm(value)
    if value < least - 1e-9 or value > most + 1e-9:
        raise ShellEditError(
            422,
            f"The {FIELD_WORDS[key]} of a {KINDS[kind]} must be between {_metres(least)} m "
            f"and {_metres(most)} m; {_metres(value)} m is not.",
        )
    return value


def base_of(item: Dict[str, Any]) -> float:
    """How far above the floor a raised area's underside is: 0 for one that stands on it, or says nothing."""
    base = item.get("base_height")
    return float(base) if _number(base) and base > 0 else 0.0


def deck_top(item: Dict[str, Any]) -> Optional[float]:
    """A raised area's top surface above the floor (its base and its height), or None with no height stored."""
    height = item.get("height")
    return base_of(item) + float(height) if _number(height) else None


def first_stage(shell: Optional[Dict[str, Any]]) -> Optional[int]:
    """The place of the first raised area that is a stage, or None: the one a suggestion puts floor lights on (suggest.py)."""
    risers = shell.get("risers") if isinstance(shell, dict) else None
    for place, item in enumerate(risers if isinstance(risers, list) else []):
        if isinstance(item, dict) and item.get("kind") == "stage":
            return place
    return None


def _top_under_ceiling(shell: Dict[str, Any], item: Dict[str, Any]) -> None:
    """Refuse a raised area whose base and height together put its top above the ceiling."""
    _, _, ceiling = _room(shell)
    top = deck_top(item)
    if ceiling is not None and top is not None and top > ceiling + 1e-9:
        raise ShellEditError(
            422,
            f"That would put the top of the raised area {_metres(top)} m above the floor "
            f"(a base of {_metres(base_of(item))} m and a height of {_metres(item['height'])} m), "
            f"and the ceiling is at {_metres(ceiling)} m. Give it a lower base or a lower height.",
        )


def height_limits(shell: Dict[str, Any], kind: str, item: Optional[Dict[str, Any]] = None) -> Tuple[float, float]:
    """(least, most) height an item of this list may have in this room.

    A raised area's height is its deck above its base, and its top stays under
    the ceiling. A truss's or ring's is its underside, at most the ceiling.
    """
    _, _, ceiling = _room(shell)
    if kind == "risers":
        base = base_of(item or {})
        most = DECK_MAX_M if ceiling is None else min(DECK_MAX_M, ceiling - base)
        return DECK_MIN_M, max(DECK_MIN_M, _mm(most))
    most = ANY_ROOM_HEIGHT_MAX_M if ceiling is None else ceiling
    return HANG_MIN_M, max(HANG_MIN_M, _mm(most))


def clean_heading(degrees: float) -> float:
    """A heading as a line stores it: over -90 and up to 90 degrees, to a tenth.

    Degrees clockwise from across the room, seen from above. A line has no
    front, so 135 is the same line as -45, and -90 the same as 90.
    """
    if abs(degrees) > HEADING_LIMIT_DEG:
        raise ShellEditError(
            422, f"A heading must be between -{HEADING_LIMIT_DEG:g} and {HEADING_LIMIT_DEG:g} degrees."
        )
    heading = math.fmod(degrees, 180.0)
    if heading > 90.0:
        heading -= 180.0
    elif heading <= -90.0:
        heading += 180.0
    return round(heading, 1) + 0.0


def area_heading(item: Any) -> float:
    """The heading a raised area stands at: 0, square to the room, for one that stores none.

    Degrees clockwise from across the room seen from above, as a line's is:
    its `width` then runs along that heading and its `depth` square to it. A
    rectangle looks the same after half a turn, so it is kept over -90 and up
    to 90. Every raised area stored before a heading could be set has none.
    """
    stored = item.get("heading_deg") if isinstance(item, dict) else None
    if not _number(stored) or abs(stored) > HEADING_LIMIT_DEG:
        return 0.0
    return clean_heading(float(stored))


def area_reach(width: float, depth: float, heading: float) -> Tuple[float, float]:
    """How far a raised area at a heading reaches either side of its middle, across the room and in depth."""
    if heading == 0.0:
        return width / 2.0, depth / 2.0
    radians = math.radians(heading)
    cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
    return (cos * width + sin * depth) / 2.0, (sin * width + cos * depth) / 2.0


def area_corners(item: Dict[str, Any]) -> List[Tuple[float, float]]:
    """The four corners of a raised area on the plan, turned to its heading: (x, z) each, in order round it.

    From the corner that is upstage stage right when it stands square, then
    clockwise seen from above. Its numbers must all be there.
    """
    cx, cz = float(item["center_x"]), float(item["center_z"])
    half_w, half_d = float(item["width"]) / 2.0, float(item["depth"]) / 2.0
    heading = area_heading(item)
    if heading == 0.0:
        cos, sin = 1.0, 0.0
    else:
        cos, sin = math.cos(math.radians(heading)), math.sin(math.radians(heading))
    return [
        (cx + u * cos - v * sin, cz + u * sin + v * cos)
        for u, v in ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))
    ]


def line_heading(item: Dict[str, Any]) -> Optional[float]:
    """The heading a line's two ends give it, or None when they are missing or the same point."""
    ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
    if not all(_number(end) for end in ends):
        return None
    run_x, run_z = ends[2] - ends[0], ends[3] - ends[1]
    if run_x == 0 and run_z == 0:
        return None
    return clean_heading(math.degrees(math.atan2(run_z, run_x)))


def _axis(heading: float) -> str:
    if abs(heading) <= AXIS_SNAP_DEG:
        return "x"
    if abs(heading) >= 90.0 - AXIS_SNAP_DEG:
        return "z"
    return "angled"


def _lay_line(
    item: Dict[str, Any], x: float, z: float, length: float, heading: float, radians: Optional[float] = None,
) -> None:
    """Write a line's ends, length, axis and heading from its middle, length and heading.

    The ends are written as a scan writes them: from stage right to stage
    left, or from upstage to downstage for a line that runs that way.
    `radians` is the way it runs where that is known more closely than the
    heading, which is kept to a tenth of a degree: a line made longer stays on
    the line it was on.
    """
    if radians is None:
        radians = math.radians(heading)
    reach_x, reach_z = math.cos(radians) * length / 2.0, math.sin(radians) * length / 2.0
    item["x1"], item["z1"] = _mm(x - reach_x), _mm(z - reach_z)
    item["x2"], item["z2"] = _mm(x + reach_x), _mm(z + reach_z)
    item["length"] = _mm(length)
    item["heading_deg"] = heading
    item["axis"] = _axis(heading)


def _shifted(a: Optional[Tuple[float, float]], b: Optional[Tuple[float, float]]) -> bool:
    """Whether two centres are different places.

    The least move is a millimetre. A line turned or resized about its middle
    has ends rounded to the millimetre, which can put the middle up to half of
    one off: that is not a move.
    """
    if a is None or b is None:
        return a is not b
    return abs(a[0] - b[0]) > 0.00075 or abs(a[1] - b[1]) > 0.00075


def _line_length(item: Dict[str, Any]) -> Optional[float]:
    ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
    if not all(_number(end) for end in ends):
        return None
    return _mm(math.hypot(ends[2] - ends[0], ends[3] - ends[1]))


def _mark(item: Dict[str, Any], mark: str) -> None:
    """A person set this: it is no longer the scan's guess, and its basis says what was done, once."""
    item["suggested"] = False
    basis = str(item.get("basis") or "").strip()
    if mark not in basis:
        item["basis"] = f"{basis} {mark}".strip()


def edit_item(
    shell: Optional[Dict[str, Any]],
    kind: str,
    index: int,
    name: Optional[str] = None,
    center_x: Optional[float] = None,
    center_z: Optional[float] = None,
    width: Optional[float] = None,
    depth: Optional[float] = None,
    length: Optional[float] = None,
    radius: Optional[float] = None,
    height: Optional[float] = None,
    heading_deg: Optional[float] = None,
    base_height: Optional[float] = None,
    riser_kind: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the shell with one item changed, that item). The shell given is not changed.

    Anything left out keeps what it has.

    `center_x` and `center_z` are where the middle of the item goes. A line
    keeps its length and heading: both ends take the same shift. The middle is
    held to the room's box and a 2 m margin round it.

    `width` and `depth` resize a raised area, `length` a line (about its
    middle, along its heading), `radius` a ring. `heading_deg` turns a line
    or a raised area about its middle: a raised area's `width` then runs
    along its heading and its `depth` square to it, and one that stores no
    heading stands square to the room (0). With any of them the whole item is
    held inside the room's box and its margin, and one too big to be is
    refused.

    `height` is a raised area's deck above its base, and the underside of a
    line or ring, whose top moves with it and whose hanging-height band is
    counted again.

    `base_height` is how far above the floor a raised area's underside is (0
    stands on the floor; up to 10 m, with its top under the ceiling), and
    `riser_kind` makes it a `stage`, a `riser` or a `booth`. Its place in the
    list is kept. One still called what its old kind is called ("Riser") is
    called what its new kind is, unless a name is given.

    Everything is stored to the millimetre. An item that actually shifts is no
    longer a suggestion (`suggested` false) and its `basis` says it was moved
    by hand; one whose size, height or heading actually changes says it was
    resized by hand. A rename changes the name and nothing else.
    """
    _find(shell, kind, index)
    sizes = _given_sizes(kind, {
        "width": width, "depth": depth, "length": length, "radius": radius,
        "height": height, "heading_deg": heading_deg, "base_height": base_height,
    })
    _riser_kind(kind, riser_kind)
    if name is None and center_x is None and center_z is None and not sizes and riser_kind is None:
        raise ShellEditError(
            422, "Nothing to change: give a name, a centre, a size, a height, a heading, a base height or a kind.",
        )
    for value in (center_x, center_z):
        if value is not None and not _number(value):
            raise ShellEditError(422, "A centre must be a number of metres.")

    edited = copy.deepcopy(shell)
    item = edited[kind][index]
    before = copy.deepcopy(item)

    if name is not None:
        item["name"] = clean_name(name)

    if riser_kind is not None and item.get("kind") != riser_kind:
        had = item.get("kind")
        item["kind"] = riser_kind
        # One still called what it was ("Riser") would be a stage called Riser.
        if name is None and item.get("name") == RISER_KINDS.get(had if isinstance(had, str) else ""):
            item["name"] = RISER_KINDS[riser_kind]
        _mark(item, KIND_BY_HAND)

    shaped = {key: value for key, value in sizes.items() if key not in ("height", "base_height")}
    resized = False
    rebased = False

    if "base_height" in sizes:
        # Before the height: how high a deck may be depends on where it starts.
        value = _in_range(kind, "base_height", sizes["base_height"], 0.0, BASE_MAX_M)
        if _mm(base_of(item)) != value:
            item["base_height"] = value
            resized = rebased = True

    if center_x is not None or center_z is not None or shaped:
        centre = item_centre(kind, item)
        if centre is None:
            raise ShellEditError(
                409,
                f"This {KINDS[kind]} has no position stored that can be "
                f"{'moved' if not shaped else 'moved, resized or turned'}. Delete it, or read the scan again.",
            )
        want_x = centre[0] if center_x is None else float(center_x)
        want_z = centre[1] if center_z is None else float(center_z)

        if kind == "risers":
            for key in ("width", "depth"):
                if key in shaped:
                    value = _in_range(kind, key, shaped[key], SIDE_MIN_M, ANY_ROOM_SIZE_MAX_M)
                    if not _number(item.get(key)) or _mm(item[key]) != value:
                        item[key] = value
                        resized = True
            if "heading_deg" in shaped:
                value = clean_heading(shaped["heading_deg"])
                # A tenth of a degree is the least turn, as for a line. One that stores no heading stands at 0.
                if abs(value - area_heading(item)) >= 0.05:
                    item["heading_deg"] = value
                    resized = True
            if resized:
                # As far as it reaches at the heading it stands at, which is not half its sides once it is turned.
                half_x, half_z = area_reach(
                    float(item["width"]) if _number(item.get("width")) else 0.0,
                    float(item["depth"]) if _number(item.get("depth")) else 0.0,
                    area_heading(item),
                )
                to_x, to_z = _fit(edited, kind, want_x, want_z, half_x, half_z)
            else:
                to_x, to_z = _held(edited, want_x, want_z)
            item["center_x"], item["center_z"] = _mm(to_x), _mm(to_z)

        elif kind == "truss_rings":
            if "radius" in shaped:
                value = _in_range(kind, "radius", shaped["radius"], RING_MIN_RADIUS_M, ANY_ROOM_SIZE_MAX_M / 2.0)
                if not _number(item.get("radius")) or _mm(item["radius"]) != value:
                    item["radius"] = value
                    resized = True
            if resized:
                to_x, to_z = _fit(edited, kind, want_x, want_z, item["radius"], item["radius"])
            else:
                to_x, to_z = _held(edited, want_x, want_z)
            item["center_x"], item["center_z"] = _mm(to_x), _mm(to_z)

        else:
            run_x, run_z = item["x2"] - item["x1"], item["z2"] - item["z1"]
            had_length = math.hypot(run_x, run_z)
            had_heading = line_heading(item)
            to_length, to_heading = had_length, had_heading
            # The way it runs now, as its ends have it and not as a tenth of a degree does.
            runs: Optional[float] = math.atan2(run_z, run_x) if had_heading is not None else None
            if runs is not None and (runs > math.pi / 2 or runs <= -math.pi / 2):
                runs += math.pi if runs < 0 else -math.pi
            if "length" in shaped:
                value = _in_range(kind, "length", shaped["length"], LINE_MIN_M, ANY_ROOM_SIZE_MAX_M)
                if abs(value - had_length) >= 0.0005:
                    to_length, resized = value, True
            if "heading_deg" in shaped:
                value = clean_heading(shaped["heading_deg"])
                if had_heading is None or abs(value - had_heading) >= 0.05:
                    to_heading, runs, resized = value, None, True
            if resized:
                if to_heading is None:
                    # Both ends at one point: it has no heading of its own to keep.
                    stored = item.get("heading_deg")
                    to_heading = clean_heading(stored) if _number(stored) and abs(stored) <= HEADING_LIMIT_DEG else 0.0
                if to_length < LINE_MIN_M:
                    raise ShellEditError(
                        422,
                        f"This {KINDS[kind]} is {_metres(to_length)} m long, too short to turn. "
                        f"Give it a length of at least {_metres(LINE_MIN_M)} m as well.",
                    )
                radians = math.radians(to_heading) if runs is None else runs
                half_x = abs(math.cos(radians)) * to_length / 2.0
                half_z = abs(math.sin(radians)) * to_length / 2.0
                to_x, to_z = _fit(edited, kind, want_x, want_z, half_x, half_z)
                _lay_line(item, to_x, to_z, to_length, to_heading, radians)
            else:
                # Both ends take the same shift: its length and heading are untouched to the last digit.
                to_x, to_z = _held(edited, want_x, want_z)
                dx, dz = _mm(to_x - centre[0]), _mm(to_z - centre[1])
                if dx != 0 or dz != 0:
                    item["x1"], item["x2"] = _mm(item["x1"] + dx), _mm(item["x2"] + dx)
                    item["z1"], item["z2"] = _mm(item["z1"] + dz), _mm(item["z2"] + dz)

        if _shifted(centre, item_centre(kind, item)):
            _mark(item, MOVED_BY_HAND)
        else:
            # Not moved: what it had is kept as it was stored, not as it rounds.
            for key in ("center_x", "center_z"):
                if key in before:
                    item[key] = before[key]

    if "height" in sizes:
        least, most = height_limits(edited, kind, item)
        value = _in_range(kind, "height", sizes["height"], least, most)
        had = item.get("height")
        if not _number(had) or _mm(had) != value:
            item["height"] = value
            resized = True
            if kind != "risers":
                top = item.get("top")
                if _number(top) and _number(had):
                    # The truss is as deep as it was: its top goes up or down with its underside.
                    item["top"] = _mm(value + (top - had))
                _uncount(edited, kind, before)
                _count(edited, kind, item)

    if rebased:
        _top_under_ceiling(edited, item)

    if resized:
        _mark(item, RESIZED_BY_HAND)

    return edited, item


# ---------------------------------------------------------------------------
# Hanging-height bands
# ---------------------------------------------------------------------------

def _band_count(band: Any, name: str) -> int:
    value = band.get(name) if isinstance(band, dict) else None
    return int(value) if _number(value) and value > 0 else 0


def _bands_at(bands: List[Any], height: float) -> List[Dict[str, Any]]:
    """The bands whose range of heights takes in this one."""
    return [
        band for band in bands
        if isinstance(band, dict) and _number(band.get("height"))
        and band["height"] - BAND_SLACK_M <= height
        <= (band["top"] if _number(band.get("top")) else band["height"]) + BAND_SLACK_M
    ]


def _uncount(shell: Dict[str, Any], kind: str, removed: Dict[str, Any]) -> None:
    """Take a deleted (or re-hung) truss out of the hanging-height band that counted it.

    A band with nothing left in it is dropped: a suggestion would otherwise go
    on hanging rows at a height where nothing hangs any more (suggest.py).
    """
    bands = shell.get("hanging_bands")
    if not isinstance(bands, list):
        return
    key = "lines" if kind == "truss_lines" else "rings"
    other = "rings" if key == "lines" else "lines"

    remaining = [item for item in (shell.get("truss_lines") or []) + (shell.get("truss_rings") or [])
                 if isinstance(item, dict)]
    if not remaining:
        # Nothing hangs in the room any more, whatever the bands add up to.
        shell["hanging_bands"] = []
        return

    height = removed.get("height")
    if not _number(height):
        return
    inside = [band for band in _bands_at(bands, height) if _band_count(band, key) > 0]
    if not inside:
        return
    band = min(inside, key=lambda b: abs(b["height"] - height))
    band[key] = _band_count(band, key) - 1
    if band[key] == 0 and _band_count(band, other) == 0:
        shell["hanging_bands"] = [b for b in bands if b is not band]
    elif band[key] == 0 and key == "lines" and band.get("basis") == BAND_BASIS_LINES:
        band["basis"] = BAND_BASIS_RING


def _count(shell: Dict[str, Any], kind: str, added: Dict[str, Any]) -> None:
    """Count an added (or re-hung) truss in the hanging-height band its underside is in.

    Where no band takes in its height it starts one of its own, marked as not
    the scan's: a suggestion hangs rows by the lowest band when no truss runs
    across the room (suggest.py), so a height with a truss at it has to be one.
    """
    height = added.get("height")
    if not _number(height):
        return
    stored = shell.get("hanging_bands")
    bands: List[Any] = list(stored) if isinstance(stored, list) else []
    key = "lines" if kind == "truss_lines" else "rings"
    inside = _bands_at(bands, height)
    if inside:
        band = min(inside, key=lambda b: abs(b["height"] - height))
        band[key] = _band_count(band, key) + 1
        if key == "lines" and band.get("basis") == BAND_BASIS_RING:
            band["basis"] = BAND_BASIS_LINES
    else:
        top = added.get("top")
        bands.append({
            "height": _mm(height),
            "top": _mm(top) if _number(top) and top >= height else _mm(height),
            "lines": 1 if key == "lines" else 0,
            "rings": 1 if key == "rings" else 0,
            "suggested": False,
            "basis": BAND_BASIS_HAND,
        })
        bands.sort(key=lambda b: b["height"] if isinstance(b, dict) and _number(b.get("height")) else math.inf)
    shell["hanging_bands"] = bands


# ---------------------------------------------------------------------------
# Deleting and adding
# ---------------------------------------------------------------------------

def delete_item(shell: Optional[Dict[str, Any]], kind: str, index: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the shell without one item, the item taken out). The shell given is not changed.

    Items after it move up one place in their list. A truss or ring is also
    taken out of the hanging-height band that counted it, and a band left with
    nothing in it goes too.
    """
    _find(shell, kind, index)
    edited = copy.deepcopy(shell)
    removed = edited[kind].pop(index)
    if kind in ("truss_lines", "truss_rings"):
        _uncount(edited, kind, removed)
    return edited, removed


def add_item(
    shell: Optional[Dict[str, Any]],
    kind: str,
    name: Optional[str] = None,
    center_x: Optional[float] = None,
    center_z: Optional[float] = None,
    width: Optional[float] = None,
    depth: Optional[float] = None,
    length: Optional[float] = None,
    radius: Optional[float] = None,
    height: Optional[float] = None,
    heading_deg: Optional[float] = None,
    riser_kind: Optional[str] = None,
    base_height: Optional[float] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """(the shell with one more item, that item, its place in its list). The shell given is not changed.

    The scan missed it, and a person puts it in: a stage, riser or booth
    (`risers`, with `riser_kind`, a width, a depth and a height, and a
    heading when it does not stand square to the room), a truss
    (`truss_lines`, with a length, a height and a heading, across the room
    when none is given) or a ring (`truss_rings`, with a radius and a height).
    The centre is needed for all three. It goes at the end of its list, so no
    other item changes place.

    It is marked as a person's and not the scan's: `added_by_hand` true,
    `suggested` false, and a `basis` that says so. The whole of it is held
    inside the room's box and its margin; a size outside its limits, or too
    big for the room, is refused. An added truss or ring is counted in the
    hanging-height band it is in, or starts one.
    """
    _editable(shell, kind)
    sizes = _given_sizes(kind, {
        "width": width, "depth": depth, "length": length, "radius": radius,
        "height": height, "heading_deg": heading_deg, "base_height": base_height,
    })
    # An empty kind is no kind given, as it always was: a riser.
    _riser_kind(kind, riser_kind or None)
    for key, value in (("center_x", center_x), ("center_z", center_z)):
        if value is None:
            raise ShellEditError(422, "Say where its middle goes: center_x and center_z, in metres.")
        if not _number(value):
            raise ShellEditError(422, "A centre must be a number of metres.")
    needed = [key for key in SIZE_FIELDS[kind] if key not in OPTIONAL_SIZES and key not in sizes]
    if needed:
        raise ShellEditError(
            422, f"A new {KINDS[kind]} needs a {' and a '.join(FIELD_WORDS[key] for key in needed)}, in metres."
        )

    edited = copy.deepcopy(shell)
    stored = edited.get(kind)
    # A shell stored before rings were read has no list of them.
    items: List[Any] = list(stored) if isinstance(stored, list) else []
    if len(items) >= ITEMS_MAX:
        raise ShellEditError(
            409, f"The stored room already has {len(items)} of these, which is as many as it can hold. Delete one first."
        )

    base = _in_range(kind, "base_height", sizes.get("base_height", 0.0), 0.0, BASE_MAX_M) if kind == "risers" else 0.0
    # A raised area's deck is held to what a deck can be, and its top to the ceiling just below, in the
    # words an edited base is refused in: "a height of at most 0.5 m" would not say that the base is why.
    least, most = height_limits(edited, kind)
    high = _in_range(kind, "height", sizes["height"], least, most)
    if kind == "risers":
        _top_under_ceiling(edited, {"base_height": base, "height": high})
    x, z = float(center_x), float(center_z)

    if kind == "risers":
        what = riser_kind or "riser"
        wide = _in_range(kind, "width", sizes["width"], SIDE_MIN_M, ANY_ROOM_SIZE_MAX_M)
        deep = _in_range(kind, "depth", sizes["depth"], SIDE_MIN_M, ANY_ROOM_SIZE_MAX_M)
        turned = clean_heading(sizes.get("heading_deg", 0.0))
        x, z = _fit(edited, kind, x, z, *area_reach(wide, deep, turned))
        item: Dict[str, Any] = {
            "center_x": _mm(x), "center_z": _mm(z), "width": wide, "depth": deep,
            "height": high, "base_height": base,
            "name": clean_name(name) if name is not None else RISER_KINDS[what],
            "kind": what,
        }
        if turned != 0.0:
            # One square to the room says nothing, like every raised area stored before a heading could be set.
            item["heading_deg"] = turned
    elif kind == "truss_lines":
        long = _in_range(kind, "length", sizes["length"], LINE_MIN_M, ANY_ROOM_SIZE_MAX_M)
        heading = clean_heading(sizes.get("heading_deg", 0.0))
        radians = math.radians(heading)
        x, z = _fit(edited, kind, x, z, abs(math.cos(radians)) * long / 2.0, abs(math.sin(radians)) * long / 2.0)
        item = {"name": clean_name(name) if name is not None else f"Overhead line {len(items) + 1}"}
        _lay_line(item, x, z, long, heading)
        item.update({"height": high, "top": _mm(high + ADDED_TRUSS_DEPTH_M), "across": ADDED_TRUSS_DEPTH_M})
        # In the order a scan writes a line's keys.
        item = {key: item[key] for key in (
            "name", "x1", "z1", "x2", "z2", "height", "top", "length", "across", "axis", "heading_deg",
        )}
    else:
        round_ = _in_range(kind, "radius", sizes["radius"], RING_MIN_RADIUS_M, ANY_ROOM_SIZE_MAX_M / 2.0)
        x, z = _fit(edited, kind, x, z, round_, round_)
        item = {
            "name": clean_name(name) if name is not None else f"Overhead ring {len(items) + 1}",
            "center_x": _mm(x), "center_z": _mm(z), "radius": round_,
            "height": high, "top": _mm(high + ADDED_TRUSS_DEPTH_M), "across": ADDED_TRUSS_DEPTH_M,
        }

    item.update({"suggested": False, "added_by_hand": True, "basis": ADDED_BY_HAND})
    items.append(item)
    edited[kind] = items
    if kind != "risers":
        _count(edited, kind, item)
    return edited, item, len(items) - 1


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------

def item_name(kind: str, item: Dict[str, Any]) -> str:
    """What to call an item in a message: its name, or what it is."""
    name = item.get("name")
    return name if isinstance(name, str) and name.strip() else f"The {KINDS[kind]}"


def edit_words(kind: str, before: Dict[str, Any], after: Dict[str, Any]) -> Optional[str]:
    """What an edit did to an item, for the list of what can be undone: "Stage renamed and moved".

    None when it changed nothing, which is not a step to undo.
    """
    if before == after:
        return None
    done: List[str] = []
    if before.get("name") != after.get("name"):
        done.append("renamed")
    if _shifted(item_centre(kind, before), item_centre(kind, after)):
        done.append("moved")
    if kind == "truss_lines":
        # Ends rounded to the millimetre can put a turned line's length a millimetre or two out.
        was, now = _line_length(before), _line_length(after)
        longer = (was is None) != (now is None) or (was is not None and abs(was - now) > 0.003)
        resized = longer or before.get("height") != after.get("height")
    else:
        resized = any(before.get(key) != after.get(key) for key in ("width", "depth", "radius", "height"))
    if resized:
        done.append("resized")
    if kind == "truss_lines" and line_heading(before) != line_heading(after):
        done.append("turned")
    if kind == "risers":
        if area_heading(before) != area_heading(after):
            done.append("turned")
        if _mm(base_of(before)) != _mm(base_of(after)):
            done.append("raised" if base_of(after) > base_of(before) else "lowered")
        if before.get("kind") != after.get("kind") and after.get("kind") in RISER_KINDS:
            # A riser that was called "Riser" and is now a stage called "Stage" was not renamed by anybody.
            if "renamed" in done and after.get("name") == RISER_KINDS[after["kind"]]:
                done.remove("renamed")
            done.append(f"made a {after['kind']}")
    if not done:
        done.append("changed")
    words = done[0] if len(done) == 1 else f"{', '.join(done[:-1])} and {done[-1]}"
    return f"{item_name(kind, before)} {words}"
