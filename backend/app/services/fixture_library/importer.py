"""
Library Import
==============

Turning an Open Fixture Library key into a profile row the rig can patch. The
offline snapshot answers first so load-in never waits on the internet; the
online library is asked only for a fixture the snapshot does not hold (one added
upstream since the snapshot was cut).

Importing is idempotent: a fixture already in the library, under its current
key or the key it had before an OFL rename, is returned rather than duplicated.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fixture import ChannelType, Fixture, FixtureChannel, FixtureMode, FixtureType
from app.services.fixture_library.ofl_client import OFLClient, convert_ofl_to_internal
from app.services.fixture_library.ofl_snapshot import OFLSnapshot, get_snapshot

logger = logging.getLogger(__name__)


class FixtureNotInLibrary(LookupError):
    """Neither the offline snapshot nor the online library has this key."""


def library_fixture(fixture_data: Dict[str, Any]) -> Fixture:
    """The library row for a converted definition, carrying all it parsed.

    Travel the converter could not read is left absent so the column default
    stands, rather than written as None.
    """
    fixture = Fixture(
        manufacturer=fixture_data["manufacturer"],
        model=fixture_data["model"],
        fixture_type=FixtureType(fixture_data.get("fixture_type", "other")),
        weight=fixture_data.get("weight"),
        power=fixture_data.get("power"),
        beam_angle=fixture_data.get("beam_angle"),
        has_rgb=fixture_data.get("has_rgb", False),
        has_cmy=fixture_data.get("has_cmy", False),
        has_color_wheel=fixture_data.get("has_color_wheel", False),
        source=fixture_data.get("source"),
        source_id=fixture_data.get("source_id"),
        categories=fixture_data.get("categories"),
    )
    for key in ("pan_range", "tilt_range"):
        if fixture_data.get(key) is not None:
            setattr(fixture, key, fixture_data[key])
    return fixture


def library_channel(mode_id: int, ch_data: Dict[str, Any]) -> FixtureChannel:
    return FixtureChannel(
        mode_id=mode_id,
        channel_number=ch_data["channel_number"],
        channel_type=ChannelType(ch_data.get("channel_type", "other")),
        name=ch_data.get("name", f"Channel {ch_data['channel_number']}"),
        default_value=ch_data.get("default_value", 0),
        min_value=ch_data.get("min_value", 0),
        max_value=ch_data.get("max_value", 255),
        is_fine=ch_data.get("is_fine", False),
        coarse_channel=ch_data.get("coarse_channel"),
        value_ranges=ch_data.get("value_ranges"),
    )


async def store_converted(db: AsyncSession, fixture_data: Dict[str, Any]) -> Fixture:
    """Write a converted definition, its modes and channels. Flushes, never commits."""
    fixture_data = dict(fixture_data)
    modes_data = fixture_data.pop("modes", [])
    fixture = library_fixture(fixture_data)
    db.add(fixture)
    await db.flush()

    for mode_data in modes_data:
        mode = FixtureMode(
            fixture_id=fixture.id,
            name=mode_data["name"],
            channel_count=mode_data["channel_count"],
        )
        db.add(mode)
        await db.flush()
        for ch_data in mode_data.get("channels", []):
            db.add(library_channel(mode.id, ch_data))

    await db.flush()
    return fixture


async def find_imported(db: AsyncSession, *source_ids: str) -> Optional[Fixture]:
    """A library fixture already carrying one of these OFL keys, modes loaded."""
    result = await db.execute(
        select(Fixture)
        .where(Fixture.source_id.in_([s for s in source_ids if s]))
        .options(selectinload(Fixture.modes).selectinload(FixtureMode.channels))
        .order_by(Fixture.id)
        .limit(1)
    )
    return result.scalars().first()


async def load_with_modes(db: AsyncSession, fixture_id: int) -> Optional[Fixture]:
    result = await db.execute(
        select(Fixture)
        .where(Fixture.id == fixture_id)
        .options(selectinload(Fixture.modes).selectinload(FixtureMode.channels))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def converted_definition(
    manufacturer_key: str,
    fixture_key: str,
    client: Optional[OFLClient] = None,
    snapshot: Optional[OFLSnapshot] = None,
) -> Dict[str, Any]:
    """A definition in our profile format: offline snapshot first, then online.

    Raises FixtureNotInLibrary when neither has it, OFLUnavailableError when the
    snapshot lacks it and the online library cannot be reached, and ValueError
    for a malformed key.
    """
    snapshot = snapshot or get_snapshot()
    # Conversion is CPU work; keep it off the loop the show runs on.
    converted = await asyncio.to_thread(snapshot.convert, manufacturer_key, fixture_key)
    if converted is not None:
        return converted

    if client is None:
        raise FixtureNotInLibrary(f"{manufacturer_key}/{fixture_key} is not in the fixture library")

    ofl_data = await client.get_fixture(manufacturer_key, fixture_key)
    if not ofl_data:
        raise FixtureNotInLibrary(f"{manufacturer_key}/{fixture_key} is not in the fixture library")
    name = await asyncio.to_thread(snapshot.manufacturer_name, manufacturer_key)
    return await asyncio.to_thread(
        convert_ofl_to_internal, ofl_data, manufacturer_key, fixture_key, name
    )


async def import_ofl_fixture(
    db: AsyncSession,
    manufacturer_key: str,
    fixture_key: str,
    client: Optional[OFLClient] = None,
    snapshot: Optional[OFLSnapshot] = None,
) -> Tuple[Fixture, bool]:
    """The library row for an OFL fixture, importing it if needed.

    Returns (fixture with modes and channels loaded, True if it was just imported).
    """
    snapshot = snapshot or get_snapshot()
    original = f"{manufacturer_key}/{fixture_key}"
    current = await asyncio.to_thread(snapshot.resolve_key, manufacturer_key, fixture_key)

    existing = await find_imported(db, current, original)
    if existing is not None:
        return existing, False

    mfr_key, _, fix_key = current.partition("/")
    fixture_data = await converted_definition(mfr_key, fix_key, client=client, snapshot=snapshot)
    fixture = await store_converted(db, fixture_data)
    logger.info("Imported %s (%s %s) into the fixture library", current, fixture.manufacturer, fixture.model)
    loaded = await load_with_modes(db, fixture.id)
    return loaded, True
