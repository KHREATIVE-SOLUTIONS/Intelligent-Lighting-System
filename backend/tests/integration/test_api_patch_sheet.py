"""
Patch sheet import over HTTP
============================

POST /api/import/patch-sheet previews a patch sheet with a generated layout
and, with apply=true, writes it as a new rig. What matters on a show night: a
preview writes nothing, the new rig is not the active one, and every position
this system made up arrives on the rig saying it is unconfirmed.

The library a test database holds is not known here, so nothing below leans on
whether a fixture type matched a profile.
"""

import io
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.rig import Rig, RigFixture
from app.services.demo import patch_sheet_samples

URL = "/api/import/patch-sheet"
SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"
FESTIVAL = patch_sheet_samples.FESTIVAL_FILE

# Invented, so nothing another test left in the library can match it.
UNKNOWN_TYPE = "Nonesuch Beam 9000"

MIXED_CSV = (
    "FID,Label,Fixture Type,Footprint,Patch,Position,X,Y,Z\n"
    f"1,Measured,{UNKNOWN_TYPE},16,1.1,,1.5,6,-2\n"
    f"2,Truss L,{UNKNOWN_TYPE},16,1.17,US Truss,,,\n"
    f"3,Truss R,{UNKNOWN_TYPE},16,1.33,US Truss,,,\n"
    f"4,Spare,{UNKNOWN_TYPE},16,,US Truss,,,\n"
).encode()


def upload(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


def festival() -> dict:
    return upload(FESTIVAL, (SAMPLES / FESTIVAL).read_bytes())


def xlsx(rows) -> bytes:
    """A minimal workbook with inline strings."""
    cells = []
    for r, row in enumerate(rows, start=1):
        cells.append(f'<row r="{r}">')
        for c, value in enumerate(row):
            ref = f"{chr(ord('A') + c)}{r}"
            if isinstance(value, str):
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
            elif value is not None:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        cells.append("</row>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("xl/workbook.xml", (
            '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Patch" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ))
        zf.writestr("xl/_rels/workbook.xml.rels", (
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        ))
        zf.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData>" + "".join(cells) + "</sheetData></worksheet>")
    return buffer.getvalue()


async def rig_count(db_session) -> int:
    return (await db_session.execute(select(func.count(Rig.id)))).scalar_one()


async def rig_fixtures(db_session, rig_id: int) -> dict:
    result = await db_session.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))
    return {fixture.name: fixture for fixture in result.scalars().all()}


class TestPatchSheetPreview:

    @pytest.mark.asyncio
    async def test_preview_lays_the_festival_sheet_out_and_writes_nothing(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)

        response = await client.post(URL, files=festival())

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == "csv" and preview["applied"] is None
        assert await rig_count(db_session) == before

        summary = preview["summary"]
        assert (summary["fixtures"], summary["importable"]) == (84, 84)
        assert (summary["placed"], summary["unplaced"], summary["unconfirmed_positions"]) == (84, 0, 84)
        assert summary["position_sources"] == {"template": 84}
        assert summary["address_clashes"] == 0
        assert [u["universe"] for u in summary["universes"]] == [0, 1, 2, 3]

        layout = preview["layout"]
        assert layout["template"]["name"] == "festival_main_stage"
        assert "chosen because" in layout["template"]["chosen_by"]
        assert layout["generated"] == 84 and layout["position_confirmed"] is False
        assert [row["fixtures"] for row in layout["rows"]] == [16, 12, 16, 8, 8, 12, 12]

        for row in preview["fixtures"]:
            assert row["position"] is not None and row["position"] != {"x": 0.0, "y": 0.0, "z": 0.0}
            assert row["position_source"] == "template"
            assert row["position_confirmed"] is False and row["unplaced"] is False
            assert row["group_name"]

        # A row reads left to right in address order, mirrored about the centre line.
        spots = [row for row in preview["fixtures"] if row["name"].startswith("Spot ")]
        xs = [row["position"]["x"] for row in spots]
        assert len(spots) == 16 and xs == sorted(xs)
        assert [round(a + b, 6) for a, b in zip(xs, reversed(xs))] == [0.0] * 16
        assert len({(row["position"]["y"], row["position"]["z"]) for row in spots}) == 1

        groups = {g["name"]: g["fixtures"] for g in preview["groups"] if g["role"] == "group"}
        assert len(groups) == 7 and sum(groups.values()) == 84
        assert any("first guess" in a for a in preview["assumptions"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template", ["festival_main_stage", "club_ring", "small_stage"])
    async def test_each_template_can_be_asked_for(self, client: AsyncClient, template):
        response = await client.post(URL, params={"template": template}, files=festival())

        assert response.status_code == 200, response.text
        layout = response.json()["layout"]
        assert layout["template"]["name"] == template
        assert layout["template"]["chosen_by"] == "asked for"
        assert layout["generated"] == 84
        positions = [tuple(row["position"].values()) for row in response.json()["fixtures"]]
        assert len(set(positions)) == 84

    @pytest.mark.asyncio
    async def test_the_template_takes_a_stage_size(self, client: AsyncClient):
        response = await client.post(
            URL,
            params={"template": "festival_main_stage", "stage_width": 40, "stage_depth": 20, "stage_height": 16},
            files=festival(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["layout"]["template"]["stage"] == {"width": 40.0, "depth": 20.0, "height": 16.0}

    @pytest.mark.asyncio
    async def test_a_sheet_position_is_kept_and_only_the_rest_is_generated(self, client: AsyncClient):
        response = await client.post(URL, files=upload("patch.csv", MIXED_CSV))

        assert response.status_code == 200, response.text
        preview = response.json()
        rows = {row["name"]: row for row in preview["fixtures"]}
        assert rows["Measured"]["position"] == {"x": 1.5, "y": 6.0, "z": -2.0}
        assert rows["Measured"]["position_source"] == "csv" and rows["Measured"]["position_confirmed"] is True
        assert rows["Truss L"]["position_source"] == "template" and rows["Truss L"]["position_confirmed"] is False
        assert rows["Truss L"]["position"]["x"] == -rows["Truss R"]["position"]["x"] < 0
        # No address: not imported, so not placed either.
        assert rows["Spare"]["position"] is None and rows["Spare"]["importable"] is False
        layout = preview["layout"]
        assert (layout["generated"], layout["kept_from_sheet"]) == (2, 1)
        assert layout["rows"][0]["where"] == "US Truss" and layout["rows"][0]["placed_by"] == "label"
        assert preview["summary"]["unconfirmed_positions"] == 2

    @pytest.mark.asyncio
    async def test_layout_can_be_turned_off(self, client: AsyncClient):
        response = await client.post(URL, params={"layout": "false"}, files=festival())

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["layout"] is None
        assert preview["summary"]["unplaced"] == 84 and preview["summary"]["unconfirmed_positions"] == 0

    @pytest.mark.asyncio
    async def test_a_spreadsheet_is_read(self, client: AsyncClient):
        content = xlsx([
            ["FID", "Label", "Fixture Type", "Footprint", "Patch"],
            [1, "Spot 1", UNKNOWN_TYPE, 16, "2.101"],
            [2, "Spot 2", UNKNOWN_TYPE, 16, "2.117"],
        ])
        response = await client.post(URL, files=upload("patch.xlsx", content))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == "xlsx"
        rows = {row["name"]: row for row in preview["fixtures"]}
        assert (rows["Spot 2"]["universe"], rows["Spot 2"]["dmx_address"]) == (1, 117)
        assert preview["layout"]["rows"][0]["fixtures"] == 2

    @pytest.mark.asyncio
    async def test_a_text_table_is_read(self, client: AsyncClient):
        text = (
            "FID    Label     Fixture Type          Footprint    Patch\n"
            f"1      Spot 1    {UNKNOWN_TYPE}    16           1.1\n"
            f"2      Spot 2    {UNKNOWN_TYPE}                 1.17\n"
        ).encode()
        response = await client.post(URL, files=upload("patch.txt", text))

        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["format"] == "text"
        rows = {row["name"]: row for row in preview["fixtures"]}
        assert rows["Spot 2"]["dmx_address"] == 17

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name, content", [
        ("empty.csv", b"   \n"),
        ("words.txt", b"nothing here\nlooks like a patch\n"),
        ("patch.xlsx", b"PK\x05\x06 not really a workbook"),
        ("rig.xml", b"<MA><Layers/></MA>"),
        ("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 old workbook"),
    ])
    async def test_unreadable_files_are_refused_with_a_reason(self, client: AsyncClient, name, content):
        response = await client.post(URL, files=upload(name, content))
        assert response.status_code == 400, response.text
        assert response.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_pdf_or_photo_is_refused_with_what_to_do_when_nothing_local_can_read_it(
        self, client: AsyncClient,
    ):
        reads = (await client.get(URL + "/templates")).json()["reads"]
        if reads["pdf"] and reads["image"]:
            pytest.skip("a PDF reader and an OCR engine are both installed here")
        if not reads["pdf"]:
            response = await client.post(URL, files=upload("patch.pdf", b"%PDF-1.4\n%%EOF\n"))
            assert response.status_code == 400 and "CSV or XLSX" in response.json()["detail"]
        if not reads["image"]:
            response = await client.post(URL, files=upload("sheet.png", b"\x89PNG\r\n\x1a\n pixels"))
            assert response.status_code == 400 and "CSV or XLSX" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_an_unknown_template_is_refused(self, client: AsyncClient):
        response = await client.post(URL, params={"template": "arena"}, files=festival())
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_templates_and_the_sample_can_be_fetched(self, client: AsyncClient):
        response = await client.get(URL + "/templates")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [t["name"] for t in body["templates"]] == ["festival_main_stage", "club_ring", "small_stage"]
        assert body["reads"]["csv"] is True and body["reads"]["xlsx"] is True

        response = await client.get(URL + "/sample")
        assert response.status_code == 200
        assert response.text == patch_sheet_samples.festival_csv()
        assert "EXAMPLE DATA" in response.text
        assert FESTIVAL in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_the_endpoint_is_behind_the_operator_login(self, unauthenticated_client: AsyncClient):
        response = await unauthenticated_client.post(URL, files=festival())
        assert response.status_code in (401, 403)


class TestPatchSheetApply:

    @pytest.mark.asyncio
    async def test_apply_creates_a_new_inactive_rig_with_unconfirmed_positions(
        self, client: AsyncClient, db_session,
    ):
        before = await rig_count(db_session)

        response = await client.post(
            URL, params={"apply": "true", "rig_name": "Festival from a sheet"}, files=festival(),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        applied = body["applied"]
        assert applied["rig_name"] == "Festival from a sheet"
        assert applied["is_active"] is False and applied["activated"] is False
        assert applied["fixtures_created"] == 84 and applied["fixtures_not_imported"] == 0
        assert applied["unplaced"] == 0 and applied["unconfirmed_positions"] == 84
        assert await rig_count(db_session) == before + 1

        rig = await db_session.get(Rig, applied["rig_id"])
        assert rig.is_active is False
        assert rig.source_format == "csv" and rig.source_file == FESTIVAL
        # The template's own stage: nothing on this sheet hangs outside it.
        assert (rig.stage_width, rig.stage_depth, rig.stage_height) == (24.0, 14.0, 12.0)
        assert sorted(u["universe"] for u in rig.universes) == [0, 1, 2, 3]

        fixtures = await rig_fixtures(db_session, rig.id)
        assert len(fixtures) == 84
        planned = {row["name"]: row for row in body["fixtures"]}
        for name, fixture in fixtures.items():
            assert "position_unconfirmed" in fixture.tags and "position_source:template" in fixture.tags
            assert "unplaced" not in fixture.tags
            # What was previewed is what was written.
            assert planned[name]["position"] == {
                "x": fixture.position_x, "y": fixture.position_y, "z": fixture.position_z,
            }
            assert fixture.group_name == planned[name]["group_name"]
            assert (fixture.position_x, fixture.position_y, fixture.position_z) != (0.0, 0.0, 0.0)

        # The row that ran off the end of universe 2 onto universe 3 is one group.
        back = [f for name, f in fixtures.items() if name.startswith("Back Wash ")]
        assert len(back) == 12 and len({f.group_name for f in back}) == 1
        assert sorted({f.universe for f in back}) == [2, 3]
        assert all("group:ILS Demo Demo Wash 14ch" in f.tags for f in back)

        spot_1, spot_16 = fixtures["Spot 1"], fixtures["Spot 16"]
        assert (spot_1.universe, spot_1.dmx_address, spot_1.fixture_number) == (0, 1, 101)
        assert spot_1.position_x == -spot_16.position_x < 0
        assert (spot_1.position_y, spot_1.position_z) == (spot_16.position_y, spot_16.position_z)

    @pytest.mark.asyncio
    async def test_apply_keeps_a_sheet_position_confirmed_beside_generated_ones(
        self, client: AsyncClient, db_session,
    ):
        response = await client.post(URL, params={"apply": "true"}, files=upload("mixed.csv", MIXED_CSV))

        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["rig_name"] == "mixed (imported)"
        assert applied["fixtures_created"] == 3 and applied["fixtures_not_imported"] == 1
        assert applied["unconfirmed_positions"] == 2

        fixtures = await rig_fixtures(db_session, applied["rig_id"])
        assert set(fixtures) == {"Measured", "Truss L", "Truss R"}
        measured = fixtures["Measured"]
        assert (measured.position_x, measured.position_y, measured.position_z) == (1.5, 6.0, -2.0)
        assert "position_source:csv" in measured.tags and "position_unconfirmed" not in measured.tags
        for name in ("Truss L", "Truss R"):
            assert "position_unconfirmed" in fixtures[name].tags
            assert "hang_position:US Truss" in fixtures[name].tags
            assert fixtures[name].group_name == f"US Truss {UNKNOWN_TYPE}"

    @pytest.mark.asyncio
    async def test_apply_without_layout_leaves_fixtures_unplaced(self, client: AsyncClient, db_session):
        response = await client.post(
            URL, params={"apply": "true", "layout": "false"}, files=upload("mixed.csv", MIXED_CSV),
        )
        assert response.status_code == 200, response.text
        applied = response.json()["applied"]
        assert applied["unplaced"] == 2 and applied["unconfirmed_positions"] == 0
        fixtures = await rig_fixtures(db_session, applied["rig_id"])
        assert "unplaced" in fixtures["Truss L"].tags and "position_unconfirmed" not in fixtures["Truss L"].tags

    @pytest.mark.asyncio
    async def test_apply_refuses_a_sheet_with_nothing_to_patch(self, client: AsyncClient, db_session):
        before = await rig_count(db_session)
        sheet = f"Name,Type,Patch\nA,{UNKNOWN_TYPE},\nB,{UNKNOWN_TYPE},\n".encode()

        response = await client.post(URL, params={"apply": "true"}, files=upload("patch.csv", sheet))

        assert response.status_code == 400, response.text
        assert "no DMX address" in response.json()["detail"]
        assert await rig_count(db_session) == before
