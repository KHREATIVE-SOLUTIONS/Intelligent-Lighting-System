"""
Watchdog Fade To Black, At The Wire
===================================

The show engine runs on the event loop and the transmitter on a thread of its
own. That is what keeps a stalled send from freezing the server, and it is also
what let a frozen server keep a rig lit: the transmitter went on sending the
last frame the engine left behind, forty times a second, indefinitely.

Here the real engine loop and the real transmit loop run together, the engine
is killed, blocked or broken, and the result is read off the packets.

No socket is opened. The controller is given a recorder in place of one, so no
packet leaves the process.
"""

import asyncio
import logging
import threading
import time

import numpy as np
import pytest

from app.core.config import settings
from app.services.dmx.dmx_controller import DMXController
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine

from tests.integration.test_output_stage_wire import (
    ENGINE_FPS, WIRE_FPS, WRITERS, Recorder, _stop_pattern, rig,
)

# Short, so the tests that wait for real do not wait long. The light holds for
# half of it, which has to be longer than the event loop hiccups on a busy box.
X = 0.6
# What real threads and a 40 fps wire are allowed on top of the limit.
SLACK = 0.25

PAN, DIMMER = 0, 4       # the first mover
PAR = 100                # the first par, which has no dimmer


class TimedRecorder(Recorder):
    """The recorder, also noting when each packet was handed over."""

    def __init__(self):
        super().__init__()
        self.times = []

    def sendto(self, packet, target):
        super().sendto(packet, target)
        self.times.append(time.perf_counter())

    def between(self, start, end=float("inf")):
        return [np.frombuffer(data, dtype=np.uint8)
                for when, (_, data) in zip(list(self.times), list(self.packets))
                if start <= when < end]


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.broadcast = False
    ctrl.socket = TimedRecorder()
    ctrl.is_connected = True
    ctrl.blackout_on_stop = False
    ctrl.output_stage.set_watchdog_seconds(X)
    return ctrl


@pytest.fixture
def transmitter(controller):
    """The transmit loop the venue runs, on its thread, sending to the recorder."""
    stop = threading.Event()
    thread = threading.Thread(target=controller._output_loop, args=(stop,), daemon=True)
    thread.start()
    yield controller.socket
    stop.set()
    thread.join(2.0)
    assert not thread.is_alive()


def still_engine(controller):
    """A real engine, wired as main.py wires it, holding one look that never changes."""
    engine = EffectsEngine(EffectsConfig(fps=ENGINE_FPS))
    engine.set_fixture_manager(rig())
    engine.set_dmx_callback(controller.write_universe)
    engine.attach_output_stage(controller.output_stage)

    def hold_the_look(delta_time=None):
        for fixture in engine.fixtures.fixtures.values():
            fixture.dimmer = 1.0
            fixture.pan = 40.0
            fixture.tilt = -20.0
            fixture.red = fixture.green = fixture.blue = 1.0
        engine._emit_dmx()

    engine.update = hold_the_look
    return engine


async def running(engine, seconds=0.4):
    """Start the engine's own loop and let the look reach the wire."""
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(seconds)
    return task


async def finish(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def lit(frame):
    return frame[DIMMER] > 0 or frame[PAR] > 0


def assert_faded_to_black(recorder, stopped, pan):
    """From `stopped`: down, never back up, black inside the limit, heads unmoved."""
    after = recorder.between(stopped)
    assert after, "the transmitter stopped as well; this test proves nothing"
    dimmer = np.array([int(frame[DIMMER]) for frame in after])
    assert dimmer[0] == 255, "it was not lit when the engine stopped"
    assert np.all(np.diff(dimmer) <= 0), "the fade went back up"
    assert 0 < dimmer[dimmer > 0].min() < 255, "it cut out rather than faded"

    late = recorder.between(stopped + X + SLACK)
    assert len(late) > 5, "nothing was sent after the limit, so nothing shows it stayed dark"
    assert not any(lit(frame) for frame in late), "light on the wire after the limit"
    assert all(frame[PAN] == pan for frame in after), "a head moved"


# ---------------------------------------------------------------------------
# A look that sits still is not a hang
# ---------------------------------------------------------------------------


async def test_a_still_look_stays_lit_while_the_engine_loop_is_ticking(controller, transmitter):
    engine = still_engine(controller)
    task = await running(engine)
    try:
        start = time.perf_counter()
        await asyncio.sleep(4 * X)
        frames = transmitter.between(start)
    finally:
        await finish(task)

    assert len(frames) > 4 * X * WIRE_FPS / 2
    assert len({frame.tobytes() for frame in frames}) == 1, "the look was not still"
    assert frames[0][DIMMER] == 255 and frames[0][PAR] == 255
    assert controller.output_stage.watchdog_armed
    assert controller.output_stage.watchdog_trips == 0


# ---------------------------------------------------------------------------
# The engine stops producing frames
# ---------------------------------------------------------------------------


async def test_killing_the_engine_loop_fades_the_wire_to_black(controller, transmitter, caplog):
    engine = still_engine(controller)
    task = await running(engine)
    pan = transmitter.frames()[-1][PAN]

    with caplog.at_level(logging.ERROR, logger="app.services.dmx.dmx_controller"):
        stopped = time.perf_counter()
        await finish(task)               # cancelled, never stopped: nothing stood it down
        await asyncio.sleep(X + SLACK + 0.5)

    assert_faded_to_black(transmitter, stopped, pan)
    assert any(controller.universes[0].data), "the frozen frame is still in the buffer"
    status = controller.get_transmit_status()["output_stage"]["watchdog"]
    assert status["tripped"] and status["trips"] == 1 and status["level"] == 0.0
    assert any("stopped producing frames" in record.message for record in caplog.records)


async def test_blocking_the_event_loop_fades_the_wire_to_black_and_it_comes_back(
        controller, transmitter):
    """The hang as a venue would meet it: something synchronous sits on the loop."""
    engine = still_engine(controller)
    task = await running(engine)
    pan = transmitter.frames()[-1][PAN]
    try:
        stopped = time.perf_counter()
        time.sleep(X + SLACK + 0.5)      # on purpose: this is the event loop being blocked
        released = time.perf_counter()
        assert_faded_to_black(transmitter, stopped, pan)

        # The engine is ticking again. Output follows it, with nothing done to help.
        await asyncio.sleep(0.5)
        back = transmitter.between(released + 0.3)
        assert back and all(frame[DIMMER] == 255 and frame[PAR] == 255 for frame in back)
        assert controller.output_stage.watchdog_level == 1.0
    finally:
        await finish(task)


async def test_an_engine_that_fails_every_frame_fades_the_wire_to_black(controller, transmitter):
    """Its loop survives a bad frame by design. Going round is not producing frames."""
    engine = still_engine(controller)
    task = await running(engine)
    pan = transmitter.frames()[-1][PAN]
    try:
        def broken(delta_time=None):
            raise RuntimeError("the renderer fell over")

        stopped = time.perf_counter()
        engine.update = broken
        await asyncio.sleep(X + SLACK + 0.5)
        assert engine.running and not task.done(), "the loop died; this is the other test"
        assert_faded_to_black(transmitter, stopped, pan)
    finally:
        await finish(task)


async def test_stopping_the_engine_on_purpose_does_not_fade(controller, transmitter):
    """A stop is a decision, and raw writes and fixture tests come after it."""
    engine = still_engine(controller)
    task = await running(engine)

    stopped = time.perf_counter()
    engine.stop()
    await task
    await asyncio.sleep(2 * X)
    held = transmitter.between(stopped + 0.1)
    assert held and all(frame[DIMMER] == 255 for frame in held)

    await controller.set_channel(0, 300, 255)
    await asyncio.sleep(0.2)
    assert transmitter.frames()[-1][299] == 255
    assert controller.output_stage.watchdog_trips == 0


async def test_an_engine_started_again_is_watched_again(controller, transmitter):
    engine = still_engine(controller)
    task = await running(engine)
    engine.stop()
    await task

    task = await running(engine)
    pan = transmitter.frames()[-1][PAN]
    stopped = time.perf_counter()
    await finish(task)
    await asyncio.sleep(X + SLACK + 0.5)

    assert_faded_to_black(transmitter, stopped, pan)


# ---------------------------------------------------------------------------
# No writer lights the rig while the engine is down
# ---------------------------------------------------------------------------


@pytest.fixture
def stepped():
    """A controller whose transmitter the test steps by hand, on a made-up clock."""
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.broadcast = False
    ctrl.socket = Recorder()
    ctrl.is_connected = True
    ctrl.output_stage.set_watchdog_seconds(X)
    return ctrl


@pytest.mark.parametrize("write", WRITERS, ids=lambda w: w.__name__.strip("_"))
async def test_this_writer_cannot_light_the_rig_while_the_engine_is_hung(stepped, write):
    stage = stepped.output_stage
    stepped.write_universe(0, [255] * 512)
    for n in range(10):
        stage.heartbeat()
        stepped._transmit_frame(n / WIRE_FPS)
    assert stepped.socket.frames()[-1].max() == 255

    hung = 10 / WIRE_FPS + X             # the engine's last beat was before this
    stepped._transmit_frame(hung)
    stepped.socket.packets.clear()
    try:
        await write(stepped)
        for n in range(10):
            stepped._transmit_frame(hung + (n + 1) / WIRE_FPS)
    finally:
        await _stop_pattern(stepped)

    assert stepped.socket.packets, "nothing was sent at all"
    for universe, data in stepped.socket.packets:
        assert not any(data), f"universe {universe} lit while the engine was hung"


def test_a_frame_emitted_by_hand_does_not_feed_the_watchdog(stepped):
    """An operator pressing blackout, say, emits a frame. That is not the loop running."""
    engine = still_engine(stepped)
    stepped.output_stage.heartbeat()
    stepped._transmit_frame(0.0)

    for n in range(1, int(3 * X * WIRE_FPS)):
        engine.update()                  # by hand, as an API call would
        stepped._transmit_frame(n / WIRE_FPS)

    last = stepped.socket.frames()[-1]
    assert last[DIMMER] == 0 and last[PAR] == 0


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def test_the_controller_takes_the_limit_from_the_settings(monkeypatch):
    assert settings.DMX_WATCHDOG_SECONDS == 2.0
    assert DMXController().output_stage.watchdog_seconds == 2.0

    monkeypatch.setattr(settings, "DMX_WATCHDOG_SECONDS", 3.5)
    assert DMXController().output_stage.watchdog_seconds == 3.5

    monkeypatch.setattr(settings, "DMX_WATCHDOG_SECONDS", 0.0)
    assert DMXController().output_stage.watchdog_seconds == 2.0, "zero must not switch it off"
