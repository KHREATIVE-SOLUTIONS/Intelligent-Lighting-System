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


def parse_grandma_xml(content: str) -> List[Dict[str, Any]]:
    """Parse grandMA2/3 XML patch export."""
    fixtures = []
    try:
        root = ElementTree.fromstring(content)
        for fixture_el in root.findall(".//Fixture"):
            name = fixture_el.get("Name", "")
            fixture_type = fixture_el.get("FixtureType", "")

            # Extract DMX address
            patch = fixture_el.find("Patch") or fixture_el.find("DMX")
            universe = 0
            address = 1
            if patch is not None:
                try:
                    universe = int(patch.get("Universe", "0"))
                    address = int(patch.get("Address", "1"))
                except (ValueError, TypeError):
                    pass

            # Extract manufacturer/model
            parts = fixture_type.split(" ", 1)
            manufacturer = parts[0] if parts else "Unknown"
            model = parts[1] if len(parts) > 1 else fixture_type

            fixtures.append({
                "name": name,
                "manufacturer": manufacturer,
                "model": model,
                "universe": universe,
                "dmx_address": address,
            })
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse grandMA XML: {e}")

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
