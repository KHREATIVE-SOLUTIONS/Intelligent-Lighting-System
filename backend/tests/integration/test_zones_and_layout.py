"""
Zones and the Floor Plan
========================

Two things a non-expert can actually tell the software: where a light is, and
what it points at. Both have to survive being written down.

A zone is the only way an owner who has never patched a console can say "this
one is on the singer", so it has to reach the engine fixture rather than stop at
the database. A position dragged on the floor plan has to come back identical
after a reload. And a rig that names no zones at all has to behave exactly as it
did before any of this existed - silently changing an existing rig is the worst
outcome of the zone work.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  - registers every table on Base.metadata
from app.db.database import Base
from app.models.fixture import (
    ChannelType,
    Fixture as FixtureProfile,
    FixtureChannel,
    FixtureMode,
    FixtureType,
)
from app.models.rig import Rig, RigFixture
from app.services.effects import EffectsConfig, EffectsEngine
from app.services.lighting.key_lighting import KeyLightConfig, PerformerZone
from app.services.rig.rig_loader import build_manager_for_rig_id


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEV_DATABASE = BACKEND_DIR / "lighting_dev.db"

# Contract section 3: the performer zones the engine already knows, plus the
# areas a bar owner names that are not a performer at all.
PERFORMER_ZONES = {
    "dj_booth", "stage_center", "stage_left", "stage_right",
    "drum_riser", "keyboard", "downstage_center",
}
VENUE_ZONES = {"dance_floor", "bar", "audience", "entrance"}


def _zone_value(zone):
    """Zones cross the loader as either the enum or its string value."""
    return getattr(zone, "value", zone)


# ---------------------------------------------------------------------------
# A throwaway database holding one drivable fixture profile
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def zone_db_path():
    tmpdir = tempfile.mkdtemp(prefix="ils-zones-")
    path = Path(tmpdir) / "zones.db"

    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)

    session = sessionmaker(bind=engine)()
    try:
        profile = FixtureProfile(
            manufacturer="Test",
            model="Zone Par",
            fixture_type=FixtureType.LED_PAR,
            source_id="test-zones-par",
        )
        session.add(profile)
        session.flush()

        mode = FixtureMode(fixture_id=profile.id, name="4-Channel", channel_count=4)
        session.add(mode)
        session.flush()

        for number, channel_type in enumerate(
            (ChannelType.DIMMER, ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE),
            start=1,
        ):
            session.add(FixtureChannel(
                mode_id=mode.id,
                channel_number=number,
                channel_type=channel_type,
                name=channel_type.value,
            ))
        session.commit()
    finally:
        session.close()
        engine.dispose()

    yield path

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest_asyncio.fixture
async def db(zone_db_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{zone_db_path.as_posix()}",
        poolclass=NullPool,
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _profile(db: AsyncSession) -> FixtureProfile:
    result = await db.execute(
        select(FixtureProfile)
        .where(FixtureProfile.source_id == "test-zones-par")
        .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
    )
    return result.scalar_one()


async def _rig(db: AsyncSession, name: str, rows) -> Rig:
    rig = Rig(name=name, universes=[], is_active=False)
    db.add(rig)
    await db.flush()
    for row in rows:
        db.add(RigFixture(rig_id=rig.id, **row))
    await db.commit()
    return rig


def _by_name(manager, name):
    for fixture in manager.fixtures.values():
        if fixture.name == name:
            return fixture
    raise AssertionError(f"{name} is not in the manager: {[f.name for f in manager.fixtures.values()]}")


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

def test_the_zone_vocabulary_covers_the_areas_a_bar_owner_names():
    values = {zone.value for zone in PerformerZone}

    assert PERFORMER_ZONES <= values, (
        f"the engine lost performer zones: {sorted(PERFORMER_ZONES - values)}"
    )
    assert VENUE_ZONES <= values, (
        f"a bar owner cannot name {sorted(VENUE_ZONES - values)}, which are the "
        f"areas they actually light"
    )


# ---------------------------------------------------------------------------
# A zone survives the round trip and reaches the engine
# ---------------------------------------------------------------------------

async def test_a_zone_survives_the_database_round_trip(db):
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Zoned Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Floor Wash",
             universe=0, dmx_address=11, zone="dance_floor"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Unzoned",
             universe=0, dmx_address=21),
    ])

    # Detached, so the rows come back from SQLite rather than the identity map.
    db.expunge_all()
    result = await db.execute(
        select(RigFixture).where(RigFixture.rig_id == rig.id).order_by(RigFixture.dmx_address)
    )
    rows = result.scalars().all()

    assert [_zone_value(row.zone) for row in rows] == ["stage_center", "dance_floor", None]


async def test_a_zone_reaches_the_engine_fixture_through_rig_loader(db):
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Loader Zone Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Unzoned",
             universe=0, dmx_address=11),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert _zone_value(getattr(_by_name(manager, "Singer Key"), "zone", None)) == "stage_center", (
        "the zone stopped at the database; the engine fixture cannot be kept lit "
        "for a performer it does not know about"
    )
    assert _zone_value(getattr(_by_name(manager, "Unzoned"), "zone", None)) is None


async def test_key_lighting_treats_a_zoned_fixture_differently_from_an_unzoned_one(db):
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Key Light Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Back Wash",
             universe=0, dmx_address=11),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    zoned = _by_name(manager, "Singer Key").id
    unzoned = _by_name(manager, "Back Wash").id

    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)

    assigned = engine.key_lighting.get_zone_fixtures(PerformerZone.STAGE_CENTER)
    assert zoned in assigned, (
        "a DB rig's zoned fixture never reaches key_lighting.assign_fixtures, so "
        "only the five hardcoded demo presets can keep a performer lit"
    )
    assert unzoned not in assigned

    engine.key_lighting.configure_zone(
        PerformerZone.STAGE_CENTER,
        KeyLightConfig(zone=PerformerZone.STAGE_CENTER, min_intensity=0.6, active=True),
    )

    override = engine.key_lighting.get_key_light_override(zoned, 0.0, 0.0, 0.0, 0.0)
    assert override is not None, "the zoned fixture is not held above the zone floor"
    assert override["dimmer"] == pytest.approx(0.6)

    assert engine.key_lighting.get_key_light_override(unzoned, 0.0, 0.0, 0.0, 0.0) is None, (
        "an unzoned fixture must never inherit another zone's intensity floor"
    )


# ---------------------------------------------------------------------------
# A rig with no zones is untouched
# ---------------------------------------------------------------------------

async def test_a_rig_with_no_zones_behaves_exactly_as_before(db):
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Zoneless Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Par 1",
             universe=0, dmx_address=1),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Par 2",
             universe=0, dmx_address=11),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    for fixture in manager.fixtures.values():
        assert _zone_value(getattr(fixture, "zone", None)) is None
        fixture.dimmer = 1.0
        fixture.red = 1.0

    before = manager.get_dmx_frame(0)
    assert before[0] == 255 and before[1] == 255
    assert before[10] == 255 and before[11] == 255

    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)

    assert engine.key_lighting.get_active_zones() == [], (
        "loading a rig that names no zones activated one anyway"
    )
    for fixture_id in manager.fixtures:
        assert engine.key_lighting.get_key_light_override(
            fixture_id, 0.0, 0.0, 0.0, 0.0
        ) is None, f"{fixture_id} picked up an intensity floor it never asked for"

    assert manager.get_dmx_frame(0) == before, (
        "loading the rig through the zone path changed its output"
    )

    for fixture in manager.fixtures.values():
        fixture.dimmer = 0.0
        fixture.red = 0.0
    assert max(manager.get_dmx_frame(0)) == 0, (
        "a rig with no zones must still be able to reach a real blackout"
    )


# ---------------------------------------------------------------------------
# The floor plan save path
# ---------------------------------------------------------------------------

async def _patched_rig(client: AsyncClient, sample_rig_data, sample_fixture_data, count=3):
    """A rig with `count` patched fixtures, created through the public API."""
    rig_response = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig_response.status_code == 201, rig_response.text
    rig_id = rig_response.json()["id"]

    fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert fixture_response.status_code in (200, 201), fixture_response.text
    fixture_id = fixture_response.json()["id"]

    rig_fixture_ids = []
    for index in range(count):
        added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": fixture_id,
            "name": f"Par {index + 1}",
            "universe": 0,
            "dmx_address": 1 + index * 20,
            "position_x": 0.0,
            "position_y": 0.0,
            "position_z": 0.0,
        })
        assert added.status_code == 201, added.text
        rig_fixture_ids.append(added.json()["id"])

    return rig_id, rig_fixture_ids


async def test_the_batch_update_endpoint_persists_dragged_positions(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    """Dragging an icon on the plan is the one interaction that needs no lighting
    knowledge, and it is the one that has to come back after a reload."""
    rig_id, rig_fixture_ids = await _patched_rig(
        client, sample_rig_data, sample_fixture_data
    )

    dragged = {
        rig_fixture_ids[0]: {"position_x": -4.25, "position_y": 5.5, "position_z": -3.75},
        rig_fixture_ids[1]: {"position_x": 0.0, "position_y": 5.5, "position_z": 2.5},
        rig_fixture_ids[2]: {"position_x": 4.25, "position_y": 0.0, "position_z": -3.75},
    }

    response = await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={
        "fixtures": [{"id": rf_id, **position} for rf_id, position in dragged.items()]
    })
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == len(dragged)

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    assert listed.status_code == 200, listed.text

    read_back = {row["id"]: row for row in listed.json()}
    for rf_id, position in dragged.items():
        row = read_back[rf_id]
        for axis, value in position.items():
            assert row[axis] == value, (
                f"fixture {rf_id} was dragged to {axis}={value} and reads back "
                f"{row[axis]}"
            )


async def test_the_batch_update_endpoint_persists_a_zone(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    """The floor plan is where the owner says what a light points at, so the save
    path must not drop the zone the way it dropped the position."""
    rig_id, rig_fixture_ids = await _patched_rig(
        client, sample_rig_data, sample_fixture_data, count=2
    )

    response = await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={
        "fixtures": [{"id": rig_fixture_ids[0], "zone": "dance_floor"}]
    })
    assert response.status_code == 200, response.text

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    read_back = {row["id"]: row for row in listed.json()}

    assert read_back[rig_fixture_ids[0]].get("zone") == "dance_floor", (
        "the batch-update whitelist in app/api/endpoints/rigs.py silently drops "
        "zone, so assigning one on the floor plan does nothing"
    )
    assert read_back[rig_fixture_ids[1]].get("zone") is None


# ---------------------------------------------------------------------------
# Migration 005
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
    return result


def _columns(connection, table: str):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


@pytest.fixture
def migration_db():
    tmpdir = tempfile.mkdtemp(prefix="ils-migration-")
    yield Path(tmpdir) / "migration.db"
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_migration_005_preserves_existing_rig_fixture_rows(migration_db):
    _alembic(migration_db, "004")

    connection = sqlite3.connect(migration_db)
    try:
        connection.execute(
            "INSERT INTO fixtures (id, manufacturer, model, fixture_type) "
            "VALUES (1, 'Test', 'Pre-migration Par', 'led_par')"
        )
        connection.execute(
            "INSERT INTO rigs (id, name, stage_width, stage_depth, stage_height) "
            "VALUES (1, 'Existing Rig', 10.0, 8.0, 6.0)"
        )
        for rf_id, address, x, z, group in (
            (1, 1, -3.5, -2.0, 'Front Wash'),
            (2, 21, 0.0, 0.0, 'Movers'),
            (3, 41, 3.5, 2.0, None),
        ):
            connection.execute(
                "INSERT INTO rig_fixtures "
                "(id, rig_id, fixture_id, name, universe, dmx_address, "
                " position_x, position_y, position_z, group_name, is_active) "
                "VALUES (?, 1, 1, ?, 0, ?, ?, 4.0, ?, ?, 1)",
                (rf_id, f"Par {rf_id}", address, x, z, group),
            )
        connection.commit()

        columns = _columns(connection, "rig_fixtures")
        assert "zone" not in columns
        select_sql = f"SELECT {', '.join(columns)} FROM rig_fixtures ORDER BY id"
        before = connection.execute(select_sql).fetchall()
        rigs_before = connection.execute("SELECT * FROM rigs ORDER BY id").fetchall()
        assert len(before) == 3
    finally:
        connection.close()

    _alembic(migration_db, "head")

    connection = sqlite3.connect(migration_db)
    try:
        after_columns = _columns(connection, "rig_fixtures")
        assert "zone" in after_columns, (
            "migration 005 did not add the zone column to rig_fixtures"
        )
        assert connection.execute(select_sql).fetchall() == before, (
            "migration 005 changed rows that were already in the rig"
        )
        assert connection.execute("SELECT * FROM rigs ORDER BY id").fetchall() == rigs_before
        assert connection.execute(
            "SELECT COUNT(*) FROM rig_fixtures WHERE zone IS NOT NULL"
        ).fetchone()[0] == 0, "migration 005 invented a zone for an existing fixture"
    finally:
        connection.close()


def test_migration_005_preserves_a_real_development_database(migration_db):
    """The upgrade a venue's own box will run, on the database this repo ships."""
    if not DEV_DATABASE.exists():
        pytest.skip(f"no development database at {DEV_DATABASE}")

    shutil.copyfile(DEV_DATABASE, migration_db)

    connection = sqlite3.connect(migration_db)
    try:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("fixtures", "fixture_modes", "fixture_channels", "rigs", "rig_fixtures")
        }
        fixtures_before = connection.execute(
            "SELECT id, manufacturer, model, fixture_type FROM fixtures ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    assert before["fixtures"] > 0, "the development database has no fixtures to preserve"

    _alembic(migration_db, "head")

    connection = sqlite3.connect(migration_db)
    try:
        for table, count in before.items():
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == count, f"the upgrade lost rows from {table}"
        assert connection.execute(
            "SELECT id, manufacturer, model, fixture_type FROM fixtures ORDER BY id"
        ).fetchall() == fixtures_before
        assert "zone" in _columns(connection, "rig_fixtures")
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# The floor a zone actually gets, and taking a zone back off
# ---------------------------------------------------------------------------
#
# Every test above that asserted a floor also supplied it, so setting every
# default to 0.0 - or to 1.0 - left the file green. These read the value the
# implementation gives.

async def test_declaring_a_zone_does_not_impose_a_light_level_of_its_own(db):
    """A zone says where a light points, not how bright it must stay.

    Every shipped venue preset holds its zones at 0.0 and the key-light pass runs
    inside the blackout branch, so a floor adopted from a rig file is light the
    owner never asked for and has no control to take away.
    """
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Floor Default Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="DJ Key",
             universe=0, dmx_address=11, zone="dj_booth"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Bar Wash",
             universe=0, dmx_address=21, zone="bar"),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)

    for fixture in manager.fixtures.values():
        override = engine.key_lighting.get_key_light_override(fixture.id, 0.0, 0.0, 0.0, 0.0)
        assert override is None, (
            f"{fixture.name} declares zone {_zone_value(fixture.zone)!r} and is "
            f"held at {override['dimmer']} with no operator action; a zoned rig "
            f"can no longer reach a blackout"
        )

    for fixture in manager.fixtures.values():
        fixture.dimmer = 0.0
        fixture.red = fixture.green = fixture.blue = 0.0
    assert max(manager.get_dmx_frame(0)) == 0, (
        "a rig that names zones must still be able to reach a real blackout"
    )


async def test_the_operator_can_raise_a_zone_and_it_reaches_the_rigs_fixtures(db):
    """What adoption buys: POST /api/effects/pro/key-lighting could only ever
    reach the five hardcoded demo presets, because nothing bound a DB rig's
    fixtures to a zone at all."""
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Operator Raise Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Back Wash",
             universe=0, dmx_address=11),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)

    zoned = _by_name(manager, "Singer Key").id
    unzoned = _by_name(manager, "Back Wash").id

    # Exactly what the endpoint does with min_intensity.
    config = engine.key_lighting._configs[PerformerZone.STAGE_CENTER]
    config.min_intensity = 0.45

    override = engine.key_lighting.get_key_light_override(zoned, 0.0, 0.0, 0.0, 0.0)
    assert override is not None and override["dimmer"] == pytest.approx(0.45)
    assert engine.key_lighting.get_key_light_override(unzoned, 0.0, 0.0, 0.0, 0.0) is None


async def test_a_zone_configured_before_the_rig_loads_still_reaches_it(db):
    """app/main.py configures DJ_BOOTH during lifespan and only boots the rig
    afterwards, so dj_booth is the one zone whose config already exists when
    adoption runs. It has to behave like every other zone."""
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Boot Order Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="DJ Key",
             universe=0, dmx_address=1, zone="dj_booth"),
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=11, zone="stage_center"),
    ])

    engine = EffectsEngine(EffectsConfig())
    # main.py's exact call, before _boot_rig.
    engine.key_lighting.configure_zone(
        PerformerZone.DJ_BOOTH,
        KeyLightConfig(zone=PerformerZone.DJ_BOOTH, min_intensity=0.0,
                       color_temp="genre", active=True),
    )

    manager = await build_manager_for_rig_id(db, rig.id)
    engine.set_fixture_manager(manager)

    dj = _by_name(manager, "DJ Key").id
    singer = _by_name(manager, "Singer Key").id

    assert dj in engine.key_lighting.get_zone_fixtures(PerformerZone.DJ_BOOTH), (
        "dj_booth is configured before the rig boots, so a fixture that declares "
        "it is never bound - the first zone a bar with a DJ would pick does "
        "nothing"
    )
    assert singer in engine.key_lighting.get_zone_fixtures(PerformerZone.STAGE_CENTER)

    for zone, fixture_id in (
        (PerformerZone.DJ_BOOTH, dj),
        (PerformerZone.STAGE_CENTER, singer),
    ):
        engine.key_lighting._configs[zone].min_intensity = 0.5
        override = engine.key_lighting.get_key_light_override(fixture_id, 0.0, 0.0, 0.0, 0.0)
        assert override is not None and override["dimmer"] == pytest.approx(0.5), (
            f"raising {zone.value} does not reach the fixture that declares it"
        )


async def test_clearing_a_zone_releases_the_fixture(db):
    """"My light is stuck on and I cannot turn it off". Dropping only the ids
    that left the rig keeps a fixture bound to a zone it no longer declares."""
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Clearable Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Singer Key",
             universe=0, dmx_address=1, zone="stage_center"),
    ])

    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(await build_manager_for_rig_id(db, rig.id))
    engine.key_lighting._configs[PerformerZone.STAGE_CENTER].min_intensity = 0.4

    # The owner clears the zone on the floor plan and the rig is reinstalled.
    result = await db.execute(select(RigFixture).where(RigFixture.rig_id == rig.id))
    row = result.scalars().one()
    row.zone = None
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)
    engine.set_fixture_manager(manager)
    fixture_id = _by_name(manager, "Singer Key").id

    assert engine.key_lighting.get_key_light_override(fixture_id, 0.0, 0.0, 0.0, 0.0) is None, (
        "the fixture is still floored by a zone it no longer declares"
    )
    assert fixture_id not in engine.key_lighting.get_zone_fixtures(PerformerZone.STAGE_CENTER)


async def test_changing_a_zone_does_not_leave_the_fixture_in_both(db):
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Rezoned Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Movable",
             universe=0, dmx_address=1, zone="stage_center"),
    ])

    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(await build_manager_for_rig_id(db, rig.id))

    result = await db.execute(select(RigFixture).where(RigFixture.rig_id == rig.id))
    row = result.scalars().one()
    row.zone = "bar"
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)
    engine.set_fixture_manager(manager)
    fixture_id = _by_name(manager, "Movable").id

    assert fixture_id in engine.key_lighting.get_zone_fixtures(PerformerZone.BAR)
    assert fixture_id not in engine.key_lighting.get_zone_fixtures(PerformerZone.STAGE_CENTER), (
        "the fixture is reported under both its old and its new zone, so the "
        "key-lighting status endpoint describes a binding that does not exist"
    )


async def test_an_operators_own_assignment_is_not_retracted_by_a_zoneless_rig(db):
    """The other half of the same rule: adoption may only take back what
    adoption gave, never an assignment the operator made by hand."""
    profile = await _profile(db)
    mode = profile.modes[0]

    rig = await _rig(db, "Hand Assigned Rig", [
        dict(fixture_id=profile.id, mode_id=mode.id, name="Par 1",
             universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)
    fixture_id = _by_name(manager, "Par 1").id

    engine.key_lighting.configure_zone(
        PerformerZone.STAGE_CENTER,
        KeyLightConfig(zone=PerformerZone.STAGE_CENTER, min_intensity=0.7, active=True),
    )
    engine.key_lighting.assign_fixtures(PerformerZone.STAGE_CENTER, [fixture_id])

    engine.set_fixture_manager(await build_manager_for_rig_id(db, rig.id))

    override = engine.key_lighting.get_key_light_override(fixture_id, 0.0, 0.0, 0.0, 0.0)
    assert override is not None and override["dimmer"] == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# The other save paths an owner can reach
# ---------------------------------------------------------------------------

async def test_the_batch_update_endpoint_can_clear_a_zone(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    """Skipping None values means a whitelist alone could set a zone and never
    take one off."""
    rig_id, rig_fixture_ids = await _patched_rig(
        client, sample_rig_data, sample_fixture_data, count=1
    )
    target = rig_fixture_ids[0]

    set_it = await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={
        "fixtures": [{"id": target, "zone": "bar"}]
    })
    assert set_it.status_code == 200, set_it.text

    cleared = await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={
        "fixtures": [{"id": target, "zone": ""}]
    })
    assert cleared.status_code == 200, cleared.text

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    row = {r["id"]: r for r in listed.json()}[target]
    assert row.get("zone") is None, (
        f"the zone reads back as {row.get('zone')!r}; a zone that cannot be "
        "cleared is a light the owner cannot take off the singer"
    )


async def test_the_batch_update_endpoint_refuses_a_zone_the_engine_cannot_use(
    client: AsyncClient, sample_rig_data, sample_fixture_data
):
    rig_id, rig_fixture_ids = await _patched_rig(
        client, sample_rig_data, sample_fixture_data, count=1
    )

    response = await client.put(f"/api/rigs/{rig_id}/fixtures/batch-update", json={
        "fixtures": [{"id": rig_fixture_ids[0], "zone": "behind the bar"}]
    })
    assert response.status_code == 400, (
        "an unrecognised zone is stored, redisplayed and then silently ignored "
        f"at showtime; got {response.status_code}"
    )


async def test_the_wizard_create_rig_endpoint_persists_a_zone(
    client: AsyncClient, sample_fixture_data
):
    """The wizard is the primary way a new owner builds a rig, so it is the last
    place a zone may be dropped on the way to the database."""
    fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert fixture_response.status_code in (200, 201), fixture_response.text
    fixture_id = fixture_response.json()["id"]

    created = await client.post("/api/wizard/create-rig", json={
        "rig_name": "Wizard Zone Rig",
        "stage_width": 8.0,
        "stage_depth": 6.0,
        "stage_height": 4.0,
        "placements": [
            {
                "fixture_id": fixture_id,
                "name": "Singer Key",
                "universe": 0,
                "dmx_address": 1,
                "position_x": 0.0,
                "position_y": 3.5,
                "position_z": 2.1,
                "rotation_y": 180.0,
                "group_name": "Front Wash",
                "zone": "stage_center",
            },
            {
                "fixture_id": fixture_id,
                "name": "Back Wash",
                "universe": 0,
                "dmx_address": 21,
                "position_x": 0.0,
                "position_y": 3.0,
                "position_z": -2.1,
                "rotation_y": 0.0,
                "group_name": "Back Wash",
            },
        ],
    })
    assert created.status_code in (200, 201), created.text
    rig_id = created.json()["id"]

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    rows = {row["name"]: row for row in listed.json()}

    assert rows["Singer Key"].get("zone") == "stage_center", (
        "POST /api/wizard/create-rig never reads 'zone' off a placement, so a rig "
        "built in the wizard can never say which light is on the singer"
    )
    assert rows["Back Wash"].get("zone") is None
    assert rows["Singer Key"]["rotation_y"] == pytest.approx(180.0)


async def test_the_wizard_create_rig_endpoint_refuses_an_unknown_zone(
    client: AsyncClient, sample_fixture_data
):
    fixture_response = await client.post("/api/fixtures/", json=sample_fixture_data)
    fixture_id = fixture_response.json()["id"]

    created = await client.post("/api/wizard/create-rig", json={
        "rig_name": "Bad Zone Rig",
        "placements": [{
            "fixture_id": fixture_id, "dmx_address": 1, "zone": "the smoking area",
        }],
    })
    assert created.status_code == 400, created.text
