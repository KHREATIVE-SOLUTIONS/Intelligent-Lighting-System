"""
Open Fixture Library Client
============================

Integration with the Open Fixture Library (OFL) API for searching and
importing community-maintained fixture definitions.
"""

import logging
from typing import List, Optional, Dict, Any

import httpx

from app.models.fixture import FixtureType, ChannelType

logger = logging.getLogger(__name__)

OFL_API_BASE = "https://open-fixture-library.org/api/v1"

# Map OFL fixture categories to our FixtureType enum
OFL_CATEGORY_MAP = {
    "Moving Head": FixtureType.MOVING_HEAD,
    "Color Changer": FixtureType.WASH,
    "Dimmer": FixtureType.DIMMER,
    "Effect": FixtureType.EFFECT,
    "Fan": FixtureType.OTHER,
    "Flower": FixtureType.EFFECT,
    "Hazer": FixtureType.OTHER,
    "Laser": FixtureType.LASER,
    "Barrel Scanner": FixtureType.SPOT,
    "Stand": FixtureType.OTHER,
    "Pixel Bar": FixtureType.LED_BAR,
    "Blinder": FixtureType.STROBE,
    "Strobe": FixtureType.STROBE,
    "Smoke": FixtureType.OTHER,
    "Other": FixtureType.OTHER,
}

# Map OFL channel type strings to our ChannelType enum
OFL_CHANNEL_TYPE_MAP = {
    "Intensity": ChannelType.DIMMER,
    "Single Color": None,  # Handled by color name lookup
    "Multi-Color": ChannelType.COLOR_WHEEL,
    "Pan": ChannelType.PAN,
    "Tilt": ChannelType.TILT,
    "Beam": ChannelType.ZOOM,
    "Gobo": ChannelType.GOBO,
    "Prism": ChannelType.PRISM,
    "Shutter": ChannelType.SHUTTER,
    "Strobe": ChannelType.STROBE,
    "Speed": ChannelType.SPEED,
    "Effect": ChannelType.EFFECT,
    "Maintenance": ChannelType.OTHER,
    "NoFunction": ChannelType.OTHER,
    "Focus": ChannelType.FOCUS,
    "Zoom": ChannelType.ZOOM,
}

OFL_COLOR_MAP = {
    "Red": ChannelType.RED,
    "Green": ChannelType.GREEN,
    "Blue": ChannelType.BLUE,
    "White": ChannelType.WHITE,
    "Amber": ChannelType.AMBER,
    "UV": ChannelType.UV,
    "Warm White": ChannelType.WHITE,
    "Cool White": ChannelType.WHITE,
}


class OFLClient:
    """Client for the Open Fixture Library API."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=OFL_API_BASE,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self):
        await self._client.aclose()

    async def search_fixtures(
        self, query: str, manufacturer: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search OFL for fixtures matching query."""
        params = {"q": query}
        if manufacturer:
            params["manufacturer"] = manufacturer

        try:
            response = await self._client.get("/fixtures/search", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"OFL search failed: {e}")
            return []

    async def get_fixture(
        self, manufacturer_key: str, fixture_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get full fixture definition from OFL."""
        try:
            response = await self._client.get(
                f"/fixtures/{manufacturer_key}/{fixture_key}"
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"OFL fixture fetch failed: {e}")
            return None

    async def list_manufacturers(self) -> List[Dict[str, Any]]:
        """List all manufacturers from OFL."""
        try:
            response = await self._client.get("/manufacturers")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"OFL manufacturers fetch failed: {e}")
            return []


def _resolve_channel_type(ofl_channel: Dict[str, Any]) -> ChannelType:
    """Map an OFL channel definition to our ChannelType."""
    ch_type = ofl_channel.get("type", "")

    # Handle color channels specifically
    if ch_type == "Single Color":
        color = ofl_channel.get("color", "")
        return OFL_COLOR_MAP.get(color, ChannelType.OTHER)

    # Check fine channel
    fine_of = ofl_channel.get("fineChannelAliases")
    if fine_of:
        base_type = OFL_CHANNEL_TYPE_MAP.get(ch_type, ChannelType.OTHER)
        if base_type == ChannelType.PAN:
            return ChannelType.PAN
        if base_type == ChannelType.TILT:
            return ChannelType.TILT

    return OFL_CHANNEL_TYPE_MAP.get(ch_type, ChannelType.OTHER)


def convert_ofl_to_internal(
    ofl_data: Dict[str, Any],
    manufacturer_key: str,
    fixture_key: str,
) -> Dict[str, Any]:
    """Convert an OFL fixture definition to our FixtureCreate schema dict.

    Returns a dict compatible with FixtureCreate.
    """
    # Extract basic info
    name = ofl_data.get("name", fixture_key)
    manufacturer = manufacturer_key.replace("-", " ").title()

    # Determine fixture type from categories
    categories = ofl_data.get("categories", [])
    fixture_type = FixtureType.OTHER
    for cat in categories:
        if cat in OFL_CATEGORY_MAP:
            fixture_type = OFL_CATEGORY_MAP[cat]
            break

    # Extract physical properties
    physical = ofl_data.get("physical", {})
    weight = physical.get("weight")
    power = physical.get("power")
    lens = physical.get("lens", {})
    beam_angle = None
    if lens and "degreesMinMax" in lens:
        deg = lens["degreesMinMax"]
        beam_angle = deg[0] if isinstance(deg, list) and deg else None

    # Detect color capabilities
    available_channels = ofl_data.get("availableChannels", {})
    has_rgb = False
    has_color_wheel = False
    for ch_key, ch_def in available_channels.items():
        ch_type = ch_def.get("type", "")
        if ch_type == "Single Color":
            color = ch_def.get("color", "")
            if color in ("Red", "Green", "Blue"):
                has_rgb = True
        elif ch_type == "Multi-Color":
            has_color_wheel = True

    # Build modes
    modes = []
    ofl_modes = ofl_data.get("modes", [])
    for ofl_mode in ofl_modes:
        mode_name = ofl_mode.get("name", "Default")
        mode_channels_keys = ofl_mode.get("channels", [])

        channels = []
        ch_num = 1
        for ch_key in mode_channels_keys:
            if ch_key is None:
                # Null channel = gap/unused
                channels.append({
                    "channel_number": ch_num,
                    "channel_type": ChannelType.OTHER.value,
                    "name": f"Unused {ch_num}",
                    "default_value": 0,
                })
                ch_num += 1
                continue

            # Resolve fine channel references
            ch_def = available_channels.get(ch_key, {})
            if not ch_def:
                # Could be a fine channel alias
                channels.append({
                    "channel_number": ch_num,
                    "channel_type": ChannelType.OTHER.value,
                    "name": ch_key,
                    "default_value": 0,
                })
                ch_num += 1
                continue

            channel_type = _resolve_channel_type(ch_def)
            default_val = ch_def.get("defaultValue", 0)
            if isinstance(default_val, str):
                default_val = 0

            # Check if this is a fine channel
            is_fine = "Fine" in ch_key or ch_key.endswith(" fine")

            channels.append({
                "channel_number": ch_num,
                "channel_type": channel_type.value,
                "name": ch_key,
                "default_value": min(255, max(0, int(default_val))),
                "is_fine": is_fine,
            })
            ch_num += 1

        modes.append({
            "name": mode_name,
            "channel_count": len(channels),
            "channels": channels,
        })

    return {
        "manufacturer": manufacturer,
        "model": name,
        "fixture_type": fixture_type.value,
        "weight": weight,
        "power": power,
        "beam_angle": beam_angle,
        "has_rgb": has_rgb,
        "has_color_wheel": has_color_wheel,
        "source": "ofl",
        "source_id": f"{manufacturer_key}/{fixture_key}",
        "categories": [c.lower().replace(" ", "_") for c in categories],
        "modes": modes,
    }
