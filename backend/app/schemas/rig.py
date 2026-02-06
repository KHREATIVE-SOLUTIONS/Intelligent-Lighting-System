"""
Rig Schemas
===========

Pydantic schemas for rig-related API operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# Rig Fixture Schemas
class RigFixtureBase(BaseModel):
    """Base rig fixture schema."""
    fixture_id: int
    name: Optional[str] = None
    fixture_number: Optional[int] = None
    universe: int = Field(default=0, ge=0, le=15)
    dmx_address: int = Field(..., ge=1, le=512)
    mode_id: Optional[int] = None
    position_x: float = Field(default=0.0)
    position_y: float = Field(default=0.0)
    position_z: float = Field(default=0.0)
    rotation_x: float = Field(default=0.0)
    rotation_y: float = Field(default=0.0)
    rotation_z: float = Field(default=0.0)
    group_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_inverted: bool = False
    is_address_locked: bool = False
    serial_number: Optional[str] = None
    qr_code_data: Optional[str] = None


class RigFixtureCreate(RigFixtureBase):
    """Schema for creating a rig fixture."""
    pass


class RigFixtureUpdate(BaseModel):
    """Schema for updating a rig fixture."""
    name: Optional[str] = None
    fixture_number: Optional[int] = None
    universe: Optional[int] = Field(default=None, ge=0, le=15)
    dmx_address: Optional[int] = Field(default=None, ge=1, le=512)
    mode_id: Optional[int] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_x: Optional[float] = None
    rotation_y: Optional[float] = None
    rotation_z: Optional[float] = None
    group_name: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_inverted: Optional[bool] = None
    is_address_locked: Optional[bool] = None
    serial_number: Optional[str] = None
    qr_code_data: Optional[str] = None


class RigFixtureResponse(RigFixtureBase):
    """Schema for rig fixture response."""
    id: int
    rig_id: int
    fixture: Optional[Dict[str, Any]] = None  # Nested fixture info

    class Config:
        from_attributes = True


# Rig Schemas
class UniverseConfig(BaseModel):
    """DMX universe configuration."""
    universe: int = Field(..., ge=0, le=15)
    protocol: str = "artnet"  # artnet, sacn, dmx
    ip_address: Optional[str] = None
    port: int = 6454


class RigBase(BaseModel):
    """Base rig schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    venue: Optional[str] = None
    stage_width: float = Field(default=10.0, gt=0)
    stage_depth: float = Field(default=8.0, gt=0)
    stage_height: float = Field(default=6.0, gt=0)
    universes: List[Dict[str, Any]] = Field(default_factory=list)  # Universe configurations


class RigCreate(RigBase):
    """Schema for creating a rig."""
    pass


class RigUpdate(BaseModel):
    """Schema for updating a rig."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    venue: Optional[str] = None
    stage_width: Optional[float] = Field(default=None, gt=0)
    stage_depth: Optional[float] = Field(default=None, gt=0)
    stage_height: Optional[float] = Field(default=None, gt=0)
    universes: Optional[List[Dict[str, Any]]] = None  # Universe configurations
    is_active: Optional[bool] = None


class RigResponse(RigBase):
    """Schema for rig response."""
    id: int
    source_format: Optional[str] = None
    source_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    is_active: bool
    fixtures: List[RigFixtureResponse] = []

    class Config:
        from_attributes = True


class RigListResponse(BaseModel):
    """Schema for paginated rig list response."""
    items: List[RigResponse]
    total: int
    page: int
    size: int
    pages: int
