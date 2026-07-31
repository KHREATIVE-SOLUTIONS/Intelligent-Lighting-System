"""
DMX Transmit-Set Tests
======================

The controller must only transmit universes this box actually drives, and must never
leave one latched at full.

Both failure modes here are silent on our side and destructive at the venue. Art-Net
Port-Address 0 is the common field default, so transmitting an unowned universe puts us
into whatever merge behaviour the node implements - under LTP, or as sole source, we win
and the house rig does what we say. Nothing in our logs would show it.
"""

import asyncio

import pytest

from app.schemas.dmx import DMXUniverse
from app.services.dmx.dmx_controller import DMXController


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.universes = [0]
    return ctrl


@pytest.mark.asyncio
async def test_connect_does_not_claim_a_universe_nothing_drives(controller):
    """A freshly connected controller transmits nothing until something writes."""
    await controller.connect()
    try:
        assert controller.universes == {}, (
            "connect() pre-seeded %s - those transmit zeros on universes the rig may not own"
            % sorted(controller.universes)
        )
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_only_written_universes_are_transmitted(controller):
    """Driving universes 4 and 5 must not put universe 0 on the wire."""
    await controller.connect()
    try:
        for universe in (4, 5):
            controller.universes[universe] = DMXUniverse(universe=universe)
            controller.universes[universe].data = [7] * 512

        await asyncio.sleep(0.1)

        assert sorted(controller.universes) == [4, 5]
        assert 0 not in controller.universes
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_stopping_a_test_pattern_does_not_latch_the_universe_on(controller):
    """The safety case: a pattern stopped on an on-phase must not stay at full."""
    await controller.connect()
    try:
        await controller.run_test_pattern(9, "strobe", max_duration=5.0)

        # Let it reach an on-phase, then stop mid-cycle.
        for _ in range(40):
            await asyncio.sleep(0.02)
            entry = controller.universes.get(9)
            if entry is not None and max(entry.data) > 0:
                break

        await controller.stop_test_pattern()
        await asyncio.sleep(0.05)

        entry = controller.universes.get(9)
        if entry is not None:
            assert max(entry.data) == 0, (
                "universe 9 latched at %d after stop - every channel would sit at full "
                "indefinitely with no correcting frame" % max(entry.data)
            )
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_test_pattern_timeout_also_releases_the_universe(controller):
    """The duration timeout fires with nobody watching, so it must clean up too."""
    await controller.connect()
    try:
        await controller.run_test_pattern(11, "strobe", max_duration=0.25)
        await asyncio.sleep(0.6)

        entry = controller.universes.get(11)
        if entry is not None:
            assert max(entry.data) == 0, (
                "universe 11 latched at %d after the auto-timeout" % max(entry.data)
            )
    finally:
        await controller.disconnect()


@pytest.mark.asyncio
async def test_all_on_holds_then_releases_rather_than_latching_forever(controller):
    """`all_on` wrote 512 bytes and returned, stranding every channel at 255.

    It completes normally, so cancellation and timeout handling never saw it - this is
    the deterministic case, not a race. It must hold for its duration (so the pattern is
    still useful for ringing out a rig) and then black out.
    """
    await controller.connect()
    try:
        await controller.run_test_pattern(13, "all_on", max_duration=0.4)
        await asyncio.sleep(0.15)

        entry = controller.universes.get(13)
        assert entry is not None and max(entry.data) == 255, (
            "all_on did not hold - the pattern is useless for testing a rig"
        )

        await asyncio.sleep(0.7)

        entry = controller.universes.get(13)
        assert entry is None or max(entry.data) == 0, (
            "universe 13 still at %d after all_on finished - every channel would sit at "
            "full with strobes open indefinitely" % max(entry.data)
        )
    finally:
        await controller.stop_test_pattern()
        await controller.disconnect()


@pytest.mark.asyncio
async def test_a_borrowed_universe_is_not_transmitted_forever(controller):
    """Test patterns must not permanently enlarge the per-frame transmit set."""
    await controller.connect()
    try:
        for universe in (40, 41, 42):
            await controller.run_test_pattern(universe, "all_on", max_duration=0.2)
            await asyncio.sleep(0.75)

        leftover = [u for u in (40, 41, 42) if u in controller.universes]
        assert not leftover, (
            "universes %s still in the transmit set; repeated test patterns would grow "
            "the 40fps send loop without bound" % leftover
        )
    finally:
        await controller.stop_test_pattern()
        await controller.disconnect()


@pytest.mark.asyncio
async def test_restarting_a_pattern_inside_the_release_window_is_safe(controller):
    """A pending release must not pop the universe out from under a new run.

    Releasing is deferred so the blackout frame reaches the wire first. Re-running a
    pattern on the same universe inside that window leaves a stale release in flight;
    if it fires it removes the entry the running pattern is writing to.
    """
    await controller.connect()
    try:
        # Ends at ~0.10s, so its release comes due at ~0.35s.
        await controller.run_test_pattern(17, "all_on", max_duration=0.10)
        await asyncio.sleep(0.20)

        # Restart while that release is still in flight.
        await controller.run_test_pattern(17, "all_on", max_duration=3.0)
        await asyncio.sleep(0.02)

        # all_on writes once and then holds, so this frame stays put until the stale
        # release wakes. A running pattern legitimately sits at zero (a strobe spends
        # half its cycle there); pinning it makes the race deterministic instead of
        # dependent on which phase the release happens to land in.
        controller.universes[17].data = [0] * 512

        await asyncio.sleep(0.30)

        assert 17 in controller.universes, (
            "a stale release popped the universe out from under the running pattern"
        )

        await controller.stop_test_pattern()
        await asyncio.sleep(0.45)

        # The restarted run still owns the borrow, so it must hand the universe back.
        assert 17 not in controller.universes, "universe 17 leaked after the restarted run"
    finally:
        await controller.stop_test_pattern()
        await controller.disconnect()


@pytest.mark.asyncio
async def test_output_loop_survives_universes_appearing_and_vanishing(controller):
    """The send loop awaits mid-iteration, so the transmit set can mutate under it."""
    await controller.connect()
    try:
        async def churn():
            for i in range(60):
                universe = 20 + (i % 5)
                controller.universes[universe] = DMXUniverse(universe=universe)
                await asyncio.sleep(0.005)
                controller.universes.pop(universe, None)

        await asyncio.wait_for(churn(), timeout=10)
        assert controller.is_connected, "output loop died while the transmit set changed"
    finally:
        await controller.disconnect()
