"""
RDM Device Models
=================

Database models for RDM auto-discovered devices.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON
)

from app.db.database import Base


class RDMDevice(Base):
    """RDM-discovered device record."""

    __tablename__ = "rdm_devices"

    id = Column(Integer, primary_key=True, index=True)

    # RDM UID (manufacturer + device)
    uid_manufacturer = Column(Integer, nullable=False)
    uid_device = Column(Integer, nullable=False)

    # Device info from RDM queries
    manufacturer_label = Column(String(255), nullable=True)
    model_description = Column(String(255), nullable=True)
    device_label = Column(String(255), nullable=True)

    # DMX personality
    dmx_footprint = Column(Integer, nullable=True)
    current_personality = Column(Integer, nullable=True)
    personality_count = Column(Integer, nullable=True)
    personalities = Column(JSON, nullable=True)  # [{index, channel_count, description}]

    # Current addressing
    dmx_address = Column(Integer, nullable=True)
    universe = Column(Integer, default=0)

    # Supported parameters
    supported_parameters = Column(JSON, nullable=True)

    # Library match
    matched_fixture_id = Column(Integer, nullable=True)  # FK to fixtures.id if matched
    is_imported = Column(Boolean, default=False)

    # Discovery metadata
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RDMDevice(uid={self.uid_manufacturer}:{self.uid_device}, model='{self.model_description}')>"
