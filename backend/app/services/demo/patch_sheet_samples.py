"""
Demo Patch Sheet Samples
========================

Writes the example patch sheet the patch sheet importer is shown and tested
with: a festival main stage rig as a console would print it, with fixture IDs,
types, footprints and addresses, and nothing at all about where anything hangs.
That is the case the layout generator exists for.

Everything here is made up for this project. The rig is no festival's, and the
fixture types are this system's own generic demo footprints under the invented
maker "ILS Demo"; none is a manufacturer's product or personality.

    demo_festival_patch_no_positions.csv   84 fixtures on four universes, in
                                           seven runs of consecutive addresses.
                                           The last run starts near the end of
                                           one universe and carries on at the
                                           start of the next.

scripts/build_venue_import_samples.py writes it to backend/tests/fixtures/import/
and a unit test holds the committed copy to what this returns.
"""

import csv
import io
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .import_samples import MAKER

FESTIVAL_FILE = "demo_festival_patch_no_positions.csv"

NOTE = (
    "EXAMPLE DATA. Authored for the Intelligent Lighting System's patch sheet importer. "
    "Not a real festival's patch and not a manufacturer's fixture list."
)

COLUMNS = ["FID", "Label", "Fixture Type", "Mode", "Footprint", "Patch"]
DMX_UNIVERSE_SIZE = 512


@dataclass(frozen=True)
class Run:
    """Fixtures of one type on consecutive addresses, as a console numbers them."""

    first_id: int
    count: int
    label: str
    model: str
    footprint: int
    universe: int      # as the console counts: from 1
    address: int


# What a festival main stage carries, in the order a programmer patches it.
FESTIVAL_RUNS: Tuple[Run, ...] = (
    Run(101, 16, "Spot", "Demo Spot 16ch", 16, 1, 1),
    Run(201, 12, "Wash", "Demo Wash 14ch", 14, 1, 257),
    Run(301, 16, "Compact Spot", "Demo Compact Spot 12ch", 12, 2, 1),
    Run(401, 8, "Strobe", "Demo Strobe 4ch", 4, 2, 201),
    Run(501, 8, "Blinder", "Demo Blinder 2ch", 2, 2, 301),
    Run(601, 12, "LED Bar", "Demo LED Bar 8ch", 8, 3, 1),
    # Eight fit before channel 512; the other four start universe 4.
    Run(701, 12, "Back Wash", "Demo Wash 14ch", 14, 3, 401),
)


def run_patch(run: Run) -> List[Tuple[int, int]]:
    """(console universe, address) of each fixture in a run, rolling onto the
    next universe when one more would not fit."""
    out: List[Tuple[int, int]] = []
    universe, address = run.universe, run.address
    for _ in range(run.count):
        if address + run.footprint - 1 > DMX_UNIVERSE_SIZE:
            universe, address = universe + 1, 1
        out.append((universe, address))
        address += run.footprint
    return out


def festival_rows() -> List[List[str]]:
    rows: List[List[str]] = []
    for run in FESTIVAL_RUNS:
        for index, (universe, address) in enumerate(run_patch(run)):
            rows.append([
                str(run.first_id + index), f"{run.label} {index + 1}", f"{MAKER} {run.model}",
                f"{run.footprint}ch", str(run.footprint), f"{universe}.{address}",
            ])
    return rows


def festival_csv() -> str:
    """The festival patch as CSV. Universes count from 1; no positions, no groups."""
    out = io.StringIO()
    out.write("# Example festival main stage - console patch list, no position information\n")
    out.write(f"# {NOTE}\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(festival_rows())
    return out.getvalue()


def sample_files() -> Dict[str, bytes]:
    """Every sample, by the file name it is committed under."""
    return {FESTIVAL_FILE: festival_csv().encode("utf-8")}
