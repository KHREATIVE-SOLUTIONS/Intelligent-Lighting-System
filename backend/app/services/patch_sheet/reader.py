"""
Reading a patch sheet
=====================

A patch sheet is a list of fixtures and addresses with, usually, nothing about
where anything hangs. It arrives as a CSV, a spreadsheet, a PDF printed from a
console, or a photo of that printout. Whatever it was, it comes out of here as
the same ParsedVenue the venue importer produces, read by the same header
matching and address rules (venue_import.csv_patch).

The contents decide what the file is; the name is only a hint.

    csv    comma, semicolon, tab or bar separated text
    xlsx   a spreadsheet, read with the standard library
    text   a table in plain text, columns kept apart by spaces
    pdf    the same, once a local PDF reader has pulled the text out
    image  the same, once a local OCR engine has read the photo

An MVR, a GDTF or a console XML export is not a patch sheet. Those carry
positions of their own and go to POST /api/import/venue.
"""

import io
import zipfile
from typing import List, Optional

from app.services.venue_import.csv_patch import (
    decode,
    find_header_row,
    header_columns,
    parse_csv_patch,
    parse_patch_rows,
    separator_of,
)
from app.services.venue_import.model import ParsedVenue, VenueImportError

from .extract import image_text, pdf_text
from .text_table import read_text_table, skipped_warning
from .xlsx import Sheet, read_xlsx

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic")
OLD_SPREADSHEET_EXTENSIONS = (".xls", ".ods", ".numbers")
MAX_CELLS_LISTED = 8

NOT_A_PATCH_SHEET = (
    "This is a venue file with positions of its own (MVR, GDTF or a console XML export), "
    "not a patch sheet. Import it with the venue importer (POST /api/import/venue)."
)


def _extension(filename: str) -> str:
    name = (filename or "").lower().strip()
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""


def _is_image(content: bytes) -> bool:
    return (
        content[:8] == b"\x89PNG\r\n\x1a\n"
        or content[:3] == b"\xff\xd8\xff"
        or content[:6] in (b"GIF87a", b"GIF89a")
        or content[:2] == b"BM"
        or content[:4] in (b"II*\x00", b"MM\x00*")
        or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")
    )


def detect_kind(filename: str, content: bytes) -> str:
    """One of "csv", "xlsx", "pdf", "image", "text".

    "text" means plain text whose layout is still to be worked out: separated
    values, a ruled table or aligned columns. Raises
    VenueImportError for an empty file and for a file that is not a patch sheet.
    """
    if not content or not content.strip():
        raise VenueImportError("The file is empty.")
    extension = _extension(filename)

    if content[:5] == b"%PDF-":
        return "pdf"
    if content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = [name.lower() for name in zf.namelist()]
        except zipfile.BadZipFile:
            raise VenueImportError("The file looks like a ZIP archive but cannot be opened.")
        if any(name.startswith("xl/") for name in names):
            return "xlsx"
        leaves = [name.rsplit("/", 1)[-1] for name in names]
        if "generalscenedescription.xml" in leaves or "description.xml" in leaves:
            raise VenueImportError(NOT_A_PATCH_SHEET)
        raise VenueImportError("The archive is not a spreadsheet (.xlsx).")
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or extension in OLD_SPREADSHEET_EXTENSIONS:
        raise VenueImportError(
            f"{extension or 'This spreadsheet format'} is not read. Save the sheet as .xlsx or CSV."
        )
    if extension == ".xlsx":
        raise VenueImportError("The file is named .xlsx but is not a spreadsheet.")
    if _is_image(content) or extension in IMAGE_EXTENSIONS:
        return "image"
    if extension == ".pdf":
        raise VenueImportError("The file is named .pdf but is not a PDF.")
    if decode(content[:4096]).lstrip().startswith("<"):
        raise VenueImportError(NOT_A_PATCH_SHEET)
    return "csv" if extension in (".csv", ".tsv") else "text"


def _decimal_address_warning(sheet: Sheet) -> Optional[str]:
    """What to say about address cells a spreadsheet stored as decimal numbers.

    2.100 typed into a number cell is kept as 2.1, and 2.1 is universe 2
    channel 1. Which was meant cannot be told from the file.
    """
    score, header_index = find_header_row(sheet.rows)
    if score < 2:
        return None
    column = header_columns(sheet.rows[header_index]).get("address")
    if column is None:
        return None
    suspect: List[str] = []
    for index, row in enumerate(sheet.rows[header_index + 1:], start=header_index + 1):
        if (index, column) not in sheet.numeric or column >= len(row):
            continue
        whole, _, fraction = row[column].partition(".")
        if fraction and len(fraction) < 3:
            suspect.append(row[column])
    if not suspect:
        return None
    shown = ", ".join(suspect[:MAX_CELLS_LISTED]) + ("..." if len(suspect) > MAX_CELLS_LISTED else "")
    return (
        f"{len(suspect)} address(es) are stored in the spreadsheet as decimal numbers ({shown}). "
        "A number cell drops trailing zeros, so 2.100 and 2.1 are the same cell; each was read "
        "as universe.channel exactly as stored. Check these, or format the column as text."
    )


def _from_text(text: str, filename: str, kind: str, universe_base: str, up_axis: str) -> ParsedVenue:
    table = read_text_table(text)
    parsed = parse_patch_rows(table.rows, filename, format=kind, universe_base=universe_base, up_axis=up_axis)
    warning = skipped_warning(table)
    if warning:
        parsed.warnings.append(warning)
    return parsed


def read_patch_sheet(
    filename: str,
    content: bytes,
    universe_base: str = "auto",
    up_axis: str = "y",
) -> ParsedVenue:
    """Read an uploaded patch sheet in whichever form it is.

    Raises VenueImportError when it is none of them or holds no patch table.
    """
    kind = detect_kind(filename, content)

    if kind == "xlsx":
        sheet = read_xlsx(content)
        parsed = parse_patch_rows(sheet.rows, filename, format="xlsx", universe_base=universe_base, up_axis=up_axis)
        parsed.assumptions.append(f"The patch was read from the worksheet '{sheet.name}'.")
        warning = _decimal_address_warning(sheet)
        if warning:
            parsed.warnings.append(warning)
        return parsed

    if kind == "pdf":
        parsed = _from_text(pdf_text(content), filename, "pdf", universe_base, up_axis)
        parsed.assumptions.append(
            "The table was rebuilt from the PDF's text by lining each value up under its column heading."
        )
        return parsed

    if kind == "image":
        parsed = _from_text(image_text(content), filename, "image", universe_base, up_axis)
        parsed.warnings.append(
            "This patch was read off a photo by OCR. Check every address against the sheet "
            "before the rig is used: a misread digit patches a fixture on the wrong channels."
        )
        return parsed

    if kind == "csv":
        return parse_csv_patch(content, filename, universe_base=universe_base, up_axis=up_axis)

    # Plain text of unknown layout. Commas or semicolons make it separated
    # values. Bars, tabs and aligned columns go to the table reader, which
    # knows a Markdown table's rule line and outer bars are not cells.
    text = decode(content)
    if separator_of(text) in (",", ";"):
        return parse_csv_patch(content, filename, universe_base=universe_base, up_axis=up_axis)
    return _from_text(text, filename, "text", universe_base, up_axis)
