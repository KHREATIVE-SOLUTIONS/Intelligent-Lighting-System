"""
Venue Configuration Presets
Pre-configured rig and settings for common venue types.

Each preset defines:
- Stage dimensions
- Fixture inventory (movers, washes, bars, strobes, spots)
- Fixture positions on the rig
- DMX addressing
- Key lighting zones
- Default genre
"""

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class VenueSize(Enum):
    SMALL_NIGHTCLUB = "small_nightclub"
    MEDIUM_VENUE = "medium_venue"
    PRO_BEAM_ROOM = "pro_beam_room"
    LARGE_CONCERT = "large_concert"
    FESTIVAL_MAINSTAGE = "festival_mainstage"
    BIGROOM_EDM = "bigroom_edm"
    CLUB_NIGHT = "club_night"
    LIV_MIAMI_APPROX = "liv_miami_approx"


@dataclass
class StageSpec:
    """Physical stage dimensions in meters."""
    width: float
    depth: float
    height: float     # Truss/ceiling height
    truss_lines: int  # Number of truss lines (front to back)


@dataclass
class FixtureSpec:
    """Specification for a fixture in the venue."""
    fixture_type: str      # mover, wash, bar, strobe, spot
    id: str
    name: str
    dmx_address: int
    universe: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    # Patch-sheet detail, for a preset modelled on a real room. `model` is the
    # fixture the source names, `stands_for` is what one patched fixture
    # represents when several real ones are folded into it, and `basis` says
    # whether the count is from the source or assumed.
    model: str = ""
    stands_for: str = ""
    basis: str = ""
    group: str = ""
    # Engine groups this fixture belongs to, by name: what a look selects on.
    # `group` above is the one label a person reads on the patch sheet.
    groups: Tuple[str, ...] = ()
    # Degrees about X, Y and Z. No preset turns a fixture yet: the 3D view
    # mounts and aims each one from where it is patched.
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class KeyZoneSpec:
    """Specification for a key lighting zone."""
    zone: str             # PerformerZone value
    fixture_ids: List[str]
    active: bool = True
    min_intensity: float = 0.4


@dataclass
class DomeShell:
    """A shallow dome ceiling: a spherical cap over a circle on the floor plan."""
    diameter_ft: float
    radius: float
    center_x: float
    center_z: float
    rim_height: float
    apex_height: float
    basis: str

    def height_at(self, distance: float) -> float:
        """Height of the dome's surface this far out from its centre line."""
        rise = self.apex_height - self.rim_height
        sphere = (self.radius ** 2 + rise ** 2) / (2.0 * rise)
        reach = min(abs(distance), self.radius)
        return self.apex_height - (sphere - math.sqrt(sphere ** 2 - reach ** 2))


@dataclass
class DiscShell:
    """A round area of floor: the dance floor."""
    center_x: float
    center_z: float
    radius: float
    basis: str


@dataclass
class RingShell:
    """Part of a flat ring at one height: a balcony or mezzanine.

    Angles are in degrees clockwise from upstage seen from above, as
    _ring_positions counts them: 0 is -Z (the booth), 90 is +X, 180 is +Z.
    """
    center_x: float
    center_z: float
    inner_radius: float
    outer_radius: float
    soffit_height: float
    deck_height: float
    start_deg: float
    end_deg: float
    basis: str


@dataclass
class BoxShell:
    """A box standing on the floor (or `base_height` above it), sides square to the room."""
    center_x: float
    center_z: float
    width: float    # along X
    depth: float    # along Z
    height: float
    basis: str
    base_height: float = 0.0
    name: str = ""


@dataclass
class RoomShell:
    """The room around a rig, for the 3D view: metres, in the rig's own axes.

    Origin at the centre of the floor, X across, Y up, -Z upstage. This is
    scenery only. Nothing here stops a beam or is read by the engine.
    """
    basis: str
    dome: DomeShell
    dance_floor: DiscShell
    balcony: RingShell
    dj_booth: BoxShell
    rear_stage: BoxShell
    led_walls: List[BoxShell] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VenuePreset:
    """Complete venue configuration preset."""
    name: str
    display_name: str
    description: str
    size: VenueSize
    stage: StageSpec
    fixtures: List[FixtureSpec]
    key_zones: List[KeyZoneSpec]
    default_genre: str
    default_bpm: float
    fixture_counts: Dict[str, int] = field(default_factory=dict)
    # Set on a preset that imitates a real room: printed at the head of its
    # patch sheet so the sheet can never be taken for the venue's own.
    disclaimer: str = ""
    # The room the rig hangs in, where a preset describes one.
    room: Optional[RoomShell] = None
    # Engine group name -> fixture ids, in patch order. Read off each fixture's
    # `groups`, so the patch sheet and the engine cannot name different sets.
    groups: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.fixture_counts:
            counts = {}
            for f in self.fixtures:
                counts[f.fixture_type] = counts.get(f.fixture_type, 0) + 1
            self.fixture_counts = counts
        if not self.groups:
            groups: Dict[str, List[str]] = {}
            for f in self.fixtures:
                for name in f.groups:
                    groups.setdefault(name, []).append(f.id)
            self.groups = groups


# Channel mappings (shared across presets)
MOVER_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'speed': 4, 'dimmer': 5, 'shutter': 6,
    'red': 7, 'green': 8, 'blue': 9, 'white': 10,
    'color_wheel': 11, 'gobo': 12, 'gobo_rotation': 13,
    'prism': 14, 'focus': 15
}
MOVER_CH_COUNT = 16

WASH_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'speed': 4, 'dimmer': 5, 'shutter': 6,
    'red': 7, 'green': 8, 'blue': 9, 'white': 10,
    'zoom': 11, 'other': 12, 'other_2': 13
}
WASH_CH_COUNT = 14

BAR_CHANNELS = {
    'dimmer': 0, 'strobe': 1,
    'red': 2, 'green': 3, 'blue': 4, 'white': 5,
    'amber': 6, 'uv': 7, 'macro': 8, 'speed': 9,
    'other': 10, 'other_2': 11
}
BAR_CH_COUNT = 12

STROBE_CHANNELS = {
    'dimmer': 0, 'strobe': 1, 'other': 2, 'speed': 3,
}
STROBE_CH_COUNT = 4

SPOT_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'dimmer': 4, 'shutter': 5,
    'red': 6, 'green': 7, 'blue': 8, 'white': 9,
    'zoom': 10, 'focus': 11
}
SPOT_CH_COUNT = 12

# Pan/tilt travel in degrees per fixture type. A range of 0 means the fixture
# is static and must never be given pan/tilt output.
FIXTURE_RANGES: Dict[str, Tuple[float, float]] = {
    'mover': (540.0, 270.0),
    'wash': (540.0, 270.0),
    'spot': (540.0, 270.0),
    'bar': (0.0, 0.0),
    'strobe': (0.0, 0.0),
    'par': (0.0, 0.0),
}
STATIC_RANGES = (0.0, 0.0)

# The preset vocabulary describes the physical fixture; the engine groups on
# mover/wash/bar/strobe. A preset spot must reach the engine as a mover or it is
# driven at a different speed class than the same fixture patched in the database.
PRESET_ENGINE_TYPES: Dict[str, str] = {
    'mover': 'mover',
    'spot': 'mover',
    'wash': 'wash',
    'par': 'wash',
    'bar': 'bar',
    'strobe': 'strobe',
}
ENGINE_TYPE_GROUP_NAMES: Dict[str, str] = {
    'mover': 'movers',
    'wash': 'washes',
    'bar': 'bars',
    'strobe': 'strobes',
}


class _AddressAllocator:
    """Assigns sequential DMX addresses, rolling to the next universe on overflow."""

    def __init__(self, universe: int = 0):
        self.address = 1
        self.universe = universe

    def take(self, ch_count: int) -> Tuple[int, int]:
        if self.address + ch_count - 1 > 512:
            self.universe += 1
            self.address = 1
        current = self.address
        self.address += ch_count
        return current, self.universe


def _distribute_positions(count: int, x_range: Tuple[float, float],
                          y: float, z: float) -> List[Tuple[float, float, float]]:
    """Distribute fixtures evenly across an x-range."""
    if count <= 1:
        return [((x_range[0] + x_range[1]) / 2.0, y, z)]
    positions = []
    for i in range(count):
        t = i / (count - 1)
        x = x_range[0] + t * (x_range[1] - x_range[0])
        positions.append((x, y, z))
    return positions


def _build_small_nightclub() -> VenuePreset:
    """Small nightclub: 4 movers, 4 bars, 2 strobes."""
    stage = StageSpec(width=8.0, depth=6.0, height=3.0, truss_lines=1)
    fixtures = []
    alloc = _AddressAllocator()

    # 2 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.0, 3.0), 2.8, -2.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", a, u, x, y, z))

    # 2 movers rear
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.0, 3.0), 2.8, 2.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", a, u, x, y, z))

    # 2 bars floor
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-2.5, 2.5), 0.5, -2.5)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", a, u, x, y, z))

    # 2 bars truss
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-2.5, 2.5), 2.5, 0.0)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_truss{i+1}", f"Bar Truss {i+1}", a, u, x, y, z))

    # 2 strobes
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.5, 3.5), 2.8, -1.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe{i+1}", f"Strobe {i+1}", a, u, x, y, z))

    key_zones = [
        KeyZoneSpec("dj_booth", ["mover_f1", "mover_f2"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="small_nightclub",
        display_name="Small Nightclub",
        description="Intimate club with 4 movers, 4 LED bars, and 2 strobes. 8x6m stage, 3m ceiling.",
        size=VenueSize.SMALL_NIGHTCLUB,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


def _build_medium_venue() -> VenuePreset:
    """Medium venue: rebuilt all-mover rig for clear pan/tilt busking motion."""
    stage = StageSpec(width=12.0, depth=8.0, height=5.0, truss_lines=2)
    fixtures = []
    alloc = _AddressAllocator()

    # 7 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(7, (-5.2, 5.2), 4.5, -1.1)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", a, u, x, y, z))

    # 7 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(7, (-5.2, 5.2), 4.5, 1.1)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", a, u, x, y, z))

    key_zones = [
        KeyZoneSpec("dj_booth", ["mover_f3", "mover_f4", "mover_f5"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_center", ["mover_r3", "mover_r4", "mover_r5"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="medium_venue",
        display_name="Medium Venue",
        description="Two parallel trusses with 14 symmetric movers for fully dynamic pan/tilt busking looks.",
        size=VenueSize.MEDIUM_VENUE,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


def _build_large_concert() -> VenuePreset:
    """Large concert: 16 movers, 12 bars, 8 strobes, 4 spots."""
    stage = StageSpec(width=20.0, depth=12.0, height=8.0, truss_lines=3)
    fixtures = []
    alloc = _AddressAllocator()

    # 8 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-8.0, 8.0), 7.0, -5.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", a, u, x, y, z))

    # 8 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-8.0, 8.0), 7.0, 5.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", a, u, x, y, z))

    # 6 bars floor (downstage)
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-7.0, 7.0), 0.5, -5.5)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", a, u, x, y, z))

    # 6 bars mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-7.0, 7.0), 6.5, 0.0)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_truss{i+1}", f"Bar Truss {i+1}", a, u, x, y, z))

    # 8 strobes (4 front + 4 rear)
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-7.5, 7.5), 7.0, -4.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_f{i+1}", f"Strobe Front {i+1}", a, u, x, y, z))
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-7.5, 7.5), 7.0, 4.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_r{i+1}", f"Strobe Rear {i+1}", a, u, x, y, z))

    # 4 spots
    spots = [
        ("spot_dj", "DJ Spot", 0.0, 6.5, -5.5),
        ("spot_center", "Center Spot", 0.0, 7.0, 0.0),
        ("spot_left", "Stage Left Spot", -6.0, 6.5, 0.0),
        ("spot_right", "Stage Right Spot", 6.0, 6.5, 0.0),
    ]
    for sid, sname, sx, sy, sz in spots:
        a, u = alloc.take(SPOT_CH_COUNT)
        fixtures.append(FixtureSpec("spot", sid, sname, a, u, sx, sy, sz))

    key_zones = [
        KeyZoneSpec("dj_booth", ["spot_dj", "mover_f4", "mover_f5"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_center", ["spot_center", "mover_r4", "mover_r5"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_left", ["spot_left", "mover_f1", "mover_f2"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_right", ["spot_right", "mover_f7", "mover_f8"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="large_concert",
        display_name="Large Concert",
        description="Concert hall with 16 movers, 12 LED bars, 8 strobes, and 4 spots. 20x12m stage, 8m truss.",
        size=VenueSize.LARGE_CONCERT,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="rock",
        default_bpm=120.0,
    )


def _build_pro_beam_room() -> VenuePreset:
    """Professional beam-only room rig with multiple truss rows."""
    stage = StageSpec(width=24.0, depth=16.0, height=10.0, truss_lines=5)
    fixtures = []
    alloc = _AddressAllocator()

    truss_rows = [
        ("f", "Front", -7.0, 10),
        ("ff", "Front Fill", -3.5, 10),
        ("m", "Mid", 0.0, 12),
        ("rr", "Rear Fill", 3.5, 10),
        ("r", "Rear", 7.0, 10),
    ]

    for row_key, row_name, z, count in truss_rows:
        for i, (x, y, zz) in enumerate(_distribute_positions(count, (-10.5, 10.5), 9.2, z)):
            a, u = alloc.take(MOVER_CH_COUNT)
            fixtures.append(
                FixtureSpec(
                    "mover",
                    f"beam_{row_key}{i+1}",
                    f"Beam {row_name} {i+1}",
                    a,
                    u,
                    x,
                    y,
                    zz,
                )
            )

    key_zones = [
        KeyZoneSpec("dj_booth", ["beam_f5", "beam_f6", "beam_ff5", "beam_ff6"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_center", ["beam_m5", "beam_m6", "beam_m7", "beam_m8"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="pro_beam_room",
        display_name="Pro Beam Room",
        description=(
            "Beam-only top-down room rig with 5 truss rows and full-depth canopy coverage "
            "for immersive whole-room looks."
        ),
        size=VenueSize.PRO_BEAM_ROOM,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


def _build_festival_mainstage() -> VenuePreset:
    """Festival mainstage: 32 movers, 24 bars, 16 strobes, 8 spots."""
    stage = StageSpec(width=40.0, depth=20.0, height=15.0, truss_lines=4)
    fixtures = []
    alloc = _AddressAllocator()

    # 12 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(12, (-16.0, 16.0), 13.0, -8.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", a, u, x, y, z))

    # 10 movers mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(10, (-14.0, 14.0), 12.0, 0.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_m{i+1}", f"Mover Mid {i+1}", a, u, x, y, z))

    # 10 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(10, (-14.0, 14.0), 13.0, 8.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", a, u, x, y, z))

    # 8 bars floor
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-15.0, 15.0), 0.5, -9.0)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", a, u, x, y, z))

    # 8 bars mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-14.0, 14.0), 11.0, 0.0)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_mid{i+1}", f"Bar Mid {i+1}", a, u, x, y, z))

    # 8 bars rear
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-14.0, 14.0), 11.0, 7.0)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_rear{i+1}", f"Bar Rear {i+1}", a, u, x, y, z))

    # 16 strobes (distributed across front/mid/rear)
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-16.0, 16.0), 13.0, -7.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_f{i+1}", f"Strobe Front {i+1}", a, u, x, y, z))
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-14.0, 14.0), 12.0, 0.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_m{i+1}", f"Strobe Mid {i+1}", a, u, x, y, z))
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-16.0, 16.0), 13.0, 7.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_r{i+1}", f"Strobe Rear {i+1}", a, u, x, y, z))

    # 8 spots
    spot_positions = [
        ("spot_dj", "DJ Spot", 0.0, 12.0, -9.0),
        ("spot_center_ds", "Downstage Center", 0.0, 13.0, -6.0),
        ("spot_center_us", "Upstage Center", 0.0, 13.0, 6.0),
        ("spot_left_ds", "Downstage Left", -10.0, 12.0, -6.0),
        ("spot_right_ds", "Downstage Right", 10.0, 12.0, -6.0),
        ("spot_left_us", "Upstage Left", -10.0, 12.0, 6.0),
        ("spot_right_us", "Upstage Right", 10.0, 12.0, 6.0),
        ("spot_drum", "Drum Riser", 5.0, 12.0, 4.0),
    ]
    for sid, sname, sx, sy, sz in spot_positions:
        a, u = alloc.take(SPOT_CH_COUNT)
        fixtures.append(FixtureSpec("spot", sid, sname, a, u, sx, sy, sz))

    key_zones = [
        KeyZoneSpec("dj_booth", ["spot_dj", "mover_f6", "mover_f7"], active=True, min_intensity=0.0),
        KeyZoneSpec("stage_center", ["spot_center_ds", "spot_center_us", "mover_m5", "mover_m6"],
                    active=True, min_intensity=0.0),
        KeyZoneSpec("stage_left", ["spot_left_ds", "spot_left_us", "mover_f1", "mover_f2"],
                    active=True, min_intensity=0.0),
        KeyZoneSpec("stage_right", ["spot_right_ds", "spot_right_us", "mover_f11", "mover_f12"],
                    active=True, min_intensity=0.0),
        KeyZoneSpec("drum_riser", ["spot_drum", "mover_r8", "mover_r9"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="festival_mainstage",
        display_name="Festival Mainstage",
        description="Festival stage with 32 movers, 24 LED bars, 16 strobes, and 8 spots across 3 truss lines. 40x20m stage, 15m truss.",
        size=VenueSize.FESTIVAL_MAINSTAGE,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


def _build_bigroom_edm() -> VenuePreset:
    """Big-room EDM nightclub: 44 fixtures modeling Hakkasan/Amnesia style rig."""
    stage = StageSpec(width=14.0, depth=10.0, height=7.0, truss_lines=3)
    fixtures = []
    addr = 1
    universe = 0

    def next_addr(ch_count):
        nonlocal addr, universe
        if addr + ch_count > 512:
            universe += 1
            addr = 1
        current = addr
        addr += ch_count
        return current, universe

    # 10 beam movers on upstage truss (main aerial beams)
    # Spread across 10m width at height 6.5m, z=-2.0
    for i, (x, y, z) in enumerate(_distribute_positions(10, (-5.0, 5.0), 6.5, -2.0)):
        a, u = next_addr(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"beam_up{i+1}", f"Beam Upstage {i+1}", a, u, x, y, z))

    # 8 spot movers on mid truss
    # Spread 8m width at height 6.0m, z=0.0
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-4.0, 4.0), 6.0, 0.0)):
        a, u = next_addr(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_mid{i+1}", f"Mover Mid {i+1}", a, u, x, y, z))

    # 6 wash fixtures on downstage truss
    # Spread 7m width at height 5.5m, z=2.0
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-3.5, 3.5), 5.5, 2.0)):
        a, u = next_addr(WASH_CH_COUNT)
        fixtures.append(FixtureSpec("wash", f"wash_ds{i+1}", f"Wash Downstage {i+1}", a, u, x, y, z))

    # 4 LED bars on floor (z=-3.0, y=0.3)
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-5.0, 5.0), 0.3, -3.0)):
        a, u = next_addr(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", a, u, x, y, z))

    # 4 LED bars on rear truss (z=-2.5, y=6.0)
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-5.0, 5.0), 6.0, -2.5)):
        a, u = next_addr(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_rear{i+1}", f"Bar Rear {i+1}", a, u, x, y, z))

    # 4 strobes (2 left, 2 right) at height 6.0m
    strobe_positions = [
        ("strobe_l1", "Strobe Left 1", -6.5, 6.0, -1.0),
        ("strobe_l2", "Strobe Left 2", -6.5, 6.0, 1.0),
        ("strobe_r1", "Strobe Right 1", 6.5, 6.0, -1.0),
        ("strobe_r2", "Strobe Right 2", 6.5, 6.0, 1.0),
    ]
    for sid, sname, sx, sy, sz in strobe_positions:
        a, u = next_addr(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", sid, sname, a, u, sx, sy, sz))

    # 4 blinders (modeled as strobes with strobe channels) - center cluster at height 5.5m, z=1.0
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-1.5, 1.5), 5.5, 1.0)):
        a, u = next_addr(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"blinder{i+1}", f"Blinder {i+1}", a, u, x, y, z))

    # 4 spot fixtures (followspot positions) at corners
    spot_positions = [
        ("spot_dl", "Spot Downstage Left", -5.0, 6.0, 2.5),
        ("spot_dr", "Spot Downstage Right", 5.0, 6.0, 2.5),
        ("spot_ul", "Spot Upstage Left", -5.0, 6.0, -2.0),
        ("spot_ur", "Spot Upstage Right", 5.0, 6.0, -2.0),
    ]
    for sid, sname, sx, sy, sz in spot_positions:
        a, u = next_addr(SPOT_CH_COUNT)
        fixtures.append(FixtureSpec("spot", sid, sname, a, u, sx, sy, sz))

    key_zones = [
        KeyZoneSpec("aerial_beams", ["beam_up1", "beam_up2", "beam_up3", "beam_up4", "beam_up5",
                                      "beam_up6", "beam_up7", "beam_up8", "beam_up9", "beam_up10"],
                    active=True, min_intensity=0.5),
        KeyZoneSpec("mid_movers", ["mover_mid1", "mover_mid2", "mover_mid3", "mover_mid4",
                                    "mover_mid5", "mover_mid6", "mover_mid7", "mover_mid8"],
                    active=True, min_intensity=0.45),
        KeyZoneSpec("wash_lights", ["wash_ds1", "wash_ds2", "wash_ds3", "wash_ds4", "wash_ds5", "wash_ds6"],
                    active=True, min_intensity=0.4),
        KeyZoneSpec("dance_floor", ["bar_floor1", "bar_floor2", "bar_floor3", "bar_floor4"],
                    active=True, min_intensity=0.5),
    ]

    return VenuePreset(
        name="bigroom_edm",
        display_name="Big-Room EDM",
        description=(
            "Hakkasan/Amnesia-style big-room nightclub with 44 fixtures: "
            "10 aerial beams, 8 mid movers, 6 washes, 8 LED bars, 4 strobes, 4 blinders, 4 spots. "
            "14x10m stage, 7m ceiling, optimized for high-energy EDM."
        ),
        size=VenueSize.BIGROOM_EDM,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


def _build_club_night() -> VenuePreset:
    """Mid-size nightclub, rigged the way a lighting designer would rig one.

    This is the reference rig for tuning the show. Every fixture family the
    engine drives is here, mounted where a club puts it, and mirrored about the
    centre line so that a symmetric look has something to be symmetric on.
    `pro_beam_room` is 52 identical movers: nothing the bars, pars or strobes do
    can be seen on it, and nothing can be judged for left/right balance.

    Layout, with -Z upstage (the DJ booth) and +Z toward the dance floor:

        back truss   z=-3.5  six beams over the booth
        mid truss    z= 0.0  six movers over the dance floor, a strobe at each end
        front truss  z= 3.5  four moving washes
        booth front  z=-3.8  four LED bars across the booth fascia
        back wall    z=-4.8  four LED bars high behind the DJ, a strobe each side
        floor                six pars uplighting the side walls
    """
    stage = StageSpec(width=12.0, depth=10.0, height=4.5, truss_lines=3)
    fixtures = []
    alloc = _AddressAllocator()

    for i, (x, y, z) in enumerate(_distribute_positions(6, (-5.0, 5.0), 4.2, -3.5)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"beam_b{i+1}", f"Beam Back {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(6, (-5.0, 5.0), 4.3, 0.0)):
        a, u = alloc.take(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_m{i+1}", f"Mover Mid {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(4, (-4.5, 4.5), 4.2, 3.5)):
        a, u = alloc.take(WASH_CH_COUNT)
        fixtures.append(FixtureSpec("wash", f"wash_f{i+1}", f"Wash Front {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(4, (-2.25, 2.25), 1.0, -3.8)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_booth{i+1}", f"Bar Booth {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(4, (-4.5, 4.5), 3.0, -4.8)):
        a, u = alloc.take(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_wall{i+1}", f"Bar Wall {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(2, (-5.7, 5.7), 4.2, 0.0)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_m{i+1}", f"Strobe Mid {i+1}", a, u, x, y, z))

    for i, (x, y, z) in enumerate(_distribute_positions(2, (-2.0, 2.0), 3.6, -4.8)):
        a, u = alloc.take(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_w{i+1}", f"Strobe Wall {i+1}", a, u, x, y, z))

    # Left wall then right wall, so par N and par N+3 are a mirrored pair.
    par_index = 0
    for x in (-5.8, 5.8):
        for z in (-2.0, 1.0, 4.0):
            par_index += 1
            a, u = alloc.take(BAR_CH_COUNT)
            fixtures.append(FixtureSpec("par", f"par_{par_index}", f"Par {par_index}", a, u, x, 0.3, z))

    key_zones = [
        KeyZoneSpec("dj_booth", ["wash_f2", "wash_f3"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="club_night",
        display_name="Club Night",
        description="Mid-size nightclub: 12 movers on two trusses, 4 moving washes, 8 LED bars, "
                    "4 strobes and 6 pars. 12x10m floor, 4.5m ceiling, DJ booth upstage.",
        size=VenueSize.CLUB_NIGHT,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
    )


LIV_DISCLAIMER = (
    "APPROXIMATE RECREATION of LIV Miami (Fontainebleau Miami Beach), built from "
    "public 2009 trade press. It is NOT LIV's real patch, plot or addressing, and "
    "is not endorsed by or affiliated with the venue."
)

# The dome is 88 ft across.
LIV_DOME_RADIUS = 13.4


# The LED walls stand just off the upstage wall, which is at -13.5.
LIV_LED_WALL_Z = -13.3


def _liv_room_shell() -> RoomShell:
    """The room round the LIV recreation. Only the dome's 88 ft is from the press."""
    wall = "sourced: LED walls at the booth; size and position assumed"
    return RoomShell(
        basis=(
            "Approximate. The 88 ft dome is from the 2009 press; every other "
            "dimension is assumed. Not a survey of the venue."
        ),
        # Rim and apex are set to clear the dome fixtures patched under it.
        dome=DomeShell(diameter_ft=88.0, radius=LIV_DOME_RADIUS, center_x=0.0, center_z=0.0,
                       rim_height=7.2, apex_height=9.1,
                       basis="sourced: 88 ft across; heights assumed"),
        dance_floor=DiscShell(center_x=0.0, center_z=0.0, radius=7.5, basis="assumed"),
        # The rear half of the room, open on the booth side. The mezzanine
        # spots hang from its soffit.
        balcony=RingShell(center_x=0.0, center_z=0.0, inner_radius=10.0, outer_radius=LIV_DOME_RADIUS,
                          soffit_height=4.0, deck_height=4.4, start_deg=90.0, end_deg=270.0,
                          basis="sourced: a mezzanine level; shape and size assumed"),
        # Where the 3D view already builds its booth for a 27 m room.
        dj_booth=BoxShell(center_x=0.0, center_z=-12.85, width=6.5, depth=1.3, height=1.25,
                          basis="sourced: a DJ booth; position and size assumed", name="DJ booth"),
        # The rear VIP level that converts to a stage, between the staircase pars.
        rear_stage=BoxShell(center_x=0.0, center_z=12.5, width=7.0, depth=1.8, height=0.6,
                            basis="sourced: a rear level that converts to a stage; size assumed",
                            name="Rear stage riser"),
        led_walls=[
            BoxShell(center_x=0.0, center_z=LIV_LED_WALL_Z - 0.1, width=6.0, depth=0.1, height=2.4,
                     base_height=3.2, basis=wall, name="LED wall centre"),
            BoxShell(center_x=-5.0, center_z=LIV_LED_WALL_Z - 0.1, width=2.0, depth=0.1, height=2.4,
                     base_height=3.2, basis=wall, name="LED wall wing left"),
            BoxShell(center_x=5.0, center_z=LIV_LED_WALL_Z - 0.1, width=2.0, depth=0.1, height=2.4,
                     base_height=3.2, basis=wall, name="LED wall wing right"),
        ],
    )


def _ring_positions(count: int, radius: float, y: float,
                    offset_deg: float) -> List[Tuple[float, float, float]]:
    """Points round a circle centred over the dance floor, clockwise from upstage.

    Rounded to the centimetre so that a point and its mirror image share exactly
    one depth: the engine pairs fixtures by equal z and opposite x.
    """
    positions = []
    for i in range(count):
        angle = math.radians(offset_deg + i * 360.0 / count)
        positions.append((round(radius * math.sin(angle), 2), y, round(-radius * math.cos(angle), 2)))
    return positions


def _build_liv_miami_approx() -> VenuePreset:
    """An approximate recreation of LIV Miami, from public sources. Not LIV's plot.

    What the 2009 press (Live Design, PLSN, SJ Lighting) describes: a round room
    under an 88 ft dome, the dome lit by about 585 LED nodes in radial spokes and
    about 300 colour floods round its edge; 22 moving spots as the dance-floor
    package, 4 smaller spots on the mezzanine soffit, 8 LED moving washes low
    over the crowd at the dome centre, plus LED pars, LED strips and strobes.
    docs/venues/LIV_MIAMI_APPROX_NOTES.md lists what is sourced, what is
    assumed and what was changed to fit this system.

    Layout, with -Z upstage (the DJ booth) and +Z toward the rear mezzanine:

        dome            16 spokes x 2 cells of LED nodes, 12 flood segments at the rim
        chords A-D      z=-7.5/-2.5/2.5/7.5  22 spots on four trusses inside the dome,
                                             a strobe off each end
        centre, 10 ft   z=-1.5/1.5           8 moving washes over the dance floor
        mezzanine       z=11                 4 spots on the soffit, facing the booth
        booth, skyboxes                      8 LED strips
        floor                                8 LED pars up the walls and the staircase
        behind the booth z=-13.3             its LED walls as 27 cells, 2 booth wash pars

    The spots hang on straight chords, not a ring: the engine and the 3D view
    both read a rig as rows, and a ring would be eleven rows of two heads.

    Universe 0 is the moving lights, 1 the dome matrix, strips and strobes,
    2 the colour floods and pars, 3 the booth: a stand-in for its LED walls
    and two wash pars.
    """
    # Trim height of the main package. The dome itself rises above it.
    stage = StageSpec(width=27.0, depth=27.0, height=6.5, truss_lines=4)
    fixtures: List[FixtureSpec] = []

    def add(alloc, kind, ch_count, fid, name, pos, model, stands_for, basis, group, groups):
        a, u = alloc.take(ch_count)
        x, y, z = pos
        fixtures.append(FixtureSpec(kind, fid, name, a, u, x, y, z,
                                    model=model, stands_for=stands_for, basis=basis,
                                    group=group, groups=tuple(groups)))

    # --- Universe 0: moving lights -------------------------------------------
    moving = _AddressAllocator(universe=0)

    chords = [("a", -7.5, 5, 6.0), ("b", -2.5, 6, 9.0), ("c", 2.5, 6, 9.0), ("d", 7.5, 5, 6.0)]
    for row, z, count, half in chords:
        for i, pos in enumerate(_distribute_positions(count, (-half, half), 6.5, z)):
            # The head on the centre line is on neither side.
            side = ["spots_left"] if pos[0] < 0 else ["spots_right"] if pos[0] > 0 else []
            add(moving, "mover", MOVER_CH_COUNT, f"ds575_{row}{i+1}", f"Design Spot {row.upper()}{i+1}",
                pos, "Elation Design Spot 575E", "1 fixture", "sourced: 22", "Dance Floor Spots",
                ["floor_spots", f"spots_chord_{row}"] + side)

    # Under the balcony ring: any wider and the outer pair would hang outside it.
    for i, pos in enumerate(_distribute_positions(4, (-7.5, 7.5), 4.0, 11.0)):
        add(moving, "spot", SPOT_CH_COUNT, f"ds300_{i+1}", f"Mezzanine Spot {i+1}",
            pos, "Elation Design Spot 300E", "1 fixture", "sourced: 4", "Mezzanine Spots",
            ["balcony_spots"])

    # 10 ft over the crowd.
    wash_index = 0
    for z in (-1.5, 1.5):
        for pos in _distribute_positions(4, (-3.6, 3.6), 3.05, z):
            wash_index += 1
            add(moving, "wash", WASH_CH_COUNT, f"imp_{wash_index}", f"Impression Wash {wash_index}",
                pos, "Elation Impression RGB", "1 fixture", "sourced: 8", "Dome Centre Washes",
                ["centre_washes"])

    # --- Universe 1: dome matrix, strips, strobes ----------------------------
    matrix = _AddressAllocator(universe=1)

    # About 585 nodes folded into 32 cells: 16 spokes, an inner and an outer
    # cell on each. Turned half a step so no spoke lies on the centre line.
    inner = _ring_positions(16, 3.5, 8.6, 11.25)
    outer = _ring_positions(16, 8.5, 7.8, 11.25)
    for i in range(16):
        add(matrix, "bar", BAR_CH_COUNT, f"dome_s{i+1}a", f"Dome Spoke {i+1} Inner",
            inner[i], "Color Kinetics iColor Cove MX", "about 18 nodes",
            "sourced: about 585 nodes; spoke count assumed", "Dome Spokes",
            ["dome_pixels", "dome_spokes", "dome_spokes_inner"])
        add(matrix, "bar", BAR_CH_COUNT, f"dome_s{i+1}b", f"Dome Spoke {i+1} Outer",
            outer[i], "Color Kinetics iColor Cove MX", "about 18 nodes",
            "sourced: about 585 nodes; spoke count assumed", "Dome Spokes",
            ["dome_pixels", "dome_spokes", "dome_spokes_outer"])

    for i, x in enumerate((-2.7, -0.9, 0.9, 2.7)):
        add(matrix, "bar", BAR_CH_COUNT, f"dled_booth{i+1}", f"Booth Strip {i+1}",
            (x, 1.0, -12.1), "Elation DLED 60 Strip", "1 strip",
            "assumed count and position", "Booth Strips",
            ["led_strips", "booth_strips", "dj_booth"])
    strip_index = 0
    for x in (-13.3, 13.3):
        for z in (-4.0, 4.0):
            strip_index += 1
            add(matrix, "bar", BAR_CH_COUNT, f"dled_sky{strip_index}", f"Skybox Strip {strip_index}",
                (x, 3.6, z), "Elation DLED 60 Strip", "1 strip",
                "assumed count and position", "Skybox Strips",
                ["led_strips", "skybox_strips"])

    # Off both ends of each spot truss, so they share its steel.
    strobe_index = 0
    for z, half in ((-7.5, 8.0), (-2.5, 10.5), (2.5, 10.5), (7.5, 8.0)):
        for x in (-half, half):
            strobe_index += 1
            add(matrix, "strobe", STROBE_CH_COUNT, f"atomic_{strobe_index}", f"Atomic Strobe {strobe_index}",
                (x, 6.5, z), "Martin Atomic 3000 DMX", "1 fixture",
                "assumed count and position", "Strobes",
                ["truss_strobes"])

    # --- Universe 2: colour floods and pars ----------------------------------
    floods = _AddressAllocator(universe=2)

    # About 300 floods folded into 12 segments of 25 round the dome's edge.
    for i, pos in enumerate(_ring_positions(12, LIV_DOME_RADIUS - 0.5, 7.0, 15.0)):
        add(floods, "par", BAR_CH_COUNT, f"dome_rim{i+1}", f"Dome Rim {i+1}",
            pos, "Color Kinetics ColorBlast 12", "about 25 floods",
            "sourced: about 300 floods; segment count assumed", "Dome Rim",
            ["dome_pixels", "dome_rim"])

    # Left wall then right wall, so par N and par N+3 are a mirrored pair; then
    # the pair at the foot of the staircase.
    par_index = 0
    for x in (-12.6, 12.6):
        for z in (-6.0, 0.0, 6.0):
            par_index += 1
            add(floods, "par", BAR_CH_COUNT, f"tripar_{par_index}", f"Tri Par {par_index}",
                (x, 0.3, z), "Elation Opti Tri Par", "1 fixture",
                "assumed count and position", "Wall Pars",
                ["led_pars", "wall_pars"])
    for x in (-4.0, 4.0):
        par_index += 1
        add(floods, "par", BAR_CH_COUNT, f"tripar_{par_index}", f"Tri Par {par_index}",
            (x, 0.3, 12.6), "Elation Opti Tri Par", "1 fixture",
            "assumed count and position", "Staircase Pars",
            ["led_pars", "staircase_pars"])

    # --- Universe 3: LED walls and booth wash --------------------------------
    booth = _AddressAllocator(universe=3)

    # The press says the booth has LED walls and nothing about their size, make
    # or how they are fed. A video wall is not a lighting fixture, so this is a
    # stand-in the engine can colour: a centre wall and a wing each side, cut
    # into cells about a metre wide. They are on the upstage wall, where the 3D
    # view brackets a fixture to the wall instead of standing it on the floor.
    #
    # The wall starts at 3.2 m: the view's DJ camera stands behind this wall at
    # head height and looks out through it, and its speaker stacks and the DJ
    # reach about 2.1 m. An odd number of centre columns keeps every cell off
    # x = +/-0.5, where the engine divides its left, centre and right groups.
    wall_rows = (5.2, 4.4, 3.6)
    for r, y in enumerate(wall_rows, start=1):
        for c, x in enumerate((-2.4, -1.2, 0.0, 1.2, 2.4), start=1):
            add(booth, "bar", BAR_CH_COUNT, f"ledwall_c_r{r}c{c}", f"LED Wall Centre R{r} C{c}",
                (x, y, LIV_LED_WALL_Z), "LED video wall (make and model not reported)",
                "about 1.2 x 0.8 m of wall",
                "sourced: LED walls at the booth; size, layout and cell count assumed",
                "LED Wall Centre", ["led_wall", "led_wall_centre", "dj_booth"])
    for r, y in enumerate(wall_rows, start=1):
        for c, x in enumerate((-5.5, -4.5, 4.5, 5.5), start=1):
            add(booth, "bar", BAR_CH_COUNT, f"ledwall_w_r{r}c{c}", f"LED Wall Wing R{r} C{c}",
                (x, y, LIV_LED_WALL_Z), "LED video wall (make and model not reported)",
                "about 1.0 x 0.8 m of wall",
                "sourced: LED walls at the booth; size, layout and cell count assumed",
                "LED Wall Wings", ["led_wall", "led_wall_wings", "dj_booth"])

    # Two pars over the wall to light the DJ. The press lists no booth wash.
    for i, x in enumerate((-3.5, 3.5), start=1):
        add(booth, "par", BAR_CH_COUNT, f"booth_wash_{i}", f"Booth Wash {i}",
            (x, 6.0, LIV_LED_WALL_Z), "Elation Opti Tri Par", "1 fixture",
            "assumed: no booth wash is reported", "Booth Wash",
            ["led_pars", "booth_wash", "dj_booth"])

    key_zones = [
        KeyZoneSpec("dj_booth", ["ds300_2", "ds300_3"], active=True, min_intensity=0.0),
    ]

    return VenuePreset(
        name="liv_miami_approx",
        display_name="LIV Miami (approximate recreation)",
        description=(
            f"{LIV_DISCLAIMER} Round room under an 88 ft dome: 22 dance-floor spots, 4 mezzanine "
            "spots, 8 moving washes at 10 ft, the dome's LED spokes and rim floods folded into "
            "44 cells, 8 LED strips, 8 pars and 8 strobes, plus a stand-in for the booth's LED "
            "walls (27 cells) and 2 booth wash pars. 131 fixtures on 4 universes."
        ),
        size=VenueSize.LIV_MIAMI_APPROX,
        stage=stage,
        fixtures=fixtures,
        key_zones=key_zones,
        default_genre="edm",
        default_bpm=128.0,
        disclaimer=LIV_DISCLAIMER,
        room=_liv_room_shell(),
    )


# Build all presets
VENUE_PRESETS: Dict[str, VenuePreset] = {
    "liv_miami_approx": _build_liv_miami_approx(),
    "small_nightclub": _build_small_nightclub(),
    "club_night": _build_club_night(),
    "medium_venue": _build_medium_venue(),
    "pro_beam_room": _build_pro_beam_room(),
    "large_concert": _build_large_concert(),
    "festival_mainstage": _build_festival_mainstage(),
    "bigroom_edm": _build_bigroom_edm(),
}


def create_venue_rig(preset_name: str):
    """
    Create a FixtureGroupManager from a venue preset.

    Args:
        preset_name: Name of the venue preset

    Returns:
        (FixtureGroupManager, VenuePreset) tuple, or (None, None) if not found
    """
    from ..effects.fixture_groups import Fixture, FixtureGroupManager

    preset = VENUE_PRESETS.get(preset_name)
    if preset is None:
        return None, None

    manager = FixtureGroupManager()
    fixtures = []

    # Channel mapping by fixture type
    channel_maps = {
        "mover": MOVER_CHANNELS,
        "wash": WASH_CHANNELS,
        "bar": BAR_CHANNELS,
        "strobe": STROBE_CHANNELS,
        "spot": SPOT_CHANNELS,
    }

    for spec in preset.fixtures:
        channels = channel_maps.get(spec.fixture_type, BAR_CHANNELS)
        pan_range, tilt_range = FIXTURE_RANGES.get(spec.fixture_type, STATIC_RANGES)
        if 'pan' not in channels:
            pan_range = 0.0
        if 'tilt' not in channels:
            tilt_range = 0.0
        fixture = Fixture(
            id=spec.id,
            name=spec.name,
            dmx_address=spec.dmx_address,
            universe=spec.universe,
            channels=channels.copy(),
            x=spec.x,
            y=spec.y,
            z=spec.z,
            fixture_type=PRESET_ENGINE_TYPES.get(spec.fixture_type, 'wash'),
            pan_range=pan_range,
            tilt_range=tilt_range,
        )
        fixtures.append(fixture)

    manager.add_fixtures(fixtures)

    # Type groups, in the same shape the rig loader builds them so a preset rig
    # and a patched rig expose the same group names.
    type_groups: Dict[str, List[str]] = {name: [] for name in ENGINE_TYPE_GROUP_NAMES}
    for f in fixtures:
        type_groups.setdefault(f.fixture_type, []).append(f.id)

    for type_name, group_name in ENGINE_TYPE_GROUP_NAMES.items():
        manager.create_custom_group(group_name, list(type_groups.get(type_name, [])))

    manager.create_custom_group(
        "movers_washes",
        list(type_groups.get("mover", [])) + list(type_groups.get("wash", [])),
    )

    # The preset's own groups. One named like a group above would replace the
    # group the engine looks up for every effect, so it is left out.
    reserved = set(manager.groups)
    for name, ids in preset.groups.items():
        if name in reserved:
            logging.getLogger(__name__).warning(
                "Venue preset %s: group '%s' is one of the engine's own and was not created",
                preset.name, name,
            )
            continue
        manager.create_custom_group(name, list(ids))

    return manager, preset
