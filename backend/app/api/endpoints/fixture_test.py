"""
Fixture Test Endpoints
=======================

API endpoints for live fixture testing: identify, color cycle,
movement test, and manual channel control.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import FixtureMode, FixtureChannel
from app.services.fixture_test.fixture_test_service import FixtureTestService

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared service instance (initialized lazily with DMX controller)
_test_service: Optional[FixtureTestService] = None


def get_test_service(request: Request) -> FixtureTestService:
    global _test_service
    if _test_service is None:
        dmx = getattr(request.app.state, "dmx_controller", None)
        if dmx is None:
            raise HTTPException(
                status_code=503,
                detail="DMX controller not available",
            )
        _test_service = FixtureTestService(dmx)
    return _test_service


async def _get_fixture_test_context(rig_id: int, fixture_id: int, db: AsyncSession):
    """Load a rig fixture with its mode channels for testing."""
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.id == fixture_id)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
        .limit(1)
    )
    rf = result.scalars().first()
    if not rf:
        raise HTTPException(status_code=404, detail="Rig fixture not found")

    if not rf.mode:
        raise HTTPException(
            status_code=400,
            detail="Fixture has no mode assigned - cannot determine channel layout",
        )

    return rf


@router.post("/rigs/{rig_id}/fixtures/{fixture_id}/test")
async def test_fixture(
    rig_id: int,
    fixture_id: int,
    test_type: str = Query(default="identify", regex="^(identify|color_cycle|movement|full)$"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Run a test on a single fixture."""
    service = get_test_service(request)
    rf = await _get_fixture_test_context(rig_id, fixture_id, db)

    ch_map = service._build_channel_map(rf.mode.channels)
    channel_count = rf.mode.channel_count

    await service.run_test(
        rig_fixture_id=rf.id,
        universe=rf.universe or 0,
        base_address=rf.dmx_address,
        ch_map=ch_map,
        channel_count=channel_count,
        test_type=test_type,
    )

    return {
        "message": f"Started {test_type} test",
        "fixture_id": rf.id,
        "fixture_name": rf.name or f"Fixture @ {rf.dmx_address}",
        "test_type": test_type,
    }


@router.post("/rigs/{rig_id}/fixtures/{fixture_id}/test/stop")
async def stop_fixture_test(
    rig_id: int,
    fixture_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Stop an active test on a fixture."""
    service = get_test_service(request)

    # Validate fixture exists
    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.id == fixture_id)
        .limit(1)
    )
    rf = result.scalars().first()
    if not rf:
        raise HTTPException(status_code=404, detail="Rig fixture not found")

    await service.stop_test(rf.id)
    return {"message": "Test stopped", "fixture_id": rf.id}


@router.post("/rigs/{rig_id}/fixtures/{fixture_id}/set-channels")
async def set_fixture_channels(
    rig_id: int,
    fixture_id: int,
    channel_values: Dict[str, int],
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Set specific DMX channel values on a fixture (live fader control).

    Body: {"0": 255, "5": 128} where keys are 0-indexed channel offsets.
    """
    service = get_test_service(request)

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.id == fixture_id)
        .limit(1)
    )
    rf = result.scalars().first()
    if not rf:
        raise HTTPException(status_code=404, detail="Rig fixture not found")

    # Convert string keys to int
    int_values = {int(k): max(0, min(255, v)) for k, v in channel_values.items()}

    await service.set_channels(
        universe=rf.universe or 0,
        base_address=rf.dmx_address,
        channel_values=int_values,
    )

    return {"message": "Channels set", "fixture_id": rf.id, "values": int_values}


@router.post("/rigs/{rig_id}/test-all")
async def test_all_fixtures(
    rig_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Run sequential identify test on all fixtures in a rig."""
    service = get_test_service(request)

    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.is_active == True)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
    )
    rig_fixtures = result.scalars().all()

    if not rig_fixtures:
        return {"message": "No active fixtures to test", "tested": 0}

    tested = 0
    for rf in rig_fixtures:
        if not rf.mode:
            continue
        ch_map = service._build_channel_map(rf.mode.channels)
        await service.run_test(
            rig_fixture_id=rf.id,
            universe=rf.universe or 0,
            base_address=rf.dmx_address,
            ch_map=ch_map,
            channel_count=rf.mode.channel_count,
            test_type="identify",
        )
        tested += 1

    return {
        "message": f"Started identify test on {tested} fixtures",
        "rig_id": rig_id,
        "tested": tested,
    }


@router.post("/rigs/{rig_id}/test-all/stop")
async def stop_all_tests(
    rig_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Stop all active fixture tests in a rig."""
    service = get_test_service(request)

    result = await db.execute(
        select(RigFixture).where(RigFixture.rig_id == rig_id)
    )
    rig_fixtures = result.scalars().all()

    stopped = 0
    for rf in rig_fixtures:
        if rf.id in service.active_tests:
            await service.stop_test(rf.id)
            stopped += 1

    return {"message": f"Stopped {stopped} tests", "stopped": stopped}
