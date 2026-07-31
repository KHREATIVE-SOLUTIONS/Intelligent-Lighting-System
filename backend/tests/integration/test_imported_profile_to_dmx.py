"""
Imported Profile to DMX Integration Tests
=========================================

The Phase 2 claim, tied back to the Phase 1 spine: a GDTF archive parsed into the
library, patched into a rig at a known address, and driven out as DMX bytes at the
slots the archive's `Offset` attributes declare.

The mode below is built so that a parser which numbers channels sequentially - the
pre-Phase-2 behaviour - lands pan's coarse byte one slot late. Everything after it
moves too, so the fixture appears to work while aiming the wrong light. This test
is what catches that before a venue does.
"""

from typing import Any, Dict

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  - registers every table on Base.metadata
from app.db.database import Base
from app.db.startup import _insert_fixture
from app.models.fixture import (
    ChannelType,
    Fixture as FixtureProfile,
    FixtureMode,
)
from app.models.rig import Rig, RigFixture
from app.services.fixture_library.gdtf_parser import parse_gdtf
from app.services.rig.rig_loader import build_manager_for_rig_id
from tests.unit.test_gdtf_parser import gdtf_archive


# Slot 1 shutter, 2 dimmer, 3+4 pan, 5+6 tilt, 7-9 colour - with a virtual channel
# sitting between the shutter and the dimmer. Counting DMXChannel elements instead
# of reading Offset gives pan slot 4 rather than 3.
MOVER_MODE = [
    {"offset": "1", "attribute": "Shutter"},
    {"attribute": "NoFunction", "geometry": "Base"},
    {"offset": "2", "attribute": "Dimmer"},
    # -270..270 and -135..135 are the model defaults, so these bytes are about
    # where the channel sits, never about how travel was read.
    {"offset": "3,4", "attribute": "Pan", "physical": (-270.0, 270.0)},
    {"offset": "5,6", "attribute": "Tilt", "physical": (-135.0, 135.0)},
    {"offset": "7", "attribute": "ColorAdd_R"},
    {"offset": "8", "attribute": "ColorAdd_G"},
    {"offset": "9", "attribute": "ColorAdd_B"},
]
MOVER_SPAN = 9

COARSE_MODE = [
    {"offset": "1", "attribute": "Dimmer"},
    {"offset": "2", "attribute": "Pan", "physical": (-270.0, 270.0)},
    {"offset": "3", "attribute": "Tilt", "physical": (-135.0, 135.0)},
]

ADDRESS = 101
BASE = ADDRESS - 1

# Numbering DMXChannel elements instead of reading Offset counts the virtual
# channel, so pan's coarse byte comes out on slot 4 - 0-based offset 3.
SEQUENTIAL_PAN_OFFSET = 3

# pan 100 over 540 -> (100 + 270) / 540 * 65535 = 44904 = 0xAF68.
PAN_ANGLE = 100.0
PAN_COARSE, PAN_FINE = 175, 104
# tilt -40 over 270 -> (-40 + 135) / 270 * 65535 = 23059 = 0x5A13.
TILT_ANGLE = -40.0
TILT_COARSE, TILT_FINE = 90, 19

# The same angles at 8 bit, for the profile with no fine channels.
PAN_8, TILT_8 = 175, 90


@pytest.fixture
def db_path(tmp_path):
    """An empty database with the real schema and no seeded library."""
    path = tmp_path / "imported.db"
    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return path


@pytest_asyncio.fixture
async def db(db_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        poolclass=NullPool,
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()


def import_gdtf(db_path, modes, source_id: str, **kwargs: Any) -> Dict[str, Any]:
    """Parse a synthesised GDTF archive into the library the way an upload does."""
    data = parse_gdtf(gdtf_archive(modes, **kwargs))

    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session = sessionmaker(bind=engine)()
    try:
        _insert_fixture(session, data, source_id)
        session.commit()
    finally:
        session.close()
        engine.dispose()

    return data


async def patch_rig(db: AsyncSession, source_id: str, mode_name: str, *addresses) -> Rig:
    """Patch an imported profile's mode into a rig, once per address given."""
    profile = (await db.execute(
        select(FixtureProfile).where(FixtureProfile.source_id == source_id)
    )).scalar_one()
    mode = (await db.execute(
        select(FixtureMode)
        .where(FixtureMode.fixture_id == profile.id, FixtureMode.name == mode_name)
    )).scalar_one()

    rig = Rig(name="Imported Rig", universes=[{"universe": 0, "protocol": "artnet"}])
    db.add(rig)
    await db.flush()
    for index, address in enumerate(addresses, start=1):
        db.add(RigFixture(
            rig_id=rig.id,
            fixture_id=profile.id,
            mode_id=mode.id,
            name=f"Imported {index}",
            universe=0,
            dmx_address=address,
        ))
    await db.commit()
    return rig


async def stored_mode(db: AsyncSession, source_id: str, mode_name: str) -> FixtureMode:
    """The mode row as the import actually wrote it, with its channels loaded."""
    profile = (await db.execute(
        select(FixtureProfile).where(FixtureProfile.source_id == source_id)
    )).scalar_one()
    return (await db.execute(
        select(FixtureMode)
        .options(selectinload(FixtureMode.channels))
        .where(FixtureMode.fixture_id == profile.id, FixtureMode.name == mode_name)
    )).scalar_one()


def only_fixture(manager):
    assert len(manager.fixtures) == 1, f"expected one fixture, got {manager.fixtures}"
    return next(iter(manager.fixtures.values()))


async def test_the_import_writes_the_declared_slots_into_the_library(db_path, db):
    import_gdtf(db_path, [("Standard", MOVER_MODE)], "test-gdtf-mover")

    mode = await stored_mode(db, "test-gdtf-mover", "Standard")
    rows = {channel.channel_number: channel for channel in mode.channels}

    assert sorted(rows) == list(range(1, MOVER_SPAN + 1))
    assert mode.channel_count == MOVER_SPAN

    assert rows[3].channel_type == ChannelType.PAN
    assert rows[3].is_fine is False
    assert rows[3].coarse_channel is None

    assert rows[4].channel_type == ChannelType.PAN_FINE
    assert rows[4].is_fine is True
    assert rows[4].coarse_channel == 3

    assert rows[5].channel_type == ChannelType.TILT
    assert rows[6].channel_type == ChannelType.TILT_FINE
    assert rows[6].coarse_channel == 5

    assert ChannelType.OTHER not in {c.channel_type for c in mode.channels}, (
        "the offset-less NoFunction channel took a DMX slot it does not own"
    )


async def test_pan_coarse_lands_on_the_slot_the_gdtf_declares(db_path, db):
    import_gdtf(db_path, [("Standard", MOVER_MODE)], "test-gdtf-mover")
    rig = await patch_rig(db, "test-gdtf-mover", "Standard", ADDRESS)

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = only_fixture(manager)

    assert fixture.channels == {
        'shutter': 0, 'dimmer': 1, 'pan': 2, 'pan_fine': 3,
        'tilt': 4, 'tilt_fine': 5, 'red': 6, 'green': 7, 'blue': 8,
    }
    assert fixture.pan_range == pytest.approx(540.0)
    assert fixture.tilt_range == pytest.approx(270.0)

    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE
    fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    # shutter open, dimmer full, pan, tilt, then colour held dark.
    assert frame[BASE:BASE + MOVER_SPAN] == [
        255, 255, PAN_COARSE, PAN_FINE, TILT_COARSE, TILT_FINE, 0, 0, 0,
    ]

    # Counting DMXChannel elements puts pan's coarse byte on slot 4 - one late,
    # because the virtual channel ahead of it took a slot it does not own. That
    # slot carries pan's fine byte, so a shift is silent at the console and
    # visible only in where the light points.
    assert frame[BASE + SEQUENTIAL_PAN_OFFSET] == PAN_FINE
    assert frame[BASE + MOVER_SPAN] == 0, "the fixture must not write past its mode"


async def test_the_imported_mode_spans_the_slots_the_gdtf_declares(db_path, db):
    data = import_gdtf(db_path, [("Standard", MOVER_MODE)], "test-gdtf-mover")

    mode = data["modes"][0]
    assert mode["channel_count"] == MOVER_SPAN
    assert sorted(ch["channel_number"] for ch in mode["channels"]) == list(
        range(1, MOVER_SPAN + 1)
    )
    assert data["pan_range"] == pytest.approx(540.0)
    assert data["tilt_range"] == pytest.approx(270.0)

    rig = await patch_rig(db, "test-gdtf-mover", "Standard", ADDRESS)
    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = only_fixture(manager)

    fixture.dimmer = 1.0
    fixture.red = 1.0
    fixture.green = 1.0
    fixture.blue = 1.0
    frame = manager.get_dmx_frame(0)

    assert frame[BASE + 6:BASE + 9] == [255, 255, 255]
    assert sum(frame[BASE + MOVER_SPAN:]) == 0
    assert sum(frame[:BASE]) == 0


async def test_the_patch_address_offsets_the_declared_slots(db_path, db):
    import_gdtf(db_path, [("Standard", MOVER_MODE)], "test-gdtf-mover")
    rig = await patch_rig(db, "test-gdtf-mover", "Standard", 1)

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = only_fixture(manager)
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE

    frame = manager.get_dmx_frame(0)

    assert frame[2] == PAN_COARSE
    assert frame[3] == PAN_FINE
    assert frame[4] == TILT_COARSE
    assert frame[5] == TILT_FINE
    assert sum(frame[MOVER_SPAN:]) == 0


async def test_two_imported_fixtures_hold_their_own_declared_slots(db_path, db):
    import_gdtf(db_path, [("Standard", MOVER_MODE)], "test-gdtf-mover")
    rig = await patch_rig(db, "test-gdtf-mover", "Standard", 1, 1 + MOVER_SPAN)

    manager = await build_manager_for_rig_id(db, rig.id)
    assert len(manager.fixtures) == 2

    by_address = {f.dmx_address: f for f in manager.fixtures.values()}
    assert sorted(by_address) == [1, 1 + MOVER_SPAN]

    by_address[1].pan = PAN_ANGLE
    by_address[1].tilt = TILT_ANGLE
    by_address[1].dimmer = 1.0
    by_address[1 + MOVER_SPAN].pan = -PAN_ANGLE
    by_address[1 + MOVER_SPAN].tilt = -TILT_ANGLE
    by_address[1 + MOVER_SPAN].dimmer = 0.0

    frame = manager.get_dmx_frame(0)

    assert frame[0:MOVER_SPAN] == [
        255, 255, PAN_COARSE, PAN_FINE, TILT_COARSE, TILT_FINE, 0, 0, 0,
    ]
    # pan -100 over 540 -> 20631 = 0x5097; tilt 40 over 270 -> 42476 = 0xA5EC.
    assert frame[MOVER_SPAN:2 * MOVER_SPAN] == [
        255, 0, 0x50, 0x97, 0xA5, 0xEC, 0, 0, 0,
    ]
    assert sum(frame[2 * MOVER_SPAN:]) == 0


async def test_an_imported_coarse_only_profile_is_driven_at_8_bit(db_path, db):
    import_gdtf(db_path, [("Basic", COARSE_MODE)], "test-gdtf-coarse")
    rig = await patch_rig(db, "test-gdtf-coarse", "Basic", ADDRESS)

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = only_fixture(manager)

    assert fixture.channels == {'dimmer': 0, 'pan': 1, 'tilt': 2}
    assert not fixture.has_channel('pan_fine')
    assert not fixture.has_channel('tilt_fine')

    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE

    frame = manager.get_dmx_frame(0)

    assert frame[BASE + 1] == PAN_8
    assert frame[BASE + 2] == TILT_8
    assert sum(frame[BASE + 3:]) == 0
