"""
Room Scan Endpoint
==================

POST /api/rigs/{rig_id}/room-scan takes a phone scan of the room (OBJ, PLY, a
USDZ or USDA with a text layer, RoomPlan JSON) and answers with a preview: the
room shell it suggests, the guesses it made on the way, and where it would move
the rig's unconfirmed fixtures. Nothing is written.

The same request with apply=true stores that shell on the rig and moves those
fixtures. They stay tagged as guesses: a scan suggests, flash-and-tap and
dragging decide.

The file is sent again to apply. Nothing is kept on the server between the two
requests, so a preview can never be applied against a different file.

Nothing here reaches a device. The shell is scenery for the 3D view and is not
read by the engine; a fixture's stored position changes, its DMX does not.

Applying records where each fixture it moved stood before, on the rig
(rigs.room_scan_undo). POST /api/rigs/{rig_id}/room-scan/undo puts them back;
GET on the same path says what that would do. Only a fixture that is still the
guess the scan left is put back: one a person has tapped, confirmed, dragged or
moved since is left alone and reported (services/room_scan/undo.py).

DELETE /api/rigs/{rig_id}/room-shell takes the shell off again. It leaves moved
fixtures where they are unless asked to put them back (restore_fixtures=true).
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.services.room_scan import (
    RoomScanError, ScanOptions, extract_room, read_scan_file, suggest_positions,
)
from app.services.room_scan.suggest import TAG_SCAN_HINT
from app.services.room_scan.undo import plan_undo, record_moves, restore, undo_count, undo_message
from app.services.venue_import.apply import SOURCE_TEMPLATE, is_unconfirmed, with_position_source

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DOC = "docs/ROOM_SCAN.md"


def _read_and_extract(filename: str, content: bytes, options: ScanOptions):
    """Parse and extract in one call, so both run off the event loop together."""
    return extract_room(read_scan_file(filename, content), options)


LOCATE_RUNNING = "A locate walkthrough is running on this rig. Finish or end it, then {then}."


def locate_running(rig_id: int) -> bool:
    """Whether a flash-and-tap walkthrough holds this rig's fixtures right now."""
    from app.api.endpoints import rig_identify

    return any(
        session.rig_id == rig_id and not session.released
        for session in rig_identify._sessions.values()
    )


async def _rig_with_fixtures(db: AsyncSession, rig_id: int) -> Rig:
    result = await db.execute(
        select(Rig).where(Rig.id == rig_id).options(selectinload(Rig.fixtures))
    )
    rig = result.scalar_one_or_none()
    if rig is None:
        raise HTTPException(status_code=404, detail="Rig not found")
    return rig


@router.post("/rigs/{rig_id}/room-scan")
async def import_room_scan(
    rig_id: int,
    file: UploadFile = File(..., description="A scan export: .obj, .ply, .usdz, .usda or RoomPlan .json"),
    apply: bool = Query(False, description="Store the suggested shell on the rig and move its unconfirmed fixtures"),
    units: str = Query("auto", pattern="^(auto|m|cm|mm)$", description="The scan's units, when the guess is wrong"),
    up_axis: str = Query("auto", pattern="^(auto|y|z)$", description="The scan's up axis, when the guess is wrong"),
    rotate: int = Query(0, description="A further 0, 90, 180 or 270 degrees clockwise seen from above"),
    move_fixtures: bool = Query(True, description="With apply: also move the unconfirmed fixtures as previewed"),
    db: AsyncSession = Depends(get_db),
):
    """Preview a room scan against a rig, or with apply=true store it."""
    if rotate not in (0, 90, 180, 270):
        raise HTTPException(status_code=400, detail="rotate must be 0, 90, 180 or 270.")
    rig = await _rig_with_fixtures(db, rig_id)

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Export the scan at a lower detail.",
        )
    filename = file.filename or ""

    # Parsing a mesh is CPU work; keep it off the loop the show runs on.
    try:
        found = await asyncio.to_thread(
            _read_and_extract, filename, content, ScanOptions(units=units, up_axis=up_axis, rotate=rotate)
        )
    except RoomScanError as e:
        raise HTTPException(status_code=400, detail=str(e))

    moves, move_notes = suggest_positions(rig.fixtures, found.shell)
    unconfirmed = sum(1 for rf in rig.fixtures if is_unconfirmed(rf.tags))
    shell = found.shell
    preview: Dict[str, Any] = {
        "rig_id": rig.id,
        "rig_name": rig.name,
        "file": filename,
        "format": shell["scan"]["format"],
        "room_shell": shell,
        "replaces_existing_shell": rig.room_shell is not None,
        "summary": {
            "width": shell["room"]["width"],
            "depth": shell["room"]["depth"],
            "height": shell["room"]["height"],
            "raised_areas": len(shell["risers"]),
            "overhead_lines": len(shell["truss_lines"]),
            "overhead_rings": len(shell.get("truss_rings") or []),
            # 4 for a box; the number of outline segments for a room that is not one.
            "walls": len(shell["room"].get("outline") or []) or 4,
            "hanging_heights": [band["height"] for band in shell["hanging_bands"]],
            "units": shell["scan"]["units"],
            "up_axis": shell["scan"]["up_axis"],
        },
        "assumptions": found.assumptions,
        "warnings": found.warnings + move_notes,
        "fixtures": {
            "total": len(rig.fixtures),
            "unconfirmed": unconfirmed,
            "would_move": len(moves),
            "moves": [move.to_dict() for move in moves],
        },
        "operator_guide": DOC,
        "applied": None,
    }
    if not apply:
        return preview

    moved: List[Dict[str, Any]] = []
    if move_fixtures and moves:
        if locate_running(rig.id):
            raise HTTPException(status_code=409, detail=LOCATE_RUNNING.format(then="apply the scan"))
        by_id = {rf.id: rf for rf in rig.fixtures}
        for move in moves:
            rf = by_id.get(move.rig_fixture_id)
            if rf is None:
                continue
            tags_before = list(rf.tags or [])
            rf.position_x, rf.position_y, rf.position_z = move.to_position
            # Still a template guess, and still unconfirmed: flash-and-tap's
            # row fit and mirror go on treating it as one. The hint records
            # that a scan has shifted it.
            tags = with_position_source(rf.tags, SOURCE_TEMPLATE, confirmed=False)
            if TAG_SCAN_HINT not in tags:
                tags.append(TAG_SCAN_HINT)
            rf.tags = tags
            moved.append({
                "rig_fixture_id": rf.id, "name": move.name,
                "from": move.from_position, "to": move.to_position, "tags_before": tags_before,
            })

    # A new dict: the column is plain JSON, so a change made in place is never written.
    rig.room_shell = dict(shell)
    # Where each moved fixture stood, so the move can be undone. An apply that
    # moved nothing leaves an earlier record standing.
    rig.room_scan_undo = record_moves(rig.room_scan_undo, moved, filename)
    await db.flush()

    preview["applied"] = {
        "room_shell_stored": True,
        "fixtures_moved": len(moved),
        "fixtures_still_unconfirmed": unconfirmed,
        "undo_available": undo_count(rig.room_scan_undo),
        "message": (
            "The room is stored on the rig as a suggestion. "
            + (f"{len(moved)} unconfirmed fixtures were moved and are still unconfirmed: "
               "check them with Identify Lights, or drag them in the 3D view. "
               "Undo room scan moves puts them back." if moved
               else "No fixture was moved.")
        ),
    }
    logger.info(
        "Room scan: rig %s '%s' from %s (%s): %.1f x %.1f x %.1f m, %d raised, %d overhead lines, %d fixtures moved",
        rig.id, rig.name, filename, shell["scan"]["format"],
        shell["room"]["width"], shell["room"]["depth"], shell["room"]["height"],
        len(shell["risers"]), len(shell["truss_lines"]), len(moved),
    )
    return preview


def _undo_moves(rig: Rig) -> Dict[str, Any]:
    """Put back what the rig's undo record says a scan moved, and spend the record."""
    plan = plan_undo(rig.fixtures, rig.room_scan_undo)
    if plan.restores and locate_running(rig.id):
        raise HTTPException(status_code=409, detail=LOCATE_RUNNING.format(then="undo the room scan moves"))
    restored = [item.to_dict() for item in plan.restores]
    restore(plan)
    # Spent whether or not anything was skipped: what was skipped is what a
    # person has placed since, and that is not the scan's to take back later.
    rig.room_scan_undo = None
    return {
        "rig_id": rig.id,
        "restored": len(restored),
        "skipped": len(plan.skipped),
        "restored_fixtures": restored,
        "skipped_fixtures": plan.skipped,
        "message": undo_message(len(restored), len(plan.skipped)),
    }


@router.get("/rigs/{rig_id}/room-scan/undo")
async def preview_room_scan_undo(rig_id: int, db: AsyncSession = Depends(get_db)):
    """What undoing the room scan's moves would put back and leave alone. Writes nothing."""
    rig = await _rig_with_fixtures(db, rig_id)
    plan = plan_undo(rig.fixtures, rig.room_scan_undo)
    record = rig.room_scan_undo or {}
    return {
        "rig_id": rig.id,
        "available": undo_count(rig.room_scan_undo),
        "file": record.get("file"),
        "applied_at": record.get("applied_at"),
        **plan.to_dict(),
    }


@router.post("/rigs/{rig_id}/room-scan/undo")
async def undo_room_scan_moves(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Put the fixtures a room scan moved back where they stood before it.

    A fixture a person has tapped, confirmed, dragged or moved since is not
    touched; it comes back in `skipped_fixtures` with the reason. The stored
    room stays. Nothing reaches a device.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    answer = _undo_moves(rig)
    await db.flush()
    logger.info(
        "Room scan undo: rig %s '%s': %d fixtures put back, %d left alone",
        rig.id, rig.name, answer["restored"], answer["skipped"],
    )
    return answer


@router.delete("/rigs/{rig_id}/room-shell")
async def remove_room_shell(
    rig_id: int,
    restore_fixtures: bool = Query(False, description="Also put back the fixtures the scan moved"),
    db: AsyncSession = Depends(get_db),
):
    """Take the stored room off a rig.

    Fixtures are left where they are unless restore_fixtures is set, which
    also undoes the scan's moves (as POST .../room-scan/undo does). Left alone,
    the moves can still be undone afterwards.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    had = rig.room_shell is not None
    answer: Dict[str, Any] = {"rig_id": rig.id, "removed": had}
    if restore_fixtures:
        undone = _undo_moves(rig)
        answer.update({
            "fixtures_restored": undone["restored"],
            "fixtures_skipped": undone["skipped"],
            "skipped_fixtures": undone["skipped_fixtures"],
            "message": undone["message"],
        })
    rig.room_shell = None
    await db.flush()
    answer["undo_available"] = undo_count(rig.room_scan_undo)
    return answer
