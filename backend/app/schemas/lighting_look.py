"""
Lighting Look Specification Schemas
==================================

Typed contract describing section/genre-aware beam and spot intent.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class BeamLookParams(BaseModel):
    beam_angle_deg: float = Field(..., ge=1.0, le=60.0)
    beam_width_normalized: float = Field(..., ge=0.0, le=1.0)
    beam_width_profile: str = "balanced"
    phrase_phase: float = Field(..., ge=0.0, le=1.0)
    density: float = Field(..., ge=0.0, le=1.0)
    strobe_mode: str
    movement_pattern: str
    movement_speed_hz: float = Field(..., ge=0.0, le=20.0)


class SpotLookParams(BaseModel):
    focus_mode: str
    gobo_mode: str
    zoom: float = Field(..., ge=0.0, le=1.0)
    iris: float = Field(..., ge=0.0, le=1.0)
    key_priority: float = Field(..., ge=0.0, le=1.0)


class ColorLookParams(BaseModel):
    palette_id: str
    dominant_color: str
    accent_color: str
    saturation: float = Field(..., ge=0.0, le=1.0)
    white_level: float = Field(..., ge=0.0, le=1.0)


class TransitionLookParams(BaseModel):
    mib_enabled: bool
    transition_ms: int = Field(..., ge=0, le=10000)
    blackout_policy: str


class FixtureCapabilityProfile(BaseModel):
    role: str
    supports_gobo: bool = False
    supports_prism: bool = False
    supports_frost: bool = False
    supports_zoom: bool = False
    supports_focus: bool = False
    supports_iris: bool = False
    movement_speed_class: str = "medium"


class LightingLookSpec(BaseModel):
    timestamp: datetime
    section: str
    genre: str
    energy: float = Field(..., ge=0.0, le=1.0)
    bpm: float = Field(..., ge=0.0, le=300.0)
    palette_version: int = Field(default=1, ge=1)
    palette_locked: bool = False
    beam: BeamLookParams
    spot: SpotLookParams
    color: ColorLookParams
    transition: TransitionLookParams
    fixture_capabilities: dict[str, FixtureCapabilityProfile] = Field(default_factory=dict)
