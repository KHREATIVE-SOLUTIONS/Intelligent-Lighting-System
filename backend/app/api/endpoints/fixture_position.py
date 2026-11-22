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
from typing import Optional

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
    scanned room is often wider than the stage the rig was laid out on.
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

    limit_x, limit_z, top = position_limits(rig)
    rf.position_x = round(max(-limit_x, min(limit_x, body.position_x)), 3)
    rf.position_z = round(max(-limit_z, min(limit_z, body.position_z)), 3)
    if body.position_y is not None:
        rf.position_y = round(max(0.0, min(top, body.position_y)), 3)
    # A person put it here: the guess flag comes off, as it does for a tap.
    rf.tags = with_position_source(rf.tags, SOURCE_TAP, confirmed=True)

    await db.flush()
    await db.refresh(rf)
    return rf
