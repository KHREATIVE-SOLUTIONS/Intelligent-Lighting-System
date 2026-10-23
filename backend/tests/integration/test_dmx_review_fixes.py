"""
DMX Output: Races, Blackout and Bad Input
=========================================

A Connect landing while a Disconnect waited on its thread had its fresh socket
closed underneath it: status said connected while nothing went out. A blackout
left a running test pattern strobing. The rainbow pattern died on its first
frame. A string universe from a WebSocket client took that universe off the wire,
and a blackout with an infinite fade never happened at all.
"""

import asyncio
import math
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.endpoints import dmx as dmx_api
from app.schemas.dmx import ArtNetConfig, DMXBlackoutCommand
from app.services.dmx.dmx_controller import DMXController


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.port = 9  # discard; nothing needs to listen
    ctrl.config.broadcast = False
    return ctrl


def fake_request(**state):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


async def test_connect_during_disconnect_keeps_a_live_socket(controller):
    controller.get_universe(0)
    await controller.connect()
    await asyncio.gather(controller.disconnect(), controller.connect())

    try:
        assert controller.is_connected
        assert controller.socket is not None
        before = controller.frames_sent
        await asyncio.sleep(0.3)
        assert controller.frames_sent > before
    finally:
        await controller.disconnect()


async def test_config_change_racing_connect_keeps_output_running(controller):
    controller.get_universe(0)
    await controller.connect()
    await asyncio.gather(
        controller.update_config(ArtNetConfig(ip_address="127.0.0.1", port=9)),
        controller.connect(),
    )
    try:
        assert controller.socket is not None
        before = controller.frames_sent
        await asyncio.sleep(0.3)
        assert controller.frames_sent > before
    finally:
        await controller.disconnect()


async def test_blackout_stops_a_running_test_pattern(controller):
    await controller.run_test_pattern(0, "strobe")
    await asyncio.sleep(0.05)
    await controller.blackout()

    assert controller.test_pattern_task is None
    for _ in range(10):
        assert not any(controller.get_universe(0).data)
        await asyncio.sleep(0.03)


async def test_rainbow_pattern_runs_without_falling_over(controller):
    await controller.run_test_pattern(0, "rainbow")
    await asyncio.sleep(0.1)
    task = controller.test_pattern_task
    assert task is not None and not task.done()
    assert any(controller.get_universe(0).data)
    await controller.stop_test_pattern()


async def test_strobe_test_pattern_stays_under_the_show_flash_limit(controller):
    on_edges = 0
    await controller.run_test_pattern(0, "strobe")
    last = 0
    loop = asyncio.get_running_loop()
    end = loop.time() + 1.0
    while loop.time() < end:
        value = controller.get_universe(0).data[0]
        if value and not last:
            on_edges += 1
        last = value
        await asyncio.sleep(0.01)
    await controller.stop_test_pattern()
    assert on_edges <= 3


async def test_a_string_universe_is_stored_as_an_int(controller):
    await controller.set_channel("1", 1, 255)
    assert 1 in controller.universes
    assert "1" not in controller.universes


@pytest.mark.parametrize("universe", [-1, 40000, 1.5, "one", None, True, math.inf])
async def test_a_bad_universe_is_refused(controller, universe):
    with pytest.raises(ValueError):
        await controller.set_channel(universe, 1, 255)
    assert controller.universes == {}


@pytest.mark.parametrize("fade_time", [math.inf, math.nan, 61, -1])
def test_blackout_fade_is_bounded(fade_time):
    with pytest.raises(ValidationError):
        DMXBlackoutCommand(fade_time=fade_time)


async def test_controller_survives_an_unbounded_fade(controller):
    controller.get_universe(0).data = [200] * 512
    await asyncio.wait_for(controller.blackout(fade_time=math.inf), timeout=1.0)
    assert not any(controller.get_universe(0).data)


class FakeEngine:
    def __init__(self):
        self.grand_master = 0.8
        self.blackout_active = False
        self.levels = []

    def set_grand_master(self, level):
        self.grand_master = level
        self.levels.append(level)
        return level

    def blackout(self):
        self.blackout_active = True


async def test_full_blackout_fades_the_engine_instead_of_snapping(controller):
    engine = FakeEngine()
    request = fake_request(dmx_controller=controller, effects_engine=engine)

    await dmx_api.blackout(DMXBlackoutCommand(fade_time=0.2), request)

    assert engine.blackout_active
    fade = engine.levels[:-1]
    assert len(fade) > 2 and fade == sorted(fade, reverse=True) and fade[-1] == 0
    # The operator's master comes back once the latch holds, ready for restore.
    assert engine.grand_master == 0.8


async def test_previs_setup_keeps_the_rigs_net_and_subnet(controller):
    controller.config.net = 2
    controller.config.subnet = 3
    request = fake_request(dmx_controller=controller)

    await dmx_api.configure_for_broadcast(request)
    assert (controller.config.net, controller.config.subnet) == (2, 3)

    await dmx_api.configure_for_unicast(request, target_ip="127.0.0.1")
    assert (controller.config.net, controller.config.subnet) == (2, 3)


async def test_previs_connection_test_ends_on_time_and_is_stoppable(controller):
    request = fake_request(dmx_controller=controller)
    await dmx_api.test_previs_connection(request, duration=0.2)
    task = controller.test_pattern_task
    assert task is not None
    await asyncio.wait_for(task, timeout=1.0)
    assert not any(controller.get_universe(0).data[:12])

    await dmx_api.test_previs_connection(request, duration=5)
    await controller.stop_test_pattern()
    assert controller.test_pattern_task is None


def test_engine_time_survives_a_bad_step():
    from app.services.effects.effects_engine import EffectsEngine

    engine = EffectsEngine()
    engine.update(0.016)
    engine.update(float("nan"))
    engine.update(-5.0)
    engine.update(0.016)
    assert math.isfinite(engine.time) and engine.time >= 0
