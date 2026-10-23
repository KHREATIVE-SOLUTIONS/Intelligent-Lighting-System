"""
Fixture Library Endpoints
==========================

API endpoints for searching, browsing, and importing fixtures from
the Open Fixture Library (OFL) and local bundled fixtures.
"""

import asyncio
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.fixture import Fixture, FixtureMode, FixtureChannel, FixtureType, ChannelType
from app.schemas.fixture import FixtureResponse, FixtureCreate
from app.services.fixture_library.ofl_client import (
    OFLClient,
    OFLUnavailableError,
)
from app.services.fixture_library.ofl_snapshot import get_snapshot, summarise
from app.services.fixture_library.importer import (
    FixtureNotInLibrary,
    converted_definition,
    import_ofl_fixture,
)
from app.services.rig.fixture_choice import mode_features, recommend_mode

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
    """Search the Open Fixture Library for fixtures.

    The offline snapshot answers first so a venue with no internet can still
    find its fixtures; the online library is only asked when the snapshot has
    nothing, which catches a fixture added upstream since the snapshot was cut.
    """
    snapshot = get_snapshot()
    results = await asyncio.to_thread(snapshot.search, query, None, manufacturer, 50)
    if results:
        return {"results": results, "source": "ofl-offline"}

    client = get_ofl_client()
    try:
        results = await client.search_fixtures(query, manufacturer)
    except OFLUnavailableError as e:
        if snapshot.available:
            # The offline library was searched and had nothing: that is the answer.
            return {"results": [], "source": "ofl-offline", "online_error": str(e)}
        # 503 rather than an empty list: a venue offline at load-in must be told the
        # library is unreachable, not that their fixture does not exist.
        raise HTTPException(status_code=503, detail=str(e))
    return {"results": results, "source": "ofl"}


async def _import_or_raise(db: AsyncSession, manufacturer_key: str, fixture_key: str):
    try:
        return await import_ofl_fixture(db, manufacturer_key, fixture_key, client=get_ofl_client())
    except OFLUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except FixtureNotInLibrary as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import")
async def import_fixture(
    manufacturer_key: str = Query(...),
    fixture_key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a single fixture from OFL into the local library."""
    fixture, created = await _import_or_raise(db, manufacturer_key, fixture_key)
    if not created:
        return {"message": "Fixture already imported", "fixture_id": fixture.id}
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
    unavailable = None

    for item in fixtures:
        mfr_key = item.get("manufacturer_key", "")
        fix_key = item.get("fixture_key", "")
        source_id = f"{mfr_key}/{fix_key}"

        try:
            fixture, created = await import_ofl_fixture(db, mfr_key, fix_key, client=client)
            await db.commit()
            (imported if created else skipped).append(source_id)
        except OFLUnavailableError as e:
            # One unreachable library is not N separate fixture failures. Stop
            # rather than reporting the rest of the batch as missing fixtures,
            # and keep what already committed.
            await db.rollback()
            unavailable = str(e)
            break
        except FixtureNotInLibrary:
            await db.rollback()
            errors.append({"source_id": source_id, "error": "Not found"})
        except Exception as e:
            await db.rollback()
            errors.append({"source_id": source_id, "error": str(e)})

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_imported": len(imported),
        "unavailable": unavailable,
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
    try:
        manufacturers = await client.list_manufacturers()
    except OFLUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
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


# ---------------------------------------------------------------------------
# Catalog: what the rig editor's fixture picker searches
# ---------------------------------------------------------------------------


def _library_summary(fixture: Fixture) -> dict:
    """A local library fixture in the same shape as an offline OFL hit."""
    modes = sorted(fixture.modes or [], key=lambda m: m.id or 0)
    recommended = recommend_mode(modes)
    mfr_key, _, fix_key = (fixture.source_id or "").partition("/") if fixture.source == "ofl" else ("", "", "")
    return {
        "key": fixture.source_id if fixture.source == "ofl" else f"library/{fixture.id}",
        "manufacturer_key": mfr_key or None,
        "fixture_key": fix_key or None,
        "manufacturer": fixture.manufacturer,
        "name": fixture.model,
        "fixture_type": fixture.fixture_type.value if fixture.fixture_type else "other",
        "categories": fixture.categories or [],
        "modes": [
            {
                "id": m.id,
                "name": m.name,
                "channel_count": m.channel_count,
                "features": mode_features(m),
                "recommended": m is recommended,
            }
            for m in modes
        ],
        "recommended_mode": recommended.name if recommended else None,
        "source": fixture.source or "manual",
        "fixture_id": fixture.id,
        "in_library": True,
    }


def _matches_words(words: List[str], *fields: str) -> bool:
    text = " ".join(f or "" for f in fields).lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    compact = "".join(re.findall(r"[a-z0-9]+", text))
    return all(any(t.startswith(w) for t in tokens) or w in compact for w in words)


@router.get("/catalog")
async def search_catalog(
    q: str = Query(default="", max_length=100),
    fixture_type: Optional[str] = None,
    manufacturer: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Every fixture the operator can patch: the local library, then the offline OFL.

    Works with no internet. Each hit lists its modes, what each can do, and the
    mode we would patch, so the picker can patch in one step.
    """
    words = re.findall(r"[a-z0-9]+", q.lower())

    result = await db.execute(
        select(Fixture).options(selectinload(Fixture.modes).selectinload(FixtureMode.channels))
    )
    local = []
    in_library = {}
    for fixture in result.scalars().all():
        if fixture.source == "ofl" and fixture.source_id:
            in_library[fixture.source_id] = fixture.id
        if fixture_type and (fixture.fixture_type.value if fixture.fixture_type else "other") != fixture_type:
            continue
        if manufacturer and not _matches_words([manufacturer.lower()], fixture.manufacturer, fixture.source_id or ""):
            continue
        if words and not _matches_words(words, fixture.manufacturer, fixture.model, fixture.source_id or ""):
            continue
        local.append(fixture)
    local.sort(key=lambda f: (-(f.popularity_score or 0), f.manufacturer.lower(), f.model.lower()))

    results = [_library_summary(f) for f in local[:limit]]
    seen = {r["key"] for r in results}

    snapshot = get_snapshot()
    offline = await asyncio.to_thread(snapshot.search, q, fixture_type, manufacturer, limit)
    for hit in offline:
        if len(results) >= limit:
            break
        if hit["key"] in seen:
            continue
        results.append({**hit, "fixture_id": in_library.get(hit["key"]), "in_library": hit["key"] in in_library})

    return {"results": results, "offline_library": snapshot.info()}


@router.get("/catalog/{manufacturer_key}/{fixture_key}")
async def preview_catalog_fixture(manufacturer_key: str, fixture_key: str):
    """A fixture's modes channel by channel, before anything is imported."""
    try:
        converted = await converted_definition(
            manufacturer_key, fixture_key, client=get_ofl_client()
        )
    except OFLUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except FixtureNotInLibrary as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    summary = summarise(converted, converted["source_id"])
    channels_by_mode = {m["name"]: m["channels"] for m in converted.get("modes") or []}
    for mode in summary["modes"]:
        mode["channels"] = [
            {
                "channel_number": ch["channel_number"],
                "name": ch["name"],
                "channel_type": ch["channel_type"],
                "is_fine": ch.get("is_fine", False),
            }
            for ch in channels_by_mode.get(mode["name"], [])
        ]
    summary.update({
        "weight": converted.get("weight"),
        "power": converted.get("power"),
        "beam_angle": converted.get("beam_angle"),
        "pan_range": converted.get("pan_range"),
        "tilt_range": converted.get("tilt_range"),
    })
    return summary


@router.get("/status")
async def library_status():
    """Whether the offline library is installed, how big it is and how old."""
    snapshot = get_snapshot()
    return {"offline_library": await asyncio.to_thread(snapshot.info)}
