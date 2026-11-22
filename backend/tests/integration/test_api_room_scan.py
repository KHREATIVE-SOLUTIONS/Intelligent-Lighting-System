"""
Room scan over HTTP
===================

POST /api/rigs/{id}/room-scan previews a scan against a rig and, with
apply=true, stores the suggested room on it and moves its unconfirmed
fixtures. docs/ROOM_SCAN.md.

What has to hold: a preview writes nothing; an applied shell comes back on the
rig the 3D view loads; only template guesses move, a row at a time, and they
are still guesses afterwards; a position a person tapped or confirmed never
moves; and a file that cannot be read says what to export instead.

The scans are made in the test (tests/unit/room_scan_meshes.py). Nothing here
drives a fixture: the endpoint changes stored positions and scenery only.
"""

import pytest
from httpx import AsyncClient

from app.services.venue_import.apply import is_unconfirmed, position_source
from tests.unit.room_scan_meshes import (
    ROOM, STAGE, TRUSS, as_scanned, box, merge, room_mesh, roomplan_json, write_obj, write_ply, write_zip,
)

GUESS = ["position_source:template", "position_unconfirmed"]
FOOTPRINT = 16


def upload(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


def scan_file(yaw=25.0, up="z", units_per_metre=100.0) -> bytes:
    """The synthetic room as a phone would hand it over: turned, Z-up, in centimetres."""
    vertices, faces = room_mesh()
    return write_obj(as_scanned(vertices, yaw, offset=(2.0, 0.5, -3.0), up=up, units_per_metre=units_per_metre), faces)


def light(name, address, x, y, z, group, tags=None):
    return {
        "name": name, "dmx_address": address, "position_x": x, "position_y": y, "position_z": z,
        "group_name": group, "tags": list(GUESS if tags is None else tags),
    }


# A truss row drawn on a template 6 m up and 2 m upstage of where the truss is,
# a floor row drawn where the stage turns out to be, a tapped light and a
# confirmed one in the same truss group, and a measured light.
LIGHTS = (
    [light(f"Spot {n}", 1 + (n - 1) * FOOTPRINT, -3.0 + 2.0 * (n - 1), 6.0, -1.5, "Truss Spots") for n in range(1, 5)]
    + [light(f"Par {n}", 101 + (n - 1) * FOOTPRINT, -3.0 + n, 0.2, -4.4, "Floor Pars") for n in range(1, 4)]
    + [
        light("Tapped", 201, 2.0, 6.0, -1.5, "Truss Spots", tags=["position_source:tap"]),
        light("Agreed", 217, 3.0, 6.0, -1.5, "Truss Spots", tags=["position_source:confirmed"]),
        light("Measured", 233, -5.0, 3.0, 4.0, "Side", tags=["position_source:mvr"]),
        light("Fitted", 249, 0.0, 6.0, 3.0, "Back Truss", tags=["position_source:row_fit", "position_unconfirmed"]),
    ]
)


async def build_rig(client: AsyncClient, sample_rig_data, sample_fixture_data, lights=LIGHTS):
    rig = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig.status_code == 201, rig.text
    rig_id = rig.json()["id"]
    profile = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert profile.status_code in (200, 201), profile.text
    profile = profile.json()
    for spec in lights:
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": profile["id"], "mode_id": profile["modes"][0]["id"], "universe": 0, **spec,
        })
        assert added.status_code == 201, added.text
    return rig_id


async def fixtures_by_name(client: AsyncClient, rig_id: int) -> dict:
    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text
    return {entry["name"]: entry for entry in listed.json()}


def place(entry: dict) -> tuple:
    return (entry["position_x"], entry["position_y"], entry["position_z"])


class TestRoomScanPreview:

    @pytest.mark.asyncio
    async def test_a_new_rig_has_no_room_shell(self, client: AsyncClient, sample_rig_data):
        rig = await client.post("/api/rigs/", json=sample_rig_data)
        assert rig.status_code == 201, rig.text
        assert rig.json()["room_shell"] is None

    @pytest.mark.asyncio
    async def test_preview_describes_the_room_and_writes_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)

        response = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["applied"] is None
        assert preview["format"] == "obj"
        assert preview["replaces_existing_shell"] is False

        summary = preview["summary"]
        assert summary["width"] == pytest.approx(ROOM["width"], abs=0.1)
        assert summary["depth"] == pytest.approx(ROOM["depth"], abs=0.1)
        assert summary["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert (summary["units"], summary["up_axis"]) == ("cm", "z")
        assert summary["raised_areas"] == 2 and summary["overhead_lines"] == 1
        assert summary["hanging_heights"] == pytest.approx([TRUSS["bottom"]], abs=0.1)

        shell = preview["room_shell"]
        assert shell["suggested"] is True and shell["source"] == "scan"
        assert all(item["suggested"] for item in shell["risers"] + shell["truss_lines"] + shell["hanging_bands"])
        assert preview["assumptions"] and isinstance(preview["warnings"], list)

        # Which fixtures it would move, from where to where: the seven guesses and nothing else.
        fixtures = preview["fixtures"]
        assert fixtures["total"] == len(LIGHTS)
        assert fixtures["unconfirmed"] == 8
        assert fixtures["would_move"] == 7
        moves = {move["name"]: move for move in fixtures["moves"]}
        assert set(moves) == {"Spot 1", "Spot 2", "Spot 3", "Spot 4", "Par 1", "Par 2", "Par 3"}
        assert moves["Spot 1"]["from"] == {"x": -3.0, "y": 6.0, "z": -1.5}
        assert moves["Spot 1"]["to"]["y"] == pytest.approx(TRUSS["bottom"], abs=0.1)
        assert moves["Spot 1"]["to"]["z"] == pytest.approx(TRUSS["z"], abs=0.1)
        assert "Overhead line 1" in moves["Spot 1"]["reason"]
        # A move is a suggestion too, and says so, like every part of the shell.
        assert all(move["suggested"] is True for move in fixtures["moves"])

        # Nothing was written: no shell on the rig, no fixture moved or retagged.
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_dj_booth_is_suggested_where_the_scan_shows_one(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """A small level area at desk height comes back as a booth, beside the stage and the riser."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        # 2.5 m by 1.2 m, a metre high, against the upstage wall beside the stage.
        booth = {"x_min": 3.0, "x_max": 5.5, "z_min": -4.5, "z_max": -3.3, "height": 1.0}
        vertices, faces = merge([
            room_mesh(),
            box(booth["x_min"], booth["x_max"], 0.0, booth["height"], booth["z_min"], booth["z_max"]),
        ])

        response = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", write_obj(vertices, faces)))

        assert response.status_code == 200, response.text
        risers = response.json()["room_shell"]["risers"]
        assert sorted(r["kind"] for r in risers) == ["booth", "riser", "stage"]
        found = next(r for r in risers if r["kind"] == "booth")
        assert found["suggested"] is True and "guessed" in found["basis"]
        assert found["height"] == pytest.approx(booth["height"], abs=0.06)
        assert found["center_x"] == pytest.approx((booth["x_min"] + booth["x_max"]) / 2, abs=0.15)
        assert found["center_z"] == pytest.approx((booth["z_min"] + booth["z_max"]) / 2, abs=0.15)
        assert found["width"] == pytest.approx(booth["x_max"] - booth["x_min"], abs=0.25)
        # The stage is still the largest raised area, so it still says which end is upstage.
        stage = next(r for r in risers if r["kind"] == "stage")
        assert stage["center_z"] < 0

    @pytest.mark.asyncio
    async def test_the_guesses_can_be_overridden(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"

        turned = await client.post(url, files=upload("club.obj", scan_file()), params={"rotate": 90})
        assert turned.status_code == 200, turned.text
        assert turned.json()["summary"]["width"] == pytest.approx(ROOM["depth"], abs=0.1)

        stated = await client.post(
            url, files=upload("club.obj", scan_file()), params={"units": "cm", "up_axis": "z"},
        )
        assert stated.status_code == 200, stated.text
        assert any("as asked" in line for line in stated.json()["assumptions"])

        # The scan is in centimetres; read as metres it is a room 500 m high.
        wrong = await client.post(url, files=upload("club.obj", scan_file()), params={"units": "m"})
        assert wrong.status_code == 200, wrong.text
        assert any("Check the units" in line for line in wrong.json()["warnings"])

    @pytest.mark.asyncio
    async def test_ply_and_roomplan_are_read_too(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"
        vertices, faces = room_mesh()

        ply = await client.post(url, files=upload("club.ply", write_ply(vertices, faces)))
        assert ply.status_code == 200, ply.text
        assert ply.json()["format"] == "ply"
        assert ply.json()["summary"]["overhead_lines"] == 1

        roomplan = await client.post(url, files=upload("Room.json", roomplan_json()))
        assert roomplan.status_code == 200, roomplan.text
        assert roomplan.json()["format"] == "roomplan"
        assert roomplan.json()["summary"]["width"] == pytest.approx(ROOM["width"], abs=0.1)


class TestRoomScanRefusals:

    @pytest.mark.asyncio
    async def test_a_binary_usdz_says_to_export_obj(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        archive = write_zip([("Room.usdc", b"PXR-USDC" + bytes(64))])

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("Room.usdz", archive), params={"apply": True},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "OBJ" in detail and "Polycam" in detail and "Scaniverse" in detail
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

    @pytest.mark.asyncio
    async def test_other_refusals(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"

        assert (await client.post(url, files=upload("notes.txt", b"not a scan"))).status_code == 400
        assert (await client.post(url, files=upload("club.obj", scan_file()), params={"rotate": 45})).status_code == 400
        assert (await client.post(url, files=upload("club.obj", scan_file()), params={"units": "ft"})).status_code == 422
        missing = await client.post("/api/rigs/999999/room-scan", files=upload("club.obj", scan_file()))
        assert missing.status_code == 404
        assert (await client.delete("/api/rigs/999999/room-shell")).status_code == 404

    @pytest.mark.asyncio
    async def test_a_file_over_the_size_limit_is_refused_before_it_is_read(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data, monkeypatch,
    ):
        from app.api.endpoints import room_scan

        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        content = scan_file()
        monkeypatch.setattr(room_scan, "MAX_UPLOAD_BYTES", len(content) - 1)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", content), params={"apply": True},
        )

        assert response.status_code == 413
        assert "larger than" in response.json()["detail"] and "lower detail" in response.json()["detail"]
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

        # One byte under the limit it is read.
        monkeypatch.setattr(room_scan, "MAX_UPLOAD_BYTES", len(content))
        assert (await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", content))).status_code == 200

    @pytest.mark.asyncio
    async def test_fixtures_are_not_moved_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """Flash-and-tap is writing positions of its own; a scan must not move lights under it."""
        from app.api.endpoints import rig_identify

        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        url = f"/api/rigs/{rig_id}/room-scan"
        rig_identify._sessions["scan-test"] = rig_identify._Session(
            session_id="scan-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            # A preview writes nothing, so it is still answered.
            assert (await client.post(url, files=upload("club.obj", scan_file()))).status_code == 200

            refused = await client.post(url, files=upload("club.obj", scan_file()), params={"apply": True})
            assert refused.status_code == 409
            assert "locate walkthrough" in refused.json()["detail"]
            assert await fixtures_by_name(client, rig_id) == before
            assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

            # The room alone moves no light, so it can be stored.
            room_only = await client.post(
                url, files=upload("club.obj", scan_file()), params={"apply": True, "move_fixtures": False},
            )
            assert room_only.status_code == 200, room_only.text
            assert await fixtures_by_name(client, rig_id) == before
        finally:
            rig_identify._sessions.pop("scan-test", None)

        # Once the walkthrough is over the same request goes through.
        after = await client.post(url, files=upload("club.obj", scan_file()), params={"apply": True})
        assert after.status_code == 200, after.text
        assert after.json()["applied"]["fixtures_moved"] == 7


class TestRoomScanApply:

    @pytest.mark.asyncio
    async def test_apply_stores_the_shell_on_the_rig(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["room_shell_stored"] is True
        assert applied["fixtures_moved"] == 7
        assert applied["fixtures_still_unconfirmed"] == 8

        # The rig the 3D view loads now carries its room.
        rig = (await client.get(f"/api/rigs/{rig_id}")).json()
        shell = rig["room_shell"]
        assert shell == response.json()["room_shell"]
        assert shell["room"]["width"] == pytest.approx(ROOM["width"], abs=0.1)
        stage = next(r for r in shell["risers"] if r["kind"] == "stage")
        assert stage["center_x"] == pytest.approx((STAGE["x_min"] + STAGE["x_max"]) / 2, abs=0.1)
        assert stage["center_z"] == pytest.approx((STAGE["z_min"] + STAGE["z_max"]) / 2, abs=0.1)
        # The stage size the engine and the mount logic read is left alone.
        assert (rig["stage_width"], rig["stage_depth"], rig["stage_height"]) == (12.0, 10.0, 8.0)

        # And it is in the rig list the visualizer page reads.
        listed = (await client.get("/api/rigs/", params={"size": 100})).json()["items"]
        assert next(item for item in listed if item["id"] == rig_id)["room_shell"] is not None

    @pytest.mark.asyncio
    async def test_guesses_move_a_row_at_a_time_and_stay_guesses(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )
        assert response.status_code == 200, response.text
        after = await fixtures_by_name(client, rig_id)

        # The truss row hangs under the truss the scan found, spaced as it was.
        spots = [after[f"Spot {n}"] for n in range(1, 5)]
        for spot in spots:
            assert spot["position_y"] == pytest.approx(TRUSS["bottom"], abs=0.1)
            assert spot["position_z"] == pytest.approx(TRUSS["z"], abs=0.1)
        assert [round(b["position_x"] - a["position_x"], 6) for a, b in zip(spots, spots[1:])] == [2.0, 2.0, 2.0]
        assert len({spot["position_y"] for spot in spots}) == 1
        assert len({spot["position_z"] for spot in spots}) == 1

        # The floor row is up on the stage.
        for n in range(1, 4):
            par = after[f"Par {n}"]
            assert par["position_y"] == pytest.approx(0.2 + STAGE["height"], abs=0.06)
            assert STAGE["z_min"] < par["position_z"] < STAGE["z_max"]

        # Every moved fixture is still a template guess, and says a scan shifted it.
        for name in ("Spot 1", "Spot 4", "Par 2"):
            tags = after[name]["tags"]
            assert is_unconfirmed(tags)
            assert position_source(tags) == "template"
            assert "position_hint:room_scan" in tags

        # What a person, a file or a row fit placed is exactly where it was.
        for name in ("Tapped", "Agreed", "Measured", "Fitted"):
            assert place(after[name]) == place(before[name])
            assert after[name]["tags"] == before[name]["tags"]

    @pytest.mark.asyncio
    async def test_the_moved_guesses_are_what_locate_mode_then_walks(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """Flash-and-tap still finalises them: a tap takes the flag off a fixture the scan moved."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )
        after = await fixtures_by_name(client, rig_id)
        spot = after["Spot 1"]

        # Dragging in the layout view is a plain position update with the tags it sends.
        dragged = await client.put(f"/api/rigs/{rig_id}/fixtures/{spot['id']}", json={
            "position_x": -3.4, "position_z": 0.6,
            "tags": ["position_source:tap"],
        })
        assert dragged.status_code == 200, dragged.text
        assert not is_unconfirmed(dragged.json()["tags"])

        # A second scan leaves the fixture a person placed alone.
        again = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )
        assert again.status_code == 200, again.text
        assert again.json()["replaces_existing_shell"] is True
        final = await fixtures_by_name(client, rig_id)
        assert place(final["Spot 1"]) == (-3.4, spot["position_y"], 0.6)
        # And the rows already under the truss are not shifted a second time.
        assert again.json()["fixtures"]["would_move"] == 0

    @pytest.mark.asyncio
    async def test_apply_can_store_the_room_and_leave_the_fixtures(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()),
            params={"apply": True, "move_fixtures": False},
        )

        assert response.status_code == 200, response.text
        assert response.json()["applied"]["fixtures_moved"] == 0
        assert await fixtures_by_name(client, rig_id) == before
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is not None

    @pytest.mark.asyncio
    async def test_the_shell_can_be_taken_off_again(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )

        removed = await client.delete(f"/api/rigs/{rig_id}/room-shell")
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"rig_id": rig_id, "removed": True, "undo_available": 0}
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None
        assert (await client.delete(f"/api/rigs/{rig_id}/room-shell")).json()["removed"] is False

    @pytest.mark.asyncio
    async def test_a_rig_update_cannot_write_the_shell(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        """The shell is written by the scan endpoint only; a rig edit neither sets nor clears it."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )

        edited = await client.put(f"/api/rigs/{rig_id}", json={"name": "Renamed", "room_shell": None})

        assert edited.status_code == 200, edited.text
        assert edited.json()["name"] == "Renamed"
        assert edited.json()["room_shell"] is not None


class TestRoomScanNeedsAnOperator:

    @pytest.mark.asyncio
    async def test_the_route_is_behind_the_login(self, unauthenticated_client: AsyncClient):
        response = await unauthenticated_client.post(
            "/api/rigs/1/room-scan", files=upload("club.obj", b"v 0 0 0\n"),
        )
        assert response.status_code in (401, 403)
