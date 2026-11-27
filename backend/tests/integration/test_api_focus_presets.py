"""
Focus presets over HTTP
=======================

GET the table and its CSV, POST and DELETE custom targets, the presets in the
ma2-macro export, and focus-presets.csv in the handoff pack. Computing changes
nothing; adding a target writes only rigs.focus_targets. docs/FOCUS_PRESETS.md.
"""

import csv
import io
import zipfile

import pytest
from httpx import AsyncClient

from tests.integration.test_api_readiness import SCANNED_ROOM, make_rig, snapshot

BASE = "/api/rigs/{}/focus-presets"


async def movers(db):
    # The default profile is a spot with no channel list: taken as a mover, 8-bit.
    rig, _ = await make_rig(db, [{"x": -2.0}, {"x": 2.0, "tags": ["position_source:template", "position_unconfirmed"]}],
                            room_shell=SCANNED_ROOM, name="Focus rig")
    return rig


class TestTheTable:

    @pytest.mark.asyncio
    async def test_the_table_has_every_target_against_every_head(self, client: AsyncClient, db_session):
        rig = await movers(db_session)

        response = await client.get(BASE.format(rig.id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rig_id"] == rig.id and body["heads"] == 2 and body["custom_targets"] == []
        keys = [t["key"] for t in body["targets"]]
        assert keys == ["dj_booth", "dance_floor", "audience", "stage_front", "straight_down"]
        floor = next(t for t in body["targets"] if t["key"] == "dance_floor")
        assert floor["reachable_count"] == 2
        assert [f["position_unconfirmed"] for f in floor["fixtures"]] == [False, True]
        booth = body["targets"][0]
        assert booth["skipped"] and booth["fixtures"] == []

    @pytest.mark.asyncio
    async def test_the_csv_is_a_download(self, client: AsyncClient, db_session):
        rig = await movers(db_session)

        response = await client.get(BASE.format(rig.id) + ".csv")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "_focus-presets.csv" in response.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert {r["position"] for r in rows if r["fixture_id"] == "2"} == {"guessed"}

    @pytest.mark.asyncio
    async def test_reading_changes_nothing(self, client: AsyncClient, db_session):
        rig = await movers(db_session)
        before = await snapshot(db_session, rig.id)

        await client.get(BASE.format(rig.id))
        await client.get(BASE.format(rig.id) + ".csv")
        await client.get(f"/api/rigs/{rig.id}/export/ma2-macro")

        assert await snapshot(db_session, rig.id) == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["", ".csv"])
    async def test_an_unknown_rig_is_a_404(self, client: AsyncClient, db_session, path):
        response = await client.get(BASE.format(999999) + path)
        assert response.status_code == 404


class TestCustomTargets:

    @pytest.mark.asyncio
    async def test_add_then_remove(self, client: AsyncClient, db_session):
        rig = await movers(db_session)
        before_rig, before_rows = await snapshot(db_session, rig.id)

        added = await client.post(BASE.format(rig.id) + "/targets", json={"name": "Bar", "x": 4, "y": 1.1, "z": 3})

        assert added.status_code == 201, added.text
        item = added.json()["target"]
        assert item == {"id": 1, "name": "Bar", "x": 4.0, "y": 1.1, "z": 3.0}
        table = (await client.get(BASE.format(rig.id))).json()
        assert table["targets"][-1]["key"] == "custom_1"
        assert table["custom_targets"] == [item]
        after_rig, after_rows = await snapshot(db_session, rig.id)
        assert after_rows == before_rows
        assert after_rig["updated_at"] == before_rig["updated_at"]
        assert {k for k in after_rig if after_rig[k] != before_rig[k]} == {"focus_targets"}

        removed = await client.delete(BASE.format(rig.id) + "/targets/1")

        assert removed.status_code == 200
        assert removed.json()["custom_targets"] == []

    @pytest.mark.asyncio
    async def test_bad_input_is_a_422(self, client: AsyncClient, db_session):
        rig = await movers(db_session)
        response = await client.post(BASE.format(rig.id) + "/targets", json={"name": "", "x": 0, "y": 0, "z": 0})
        assert response.status_code == 422
        response = await client.post(BASE.format(rig.id) + "/targets", json={"name": "A", "x": 0, "y": -1, "z": 0})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_404s(self, client: AsyncClient, db_session):
        rig = await movers(db_session)
        assert (await client.post(BASE.format(999999) + "/targets",
                                  json={"name": "A", "x": 0, "y": 0, "z": 0})).status_code == 404
        assert (await client.delete(BASE.format(999999) + "/targets/1")).status_code == 404
        assert (await client.delete(BASE.format(rig.id) + "/targets/42")).status_code == 404


class TestTheExports:

    @pytest.mark.asyncio
    async def test_the_ma2_script_stores_the_presets(self, client: AsyncClient, db_session):
        rig = await movers(db_session)

        full = await client.get(f"/api/rigs/{rig.id}/export/ma2-macro")
        focus = await client.get(f"/api/rigs/{rig.id}/export/ma2-macro", params={"include": "focus", "first_preset": 20})
        patch = await client.get(f"/api/rigs/{rig.id}/export/ma2-macro", params={"include": "patch"})

        assert full.status_code == focus.status_code == patch.status_code == 200
        assert "Store Preset 2.5" in full.text  # straight down; the scanned room has no booth or stage
        assert "Store Preset 2.1" not in full.text
        assert "Store Preset 2.24" in focus.text and "Assign Fixture" not in focus.text
        assert "Preset" not in patch.text
        assert "fixture 2: position guessed" in full.text

    @pytest.mark.asyncio
    async def test_the_handoff_pack_carries_focus_presets_csv(self, client: AsyncClient, db_session):
        rig = await movers(db_session)

        response = await client.get(f"/api/rigs/{rig.id}/handoff-pack")

        assert response.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(response.content))
        assert "focus-presets.csv" in zf.namelist()
        csv_route = await client.get(BASE.format(rig.id) + ".csv")
        assert zf.read("focus-presets.csv") == csv_route.content
        assert "focus-presets.csv" in zf.read("README.txt").decode("utf-8")
        script = next(n for n in zf.namelist() if n.endswith("_ma2_script.txt"))
        assert zf.read(script) == (await client.get(f"/api/rigs/{rig.id}/export/ma2-macro")).content
