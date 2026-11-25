"""
Overhead lines, deleted raised areas and checks across a scan applied again (docs/ROOM_SCAN.md, slice 33)
=========================================================================================================

POST /api/rigs/{id}/room-scan over a room a person has corrected in Edit
Room: an overhead line keeps a name and a hanging height set by hand, where
and as long as the scan reads it; a line added by hand is kept where the scan
has nothing and replaced where it has a truss; a scanned raised area deleted
by hand is left out of the reading, in a preview (which writes nothing) and
in an apply, until the room's Undo puts it back or the room is taken off the
rig; something kept that the new room does not hold is kept and flagged; and
with none of these both answers have exactly the keys they had.

The test scan's room is 12 x 9 x 5 m with a stage, a riser and one 8 m truss
across it at 4 m.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, scan_file, upload
from tests.integration.test_api_room_scan_keep_mark import scan_again
from tests.integration.test_api_room_shell_adjust import bands_add_up, column, rig_of
from tests.integration.test_api_room_shell_dj_booth import room_of

LINES = "truss_lines"
PREVIEW_KEYS = {
    "rig_id", "rig_name", "file", "format", "room_shell", "replaces_existing_shell", "summary",
    "assumptions", "warnings", "fixtures", "operator_guide", "applied",
}
APPLIED_KEYS = {"room_shell_stored", "fixtures_moved", "fixtures_still_unconfirmed", "undo_available", "message"}
# "items" since slice 35: an answer that kept, left out or replaced something lists it one thing at a time.
AREA_KEYS = {"areas", "kept", "added_kept", "added_replaced", "message", "items"}


def beside(truss: dict, by: float) -> dict:
    """A pipe as long as the scan's truss and `by` metres downstage or upstage of it, whichever is inside the room."""
    z = (truss["z1"] + truss["z2"]) / 2.0
    return {
        "name": "Front pipe", "center_x": (truss["x1"] + truss["x2"]) / 2.0,
        "center_z": z + by if z < 0 else z - by, "length": truss["length"], "height": 3.5,
    }


class TestOverheadLinesAcrossAScanAppliedAgain:

    @pytest.mark.asyncio
    async def test_a_name_and_a_hanging_height_set_by_hand_are_kept(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        truss = scanned[LINES][0]
        # Named, lowered and nudged: the name and the trim are the person's, the place is the scan's.
        done = await client.patch(f"{room}/{LINES}/0", json={
            "name": "Front truss", "height": 3.5, "center_z": (truss["z1"] + truss["z2"]) / 2.0 + 0.1,
            "carry_fixtures": False,
        })
        assert done.status_code == 200, done.text
        before = await fixtures_by_name(client, rig_id)

        for _ in range(2):
            # The second time over the room the first one stored: both are still known to be a person's.
            answer = await scan_again(client, rig_id)

            line = answer["room_shell"][LINES][0]
            assert (line["name"], line["height"]) == ("Front truss", 3.5)
            assert line["top"] == pytest.approx(3.5 + truss["top"] - truss["height"])
            same = ("x1", "z1", "x2", "z2", "length", "across", "axis", "heading_deg")
            assert {key: line[key] for key in same} == {key: truss[key] for key in same}
            assert line["suggested"] is False
            for mark in ("Name set by hand.", "Height set by hand.", "Resized by hand."):
                assert line["basis"].count(mark) == 1
            bands_add_up(answer["room_shell"])
            assert answer["summary"]["hanging_heights"] == [3.5]
            assert answer["room_shell"]["risers"] == scanned["risers"]
            assert answer["room_shell"] == await column(db_session, rig_id)
            said = answer["applied"]["hand_edits"]
            assert set(said) == AREA_KEYS | {"overhead_kept"}
            assert (said["areas"], said["kept"]) == (0, [])
            assert said["overhead_kept"] == [
                {"kind": LINES, "index": 0, "edits": ["name", "height"], "overlap": said["overhead_kept"][0]["overlap"],
                 "name": "Front truss"},
            ]
            assert said["message"] == "Kept your edits on 1 overhead line: Front truss (name, hanging height)."
        assert "hand_edits" not in answer and await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_line_added_by_hand_is_kept_where_the_scan_has_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/{LINES}", json=beside(scanned[LINES][0], 2.0))
        assert made.status_code == 201, made.text
        pipe, at = made.json()["item"], made.json()["index"]

        for _ in range(2):
            answer = await scan_again(client, rig_id)

            assert answer["room_shell"][LINES] == [*scanned[LINES], pipe]
            assert answer["summary"]["overhead_lines"] == 2
            bands_add_up(answer["room_shell"])
            assert answer["room_shell"] == await column(db_session, rig_id)
            said = answer["applied"]["hand_edits"]
            assert said["overhead_added_kept"] == [{"kind": LINES, "index": at, "name": "Front pipe"}]
            assert said["message"] == "1 overhead line you added was kept as it is: Front pipe."
            assert "warnings" not in said and "overhead_added_replaced" not in said

    @pytest.mark.asyncio
    async def test_a_line_added_by_hand_is_replaced_where_the_scan_has_a_truss(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/{LINES}", json=beside(scanned[LINES][0], 0.3))
        assert made.status_code == 201, made.text

        answer = await scan_again(client, rig_id)

        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        said = answer["applied"]["hand_edits"]
        assert said["overhead_added_replaced"] == [
            {"kind": LINES, "name": "Front pipe", "by_index": 0, "by": scanned[LINES][0]["name"]},
        ]
        assert said["message"] == (
            f"Front pipe, which you added, was replaced by the scan's {scanned[LINES][0]['name']}: "
            "the scan has an overhead line there now."
        )
        # Gone, so there is nothing to say at the reading after.
        assert "hand_edits" not in (await scan_again(client, rig_id))["applied"]


class TestARaisedAreaDeletedByHandAcrossAScanAppliedAgain:

    @pytest.mark.asyncio
    async def test_it_is_left_out_and_reported_in_a_preview_that_writes_nothing_and_in_each_apply(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        gone = await client.delete(f"{room}/risers/{riser_at}")
        assert gone.status_code == 200, gone.text
        riser = scanned["risers"][riser_at]
        record = {key: riser[key] for key in ("kind", "name", "center_x", "center_z", "width", "depth")}
        stored_room = await column(db_session, rig_id)
        assert stored_room["deleted_areas"] == [record] == gone.json()["room_shell"]["deleted_areas"]
        # Another edit made afterwards keeps the record: it is part of the room.
        named = await client.patch(f"{room}/risers/0", json={"name": "Main stage"})
        assert named.status_code == 200 and named.json()["room_shell"]["deleted_areas"] == [record]
        # So does a change to the walls.
        raised = await client.patch(f"{room}/outline", json={"height": scanned["room"]["height"] + 0.5})
        assert raised.status_code == 200, raised.text
        stored_room = await column(db_session, rig_id)
        undo = await column(db_session, rig_id, "room_shell_undo")
        fixtures = await fixtures_by_name(client, rig_id)

        preview = await scan_again(client, rig_id, apply=False)

        assert preview["applied"] is None
        said = preview["hand_edits"]
        assert said["deleted_left_out"] == [{"name": "Riser", "kind": "riser", "overlap": 1.0}]
        assert said["message"] == (
            "Will leave out 1 raised area you deleted: Riser. Will keep your edits on 1 raised area: Main stage (name)."
        )
        left = [area for place, area in enumerate(scanned["risers"]) if place != riser_at]
        assert [area["center_x"] for area in preview["room_shell"]["risers"]] == [area["center_x"] for area in left]
        assert preview["summary"]["raised_areas"] == len(scanned["risers"]) - 1
        # Nothing written: the room, its undo steps and the fixtures are what they were.
        assert await column(db_session, rig_id) == stored_room
        assert await column(db_session, rig_id, "room_shell_undo") == undo and undo is not None
        assert await fixtures_by_name(client, rig_id) == fixtures

        for _ in range(2):
            # And at the reading after: the record went on to the new room.
            answer = await scan_again(client, rig_id)

            assert answer["room_shell"] == preview["room_shell"] == await column(db_session, rig_id)
            assert answer["room_shell"]["deleted_areas"] == [record]
            assert len(answer["room_shell"]["risers"]) == len(scanned["risers"]) - 1
            done = answer["applied"]["hand_edits"]
            assert done["deleted_left_out"] == said["deleted_left_out"]
            assert done["message"].startswith("Left out 1 raised area you deleted: Riser.")
        assert (await rig_of(client, rig_id))["room_shell"]["deleted_areas"] == [record]

    @pytest.mark.asyncio
    async def test_the_rooms_undo_putting_it_back_forgets_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.delete(f"{room}/risers/{riser_at}")).status_code == 200
        assert "deleted_areas" in await column(db_session, rig_id)

        undone = await client.post(f"{room}/undo")

        assert undone.status_code == 200, undone.text
        assert undone.json()["room_shell"] == scanned == await column(db_session, rig_id)
        answer = await scan_again(client, rig_id)
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        assert set(answer["applied"]) == APPLIED_KEYS

    @pytest.mark.asyncio
    async def test_a_room_read_from_scratch_has_it_again(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.delete(f"{room}/risers/{riser_at}")).status_code == 200
        assert (await client.delete(room)).status_code == 200

        answer = await scan_again(client, rig_id)

        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        assert set(answer["applied"]) == APPLIED_KEYS

    @pytest.mark.asyncio
    async def test_one_added_by_hand_and_deleted_leaves_nothing_behind(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        # Until slice 34 this also deleted the scan's line and saw it come back: that is now
        # TestAnOverheadLineDeletedByHandAcrossAScanAppliedAgain, below.
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/risers", json={
            "name": "Podium", "center_x": -3.0, "center_z": 2.0, "width": 1.5, "depth": 1.5, "height": 0.4,
        })
        pipe = await client.post(f"{room}/{LINES}", json=beside(scanned[LINES][0], 2.0))
        assert made.status_code == 201 and pipe.status_code == 201, (made.text, pipe.text)
        assert (await client.delete(f"{room}/{LINES}/{pipe.json()['index']}")).status_code == 200
        assert (await client.delete(f"{room}/risers/{made.json()['index']}")).status_code == 200
        assert "deleted_areas" not in await column(db_session, rig_id)

        preview = await scan_again(client, rig_id, apply=False)
        answer = await scan_again(client, rig_id)

        # With nothing kept, left out or flagged both answers have exactly the keys they had.
        assert set(preview) == PREVIEW_KEYS and set(answer["applied"]) == APPLIED_KEYS
        assert preview["room_shell"] == answer["room_shell"] == scanned == await column(db_session, rig_id)


class TestAnOverheadLineDeletedByHandAcrossAScanAppliedAgain:
    """Slice 34: the scan's truss, deleted in Edit Room, stays out of a scan applied again."""

    @pytest.mark.asyncio
    async def test_it_is_left_out_and_reported_in_a_preview_that_writes_nothing_and_in_each_apply(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        truss = scanned[LINES][0]
        gone = await client.delete(f"{room}/{LINES}/0")
        assert gone.status_code == 200, gone.text
        record = {key: truss[key] for key in ("name", "x1", "z1", "x2", "z2", "across", "height")}
        stored_room = await column(db_session, rig_id)
        assert stored_room["deleted_areas"] == [record] == gone.json()["room_shell"]["deleted_areas"]

        preview = await scan_again(client, rig_id, apply=False)

        assert preview["applied"] is None
        said = preview["hand_edits"]
        assert said["deleted_left_out"] == [{"name": truss["name"], "kind": LINES, "overlap": 1.0}]
        assert said["message"] == f"Will leave out 1 overhead line you deleted: {truss['name']}."
        assert set(said) == AREA_KEYS | {"deleted_left_out"}
        assert preview["room_shell"][LINES] == [] and preview["room_shell"]["hanging_bands"] == []
        assert preview["summary"]["overhead_lines"] == 0
        assert await column(db_session, rig_id) == stored_room

        for _ in range(2):
            # And at the reading after: the record went on to the new room.
            answer = await scan_again(client, rig_id)

            assert answer["room_shell"] == preview["room_shell"] == await column(db_session, rig_id)
            assert answer["room_shell"]["deleted_areas"] == [record]
            assert answer["room_shell"]["risers"] == scanned["risers"]
            done = answer["applied"]["hand_edits"]
            assert done["deleted_left_out"] == said["deleted_left_out"]
            assert done["message"] == f"Left out 1 overhead line you deleted: {truss['name']}."

    @pytest.mark.asyncio
    async def test_the_rooms_undo_putting_it_back_forgets_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await client.delete(f"{room}/{LINES}/0")).status_code == 200

        undone = await client.post(f"{room}/undo")

        assert undone.status_code == 200, undone.text
        assert undone.json()["room_shell"] == scanned
        answer = await scan_again(client, rig_id)
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        assert set(answer["applied"]) == APPLIED_KEYS


class TestWhatTheNewRoomDoesNotHoldIsFlagged:

    @pytest.mark.asyncio
    async def test_a_kept_trim_above_the_new_ceiling_and_an_area_outside_the_new_walls(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        podium = await client.post(f"{room}/risers", json={
            "name": "Podium", "center_x": -5.0, "center_z": 3.5, "width": 1.0, "depth": 1.0, "height": 0.4,
        })
        pipe = await client.post(f"{room}/{LINES}", json={
            "name": "Back pipe", "center_x": 0.0, "center_z": 4.0, "length": 3.0, "height": 4.0,
        })
        assert podium.status_code == 201 and pipe.status_code == 201, (podium.text, pipe.text)

        # The same room read at half the size: 6 x 4.5 m, and 2.5 m to the ceiling.
        async def half_size(apply: bool) -> dict:
            response = await client.post(
                f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file(units_per_metre=50.0)),
                params={"apply": apply, "move_fixtures": False, "units": "cm"},
            )
            assert response.status_code == 200, response.text
            return response.json()

        preview = await half_size(False)
        answer = await half_size(True)

        room_now = answer["room_shell"]
        assert room_now["room"]["height"] == pytest.approx(scanned["room"]["height"] / 2.0, abs=0.05)
        # Both are kept as they were.
        assert room_now["risers"][-1] == podium.json()["item"] and room_now[LINES][-1] == pipe.json()["item"]
        said = answer["applied"]["hand_edits"]
        assert said["warnings"] == preview["hand_edits"]["warnings"] == [
            {"kind": "risers", "index": len(room_now["risers"]) - 1, "reason": "outside the walls", "name": "Podium"},
            {"kind": LINES, "index": len(room_now[LINES]) - 1, "reason": "outside the walls and above the ceiling",
             "name": "Back pipe"},
        ]
        assert said["message"].endswith(
            "Check Podium: it is outside the walls of the room as this scan reads it. "
            "Check Back pipe: it is outside the walls and above the ceiling of the room as this scan reads it."
        )
        assert room_now == await column(db_session, rig_id)
