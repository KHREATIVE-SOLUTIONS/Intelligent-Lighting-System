"""
Venue handoff pack
==================

Everything an operator walks away with to program a rig, as one zip built in
memory (nothing is written to disk, nothing is sent anywhere):

- patch.csv       one row per fixture: console id, name, type, mode, address, place
- groups.csv      every group with its fixture ids in patch order
- readiness.md    the readiness report in words, worst first, with the time it was read
- patch-sheet.html  the printable patch sheet (services/rig/patch_sheet.py), the same
  rows as patch.csv, one universe per printed page
- focus-presets.csv  every focus target against every moving head (services/focus_presets)
- <rig>_ma2.xml, <rig>_ma2_script.txt, <rig>.mvr   the console exports, from the
  same writers the export routes use (console_export/ma2.py and mvr.py); the
  script carries the focus presets as Position presets
- <rig>_ma2_starter_presets.txt   dimmer, colour and beam presets as grandMA2
  command-line text (console_export/starter_presets.py); left out when the
  caller turns `starter_presets` off
- README.txt      what each file is, which positions are guessed, any Fail check,
  and any file that is missing because its writer failed

A writer that fails (the patch sheet included) leaves its file out; the pack is still built and both
README.txt and readiness.md say which file is missing and why. See
docs/HANDOFF_PACK.md.

Ids: "fixture id" is the console's fixture id (ExportFixture.number), the same
number the MA2 and MVR files in the pack use. Universes are counted from 1, as
the readiness checks and a console count them.
"""

import csv
import io
import zipfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.services.console_export.ma2 import ma2_script, ma2_xml
from app.services.console_export.model import ExportRig, from_rig
from app.services.console_export.mvr import mvr_bytes
from app.services.console_export.starter_presets import build_starter_presets, starter_presets_script
from app.services.focus_presets.table import build_table as build_focus_table, focus_csv
from app.services.rig.patch_sheet import (  # noqa: F401 - POSITION_* and worst_first are re-exported
    POSITION_CONFIRMED, POSITION_GUESSED, POSITION_NONE, STATUS_WORDS as _STATUS_WORDS,
    console_ids, patch_rows, patch_sheet_html, worst_first,
)
from app.services.rig.readiness import FAIL, OK, WARN, _key_id, readiness

PATCH_COLUMNS = [
    "fixture_id", "name", "type", "manufacturer", "model", "mode", "channels",
    "universe", "address", "position_name", "x", "y", "z", "position", "groups", "rig_fixture_id",
]
GROUP_COLUMNS = ["group", "fixture_ids"]
PATCH_SHEET = "patch-sheet.html"
FOCUS_CSV = "focus-presets.csv"


def patch_csv(rig: Any, rows: Sequence[Any], export: ExportRig) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(PATCH_COLUMNS)
    for r in patch_rows(rig, rows, export):
        writer.writerow([
            r.number, r.name, r.type_name, r.manufacturer, r.model, r.mode, r.channels,
            r.universe, r.address, r.position_name, r.x, r.y, r.z, r.position, "; ".join(r.groups),
            r.row_id if r.row_id is not None else "",
        ])
    return out.getvalue()


def groups_csv(export: ExportRig) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(GROUP_COLUMNS)
    for group in export.groups:
        writer.writerow([group.name, " ".join(str(n) for n in group.numbers)])
    return out.getvalue()


def readiness_md(report: Dict[str, Any], export: ExportRig, read_at: str, missing: Dict[str, str]) -> str:
    numbers = {_key_id(f.key): f.number for f in export.fixtures}
    counts = report["counts"]
    lines = [
        f"# Readiness: {report['rig_name']}",
        "",
        f"Read at {read_at} (UTC). Overall: **{_STATUS_WORDS[report['status']]}** "
        f"({counts[FAIL]} fail, {counts[WARN]} warn, {counts[OK]} ok).",
        "",
        "Worst first. Fixture ids are console fixture ids, as in patch.csv and the console files.",
        "",
    ]
    for check in worst_first(report["checks"]):
        lines.append(f"## {_STATUS_WORDS[check['status']]}: {check['title']}")
        lines.append("")
        lines.append(check["message"])
        if check["fixture_ids"]:
            lines.append("")
            lines.append(f"Fixtures: {console_ids(check, numbers)}.")
        lines.append("")
    if missing:
        lines.append("## Missing from this pack")
        lines.append("")
        for name, why in missing.items():
            lines.append(f"- {name}: {why}")
        lines.append("")
    lines.append(f"What each check means: {report['operator_guide']}.")
    return "\n".join(lines) + "\n"


def readme_txt(
    report: Dict[str, Any], export: ExportRig, read_at: str,
    files: Dict[str, str], missing: Dict[str, str],
) -> str:
    guessed = [f for f in export.fixtures if f.position is not None and f.unconfirmed]
    unplaced = [f for f in export.fixtures if f.position is None]
    fails = [c for c in report["checks"] if c["status"] == FAIL]
    lines = [
        f"Venue handoff pack: {export.name}",
        f"Built {read_at} (UTC) from the rig as it was at that moment. Nothing was changed or sent.",
        "",
        "FILES",
    ]
    for name, what in files.items():
        lines.append(f"  {name}")
        lines.append(f"      {what}")
    if missing:
        lines += ["", "MISSING FILES"]
        for name, why in missing.items():
            lines.append(f"  {name}: {why}")
    lines += ["", "POSITIONS"]
    if guessed:
        lines.append(
            f"  {len(guessed)} fixture(s) stand where a layout guessed and nobody has confirmed it "
            "(position = guessed in patch.csv). Check them in the room before focusing."
        )
        lines.append("  Fixture ids: " + ", ".join(str(f.number) for f in guessed))
    if unplaced:
        lines.append(f"  {len(unplaced)} fixture(s) have no position at all (position = none).")
        lines.append("  Fixture ids: " + ", ".join(str(f.number) for f in unplaced))
    if not guessed and not unplaced:
        lines.append("  Every position was read from a file or confirmed by a person.")
    lines += ["", "READINESS"]
    lines.append(f"  Overall: {_STATUS_WORDS[report['status']]}. Full report in readiness.md.")
    if fails:
        lines.append(f"  {len(fails)} check(s) FAIL. Sort them out before programming:")
        for check in fails:
            lines.append(f"  - {check['title']}: {check['message']}")
    else:
        lines.append("  No check fails.")
    if export.notes:
        lines += ["", "EXPORT NOTES"]
        lines += [f"  - {note}" for note in export.notes]
    if export.disclaimer:
        lines += ["", export.disclaimer]
    lines += [
        "",
        "Universes are counted from 1. Positions are metres in this system's stage axes "
        "(X across, Y up, -Z upstage). See docs/HANDOFF_PACK.md and docs/CONSOLE_EXPORT.md.",
    ]
    return "\n".join(lines) + "\n"


def _focus(rig: Any, rows: Sequence[Any], export: ExportRig) -> Tuple[Optional[Any], Optional[str]]:
    """The focus table, or None and why it could not be built (the script then goes without presets)."""
    try:
        return build_focus_table(rig, rows, export), None
    except Exception as e:  # noqa: BLE001 - the presets are left out, the pack still builds
        return None, f"the focus presets stopped with an error: {type(e).__name__}: {e}"


def _exports(export: ExportRig, focus: Optional[Any] = None) -> List[Tuple[str, str, Callable[[], bytes]]]:
    stem = export.file_stem()
    return [
        (f"{stem}_ma2.xml", "grandMA2 fixture layer XML: patch, positions and rotations. Import on the desk.",
         lambda: ma2_xml(export).encode("utf-8")),
        (f"{stem}_ma2_script.txt",
         "grandMA2 command-line script: patch, labels, groups" + (", and focus position presets." if focus else "."),
         lambda: ma2_script(export, focus=focus).encode("utf-8")),
        (f"{stem}.mvr", "MVR for MA3D, Capture or another visualiser: patch, positions, rotations, groups.",
         lambda: mvr_bytes(export)),
    ]


def starter_presets_name(export: ExportRig) -> str:
    return f"{export.file_stem()}_ma2_starter_presets.txt"


def build_handoff_pack(
    rig: Any, rows: Sequence[Any], now: Optional[datetime] = None, starter_presets: bool = True,
) -> Tuple[bytes, str]:
    """The zip's bytes and its file name. `rows` need `fixture` and `mode` (with channels) loaded.

    `starter_presets` adds the grandMA2 dimmer, colour and beam starter presets as their own file.
    """
    read_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
    report = readiness(rig, rows)
    export = from_rig(rig, rows)

    built: Dict[str, bytes] = {}
    files: Dict[str, str] = {
        "README.txt": "This file.",
        "patch.csv": "One row per fixture: console fixture id, name, type, mode, channels, universe "
                     "(from 1), address, position name, x/y/z in metres, position "
                     "(confirmed, guessed or none), groups, and the rig's own row id.",
        "groups.csv": "Every group, with its console fixture ids in patch order, space separated.",
        "readiness.md": "The readiness report in words, worst first, with the time it was read.",
    }
    missing: Dict[str, str] = {}
    try:
        built[PATCH_SHEET] = patch_sheet_html(rig, rows, export, report, read_at).encode("utf-8")
        files[PATCH_SHEET] = ("Printable patch sheet: open in a browser and print. One universe per page, "
                              "sorted by address, guessed positions marked, then groups and readiness.")
    except Exception as e:  # noqa: BLE001 - the sheet is left out, the pack still builds
        missing[PATCH_SHEET] = f"the patch sheet stopped with an error: {type(e).__name__}: {e}"
    focus, focus_error = _focus(rig, rows, export)
    if focus is None:
        missing[FOCUS_CSV] = focus_error or "the focus presets could not be built"
    else:
        try:
            built[FOCUS_CSV] = focus_csv(focus).encode("utf-8")
            files[FOCUS_CSV] = ("Focus position presets: one row per target and moving head, pan and tilt in "
                                "degrees and DMX, reachable or why not, position guessed or confirmed. "
                                "The same presets are in the MA2 script. See docs/FOCUS_PRESETS.md.")
        except Exception as e:  # noqa: BLE001 - the CSV is left out, the pack still builds
            missing[FOCUS_CSV] = f"the writer stopped with an error: {type(e).__name__}: {e}"
    for name, what, write in _exports(export, focus):
        try:
            built[name] = write()
            files[name] = what
        except Exception as e:  # noqa: BLE001 - a failed writer leaves its file out, the pack still builds
            missing[name] = f"the writer stopped with an error: {type(e).__name__}: {e}"
    if starter_presets:
        name = starter_presets_name(export)
        try:
            table = build_starter_presets(rows, export)
            built[name] = starter_presets_script(export, table).encode("utf-8")
            files[name] = ("grandMA2 starter presets: dimmer (Preset 1.x), colour (4.x) and beam (5.x) "
                           "from each fixture's profile channels; who is left out and why is in its notes. "
                           "Paste after the MA2 script. See docs/CONSOLE_EXPORT.md.")
        except Exception as e:  # noqa: BLE001 - the presets are left out, the pack still builds
            missing[name] = f"the writer stopped with an error: {type(e).__name__}: {e}"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("README.txt", readme_txt(report, export, read_at, files, missing))
        pack.writestr("patch.csv", patch_csv(rig, rows, export))
        pack.writestr("groups.csv", groups_csv(export))
        pack.writestr("readiness.md", readiness_md(report, export, read_at, missing))
        for name, content in built.items():
            pack.writestr(name, content)
    return buffer.getvalue(), f"{export.file_stem()}_handoff_pack.zip"
