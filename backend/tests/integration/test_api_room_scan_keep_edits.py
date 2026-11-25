"""
Hand edits across a scan applied again (docs/ROOM_SCAN.md, slice 32)
====================================================================

POST /api/rigs/{id}/room-scan over a room a person has corrected in Edit
Room: a name and a height set by hand are kept on the raised area of the new
reading that stands there, whose place and size are the scan's; a raised area
added by hand is kept as it is where the scan has nothing, and replaced where
the scan now has something; `hand_edits` says so in the preview and in
`applied`, and is not sent where there is nothing to say; and a preview
writes nothing.

The test scan's room is 12 x 9 m with a stage at (-1.5, -3.25), 6 x 2.5, and a
riser at (4.5, 2.75), 2 x 1.5.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name
from tests.integration.test_api_room_scan_keep_mark import scan_again
from tests.integration.test_api_room_shell_adjust import column, rig_of
from tests.integration.test_api_room_shell_dj_booth import KEY, marked, room_of

NAMED = " Name set by hand."
# Clear of the stage and the riser; and across the riser's stage-right 0.9 m (0.29 of the two together).
CLEAR = {"name": "Podium", "center_x": -3.0, "center_z": 2.0, "width": 1.5, "depth": 1.5, "height": 0.4}
ACROSS = {"name": "Drum riser", "center_x": 3.4, "center_z": 2.75, "width": 2.0, "depth": 1.5, "height": 0.5}


class TestHandEditsAcrossAScanAppliedAgain:

    @pytest.mark.asyncio
    async def test_a_name_set_by_hand_is_kept(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        # Named, and nudged: the name is the person's to keep, the place is the scan's to read again.
        renamed = await client.patch(f"{room}/risers/{riser_at}", json={
            "name": "Drum riser", "center_x": riser["center_x"] - 0.3, "carry_fixtures": False,
        })
        assert renamed.status_code == 200, renamed.text
        before = await fixtures_by_name(client, rig_id)

        for _ in range(2):
            # The second time over the room the first one stored: the name is still known to be a person's.
            answer = await scan_again(client, rig_id)

            kept = {**riser, "name": "Drum riser", "basis": riser["basis"] + NAMED}
            assert answer["room_shell"]["risers"][riser_at] == kept
            assert answer["room_shell"] == {
                **scanned, "risers": [kept if n == riser_at else area for n, area in enumerate(scanned["risers"])],
            } == await column(db_session, rig_id)
            said = answer["applied"]["hand_edits"]
            assert said["areas"] == 1 and said["added_kept"] == [] and said["added_replaced"] == []
            assert [(entry["index"], entry["name"], entry["edits"]) for entry in said["kept"]] == [
                (riser_at, "Drum riser", ["name"]),
            ]
            assert said["message"] == "Kept your edits on 1 raised area: Drum riser (name)."
        assert "hand_edits" not in answer and await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_height_and_a_base_height_set_by_hand_are_kept(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser, stage = scanned["risers"][riser_at], scanned["risers"][stage_at]
        for at, change in ((riser_at, {"height": 0.45, "base_height": 0.2}), (stage_at, {"height": 1.1})):
            done = await client.patch(f"{room}/risers/{at}", json={**change, "carry_fixtures": False})
            assert done.status_code == 200, done.text

        answer = await scan_again(client, rig_id)

        now = answer["room_shell"]["risers"]
        assert (now[riser_at]["height"], now[riser_at]["base_height"]) == (0.45, 0.2)
        assert now[stage_at]["height"] == 1.1 and now[stage_at]["base_height"] == stage["base_height"]
        for at, was in ((riser_at, riser), (stage_at, stage)):
            # Everything about its footprint and its name is the scan's.
            same = ("center_x", "center_z", "width", "depth", "name", "kind")
            assert {key: now[at][key] for key in same} == {key: was[key] for key in same}
            assert now[at]["suggested"] is False and "Height set by hand." in now[at]["basis"]
        assert "Base height set by hand." in now[riser_at]["basis"]
        assert "Base height set by hand." not in now[stage_at]["basis"]
        assert answer["room_shell"] == await column(db_session, rig_id)
        assert sorted((entry["index"], entry["edits"]) for entry in answer["applied"]["hand_edits"]["kept"]) == sorted([
            (riser_at, ["height", "base_height"]), (stage_at, ["height"]),
        ])
        assert answer["applied"]["hand_edits"]["areas"] == 2

    @pytest.mark.asyncio
    async def test_a_raised_area_added_by_hand_is_kept_where_the_scan_has_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/risers", json=CLEAR)
        assert made.status_code == 201, made.text
        podium, at = made.json()["item"], made.json()["index"]

        for _ in range(2):
            answer = await scan_again(client, rig_id)

            # The scan's own raised areas where they were, and the one added by hand after them, as it was.
            assert answer["room_shell"]["risers"] == [*scanned["risers"], podium]
            assert answer["room_shell"] == await column(db_session, rig_id)
            assert answer["summary"]["raised_areas"] == len(scanned["risers"]) + 1
            assert answer["applied"]["hand_edits"] == {
                "areas": 0, "kept": [], "added_replaced": [],
                "added_kept": [{"index": at, "name": "Podium"}],
                "message": "1 raised area you added was kept as it is: Podium.",
                # Slice 35: the same, one thing at a time.
                "items": [{"kind": "raised area", "name": "Podium", "outcome": "added by hand, kept"}],
            }

    @pytest.mark.asyncio
    async def test_a_raised_area_added_by_hand_is_replaced_where_the_scan_overlaps_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/risers", json=ACROSS)
        assert made.status_code == 201, made.text

        answer = await scan_again(client, rig_id)

        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        assert answer["applied"]["hand_edits"] == {
            "areas": 0, "kept": [], "added_kept": [],
            "added_replaced": [{"name": "Drum riser", "by_index": riser_at, "by": "Riser"}],
            "message": (
                "Drum riser, which you added, was replaced by the scan's Riser: the scan has a raised area there now."
            ),
            # Slice 35: the same, one thing at a time.
            "items": [
                {"kind": "raised area", "name": "Drum riser", "outcome": "replaced (a scanned item overlaps it)"},
            ],
        }
        # Gone, so there is nothing to say at the reading after.
        assert "hand_edits" not in (await scan_again(client, rig_id))["applied"]

    @pytest.mark.asyncio
    async def test_a_marked_booth_added_by_hand_is_kept_with_its_mark(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        made = await client.post(f"{room}/risers", json={**CLEAR, "name": "DJ", "riser_kind": "booth", KEY: True})
        assert made.status_code == 201 and made.json()["dj_booth"] == made.json()["index"]
        at = made.json()["index"]

        answer = await scan_again(client, rig_id)

        applied = answer["applied"]
        assert applied["dj_booth"] == at and applied["dj_booth_dropped"] is False
        assert applied["dj_booth_message"] == "The DJ booth mark was kept on DJ."
        assert applied["hand_edits"]["added_kept"] == [{"index": at, "name": "DJ"}]
        assert marked(await column(db_session, rig_id)) == [at]
        assert answer["room_shell"]["risers"][at] == made.json()["item"]

    @pytest.mark.asyncio
    async def test_nothing_is_carried_and_nothing_said_with_no_hand_edits(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        # A move and a width are edits, but not ones that are kept: the footprint is the scan's.
        moved = await client.patch(f"{room}/risers/{riser_at}", json={
            "center_x": riser["center_x"] - 0.2, "width": 2.2, "carry_fixtures": False,
        })
        assert moved.status_code == 200, moved.text

        preview = await scan_again(client, rig_id, apply=False)
        answer = await scan_again(client, rig_id)

        assert set(preview) == {
            "rig_id", "rig_name", "file", "format", "room_shell", "replaces_existing_shell", "summary",
            "assumptions", "warnings", "fixtures", "operator_guide", "applied",
        }
        assert set(answer["applied"]) == {
            "room_shell_stored", "fixtures_moved", "fixtures_still_unconfirmed", "undo_available", "message",
        }
        assert preview["room_shell"] == answer["room_shell"] == scanned == await column(db_session, rig_id)

    @pytest.mark.asyncio
    async def test_a_preview_says_what_will_be_kept_and_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        await client.patch(f"{room}/risers/{riser_at}", json={"name": "Drum riser", "height": 0.45})
        made = await client.post(f"{room}/risers", json=CLEAR)
        assert made.status_code == 201, made.text
        stored_room = await column(db_session, rig_id)
        undo = await column(db_session, rig_id, "room_shell_undo")
        edits = (await rig_of(client, rig_id))["room_shell_edits"]
        fixtures = await fixtures_by_name(client, rig_id)

        preview = await scan_again(client, rig_id, apply=False)

        assert preview["applied"] is None
        said = preview["hand_edits"]
        assert said["areas"] == 1 and said["added_replaced"] == []
        assert said["kept"] == [{"index": riser_at, "edits": ["name", "height"], "overlap": 1.0, "name": "Drum riser"}]
        assert said["added_kept"] == [{"index": made.json()["index"], "name": "Podium"}]
        assert said["message"] == (
            "Will keep your edits on 1 raised area: Drum riser (name, height). "
            "1 raised area you added will be kept as it is: Podium."
        )
        # The room shown is the one apply would store.
        shown = preview["room_shell"]["risers"]
        assert (shown[riser_at]["name"], shown[riser_at]["height"]) == ("Drum riser", 0.45)
        assert shown[-1] == made.json()["item"] and preview["summary"]["raised_areas"] == len(shown)
        # Nothing written: the room, its undo steps and the fixtures are what they were.
        assert await column(db_session, rig_id) == stored_room
        assert await column(db_session, rig_id, "room_shell_undo") == undo and undo is not None
        assert (await rig_of(client, rig_id))["room_shell_edits"] == edits
        assert await fixtures_by_name(client, rig_id) == fixtures

        # Apply then does what the preview said, to the letter of the room it showed.
        answer = await scan_again(client, rig_id)
        assert answer["room_shell"] == preview["room_shell"] == await column(db_session, rig_id)
        assert "hand_edits" not in answer
        assert {**answer["applied"]["hand_edits"], "message": None} == {**said, "message": None}
