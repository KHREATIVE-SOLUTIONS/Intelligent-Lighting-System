"""
DMX Control Schemas
===================

Pydantic schemas for DMX/ArtNet operations.
"""

import ipaddress
from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, Field, model_validator


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
            self.data[channel - 1] = min(255, max(0, int(round(value))))


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


def validate_target_ip(ip_address: str, allow_broadcast: bool = False) -> str:
    """A unicast IPv4 destination for lighting data, or ValueError.

    Broadcast (limited, or a host part of .255) only passes when the caller
    asked for it by name: a remembered target must never be the reason a show
    lands on every device on the venue's network.
    """
    text = (ip_address or "").strip()
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(f"'{ip_address}' is not a valid IPv4 address")
    if address.is_unspecified:
        raise ValueError("0.0.0.0 is not a destination")
    if address.is_multicast:
        raise ValueError(
            f"{text} is a multicast address; for sACN multicast set multicast=true instead"
        )
    if text == "255.255.255.255" or text.endswith(".255"):
        if not allow_broadcast:
            raise ValueError(
                f"{text} is a broadcast address; give the node's own IP, "
                "or set allow_broadcast=true to broadcast on purpose"
            )
    elif address.is_reserved:
        raise ValueError(f"{text} is a reserved address")
    return text


class OutputTarget(BaseModel):
    """Where the show is sent: the remembered demo destination.

    ``universe`` is where the engine's first universe (0) lands; later engine
    universes follow on from it. For Art-Net it is the 0-15 Universe field,
    packed with ``net`` and ``subnet`` into the Port-Address. For sACN it is
    the E1.31 universe, 1-63999. Left out, it is 0 for Art-Net and 1 for sACN.
    """
    protocol: Literal["artnet", "sacn"] = "artnet"
    ip_address: Optional[str] = None
    # None means the protocol's own port: 6454 for Art-Net, 5568 for sACN.
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    universe: Optional[int] = None
    net: int = Field(default=0, ge=0, le=127)
    subnet: int = Field(default=0, ge=0, le=15)
    priority: int = Field(default=100, ge=0, le=200)
    multicast: bool = False
    allow_broadcast: bool = False
    source_name: str = Field(
        default="Intelligent Lighting System", min_length=1, max_length=63
    )

    @model_validator(mode="after")
    def _check(self) -> "OutputTarget":
        if self.protocol == "artnet":
            if self.multicast:
                raise ValueError("multicast is an sACN option; Art-Net is unicast or broadcast")
            if self.universe is None:
                self.universe = 0
            if not 0 <= self.universe <= 15:
                raise ValueError(
                    "Art-Net universe must be 0-15 (use net and subnet for the rest "
                    "of the Port-Address)"
                )
        else:
            if self.universe is None:
                self.universe = 1
            if not 1 <= self.universe <= 63999:
                raise ValueError("sACN universe must be 1-63999")

        if self.protocol == "sacn" and self.multicast:
            # Multicast derives its group from the universe; an IP would only mislead.
            self.ip_address = None
        else:
            if not self.ip_address:
                raise ValueError("ip_address is required for a unicast target")
            self.ip_address = validate_target_ip(self.ip_address, self.allow_broadcast)
        return self

    @property
    def resolved_port(self) -> int:
        if self.port is not None:
            return self.port
        return 6454 if self.protocol == "artnet" else 5568


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
    # Bounded: Infinity (which JSON parsing accepts) overflowed the fade and the
    # blackout never happened; a huge value held the request open for ever.
    fade_time: float = Field(default=0.0, ge=0, le=60, allow_inf_nan=False)
    universes: Optional[List[int]] = None  # None = all universes
