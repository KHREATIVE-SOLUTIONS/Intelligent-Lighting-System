"""
Rig Schemas
===========

Pydantic schemas for rig-related API operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable


_FIXTURE_FIELDS = (
    "id", "manufacturer", "model", "fixture_type", "gdtf_id", "weight", "power",
    "beam_angle", "pan_range", "tilt_range", "has_rgb", "has_cmy", "has_color_wheel",
    "color_temp_range", "thumbnail_url", "model_3d_url", "source", "source_id",
    "categories", "popularity_score", "is_bundled",
)
_MODE_FIELDS = ("id", "fixture_id", "name", "channel_count", "description")
_CHANNEL_FIELDS = (
    "id", "mode_id", "channel_number", "channel_type", "name", "default_value",
    "min_value", "max_value", "is_fine", "coarse_channel", "value_ranges",
)


def _unloaded(obj: Any) -> frozenset:
    """Names of ORM attributes that would emit IO if read."""
    try:
        return frozenset(sa_inspect(obj).unloaded)
    except NoInspectionAvailable:
        return frozenset()


def _serialize_fixture(fixture: Any) -> Any:
    """Flatten an ORM fixture into a plain dict.

    Relationships that are not already eager-loaded are omitted rather than
    walked: reading them would emit IO, which raises MissingGreenlet under an
    AsyncSession.
    """
    if fixture is None or isinstance(fixture, dict):
        return fixture

    data: Dict[str, Any] = {
        name: getattr(fixture, name, None) for name in _FIXTURE_FIELDS
    }
    if "modes" not in _unloaded(fixture):
        data["modes"] = [_serialize_mode(mode) for mode in fixture.modes]
    return data


def _serialize_mode(mode: Any) -> Dict[str, Any]:
    """Flatten an ORM fixture mode, including its channels when loaded."""
    data: Dict[str, Any] = {name: getattr(mode, name, None) for name in _MODE_FIELDS}
    if "channels" not in _unloaded(mode):
        data["channels"] = [
            {name: getattr(channel, name, None) for name in _CHANNEL_FIELDS}
            for channel in mode.channels
        ]
    return data


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

    @field_validator("fixture", mode="before")
    @classmethod
    def _coerce_fixture(cls, value: Any) -> Any:
        return _serialize_fixture(value)


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
