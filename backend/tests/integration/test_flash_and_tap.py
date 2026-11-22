"""
Flash-and-tap locate mode
=========================

docs/FLASH_AND_TAP.md. A patch sheet import draws every fixture on a generated
guess and tags it position_unconfirmed. Locate mode is how a guess becomes a
fact: one light comes on, a person says where it is, and the flag comes off.

What has to hold:

- a tap or "it is where the plan shows it" confirms; skipping and "leave it"
  confirm nothing;
- only=unconfirmed walks the guesses and nothing else, and says which lights
  it could not show and why;
- a row is walked ends first, the lights between are spaced evenly along the
  line joining the two taps and stay unconfirmed until the row check passes;
- the row check is one steady light at a time, never two, never fast;
- every way out leaves the rig dark and the show's own levels back in place.

All of it runs against the in-memory DMX controller. Nothing here, and nothing
anywhere else, starts a locate session against real output.
"""

import asyncio

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.dmx.dmx_controller import DMXController
from app.services.venue_import.apply import (
    TAG_UNCONFIRMED,
    TAG_UNPLACED,
    is_unconfirmed,
    position_source,
    with_position_confirmed,
    with_position_source,
)

GUESS = ["position_source:template", "position_unconfirmed"]
MEASURED = ["position_source:csv"]
FOOTPRINT = 16


@pytest.fixture
def dmx_state():
    """A DMX controller on app.state, as the real lifespan would leave one."""
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


@pytest.fixture
def fast_row_check(monkeypatch):
    """The row check at test speed. The order and the one-at-a-time rule are
    what is under test, not the 1.5 seconds."""
    from app.api.endpoints import rig_identify as identify_module

    monkeypatch.setattr(identify_module, "ROW_CHECK_STEP_S", 0.04)
    return 0.04


def light(name, address, x, z, *, y=6.0, group=None, tags=None, active=True):
    return {
        "name": name, "dmx_address": address, "position_x": x, "position_y": y,
        "position_z": z, "group_name": group, "tags": list(GUESS if tags is None else tags),
        "is_active": active,
    }


def row(prefix, first_address, xs, z, group, **extra):
    """A straight row on consecutive addresses, drawn left to right."""
    return [
        light(f"{prefix}{n}", first_address + (n - 1) * FOOTPRINT, x, z, group=group, **extra)
        for n, x in enumerate(xs, start=1)
    ]


async def build_rig(client: AsyncClient, sample_rig_data, sample_fixture_data, lights):
    rig = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig.status_code == 201, rig.text
    rig_id = rig.json()["id"]

    profile = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert profile.status_code in (200, 201), profile.text
    profile = profile.json()

    ids = {}
    for spec in lights:
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": profile["id"], "mode_id": profile["modes"][0]["id"],
            "universe": 0, **spec,
        })
        assert added.status_code == 201, added.text
        ids[spec["name"]] = added.json()["id"]
    return rig_id, ids


async def fixtures_by_name(client: AsyncClient, rig_id: int) -> dict:
    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text
    return {entry["name"]: entry for entry in listed.json()}


async def start(client: AsyncClient, rig_id: int, only="unconfirmed"):
    params = {"only": only} if only else None
    started = await client.post(f"/api/rigs/{rig_id}/identify/start", params=params)
    assert started.status_code == 200, started.text
    state = started.json()
    return state, f"/api/rigs/{rig_id}/identify/{state['session_id']}"


async def tap(client: AsyncClient, base: str, state: dict, x: float, z: float) -> dict:
    response = await client.post(f"{base}/position", json={
        "position_x": x, "position_z": z, "fixture_id": state["current"]["fixture_id"],
    })
    assert response.status_code == 200, response.text
    return response.json()


def lit_fixtures(controller, lights) -> list:
    """Names of the lights with anything above zero on their channels."""
    data = controller.get_universe(0).data
    return [
        spec["name"] for spec in lights
        if max(data[spec["dmx_address"] - 1:spec["dmx_address"] - 1 + FOOTPRINT]) > 0
    ]


# ---------------------------------------------------------------------------
# The tags
# ---------------------------------------------------------------------------

def test_a_new_source_replaces_the_old_one_and_never_edits_in_place():
    before = ["position_source:template", "group:Spots", "position_unconfirmed"]
    after = with_position_source(before, "tap", confirmed=True)

    assert after == ["position_source:tap", "group:Spots"]
    assert before == ["position_source:template", "group:Spots", "position_unconfirmed"], (
        "the tags column is plain JSON: a list changed in place is never written back"
    )
    assert position_source(after) == "tap" and not is_unconfirmed(after)


def test_a_row_fit_is_a_position_that_is_still_a_guess():
    fitted = with_position_source(["position_source:template", TAG_UNCONFIRMED], "row_fit", confirmed=False)
    assert position_source(fitted) == "row_fit" and is_unconfirmed(fitted)

    passed = with_position_confirmed(fitted)
    assert position_source(passed) == "row_fit" and not is_unconfirmed(passed)


def test_a_tap_places_a_fixture_that_had_no_position():
    tapped = with_position_source(["position_source:none", TAG_UNPLACED], "tap", confirmed=True)
    assert tapped == ["position_source:tap"]
    assert position_source(None) is None and position_source(["group:x"]) is None


# ---------------------------------------------------------------------------
# What confirms and what does not
# ---------------------------------------------------------------------------

async def test_a_tap_confirms_and_skipping_does_not(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = [
        light("Tapped", 1, 0.0, 0.0), light("Skipped", 41, 1.0, 0.0),
        light("Left", 81, 2.0, 0.0), light("Agreed", 121, 3.0, 0.0),
    ]
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id, only=None)
    assert state["mode"] == "all" and state["still_unconfirmed"] == 4

    state = await tap(client, base, state, -2.5, 1.5)
    state = (await client.post(f"{base}/skip", json={"fixture_id": ids["Skipped"]})).json()
    state = (await client.post(f"{base}/advance", params={"fixture_id": ids["Left"]})).json()
    confirmed = await client.post(f"{base}/confirm", params={"fixture_id": ids["Agreed"]})
    assert confirmed.status_code == 200, confirmed.text
    state = confirmed.json()

    assert state["complete"]
    assert (state["placed"], state["no_response"], state["kept"], state["confirmed"]) == (1, 1, 1, 1)
    assert state["still_unconfirmed"] == 2

    rows = await fixtures_by_name(client, rig_id)
    assert "position_source:tap" in rows["Tapped"]["tags"]
    assert TAG_UNCONFIRMED not in rows["Tapped"]["tags"]
    assert (rows["Tapped"]["position_x"], rows["Tapped"]["position_z"]) == (-2.5, 1.5)
    assert rows["Tapped"]["position_y"] == 6.0, "a tap is X and Z; the height is the row's"

    for name in ("Skipped", "Left"):
        assert TAG_UNCONFIRMED in rows[name]["tags"], f"{name} was never located but lost its flag"
        assert "position_source:template" in rows[name]["tags"]

    assert "position_source:confirmed" in rows["Agreed"]["tags"]
    assert TAG_UNCONFIRMED not in rows["Agreed"]["tags"]
    assert rows["Agreed"]["position_x"] == 3.0, "accepting the drawing must not move the light"


async def test_agreeing_with_a_measured_position_keeps_where_it_was_measured_from(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = [light("Surveyed", 1, 1.0, 1.0, tags=MEASURED)]
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    _, base = await start(client, rig_id, only=None)

    response = await client.post(f"{base}/confirm", params={"fixture_id": ids["Surveyed"]})
    assert response.status_code == 200, response.text

    rows = await fixtures_by_name(client, rig_id)
    assert rows["Surveyed"]["tags"] == MEASURED


# ---------------------------------------------------------------------------
# Only what needs it
# ---------------------------------------------------------------------------

async def test_only_unconfirmed_leaves_measured_lights_out_and_names_the_ones_it_cannot_show(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = [
        light("Measured", 1, -4.0, 0.0, tags=MEASURED),
        light("Guess A", 41, -2.0, 0.0),
        light("Guess B", 81, 2.0, 0.0),
        light("No Profile", 121, 3.0, 0.0, active=False, tags=GUESS + ["unmatched_type"]),
        light("Clash", 161, 4.0, 0.0, active=False, tags=GUESS + ["address_clash"]),
        light("Off And Measured", 201, 5.0, 0.0, active=False, tags=MEASURED),
    ]
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)

    state, base = await start(client, rig_id)

    assert state["mode"] == "unconfirmed" and state["total"] == 2
    assert state["current"]["fixture_id"] == ids["Guess A"]
    assert state["still_unconfirmed"] == 2
    assert state["not_located_count"] == 2
    reasons = {entry["label"]: entry["reason"] for entry in state["not_located"]}
    assert set(reasons) == {"No Profile", "Clash"}, (
        "a switched-off guess is reported as not located; a switched-off measured light is not a guess"
    )
    assert "profile" in reasons["No Profile"] and "shares DMX channels" in reasons["Clash"]

    state = await tap(client, base, state, -1.0, 0.0)
    state = await tap(client, base, state, 1.0, 0.0)
    assert state["complete"] and state["still_unconfirmed"] == 0
    assert state["not_located_count"] == 2, "finishing the walk does not locate what could not be lit"

    rows = await fixtures_by_name(client, rig_id)
    assert rows["Measured"]["position_x"] == -4.0 and rows["Measured"]["tags"] == MEASURED
    assert TAG_UNCONFIRMED in rows["No Profile"]["tags"]


async def test_a_rig_with_no_guesses_left_is_refused_before_the_show_is_touched(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = [
        light("Measured", 1, 0.0, 0.0, tags=MEASURED),
        light("No Profile", 41, 3.0, 0.0, active=False, tags=GUESS + ["unmatched_type"]),
    ]
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    dmx_state.get_universe(0).set_channel(401, 200)

    refused = await client.post(f"/api/rigs/{rig_id}/identify/start", params={"only": "unconfirmed"})

    assert refused.status_code == 400, refused.text
    assert "No Profile" in refused.json()["detail"]
    assert dmx_state.get_universe(0).data[400] == 200, (
        "a walkthrough with nothing to walk took the room's levels down anyway"
    )

    unknown = await client.post(f"/api/rigs/{rig_id}/identify/start", params={"only": "everything"})
    assert unknown.status_code == 400, unknown.text


# ---------------------------------------------------------------------------
# Row by row, ends first
# ---------------------------------------------------------------------------

async def test_a_row_is_walked_ends_first_then_fitted_between_the_two_taps(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, fast_row_check
):
    lights = row("Spot ", 1, [-4.0, -2.0, 0.0, 2.0, 4.0], -3.0, "US Truss Spots")
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    dmx_state.get_universe(0).set_channel(401, 200)

    state, base = await start(client, rig_id)
    assert state["rows_total"] == 1 and state["row"]["stage"] == "ends"
    assert state["row"]["can_fit"] is True
    assert state["current"]["fixture_id"] == ids["Spot 1"]

    state = await tap(client, base, state, -5.0, -2.0)
    assert state["current"]["fixture_id"] == ids["Spot 5"], "the row's far end comes second"

    state = await tap(client, base, state, 3.0, -4.0)
    assert state["row"]["stage"] == "fit_offer" and state["current"] is None
    await asyncio.sleep(0.02)
    assert lit_fixtures(dmx_state, lights) == [], "nothing is lit while the row question is open"

    # A tap that arrives late must not be taken as an answer about the next light.
    stray = await client.post(f"{base}/position", json={"position_x": 0.0, "position_z": 0.0})
    assert stray.status_code == 409, stray.text

    fitted = await client.post(f"{base}/fit-row")
    assert fitted.status_code == 200, fitted.text
    state = fitted.json()
    assert state["row"]["stage"] == "check" and state["row"]["fitted"] is True
    assert state["still_unconfirmed"] == 3, "a fit is arithmetic; it confirms nothing"

    rows = await fixtures_by_name(client, rig_id)
    xs = [rows[f"Spot {n}"]["position_x"] for n in range(1, 6)]
    zs = [rows[f"Spot {n}"]["position_z"] for n in range(1, 6)]
    assert xs == pytest.approx([-5.0, -3.0, -1.0, 1.0, 3.0])
    assert zs == pytest.approx([-2.0, -2.5, -3.0, -3.5, -4.0])
    assert {rows[f"Spot {n}"]["position_y"] for n in range(1, 6)} == {6.0}
    for n in (2, 3, 4):
        tags = rows[f"Spot {n}"]["tags"]
        assert "position_source:row_fit" in tags and TAG_UNCONFIRMED in tags
    for n in (1, 5):
        assert "position_source:tap" in rows[f"Spot {n}"]["tags"]

    passed = await client.post(f"{base}/row-check", json={"passed": True})
    assert passed.status_code == 200, passed.text
    state = passed.json()
    assert state["complete"] and state["still_unconfirmed"] == 0
    assert (state["placed"], state["fitted"]) == (2, 3)
    assert state["placed"] + state["fitted"] == state["total"]

    rows = await fixtures_by_name(client, rig_id)
    for n in (2, 3, 4):
        tags = rows[f"Spot {n}"]["tags"]
        assert TAG_UNCONFIRMED not in tags and "position_source:row_fit" in tags

    await asyncio.sleep(0.02)
    assert lit_fixtures(dmx_state, lights) == []
    assert dmx_state.get_universe(0).data[400] == 200, "finishing must hand the room back"


async def test_the_row_check_is_one_steady_light_at_a_time_from_plan_left_to_plan_right(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, fast_row_check
):
    lights = row("Wash ", 1, [-3.0, -1.0, 1.0, 3.0], 2.0, "DS Truss Wash")
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)

    # Tapped right to left: the addresses run the other way to the drawing.
    state = await tap(client, base, state, 3.0, 2.0)
    state = await tap(client, base, state, -3.0, 2.0)
    fitted = (await client.post(f"{base}/fit-row")).json()
    assert fitted["row"]["direction"] == "left_to_right" and fitted["row"]["running"] is True

    seen = []
    for _ in range(40):
        lit = lit_fixtures(dmx_state, lights)
        assert len(lit) <= 1, f"the row check lit {lit} together; it is one light at a time"
        if lit and (not seen or seen[-1] != lit[0]):
            seen.append(lit[0])
        await asyncio.sleep(fast_row_check / 4)

    assert seen == ["Wash 4", "Wash 3", "Wash 2", "Wash 1"], (
        "the light walks from the plan's left to its right, which after these taps "
        "is the row's last address first"
    )
    assert lit_fixtures(dmx_state, lights) == [], "the walk ends dark; it does not loop"

    again = await client.post(f"{base}/flash")
    assert again.status_code == 200 and again.json()["row"]["running"] is True
    await client.post(f"{base}/end")
    await asyncio.sleep(0.02)
    assert lit_fixtures(dmx_state, lights) == []


async def test_a_failed_row_check_drops_back_to_tapping_each_light(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, fast_row_check
):
    lights = row("Beam ", 1, [-2.0, 0.0, 2.0, 4.0], 0.0, "MS Truss Beams")
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)
    state = await tap(client, base, state, -2.0, 0.0)
    state = await tap(client, base, state, 4.0, 0.0)
    await client.post(f"{base}/fit-row")

    failed = await client.post(f"{base}/row-check", json={"passed": False})
    assert failed.status_code == 200, failed.text
    state = failed.json()
    assert state["row"]["stage"] == "each" and state["still_unconfirmed"] == 2
    assert state["current"]["fixture_id"] == ids["Beam 2"]

    rows = await fixtures_by_name(client, rig_id)
    assert TAG_UNCONFIRMED in rows["Beam 2"]["tags"] and TAG_UNCONFIRMED in rows["Beam 3"]["tags"]

    state = await tap(client, base, state, 0.5, 0.0)
    state = await tap(client, base, state, 1.5, 0.0)
    assert state["complete"] and state["placed"] == 4 and state["still_unconfirmed"] == 0

    answered_twice = await client.post(f"{base}/row-check", json={"passed": True})
    assert answered_twice.status_code == 409, answered_twice.text


async def test_declining_the_fit_taps_the_rest_and_moves_nothing(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = row("Par ", 1, [-2.0, 0.0, 2.0], 3.0, "DS Floor Pars")
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)
    state = await tap(client, base, state, -3.0, 3.0)
    state = await tap(client, base, state, 3.0, 3.0)

    declined = await client.post(f"{base}/fit-row", json={"accept": False})
    assert declined.status_code == 200, declined.text
    state = declined.json()
    assert state["row"]["stage"] == "each" and state["current"]["fixture_id"] == ids["Par 2"]

    rows = await fixtures_by_name(client, rig_id)
    assert rows["Par 2"]["position_x"] == 0.0 and "position_source:template" in rows["Par 2"]["tags"]


async def test_an_end_that_was_not_found_means_no_fit_is_offered(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = row("Bar ", 1, [-2.0, 0.0, 2.0], -4.0, "US Floor Bars")
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)
    state = await tap(client, base, state, -2.0, -4.0)
    state = (await client.post(f"{base}/skip", json={"fixture_id": ids["Bar 3"]})).json()

    assert state["row"]["stage"] == "each" and state["row"]["can_fit"] is False
    assert state["current"]["fixture_id"] == ids["Bar 2"]
    refused = await client.post(f"{base}/fit-row")
    assert refused.status_code == 409, refused.text


async def test_a_ring_is_never_fitted_to_a_straight_line(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    ring = [(-3.0, 0.0), (0.0, -3.0), (3.0, 0.0), (0.0, 3.0)]
    lights = [
        light(f"Ring {n}", 1 + (n - 1) * FOOTPRINT, x, z, group="Ring Spots")
        for n, (x, z) in enumerate(ring, start=1)
    ]
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)

    assert state["row"]["can_fit"] is False and "straight line" in state["row"]["fit_blocked_reason"]
    state = await tap(client, base, state, -3.0, 0.0)
    state = await tap(client, base, state, 0.0, 3.0)
    assert state["row"]["stage"] == "each" and state["current"]["fixture_id"] == ids["Ring 2"]


async def test_one_group_name_over_a_gap_in_the_addresses_is_two_rows(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """A sheet that names its own group can spread it over two trusses. Fitting
    one line through both would drag the second truss onto the first."""
    lights = (
        row("Front ", 1, [-2.0, 0.0, 2.0], 3.0, "Spots")
        + row("Back ", 201, [-2.0, 0.0, 2.0], -3.0, "Spots")
    )
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)

    assert state["rows_total"] == 2 and state["row"]["number"] == 1
    assert [f["fixture_id"] for f in state["row"]["fixtures"]] == [ids[f"Front {n}"] for n in (1, 2, 3)]

    state = await tap(client, base, state, -2.0, 3.0)
    state = await tap(client, base, state, 2.0, 3.0)
    state = (await client.post(f"{base}/fit-row", json={"accept": False})).json()
    state = await tap(client, base, state, 0.0, 3.0)
    assert state["row"]["number"] == 2 and state["current"]["fixture_id"] == ids["Back 1"]


# ---------------------------------------------------------------------------
# Height and mirrored sheets
# ---------------------------------------------------------------------------

async def test_a_rows_trim_height_is_set_once_for_the_whole_row(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = row("Spot ", 1, [-2.0, 0.0, 2.0], -3.0, "US Truss") + row("Par ", 201, [-1.0, 1.0], 3.0, "Floor", y=0.3)
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)
    assert state["row"]["height"] == 6.0

    changed = await client.post(f"{base}/row-height", json={"height": 7.25})
    assert changed.status_code == 200, changed.text
    assert changed.json()["row"]["height"] == 7.25
    assert changed.json()["still_unconfirmed"] == 5, "a height is not a location"

    rows = await fixtures_by_name(client, rig_id)
    assert {rows[f"Spot {n}"]["position_y"] for n in (1, 2, 3)} == {7.25}
    assert {rows[f"Par {n}"]["position_y"] for n in (1, 2)} == {0.3}, "another row's trim was changed"

    too_high = await client.post(f"{base}/row-height", json={"height": 5000})
    assert too_high.status_code == 422, too_high.text
    await client.post(f"{base}/end")


async def test_taps_that_run_right_to_left_offer_to_mirror_what_is_left(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, fast_row_check
):
    lights = (
        row("Spot ", 1, [-4.0, -2.0, 0.0, 2.0, 4.0], -3.0, "US Truss Spots")
        + row("Tower ", 201, [-5.0, -4.5, -4.0], 2.0, "SL Tower Wash")
        + [light("Off", 401, -2.0, 4.0, active=False, tags=GUESS + ["unmatched_type"])]
        + [light("Measured", 441, -1.0, 1.0, tags=MEASURED)]
    )
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)

    state = await tap(client, base, state, 4.0, -3.0)
    assert state["mirror_offer"] is None, "one tap says nothing about which way the row runs"
    state = await tap(client, base, state, -4.0, -3.0)
    assert state["mirror_offer"] == {"fixtures": 3}

    mirrored = await client.post(f"{base}/mirror")
    assert mirrored.status_code == 200, mirrored.text
    state = mirrored.json()
    assert state["mirrored"] is True and state["mirror_offer"] is None

    rows = await fixtures_by_name(client, rig_id)
    assert [rows[f"Tower {n}"]["position_x"] for n in (1, 2, 3)] == [5.0, 4.5, 4.0]
    assert rows["Off"]["position_x"] == 2.0, "the switched-off lights sit on the same mirrored guess"
    assert rows["Measured"]["position_x"] == -1.0, "a measured position is not a guess to flip"
    assert rows["Spot 1"]["position_x"] == 4.0 and rows["Spot 5"]["position_x"] == -4.0
    assert rows["Spot 3"]["position_x"] == 0.0 and TAG_UNCONFIRMED in rows["Tower 1"]["tags"]

    again = await client.post(f"{base}/mirror")
    assert again.status_code == 409, "the offer is made once"
    await client.post(f"{base}/end")


async def test_taps_that_agree_with_the_drawing_offer_no_mirror(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = row("Spot ", 1, [-4.0, 0.0, 4.0], -3.0, "A") + row("Wash ", 201, [-4.0, 4.0], 2.0, "B")
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    state, base = await start(client, rig_id)
    state = await tap(client, base, state, -4.5, -3.0)
    state = await tap(client, base, state, 4.5, -3.0)

    assert state["mirror_offer"] is None
    refused = await client.post(f"{base}/mirror")
    assert refused.status_code == 409, refused.text
    await client.post(f"{base}/end")


# ---------------------------------------------------------------------------
# Every way out leaves the rig dark and the room as it was
# ---------------------------------------------------------------------------

async def _into_a_running_row_check(client, sample_rig_data, sample_fixture_data, dmx_state):
    lights = row("Spot ", 1, [-4.0, -2.0, 0.0, 2.0, 4.0], -3.0, "US Truss Spots")
    rig_id, ids = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    dmx_state.get_universe(0).set_channel(401, 200)

    state, base = await start(client, rig_id)
    state = await tap(client, base, state, -4.0, -3.0)
    state = await tap(client, base, state, 4.0, -3.0)
    state = (await client.post(f"{base}/fit-row")).json()
    await asyncio.sleep(0.02)
    assert state["row"]["running"] and len(lit_fixtures(dmx_state, lights)) == 1
    assert dmx_state.get_universe(0).data[400] == 0
    return rig_id, ids, lights, base


def _assert_dark_and_restored(dmx_state, lights):
    assert lit_fixtures(dmx_state, lights) == [], "a light was left on"
    assert dmx_state.get_universe(0).data[400] == 200, "the room's own levels were not put back"


async def test_ending_in_the_middle_of_a_row_check_leaves_the_rig_dark(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    _, _, lights, base = await _into_a_running_row_check(
        client, sample_rig_data, sample_fixture_data, dmx_state
    )

    ended = await client.post(f"{base}/end")
    assert ended.status_code == 200, ended.text
    await asyncio.sleep(0.05)

    _assert_dark_and_restored(dmx_state, lights)


async def test_a_browser_that_goes_quiet_in_the_middle_of_a_row_check_is_released(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state, monkeypatch
):
    from app.api.endpoints import rig_identify as identify_module

    monkeypatch.setattr(identify_module, "SESSION_IDLE_TIMEOUT_S", 0.1)
    monkeypatch.setattr(identify_module, "WATCHDOG_TICK_S", 0.02)

    _, _, lights, base = await _into_a_running_row_check(
        client, sample_rig_data, sample_fixture_data, dmx_state
    )
    await asyncio.sleep(0.4)

    assert not identify_module._sessions, "the watchdog never reaped the silent session"
    _assert_dark_and_restored(dmx_state, lights)
    gone = await client.post(f"{base}/row-check", json={"passed": True})
    assert gone.status_code == 404, gone.text


async def test_stopping_one_fixtures_test_in_the_middle_of_a_row_check_blacks_the_row_out(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    """/test/stop knows nothing about a walkthrough: it only cancels the task
    registered for that fixture. The row check has to black itself out."""
    rig_id, ids, lights, base = await _into_a_running_row_check(
        client, sample_rig_data, sample_fixture_data, dmx_state
    )

    stopped = await client.post(f"/api/rigs/{rig_id}/fixtures/{ids['Spot 3']}/test/stop")
    assert stopped.status_code == 200, stopped.text
    await asyncio.sleep(0.05)

    assert lit_fixtures(dmx_state, lights) == []
    await client.post(f"{base}/end")
    _assert_dark_and_restored(dmx_state, lights)


async def test_finishing_a_locate_walk_leaves_the_rig_dark(
    client: AsyncClient, sample_rig_data, sample_fixture_data, dmx_state
):
    lights = row("Par ", 1, [-1.0, 1.0], 3.0, "Floor Pars")
    rig_id, _ = await build_rig(client, sample_rig_data, sample_fixture_data, lights)
    dmx_state.get_universe(0).set_channel(401, 200)
    state, base = await start(client, rig_id)
    await asyncio.sleep(0.02)
    assert lit_fixtures(dmx_state, lights) == ["Par 1"]

    state = await tap(client, base, state, -1.0, 3.0)
    state = (await client.post(f"{base}/confirm")).json()
    assert state["complete"] and state["row"] is None
    await asyncio.sleep(0.02)

    _assert_dark_and_restored(dmx_state, lights)
