"""
"This one is the DJ's booth", through the API (slice 28)
========================================================

PATCH /api/rigs/{id}/room-shell/risers/{index} with `is_dj_booth` marks one
raised area as the DJ's booth. What has to hold: the mark is stored on the
rig and read back with it; one at a time; a raised area made another kind
loses it unless the same request sets it; a deleted booth takes it along and
one deleted before it leaves it on the right raised area; each change is one
undo step that the room's Undo takes back; no fixture moves; a mark that is
not true or false, or is asked of a truss, is refused in a sentence; and all
of it is refused during a locate walkthrough. docs/ROOM_SCAN.md.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name
from tests.integration.test_api_room_shell_adjust import NO_EDITS, column, rig_of, stored

KEY = "is_dj_booth"


def at(scanned: dict, kind: str) -> int:
    """The place of the first raised area of a kind in the scanned room."""
    return next(n for n, item in enumerate(scanned["risers"]) if item["kind"] == kind)


def marked(shell: dict) -> list:
    """The places of every raised area that carries the mark."""
    return [place for place, item in enumerate(shell["risers"]) if KEY in item]


async def room_of(client, sample_rig_data, sample_fixture_data):
    """(rig id, the scanned room, the stage's place, the riser's place, the path to the room)."""
    rig_id, scanned = await stored(client, sample_rig_data, sample_fixture_data)
    assert marked(scanned) == []
    return rig_id, scanned, at(scanned, "stage"), at(scanned, "riser"), f"/api/rigs/{rig_id}/room-shell"


class TestMarkingTheDjBooth:

    @pytest.mark.asyncio
    async def test_a_raised_area_is_marked_stored_and_read_back_and_nothing_moves(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        stage = scanned["risers"][stage_at]
        before = await fixtures_by_name(client, rig_id)

        response = await client.patch(f"{room}/risers/{stage_at}", json={KEY: True})

        assert response.status_code == 200, response.text
        answer = response.json()
        assert (answer["kind"], answer["index"], answer["dj_booth"]) == ("risers", stage_at, stage_at)
        assert answer["changed"] is True and answer["fixtures_moved"] == [] and answer["items_moved"] == []
        # The mark and nothing else: it is still the scan's own guess of a stage.
        assert answer["item"] == {**stage, KEY: True}
        assert answer["undo"] == {"available": 1, "label": f"{stage['name']} marked as the DJ booth"}
        expected = {
            **scanned,
            "risers": [answer["item"] if n == stage_at else area for n, area in enumerate(scanned["risers"])],
        }
        assert answer["room_shell"] == expected == await column(db_session, rig_id)
        # Read back with the rig, as every other part of the room is.
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == expected and rig["room_shell_edits"]["available"] == 1
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_only_one_at_a_time_and_each_change_is_one_undo_step(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        stage, riser = scanned["risers"][stage_at], scanned["risers"][riser_at]
        assert (await client.patch(f"{room}/risers/{stage_at}", json={KEY: True})).status_code == 200

        moved = await client.patch(f"{room}/risers/{riser_at}", json={KEY: True})

        assert moved.status_code == 200, moved.text
        shell = moved.json()["room_shell"]
        assert moved.json()["dj_booth"] == riser_at and marked(shell) == [riser_at]
        # The stage is the scan's again, to the last key: no false mark is left on it.
        assert shell["risers"][stage_at] == stage and shell["risers"][riser_at] == {**riser, KEY: True}
        assert shell == await column(db_session, rig_id)
        assert moved.json()["undo"] == {"available": 2, "label": f"{riser['name']} marked as the DJ booth"}

        # Marked again, nothing is written and no step is left.
        same = await client.patch(f"{room}/risers/{riser_at}", json={KEY: True})
        assert same.status_code == 200 and same.json()["changed"] is False
        assert same.json()["dj_booth"] == riser_at and same.json()["undo"]["available"] == 2
        # Nor by taking the mark off one that has none.
        none = await client.patch(f"{room}/risers/{stage_at}", json={KEY: False})
        assert none.status_code == 200 and none.json()["changed"] is False and none.json()["dj_booth"] == riser_at

        off = await client.patch(f"{room}/risers/{riser_at}", json={KEY: False})
        assert off.status_code == 200 and off.json()["dj_booth"] is None
        assert off.json()["room_shell"] == scanned
        assert off.json()["undo"] == {"available": 3, "label": f"{riser['name']} no longer marked as the DJ booth"}

        # The room's own Undo walks it back: the riser is the booth, then the stage, then none.
        for label, booth in (
            (f"{riser['name']} no longer marked as the DJ booth", [riser_at]),
            (f"{riser['name']} marked as the DJ booth", [stage_at]),
            (f"{stage['name']} marked as the DJ booth", []),
        ):
            undone = await client.post(f"{room}/undo")
            assert undone.status_code == 200 and undone.json()["undone"] == label
            assert marked(undone.json()["room_shell"]) == booth
            assert undone.json()["fixtures_restored"] == []
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == scanned and rig["room_shell_edits"] == NO_EDITS

    @pytest.mark.asyncio
    async def test_a_raised_area_made_another_kind_loses_the_mark_unless_the_request_sets_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        path = f"{room}/risers/{riser_at}"
        riser = scanned["risers"][riser_at]
        assert riser["name"] == "Riser"
        assert (await client.patch(path, json={KEY: True})).status_code == 200

        made = await client.patch(path, json={"riser_kind": "booth"})

        assert made.status_code == 200, made.text
        assert made.json()["riser_kind"] == "booth" and made.json()["dj_booth"] is None
        assert KEY not in made.json()["item"] and marked(made.json()["room_shell"]) == []
        assert made.json()["undo"]["label"] == "Riser made a booth and no longer marked as the DJ booth"

        # Made a kind and the booth in one request, it is both.
        both = await client.patch(path, json={"riser_kind": "stage", KEY: True})
        assert both.status_code == 200, both.text
        assert both.json()["riser_kind"] == "stage" and both.json()["dj_booth"] == riser_at
        assert both.json()["undo"]["label"] == "Booth or counter made a stage and marked as the DJ booth"
        # And a change of kind that says it is still the booth keeps the mark.
        kept = await client.patch(path, json={"riser_kind": "riser", KEY: True})
        assert kept.status_code == 200, kept.text
        assert kept.json()["riser_kind"] == "riser" and kept.json()["dj_booth"] == riser_at
        assert kept.json()["undo"]["label"] == "Stage made a riser"
        assert marked((await rig_of(client, rig_id))["room_shell"]) == [riser_at]

    @pytest.mark.asyncio
    async def test_a_mark_goes_with_a_move_and_stays_through_later_edits(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        path = f"{room}/risers/{riser_at}"
        riser = scanned["risers"][riser_at]

        together = await client.patch(path, json={"name": "DJ booth", "center_x": riser["center_x"] + 0.25, KEY: True})

        assert together.status_code == 200, together.text
        assert together.json()["item"]["name"] == "DJ booth" and together.json()["item"][KEY] is True
        assert together.json()["undo"]["label"].startswith("Riser renamed, moved and marked as the DJ booth")
        later = await client.patch(path, json={"height": riser["height"] + 0.1, "carry_fixtures": False})
        assert later.status_code == 200 and later.json()["dj_booth"] == riser_at
        assert later.json()["item"][KEY] is True


class TestDeletingAndAdding:

    @pytest.mark.asyncio
    async def test_the_mark_follows_its_raised_area_and_goes_out_with_it(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        marking = await client.patch(f"{room}/risers/{riser_at}", json={KEY: True})
        assert marking.status_code == 200
        is_booth = marking.json()["item"]

        gone = await client.delete(f"{room}/risers/{stage_at}")

        # Whatever came after the stage moved up a place; the booth is still the booth where it now is.
        now_at = riser_at - (1 if stage_at < riser_at else 0)
        assert gone.status_code == 200, gone.text
        assert gone.json()["dj_booth"] == now_at and gone.json()["room_shell"]["risers"][now_at] == is_booth
        assert marked(gone.json()["room_shell"]) == [now_at]

        booth_gone = await client.delete(f"{room}/risers/{now_at}")

        assert booth_gone.status_code == 200, booth_gone.text
        assert booth_gone.json()["removed"] == is_booth and booth_gone.json()["dj_booth"] is None
        # Nothing is promoted in its place.
        assert marked(booth_gone.json()["room_shell"]) == []
        assert marked((await rig_of(client, rig_id))["room_shell"]) == []

        # Undo brings the booth back, marked, and then the stage, with the mark on the right one.
        back = await client.post(f"{room}/undo")
        assert back.status_code == 200 and marked(back.json()["room_shell"]) == [now_at]
        again = await client.post(f"{room}/undo")
        assert again.status_code == 200 and marked(again.json()["room_shell"]) == [riser_at]

    @pytest.mark.asyncio
    async def test_a_booth_added_as_the_djs_takes_the_mark_from_the_one_that_had_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.patch(f"{room}/risers/{stage_at}", json={KEY: True})).status_code == 200
        body = {"center_x": 0.0, "center_z": 1.0, "width": 2.0, "depth": 1.0, "height": 1.0, "riser_kind": "booth"}

        added = await client.post(f"{room}/risers", json={**body, "name": "DJ booth", KEY: True})

        assert added.status_code == 201, added.text
        index = len(scanned["risers"])
        assert added.json()["index"] == index and added.json()["dj_booth"] == index
        assert added.json()["item"][KEY] is True and added.json()["item"]["added_by_hand"] is True
        shell = added.json()["room_shell"]
        assert marked(shell) == [index] and shell["risers"][stage_at] == scanned["risers"][stage_at]
        assert shell == await column(db_session, rig_id)

        # One added without the mark leaves the booth where it is.
        plain = await client.post(f"{room}/risers", json=body)
        assert plain.status_code == 201 and plain.json()["dj_booth"] == index
        assert KEY not in plain.json()["item"]

        truss = await client.post(f"{room}/truss_lines", json={
            "center_x": 0.0, "center_z": 0.0, "length": 4.0, "height": 4.0, KEY: True,
        })
        assert truss.status_code == 422 and "Only a raised area can be the DJ booth" in truss.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_marked_riser_carried_with_the_stage_does_not_keep_a_mark_the_stage_took(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        stage = scanned["risers"][stage_at]
        # A riser standing on the stage (its middle over it, its base at its top), marked as the booth.
        on_stage = await client.post(f"{room}/risers", json={
            "center_x": stage["center_x"], "center_z": stage["center_z"], "width": 1.0, "depth": 1.0,
            "height": 0.3, "base_height": stage["height"], "name": "Drum riser", KEY: True,
        })
        assert on_stage.status_code == 201, on_stage.text
        riser_at = on_stage.json()["index"]

        # Carried with the stage and nothing said of the mark, the riser is still the booth where it went.
        carried = await client.patch(f"{room}/risers/{stage_at}", json={"center_z": stage["center_z"] + 0.25})
        assert carried.status_code == 200, carried.text
        assert riser_at in [entry["index"] for entry in carried.json()["items_moved"]]
        assert carried.json()["dj_booth"] == riser_at and marked(carried.json()["room_shell"]) == [riser_at]
        assert carried.json()["room_shell"]["risers"][riser_at]["center_z"] == pytest.approx(stage["center_z"] + 0.25)
        assert marked((await rig_of(client, rig_id))["room_shell"]) == [riser_at]

        # The stage is moved, which carries the riser, and made the booth in the same request.
        moved = await client.patch(
            f"{room}/risers/{stage_at}", json={"center_x": stage["center_x"] + 0.5, KEY: True},
        )

        assert moved.status_code == 200, moved.text
        assert riser_at in [entry["index"] for entry in moved.json()["items_moved"]]
        shell = moved.json()["room_shell"]
        assert moved.json()["dj_booth"] == stage_at and marked(shell) == [stage_at]
        assert shell["risers"][riser_at]["center_x"] == pytest.approx(stage["center_x"] + 0.5)
        assert marked((await rig_of(client, rig_id))["room_shell"]) == [stage_at]
        # One undo: the riser is the booth again, on the stage where it was.
        undone = await client.post(f"{room}/undo")
        assert undone.status_code == 200 and marked(undone.json()["room_shell"]) == [riser_at]


class TestRefusals:

    @pytest.mark.asyncio
    async def test_a_mark_that_cannot_be_made_is_refused_in_a_sentence_and_nothing_is_stored(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        path = f"{room}/risers/{stage_at}"

        for wrong in ("yes", "true", 1, 0, 2.5, [True], {"a": 1}):
            refused = await client.patch(path, json={KEY: wrong})
            assert refused.status_code == 422, (wrong, refused.text)
            assert "true or false" in refused.json()["detail"], wrong
        # JSON has no infinity; a client that sends one anyway is refused in a sentence, not with a 500.
        raw = await client.patch(path, content=b'{"is_dj_booth": Infinity}', headers={"Content-Type": "application/json"})
        assert raw.status_code == 422 and "true or false" in raw.json()["detail"]

        for kind in ("truss_lines", "truss_rings"):
            if not scanned.get(kind):
                continue
            truss = await client.patch(f"{room}/{kind}/0", json={KEY: True})
            assert truss.status_code == 422, truss.text
            assert "Only a raised area can be the DJ booth" in truss.json()["detail"]
        # It has to be a raised area the room has.
        missing = await client.patch(f"{room}/risers/{len(scanned['risers'])}", json={KEY: True})
        assert missing.status_code == 404 and "has no raised area number" in missing.json()["detail"]
        # A null is nothing asked: with nothing else in the request there is nothing to change.
        nothing = await client.patch(path, json={KEY: None})
        assert nothing.status_code == 422 and "Nothing to change" in nothing.json()["detail"]

        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == scanned and rig["room_shell_edits"] == NO_EDITS

    @pytest.mark.asyncio
    async def test_no_booth_is_marked_under_a_running_locate_walkthrough(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        from app.api.endpoints import rig_identify

        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.patch(f"{room}/risers/{stage_at}", json={KEY: True})).status_code == 200
        shell = (await rig_of(client, rig_id))["room_shell"]

        rig_identify._sessions["room-dj-booth-test"] = rig_identify._Session(
            session_id="room-dj-booth-test", rig_id=rig_id, rig_name="", stage_width=12.0, stage_depth=10.0,
            flash_level=0, steps=[],
        )
        try:
            for request in (
                client.patch(f"{room}/risers/{riser_at}", json={KEY: True}),
                client.patch(f"{room}/risers/{stage_at}", json={KEY: False}),
                # Before the body is looked at: one that would be refused anyway is refused for this first.
                client.patch(f"{room}/risers/{stage_at}", json={KEY: "yes"}),
                client.post(f"{room}/risers", json={
                    "center_x": 0.0, "center_z": 1.0, "width": 2.0, "depth": 1.0, "height": 1.0, KEY: True,
                }),
                client.post(f"{room}/undo"),
            ):
                refused = await request
                assert refused.status_code == 409, refused.text
                assert "locate walkthrough is running" in refused.json()["detail"]
            assert (await rig_of(client, rig_id))["room_shell"] == shell
        finally:
            rig_identify._sessions.pop("room-dj-booth-test", None)
