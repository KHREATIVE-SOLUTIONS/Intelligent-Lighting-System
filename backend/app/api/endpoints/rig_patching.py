"""
Rig Patching Endpoints
=======================

API endpoints for DMX auto-patching, conflict detection, and
address management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import FixtureMode
from app.services.rig.patching_service import PatchingService

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_rig_fixtures_with_channels(rig_id: int, db: Session):
    """Load rig fixtures with their mode channel counts."""
    rig = db.query(Rig).filter(Rig.id == rig_id).first()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    rig_fixtures = (
        db.query(RigFixture)
        .filter(RigFixture.rig_id == rig_id)
        .options(joinedload(RigFixture.mode))
        .all()
    )

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
        })

    return rig, rig_fixtures, fixtures_data


@router.post("/{rig_id}/auto-patch")
async def auto_patch_rig(
    rig_id: int,
    db: Session = Depends(get_db),
):
    """Auto-assign DMX addresses for all unlocked fixtures in a rig.

    Respects locked fixtures and universe boundaries (512ch max).
    """
    rig, rig_fixtures, fixtures_data = _get_rig_fixtures_with_channels(rig_id, db)

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

    db.commit()

    return {
        "message": f"Auto-patched {updated_count} fixtures",
        "rig_id": rig_id,
        "updated_count": updated_count,
        "fixtures": patched,
    }


@router.get("/{rig_id}/patch-conflicts")
async def get_patch_conflicts(
    rig_id: int,
    db: Session = Depends(get_db),
):
    """Detect DMX address conflicts in a rig."""
    rig, rig_fixtures, fixtures_data = _get_rig_fixtures_with_channels(rig_id, db)
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
    db: Session = Depends(get_db),
):
    """Get the next available DMX address in a universe."""
    rig, rig_fixtures, fixtures_data = _get_rig_fixtures_with_channels(rig_id, db)

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
