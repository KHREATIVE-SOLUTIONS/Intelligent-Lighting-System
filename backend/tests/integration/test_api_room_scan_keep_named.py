"""
A scan applied again says by name what it kept, left out and lost (docs/ROOM_SCAN.md, slice 35)
===============================================================================================

POST /api/rigs/{id}/room-scan over a room a person has corrected in Edit
Room: `hand_edits`, in a preview (which writes nothing) and in `applied`,
lists what was done one thing at a time (`items`), and names in `warnings`
what was lost: a truss's name and trim where the scan now reads the truss
more than 1.0 m lower, or 0.3 m to one side, and the record of a deleted
riser that the scan no longer reads.

The test scan's room is 12 x 9 x 5 m with a stage, a riser and one 8 m truss
across it at 4 m. The readings here are that room with the truss hung
somewhere else or the riser gone, made in the test: nothing is sent anywhere.
"""

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import fixtures_by_name, upload
from tests.integration.test_api_room_scan_keep_mark import scan_again
from tests.integration.test_api_room_scan_keep_overhead import APPLIED_KEYS, AREA_KEYS, LINES, beside
from tests.integration.test_api_room_shell_adjust import bands_add_up, column
from tests.integration.test_api_room_shell_dj_booth import room_of
from tests.unit.room_scan_meshes import TRUSS, as_scanned, box, merge, room_mesh, write_obj

# What an answer has that only warns: nothing was kept, left out or replaced, so there is no list.
WARNING_KEYS = (AREA_KEYS - {"items"}) | {"warnings"}


def reading(truss_bottom: float = TRUSS["bottom"], truss_z: float = TRUSS["z"], riser: bool = True) -> bytes:
    """The test room as a phone hands it over, with its truss hung where asked and with or without its riser."""
    half, deep = TRUSS["across"] / 2.0, TRUSS["top"] - TRUSS["bottom"]
    vertices, faces = merge([
        room_mesh(truss=False, riser=riser),
        box(TRUSS["x_min"], TRUSS["x_max"], truss_bottom, truss_bottom + deep, truss_z - half, truss_z + half),
    ])
    return write_obj(as_scanned(vertices, 25.0, offset=(2.0, 0.5, -3.0), up="z", units_per_metre=100.0), faces)


async def read(client: AsyncClient, rig_id: int, content: bytes, apply: bool = True) -> dict:
    response = await client.post(
        f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", content),
        params={"apply": apply, "move_fixtures": False},
    )
    assert response.status_code == 200, response.text
    return response.json()


def one(kind, name, outcome):
    return {"kind": kind, "name": name, "outcome": outcome}


class TestTheListOfWhatWasDone:

    @pytest.mark.asyncio
    async def test_the_same_reading_as_the_one_stored_is_the_test_scan(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, _ = await room_of(client, sample_rig_data, sample_fixture_data)
        assert (await read(client, rig_id, reading(), apply=False))["room_shell"] == scanned

    @pytest.mark.asyncio
    async def test_a_preview_and_an_apply_list_each_thing_by_name(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, stage_at, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        stage, truss = scanned["risers"][stage_at], scanned[LINES][0]
        assert (await client.patch(f"{room}/risers/{riser_at}", json={"name": "Drum riser"})).status_code == 200
        assert (await client.patch(f"{room}/{LINES}/0", json={"name": "Front truss"})).status_code == 200
        podium = await client.post(f"{room}/risers", json={
            "name": "Podium", "center_x": -3.0, "center_z": 2.0, "width": 1.5, "depth": 1.5, "height": 0.4,
        })
        pipe = await client.post(f"{room}/{LINES}", json=beside(truss, 0.3))
        assert podium.status_code == 201 and pipe.status_code == 201, (podium.text, pipe.text)
        assert (await client.delete(f"{room}/risers/{stage_at}")).status_code == 200
        stored_room = await column(db_session, rig_id)
        fixtures = await fixtures_by_name(client, rig_id)

        preview = await scan_again(client, rig_id, apply=False)

        expected = [
            one("raised area", stage["name"], "left out (you deleted it)"),
            one("raised area", "Drum riser", "kept your edits"),
            one("line", "Front truss", "kept your edits"),
            one("raised area", "Podium", "added by hand, kept"),
            one("line", "Front pipe", "replaced (a scanned item overlaps it)"),
        ]
        said = preview["hand_edits"]
        assert said["items"] == expected
        assert set(said) == AREA_KEYS | {"overhead_kept", "overhead_added_replaced", "deleted_left_out"}
        # Nothing written: the room and the fixtures are what they were.
        assert preview["applied"] is None and await column(db_session, rig_id) == stored_room
        assert await fixtures_by_name(client, rig_id) == fixtures

        answer = await scan_again(client, rig_id)

        done = answer["applied"]["hand_edits"]
        assert done["items"] == expected
        # The counts and the sentence are what they were before the list.
        assert (done["areas"], len(done["added_kept"]), done["added_replaced"]) == (1, 1, [])
        assert [entry["name"] for entry in done["overhead_kept"]] == ["Front truss"]
        assert [entry["name"] for entry in done["overhead_added_replaced"]] == ["Front pipe"]
        assert [entry["name"] for entry in done["deleted_left_out"]] == [stage["name"]]
        assert done["message"] == (
            f"Left out 1 raised area you deleted: {stage['name']}. "
            "Kept your edits on 1 raised area: Drum riser (name). "
            "Kept your edits on 1 overhead line: Front truss (name). "
            "1 raised area you added was kept as it is: Podium. "
            "Front pipe, which you added, was replaced by the scan's Front truss: "
            "the scan has an overhead line there now."
        )
        assert {**done, "message": None} == {**said, "message": None}
        assert answer["room_shell"] == preview["room_shell"] == await column(db_session, rig_id)


class TestATrussTheScanReadsSomewhereElse:

    @pytest.mark.asyncio
    async def test_one_read_more_than_a_metre_lower_loses_its_name_and_trim_and_says_so(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        truss = scanned[LINES][0]
        done = await client.patch(f"{room}/{LINES}/0", json={"name": "Front truss", "height": 3.5, "carry_fixtures": False})
        assert done.status_code == 200, done.text
        stored_room = await column(db_session, rig_id)
        lowered = reading(truss_bottom=TRUSS["bottom"] - 1.2)

        preview = await read(client, rig_id, lowered, apply=False)
        answer = await read(client, rig_id, lowered)

        line = answer["room_shell"][LINES][0]
        # The room is the reading's: the truss where the scan has it now, under the scan's own name.
        assert line["height"] == pytest.approx(truss["height"] - 1.2, abs=0.05)
        assert line["name"] == truss["name"] and "set by hand" not in line["basis"]
        assert answer["room_shell"] == preview["room_shell"] == await column(db_session, rig_id)
        bands_add_up(answer["room_shell"])
        said = answer["applied"]["hand_edits"]
        assert set(said) == WARNING_KEYS == set(preview["hand_edits"])
        fact = {
            "kind": LINES, "name": "Front truss", "edits": ["name", "height"], "reason": "hanging height",
            "read_height": line["height"], "trim": 3.5, "scan_height": truss["height"],
        }
        sentence = (
            f"The scan read a truss at {line['height']:g} m where Front truss was, against its trim of 3.5 m "
            f"(the scan read it at {truss['height']:g} m before): more than 1 m from where the scan read it before, "
        )
        assert said["warnings"] == [{**fact, "message": sentence + "so its name and trim were not kept."}]
        assert preview["hand_edits"]["warnings"] == [
            {**fact, "message": sentence + "so its name and trim will not be kept."},
        ]
        assert said["message"] == said["warnings"][0]["message"]
        assert (said["areas"], said["kept"], said["added_kept"], said["added_replaced"]) == (0, [], [], [])
        # The preview wrote nothing (the apply after it did).
        assert stored_room[LINES][0]["name"] == "Front truss"
        # Said once: the room now has nothing of a person's on that truss.
        assert set((await read(client, rig_id, lowered))["applied"]) == APPLIED_KEYS

    @pytest.mark.asyncio
    async def test_one_read_to_one_side_loses_its_name_and_says_how_far(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, _, room = await room_of(client, sample_rig_data, sample_fixture_data)
        truss = scanned[LINES][0]
        assert (await client.patch(f"{room}/{LINES}/0", json={"name": "Front truss"})).status_code == 200
        stored_room = await column(db_session, rig_id)
        aside = reading(truss_z=TRUSS["z"] + 0.3)

        preview = await read(client, rig_id, aside, apply=False)

        assert await column(db_session, rig_id) == stored_room
        answer = await read(client, rig_id, aside)

        line = answer["room_shell"][LINES][0]
        assert abs(line["z1"] - truss["z1"]) == pytest.approx(0.3, abs=0.03) and line["name"] == truss["name"]
        said = answer["applied"]["hand_edits"]
        assert set(said) == WARNING_KEYS
        [warning] = said["warnings"]
        assert (warning["kind"], warning["name"], warning["edits"], warning["reason"]) == (
            LINES, "Front truss", ["name"], "read beside",
        )
        # 0.3 m to one side of a strip 0.6 m wide: a third of the two together, under the half a match needs.
        assert warning["offset"] == pytest.approx(0.3, abs=0.03)
        assert warning["overlap"] == pytest.approx(1.0 / 3.0, abs=0.05)
        assert warning["message"] == (
            f"The scan read a truss {round(warning['offset'], 2):g} m from where Front truss was, sharing "
            f"{round(warning['overlap'] * 100)}% of the plan with it where half is needed, so its name was not kept."
        )
        assert said["message"] == warning["message"]
        [before] = preview["hand_edits"]["warnings"]
        assert before["message"].endswith("so its name will not be kept.")
        assert {**before, "message": None} == {**warning, "message": None}


class TestARecordOfADeletedRiserTheScanNoLongerReads:

    @pytest.mark.asyncio
    async def test_it_is_dropped_and_named_and_a_later_scan_brings_the_riser_back(
        self, client: AsyncClient, db_session, sample_rig_data, sample_fixture_data,
    ):
        rig_id, scanned, _, riser_at, room = await room_of(client, sample_rig_data, sample_fixture_data)
        name = scanned["risers"][riser_at]["name"]
        assert (await client.delete(f"{room}/risers/{riser_at}")).status_code == 200
        stored_room = await column(db_session, rig_id)
        assert len(stored_room["deleted_areas"]) == 1
        without = reading(riser=False)

        preview = await read(client, rig_id, without, apply=False)

        fact = {"kind": "risers", "name": name, "reason": "record dropped"}
        assert preview["hand_edits"]["warnings"] == [{**fact, "message": (
            f"The scan did not see {name}; the record that keeps it deleted will be dropped, "
            "so it may come back on a later scan."
        )}]
        assert set(preview["hand_edits"]) == WARNING_KEYS
        # Nothing written: the record is still in the room.
        assert await column(db_session, rig_id) == stored_room

        answer = await read(client, rig_id, without)

        said = answer["applied"]["hand_edits"]
        assert said["warnings"] == [{**fact, "message": (
            f"The scan did not see {name}; the record that keeps it deleted was dropped, "
            "so it may come back on a later scan."
        )}]
        assert said["message"] == said["warnings"][0]["message"] and set(said) == WARNING_KEYS
        assert "deleted_areas" not in answer["room_shell"]
        assert answer["room_shell"] == await column(db_session, rig_id)
        assert len(answer["room_shell"]["risers"]) == len(scanned["risers"]) - 1

        # As the warning said: the scan that reads the riser again has it back, and has nothing more to say.
        later = await scan_again(client, rig_id)
        assert later["room_shell"] == scanned == await column(db_session, rig_id)
        assert set(later["applied"]) == APPLIED_KEYS
