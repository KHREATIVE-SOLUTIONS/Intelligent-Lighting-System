"""
Focus presets
=============

GET    /api/rigs/{rig_id}/focus-presets                     the computed table
GET    /api/rigs/{rig_id}/focus-presets.csv                 the same, as the handoff pack's CSV
POST   /api/rigs/{rig_id}/focus-presets/targets             add a custom target {name, x, y, z}
DELETE /api/rigs/{rig_id}/focus-presets/targets/{id}        remove one

Computing is read-only: nothing here sends DMX or moves a light, and there is
no preview route (a preview has to go through the output stage like any other
look). Adding or removing a custom target writes only `rigs.focus_targets`,
and leaves the rig's `updated_at` as it was. docs/FOCUS_PRESETS.md.
"""

from typing import Any, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.fixture import FixtureMode
from app.models.rig import Rig, RigFixture
from app.services.console_export.model import from_rig
from app.services.focus_presets.table import build_table, focus_csv, table_dict
from app.services.focus_presets.targets import TargetError, add_custom, remove_custom, stored_custom

router = APIRouter()

DOC = "docs/FOCUS_PRESETS.md"


class CustomTargetIn(BaseModel):
    name: Any = None
    x: Any = None
    y: Any = None
    z: Any = None


async def _rig(db: AsyncSession, rig_id: int) -> Rig:
    rig = (await db.execute(select(Rig).where(Rig.id == rig_id))).scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")
    return rig


async def _rig_and_rows(db: AsyncSession, rig_id: int) -> Tuple[Rig, List[RigFixture]]:
    rig = await _rig(db, rig_id)
    rows = (await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.fixture), selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
    )).scalars().all()
    return rig, list(rows)


@router.get("/rigs/{rig_id}/focus-presets")
async def get_focus_presets(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Every target against every moving head: pan and tilt in degrees and DMX, or why it cannot reach."""
    rig, rows = await _rig_and_rows(db, rig_id)
    out = table_dict(build_table(rig, rows, from_rig(rig, rows)))
    out["rig_id"] = rig.id
    out["custom_targets"] = stored_custom(rig.focus_targets)
    return out


@router.get("/rigs/{rig_id}/focus-presets.csv")
async def get_focus_presets_csv(rig_id: int, db: AsyncSession = Depends(get_db)):
    rig, rows = await _rig_and_rows(db, rig_id)
    export = from_rig(rig, rows)
    return Response(
        content=focus_csv(build_table(rig, rows, export)).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export.file_stem()}_focus-presets.csv"'},
    )


async def _store(db: AsyncSession, rig: Rig, targets: list) -> None:
    # updated_at given as itself, so the column's onupdate does not move it.
    await db.execute(
        update(Rig).where(Rig.id == rig.id).values(focus_targets=targets, updated_at=Rig.updated_at)
    )
    await db.commit()


@router.post("/rigs/{rig_id}/focus-presets/targets", status_code=201)
async def add_focus_target(rig_id: int, body: CustomTargetIn, db: AsyncSession = Depends(get_db)):
    """Add a point to focus on: a name and x, y, z in metres (stage axes, y up from the floor)."""
    rig = await _rig(db, rig_id)
    try:
        targets, item = add_custom(rig.focus_targets, body.name, body.x, body.y, body.z)
    except TargetError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _store(db, rig, targets)
    return {"target": item, "custom_targets": targets, "operator_guide": DOC}


@router.delete("/rigs/{rig_id}/focus-presets/targets/{target_id}")
async def remove_focus_target(rig_id: int, target_id: int, db: AsyncSession = Depends(get_db)):
    rig = await _rig(db, rig_id)
    targets = remove_custom(rig.focus_targets, target_id)
    if targets is None:
        raise HTTPException(status_code=404, detail="That rig has no custom target with that id")
    await _store(db, rig, targets)
    return {"removed": target_id, "custom_targets": targets, "operator_guide": DOC}
