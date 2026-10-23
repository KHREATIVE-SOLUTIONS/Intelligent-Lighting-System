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


def parse_grandma_xml(content: str) -> List[Dict[str, Any]]:
    """Parse grandMA2/3 XML patch export.

    Real grandMA2 exports put every element in the MA namespace, name the fixture
    type in a child element, and store the patch as an absolute address; all of
    that is handled alongside the simpler attribute form. Universes come back
    0-based, matching the Hog and Eos parsers.
    """
    fixtures = []
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse grandMA XML: {e}")
        return fixtures

    for fixture_el in root.iter():
        if _local_name(fixture_el.tag) != "Fixture":
            continue

        name = _attr(fixture_el, "Name", "name")
        fixture_type = _attr(fixture_el, "FixtureType", "fixture_type")
        if not fixture_type:
            type_el = _child(fixture_el, "FixtureType")
            if type_el is not None:
                fixture_type = _attr(type_el, "name", "Name") or (type_el.text or "").strip()

        patched = _grandma_patch(fixture_el)
        universe, address = patched if patched is not None else (0, 1)

        # Extract manufacturer/model
        parts = fixture_type.split(" ", 1)
        manufacturer = parts[0] if parts and parts[0] else "Unknown"
        model = parts[1] if len(parts) > 1 else fixture_type

        fixtures.append({
            "name": name,
            "manufacturer": manufacturer,
            "model": model,
            "universe": universe,
            "dmx_address": address,
        })

    return fixtures


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
