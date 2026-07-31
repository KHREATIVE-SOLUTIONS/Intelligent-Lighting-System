"""
Flash-to-Identify Walkthrough
=============================

Contract section 5. The owner does not know which light is which, so the box
lights one and they tap where it is. Three things have to hold or the feature is
worse than not having it:

- it has to be reachable at all (a router nobody registers 404s on every call);
- an answer given twice must not silently drop the light in between, because the
  summary the owner reads says every light was checked;
- nothing may leave a fixture latched on, and the show has to get its levels
  back when the walkthrough ends.
"""

import asyncio

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.dmx.dmx_controller import DMXController


IDENTIFY_PATHS = [
    ("POST", "/api/rigs/1/identify/start"),
    ("GET", "/api/rigs/1/identify/abc"),
    ("POST", "/api/rigs/1/identify/abc/heartbeat"),
    ("POST", "/api/rigs/1/identify/abc/flash"),
    ("POST", "/api/rigs/1/identify/abc/position"),
    ("POST", "/api/rigs/1/identify/abc/skip"),
    ("POST", "/api/rigs/1/identify/abc/advance"),
    ("POST", "/api/rigs/1/identify/abc/end"),
]


@pytest.fixture
def dmx_state():
    """A DMX controller on app.state, as the real lifespan would leave one.

    The walkthrough writes through FixtureTestService, which needs one; without
    it every call is a 503 and the tests below would prove nothing.
    """
    from app.api.endpoints import fixture_test as fixture_test_module
    from app.api.endpoints import rig_identify as identify_module

    controller = DMXController()
    previous_dmx = getattr(app.state, "dmx_controller", None)
    previous_engine = getattr(app.state, "effects_engine", None)
    previous_service = fixture_test_module._test_service

    app.state.dmx_controller = controller
    app.state.effects_engine = None
    fixture_test_module._test_service = None
    identify_module._sessions.clear()

    yield controller

    for session in identify_module._sessions.values():
        for task in (session.watchdog_task, session.hold_task):
            if task is not None and not task.done():
                task.cancel()
    identify_module._sessions.clear()
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


async def _rig_with_lights(client: AsyncClient, sample_rig_data, sample_fixture_data, count=4):
    rig_response = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig_response.status_code == 201, rig_response.text
    rig_id = rig_response.json()["id"]

    fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert fixture_response.status_code in (200, 201), fixture_response.text
    profile = fixture_response.json()
    mode_id = profile["modes"][0]["id"]

    ids = []
    for index in range(count):
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": profile["id"],
            "mode_id": mode_id,
            "name": f"L{index + 1}",
            "universe": 0,
            "dmx_address": 1 + index * 20,
            "position_x": 0.0,
            "position_y": 0.0,
            "position_z": 0.0,
        })
        assert added.status_code == 201, added.text
        ids.append(added.json()["id"])
    return rig_id, ids


# ---------------------------------------------------------------------------
# Reachable at all, and behind the operator gate
# ---------------------------------------------------------------------------

def test_the_walkthrough_routes_are_registered():
    """app/api/endpoints/rig_identify.py was written and never included, so every
    call from the browser 404'd against a route table that had no such path."""
    registered = {route.path for route in app.routes}
    missing = [
        path for _, path in IDENTIFY_PATHS
        if path.replace("/1/", "/{rig_id}/").replace("/abc", "/{session_id}") not in registered
    ]
    assert not missing, f"the flash-to-identify router is not mounted: {missing}"


@pytest.mark.parametrize("method,path", IDENTIFY_PATHS)
async def test_the_walkthrough_requires_an_operator_credential(
    unauthenticated_client: AsyncClient, method, path
):
    """These endpoints drive the lights and write positions; none of them is on
    the public allowlist."""
    response = await unauthenticated_client.request(method, path, json={})
    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} with no operator token"
    )


# ---------------------------------------------------------------------------
# A double tap must not drop the light in between
# ---------------------------------------------------------------------------

async def test_two_taps_at_once_do_not_skip_the_next_light(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """One fat-fingered double tap on a touch plan is two requests. Answering the
    step the first one just advanced past leaves the light in between never lit,
    never asked about, and absent from the report - while the summary still says
    every light was checked."""
    rig_id, rig_fixture_ids = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data
    )

    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    assert started.status_code == 200, started.text
    session = started.json()
    session_id = session["session_id"]
    first = session["current"]["fixture_id"]
    assert first == rig_fixture_ids[0]

    body = {"position_x": -3.0, "position_z": 1.0, "fixture_id": first}
    url = f"/api/rigs/{rig_id}/identify/{session_id}/position"
    responses = await asyncio.gather(
        client.post(url, json=body),
        client.post(url, json=body),
        return_exceptions=True,
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409], f"a repeated answer was accepted twice: {codes}"

    state = (await client.get(f"/api/rigs/{rig_id}/identify/{session_id}")).json()
    assert state["step_number"] == 2
    assert state["current"]["fixture_id"] == rig_fixture_ids[1], (
        "the second light was never presented; it has no outcome and does not "
        "appear anywhere in the report"
    )

    await client.post(f"/api/rigs/{rig_id}/identify/{session_id}/end")


async def test_every_light_ends_with_an_outcome(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """The summary is the whole point: a total that counts lights nobody looked
    at is worse than no walkthrough."""
    rig_id, rig_fixture_ids = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data
    )
    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    session_id = started.json()["session_id"]

    state = started.json()
    while not state["complete"]:
        fixture_id = state["current"]["fixture_id"]
        base = f"/api/rigs/{rig_id}/identify/{session_id}"
        # Answer each one twice, the way an impatient owner does.
        for _ in range(2):
            response = await client.post(
                f"{base}/skip", json={"fixture_id": fixture_id}
            )
            if response.status_code == 200:
                state = response.json()
            else:
                assert response.status_code == 409, response.text

    assert state["complete"]
    assert state["total"] == len(rig_fixture_ids)
    accounted = state["placed"] + state["kept"] + state["no_response"]
    assert accounted == state["total"], (
        f"{state['total'] - accounted} of {state['total']} lights finished the "
        f"walkthrough with no outcome at all"
    )
    assert len(state["unresponsive"]) == len(rig_fixture_ids)


async def test_answering_a_light_the_walkthrough_has_moved_past_changes_nothing(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    rig_id, rig_fixture_ids = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data, count=2
    )
    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    session_id = started.json()["session_id"]
    base = f"/api/rigs/{rig_id}/identify/{session_id}"

    await client.post(f"{base}/position", json={
        "position_x": 1.0, "position_z": 1.0, "fixture_id": rig_fixture_ids[0],
    })
    stale = await client.post(f"{base}/position", json={
        "position_x": -9.0, "position_z": -9.0, "fixture_id": rig_fixture_ids[0],
    })
    assert stale.status_code == 409, stale.text

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    rows = {row["id"]: row for row in listed.json()}
    assert rows[rig_fixture_ids[0]]["position_x"] == pytest.approx(1.0)
    assert rows[rig_fixture_ids[1]]["position_x"] == pytest.approx(0.0), (
        "the stale answer was written onto the next light instead"
    )

    await client.post(f"{base}/end")


# ---------------------------------------------------------------------------
# Nothing is left latched on
# ---------------------------------------------------------------------------

def _fixture_slice(controller, universe, address, count):
    data = controller.get_universe(universe).data
    return list(data[address - 1:address - 1 + count])


async def test_stopping_the_fixture_test_leaves_the_light_dark(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """/test/stop and /test-all/stop only cancel the task. A hold that trusts the
    canceller to black it out leaves the fixture at full while the app reports it
    off - the one outcome this walkthrough is not allowed to leave behind."""
    rig_id, rig_fixture_ids = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data, count=2
    )
    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    await asyncio.sleep(0.05)

    lit = _fixture_slice(dmx_state, 0, 1, 16)
    assert max(lit) > 0, f"the walkthrough never lit the first fixture: {lit}"

    stopped = await client.post(f"/api/rigs/{rig_id}/fixtures/{rig_fixture_ids[0]}/test/stop")
    assert stopped.status_code == 200, stopped.text
    await asyncio.sleep(0.05)

    after = _fixture_slice(dmx_state, 0, 1, 16)
    assert max(after) == 0, (
        f"the fixture is still latched at {max(after)} after its test was "
        f"stopped: {after}"
    )

    await client.post(f"/api/rigs/{rig_id}/identify/{session_id}/end")


async def test_ending_the_walkthrough_puts_the_rooms_other_levels_back(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """House lights, a hazer or a static look parked through /api/dmx are not
    repainted by the effects engine, so zeroing every universe and never
    restoring leaves them dead once the walkthrough is over."""
    rig_id, _ = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data, count=2
    )
    parked = dmx_state.get_universe(0)
    parked.set_channel(401, 200)
    parked.set_channel(402, 120)

    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]

    assert dmx_state.get_universe(0).data[400] == 0, (
        "the walkthrough left the rest of the room lit; it cannot ask 'which one "
        "is that?' with everything else on"
    )

    ended = await client.post(f"/api/rigs/{rig_id}/identify/{session_id}/end")
    assert ended.status_code == 200, ended.text

    assert dmx_state.get_universe(0).data[400] == 200, (
        "channel 401 was parked at 200 and reads back "
        f"{dmx_state.get_universe(0).data[400]} - the walkthrough wiped it and "
        "never put it back"
    )
    assert dmx_state.get_universe(0).data[401] == 120


async def test_the_walkthrough_records_a_light_that_never_lit(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """Contract section 5: skipping has to record, not just move on."""
    rig_id, rig_fixture_ids = await _rig_with_lights(
        client, sample_rig_data, sample_fixture_data, count=2
    )
    started = await client.post(f"/api/rigs/{rig_id}/identify/start")
    session_id = started.json()["session_id"]
    base = f"/api/rigs/{rig_id}/identify/{session_id}"

    skipped = await client.post(f"{base}/skip", json={
        "reason": "nothing happened", "fixture_id": rig_fixture_ids[0],
    })
    assert skipped.status_code == 200, skipped.text
    state = skipped.json()
    assert state["no_response"] == 1
    assert state["unresponsive"][0]["fixture_id"] == rig_fixture_ids[0]

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    rows = {row["id"]: row for row in listed.json()}
    assert "identify:no-response" in (rows[rig_fixture_ids[0]].get("tags") or []), (
        "the mark is only in the session, so the owner loses it the moment they "
        "close the tab - and a light that never lit is the finding worth keeping"
    )

    await client.post(f"{base}/end")
