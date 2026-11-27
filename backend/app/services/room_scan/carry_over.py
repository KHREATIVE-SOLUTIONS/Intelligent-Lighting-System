"""
Putting a lost name and trim back onto the item a scan read in its place (docs/ROOM_SCAN.md, slice 36)
=====================================================================================================

A scan applied again sometimes cannot keep what a person set: the truss was
read more than a metre from where it hung, or to one side, or two stored items
picked the same new one. Slice 36 says each of those in `hand_edits.warnings`
and gives one entry of `hand_edits.carry_over` for each that has an item of the
new room behind it (keep_edits.py). `carry_over` here takes one such entry as
it is and puts the old name, and the old trim (a line's or ring's hanging
height) or a raised area's height and base height, onto that item.

- **Only the fields in `edits`.** An entry for a trim alone names the item what
  the scan called it ("Overhead ring 1"): that name is not a person's, and is
  not written or marked.
- **Marked as set by hand** with the markers Edit Room writes (edit.py), so the
  scan applied after this keeps them (keep_edits.py, slice 32 rule 1). Edit
  Room writes a marker only for a value that changes; here it is written even
  where the scan happened to read the same value, as keep_edits does, because
  without it the next reading drops it again.
- **A trim is set as Edit Room sets one**: the top goes with it, the
  hanging-height bands are counted again, and the height the scan read is kept
  as `scan_height` (the next reading is matched by that, slice 34).
- **Stale entries are refused (409)**: the item at `new_index` must still be
  there and still be called `new_name`, the name the answer gave it. The room
  may have been edited, or another entry carried onto the same item, since.

Pure: the shell given is not changed. Fixtures are not looked at: the route
moves the ones hung on a truss whose trim changed, by Edit Room's own rules.
"""

from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.room_scan.edit import (
    BASE_BY_HAND, HEIGHT_BY_HAND, KINDS, NAME_BY_HAND, RESIZED_BY_HAND, SCAN_HEIGHT_KEY, ShellEditError,
    _mark, _note, _number, edit_item, item_name,
)

# Which fields can be carried onto each list's items.
CARRIED: Dict[str, Tuple[str, ...]] = {
    "risers": ("name", "height", "base_height"),
    "truss_lines": ("name", "height"),
    "truss_rings": ("name", "height"),
}
# What each is called in the label of the room's Undo step.
_WORDS: Dict[str, Dict[str, str]] = {
    "risers": {"name": "name", "height": "height", "base_height": "base height"},
    "truss_lines": {"name": "name", "height": "trim"},
    "truss_rings": {"name": "name", "height": "trim"},
}


def _stale(kind: str, index: Any, name: Any) -> ShellEditError:
    return ShellEditError(
        409,
        f"The room has changed since the scan was applied: {KINDS[kind]} {index} is not "
        f"{name if isinstance(name, str) and name else 'what the scan answer said'} any more. "
        "Nothing was changed: rename or trim it in Edit Room.",
    )


def refuse_shared_targets(entries: Any) -> List[Dict[str, Any]]:
    """The entries of a "Keep all" (slice 37), refused (422) where they are not a list of entries or two share an item.

    Two entries for the same new item would each put their name on it, and
    the second would quietly take the place of the first: the operator must
    choose, one at a time. Nothing else of an entry is checked here:
    `carry_over` does that, entry by entry.
    """
    if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
        raise ShellEditError(422, "`entries` must be a list of the carry_over entries to keep, at least one.")
    seen: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for entry in entries:
        target = (entry.get("kind"), entry.get("new_index"))
        if target in seen and isinstance(target[0], str) and target[0] in KINDS:
            first = seen[target]
            raise ShellEditError(
                422,
                f"{first.get('old_name')} and {entry.get('old_name')} would both be put on "
                f"{entry.get('new_name') or f'{KINDS[target[0]]} {target[1]}'}: keep one of them on it, "
                "one at a time. Nothing was changed.",
            )
        seen[target] = entry
    return entries


# What goes with one carried item (the route's Edit Room rules): (room before, kind, index, room after, item)
# -> (room after with what it carried, fixture moves, raised areas carried).
CarryWith = Callable[
    [Dict[str, Any], str, int, Dict[str, Any], Dict[str, Any]],
    Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]],
]


def _nothing_with(before, kind, index, shell, item):
    return shell, [], []


def carry_all(
    shell: Optional[Dict[str, Any]], entries: Any, carry_with: CarryWith = _nothing_with,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """"Keep all" (slice 37): (the room with every entry carried, per entry what was done, moves, areas, labels).

    All or none: the entries are carried one after another, each onto the
    room the ones before it left, and the first refused (ShellEditError: 409
    stale, 422 not an entry) refuses the lot; the shell given is never
    changed, so nothing is written. Two entries for one item are a 422 before
    any is tried (`refuse_shared_targets`), and so is a fixture two of them
    would each move: the moves are worked out from where the fixtures stand
    now and made together, so the second would quietly win. `labels` has
    what each entry that changed something did, for the label of the one Undo
    step. Each of the per-entry answers is {warning_id, kind, index, old_name,
    new_name, item, changed, fixtures_moved, done}.
    """
    entries = refuse_shared_targets(entries)
    carried: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []
    areas: List[Dict[str, Any]] = []
    labels: List[str] = []
    for entry in entries:
        edited, item, done = carry_over(shell, entry)
        kind, index = entry["kind"], entry["new_index"]
        theirs: List[Dict[str, Any]] = []
        if done is not None:
            edited, theirs, stacked = carry_with(shell, kind, index, edited, item)
            shell = edited
            moves, areas = moves + theirs, areas + stacked
            labels.append(done)
        carried.append({
            "warning_id": entry.get("warning_id"), "kind": kind, "index": index,
            "old_name": entry.get("old_name"), "new_name": entry.get("new_name"), "item": item,
            "changed": done is not None, "fixtures_moved": len(theirs), "done": done,
        })
    twice = sorted(key for key, count in Counter(move.get("rig_fixture_id") for move in moves).items() if count > 1)
    if twice:
        raise ShellEditError(
            422,
            f"{len(twice)} fixture{'' if len(twice) == 1 else 's'} would be moved by more than one of these: "
            "keep them one at a time. Nothing was changed.",
        )
    return shell, carried, moves, areas, labels


def carry_over(
    shell: Optional[Dict[str, Any]], entry: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    """(the shell with the old name and trim on the item, that item, what was done or None).

    `entry` is one of `hand_edits.carry_over`: its `kind`, `new_index`,
    `new_name`, `edits`, `old_name`, `old_trim_or_height` and, for a raised
    area, `old_base_height` are read; anything else in it is passed over.
    None where the item already has all of it, set by hand: nothing to do.
    Raises ShellEditError: 404 with no room, 422 for an entry that is not
    one, 409 for one the room no longer fits.
    """
    if not isinstance(shell, dict):
        raise ShellEditError(404, "This rig has no room stored. Apply a room scan first.")
    kind = entry.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ShellEditError(422, f"`kind` must be one of {', '.join(KINDS)}.")
    index = entry.get("new_index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise ShellEditError(422, "`new_index` must be a whole number: the place of the item in its list.")
    edits = entry.get("edits")
    if not isinstance(edits, list) or not edits or any(key not in CARRIED[kind] for key in edits):
        raise ShellEditError(
            422, f"`edits` must list what to carry onto a {KINDS[kind]}: some of {', '.join(CARRIED[kind])}.",
        )
    fields: Dict[str, Any] = {}
    if "name" in edits:
        name = entry.get("old_name")
        if not isinstance(name, str) or not name.strip():
            raise ShellEditError(422, "`old_name` must be the name to carry over.")
        fields["name"] = name
    for key, given in (("height", "old_trim_or_height"), ("base_height", "old_base_height")):
        if key in edits:
            value = entry.get(given)
            if not _number(value):
                raise ShellEditError(422, f"`{given}` must be a number of metres.")
            fields[key] = float(value)

    items = shell.get(kind)
    if not isinstance(items, list) or not 0 <= index < len(items) or not isinstance(items[index], dict):
        raise _stale(kind, index, entry.get("new_name"))
    if item_name(kind, items[index]) != entry.get("new_name"):
        raise _stale(kind, index, entry.get("new_name"))

    before = items[index]
    # Edit Room's own edit, on a copy: the limits (the ceiling, the floor), the top and the bands, `scan_height`.
    edited, item = edit_item(shell, kind, index, **fields)
    # And the markers, written whether or not the value changed: the next scan keeps only what is marked.
    if "name" in fields:
        _note(item, NAME_BY_HAND)
    if "height" in fields:
        if kind != "risers" and SCAN_HEIGHT_KEY not in item and _number(before.get("height")):
            # The trim is what the scan read: that reading is what the next one is matched by.
            item[SCAN_HEIGHT_KEY] = before["height"]
        _mark(item, HEIGHT_BY_HAND)
    if "base_height" in fields:
        _mark(item, BASE_BY_HAND)
    if "height" in fields or "base_height" in fields:
        _mark(item, RESIZED_BY_HAND)
    if item == before:
        return shell, before, None
    what = [_WORDS[kind][key] for key in edits]
    said = what[0] if len(what) == 1 else f"{', '.join(what[:-1])} and {what[-1]}"
    return edited, item, f"{item_name(kind, before)} given the {said} of {entry.get('old_name')}"
