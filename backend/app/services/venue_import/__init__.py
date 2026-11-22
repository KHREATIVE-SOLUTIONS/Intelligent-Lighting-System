"""
Venue Import
============

Reads what a venue already has - a spreadsheet patch list, a GDTF, an MVR, a
grandMA2 export - into one shape, reports what it found before anything is
written, and can then create a new rig from it.

    parsed  = read_venue_file(filename, content)        # detect.py, pure
    preview = build_preview(parsed, library_entries)    # preview.py, pure
    result  = await apply_import(db, parsed, ...)       # apply.py, writes a new rig
"""

from .detect import detect_format, read_venue_file
from .model import ImportedFixture, ParsedVenue, VenueImportError
from .preview import build_preview

__all__ = [
    "ImportedFixture",
    "ParsedVenue",
    "VenueImportError",
    "build_preview",
    "detect_format",
    "read_venue_file",
]
