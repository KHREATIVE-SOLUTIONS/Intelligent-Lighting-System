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

PATCH and DELETE on /api/rigs/{rig_id}/room-shell/{kind}/{index} rename, move,
resize, raise, turn or take out one raised area, overhead line or ring of the
stored shell, and POST /api/rigs/{rig_id}/room-shell/{kind} adds one: the scan
suggested a room, and a person who can see it corrects it
(services/room_scan/edit.py). The fixtures hung on a line or ring that is
moved, raised, turned or resized go with it unless the request says not
(`carry_fixtures`, services/room_scan/carry.py): their positions and headings
only, never a patch or a tag. So do the fixtures standing on a raised area
that is moved, raised, resized or given a quarter turn. Nothing else moves a
fixture: not a rename, a change of what a raised area is, an added item or a
deleted one.

Each of those edits leaves the room as it was on the rig, with what it
carried (rigs.room_shell_undo), and POST /api/rigs/{rig_id}/room-shell/undo
takes the latest one back, fixtures included; GET on the same path says what
that would be
(services/room_scan/edit_undo.py). The record is emptied when a scan is
applied again and when the room is taken off. All of them are refused while a
locate walkthrough is running on the rig.

PATCH /api/rigs/{rig_id}/room-shell/outline redraws the room's walls (every
corner of its floor) and sets its height; PATCH, POST and DELETE under
.../room-shell/outline/corners move, add and take out one corner; GET
.../room-shell/outline reads them (services/room_scan/outline_edit.py). They
go through the same undo and the same refusal. No fixture and nothing in the
room is moved to suit new walls: each answer lists what they leave outside.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.services.room_scan import (
    RoomScanError, ScanOptions, extract_room, read_scan_file, suggest_positions,
)
from app.services.room_scan.carry import (
    apply_areas, apply_moves, areas_report, carried_area_moves, carried_areas, carried_moves, carried_words,
    put_back, put_back_words, refuse_areas_outside, refuse_outside,
)
from app.services.room_scan.edit import (
    KINDS, ShellEditError, add_item, delete_item, edit_item, edit_words, first_stage, item_name,
)
from app.services.room_scan.edit_undo import pop_step, push_step, undo_summary
from app.services.room_scan.outline_edit import (
    corner_points, delete_corner, insert_corner, move_corner, outside_report, outside_words, room_corners, set_outline,
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
    # The edits made by hand were to the room this one replaces: there is nothing of it to go back to.
    rig.room_shell_undo = None
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
    # With the room gone, so are the edits to it that could be undone.
    rig.room_shell_undo = None
    await db.flush()
    answer["undo_available"] = undo_count(rig.room_scan_undo)
    return answer


class ShellItemEdit(BaseModel):
    """What to change on one raised area, overhead line or ring. Anything left out is kept."""
    name: Optional[str] = Field(default=None, max_length=200)
    # The numbers are not held to finite ones here. JSON has no infinity, but a
    # client can send one all the same, and FastAPI's own refusal then fails to
    # answer (it cannot write the value back, and the request ends as a 500).
    # edit.py refuses anything that is not a finite number, in a sentence.
    #
    # Where the middle of it goes, in the rig's axes: metres, X across, -Z upstage.
    center_x: Optional[float] = None
    center_z: Optional[float] = None
    # A raised area's size on the plan: along X, and along Z.
    width: Optional[float] = None
    depth: Optional[float] = None
    # A line's, end to end.
    length: Optional[float] = None
    # A ring's, to the middle of the truss.
    radius: Optional[float] = None
    # A raised area's deck above its base; the underside of a line or ring.
    height: Optional[float] = None
    # Which way a line runs: degrees clockwise from across the room, seen from above.
    heading_deg: Optional[float] = None
    # A raised area's underside above the floor: 0 stands on it, more floats (a balcony, a mezzanine).
    base_height: Optional[float] = None
    # What a raised area is: "stage", "riser" or "booth". Added, it is a riser when left out;
    # edited, it keeps what it is.
    riser_kind: Optional[str] = Field(default=None, max_length=20)


class ShellItemPatch(ShellItemEdit):
    """A change to one item, and whether the fixtures hung on it or standing on it go with it."""
    # Left out (or null), they do. False leaves every fixture where it is.
    carry_fixtures: Optional[bool] = True


class ShellItemAdd(ShellItemEdit):
    """A raised area, overhead line or ring to put into the stored room by hand."""


async def _rig(db: AsyncSession, rig_id: int) -> Rig:
    rig = (await db.execute(select(Rig).where(Rig.id == rig_id))).scalar_one_or_none()
    if rig is None:
        raise HTTPException(status_code=404, detail="Rig not found")
    return rig


def _not_during_locate(rig: Rig, then: str) -> None:
    """Refuse a change to the room while a flash-and-tap walkthrough is running on the rig.

    The walkthrough places fixtures against the room as it stands (its truss
    lines and hanging heights) and holds its own copy of each position, which
    a truss carrying its fixtures would go behind; and its operator is looking
    at the lights, not at this.
    """
    if locate_running(rig.id):
        raise HTTPException(status_code=409, detail=LOCATE_RUNNING.format(then=then))


# ---------------------------------------------------------------------------
# The walls: the floor outline and the room's height
# ---------------------------------------------------------------------------

class OutlineEdit(BaseModel):
    """The room's walls, its height, or both. Anything left out is kept."""
    # Every corner of the floor in order, each [x, z] in metres in the rig's
    # axes (X across, -Z upstage); the last is joined back to the first. Not
    # held to numbers here, for the reason given on ShellItemEdit: a raw
    # Infinity must be refused in a sentence by outline_edit.py, not by a
    # FastAPI refusal that cannot write it back. Not held to a list either:
    # `"corners": Infinity` would be refused here, and end the same way.
    corners: Optional[Any] = None
    # Floor to ceiling, in metres.
    height: Optional[float] = None


class CornerMove(BaseModel):
    """Where one corner of the walls goes. One of x and z given alone keeps the other."""
    x: Optional[float] = None
    z: Optional[float] = None


class CornerInsert(BaseModel):
    """A new corner on the wall that leaves corner `after` (from 0). With no place given, half way along it."""
    after: int
    x: Optional[float] = None
    z: Optional[float] = None


def _walls(shell: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The walls of a stored room as an answer carries them: its corners, whether it is a box, its height."""
    corners, is_box = room_corners(shell)
    return {
        "outline": corner_points(corners),
        "box": is_box,
        "height": shell["room"].get("height"),
        "width": shell["room"].get("width"),
        "depth": shell["room"].get("depth"),
    }


def _walls_changed(rig: Rig, before: Dict[str, Any], shell: Dict[str, Any], done: Optional[str]) -> Dict[str, Any]:
    """Store a change to the walls with its undo step, and answer with what the walls now leave outside.

    No fixture and no item of the room is moved to suit the new walls: what
    they leave outside is listed for a person to deal with. A change that
    changes nothing is not written and leaves no step.
    """
    was = outside_report(before, rig.fixtures)
    if done is not None:
        # A new object throughout: the column is plain JSON, so a change made in place is never written.
        rig.room_shell = shell
        rig.room_shell_undo = push_step(rig.room_shell_undo, before, done)
        logger.info("Room shell: rig %s '%s': %s", rig.id, rig.name, done)
    stored = shell if done is not None else before
    outside = outside_report(stored, rig.fixtures, before=was)
    return {
        "rig_id": rig.id,
        "room_shell": stored,
        **_walls(stored),
        "changed": done is not None,
        "undo": undo_summary(rig.room_shell_undo),
        "outside": outside,
        "message": (f"{done}. " if done else "The walls are as they were. ") + outside_words(outside),
    }


@router.get("/rigs/{rig_id}/room-shell/outline")
async def read_room_outline(rig_id: int, db: AsyncSession = Depends(get_db)):
    """The stored room's walls as corners, and what they leave outside. Writes nothing.

    A box room answers its four corners, clockwise seen from above from
    upstage stage right, with `box` true. `outside` lists the raised areas,
    lines, rings and fixtures beyond a wall or above the ceiling as the room
    now stands.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    try:
        walls = _walls(rig.room_shell)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return {"rig_id": rig.id, **walls, "outside": outside_report(rig.room_shell, rig.fixtures)}


@router.patch("/rigs/{rig_id}/room-shell/outline")
async def edit_room_outline(rig_id: int, body: OutlineEdit, db: AsyncSession = Depends(get_db)):
    """Redraw the stored room's walls, set its height, or both.

    `corners` replaces every corner of the floor. The room's box (`width`,
    `depth`) is worked out again from them, about the origin, which does not
    move. No fixture, raised area, truss or ring is moved: `outside` lists
    what the new walls and ceiling leave outside. One undo step
    (POST .../room-shell/undo). Nothing reaches a device
    (services/room_scan/outline_edit.py).
    """
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    try:
        shell, done = set_outline(before, corners=body.corners, height=body.height)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    answer = _walls_changed(rig, before, shell, done)
    await db.flush()
    return answer


@router.post("/rigs/{rig_id}/room-shell/outline/corners", status_code=201)
async def add_room_outline_corner(rig_id: int, body: CornerInsert, db: AsyncSession = Depends(get_db)):
    """Add a corner on the wall that leaves corner `after`: half way along it, or at `x`, `z`.

    Half way along, it changes no wall until it is moved. The corners after
    it move down one place; `index` is where the new one is.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    try:
        shell, done, index = insert_corner(before, body.after, x=body.x, z=body.z)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    answer = _walls_changed(rig, before, shell, done)
    await db.flush()
    return {**answer, "index": index}


@router.patch("/rigs/{rig_id}/room-shell/outline/corners/{index}")
async def move_room_outline_corner(
    rig_id: int, index: int, body: CornerMove, db: AsyncSession = Depends(get_db),
):
    """Move one corner of the stored room's walls. `index` is its place in the outline, from 0.

    A box room's corners are its four, from upstage stage right clockwise
    seen from above; moving one makes the room an outline. `index` in the
    answer is where the corner is afterwards, which differs only when the
    move turned the walls inside out and they were numbered clockwise again.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    try:
        shell, done, at = move_corner(before, index, x=body.x, z=body.z)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    answer = _walls_changed(rig, before, shell, done)
    await db.flush()
    return {**answer, "index": at}


@router.delete("/rigs/{rig_id}/room-shell/outline/corners/{index}")
async def delete_room_outline_corner(rig_id: int, index: int, db: AsyncSession = Depends(get_db)):
    """Take one corner out of the stored room's walls: its two walls become one. A room keeps at least three."""
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    try:
        shell, done = delete_corner(before, index)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    answer = _walls_changed(rig, before, shell, done)
    await db.flush()
    return {**answer, "index": index}


@router.patch("/rigs/{rig_id}/room-shell/{kind}/{index}")
async def edit_room_shell_item(
    rig_id: int,
    kind: str,
    index: int,
    body: ShellItemPatch,
    db: AsyncSession = Depends(get_db),
):
    """Rename, move, resize, raise or turn one raised area, overhead line or ring of the stored room.

    `kind` is the list it is stored in (`risers`, `truss_lines`, `truss_rings`)
    and `index` its place in that list, from 0. A moved line keeps its length
    and heading (services/room_scan/edit.py).

    The fixtures hung on a line or ring go with it unless `carry_fixtures` is
    false: shifted with a move, raised with a height, swung about a line's
    middle with a turn, spread along it with a length, moved out or in with a
    ring's radius (services/room_scan/carry.py). `fixtures_moved` lists them.
    Only their positions and headings change: no patch, mode or tag. An edit
    that would carry one out of the room and the 2 m round it is refused whole
    (422).

    A raised area takes the fixtures standing on it in the same way: shifted
    with a move, raised with its height or its `base_height`, kept at the
    same share of a footprint made bigger or smaller, and swung a quarter
    turn when its width and depth change places. `riser_kind` makes it a
    stage, a riser or a booth where it is in its list; `first_stage` in the
    answer is the place of the stage a suggestion would put floor lights on.

    A raised area that is moved, raised or given a quarter turn also takes
    the other raised areas standing on it (the middle of the footprint inside
    its footprint, the base within 0.1 m of its top), and the fixtures
    standing on those, as one piece. `items_moved` lists those areas, each
    with where it was and where it went. One that would end up outside the
    room and the 2 m round it, or above the ceiling, refuses the whole edit
    (422), as a fixture does. `carry_fixtures` false leaves them all.

    The scan's undo record is left alone, and nothing reaches a device. The
    room as it was is kept with what the edit carried, so both are undone
    together (POST .../room-shell/undo); an edit that changes nothing leaves
    no step behind.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    carry = body.carry_fixtures is not False
    try:
        shell, item = edit_item(before, kind, index, **body.model_dump(exclude={"carry_fixtures"}))
        done = edit_words(kind, before[kind][index], item)
        # Where the fixtures hung on it would go, worked out and checked before anything is written:
        # one that would leave the room refuses the whole edit, the truss's included.
        moves = carried_moves(before, kind, index, item, rig.fixtures) if carry and done is not None else []
        refuse_outside(shell, kind, item, moves)
        # The raised areas standing on a raised area go with it, and so do the fixtures standing on those.
        # All of it is read from the room as it was, and checked before anything is written.
        stacked = carried_areas(before, index, item) if kind == "risers" and carry and done is not None else []
        refuse_areas_outside(shell, item, stacked)
        for entry, theirs in zip(stacked, carried_area_moves(before, stacked, rig.fixtures)):
            refuse_outside(shell, kind, entry["item"], theirs)
            moves = moves + theirs
        shell = apply_areas(shell, stacked)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    if done is not None:
        apply_moves(rig.fixtures, moves)
        carried = [f"{len(stacked)} raised area{'' if len(stacked) == 1 else 's'}"] if stacked else []
        if moves:
            carried.append(f"{len(moves)} fixture{'' if len(moves) == 1 else 's'}")
        label = f"{done}, with {' and '.join(carried)}" if carried else done
        # A new object throughout: the column is plain JSON, so a change made in place is never written.
        rig.room_shell = shell
        # One step for the truss and what it carried: one undo takes both back.
        rig.room_shell_undo = push_step(rig.room_shell_undo, before, label, fixtures=moves, kind=kind)
        await db.flush()
        logger.info(
            "Room shell: rig %s '%s': %s %d: %s (%d fixtures and %d raised areas carried)",
            rig.id, rig.name, kind, index, done, len(moves), len(stacked),
        )
    return {
        "rig_id": rig.id, "kind": kind, "index": index, "item": item, "room_shell": shell,
        # For a raised area: what it now is, and which raised area is the room's first stage (or null).
        "riser_kind": item.get("kind") if kind == "risers" else None,
        "first_stage": first_stage(shell),
        "changed": done is not None,
        "undo": undo_summary(rig.room_shell_undo),
        "carry_fixtures": carry,
        "fixtures_moved": moves,
        # The other raised areas that stood on this one and went with it: {kind, index, name, from, to}.
        "items_moved": areas_report(stacked),
        "message": (
            carried_words(kind, item, len(moves), carry, areas=len(stacked))
            if done is not None else "Nothing was changed."
        ),
    }


@router.delete("/rigs/{rig_id}/room-shell/{kind}/{index}")
async def delete_room_shell_item(
    rig_id: int,
    kind: str,
    index: int,
    db: AsyncSession = Depends(get_db),
):
    """Take one raised area, overhead line or ring out of the stored room.

    The items after it move up one place. No fixture is moved: one that hung
    on a deleted truss stays where it is. POST .../room-shell/undo brings it
    back, to the place in its list it had.
    """
    rig = await _rig(db, rig_id)
    _not_during_locate(rig, "edit the room")
    before = rig.room_shell
    try:
        shell, removed = delete_item(before, kind, index)
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    name = item_name(kind, removed)
    rig.room_shell = shell
    rig.room_shell_undo = push_step(rig.room_shell_undo, before, f"{name} deleted")
    await db.flush()
    logger.info("Room shell: rig %s '%s': %s %d deleted (%s)", rig.id, rig.name, kind, index, name)
    return {
        "rig_id": rig.id,
        "kind": kind,
        "index": index,
        "removed": removed,
        "room_shell": shell,
        "undo": undo_summary(rig.room_shell_undo),
        "message": f"{name} was taken out of the stored room. No fixture was moved.",
    }


# Declared before the route that adds to a list: "undo" is not a list of the room.
@router.get("/rigs/{rig_id}/room-shell/undo")
async def preview_room_shell_undo(rig_id: int, db: AsyncSession = Depends(get_db)):
    """How many edits to the stored room can be undone, and what the next undo takes back. Writes nothing."""
    rig = await _rig(db, rig_id)
    return {"rig_id": rig.id, **undo_summary(rig.room_shell_undo)}


@router.post("/rigs/{rig_id}/room-shell/undo")
async def undo_room_shell_edit(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Take back the latest edit made to the stored room by hand: one edit for each call.

    The whole room goes back to what it was before that edit: a deleted item
    is in its old place in its list, a renamed one has its old name, and the
    hanging heights are what they were. The fixtures that edit carried with a
    truss go back to where they hung (`fixtures_restored`), except one that
    has been moved since, which is left alone and listed with the reason
    (`fixtures_skipped`). No other fixture is moved, and the scan's own
    undo record (POST .../room-scan/undo) is left alone. An undo cannot itself
    be undone. `outside` lists what the walls, as they are again, leave
    outside them: an undone change to the walls changes that.
    """
    rig = await _rig_with_fixtures(db, rig_id)
    _not_during_locate(rig, "undo the room edit")
    record, step = pop_step(rig.room_shell_undo)
    if step is None:
        raise HTTPException(status_code=409, detail="There is no edit to the room left to undo.")
    rig.room_shell = step["shell"]
    rig.room_shell_undo = record
    # The fixtures the edit carried with its truss go back with it.
    restored, skipped = put_back(rig.fixtures, step.get("fixtures"))
    await db.flush()
    label = step.get("label") if isinstance(step.get("label"), str) else ""
    logger.info(
        "Room shell: rig %s '%s': undone: %s (%d fixtures put back, %d left alone)",
        rig.id, rig.name, label, len(restored), len(skipped),
    )
    return {
        "rig_id": rig.id,
        "undone": label,
        "room_shell": step["shell"],
        "undo": undo_summary(record),
        "fixtures_restored": restored,
        "fixtures_skipped": skipped,
        # After the fixtures are back: one that was carried outside the walls is no longer there.
        "outside": outside_report(step["shell"], rig.fixtures),
        "message": (
            (f"Undone: {label}. " if label else "The last room edit was undone. ")
            + put_back_words(len(restored), len(skipped), step.get("kind"))
        ),
    }


@router.post("/rigs/{rig_id}/room-shell/{kind}", status_code=201)
async def add_room_shell_item(
    rig_id: int,
    kind: str,
    body: ShellItemAdd,
    db: AsyncSession = Depends(get_db),
):
    """Put a raised area, overhead line or ring into the stored room by hand.

    `kind` is the list it goes in (`risers`, `truss_lines`, `truss_rings`); it
    goes at the end, so nothing else changes place. It is marked as added by
    hand, not as the scan's (`added_by_hand`). No fixture is moved and nothing
    reaches a device. POST .../room-shell/undo takes it out again.
    """
    rig = await _rig(db, rig_id)
    _not_during_locate(rig, "add to the room")
    before = rig.room_shell
    try:
        shell, item, index = add_item(before, kind, **body.model_dump())
    except ShellEditError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    name = item_name(kind, item)
    rig.room_shell = shell
    rig.room_shell_undo = push_step(rig.room_shell_undo, before, f"{name} added")
    await db.flush()
    logger.info("Room shell: rig %s '%s': %s %d added (%s)", rig.id, rig.name, kind, index, name)
    return {
        "rig_id": rig.id,
        "kind": kind,
        "index": index,
        "item": item,
        "room_shell": shell,
        "undo": undo_summary(rig.room_shell_undo),
        "message": f"{name} was added to the stored room as a {KINDS[kind]}. No fixture was moved.",
    }
