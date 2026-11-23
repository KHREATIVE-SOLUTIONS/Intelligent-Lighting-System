"""
Fixtures that follow their truss, over HTTP
===========================================

PATCH /api/rigs/{id}/room-shell/{kind}/{index} takes the fixtures hung on a
truss line or ring along when it is moved, raised, turned or resized, unless
`carry_fixtures` is false; POST /api/rigs/{id}/room-shell/undo puts the truss
and its fixtures back together. docs/ROOM_SCAN.md, slice 17.

What has to hold: the fixtures hung on it move with it and are listed; nothing
but their position (and, for a turn, their heading) changes, and no other
fixture changes at all; `carry_fixtures` false moves the truss alone; an edit
that would carry one out of the room writes nothing; the truss and its
fixtures are one undo step; and it is all refused during a locate walkthrough.

The synthetic room (tests/unit/room_scan_meshes.py) is 12 m by 9 m by 5 m with
one 8 m truss across it at 4 m. Applying the scan hangs the four "Spot"
guesses under it; nothing here drives a fixture.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import LIGHTS, fixtures_by_name, light, place
from tests.integration.test_api_room_shell_adjust import NO_EDITS, column, rig_of, stored

SPOTS = ["Spot 1", "Spot 2", "Spot 3", "Spot 4"]
PLACE_KEYS = {"position_x", "position_y", "position_z"}

# A ring is added by hand in these tests, with lights a person placed already hanging round it:
# three on it, one 0.2 m inside it. Their tags say a person put them there, so the scan leaves them.
RING = {"center_x": 0.0, "center_z": -2.0, "radius": 1.0, "height": 2.5}
RING_LIGHTS = [
    light("Ring 1", 301, 1.0, 2.5, -2.0, "Ring", tags=["position_source:tap"]),
    light("Ring 2", 317, 0.0, 2.5, -1.0, "Ring", tags=["position_source:tap"]),
    light("Ring 3", 333, -1.0, 2.3, -2.0, "Ring", tags=["position_source:tap"]),
    light("Ring 4", 349, 0.8, 2.5, -2.0, "Ring", tags=["position_source:tap"]),
]


def middle(line: dict) -> tuple:
    return (line["x1"] + line["x2"]) / 2, (line["z1"] + line["z2"]) / 2


def apart_from(entry: dict, keys) -> dict:
    return {key: value for key, value in entry.items() if key not in keys}


def only_these_moved(before: dict, after: dict, names, keys=PLACE_KEYS) -> None:
    """Nothing about any fixture changed but the position (or `keys`) of the ones named."""
    assert before.keys() == after.keys()
    for name in before:
        if name in names:
            assert apart_from(after[name], keys) == apart_from(before[name], keys), name
            assert place(after[name]) != place(before[name]) or keys != PLACE_KEYS, name
        else:
            assert after[name] == before[name], name


class TestALineCarriesItsFixtures:

    @pytest.mark.asyncio
    async def test_a_moved_truss_takes_the_row_hung_on_it_and_nothing_else(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        scan_undo = (await rig_of(client, rig_id))["room_scan_undo"]
        line = scanned["truss_lines"][0]
        was_x, was_z = middle(line)
        # The scan hung the four guesses under the truss; the tapped and confirmed lights of the group stayed at 6 m.
        assert all(before[name]["position_y"] == pytest.approx(line["height"], abs=0.6) for name in SPOTS)

        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"center_x": was_x + 1.0, "center_z": 2.0},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        now_x, now_z = middle(answer["item"])
        assert (now_x, now_z) == (pytest.approx(was_x + 1.0, abs=0.001), pytest.approx(2.0, abs=0.001))
        assert answer["carry_fixtures"] is True
        assert sorted(move["name"] for move in answer["fixtures_moved"]) == SPOTS
        assert answer["message"] == f"4 fixtures hung on {line['name']} moved with it."
        assert answer["undo"] == {"available": 1, "label": f"{line['name']} moved, with 4 fixtures"}

        after = await fixtures_by_name(client, rig_id)
        # Their patch, mode, tags, group and heading are what they were; the other seven lights are untouched.
        only_these_moved(before, after, SPOTS)
        for move in answer["fixtures_moved"]:
            was, now = before[move["name"]], after[move["name"]]
            assert move["rig_fixture_id"] == was["id"]
            assert place(now) == (
                pytest.approx(was["position_x"] + (now_x - was_x), abs=0.001),
                was["position_y"],
                pytest.approx(was["position_z"] + (now_z - was_z), abs=0.001),
            )
            assert move["from"] == {
                "x": was["position_x"], "y": was["position_y"], "z": was["position_z"], "rotation_y": was["rotation_y"],
            }
            assert (move["to"]["x"], move["to"]["y"], move["to"]["z"]) == place(now)
        # Still guesses: a carried fixture is not confirmed by being carried.
        assert all("position_unconfirmed" in after[name]["tags"] for name in SPOTS)

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == answer["room_shell"] == await column(db_session, rig_id)
        assert rig["room_scan_undo"] == scan_undo
        step = (await column(db_session, rig_id, "room_shell_undo"))["steps"][-1]
        assert step["shell"] == scanned and step["fixtures"] == answer["fixtures_moved"]

    @pytest.mark.asyncio
    async def test_a_raised_truss_keeps_each_fixture_as_far_under_it_as_it_hung(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        line = scanned["truss_lines"][0]

        response = await client.patch(f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"height": 3.2})

        assert response.status_code == 200, response.text
        assert len(response.json()["fixtures_moved"]) == 4
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, SPOTS)
        for name in SPOTS:
            assert place(after[name]) == (
                before[name]["position_x"],
                pytest.approx(before[name]["position_y"] + (3.2 - line["height"]), abs=0.001),
                before[name]["position_z"],
            )

    @pytest.mark.asyncio
    async def test_a_turned_truss_swings_its_fixtures_about_its_middle_and_turns_them_with_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        mid_x, mid_z = middle(scanned["truss_lines"][0])

        response = await client.patch(f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"heading_deg": 90})

        assert response.status_code == 200, response.text
        assert response.json()["undo"]["label"].endswith("turned, with 4 fixtures")
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, SPOTS, keys=PLACE_KEYS | {"rotation_y"})
        for name in SPOTS:
            off_x, off_z = before[name]["position_x"] - mid_x, before[name]["position_z"] - mid_z
            # A quarter turn clockwise seen from above: what was stage left of the middle is now downstage of it.
            assert place(after[name]) == (
                pytest.approx(mid_x - off_z, abs=0.002),
                before[name]["position_y"],
                pytest.approx(mid_z + off_x, abs=0.002),
            )
            assert after[name]["rotation_y"] == pytest.approx(before[name]["rotation_y"] - 90.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_a_shortened_truss_closes_its_fixtures_up_along_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        line = scanned["truss_lines"][0]
        mid_x, _ = middle(line)

        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"length": line["length"] / 2},
        )

        assert response.status_code == 200, response.text
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, SPOTS)
        for name in SPOTS:
            # The truss runs across the room: half as long, each is half as far from its middle.
            assert place(after[name]) == (
                pytest.approx(mid_x + (before[name]["position_x"] - mid_x) / 2, abs=0.002),
                before[name]["position_y"],
                pytest.approx(before[name]["position_z"], abs=0.002),
            )

    @pytest.mark.asyncio
    async def test_a_truss_told_to_go_alone_leaves_every_fixture_where_it_is(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        name = scanned["truss_lines"][0]["name"]

        response = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/truss_lines/0",
            json={"center_z": 2.0, "height": 3.0, "heading_deg": 30, "carry_fixtures": False},
        )

        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["changed"] is True and answer["carry_fixtures"] is False and answer["fixtures_moved"] == []
        assert answer["message"] == f"The fixtures hung on {name} were left where they are, as asked."
        assert answer["undo"]["label"] == f"{name} moved, resized and turned"
        assert await fixtures_by_name(client, rig_id) == before
        # A null is the default, not a no.
        again = await client.patch(
            f"/api/rigs/{rig_id}/room-shell/truss_lines/0", json={"center_z": 0.5, "carry_fixtures": None},
        )
        assert again.status_code == 200 and again.json()["carry_fixtures"] is True

    @pytest.mark.asyncio
    async def test_a_rename_a_raised_area_and_no_change_carry_nothing(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        path = f"/api/rigs/{rig_id}/room-shell"
        line = scanned["truss_lines"][0]

        renamed = await client.patch(f"{path}/truss_lines/0", json={"name": "Front truss"})
        assert renamed.status_code == 200 and renamed.json()["fixtures_moved"] == []
        assert renamed.json()["undo"]["label"] == f"{line['name']} renamed"
        # Since slice 18 a raised area takes what stands on it (test_api_room_shell_raised.py); told not to, it goes alone.
        riser = await client.patch(f"{path}/risers/0", json={"center_x": 0.5, "height": 1.2, "carry_fixtures": False})
        assert riser.status_code == 200 and riser.json()["fixtures_moved"] == []
        assert riser.json()["message"] == (
            f"The fixtures standing on {scanned['risers'][0]['name']} were left where they are, as asked."
        )
        kind = await client.patch(f"{path}/risers/0", json={"riser_kind": "booth"})
        assert kind.status_code == 200 and kind.json()["fixtures_moved"] == []
        same = await client.patch(f"{path}/truss_lines/0", json={"height": line["height"]})
        assert same.status_code == 200 and same.json()["changed"] is False and same.json()["fixtures_moved"] == []
        # The flag alone is not a change.
        nothing = await client.patch(f"{path}/truss_lines/0", json={"carry_fixtures": True})
        assert nothing.status_code == 422 and "Nothing to change" in nothing.json()["detail"]
        assert await fixtures_by_name(client, rig_id) == before


class TestARingCarriesItsFixtures:

    @pytest.mark.asyncio
    async def test_a_ring_made_bigger_moved_and_raised_takes_its_fixtures(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _ = await stored(client, sample_rig_data, sample_fixture_data, lights=LIGHTS + RING_LIGHTS)
        path = f"/api/rigs/{rig_id}/room-shell"
        added = await client.post(f"{path}/truss_rings", json=RING)
        assert added.status_code == 201, added.text
        before = await fixtures_by_name(client, rig_id)
        names = [spec["name"] for spec in RING_LIGHTS]

        grown = await client.patch(f"{path}/truss_rings/0", json={"radius": 2.0})

        assert grown.status_code == 200, grown.text
        assert sorted(move["name"] for move in grown.json()["fixtures_moved"]) == names
        assert grown.json()["undo"]["label"] == "Overhead ring 1 resized, with 4 fixtures"
        after = await fixtures_by_name(client, rig_id)
        only_these_moved(before, after, names)
        # Each keeps its angle round the ring, its height, and how far inside the truss it hung.
        assert [place(after[name]) for name in names] == [
            (2.0, 2.5, -2.0), (0.0, 2.5, 0.0), (-2.0, 2.3, -2.0), (1.8, 2.5, -2.0),
        ]
        # A person placed these: carried, they are still a person's.
        assert all(after[name]["tags"] == ["position_source:tap"] for name in names)

        shifted = await client.patch(f"{path}/truss_rings/0", json={"center_x": 1.0, "center_z": -1.5, "height": 3.0})

        assert shifted.status_code == 200, shifted.text
        assert len(shifted.json()["fixtures_moved"]) == 4
        moved = await fixtures_by_name(client, rig_id)
        only_these_moved(after, moved, names)
        assert [place(moved[name]) for name in names] == [
            (3.0, 3.0, -1.5), (1.0, 3.0, 0.5), (-1.0, 2.8, -1.5), (2.8, 3.0, -1.5),
        ]

        # Two undos: the ring and its lights go back a step at a time, to exactly where they were.
        for expected in (after, before):
            undone = await client.post(f"{path}/undo")
            assert undone.status_code == 200 and len(undone.json()["fixtures_restored"]) == 4
            assert await fixtures_by_name(client, rig_id) == expected


class TestOutOfTheRoom:

    @pytest.mark.asyncio
    async def test_an_edit_that_would_carry_a_fixture_out_of_the_room_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        path = f"/api/rigs/{rig_id}/room-shell/truss_lines/0"
        name = scanned["truss_lines"][0]["name"]

        # 12 m across and 2 m round it: 8 m either side. A plain move holds the truss's middle,
        # so its stage-left end, and the lights hung there, would be past that.
        refused = await client.patch(path, json={"center_x": 7.5})

        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert f"hung on {name} out of the room and the 2 m round it" in detail
        assert "Spot 4 to " in detail and "Nothing was changed" in detail
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == scanned == await column(db_session, rig_id)
        assert rig["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id, "room_shell_undo") is None
        # Not half the row: nothing at all.
        assert await fixtures_by_name(client, rig_id) == before

        # The truss alone may go there, as it always could.
        alone = await client.patch(path, json={"center_x": 7.5, "carry_fixtures": False})
        assert alone.status_code == 200, alone.text
        assert await fixtures_by_name(client, rig_id) == before


class TestUndo:

    @pytest.mark.asyncio
    async def test_one_undo_puts_the_truss_and_its_fixtures_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        path = f"/api/rigs/{rig_id}/room-shell"
        name = scanned["truss_lines"][0]["name"]
        changed = await client.patch(
            f"{path}/truss_lines/0", json={"center_z": 2.0, "height": 3.4, "heading_deg": 40, "length": 6.0},
        )
        assert changed.status_code == 200 and len(changed.json()["fixtures_moved"]) == 4
        assert await fixtures_by_name(client, rig_id) != before
        label = f"{name} moved, resized and turned, with 4 fixtures"
        assert (await client.get(f"{path}/undo")).json() == {"rig_id": rig_id, "available": 1, "label": label}

        undone = await client.post(f"{path}/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert answer["undone"] == label
        assert answer["message"] == f"Undone: {label}. 4 fixtures put back where they hung before it."
        assert sorted(entry["name"] for entry in answer["fixtures_restored"]) == SPOTS
        assert answer["fixtures_skipped"] == [] and answer["undo"] == NO_EDITS
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        # Position, height and heading: every fixture is exactly what it was.
        assert await fixtures_by_name(client, rig_id) == before
        assert await column(db_session, rig_id, "room_shell_undo") is None

    @pytest.mark.asyncio
    async def test_a_fixture_moved_since_is_left_where_a_person_put_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        before = await fixtures_by_name(client, rig_id)
        path = f"/api/rigs/{rig_id}/room-shell"
        assert (await client.patch(f"{path}/truss_lines/0", json={"center_z": 2.0})).status_code == 200
        dragged = await client.put(
            f"/api/rigs/{rig_id}/fixtures/{before['Spot 2']['id']}/position",
            json={"position_x": -5.0, "position_z": 3.5},
        )
        assert dragged.status_code == 200, dragged.text
        placed = (await fixtures_by_name(client, rig_id))["Spot 2"]

        undone = await client.post(f"{path}/undo")

        assert undone.status_code == 200, undone.text
        answer = undone.json()
        assert sorted(entry["name"] for entry in answer["fixtures_restored"]) == ["Spot 1", "Spot 3", "Spot 4"]
        assert answer["fixtures_skipped"] == [
            {"rig_fixture_id": placed["id"], "name": "Spot 2", "reason": "it was moved since"},
        ]
        assert answer["message"].endswith(
            "3 fixtures put back where they hung before it. 1 fixture left alone, because it has been moved since."
        )
        assert answer["room_shell"] == scanned
        after = await fixtures_by_name(client, rig_id)
        assert after["Spot 2"] == placed
        assert {name: entry for name, entry in after.items() if name != "Spot 2"} == {
            name: entry for name, entry in before.items() if name != "Spot 2"
        }


class TestLocateWalkthrough:

    @pytest.mark.asyncio
    async def test_no_truss_carries_its_fixtures_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The walkthrough holds its own copy of each position: nothing moves a fixture behind it."""
        from app.api.endpoints import rig_identify

        rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
        path = f"/api/rigs/{rig_id}/room-shell"
        assert (await client.patch(f"{path}/truss_lines/0", json={"center_z": 2.0})).status_code == 200
        before, shell = await fixtures_by_name(client, rig_id), (await rig_of(client, rig_id))["room_shell"]

        rig_identify._sessions["room-carry-test"] = rig_identify._Session(
            session_id="room-carry-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for request in (
                client.patch(f"{path}/truss_lines/0", json={"center_z": 1.0}),
                client.patch(f"{path}/truss_lines/0", json={"height": 3.0, "carry_fixtures": True}),
                client.patch(f"{path}/truss_lines/0", json={"heading_deg": 45, "carry_fixtures": False}),
                # The undo would put the row back: that is a move behind the walkthrough as well.
                client.post(f"{path}/undo"),
            ):
                refused = await request
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            assert await fixtures_by_name(client, rig_id) == before
            assert (await rig_of(client, rig_id))["room_shell"] == shell
        finally:
            rig_identify._sessions.pop("room-carry-test", None)

        # Once it is over the truss and its row go back together.
        undone = await client.post(f"{path}/undo")
        assert undone.status_code == 200 and len(undone.json()["fixtures_restored"]) == 4
        assert (await rig_of(client, rig_id))["room_shell"] == scanned
