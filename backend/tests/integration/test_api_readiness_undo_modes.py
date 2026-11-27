"""
Undo for the readiness fixes, and the DMX modes check
=====================================================

POST /api/rigs/{id}/readiness/fix/undo puts back exactly what the last Make
groups or Re-address changed, as one step; refuses (409) and writes nothing
when a fixture it changed has been changed since; and with nothing to undo
answers so and writes nothing. The DMX modes check warns when a fixture's
footprint is only guessed and fails when its mode is not its profile's.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.rig import RigFixture
from tests.integration.test_api_readiness import get, imported_liv, make_rig, profile, readdress, snapshot

UNDO = "/api/rigs/{}/readiness/fix/undo"


async def undo(client, rig_id, status=200):
    response = await client.post(UNDO.format(rig_id))
    assert response.status_code == status, response.text
    return response.json()


async def groups(client, rig_id):
    response = await client.post(f"/api/rigs/{rig_id}/readiness/fix/auto-groups")
    assert response.status_code == 200, response.text
    return response.json()


def same_rig(a, b):
    """The rig and its fixtures as stored, but for the rig's updated_at (any write bumps it)."""
    (rig_a, rows_a), (rig_b, rows_b) = a, b
    drop = lambda rig: {k: v for k, v in rig.items() if k != "updated_at"}  # noqa: E731
    return drop(rig_a) == drop(rig_b) and rows_a == rows_b


class TestUndo:

    @pytest.mark.asyncio
    async def test_make_groups_is_undone_exactly(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [
            {"group_name": None, "x": -1.0, "z": 2.0},
            {"group_name": None, "x": 1.0, "z": -3.0},
            {"group_name": "Mine", "x": 0.0, "z": 0.0},
        ])
        before = await snapshot(db_session, rig.id)

        fixed = await groups(client, rig.id)
        assert len(fixed["changed"]) == 2
        assert fixed["undo"] == {"fix": "auto-groups", "label": "Undo Make groups", "count": 2}

        body = await undo(client, rig.id)

        assert body["fix"] == "auto-groups"
        assert sorted(r["id"] for r in body["restored"]) == [rows[0].id, rows[1].id]
        assert all(r["to"] == {"group_name": None} for r in body["restored"])
        assert body["message"] == "Undid Make groups: 2 fixtures back in no group."
        assert same_rig(await snapshot(db_session, rig.id), before)
        _, checks = await get(client, rig.id)
        assert checks["groups"]["status"] == "warn"

    @pytest.mark.asyncio
    async def test_re_address_is_undone_exactly(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"dmx_address": 1}, {"dmx_address": 5}, {"dmx_address": 30}])
        before = await snapshot(db_session, rig.id)

        fixed = await readdress(client, rig.id)
        assert [m["id"] for m in fixed["moves"]] == [rows[1].id]
        assert fixed["undo"]["fix"] == "readdress" and fixed["undo"]["count"] == 1

        body = await undo(client, rig.id)

        assert body["restored"] == [{
            "id": rows[1].id, "name": rows[1].name,
            "from": {"universe": 0, "dmx_address": 11}, "to": {"universe": 0, "dmx_address": 5},
        }]
        assert "on the fixture itself" in body["message"]
        assert same_rig(await snapshot(db_session, rig.id), before)
        _, checks = await get(client, rig.id)
        assert checks["addresses"]["status"] == "fail", "the clash the fix took away is back"

    @pytest.mark.asyncio
    async def test_the_liv_re_address_is_undone(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        before = await snapshot(db_session, rig_id)

        fixed = await readdress(client, rig_id)
        assert [m["name"] for m in fixed["moves"]] == ["Booth Wash 2"]
        body = await undo(client, rig_id)

        assert [(r["name"], r["to"]) for r in body["restored"]] == [
            ("Booth Wash 2", {"universe": 3, "dmx_address": 337}),
        ]
        assert same_rig(await snapshot(db_session, rig_id), before)

    @pytest.mark.asyncio
    async def test_a_fixture_changed_since_refuses_the_undo_and_writes_nothing(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [
            {"group_name": None, "x": -1.0, "z": 2.0},
            {"group_name": None, "x": 1.0, "z": -3.0},
        ])
        await groups(client, rig.id)
        rf = (await db_session.execute(select(RigFixture).where(RigFixture.id == rows[1].id))).scalar_one()
        rf.group_name = "Renamed by hand"
        await db_session.flush()
        before = await snapshot(db_session, rig.id)

        body = await undo(client, rig.id, status=409)

        detail = body["detail"]
        assert [s["id"] for s in detail["stale"]] == [rows[1].id]
        assert detail["stale"][0]["reason"] == "changed"
        assert detail["message"].startswith("Cannot undo Make groups: 1 of the fixtures it changed has been changed")
        assert "Nothing was put back" in detail["message"]
        assert await snapshot(db_session, rig.id) == before, "a refused undo writes nothing, not even half"

    @pytest.mark.asyncio
    async def test_a_moved_fixture_moved_again_refuses_the_re_address_undo(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"dmx_address": 1}, {"dmx_address": 5}])
        await readdress(client, rig.id)
        rf = (await db_session.execute(select(RigFixture).where(RigFixture.id == rows[1].id))).scalar_one()
        rf.dmx_address = 200
        await db_session.flush()

        body = await undo(client, rig.id, status=409)

        assert "Cannot undo Re-address" in body["detail"]["message"]
        await db_session.refresh(rf)
        assert rf.dmx_address == 200

    @pytest.mark.asyncio
    async def test_nothing_to_undo_is_a_no_op(self, client: AsyncClient, db_session):
        rig, _ = await make_rig(db_session, [{"group_name": None, "x": -1.0, "z": 2.0}])
        before = await snapshot(db_session, rig.id)

        body = await undo(client, rig.id)

        assert body["fix"] is None and body["restored"] == []
        assert body["message"].startswith("Nothing to undo")
        assert await snapshot(db_session, rig.id) == before

        await groups(client, rig.id)
        await undo(client, rig.id)
        after_undo = await snapshot(db_session, rig.id)
        again = await undo(client, rig.id)
        assert again["fix"] is None, "an undo is spent once taken"
        assert await snapshot(db_session, rig.id) == after_undo

    @pytest.mark.asyncio
    async def test_a_second_press_that_changes_nothing_keeps_the_undo(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"group_name": None, "x": -1.0, "z": 2.0}, {"dmx_address": 200}])
        before = await snapshot(db_session, rig.id)
        await groups(client, rig.id)

        second = await groups(client, rig.id)
        dry = await readdress(client, rig.id, dry_run=True)
        nothing = await readdress(client, rig.id)

        assert second["changed"] == [] and second["undo"]["fix"] == "auto-groups"
        assert dry["undo"]["fix"] == "auto-groups", "a dry run records nothing"
        assert nothing["moves"] == [] and nothing["undo"]["fix"] == "auto-groups"
        assert (await undo(client, rig.id))["fix"] == "auto-groups"
        assert same_rig(await snapshot(db_session, rig.id), before)

    @pytest.mark.asyncio
    async def test_only_the_last_fix_is_undone(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [
            {"group_name": None, "x": -1.0, "z": 2.0, "dmx_address": 1},
            {"dmx_address": 5},
        ])
        await groups(client, rig.id)
        await readdress(client, rig.id)

        body = await undo(client, rig.id)

        assert body["fix"] == "readdress"
        for rf in rows:
            await db_session.refresh(rf)
        assert rows[1].dmx_address == 5
        assert rows[0].group_name is not None, "Make groups was the fix before: it stays"
        assert (await undo(client, rig.id))["fix"] is None


class TestModes:

    @pytest.mark.asyncio
    async def test_a_mode_of_the_profile_is_ok(self, client: AsyncClient, db_session):
        rig, _ = await make_rig(db_session, [{}, {"dmx_address": 20}])

        _, checks = await get(client, rig.id)

        assert checks["modes"]["status"] == "ok"
        assert checks["modes"]["title"] == "DMX modes"
        assert checks["modes"]["fixture_ids"] == []

    @pytest.mark.asyncio
    async def test_no_mode_warns_that_the_footprint_is_guessed(self, client: AsyncClient, db_session):
        no_mode = await profile(db_session, channels=0, model="Modeless")
        rig, rows = await make_rig(db_session, [{}, {"profile": no_mode, "name": "Old Par", "dmx_address": 20}])

        _, checks = await get(client, rig.id)

        check = checks["modes"]
        assert check["status"] == "warn"
        assert check["fixture_ids"] == [rows[1].id]
        assert check["message"] == (
            "1 fixture have no DMX mode set (Old Par), so each one's footprint is only guessed "
            "as 16 channels. Pick the mode each fixture is set to."
        )

    @pytest.mark.asyncio
    async def test_a_mode_of_another_profile_fails(self, client: AsyncClient, db_session):
        spot, _ = await profile(db_session, channels=10, model="Spot A")
        _, wash_mode = await profile(db_session, channels=24, model="Wash B")
        no_mode = await profile(db_session, channels=0, model="Modeless")
        rig, rows = await make_rig(db_session, [
            {"profile": (spot, wash_mode), "name": "Mixed up"},
            {"profile": no_mode, "dmx_address": 100},
        ])

        _, checks = await get(client, rig.id)

        check = checks["modes"]
        assert check["status"] == "fail"
        assert check["fixture_ids"] == sorted([rows[0].id, rows[1].id])
        assert "Mixed up: mode '24ch' (24ch)" in check["message"]
        assert "not a mode of their profile" in check["message"]
        assert "guessed as 16 channels" in check["message"]

    @pytest.mark.asyncio
    async def test_a_mode_id_that_points_at_no_mode_fails(self, client: AsyncClient, db_session):
        rig, rows = await make_rig(db_session, [{"name": "Lost mode"}])
        rf = (await db_session.execute(select(RigFixture).where(RigFixture.id == rows[0].id))).scalar_one()
        rig_id = rig.id
        rf.mode_id = 987654
        await db_session.flush()
        db_session.expire_all()  # so the endpoint loads rf.mode afresh, finding none

        _, checks = await get(client, rig_id)

        assert checks["modes"]["status"] == "fail"
        assert "mode id 987654, which no longer exists" in checks["modes"]["message"]

    @pytest.mark.asyncio
    async def test_the_liv_demo_rig_has_its_profiles_modes(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        rows = (await db_session.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))).scalars().all()

        _, checks = await get(client, rig_id)

        # 34 of the 36 come in with a mode of their matched profile. The two
        # with none (the Booth Washes) matched no profile: the profiles check
        # fails them, and the modes check leaves them to it.
        no_mode = sorted(rf.id for rf in rows if rf.mode_id is None)
        assert len(rows) == 36 and len(no_mode) == 2
        assert checks["profiles"]["status"] == "fail"
        assert checks["profiles"]["fixture_ids"] == no_mode
        assert checks["modes"]["status"] == "ok", checks["modes"]["message"]

        # Give one matched fixture another profile's mode: now it fails, naming it.
        other = next(rf for rf in rows if rf.mode_id is not None)
        foreign = next(rf for rf in rows if rf.mode_id is not None and rf.fixture_id != other.fixture_id)
        other_id, other.mode_id = other.id, foreign.mode_id
        await db_session.flush()
        db_session.expire_all()
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "fail"
        assert checks["modes"]["fixture_ids"] == [other_id]
