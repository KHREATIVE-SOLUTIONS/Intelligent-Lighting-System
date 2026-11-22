"""
Venue Import Sample Files
=========================

Writes the small files the venue importer is tested against, from the LIV
approximate demo preset, so each one is a known subset of a rig this system
already holds and what an import should return is the preset itself.

Everything here is authored for this project. The three GDTFs describe this
system's own generic demo channel maps under the made-up maker "ILS Demo"; no
manufacturer's file was copied. The fixtures are the preset's, which is an
approximate recreation of a room and not that room's real patch.

    liv_approx_subset.mvr       36 fixtures: the 22 dance-floor spots hung under
                                four trusses, the 4 mezzanine spots inside a
                                group, the 8 dome washes, and the 2 booth wash
                                pars, whose GDTF is deliberately not in the
                                archive. Three GDTFs embedded.
    liv_approx_subset_ma2.xml   20 fixtures in three layers: mezzanine spots,
                                dome washes, strobes.
    liv_approx_subset_patch.csv 20 fixtures: the dome rim floods and the pars,
                                laid out the way a console sheet is, with the
                                two staircase pars given no coordinates.
    ils_demo_spot_16ch.gdtf     the 16-channel spot the MVR embeds.

scripts/build_venue_import_samples.py writes them to backend/tests/fixtures/import/
and a unit test holds the committed copies to what this returns.
"""

import csv
import io
import uuid
from typing import Dict, List, Sequence, Tuple
from xml.sax.saxutils import quoteattr

from app.services.console_export.archive import deterministic_zip
from app.services.fixture_library.stage_axes import stage_to_z_up

from .patch_sheet import channel_count
from .venue_presets import VENUE_PRESETS, FixtureSpec, VenuePreset

PRESET_NAME = "liv_miami_approx"
MAKER = "ILS Demo"
NOTE = (
    "Authored for the Intelligent Lighting System's import tests from its approximate "
    "LIV demo preset. Not a venue's real patch and not a manufacturer's file."
)

_NAMESPACE = uuid.UUID("6f1f6c0e-5a5c-4a39-9d0b-1d2a3c4b5e6f")

MVR_FILE = "liv_approx_subset.mvr"
MA2_FILE = "liv_approx_subset_ma2.xml"
CSV_FILE = "liv_approx_subset_patch.csv"
GDTF_FILE = "ils_demo_spot_16ch.gdtf"

# The spec the booth wash pars name in the MVR. No such file is in the archive.
MISSING_GDTF_SPEC = "Elation@Opti Tri Par.gdtf"


def _uuid(name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, name)).upper()


def preset() -> VenuePreset:
    return VENUE_PRESETS[PRESET_NAME]


def sheet_numbers(venue: VenuePreset) -> Dict[str, int]:
    """Preset fixture id -> its number on the patch sheet (universe, then address)."""
    ordered = sorted(venue.fixtures, key=lambda f: (f.universe, f.dmx_address))
    return {f.id: number for number, f in enumerate(ordered, start=1)}


def _by_group(venue: VenuePreset, *groups: str) -> List[FixtureSpec]:
    return [f for f in venue.fixtures if f.group in groups]


# ---------------------------------------------------------------------------
# GDTF
# ---------------------------------------------------------------------------

# (offset, attribute, physical from, physical to). A two-slot offset is 16-bit.
_Channel = Tuple[str, str, float, float]

_SPOT_16: List[_Channel] = [
    ("1,2", "Pan", -270, 270), ("3,4", "Tilt", -135, 135), ("5", "PositionMSpeed", 0, 1),
    ("6", "Dimmer", 0, 1), ("7", "Shutter1", 0, 1),
    ("8", "ColorAdd_R", 0, 1), ("9", "ColorAdd_G", 0, 1), ("10", "ColorAdd_B", 0, 1),
    ("11", "ColorAdd_W", 0, 1), ("12", "Color1", 0, 1), ("13", "Gobo1", 0, 1),
    ("14", "Gobo1PosRotate", 0, 1), ("15", "Prism1", 0, 1), ("16", "Focus1", 0, 1),
]
# Two attributes this system has no meaning for, to show they are kept and marked.
_SPOT_18: List[_Channel] = _SPOT_16 + [("17", "Control1", 0, 1), ("18", "Fans", 0, 1)]

_SPOT_12: List[_Channel] = [
    ("1,2", "Pan", -270, 270), ("3,4", "Tilt", -135, 135),
    ("5", "Dimmer", 0, 1), ("6", "Shutter1", 0, 1),
    ("7", "ColorAdd_R", 0, 1), ("8", "ColorAdd_G", 0, 1), ("9", "ColorAdd_B", 0, 1),
    ("10", "ColorAdd_W", 0, 1), ("11", "Zoom", 0, 1), ("12", "Focus1", 0, 1),
]

_WASH_14: List[_Channel] = [
    ("1,2", "Pan", -270, 270), ("3,4", "Tilt", -135, 135), ("5", "PositionMSpeed", 0, 1),
    ("6", "Dimmer", 0, 1), ("7", "Shutter1", 0, 1),
    ("8", "ColorAdd_R", 0, 1), ("9", "ColorAdd_G", 0, 1), ("10", "ColorAdd_B", 0, 1),
    ("11", "ColorAdd_W", 0, 1), ("12", "Zoom", 0, 1),
    ("13", "NoFunction", 0, 1), ("14", "NoFunction", 0, 1),
]

# file name -> (Name, ShortName, LongName, [(mode name, channels)])
GDTF_PROFILES: Dict[str, Tuple[str, str, str, List[Tuple[str, List[_Channel]]]]] = {
    f"{MAKER}@Demo Spot 16ch.gdtf": (
        "Demo Spot 16ch", "DSPOT16", "Demo moving spot, 16 channels",
        [("Standard 16ch", _SPOT_16), ("Extended 18ch", _SPOT_18)],
    ),
    f"{MAKER}@Demo Compact Spot 12ch.gdtf": (
        "Demo Compact Spot 12ch", "DSPOT12", "Demo compact moving spot, 12 channels",
        [("Standard 12ch", _SPOT_12)],
    ),
    f"{MAKER}@Demo Wash 14ch.gdtf": (
        "Demo Wash 14ch", "DWASH14", "Demo moving wash, 14 channels",
        [("Standard 14ch", _WASH_14)],
    ),
}

# Preset fixture type -> (the GDTF it is patched on in the MVR, its mode).
MVR_SPECS: Dict[str, Tuple[str, str]] = {
    "mover": (f"{MAKER}@Demo Spot 16ch.gdtf", "Standard 16ch"),
    "spot": (f"{MAKER}@Demo Compact Spot 12ch.gdtf", "Standard 12ch"),
    "wash": (f"{MAKER}@Demo Wash 14ch.gdtf", "Standard 14ch"),
}


def gdtf_description(file_name: str) -> str:
    """The description.xml of one of the demo GDTFs."""
    name, short_name, long_name, modes = GDTF_PROFILES[file_name]
    attributes = []
    for _, channels in modes:
        for _, attribute, _, _ in channels:
            if attribute not in attributes:
                attributes.append(attribute)

    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<GDTF DataVersion="1.2">',
        f'  <FixtureType Name={quoteattr(name)} ShortName={quoteattr(short_name)} '
        f'LongName={quoteattr(long_name)} Manufacturer={quoteattr(MAKER)} '
        f'Description={quoteattr(NOTE)} FixtureTypeID="{_uuid(file_name)}" '
        'Thumbnail="" RefFT="" CanHaveChildren="No">',
        "    <AttributeDefinitions>",
        "      <ActivationGroups/>",
        '      <FeatureGroups><FeatureGroup Name="Control" Pretty="Control">'
        '<Feature Name="Control"/></FeatureGroup></FeatureGroups>',
        "      <Attributes>",
    ]
    out.extend(
        f'        <Attribute Name={quoteattr(a)} Pretty={quoteattr(a)} Feature="Control.Control"/>'
        for a in attributes
    )
    out += [
        "      </Attributes>",
        "    </AttributeDefinitions>",
        "    <Wheels/>",
        "    <PhysicalDescriptions/>",
        "    <Models/>",
        "    <Geometries>",
        '      <Geometry Name="Base"><Axis Name="Yoke"><Axis Name="Head">'
        '<Beam Name="Beam"/></Axis></Axis></Geometry>',
        "    </Geometries>",
        "    <DMXModes>",
    ]
    for mode_name, channels in modes:
        out.append(f'      <DMXMode Name={quoteattr(mode_name)} Geometry="Base">')
        out.append("        <DMXChannels>")
        for offset, attribute, low, high in channels:
            width = len(offset.split(","))
            geometry = "Yoke" if attribute == "Pan" else "Head" if attribute == "Tilt" else "Beam"
            out.append(
                f'          <DMXChannel DMXBreak="1" Offset="{offset}" Highlight="None" Geometry="{geometry}">'
            )
            out.append(f'            <LogicalChannel Attribute={quoteattr(attribute)} Snap="No" Master="None">')
            out.append(
                f'              <ChannelFunction Name={quoteattr(attribute)} Attribute={quoteattr(attribute)} '
                f'DMXFrom="0/{width}" Default="0/{width}" PhysicalFrom="{low:g}" PhysicalTo="{high:g}"/>'
            )
            out.append("            </LogicalChannel>")
            out.append("          </DMXChannel>")
        out.append("        </DMXChannels>")
        out.append("      </DMXMode>")
    out += ["    </DMXModes>", "  </FixtureType>", "</GDTF>", ""]
    return "\n".join(out)


def _zip(members: Sequence[Tuple[str, bytes]]) -> bytes:
    """A ZIP that is the same bytes on every machine: stored, fixed dates."""
    return deterministic_zip(members)


def gdtf_bytes(file_name: str = f"{MAKER}@Demo Spot 16ch.gdtf") -> bytes:
    return _zip([("description.xml", gdtf_description(file_name).encode("utf-8"))])


# ---------------------------------------------------------------------------
# MVR
# ---------------------------------------------------------------------------

def _matrix(x: float, y: float, z: float) -> str:
    """An unturned MVR matrix at a Z-up point given in metres."""
    return (
        "{1.000000,0.000000,0.000000}{0.000000,1.000000,0.000000}{0.000000,0.000000,1.000000}"
        f"{{{x * 1000:.6f},{y * 1000:.6f},{z * 1000:.6f}}}"
    )


def _absolute(spec: FixtureSpec) -> int:
    """A console's absolute address: universes from 1, 512 channels each."""
    return spec.universe * 512 + spec.dmx_address


def mvr_fixtures(venue: VenuePreset) -> List[FixtureSpec]:
    """The preset fixtures the sample MVR holds, in the order it writes them."""
    return _by_group(venue, "Dance Floor Spots", "Mezzanine Spots", "Dome Centre Washes", "Booth Wash")


def mvr_scene() -> str:
    """The GeneralSceneDescription.xml of the sample MVR."""
    venue = preset()
    numbers = sheet_numbers(venue)
    classes = ["Dance Floor Spots", "Mezzanine Spots", "Dome Centre Washes", "Booth Wash"]
    chords = ["a", "b", "c", "d"]

    def fixture(spec: FixtureSpec, relative_to: Tuple[float, float, float], indent: str,
                position: str = "", address_as_text: bool = False) -> List[str]:
        gdtf, mode = MVR_SPECS.get(spec.fixture_type, (MISSING_GDTF_SPEC, "12ch"))
        zx, zy, zz = stage_to_z_up(spec.x, spec.y, spec.z)
        local = (zx - relative_to[0], zy - relative_to[1], zz - relative_to[2])
        address = f"{spec.universe + 1}.{spec.dmx_address}" if address_as_text else str(_absolute(spec))
        lines = [
            f'{indent}<Fixture name={quoteattr(spec.name)} uuid="{_uuid("fixture " + spec.id)}">',
            f"{indent}  <Matrix>{_matrix(*local)}</Matrix>",
            f'{indent}  <Classing>{_uuid("class " + spec.group)}</Classing>',
            f"{indent}  <GDTFSpec>{gdtf}</GDTFSpec>",
            f"{indent}  <GDTFMode>{mode}</GDTFMode>",
        ]
        if position:
            lines.append(f'{indent}  <Position>{_uuid("position " + position)}</Position>')
        lines += [
            f"{indent}  <FixtureID>{numbers[spec.id]}</FixtureID>",
            f"{indent}  <FixtureIDNumeric>{numbers[spec.id]}</FixtureIDNumeric>",
            f"{indent}  <UnitNumber>0</UnitNumber>",
            f'{indent}  <Addresses><Address break="0">{address}</Address></Addresses>',
            f"{indent}</Fixture>",
        ]
        return lines

    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<GeneralSceneDescription verMajor="1" verMinor="6" provider="Intelligent Lighting System" '
        'providerVersion="import sample">',
        f"  <!-- {NOTE} -->",
        "  <Scene>",
        "    <AUXData>",
    ]
    out.extend(f'      <Class uuid="{_uuid("class " + c)}" name={quoteattr(c)}/>' for c in classes)
    out.extend(
        f'      <Position uuid="{_uuid("position Chord " + c.upper())}" name="Chord {c.upper()}"/>'
        for c in chords
    )
    out += ["    </AUXData>", "    <Layers>"]

    # The spots hang under four trusses. Each truss is placed in the room and
    # its fixtures are placed along it, so a reader has to compose the two.
    out.append(f'      <Layer name="Dance Floor Rig" uuid="{_uuid("layer floor")}">')
    out.append("        <ChildList>")
    for chord in chords:
        members = [f for f in _by_group(venue, "Dance Floor Spots") if f.id.startswith(f"ds575_{chord}")]
        origin = stage_to_z_up(0.0, members[0].y, members[0].z)
        label = f"Chord {chord.upper()}"
        out.append(f'          <Truss name="{label}" uuid="{_uuid("truss " + chord)}">')
        out.append(f"            <Matrix>{_matrix(*origin)}</Matrix>")
        out.append("            <ChildList>")
        for spec in members:
            out.extend(fixture(spec, origin, "              ", position=label))
        out.append("            </ChildList>")
        out.append("          </Truss>")
    out += ["        </ChildList>", "      </Layer>"]

    # The mezzanine spots are in a group that carries their height and depth.
    mezzanine = _by_group(venue, "Mezzanine Spots")
    origin = stage_to_z_up(0.0, mezzanine[0].y, mezzanine[0].z)
    out.append(f'      <Layer name="Mezzanine" uuid="{_uuid("layer mezzanine")}">')
    out.append("        <ChildList>")
    out.append(f'          <GroupObject name="Mezzanine Soffit" uuid="{_uuid("group mezzanine")}">')
    out.append(f"            <Matrix>{_matrix(*origin)}</Matrix>")
    out.append("            <ChildList>")
    for spec in mezzanine:
        out.extend(fixture(spec, origin, "              "))
    out += ["            </ChildList>", "          </GroupObject>", "        </ChildList>", "      </Layer>"]

    out.append(f'      <Layer name="Dome Centre" uuid="{_uuid("layer dome")}">')
    out.append("        <ChildList>")
    for spec in _by_group(venue, "Dome Centre Washes"):
        out.extend(fixture(spec, (0.0, 0.0, 0.0), "          "))
    out += ["        </ChildList>", "      </Layer>"]

    # Their GDTF is not in the archive, and one address is written as text.
    out.append(f'      <Layer name="Booth" uuid="{_uuid("layer booth")}">')
    out.append("        <ChildList>")
    for index, spec in enumerate(_by_group(venue, "Booth Wash")):
        out.extend(fixture(spec, (0.0, 0.0, 0.0), "          ", address_as_text=index == 1))
    out += ["        </ChildList>", "      </Layer>"]

    out += ["    </Layers>", "  </Scene>", "</GeneralSceneDescription>", ""]
    return "\n".join(out)


def mvr_bytes() -> bytes:
    members = [("GeneralSceneDescription.xml", mvr_scene().encode("utf-8"))]
    members.extend((name, gdtf_bytes(name)) for name in GDTF_PROFILES)
    return _zip(members)


# ---------------------------------------------------------------------------
# grandMA2
# ---------------------------------------------------------------------------

MA2_LAYERS = ("Mezzanine Spots", "Dome Centre Washes", "Strobes")


def ma2_fixtures(venue: VenuePreset) -> List[FixtureSpec]:
    return _by_group(venue, *MA2_LAYERS)


def ma2_xml() -> str:
    """A grandMA2-style export of three fixture layers."""
    venue = preset()
    numbers = sheet_numbers(venue)
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<MA xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns="http://schemas.malighting.de/grandma2/xml/MA" major_vers="3" minor_vers="9" stream_vers="0">',
        f"  <!-- {NOTE} -->",
        '  <Info datetime="2026-01-01T00:00:00" showfile="liv_approx_subset"/>',
    ]
    type_numbers: Dict[str, int] = {}
    for layer_index, layer in enumerate(MA2_LAYERS, start=1):
        out.append(f'  <Layer index="{layer_index}" name={quoteattr(layer)}>')
        for index, spec in enumerate(_by_group(venue, layer)):
            type_number = type_numbers.setdefault(spec.model, len(type_numbers) + 2)
            x, y, z = stage_to_z_up(spec.x, spec.y, spec.z)
            out += [
                f'    <Fixture index="{index}" name={quoteattr(spec.name)} fixture_id="{numbers[spec.id]}">',
                f'      <FixtureType name={quoteattr(f"{type_number} {spec.model}")}><No>{type_number}</No></FixtureType>',
                '      <SubFixture index="0" react_to_grandmaster="true" color="ffffff">',
                f"        <Patch><Address>{_absolute(spec)}</Address></Patch>",
                "        <AbsolutePosition>",
                f'          <Location x="{x:g}" y="{y:g}" z="{z:g}"/>',
                '          <Rotation x="0" y="0" z="0"/>',
                '          <Scaling x="1" y="1" z="1"/>',
                "        </AbsolutePosition>",
                "      </SubFixture>",
                "    </Fixture>",
            ]
        out.append("  </Layer>")
    out += ["</MA>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

CSV_GROUPS = ("Dome Rim", "Wall Pars", "Staircase Pars")
CSV_COLUMNS = ["FID", "Label", "Fixture Type", "Mode", "Footprint", "Patch", "Position", "X", "Y", "Z", "Group"]


def csv_fixtures(venue: VenuePreset) -> List[FixtureSpec]:
    return _by_group(venue, *CSV_GROUPS)


def csv_text() -> str:
    """A patch list laid out the way a console's is, not the way this system exports one.

    Universes count from 1. The address is written three ways in turn: "3.1",
    "3/13" and as one absolute number. The staircase pars have a named position
    and no coordinates, so they import unplaced.
    """
    venue = preset()
    numbers = sheet_numbers(venue)
    out = io.StringIO()
    out.write(f"# LIV approximate demo subset - console-style patch list\n# {NOTE}\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for index, spec in enumerate(csv_fixtures(venue)):
        style = index % 3
        if style == 0:
            patch = f"{spec.universe + 1}.{spec.dmx_address}"
        elif style == 1:
            patch = f"{spec.universe + 1}/{spec.dmx_address}"
        else:
            patch = str(_absolute(spec))
        placed = spec.group != "Staircase Pars"
        width = channel_count(spec.fixture_type)
        writer.writerow([
            numbers[spec.id], spec.name, spec.model, f"{width}ch", width, patch,
            spec.group if not placed else "",
            f"{spec.x:.2f}" if placed else "",
            f"{spec.y:.2f}" if placed else "",
            f"{spec.z:.2f}" if placed else "",
            spec.group,
        ])
    return out.getvalue()


def sample_files() -> Dict[str, bytes]:
    """Every sample, by the file name it is committed under."""
    return {
        MVR_FILE: mvr_bytes(),
        MA2_FILE: ma2_xml().encode("utf-8"),
        CSV_FILE: csv_text().encode("utf-8"),
        GDTF_FILE: gdtf_bytes(),
    }
