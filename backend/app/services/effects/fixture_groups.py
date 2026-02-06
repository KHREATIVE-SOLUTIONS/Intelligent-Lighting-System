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

    # Current state
    pan: float = 0.0
    tilt: float = 0.0
    dimmer: float = 0.0
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    white: float = 0.0
    strobe: float = 0.0

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

    def _update_group_assignments(self):
        """Auto-assign fixtures to groups based on position and index."""
        fixture_list = list(self.fixtures.values())
        fixture_list.sort(key=lambda f: (f.x, f.z))  # Sort left-to-right, front-to-back

        # Clear existing assignments
        for group in self.groups.values():
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

        # Update phase offsets for all groups
        for group in self.groups.values():
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

            # Map fixture state to channels
            channel_values = {
                'pan': int(((fixture.pan + 270) / 540) * 255),  # -270 to +270 -> 0-255
                'tilt': int(((fixture.tilt + 135) / 270) * 255),  # -135 to +135 -> 0-255
                'dimmer': int(fixture.dimmer * 255),
                'red': int(fixture.red * 255),
                'green': int(fixture.green * 255),
                'blue': int(fixture.blue * 255),
                'white': int(fixture.white * 255),
                'shutter': int(fixture.strobe * 255) if fixture.strobe > 0 else 255,  # 255 = open
            }

            for channel_name, offset in fixture.channels.items():
                addr = base + offset
                if 0 <= addr < 512 and channel_name in channel_values:
                    frame[addr] = max(0, min(255, channel_values[channel_name]))

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
        'zoom': 11, 'color_temp': 12, 'control': 13
    }

    # Channel mapping for LED bar (12 channels)
    bar_channels = {
        'dimmer': 0, 'strobe': 1,
        'red': 2, 'green': 3, 'blue': 4, 'white': 5,
        'amber': 6, 'uv': 7, 'macro': 8, 'speed': 9,
        'mode': 10, 'control': 11
    }

    fixtures = []

    # Moving Heads - Left side
    for i, (addr, z) in enumerate([(1, -4), (17, -1.5), (33, 1.5), (49, 4)]):
        fixtures.append(Fixture(
            id=f"mover_l{i+1}",
            name=f"Mover L{i+1}",
            dmx_address=addr,
            channels=mover_channels.copy(),
            x=-6, y=4, z=z,
            fixture_type="mover"
        ))

    # Moving Heads - Right side
    for i, (addr, z) in enumerate([(65, -4), (81, -1.5), (97, 1.5), (113, 4)]):
        fixtures.append(Fixture(
            id=f"mover_r{i+1}",
            name=f"Mover R{i+1}",
            dmx_address=addr,
            channels=mover_channels.copy(),
            x=6, y=4, z=z,
            fixture_type="mover"
        ))

    # Washes - Left side
    for i, (addr, z) in enumerate([(129, -3), (143, 0), (157, 3)]):
        fixtures.append(Fixture(
            id=f"wash_l{i+1}",
            name=f"Wash L{i+1}",
            dmx_address=addr,
            channels=wash_channels.copy(),
            x=-4, y=3.5, z=z,
            fixture_type="wash"
        ))

    # Washes - Right side
    for i, (addr, z) in enumerate([(171, -3), (185, 0), (199, 3)]):
        fixtures.append(Fixture(
            id=f"wash_r{i+1}",
            name=f"Wash R{i+1}",
            dmx_address=addr,
            channels=wash_channels.copy(),
            x=4, y=3.5, z=z,
            fixture_type="wash"
        ))

    # LED Bars
    for i, (addr, x) in enumerate([(213, -3), (225, -1), (237, 1), (249, 3)]):
        fixtures.append(Fixture(
            id=f"bar_{i+1}",
            name=f"Bar {i+1}",
            dmx_address=addr,
            channels=bar_channels.copy(),
            x=x, y=2, z=-5,
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
