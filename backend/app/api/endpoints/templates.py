"""
Rig Template Endpoints
=======================

API endpoints for creating, browsing, and applying rig templates.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.template import RigTemplate
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture, FixtureMode
from app.services.lighting.key_lighting import parse_zone
from app.services.rig.fixture_choice import choose_mode, mode_makes_light
from app.services.rig.patching_service import PatchingService

logger = logging.getLogger(__name__)
router = APIRouter()


def _validated_zone(value) -> Optional[str]:
    """A zone name the engine recognises, or None. A template is not user input,
    so an unknown zone is dropped and logged rather than failing the whole apply."""
    if not value:
        return None
    zone = parse_zone(value)
    if zone is None:
        logger.warning("Template declares unknown zone %r; ignoring it", value)
        return None
    return zone.value


async def _pick_profile(db: AsyncSession, fixture_type: str):
    """The library profile and mode to patch a slot of this type onto.

    Prefers a mode that can actually make light. Taking the first mode blindly
    patches an `effect` slot onto a macro+speed mode, so the fixture holds an
    address, shows on the plan and can never be turned on.
    """
    result = await db.execute(
        select(Fixture)
        .where(Fixture.fixture_type == fixture_type)
        .order_by(Fixture.id)
    )
    fixtures = result.scalars().all()
    if not fixtures:
        return None, None

    fallback = (None, None)
    for fixture in fixtures:
        mode_result = await db.execute(
            select(FixtureMode)
            .where(FixtureMode.fixture_id == fixture.id)
            .options(selectinload(FixtureMode.channels))
            .order_by(FixtureMode.id)
        )
        modes = mode_result.scalars().all()
        mode = choose_mode(modes)
        if mode is not None and mode_makes_light(mode.channels):
            return fixture, mode
        if fallback == (None, None):
            fallback = (fixture, mode)

    logger.warning(
        "No '%s' profile in the library has a drivable mode; the fixtures this "
        "template patches will not light", fixture_type,
    )
    return fallback


@router.get("/")
async def list_templates(
    venue_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List rig templates with optional venue type filter."""
    query = select(RigTemplate)
    if venue_type:
        query = query.where(RigTemplate.venue_type == venue_type)
    result = await db.execute(query.order_by(RigTemplate.usage_count.desc()))
    templates = result.scalars().all()
    return {
        "items": [_template_to_dict(t) for t in templates],
        "total": len(templates),
    }


@router.get("/{template_id}")
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Get a template with its fixture slots."""
    result = await db.execute(select(RigTemplate).where(RigTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_dict(template)


@router.post("/")
async def create_template_from_rig(
    rig_id: int = Query(...),
    name: str = Query(...),
    description: Optional[str] = None,
    venue_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Create a template from an existing rig. Abstracts fixture IDs to types."""
    rig_result = await db.execute(select(Rig).where(Rig.id == rig_id))
    rig = rig_result.scalar_one_or_none()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    fixtures_result = await db.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.fixture), selectinload(RigFixture.mode))
    )
    rig_fixtures = fixtures_result.scalars().all()

    # Group fixtures by type and group
    groups = {}
    for rf in rig_fixtures:
        fixture_type = rf.fixture.fixture_type.value if rf.fixture and rf.fixture.fixture_type else "other"
        group_name = rf.group_name or "Default"
        key = f"{fixture_type}_{group_name}"

        if key not in groups:
            groups[key] = {
                "fixture_type": fixture_type,
                "count": 0,
                "group_name": group_name,
                "positions": [],
                "mode_channel_count": rf.mode.channel_count if rf.mode else None,
            }

        groups[key]["count"] += 1
        groups[key]["positions"].append({
            "x": rf.position_x,
            "y": rf.position_y,
            "z": rf.position_z,
            "rotation_y": rf.rotation_y,
        })

    template = RigTemplate(
        name=name,
        description=description,
        venue_type=venue_type or rig.venue,
        stage_width=rig.stage_width,
        stage_depth=rig.stage_depth,
        stage_height=rig.stage_height,
        fixture_slots=list(groups.values()),
        is_system=False,
        is_public=True,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)

    return _template_to_dict(template)


@router.post("/{template_id}/apply")
async def apply_template(
    template_id: int,
    rig_name: str = Query(...),
    venue: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Apply a template to create a new rig.

    Matches fixture slots to available library fixtures by type.
    """
    result = await db.execute(select(RigTemplate).where(RigTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create rig
    rig = Rig(
        name=rig_name,
        venue=venue or template.venue_type,
        stage_width=template.stage_width,
        stage_depth=template.stage_depth,
        stage_height=template.stage_height,
        source_format="template",
        is_active=True,
    )
    db.add(rig)
    await db.flush()

    # Map fixture slots to library fixtures
    dmx_address = 1
    universe = 0
    fixture_num = 1

    for slot in (template.fixture_slots or []):
        fixture_type = slot.get("fixture_type", "other")

        matched, mode = await _pick_profile(db, fixture_type)
        if not matched:
            continue

        channel_count = mode.channel_count if mode else 16
        positions = slot.get("positions", [])
        zone = _validated_zone(slot.get("zone"))

        for i in range(slot.get("count", 1)):
            # Universe boundary check
            if dmx_address + channel_count - 1 > 512:
                universe += 1
                dmx_address = 1

            pos = positions[i] if i < len(positions) else {}

            rf = RigFixture(
                rig_id=rig.id,
                fixture_id=matched.id,
                name=f"{slot.get('group_name', 'Fixture')} {i + 1}",
                fixture_number=fixture_num,
                universe=universe,
                dmx_address=dmx_address,
                mode_id=mode.id if mode else None,
                position_x=pos.get("x", 0.0),
                position_y=pos.get("y", 0.0),
                position_z=pos.get("z", 0.0),
                rotation_y=pos.get("rotation_y", 0.0),
                group_name=slot.get("group_name"),
                zone=zone,
                is_active=True,
            )
            db.add(rf)
            dmx_address += channel_count
            fixture_num += 1

    # Increment template usage
    template.usage_count = (template.usage_count or 0) + 1

    await db.flush()
    await db.refresh(rig)

    return {
        "id": rig.id,
        "name": rig.name,
        "fixture_count": fixture_num - 1,
        "message": f"Rig created from template '{template.name}'",
    }


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a user-created template."""
    result = await db.execute(select(RigTemplate).where(RigTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system templates")

    await db.delete(template)
    return {"message": "Template deleted"}


def _template_to_dict(template: RigTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "venue_type": template.venue_type,
        "stage_width": template.stage_width,
        "stage_depth": template.stage_depth,
        "stage_height": template.stage_height,
        "fixture_slots": template.fixture_slots or [],
        "thumbnail_url": template.thumbnail_url,
        "is_system": template.is_system,
        "is_public": template.is_public,
        "created_by": template.created_by,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "usage_count": template.usage_count or 0,
    }
