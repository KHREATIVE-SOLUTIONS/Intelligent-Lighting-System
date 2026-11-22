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

DELETE /api/rigs/{rig_id}/room-shell takes the shell off again. It does not put
moved fixtures back.
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
from app.services.venue_import.apply import SOURCE_TEMPLATE, is_unconfirmed, with_position_source

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DOC = "docs/ROOM_SCAN.md"


def _read_and_extract(filename: str, content: bytes, options: ScanOptions):
    """Parse and extract in one call, so both run off the event loop together."""
    return extract_room(read_scan_file(filename, content), options)


def _locate_running(rig_id: int) -> bool:
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

    moved: List[int] = []
    if move_fixtures and moves:
        if _locate_running(rig.id):
            raise HTTPException(
                status_code=409,
                detail="A locate walkthrough is running on this rig. Finish or end it, then apply the scan.",
            )
        by_id = {rf.id: rf for rf in rig.fixtures}
        for move in moves:
            rf = by_id.get(move.rig_fixture_id)
            if rf is None:
                continue
            rf.position_x, rf.position_y, rf.position_z = move.to_position
            # Still a template guess, and still unconfirmed: flash-and-tap's
            # row fit and mirror go on treating it as one. The hint records
            # that a scan has shifted it.
            tags = with_position_source(rf.tags, SOURCE_TEMPLATE, confirmed=False)
            if TAG_SCAN_HINT not in tags:
                tags.append(TAG_SCAN_HINT)
            rf.tags = tags
            moved.append(rf.id)

    # A new dict: the column is plain JSON, so a change made in place is never written.
    rig.room_shell = dict(shell)
    await db.flush()

    preview["applied"] = {
        "room_shell_stored": True,
        "fixtures_moved": len(moved),
        "fixtures_still_unconfirmed": unconfirmed,
        "message": (
            "The room is stored on the rig as a suggestion. "
            + (f"{len(moved)} unconfirmed fixtures were moved and are still unconfirmed: "
               "check them with Identify Lights, or drag them." if moved
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


@router.delete("/rigs/{rig_id}/room-shell")
async def remove_room_shell(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Take the stored room off a rig. Fixtures are left where they are."""
    rig = (await db.execute(select(Rig).where(Rig.id == rig_id))).scalar_one_or_none()
    if rig is None:
        raise HTTPException(status_code=404, detail="Rig not found")
    had = rig.room_shell is not None
    rig.room_shell = None
    await db.flush()
    return {"rig_id": rig.id, "removed": had}
