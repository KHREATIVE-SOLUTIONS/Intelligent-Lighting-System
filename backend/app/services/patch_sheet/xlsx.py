"""
Spreadsheet Rows
================

Reads the cells of an .xlsx workbook with the standard library alone: the file
is a ZIP of XML, and a patch list needs nothing from it but the text of each
cell. No spreadsheet package is a dependency of this system.

What is read: the first worksheet whose rows hold a patch header (or the first
worksheet, if none does), shared and inline strings, numbers, booleans and the
cached result of a formula. What is not: dates, styles, merged cells, charts,
the old binary .xls.

A number comes back as the text a person would have typed, with one loss that
cannot be undone here: a spreadsheet stores 2.100 as the number 2.1. Cells that
were numbers are reported in `numeric`, so the caller can say so where it
matters (an address column).
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.services.fixture_library.xml_safety import local_name, parse_xml
from app.services.venue_import.csv_patch import find_header_row
from app.services.venue_import.model import VenueImportError

# A patch list is small. These refuse a file that is not one before it is unpacked.
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLUMNS = 256

_CELL_REF = re.compile(r"^([A-Za-z]+)(\d+)$")


@dataclass
class Sheet:
    """One worksheet as rows of text."""

    name: str
    rows: List[List[str]] = field(default_factory=list)
    # (row index, column index) of every cell that was stored as a number.
    numeric: Set[Tuple[int, int]] = field(default_factory=set)


def _column_index(letters: str) -> int:
    """"A" -> 0, "Z" -> 25, "AA" -> 26."""
    index = 0
    for letter in letters.upper():
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def _number_text(raw: str) -> str:
    """A stored number as it would be typed: 613 not 613.0, 2.1 not 2.1000000000000001."""
    raw = (raw or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return raw
    if value != value or value in (float("inf"), float("-inf")):
        return raw
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return format(value, ".10g")


def _text_of(element) -> str:
    """The text of a string item: every <t> under it, without phonetic guides."""
    parts: List[str] = []

    def walk(node) -> None:
        name = local_name(node.tag)
        if name == "rPh":
            return
        if name == "t":
            parts.append(node.text or "")
        for child in node:
            walk(child)

    walk(element)
    return "".join(parts)


def _read_member(zf: zipfile.ZipFile, name: str, what: str):
    try:
        return parse_xml(zf.read(name), what)
    except KeyError:
        raise VenueImportError(f"The workbook has no {what} ({name}).")
    except ValueError as e:
        raise VenueImportError(str(e))


def _member(names: Dict[str, str], wanted: str) -> Optional[str]:
    """The archive's own spelling of a member name, whatever its case."""
    return names.get(wanted.lower().lstrip("/"))


def _sheet_members(zf: zipfile.ZipFile, names: Dict[str, str]) -> List[Tuple[str, str]]:
    """(sheet name, archive member) for each worksheet, in workbook order."""
    workbook_name = _member(names, "xl/workbook.xml")
    if workbook_name is None:
        raise VenueImportError("The file is a ZIP archive but not an .xlsx workbook: it has no xl/workbook.xml.")
    workbook = _read_member(zf, workbook_name, "workbook")

    targets: Dict[str, str] = {}
    rels_name = _member(names, "xl/_rels/workbook.xml.rels")
    if rels_name is not None:
        for rel in _read_member(zf, rels_name, "workbook relationships"):
            target = (rel.get("Target") or "").replace("\\", "/")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            targets[rel.get("Id") or ""] = target

    found: List[Tuple[str, str]] = []
    position = 0
    for element in workbook.iter():
        if local_name(element.tag) != "sheet":
            continue
        position += 1
        rel_id = next(
            (value for key, value in element.attrib.items() if local_name(key) == "id"), ""
        )
        target = targets.get(rel_id) or f"xl/worksheets/sheet{position}.xml"
        member = _member(names, target)
        if member is not None:
            found.append((element.get("name") or f"Sheet{position}", member))
    if not found:
        raise VenueImportError("The workbook has no worksheets.")
    return found


def _shared_strings(zf: zipfile.ZipFile, names: Dict[str, str]) -> List[str]:
    member = _member(names, "xl/sharedStrings.xml")
    if member is None:
        return []
    root = _read_member(zf, member, "shared strings")
    return [_text_of(item) for item in root if local_name(item.tag) == "si"]


def _read_sheet(zf: zipfile.ZipFile, name: str, member: str, strings: List[str]) -> Sheet:
    root = _read_member(zf, member, f"worksheet '{name}'")
    sheet = Sheet(name=name)
    cells: Dict[int, Dict[int, str]] = {}

    next_row = 0
    for row in root.iter():
        if local_name(row.tag) != "row":
            continue
        try:
            row_index = int(row.get("r")) - 1 if row.get("r") else next_row
        except ValueError:
            row_index = next_row
        next_row = row_index + 1
        if row_index >= MAX_ROWS:
            raise VenueImportError(f"The worksheet '{name}' has more than {MAX_ROWS} rows.")

        next_column = 0
        for cell in row:
            if local_name(cell.tag) != "c":
                continue
            ref = _CELL_REF.match(cell.get("r") or "")
            column = _column_index(ref.group(1)) if ref else next_column
            next_column = column + 1
            if column >= MAX_COLUMNS:
                continue

            kind = cell.get("t") or "n"
            value = next((c for c in cell if local_name(c.tag) == "v"), None)
            raw = (value.text or "") if value is not None else ""
            text = ""
            if kind == "s":
                try:
                    text = strings[int(raw)]
                except (ValueError, IndexError):
                    text = ""
            elif kind == "inlineStr":
                inline = next((c for c in cell if local_name(c.tag) == "is"), None)
                text = _text_of(inline) if inline is not None else ""
            elif kind == "b":
                text = "TRUE" if raw.strip() == "1" else "FALSE"
            elif kind in ("str", "e"):
                text = raw
            else:
                text = _number_text(raw)
                if text:
                    sheet.numeric.add((row_index, column))
            if text.strip():
                cells.setdefault(row_index, {})[column] = text.strip()

    if cells:
        width = max(max(columns) for columns in cells.values()) + 1
        for row_index in range(max(cells) + 1):
            columns = cells.get(row_index, {})
            sheet.rows.append([columns.get(c, "") for c in range(width)])
    return sheet


def read_xlsx(content: bytes) -> Sheet:
    """The worksheet of an .xlsx that holds the patch, as rows of text.

    Raises VenueImportError when the file is not a workbook that can be read.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise VenueImportError("The file is named as a spreadsheet but cannot be opened as one.")

    with zf:
        if sum(info.file_size for info in zf.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise VenueImportError(
                f"The workbook unpacks to more than {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB."
            )
        names = {name.lower(): name for name in zf.namelist()}
        if _member(names, "xl/workbook.bin") is not None:
            raise VenueImportError("Binary workbooks (.xlsb) are not read. Save the sheet as .xlsx or CSV.")
        members = _sheet_members(zf, names)
        strings = _shared_strings(zf, names)

        best: Optional[Sheet] = None
        best_score = -1
        for name, member in members:
            sheet = _read_sheet(zf, name, member, strings)
            score = find_header_row(sheet.rows)[0] if sheet.rows else -1
            if score > best_score:
                best, best_score = sheet, score
    if best is None or not best.rows:
        raise VenueImportError("The workbook has no cells with anything in them.")
    return best
