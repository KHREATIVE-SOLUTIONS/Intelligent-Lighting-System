"""
Fixture Library Endpoints
==========================

API endpoints for searching, browsing, and importing fixtures from
the Open Fixture Library (OFL) and local bundled fixtures.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.fixture import Fixture, FixtureMode, FixtureChannel, FixtureType, ChannelType
from app.schemas.fixture import FixtureResponse, FixtureCreate
from app.services.fixture_library.ofl_client import OFLClient, convert_ofl_to_internal

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared OFL client instance
_ofl_client: Optional[OFLClient] = None


def get_ofl_client() -> OFLClient:
    global _ofl_client
    if _ofl_client is None:
        _ofl_client = OFLClient()
    return _ofl_client


@router.get("/search")
async def search_fixtures_online(
    query: str = Query(..., min_length=1),
    manufacturer: Optional[str] = None,
):
    """Search the Open Fixture Library for fixtures."""
    client = get_ofl_client()
    results = await client.search_fixtures(query, manufacturer)
    return {"results": results, "source": "ofl"}


@router.post("/import")
async def import_fixture(
    manufacturer_key: str = Query(...),
    fixture_key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a single fixture from OFL into the local library."""
    # Check if already imported
    source_id = f"{manufacturer_key}/{fixture_key}"
    result = await db.execute(
        select(Fixture).where(Fixture.source_id == source_id).limit(1)
    )
    existing = result.scalars().first()
    if existing:
        return {"message": "Fixture already imported", "fixture_id": existing.id}

    # Fetch from OFL
    client = get_ofl_client()
    ofl_data = await client.get_fixture(manufacturer_key, fixture_key)
    if not ofl_data:
        raise HTTPException(status_code=404, detail="Fixture not found on OFL")

    # Convert to our format
    fixture_data = convert_ofl_to_internal(ofl_data, manufacturer_key, fixture_key)

    # Create in database
    modes_data = fixture_data.pop("modes", [])
    fixture = Fixture(
        manufacturer=fixture_data["manufacturer"],
        model=fixture_data["model"],
        fixture_type=FixtureType(fixture_data.get("fixture_type", "other")),
        weight=fixture_data.get("weight"),
        power=fixture_data.get("power"),
        beam_angle=fixture_data.get("beam_angle"),
        has_rgb=fixture_data.get("has_rgb", False),
        has_color_wheel=fixture_data.get("has_color_wheel", False),
        source=fixture_data.get("source"),
        source_id=fixture_data.get("source_id"),
        categories=fixture_data.get("categories"),
    )
    db.add(fixture)
    await db.flush()

    # Create modes and channels
    for mode_data in modes_data:
        channels_data = mode_data.pop("channels", [])
        mode = FixtureMode(
            fixture_id=fixture.id,
            name=mode_data["name"],
            channel_count=mode_data["channel_count"],
        )
        db.add(mode)
        await db.flush()

        for ch_data in channels_data:
            channel = FixtureChannel(
                mode_id=mode.id,
                channel_number=ch_data["channel_number"],
                channel_type=ChannelType(ch_data.get("channel_type", "other")),
                name=ch_data.get("name", f"Channel {ch_data['channel_number']}"),
                default_value=ch_data.get("default_value", 0),
                is_fine=ch_data.get("is_fine", False),
            )
            db.add(channel)

    await db.flush()

    return {"message": "Fixture imported successfully", "fixture_id": fixture.id}


@router.post("/import-bulk")
async def import_fixtures_bulk(
    fixtures: List[dict],
    db: AsyncSession = Depends(get_db),
):
    """Bulk import multiple fixtures from OFL.

    Body: [{"manufacturer_key": "...", "fixture_key": "..."}, ...]
    """
    client = get_ofl_client()
    imported = []
    skipped = []
    errors = []

    for item in fixtures:
        mfr_key = item.get("manufacturer_key", "")
        fix_key = item.get("fixture_key", "")
        source_id = f"{mfr_key}/{fix_key}"

        result = await db.execute(
            select(Fixture).where(Fixture.source_id == source_id).limit(1)
        )
        existing = result.scalars().first()
        if existing:
            skipped.append(source_id)
            continue

        try:
            ofl_data = await client.get_fixture(mfr_key, fix_key)
            if not ofl_data:
                errors.append({"source_id": source_id, "error": "Not found"})
                continue

            fixture_data = convert_ofl_to_internal(ofl_data, mfr_key, fix_key)
            modes_data = fixture_data.pop("modes", [])

            fixture = Fixture(
                manufacturer=fixture_data["manufacturer"],
                model=fixture_data["model"],
                fixture_type=FixtureType(fixture_data.get("fixture_type", "other")),
                weight=fixture_data.get("weight"),
                power=fixture_data.get("power"),
                beam_angle=fixture_data.get("beam_angle"),
                has_rgb=fixture_data.get("has_rgb", False),
                has_color_wheel=fixture_data.get("has_color_wheel", False),
                source=fixture_data.get("source"),
                source_id=fixture_data.get("source_id"),
                categories=fixture_data.get("categories"),
            )
            db.add(fixture)
            await db.flush()

            for mode_data in modes_data:
                channels_data = mode_data.pop("channels", [])
                mode = FixtureMode(
                    fixture_id=fixture.id,
                    name=mode_data["name"],
                    channel_count=mode_data["channel_count"],
                )
                db.add(mode)
                await db.flush()

                for ch_data in channels_data:
                    channel = FixtureChannel(
                        mode_id=mode.id,
                        channel_number=ch_data["channel_number"],
                        channel_type=ChannelType(ch_data.get("channel_type", "other")),
                        name=ch_data.get("name", f"Channel {ch_data['channel_number']}"),
                        default_value=ch_data.get("default_value", 0),
                        is_fine=ch_data.get("is_fine", False),
                    )
                    db.add(channel)

            await db.commit()
            imported.append(source_id)
        except Exception as e:
            await db.rollback()
            errors.append({"source_id": source_id, "error": str(e)})

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_imported": len(imported),
    }


@router.get("/popular")
async def get_popular_fixtures(
    limit: int = Query(default=20, ge=1, le=100),
    fixture_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get popular fixtures from the local library."""
    query = select(Fixture).options(
        selectinload(Fixture.modes).selectinload(FixtureMode.channels)
    )

    if fixture_type:
        query = query.where(Fixture.fixture_type == FixtureType(fixture_type))

    query = query.order_by(Fixture.popularity_score.desc()).limit(limit)
    result = await db.execute(query)
    fixtures = result.scalars().all()
    return {"items": [_fixture_to_dict(f) for f in fixtures]}


@router.get("/manufacturers")
async def list_ofl_manufacturers():
    """List manufacturers available on OFL."""
    client = get_ofl_client()
    manufacturers = await client.list_manufacturers()
    return {"manufacturers": manufacturers}


@router.post("/sync")
async def sync_bundled_fixtures(db: AsyncSession = Depends(get_db)):
    """Sync bundled fixture definitions to database."""
    import json
    import os

    bundled_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
        "data", "fixtures", "bundled"
    )

    if not os.path.isdir(bundled_dir):
        return {"message": "No bundled fixtures directory found", "synced": 0}

    synced = 0
    for filename in os.listdir(bundled_dir):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(bundled_dir, filename)
        with open(filepath, "r") as f:
            fixture_data = json.load(f)

        source_id = fixture_data.get("source_id", filename.replace(".json", ""))
        result = await db.execute(
            select(Fixture).where(Fixture.source_id == source_id).limit(1)
        )
        existing = result.scalars().first()
        if existing:
            continue

        modes_data = fixture_data.pop("modes", [])
        fixture = Fixture(
            manufacturer=fixture_data["manufacturer"],
            model=fixture_data["model"],
            fixture_type=FixtureType(fixture_data.get("fixture_type", "other")),
            weight=fixture_data.get("weight"),
            power=fixture_data.get("power"),
            beam_angle=fixture_data.get("beam_angle"),
            pan_range=fixture_data.get("pan_range", 540.0),
            tilt_range=fixture_data.get("tilt_range", 270.0),
            has_rgb=fixture_data.get("has_rgb", False),
            has_cmy=fixture_data.get("has_cmy", False),
            has_color_wheel=fixture_data.get("has_color_wheel", False),
            color_temp_range=fixture_data.get("color_temp_range"),
            thumbnail_url=fixture_data.get("thumbnail_url"),
            source="bundled",
            source_id=source_id,
            categories=fixture_data.get("categories"),
            is_bundled=True,
            popularity_score=fixture_data.get("popularity_score", 50),
        )
        db.add(fixture)
        await db.flush()

        for mode_data in modes_data:
            channels_data = mode_data.pop("channels", [])
            mode = FixtureMode(
                fixture_id=fixture.id,
                name=mode_data["name"],
                channel_count=mode_data["channel_count"],
                description=mode_data.get("description"),
            )
            db.add(mode)
            await db.flush()

            for ch_data in channels_data:
                channel = FixtureChannel(
                    mode_id=mode.id,
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
                db.add(channel)

        await db.commit()
        synced += 1

    return {"message": f"Synced {synced} bundled fixtures", "synced": synced}


def _fixture_to_dict(fixture: Fixture) -> dict:
    """Convert fixture model to dict for response."""
    return {
        "id": fixture.id,
        "manufacturer": fixture.manufacturer,
        "model": fixture.model,
        "fixture_type": fixture.fixture_type.value if fixture.fixture_type else "other",
        "source": fixture.source,
        "source_id": fixture.source_id,
        "categories": fixture.categories,
        "popularity_score": fixture.popularity_score,
        "is_bundled": fixture.is_bundled,
        "weight": fixture.weight,
        "power": fixture.power,
        "beam_angle": fixture.beam_angle,
        "has_rgb": fixture.has_rgb,
        "has_color_wheel": fixture.has_color_wheel,
        "thumbnail_url": fixture.thumbnail_url,
        "modes": [
            {
                "id": m.id,
                "name": m.name,
                "channel_count": m.channel_count,
                "channels": [
                    {
                        "id": ch.id,
                        "channel_number": ch.channel_number,
                        "channel_type": ch.channel_type.value if ch.channel_type else "other",
                        "name": ch.name,
                    }
                    for ch in (m.channels or [])
                ],
            }
            for m in (fixture.modes or [])
        ],
    }
