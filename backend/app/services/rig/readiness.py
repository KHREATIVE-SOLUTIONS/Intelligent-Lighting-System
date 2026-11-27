"""
Venue readiness
===============

One answer to "can I start programming this rig?": a list of checks, each
ok, warn or fail, in a sentence an operator reads, with the fixtures it is
about. The rig's status is its worst check. See docs/READINESS.md.

Every check is built from what the rest of the system already decides, so
this module never disagrees with the view a check sends the operator to:

- position: the `position_unconfirmed` and `unplaced` tags the importers,
  the patch-sheet layout and flash-and-tap write (venue_import/apply.py);
- addresses: PatchingService.find_conflicts, the same overlap rule
  /patch-conflicts uses, and the programming audit's 1-512 footprint rule;
- profiles: the `unmatched_type` tag and the import's placeholder profile;
- room: the scanned room's box and outline as fixture_position reads them;
- groups: the groups an export writes (console_export.model.from_rig);
- carry-over: room_shell.pending_carry_over (room_scan/pending_carry.py);
- export: the grandMA2 and MVR writers themselves, run in memory.

Reads only. Nothing is written, nothing is sent to a device.

Two fixes plan here and the endpoints write: `plan_auto_groups` (a group for
each position and kind of fixture, for the fixtures that have none) and
`plan_readdress` (a free address for each fixture that clashes). The third,
Locate, is the flash-and-tap walkthrough started with the fixtures the
Positions check names; it has no planner.
"""

import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.console_export.ma2 import ma2_script, ma2_xml
from app.services.console_export.model import ExportRig, from_rig
from app.services.console_export.mvr import mvr_bytes
from app.services.rig.patching_service import (
    MAX_DMX_CHANNELS, NO_MODE_CHANNELS, PatchingService, PatchPlanError, fixture_rows, plan_addresses,
)
from app.services.rig.programming_audit import build_programming_audit
from app.services.room_scan.carry import HANGING_KINDS, hung_fixtures
from app.services.room_scan.pending_carry import pending
from app.services.venue_import.apply import (
    PLACEHOLDER_MANUFACTURER, TAG_UNCONFIRMED, TAG_UNMATCHED, TAG_UNPLACED,
)
from app.services.venue_import.matching import PLACEHOLDER_SOURCE

OK, WARN, FAIL = "ok", "warn", "fail"
_RANK = {OK: 0, WARN: 1, FAIL: 2}

# A check names at most this many fixtures; `fixture_count` has them all.
FIXTURE_IDS_MAX = 50
# A fixture this far past a wall, the floor or the ceiling of the scanned room
# is outside it. Enough for a light hung on the wall itself.
ROOM_TOLERANCE_M = 0.25
FIX_AUTO_GROUPS = "auto-groups"
FIX_READDRESS = "readdress"
FIX_LOCATE = "locate"
HANG_POSITION_PREFIX = "hang_position:"
GROUP_NAME_MAX = 100  # RigFixture.group_name is String(100)

# Kind of fixture -> the word a group of them is called by.
_KIND_WORDS = {
    "moving_head": "Movers",
    "spot": "Spots",
    "wash": "Washes",
    "beam": "Beams",
    "led_par": "Pars",
    "led_bar": "Bars",
    "strobe": "Strobes",
    "laser": "Lasers",
    "effect": "Effects",
    "dimmer": "Dimmers",
}


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------

def _tags(rf: Any) -> List[str]:
    return [t for t in (rf.tags or []) if isinstance(t, str)]


def _label(rf: Any) -> str:
    return (rf.name or "").strip() or f"Fixture {rf.id}"


def _fixtures(n: int) -> str:
    return f"{n} fixture" if n == 1 else f"{n} fixtures"


def _named(rows: Sequence[Any], most: int = 3) -> str:
    """ "Spot 1, Spot 2 and 4 more" for the start of a list of fixtures."""
    names = [_label(rf) for rf in rows[:most]]
    more = len(rows) - len(names)
    if more > 0:
        return ", ".join(names) + f" and {more} more"
    if len(names) > 1:
        return ", ".join(names[:-1]) + " and " + names[-1]
    return names[0] if names else ""


def _check(
    check_id: str,
    title: str,
    status: str,
    message: str,
    fixture_ids: Iterable[int] = (),
    fix: Optional[str] = None,
) -> Dict[str, Any]:
    ids = sorted(dict.fromkeys(int(i) for i in fixture_ids))
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "message": message,
        "fixture_ids": ids[:FIXTURE_IDS_MAX],
        "fixture_count": len(ids),
        "fix": fix,
    }


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def is_unplaced(rf: Any) -> bool:
    return TAG_UNPLACED in _tags(rf)


def is_unmatched(rf: Any) -> bool:
    profile = getattr(rf, "fixture", None)
    if TAG_UNMATCHED in _tags(rf) or profile is None:
        return True
    return (
        getattr(profile, "source", None) == PLACEHOLDER_SOURCE
        or (getattr(profile, "manufacturer", "") or "").strip() == PLACEHOLDER_MANUFACTURER
    )


def fixture_kind(rf: Any) -> str:
    """The profile's kind of fixture, "other" when it has none."""
    kind = getattr(getattr(rf, "fixture", None), "fixture_type", None)
    kind = getattr(kind, "value", kind)
    return kind if isinstance(kind, str) and kind else "other"


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def check_fixtures(rows: Sequence[Any]) -> Dict[str, Any]:
    if not rows:
        return _check("fixtures", "Fixtures", FAIL, "This rig has no fixtures yet. Import a venue or a patch sheet, or patch some.")
    active = sum(1 for rf in rows if rf.is_active is not False)
    off = len(rows) - active
    message = f"{_fixtures(len(rows))} in the rig"
    message += f", {off} of them switched off." if off else "."
    return _check("fixtures", "Fixtures", OK, message)


def check_positions(rows: Sequence[Any]) -> Dict[str, Any]:
    unplaced = [rf for rf in rows if is_unplaced(rf)]
    guessed = [rf for rf in rows if not is_unplaced(rf) and TAG_UNCONFIRMED in _tags(rf)]
    if not unplaced and not guessed:
        return _check("positions", "Positions", OK, "Every fixture's position has been read from a file or confirmed by a person.")
    parts = []
    if guessed:
        parts.append(
            f"{_fixtures(len(guessed))} stand where a layout guessed, and nobody has confirmed it "
            f"({_named(guessed)})"
        )
    if unplaced:
        parts.append(f"{_fixtures(len(unplaced))} have no position at all and sit at 0,0,0 ({_named(unplaced)})")
    message = "; ".join(parts) + ". Confirm them with flash-and-tap (Locate) or by dragging them in the 3D view."
    return _check("positions", "Positions", WARN, message, (rf.id for rf in guessed + unplaced), fix=FIX_LOCATE)


def check_addresses(rows: Sequence[Any], data: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {rf.id: rf for rf in rows}
    conflicts = PatchingService.find_conflicts(list(data))
    audit = build_programming_audit(list(data))
    past_end = [row for row in audit["patch_report"] if not row["range_ok"]]
    no_mode = {f["id"] for f in data if not f["has_mode"]}

    if not conflicts and not past_end:
        message = "No two fixtures share a DMX channel and every fixture fits in its universe."
        if no_mode:
            message += (
                f" {_fixtures(len(no_mode))} have no DMX mode, so each was counted as "
                f"{NO_MODE_CHANNELS} channels."
            )
        return _check("addresses", "DMX addresses", OK, message)

    # A fixture with no DMX mode has a footprint this module guessed. A clash
    # that needs a guessed footprint may not be there at all (an imported
    # 12-channel par counted as 16), so it warns; a clash between known
    # footprints, or a start address off the universe, fails.
    def guessed_clash(c: Dict[str, Any]) -> bool:
        return c["fixture_a_id"] in no_mode or c["fixture_b_id"] in no_mode

    def guessed_end(row: Dict[str, Any]) -> bool:
        return row["fixture_id"] in no_mode and 1 <= int(row["dmx_address"] or 0) <= MAX_DMX_CHANNELS

    proven = (
        [c for c in conflicts if not guessed_clash(c)],
        [row for row in past_end if not guessed_end(row)],
    )
    guessed = (
        [c for c in conflicts if guessed_clash(c)],
        [row for row in past_end if guessed_end(row)],
    )

    def describe(clashes: List[Dict[str, Any]], ends: List[Dict[str, Any]]) -> Tuple[List[str], List[int]]:
        involved: List[int] = []
        parts = []
        if clashes:
            pairs = []
            for c in clashes:
                involved += [c["fixture_a_id"], c["fixture_b_id"]]
                a, b = by_id.get(c["fixture_a_id"]), by_id.get(c["fixture_b_id"])
                if len(pairs) < 3 and a is not None and b is not None:
                    pairs.append(
                        f"{_label(a)} and {_label(b)} on universe {c['universe'] + 1} "
                        f"channels {c['overlap_start']}-{c['overlap_end']}"
                    )
            text = f"{len(clashes)} address overlap" + ("s" if len(clashes) != 1 else "")
            parts.append(text + ": " + "; ".join(pairs) + (" and more" if len(clashes) > len(pairs) else ""))
        if ends:
            involved += [row["fixture_id"] for row in ends]
            shown = [
                f"{_label(by_id[row['fixture_id']])} ({row['dmx_address']}-{row['address_end']})"
                for row in ends[:3] if row["fixture_id"] in by_id
            ]
            parts.append(
                f"{_fixtures(len(ends))} run past channel 512 of their universe: " + ", ".join(shown)
                + (" and more" if len(ends) > len(shown) else "")
            )
        return parts, involved

    proven_parts, proven_ids = describe(*proven)
    guessed_parts, guessed_ids = describe(*guessed)
    sentences = []
    if proven_parts:
        sentences.append(
            ". ".join(proven_parts) + ". Re-address moves only the fixtures that clash, or edit the "
            "address, before programming."
        )
    if guessed_parts:
        sentences.append(
            ("Maybe also: " if proven_parts else "Maybe: ") + ". ".join(guessed_parts)
            + f". Each of these needs a fixture with no DMX mode, counted as {NO_MODE_CHANNELS} channels: "
            "pick its mode and look again."
        )
    status = FAIL if proven_parts else WARN
    return _check(
        "addresses", "DMX addresses", status, " ".join(sentences), proven_ids + guessed_ids, fix=FIX_READDRESS,
    )


def check_profiles(rows: Sequence[Any]) -> Dict[str, Any]:
    unmatched = [rf for rf in rows if is_unmatched(rf)]
    no_mode = [rf for rf in rows if not is_unmatched(rf) and rf.mode is None]
    if unmatched:
        message = (
            f"{_fixtures(len(unmatched))} have no fixture profile that matched ({_named(unmatched)}). "
            "They are switched off and a console cannot patch them: choose a profile for each."
        )
        if no_mode:
            message += f" {_fixtures(len(no_mode))} more have a profile but no DMX mode."
        return _check("profiles", "Fixture profiles", FAIL, message, (rf.id for rf in unmatched + no_mode))
    if no_mode:
        return _check(
            "profiles", "Fixture profiles", WARN,
            f"{_fixtures(len(no_mode))} have a profile but no DMX mode ({_named(no_mode)}), "
            "so their channels are not known. Pick a mode for each.",
            (rf.id for rf in no_mode),
        )
    return _check("profiles", "Fixture profiles", OK, "Every fixture has a matched profile and a DMX mode.")


def _room(rig: Any) -> Optional[Tuple[float, float, float]]:
    """(width, depth, height) of the stored room, or None when there is none to hold fixtures to."""
    room = (rig.room_shell or {}).get("room") if isinstance(rig.room_shell, dict) else None
    if not isinstance(room, dict):
        return None
    sizes = [_number(room.get(key)) for key in ("width", "depth", "height")]
    if any(size is None or size <= 0 for size in sizes):
        return None
    return sizes[0], sizes[1], sizes[2]  # type: ignore[return-value]


def check_room(rig: Any, rows: Sequence[Any]) -> Dict[str, Any]:
    # Imported here: fixture_position is an endpoint module and imports the room-scan routes.
    from app.api.endpoints.fixture_position import inside_outline, position_outline

    room = _room(rig)
    if room is None:
        return _check(
            "room", "Inside the room", OK,
            "No room is stored with this rig, so nothing was checked. Scan the room to check fixtures against it.",
        )
    width, depth, height = room
    outline = position_outline(rig)
    tol = ROOM_TOLERANCE_M
    outside = []
    for rf in rows:
        if is_unplaced(rf):
            continue
        x, y, z = (_number(v) for v in (rf.position_x, rf.position_y, rf.position_z))
        if x is None or y is None or z is None:
            continue
        out = abs(x) > width / 2 + tol or abs(z) > depth / 2 + tol or y < -tol or y > height + tol
        if not out and outline is not None and not inside_outline(outline, x, z):
            # Near a wall of an L or a notch still counts as in.
            out = not any(
                inside_outline(outline, x + dx, z + dz)
                for dx, dz in ((tol, 0), (-tol, 0), (0, tol), (0, -tol))
            )
        if out:
            outside.append(rf)
    if not outside:
        return _check("room", "Inside the room", OK, "Every placed fixture is inside the scanned room.")
    return _check(
        "room", "Inside the room", WARN,
        f"{_fixtures(len(outside))} stand outside the scanned room's walls, floor or ceiling "
        f"({_named(outside)}). Move them, or fix the room in Edit Room if the scan is wrong.",
        (rf.id for rf in outside),
    )


def _key_id(key: str) -> Optional[int]:
    prefix = "fixture-"
    if key.startswith(prefix) and key[len(prefix):].isdigit():
        return int(key[len(prefix):])
    return None


def check_groups(rows: Sequence[Any], export: ExportRig) -> Dict[str, Any]:
    by_id = {rf.id: rf for rf in rows}
    ungrouped = [by_id[i] for i in (_key_id(f.key) for f in export.fixtures if not f.groups) if i in by_id]
    groups = len(export.groups)
    if not ungrouped:
        return _check("groups", "Groups", OK, f"Every fixture is in a group ({groups} group{'s' if groups != 1 else ''}).")
    return _check(
        "groups", "Groups", WARN,
        f"{_fixtures(len(ungrouped))} are in no group ({_named(ungrouped)}). A console puts them in "
        "'Ungrouped'. Make groups gives each a group by where it hangs and what it is.",
        (rf.id for rf in ungrouped),
        fix=FIX_AUTO_GROUPS,
    )


def check_carry_over(rig: Any) -> Dict[str, Any]:
    entries = pending(rig.room_shell if isinstance(rig.room_shell, dict) else None)
    if not entries:
        return _check("carry_over", "Room scan edits", OK, "No room-scan edits are waiting to be kept.")
    words = [e["message"] for e in entries[:2] if isinstance(e.get("message"), str)]
    message = (
        f"{len(entries)} edit{'s' if len(entries) != 1 else ''} made by hand to the last room were not "
        "kept when the room was scanned again. Open Room Scan to keep them or let them go."
    )
    if words:
        message += " " + " ".join(words)
    return _check("carry_over", "Room scan edits", WARN, message)


def _dry_run(check_id: str, title: str, writers: Sequence[Callable[[], Any]], ok_message: str) -> Dict[str, Any]:
    try:
        for write in writers:
            write()
    except Exception as e:  # noqa: BLE001 - any failure is what this check reports
        return _check(check_id, title, FAIL, f"The export stopped with an error: {type(e).__name__}: {e}")
    return _check(check_id, title, OK, ok_message)


def check_exports(export: ExportRig) -> List[Dict[str, Any]]:
    """Run the grandMA2 and MVR writers in memory. No file is written."""
    ma2 = _dry_run(
        "export_ma2", "grandMA2 export",
        [lambda: ma2_xml(export), lambda: ma2_script(export)],
        "The grandMA2 fixture layer XML and command-line script build without errors.",
    )
    missing = export.missing_gdtf
    mvr_message = "The MVR builds without errors."
    if missing:
        mvr_message += (
            f" {len(missing)} fixture type{'s are' if len(missing) != 1 else ' is'} named by GDTF spec "
            "with no GDTF file inside, so the visualiser needs its own profile for "
            f"{'them' if len(missing) != 1 else 'it'}."
        )
    mvr = _dry_run("export_mvr", "MVR export", [lambda: mvr_bytes(export)], mvr_message)
    return [ma2, mvr]


def readiness(rig: Any, rows: Sequence[Any]) -> Dict[str, Any]:
    """Every check for one rig. `rows` need `fixture` and `mode` (with channels) loaded."""
    rows = sorted(rows, key=lambda rf: (int(rf.universe or 0), int(rf.dmx_address or 0), int(rf.id or 0)))
    data = fixture_rows(rows)
    export = from_rig(rig, rows)
    checks = [
        check_fixtures(rows),
        check_positions(rows),
        check_addresses(rows, data),
        check_profiles(rows),
        check_room(rig, rows),
        check_groups(rows, export),
        check_carry_over(rig),
        *check_exports(export),
    ]
    status = max((c["status"] for c in checks), key=_RANK.__getitem__)
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (OK, WARN, FAIL)}
    return {
        "rig_id": rig.id,
        "rig_name": rig.name,
        "status": status,
        "counts": counts,
        "checks": checks,
        "operator_guide": "docs/READINESS.md",
    }


# ---------------------------------------------------------------------------
# The fix: groups by position and kind
# ---------------------------------------------------------------------------

def _group_names(rows: Sequence[Any]) -> List[str]:
    """Every group name in the rig as written, first seen first: group names and group tags."""
    names: List[str] = []
    for rf in rows:
        for name in [(rf.group_name or "").strip()] + [
            t[len("group:"):].strip() for t in _tags(rf) if t.startswith("group:")
        ]:
            if name and name not in names:
                names.append(name)
    return names


def existing_groups(rows: Sequence[Any]) -> Dict[str, str]:
    """Every group name in the rig, lower-cased, to the name as written."""
    names: Dict[str, str] = {}
    for name in _group_names(rows):
        names.setdefault(name.lower(), name)
    return names


def _in_a_group(rf: Any) -> bool:
    return bool((rf.group_name or "").strip()) or any(
        t.startswith("group:") and t[len("group:"):].strip() for t in _tags(rf)
    )


def _guessed_place(rig: Any, rf: Any) -> str:
    """Where a fixture hangs, read from where it stands on the stage. A guess, and named as one would."""
    width = float(rig.stage_width or 10.0)
    depth = float(rig.stage_depth or 8.0)
    x, y, z = (_number(v) or 0.0 for v in (rf.position_x, rf.position_y, rf.position_z))
    if y < 1.0:
        return "Floor"
    if abs(x) > 0.45 * width:
        # This system's own rigs put stage left at -X (patch_sheet/layout.py).
        return "SL tower" if x < 0 else "SR tower"
    if z > depth / 2:
        return "FOH truss"
    if z > depth / 6:
        return "Front truss"
    if z < -depth / 6:
        return "Back truss"
    return "Mid truss"


def _truss_names(rig: Any, rows: Sequence[Any]) -> Dict[int, str]:
    """The named truss line or ring of the scanned room each fixture hangs on."""
    shell = rig.room_shell if isinstance(rig.room_shell, dict) else None
    out: Dict[int, str] = {}
    if shell is None:
        return out
    for kind in HANGING_KINDS:
        items = shell.get(kind) if isinstance(shell.get(kind), list) else []
        for index, item in enumerate(items):
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            for rf in hung_fixtures(shell, kind, index, rows):
                out.setdefault(rf.id, name.strip())
    return out


def place_name(rig: Any, rf: Any, trusses: Dict[int, str]) -> str:
    """The file's own hang position, else the scanned truss it hangs on, else a guess from where it stands."""
    for tag in _tags(rf):
        if tag.startswith(HANG_POSITION_PREFIX) and tag[len(HANG_POSITION_PREFIX):].strip():
            return tag[len(HANG_POSITION_PREFIX):].strip()
    return trusses.get(rf.id) or _guessed_place(rig, rf)


def auto_group_name(place: str, kind: str) -> str:
    name = f"{place} {_KIND_WORDS.get(kind, 'Fixtures')}"
    return name[:GROUP_NAME_MAX].rstrip()


def plan_auto_groups(rig: Any, rows: Sequence[Any]) -> Dict[str, Any]:
    """Which fixture goes in which group. Changes nothing.

    Only fixtures in no group at all are given one, as their `group_name`.
    When the rig already has a group of exactly the name this would make
    (same letters, same case: the name Make groups itself writes), the
    fixture joins it and the group is listed as `added`. The rig does not
    record who made a group, so that exact name is the only sign one was made
    here; a name that differs only in case ("front truss spots") was typed by
    someone, and its fixtures are left alone and listed as `skipped`. No
    fixture is ever taken out of a group. A fixture with no position is left
    out: there is no place to name it by.
    """
    taken = existing_groups(rows)
    exact = set(_group_names(rows))
    trusses = _truss_names(rig, rows)
    wanted: Dict[str, List[Any]] = {}
    unplaced: List[Any] = []
    for rf in sorted(rows, key=lambda r: (int(r.universe or 0), int(r.dmx_address or 0), int(r.id or 0))):
        if _in_a_group(rf):
            continue
        if is_unplaced(rf):
            unplaced.append(rf)
            continue
        wanted.setdefault(auto_group_name(place_name(rig, rf, trusses), fixture_kind(rf)), []).append(rf)

    assign: Dict[int, str] = {}
    created, added, skipped = [], [], []
    for name, members in wanted.items():
        entry = {"name": name, "fixture_ids": [rf.id for rf in members]}
        if name in exact:
            added.append(entry)
        elif name.lower() in taken:
            skipped.append({"name": taken[name.lower()], "fixture_ids": entry["fixture_ids"]})
            continue
        else:
            created.append(entry)
        for rf in members:
            assign[rf.id] = name
    return {
        "assign": assign,
        "created": created,
        "added": added,
        "skipped": skipped,
        "unplaced_ids": [rf.id for rf in unplaced],
    }


# ---------------------------------------------------------------------------
# The fix: re-address the fixtures that clash
# ---------------------------------------------------------------------------

def address_label(universe: int, address: int) -> str:
    """ "1.001": universe as the check names it (counted from 1), then the address."""
    return f"{int(universe) + 1}.{int(address):03d}"


def plan_readdress(rows: Sequence[Any]) -> Dict[str, Any]:
    """Where each fixture that clashes goes. Changes nothing: it reads dicts, not the rows.

    A fixture clashes when its footprint overlaps one kept in place, or runs
    off its universe (the audit's 1-512 rule). Fixtures are kept in place in
    order: every address-locked fixture first, then by id, so of two that
    overlap the one patched first (lower id) stays. Of a chain A-B-C only B
    moves. Each one that moves takes the first free range at or after its own
    address in its universe, else the first free range in that universe, else
    the next universe with room (plan_addresses). A fixture that cannot move
    (address-locked, or no room anywhere) is listed in `left` with the reason.

    The footprint is the one the check uses: a fixture with no DMX mode is
    counted as NO_MODE_CHANNELS, and its move is marked `guessed`.
    """
    data = fixture_rows(rows)
    by_id = {d["id"]: d for d in data}
    off_universe = {
        row["fixture_id"] for row in build_programming_audit(list(data))["patch_report"] if not row["range_ok"]
    }

    order = sorted(data, key=lambda d: (not d["is_address_locked"], int(d["id"])))
    kept: List[Dict[str, Any]] = []
    movers: List[Tuple[Dict[str, Any], str, List[int]]] = []
    left: List[Dict[str, Any]] = []
    for d in order:
        clashes = sorted({
            c["fixture_a_id"] if c["fixture_b_id"] == d["id"] else c["fixture_b_id"]
            for c in PatchingService.find_conflicts(kept + [d])
            if d["id"] in (c["fixture_a_id"], c["fixture_b_id"])
        })
        reason = "overlap" if clashes else ("past_end" if d["id"] in off_universe else None)
        if reason is None or d["is_address_locked"]:
            kept.append(d)
            if reason is not None:
                left.append({
                    "id": d["id"], "name": d["name"], "reason": "locked",
                    "clashes_with": clashes,
                    "message": f"{d['name'] or 'Fixture ' + str(d['id'])} has a locked address, so it was not moved.",
                })
            continue
        movers.append((d, reason, clashes))

    occupied: Dict[int, List[Tuple[int, int]]] = {}
    for d in kept:
        start = int(d["dmx_address"])
        occupied.setdefault(int(d["universe"]), []).append((start, start + int(d["channel_count"]) - 1))

    moves: List[Dict[str, Any]] = []
    for d, reason, clashes in sorted(movers, key=lambda m: (int(m[0]["universe"]), int(m[0]["dmx_address"]), int(m[0]["id"]))):
        universe, address, footprint = int(d["universe"]), int(d["dmx_address"]), int(d["channel_count"])
        target: Optional[Tuple[int, int]] = None
        try:
            # At or after where it was, in its own universe: the lower addresses are held for this try only.
            ahead = {universe: occupied.get(universe, []) + ([(1, address - 1)] if address > 1 else [])}
            target = plan_addresses(ahead, footprint, 1, universe=universe, max_universes=universe + 1)[0]
        except PatchPlanError:
            try:
                target = plan_addresses(occupied, footprint, 1, universe=universe)[0]
            except PatchPlanError as e:
                left.append({
                    "id": d["id"], "name": d["name"], "reason": "no_room", "clashes_with": clashes,
                    "message": f"{d['name'] or 'Fixture ' + str(d['id'])} was not moved: {e}.",
                })
                continue
        to_u, to_a = target
        occupied.setdefault(to_u, []).append((to_a, to_a + footprint - 1))
        moves.append({
            "id": d["id"],
            "name": d["name"],
            "reason": reason,
            "clashes_with": clashes,
            "channel_count": footprint,
            "guessed": not d["has_mode"],
            "from_universe": universe,
            "from_address": address,
            "to_universe": to_u,
            "to_address": to_a,
            "from_label": address_label(universe, address),
            "to_label": address_label(to_u, to_a),
        })

    # The plan's own proof: with the moves made, the rule the check uses finds nothing left
    # except what `left` already names.
    after = [dict(by_id[i]) for i in by_id]
    planned = {m["id"]: m for m in moves}
    for d in after:
        if d["id"] in planned:
            d["universe"], d["dmx_address"] = planned[d["id"]]["to_universe"], planned[d["id"]]["to_address"]
    still = PatchingService.find_conflicts(after)
    still_off = [r["fixture_id"] for r in build_programming_audit(after)["patch_report"] if not r["range_ok"]]
    return {
        "moves": moves,
        "left": left,
        "conflicts_after": len(still),
        "past_end_after": len(still_off),
    }
