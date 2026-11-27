"""
Stage plot underlay, through the API
====================================

POST/GET/DELETE /api/rigs/{id}/stage-plot, GET .../stage-plot/info and PUT
.../stage-plot/calibration. What has to hold: an image is stored and given
back byte for byte with its sniffed type; the type comes from the bytes, not
the name or the client's say; a PDF is refused with a 415 that says to export
the page as an image; the size limit holds; the calibration answers with the
transform (the rotated example the unit tests and vitest share); an unknown
rig is a 404; and none of it changes the rig itself. docs/STAGE_PLOT.md.
"""

import pytest
from httpx import AsyncClient

from app.services.stage_plot import MAX_STAGE_PLOT_BYTES
from tests.integration.test_api_room_scan import build_rig
from tests.unit.test_stage_plot import ROTATED_MATRIX, jpeg, png, webp_vp8x

ROTATED_BODY = {
    "point_a": {"x": 100, "y": 100}, "point_b": {"x": 300, "y": 100}, "distance_m": 4.0,
    "origin": {"x": 200, "y": 300}, "rotation_deg": 90, "opacity": 0.4,
}


def path(rig_id: int, rest: str = "") -> str:
    return f"/api/rigs/{rig_id}/stage-plot{rest}"


async def upload(client: AsyncClient, rig_id: int, content: bytes, name: str = "plot.png", kind: str = "image/png"):
    return await client.post(path(rig_id), files={"file": (name, content, kind)})


async def the_rig(client: AsyncClient, rig_id: int) -> dict:
    """The rig as read back, with its fixtures."""
    rig = await client.get(f"/api/rigs/{rig_id}")
    assert rig.status_code == 200, rig.text
    return rig.json()


class TestUploadGetDelete:

    @pytest.mark.asyncio
    async def test_an_image_is_stored_given_back_and_removed(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        image = png(1600, 900) + b"rest of the image"

        stored = await upload(client, rig_id, image)

        assert stored.status_code == 201, stored.text
        info = stored.json()
        assert (info["present"], info["content_type"], info["width_px"], info["height_px"]) == (True, "image/png", 1600, 900)
        assert (info["byte_size"], info["filename"], info["calibration"], info["transform"]) == (len(image), "plot.png", None, None)
        got = await client.get(path(rig_id))
        assert got.status_code == 200
        assert got.content == image and got.headers["content-type"] == "image/png"
        assert (await client.get(path(rig_id, "/info"))).json()["width_px"] == 1600

        removed = await client.delete(path(rig_id))

        assert removed.status_code == 200 and removed.json()["removed"] is True
        assert (await client.get(path(rig_id))).status_code == 404
        assert (await client.get(path(rig_id, "/info"))).json()["present"] is False
        assert (await client.delete(path(rig_id))).json()["removed"] is False

    @pytest.mark.asyncio
    async def test_jpeg_and_webp_are_taken_and_a_new_upload_replaces_the_old_and_its_calibration(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        assert (await upload(client, rig_id, png(400, 400))).status_code == 201
        assert (await client.put(path(rig_id, "/calibration"), json=ROTATED_BODY)).status_code == 200

        # Named and sent as a PNG, but it is a JPEG: its bytes say so.
        photo = await upload(client, rig_id, jpeg(4032, 3024), name="IMG_0001.png", kind="image/png")

        assert photo.status_code == 201, photo.text
        assert (photo.json()["content_type"], photo.json()["width_px"]) == ("image/jpeg", 4032)
        assert photo.json()["calibration"] is None and photo.json()["transform"] is None
        webp = await upload(client, rig_id, webp_vp8x(800, 600), name="plot.webp", kind="image/webp")
        assert webp.status_code == 201 and webp.json()["content_type"] == "image/webp"
        assert (await client.get(path(rig_id))).headers["content-type"] == "image/webp"


class TestRefusals:

    @pytest.mark.asyncio
    async def test_a_file_that_is_not_an_image_is_refused_whatever_it_claims(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        for content in (b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a" + b"\x00" * 20, b"MZ\x90\x00 not a png"):
            refused = await upload(client, rig_id, content, name="plot.png", kind="image/png")
            assert refused.status_code == 415, refused.text
            assert "PNG, JPEG or WebP" in refused.json()["detail"]
        assert (await upload(client, rig_id, b"")).status_code == 400
        # A PNG signature with nothing after it cannot say how big it is.
        assert (await upload(client, rig_id, b"\x89PNG\r\n\x1a\n")).status_code == 400
        assert (await client.get(path(rig_id, "/info"))).json()["present"] is False

    @pytest.mark.asyncio
    async def test_a_pdf_is_refused_with_a_415_that_says_to_export_the_page_as_an_image(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)

        refused = await upload(client, rig_id, b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj", name="plot.pdf", kind="application/pdf")

        assert refused.status_code == 415
        detail = refused.json()["detail"]
        assert "PDF" in detail and "Export the page as a PNG or JPEG image" in detail
        assert (await client.get(path(rig_id, "/info"))).json()["present"] is False

    @pytest.mark.asyncio
    async def test_a_file_over_the_limit_is_refused_and_one_at_it_is_taken(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        head = png(2000, 2000)

        too_big = await upload(client, rig_id, head + b"\x00" * (MAX_STAGE_PLOT_BYTES + 1 - len(head)))

        assert too_big.status_code == 413
        assert "15 MB" in too_big.json()["detail"]
        at_limit = await upload(client, rig_id, head + b"\x00" * (MAX_STAGE_PLOT_BYTES - len(head)))
        assert at_limit.status_code == 201 and at_limit.json()["byte_size"] == MAX_STAGE_PLOT_BYTES

    @pytest.mark.asyncio
    async def test_an_unknown_rig_is_a_404_on_every_route(self, client: AsyncClient):
        missing = 987654
        assert (await upload(client, missing, png(10, 10))).status_code == 404
        assert (await client.get(path(missing))).status_code == 404
        assert (await client.get(path(missing, "/info"))).status_code == 404
        assert (await client.delete(path(missing))).status_code == 404
        assert (await client.put(path(missing, "/calibration"), json=ROTATED_BODY)).status_code == 404

    @pytest.mark.asyncio
    async def test_calibrating_a_rig_without_a_plot_is_a_404_that_says_to_upload(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        answer = await client.put(path(rig_id, "/calibration"), json=ROTATED_BODY)
        assert answer.status_code == 404 and "Upload one first" in answer.json()["detail"]


class TestCalibration:

    @pytest.mark.asyncio
    async def test_the_rotated_example_is_answered_with_its_transform_and_kept(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        assert (await upload(client, rig_id, png(600, 400))).status_code == 201

        answer = await client.put(path(rig_id, "/calibration"), json=ROTATED_BODY)

        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["calibration"] == {
            "point_a": {"x": 100.0, "y": 100.0}, "point_b": {"x": 300.0, "y": 100.0}, "distance_m": 4.0,
            "origin": {"x": 200.0, "y": 300.0}, "rotation_deg": 90.0, "opacity": 0.4,
        }
        t = body["transform"]
        assert t["scale_m_per_px"] == pytest.approx(0.02) and t["rotation_deg"] == 90.0
        assert t["matrix"] == pytest.approx(ROTATED_MATRIX, abs=1e-12)
        assert (t["offset_x"], t["offset_z"]) == pytest.approx((6.0, -4.0))
        info = (await client.get(path(rig_id, "/info"))).json()
        assert info["calibration"] == body["calibration"] and info["transform"] == t

    @pytest.mark.asyncio
    async def test_a_calibration_that_cannot_be_used_is_a_400_in_a_sentence_and_keeps_the_last(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        assert (await upload(client, rig_id, png(600, 400))).status_code == 201
        assert (await client.put(path(rig_id, "/calibration"), json=ROTATED_BODY)).status_code == 200
        for change in (
            {"point_b": {"x": 100, "y": 100}},
            {"distance_m": 0},
            {"opacity": 2},
        ):
            refused = await client.put(path(rig_id, "/calibration"), json={**ROTATED_BODY, **change})
            assert refused.status_code == 400, (change, refused.text)
            assert refused.json()["detail"].endswith(".")
        # JSON has no infinity, but a client can send one: a sentence, not a 500.
        infinite = await client.put(
            path(rig_id, "/calibration"), content=b'{"point_a":{"x":0,"y":0},"point_b":{"x":10,"y":0},'
            b'"distance_m":Infinity,"origin":{"x":0,"y":0}}', headers={"Content-Type": "application/json"},
        )
        assert infinite.status_code in (400, 422), infinite.text
        assert (await client.get(path(rig_id, "/info"))).json()["calibration"]["distance_m"] == 4.0


class TestTheRigIsOtherwiseUnchanged:

    @pytest.mark.asyncio
    async def test_upload_calibrate_and_remove_leave_the_rig_and_its_fixtures_as_they_were(
        self, client: AsyncClient, sample_rig_data, sample_fixture_data,
    ):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        before = await the_rig(client, rig_id)

        assert (await upload(client, rig_id, png(600, 400))).status_code == 201
        assert await the_rig(client, rig_id) == before
        assert (await client.put(path(rig_id, "/calibration"), json=ROTATED_BODY)).status_code == 200
        assert await the_rig(client, rig_id) == before
        assert (await client.delete(path(rig_id))).status_code == 200
        # updated_at included: the underlay is kept in a table of its own.
        assert await the_rig(client, rig_id) == before

    @pytest.mark.asyncio
    async def test_the_plot_goes_with_a_deleted_rig(self, client: AsyncClient, sample_rig_data, sample_fixture_data):
        rig_id = await build_rig(client, sample_rig_data, sample_fixture_data)
        assert (await upload(client, rig_id, png(10, 10))).status_code == 201

        assert (await client.delete(f"/api/rigs/{rig_id}")).status_code == 204

        assert (await client.get(path(rig_id))).status_code == 404
        again = await client.post("/api/rigs/", json=sample_rig_data)
        if again.json()["id"] == rig_id:  # SQLite may hand the id out again: it must come without a plot.
            assert (await client.get(path(rig_id, "/info"))).json()["present"] is False
