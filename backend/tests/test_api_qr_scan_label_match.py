"""
Scanning a printed label: POST /api/rigs/{id}/scan, GET /api/fixtures/{id}/qr-code
==================================================================================

A label from GET /rigs/{id}/labels/pdf holds `{"fixture_id", "rig_fixture_id"}`.
Its rig fixture is matched first, so scanning the label of a fixture patched
some other way (UI, import, RDM) names it instead of adding a second copy. A
label whose rig fixture is gone, or in another rig, adds by fixture_id as
before and says why.
"""

import json

import pytest
from httpx import AsyncClient

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def _profile(client: AsyncClient, sample_fixture_data, model: str = None):
    data = dict(sample_fixture_data)
    if model:
        data["model"] = model
    profile = await client.post("/api/fixtures/", json=data)
    assert profile.status_code in (200, 201), profile.text
    return profile.json()


async def _rig(client: AsyncClient, sample_rig_data, name: str) -> int:
    rig = await client.post("/api/rigs/", json={**sample_rig_data, "name": name})
    assert rig.status_code == 201, rig.text
    return rig.json()["id"]


async def _patch(client: AsyncClient, rig_id: int, profile, address: int, name: str) -> int:
    """Patch through the UI's route: it leaves qr_code_data empty."""
    added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
        "fixture_id": profile["id"], "mode_id": profile["modes"][0]["id"],
        "universe": 0, "dmx_address": address, "name": name,
    })
    assert added.status_code == 201, added.text
    assert added.json().get("qr_code_data") is None
    return added.json()["id"]


async def _rows(client: AsyncClient, rig_id: int):
    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text
    return listed.json()


async def _label(client: AsyncClient, rig_id: int, rig_fixture_id: int) -> str:
    """The QR text the printed label for this rig fixture carries."""
    sheet = await client.get(f"/api/rigs/{rig_id}/labels/pdf", params={"format": "json"})
    assert sheet.status_code == 200, sheet.text
    for label in sheet.json()["labels"]:
        if json.loads(label["qr_data"])["rig_fixture_id"] == rig_fixture_id:
            return label["qr_data"]
    raise AssertionError(f"no label for rig fixture {rig_fixture_id}")


async def _scan(client: AsyncClient, rig_id: int, code: str):
    answer = await client.post(f"/api/rigs/{rig_id}/scan", json={"qr_data": code})
    assert answer.status_code == 200, answer.text
    return answer.json()


@pytest.mark.asyncio
async def test_label_of_a_fixture_patched_without_qr_data_adds_nothing(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match UI patched")
    rf_id = await _patch(client, rig_id, profile, 33, "Spot SL")
    code = await _label(client, rig_id, rf_id)

    answer = await _scan(client, rig_id, code)
    assert answer["action"] == "identified"
    assert answer["already_patched"] is True
    assert answer["matched_by"] == "rig_fixture_id"
    assert answer["rig_fixture_id"] == rf_id
    assert (answer["universe"], answer["dmx_address"]) == (0, 33)
    assert "already patched" in answer["message"] and "0.33" in answer["message"]
    assert "Added" not in answer["message"]

    rows = await _rows(client, rig_id)
    assert [r["id"] for r in rows] == [rf_id]
    # Stored so a later scan matches on the text as well.
    assert rows[0]["qr_code_data"] == code


@pytest.mark.asyncio
async def test_repeat_label_scans_add_nothing(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match repeats")
    ids = [await _patch(client, rig_id, profile, 1 + 16 * i, f"Spot {i}") for i in range(3)]
    codes = [await _label(client, rig_id, i) for i in ids]

    for _ in range(3):
        for rf_id, code in zip(ids, codes):
            answer = await _scan(client, rig_id, code)
            assert answer["action"] == "identified"
            assert answer["rig_fixture_id"] == rf_id
    assert sorted(r["id"] for r in await _rows(client, rig_id)) == sorted(ids)


@pytest.mark.asyncio
async def test_label_from_another_rig_adds_by_fixture_id(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    other = await _rig(client, sample_rig_data, "Label match other rig")
    other_rf = await _patch(client, other, profile, 1, "Elsewhere")
    code = await _label(client, other, other_rf)
    rig_id = await _rig(client, sample_rig_data, "Label match this rig")

    answer = await _scan(client, rig_id, code)
    assert answer["action"] == "added"
    assert answer["already_patched"] is False
    assert f"rig fixture {other_rf} is not in this rig" in answer["message"]
    assert "Added" in answer["message"]
    rows = await _rows(client, rig_id)
    assert len(rows) == 1
    assert rows[0]["fixture_id"] == profile["id"]
    assert rows[0]["id"] != other_rf

    # The same label again: the stored text matches, still one row.
    again = await _scan(client, rig_id, code)
    assert again["action"] == "identified"
    assert again["matched_by"] == "qr_code_data"
    assert len(await _rows(client, rig_id)) == 1
    # The other rig is untouched.
    assert [r["id"] for r in await _rows(client, other)] == [other_rf]


@pytest.mark.asyncio
async def test_label_of_a_deleted_rig_fixture_adds_by_fixture_id(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match deleted")
    gone = await _patch(client, rig_id, profile, 1, "Removed")
    kept = await _patch(client, rig_id, profile, 17, "Kept")
    code = await _label(client, rig_id, gone)
    deleted = await client.delete(f"/api/rigs/{rig_id}/fixtures/{gone}")
    assert deleted.status_code == 204

    answer = await _scan(client, rig_id, code)
    assert answer["action"] == "added"
    assert f"rig fixture {gone} no longer exists" in answer["message"]
    assert len(await _rows(client, rig_id)) == 2

    again = await _scan(client, rig_id, code)
    assert again["action"] == "identified"
    assert again["rig_fixture_id"] == answer["rig_fixture_id"]
    rows = await _rows(client, rig_id)
    assert len(rows) == 2
    assert kept in [r["id"] for r in rows]


@pytest.mark.asyncio
async def test_a_reused_rig_fixture_id_on_another_profile_is_not_a_match(client, sample_rig_data, sample_fixture_data):
    # Rig fixture ids are rowids: delete the newest and the next patch may take
    # its id. The label's fixture_id no longer agrees, so it adds instead.
    spot = await _profile(client, sample_fixture_data, model="Label Spot")
    wash = await _profile(client, sample_fixture_data, model="Label Wash")
    rig_id = await _rig(client, sample_rig_data, "Label match reused id")
    gone = await _patch(client, rig_id, spot, 1, "Old spot")
    code = await _label(client, rig_id, gone)
    assert (await client.delete(f"/api/rigs/{rig_id}/fixtures/{gone}")).status_code == 204
    new_wash = await _patch(client, rig_id, wash, 1, "New wash")

    answer = await _scan(client, rig_id, code)
    assert answer["action"] == "added"
    # Reuse is likely, not certain: the reason names whichever happened.
    reason = "is now a different fixture" if new_wash == gone else "no longer exists"
    assert f"rig fixture {gone} {reason}" in answer["message"]
    rows = await _rows(client, rig_id)
    assert sorted(r["fixture_id"] for r in rows) == sorted([spot["id"], wash["id"]])


@pytest.mark.asyncio
async def test_old_qr_code_data_match_still_identifies(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match old text")
    code = json.dumps({"fixture_id": profile["id"], "serial_number": "SN-42", "name": "Tagged"})

    first = await _scan(client, rig_id, code)
    assert first["action"] == "added"
    second = await _scan(client, rig_id, code)
    assert second["action"] == "identified"
    assert second["already_patched"] is True
    assert second["matched_by"] == "qr_code_data"
    assert second["rig_fixture_id"] == first["rig_fixture_id"]
    rows = await _rows(client, rig_id)
    assert len(rows) == 1
    assert rows[0]["serial_number"] == "SN-42"


@pytest.mark.asyncio
async def test_plain_fixture_id_still_adds(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match plain id")
    answer = await _scan(client, rig_id, str(profile["id"]))
    assert answer["action"] == "added"
    assert answer["message"].startswith("Added")
    rows = await _rows(client, rig_id)
    assert [r["fixture_id"] for r in rows] == [profile["id"]]


@pytest.mark.asyncio
async def test_a_non_integer_rig_fixture_id_is_ignored(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Label match junk id")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    for junk in (str(rf_id), True, 1.0):
        code = json.dumps({"fixture_id": profile["id"], "rig_fixture_id": junk})
        answer = await _scan(client, rig_id, code)
        assert "matched_by" not in answer or answer["matched_by"] != "rig_fixture_id"


# GET /fixtures/{id}/qr-code

@pytest.mark.asyncio
async def test_qr_code_route_answers_a_png_that_decodes(client, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    response = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"size": 400})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(PNG_SIGNATURE)

    expected = json.dumps({
        "fixture_id": profile["id"],
        "manufacturer": profile["manufacturer"],
        "model": profile["model"],
    })
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    img = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape[0] == img.shape[1] <= 400
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    assert any(d.detectAndDecode(img)[0] == expected for d in detectors)


@pytest.mark.asyncio
async def test_qr_code_size_scales_by_whole_modules(client, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    small = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"size": 50})
    large = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"size": 500})
    assert small.content.startswith(PNG_SIGNATURE) and large.content.startswith(PNG_SIGNATURE)

    from PIL import Image
    import io

    s = Image.open(io.BytesIO(small.content)).size[0]
    big = Image.open(io.BytesIO(large.content)).size[0]
    assert big > s
    assert big % s == 0 and big <= 500


@pytest.mark.asyncio
async def test_qr_code_json_on_request(client, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    response = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"format": "json"})
    assert response.status_code == 200
    body = response.json()
    assert json.loads(body["qr_data"]) == {
        "fixture_id": profile["id"],
        "manufacturer": profile["manufacturer"],
        "model": profile["model"],
    }


@pytest.mark.asyncio
async def test_qr_code_unknown_format_is_refused(client, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    response = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"format": "svg"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_qr_code_missing_fixture_is_404(client):
    response = await client.get("/api/fixtures/999999/qr-code")
    assert response.status_code == 404
    assert response.json()["detail"] == "Fixture not found"
    response = await client.get("/api/fixtures/999999/qr-code", params={"format": "json"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_long_profile_name_falls_back_to_the_id_alone(client, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data, model="M" * 240)
    response = await client.get(f"/api/fixtures/{profile['id']}/qr-code", params={"format": "json"})
    assert response.status_code == 200
    assert json.loads(response.json()["qr_data"]) == {"fixture_id": profile["id"]}
    png = await client.get(f"/api/fixtures/{profile['id']}/qr-code")
    assert png.content.startswith(PNG_SIGNATURE)
