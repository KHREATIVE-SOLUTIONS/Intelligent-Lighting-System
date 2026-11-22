"""
Stage Templates
===============

Three stages a rig can be laid out on when nothing says where it really hangs:
a festival main stage with a roof and side towers, a club with a ring over the
dance floor, and a small stage with a back and a front truss. Each is built
from a width, a depth and a height, so the same template fits a 12 m or a 30 m
stage.

A template is places, not fixtures: lines and rings in this system's stage
axes (metres from the centre of the floor, X across, Y up, -Z upstage). The
layout generator decides what goes on which.

Every place spreads its fixtures evenly and mirrored about the centre line. A
row of n on a line sits at the middle of n equal bays, so one fixture is dead
centre and two are at the quarter points. Positions are built from whole
numbers that are exact opposites and rounded to the centimetre, so a fixture
and its mirror image share exactly one height and depth and have exactly
opposite X: the engine pairs fixtures on that.
"""

import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

Point = Tuple[float, float, float]

# Where the second, third... row on one truss goes: the far chord, the near
# chord, then further out. Metres along Z.
CHORD_OFFSETS = (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5)
# Each further ring is this much smaller than the one outside it.
RING_STEP = 0.3
# A fixture on the deck. Not zero: 0,0,0 is what an unplaced fixture looks like.
FLOOR_HEIGHT = 0.1


def _cm(value: float) -> float:
    return round(value, 2) + 0.0


@dataclass(frozen=True)
class Line:
    """A straight run: a truss, a floor row, or one tower (bottom to top)."""

    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    def points(self, count: int) -> List[Point]:
        middle = tuple((a + b) / 2.0 for a, b in zip(self.start, self.end))
        half = tuple((b - a) / 2.0 for a, b in zip(self.start, self.end))
        out: List[Point] = []
        for index in range(count):
            step = 2 * index + 1 - count          # -(n-1) .. n-1, an exact mirror pair
            out.append(tuple(_cm(m + h * step / count) for m, h in zip(middle, half)))
        return out

    def shifted(self, nth: int) -> "Line":
        """The same run for the nth row sharing it, moved onto another chord."""
        dz = CHORD_OFFSETS[nth] if nth < len(CHORD_OFFSETS) else 0.5 * nth
        return Line(
            (self.start[0], self.start[1], self.start[2] + dz),
            (self.end[0], self.end[1], self.end[2] + dz),
        )

    def part(self, side: str) -> "Line":
        """The -X half ("low"), the +X half ("high") or the middle third ("c")."""
        def at(t: float) -> Point:
            return tuple(a + (b - a) * t for a, b in zip(self.start, self.end))
        if side == "low":
            return Line(self.start, at(0.5))
        if side == "high":
            return Line(at(0.5), self.end)
        if side == "c":
            return Line(at(1 / 3), at(2 / 3))
        return self

    def describe(self) -> Dict[str, Any]:
        return {"shape": "line", "from": list(map(_cm, self.start)), "to": list(map(_cm, self.end))}


@dataclass(frozen=True)
class Ring:
    """A circle at one height, walked clockwise from upstage as seen from above."""

    centre_z: float
    radius: float
    y: float

    @property
    def length(self) -> float:
        return 2 * math.pi * self.radius

    def points(self, count: int) -> List[Point]:
        out: List[Optional[Point]] = [None] * count
        for index in range((count + 1) // 2):
            mirror = count - 1 - index
            if index == mirror:
                # The odd one out sits on the centre line, downstage.
                out[index] = (0.0, _cm(self.y), _cm(self.centre_z + self.radius))
                continue
            angle = math.pi * (2 * index + 1) / count
            x = _cm(self.radius * math.sin(angle))
            z = _cm(self.centre_z - self.radius * math.cos(angle))
            out[index] = (x, _cm(self.y), z)
            out[mirror] = (-x, _cm(self.y), z)
        return out  # type: ignore[return-value]

    def shifted(self, nth: int) -> "Ring":
        return replace(self, radius=self.radius * max(0.2, 1.0 - RING_STEP * nth))

    def describe(self) -> Dict[str, Any]:
        return {"shape": "ring", "centre": [0.0, _cm(self.y), _cm(self.centre_z)], "radius": _cm(self.radius)}


@dataclass(frozen=True)
class Pair:
    """Two towers taken together: a row split between them, level for level."""

    low: Line    # the tower at -X
    high: Line   # the tower at +X

    @property
    def length(self) -> float:
        return self.low.length + self.high.length

    def points(self, count: int) -> List[Point]:
        on_low = (count + 1) // 2
        on_high = count // 2
        # Both towers use the low tower's levels, so the pairs are level.
        levels = self.low.points(on_low)
        mirrored = [(-x, y, z) for x, y, z in levels[:on_high]]
        return levels + mirrored

    def shifted(self, nth: int) -> "Pair":
        return Pair(self.low.shifted(nth), self.high.shifted(nth))

    def describe(self) -> Dict[str, Any]:
        return {"shape": "pair", "low": self.low.describe(), "high": self.high.describe()}


@dataclass(frozen=True)
class StageTemplate:
    """A stage reduced to the places a fixture can be put."""

    name: str
    display_name: str
    description: str
    width: float
    depth: float
    height: float
    # Overhead: the height fixtures hang at, how long a truss is, where the
    # upstage and downstage trusses are, and how many lines unlabelled rows use.
    trim: float
    truss_length: float
    upstage_z: float
    downstage_z: float
    overhead_lines: int
    # Floor rows.
    floor_length: float
    floor_upstage_z: float
    floor_downstage_z: float
    # Side towers: how far out, how far downstage, and the span of heights.
    tower_x: float
    tower_z: float
    tower_low: float
    tower_high: float
    # Riser and booth: a short line on the centre line.
    riser_z: float
    riser_y: float
    riser_length: float
    booth_z: float
    booth_y: float
    booth_length: float
    foh_z: float
    # A ring over the floor. Zero radius: this stage has none.
    ring_radius: float = 0.0
    ring_z: float = 0.0

    def _across(self, length: float, y: float, z: float) -> Line:
        return Line((-length / 2.0, y, z), (length / 2.0, y, z))

    def overhead(self, depth: float) -> Line:
        """A truss across the stage. depth 0 is the upstage truss, 1 the downstage."""
        z = self.upstage_z + (self.downstage_z - self.upstage_z) * depth
        return self._across(self.truss_length, self.trim, z)

    def floor(self, depth: float) -> Line:
        z = self.floor_upstage_z + (self.floor_downstage_z - self.floor_upstage_z) * depth
        return self._across(self.floor_length, FLOOR_HEIGHT, z)

    def tower(self, low_side: bool) -> Line:
        x = -self.tower_x if low_side else self.tower_x
        return Line((x, self.tower_low, self.tower_z), (x, self.tower_high, self.tower_z))

    def towers(self) -> Pair:
        return Pair(self.tower(True), self.tower(False))

    def riser(self) -> Line:
        return self._across(self.riser_length, self.riser_y, self.riser_z)

    def booth(self) -> Line:
        return self._across(self.booth_length, self.booth_y, self.booth_z)

    def foh(self) -> Line:
        return self._across(self.truss_length, max(1.0, self.trim - 1.0), self.foh_z)

    def ring(self, nth: int = 0) -> Ring:
        return Ring(self.ring_z, self.ring_radius, self.trim).shifted(nth)

    @property
    def has_ring(self) -> bool:
        return self.ring_radius > 0.0

    def stage_size(self) -> Dict[str, float]:
        return {"stage_width": self.width, "stage_depth": self.depth, "stage_height": self.height}

    def describe(self) -> Dict[str, Any]:
        places: Dict[str, Any] = {
            "upstage_truss": self.overhead(0.0).describe(),
            "midstage_truss": self.overhead(0.5).describe(),
            "downstage_truss": self.overhead(1.0).describe(),
            "upstage_floor": self.floor(0.0).describe(),
            "downstage_floor": self.floor(1.0).describe(),
            "towers": self.towers().describe(),
            "riser": self.riser().describe(),
            "dj_booth": self.booth().describe(),
            "foh_truss": self.foh().describe(),
        }
        if self.has_ring:
            places["ring"] = self.ring().describe()
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "stage": {"width": self.width, "depth": self.depth, "height": self.height},
            "overhead_lines": self.overhead_lines,
            "places": places,
        }


def festival_main_stage(width: float = 24.0, depth: float = 14.0, height: float = 12.0) -> StageTemplate:
    """A roofed main stage: trusses across under the roof, a tower each side."""
    return StageTemplate(
        name="festival_main_stage",
        display_name="Festival main stage",
        description=(
            "A roofed stage with trusses across it from upstage to downstage, a tower either "
            "side at the downstage edge, a floor package, a riser and a DJ booth on the centre line."
        ),
        width=width, depth=depth, height=height,
        trim=max(2.0, height - 1.5),
        truss_length=max(2.0, width - 2.0),
        upstage_z=-(depth / 2.0 - 1.0),
        downstage_z=depth / 2.0 - 1.0,
        overhead_lines=6,
        floor_length=max(2.0, width - 4.0),
        floor_upstage_z=-(depth / 2.0 - 1.5),
        floor_downstage_z=depth / 2.0 - 0.5,
        tower_x=width / 2.0 + 2.0,
        tower_z=depth / 2.0 - 1.0,
        tower_low=2.0,
        tower_high=max(3.0, height - 2.0),
        riser_z=-depth / 4.0, riser_y=0.6, riser_length=max(2.0, width / 4.0),
        booth_z=depth / 6.0, booth_y=1.1, booth_length=min(4.0, width / 3.0),
        foh_z=depth / 2.0 + 1.5,
    )


def club_ring(width: float = 14.0, depth: float = 14.0, height: float = 5.0) -> StageTemplate:
    """A club: a ring over the dance floor, the DJ booth upstage."""
    return StageTemplate(
        name="club_ring",
        display_name="Club ring",
        description=(
            "A room with a ring of fixtures over the dance floor and the DJ booth upstage. "
            "Unlabelled overhead rows go round the ring; further rows go on smaller rings inside it."
        ),
        width=width, depth=depth, height=height,
        trim=max(2.0, height - 0.5),
        truss_length=max(2.0, width - 2.0),
        upstage_z=-(depth / 2.0 - 2.0),
        downstage_z=depth / 2.0 - 2.0,
        overhead_lines=3,
        floor_length=max(2.0, width - 3.0),
        floor_upstage_z=-(depth / 2.0 - 1.0),
        floor_downstage_z=depth / 2.0 - 1.0,
        tower_x=width / 2.0 - 0.5,
        tower_z=-(depth / 2.0 - 2.0),
        tower_low=1.0,
        tower_high=max(1.5, height - 1.0),
        riser_z=-(depth / 2.0 - 2.5), riser_y=0.5, riser_length=max(2.0, width / 4.0),
        booth_z=-(depth / 2.0 - 1.5), booth_y=1.1, booth_length=min(4.0, width / 3.0),
        foh_z=depth / 2.0 - 0.5,
        ring_radius=0.3 * min(width, depth),
        ring_z=depth / 14.0,
    )


def small_stage(width: float = 8.0, depth: float = 6.0, height: float = 4.5) -> StageTemplate:
    """A small stage: a back truss, a front truss, a stand each side."""
    return StageTemplate(
        name="small_stage",
        display_name="Small stage",
        description=(
            "A small stage with a truss at the back and one at the front, a lighting stand "
            "either side, and a floor row."
        ),
        width=width, depth=depth, height=height,
        trim=max(2.0, height - 0.5),
        truss_length=max(2.0, width - 1.0),
        upstage_z=-(depth / 2.0 - 0.5),
        downstage_z=depth / 2.0 - 0.5,
        overhead_lines=2,
        floor_length=max(2.0, width - 2.0),
        floor_upstage_z=-(depth / 2.0 - 1.0),
        floor_downstage_z=depth / 2.0 - 0.3,
        tower_x=width / 2.0 + 0.5,
        tower_z=depth / 2.0 - 0.5,
        tower_low=1.0,
        tower_high=max(1.5, min(3.0, height - 0.5)),
        riser_z=-depth / 4.0, riser_y=0.4, riser_length=max(1.5, width / 4.0),
        booth_z=0.0, booth_y=1.1, booth_length=min(3.0, width / 3.0),
        foh_z=depth / 2.0 + 1.5,
    )


TEMPLATES: Dict[str, Callable[..., StageTemplate]] = {
    "festival_main_stage": festival_main_stage,
    "club_ring": club_ring,
    "small_stage": small_stage,
}


def build_template(
    name: str,
    width: Optional[float] = None,
    depth: Optional[float] = None,
    height: Optional[float] = None,
) -> StageTemplate:
    """A named template, at its usual size or the size given. Raises KeyError for an unknown name."""
    builder = TEMPLATES[name]
    sizes = {key: value for key, value in (("width", width), ("depth", depth), ("height", height)) if value}
    return builder(**sizes)
