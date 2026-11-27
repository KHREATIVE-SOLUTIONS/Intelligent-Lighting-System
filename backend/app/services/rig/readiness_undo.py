"""
Undoing the last readiness fix
==============================

Make groups writes `group_name` and Re-address writes `universe` and
`dmx_address`, on the fixtures each one changes. The endpoint records, for
each fixture a fix changed, those columns before and after, as one record on
the rig (`rigs.readiness_undo`). The undo puts every one of them back in one
write, or none.

It puts back only what the fix did. If any fixture the fix changed has been
changed since (its group or address is no longer what the fix left) or taken
off the rig, nothing is put back and the undo is refused, naming them: a
partial undo of a re-address could leave a clash the fix had taken away.

    record = make_record(fix, entries)      # at a fix that changed something
    plan   = plan_undo(rows, record)        # read-only
    restore(plan)                           # writes the fixtures

Pure apart from `restore`, which sets attributes on the fixtures it is given.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

FIX_AUTO_GROUPS = "auto-groups"
FIX_READDRESS = "readdress"

# The columns each fix writes, and so the only ones its undo puts back.
FIELDS = {
    FIX_AUTO_GROUPS: ("group_name",),
    FIX_READDRESS: ("universe", "dmx_address"),
}
FIX_WORDS = {FIX_AUTO_GROUPS: "Make groups", FIX_READDRESS: "Re-address"}


def make_record(fix: str, entries: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The undo record for a fix. `entries`: id, name, before, after. None when nothing changed."""
    if not entries:
        return None
    return {
        "fix": fix,
        "at": datetime.now(timezone.utc).isoformat(),
        "entries": [
            {"id": int(e["id"]), "name": e.get("name"), "before": dict(e["before"]), "after": dict(e["after"])}
            for e in entries
        ],
    }


def entry(rf: Any, fix: str, after: Dict[str, Any]) -> Dict[str, Any]:
    """One fixture's entry, read before the fix writes `after` onto it."""
    return {
        "id": rf.id,
        "name": rf.name,
        "before": {f: getattr(rf, f) for f in FIELDS[fix]},
        "after": {f: after[f] for f in FIELDS[fix]},
    }


def summary(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What an undo would take back, for the answer to a fix: fix, label and count."""
    if not isinstance(record, dict) or not record.get("entries"):
        return None
    fix = record.get("fix")
    n = len(record["entries"])
    return {"fix": fix, "label": f"Undo {FIX_WORDS.get(fix, fix)}", "count": n}


def plan_undo(rows: Sequence[Any], record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What undoing `record` would do: `restore` (fixture, before) pairs, and `stale` when it must refuse."""
    if not isinstance(record, dict) or record.get("fix") not in FIELDS or not record.get("entries"):
        return {"fix": None, "restore": [], "stale": []}
    fix = record["fix"]
    fields = FIELDS[fix]
    by_id = {rf.id: rf for rf in rows}
    restore_pairs: List[Any] = []
    stale: List[Dict[str, Any]] = []
    for e in record["entries"]:
        rf = by_id.get(e.get("id"))
        label = e.get("name") or f"Fixture {e.get('id')}"
        if rf is None:
            stale.append({"id": e.get("id"), "name": label, "reason": "removed"})
            continue
        after = e.get("after") or {}
        if any(getattr(rf, f) != after.get(f) for f in fields):
            stale.append({"id": rf.id, "name": label, "reason": "changed"})
            continue
        restore_pairs.append((rf, {f: (e.get("before") or {}).get(f) for f in fields}))
    return {"fix": fix, "restore": restore_pairs, "stale": stale}


def restore(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Write each fixture's columns back to what they were before the fix. Returns what it put back."""
    done = []
    for rf, before in plan["restore"]:
        now = {f: getattr(rf, f) for f in before}
        for f, value in before.items():
            setattr(rf, f, value)
        done.append({"id": rf.id, "name": rf.name, "from": now, "to": dict(before)})
    return done


def stale_message(plan: Dict[str, Any]) -> str:
    stale = plan["stale"]
    words = FIX_WORDS.get(plan["fix"], "the fix")
    names = ", ".join(s["name"] for s in stale[:3]) + (f" and {len(stale) - 3} more" if len(stale) > 3 else "")
    what = "group" if plan["fix"] == FIX_AUTO_GROUPS else "address"
    return (
        f"Cannot undo {words}: {len(stale)} of the fixtures it changed "
        f"{'have' if len(stale) != 1 else 'has'} been changed or removed since ({names}). "
        f"Nothing was put back. Set the {what} by hand."
    )
