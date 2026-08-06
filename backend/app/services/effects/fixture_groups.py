"""
Fixture Grouping System
Manages fixture groups for applying effects (odd/even, left/right, etc.)
"""

from enum import Enum
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
import math


class GroupType(Enum):
    """Predefined group types for common fixture arrangements."""
    ALL = "all"
    ODD = "odd"
    EVEN = "even"
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    OUTER = "outer"
    FRONT = "front"
    BACK = "back"
    CUSTOM = "custom"


@dataclass
class Fixture:
    """Represents a single fixture with DMX addressing and position."""
    id: str
    name: str
    dmx_address: int
    universe: int = 0

    # Channel offsets within fixture
    channels: Dict[str, int] = field(default_factory=dict)

    # Physical position (for spatial effects)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    # Fixture type for grouping
    fixture_type: str = "mover"  # mover, wash, bar, strobe

    # Physical capability, read from the fixture profile
    pan_range: float = 540.0
    tilt_range: float = 270.0

    # Profile clamps: channel name -> (min_value, max_value)
    channel_limits: Dict[str, tuple] = field(default_factory=dict)

    # Profile homes: channel name -> the DMX value the profile parks it at
    channel_defaults: Dict[str, int] = field(default_factory=dict)

    # Current state
    pan: float = 0.0
    tilt: float = 0.0
    dimmer: float = 0.0
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    white: float = 0.0
    strobe: float = 0.0
    amber: float = 0.0
    uv: float = 0.0
    lime: float = 0.0
    indigo: float = 0.0
    zoom: float = 0.5
    focus: float = 0.5
    gobo: float = 0.0
    gobo_rotation: float = 0.0
    gobo2: float = 0.0
    gobo2_rotation: float = 0.0
    animation: float = 0.0
    prism: float = 0.0
    color_wheel: float = 0.0
    # Mechanical flags carry the channel's own value, where 0 is iris open, frost
    # and framing out of the beam, and no colour correction.
    iris: float = 0.0
    frost: float = 0.0
    framing: float = 0.0
    cto: float = 0.0
    ctb: float = 0.0

    def has_channel(self, name: str) -> bool:
        """Check whether the fixture's profile declares a channel type."""
        return name in self.channels

    # Beam optics state (0-1 normalized)
    gobo_index: float = 0.0        # 0 = open/no gobo, >0 = gobo pattern selection
    gobo_rotation: float = 0.0     # Gobo rotation speed/position
    zoom: float = 0.5              # Zoom (0 = narrow, 1 = wide)
    iris: float = 1.0              # Iris (0 = closed, 1 = open)
    frost: float = 0.0             # Frost (0 = sharp, 1 = full frost)
    prism: float = 0.0             # Prism (0 = out, 1 = in)

    def get_channel_address(self, channel_name: str) -> Optional[int]:
        """Get absolute DMX address for a channel."""
        if channel_name in self.channels:
            return self.dmx_address + self.channels[channel_name]
        return None

    def set_color_rgb(self, r: float, g: float, b: float):
        """Set RGB color (0-1 range)."""
        self.red = max(0, min(1, r))
        self.green = max(0, min(1, g))
        self.blue = max(0, min(1, b))

    def set_color_hsv(self, h: float, s: float, v: float):
        """Set color from HSV (h: 0-360, s: 0-1, v: 0-1)."""
        h = h % 360
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        self.red = r + m
        self.green = g + m
        self.blue = b + m


@dataclass
class FixtureGroup:
    """A group of fixtures that can be controlled together."""
    name: str
    group_type: GroupType
    fixture_ids: List[str] = field(default_factory=list)

    # Phase offset for chase effects (0-1 per fixture)
    phase_offsets: List[float] = field(default_factory=list)

    def __post_init__(self):
        # Auto-generate phase offsets if not provided
        if not self.phase_offsets and self.fixture_ids:
            count = len(self.fixture_ids)
            self.phase_offsets = [i / count for i in range(count)]

    def get_phase_offset(self, fixture_index: int) -> float:
        """Get phase offset for a fixture in this group."""
        if fixture_index < len(self.phase_offsets):
            return self.phase_offsets[fixture_index]
        return 0.0


COLOR_CHANNELS = ('red', 'green', 'blue', 'white', 'amber', 'uv', 'lime', 'indigo')
RGB_CHANNELS = ('red', 'green', 'blue')
# Subtractive mixing: each flag removes the additive component it is paired with.
CMY_CHANNELS = {'cyan': 'red', 'magenta': 'green', 'yellow': 'blue'}
COLOR_BEARING_CHANNELS = COLOR_CHANNELS + tuple(CMY_CHANNELS)
LEVEL_CHANNELS = (
    'zoom', 'focus', 'gobo', 'gobo_rotation', 'gobo2', 'gobo2_rotation',
    'animation', 'prism', 'color_wheel', 'iris', 'frost', 'framing', 'cto', 'ctb',
)
PASSIVE_CHANNELS = ('macro', 'effect', 'speed')


def _level(value, default: float = 0.0) -> float:
    """A state value as a float. Profiles and adapters may hand us None."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_byte(value) -> int:
    """Scale a 0-1 state value to a DMX byte."""
    return max(0, min(255, int(_level(value) * 255)))


def canonical_channel_name(name: str) -> str:
    """The channel type a repeated-channel alias ("dimmer_2") stands for."""
    text = str(name)
    base, _, suffix = text.rpartition('_')
    return base if base and suffix.isdigit() else text


def _render_fixture(fixture: Fixture) -> Dict[str, int]:
    """Map a fixture's state onto the channel types its profile declares."""
    values: Dict[str, int] = {}
    homes = fixture.channel_defaults or {}

    def home(name: str) -> int:
        """Where a channel the engine is not commanding parks.

        0 is not universally safe: on a blade or a wheel rotation it is a
        mechanical end stop, which is why profiles carry a default per channel.
        """
        try:
            return max(0, min(255, int(homes.get(name, 0))))
        except (TypeError, ValueError):
            return 0

    dimmer = max(0.0, min(1.0, _level(fixture.dimmer)))

    has_dimmer = fixture.has_channel('dimmer')
    if has_dimmer:
        values['dimmer'] = _to_byte(dimmer)
        color_scale = 1.0
    elif any(fixture.has_channel(name) for name in COLOR_BEARING_CHANNELS):
        # No intensity channel: intensity has to live in the colour values.
        color_scale = dimmer
    else:
        color_scale = 1.0

    for name in COLOR_CHANNELS:
        if fixture.has_channel(name):
            values[name] = _to_byte(_level(getattr(fixture, name, 0.0)) * color_scale)

    # A fixture that also declares additive red/green/blue emitters mixes
    # additively, so its cyan/magenta/yellow are emitters of their own rather
    # than subtractive flags. Complementing those lights them fully at blackout.
    subtractive = not any(fixture.has_channel(name) for name in RGB_CHANNELS)

    # 0 is full open on a subtractive flag: intensity scales the additive component
    # before it is complemented, or a blackout would open every flag to white.
    for name, source in CMY_CHANNELS.items():
        if not fixture.has_channel(name):
            continue
        if subtractive:
            values[name] = 255 - _to_byte(_level(getattr(fixture, source, 0.0)) * color_scale)
        else:
            values[name] = home(name)

    # A pan_range of 0 marks a fixture that cannot move, so neither axis is driven.
    pan_range = _level(fixture.pan_range)
    tilt_range = _level(fixture.tilt_range)
    if pan_range > 0:
        if fixture.has_channel('pan'):
            pan_norm = max(0.0, min(1.0, (_level(fixture.pan) + pan_range / 2.0) / pan_range))
            if fixture.has_channel('pan_fine'):
                pan_16 = int(round(pan_norm * 65535.0))
                values['pan'] = (pan_16 >> 8) & 0xFF
                values['pan_fine'] = pan_16 & 0xFF
            else:
                values['pan'] = int(round(pan_norm * 255.0))

        if tilt_range > 0 and fixture.has_channel('tilt'):
            tilt_norm = max(0.0, min(1.0, (_level(fixture.tilt) + tilt_range / 2.0) / tilt_range))
            if fixture.has_channel('tilt_fine'):
                tilt_16 = int(round(tilt_norm * 65535.0))
                values['tilt'] = (tilt_16 >> 8) & 0xFF
                values['tilt_fine'] = tilt_16 & 0xFF
            else:
                values['tilt'] = int(round(tilt_norm * 255.0))

    strobe = max(0.0, min(1.0, _level(fixture.strobe)))
    if fixture.has_channel('shutter'):
        values['shutter'] = _to_byte(strobe) if strobe > 0 else 255
    if fixture.has_channel('strobe'):
        # A dedicated strobe channel rates the flash; 0 is "no strobe", not "closed".
        values['strobe'] = _to_byte(strobe)

    at_home = set()
    for name in LEVEL_CHANNELS + PASSIVE_CHANNELS:
        if fixture.has_channel(name):
            level = _level(getattr(fixture, name, 0.0))
            if level > 0.0:
                values[name] = _to_byte(level)
            else:
                values[name] = home(name)
                at_home.add(name)

    # Repeated channel types (per-cell dimmers, multi-zone colour) carry the same
    # value as the channel that owns the canonical name; leaving them at 0 puts a
    # cell fixture at a fraction of its output or blacks it out entirely. A
    # repeat that is only parked follows its own profile home instead.
    for name in fixture.channels:
        if name in values:
            continue
        base = canonical_channel_name(name)
        if base != name and base in values:
            values[name] = home(name) if base in at_home else values[base]

    return values


class FixtureGroupManager:
    """
    Manages fixtures and groups for effect application.
    """

    def __init__(self):
        self.fixtures: Dict[str, Fixture] = {}
        self.groups: Dict[str, FixtureGroup] = {}

        # Create default groups
        self._create_default_groups()

    def _create_default_groups(self):
        """Create standard group types."""
        self.groups = {
            GroupType.ALL.value: FixtureGroup(
                name="All Fixtures",
                group_type=GroupType.ALL
            ),
            GroupType.ODD.value: FixtureGroup(
                name="Odd Fixtures",
                group_type=GroupType.ODD
            ),
            GroupType.EVEN.value: FixtureGroup(
                name="Even Fixtures",
                group_type=GroupType.EVEN
            ),
            GroupType.LEFT.value: FixtureGroup(
                name="Left Side",
                group_type=GroupType.LEFT
            ),
            GroupType.RIGHT.value: FixtureGroup(
                name="Right Side",
                group_type=GroupType.RIGHT
            ),
            GroupType.CENTER.value: FixtureGroup(
                name="Center",
                group_type=GroupType.CENTER
            ),
            GroupType.OUTER.value: FixtureGroup(
                name="Outer",
                group_type=GroupType.OUTER
            )
        }

    def add_fixture(self, fixture: Fixture):
        """Add a fixture and auto-assign to groups."""
        self.fixtures[fixture.id] = fixture
        self._update_group_assignments()

    def add_fixtures(self, fixtures: List[Fixture]):
        """Add multiple fixtures."""
        for fixture in fixtures:
            self.fixtures[fixture.id] = fixture
        self._update_group_assignments()

    @staticmethod
    def _auto_group_keys() -> List[str]:
        """Keys of the groups this manager rebuilds automatically.

        Everything else in self.groups is caller-owned (custom groups) and is
        left untouched by _update_group_assignments.
        """
        return [gt.value for gt in GroupType if gt is not GroupType.CUSTOM]

    def _update_group_assignments(self):
        """Auto-assign fixtures to groups based on position and index."""
        fixture_list = list(self.fixtures.values())
        fixture_list.sort(key=lambda f: (f.x, f.z))  # Sort left-to-right, front-to-back

        # Clear existing assignments.
        # Only the auto-managed GroupType groups are rebuilt here; custom groups
        # are owned by whoever created them and must survive fixture adds.
        for key in self._auto_group_keys():
            group = self.groups.get(key)
            if group is None:
                continue
            group.fixture_ids = []
            group.phase_offsets = []

        # Calculate center point
        if fixture_list:
            center_x = sum(f.x for f in fixture_list) / len(fixture_list)
        else:
            center_x = 0

        for i, fixture in enumerate(fixture_list):
            fixture_id = fixture.id

            # All fixtures
            self.groups[GroupType.ALL.value].fixture_ids.append(fixture_id)

            # Odd/Even (1-indexed for user-friendliness)
            if (i + 1) % 2 == 1:
                self.groups[GroupType.ODD.value].fixture_ids.append(fixture_id)
            else:
                self.groups[GroupType.EVEN.value].fixture_ids.append(fixture_id)

            # Left/Right/Center based on X position
            if fixture.x < center_x - 0.5:
                self.groups[GroupType.LEFT.value].fixture_ids.append(fixture_id)
            elif fixture.x > center_x + 0.5:
                self.groups[GroupType.RIGHT.value].fixture_ids.append(fixture_id)
            else:
                self.groups[GroupType.CENTER.value].fixture_ids.append(fixture_id)

            # Outer (first and last quarter)
            if i < len(fixture_list) * 0.25 or i >= len(fixture_list) * 0.75:
                self.groups[GroupType.OUTER.value].fixture_ids.append(fixture_id)

        # Update phase offsets for the auto-managed groups only. Custom groups
        # may carry caller-supplied chase offsets, which this must not clobber.
        for key in self._auto_group_keys():
            group = self.groups.get(key)
            if group is None:
                continue
            count = len(group.fixture_ids)
            if count > 0:
                group.phase_offsets = [i / count for i in range(count)]

    def create_custom_group(
        self,
        name: str,
        fixture_ids: List[str],
        phase_offsets: Optional[List[float]] = None
    ) -> FixtureGroup:
        """Create a custom fixture group."""
        group = FixtureGroup(
            name=name,
            group_type=GroupType.CUSTOM,
            fixture_ids=fixture_ids,
            phase_offsets=phase_offsets or []
        )
        self.groups[name] = group
        return group

    def get_group(self, group_name: str) -> Optional[FixtureGroup]:
        """Get a group by name."""
        return self.groups.get(group_name)

    def get_fixtures_in_group(self, group_name: str) -> List[Fixture]:
        """Get all fixtures in a group."""
        group = self.groups.get(group_name)
        if not group:
            return []
        return [
            self.fixtures[fid]
            for fid in group.fixture_ids
            if fid in self.fixtures
        ]

    def get_fixture(self, fixture_id: str) -> Optional[Fixture]:
        """Get a single fixture by ID."""
        return self.fixtures.get(fixture_id)

    def apply_to_group(
        self,
        group_name: str,
        func: Callable[[Fixture, int, float], None]
    ):
        """
        Apply a function to all fixtures in a group.

        Args:
            group_name: Name of the group
            func: Function(fixture, index, phase_offset) to apply
        """
        group = self.groups.get(group_name)
        if not group:
            return

        for i, fixture_id in enumerate(group.fixture_ids):
            fixture = self.fixtures.get(fixture_id)
            if fixture:
                phase = group.get_phase_offset(i)
                func(fixture, i, phase)

    def get_universes(self) -> List[int]:
        """Sorted universes holding at least one fixture that can actually be driven.

        A fixture patched past the end of a universe renders nothing, so counting it
        here would put a permanently blank universe on the wire at frame rate.
        """
        return sorted({
            fixture.universe
            for fixture in self.fixtures.values()
            if 0 <= fixture.dmx_address - 1 < 512
        })

    def get_dmx_frames(self) -> Dict[int, List[int]]:
        """
        Generate a DMX frame for every universe that holds fixtures.

        Returns:
            Mapping of universe number to 512-element list of DMX values
        """
        return {universe: self.get_dmx_frame(universe) for universe in self.get_universes()}

    def get_dmx_frame(self, universe: int = 0) -> List[int]:
        """
        Generate DMX frame from current fixture states.

        Returns:
            512-element list of DMX values
        """
        frame = [0] * 512

        for fixture in self.fixtures.values():
            if fixture.universe != universe:
                continue

            base = fixture.dmx_address - 1  # DMX is 1-indexed
            if base < 0 or base >= 512:
                continue

            channel_values = _render_fixture(fixture)

            for channel_name, offset in fixture.channels.items():
                if channel_name not in channel_values:
                    continue
                addr = base + offset
                if not 0 <= addr < 512:
                    continue

                value = channel_values[channel_name]
                limits = (fixture.channel_limits or {}).get(channel_name)
                if isinstance(limits, (tuple, list)) and len(limits) >= 2:
                    low, high = limits[0], limits[1]
                    # A floor may not defeat blackout: 0 out stays 0 on the wire.
                    if low is not None and value > 0:
                        value = max(int(low), value)
                    if high is not None:
                        value = min(int(high), value)

                frame[addr] = max(0, min(255, value))

        return frame


def create_demo_rig() -> FixtureGroupManager:
    """Create the demo rig with 18 fixtures matching the visualizer."""
    manager = FixtureGroupManager()

    # Channel mapping for mover (16 channels)
    mover_channels = {
        'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
        'speed': 4, 'dimmer': 5, 'shutter': 6,
        'red': 7, 'green': 8, 'blue': 9, 'white': 10,
        'color_wheel': 11, 'gobo': 12, 'gobo_rotation': 13,
        'prism': 14, 'focus': 15
    }

    # Channel mapping for wash (14 channels)
    wash_channels = {
        'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
        'speed': 4, 'dimmer': 5, 'shutter': 6,
        'red': 7, 'green': 8, 'blue': 9, 'white': 10,
        'zoom': 11, 'other': 12, 'other_2': 13
    }

    # Channel mapping for LED bar (12 channels)
    bar_channels = {
        'dimmer': 0, 'strobe': 1,
        'red': 2, 'green': 3, 'blue': 4, 'white': 5,
        'amber': 6, 'uv': 7, 'macro': 8, 'speed': 9,
        'other': 10, 'other_2': 11
    }

    fixtures = []

    # Moving Heads - Upstage truss (single straight line)
    for i, (addr, x) in enumerate([(1, -6), (17, -4), (33, -2), (49, 0)]):
        fixtures.append(Fixture(
            id=f"mover_l{i+1}",
            name=f"Mover L{i+1}",
            dmx_address=addr,
            channels=mover_channels.copy(),
            x=x, y=5.2, z=-1.0,
            fixture_type="mover"
        ))

    # Moving Heads - Upstage truss continuation
    for i, (addr, x) in enumerate([(65, 2), (81, 4), (97, 6), (113, 8)]):
        fixtures.append(Fixture(
            id=f"mover_r{i+1}",
            name=f"Mover R{i+1}",
            dmx_address=addr,
            channels=mover_channels.copy(),
            x=x, y=5.2, z=-1.0,
            fixture_type="mover"
        ))

    # Washes - Downstage truss (single straight line)
    for i, (addr, x) in enumerate([(129, -5), (143, -3), (157, -1)]):
        fixtures.append(Fixture(
            id=f"wash_l{i+1}",
            name=f"Wash L{i+1}",
            dmx_address=addr,
            channels=wash_channels.copy(),
            x=x, y=4.6, z=1.0,
            fixture_type="wash"
        ))

    # Washes - Downstage truss continuation
    for i, (addr, x) in enumerate([(171, 1), (185, 3), (199, 5)]):
        fixtures.append(Fixture(
            id=f"wash_r{i+1}",
            name=f"Wash R{i+1}",
            dmx_address=addr,
            channels=wash_channels.copy(),
            x=x, y=4.6, z=1.0,
            fixture_type="wash"
        ))

    # LED Bars - mounted on rear of downstage truss
    for i, (addr, x) in enumerate([(213, -3), (225, -1), (237, 1), (249, 3)]):
        fixtures.append(Fixture(
            id=f"bar_{i+1}",
            name=f"Bar {i+1}",
            dmx_address=addr,
            channels=bar_channels.copy(),
            x=x, y=4.9, z=1.0,
            fixture_type="bar"
        ))

    manager.add_fixtures(fixtures)

    # Create fixture-type groups
    movers = [f.id for f in fixtures if f.fixture_type == "mover"]
    washes = [f.id for f in fixtures if f.fixture_type == "wash"]
    bars = [f.id for f in fixtures if f.fixture_type == "bar"]

    manager.create_custom_group("movers", movers)
    manager.create_custom_group("washes", washes)
    manager.create_custom_group("bars", bars)
    manager.create_custom_group("movers_washes", movers + washes)

    return manager
