"""
Fixture Schemas
===============

Pydantic schemas for fixture library operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import AliasChoices, BaseModel, Field

from app.models.fixture import FixtureType, ChannelType


# Channel Schemas
class ChannelValueRange(BaseModel):
    """Value range for channel presets.

    Importers write these straight to the JSON column; "min"/"max" are accepted
    so a GDTF ChannelSet or an OFL capability still reads back through here.
    """
    name: str
    min_value: int = Field(
        ..., ge=0, le=255, validation_alias=AliasChoices("min_value", "min")
    )
    max_value: int = Field(
        ..., ge=0, le=255, validation_alias=AliasChoices("max_value", "max")
    )

    class Config:
        populate_by_name = True


class FixtureChannelBase(BaseModel):
    """Base fixture channel schema."""
    channel_number: int = Field(..., ge=1)
    channel_type: ChannelType = ChannelType.OTHER
    name: str
    default_value: int = Field(default=0, ge=0, le=255)
    min_value: int = Field(default=0, ge=0, le=255)
    max_value: int = Field(default=255, ge=0, le=255)
    is_fine: bool = False
    coarse_channel: Optional[int] = None
    value_ranges: Optional[List[ChannelValueRange]] = None


class FixtureChannelCreate(FixtureChannelBase):
    """Schema for creating a fixture channel."""
    pass


class FixtureChannelResponse(FixtureChannelBase):
    """Schema for fixture channel response."""
    id: int
    mode_id: int

    class Config:
        from_attributes = True


# Mode Schemas
class FixtureModeBase(BaseModel):
    """Base fixture mode schema."""
    name: str
    channel_count: int = Field(..., ge=1, le=512)
    description: Optional[str] = None


class FixtureModeCreate(FixtureModeBase):
    """Schema for creating a fixture mode."""
    channels: List[FixtureChannelCreate] = []


class FixtureModeResponse(FixtureModeBase):
    """Schema for fixture mode response."""
    id: int
    fixture_id: int
    channels: List[FixtureChannelResponse] = []

    class Config:
        from_attributes = True


# Fixture Schemas
class FixtureBase(BaseModel):
    """Base fixture schema."""
    manufacturer: str = Field(..., min_length=1, max_length=255)
    model: str = Field(..., min_length=1, max_length=255)
    fixture_type: FixtureType = FixtureType.OTHER
    gdtf_id: Optional[str] = None
    gdtf_file: Optional[str] = None
    weight: Optional[float] = Field(default=None, ge=0)
    power: Optional[float] = Field(default=None, ge=0)
    beam_angle: Optional[float] = Field(default=None, ge=0, le=180)
    pan_range: float = Field(default=540.0, ge=0)
    tilt_range: float = Field(default=270.0, ge=0)
    has_rgb: bool = False
    has_cmy: bool = False
    has_color_wheel: bool = False
    color_temp_range: Optional[List[int]] = None
    thumbnail_url: Optional[str] = None
    model_3d_url: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    categories: Optional[List[str]] = None
    popularity_score: int = 0
    is_bundled: bool = False


class FixtureCreate(FixtureBase):
    """Schema for creating a fixture."""
    modes: List[FixtureModeCreate] = []


class FixtureUpdate(BaseModel):
    """Schema for updating a fixture."""
    manufacturer: Optional[str] = Field(default=None, min_length=1, max_length=255)
    model: Optional[str] = Field(default=None, min_length=1, max_length=255)
    fixture_type: Optional[FixtureType] = None
    weight: Optional[float] = Field(default=None, ge=0)
    power: Optional[float] = Field(default=None, ge=0)
    beam_angle: Optional[float] = Field(default=None, ge=0, le=180)
    pan_range: Optional[float] = Field(default=None, ge=0)
    tilt_range: Optional[float] = Field(default=None, ge=0)
    has_rgb: Optional[bool] = None
    has_cmy: Optional[bool] = None
    has_color_wheel: Optional[bool] = None
    color_temp_range: Optional[List[int]] = None
    thumbnail_url: Optional[str] = None
    model_3d_url: Optional[str] = None


class FixtureResponse(FixtureBase):
    """Schema for fixture response."""
    id: int
    created_at: datetime
    updated_at: datetime
    modes: List[FixtureModeResponse] = []

    class Config:
        from_attributes = True


class FixtureListResponse(BaseModel):
    """Schema for paginated fixture list response."""
    items: List[FixtureResponse]
    total: int
    page: int
    size: int
    pages: int
