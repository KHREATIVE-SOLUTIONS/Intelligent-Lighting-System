"""
Venue import over HTTP
======================

POST /api/import/venue previews a file and, with apply=true, writes it as a new
rig. What matters on a show night: a preview writes nothing, an applied rig is
not the active one, and a fixture the file never placed, could not match or
double-patched arrives saying so instead of looking finished.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.rig import Rig, RigFixture

URL = "/api/import/venue"
SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"

# Invented, so nothing another test left in the library can match it.
UNKNOWN_TYPE = "Nonesuch Blinder 9000"

PATCH_CSV = (
    "FID,Label,Fixture Type,Footprint,Patch,X,Y,Z,Group\n"
    f"1,Placed,{UNKNOWN_TYPE},8,2.101,1.5,6,-2,Front\n"
    f"2,Slash,{UNKNOWN_TYPE},8,2/201,-1.5,6,-2,Front\n"
    f"3,Absolute,{UNKNOWN_TYPE},8,613,,,,Front\n"
    f"4,Clashing,{UNKNOWN_TYPE},8,2.105,0,6,-2,Back\n"
    f"5,Spare,{UNKNOWN_TYPE},8,,0,6,2,Back\n"
).encode()


def upload(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


def sample(name: str) -> dict:
    return upload(name, (SAMPLES / name).read_bytes())


async def rig_count(db_session) -> int:
    return (await db_session.execute(select(func.count(Rig.id)))).scalar_one()


async def rig_fixtures(db_session, rig_id: int) -> dict:
    result = await db_session.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))
    return {fixture.name: fixture for fixture in result.scalars().all()}


class TestVenueImportPreview:

    @pytest.mark.asyncio
    async def test_preview_reports_and_writes_nothing(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)

        response = await client.post(URL, files=upload("patch.csv", PATCH_CSV))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == "csv"
        assert preview["applied"] is None
        assert await rig_count(db_session) == before

        for key in ("fixtures", "groups", "unmatched_types", "address_clashes", "warnings", "assumptions"):
            assert key in preview

        rows = {row["name"]: row for row in preview["fixtures"]}
        assert len(rows) == 5
        # 2.101, 2/201 and 613 all land in this system's universe 1.
        assert (rows["Placed"]["universe"], rows["Placed"]["dmx_address"]) == (1, 101)
        assert (rows["Slash"]["universe"], rows["Slash"]["dmx_address"]) == (1, 201)
        assert (rows["Absolute"]["universe"], rows["Absolute"]["dmx_address"]) == (1, 101)

        assert rows["Placed"]["position"] == {"x": 1.5, "y": 6.0, "z": -2.0}
        assert rows["Placed"]["position_source"] == "csv"
        assert rows["Absolute"]["position"] is None
        assert rows["Absolute"]["position_source"] == "none"
        assert rows["Absolute"]["unplaced"] is True

        assert [u["type_name"] for u in preview["unmatched_types"]] == [UNKNOWN_TYPE]
        assert preview["unmatched_types"][0]["fixtures"] == 5

        clashing = {(c["first"]["name"], c["second"]["name"]) for c in preview["address_clashes"]}
        assert clashing == {("Placed", "Absolute"), ("Placed", "Clashing"), ("Absolute", "Clashing")}

        assert preview["not_importable"] == [{"index": 4, "name": "Spare", "reason": "no DMX address"}]
        assert {g["name"]: g["fixtures"] for g in preview["groups"] if g["role"] == "group"} == {
            "Front": 3, "Back": 2,
        }
        summary = preview["summary"]
        assert (summary["fixtures"], summary["importable"], summary["unplaced"]) == (5, 4, 1)
        assert summary["address_clashes"] == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name, fmt, fixtures, source", [
        ("liv_approx_subset_patch.csv", "csv", 20, "csv"),
        ("liv_approx_subset.mvr", "mvr", 36, "mvr"),
        ("liv_approx_subset_ma2.xml", "ma2", 20, "ma2"),
        ("ils_demo_spot_16ch.gdtf", "gdtf", 0, None),
    ])
    async def test_every_sample_previews(self, client: AsyncClient, name, fmt, fixtures, source):
        response = await client.post(URL, files=sample(name))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == fmt
        assert preview["summary"]["fixtures"] == fixtures
        assert preview["summary"]["address_clashes"] == 0
        if source:
            assert preview["summary"]["position_sources"].get(source, 0) >= fixtures - 2
        else:
            assert preview["summary"]["profiles_in_file"] == 1

    @pytest.mark.asyncio
    async def test_z_up_option_turns_a_sheet(self, client: AsyncClient):
        sheet = b"Name,Type,Patch,X,Y,Z\nA,Par,1.1,1,2,3\n"
        response = await client.post(URL, params={"up_axis": "z"}, files=upload("patch.csv", sheet))
        assert response.status_code == 200, response.text
        assert response.json()["fixtures"][0]["position"] == {"x": 1.0, "y": 3.0, "z": -2.0}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name, content", [
        ("empty.csv", b"   \n"),
        ("patch.xlsx", b"PK\x05\x06 not really a workbook"),
        ("rig.mvr", b"not an archive"),
        ("words.csv", b"nothing here\nlooks like a patch\n"),
        ("patch.xml", b"<MA><Layers/></MA>"),
    ])
    async def test_unreadable_files_are_refused_with_a_reason(self, client: AsyncClient, name, content):
        response = await client.post(URL, files=upload(name, content))
        assert response.status_code == 400, response.text
        assert response.json()["detail"]

    @pytest.mark.asyncio
    async def test_the_endpoint_is_behind_the_operator_login(self, unauthenticated_client: AsyncClient):
        response = await unauthenticated_client.post(URL, files=upload("patch.csv", PATCH_CSV))
        assert response.status_code in (401, 403)


class TestVenueImportApply:

    @pytest.mark.asyncio
    async def test_apply_creates_a_new_inactive_rig(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)

        response = await client.post(
            URL, params={"apply": "true", "rig_name": "Club import"}, files=upload("patch.csv", PATCH_CSV)
        )

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["rig_name"] == "Club import"
        assert applied["is_active"] is False and applied["activated"] is False
        assert applied["fixtures_created"] == 4
        assert applied["fixtures_not_imported"] == 1
        assert applied["unplaced"] == 1
        assert await rig_count(db_session) == before + 1

        rig = await db_session.get(Rig, applied["rig_id"])
        assert rig.is_active is False
        assert rig.source_format == "csv" and rig.source_file == "patch.csv"

        fixtures = await rig_fixtures(db_session, rig.id)
        assert set(fixtures) == {"Placed", "Slash", "Absolute", "Clashing"}

        placed = fixtures["Placed"]
        assert (placed.universe, placed.dmx_address) == (1, 101)
        assert (placed.position_x, placed.position_y, placed.position_z) == (1.5, 6.0, -2.0)
        assert "position_source:csv" in placed.tags and "unplaced" not in placed.tags
        assert placed.group_name == "Front" and placed.fixture_number == 1

        # Not placed by the file: flagged, not given an invented position.
        unplaced = fixtures["Absolute"]
        assert "position_source:none" in unplaced.tags and "unplaced" in unplaced.tags
        assert (unplaced.position_x, unplaced.position_y, unplaced.position_z) == (0.0, 0.0, 0.0)

        # Unmatched types and double-patched channels stay dark until someone looks.
        assert all("unmatched_type" in f.tags and f.is_active is False for f in fixtures.values())
        assert "address_clash" in fixtures["Clashing"].tags
        assert "address_clash" not in fixtures["Placed"].tags

    @pytest.mark.asyncio
    async def test_apply_names_the_rig_after_the_file_by_default(self, client: AsyncClient):
        response = await client.post(URL, params={"apply": "true"}, files=upload("club night.csv", PATCH_CSV))
        assert response.status_code == 200, response.text
        assert response.json()["applied"]["rig_name"] == "club night (imported)"

    @pytest.mark.asyncio
    async def test_apply_mvr_sample_carries_positions_and_profiles(self, client: AsyncClient, db_session):
        response = await client.post(URL, params={"apply": "true"}, files=sample("liv_approx_subset.mvr"))

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["fixtures_created"] == 36
        assert applied["unplaced"] == 0
        assert applied["is_active"] is False

        fixtures = await rig_fixtures(db_session, applied["rig_id"])
        assert len(fixtures) == 36
        assert all("position_source:mvr" in f.tags for f in fixtures.values())

        spot = fixtures["Design Spot A1"]
        assert (spot.universe, spot.dmx_address) == (0, 1)
        assert (spot.position_x, spot.position_y, spot.position_z) == (-6.0, 6.5, -7.5)
        # Its profile came out of the archive, so it has a real mode and is live.
        assert spot.mode_id is not None and spot.is_active is True
        assert "hang_position:Chord A" in spot.tags

    @pytest.mark.asyncio
    async def test_apply_ma2_sample_records_ma2_positions(self, client: AsyncClient, db_session):
        response = await client.post(URL, params={"apply": "true"}, files=sample("liv_approx_subset_ma2.xml"))

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["fixtures_created"] == 20

        fixtures = await rig_fixtures(db_session, applied["rig_id"])
        assert all("position_source:ma2" in f.tags for f in fixtures.values())
        strobe = fixtures["Atomic Strobe 8"]
        assert (strobe.universe, strobe.dmx_address) == (1, 509)
        assert (strobe.position_x, strobe.position_y, strobe.position_z) == (8.0, 6.5, 7.5)

    @pytest.mark.asyncio
    async def test_apply_gdtf_adds_a_profile_and_no_rig(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)

        response = await client.post(URL, params={"apply": "true"}, files=sample("ils_demo_spot_16ch.gdtf"))

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["rig_id"] is None
        assert applied["message"]
        assert await rig_count(db_session) == before

    @pytest.mark.asyncio
    async def test_apply_refuses_a_file_with_nothing_to_patch(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)
        sheet = f"Name,Type,Patch\nA,{UNKNOWN_TYPE},\nB,{UNKNOWN_TYPE},\n".encode()

        response = await client.post(URL, params={"apply": "true"}, files=upload("patch.csv", sheet))

        assert response.status_code == 400, response.text
        assert "Nothing in the file can be patched" in response.json()["detail"]
        assert await rig_count(db_session) == before
