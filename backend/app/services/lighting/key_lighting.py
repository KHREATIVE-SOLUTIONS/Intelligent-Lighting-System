"""
DJ/Performer Key Lighting and Spotlight Tracking
Ensures performers are always visible with appropriate front lighting.

Features:
- Performer zone definitions (DJ_BOOTH, STAGE_CENTER, STAGE_LEFT, etc.)
- Minimum intensity thresholds per zone
- Genre-specific front light color temperature rules
- Key light persistence during effects (performer always lit)
- Dynamic zone activation/deactivation
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..effects.color_mapper import RGB


class PerformerZone(Enum):
    """Predefined performer zones on stage."""
    DJ_BOOTH = "dj_booth"
    STAGE_CENTER = "stage_center"
    STAGE_LEFT = "stage_left"
    STAGE_RIGHT = "stage_right"
    DRUM_RISER = "drum_riser"
    KEYBOARD = "keyboard"
    DOWNSTAGE_CENTER = "downstage_center"
    UPSTAGE_CENTER = "upstage_center"


@dataclass
class ZoneDefinition:
    """Physical definition of a performer zone."""
    zone: PerformerZone
    # Bounding box in stage coordinates (meters from center)
    x_min: float = -1.0
    x_max: float = 1.0
    y_min: float = 0.0  # height
    y_max: float = 3.0
    z_min: float = -1.0  # depth (negative = upstage)
    z_max: float = 1.0

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a point is within this zone."""
        return (self.x_min <= x <= self.x_max and
                self.y_min <= y <= self.y_max and
                self.z_min <= z <= self.z_max)


@dataclass
class KeyLightConfig:
    """Configuration for key lighting in a zone."""
    zone: PerformerZone

    # Minimum dimmer intensity (never go below this)
    min_intensity: float = 0.4

    # Key light color (warm white by default)
    color: RGB = field(default_factory=lambda: RGB(1.0, 0.93, 0.85))

    # Color temperature mode: "warm", "cool", "neutral", "genre"
    color_temp: str = "warm"

    # Whether this zone is currently active (performer present)
    active: bool = True

    # Priority (higher = maintained over other effects)
    priority: int = 10

    # Fixture IDs assigned as key lights for this zone
    fixture_ids: List[str] = field(default_factory=list)

    # Target position (where key light aims within zone)
    target_x: float = 0.0
    target_y: float = 1.5  # Roughly head height
    target_z: float = 0.0


# Default zone definitions for common stage layouts
DEFAULT_ZONES: Dict[PerformerZone, ZoneDefinition] = {
    PerformerZone.DJ_BOOTH: ZoneDefinition(
        zone=PerformerZone.DJ_BOOTH,
        x_min=-1.5, x_max=1.5,
        y_min=0.0, y_max=2.5,
        z_min=-6.0, z_max=-4.0,  # Upstage center
    ),
    PerformerZone.STAGE_CENTER: ZoneDefinition(
        zone=PerformerZone.STAGE_CENTER,
        x_min=-2.0, x_max=2.0,
        y_min=0.0, y_max=3.0,
        z_min=-2.0, z_max=2.0,
    ),
    PerformerZone.STAGE_LEFT: ZoneDefinition(
        zone=PerformerZone.STAGE_LEFT,
        x_min=-6.0, x_max=-2.0,
        y_min=0.0, y_max=3.0,
        z_min=-3.0, z_max=2.0,
    ),
    PerformerZone.STAGE_RIGHT: ZoneDefinition(
        zone=PerformerZone.STAGE_RIGHT,
        x_min=2.0, x_max=6.0,
        y_min=0.0, y_max=3.0,
        z_min=-3.0, z_max=2.0,
    ),
    PerformerZone.DRUM_RISER: ZoneDefinition(
        zone=PerformerZone.DRUM_RISER,
        x_min=-1.5, x_max=1.5,
        y_min=0.5, y_max=3.0,
        z_min=-5.0, z_max=-3.0,  # Upstage center, elevated
    ),
    PerformerZone.KEYBOARD: ZoneDefinition(
        zone=PerformerZone.KEYBOARD,
        x_min=-5.0, x_max=-3.0,
        y_min=0.0, y_max=2.5,
        z_min=-4.0, z_max=-2.0,
    ),
    PerformerZone.DOWNSTAGE_CENTER: ZoneDefinition(
        zone=PerformerZone.DOWNSTAGE_CENTER,
        x_min=-2.0, x_max=2.0,
        y_min=0.0, y_max=3.0,
        z_min=2.0, z_max=5.0,  # Near audience
    ),
    PerformerZone.UPSTAGE_CENTER: ZoneDefinition(
        zone=PerformerZone.UPSTAGE_CENTER,
        x_min=-2.0, x_max=2.0,
        y_min=0.0, y_max=3.0,
        z_min=-6.0, z_max=-3.0,
    ),
}

# Genre-specific front light colors
GENRE_KEY_LIGHT_COLORS: Dict[str, RGB] = {
    "warm": RGB(1.0, 0.93, 0.85),      # 3200K warm white
    "cool": RGB(0.85, 0.93, 1.0),      # 5600K cool white
    "neutral": RGB(0.95, 0.95, 0.95),  # 4500K neutral
    "edm": RGB(0.85, 0.93, 1.0),       # Cool for EDM
    "rock": RGB(1.0, 0.90, 0.80),      # Warm amber for rock
    "pop": RGB(0.95, 0.95, 0.95),      # Neutral for pop
    "hip_hop": RGB(1.0, 0.93, 0.85),   # Warm for hip-hop
    "jazz": RGB(1.0, 0.88, 0.75),      # Very warm amber for jazz
}


class KeyLightingManager:
    """
    Manages key lighting for performers across all zones.
    Ensures performers are always visible regardless of effects.
    """

    def __init__(self):
        self._zones: Dict[PerformerZone, ZoneDefinition] = dict(DEFAULT_ZONES)
        self._configs: Dict[PerformerZone, KeyLightConfig] = {}
        self._genre: str = "neutral"

        # Fixture-to-zone mapping
        self._fixture_zone_map: Dict[str, PerformerZone] = {}

        # Global key light intensity multiplier
        self._master_intensity: float = 1.0

    def configure_zone(self, zone: PerformerZone, config: KeyLightConfig):
        """Configure key lighting for a zone."""
        self._configs[zone] = config
        # Update fixture-zone mapping
        for fid in config.fixture_ids:
            self._fixture_zone_map[fid] = zone

    def set_zone_active(self, zone: PerformerZone, active: bool):
        """Activate or deactivate a performer zone."""
        if zone in self._configs:
            self._configs[zone].active = active

    def set_genre(self, genre: str):
        """Set genre for color temperature selection."""
        self._genre = genre
        # Update all zone colors that use "genre" mode
        for config in self._configs.values():
            if config.color_temp == "genre":
                config.color = GENRE_KEY_LIGHT_COLORS.get(
                    genre, GENRE_KEY_LIGHT_COLORS["neutral"]
                )

    def set_master_intensity(self, intensity: float):
        """Set global key light intensity multiplier."""
        self._master_intensity = max(0.0, min(1.0, intensity))

    def assign_fixtures(self, zone: PerformerZone, fixture_ids: List[str]):
        """Assign fixtures as key lights for a zone."""
        if zone not in self._configs:
            # Auto-create config
            self._configs[zone] = KeyLightConfig(zone=zone, fixture_ids=fixture_ids)
        else:
            self._configs[zone].fixture_ids = fixture_ids

        for fid in fixture_ids:
            self._fixture_zone_map[fid] = zone

    def auto_assign_fixtures(self, fixtures: Dict[str, dict]):
        """
        Auto-assign fixtures to zones based on their position.

        Args:
            fixtures: Dict of fixture_id -> {x, y, z, fixture_type}
        """
        for zone, zone_def in self._zones.items():
            matching_fixtures = []
            for fid, fdata in fixtures.items():
                # Only assign wash and front-pointing fixtures as key lights
                if fdata.get("fixture_type") in ("wash", "mover"):
                    if zone_def.contains_point(
                        fdata.get("x", 0), fdata.get("y", 0), fdata.get("z", 0)
                    ):
                        matching_fixtures.append(fid)

            if matching_fixtures:
                self.assign_fixtures(zone, matching_fixtures)

    def get_key_light_override(self, fixture_id: str,
                                current_dimmer: float,
                                current_r: float,
                                current_g: float,
                                current_b: float) -> Optional[Dict]:
        """
        Get key light override for a fixture if it's assigned to an active zone.

        Returns None if no override needed, or dict with:
        - dimmer: minimum dimmer value
        - r, g, b: key light color blend
        """
        zone = self._fixture_zone_map.get(fixture_id)
        if zone is None:
            return None

        config = self._configs.get(zone)
        if config is None or not config.active:
            return None

        min_dimmer = config.min_intensity * self._master_intensity

        # Only override if current dimmer is below minimum
        if current_dimmer >= min_dimmer:
            return None

        # Blend key light color with current color
        # Key light color takes priority proportional to how much we're boosting
        boost_ratio = (min_dimmer - current_dimmer) / max(0.01, min_dimmer)
        key_color = self._get_zone_color(config)

        return {
            "dimmer": min_dimmer,
            "r": current_r + (key_color.r - current_r) * boost_ratio * 0.5,
            "g": current_g + (key_color.g - current_g) * boost_ratio * 0.5,
            "b": current_b + (key_color.b - current_b) * boost_ratio * 0.5,
        }

    def _get_zone_color(self, config: KeyLightConfig) -> RGB:
        """Get the key light color for a zone based on its config."""
        if config.color_temp == "genre":
            return GENRE_KEY_LIGHT_COLORS.get(
                self._genre, GENRE_KEY_LIGHT_COLORS["neutral"]
            )
        return GENRE_KEY_LIGHT_COLORS.get(
            config.color_temp, config.color
        )

    def get_active_zones(self) -> List[PerformerZone]:
        """Get list of currently active performer zones."""
        return [
            zone for zone, config in self._configs.items()
            if config.active
        ]

    def get_zone_fixtures(self, zone: PerformerZone) -> List[str]:
        """Get fixture IDs assigned to a zone."""
        config = self._configs.get(zone)
        if config is None:
            return []
        return config.fixture_ids

    def get_zone_target(self, zone: PerformerZone) -> Optional[Tuple[float, float, float]]:
        """Get the target position for key lights in a zone."""
        config = self._configs.get(zone)
        if config is None:
            return None
        return (config.target_x, config.target_y, config.target_z)
