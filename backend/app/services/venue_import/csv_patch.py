"""
Spreadsheet Patch List
======================

Reads a patch list saved as CSV, whoever laid it out. Headers are matched by
meaning, not by position or exact spelling, so "FID", "Fixture ID" and "Chan"
are one column and "DMX", "Patch" and "Start Address" are another.

parse_csv_patch reads CSV text. parse_patch_rows reads the same sheet when it
is already rows of cells, which is how app.services.patch_sheet hands over a
spreadsheet or a table lifted out of a PDF. The venue importer itself still
takes CSV only and answers an .xlsx with "Save As CSV".

What needs saying about the numbers:

- An address written with its universe ("2.101", "2/101", "2:101") or as one
  absolute number past 512 (613) is console style, where universes count from 1.
  Both of those are universe 1 here, address 101.
- A separate Universe column is ambiguous: consoles count from 1, this system
  and its own exports count from 0. Left on auto, a column that contains a 0 is
  taken as counting from 0 and any other as counting from 1. The report always
  says which was used; universe_base overrides it.
- X / Y / Z are metres. They are taken in this system's axes (Y up) unless
  up_axis says the sheet is Z-up.
- A lone "Position" column is the name of where the fixture hangs. It is kept
  as a label and the fixture stays unplaced, unless the cell holds three numbers.
"""

import csv
import io
import re
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.fixture_library import stage_axes

from .model import DMX_UNIVERSE_SIZE, ImportedFixture, ParsedVenue, VenueImportError, split_absolute_address

DELIMITERS = (",", ";", "\t", "|")
HEADER_SEARCH_ROWS = 40

# Field -> the headers that mean it, already normalised (see _normalise).
HEADER_ALIASES: Dict[str, Sequence[str]] = {
    "number": ("number", "no", "num", "#", "nr", "unit", "unit number", "unit no"),
    "fixture_id": (
        "fixture id", "fixtureid", "fid", "fix id", "id", "channel", "chan", "ch",
        "channel id", "chan id", "fixture number", "fixture no", "fixture #",
    ),
    "name": ("name", "label", "fixture name", "purpose", "description", "desc"),
    "manufacturer": ("manufacturer", "make", "mfr", "mfg", "brand", "vendor"),
    "model": ("model", "fixture model", "source fixture", "instrument", "instrument type", "device", "fixture"),
    "type": ("type", "fixture type", "fixturetype", "profile", "library"),
    "mode": ("mode", "dmx mode", "personality", "profile mode"),
    "channel_count": (
        "channels", "channel count", "footprint", "dmx footprint", "chans",
        "num channels", "number of channels", "dmx channels", "ch count",
    ),
    "universe": ("universe", "univ", "uni", "u", "dmx universe", "dmx univ"),
    "address": (
        "address", "addr", "dmx", "dmx address", "dmx addr", "patch", "start address",
        "dmx start", "start", "start addr", "dmx start address", "universe address",
    ),
    "position": ("position", "hang position", "hanging position", "location", "truss", "pos"),
    "x": ("x", "pos x", "position x", "x pos", "x position", "x m", "posx", "x metres", "x meters"),
    "y": ("y", "pos y", "position y", "y pos", "y position", "y m", "posy", "y metres", "y meters"),
    "z": ("z", "pos z", "position z", "z pos", "z position", "z m", "posz", "z metres", "z meters"),
    "rotation_x": ("rotation x", "rot x", "rx", "x rotation", "rotx", "x rot"),
    "rotation_y": ("rotation y", "rot y", "ry", "y rotation", "roty", "y rot"),
    "rotation_z": ("rotation z", "rot z", "rz", "z rotation", "rotz", "z rot"),
    "group": ("group", "group name", "groupname"),
    "groups": ("groups", "classes", "class", "tags"),
    "layer": ("layer",),
    "zone": ("zone",),
}

_FIELD_BY_HEADER: Dict[str, str] = {
    header: field_name for field_name, headers in HEADER_ALIASES.items() for header in headers
}

_COMBINED_ADDRESS = re.compile(r"^(\d+)\s*[./:]\s*(\d+)$")
_TRIPLE = re.compile(
    r"^\(?\s*([-+]?\d+(?:[.]\d+)?)\s*[,;\s]\s*([-+]?\d+(?:[.]\d+)?)\s*[,;\s]\s*([-+]?\d+(?:[.]\d+)?)\s*\)?$"
)


def _normalise(header: str) -> str:
    """A header reduced to what it says: lower case, punctuation gone."""
    text = re.sub(r"[^a-z0-9#]+", " ", (header or "").lower())
    return " ".join(text.split())


def decode(content: bytes) -> str:
    """Text from an upload: UTF-8 with or without a BOM, UTF-16 (Excel's
    "Unicode Text"), or Windows-1252 as the last resort."""
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return content.decode("utf-16", errors="replace")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _integer(text: str) -> Optional[int]:
    """A whole number, including one a spreadsheet wrote as "613.0"."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value == int(value) else None


def _metres(text: str) -> Optional[float]:
    """A coordinate: "1.5", "1,5", "1.5 m"."""
    text = (text or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"\s*(m|metres|meters)$", "", text)
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


NO_HEADER = (
    "No header row was found. A patch list needs a row of column names such as "
    "Name, Type, Universe, Address (or one Patch column like 2.101)."
)


def find_header_row(rows: Sequence[Sequence[str]]) -> Tuple[int, int]:
    """(how many cells were recognised, the row index) of the row that reads best as a header.

    The header is the row, among the first few, in which the most cells are
    recognised.
    """
    best = (0, 0)
    for index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        recognised = len({_FIELD_BY_HEADER[h] for h in map(_normalise, row) if h in _FIELD_BY_HEADER})
        if recognised > best[0]:
            best = (recognised, index)
    return best


def _find_header(text: str) -> Tuple[str, int, List[List[str]]]:
    """(delimiter, header row index, every row) for the layout that reads best.

    Lines that start with '#' are comments. Trying each delimiter and keeping
    the best is what lets a semicolon or tab file through without a setting.
    """
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    best: Tuple[int, int, str, List[List[str]]] = (0, 0, ",", [])
    for delimiter in DELIMITERS:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
        recognised, index = find_header_row(rows)
        if recognised > best[0]:
            best = (recognised, index, delimiter, rows)
    recognised, index, delimiter, rows = best
    if recognised < 2:
        raise VenueImportError(NO_HEADER)
    return delimiter, index, rows


def _columns(header: Sequence[str]) -> Tuple[Dict[str, int], List[str]]:
    """Field -> column index (the first column that means it), and what was not understood."""
    columns: Dict[str, int] = {}
    unknown: List[str] = []
    for index, cell in enumerate(header):
        field_name = _FIELD_BY_HEADER.get(_normalise(cell))
        if field_name is None:
            if cell.strip():
                unknown.append(cell.strip())
            continue
        columns.setdefault(field_name, index)
    return columns, unknown


def header_columns(header: Sequence[str]) -> Dict[str, int]:
    """Field -> column index for a header row, for a reader that needs to know
    which column is which before the rows are parsed."""
    return _columns(header)[0]


def _split_groups(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    separator = ";" if ";" in text else "|" if "|" in text else ","
    seen: List[str] = []
    for part in text.split(separator):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen


def _universe_base(values: List[int], requested: str) -> Tuple[int, str]:
    """(what the first universe is called in this sheet, how that was decided)."""
    if requested in ("0", "1"):
        return int(requested), f"The Universe column was read as counting from {requested}, as asked."
    if any(v == 0 for v in values):
        return 0, (
            "The Universe column contains a 0, so it was read as counting from 0 "
            "(this system's own numbering). Import with universe_base=1 if it is a console's."
        )
    return 1, (
        "The Universe column was read as counting from 1, the way a console numbers them: "
        "its universe 1 is universe 0 here. Import with universe_base=0 if the sheet "
        "already counts from 0."
    )


def read_address(text: str, universe: Optional[int], notes: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """(0-based universe, address) from an address cell and the row's universe, if any.

    `universe` is already 0-based. A combined form in the cell wins over it.
    """
    text = (text or "").strip()
    if not text:
        return universe, None

    combined = _COMBINED_ADDRESS.match(text)
    # "613.0" is a spreadsheet's whole number, not universe 613 channel 0.
    if combined and not (text.count(".") == 1 and int(combined.group(2)) == 0):
        cell_universe, address = int(combined.group(1)), int(combined.group(2))
        if cell_universe < 1 or not 1 <= address <= DMX_UNIVERSE_SIZE:
            notes.append(f"address '{text}' is not a universe from 1 and a channel from 1 to 512")
            return universe, None
        if universe is not None and universe != cell_universe - 1:
            notes.append(
                f"address '{text}' names universe {cell_universe - 1}, the Universe column {universe}; "
                "the address was believed"
            )
        return cell_universe - 1, address

    number = _integer(text)
    if number is None:
        notes.append(f"address '{text}' could not be read")
        return universe, None
    if number < 1:
        return universe, None
    if number <= DMX_UNIVERSE_SIZE:
        return (universe if universe is not None else 0), number

    split = split_absolute_address(number)
    if universe is not None and split is not None and universe != split[0]:
        notes.append(
            f"address {number} is past 512, so it was read as absolute: universe {split[0]}, "
            f"channel {split[1]}, not the Universe column's {universe}"
        )
    return split if split is not None else (universe, None)


def parse_csv_patch(
    content: bytes,
    source_file: str = "",
    universe_base: str = "auto",
    up_axis: str = "y",
) -> ParsedVenue:
    """Read a CSV patch list. Raises VenueImportError when it has no usable header."""
    text = decode(content)
    delimiter, header_index, rows = _find_header(text)

    parsed = ParsedVenue(format="csv", source_file=source_file)
    if delimiter != ",":
        parsed.assumptions.append(
            f"The file is separated by {'tabs' if delimiter == chr(9) else repr(delimiter)}, not commas."
        )
    _read_rows(parsed, rows, header_index, universe_base, up_axis)
    return parsed


def parse_patch_rows(
    rows: Sequence[Sequence[str]],
    source_file: str = "",
    format: str = "csv",
    universe_base: str = "auto",
    up_axis: str = "y",
) -> ParsedVenue:
    """Read a patch list that is already rows of cells: a spreadsheet, a table
    lifted out of a PDF. Every cell is text. Raises VenueImportError when no
    row reads as a header.
    """
    rows = [[str(c) if c is not None else "" for c in row] for row in rows]
    recognised, header_index = find_header_row(rows)
    if recognised < 2:
        raise VenueImportError(NO_HEADER)
    parsed = ParsedVenue(format=format, source_file=source_file)
    _read_rows(parsed, rows, header_index, universe_base, up_axis)
    return parsed


def _read_rows(
    parsed: ParsedVenue,
    rows: List[List[str]],
    header_index: int,
    universe_base: str,
    up_axis: str,
) -> None:
    """Fill `parsed` from the rows under the header at `header_index`."""
    header = rows[header_index]
    columns, unknown = _columns(header)

    if unknown:
        parsed.warnings.append("Columns not used: " + ", ".join(unknown) + ".")
    if "address" not in columns:
        parsed.warnings.append(
            "The sheet has no address column, so nothing in it can be patched."
        )

    def cell(row: List[str], field_name: str) -> str:
        index = columns.get(field_name)
        return row[index].strip() if index is not None and index < len(row) else ""

    body = [row for row in rows[header_index + 1:] if any(c.strip() for c in row)]
    # A header printed again at the top of each page.
    normal_header = [_normalise(c) for c in header]
    body = [row for row in body if [_normalise(c) for c in row] != normal_header]

    base = 0
    if "universe" in columns:
        universes = [u for u in (_integer(cell(row, "universe")) for row in body) if u is not None]
        base, how = _universe_base(universes, universe_base)
        parsed.assumptions.append(how)

    has_xyz = all(axis in columns for axis in ("x", "y", "z"))
    if has_xyz or "position" in columns:
        parsed.assumptions.append(
            "X / Y / Z were read as metres in this system's axes: X across, Y up, Z toward the rear."
            if up_axis != "z" else
            "X / Y / Z were read as metres with Z up. " + stage_axes.AXIS_ASSUMPTION
        )

    empty = 0
    for row in body:
        notes: List[str] = []
        name = cell(row, "name")
        model = cell(row, "model")
        manufacturer = cell(row, "manufacturer")
        type_cell = cell(row, "type")
        address_cell = cell(row, "address")
        if not (name or model or type_cell or address_cell or cell(row, "fixture_id")):
            empty += 1
            continue

        # With a model column beside it, "Type" is the kind of fixture.
        if model:
            type_name = " ".join(part for part in (manufacturer, model) if part)
            category = type_cell
        else:
            type_name = type_cell
            category = ""
            if manufacturer and type_cell and not type_cell.lower().startswith(manufacturer.lower()):
                type_name = f"{manufacturer} {type_cell}"

        universe_cell = cell(row, "universe")
        universe: Optional[int] = None
        if universe_cell:
            raw = _integer(universe_cell)
            if raw is None or raw - base < 0:
                notes.append(f"universe '{universe_cell}' could not be read")
            else:
                universe = raw - base
        universe, address = read_address(address_cell, universe, notes)

        position = None
        position_label = cell(row, "position")
        triple = _TRIPLE.match(position_label)
        coordinates: Optional[Tuple[Optional[float], ...]] = None
        if has_xyz:
            given = tuple(_metres(cell(row, axis)) for axis in ("x", "y", "z"))
            if all(v is not None for v in given):
                coordinates = given
            elif any(v is not None for v in given):
                notes.append("only part of a position was given, so it was left unplaced")
        if coordinates is None and triple:
            coordinates = tuple(float(v) for v in triple.groups())
            position_label = ""
        if coordinates is not None:
            position = (
                stage_axes.z_up_to_stage(*coordinates) if up_axis == "z"
                else tuple(float(v) + 0.0 for v in coordinates)
            )

        rotation = None
        turns = [_metres(cell(row, axis)) for axis in ("rotation_x", "rotation_y", "rotation_z")]
        if any(v is not None for v in turns):
            turns = [v or 0.0 for v in turns]
            rotation = stage_axes.z_up_euler_to_stage(*turns) if up_axis == "z" else tuple(turns)

        fixture_id = cell(row, "fixture_id")
        number = _integer(cell(row, "number"))
        if number is None:
            number = _integer(fixture_id)

        group_name = cell(row, "group")
        groups = [g for g in _split_groups(cell(row, "groups")) if g != group_name]

        parsed.fixtures.append(ImportedFixture(
            name=name,
            fixture_id=fixture_id,
            fixture_number=number,
            type_name=type_name,
            manufacturer=manufacturer,
            model=model,
            category=category,
            mode_name=cell(row, "mode"),
            channel_count=_integer(cell(row, "channel_count")),
            universe=universe if address is not None else None,
            dmx_address=address,
            position=position,
            rotation=rotation,
            position_source="csv" if position is not None else "none",
            position_label=position_label,
            group_name=group_name,
            groups=groups,
            layer=cell(row, "layer"),
            zone=cell(row, "zone"),
            notes=notes,
        ))

    if empty:
        parsed.warnings.append(f"{empty} row(s) had nothing to import and were skipped.")
    if not parsed.fixtures:
        parsed.warnings.append("The sheet has a header but no fixture rows.")
