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

Locate mode (docs/FLASH_AND_TAP.md) is the same walkthrough started with
``only=unconfirmed``: it walks just the fixtures whose position is a generated
guess, a row at a time and ends first, offers to space the rest of a row along
the line between its two tapped ends, and confirms that fit with a slow walk of
light along the row. Every light it shows goes through the one hold slot on the
session, so the release paths below cover all of it.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.endpoints.fixture_test import get_test_service
from app.db.database import get_db
from app.models.fixture import FixtureMode
from app.models.rig import Rig, RigFixture
from app.services.dmx.channel_ranges import (
    FALLBACK_SHUTTER_OPEN, FALLBACK_STROBE_IDLE, resolve_channel_ranges,
)
from app.services.fixture_test.fixture_test_service import FixtureTestService
from app.services.venue_import.apply import (
    SOURCE_CONFIRMED,
    SOURCE_ROW_FIT,
    SOURCE_TAP,
    SOURCE_TEMPLATE,
    TAG_CLASH,
    TAG_UNMATCHED,
    is_unconfirmed,
    position_source,
    with_position_confirmed,
    with_position_source,
)
from app.services.fixture_test.setup_check import (
    ShowSuspension,
    setup_hold,
)

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
# "It is where the plan shows it": the drawn position, accepted by a person.
OUTCOME_CONFIRMED = "confirmed"
# Spaced between its row's two tapped ends, and the row check passed.
OUTCOME_FITTED = "fitted"
# These two leave a fixture with a position somebody stands behind.
LOCATED_OUTCOMES = (OUTCOME_PLACED, OUTCOME_CONFIRMED)

MODE_ALL = "all"
MODE_UNCONFIRMED = "unconfirmed"

# The row check walks one steady light along the row. This is how long each
# fixture stays on before the next takes over: slow enough to follow with a
# finger, and nowhere near a rate that reads as a flash.
ROW_CHECK_STEP_S = 1.5

# A row's life in locate mode.
ROW_ENDS = "ends"            # lighting its first fixture, then its last
ROW_FIT_OFFER = "fit_offer"  # both ends located; nothing lit; fit the rest?
ROW_CHECK = "check"          # fitted; the light is walking along the row
ROW_EACH = "each"            # the rest are being tapped one at a time
ROW_DONE = "done"
ROW_PAUSED = (ROW_FIT_OFFER, ROW_CHECK)

# A row is only fitted to a line if the generated positions were one: further
# than this off the line between its ends (metres, on the plan) and it is a
# ring or a stack, not a truss.
STRAIGHT_TOLERANCE_M = 0.15
MIN_ROW_LENGTH_M = 0.1
# The two end taps must be this far apart across the stage before their order
# is read as "the sheet is mirrored" and not as two taps on one spot.
MIRROR_MIN_SPAN_M = 0.5
MAX_HEIGHT_M = 100.0

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
    # Whether the fixture's position is still a guess nobody has checked.
    unconfirmed: bool = False
    source: Optional[str] = None
    group: Optional[str] = None


@dataclass
class _Row:
    """A run of guessed fixtures that hang together, in locate mode.

    Its steps sit together in the session: the first fixture, then the last,
    then the ones between in address order - so the two taps that pin the row
    down come before anything else is asked.
    """

    group: str
    start: int
    count: int
    can_fit: bool
    fit_blocked_reason: Optional[str] = None
    stage: str = ROW_ENDS
    fitted: bool = False
    # Where the generator drew the two ends, kept to tell a mirrored sheet.
    guess_first_x: float = 0.0
    guess_last_x: float = 0.0

    @property
    def end(self) -> int:
        return self.start + self.count

    def in_address_order(self, steps: List[_Step]) -> List[_Step]:
        mine = steps[self.start:self.end]
        if self.count < 3:
            return mine
        return [mine[0], *mine[2:], mine[1]]


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
    mode: str = MODE_ALL
    rows: List[_Row] = field(default_factory=list)
    # Fixtures that are switched off, so cannot be lit, with the reason.
    not_located: List[Dict[str, Any]] = field(default_factory=list)
    mirror_checked: bool = False
    mirror_offer: bool = False
    # Index of the first step after the row whose taps raised the offer.
    mirror_from: int = 0
    mirrored: bool = False
    last_seen: float = field(default_factory=time.monotonic)
    released: bool = False
    hold_task: Optional[asyncio.Task] = None
    hold_step: Optional[_Step] = None
    # The fixtures a running row check owns; hold_step is None while it runs.
    hold_row: List[_Step] = field(default_factory=list)
    watchdog_task: Optional[asyncio.Task] = None
    # The running show, parked for as long as the walkthrough owns the wire.
    suspension: ShowSuspension = field(default_factory=ShowSuspension)
    # Guards a step against being answered twice. Two taps that race each other
    # would otherwise both advance and skip the fixture in between.
    action_lock: Any = None

    @property
    def complete(self) -> bool:
        return self.index >= len(self.steps)

    @property
    def current(self) -> Optional[_Step]:
        return None if self.complete else self.steps[self.index]

    @property
    def current_row(self) -> Optional[_Row]:
        if self.complete:
            return None
        for row in self.rows:
            if row.start <= self.index < row.end:
                return row
        return None

    @property
    def paused(self) -> bool:
        """A question about the whole row is open, so no single light is current."""
        row = self.current_row
        return row is not None and row.stage in ROW_PAUSED

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
    ranges = resolve_channel_ranges("shutter", getattr(channel, "value_ranges", None))
    return ranges.open_byte() if ranges is not None else FALLBACK_SHUTTER_OPEN


def _strobe_idle_value(channel: Any) -> int:
    """The value at which this strobe channel does not strobe and shows light.

    0 unless the profile says otherwise - and several say otherwise: a par whose
    strobe channel names 0 "closed" stays dark at 0, and the owner would report
    a light that never lit.
    """
    ranges = resolve_channel_ranges("strobe", getattr(channel, "value_ranges", None))
    return ranges.open_byte() if ranges is not None else FALLBACK_STROBE_IDLE


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
            # come up hot is the hazard this endpoint exists to avoid. "Off" is
            # the profile's resting value, never a byte inside a strobe range.
            values[offset] = _strobe_idle_value(channel)
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
    has an answer. The mechanism is ShowSuspension, shared with the per-fixture
    setup checks so there is one way of parking a show and putting it back.
    """
    session.suspension.suspend(
        request.app.state,
        {step.universe for step in session.steps if step.can_flash},
    )


def _resume_show_output(session: _Session) -> None:
    """Hand the universes back to the show, at the levels it left them."""
    session.suspension.resume()


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
    """Cancel the hold and black out what it lit. Safe to call repeatedly."""
    task = session.hold_task
    held = [session.hold_step] if session.hold_step is not None else list(session.hold_row)
    session.hold_task = None
    session.hold_step = None
    session.hold_row = []
    if task is None or not held:
        return

    # Registered under the fixture id, so the existing fixture-test stop endpoints
    # release this hold too; drop the registration only if it is still ours.
    for step in held:
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
    for step in held:
        await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)


async def _walk_row(service: FixtureTestService, steps: List[_Step]) -> None:
    """Light a row one fixture at a time, once, then leave all of it dark.

    One fixture is lit at any moment: each is blacked out before the next comes
    on, and each stays on for ROW_CHECK_STEP_S. Like _hold, it cleans up after
    itself however it ends.
    """
    current = asyncio.current_task()

    async def _dark() -> None:
        for step in steps:
            await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)
            if service.active_tests.get(step.fixture_id) is current:
                service.active_tests.pop(step.fixture_id, None)

    try:
        for step in steps:
            await service._set_fixture_channels(step.universe, step.dmx_address, step.values)
            await asyncio.sleep(ROW_CHECK_STEP_S)
            await service._zero_fixture(step.universe, step.dmx_address, step.channel_count)
    except asyncio.CancelledError:
        await _dark()
        raise
    except Exception:
        logger.exception("Row check failed - blacking the row out")
    await _dark()


def _check_order(session: _Session, row: _Row) -> List[_Step]:
    """The row in the order the check lights it: plan left to plan right.

    A row that runs straight up or down the plan has no left, so it goes in
    address order.
    """
    ordered = row.in_address_order(session.steps)
    if ordered[-1].position_x - ordered[0].position_x < -MIN_ROW_LENGTH_M:
        ordered = list(reversed(ordered))
    return ordered


def _check_direction(session: _Session, row: _Row) -> str:
    ordered = row.in_address_order(session.steps)
    across = abs(ordered[-1].position_x - ordered[0].position_x)
    return "left_to_right" if across >= MIN_ROW_LENGTH_M else "address_order"


async def _start_row_check(session: _Session, service: FixtureTestService, row: _Row) -> None:
    """Walk the light along a fitted row. It sits in the session's one hold
    slot, so every path that releases a flash releases this too."""
    await _stop_flash(session, service)
    steps = [step for step in _check_order(session, row) if step.can_flash]
    if not steps:
        return
    for step in steps:
        await service.stop_test(step.fixture_id)
    task = asyncio.create_task(_walk_row(service, steps))
    session.hold_task = task
    session.hold_row = steps
    for step in steps:
        service.active_tests[step.fixture_id] = task


async def _start_flash(session: _Session, service: FixtureTestService) -> None:
    await _stop_flash(session, service)
    step = session.current
    # While a question about the whole row is open, no single light is lit.
    if step is None or not step.can_flash or session.paused:
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
        "unconfirmed": step.unconfirmed,
        "group": step.group,
        "flashing": bool(
            session.hold_step is step
            and session.hold_task is not None
            and not session.hold_task.done()
        ),
    }


def _mirror_candidates(session: _Session) -> List[_Step]:
    """Steps a mirror would move: unanswered guesses in the rows after the one
    whose taps raised the offer."""
    return [
        step for step in session.steps[session.mirror_from:]
        if step.outcome is None and step.unconfirmed and step.source == SOURCE_TEMPLATE
    ]


def _row_payload(session: _Session, row: _Row) -> Dict[str, Any]:
    ordered = row.in_address_order(session.steps)
    heights = {round(step.position_y, 3) for step in ordered}
    running = bool(
        session.hold_row and session.hold_task is not None and not session.hold_task.done()
    )
    return {
        "number": session.rows.index(row) + 1,
        "of": len(session.rows),
        "group": row.group,
        "stage": row.stage,
        "can_fit": row.can_fit,
        "fit_blocked_reason": row.fit_blocked_reason,
        "fitted": row.fitted,
        "running": running,
        "direction": _check_direction(session, row),
        "step_seconds": ROW_CHECK_STEP_S,
        # One trim height for the row, or None while its fixtures differ.
        "height": heights.pop() if len(heights) == 1 else None,
        "fixtures": [
            {
                "fixture_id": step.fixture_id,
                "label": step.label,
                "position_x": step.position_x,
                "position_y": step.position_y,
                "position_z": step.position_z,
                "unconfirmed": step.unconfirmed,
                "outcome": step.outcome,
            }
            for step in ordered
        ],
    }


def _session_state(session: _Session) -> Dict[str, Any]:
    counts = {
        OUTCOME_PLACED: 0, OUTCOME_KEPT: 0, OUTCOME_NO_RESPONSE: 0,
        OUTCOME_CONFIRMED: 0, OUTCOME_FITTED: 0,
    }
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

    row = session.current_row
    # While the row itself is the question, no single light is the current one.
    current = None if session.paused else session.current
    mirror = _mirror_candidates(session) if session.mirror_offer else []
    return {
        "mode": session.mode,
        "row": _row_payload(session, row) if row is not None else None,
        "rows_total": len(session.rows),
        "confirmed": counts[OUTCOME_CONFIRMED],
        "fitted": counts[OUTCOME_FITTED],
        # Of the lights in this walk, how many still sit on a guess.
        "still_unconfirmed": sum(1 for step in session.steps if step.unconfirmed),
        # Switched off, so never lit and never asked about. Counted apart.
        "not_located": session.not_located,
        "not_located_count": len(session.not_located),
        "mirror_offer": {"fixtures": len(mirror)} if mirror else None,
        "mirrored": session.mirrored,
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
    if session.paused:
        raise HTTPException(
            status_code=409,
            detail="There is a question about the whole row to answer first - nothing was changed.",
        )
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


async def _load_rig_fixtures(rig_id: int, fixture_ids: List[int], db: AsyncSession) -> Dict[int, RigFixture]:
    if not fixture_ids:
        return {}
    result = await db.execute(
        select(RigFixture).where(RigFixture.rig_id == rig_id, RigFixture.id.in_(fixture_ids))
    )
    return {rf.id: rf for rf in result.scalars().all()}


def _require_row(session: _Session, stage: str, otherwise: str) -> _Row:
    row = session.current_row
    if row is None or row.stage != stage:
        raise HTTPException(status_code=409, detail=otherwise)
    return row


# ---------------------------------------------------------------------------
# Rows (locate mode)
# ---------------------------------------------------------------------------


def _continues_row(previous: RigFixture, fixture: RigFixture) -> bool:
    """Whether `fixture` is the next one along the same row as `previous`.

    A row is one group on consecutive addresses, which is how the layout
    generator made it. The address test matters: a sheet that named its own
    group can spread that name over two trusses, and a fixture missing from the
    middle (switched off, or already measured) leaves a hole the fit would
    space straight across.
    """
    if not previous.group_name or previous.group_name != fixture.group_name:
        return False
    footprint = previous.mode.channel_count if previous.mode else 1
    footprint = max(1, int(footprint or 1))
    if (fixture.universe or 0) == (previous.universe or 0):
        gap = fixture.dmx_address - (previous.dmx_address + footprint)
        return 0 <= gap < footprint
    if (fixture.universe or 0) == (previous.universe or 0) + 1:
        # Ran off the end of one universe onto the start of the next.
        return previous.dmx_address + 2 * footprint - 1 > 512 and fixture.dmx_address <= footprint
    return False


def _fit_blocker(steps: List[_Step]) -> Optional[str]:
    """Why the fixtures between a row's ends cannot be spaced along a line.

    `steps` is the row in address order, at the positions the generator gave.
    """
    if len(steps) < 3:
        return "A row of one or two lights has nothing between its ends."
    if not all(step.can_flash for step in steps):
        return (
            "A light in this row cannot be turned on from here, so a check of the "
            "whole row would not cover it. Each light is tapped on its own."
        )
    ax, az = steps[0].position_x, steps[0].position_z
    dx, dz = steps[-1].position_x - ax, steps[-1].position_z - az
    length_sq = dx * dx + dz * dz
    not_a_line = (
        "This row is not drawn as a straight line on the plan (a ring, or lights "
        "stacked on a tower), so each light is tapped on its own."
    )
    if length_sq < MIN_ROW_LENGTH_M ** 2:
        return not_a_line
    length = length_sq ** 0.5
    along_before = 0.0
    for step in steps[1:-1]:
        px, pz = step.position_x - ax, step.position_z - az
        along = (px * dx + pz * dz) / length_sq
        off = abs(px * dz - pz * dx) / length
        if off > STRAIGHT_TOLERANCE_M or along <= along_before or along >= 1.0:
            return not_a_line
        along_before = along
    return None


def _order_for_locate(
    fixtures: List[RigFixture], make_step: Callable[[RigFixture], _Step],
) -> "tuple[List[_Step], List[_Row]]":
    """Steps and rows for locate mode: a row at a time, each row's ends first."""
    runs: List[List[RigFixture]] = []
    for fixture in fixtures:
        if runs and _continues_row(runs[-1][-1], fixture):
            runs[-1].append(fixture)
        else:
            runs.append([fixture])

    steps: List[_Step] = []
    rows: List[_Row] = []
    for run in runs:
        in_order = [make_step(fixture) for fixture in run]
        blocker = _fit_blocker(in_order)
        rows.append(_Row(
            group=run[0].group_name or in_order[0].label,
            start=len(steps),
            count=len(in_order),
            can_fit=blocker is None,
            fit_blocked_reason=blocker,
            guess_first_x=in_order[0].position_x,
            guess_last_x=in_order[-1].position_x,
        ))
        if len(in_order) >= 3:
            in_order = [in_order[0], in_order[-1], *in_order[1:-1]]
        steps.extend(in_order)
    return steps, rows


def _switched_off_reason(tags: Optional[List[str]]) -> str:
    tags = tags or []
    if TAG_UNMATCHED in tags:
        return (
            "No fixture profile matched its type, so it was switched off when the "
            "sheet was imported and cannot be turned on from here."
        )
    if TAG_CLASH in tags:
        return (
            "It shares DMX channels with another light, so it was switched off "
            "when the sheet was imported."
        )
    return "It is switched off in the patch."


def _after_answer(session: _Session, row: _Row) -> None:
    """Move a row on once the step just answered has been counted.

    Called with session.index already past that step.
    """
    if row.stage == ROW_ENDS and session.index >= row.start + min(2, row.count):
        first = session.steps[row.start]
        last = session.steps[row.start + 1] if row.count > 1 else first
        _look_for_mirror(session, row, first, last)
        if row.count < 3:
            row.stage = ROW_DONE
        elif not row.can_fit:
            row.stage = ROW_EACH
        elif first.outcome in LOCATED_OUTCOMES and last.outcome in LOCATED_OUTCOMES:
            row.stage = ROW_FIT_OFFER
        else:
            row.can_fit = False
            row.fit_blocked_reason = (
                "Both ends of the row have to be found before the lights between "
                "them can be spaced, so each one is tapped on its own."
            )
            row.stage = ROW_EACH
    if row.stage == ROW_EACH and session.index >= row.end:
        row.stage = ROW_DONE


def _look_for_mirror(session: _Session, row: _Row, first: _Step, last: _Step) -> None:
    """Notice, once, that a row's two taps ran the opposite way to its drawing.

    Only two real taps say anything: an end accepted as drawn agrees with the
    drawing by definition.
    """
    if session.mirror_checked or row.count < 2:
        return
    if first.outcome != OUTCOME_PLACED or last.outcome != OUTCOME_PLACED:
        return
    drawn = row.guess_last_x - row.guess_first_x
    tapped = last.position_x - first.position_x
    if abs(drawn) < MIRROR_MIN_SPAN_M or abs(tapped) < MIRROR_MIN_SPAN_M:
        return
    session.mirror_checked = True
    session.mirror_from = row.end
    session.mirror_offer = (drawn > 0) != (tapped > 0)


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


class RowFit(BaseModel):
    """Whether to space the lights between a row's two located ends."""

    accept: bool = True


class RowCheck(BaseModel):
    """Whether the light was seen to run along the row in order."""

    passed: bool


class RowHeight(BaseModel):
    """One trim height, in metres, for every light in the row."""

    height: float = Field(..., ge=0.0, le=MAX_HEIGHT_M)


class MirrorAnswer(BaseModel):
    accept: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    """Which lights to walk. Left out, the walk is chosen by `only`."""

    fixture_ids: Optional[List[int]] = Field(
        default=None,
        max_length=4096,
        description="Walk exactly these lights of the rig (the Readiness panel's Locate these). "
                    "With only=unconfirmed they are walked a row at a time, as locate mode walks.",
    )


@router.post("/rigs/{rig_id}/identify/start")
async def start_walkthrough(
    rig_id: int,
    only: Optional[str] = Query(
        default=None,
        description="'unconfirmed' walks just the lights whose position is a generated guess, "
                    "a row at a time (locate mode). Left out, every active light is walked.",
    ),
    body: Optional[StartRequest] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Begin the flash-to-identify walkthrough for a rig."""
    if only not in (None, "", MODE_UNCONFIRMED):
        raise HTTPException(
            status_code=400,
            detail=f"'only' can be '{MODE_UNCONFIRMED}' or left out, not '{only}'.",
        )
    locate = only == MODE_UNCONFIRMED
    chosen = set(body.fixture_ids) if body is not None and body.fixture_ids is not None else None
    if chosen is not None and not chosen:
        raise HTTPException(status_code=400, detail="No lights were named to walk.")

    def wanted(rf: RigFixture) -> bool:
        # Named lights are walked whatever their tags: the Positions check also names
        # lights with no position at all, which carry no position_unconfirmed tag.
        if chosen is not None:
            return rf.id in chosen
        return not locate or is_unconfirmed(rf.tags)
    service = get_test_service(request)
    rig = await _load_rig(rig_id, db)

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
        .order_by(RigFixture.universe, RigFixture.dmx_address, RigFixture.id)
    )
    everything = result.scalars().all()
    rig_fixtures = [rf for rf in everything if rf.is_active and wanted(rf)]
    # A switched-off fixture drives nothing, so it can never be the one that is
    # lit. It is reported, with the reason, instead of being left out of the count.
    not_located = [
        {
            "fixture_id": rf.id,
            "label": rf.name or f"Light at address {rf.dmx_address}",
            "universe": rf.universe or 0,
            "dmx_address": rf.dmx_address,
            "group": rf.group_name,
            "unconfirmed": is_unconfirmed(rf.tags),
            "reason": _switched_off_reason(rf.tags),
        }
        for rf in everything
        if not rf.is_active and wanted(rf)
    ]
    # Both refusals come before anything touches the wire: a walkthrough with
    # nothing to walk must not take the show down to say so.
    if not rig_fixtures:
        if chosen is not None:
            detail = "None of the lights named is on this rig and switched on, so there is nothing to walk."
            if not_located:
                detail += (
                    f" {len(not_located)} of them {'are' if len(not_located) != 1 else 'is'} switched off: "
                    + ", ".join(entry["label"] for entry in not_located[:8])
                    + ("..." if len(not_located) > 8 else "") + "."
                )
            raise HTTPException(status_code=400, detail=detail)
        if not locate:
            raise HTTPException(
                status_code=400,
                detail="This rig has no lights patched yet, so there is nothing to identify.",
            )
        detail = "No light on this rig has a guessed position left to check."
        if not_located:
            detail += (
                f" {len(not_located)} switched-off light(s) still sit on a guessed position "
                "and cannot be turned on from here: "
                + ", ".join(entry["label"] for entry in not_located[:8])
                + ("..." if len(not_located) > 8 else "") + "."
            )
        raise HTTPException(status_code=400, detail=detail)

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

    numbers = {rf.id: number for number, rf in enumerate(rig_fixtures, start=1)}

    def make_step(rf: RigFixture) -> _Step:
        label = rf.name or f"Light {numbers[rf.id]} (address {rf.dmx_address})"
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

        return _Step(
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
            unconfirmed=is_unconfirmed(rf.tags),
            source=position_source(rf.tags),
            group=rf.group_name,
        )

    rows: List[_Row] = []
    if locate:
        steps, rows = _order_for_locate(rig_fixtures, make_step)
    else:
        steps = [make_step(rf) for rf in rig_fixtures]

    # One walkthrough at a time: it owns the universes while it runs. A fixture
    # held for a setup check owns them too and has to let go first, or each
    # would park the other's dark room as "the show" and restore that.
    for existing in list(_sessions.values()):
        await _end_session(existing, service)
    await setup_hold.release(service)

    session = _Session(
        session_id=uuid.uuid4().hex,
        rig_id=rig_id,
        rig_name=rig.name,
        stage_width=float(rig.stage_width or 10.0),
        stage_depth=float(rig.stage_depth or 8.0),
        flash_level=level,
        steps=steps,
        mode=MODE_UNCONFIRMED if locate else MODE_ALL,
        rows=rows,
        not_located=not_located,
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
    """Light the current fixture again, or walk the row again during a row check."""
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        row = session.current_row
        if row is not None and row.stage == ROW_CHECK:
            await _start_row_check(session, get_test_service(request), row)
            return _session_state(session)
        step = _claim_step(session, fixture_id)
        if not step.can_flash:
            raise HTTPException(status_code=409, detail=step.blocked_reason)
        await _start_flash(session, get_test_service(request))
        return _session_state(session)


async def _advance(session: _Session, service: FixtureTestService) -> None:
    """Move to the next light. Callers hold the session lock and have already
    claimed the step they are answering, so this can only run once per step."""
    row = session.current_row
    session.index += 1
    if row is not None:
        _after_answer(session, row)
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
        # A tap is a person saying where the light is: the guess flag comes off.
        rf.tags = with_position_source(rf.tags, SOURCE_TAP, confirmed=True)
        # It lit up and the owner pointed at it, so any earlier "never lit" mark is stale.
        _set_no_response_tag(rf, False)
        await db.commit()

        step.position_x, step.position_y, step.position_z = x, y, z
        step.unconfirmed, step.source = False, SOURCE_TAP
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
    """Leave this fixture where it already is and move to the next one.

    This says nothing about whether the position is right, so a guessed
    position stays a guess. "It is where the plan shows it" is /confirm.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, fixture_id)
        step.outcome = OUTCOME_KEPT
        await _advance(session, get_test_service(request))
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/confirm")
async def confirm_as_drawn(
    rig_id: int,
    session_id: str,
    fixture_id: Optional[int] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """ "It is where the plan shows it": accept the drawn position, then move on."""
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        step = _claim_step(session, fixture_id)

        rf = await _load_rig_fixture(rig_id, step.fixture_id, db)
        # A measured position keeps saying where it was measured from; only a
        # guess changes hands.
        if is_unconfirmed(rf.tags):
            rf.tags = with_position_source(rf.tags, SOURCE_CONFIRMED, confirmed=True)
            step.source = SOURCE_CONFIRMED
        if step.can_flash:
            _set_no_response_tag(rf, False)
        await db.commit()

        step.unconfirmed = False
        step.outcome = OUTCOME_CONFIRMED
        await _advance(session, get_test_service(request))
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/fit-row")
async def fit_row(
    rig_id: int,
    session_id: str,
    body: Optional[RowFit] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Space the lights between a row's two located ends along the line joining them.

    The fitted lights stay unconfirmed: the fit is arithmetic, and it is the
    row check that says the arithmetic matches the truss. Declining drops back
    to tapping each light.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        row = _require_row(
            session, ROW_FIT_OFFER,
            "There is no row waiting to be spaced right now - nothing was changed.",
        )
        service = get_test_service(request)
        if body is not None and not body.accept:
            row.stage = ROW_EACH
            await _start_flash(session, service)
            return _session_state(session)

        ordered = row.in_address_order(session.steps)
        first, last = ordered[0], ordered[-1]
        between = ordered[1:-1]
        spans = len(ordered) - 1
        rows = await _load_rig_fixtures(rig_id, [step.fixture_id for step in between], db)
        placed = []
        for number, step in enumerate(between, start=1):
            rf = rows.get(step.fixture_id)
            if rf is None:
                raise HTTPException(status_code=404, detail="Rig fixture not found")
            share = number / spans
            x = round(first.position_x + (last.position_x - first.position_x) * share, 3)
            z = round(first.position_z + (last.position_z - first.position_z) * share, 3)
            # X and Z only. Height is the row's trim, set once on the row.
            rf.position_x, rf.position_z = x, z
            rf.tags = with_position_source(rf.tags, SOURCE_ROW_FIT, confirmed=False)
            placed.append((step, x, z))
        await db.commit()

        for step, x, z in placed:
            step.position_x, step.position_z = x, z
            step.source, step.unconfirmed = SOURCE_ROW_FIT, True
        row.fitted = True
        row.stage = ROW_CHECK
        await _start_row_check(session, service, row)
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/row-check")
async def answer_row_check(
    rig_id: int,
    session_id: str,
    body: RowCheck,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Record whether the light ran along the fitted row in order.

    Yes confirms every fitted light in the row at once. No leaves them as
    guesses and goes back to tapping them one at a time.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        row = _require_row(
            session, ROW_CHECK,
            "There is no row being checked right now - nothing was changed.",
        )
        service = get_test_service(request)
        await _stop_flash(session, service)

        if not body.passed:
            row.stage = ROW_EACH
            await _start_flash(session, service)
            return _session_state(session)

        between = session.steps[row.start + 2:row.end]
        rows = await _load_rig_fixtures(rig_id, [step.fixture_id for step in between], db)
        for step in between:
            rf = rows.get(step.fixture_id)
            if rf is not None:
                rf.tags = with_position_confirmed(rf.tags)
                # Every light in a fitted row can be lit, and was just seen lit.
                _set_no_response_tag(rf, False)
        await db.commit()

        for step in between:
            step.unconfirmed = False
            step.outcome = OUTCOME_FITTED
        row.stage = ROW_DONE
        session.index = row.end
        if session.complete:
            await _release(session, service)
        else:
            await _start_flash(session, service)
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/row-height")
async def set_row_height(
    rig_id: int,
    session_id: str,
    body: RowHeight,
    db: AsyncSession = Depends(get_db),
):
    """Give the row being located one trim height.

    Height is a property of the truss, so it is set once for the row. It moves
    nothing on the plan and confirms nothing.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        row = session.current_row
        if row is None:
            raise HTTPException(
                status_code=409,
                detail="There is no row being located right now - nothing was changed.",
            )
        mine = session.steps[row.start:row.end]
        height = round(float(body.height), 3)
        rows = await _load_rig_fixtures(rig_id, [step.fixture_id for step in mine], db)
        for rf in rows.values():
            rf.position_y = height
        await db.commit()
        for step in mine:
            step.position_y = height
        return _session_state(session)


@router.post("/rigs/{rig_id}/identify/{session_id}/mirror")
async def answer_mirror_offer(
    rig_id: int,
    session_id: str,
    body: Optional[MirrorAnswer] = None,
    db: AsyncSession = Depends(get_db),
):
    """Flip the guessed positions that are left about the stage's centre line.

    Offered when a row's two taps ran the opposite way to its drawing: the
    sheet's left is the plan's right. Only positions that are still template
    guesses in rows not yet reached are moved; anything tapped, confirmed,
    fitted or measured stays where it is.
    """
    session = _require_session(rig_id, session_id)
    async with _session_lock(session):
        if not session.mirror_offer:
            raise HTTPException(
                status_code=409,
                detail="There is no mirror offer open right now - nothing was changed.",
            )
        session.mirror_offer = False
        if body is not None and not body.accept:
            return _session_state(session)

        steps = _mirror_candidates(session)
        walked = {step.fixture_id for step in session.steps}
        result = await db.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))
        by_id = {rf.id: rf for rf in result.scalars().all()}
        moved: List[RigFixture] = [by_id[s.fixture_id] for s in steps if s.fixture_id in by_id]
        # The switched-off lights were drawn on the same mirrored guess.
        moved += [
            rf for rf in by_id.values()
            if rf.id not in walked and not rf.is_active
            and is_unconfirmed(rf.tags) and position_source(rf.tags) == SOURCE_TEMPLATE
        ]
        for rf in moved:
            rf.position_x = -float(rf.position_x or 0.0)
        await db.commit()

        for step in steps:
            step.position_x = -step.position_x
        session.mirrored = True
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
