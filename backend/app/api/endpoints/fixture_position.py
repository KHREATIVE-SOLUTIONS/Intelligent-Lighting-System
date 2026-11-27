"""
Fixture Position Endpoint
=========================

PUT /api/rigs/{rig_id}/fixtures/{fixture_id}/position is what dragging a
fixture in the 3D view saves through. It differs from the plain fixture update
in one way that matters: a person put the fixture there, so the position stops
being a guess. Its tags become `position_source:tap` with no
`position_unconfirmed`, exactly as a tap in flash-and-tap leaves them
(FLASH_AND_TAP.md), and from then on a room scan, a row fit and a room-scan
undo all leave it alone.

The layout view's drag does not come through here. It saves through
batch-update, which leaves tags as they are, and its undo and redo write
through the same route; confirming there would confirm every fixture an undo
touched.

Nothing here reaches a device: a stored position changes, no DMX is sent.
"""

import logging
import math
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.endpoints.room_scan import LOCATE_RUNNING, locate_running
from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.schemas.rig import RigFixtureResponse
from app.services.venue_import.apply import SOURCE_TAP, with_position_source

logger = logging.getLogger(__name__)
router = APIRouter()

# How far past the stage or the scanned room a fixture may be put. The same
# margin a tap in flash-and-tap is held to: a slip of the hand should not put
# a light in the car park.
OUTSIDE_MARGIN_M = 2.0


class DraggedPosition(BaseModel):
    """Where the fixture was put, in the rig's axes: metres, X across, Y up, -Z upstage."""
    position_x: float = Field(..., allow_inf_nan=False)
    position_z: float = Field(..., allow_inf_nan=False)
    # Left out, the fixture keeps its height: a drag is along the floor plan.
    position_y: Optional[float] = Field(default=None, allow_inf_nan=False)


def position_limits(rig: Rig) -> tuple:
    """(half width, half depth, top) a position is held inside, margin included.

    The larger of the stage and, where a room scan stored one, the room: a
    scanned room is often wider than the stage the rig was laid out on. A
    scanned room that is not a box is held to its outline as well
    (`hold_position`).
    """
    room = (rig.room_shell or {}).get("room") or {}

    def size(stage_value, key: str, default: float) -> float:
        values = [float(stage_value or default)]
        try:
            scanned = float(room.get(key))
            if math.isfinite(scanned) and scanned > 0:
                values.append(scanned)
        except (TypeError, ValueError):
            pass
        return max(values)

    return (
        size(rig.stage_width, "width", 10.0) / 2 + OUTSIDE_MARGIN_M,
        size(rig.stage_depth, "depth", 8.0) / 2 + OUTSIDE_MARGIN_M,
        size(rig.stage_height, "height", 6.0) + OUTSIDE_MARGIN_M,
    )


def position_outline(rig: Rig) -> Optional[List[Tuple[float, float]]]:
    """The floor outline of a scanned room that is not a box, as (x, z) corners, or None.

    None for a box room, a shell that is not a scan, and an outline that is not
    one: too few corners, a number missing, no area. The same rule as
    `roomOutline` in frontend/src/components/rig/previs/outline.ts, so the 3D
    view and this route agree on which rooms have one.
    """
    shell = rig.room_shell or {}
    if shell.get("source") != "scan":
        return None
    room = shell.get("room")
    if not isinstance(room, dict):
        return None

    def number(value) -> bool:
        # A bool is an int to Python, and is not a number here.
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    sizes = [room.get(key) for key in ("width", "depth", "height")]
    if not all(number(size) for size in sizes) or sizes[0] < 1 or sizes[1] < 1 or sizes[2] < 1.5:
        return None
    raw = room.get("outline")
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    outline: List[Tuple[float, float]] = []
    for corner in raw:
        if not isinstance(corner, dict) or not number(corner.get("x")) or not number(corner.get("z")):
            return None
        outline.append((float(corner["x"]), float(corner["z"])))
    twice_area = sum(
        a[0] * b[1] - b[0] * a[1] for a, b in zip(outline, outline[1:] + outline[:1])
    )
    if not abs(twice_area) / 2 >= 1:
        return None
    return outline


def inside_outline(outline: List[Tuple[float, float]], x: float, z: float) -> bool:
    """Whether a point on the plan is inside an outline."""
    inside = False
    for (ax, az), (bx, bz) in zip(outline, outline[1:] + outline[:1]):
        if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
            inside = not inside
    return inside


def hold_near_outline(
    outline: List[Tuple[float, float]], x: float, z: float, margin: float = OUTSIDE_MARGIN_M,
) -> Tuple[float, float]:
    """A point held to the room: inside the outline, or within `margin` of its walls.

    A point further out is brought straight towards the nearest point of the
    walls until it is `margin` from it. The notch of an L is outside the room,
    so a point deep in a notch comes back towards the notch's walls. Step for
    step what `holdNearOutline` in the 3D view's outline.ts does, the earlier
    wall winning a tie, so a fixture does not jump when a drag is saved.
    """
    if inside_outline(outline, x, z):
        return x, z
    nearest = None
    for (ax, az), (bx, bz) in zip(outline, outline[1:] + outline[:1]):
        dx, dz = bx - ax, bz - az
        length_sq = dx * dx + dz * dz
        along = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / length_sq)) if length_sq > 0 else 0.0
        px, pz = ax + along * dx, az + along * dz
        distance = math.hypot(x - px, z - pz)
        if nearest is None or distance < nearest[0]:
            nearest = (distance, px, pz)
    if nearest is None or not nearest[0] > margin:
        return x, z
    distance, px, pz = nearest
    share = margin / distance
    return px + (x - px) * share, pz + (z - pz) * share


def hold_position(rig: Rig, x: float, z: float) -> Tuple[float, float]:
    """Where on the plan a fixture put at (x, z) is stored, to the millimetre.

    In a scanned room that is not a box it is first brought to within the
    margin of the room's own walls, then held to the box: the same two steps,
    in the same order, as `clampPosition` in the 3D view's fixtureDrag.ts.
    """
    outline = position_outline(rig)
    if outline is not None:
        x, z = hold_near_outline(outline, x, z)
    limit_x, limit_z, _ = position_limits(rig)
    return round(max(-limit_x, min(limit_x, x)), 3), round(max(-limit_z, min(limit_z, z)), 3)


@router.put("/rigs/{rig_id}/fixtures/{fixture_id}/position", response_model=RigFixtureResponse)
async def set_fixture_position(
    rig_id: int,
    fixture_id: int,
    body: DraggedPosition,
    db: AsyncSession = Depends(get_db),
):
    """Store where a person dragged a fixture, and mark the position confirmed."""
    rig = (await db.execute(select(Rig).where(Rig.id == rig_id))).scalar_one_or_none()
    if rig is None:
        raise HTTPException(status_code=404, detail="Rig not found")
    rf = (await db.execute(
        select(RigFixture)
        .where(RigFixture.id == fixture_id, RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.fixture))
    )).scalar_one_or_none()
    if rf is None:
        raise HTTPException(status_code=404, detail="Rig fixture not found")
    # The walkthrough holds its own copy of each position and writes them as it
    # goes; a drag under it would be overwritten, or would move a row's end.
    if locate_running(rig_id):
        raise HTTPException(status_code=409, detail=LOCATE_RUNNING.format(then="move the fixture"))

    _, _, top = position_limits(rig)
    rf.position_x, rf.position_z = hold_position(rig, body.position_x, body.position_z)
    if body.position_y is not None:
        rf.position_y = round(max(0.0, min(top, body.position_y)), 3)
    # A person put it here: the guess flag comes off, as it does for a tap.
    rf.tags = with_position_source(rf.tags, SOURCE_TAP, confirmed=True)

    await db.flush()
    await db.refresh(rf)
    return rf
