"""
GDTF File Parser
=================

Parses GDTF (General Device Type Format) fixture files.
GDTF files are ZIP archives containing a description.xml with
fixture definitions conforming to the DIN SPEC 15800 standard.
"""

import io
import logging
import re
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
    "PositionMSpeed": ChannelType.SPEED,
    "Gobo": ChannelType.GOBO,
    "Gobo1": ChannelType.GOBO,
    "Gobo2": ChannelType.GOBO2,
    "GoboWheel": ChannelType.GOBO,
    "GoboSpin": ChannelType.GOBO_ROTATION,
    "Color": ChannelType.COLOR_WHEEL,
    "Color1": ChannelType.COLOR_WHEEL,
    "Color2": ChannelType.COLOR_WHEEL,
    "ColorWheel": ChannelType.COLOR_WHEEL,
    "ColorAdd_R": ChannelType.RED,
    "ColorAdd_G": ChannelType.GREEN,
    "ColorAdd_B": ChannelType.BLUE,
    "ColorAdd_W": ChannelType.WHITE,
    "ColorAdd_WW": ChannelType.WHITE,
    "ColorAdd_CW": ChannelType.WHITE,
    "ColorAdd_A": ChannelType.AMBER,
    "ColorAdd_RY": ChannelType.AMBER,
    "ColorAdd_GY": ChannelType.LIME,
    "ColorAdd_UV": ChannelType.UV,
    "ColorAdd_C": ChannelType.CYAN,
    "ColorAdd_M": ChannelType.MAGENTA,
    "ColorAdd_Y": ChannelType.YELLOW,
    "ColorSub_R": ChannelType.RED,
    "ColorSub_G": ChannelType.GREEN,
    "ColorSub_B": ChannelType.BLUE,
    "ColorSub_C": ChannelType.CYAN,
    "ColorSub_M": ChannelType.MAGENTA,
    "ColorSub_Y": ChannelType.YELLOW,
    "CTO": ChannelType.CTO,
    "CTB": ChannelType.CTB,
    "Shutter": ChannelType.SHUTTER,
    "ShutterStrobe": ChannelType.STROBE,
    "Strobe": ChannelType.STROBE,
    "StrobeDuration": ChannelType.STROBE,
    "StrobeFrequency": ChannelType.STROBE,
    "Prism": ChannelType.PRISM,
    "PrismRotation": ChannelType.PRISM,
    "Focus": ChannelType.FOCUS,
    "Zoom": ChannelType.ZOOM,
    "Frost": ChannelType.FROST,
    "Iris": ChannelType.IRIS,
    "AnimationWheel": ChannelType.ANIMATION,
    "AnimationIndexRotate": ChannelType.ANIMATION,
    "AnimationIndexRotateMode": ChannelType.ANIMATION,
    "Blade": ChannelType.FRAMING,
    "BladeSoft": ChannelType.FRAMING,
    "KeyStone": ChannelType.FRAMING,
    "ShaperRot": ChannelType.FRAMING,
    "ShaperMacros": ChannelType.FRAMING,
    "ShaperMacrosSpeed": ChannelType.FRAMING,
    "Speed": ChannelType.SPEED,
    "Effects": ChannelType.EFFECT,
    "Macro": ChannelType.MACRO,
    "Maintenance": ChannelType.OTHER,
    "NoFunction": ChannelType.OTHER,
    "NoFeature": ChannelType.OTHER,
}

# GDTF numbers repeated features inline ("Gobo2PosRotate", "Frost3PulseOpen")
_INDEXED_ATTRIBUTE_RE = re.compile(r"^(?P<base>[A-Za-z_]+?)(?P<index>\d+)(?P<rest>[A-Za-z_]*)$")

# Checked in order; the first substring to appear in the attribute wins
_ATTRIBUTE_KEYWORDS = (
    ("cto", ChannelType.CTO),
    ("ctb", ChannelType.CTB),
    ("iris", ChannelType.IRIS),
    ("frost", ChannelType.FROST),
    ("animation", ChannelType.ANIMATION),
    ("blade", ChannelType.FRAMING),
    ("shaper", ChannelType.FRAMING),
    ("keystone", ChannelType.FRAMING),
    ("framing", ChannelType.FRAMING),
    ("cyan", ChannelType.CYAN),
    ("magenta", ChannelType.MAGENTA),
    ("yellow", ChannelType.YELLOW),
    ("lime", ChannelType.LIME),
    ("indigo", ChannelType.INDIGO),
    ("red", ChannelType.RED),
    ("green", ChannelType.GREEN),
    ("blue", ChannelType.BLUE),
    ("white", ChannelType.WHITE),
    ("amber", ChannelType.AMBER),
    ("uv", ChannelType.UV),
    ("prism", ChannelType.PRISM),
    ("gobo", ChannelType.GOBO),
    ("strobe", ChannelType.STROBE),
    ("shutter", ChannelType.SHUTTER),
    ("color", ChannelType.COLOR_WHEEL),
    ("zoom", ChannelType.ZOOM),
    ("focus", ChannelType.FOCUS),
    ("dimmer", ChannelType.DIMMER),
    ("intensity", ChannelType.DIMMER),
    ("pan", ChannelType.PAN),
    ("tilt", ChannelType.TILT),
    ("macro", ChannelType.MACRO),
    ("speed", ChannelType.SPEED),
    ("effect", ChannelType.EFFECT),
)

_FINE_SUFFIXES = {1: "Fine", 2: "Ultra", 3: "Extra"}


def _resolve_indexed_attribute(base: str, index: int, rest: str) -> Optional[ChannelType]:
    """Resolve a GDTF attribute that carries a feature index."""
    rotating = "Rotate" in rest or "Spin" in rest

    if base == "Gobo":
        if index >= 2:
            return ChannelType.GOBO2_ROTATION if rotating else ChannelType.GOBO2
        return ChannelType.GOBO_ROTATION if rotating else ChannelType.GOBO
    if base == "Color":
        return ChannelType.COLOR_WHEEL
    if base == "ColorMacro":
        return ChannelType.MACRO
    if base == "Shutter":
        if "Strobe" in rest or "Pulse" in rest or "Random" in rest:
            return ChannelType.STROBE
        return ChannelType.SHUTTER

    return GDTF_CHANNEL_FUNCTION_MAP.get(base + rest) or GDTF_CHANNEL_FUNCTION_MAP.get(base)


def _resolve_channel_type(attribute: str) -> ChannelType:
    """Resolve GDTF attribute name to our ChannelType."""
    attribute = (attribute or "").strip()
    if not attribute:
        return ChannelType.OTHER

    direct = GDTF_CHANNEL_FUNCTION_MAP.get(attribute)
    if direct is not None:
        return direct

    indexed = _INDEXED_ATTRIBUTE_RE.match(attribute)
    if indexed is not None:
        resolved = _resolve_indexed_attribute(
            indexed.group("base"),
            int(indexed.group("index")),
            indexed.group("rest"),
        )
        if resolved is not None:
            return resolved

    attr_lower = attribute.lower()
    for keyword, channel_type in _ATTRIBUTE_KEYWORDS:
        if keyword in attr_lower:
            return channel_type

    return ChannelType.OTHER


def _fine_channel_type(coarse: ChannelType) -> ChannelType:
    """The dedicated fine type for a coarse type, or the coarse type itself."""
    try:
        return ChannelType(f"{coarse.value}_fine")
    except ValueError:
        return coarse


def _strip_namespaces(root: ElementTree.Element) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
        for key in [k for k in element.attrib if k.startswith("{")]:
            element.attrib[key.split("}", 1)[1]] = element.attrib.pop(key)


def _parse_offsets(raw: Optional[str]) -> List[int]:
    """GDTF Offset is a comma separated list of 1-based DMX slots, coarse first."""
    if not raw:
        return []

    slots = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            slot = int(part)
        except ValueError:
            return []
        if slot < 1:
            return []
        slots.append(slot)

    return slots


def _parse_dmx_value(raw: Optional[str]) -> Optional[int]:
    """GDTF DMXValue is "<value>/<byte count>"; reduce it to its coarse byte."""
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    byte_count = 1
    if "/" in text:
        text, _, suffix = text.partition("/")
        digits = "".join(c for c in suffix if c.isdigit())
        if digits:
            byte_count = max(1, int(digits))

    try:
        value = int(text.strip())
    except ValueError:
        return None

    if byte_count > 1:
        value >>= 8 * (byte_count - 1)
    return max(0, min(255, value))


def _channel_functions(ch_el: ElementTree.Element) -> List[ElementTree.Element]:
    functions = []
    for logical in ch_el.findall("LogicalChannel"):
        functions.extend(logical.findall("ChannelFunction"))
    return functions


def _function_attribute(func: ElementTree.Element, fallback: str) -> str:
    return func.get("Attribute") or fallback


def _extract_value_ranges(ch_el: ElementTree.Element) -> Optional[List[Dict[str, Any]]]:
    """Turn ChannelSet entries into named DMX ranges on the coarse byte."""
    functions = []
    for func in _channel_functions(ch_el):
        start = _parse_dmx_value(func.get("DMXFrom"))
        functions.append((0 if start is None else start, func))
    functions.sort(key=lambda item: item[0])

    ranges: List[Dict[str, Any]] = []
    for index, (func_start, func) in enumerate(functions):
        func_end = functions[index + 1][0] - 1 if index + 1 < len(functions) else 255
        if func_end < func_start:
            func_end = func_start

        sets = []
        for ch_set in func.findall("ChannelSet"):
            start = _parse_dmx_value(ch_set.get("DMXFrom"))
            sets.append((func_start if start is None else start, ch_set))
        sets.sort(key=lambda item: item[0])

        for set_index, (start, ch_set) in enumerate(sets):
            end = sets[set_index + 1][0] - 1 if set_index + 1 < len(sets) else func_end
            name = (ch_set.get("Name") or "").strip()
            if not name:
                continue
            ranges.append({
                "name": name,
                "min_value": start,
                "max_value": max(start, end),
            })

    return ranges or None


def _claim_slot(slots: Dict[int, Dict[str, Any]], mode_name: str, slot: int, row: Dict[str, Any]) -> None:
    if slot in slots:
        logger.warning(
            "GDTF mode '%s' declares DMX slot %d twice ('%s' and '%s'); keeping the first",
            mode_name, slot, slots[slot]["name"], row["name"],
        )
        return
    slots[slot] = row


def _physical_span(ch_el: ElementTree.Element, attribute: str, wanted: ChannelType) -> Optional[float]:
    """Widest physical travel declared by this channel's functions, in degrees."""
    span = None
    for func in _channel_functions(ch_el):
        if _resolve_channel_type(_function_attribute(func, attribute)) is not wanted:
            continue
        raw_from = func.get("PhysicalFrom")
        raw_to = func.get("PhysicalTo")
        if raw_from is None or raw_to is None:
            continue
        try:
            candidate = abs(float(raw_to) - float(raw_from))
        except (TypeError, ValueError):
            continue
        if candidate > 0 and (span is None or candidate > span):
            span = candidate
    return span


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
                if name.lower().rsplit("/", 1)[-1] == "description.xml":
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

    _strip_namespaces(root)

    fixture_type_el = root.find(".//FixtureType")
    if fixture_type_el is None:
        if root.tag != "FixtureType":
            raise ValueError("No FixtureType element found in GDTF description")
        fixture_type_el = root

    # Extract basic info
    name = fixture_type_el.get("Name", "Unknown")
    manufacturer = fixture_type_el.get("Manufacturer", "Unknown")
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
    has_cmy = False
    has_color_wheel = False
    pan_range = None
    tilt_range = None

    for dmx_mode in dmx_modes:
        mode_name = dmx_mode.get("Name", "Default")
        channels_els = dmx_mode.findall(".//DMXChannel")

        slots: Dict[int, Dict[str, Any]] = {}

        for ch_el in channels_els:
            offsets = _parse_offsets(ch_el.get("Offset"))
            if not offsets:
                continue

            geometry = ch_el.get("Geometry", "")

            attribute = ""
            for logical in ch_el.findall("LogicalChannel"):
                attribute = logical.get("Attribute", "")
                if not attribute:
                    for ch_func in logical.findall("ChannelFunction"):
                        attribute = ch_func.get("Attribute", "")
                        if attribute:
                            break
                if attribute:
                    break

            channel_type = _resolve_channel_type(attribute)
            channel_name = attribute or geometry or f"Channel {offsets[0]}"

            # Track color capabilities
            if channel_type in (ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE):
                has_rgb = True
            if channel_type in (ChannelType.CYAN, ChannelType.MAGENTA, ChannelType.YELLOW):
                has_cmy = True
            if channel_type == ChannelType.COLOR_WHEEL:
                has_color_wheel = True

            if channel_type == ChannelType.PAN:
                span = _physical_span(ch_el, attribute, ChannelType.PAN)
                if span is not None and (pan_range is None or span > pan_range):
                    pan_range = span
            elif channel_type == ChannelType.TILT:
                span = _physical_span(ch_el, attribute, ChannelType.TILT)
                if span is not None and (tilt_range is None or span > tilt_range):
                    tilt_range = span

            coarse_number = offsets[0]
            _claim_slot(slots, mode_name, coarse_number, {
                "channel_number": coarse_number,
                "channel_type": channel_type.value,
                "name": channel_name,
                "default_value": 0,
                "is_fine": False,
                "coarse_channel": None,
                "value_ranges": _extract_value_ranges(ch_el),
            })

            fine_type = _fine_channel_type(channel_type)
            for depth, slot in enumerate(offsets[1:], start=1):
                _claim_slot(slots, mode_name, slot, {
                    "channel_number": slot,
                    "channel_type": fine_type.value,
                    "name": f"{channel_name} {_FINE_SUFFIXES.get(depth, f'Fine {depth}')}",
                    "default_value": 0,
                    "is_fine": True,
                    "coarse_channel": coarse_number,
                    "value_ranges": None,
                })

        if slots:
            modes.append({
                "name": mode_name,
                "channel_count": max(slots),
                "channels": [slots[slot] for slot in sorted(slots)],
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
        "pan_range": pan_range,
        "tilt_range": tilt_range,
        "has_rgb": has_rgb,
        "has_cmy": has_cmy,
        "has_color_wheel": has_color_wheel,
        "source": "gdtf",
        "modes": modes,
    }
