"""
Keep all, and the carry-over list kept with the stored room, over HTTP (docs/ROOM_SCAN.md, slice 37)
===================================================================================================

The room of slice 36's tests: its truss named Front truss and trimmed by hand,
read again 1.2 m lower, so the applied answer has one `carry_over` entry. That
entry is stored with the room (`room_shell.pending_carry_over`, GET
.../room-scan/carry-over), dropped when it is carried or made stale, and
brought back by the room's Undo. POST .../room-scan/carry-over/all keeps a list
of them at once, all or none, as one Undo step. Nothing is sent anywhere.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan_carry_over import carry_path, lost_trim
from tests.integration.test_api_room_scan_keep_named import read
from tests.integration.test_api_room_scan_keep_overhead import LINES
from tests.integration.test_api_room_shell_adjust import column


def all_path(rig_id: int) -> str:
    return f"/api/rigs/{rig_id}/room-scan/carry-over/all"


async def stored_list(client: AsyncClient, rig_id: int):
    response = await client.get(carry_path(rig_id))
    assert response.status_code == 200, response.text
    return response.json()["carry_over"]


class TestTheListOutlivesTheDialog:

    @pytest.mark.asyncio
    async def test_the_applied_scan_stores_its_entries_with_the_room(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, answer, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        [warning] = [w for w in answer["applied"]["hand_edits"]["warnings"] if w.get("id") == entry["warning_id"]]
        expected = [{**entry, "message": warning["message"]}]
        assert (await column(db_session, rig_id))["pending_carry_over"] == expected
        assert answer["room_shell"] == await column(db_session, rig_id)
        assert await stored_list(client, rig_id) == expected
        # In the rig as read too, where the dialog's parent gets it.
        rig = (await client.get(f"/api/rigs/{rig_id}")).json()
        assert rig["room_shell"]["pending_carry_over"] == expected

    @pytest.mark.asyncio
    async def test_carried_it_is_gone_and_the_undo_brings_it_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        listed = await stored_list(client, rig_id)
        done = await client.post(carry_path(rig_id), json=entry)
        assert done.status_code == 200, done.text
        assert done.json()["pending_carry_over"] == [] and await stored_list(client, rig_id) == []
        assert "pending_carry_over" not in await column(db_session, rig_id)

        assert (await client.post(f"{room}/undo")).status_code == 200
        assert await stored_list(client, rig_id) == listed

    @pytest.mark.asyncio
    async def test_renamed_in_edit_room_it_is_dropped_and_the_undo_brings_it_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        listed = await stored_list(client, rig_id)
        renamed = await client.patch(f"{room}/{LINES}/0", json={"name": "Mid truss", "carry_fixtures": False})
        assert renamed.status_code == 200, renamed.text
        assert "pending_carry_over" not in renamed.json()["room_shell"]
        assert await stored_list(client, rig_id) == []
        # A button for it now would be a 409: the item is not what the answer called it.
        assert (await client.post(carry_path(rig_id), json=entry)).status_code == 409

        assert (await client.post(f"{room}/undo")).status_code == 200
        assert await stored_list(client, rig_id) == listed

    @pytest.mark.asyncio
    async def test_re_trimmed_it_is_dropped(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, _ = await lost_trim(client, sample_rig_data, sample_fixture_data)
        trimmed = await client.patch(f"{room}/{LINES}/0", json={"height": 3.9, "carry_fixtures": False})
        assert trimmed.status_code == 200, trimmed.text
        assert await stored_list(client, rig_id) == []

    @pytest.mark.asyncio
    async def test_deleted_it_is_dropped(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, _ = await lost_trim(client, sample_rig_data, sample_fixture_data)
        assert (await client.delete(f"{room}/{LINES}/0")).status_code == 200
        assert await stored_list(client, rig_id) == []

    @pytest.mark.asyncio
    async def test_the_room_read_again_or_taken_off_drops_it(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, lowered, _, _ = await lost_trim(client, sample_rig_data, sample_fixture_data)
        # Read again: the room is the scan's now, with no name set by hand to lose, and so nothing to put back.
        again = await read(client, rig_id, lowered)
        assert "carry_over" not in (again["applied"].get("hand_edits") or {})
        assert await stored_list(client, rig_id) == []

        rig_id, _, _, _, _ = await lost_trim(client, sample_rig_data, sample_fixture_data)
        assert (await client.delete(f"/api/rigs/{rig_id}/room-shell")).status_code == 200
        assert await stored_list(client, rig_id) == []


class TestKeepAll:

    @pytest.mark.asyncio
    async def test_the_list_is_kept_as_one_undo_step_and_says_per_entry_what_was_done(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        applied = await column(db_session, rig_id)

        response = await client.post(all_path(rig_id), json={"entries": await stored_list(client, rig_id)})

        assert response.status_code == 200, response.text
        done = response.json()
        [said] = done["carried"]
        assert (said["warning_id"], said["kind"], said["index"], said["changed"]) == (
            entry["warning_id"], LINES, 0, True,
        )
        assert said["message"].startswith(f"{entry['new_name']} given the name and trim of Front truss")
        line = done["room_shell"][LINES][0]
        assert (line["name"], line["height"]) == ("Front truss", 3.5)
        assert done["changed"] is True and done["undo"]["available"] == 1
        assert done["pending_carry_over"] == [] and await stored_list(client, rig_id) == []
        assert done["room_shell"] == await column(db_session, rig_id)

        undone = await client.post(f"{room}/undo")
        assert undone.status_code == 200 and await column(db_session, rig_id) == applied

    @pytest.mark.asyncio
    async def test_two_entries_on_two_lists_are_one_undo_step(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, room, _, answer, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        applied = await column(db_session, rig_id)
        riser = answer["room_shell"]["risers"][0]
        # A second entry made by hand against a raised area of the room as stored: carry_over reads only
        # the shape of an entry and the item's name now, so it stands in for a second loss.
        other = {
            "kind": "risers", "old_name": "The bar", "old_trim_or_height": None, "edits": ["name"],
            "new_index": 0, "new_name": riser.get("name") or "The raised area", "reason": "read beside",
            "warning_id": "lost-1",
        }

        response = await client.post(all_path(rig_id), json={"entries": [entry, other]})

        assert response.status_code == 200, response.text
        done = response.json()
        assert [said["changed"] for said in done["carried"]] == [True, True]
        assert [said["warning_id"] for said in done["carried"]] == [entry["warning_id"], "lost-1"]
        assert done["room_shell"][LINES][0]["name"] == "Front truss"
        assert done["room_shell"]["risers"][0]["name"] == "The bar"
        assert done["undo"] == {"available": 1, "label": "2 names and trims kept from the last scan"}
        assert done["room_shell"] == await column(db_session, rig_id)

        undone = await client.post(f"{room}/undo")
        assert undone.status_code == 200, undone.text
        assert await column(db_session, rig_id) == applied
        assert len(await stored_list(client, rig_id)) == 1

    @pytest.mark.asyncio
    async def test_one_stale_entry_writes_nothing(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        stored = await column(db_session, rig_id)
        stale = {**entry, "new_index": 0, "kind": "truss_rings", "warning_id": "lost-9"}

        response = await client.post(all_path(rig_id), json={"entries": [entry, stale]})

        assert response.status_code == 409, response.text
        assert await column(db_session, rig_id) == stored
        assert len(await stored_list(client, rig_id)) == 1

    @pytest.mark.asyncio
    async def test_two_for_one_item_are_a_422_naming_both(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, _, _, _, entry = await lost_trim(client, sample_rig_data, sample_fixture_data)
        stored = await column(db_session, rig_id)

        response = await client.post(
            all_path(rig_id), json={"entries": [entry, {**entry, "old_name": "Back truss", "warning_id": "lost-1"}]},
        )

        assert response.status_code == 422, response.text
        assert "Front truss" in response.json()["detail"] and "Back truss" in response.json()["detail"]
        assert await column(db_session, rig_id) == stored

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [
        {}, {"entries": []}, {"entries": "all"}, {"entries": [1]},
        # Not hashable: refused in a sentence, never a 500.
        {"entries": [{"kind": [], "new_index": 0}]}, {"entries": [{"kind": "risers", "new_index": {}}]},
    ])
    async def test_a_body_that_is_not_a_list_of_entries_is_a_422(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data, body,
    ):
        rig_id, _, _, _, _ = await lost_trim(client, sample_rig_data, sample_fixture_data)
        stored = await column(db_session, rig_id)
        response = await client.post(all_path(rig_id), json=body)
        assert response.status_code == 422, response.text
        assert await column(db_session, rig_id) == stored
