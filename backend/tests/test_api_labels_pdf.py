"""
Label sheet route: GET /api/rigs/{id}/labels/pdf
================================================

The Generate Labels button (QRScanner.tsx) asks for this and saves what comes
back. It is a PDF now, drawn with Pillow (app/services/label_sheet.py); JSON
only on ?format=json.
"""

import json
import re

import pytest
from httpx import AsyncClient

from app.services import label_sheet


async def _rig_with(client: AsyncClient, sample_rig_data, sample_fixture_data, name: str, count: int):
    rig = await client.post("/api/rigs/", json={**sample_rig_data, "name": name})
    assert rig.status_code == 201, rig.text
    rig_id = rig.json()["id"]
    profile = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert profile.status_code in (200, 201), profile.text
    profile = profile.json()
    ids = []
    for i in range(count):
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": profile["id"], "mode_id": profile["modes"][0]["id"],
            "universe": 0, "dmx_address": 1 + 16 * i, "name": f"Spot {i + 1}",
        })
        assert added.status_code == 201, added.text
        ids.append(added.json()["id"])
    return rig_id, profile["id"], ids


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


@pytest.mark.asyncio
async def test_a_rig_gets_a_pdf_download(client, sample_rig_data, sample_fixture_data):
    rig_id, _, _ = await _rig_with(client, sample_rig_data, sample_fixture_data, "Labels one page", 3)
    response = await client.get(f"/api/rigs/{rig_id}/labels/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="rig_{rig_id}_labels.pdf"'
    pdf = response.content
    assert pdf.startswith(b"%PDF")
    assert _page_count(pdf) == 1
    assert b"/MediaBox [ 0 0 612.0 792.0 ]" in pdf  # US Letter
    # Lossless 1-bit pages: no JPEG to blur the QR modules.
    assert b"/DCTDecode" not in pdf


@pytest.mark.asyncio
async def test_more_labels_than_a_sheet_holds_paginate(client, sample_rig_data, sample_fixture_data):
    # 30 labels a page: 31 fixtures need two pages.
    rig_id, _, _ = await _rig_with(client, sample_rig_data, sample_fixture_data, "Labels two pages", 31)
    pdf = (await client.get(f"/api/rigs/{rig_id}/labels/pdf")).content
    assert pdf.startswith(b"%PDF")
    assert _page_count(pdf) == 2
    assert b"/Count 2" in pdf


@pytest.mark.asyncio
async def test_json_on_request_keeps_the_old_fields(client, sample_rig_data, sample_fixture_data):
    rig_id, fixture_id, ids = await _rig_with(client, sample_rig_data, sample_fixture_data, "Labels json", 2)
    response = await client.get(f"/api/rigs/{rig_id}/labels/pdf", params={"format": "json"})
    assert response.status_code == 200
    body = response.json()
    assert body["rig_name"] == "Labels json"
    assert body["total"] == 2
    first = body["labels"][0]
    assert set(first) == {"name", "universe", "dmx_address", "fixture_number", "group", "qr_data"}
    assert (first["name"], first["universe"], first["dmx_address"]) == ("Spot 1", 0, 1)
    code = json.loads(first["qr_data"])
    assert set(code) == {"fixture_id", "rig_fixture_id", "label_token"}
    assert (code["fixture_id"], code["rig_fixture_id"]) == (fixture_id, ids[0])
    assert isinstance(code["label_token"], str) and len(code["label_token"]) == 32


@pytest.mark.asyncio
async def test_an_unknown_format_is_refused(client, sample_rig_data, sample_fixture_data):
    rig_id, _, _ = await _rig_with(client, sample_rig_data, sample_fixture_data, "Labels bad format", 1)
    response = await client.get(f"/api/rigs/{rig_id}/labels/pdf", params={"format": "docx"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_an_empty_rig_gets_one_page_that_says_so(client, sample_rig_data):
    rig = await client.post("/api/rigs/", json={**sample_rig_data, "name": "Labels empty"})
    rig_id = rig.json()["id"]
    response = await client.get(f"/api/rigs/{rig_id}/labels/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert _page_count(response.content) == 1


@pytest.mark.asyncio
async def test_a_missing_rig_is_404(client):
    response = await client.get("/api/rigs/999999/labels/pdf")
    assert response.status_code == 404
    assert response.json()["detail"] == "Rig not found"


def test_the_printed_codes_scan_back_to_their_fixtures():
    """Decode every label straight off the 300 dpi page the PDF is made of."""
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    labels = [
        label_sheet.Label(
            name=f"Moving head stage left {i}", fixture_number=i, universe=i % 2,
            dmx_address=1 + 16 * i, group="Back truss" if i % 2 else None,
            qr_data=json.dumps({"fixture_id": 100 + i, "rig_fixture_id": 54000 + i}),
        )
        for i in range(32)
    ]
    pages = label_sheet.render_pages("Club", labels)
    assert len(pages) == 2
    assert all(p.size == (2550, 3300) and p.mode == "1" for p in pages)
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    for i, label in enumerate(labels):
        page = np.array(pages[i // label_sheet.PER_PAGE].convert("L"))
        x0, y0, x1, y1 = label_sheet.label_box(i % label_sheet.PER_PAGE)
        crop = np.ascontiguousarray(page[y0:y1, x0:x1])
        assert any(d.detectAndDecode(crop)[0] == label.qr_data for d in detectors), i


def test_empty_sheet_is_one_page():
    assert len(label_sheet.render_pages("Empty", [])) == 1
