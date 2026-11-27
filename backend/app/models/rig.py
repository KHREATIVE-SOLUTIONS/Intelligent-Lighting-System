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

    # The room round the rig, for the 3D view, as a room scan suggested it:
    # `room` (width, depth, height), `risers`, `truss_lines`, `hanging_bands`
    # and `scan` (services/room_scan/extract.py). It travels to the view under
    # the same name as a demo preset's room_shell, which has other keys (dome,
    # balcony, LED walls); the view draws whichever keys are there.
    # Scenery only; the engine never reads it. See docs/ROOM_SCAN.md.
    room_shell = Column(JSON, nullable=True)

    # Where each fixture stood before a room scan moved it, so the move can be
    # undone: `file`, `applied_at`, and `moves` (rig_fixture_id, name, from,
    # to, tags_before). Kept apart from room_shell, which a new scan replaces
    # and removing the room clears: those are when an undo is wanted.
    # Written by the room-scan endpoint only (services/room_scan/undo.py).
    room_scan_undo = Column(JSON, nullable=True)

    # What the stored room was before each edit made to it by hand, latest
    # last, so an edit can be undone one at a time: `steps` (label, at,
    # shell, and `fixtures` where the edit carried the fixtures hung on a
    # truss: each one's from and to). Emptied when a scan is read again or the room is taken off: the
    # steps are of a room that is no longer there. Written by the room-scan
    # endpoint only (services/room_scan/edit_undo.py). Not sent with the rig:
    # `room_shell_edits` below is what a reader gets.
    room_shell_undo = Column(JSON, nullable=True)

    # What the last readiness fix changed, so it can be undone as one step:
    # `fix` ("auto-groups" or "readdress"), `at`, and `entries` (id, name,
    # `before` and `after` of only the columns that fix writes). The next fix
    # that changes something replaces it; an undo spends it. Written by the
    # readiness endpoints only (services/rig/readiness_undo.py).
    readiness_undo = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    @property
    def room_shell_edits(self):
        """How many edits to the stored room can be undone, and what the next undo takes back."""
        from app.services.room_scan.edit_undo import undo_summary

        return undo_summary(self.room_shell_undo)

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
    # What this fixture points at, from the PerformerZone vocabulary. Optional:
    # a rig that declares none behaves as it did before zones existed.
    zone = Column(String(50), nullable=True)
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
