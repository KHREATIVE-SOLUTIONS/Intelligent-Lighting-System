"""
Carrying a lost name and trim over onto the truss the scan read in its place (docs/ROOM_SCAN.md, slice 36)
=========================================================================================================

POST /api/rigs/{id}/room-scan/carry-over takes one entry of an applied scan's
`hand_edits.carry_over` as it is and puts the old name and trim onto the new
item, marked as set by hand, as one step of the room's Undo. A stale entry
(the room changed since) is refused with a 409 and writes nothing.

The readings are the test room (tests/unit/room_scan_meshes.py) with its truss
hung lower, made in the test: nothing is sent anywhere.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name
from tests.integration.test_api_room_scan_keep_named import read, reading
from tests.integration.test_api_room_scan_keep_overhead import LINES
from tests.integration.test_api_room_shell_adjust import bands_add_up, column
from tests.integration.test_api_room_shell_dj_booth import room_of
from tests.unit.room_scan_meshes import TRUSS


def carry_path(rig_id: int) -> str:
    return f"/api/rigs/{rig_id}/room-scan/carry-over"


async def lost_trim(client: AsyncClient, sample_rig_data, sample_fixture_data):
    """A room whose truss was named and trimmed by hand, then scanned again read 1.2 m lower."""
    rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
    done = await client.patch(f"{room}/{LINES}/0", json={"name": "Front truss", "height": 3.5, "carry_fixtures": False})
    assert done.status_code == 200, done.text
    lowered = reading(truss_bottom=TRUSS["bottom"] - 1.2)
    answer = await read(client, rig_id, lowered)
    [entry] = answer["applied"]["hand_edits"]["carry_over"]
    return rig_id, room, lowered, answer, entry


class TestCarryingOver:

    @pytest.mark.asyncio
    async def test_the_entry_as_given_puts_the_name_and_trim_back_and_marks_them(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, lowered, answer, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        scanned_line = answer["room_shell"][LINES][0]
        assert (entry["kind"], entry["old_name"], entry["old_trim_or_height"], entry["new_index"]) == (
            LINES, "Front truss", 3.5, 0,
        )
        assert entry["new_name"] == scanned_line["name"] and entry["edits"] == ["name", "height"]
        fixtures = await fixtures_by_name(client, rig_id)

        response = await client.post(carry_path(rig_id), json=entry)

        assert response.status_code == 200, response.text
        done = response.json()
        line = done["room_shell"][LINES][0]
        assert (line["name"], line["height"]) == ("Front truss", 3.5)
        assert "Name set by hand." in line["basis"] and "Height set by hand." in line["basis"]
        assert line["suggested"] is False
        # The height the scan read is what the next reading is matched by (slice 34).
        assert line["scan_height"] == pytest.approx(scanned_line["height"])
        assert done["changed"] is True and done["kind"] == LINES and done["index"] == 0
        assert done["undo"]["available"] == 1
        assert done["undo"]["label"].startswith(f"{scanned_line['name']} given the name and trim of Front truss")
        assert done["room_shell"] == await column(db_session, rig_id)
        bands_add_up(done["room_shell"])
        # No fixture hung on this truss in the test room: none moved.
        assert done["fixtures_moved"] == [] and await fixtures_by_name(client, rig_id) == fixtures

        # Marked by hand, so the same reading applied again keeps it, and has nothing to carry over.
        again = await read(client, rig_id, lowered)
        assert (again["room_shell"][LINES][0]["name"], again["room_shell"][LINES][0]["height"]) == ("Front truss", 3.5)
        assert "carry_over" not in (again["applied"]["hand_edits"] or {})

    @pytest.mark.asyncio
    async def test_one_undo_puts_the_room_back_as_the_scan_left_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, answer, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        applied = await column(db_session, rig_id)
        assert (await client.post(carry_path(rig_id), json=entry)).status_code == 200
        assert await column(db_session, rig_id) != applied

        undone = await client.post(f"{room}/undo")

        assert undone.status_code == 200, undone.text
        assert undone.json()["room_shell"] == applied == await column(db_session, rig_id)
        assert undone.json()["undone"].startswith(f"{entry['new_name']} given the name and trim of Front truss")

    @pytest.mark.asyncio
    async def test_the_same_entry_sent_twice_is_stale_the_second_time(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        assert (await client.post(carry_path(rig_id), json=entry)).status_code == 200
        stored = await column(db_session, rig_id)

        # The truss is called Front truss now, not what the answer said: the room changed since.
        response = await client.post(carry_path(rig_id), json=entry)

        assert response.status_code == 409, response.text
        assert "has changed since the scan was applied" in response.json()["detail"]
        assert await column(db_session, rig_id) == stored

    @pytest.mark.asyncio
    async def test_an_index_past_the_end_is_refused_and_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        stored = await column(db_session, rig_id)

        response = await client.post(carry_path(rig_id), json={**entry, "new_index": 7})

        assert response.status_code == 409, response.text
        assert await column(db_session, rig_id) == stored

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [
        {"kind": "walls"}, {"new_index": "0"}, {"edits": ["center_x"]}, {"edits": []},
        {"old_trim_or_height": "high"}, {"old_name": " "},
    ])
    async def test_an_entry_that_is_not_one_is_refused(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data, bad,
    ):
        rig_id, _, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        stored = await column(db_session, rig_id)

        response = await client.post(carry_path(rig_id), json={**entry, **bad})

        assert response.status_code == 422, response.text
        assert await column(db_session, rig_id) == stored
