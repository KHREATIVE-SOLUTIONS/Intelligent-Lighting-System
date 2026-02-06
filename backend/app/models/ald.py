"""
Abstract Lighting Description (ALD) Format
===========================================

Rig-agnostic representation of lighting states. The AI model outputs
ALD states, which are then mapped to specific fixture DMX values by
the ALD mapper. This allows a single trained model to work with any
fixture configuration.

Core concept: Instead of predicting "fixture 3 dimmer = 200, pan = 128",
predict "center stage, 80% intensity, warm amber, slow circle movement".

9-Zone Stage Grid:
    +-------+-------+-------+
    |  USL  |  USC  |  USR  |    US = Upstage (back)
    +-------+-------+-------+
    |  MSL  |  MSC  |  MSR  |    MS = Midstage
    +-------+-------+-------+
    |  DSL  |  DSC  |  DSR  |    DS = Downstage (front)
    +-------+-------+-------+
    Left     Center    Right
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import time


class StageZone(Enum):
    """9-zone stage grid for spatial lighting control."""
    USL = "upstage_left"       # Back left
    USC = "upstage_center"     # Back center
    USR = "upstage_right"      # Back right
    MSL = "midstage_left"      # Middle left
    MSC = "midstage_center"    # Center stage
    MSR = "midstage_right"     # Middle right
    DSL = "downstage_left"     # Front left
    DSC = "downstage_center"   # Front center
    DSR = "downstage_right"    # Front right
    AUDIENCE = "audience"      # House/audience area
    ALL = "all"                # All zones


# Zone coordinates for spatial calculations (normalized 0-1)
ZONE_POSITIONS = {
    StageZone.USL: (0.167, 0.833),
    StageZone.USC: (0.500, 0.833),
    StageZone.USR: (0.833, 0.833),
    StageZone.MSL: (0.167, 0.500),
    StageZone.MSC: (0.500, 0.500),
    StageZone.MSR: (0.833, 0.500),
    StageZone.DSL: (0.167, 0.167),
    StageZone.DSC: (0.500, 0.167),
    StageZone.DSR: (0.833, 0.167),
    StageZone.AUDIENCE: (0.500, 0.000),
    StageZone.ALL: (0.500, 0.500),
}


class MovementType(Enum):
    """Abstract movement types for fixtures."""
    NONE = "none"
    CIRCLE = "circle"
    FIGURE_8 = "figure_8"
    SWEEP_LR = "sweep_lr"          # Left-right sweep
    SWEEP_FB = "sweep_fb"          # Front-back sweep
    CHASE_LR = "chase_lr"          # Chase left to right
    CHASE_RL = "chase_rl"          # Chase right to left
    CONVERGE = "converge"          # Move toward center
    DIVERGE = "diverge"            # Move away from center
    RANDOM = "random"              # Gentle random motion
    BALLYHOO = "ballyhoo"          # Dramatic all-directions
    TILT_WAVE = "tilt_wave"        # Wave motion on tilt axis
    PAN_WAVE = "pan_wave"          # Wave motion on pan axis
    FOCUS_TRACK = "focus_track"    # Track a point (performer)


class EffectType(Enum):
    """Abstract lighting effects."""
    NONE = "none"
    STROBE = "strobe"
    PULSE = "pulse"                # Beat-sync dimmer pulse
    CHASE = "chase"                # Sequential fixture activation
    RAINBOW = "rainbow"            # Color cycling
    COLOR_FADE = "color_fade"      # Slow color transition
    SPARKLE = "sparkle"            # Random fixture flashes
    WAVE = "wave"                  # Intensity wave across fixtures
    BLACKOUT = "blackout"          # All off
    FLASH = "flash"                # Momentary full-on
    BUILD = "build"                # Gradual intensity increase


@dataclass
class ALDColor:
    """Abstract color representation."""
    hue: float = 0.0               # 0-360
    saturation: float = 1.0        # 0-1
    brightness: float = 1.0        # 0-1
    color_temp_k: float = 0.0      # 0 = use HSB, >0 = use color temperature

    @property
    def rgb(self) -> Tuple[float, float, float]:
        """Convert to RGB (0-1 range)."""
        if self.color_temp_k > 0:
            return _color_temp_to_rgb(self.color_temp_k)

        # HSV to RGB conversion
        h = self.hue / 60.0
        s = self.saturation
        v = self.brightness
        c = v * s
        x = c * (1 - abs(h % 2 - 1))
        m = v - c

        if h < 1:
            r, g, b = c, x, 0
        elif h < 2:
            r, g, b = x, c, 0
        elif h < 3:
            r, g, b = 0, c, x
        elif h < 4:
            r, g, b = 0, x, c
        elif h < 5:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (r + m, g + m, b + m)


@dataclass
class ALDZoneState:
    """Lighting state for a single zone."""
    zone: StageZone = StageZone.ALL
    intensity: float = 0.0         # 0-1
    color: ALDColor = field(default_factory=ALDColor)
    secondary_color: Optional[ALDColor] = None  # For split-color effects


@dataclass
class ALDMovement:
    """Movement description for the rig."""
    movement_type: MovementType = MovementType.NONE
    speed: float = 0.5             # 0-1 (fraction of max speed)
    size: float = 0.5              # 0-1 (fraction of full range)
    phase_offset: float = 0.0      # 0-1 (phase offset between fixtures)
    focus_point: Optional[Tuple[float, float]] = None  # (x, y) normalized


@dataclass
class ALDEffect:
    """Active effect description."""
    effect_type: EffectType = EffectType.NONE
    intensity: float = 1.0         # 0-1, effect strength
    speed: float = 0.5             # 0-1, effect speed
    zones: List[StageZone] = field(default_factory=lambda: [StageZone.ALL])


@dataclass
class AbstractLightingState:
    """Complete abstract lighting state at a point in time.

    This is the core ALD format. The AI model produces these states,
    and the rig adapter converts them to fixture-specific DMX values.
    """
    # Global parameters
    master_intensity: float = 1.0    # 0-1, global dimmer
    energy_level: float = 0.5        # 0-1, overall energy/excitement

    # Per-zone states (lighting intention per area)
    zones: List[ALDZoneState] = field(default_factory=list)

    # Primary and secondary colors (applied globally when zones are empty)
    primary_color: ALDColor = field(default_factory=ALDColor)
    secondary_color: ALDColor = field(default_factory=lambda: ALDColor(hue=180))

    # Coverage and spatial
    coverage: float = 0.5           # 0 (narrow spot) to 1 (full wash)
    symmetry: float = 0.8           # 0 (asymmetric) to 1 (symmetric)
    focus_zone: StageZone = StageZone.MSC

    # Movement
    movement: ALDMovement = field(default_factory=ALDMovement)

    # Active effects
    effects: List[ALDEffect] = field(default_factory=list)

    # Beat sync
    beat_response: float = 0.5      # 0-1, how strongly to respond to beats
    pulse_depth: float = 0.3        # 0-1, dimmer pulse depth on beat

    # Structure context
    section_label: str = "unknown"
    section_progress: float = 0.0

    # Metadata
    timestamp: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON/storage."""
        return {
            "master_intensity": self.master_intensity,
            "energy_level": self.energy_level,
            "zones": [
                {
                    "zone": z.zone.value,
                    "intensity": z.intensity,
                    "color": {"hue": z.color.hue, "saturation": z.color.saturation,
                              "brightness": z.color.brightness},
                }
                for z in self.zones
            ],
            "primary_color": {
                "hue": self.primary_color.hue,
                "saturation": self.primary_color.saturation,
                "brightness": self.primary_color.brightness,
            },
            "secondary_color": {
                "hue": self.secondary_color.hue,
                "saturation": self.secondary_color.saturation,
                "brightness": self.secondary_color.brightness,
            },
            "coverage": self.coverage,
            "symmetry": self.symmetry,
            "focus_zone": self.focus_zone.value,
            "movement": {
                "type": self.movement.movement_type.value,
                "speed": self.movement.speed,
                "size": self.movement.size,
                "phase_offset": self.movement.phase_offset,
            },
            "effects": [
                {
                    "type": e.effect_type.value,
                    "intensity": e.intensity,
                    "speed": e.speed,
                    "zones": [z.value for z in e.zones],
                }
                for e in self.effects
            ],
            "beat_response": self.beat_response,
            "pulse_depth": self.pulse_depth,
            "section_label": self.section_label,
            "section_progress": self.section_progress,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AbstractLightingState":
        """Deserialize from dictionary."""
        state = cls()
        state.master_intensity = data.get("master_intensity", 1.0)
        state.energy_level = data.get("energy_level", 0.5)
        state.coverage = data.get("coverage", 0.5)
        state.symmetry = data.get("symmetry", 0.8)
        state.beat_response = data.get("beat_response", 0.5)
        state.pulse_depth = data.get("pulse_depth", 0.3)
        state.section_label = data.get("section_label", "unknown")
        state.section_progress = data.get("section_progress", 0.0)
        state.timestamp = data.get("timestamp", 0.0)

        # Parse colors
        pc = data.get("primary_color", {})
        state.primary_color = ALDColor(
            hue=pc.get("hue", 0), saturation=pc.get("saturation", 1),
            brightness=pc.get("brightness", 1),
        )
        sc = data.get("secondary_color", {})
        state.secondary_color = ALDColor(
            hue=sc.get("hue", 180), saturation=sc.get("saturation", 1),
            brightness=sc.get("brightness", 1),
        )

        # Parse focus zone
        fz = data.get("focus_zone", "midstage_center")
        try:
            state.focus_zone = StageZone(fz)
        except ValueError:
            state.focus_zone = StageZone.MSC

        # Parse zones
        for zd in data.get("zones", []):
            try:
                zone = StageZone(zd["zone"])
            except (ValueError, KeyError):
                continue
            color_data = zd.get("color", {})
            state.zones.append(ALDZoneState(
                zone=zone,
                intensity=zd.get("intensity", 0.5),
                color=ALDColor(
                    hue=color_data.get("hue", 0),
                    saturation=color_data.get("saturation", 1),
                    brightness=color_data.get("brightness", 1),
                ),
            ))

        # Parse movement
        md = data.get("movement", {})
        try:
            mt = MovementType(md.get("type", "none"))
        except ValueError:
            mt = MovementType.NONE
        state.movement = ALDMovement(
            movement_type=mt,
            speed=md.get("speed", 0.5),
            size=md.get("size", 0.5),
            phase_offset=md.get("phase_offset", 0.0),
        )

        # Parse effects
        for ed in data.get("effects", []):
            try:
                et = EffectType(ed.get("type", "none"))
            except ValueError:
                continue
            zones = []
            for zv in ed.get("zones", ["all"]):
                try:
                    zones.append(StageZone(zv))
                except ValueError:
                    zones.append(StageZone.ALL)
            state.effects.append(ALDEffect(
                effect_type=et,
                intensity=ed.get("intensity", 1.0),
                speed=ed.get("speed", 0.5),
                zones=zones,
            ))

        return state


@dataclass
class ALDTimeline:
    """Sequence of timestamped ALD states forming a lighting plan.

    Used for:
    - Training data: paired with audio features
    - Inference output: plan for next N seconds
    - Pre-programmed sequences
    """
    states: List[AbstractLightingState] = field(default_factory=list)
    duration_sec: float = 0.0
    sample_rate_hz: float = 2.0    # States per second
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_state(self, state: AbstractLightingState):
        """Add a state to the timeline."""
        self.states.append(state)
        if self.states:
            self.duration_sec = self.states[-1].timestamp - self.states[0].timestamp

    def get_state_at(self, timestamp: float) -> Optional[AbstractLightingState]:
        """Get the state at a specific timestamp via interpolation."""
        if not self.states:
            return None

        # Find surrounding states
        for i, state in enumerate(self.states):
            if state.timestamp >= timestamp:
                if i == 0:
                    return state
                prev = self.states[i - 1]
                # Linear interpolation factor
                dt = state.timestamp - prev.timestamp
                if dt <= 0:
                    return state
                t = (timestamp - prev.timestamp) / dt
                return _interpolate_states(prev, state, t)

        return self.states[-1]

    def to_dict_list(self) -> List[Dict]:
        """Export as list of dictionaries."""
        return [s.to_dict() for s in self.states]


def _interpolate_states(
    a: AbstractLightingState, b: AbstractLightingState, t: float
) -> AbstractLightingState:
    """Linearly interpolate between two ALD states.

    Args:
        a: Start state
        b: End state
        t: Interpolation factor (0 = a, 1 = b)
    """
    t = max(0.0, min(1.0, t))

    def lerp(x: float, y: float) -> float:
        return x + (y - x) * t

    result = AbstractLightingState(
        master_intensity=lerp(a.master_intensity, b.master_intensity),
        energy_level=lerp(a.energy_level, b.energy_level),
        primary_color=ALDColor(
            hue=_lerp_hue(a.primary_color.hue, b.primary_color.hue, t),
            saturation=lerp(a.primary_color.saturation, b.primary_color.saturation),
            brightness=lerp(a.primary_color.brightness, b.primary_color.brightness),
        ),
        secondary_color=ALDColor(
            hue=_lerp_hue(a.secondary_color.hue, b.secondary_color.hue, t),
            saturation=lerp(a.secondary_color.saturation, b.secondary_color.saturation),
            brightness=lerp(a.secondary_color.brightness, b.secondary_color.brightness),
        ),
        coverage=lerp(a.coverage, b.coverage),
        symmetry=lerp(a.symmetry, b.symmetry),
        focus_zone=b.focus_zone if t > 0.5 else a.focus_zone,
        movement=ALDMovement(
            movement_type=b.movement.movement_type if t > 0.5 else a.movement.movement_type,
            speed=lerp(a.movement.speed, b.movement.speed),
            size=lerp(a.movement.size, b.movement.size),
            phase_offset=lerp(a.movement.phase_offset, b.movement.phase_offset),
        ),
        effects=b.effects if t > 0.5 else a.effects,
        beat_response=lerp(a.beat_response, b.beat_response),
        pulse_depth=lerp(a.pulse_depth, b.pulse_depth),
        section_label=b.section_label if t > 0.5 else a.section_label,
        section_progress=lerp(a.section_progress, b.section_progress),
        timestamp=lerp(a.timestamp, b.timestamp),
    )

    # Interpolate zones that exist in both states
    zone_map_a = {z.zone: z for z in a.zones}
    zone_map_b = {z.zone: z for z in b.zones}
    all_zones = set(zone_map_a.keys()) | set(zone_map_b.keys())

    for zone in all_zones:
        za = zone_map_a.get(zone)
        zb = zone_map_b.get(zone)
        if za and zb:
            result.zones.append(ALDZoneState(
                zone=zone,
                intensity=lerp(za.intensity, zb.intensity),
                color=ALDColor(
                    hue=_lerp_hue(za.color.hue, zb.color.hue, t),
                    saturation=lerp(za.color.saturation, zb.color.saturation),
                    brightness=lerp(za.color.brightness, zb.color.brightness),
                ),
            ))
        elif za:
            result.zones.append(ALDZoneState(
                zone=zone,
                intensity=za.intensity * (1 - t),
                color=za.color,
            ))
        elif zb:
            result.zones.append(ALDZoneState(
                zone=zone,
                intensity=zb.intensity * t,
                color=zb.color,
            ))

    return result


def _lerp_hue(h1: float, h2: float, t: float) -> float:
    """Interpolate between two hue values on the circular color wheel."""
    diff = h2 - h1
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    result = h1 + diff * t
    return result % 360


def _color_temp_to_rgb(kelvin: float) -> Tuple[float, float, float]:
    """Convert color temperature in Kelvin to RGB (0-1 range).

    Uses Tanner Helland's approximation.
    """
    temp = max(1000, min(12000, kelvin)) / 100.0

    # Red
    if temp <= 66:
        r = 1.0
    else:
        r = max(0.0, min(1.0, (329.698727446 * ((temp - 60) ** -0.1332047592)) / 255))

    # Green
    if temp <= 66:
        g = max(0.0, min(1.0, (99.4708025861 * (temp ** 0.39036112843) - 161.1195681661) / 255))
        # Clamp for low temps
        g = max(0.0, g)
    else:
        g = max(0.0, min(1.0, (288.1221695283 * ((temp - 60) ** -0.0755148492)) / 255))

    # Blue
    if temp >= 66:
        b = 1.0
    elif temp <= 19:
        b = 0.0
    else:
        b = max(0.0, min(1.0, (138.5177312231 * ((temp - 10) ** 0.50103842461) - 305.0447927307) / 255))
        b = max(0.0, b)

    return (r, g, b)
