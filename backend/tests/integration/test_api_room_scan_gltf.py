"""
Room scan API: glTF 2.0 uploads (.glb and .gltf)
================================================

A .glb is what Polycam, Scaniverse and most LiDAR apps export by default. It
goes through POST /api/rigs/{rig_id}/room-scan as an OBJ does: previewed, then
applied, with the room and the stage found the same way.

The room here is a plain box, 10 m across, 8 m deep and 4 m high, with one
stage block hard against the upstage wall and off to stage right, so a mirror
or a swap of two axes would show. It is written once as OBJ and once as glTF,
and both are sent. docs/ROOM_SCAN.md.

Nothing here opens a socket or drives a fixture.
"""

import math

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import build_rig, upload
from tests.unit.room_scan_meshes import as_scanned, box, gltf_scene, merge, write_glb, write_gltf, write_obj

HALL = {"width": 10.0, "depth": 8.0, "height": 4.0}
BLOCK = {"x_min": -4.0, "x_max": 0.5, "z_min": -4.0, "z_max": -1.5, "height": 1.0}


def hall_mesh():
    """The hall in stage axes, metres."""
    half_w, half_d = HALL["width"] / 2.0, HALL["depth"] / 2.0
    return merge([
        box(-half_w, half_w, 0.0, HALL["height"], -half_d, half_d),
        box(BLOCK["x_min"], BLOCK["x_max"], 0.0, BLOCK["height"], BLOCK["z_min"], BLOCK["z_max"]),
    ])


def as_a_phone_has_it():
    """Turned 20 degrees and off its origin, Y-up, metres: what a glTF export of a scan holds."""
    vertices, faces = hall_mesh()
    return as_scanned(vertices, 20.0, offset=(3.0, 0.4, -2.0)), faces


def stage_of(preview: dict) -> dict:
    return next(r for r in preview["room_shell"]["risers"] if r["kind"] == "stage")


def assert_the_hall(preview: dict):
    summary = preview["summary"]
    assert summary["width"] == pytest.approx(HALL["width"], abs=0.1)
    assert summary["depth"] == pytest.approx(HALL["depth"], abs=0.1)
    assert summary["height"] == pytest.approx(HALL["height"], abs=0.1)
    assert summary["raised_areas"] == 1
    stage = stage_of(preview)
    # Stage right of centre, against the upstage wall. Mirrored, it would be at +1.75.
    assert stage["center_x"] == pytest.approx((BLOCK["x_min"] + BLOCK["x_max"]) / 2, abs=0.1)
    assert stage["center_z"] == pytest.approx((BLOCK["z_min"] + BLOCK["z_max"]) / 2, abs=0.1)
    assert stage["width"] == pytest.approx(BLOCK["x_max"] - BLOCK["x_min"], abs=0.2)
    assert stage["depth"] == pytest.approx(BLOCK["z_max"] - BLOCK["z_min"], abs=0.2)
    assert stage["height"] == pytest.approx(BLOCK["height"], abs=0.05)


class TestGltfPreview:

    @pytest.mark.asyncio
    async def test_a_glb_finds_the_room_and_the_stage_as_the_obj_does(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"
        vertices, faces = as_a_phone_has_it()
        doc, data = gltf_scene([(vertices, faces, {})])

        obj = await client.post(url, files=upload("hall.obj", write_obj(vertices, faces)))
        glb = await client.post(url, files=upload("hall.glb", write_glb(doc, data)))
        text = await client.post(url, files=upload("hall.gltf", write_gltf(doc, data)))

        for response in (obj, glb, text):
            assert response.status_code == 200, response.text
        obj, glb, text = obj.json(), glb.json(), text.json()
        assert (obj["format"], glb["format"], text["format"]) == ("obj", "glb", "gltf")

        # Against what the room is.
        for preview in (obj, glb, text):
            assert_the_hall(preview)
            assert preview["applied"] is None
            assert preview["room_shell"]["suggested"] is True

        # Against each other. A glTF's points are 32-bit, so not to the last digit.
        for preview in (glb, text):
            for key in ("width", "depth", "height"):
                assert preview["summary"][key] == pytest.approx(obj["summary"][key], abs=0.02)
            for key in ("center_x", "center_z", "width", "depth", "height"):
                assert stage_of(preview)[key] == pytest.approx(stage_of(obj)[key], abs=0.02)
        # The .glb and the .gltf hold the same bytes, so they are the same room exactly.
        assert glb["room_shell"]["room"] == text["room_shell"]["room"]
        assert glb["room_shell"]["risers"] == text["room_shell"]["risers"]

        # A glTF says its units and its up axis; an OBJ's are guessed.
        assert (glb["summary"]["units"], glb["summary"]["up_axis"]) == ("m", "y")
        assert sum("the file says so" in line for line in glb["assumptions"]) == 2
        assert not any("the file says so" in line for line in obj["assumptions"])

        # A preview writes nothing.
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

    @pytest.mark.asyncio
    async def test_a_scene_that_places_its_mesh_with_nodes(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        """The mesh lies Z-up and in two parts; a parent node stands it up and a child moves the stage in."""
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        half_w, half_d = HALL["width"] / 2.0, HALL["depth"] / 2.0
        walls = box(-half_w, half_w, 0.0, HALL["height"], -half_d, half_d)
        # The block is written at the origin and put in place by its node.
        block = box(0.0, BLOCK["x_max"] - BLOCK["x_min"], 0.0, BLOCK["height"], 0.0, BLOCK["z_max"] - BLOCK["z_min"])

        def lying(points):
            return as_scanned(points, up="z")

        # Stage (x, y, z) is Z-up (x, -z, y): the block's place, said in the axes its parent turns.
        doc, data = gltf_scene([
            (lying(walls[0]), walls[1], {}),
            (lying(block[0]), block[1], {"translation": [BLOCK["x_min"], -BLOCK["z_min"], 0.0]}),
        ])
        half = math.radians(-90.0) / 2.0
        doc["nodes"].append({
            "name": "stood up", "rotation": [math.sin(half), 0.0, 0.0, math.cos(half)], "children": [0, 1],
        })
        doc["scenes"][0]["nodes"] = [2]

        response = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("hall.glb", write_glb(doc, data)))

        assert response.status_code == 200, response.text
        assert_the_hall(response.json())

    @pytest.mark.asyncio
    async def test_a_glb_is_applied_like_any_other_scan(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        vertices, faces = as_a_phone_has_it()
        doc, data = gltf_scene([(vertices, faces, {})], indexed=False, interleaved=True)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("hall.glb", write_glb(doc, data)), params={"apply": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["applied"]["room_shell_stored"] is True
        stored = (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"]
        assert stored["scan"]["format"] == "glb"
        assert stored["room"]["width"] == pytest.approx(HALL["width"], abs=0.1)
        assert_the_hall({"summary": {**stored["room"], "raised_areas": len(stored["risers"])}, "room_shell": stored})


class TestGltfRefusals:

    @pytest.mark.asyncio
    async def test_each_refusal_is_a_400_that_says_what_to_do(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"
        vertices, faces = as_a_phone_has_it()

        async def refused(name: str, content: bytes) -> str:
            response = await client.post(url, files=upload(name, content), params={"apply": True})
            assert response.status_code == 400, response.text
            return response.json()["detail"]

        doc, data = gltf_scene([(vertices, faces, {})])
        doc["extensionsUsed"] = doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]
        said = await refused("hall.glb", write_glb(doc, data))
        assert "Draco" in said and "without Draco or mesh compression" in said and "OBJ" in said

        doc, data = gltf_scene([(vertices, faces, {})])
        doc["extensionsUsed"] = doc["extensionsRequired"] = ["EXT_meshopt_compression"]
        assert "meshopt" in await refused("hall.gltf", write_gltf(doc, data))

        doc, data = gltf_scene([(vertices, faces, {})])
        doc["buffers"][0]["uri"] = "hall.bin"
        said = await refused("hall.gltf", write_gltf(doc))
        assert "hall.bin" in said and ".glb" in said

        doc, data = gltf_scene([(vertices, faces, {})])
        whole = write_glb(doc, data)
        assert "cut short" in await refused("hall.glb", whole[: len(whole) // 2])
        assert "cut short" in await refused("hall.gltf", write_gltf(doc, data)[:400])

        empty = {"asset": {"version": "2.0"}, "scenes": [{"nodes": []}]}
        assert "no triangles or points" in await refused("hall.glb", write_glb(empty))

        # Nothing was stored by any of them.
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None
