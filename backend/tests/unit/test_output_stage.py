"""
Output Stage
============

The grand master, the blackout latch and the flash limit used to live in the
show engine, so they covered the show and nothing else. A raw channel write lit
a fixture through a latched blackout, and with strobes switched off a manual
strobe still put an 8 Hz full-rig flicker on the wire.

These tests drive the stage on its own, with a made-up clock, and count flashes
with a meter that shares no code with the limiter.
"""

import math

import numpy as np
import pytest

from app.services.dmx.output_stage import (
    ROLE_COLOUR, ROLE_FIXED, ROLE_INTENSITY, ROLE_INTENSITY_INVERTED,
    STRICT_FLASH_HZ, STROBE_OFF_MAX_HZ, OutputStage, StagedFrame, frame_bytes,
)

FPS = 40
DT = 1.0 / FPS

# A mover at slots 0-7 and a par with no dimmer at slots 100-102.
PAN, PAN_FINE, TILT, TILT_FINE, DIMMER, RED, GREEN, BLUE = range(8)
PATCH = {0: [
    {PAN: ROLE_FIXED, PAN_FINE: ROLE_FIXED, TILT: ROLE_FIXED, TILT_FINE: ROLE_FIXED,
     DIMMER: ROLE_INTENSITY, RED: ROLE_COLOUR, GREEN: ROLE_COLOUR, BLUE: ROLE_COLOUR},
    {100: ROLE_INTENSITY, 101: ROLE_INTENSITY, 102: ROLE_INTENSITY},
]}


# ---------------------------------------------------------------------------
# An independent flash meter
# ---------------------------------------------------------------------------


def worst_flashes_per_second(times, series, rise=0.25, within=0.075):
    """Most flashes in any one second: a rise of `rise` or more inside `within`.

    The venue simulator's definition (scripts/venue_sim), read against the
    lowest level in the window rather than the level at its start, which only
    ever counts more.
    """
    times = np.asarray(times, dtype=float)
    series = np.asarray(series, dtype=float)
    flashing = np.zeros(len(series), dtype=bool)
    for i in range(1, len(series)):
        start = np.searchsorted(times, times[i] - within - 1e-9)
        flashing[i] = series[i] - series[start:i + 1].min() >= rise
    starts = [i for i in range(1, len(series)) if flashing[i] and not flashing[i - 1]]
    # One rise still climbing can cross the threshold, slip a hair under it as
    # the window slides and cross again. That is one flash. A second one needs
    # the light to have fallen at all in between; 0.02 is rounding, not a fall.
    kept = []
    for i in starts:
        if kept:
            since = series[kept[-1]:i + 1]
            if (np.maximum.accumulate(since) - since).max() < 0.02:
                continue
        kept.append(i)
    worst = _worst_in_a_second(times[kept])

    # On the simulator's own 25 ms grid, count its way as well and take the worse.
    if len(times) > 4 and np.allclose(np.diff(times), 0.025, atol=1e-6):
        worst = max(worst, venue_sim_flashes(times, series, rise))
    return worst


def _worst_in_a_second(edges):
    edges = np.asarray(edges, dtype=float)
    if edges.size == 0:
        return 0
    return max(int(np.count_nonzero((edges >= t) & (edges < t + 1.0))) for t in edges)


def venue_sim_flashes(times, series, rise=0.25):
    """scripts/venue_sim/venue_sim.py `flashes`, line for line: rises over three 25 ms frames."""
    series = np.asarray(series, dtype=float)
    d3 = series[3:] - series[:-3]
    edges = np.where((d3[1:] >= rise) & (d3[:-1] < rise))[0]
    return _worst_in_a_second(np.asarray(times, dtype=float)[edges])


def play(stage, source, seconds, start=0.0):
    """Feed `source(t) -> {universe: frame}` through the stage at 40 fps."""
    times, asked, sent = [], [], []
    for n in range(int(round(seconds * FPS))):
        t = start + n * DT
        frames = source(t)
        out = stage.process(frames, t)
        times.append(t)
        asked.append({u: np.frombuffer(frame_bytes(f), dtype=np.uint8) for u, f in frames.items()})
        sent.append({u: np.frombuffer(f, dtype=np.uint8) for u, f in out.items()})
    return np.asarray(times), asked, sent


def slot(frames, index, universe=0):
    return np.array([f[universe][index] for f in frames]) / 255.0


def square(hz, duty=0.5, offset=0.0):
    return lambda t: 255 if ((t + offset) * hz) % 1.0 < duty else 0


# ---------------------------------------------------------------------------
# Passing things through
# ---------------------------------------------------------------------------


def test_a_steady_frame_goes_out_as_it_came_in():
    stage = OutputStage()
    frame = [(i * 7) % 256 for i in range(512)]
    stage.process({0: frame}, 0.0)
    for n in range(1, 40):
        out = stage.process({0: frame}, n * DT)
    assert isinstance(out[0], StagedFrame)
    assert list(out[0]) == frame


def test_one_step_up_is_not_a_strobe():
    """Bringing a look up from dark is a single flash, and arrives at once."""
    stage = OutputStage()
    out = stage.process({0: [255] * 512}, 0.0)
    assert set(out[0]) == {255}


def test_falls_are_never_slowed():
    stage = OutputStage()
    stage.process({0: [255] * 512}, 0.0)
    out = stage.process({0: [0] * 512}, DT)
    assert not any(out[0])


# ---------------------------------------------------------------------------
# The flash limit
# ---------------------------------------------------------------------------


def test_a_manual_strobe_is_held_to_the_limit_with_strobes_off():
    """An 8 Hz full-on, full-off write with strobes disabled: the finding, at its plainest."""
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    wave = square(8.0)
    times, asked, sent = play(stage, lambda t: {0: [wave(t)] * 512}, 6.0)

    assert worst_flashes_per_second(times, slot(asked, 0)) >= 8, "the test is not strobing"
    for index in (0, 5, 255, 511):
        assert worst_flashes_per_second(times, slot(sent, index)) <= 2
    rig = np.array([f[0].mean() for f in sent]) / 255.0
    assert worst_flashes_per_second(times, rig) <= 2


@pytest.mark.parametrize("hz", [3.5, 5.0, 8.0, 12.0, 20.0])
@pytest.mark.parametrize("duty", [0.2, 0.5, 0.8])
def test_no_rate_or_duty_gets_past_the_limit(hz, duty):
    stage = OutputStage()
    stage.set_flash_policy(False, 3.0)
    wave = square(hz, duty)
    times, _, sent = play(stage, lambda t: {0: [wave(t)] * 8}, 5.0)
    assert worst_flashes_per_second(times, slot(sent, 0)) <= 3


def test_a_strobe_inside_the_limit_is_left_alone():
    stage = OutputStage()
    stage.set_flash_policy(True, 3.0)
    wave = square(2.5, 0.3)
    times, asked, sent = play(stage, lambda t: {0: [wave(t)] * 8}, 5.0)
    assert [list(f[0]) for f in sent] == [list(f[0]) for f in asked]


def test_a_rise_with_no_budget_left_still_arrives():
    """The limiter slows a rise it cannot allow. It does not leave the room dark."""
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    wave = square(8.0)
    play(stage, lambda t: {0: [wave(t)] * 8}, 1.0)
    stage.process({0: [0] * 8}, 1.0)
    times, _, sent = play(stage, lambda t: {0: [255] * 8}, 1.0, start=1.0 + DT)
    level = slot(sent, 0)
    assert level[-1] == 1.0, "a steady look never came up"
    assert np.all(np.diff(level) >= 0)


def test_turn_taking_cannot_flash_the_rig_faster_than_any_one_slot():
    """Four groups each inside the limit, a quarter of a beat apart: 8 rig flashes a second."""
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    waves = [square(2.0, 0.12, offset=k / 8.0) for k in range(4)]

    def source(t):
        return {0: [w(t) for w in waves]}

    times, asked, sent = play(stage, source, 6.0)

    def rig(frames):
        return np.array([f[0][:4].mean() for f in frames]) / 255.0

    assert worst_flashes_per_second(times, rig(asked)) >= 6, "the test is not flashing the rig"
    assert worst_flashes_per_second(times, rig(sent)) <= 2


def test_the_rig_limit_spans_universes():
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    waves = [square(2.0, 0.12, offset=k / 8.0) for k in range(4)]
    times, _, sent = play(stage, lambda t: {u: [waves[u](t)] for u in range(4)}, 6.0)
    rig = np.array([np.mean([f[u][0] for u in range(4)]) for f in sent]) / 255.0
    assert worst_flashes_per_second(times, rig) <= 2


def test_colour_flashing_behind_an_open_dimmer_is_limited():
    stage = OutputStage()
    stage.set_patch(PATCH)
    stage.set_flash_policy(False, 2.0)
    wave = square(8.0)

    def source(t):
        frame = [0] * 512
        frame[DIMMER] = 255
        frame[RED] = frame[GREEN] = frame[BLUE] = wave(t)
        return {0: frame}

    times, _, sent = play(stage, source, 5.0)
    assert worst_flashes_per_second(times, slot(sent, RED)) <= 2


def test_colours_taking_turns_cannot_flash_a_fixture_faster_than_the_limit():
    """A par with no dimmer: red, green and blue each at 2 Hz, a third of a beat apart."""
    stage = OutputStage()
    # Enough dark fixtures around it that the rig as a whole barely moves, so
    # it is the limit on the fixture that is being tested and not the rig's.
    bystanders = [{200 + i: ROLE_INTENSITY} for i in range(12)]
    stage.set_patch({0: PATCH[0] + bystanders})
    stage.set_flash_policy(False, 2.0)
    waves = [square(2.0, 0.12, offset=k / 6.0) for k in range(3)]

    def source(t):
        frame = [0] * 512
        frame[100:103] = [w(t) for w in waves]
        return {0: frame}

    times, asked, sent = play(stage, source, 6.0)

    def fixture(frames):
        return np.array([f[0][100:103].max() for f in frames]) / 255.0

    assert worst_flashes_per_second(times, fixture(asked)) >= 6, "the test is not flashing"
    assert worst_flashes_per_second(times, fixture(sent)) <= 2


def test_a_universe_that_comes_and_goes_does_not_get_a_fresh_budget_each_time():
    """A test pattern started and stopped over and over, on a universe it borrows."""
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    times, level = [], []
    was_lit = False
    for n in range(6 * FPS):
        t = n * DT
        lit = (t * 8.0) % 1.0 < 0.5
        if lit:
            frames = {3: [255] * 8}
        elif was_lit:
            frames = {3: [0] * 8}   # the controller blacks a universe out before it lets go
        else:
            frames = {}
        was_lit = lit
        out = stage.process(frames, t)
        times.append(t)
        level.append(out[3][0] / 255.0 if 3 in out else 0.0)
    assert max(level) == 1.0
    assert worst_flashes_per_second(times, level) <= 2


def test_position_is_never_limited():
    stage = OutputStage()
    stage.set_patch(PATCH)
    stage.set_flash_policy(False, 2.0)
    wave = square(8.0)

    def source(t):
        frame = [0] * 512
        frame[PAN] = frame[TILT] = wave(t)
        return {0: frame}

    _, asked, sent = play(stage, source, 3.0)
    assert list(slot(sent, PAN)) == list(slot(asked, PAN))
    assert list(slot(sent, TILT)) == list(slot(asked, TILT))


def test_toggling_blackout_is_not_a_way_to_strobe():
    stage = OutputStage()
    stage.set_flash_policy(False, 2.0)
    times, sent = [], []
    for n in range(6 * FPS):
        t = n * DT
        (stage.blackout if (t * 8.0) % 1.0 < 0.5 else stage.restore)()
        sent.append(stage.process({0: [255] * 8}, t)[0][0] / 255.0)
        times.append(t)
    assert worst_flashes_per_second(times, sent) <= 2


# ---------------------------------------------------------------------------
# Flash policy fails closed
# ---------------------------------------------------------------------------


def test_the_limit_before_anyone_sets_one_is_the_strictest():
    assert OutputStage().flash_limit_hz == STRICT_FLASH_HZ


@pytest.mark.parametrize("cap", [None, "fast", math.nan, math.inf])
def test_a_cap_that_is_not_a_rate_selects_the_strictest(cap):
    stage = OutputStage()
    stage.set_flash_policy(True, cap)
    assert stage.flash_limit_hz == STRICT_FLASH_HZ


def test_switching_strobes_off_tightens_a_loose_cap():
    stage = OutputStage()
    stage.set_flash_policy(True, 18.0)
    assert stage.flash_limit_hz == 18.0
    stage.set_flash_policy(False, 18.0)
    assert stage.flash_limit_hz == STROBE_OFF_MAX_HZ
    stage.set_flash_policy(False, 2.0)
    assert stage.flash_limit_hz == 2.0


def test_a_cap_of_zero_allows_no_flash_but_still_lights_the_room():
    stage = OutputStage()
    stage.set_flash_policy(False, 0.0)
    times, _, sent = play(stage, lambda t: {0: [255] * 4}, 2.0)
    level = slot(sent, 0)
    assert worst_flashes_per_second(times, level) == 0
    assert level[-1] == 1.0


# ---------------------------------------------------------------------------
# Blackout and the grand master
# ---------------------------------------------------------------------------


def lit_frame():
    frame = [0] * 512
    frame[PAN], frame[PAN_FINE], frame[TILT], frame[TILT_FINE] = 200, 17, 90, 3
    frame[DIMMER] = 255
    frame[RED], frame[GREEN], frame[BLUE] = 255, 128, 64
    frame[100], frame[101], frame[102] = 255, 128, 0
    frame[300] = 255  # nothing is patched here
    return frame


def test_blackout_darkens_every_writer_and_holds_position():
    stage = OutputStage()
    stage.set_patch(PATCH)
    stage.blackout()
    for n in range(10):
        out = stage.process({0: lit_frame()}, n * DT)[0]
        assert out[DIMMER] == 0
        assert out[100:103] == bytes(3), "a par with no dimmer carries its light in its colour"
        assert out[300] == 0, "an unpatched slot must not light through a blackout"
        assert list(out[PAN:TILT_FINE + 1]) == [200, 17, 90, 3], "blackout must not move a head"

    stage.restore()
    assert stage.process({0: lit_frame()}, 1.0)[0][DIMMER] == 255


def test_blackout_covers_a_universe_nobody_patched():
    stage = OutputStage()
    stage.set_patch(PATCH)
    stage.blackout()
    assert not any(stage.process({7: [255] * 512}, 0.0)[7])


def test_master_scales_light_and_never_position():
    stage = OutputStage()
    stage.set_patch(PATCH)
    stage.set_master(0.5)
    out = stage.process({0: lit_frame()}, 0.0)[0]
    assert out[DIMMER] == 127
    assert list(out[RED:BLUE + 1]) == [255, 128, 64], "colour behind a dimmer is not scaled twice"
    assert list(out[100:103]) == [127, 64, 0]
    assert out[300] == 127
    assert list(out[PAN:TILT_FINE + 1]) == [200, 17, 90, 3]


def test_blackout_closes_a_subtractive_flag():
    """On a CMY fixture with no dimmer, 0 is fully open: dark is 255."""
    stage = OutputStage()
    stage.set_patch({0: [{0: ROLE_INTENSITY_INVERTED, 1: ROLE_INTENSITY_INVERTED,
                          2: ROLE_INTENSITY_INVERTED}]})
    assert list(stage.process({0: [0, 0, 0]}, 0.0)[0][:3]) == [0, 0, 0]
    stage.blackout()
    assert list(stage.process({0: [0, 0, 0]}, DT)[0][:3]) == [255, 255, 255]


@pytest.mark.parametrize("level", ["loud", None, math.nan])
def test_master_refuses_a_level_that_is_not_a_number(level):
    stage = OutputStage()
    with pytest.raises(ValueError):
        stage.set_master(level)
    assert stage.master == 1.0


def test_a_malformed_buffer_still_goes_out_as_a_universe():
    out = OutputStage().process({0: [127.5, 300, -4, "x", None]}, 0.0)[0]
    assert len(out) == 512
    assert list(out[:5]) == [128, 255, 0, 0, 0]
