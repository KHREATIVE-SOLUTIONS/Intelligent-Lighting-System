"""
Rig to DMX Integration Tests
============================

The Phase 1 spine end to end: a rig patched in the database, through the real
bundled fixture profiles, into the engine's FixtureGroupManager, out as DMX
bytes at the addresses the profile says.

Uses its own temporary SQLite file so the seeded fixture library and the rigs
built here cannot collide with the shared test database.
"""

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
    ChannelType,
    Fixture as FixtureProfile,
    FixtureChannel,
    FixtureMode,
    FixtureType,
)
from app.models.rig import Rig, RigFixture
from app.services.rig.rig_loader import build_manager_for_rig_id, get_rig_diagnostics


MOVER_SOURCE = "martin_rush_mh6_wash"
MOVER_MODE = "12-Channel"
MOVER_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'speed': 4, 'dimmer': 5, 'shutter': 6,
    'red': 7, 'green': 8, 'blue': 9, 'white': 10, 'zoom': 11,
}
MOVER_PAN_RANGE = 540.0
MOVER_TILT_RANGE = 230.0

DUP_SOURCE = "chauvet_rogue_r2_wash"
DUP_MODE = "15-Channel"

PAR_SOURCE = "adj_dotz_par"
PAR_MODE = "3-Channel"

# A genuine mover (fixture_type "beam") and a genuine bar, so the engine
# vocabulary is exercised on more than the wash branch. MOVER_SOURCE above is a
# moving *wash*, which correctly maps to "wash" and never reaches "mover".
BEAM_SOURCE = "robe_robin_pointe"
BEAM_MODE = "24-Channel"
BAR_SOURCE = "adj_ultra_hex_bar_12"
BAR_MODE = "12-Channel"

# Pan and tilt on channels 1 and 2 with no fine channels, and dimmer on channel 10.
COARSE_SOURCE = "chauvet_intimidator_spot_375z"
COARSE_MODE = "11-Channel"

# Carries four channels typed "other" (4, 5, 6, 14) among drivable ones.
OTHER_SOURCE = "chauvet_maverick_mk2_spot"
OTHER_MODE = "18-Channel"

# The demo rig's mover map puts dimmer on offset 5; every profile used here puts
# it somewhere else, so a demo-driven frame is distinguishable from a rig-driven one.
DEMO_MOVER_DIMMER_OFFSET = 5

# pan -154 of 540 and tilt 77 of 270: the 8-bit scale gives 55 and 200 while the
# high byte of the 16-bit scale gives 54 and 201, so a coarse-only profile that is
# driven as if it had fine channels produces different bytes.
COARSE_PAN_ANGLE = -154.0
COARSE_TILT_ANGLE = 77.0
COARSE_PAN_8 = 55
COARSE_TILT_8 = 200

# pan 100 over 540 -> 44904 = 0xAF68.
PAN_ANGLE = 100.0
PAN_COARSE, PAN_FINE = 175, 104
# tilt -40 over the profile's 230 -> 21370 = 0x537A. Over the demo rig's
# hardcoded 270 the same angle would be (90, 19), so these bytes are what
# distinguishes profile-driven output from demo-driven output.
TILT_ANGLE = -40.0
TILT_COARSE, TILT_FINE = 83, 122


@pytest.fixture(scope="module")
def seeded_db_path():
    """A throwaway SQLite file holding the real bundled fixture library."""
    tmpdir = tempfile.mkdtemp(prefix="ils-rig-to-dmx-")
    path = Path(tmpdir) / "rig_to_dmx.db"

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


async def _mode(db: AsyncSession, profile: FixtureProfile, name: str) -> FixtureMode:
    for mode in profile.modes:
        if mode.name == name:
            return mode
    raise AssertionError(f"mode {name} missing from profile {profile.id}")


async def _mode_with_channels(db: AsyncSession, mode_id: int) -> FixtureMode:
    result = await db.execute(
        select(FixtureMode)
        .options(selectinload(FixtureMode.channels))
        .where(FixtureMode.id == mode_id)
    )
    return result.scalar_one()


def _profile_offsets(mode: FixtureMode):
    """Canonical channel-type name -> 0-based offset, read from the profile rows."""
    offsets = {}
    for channel in sorted(mode.channels, key=lambda c: c.channel_number):
        offsets.setdefault(channel.channel_type.value, channel.channel_number - 1)
    return offsets


def _by_name(manager, name: str):
    matches = [f for f in manager.fixtures.values() if f.name == name]
    assert len(matches) == 1, f"expected one fixture named {name}, got {len(matches)}"
    return matches[0]


async def _make_rig(db: AsyncSession, name: str, patches) -> Rig:
    """Create a rig. `patches` is a list of (source_id, mode_name, kwargs)."""
    rig = Rig(name=name, universes=[{"universe": 0, "protocol": "artnet"}])
    db.add(rig)
    await db.flush()

    for source_id, mode_name, kwargs in patches:
        profile = await _profile(db, source_id)
        mode = await _mode(db, profile, mode_name) if mode_name else None
        db.add(RigFixture(
            rig_id=rig.id,
            fixture_id=profile.id,
            mode_id=mode.id if mode else None,
            **kwargs,
        ))

    await db.commit()
    return rig


async def test_channel_map_matches_the_profile_mode_exactly(db):
    rig = await _make_rig(db, "Map Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert len(manager.fixtures) == 1
    fixture = next(iter(manager.fixtures.values()))

    assert fixture.channels == MOVER_CHANNELS
    assert fixture.dmx_address == 101
    assert fixture.universe == 0
    assert fixture.pan_range == MOVER_PAN_RANGE
    assert fixture.tilt_range == MOVER_TILT_RANGE
    assert fixture.fixture_type == "wash"


async def test_pan_tilt_land_at_profile_addresses_not_demo_addresses(db):
    rig = await _make_rig(db, "Address Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE
    fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    assert frame[100] == PAN_COARSE
    assert frame[101] == PAN_FINE
    assert frame[102] == TILT_COARSE
    assert frame[103] == TILT_FINE
    assert frame[105] == 255

    # The demo rig patches its first mover at address 1 and its second at 17.
    assert frame[0] == 0
    assert frame[16] == 0


async def test_changing_the_patch_address_moves_the_output_bytes(db):
    rig = await _make_rig(db, "Repatch Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE
    before = manager.get_dmx_frame(0)

    patch = (await db.execute(
        select(RigFixture).where(RigFixture.rig_id == rig.id)
    )).scalar_one()
    patch.dmx_address = 201
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE
    after = manager.get_dmx_frame(0)

    assert fixture.dmx_address == 201
    assert before[100:112] == after[200:212]
    assert sum(before[200:212]) == 0
    assert sum(after[100:112]) == 0


async def test_fixtures_render_into_their_patched_universe(db):
    rig = await _make_rig(db, "Two Universe Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 1}),
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 2", "universe": 1, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert manager.get_universes() == [0, 1]

    by_universe = {f.universe: f for f in manager.fixtures.values()}
    by_universe[0].dimmer = 1.0
    by_universe[1].dimmer = 0.5

    frames = manager.get_dmx_frames()

    assert sorted(frames.keys()) == [0, 1]
    assert len(frames[0]) == 512
    assert len(frames[1]) == 512

    assert frames[0][5] == 255
    assert frames[1][105] == 127

    # Each fixture occupies 12 channels; neither may appear in the other's frame.
    assert frames[0][100:112] == [0] * 12
    assert frames[1][0:12] == [0] * 12
    assert frames[0] == manager.get_dmx_frame(0)
    assert frames[1] == manager.get_dmx_frame(1)


async def test_led_par_without_a_dimmer_channel_is_scaled_by_the_virtual_dimmer(db):
    rig = await _make_rig(db, "Par Rig", [
        (PAR_SOURCE, PAR_MODE, {"name": "Par 1", "universe": 0, "dmx_address": 51}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))

    assert fixture.channels == {'red': 0, 'green': 1, 'blue': 2}
    assert fixture.pan_range == 0.0
    assert fixture.tilt_range == 0.0

    fixture.red = 1.0
    fixture.green = 1.0
    fixture.blue = 1.0
    fixture.dimmer = 0.5

    frame = manager.get_dmx_frame(0)

    assert frame[50] in (127, 128)
    assert frame[51] in (127, 128)
    assert frame[52] in (127, 128)

    fixture.dimmer = 0.0
    blackout = manager.get_dmx_frame(0)

    assert blackout[50] == 0
    assert blackout[51] == 0
    assert blackout[52] == 0


async def test_repeated_channel_types_do_not_overwrite_each_other(db):
    rig = await _make_rig(db, "Duplicate Rig", [
        (DUP_SOURCE, DUP_MODE, {"name": "Wash 1", "universe": 0, "dmx_address": 1}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = next(iter(manager.fixtures.values()))

    # Channels 6 and 7 are both typed "dimmer" (coarse and fine); the coarse one
    # owns the canonical name or the fixture is driven from its fine byte only.
    assert fixture.channels['dimmer'] == 5
    assert fixture.channels['macro'] == 13

    fixture.dimmer = 1.0
    frame = manager.get_dmx_frame(0)

    assert frame[5] == 255


async def test_type_groups_use_the_engine_vocabulary(db):
    rig = await _make_rig(db, "Group Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 1}),
        (PAR_SOURCE, PAR_MODE, {"name": "Par 1", "universe": 0, "dmx_address": 51}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert len(manager.get_fixtures_in_group("washes")) == 2
    assert len(manager.get_fixtures_in_group("all")) == 2
    assert len(manager.get_fixtures_in_group("movers_washes")) == 2

    for name in ("movers", "washes", "bars", "movers_washes"):
        assert manager.get_group(name) is not None


async def test_beams_and_bars_land_in_their_own_engine_groups(db):
    rig = await _make_rig(db, "Mixed Rig", [
        (BEAM_SOURCE, BEAM_MODE, {"name": "Beam 1", "universe": 0, "dmx_address": 1}),
        (BAR_SOURCE, BAR_MODE, {"name": "Bar 1", "universe": 0, "dmx_address": 101}),
        (PAR_SOURCE, PAR_MODE, {"name": "Par 1", "universe": 0, "dmx_address": 201}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    # The engine vocabulary is "mover"/"wash"/"bar", not the profile enum names.
    assert _by_name(manager, "Beam 1").fixture_type == "mover"
    assert _by_name(manager, "Bar 1").fixture_type == "bar"
    assert _by_name(manager, "Par 1").fixture_type == "wash"

    assert [f.name for f in manager.get_fixtures_in_group("movers")] == ["Beam 1"]
    assert [f.name for f in manager.get_fixtures_in_group("bars")] == ["Bar 1"]
    assert [f.name for f in manager.get_fixtures_in_group("washes")] == ["Par 1"]
    assert len(manager.get_fixtures_in_group("movers_washes")) == 2

    assert manager.get_group("moving_heads") is None
    assert manager.get_group("led_bars") is None


async def test_empty_rig_degrades_to_an_empty_manager(db):
    rig = await _make_rig(db, "Empty Rig", [])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert manager.fixtures == {}
    assert manager.get_universes() == []
    assert manager.get_dmx_frames() == {}
    assert manager.get_dmx_frame(0) == [0] * 512


async def test_missing_rig_degrades_without_raising(db):
    manager = await build_manager_for_rig_id(db, 999999)

    assert manager.fixtures == {}
    assert manager.get_dmx_frame(0) == [0] * 512

    diagnostics = get_rig_diagnostics(manager)
    assert diagnostics is not None
    assert diagnostics.errors


async def test_profile_without_a_mode_degrades_without_raising(db):
    bare = FixtureProfile(
        manufacturer="Nameless",
        model="Profileless Par",
        source_id="test-profileless-par",
    )
    db.add(bare)
    await db.flush()

    rig = Rig(name="Profileless Rig", universes=[])
    db.add(rig)
    await db.flush()
    db.add(RigFixture(
        rig_id=rig.id,
        fixture_id=bare.id,
        name="Unknown 1",
        universe=0,
        dmx_address=201,
    ))
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)

    assert len(manager.fixtures) == 1
    fixture = next(iter(manager.fixtures.values()))
    assert fixture.channels

    fixture.dimmer = 1.0
    frame = manager.get_dmx_frame(0)

    assert len(frame) == 512
    assert max(frame) == 255

    diagnostics = get_rig_diagnostics(manager)
    assert diagnostics is not None
    assert diagnostics.generic_maps


async def test_every_channel_map_matches_its_profile_rows(db):
    rig = await _make_rig(db, "Whole Rig", [
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 1", "universe": 0, "dmx_address": 1}),
        (COARSE_SOURCE, COARSE_MODE, {"name": "Spot 1", "universe": 0, "dmx_address": 101}),
        (OTHER_SOURCE, OTHER_MODE, {"name": "Spot 2", "universe": 0, "dmx_address": 201}),
        (DUP_SOURCE, DUP_MODE, {"name": "Wash 1", "universe": 1, "dmx_address": 1}),
        (PAR_SOURCE, PAR_MODE, {"name": "Par 1", "universe": 1, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert len(manager.fixtures) == 5

    rows = (await db.execute(
        select(RigFixture).where(RigFixture.rig_id == rig.id)
    )).scalars().all()

    for patch in rows:
        mode = await _mode_with_channels(db, patch.mode_id)
        fixture = _by_name(manager, patch.name)

        for name, offset in _profile_offsets(mode).items():
            assert fixture.channels.get(name) == offset, (
                f"{patch.name}: {name} should sit at offset {offset}, "
                f"got {fixture.channels.get(name)}"
            )

        assert sorted(fixture.channels.values()) == sorted(
            channel.channel_number - 1 for channel in mode.channels
        ), f"{patch.name}: engine offsets do not cover the profile's channels"


async def test_coarse_only_profile_is_driven_at_8_bit(db):
    rig = await _make_rig(db, "Coarse Rig", [
        (COARSE_SOURCE, COARSE_MODE, {"name": "Spot 1", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = _by_name(manager, "Spot 1")

    assert not fixture.has_channel('pan_fine')
    assert not fixture.has_channel('tilt_fine')

    fixture.pan = COARSE_PAN_ANGLE
    fixture.tilt = COARSE_TILT_ANGLE

    frame = manager.get_dmx_frame(0)

    assert frame[100] == COARSE_PAN_8
    assert frame[101] == COARSE_TILT_8


async def test_dimmer_lands_at_the_profile_offset_not_the_demo_offset(db):
    rig = await _make_rig(db, "Dimmer Offset Rig", [
        (COARSE_SOURCE, COARSE_MODE, {"name": "Spot 1", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = _by_name(manager, "Spot 1")
    fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    assert fixture.channels['dimmer'] == 9
    assert frame[109] == 255
    assert frame[100 + DEMO_MOVER_DIMMER_OFFSET] == 0


async def test_channels_typed_other_are_never_driven(db):
    # Built here rather than read off a bundled profile: which of those carry
    # 'other' rows is exactly what the library corrections keep changing.
    profile = FixtureProfile(
        manufacturer="Nameless",
        model="Undeclared Spot",
        fixture_type=FixtureType.SPOT,
        source_id="test-undeclared-spot",
        pan_range=0.0,
        tilt_range=0.0,
    )
    db.add(profile)
    await db.flush()

    mode = FixtureMode(fixture_id=profile.id, name="5-Channel", channel_count=5)
    db.add(mode)
    await db.flush()

    db.add_all([
        FixtureChannel(mode_id=mode.id, channel_number=1,
                       channel_type=ChannelType.DIMMER, name="Dimmer"),
        FixtureChannel(mode_id=mode.id, channel_number=2,
                       channel_type=ChannelType.OTHER, name="Fan Control"),
        FixtureChannel(mode_id=mode.id, channel_number=3,
                       channel_type=ChannelType.OTHER, name="CTC"),
        FixtureChannel(mode_id=mode.id, channel_number=4,
                       channel_type=ChannelType.ZOOM, name="Zoom"),
        FixtureChannel(mode_id=mode.id, channel_number=5,
                       channel_type=ChannelType.OTHER, name="Hue"),
    ])

    rig = Rig(name="Other Rig", universes=[])
    db.add(rig)
    await db.flush()
    db.add(RigFixture(
        rig_id=rig.id, fixture_id=profile.id, mode_id=mode.id, name="Spot 1",
        universe=0, dmx_address=1,
    ))
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = _by_name(manager, "Spot 1")
    fixture.dimmer = 1.0
    fixture.zoom = 1.0
    fixture.gobo = 1.0
    fixture.prism = 1.0
    fixture.color_wheel = 1.0

    frame = manager.get_dmx_frame(0)

    for offset in (1, 2, 4):
        assert frame[offset] == 0, f"channel {offset + 1} is typed 'other' and was driven"

    assert frame[0] == 255
    assert frame[3] == 255


async def test_profile_channel_limits_clamp_the_output(db):
    limited = FixtureProfile(
        manufacturer="Nameless",
        model="Limited Par",
        fixture_type=FixtureType.LED_PAR,
        source_id="test-limited-par",
        pan_range=0.0,
        tilt_range=0.0,
    )
    db.add(limited)
    await db.flush()

    mode = FixtureMode(fixture_id=limited.id, name="4-Channel", channel_count=4)
    db.add(mode)
    await db.flush()

    db.add_all([
        FixtureChannel(
            mode_id=mode.id, channel_number=1, channel_type=ChannelType.DIMMER,
            name="Dimmer", min_value=0, max_value=200,
        ),
        FixtureChannel(
            mode_id=mode.id, channel_number=2, channel_type=ChannelType.RED,
            name="Red", min_value=10, max_value=255,
        ),
        FixtureChannel(
            mode_id=mode.id, channel_number=3, channel_type=ChannelType.GREEN,
            name="Green", min_value=0, max_value=255,
        ),
        FixtureChannel(
            mode_id=mode.id, channel_number=4, channel_type=ChannelType.BLUE,
            name="Blue", min_value=0, max_value=255,
        ),
    ])

    rig = Rig(name="Limited Rig", universes=[])
    db.add(rig)
    await db.flush()
    db.add(RigFixture(
        rig_id=rig.id, fixture_id=limited.id, mode_id=mode.id, name="Par 1",
        universe=0, dmx_address=101,
    ))
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)
    fixture = _by_name(manager, "Par 1")

    assert fixture.channel_limits == {'dimmer': (0, 200), 'red': (10, 255)}

    fixture.dimmer = 1.0
    fixture.red = 0.0
    fixture.green = 1.0

    frame = manager.get_dmx_frame(0)

    assert frame[100] == 200
    # The profile's floor of 10 describes where the channel's usable range starts; it
    # must not lift a zero, or this par could never go fully dark.
    assert frame[101] == 0
    assert frame[102] == 255

    fixture.red = 0.01
    assert manager.get_dmx_frame(0)[101] == 10


async def test_patch_with_a_dangling_profile_is_skipped_without_raising(db):
    rig = Rig(name="Dangling Rig", universes=[])
    db.add(rig)
    await db.flush()

    par = await _profile(db, PAR_SOURCE)
    mode = await _mode(db, par, "5-Channel")

    db.add_all([
        RigFixture(
            rig_id=rig.id, fixture_id=10_000_019, name="Ghost",
            universe=0, dmx_address=1,
        ),
        RigFixture(
            rig_id=rig.id, fixture_id=par.id, mode_id=mode.id, name="Par 1",
            universe=0, dmx_address=51,
        ),
    ])
    await db.commit()

    manager = await build_manager_for_rig_id(db, rig.id)

    assert [f.name for f in manager.fixtures.values()] == ["Par 1"]

    _by_name(manager, "Par 1").dimmer = 1.0
    frame = manager.get_dmx_frame(0)

    assert frame[53] == 255
    assert frame[0] == 0

    diagnostics = get_rig_diagnostics(manager)
    assert diagnostics is not None
    assert diagnostics.skipped


async def test_inactive_patches_are_not_driven(db):
    rig = await _make_rig(db, "Inactive Rig", [
        (MOVER_SOURCE, MOVER_MODE, {
            "name": "MH 1", "universe": 0, "dmx_address": 1, "is_active": False,
        }),
        (MOVER_SOURCE, MOVER_MODE, {"name": "MH 2", "universe": 0, "dmx_address": 101}),
    ])

    manager = await build_manager_for_rig_id(db, rig.id)

    assert len(manager.fixtures) == 1
    assert next(iter(manager.fixtures.values())).dmx_address == 101
