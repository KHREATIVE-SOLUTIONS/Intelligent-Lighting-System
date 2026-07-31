"""
Open Fixture Library Client
============================

Integration with the Open Fixture Library (OFL) API for searching and
importing community-maintained fixture definitions.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import quote

import httpx

from app.models.fixture import FixtureType, ChannelType

logger = logging.getLogger(__name__)

OFL_SITE_BASE = "https://open-fixture-library.org"
OFL_API_BASE = f"{OFL_SITE_BASE}/api/v1"

# The backend also runs a 60fps effects engine and a 40fps DMX transmitter, so
# library traffic gets a short per-operation ceiling on top of the socket timeouts.
OFL_TIMEOUT = 5.0
OFL_DEADLINE = 8.0
OFL_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

_FIXTURE_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

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
    "Matrix": FixtureType.LED_BAR,
    "Scanner": FixtureType.SPOT,
    "Barrel Scanner": FixtureType.SPOT,
    "Stand": FixtureType.OTHER,
    "Pixel Bar": FixtureType.LED_BAR,
    "Blinder": FixtureType.STROBE,
    "Strobe": FixtureType.STROBE,
    "Smoke": FixtureType.OTHER,
    "Other": FixtureType.OTHER,
}

# Map OFL capability types to our ChannelType enum. Capability type is the only
# type information a modern OFL definition carries; channels have no `type` key.
OFL_CAPABILITY_TYPE_MAP = {
    "Intensity": ChannelType.DIMMER,
    "ColorPreset": ChannelType.COLOR_WHEEL,
    "Pan": ChannelType.PAN,
    "Tilt": ChannelType.TILT,
    "PanContinuous": ChannelType.SPEED,
    "TiltContinuous": ChannelType.SPEED,
    "PanTiltSpeed": ChannelType.SPEED,
    "StrobeSpeed": ChannelType.STROBE,
    "StrobeDuration": ChannelType.STROBE,
    "Focus": ChannelType.FOCUS,
    "Zoom": ChannelType.ZOOM,
    "BeamAngle": ChannelType.ZOOM,
    "Iris": ChannelType.IRIS,
    "IrisEffect": ChannelType.IRIS,
    "Frost": ChannelType.FROST,
    "FrostEffect": ChannelType.FROST,
    "Prism": ChannelType.PRISM,
    "PrismRotation": ChannelType.PRISM,
    "BladeInsertion": ChannelType.FRAMING,
    "BladeRotation": ChannelType.FRAMING,
    "BladeSystemRotation": ChannelType.FRAMING,
    "Effect": ChannelType.EFFECT,
    "EffectParameter": ChannelType.EFFECT,
    "EffectSpeed": ChannelType.SPEED,
    "EffectDuration": ChannelType.SPEED,
    "Fog": ChannelType.EFFECT,
    "FogOutput": ChannelType.EFFECT,
    "FogType": ChannelType.EFFECT,
    "Rotation": ChannelType.SPEED,
    "Speed": ChannelType.SPEED,
    "Time": ChannelType.SPEED,
    "SoundSensitivity": ChannelType.OTHER,
    "BeamPosition": ChannelType.OTHER,
    "Maintenance": ChannelType.OTHER,
    "Generic": ChannelType.OTHER,
    "NoFunction": ChannelType.OTHER,
}

OFL_COLOR_MAP = {
    "Red": ChannelType.RED,
    "Green": ChannelType.GREEN,
    "Blue": ChannelType.BLUE,
    "Cyan": ChannelType.CYAN,
    "Magenta": ChannelType.MAGENTA,
    "Yellow": ChannelType.YELLOW,
    "White": ChannelType.WHITE,
    "Warm White": ChannelType.WHITE,
    "Cold White": ChannelType.WHITE,
    "Cool White": ChannelType.WHITE,
    "Amber": ChannelType.AMBER,
    "UV": ChannelType.UV,
    "Lime": ChannelType.LIME,
    "Indigo": ChannelType.INDIGO,
}

# Slot types that identify what a wheel is for. Open/Closed appear on every
# wheel and say nothing, so they are deliberately absent.
OFL_WHEEL_SLOT_KINDS = {
    "Color": "color",
    "Gobo": "gobo",
    "Prism": "prism",
    "Iris": "iris",
    "Frost": "frost",
    "AnimationGoboStart": "animation",
    "AnimationGoboEnd": "animation",
}

WHEEL_KIND_CHANNEL_TYPES = {
    "color": (ChannelType.COLOR_WHEEL, ChannelType.COLOR_WHEEL),
    "gobo": (ChannelType.GOBO, ChannelType.GOBO_ROTATION),
    "gobo2": (ChannelType.GOBO2, ChannelType.GOBO2_ROTATION),
    "animation": (ChannelType.ANIMATION, ChannelType.ANIMATION),
    "prism": (ChannelType.PRISM, ChannelType.PRISM),
    "iris": (ChannelType.IRIS, ChannelType.IRIS),
    "frost": (ChannelType.FROST, ChannelType.FROST),
}

FINE_CHANNEL_TYPES = {
    ChannelType.PAN: ChannelType.PAN_FINE,
    ChannelType.TILT: ChannelType.TILT_FINE,
}

# Catch-all types, outranked by any type naming a physical mechanism when a
# channel mixes the two — a prism channel carrying prism macros is still a prism.
GENERIC_CHANNEL_TYPES = frozenset({
    ChannelType.EFFECT,
    ChannelType.SPEED,
    ChannelType.MACRO,
    ChannelType.OTHER,
})

_PIXEL_KEY_TOKEN = "$pixelKey"
_FINE_SUFFIX = " fine"
_MAX_SWITCH_DEPTH = 4


class OFLUnavailableError(RuntimeError):
    """The Open Fixture Library could not be reached or answered unusably.

    Distinct from an empty result: callers must be able to tell "no matches"
    apart from "the library is down".
    """


class OFLClient:
    """Client for the Open Fixture Library API."""

    def __init__(self, timeout: float = OFL_TIMEOUT, deadline: float = OFL_DEADLINE):
        self._deadline = deadline
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            headers={"Accept": "application/json"},
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            follow_redirects=True,
        )

    async def close(self):
        await self._client.aclose()

    async def search_fixtures(
        self, query: str, manufacturer: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search OFL for fixtures matching query.

        Raises OFLUnavailableError if the library cannot be reached.
        """
        payload = await self._request(
            "POST",
            f"{OFL_API_BASE}/get-search-results",
            json_body={
                "searchQuery": query or "",
                "manufacturersQuery": [manufacturer] if manufacturer else [],
                "categoriesQuery": [],
            },
        )

        if not isinstance(payload, list):
            raise OFLUnavailableError("OFL search returned an unexpected payload")

        results = []
        for entry in payload:
            if not isinstance(entry, str) or "/" not in entry:
                continue
            manufacturer_key, _, fixture_key = entry.partition("/")
            results.append({
                "key": entry,
                "manufacturer_key": manufacturer_key,
                "fixture_key": fixture_key,
                "manufacturer": _humanise_key(manufacturer_key),
                "name": _humanise_key(fixture_key),
            })
        return results

    async def get_fixture(
        self, manufacturer_key: str, fixture_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get full fixture definition from OFL, or None if it does not exist.

        Raises OFLUnavailableError if the library cannot be reached.
        """
        url = f"{OFL_SITE_BASE}/{_safe_key(manufacturer_key)}/{_safe_key(fixture_key)}.json"
        payload = await self._request("GET", url, missing_is_none=True)
        if not isinstance(payload, dict) or not payload:
            return None
        return payload

    async def list_manufacturers(self) -> List[Dict[str, Any]]:
        """List all manufacturers from OFL.

        Raises OFLUnavailableError if the library cannot be reached.
        """
        payload = await self._request("GET", f"{OFL_API_BASE}/manufacturers")
        if not isinstance(payload, dict):
            raise OFLUnavailableError("OFL manufacturers returned an unexpected payload")

        manufacturers = []
        for key, entry in payload.items():
            entry = entry if isinstance(entry, dict) else {}
            manufacturers.append({
                "key": key,
                "name": entry.get("name") or _humanise_key(key),
                "fixture_count": entry.get("fixtureCount", 0),
                "color": entry.get("color"),
            })
        manufacturers.sort(key=lambda item: str(item["name"]).lower())
        return manufacturers

    async def _request(
        self,
        method: str,
        url: str,
        json_body: Optional[Dict[str, Any]] = None,
        missing_is_none: bool = False,
    ) -> Any:
        try:
            response = await asyncio.wait_for(
                self._client.request(method, url, json=json_body),
                timeout=self._deadline,
            )
        except asyncio.TimeoutError as e:
            logger.error(f"OFL request {method} {url} exceeded {self._deadline}s")
            raise OFLUnavailableError(f"OFL request timed out after {self._deadline}s") from e
        except httpx.HTTPError as e:
            logger.error(f"OFL request {method} {url} failed: {e}")
            raise OFLUnavailableError(f"OFL request failed: {e}") from e

        if missing_is_none and response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.error(f"OFL request {method} {url} returned HTTP {response.status_code}")
            raise OFLUnavailableError(f"OFL returned HTTP {response.status_code}")
        if len(response.content) > OFL_MAX_RESPONSE_BYTES:
            raise OFLUnavailableError("OFL response exceeded the size limit")

        try:
            return response.json()
        except ValueError as e:
            logger.error(f"OFL request {method} {url} returned a non-JSON body")
            raise OFLUnavailableError("OFL returned a non-JSON body") from e


def _safe_key(key: str) -> str:
    """URL path segment for an OFL manufacturer/fixture key."""
    text = str(key or "").strip()
    if not _FIXTURE_KEY_PATTERN.fullmatch(text):
        raise ValueError(f"Invalid OFL key: {key!r}")
    return quote(text, safe="")


def _humanise_key(key: str) -> str:
    return str(key or "").replace("-", " ").title()


def _humanise_type(text: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(text or ""))


def _natural_key(text: str) -> List[Any]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(text))
    ]


class _Wheels(NamedTuple):
    """Wheel definitions plus, per wheel name, its kind and ordinal of that kind."""

    definitions: Dict[str, Any]
    kinds: Dict[str, Tuple[str, int]]


def _capabilities(channel: Dict[str, Any]) -> List[Dict[str, Any]]:
    capabilities = channel.get("capabilities")
    if isinstance(capabilities, list):
        return [c for c in capabilities if isinstance(c, dict)]
    capability = channel.get("capability")
    return [capability] if isinstance(capability, dict) else []


def _resolution(channel: Dict[str, Any]) -> int:
    """Byte width the channel's DMX values are expressed in."""
    declared = re.fullmatch(r"(\d+)bit", str(channel.get("dmxValueResolution") or ""))
    if declared:
        return max(1, int(declared.group(1)) // 8)
    return 1 + len(channel.get("fineChannelAliases") or [])


def _raw_default_value(channel: Dict[str, Any]) -> int:
    raw = channel.get("defaultValue")
    maximum = 256 ** _resolution(channel) - 1

    if isinstance(raw, str):
        text = raw.strip()
        try:
            value = (
                float(text[:-1]) / 100.0 * maximum
                if text.endswith("%")
                else float(text)
            )
        except ValueError:
            return 0
        return max(0, min(maximum, int(value)))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(0, min(maximum, int(raw)))
    return 0


def _default_byte(channel: Dict[str, Any], byte_index: int) -> int:
    """The byte_index-th byte of the channel default, 0 being the coarse byte."""
    resolution = _resolution(channel)
    if byte_index >= resolution:
        return 0
    return (_raw_default_value(channel) >> (8 * (resolution - 1 - byte_index))) & 0xFF


def _to_coarse(value: Any, resolution: int) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, raw >> (8 * (resolution - 1))))


def _angle_degrees(text: Any) -> Optional[float]:
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*deg\s*", str(text))
    return float(match.group(1)) if match else None


def _kelvin(text: Any) -> Optional[float]:
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*K\s*", str(text))
    return float(match.group(1)) if match else None


def _substitute_pixel_key(node: Any, pixel_key: str) -> Any:
    if isinstance(node, str):
        return node.replace(_PIXEL_KEY_TOKEN, pixel_key)
    if isinstance(node, list):
        return [_substitute_pixel_key(item, pixel_key) for item in node]
    if isinstance(node, dict):
        return {
            _substitute_pixel_key(key, pixel_key): _substitute_pixel_key(value, pixel_key)
            for key, value in node.items()
        }
    return node


def _default_pixel_key(x: int, y: int, z: int, counts: Sequence[int]) -> str:
    axes = sum(1 for count in counts if count > 1)
    if axes <= 1:
        return str(max(x, y, z))
    if axes == 2:
        if counts[0] == 1:
            return f"({y}, {z})"
        if counts[1] == 1:
            return f"({x}, {z})"
        return f"({x}, {y})"
    return f"({x}, {y}, {z})"


def _matrix_pixels(matrix: Dict[str, Any]) -> List[Tuple[str, int, int, int]]:
    """Every pixel as (key, x, y, z) with 1-based coordinates."""
    pixels: List[Tuple[str, int, int, int]] = []

    pixel_keys = matrix.get("pixelKeys")
    if isinstance(pixel_keys, list):
        for z, layer in enumerate(pixel_keys, start=1):
            for y, row in enumerate(layer or [], start=1):
                for x, key in enumerate(row or [], start=1):
                    if key is not None:
                        pixels.append((str(key), x, y, z))
        return pixels

    counts = matrix.get("pixelCount")
    if isinstance(counts, list) and len(counts) == 3:
        try:
            extents = tuple(max(1, int(count)) for count in counts)
        except (TypeError, ValueError):
            return pixels
        for z in range(1, extents[2] + 1):
            for y in range(1, extents[1] + 1):
                for x in range(1, extents[0] + 1):
                    pixels.append((_default_pixel_key(x, y, z, extents), x, y, z))
    return pixels


def _pixel_keys_for(matrix: Dict[str, Any], repeat_for: Any) -> List[str]:
    if isinstance(repeat_for, list):
        return [str(key) for key in repeat_for]

    groups = matrix.get("pixelGroups") or {}
    if repeat_for == "eachPixelGroup":
        return [str(key) for key in groups]

    pixels = _matrix_pixels(matrix)
    if repeat_for == "eachPixelABC":
        return sorted((pixel[0] for pixel in pixels), key=_natural_key)

    order = str(repeat_for or "")[len("eachPixel"):].upper()
    if len(order) == 3 and set(order) == {"X", "Y", "Z"}:
        axis = {"X": 1, "Y": 2, "Z": 3}
        # The first-named axis varies fastest.
        pixels = sorted(
            pixels,
            key=lambda p: (p[axis[order[2]]], p[axis[order[1]]], p[axis[order[0]]]),
        )
    return [pixel[0] for pixel in pixels]


def _resolvable_channels(ofl_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Every channel a mode can name, with matrix templates expanded per pixel."""
    channels = {
        key: value
        for key, value in (ofl_data.get("availableChannels") or {}).items()
        if isinstance(value, dict)
    }

    templates = ofl_data.get("templateChannels") or {}
    if not templates:
        return channels

    matrix = ofl_data.get("matrix") or {}
    pixel_keys = [pixel[0] for pixel in _matrix_pixels(matrix)]
    pixel_keys += [str(key) for key in (matrix.get("pixelGroups") or {})]

    for template_key, template in templates.items():
        if not isinstance(template, dict):
            continue
        for pixel_key in pixel_keys:
            key = template_key.replace(_PIXEL_KEY_TOKEN, pixel_key)
            channels.setdefault(key, _substitute_pixel_key(template, pixel_key))
    return channels


def _fine_alias_map(
    channels: Dict[str, Dict[str, Any]]
) -> Dict[str, Tuple[str, int]]:
    """Fine channel alias -> (coarse channel key, byte index)."""
    aliases: Dict[str, Tuple[str, int]] = {}
    for key, channel in channels.items():
        for index, alias in enumerate(channel.get("fineChannelAliases") or [], start=1):
            if isinstance(alias, str):
                aliases.setdefault(alias, (key, index))
    return aliases


def _switching_channel_map(channels: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """Switching channel key -> the channel it becomes at its trigger's default."""
    resolved: Dict[str, str] = {}
    preferred: Dict[str, str] = {}

    for channel in channels.values():
        capabilities = _capabilities(channel)
        default = _raw_default_value(channel)
        for capability in capabilities:
            targets = capability.get("switchChannels")
            if not isinstance(targets, dict):
                continue
            dmx_range = capability.get("dmxRange")
            covers_default = (
                not isinstance(dmx_range, list)
                or len(dmx_range) != 2
                or _in_range(default, dmx_range)
            )
            for switch_key, target_key in targets.items():
                if not isinstance(switch_key, str) or not isinstance(target_key, str):
                    continue
                resolved.setdefault(switch_key, target_key)
                if covers_default:
                    preferred.setdefault(switch_key, target_key)

    resolved.update(preferred)
    return resolved


def _in_range(value: int, dmx_range: Sequence[Any]) -> bool:
    try:
        return int(dmx_range[0]) <= value <= int(dmx_range[1])
    except (TypeError, ValueError):
        return False


def _mode_channel_keys(
    ofl_mode: Dict[str, Any], matrix: Dict[str, Any]
) -> List[Optional[str]]:
    """The mode's DMX footprint, one entry per slot, matrix inserts expanded."""
    keys: List[Optional[str]] = []

    for entry in ofl_mode.get("channels") or []:
        if entry is None or isinstance(entry, str):
            keys.append(entry)
            continue
        if not isinstance(entry, dict) or entry.get("insert") != "matrixChannels":
            keys.append(None)
            continue

        pixel_keys = _pixel_keys_for(matrix, entry.get("repeatFor"))
        templates = [str(t) for t in entry.get("templateChannels") or []]
        if entry.get("channelOrder") == "perChannel":
            pairs = [(t, p) for t in templates for p in pixel_keys]
        else:
            pairs = [(t, p) for p in pixel_keys for t in templates]
        keys.extend(template.replace(_PIXEL_KEY_TOKEN, pixel) for template, pixel in pairs)

    return keys


def _wheel_kind_from_name(name: str) -> str:
    lowered = str(name).lower()
    for token, kind in (
        ("animation", "animation"),
        ("gobo", "gobo"),
        ("colour", "color"),
        ("color", "color"),
        ("prism", "prism"),
        ("iris", "iris"),
        ("frost", "frost"),
    ):
        if token in lowered:
            return kind
    return ""


def _wheel_kind(name: str, wheel: Dict[str, Any]) -> str:
    counts: Dict[str, int] = {}
    for slot in (wheel or {}).get("slots") or []:
        kind = OFL_WHEEL_SLOT_KINDS.get(str((slot or {}).get("type") or ""))
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    return _wheel_kind_from_name(name)


def _build_wheels(ofl_data: Dict[str, Any]) -> _Wheels:
    definitions = {
        str(name): wheel
        for name, wheel in (ofl_data.get("wheels") or {}).items()
        if isinstance(wheel, dict)
    }
    kinds: Dict[str, Tuple[str, int]] = {}
    ordinals: Dict[str, int] = {}
    for name, wheel in definitions.items():
        kind = _wheel_kind(name, wheel)
        ordinals[kind] = ordinals.get(kind, 0) + 1
        kinds[name] = (kind, ordinals[kind])
    return _Wheels(definitions=definitions, kinds=kinds)


def _wheel_channel_type(kind: str, ordinal: int, rotating: bool) -> ChannelType:
    if kind == "gobo" and ordinal >= 2:
        kind = "gobo2"
    slot_type, rotation_type = WHEEL_KIND_CHANNEL_TYPES.get(
        kind, (ChannelType.OTHER, ChannelType.OTHER)
    )
    return rotation_type if rotating else slot_type


def _color_temperature_type(capability: Dict[str, Any], channel_key: str) -> ChannelType:
    start = _kelvin(capability.get("colorTemperatureStart"))
    end = _kelvin(capability.get("colorTemperatureEnd"))
    if start is not None and end is not None and start != end:
        return ChannelType.CTB if end > start else ChannelType.CTO
    return ChannelType.CTB if "ctb" in str(channel_key).lower() else ChannelType.CTO


def _capability_channel_type(
    capability: Dict[str, Any], channel_key: str, wheels: _Wheels
) -> ChannelType:
    capability_type = str(capability.get("type") or "")

    if capability_type == "ColorIntensity":
        return OFL_COLOR_MAP.get(str(capability.get("color") or ""), ChannelType.OTHER)
    if capability_type == "ColorTemperature":
        return _color_temperature_type(capability, channel_key)
    if capability_type.startswith("Wheel"):
        wheel_name = str(capability.get("wheel") or channel_key)
        kind, ordinal = wheels.kinds.get(
            wheel_name, (_wheel_kind_from_name(wheel_name), 1)
        )
        rotating = capability_type in ("WheelRotation", "WheelSlotRotation")
        return _wheel_channel_type(kind, ordinal, rotating)

    return OFL_CAPABILITY_TYPE_MAP.get(capability_type, ChannelType.OTHER)


def _capability_span(capability: Dict[str, Any], resolution: int) -> int:
    dmx_range = capability.get("dmxRange")
    if isinstance(dmx_range, list) and len(dmx_range) == 2:
        try:
            return max(1, int(dmx_range[1]) - int(dmx_range[0]) + 1)
        except (TypeError, ValueError):
            return 1
    return 256 ** resolution


def _resolve_channel_type(
    channel: Dict[str, Any], channel_key: str, wheels: _Wheels
) -> ChannelType:
    """The one ChannelType that best describes an OFL channel definition."""
    capabilities = _capabilities(channel)

    shutter = [c for c in capabilities if c.get("type") == "ShutterStrobe"]
    if shutter:
        # A channel that can open the shutter must be driven as a shutter, or the
        # fixture never emits light.
        opens = any(c.get("shutterEffect") == "Open" for c in shutter)
        return ChannelType.SHUTTER if opens else ChannelType.STROBE

    resolution = _resolution(channel)
    spans: Dict[ChannelType, int] = {}
    first_seen: Dict[ChannelType, int] = {}
    for index, capability in enumerate(capabilities):
        channel_type = _capability_channel_type(capability, channel_key, wheels)
        spans[channel_type] = spans.get(channel_type, 0) + _capability_span(
            capability, resolution
        )
        first_seen.setdefault(channel_type, index)

    candidates = [t for t in spans if t is not ChannelType.OTHER]
    if not candidates:
        return ChannelType.OTHER
    return max(
        candidates,
        key=lambda t: (t not in GENERIC_CHANNEL_TYPES, spans[t], -first_seen[t]),
    )


def _slot_label(wheel: Dict[str, Any], slot_number: float) -> str:
    slots = (wheel or {}).get("slots") or []
    index = int(slot_number) - 1
    if index < 0 or index >= len(slots):
        return f"Slot {slot_number:g}"

    slot = slots[index] or {}
    name = slot.get("name")
    if name:
        return str(name)

    slot_type = str(slot.get("type") or "Slot")
    same_type = [s for s in slots if str((s or {}).get("type") or "Slot") == slot_type]
    if len(same_type) < 2:
        return slot_type
    ordinal = sum(
        1 for s in slots[: index + 1] if str((s or {}).get("type") or "Slot") == slot_type
    )
    return f"{slot_type} {ordinal}"


def _wheel_slot_label(wheel: Dict[str, Any], capability: Dict[str, Any]) -> str:
    start = capability.get("slotNumber", capability.get("slotNumberStart"))
    end = capability.get("slotNumber", capability.get("slotNumberEnd"))
    if start is None or end is None:
        return ""
    try:
        first = _slot_label(wheel, float(start))
        last = _slot_label(wheel, float(end))
    except (TypeError, ValueError):
        return ""
    return first if first == last else f"{first} - {last}"


def _capability_label(
    capability: Dict[str, Any], channel_key: str, wheels: _Wheels
) -> str:
    capability_type = str(capability.get("type") or "")

    if capability_type.startswith("Wheel"):
        wheel = wheels.definitions.get(str(capability.get("wheel") or channel_key), {})
        label = _wheel_slot_label(wheel, capability)
        if label:
            suffix = {
                "WheelShake": " shake",
                "WheelRotation": " rotation",
                "WheelSlotRotation": " rotation",
            }.get(capability_type, "")
            return f"{label}{suffix}"

    for key in ("effectName", "effectPreset", "shutterEffect", "comment"):
        value = capability.get(key)
        if value:
            return str(value)

    return _humanise_type(capability_type) or "Range"


def _value_ranges(
    channel: Dict[str, Any], channel_key: str, wheels: _Wheels
) -> Optional[List[Dict[str, Any]]]:
    """Named DMX ranges so gobo and colour slots are addressable by meaning."""
    resolution = _resolution(channel)
    ranges = []
    for capability in _capabilities(channel):
        dmx_range = capability.get("dmxRange")
        if not (isinstance(dmx_range, list) and len(dmx_range) == 2):
            continue
        ranges.append({
            "name": _capability_label(capability, channel_key, wheels)[:100],
            "min": _to_coarse(dmx_range[0], resolution),
            "max": _to_coarse(dmx_range[1], resolution),
        })
    return ranges or None


def _axis_travel(
    channels: Dict[str, Dict[str, Any]], capability_type: str
) -> Optional[float]:
    for channel in channels.values():
        for capability in _capabilities(channel):
            if capability.get("type") != capability_type:
                continue
            start = _angle_degrees(capability.get("angleStart"))
            end = _angle_degrees(capability.get("angleEnd"))
            if start is not None and end is not None:
                travel = abs(end - start)
                if travel > 0:
                    return travel
    return None


def _resolve_slot(
    key: str,
    channels: Dict[str, Dict[str, Any]],
    fine_aliases: Dict[str, Tuple[str, int]],
    switching: Dict[str, str],
) -> Tuple[Optional[str], int]:
    """(channel definition key, byte index) for one key out of a mode's list.

    A mode may name a channel directly, a fine alias of one, or a switching
    channel that stands for whichever channel its trigger selects, and a
    switching channel has a fine variant of its own.
    """
    target = key
    for _ in range(_MAX_SWITCH_DEPTH):
        if target in channels:
            return target, 0
        alias = fine_aliases.get(target)
        if alias is not None:
            return alias
        switched = switching.get(target)
        if switched is None:
            break
        target = switched

    if key.endswith(_FINE_SUFFIX):
        coarse, _ = _resolve_slot(
            key[: -len(_FINE_SUFFIX)], channels, fine_aliases, switching
        )
        if coarse is not None:
            return coarse, 1

    return None, 0


def _coarse_key(
    key: str, fine_aliases: Dict[str, Tuple[str, int]], slot_of: Dict[str, int]
) -> Optional[str]:
    """The mode key carrying the coarse byte of `key`, if the mode patches one."""
    alias = fine_aliases.get(key)
    if alias is not None:
        return alias[0] if alias[0] in slot_of else None
    if key.endswith(_FINE_SUFFIX):
        base = key[: -len(_FINE_SUFFIX)]
        if base in slot_of:
            return base
    return None


def _build_mode(
    ofl_mode: Dict[str, Any],
    channels: Dict[str, Dict[str, Any]],
    matrix: Dict[str, Any],
    fine_aliases: Dict[str, Tuple[str, int]],
    switching: Dict[str, str],
    wheels: _Wheels,
    type_cache: Dict[str, ChannelType],
    emitted: set,
) -> Dict[str, Any]:
    keys = _mode_channel_keys(ofl_mode, matrix)

    slot_of: Dict[str, int] = {}
    for number, key in enumerate(keys, start=1):
        if isinstance(key, str):
            slot_of.setdefault(key, number)

    built = []
    for number, key in enumerate(keys, start=1):
        if key is None:
            built.append({
                "channel_number": number,
                "channel_type": ChannelType.OTHER.value,
                "name": f"Unused {number}",
                "default_value": 0,
                "is_fine": False,
                "coarse_channel": None,
                "value_ranges": None,
            })
            continue

        definition_key, byte_index = _resolve_slot(
            key, channels, fine_aliases, switching
        )
        coarse_key = _coarse_key(key, fine_aliases, slot_of) if byte_index else None

        definition = channels.get(definition_key) if definition_key else None
        if definition is None:
            built.append({
                "channel_number": number,
                "channel_type": ChannelType.OTHER.value,
                "name": key[:100],
                "default_value": 0,
                "is_fine": coarse_key is not None,
                "coarse_channel": slot_of.get(coarse_key) if coarse_key else None,
                "value_ranges": None,
            })
            continue

        if definition_key not in type_cache:
            type_cache[definition_key] = _resolve_channel_type(
                definition, definition_key, wheels
            )
        channel_type = type_cache[definition_key]

        is_fine = coarse_key is not None
        if is_fine:
            channel_type = FINE_CHANNEL_TYPES.get(channel_type, channel_type)

        emitted.add(channel_type)
        built.append({
            "channel_number": number,
            "channel_type": channel_type.value,
            "name": key[:100],
            "default_value": _default_byte(definition, byte_index),
            "is_fine": is_fine,
            "coarse_channel": slot_of.get(coarse_key) if coarse_key else None,
            "value_ranges": None if is_fine else _value_ranges(definition, definition_key, wheels),
        })

    return {
        "name": str(ofl_mode.get("name", "Default"))[:100],
        "channel_count": len(built),
        "channels": built,
    }


def convert_ofl_to_internal(
    ofl_data: Dict[str, Any],
    manufacturer_key: str,
    fixture_key: str,
    manufacturer_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert an OFL fixture definition to our FixtureCreate schema dict.

    Returns a dict compatible with FixtureCreate.
    """
    name = ofl_data.get("name", fixture_key)
    manufacturer = manufacturer_name or _humanise_key(manufacturer_key)

    categories = [c for c in (ofl_data.get("categories") or []) if isinstance(c, str)]
    fixture_type = FixtureType.OTHER
    for category in categories:
        if category in OFL_CATEGORY_MAP:
            fixture_type = OFL_CATEGORY_MAP[category]
            break

    physical = ofl_data.get("physical") or {}
    lens = physical.get("lens") or {}
    beam_angle = None
    degrees = lens.get("degreesMinMax")
    if isinstance(degrees, list) and degrees:
        beam_angle = degrees[0]

    channels = _resolvable_channels(ofl_data)
    matrix = ofl_data.get("matrix") or {}
    wheels = _build_wheels(ofl_data)
    fine_aliases = _fine_alias_map(channels)
    switching = _switching_channel_map(channels)
    type_cache: Dict[str, ChannelType] = {}
    emitted: set = set()

    modes = [
        _build_mode(
            ofl_mode, channels, matrix, fine_aliases, switching, wheels, type_cache, emitted
        )
        for ofl_mode in (ofl_data.get("modes") or [])
        if isinstance(ofl_mode, dict)
    ]

    result = {
        "manufacturer": manufacturer,
        "model": name,
        "fixture_type": fixture_type.value,
        "weight": physical.get("weight"),
        "power": physical.get("power"),
        "beam_angle": beam_angle,
        "has_rgb": {ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE} <= emitted,
        "has_cmy": {ChannelType.CYAN, ChannelType.MAGENTA, ChannelType.YELLOW} <= emitted,
        "has_color_wheel": ChannelType.COLOR_WHEEL in emitted,
        "source": "ofl",
        "source_id": f"{manufacturer_key}/{fixture_key}",
        "categories": [c.lower().replace(" ", "_") for c in categories],
        "modes": modes,
    }

    pan_range = _axis_travel(channels, "Pan")
    if pan_range is not None:
        result["pan_range"] = pan_range
    tilt_range = _axis_travel(channels, "Tilt")
    if tilt_range is not None:
        result["tilt_range"] = tilt_range

    return result
