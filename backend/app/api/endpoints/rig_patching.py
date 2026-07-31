"""
Rig Patching Endpoints
=======================

API endpoints for DMX auto-patching, conflict detection, and
address management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import FixtureMode
from app.services.rig.patching_service import PatchingService
from app.services.rig.programming_audit import build_programming_audit

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_rig_fixtures_with_channels(rig_id: int, db: AsyncSession):
    """Load rig fixtures with their mode channel counts."""
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(
            selectinload(RigFixture.fixture),
            selectinload(RigFixture.mode).selectinload(FixtureMode.channels),
        )
    )
    rig_fixtures = result.scalars().all()

    fixtures_data = []
    for rf in rig_fixtures:
        channel_count = 16  # Default fallback
        if rf.mode:
            channel_count = rf.mode.channel_count

        fixtures_data.append({
            "id": rf.id,
            "universe": rf.universe or 0,
            "dmx_address": rf.dmx_address,
            "channel_count": channel_count,
            "is_address_locked": rf.is_address_locked,
            "name": rf.name,
            "fixture_type": (
                rf.fixture.fixture_type.value
                if rf.fixture and getattr(rf.fixture, "fixture_type", None)
                else "other"
            ),
            "has_mode": rf.mode is not None,
            "mode_name": rf.mode.name if rf.mode else None,
            "channel_types": [
                str(ch.channel_type.value if getattr(ch, "channel_type", None) else "other")
                for ch in (rf.mode.channels if rf.mode else [])
            ],
        })

    return rig, rig_fixtures, fixtures_data


@router.post("/{rig_id}/auto-patch")
async def auto_patch_rig(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Auto-assign DMX addresses for all unlocked fixtures in a rig.

    Respects locked fixtures and universe boundaries (512ch max).
    """
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)

    locked_ids = {f["id"] for f in fixtures_data if f["is_address_locked"]}
    patched = PatchingService.auto_patch(fixtures_data, locked_ids)

    # Update database
    patched_map = {f["id"]: f for f in patched}
    updated_count = 0
    for rf in rig_fixtures:
        p = patched_map.get(rf.id)
        if p and not rf.is_address_locked:
            if rf.universe != p["universe"] or rf.dmx_address != p["dmx_address"]:
                rf.universe = p["universe"]
                rf.dmx_address = p["dmx_address"]
                updated_count += 1

    await db.flush()

    return {
        "message": f"Auto-patched {updated_count} fixtures",
        "rig_id": rig_id,
        "updated_count": updated_count,
        "fixtures": patched,
    }


@router.get("/{rig_id}/patch-conflicts")
async def get_patch_conflicts(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detect DMX address conflicts in a rig."""
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)
    conflicts = PatchingService.find_conflicts(fixtures_data)

    return {
        "rig_id": rig_id,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


@router.get("/{rig_id}/next-address")
async def get_next_available_address(
    rig_id: int,
    universe: int = Query(default=0, ge=0, le=15),
    channel_count: int = Query(default=16, ge=1, le=512),
    db: AsyncSession = Depends(get_db),
):
    """Get the next available DMX address in a universe."""
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)

    # Build occupied ranges for the specified universe
    occupied = []
    for f in fixtures_data:
        if f["universe"] == universe:
            start = f["dmx_address"]
            end = start + f["channel_count"] - 1
            occupied.append((start, end))

    address = PatchingService.get_next_address(occupied, channel_count)

    if address is None:
        return {
            "universe": universe,
            "address": None,
            "message": f"No space for {channel_count} channels in universe {universe}",
        }

    return {
        "universe": universe,
        "address": address,
        "channel_count": channel_count,
    }


@router.get("/{rig_id}/programming-audit")
async def get_programming_audit(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Run a professional programming-practices audit on a rig patch."""
    _, _, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)
    return build_programming_audit(fixtures_data)
