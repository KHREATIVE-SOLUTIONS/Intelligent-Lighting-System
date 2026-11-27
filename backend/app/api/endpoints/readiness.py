"""
Venue readiness endpoints
=========================

GET  /api/rigs/{rig_id}/readiness                  every check, worst first in `status`
POST /api/rigs/{rig_id}/readiness/fix/auto-groups  a group for each place and kind of fixture

The GET reads and writes nothing. The fix writes `group_name` on the
fixtures that are in no group, and nothing else. See docs/READINESS.md and
services/rig/readiness.py.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.rig_patching import _get_rig_fixtures_with_channels
from app.db.database import get_db
from app.services.rig.readiness import plan_auto_groups, readiness

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
    parts = [
        f"Made {made} group{'s' if made != 1 else ''} for {len(changed)} fixture{'s' if len(changed) != 1 else ''}."
        if made else "No group was needed: every placed fixture is already in one."
    ]
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
        "skipped": plan["skipped"],
        "unplaced_ids": plan["unplaced_ids"],
        "changed": changed,
        "message": " ".join(parts),
    }
