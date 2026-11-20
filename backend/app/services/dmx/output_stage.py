"""
Output Stage
============

The last thing between every writer and the wire.

The show engine, the raw DMX routes, cues and fades, the test patterns, the
fixture tests and the identify walkthrough all end the same way: they leave
values in a universe buffer, and the transmitter sends whatever is there. This
stage sits in the transmitter, so it sees all of them and none of them can go
round it. It owns three things:

* the **grand master**, which scales light and never position;
* the **blackout latch**, which holds against every writer until released;
* the **flash limiter**, which caps how often light may jump up.

It works on bytes, and bytes do not say which slot is a dimmer and which is a
pan. The patch (``set_patch``) tells it. A slot the patch does not cover is
treated as light: an unknown channel that is dimmed or slowed by mistake is a
nuisance, an unknown channel that flashes through a blackout is the hazard.

The flash limiter
-----------------
A *flash* here is light rising by ``FLASH_FREE_RISE`` of full scale or more
inside ``FLASH_WINDOW_S``. Each light slot, and the rig as a whole, may do that
at most ``flash_limit_hz`` times in any one second. A rise that has no budget
left is not dropped, it is slowed to just under that slope, so a steady look
still arrives; it fades up instead of snapping. Falls are never limited, so
blackout is always immediate and the limiter cannot hold light on.

What it cannot see: a fixture's own strobe. A constant value on a shutter or
strobe channel makes the fixture flash with no change in the DMX at all, and
which values do that differs per profile. Those slots pass through untouched.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


SLOTS = 512

# Roles a patched slot can have. Anything else a patch says is read as LIGHT.
ROLE_INTENSITY = "intensity"                    # light, and the master scales it
ROLE_INTENSITY_INVERTED = "intensity_inverted"  # same, 0 is full (a CMY flag)
ROLE_COLOUR = "colour"                          # light, behind a dimmer the master scales
ROLE_COLOUR_INVERTED = "colour_inverted"
ROLE_FIXED = "fixed"                            # not light: position, wheels, shutter

_INVERTED = (ROLE_INTENSITY_INVERTED, ROLE_COLOUR_INVERTED)

# A rise this large (fraction of full scale) inside the window is a flash.
# Under the 25%-in-75ms the venue simulator counts, with room for sampling.
FLASH_FREE_RISE = 0.18
FLASH_WINDOW_S = 0.100
# Once a flash is allowed, how long its rising edge may keep climbing. An
# attack spread over a couple of frames is one flash, not one per frame.
FLASH_ATTACK_S = 0.075

# The limit before anything has said otherwise, and when what was said cannot
# be read as a rate. Matches the `no_strobe` safety profile.
STRICT_FLASH_HZ = 2.0
# With strobes switched off the limit never exceeds the general-audience
# three flashes a second, whatever cap is configured.
STROBE_OFF_MAX_HZ = 3.0

_HISTORY_ROWS = 8      # 100 ms of frames up to 80 fps
_MAX_GRANTS = 32       # flashes remembered per slot; also the highest usable limit
_EPS = 1e-9
_FORGET_AFTER_S = 5.0  # how long a universe that left the wire keeps its flash record


class StagedFrame(bytes):
    """Bytes that have been through the stage. The transmitter sends nothing else."""

    __slots__ = ()


def dark_frame() -> StagedFrame:
    """A universe of zeros. Dark needs no limiting."""
    return StagedFrame(bytes(SLOTS))


def frame_bytes(data: Any) -> bytes:
    """A universe's values as 512 wire bytes, whatever wrote them.

    The engine hands over clamped ints, but a manual or API write can leave a
    float (127.5), a stray out-of-range value or a short list behind.
    """
    try:
        out = bytes(data)
    except (TypeError, ValueError):
        try:
            values = list(data)
        except TypeError:
            values = []
        buf = bytearray(len(values))
        for i, value in enumerate(values):
            try:
                buf[i] = max(0, min(255, int(round(float(value)))))
            except (TypeError, ValueError, OverflowError):
                buf[i] = 0
        out = bytes(buf)
    if len(out) < SLOTS:
        out = out + bytes(SLOTS - len(out))
    return out[:SLOTS]


@dataclass
class _UniversePatch:
    """What the patch says about one universe's slots."""

    mastered: np.ndarray = field(default_factory=lambda: np.ones(SLOTS, dtype=bool))
    light: np.ndarray = field(default_factory=lambda: np.ones(SLOTS, dtype=bool))
    inverted: np.ndarray = field(default_factory=lambda: np.zeros(SLOTS, dtype=bool))
    unpatched: np.ndarray = field(default_factory=lambda: np.ones(SLOTS, dtype=bool))
    # Per fixture: (mastered slots, colour slots behind them). Its light is
    # the brightest of one times the brightest of the other.
    fixtures: List[Tuple[np.ndarray, np.ndarray]] = field(default_factory=list)


_UNPATCHED = _UniversePatch()


class _Budget:
    """Who has flashed, and when. One column per thing being limited."""

    def __init__(self, width: int):
        self.grants = np.full((_MAX_GRANTS, width), -np.inf)
        self.rising = np.zeros(width, dtype=bool)
        self.open_until = np.full(width, -np.inf)

    def decide(self, want: np.ndarray, level: np.ndarray, previous: np.ndarray,
               now: float, allowed: int, window: float) -> np.ndarray:
        """Which of the fast rises in `want` may not happen. Spends budget on the rest."""
        still = self.rising & (now <= self.open_until + _EPS) & (level >= previous)
        self.rising = still
        need = want & ~still
        if not need.any():
            return need
        if allowed <= 0:
            return need
        spent = np.count_nonzero(self.grants > now - window + _EPS, axis=0)
        granted = need & (spent < min(allowed, _MAX_GRANTS))
        columns = np.nonzero(granted)[0]
        if columns.size:
            oldest = np.argmin(self.grants[:, columns], axis=0)
            self.grants[oldest, columns] = now
            self.rising[columns] = True
            self.open_until[columns] = now + FLASH_ATTACK_S
        return need & ~granted


class _History:
    """The last few frames of what actually went out."""

    def __init__(self, width: int):
        self.levels = np.zeros((_HISTORY_ROWS, width))
        self.times = np.full(_HISTORY_ROWS, -np.inf)
        self.head = 0

    @property
    def previous(self) -> np.ndarray:
        return self.levels[self.head]

    def floor(self, now: float) -> np.ndarray:
        """The lowest level held at any point in the flash window."""
        inside = self.times >= now - FLASH_WINDOW_S - _EPS
        outside = ~inside
        if outside.any():
            # The level in force when the window opened is the newest frame
            # sent before it. Before any frame at all, that level is dark.
            candidates = np.where(outside, self.times, -np.inf)
            inside = inside.copy()
            inside[int(np.argmax(candidates))] = True
        return self.levels[inside].min(axis=0)

    def push(self, level: np.ndarray, now: float) -> None:
        self.head = (self.head + 1) % _HISTORY_ROWS
        self.levels[self.head] = level
        self.times[self.head] = now


def _fixture_light(dimmers: np.ndarray, colours: np.ndarray, level: np.ndarray) -> Tuple[float, float]:
    """One fixture's light, 0-1, measured two ways.

    First by its dimmer alone, which is how the venue simulator reads a flash
    and does not let a dim colour hide one. Then as dimmer times colour, which
    is what the room gets and the only one that sees colour flashing behind an
    open dimmer. A fixture with no dimmer has its colours in `dimmers`.
    """
    dimmer = float(level[dimmers].max()) / 255.0 if dimmers.size else 1.0
    colour = float(level[colours].max()) / 255.0 if colours.size else 1.0
    return (dimmer if dimmers.size else colour), dimmer * colour


def _share_of_rise(level: np.ndarray, before: np.ndarray, rising: np.ndarray, fits) -> np.ndarray:
    """Give every rising slot the same share of its rise, the largest that fits.

    Falls are left alone, so a share of zero is always available.
    """
    def shared(share: float) -> np.ndarray:
        return np.where(rising, np.floor(before + (level - before) * share), level)

    low, high = 0.0, 1.0
    for _ in range(10):
        middle = (low + high) / 2.0
        if fits(shared(middle)):
            low = middle
        else:
            high = middle
    return shared(low)


class _UniverseState:
    def __init__(self):
        self.history = _History(SLOTS)
        self.budget = _Budget(SLOTS)
        self.seen_lit = np.zeros(SLOTS, dtype=bool)
        self.last_seen = -np.inf
        self.patch: Optional[_UniversePatch] = None
        self.fixture_history = _History(0)
        self.fixture_budget = _Budget(0)

    def follow(self, patch: _UniversePatch) -> None:
        """Start the per-fixture record again when the rig under it changes."""
        if patch is not self.patch:
            self.patch = patch
            self.fixture_history = _History(2 * len(patch.fixtures))
            self.fixture_budget = _Budget(2 * len(patch.fixtures))


class OutputStage:
    """Grand master, blackout latch and flash limiter, applied to every frame sent."""

    def __init__(self):
        self._lock = threading.Lock()
        self._master = 1.0
        self._blackout = False
        self._strobe_allowed = False
        self._hz_cap: Optional[float] = None
        self._patch: Dict[int, _UniversePatch] = {}
        self._universes: Dict[int, _UniverseState] = {}
        self._rig_history = _History(2)
        self._rig_budget = _Budget(2)
        self.limited_frames = 0
        self.frames = 0

    # ------------------------------------------------------------------
    # Operator state
    # ------------------------------------------------------------------

    def set_master(self, level: float) -> float:
        """Set the grand master (0-1). Scales light only, never position."""
        try:
            value = float(level)
        except (TypeError, ValueError):
            raise ValueError("grand master must be a number between 0 and 1")
        if value != value:  # NaN
            raise ValueError("grand master must be a number between 0 and 1")
        with self._lock:
            self._master = max(0.0, min(1.0, value))
            return self._master

    @property
    def master(self) -> float:
        return self._master

    def blackout(self) -> None:
        """Latch the blackout. Every writer stays dark until restore()."""
        with self._lock:
            self._blackout = True

    def restore(self) -> None:
        with self._lock:
            self._blackout = False

    @property
    def blackout_active(self) -> bool:
        return self._blackout

    @property
    def output_master(self) -> float:
        """The scale light is actually sent at."""
        return 0.0 if self._blackout else self._master

    # ------------------------------------------------------------------
    # Flash policy
    # ------------------------------------------------------------------

    def set_flash_policy(self, strobe_allowed: bool, hz_cap: Any) -> None:
        """Take the venue's strobe switch and flash-rate cap.

        Switching strobes off does not lift the limit, it tightens it. A cap
        that cannot be read as a rate selects the strictest limit.
        """
        try:
            cap: Optional[float] = float(hz_cap)
        except (TypeError, ValueError):
            cap = None
        if cap is not None and not math.isfinite(cap):
            cap = None
        with self._lock:
            self._strobe_allowed = bool(strobe_allowed)
            self._hz_cap = cap

    @property
    def flash_limit_hz(self) -> float:
        """Flashes a second any slot, and the rig, may make."""
        cap = self._hz_cap
        if cap is None:
            cap = STRICT_FLASH_HZ
        cap = max(0.0, cap)
        if not self._strobe_allowed:
            cap = min(cap, STROBE_OFF_MAX_HZ)
        return min(cap, float(_MAX_GRANTS))

    def _allowance(self) -> Tuple[int, float]:
        """The limit as (flashes, in this many seconds)."""
        hz = self.flash_limit_hz
        if hz <= 0.0:
            return 0, 1.0
        # The second is stretched by the length of an attack: a flash is
        # counted when it is allowed, and may not be seen until it has risen.
        if hz < 1.0:
            return 1, 1.0 / hz + FLASH_WINDOW_S
        return int(math.floor(hz + _EPS)), 1.0 + FLASH_WINDOW_S

    # ------------------------------------------------------------------
    # Patch
    # ------------------------------------------------------------------

    def set_patch(self, patch: Optional[Mapping[int, Iterable[Mapping[int, str]]]]) -> None:
        """Say what each patched slot is.

        ``patch`` maps a universe to its fixtures, each a mapping of 0-based
        slot to role. Slots it leaves out stay unpatched, and so stay light.
        """
        built: Dict[int, _UniversePatch] = {}
        for universe, fixtures in (patch or {}).items():
            entry = _UniversePatch(
                mastered=np.ones(SLOTS, dtype=bool),
                light=np.ones(SLOTS, dtype=bool),
                inverted=np.zeros(SLOTS, dtype=bool),
                unpatched=np.ones(SLOTS, dtype=bool),
                fixtures=[],
            )
            for slots in fixtures:
                dimmers: List[int] = []
                colours: List[int] = []
                for slot, role in slots.items():
                    try:
                        slot = int(slot)
                    except (TypeError, ValueError):
                        continue
                    if not 0 <= slot < SLOTS:
                        continue
                    entry.unpatched[slot] = False
                    entry.light[slot] = role != ROLE_FIXED
                    entry.mastered[slot] = role != ROLE_FIXED and role not in (
                        ROLE_COLOUR, ROLE_COLOUR_INVERTED)
                    entry.inverted[slot] = role in _INVERTED
                    if role == ROLE_FIXED:
                        continue
                    # A fixture with no dimmer carries intensity in its colour
                    # slots; they are then the mastered ones, and its light is
                    # simply the brightest of them.
                    (dimmers if entry.mastered[slot] else colours).append(slot)
                if dimmers or colours:
                    entry.fixtures.append((
                        np.asarray(dimmers, dtype=np.intp),
                        np.asarray(colours, dtype=np.intp),
                    ))
            built[int(universe)] = entry
        with self._lock:
            self._patch = built

    # ------------------------------------------------------------------
    # The stage itself
    # ------------------------------------------------------------------

    def process(self, frames: Mapping[int, Any], now: float) -> Dict[int, StagedFrame]:
        """Turn what the writers left in the buffers into what may be sent.

        ``frames`` is every universe about to go out, and ``now`` a monotonic
        time in seconds. Called once per transmitted frame.
        """
        with self._lock:
            return self._process(frames, float(now))

    def _process(self, frames: Mapping[int, Any], now: float) -> Dict[int, StagedFrame]:
        self.frames += 1
        scale = 0.0 if self._blackout else self._master
        allowed, window = self._allowance()
        free = FLASH_FREE_RISE * 255.0

        # A universe that leaves the wire keeps its record for a while. Dropped
        # at once, starting and stopping a test pattern on a borrowed universe
        # would hand it a fresh flash budget every time.
        for gone in [u for u, state in self._universes.items()
                     if u not in frames and now - state.last_seen > _FORGET_AFTER_S]:
            del self._universes[gone]

        work = []
        limited = False
        for universe, data in frames.items():
            raw = np.frombuffer(frame_bytes(data), dtype=np.uint8)
            patch = self._patch.get(universe, _UNPATCHED)
            state = self._universes.get(universe)
            if state is None:
                state = self._universes[universe] = _UniverseState()
            state.last_seen = now

            # Everything below is in "light": 0 dark, 255 full, on every slot.
            level = raw.astype(np.float64)
            level[patch.inverted] = 255.0 - level[patch.inverted]
            if scale != 1.0:
                level[patch.mastered] = np.floor(level[patch.mastered] * scale)
            state.seen_lit |= patch.unpatched & (raw > 0)

            previous = state.history.previous
            ceiling = np.maximum(previous, state.history.floor(now) + free)
            want = patch.light & (level > ceiling + _EPS)
            denied = state.budget.decide(want, level, previous, now, allowed, window)
            if denied.any():
                level[denied] = np.floor(ceiling[denied])
                limited = True
            if self._limit_fixtures(patch, state, level, now, allowed, window):
                limited = True
            work.append((universe, raw, patch, state, level))

        if self._limit_rig(work, now, allowed, window):
            limited = True
        if limited:
            self.limited_frames += 1

        out: Dict[int, StagedFrame] = {}
        for universe, raw, patch, state, level in work:
            state.history.push(level, now)
            state.fixture_history.push(self._fixture_levels(patch, level), now)
            wire = level.copy()
            wire[patch.inverted] = 255.0 - wire[patch.inverted]
            sent = np.where(patch.light, wire, raw).astype(np.uint8)
            out[universe] = StagedFrame(sent.tobytes())
        return out

    # ------------------------------------------------------------------
    # Per-fixture and rig-wide limits
    # ------------------------------------------------------------------

    @staticmethod
    def _fixture_levels(patch: _UniversePatch, level: np.ndarray) -> np.ndarray:
        out = np.zeros(2 * len(patch.fixtures))
        for index, (dimmers, colours) in enumerate(patch.fixtures):
            out[2 * index], out[2 * index + 1] = _fixture_light(dimmers, colours, level)
        return out

    def _limit_fixtures(self, patch: _UniversePatch, state: _UniverseState,
                        level: np.ndarray, now: float, allowed: int, window: float) -> bool:
        """Hold each patched fixture to the limit, as well as each of its slots.

        The light of one fixture is spread over several slots. Red, green and
        blue each inside their own budget can flash the fixture three times as
        often, by taking turns.
        """
        state.follow(patch)
        if not patch.fixtures:
            return False
        light = self._fixture_levels(patch, level)
        previous = state.fixture_history.previous
        ceiling = np.maximum(previous, state.fixture_history.floor(now) + FLASH_FREE_RISE)
        denied = state.fixture_budget.decide(
            light > ceiling + _EPS, light, previous, now, allowed, window)
        if not denied.any():
            return False

        before_all = state.history.previous
        for index in np.unique(np.nonzero(denied)[0] // 2):
            dimmers, colours = patch.fixtures[index]
            slots = np.concatenate((dimmers, colours))
            pair = slice(2 * index, 2 * index + 2)
            held, limit = denied[pair], ceiling[pair]

            def fits(candidate: np.ndarray) -> bool:
                trial = level.copy()
                trial[slots] = candidate
                measured = np.array(_fixture_light(dimmers, colours, trial))
                return bool(np.all(measured[held] <= limit[held] + _EPS))

            before = before_all[slots]
            level[slots] = _share_of_rise(level[slots], before, level[slots] > before, fits)
        return True

    @staticmethod
    def _rig_level(work, levels: Sequence[np.ndarray]) -> np.ndarray:
        """Mean light across the rig, 0-1, in the two measures a fixture has.

        A slot outside the patch counts as a fixture once it has been lit.
        """
        by_dimmer = 0.0
        by_light = 0.0
        units = 0
        for (_, _, patch, state, _), level in zip(work, levels):
            for dimmers, colours in patch.fixtures:
                dimmer, light = _fixture_light(dimmers, colours, level)
                by_dimmer += dimmer
                by_light += light
                units += 1
            loose = state.seen_lit
            count = int(np.count_nonzero(loose))
            if count:
                lit = float(level[loose].sum()) / 255.0
                by_dimmer += lit
                by_light += lit
                units += count
        if not units:
            return np.zeros(2)
        return np.array([by_dimmer, by_light]) / units

    def _limit_rig(self, work, now: float, allowed: int, window: float) -> bool:
        """Hold the rig as a whole to the same limit as each slot and fixture.

        Fixtures that each stay inside their own budget can still add up to a
        rig that flashes faster than any of them, by taking turns.
        """
        if not work:
            self._rig_history.push(np.zeros(2), now)
            return False
        levels = [item[4] for item in work]
        rig = self._rig_level(work, levels)
        previous = self._rig_history.previous
        ceiling = np.maximum(previous, self._rig_history.floor(now) + FLASH_FREE_RISE)
        denied = self._rig_budget.decide(
            rig > ceiling + _EPS, rig, previous, now, allowed, window)
        if not denied.any():
            self._rig_history.push(rig, now)
            return False

        # No budget for the rig to jump. Give every rising light slot the same
        # share of its rise, the largest share that keeps the rig under the
        # slope. Falls are left alone, so a share of zero always fits.
        befores = [item[3].history.previous for item in work]
        rising = [
            item[2].light & (level > before)
            for item, level, before in zip(work, levels, befores)
        ]

        def shared(share: float) -> List[np.ndarray]:
            return [
                np.where(up, np.floor(before + (level - before) * share), level)
                for level, before, up in zip(levels, befores, rising)
            ]

        def fits(candidate: List[np.ndarray]) -> bool:
            return bool(np.all(self._rig_level(work, candidate)[denied] <= ceiling[denied] + _EPS))

        low, high = 0.0, 1.0
        for _ in range(10):
            middle = (low + high) / 2.0
            if fits(shared(middle)):
                low = middle
            else:
                high = middle
        held = shared(low)
        for item, level in zip(work, held):
            item[4][:] = level
        self._rig_history.push(self._rig_level(work, held), now)
        return True

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "grand_master": self._master,
            "blackout": self._blackout,
            "output_master": self.output_master,
            "strobe_allowed": self._strobe_allowed,
            "flash_limit_hz": self.flash_limit_hz,
            "frames": self.frames,
            "limited_frames": self.limited_frames,
            "patched_universes": sorted(self._patch),
        }
