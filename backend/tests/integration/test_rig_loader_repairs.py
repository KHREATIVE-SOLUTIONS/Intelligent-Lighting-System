"""
Rig Loader - Contract Surface and Degradation
=============================================

The public API the rest of Phase 1 codes against, the boot path that decides
which rig a venue runs, and the two ways a bad patch can go wrong silently:
a fixture told to do something its hardware cannot do, and a whole rig lost to
one unreadable row.
"""

import inspect
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  - registers every table on Base.metadata
from app.db.database import Base
from app.db.startup import BUNDLED_FIXTURE_DIR, _insert_fixture
from app.models.fixture import (
    Fixture as FixtureProfile,
    FixtureMode,
    FixtureType,
)
from app.models.rig import Rig, RigFixture
from app.services.rig.rig_loader import (
    ENGINE_FIXTURE_TYPES,
    build_manager_for_rig_id,
    build_manager_from_rig,
    get_rig_diagnostics,
    load_active_rig,
)


PAR_SOURCE = "adj_dotz_par"
CELL_SOURCE = "robe_robin_patt_2013"
STRIKE_SOURCE = "chauvet_strike_array_4"


@pytest.fixture(scope="module")
def seeded_db_path():
    """A throwaway SQLite file holding the real bundled fixture library."""
    tmpdir = tempfile.mkdtemp(prefix="ils-loader-repairs-")
    path = Path(tmpdir) / "loader_repairs.db"

    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)

    session = sessionmaker(bind=engine)()
    try:
        for definition in sorted(BUNDLED_FIXTURE_DIR.glob("*.json")):
            with definition.open("r", encoding="utf-8") as f:
                data = json.load(f)
            _insert_fixture(session, data, data.get("source_id") or definition.stem)
        session.commit()
    finally:
        session.close()
        engine.dispose()

    yield path

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest_asyncio.fixture
async def db(seeded_db_path):
    """AsyncSession over the seeded library, rolled back after each test."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{seeded_db_path.as_posix()}",
        poolclass=NullPool,
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _profile(db: AsyncSession, source_id: str) -> FixtureProfile:
    result = await db.execute(
        select(FixtureProfile)
        .where(FixtureProfile.source_id == source_id)
        .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
    )
    profile = result.scalar_one_or_none()
    assert profile is not None, f"bundled profile {source_id} was not seeded"
    return profile


async def _mode(profile: FixtureProfile, name: str) -> FixtureMode:
    for mode in profile.modes:
        if mode.name == name:
            return mode
    raise AssertionError(f"mode {name} missing from profile {profile.id}")


async def _rig(db: AsyncSession, name: str, rows, is_active: bool = False) -> Rig:
    rig = Rig(name=name, universes=[], is_active=is_active)
    db.add(rig)
    await db.flush()
    for row in rows:
        db.add(RigFixture(rig_id=rig.id, **row))
    await db.commit()
    return rig


async def _reload(db: AsyncSession, rig_id: int) -> Rig:
    """Re-read a rig with every relationship the pure mapper walks eager-loaded."""
    result = await db.execute(
        select(Rig)
        .where(Rig.id == rig_id)
        .options(
            selectinload(Rig.fixtures)
            .selectinload(RigFixture.fixture)
            .selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels),
            selectinload(Rig.fixtures)
            .selectinload(RigFixture.mode)
            .selectinload(FixtureMode.channels),
        )
    )
    return result.scalar_one()


# --- the API other modules code against --------------------------------------

def test_build_manager_from_rig_is_the_pure_synchronous_mapper():
    assert not inspect.iscoroutinefunction(build_manager_from_rig)
    assert list(inspect.signature(build_manager_from_rig).parameters) == ["rig"]
    assert inspect.iscoroutinefunction(build_manager_for_rig_id)
    assert inspect.iscoroutinefunction(load_active_rig)


def test_fixture_type_mapping_follows_the_contract():
    assert {t.value: e for t, e in ENGINE_FIXTURE_TYPES.items()} == {
        "moving_head": "mover", "spot": "mover", "beam": "mover",
        "wash": "wash", "led_par": "wash", "dimmer": "wash",
        "led_bar": "bar",
        "strobe": "strobe",
        "laser": "effect", "effect": "effect", "other": "effect",
    }


async def test_the_pure_mapper_builds_the_same_manager_as_the_async_entry_point(db):
    par = await _profile(db, PAR_SOURCE)
    mode = await _mode(par, "3-Channel")
    rig = await _rig(db, "Pure Rig", [
        dict(fixture_id=par.id, mode_id=mode.id, name="Par 1", universe=0, dmx_address=51),
    ])

    from_id = await build_manager_for_rig_id(db, rig.id)
    pure = build_manager_from_rig(await _reload(db, rig.id))

    assert set(pure.fixtures) == set(from_id.fixtures)
    assert pure.get_dmx_frame(0) == from_id.get_dmx_frame(0)
    assert get_rig_diagnostics(pure).rig_name == "Pure Rig"


# --- a fixture must never be told to do what it cannot do ---------------------

async def test_a_mode_less_par_is_never_told_to_pan(db):
    """Console and CSV imports create profiles with no modes; the fallback map for
    anything that is not a moving head must contain no movement."""
    bare = FixtureProfile(
        manufacturer="Nameless",
        model="Imported Par",
        fixture_type=FixtureType.LED_PAR,
        source_id="test-repairs-mode-less-par",
    )
    db.add(bare)
    await db.flush()
    rig = await _rig(db, "Mode-less Rig", [
        dict(fixture_id=bare.id, name="Par 1", universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.pan = 120.0
    fixture.tilt = -30.0
    fixture.dimmer = 1.0

    assert not any(
        name in fixture.channels
        for name in ("pan", "pan_fine", "tilt", "tilt_fine")
    )
    assert fixture.pan_range == 0.0
    assert fixture.tilt_range == 0.0

    frame = manager.get_dmx_frame(0)

    assert frame[0:5] == [0, 0, 0, 0, 0]
    assert frame[5] == 255, "dimmer"
    assert frame[6] == 255, "shutter open"
    assert frame[11] == 127, "zoom mid-scale"
    assert sum(frame[12:]) == 0

    assert get_rig_diagnostics(manager).generic_maps


async def test_a_mode_less_unknown_fixture_gets_one_guessed_channel(db):
    bare = FixtureProfile(
        manufacturer="Nameless",
        model="Console Import",
        fixture_type=FixtureType.OTHER,
        source_id="test-repairs-mode-less-other",
    )
    db.add(bare)
    await db.flush()
    rig = await _rig(db, "Console Rig", [
        dict(fixture_id=bare.id, name="Unknown 1", universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.pan = 120.0
    fixture.dimmer = 1.0

    assert fixture.channels == {'dimmer': 0}
    assert fixture.fixture_type == "effect"
    assert manager.get_group("effects") is not None
    assert manager.get_dmx_frame(0)[0:4] == [255, 0, 0, 0]


async def test_travel_is_zero_when_the_mode_declares_no_pan_channel(db):
    """The pan_range column defaults to 540 for every row that never set one, so
    the channel map is the only honest source of whether a fixture moves."""
    par = await _profile(db, PAR_SOURCE)
    par.pan_range = 540.0
    par.tilt_range = 270.0
    await db.flush()

    mode = await _mode(par, "3-Channel")
    rig = await _rig(db, "Lying Profile Rig", [
        dict(fixture_id=par.id, mode_id=mode.id, name="Par 1", universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))

    assert fixture.pan_range == 0.0
    assert fixture.tilt_range == 0.0


# --- per-cell duplicates ------------------------------------------------------

async def test_per_cell_dimmers_all_light(db):
    cell = await _profile(db, CELL_SOURCE)
    mode = await _mode(cell, "8-Channel")
    rig = await _rig(db, "Cell Rig", [
        dict(fixture_id=cell.id, mode_id=mode.id, name="Patt 1", universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    # ch1 master, ch2 dimmer fine, ch3-6 "Cell 1".."Cell 4", ch7 strobe, ch8 control.
    assert frame[0] == 255
    assert frame[1] == 0
    assert frame[2:6] == [255, 255, 255, 255]

    fixture.dimmer = 0.0
    assert max(manager.get_dmx_frame(0)) == 0


async def test_a_second_dimmer_section_follows_the_master_intensity(db):
    strike = await _profile(db, STRIKE_SOURCE)
    mode = await _mode(strike, "13-Channel")
    rig = await _rig(db, "Strike Rig", [
        dict(fixture_id=strike.id, mode_id=mode.id, name="Strike 1", universe=0, dmx_address=1),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.dimmer = 1.0
    fixture.red = fixture.green = fixture.blue = 1.0

    frame = manager.get_dmx_frame(0)

    assert frame[0:4] == [255, 255, 255, 255], "warm white cells"
    assert frame[8] == 255, "RGB dimmer"
    assert frame[9:12] == [255, 255, 255]

    # The RGB section has its own dimmer, so intensity must reach it too.
    fixture.dimmer = 0.25
    frame = manager.get_dmx_frame(0)

    assert frame[0:4] == [63, 63, 63, 63]
    assert frame[8] == 63


# --- one bad row must not cost the operator the whole patch -------------------

async def test_an_untyped_universe_or_address_does_not_lose_the_rig(db):
    """SQLite does not enforce Integer affinity and the console importers write
    these columns straight from parsed files."""
    par = await _profile(db, PAR_SOURCE)
    mode = await _mode(par, "3-Channel")

    rig = Rig(name="Malformed Rig", universes=[], is_active=False)
    db.add(rig)
    await db.flush()
    db.add_all([
        RigFixture(rig_id=rig.id, fixture_id=par.id, mode_id=mode.id,
                   name="Bad Universe", universe="u1", dmx_address=1),
        RigFixture(rig_id=rig.id, fixture_id=par.id, mode_id=mode.id,
                   name="Bad Address", universe=0, dmx_address="x"),
        RigFixture(rig_id=rig.id, fixture_id=par.id, mode_id=mode.id,
                   name="Good", universe=0, dmx_address=101),
    ])
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)

    names = {f.name for f in manager.fixtures.values()}
    assert "Good" in names

    fixture = next(f for f in manager.fixtures.values() if f.name == "Good")
    fixture.red = 1.0
    fixture.dimmer = 1.0
    assert manager.get_dmx_frame(0)[100] == 255

    diagnostics = get_rig_diagnostics(manager)
    assert any(entry["name"] == "Bad Address" for entry in diagnostics.skipped)


# --- which rig boots ----------------------------------------------------------

async def test_load_active_rig_without_an_active_rig(db):
    await _rig(db, "Shelved Rig", [], is_active=False)

    manager, rig = await load_active_rig(db)

    assert manager is None
    assert rig is None


async def test_load_active_rig_breaks_a_tie_on_most_recently_updated(db):
    """Rig.is_active has no uniqueness constraint and importers stamp it on every
    rig they create, so which rig boots must not depend on row order."""
    par = await _profile(db, PAR_SOURCE)
    mode = await _mode(par, "3-Channel")

    older = await _rig(db, "Older Active", [
        dict(fixture_id=par.id, mode_id=mode.id, name="P1", universe=0, dmx_address=1),
    ], is_active=True)
    newer = await _rig(db, "Newer Active", [
        dict(fixture_id=par.id, mode_id=mode.id, name="P2", universe=0, dmx_address=51),
    ], is_active=True)

    manager, rig = await load_active_rig(db)

    assert rig is not None
    assert rig.id == newer.id, f"expected the newer rig, got {rig.name}"
    assert rig.id != older.id
    assert manager is not None
    assert [f.name for f in manager.fixtures.values()] == ["P2"]


async def test_load_active_rig_reports_an_active_rig_with_nothing_drivable(db):
    """(None, rig) tells the caller to fall back rather than run a dark show."""
    empty = await _rig(db, "Active But Empty", [], is_active=True)

    manager, rig = await load_active_rig(db)

    assert manager is None
    assert rig is not None
    assert rig.id == empty.id
