"""
Stage Plot Underlay Endpoints
=============================

A stage plot (an image of the venue's plot, or a photo of it) kept with a rig
and drawn under the fixtures in the 2D plan, so the operator can drag the
guessed fixtures onto where the plot says they hang. docs/STAGE_PLOT.md.

POST   /api/rigs/{rig_id}/stage-plot              upload a PNG, JPEG or WebP (replaces one, clears its calibration)
GET    /api/rigs/{rig_id}/stage-plot              the image itself
GET    /api/rigs/{rig_id}/stage-plot/info         what is stored: size, type, calibration and transform
DELETE /api/rigs/{rig_id}/stage-plot              take the underlay off (nothing else)
PUT    /api/rigs/{rig_id}/stage-plot/calibration  two points, the metres between them, the origin,
                                                  rotation and opacity; answers with the transform

The type is read from the file's first bytes. A PDF is refused with a 415: no
PDF renderer is a dependency of this product, so the operator is asked to
export the page as an image. The image is kept in its own table, so nothing
in the rig changes: not its fixtures, its room, nor its `updated_at`. Nothing
here reaches a device.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.rig import Rig
from app.models.stage_plot import RigStagePlot
from app.services.stage_plot import (
    IMAGE_TYPES, MAX_STAGE_PLOT_BYTES, PDF, Calibration, StagePlotError, calibration_dict, image_size, sniff,
    transform,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DOC = "docs/STAGE_PLOT.md"
PDF_REFUSED = (
    "A PDF stage plot cannot be read here: no PDF renderer is installed. "
    "Export the page as a PNG or JPEG image (or take a screenshot of it) and upload that."
)
NOT_AN_IMAGE = "The file is not a PNG, JPEG or WebP image. Export the stage plot as one of those and upload that."
NO_PLOT = "This rig has no stage plot. Upload one first."

# Every column but the image itself: what a reader of the info needs.
_INFO_COLUMNS = (
    RigStagePlot.rig_id, RigStagePlot.filename, RigStagePlot.content_type, RigStagePlot.byte_size,
    RigStagePlot.width_px, RigStagePlot.height_px, RigStagePlot.calibration, RigStagePlot.uploaded_at,
)


async def _require_rig(db: AsyncSession, rig_id: int) -> None:
    found = (await db.execute(select(Rig.id).where(Rig.id == rig_id))).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail="Rig not found")


def _info(row: Any) -> Dict[str, Any]:
    stored = row.calibration or None
    return {
        "rig_id": row.rig_id,
        "present": True,
        "filename": row.filename,
        "content_type": row.content_type,
        "byte_size": row.byte_size,
        "width_px": row.width_px,
        "height_px": row.height_px,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "calibration": stored["input"] if stored else None,
        "transform": stored["transform"] if stored else None,
        "operator_guide": DOC,
    }


async def _info_row(db: AsyncSession, rig_id: int) -> Optional[Any]:
    return (await db.execute(select(*_INFO_COLUMNS).where(RigStagePlot.rig_id == rig_id))).one_or_none()


@router.post("/rigs/{rig_id}/stage-plot", status_code=201)
async def upload_stage_plot(
    rig_id: int,
    file: UploadFile = File(..., description="The stage plot as a PNG, JPEG or WebP image"),
    db: AsyncSession = Depends(get_db),
):
    """Store a stage plot image with the rig, replacing any before it (and its calibration)."""
    await _require_rig(db, rig_id)
    content = await file.read(MAX_STAGE_PLOT_BYTES + 1)
    if len(content) > MAX_STAGE_PLOT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file is larger than {MAX_STAGE_PLOT_BYTES // (1024 * 1024)} MB. Export it at a lower resolution.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty.")
    kind = sniff(content)
    if kind == PDF:
        raise HTTPException(status_code=415, detail=PDF_REFUSED)
    if kind not in IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=NOT_AN_IMAGE)
    try:
        width, height = image_size(content, kind)
    except StagePlotError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = (file.filename or "")[:255] or None
    # Replaced whole: the calibration was of the image before.
    await db.execute(delete(RigStagePlot).where(RigStagePlot.rig_id == rig_id))
    db.add(RigStagePlot(
        rig_id=rig_id, filename=filename, content_type=kind, byte_size=len(content),
        width_px=width, height_px=height, data=content, calibration=None,
    ))
    await db.flush()
    logger.info("Stage plot: rig %s %s (%s, %dx%d, %d bytes)", rig_id, filename, kind, width, height, len(content))
    return _info(await _info_row(db, rig_id))


@router.get("/rigs/{rig_id}/stage-plot")
async def get_stage_plot(rig_id: int, db: AsyncSession = Depends(get_db)):
    """The stored image, as it was uploaded."""
    await _require_rig(db, rig_id)
    row = (await db.execute(
        select(RigStagePlot.data, RigStagePlot.content_type).where(RigStagePlot.rig_id == rig_id)
    )).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=NO_PLOT)
    # The image is behind the operator's token: no shared cache keeps it.
    return Response(content=row.data, media_type=row.content_type, headers={"Cache-Control": "no-store"})


@router.get("/rigs/{rig_id}/stage-plot/info")
async def get_stage_plot_info(rig_id: int, db: AsyncSession = Depends(get_db)):
    """What is stored, without the image. `present` is false where the rig has no stage plot."""
    await _require_rig(db, rig_id)
    row = await _info_row(db, rig_id)
    if row is None:
        return {"rig_id": rig_id, "present": False, "operator_guide": DOC}
    return _info(row)


@router.delete("/rigs/{rig_id}/stage-plot")
async def delete_stage_plot(rig_id: int, db: AsyncSession = Depends(get_db)):
    """Take the stage plot off the rig. Nothing else changes."""
    await _require_rig(db, rig_id)
    result = await db.execute(delete(RigStagePlot).where(RigStagePlot.rig_id == rig_id))
    await db.flush()
    return {"rig_id": rig_id, "removed": bool(result.rowcount)}


class ImagePoint(BaseModel):
    """A point on the image, in its pixels: x to the right, y down, from the top-left corner."""
    # Not held to finite numbers here: a refusal by FastAPI of an infinity
    # fails to answer (see room_scan.py). services/stage_plot.py refuses it in a sentence.
    x: float
    y: float


class StagePlotCalibration(BaseModel):
    point_a: ImagePoint
    point_b: ImagePoint
    distance_m: float
    origin: ImagePoint
    rotation_deg: float = 0.0
    opacity: float = 0.5


@router.put("/rigs/{rig_id}/stage-plot/calibration")
async def calibrate_stage_plot(rig_id: int, body: StagePlotCalibration, db: AsyncSession = Depends(get_db)):
    """Store how the stage plot lies on the room, and answer with the image-to-room transform."""
    await _require_rig(db, rig_id)
    row = (await db.execute(select(RigStagePlot).where(RigStagePlot.rig_id == rig_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=NO_PLOT)
    calibration = Calibration(
        point_a=(body.point_a.x, body.point_a.y), point_b=(body.point_b.x, body.point_b.y),
        distance_m=body.distance_m, origin=(body.origin.x, body.origin.y),
        rotation_deg=body.rotation_deg, opacity=body.opacity,
    )
    try:
        stored = {"input": calibration_dict(calibration), "transform": transform(calibration)}
    except StagePlotError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # A new dict: the column is plain JSON, so a change made in place is never written.
    row.calibration = stored
    await db.flush()
    return {"rig_id": rig_id, "calibration": stored["input"], "transform": stored["transform"]}
