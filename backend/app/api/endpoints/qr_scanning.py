"""
QR Code / NFC Scanning Endpoints
==================================

API endpoints for scanning QR codes on fixtures and generating
labels for fixture identification.
"""

import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture

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
            "rig_fixture_id": existing.id,
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
        "rig_fixture_id": rf.id,
        "dmx_address": rf.dmx_address,
        "message": f"Added {fixture.model} at address {rf.dmx_address}",
    }


@router.get("/fixtures/{fixture_id}/qr-code")
async def generate_qr_code(
    fixture_id: int,
    size: int = Query(default=200, ge=50, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Generate a QR code image for a fixture."""
    result = await db.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    qr_data = json.dumps({
        "fixture_id": fixture.id,
        "manufacturer": fixture.manufacturer,
        "model": fixture.model,
    })

    # Try to generate QR code (requires qrcode library)
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        return StreamingResponse(buf, media_type="image/png")
    except ImportError:
        # qrcode library not installed - return JSON data instead
        return {
            "qr_data": qr_data,
            "message": "Install 'qrcode' package to generate QR code images",
        }


@router.get("/rigs/{rig_id}/labels/pdf")
async def generate_label_sheet(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate a printable label sheet for all fixtures in a rig."""
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

    # Return fixture label data (PDF generation requires reportlab)
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

    return {
        "rig_name": rig.name,
        "labels": labels,
        "total": len(labels),
        "message": "Label data generated. Install 'reportlab' for PDF output.",
    }
