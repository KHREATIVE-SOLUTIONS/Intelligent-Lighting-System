"""
Tables in Plain Text
====================

A patch list that arrives as text - lifted out of a PDF, read off a photo, or
pasted into a .txt - has no cells, only lines. This turns those lines back
into rows.

Two layouts are read:

- Ruled: cells separated by a bar or a tab ("| 101 | Spot 1 | ..."), which is
  how a Markdown table and a tab-separated paste look.
- Aligned: columns kept apart by runs of two or more spaces, the way a PDF
  prints a table. The header row gives each column its place across the line,
  and a piece of text belongs to the column it sits under.

An empty cell is the trap. Splitting an aligned line on white space alone
moves every later cell one column to the left, which would patch a fixture at
its channel count. So a line is only trusted when it has one piece per column,
or when each piece sits under exactly one header. A line that cannot be lined
up is left out and reported; it is never imported shifted.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.services.venue_import.csv_patch import find_header_row
from app.services.venue_import.model import VenueImportError

MAX_LINES_LISTED = 5

_GAP = re.compile(r"\s{2,}|\t")
_RULE = re.compile(r"^[\s|+:=-]*$")

NO_TABLE = (
    "No patch table was found in the text. It needs a line of column names such as "
    "Name, Type, Universe, Address, with the columns kept apart by two or more spaces, "
    "tabs or bars."
)


@dataclass
class TextTable:
    """Rows read out of text. The first row is the header."""

    rows: List[List[str]] = field(default_factory=list)
    layout: str = "aligned"
    # Lines under the header that looked like table rows and could not be read.
    skipped: List[str] = field(default_factory=list)


def _pieces(line: str) -> List[Tuple[int, int, str]]:
    """(start, end, text) of each run of text in a line, split at wide gaps."""
    pieces: List[Tuple[int, int, str]] = []
    position = 0
    expanded = line.expandtabs(8).rstrip()
    for gap in _GAP.finditer(expanded):
        if gap.start() > position and expanded[position:gap.start()].strip():
            text = expanded[position:gap.start()]
            start = position + (len(text) - len(text.lstrip()))
            pieces.append((start, gap.start(), text.strip()))
        position = gap.end()
    if expanded[position:].strip():
        text = expanded[position:]
        start = position + (len(text) - len(text.lstrip()))
        pieces.append((start, len(expanded), text.strip()))
    return pieces


def _ruled_rows(lines: List[str], bar: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in lines:
        if bar not in line or _RULE.match(line):
            continue
        cells = [cell.strip() for cell in line.split(bar)]
        if bar == "|":
            # A Markdown row opens and closes with a bar.
            if cells and not cells[0]:
                cells = cells[1:]
            if cells and not cells[-1]:
                cells = cells[:-1]
        rows.append(cells)
    return rows


def _place(pieces: List[Tuple[int, int, str]], header: List[Tuple[int, int, str]]) -> Optional[List[str]]:
    """The cells of one aligned line, or None when it cannot be lined up."""
    if len(pieces) == len(header):
        return [text for _, _, text in pieces]
    if len(pieces) > len(header):
        return None

    cells = [""] * len(header)
    for start, end, text in pieces:
        under = [
            index for index, (h_start, h_end, _) in enumerate(header)
            if start < h_end and end > h_start
        ]
        if len(under) != 1 or cells[under[0]]:
            return None
        cells[under[0]] = text
    return cells


def _aligned_table(lines: List[str]) -> Optional[TextTable]:
    split = [_pieces(line) for line in lines]
    score, header_index = find_header_row([[text for _, _, text in pieces] for pieces in split[:200]])
    if score < 2:
        return None
    header = split[header_index]
    header_cells = [text for _, _, text in header]
    table = TextTable(rows=[header_cells], layout="aligned")

    for line, pieces in zip(lines[header_index + 1:], split[header_index + 1:]):
        # One piece is a title, a page number, a note: not a row of a table.
        if len(pieces) < 2 or _RULE.match(line):
            continue
        cells = _place(pieces, header)
        if cells is None:
            table.skipped.append(line.strip())
        else:
            table.rows.append(cells)
    return table


def read_text_table(text: str) -> TextTable:
    """The patch table in a block of text. Raises VenueImportError when there is none."""
    lines = [line for line in (text or "").replace("\x0c", "\n").splitlines() if line.strip()]

    best: Optional[TextTable] = None
    best_score = 1
    for bar in ("|", "\t"):
        rows = _ruled_rows(lines, bar)
        if not rows:
            continue
        score, header_index = find_header_row(rows)
        if score > best_score:
            best, best_score = TextTable(rows=rows[header_index:], layout="ruled"), score

    if best is None:
        best = _aligned_table(lines)
    if best is None:
        raise VenueImportError(NO_TABLE)
    return best


def skipped_warning(table: TextTable) -> Optional[str]:
    """What to tell the operator about the lines that were left out, if any were."""
    if not table.skipped:
        return None
    shown = "; ".join(f"'{line[:80]}'" for line in table.skipped[:MAX_LINES_LISTED])
    more = len(table.skipped) - MAX_LINES_LISTED
    return (
        f"{len(table.skipped)} line(s) of the table could not be lined up with its columns "
        f"and were left out, not guessed at: {shown}" + (f" and {more} more." if more > 0 else ".")
    )
