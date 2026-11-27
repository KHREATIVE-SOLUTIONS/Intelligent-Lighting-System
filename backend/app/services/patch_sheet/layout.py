"""
Layout Generator
================

Puts the fixtures a patch sheet did not place onto a stage template, so a rig
imported from a bare patch list has a plausible 3D shape before anyone has
been near the room. It is a first guess and is marked as one on every fixture.

It works on the import plan (venue_import.preview.plan_import), after profiles
are matched, because a row is found from addresses and that needs footprints.

1. Rows. Fixtures of one type on consecutive addresses are one row, in address
   order. A row ends where the type, the position name or the sheet's own group
   changes, where the addresses leave a gap a whole fixture would fit in, where
   the universe changes (unless the row simply ran off the end of one universe
   onto the start of the next), or where the fixture numbers jump (101-108,
   then 201).
2. Places. A row whose position name can be read ("US Truss", "SL Tower", "DJ
   Booth") goes there. Any other row is placed by what kind of fixture it is:
   moving lights, washes, strobes and blinders overhead from upstage to
   downstage in that order, bars and pars on the floor.
3. Positions. Each row is spread evenly along its place, left to right in
   address order, mirrored about the centre line. Rows that share one truss sit
   on different chords of it.
4. Groups. Each row becomes a group named for its place and type, unless the
   sheet named a group itself. A type that spans several rows is also kept as a
   tag on each fixture.

A position the sheet gives is never touched. A fixture that cannot be patched
(no address) is not placed either: it is not imported.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.venue_import.matching import normalise
from app.services.venue_import.model import DMX_UNIVERSE_SIZE
from app.services.venue_import.preview import NO_TYPE, RESERVED_GROUP_NAMES, PlannedFixture

from .positions import BOOTH, FLOOR, FOH, OVERHEAD, RISER, TOWER, HangHint, classify_position
from .templates import TEMPLATES, StageTemplate, build_template

POSITION_SOURCE = "template"
MAX_GROUP_NAME = 100
# Closer than this along a row and the fixtures are drawn on top of each other.
TIGHT_SPACING_M = 0.3
# A sheet this small is a small stage unless something says otherwise.
SMALL_RIG_FIXTURES = 24

# Kind of fixture -> (where it goes when the sheet does not say, its place in
# the order from upstage to downstage, where a lone row of it sits).
_KINDS: Dict[str, Tuple[str, int, float]] = {
    "mover": (OVERHEAD, 0, 0.0),
    "other": (OVERHEAD, 1, 0.0),
    "wash": (OVERHEAD, 2, 0.5),
    "strobe": (OVERHEAD, 3, 1.0),
    "blinder": (OVERHEAD, 4, 1.0),
    "bar": (FLOOR, 0, 0.0),
    "atmosphere": (FLOOR, 1, 0.0),
    "par": (FLOOR, 2, 1.0),
}
# Checked in this order: a "strobe bar" is a strobe, a "wash beam" is a wash.
_KIND_WORDS = (
    ("strobe", r"strob"),
    ("blinder", r"blind|molefay|mole\b"),
    ("bar", r"\b(bar|bars|batten|battens|strip|strips|pixel|tube|tubes|stick|sticks)\b"),
    ("wash", r"wash"),
    ("mover", r"spot|beam|profile|moving|mover|hybrid|\bhead\b"),
    ("par", r"\bpars?\b|\bpar\d|parcan"),
    ("atmosphere", r"laser|haze|hazer|fog|smoke|\bfan\b"),
)


@dataclass
class Row:
    """A run of fixtures placed together."""

    plans: List[PlannedFixture]
    kind: str
    label: str = ""                    # the sheet's position name, as written
    hint: Optional[HangHint] = None
    placed_by: str = "type"            # "label" or "type"
    where: str = ""                    # the place, in words
    group: str = ""
    span: Any = None
    points: List[Tuple[float, float, float]] = field(default_factory=list)

    @property
    def type_label(self) -> str:
        return self.plans[0].type_label

    @property
    def first(self) -> PlannedFixture:
        return self.plans[0]


def fixture_kind(plan: PlannedFixture) -> str:
    """What sort of fixture this is, for deciding where an unlabelled one goes."""
    profile = plan.library_entry or plan.embedded_profile or {}
    sources = [
        str(profile.get("fixture_type") or ""),
        plan.fixture.category,
        plan.fixture.type_name,
        # The name last: "Spot 1" on an unmatched "Acme 300" still says something.
        plan.fixture.name,
    ]
    for source in sources:
        text = source.replace("_", " ").lower()
        if not text or text == "other":
            continue
        for kind, pattern in _KIND_WORDS:
            if re.search(pattern, text):
                return kind
    return "other"


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def _first_step_ok(step: int, next_step: Optional[int]) -> bool:
    """Whether the step between a row's first two fixtures can be believed.

    One step says nothing on its own: 108 to 201 could be a row counted in
    93s. It is believed when it is 1, or when the step after it is no smaller
    (a smaller one means this step was the jump between two rows).
    """
    if step <= 0:
        return False
    return step == 1 or (next_step is not None and step <= next_step)


def _same_run(a: PlannedFixture, b: PlannedFixture) -> bool:
    return (
        normalise(a.type_label) == normalise(b.type_label)
        and normalise(a.fixture.position_label) == normalise(b.fixture.position_label)
        and (a.fixture.group_name or "") == (b.fixture.group_name or "")
    )


def _addresses_continue(
    a: PlannedFixture, b: PlannedFixture, stride: Optional[int], after: Optional[PlannedFixture],
) -> Tuple[bool, Optional[int]]:
    """(whether b carries on a's row by address, the row's stride from here on)."""
    ua, ub = a.fixture.universe, b.fixture.universe
    known = a.footprint_known
    footprint = a.footprint if known else (stride or 1)

    if ub == ua:
        step = b.fixture.dmx_address - a.fixture.dmx_address
        if step <= 0:
            return False, stride
        if known:
            gap = step - a.footprint
            # Overlapping is a clash, and room for a whole fixture is a break.
            if gap < 0 or gap >= a.footprint:
                return False, stride
        if stride is not None:
            return step == stride, stride
        if known:
            return True, step
        next_step = None
        if after is not None and _same_run(b, after) and after.fixture.universe == ub:
            next_step = after.fixture.dmx_address - b.fixture.dmx_address
        # With no footprint, the stride is all there is to go on. A smaller
        # step straight after means this one was the gap between two rows.
        return (next_step is None or step <= next_step), step

    if ub == ua + 1:
        # Ran off the end: another would not have fitted, and the next starts the universe.
        last = a.fixture.dmx_address + footprint - 1
        if last + footprint <= DMX_UNIVERSE_SIZE or b.fixture.dmx_address > footprint:
            return False, stride
        return True, stride
    return False, stride


def find_rows(plans: List[PlannedFixture]) -> List[Row]:
    """The rows among the fixtures that need a position, in address order."""
    waiting = sorted(
        (p for p in plans if p.importable and p.position is None),
        key=lambda p: (p.fixture.universe, p.fixture.dmx_address, p.index),
    )
    runs: List[List[PlannedFixture]] = []
    stride: Optional[int] = None
    id_step: Optional[int] = None

    for position, plan in enumerate(waiting):
        after = waiting[position + 1] if position + 1 < len(waiting) else None
        joined = False
        if runs:
            previous = runs[-1][-1]
            if _same_run(previous, plan):
                joined, new_stride = _addresses_continue(previous, plan, stride, after)
                a, b = previous.fixture.fixture_number, plan.fixture.fixture_number
                if joined and a is not None and b is not None:
                    step = b - a
                    if id_step is not None:
                        joined = step == id_step
                    else:
                        c = after.fixture.fixture_number if after is not None and _same_run(plan, after) else None
                        joined = _first_step_ok(step, c - b if c is not None else None)
                        if joined:
                            id_step = step
                if joined:
                    stride = new_stride
        if joined:
            runs[-1].append(plan)
        else:
            runs.append([plan])
            stride, id_step = None, None

    rows: List[Row] = []
    for run in runs:
        label = run[0].fixture.position_label.strip()
        hint = classify_position(label) if label else None
        rows.append(Row(
            plans=run, kind=fixture_kind(run[0]), label=label, hint=hint,
            placed_by="label" if hint is not None else "type",
        ))
    return rows


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------

def _depth_name(depth: float, family: str, letter: str = "") -> str:
    """A line across the stage, in words. `letter` names one of several lines
    between the upstage and the downstage one, counted from upstage."""
    thing = "Truss" if family == OVERHEAD else "Floor"
    if depth <= 0.0:
        return f"US {thing}"
    if depth >= 1.0:
        return f"DS {thing}"
    if abs(depth - 0.5) < 1e-9:
        return f"MS {thing}"
    if letter:
        return f"{thing} {letter}"
    return f"{thing} {round(depth * 100)}% downstage"


def _spread(count: int, lines: int) -> List[Tuple[float, str]]:
    """(depth, letter) for `count` rows over at most `lines` lines, upstage to downstage.

    A lone line has depth -1: the caller picks where it goes.
    """
    used = max(1, min(count, lines))
    if used == 1:
        return [(-1.0, "")] * count
    out = []
    for index in range(count):
        line = index * used // count
        out.append((line / (used - 1), chr(ord("A") + line)))
    return out


class _Placer:
    def __init__(self, template: StageTemplate, mirror: bool):
        self.template = template
        self.mirror = mirror
        self.taken: Dict[Tuple, int] = {}
        self.assumptions: List[str] = []
        self.warnings: List[str] = []
        self.used_sides = False

    def _low(self, side: str) -> bool:
        """Whether a sheet's side is the -X side of the plan."""
        self.used_sides = True
        return (side == "sl") != self.mirror

    def _claim(self, *keys: Tuple) -> int:
        """How many rows already sit on these places; this row is the next."""
        nth = max(self.taken.get(key, 0) for key in keys)
        for key in keys:
            self.taken[key] = nth + 1
        return nth

    def _across(self, row: Row, family: str, depth: float, side: str, letter: str = "") -> None:
        line = self.template.overhead(depth) if family == OVERHEAD else self.template.floor(depth)
        name = _depth_name(depth, family, letter)
        if side in ("sl", "sr"):
            low = self._low(side)
            line = line.part("low" if low else "high")
            name += f", {side.upper()} half"
        elif side == "c":
            line = line.part("c")
            name += ", centre"
        nth = self._claim((family, round(depth, 4), side))
        row.span, row.where = line.shifted(nth), name

    def place_labelled(self, row: Row, numbered: Dict[int, float]) -> bool:
        """Place a row by what its position name says. False: the name gave no place."""
        hint = row.hint
        template = self.template
        if hint.family == OVERHEAD:
            if hint.ring and template.has_ring and self.taken.get(("ring",), 0) < template.overhead_lines:
                nth = self._claim(("ring",))
                row.span, row.where = template.ring(nth), "Ring" if nth == 0 else f"Ring {nth + 1}"
                return True
            depth = hint.depth
            if depth is None and hint.number is not None:
                depth = numbered.get(hint.number)
            if depth is None:
                return False
            self._across(row, OVERHEAD, depth, hint.side)
            return True
        if hint.family == FLOOR:
            if hint.depth is None and not hint.side:
                return False
            self._across(row, FLOOR, hint.depth if hint.depth is not None else 1.0, hint.side)
            return True
        if hint.family == TOWER:
            if hint.side in ("sl", "sr"):
                low = self._low(hint.side)
                nth = self._claim((TOWER, low))
                row.span, row.where = template.tower(low).shifted(nth), f"{hint.side.upper()} Tower"
            else:
                nth = self._claim((TOWER, True), (TOWER, False))
                row.span, row.where = template.towers().shifted(nth), "Towers"
                if len(row.plans) % 2:
                    self.warnings.append(
                        f"{len(row.plans)} x {row.type_label} on the towers is an odd number, so one "
                        "tower carries one more than the other."
                    )
            return True
        line, name = {
            RISER: (template.riser, "Riser"),
            BOOTH: (template.booth, "DJ Booth"),
            FOH: (template.foh, "FOH Truss"),
        }[hint.family]
        nth = self._claim((hint.family,))
        row.span, row.where = line().shifted(nth), name
        return True

    def place_by_type(self, rows: List[Row]) -> None:
        """Place the rows no position name placed, by kind of fixture."""
        template = self.template
        for family in (OVERHEAD, FLOOR):
            pool = [
                row for row in rows
                if (row.hint.family if row.hint is not None else _KINDS[row.kind][0]) == family
            ]
            pool.sort(key=lambda row: (
                _KINDS[row.kind][1], row.first.fixture.universe, row.first.fixture.dmx_address,
            ))
            if not pool:
                continue
            if family == OVERHEAD and template.has_ring:
                # The ring, then the smaller rings inside it. Past the last
                # ring the rest hang on straight trusses across the room.
                while pool and self.taken.get(("ring",), 0) < template.overhead_lines:
                    row = pool.pop(0)
                    nth = self._claim(("ring",))
                    row.span = template.ring(nth)
                    row.where = "Ring" if nth == 0 else f"Ring {nth + 1}"
                if not pool:
                    continue
            lines = template.overhead_lines if family == OVERHEAD else 2
            for row, (depth, letter) in zip(pool, _spread(len(pool), lines)):
                self._across(row, family, _KINDS[row.kind][2] if depth < 0 else depth, "", letter)


def _numbered_depths(rows: List[Row]) -> Dict[int, float]:
    """Depth for each numbered overhead position ("Truss 1", "LX 3") that gives no other."""
    numbers = sorted({
        row.hint.number for row in rows
        if row.hint is not None and row.hint.family == OVERHEAD
        and row.hint.depth is None and row.hint.number is not None
    })
    if not numbers:
        return {}
    if len(numbers) == 1:
        return {numbers[0]: 0.5}
    # Number 1 is the furthest downstage, the way electrics are counted.
    return {number: 1.0 - index / (len(numbers) - 1) for index, number in enumerate(numbers)}


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _short_type(plan: PlannedFixture) -> str:
    if plan.type_label == NO_TYPE:
        return "fixtures"
    return plan.fixture.model or plan.fixture.type_name


def _name_groups(rows: List[Row]) -> None:
    """Give each row a group, and each fixture its type as a tag when the type spans rows."""
    used: Dict[str, int] = {}
    for row in rows:
        given = (row.first.fixture.group_name or "").strip()
        if given:
            row.group = given
            continue
        place = row.label or row.where
        kind = _short_type(row.first)
        name = f"{place} {kind}".strip()
        if len(name) > MAX_GROUP_NAME - 5:
            name = name[:MAX_GROUP_NAME - 5].rstrip()
        if name.lower() in RESERVED_GROUP_NAMES:
            name += " row"
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name} ({used[name]})"
        row.group = name
        for plan in row.plans:
            plan.fixture.group_name = name

    rows_per_type: Dict[str, int] = {}
    for row in rows:
        rows_per_type[normalise(row.type_label)] = rows_per_type.get(normalise(row.type_label), 0) + 1
    for row in rows:
        if rows_per_type[normalise(row.type_label)] < 2 or row.type_label == NO_TYPE:
            continue
        tag = row.type_label[:MAX_GROUP_NAME]
        for plan in row.plans:
            if tag != plan.fixture.group_name and tag not in plan.fixture.groups:
                plan.fixture.groups.append(tag)


# ---------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------

def pick_template(plans: List[PlannedFixture]) -> Tuple[str, str]:
    """(template name, why) for a sheet whose importer did not choose one."""
    waiting = [p for p in plans if p.importable and p.position is None]
    hints = [classify_position(p.fixture.position_label) for p in waiting if p.fixture.position_label]
    if any(hint is not None and hint.ring for hint in hints):
        return "club_ring", "the sheet names a ring"
    if len(waiting) <= SMALL_RIG_FIXTURES:
        return "small_stage", f"the sheet has {len(waiting)} fixture(s) to place, {SMALL_RIG_FIXTURES} or fewer"
    return "festival_main_stage", f"the sheet has {len(waiting)} fixtures to place, more than {SMALL_RIG_FIXTURES}"


def _xyz(point: Tuple[float, float, float]) -> Dict[str, float]:
    return {"x": point[0], "y": point[1], "z": point[2]}


def generate_layout(
    plans: List[PlannedFixture],
    template: StageTemplate,
    mirror: bool = False,
    chosen_by: str = "asked for",
) -> Dict[str, Any]:
    """Place every importable fixture that has no position, and report what was done.

    Changes the plans in place: position, position_source "template", and the
    fixture's group where the sheet gave none. Returns the layout report.
    """
    kept = sum(1 for p in plans if p.importable and p.position is not None)
    rows = find_rows(plans)
    placer = _Placer(template, mirror)

    numbered = _numbered_depths(rows)
    unread = sorted({row.label for row in rows if row.label and row.hint is None})
    by_type: List[Row] = []
    for row in rows:
        if row.hint is None or not placer.place_labelled(row, numbered):
            row.placed_by = "type"
            by_type.append(row)
    placer.place_by_type(by_type)

    for row in rows:
        count = len(row.plans)
        row.points = row.span.points(count)
        for plan, point in zip(row.plans, row.points):
            if point == (0.0, 0.0, 0.0):
                # The origin is what an unplaced fixture looks like everywhere else.
                point = (0.0, 0.1, 0.0)
            plan.position = point
            plan.rotation = None
            plan.position_source = POSITION_SOURCE
        spacing = row.span.length / count
        if count > 1 and spacing < TIGHT_SPACING_M:
            placer.warnings.append(
                f"{count} x {row.type_label} on {row.where} are {spacing:.2f} m apart on this "
                "template. A wider stage, or splitting the row, would spread them out."
            )
    _name_groups(rows)

    assumptions = [
        f"Positions were generated on the '{template.display_name}' template "
        f"({template.width:g} m wide, {template.depth:g} m deep, {template.height:g} m high; {chosen_by}). "
        "They are a first guess at the room, not a measurement: each one is marked unconfirmed "
        "until someone has checked it.",
        "Fixtures of one type on consecutive addresses were taken as one row and laid out in "
        "address order from the plan's left (-X) to its right (+X).",
    ]
    if placer.used_sides:
        assumptions.append(
            "SL / stage left was placed on the plan's " + ("right (+X)" if mirror else "left (-X)")
            + ", SR on the other side"
            + (", as asked (mirror)." if mirror else
               ", which is the side this system's own rigs call stage left. Import with "
               "mirror=true if the sheet means the other side.")
        )
    if numbered:
        assumptions.append(
            "Numbered overhead positions were spread from downstage to upstage in number order: "
            + ", ".join(f"{n} at {_depth_name(d, OVERHEAD)}" for n, d in sorted(numbered.items())) + "."
        )
    if unread:
        placer.warnings.append(
            "Position name(s) not understood, so those fixtures were placed by their type: "
            + ", ".join(f"'{label}'" for label in unread[:10]) + ("..." if len(unread) > 10 else "") + "."
        )

    return {
        "template": {**template.describe(), "chosen_by": chosen_by, "mirror": mirror},
        "generated": sum(len(row.plans) for row in rows),
        "kept_from_sheet": kept,
        "position_confirmed": False,
        "rows": [
            {
                "row": number,
                "where": row.where,
                "placed_by": row.placed_by,
                "position_label": row.label,
                "type_name": row.type_label,
                "kind": row.kind,
                "group": row.group,
                "fixtures": len(row.plans),
                "fixture_indexes": [plan.index for plan in row.plans],
                "first_address": {"universe": row.first.fixture.universe, "dmx_address": row.first.fixture.dmx_address},
                "last_address": {
                    "universe": row.plans[-1].fixture.universe, "dmx_address": row.plans[-1].fixture.dmx_address,
                },
                "universes": sorted({plan.fixture.universe for plan in row.plans}),
                "from": _xyz(row.points[0]),
                "to": _xyz(row.points[-1]),
                "place": row.span.describe(),
                "position_confirmed": False,
            }
            for number, row in enumerate(rows, start=1)
        ],
        "assumptions": assumptions,
        "warnings": placer.warnings,
    }


def template_names() -> List[str]:
    return list(TEMPLATES)


__all__ = [
    "POSITION_SOURCE", "Row", "build_template", "find_rows", "fixture_kind",
    "generate_layout", "pick_template", "template_names",
]
