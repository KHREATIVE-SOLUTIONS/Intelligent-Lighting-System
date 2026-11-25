"""
Keeping what a person set on a raised area when a room is scanned again
=======================================================================

A scan applied again writes a whole new room. A person who had corrected the
old one (typed a name, set a height, put in a riser the scan never saw) lost
all of it. This carries those corrections onto the new reading
(docs/ROOM_SCAN.md, slice 32). Raised areas only.

Which stored raised area is which new one is `keep_mark.best_match`, the rule
the DJ booth mark is kept by, asked here for every stored raised area with
something to keep: the same kind unless the kind was set by hand, footprints
overlapping by an intersection over union of at least 0.5, the greatest
overlap, the earlier of two equal. There is no second rule.

What counts as set by hand is read from what is stored (`hand_edits`):

- a **name**: the `basis` says "Name set by hand." (edit.py writes it when a
  rename changes a raised area's name), or the area was added by hand under a
  name that is not just what its kind is called;
- a **height**: the `basis` says "Height set by hand.", or it was added by hand;
- a **base height**: the `basis` says "Base height set by hand.", or it was
  added by hand.

"Resized by hand." alone says none of them: it is written for a width, a
depth and a heading too. A room edited before these marks were written keeps
nothing.

What is done:

1. A stored raised area with any of those that matches a new one gives it
   the name, the height and the base height that were set by hand, and the
   new one's `basis` says so again, so the reading after this one keeps them
   too. Where it stands, how wide and deep it is and its heading are the
   scan's: the scan measures those better than a person drags them. Its kind
   is the scan's too (only the marked DJ booth keeps a kind: keep_mark.py).
2. Two stored areas that pick the same new one: the greater overlap has it,
   the earlier of two equal. The other is treated as one that matched nothing.
3. A raised area **added by hand** that matches nothing and shares no floor
   with any raised area of the new reading is kept as it is, at the end of
   the list, so every place the scan gave is what it was.
4. One added by hand that matches nothing but does share floor with a new
   raised area is not kept: the scan has something there now, and two things
   in one place is worse than one. It is reported, with what replaced it.
5. Anything else that matches nothing is not carried and not reported: a
   name has nowhere to go.

Call this before `keep_dj_booth`, and give that the room this returns: a
marked booth added by hand and kept as it is then keeps its mark (it matches
itself), and the mark's sentence names the raised area by its kept name.

Pure: the shells given are never changed, and with nothing to carry the new
one is returned as it is, the same object.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.room_scan.edit import (
    BASE_BY_HAND, HEIGHT_BY_HAND, NAME_BY_HAND, RESIZED_BY_HAND, RISER_KINDS, _mark, _mm, _note,
    _number, base_of, item_name,
)
from app.services.room_scan.keep_mark import best_match, footprint_overlap

# Less shared floor than this (as intersection over union) is two raised areas that touch, not overlap.
TOUCHING = 1e-6

# What each kept field is called in a sentence, in the order they are said.
EDIT_WORDS: Dict[str, str] = {"name": "name", "height": "height", "base_height": "base height"}


def hand_edits(item: Any) -> Tuple[str, ...]:
    """Which of a stored raised area's name, height and base height a person set: keys of EDIT_WORDS."""
    if not isinstance(item, dict):
        return ()
    basis = str(item.get("basis") or "")
    added = item.get("added_by_hand") is True
    name = item.get("name")
    found = []
    if isinstance(name, str) and name.strip() and (
        NAME_BY_HAND in basis or (added and name != RISER_KINDS.get(str(item.get("kind"))))
    ):
        found.append("name")
    if _number(item.get("height")) and (HEIGHT_BY_HAND in basis or added):
        found.append("height")
    if BASE_BY_HAND in basis or added:
        found.append("base_height")
    return tuple(found)


def _plural(count: int) -> str:
    return f"{count} raised area{'' if count == 1 else 's'}"


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

    @property
    def any(self) -> bool:
        return bool(self.kept or self.added_kept or self.added_replaced)

    def report(self, shell: Optional[Dict[str, Any]] = None, applied: bool = False) -> Optional[Dict[str, Any]]:
        """What an answer says of it, or None when nothing was carried and nothing replaced.

        `shell` is the room as it will be stored (the DJ booth mark can still
        rename a raised area after this); names are read from it. `applied`
        words the sentence as done, not as what Apply will do.
        """
        if not self.any:
            return None
        risers = (shell or self.shell)["risers"]

        def called(index: int) -> str:
            return item_name("risers", risers[index])

        kept = [{**entry, "name": called(entry["index"])} for entry in self.kept]
        added_kept = [{**entry, "name": called(entry["index"])} for entry in self.added_kept]
        replaced = [{**entry, "by": called(entry["by_index"])} for entry in self.added_replaced]
        was, were = ("was", "were") if applied else ("will be", "will be")
        said = []
        if kept:
            each = ", ".join(
                f"{entry['name']} ({', '.join(EDIT_WORDS[key] for key in entry['edits'])})" for entry in kept
            )
            said.append(f"{'Kept' if applied else 'Will keep'} your edits on {_plural(len(kept))}: {each}.")
        if added_kept:
            names = ", ".join(entry["name"] for entry in added_kept)
            said.append(
                f"{_plural(len(added_kept))} you added {was if len(added_kept) == 1 else were} kept as "
                f"{'it is' if len(added_kept) == 1 else 'they are'}: {names}."
            )
        for entry in replaced:
            said.append(
                f"{entry['name']}, which you added, {was} replaced by the scan's {entry['by']}: "
                "the scan has a raised area there now."
            )
        return {
            "areas": len(kept),
            "kept": kept,
            "added_kept": added_kept,
            "added_replaced": replaced,
            "message": " ".join(said),
        }


def keep_hand_edits(old_shell: Optional[Dict[str, Any]], new_shell: Dict[str, Any]) -> KeptEdits:
    """The new room with what a person set on the old room's raised areas, and what became of each.

    See the rule at the top of this file. Neither shell is changed.
    """
    old = old_shell.get("risers") if isinstance(old_shell, dict) else None
    new = new_shell.get("risers") if isinstance(new_shell, dict) else None
    if not isinstance(old, list) or not isinstance(new, list):
        return KeptEdits(shell=new_shell)

    # Every stored raised area with something to keep, and the new one it is (or None).
    wanted: List[Tuple[int, Tuple[str, ...], Optional[int], float]] = []
    for place, item in enumerate(old):
        edits = hand_edits(item)
        if edits or (isinstance(item, dict) and item.get("added_by_hand") is True):
            match, overlap = best_match(item, new)
            wanted.append((place, edits, match, overlap))
    if not wanted:
        return KeptEdits(shell=new_shell)

    # One stored area for each new one: the greater overlap, and of two equal the earlier.
    winner: Dict[int, Tuple[int, float]] = {}
    for place, _, match, overlap in wanted:
        if match is not None and (match not in winner or overlap > winner[match][1]):
            winner[match] = (place, overlap)

    shell = copy.deepcopy(new_shell)
    risers = shell["risers"]
    kept: List[Dict[str, Any]] = []
    added_kept: List[Dict[str, Any]] = []
    added_replaced: List[Dict[str, Any]] = []
    for place, edits, match, overlap in wanted:
        was = old[place]
        if match is not None and winner[match][0] == place:
            if not edits:
                continue
            item = risers[match]
            if "name" in edits:
                item["name"] = was["name"]
                _note(item, NAME_BY_HAND)
            if "height" in edits:
                item["height"] = _mm(was["height"])
                _mark(item, HEIGHT_BY_HAND)
            if "base_height" in edits:
                item["base_height"] = _mm(base_of(was))
                _mark(item, BASE_BY_HAND)
            if "height" in edits or "base_height" in edits:
                # As Edit Room leaves one whose height was set: its size is no longer all the scan's.
                _mark(item, RESIZED_BY_HAND)
            kept.append({"index": match, "edits": list(edits), "overlap": round(overlap, 3)})
        elif was.get("added_by_hand") is True:
            # Against the reading only, not the ones kept before it: two a person added may overlap, as they did.
            shared = [footprint_overlap(was, other) for other in new]
            most = max(shared, default=0.0)
            if most > TOUCHING:
                added_replaced.append({"name": item_name("risers", was), "by_index": shared.index(most)})
            else:
                risers.append(copy.deepcopy(was))
                added_kept.append({"index": len(risers) - 1})

    if not (kept or added_kept or added_replaced):
        return KeptEdits(shell=new_shell)
    if not (kept or added_kept):
        # Only something replaced: the room is the reading as it came.
        return KeptEdits(shell=new_shell, added_replaced=added_replaced)
    # A marked booth kept as it is still carries its mark: keep_dj_booth, asked next, finds it on itself.
    return KeptEdits(shell=shell, kept=kept, added_kept=added_kept, added_replaced=added_replaced)
