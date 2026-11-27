"""
Set modes: the fix for the DMX modes check
==========================================

POST /api/rigs/{id}/readiness/fix/set-modes sets the DMX mode of each fixture
the DMX modes check names, but only where one mode is unambiguous: the
profile's only mode, or exactly one mode of the fixture's present footprint
or address span. Everything else is listed to pick by hand and never
changed. It never moves an address, says when a new footprint would clash,
and is one step of the readiness undo (409 when a fixture changed since).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.fixture import FixtureMode
from app.models.rig import RigFixture
from tests.integration.test_api_readiness import get, imported_liv, make_rig, profile, snapshot
from tests.integration.test_api_readiness_undo_modes import same_rig, undo

SET_MODES = "/api/rigs/{}/readiness/fix/set-modes"


async def set_modes(client, rig_id, dry_run=False):
    response = await client.post(SET_MODES.format(rig_id), params={"dry_run": "true"} if dry_run else None)
    assert response.status_code == 200, response.text
    return response.json()


async def multi_mode(db, counts, model):
    """A profile with one mode per channel count in `counts`."""
    fixture, first = await profile(db, channels=counts[0], model=model)
    modes = [first]
    for n in counts[1:]:
        mode = FixtureMode(fixture_id=fixture.id, name=f"{n}ch", channel_count=n)
        db.add(mode)
        modes.append(mode)
    await db.flush()
    return fixture, modes


async def fixture_row(db, rf_id):
    db.expire_all()
    return (await db.execute(select(RigFixture).where(RigFixture.id == rf_id))).scalar_one()


class TestThePlan:

    @pytest.mark.asyncio
    async def test_a_profile_with_one_mode_is_set_to_it(self, client: AsyncClient, db_session):
        par, mode = await profile(db_session, channels=12, model="One mode par")
        rig, rows = await make_rig(db_session, [{}, {"profile": (par, None), "name": "Old Par", "dmx_address": 100}])
        rig_id, mode_id, old_par = rig.id, mode.id, rows[1].id
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "warn" and checks["modes"]["fix"] == "set-modes"

        body = await set_modes(client, rig_id)

        assert [(p["id"], p["mode_id"], p["reason"], p["channel_count"]) for p in body["proposals"]] == [
            (old_par, mode_id, "only_mode", 12),
        ]
        assert body["proposals"][0]["channel_count_before"] == 16, "the guess it replaces"
        assert body["by_hand"] == [] and body["clashes"] == []
        assert body["undo"] == {"fix": "set-modes", "label": "Undo Set modes", "count": 1}
        assert body["message"] == "Set the DMX mode of 1 fixture: Old Par to 12ch (12ch)."
        rf = await fixture_row(db_session, old_par)
        assert rf.mode_id == mode_id and rf.dmx_address == 100
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "ok" and checks["modes"]["fix"] is None

    @pytest.mark.asyncio
    async def test_a_foreign_mode_is_replaced_by_the_profiles_mode_of_the_same_footprint(self, client: AsyncClient, db_session):
        spot, modes = await multi_mode(db_session, [8, 24, 40], "Three mode spot")
        _, wash_24 = await profile(db_session, channels=24, model="Wash B")
        rig, rows = await make_rig(db_session, [{"profile": (spot, wash_24), "name": "Mixed up", "dmx_address": 1}])

        body = await set_modes(client, rig.id, dry_run=True)

        (p,) = body["proposals"]
        assert (p["id"], p["mode_id"], p["reason"], p["problem"]) == (rows[0].id, modes[1].id, "footprint", "foreign")
        assert p["mode_id_before"] == wash_24.id and p["mode_name_before"] == "24ch"

    @pytest.mark.asyncio
    async def test_no_mode_takes_the_one_mode_that_fills_its_address_span(self, client: AsyncClient, db_session):
        par, modes = await multi_mode(db_session, [8, 12], "Two mode par")
        rig, rows = await make_rig(db_session, [
            {"profile": (par, None), "name": "Par 1", "dmx_address": 1},
            {"dmx_address": 13},
        ])

        body = await set_modes(client, rig.id, dry_run=True)

        assert [(p["id"], p["mode_id"], p["reason"]) for p in body["proposals"]] == [
            (rows[0].id, modes[1].id, "address_span"),
        ]

    @pytest.mark.asyncio
    async def test_an_ambiguous_fixture_is_left_to_pick_by_hand(self, client: AsyncClient, db_session):
        par, modes = await multi_mode(db_session, [8, 12], "Two mode par")
        twins, _ = await multi_mode(db_session, [10, 10], "Two 10ch modes")
        modeless = await profile(db_session, channels=0, model="Modeless")
        rig, rows = await make_rig(db_session, [
            {"profile": (twins, None), "name": "Twin", "dmx_address": 1},       # span 10: both modes fit
            {"profile": modeless, "name": "Empty", "dmx_address": 11},          # no modes at all
            {"profile": (par, None), "name": "Last par", "dmx_address": 300},   # last in its universe: no span
        ])
        rig_id = rig.id
        before = await snapshot(db_session, rig_id)

        body = await set_modes(client, rig_id)

        assert body["proposals"] == []
        hand = {b["name"]: b for b in body["by_hand"]}
        assert sorted(hand) == ["Empty", "Last par", "Twin"]
        assert [c["channel_count"] for c in hand["Last par"]["candidates"]] == [8, 12]
        assert [c["id"] for c in hand["Twin"]["candidates"]] == sorted(m.id for m in (await db_session.execute(
            select(FixtureMode).where(FixtureMode.fixture_id == twins.id))).scalars())
        assert hand["Empty"]["candidates"] == [] and "no DMX modes" in hand["Empty"]["why"]
        assert "picked by hand" in body["message"]
        assert body["undo"] is None, "nothing changed, nothing to undo"
        assert await snapshot(db_session, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_new_footprint_that_clashes_is_reported_and_no_address_moves(self, client: AsyncClient, db_session):
        big, mode = await profile(db_session, channels=24, model="Big wash")
        rig, rows = await make_rig(db_session, [
            {"profile": (big, None), "name": "Big", "dmx_address": 1},   # guessed 1-16, really 1-24
            {"name": "Neighbour", "dmx_address": 17},
            {"profile": (big, None), "name": "Edge", "dmx_address": 500},  # 500-523: past 512
        ])
        rig_id, ids = rig.id, [rf.id for rf in rows]
        _, checks = await get(client, rig_id)
        assert checks["addresses"]["status"] == "warn", "a past-end guess only warns"

        dry = await set_modes(client, rig_id, dry_run=True)
        body = await set_modes(client, rig_id)

        for answer in (dry, body):
            kinds = sorted((c["kind"], tuple(c["names"])) for c in answer["clashes"])
            assert kinds == [("overlap", ("Big", "Neighbour")), ("past_end", ("Edge",))]
            assert "run Re-address" in answer["message"]
        assert "would show" in dry["message"] and "will show" in body["message"]
        for rf_id, address in zip(ids, (1, 17, 500)):
            assert (await fixture_row(db_session, rf_id)).dmx_address == address
        _, checks = await get(client, rig_id)
        assert checks["addresses"]["status"] == "fail", "the clash is real now the footprint is known"


class TestWritesAndUndo:

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self, client: AsyncClient, db_session):
        par, _ = await profile(db_session, channels=12, model="One mode par")
        rig, rows = await make_rig(db_session, [{"profile": (par, None), "name": "Old Par"}])
        rig_id = rig.id
        before = await snapshot(db_session, rig_id)

        body = await set_modes(client, rig_id, dry_run=True)

        assert body["dry_run"] is True and len(body["proposals"]) == 1
        assert body["message"].startswith("Would set the DMX mode of 1 fixture")
        assert body["undo"] is None
        assert await snapshot(db_session, rig_id) == before

    @pytest.mark.asyncio
    async def test_undo_restores_exactly(self, client: AsyncClient, db_session):
        par, _ = await profile(db_session, channels=12, model="One mode par")
        spot, modes = await multi_mode(db_session, [8, 24], "Two mode spot")
        _, wash_24 = await profile(db_session, channels=24, model="Wash B")
        rig, rows = await make_rig(db_session, [
            {"profile": (par, None), "name": "Old Par", "dmx_address": 1},
            {"profile": (spot, wash_24), "name": "Mixed up", "dmx_address": 100},
        ])
        rig_id = rig.id
        before = await snapshot(db_session, rig_id)
        fixed = await set_modes(client, rig_id)
        assert len(fixed["proposals"]) == 2

        body = await undo(client, rig_id)

        assert body["fix"] == "set-modes"
        assert sorted((r["id"], r["to"]["mode_id"]) for r in body["restored"]) == [
            (rows[0].id, None), (rows[1].id, wash_24.id),
        ]
        assert body["message"].startswith("Undid Set modes: 2 fixtures back on the DMX mode")
        assert same_rig(await snapshot(db_session, rig_id), before)
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "fail", "the foreign mode is back"

    @pytest.mark.asyncio
    async def test_undo_reads_the_restored_mode_without_a_fresh_session(self, client: AsyncClient, db_session):
        par, _ = await profile(db_session, channels=12, model="One mode par")
        rig, _ = await make_rig(db_session, [{"profile": (par, None), "name": "Old Par"}])
        rig_id = rig.id

        await set_modes(client, rig_id)
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "ok"
        await undo(client, rig_id)
        _, checks = await get(client, rig_id)

        assert checks["modes"]["status"] == "warn", "the check sees the mode undo put back, not the one it had loaded"

    @pytest.mark.asyncio
    async def test_a_mode_changed_since_refuses_the_undo_and_writes_nothing(self, client: AsyncClient, db_session):
        par, modes = await multi_mode(db_session, [12, 20], "Two mode par")
        rig, rows = await make_rig(db_session, [
            {"profile": (par, None), "name": "Par 1", "dmx_address": 1},
            {"dmx_address": 13},
        ])
        rig_id, par_1, mode_12, mode_20 = rig.id, rows[0].id, modes[0].id, modes[1].id
        await set_modes(client, rig_id)
        rf = await fixture_row(db_session, par_1)
        assert rf.mode_id == mode_12
        rf.mode_id = mode_20  # picked by hand afterwards
        await db_session.flush()
        before = await snapshot(db_session, rig_id)

        body = await undo(client, rig_id, status=409)

        detail = body["detail"]
        assert [s["id"] for s in detail["stale"]] == [par_1]
        assert detail["message"] == (
            "Cannot undo Set modes: 1 of the fixtures it changed has been changed or removed since (Par 1). "
            "Nothing was put back. Set the DMX mode by hand."
        )
        assert await snapshot(db_session, rig_id) == before

    @pytest.mark.asyncio
    async def test_a_second_press_changes_nothing_and_keeps_the_undo(self, client: AsyncClient, db_session):
        par, _ = await profile(db_session, channels=12, model="One mode par")
        rig, _ = await make_rig(db_session, [{"profile": (par, None), "name": "Old Par"}])
        rig_id = rig.id
        await set_modes(client, rig_id)

        again = await set_modes(client, rig_id)

        assert again["proposals"] == [] and again["by_hand"] == []
        assert again["message"].startswith("Nothing to set")
        assert again["undo"]["fix"] == "set-modes"


class TestLiv:

    @pytest.mark.asyncio
    async def test_the_liv_demo_rig(self, client: AsyncClient, db_session):
        rig_id = await imported_liv(client)
        before = await snapshot(db_session, rig_id)

        # As imported, every matched fixture has its profile's mode: nothing to set,
        # and the two unmatched Booth Washes are left to the Fixture profiles check.
        plain = await set_modes(client, rig_id)
        assert plain["proposals"] == [] and plain["by_hand"] == [] and plain["clashes"] == []
        assert plain["undo"] is None
        assert await snapshot(db_session, rig_id) == before

        # Lose one matched fixture's mode: Set modes finds it again when its profile allows one answer.
        rows = (await db_session.execute(select(RigFixture).where(RigFixture.rig_id == rig_id))).scalars().all()
        victim = next(rf for rf in rows if rf.mode_id is not None)
        victim_id, original, profile_id = victim.id, victim.mode_id, victim.fixture_id
        names = {rf.id: rf.name for rf in rows}
        victim.mode_id = None
        await db_session.flush()
        db_session.expire_all()
        modes = (await db_session.execute(
            select(FixtureMode).where(FixtureMode.fixture_id == profile_id))).scalars().all()
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "warn" and checks["modes"]["fixture_ids"] == [victim_id]

        body = await set_modes(client, rig_id, dry_run=True)

        booth = {i for i, n in names.items() if n and n.startswith("Booth Wash")}
        assert not booth & {p["id"] for p in body["proposals"] + body["by_hand"]}
        # Its profile has two modes (Standard 16ch, Extended 18ch): the next fixture starts
        # 16 channels on, so the address span names the mode it lost.
        assert sorted(m.channel_count for m in modes) == [16, 18]
        assert [(p["id"], p["mode_id"], p["reason"]) for p in body["proposals"]] == [
            (victim_id, original, "address_span"),
        ]
        assert body["by_hand"] == [] and body["clashes"] == []
        await set_modes(client, rig_id)
        assert (await fixture_row(db_session, victim_id)).mode_id == original
        _, checks = await get(client, rig_id)
        assert checks["modes"]["status"] == "ok"
        assert (await undo(client, rig_id))["fix"] == "set-modes"
        _, checks = await get(client, rig_id)
        assert checks["modes"]["fixture_ids"] == [victim_id], "undo takes the mode off again"
