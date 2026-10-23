"""
Releasing a Universe After a Rig Swap
=====================================

A universe the old rig used and the new rig does not used to get one zero frame
and then stay in the controller, so the output loop sent zeros on it forever.
That fights any other console or node on the universe. It should black out a
few times over and then leave the wire.
"""

import threading
import time
from types import SimpleNamespace

from app.main import _release_engine_universe, _send_engine_frame
from app.services.demo.venue_presets import create_venue_rig
from app.services.dmx.dmx_controller import DMXController
from app.services.effects import EffectsConfig, EffectsEngine


class _RecordingSocket:
    """Stands in for the ArtNet socket and keeps every packet sent."""

    def __init__(self):
        self.packets = []
        self._lock = threading.Lock()

    def sendto(self, packet, target):
        with self._lock:
            self.packets.append(bytes(packet))

    def close(self):
        pass

    def sent(self, universe):
        with self._lock:
            return [p[18:] for p in self.packets if int.from_bytes(p[14:16], "little") == universe]


def _wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


def _transmitting_controller():
    """A controller whose real output loop runs against a recording socket."""
    controller = DMXController()
    controller.target_fps = 200
    controller.blackout_on_stop = False
    sock = _RecordingSocket()
    controller.socket = sock
    controller.is_connected = True
    stop = threading.Event()
    controller.output_thread = threading.Thread(target=controller._output_loop, args=(stop,), daemon=True)
    controller.output_thread.start()
    return controller, sock, stop


def test_a_released_universe_blacks_out_then_stops_sending():
    controller, sock, stop = _transmitting_controller()
    try:
        controller.write_universe(0, [100] * 512)
        controller.write_universe(1, [255] * 512)
        assert _wait_for(lambda: sock.sent(1)), "universe 1 should be on the wire first"

        controller.release_universe(1)
        assert _wait_for(lambda: 1 not in controller.universes), "universe 1 never left the wire"

        sent_after_release = len(sock.sent(1))
        zeros = [frame for frame in sock.sent(1) if not any(frame)]
        assert len(zeros) >= controller.RELEASE_FRAMES, "the blackout must go out more than once"

        before = len(sock.sent(0))
        assert _wait_for(lambda: len(sock.sent(0)) > before + 5)
        assert len(sock.sent(1)) == sent_after_release, "a released universe kept transmitting"
        assert sock.sent(0)[-1][0] == 100, "the universe still in the rig keeps its frame"
    finally:
        stop.set()
        controller.output_thread.join(timeout=2)


def test_a_new_frame_calls_off_a_pending_release():
    controller, sock, stop = _transmitting_controller()
    stop.set()
    controller.output_thread.join(timeout=2)
    # Nothing counts the release down now, so it stays pending until the write.
    controller.output_thread = threading.current_thread()
    controller.write_universe(1, [255] * 512)
    controller.release_universe(1)
    assert 1 in controller._releasing

    controller.write_universe(1, [50] * 512)
    controller._count_down_releases()
    controller._count_down_releases()
    controller._count_down_releases()

    assert 1 not in controller._releasing
    assert controller.universes[1].data[0] == 50


def test_release_with_nothing_transmitting_drops_the_universe_at_once():
    controller = DMXController()
    controller.write_universe(2, [255] * 512)

    controller.release_universe(2)

    assert 2 not in controller.universes
    controller.release_universe(7)  # a universe it never held is a no-op


def test_a_rig_swap_takes_dropped_universes_off_the_controller():
    controller = DMXController()
    app = SimpleNamespace(state=SimpleNamespace(dmx_controller=controller, dmx_output_held=False))
    engine = EffectsEngine(EffectsConfig())
    engine.set_dmx_callback(lambda universe, frame: _send_engine_frame(app, universe, frame))
    engine.set_dmx_release_callback(lambda universe: _release_engine_universe(app, universe))

    def run():
        for _ in range(10):
            engine.update_audio(energy=0.7, bass=0.6, mid=0.5, high=0.4, is_beat=True, bpm=128)
            engine.update(1 / 30.0)

    big, _ = create_venue_rig("festival_mainstage")
    engine.set_fixture_manager(big)
    run()
    assert {0, 1} <= set(controller.universes)

    small, _ = create_venue_rig("small_nightclub")
    engine.set_fixture_manager(small)
    run()

    assert 1 not in controller.universes, "the old rig's universe would keep sending zeros"
    assert any(controller.universes[0].data)


def test_without_a_release_callback_a_swap_still_sends_one_blackout():
    frames = []
    engine = EffectsEngine(EffectsConfig())
    engine.set_dmx_callback(lambda universe, frame: frames.append((universe, list(frame))))
    big, _ = create_venue_rig("festival_mainstage")
    engine.set_fixture_manager(big)
    for _ in range(3):
        engine.update(1 / 30.0)
    frames.clear()

    small, _ = create_venue_rig("small_nightclub")
    engine.set_fixture_manager(small)

    assert (1, [0] * 512) in frames
