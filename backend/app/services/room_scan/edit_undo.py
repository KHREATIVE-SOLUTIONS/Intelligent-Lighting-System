"""
Undoing an edit to a stored room
================================

Each edit made to a rig's stored room by hand (edit.py: a rename, a move, a
resize, a delete, an added item) leaves the room as it was behind it, so the
edit can be taken back. One undo takes back one edit, the latest first.

The record is kept on the rig beside the room (`rigs.room_shell_undo`), so it
is still there after the page is loaded again:

    { "steps": [ { "label": "Stage renamed", "at": "...", "shell": { ... } } ] }

oldest first. A step holds the whole room as it stood before its edit: a room
is a few kilobytes, and putting back the whole of it cannot go wrong the way
replaying an edit backwards can (a deleted item's place in its list, a
hanging-height band that was dropped with its last truss).

It is the caller's to clear when the room is no longer the one the steps were
taken from: a scan read again, or the room taken off the rig.

Pure: a record goes in and a new one comes out, and the one given is never
changed. The column is plain JSON, and a change made in place is never written.
Nothing here touches a fixture, the engine or a device.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# How many edits can be taken back. The oldest is forgotten past this.
STEPS_MAX = 20


def _steps(record: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The steps of a record that can be read: each with a room to go back to."""
    steps = (record or {}).get("steps") if isinstance(record, dict) else None
    return [
        step for step in (steps if isinstance(steps, list) else [])
        if isinstance(step, dict) and isinstance(step.get("shell"), dict)
    ]


def push_step(record: Optional[Dict[str, Any]], shell_before: Dict[str, Any], label: str) -> Dict[str, Any]:
    """The record after an edit: the room as it was before it, added as the latest step."""
    steps = _steps(record)
    steps.append({
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shell": shell_before,
    })
    return {"steps": steps[-STEPS_MAX:]}


def pop_step(record: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """(the record without its latest step, that step). (None, None) when there is nothing to undo.

    A record left with no steps is None: the column goes back to empty.
    """
    steps = _steps(record)
    if not steps:
        return None, None
    step = steps.pop()
    return ({"steps": steps} if steps else None), step


def undo_summary(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What a rig says about its record: how many edits can be undone, and what the next undo takes back.

    The rooms themselves are left out: they are for the undo, not the reader.
    """
    steps = _steps(record)
    label = steps[-1].get("label") if steps else None
    return {
        "available": len(steps),
        "label": label if isinstance(label, str) and label else None,
    }
