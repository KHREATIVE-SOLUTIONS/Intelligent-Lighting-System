"""
DMX Transmitter Isolation
=========================

The transmitter used to share the event loop with the HTTP API, the WebSocket
broadcast and the 60fps engine, and it sends with a blocking `sendto`. Pointing
ArtNet at a port with no listener was enough to freeze the entire server: Windows
answers the send with ICMP port-unreachable, the send stalls, and every coroutine
behind it stops. The process stayed alive the whole time, which is what made it
hard to see - the log simply stopped mid-sentence.

An unreachable node is not an edge case for a venue. It is what happens when
somebody unplugs a cable mid-show.
"""

import asyncio
import time

import pytest

from app.schemas.dmx import DMXUniverse
from app.services.dmx.dmx_controller import DMXController


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.universes = [0]
    return ctrl


async def _loop_stays_responsive(seconds: float, budget: float = 0.25) -> float:
    """Worst delay the event loop takes to honour a short sleep."""
    worst = 0.0
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        t0 = time.perf_counter()
        await asyncio.sleep(0.02)
        worst = max(worst, time.perf_counter() - t0 - 0.02)
        assert worst < budget, f"event loop stalled {worst:.2f}s while DMX was sending"
    return worst


@pytest.mark.asyncio
async def test_the_event_loop_survives_an_unreachable_artnet_node(controller):
    """The regression: nothing is listening on 6454, and the API must keep serving."""
    await controller.connect()
    try:
        controller.universes[0] = DMXUniverse(universe=0)
        controller.universes[0].data = [255] * 512

        worst = await _loop_stays_responsive(3.0)

        assert controller.is_connected
        print(f"worst event-loop delay while transmitting: {worst * 1000:.0f} ms")
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_transmitting_does_not_run_on_the_event_loop(controller):
    """Output continues while the loop is busy, because it is not on the loop."""
    await controller.connect()
    try:
        controller.universes[0] = DMXUniverse(universe=0)
        await asyncio.sleep(0.3)
        before = controller.frames_sent

        # Occupy the event loop the way a burst of API traffic would.
        for _ in range(40):
            await asyncio.sleep(0.005)

        assert controller.frames_sent > before, (
            "no frames left while the event loop was busy - the transmitter is still "
            "sharing it"
        )
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_frame_rate_holds_near_the_target(controller):
    """Deadline pacing, so the rate does not walk away under its own overshoot."""
    await controller.connect()
    try:
        controller.universes[0] = DMXUniverse(universe=0)
        await asyncio.sleep(0.4)
        start_frames = controller.frames_sent
        t0 = time.perf_counter()
        await asyncio.sleep(2.0)
        sent = controller.frames_sent - start_frames
        rate = sent / (time.perf_counter() - t0)

        target = controller.target_fps
        print(f"measured {rate:.1f} fps against a {target} fps target")
        assert rate > target * 0.7, f"only {rate:.1f} fps against a {target} target"
        assert rate < target * 1.3, f"{rate:.1f} fps overruns the {target} target"
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_disconnect_stops_the_transmitter(controller):
    """No thread left running, and no sends against a closed socket."""
    await controller.connect()
    controller.universes[0] = DMXUniverse(universe=0)
    await asyncio.sleep(0.2)

    thread = controller.output_thread
    assert thread is not None and thread.is_alive()

    await controller.disconnect()

    assert not thread.is_alive(), "transmitter thread outlived disconnect()"
    assert controller.socket is None

    settled = controller.frames_sent
    await asyncio.sleep(0.3)
    assert controller.frames_sent == settled, "frames still leaving after disconnect"


@pytest.mark.asyncio
async def test_a_universe_appearing_mid_send_does_not_break_the_loop(controller):
    """The engine adds and drops universes from the loop while this thread reads."""
    await controller.connect()
    try:
        for i in range(30):
            controller.universes[i % 6] = DMXUniverse(universe=i % 6)
            await asyncio.sleep(0.01)
            controller.universes.pop((i + 3) % 6, None)

        assert controller.is_connected
        assert controller.output_thread.is_alive(), "transmitter died on a mutating dict"
    finally:
        await controller.disconnect()
