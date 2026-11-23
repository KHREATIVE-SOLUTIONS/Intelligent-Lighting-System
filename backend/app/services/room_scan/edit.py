"""
Editing a stored room by hand
=============================

A room scan suggests a stage, risers, a booth, trusses and rings of truss. A
person looking at the room knows better: the "Booth or counter" is the bar, the
truss is half a metre further upstage, the "riser" is a flight case somebody
left on the floor. This renames, moves and deletes one of those at a time in
the shell stored on a rig (docs/ROOM_SCAN.md).

Pure: a shell goes in and a new shell comes out, and the one given is never
changed. That matters to the caller, whose column is plain JSON: a change made
in place to what was loaded is never written.

What an item is addressed by is the list it is stored in and its place in that
list (`truss_lines`, 1). The lists carry no ids, and the views leave out items
they cannot draw, so a place on the plan is not a place in the list.

Nothing here moves a fixture. A fixture hung on a truss that is then moved or
deleted stays where it is.
"""

import copy
import math
from typing import Any, Dict, Optional, Tuple

# The lists of a scanned shell that can be edited, and what one item is called.
KINDS: Dict[str, str] = {
    "risers": "raised area",
    "truss_lines": "overhead line",
    "truss_rings": "overhead ring",
}

NAME_MAX = 60

# How far past the room's own box the middle of an item may be put: the margin
# a fixture's position is held to (fixture_position.OUTSIDE_MARGIN_M).
OUTSIDE_MARGIN_M = 2.0

MOVED_BY_HAND = "Moved by hand."

# Slack when deciding which hanging-height band a truss was counted in: the
# shell's heights are rounded to the centimetre.
BAND_SLACK_M = 0.011


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


def _find(shell: Optional[Dict[str, Any]], kind: str, index: int) -> Dict[str, Any]:
    """The stored item, or the refusal that says why there is none."""
    if kind not in KINDS:
        raise ShellEditError(404, f"'{kind}' is not part of a room that can be edited. Use one of: {', '.join(KINDS)}.")
    if not isinstance(shell, dict) or shell.get("source") != "scan":
        raise ShellEditError(404, "This rig has no scanned room stored, so there is nothing to edit.")
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


def _held(shell: Dict[str, Any], x: float, z: float) -> Tuple[float, float]:
    """A centre held to the room's box and the margin round it. Left alone when the room has no size."""
    room = shell.get("room") if isinstance(shell.get("room"), dict) else {}
    width, depth = room.get("width"), room.get("depth")
    if _number(width) and width > 0:
        limit = width / 2.0 + OUTSIDE_MARGIN_M
        x = max(-limit, min(limit, x))
    if _number(depth) and depth > 0:
        limit = depth / 2.0 + OUTSIDE_MARGIN_M
        z = max(-limit, min(limit, z))
    return x, z


def clean_name(name: str) -> str:
    """A name as it is stored: trimmed, one line, with something in it."""
    cleaned = " ".join(str(name).split())
    if not cleaned:
        raise ShellEditError(422, "A name needs at least one letter or number.")
    if len(cleaned) > NAME_MAX:
        raise ShellEditError(422, f"A name can be at most {NAME_MAX} characters; this one is {len(cleaned)}.")
    return cleaned


def edit_item(
    shell: Optional[Dict[str, Any]],
    kind: str,
    index: int,
    name: Optional[str] = None,
    center_x: Optional[float] = None,
    center_z: Optional[float] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the shell with one item renamed or moved, that item). The shell given is not changed.

    `center_x` and `center_z` are where the middle of the item goes; either
    left out keeps what it has. A line keeps its length and heading: both ends
    take the same shift. The middle is held to the room's box and a 2 m margin
    round it, and stored to the millimetre. A moved item is no longer a
    suggestion (`suggested` false) and its `basis` says it was moved by hand.
    A rename changes the name and nothing else.
    """
    _find(shell, kind, index)
    if name is None and center_x is None and center_z is None:
        raise ShellEditError(422, "Nothing to change: give a name, a centre, or both.")
    for value in (center_x, center_z):
        if value is not None and not _number(value):
            raise ShellEditError(422, "A centre must be a number of metres.")

    edited = copy.deepcopy(shell)
    item = edited[kind][index]

    if name is not None:
        item["name"] = clean_name(name)

    if center_x is not None or center_z is not None:
        centre = item_centre(kind, item)
        if centre is None:
            raise ShellEditError(
                409,
                f"This {KINDS[kind]} has no position stored that can be moved. Delete it, or read the scan again.",
            )
        to_x, to_z = _held(
            edited,
            centre[0] if center_x is None else float(center_x),
            centre[1] if center_z is None else float(center_z),
        )
        dx, dz = _mm(to_x - centre[0]), _mm(to_z - centre[1])
        if dx != 0 or dz != 0:
            if kind == "truss_lines":
                item["x1"], item["x2"] = _mm(item["x1"] + dx), _mm(item["x2"] + dx)
                item["z1"], item["z2"] = _mm(item["z1"] + dz), _mm(item["z2"] + dz)
            else:
                item["center_x"], item["center_z"] = _mm(centre[0] + dx), _mm(centre[1] + dz)
            # A person put it here: it is no longer the scan's guess.
            item["suggested"] = False
            basis = str(item.get("basis") or "").strip()
            if MOVED_BY_HAND not in basis:
                item["basis"] = f"{basis} {MOVED_BY_HAND}".strip()

    return edited, item


def _uncount(shell: Dict[str, Any], kind: str, removed: Dict[str, Any]) -> None:
    """Take a deleted truss out of the hanging-height band that counted it.

    A band with nothing left in it is dropped: a suggestion would otherwise go
    on hanging rows at a height where nothing hangs any more (suggest.py).
    """
    bands = shell.get("hanging_bands")
    if not isinstance(bands, list):
        return
    key = "lines" if kind == "truss_lines" else "rings"
    other = "rings" if key == "lines" else "lines"

    def held(band: Any, name: str) -> int:
        value = band.get(name) if isinstance(band, dict) else None
        return int(value) if _number(value) and value > 0 else 0

    remaining = [item for item in (shell.get("truss_lines") or []) + (shell.get("truss_rings") or [])
                 if isinstance(item, dict)]
    if not remaining:
        # Nothing hangs in the room any more, whatever the bands add up to.
        shell["hanging_bands"] = []
        return

    height = removed.get("height")
    if not _number(height):
        return
    inside = [
        band for band in bands
        if held(band, key) > 0 and _number(band.get("height"))
        and band["height"] - BAND_SLACK_M <= height
        <= (band["top"] if _number(band.get("top")) else band["height"]) + BAND_SLACK_M
    ]
    if not inside:
        return
    band = min(inside, key=lambda b: abs(b["height"] - height))
    band[key] = held(band, key) - 1
    if band[key] == 0 and held(band, other) == 0:
        shell["hanging_bands"] = [b for b in bands if b is not band]
    elif band[key] == 0 and key == "lines":
        band["basis"] = "scan: a ring hanging clear of the walls at this height"


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


def item_name(kind: str, item: Dict[str, Any]) -> str:
    """What to call an item in a message: its name, or what it is."""
    name = item.get("name")
    return name if isinstance(name, str) and name.strip() else f"The {KINDS[kind]}"
