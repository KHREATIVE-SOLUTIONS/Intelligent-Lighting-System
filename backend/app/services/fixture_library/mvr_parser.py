"""
MVR File Parser
================

Parses MVR (My Virtual Rig) files - ZIP archives containing GDTF fixtures
and a GeneralSceneDescription.xml with stage layout information.

What is read from the scene (MVR 1.4 - 1.6, DIN SPEC 15801):

- Layers, and the objects in their ChildLists, to any depth. A Matrix places an
  object in its PARENT's coordinate system, so a fixture inside a GroupObject or
  hung under a Truss is placed by composing every matrix above it.
- Matrix is four vectors "{u}{v}{w}{o}": a local point (x, y, z) lands at
  u*x + v*y + w*z + o. Millimetres, right-handed, Z up. Converted to metres in
  stage axes by stage_axes, which documents the one assumption that involves.
- Fixture: name and uuid attributes; GDTFSpec, GDTFMode, FixtureID,
  FixtureIDNumeric, UnitNumber, CustomId, Classing, Position, Function and
  Addresses as child elements.
- Address: break attribute, and either an absolute address counted from 1
  (universe 1 address 1 is 1, universe 2 address 1 is 513) or "universe.address"
  with the universe counted from 1. Universes come back 0-based.
- AUXData Class and Position, resolved to their names.
- Truss objects, as named positions.
"""

import io
import logging
import re
import zipfile
from typing import Dict, Any, List, Optional, Tuple
from xml.etree import ElementTree

from app.services.fixture_library import stage_axes
from app.services.fixture_library.gdtf_parser import parse_gdtf, _strip_namespaces
from app.services.fixture_library.xml_safety import MAX_XML_BYTES, parse_xml

logger = logging.getLogger(__name__)

DMX_UNIVERSE_SIZE = 512
MAX_EMBEDDED_GDTF = 500
MAX_EMBEDDED_GDTF_BYTES = 64 * 1024 * 1024

SCENE_FILE = "generalscenedescription.xml"

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_GROUP = re.compile(r"\{([^{}]*)\}")

# Objects that can hold a ChildList of their own, besides the two that are
# reported (GroupObject as a group, Truss as a position).
_CONTAINERS = {"SceneObject", "Support", "VideoScreen", "Projector", "FocusPoint"}

Transform = Tuple[stage_axes.Matrix3, Tuple[float, float, float]]
_ORIGIN: Transform = (stage_axes.IDENTITY, (0.0, 0.0, 0.0))


def split_absolute_address(absolute: int) -> Optional[Tuple[int, int]]:
    """(0-based universe, 1-512 address) for an absolute address counted from 1."""
    if absolute < 1:
        return None
    return (absolute - 1) // DMX_UNIVERSE_SIZE, (absolute - 1) % DMX_UNIVERSE_SIZE + 1


def parse_matrix(text: Optional[str]) -> Optional[Transform]:
    """An MVR Matrix as (rotation acting on column vectors, offset in mm).

    Accepts the 4x3 form the specification defines and the 4x4 form some
    exporters write, whose fourth column carries nothing.
    """
    if not text or not text.strip():
        return None
    groups = [[float(n) for n in _NUMBER.findall(g)] for g in _GROUP.findall(text)]
    if not groups:
        flat = [float(n) for n in _NUMBER.findall(text)]
        size = 4 if len(flat) == 16 else 3
        if len(flat) not in (12, 16):
            return None
        groups = [flat[i:i + size] for i in range(0, len(flat), size)]
    if len(groups) != 4 or any(len(g) < 3 for g in groups):
        return None
    u, v, w, o = (g[:3] for g in groups)
    return stage_axes.columns_to_matrix(u, v, w), (o[0], o[1], o[2])


def _compose(parent: Transform, child: Transform) -> Transform:
    parent_m, parent_o = parent
    child_m, child_o = child
    turned = stage_axes.apply(parent_m, child_o)
    return (
        stage_axes.multiply(parent_m, child_m),
        (turned[0] + parent_o[0], turned[1] + parent_o[1], turned[2] + parent_o[2]),
    )


def _text(element: ElementTree.Element, name: str) -> str:
    """A value MVR writes as a child element, and older files as an attribute."""
    child = element.find(name)
    if child is not None and (child.text or "").strip():
        return child.text.strip()
    return (element.get(name) or "").strip()


def _parse_address(text: str) -> Optional[Tuple[int, int]]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        if "." in text:
            universe_text, address_text = text.split(".", 1)
            universe, address = int(universe_text), int(address_text)
            if universe < 1 or not 1 <= address <= DMX_UNIVERSE_SIZE:
                return None
            return universe - 1, address
        return split_absolute_address(int(text))
    except ValueError:
        return None


def _addresses(fixture_el: ElementTree.Element, name: str, warnings: List[str]) -> List[Dict[str, int]]:
    found = []
    for addr in fixture_el.iter("Address"):
        raw = (addr.text or "").strip()
        if not raw:
            continue
        parsed = _parse_address(raw)
        if parsed is None:
            # 0 is how several exporters write "not patched"; anything else is a fault.
            if raw not in ("0", "0.0"):
                warnings.append(f"{name}: address '{raw}' could not be read")
            continue
        try:
            dmx_break = int(addr.get("break") or 0)
        except ValueError:
            dmx_break = 0
        found.append({"break": dmx_break, "universe": parsed[0], "address": parsed[1]})
    found.sort(key=lambda a: a["break"])
    return found


def _place(transform: Transform) -> Dict[str, Any]:
    matrix, offset = transform
    x, y, z = stage_axes.z_up_to_stage(offset[0] / 1000.0, offset[1] / 1000.0, offset[2] / 1000.0)
    rotation = stage_axes.stage_rotation_degrees(stage_axes.z_up_rotation_to_stage(matrix))
    rx, ry, rz = rotation if rotation is not None else (0.0, 0.0, 0.0)
    return {
        "position_x": round(x, 4), "position_y": round(y, 4), "position_z": round(z, 4),
        "rotation_x": rx, "rotation_y": ry, "rotation_z": rz,
    }


class _Scene:
    """Walks a scene, carrying the transform and the names above each object."""

    def __init__(self, classes: Dict[str, str], positions: Dict[str, str]):
        self.classes = classes
        self.positions = positions
        self.fixtures: List[Dict[str, Any]] = []
        self.trusses: List[Dict[str, Any]] = []
        self.layers: List[str] = []
        self.warnings: List[str] = []

    def _own(self, element: ElementTree.Element, label: str) -> Tuple[Optional[Transform], bool]:
        """(this object's own transform, whether it declared a Matrix at all)."""
        matrix_el = element.find("Matrix")
        if matrix_el is None:
            return None, False
        own = parse_matrix(matrix_el.text)
        if own is None:
            self.warnings.append(f"{label}: Matrix '{(matrix_el.text or '').strip()[:60]}' could not be read")
        return own, True

    def walk(self, element: ElementTree.Element, parent: Transform, placed: bool,
             layer: str, groups: Tuple[str, ...], truss: str) -> None:
        for child in element:
            tag = child.tag
            if tag == "ChildList":
                self.walk(child, parent, placed, layer, groups, truss)
                continue
            if tag not in ("Fixture", "GroupObject", "Truss") and tag not in _CONTAINERS:
                continue

            name = (child.get("name") or "").strip()
            own, declared = self._own(child, name or tag)
            unreadable = declared and own is None
            world = _compose(parent, own) if own is not None else parent
            # A position is only known when something on the way down stated one.
            here = (placed or own is not None) and not unreadable

            if tag == "Fixture":
                self._fixture(child, name, world, here, layer, groups, truss)
            elif tag == "GroupObject":
                self.walk(child, world, here, layer, groups + ((name,) if name else ()), truss)
            elif tag == "Truss":
                entry = {"name": name, "layer": layer, "kind": "truss", "has_position": here}
                entry.update(_place(world))
                self.trusses.append(entry)
                self.walk(child, world, here, layer, groups, name or truss)
            else:
                self.walk(child, world, here, layer, groups, truss)

    def _fixture(self, el: ElementTree.Element, name: str, world: Transform, placed: bool,
                 layer: str, groups: Tuple[str, ...], truss: str) -> None:
        label = name or _text(el, "FixtureID") or "fixture"
        addresses = _addresses(el, label, self.warnings)
        primary = addresses[0] if addresses else None

        class_uuid = _text(el, "Classing")
        position_uuid = _text(el, "Position")
        numeric = _text(el, "FixtureIDNumeric")
        try:
            fixture_id_numeric = int(numeric) if numeric else None
        except ValueError:
            fixture_id_numeric = None

        entry: Dict[str, Any] = {
            "name": name,
            "uuid": (el.get("uuid") or "").strip(),
            "gdtf_spec": _text(el, "GDTFSpec"),
            "gdtf_mode": _text(el, "GDTFMode"),
            "fixture_id": _text(el, "FixtureID"),
            "fixture_id_numeric": fixture_id_numeric,
            "unit_number": _text(el, "UnitNumber"),
            "custom_id": _text(el, "CustomId"),
            "function": _text(el, "Function"),
            # The legacy keys: an unpatched fixture still reads universe 0,
            # address 1 there, so `patched` is what says whether to believe them.
            "universe": primary["universe"] if primary else 0,
            "dmx_address": primary["address"] if primary else 1,
            "patched": primary is not None,
            "addresses": addresses,
            "has_position": placed,
            "layer": layer,
            "groups": list(groups),
            "class_name": self.classes.get(class_uuid, ""),
            "position_name": self.positions.get(position_uuid, "") or truss,
            "truss": truss,
        }
        entry.update(_place(world) if placed else {
            "position_x": 0.0, "position_y": 0.0, "position_z": 0.0,
            "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
        })
        self.fixtures.append(entry)


def parse_scene_xml(xml_content: bytes) -> Dict[str, Any]:
    """Parse a GeneralSceneDescription.xml on its own.

    Returns the same keys as parse_mvr, with nothing under gdtf_parsed.
    """
    root = parse_xml(xml_content, "MVR XML")
    _strip_namespaces(root)

    result: Dict[str, Any] = {
        "stage": {"width": 10.0, "depth": 8.0, "height": 6.0},
        "fixtures": [],
        "gdtf_parsed": [],
        "trusses": [],
        "layers": [],
        "warnings": [],
        "version": "",
        "provider": "",
    }
    if root.tag == "GeneralSceneDescription":
        major, minor = root.get("verMajor"), root.get("verMinor")
        if major is not None:
            result["version"] = f"{major}.{minor or 0}"
        result["provider"] = " ".join(
            part for part in (root.get("provider"), root.get("providerVersion")) if part
        )

    scene = root if root.tag == "Scene" else root.find(".//Scene")
    if scene is None:
        result["warnings"].append("the file has no Scene, so it places nothing")
        return result

    classes: Dict[str, str] = {}
    positions: Dict[str, str] = {}
    aux = scene.find("AUXData")
    if aux is not None:
        for el in aux.iter("Class"):
            if el.get("uuid"):
                classes[el.get("uuid").strip()] = (el.get("name") or "").strip()
        for el in aux.iter("Position"):
            if el.get("uuid"):
                positions[el.get("uuid").strip()] = (el.get("name") or "").strip()

    walker = _Scene(classes, positions)
    layers_el = scene.find("Layers")
    layers = list(layers_el) if layers_el is not None else scene.findall(".//Layer")
    for layer in layers:
        if layer.tag != "Layer":
            continue
        layer_name = (layer.get("name") or "").strip()
        walker.layers.append(layer_name)
        own, declared = walker._own(layer, layer_name or "Layer")
        base = own if own is not None else _ORIGIN
        walker.walk(layer, base, own is not None, layer_name, (), "")

    result["fixtures"] = walker.fixtures
    result["trusses"] = walker.trusses
    result["layers"] = walker.layers
    result["warnings"] = walker.warnings
    return result


def parse_mvr(file_content: bytes) -> Dict[str, Any]:
    """Parse an MVR file and return stage layout + fixtures.

    Returns:
        Dict with keys: stage, fixtures, gdtf_parsed, trusses, layers, warnings,
        version, provider. Each fixture keeps the keys this always returned
        (name, gdtf_spec, universe, dmx_address, position_x/y/z) and adds the
        rest of what the scene says about it.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            gsd_name = None
            for name in zf.namelist():
                if name.lower().rsplit("/", 1)[-1] == SCENE_FILE:
                    gsd_name = name
                    break

            if not gsd_name:
                raise ValueError("No GeneralSceneDescription.xml found in MVR archive")
            if zf.getinfo(gsd_name).file_size > MAX_XML_BYTES:
                raise ValueError("Invalid MVR file - the scene description is too large to read")

            xml_content = zf.read(gsd_name)

            skipped: List[str] = []
            gdtf_files = {}
            for info in zf.infolist():
                if not info.filename.lower().endswith(".gdtf"):
                    continue
                if len(gdtf_files) >= MAX_EMBEDDED_GDTF or info.file_size > MAX_EMBEDDED_GDTF_BYTES:
                    skipped.append(info.filename)
                    continue
                gdtf_files[info.filename] = zf.read(info.filename)

    except zipfile.BadZipFile:
        raise ValueError("Invalid MVR file - not a valid ZIP archive")

    result = parse_scene_xml(xml_content)
    for name in skipped:
        result["warnings"].append(f"embedded GDTF '{name}' was skipped: too large, or too many files")

    for gdtf_name, gdtf_content in gdtf_files.items():
        try:
            parsed = parse_gdtf(gdtf_content)
            parsed["_gdtf_filename"] = gdtf_name
            result["gdtf_parsed"].append(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse GDTF file {gdtf_name}: {e}")
            result["warnings"].append(f"embedded GDTF '{gdtf_name}' could not be read: {e}")

    return result
