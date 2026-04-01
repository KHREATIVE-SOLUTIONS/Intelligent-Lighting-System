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

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class VenueSize(Enum):
    SMALL_NIGHTCLUB = "small_nightclub"
    MEDIUM_VENUE = "medium_venue"
    PRO_BEAM_ROOM = "pro_beam_room"
    LARGE_CONCERT = "large_concert"
    FESTIVAL_MAINSTAGE = "festival_mainstage"


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


@dataclass
class KeyZoneSpec:
    """Specification for a key lighting zone."""
    zone: str             # PerformerZone value
    fixture_ids: List[str]
    active: bool = True
    min_intensity: float = 0.4


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

    def __post_init__(self):
        if not self.fixture_counts:
            counts = {}
            for f in self.fixtures:
                counts[f.fixture_type] = counts.get(f.fixture_type, 0) + 1
            self.fixture_counts = counts


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
    'zoom': 11, 'color_temp': 12, 'control': 13
}
WASH_CH_COUNT = 14

BAR_CHANNELS = {
    'dimmer': 0, 'strobe': 1,
    'red': 2, 'green': 3, 'blue': 4, 'white': 5,
    'amber': 6, 'uv': 7, 'macro': 8, 'speed': 9,
    'mode': 10, 'control': 11
}
BAR_CH_COUNT = 12

STROBE_CHANNELS = {
    'dimmer': 0, 'strobe': 1, 'duration': 2, 'rate': 3,
}
STROBE_CH_COUNT = 4

SPOT_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'dimmer': 4, 'shutter': 5,
    'red': 6, 'green': 7, 'blue': 8, 'white': 9,
    'zoom': 10, 'focus': 11
}
SPOT_CH_COUNT = 12


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
    addr = 1

    # 2 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.0, 3.0), 2.8, -2.0)):
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

    # 2 movers rear
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.0, 3.0), 2.8, 2.0)):
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

    # 2 bars floor
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-2.5, 2.5), 0.5, -2.5)):
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", addr, 0, x, y, z))
        addr += BAR_CH_COUNT

    # 2 bars truss
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-2.5, 2.5), 2.5, 0.0)):
        fixtures.append(FixtureSpec("bar", f"bar_truss{i+1}", f"Bar Truss {i+1}", addr, 0, x, y, z))
        addr += BAR_CH_COUNT

    # 2 strobes
    for i, (x, y, z) in enumerate(_distribute_positions(2, (-3.5, 3.5), 2.8, -1.0)):
        fixtures.append(FixtureSpec("strobe", f"strobe{i+1}", f"Strobe {i+1}", addr, 0, x, y, z))
        addr += STROBE_CH_COUNT

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
    addr = 1

    # 7 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(7, (-5.2, 5.2), 4.5, -1.1)):
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

    # 7 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(7, (-5.2, 5.2), 4.5, 1.1)):
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

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
    addr = 1

    # 8 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-8.0, 8.0), 7.0, -5.0)):
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

    # 8 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-8.0, 8.0), 7.0, 5.0)):
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", addr, 0, x, y, z))
        addr += MOVER_CH_COUNT

    # 6 bars floor (downstage)
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-7.0, 7.0), 0.5, -5.5)):
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", addr, 0, x, y, z))
        addr += BAR_CH_COUNT

    # 6 bars mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-7.0, 7.0), 6.5, 0.0)):
        fixtures.append(FixtureSpec("bar", f"bar_truss{i+1}", f"Bar Truss {i+1}", addr, 0, x, y, z))
        addr += BAR_CH_COUNT

    # 8 strobes (4 front + 4 rear)
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-7.5, 7.5), 7.0, -4.0)):
        fixtures.append(FixtureSpec("strobe", f"strobe_f{i+1}", f"Strobe Front {i+1}", addr, 0, x, y, z))
        addr += STROBE_CH_COUNT
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-7.5, 7.5), 7.0, 4.0)):
        fixtures.append(FixtureSpec("strobe", f"strobe_r{i+1}", f"Strobe Rear {i+1}", addr, 0, x, y, z))
        addr += STROBE_CH_COUNT

    # 4 spots
    spots = [
        ("spot_dj", "DJ Spot", 0.0, 6.5, -5.5),
        ("spot_center", "Center Spot", 0.0, 7.0, 0.0),
        ("spot_left", "Stage Left Spot", -6.0, 6.5, 0.0),
        ("spot_right", "Stage Right Spot", 6.0, 6.5, 0.0),
    ]
    for sid, sname, sx, sy, sz in spots:
        fixtures.append(FixtureSpec("spot", sid, sname, addr, 0, sx, sy, sz))
        addr += SPOT_CH_COUNT

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

    truss_rows = [
        ("f", "Front", -7.0, 10),
        ("ff", "Front Fill", -3.5, 10),
        ("m", "Mid", 0.0, 12),
        ("rr", "Rear Fill", 3.5, 10),
        ("r", "Rear", 7.0, 10),
    ]

    for row_key, row_name, z, count in truss_rows:
        for i, (x, y, zz) in enumerate(_distribute_positions(count, (-10.5, 10.5), 9.2, z)):
            a, u = next_addr(MOVER_CH_COUNT)
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

    # 12 movers front truss
    for i, (x, y, z) in enumerate(_distribute_positions(12, (-16.0, 16.0), 13.0, -8.0)):
        a, u = next_addr(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_f{i+1}", f"Mover Front {i+1}", a, u, x, y, z))

    # 10 movers mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(10, (-14.0, 14.0), 12.0, 0.0)):
        a, u = next_addr(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_m{i+1}", f"Mover Mid {i+1}", a, u, x, y, z))

    # 10 movers rear truss
    for i, (x, y, z) in enumerate(_distribute_positions(10, (-14.0, 14.0), 13.0, 8.0)):
        a, u = next_addr(MOVER_CH_COUNT)
        fixtures.append(FixtureSpec("mover", f"mover_r{i+1}", f"Mover Rear {i+1}", a, u, x, y, z))

    # 8 bars floor
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-15.0, 15.0), 0.5, -9.0)):
        a, u = next_addr(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_floor{i+1}", f"Bar Floor {i+1}", a, u, x, y, z))

    # 8 bars mid truss
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-14.0, 14.0), 11.0, 0.0)):
        a, u = next_addr(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_mid{i+1}", f"Bar Mid {i+1}", a, u, x, y, z))

    # 8 bars rear
    for i, (x, y, z) in enumerate(_distribute_positions(8, (-14.0, 14.0), 11.0, 7.0)):
        a, u = next_addr(BAR_CH_COUNT)
        fixtures.append(FixtureSpec("bar", f"bar_rear{i+1}", f"Bar Rear {i+1}", a, u, x, y, z))

    # 16 strobes (distributed across front/mid/rear)
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-16.0, 16.0), 13.0, -7.0)):
        a, u = next_addr(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_f{i+1}", f"Strobe Front {i+1}", a, u, x, y, z))
    for i, (x, y, z) in enumerate(_distribute_positions(4, (-14.0, 14.0), 12.0, 0.0)):
        a, u = next_addr(STROBE_CH_COUNT)
        fixtures.append(FixtureSpec("strobe", f"strobe_m{i+1}", f"Strobe Mid {i+1}", a, u, x, y, z))
    for i, (x, y, z) in enumerate(_distribute_positions(6, (-16.0, 16.0), 13.0, 7.0)):
        a, u = next_addr(STROBE_CH_COUNT)
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
        a, u = next_addr(SPOT_CH_COUNT)
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


# Build all presets
VENUE_PRESETS: Dict[str, VenuePreset] = {
    "small_nightclub": _build_small_nightclub(),
    "medium_venue": _build_medium_venue(),
    "pro_beam_room": _build_pro_beam_room(),
    "large_concert": _build_large_concert(),
    "festival_mainstage": _build_festival_mainstage(),
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
        fixture = Fixture(
            id=spec.id,
            name=spec.name,
            dmx_address=spec.dmx_address,
            universe=spec.universe,
            channels=channels.copy(),
            x=spec.x,
            y=spec.y,
            z=spec.z,
            fixture_type=spec.fixture_type,
        )
        fixtures.append(fixture)

    manager.add_fixtures(fixtures)

    # Create type-based groups
    type_groups = {}
    for f in fixtures:
        if f.fixture_type not in type_groups:
            type_groups[f.fixture_type] = []
        type_groups[f.fixture_type].append(f.id)

    for type_name, ids in type_groups.items():
        manager.create_custom_group(f"{type_name}s", ids)

    # Create combined mover+wash group
    movers = type_groups.get("mover", [])
    washes = type_groups.get("wash", [])
    if movers or washes:
        manager.create_custom_group("movers_washes", movers + washes)

    return manager, preset
