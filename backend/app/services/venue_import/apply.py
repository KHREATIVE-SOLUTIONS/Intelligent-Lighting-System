"""
Applying an import
==================

Writes a planned import as a NEW rig. It never touches an existing rig, and the
rig it creates is not the active one: `Rig.is_active` defaults to True and the
show loads the newest active rig, so leaving the default would put an unchecked
import on stage at the next restart. Activating is a separate, asked-for step.

Everything goes through the schemas the rig endpoints use (RigCreate,
RigFixtureCreate), so an imported rig is held to the same limits as one built
by hand. Flushes, never commits: the request's session decides that.

What each rig fixture carries in its tags, since the patch has no column for it:

    position_source:mvr|ma2|csv|none    where its position came from
    unplaced                            it has none; it sits at 0,0,0 until placed
    unmatched_type                      no profile matched; switched off
    address_clash                       shares channels with another; switched off
    group:<name>                        a group beyond the one in group_name
    fixture_id:<id>                     the file's own id, when it is not a number
    hang_position:<name>, layer:<name>  where the file says it hangs
"""

import math
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fixture import ChannelType, Fixture, FixtureChannel, FixtureMode, FixtureType
from app.models.rig import Rig, RigFixture
from app.schemas.rig import RigCreate, RigFixtureCreate
from app.services.fixture_library.importer import load_with_modes, store_converted

from .matching import PLACEHOLDER_SOURCE
from .model import ParsedVenue
from .preview import PlannedFixture

PLACEHOLDER_MANUFACTURER = "Unmatched import"

TAG_UNPLACED = "unplaced"
TAG_UNMATCHED = "unmatched_type"
TAG_CLASH = "address_clash"


def library_entry(fixture: Fixture) -> Dict[str, Any]:
    """A library row as the plain dict the matcher reads. Modes must be loaded."""
    fixture_type = fixture.fixture_type
    return {
        "id": fixture.id,
        "manufacturer": fixture.manufacturer,
        "model": fixture.model,
        "fixture_type": fixture_type.value if isinstance(fixture_type, FixtureType) else fixture_type,
        "gdtf_id": fixture.gdtf_id,
        "source": fixture.source,
        "modes": [
            {"id": mode.id, "name": mode.name, "channel_count": mode.channel_count}
            for mode in sorted(fixture.modes or [], key=lambda m: m.id or 0)
        ],
    }


async def load_library(db: AsyncSession) -> List[Dict[str, Any]]:
    """Every profile in the library, with its modes, as plain dicts."""
    result = await db.execute(select(Fixture).options(selectinload(Fixture.modes)).order_by(Fixture.id))
    return [library_entry(fixture) for fixture in result.scalars().all()]


def fixture_tags(plan: PlannedFixture) -> List[str]:
    fixture = plan.fixture
    tags = [f"position_source:{plan.position_source}"]
    if plan.position is None:
        tags.append(TAG_UNPLACED)
    if plan.profile_status == "unmatched":
        tags.append(TAG_UNMATCHED)
    if plan.clashes:
        tags.append(TAG_CLASH)
    tags.extend(f"group:{name}" for name in fixture.groups)
    if fixture.fixture_id and fixture.fixture_number is None:
        tags.append(f"fixture_id:{fixture.fixture_id}")
    if fixture.position_label:
        tags.append(f"hang_position:{fixture.position_label}")
    if fixture.layer and fixture.layer != fixture.group_name:
        tags.append(f"layer:{fixture.layer}")
    return tags


def stage_size(plans: List[PlannedFixture], parsed: ParsedVenue) -> Dict[str, float]:
    """Stage dimensions that hold everything the file placed, or nothing to say.

    The origin is the centre of the floor, so the width is twice the furthest
    reach. Measured from the file's own positions; a file that places nothing
    leaves the rig's defaults alone.
    """
    points = [p.position for p in plans if p.importable and p.position is not None]
    points += [(t["x"], t["y"], t["z"]) for t in parsed.positions]
    if not points:
        return {}
    return {
        "stage_width": float(max(1, math.ceil(2 * max(abs(x) for x, _, _ in points)))),
        "stage_depth": float(max(1, math.ceil(2 * max(abs(z) for _, _, z in points)))),
        "stage_height": float(max(1.0, round(max(y for _, y, _ in points), 2))),
    }


async def _store_profile(db: AsyncSession, profile: Dict[str, Any]) -> Fixture:
    """Write a profile the file carried into the library, modes and channels loaded."""
    data = {k: v for k, v in profile.items() if not k.startswith("_")}
    fixture = await store_converted(db, data)
    fixture.gdtf_id = profile.get("gdtf_id")
    fixture.gdtf_file = (profile.get("_gdtf_filename") or "")[:500] or None
    await db.flush()
    return await load_with_modes(db, fixture.id)


async def _placeholder(db: AsyncSession, type_label: str, footprint: Optional[int]) -> Tuple[Fixture, Optional[FixtureMode], bool]:
    """(profile, mode, created) standing in for a type nothing matched.

    Its channels are all typed "other", which the engine never writes: the
    profile holds the fixture's place in the universe and nothing more.
    """
    model = type_label[:255]
    result = await db.execute(
        select(Fixture)
        .where(Fixture.source == PLACEHOLDER_SOURCE, Fixture.model == model)
        .options(selectinload(Fixture.modes))
        .order_by(Fixture.id)
        .limit(1)
    )
    fixture = result.scalars().first()
    created = fixture is None
    if fixture is None:
        fixture = Fixture(
            manufacturer=PLACEHOLDER_MANUFACTURER,
            model=model,
            fixture_type=FixtureType.OTHER,
            source=PLACEHOLDER_SOURCE,
            pan_range=0.0,
            tilt_range=0.0,
        )
        db.add(fixture)
        await db.flush()
        modes: List[FixtureMode] = []
    else:
        modes = list(fixture.modes or [])

    if not footprint:
        return fixture, None, created
    for mode in modes:
        if mode.channel_count == footprint:
            return fixture, mode, created

    mode = FixtureMode(
        fixture_id=fixture.id,
        name=f"Imported footprint ({footprint} ch)",
        channel_count=footprint,
        description="Placeholder from a venue import: occupies the channels, drives none.",
    )
    db.add(mode)
    await db.flush()
    for number in range(1, footprint + 1):
        db.add(FixtureChannel(
            mode_id=mode.id,
            channel_number=number,
            channel_type=ChannelType.OTHER,
            name=f"Channel {number}",
        ))
    await db.flush()
    return fixture, mode, created


def _mode_id(fixture: Fixture, wanted: Optional[Dict[str, Any]]) -> Optional[int]:
    """The stored mode that a planned (file-side) mode became."""
    if wanted is None:
        return None
    for mode in sorted(fixture.modes or [], key=lambda m: m.id or 0):
        if mode.name == wanted.get("name") and mode.channel_count == wanted.get("channel_count"):
            return mode.id
    return None


def default_rig_name(source_file: str) -> str:
    stem = PurePath(source_file or "").stem.strip()
    return f"{stem} (imported)" if stem else "Imported venue"


async def store_profiles(db: AsyncSession, parsed: ParsedVenue, library: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add every profile the file carries that the library lacks. For a GDTF on its own."""
    created = []
    known = {entry.get("gdtf_id") for entry in library if entry.get("gdtf_id")}
    for profile in parsed.profiles:
        if profile.get("gdtf_id") and profile["gdtf_id"] in known:
            continue
        fixture = await _store_profile(db, profile)
        known.add(profile.get("gdtf_id"))
        created.append({"fixture_id": fixture.id, "manufacturer": fixture.manufacturer, "model": fixture.model})
    return created


async def apply_import(
    db: AsyncSession,
    parsed: ParsedVenue,
    plans: List[PlannedFixture],
    rig_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new, inactive rig from a plan. Returns what was written."""
    importable = [p for p in plans if p.importable]

    stored: Dict[int, Fixture] = {}       # id(embedded profile dict) -> library row
    by_gdtf_id: Dict[str, Fixture] = {}
    profiles_created: List[Dict[str, Any]] = []
    placeholders: Dict[Tuple[str, int], Tuple[Fixture, Optional[FixtureMode]]] = {}
    placeholders_created: List[str] = []

    name = (rig_name or "").strip() or default_rig_name(parsed.source_file)
    universes = sorted({p.fixture.universe for p in importable})
    rig_data = RigCreate(
        name=name[:255],
        description=f"Imported from {parsed.source_file or 'a file'} ({parsed.format}).",
        universes=[{"universe": u, "protocol": "artnet", "port": 6454} for u in universes],
        **stage_size(plans, parsed),
    )
    rig = Rig(
        **rig_data.model_dump(),
        source_format=parsed.format,
        source_file=(parsed.source_file or "")[:500] or None,
        # Explicit: the column default is True. See the module docstring.
        is_active=False,
    )
    db.add(rig)
    await db.flush()

    switched_off = 0
    for plan in importable:
        fixture = plan.fixture
        mode_id: Optional[int] = None

        if plan.profile_status == "library":
            profile_id = plan.library_entry["id"]
            mode_id = plan.mode.get("id") if plan.mode else None
        elif plan.profile_status == "embedded":
            embedded = plan.embedded_profile
            row = stored.get(id(embedded)) or by_gdtf_id.get(embedded.get("gdtf_id") or "")
            if row is None:
                row = await _store_profile(db, embedded)
                profiles_created.append({
                    "fixture_id": row.id, "manufacturer": row.manufacturer, "model": row.model,
                })
                if embedded.get("gdtf_id"):
                    by_gdtf_id[embedded["gdtf_id"]] = row
            stored[id(embedded)] = row
            profile_id = row.id
            mode_id = _mode_id(row, plan.mode)
        else:
            footprint = plan.footprint if plan.footprint_known else 0
            key = (plan.type_label, footprint)
            if key not in placeholders:
                row, mode, created = await _placeholder(db, plan.type_label, footprint)
                placeholders[key] = (row, mode)
                if created:
                    placeholders_created.append(plan.type_label)
            row, mode = placeholders[key]
            profile_id = row.id
            mode_id = mode.id if mode is not None else None

        position = plan.position or (0.0, 0.0, 0.0)
        rotation = plan.rotation or (0.0, 0.0, 0.0)
        active = not plan.switched_off
        switched_off += 0 if active else 1

        data = RigFixtureCreate(
            fixture_id=profile_id,
            name=plan.name[:255],
            fixture_number=fixture.fixture_number,
            universe=fixture.universe,
            dmx_address=fixture.dmx_address,
            mode_id=mode_id,
            position_x=position[0], position_y=position[1], position_z=position[2],
            rotation_x=rotation[0], rotation_y=rotation[1], rotation_z=rotation[2],
            group_name=(fixture.group_name or None) and fixture.group_name[:100],
            zone=plan.zone,
            tags=fixture_tags(plan),
            is_active=active,
        )
        db.add(RigFixture(rig_id=rig.id, **data.model_dump()))

    await db.flush()

    return {
        "rig_id": rig.id,
        "rig_name": rig.name,
        "is_active": False,
        "fixtures_created": len(importable),
        "fixtures_switched_off": switched_off,
        "fixtures_not_imported": len(plans) - len(importable),
        "unplaced": sum(1 for p in importable if p.position is None),
        "profiles_created": profiles_created,
        "placeholder_profiles_created": placeholders_created,
    }
