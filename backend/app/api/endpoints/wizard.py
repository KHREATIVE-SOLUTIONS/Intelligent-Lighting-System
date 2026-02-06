"""
Quick Rig Wizard Endpoints
===========================

API endpoints for the guided rig creation wizard with venue presets
and auto-placement.
"""

import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture, FixtureMode
from app.services.rig.wizard_service import WizardService

logger = logging.getLogger(__name__)
router = APIRouter()


class AutoPlaceRequest(BaseModel):
    stage_width: float = Field(default=10.0, gt=0)
    stage_depth: float = Field(default=8.0, gt=0)
    stage_height: float = Field(default=6.0, gt=0)
    fixtures: List[Dict[str, Any]]


class CreateRigFromWizardRequest(BaseModel):
    rig_name: str = Field(..., min_length=1, max_length=255)
    venue: Optional[str] = None
    stage_width: float = Field(default=10.0, gt=0)
    stage_depth: float = Field(default=8.0, gt=0)
    stage_height: float = Field(default=6.0, gt=0)
    placements: List[Dict[str, Any]]


@router.get("/venue-presets")
async def get_venue_presets():
    """List all venue presets."""
    presets = WizardService.get_venue_presets()
    return {"presets": presets}


@router.get("/venue-presets/{key}")
async def get_venue_preset(key: str):
    """Get a specific venue preset with details."""
    preset = WizardService.get_venue_preset(key)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Venue preset '{key}' not found")
    return preset


@router.get("/venue-presets/{key}/suggestions")
async def get_venue_suggestions(
    key: str,
    db: Session = Depends(get_db),
):
    """Get fixture suggestions matched to the local library for a venue preset."""
    preset = WizardService.get_venue_preset(key)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Venue preset '{key}' not found")

    suggestions = []
    for suggested in preset.get("suggested_fixtures", []):
        fixture_type = suggested["fixture_type"]

        # Try to find a matching fixture in the library
        matched = (
            db.query(Fixture)
            .filter(Fixture.fixture_type == fixture_type)
            .options(joinedload(Fixture.modes).joinedload(FixtureMode.channels))
            .first()
        )

        suggestion = {
            **suggested,
            "matched_fixture": None,
        }

        if matched:
            suggestion["matched_fixture"] = {
                "id": matched.id,
                "manufacturer": matched.manufacturer,
                "model": matched.model,
                "fixture_type": matched.fixture_type.value if matched.fixture_type else "other",
                "modes": [
                    {"id": m.id, "name": m.name, "channel_count": m.channel_count}
                    for m in (matched.modes or [])
                ],
            }

        suggestions.append(suggestion)

    return {
        "preset": preset,
        "suggestions": suggestions,
    }


@router.post("/auto-place")
async def auto_place_fixtures(request: AutoPlaceRequest):
    """Compute optimal fixture placement positions."""
    placements = WizardService.compute_placement(
        stage_width=request.stage_width,
        stage_depth=request.stage_depth,
        stage_height=request.stage_height,
        fixtures=request.fixtures,
    )
    return {"placements": placements}


@router.post("/create-rig")
async def create_rig_from_wizard(
    request: CreateRigFromWizardRequest,
    db: Session = Depends(get_db),
):
    """Create a complete rig from wizard data."""
    # Create the rig
    rig = Rig(
        name=request.rig_name,
        venue=request.venue,
        stage_width=request.stage_width,
        stage_depth=request.stage_depth,
        stage_height=request.stage_height,
        source_format="wizard",
        is_active=True,
    )
    db.add(rig)
    db.flush()

    # Create rig fixtures from placements
    for i, placement in enumerate(request.placements):
        rf = RigFixture(
            rig_id=rig.id,
            fixture_id=placement["fixture_id"],
            name=placement.get("name", f"Fixture {i + 1}"),
            fixture_number=i + 1,
            universe=placement.get("universe", 0),
            dmx_address=placement["dmx_address"],
            mode_id=placement.get("mode_id"),
            position_x=placement.get("position_x", 0.0),
            position_y=placement.get("position_y", 0.0),
            position_z=placement.get("position_z", 0.0),
            rotation_y=placement.get("rotation_y", 0.0),
            group_name=placement.get("group_name"),
            is_active=True,
        )
        db.add(rf)

    db.commit()
    db.refresh(rig)

    # Return the created rig
    return {
        "id": rig.id,
        "name": rig.name,
        "venue": rig.venue,
        "stage_width": rig.stage_width,
        "stage_depth": rig.stage_depth,
        "stage_height": rig.stage_height,
        "fixture_count": len(request.placements),
        "message": f"Rig '{rig.name}' created with {len(request.placements)} fixtures",
    }
