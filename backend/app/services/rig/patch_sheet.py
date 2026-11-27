"""
Printable patch sheet
=====================

One self-contained HTML page an operator prints and takes to the desk: the rig,
a summary line, the patch table one universe per printed page (sorted by
address, the table header repeated on every page), the groups and the Fail and
Warn readiness checks in words. Inline CSS only, no script, no external asset;
every value is HTML-escaped.

`patch_rows()` is the one place a fixture's patch row is worked out: patch.csv
in the handoff pack and this sheet both read it. See docs/HANDOFF_PACK.md.

Universes are counted from 1, as the readiness checks and a console count them.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional, Sequence

from app.services.console_export.model import ExportRig, from_rig
from app.services.rig.readiness import (
    FAIL, OK, WARN, _RANK, _key_id, _truss_names, place_name, readiness,
)

# How the patch names where a fixture stands.
POSITION_CONFIRMED = "confirmed"  # read from a file, or confirmed by a person
POSITION_GUESSED = "guessed"      # a generated layout nobody has checked
POSITION_NONE = "none"            # never placed: no position at all

STATUS_WORDS = {OK: "OK", WARN: "Warn", FAIL: "Fail"}


@dataclass
class PatchRow:
    """One fixture's line in the patch, as patch.csv and the patch sheet print it."""

    number: int
    name: str
    type_name: str
    manufacturer: str
    model: str
    mode: str
    channels: str        # blank when the fixture has no mode: a guessed footprint is never printed
    universe: int        # counted from 1
    address: int
    position_name: str   # blank when it has no position
    x: str
    y: str
    z: str
    position: str        # confirmed, guessed or none
    groups: List[str]
    row_id: Optional[int]


def _position_state(fixture: Any) -> str:
    if fixture.position is None:
        return POSITION_NONE
    return POSITION_GUESSED if fixture.unconfirmed else POSITION_CONFIRMED


def _metres(value: float) -> str:
    return f"{value:.3f}"


def patch_rows(rig: Any, rows: Sequence[Any], export: ExportRig) -> List[PatchRow]:
    """One row per fixture, in the export's (patch) order."""
    by_id = {rf.id: rf for rf in rows}
    trusses = _truss_names(rig, rows)
    out: List[PatchRow] = []
    for f in export.fixtures:
        row_id = _key_id(f.key)
        rf = by_id.get(row_id)
        state = _position_state(f)
        # An unplaced fixture sits at 0,0,0: a place name would call that "Floor".
        place = place_name(rig, rf, trusses) if rf is not None and state != POSITION_NONE else ""
        x, y, z = (_metres(v) for v in f.position) if f.position is not None else ("", "", "")
        out.append(PatchRow(
            number=f.number, name=f.name, type_name=f.type_name, manufacturer=f.manufacturer,
            model=f.model, mode=f.mode_name,
            channels=str(f.channel_count) if f.channel_count is not None else "",
            universe=f.universe + 1, address=f.address, position_name=place,
            x=x, y=y, z=z, position=state, groups=list(f.groups), row_id=row_id,
        ))
    return out


def worst_first(checks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fail, then Warn, then OK; checks of the same status keep their order."""
    return sorted(checks, key=lambda c: -_RANK[c["status"]])


def console_ids(check: Dict[str, Any], numbers: Dict[Optional[int], int]) -> str:
    """A check's fixtures as console fixture ids."""
    ids = [str(numbers.get(i, f"row {i}")) for i in check["fixture_ids"]]
    more = check["fixture_count"] - len(ids)
    return ", ".join(ids) + (f" and {more} more" if more > 0 else "")


_CSS = """
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; color: #000; margin: 12mm; }
h1 { font-size: 16pt; margin: 0 0 2mm; }
h2 { font-size: 12pt; margin: 6mm 0 2mm; }
p.meta { margin: 0 0 2mm; color: #333; }
p.summary { margin: 0 0 4mm; font-weight: bold; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #888; padding: 1mm 1.5mm; text-align: left; vertical-align: top; }
th { background: #e6e6e6; }
td.num { text-align: right; white-space: nowrap; }
tr.guessed td { background: #fff4d6; }
tr.none td { background: #f0f0f0; }
.mark { font-weight: bold; }
ul { margin: 0; padding-left: 5mm; }
li { margin-bottom: 1mm; }
.legend { font-size: 9pt; color: #333; }
@page { size: A4 landscape; margin: 10mm; }
@media print {
  body { margin: 0; font-size: 9pt; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; page-break-inside: avoid; }
  section.universe + section.universe { break-before: page; page-break-before: always; }
  section.after { break-before: page; page-break-before: always; }
}
"""

_HEAD = [
    "Fixture", "Name", "Profile", "Mode", "Ch", "Univ", "Addr", "U.Addr",
    "Position", "X", "Y", "Z", "Placed", "Groups",
]

_PLACED_WORDS = {
    POSITION_CONFIRMED: "confirmed",
    POSITION_GUESSED: "GUESSED - check in the room",
    POSITION_NONE: "none - not placed",
}


def _row_html(r: PatchRow) -> str:
    e = escape
    placed = _PLACED_WORDS[r.position]
    if r.position != POSITION_CONFIRMED:
        placed = f'<span class="mark">{e(placed)}</span>'
    else:
        placed = e(placed)
    # A guessed position name is marked in words too, not by colour alone.
    where = e(r.position_name) + (" (guessed)" if r.position == POSITION_GUESSED and r.position_name else "")
    cells = [
        f'<td class="num">{r.number}</td>',
        f"<td>{e(r.name)}</td>",
        f"<td>{e(r.type_name)}</td>",
        f"<td>{e(r.mode)}</td>",
        f'<td class="num">{e(r.channels)}</td>',
        f'<td class="num">{r.universe}</td>',
        f'<td class="num">{r.address}</td>',
        f'<td class="num">{r.universe}.{r.address:03d}</td>',
        f"<td>{where}</td>",
        f'<td class="num">{e(r.x)}</td>',
        f'<td class="num">{e(r.y)}</td>',
        f'<td class="num">{e(r.z)}</td>',
        f"<td>{placed}</td>",
        f"<td>{e('; '.join(r.groups))}</td>",
    ]
    return (f'<tr class="{r.position}" data-fixture="{r.number}" data-position="{r.position}">'
            + "".join(cells) + "</tr>")


def sorted_rows(rows: Sequence[PatchRow]) -> List[PatchRow]:
    """By universe, then address, then console fixture id (an address clash keeps a stable order)."""
    return sorted(rows, key=lambda r: (r.universe, r.address, r.number))


def patch_sheet_html(
    rig: Any, rows: Sequence[Any], export: ExportRig, report: Dict[str, Any],
    read_at: str, universe: Optional[int] = None,
) -> str:
    """The printable patch sheet. `universe` (counted from 1) prints that universe only;
    the summary, groups and readiness sections always describe the whole rig."""
    e = escape
    every = patch_rows(rig, rows, export)
    shown = sorted_rows(r for r in every if universe is None or r.universe == universe)
    universes = sorted({r.universe for r in every})
    guessed = sum(1 for r in every if r.position == POSITION_GUESSED)
    unplaced = sum(1 for r in every if r.position == POSITION_NONE)
    counts = report["counts"]

    title = f"Patch sheet: {export.name}"
    out: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{e(title)}</title>",
        f"<style>{_CSS}</style>",
        "</head><body>",
        f"<h1>{e(title)}</h1>",
        f'<p class="meta">Generated {e(read_at)} (UTC) from the rig as it was at that moment.'
        + (f" Universe {universe} only." if universe is not None else "") + "</p>",
        '<p class="summary" data-summary>'
        f"{len(every)} fixture(s) in {len(universes)} universe(s)"
        + (f" ({', '.join(str(u) for u in universes)})" if universes else "")
        + f"; {guessed} position(s) guessed, {unplaced} not placed;"
        f" readiness {counts[FAIL]} fail, {counts[WARN]} warn.</p>",
        '<p class="legend">Universes count from 1. X/Y/Z in metres (X across, Y up, -Z upstage). '
        "<b>GUESSED</b> rows stand where a layout guessed and nobody has confirmed it: "
        "check them in the room before focusing.</p>",
    ]

    if not shown:
        out.append('<p data-empty>No fixtures'
                   + (f" in universe {universe}" if universe is not None else "") + ".</p>")
    head = "<thead><tr>" + "".join(f"<th>{h}</th>" for h in _HEAD) + "</tr></thead>"
    for u in sorted({r.universe for r in shown}):
        in_u = [r for r in shown if r.universe == u]
        out.append(f'<section class="universe" data-universe="{u}">')
        out.append(f"<h2>Universe {u} ({len(in_u)} fixture(s))</h2>")
        out.append("<table>" + head + "<tbody>")
        out += [_row_html(r) for r in in_u]
        out.append("</tbody></table></section>")

    out.append('<section class="after" data-groups>')
    out.append("<h2>Groups</h2>")
    groups = export.groups
    if groups:
        out.append("<table><thead><tr><th>Group</th><th>Count</th><th>Fixture ids</th></tr></thead><tbody>")
        for g in groups:
            out.append(f"<tr><td>{e(g.name)}</td><td class=\"num\">{len(g.numbers)}</td>"
                       f"<td>{e(' '.join(str(n) for n in g.numbers))}</td></tr>")
        out.append("</tbody></table>")
    else:
        out.append("<p>No groups.</p>")

    out.append("<h2>Readiness</h2>")
    out.append(f"<p>Overall: <b>{STATUS_WORDS[report['status']]}</b> "
               f"({counts[FAIL]} fail, {counts[WARN]} warn, {counts[OK]} ok).</p>")
    numbers = {r.row_id: r.number for r in every}
    bad = [c for c in worst_first(report["checks"]) if c["status"] in (FAIL, WARN)]
    if bad:
        out.append('<ul data-readiness>')
        for c in bad:
            ids = f" Fixtures: {console_ids(c, numbers)}." if c["fixture_ids"] else ""
            out.append(f"<li><b>{STATUS_WORDS[c['status']]}: {e(c['title'])}</b> - "
                       f"{e(c['message'])}{e(ids)}</li>")
        out.append("</ul>")
    else:
        out.append("<p>No check fails or warns.</p>")
    out.append("</section>")

    if export.disclaimer:
        out.append(f'<p class="legend">{e(export.disclaimer)}</p>')
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def build_patch_sheet(
    rig: Any, rows: Sequence[Any], universe: Optional[int] = None, now: Optional[datetime] = None,
) -> str:
    """The sheet for GET /api/rigs/{id}/patch-sheet. `rows` need `fixture` and `mode` loaded."""
    read_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
    return patch_sheet_html(rig, rows, from_rig(rig, rows), readiness(rig, rows), read_at, universe)
