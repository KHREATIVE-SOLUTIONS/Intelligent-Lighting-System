"""
Per-Fixture Setup Checks
========================

The four things someone has to see with their own eyes before a rig can be
trusted, asked of one fixture at a time from the patch:

* **flash** - does this fixture light, steadily, when we address it?
* **colour** - is red red, green green and blue blue?
* **pan** / **tilt** - does the head move, and the way we expect?

A check is a *look held steadily* on one fixture while the rest of the room is
dark, and an answer from the person looking at it. Nothing here blinks: the
light is held, re-asserted once a second, and released when the operator
stops, when their browser goes quiet, or when the hold has simply been up too
long.

Everything is written into the universe buffers like any other writer, so it
goes through the output stage on its way to the wire. A latched blackout, a
grand master at zero or the strobe switch still win, and ``output_block_reason``
says so rather than letting the operator read a dark fixture as a dead one.

This module also holds what the identify walkthrough and the setup checks
share: the values that light a fixture without strobing it, and the one way of
taking the running show off the wire and putting it back.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Channel types whose profile default is the fixture's own "no effect" position.
# A spot parked on a blackout gobo or a dark colour wheel slot is a light the
# owner would report as dead.
HOME_VALUE_TYPES = ("gobo", "gobo2", "color_wheel", "prism", "frost", "animation")
COLOR_TYPES = ("red", "green", "blue", "white")

# Subtractive flags, and the primary each one removes. 0 is fully open.
_SUBTRACTIVE = {"cyan": "red", "magenta": "green", "yellow": "blue"}

CHECK_FLASH = "flash"
CHECK_COLOUR = "colour"
CHECK_PAN = "pan"
CHECK_TILT = "tilt"
CHECKS = (CHECK_FLASH, CHECK_COLOUR, CHECK_PAN, CHECK_TILT)

LOOK_WHITE = "white"
LOOK_RED = "red"
LOOK_GREEN = "green"
LOOK_BLUE = "blue"
LOOK_WHITE_EMITTER = "white_emitter"
LOOK_CENTRE = "centre"
LOOK_PAN_LOW = "pan_low"
LOOK_PAN_HIGH = "pan_high"
LOOK_TILT_LOW = "tilt_low"
LOOK_TILT_HIGH = "tilt_high"

# DMX zero is an end stop on a moving head. Every look holds the head at the
# middle of its travel instead, and the direction looks step a little either
# side of it: far enough to see, not far enough to swing a beam round the room.
PAN_TILT_CENTRE = 128
PAN_TILT_STEP = 24

HOLD_REASSERT_S = 1.0
# Nobody studies one lamp for longer than this. Past it the hold lets go, so a
# walked-away-from browser cannot leave a fixture lit and the show off the wire.
HOLD_MAX_S = 90.0
# The browser heartbeats while a check is open; a gap this long means it is gone.
HOLD_IDLE_TIMEOUT_S = 30.0

RESULT_OK = "ok"
RESULT_FAIL = "fail"
_RESULT_PREFIX = "setup:"


# ---------------------------------------------------------------------------
# Values that light a fixture
# ---------------------------------------------------------------------------


def channel_type(channel: Any) -> str:
    if isinstance(channel, dict):
        ct = channel.get("channel_type")
    else:
        ct = getattr(channel, "channel_type", None)
    return str(getattr(ct, "value", ct) or "other")


def _attr(channel: Any, name: str, default: Any = None) -> Any:
    if isinstance(channel, dict):
        return channel.get(name, default)
    return getattr(channel, name, default)


def shutter_open_value(channel: Any) -> int:
    """The value that opens this shutter without putting it into strobe."""
    for entry in _attr(channel, "value_ranges") or []:
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


def identify_values(channels: List[Any], ch_map: Dict[str, int], level: int) -> Dict[int, int]:
    """DMX offsets to hold while this fixture is the one being looked at."""
    values: Dict[int, int] = {}

    if "dimmer" in ch_map:
        values[ch_map["dimmer"]] = level
    for color in COLOR_TYPES:
        if color in ch_map:
            values[ch_map[color]] = level

    for channel in channels:
        ctype = channel_type(channel)
        offset = int(_attr(channel, "channel_number", 1)) - 1
        if _attr(channel, "is_fine", False):
            continue
        if ctype == "shutter":
            values[offset] = shutter_open_value(channel)
        elif ctype == "strobe":
            # Explicitly parked off. A profile whose strobe channel happens to
            # come up hot is the hazard this exists to avoid.
            values[offset] = 0
        elif ctype in HOME_VALUE_TYPES:
            values[offset] = max(0, min(255, int(_attr(channel, "default_value", 0) or 0)))

    return values


def _has_full_cmy(ch_map: Dict[str, int]) -> bool:
    return all(flag in ch_map for flag in _SUBTRACTIVE)


def capabilities(channels: List[Any], ch_map: Dict[str, int]) -> List[Dict[str, Any]]:
    """Which checks this fixture's mode supports, and why not when it does not.

    Decided here, from the profile, so the patch screen never has to work out
    for itself what a channel list means.
    """
    def entry(check: str, looks: List[str], reason: Optional[str]) -> Dict[str, Any]:
        return {"check": check, "available": bool(looks), "looks": looks,
                "reason": None if looks else reason}

    if not channels:
        reason = ("This light has no mode set, so we do not know its channel layout. "
                  "Set its mode, then check it again.")
        return [entry(check, [], reason) for check in CHECKS]

    can_light = bool(identify_values(channels, ch_map, 255))
    dark = ("This light's profile has no dimmer, colour or shutter channel, so we "
            "cannot turn it on from here.")

    colour_looks: List[str] = []
    if can_light:
        cmy = _has_full_cmy(ch_map)
        colour_looks = [look for look in (LOOK_RED, LOOK_GREEN, LOOK_BLUE)
                        if look in ch_map or cmy]
        if colour_looks and "white" in ch_map:
            colour_looks.append(LOOK_WHITE_EMITTER)

    out = [
        entry(CHECK_FLASH, [LOOK_WHITE] if can_light else [], dark),
        entry(CHECK_COLOUR, colour_looks, dark if not can_light else (
            "This light does not mix its own colour (one colour, or a colour "
            "wheel), so there is nothing to check here.")),
    ]
    for check, low, high in ((CHECK_PAN, LOOK_PAN_LOW, LOOK_PAN_HIGH),
                             (CHECK_TILT, LOOK_TILT_LOW, LOOK_TILT_HIGH)):
        moves = can_light and check in ch_map
        out.append(entry(check, [LOOK_CENTRE, low, high] if moves else [],
                         dark if not can_light else "This light does not move."))
    return out


def look_values(channels: List[Any], ch_map: Dict[str, int], channel_count: int,
                level: int, look: str) -> Dict[int, int]:
    """Every channel of the fixture for one look. Empty if it cannot be lit.

    The whole fixture is given, zeros included, so going from one look to the
    next is a single write with no dark frame in between.
    """
    base = identify_values(channels, ch_map, level)
    if not base:
        return {}
    values = {offset: 0 for offset in range(max(1, int(channel_count)))}
    values.update(base)

    position = {"pan": PAN_TILT_CENTRE, "tilt": PAN_TILT_CENTRE}
    if look == LOOK_PAN_LOW:
        position["pan"] -= PAN_TILT_STEP
    elif look == LOOK_PAN_HIGH:
        position["pan"] += PAN_TILT_STEP
    elif look == LOOK_TILT_LOW:
        position["tilt"] -= PAN_TILT_STEP
    elif look == LOOK_TILT_HIGH:
        position["tilt"] += PAN_TILT_STEP
    for axis, value in position.items():
        if axis in ch_map:
            values[ch_map[axis]] = value

    if look in (LOOK_RED, LOOK_GREEN, LOOK_BLUE):
        for color in COLOR_TYPES:
            if color in ch_map:
                values[ch_map[color]] = level if color == look else 0
        for flag, removes in _SUBTRACTIVE.items():
            if flag in ch_map:
                values[ch_map[flag]] = 0 if removes == look else 255
    elif look == LOOK_WHITE_EMITTER:
        for color in COLOR_TYPES:
            if color in ch_map:
                values[ch_map[color]] = level if color == "white" else 0

    return values


# ---------------------------------------------------------------------------
# Recorded answers
# ---------------------------------------------------------------------------


def results_from_tags(tags: Optional[Iterable[str]]) -> Dict[str, Optional[str]]:
    """What the operator last said about each check, read off the fixture's tags."""
    results: Dict[str, Optional[str]] = {check: None for check in CHECKS}
    for tag in tags or []:
        parts = str(tag).split(":")
        if (len(parts) == 3 and parts[0] + ":" == _RESULT_PREFIX
                and parts[1] in results and parts[2] in (RESULT_OK, RESULT_FAIL)):
            results[parts[1]] = parts[2]
    return results


def tags_with_result(tags: Optional[Iterable[str]], check: str,
                     passed: Optional[bool]) -> List[str]:
    """The fixture's tags with one check's answer set, or cleared when None.

    Returns a new list: the column is plain JSON, so an in-place change would
    never be written back.
    """
    prefix = f"{_RESULT_PREFIX}{check}:"
    out = [tag for tag in (tags or []) if not str(tag).startswith(prefix)]
    if passed is not None:
        out.append(prefix + (RESULT_OK if passed else RESULT_FAIL))
    return out


# ---------------------------------------------------------------------------
# The output stage's say
# ---------------------------------------------------------------------------


def output_block_reason(dmx: Any, universe: Optional[int] = None,
                        dmx_address: int = 1, channel_count: int = 0) -> Optional[str]:
    """Why a test light would not be seen right now, or None if it would.

    Reads the output stage and nothing else. It must not touch a universe: a
    read that creates one starts transmitting it.
    """
    stage = getattr(dmx, "output_stage", None)
    if stage is None:
        return None
    if getattr(stage, "blackout_active", False):
        return ("Blackout is on, so a test light would stay dark. Release the "
                "blackout, then try again.")
    try:
        master = float(getattr(stage, "master", 1.0))
    except (TypeError, ValueError):
        master = 1.0
    if master <= 0.0:
        return ("The grand master is at zero, so a test light would stay dark. "
                "Raise it, then try again.")
    held_off = getattr(stage, "strobe_held_off", None)
    if universe is not None and callable(held_off):
        slots = range(dmx_address - 1, dmx_address - 1 + max(0, channel_count))
        if held_off(universe, slots):
            return ("This is a strobe fixture and strobes are switched off, so it "
                    "is being held dark. That is the safety setting working, not "
                    "a fault with the light.")
    return None


# ---------------------------------------------------------------------------
# Taking the show off the wire
# ---------------------------------------------------------------------------


@dataclass
class ShowSuspension:
    """The running show, parked while one fixture is lit on its own.

    The effects engine repaints every universe its rig occupies sixty times a
    second, so a test write would be overwritten before the operator could look
    up. Detaching the engine's DMX callback and zeroing the universes leaves
    the room dark with one fixture lit, which is also the only state in which
    "which one is that?" has an answer.
    """

    engine: Any = None
    dmx: Any = None
    # universe -> the levels the show was holding, or None when the universe
    # was created for the test and there was nothing to put back.
    parked: Dict[int, Optional[List[int]]] = field(default_factory=dict)
    previous_callback: Optional[Callable] = None
    active: bool = False

    def suspend(self, app_state: Any, universes: Iterable[int]) -> None:
        """Park the show. Called again while active, it only adds universes."""
        if not self.active:
            engine = getattr(app_state, "effects_engine", None)
            if engine is not None and hasattr(engine, "set_dmx_callback"):
                self.engine = engine
                self.previous_callback = getattr(engine, "_dmx_callback", None)
                engine.set_dmx_callback(None)
            self.dmx = getattr(app_state, "dmx_controller", None)
            self.active = True
            if self.dmx is not None:
                # Not everything on the wire is repainted by the engine: house
                # and work lights, a hazer, a static look parked through
                # /api/dmx. Those levels are the operator's and are put back
                # verbatim.
                for universe in list(getattr(self.dmx, "universes", {}).keys()):
                    self.parked[universe] = list(self.dmx.universes[universe].data)
                    self.dmx.universes[universe].data = [0] * 512

        dmx = self.dmx
        if dmx is None:
            return
        for universe in universes:
            if universe in self.parked:
                continue
            existing = getattr(dmx, "universes", {}).get(universe)
            self.parked[universe] = list(existing.data) if existing is not None else None
            dmx.get_universe(universe).data = [0] * 512

    def resume(self) -> None:
        """Hand the universes back to the show, at the levels it left them."""
        if not self.active:
            return
        self.active = False
        if self.engine is not None and hasattr(self.engine, "set_dmx_callback"):
            self.engine.set_dmx_callback(self.previous_callback)

        dmx = self.dmx
        if dmx is not None:
            for universe, data in self.parked.items():
                if data is None:
                    # Created for the test. Left in place it would go on
                    # sending zeros on a universe this box does not drive.
                    release = getattr(dmx, "release_universe", None)
                    if callable(release):
                        release(universe)
                    continue
                existing = getattr(dmx, "universes", {}).get(universe)
                if existing is not None:
                    existing.data = list(data)

        self.parked = {}
        self.dmx = None
        self.engine = None
        self.previous_callback = None


# ---------------------------------------------------------------------------
# The hold
# ---------------------------------------------------------------------------


@dataclass
class Hold:
    """The one fixture being looked at, and the look it is holding."""

    rig_id: int
    fixture_id: int
    label: str
    universe: int
    dmx_address: int
    channel_count: int
    values: Dict[int, int]
    check: str
    look: str
    last_seen: float = field(default_factory=time.monotonic)
    deadline: float = 0.0
    task: Optional[asyncio.Task] = None
    suspension: ShowSuspension = field(default_factory=ShowSuspension)
    finished: bool = False


class SetupCheckHold:
    """At most one fixture held lit for a setup check, process-wide.

    One, because the hold takes the show off the wire and two of them would
    fight over the same universes. ``service`` is the FixtureTestService: the
    hold is registered in its ``active_tests`` so the existing fixture-test
    stop endpoints release it too, and it cleans up after itself whoever
    cancels it.
    """

    def __init__(self):
        self.current: Optional[Hold] = None
        self._lock: Optional[asyncio.Lock] = None

    def _guard(self) -> asyncio.Lock:
        # Created lazily so this can be built before an event loop runs.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def active(self, rig_id: Optional[int] = None) -> Optional[Hold]:
        hold = self.current
        if hold is None or hold.finished or hold.task is None or hold.task.done():
            return None
        if rig_id is not None and hold.rig_id != rig_id:
            return None
        return hold

    def touch(self, rig_id: int) -> Optional[Hold]:
        """Heartbeat. Keeps the hold alive while someone is still looking."""
        hold = self.active(rig_id)
        if hold is not None:
            hold.last_seen = time.monotonic()
        return hold

    async def show(self, service: Any, app_state: Any, *, rig_id: int, fixture_id: int,
                   label: str, universe: int, dmx_address: int, channel_count: int,
                   values: Dict[int, int], check: str, look: str) -> Hold:
        """Hold ``values`` on a fixture, replacing whatever was held before."""
        async with self._guard():
            now = time.monotonic()
            hold = self.active()
            if hold is None:
                # Any other test on this fixture would zero it from under us.
                await service.stop_test(fixture_id)
                hold = Hold(rig_id=rig_id, fixture_id=fixture_id, label=label,
                            universe=universe, dmx_address=dmx_address,
                            channel_count=channel_count, values=dict(values),
                            check=check, look=look, last_seen=now,
                            deadline=now + HOLD_MAX_S)
                hold.suspension.suspend(app_state, [universe])
                self.current = hold
                try:
                    await service._set_fixture_channels(universe, dmx_address, hold.values)
                except Exception:
                    # A half-started hold would keep the show off the wire.
                    await self._finish(service, hold)
                    raise
                hold.task = asyncio.create_task(self._run(service, hold))
                service.active_tests[fixture_id] = hold.task
                return hold

            hold.last_seen = now
            hold.deadline = now + HOLD_MAX_S
            moved = (hold.fixture_id, hold.universe, hold.dmx_address, hold.channel_count) != (
                fixture_id, universe, dmx_address, channel_count)
            if moved:
                # The show stays parked across the change, so the room does not
                # come back on for a frame between two fixtures.
                await service._zero_fixture(hold.universe, hold.dmx_address, hold.channel_count)
                if service.active_tests.get(hold.fixture_id) is hold.task:
                    service.active_tests.pop(hold.fixture_id, None)
                if fixture_id != hold.fixture_id:
                    await service.stop_test(fixture_id)
                hold.suspension.suspend(app_state, [universe])
                service.active_tests[fixture_id] = hold.task
            hold.rig_id, hold.fixture_id, hold.label = rig_id, fixture_id, label
            hold.universe, hold.dmx_address, hold.channel_count = universe, dmx_address, channel_count
            hold.values, hold.check, hold.look = dict(values), check, look
            await service._set_fixture_channels(universe, dmx_address, hold.values)
            return hold

    async def release(self, service: Any, rig_id: Optional[int] = None) -> bool:
        """Fixture dark, show back on the wire. Safe to call when nothing is held."""
        async with self._guard():
            hold = self.current
            if hold is None or (rig_id is not None and hold.rig_id != rig_id):
                return False
            task = hold.task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:  # pragma: no cover - must not block the release
                    logger.exception("Setup check hold ended badly")
            await self._finish(service, hold)
            return True

    async def _run(self, service: Any, hold: Hold) -> None:
        try:
            while True:
                await asyncio.sleep(HOLD_REASSERT_S)
                now = time.monotonic()
                if now >= hold.deadline or now - hold.last_seen > HOLD_IDLE_TIMEOUT_S:
                    logger.info("Setup check on fixture %s released itself", hold.fixture_id)
                    return
                await service._set_fixture_channels(hold.universe, hold.dmx_address, hold.values)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Setup check hold failed - blacking the fixture out")
        finally:
            # Here, not in the canceller: FixtureTestService.stop_test only
            # cancels, and a fixture left lit with the show still parked is
            # the one outcome a check may not leave behind.
            await self._finish(service, hold)

    async def _finish(self, service: Any, hold: Hold) -> None:
        if hold.finished:
            return
        hold.finished = True
        try:
            await service._zero_fixture(hold.universe, hold.dmx_address, hold.channel_count)
        finally:
            hold.suspension.resume()
            if hold.task is not None and service.active_tests.get(hold.fixture_id) is hold.task:
                service.active_tests.pop(hold.fixture_id, None)
            if self.current is hold:
                self.current = None

    def state(self, hold: Optional[Hold]) -> Optional[Dict[str, Any]]:
        if hold is None:
            return None
        return {
            "rig_id": hold.rig_id,
            "fixture_id": hold.fixture_id,
            "label": hold.label,
            "check": hold.check,
            "look": hold.look,
            "seconds_left": max(0.0, round(hold.deadline - time.monotonic(), 1)),
        }


# Process-wide, like the walkthrough's sessions: both own the universes while
# they run, and each releases the other before it starts.
setup_hold = SetupCheckHold()
