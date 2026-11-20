"""
Per-Fixture Setup Check Endpoints
=================================

The patch screen's "is this one right?" for a single fixture: light it, show
it each colour, nudge its pan and tilt, and record what the operator saw.

The walkthrough (rig_identify) answers "which light is which" for a whole rig
in order. This answers "is this light set up correctly" for whichever one the
operator points at, in whatever order they like. Both hold a fixture steadily
lit with the show parked, and each releases the other before it starts.

Answers are written to the fixture's tags (``setup:<check>:ok`` or ``:fail``),
so they survive a restart and travel with the rig. A flash that fails also sets
the walkthrough's ``identify:no-response`` mark, and one that passes clears it:
they are the same finding.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.endpoints import rig_identify
from app.api.endpoints.fixture_test import get_test_service
from app.db.database import get_db
from app.models.fixture import FixtureMode
from app.models.rig import Rig, RigFixture
from app.services.fixture_test import setup_check
from app.services.fixture_test.setup_check import setup_hold

logger = logging.getLogger(__name__)
router = APIRouter()


class ShowLook(BaseModel):
    check: str
    look: str


class CheckResult(BaseModel):
    check: str
    # True: it did what it should. False: it did not. None: forget the answer.
    passed: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_rig(rig_id: int, db: AsyncSession) -> Rig:
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")
    return rig


async def _load_fixture(rig_id: int, fixture_id: int, db: AsyncSession) -> RigFixture:
    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.id == fixture_id)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
        .limit(1)
    )
    rf = result.scalars().first()
    if not rf:
        raise HTTPException(status_code=404, detail="Rig fixture not found")
    return rf


def _label(rf: RigFixture) -> str:
    return rf.name or f"Light at address {rf.dmx_address}"


def _channels(rf: RigFixture) -> List[Any]:
    return list(rf.mode.channels) if rf.mode else []


def _fixture_payload(rf: RigFixture, service: Any, dmx: Any) -> Dict[str, Any]:
    channels = _channels(rf)
    ch_map = service._build_channel_map(channels) if channels else {}
    channel_count = rf.mode.channel_count if rf.mode else 0
    results = setup_check.results_from_tags(rf.tags)

    shutter = next(
        (c for c in channels
         if setup_check.channel_type(c) == "shutter" and not getattr(c, "is_fine", False)),
        None,
    )
    checks = setup_check.capabilities(channels, ch_map)
    for entry in checks:
        entry["result"] = results[entry["check"]]

    return {
        "fixture_id": rf.id,
        "label": _label(rf),
        "universe": rf.universe or 0,
        "dmx_address": rf.dmx_address,
        "channel_count": channel_count,
        "has_shutter": shutter is not None,
        "shutter_open_value": (
            setup_check.shutter_open_value(shutter) if shutter is not None else None
        ),
        "no_response": rig_identify.NO_RESPONSE_TAG in (rf.tags or []),
        # Something outside the fixture that would keep it dark: the strobe
        # switch holding a strobe fixture off.
        "output_blocked_reason": setup_check.output_block_reason(
            dmx, rf.universe or 0, rf.dmx_address, channel_count),
        "checks": checks,
    }


def _state(rig_id: int, request: Request) -> Dict[str, Any]:
    dmx = getattr(request.app.state, "dmx_controller", None)
    hold = setup_hold.active(rig_id)
    active = setup_hold.state(hold)
    if active is not None and hold is not None:
        active["output_blocked_reason"] = setup_check.output_block_reason(
            dmx, hold.universe, hold.dmx_address, hold.channel_count)
    return {
        "rig_id": rig_id,
        "active": active,
        # Rig-wide: blackout latched or the grand master at zero.
        "output_blocked_reason": setup_check.output_block_reason(dmx),
        "hold_max_s": setup_check.HOLD_MAX_S,
        "heartbeat_timeout_s": setup_check.HOLD_IDLE_TIMEOUT_S,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/rigs/{rig_id}/setup-checks")
async def list_setup_checks(
    rig_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Every fixture in the rig: which checks it supports and what was recorded.

    Read-only. It lights nothing and creates no universe.
    """
    await _require_rig(rig_id, db)
    service = get_test_service(request)
    dmx = getattr(request.app.state, "dmx_controller", None)

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
        .order_by(RigFixture.universe, RigFixture.dmx_address, RigFixture.id)
    )
    state = _state(rig_id, request)
    state["fixtures"] = [
        _fixture_payload(rf, service, dmx) for rf in result.scalars().all()
    ]
    return state


@router.post("/rigs/{rig_id}/fixtures/{fixture_id}/setup-check/show")
async def show_look(
    rig_id: int,
    fixture_id: int,
    body: ShowLook,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Hold one look on one fixture, with the rest of the room dark.

    Steady, never blinking. Replaces whatever this or another fixture was
    holding; the show stays parked across the change.
    """
    service = get_test_service(request)
    await _require_rig(rig_id, db)
    rf = await _load_fixture(rig_id, fixture_id, db)

    channels = _channels(rf)
    ch_map = service._build_channel_map(channels) if channels else {}
    by_name = {entry["check"]: entry for entry in setup_check.capabilities(channels, ch_map)}
    entry = by_name.get(body.check)
    if entry is None:
        raise HTTPException(status_code=422, detail=f"Unknown check: {body.check}")
    if not entry["available"]:
        raise HTTPException(status_code=409, detail=entry["reason"])
    if body.look not in entry["looks"]:
        raise HTTPException(
            status_code=422,
            detail=f"'{body.look}' is not part of the {body.check} check for this light.",
        )

    level = int(round(255 * rig_identify._venue_intensity_cap(request.app.state)))
    if level <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "The venue intensity limit is set to zero, so a test light would not "
                "be visible. Raise it before checking a light."
            ),
        )

    universe = rf.universe or 0
    channel_count = rf.mode.channel_count
    dmx = getattr(request.app.state, "dmx_controller", None)
    blocked = setup_check.output_block_reason(dmx, universe, rf.dmx_address, channel_count)
    if blocked:
        # Lighting it anyway would leave the operator looking at a dark
        # fixture the app says is on, which reads as a dead light.
        raise HTTPException(status_code=409, detail=blocked)

    values = setup_check.look_values(channels, ch_map, channel_count, level, body.look)

    # A walkthrough owns the wire while it runs; it lets go before this takes it.
    for session in list(rig_identify._sessions.values()):
        await rig_identify._end_session(session, service)

    await setup_hold.show(
        service, request.app.state,
        rig_id=rig_id, fixture_id=rf.id, label=_label(rf),
        universe=universe, dmx_address=rf.dmx_address, channel_count=channel_count,
        values=values, check=body.check, look=body.look,
    )
    return _state(rig_id, request)


@router.post("/rigs/{rig_id}/setup-check/heartbeat")
async def heartbeat(rig_id: int, request: Request = None):
    """Keep the held light alive. Silence releases it and the show."""
    setup_hold.touch(rig_id)
    return _state(rig_id, request)


@router.post("/rigs/{rig_id}/setup-check/release")
async def release(rig_id: int, request: Request = None):
    """Fixture dark, show back on the wire.

    Releasing when nothing is held is not an error: the browser sends this on
    unload and may be racing the hold's own timeout.
    """
    released = await setup_hold.release(get_test_service(request), rig_id)
    state = _state(rig_id, request)
    state["released"] = released
    return state


@router.post("/rigs/{rig_id}/fixtures/{fixture_id}/setup-check/result")
async def record_result(
    rig_id: int,
    fixture_id: int,
    body: CheckResult,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Record what the operator saw for one check on one fixture."""
    if body.check not in setup_check.CHECKS:
        raise HTTPException(status_code=422, detail=f"Unknown check: {body.check}")
    service = get_test_service(request)
    rf = await _load_fixture(rig_id, fixture_id, db)

    tags = setup_check.tags_with_result(rf.tags, body.check, body.passed)
    if body.check == setup_check.CHECK_FLASH and body.passed is not None:
        # "It never lit" is the walkthrough's finding too; keep the two in step.
        tags = [t for t in tags if t != rig_identify.NO_RESPONSE_TAG]
        if not body.passed:
            tags.append(rig_identify.NO_RESPONSE_TAG)
    rf.tags = tags
    await db.commit()

    if body.passed is False:
        logger.warning(
            "Setup check: rig %s fixture %s (universe %s @ %s) failed its %s check",
            rig_id, rf.id, rf.universe, rf.dmx_address, body.check,
        )

    dmx = getattr(request.app.state, "dmx_controller", None)
    return _fixture_payload(rf, service, dmx)
