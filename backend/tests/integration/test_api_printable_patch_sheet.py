"""
Printable patch sheet over HTTP
===============================

GET /api/rigs/{id}/patch-sheet: one self-contained HTML page to print. What
matters to the operator: every fixture is on it, sorted by universe then
address, one section (printed page) per universe; a guessed position says so in
words; a fixture name cannot break or script the page; ?universe=N prints one
universe; the handoff pack carries the same sheet and still builds without it.
"""

import io
import re
import zipfile

import pytest
from httpx import AsyncClient

from app.services.rig import handoff_pack
from app.services.venue_import.apply import TAG_UNCONFIRMED, TAG_UNPLACED
from tests.integration.test_api_readiness import imported_liv, make_rig, snapshot

SHEET = "/api/rigs/{}/patch-sheet"

ROW = re.compile(r'<tr class="(\w+)" data-fixture="(\d+)" data-position="(\w+)">(.*?)</tr>')
CELL = re.compile(r"<td[^>]*>(.*?)</td>")


async def sheet(client, rig_id, **params):
    response = await client.get(SHEET.format(rig_id), params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" not in response.headers.get("content-disposition", "")
    return response.text


def rows(html):
    """(fixture number, position state, cells) for every patch row, in page order."""
    return [(int(m.group(2)), m.group(3), CELL.findall(m.group(4))) for m in ROW.finditer(html)]


def universe_sections(html):
    return [int(u) for u in re.findall(r'<section class="universe" data-universe="(\d+)">', html)]


def self_contained(html):
    assert html.startswith("<!DOCTYPE html>")
    assert "<script" not in html.lower()
    assert "<link" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "@media print" in html and "display: table-header-group" in html
    assert "break-before: page" in html and "landscape" in html


class TestTheLivDemoRig:

    @pytest.mark.asyncio
    async def test_every_fixture_sorted_by_universe_then_address(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        csv_rows = (await client.get(f"/api/rigs/{rig_id}/handoff-pack")).content
        patch = zipfile.ZipFile(io.BytesIO(csv_rows)).read("patch.csv").decode("utf-8").splitlines()[1:]

        html = await sheet(client, rig_id)

        self_contained(html)
        found = rows(html)
        assert len(found) == 36 == len(patch)
        assert len({n for n, _, _ in found}) == 36
        # Universe (column 6) then address (column 7), both numbers.
        keys = [(int(c[5]), int(c[6]), n) for n, _, c in found]
        assert keys == sorted(keys)
        assert universe_sections(html) == sorted({u for u, _, _ in keys})
        assert len(universe_sections(html)) > 1
        booth = next(c for _, _, c in found if c[1] == "Booth Wash 1")
        assert (booth[5], booth[6], booth[7]) == ("4", "325", "4.325")
        # No mode: mode and channels are blank, never a guessed footprint.
        assert booth[3] == "" and booth[4] == ""
        assert "<h1>Patch sheet: Readiness LIV</h1>" in html and "Generated " in html and "(UTC)" in html

    @pytest.mark.asyncio
    async def test_the_summary_and_readiness_agree_with_the_report(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        report = (await client.get(f"/api/rigs/{rig_id}/readiness")).json()

        html = await sheet(client, rig_id)

        counts = report["counts"]
        summary = re.search(r"<p class=\"summary\" data-summary>(.*?)</p>", html).group(1)
        assert summary.startswith("36 fixture(s) in ")
        assert f"readiness {counts['fail']} fail, {counts['warn']} warn." in summary
        for check in report["checks"]:
            if check["status"] in ("fail", "warn"):
                assert check["title"] in html
        ok_titles = [c["title"] for c in report["checks"] if c["status"] == "ok"]
        readiness_part = html[html.index("<h2>Readiness</h2>"):]
        for title in ok_titles:
            assert f": {title}</b>" not in readiness_part

    @pytest.mark.asyncio
    async def test_reading_it_changes_nothing(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        before = await snapshot(db_session, rig_id)

        await sheet(client, rig_id)

        assert await snapshot(db_session, rig_id) == before


class TestAHandMadeRig:

    async def rig(self, db):
        return await make_rig(db, [
            # Out of address order on purpose: universe 2 first, then 1 at 21, then 1 at 1.
            {"name": "Lost Spot", "x": 0.0, "y": 0.0, "tags": [TAG_UNPLACED], "group_name": None,
             "universe": 1, "dmx_address": 101},
            {"name": "Guess Spot", "x": 2.0, "tags": [TAG_UNCONFIRMED], "group_name": "Spots",
             "dmx_address": 21},
            {"name": "<script>alert(1)</script> & Co", "x": -2.0, "dmx_address": 1,
             "tags": ["position_source:mvr", "hang_position:Front <truss> & pipe"], "group_name": "A&B <g>"},
        ], name="Hand Rig")

    @pytest.mark.asyncio
    async def test_sorted_with_a_page_per_universe_and_guessed_marked(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        html = await sheet(client, rig.id)

        self_contained(html)
        found = rows(html)
        names = [c[1] for _, _, c in found]
        assert names == ["&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co", "Guess Spot", "Lost Spot"]
        assert [(c[5], c[6], c[7]) for _, _, c in found] == [("1", "1", "1.001"), ("1", "21", "1.021"),
                                                           ("2", "101", "2.101")]
        assert universe_sections(html) == [1, 2]
        states = {c[1]: (state, c) for _, state, c in found}
        state, guess = states["Guess Spot"]
        assert state == "guessed"
        assert "GUESSED" in guess[12] and guess[8].endswith("(guessed)")
        state, lost = states["Lost Spot"]
        assert state == "none"
        assert (lost[8], lost[9], lost[10], lost[11]) == ("", "", "", "")
        assert "not placed" in lost[12]
        confirmed = states["&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co"]
        assert confirmed[0] == "confirmed" and confirmed[1][12] == "confirmed"
        assert "1 position(s) guessed, 1 not placed" in html
        assert "3 fixture(s) in 2 universe(s) (1, 2)" in html

    @pytest.mark.asyncio
    async def test_a_name_with_script_and_ampersand_is_escaped_everywhere(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        html = await sheet(client, rig.id)

        assert "<script" not in html
        assert "alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co" in html
        assert "Front &lt;truss&gt; &amp; pipe" in html
        assert "A&amp;B &lt;g&gt;" in html
        # Every & in the page starts an entity.
        assert not re.search(r"&(?!(amp|lt|gt|quot|#x27);)", html)

    @pytest.mark.asyncio
    async def test_the_groups_section_lists_console_ids(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        html = await sheet(client, rig.id)

        groups = html[html.index("<h2>Groups</h2>"):html.index("<h2>Readiness</h2>")]
        found = {c[1]: n for n, _, c in rows(html)}
        assert f"<td>Spots</td><td class=\"num\">1</td><td>{found['Guess Spot']}</td>" in groups
        assert "A&amp;B &lt;g&gt;" in groups

    @pytest.mark.asyncio
    async def test_a_universe_filter_prints_that_universe_only(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        html = await sheet(client, rig.id, universe=2)

        assert [c[1] for _, _, c in rows(html)] == ["Lost Spot"]
        assert universe_sections(html) == [2]
        assert "Universe 2 only." in html
        # The summary still describes the whole rig.
        assert "3 fixture(s) in 2 universe(s)" in html

        empty = await sheet(client, rig.id, universe=9)
        assert rows(empty) == [] and universe_sections(empty) == []
        assert "No fixtures in universe 9." in empty

        bad = await client.get(SHEET.format(rig.id), params={"universe": 0})
        assert bad.status_code == 422

    @pytest.mark.asyncio
    async def test_the_pack_carries_the_same_sheet(self, client: AsyncClient, db_session):
        rig, _ = await self.rig(db_session)

        zf = zipfile.ZipFile(io.BytesIO((await client.get(f"/api/rigs/{rig.id}/handoff-pack")).content))

        assert "patch-sheet.html" in zf.namelist()
        packed = zf.read("patch-sheet.html").decode("utf-8")
        live = await sheet(client, rig.id)
        assert rows(packed) == rows(live)
        readme = zf.read("README.txt").decode("utf-8")
        assert "  patch-sheet.html\n      Printable patch sheet" in readme
        assert "MISSING FILES" not in readme

    @pytest.mark.asyncio
    async def test_the_pack_still_builds_when_the_sheet_fails(
        self, client: AsyncClient, db_session, monkeypatch,
    ):
        rig, _ = await self.rig(db_session)

        def broken(*args, **kwargs):
            raise RuntimeError("no sheet today")

        monkeypatch.setattr(handoff_pack, "patch_sheet_html", broken)

        response = await client.get(f"/api/rigs/{rig.id}/handoff-pack")
        assert response.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(zf.namelist())
        assert "patch-sheet.html" not in names
        assert {"README.txt", "patch.csv", "groups.csv", "readiness.md", "Hand_Rig.mvr"} <= names
        readme = zf.read("README.txt").decode("utf-8")
        assert "MISSING FILES" in readme
        assert "patch-sheet.html: the patch sheet stopped with an error: RuntimeError: no sheet today" in readme
        assert "- patch-sheet.html: the patch sheet stopped" in zf.read("readiness.md").decode("utf-8")


@pytest.mark.asyncio
async def test_an_unknown_rig_is_404(client: AsyncClient, db_session):
    response = await client.get(SHEET.format(987654))
    assert response.status_code == 404
