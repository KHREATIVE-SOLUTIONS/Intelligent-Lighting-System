"""
Demo Venue Patch Sheet
======================

Writes a venue preset out as a patch sheet, so the sheets in docs/ are
generated from the preset and cannot drift from it. The CSV starts with the
columns the rig CSV export uses, in its order; the Markdown sheet is the same
rows laid out to be read. scripts/export_demo_patch_sheet.py writes both files
and a unit test holds the committed copies to what this returns.
"""

import csv
import io
from typing import Dict, List

from .venue_presets import (
    BAR_CH_COUNT,
    MOVER_CH_COUNT,
    SPOT_CH_COUNT,
    STROBE_CH_COUNT,
    WASH_CH_COUNT,
    FixtureSpec,
    VenuePreset,
)

# The footprint each preset fixture type is patched at. Anything unlisted takes
# the bar map, which is what create_venue_rig gives it.
CHANNEL_COUNTS: Dict[str, int] = {
    "mover": MOVER_CH_COUNT,
    "wash": WASH_CH_COUNT,
    "bar": BAR_CH_COUNT,
    "strobe": STROBE_CH_COUNT,
    "spot": SPOT_CH_COUNT,
    "par": BAR_CH_COUNT,
}

COLUMNS: List[str] = [
    "Number", "Name", "Source Fixture", "Type",
    "Universe", "Address", "Mode", "Channels",
    "Position X", "Position Y", "Position Z", "Group",
    "Stands For", "Basis",
    "Fixture ID", "Groups", "Rotation X", "Rotation Y", "Rotation Z",
]

# Between group names in one cell. Not a comma (CSV) or a bar (Markdown table).
GROUP_SEPARATOR = "; "


def channel_count(fixture_type: str) -> int:
    return CHANNEL_COUNTS.get(fixture_type, BAR_CH_COUNT)


def _ordered(preset: VenuePreset) -> List[FixtureSpec]:
    return sorted(preset.fixtures, key=lambda f: (f.universe, f.dmx_address))


def _summary(preset: VenuePreset) -> str:
    universes = sorted({f.universe for f in preset.fixtures})
    return (
        f"{len(preset.fixtures)} fixtures on universe(s) {', '.join(str(u) for u in universes)}. "
        "Every fixture is patched on this system's generic demo profile for its type, "
        "not on the source fixture's own DMX personality."
    )


def _generated_by(preset: VenuePreset) -> str:
    return (
        f"Generated from the '{preset.name}' venue preset by "
        "scripts/export_demo_patch_sheet.py - edit the preset, not this file."
    )


def _degrees(value: float) -> str:
    return f"{value:g}"


def patch_sheet_csv(preset: VenuePreset) -> str:
    """The preset as a CSV patch sheet, ordered by universe then address.

    Lines starting with '#' are the header: what the sheet is, and for a preset
    modelled on a real room, that it is not that room's patch.
    """
    out = io.StringIO()
    out.write(f"# {preset.display_name} - demo patch sheet\n")
    if preset.disclaimer:
        out.write(f"# {preset.disclaimer}\n")
    out.write(f"# {_summary(preset)}\n")
    out.write(f"# {_generated_by(preset)}\n")

    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for number, f in enumerate(_ordered(preset), start=1):
        width = channel_count(f.fixture_type)
        writer.writerow([
            number, f.name, f.model, f.fixture_type,
            f.universe, f.dmx_address, f"Demo generic {width}ch", width,
            f"{f.x:.2f}", f"{f.y:.2f}", f"{f.z:.2f}", f.group or f.fixture_type,
            f.stands_for, f.basis,
            f.id, GROUP_SEPARATOR.join(f.groups),
            _degrees(f.rotation[0]), _degrees(f.rotation[1]), _degrees(f.rotation[2]),
        ])
    return out.getvalue()


def _cell(value) -> str:
    """One Markdown table cell: a bar or a line break would end it early."""
    return str(value).replace("|", "/").replace("\n", " ")


def _table(header: List[str], rows: List[List]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def patch_sheet_markdown(preset: VenuePreset) -> str:
    """The preset as a Markdown patch sheet: universes, groups, then every fixture.

    The same rows as the CSV, in the same order. A preset modelled on a real
    room carries its disclaimer directly under the title.
    """
    ordered = _ordered(preset)
    out = [f"# {preset.display_name} - demo patch sheet\n"]
    if preset.disclaimer:
        out.append(f"**{preset.disclaimer}**\n")
    out.append(f"{_summary(preset)}\n")
    out.append(f"{_generated_by(preset)}\n")

    universes: Dict[int, List[FixtureSpec]] = {}
    for f in ordered:
        universes.setdefault(f.universe, []).append(f)
    out.append("## Universes\n")
    out.append(_table(
        ["Universe", "Fixtures", "Channels used", "Last channel"],
        [
            [
                universe,
                len(members),
                sum(channel_count(f.fixture_type) for f in members),
                max(f.dmx_address + channel_count(f.fixture_type) - 1 for f in members),
            ]
            for universe, members in sorted(universes.items())
        ],
    ))

    if preset.groups:
        out.append("## Groups\n")
        out.append(
            "The names a look selects on. The engine adds its own groups by type "
            "and by position on top of these.\n"
        )
        out.append(_table(
            ["Group", "Fixtures"],
            [[f"`{name}`", len(ids)] for name, ids in preset.groups.items()],
        ))

    out.append("## Patch\n")
    out.append(
        "Positions are metres from the centre of the floor: X across, Y up, "
        "Z toward the rear of the room. Rotation is degrees about X / Y / Z.\n"
    )
    rows = []
    for number, f in enumerate(ordered, start=1):
        width = channel_count(f.fixture_type)
        rows.append([
            number, f"`{f.id}`", f.name,
            f"{f.model} (as generic {f.fixture_type})" if f.model else f"Generic {f.fixture_type}",
            f"Demo generic {width}ch", width, f.universe, f.dmx_address,
            f.group or f.fixture_type, GROUP_SEPARATOR.join(f.groups),
            f"{f.x:.2f}", f"{f.y:.2f}", f"{f.z:.2f}",
            " / ".join(_degrees(v) for v in f.rotation),
        ])
    out.append(_table(
        ["#", "Fixture ID", "Name", "Profile", "Mode", "Channels", "Universe", "Address",
         "Group", "Groups", "X", "Y", "Z", "Rotation"],
        rows,
    ))
    return "\n".join(out)
