"""
Console Patch File Parsers
===========================

Parsers for lighting console patch export formats:
- grandMA2/3 XML
- Hog CSV
- ETC Eos CSV
"""

import csv
import io
import logging
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)


def _local_name(tag: str) -> str:
    """An element's tag without its XML namespace."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(element, name: str):
    """First direct child with the given local name, ignoring namespaces."""
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _descendant(element, name: str):
    """First descendant with the given local name, ignoring namespaces."""
    for child in element.iter():
        if child is not element and _local_name(child.tag) == name:
            return child
    return None


def _attr(element, *names: str) -> str:
    for name in names:
        value = element.get(name)
        if value not in (None, ""):
            return value
    return ""


def _grandma_patch(fixture_el) -> Optional[tuple]:
    """(universe, address) from a grandMA fixture, 0-based universe, 1-based address.

    grandMA numbers universes from 1. Accepted forms:
      <Patch Universe="3" Address="101"/>   attributes, MA-style 1-based universe
      <Patch><Address>1125</Address></Patch> grandMA2 export: absolute address,
                                              (universe - 1) * 512 + address
      <Address>3.101</Address>               universe.address text
    """
    patch = _descendant(fixture_el, "Patch")
    if patch is None:
        patch = _descendant(fixture_el, "DMX")
    if patch is None:
        return None

    try:
        universe_attr = _attr(patch, "Universe", "universe")
        address_attr = _attr(patch, "Address", "address")
        if address_attr:
            address = int(address_attr)
            universe = int(universe_attr) if universe_attr else 1
            return max(0, universe - 1), max(1, min(512, address))

        address_el = patch if _local_name(patch.tag) == "Address" else _descendant(patch, "Address")
        text = (address_el.text or "").strip() if address_el is not None else ""
        if not text:
            return None
        if "." in text:
            universe_text, address_text = text.split(".", 1)
            return max(0, int(universe_text) - 1), max(1, min(512, int(address_text)))
        absolute = int(text)
        if absolute < 1:
            return None
        return (absolute - 1) // 512, (absolute - 1) % 512 + 1
    except (ValueError, TypeError):
        return None


def _number(value) -> Optional[float]:
    """A coordinate as written by a console: "1.5", "1,5", " -0 "."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _triple(element, *name_sets) -> Optional[tuple]:
    """Three numbers from an element's attributes or same-named children.

    Each name set is one way of spelling x, y and z; the first set that yields
    all three wins.
    """
    if element is None:
        return None
    for names in name_sets:
        values = []
        for name in names:
            value = _number(element.get(name))
            if value is None:
                child = _child(element, name)
                value = _number(child.text) if child is not None else None
            values.append(value)
        if all(v is not None for v in values):
            return tuple(values)
    return None


_XYZ = (("x", "y", "z"), ("X", "Y", "Z"))
_POS = (("PosX", "PosY", "PosZ"), ("posx", "posy", "posz"), ("pos_x", "pos_y", "pos_z"))
_ROT = (("RotX", "RotY", "RotZ"), ("rotx", "roty", "rotz"), ("rot_x", "rot_y", "rot_z"))


def _grandma_position(fixture_el) -> tuple:
    """(location, rotation) as the export writes them, or None for either.

    grandMA2 puts each fixture's stage position on its SubFixture:

        <AbsolutePosition>
          <Location x="-3.6" y="1.5" z="3.05"/>
          <Rotation x="0" y="0" z="90"/>
        </AbsolutePosition>

    Metres and degrees, Z up. PosX/PosY/PosZ (and RotX/RotY/RotZ), as attributes
    or child elements of the fixture or of a position element, are read too.
    """
    for holder_name in ("AbsolutePosition", "Position", "Pos"):
        holder = _descendant(fixture_el, holder_name)
        if holder is None:
            continue
        location = _triple(_child(holder, "Location"), *_XYZ) or _triple(holder, *_XYZ, *_POS)
        if location is None:
            continue
        rotation = _triple(_child(holder, "Rotation"), *_XYZ) or _triple(holder, *_ROT)
        return location, rotation

    for element in [fixture_el] + [e for e in fixture_el.iter() if _local_name(e.tag) == "SubFixture"]:
        location = _triple(element, *_POS)
        if location is not None:
            return location, _triple(element, *_ROT)
    return None, None


def _grandma_all_patches(fixture_el) -> list:
    """Every (universe, address) the fixture is patched at, in file order."""
    patches = []
    for element in fixture_el.iter():
        if element is fixture_el or _local_name(element.tag) not in ("Patch", "DMX"):
            continue
        holder = ElementTree.Element("holder")
        holder.append(element)
        patched = _grandma_patch(holder)
        if patched is not None and patched not in patches:
            patches.append(patched)
    return patches


def _grandma_type_name(fixture_el) -> tuple:
    """(type name, mode, type number) for a fixture.

    A grandMA2 export names the type in a child element and can lead the name
    with the show's own type number ("3 Martin MAC Aura XB"); that number is
    the console's, not part of the fixture's name, so it is taken off.
    """
    name = _attr(fixture_el, "FixtureType", "fixture_type")
    mode = _attr(fixture_el, "Mode", "mode")
    number = ""
    type_el = _child(fixture_el, "FixtureType")
    if type_el is not None:
        if not name:
            name = _attr(type_el, "name", "Name") or (type_el.text or "").strip()
        mode = mode or _attr(type_el, "mode", "Mode")
        no_el = _child(type_el, "No")
        number = (no_el.text or "").strip() if no_el is not None else ""
    name = " ".join(name.split())
    if number and name.startswith(number + " "):
        name = name[len(number) + 1:]
    return name, mode, number


def parse_grandma_export(content) -> Dict[str, Any]:
    """Read a grandMA2/3 XML patch or fixture-layer export in full.

    Returns {"fixtures": [...], "layers": [...], "warnings": [...]}. Each
    fixture carries what parse_grandma_xml always returned (name, manufacturer,
    model, universe, dmx_address) plus its layer, fixture and channel ids, the
    whole type name, whether it is patched at all, and its position and
    rotation in stage axes when the export has them.

    Real grandMA2 exports put every element in the MA namespace, name the fixture
    type in a child element, and store the patch as an absolute address; all of
    that is handled alongside the simpler attribute form. Universes come back
    0-based, matching the Hog and Eos parsers.
    """
    from app.services.fixture_library import stage_axes
    from app.services.fixture_library.xml_safety import parse_xml

    result: Dict[str, Any] = {"fixtures": [], "layers": [], "warnings": []}
    try:
        root = parse_xml(content, "grandMA XML")
    except ValueError as e:
        logger.error(f"Failed to parse grandMA XML: {e}")
        result["warnings"].append(str(e))
        return result

    layer_of = {}
    for layer_el in root.iter():
        if _local_name(layer_el.tag) != "Layer":
            continue
        layer_name = _attr(layer_el, "name", "Name")
        result["layers"].append(layer_name)
        for inner in layer_el.iter():
            layer_of[inner] = layer_name

    for fixture_el in root.iter():
        if _local_name(fixture_el.tag) != "Fixture":
            continue

        name = _attr(fixture_el, "Name", "name")
        fixture_type, mode, type_number = _grandma_type_name(fixture_el)

        patched = _grandma_patch(fixture_el)
        universe, address = patched if patched is not None else (0, 1)
        patches = _grandma_all_patches(fixture_el)

        # Extract manufacturer/model
        parts = fixture_type.split(" ", 1)
        manufacturer = parts[0] if parts and parts[0] else "Unknown"
        model = parts[1] if len(parts) > 1 else fixture_type

        entry = {
            "name": name,
            "manufacturer": manufacturer,
            "model": model,
            "universe": universe,
            "dmx_address": address,
            "fixture_type": fixture_type,
            "mode": mode,
            "type_number": type_number,
            "fixture_id": _attr(fixture_el, "fixture_id", "FixtureID", "FixtureId", "fid", "FID"),
            "channel_id": _attr(fixture_el, "channel_id", "ChannelID", "ChannelId", "cid", "CID"),
            "layer": layer_of.get(fixture_el, ""),
            # An unpatched fixture still reads universe 0, address 1 in the legacy
            # keys, so `patched` is what says whether to believe them.
            "patched": patched is not None,
            "patches": [{"universe": u, "address": a} for u, a in patches],
            "has_position": False,
            "position_x": 0.0, "position_y": 0.0, "position_z": 0.0,
            "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
        }

        location, rotation = _grandma_position(fixture_el)
        if location is not None:
            x, y, z = stage_axes.z_up_to_stage(*location)
            entry.update(has_position=True, position_x=x, position_y=y, position_z=z)
            if rotation is not None:
                rx, ry, rz = stage_axes.z_up_euler_to_stage(*rotation)
                entry.update(rotation_x=rx, rotation_y=ry, rotation_z=rz)
                if sum(1 for v in rotation if abs(v) > 1e-9) > 1:
                    result["warnings"].append(
                        f"{name or 'fixture'}: turned about more than one axis; each angle was "
                        "carried over on its own axis, and the order the console applies them in is assumed"
                    )

        result["fixtures"].append(entry)

    return result


def parse_grandma_xml(content: str) -> List[Dict[str, Any]]:
    """Parse grandMA2/3 XML patch export. See parse_grandma_export."""
    return parse_grandma_export(content)["fixtures"]


def parse_hog_csv(content: str) -> List[Dict[str, Any]]:
    """Parse Hog console CSV patch export."""
    fixtures = []
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        try:
            name = row.get("Name", row.get("name", ""))
            fixture_type = row.get("Type", row.get("type", ""))
            dmx = row.get("DMX", row.get("dmx", "1.1"))

            # Parse universe.address format
            parts = dmx.split(".")
            universe = int(parts[0]) - 1 if len(parts) > 1 else 0
            address = int(parts[-1])

            fixtures.append({
                "name": name,
                "manufacturer": "",
                "model": fixture_type,
                "universe": universe,
                "dmx_address": address,
            })
        except (ValueError, TypeError, KeyError):
            continue

    return fixtures


def parse_eos_csv(content: str) -> List[Dict[str, Any]]:
    """Parse ETC Eos CSV patch export."""
    fixtures = []
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        try:
            channel = row.get("Channel", row.get("Chan", ""))
            name = row.get("Label", row.get("Name", f"Ch {channel}"))
            fixture_type = row.get("Fixture Type", row.get("Type", ""))
            address = row.get("Address", row.get("Addr", "1/1"))

            # Parse universe/address format
            parts = str(address).split("/")
            universe = int(parts[0]) - 1 if len(parts) > 1 else 0
            dmx_addr = int(parts[-1])

            fixtures.append({
                "name": name,
                "manufacturer": "",
                "model": fixture_type,
                "universe": max(0, universe),
                "dmx_address": max(1, dmx_addr),
            })
        except (ValueError, TypeError, KeyError):
            continue

    return fixtures


def detect_and_parse(content: str, format_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """Auto-detect format and parse console patch file."""
    if format_hint:
        parsers = {
            "grandma": parse_grandma_xml,
            "grandma2": parse_grandma_xml,
            "grandma3": parse_grandma_xml,
            "hog": parse_hog_csv,
            "eos": parse_eos_csv,
        }
        parser = parsers.get(format_hint.lower())
        if parser:
            return parser(content)

    # Auto-detect
    content_stripped = content.strip()
    if content_stripped.startswith("<?xml") or content_stripped.startswith("<"):
        return parse_grandma_xml(content)
    elif "," in content_stripped.split("\n")[0]:
        # Try Eos first (has "Channel" or "Fixture Type" headers)
        first_line = content_stripped.split("\n")[0].lower()
        if "channel" in first_line or "fixture type" in first_line:
            return parse_eos_csv(content)
        return parse_hog_csv(content)

    return []
