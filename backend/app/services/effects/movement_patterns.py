"""
Movement Patterns Engine
Controls pan/tilt positioning for fixtures (Layer 2)

7 Static Looks + 10 Movement Patterns
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import math
import random


class StaticLook(Enum):
    """Predefined static positions (base looks)."""
    ALL_CENTER = "all_center"           # All beams converge at center
    X_PATTERN = "x_pattern"             # Crossing beams
    FAN_OUT = "fan_out"                 # Wide symmetrical spread
    PARALLEL_FORWARD = "parallel_forward"  # All point at audience
    STAGGERED_HEIGHTS = "staggered"     # Varying tilt for depth
    OPPOSING_CORNERS = "corners"        # Diagonal tension
    CIRCLE_FLOOR = "circle"             # Geometric circle on floor


class MovementType(Enum):
    """Movement pattern types."""
    NONE = "none"                       # Hold static position
    HORIZONTAL_SWEEP = "h_sweep"        # Pan oscillates left-right
    VERTICAL_SWEEP = "v_sweep"          # Tilt oscillates up-down
    FIGURE_8 = "figure_8"               # Lissajous figure-8 (pan 1:2 tilt)
    PAN_CHASE = "pan_chase"             # Wave traveling across rig
    TILT_CHASE = "tilt_chase"           # Tilt ripple effect
    ALTERNATING = "alternating"         # Odd/even opposite movement
    LINEAR_SCAN = "linear_scan"         # Searchlight sweep
    RANDOM_WALK = "random_walk"         # Organic chaos
    SYNCHRONIZED = "synchronized"       # All rotate together
    COUNTER_ROTATION = "counter_rotation"  # Opposing vortex
    # New professional patterns
    TRUE_CIRCLE = "circle"              # True circular motion (same freq, 90° phase)
    SPIRAL = "spiral"                   # Expanding/contracting circle
    MIRROR_SWEEP = "mirror"             # L/R symmetrical opposite movement
    CENTER_OUT_WAVE = "center_out"      # Wave from center to edges
    OUTSIDE_IN_WAVE = "outside_in"      # Wave from edges to center
    TILT_BUMP = "tilt_bump"             # Quick down-up tilt hit on beat
    PAN_BUMP = "pan_bump"               # Quick L-R snap on beat
    BALLYHOO = "ballyhoo"               # Classic ballyhoo with offset timing
    CIRCLE_CHASE = "circle_chase"       # Circular with phase offset (creates helix)
    FIGURE_8_MIRROR = "figure_8_mirror" # Figure-8 with L/R mirror


@dataclass
class MovementParams:
    """Parameters for movement patterns."""
    pattern: MovementType = MovementType.NONE
    base_look: StaticLook = StaticLook.ALL_CENTER

    # Speed control (Hz - cycles per second)
    pan_speed: float = 0.4      # 0.4 Hz = 2.5 second cycle (visible but not frantic)
    tilt_speed: float = 0.4

    # BPM sync (overrides manual speed when > 0)
    bpm: float = 0.0            # Current BPM (0 = use manual speed)
    beat_divisor: float = 1.0   # 1=every beat, 2=half beat, 0.5=every 2 beats

    # Amplitude (degrees) - INCREASED for visibility
    pan_amplitude: float = 70.0   # +/- 70 degrees (dramatic sweep)
    tilt_amplitude: float = 45.0  # +/- 45 degrees (visible head nod)

    # Phase offset between fixtures (0-1)
    phase_spread: float = 1.0    # 1.0 = full spread, 0 = synchronized

    # Phase calculation mode
    phase_mode: str = "index"    # index, position_x, center_distance

    # Wave shape
    wave_type: str = "sine"      # sine, triangle, square, sawtooth

    # Direction
    reverse: bool = False

    # Smoothing (0 = instant snap, 1 = very slow) - INCREASED for snappier response
    smoothing: float = 0.35      # Faster interpolation for more responsive movement

    # Snap mode for beat hits (bypasses smoothing)
    snap_on_beat: bool = False

    # Spiral parameters
    spiral_expansion: float = 0.4  # Rate of radius change for spiral

    # Bump parameters
    bump_attack: float = 0.08   # Very quick attack (seconds)
    bump_decay: float = 0.25    # Snappy decay (seconds)


class MovementEngine:
    """
    Generates pan/tilt values for fixtures based on movement patterns.
    """

    def __init__(self):
        self.params = MovementParams()
        self.time = 0.0
        self.beat_time = 0.0  # Time since last beat
        self._delta_time = 1.0 / 60.0  # BUG-022 fix: store for frame-rate-independent smoothing

        # Per-fixture state for smoothing
        self._fixture_targets: Dict[str, Tuple[float, float]] = {}
        self._fixture_current: Dict[str, Tuple[float, float]] = {}

        # Random walk state
        self._random_targets: Dict[str, Tuple[float, float]] = {}
        self._random_timer: float = 0.0

        # Bump state (for TILT_BUMP/PAN_BUMP patterns)
        self._bump_active: bool = False
        self._bump_start_time: float = 0.0
        self._bump_direction: int = 1  # Alternates on each beat

        # Fixture position cache for phase calculations
        self._fixture_positions: Dict[str, Tuple[float, float, float]] = {}
        self._position_phase_cache: Dict[str, float] = {}
        self._phase_cache_dirty: bool = True

    def trigger_beat(self):
        """Trigger beat event for beat-synced patterns."""
        self.beat_time = 0.0
        self._bump_active = True
        self._bump_start_time = self.time
        self._bump_direction *= -1  # Alternate direction

    def _get_effective_speed(self) -> Tuple[float, float]:
        """Get pan/tilt speed, using BPM if set."""
        if self.params.bpm > 0:
            # Convert BPM to Hz: (bpm/60) / beat_divisor
            base_speed = (self.params.bpm / 60.0) / self.params.beat_divisor
            return (base_speed, base_speed)
        return (self.params.pan_speed, self.params.tilt_speed)

    def cache_fixture_position(self, fixture_id: str, x: float, y: float, z: float):
        """Cache fixture position for phase calculations."""
        self._fixture_positions[fixture_id] = (x, y, z)
        self._phase_cache_dirty = True

    def _calculate_position_phase(self, fixture_id: str, fixture_x: float) -> float:
        """Calculate phase offset based on fixture position."""
        mode = self.params.phase_mode

        if mode == "position_x":
            # Phase based on X position (left-to-right wave)
            # Normalize X to 0-1 range (assuming stage is -8 to +8)
            return (fixture_x + 8) / 16.0

        elif mode == "center_distance":
            # Phase based on distance from center (center-out wave)
            return abs(fixture_x) / 8.0

        # Default: index-based (handled elsewhere)
        return 0.0

    def set_pattern(
        self,
        pattern: MovementType,
        base_look: StaticLook = StaticLook.ALL_CENTER,
        **kwargs
    ):
        """Set the current movement pattern."""
        self.params.pattern = pattern
        self.params.base_look = base_look

        # Update any provided parameters
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)

    def update(self, delta_time: float):
        """Update movement state."""
        self.time += delta_time
        self._delta_time = delta_time  # BUG-022 fix: store for frame-rate-independent smoothing
        self._random_timer += delta_time

    def get_position(
        self,
        fixture_id: str,
        fixture_x: float,
        fixture_y: float,
        fixture_z: float,
        index: int,
        phase_offset: float
    ) -> Tuple[float, float]:
        """
        Calculate pan/tilt for a fixture.

        Args:
            fixture_id: Unique fixture identifier
            fixture_x, y, z: Fixture position in space
            index: Fixture index in group
            phase_offset: Phase offset (0-1)

        Returns:
            Tuple of (pan_degrees, tilt_degrees)
        """
        # Get base position from static look
        base_pan, base_tilt = self._get_static_position(
            fixture_x, fixture_y, fixture_z, index
        )

        # Apply movement pattern
        if self.params.pattern == MovementType.NONE:
            target_pan, target_tilt = base_pan, base_tilt
        else:
            move_pan, move_tilt = self._calculate_movement(
                fixture_id, index, phase_offset, fixture_x
            )
            target_pan = base_pan + move_pan
            target_tilt = base_tilt + move_tilt

        # Smooth interpolation
        if fixture_id not in self._fixture_current:
            self._fixture_current[fixture_id] = (target_pan, target_tilt)

        current_pan, current_tilt = self._fixture_current[fixture_id]
        # BUG-022 fix: frame-rate-independent smoothing using exponential decay
        # At 60fps (dt=0.0167), factor ≈ smoothing (preserves original feel)
        smooth = 1.0 - (1.0 - self.params.smoothing) ** (self._delta_time * 60.0)

        new_pan = current_pan + (target_pan - current_pan) * smooth
        new_tilt = current_tilt + (target_tilt - current_tilt) * smooth

        self._fixture_current[fixture_id] = (new_pan, new_tilt)
        return (new_pan, new_tilt)

    def _get_static_position(
        self,
        x: float,
        y: float,
        z: float,
        index: int
    ) -> Tuple[float, float]:
        """Get pan/tilt for static look based on fixture position."""
        look = self.params.base_look

        # Target point on floor (y=0)
        target_x, target_y, target_z = 0, 0, 0

        if look == StaticLook.ALL_CENTER:
            # True home position in this engine's convention.
            # pan=0, tilt=0 should point straight down in the visualizer.
            return (0.0, 0.0)

        elif look == StaticLook.X_PATTERN:
            # Cross pattern - left fixtures point right, right point left
            if x < 0:
                target_x = 3
            else:
                target_x = -3
            target_z = 2

        elif look == StaticLook.FAN_OUT:
            # Fan out from center
            target_x = x * 1.5
            target_z = 5

        elif look == StaticLook.PARALLEL_FORWARD:
            # All point straight forward
            target_x = x
            target_z = 10

        elif look == StaticLook.STAGGERED_HEIGHTS:
            # Alternating high/low tilt
            target_x = 0
            target_z = 2 + (index % 3) * 2

        elif look == StaticLook.OPPOSING_CORNERS:
            # Diagonal tension
            if index % 2 == 0:
                target_x = -5
                target_z = -2
            else:
                target_x = 5
                target_z = 5

        elif look == StaticLook.CIRCLE_FLOOR:
            # Circle on floor
            # BUG-043 fix: use dynamic fixture count instead of hardcoded 8
            fixture_count = max(1, len(self._fixture_current) or 8)
            angle = (index / fixture_count) * math.pi * 2
            radius = 3
            target_x = math.cos(angle) * radius
            target_z = math.sin(angle) * radius + 2

        # Calculate pan/tilt to hit target
        return self._calculate_pan_tilt_to_target(x, y, z, target_x, target_y, target_z)

    def _calculate_pan_tilt_to_target(
        self,
        fx: float, fy: float, fz: float,  # Fixture position
        tx: float, ty: float, tz: float   # Target position
    ) -> Tuple[float, float]:
        """Calculate pan/tilt angles to point fixture at target."""
        dx = tx - fx
        dy = ty - fy
        dz = tz - fz

        # Pan: rotation around Y axis
        pan = math.degrees(math.atan2(dx, dz))

        # Tilt: rotation around X axis (pointing down is positive tilt)
        horizontal_dist = math.sqrt(dx * dx + dz * dz)
        tilt = math.degrees(math.atan2(-dy, horizontal_dist))

        return (pan, tilt)

    def _calculate_movement(
        self,
        fixture_id: str,
        index: int,
        phase_offset: float,
        fixture_x: float = 0.0
    ) -> Tuple[float, float]:
        """Calculate movement offset from base position."""
        pattern = self.params.pattern
        t = self.time
        pan_speed, tilt_speed = self._get_effective_speed()

        # Calculate phase based on mode
        if self.params.phase_mode == "index":
            phase = phase_offset * self.params.phase_spread
        else:
            phase = self._calculate_position_phase(fixture_id, fixture_x) * self.params.phase_spread

        if self.params.reverse:
            phase = 1.0 - phase

        pan_offset = 0.0
        tilt_offset = 0.0

        if pattern == MovementType.HORIZONTAL_SWEEP:
            pan_offset = self._wave(t * pan_speed + phase) * self.params.pan_amplitude

        elif pattern == MovementType.VERTICAL_SWEEP:
            tilt_offset = self._wave(t * tilt_speed + phase) * self.params.tilt_amplitude

        elif pattern == MovementType.FIGURE_8:
            # Lissajous figure-8 (1:2 frequency ratio)
            pan_offset = self._wave(t * pan_speed + phase) * self.params.pan_amplitude
            tilt_offset = self._wave(t * tilt_speed * 2 + phase) * self.params.tilt_amplitude

        elif pattern == MovementType.TRUE_CIRCLE:
            # True circular motion (same frequency, 90° phase offset)
            angle = (t * pan_speed + phase) * math.pi * 2
            pan_offset = math.sin(angle) * self.params.pan_amplitude
            tilt_offset = math.cos(angle) * self.params.tilt_amplitude

        elif pattern == MovementType.CIRCLE_CHASE:
            # Circular with phase offset creating helix effect
            angle = (t * pan_speed) * math.pi * 2
            pan_offset = math.sin(angle + phase * math.pi * 2) * self.params.pan_amplitude
            tilt_offset = math.cos(angle + phase * math.pi * 2) * self.params.tilt_amplitude

        elif pattern == MovementType.SPIRAL:
            # Expanding/contracting circular motion
            angle = (t * pan_speed + phase) * math.pi * 2
            # Radius oscillates over time
            radius_factor = 0.3 + 0.7 * (math.sin(t * self.params.spiral_expansion) * 0.5 + 0.5)
            pan_offset = math.sin(angle) * self.params.pan_amplitude * radius_factor
            tilt_offset = math.cos(angle) * self.params.tilt_amplitude * radius_factor

        elif pattern == MovementType.MIRROR_SWEEP:
            # Left/right symmetrical opposite movement
            # Fixtures with x < 0 pan left, x > 0 pan right
            direction = -1 if fixture_x < 0 else 1
            pan_offset = self._wave(t * pan_speed) * self.params.pan_amplitude * direction
            tilt_offset = self._wave(t * tilt_speed) * self.params.tilt_amplitude

        elif pattern == MovementType.FIGURE_8_MIRROR:
            # Figure-8 with L/R mirror
            direction = -1 if fixture_x < 0 else 1
            pan_offset = self._wave(t * pan_speed + phase) * self.params.pan_amplitude * direction
            tilt_offset = self._wave(t * tilt_speed * 2 + phase) * self.params.tilt_amplitude

        elif pattern == MovementType.CENTER_OUT_WAVE:
            # Wave propagates from center to edges
            center_phase = abs(fixture_x) / 8.0 * self.params.phase_spread
            pan_offset = self._wave(t * pan_speed - center_phase) * self.params.pan_amplitude
            tilt_offset = self._wave(t * tilt_speed - center_phase) * self.params.tilt_amplitude

        elif pattern == MovementType.OUTSIDE_IN_WAVE:
            # Wave propagates from edges to center
            edge_phase = (1.0 - abs(fixture_x) / 8.0) * self.params.phase_spread
            pan_offset = self._wave(t * pan_speed - edge_phase) * self.params.pan_amplitude
            tilt_offset = self._wave(t * tilt_speed - edge_phase) * self.params.tilt_amplitude

        elif pattern == MovementType.TILT_BUMP:
            # Quick tilt hit on beat
            pan_offset, tilt_offset = self._calculate_bump(is_pan=False)

        elif pattern == MovementType.PAN_BUMP:
            # Quick pan hit on beat
            pan_offset, tilt_offset = self._calculate_bump(is_pan=True)

        elif pattern == MovementType.BALLYHOO:
            # Classic ballyhoo - figure-8 with staggered timing
            ballyhoo_phase = phase * 0.25  # Subtle offset between fixtures
            angle = (t * pan_speed + ballyhoo_phase) * math.pi * 2
            pan_offset = math.sin(angle) * self.params.pan_amplitude
            tilt_offset = math.sin(angle * 2 + ballyhoo_phase * math.pi) * self.params.tilt_amplitude * 0.7

        elif pattern == MovementType.PAN_CHASE:
            # Chase wave across pan (left to right)
            pan_offset = self._wave(t * pan_speed - phase) * self.params.pan_amplitude

        elif pattern == MovementType.TILT_CHASE:
            # Chase wave across tilt
            tilt_offset = self._wave(t * tilt_speed - phase) * self.params.tilt_amplitude

        elif pattern == MovementType.ALTERNATING:
            # Odd/even move opposite directions
            direction = 1 if index % 2 == 0 else -1
            pan_offset = self._wave(t * pan_speed) * self.params.pan_amplitude * direction
            tilt_offset = self._wave(t * tilt_speed) * self.params.tilt_amplitude * direction

        elif pattern == MovementType.LINEAR_SCAN:
            # Sawtooth scan (searchlight)
            scan_phase = (t * pan_speed + phase) % 1.0
            pan_offset = (scan_phase * 2 - 1) * self.params.pan_amplitude

        elif pattern == MovementType.RANDOM_WALK:
            pan_offset, tilt_offset = self._random_walk(fixture_id)

        elif pattern == MovementType.SYNCHRONIZED:
            # All move together (no phase offset)
            pan_offset = self._wave(t * pan_speed) * self.params.pan_amplitude
            tilt_offset = self._wave(t * tilt_speed) * self.params.tilt_amplitude

        elif pattern == MovementType.COUNTER_ROTATION:
            # Half rotate one way, half the other (based on position, not index)
            direction = 1 if fixture_x < 0 else -1
            angle = t * pan_speed * math.pi * 2
            pan_offset = math.sin(angle) * self.params.pan_amplitude * direction
            tilt_offset = math.cos(angle) * self.params.tilt_amplitude * direction

        return (pan_offset, tilt_offset)

    def _calculate_bump(self, is_pan: bool) -> Tuple[float, float]:
        """Calculate bump offset (quick attack, slower decay)."""
        if not self._bump_active:
            return (0.0, 0.0)

        elapsed = self.time - self._bump_start_time
        attack = self.params.bump_attack
        decay = self.params.bump_decay
        total_duration = attack + decay

        if elapsed > total_duration:
            self._bump_active = False
            return (0.0, 0.0)

        # Attack phase: quick ramp up
        if elapsed < attack:
            intensity = elapsed / attack
        else:
            # Decay phase: exponential decay
            decay_elapsed = elapsed - attack
            intensity = 1.0 - (decay_elapsed / decay)
            intensity = max(0, intensity * intensity)  # Squared for smoother decay

        amplitude = self.params.pan_amplitude if is_pan else self.params.tilt_amplitude
        offset = intensity * amplitude * self._bump_direction

        if is_pan:
            return (offset, 0.0)
        else:
            return (0.0, offset)

    def _wave(self, phase: float) -> float:
        """Generate wave value based on wave type."""
        phase = phase % 1.0
        wave_type = self.params.wave_type

        if wave_type == "sine":
            return math.sin(phase * math.pi * 2)

        elif wave_type == "triangle":
            return 1 - 4 * abs(phase - 0.5)

        elif wave_type == "square":
            return 1.0 if phase < 0.5 else -1.0

        elif wave_type == "sawtooth":
            return phase * 2 - 1

        return math.sin(phase * math.pi * 2)

    def _random_walk(self, fixture_id: str) -> Tuple[float, float]:
        """Generate random walk movement."""
        # Update targets every 2-4 seconds
        if self._random_timer > random.uniform(2, 4):
            self._random_timer = 0
            for fid in list(self._random_targets.keys()):
                self._random_targets[fid] = (
                    random.uniform(-1, 1) * self.params.pan_amplitude,
                    random.uniform(-1, 1) * self.params.tilt_amplitude
                )

        if fixture_id not in self._random_targets:
            self._random_targets[fixture_id] = (0, 0)

        return self._random_targets[fixture_id]


# Preset movement configurations - tuned for DRAMATIC, VISIBLE movement
MOVEMENT_PRESETS = {
    "slow_sweep": MovementParams(
        pattern=MovementType.HORIZONTAL_SWEEP,
        pan_speed=0.2,
        pan_amplitude=80,  # Wide sweep
        wave_type="sine",
        smoothing=0.25
    ),
    "fast_sweep": MovementParams(
        pattern=MovementType.HORIZONTAL_SWEEP,
        pan_speed=0.8,
        pan_amplitude=65,
        wave_type="sine",
        smoothing=0.4
    ),
    "gentle_tilt": MovementParams(
        pattern=MovementType.VERTICAL_SWEEP,
        tilt_speed=0.25,
        tilt_amplitude=35,
        wave_type="sine",
        smoothing=0.25
    ),
    "dramatic_tilt": MovementParams(
        pattern=MovementType.VERTICAL_SWEEP,
        tilt_speed=0.4,
        tilt_amplitude=55,
        wave_type="sine",
        smoothing=0.35
    ),
    "figure_8_slow": MovementParams(
        pattern=MovementType.FIGURE_8,
        pan_speed=0.2,
        tilt_speed=0.2,
        pan_amplitude=65,
        tilt_amplitude=40,
        wave_type="sine",
        smoothing=0.25
    ),
    "figure_8_fast": MovementParams(
        pattern=MovementType.FIGURE_8,
        pan_speed=0.5,
        tilt_speed=0.5,
        pan_amplitude=55,
        tilt_amplitude=35,
        wave_type="sine",
        smoothing=0.35
    ),
    "chase_left_right": MovementParams(
        pattern=MovementType.PAN_CHASE,
        pan_speed=0.4,
        pan_amplitude=70,
        phase_spread=1.0,
        phase_mode="position_x",
        smoothing=0.3
    ),
    "chase_right_left": MovementParams(
        pattern=MovementType.PAN_CHASE,
        pan_speed=0.4,
        pan_amplitude=70,
        phase_spread=1.0,
        phase_mode="position_x",
        reverse=True,
        smoothing=0.3
    ),
    "ballyhoo": MovementParams(
        pattern=MovementType.BALLYHOO,
        pan_speed=0.6,
        tilt_speed=0.3,
        pan_amplitude=95,  # Very dramatic
        tilt_amplitude=50,
        wave_type="sine",
        smoothing=0.25
    ),
    "tilt_wave": MovementParams(
        pattern=MovementType.TILT_CHASE,
        tilt_speed=0.35,
        tilt_amplitude=45,
        phase_spread=1.0,
        smoothing=0.3
    ),
    "alternating_sweep": MovementParams(
        pattern=MovementType.ALTERNATING,
        pan_speed=0.4,
        tilt_speed=0.3,
        pan_amplitude=65,
        tilt_amplitude=40,
        smoothing=0.35
    ),
    "random_organic": MovementParams(
        pattern=MovementType.RANDOM_WALK,
        pan_amplitude=75,
        tilt_amplitude=50,
        smoothing=0.08  # Very slow smoothing for organic feel
    ),
    "synchronized_circle": MovementParams(
        pattern=MovementType.TRUE_CIRCLE,  # Use TRUE_CIRCLE instead
        pan_speed=0.25,
        tilt_speed=0.25,
        pan_amplitude=60,
        tilt_amplitude=45,
        smoothing=0.25
    ),
    "vortex": MovementParams(
        pattern=MovementType.COUNTER_ROTATION,
        pan_speed=0.35,
        pan_amplitude=75,
        tilt_amplitude=45,
        smoothing=0.3
    ),
    # === New Professional Presets ===
    "circle_slow": MovementParams(
        pattern=MovementType.TRUE_CIRCLE,
        pan_speed=0.2,
        pan_amplitude=50,
        tilt_amplitude=35,
        smoothing=0.2
    ),
    "circle_fast": MovementParams(
        pattern=MovementType.TRUE_CIRCLE,
        pan_speed=0.5,
        pan_amplitude=60,
        tilt_amplitude=40,
        smoothing=0.3
    ),
    "circle_chase": MovementParams(
        pattern=MovementType.CIRCLE_CHASE,
        pan_speed=0.3,
        pan_amplitude=55,
        tilt_amplitude=35,
        phase_spread=1.0,
        smoothing=0.25
    ),
    "spiral_expand": MovementParams(
        pattern=MovementType.SPIRAL,
        pan_speed=0.25,
        pan_amplitude=60,
        tilt_amplitude=40,
        spiral_expansion=0.3,
        smoothing=0.2
    ),
    "mirror_sweep": MovementParams(
        pattern=MovementType.MIRROR_SWEEP,
        pan_speed=0.4,
        pan_amplitude=70,
        tilt_amplitude=25,
        smoothing=0.25
    ),
    "mirror_figure_8": MovementParams(
        pattern=MovementType.FIGURE_8_MIRROR,
        pan_speed=0.3,
        pan_amplitude=65,
        tilt_amplitude=35,
        phase_spread=0.5,
        smoothing=0.2
    ),
    "center_out": MovementParams(
        pattern=MovementType.CENTER_OUT_WAVE,
        pan_speed=0.4,
        pan_amplitude=50,
        tilt_amplitude=30,
        phase_spread=1.0,
        phase_mode="center_distance",
        smoothing=0.25
    ),
    "outside_in": MovementParams(
        pattern=MovementType.OUTSIDE_IN_WAVE,
        pan_speed=0.4,
        pan_amplitude=50,
        tilt_amplitude=30,
        phase_spread=1.0,
        phase_mode="center_distance",
        smoothing=0.25
    ),
    "tilt_bump_beat": MovementParams(
        pattern=MovementType.TILT_BUMP,
        tilt_amplitude=40,
        bump_attack=0.05,
        bump_decay=0.2,
        smoothing=0.5
    ),
    "pan_bump_beat": MovementParams(
        pattern=MovementType.PAN_BUMP,
        pan_amplitude=35,
        bump_attack=0.05,
        bump_decay=0.25,
        smoothing=0.5
    ),
    "ballyhoo_classic": MovementParams(
        pattern=MovementType.BALLYHOO,
        pan_speed=0.6,
        pan_amplitude=80,
        tilt_amplitude=50,
        phase_spread=0.3,
        smoothing=0.2
    ),
    "ballyhoo_slow": MovementParams(
        pattern=MovementType.BALLYHOO,
        pan_speed=0.25,
        pan_amplitude=90,
        tilt_amplitude=45,
        phase_spread=0.2,
        smoothing=0.15
    ),
    # BPM-synced presets (set bpm at runtime)
    "circle_on_beat": MovementParams(
        pattern=MovementType.TRUE_CIRCLE,
        beat_divisor=1.0,  # One circle per beat
        pan_amplitude=55,
        tilt_amplitude=40,
        smoothing=0.3
    ),
    "circle_half_beat": MovementParams(
        pattern=MovementType.TRUE_CIRCLE,
        beat_divisor=2.0,  # Two circles per beat
        pan_amplitude=45,
        tilt_amplitude=30,
        smoothing=0.35
    ),
    "sweep_on_bar": MovementParams(
        pattern=MovementType.HORIZONTAL_SWEEP,
        beat_divisor=0.25,  # One sweep per 4 beats (1 bar)
        pan_amplitude=80,
        smoothing=0.2
    ),
    "chase_on_beat": MovementParams(
        pattern=MovementType.PAN_CHASE,
        beat_divisor=0.5,  # Chase completes every 2 beats
        pan_amplitude=60,
        phase_spread=1.0,
        phase_mode="position_x",
        smoothing=0.3
    )
}

class MovementOrchestrator:
    """
    Orchestrates movement across fixture groups for complex choreography.
    Enables split-action patterns like odd/even alternating, L/R mirroring, etc.
    """

    def __init__(self, movement_engine: MovementEngine):
        self.engine = movement_engine
        self.group_overrides: Dict[str, MovementParams] = {}
        self.beat_count = 0
        self.odd_even_swap = False  # Swaps on each beat for alternating patterns

        # Orchestration modes
        self.mode = "unified"  # unified, split_odd_even, split_left_right, split_front_back

    def trigger_beat(self, beat_number: int):
        """Handle beat for orchestrated patterns."""
        self.beat_count = beat_number
        self.odd_even_swap = not self.odd_even_swap
        self.engine.trigger_beat()

    def set_mode(self, mode: str, **kwargs):
        """
        Set orchestration mode.

        Modes:
        - unified: All fixtures use same movement
        - split_odd_even: Odd and even fixtures alternate
        - split_left_right: Left and right groups mirror
        - alternating_beat: Odd/even swap movement direction on each beat
        """
        self.mode = mode
        self.group_overrides.clear()

        if mode == "split_odd_even":
            # Odd fixtures: base pattern
            # Even fixtures: inverted (via direction parameter)
            pass

        elif mode == "split_left_right":
            # Left fixtures: pan positive
            # Right fixtures: pan negative (mirrored)
            pass

    def get_position_for_fixture(
        self,
        fixture_id: str,
        fixture_x: float,
        fixture_y: float,
        fixture_z: float,
        index: int,
        phase_offset: float,
        group_type: str = "all"
    ) -> Tuple[float, float]:
        """
        Get orchestrated pan/tilt for a fixture based on its group.

        Args:
            fixture_id: Unique fixture ID
            fixture_x, y, z: Fixture position
            index: Index in fixture list
            phase_offset: Base phase offset
            group_type: Which group this fixture belongs to (odd/even/left/right)
        """
        # Get base position from engine
        base_pan, base_tilt = self.engine._get_static_position(
            fixture_x, fixture_y, fixture_z, index
        )

        if self.engine.params.pattern == MovementType.NONE:
            return (base_pan, base_tilt)

        # Apply orchestration based on mode
        if self.mode == "alternating_beat":
            # Odd/even fixtures swap direction on each beat
            is_odd = index % 2 == 1
            direction = 1
            if is_odd:
                direction = 1 if self.odd_even_swap else -1
            else:
                direction = -1 if self.odd_even_swap else 1

            move_pan, move_tilt = self.engine._calculate_movement(
                fixture_id, index, phase_offset, fixture_x
            )
            return (base_pan + move_pan * direction, base_tilt + move_tilt)

        elif self.mode == "split_left_right":
            # Left and right sides mirror pan movement
            direction = -1 if fixture_x < 0 else 1
            move_pan, move_tilt = self.engine._calculate_movement(
                fixture_id, index, phase_offset, fixture_x
            )
            return (base_pan + move_pan * direction, base_tilt + move_tilt)

        elif self.mode == "tilt_alternating":
            # Odd tilts up, even tilts down (swaps on beat)
            is_odd = index % 2 == 1
            direction = 1
            if is_odd:
                direction = 1 if self.odd_even_swap else -1
            else:
                direction = -1 if self.odd_even_swap else 1

            move_pan, move_tilt = self.engine._calculate_movement(
                fixture_id, index, phase_offset, fixture_x
            )
            return (base_pan + move_pan, base_tilt + move_tilt * direction)

        else:
            # Unified mode - standard movement
            return self.engine.get_position(
                fixture_id, fixture_x, fixture_y, fixture_z, index, phase_offset
            )


# Orchestration presets
ORCHESTRATION_PRESETS = {
    "unified": {"mode": "unified"},
    "odd_even_alternate": {"mode": "alternating_beat"},
    "left_right_mirror": {"mode": "split_left_right"},
    "tilt_alternate": {"mode": "tilt_alternating"},
}


# Static look presets for quick access
STATIC_LOOK_PRESETS = {
    "center": StaticLook.ALL_CENTER,
    "x": StaticLook.X_PATTERN,
    "fan": StaticLook.FAN_OUT,
    "forward": StaticLook.PARALLEL_FORWARD,
    "staggered": StaticLook.STAGGERED_HEIGHTS,
    "corners": StaticLook.OPPOSING_CORNERS,
    "circle": StaticLook.CIRCLE_FLOOR
}
