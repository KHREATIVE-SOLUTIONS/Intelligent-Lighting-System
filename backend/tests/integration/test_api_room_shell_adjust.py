"""
Correcting a stored room over HTTP: size, height, heading, a new item, undo
===========================================================================

PATCH /api/rigs/{id}/room-shell/{kind}/{index} resizes, raises and turns;
POST /api/rigs/{id}/room-shell/{kind} adds; POST /api/rigs/{id}/room-shell/undo
takes the latest edit back. docs/ROOM_SCAN.md.

What has to hold: each change is stored (read back from the rig and from the
database row) and changes nothing else; no fixture and no fixture's patch is
touched, and the scan's own undo record is left alone; every edit leaves one
step to undo, an undo puts the whole room back, and the steps are gone once a
scan is read again or the room is taken off; a refused request writes nothing;
and all of it is refused while a locate walkthrough is running on the rig.

The synthetic room (tests/unit/room_scan_meshes.py) is 12 m by 9 m by 5 m with
a stage, a riser and one 8 m truss across it at 4 m.
"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.test_api_room_scan import LIGHTS, build_rig, fixtures_by_name, scan_file, upload


async def stored(client: AsyncClient, sample_rig_data, sample_fixture_data, lights=LIGHTS):
    rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=lights)
    applied = await client.post(
        f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
    )
    assert applied.status_code == 200, applied.text
    return rig_id, applied.json()["room_shell"]


async def rig_of(client: AsyncClient, rig_id: int) -> dict:
    rig = await client.get(f"/api/rigs/{rig_id}")
    assert rig.status_code == 200, rig.text
    return rig.json()


async def column(db_session, rig_id: int, name: str = "room_shell"):
    """A column as the database row has it, not as the loaded rig does (plain JSON is easy to answer and not write)."""
    row = (await db_session.execute(text(f"SELECT {name} FROM rigs WHERE id = :id"), {"id": rig_id})).one()
    return json.loads(row[0]) if isinstance(row[0], str) else row[0]


def bands_add_up(shell: dict) -> None:
    bands = shell["hanging_bands"]
    assert sum(band.get("lines", 0) for band in bands) == len(shell["truss_lines"])
    assert sum(band.get("rings", 0) for band in bands) == len(shell.get("truss_rings") or [])
    assert all(band.get("lines", 0) + band.get("rings", 0) > 0 for band in bands)


NO_EDITS = {"available": 0, "label": None}


class TestResizeHeightHeading:

    @pytest.mark.asyncio
    async def test_a_stage_is_resized_and_raised_and_nothing_else_changes(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data)
        fixtures = await fixtures_by_name(client, rig_id)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]
        assert (await rig_of(client, rig_id))["room_shell_edits"] == NO_EDITS

        # The stage alone: what the fixtures standing on it do when they go with it is test_api_room_shell_raised.py's.
        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/risers/0",
            json={"width": 7.5, "depth": 3.0, "height": 1.1, "carry_fixtures": False},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        item = answer["item"]
        assert (item["width"], item["depth"], item["height"]) == (7.5, 3.0, 1.1)
        assert (item["center_x"], item["center_z"]) == (before["risers"][0]["center_x"], before["risers"][0]["center_z"])
        assert item["suggested"] is False and "Resized by hand." in item["basis"]
        assert answer["changed"] is True
        assert answer["undo"] == {"available": 1, "label": f"{before['risers'][0]['name']} resized"}

        expected = {**before, "risers": [item, *before["risers"][1:]]}
        assert answer["room_shell"] == expected
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == expected and await column(db_session, rig_id) == expected
        assert rig["room_shell_edits"] == answer["undo"]
        # No fixture moved, no patch changed, and the scan's own undo is what it was.
        assert await fixtures_by_name(client, rig_id) == fixtures
        assert rig["room_scan_undo"] == scan_undo
        # The rooms the steps go back to are not sent with the rig.
        assert "room_shell_undo" not in rig

    @pytest.mark.asyncio
    async def test_a_truss_is_made_shorter_turned_and_lowered(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data)
        fixtures = await fixtures_by_name(client, rig_id)
        line = before["truss_lines"][0]
        mid_x, mid_z = (line["x1"] + line["x2"]) / 2, (line["z1"] + line["z2"]) / 2

        # The truss alone: what its fixtures do when they go with it is test_api_room_shell_carry.py's.
        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/truss_lines/0",
            json={"length": 6.0, "heading_deg": 90, "height": 3.2, "carry_fixtures": False},
        )

        assert response.status_code == 200, response.text
        item = response.json()["item"]
        assert (item["x1"], item["x2"]) == (pytest.approx(mid_x, abs=0.001), pytest.approx(mid_x, abs=0.001))
        assert (item["z1"], item["z2"]) == (pytest.approx(mid_z - 3, abs=0.001), pytest.approx(mid_z + 3, abs=0.001))
        assert (item["length"], item["axis"], item["heading_deg"], item["height"]) == (6.0, "z", 90.0, 3.2)
        assert item["top"] == pytest.approx(3.2 + (line["top"] - line["height"]), abs=0.001)

        shell = (await rig_of(client, rig_id))["room_shell"]
        assert shell == await column(db_session, rig_id)
        # The height it hung at is no longer one, and the height it hangs at is.
        assert [band["height"] for band in shell["hanging_bands"]] == [3.2]
        assert shell["hanging_bands"][0]["suggested"] is False
        bands_add_up(shell)
        # Asked to leave them, the fixtures the scan hung under it stay where they were.
        assert response.json()["fixtures_moved"] == []
        assert await fixtures_by_name(client, rig_id) == fixtures

    @pytest.mark.asyncio
    async def test_a_size_is_held_inside_the_room_and_one_too_big_is_refused(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        riser = before["risers"][1]

        # 12 m across and 2 m round it: 8 m either side. A 10 m riser's middle is within 3 m of the centre line.
        grown = await client.patch(f"{path}/risers/1", json={"width": 10.0})
        assert grown.status_code == 200, grown.text
        assert riser["center_x"] > 3.0 and grown.json()["item"]["center_x"] == 3.0
        assert "Moved by hand." in grown.json()["item"]["basis"]

        after = (await rig_of(client, rig_id))["room_shell"]
        too_big = await client.patch(f"{path}/risers/1", json={"width": 16.5})
        assert too_big.status_code == 422 and "room for 16 m" in too_big.json()["detail"]
        too_long = await client.patch(f"{path}/truss_lines/0", json={"length": 14.0, "heading_deg": 90})
        assert too_long.status_code == 422 and "room for 13 m" in too_long.json()["detail"]
        assert (await rig_of(client, rig_id))["room_shell"] == after

    @pytest.mark.asyncio
    async def test_what_cannot_be_resized_says_why_and_writes_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"

        for kind, body, words in [
            ("risers/0", {"width": 0.1}, "must be between"),
            ("risers/0", {"depth": -3}, "must be between"),
            ("risers/0", {"height": 0}, "must be between"),
            ("risers/0", {"height": 3.5}, "must be between"),
            ("truss_lines/0", {"length": 0.2}, "must be between"),
            ("truss_lines/0", {"height": 5.5}, "must be between 0.5 m and 5 m"),
            ("truss_lines/0", {"height": 0.2}, "must be between"),
            ("truss_lines/0", {"heading_deg": 400}, "between -360 and 360"),
            ("truss_lines/0", {"width": 2}, "It takes: length, height, heading"),
            ("risers/0", {"radius": 2}, "It takes: width, depth, height"),
            # A raised area takes a heading since slice 21; one past a whole turn is refused, as a line's is.
            ("risers/0", {"heading_deg": 400}, "between -360 and 360"),
        ]:
            refused = await client.patch(f"{path}/{kind}", json=body)
            assert refused.status_code == 422, (kind, body, refused.text)
            assert words in refused.json()["detail"], (kind, body, refused.text)

        # Not a number at all is FastAPI's own refusal: a list of errors.
        for body in ({"width": "wide"}, {"height": None, "length": "long"}, {"radius": [1]}):
            refused = await client.patch(f"{path}/risers/0", json=body)
            assert refused.status_code == 422 and isinstance(refused.json()["detail"], list)
        # JSON has no infinity; a client that sends one anyway is refused in a sentence, not with a 500.
        raw_json = {"Content-Type": "application/json"}
        for kind, raw in (
            ("risers/0", b'{"width": Infinity}'), ("risers/0", b'{"height": NaN}'),
            ("risers/0", b'{"center_x": -Infinity}'),
            ("truss_lines/0", b'{"length": -Infinity}'), ("truss_lines/0", b'{"heading_deg": NaN}'),
        ):
            refused = await client.patch(f"{path}/{kind}", content=raw, headers=raw_json)
            assert refused.status_code == 422, (raw, refused.text)
            assert "must be a number" in refused.json()["detail"], raw
        refused = await client.post(
            f"{path}/truss_rings", headers=raw_json,
            content=b'{"center_x": 0, "center_z": 0, "radius": Infinity, "height": 4}',
        )
        assert refused.status_code == 422 and "must be a number" in refused.json()["detail"]

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS

    @pytest.mark.asyncio
    async def test_an_edit_that_changes_nothing_leaves_no_step(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        stage = before["risers"][0]

        same = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/risers/0",
            json={"name": stage["name"], "width": stage["width"], "height": stage["height"]},
        )

        assert same.status_code == 200, same.text
        assert same.json()["changed"] is False and same.json()["undo"] == NO_EDITS
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS


class TestAdd:

    @pytest.mark.asyncio
    async def test_a_booth_a_truss_and_a_ring_are_added_by_hand(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data)
        fixtures = await fixtures_by_name(client, rig_id)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]
        path = f"/api/rigs/{rig_id}/room-shell"

        booth = await client.post(f"{path}/risers", json={
            "name": "DJ booth", "riser_kind": "booth", "center_x": 0.0, "center_z": 3.0,
            "width": 2.0, "depth": 1.0, "height": 1.0,
        })
        assert booth.status_code == 201, booth.text
        answer = booth.json()
        assert (answer["kind"], answer["index"]) == ("risers", len(before["risers"]))
        assert answer["item"] == {
            "center_x": 0.0, "center_z": 3.0, "width": 2.0, "depth": 1.0, "height": 1.0, "base_height": 0.0,
            "name": "DJ booth", "kind": "booth", "suggested": False, "added_by_hand": True, "basis": "Added by hand.",
        }
        assert "DJ booth was added" in answer["message"] and "No fixture was moved" in answer["message"]
        assert answer["undo"] == {"available": 1, "label": "DJ booth added"}

        truss = await client.post(f"{path}/truss_lines", json={
            "center_x": 0.0, "center_z": -2.0, "length": 6.0, "height": 4.1,
        })
        assert truss.status_code == 201, truss.text
        line = truss.json()["item"]
        assert (line["x1"], line["z1"], line["x2"], line["z2"]) == (-3.0, -2.0, 3.0, -2.0)
        assert (line["name"], line["axis"], line["added_by_hand"]) == ("Overhead line 2", "x", True)

        ring = await client.post(f"{path}/truss_rings", json={
            "name": "Halo", "center_x": 1.0, "center_z": 1.0, "radius": 1.5, "height": 2.5,
        })
        assert ring.status_code == 201, ring.text
        assert ring.json()["undo"] == {"available": 3, "label": "Halo added"}

        rig = await rig_of(client, rig_id)
        shell = rig["room_shell"]
        assert shell == ring.json()["room_shell"] == await column(db_session, rig_id)
        # At the end of each list: what the scan found has kept its place.
        assert shell["risers"][:-1] == before["risers"] and shell["risers"][-1]["name"] == "DJ booth"
        assert shell["truss_lines"][:-1] == before["truss_lines"]
        assert [r["name"] for r in shell["truss_rings"]] == ["Halo"]
        # The truss joined the scanned truss's hanging height; the ring started its own.
        assert [(b["height"], b["lines"], b["rings"]) for b in shell["hanging_bands"]] == [
            (2.5, 0, 1), (before["hanging_bands"][0]["height"], 2, 0),
        ]
        bands_add_up(shell)
        assert await fixtures_by_name(client, rig_id) == fixtures
        assert rig["room_scan_undo"] == scan_undo

        # What was added is edited and deleted like anything else, by its place.
        renamed = await client.patch(f"{path}/truss_rings/0", json={"name": "Mirror ball ring", "radius": 2.0})
        assert renamed.status_code == 200 and renamed.json()["item"]["added_by_hand"] is True
        assert (await client.delete(f"{path}/truss_rings/0")).status_code == 200

    @pytest.mark.asyncio
    async def test_what_cannot_be_added_says_why_and_writes_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        bare = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        stage = {"center_x": 0, "center_z": 0, "width": 2, "depth": 2, "height": 0.5}
        no_room = await client.post(f"/api/rigs/{bare}/room-shell/risers", json=stage)
        assert no_room.status_code == 404 and "no scanned room" in no_room.json()["detail"]
        assert (await client.post("/api/rigs/999999/room-shell/risers", json=stage)).status_code == 404

        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        assert (await client.post(f"{path}/hanging_bands", json=stage)).status_code == 404
        assert (await client.post(f"{path}/room", json=stage)).status_code == 404

        for kind, body, words in [
            ("risers", {"center_x": 0, "center_z": 0}, "needs a width and a depth and a height"),
            ("risers", {**stage, "riser_kind": "bar"}, "one of: stage, riser, booth"),
            ("risers", {**stage, "width": 0.1}, "must be between"),
            ("risers", {**stage, "height": 4}, "must be between"),
            ("risers", {**stage, "width": 17}, "room for 16 m"),
            ("risers", {**stage, "name": " "}, "at least one letter"),
            ("risers", {**stage, "name": "x" * 61}, "at most 60"),
            ("risers", {"width": 2, "depth": 2, "height": 0.5}, "where its middle goes"),
            ("truss_lines", {"center_x": 0, "center_z": 0, "height": 4}, "needs a length"),
            ("truss_lines", {"center_x": 0, "center_z": 0, "length": 4, "height": 6}, "must be between"),
            ("truss_lines", {"center_x": 0, "center_z": 0, "length": 4, "height": 4, "riser_kind": "stage"},
             "Only a raised area"),
            ("truss_rings", {"center_x": 0, "center_z": 0, "radius": 0.1, "height": 4}, "must be between"),
            ("truss_rings", {"center_x": 0, "center_z": 0, "radius": 1, "height": 4, "length": 3}, "It takes:"),
        ]:
            refused = await client.post(f"{path}/{kind}", json=body)
            assert refused.status_code == 422, (kind, body, refused.text)
            assert words in refused.json()["detail"], (kind, body, refused.text)

        assert (await client.post(f"{path}/risers", json={**stage, "width": "wide"})).status_code == 422
        assert (await client.post(f"{path}/risers")).status_code == 422

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS


class TestUndo:

    @pytest.mark.asyncio
    async def test_each_undo_takes_back_one_edit_latest_first(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        fixtures = await fixtures_by_name(client, rig_id)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]
        path = f"/api/rigs/{rig_id}/room-shell"
        stage, truss = scanned["risers"][0]["name"], scanned["truss_lines"][0]["name"]

        rooms = [scanned]
        for request in (
            client.patch(f"{path}/risers/0", json={"name": "Main stage"}),
            client.patch(f"{path}/risers/1", json={"center_x": 1.0}),
            client.patch(f"{path}/truss_lines/0", json={"height": 3.0, "length": 5.0}),
            client.post(f"{path}/truss_rings", json={"center_x": 0, "center_z": 0, "radius": 2, "height": 4.5}),
            client.delete(f"{path}/risers/0"),
        ):
            response = await request
            assert response.status_code in (200, 201), response.text
            rooms.append(response.json()["room_shell"])
        # The truss took the four fixtures the scan hung under it along, in the same step.
        labels = [
            f"{stage} renamed", f"{scanned['risers'][1]['name']} moved", f"{truss} resized, with 4 fixtures",
            "Overhead ring 1 added", "Main stage deleted",
        ]
        assert await fixtures_by_name(client, rig_id) != fixtures
        assert len({json.dumps(room, sort_keys=True) for room in rooms}) == 6

        preview = await client.get(f"{path}/undo")
        assert preview.status_code == 200 and preview.json() == {
            "rig_id": rig_id, "available": 5, "label": labels[-1],
        }
        assert (await rig_of(client, rig_id))["room_shell_edits"] == {"available": 5, "label": labels[-1]}
        # The record survives a reload because it is in the row, not in the session.
        assert [step["label"] for step in (await column(db_session, rig_id, "room_shell_undo"))["steps"]] == labels

        for left in range(4, -1, -1):
            undone = await client.post(f"{path}/undo")
            assert undone.status_code == 200, undone.text
            answer = undone.json()
            assert answer["undone"] == labels[left]
            assert answer["message"] == f"Undone: {labels[left]}. " + (
                "4 fixtures put back where they hung before it." if left == 2 else "No fixture was moved."
            )
            assert len(answer["fixtures_restored"]) == (4 if left == 2 else 0) and answer["fixtures_skipped"] == []
            assert answer["room_shell"] == rooms[left]
            assert answer["undo"] == {"available": left, "label": labels[left - 1] if left else None}
            rig = await rig_of(client, rig_id)
            assert rig["room_shell"] == rooms[left] == await column(db_session, rig_id)
            assert rig["room_shell_edits"] == answer["undo"]

        # All the way back: the room is the scan's again, band for band and place for place.
        assert (await rig_of(client, rig_id))["room_shell"] == scanned
        assert await column(db_session, rig_id, "room_shell_undo") is None
        nothing = await client.post(f"{path}/undo")
        assert nothing.status_code == 409 and "no edit to the room left to undo" in nothing.json()["detail"]
        assert (await rig_of(client, rig_id))["room_shell"] == scanned
        # Every fixture is back exactly where it was, and the scan's undo is still there.
        assert await fixtures_by_name(client, rig_id) == fixtures
        assert (await rig_of(client, rig_id))["room_scan_undo"] == scan_undo

    @pytest.mark.asyncio
    async def test_a_refused_edit_leaves_no_step(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        assert (await client.patch(f"{path}/risers/0", json={"width": 99})).status_code == 422
        assert (await client.delete(f"{path}/risers/9")).status_code == 404
        assert (await client.post(f"{path}/truss_rings", json={"radius": 1})).status_code == 422
        assert (await client.get(f"{path}/undo")).json()["available"] == 0

    @pytest.mark.asyncio
    async def test_only_the_last_twenty_edits_are_kept(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        for n in range(23):
            assert (await client.patch(f"{path}/risers/0", json={"name": f"Stage {n}"})).status_code == 200
        assert (await client.get(f"{path}/undo")).json() == {
            "rig_id": rig_id, "available": 20, "label": "Stage 21 renamed",
        }

    @pytest.mark.asyncio
    async def test_a_scan_read_again_clears_the_steps(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        await client.patch(f"{path}/risers/0", json={"name": "Main stage"})
        await client.delete(f"{path}/truss_lines/0")
        assert (await rig_of(client, rig_id))["room_shell_edits"]["available"] == 2

        # A preview writes nothing, the steps included.
        preview = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()))
        assert preview.status_code == 200
        assert (await rig_of(client, rig_id))["room_shell_edits"]["available"] == 2

        again = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )
        assert again.status_code == 200, again.text
        rig = await rig_of(client, rig_id)
        # Slice 32: the name set by hand is kept across the reading (until then the room was `scanned`
        # again). The steps are cleared as before. Slice 34: the deleted line stays out (until then it
        # was the scan's again), and the room remembers it.
        stage = scanned["risers"][0]
        named = {**stage, "name": "Main stage", "basis": stage["basis"] + " Name set by hand."}
        truss = scanned["truss_lines"][0]
        record = {key: truss[key] for key in ("name", "x1", "z1", "x2", "z2", "across", "height")}
        kept = {
            **scanned, "risers": [named, *scanned["risers"][1:]], "truss_lines": [], "hanging_bands": [],
            "deleted_areas": [record],
        }
        assert rig["room_shell"] == kept and rig["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id, "room_shell_undo") is None
        assert (await client.post(f"{path}/undo")).status_code == 409
        assert (await rig_of(client, rig_id))["room_shell"] == kept

    @pytest.mark.asyncio
    async def test_taking_the_room_off_clears_the_steps(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell"
        await client.patch(f"{path}/risers/0", json={"name": "Main stage"})

        assert (await client.delete(path)).status_code == 200

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] is None and rig["room_shell_edits"] == NO_EDITS
        # An undo does not bring back a room that was taken off.
        assert (await client.post(f"{path}/undo")).status_code == 409
        assert (await rig_of(client, rig_id))["room_shell"] is None

    @pytest.mark.asyncio
    async def test_a_rig_that_is_not_there(self, client: AsyncClient):
        assert (await client.get("/api/rigs/999999/room-shell/undo")).status_code == 404
        assert (await client.post("/api/rigs/999999/room-shell/undo")).status_code == 404

    @pytest.mark.asyncio
    async def test_a_new_rig_has_no_edits_to_undo(self, client: AsyncClient, sample_rig_data):
        rig = await client.post("/api/rigs/", json=sample_rig_data)
        assert rig.status_code == 201, rig.text
        rig_id = rig.json()["id"]
        assert (await rig_of(client, rig_id))["room_shell_edits"] == NO_EDITS
        assert (await client.post(f"/api/rigs/{rig_id}/room-shell/undo")).status_code == 409


class TestLocateWalkthrough:

    @pytest.mark.asyncio
    async def test_the_room_is_not_edited_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """Flash-and-tap places lights against the room as it stands; it is not changed under it."""
        from app.api.endpoints import rig_identify

        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data)
        other, _ = await stored(
            client, {**sample_rig_data, "name": "The other room"}, {**sample_fixture_data, "name": "Other"}, lights=[],
        )
        path = f"/api/rigs/{rig_id}/room-shell"
        renamed = await client.patch(f"{path}/risers/0", json={"name": "Main stage"})
        assert renamed.status_code == 200, renamed.text
        before = await rig_of(client, rig_id)
        ring = {"center_x": 0, "center_z": 0, "radius": 1, "height": 4}

        def requests(base: str):
            return [
                client.patch(f"{base}/risers/0", json={"name": "Bar"}),
                client.patch(f"{base}/risers/0", json={"width": 5.0}),
                client.patch(f"{base}/truss_lines/0", json={"center_x": 1.0}),
                client.delete(f"{base}/risers/1"),
                client.post(f"{base}/truss_rings", json=ring),
                client.post(f"{base}/undo"),
            ]

        rig_identify._sessions["room-edit-test"] = rig_identify._Session(
            session_id="room-edit-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for request in requests(path):
                refused = await request
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            # Before anything else about the request is looked at: there is no such item.
            assert (await client.delete(f"{path}/risers/9")).status_code == 409
            # But after the rig is found, and after the body is read.
            assert (await client.delete("/api/rigs/999999/room-shell/risers/0")).status_code == 404
            assert (await client.patch(f"{path}/risers/0", json={"width": "wide"})).status_code == 422

            after = await rig_of(client, rig_id)
            assert after["room_shell"] == before["room_shell"]
            assert after["room_shell_edits"] == before["room_shell_edits"] == {
                "available": 1, "label": before["room_shell_edits"]["label"],
            }
            # Reading what an undo would take back writes nothing, and is answered.
            assert (await client.get(f"{path}/undo")).status_code == 200
            # Another rig's room is not held by this rig's walkthrough.
            elsewhere = await client.patch(f"/api/rigs/{other}/room-shell/risers/0", json={"name": "Bar"})
            assert elsewhere.status_code == 200, elsewhere.text
        finally:
            rig_identify._sessions.pop("room-edit-test", None)

        # Once the walkthrough is over the same requests go through.
        for request in requests(path):
            response = await request
            assert response.status_code in (200, 201), response.text

    @pytest.mark.asyncio
    async def test_a_walkthrough_that_has_let_go_holds_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        session = rig_identify._Session(
            session_id="room-edit-done", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        session.released = True
        rig_identify._sessions["room-edit-done"] = session
        try:
            response = await client.patch(f"/api/rigs/{rig_id}/room-shell/risers/0", json={"height": 1.0})
            assert response.status_code == 200, response.text
        finally:
            rig_identify._sessions.pop("room-edit-done", None)


class TestNeedsAnOperator:

    @pytest.mark.asyncio
    async def test_adding_and_undoing_are_behind_the_login(self, unauthenticated_client: AsyncClient):
        ring = {"center_x": 0, "center_z": 0, "radius": 1, "height": 4}
        for response in (
            await unauthenticated_client.post("/api/rigs/1/room-shell/truss_rings", json=ring),
            await unauthenticated_client.post("/api/rigs/1/room-shell/undo"),
            await unauthenticated_client.get("/api/rigs/1/room-shell/undo"),
            await unauthenticated_client.patch("/api/rigs/1/room-shell/risers/0", json={"width": 2}),
        ):
            assert response.status_code in (401, 403)
