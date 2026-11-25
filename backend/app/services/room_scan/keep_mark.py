"""
Keeping the DJ booth mark when a room is scanned again
======================================================

A person marks one raised area of the stored room as the DJ's booth
(`is_dj_booth`, edit.py). A scan read again makes a whole new room, and its
raised areas carry no mark: the lists have no ids, so nothing says which of
the new ones is the one that was marked. This says which, by where it stands
(docs/ROOM_SCAN.md, slices 30 and 31).

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
   A kind set by hand is not compared (slice 31, `kind_set_by_hand`): where
   the marked one's stored `basis` says "Kind set by hand." (edit.py writes
   that when a person changes a kind), or it was added by hand
   (`added_by_hand`), the scan will read what stands there as what it always
   did, so a raised area of any kind that overlaps enough is the same one. It
   takes the mark and the kind the person gave, and its `basis` says the kind
   was set by hand, so the reading after this one keeps it too.
3. Of several that pass, the one with the greatest overlap takes it; of two
   that overlap exactly as much, the earlier in the list.
4. With none that passes, the mark is dropped and the answer says so. It is
   never given to the nearest thing, or to the scan's first booth: a mark set
   by hand is only ever kept where it was, not moved.

Only the mark is carried here, and with it a kind set by hand. A name, a
height and a base height set by hand are carried by keep_edits.py (slice 32),
for every raised area and by the same matching (`best_match`, points 2 and
3); a width, a depth, a heading and a place set by hand are not: those are
the scan's.

The route calls this once, after keep_edits.py and on the room that returns,
before it answers a preview or applies: what a preview says will become of
the mark is what apply then does.

Overhead lines and rings are matched by the same rule (slice 33): only what a
footprint is differs (`_footprint`). A line's is the strip `LINE_STRIP_M` wide
that runs along it from end to end (or as wide as the truss is, if that is
wider): a truss is 0.3 m across, and two readings of the same one 0.1 m apart
would share only half of that. A ring's is the disc it goes round, as a polygon
of `RING_SIDES` sides. Neither has a kind, so none is compared, and a line is
only ever asked of lines and a ring of rings: the caller gives the list.
Heights are not looked at for them either.

Pure: the shells given are never changed, and a new one is returned only when
there is a mark to write.
"""

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.room_scan.edit import (
    DJ_BOOTH_KEY, KIND_BY_HAND, RISER_KINDS, _mark, _number, area_corners, dj_booth_place, item_name,
)

# How much of the two footprints together must be shared for a raised area of the new reading to be
# the marked one: intersection over union. 0.5 lets a booth be read a little off, a little bigger or
# a few degrees round, and refuses the next booth along.
MATCH_IOU = 0.5

# How wide the strip is that stands for an overhead line on the plan. Two readings of one truss a
# distance d apart sideways share (W - d) / (W + d) of the two strips together, so they are the same
# truss up to d = W / 3: 0.2 m. Trusses hung 0.6 m apart or more share nothing.
LINE_STRIP_M = 0.6
# How many sides the polygon has that stands for a ring's disc.
RING_SIDES = 24

Point = Tuple[float, float]


@dataclass(frozen=True)
class KeptMark:
    """What became of the DJ booth mark when a room was read again."""
    shell: Dict[str, Any]           # the new room, with the mark on the raised area that keeps it
    was_marked: bool                # whether the room it replaces had a marked raised area
    place: Optional[int] = None     # where the mark now is in the new room's risers, or None
    overlap: Optional[float] = None  # the intersection over union it was kept at
    name: Optional[str] = None      # what the marked raised area was called, for the sentence
    # A kind set by hand that was kept against the reading: what the person made it, and what the scan
    # read there. Both None where the reading agrees, or the kind was the scan's own.
    kind_kept: Optional[str] = None
    scan_kind: Optional[str] = None

    @property
    def dropped(self) -> bool:
        return self.was_marked and self.place is None

    @property
    def kept_on(self) -> Optional[str]:
        """What the raised area that keeps the mark is called in the new room, or None."""
        if self.place is None:
            return None
        return item_name("risers", self.shell["risers"][self.place])

    @property
    def _kind_words(self) -> str:
        if self.kind_kept is None:
            return ""
        return f" It stays a {self.kind_kept}, as set by hand: this scan reads it as a {self.scan_kind}."

    def preview(self) -> Optional[Dict[str, Any]]:
        """What a preview says will become of the mark on apply, or None when there is no mark to speak of."""
        if not self.was_marked:
            return None
        return {
            "kept": self.place is not None,
            "dropped": self.dropped,
            # Where the mark will be in the new room's risers and what that raised area is called, or null.
            "index": self.place,
            "name": self.kept_on,
            "overlap": self.overlap,
            # The kind set by hand that is kept against the reading, or null.
            "kind_kept": self.kind_kept,
            "message": (
                f"The DJ booth mark will be dropped: no raised area in this scan stands where {self.name} does. "
                "Mark the DJ booth again in Edit Room after applying."
                if self.place is None else
                f"The DJ booth mark will be kept on {self.kept_on}.{self._kind_words}"
            ),
        }

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
        return f"The DJ booth mark was kept on {self.kept_on}.{self._kind_words}"


def kind_set_by_hand(item: Any) -> bool:
    """Whether a person, not the scan, said what kind of raised area this is.

    Read from what is already stored: edit.py writes "Kind set by hand." into
    the `basis` of a raised area whose kind a person changed, and marks one a
    person added (`added_by_hand`), whose kind was theirs from the start.
    """
    if not isinstance(item, dict):
        return False
    return item.get("added_by_hand") is True or KIND_BY_HAND in str(item.get("basis") or "")


def _line_footprint(item: Dict[str, Any]) -> Optional[List[Point]]:
    """The strip along an overhead line, from its ends as they are stored (not its heading, kept to a tenth)."""
    ends = [item.get(key) for key in ("x1", "z1", "x2", "z2")]
    if not all(_number(end) for end in ends):
        return None
    run_x, run_z = ends[2] - ends[0], ends[3] - ends[1]
    length = math.hypot(run_x, run_z)
    if length <= 0:
        return None
    across = item.get("across")
    half = max(LINE_STRIP_M, float(across) if _number(across) else 0.0) / 2.0
    side_x, side_z = -run_z / length * half, run_x / length * half
    return [
        (ends[0] - side_x, ends[1] - side_z), (ends[2] - side_x, ends[3] - side_z),
        (ends[2] + side_x, ends[3] + side_z), (ends[0] + side_x, ends[1] + side_z),
    ]


def _ring_footprint(item: Dict[str, Any]) -> Optional[List[Point]]:
    """The disc an overhead ring goes round, as a polygon."""
    numbers = [item.get(key) for key in ("center_x", "center_z", "radius")]
    if not all(_number(value) for value in numbers) or numbers[2] <= 0:
        return None
    return [
        (numbers[0] + numbers[2] * math.cos(2 * math.pi * k / RING_SIDES),
         numbers[1] + numbers[2] * math.sin(2 * math.pi * k / RING_SIDES))
        for k in range(RING_SIDES)
    ]


def _footprint(item: Any) -> Optional[List[Point]]:
    """An item's footprint on the plan, anticlockwise in (x, z), or None when it has none to compare.

    A raised area's four corners, turned to its heading; the strip along an
    overhead line (one that stores ends); the disc of a ring (one that stores
    a radius). What an item is, is read from what it stores.
    """
    if not isinstance(item, dict):
        return None
    if "x1" in item or "radius" in item:
        corners = _line_footprint(item) if "x1" in item else _ring_footprint(item)
        if corners is None:
            return None
        return corners if _signed_area(corners) > 0 else corners[::-1]
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
    """How much two raised areas (or two lines, or two rings) share on the plan: intersection over union, 0 to 1.

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


def best_match(area: Any, risers: Any) -> Tuple[Optional[int], float]:
    """Which raised area of a new reading is the stored one given, and by how much they overlap.

    The one matching rule (points 2 and 3 at the top of this file), for the
    DJ booth mark and for every other thing kept across a reading
    (keep_edits.py): the same kind, unless the stored one's kind was set by
    hand; an intersection over union of at least `MATCH_IOU`; the greatest
    overlap, and of two equal the earlier. (None, 0.0) when none passes.

    Asked the same way of an overhead line among the new reading's lines, a
    ring among its rings (neither stores a kind, so none differs), and a
    raised area a person deleted among its raised areas (slice 33).
    """
    if not isinstance(area, dict) or not isinstance(risers, list):
        return None, 0.0
    # A kind a person set is theirs, not one the scan can be expected to read again: any kind may match.
    by_hand = kind_set_by_hand(area) and area.get("kind") in RISER_KINDS
    best: Optional[int] = None
    best_overlap = 0.0
    for index, item in enumerate(risers):
        if not isinstance(item, dict) or (item.get("kind") != area.get("kind") and not by_hand):
            continue
        overlap = footprint_overlap(area, item)
        # Strictly greater: of two that overlap as much, the earlier keeps it.
        if overlap >= MATCH_IOU and overlap > best_overlap:
            best, best_overlap = index, overlap
    return best, best_overlap


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
    best, best_overlap = best_match(marked, risers)

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
    item = kept["risers"][best]
    item[DJ_BOOTH_KEY] = True
    kind_kept = scan_kind = None
    if item.get("kind") != marked.get("kind"):
        # Only reached for a kind set by hand. It is kept as edit.py would have changed it, and the
        # basis says so: that is what keeps it at the reading after this one.
        scan_kind, kind_kept = item.get("kind"), marked["kind"]
        item["kind"] = kind_kept
        if item.get("name") == RISER_KINDS.get(scan_kind if isinstance(scan_kind, str) else ""):
            item["name"] = RISER_KINDS[kind_kept]
        _mark(item, KIND_BY_HAND)
    return KeptMark(
        shell=kept, was_marked=True, place=best, overlap=round(best_overlap, 3), name=name,
        kind_kept=kind_kept, scan_kind=scan_kind,
    )
