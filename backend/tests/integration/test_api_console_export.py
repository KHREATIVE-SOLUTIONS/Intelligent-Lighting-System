"""
Console export over HTTP
========================

GET /api/rigs/{id}/export/ma2-xml, /ma2-macro and /mvr, and the same three for
a demo preset. What matters to the operator: the file holds the rig that is in
the database right now, the same rig the 3D view draws, and reading it back
with the venue import gives that rig again.
"""

from pathlib import Path
from xml.etree import ElementTree

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.rig import RigFixture
from app.services.console_export.ma2 import ma2_script, ma2_xml
from app.services.console_export.model import from_preset
from app.services.console_export.mvr import mvr_bytes
from app.services.demo.venue_presets import VENUE_PRESETS
from app.services.venue_import import read_venue_file

SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"
LIV = "liv_miami_approx"
MILLIMETRE = 0.001


async def imported_rig(client: AsyncClient, db_session, name: str = "liv_approx_subset.mvr"):
    """The sample MVR written as a rig: (rig id, its rows by name)."""
    response = await client.post(
        "/api/import/venue",
        files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")},
        params={"apply": "true", "rig_name": "Console export test"},
    )
    assert response.status_code == 200, response.text
    rig_id = response.json()["applied"]["rig_id"]
    result = await db_session.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))
    return rig_id, {row.name: row for row in result.scalars().all()}


def assert_file_holds_the_rows(parsed, rows):
    assert len(parsed.fixtures) == len(rows) == 36
    for fixture in parsed.fixtures:
        row = rows[fixture.name]
        assert (fixture.universe, fixture.dmx_address) == (row.universe, row.dmx_address), fixture.name
        assert fixture.fixture_number == row.fixture_number
        assert fixture.group_name == row.group_name
        for read, held in zip(fixture.position, (row.position_x, row.position_y, row.position_z)):
            assert abs(read - held) < MILLIMETRE, fixture.name


class TestRigConsoleExport:

    @pytest.mark.asyncio
    async def test_mvr_holds_the_rig_in_the_database(self, client: AsyncClient, db_session):
        rig_id, rows = await imported_rig(client, db_session)

        response = await client.get(f"/api/rigs/{rig_id}/export/mvr")

        assert response.status_code == 200, response.text
        assert response.headers["content-disposition"] == 'attachment; filename="Console_export_test.mvr"'
        parsed = read_venue_file("export.mvr", response.content)
        assert parsed.format == "mvr"
        assert_file_holds_the_rows(parsed, rows)

        again = await client.get(f"/api/rigs/{rig_id}/export/mvr")
        assert again.content == response.content

    @pytest.mark.asyncio
    async def test_ma2_xml_holds_the_rig_in_the_database(self, client: AsyncClient, db_session):
        rig_id, rows = await imported_rig(client, db_session)

        response = await client.get(f"/api/rigs/{rig_id}/export/ma2-xml")

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/xml")
        assert response.headers["content-disposition"].endswith('_ma2.xml"')
        parsed = read_venue_file("export.xml", response.content)
        assert parsed.format == "ma2"
        assert_file_holds_the_rows(parsed, rows)

    @pytest.mark.asyncio
    async def test_the_script_patches_and_groups_by_fixture_number(self, client: AsyncClient, db_session):
        rig_id, rows = await imported_rig(client, db_session)

        response = await client.get(
            f"/api/rigs/{rig_id}/export/ma2-macro", params={"first_group": 50}
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/plain")
        lines = response.text.splitlines()
        for row in rows.values():
            assert f"Assign Fixture {row.fixture_number} At DMX {row.universe + 1}.{row.dmx_address}" in lines
        assert "Store Group 50" in lines
        assert 'Label Group 50 "Dance Floor Spots"' in lines
        assert "Store Group 49" not in lines

        only_groups = await client.get(
            f"/api/rigs/{rig_id}/export/ma2-macro", params={"include": "groups", "notes": "false"}
        )
        assert only_groups.status_code == 200
        assert "Assign" not in only_groups.text and "#" not in only_groups.text
        assert "Store Group 1" in only_groups.text.splitlines()

    @pytest.mark.asyncio
    async def test_an_edit_to_the_rig_is_in_the_next_export(self, client: AsyncClient, db_session):
        """Nothing is cached: the export is the rig as the layout view left it."""
        rig_id, rows = await imported_rig(client, db_session)
        spot = rows["Design Spot A1"]
        spot.position_x, spot.position_y, spot.position_z = 1.234, 5.678, -9.012
        spot.rotation_y = 45.0
        await db_session.flush()

        mvr = read_venue_file("e.mvr", (await client.get(f"/api/rigs/{rig_id}/export/mvr")).content)
        ma2 = read_venue_file("e.xml", (await client.get(f"/api/rigs/{rig_id}/export/ma2-xml")).content)

        for parsed in (mvr, ma2):
            moved = next(f for f in parsed.fixtures if f.name == "Design Spot A1")
            for read, held in zip(moved.position, (1.234, 5.678, -9.012)):
                assert abs(read - held) < MILLIMETRE
            assert abs(moved.rotation[1] - 45.0) < 0.01

    @pytest.mark.asyncio
    async def test_an_unconfirmed_position_is_exported_and_marked(self, client: AsyncClient, db_session):
        rig_id, rows = await imported_rig(client, db_session)
        guess = rows["Impression Wash 1"]
        guess.tags = ["position_source:template", "position_unconfirmed"]
        await db_session.flush()

        summary = (await client.get(f"/api/rigs/{rig_id}/export/console-summary")).json()
        assert summary["position_unconfirmed"] == 1
        assert summary["fixtures"] == 36
        assert summary["operator_guide"] == "docs/CONSOLE_EXPORT.md"

        mvr = await client.get(f"/api/rigs/{rig_id}/export/mvr")
        parsed = read_venue_file("e.mvr", mvr.content)
        back = next(f for f in parsed.fixtures if f.name == "Impression Wash 1")
        assert back.position is not None

        # Imported again, it is still a guess and every other fixture is not.
        preview = await client.post(
            "/api/import/venue",
            files={"file": ("again.mvr", mvr.content, "application/octet-stream")},
        )
        assert preview.status_code == 200, preview.text
        confirmed = {row["name"]: row["position_confirmed"] for row in preview.json()["fixtures"]}
        assert confirmed["Impression Wash 1"] is False
        assert confirmed["Impression Wash 2"] is True
        assert sum(1 for value in confirmed.values() if value is False) == 1

        script = (await client.get(f"/api/rigs/{rig_id}/export/ma2-macro")).text
        assert '"Position unconfirmed"' in script
        assert f"Fixture {guess.fixture_number}" in script.splitlines()

        marked = await client.get(f"/api/rigs/{rig_id}/export/ma2-xml", params={"mark_names": "true"})
        assert 'name="Impression Wash 1 (position unconfirmed)"' in marked.text
        plain = await client.get(f"/api/rigs/{rig_id}/export/ma2-xml")
        assert 'name="Impression Wash 1"' in plain.text

    @pytest.mark.asyncio
    async def test_the_summary_says_which_gdtf_files_travel(self, client: AsyncClient, db_session):
        rig_id, _ = await imported_rig(client, db_session)

        summary = (await client.get(f"/api/rigs/{rig_id}/export/console-summary")).json()

        named = set(summary["gdtf_embedded"]) | set(summary["gdtf_not_embedded"])
        assert len(named) >= 4
        # The booth wash pars matched nothing: their type is named, never embedded.
        assert any("Opti Tri Par" in spec for spec in summary["gdtf_not_embedded"])
        assert {g["name"] for g in summary["groups"]} >= {"Dance Floor Spots", "Mezzanine Spots"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["ma2-xml", "ma2-macro", "mvr", "console-summary"])
    async def test_a_rig_that_does_not_exist_is_a_404(self, client: AsyncClient, kind):
        response = await client.get(f"/api/rigs/99999999/export/{kind}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_a_bad_first_group_is_refused(self, client: AsyncClient, db_session):
        rig_id, _ = await imported_rig(client, db_session)
        response = await client.get(f"/api/rigs/{rig_id}/export/ma2-macro", params={"first_group": 0})
        assert response.status_code == 422


class TestDemoPresetConsoleExport:

    @pytest.mark.asyncio
    async def test_the_three_files_are_the_ones_the_service_writes(self, client: AsyncClient):
        rig = from_preset(VENUE_PRESETS[LIV])
        base = f"/api/venues/presets/{LIV}/export"

        mvr = await client.get(f"{base}/mvr")
        xml = await client.get(f"{base}/ma2-xml")
        script = await client.get(f"{base}/ma2-macro")

        assert (mvr.status_code, xml.status_code, script.status_code) == (200, 200, 200)
        assert mvr.content == mvr_bytes(rig)
        assert xml.content == ma2_xml(rig).encode("utf-8")
        assert script.content == ma2_script(rig).encode("utf-8")
        assert mvr.headers["content-disposition"] == (
            'attachment; filename="LIV_Miami_approximate_recreation.mvr"'
        )

    @pytest.mark.asyncio
    async def test_the_export_is_the_rig_the_3d_view_draws(self, client: AsyncClient):
        """/demo/rig is what the visualiser renders; the export must be that rig."""
        drawn = (await client.get("/api/demo/rig", params={"preset": LIV})).json()["fixtures"]
        mvr = await client.get(f"/api/venues/presets/{LIV}/export/mvr")
        xml = await client.get(f"/api/venues/presets/{LIV}/export/ma2-xml")

        for parsed in (read_venue_file("liv.mvr", mvr.content), read_venue_file("liv.xml", xml.content)):
            exported = {f.name: f for f in parsed.fixtures}
            assert len(exported) == len(drawn) == 131
            for fixture in drawn:
                got = exported[fixture["name"]]
                assert (got.universe, got.dmx_address) == (fixture["universe"], fixture["dmx_address"])
                held = (fixture["position_x"], fixture["position_y"], fixture["position_z"])
                for read, value in zip(got.position, held):
                    assert abs(read - value) < MILLIMETRE, fixture["name"]
                turned = (fixture["rotation_x"], fixture["rotation_y"], fixture["rotation_z"])
                for read, value in zip(got.rotation, turned):
                    assert abs(read - value) < 0.01, fixture["name"]

    @pytest.mark.asyncio
    async def test_the_summary_carries_the_disclaimer_and_the_gdtf_list(self, client: AsyncClient):
        summary = (await client.get(f"/api/venues/presets/{LIV}/export/console-summary")).json()

        assert summary["fixtures"] == 131
        assert summary["universes"] == [0, 1, 2, 3]
        assert summary["disclaimer"].startswith("APPROXIMATE RECREATION")
        assert len(summary["gdtf_embedded"]) == 3
        assert summary["gdtf_not_embedded"] == ["ILS Demo@Demo LED 12ch.gdtf", "ILS Demo@Demo Strobe 4ch.gdtf"]
        assert summary["position_unconfirmed"] == 0

    @pytest.mark.asyncio
    async def test_the_disclaimer_is_in_every_file(self, client: AsyncClient):
        base = f"/api/venues/presets/{LIV}/export"
        xml = (await client.get(f"{base}/ma2-xml")).text
        script = (await client.get(f"{base}/ma2-macro")).text
        scene = read_scene((await client.get(f"{base}/mvr")).content)
        for text in (xml, script, scene):
            assert "APPROXIMATE RECREATION of LIV Miami" in text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["ma2-xml", "ma2-macro", "mvr", "console-summary"])
    async def test_an_unknown_preset_is_a_404(self, client: AsyncClient, kind):
        response = await client.get(f"/api/venues/presets/no_such_room/export/{kind}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_an_exported_preset_can_be_previewed_by_the_venue_import(self, client: AsyncClient):
        """The whole way round over HTTP: download, then hand it to the importer."""
        mvr = await client.get(f"/api/venues/presets/{LIV}/export/mvr")

        preview = await client.post(
            "/api/import/venue",
            files={"file": ("liv_export.mvr", mvr.content, "application/octet-stream")},
        )

        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["format"] == "mvr"
        assert body["applied"] is None
        assert len(body["fixtures"]) == 131
        assert body["address_clashes"] == []
        assert all(row["position"] is not None for row in body["fixtures"])


def read_scene(mvr: bytes) -> str:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(mvr)) as zf:
        text = zf.read("GeneralSceneDescription.xml").decode("utf-8")
    ElementTree.fromstring(text)
    return text
