"""
Keeping what a person set in a room when the room is scanned again
==================================================================

A scan applied again writes a whole new room. A person who had corrected the
old one (typed a name, set a height, put in a riser the scan never saw, taken
out a "riser" that was a flight case) lost all of it. This carries those
corrections onto the new reading (docs/ROOM_SCAN.md, slices 32 to 36), for
raised areas, overhead lines and overhead rings.

Which stored item is which new one is `keep_mark.best_match`, the rule the DJ
booth mark is kept by, asked here for every stored item: the same kind unless
the kind was set by hand (a line and a ring have no kind), footprints
overlapping by an intersection over union of at least 0.5, the greatest
overlap, the earlier of two equal. A raised area is only asked of raised
areas, a line of lines, a ring of rings. There is no second rule: what differs
between the three is what a footprint is (keep_mark.py, `_footprint`), and
that a line or ring read more than 1.0 m above or below where the scan read
the stored one is not it (`HANG_MATCH_M`, slice 34).

What counts as set by hand is read from what is stored (`hand_edits`):

- a **name**: the `basis` says "Name set by hand." (edit.py writes it when a
  rename changes a name), or the item was added by hand under a name that is
  not just what it would be called anyway ("Riser", "Overhead line 3");
- a **height** (a raised area's deck; the height a line or ring hangs at): the
  `basis` says "Height set by hand.", or it was added by hand;
- a **base height** (raised areas only): the `basis` says "Base height set by
  hand.", or it was added by hand.

"Resized by hand." alone says none of them: it is written for a width, a
depth, a length, a radius and a heading too. A room edited before these marks
were written keeps nothing.

What is done, in this order:

0. **Raised areas, lines and rings a person deleted** (`deleted_areas` in the
   stored room, edit.py `tombstone`; lines and rings slice 34). Each record is
   asked, by the same rule, which item of the new reading it is, in the list
   it was deleted from (a record with ends is a line's, one with a radius a
   ring's). One it matches is left out of the new room and reported, and its
   record goes on to the new room (with the footprint, and for a line or ring
   the height, this reading gave), so it is left out at the reading after
   too. A line or ring left out is taken out of `hanging_bands`, as Edit Room
   does when one is deleted. Two records that pick the same new item: the
   greater overlap has it, the earlier of two equal. A record that matches
   nothing is dropped: the scan no longer reads anything there. This is done
   first: everything below is asked of the new room without those items, so
   one a person deleted and then put in again by hand, their way, is kept as
   theirs.
1. A stored item with anything set by hand that matches a new one gives it
   the name, the height and the base height that were set by hand, and the
   new one's `basis` says so again, so the reading after this one keeps them
   too. Where it is, how big or long it is and its heading are the scan's:
   the scan measures those better than a person drags them. A raised area's
   kind is the scan's too (only the marked DJ booth keeps a kind:
   keep_mark.py). A line or ring given a height keeps its depth (its `top`
   goes with it) and is counted again in `hanging_bands`, as Edit Room does;
   the height this reading gave is stored beside it (`scan_height`), for the
   reading after to match by.
2. Two stored items that pick the same new one: the greater overlap has it,
   the earlier of two equal. The other is treated as one that matched nothing.
   Every stored item is asked, with or without anything to keep: a riser a
   person added on top of the scan's own does not rename the scan's riser
   when it is read again; it is replaced (4).
3. An item **added by hand** that matches nothing and does not share the plan
   with any item of its list in the new reading (`SHARED`) is kept as it is,
   at the end of its list, so every place the scan gave is what it was. An
   added line or ring is counted in `hanging_bands`.
4. One added by hand that matches nothing but does share the plan with a new
   one is not kept: the scan has something there now, and two things in one
   place is worse than one. It is reported, with what replaced it.
5. Anything else that matches nothing is not carried: a name has nowhere to
   go. It is said (point 7), but for a raised area the scan no longer reads
   at all, or reads as another kind.
6. **Checks.** What was kept is kept whatever the new room is, but it is
   flagged (`warnings`) where the new room cannot hold it: a kept height (a
   raised area's top, a line's or ring's hanging height) above the new
   ceiling, and an item added by hand and kept as it is any part of which is
   outside the new walls or above the ceiling. The walls and the ceiling are
   asked as Edit Room asks them (outline_edit.outside_report).

7. **Nothing is lost without a word** (slice 35; `lost`, said in `warnings`).
   - A line or ring with a name or a hanging height set by hand (not one
     added by hand) that matches nothing, where the new reading has a line or
     ring that no stored one is and that would have been it but for the
     height it hangs at (shares half the plan, read more than `HANG_MATCH_M`
     from where the scan read the stored one), or that shares some of the
     plan with it but less than the half a match needs (read to one side, or
     at another length). The warning names it, and says where the scan read
     that one.
   - A record of a deleted raised area, line or ring that matches nothing and
     is dropped (point 0). The warning names it.
   Only the reading's items that no stored item is are looked at: the other
   truss of a stack, and a truss that crosses, are themselves and not this
   one read differently.
   Slice 36 says three more, and lists each in `items` as `LOST`:
   - A raised area with a name, a height or a base height set by hand that
     matches nothing, where the new reading has a raised area that no stored
     one is and that shares some floor with it but less than the half a match
     needs (`LOST_BESIDE`). The warning names it and the new area.
   - A line or ring with a name or a trim set by hand that matches nothing
     and has no such item of the reading near it: the scan no longer reads it
     at all (`LOST_GONE`).
   - Of two stored items that pick the same new one (point 2), the one that
     does not have it, where it had something set by hand and was not added
     by hand (that one is replaced, point 4): `LOST_OTHER`. The warning names
     both, and what the scan reads there.
8. **What can be put back** (slice 36; `carry`, said as `carry_over`). Every
   warning of point 7 that has an item of the new room behind it (read at
   another height, read beside, lost to another) is also given in a form a
   program can act on: the list, the old name, the old trim or height, the
   place and name of the new item, and why. Nothing is written for it here:
   carry_over.py puts the old name and trim onto that item when asked.

What was done is also listed one thing at a time (`items` in the answer,
slice 35): what it is ("raised area", "line", "ring"), its name, and which of
five things happened to it (`KEPT`, `LEFT_OUT`, `REPLACED`, `ADDED_KEPT`, and
since slice 36 `LOST`).

"Shares the plan" (`SHARED`): two raised areas share it with any floor in
common at all; two that only touch along an edge do not. Trusses cross and
hang side by side, so two lines, or two rings, share it only when their
footprints overlap by more than `CROSSING` (0.2): more than two trusses that
cross do, less than one truss read 0.3 m to one side.

Call this before `keep_dj_booth`, and give that the room this returns: a
marked booth added by hand and kept as it is then keeps its mark (it matches
itself), and the mark's sentence names the raised area by its kept name.

Pure: the shells given are never changed, and with nothing to carry the new
one is returned as it is, the same object.
"""

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.room_scan.edit import (
    BASE_BY_HAND, DELETED_KEY, HEIGHT_BY_HAND, KINDS, NAME_BY_HAND, RESIZED_BY_HAND, RISER_KINDS, SCAN_HEIGHT_KEY,
    _count, _mark, _metres, _mm, _note, _number, _uncount, base_of, item_centre, item_name, scan_read_height,
)
from app.services.room_scan.keep_mark import HANG_MATCH_M, MATCH_IOU, best_match, footprint_overlap
from app.services.room_scan.outline_edit import ABOVE, outside_report

# Less shared floor than this (as intersection over union) is two raised areas that touch, not overlap.
TOUCHING = 1e-6
# Two lines, or two rings, that share no more than this are two that cross or hang side by side.
CROSSING = 0.2
# How much of the plan an item added by hand may share with one of the new reading and still be kept.
SHARED: Dict[str, float] = {"risers": TOUCHING, "truss_lines": CROSSING, "truss_rings": CROSSING}

OVERHEAD: Tuple[str, ...] = ("truss_lines", "truss_rings")

# What each list's items are called in `items`, the list of what was done one thing at a time (slice 35).
ITEM_WORDS: Dict[str, str] = {"risers": "raised area", "truss_lines": "line", "truss_rings": "ring"}
# The four things that can have been done to one. The same words in a preview and after Apply.
KEPT = "kept your edits"
LEFT_OUT = "left out (you deleted it)"
REPLACED = "replaced (a scanned item overlaps it)"
ADDED_KEPT = "added by hand, kept"
# Slice 36: a name, a trim or a height set by hand that went nowhere (the three new warnings only).
LOST = "lost"

# Why something was lost: the `reason` of a warning that has no place in the new room (slice 35).
LOST_HEIGHT = "hanging height"      # read over the same plan, more than HANG_MATCH_M from where it was read
LOST_BESIDE = "read beside"         # read sharing some of the plan, less than the half a match needs
LOST_RECORD = "record dropped"      # a record of a deleted item that this reading has nothing for
LOST_GONE = "no longer read"        # a line or ring the reading has nothing near (slice 36)
LOST_OTHER = "another has it"       # of two stored items that pick one new item, the one that does not have it
# What the scan read in the place of a line and of a ring, in a sentence.
_READ_WORDS: Dict[str, str] = {"truss_lines": "a truss", "truss_rings": "a ring"}

# What a record of a deleted item takes from the reading that has it again: where the next is matched.
_RECORD_READ: Dict[str, Tuple[str, ...]] = {
    "risers": ("center_x", "center_z", "width", "depth", "heading_deg"),
    "truss_lines": ("x1", "z1", "x2", "z2", "across", "height"),
    "truss_rings": ("center_x", "center_z", "radius", "height"),
}


def _record_list(record: Any) -> str:
    """The list a record of a deleted item was deleted from, read from what it stores (as keep_mark._footprint)."""
    if isinstance(record, dict) and "x1" in record:
        return "truss_lines"
    if isinstance(record, dict) and "radius" in record:
        return "truss_rings"
    return "risers"

# What each kept field is called in a sentence, in the order they are said.
EDIT_WORDS: Dict[str, str] = {"name": "name", "height": "height", "base_height": "base height"}
# A line's or a ring's height is the height it hangs at.
OVERHEAD_EDIT_WORDS: Dict[str, str] = {"name": "name", "height": "hanging height"}

# What a line or ring is called when nobody named it: by a scan, and by Edit Room when one is added.
_UNNAMED = re.compile(r"Overhead (line|ring) \d+")


def hand_edits(item: Any, kind: str = "risers") -> Tuple[str, ...]:
    """Which of a stored item's name, height and base height a person set: keys of EDIT_WORDS.

    `kind` is the list it is stored in. A line or a ring has no base height.
    """
    if not isinstance(item, dict):
        return ()
    basis = str(item.get("basis") or "")
    added = item.get("added_by_hand") is True
    name = item.get("name")
    if kind == "risers":
        unnamed = name == RISER_KINDS.get(str(item.get("kind")))
    else:
        unnamed = isinstance(name, str) and _UNNAMED.fullmatch(name) is not None
    found = []
    if isinstance(name, str) and name.strip() and (NAME_BY_HAND in basis or (added and not unnamed)):
        found.append("name")
    if _number(item.get("height")) and (HEIGHT_BY_HAND in basis or added):
        found.append("height")
    if kind == "risers" and (BASE_BY_HAND in basis or added):
        found.append("base_height")
    return tuple(found)


def _plural(count: int, kind: str = "risers") -> str:
    return f"{count} {KINDS[kind]}{'' if count == 1 else 's'}"


@dataclass(frozen=True)
class KeptEdits:
    """What was carried from the room being replaced onto a new reading."""
    shell: Dict[str, Any]   # the new room, with what was kept
    # Each {"index", "edits", "overlap"}: a raised area of the new room and which fields it kept.
    kept: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"index"}: a raised area added by hand, kept as it was at that place in the new room.
    added_kept: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"name", "by_index"}: one added by hand that the scan now has something in the place of.
    added_replaced: List[Dict[str, Any]] = field(default_factory=list)
    # The same three for overhead lines and rings, each entry with the "kind" (the list) its index is in.
    overhead_kept: List[Dict[str, Any]] = field(default_factory=list)
    overhead_added_kept: List[Dict[str, Any]] = field(default_factory=list)
    overhead_added_replaced: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"name", "kind", "overlap"}: an item of the reading left out because a person deleted it. `kind`
    # is a raised area's kind ("stage", "riser", "booth"), and "truss_lines" or "truss_rings" for one of those.
    left_out: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"kind", "index", "reason"}: something kept that the new room's ceiling or walls do not hold.
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"kind", "name", "reason", ...}: something that was not kept and is not in the new room to point
    # at (slice 35). `kind` is the list. A line's or ring's name or trim lost to the height it was read at
    # (LOST_HEIGHT: "edits", "read_height", "trim", "scan_height") or to where on the plan (LOST_BESIDE:
    # "edits", "offset", "overlap"), and a record of a deleted item dropped (LOST_RECORD).
    # Slice 36 adds: a raised area read beside (LOST_BESIDE with "by_index", the new area), a line or ring
    # no longer read (LOST_GONE), and one that lost its new item to another stored one (LOST_OTHER:
    # "kept", the stored one that has it, "read", what the scan calls the new item, and "by_index").
    lost: List[Dict[str, Any]] = field(default_factory=list)
    # Each {"kind", "old_name", "old_trim_or_height", "edits", "new_index", "reason", "lost"}: an entry of
    # `lost` (at place "lost") that has an item of the new room behind it, in the form carry_over.py
    # takes (slice 36). `kind` is the list; a raised area's also has "old_base_height".
    carry: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(
            self.kept or self.added_kept or self.added_replaced or self.overhead_kept
            or self.overhead_added_kept or self.overhead_added_replaced or self.left_out or self.lost
        )

    def report(self, shell: Optional[Dict[str, Any]] = None, applied: bool = False) -> Optional[Dict[str, Any]]:
        """What an answer says of it, or None when nothing was carried, replaced or left out.

        `shell` is the room as it will be stored (the DJ booth mark can still
        rename a raised area after this); names are read from it. `applied`
        words the sentence as done, not as what Apply will do.

        `areas`, `kept`, `added_kept`, `added_replaced` and `message` are
        always there, and speak of raised areas. `overhead_kept`,
        `overhead_added_kept`, `overhead_added_replaced`, `deleted_left_out`,
        `warnings`, `items` and `carry_over` are there only when they have
        something in them.

        `items` (slice 35) is everything above one thing at a time, in the
        order `message` says them: {"kind": "raised area" | "line" | "ring",
        "name", "outcome"}, the outcome one of LEFT_OUT, KEPT, ADDED_KEPT and
        REPLACED, worded the same before and after Apply. `warnings` holds
        the checks ({"kind", "index", "reason", "name"}) and then what was
        lost ({"kind", "name", "reason", "message"} and its numbers, with no
        index: it is not in the new room).

        Slice 36: `items` ends with what was lost in one of the three ways
        that slice names, each with the outcome LOST. `carry_over` is every
        warning with an item of the new room behind it, for a program:
        {"kind" (the list), "old_name", "old_trim_or_height", "edits",
        "new_index", "new_name", "reason", "warning"} and, for a raised area,
        "old_base_height". `warning` is the place of its warning in
        `warnings`. POST .../room-scan/carry-over takes one as it is.
        """
        if not self.any:
            return None
        room = shell or self.shell

        def called(index: int, kind: str = "risers") -> str:
            return item_name(kind, room[kind][index])

        kept = [{**entry, "name": called(entry["index"])} for entry in self.kept]
        added_kept = [{**entry, "name": called(entry["index"])} for entry in self.added_kept]
        replaced = [{**entry, "by": called(entry["by_index"])} for entry in self.added_replaced]
        over_kept = [{**entry, "name": called(entry["index"], entry["kind"])} for entry in self.overhead_kept]
        over_added = [{**entry, "name": called(entry["index"], entry["kind"])} for entry in self.overhead_added_kept]
        over_replaced = [
            {**entry, "by": called(entry["by_index"], entry["kind"])} for entry in self.overhead_added_replaced
        ]
        warnings = [{**entry, "name": called(entry["index"], entry["kind"])} for entry in self.warnings]

        was, were = ("was", "were") if applied else ("will be", "will be")
        said = []
        for kind in KINDS:
            gone = [entry for entry in self.left_out if (entry["kind"] if entry["kind"] in OVERHEAD else "risers") == kind]
            if gone:
                names = ", ".join(entry["name"] for entry in gone)
                said.append(f"{'Left' if applied else 'Will leave'} out {_plural(len(gone), kind)} you deleted: {names}.")
        for kind, words, entries in (
            ("risers", EDIT_WORDS, kept),
            *((over, OVERHEAD_EDIT_WORDS, [entry for entry in over_kept if entry["kind"] == over]) for over in OVERHEAD),
        ):
            if entries:
                each = ", ".join(
                    f"{entry['name']} ({', '.join(words[key] for key in entry['edits'])})" for entry in entries
                )
                said.append(f"{'Kept' if applied else 'Will keep'} your edits on {_plural(len(entries), kind)}: {each}.")
        for kind, entries in (
            ("risers", added_kept), *((over, [entry for entry in over_added if entry["kind"] == over]) for over in OVERHEAD),
        ):
            if entries:
                names = ", ".join(entry["name"] for entry in entries)
                said.append(
                    f"{_plural(len(entries), kind)} you added {was if len(entries) == 1 else were} kept as "
                    f"{'it is' if len(entries) == 1 else 'they are'}: {names}."
                )
        for kind, entries in (("risers", replaced), *((over, over_replaced) for over in OVERHEAD)):
            for entry in entries:
                if entry.get("kind", "risers") == kind:
                    said.append(
                        f"{entry['name']}, which you added, {was} replaced by the scan's {entry['by']}: "
                        f"the scan has {'a' if kind == 'risers' else 'an'} {KINDS[kind]} there now."
                    )
        for entry in warnings:
            said.append(f"Check {entry['name']}: it is {entry['reason']} of the room as this scan reads it.")
        lost = []
        for entry in self.lost:
            if "by_index" in entry:
                # What the item of the new room is called as it will be stored.
                entry = {**entry, "by": called(entry["by_index"], entry["kind"])}
            lost.append({**entry, "message": _lost_words(entry, applied)})
        said.extend(entry["message"] for entry in lost)

        # One thing at a time, in the order the sentences above say them.
        items: List[Dict[str, str]] = []
        for kind in KINDS:
            for entry in self.left_out:
                if (entry["kind"] if entry["kind"] in OVERHEAD else "risers") == kind:
                    items.append({"kind": ITEM_WORDS[kind], "name": entry["name"], "outcome": LEFT_OUT})
        for outcome, areas, overhead in (
            (KEPT, kept, over_kept), (ADDED_KEPT, added_kept, over_added), (REPLACED, replaced, over_replaced),
        ):
            for kind in KINDS:
                for entry in areas if kind == "risers" else overhead:
                    if entry.get("kind", "risers") == kind:
                        items.append({"kind": ITEM_WORDS[kind], "name": entry["name"], "outcome": outcome})
        # Then what was lost in one of the three ways slice 36 says, in the order the warnings say them.
        items.extend(
            {"kind": ITEM_WORDS[entry["kind"]], "name": entry["name"], "outcome": LOST}
            for entry in self.lost if _listed_as_lost(entry)
        )
        carry_over = [
            {
                **{key: value for key, value in entry.items() if key != "lost"},
                "new_name": called(entry["new_index"], entry["kind"]),
                # The checks are said before what was lost.
                "warning": len(warnings) + entry["lost"],
            }
            for entry in self.carry
        ]

        answer: Dict[str, Any] = {
            "areas": len(kept),
            "kept": kept,
            "added_kept": added_kept,
            "added_replaced": replaced,
            "message": " ".join(said),
        }
        for key, entries in (
            ("overhead_kept", over_kept), ("overhead_added_kept", over_added),
            ("overhead_added_replaced", over_replaced), ("deleted_left_out", list(self.left_out)),
            ("warnings", warnings + lost), ("items", items), ("carry_over", carry_over),
        ):
            if entries:
                answer[key] = entries
        return answer


def _lost_words(entry: Dict[str, Any], applied: bool) -> str:
    """The sentence for one thing that was lost: what the scan read, and what went with it."""
    name, kind = entry["name"], entry["kind"]
    if entry["reason"] == LOST_RECORD:
        return (
            f"The scan did not see {name}; the record that keeps it deleted {'was' if applied else 'will be'} "
            "dropped, so it may come back on a later scan."
        )
    edits = entry["edits"]
    # A line's or ring's height is its trim; a raised area's is its height, and it has a base height too.
    words = EDIT_WORDS if kind == "risers" else {"name": "name", "height": "trim"}
    said = [words[key] for key in edits]
    what = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"
    if entry["reason"] == LOST_GONE:
        go = "went" if applied else ("goes" if len(edits) == 1 else "go")
        return f"The scan no longer reads {name}; its {what} {go} with it."
    kept = f"{'was' if len(edits) == 1 else 'were'} not kept" if applied else "will not be kept"
    gone = f"its {what} {kept}"
    if entry["reason"] == LOST_OTHER:
        return (
            f"{name} and {entry['kept']} both stand where the scan reads {entry['read']}: {entry['kept']} "
            f"{'has' if applied else 'will have'} it, so the {what} of {name} {kept}."
        )
    # A raised area of the reading is named: there may be several, and one is to be pointed at.
    read = entry["by"] if kind == "risers" else _READ_WORDS[kind]
    if entry["reason"] == LOST_HEIGHT:
        before = entry.get("scan_height")
        beside = "" if before is None or before == entry["trim"] else f" (the scan read it at {_metres(before)} m before)"
        return (
            f"The scan read {read} at {_metres(entry['read_height'])} m where {name} was, against its trim of "
            f"{_metres(entry['trim'])} m{beside}: more than {_metres(HANG_MATCH_M)} m from where the scan read it "
            f"before, so {gone}."
        )
    return (
        f"The scan read {read} {_metres(round(entry['offset'], 2))} m from where {name} was, sharing "
        f"{round(entry['overlap'] * 100)}% of the plan with it where half is needed, so {gone}."
    )


def _listed_as_lost(entry: Dict[str, Any]) -> bool:
    """Whether something lost is one of the three slice 36 lists in `items`: the rest are warnings only, as they were."""
    return entry["reason"] in (LOST_GONE, LOST_OTHER) or (entry["reason"] == LOST_BESIDE and entry["kind"] == "risers")


def _near_miss(
    kind: str, was: Dict[str, Any], new: List[Any], taken: Any,
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """(why a stored item that matched nothing was not matched, the place of the one it was not). Point 7.

    (None, None) where the reading does not say. A raised area has no height
    to be passed over for (its height is never compared), and its kind is not
    looked at: only one that shares some floor and less than half.

    Asked only of the reading's items that no stored item is (`taken` holds
    the places of the rest). One that shares half the plan and was passed over
    for the height it hangs at comes before one that shares less than half;
    of several, the greatest overlap, the earlier of two equal. None where the
    reading has nothing there: the scan no longer reads it at all.
    """
    read_at = scan_read_height(was) if kind in OVERHEAD else None
    found: Dict[str, Tuple[int, float]] = {}
    for index, item in enumerate(new):
        if index in taken or not isinstance(item, dict):
            continue
        overlap = footprint_overlap(was, item)
        far = read_at is not None and _number(item.get("height")) and abs(item["height"] - read_at) > HANG_MATCH_M
        if far and overlap >= MATCH_IOU:
            reason = LOST_HEIGHT
        elif not far and TOUCHING < overlap < MATCH_IOU:
            reason = LOST_BESIDE
        else:
            continue
        if reason not in found or overlap > found[reason][1]:
            found[reason] = (index, overlap)
    if LOST_HEIGHT in found:
        index = found[LOST_HEIGHT][0]
        read = new[index]
        return {
            "reason": LOST_HEIGHT, "read_height": read["height"],
            "trim": was["height"] if _number(was.get("height")) else read_at, "scan_height": read_at,
        }, index
    if LOST_BESIDE in found:
        index, overlap = found[LOST_BESIDE]
        here, there = item_centre(kind, was), item_centre(kind, new[index])
        offset = math.hypot(here[0] - there[0], here[1] - there[1]) if here and there else 0.0
        return {"reason": LOST_BESIDE, "offset": round(offset, 3), "overlap": round(overlap, 3)}, index
    return None, None


def _winners(matches: List[Tuple[Optional[int], float]]) -> Dict[int, Tuple[int, float]]:
    """For each new item picked, the stored one that has it: the greater overlap, and of two equal the earlier."""
    winner: Dict[int, Tuple[int, float]] = {}
    for place, (match, overlap) in enumerate(matches):
        if match is not None and (match not in winner or overlap > winner[match][1]):
            winner[match] = (place, overlap)
    return winner


def _leave_out(
    old_shell: Any, new_shell: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(the new room without the items a person deleted, what was left out, the records dropped). Point 0.

    The same object, and nothing left out, when no record matches. A record
    that matches nothing is dropped and named (point 7): {"kind", "name",
    "reason"}, `kind` the list it was deleted from.
    """
    records = old_shell.get(DELETED_KEY) if isinstance(old_shell, dict) else None
    if not isinstance(records, list) or not isinstance(new_shell, dict):
        return new_shell, [], []
    # (the record's place, the list, the place in that list of the new reading, the overlap)
    taken: List[Tuple[int, str, int, float]] = []
    for kind in KINDS:
        new = new_shell.get(kind)
        places = [place for place, record in enumerate(records) if _record_list(record) == kind]
        if not places or not isinstance(new, list):
            continue
        winner = _winners([best_match(records[place], new) for place in places])
        taken.extend((places[at], kind, index, overlap) for index, (at, overlap) in winner.items())
    has = {place for place, _, _, _ in taken}
    dropped: List[Dict[str, Any]] = []
    for place, record in enumerate(records):
        if place in has or not isinstance(record, dict):
            continue
        kind, name = _record_list(record), record.get("name")
        dropped.append({
            "kind": kind, "name": name if isinstance(name, str) and name.strip() else f"a deleted {KINDS[kind]}",
            "reason": LOST_RECORD,
        })
    if not taken:
        return new_shell, [], dropped
    shell = copy.deepcopy(new_shell)
    for kind in KINDS:
        out = {index for _, where, index, _ in taken if where == kind}
        if not out:
            continue
        shell[kind] = [item for index, item in enumerate(shell[kind]) if index not in out]
        if kind in OVERHEAD:
            # As Edit Room's delete: out of its list, then out of the band that counted it.
            for index in sorted(out):
                _uncount(shell, kind, new_shell[kind][index])
    carried: List[Dict[str, Any]] = []
    left_out: List[Dict[str, Any]] = []
    for place, kind, index, overlap in sorted(taken):
        record, read = records[place], new_shell[kind][index]
        # The record goes on, standing where this reading has it: the next reading is matched against that.
        again = {key: value for key, value in record.items() if key not in _RECORD_READ[kind]}
        again.update({key: read[key] for key in _RECORD_READ[kind] if key in read})
        carried.append(again)
        name = record.get("name")
        left_out.append({
            "name": name if isinstance(name, str) and name.strip() else item_name(kind, read),
            "kind": kind if kind in OVERHEAD else record.get("kind"), "overlap": round(overlap, 3),
        })
    shell[DELETED_KEY] = carried
    return shell, left_out, dropped


def _plan(
    kind: str, old: List[Any], new: List[Any],
) -> Tuple[
    List[Tuple[int, int, Tuple[str, ...], float]], List[int], List[Dict[str, Any]],
    List[Tuple[Dict[str, Any], Optional[int], Dict[str, Any]]],
]:
    """What becomes of one list's stored items: (kept, added and kept, added and replaced, lost). Points 1 to 5, 7.

    `kept`: (place in the old list, place in the new, the fields, the overlap).
    `added and kept`: places in the old list. `lost`: what went nowhere and
    is said (point 7), each (the entry, the place in the new list of the item
    it points at or None, the stored item). Nothing is written here.
    """
    # Every stored item with something to keep.
    wanted: List[Tuple[int, Tuple[str, ...]]] = []
    for place, item in enumerate(old):
        edits = hand_edits(item, kind)
        if edits or (isinstance(item, dict) and item.get("added_by_hand") is True):
            wanted.append((place, edits))
    if not wanted:
        return [], [], [], []

    # One stored item for each new one: the greater overlap, and of two equal the earlier. Every
    # stored item is asked, not only those with something to keep: the scan's own riser, read again,
    # is that riser, and one a person added on top of it does not take its place.
    matches = [best_match(item, new) for item in old]
    winner = _winners(matches)

    kept: List[Tuple[int, int, Tuple[str, ...], float]] = []
    added_kept: List[int] = []
    added_replaced: List[Dict[str, Any]] = []
    lost: List[Tuple[Dict[str, Any], Optional[int], Dict[str, Any]]] = []
    for place, edits in wanted:
        was = old[place]
        match, overlap = matches[place]
        if match is not None and winner[match][0] == place:
            if edits:
                kept.append((place, match, edits, overlap))
        elif was.get("added_by_hand") is True:
            # Against the reading only, not the ones kept before it: two a person added may overlap, as they did.
            shared = [footprint_overlap(was, other) for other in new]
            most = max(shared, default=0.0)
            if most > SHARED[kind]:
                added_replaced.append({"name": item_name(kind, was), "by_index": shared.index(most)})
            else:
                added_kept.append(place)
        elif not edits:
            continue
        elif match is not None:
            # Another stored item has the one it picked (point 2). What a person set on this one goes nowhere.
            lost.append(({
                "kind": kind, "name": item_name(kind, was), "edits": list(edits), "reason": LOST_OTHER,
                "kept": item_name(kind, old[winner[match][0]]), "read": item_name(kind, new[match]),
                "by_index": match,
            }, match, was))
        else:
            # Its name or trim goes nowhere. Said with the one the reading has there that is not it,
            # and for a line or ring also where the reading has none.
            why, index = _near_miss(kind, was, new, winner)
            fact = {"kind": kind, "name": item_name(kind, was), "edits": list(edits)}
            if why is not None:
                # A raised area's warning names the new area: its place is part of what is said.
                lost.append(({**fact, **why, **({"by_index": index} if kind == "risers" else {})}, index, was))
            elif kind in OVERHEAD:
                lost.append(({**fact, "reason": LOST_GONE}, None, was))
    return kept, added_kept, added_replaced, lost


def _checks(
    shell: Dict[str, Any], kept: Dict[str, List[Dict[str, Any]]], added: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """What was kept that the new room's ceiling or walls do not hold. Point 6 at the top."""
    outside = {(entry["kind"], entry["index"]): entry["reason"] for entry in outside_report(shell)["items"]}
    warnings: List[Dict[str, Any]] = []
    for kind in KINDS:
        for entry in kept.get(kind, []):
            reason = outside.get((kind, entry["index"]), "")
            # Its place is the scan's: only a height that was kept can be what puts it above the ceiling.
            if ABOVE in reason and ("height" in entry["edits"] or "base_height" in entry["edits"]):
                warnings.append({"kind": kind, "index": entry["index"], "reason": ABOVE})
        for entry in added.get(kind, []):
            reason = outside.get((kind, entry["index"]))
            if reason:
                warnings.append({"kind": kind, "index": entry["index"], "reason": reason})
    return warnings


def keep_hand_edits(old_shell: Optional[Dict[str, Any]], new_shell: Dict[str, Any]) -> KeptEdits:
    """The new room with what a person set in the old one, and what became of each thing.

    See the rule at the top of this file. Neither shell is changed.
    """
    if not isinstance(old_shell, dict) or not isinstance(new_shell, dict):
        return KeptEdits(shell=new_shell)

    # What a person deleted goes first: the rest is asked of the room without it.
    read, left_out, dropped = _leave_out(old_shell, new_shell)

    plans: Dict[str, Any] = {}
    for kind in KINDS:
        old, new = old_shell.get(kind), read.get(kind)
        if kind in OVERHEAD and isinstance(old, list) and new is None:
            new = []    # a reading with no list of rings has no rings
        if isinstance(old, list) and isinstance(new, list):
            plans[kind] = (old, new, *_plan(kind, old, new))

    replaced: Dict[str, List[Dict[str, Any]]] = {kind: plan[4] for kind, plan in plans.items()}
    risers_replaced = replaced.get("risers", [])
    overhead_replaced = [{"kind": kind, **entry} for kind in OVERHEAD for entry in replaced.get(kind, [])]
    # What went nowhere: names and trims the reading had one near but not at, then the records dropped.
    lost: List[Dict[str, Any]] = []
    carry: List[Dict[str, Any]] = []
    for kind in KINDS:
        for entry, index, was in (plans[kind][5] if kind in plans else []):
            if index is not None:
                # The place is in the reading without what was left out, which is the room's own: what is
                # kept is written where it is, and what is added by hand goes after it.
                edits = entry["edits"]
                carry.append({
                    "kind": kind, "old_name": entry["name"],
                    "old_trim_or_height": _mm(was["height"]) if "height" in edits else None,
                    **({"old_base_height": _mm(base_of(was)) if "base_height" in edits else None}
                       if kind == "risers" else {}),
                    "edits": list(edits), "new_index": index, "reason": entry["reason"], "lost": len(lost),
                })
            lost.append(entry)
    lost += dropped
    if not any(plan[2] or plan[3] for plan in plans.values()):
        # Nothing to write: the room is the reading as it came (but for what was left out of it).
        return KeptEdits(
            shell=read, added_replaced=risers_replaced, overhead_added_replaced=overhead_replaced, left_out=left_out,
            lost=lost, carry=carry,
        )

    shell = copy.deepcopy(read)
    kept: Dict[str, List[Dict[str, Any]]] = {}
    added: Dict[str, List[Dict[str, Any]]] = {}
    for kind, (old, _, keeps, appends, _, _) in plans.items():
        if kind in OVERHEAD and (keeps or appends) and not isinstance(shell.get(kind), list):
            shell[kind] = []
        items = shell.get(kind)
        for place, match, edits, overlap in keeps:
            was, item = old[place], items[match]
            if "name" in edits:
                item["name"] = was["name"]
                _note(item, NAME_BY_HAND)
            if "height" in edits:
                before = copy.deepcopy(item)
                item["height"] = _mm(was["height"])
                _mark(item, HEIGHT_BY_HAND)
                if kind in OVERHEAD:
                    # As Edit Room hangs one higher or lower: as deep as the scan reads it, and counted
                    # in the hanging-height band it is now in.
                    top, had = before.get("top"), before.get("height")
                    if _number(had):
                        # Where this reading has it, beside the trim: the reading after matches by that.
                        item[SCAN_HEIGHT_KEY] = had
                    if _number(top) and _number(had):
                        item["top"] = _mm(item["height"] + (top - had))
                    _uncount(shell, kind, before)
                    _count(shell, kind, item)
            if "base_height" in edits:
                item["base_height"] = _mm(base_of(was))
                _mark(item, BASE_BY_HAND)
            if "height" in edits or "base_height" in edits:
                # As Edit Room leaves one whose height was set: its size is no longer all the scan's.
                _mark(item, RESIZED_BY_HAND)
            kept.setdefault(kind, []).append({"index": match, "edits": list(edits), "overlap": round(overlap, 3)})
        for place in appends:
            item = copy.deepcopy(old[place])
            items.append(item)
            if kind in OVERHEAD:
                _count(shell, kind, item)
            added.setdefault(kind, []).append({"index": len(items) - 1})

    # A marked booth kept as it is still carries its mark: keep_dj_booth, asked next, finds it on itself.
    return KeptEdits(
        shell=shell,
        kept=kept.get("risers", []),
        added_kept=added.get("risers", []),
        added_replaced=risers_replaced,
        overhead_kept=[{"kind": kind, **entry} for kind in OVERHEAD for entry in kept.get(kind, [])],
        overhead_added_kept=[{"kind": kind, **entry} for kind in OVERHEAD for entry in added.get(kind, [])],
        overhead_added_replaced=overhead_replaced,
        left_out=left_out,
        warnings=_checks(shell, kept, added),
        lost=lost,
        carry=carry,
    )
