"""
grandMA2 export
===============

Two files for a grandMA2 desk, both written from an ExportRig.

ma2_xml: a fixture layer export, in the layout the desk's own Export writes and
this system's importer reads back:

    <MA xmlns="http://schemas.malighting.de/grandma2/xml/MA" ...>
      <Layer index="1" name="Dance Floor Spots">
        <Fixture index="0" name="Design Spot A1" fixture_id="1">
          <FixtureType name="2 ILS Demo Spot 16ch"><No>2</No></FixtureType>
          <SubFixture index="0" react_to_grandmaster="true" color="ffffff">
            <Patch><Address>1</Address></Patch>
            <AbsolutePosition>
              <Location x="-6" y="7.5" z="6.5"/>
              <Rotation x="0" y="0" z="0"/>
              <Scaling x="1" y="1" z="1"/>
            </AbsolutePosition>

Address is absolute, counted from 1 across universes. Location is metres and
Rotation degrees, Z up, +Y upstage (stage_axes holds the mapping). One layer per
group the patch sheet shows. A fixture type is named with a number the show must
already hold that type under: the file describes where fixtures go, not what
they are.

ma2_script: plain command-line text that patches, labels and groups fixtures by
fixture id. It creates no fixtures and carries no positions.

Nothing here has been run on a desk. docs/CONSOLE_EXPORT.md says so, and lists
what the operator still has to do.
"""

from typing import Dict, List, Sequence
from xml.sax.saxutils import quoteattr

from app.services.fixture_library.stage_axes import stage_euler_to_z_up, stage_to_z_up

from .model import UNCONFIRMED_GROUP, UNCONFIRMED_SUFFIX, ExportFixture, ExportGroup, ExportRig

# A new grandMA2 show holds its own Dimmer as fixture type 1.
FIRST_TYPE_NUMBER = 2

MA2_NAMESPACE = "http://schemas.malighting.de/grandma2/xml/MA"
# No clock goes into an export: the same rig is the same bytes.
FIXED_DATETIME = "2026-01-01T00:00:00"


def _number(value: float) -> str:
    """A coordinate to a tenth of a millimetre, with no trailing zeros and no -0."""
    text = f"{round(float(value), 4) + 0.0:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _comment(text: str) -> str:
    """Text that can stand inside an XML comment."""
    return " ".join(str(text).replace("--", "- -").split())


def display_name(fixture: ExportFixture, mark_names: bool) -> str:
    return fixture.name + (UNCONFIRMED_SUFFIX if mark_names and fixture.unconfirmed else "")


def type_numbers(rig: ExportRig) -> Dict[str, int]:
    """Fixture type name -> the number it is exported under, in patch order."""
    numbers: Dict[str, int] = {}
    for fixture in rig.fixtures:
        numbers.setdefault(fixture.type_name, len(numbers) + FIRST_TYPE_NUMBER)
    return numbers


def layers(rig: ExportRig) -> Dict[str, List[ExportFixture]]:
    """Layer name -> its fixtures, layers in the order the patch first names them."""
    out: Dict[str, List[ExportFixture]] = {}
    for fixture in rig.fixtures:
        out.setdefault(fixture.layer_name, []).append(fixture)
    return out


def ma2_xml(rig: ExportRig, mark_names: bool = False) -> str:
    """The rig as a grandMA2 fixture layer XML: patch, positions and rotations."""
    types = type_numbers(rig)
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<MA xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns="{MA2_NAMESPACE}" major_vers="3" minor_vers="9" stream_vers="0">',
        f"  <!-- {_comment(rig.name)}: exported by the Intelligent Lighting System. -->",
    ]
    if rig.disclaimer:
        out.append(f"  <!-- {_comment(rig.disclaimer)} -->")
    out.append(
        "  <!-- Fixture types the show must already hold, under these numbers: "
        + _comment("; ".join(f"{number} = {name}" for name, number in types.items()))
        + " -->"
    )
    out.append(f'  <Info datetime="{FIXED_DATETIME}" showfile={quoteattr(rig.file_stem())}/>')

    for layer_index, (layer, members) in enumerate(layers(rig).items(), start=1):
        out.append(f'  <Layer index="{layer_index}" name={quoteattr(layer)}>')
        for index, fixture in enumerate(members):
            type_number = types[fixture.type_name]
            if fixture.unconfirmed:
                out.append("    <!-- position unconfirmed: a generated guess, not checked against the room -->")
            out += [
                f'    <Fixture index="{index}" name={quoteattr(display_name(fixture, mark_names))} '
                f'fixture_id="{fixture.number}">',
                f'      <FixtureType name={quoteattr(f"{type_number} {fixture.type_name}")}>'
                f"<No>{type_number}</No></FixtureType>",
                '      <SubFixture index="0" react_to_grandmaster="true" color="ffffff">',
                f"        <Patch><Address>{fixture.absolute_address}</Address></Patch>",
            ]
            if fixture.position is not None:
                x, y, z = stage_to_z_up(*fixture.position)
                rx, ry, rz = stage_euler_to_z_up(*fixture.rotation)
                out += [
                    "        <AbsolutePosition>",
                    f'          <Location x="{_number(x)}" y="{_number(y)}" z="{_number(z)}"/>',
                    f'          <Rotation x="{_number(rx)}" y="{_number(ry)}" z="{_number(rz)}"/>',
                    '          <Scaling x="1" y="1" z="1"/>',
                    "        </AbsolutePosition>",
                ]
            out += ["      </SubFixture>", "    </Fixture>"]
        out.append("  </Layer>")
    out += ["</MA>", ""]
    return "\n".join(out)


def selection(numbers: Sequence[int]) -> str:
    """Fixture numbers as a grandMA2 selection: "1 Thru 5 + 9 + 12 Thru 14".

    Order is kept, because the order of a selection is the order of the group.
    Only a run that counts up by one is folded into a Thru.
    """
    runs: List[List[int]] = []
    for number in numbers:
        if runs and number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return " + ".join(
        str(first) if first == last else f"{first} + {last}" if last == first + 1 else f"{first} Thru {last}"
        for first, last in runs
    )


def _label(text: str) -> str:
    """A name inside the quotes of a Label command."""
    return " ".join(str(text).replace('"', "'").split())


def script_groups(rig: ExportRig) -> List[ExportGroup]:
    """The rig's groups, then one holding every unconfirmed position."""
    groups = list(rig.groups)
    if rig.unconfirmed:
        groups.append(ExportGroup(UNCONFIRMED_GROUP, tuple(f.number for f in rig.unconfirmed)))
    return groups


def ma2_script(
    rig: ExportRig,
    first_group: int = 1,
    include_patch: bool = True,
    include_groups: bool = True,
    notes: bool = True,
    mark_names: bool = False,
) -> str:
    """Command-line text that patches, labels and groups the rig's fixtures.

    One command a line. Lines starting with '#' are notes for the reader and
    are not commands: pass notes=False for a file that is commands only.

        Assign Fixture 23 At DMX 1.353      patch: universe counted from 1
        Label Fixture 23 "Mezzanine Spot 1"
        ClearSelection
        Fixture 1 Thru 22
        Store Group 1
        Label Group 1 "Dance Floor Spots"

    The fixtures must already be in the show under these ids, on types whose
    footprint matches. Groups are stored from `first_group` up.
    """
    first_group = max(1, int(first_group))
    out: List[str] = []

    def note(text: str = "") -> None:
        if notes:
            out.append(f"# {text}".rstrip())

    note(f"{rig.name}: grandMA2 command-line script")
    note("Exported by the Intelligent Lighting System. Not run on a desk: read before you paste.")
    if rig.disclaimer:
        note(rig.disclaimer)
    note("Lines starting with # are notes, not commands.")
    note("The fixtures must already exist in the show under these fixture ids.")
    for text in rig.notes:
        note(text)

    if include_patch:
        note()
        note(f"Patch and labels: {len(rig.fixtures)} fixtures. grandMA2 counts universes from 1.")
        types = type_numbers(rig)
        for name in types:
            members = [f for f in rig.fixtures if f.type_name == name]
            footprint = members[0].channel_count
            note(
                f"  {name}: {len(members)} fixture(s)"
                + (f", {footprint} channels each" if footprint else "")
                + (f", mode {members[0].mode_name}" if members[0].mode_name else "")
            )
        for fixture in rig.fixtures:
            out.append(f"Assign Fixture {fixture.number} At DMX {fixture.universe + 1}.{fixture.address}")
            out.append(f'Label Fixture {fixture.number} "{_label(display_name(fixture, mark_names))}"')

    if include_groups:
        groups = script_groups(rig)
        note()
        note(
            f"Groups: {len(groups)}, stored at Group {first_group} to "
            f"{first_group + len(groups) - 1}. A group already there is asked about or replaced."
        )
        for index, group in enumerate(groups):
            slot = first_group + index
            out += [
                "ClearSelection",
                f"Fixture {selection(group.numbers)}",
                f"Store Group {slot}",
                f'Label Group {slot} "{_label(group.name)}"',
            ]
        if groups:
            out.append("ClearSelection")

    out.append("")
    return "\n".join(out)
