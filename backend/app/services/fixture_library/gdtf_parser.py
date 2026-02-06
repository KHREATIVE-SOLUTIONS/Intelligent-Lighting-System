"""
GDTF File Parser
=================

Parses GDTF (General Device Type Format) fixture files.
GDTF files are ZIP archives containing a description.xml with
fixture definitions conforming to the DIN SPEC 15800 standard.
"""

import io
import logging
import zipfile
from typing import Dict, Any, List, Optional
from xml.etree import ElementTree

from app.models.fixture import FixtureType, ChannelType

logger = logging.getLogger(__name__)

# Map GDTF geometry types to our fixture types
GDTF_GEOMETRY_TYPE_MAP = {
    "Spot": FixtureType.SPOT,
    "Wash": FixtureType.WASH,
    "Beam": FixtureType.BEAM,
    "Strobe": FixtureType.STROBE,
    "Moving Head": FixtureType.MOVING_HEAD,
    "LED Bar": FixtureType.LED_BAR,
    "LED Panel": FixtureType.LED_PAR,
    "Dimmer": FixtureType.DIMMER,
    "Laser": FixtureType.LASER,
    "Effect": FixtureType.EFFECT,
}

# Map GDTF channel function attributes to our ChannelType
GDTF_CHANNEL_FUNCTION_MAP = {
    "Dimmer": ChannelType.DIMMER,
    "Pan": ChannelType.PAN,
    "Tilt": ChannelType.TILT,
    "PanRotate": ChannelType.PAN,
    "TiltRotate": ChannelType.TILT,
    "Gobo1": ChannelType.GOBO,
    "Gobo2": ChannelType.GOBO,
    "GoboWheel": ChannelType.GOBO,
    "GoboSpin": ChannelType.GOBO_ROTATION,
    "Color1": ChannelType.COLOR_WHEEL,
    "Color2": ChannelType.COLOR_WHEEL,
    "ColorWheel": ChannelType.COLOR_WHEEL,
    "ColorAdd_R": ChannelType.RED,
    "ColorAdd_G": ChannelType.GREEN,
    "ColorAdd_B": ChannelType.BLUE,
    "ColorAdd_W": ChannelType.WHITE,
    "ColorAdd_A": ChannelType.AMBER,
    "ColorAdd_UV": ChannelType.UV,
    "ColorSub_C": ChannelType.OTHER,
    "ColorSub_M": ChannelType.OTHER,
    "ColorSub_Y": ChannelType.OTHER,
    "Shutter": ChannelType.SHUTTER,
    "ShutterStrobe": ChannelType.STROBE,
    "Strobe": ChannelType.STROBE,
    "StrobeDuration": ChannelType.STROBE,
    "StrobeFrequency": ChannelType.STROBE,
    "Prism": ChannelType.PRISM,
    "PrismRotation": ChannelType.PRISM,
    "Focus": ChannelType.FOCUS,
    "Zoom": ChannelType.ZOOM,
    "Frost": ChannelType.OTHER,
    "Iris": ChannelType.OTHER,
    "Speed": ChannelType.SPEED,
    "Effects": ChannelType.EFFECT,
    "Macro": ChannelType.MACRO,
    "Maintenance": ChannelType.OTHER,
    "NoFunction": ChannelType.OTHER,
}


def _resolve_channel_type(attribute: str) -> ChannelType:
    """Resolve GDTF attribute name to our ChannelType."""
    # Try direct match
    if attribute in GDTF_CHANNEL_FUNCTION_MAP:
        return GDTF_CHANNEL_FUNCTION_MAP[attribute]

    # Try partial match
    attr_lower = attribute.lower()
    for key, ct in GDTF_CHANNEL_FUNCTION_MAP.items():
        if key.lower() in attr_lower:
            return ct

    # Check for color names
    if "red" in attr_lower:
        return ChannelType.RED
    if "green" in attr_lower:
        return ChannelType.GREEN
    if "blue" in attr_lower:
        return ChannelType.BLUE
    if "white" in attr_lower:
        return ChannelType.WHITE
    if "amber" in attr_lower:
        return ChannelType.AMBER
    if "uv" in attr_lower:
        return ChannelType.UV
    if "dimmer" in attr_lower or "intensity" in attr_lower:
        return ChannelType.DIMMER
    if "pan" in attr_lower:
        return ChannelType.PAN
    if "tilt" in attr_lower:
        return ChannelType.TILT

    return ChannelType.OTHER


def parse_gdtf(file_content: bytes) -> Dict[str, Any]:
    """Parse a GDTF file and return a dict compatible with FixtureCreate schema.

    Args:
        file_content: Raw bytes of the .gdtf file (ZIP format)

    Returns:
        Dict compatible with FixtureCreate schema

    Raises:
        ValueError: If the file is not a valid GDTF archive
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            # Find description.xml
            desc_name = None
            for name in zf.namelist():
                if name.lower() == "description.xml":
                    desc_name = name
                    break

            if not desc_name:
                raise ValueError("No description.xml found in GDTF archive")

            xml_content = zf.read(desc_name)
    except zipfile.BadZipFile:
        raise ValueError("Invalid GDTF file - not a valid ZIP archive")

    # Parse XML
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError as e:
        raise ValueError(f"Invalid GDTF XML: {e}")

    # GDTF namespace
    ns = {"": ""}
    # Try to find the fixture type element
    fixture_type_el = root.find(".//FixtureType") or root

    # Extract basic info
    name = fixture_type_el.get("Name", "Unknown")
    manufacturer = fixture_type_el.get("Manufacturer", "Unknown")
    description = fixture_type_el.get("Description", "")
    fixture_type_id = fixture_type_el.get("FixtureTypeID", "")

    # Determine fixture type
    fixture_type = FixtureType.OTHER
    short_name = fixture_type_el.get("ShortName", "").lower()
    for key, ft in GDTF_GEOMETRY_TYPE_MAP.items():
        if key.lower() in short_name or key.lower() in name.lower():
            fixture_type = ft
            break

    # Extract physical properties
    physical_el = fixture_type_el.find(".//PhysicalDescriptions")
    weight = None
    power = None
    beam_angle = None

    if physical_el is not None:
        props = physical_el.find("Properties")
        if props is not None:
            weight_el = props.find("Weight")
            if weight_el is not None:
                try:
                    weight = float(weight_el.get("Value", "0"))
                except (ValueError, TypeError):
                    pass

            power_el = props.find("PowerConsumption")
            if power_el is not None:
                try:
                    power = float(power_el.get("Value", "0"))
                except (ValueError, TypeError):
                    pass

        # Beam angle from emitter
        emitters = physical_el.findall(".//Emitter")
        for emitter in emitters:
            beam = emitter.find("BeamAngle")
            if beam is not None:
                try:
                    beam_angle = float(beam.get("Value", "0"))
                except (ValueError, TypeError):
                    pass

    # Extract DMX modes
    dmx_modes = fixture_type_el.findall(".//DMXModes/DMXMode")
    modes = []

    has_rgb = False
    has_color_wheel = False

    for dmx_mode in dmx_modes:
        mode_name = dmx_mode.get("Name", "Default")
        channels_els = dmx_mode.findall(".//DMXChannel")

        channels = []
        ch_num = 1

        for ch_el in channels_els:
            # Get channel attributes
            offset = ch_el.get("Offset")
            geometry = ch_el.get("Geometry", "")

            # Get logical channel and channel function
            logical = ch_el.find("LogicalChannel")
            attribute = ""
            if logical is not None:
                attribute = logical.get("Attribute", "")
                # Check for channel function
                ch_func = logical.find("ChannelFunction")
                if ch_func is not None and not attribute:
                    attribute = ch_func.get("Attribute", "")

            channel_type = _resolve_channel_type(attribute)
            channel_name = attribute or geometry or f"Channel {ch_num}"

            # Track color capabilities
            if channel_type in (ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE):
                has_rgb = True
            if channel_type == ChannelType.COLOR_WHEEL:
                has_color_wheel = True

            # Check for fine channels
            is_fine = "fine" in channel_name.lower() or (offset and "," in str(offset))

            channels.append({
                "channel_number": ch_num,
                "channel_type": channel_type.value,
                "name": channel_name,
                "default_value": 0,
                "is_fine": is_fine,
            })
            ch_num += 1

        if channels:
            modes.append({
                "name": mode_name,
                "channel_count": len(channels),
                "channels": channels,
            })

    # If no modes found, create a basic placeholder
    if not modes:
        modes.append({
            "name": "Default",
            "channel_count": 1,
            "channels": [{
                "channel_number": 1,
                "channel_type": "dimmer",
                "name": "Dimmer",
                "default_value": 0,
            }],
        })

    return {
        "manufacturer": manufacturer,
        "model": name,
        "fixture_type": fixture_type.value,
        "gdtf_id": fixture_type_id or None,
        "weight": weight,
        "power": power,
        "beam_angle": beam_angle,
        "has_rgb": has_rgb,
        "has_color_wheel": has_color_wheel,
        "source": "gdtf",
        "modes": modes,
    }
