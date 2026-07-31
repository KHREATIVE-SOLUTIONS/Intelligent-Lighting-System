"""
RDM Discovery Endpoints
========================

API endpoints for RDM auto-discovery of DMX fixtures.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.rdm_device import RDMDevice
from app.services.discovery.rdm_service import RDMDiscoveryService

logger = logging.getLogger(__name__)
router = APIRouter()

_rdm_service: Optional[RDMDiscoveryService] = None


def get_rdm_service() -> RDMDiscoveryService:
    global _rdm_service
    if _rdm_service is None:
        _rdm_service = RDMDiscoveryService()
    return _rdm_service


@router.post("/rdm/start")
async def start_rdm_discovery(
    port: Optional[str] = None,
    universes: str = "0",
):
    """Start RDM device discovery."""
    service = get_rdm_service()
    uni_list = [int(u.strip()) for u in universes.split(",")]
    result = await service.start_discovery(port=port, universes=uni_list)
    return result


@router.post("/rdm/stop")
async def stop_rdm_discovery():
    """Stop RDM discovery scan."""
    service = get_rdm_service()
    return await service.stop_discovery()


@router.get("/rdm/devices")
async def get_rdm_devices(db: AsyncSession = Depends(get_db)):
    """Get discovered RDM devices."""
    service = get_rdm_service()
    live_devices = service.get_discovered_devices()

    # Also return previously saved devices
    result = await db.execute(
        select(RDMDevice).order_by(RDMDevice.last_seen.desc())
    )
    saved = result.scalars().all()
    saved_list = [
        {
            "id": d.id,
            "uid": f"{d.uid_manufacturer}:{d.uid_device}",
            "manufacturer": d.manufacturer_label,
            "model": d.model_description,
            "label": d.device_label,
            "dmx_footprint": d.dmx_footprint,
            "dmx_address": d.dmx_address,
            "universe": d.universe,
            "is_imported": d.is_imported,
            "matched_fixture_id": d.matched_fixture_id,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in saved
    ]

    return {
        "scanning": service.is_scanning,
        "live_devices": live_devices,
        "saved_devices": saved_list,
    }


@router.post("/rdm/import")
async def import_rdm_devices(
    device_ids: List[int],
    rig_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Import discovered RDM devices into the rig."""
    from app.models.rig import Rig, RigFixture
    from app.models.fixture import Fixture, FixtureType

    imported = 0
    for device_id in device_ids:
        device_result = await db.execute(
            select(RDMDevice).where(RDMDevice.id == device_id)
        )
        device = device_result.scalar_one_or_none()
        if not device or device.is_imported:
            continue

        # Create or find fixture
        fixture = None
        if device.matched_fixture_id:
            fixture_result = await db.execute(
                select(Fixture).where(Fixture.id == device.matched_fixture_id)
            )
            fixture = fixture_result.scalar_one_or_none()

        if not fixture:
            fixture = Fixture(
                manufacturer=device.manufacturer_label or "RDM Device",
                model=device.model_description or f"UID {device.uid_manufacturer}:{device.uid_device}",
                fixture_type=FixtureType.OTHER,
                source="rdm",
            )
            db.add(fixture)
            await db.flush()

        # Add to rig if specified
        if rig_id:
            rig_result = await db.execute(select(Rig).where(Rig.id == rig_id))
            rig = rig_result.scalar_one_or_none()
            if rig:
                rf = RigFixture(
                    rig_id=rig.id,
                    fixture_id=fixture.id,
                    name=device.device_label or device.model_description,
                    universe=device.universe or 0,
                    dmx_address=device.dmx_address or 1,
                    is_active=True,
                )
                db.add(rf)

        device.is_imported = True
        device.matched_fixture_id = fixture.id
        imported += 1

    await db.flush()
    return {"imported": imported}


@router.get("/rdm/device/{uid}/identify")
async def identify_rdm_device(uid: str):
    """Send RDM identify command to a device."""
    service = get_rdm_service()
    return await service.identify_device(uid)
