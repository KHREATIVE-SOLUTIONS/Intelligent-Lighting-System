"""
Room scan API: a scan sent as a zip
===================================

Polycam and Scaniverse often share a scan as a zip: a .gltf with its .bin and
textures, or an .obj with its .mtl and textures. It goes through
POST /api/rigs/{rig_id}/room-scan as the model in it would on its own:
previewed, then applied, with the room and the stage found the same way.

The room is the hall of test_api_room_scan_gltf.py: a box 10 by 8 by 4 m with
one stage block against the upstage wall, off to stage right. Every zip is
built here; nothing is read from or written to disk. docs/ROOM_SCAN.md.

Nothing here opens a socket or drives a fixture.
"""

import zipfile

import pytest
from httpx import AsyncClient

from tests.integration.test_api_room_scan import build_rig, upload
from tests.integration.test_api_room_scan_gltf import as_a_phone_has_it, assert_the_hall, stage_of
from tests.unit.room_scan_meshes import gltf_scene, write_glb, write_gltf, write_obj, write_zip
from tests.unit.test_room_scan_zip import forged

PNG = b"\x89PNG\r\n\x1a\n" + bytes(300)
MTL = b"newmtl hall\nKd 0.8 0.8 0.8\nmap_Kd textures/hall.png\n"


def gltf_and_bin():
    """(the hall as a .gltf that names 'hall.bin', that .bin, the same hall as a .glb)."""
    vertices, faces = as_a_phone_has_it()
    doc, data = gltf_scene([(vertices, faces, {})])
    glb = write_glb(doc, data)
    doc["buffers"][0]["uri"] = "hall.bin"
    return write_gltf(doc), data, glb


class TestZipPreviewAndApply:

    @pytest.mark.asyncio
    async def test_a_gltf_zipped_with_its_bin_is_the_room_the_glb_is(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"
        text, data, glb = gltf_and_bin()
        archive = write_zip([
            ("__MACOSX/hall/._hall.gltf", bytes(80)), ("hall/.DS_Store", bytes(40)),
            ("hall/hall.gltf", text), ("hall/hall.bin", data), ("hall/textures/hall.png", PNG),
        ], compression=zipfile.ZIP_DEFLATED)

        zipped = await client.post(url, files=upload("hall.zip", archive))
        whole = await client.post(url, files=upload("hall.glb", glb))

        assert zipped.status_code == 200, zipped.text
        assert whole.status_code == 200, whole.text
        zipped, whole = zipped.json(), whole.json()
        # The answer names the zip that was sent, and the kind of scan found in it.
        assert (zipped["file"], zipped["format"]) == ("hall.zip", "gltf")
        assert_the_hall(zipped)
        # The .gltf and its .bin hold the bytes the .glb does, so it is the same room exactly.
        assert zipped["room_shell"]["room"] == whole["room_shell"]["room"]
        assert stage_of(zipped) == stage_of(whole)
        assert (zipped["summary"]["units"], zipped["summary"]["up_axis"]) == ("m", "y")
        # The report says which file of the zip was read, and nothing of the junk beside it.
        assert "Read 'hall/hall.gltf' from the zip." in zipped["assumptions"]
        assert not any("MACOSX" in line or "also holds" in line for line in zipped["assumptions"])
        # A preview writes nothing.
        assert zipped["applied"] is None
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

    @pytest.mark.asyncio
    async def test_an_obj_zipped_with_its_mtl_and_textures_is_applied(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        vertices, faces = as_a_phone_has_it()
        archive = write_zip([
            ("hall.obj", write_obj(vertices, faces)), ("hall.mtl", MTL),
            ("textures/hall.png", PNG), ("textures/hall_normal.jpg", b"\xff\xd8\xff" + bytes(80)),
        ], compression=zipfile.ZIP_DEFLATED)

        response = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files=upload("hall.zip", archive), params={"apply": True},
        )

        assert response.status_code == 200, response.text
        applied = response.json()
        assert applied["format"] == "obj" and applied["applied"]["room_shell_stored"] is True
        assert "Read 'hall.obj' from the zip." in applied["assumptions"]
        stored = (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"]
        assert (stored["scan"]["file"], stored["scan"]["format"]) == ("hall.zip", "obj")
        assert_the_hall({"summary": {**stored["room"], "raised_areas": len(stored["risers"])}, "room_shell": stored})

    @pytest.mark.asyncio
    async def test_of_several_models_one_is_read_and_the_answer_says_which(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        vertices, faces = as_a_phone_has_it()
        text, data, glb = gltf_and_bin()
        archive = write_zip([
            ("hall.obj", write_obj(vertices, faces)), ("hall.gltf", text), ("hall.bin", data), ("hall.glb", glb),
        ])

        response = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("hall.zip", archive))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == "glb"
        assert_the_hall(preview)
        said = preview["assumptions"]
        assert "Read 'hall.glb' from the zip." in said
        assert any("also holds 'hall.gltf' and 'hall.obj', which were not read" in line for line in said)


class TestZipRefusals:

    @pytest.mark.asyncio
    async def test_each_refusal_is_a_400_that_says_what_is_wrong(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        url = f"/api/rigs/{rig_id}/room-scan"
        vertices, faces = as_a_phone_has_it()
        obj = write_obj(vertices, faces)
        text, data, _ = gltf_and_bin()

        async def refused(name: str, content: bytes) -> str:
            response = await client.post(url, files=upload(name, content), params={"apply": True})
            assert response.status_code == 400, response.text
            return response.json()["detail"]

        # The .bin left out of the zip: named, with what to do.
        said = await refused("hall.zip", write_zip([("hall.gltf", text), ("textures/hall.png", PNG)]))
        assert "'hall.gltf' in the zip could not be read" in said
        assert "needs 'hall.bin'" in said and "not in the zip" in said

        # The .gltf sent on its own: the same file, and now the zip is the way out.
        said = await refused("hall.gltf", text)
        assert "'hall.bin'" in said and "send the zip" in said and ".glb" in said

        # A name that climbs out of the zip refuses all of it, the good scan beside it too.
        said = await refused("hall.zip", write_zip([("hall.obj", obj), ("../../outside.obj", obj)]))
        assert "points outside the zip" in said

        # A password.
        said = await refused("hall.zip", forged(write_zip([("hall.obj", obj)]), "hall.obj", flags=0x1))
        assert "locked with a password" in said

        # Not a zip at all, and one cut short.
        assert "damaged or cut short" in await refused("hall.zip", b"PK\x03\x04 not really a zip")
        whole = write_zip([("hall.obj", obj)])
        assert "damaged" in await refused("hall.zip", whole[: len(whole) // 2])

        # Nothing in it to read.
        said = await refused("hall.zip", write_zip([("hall.mtl", MTL), ("textures/hall.png", PNG)]))
        assert "holds no scan this can read" in said and ".gltf" in said

        # A file that is said to be smaller than it is.
        said = await refused("hall.zip", forged(write_zip([("hall.obj", obj)]), "hall.obj", size=64))
        assert "The zip is damaged" in said

        # Nothing was stored by any of them.
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

    @pytest.mark.asyncio
    async def test_a_zip_is_held_to_the_upload_limit_like_any_file(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data, monkeypatch,
    ):
        from app.api.endpoints import room_scan

        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data, lights=[])
        vertices, faces = as_a_phone_has_it()
        archive = write_zip([("hall.obj", write_obj(vertices, faces))])
        monkeypatch.setattr(room_scan, "MAX_UPLOAD_BYTES", len(archive) - 1)

        response = await client.post(f"/api/rigs/{rig_id}/room-scan", files=upload("hall.zip", archive))

        assert response.status_code == 413
        assert "larger than" in response.json()["detail"]
