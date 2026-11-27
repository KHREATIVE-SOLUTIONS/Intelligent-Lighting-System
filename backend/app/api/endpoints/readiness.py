"""
Venue readiness endpoints
=========================

GET  /api/rigs/{rig_id}/readiness                  every check, worst first in `status`
POST /api/rigs/{rig_id}/readiness/fix/auto-groups  a group for each place and kind of fixture
POST /api/rigs/{rig_id}/readiness/fix/readdress    a free address for each fixture that clashes

The GET reads and writes nothing. Make groups writes `group_name` on the
fixtures that are in no group, and nothing else. Re-address writes
`universe` and `dmx_address` on the fixtures that clash, and nothing else;
with ?dry_run=true it writes nothing and answers the same plan. See
docs/READINESS.md and services/rig/readiness.py.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.rig_patching import _get_rig_fixtures_with_channels
from app.db.database import get_db
from app.services.rig.readiness import plan_auto_groups, plan_readdress, readiness

router = APIRouter()


@router.get("/rigs/{rig_id}/readiness")
async def read_readiness(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Whether this rig is ready to program, check by check. Writes nothing."""
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    return readiness(rig, rows)


@router.post("/rigs/{rig_id}/readiness/fix/auto-groups")
async def fix_auto_groups(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Put every fixture that is in no group in one named for where it hangs and what it is.

    "Front truss Spots", "SL tower Washes". A name the rig already has is not
    made again, and a fixture with no position is left alone, so a second
    call changes nothing. All in one write: the rig has no undo for groups,
    so `changed` lists each fixture with the group it had (none) to put back
    by hand.
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = plan_auto_groups(rig, rows)
    changed = []
    for rf in rows:
        name = plan["assign"].get(rf.id)
        if name is None:
            continue
        changed.append({"id": rf.id, "name": rf.name, "group_before": rf.group_name, "group_name": name})
        rf.group_name = name
    if changed:
        await db.flush()

    made = len(plan["created"])
    joined = sum(len(a["fixture_ids"]) for a in plan["added"])
    parts = []
    if made:
        n = len(changed) - joined
        parts.append(f"Made {made} group{'s' if made != 1 else ''} for {n} fixture{'s' if n != 1 else ''}.")
    if joined:
        parts.append(
            f"Added {joined} fixture{'s' if joined != 1 else ''} to "
            + ", ".join(a["name"] for a in plan["added"]) + "."
        )
    if not changed:
        parts.append("No group was needed: every placed fixture is already in one.")
    if plan["skipped"]:
        parts.append(
            "Left alone because the rig already has a group of that name: "
            + ", ".join(s["name"] for s in plan["skipped"]) + "."
        )
    if plan["unplaced_ids"]:
        n = len(plan["unplaced_ids"])
        parts.append(f"{n} fixture{'s have' if n != 1 else ' has'} no position and {'were' if n != 1 else 'was'} not grouped.")
    return {
        "rig_id": rig.id,
        "created": plan["created"],
        "added": plan["added"],
        "skipped": plan["skipped"],
        "unplaced_ids": plan["unplaced_ids"],
        "changed": changed,
        "message": " ".join(parts),
    }


def _readdress_message(plan: dict, dry_run: bool) -> str:
    moves, left = plan["moves"], plan["left"]
    n = len(moves)
    if not moves and not left:
        return "Nothing to move: no fixture overlaps another or runs past channel 512."
    parts = []
    if moves:
        verb = "Would move" if dry_run else "Moved"
        parts.append(
            f"{verb} {n} fixture{'s' if n != 1 else ''}: "
            + "; ".join(f"{m['name'] or 'Fixture ' + str(m['id'])} {m['from_label']} to {m['to_label']}" for m in moves[:5])
            + (f" and {n - 5} more" if n > 5 else "") + "."
        )
        guessed = sum(1 for m in moves if m["guessed"])
        if guessed:
            parts.append(
                f"{guessed} of them {'have' if guessed != 1 else 'has'} no DMX mode, so the clash was found "
                "with a guessed 16-channel footprint and may not be real."
            )
        parts.append("Set each moved fixture to its new address on the fixture itself.")
    if left:
        parts.append(" ".join(entry["message"] for entry in left))
    return " ".join(parts)


@router.post("/rigs/{rig_id}/readiness/fix/readdress")
async def fix_readdress(
    rig_id: int,
    dry_run: bool = Query(False, description="Answer the planned moves and change nothing."),
    db: AsyncSession = Depends(get_db),
):
    """Move each fixture that overlaps another, or runs past channel 512, to a free address.

    Only fixtures that clash move; of two that overlap the one patched first
    (lower id) stays, and an address-locked fixture never moves. Each move
    goes to the first free range at or after its address in the same
    universe, else the first in that universe, else the next universe with
    room. All in one write. The rig has no undo for addresses, so `moves`
    lists each fixture's address before and after, to put back by hand. A
    second call finds nothing to move.
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = plan_readdress(rows)
    if not dry_run and plan["moves"]:
        planned = {m["id"]: m for m in plan["moves"]}
        for rf in rows:
            move = planned.get(rf.id)
            if move is not None:
                rf.universe = move["to_universe"]
                rf.dmx_address = move["to_address"]
        await db.flush()
    return {
        "rig_id": rig.id,
        "dry_run": dry_run,
        "moves": plan["moves"],
        "left": plan["left"],
        "conflicts_after": plan["conflicts_after"],
        "past_end_after": plan["past_end_after"],
        "message": _readdress_message(plan, dry_run),
    }
