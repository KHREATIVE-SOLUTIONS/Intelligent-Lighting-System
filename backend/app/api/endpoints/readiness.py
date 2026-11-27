"""
Venue readiness endpoints
=========================

GET  /api/rigs/{rig_id}/readiness                  every check, worst first in `status`
POST /api/rigs/{rig_id}/readiness/fix/auto-groups  a group for each place and kind of fixture
POST /api/rigs/{rig_id}/readiness/fix/readdress    a free address for each fixture that clashes
POST /api/rigs/{rig_id}/readiness/fix/set-modes    the DMX mode, where only one is possible
POST /api/rigs/{rig_id}/readiness/fix/undo         put back what the last of those three changed
GET  /api/rigs/{rig_id}/handoff-pack               a zip of everything needed to program it (reads only)

The GET reads and writes nothing. Make groups writes `group_name` on the
fixtures that are in no group, and nothing else. Re-address writes
`universe` and `dmx_address` on the fixtures that clash, and nothing else.
Set modes writes `mode_id` on the fixtures the DMX modes check names where
one mode is unambiguous, and nothing else. Re-address and Set modes take
?dry_run=true: it writes nothing and answers the same plan. Each fix
that changes something also keeps what it changed on the rig
(`rigs.readiness_undo`), so Undo takes it back as one step. See
docs/READINESS.md, services/rig/readiness.py and readiness_undo.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.rig_patching import _get_rig_fixtures_with_channels
from app.db.database import get_db
from app.models.fixture import FixtureMode
from app.services.rig import readiness_undo
from app.services.rig.handoff_pack import build_handoff_pack
from app.services.rig.readiness import plan_auto_groups, plan_readdress, plan_set_modes, readiness

router = APIRouter()


@router.get("/rigs/{rig_id}/readiness")
async def read_readiness(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Whether this rig is ready to program, check by check. Writes nothing."""
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    return readiness(rig, rows)


@router.get("/rigs/{rig_id}/handoff-pack")
async def download_handoff_pack(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Everything needed to program this rig, as one zip: patch.csv, groups.csv,
    readiness.md, the grandMA2 and MVR exports and a README. Built in memory;
    reads only. A console file whose writer fails is left out and named in
    README.txt and readiness.md. See docs/HANDOFF_PACK.md.
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    content, filename = build_handoff_pack(rig, rows)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/rigs/{rig_id}/readiness/fix/auto-groups")
async def fix_auto_groups(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Put every fixture that is in no group in one named for where it hangs and what it is.

    "Front truss Spots", "SL tower Washes". A name the rig already has is not
    made again, and a fixture with no position is left alone, so a second
    call changes nothing. All in one write, and one step of Undo
    (POST .../readiness/fix/undo); `changed` lists each fixture with the
    group it had (none).
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = plan_auto_groups(rig, rows)
    changed, entries = [], []
    for rf in rows:
        name = plan["assign"].get(rf.id)
        if name is None:
            continue
        changed.append({"id": rf.id, "name": rf.name, "group_before": rf.group_name, "group_name": name})
        entries.append(readiness_undo.entry(rf, readiness_undo.FIX_AUTO_GROUPS, {"group_name": name}))
        rf.group_name = name
    if changed:
        # Only a call that changed something replaces the undo: a second
        # press, which changes nothing, must not lose the first one's undo.
        rig.readiness_undo = readiness_undo.make_record(readiness_undo.FIX_AUTO_GROUPS, entries)
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
        "undo": readiness_undo.summary(rig.readiness_undo),
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
    room. All in one write, and one step of Undo (POST .../readiness/fix/undo);
    `moves` lists each fixture's address before and after. A second call
    finds nothing to move.
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = plan_readdress(rows)
    if not dry_run and plan["moves"]:
        planned = {m["id"]: m for m in plan["moves"]}
        entries = []
        for rf in rows:
            move = planned.get(rf.id)
            if move is not None:
                after = {"universe": move["to_universe"], "dmx_address": move["to_address"]}
                entries.append(readiness_undo.entry(rf, readiness_undo.FIX_READDRESS, after))
                rf.universe = move["to_universe"]
                rf.dmx_address = move["to_address"]
        rig.readiness_undo = readiness_undo.make_record(readiness_undo.FIX_READDRESS, entries)
        await db.flush()
    return {
        "rig_id": rig.id,
        "dry_run": dry_run,
        "moves": plan["moves"],
        "left": plan["left"],
        "conflicts_after": plan["conflicts_after"],
        "past_end_after": plan["past_end_after"],
        "undo": readiness_undo.summary(rig.readiness_undo),
        "message": _readdress_message(plan, dry_run),
    }


async def _modes_by_profile(rows, db: AsyncSession):
    """Each profile's modes, for the profiles of these fixtures (rf.fixture.modes is not loaded)."""
    ids = sorted({rf.fixture_id for rf in rows if rf.fixture_id is not None})
    if not ids:
        return {}
    result = await db.execute(select(FixtureMode).where(FixtureMode.fixture_id.in_(ids)))
    modes = {}
    for mode in result.scalars().all():
        modes.setdefault(mode.fixture_id, []).append(mode)
    return modes


def _forget_modes(db: AsyncSession, fixtures) -> None:
    """After `mode_id` is written: the loaded `mode` is the old one. The next read loads it afresh."""
    for rf in fixtures:
        db.expire(rf, ["mode"])


def _set_modes_message(plan: dict, dry_run: bool) -> str:
    proposals, by_hand, clashes = plan["proposals"], plan["by_hand"], plan["clashes"]
    if not proposals and not by_hand:
        return "Nothing to set: every matched fixture has a DMX mode of its own profile."
    parts = []
    if proposals:
        n = len(proposals)
        verb = "Would set" if dry_run else "Set"
        parts.append(
            f"{verb} the DMX mode of {n} fixture{'s' if n != 1 else ''}: "
            + "; ".join(f"{p['name']} to {p['mode_name']} ({p['channel_count']}ch)" for p in proposals[:5])
            + (f" and {n - 5} more" if n > 5 else "") + "."
        )
    if by_hand:
        n = len(by_hand)
        parts.append(
            f"{n} fixture{'s' if n != 1 else ''} must be picked by hand, as more than one mode could be right "
            f"or none is known ({', '.join(b['name'] for b in by_hand[:3])}{' and more' if n > 3 else ''})."
        )
    if clashes:
        n = len(clashes)
        parts.append(
            f"With the new footprint{'s' if len(proposals) != 1 else ''} {n} address clash{'es' if n != 1 else ''} "
            f"{'would' if dry_run else 'will'} show: " + " ".join(c["message"] for c in clashes[:3])
            + (f" and {n - 3} more." if n > 3 else "")
            + " No address was moved; run Re-address for that."
        )
    return " ".join(parts)


@router.post("/rigs/{rig_id}/readiness/fix/set-modes")
async def fix_set_modes(
    rig_id: int,
    dry_run: bool = Query(False, description="Answer the planned modes and change nothing."),
    db: AsyncSession = Depends(get_db),
):
    """Set the DMX mode of each fixture the DMX modes check names, where only one mode is possible.

    A profile with a single mode, or exactly one mode of the fixture's present
    footprint or address span. Every other fixture is listed under `by_hand`
    with its candidate modes and is not changed. Writes `mode_id` only; never
    moves an address, and lists under `clashes` any overlap or run past 512
    the new footprints would make. One step of Undo (POST .../readiness/fix/undo).
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = plan_set_modes(rows, await _modes_by_profile(rows, db))
    if not dry_run and plan["proposals"]:
        planned = {p["id"]: p for p in plan["proposals"]}
        entries, changed = [], []
        for rf in rows:
            proposal = planned.get(rf.id)
            if proposal is not None:
                entries.append(readiness_undo.entry(rf, readiness_undo.FIX_SET_MODES, {"mode_id": proposal["mode_id"]}))
                rf.mode_id = proposal["mode_id"]
                changed.append(rf)
        rig.readiness_undo = readiness_undo.make_record(readiness_undo.FIX_SET_MODES, entries)
        await db.flush()
        _forget_modes(db, changed)
    return {
        "rig_id": rig.id,
        "dry_run": dry_run,
        "proposals": plan["proposals"],
        "by_hand": plan["by_hand"],
        "clashes": plan["clashes"],
        "undo": readiness_undo.summary(rig.readiness_undo),
        "message": _set_modes_message(plan, dry_run),
    }


@router.post("/rigs/{rig_id}/readiness/fix/undo")
async def undo_readiness_fix(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Put back exactly what the last Make groups, Re-address or Set modes changed, as one step.

    Only the columns that fix wrote, only on the fixtures it changed. When
    any of them has been changed or removed since, nothing is put back: 409,
    naming them. With nothing to undo it answers so and changes nothing. A
    successful undo spends the record, so a second one finds nothing.
    """
    rig, rows, _ = await _get_rig_fixtures_with_channels(rig_id, db)
    plan = readiness_undo.plan_undo(rows, rig.readiness_undo)
    if plan["fix"] is None:
        return {
            "rig_id": rig.id, "fix": None, "restored": [], "undo": None,
            "message": "Nothing to undo: no readiness fix has changed this rig since the last undo.",
        }
    if plan["stale"]:
        raise HTTPException(
            status_code=409,
            detail={"message": readiness_undo.stale_message(plan), "stale": plan["stale"]},
        )
    restored = readiness_undo.restore(plan)
    rig.readiness_undo = None
    await db.flush()
    n = len(restored)
    noun = f"{n} fixture{'s' if n != 1 else ''}"
    if plan["fix"] == readiness_undo.FIX_AUTO_GROUPS:
        message = f"Undid Make groups: {noun} back in no group."
    elif plan["fix"] == readiness_undo.FIX_SET_MODES:
        _forget_modes(db, [rf for rf, _ in plan["restore"]])
        message = f"Undid Set modes: {noun} back on the DMX mode {'they' if n != 1 else 'it'} had (or none)."
    else:
        message = (
            f"Undid Re-address: {noun} back at the address {'they' if n != 1 else 'it'} had. "
            "Set each fixture back to that address on the fixture itself."
        )
    return {"rig_id": rig.id, "fix": plan["fix"], "restored": restored, "undo": None, "message": message}
