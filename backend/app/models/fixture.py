"""
Fixture Models
==============

Database models for fixture library (GDTF-compatible).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, JSON, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class FixtureType(str, enum.Enum):
    """Fixture type enumeration."""
    MOVING_HEAD = "moving_head"
    LED_PAR = "led_par"
    LED_BAR = "led_bar"
    WASH = "wash"
    SPOT = "spot"
    BEAM = "beam"
    STROBE = "strobe"
    LASER = "laser"
    EFFECT = "effect"
    DIMMER = "dimmer"
    OTHER = "other"


class ChannelType(str, enum.Enum):
    """DMX channel type enumeration.

    Persisted by member NAME, so the longest name sets the stored column width;
    widening it is a migration (see 003_extended_channel_types).
    """
    DIMMER = "dimmer"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    WHITE = "white"
    AMBER = "amber"
    UV = "uv"
    LIME = "lime"
    INDIGO = "indigo"
    CYAN = "cyan"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    CTO = "cto"
    CTB = "ctb"
    PAN = "pan"
    PAN_FINE = "pan_fine"
    TILT = "tilt"
    TILT_FINE = "tilt_fine"
    ZOOM = "zoom"
    FOCUS = "focus"
    IRIS = "iris"
    FROST = "frost"
    GOBO = "gobo"
    GOBO_ROTATION = "gobo_rotation"
    GOBO2 = "gobo2"
    GOBO2_ROTATION = "gobo2_rotation"
    ANIMATION = "animation"
    FRAMING = "framing"
    PRISM = "prism"
    COLOR_WHEEL = "color_wheel"
    SHUTTER = "shutter"
    STROBE = "strobe"
    SPEED = "speed"
    EFFECT = "effect"
    MACRO = "macro"
    OTHER = "other"


class Fixture(Base):
    """Fixture model representing a fixture type in the library."""

    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True)
    manufacturer = Column(String(255), nullable=False, index=True)
    model = Column(String(255), nullable=False, index=True)
    fixture_type = Column(SQLEnum(FixtureType), default=FixtureType.OTHER)

    # GDTF identifiers
    gdtf_id = Column(String(100), nullable=True, unique=True)
    gdtf_file = Column(String(500), nullable=True)

    # Physical properties
    weight = Column(Float, nullable=True)  # kg
    power = Column(Float, nullable=True)  # watts
    beam_angle = Column(Float, nullable=True)  # degrees

    # Pan/Tilt range
    pan_range = Column(Float, default=540.0)  # degrees
    tilt_range = Column(Float, default=270.0)  # degrees

    # Color capabilities
    has_rgb = Column(Boolean, default=False)
    has_cmy = Column(Boolean, default=False)
    has_color_wheel = Column(Boolean, default=False)
    color_temp_range = Column(JSON, nullable=True)  # [min_k, max_k]

    # Thumbnail/preview
    thumbnail_url = Column(String(500), nullable=True)
    model_3d_url = Column(String(500), nullable=True)

    # Library source tracking
    source = Column(String(50), nullable=True)  # "ofl", "gdtf", "manual", "bundled"
    source_id = Column(String(255), nullable=True)  # External ID (e.g., "chauvet-dj/rogue-r2-wash")
    categories = Column(JSON, nullable=True)  # ["wash", "led", "indoor"]
    popularity_score = Column(Integer, default=0)
    is_bundled = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    modes = relationship("FixtureMode", back_populates="fixture", cascade="all, delete-orphan")
    rig_fixtures = relationship("RigFixture", back_populates="fixture")

    def __repr__(self):
        return f"<Fixture(id={self.id}, manufacturer='{self.manufacturer}', model='{self.model}')>"


class FixtureMode(Base):
    """Fixture mode/profile configuration."""

    __tablename__ = "fixture_modes"

    id = Column(Integer, primary_key=True, index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., "Standard", "Extended", "Basic"
    channel_count = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)

    # Relationships
    fixture = relationship("Fixture", back_populates="modes")
    channels = relationship("FixtureChannel", back_populates="mode", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FixtureMode(id={self.id}, name='{self.name}', channels={self.channel_count})>"


class FixtureChannel(Base):
    """Individual channel definition within a fixture mode."""

    __tablename__ = "fixture_channels"

    id = Column(Integer, primary_key=True, index=True)
    mode_id = Column(Integer, ForeignKey("fixture_modes.id"), nullable=False)

    channel_number = Column(Integer, nullable=False)  # 1-indexed
    channel_type = Column(SQLEnum(ChannelType), default=ChannelType.OTHER)
    name = Column(String(100), nullable=False)

    # Value range
    default_value = Column(Integer, default=0)
    min_value = Column(Integer, default=0)
    max_value = Column(Integer, default=255)

    # Fine channel pairing
    is_fine = Column(Boolean, default=False)
    coarse_channel = Column(Integer, nullable=True)  # Reference to coarse channel number

    # Value ranges/presets (for gobos, colors, etc.)
    value_ranges = Column(JSON, nullable=True)  # [{name, min_value, max_value}, ...]

    # Relationships
    mode = relationship("FixtureMode", back_populates="channels")

    def __repr__(self):
        return f"<FixtureChannel(id={self.id}, ch={self.channel_number}, type={self.channel_type})>"
