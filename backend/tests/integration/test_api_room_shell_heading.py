"""
A raised area at a heading, over HTTP
=====================================

PATCH /api/rigs/{id}/room-shell/risers/{index} takes a `heading_deg` and
stands a stage, riser or booth at it, with the fixtures standing on it and the
raised areas standing on it swung about its middle; POST
/api/rigs/{id}/room-shell/risers takes one for an added area.
docs/ROOM_SCAN.md, slice 21.

What has to hold: the heading is stored on the item and nowhere else; the
fixtures standing on it go round its middle and their own heading turns with
it; nothing else about them, or about the room, changes; one undo puts all of
it back; a riser on the stage turns with the stage and is listed with its
heading; an area added square says nothing, as it always did; and it is all
refused during a locate walkthrough.

The synthetic room (tests/unit/room_scan_meshes.py) is 12 m by 9 m by 5 m,
with a 6 m by 2.5 m stage 0.9 m high upstage; nothing here drives a fixture.
"""

import math

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, place
from tests.integration.test_api_room_shell_adjust import column, rig_of
from tests.integration.test_api_room_shell_carry import PLACE_KEYS, only_these_moved
from tests.integration.test_api_room_shell_raised import PARS, stage_of
from tests.integration.test_api_room_shell_stack import DRUM, ON_DRUM, stack_of


def about(x, z, degrees, cx, cz):
    """A point swung clockwise seen from above (+X towards +Z) about a middle."""
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return cx + (x - cx) * cos - (z - cz) * sin, cz + (x - cx) * sin + (z - cz) * cos


def heading_of(fixture: dict) -> float:
    return fixture["rotation_y"] or 0.0


class TestAStageTurnedToAHeading:

    @pytest.mark.asyncio
    async def test_it_is_stored_and_the_row_standing_on_it_goes_round_its_middle(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, index, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        assert "heading_deg" not in stage

        response = await client.patch(path, json={"heading_deg": 30})

        assert response.status_code == 200, response.text
        answer = response.json()
        item = answer["item"]
        assert item["heading_deg"] == 30.0 and item["suggested"] is False and "Resized by hand." in item["basis"]
        # Its middle and its sides are what they were: only the heading and the marks are new.
        assert {**item, "heading_deg": None, "suggested": None, "basis": None} == {
            **stage, "heading_deg": None, "suggested": None, "basis": None,
        }
        assert answer["changed"] is True and answer["items_moved"] == []
        assert sorted(move["name"] for move in answer["fixtures_moved"]) == PARS
        assert answer["message"] == f"3 fixtures standing on {stage['name']} moved with it."
        assert answer["undo"] == {"available": 1, "label": f"{stage['name']} turned, with 3 fixtures"}

        # The room: that one item, and nothing else.
        shell = answer["room_shell"]
        assert shell == await column(db_session, rig_id) == (await rig_of(client, rig_id))["room_shell"]
        assert {**shell, "risers": None} == {**scanned, "risers": None}
        assert [shell["risers"][n] for n in range(len(shell["risers"])) if n != index] == [
            scanned["risers"][n] for n in range(len(scanned["risers"])) if n != index
        ]

        # The fixtures: each swung about the stage's middle, its height kept, its own heading turned with it.
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, PARS, keys=PLACE_KEYS | {"rotation_y"})
        for name in PARS:
            x, z = about(before[name]["position_x"], before[name]["position_z"], 30, stage["center_x"], stage["center_z"])
            assert place(after[name]) == (
                pytest.approx(x, abs=0.001), before[name]["position_y"], pytest.approx(z, abs=0.001),
            )
            # rotation_y runs the other way round from a heading.
            assert after[name]["rotation_y"] == pytest.approx(heading_of(before[name]) - 30.0)
            assert "position_unconfirmed" in after[name]["tags"]

        # One undo: the room and the fixtures as they were, headings included.
        undone = await client.post(f"/api/rigs/{rig_id}/room-shell/undo")
        assert undone.status_code == 200, undone.text
        assert undone.json()["room_shell"] == scanned == await column(db_session, rig_id)
        assert len(undone.json()["fixtures_restored"]) == 3 and undone.json()["fixtures_skipped"] == []
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_turn_to_90_is_the_quarter_turn_the_sides_tell(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        by_heading = await client.patch(path, json={"heading_deg": 90})
        assert by_heading.status_code == 200, by_heading.text
        there = await fixtures_by_name(client, rig_id)
        assert (await client.post(f"/api/rigs/{rig_id}/room-shell/undo")).status_code == 200
        assert await fixtures_by_name(client, rig_id) == before

        by_sides = await client.patch(path, json={"width": stage["depth"], "depth": stage["width"]})
        assert by_sides.status_code == 200, by_sides.text
        assert "heading_deg" not in by_sides.json()["item"]

        # The same middle for the area (one may have been brought in to fit), and so the same places.
        assert by_heading.json()["item"]["center_z"] == by_sides.json()["item"]["center_z"]
        assert await fixtures_by_name(client, rig_id) == there

    @pytest.mark.asyncio
    async def test_the_fixtures_can_be_left_and_the_same_heading_changes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        left = await client.patch(path, json={"heading_deg": -20, "carry_fixtures": False})

        assert left.status_code == 200, left.text
        assert left.json()["item"]["heading_deg"] == -20.0 and left.json()["fixtures_moved"] == []
        assert left.json()["undo"]["label"] == f"{stage['name']} turned"
        assert await fixtures_by_name(client, rig_id) == before

        # Half a turn on is the same rectangle: nothing is written and no step is left.
        steps = len((await column(db_session, rig_id, "room_shell_undo"))["steps"])
        same = await client.patch(path, json={"heading_deg": 160})
        assert same.status_code == 200 and same.json()["changed"] is False
        assert same.json()["message"] == "Nothing was changed."
        assert len((await column(db_session, rig_id, "room_shell_undo"))["steps"]) == steps

    @pytest.mark.asyncio
    async def test_a_heading_that_is_not_one_is_refused_and_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        for body, words in (
            ({"heading_deg": 361}, "between -360 and 360"),
            ({"heading_deg": -400}, "between -360 and 360"),
        ):
            refused = await client.patch(path, json=body)
            assert refused.status_code == 422, (body, refused.text)
            assert words in refused.json()["detail"]
        assert (await client.patch(path, json={"heading_deg": "east"})).status_code == 422
        assert await column(db_session, rig_id) == scanned
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_it_is_refused_during_a_locate_walkthrough(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id, scanned, _, _, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        rig_identify._sessions["room-heading-test"] = rig_identify._Session(
            session_id="room-heading-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            refused = await client.patch(path, json={"heading_deg": 30})
            assert refused.status_code == 409, refused.text
            assert "locate walkthrough is running" in refused.json()["detail"]
            added = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={
                "center_x": 3.0, "center_z": 2.0, "width": 2.0, "depth": 1.0, "height": 0.3, "heading_deg": 45,
            })
            assert added.status_code == 409, added.text
            assert await column(db_session, rig_id) == scanned
            assert await fixtures_by_name(client, rig_id) == before
        finally:
            rig_identify._sessions.pop("room-heading-test", None)


class TestARiserOnATurnedStage:

    @pytest.mark.asyncio
    async def test_it_goes_round_with_the_stage_and_takes_its_heading(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, drum_at, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(path, json={"heading_deg": 30})

        assert response.status_code == 200, response.text
        answer = response.json()
        x, z = about(drum["center_x"], drum["center_z"], 30, stage["center_x"], stage["center_z"])
        assert answer["items_moved"] == [{
            "kind": "risers", "index": drum_at, "name": DRUM,
            "from": {"center_x": drum["center_x"], "center_z": drum["center_z"], "width": 1.2, "depth": 1.2,
                     "base_height": stage["height"], "heading_deg": 0.0},
            "to": {"center_x": pytest.approx(x, abs=0.001), "center_z": pytest.approx(z, abs=0.001),
                   "width": 1.2, "depth": 1.2, "base_height": stage["height"], "heading_deg": 30.0},
        }]
        now = answer["room_shell"]["risers"][drum_at]
        assert now["heading_deg"] == 30.0 and "Moved by hand." in now["basis"]
        assert answer["undo"]["label"] == f"{stage['name']} turned, with 1 raised area and 4 fixtures"

        carried = PARS + [ON_DRUM]
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, carried, keys=PLACE_KEYS | {"rotation_y"})
        for name in carried:
            to_x, to_z = about(
                before[name]["position_x"], before[name]["position_z"], 30, stage["center_x"], stage["center_z"],
            )
            # The riser's middle is stored to the millimetre, and the light on it goes by that.
            assert place(after[name]) == (
                pytest.approx(to_x, abs=0.002), before[name]["position_y"], pytest.approx(to_z, abs=0.002),
            )
            assert after[name]["rotation_y"] == pytest.approx(heading_of(before[name]) - 30.0)

        # One undo: the stage, the riser and every light.
        undone = await client.post(f"/api/rigs/{rig_id}/room-shell/undo")
        assert undone.status_code == 200, undone.text
        assert undone.json()["room_shell"] == room == await column(db_session, rig_id)
        assert await fixtures_by_name(client, rig_id) == before


class TestAddingARaisedAreaAtAHeading:

    @pytest.mark.asyncio
    async def test_an_added_one_keeps_its_heading_and_a_square_one_says_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, _, _, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        base = {"center_x": 3.0, "center_z": 2.0, "width": 2.0, "depth": 1.0, "height": 0.3}

        angled = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={**base, "heading_deg": 135})
        assert angled.status_code == 201, angled.text
        assert angled.json()["item"]["heading_deg"] == -45.0

        square = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={**base, "center_x": -3.0})
        assert square.status_code == 201, square.text
        assert "heading_deg" not in square.json()["item"]

        refused = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={**base, "heading_deg": 720})
        assert refused.status_code == 422 and "between -360 and 360" in refused.json()["detail"]
        assert await fixtures_by_name(client, rig_id) == before
