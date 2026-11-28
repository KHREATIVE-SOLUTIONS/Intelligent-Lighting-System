"""
Label tokens: a stale label never names the rig fixture that took its id
=========================================================================

Rig fixture ids are SQLite rowids: delete the newest and the next patch gets
its id back. Every rig fixture has a random `label_token`, printed into its
label QR (GET /rigs/{id}/labels/pdf, GET /rigs/{id}/fixtures/{rf}/qr-code), and
POST /rigs/{id}/scan trusts the label's rig_fixture_id only when the token
agrees. A label printed before tokens existed keeps the old rule (rig fixture
id and fixture_id agree) and the answer says it is an older label.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.rig import RigFixture

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BACKEND_DIR = Path(__file__).resolve().parents[1]


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
    added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
        "fixture_id": profile["id"], "mode_id": profile["modes"][0]["id"],
        "universe": 0, "dmx_address": address, "name": name,
    })
    assert added.status_code == 201, added.text
    return added.json()["id"]


async def _rows(client: AsyncClient, rig_id: int):
    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text
    return listed.json()


async def _label(client: AsyncClient, rig_id: int, rig_fixture_id: int) -> str:
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


# The token

@pytest.mark.asyncio
async def test_every_label_carries_its_own_token_and_it_is_stable(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token stable")
    ids = [await _patch(client, rig_id, profile, 1 + 16 * i, f"Spot {i}") for i in range(3)]

    first = {i: json.loads(await _label(client, rig_id, i))["label_token"] for i in ids}
    assert all(isinstance(t, str) and len(t) == 32 for t in first.values())
    int(next(iter(first.values())), 16)  # hex digits
    assert len(set(first.values())) == 3

    again = {i: json.loads(await _label(client, rig_id, i))["label_token"] for i in ids}
    assert again == first
    # The PDF prints the same text the JSON answers, and the single-fixture
    # route agrees with the sheet.
    pdf = await client.get(f"/api/rigs/{rig_id}/labels/pdf")
    assert pdf.content.startswith(b"%PDF")
    for i in ids:
        one = await client.get(f"/api/rigs/{rig_id}/fixtures/{i}/qr-code", params={"format": "json"})
        assert one.json()["label_token"] == first[i]
        assert json.loads(one.json()["qr_data"])["label_token"] == first[i]


@pytest.mark.asyncio
async def test_a_row_without_a_token_gets_one_on_first_print(client, db_session, sample_rig_data, sample_fixture_data):
    # A raw insert (or a row the migration missed) has none: the first print
    # makes it and later prints keep it.
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token lazy")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    await db_session.execute(update(RigFixture).where(RigFixture.id == rf_id).values(label_token=None))
    await db_session.flush()
    db_session.expire_all()

    made = json.loads(await _label(client, rig_id, rf_id))["label_token"]
    assert isinstance(made, str) and len(made) == 32
    assert json.loads(await _label(client, rig_id, rf_id))["label_token"] == made
    row = await db_session.get(RigFixture, rf_id)
    assert row.label_token == made


@pytest.mark.asyncio
async def test_the_token_is_not_writable_through_the_api(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token not writable")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    before = json.loads(await _label(client, rig_id, rf_id))["label_token"]
    await client.put(f"/api/rigs/{rig_id}/fixtures/{rf_id}", json={"label_token": "0" * 32})
    assert json.loads(await _label(client, rig_id, rf_id))["label_token"] == before


# Scanning

@pytest.mark.asyncio
async def test_a_label_with_its_token_reads_as_already_patched(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token match")
    rf_id = await _patch(client, rig_id, profile, 33, "Spot SL")
    code = await _label(client, rig_id, rf_id)

    answer = await _scan(client, rig_id, code)
    assert answer["action"] == "identified"
    assert answer["already_patched"] is True
    assert answer["matched_by"] == "rig_fixture_id"
    assert answer["older_label"] is False
    assert answer["rig_fixture_id"] == rf_id
    assert "older label" not in answer["message"].lower()
    assert [r["id"] for r in await _rows(client, rig_id)] == [rf_id]


@pytest.mark.asyncio
async def test_an_old_label_of_a_deleted_fixture_does_not_match_the_row_that_took_its_id(
    client, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token reused id")
    kept = await _patch(client, rig_id, profile, 1, "Kept")
    gone = await _patch(client, rig_id, profile, 17, "Old spot")
    old_label = await _label(client, rig_id, gone)
    assert (await client.delete(f"/api/rigs/{rig_id}/fixtures/{gone}")).status_code == 204

    # The newest row was deleted, so the next patch takes its id: same rig,
    # same profile. Without the token this is exactly the false match.
    new_spot = await _patch(client, rig_id, profile, 33, "New spot")
    assert new_spot == gone

    answer = await _scan(client, rig_id, old_label)
    assert answer["action"] == "added"
    assert answer["already_patched"] is False
    assert answer["rig_fixture_id"] not in (kept, new_spot)
    assert f"token does not match rig fixture {gone}" in answer["message"]
    assert "id was reused" in answer["message"]
    assert "Added" in answer["message"]

    rows = await _rows(client, rig_id)
    assert len(rows) == 3
    # The fixture that took the id is untouched by the stale scan.
    reused = next(r for r in rows if r["id"] == new_spot)
    assert reused["name"] == "New spot" and reused["dmx_address"] == 33
    assert reused["qr_code_data"] is None

    # The new fixture's own label still names it.
    own = await _scan(client, rig_id, await _label(client, rig_id, new_spot))
    assert own["action"] == "identified" and own["rig_fixture_id"] == new_spot
    # The old label again: its text is stored on the row it added.
    again = await _scan(client, rig_id, old_label)
    assert again["action"] == "identified"
    assert again["matched_by"] == "qr_code_data"
    assert again["rig_fixture_id"] == answer["rig_fixture_id"]
    assert len(await _rows(client, rig_id)) == 3


@pytest.mark.asyncio
async def test_a_wrong_or_malformed_token_falls_back(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token wrong")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    for bad in ("f" * 32, "", None, 12345):
        code = json.dumps({"fixture_id": profile["id"], "rig_fixture_id": rf_id, "label_token": bad})
        answer = await _scan(client, rig_id, code)
        assert answer["action"] == "added", bad
        assert f"token does not match rig fixture {rf_id}" in answer["message"]


@pytest.mark.asyncio
async def test_an_older_label_without_a_token_keeps_the_old_rule(client, sample_rig_data, sample_fixture_data):
    spot = await _profile(client, sample_fixture_data, model="Older Spot")
    wash = await _profile(client, sample_fixture_data, model="Older Wash")
    rig_id = await _rig(client, sample_rig_data, "Token older label")
    rf_id = await _patch(client, rig_id, spot, 1, "Spot")
    # What GET /labels/pdf printed before tokens.
    older = json.dumps({"fixture_id": spot["id"], "rig_fixture_id": rf_id})

    answer = await _scan(client, rig_id, older)
    assert answer["action"] == "identified"
    assert answer["matched_by"] == "rig_fixture_id"
    assert answer["older_label"] is True
    assert answer["rig_fixture_id"] == rf_id
    assert "older label" in answer["message"].lower()
    assert "without a token" in answer["message"]
    assert len(await _rows(client, rig_id)) == 1

    # And the old rule's other half: a different profile is not a match.
    other = json.dumps({"fixture_id": wash["id"], "rig_fixture_id": rf_id})
    mismatch = await _scan(client, rig_id, other)
    assert mismatch["action"] == "added"
    assert f"rig fixture {rf_id} is now a different fixture" in mismatch["message"]


# GET /rigs/{rig_id}/fixtures/{rig_fixture_id}/qr-code

@pytest.mark.asyncio
async def test_rig_fixture_qr_png_decodes_to_the_label_text(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token png")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    response = await client.get(f"/api/rigs/{rig_id}/fixtures/{rf_id}/qr-code", params={"size": 400})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(PNG_SIGNATURE)
    assert f"rig_{rig_id}_fixture_{rf_id}_qr.png" in response.headers["content-disposition"]

    expected = await _label(client, rig_id, rf_id)
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    img = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape[0] == img.shape[1] <= 400
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    decoded = [d.detectAndDecode(img)[0] for d in detectors]
    assert expected in decoded
    assert len(json.loads(expected)["label_token"]) == 32

    # Scanning what the PNG holds names this rig fixture.
    answer = await _scan(client, rig_id, expected)
    assert answer["action"] == "identified" and answer["rig_fixture_id"] == rf_id


@pytest.mark.asyncio
async def test_rig_fixture_qr_json(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token json")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")
    response = await client.get(f"/api/rigs/{rig_id}/fixtures/{rf_id}/qr-code", params={"format": "json"})
    assert response.status_code == 200
    body = response.json()
    code = json.loads(body["qr_data"])
    assert code == {"fixture_id": profile["id"], "rig_fixture_id": rf_id, "label_token": body["label_token"]}
    assert body["rig_fixture_id"] == rf_id
    bad = await client.get(f"/api/rigs/{rig_id}/fixtures/{rf_id}/qr-code", params={"format": "svg"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_rig_fixture_qr_404s(client, sample_rig_data, sample_fixture_data):
    profile = await _profile(client, sample_fixture_data)
    rig_id = await _rig(client, sample_rig_data, "Token 404 here")
    other = await _rig(client, sample_rig_data, "Token 404 other")
    rf_id = await _patch(client, rig_id, profile, 1, "Spot")

    missing_rig = await client.get(f"/api/rigs/999999/fixtures/{rf_id}/qr-code")
    assert missing_rig.status_code == 404
    assert missing_rig.json()["detail"] == "Rig not found"
    for fmt in ("png", "json"):
        wrong_rig = await client.get(f"/api/rigs/{other}/fixtures/{rf_id}/qr-code", params={"format": fmt})
        assert wrong_rig.status_code == 404
        assert wrong_rig.json()["detail"] == "Rig fixture not found in this rig"
        gone = await client.get(f"/api/rigs/{rig_id}/fixtures/999999/qr-code", params={"format": fmt})
        assert gone.status_code == 404


# Migration 012

def _alembic(db_path: Path, revision: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic upgrade {revision} failed:\n{result.stdout}\n{result.stderr}"


def _columns(connection, table: str):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


@pytest.fixture
def migration_db():
    tmpdir = tempfile.mkdtemp(prefix="ils-migration-012-")
    yield Path(tmpdir) / "migration.db"
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_migration_012_adds_label_token_without_losing_rows(migration_db):
    _alembic(migration_db, "011")

    connection = sqlite3.connect(migration_db)
    try:
        connection.execute(
            "INSERT INTO fixtures (id, manufacturer, model, fixture_type) "
            "VALUES (1, 'Test', 'Pre-token Spot', 'moving_head')"
        )
        connection.execute(
            "INSERT INTO rigs (id, name, stage_width, stage_depth, stage_height) "
            "VALUES (1, 'Existing Rig', 10.0, 8.0, 6.0)"
        )
        for rf_id, address, qr in ((1, 1, None), (2, 17, '{"fixture_id": 1}'), (5, 33, None)):
            connection.execute(
                "INSERT INTO rig_fixtures (id, rig_id, fixture_id, name, universe, dmx_address, "
                " group_name, serial_number, qr_code_data, is_active) "
                "VALUES (?, 1, 1, ?, 0, ?, 'Movers', ?, ?, 1)",
                (rf_id, f"Spot {rf_id}", address, f"SN-{rf_id}", qr),
            )
        connection.commit()
        columns = _columns(connection, "rig_fixtures")
        assert "label_token" not in columns
        select_sql = f"SELECT {', '.join(columns)} FROM rig_fixtures ORDER BY id"
        before = connection.execute(select_sql).fetchall()
    finally:
        connection.close()

    _alembic(migration_db, "head")
    # Running it again changes nothing.
    _alembic(migration_db, "head")

    connection = sqlite3.connect(migration_db)
    try:
        assert "label_token" in _columns(connection, "rig_fixtures")
        assert connection.execute(select_sql).fetchall() == before
        tokens = [row[0] for row in connection.execute("SELECT label_token FROM rig_fixtures ORDER BY id")]
        assert all(isinstance(t, str) and len(t) == 32 for t in tokens)
        assert len(set(tokens)) == len(tokens) == 3
    finally:
        connection.close()
