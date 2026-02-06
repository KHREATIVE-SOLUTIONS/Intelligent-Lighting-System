"""
MVR File Parser
================

Parses MVR (My Virtual Rig) files - ZIP archives containing GDTF fixtures
and a GeneralSceneDescription.xml with stage layout information.
"""

import io
import logging
import zipfile
from typing import Dict, Any, List, Optional
from xml.etree import ElementTree

from app.services.fixture_library.gdtf_parser import parse_gdtf

logger = logging.getLogger(__name__)


def parse_mvr(file_content: bytes) -> Dict[str, Any]:
    """Parse an MVR file and return stage layout + fixtures.

    Returns:
        Dict with keys: stage, fixtures, gdtf_files
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            # Find GeneralSceneDescription.xml
            gsd_name = None
            for name in zf.namelist():
                if name.lower().endswith("generalscenedescription.xml"):
                    gsd_name = name
                    break

            if not gsd_name:
                raise ValueError("No GeneralSceneDescription.xml found in MVR archive")

            xml_content = zf.read(gsd_name)

            # Find embedded GDTF files
            gdtf_files = {}
            for name in zf.namelist():
                if name.lower().endswith(".gdtf"):
                    gdtf_files[name] = zf.read(name)

    except zipfile.BadZipFile:
        raise ValueError("Invalid MVR file - not a valid ZIP archive")

    # Parse the scene description
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError as e:
        raise ValueError(f"Invalid MVR XML: {e}")

    # Extract scene info
    scene = root.find(".//Scene")
    result = {
        "stage": {
            "width": 10.0,
            "depth": 8.0,
            "height": 6.0,
        },
        "fixtures": [],
        "gdtf_parsed": [],
    }

    # Parse GDTF files
    for gdtf_name, gdtf_content in gdtf_files.items():
        try:
            parsed = parse_gdtf(gdtf_content)
            parsed["_gdtf_filename"] = gdtf_name
            result["gdtf_parsed"].append(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse GDTF file {gdtf_name}: {e}")

    # Extract fixture placements from scene
    if scene is not None:
        layers = scene.findall(".//Layer")
        for layer in layers:
            fixture_els = layer.findall(".//Fixture")
            for fix_el in fixture_els:
                name = fix_el.get("name", "")
                gdtf_spec = fix_el.get("GDTFSpec", "")

                # Extract position matrix
                matrix_el = fix_el.find("Matrix")
                position = {"x": 0.0, "y": 0.0, "z": 0.0}
                if matrix_el is not None:
                    matrix_text = matrix_el.text or ""
                    values = [float(v) for v in matrix_text.replace("{", "").replace("}", "").split(",") if v.strip()]
                    if len(values) >= 12:
                        # Translation is in the last column of the 4x3 matrix
                        position["x"] = values[3] / 1000.0  # mm to meters
                        position["y"] = values[7] / 1000.0
                        position["z"] = values[11] / 1000.0

                # Extract DMX addressing
                addresses = fix_el.findall(".//Address")
                universe = 0
                dmx_address = 1
                for addr in addresses:
                    try:
                        dmx_val = int(addr.text or "1")
                        universe = dmx_val // 512
                        dmx_address = (dmx_val % 512) or 512
                    except (ValueError, TypeError):
                        pass

                result["fixtures"].append({
                    "name": name,
                    "gdtf_spec": gdtf_spec,
                    "universe": universe,
                    "dmx_address": dmx_address,
                    "position_x": position["x"],
                    "position_y": position["y"],
                    "position_z": position["z"],
                })

    return result
