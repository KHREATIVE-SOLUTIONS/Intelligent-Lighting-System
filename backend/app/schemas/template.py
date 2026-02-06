"""
Rig Template Schemas
====================

Pydantic schemas for rig template operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FixtureSlot(BaseModel):
    """A fixture slot within a template."""
    fixture_type: str  # FixtureType value
    count: int = Field(default=1, ge=1)
    group_name: Optional[str] = None
    positions: Optional[List[Dict[str, float]]] = None  # [{x, y, z, rotation_y}]
    mode_channel_count: Optional[int] = None


class RigTemplateBase(BaseModel):
    """Base rig template schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    venue_type: Optional[str] = None
    stage_width: float = Field(default=10.0, gt=0)
    stage_depth: float = Field(default=8.0, gt=0)
    stage_height: float = Field(default=6.0, gt=0)
    fixture_slots: List[FixtureSlot] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    is_public: bool = True


class RigTemplateCreate(RigTemplateBase):
    """Schema for creating a rig template."""
    pass


class RigTemplateResponse(RigTemplateBase):
    """Schema for rig template response."""
    id: int
    is_system: bool
    created_by: Optional[str] = None
    created_at: datetime
    usage_count: int = 0

    class Config:
        from_attributes = True


class RigTemplateListResponse(BaseModel):
    """Schema for paginated template list."""
    items: List[RigTemplateResponse]
    total: int


class TemplateApplyRequest(BaseModel):
    """Request to apply a template and create a rig."""
    rig_name: str = Field(..., min_length=1, max_length=255)
    venue: Optional[str] = None
    fixture_mapping: Dict[str, int] = Field(default_factory=dict)  # slot_fixture_type -> fixture_id
