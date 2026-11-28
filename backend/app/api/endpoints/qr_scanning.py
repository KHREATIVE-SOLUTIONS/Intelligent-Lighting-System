"""
QR Code / NFC Scanning Endpoints
==================================

API endpoints for scanning QR codes on fixtures and generating
labels for fixture identification.
"""

import asyncio
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture
from app.services import qr_encode
from app.services.label_sheet import Label, label_sheet_pdf

logger = logging.getLogger(__name__)
router = APIRouter()


class QRScanRequest(BaseModel):
    """Body for a QR code scan submitted by the scanner UI."""

    qr_data: str


@router.post("/rigs/{rig_id}/scan")
async def process_qr_scan(
    rig_id: int,
    scan_request: QRScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process a QR code scan and add/identify fixture in rig."""
    qr_data = scan_request.qr_data

    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    # Parse QR data - could be JSON or simple fixture ID
    fixture_id = None
    scan_data = {}

    try:
        parsed = json.loads(qr_data)
    except json.JSONDecodeError:
        parsed = None

    # json.loads accepts bare scalars, so a plain fixture ID parses as an int.
    if isinstance(parsed, dict):
        scan_data = parsed
        fixture_id = scan_data.get("fixture_id")
    else:
        try:
            fixture_id = int(qr_data)
        except ValueError:
            pass

    if not fixture_id:
        raise HTTPException(status_code=400, detail="Could not parse QR code data")

    # A printed label (generate_label_sheet) names its rig fixture. When that
    # rig fixture is in this rig, the fixture is already patched, however it got
    # there (UI, import, RDM, an earlier scan): say so and add nothing. Its
    # fixture_id must agree too: rig fixture ids are SQLite rowids and can be
    # reused after a delete, so a stale label could name some other fixture.
    label_rf_id = scan_data.get("rig_fixture_id")
    if not isinstance(label_rf_id, int) or isinstance(label_rf_id, bool):
        label_rf_id = None
    label_note = ""
    if label_rf_id is not None:
        # A query, not session.get(): it flushes first, so a delete earlier in
        # the session is seen.
        result = await db.execute(select(RigFixture).where(RigFixture.id == label_rf_id))
        labelled = result.scalar_one_or_none()
        if labelled is not None and labelled.rig_id == rig_id and labelled.fixture_id == fixture_id:
            if not labelled.qr_code_data:
                # Later scans match on the text as well.
                labelled.qr_code_data = qr_data
                await db.flush()
            return {
                "action": "identified",
                "already_patched": True,
                "matched_by": "rig_fixture_id",
                "rig_fixture_id": labelled.id,
                "universe": labelled.universe,
                "dmx_address": labelled.dmx_address,
                "message": (
                    f"{labelled.name or 'Fixture'} is already patched at "
                    f"{labelled.universe}.{labelled.dmx_address}: nothing added"
                ),
            }
        if labelled is None:
            label_note = f"The label's rig fixture {label_rf_id} no longer exists. "
        else:
            label_note = f"The label's rig fixture {label_rf_id} is not in this rig. "

    # Find or verify fixture
    result = await db.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()
    if not fixture:
        raise HTTPException(status_code=404, detail=f"Fixture ID {fixture_id} not found")

    # Check if already in rig
    result = await db.execute(
        select(RigFixture).where(
            RigFixture.rig_id == rig_id,
            RigFixture.fixture_id == fixture_id,
            RigFixture.qr_code_data == qr_data,
        ).limit(1)
    )
    existing = result.scalars().first()

    if existing:
        return {
            "action": "identified",
            "already_patched": True,
            "matched_by": "qr_code_data",
            "rig_fixture_id": existing.id,
            "universe": existing.universe,
            "dmx_address": existing.dmx_address,
            "message": f"Fixture already in rig at address {existing.dmx_address}",
        }

    # Find next available address
    from app.services.rig.patching_service import PatchingService
    result = await db.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))
    all_fixtures = result.scalars().all()
    occupied = [(rf.dmx_address, rf.dmx_address + 15) for rf in all_fixtures]
    next_addr = PatchingService.get_next_address(occupied, 16)

    if next_addr is None:
        next_addr = 1

    # Add to rig
    rf = RigFixture(
        rig_id=rig_id,
        fixture_id=fixture_id,
        name=scan_data.get("name") or f"{fixture.manufacturer} {fixture.model}",
        universe=0,
        dmx_address=next_addr,
        qr_code_data=qr_data,
        serial_number=scan_data.get("serial_number"),
        is_active=True,
    )
    db.add(rf)
    await db.flush()
    await db.refresh(rf)

    return {
        "action": "added",
        "already_patched": False,
        "rig_fixture_id": rf.id,
        "dmx_address": rf.dmx_address,
        "message": f"{label_note}Added {fixture.model} at address {rf.dmx_address}",
    }


@router.get("/fixtures/{fixture_id}/qr-code")
async def generate_qr_code(
    fixture_id: int,
    size: int = Query(default=200, ge=50, le=500),
    output: str = Query(default="png", alias="format", pattern="^(png|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """A QR code PNG for a fixture profile, drawn by app/services/qr_encode.py.

    The code holds `{"fixture_id", "manufacturer", "model"}`, which the scan
    route adds by fixture_id. `size` is the side in pixels, rounded down to a
    whole number of pixels a module (never below one) so every module is the
    same width. `?format=json` answers the code's text instead.
    """
    result = await db.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    qr_data = json.dumps({
        "fixture_id": fixture.id,
        "manufacturer": fixture.manufacturer,
        "model": fixture.model,
    })
    try:
        matrix = qr_encode.encode(qr_data, ecc="M")
    except ValueError:
        # Names too long for a version 10 code: the id alone still scans.
        qr_data = json.dumps({"fixture_id": fixture.id})
        matrix = qr_encode.encode(qr_data, ecc="M")

    if output == "json":
        return {
            "qr_data": qr_data,
            "message": "QR code text. Leave out ?format=json for the PNG.",
        }

    quiet = 4
    module_px = max(1, size // (len(matrix) + 2 * quiet))
    img = qr_encode.to_image(matrix, module_px=module_px, quiet=quiet)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="fixture_{fixture_id}_qr.png"'},
    )


@router.get("/rigs/{rig_id}/labels/pdf")
async def generate_label_sheet(
    rig_id: int,
    output: str = Query(default="pdf", alias="format", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """A printable label sheet for every fixture in a rig.

    A US Letter PDF laid out for Avery 5160 labels (app/services/label_sheet.py):
    each label has a QR code the scan route reads back, the fixture's name,
    number, universe.address and group. A rig with nothing patched gets a
    one-page PDF that says so. `?format=json` answers the label data instead.
    """
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.fixture))
        .order_by(RigFixture.universe, RigFixture.dmx_address)
    )
    fixtures = result.scalars().all()

    labels = []
    for rf in fixtures:
        fixture = rf.fixture
        labels.append({
            "name": rf.name or (f"{fixture.manufacturer} {fixture.model}" if fixture else "Unknown"),
            "universe": rf.universe,
            "dmx_address": rf.dmx_address,
            "fixture_number": rf.fixture_number,
            "group": rf.group_name,
            "qr_data": json.dumps({"fixture_id": rf.fixture_id, "rig_fixture_id": rf.id}),
        })

    if output == "json":
        return {
            "rig_name": rig.name,
            "labels": labels,
            "total": len(labels),
            "message": "Label data. Leave out ?format=json for the printable PDF.",
        }

    # Plain values only past this point: drawing runs off the event loop.
    sheet = [Label(**label) for label in labels]
    pdf = await asyncio.to_thread(label_sheet_pdf, rig.name, sheet)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rig_{rig_id}_labels.pdf"'},
    )
