"""
Output Watchdog
===============

The transmitter has its own thread and outlives a hung show engine. What it
went on sending was the engine's last frame, so a hang left the rig frozen on
whatever it happened to be showing, lit, for as long as the process lived.

The output stage now fades to black when the engine's heartbeat stops. These
tests drive the stage on its own with a made-up clock. Nothing here sleeps and
nothing is sent anywhere.
"""

import numpy as np
import pytest

from app.services.dmx.output_stage import (
    ROLE_COLOUR, ROLE_FIXED, ROLE_INTENSITY, WATCHDOG_HOLD, WATCHDOG_SECONDS,
    OutputStage,
)

FPS = 40
DT = 1.0 / FPS
X = 1.0   # shorter than the default, so the made-up clock has less far to go

PAN, PAN_FINE, TILT, TILT_FINE, DIMMER, RED, GREEN, BLUE = range(8)
PATCH = {0: [
    {PAN: ROLE_FIXED, PAN_FINE: ROLE_FIXED, TILT: ROLE_FIXED, TILT_FINE: ROLE_FIXED,
     DIMMER: ROLE_INTENSITY, RED: ROLE_COLOUR, GREEN: ROLE_COLOUR, BLUE: ROLE_COLOUR},
    {100: ROLE_INTENSITY, 101: ROLE_INTENSITY, 102: ROLE_INTENSITY},
]}

LOOK = [200] * 512


class Wire:
    """A stage being stepped at 40 fps, and everything it has let out."""

    def __init__(self, seconds=X):
        self.stage = OutputStage()
        self.stage.set_watchdog_seconds(seconds)
        self.now = 0.0
        self.times = []
        self.sent = []

    def run(self, seconds, look=LOOK, engine_alive=True):
        """Transmit for `seconds`. The engine beats before each frame, or it does not."""
        for _ in range(int(round(seconds * FPS))):
            if engine_alive:
                self.stage.heartbeat()
            frame = look(self.now) if callable(look) else look
            out = self.stage.process({0: frame}, self.now)
            self.times.append(self.now)
            self.sent.append(np.frombuffer(out[0], dtype=np.uint8))
            self.now += DT
        return self

    def since(self, t):
        return [frame for when, frame in zip(self.times, self.sent) if when >= t - 1e-9]

    def slot(self, index, since=0.0):
        return np.array([int(frame[index]) for frame in self.since(since)])


# ---------------------------------------------------------------------------
# A look that sits still is not a hang
# ---------------------------------------------------------------------------


def test_a_still_look_stays_lit_for_as_long_as_the_engine_is_ticking():
    """Not one byte changes for twenty times the limit. The beats are what count."""
    wire = Wire().run(20 * X)

    assert wire.stage.watchdog_armed
    assert all(set(frame) == {200} for frame in wire.sent)
    assert wire.stage.watchdog_trips == 0
    assert wire.stage.status()["watchdog"]["tripped"] is False


def test_a_dark_scene_held_by_a_ticking_engine_comes_up_when_asked():
    wire = Wire().run(5 * X, look=[0] * 512)
    wire.run(DT)
    assert set(wire.sent[-1]) == {200}


def test_a_stage_no_engine_ever_beat_does_not_fade():
    """Raw writes with no engine attached are not a hung engine."""
    wire = Wire().run(10 * X, engine_alive=False)

    assert not wire.stage.watchdog_armed
    assert all(set(frame) == {200} for frame in wire.sent)


# ---------------------------------------------------------------------------
# The engine stops
# ---------------------------------------------------------------------------


def test_the_wire_is_black_within_the_limit_once_the_engine_stops():
    wire = Wire().run(3 * X)
    stopped = wire.now - DT          # the last frame the engine beat for
    wire.run(4 * X, engine_alive=False)

    level = wire.slot(0, since=stopped)
    assert level[0] == 200
    assert np.all(np.diff(level) <= 0), "the fade went back up"
    assert 0 < min(level[level > 0]) < 200, "it cut out rather than faded"

    by_limit = wire.since(stopped + X)
    assert by_limit, "the run never reached the limit"
    assert all(not frame.any() for frame in by_limit), "light on the wire past the limit"
    assert wire.stage.watchdog_trips == 1
    assert wire.stage.status()["watchdog"]["tripped"] is True
    assert wire.stage.watchdog_level == 0.0


def test_a_short_stall_does_not_dim_the_room():
    """The light holds for the first part of the limit; only then does it fade."""
    wire = Wire().run(X)
    stalled = wire.now
    wire.run(X * WATCHDOG_HOLD - DT, engine_alive=False)
    wire.run(X)

    assert set(wire.slot(0, since=stalled)) == {200}
    assert wire.stage.watchdog_trips == 0


def test_the_frozen_frame_is_not_what_stays_on_the_wire():
    """Black means black for good, not a dip. An hour on, still nothing."""
    wire = Wire().run(X).run(2 * X, engine_alive=False)
    wire.now += 3600.0
    wire.run(X, engine_alive=False)

    assert all(not frame.any() for frame in wire.since(3600.0))


def test_values_that_keep_changing_do_not_count_as_the_engine_being_alive():
    """Some other writer is still moving the buffer. The engine is still dead."""
    wire = Wire().run(X)
    stopped = wire.now - DT
    wire.run(3 * X, look=lambda t: [100 + int(t * 400) % 150] * 512, engine_alive=False)

    assert all(not frame.any() for frame in wire.since(stopped + X))


def test_a_new_write_after_the_fade_does_not_light_the_rig():
    wire = Wire().run(X).run(2 * X, engine_alive=False)
    wire.run(X, look=[255] * 512, engine_alive=False)

    assert all(not frame.any() for frame in wire.since(wire.now - X))


def test_output_follows_the_engine_again_when_it_comes_back():
    wire = Wire().run(X).run(3 * X, engine_alive=False)
    assert not wire.sent[-1].any()

    back = wire.now
    wire.run(X)

    assert set(wire.sent[-1]) == {200}
    assert wire.stage.watchdog_level == 1.0
    assert wire.stage.status()["watchdog"]["tripped"] is False
    assert all(frame.max() <= 200 for frame in wire.since(back)), "came back brighter than asked"

    # And it is watching again: a second hang fades like the first.
    stopped = wire.now - DT
    wire.run(2 * X, engine_alive=False)
    assert all(not frame.any() for frame in wire.since(stopped + X))
    assert wire.stage.watchdog_trips == 2


def test_an_engine_stopped_on_purpose_is_not_a_hang():
    wire = Wire().run(X)
    wire.stage.stand_down_watchdog()
    wire.run(5 * X, engine_alive=False)

    assert not wire.stage.watchdog_armed
    assert all(set(frame) == {200} for frame in wire.sent)

    # Started again, it is watched again.
    wire.run(X)
    stopped = wire.now - DT
    wire.run(2 * X, engine_alive=False)
    assert all(not frame.any() for frame in wire.since(stopped + X))


@pytest.mark.parametrize("silent_for", [0.75 * X, 3 * X], ids=["mid-fade", "black"])
def test_stopping_an_engine_that_already_hung_does_not_bring_the_frozen_frame_back(silent_for):
    """The engine hangs, the rig fades, and then someone presses stop or shuts down.

    That stop is not what silenced the engine. Standing the watchdog down for
    it would put the frozen frame straight back on the wire.
    """
    wire = Wire().run(X)
    stopped = wire.now - DT
    wire.run(silent_for, engine_alive=False)
    assert wire.sent[-1][0] < 200

    wire.stage.stand_down_watchdog()
    asked = wire.now
    wire.run(3 * X, engine_alive=False)

    assert wire.stage.watchdog_armed
    assert np.all(np.diff(wire.slot(0, since=stopped)) <= 0), "the frozen frame came back"
    assert all(not frame.any() for frame in wire.since(max(asked, stopped + X)))

    # Only the engine producing frames again lifts it.
    wire.run(X)
    assert set(wire.sent[-1]) == {200}


# ---------------------------------------------------------------------------
# Black is light at zero, and nothing else moves
# ---------------------------------------------------------------------------


def test_the_fade_takes_the_light_and_leaves_the_heads_where_they_are():
    wire = Wire()
    wire.stage.set_patch(PATCH)
    look = [0] * 512
    look[PAN], look[PAN_FINE], look[TILT], look[TILT_FINE] = 40, 41, 150, 151
    look[DIMMER] = 255
    look[RED], look[GREEN], look[BLUE] = 255, 128, 0
    look[100:103] = [255, 255, 255]
    look[300] = 255                      # outside the patch: treated as light

    wire.run(X, look=look)
    stopped = wire.now - DT
    wire.run(3 * X, look=look, engine_alive=False)

    for frame in wire.since(stopped):
        assert list(frame[PAN:TILT_FINE + 1]) == [40, 41, 150, 151], "a head moved"
    for frame in wire.since(stopped + X):
        assert frame[DIMMER] == 0, "the mover is still lit"
        assert not frame[100:103].any(), "a par with no dimmer is still lit"
        assert frame[300] == 0, "an unpatched slot is still lit"


# ---------------------------------------------------------------------------
# The rest of the stage is still there
# ---------------------------------------------------------------------------


def test_the_fade_starts_from_the_grand_master_not_from_full():
    wire = Wire()
    wire.stage.set_master(0.5)
    wire.run(X)
    stopped = wire.now - DT
    wire.run(3 * X, engine_alive=False)

    level = wire.slot(0)
    assert level.max() == 100
    assert np.all(np.diff(wire.slot(0, since=stopped)) <= 0)
    assert not wire.sent[-1].any()


def test_a_latched_blackout_holds_while_the_engine_ticks_and_after_it_comes_back():
    wire = Wire()
    wire.stage.blackout()
    wire.run(X).run(3 * X, engine_alive=False).run(X)
    assert all(not frame.any() for frame in wire.sent), "the watchdog lifted a blackout"

    wire.stage.restore()
    wire.run(DT)
    assert set(wire.sent[-1]) == {200}


def test_coming_back_from_the_fade_is_still_held_to_the_flash_limit():
    """An engine that hangs and recovers over and over must not strobe the room."""
    from tests.unit.test_output_stage import worst_flashes_per_second

    wire = Wire(seconds=0.2)
    wire.stage.set_flash_policy(False, 2.0)
    for _ in range(40):
        wire.run(0.05, look=[255] * 512)
        wire.run(0.3, look=[255] * 512, engine_alive=False)

    level = wire.slot(0) / 255.0
    assert level.max() == 1.0 and level.min() == 0.0
    assert worst_flashes_per_second(wire.times, level) <= 2


def test_strobe_fixtures_stay_held_off_through_a_hang_and_back():
    wire = Wire()
    wire.stage.set_patch({0: [{10: ROLE_INTENSITY, 11: ROLE_FIXED}]}, {0: [10, 11]})
    wire.stage.set_flash_policy(False, 2.0)
    wire.run(X).run(2 * X, engine_alive=False).run(X)

    assert all(frame[10] == 0 and frame[11] == 0 for frame in wire.sent)


# ---------------------------------------------------------------------------
# The limit itself
# ---------------------------------------------------------------------------


def test_the_default_limit_is_two_seconds():
    assert WATCHDOG_SECONDS == 2.0
    assert OutputStage().watchdog_seconds == 2.0


def test_the_limit_can_be_set():
    wire = Wire(seconds=4.0).run(1.0)
    stopped = wire.now - DT
    wire.run(6.0, engine_alive=False)

    assert set(wire.slot(0, since=stopped)[:int(2.0 * FPS)]) == {200}, "faded early"
    assert all(not frame.any() for frame in wire.since(stopped + 4.0))


@pytest.mark.parametrize("nonsense", [0, -1, None, "soon", float("nan"), float("inf")])
def test_a_limit_that_makes_no_sense_selects_the_default_and_never_switches_it_off(nonsense):
    stage = OutputStage()
    stage.set_watchdog_seconds(0.5)
    assert stage.set_watchdog_seconds(nonsense) == WATCHDOG_SECONDS

    stage.heartbeat()
    stage.process({0: LOOK}, 0.0)
    out = stage.process({0: LOOK}, WATCHDOG_SECONDS)
    assert not any(out[0])
