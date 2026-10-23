"""
DMX Output: Stopping, Reconnecting, and Bad Values
==================================================

Nodes hold the last frame they receive. Stopping output without sending zeros
left the rig lit after the server exited - strobes included. Reconnecting while
a stalled transmitter was still alive revived it next to the new one. And one
non-integer value took a whole universe off the wire while status said OK.
"""

import asyncio
import socket
import threading

import pytest

from app.schemas.dmx import DMXUniverse
from app.services.dmx.dmx_controller import DMXController

DATA_OFFSET = 18  # ArtDmx header length


@pytest.fixture
def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.05)
    packets = []
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            try:
                packets.append(sock.recvfrom(1024)[0])
            except socket.timeout:
                continue
            except OSError:
                return

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield sock.getsockname()[1], packets
    stop.set()
    thread.join(1)
    sock.close()


@pytest.fixture
def controller(listener):
    port, _ = listener
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.port = port
    ctrl.config.broadcast = False
    ctrl.blackout_on_stop = True
    return ctrl


async def test_stopping_output_blacks_out_the_rig(controller, listener):
    _, packets = listener
    await controller.connect()
    controller.universes[0] = DMXUniverse(universe=0)
    controller.universes[0].data = [255] * 512
    await asyncio.sleep(0.2)
    await controller.disconnect()
    await asyncio.sleep(0.1)

    assert packets, "nothing reached the listener"
    assert packets[-1][DATA_OFFSET:DATA_OFFSET + 512] == bytes(512), (
        "the last frame on the wire was still lit after output stopped"
    )


async def test_hold_last_look_is_an_explicit_choice(controller, listener):
    _, packets = listener
    controller.blackout_on_stop = False
    await controller.connect()
    controller.universes[0] = DMXUniverse(universe=0)
    controller.universes[0].data = [200] * 512
    await asyncio.sleep(0.2)
    await controller.disconnect()
    await asyncio.sleep(0.1)
    assert packets[-1][DATA_OFFSET] == 200


async def test_reconnecting_never_leaves_two_transmitters(controller):
    await controller.connect()
    old_stop = controller._output_stop
    await controller.disconnect()
    await controller.connect()
    try:
        assert controller._output_stop is not old_stop
        assert old_stop.is_set(), "reconnecting re-armed the previous transmitter"
        await asyncio.sleep(0.1)
        alive = [t for t in threading.enumerate() if t.name == "artnet-tx" and t.is_alive()]
        assert len(alive) == 1
    finally:
        await controller.disconnect()


async def test_a_fractional_value_does_not_take_a_universe_off_the_wire(controller, listener):
    _, packets = listener
    await controller.connect()
    try:
        controller.universes[3] = DMXUniverse(universe=3)
        controller.universes[3].data = [0] * 512
        controller.universes[3].data[1] = 127.5  # a raw write, as a websocket client can make
        await asyncio.sleep(0.2)
        status = controller.get_transmit_status()
        assert status["failing_universes"] == []
        assert status["last_send_error"] is None
        assert any(p[DATA_OFFSET + 1] == 128 for p in packets)
    finally:
        await controller.disconnect()


def test_set_channel_stores_an_integer():
    universe = DMXUniverse(universe=0)
    universe.set_channel(2, 127.6)
    assert universe.data[1] == 128 and isinstance(universe.data[1], int)


def test_sequence_numbers_never_hit_zero_and_run_per_universe():
    ctrl = DMXController()
    seen = [ctrl._next_sequence(0) for _ in range(600)]
    assert 0 not in seen
    assert min(seen) == 1 and max(seen) == 255
    assert ctrl._next_sequence(1) == 1, "each Port-Address keeps its own sequence"


def test_frame_bytes_cleans_any_value():
    data = [0, 255, 300, -4, 12.4, float("nan"), None]
    assert DMXController._frame_bytes(data) == bytes([0, 255, 255, 0, 12, 0, 0])
