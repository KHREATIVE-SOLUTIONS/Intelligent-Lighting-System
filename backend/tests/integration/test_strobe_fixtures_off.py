"""
Strobe Fixtures Off, At The Wire
================================

The owner's decision: with strobes disabled, a dedicated strobe fixture outputs
fully off - dimmer 0 and no flashes - whoever is writing. Pars, movers and
battens keep running, under the same flash-rate cap as before.

Read off the packets a recorder was handed in place of a socket, as in
test_output_stage_wire. No socket is opened and no packet leaves the process.

The rig here is chosen for what could be confused with a strobe and is not: the
mover has a shutter channel and the batten has a strobe channel.
"""

import asyncio
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.schemas.dmx import DMXFixtureState, DMXFrame
from app.services.dmx.dmx_controller import DMXController
from app.services.effects import lfo_engine as lfo_module
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import (
    Fixture, FixtureGroupManager, fixture_strobe_slots, is_strobe_fixture,
)
from app.services.effects.lfo_engine import LFOEngine
from app.services.fixture_test.fixture_test_service import FixtureTestService

from tests.integration.test_output_stage_wire import Recorder
from tests.unit.test_output_stage import worst_flashes_per_second

WIRE_FPS = 40
ENGINE_FPS = 60

MOVER = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4, 'shutter': 5,
         'red': 6, 'green': 7, 'blue': 8}
BATTEN = {'dimmer': 0, 'strobe': 1, 'red': 2, 'green': 3, 'blue': 4}
PAR = {'red': 0, 'green': 1, 'blue': 2}
STROBE = {'dimmer': 0, 'strobe': 1, 'other': 2, 'speed': 3}            # the presets' strobe
COLOUR_STROBE = {'dimmer': 0, 'shutter': 1, 'red': 2, 'green': 3, 'blue': 4, 'macro': 5}

# 1-based DMX addresses. Slots below are 0-based, as they sit in a frame.
MOVER_AT, BATTEN_AT, PAR_AT, STROBE_AT, COLOUR_STROBE_AT = 1, 51, 101, 201, 211

MOVER_DIMMER, MOVER_SHUTTER = 4, 5
BATTEN_DIMMER, BATTEN_STROBE = 50, 51
PAR_RED = 100
STROBE_DIMMER, STROBE_RATE = 200, 201
STROBE_SLOTS = list(range(200, 204)) + list(range(210, 216))
OTHER_LIGHT = {"mover": MOVER_DIMMER, "batten": BATTEN_DIMMER, "par": PAR_RED}


def rig():
    manager = FixtureGroupManager()
    manager.add_fixtures([
        Fixture(id="mh", name="Mover", dmx_address=MOVER_AT, channels=dict(MOVER),
                fixture_type="mover"),
        Fixture(id="bat", name="Batten", dmx_address=BATTEN_AT, channels=dict(BATTEN),
                fixture_type="bar", pan_range=0.0, tilt_range=0.0),
        Fixture(id="par", name="Par", dmx_address=PAR_AT, channels=dict(PAR),
                fixture_type="par", pan_range=0.0, tilt_range=0.0),
        Fixture(id="st", name="Strobe", dmx_address=STROBE_AT, channels=dict(STROBE),
                fixture_type="strobe", pan_range=0.0, tilt_range=0.0),
        Fixture(id="cst", name="Colour Strobe", dmx_address=COLOUR_STROBE_AT,
                channels=dict(COLOUR_STROBE), fixture_type="strobe",
                pan_range=0.0, tilt_range=0.0),
    ])
    return manager


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.broadcast = False
    ctrl.socket = Recorder()
    ctrl.is_connected = True   # no thread: the tests step the transmitter
    return ctrl


def live_engine(controller, **config):
    """An engine wired to the controller the way main.py wires it, strobes allowed."""
    settings = dict(fps=ENGINE_FPS, strobe_enabled=True, accessibility_mode="performance",
                    strobe_hz_cap=18.0)
    settings.update(config)
    engine = EffectsEngine(EffectsConfig(**settings))
    engine.set_fixture_manager(rig())
    engine.set_dmx_callback(controller.write_universe)
    engine.attach_output_stage(controller.output_stage)
    return engine


# The ways strobes get disabled. Each leaves the stage with strobes not allowed.
def _no_strobe_profile(engine):
    engine.set_safety_profile("no_strobe")


def _strobe_layer_off(engine):
    engine.set_strobe_layer_enabled(False)


def _camera_mode(engine):
    engine.set_safety_profile("performance", camera_mode=True)


DISABLERS = [_no_strobe_profile, _strobe_layer_off, _camera_mode]


def disable_strobes(engine, how=_no_strobe_profile):
    how(engine)
    engine._sync_output_stage()
    assert not engine._output_stage.status()["strobe_allowed"]


# ---------------------------------------------------------------------------
# Every write path, aimed at everything in the rig
# ---------------------------------------------------------------------------

EVERY_CHANNEL = sorted(
    {MOVER_DIMMER + 1, MOVER_SHUTTER + 1, 7, 8, 9}
    | {BATTEN_AT + i for i in range(5)}
    | {PAR_AT + i for i in range(3)}
    | {slot + 1 for slot in STROBE_SLOTS}
)


async def _engine_render(ctrl, engine):
    """The engine's own way out: fixture state, rendered and handed over."""
    for fixture in engine.fixtures.fixtures.values():
        fixture.dimmer = 1.0
        fixture.strobe = 1.0
        fixture.red = fixture.green = fixture.blue = 1.0
    engine._emit_dmx()


async def _raw_channel(ctrl, engine):
    for channel in EVERY_CHANNEL:
        await ctrl.set_channel(0, channel, 255)


async def _raw_frame(ctrl, engine):
    await ctrl.set_frame(0, DMXFrame(universe=0, channels={c: 255 for c in EVERY_CHANNEL}))


async def _raw_buffer(ctrl, engine):
    ctrl.write_universe(0, [255 if (i + 1) in EVERY_CHANNEL else 0 for i in range(512)])


async def _fixture_state(ctrl, engine):
    for n, (address, width) in enumerate(
            [(MOVER_AT + 4, 5), (BATTEN_AT, 5), (PAR_AT, 3), (STROBE_AT, 4), (COLOUR_STROBE_AT, 6)]):
        await ctrl.set_fixture_state(n, DMXFixtureState(
            fixture_id=n, rig_fixture_id=n, universe=0, start_address=address,
            channel_values={f"ch{i}": 255 for i in range(width)},
        ))


async def _cue(ctrl, engine):
    await ctrl.execute_cue(SimpleNamespace(dmx_values={f"0:{c}": 255 for c in EVERY_CHANNEL}))


async def _cue_with_fade(ctrl, engine):
    ctrl.get_universe(0)
    await ctrl.execute_cue(
        SimpleNamespace(dmx_values={str(c): 255 for c in EVERY_CHANNEL}), fade_time=0.1)


async def _all_on_pattern(ctrl, engine):
    await ctrl.run_test_pattern(0, "all_on")


async def _strobe_pattern(ctrl, engine):
    await ctrl.run_test_pattern(0, "strobe")


async def _fixture_test(ctrl, engine):
    service = FixtureTestService(ctrl)
    for address, width in [(MOVER_AT + 4, 5), (BATTEN_AT, 5), (PAR_AT, 3), (STROBE_AT, 4),
                           (COLOUR_STROBE_AT, 6)]:
        await service._set_fixture_channels(0, address, {i: 255 for i in range(width)})


async def _identify_poke(ctrl, engine):
    # The identify walkthrough writes the buffer directly, as do the patterns.
    ctrl.get_universe(0).data = [255] * 512


WRITERS = [_engine_render, _raw_channel, _raw_frame, _raw_buffer, _fixture_state, _cue,
           _cue_with_fade, _all_on_pattern, _strobe_pattern, _fixture_test, _identify_poke]


async def _settle(ctrl):
    await ctrl.stop_test_pattern()
    for task in list(ctrl.fade_tasks.values()) + list(ctrl._release_tasks.values()):
        task.cancel()
    await asyncio.sleep(0)


async def write_and_watch(ctrl, engine, write, seconds=0.6):
    """Let a writer write, in real time because fades and patterns sleep for real.

    Returns what was asked for and what was sent, frame by frame.
    """
    asked = []
    try:
        await write(ctrl, engine)
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            asked.append(np.array(ctrl.get_universe(0).data, dtype=np.uint8))
            ctrl._transmit_frame(time.monotonic())
            await asyncio.sleep(1.0 / WIRE_FPS)
    finally:
        await _settle(ctrl)
    return np.asarray(asked), np.asarray(ctrl.socket.frames())


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_strobes_off_holds_strobe_fixtures_dark_against_this_writer(controller, write):
    engine = live_engine(controller)
    disable_strobes(engine)

    asked, sent = await write_and_watch(controller, engine, write)

    assert asked[:, STROBE_DIMMER].max() == 255 and asked[:, STROBE_RATE].max() == 255, (
        "the writer never drove the strobe fixture; this test proves nothing")
    assert asked[:, 210].max() == 255, "nor the second one"
    assert len(sent) == len(asked) and len(sent) > 10
    assert not sent[:, STROBE_SLOTS].any(), (
        f"a strobe fixture got {sent[:, STROBE_SLOTS].max()} on the wire with strobes disabled")


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_strobes_off_leaves_the_other_fixtures_to_this_writer(controller, write):
    """The same runs, read on the fixtures that are not strobes."""
    engine = live_engine(controller)
    disable_strobes(engine)

    asked, sent = await write_and_watch(controller, engine, write)

    for name, slot in OTHER_LIGHT.items():
        assert asked[:, slot].max() == 255
        assert sent[:, slot].max() == 255, f"the {name} never reached full with strobes disabled"
    # A batten's strobe channel and a mover's shutter are not a strobe fixture.
    # They go out as written.
    assert asked[:, BATTEN_STROBE].max() == 255 and asked[:, MOVER_SHUTTER].max() == 255
    assert np.array_equal(sent[:, BATTEN_STROBE], asked[:, BATTEN_STROBE])
    assert np.array_equal(sent[:, MOVER_SHUTTER], asked[:, MOVER_SHUTTER])


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_strobes_on_lets_this_writer_run_the_strobe_fixtures(controller, write):
    engine = live_engine(controller)
    engine._sync_output_stage()
    assert controller.output_stage.status()["strobe_allowed"]

    asked, sent = await write_and_watch(controller, engine, write)

    assert sent[:, STROBE_DIMMER].max() == 255, "the strobe's dimmer never opened"
    assert sent[:, 210].max() == 255
    # The rate, shutter and macro channels arrive as written.
    for slot in (STROBE_RATE, 211):
        assert asked[:, slot].max() == 255
    for slot in (STROBE_RATE, 202, 203, 211, 215):
        assert np.array_equal(sent[:, slot], asked[:, slot])
    for slot in OTHER_LIGHT.values():
        assert sent[:, slot].max() == 255


@pytest.mark.parametrize("disable", DISABLERS, ids=lambda d: d.__name__.strip("_"))
async def test_every_way_of_disabling_strobes_holds_them_dark(controller, disable):
    engine = live_engine(controller)
    disable_strobes(engine, disable)
    assert controller.output_stage.status()["strobe_fixtures_held_off"]

    asked, sent = await write_and_watch(controller, engine, _raw_channel, seconds=0.3)

    assert asked[:, STROBE_SLOTS].min() == 255
    assert not sent[:, STROBE_SLOTS].any()
    assert sent[:, PAR_RED].max() == 255


# ---------------------------------------------------------------------------
# The switch, thrown mid-show
# ---------------------------------------------------------------------------


async def test_switching_strobes_off_darkens_them_on_the_next_frame_and_on_brings_them_back(
        controller):
    engine = live_engine(controller)
    engine.set_dmx_callback(None)       # a raw writer holds the buffer; the engine only syncs
    engine._emit_dmx()
    for channel in EVERY_CHANNEL:
        await controller.set_channel(0, channel, 255)

    t = 0.0
    for _ in range(WIRE_FPS):
        controller._transmit_frame(t)
        t += 1.0 / WIRE_FPS
    lit = controller.socket.frames()[-1]
    assert all(lit[slot] == 255 for slot in STROBE_SLOTS)
    assert not controller.output_stage.status()["strobe_fixtures_held_off"]

    engine.set_strobe_layer_enabled(False)
    engine._emit_dmx()
    controller._transmit_frame(t)
    dark = controller.socket.frames()[-1]
    assert not dark[STROBE_SLOTS].any(), "strobes off must not wait for a fade"
    assert dark[PAR_RED] == 255 and dark[BATTEN_DIMMER] == 255 and dark[MOVER_DIMMER] == 255
    assert dark[BATTEN_STROBE] == 255 and dark[MOVER_SHUTTER] == 255

    for _ in range(2 * WIRE_FPS):
        t += 1.0 / WIRE_FPS
        controller._transmit_frame(t)
        assert not controller.socket.frames()[-1][STROBE_SLOTS].any()

    engine.set_strobe_layer_enabled(True)
    engine._emit_dmx()
    for _ in range(2 * WIRE_FPS):
        t += 1.0 / WIRE_FPS
        controller._transmit_frame(t)
    back = controller.socket.frames()[-1]
    assert all(back[slot] == 255 for slot in STROBE_SLOTS)


# ---------------------------------------------------------------------------
# The others still flash, and still under the cap
# ---------------------------------------------------------------------------


def others_worst_flash_rate(times, frames):
    levels = np.asarray(frames, dtype=float)[:, list(OTHER_LIGHT.values())] / 255.0
    per_fixture = max(worst_flashes_per_second(times, levels[:, i]) for i in range(levels.shape[1]))
    return max(per_fixture, worst_flashes_per_second(times, levels.mean(axis=1)))


@pytest.mark.parametrize("profile, cap", [("no_strobe", 2), ("conservative", 3)])
async def test_a_raw_strobe_on_everything_darkens_strobes_and_caps_the_rest(
        controller, profile, cap):
    engine = live_engine(controller)
    engine.set_safety_profile(profile)
    engine.set_strobe_layer_enabled(False)
    engine.set_dmx_callback(None)
    engine._emit_dmx()
    assert controller.output_stage.flash_limit_hz == cap

    times, asked = [], []
    for n in range(6 * WIRE_FPS):
        t = n / WIRE_FPS
        value = 255 if (t * 8.0) % 1.0 < 0.5 else 0
        for channel in EVERY_CHANNEL:
            await controller.set_channel(0, channel, value)
        asked.append(np.array(controller.get_universe(0).data, dtype=np.uint8))
        controller._transmit_frame(t)
        times.append(t)
    sent = np.asarray(controller.socket.frames())
    asked = np.asarray(asked)

    assert worst_flashes_per_second(times, asked[:, STROBE_DIMMER] / 255.0) >= 8
    assert not sent[:, STROBE_SLOTS].any()

    assert others_worst_flash_rate(times, asked) >= 8
    for name, slot in OTHER_LIGHT.items():
        level = sent[:, slot] / 255.0
        assert level.max() == 1.0, f"the {name} was held dark with the strobes"
        assert worst_flashes_per_second(times, level) >= 1, f"the {name} stopped flashing at all"
    assert others_worst_flash_rate(times, sent) <= cap


@pytest.fixture
def clock(monkeypatch):
    """The LFO engine reads wall time; give it the test's clock instead."""
    fake = SimpleNamespace(now=0.0)
    monkeypatch.setattr(lfo_module, "time", SimpleNamespace(time=lambda: fake.now))
    return fake


def run_show(controller, engine, seconds, clock, audio=None):
    """Step the engine at 60 fps and the transmitter at 40, on one made-up clock."""
    times, asked = [], []
    next_wire = 0.0
    for n in range(int(seconds * ENGINE_FPS)):
        clock.now = n / ENGINE_FPS
        if audio is not None:
            audio(engine, n)
        engine.update(1.0 / ENGINE_FPS)
        while next_wire <= clock.now + 1e-9:
            asked.append(np.array(controller.get_universe(0).data, dtype=np.uint8))
            controller._transmit_frame(next_wire)
            times.append(next_wire)
            next_wire += 1.0 / WIRE_FPS
    return np.asarray(times), np.asarray(asked), np.asarray(controller.socket.frames())


def manual_lfo_strobe(engine):
    engine.set_auto_mode(False)
    lfo = LFOEngine()
    engine.set_lfo_engine(lfo)
    lfo.set_single_effect("strobe")


def test_manual_lfo_strobe_with_strobes_off_darkens_strobes_and_caps_the_rest(controller, clock):
    engine = live_engine(controller, bpm=120.0)
    engine.set_safety_profile("no_strobe")
    manual_lfo_strobe(engine)

    times, asked, sent = run_show(controller, engine, 8.0, clock)

    assert asked[:, STROBE_DIMMER].max() > 0 and asked[:, 210].max() > 0, (
        "manual mode no longer drives the strobe fixtures; this test proves nothing")
    assert not sent[:, STROBE_SLOTS].any()
    others = list(OTHER_LIGHT.values())
    assert others_worst_flash_rate(times, asked) >= 7
    assert sent[:, others].max() == asked[:, others].max() > 0, "the rest never reached its level"
    assert others_worst_flash_rate(times, sent) <= 2


def test_manual_lfo_strobe_with_strobes_on_reaches_the_strobe_fixtures(controller, clock):
    engine = live_engine(controller, bpm=120.0)
    manual_lfo_strobe(engine)

    times, asked, sent = run_show(controller, engine, 4.0, clock)

    assert asked[:, STROBE_DIMMER].max() > 0
    assert sent[:, STROBE_DIMMER].max() == asked[:, STROBE_DIMMER].max()
    assert worst_flashes_per_second(times, sent[:, STROBE_DIMMER] / 255.0) >= 2


def loud_four_on_the_floor(engine, frame):
    """A loud 128 bpm track, as the analyser would report it."""
    per_beat = ENGINE_FPS * 60.0 / 128.0
    beat = int(frame / per_beat)
    engine.update_audio(
        energy=0.9, bass=0.9, mid=0.7, high=0.6,
        is_beat=int((frame - 1) / per_beat) != beat or frame == 0, beat_number=beat,
        arousal=0.9, spectral_flux=0.5, bpm=128.0, tempo_confidence=0.9,
    )


def test_the_autopilot_with_strobes_off_never_reaches_a_strobe_fixture(controller, clock):
    engine = live_engine(controller)
    engine.set_safety_profile("no_strobe")
    engine.set_auto_mode(True)

    times, asked, sent = run_show(controller, engine, 12.0, clock, audio=loud_four_on_the_floor)

    assert not sent[:, STROBE_SLOTS].any()
    assert sent[:, list(OTHER_LIGHT.values())].max() > 0, "the autopilot lit nothing at all"
    assert others_worst_flash_rate(times, sent) <= 2


# ---------------------------------------------------------------------------
# What counts as a strobe fixture
# ---------------------------------------------------------------------------


def test_a_strobe_fixture_is_one_by_type_not_by_having_a_strobe_channel():
    fixtures = rig().fixtures
    assert [f.id for f in fixtures.values() if is_strobe_fixture(f)] == ["st", "cst"]
    assert fixture_strobe_slots(fixtures["bat"]) == [], "a batten has a strobe channel"
    assert fixture_strobe_slots(fixtures["mh"]) == [], "a mover has a shutter"
    assert fixture_strobe_slots(fixtures["par"]) == []
    assert fixture_strobe_slots(fixtures["st"]) == [200, 201, 202, 203]
    assert rig().strobe_patch() == {0: STROBE_SLOTS}


def test_a_moving_strobe_keeps_its_position_when_strobes_are_off(controller):
    engine = live_engine(controller)
    engine.fixtures.add_fixtures([Fixture(
        id="mst", name="Moving Strobe", dmx_address=301, universe=1,
        channels={'pan': 0, 'tilt': 1, 'dimmer': 2, 'strobe': 3}, fixture_type="STROBE")])
    disable_strobes(engine)
    engine.set_dmx_callback(None)
    engine._emit_dmx()

    controller.write_universe(1, [0] * 300 + [200, 90, 255, 255] + [0] * 208)
    controller._transmit_frame(0.0)
    frame = controller.socket.frames(1)[-1]
    assert list(frame[300:304]) == [200, 90, 0, 0]


def test_retyping_a_fixture_reaches_the_stage(controller):
    engine = live_engine(controller)
    disable_strobes(engine)
    engine.set_dmx_callback(None)
    engine._emit_dmx()
    controller.write_universe(0, [255] * 512)

    controller._transmit_frame(0.0)
    assert controller.socket.frames()[-1][BATTEN_DIMMER] == 255

    engine.fixtures.fixtures["bat"].fixture_type = "strobe"    # same address, same channels
    engine._emit_dmx()
    controller._transmit_frame(1.0)
    assert not controller.socket.frames()[-1][50:55].any()

    engine.fixtures.fixtures["st"].fixture_type = "bar"
    engine._emit_dmx()
    for n in range(WIRE_FPS):
        controller._transmit_frame(2.0 + n / WIRE_FPS)
    assert controller.socket.frames()[-1][STROBE_DIMMER] == 255


def test_a_rig_held_off_the_wire_names_no_strobe_fixtures(controller):
    """The demo's patch describes nothing real, so its strobes are not anybody's strobes.

    Slots it calls a strobe stay under the blackout, the master and the flash
    limit like any unpatched slot; they are not pinned to zero.
    """
    engine = live_engine(controller)
    engine.set_dmx_callback(None)
    engine.set_output_held(True)
    disable_strobes(engine)
    engine._emit_dmx()
    assert not controller.output_stage.status()["strobe_fixtures_held_off"]

    controller.write_universe(0, [0] * 200 + [255] + [0] * 311)
    controller._transmit_frame(0.0)
    assert controller.socket.frames()[-1][STROBE_DIMMER] == 255
