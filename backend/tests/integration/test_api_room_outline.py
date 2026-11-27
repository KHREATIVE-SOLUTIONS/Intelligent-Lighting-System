"""
Correcting a stored room's walls over HTTP
==========================================

PATCH /api/rigs/{id}/room-shell/outline redraws the walls and sets the
room's height; PATCH, POST and DELETE under .../room-shell/outline/corners
move, add and take out one corner; GET .../room-shell/outline reads them.
docs/ROOM_SCAN.md.

What has to hold: the walls asked for are stored (read back from the rig and
from the database row) with the box round them; no fixture and nothing in the
room is moved, and what the new walls leave outside is listed instead; each
change is one step of the room's own undo, and an undo puts the whole room
back; a refused request writes nothing; all of it is refused while a locate
walkthrough is running; and reading the scan again replaces it all.

The synthetic room (tests/unit/room_scan_meshes.py) is a 12 m by 9 m by 5 m
box with a stage, a riser and one 8 m truss across it at 4 m.
"""

import pytest
from httpx import AsyncClient

from app.services.room_scan.outline_edit import outside_report
from tests.integration.test_api_room_scan import fixtures_by_name, light, scan_file, upload
from tests.integration.test_api_room_shell_adjust import NO_EDITS, bands_add_up, column, rig_of, stored

MEASURED = ["position_source:mvr"]
# Lights a scan does not move: each was measured. One where the notch of the L
# below will be, one well inside, one on the line a wall of the L will run along.
LIGHTS = [
    light("In the notch", 1, 3.0, 3.0, 3.0, "Side", tags=MEASURED),
    light("Inside", 101, -3.0, 3.0, 3.0, "Side", tags=MEASURED),
    light("On the wall", 201, 0.0, 3.0, 2.0, "Side", tags=MEASURED),
]

BOX = [{"x": -6.0, "z": -4.5}, {"x": 6.0, "z": -4.5}, {"x": 6.0, "z": 4.5}, {"x": -6.0, "z": 4.5}]
# The box with its downstage stage left quarter cut out.
L_CORNERS = [[-6, -4.5], [6, -4.5], [6, 0], [0, 0], [0, 4.5], [-6, 4.5]]
RAW_JSON = {"Content-Type": "application/json"}


def points(corners) -> list:
    return [{"x": float(x), "z": float(z)} for x, z in corners]


class TestReadingTheWalls:

    @pytest.mark.asyncio
    async def test_a_box_room_answers_its_four_corners_and_writes_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        assert "outline" not in before["room"]
        assert (before["room"]["width"], before["room"]["depth"]) == (12.0, 9.0)

        response = await client.get(f"/api/rigs/{rig_id}/room-shell/outline")

        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["outline"] == BOX and answer["box"] is True
        assert (answer["width"], answer["depth"], answer["height"]) == (12.0, 9.0, before["room"]["height"])
        assert answer["outside"]["fixtures"] == []
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS

    @pytest.mark.asyncio
    async def test_a_rig_with_no_room_has_no_walls(self, client: AsyncClient, sample_rig_data):
        rig = await client.post("/api/rigs/", json=sample_rig_data)
        rig_id = rig.json()["id"]
        for request in (
            client.get(f"/api/rigs/{rig_id}/room-shell/outline"),
            client.patch(f"/api/rigs/{rig_id}/room-shell/outline", json={"height": 4}),
            client.patch(f"/api/rigs/{rig_id}/room-shell/outline/corners/0", json={"x": 1}),
            client.post(f"/api/rigs/{rig_id}/room-shell/outline/corners", json={"after": 0}),
            client.delete(f"/api/rigs/{rig_id}/room-shell/outline/corners/0"),
        ):
            refused = await request
            assert refused.status_code == 404, refused.text
            assert "no scanned room" in refused.json()["detail"]
        assert (await client.get("/api/rigs/999999/room-shell/outline")).json()["detail"] == "Rig not found"
        assert (await client.patch("/api/rigs/999999/room-shell/outline", json={"height": 4})).status_code == 404


class TestRedrawingTheWalls:

    @pytest.mark.asyncio
    async def test_the_walls_are_stored_nothing_moves_and_what_is_outside_is_listed(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        fixtures = await fixtures_by_name(client, rig_id)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]

        response = await client.patch(f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": L_CORNERS})

        assert response.status_code == 200, response.text
        answer = response.json()
        shell = answer["room_shell"]
        assert shell["room"]["outline"] == points(L_CORNERS) == answer["outline"]
        assert answer["box"] is False and answer["changed"] is True
        # The box round the walls, about an origin that has not moved.
        assert (shell["room"]["width"], shell["room"]["depth"], shell["room"]["height"]) == (
            12.0, 9.0, before["room"]["height"],
        )
        assert shell["room"]["suggested"] is False and "Walls set by hand." in shell["room"]["basis"]
        assert answer["undo"] == {"available": 1, "label": "Walls redrawn"}

        # Nothing in the room moved, and the hanging heights are what they were.
        for key in ("risers", "truss_lines", "truss_rings", "hanging_bands", "scan"):
            assert shell[key] == before[key]
        bands_add_up(shell)
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == shell and await column(db_session, rig_id) == shell
        assert rig["room_shell_edits"] == answer["undo"]
        # No fixture moved, no patch changed, and the scan's own undo is what it was.
        assert await fixtures_by_name(client, rig_id) == fixtures
        assert rig["room_scan_undo"] == scan_undo

        # The light in the notch is listed; the one on the new wall and the one inside are not.
        outside = answer["outside"]
        assert [(entry["name"], entry["reason"], entry["already_outside"]) for entry in outside["fixtures"]] == [
            ("In the notch", "outside the walls", False),
        ]
        assert outside["fixtures"][0]["rig_fixture_id"] == fixtures["In the notch"]["id"]
        assert outside["fixtures"][0]["position"] == {"x": 3.0, "y": 3.0, "z": 3.0}
        # The items are those the room itself says are outside, each by its list and its place in it.
        assert outside["items"] == outside_report(shell)["items"]
        for entry in outside["items"]:
            assert shell[entry["kind"]][entry["index"]]["name"] == entry["name"]
        assert outside["count"] == len(outside["items"]) + 1
        assert "Walls redrawn." in answer["message"] and "Nothing was moved" in answer["message"]

        # The same list is read back with the walls.
        read = (await client.get(f"/api/rigs/{rig_id}/room-shell/outline")).json()
        assert read["outline"] == points(L_CORNERS) and read["box"] is False
        assert [entry["name"] for entry in read["outside"]["fixtures"]] == ["In the notch"]

    @pytest.mark.asyncio
    async def test_a_riser_the_new_walls_cut_through_is_listed_by_its_place(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        riser = before["risers"][1]
        # A wall drawn through the middle of the riser, from upstage to downstage.
        wall = riser["center_x"]
        assert 0 < wall < 6

        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline",
            json={"corners": [[-6, -4.5], [wall, -4.5], [wall, 4.5], [-6, 4.5]]},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        listed = {(entry["kind"], entry["index"]): entry for entry in answer["outside"]["items"]}
        assert listed[("risers", 1)]["name"] == riser["name"]
        assert listed[("risers", 1)]["reason"] == "partly outside the walls"
        assert listed[("risers", 1)]["already_outside"] is False
        # It is where it was.
        assert answer["room_shell"]["risers"] == before["risers"]
        # The walls are not centred on the origin any more: the box that is holds them.
        assert answer["room_shell"]["room"]["width"] == 12.0 and answer["width"] == 12.0

    @pytest.mark.asyncio
    async def test_the_height_is_set_and_what_is_above_the_ceiling_is_listed(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        truss = before["truss_lines"][0]
        assert truss["height"] > 3.5

        response = await client.patch(f"/api/rigs/{rig_id}/room-shell/outline", json={"height": 3.5})

        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["height"] == 3.5 and answer["box"] is True and answer["outline"] == BOX
        assert answer["undo"] == {"available": 1, "label": "Room height set to 3.5 m"}
        shell = answer["room_shell"]
        assert "outline" not in shell["room"] and "Height set by hand." in shell["room"]["basis"]
        assert await column(db_session, rig_id) == shell
        # The truss is where it hung, and is listed.
        assert shell["truss_lines"] == before["truss_lines"] and shell["hanging_bands"] == before["hanging_bands"]
        assert [(entry["kind"], entry["index"], entry["reason"]) for entry in answer["outside"]["items"]] == [
            ("truss_lines", 0, "above the ceiling"),
        ]
        assert answer["outside"]["fixtures"] == []

        both = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": L_CORNERS, "height": 5},
        )
        assert both.status_code == 200, both.text
        assert both.json()["undo"] == {"available": 2, "label": "Walls redrawn and room height set to 5 m"}
        assert both.json()["room_shell"]["room"]["height"] == 5.0

    @pytest.mark.asyncio
    async def test_the_same_walls_change_nothing_and_leave_no_step(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        same = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline",
            json={"corners": [[-6, -4.5], [6, -4.5], [6, 4.5], [-6, 4.5]], "height": before["room"]["height"]},
        )
        assert same.status_code == 200, same.text
        assert same.json()["changed"] is False and same.json()["undo"] == NO_EDITS
        assert same.json()["room_shell"] == before
        assert await column(db_session, rig_id) == before
        assert await column(db_session, rig_id, "room_shell_undo") is None

    @pytest.mark.asyncio
    async def test_a_box_drawn_wider_is_still_a_box(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        wider = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": [[-8, -5], [8, -5], [8, 5], [-8, 5]]},
        )
        assert wider.status_code == 200, wider.text
        room = wider.json()["room_shell"]["room"]
        assert "outline" not in room and (room["width"], room["depth"]) == (16.0, 10.0)
        assert wider.json()["box"] is True

    @pytest.mark.asyncio
    async def test_a_fixture_by_a_wall_far_from_the_origin_is_not_shifted_when_it_is_placed(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The room's box is what a position is held to: it has to hold walls that are not centred."""
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        drawn = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": [[-4, -4.5], [10, -4.5], [10, 4.5], [-4, 4.5]]},
        )
        assert drawn.status_code == 200, drawn.text
        assert drawn.json()["room_shell"]["room"]["width"] == 20.0
        fixture_id = (await fixtures_by_name(client, rig_id))["Inside"]["id"]

        placed = await client.put(
            f"/api/rigs/{rig_id}/fixtures/{fixture_id}/position", json={"position_x": 9.5, "position_z": 1.0},
        )

        assert placed.status_code == 200, placed.text
        assert (placed.json()["position_x"], placed.json()["position_z"]) == (9.5, 1.0)


class TestOneCorner:

    @pytest.mark.asyncio
    async def test_a_corner_is_moved_added_and_deleted_each_as_one_step_and_undone(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        fixtures = await fixtures_by_name(client, rig_id)
        path = f"/api/rigs/{rig_id}/room-shell/outline/corners"

        moved = await client.patch(f"{path}/2", json={"x": 7.5, "z": 5.0})
        assert moved.status_code == 200, moved.text
        assert moved.json()["index"] == 2 and moved.json()["box"] is False
        assert moved.json()["outline"] == [BOX[0], BOX[1], {"x": 7.5, "z": 5.0}, BOX[3]]
        assert moved.json()["undo"] == {"available": 1, "label": "Walls: corner 3 moved"}
        room = moved.json()["room_shell"]["room"]
        assert (room["width"], room["depth"]) == (15.0, 10.0)
        after_move = moved.json()["room_shell"]

        added = await client.post(path, json={"after": 0})
        assert added.status_code == 201, added.text
        assert added.json()["index"] == 1
        assert added.json()["outline"][1] == {"x": 0.0, "z": -4.5} and len(added.json()["outline"]) == 5
        assert added.json()["undo"] == {"available": 2, "label": "Walls: corner added after corner 1"}
        after_add = added.json()["room_shell"]

        # On the wall from the last corner back to the first, and pushed out from it.
        placed = await client.post(path, json={"after": 4, "x": -7, "z": 0})
        assert placed.status_code == 201, placed.text
        assert placed.json()["index"] == 5 and placed.json()["outline"][5] == {"x": -7.0, "z": 0.0}

        deleted = await client.delete(f"{path}/5")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["undo"] == {"available": 4, "label": "Walls: corner 6 deleted"}
        assert deleted.json()["room_shell"]["room"]["outline"] == after_add["room"]["outline"]
        assert await column(db_session, rig_id) == deleted.json()["room_shell"]

        one_of_two = await client.patch(f"{path}/1", json={"z": -5.0})
        assert one_of_two.status_code == 200, one_of_two.text
        assert one_of_two.json()["outline"][1] == {"x": 0.0, "z": -5.0}

        # Latest first, one step for each call, each back to the whole room as it was.
        undo = f"/api/rigs/{rig_id}/room-shell/undo"
        for label, shell in (
            ("Walls: corner 2 moved", deleted.json()["room_shell"]),
            ("Walls: corner 6 deleted", placed.json()["room_shell"]),
            ("Walls: corner added after corner 5", after_add),
            ("Walls: corner added after corner 1", after_move),
            ("Walls: corner 3 moved", before),
        ):
            undone = await client.post(undo)
            assert undone.status_code == 200, undone.text
            assert undone.json()["undone"] == label
            assert undone.json()["room_shell"] == shell
            assert set(undone.json()["outside"]) == {"items", "fixtures", "count"}
        assert (await client.post(undo)).status_code == 409
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and "outline" not in rig["room_shell"]["room"]
        assert rig["room_shell_edits"] == NO_EDITS
        assert await fixtures_by_name(client, rig_id) == fixtures

    @pytest.mark.asyncio
    async def test_an_undone_wall_takes_what_it_left_outside_off_the_list(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        drawn = await client.patch(f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": L_CORNERS})
        assert [entry["name"] for entry in drawn.json()["outside"]["fixtures"]] == ["In the notch"]

        undone = await client.post(f"/api/rigs/{rig_id}/room-shell/undo")

        assert undone.status_code == 200, undone.text
        assert undone.json()["outside"]["fixtures"] == []

    @pytest.mark.asyncio
    async def test_a_corner_moved_to_where_it_is_leaves_no_step(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        same = await client.patch(f"/api/rigs/{rig_id}/room-shell/outline/corners/1", json={"x": 6.0})
        assert same.status_code == 200, same.text
        assert same.json()["changed"] is False and same.json()["undo"] == NO_EDITS
        assert (await rig_of(client, rig_id))["room_shell"] == before

    @pytest.mark.asyncio
    async def test_a_room_keeps_three_corners_and_a_corner_that_is_not_there_is_not_found(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell/outline/corners"
        assert (await client.delete(f"{path}/3")).status_code == 200
        after = (await rig_of(client, rig_id))["room_shell"]
        assert len(after["room"]["outline"]) == 3

        kept = await client.delete(f"{path}/0")
        assert kept.status_code == 409 and "at least 3 corners" in kept.json()["detail"]
        for request in (
            client.delete(f"{path}/3"), client.patch(f"{path}/7", json={"x": 1}), client.post(path, json={"after": 3}),
            client.patch(f"{path}/-1", json={"x": 1}),
        ):
            missing = await request
            assert missing.status_code == 404, missing.text
            assert "no corner number" in missing.json()["detail"] and "(it has 3)" in missing.json()["detail"]
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == after and rig["room_shell_edits"]["available"] == 1


class TestRefusals:

    @pytest.mark.asyncio
    async def test_walls_that_are_not_a_room_are_refused_in_a_sentence_and_nothing_is_written(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell/outline"

        for body, words in (
            ({}, "Nothing to change"),
            ({"corners": [[0, 0], [4, 0]]}, "between 3 and 64 corners"),
            ({"corners": [[k, 0] for k in range(65)]}, "between 3 and 64 corners"),
            ({"corners": "square"}, "must be a list of corners"),
            ({"corners": [[0, 0], [4, 0], [4, 4, 4]]}, "Corner 3 must be two numbers"),
            ({"corners": [[0, 0], [4, 0], ["far", 4]]}, "Corner 3 must be two numbers"),
            ({"corners": [[0, 0], [4, 0], None]}, "Corner 3 must be two numbers"),
            ({"corners": [[-3, -3], [3, 3], [3, -3], [-3, 3]]}, "The walls would cross"),
            ({"corners": [[0, 0], [300, 0], [300, 4], [0, 4]]}, "the most is 100 m"),
            ({"corners": [[0, 0], [0.6, 0], [0.6, 4], [0, 4]]}, "0.6 m across"),
            ({"corners": [[0, 0], [4, 0], [4.02, 0], [4, 4]]}, "A wall is at least 0.1 m long"),
            ({"height": 1.0}, "between 1.5 m and 30 m"),
            ({"height": 45}, "between 1.5 m and 30 m"),
            # The walls are good and the height is not: neither is stored.
            ({"corners": L_CORNERS, "height": 0.5}, "between 1.5 m and 30 m"),
        ):
            refused = await client.patch(path, json=body)
            assert refused.status_code == 422, (body, refused.text)
            assert words in refused.json()["detail"], (body, refused.text)

        # JSON has no infinity; a client that sends one anyway is refused in a sentence, not with a 500.
        for raw, words in (
            (b'{"corners": [[0, 0], [Infinity, 0], [4, 4]]}', "Corner 2 must be two numbers"),
            (b'{"corners": [[0, 0], [4, 0], [4, NaN]]}', "Corner 3 must be two numbers"),
            (b'{"corners": [[0, 0], [4, 0], [-Infinity, -Infinity]]}', "Corner 3 must be two numbers"),
            (b'{"corners": Infinity}', "must be a list of corners"),
            (b'{"height": NaN}', "must be a number of metres"),
            (b'{"height": Infinity}', "must be a number of metres"),
        ):
            refused = await client.patch(path, content=raw, headers=RAW_JSON)
            assert refused.status_code == 422, (raw, refused.text)
            assert words in refused.json()["detail"], (raw, refused.text)
        for raw in (b'{"x": Infinity}', b'{"z": NaN}'):
            refused = await client.patch(f"{path}/corners/0", content=raw, headers=RAW_JSON)
            assert refused.status_code == 422 and "must be a number of metres" in refused.json()["detail"], raw
        refused = await client.post(f"{path}/corners", content=b'{"after": 0, "x": 1, "z": -Infinity}', headers=RAW_JSON)
        assert refused.status_code == 422 and "must be a number of metres" in refused.json()["detail"]

        # One corner at a time is held to the same rules.
        crossed = await client.patch(f"{path}/corners/2", json={"x": 0, "z": -9})
        assert crossed.status_code == 422 and "The walls would cross" in crossed.json()["detail"]
        nothing = await client.patch(f"{path}/corners/2", json={})
        assert nothing.status_code == 422 and "Nothing to change" in nothing.json()["detail"]
        half = await client.post(f"{path}/corners", json={"after": 0, "x": 1})
        assert half.status_code == 422 and "both x and z" in half.json()["detail"]

        # What FastAPI itself refuses, before the rig is looked at.
        for request in (
            client.patch(path, json={"height": "tall"}),
            client.patch(f"{path}/corners/first", json={"x": 1}),
            client.patch(f"{path}/corners/0", json={"x": "left"}),
            client.post(f"{path}/corners", json={}),
            client.post(f"{path}/corners", json={"after": "the last"}),
            client.delete(f"{path}/corners/first"),
        ):
            refused = await request
            assert refused.status_code == 422 and isinstance(refused.json()["detail"], list), refused.text

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id) == before
        assert await column(db_session, rig_id, "room_shell_undo") is None

    @pytest.mark.asyncio
    async def test_outline_is_not_one_of_the_lists_of_the_room(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The walls have routes of their own; the routes that take a list's name do not take theirs."""
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        added = await client.post(
            f"/api/rigs/{rig_id}/room-shell/outline", json={"center_x": 0, "center_z": 0, "radius": 1, "height": 3},
        )
        assert added.status_code == 404 and "'outline' is not part of a room" in added.json()["detail"]
        assert (await client.patch(f"/api/rigs/{rig_id}/room-shell/outline/0", json={"name": "Wall"})).status_code == 404
        assert (await rig_of(client, rig_id))["room_shell"] == before


class TestLocateWalkthrough:

    @pytest.mark.asyncio
    async def test_the_walls_are_not_edited_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        path = f"/api/rigs/{rig_id}/room-shell/outline"

        def requests():
            return [
                client.patch(path, json={"corners": L_CORNERS}),
                client.patch(path, json={"height": 4.5}),
                client.patch(f"{path}/corners/0", json={"x": -7}),
                client.post(f"{path}/corners", json={"after": 0}),
                client.delete(f"{path}/corners/1"),
            ]

        rig_identify._sessions["room-walls-test"] = rig_identify._Session(
            session_id="room-walls-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for request in requests():
                refused = await request
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            # Before anything else about the request is looked at, but after the rig is found and the body read.
            assert (await client.patch(path, json={"corners": [[0, 0]]})).status_code == 409
            assert (await client.patch("/api/rigs/999999/room-shell/outline", json={"height": 4})).status_code == 404
            assert (await client.patch(path, json={"height": "tall"})).status_code == 422
            # Reading the walls writes nothing, and is answered.
            assert (await client.get(path)).status_code == 200
            rig = await rig_of(client, rig_id)
            assert rig["room_shell"] == before and rig["room_shell_edits"] == NO_EDITS
        finally:
            rig_identify._sessions.pop("room-walls-test", None)

        # Once the walkthrough is over the same requests go through.
        for request in requests():
            response = await request
            assert response.status_code in (200, 201), response.text


class TestReadingTheScanAgain:

    @pytest.mark.asyncio
    async def test_a_scan_applied_again_replaces_the_walls_drawn_by_hand_and_their_undo(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, before = await stored(client, sample_rig_data, sample_fixture_data, lights=[])
        drawn = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/outline", json={"corners": L_CORNERS, "height": 4.4},
        )
        assert drawn.status_code == 200 and (await rig_of(client, rig_id))["room_shell_edits"]["available"] == 1

        again = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()), params={"apply": True},
        )

        assert again.status_code == 200, again.text
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == before and "outline" not in rig["room_shell"]["room"]
        assert rig["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id, "room_shell_undo") is None
        assert (await client.post(f"/api/rigs/{rig_id}/room-shell/undo")).status_code == 409


class TestNeedsAnOperator:

    @pytest.mark.asyncio
    async def test_the_walls_are_behind_the_login(self, unauthenticated_client: AsyncClient):
        path = "/api/rigs/1/room-shell/outline"
        for request in (
            unauthenticated_client.get(path),
            unauthenticated_client.patch(path, json={"height": 4}),
            unauthenticated_client.patch(f"{path}/corners/0", json={"x": 1}),
            unauthenticated_client.post(f"{path}/corners", json={"after": 0}),
            unauthenticated_client.delete(f"{path}/corners/0"),
        ):
            assert (await request).status_code in (401, 403)
