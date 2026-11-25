"""
The DJ booth mark across a scan applied again (docs/ROOM_SCAN.md, slice 30)
===========================================================================

POST /api/rigs/{id}/room-scan?apply=true over a room with a raised area
marked as the DJ's booth: the new room's raised area of the same kind in the
same place keeps the mark, stored and answered; where none matches the mark
is dropped and `applied` says so; a room nobody marked answers exactly as it
did; a preview writes nothing; and the room's Undo is emptied by the apply as
it always was, so it does not bring a dropped mark back.

Slice 31: the preview says beforehand what apply will do to the mark
(`dj_booth_mark`), still writing nothing, and a kind set by hand on the marked
raised area is kept with the mark, at this reading and the next.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, scan_file, upload
from tests.integration.test_api_room_shell_adjust import NO_EDITS, column, rig_of
from tests.integration.test_api_room_shell_dj_booth import KEY, marked, room_of

MARK_KEYS = {"dj_booth", "dj_booth_dropped", "dj_booth_overlap", "dj_booth_message"}


async def scan_again(client: AsyncClient, rig_id: int, apply: bool = True, **params) -> dict:
    response = await client.post(
        f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()),
        params={"apply": apply, "move_fixtures": False, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestTheMarkAcrossAScanAppliedAgain:

    @pytest.mark.asyncio
    async def test_the_same_scan_applied_again_keeps_the_mark(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        set_mark = await client.patch(f"{room}/risers/{riser_at}", json={KEY: True, "name": "DJ"})
        assert set_mark.status_code == 200 and set_mark.json()["dj_booth"] == riser_at
        before = await fixtures_by_name(client, rig_id)

        answer = await scan_again(client, rig_id)

        applied = answer["applied"]
        assert applied["dj_booth"] == riser_at and applied["dj_booth_dropped"] is False
        assert applied["dj_booth_overlap"] == 1.0
        # The scan's own name for it: only the mark is carried over, not what was typed.
        assert applied["dj_booth_message"] == "The DJ booth mark was kept on Riser."
        # The room is the scan's again, with the mark and nothing else added: answered, stored and read back.
        expected = {
            **scanned,
            "risers": [{**area, KEY: True} if n == riser_at else area for n, area in enumerate(scanned["risers"])],
        }
        assert answer["room_shell"] == expected == await column(db_session, rig_id)
        assert marked(answer["room_shell"]) == [riser_at]
        rig = await rig_of(client, rig_id)
        assert rig["room_shell"] == expected
        # The mark moves no fixture.
        assert await fixtures_by_name(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_booth_nudged_by_hand_is_still_the_same_booth(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        nudged = await client.patch(f"{room}/risers/{riser_at}", json={
            KEY: True, "center_x": riser["center_x"] - 0.3, "carry_fixtures": False,
        })
        assert nudged.status_code == 200, nudged.text

        answer = await scan_again(client, rig_id)

        # 2 m wide and 0.3 m off: 1.7 shared of 2.3 covered.
        assert answer["applied"]["dj_booth"] == riser_at
        assert answer["applied"]["dj_booth_overlap"] == pytest.approx(1.7 / 2.3, abs=1e-3)
        # It stands where the scan has it, not where it was nudged to.
        assert answer["room_shell"]["risers"][riser_at] == {**riser, KEY: True}

    @pytest.mark.asyncio
    async def test_a_booth_the_new_reading_does_not_have_there_drops_the_mark_and_says_so(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        # Marked, then moved by hand to where the scan has nothing of its kind.
        moved = await client.patch(f"{room}/risers/{riser_at}", json={
            KEY: True, "name": "DJ", "center_x": riser["center_x"] - 4.0, "carry_fixtures": False,
        })
        assert moved.status_code == 200 and moved.json()["dj_booth"] == riser_at
        assert moved.json()["item"]["center_x"] == riser["center_x"] - 4.0

        answer = await scan_again(client, rig_id)

        applied = answer["applied"]
        assert applied["dj_booth"] is None and applied["dj_booth_dropped"] is True
        assert applied["dj_booth_overlap"] is None
        assert applied["dj_booth_message"] == (
            "The DJ booth mark was dropped: no raised area in this scan stands where DJ did. "
            "Mark the DJ booth again in Edit Room."
        )
        # Not given to anything else: the room is the scan's own, unmarked.
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)
        assert marked(answer["room_shell"]) == []
        # The sentence that was always there is what it was.
        assert applied["message"] == "The room is stored on the rig as a suggestion. No fixture was moved."

    @pytest.mark.asyncio
    async def test_a_kind_changed_by_hand_keeps_the_mark_and_the_kind(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        # Slice 31. Until then this was dropped (the test was test_a_kind_changed_by_hand_drops_the_mark):
        # the scan calls it a riser again, and the match was on the kind alone.
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        made = await client.patch(f"{room}/risers/{riser_at}", json={KEY: True, "riser_kind": "booth"})
        assert made.status_code == 200 and made.json()["dj_booth"] == riser_at
        by_hand = made.json()["item"]
        assert by_hand["kind"] == "booth" and "Kind set by hand." in by_hand["basis"]

        for _ in range(2):
            # The second time over the room the first one stored: the kind is still known to be a person's.
            answer = await scan_again(client, rig_id)

            applied = answer["applied"]
            assert applied["dj_booth"] == riser_at and applied["dj_booth_dropped"] is False
            assert applied["dj_booth_kind_kept"] == "booth"
            assert applied["dj_booth_message"] == (
                "The DJ booth mark was kept on Booth or counter. It stays a booth, as set by hand: "
                "this scan reads it as a riser."
            )
            # Where and as big as the scan reads it; the kind, and that it was set by hand, the person's.
            kept = answer["room_shell"]["risers"][riser_at]
            assert kept == {
                **riser, "kind": "booth", "name": "Booth or counter", "suggested": False,
                "basis": by_hand["basis"], KEY: True,
            }
            assert answer["room_shell"] == await column(db_session, rig_id)
            assert marked(answer["room_shell"]) == [riser_at]

    @pytest.mark.asyncio
    async def test_a_kind_the_scan_agrees_with_says_nothing_of_the_kind(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        await client.patch(f"{room}/risers/{riser_at}", json={KEY: True})

        answer = await scan_again(client, rig_id)

        assert answer["applied"]["dj_booth"] == riser_at and "dj_booth_kind_kept" not in answer["applied"]

    @pytest.mark.asyncio
    async def test_the_rooms_undo_is_emptied_as_before_and_does_not_bring_a_dropped_mark_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        await client.patch(f"{room}/risers/{riser_at}", json={
            KEY: True, "center_x": riser["center_x"] - 4.0, "carry_fixtures": False,
        })
        assert (await rig_of(client, rig_id))["room_shell_edits"]["available"] == 1

        answer = await scan_again(client, rig_id)
        assert answer["applied"]["dj_booth_dropped"] is True

        # The steps were edits to the room this one replaced.
        assert (await rig_of(client, rig_id))["room_shell_edits"] == NO_EDITS
        assert await column(db_session, rig_id, "room_shell_undo") is None
        peek = await client.get(f"{room}/undo")
        assert peek.status_code == 200 and peek.json()["available"] == 0
        assert marked(await column(db_session, rig_id)) == []

        # A mark that was kept is one the Undo has nothing to say about either, and the next edit is step one.
        again = await client.patch(f"{room}/risers/{stage_at}", json={KEY: True})
        assert again.json()["undo"]["available"] == 1
        kept = await scan_again(client, rig_id)
        assert kept["applied"]["dj_booth"] == stage_at
        assert (await rig_of(client, rig_id))["room_shell_edits"] == NO_EDITS
        assert marked(await column(db_session, rig_id)) == [stage_at]
        # Taking the kept mark off is an edit like any other, and can be undone.
        off = await client.patch(f"{room}/risers/{stage_at}", json={KEY: False})
        assert off.json()["dj_booth"] is None and off.json()["undo"]["available"] == 1
        undone = await client.post(f"{room}/undo")
        assert undone.status_code == 200 and marked(undone.json()["room_shell"]) == [stage_at]

    @pytest.mark.asyncio
    async def test_a_room_nobody_marked_answers_as_it_always_did(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, _ = await room_of(client, sample_rig_data, sample_fixture_data)

        answer = await scan_again(client, rig_id)

        assert not MARK_KEYS & set(answer["applied"])
        assert set(answer["applied"]) == {
            "room_shell_stored", "fixtures_moved", "fixtures_still_unconfirmed", "undo_available", "message",
        }
        assert answer["room_shell"] == scanned == await column(db_session, rig_id)

    @pytest.mark.asyncio
    async def test_a_preview_over_a_marked_room_writes_nothing_and_says_the_mark_will_be_kept(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        # Until slice 31 a preview said nothing of the mark and its room_shell carried none
        # (test_a_preview_over_a_marked_room_writes_nothing_and_says_nothing_of_the_mark). It now
        # shows the room apply would store. What it writes is what it always did: nothing.
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        await client.patch(f"{room}/risers/{riser_at}", json={KEY: True, "name": "DJ"})
        stored_room = await column(db_session, rig_id)
        fixtures = await fixtures_by_name(client, rig_id)

        preview = await scan_again(client, rig_id, apply=False)

        assert preview["applied"] is None
        assert preview["dj_booth_mark"] == {
            "kept": True, "dropped": False, "index": riser_at, "name": "Riser", "overlap": 1.0,
            "kind_kept": None, "message": "The DJ booth mark will be kept on Riser.",
        }
        assert marked(preview["room_shell"]) == [riser_at]
        assert await column(db_session, rig_id) == stored_room and marked(stored_room) == [riser_at]
        assert stored_room["risers"][riser_at]["name"] == "DJ"
        assert (await rig_of(client, rig_id))["room_shell_edits"]["available"] == 1
        assert await fixtures_by_name(client, rig_id) == fixtures

        # Apply then does what the preview said, to the letter of the room it showed.
        answer = await scan_again(client, rig_id)
        assert answer["applied"]["dj_booth"] == preview["dj_booth_mark"]["index"]
        assert answer["room_shell"] == preview["room_shell"]
        assert "dj_booth_mark" not in answer

    @pytest.mark.asyncio
    async def test_a_preview_says_the_mark_will_be_dropped_and_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        riser = scanned["risers"][riser_at]
        await client.patch(f"{room}/risers/{riser_at}", json={
            KEY: True, "name": "DJ", "center_x": riser["center_x"] - 4.0, "carry_fixtures": False,
        })
        stored_room = await column(db_session, rig_id)
        undo = await column(db_session, rig_id, "room_shell_undo")

        preview = await scan_again(client, rig_id, apply=False)

        assert preview["applied"] is None
        assert preview["dj_booth_mark"] == {
            "kept": False, "dropped": True, "index": None, "name": None, "overlap": None, "kind_kept": None,
            "message": (
                "The DJ booth mark will be dropped: no raised area in this scan stands where DJ does. "
                "Mark the DJ booth again in Edit Room after applying."
            ),
        }
        assert preview["room_shell"] == scanned
        # Still marked, still where it was moved to, and the edit still there to be undone.
        assert await column(db_session, rig_id) == stored_room and marked(stored_room) == [riser_at]
        assert await column(db_session, rig_id, "room_shell_undo") == undo and undo is not None

        answer = await scan_again(client, rig_id)
        assert answer["applied"]["dj_booth_dropped"] is True

    @pytest.mark.asyncio
    async def test_a_preview_says_a_kind_set_by_hand_will_be_kept_and_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        await client.patch(f"{room}/risers/{riser_at}", json={KEY: True, "riser_kind": "booth"})
        stored_room = await column(db_session, rig_id)

        preview = await scan_again(client, rig_id, apply=False)

        said = preview["dj_booth_mark"]
        assert (said["kept"], said["index"], said["name"], said["kind_kept"]) == (
            True, riser_at, "Booth or counter", "booth",
        )
        assert said["message"] == (
            "The DJ booth mark will be kept on Booth or counter. It stays a booth, as set by hand: "
            "this scan reads it as a riser."
        )
        # The room shown is the one that would be stored: a booth, not the scan's riser.
        assert preview["room_shell"]["risers"][riser_at]["kind"] == "booth"
        assert await column(db_session, rig_id) == stored_room

    @pytest.mark.asyncio
    async def test_a_preview_over_a_room_nobody_marked_answers_as_it_always_did(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, _ = await room_of(client, sample_rig_data, sample_fixture_data)

        preview = await scan_again(client, rig_id, apply=False)

        assert "dj_booth_mark" not in preview and preview["room_shell"] == scanned
        assert set(preview) == {
            "rig_id", "rig_name", "file", "format", "room_shell", "replaces_existing_shell", "summary",
            "assumptions", "warnings", "fixtures", "operator_guide", "applied",
        }

    @pytest.mark.asyncio
    async def test_a_room_read_a_quarter_turn_round_drops_the_mark(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        await client.patch(f"{room}/risers/{riser_at}", json={KEY: True})

        answer = await scan_again(client, rig_id, rotate=90)

        # Every raised area is somewhere else on the plan now: nothing stands where the booth did.
        assert answer["applied"]["dj_booth_dropped"] is True and marked(answer["room_shell"]) == []
