"""
Raised areas in Edit Room, over HTTP
====================================

PATCH /api/rigs/{id}/room-shell/risers/{index} takes the fixtures standing on
a raised area along when it is moved, raised, resized or given a quarter turn,
unless `carry_fixtures` is false; makes it a stage, a riser or a booth
(`riser_kind`) where it is in its list; and floats it (`base_height`).
POST /api/rigs/{id}/room-shell/undo puts the area and its fixtures back
together. docs/ROOM_SCAN.md, slice 18.

What has to hold: the fixtures standing on it move with it and are listed;
nothing but their position (and, for a quarter turn, their heading) changes,
and no other fixture changes at all; an edit that would carry one out of the
room writes nothing; each change is one undo step; a base height is a finite
number from 0 to 10 m; and it is all refused during a locate walkthrough.

The synthetic room (tests/unit/room_scan_meshes.py) is 12 m by 9 m by 5 m,
with a 6 m by 2.5 m stage 0.9 m high upstage and a small riser. Applying the
scan lifts the three "Par" guesses onto the stage; nothing here drives a
fixture.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, place
from tests.integration.test_api_room_shell_adjust import NO_EDITS, column, rig_of, stored
from tests.integration.test_api_room_shell_carry import PLACE_KEYS, only_these_moved

PARS = ["Par 1", "Par 2", "Par 3"]


def at(scanned: dict, kind: str) -> int:
    """The place of the first raised area of a kind in the scanned room."""
    return next(n for n, item in enumerate(scanned["risers"]) if item["kind"] == kind)


async def stage_of(client, sample_rig_data, sample_fixture_data):
    """(rig id, the scanned room, the stage's place, the stage, the path to it, the fixtures by name)."""
    rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
    index = at(scanned, "stage")
    stage = scanned["risers"][index]
    before = await fixtures_by_name(client, rig_id)
    # The scan lifted the three guesses onto the stage: they stand a little above its top.
    assert all(0.0 <= before[name]["position_y"] - stage["height"] <= 0.6 for name in PARS)
    return rig_id, scanned, index, stage, f"/api/rigs/{rig_id}/room-shell/risers/{index}", before


class TestARaisedAreaCarriesWhatStandsOnIt:

    @pytest.mark.asyncio
    async def test_a_moved_stage_takes_the_row_standing_on_it_and_nothing_else(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, index, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]

        response = await client.patch(
            path, json={"center_x": stage["center_x"] + 1.0, "center_z": stage["center_z"] + 0.5},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        item = answer["item"]
        dx, dz = item["center_x"] - stage["center_x"], item["center_z"] - stage["center_z"]
        assert (dx, dz) == (pytest.approx(1.0, abs=0.001), pytest.approx(0.5, abs=0.001))
        assert answer["carry_fixtures"] is True
        assert sorted(move["name"] for move in answer["fixtures_moved"]) == PARS
        assert answer["message"] == f"3 fixtures standing on {stage['name']} moved with it."
        assert answer["undo"] == {"available": 1, "label": f"{stage['name']} moved, with 3 fixtures"}

        after = await fixtures_by_name(client, rig_id)
        # Their patch, mode, tags, group and heading are what they were; the lights on the truss are untouched.
        only_these_moved(before, after, PARS)
        for move in answer["fixtures_moved"]:
            was, now = before[move["name"]], after[move["name"]]
            assert move["rig_fixture_id"] == was["id"]
            assert place(now) == (
                pytest.approx(was["position_x"] + dx, abs=0.001),
                was["position_y"],
                pytest.approx(was["position_z"] + dz, abs=0.001),
            )
            assert move["from"] == {
                "x": was["position_x"], "y": was["position_y"], "z": was["position_z"], "rotation_y": was["rotation_y"],
            }
            assert (move["to"]["x"], move["to"]["y"], move["to"]["z"]) == place(now)
        # Still guesses: a carried fixture is not confirmed by being carried.
        assert all("position_unconfirmed" in after[name]["tags"] for name in PARS)

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == answer["room_shell"] == await column(db_session, rig_id)
        assert rig["room_scan_undo"] == scan_undo
        step = (await column(db_session, rig_id, "room_shell_undo"))["steps"][-1]
        assert step["shell"] == scanned and step["fixtures"] == answer["fixtures_moved"] and step["kind"] == "risers"

    @pytest.mark.asyncio
    async def test_a_higher_deck_and_a_base_height_raise_them_by_what_the_top_moved(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        higher = await client.patch(path, json={"height": 1.2})

        assert higher.status_code == 200, higher.text
        assert len(higher.json()["fixtures_moved"]) == 3
        assert higher.json()["undo"]["label"] == f"{stage['name']} resized, with 3 fixtures"
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, PARS)
        rise = 1.2 - stage["height"]
        for name in PARS:
            assert place(after[name]) == (
                before[name]["position_x"],
                pytest.approx(before[name]["position_y"] + rise, abs=0.001),
                before[name]["position_z"],
            )

        floated = await client.patch(path, json={"base_height": 1.5})

        assert floated.status_code == 200, floated.text
        answer = floated.json()
        assert answer["item"]["base_height"] == 1.5 and answer["item"]["height"] == 1.2
        assert answer["undo"]["label"] == f"{stage['name']} raised, with 3 fixtures"
        assert len(answer["fixtures_moved"]) == 3
        floating = await fixtures_by_name(client, rig_id)
        only_these_moved(after, floating, PARS)
        for name in PARS:
            assert floating[name]["position_y"] == pytest.approx(after[name]["position_y"] + 1.5, abs=0.001)

        # Back down onto the floor, and they come down with it.
        landed = await client.patch(path, json={"base_height": 0})
        assert landed.status_code == 200 and landed.json()["undo"]["label"] == f"{stage['name']} lowered, with 3 fixtures"
        assert await fixtures_by_name(client, rig_id) == after

    @pytest.mark.asyncio
    async def test_a_resized_stage_keeps_each_at_the_same_share_of_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(path, json={"width": stage["width"] / 2})

        assert response.status_code == 200, response.text
        item = response.json()["item"]
        # Its middle may have been brought in; the fixtures follow the one stored.
        after = await fixtures_by_name(client, rig_id)
        moved = [name for name in PARS if abs(before[name]["position_x"] - stage["center_x"]) > 0.001]
        only_these_moved(before, after, moved)
        for name in PARS:
            assert place(after[name]) == (
                pytest.approx(item["center_x"] + (before[name]["position_x"] - stage["center_x"]) / 2, abs=0.002),
                before[name]["position_y"],
                pytest.approx(before[name]["position_z"], abs=0.002),
            )

    @pytest.mark.asyncio
    async def test_a_quarter_turn_swings_them_about_its_middle_and_turns_them_with_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        assert stage["width"] != stage["depth"]

        # A quarter turn is all the dialog's Turn sends: the width and the depth changed places.
        response = await client.patch(path, json={"width": stage["depth"], "depth": stage["width"]})

        assert response.status_code == 200, response.text
        answer = response.json()
        item = answer["item"]
        assert (item["width"], item["depth"]) == (stage["depth"], stage["width"])
        assert len(answer["fixtures_moved"]) == 3
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, PARS, keys=PLACE_KEYS | {"rotation_y"})
        for name in PARS:
            off_x = before[name]["position_x"] - stage["center_x"]
            off_z = before[name]["position_z"] - stage["center_z"]
            # Clockwise seen from above, as a truss turns: what was stage left of the middle is now downstage of it.
            assert place(after[name]) == (
                pytest.approx(item["center_x"] - off_z, abs=0.002),
                before[name]["position_y"],
                pytest.approx(item["center_z"] + off_x, abs=0.002),
            )
            assert after[name]["rotation_y"] == pytest.approx(before[name]["rotation_y"] - 90.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_a_stage_told_to_go_alone_leaves_every_fixture_where_it_is(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        response = await client.patch(
            path, json={"center_x": 0.0, "height": 1.4, "base_height": 0.5, "carry_fixtures": False},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["changed"] is True and answer["carry_fixtures"] is False and answer["fixtures_moved"] == []
        assert answer["message"] == f"The fixtures standing on {stage['name']} were left where they are, as asked."
        assert answer["undo"]["label"] == f"{stage['name']} moved, resized and raised"
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_light_hung_on_a_truss_over_the_stage_stays_with_its_truss(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        room = f"/api/rigs/{rig_id}/room-shell"
        # A low truss over the stage, 0.3 m above the lights standing on it and right over them.
        row_z = before["Par 1"]["position_z"]
        added = await client.post(f"{room}/truss_lines", json={
            "center_x": stage["center_x"], "center_z": row_z, "length": 5.0, "height": before["Par 1"]["position_y"] + 0.3,
        })
        assert added.status_code == 201, added.text

        response = await client.patch(path, json={"center_z": stage["center_z"] + 0.5})

        assert response.status_code == 200, response.text
        answer = response.json()
        # Within the truss's reach they are the truss's: the stage goes without them.
        assert answer["fixtures_moved"] == []
        assert answer["message"] == "No fixture was moved: none that stands on it had to move."
        assert await fixtures_by_name(client, rig_id) == before


class TestOutOfTheRoom:

    @pytest.mark.asyncio
    async def test_an_edit_that_would_carry_a_fixture_out_of_the_room_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        # 12 m across and 2 m round it: 8 m either side. A plain move holds the stage's middle,
        # so the light standing furthest stage left of it would be past that.
        furthest = max(PARS, key=lambda name: before[name]["position_x"])
        assert before[furthest]["position_x"] - stage["center_x"] > 0.6

        refused = await client.patch(path, json={"center_x": 7.5})

        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert f"standing on {stage['name']} out of the room and the 2 m round it" in detail
        assert f"{furthest} to " in detail and "Nothing was changed" in detail
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == scanned == await column(db_session, rig_id)
        assert rig["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id, "room_shell_undo") is None
        # Not part of the row: nothing at all.
        assert await fixtures_by_name(client, rig_id) == before

        # The stage alone may go there, as it always could.
        alone = await client.patch(path, json={"center_x": 7.5, "carry_fixtures": False})
        assert alone.status_code == 200, alone.text
        assert await fixtures_by_name(client, rig_id) == before


class TestKindChange:

    @pytest.mark.asyncio
    async def test_a_riser_is_made_a_stage_where_it_is_and_the_first_stage_is_answered(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        riser_at = at(scanned, "riser")
        riser = scanned["risers"][riser_at]
        room = f"/api/rigs/{rig_id}/room-shell"

        response = await client.patch(f"{room}/risers/{riser_at}", json={"riser_kind": "stage"})

        assert response.status_code == 200, response.text
        answer = response.json()
        assert (answer["kind"], answer["index"], answer["riser_kind"]) == ("risers", riser_at, "stage")
        assert answer["changed"] is True and answer["fixtures_moved"] == []
        item = answer["item"]
        assert item["kind"] == "stage" and item["suggested"] is False and "Kind set by hand." in item["basis"]
        # Called what the scan called a riser, it is now called what a stage is called.
        assert riser["name"] == "Riser" and item["name"] == "Stage"
        assert answer["undo"] == {"available": 1, "label": "Riser made a stage"}
        # Nothing but that one item changed, and it is where it was in its list.
        expected = {**scanned, "risers": [item if n == riser_at else area for n, area in enumerate(scanned["risers"])]}
        assert answer["room_shell"] == expected == await column(db_session, rig_id)
        # Two stages: the one listed first is still the one a suggestion goes by.
        assert answer["first_stage"] == min(stage_at, riser_at)

        demoted = await client.patch(path, json={"riser_kind": "booth"})

        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["riser_kind"] == "booth" and demoted.json()["index"] == stage_at
        assert demoted.json()["item"]["name"] == "Booth or counter"
        assert demoted.json()["first_stage"] == riser_at
        assert demoted.json()["undo"] == {"available": 2, "label": f"{stage['name']} made a booth"}
        # A kind is not a place: no fixture moved.
        assert await fixtures_by_name(client, rig_id) == before

        # One undo for each, and the room is the scan's again.
        for label in (f"{stage['name']} made a booth", "Riser made a stage"):
            undone = await client.post(f"{room}/undo")
            assert undone.status_code == 200 and undone.json()["undone"] == label
            assert undone.json()["fixtures_restored"] == []
        assert (await rig_of(client, rig_id))["room_shell"] == scanned

    @pytest.mark.asyncio
    async def test_the_kind_it_is_changes_nothing_and_a_kind_that_is_not_one_is_refused(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, path, _ = await stage_of(client, sample_rig_data, sample_fixture_data)

        same = await client.patch(path, json={"riser_kind": "stage"})
        assert same.status_code == 200 and same.json()["changed"] is False and same.json()["undo"] == NO_EDITS

        for body in ({"riser_kind": "balcony"}, {"riser_kind": ""}):
            refused = await client.patch(path, json=body)
            assert refused.status_code == 422, refused.text
            assert "one of: stage, riser, booth" in refused.json()["detail"]
        truss = await client.patch(f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"riser_kind": "stage"})
        assert truss.status_code == 422 and "Only a raised area" in truss.json()["detail"]
        assert (await rig_of(client, rig_id))["room_shell"] == scanned


class TestBaseHeight:

    @pytest.mark.asyncio
    async def test_a_base_height_that_is_not_a_number_from_nothing_to_ten_metres_is_refused(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)

        for wrong in (-0.1, 10.5, 11):
            refused = await client.patch(path, json={"base_height": wrong})
            assert refused.status_code == 422, refused.text
            assert "base height of a raised area must be between 0 m and 10 m" in refused.json()["detail"]
        # JSON has no infinity and no NaN; a client that sends one anyway is refused in a sentence, not with a 500.
        raw_json = {"Content-Type": "application/json"}
        for raw in (b'{"base_height": Infinity}', b'{"base_height": -Infinity}', b'{"base_height": NaN}'):
            refused = await client.patch(path, content=raw, headers=raw_json)
            assert refused.status_code == 422, (raw, refused.text)
            assert "base height must be a number" in refused.json()["detail"], raw
        # The room is 5 m high and the stage 0.9 m: a base of 4.5 m would put its top through the ceiling.
        ceiling = await client.patch(path, json={"base_height": 4.5})
        assert ceiling.status_code == 422 and "the ceiling is at 5 m" in ceiling.json()["detail"]
        truss = await client.patch(f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"base_height": 1.0})
        assert truss.status_code == 422 and "no base height to set" in truss.json()["detail"]

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == scanned and rig["room_shell_edits"] == NO_EDITS
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_platform_is_added_floating_and_a_base_of_nothing_is_no_change(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, path, _ = await stage_of(client, sample_rig_data, sample_fixture_data)

        same = await client.patch(path, json={"base_height": 0})
        assert same.status_code == 200 and same.json()["changed"] is False

        added = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={
            "center_x": 3.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3,
            "base_height": 2.7, "name": "Balcony",
        })
        assert added.status_code == 201, added.text
        assert added.json()["item"]["base_height"] == 2.7 and added.json()["index"] == len(scanned["risers"])
        over = await client.post(f"/api/rigs/{rig_id}/room-shell/risers", json={
            "center_x": 3.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3, "base_height": 12,
        })
        assert over.status_code == 422, over.text


class TestUndo:

    @pytest.mark.asyncio
    async def test_one_undo_puts_the_stage_and_what_stood_on_it_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        room = f"/api/rigs/{rig_id}/room-shell"
        changed = await client.patch(path, json={
            "center_x": stage["center_x"] + 0.5, "width": stage["depth"], "depth": stage["width"],
            "height": 1.2, "base_height": 0.4, "riser_kind": "riser", "name": "Platform",
        })
        assert changed.status_code == 200 and len(changed.json()["fixtures_moved"]) == 3
        assert await fixtures_by_name(client, rig_id) != before
        label = f"{stage['name']} renamed, moved, resized, raised and made a riser, with 3 fixtures"
        assert (await client.get(f"{room}/undo")).json() == {"rig_id": rig_id, "available": 1, "label": label}

        undone = await client.post(f"{room}/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert answer["undone"] == label
        assert answer["message"] == f"Undone: {label}. 3 fixtures put back where they stood before it."
        assert sorted(entry["name"] for entry in answer["fixtures_restored"]) == PARS
        assert answer["fixtures_skipped"] == [] and answer["undo"] == NO_EDITS
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        # Position, height and heading: every fixture is exactly what it was.
        assert await fixtures_by_name(client, rig_id) == before
        assert await column(db_session, rig_id, "room_shell_undo") is None

    @pytest.mark.asyncio
    async def test_a_fixture_moved_since_is_left_where_a_person_put_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, stage, path, before = await stage_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.patch(path, json={"center_z": stage["center_z"] + 0.5})).status_code == 200
        dragged = await client.put(
            f"/api/rigs/{rig_id}/fixtures/{before['Par 2']['id']}/position",
            json={"position_x": 4.0, "position_z": 3.0},
        )
        assert dragged.status_code == 200, dragged.text
        placed = (await fixtures_by_name(client, rig_id))["Par 2"]

        undone = await client.post(f"/api/rigs/{rig_id}/room-shell/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert sorted(entry["name"] for entry in answer["fixtures_restored"]) == ["Par 1", "Par 3"]
        assert answer["fixtures_skipped"] == [
            {"rig_fixture_id": placed["id"], "name": "Par 2", "reason": "it was moved since"},
        ]
        assert answer["message"].endswith(
            "2 fixtures put back where they stood before it. 1 fixture left alone, because it has been moved since."
        )
        assert answer["room_shell"] == scanned
        after = await fixtures_by_name(client, rig_id)
        assert after["Par 2"] == placed
        assert {name: entry for name, entry in after.items() if name != "Par 2"} == {
            name: entry for name, entry in before.items() if name != "Par 2"
        }


class TestLocateWalkthrough:

    @pytest.mark.asyncio
    async def test_no_raised_area_is_changed_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The walkthrough holds its own copy of each position: nothing moves a fixture behind it."""
        from app.api.endpoints import rig_identify

        rig_id, scanned, _, stage, path, _ = await stage_of(client, sample_rig_data, sample_fixture_data)
        room = f"/api/rigs/{rig_id}/room-shell"
        assert (await client.patch(path, json={"center_z": stage["center_z"] + 0.5})).status_code == 200
        before, shell = await fixtures_by_name(client, rig_id), (await rig_of(client, rig_id))["room_shell"]

        rig_identify._sessions["room-raised-test"] = rig_identify._Session(
            session_id="room-raised-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for request in (
                client.patch(path, json={"center_x": 0.0}),
                client.patch(path, json={"height": 1.2, "carry_fixtures": True}),
                client.patch(path, json={"base_height": 1.0, "carry_fixtures": False}),
                # Not even what a raised area is called: every room edit waits for the walkthrough.
                client.patch(path, json={"riser_kind": "booth"}),
                # Before the body is looked at: one that would be refused anyway is refused for this first.
                client.patch(path, json={"base_height": -5}),
                client.post(f"{room}/undo"),
            ):
                refused = await request
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            assert await fixtures_by_name(client, rig_id) == before
            assert (await rig_of(client, rig_id))["room_shell"] == shell
        finally:
            rig_identify._sessions.pop("room-raised-test", None)

        # Once it is over the stage and its row go back together.
        undone = await client.post(f"{room}/undo")
        assert undone.status_code == 200 and len(undone.json()["fixtures_restored"]) == 3
        assert (await rig_of(client, rig_id))["room_shell"] == scanned
