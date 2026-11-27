"""
Dragging a fixture into place, and undoing a room scan's moves
==============================================================

PUT /api/rigs/{id}/fixtures/{fid}/position is what a drag in the 3D view saves
through: the position is stored and stops being a guess.

POST /api/rigs/{id}/room-scan/undo puts back the fixtures a scan moved, and
DELETE /api/rigs/{id}/room-shell?restore_fixtures=true does the same while
taking the room off. Neither overwrites a position a person has set since.

docs/ROOM_SCAN.md. Nothing here drives a fixture: stored positions only.
"""

import pytest
from httpx import AsyncClient

from app.services.venue_import.apply import is_unconfirmed, position_source
from tests.integration.test_api_room_scan import (
    GUESS, build_rig, fixtures_by_name, light, place, scan_file, upload,
)

MOVED = ("Spot 1", "Spot 2", "Spot 3", "Spot 4", "Par 1", "Par 2", "Par 3")


async def apply_scan(client: AsyncClient, rig_id: int, **params) -> dict:
    response = await client.post(
        f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def drag(client: AsyncClient, rig_id: int, fixture_id: int, **position):
    return await client.put(f"/api/rigs/{rig_id}/fixtures/{fixture_id}/position", json=position)


class TestDraggedPosition:

    @pytest.mark.asyncio
    async def test_a_drag_stores_the_position_and_confirms_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        spot = (await fixtures_by_name(client, rig_id))["Spot 1"]
        assert is_unconfirmed(spot["tags"])

        response = await drag(client, rig_id, spot["id"], position_x=-2.25, position_z=1.5)

        assert response.status_code == 200, response.text
        saved = response.json()
        # Along the plan: the height is kept when none is sent.
        assert place(saved) == (-2.25, 6.0, 1.5)
        assert not is_unconfirmed(saved["tags"])
        assert position_source(saved["tags"]) == "tap"
        # The 3D view redraws the fixture from this answer, so its profile is in it.
        assert saved["fixture"]["model"] == sample_fixture_data["model"]
        # And it is what the rig then reads back.
        stored = (await fixtures_by_name(client, rig_id))["Spot 1"]
        assert place(stored) == (-2.25, 6.0, 1.5) and stored["tags"] == saved["tags"]

    @pytest.mark.asyncio
    async def test_a_drag_can_set_the_height_and_keeps_other_tags(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        lights = [light("Spot", 1, 0.0, 6.0, 0.0, "Truss", tags=[*GUESS, "group:Back", "unplaced"])]
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=lights)
        spot = (await fixtures_by_name(client, rig_id))["Spot"]

        response = await drag(client, rig_id, spot["id"], position_x=1.0, position_y=4.5, position_z=-1.0)

        assert response.status_code == 200, response.text
        assert place(response.json()) == (1.0, 4.5, -1.0)
        tags = response.json()["tags"]
        assert "group:Back" in tags and "unplaced" not in tags and "position_unconfirmed" not in tags

    @pytest.mark.asyncio
    async def test_a_drag_is_held_inside_the_room(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        """The stage is 12 by 10 by 8: two metres past it is as far as a fixture goes."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        spot = (await fixtures_by_name(client, rig_id))["Spot 1"]

        far = await drag(client, rig_id, spot["id"], position_x=500.0, position_y=-3.0, position_z=-500.0)
        assert far.status_code == 200, far.text
        assert place(far.json()) == (8.0, 0.0, -7.0)

        high = await drag(client, rig_id, spot["id"], position_x=0.0, position_y=99.0, position_z=0.0)
        assert high.json()["position_y"] == 10.0

    @pytest.mark.asyncio
    async def test_a_scanned_room_wider_than_the_stage_widens_the_limit(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, {**sample_rig_data, "stage_width": 4.0}, sample_fixture_data)
        shell = (await apply_scan(client, rig_id, move_fixtures=False))["room_shell"]
        assert shell["room"]["width"] > 4.0
        spot = (await fixtures_by_name(client, rig_id))["Tapped"]

        response = await drag(client, rig_id, spot["id"], position_x=500.0, position_z=0.0)

        assert response.json()["position_x"] == pytest.approx(shell["room"]["width"] / 2 + 2.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_refusals(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        other_rig = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        spot = (await fixtures_by_name(client, rig_id))["Spot 1"]

        assert (await drag(client, 999999, spot["id"], position_x=0, position_z=0)).status_code == 404
        assert (await drag(client, rig_id, 999999, position_x=0, position_z=0)).status_code == 404
        # A fixture is only moved through its own rig.
        assert (await drag(client, other_rig, spot["id"], position_x=0, position_z=0)).status_code == 404
        assert (await drag(client, rig_id, spot["id"], position_x=0)).status_code == 422
        assert (await drag(client, rig_id, spot["id"], position_x="left", position_z=0)).status_code == 422
        # Nothing above moved it or confirmed it.
        after = (await fixtures_by_name(client, rig_id))["Spot 1"]
        assert place(after) == place(spot) and after["tags"] == spot["tags"]

    @pytest.mark.asyncio
    async def test_a_drag_is_refused_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        spot = (await fixtures_by_name(client, rig_id))["Spot 1"]
        rig_identify._sessions["drag-test"] = rig_identify._Session(
            session_id="drag-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            refused = await drag(client, rig_id, spot["id"], position_x=1.0, position_z=1.0)
            assert refused.status_code == 409
            assert "locate walkthrough" in refused.json()["detail"]
        finally:
            rig_identify._sessions.pop("drag-test", None)
        assert (await fixtures_by_name(client, rig_id))["Spot 1"] == spot
        assert (await drag(client, rig_id, spot["id"], position_x=1.0, position_z=1.0)).status_code == 200

    @pytest.mark.asyncio
    async def test_a_scan_does_not_move_a_dragged_fixture(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        spot = (await fixtures_by_name(client, rig_id))["Spot 1"]
        await drag(client, rig_id, spot["id"], position_x=-4.0, position_z=3.0)

        applied = await apply_scan(client, rig_id)

        assert applied["applied"]["fixtures_moved"] == 6
        assert place((await fixtures_by_name(client, rig_id))["Spot 1"]) == (-4.0, 6.0, 3.0)

    @pytest.mark.asyncio
    async def test_the_route_is_behind_the_login(self, unauthenticated_client: AsyncClient):
        response = await unauthenticated_client.put(
            "/api/rigs/1/fixtures/1/position", json={"position_x": 0, "position_z": 0},
        )
        assert response.status_code in (401, 403)


class TestRoomScanUndo:

    @pytest.mark.asyncio
    async def test_apply_records_what_it_moved_and_undo_puts_it_back(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_scan_undo"] is None

        applied = await apply_scan(client, rig_id)
        assert applied["applied"]["undo_available"] == 7

        # The rig says an undo is there, with where each fixture stood.
        record = (await client.get(f"/api/rigs/{rig_id}")).json()["room_scan_undo"]
        assert record["file"] == "club.obj"
        assert {entry["name"] for entry in record["moves"]} == set(MOVED)
        entry = next(e for e in record["moves"] if e["name"] == "Spot 1")
        assert entry["from"] == {"x": -3.0, "y": 6.0, "z": -1.5}

        # Asking what it would do writes nothing.
        moved = await fixtures_by_name(client, rig_id)
        would = (await client.get(f"/api/rigs/{rig_id}/room-scan/undo")).json()
        assert (would["available"], would["would_restore"], would["would_skip"]) == (7, 7, 0)
        assert await fixtures_by_name(client, rig_id) == moved

        undone = await client.post(f"/api/rigs/{rig_id}/room-scan/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert (answer["restored"], answer["skipped"]) == (7, 0)
        assert "7 fixtures put back" in answer["message"]
        # Every fixture is exactly as it was before the scan, tags and all.
        assert await fixtures_by_name(client, rig_id) == before
        # The room itself stays, and the undo is spent.
        rig = (await client.get(f"/api/rigs/{rig_id}")).json()
        assert rig["room_shell"] is not None and rig["room_scan_undo"] is None
        again = (await client.post(f"/api/rigs/{rig_id}/room-scan/undo")).json()
        assert (again["restored"], again["skipped"]) == (0, 0)
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_undo_leaves_what_a_person_placed_since(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        await apply_scan(client, rig_id)
        moved = await fixtures_by_name(client, rig_id)

        # Dragged in the 3D view.
        dragged = (await drag(client, rig_id, moved["Spot 1"]["id"], position_x=-3.4, position_z=0.6)).json()
        # Confirmed where the scan put it (what Identify Lights' confirm writes).
        confirmed_tags = ["position_source:confirmed", "position_hint:room_scan"]
        await client.put(f"/api/rigs/{rig_id}/fixtures/{moved['Spot 2']['id']}", json={"tags": confirmed_tags})
        # Moved in the layout view, which leaves the tags as they are.
        await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={"fixtures": [
            {"id": moved["Par 1"]["id"], "position_x": 1.75},
        ]})
        # Taken out of the rig.
        await client.delete(f"/api/rigs/{rig_id}/fixtures/{moved['Par 3']['id']}")

        answer = (await client.post(f"/api/rigs/{rig_id}/room-scan/undo")).json()

        assert answer["restored"] == 3 and answer["skipped"] == 4
        assert {item["name"] for item in answer["restored_fixtures"]} == {"Spot 3", "Spot 4", "Par 2"}
        reasons = {item["name"]: item["reason"] for item in answer["skipped_fixtures"]}
        assert set(reasons) == {"Spot 1", "Spot 2", "Par 1", "Par 3"}
        assert "tapped or dragged" in reasons["Spot 1"]
        assert "confirmed" in reasons["Spot 2"]
        assert "moved since the scan" in reasons["Par 1"]
        assert "no longer in the rig" in reasons["Par 3"]
        assert "3 fixtures put back" in answer["message"] and "4 fixtures left alone" in answer["message"]

        after = await fixtures_by_name(client, rig_id)
        for name in ("Spot 3", "Spot 4", "Par 2"):
            assert after[name] == before[name]
        # What a person set since is exactly as they left it.
        assert place(after["Spot 1"]) == place(dragged) and after["Spot 1"]["tags"] == dragged["tags"]
        assert place(after["Spot 2"]) == place(moved["Spot 2"]) and after["Spot 2"]["tags"] == confirmed_tags
        assert after["Par 1"]["position_x"] == 1.75 and after["Par 1"]["tags"] == moved["Par 1"]["tags"]
        assert "Par 3" not in after

    @pytest.mark.asyncio
    async def test_a_second_scan_does_not_forget_the_first(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The same scan again moves nothing, and the undo still goes back to before the first."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        await apply_scan(client, rig_id)

        again = await apply_scan(client, rig_id)
        assert again["applied"]["fixtures_moved"] == 0
        assert again["applied"]["undo_available"] == 7

        assert (await client.post(f"/api/rigs/{rig_id}/room-scan/undo")).json()["restored"] == 7
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_storing_only_the_room_leaves_nothing_to_undo(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        applied = await apply_scan(client, rig_id, move_fixtures=False)
        assert applied["applied"]["undo_available"] == 0
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_scan_undo"] is None

    @pytest.mark.asyncio
    async def test_removing_the_room_can_put_the_fixtures_back(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        await apply_scan(client, rig_id)
        moved = await fixtures_by_name(client, rig_id)
        await drag(client, rig_id, moved["Spot 1"]["id"], position_x=-3.4, position_z=0.6)

        removed = await client.delete(f"/api/rigs/{rig_id}/room-shell", params={"restore_fixtures": True})

        assert removed.status_code == 200, removed.text
        answer = removed.json()
        assert answer["removed"] is True
        assert (answer["fixtures_restored"], answer["fixtures_skipped"]) == (6, 1)
        assert answer["skipped_fixtures"][0]["name"] == "Spot 1"
        assert answer["undo_available"] == 0
        rig = (await client.get(f"/api/rigs/{rig_id}")).json()
        assert rig["room_shell"] is None and rig["room_scan_undo"] is None
        after = await fixtures_by_name(client, rig_id)
        assert after["Spot 2"] == before["Spot 2"] and after["Par 3"] == before["Par 3"]
        assert place(after["Spot 1"]) == (-3.4, moved["Spot 1"]["position_y"], 0.6)

    @pytest.mark.asyncio
    async def test_removing_the_room_alone_keeps_the_undo_for_later(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        await apply_scan(client, rig_id)
        moved = await fixtures_by_name(client, rig_id)

        removed = (await client.delete(f"/api/rigs/{rig_id}/room-shell")).json()

        assert removed == {"rig_id": rig_id, "removed": True, "undo_available": 7}
        assert await fixtures_by_name(client, rig_id) == moved
        assert (await client.post(f"/api/rigs/{rig_id}/room-scan/undo")).json()["restored"] == 7
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_rig_update_cannot_write_the_undo_record(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        await apply_scan(client, rig_id)

        edited = await client.put(f"/api/rigs/{rig_id}", json={"name": "Renamed", "room_scan_undo": None})

        assert edited.status_code == 200, edited.text
        assert len(edited.json()["room_scan_undo"]["moves"]) == 7

    @pytest.mark.asyncio
    async def test_undo_is_refused_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        await apply_scan(client, rig_id)
        moved = await fixtures_by_name(client, rig_id)
        rig_identify._sessions["undo-test"] = rig_identify._Session(
            session_id="undo-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            refused = await client.post(f"/api/rigs/{rig_id}/room-scan/undo")
            assert refused.status_code == 409
            assert "locate walkthrough" in refused.json()["detail"]
            also = await client.delete(f"/api/rigs/{rig_id}/room-shell", params={"restore_fixtures": True})
            assert also.status_code == 409
        finally:
            rig_identify._sessions.pop("undo-test", None)
        # Nothing moved, the room is still there, and the undo is still there.
        assert await fixtures_by_name(client, rig_id) == moved
        rig = (await client.get(f"/api/rigs/{rig_id}")).json()
        assert rig["room_shell"] is not None and len(rig["room_scan_undo"]["moves"]) == 7

    @pytest.mark.asyncio
    async def test_missing_rig_and_login(self, client: AsyncClient, unauthenticated_client: AsyncClient):
        assert (await client.post("/api/rigs/999999/room-scan/undo")).status_code == 404
        assert (await client.get("/api/rigs/999999/room-scan/undo")).status_code == 404
