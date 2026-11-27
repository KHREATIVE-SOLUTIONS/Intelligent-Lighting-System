"""
Venue readiness over HTTP
=========================

GET /api/rigs/{id}/readiness and POST .../readiness/fix/auto-groups. What
matters to the operator: each check says ok when the rig is fine and says
what is wrong, naming the fixtures, when it is not; the GET changes nothing;
and Make groups groups the ungrouped once, without touching a name the rig
already has.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.fixture import Fixture, FixtureMode, FixtureType
from app.models.rig import Rig, RigFixture
from app.services.rig import readiness as readiness_service
from app.services.venue_import.apply import TAG_UNCONFIRMED, TAG_UNMATCHED, TAG_UNPLACED

SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"
CHECK_IDS = [
    "fixtures", "positions", "addresses", "profiles", "room", "groups", "carry_over", "export_ma2", "export_mvr",
]
SCANNED_ROOM = {"source": "scan", "room": {"width": 12.0, "depth": 10.0, "height": 6.0}}


async def profile(db, kind=FixtureType.SPOT, channels=10, model=None):
    """A library profile with one mode of `channels` channels (no mode when 0)."""
    fixture = Fixture(manufacturer="Readiness Test", model=model or f"Test {kind.value}", fixture_type=kind)
    db.add(fixture)
    await db.flush()
    mode = None
    if channels:
        mode = FixtureMode(fixture_id=fixture.id, name=f"{channels}ch", channel_count=channels)
        db.add(mode)
        await db.flush()
    return fixture, mode


async def make_rig(db, rows, room_shell=None, name="Readiness rig"):
    """A rig with one RigFixture per dict in `rows`. Each dict may name `profile` as (fixture, mode)."""
    rig = Rig(name=name, stage_width=10.0, stage_depth=8.0, stage_height=6.0, room_shell=room_shell, is_active=False)
    db.add(rig)
    await db.flush()
    default = await profile(db)
    made = []
    for i, row in enumerate(rows):
        row = dict(row)
        fixture, mode = row.pop("profile", default)
        rf = RigFixture(
            rig_id=rig.id,
            fixture_id=fixture.id,
            mode_id=mode.id if mode is not None else None,
            name=row.pop("name", f"Light {i + 1}"),
            fixture_number=i + 1,
            universe=row.pop("universe", 0),
            dmx_address=row.pop("dmx_address", 1 + i * 10),
            position_x=row.pop("x", 0.0),
            position_y=row.pop("y", 5.0),
            position_z=row.pop("z", 0.0),
            group_name=row.pop("group_name", "Spots"),
            tags=row.pop("tags", ["position_source:mvr"]),
            **row,
        )
        db.add(rf)
        made.append(rf)
    await db.flush()
    return rig, made


async def get(client, rig_id):
    response = await client.get(f"/api/rigs/{rig_id}/readiness")
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {c["id"]: c for c in body["checks"]}


async def imported_liv(client: AsyncClient, name: str = "liv_approx_subset.mvr") -> int:
    response = await client.post(
        "/api/import/venue",
        files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")},
        params={"apply": "true", "rig_name": "Readiness LIV"},
    )
    assert response.status_code == 200, response.text
    return response.json()["applied"]["rig_id"]


async def snapshot(db, rig_id):
    """Every column of the rig and its fixtures, as stored."""
    db.expire_all()
    rig = (await db.execute(select(Rig).where(Rig.id == rig_id))).scalar_one()
    rows = (await db.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))).scalars().all()

    def columns(obj):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    return columns(rig), sorted((columns(rf) for rf in rows), key=lambda r: r["id"])


class TestTheReport:

    @pytest.mark.asyncio
    async def test_the_liv_demo_rig_has_every_check(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)

        body, checks = await get(client, rig_id)

        assert [c["id"] for c in body["checks"]] == CHECK_IDS
        for check in body["checks"]:
            assert check["status"] in ("ok", "warn", "fail")
            assert isinstance(check["message"], str) and check["message"]
            assert check["fixture_count"] >= len(check["fixture_ids"])
        assert checks["fixtures"]["status"] == "ok"
        assert "36 fixtures" in checks["fixtures"]["message"]
        # The file patches Booth Wash 1 at 4.325 and Booth Wash 2 at 4.337, both 12ch.
        # The import gives them no DMX mode, so at the guessed 16 channels they seem
        # to overlap: a warning to pick a mode, not a failure.
        assert checks["addresses"]["status"] == "warn", checks["addresses"]["message"]
        assert "Booth Wash 1 and Booth Wash 2 on universe 4 channels 337-340" in checks["addresses"]["message"]
        assert checks["addresses"]["message"].startswith("Maybe: ")
        assert checks["addresses"]["fixture_count"] == 2
        assert checks["export_ma2"]["status"] == "ok"
        assert checks["export_mvr"]["status"] == "ok"
        assert checks["room"]["status"] == "ok"  # no room stored with an imported rig
        assert checks["carry_over"]["status"] == "ok"
        worst = max(body["checks"], key=lambda c: ("ok", "warn", "fail").index(c["status"]))["status"]
        assert body["status"] == worst
        assert sum(body["counts"].values()) == len(CHECK_IDS)

    @pytest.mark.asyncio
    async def test_the_get_changes_nothing(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        rig = (await db_session.execute(select(Rig).where(Rig.id == rig_id))).scalar_one()
        rig.room_shell = {**SCANNED_ROOM, "pending_carry_over": [{"kind": "truss_lines", "new_index": 0}]}
        await db_session.flush()
        before = await snapshot(db_session, rig_id)

        first, _ = await get(client, rig_id)
        second, _ = await get(client, rig_id)

        assert first == second
        assert await snapshot(db_session, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_clean_rig_is_ok_throughout(self, client: AsyncClient, db_session):
        rig, _ = await make_rig(db_session, [{"x": -2.0}, {"x": 2.0}])

        body, checks = await get(client, rig.id)

        assert body["status"] == "ok", body
        assert all(c["fixture_ids"] == [] for c in body["checks"])
        assert "No room is stored" in checks["room"]["message"]

    @pytest.mark.asyncio
    async def test_an_empty_rig_fails(self, client: AsyncClient, db_session):
        rig, _ = await make_rig(db_session, [])

        body, checks = await get(client, rig.id)

        assert checks["fixtures"]["status"] == "fail"
        assert body["status"] == "fail"
        assert checks["export_ma2"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_an_unknown_rig_is_a_404(self, client: AsyncClient):
        assert (await client.get("/api/rigs/999999/readiness")).status_code == 404
        assert (await client.post("/api/rigs/999999/readiness/fix/auto-groups")).status_code == 404


class TestEachCheck:

    @pytest.mark.asyncio
    async def test_guessed_and_unplaced_positions_warn(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [
            {"tags": ["position_source:template", TAG_UNCONFIRMED]},
            {"tags": ["position_source:none", TAG_UNPLACED]},
            {},
        ])

        _, checks = await get(client, rig.id)

        assert checks["positions"]["status"] == "warn"
        assert checks["positions"]["fixture_ids"] == sorted([rows[0].id, rows[1].id])
        assert "guessed" in checks["positions"]["message"]
        assert "no position" in checks["positions"]["message"]

    @pytest.mark.asyncio
    async def test_overlapping_addresses_fail(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"dmx_address": 1}, {"dmx_address": 5}, {"dmx_address": 30}])

        _, checks = await get(client, rig.id)

        assert checks["addresses"]["status"] == "fail"
        assert checks["addresses"]["fixture_ids"] == sorted([rows[0].id, rows[1].id])
        assert "Light 1 and Light 2 on universe 1 channels 5-10" in checks["addresses"]["message"]

    @pytest.mark.asyncio
    async def test_an_overlap_that_needs_a_guessed_footprint_only_warns(self, client: AsyncClient, db_session):
        no_mode = await profile(db_session, channels=0, model="Modeless")
        # 1-16 guessed against 13-22 known: only the guess makes them meet.
        rig, rows = await make_rig(db_session, [
            {"dmx_address": 1, "profile": no_mode}, {"dmx_address": 13}, {"dmx_address": 505, "profile": no_mode},
        ])

        _, checks = await get(client, rig.id)

        assert checks["addresses"]["status"] == "warn", checks["addresses"]["message"]
        assert checks["addresses"]["fixture_ids"] == sorted(rf.id for rf in rows)
        assert checks["addresses"]["message"].startswith("Maybe: ")
        assert "past channel 512" in checks["addresses"]["message"]

        # A real overlap next to a guessed one still fails, and says both.
        rig2, rows2 = await make_rig(db_session, [
            {"dmx_address": 1, "profile": no_mode}, {"dmx_address": 13}, {"dmx_address": 100}, {"dmx_address": 105},
        ])
        _, checks2 = await get(client, rig2.id)
        assert checks2["addresses"]["status"] == "fail"
        assert "Light 3 and Light 4" in checks2["addresses"]["message"]
        assert "Maybe also: " in checks2["addresses"]["message"]
        assert checks2["addresses"]["fixture_ids"] == sorted(rf.id for rf in rows2)

    @pytest.mark.asyncio
    async def test_a_fixture_past_channel_512_fails(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"dmx_address": 1}, {"dmx_address": 507}])

        _, checks = await get(client, rig.id)

        assert checks["addresses"]["status"] == "fail"
        assert checks["addresses"]["fixture_ids"] == [rows[1].id]
        assert "past channel 512" in checks["addresses"]["message"]
        assert "507-516" in checks["addresses"]["message"]

    @pytest.mark.asyncio
    async def test_an_unmatched_profile_fails_and_a_missing_mode_warns(self, client: AsyncClient, db_session):
        no_mode = await profile(db_session, channels=0, model="Modeless")
        rig, rows = await make_rig(db_session, [{"profile": no_mode}])
        _, checks = await get(client, rig.id)
        assert checks["profiles"]["status"] == "warn"
        assert checks["profiles"]["fixture_ids"] == [rows[0].id]
        assert "16 channels" in checks["addresses"]["message"]

        rig2, rows2 = await make_rig(db_session, [{"tags": ["position_source:mvr", TAG_UNMATCHED]}, {}])
        _, checks2 = await get(client, rig2.id)
        assert checks2["profiles"]["status"] == "fail"
        assert checks2["profiles"]["fixture_ids"] == [rows2[0].id]

    @pytest.mark.asyncio
    async def test_a_fixture_outside_the_scanned_room_warns(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(
            db_session,
            [{"x": 0.0}, {"x": 6.2}, {"x": 9.0}, {"y": 7.0}, {"x": 40.0, "tags": [TAG_UNPLACED]}],
            room_shell=SCANNED_ROOM,
        )

        _, checks = await get(client, rig.id)

        assert checks["room"]["status"] == "warn"
        # 6.2 is within the 0.25 m of the 6 m wall; the unplaced one is not judged.
        assert checks["room"]["fixture_ids"] == sorted([rows[2].id, rows[3].id])

    @pytest.mark.asyncio
    async def test_the_notch_of_an_l_shaped_room_is_outside(self, client: AsyncClient, db_session):
        outline = [
            {"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": 6.0, "z": 0.0},
            {"x": 0.0, "z": 0.0}, {"x": 0.0, "z": 5.0}, {"x": -6.0, "z": 5.0},
        ]
        shell = {"source": "scan", "room": {**SCANNED_ROOM["room"], "outline": outline}}
        rig, rows = await make_rig(db_session, [{"x": -3.0, "z": 3.0}, {"x": 3.0, "z": 3.0}], room_shell=shell)

        _, checks = await get(client, rig.id)

        assert checks["room"]["fixture_ids"] == [rows[1].id]

    @pytest.mark.asyncio
    async def test_a_fixture_in_no_group_warns_and_offers_the_fix(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"group_name": None}, {"group_name": None, "tags": ["group:Extra"]}, {}])

        _, checks = await get(client, rig.id)

        assert checks["groups"]["status"] == "warn"
        assert checks["groups"]["fixture_ids"] == [rows[0].id]
        assert checks["groups"]["fix"] == "auto-groups"

    @pytest.mark.asyncio
    async def test_open_carry_over_entries_warn(self, client: AsyncClient, db_session):
        shell = {**SCANNED_ROOM, "pending_carry_over": [
            {"kind": "truss_lines", "new_index": 0, "message": "Truss 1 was called 'Main' before."},
        ]}
        rig, _ = await make_rig(db_session, [{}], room_shell=shell)

        _, checks = await get(client, rig.id)

        assert checks["carry_over"]["status"] == "warn"
        assert checks["carry_over"]["message"].startswith("1 edit made by hand")
        assert "Truss 1 was called 'Main' before." in checks["carry_over"]["message"]

    @pytest.mark.asyncio
    async def test_an_export_that_raises_fails_its_check(self, client: AsyncClient, db_session, monkeypatch):
        rig, _ = await make_rig(db_session, [{}])

        def broken(*args, **kwargs):
            raise ValueError("no room on the archive")

        monkeypatch.setattr(readiness_service, "mvr_bytes", broken)
        body, checks = await get(client, rig.id)

        assert checks["export_mvr"]["status"] == "fail"
        assert "no room on the archive" in checks["export_mvr"]["message"]
        assert checks["export_ma2"]["status"] == "ok"
        assert body["status"] == "fail"

    @pytest.mark.asyncio
    async def test_a_long_list_of_fixtures_is_capped(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(
            db_session,
            [{"group_name": None, "universe": i // 40, "dmx_address": 1 + (i % 40) * 10} for i in range(60)],
        )

        _, checks = await get(client, rig.id)

        assert checks["groups"]["fixture_count"] == 60
        assert len(checks["groups"]["fixture_ids"]) == readiness_service.FIXTURE_IDS_MAX


class TestMakeGroups:

    @pytest.mark.asyncio
    async def test_groups_are_made_by_place_and_kind(self, client: AsyncClient, db_session):
        wash = await profile(db_session, kind=FixtureType.WASH)
        rig, rows = await make_rig(db_session, [
            {"group_name": None, "x": -1.0, "z": 2.0},                       # front truss spot
            {"group_name": None, "x": 1.0, "z": 2.0},                        # front truss spot
            {"group_name": None, "x": -4.8, "y": 3.0, "profile": wash},      # SL tower wash
            {"group_name": None, "y": 0.2, "z": -1.0},                       # floor spot
            {"group_name": None, "tags": ["position_source:mvr", "hang_position:LX 2"]},
            {"group_name": None, "tags": [TAG_UNPLACED]},                    # left alone
            {"group_name": "Keep me"},
        ])

        response = await client.post(f"/api/rigs/{rig.id}/readiness/fix/auto-groups")

        assert response.status_code == 200, response.text
        body = response.json()
        made = {g["name"]: g["fixture_ids"] for g in body["created"]}
        assert made == {
            "Front truss Spots": [rows[0].id, rows[1].id],
            "SL tower Washes": [rows[2].id],
            "Floor Spots": [rows[3].id],
            "LX 2 Spots": [rows[4].id],
        }
        assert body["unplaced_ids"] == [rows[5].id]
        await db_session.refresh(rows[6])
        assert rows[6].group_name == "Keep me"
        await db_session.refresh(rows[5])
        assert rows[5].group_name is None
        assert all(c["group_before"] is None for c in body["changed"])

        _, checks = await get(client, rig.id)
        assert checks["groups"]["fixture_ids"] == [rows[5].id]

    @pytest.mark.asyncio
    async def test_a_named_scanned_truss_names_the_group(self, client: AsyncClient, db_session):
        shell = {**SCANNED_ROOM, "truss_lines": [
            {"name": "Mid Truss", "x1": -4.0, "z1": 0.0, "x2": 4.0, "z2": 0.0, "height": 5.0},
        ]}
        rig, rows = await make_rig(db_session, [{"group_name": None, "x": 1.0, "y": 4.8, "z": 0.1}], room_shell=shell)

        body = (await client.post(f"/api/rigs/{rig.id}/readiness/fix/auto-groups")).json()

        assert [g["name"] for g in body["created"]] == ["Mid Truss Spots"]

    @pytest.mark.asyncio
    async def test_a_name_the_rig_has_is_skipped(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [
            {"group_name": "front truss spots"},
            {"group_name": None, "x": 1.0, "z": 2.0},
        ])

        body = (await client.post(f"/api/rigs/{rig.id}/readiness/fix/auto-groups")).json()

        assert body["created"] == []
        assert body["skipped"] == [{"name": "front truss spots", "fixture_ids": [rows[1].id]}]
        assert body["changed"] == []
        await db_session.refresh(rows[1])
        assert rows[1].group_name is None

    @pytest.mark.asyncio
    async def test_a_second_call_changes_nothing(self, client: AsyncClient, db_session):
        rig, _ = await make_rig(db_session, [{"group_name": None, "z": 2.0}, {"group_name": None, "z": -3.0}])

        first = (await client.post(f"/api/rigs/{rig.id}/readiness/fix/auto-groups")).json()
        after_first = await snapshot(db_session, rig.id)
        second = (await client.post(f"/api/rigs/{rig.id}/readiness/fix/auto-groups")).json()

        assert len(first["created"]) == 2
        assert second["created"] == [] and second["changed"] == []
        assert "No group was needed" in second["message"]
        assert await snapshot(db_session, rig.id) == after_first

    @pytest.mark.asyncio
    async def test_the_liv_demo_rig_needs_no_groups(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        _, checks = await get(client, rig_id)
        before = await snapshot(db_session, rig_id)

        body = (await client.post(f"/api/rigs/{rig_id}/readiness/fix/auto-groups")).json()

        if checks["groups"]["status"] == "ok":
            assert body["changed"] == []
            assert await snapshot(db_session, rig_id) == before
        else:
            assert {c["id"] for c in body["changed"]} <= set(checks["groups"]["fixture_ids"]) | set(body["unplaced_ids"])
