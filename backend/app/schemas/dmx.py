"""
DMX Control Schemas
===================

Pydantic schemas for DMX/ArtNet operations.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class DMXChannel(BaseModel):
    """Individual DMX channel value."""
    channel: int = Field(..., ge=1, le=512)
    value: int = Field(..., ge=0, le=255)


class DMXFrame(BaseModel):
    """Single DMX frame (512 channels)."""
    universe: int = Field(default=0, ge=0, le=32767)
    channels: Dict[int, int] = Field(default_factory=dict)  # {channel: value}
    timestamp: Optional[float] = None

    def to_bytes(self) -> bytes:
        """Convert frame to 512-byte DMX packet."""
        data = bytearray(512)
        for channel, value in self.channels.items():
            if 1 <= channel <= 512:
                data[channel - 1] = min(255, max(0, value))
        return bytes(data)


class DMXUniverse(BaseModel):
    """Complete DMX universe state."""
    universe: int = Field(default=0, ge=0, le=32767)
    data: List[int] = Field(
        default_factory=lambda: [0] * 512,
        min_length=512,
        max_length=512
    )

    def get_channel(self, channel: int) -> int:
        """Get value of a specific channel (1-indexed)."""
        if 1 <= channel <= 512:
            return self.data[channel - 1]
        return 0

    def set_channel(self, channel: int, value: int) -> None:
        """Set value of a specific channel (1-indexed)."""
        if 1 <= channel <= 512:
            self.data[channel - 1] = min(255, max(0, value))


class ArtNetConfig(BaseModel):
    """ArtNet configuration.

    ``net`` and ``subnet`` are packed with a 0-15 ``universe`` into the 15-bit
    Port-Address; a ``universe`` above 15 is itself a full Port-Address.
    """
    ip_address: str = "255.255.255.255"
    port: int = Field(default=6454, ge=1, le=65535)
    broadcast: bool = False
    net: int = Field(default=0, ge=0, le=127)
    subnet: int = Field(default=0, ge=0, le=15)
    universes: List[int] = Field(default_factory=lambda: [0])


class DMXFixtureState(BaseModel):
    """State of a single fixture."""
    fixture_id: int
    rig_fixture_id: int
    universe: int
    start_address: int
    channel_values: Dict[str, int] = Field(default_factory=dict)  # {channel_name: value}

    # Calculated high-level values
    intensity: float = Field(default=0.0, ge=0, le=1)
    color: Optional[List[int]] = None  # [R, G, B]
    pan: Optional[float] = None  # degrees
    tilt: Optional[float] = None  # degrees


class DMXSceneState(BaseModel):
    """Complete scene state for all fixtures."""
    timestamp: float
    fixtures: List[DMXFixtureState] = []
    master_intensity: float = Field(default=1.0, ge=0, le=1)


class DMXCueCommand(BaseModel):
    """Command to execute a DMX cue."""
    cue_id: int
    fade_time: float = Field(default=0.0, ge=0)
    delay: float = Field(default=0.0, ge=0)
    priority: int = Field(default=0)


class DMXBlackoutCommand(BaseModel):
    """Command to blackout all fixtures."""
    fade_time: float = Field(default=0.0, ge=0)
    universes: Optional[List[int]] = None  # None = all universes
