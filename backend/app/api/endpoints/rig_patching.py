"""
Rig Patching Endpoints
=======================

API endpoints for DMX auto-patching, conflict detection, and
address management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.api.endpoints.rigs import _validated_zone
from app.models.fixture import Fixture as FixtureProfile, FixtureMode
from app.services.fixture_library.importer import (
    FixtureNotInLibrary,
    import_ofl_fixture,
    load_with_modes,
)
from app.services.fixture_library.ofl_client import OFLUnavailableError
from app.services.rig.fixture_choice import mode_features, recommend_mode
from app.services.rig.patching_service import (
    MAX_UNIVERSES,
    PatchingService,
    PatchPlanError,
    plan_addresses,
)
from app.services.rig.rig_loader import build_manager_for_rig_id
from app.services.rig.wizard_service import (
    MOUNTING_POSITIONS,
    WizardService,
    _DEFAULT_MOUNTING_BY_TYPE,
    _FALLBACK_MOUNTING,
)
from app.services.rig.programming_audit import build_programming_audit

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_rig_fixtures_with_channels(rig_id: int, db: AsyncSession):
    """Load rig fixtures with their mode channel counts."""
    result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(
            selectinload(RigFixture.fixture),
            selectinload(RigFixture.mode).selectinload(FixtureMode.channels),
        )
    )
    rig_fixtures = result.scalars().all()

    fixtures_data = []
    for rf in rig_fixtures:
        channel_count = 16  # Default fallback
        if rf.mode:
            channel_count = rf.mode.channel_count

        fixtures_data.append({
            "id": rf.id,
            "universe": rf.universe or 0,
            "dmx_address": rf.dmx_address,
            "channel_count": channel_count,
            "is_address_locked": rf.is_address_locked,
            "name": rf.name,
            "fixture_type": (
                rf.fixture.fixture_type.value
                if rf.fixture and getattr(rf.fixture, "fixture_type", None)
                else "other"
            ),
            "has_mode": rf.mode is not None,
            "mode_name": rf.mode.name if rf.mode else None,
            "channel_types": [
                str(ch.channel_type.value if getattr(ch, "channel_type", None) else "other")
                for ch in (rf.mode.channels if rf.mode else [])
            ],
        })

    return rig, rig_fixtures, fixtures_data


@router.post("/{rig_id}/auto-patch")
async def auto_patch_rig(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Auto-assign DMX addresses for all unlocked fixtures in a rig.

    Respects locked fixtures and universe boundaries (512ch max).
    """
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)

    locked_ids = {f["id"] for f in fixtures_data if f["is_address_locked"]}
    patched = PatchingService.auto_patch(fixtures_data, locked_ids)

    # Update database
    patched_map = {f["id"]: f for f in patched}
    updated_count = 0
    for rf in rig_fixtures:
        p = patched_map.get(rf.id)
        if p and not rf.is_address_locked:
            if rf.universe != p["universe"] or rf.dmx_address != p["dmx_address"]:
                rf.universe = p["universe"]
                rf.dmx_address = p["dmx_address"]
                updated_count += 1

    await db.flush()

    return {
        "message": f"Auto-patched {updated_count} fixtures",
        "rig_id": rig_id,
        "updated_count": updated_count,
        "fixtures": patched,
    }


@router.get("/{rig_id}/patch-conflicts")
async def get_patch_conflicts(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detect DMX address conflicts in a rig."""
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)
    conflicts = PatchingService.find_conflicts(fixtures_data)

    return {
        "rig_id": rig_id,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


@router.get("/{rig_id}/next-address")
async def get_next_available_address(
    rig_id: int,
    universe: int = Query(default=0, ge=0, le=15),
    channel_count: int = Query(default=16, ge=1, le=512),
    db: AsyncSession = Depends(get_db),
):
    """Get the next available DMX address in a universe."""
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)

    # Build occupied ranges for the specified universe
    occupied = []
    for f in fixtures_data:
        if f["universe"] == universe:
            start = f["dmx_address"]
            end = start + f["channel_count"] - 1
            occupied.append((start, end))

    address = PatchingService.get_next_address(occupied, channel_count)

    if address is None:
        return {
            "universe": universe,
            "address": None,
            "message": f"No space for {channel_count} channels in universe {universe}",
        }

    return {
        "universe": universe,
        "address": address,
        "channel_count": channel_count,
    }


@router.get("/{rig_id}/programming-audit")
async def get_programming_audit(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Run a professional programming-practices audit on a rig patch."""
    _, _, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)
    return build_programming_audit(fixtures_data)


# ---------------------------------------------------------------------------
# Patch by make and model
# ---------------------------------------------------------------------------


class LibraryPatchRequest(BaseModel):
    """Patch N fixtures of one make and model, as an operator would on a console."""

    library_key: Optional[str] = Field(
        default=None, description='OFL key from the catalog, "manufacturer/fixture"'
    )
    fixture_id: Optional[int] = Field(default=None, description="A profile already in the library")
    mode_id: Optional[int] = None
    mode_name: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=96)
    universe: int = Field(default=0, ge=0, le=MAX_UNIVERSES - 1)
    start_address: Optional[int] = Field(default=None, ge=1, le=512)
    name: Optional[str] = Field(default=None, max_length=200)
    group_name: Optional[str] = Field(default=None, max_length=100)
    mounting_position: Optional[str] = None
    zone: Optional[str] = None
    apply_live: bool = True


def _pick_mode(profile: FixtureProfile, request: LibraryPatchRequest) -> FixtureMode:
    modes = sorted(profile.modes or [], key=lambda m: m.id or 0)
    if not modes:
        raise HTTPException(
            status_code=400,
            detail=f"{profile.manufacturer} {profile.model} has no DMX modes to patch",
        )
    if request.mode_id is not None:
        for mode in modes:
            if mode.id == request.mode_id:
                return mode
        raise HTTPException(
            status_code=400,
            detail=f"mode {request.mode_id} is not a mode of {profile.manufacturer} {profile.model}",
        )
    if request.mode_name:
        wanted = request.mode_name.strip().lower()
        for mode in modes:
            if (mode.name or "").strip().lower() == wanted:
                return mode
        names = ", ".join(m.name for m in modes)
        raise HTTPException(
            status_code=400,
            detail=f"{profile.model} has no mode '{request.mode_name}'; it has: {names}",
        )
    return recommend_mode(modes)


async def _resolve_profile(db: AsyncSession, request: LibraryPatchRequest):
    """The library profile to patch and whether it was imported for this patch."""
    if (request.library_key is None) == (request.fixture_id is None):
        raise HTTPException(status_code=400, detail="send exactly one of library_key or fixture_id")

    if request.fixture_id is not None:
        profile = await load_with_modes(db, request.fixture_id)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"fixture {request.fixture_id} is not in the library")
        return profile, False

    manufacturer_key, sep, fixture_key = request.library_key.strip().partition("/")
    if not sep or not manufacturer_key or not fixture_key:
        raise HTTPException(status_code=400, detail='library_key must look like "manufacturer/fixture"')
    from app.api.endpoints.fixture_library import get_ofl_client

    try:
        return await import_ofl_fixture(db, manufacturer_key, fixture_key, client=get_ofl_client())
    except OFLUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except FixtureNotInLibrary as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _install_live(app, manager) -> None:
    """Point the running show at the rebuilt rig, as boot does."""
    engine = getattr(app.state, "effects_engine", None)
    if engine is not None:
        setter = getattr(engine, "set_fixture_manager", None)
        if callable(setter):
            setter(manager)
        else:
            engine.fixtures = manager
    app.state.fixture_manager = manager


@router.post("/{rig_id}/patch-from-library", status_code=201)
async def patch_from_library(
    rig_id: int,
    body: LibraryPatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Patch fixtures by make and model.

    Imports the profile from the fixture library if it is not there yet, picks
    the mode a programmer would (or the one asked for), finds addresses that do
    not overlap anything already patched, hangs the units evenly on a mounting
    position, groups them, and - when this is the active rig - hands the new rig
    straight to the running show.
    """
    rig, rig_fixtures, fixtures_data = await _get_rig_fixtures_with_channels(rig_id, db)
    profile, imported = await _resolve_profile(db, body)
    mode = _pick_mode(profile, body)
    footprint = int(mode.channel_count or len(mode.channels or []) or 1)

    occupied = {}
    for f in fixtures_data:
        start = int(f["dmx_address"])
        occupied.setdefault(int(f["universe"]), []).append((start, start + int(f["channel_count"]) - 1))
    try:
        addresses = plan_addresses(
            occupied, footprint, body.quantity, universe=body.universe, start_address=body.start_address
        )
    except PatchPlanError as e:
        raise HTTPException(status_code=409, detail=str(e))

    fixture_type = profile.fixture_type.value if profile.fixture_type else "other"
    mounting = body.mounting_position or _DEFAULT_MOUNTING_BY_TYPE.get(fixture_type, _FALLBACK_MOUNTING)
    if mounting not in MOUNTING_POSITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mounting position '{mounting}'; expected one of: {', '.join(MOUNTING_POSITIONS)}",
        )
    zone = _validated_zone(body.zone)

    stage_width = float(rig.stage_width or 10.0)
    stage_depth = float(rig.stage_depth or 8.0)
    stage_height = float(rig.stage_height or 6.0)
    positions = WizardService._compute_group_positions(
        mounting, body.quantity, stage_width, stage_depth, stage_height
    )
    taken_positions = {
        (round(rf.position_x or 0.0, 2), round(rf.position_y or 0.0, 2), round(rf.position_z or 0.0, 2))
        for rf in rig_fixtures
    }

    label = (body.name or profile.model).strip() or profile.model
    group_name = (body.group_name if body.group_name is not None else profile.model).strip() or None
    same_label = sum(1 for rf in rig_fixtures if (rf.name or "").startswith(f"{label} "))
    next_number = max([rf.fixture_number or 0 for rf in rig_fixtures] + [0]) + 1

    created = []
    for i, ((universe, address), pos) in enumerate(zip(addresses, positions)):
        x, y, z = WizardService._claim_position(taken_positions, pos["x"], pos["y"], pos["z"], stage_depth)
        rf = RigFixture(
            rig_id=rig.id,
            fixture_id=profile.id,
            mode_id=mode.id,
            name=f"{label} {same_label + i + 1}",
            fixture_number=next_number + i,
            universe=universe,
            dmx_address=address,
            position_x=x,
            position_y=y,
            position_z=z,
            rotation_y=WizardService._aim_rotation_y(x, z, stage_width),
            group_name=group_name,
            zone=zone,
        )
        db.add(rf)
        created.append(rf)
    await db.flush()

    applied_live = False
    notes = []
    if rig.is_active and body.apply_live:
        db.expire(rig, ["fixtures"])
        manager = await build_manager_for_rig_id(db, rig.id)
        if manager is not None and manager.fixtures:
            _install_live(request.app, manager)
            applied_live = True
        else:
            notes.append("the rig could not be rebuilt for the running show; it will load on restart")

    return {
        "rig_id": rig.id,
        "fixture": {
            "id": profile.id,
            "manufacturer": profile.manufacturer,
            "model": profile.model,
            "fixture_type": fixture_type,
            "source": profile.source,
            "source_id": profile.source_id,
            "imported": imported,
        },
        "mode": {
            "id": mode.id,
            "name": mode.name,
            "channel_count": footprint,
            "features": mode_features(mode),
            "chosen_by": "request" if (body.mode_id or body.mode_name) else "recommended",
        },
        "group_name": group_name,
        "mounting_position": mounting,
        "patched": [
            {
                "id": rf.id,
                "name": rf.name,
                "fixture_number": rf.fixture_number,
                "universe": rf.universe,
                "dmx_address": rf.dmx_address,
                "last_address": rf.dmx_address + footprint - 1,
                "position": {"x": rf.position_x, "y": rf.position_y, "z": rf.position_z},
            }
            for rf in created
        ],
        "applied_live": applied_live,
        "notes": notes,
    }
