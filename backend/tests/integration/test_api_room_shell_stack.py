"""
A riser on a stage follows the stage, over HTTP; and a platform added floating
==============================================================================

PATCH /api/rigs/{id}/room-shell/risers/{index} takes the other raised areas
standing on a raised area along when it is moved, raised or given a quarter
turn with `carry_fixtures` true, with the fixtures standing on those, as one
step of the room's undo; `items_moved` lists them. POST
/api/rigs/{id}/room-shell/risers takes a `base_height`, validated as the
PATCH's is. docs/ROOM_SCAN.md, slice 20.

What has to hold: the riser and what stands on it move with the stage and are
listed; nothing else changes; a resize alone and `carry_fixtures` false leave
them; a carry that would put the riser or a fixture outside the room writes
nothing at all; one undo puts everything back; and it is all refused during a
locate walkthrough.

The synthetic room (tests/unit/room_scan_meshes.py) is 12 m by 9 m by 5 m,
with a 6 m by 2.5 m stage 0.9 m high upstage. A square drum riser is added on
the stage by hand, and the "Measured" light is stood on it; nothing here
drives a fixture.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, place
from tests.integration.test_api_room_shell_adjust import NO_EDITS, column, rig_of
from tests.integration.test_api_room_shell_carry import PLACE_KEYS, only_these_moved
from tests.integration.test_api_room_shell_raised import PARS, stage_of

DRUM = "Drum riser"
ON_DRUM = "Measured"
ADDED = {"available": 1, "label": f"{DRUM} added"}


async def stack_of(client, sample_rig_data, sample_fixture_data):
    """A stage with a drum riser on it and a light on the riser.

    (rig id, the room with the riser in it, the stage, the path to it, the
    riser's place, the riser, the fixtures by name.)
    """
    rig_id, _, _, stage, path, _ = await stage_of(client, sample_rig_data, sample_fixture_data)
    # 2 m stage left and 0.5 m downstage of the stage's middle, clear of the row of Pars along its
    # upstage edge, with its base on the stage's top.
    added = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={
        "center_x": stage["center_x"] + 2.0, "center_z": stage["center_z"] + 0.5, "width": 1.2, "depth": 1.2,
        "height": 0.3, "base_height": stage["height"], "name": DRUM,
    })
    assert added.status_code == 201, added.text
    drum_at, drum = added.json()["index"], added.json()["item"]
    lights = await fixtures_by_name(client, rig_id)
    stood = await client.put(f"/api/rigs/{rig_id}/fixtures/{lights[ON_DRUM]['id']}/position", json={
        "position_x": drum["center_x"] + 0.3, "position_y": stage["height"] + 0.3, "position_z": drum["center_z"] - 0.2,
    })
    assert stood.status_code == 200, stood.text
    before = await fixtures_by_name(client, rig_id)
    # The Pars are the stage's, clear of the riser and the 0.15 m round it.
    assert all(abs(before[name]["position_z"] - drum["center_z"]) > 0.75 for name in PARS)
    return rig_id, added.json()["room_shell"], stage, path, drum_at, drum, before


class TestARiserOnAStageFollowsIt:

    @pytest.mark.asyncio
    async def test_a_moved_stage_takes_the_riser_on_it_and_the_light_on_that(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, drum_at, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(
            path, json={"center_x": stage["center_x"] + 1.0, "center_z": stage["center_z"] + 0.5},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        carried = PARS + [ON_DRUM]
        assert sorted(move["name"] for move in answer["fixtures_moved"]) == sorted(carried)
        to = {"center_x": pytest.approx(drum["center_x"] + 1.0, abs=0.001),
              "center_z": pytest.approx(drum["center_z"] + 0.5, abs=0.001),
              "width": 1.2, "depth": 1.2, "base_height": stage["height"]}
        assert answer["items_moved"] == [{
            "kind": "risers", "index": drum_at, "name": DRUM,
            "from": {"center_x": drum["center_x"], "center_z": drum["center_z"], "width": 1.2, "depth": 1.2,
                     "base_height": stage["height"]},
            "to": to,
        }]
        assert answer["message"] == (
            f"4 fixtures standing on {stage['name']}, or on what stands on it, moved with it. "
            "1 raised area standing on it moved with it too."
        )
        assert answer["undo"] == {"available": 2, "label": f"{stage['name']} moved, with 1 raised area and 4 fixtures"}

        # The room: the stage and the riser moved, the riser marked as moved by hand; nothing else changed.
        shell = answer["room_shell"]
        now = shell["risers"][drum_at]
        assert {key: now[key] for key in to} == to
        assert "Moved by hand." in now["basis"] and now["height"] == 0.3 and now["name"] == DRUM
        assert shell == await column(db_session, rig_id) == (await rig_of(client, rig_id))["room_shell"]
        assert {**shell, "risers": None} == {**room, "risers": None}
        others = [n for n in range(len(room["risers"])) if n not in (drum_at, answer["index"])]
        assert all(shell["risers"][n] == room["risers"][n] for n in others)

        # The fixtures: the row on the stage and the light on the riser, each by what the stage moved.
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, carried)
        for name in carried:
            assert place(after[name]) == (
                pytest.approx(before[name]["position_x"] + 1.0, abs=0.001),
                before[name]["position_y"],
                pytest.approx(before[name]["position_z"] + 0.5, abs=0.001),
            )
        step = (await column(db_session, rig_id, "room_shell_undo"))["steps"][-1]
        assert step["shell"] == room and step["fixtures"] == answer["fixtures_moved"] and step["kind"] == "risers"

    @pytest.mark.asyncio
    async def test_a_higher_deck_and_a_base_height_raise_the_riser_and_its_light(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, stage, path, drum_at, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        higher = await client.patch(path, json={"height": 1.2})

        assert higher.status_code == 200, higher.text
        answer = higher.json()
        rise = 1.2 - stage["height"]
        assert [entry["index"] for entry in answer["items_moved"]] == [drum_at]
        now = answer["room_shell"]["risers"][drum_at]
        assert now["base_height"] == pytest.approx(1.2, abs=0.001) and "Resized by hand." in now["basis"]
        assert (now["center_x"], now["center_z"]) == (drum["center_x"], drum["center_z"])
        assert answer["undo"]["label"] == f"{stage['name']} resized, with 1 raised area and 4 fixtures"
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, PARS + [ON_DRUM])
        assert after[ON_DRUM]["position_y"] == pytest.approx(before[ON_DRUM]["position_y"] + rise, abs=0.001)

        floated = await client.patch(path, json={"base_height": 1.0})

        assert floated.status_code == 200, floated.text
        assert floated.json()["room_shell"]["risers"][drum_at]["base_height"] == pytest.approx(2.2, abs=0.001)
        floating = await fixtures_by_name(client, rig_id)
        assert floating[ON_DRUM]["position_y"] == pytest.approx(after[ON_DRUM]["position_y"] + 1.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_a_quarter_turn_swings_the_square_riser_and_its_light_about_the_stage_s_middle(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, stage, path, drum_at, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(path, json={"width": stage["depth"], "depth": stage["width"]})

        assert response.status_code == 200, response.text
        answer = response.json()
        item = answer["item"]
        now = answer["room_shell"]["risers"][drum_at]
        # 2 m stage left of the middle is now 2 m downstage of it, and 0.5 m downstage is 0.5 m stage right.
        assert (now["center_x"], now["center_z"]) == (
            pytest.approx(item["center_x"] - 0.5, abs=0.002), pytest.approx(item["center_z"] + 2.0, abs=0.002),
        )
        assert (now["width"], now["depth"]) == (1.2, 1.2)
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, PARS + [ON_DRUM], keys=PLACE_KEYS | {"rotation_y"})
        off_x = before[ON_DRUM]["position_x"] - stage["center_x"]
        off_z = before[ON_DRUM]["position_z"] - stage["center_z"]
        assert place(after[ON_DRUM]) == (
            pytest.approx(item["center_x"] - off_z, abs=0.002),
            before[ON_DRUM]["position_y"],
            pytest.approx(item["center_z"] + off_x, abs=0.002),
        )
        # A square riser's own sizes say no turn; its light is turned with the stage all the same.
        assert after[ON_DRUM]["rotation_y"] == pytest.approx(before[ON_DRUM]["rotation_y"] - 90.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_a_resize_alone_and_a_stage_told_to_go_alone_leave_the_riser_where_it_is(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, drum_at, _, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        alone = await client.patch(
            path, json={"center_x": stage["center_x"] + 1.0, "height": 1.2, "carry_fixtures": False},
        )

        assert alone.status_code == 200, alone.text
        answer = alone.json()
        assert answer["items_moved"] == [] and answer["fixtures_moved"] == []
        assert answer["message"] == f"The fixtures standing on {stage['name']} were left where they are, as asked."
        assert answer["undo"]["label"] == f"{stage['name']} moved and resized"
        assert answer["room_shell"]["risers"][drum_at] == room["risers"][drum_at]
        assert await fixtures_by_name(client, rig_id) == before
        assert (await client.post(f"/api/rigs/{rig_id}/room-shell/undo")).status_code == 200

        # A little narrower about its middle: the riser keeps its place and its light, with the box ticked.
        narrower = await client.patch(path, json={"width": stage["width"] - 0.5})

        assert narrower.status_code == 200, narrower.text
        assert narrower.json()["items_moved"] == []
        assert narrower.json()["room_shell"]["risers"][drum_at] == room["risers"][drum_at]
        assert (await fixtures_by_name(client, rig_id))[ON_DRUM] == before[ON_DRUM]

    @pytest.mark.asyncio
    async def test_a_riser_on_the_floor_beside_the_stage_is_not_carried(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, stage, path, _ = await stage_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(path, json={"center_z": stage["center_z"] + 0.5})

        assert response.status_code == 200, response.text
        answer = response.json()
        # As it was before slice 20: its words, its label and every other raised area.
        assert answer["items_moved"] == []
        assert answer["message"] == f"3 fixtures standing on {stage['name']} moved with it."
        assert answer["undo"] == {"available": 1, "label": f"{stage['name']} moved, with 3 fixtures"}
        assert [area for n, area in enumerate(answer["room_shell"]["risers"]) if n != answer["index"]] == [
            area for n, area in enumerate(room["risers"]) if n != answer["index"]
        ]


class TestOutOfTheRoom:

    @pytest.mark.asyncio
    async def test_a_riser_that_would_be_carried_above_the_ceiling_refuses_the_whole_edit(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, _, _, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        # The room is 5 m high. On a 3.9 m base the stage tops out at 4.8 m, and every fixture is
        # within the 2 m over the ceiling; the riser on it would top out at 5.1 m.
        refused = await client.patch(path, json={"base_height": 3.9})

        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert f"1 raised area standing on {stage['name']} out of the room and the 2 m round it" in detail
        assert f"{DRUM} to " in detail and "above the ceiling" in detail and "Nothing was changed" in detail
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == room == await column(db_session, rig_id)
        assert rig["room_shell_edits"] == ADDED
        assert len((await column(db_session, rig_id, "room_shell_undo"))["steps"]) == 1
        assert await fixtures_by_name(client, rig_id) == before

        # The stage alone may go there.
        alone = await client.patch(path, json={"base_height": 3.9, "carry_fixtures": False})
        assert alone.status_code == 200, alone.text
        assert alone.json()["items_moved"] == []
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_riser_carried_past_the_room_s_margin_refuses_the_whole_edit(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, _, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)
        # Its light is taken off it, so that only the riser itself would be past the margin:
        # 12 m across and 2 m round it is 8 m either side, and the riser is 2 m stage left of the stage's middle.
        lifted = await client.put(
            f"/api/rigs/{rig_id}/fixtures/{before[ON_DRUM]['id']}/position",
            json={"position_x": -5.0, "position_y": 3.0, "position_z": 4.0},
        )
        assert lifted.status_code == 200, lifted.text
        before = await fixtures_by_name(client, rig_id)
        furthest = max(before[name]["position_x"] - stage["center_x"] for name in PARS)
        assert furthest <= 1.5

        refused = await client.patch(path, json={"center_x": 6.4})

        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert f"1 raised area standing on {stage['name']} out of the room" in detail and f"{DRUM} to 8.4" in detail
        assert (await rig_of(client, rig_id))["room_shell"] == room == await column(db_session, rig_id)
        assert (await rig_of(client, rig_id))["room_shell_edits"] == ADDED
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_light_on_the_riser_that_would_leave_the_room_refuses_the_whole_edit(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, _, drum, before = await stack_of(client, sample_rig_data, sample_fixture_data)

        # The riser's middle would be at 7.9 m, inside the margin; its light, 0.3 m further, at 8.2 m.
        refused = await client.patch(path, json={"center_x": 5.9})

        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert f"1 fixture standing on {DRUM} out of the room and the 2 m round it" in detail
        assert f"{ON_DRUM} to " in detail and "Nothing was changed" in detail
        assert (await rig_of(client, rig_id))["room_shell"] == room == await column(db_session, rig_id)
        assert (await rig_of(client, rig_id))["room_shell_edits"] == ADDED
        assert await fixtures_by_name(client, rig_id) == before


class TestUndo:

    @pytest.mark.asyncio
    async def test_one_undo_puts_the_stage_the_riser_and_every_light_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, stage, path, drum_at, _, before = await stack_of(client, sample_rig_data, sample_fixture_data)
        changed = await client.patch(path, json={
            "center_z": stage["center_z"] + 0.5, "width": stage["depth"], "depth": stage["width"], "height": 1.2,
        })
        assert changed.status_code == 200, changed.text
        assert len(changed.json()["items_moved"]) == 1 and len(changed.json()["fixtures_moved"]) == 4
        assert changed.json()["room_shell"]["risers"][drum_at] != room["risers"][drum_at]
        assert await fixtures_by_name(client, rig_id) != before
        label = f"{stage['name']} moved and resized, with 1 raised area and 4 fixtures"

        undone = await client.post(f"/api/rigs/{rig_id}/room-shell/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert answer["undone"] == label
        assert answer["message"] == f"Undone: {label}. 4 fixtures put back where they stood before it."
        assert sorted(entry["name"] for entry in answer["fixtures_restored"]) == sorted(PARS + [ON_DRUM])
        assert answer["fixtures_skipped"] == [] and answer["undo"] == ADDED
        # The riser is where it stood, its marks and all: the whole room is the one before the edit.
        assert answer["room_shell"] == room == await column(db_session, rig_id)
        assert await fixtures_by_name(client, rig_id) == before


class TestLocateWalkthrough:

    @pytest.mark.asyncio
    async def test_no_stack_is_carried_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id, room, stage, path, _, _, before = await stack_of(client, sample_rig_data, sample_fixture_data)
        rig_identify._sessions["room-stack-test"] = rig_identify._Session(
            session_id="room-stack-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for body in (
                {"center_x": stage["center_x"] + 1.0},
                {"height": 1.2, "carry_fixtures": True},
                {"width": stage["depth"], "depth": stage["width"]},
            ):
                refused = await client.patch(path, json=body)
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            assert await fixtures_by_name(client, rig_id) == before
            assert (await rig_of(client, rig_id))["room_shell"] == room
        finally:
            rig_identify._sessions.pop("room-stack-test", None)

        # Once it is over, the stack goes.
        moved = await client.patch(path, json={"center_x": stage["center_x"] + 1.0})
        assert moved.status_code == 200 and len(moved.json()["items_moved"]) == 1


class TestAddingAPlatformOnABase:
    """POST .../room-shell/risers with `base_height`: what the Add form's field sends."""

    BODY = {"center_x": 3.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3}

    @pytest.mark.asyncio
    async def test_it_stands_on_the_floor_with_none_given_and_floats_with_one(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, _, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        path = f"/api/rigs/{rig_id}/room-shell/risers"

        floor = await client.post(path, json=self.BODY)
        assert floor.status_code == 201, floor.text
        assert floor.json()["item"]["base_height"] == 0.0

        floating = await client.post(path, json={**self.BODY, "base_height": 2.7, "riser_kind": "booth"})
        assert floating.status_code == 201, floating.text
        item = floating.json()["item"]
        assert item["base_height"] == 2.7 and item["height"] == 0.3 and item["kind"] == "booth"
        assert item["added_by_hand"] is True
        assert floating.json()["index"] == len(room["risers"]) + 1
        assert (await column(db_session, rig_id))["risers"][-1] == item
        # An added platform moves no fixture.
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_base_that_is_not_a_number_from_nothing_to_ten_metres_under_the_ceiling_adds_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, _, _ = await stage_of(client, sample_rig_data, sample_fixture_data)
        path = f"/api/rigs/{rig_id}/room-shell/risers"

        for wrong in (-0.1, 10.5, 11):
            refused = await client.post(path, json={**self.BODY, "base_height": wrong})
            assert refused.status_code == 422, refused.text
            assert "base height of a raised area must be between 0 m and 10 m" in refused.json()["detail"]
        # JSON has no infinity and no NaN; a client that sends one anyway is refused in a sentence, not with a 500.
        raw_json = {"Content-Type": "application/json"}
        start = b'{"center_x": 3, "center_z": 3, "width": 4, "depth": 2, "height": 0.3, "base_height": '
        for raw in (b"Infinity}", b"-Infinity}", b"NaN}"):
            refused = await client.post(path, content=start + raw, headers=raw_json)
            assert refused.status_code == 422, (raw, refused.text)
            assert "base height must be a number" in refused.json()["detail"], raw
        # The room is 5 m high: a 0.3 m deck on a 4.8 m base would top out above it. The same words as the PATCH's.
        ceiling = await client.post(path, json={**self.BODY, "base_height": 4.8})
        assert ceiling.status_code == 422, ceiling.text
        assert "the ceiling is at 5 m" in ceiling.json()["detail"] and "a base of 4.8 m" in ceiling.json()["detail"]
        truss = await client.post(f"/api/rigs/{rig_id}/room-shell/truss_lines", json={
            "center_x": 0.0, "center_z": 0.0, "length": 4.0, "height": 4.0, "base_height": 1.0,
        })
        assert truss.status_code == 422 and "no base height to set" in truss.json()["detail"]

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == room and rig["room_shell_edits"] == NO_EDITS
