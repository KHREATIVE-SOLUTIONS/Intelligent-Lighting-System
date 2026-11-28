"""
A rig's moving heads against its focus targets
==============================================

Builds the focus table from the same rows every export reads (a Rig and its
RigFixture rows with `fixture` and `mode.channels` loaded) and the ExportRig the
console files are written from, so the fixture ids here are the console ids
the MA2 script and the handoff pack use. Pure: nothing is written, nothing is
sent to a device. docs/FOCUS_PRESETS.md.

Which fixtures are moving heads: a mode with a pan or a tilt channel; a fixture
with no channel list known is taken by its type (moving head, spot, wash, beam)
and written 8-bit, since nothing says it has fine channels.

How a head is mounted is not stored. A head tagged `floor`, `standing` or
`floor_standing`, or one under 1 m with no `hung` tag, is taken as standing on
the floor; every other head as hung. The table says which, and that it was
assumed. Invert follows the 3D view (`resolveInvert`): the `pan_invert` tag,
flipped again by the older `is_inverted` flag, and the `tilt_invert` tag.
Swap is the `pan_tilt_swap` tag; nothing in the system sets it yet.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.console_export.model import ExportRig

from .aim import Aim, Head, aim
from .targets import Target, all_targets

STANDING_TAGS = {"floor", "standing", "floor_standing"}
HUNG_TAG = "hung"
SWAP_TAG = "pan_tilt_swap"
STANDING_BELOW_M = 1.0
MOVER_TYPES = {"moving_head", "spot", "wash", "beam"}

CSV_COLUMNS = [
    "target", "target_name", "fixture_id", "name", "mount", "position", "reachable",
    "pan_deg", "tilt_deg", "pan_attr_deg", "tilt_attr_deg",
    "pan_dmx", "pan_fine_dmx", "tilt_dmx", "tilt_fine_dmx",
    "target_x", "target_y", "target_z", "throw_m", "reason",
]


@dataclass(frozen=True)
class FocusHead:
    number: int
    name: str
    key: str
    head: Head
    # "hung" or "standing", and whether that was read from a tag or assumed from height.
    mount: str
    mount_assumed: bool
    unconfirmed: bool


@dataclass(frozen=True)
class FocusEntry:
    fixture: FocusHead
    point: Optional[Tuple[float, float, float]]
    aim: Aim


@dataclass
class FocusTarget:
    target: Target
    entries: List[FocusEntry] = field(default_factory=list)

    @property
    def reachable(self) -> List[FocusEntry]:
        return [e for e in self.entries if e.aim.reachable]

    @property
    def unreachable(self) -> List[FocusEntry]:
        return [e for e in self.entries if not e.aim.reachable]


@dataclass
class FocusTable:
    targets: List[FocusTarget]
    heads: List[FocusHead]
    # Movers left out, and why (no position).
    left_out: List[Dict[str, Any]] = field(default_factory=list)


def _type_name(value: Any) -> str:
    value = getattr(value, "value", value)
    return str(value or "").lower()


def _axes(rf: Any) -> Optional[Dict[str, bool]]:
    """{pan, tilt, pan_fine, tilt_fine} from the mode's channels; None when no channel list is known."""
    mode = getattr(rf, "mode", None)
    channels = list(getattr(mode, "channels", None) or []) if mode is not None else []
    if not channels:
        return None
    types = {_type_name(c.channel_type) for c in channels}
    return {
        "pan": "pan" in types, "tilt": "tilt" in types,
        "pan_fine": "pan_fine" in types, "tilt_fine": "tilt_fine" in types,
    }


def _number_or(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def focus_heads(rows: Sequence[Any], export: ExportRig) -> Tuple[List[FocusHead], List[Dict[str, Any]]]:
    by_key = {f.key: f for f in export.fixtures}
    heads: List[FocusHead] = []
    left_out: List[Dict[str, Any]] = []
    for rf in rows:
        exported = by_key.get(f"fixture-{rf.id}")
        if exported is None:
            continue
        profile = getattr(rf, "fixture", None)
        axes = _axes(rf)
        if axes is None:
            if _type_name(getattr(profile, "fixture_type", None)) not in MOVER_TYPES:
                continue
            axes = {"pan": True, "tilt": True, "pan_fine": False, "tilt_fine": False}
        if not (axes["pan"] or axes["tilt"]):
            continue
        if exported.position is None:
            left_out.append({"fixture_id": exported.number, "name": exported.name,
                             "reason": "it has no position in the rig"})
            continue
        tags = [str(t).lower() for t in (rf.tags or []) if isinstance(t, str)]
        x, y, z = exported.position
        if STANDING_TAGS & set(tags):
            standing, assumed = True, False
        elif HUNG_TAG in tags:
            standing, assumed = False, False
        else:
            standing, assumed = y < STANDING_BELOW_M, True
        head = Head(
            position=(float(x), float(y), float(z)),
            rotation=tuple(float(v) for v in exported.rotation),
            standing=standing,
            pan_range=_number_or(getattr(profile, "pan_range", None), 540.0) if axes["pan"] else 0.0,
            tilt_range=_number_or(getattr(profile, "tilt_range", None), 270.0) if axes["tilt"] else 0.0,
            pan_invert=("pan_invert" in tags) != bool(getattr(rf, "is_inverted", False)),
            tilt_invert="tilt_invert" in tags,
            swap=SWAP_TAG in tags,
            pan_fine=axes["pan_fine"],
            tilt_fine=axes["tilt_fine"],
        )
        heads.append(FocusHead(
            number=exported.number, name=exported.name, key=exported.key, head=head,
            mount="standing" if standing else "hung", mount_assumed=assumed,
            unconfirmed=exported.unconfirmed,
        ))
    # Sorted, so the same rig gives the same table whatever order the rows came in.
    heads.sort(key=lambda h: h.number)
    left_out.sort(key=lambda item: item["fixture_id"])
    return heads, left_out


def build_table(rig: Any, rows: Sequence[Any], export: ExportRig) -> FocusTable:
    heads, left_out = focus_heads(rows, export)
    out: List[FocusTarget] = []
    for target in all_targets(getattr(rig, "room_shell", None), getattr(rig, "focus_targets", None)):
        row = FocusTarget(target)
        if not target.skipped:
            points = target.points_for([h.head.position for h in heads])
            for head, point in zip(heads, points):
                row.entries.append(FocusEntry(head, point, aim(head.head, point)))
        out.append(row)
    return FocusTable(out, heads, left_out)


# ---------------------------------------------------------------------------
# As the API answers and as a CSV
# ---------------------------------------------------------------------------

def _rig_fixture_id(key: str) -> Optional[int]:
    """The rig fixture row's id, from its export key `fixture-<id>`.

    `fixture_id` is the console number, which is renumbered when two fixtures
    share one or one has none, so the app cannot find the head it means in the
    3D view from it. This is the id the view draws the head under.
    """
    _, _, tail = key.rpartition("-")
    return int(tail) if tail.isdigit() else None


def _entry_dict(entry: FocusEntry) -> Dict[str, Any]:
    a = entry.aim
    return {
        "fixture_id": entry.fixture.number,
        "rig_fixture_id": _rig_fixture_id(entry.fixture.key),
        "name": entry.fixture.name,
        "mount": entry.fixture.mount,
        "mount_assumed": entry.fixture.mount_assumed,
        "position_unconfirmed": entry.fixture.unconfirmed,
        "point": list(entry.point) if entry.point else None,
        "reachable": a.reachable,
        "reason": a.reason,
        "throw_m": a.throw_m,
        "pan_deg": a.pan_deg, "tilt_deg": a.tilt_deg,
        "pan_attr_deg": a.pan_attr_deg, "tilt_attr_deg": a.tilt_attr_deg,
        "pan_dmx": a.pan_dmx, "pan_fine_dmx": a.pan_fine_dmx,
        "tilt_dmx": a.tilt_dmx, "tilt_fine_dmx": a.tilt_fine_dmx,
    }


def table_dict(table: FocusTable) -> Dict[str, Any]:
    return {
        "heads": len(table.heads),
        "left_out": table.left_out,
        "targets": [
            {
                **t.target.as_dict(),
                "reachable_count": len(t.reachable),
                "unreachable": [{"fixture_id": e.fixture.number, "name": e.fixture.name, "reason": e.aim.reason}
                                for e in t.unreachable],
                "fixtures": [_entry_dict(e) for e in t.entries],
            }
            for t in table.targets
        ],
        "operator_guide": "docs/FOCUS_PRESETS.md",
    }


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        text = f"{round(value, 4) + 0.0:.4f}".rstrip("0").rstrip(".")
        return "0" if text in ("", "-0") else text
    return value


def focus_csv(table: FocusTable) -> str:
    """One row per target and head; a skipped target is one row with its reason. Same rig, same bytes."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for t in table.targets:
        if t.target.skipped or not t.entries:
            writer.writerow([t.target.key, t.target.name] + [""] * (len(CSV_COLUMNS) - 3)
                            + [t.target.skipped or "no moving heads with a position"])
            continue
        for e in t.entries:
            a = e.aim
            point = e.point or ("", "", "")
            writer.writerow([_cell(v) for v in (
                t.target.key, t.target.name, e.fixture.number, e.fixture.name,
                e.fixture.mount + (" (assumed)" if e.fixture.mount_assumed else ""),
                "guessed" if e.fixture.unconfirmed else "confirmed",
                a.reachable, a.pan_deg, a.tilt_deg, a.pan_attr_deg, a.tilt_attr_deg,
                a.pan_dmx, a.pan_fine_dmx, a.tilt_dmx, a.tilt_fine_dmx,
                point[0], point[1], point[2], a.throw_m, a.reason,
            )])
    return out.getvalue()
