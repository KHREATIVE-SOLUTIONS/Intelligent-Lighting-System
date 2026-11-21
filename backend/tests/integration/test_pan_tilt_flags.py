"""
Pan/Tilt Hang Flags, End to End
===============================

The three per-fixture flags have to survive every way a patch is written and
read: created, edited one at a time, saved in a batch from the floor plan,
duplicated, exported. They have to reach the engine fixture through the rig
loader. And a rig that was saved before the flags existed has to load exactly
as it did, with all three off - through a real migration of a real old schema,
because every other test database is built from today's models and cannot see
what an upgrade does to rows that are already there.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  - registers every table on Base.metadata
from app.models.rig import RigFixture
from app.schemas.rig import RigFixtureResponse
from app.services.rig.rig_loader import build_manager_for_rig_id


BACKEND_DIR = Path(__file__).resolve().parents[2]
FLAGS = ("pan_invert", "tilt_invert", "pan_tilt_swap")


def _flags(row) -> dict:
    return {name: row.get(name) for name in FLAGS}


ALL_OFF = {name: False for name in FLAGS}


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------

async def _rig_with_fixture(client: AsyncClient, sample_rig_data, sample_fixture_data, **patch):
    rig = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig.status_code == 201, rig.text
    rig_id = rig.json()["id"]

    profile = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert profile.status_code in (200, 201), profile.text

    added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
        "fixture_id": profile.json()["id"], "name": "Head", "universe": 0,
        "dmx_address": 1, **patch,
    })
    assert added.status_code == 201, added.text
    return rig_id, added.json()


async def _listed(client: AsyncClient, rig_id: int) -> dict:
    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text
    return {row["id"]: row for row in listed.json()}


async def test_a_new_patch_has_every_flag_off(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(client, sample_rig_data, sample_fixture_data)

    assert _flags(created) == ALL_OFF
    assert _flags((await _listed(client, rig_id))[created["id"]]) == ALL_OFF


async def test_a_patch_can_be_created_with_its_flags_set(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(
        client, sample_rig_data, sample_fixture_data, pan_invert=True, pan_tilt_swap=True,
    )

    expected = {"pan_invert": True, "tilt_invert": False, "pan_tilt_swap": True}
    assert _flags(created) == expected
    assert _flags((await _listed(client, rig_id))[created["id"]]) == expected


async def test_each_flag_can_be_set_and_cleared_on_its_own(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(client, sample_rig_data, sample_fixture_data)
    url = f"/api/rigs/{rig_id}/fixtures/{created['id']}"
    expected = dict(ALL_OFF)

    for name in FLAGS:
        response = await client.put(url, json={name: True})
        assert response.status_code == 200, response.text
        expected[name] = True
        assert _flags(response.json()) == expected, f"setting {name} disturbed another flag"

    for name in FLAGS:
        response = await client.put(url, json={name: False})
        assert response.status_code == 200, response.text
        expected[name] = False
        assert _flags((await _listed(client, rig_id))[created["id"]]) == expected


async def test_editing_something_else_leaves_the_flags_alone(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(
        client, sample_rig_data, sample_fixture_data, tilt_invert=True,
    )
    url = f"/api/rigs/{rig_id}/fixtures/{created['id']}"

    moved = await client.put(url, json={"position_x": 2.5})
    assert moved.status_code == 200, moved.text
    # A null is "not telling you", not "turn it off" - and never a failed write.
    nulled = await client.put(url, json={"tilt_invert": None, "name": "Renamed"})
    assert nulled.status_code == 200, nulled.text

    row = (await _listed(client, rig_id))[created["id"]]
    assert row["name"] == "Renamed"
    assert _flags(row) == {"pan_invert": False, "tilt_invert": True, "pan_tilt_swap": False}


async def test_the_floor_plan_batch_save_carries_the_flags(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(client, sample_rig_data, sample_fixture_data)
    url = f"/api/rigs/{rig_id}/fixtures/batch-update"

    saved = await client.put(url, json={
        "fixtures": [{"id": created["id"], "tilt_invert": True, "pan_tilt_swap": True}]
    })
    assert saved.status_code == 200, saved.text
    assert _flags((await _listed(client, rig_id))[created["id"]]) == {
        "pan_invert": False, "tilt_invert": True, "pan_tilt_swap": True,
    }

    # False is a value to store. The batch path skips empty values for its other
    # fields, which would make a flag impossible to turn back off.
    cleared = await client.put(url, json={
        "fixtures": [{"id": created["id"], "pan_tilt_swap": False}]
    })
    assert cleared.status_code == 200, cleared.text
    assert _flags((await _listed(client, rig_id))[created["id"]]) == {
        "pan_invert": False, "tilt_invert": True, "pan_tilt_swap": False,
    }


async def test_a_duplicated_fixture_is_hung_the_same_way(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, created = await _rig_with_fixture(
        client, sample_rig_data, sample_fixture_data, pan_invert=True, tilt_invert=True,
    )

    copied = await client.post(f"/api/rigs/{rig_id}/fixtures/duplicate/{created['id']}")
    assert copied.status_code == 200, copied.text

    copy = (await _listed(client, rig_id))[copied.json()["id"]]
    assert _flags(copy) == {"pan_invert": True, "tilt_invert": True, "pan_tilt_swap": False}


async def test_the_json_export_records_the_flags(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, _ = await _rig_with_fixture(
        client, sample_rig_data, sample_fixture_data, pan_tilt_swap=True,
    )

    exported = await client.get(f"/api/rigs/{rig_id}/export/json")
    assert exported.status_code == 200, exported.text

    (fixture,) = exported.json()["fixtures"]
    assert _flags(fixture) == {"pan_invert": False, "tilt_invert": False, "pan_tilt_swap": True}


# ---------------------------------------------------------------------------
# A rig saved before the flags existed
# ---------------------------------------------------------------------------

def _alembic(db_path: Path, revision: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade {revision} failed:\n{result.stdout}\n{result.stderr}"
    )


def _columns(connection, table: str):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


@pytest.fixture
def old_rig_db():
    """A database at the revision before the flags, holding a mirrored pair.

    The profile has no modes, so the loader drives it through its generic
    moving-head map: pan, pan fine, tilt, tilt fine on the first four channels.
    """
    tmpdir = tempfile.mkdtemp(prefix="ils-pan-tilt-migration-")
    path = Path(tmpdir) / "old_rig.db"
    _alembic(path, "005")

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO fixtures (id, manufacturer, model, fixture_type) "
            "VALUES (1, 'Test', 'Pre-flag Mover', 'MOVING_HEAD')"
        )
        connection.execute(
            "INSERT INTO rigs (id, name, stage_width, stage_depth, stage_height) "
            "VALUES (1, 'Saved Before The Flags', 10.0, 8.0, 6.0)"
        )
        for rf_id, address, x in ((1, 1, -3.0), (2, 21, 3.0)):
            connection.execute(
                "INSERT INTO rig_fixtures "
                "(id, rig_id, fixture_id, name, universe, dmx_address, "
                " position_x, position_y, position_z, is_active) "
                "VALUES (?, 1, 1, ?, 0, ?, ?, 5.0, 0.0, 1)",
                (rf_id, f"Head {rf_id}", address, x),
            )
        connection.commit()
        assert not set(FLAGS) & set(_columns(connection, "rig_fixtures")), (
            "revision 005 already has the flag columns; this is not an old rig"
        )
    finally:
        connection.close()

    yield path

    shutil.rmtree(tmpdir, ignore_errors=True)


def _aimed_frame(manager, pan: float, tilt: float):
    for fixture in manager.fixtures.values():
        fixture.pan, fixture.tilt = pan, tilt
    return manager.get_dmx_frame(0)


def test_the_migration_keeps_existing_rows_and_turns_every_flag_off(old_rig_db):
    connection = sqlite3.connect(old_rig_db)
    try:
        old_columns = _columns(connection, "rig_fixtures")
        select_sql = f"SELECT {', '.join(old_columns)} FROM rig_fixtures ORDER BY id"
        before = connection.execute(select_sql).fetchall()
    finally:
        connection.close()

    _alembic(old_rig_db, "head")

    connection = sqlite3.connect(old_rig_db)
    try:
        assert set(FLAGS) <= set(_columns(connection, "rig_fixtures"))
        assert connection.execute(select_sql).fetchall() == before, (
            "the migration changed rows that were already in the rig"
        )
        # 0, not NULL: the API's boolean fields would refuse a NULL and fail
        # the whole rig.
        assert connection.execute(
            "SELECT pan_invert, tilt_invert, pan_tilt_swap FROM rig_fixtures ORDER BY id"
        ).fetchall() == [(0, 0, 0), (0, 0, 0)]
    finally:
        connection.close()

    # Running it again must be harmless: a box that half-upgraded retries.
    _alembic(old_rig_db, "head")


async def test_an_old_rig_loads_with_the_flags_off_and_the_same_output(old_rig_db):
    _alembic(old_rig_db, "head")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{old_rig_db.as_posix()}", poolclass=NullPool,
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            manager = await build_manager_for_rig_id(session, 1)
            rows = (await session.execute(
                select(RigFixture).order_by(RigFixture.id)
            )).scalars().all()
            # What the rig endpoints do with each row's flags on the way out.
            responses = [
                RigFixtureResponse.model_validate({
                    "id": row.id, "rig_id": row.rig_id,
                    "fixture_id": row.fixture_id, "dmx_address": row.dmx_address,
                    **{name: getattr(row, name) for name in FLAGS},
                })
                for row in rows
            ]
    finally:
        await engine.dispose()

    assert len(manager.fixtures) == 2, "the old rig did not load"
    for fixture in manager.fixtures.values():
        assert (fixture.pan_invert, fixture.tilt_invert, fixture.pan_tilt_swap) == (False, False, False)
    for response in responses:
        assert (response.pan_invert, response.tilt_invert, response.pan_tilt_swap) == (False, False, False)

    # pan -154 of 540 -> 14078 = (54, 254); tilt 77 of 270 -> 51457 = (201, 1).
    # The bytes this rig sent before the flags existed.
    frame = _aimed_frame(manager, -154.0, 77.0)
    assert frame[0:4] == [54, 254, 201, 1]
    assert frame[20:24] == [54, 254, 201, 1]


async def test_a_flag_set_on_an_upgraded_rig_reaches_the_engine(old_rig_db):
    """The whole path on a rig that predates the flags: upgrade, mark the
    right-hand head as hung the other way, load, and the pair that used to
    sweep the same direction now mirrors."""
    _alembic(old_rig_db, "head")

    connection = sqlite3.connect(old_rig_db)
    try:
        connection.execute("UPDATE rig_fixtures SET pan_invert = 1 WHERE id = 2")
        connection.commit()
    finally:
        connection.close()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{old_rig_db.as_posix()}", poolclass=NullPool,
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            manager = await build_manager_for_rig_id(session, 1)
    finally:
        await engine.dispose()

    left, right = manager.fixtures["rf1"], manager.fixtures["rf2"]
    assert (left.pan_invert, right.pan_invert) == (False, True)
    assert (right.tilt_invert, right.pan_tilt_swap) == (False, False)

    # A mirrored look: equal and opposite pan. The right-hand head's pan runs
    # backwards, so the same bytes on both heads is what throws mirrored beams.
    left.pan, right.pan = 100.0, -100.0
    left.tilt = right.tilt = -40.0
    frame = manager.get_dmx_frame(0)

    left_pan = frame[0] * 256 + frame[1]
    right_pan = frame[20] * 256 + frame[21]
    assert left_pan == 44904
    assert abs(right_pan - left_pan) <= 1
    assert frame[2:4] == frame[22:24] == [90, 19]


# ---------------------------------------------------------------------------
# Retire is_inverted: copy it onto tilt_invert, delete no user data (Q20)
# ---------------------------------------------------------------------------

@pytest.fixture
def inverted_legacy_db():
    """A database at revision 006 with mixed is_inverted / hang-flag rows."""
    tmpdir = tempfile.mkdtemp(prefix="ils-is-inverted-migration-")
    path = Path(tmpdir) / "inverted_legacy.db"
    _alembic(path, "006")

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO fixtures (id, manufacturer, model, fixture_type) "
            "VALUES (1, 'Test', 'Inverted Legacy Mover', 'MOVING_HEAD')"
        )
        connection.execute(
            "INSERT INTO rigs (id, name, stage_width, stage_depth, stage_height) "
            "VALUES (1, 'Legacy Inverted Flag', 10.0, 8.0, 6.0)"
        )
        rows = (
            # id, address, is_inverted, pan_invert, tilt_invert, pan_tilt_swap
            (1, 1, 1, 0, 0, 0),    # should gain tilt_invert
            (2, 21, 1, 0, 1, 0),   # tilt already set; leave it, keep is_inverted
            (3, 41, 1, 1, 0, 0),   # map tilt, keep pan_invert
            (4, 61, 0, 0, 0, 0),   # untouched
            (5, 81, 1, 0, 0, 1),   # map tilt, keep swap
        )
        for rf_id, address, inverted, pan, tilt, swap in rows:
            connection.execute(
                "INSERT INTO rig_fixtures "
                "(id, rig_id, fixture_id, name, universe, dmx_address, "
                " position_x, position_y, position_z, is_active, "
                " is_inverted, pan_invert, tilt_invert, pan_tilt_swap) "
                "VALUES (?, 1, 1, ?, 0, ?, 0.0, 5.0, 0.0, 1, ?, ?, ?, ?)",
                (rf_id, f"Head {rf_id}", address, inverted, pan, tilt, swap),
            )
        connection.commit()
        assert "is_inverted" in _columns(connection, "rig_fixtures")
    finally:
        connection.close()

    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_is_inverted_is_copied_onto_tilt_invert_and_never_dropped(inverted_legacy_db):
    connection = sqlite3.connect(inverted_legacy_db)
    try:
        before = connection.execute(
            "SELECT id, is_inverted, pan_invert, tilt_invert, pan_tilt_swap "
            "FROM rig_fixtures ORDER BY id"
        ).fetchall()
        assert before == [
            (1, 1, 0, 0, 0),
            (2, 1, 0, 1, 0),
            (3, 1, 1, 0, 0),
            (4, 0, 0, 0, 0),
            (5, 1, 0, 0, 1),
        ]
    finally:
        connection.close()

    _alembic(inverted_legacy_db, "head")

    connection = sqlite3.connect(inverted_legacy_db)
    try:
        assert "is_inverted" in _columns(connection, "rig_fixtures"), (
            "the retirement migration dropped is_inverted"
        )
        after = connection.execute(
            "SELECT id, is_inverted, pan_invert, tilt_invert, pan_tilt_swap "
            "FROM rig_fixtures ORDER BY id"
        ).fetchall()
        assert after == [
            (1, 1, 0, 1, 0),
            (2, 1, 0, 1, 0),
            (3, 1, 1, 1, 0),
            (4, 0, 0, 0, 0),
            (5, 1, 0, 1, 1),
        ]
    finally:
        connection.close()

    # Running it again must be harmless.
    _alembic(inverted_legacy_db, "head")

    connection = sqlite3.connect(inverted_legacy_db)
    try:
        again = connection.execute(
            "SELECT id, is_inverted, pan_invert, tilt_invert, pan_tilt_swap "
            "FROM rig_fixtures ORDER BY id"
        ).fetchall()
        assert again == [
            (1, 1, 0, 1, 0),
            (2, 1, 0, 1, 0),
            (3, 1, 1, 1, 0),
            (4, 0, 0, 0, 0),
            (5, 1, 0, 1, 1),
        ]
    finally:
        connection.close()
