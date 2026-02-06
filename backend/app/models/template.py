"""
Rig Template Models
===================

Database models for reusable rig templates.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    JSON, Text
)

from app.db.database import Base


class RigTemplate(Base):
    """Reusable rig template with fixture slot definitions."""

    __tablename__ = "rig_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    venue_type = Column(String(100), nullable=True)  # "small_club", "theater", etc.

    # Stage dimensions
    stage_width = Column(Float, default=10.0)
    stage_depth = Column(Float, default=8.0)
    stage_height = Column(Float, default=6.0)

    # Fixture slots: [{fixture_type, count, group_name, positions, mode_channel_count}]
    fixture_slots = Column(JSON, default=list)

    # Preview
    thumbnail_url = Column(String(500), nullable=True)

    # Ownership
    is_system = Column(Boolean, default=False)  # Built-in templates
    is_public = Column(Boolean, default=True)
    created_by = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    usage_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<RigTemplate(id={self.id}, name='{self.name}')>"
