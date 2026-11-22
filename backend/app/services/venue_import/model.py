"""
Venue Import Model
==================

What every importer hands back, whatever the file was: a list of fixtures in
one shape, the fixture profiles the file carried, and what the reader had to
assume. Nothing here touches the database.

Conventions, the same as a patched rig:

- universe is 0-based, dmx_address is 1-512.
- position is metres in stage axes (X across, Y up, -Z upstage), or None.
  A fixture with no position is unplaced. An importer never makes one up.
- position_source says where a position came from: mvr, ma2, csv or none.
  "template" is the one source that is not the file: a position worked out by
  the patch sheet layout generator (app.services.patch_sheet). It is a guess at
  where the fixture hangs and stays unconfirmed until someone has checked it.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

POSITION_SOURCES = ("mvr", "ma2", "csv", "none", "template")
# Positions from these sources were generated, not read: nobody has confirmed them.
UNCONFIRMED_POSITION_SOURCES = ("template",)
FORMATS = ("csv", "gdtf", "mvr", "ma2", "xlsx", "pdf", "text", "image")

DMX_UNIVERSE_SIZE = 512


class VenueImportError(ValueError):
    """The file cannot be read as any supported format. The message is for the operator."""


@dataclass
class ImportedFixture:
    """One fixture as the file describes it."""

    name: str = ""
    # The id as the file writes it. Not always a number ("ds575_a1", "101.2").
    fixture_id: str = ""
    fixture_number: Optional[int] = None
    # The make and model the file gives, as one string, and split where the
    # file splits it.
    type_name: str = ""
    manufacturer: str = ""
    model: str = ""
    # A kind of fixture rather than a model ("mover", "led_par"), when the file has one.
    category: str = ""
    mode_name: str = ""
    # The footprint the file states for this fixture, if it states one.
    channel_count: Optional[int] = None
    universe: Optional[int] = None
    dmx_address: Optional[int] = None
    # Addresses beyond the first: other DMX breaks, or a multipatch.
    extra_addresses: List[Tuple[int, int]] = field(default_factory=list)
    position: Optional[Tuple[float, float, float]] = None
    rotation: Optional[Tuple[float, float, float]] = None
    position_source: str = "none"
    # The name of where it hangs ("Truss 2", "FOH"). A label, not coordinates.
    position_label: str = ""
    group_name: str = ""
    groups: List[str] = field(default_factory=list)
    layer: str = ""
    zone: str = ""
    # The embedded GDTF this fixture names, for MVR.
    gdtf_spec: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def unplaced(self) -> bool:
        return self.position is None

    def display_name(self, index: int) -> str:
        return self.name or (f"fixture {self.fixture_id}" if self.fixture_id else f"fixture {index + 1}")


@dataclass
class ParsedVenue:
    """A file, read."""

    format: str
    source_file: str = ""
    fixtures: List[ImportedFixture] = field(default_factory=list)
    # Fixture profiles carried by the file, in the shape parse_gdtf returns,
    # each with "_gdtf_filename" where it came out of an archive.
    profiles: List[Dict[str, Any]] = field(default_factory=list)
    # Named places with a position that are not fixtures: trusses.
    positions: List[Dict[str, Any]] = field(default_factory=list)
    layers: List[str] = field(default_factory=list)
    # What the reader took as given, and what went wrong reading.
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def split_absolute_address(absolute: int) -> Optional[Tuple[int, int]]:
    """(0-based universe, 1-512 address) for an absolute address counted from 1.

    513 is universe 2 address 1 on a console, which is universe 1 here.
    """
    if absolute < 1:
        return None
    return (absolute - 1) // DMX_UNIVERSE_SIZE, (absolute - 1) % DMX_UNIVERSE_SIZE + 1
