"""
Rig Models
==========

Database models for lighting rigs and fixture placements.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, JSON, Text
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Rig(Base):
    """Rig model representing a complete lighting rig setup."""

    __tablename__ = "rigs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    venue = Column(String(255), nullable=True)

    # Stage dimensions
    stage_width = Column(Float, default=10.0)  # meters
    stage_depth = Column(Float, default=8.0)
    stage_height = Column(Float, default=6.0)

    # DMX universe configuration
    universes = Column(JSON, default=list)  # List of universe configs

    # Import source
    source_format = Column(String(50), nullable=True)  # "mvr", "gdtf", "console", "manual"
    source_file = Column(String(500), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    fixtures = relationship("RigFixture", back_populates="rig", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Rig(id={self.id}, name='{self.name}')>"


class RigFixture(Base):
    """Fixture placement within a rig."""

    __tablename__ = "rig_fixtures"

    id = Column(Integer, primary_key=True, index=True)
    rig_id = Column(Integer, ForeignKey("rigs.id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)

    # Instance identification
    name = Column(String(255), nullable=True)  # Custom name for this instance
    fixture_number = Column(Integer, nullable=True)  # Operator-friendly number

    # DMX addressing
    universe = Column(Integer, default=0)
    dmx_address = Column(Integer, nullable=False)
    mode_id = Column(Integer, ForeignKey("fixture_modes.id"), nullable=True)

    # 3D Position (meters from stage origin)
    position_x = Column(Float, default=0.0)
    position_y = Column(Float, default=0.0)  # Height
    position_z = Column(Float, default=0.0)  # Depth

    # Orientation (degrees)
    rotation_x = Column(Float, default=0.0)  # Tilt
    rotation_y = Column(Float, default=0.0)  # Pan
    rotation_z = Column(Float, default=0.0)  # Roll

    # Grouping
    group_name = Column(String(100), nullable=True)
    tags = Column(JSON, default=list)

    # Status
    is_active = Column(Boolean, default=True)
    is_inverted = Column(Boolean, default=False)
    is_address_locked = Column(Boolean, default=False)

    # Identification
    serial_number = Column(String(100), nullable=True)
    qr_code_data = Column(String(500), nullable=True)

    # Relationships
    rig = relationship("Rig", back_populates="fixtures")
    fixture = relationship("Fixture", back_populates="rig_fixtures")
    mode = relationship("FixtureMode")

    def __repr__(self):
        return f"<RigFixture(id={self.id}, address={self.dmx_address})>"
