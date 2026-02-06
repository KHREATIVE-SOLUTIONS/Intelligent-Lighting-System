"""
Show Schemas
============

Pydantic schemas for show-related API operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.models.show import ShowStatus, CueType


# Cue Schemas
class CueBase(BaseModel):
    """Base cue schema."""
    name: Optional[str] = None
    cue_type: CueType = CueType.STATIC
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    duration: float = Field(default=1.0, ge=0)
    fade_in: float = Field(default=0.0, ge=0)
    fade_out: float = Field(default=0.0, ge=0)
    dmx_values: Dict[str, int] = Field(default_factory=dict)
    effect_type: Optional[str] = None
    effect_params: Dict[str, Any] = Field(default_factory=dict)
    audio_reactive: bool = False
    audio_trigger: Optional[str] = None
    audio_params: Dict[str, Any] = Field(default_factory=dict)
    valence: Optional[float] = Field(default=None, ge=-1, le=1)
    arousal: Optional[float] = Field(default=None, ge=-1, le=1)


class CueCreate(CueBase):
    """Schema for creating a cue."""
    track_id: Optional[int] = None


class CueUpdate(BaseModel):
    """Schema for updating a cue."""
    name: Optional[str] = None
    cue_type: Optional[CueType] = None
    start_time: Optional[float] = Field(default=None, ge=0)
    duration: Optional[float] = Field(default=None, ge=0)
    fade_in: Optional[float] = Field(default=None, ge=0)
    fade_out: Optional[float] = Field(default=None, ge=0)
    dmx_values: Optional[Dict[str, int]] = None
    effect_type: Optional[str] = None
    effect_params: Optional[Dict[str, Any]] = None
    audio_reactive: Optional[bool] = None
    audio_trigger: Optional[str] = None
    audio_params: Optional[Dict[str, Any]] = None
    valence: Optional[float] = Field(default=None, ge=-1, le=1)
    arousal: Optional[float] = Field(default=None, ge=-1, le=1)


class CueResponse(CueBase):
    """Schema for cue response."""
    id: int
    show_id: int
    track_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Track Schemas
class TrackBase(BaseModel):
    """Base track schema."""
    name: str
    track_type: str = "fixture"
    order: int = 0
    muted: bool = False
    solo: bool = False
    fixture_ids: List[int] = Field(default_factory=list)


class TrackCreate(TrackBase):
    """Schema for creating a track."""
    pass


class TrackUpdate(BaseModel):
    """Schema for updating a track."""
    name: Optional[str] = None
    track_type: Optional[str] = None
    order: Optional[int] = None
    muted: Optional[bool] = None
    solo: Optional[bool] = None
    fixture_ids: Optional[List[int]] = None


class TrackResponse(TrackBase):
    """Schema for track response."""
    id: int
    show_id: int
    cues: List[CueResponse] = []

    class Config:
        from_attributes = True


# Show Schemas
class ShowBase(BaseModel):
    """Base show schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    duration: Optional[float] = Field(default=None, ge=0)
    bpm: Optional[float] = Field(default=None, ge=0, le=300)
    base_valence: float = Field(default=0.5, ge=0, le=1)
    base_arousal: float = Field(default=0.5, ge=0, le=1)


class ShowCreate(ShowBase):
    """Schema for creating a show."""
    pass


class ShowUpdate(BaseModel):
    """Schema for updating a show."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    duration: Optional[float] = Field(default=None, ge=0)
    bpm: Optional[float] = Field(default=None, ge=0, le=300)
    status: Optional[ShowStatus] = None
    base_valence: Optional[float] = Field(default=None, ge=0, le=1)
    base_arousal: Optional[float] = Field(default=None, ge=0, le=1)


class ShowResponse(ShowBase):
    """Schema for show response."""
    id: int
    status: ShowStatus
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    audio_fingerprint_id: Optional[int] = None
    tracks: List[TrackResponse] = []
    cues: List[CueResponse] = []

    class Config:
        from_attributes = True


class ShowListResponse(BaseModel):
    """Schema for paginated show list response."""
    items: List[ShowResponse]
    total: int
    page: int
    size: int
    pages: int
