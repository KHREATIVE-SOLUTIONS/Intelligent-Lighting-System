"""
Patch Sheet Import
==================

A patch sheet says what each fixture is and where it is patched, and almost
never where it hangs. This package reads one - CSV, spreadsheet, PDF text, or
a photo through local OCR - and, for the fixtures the sheet does not place,
works out a first-guess 3D layout on a stage template so the rig is usable
before anyone has measured anything.

    parsed = read_patch_sheet(filename, content)             # reader.py, pure
    plans, clashes, warnings = plan_import(parsed, library)  # venue_import, pure
    layout = generate_layout(plans, template)                # layout.py, pure
    preview = render_preview(parsed, library, plans, ...)    # venue_import, pure
    result = await apply_import(db, parsed, plans, ...)      # writes a new rig

Every generated position is a guess and says so: position_source "template",
position_confirmed false in the preview, and the tag position_unconfirmed on
the rig fixture. A position the sheet itself gives is kept and never flagged.
"""

from .reader import detect_kind, read_patch_sheet

__all__ = ["detect_kind", "read_patch_sheet"]
