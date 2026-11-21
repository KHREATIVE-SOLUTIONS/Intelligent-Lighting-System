"""
Demo Venue Patch Sheet
======================

Writes a venue preset out as a patch sheet, in the column order the rig CSV
export uses, so the sheet in docs/ is generated from the preset and cannot
drift from it. scripts/export_demo_patch_sheet.py writes the file; a unit test
holds the committed copy to what this returns.
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
]


def channel_count(fixture_type: str) -> int:
    return CHANNEL_COUNTS.get(fixture_type, BAR_CH_COUNT)


def patch_sheet_csv(preset: VenuePreset) -> str:
    """The preset as a CSV patch sheet, ordered by universe then address.

    Lines starting with '#' are the header: what the sheet is, and for a preset
    modelled on a real room, that it is not that room's patch.
    """
    out = io.StringIO()
    out.write(f"# {preset.display_name} - demo patch sheet\n")
    if preset.disclaimer:
        out.write(f"# {preset.disclaimer}\n")
    universes = sorted({f.universe for f in preset.fixtures})
    out.write(
        f"# {len(preset.fixtures)} fixtures on universe(s) {', '.join(str(u) for u in universes)}. "
        "Every fixture is patched on this system's generic demo profile for its type, "
        "not on the source fixture's own DMX personality.\n"
    )
    out.write(
        f"# Generated from the '{preset.name}' venue preset by "
        "scripts/export_demo_patch_sheet.py - edit the preset, not this file.\n"
    )

    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    ordered = sorted(preset.fixtures, key=lambda f: (f.universe, f.dmx_address))
    for number, f in enumerate(ordered, start=1):
        width = channel_count(f.fixture_type)
        writer.writerow([
            number, f.name, f.model, f.fixture_type,
            f.universe, f.dmx_address, f"Demo generic {width}ch", width,
            f"{f.x:.2f}", f"{f.y:.2f}", f"{f.z:.2f}", f.group or f.fixture_type,
            f.stands_for, f.basis,
        ])
    return out.getvalue()
