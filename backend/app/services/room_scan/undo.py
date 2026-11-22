"""
Undoing a room scan's fixture moves
===================================

Applying a scan moves a rig's unconfirmed template guesses (suggest.py). The
endpoint records, for each fixture it moved, where it was and where it went, so
the move can be taken back.

An undo only ever takes back what the scan did. A fixture is put back only if
it is still exactly what the scan left: a template guess nobody has confirmed,
standing where the scan put it. Anything a person has done to it since (tapped
in flash-and-tap, confirmed, dragged, fitted between two taps, moved in the
layout view, or removed from the rig) is left alone and reported, with the
reason.

    record = record_moves(previous_record, moved, file)   # at apply
    plan   = plan_undo(rig.fixtures, record)              # read-only
    restore(plan)                                         # writes the fixtures

Pure apart from `restore`, which sets attributes on the fixtures it is given.
Nothing here touches the database session, the engine or a device.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.venue_import.apply import position_source

from .suggest import TAG_SCAN_HINT, movable

# Two positions closer than this are the same position: stored values are
# rounded to the millimetre on their way through the API.
SAME_PLACE_M = 0.005

Point = Tuple[float, float, float]

SOURCE_WORDS = {
    "tap": "it was tapped or dragged into place since",
    "confirmed": "its position was confirmed since",
    "row_fit": "it was fitted between two tapped ends since",
}


def _point(p: Point) -> Dict[str, float]:
    return {"x": p[0], "y": p[1], "z": p[2]}


def _unpoint(value: Any) -> Optional[Point]:
    try:
        return (float(value["x"]), float(value["y"]), float(value["z"]))
    except (KeyError, TypeError, ValueError):
        return None


def _position(fixture: Any) -> Point:
    return (
        float(getattr(fixture, "position_x", 0.0) or 0.0),
        float(getattr(fixture, "position_y", 0.0) or 0.0),
        float(getattr(fixture, "position_z", 0.0) or 0.0),
    )


def _same_place(a: Point, b: Point) -> bool:
    return all(abs(x - y) <= SAME_PLACE_M for x, y in zip(a, b))


def record_moves(
    previous: Optional[Dict[str, Any]],
    moved: Sequence[Dict[str, Any]],
    file: str,
) -> Optional[Dict[str, Any]]:
    """The undo record after an apply that moved `moved`.

    Each entry of `moved` is {rig_fixture_id, name, from, to, tags_before},
    with from and to as (x, y, z).

    A second scan applied over the first does not forget the first: a fixture
    both moved keeps the place it stood before any scan, so one undo takes it
    all the way back, and a fixture only the first moved keeps its entry. An
    apply that moved nothing leaves the record as it was.
    """
    if not moved:
        return previous
    earlier = {
        entry.get("rig_fixture_id"): entry
        for entry in ((previous or {}).get("moves") or [])
        if isinstance(entry, dict)
    }
    entries: List[Dict[str, Any]] = []
    for move in moved:
        before = earlier.pop(move["rig_fixture_id"], None)
        entries.append({
            "rig_fixture_id": move["rig_fixture_id"],
            "name": move.get("name") or "",
            "from": before["from"] if before and _unpoint(before.get("from")) else _point(move["from"]),
            "to": _point(move["to"]),
            "tags_before": (
                list(before.get("tags_before") or []) if before else list(move.get("tags_before") or [])
            ),
        })
    entries.extend(earlier.values())
    return {
        "file": file,
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "moves": entries,
    }


def undo_count(record: Optional[Dict[str, Any]]) -> int:
    """How many fixture moves a record holds."""
    return len((record or {}).get("moves") or [])


@dataclass
class Restore:
    fixture: Any
    name: str
    from_position: Point  # where it stands now: where the scan put it
    to_position: Point    # where it goes back to
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rig_fixture_id": self.fixture.id,
            "name": self.name,
            "from": _point(self.from_position),
            "to": _point(self.to_position),
        }


@dataclass
class UndoPlan:
    restores: List[Restore] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "would_restore": len(self.restores),
            "would_skip": len(self.skipped),
            "restores": [r.to_dict() for r in self.restores],
            "skipped": list(self.skipped),
        }


def _tags_restored(fixture: Any, tags_before: Sequence[str]) -> List[str]:
    """The tags the fixture had before the scan, keeping any tag added since.

    Its position tags go back to what they were; the scan's hint comes off
    unless the fixture carried one before (a second scan over a first that was
    not recorded). A tag unrelated to position that was added after the scan,
    a group say, is kept.
    """
    before = [tag for tag in tags_before if isinstance(tag, str)]
    current = [tag for tag in (getattr(fixture, "tags", None) or []) if isinstance(tag, str)]
    added_since = [tag for tag in current if tag not in before and tag != TAG_SCAN_HINT]
    if not before:
        # A record with no tags kept: take the hint off and leave the rest.
        return [tag for tag in current if tag != TAG_SCAN_HINT]
    return [*before, *added_since]


def plan_undo(fixtures: Sequence[Any], record: Optional[Dict[str, Any]]) -> UndoPlan:
    """What an undo would put back, and what it would leave alone and why."""
    plan = UndoPlan()
    by_id = {getattr(f, "id", None): f for f in fixtures}
    for entry in (record or {}).get("moves") or []:
        if not isinstance(entry, dict):
            continue
        fixture_id = entry.get("rig_fixture_id")
        name = entry.get("name") or f"Fixture {fixture_id}"
        fixture = by_id.get(fixture_id)

        def skip(reason: str) -> None:
            plan.skipped.append({"rig_fixture_id": fixture_id, "name": name, "reason": reason})

        if fixture is None:
            skip("it is no longer in the rig")
            continue
        name = getattr(fixture, "name", None) or name
        came_from, went_to = _unpoint(entry.get("from")), _unpoint(entry.get("to"))
        if came_from is None or went_to is None:
            skip("the record of its move cannot be read")
            continue
        if not movable(fixture):
            source = position_source(getattr(fixture, "tags", None))
            skip(SOURCE_WORDS.get(source or "", "its position was set by something else since"))
            continue
        here = _position(fixture)
        if not _same_place(here, went_to):
            skip("it was moved since the scan")
            continue
        plan.restores.append(Restore(
            fixture=fixture,
            name=name,
            from_position=here,
            to_position=came_from,
            tags=_tags_restored(fixture, entry.get("tags_before") or []),
        ))
    return plan


def restore(plan: UndoPlan) -> int:
    """Put the planned fixtures back. Returns how many."""
    for item in plan.restores:
        fixture = item.fixture
        fixture.position_x, fixture.position_y, fixture.position_z = item.to_position
        # A new list: the column is plain JSON, so a change in place is never written.
        fixture.tags = list(item.tags)
    return len(plan.restores)


def undo_message(restored: int, skipped: int) -> str:
    """One sentence for the operator on what an undo did."""
    def lights(n: int) -> str:
        return f"{n} fixture{'' if n == 1 else 's'}"

    if restored == 0 and skipped == 0:
        return "There were no room scan moves to undo."
    parts = []
    if restored:
        parts.append(f"{lights(restored)} put back where {'it' if restored == 1 else 'they'} stood before the scan.")
    else:
        parts.append("No fixture was put back.")
    if skipped:
        parts.append(
            f"{lights(skipped)} left alone, because {'it has' if skipped == 1 else 'they have'} "
            "been placed, confirmed or moved since."
        )
    return " ".join(parts)
