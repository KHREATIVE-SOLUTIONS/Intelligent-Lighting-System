"""
Flash-to-Identify Walkthrough
==============================

Contract §5. The owner does not know which light is which, so the box lights one
patched fixture at a time and they tap where it is on the floor plan. The rig gets
mapped with no DMX knowledge, and it doubles as a patch check: a fixture that never
lights is recorded as unresponsive rather than waved past.

Built on FixtureTestService - its channel map is the one that survived the
coarse/fine collision fix, and its ``active_tests`` registry is shared so the
existing /test/stop and /test-all/stop endpoints release a walkthrough hold too.
Those endpoints only cancel, so the hold blacks its own fixture out on
cancellation rather than trusting whoever cancelled it.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.endpoints.fixture_test import get_test_service
from app.db.database import get_db
from app.models.fixture import FixtureMode
from app.models.rig import Rig, RigFixture
from app.services.fixture_test.fixture_test_service import FixtureTestService

logger = logging.getLogger(__name__)
router = APIRouter()

# The fixture is held steadily lit, never blinked: a strobe is the one thing this
# walkthrough must not do, and a steady light is also the only one someone can
# point at while they walk the room.
FLASH_REASSERT_S = 1.0

# Nobody stares at one lamp for a minute and a half. Past this the hold releases
# itself and the operator is offered "flash it again", so a walked-away-from
# browser cannot leave a fixture latched at full.
FLASH_MAX_S = 90.0

# The browser heartbeats while the walkthrough is open; a gap this long means the
# tab is gone.
SESSION_IDLE_TIMEOUT_S = 30.0
WATCHDOG_TICK_S = 2.0

# Survives a restart, unlike the session, so "this one never lit" is still on the
# fixture when the owner comes back to fix its address.
NO_RESPONSE_TAG = "identify:no-response"

OUTCOME_PLACED = "placed"
OUTCOME_KEPT = "kept"
OUTCOME_NO_RESPONSE = "no_response"

# Channel types whose profile default is the fixture's own "no effect" position.
# A spot parked on a blackout gobo or a dark colour wheel slot is a light the
# owner would report as dead.
HOME_VALUE_TYPES = ("gobo", "gobo2", "color_wheel", "prism", "frost", "animation")
COLOR_TYPES = ("red", "green", "blue", "white")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class _Step:
    """One fixture's turn in the walkthrough."""

    fixture_id: int
    label: str
    universe: int
    dmx_address: int
    channel_count: int
    values: Dict[int, int]
    can_flash: bool
    blocked_reason: Optional[str]
    position_x: float
    position_y: float
    position_z: float
    outcome: Optional[str] = None


@dataclass
class _Session:
    session_id: str
    rig_id: int
    rig_name: str
    stage_width: float
    stage_depth: float
    flash_level: int
    steps: List[_Step]
    index: int = 0
    last_seen: float = field(default_factory=time.monotonic)
    released: bool = False
    hold_task: Optional[asyncio.Task] = None
    hold_step: Optional[_Step] = None
    watchdog_task: Optional[asyncio.Task] = None
    engine: Any = None
    dmx: Any = None
    # universe -> the levels the show was holding, or None when the walkthrough
    # created the universe itself and there was nothing to put back.
    parked_universes: Dict[int, Optional[List[int]]] = field(default_factory=dict)
    previous_dmx_callback: Optional[Callable] = None
    output_suspended: bool = False
    # Guards a step against being answered twice. Two taps that race each other
    # would otherwise both advance and skip the fixture in between.
    action_lock: Any = None

    @property
    def complete(self) -> bool:
        return self.index >= len(self.steps)

    @property
    def current(self) -> Optional[_Step]:
        return None if self.complete else self.steps[self.index]

    def touch(self) -> None:
        self.last_seen = time.monotonic()


# Process-wide: the walkthrough takes the show off the wire, so two of them at
# once would fight over the same universes.
_sessions: Dict[str, _Session] = {}


# ---------------------------------------------------------------------------
# Flash values
# ---------------------------------------------------------------------------


def _channel_type(channel: Any) -> str:
    ct = getattr(channel, "channel_type", None)
    return str(getattr(ct, "value", ct) or "other")


def _shutter_open_value(channel: Any) -> int:
    """The value that opens this shutter without putting it into strobe."""
    for entry in getattr(channel, "value_ranges", None) or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).lower()
        if any(word in name for word in ("strob", "puls", "random", "close")):
            continue
        if "open" in name or "no function" in name or "no func" in name:
            low = int(entry.get("min_value", 0))
            high = int(entry.get("max_value", 255))
            return max(0, min(255, (low + high) // 2))
    return 255


def _identify_values(channels: List[Any], ch_map: Dict[str, int], level: int) -> Dict[int, int]:
    """DMX offsets to hold while this fixture is the one being identified."""
    values: Dict[int, int] = {}

    if "dimmer" in ch_map:
        values[ch_map["dimmer"]] = level
    for color in COLOR_TYPES:
        if color in ch_map:
            values[ch_map[color]] = level

    for channel in channels:
        ctype = _channel_type(channel)
        offset = int(getattr(channel, "channel_number", 1)) - 1
        if getattr(channel, "is_fine", False):
            continue
        if ctype == "shutter":
            values[offset] = _shutter_open_value(channel)
        elif ctype == "strobe":
            # Explicitly parked off. A profile whose strobe channel happens to
            # come up hot is the hazard this endpoint exists to avoid.
            values[offset] = 0
        elif ctype in HOME_VALUE_TYPES:
            values[offset] = max(0, min(255, int(getattr(channel, "default_value", 0) or 0)))

    return values


def _venue_intensity_cap(app_state: Any) -> float:
    """The show's own audience intensity cap - identify never exceeds it."""
    engine = getattr(app_state, "effects_engine", None)
    config = getattr(engine, "config", None)
    try:
        cap = float(getattr(config, "audience_intensity_cap", 1.0))
    except (TypeError, ValueError):
        cap = 1.0
    return max(0.0, min(1.0, cap))


# ---------------------------------------------------------------------------
# Show output suspension
# ---------------------------------------------------------------------------


def _suspend_show_output(session: _Session, request: Request) -> None:
    """Take the running show off the wire for the walkthrough.

    The effects engine repaints every universe its rig occupies sixty times a
    second, so an identify write would be overwritten before the operator could
    look up - the control would appear to work and nothing would light. Detaching
    the engine's DMX callback and zeroing the universes leaves the room dark with
    one fixture lit, which is also the only state in which "which one is that?"
    has an answer.
    """
    engine = getattr(request.app.state, "effects_engine", None)
    if engine is not None and hasattr(engine, "set_dmx_callback"):
        session.engine = engine
        session.previous_dmx_callback = getattr(engine, "_dmx_callback", None)
        engine.set_dmx_callback(None)
        session.output_suspended = True

    dmx = getattr(request.app.state, "dmx_controller", None)
    if dmx is None:
        return
    session.dmx = dmx
    session.output_suspended = True

    # Not everything on the wire is repainted by the effects engine: house and
    # work lights, a hazer, a static look parked through /api/dmx. Those levels
    # are the operator's and are put back verbatim when the walkthrough ends.
    for universe in list(getattr(dmx, "universes", {}).keys()):
        session.parked_universes[universe] = list(dmx.universes[universe].data)
        dmx.universes[universe].data = [0] * 512
    for universe in {step.universe for step in session.steps if step.can_flash}:
        if universe not in session.parked_universes:
            session.parked_universes[universe] = None
        dmx.get_universe(universe).data = [0] * 512


def _resume_show_output(session: _Session) -> None:
    """Hand the universes back to the show, at the levels it left them."""
    if not session.output_suspended:
        return
    session.output_suspended = False
    engine = session.engine
    if engine is not None and hasattr(engine, "set_dmx_callback"):
        engine.set_dmx_callback(session.previous_dmx_callback)

    dmx = session.dmx
    if dmx is not None:
        for universe, data in session.parked_universes.items():
            if data is None:
                # Created for the walkthrough; it had no levels to lose.
                continue
            existing = getattr(dmx, "universes", {}).get(universe)
            if existing is not None:
                existing.data = list(data)

    session.parked_universes = {}
    session.dmx = None
    session.engine = None
    session.previous_dmx_callback = None


# ---------------------------------------------------------------------------
# Flash hold
# ---------------------------------------------------------------------------


async def _hold(service: FixtureTestService, step: _Step) -> None:
    """Hold one fixture lit until cancelled or timed out, then leave it dark."""
    try:
        deadline = time.monotonic() + FLASH_MAX_S
        while time.monotonic() < deadline:
            await service._set_fixture_channels(step.universe, step.dmx_address, step.values)
            await asyncio.sleep(FLASH_REASSERT_S)
    except asyncio.CancelledError:
        # The hold blacks itself out rather than trusting the canceller to do it.
        # FixtureTestService.stop_test - which /test/stop and /test-all/stop both
        # call, and which does not know a walkthrough exists - only cancels, so
        # without this the fixture stays latched at full while the app reports it
        # off. Mirrors the cleanup in FixtureTestService.run_test's own wrapper.
        await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)
        if service.active_tests.get(step.fixture_id) is asyncio.current_task():
            service.active_tests.pop(step.fixture_id, None)
        raise
    except Exception:
        logger.exception("Identify hold failed - blacking the fixture out")

    await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)
    current = asyncio.current_task()
    if service.active_tests.get(step.fixture_id) is current:
        service.active_tests.pop(step.fixture_id, None)


async def _stop_flash(session: _Session, service: FixtureTestService) -> None:
    """Cancel the hold and black the fixture out. Safe to call repeatedly."""
    task, step = session.hold_task, session.hold_step
    session.hold_task = None
    session.hold_step = None
    if task is None or step is None:
        return

    # Registered under the fixture id, so the existing fixture-test stop endpoints
    # release this hold too; drop the registration only if it is still ours.
    if service.active_tests.get(step.fixture_id) is task:
        service.active_tests.pop(step.fixture_id, None)
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # pragma: no cover - a failed hold must not block release
        logger.exception("Identify hold ended badly")

    # The cancelled task cannot do this itself, and a latched fixture is the one
    # outcome this walkthrough is not allowed to leave behind.
    await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)


async def _start_flash(session: _Session, service: FixtureTestService) -> None:
    await _stop_flash(session, service)
    step = session.current
    if step is None or not step.can_flash:
        return
    # Any other test on this fixture would zero it out from under the hold.
    await service.stop_test(step.fixture_id)
    task = asyncio.create_task(_hold(service, step))
    session.hold_task = task
    session.hold_step = step
    service.active_tests[step.fixture_id] = task


async def _release(session: _Session, service: FixtureTestService) -> None:
    """Stop the flash and give the show its universes back. Idempotent."""
    await _stop_flash(session, service)
    if not session.released:
        _resume_show_output(session)
        session.released = True


async def _end_session(session: _Session, service: FixtureTestService) -> None:
    await _release(session, service)
    watchdog = session.watchdog_task
    session.watchdog_task = None
    if watchdog is not None and watchdog is not asyncio.current_task():
        watchdog.cancel()
    _sessions.pop(session.session_id, None)


async def _watchdog(session: _Session, service: FixtureTestService) -> None:
    """Reap a walkthrough whose browser stopped talking to us."""
    try:
        while True:
            await asyncio.sleep(WATCHDOG_TICK_S)
            if time.monotonic() - session.last_seen > SESSION_IDLE_TIMEOUT_S:
                logger.info(
                    "Identify session %s abandoned - releasing rig %s",
                    session.session_id, session.rig_id,
                )
                await _end_session(session, service)
                return
    except asyncio.CancelledError:
        raise


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def _step_payload(session: _Session, step: _Step) -> Dict[str, Any]:
    return {
        "fixture_id": step.fixture_id,
        "label": step.label,
        "universe": step.universe,
        "dmx_address": step.dmx_address,
        "position_x": step.position_x,
        "position_y": step.position_y,
        "position_z": step.position_z,
        "can_flash": step.can_flash,
        "blocked_reason": step.blocked_reason,
        "flashing": bool(
            session.hold_step is step
            and session.hold_task is not None
            and not session.hold_task.done()
        ),
    }


def _session_state(session: _Session) -> Dict[str, Any]:
    counts = {OUTCOME_PLACED: 0, OUTCOME_KEPT: 0, OUTCOME_NO_RESPONSE: 0}
    unresponsive: List[Dict[str, Any]] = []
    for step in session.steps:
        if step.outcome in counts:
            counts[step.outcome] += 1
        if step.outcome == OUTCOME_NO_RESPONSE:
            unresponsive.append({
                "fixture_id": step.fixture_id,
                "label": step.label,
                "universe": step.universe,
                "dmx_address": step.dmx_address,
                "reason": step.blocked_reason or "Did not light when we tested it",
            })

    current = session.current
    return {
        "session_id": session.session_id,
        "rig_id": session.rig_id,
        "rig_name": session.rig_name,
        "stage_width": session.stage_width,
        "stage_depth": session.stage_depth,
        "total": len(session.steps),
        "step_number": min(session.index + 1, len(session.steps)),
        "complete": session.complete,
        "flash_level": session.flash_level,
        "current": _step_payload(session, current) if current is not None else None,
        "placed": counts[OUTCOME_PLACED],
        "kept": counts[OUTCOME_KEPT],
        "no_response": counts[OUTCOME_NO_RESPONSE],
        "unresponsive": unresponsive,
        "heartbeat_timeout_s": SESSION_IDLE_TIMEOUT_S,
        "flash_max_s": FLASH_MAX_S,
    }


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def _require_session(rig_id: int, session_id: str) -> _Session:
    session = _sessions.get(session_id)
    if session is None or session.rig_id != rig_id:
        raise HTTPException(
            status_code=404,
            detail="That walkthrough has finished or timed out. Start it again.",
        )
    session.touch()
    return session


def _session_lock(session: _Session) -> asyncio.Lock:
    """Serialise the answer-then-advance sequence for one walkthrough."""
    if session.action_lock is None:
        session.action_lock = asyncio.Lock()
    return session.action_lock


def _claim_step(session: _Session, fixture_id: Optional[int]) -> _Step:
    """The step this request is answering, refusing to answer any other one.

    A double tap on a touch plan is one gesture that arrives as two requests.
    Without this the second one would answer whichever step the first had just
    advanced to: that fixture is never lit, never asked about and never given an
    outcome, yet the summary still says every light was checked.
    """
    step = session.current
    if step is None:
        raise HTTPException(status_code=409, detail="This walkthrough has finished.")
    if fixture_id is not None and fixture_id != step.fixture_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"That answer was for a light we have already moved on from. "
                f"We are on '{step.label}' now - nothing was changed."
            ),
        )
    return step


async def _load_rig(rig_id: int, db: AsyncSession) -> Rig:
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")
    return rig


async def _load_rig_fixture(rig_id: int, fixture_id: int, db: AsyncSession) -> RigFixture:
    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.id == fixture_id)
        .limit(1)
    )
    rf = result.scalars().first()
    if not rf:
        raise HTTPException(status_code=404, detail="Rig fixture not found")
    return rf


def _set_no_response_tag(rf: RigFixture, marked: bool) -> None:
    # The JSON column is not a MutableList, so an in-place append would never be
    # written back.
    tags = [t for t in (rf.tags or []) if t != NO_RESPONSE_TAG]
    if marked:
        tags.append(NO_RESPONSE_TAG)
    rf.tags = tags


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class TappedPosition(BaseModel):
    """Where the owner says the flashing light actually is.

    Contract §1: X across the stage (0 centre), Z depth (0 centre, +Z downstage
    toward the audience), both in metres.
    """

    position_x: float
    position_z: float
    position_y: Optional[float] = None
    # Which light this tap was about. Checked against the step the walkthrough is
    # actually on; see _claim_step.
    fixture_id: Optional[int] = None


class SkipReason(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)
    fixture_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/rigs/{rig_id}/identify/start")
async def start_walkthrough(
    rig_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Begin the flash-to-identify walkthrough for a rig."""
    service = get_test_service(request)
    rig = await _load_rig(rig_id, db)

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id, RigFixture.is_active == True)  # noqa: E712
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
        .order_by(RigFixture.universe, RigFixture.dmx_address, RigFixture.id)
    )
    rig_fixtures = result.scalars().all()
    if not rig_fixtures:
        raise HTTPException(
            status_code=400,
            detail="This rig has no lights patched yet, so there is nothing to identify.",
        )

    cap = _venue_intensity_cap(request.app.state)
    level = int(round(255 * cap))
    if level <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "The venue intensity limit is set to zero, so a test light would not "
                "be visible. Raise it before running the walkthrough."
            ),
        )

    steps: List[_Step] = []
    for position, rf in enumerate(rig_fixtures, start=1):
        label = rf.name or f"Light {position} (address {rf.dmx_address})"
        channels = list(rf.mode.channels) if rf.mode else []
        can_flash = bool(rf.mode) and bool(channels)
        blocked_reason = None
        values: Dict[int, int] = {}
        if can_flash:
            ch_map = service._build_channel_map(channels)
            values = _identify_values(channels, ch_map, level)
            if not values:
                can_flash = False
                blocked_reason = (
                    "This light's profile has no dimmer or colour channel, so we "
                    "cannot turn it on from here."
                )
        else:
            blocked_reason = (
                "This light has no mode set, so we do not know its channel layout. "
                "Set its mode in the patch, then run this again."
            )

        steps.append(_Step(
            fixture_id=rf.id,
            label=label,
            universe=rf.universe or 0,
            dmx_address=rf.dmx_address,
            channel_count=(rf.mode.channel_count if rf.mode else 1),
            values=values,
            can_flash=can_flash,
            blocked_reason=blocked_reason,
            position_x=float(rf.position_x or 0.0),
            position_y=float(rf.position_y or 0.0),
            position_z=float(rf.position_z or 0.0),
        ))

    # One walkthrough at a time: it owns the universes while it runs.
    for existing in list(_sessions.values()):
        await _end_session(existing, service)

    session = _Session(
        session_id=uuid.uuid4().hex,
        rig_id=rig_id,
        rig_name=rig.name,
        stage_width=float(rig.stage_width or 10.0),
        stage_depth=float(rig.stage_depth or 8.0),
        flash_level=level,
        steps=steps,
    )
    _sessions[session.session_id] = session

    try:
        _suspend_show_output(session, request)
        await _start_flash(session, service)
    except Exception:
        # A half-started walkthrough would hold the show off the wire forever.
        await _end_session(session, service)
        raise
    session.watchdog_task = asyncio.create_task(_watchdog(session, service))

    return _session_state(session)


@router.get("/rigs/{rig_id}/identify/{session_id}")
async def get_walkthrough(rig_id: int, session_id: str):
    """Current state of a walkthrough, for a reloaded page."""
    return _session_state(_require_session(rig_id, session_id))


@router.post("/rigs/{rig_id}/identify/{session_id}/heartbeat")
async def heartbeat(rig_id: int, session_id: str):
    """Keep the walkthrough alive. Silence releases the fixture and the show."""
    return _session_state(_require_session(rig_id, session_id))


@router.post("/rigs/{rig_id}/identify/{session_id}/flash")
async def flash_current(
    rig_id: int,
    session_id: str,
    fixture_id: Optional[int] = None,
    request: Request = None,
):
    """Light the current fixture again."""
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, fixture_id)
        if not step.can_flash:
            raise HTTPException(status_code=409, detail=step.blocked_reason)
        await _start_flash(session, get_test_service(request))
        return _session_state(session)


async def _advance(session: _Session, service: FixtureTestService) -> None:
    """Move to the next light. Callers hold the session lock and have already
    claimed the step they are answering, so this can only run once per step."""
    session.index += 1
    if session.complete:
        await _release(session, service)
    else:
        await _start_flash(session, service)


@router.post("/rigs/{rig_id}/identify/{session_id}/position")
async def record_position(
    rig_id: int,
    session_id: str,
    body: TappedPosition,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Record where the owner tapped, then move to the next light."""
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, body.fixture_id)

        # A stray tap on the far edge of the plan should not put a light in the car park.
        limit_x = session.stage_width / 2 + 2.0
        limit_z = session.stage_depth / 2 + 2.0
        x = max(-limit_x, min(limit_x, float(body.position_x)))
        z = max(-limit_z, min(limit_z, float(body.position_z)))
        y = step.position_y if body.position_y is None else float(body.position_y)

        rf = await _load_rig_fixture(rig_id, step.fixture_id, db)
        rf.position_x = x
        rf.position_z = z
        rf.position_y = y
        # It lit up and the owner pointed at it, so any earlier "never lit" mark is stale.
        _set_no_response_tag(rf, False)
        await db.commit()

        step.position_x, step.position_y, step.position_z = x, y, z
        step.outcome = OUTCOME_PLACED
        await _advance(session, get_test_service(request))
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/skip")
async def skip_current(
    rig_id: int,
    session_id: str,
    body: Optional[SkipReason] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Record that this fixture never lit, then move on.

    The mark is written to the fixture, not just the session: a light that does
    not respond is patched wrong, unpowered or dead, and that is worth more to a
    venue than the position would have been.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, body.fixture_id if body is not None else None)

        rf = await _load_rig_fixture(rig_id, step.fixture_id, db)
        _set_no_response_tag(rf, True)
        await db.commit()

        step.outcome = OUTCOME_NO_RESPONSE
        if body is not None and body.reason:
            step.blocked_reason = body.reason
        elif step.blocked_reason is None:
            step.blocked_reason = "Did not light when we tested it"

        logger.warning(
            "Identify: rig %s fixture %s (universe %s @ %s) did not respond - %s",
            rig_id, step.fixture_id, step.universe, step.dmx_address, step.blocked_reason,
        )

        await _advance(session, get_test_service(request))
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/advance")
async def keep_and_advance(
    rig_id: int,
    session_id: str,
    fixture_id: Optional[int] = None,
    request: Request = None,
):
    """Leave this fixture where it already is and move to the next one."""
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, fixture_id)
        step.outcome = OUTCOME_KEPT
        await _advance(session, get_test_service(request))
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/end")
async def end_walkthrough(rig_id: int, session_id: str, request: Request = None):
    """Finish the walkthrough: fixture off, show back on the wire.

    Ending an already-ended session is not an error - the browser sends this on
    unload and may well be racing the watchdog.
    """
    session = _sessions.get(session_id)
    if session is None or session.rig_id != rig_id:
        return {"session_id": session_id, "rig_id": rig_id, "ended": True, "already_ended": True}

    state = _session_state(session)
    await _end_session(session, get_test_service(request))
    state["ended"] = True
    state["already_ended"] = False
    return state
