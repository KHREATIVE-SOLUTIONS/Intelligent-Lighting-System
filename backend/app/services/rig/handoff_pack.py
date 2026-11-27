"""
Venue handoff pack
==================

Everything an operator walks away with to program a rig, as one zip built in
memory (nothing is written to disk, nothing is sent anywhere):

- patch.csv       one row per fixture: console id, name, type, mode, address, place
- groups.csv      every group with its fixture ids in patch order
- readiness.md    the readiness report in words, worst first, with the time it was read
- <rig>_ma2.xml, <rig>_ma2_script.txt, <rig>.mvr   the console exports, from the
  same writers the export routes use (console_export/ma2.py and mvr.py)
- README.txt      what each file is, which positions are guessed, any Fail check,
  and any file that is missing because its writer failed

A writer that fails leaves its file out; the pack is still built and both
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
from app.services.rig.readiness import (
    FAIL, OK, WARN, _RANK, _key_id, _truss_names, place_name, readiness,
)

PATCH_COLUMNS = [
    "fixture_id", "name", "type", "manufacturer", "model", "mode", "channels",
    "universe", "address", "position_name", "x", "y", "z", "position", "groups", "rig_fixture_id",
]
GROUP_COLUMNS = ["group", "fixture_ids"]

# How patch.csv names where a fixture stands.
POSITION_CONFIRMED = "confirmed"  # read from a file, or confirmed by a person
POSITION_GUESSED = "guessed"      # a generated layout nobody has checked
POSITION_NONE = "none"            # never placed: no position at all

_STATUS_WORDS = {OK: "OK", WARN: "Warn", FAIL: "Fail"}


def _position_state(fixture: Any) -> str:
    if fixture.position is None:
        return POSITION_NONE
    return POSITION_GUESSED if fixture.unconfirmed else POSITION_CONFIRMED


def _metres(value: float) -> str:
    return f"{value:.3f}"


def patch_csv(rig: Any, rows: Sequence[Any], export: ExportRig) -> str:
    by_id = {rf.id: rf for rf in rows}
    trusses = _truss_names(rig, rows)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(PATCH_COLUMNS)
    for f in export.fixtures:
        row_id = _key_id(f.key)
        rf = by_id.get(row_id)
        state = _position_state(f)
        # An unplaced fixture sits at 0,0,0: a place name would call that "Floor".
        place = place_name(rig, rf, trusses) if rf is not None and state != POSITION_NONE else ""
        x, y, z = (_metres(v) for v in f.position) if f.position is not None else ("", "", "")
        writer.writerow([
            f.number, f.name, f.type_name, f.manufacturer, f.model, f.mode_name,
            # No mode: the channel count is unknown. A guessed footprint is not written.
            f.channel_count if f.channel_count is not None else "",
            f.universe + 1, f.address, place, x, y, z, state, "; ".join(f.groups),
            row_id if row_id is not None else "",
        ])
    return out.getvalue()


def groups_csv(export: ExportRig) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(GROUP_COLUMNS)
    for group in export.groups:
        writer.writerow([group.name, " ".join(str(n) for n in group.numbers)])
    return out.getvalue()


def worst_first(checks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fail, then Warn, then OK; checks of the same status keep their order."""
    return sorted(checks, key=lambda c: -_RANK[c["status"]])


def _console_ids(check: Dict[str, Any], numbers: Dict[int, int]) -> str:
    ids = [str(numbers.get(i, f"row {i}")) for i in check["fixture_ids"]]
    more = check["fixture_count"] - len(ids)
    return ", ".join(ids) + (f" and {more} more" if more > 0 else "")


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
            lines.append(f"Fixtures: {_console_ids(check, numbers)}.")
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


def _exports(export: ExportRig) -> List[Tuple[str, str, Callable[[], bytes]]]:
    stem = export.file_stem()
    return [
        (f"{stem}_ma2.xml", "grandMA2 fixture layer XML: patch, positions and rotations. Import on the desk.",
         lambda: ma2_xml(export).encode("utf-8")),
        (f"{stem}_ma2_script.txt", "grandMA2 command-line script: patch, labels and groups.",
         lambda: ma2_script(export).encode("utf-8")),
        (f"{stem}.mvr", "MVR for MA3D, Capture or another visualiser: patch, positions, rotations, groups.",
         lambda: mvr_bytes(export)),
    ]


def build_handoff_pack(rig: Any, rows: Sequence[Any], now: Optional[datetime] = None) -> Tuple[bytes, str]:
    """The zip's bytes and its file name. `rows` need `fixture` and `mode` (with channels) loaded."""
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
    for name, what, write in _exports(export):
        try:
            built[name] = write()
            files[name] = what
        except Exception as e:  # noqa: BLE001 - a failed writer leaves its file out, the pack still builds
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
