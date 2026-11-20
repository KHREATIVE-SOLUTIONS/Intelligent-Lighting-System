"""
Output Stage, At The Wire
=========================

Everything here is read off the packets a fake socket was handed, because the
findings this closes were wire findings: with the `no_strobe` profile set and
the autopilot off, the LFO strobe preset put an 8 Hz full-rig flicker on the
wire, and a raw channel write lit a fixture through a latched blackout.

No socket is opened. The controller is given a recorder in place of one and its
transmitter is stepped by hand, so no packet leaves the process.
"""

import ast
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import app
from app.api.endpoints import dmx as dmx_api
from app.schemas.dmx import DMXBlackoutCommand, DMXFixtureState, DMXFrame
from app.services.dmx.dmx_controller import DMXController
from app.services.dmx.output_stage import StagedFrame
from app.services.effects import lfo_engine as lfo_module
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager
from app.services.effects.lfo_engine import LFOEngine
from app.services.fixture_test.fixture_test_service import FixtureTestService

from tests.unit.test_output_stage import worst_flashes_per_second

WIRE_FPS = 40
ENGINE_FPS = 60

MOVER = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4,
         'red': 5, 'green': 6, 'blue': 7}
PAR_NO_DIMMER = {'red': 0, 'green': 1, 'blue': 2}


class Recorder:
    """Stands in for the UDP socket. Keeps what it was asked to send."""

    def __init__(self):
        self.packets = []

    def sendto(self, packet, target):
        assert packet[:8] == b'Art-Net\x00'
        universe = packet[14] | (packet[15] << 8)
        self.packets.append((universe, bytes(packet[18:])))

    def frames(self, universe=0):
        return [np.frombuffer(data, dtype=np.uint8) for u, data in self.packets if u == universe]

    def close(self):
        pass


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.broadcast = False
    ctrl.socket = Recorder()
    ctrl.is_connected = True   # no thread: the tests step the transmitter
    return ctrl


def rig():
    manager = FixtureGroupManager()
    fixtures = [
        Fixture(id=f"mh{i}", name=f"MH {i}", dmx_address=1 + 8 * i, channels=dict(MOVER),
                fixture_type="mover")
        for i in range(4)
    ] + [
        Fixture(id=f"par{i}", name=f"Par {i}", dmx_address=101 + 3 * i,
                channels=dict(PAR_NO_DIMMER), fixture_type="par")
        for i in range(4)
    ]
    manager.add_fixtures(fixtures)
    return manager


def live_engine(controller, **config):
    """An engine wired to the controller the way main.py wires it."""
    engine = EffectsEngine(EffectsConfig(
        fps=ENGINE_FPS, strobe_enabled=True, accessibility_mode="conservative",
        strobe_hz_cap=3.0, **config,
    ))
    engine.set_fixture_manager(rig())
    engine.set_dmx_callback(controller.write_universe)
    engine.attach_output_stage(controller.output_stage)
    return engine


def fixture_levels(frames):
    """Per-fixture intensity the way the musical metrics read it: dimmer, else colour."""
    levels = []
    for frame in frames:
        movers = [frame[4 + 8 * i] for i in range(4)]
        pars = [max(frame[100 + 3 * i: 103 + 3 * i]) for i in range(4)]
        levels.append(movers + pars)
    return np.asarray(levels, dtype=float) / 255.0


def worst_on_any_fixture_or_the_rig(times, frames):
    levels = fixture_levels(frames)
    per_fixture = max(worst_flashes_per_second(times, levels[:, i]) for i in range(levels.shape[1]))
    return max(per_fixture, worst_flashes_per_second(times, levels.mean(axis=1)))


# ---------------------------------------------------------------------------
# One way out
# ---------------------------------------------------------------------------


def test_only_one_place_in_the_application_sends_a_packet():
    """Any second sender would be a path round the stage."""
    senders = []
    for path in Path(app.__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                            and inner.func.attr in {"sendto", "sendmsg", "send", "sendall"}
                            and not _not_a_socket(inner)):
                        senders.append((path.name, node.name))
    assert senders == [("dmx_controller.py", "_put_on_wire")], senders


def _not_a_socket(call):
    # .send() is also what a queue or a generator has. It only counts here on
    # something named like a socket; sendto and sendmsg always count.
    return call.func.attr in {"send", "sendall"} and not (
        isinstance(call.func.value, ast.Name) and "sock" in call.func.value.id.lower()
        or isinstance(call.func.value, ast.Attribute) and "sock" in call.func.value.attr.lower()
    )


def test_the_send_point_refuses_anything_the_stage_did_not_produce(controller):
    with pytest.raises(TypeError):
        controller._put_on_wire(controller.socket, 0, bytes(512))
    assert controller.socket.packets == []

    controller._put_on_wire(controller.socket, 0, StagedFrame(bytes(512)))
    assert len(controller.socket.packets) == 1


def test_a_stage_that_fails_sends_dark_rather_than_unchecked(controller):
    controller.write_universe(0, [255] * 512)

    def broken(frames, now):
        raise RuntimeError("stage fell over")

    controller.output_stage.process = broken
    controller._transmit_frame(0.0)

    assert [u for u, _ in controller.socket.packets] == [0]
    assert not any(controller.socket.packets[0][1])
    assert controller.get_transmit_status()["output_stage"]["failures"] == 1


# ---------------------------------------------------------------------------
# Blackout holds against every writer
# ---------------------------------------------------------------------------


async def _engine_frame(ctrl):
    ctrl.write_universe(0, [255] * 512)


async def _raw_channel(ctrl):
    await ctrl.set_channel(0, 1, 255)


async def _raw_frame(ctrl):
    await ctrl.set_frame(0, DMXFrame(universe=0, channels={1: 255, 200: 255, 512: 255}))


async def _fixture_state(ctrl):
    await ctrl.set_fixture_state(1, DMXFixtureState(
        fixture_id=1, rig_fixture_id=1, universe=0, start_address=10,
        channel_values={"dimmer": 255, "red": 255},
    ))


async def _cue(ctrl):
    await ctrl.execute_cue(SimpleNamespace(dmx_values={"0:1": 255, "7": 255}))


async def _cue_fade(ctrl):
    ctrl.get_universe(0)
    await ctrl._fade_channel(0, 1, 255, 0.05)


async def _test_pattern(ctrl):
    await ctrl.run_test_pattern(0, "all_on")
    await asyncio.sleep(0.05)


async def _fixture_test(ctrl):
    await FixtureTestService(ctrl)._set_fixture_channels(0, 1, {0: 255, 1: 255, 2: 255})


async def _identify_poke(ctrl):
    # The identify walkthrough writes the buffer directly, as do the patterns.
    ctrl.get_universe(0).data = [255] * 512


async def _universe_assignment(ctrl):
    from app.schemas.dmx import DMXUniverse
    ctrl.universes[3] = DMXUniverse(universe=3)
    ctrl.universes[3].data[0] = 255


async def _stop_pattern(ctrl):
    await ctrl.stop_test_pattern()
    for task in list(ctrl._release_tasks.values()):
        task.cancel()
    await asyncio.sleep(0)


WRITERS = [_engine_frame, _raw_channel, _raw_frame, _fixture_state, _cue, _cue_fade,
           _test_pattern, _fixture_test, _identify_poke, _universe_assignment]


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_a_latched_blackout_holds_against_this_writer(controller, write):
    controller.output_stage.blackout()
    try:
        await write(controller)
        assert any(any(u.data) for u in controller.universes.values()), "the writer wrote nothing"
        for n in range(10):
            controller._transmit_frame(n / WIRE_FPS)
    finally:
        await _stop_pattern(controller)

    assert controller.socket.packets, "nothing was sent at all"
    for universe, data in controller.socket.packets:
        assert not any(data), f"universe {universe} lit through a latched blackout"


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_this_writer_is_scaled_by_the_grand_master(controller, write):
    controller.output_stage.set_master(0.5)
    try:
        await write(controller)
        controller._transmit_frame(0.0)
    finally:
        await _stop_pattern(controller)

    peak = max(max(data) for _, data in controller.socket.packets)
    assert 0 < peak <= 127


async def test_the_blackout_route_latches_the_stage_and_restore_releases_it(controller):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dmx_controller=controller)))
    await controller.set_channel(0, 1, 255)

    await dmx_api.blackout(DMXBlackoutCommand(), request)
    assert controller.output_stage.blackout_active
    await controller.set_channel(0, 1, 255)      # B5: a raw write after the blackout
    controller._transmit_frame(0.0)
    assert not any(controller.socket.packets[-1][1])

    await dmx_api.restore_from_blackout(fade_time=0.0, request=request)
    assert not controller.output_stage.blackout_active
    await controller.set_channel(0, 1, 255)
    controller._transmit_frame(1.0)
    assert controller.socket.packets[-1][1][0] == 255


# ---------------------------------------------------------------------------
# The engine defers to the stage
# ---------------------------------------------------------------------------


def _light_rig(engine):
    for fixture in engine.fixtures.fixtures.values():
        fixture.dimmer = 1.0
        fixture.pan = 40.0
        fixture.tilt = -20.0
        fixture.red = fixture.green = fixture.blue = 1.0
    engine._emit_dmx()


def test_the_master_is_applied_once_not_twice(controller):
    engine = live_engine(controller)
    _light_rig(engine)
    controller._transmit_frame(0.0)
    full = controller.socket.frames()[-1]

    engine.set_grand_master(0.5)
    _light_rig(engine)
    controller._transmit_frame(1.0)
    half = controller.socket.frames()[-1]

    assert full[4] == 255 and half[4] == 127, "0.5 on the master must read 127, not 63"
    assert half[100] == 127, "a par with no dimmer carries intensity in its colour"
    assert list(half[0:4]) == list(full[0:4]), "pulling the master down must never move a head"
    assert controller.output_stage.master == 0.5 and engine.grand_master == 0.5
    assert engine.output_master == 0.5


def test_an_engine_blackout_darkens_a_raw_write_too(controller):
    engine = live_engine(controller)
    engine.blackout()
    assert controller.output_stage.blackout_active and engine.blackout_active
    assert engine.output_master == 0.0

    controller.get_universe(0).data[300] = 255   # outside the rig, written raw
    _light_rig(engine)
    controller.get_universe(0).data[300] = 255
    for n in range(5):
        controller._transmit_frame(n / WIRE_FPS)
    for frame in controller.socket.frames():
        assert frame[4] == 0 and frame[100] == 0 and frame[300] == 0

    engine.restore()
    assert not controller.output_stage.blackout_active


def test_the_stage_takes_its_limit_from_the_safety_profile(controller):
    engine = live_engine(controller)
    stage = controller.output_stage

    engine._emit_dmx()
    assert stage.flash_limit_hz == 3.0

    engine.set_safety_profile("no_strobe")
    engine._emit_dmx()
    assert stage.flash_limit_hz == 2.0

    engine.set_safety_profile("performance")
    engine._emit_dmx()
    assert stage.flash_limit_hz == 18.0
    engine.set_strobe_layer_enabled(False)
    engine._emit_dmx()
    assert stage.flash_limit_hz == 3.0, "strobes off must not leave an 18 Hz limit standing"


def test_the_stage_learns_a_rig_that_changes_under_it(controller):
    engine = live_engine(controller)
    engine.fixtures.add_fixtures([Fixture(
        id="late", name="Late", dmx_address=201, channels=dict(MOVER), fixture_type="mover")])
    engine._emit_dmx()
    controller.output_stage.set_master(0.5)

    controller.get_universe(0).data[200] = 200   # the new mover's pan
    controller.get_universe(0).data[204] = 200   # and its dimmer
    controller._transmit_frame(0.0)
    frame = controller.socket.frames()[-1]
    assert frame[200] == 200 and frame[204] == 100


# ---------------------------------------------------------------------------
# Manual mode cannot out-strobe the limit
# ---------------------------------------------------------------------------


def run_show(controller, engine, seconds, clock):
    """Step the engine at 60 fps and the transmitter at 40, on one made-up clock."""
    times, asked = [], []
    next_wire = 0.0
    for n in range(int(seconds * ENGINE_FPS)):
        clock.now = n / ENGINE_FPS
        engine.update(1.0 / ENGINE_FPS)
        while next_wire <= clock.now + 1e-9:
            asked.append(np.array(controller.get_universe(0).data, dtype=np.uint8))
            controller._transmit_frame(next_wire)
            times.append(next_wire)
            next_wire += 1.0 / WIRE_FPS
    return np.asarray(times), asked, controller.socket.frames()


@pytest.fixture
def clock(monkeypatch):
    """The LFO engine reads wall time; give it the test's clock instead."""
    fake = SimpleNamespace(now=0.0)
    monkeypatch.setattr(lfo_module, "time", SimpleNamespace(time=lambda: fake.now))
    return fake


def test_manual_lfo_strobe_with_strobes_off_stays_under_the_limit(controller, clock):
    """Finding B1: `no_strobe`, autopilot off, the LFO strobe preset."""
    engine = live_engine(controller, bpm=120.0)
    engine.set_safety_profile("no_strobe")
    engine.set_auto_mode(False)
    lfo = LFOEngine()
    engine.set_lfo_engine(lfo)
    lfo.set_single_effect("strobe")
    assert not engine.config.strobe_enabled

    times, asked, sent = run_show(controller, engine, 8.0, clock)
    limit = controller.output_stage.flash_limit_hz

    assert limit == 2.0
    assert worst_on_any_fixture_or_the_rig(times, asked) >= 7, (
        "manual mode is no longer strobing on its own; this test proves nothing")
    assert worst_on_any_fixture_or_the_rig(times, sent) <= limit


@pytest.mark.parametrize("profile, limit", [("no_strobe", 2), ("conservative", 3)])
def test_manual_lfo_strobe_with_the_strobe_layer_off_stays_under_the_limit(
        controller, clock, profile, limit):
    engine = live_engine(controller, bpm=174.0)
    engine.set_safety_profile(profile)
    engine.set_strobe_layer_enabled(False)
    engine.set_auto_mode(False)
    lfo = LFOEngine()
    engine.set_lfo_engine(lfo)
    lfo.set_single_effect("strobe")

    times, asked, sent = run_show(controller, engine, 8.0, clock)

    assert worst_on_any_fixture_or_the_rig(times, asked) >= 7
    assert worst_on_any_fixture_or_the_rig(times, sent) <= limit


async def test_a_raw_channel_strobe_with_strobes_off_stays_under_the_limit(controller):
    """Manual in the plainest sense: someone toggling channels through the API."""
    engine = live_engine(controller)
    engine.set_safety_profile("no_strobe")
    engine.set_auto_mode(False)
    engine.set_dmx_callback(None)   # as the identify walkthrough leaves it
    engine._emit_dmx()

    times, asked = [], []
    for n in range(6 * WIRE_FPS):
        t = n / WIRE_FPS
        value = 255 if (t * 8.0) % 1.0 < 0.5 else 0
        for channel in (5, 13, 101, 102, 103, 300):
            await controller.set_channel(0, channel, value)
        asked.append(np.array(controller.get_universe(0).data, dtype=np.uint8))
        controller._transmit_frame(t)
        times.append(t)
    sent = controller.socket.frames()

    for index in (4, 12, 100, 299):
        assert worst_flashes_per_second(times, [f[index] / 255.0 for f in asked]) >= 8
        assert worst_flashes_per_second(times, [f[index] / 255.0 for f in sent]) <= 2
    assert worst_on_any_fixture_or_the_rig(times, sent) <= 2


async def test_the_strobe_test_pattern_with_strobes_off_stays_under_the_limit(controller):
    """Real time, because the pattern sleeps for real."""
    controller.output_stage.set_flash_policy(False, 2.0)
    await controller.run_test_pattern(0, "strobe")
    times = []
    start = time.monotonic()
    try:
        while time.monotonic() - start < 3.0:
            now = time.monotonic()
            controller._transmit_frame(now)
            times.append(now)
            await asyncio.sleep(1.0 / WIRE_FPS)
    finally:
        await _stop_pattern(controller)

    level = [f[0] / 255.0 for f in controller.socket.frames()]
    assert max(level) == 1.0
    assert worst_flashes_per_second(times, level) <= 2


def test_the_real_transmit_loop_uses_the_stage(controller):
    """The thread the venue runs, not the stepped one: latched, it sends only dark."""
    controller.is_connected = False
    recorder = controller.socket

    async def scenario():
        await controller.connect()
        controller.socket.close()
        controller.socket = recorder          # swap the UDP socket out before anything is lit
        controller.output_stage.blackout()
        await asyncio.sleep(0.1)              # let any frame taken before the swap clear
        recorder.packets.clear()
        controller.write_universe(0, [255] * 512)
        await asyncio.sleep(0.3)
        controller.blackout_on_stop = False
        await controller.disconnect()

    asyncio.run(scenario())
    assert len(recorder.packets) > 5
    assert all(not any(data) for _, data in recorder.packets)
