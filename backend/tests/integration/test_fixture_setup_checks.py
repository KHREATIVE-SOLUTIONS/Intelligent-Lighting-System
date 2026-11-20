"""
Per-Fixture Setup Checks
========================

The patch screen lights one fixture and asks the operator what they see. For
that to be worth having:

- it has to be reachable, and only by an operator;
- what it puts on the wire has to be a steady look that has been through the
  output stage, at the right slots, in the right colour;
- when the output stage would keep the light dark it has to say so, or a
  latched blackout reads as a dead fixture;
- nothing may be left lit, and the show gets its levels back, however the hold
  ends: stopped, cancelled from the old test route, timed out, or pushed aside
  by the walkthrough.

No socket is opened. Where the wire matters the controller is given a recorder
and its transmitter is stepped by hand.
"""

import asyncio

import numpy as np
import pytest
from httpx import AsyncClient

from app.main import app
from app.services.dmx.dmx_controller import DMXController
from app.services.dmx.output_stage import ROLE_FIXED, ROLE_INTENSITY
from app.services.fixture_test import setup_check
from app.services.fixture_test.setup_check import setup_hold


SETUP_PATHS = [
    ("GET", "/api/rigs/1/setup-checks"),
    ("POST", "/api/rigs/1/fixtures/1/setup-check/show"),
    ("POST", "/api/rigs/1/fixtures/1/setup-check/result"),
    ("POST", "/api/rigs/1/setup-check/heartbeat"),
    ("POST", "/api/rigs/1/setup-check/release"),
]

# The sample profile: pan, pan fine, tilt, tilt fine, dimmer, red, green, blue.
PAN, TILT, DIMMER, RED, GREEN, BLUE = 0, 2, 4, 5, 6, 7


class Recorder:
    """Stands in for the UDP socket. Keeps what it was asked to send."""

    def __init__(self):
        self.packets = []

    def sendto(self, packet, target):
        assert packet[:8] == b'Art-Net\x00'
        universe = packet[14] | (packet[15] << 8)
        self.packets.append((universe, np.frombuffer(bytes(packet[18:]), dtype=np.uint8)))

    def last(self, universe=0):
        return [data for u, data in self.packets if u == universe][-1]

    def close(self):
        pass


class FakeEngine:
    """As much of the effects engine as the suspension touches."""

    def __init__(self, callback):
        self._dmx_callback = callback

    def set_dmx_callback(self, callback):
        self._dmx_callback = callback


@pytest.fixture
def dmx_state():
    from app.api.endpoints import fixture_test as fixture_test_module
    from app.api.endpoints import rig_identify as identify_module

    controller = DMXController()
    controller.config.ip_address = "127.0.0.1"
    controller.config.broadcast = False
    controller.socket = Recorder()
    controller.is_connected = True   # no thread: the tests step the transmitter

    previous_dmx = getattr(app.state, "dmx_controller", None)
    previous_engine = getattr(app.state, "effects_engine", None)
    previous_service = fixture_test_module._test_service

    app.state.dmx_controller = controller
    app.state.effects_engine = None
    fixture_test_module._test_service = None
    identify_module._sessions.clear()
    setup_hold.current = None
    setup_hold._lock = None

    yield controller

    hold = setup_hold.current
    if hold is not None and hold.task is not None and not hold.task.done():
        hold.task.cancel()
    setup_hold.current = None
    setup_hold._lock = None
    for session in identify_module._sessions.values():
        for task in (session.watchdog_task, session.hold_task):
            if task is not None and not task.done():
                task.cancel()
    identify_module._sessions.clear()
    controller.is_connected = False
    fixture_test_module._test_service = previous_service
    if previous_dmx is None:
        delattr(app.state, "dmx_controller")
    else:
        app.state.dmx_controller = previous_dmx
    if previous_engine is None:
        if hasattr(app.state, "effects_engine"):
            delattr(app.state, "effects_engine")
    else:
        app.state.effects_engine = previous_engine


async def _rig_with_lights(client, sample_rig_data, sample_fixture_data, count=2):
    rig = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig.status_code == 201, rig.text
    rig_id = rig.json()["id"]
    profile = (await client.post("/api/fixtures/", json=sample_fixture_data)).json()
    ids = []
    for index in range(count):
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": profile["id"],
            "mode_id": profile["modes"][0]["id"],
            "name": f"L{index + 1}",
            "universe": 0,
            "dmx_address": 1 + index * 20,
        })
        assert added.status_code == 201, added.text
        ids.append(added.json()["id"])
    return rig_id, ids


def _show(client, rig_id, fixture_id, check, look):
    return client.post(
        f"/api/rigs/{rig_id}/fixtures/{fixture_id}/setup-check/show",
        json={"check": check, "look": look},
    )


def _slots(controller, address=1, count=16, universe=0):
    data = controller.get_universe(universe).data
    return list(data[address - 1:address - 1 + count])


def _settle(controller, seconds=1.0, fps=40):
    """Step the transmitter until a rise the limiter slowed has arrived."""
    now = 100.0
    for _ in range(int(seconds * fps)):
        controller._transmit_frame(now)
        now += 1.0 / fps
    return controller.socket.last()


# ---------------------------------------------------------------------------
# Reachable, and behind the operator gate
# ---------------------------------------------------------------------------


def test_the_setup_check_routes_are_registered():
    registered = {route.path for route in app.routes}
    missing = [
        path for _, path in SETUP_PATHS
        if path.replace("/rigs/1", "/rigs/{rig_id}").replace("/fixtures/1", "/fixtures/{fixture_id}")
        not in registered
    ]
    assert not missing, f"the setup check router is not mounted: {missing}"


@pytest.mark.parametrize("method,path", SETUP_PATHS)
async def test_setup_checks_require_an_operator_credential(
    unauthenticated_client: AsyncClient, method, path
):
    response = await unauthenticated_client.request(method, path, json={})
    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} with no operator token"
    )


# ---------------------------------------------------------------------------
# What a fixture can be checked for comes from the backend
# ---------------------------------------------------------------------------


async def test_the_listing_says_what_each_fixture_supports_and_lights_nothing(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)

    listed = await client.get(f"/api/rigs/{rig_id}/setup-checks")
    assert listed.status_code == 200, listed.text
    body = listed.json()

    assert [f["fixture_id"] for f in body["fixtures"]] == ids
    checks = {c["check"]: c for c in body["fixtures"][0]["checks"]}
    assert checks["flash"]["looks"] == ["white"]
    assert checks["colour"]["looks"] == ["red", "green", "blue"]
    assert checks["pan"]["looks"] == ["centre", "pan_low", "pan_high"]
    assert checks["tilt"]["available"]
    assert all(c["result"] is None for c in checks.values())
    assert body["active"] is None
    assert dmx_state.universes == {}, (
        "reading the checks created a universe, which the transmitter would "
        "then send zeros on"
    )


def test_a_fixture_that_cannot_do_a_check_is_told_why():
    par = [{"channel_number": 1, "channel_type": "dimmer"}]
    checks = {c["check"]: c for c in setup_check.capabilities(par, {"dimmer": 0})}
    assert checks["flash"]["available"]
    assert not checks["colour"]["available"] and "colour" in checks["colour"]["reason"]
    assert not checks["pan"]["available"] and "move" in checks["pan"]["reason"]

    no_mode = setup_check.capabilities([], {})
    assert not any(c["available"] for c in no_mode)
    assert all("mode" in c["reason"] for c in no_mode)


def test_a_cmy_fixture_makes_red_by_closing_the_other_two_flags():
    channels = [
        {"channel_number": 1, "channel_type": "dimmer"},
        {"channel_number": 2, "channel_type": "cyan"},
        {"channel_number": 3, "channel_type": "magenta"},
        {"channel_number": 4, "channel_type": "yellow"},
    ]
    ch_map = {"dimmer": 0, "cyan": 1, "magenta": 2, "yellow": 3}
    checks = {c["check"]: c for c in setup_check.capabilities(channels, ch_map)}
    assert checks["colour"]["looks"] == ["red", "green", "blue"]
    assert setup_check.look_values(channels, ch_map, 4, 255, "red") == {0: 255, 1: 0, 2: 255, 3: 255}
    # White is every flag open, which is DMX zero.
    assert setup_check.look_values(channels, ch_map, 4, 255, "white") == {0: 255, 1: 0, 2: 0, 3: 0}


def test_the_shutter_is_opened_not_strobed_and_the_strobe_channel_parked():
    channels = [
        {"channel_number": 1, "channel_type": "dimmer"},
        {"channel_number": 2, "channel_type": "shutter", "value_ranges": [
            {"name": "Closed", "min_value": 0, "max_value": 9},
            {"name": "Open", "min_value": 10, "max_value": 19},
            {"name": "Strobe slow-fast", "min_value": 20, "max_value": 255},
        ]},
        {"channel_number": 3, "channel_type": "strobe", "default_value": 200},
    ]
    values = setup_check.look_values(channels, {"dimmer": 0, "shutter": 1, "strobe": 2}, 3, 255, "white")
    assert values == {0: 255, 1: 14, 2: 0}


# ---------------------------------------------------------------------------
# What reaches the wire
# ---------------------------------------------------------------------------


async def test_a_flash_reaches_the_wire_through_the_output_stage(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    dmx_state.output_stage.set_patch({0: [{
        PAN: ROLE_FIXED, 1: ROLE_FIXED, TILT: ROLE_FIXED, 3: ROLE_FIXED,
        DIMMER: ROLE_INTENSITY, RED: "colour", GREEN: "colour", BLUE: "colour",
    }]})

    shown = await _show(client, rig_id, ids[0], "flash", "white")
    assert shown.status_code == 200, shown.text
    assert shown.json()["active"]["fixture_id"] == ids[0]

    frame = _settle(dmx_state)
    assert list(frame[[DIMMER, RED, GREEN, BLUE]]) == [255, 255, 255, 255]
    # Held at the middle of its travel, not on the end stop DMX zero is.
    assert (frame[PAN], frame[TILT]) == (128, 128)
    assert not frame[20:36].any(), "the second fixture lit as well"

    dmx_state.output_stage.set_master(0.5)
    half = _settle(dmx_state)
    assert half[DIMMER] == 127 and half[PAN] == 128, (
        "the test light is not under the grand master, so it is going round "
        "the output stage"
    )


async def test_each_colour_is_one_colour_and_changing_look_never_passes_through_dark(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)

    for look, lit in (("red", RED), ("green", GREEN), ("blue", BLUE)):
        shown = await _show(client, rig_id, ids[0], "colour", look)
        assert shown.status_code == 200, shown.text
        slots = _slots(dmx_state)
        assert slots[DIMMER] == 255, (
            f"the dimmer dropped on the way to {look}: a blink between looks is "
            "a flash, and this is the one screen that must not make one"
        )
        assert [slots[c] for c in (RED, GREEN, BLUE)] == [255 if c == lit else 0 for c in (RED, GREEN, BLUE)]
        assert shown.json()["active"]["look"] == look


async def test_pan_and_tilt_step_either_side_of_centre(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    seen = {}
    for check, look in (("pan", "pan_low"), ("pan", "pan_high"), ("tilt", "tilt_low"),
                        ("tilt", "tilt_high"), ("pan", "centre")):
        assert (await _show(client, rig_id, ids[0], check, look)).status_code == 200
        slots = _slots(dmx_state)
        seen[look] = (slots[PAN], slots[TILT])
        assert slots[DIMMER] == 255
    assert seen["pan_low"][0] < 128 < seen["pan_high"][0]
    assert seen["tilt_low"][1] < 128 < seen["tilt_high"][1]
    assert seen["centre"] == (128, 128)
    assert seen["pan_low"][1] == 128 and seen["tilt_high"][0] == 128


async def test_a_look_the_fixture_does_not_have_is_refused(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    assert (await _show(client, rig_id, ids[0], "colour", "pan_low")).status_code == 422
    assert (await _show(client, rig_id, ids[0], "nonsense", "white")).status_code == 422
    assert (await _show(client, rig_id, 99999, "flash", "white")).status_code == 404
    assert setup_hold.active() is None


# ---------------------------------------------------------------------------
# The output stage has the last word, and the operator is told
# ---------------------------------------------------------------------------


async def test_a_latched_blackout_is_reported_instead_of_a_dead_looking_fixture(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    dmx_state.output_stage.blackout()

    refused = await _show(client, rig_id, ids[0], "flash", "white")
    assert refused.status_code == 409, refused.text
    assert "lackout" in refused.json()["detail"]
    assert setup_hold.active() is None, "the show was parked for a light nobody can see"

    listed = (await client.get(f"/api/rigs/{rig_id}/setup-checks")).json()
    assert "lackout" in listed["output_blocked_reason"]

    dmx_state.output_stage.restore()
    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200

    # Pressed while a light is held: the wire goes dark and the heartbeat says why.
    dmx_state.output_stage.blackout()
    assert not _settle(dmx_state, 0.1)[:16].any()
    beat = (await client.post(f"/api/rigs/{rig_id}/setup-check/heartbeat")).json()
    assert "lackout" in beat["active"]["output_blocked_reason"]


async def test_a_strobe_fixture_held_off_says_so(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    dmx_state.output_stage.set_flash_policy(False, 3.0)
    dmx_state.output_stage.set_patch({}, strobe_slots={0: range(0, 16)})

    refused = await _show(client, rig_id, ids[0], "flash", "white")
    assert refused.status_code == 409 and "strobe" in refused.json()["detail"].lower()
    # The fixture beside it is not a strobe and checks as normal.
    assert (await _show(client, rig_id, ids[1], "flash", "white")).status_code == 200

    listed = (await client.get(f"/api/rigs/{rig_id}/setup-checks")).json()
    assert listed["fixtures"][0]["output_blocked_reason"]
    assert listed["fixtures"][1]["output_blocked_reason"] is None


# ---------------------------------------------------------------------------
# Nothing left lit, and the show comes back
# ---------------------------------------------------------------------------


async def test_release_darkens_the_fixture_and_puts_the_show_back(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    engine = FakeEngine(dmx_state.write_universe)
    app.state.effects_engine = engine
    house = dmx_state.get_universe(0)
    house.set_channel(401, 200)
    house.set_channel(5, 90)       # the show's own level on the fixture under test

    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200
    assert engine._dmx_callback is None, "the show is still repainting over the test light"
    assert dmx_state.get_universe(0).data[400] == 0

    # Moving to the next fixture keeps the show parked and darkens the first.
    assert (await _show(client, rig_id, ids[1], "flash", "white")).status_code == 200
    assert max(_slots(dmx_state, 1)) == 0
    assert _slots(dmx_state, 21)[DIMMER] == 255
    assert engine._dmx_callback is None

    released = await client.post(f"/api/rigs/{rig_id}/setup-check/release")
    assert released.status_code == 200 and released.json()["released"] is True
    assert released.json()["active"] is None
    assert max(_slots(dmx_state, 21)) == 0
    assert dmx_state.get_universe(0).data[400] == 200
    assert dmx_state.get_universe(0).data[4] == 90
    assert engine._dmx_callback == dmx_state.write_universe

    again = await client.post(f"/api/rigs/{rig_id}/setup-check/release")
    assert again.status_code == 200 and again.json()["released"] is False


async def test_a_universe_borrowed_for_a_check_leaves_the_wire_afterwards(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """Left behind it would send zeros forever on a universe this box does not
    drive, fighting whatever console does."""
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    dmx_state.is_connected = False   # nothing transmitting, so release is immediate
    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200
    assert 0 in dmx_state.universes
    await client.post(f"/api/rigs/{rig_id}/setup-check/release")
    assert 0 not in dmx_state.universes


async def test_the_old_test_stop_route_releases_a_check_completely(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """/test/stop only cancels the task. The hold has to clean up after itself,
    show included, or the room stays dark with the app reporting all clear."""
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    engine = FakeEngine(dmx_state.write_universe)
    app.state.effects_engine = engine
    dmx_state.get_universe(0).set_channel(401, 200)

    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200
    stopped = await client.post(f"/api/rigs/{rig_id}/fixtures/{ids[0]}/test/stop")
    assert stopped.status_code == 200, stopped.text
    await asyncio.sleep(0.05)

    assert max(_slots(dmx_state)) == 0
    assert dmx_state.get_universe(0).data[400] == 200
    assert engine._dmx_callback == dmx_state.write_universe
    assert setup_hold.active() is None


@pytest.mark.parametrize("limit", ["HOLD_MAX_S", "HOLD_IDLE_TIMEOUT_S"])
async def test_a_hold_nobody_is_watching_lets_go_by_itself(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, monkeypatch, limit
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    engine = FakeEngine(dmx_state.write_universe)
    app.state.effects_engine = engine
    monkeypatch.setattr(setup_check, "HOLD_REASSERT_S", 0.02)
    monkeypatch.setattr(setup_check, limit, 0.05)

    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200
    assert _slots(dmx_state)[DIMMER] == 255
    await asyncio.sleep(0.3)

    assert max(_slots(dmx_state)) == 0, "the fixture is still lit with nobody watching"
    assert engine._dmx_callback == dmx_state.write_universe
    beat = (await client.post(f"/api/rigs/{rig_id}/setup-check/heartbeat")).json()
    assert beat["active"] is None


async def test_a_heartbeat_keeps_the_light_up(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, monkeypatch
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    monkeypatch.setattr(setup_check, "HOLD_REASSERT_S", 0.02)
    monkeypatch.setattr(setup_check, "HOLD_IDLE_TIMEOUT_S", 0.15)

    assert (await _show(client, rig_id, ids[0], "flash", "white")).status_code == 200
    for _ in range(6):
        await asyncio.sleep(0.06)
        beat = await client.post(f"/api/rigs/{rig_id}/setup-check/heartbeat")
        assert beat.json()["active"] is not None
    assert _slots(dmx_state)[DIMMER] == 255


async def test_the_walkthrough_and_a_check_never_both_hold_the_show(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """Nested, the inner one parks a dark room as "the show" and the outer
    restore then puts the dark room back."""
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    engine = FakeEngine(dmx_state.write_universe)
    app.state.effects_engine = engine
    dmx_state.get_universe(0).set_channel(401, 200)

    assert (await _show(client, rig_id, ids[1], "flash", "white")).status_code == 200
    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    assert started.status_code == 200, started.text
    assert setup_hold.active() is None, "the check is still holding under the walkthrough"

    assert (await _show(client, rig_id, ids[1], "flash", "white")).status_code == 200
    session_id = started.json()["session_id"]
    gone = await client.get(f"/api/rigs/{rig_id}/identify/{session_id}")
    assert gone.status_code == 404, "the walkthrough is still holding under the check"

    await client.post(f"/api/rigs/{rig_id}/setup-check/release")
    assert dmx_state.get_universe(0).data[400] == 200, (
        "the room's own levels were lost between the two"
    )
    assert engine._dmx_callback == dmx_state.write_universe


# ---------------------------------------------------------------------------
# What the operator saw is kept
# ---------------------------------------------------------------------------


async def test_answers_are_kept_on_the_fixture(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, ids = await _rig_with_lights(client, sample_rig_data, sample_fixture_data)
    url = f"/api/rigs/{rig_id}/fixtures/{ids[0]}/setup-check/result"

    failed = await client.post(url, json={"check": "flash", "passed": False})
    assert failed.status_code == 200, failed.text
    assert failed.json()["no_response"] is True
    await client.post(url, json={"check": "colour", "passed": True})

    rows = {r["id"]: r for r in (await client.get(f"/api/rigs/{rig_id}/fixtures")).json()}
    assert set(rows[ids[0]]["tags"]) == {"setup:flash:fail", "identify:no-response", "setup:colour:ok"}
    assert rows[ids[1]]["tags"] == []

    # Changing an answer replaces it; a pass clears the never-lit mark.
    await client.post(url, json={"check": "flash", "passed": True})
    listed = (await client.get(f"/api/rigs/{rig_id}/setup-checks")).json()
    first = listed["fixtures"][0]
    assert {c["check"]: c["result"] for c in first["checks"]} == {
        "flash": "ok", "colour": "ok", "pan": None, "tilt": None}
    assert first["no_response"] is False

    cleared = await client.post(url, json={"check": "colour", "passed": None})
    assert {c["check"]: c["result"] for c in cleared.json()["checks"]}["colour"] is None
    assert (await client.post(url, json={"check": "bogus", "passed": True})).status_code == 422
