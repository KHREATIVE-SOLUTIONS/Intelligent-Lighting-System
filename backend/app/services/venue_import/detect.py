"""
Reading a venue file
====================

Works out what an upload is and hands it to the reader for that format. The
contents decide; the extension is only a hint, because a patch arrives as
"patch.xml", "LIV.mvr.zip" or "export (3).txt" as often as under its own name.

The readers for GDTF, MVR and grandMA XML are the ones in fixture_library; the
functions here turn what they return into ImportedFixture.
"""

import io
import re
import zipfile
from typing import Any, Dict, Optional

from app.services.fixture_library import stage_axes
from app.services.fixture_library.console_parsers import parse_grandma_export
from app.services.fixture_library.gdtf_parser import parse_gdtf
from app.services.fixture_library.mvr_parser import SCENE_FILE, parse_mvr, parse_scene_xml

from .csv_patch import decode, parse_csv_patch
from .model import ImportedFixture, ParsedVenue, VenueImportError

SPREADSHEET_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".ods", ".numbers")

NO_SPREADSHEETS = (
    "Spreadsheet files (.xlsx) are not read: this system has no spreadsheet parser "
    "installed. Open the sheet and use Save As > CSV, then import the .csv."
)


def _extension(filename: str) -> str:
    name = (filename or "").lower().strip()
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""


_ROOT_TAG = re.compile(r"<(?![?!])(?:[\w.-]+:)?([\w.-]+)")


def _root_tag(head: str) -> str:
    """The local name of the first element, past the declaration and comments."""
    head = re.sub(r"<!--.*?(-->|$)", "", head, flags=re.DOTALL)
    found = _ROOT_TAG.search(head)
    return found.group(1) if found else ""


def detect_format(filename: str, content: bytes) -> str:
    """One of "mvr", "mvr_xml", "gdtf", "gdtf_xml", "ma2", "csv".

    Raises VenueImportError for an empty file, a spreadsheet, or an archive
    that is neither an MVR nor a GDTF.
    """
    if not content or not content.strip():
        raise VenueImportError("The file is empty.")

    extension = _extension(filename)

    if content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = [name.lower() for name in zf.namelist()]
        except zipfile.BadZipFile:
            raise VenueImportError("The file looks like a ZIP archive but cannot be opened.")
        leaves = [name.rsplit("/", 1)[-1] for name in names]
        if SCENE_FILE in leaves:
            return "mvr"
        if "description.xml" in leaves:
            return "gdtf"
        if "[content_types].xml" in leaves or any(name.startswith("xl/") for name in names):
            raise VenueImportError(NO_SPREADSHEETS)
        raise VenueImportError(
            "The archive holds neither a GeneralSceneDescription.xml (MVR) nor a "
            "description.xml (GDTF)."
        )

    if extension in SPREADSHEET_EXTENSIONS:
        raise VenueImportError(NO_SPREADSHEETS)

    head = decode(content[:4096]).lstrip()
    if head.startswith("<"):
        # The root element says what it is. A grandMA export has FixtureType
        # elements too, so looking for the word anywhere would misread it.
        root = _root_tag(head)
        if root == "GeneralSceneDescription":
            return "mvr_xml"
        if root in ("GDTF", "FixtureType"):
            return "gdtf_xml"
        return "ma2"

    if extension in (".mvr", ".gdtf"):
        raise VenueImportError(f"The file is named {extension} but is not a ZIP archive.")
    return "csv"


def _number(text: Any) -> Optional[int]:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _split_spec(spec: str) -> tuple:
    """(manufacturer, model) from a GDTFSpec file name: "Maker@Model@rev.gdtf"."""
    name = spec.rsplit("/", 1)[-1]
    if name.lower().endswith(".gdtf"):
        name = name[:-5]
    parts = name.split("@")
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return "", name.strip()


def _from_mvr(data: Dict[str, Any], source_file: str) -> ParsedVenue:
    parsed = ParsedVenue(format="mvr", source_file=source_file)
    parsed.profiles = list(data.get("gdtf_parsed", []))
    parsed.layers = list(data.get("layers", []))
    parsed.warnings.extend(data.get("warnings", []))
    parsed.positions = [
        {
            "name": truss.get("name", ""), "kind": "truss", "layer": truss.get("layer", ""),
            "x": truss["position_x"], "y": truss["position_y"], "z": truss["position_z"],
            "rotation_y": truss["rotation_y"],
        }
        for truss in data.get("trusses", []) if truss.get("has_position")
    ]

    for item in data.get("fixtures", []):
        manufacturer, model = _split_spec(item.get("gdtf_spec", ""))
        names = [n for n in [item.get("class_name", "")] + list(reversed(item.get("groups", []))) if n]
        group_name = names[0] if names else ""
        placed = bool(item.get("has_position"))
        extra = [(a["universe"], a["address"]) for a in item.get("addresses", [])[1:]]
        notes = []
        if extra:
            notes.append(
                f"has {len(extra)} more address(es) on other DMX breaks; only the first is patched"
            )
        parsed.fixtures.append(ImportedFixture(
            name=item.get("name", ""),
            fixture_id=item.get("fixture_id", ""),
            fixture_number=item.get("fixture_id_numeric") or _number(item.get("fixture_id")),
            type_name=" ".join(p for p in (manufacturer, model) if p),
            manufacturer=manufacturer,
            model=model,
            mode_name=item.get("gdtf_mode", ""),
            universe=item["universe"] if item.get("patched") else None,
            dmx_address=item["dmx_address"] if item.get("patched") else None,
            extra_addresses=extra,
            position=(item["position_x"], item["position_y"], item["position_z"]) if placed else None,
            rotation=(item["rotation_x"], item["rotation_y"], item["rotation_z"]) if placed else None,
            position_source="mvr" if placed else "none",
            position_label=item.get("position_name", ""),
            group_name=group_name,
            groups=[n for n in names[1:] if n != group_name],
            layer=item.get("layer", ""),
            gdtf_spec=item.get("gdtf_spec", ""),
            notes=notes,
        ))

    if any(f.position is not None for f in parsed.fixtures) or parsed.positions:
        parsed.assumptions.append("MVR positions are millimetres. " + stage_axes.AXIS_ASSUMPTION)
    parsed.assumptions.append(
        "MVR addresses were read as absolute, counted from 1: 513 is this system's universe 1, channel 1."
    )
    return parsed


def _from_ma2(data: Dict[str, Any], source_file: str) -> ParsedVenue:
    parsed = ParsedVenue(format="ma2", source_file=source_file)
    parsed.layers = list(data.get("layers", []))
    parsed.warnings.extend(data.get("warnings", []))

    for item in data.get("fixtures", []):
        placed = bool(item.get("has_position"))
        patched = bool(item.get("patched"))
        extra = [(p["universe"], p["address"]) for p in item.get("patches", [])[1:]]
        notes = []
        if extra:
            notes.append(f"is patched at {len(extra)} more address(es); only the first is patched here")
        fixture_id = item.get("fixture_id") or item.get("channel_id") or ""
        parsed.fixtures.append(ImportedFixture(
            name=item.get("name", ""),
            fixture_id=fixture_id,
            fixture_number=_number(fixture_id),
            # The console's type name is one string; which words are the maker
            # is not something the export says, so it is not split here.
            type_name=item.get("fixture_type", ""),
            mode_name=item.get("mode", ""),
            universe=item["universe"] if patched else None,
            dmx_address=item["dmx_address"] if patched else None,
            extra_addresses=extra,
            position=(item["position_x"], item["position_y"], item["position_z"]) if placed else None,
            rotation=(item["rotation_x"], item["rotation_y"], item["rotation_z"]) if placed else None,
            position_source="ma2" if placed else "none",
            group_name=item.get("layer", ""),
            layer=item.get("layer", ""),
            notes=notes,
        ))

    if not parsed.fixtures:
        # An XML that would not parse comes back as no fixtures and the reason.
        raise VenueImportError(parsed.warnings[0] if parsed.warnings else (
            "No fixtures were found in the XML. Expected a grandMA2 export of fixture "
            "layers or patch, with <Fixture> elements."
        ))
    if any(f.position is not None for f in parsed.fixtures):
        parsed.assumptions.append("grandMA positions are metres. " + stage_axes.AXIS_ASSUMPTION)
    parsed.assumptions.append(
        "grandMA universes count from 1: its universe 1 is universe 0 here. "
        "Each layer became a group."
    )
    return parsed


def _gdtf_from_xml(content: bytes) -> bytes:
    """A description.xml on its own, wrapped so the GDTF reader takes it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("description.xml", content)
    return buffer.getvalue()


def read_venue_file(
    filename: str,
    content: bytes,
    universe_base: str = "auto",
    up_axis: str = "y",
) -> ParsedVenue:
    """Read an upload in whichever supported format it is.

    Raises VenueImportError when it is none of them or cannot be parsed.
    """
    kind = detect_format(filename, content)
    try:
        if kind == "csv":
            return parse_csv_patch(content, filename, universe_base=universe_base, up_axis=up_axis)
        if kind == "mvr":
            return _from_mvr(parse_mvr(content), filename)
        if kind == "mvr_xml":
            parsed = _from_mvr(parse_scene_xml(content), filename)
            parsed.warnings.append(
                "This is the scene description on its own, without the .mvr archive, so no "
                "fixture profiles came with it."
            )
            return parsed
        if kind == "ma2":
            return _from_ma2(parse_grandma_export(content), filename)

        profile = parse_gdtf(content if kind == "gdtf" else _gdtf_from_xml(content))
        profile["_gdtf_filename"] = filename
        return ParsedVenue(format="gdtf", source_file=filename, profiles=[profile])
    except VenueImportError:
        raise
    except ValueError as e:
        raise VenueImportError(str(e))
