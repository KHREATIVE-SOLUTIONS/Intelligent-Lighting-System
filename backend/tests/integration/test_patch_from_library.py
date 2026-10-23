"""
Patch by make and model
=======================

The load-in flow end to end, with no internet: search the catalog, patch eight
movers in one call, and check the rig the show would run carries them at
non-overlapping addresses in the mode a programmer would choose - and that the
running show picks them up when this is the active rig.
"""

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.fixture_library.ofl_client import OFLUnavailableError

MOVER_KEY = "chauvet-dj/intimidator-spot-260"


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    """Load-in happens offline: any online OFL call is a failure of this design."""
    from app.api.endpoints import fixture_library

    class Offline:
        async def get_fixture(self, *a, **k):
            raise OFLUnavailableError("no internet at the venue")

        async def search_fixtures(self, *a, **k):
            raise OFLUnavailableError("no internet at the venue")

    monkeypatch.setattr(fixture_library, "get_ofl_client", lambda: Offline())


async def _rig(client: AsyncClient, sample_rig_data, name: str) -> int:
    response = await client.post("/api/rigs/", json={**sample_rig_data, "name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_catalog_search_works_offline(client: AsyncClient):
    response = await client.get("/api/fixtures/library/catalog", params={"q": "intimidator 260"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["offline_library"]["available"] is True
    hit = next(r for r in body["results"] if r["key"] == MOVER_KEY)
    assert hit["recommended_mode"] == "14-channel"
    assert any(m["recommended"] and "fine pan" in m["features"] for m in hit["modes"])


@pytest.mark.asyncio
async def test_catalog_preview_lists_channels(client: AsyncClient):
    response = await client.get(f"/api/fixtures/library/catalog/{MOVER_KEY}")
    assert response.status_code == 200, response.text
    mode = next(m for m in response.json()["modes"] if m["name"] == "14-channel")
    assert len(mode["channels"]) == 14
    assert mode["channels"][0]["channel_type"] == "pan"


@pytest.mark.asyncio
async def test_legacy_search_answers_from_the_offline_library(client: AsyncClient):
    response = await client.get("/api/fixtures/library/search", params={"query": "sharpy"})
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "ofl-offline"
    assert any(r["key"] == "clay-paky/sharpy" for r in response.json()["results"])


@pytest.mark.asyncio
async def test_patch_eight_movers_in_one_call(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Club load-in")
    response = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "quantity": 8, "apply_live": False},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"]["name"] == "14-channel"
    assert body["mode"]["chosen_by"] == "recommended"
    assert body["group_name"] == "Intimidator Spot 260"
    assert body["mounting_position"] == "mid_truss"
    assert [p["dmx_address"] for p in body["patched"]] == [1 + 14 * i for i in range(8)]
    assert len({(p["position"]["x"], p["position"]["z"]) for p in body["patched"]}) == 8

    # A second run lands after the first and reuses the imported profile.
    again = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "quantity": 2, "apply_live": False},
    )
    assert again.status_code == 201, again.text
    assert again.json()["fixture"]["id"] == body["fixture"]["id"]
    assert again.json()["fixture"]["imported"] is False
    assert [p["dmx_address"] for p in again.json()["patched"]] == [113, 127]
    assert [p["name"] for p in again.json()["patched"]] == [
        "Intimidator Spot 260 9", "Intimidator Spot 260 10",
    ]

    conflicts = await client.get(f"/api/rigs/{rig_id}/patch-conflicts")
    assert conflicts.json()["conflict_count"] == 0


@pytest.mark.asyncio
async def test_patched_fixtures_reach_the_engine_rig(client: AsyncClient, sample_rig_data, db_session):
    from app.services.rig.rig_loader import build_manager_for_rig_id, get_rig_diagnostics

    rig_id = await _rig(client, sample_rig_data, "Engine check")
    response = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "quantity": 2, "universe": 1, "apply_live": False},
    )
    assert response.status_code == 201, response.text

    manager = await build_manager_for_rig_id(db_session, rig_id)
    fixtures = sorted(manager.fixtures.values(), key=lambda f: f.dmx_address)
    assert [(f.universe, f.dmx_address) for f in fixtures] == [(1, 1), (1, 15)]
    assert {"pan", "pan_fine", "tilt", "tilt_fine", "dimmer"} <= set(fixtures[0].channels)
    assert not get_rig_diagnostics(manager).modes_guessed
    assert set(manager.groups["Intimidator Spot 260"].fixture_ids) == {f.id for f in fixtures}


@pytest.mark.asyncio
async def test_an_active_rig_goes_straight_to_the_running_show(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Live rig")
    assert (await client.post(f"/api/rigs/{rig_id}/activate")).status_code == 200

    installed = []

    class Engine:
        def set_fixture_manager(self, manager):
            installed.append(manager)

    previous = getattr(app.state, "effects_engine", None)
    app.state.effects_engine = Engine()
    try:
        response = await client.post(
            f"/api/rigs/{rig_id}/patch-from-library",
            json={"library_key": "american-dj/mega-hex-par", "quantity": 4},
        )
    finally:
        app.state.effects_engine = previous
    assert response.status_code == 201, response.text
    assert response.json()["applied_live"] is True
    assert response.json()["mode"]["name"] == "8-channel"
    assert len(installed) == 1 and len(installed[0].fixtures) == 4


@pytest.mark.asyncio
async def test_a_clash_at_a_chosen_address_is_refused(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Clash")
    first = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "start_address": 1, "apply_live": False},
    )
    assert first.status_code == 201, first.text
    clash = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "start_address": 10, "apply_live": False},
    )
    assert clash.status_code == 409
    assert "overlaps" in clash.json()["detail"]


@pytest.mark.asyncio
async def test_a_named_mode_and_library_profile_can_be_chosen(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Named mode")
    first = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "mode_name": "8-channel", "apply_live": False},
    )
    assert first.status_code == 201, first.text
    assert first.json()["mode"]["channel_count"] == 8
    fixture_id = first.json()["fixture"]["id"]

    by_id = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"fixture_id": fixture_id, "mode_name": "nonsense", "apply_live": False},
    )
    assert by_id.status_code == 400
    assert "14-channel" in by_id.json()["detail"]


@pytest.mark.asyncio
async def test_an_unknown_fixture_offline_is_a_clear_error(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Unknown")
    response = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": "nobody/no-such-light", "apply_live": False},
    )
    # Not in the snapshot, and the online library is unreachable.
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_single_add_checks_the_whole_footprint(client: AsyncClient, sample_rig_data):
    rig_id = await _rig(client, sample_rig_data, "Footprint")
    first = await client.post(
        f"/api/rigs/{rig_id}/patch-from-library",
        json={"library_key": MOVER_KEY, "start_address": 1, "apply_live": False},
    )
    profile = first.json()["fixture"]["id"]
    mode = first.json()["mode"]["id"]
    overlap = await client.post(
        f"/api/rigs/{rig_id}/fixtures",
        json={"fixture_id": profile, "mode_id": mode, "universe": 0, "dmx_address": 10},
    )
    assert overlap.status_code == 400
    assert "overlap" in overlap.json()["detail"]
    clear = await client.post(
        f"/api/rigs/{rig_id}/fixtures",
        json={"fixture_id": profile, "mode_id": mode, "universe": 0, "dmx_address": 15},
    )
    assert clear.status_code == 201, clear.text
