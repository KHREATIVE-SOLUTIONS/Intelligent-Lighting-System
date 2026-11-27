"""
What a scan applied again lost that can still be put back, kept with the stored room (docs/ROOM_SCAN.md, slice 37)
==================================================================================================================

Slice 36 gave each loss with an item of the new room behind it as an entry of
`hand_edits.carry_over`, in the answer to the apply only: closed, the dialog
forgot them. Slice 37 keeps the entries still open in the stored room itself,
as `room_shell["pending_carry_over"]`, so the dialog opened again shows the
same "Keep Front truss on this one" buttons.

- **In the room, not beside it.** Every step of the room's Undo keeps the room
  as it was, so an Undo of a carry-over (or of the edit that dropped an entry)
  brings the entry back with it, with nothing else to keep in step. A new
  reading is a new room: the list is the new apply's, or none. Taking the room
  off takes the list with it. No new column.
- **Each entry as the answer gave it**, with the `message` of its warning, so
  the dialog has the sentence to show beside the button when the answer is
  gone. The key is left out where nothing is open, so a room with nothing to
  put back is stored as it was before slice 37.
- **Dropped when it would be stale**: carried over; its item renamed,
  re-trimmed, given another height or base height, or deleted; an item before
  it in its list deleted shifts it up one place rather than leaving it to
  point at its neighbour. Moving an item keeps it: a name and trim do not
  care where the truss hangs.

Pure: the shells given are never changed.
"""

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

PENDING_KEY = "pending_carry_over"
# What an entry's item must still have, as it had when the entry was made, for the entry to stand.
_WATCHED = ("name", "height", "base_height")


def pending(shell: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The entries still open on a stored room: [] for none, no room, or a list that is not one."""
    entries = shell.get(PENDING_KEY) if isinstance(shell, dict) else None
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def with_pending(shell: Dict[str, Any], entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The shell with these entries open, a new dict; the key left out where there are none."""
    stored = {key: value for key, value in shell.items() if key != PENDING_KEY}
    if entries:
        stored[PENDING_KEY] = [dict(entry) for entry in entries]
    return stored


def to_store(report: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The entries of an applied answer's `hand_edits` to keep with the room, each with its warning's `message`."""
    if not isinstance(report, dict):
        return []
    words = {
        warning.get("id"): warning.get("message")
        for warning in report.get("warnings") or [] if isinstance(warning, dict) and warning.get("id")
    }
    stored = []
    for entry in report.get("carry_over") or []:
        message = words.get(entry.get("warning_id"))
        stored.append({**entry, "message": message} if isinstance(message, str) else dict(entry))
    return stored


def _target(entry: Dict[str, Any]) -> Tuple[Any, Any]:
    return entry.get("kind"), entry.get("new_index")


def _item(shell: Optional[Dict[str, Any]], kind: Any, index: Any) -> Optional[Dict[str, Any]]:
    items = shell.get(kind) if isinstance(shell, dict) and isinstance(kind, str) else None
    if not isinstance(items, list) or isinstance(index, bool) or not isinstance(index, int):
        return None
    if not 0 <= index < len(items) or not isinstance(items[index], dict):
        return None
    return items[index]


def prune(before: Optional[Dict[str, Any]], after: Dict[str, Any]) -> Dict[str, Any]:
    """`after` without the entries whose item was renamed, re-trimmed, raised or taken away since `before`.

    For an edit that keeps every item in its place (a PATCH, a carry-over, the
    walls, an item added at the end). A delete moves the items after it: see
    `after_delete`.
    """
    entries = pending(after)
    if not entries:
        return after
    kept = []
    for entry in entries:
        was, now = _item(before, *_target(entry)), _item(after, *_target(entry))
        if was is None or now is None or any(was.get(key) != now.get(key) for key in _WATCHED):
            continue
        kept.append(entry)
    return after if len(kept) == len(entries) else with_pending(after, kept)


def after_delete(shell: Dict[str, Any], kind: str, index: int) -> Dict[str, Any]:
    """The shell an item was deleted from, without the entries for it and with those after it one place up."""
    entries = pending(shell)
    if not entries:
        return shell
    kept = []
    for entry in entries:
        their_kind, at = _target(entry)
        if their_kind == kind and isinstance(at, int) and not isinstance(at, bool):
            if at == index:
                continue
            if at > index:
                entry = {**entry, "new_index": at - 1}
        kept.append(entry)
    return with_pending(shell, kept)


def without_targets(shell: Dict[str, Any], targets: Iterable[Tuple[Any, Any]]) -> Dict[str, Any]:
    """The shell without the entries that point at these items (`(kind, index)`): they have been carried over.

    Every entry for the item goes, not only the one sent: the item has the
    name it was given now, and the others would be refused as stale.
    """
    gone: Set[Tuple[Any, Any]] = set(targets)
    entries = pending(shell)
    kept = [entry for entry in entries if _target(entry) not in gone]
    return shell if len(kept) == len(entries) else with_pending(shell, kept)
