"""
MVR export
==========

An MVR (My Virtual Rig, DIN SPEC 15801) archive for MA3D, Capture and anything
else that reads one: a GeneralSceneDescription.xml, version 1.6, and the GDTF
files this system can supply.

    <GeneralSceneDescription verMajor="1" verMinor="6" ...>
      <UserData>
        <Data provider="Intelligent Lighting System" ver="1"> ... </Data>
      </UserData>
      <Scene>
        <AUXData>
          <Class uuid="..." name="Dance Floor Spots"/>
        </AUXData>
        <Layers>
          <Layer name="Dance Floor Spots" uuid="...">
            <ChildList>
              <Fixture name="Design Spot A1" uuid="...">
                <Matrix>{u}{v}{w}{o}</Matrix>
                <Classing>...</Classing>
                <GDTFSpec>ILS Demo@Demo Spot 16ch.gdtf</GDTFSpec>
                <GDTFMode>Standard 16ch</GDTFMode>
                <Addresses><Address break="0">1</Address></Addresses>
                <FixtureID>1</FixtureID>

Matrix is MVR's four vectors: the fixture's X, Y and Z axes written in the
scene's axes, then its origin in millimetres. Right-handed, Z up. Every fixture
is a direct child of its layer, so its matrix is its place in the room and no
reader has to compose anything. Address is absolute, counted from 1 (universe 2
address 1 is 513), on break 0.

A fixture can be in one layer and one class, so the group the patch sheet shows
is its layer and its class. Every other group, and the list of fixtures whose
position is unconfirmed, is in the UserData block, which is where the format
lets an application keep what the format has no element for.
"""

from typing import Dict, List, Tuple
from xml.sax.saxutils import escape, quoteattr

from app.services.fixture_library.stage_axes import (
    matrix_to_columns,
    stage_rotation_matrix,
    stage_rotation_to_z_up,
    stage_to_z_up,
)

from .archive import deterministic_zip
from .ma2 import _comment, display_name, layers
from .model import ExportFixture, ExportRig, stable_uuid

SCENE_FILE = "GeneralSceneDescription.xml"
PROVIDER = "Intelligent Lighting System"
PROVIDER_VERSION = "console export 1"
USER_DATA_VERSION = "1"


def _component(value: float) -> str:
    """Six decimals, and never the "-0.000000" a negated zero would print."""
    return f"{round(float(value), 6) + 0.0:.6f}"


def _vector(values) -> str:
    return "{" + ",".join(_component(v) for v in values) + "}"


def matrix_text(position: Tuple[float, float, float], rotation: Tuple[float, float, float]) -> str:
    """An MVR Matrix for a stage position in metres and stage rotation in degrees."""
    turn = stage_rotation_to_z_up(stage_rotation_matrix(*rotation))
    u, v, w = matrix_to_columns(turn)
    origin = [metres * 1000.0 for metres in stage_to_z_up(*position)]
    return _vector(u) + _vector(v) + _vector(w) + _vector(origin)


def fixture_uuid(rig: ExportRig, fixture: ExportFixture) -> str:
    return stable_uuid(rig.key, "fixture", fixture.key)


def _class_uuid(rig: ExportRig, name: str) -> str:
    return stable_uuid(rig.key, "class", name)


def _user_data(rig: ExportRig) -> List[str]:
    """What MVR has no element for: unconfirmed positions and overlapping groups."""
    uuids: Dict[int, str] = {f.number: fixture_uuid(rig, f) for f in rig.fixtures}
    out = [
        "  <UserData>",
        f'    <Data provider={quoteattr(PROVIDER)} ver="{USER_DATA_VERSION}">',
        f"      <ConsoleExport rig={quoteattr(rig.key)} name={quoteattr(rig.name)}>",
    ]
    if rig.unconfirmed:
        out.append("        <UnconfirmedPositions>")
        out.extend(
            f'          <Member fixture="{uuids[f.number]}" fixtureId="{f.number}"/>'
            for f in rig.unconfirmed
        )
        out.append("        </UnconfirmedPositions>")
    out.append("        <FixtureGroups>")
    for group in rig.groups:
        out.append(f"          <FixtureGroup name={quoteattr(group.name)}>")
        out.extend(
            f'            <Member fixture="{uuids[number]}" fixtureId="{number}"/>'
            for number in group.numbers
        )
        out.append("          </FixtureGroup>")
    out += ["        </FixtureGroups>", "      </ConsoleExport>", "    </Data>", "  </UserData>"]
    return out


def mvr_scene(rig: ExportRig, mark_names: bool = False) -> str:
    """The rig's GeneralSceneDescription.xml."""
    by_layer = layers(rig)
    classes = [name for name in by_layer if any(f.layer for f in by_layer[name])]

    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<GeneralSceneDescription verMajor="1" verMinor="6" provider={quoteattr(PROVIDER)} '
        f"providerVersion={quoteattr(PROVIDER_VERSION)}>",
        f"  <!-- {_comment(rig.name)}: exported by the {PROVIDER}. -->",
    ]
    if rig.disclaimer:
        out.append(f"  <!-- {_comment(rig.disclaimer)} -->")
    missing = rig.missing_gdtf
    if missing:
        out.append(
            "  <!-- GDTF named but not in this archive: " + _comment(", ".join(missing)) + " -->"
        )
    out += _user_data(rig)
    out += ["  <Scene>", "    <AUXData>"]
    out.extend(
        f'      <Class uuid="{_class_uuid(rig, name)}" name={quoteattr(name)}/>' for name in classes
    )
    out += ["    </AUXData>", "    <Layers>"]

    for layer, members in by_layer.items():
        out.append(f'      <Layer name={quoteattr(layer)} uuid="{stable_uuid(rig.key, "layer", layer)}">')
        out.append("        <ChildList>")
        for fixture in members:
            out.append(
                f'          <Fixture name={quoteattr(display_name(fixture, mark_names))} '
                f'uuid="{fixture_uuid(rig, fixture)}">'
            )
            if fixture.position is not None:
                out.append(f"            <Matrix>{matrix_text(fixture.position, fixture.rotation)}</Matrix>")
            if fixture.layer:
                out.append(f"            <Classing>{_class_uuid(rig, fixture.layer)}</Classing>")
            out += [
                f"            <GDTFSpec>{escape(fixture.gdtf_spec)}</GDTFSpec>",
                f"            <GDTFMode>{escape(fixture.mode_name)}</GDTFMode>",
                f'            <Addresses><Address break="0">{fixture.absolute_address}</Address></Addresses>',
                f"            <FixtureID>{fixture.number}</FixtureID>",
                f"            <FixtureIDNumeric>{fixture.number}</FixtureIDNumeric>",
                "            <UnitNumber>0</UnitNumber>",
                "            <FixtureTypeId>0</FixtureTypeId>",
                "            <CustomId>0</CustomId>",
                "          </Fixture>",
            ]
        out += ["        </ChildList>", "      </Layer>"]

    out += ["    </Layers>", "  </Scene>", "</GeneralSceneDescription>", ""]
    return "\n".join(out)


def mvr_bytes(rig: ExportRig, mark_names: bool = False) -> bytes:
    """The rig as an .mvr: the scene, then every GDTF there is a file for."""
    members = [(SCENE_FILE, mvr_scene(rig, mark_names).encode("utf-8"))]
    members.extend((name, rig.gdtf_files[name]) for name in sorted(rig.gdtf_files))
    return deterministic_zip(members)
