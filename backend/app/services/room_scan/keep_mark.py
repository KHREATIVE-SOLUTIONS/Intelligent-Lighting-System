"""
Keeping the DJ booth mark when a room is scanned again
======================================================

A person marks one raised area of the stored room as the DJ's booth
(`is_dj_booth`, edit.py). A scan read again makes a whole new room, and its
raised areas carry no mark: the lists have no ids, so nothing says which of
the new ones is the one that was marked. This says which, by where it stands
(docs/ROOM_SCAN.md, slice 30).

The rule, in full:

1. The room being replaced has a marked raised area (`dj_booth_place`: the
   first, should a shell written by hand mark two). With none, nothing is
   done and nothing is reported.
2. A raised area of the new reading can take the mark only if it is the same
   kind (`stage`, `riser` or `booth`) as the marked one is now, and its
   footprint on the plan overlaps the marked one's by an intersection over
   union of at least `MATCH_IOU` (0.5). The footprints are the rectangles
   turned to their headings (`area_corners`), so a booth that stands at a
   heading is compared as it stands, and the same rectangle stored as 2 x 1 at
   0 degrees or 1 x 2 at 90 is the same footprint.
3. Of several that pass, the one with the greatest overlap takes it; of two
   that overlap exactly as much, the earlier in the list.
4. With none that passes, the mark is dropped and the answer says so. It is
   never given to the nearest thing, or to the scan's first booth: a mark set
   by hand is only ever kept where it was, not moved.

Only the mark is carried. A name, a kind or a size set by hand on the old
raised area is not: the new reading is the scan's.

Pure: the shells given are never changed, and a new one is returned only when
there is a mark to write.
"""

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.room_scan.edit import DJ_BOOTH_KEY, _number, area_corners, dj_booth_place, item_name

# How much of the two footprints together must be shared for a raised area of the new reading to be
# the marked one: intersection over union. 0.5 lets a booth be read a little off, a little bigger or
# a few degrees round, and refuses the next booth along.
MATCH_IOU = 0.5

Point = Tuple[float, float]


@dataclass(frozen=True)
class KeptMark:
    """What became of the DJ booth mark when a room was read again."""
    shell: Dict[str, Any]           # the new room, with the mark on the raised area that keeps it
    was_marked: bool                # whether the room it replaces had a marked raised area
    place: Optional[int] = None     # where the mark now is in the new room's risers, or None
    overlap: Optional[float] = None  # the intersection over union it was kept at
    name: Optional[str] = None      # what the marked raised area was called, for the sentence

    @property
    def dropped(self) -> bool:
        return self.was_marked and self.place is None

    @property
    def message(self) -> Optional[str]:
        """A sentence for the operator, or None when there was no mark to speak of."""
        if not self.was_marked:
            return None
        if self.place is None:
            return (
                f"The DJ booth mark was dropped: no raised area in this scan stands where {self.name} did. "
                "Mark the DJ booth again in Edit Room."
            )
        kept_on = item_name("risers", self.shell["risers"][self.place])
        return f"The DJ booth mark was kept on {kept_on}."


def _footprint(item: Any) -> Optional[List[Point]]:
    """A raised area's corners on the plan, anticlockwise in (x, z), or None when it has no footprint to compare."""
    if not isinstance(item, dict):
        return None
    numbers = [item.get(key) for key in ("center_x", "center_z", "width", "depth")]
    if not all(_number(value) for value in numbers) or numbers[2] <= 0 or numbers[3] <= 0:
        return None
    corners = area_corners(item)
    return corners if _signed_area(corners) > 0 else corners[::-1]


def _signed_area(polygon: List[Point]) -> float:
    """The shoelace area: positive for corners that go anticlockwise in (x, z)."""
    total = 0.0
    for k, (x1, z1) in enumerate(polygon):
        x2, z2 = polygon[(k + 1) % len(polygon)]
        total += x1 * z2 - x2 * z1
    return total / 2.0


def _clip(subject: List[Point], clip: List[Point]) -> List[Point]:
    """The part of one convex polygon inside another (Sutherland-Hodgman). Both anticlockwise."""
    kept = subject
    for k, a in enumerate(clip):
        b = clip[(k + 1) % len(clip)]
        if not kept:
            break

        def side(p: Point) -> float:
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        points, kept = kept, []
        for j, current in enumerate(points):
            previous = points[j - 1]
            here, before = side(current), side(previous)
            if (here >= 0) != (before >= 0):
                t = before / (before - here)
                kept.append((previous[0] + t * (current[0] - previous[0]), previous[1] + t * (current[1] - previous[1])))
            if here >= 0:
                kept.append(current)
    return kept


def footprint_overlap(one: Any, other: Any) -> float:
    """How much two raised areas share on the plan: intersection over union, 0 to 1.

    0 when either has no footprint (a number missing, or no size). Heights are
    not looked at: a booth read 5 cm taller is the same booth.
    """
    a, b = _footprint(one), _footprint(other)
    if a is None or b is None:
        return 0.0
    shared = _clip(a, b)
    inter = abs(_signed_area(shared)) if len(shared) >= 3 else 0.0
    union = _signed_area(a) + _signed_area(b) - inter
    if union <= 0:
        return 0.0
    return max(0.0, min(1.0, inter / union))


def keep_dj_booth(old_shell: Optional[Dict[str, Any]], new_shell: Dict[str, Any]) -> KeptMark:
    """The new room with the DJ booth mark kept where the old room had it, and what became of the mark.

    See the rule at the top of this file. Neither shell is changed. With no
    mark in the old room the new one is returned as it is, the same object.
    """
    place = dj_booth_place(old_shell)
    if place is None:
        return KeptMark(shell=new_shell, was_marked=False)
    marked = old_shell["risers"][place]
    name = item_name("risers", marked)
    risers = new_shell.get("risers") if isinstance(new_shell, dict) else None

    best: Optional[int] = None
    best_overlap = 0.0
    for index, item in enumerate(risers if isinstance(risers, list) else []):
        if not isinstance(item, dict) or item.get("kind") != marked.get("kind"):
            continue
        overlap = footprint_overlap(marked, item)
        # Strictly greater: of two that overlap as much, the earlier keeps it.
        if overlap >= MATCH_IOU and overlap > best_overlap:
            best, best_overlap = index, overlap

    already = [index for index, item in enumerate(risers if isinstance(risers, list) else [])
               if isinstance(item, dict) and DJ_BOOTH_KEY in item]
    if best is None and not already:
        return KeptMark(shell=new_shell, was_marked=True, name=name)
    kept = copy.deepcopy(new_shell)
    # A reading marks nothing itself; should one ever, only the kept mark stands.
    for index in already:
        kept["risers"][index].pop(DJ_BOOTH_KEY, None)
    if best is None:
        return KeptMark(shell=kept, was_marked=True, name=name)
    kept["risers"][best][DJ_BOOTH_KEY] = True
    return KeptMark(shell=kept, was_marked=True, place=best, overlap=round(best_overlap, 3), name=name)
