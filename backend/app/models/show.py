"""
Show Models
===========

Database models for lighting shows, cues, and tracks.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, JSON, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class ShowStatus(str, enum.Enum):
    """Show status enumeration."""
    DRAFT = "draft"
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"


class CueType(str, enum.Enum):
    """Cue type enumeration."""
    STATIC = "static"
    FADE = "fade"
    CHASE = "chase"
    EFFECT = "effect"
    AUDIO_REACTIVE = "audio_reactive"


class Show(Base):
    """Show model representing a complete lighting show."""

    __tablename__ = "shows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    duration = Column(Float, nullable=True)  # Duration in seconds
    bpm = Column(Float, nullable=True)
    status = Column(SQLEnum(ShowStatus), default=ShowStatus.DRAFT)

    # Mood/emotion mapping
    base_valence = Column(Float, default=0.5)  # 0=negative, 1=positive
    base_arousal = Column(Float, default=0.5)  # 0=calm, 1=energetic

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Audio fingerprint for song matching
    audio_fingerprint_id = Column(Integer, ForeignKey("audio_fingerprints.id"), nullable=True)

    # Relationships
    cues = relationship("ShowCue", back_populates="show", cascade="all, delete-orphan")
    tracks = relationship("ShowTrack", back_populates="show", cascade="all, delete-orphan")
    audio_fingerprint = relationship("AudioFingerprint", back_populates="shows")

    def __repr__(self):
        return f"<Show(id={self.id}, name='{self.name}', status={self.status})>"


class ShowTrack(Base):
    """Track within a show for organizing cues."""

    __tablename__ = "show_tracks"

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    name = Column(String(255), nullable=False)
    track_type = Column(String(50), default="fixture")  # fixture, effect, master
    order = Column(Integer, default=0)
    muted = Column(Boolean, default=False)
    solo = Column(Boolean, default=False)

    # Target fixtures (JSON array of fixture IDs)
    fixture_ids = Column(JSON, default=list)

    # Relationships
    show = relationship("Show", back_populates="tracks")
    cues = relationship("ShowCue", back_populates="track", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ShowTrack(id={self.id}, name='{self.name}')>"


class ShowCue(Base):
    """Individual cue within a show track."""

    __tablename__ = "show_cues"

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    track_id = Column(Integer, ForeignKey("show_tracks.id"), nullable=True)

    name = Column(String(255), nullable=True)
    cue_type = Column(SQLEnum(CueType), default=CueType.STATIC)

    # Timing
    start_time = Column(Float, nullable=False)  # Start time in seconds
    duration = Column(Float, default=1.0)  # Duration in seconds
    fade_in = Column(Float, default=0.0)  # Fade in time
    fade_out = Column(Float, default=0.0)  # Fade out time

    # DMX values (JSON object: {channel: value})
    dmx_values = Column(JSON, default=dict)

    # Effect parameters
    effect_type = Column(String(50), nullable=True)
    effect_params = Column(JSON, default=dict)

    # Audio-reactive settings
    audio_reactive = Column(Boolean, default=False)
    audio_trigger = Column(String(50), nullable=True)  # beat, frequency_band, mood
    audio_params = Column(JSON, default=dict)

    # Emotion mapping
    valence = Column(Float, nullable=True)
    arousal = Column(Float, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    show = relationship("Show", back_populates="cues")
    track = relationship("ShowTrack", back_populates="cues")

    def __repr__(self):
        return f"<ShowCue(id={self.id}, type={self.cue_type}, start={self.start_time})>"
