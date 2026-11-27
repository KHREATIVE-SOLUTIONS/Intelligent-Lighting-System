"""
Venue handoff pack over HTTP
============================

GET /api/rigs/{id}/handoff-pack: one zip with patch.csv, groups.csv,
readiness.md, the grandMA2 and MVR exports and a README. What matters to the
operator: every fixture is in the patch with its address and whether its
position was guessed; the console files are the ones the export routes give;
a writer that fails leaves its file out but the pack still builds and says so;
and building it changes nothing.
"""

import csv
import io
import zipfile

import pytest
from httpx import AsyncClient

from app.services.rig import handoff_pack, readiness as readiness_service
from app.services.venue_import.apply import TAG_UNCONFIRMED, TAG_UNPLACED
from tests.integration.test_api_readiness import imported_liv, make_rig, snapshot

PACK = "/api/rigs/{}/handoff-pack"


async def pack(client, rig_id):
    response = await client.get(PACK.format(rig_id))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "_handoff_pack.zip" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def read_csv(zf, name):
    return list(csv.DictReader(io.StringIO(zf.read(name).decode("utf-8"))))


def header(zf, name):
    return next(csv.reader(io.StringIO(zf.read(name).decode("utf-8"))))


class TestTheLivDemoRig:

    @pytest.mark.asyncio
    async def test_every_file_is_there_and_the_patch_has_every_fixture(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)

        zf = await pack(client, rig_id)

        names = set(zf.namelist())
        assert {"README.txt", "patch.csv", "groups.csv", "readiness.md", "patch-sheet.html"} <= names
        assert {"Readiness_LIV_ma2.xml", "Readiness_LIV_ma2_script.txt", "Readiness_LIV.mvr"} <= names
        assert header(zf, "patch.csv") == handoff_pack.PATCH_COLUMNS
        assert header(zf, "groups.csv") == handoff_pack.GROUP_COLUMNS
        patch = read_csv(zf, "patch.csv")
        assert len(patch) == 36
        assert len({r["fixture_id"] for r in patch}) == 36
        # Universes counted from 1, as the readiness check names them ("universe 4 channels 337-340").
        booth = next(r for r in patch if r["name"] == "Booth Wash 1")
        assert (booth["universe"], booth["address"]) == ("4", "325")
        # The import sets no DMX mode: blank, not the guessed 16 channels.
        assert booth["mode"] == "" and booth["channels"] == ""
        for row in patch:
            assert row["position"] in ("confirmed", "guessed", "none")
            if row["position"] != "none":
                assert row["position_name"] and row["x"] and row["y"] and row["z"]

    @pytest.mark.asyncio
    async def test_the_console_files_are_the_ones_the_export_routes_give(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)

        zf = await pack(client, rig_id)

        for route, name in (("ma2-xml", "Readiness_LIV_ma2.xml"), ("ma2-macro", "Readiness_LIV_ma2_script.txt"),
                            ("mvr", "Readiness_LIV.mvr")):
            response = await client.get(f"/api/rigs/{rig_id}/export/{route}")
            assert response.status_code == 200
            assert zf.read(name) == response.content, name

    @pytest.mark.asyncio
    async def test_groups_list_the_same_ids_as_the_patch(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)

        zf = await pack(client, rig_id)

        patch = read_csv(zf, "patch.csv")
        groups = read_csv(zf, "groups.csv")
        assert groups
        for group in groups:
            expected = [r["fixture_id"] for r in patch if group["group"] in r["groups"].split("; ")]
            assert group["fixture_ids"].split(" ") == expected

    @pytest.mark.asyncio
    async def test_readiness_is_in_words_worst_first_with_a_time(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        report = (await client.get(f"/api/rigs/{rig_id}/readiness")).json()

        zf = await pack(client, rig_id)

        text = zf.read("readiness.md").decode("utf-8")
        assert "Read at " in text and "(UTC)" in text
        ranks = {"Fail": 2, "Warn": 1, "OK": 0}
        headings = [line[3:].split(":", 1)[0] for line in text.splitlines() if line.startswith("## ")]
        assert len(headings) == len(report["checks"])
        assert [ranks[h] for h in headings] == sorted((ranks[h] for h in headings), reverse=True)
        for check in report["checks"]:
            assert check["message"] in text

    @pytest.mark.asyncio
    async def test_building_it_changes_nothing(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        before = await snapshot(db_session, rig_id)

        await pack(client, rig_id)

        assert await snapshot(db_session, rig_id) == before


class TestAHandMadeRig:

    async def rig(self, db):
        return await make_rig(db, [
            {"name": "Read Spot", "x": -2.0, "tags": ["position_source:mvr", "hang_position:Front truss"]},
            {"name": "Guess Spot", "x": 2.0, "tags": [TAG_UNCONFIRMED], "group_name": "Spots"},
            {"name": "Lost Spot", "x": 0.0, "y": 0.0, "tags": [TAG_UNPLACED], "group_name": None,
             "universe": 1, "dmx_address": 101},
        ], name="Hand Rig")

    @pytest.mark.asyncio
    async def test_confirmed_guessed_and_unplaced_are_told_apart(self, client: AsyncClient, db_session):
        rig, made = await self.rig(db_session)

        zf = await pack(client, rig.id)

        rows = {r["name"]: r for r in read_csv(zf, "patch.csv")}
        read, guess, lost = rows["Read Spot"], rows["Guess Spot"], rows["Lost Spot"]
        assert read["position"] == "confirmed"
        assert read["position_name"] == "Front truss"
        assert (read["x"], read["y"], read["z"]) == ("-2.000", "5.000", "0.000")
        assert (read["mode"], read["channels"], read["universe"], read["address"]) == ("10ch", "10", "1", "1")
        # Maker and model as a console lists them; the repeated "Test" is said once.
        assert read["type"] == "Readiness Test spot"
        assert (read["manufacturer"], read["model"]) == ("Readiness Test", "Test spot")
        assert read["groups"] == "Spots"
        assert read["rig_fixture_id"] == str(made[0].id)
        assert guess["position"] == "guessed"
        assert guess["position_name"]  # a guess from where it stands
        # Never placed: no place name, no 0,0,0 that would read as a real place.
        assert lost["position"] == "none"
        assert (lost["position_name"], lost["x"], lost["y"], lost["z"]) == ("", "", "", "")
        assert (lost["universe"], lost["address"], lost["groups"]) == ("2", "101", "")

        readme = zf.read("README.txt").decode("utf-8")
        assert "1 fixture(s) stand where a layout guessed" in readme
        assert f"Fixture ids: {guess['fixture_id']}" in readme
        assert "1 fixture(s) have no position at all" in readme
        groups = read_csv(zf, "groups.csv")
        assert groups == [{"group": "Spots", "fixture_ids": f"{read['fixture_id']} {guess['fixture_id']}"}]

    @pytest.mark.asyncio
    async def test_a_writer_that_fails_leaves_its_file_out_and_says_why(
        self, client: AsyncClient, db_session, monkeypatch,
    ):
        rig, _ = await self.rig(db_session)

        def broken(*args, **kwargs):
            raise RuntimeError("no MVR today")

        # Both copies, so the readiness report in the pack agrees with the pack.
        monkeypatch.setattr(handoff_pack, "mvr_bytes", broken)
        monkeypatch.setattr(readiness_service, "mvr_bytes", broken)

        zf = await pack(client, rig.id)

        names = set(zf.namelist())
        assert "Hand_Rig.mvr" not in names
        assert {"README.txt", "patch.csv", "groups.csv", "readiness.md", "Hand_Rig_ma2.xml"} <= names
        readme = zf.read("README.txt").decode("utf-8")
        assert "MISSING FILES" in readme
        assert "Hand_Rig.mvr: the writer stopped with an error: RuntimeError: no MVR today" in readme
        assert "FAIL" in readme and "MVR export" in readme
        report = zf.read("readiness.md").decode("utf-8")
        assert "## Missing from this pack" in report
        assert "- Hand_Rig.mvr: the writer stopped with an error" in report
        assert report.index("## Fail: MVR export") < report.index("## OK:")

    @pytest.mark.asyncio
    async def test_no_fail_says_so(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        zf = await pack(client, rig.id)

        assert "No check fails." in zf.read("README.txt").decode("utf-8")
        assert "MISSING FILES" not in zf.read("README.txt").decode("utf-8")


@pytest.mark.asyncio
async def test_an_unknown_rig_is_404(client: AsyncClient, db_session):
    response = await client.get(PACK.format(987654))
    assert response.status_code == 404
