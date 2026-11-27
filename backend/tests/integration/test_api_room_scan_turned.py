"""
Room scan over HTTP: a stage that stands turned from the walls (slice 27)
=========================================================================

A scan of a room whose stage was built at 30 degrees, sent through
POST /api/rigs/{id}/room-scan. What has to hold: the preview says the stage is
turned and that the floor row would be turned with it, and writes nothing;
applying it puts the row on the turned stage and turns each fixture; applying
the same file again moves nothing; and the scan's undo puts each fixture back
where it stood, facing the way it faced.

The scan is made in the test. Nothing here drives a fixture: the endpoint
changes stored positions and headings only.
"""

import math

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import build_rig, fixtures_by_name, light, place, upload
from tests.unit.room_scan_meshes import BIG_ROOM, box, merge, turned_box, write_obj

HEADING = 30.0
CENTRE = (1.0, -3.0)

# A floor row drawn across the room where the stage turns out to be, each par
# facing a way of its own, and a par somebody has tapped in the same group.
LIGHTS = [
    {**light(f"Par {n}", 1 + 16 * n, -1.0 + n, 0.2, -3.5, "Floor Pars"), "rotation_y": 10.0 * n}
    for n in range(5)
] + [{**light("Tapped", 201, 0.5, 0.2, -3.0, "Floor Pars", tags=["position_source:tap"]), "rotation_y": 5.0}]


def scan_file() -> bytes:
    half_w, half_d = BIG_ROOM["width"] / 2.0, BIG_ROOM["depth"] / 2.0
    vertices, faces = merge([
        box(-half_w, half_w, 0.0, BIG_ROOM["height"], -half_d, half_d),
        turned_box(CENTRE[0], CENTRE[1], 6.0, 3.0, 0.0, 0.9, HEADING),
    ])
    return write_obj(vertices, faces)


def facing(entry: dict) -> float:
    return entry["rotation_y"]


class TestATurnedStageOverHttp:

    @pytest.mark.asyncio
    async def test_preview_apply_again_and_undo(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=LIGHTS)
        before = await fixtures_by_name(client, rig_id)
        assert [facing(before[f"Par {n}"]) for n in range(5)] == [0.0, 10.0, 20.0, 30.0, 40.0]

        # --- Preview: the stage is turned, the row would be, and nothing is written.
        preview = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("club.obj", scan_file()))
        assert preview.status_code == 200, preview.text
        body = preview.json()
        stage = next(r for r in body["room_shell"]["risers"] if r["kind"] == "stage")
        assert stage["heading_deg"] == pytest.approx(HEADING, abs=1.0)
        assert any("stands turned" in line for line in body["assumptions"])
        moves = body["fixtures"]["moves"]
        assert sorted(m["name"] for m in moves) == [f"Par {n}" for n in range(5)]
        assert all(m["turn_deg"] == stage["heading_deg"] and "turned" in m["reason"] for m in moves)
        assert await fixtures_by_name(client, rig_id) == before

        # --- Apply: on the turned stage, a metre apart along it, each turned by the heading.
        applied = await client.post(
            f"/api/rigs/{rig_id}/room-scan", params={"apply": "true"}, files=upload("club.obj", scan_file()),
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["applied"]["fixtures_moved"] == 5
        after = await fixtures_by_name(client, rig_id)
        turn = stage["heading_deg"]
        radians = math.radians(turn)
        for n in range(5):
            assert facing(after[f"Par {n}"]) == pytest.approx(10.0 * n - turn)
            assert after[f"Par {n}"]["position_y"] == pytest.approx(0.2 + stage["height"])
            assert "position_unconfirmed" in after[f"Par {n}"]["tags"]
        for n in range(4):
            a, b = after[f"Par {n}"], after[f"Par {n + 1}"]
            step = (b["position_x"] - a["position_x"], b["position_z"] - a["position_z"])
            assert step == pytest.approx((math.cos(radians), math.sin(radians)), abs=0.003)
        # A position a person tapped is never moved or turned.
        assert place(after["Tapped"]) == place(before["Tapped"]) and facing(after["Tapped"]) == 5.0

        # --- The same file again: nothing more to move, and nothing turned twice.
        again = await client.post(
            f"/api/rigs/{rig_id}/room-scan", params={"apply": "true"}, files=upload("club.obj", scan_file()),
        )
        assert again.status_code == 200, again.text
        assert again.json()["fixtures"]["would_move"] == 0
        assert await fixtures_by_name(client, rig_id) == after

        # --- Undo: back where each stood, facing the way it faced.
        undone = await client.post(f"/api/rigs/{rig_id}/room-scan/undo")
        assert undone.status_code == 200, undone.text
        assert undone.json()["restored"] == 5
        back = await fixtures_by_name(client, rig_id)
        for n in range(5):
            assert place(back[f"Par {n}"]) == place(before[f"Par {n}"])
            assert facing(back[f"Par {n}"]) == 10.0 * n
            assert back[f"Par {n}"]["tags"] == before[f"Par {n}"]["tags"]
