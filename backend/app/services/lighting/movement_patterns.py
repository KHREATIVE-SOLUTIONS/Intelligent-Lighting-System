"""
Professional Beam Patterns and Movement Effects
Concert-quality movement choreography with fixture grouping and BPM locking.

Patterns:
- MIRROR_SWEEP: L/R symmetrical sweeps
- CENTER_OUT_WAVE: Ripple from center
- FIGURE_8: Lissajous figure-8
- TRUE_CIRCLE: Perfect circular motion
- HORIZONTAL_SWEEP: Simple pan oscillation
- VERTICAL_FAN: Tilt spread effect
- BALLYHOO: Classic industry ballyhoo
- CROSS_CHASE: Alternating L/R chase
- TILT_WAVE: Tilt ripple across rig

Phase spread system: 0=unison to 1=full spread
BPM-locked speed calculation
Fixture grouping: left/right, odd/even, front/back
"""

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ProMovementPattern(Enum):
    """Professional movement pattern types."""
    # Symmetrical beam patterns
    MIRROR_SWEEP = "mirror_sweep"
    CENTER_OUT_WAVE = "center_out_wave"
    FIGURE_8 = "figure_8"
    TRUE_CIRCLE = "true_circle"
    HORIZONTAL_SWEEP = "horizontal_sweep"
    VERTICAL_FAN = "vertical_fan"
    BALLYHOO = "ballyhoo"
    CROSS_CHASE = "cross_chase"
    TILT_WAVE = "tilt_wave"
    STATIC = "static"

    # Chase sequences
    SEQUENTIAL_CHASE = "sequential_chase"
    BOUNCE_CHASE = "bounce_chase"
    RANDOM_CHASE = "random_chase"
    ODD_EVEN_CHASE = "odd_even_chase"
    CENTER_OUT_CHASE = "center_out_chase"

    # Additional professional patterns
    SNAP_HOLD = "snap_hold"           # Instant position jump on beat, hold until next
    BALLYHOO_WIDE = "ballyhoo_wide"   # Dramatic wide ballyhoo for large stages
    SPLIT_SWEEP = "split_sweep"       # L/R halves sweep opposite, independent timing


class FixtureGrouping(Enum):
    """Fixture grouping modes for split-action patterns."""
    ALL = "all"
    LEFT_RIGHT = "left_right"
    ODD_EVEN = "odd_even"
    FRONT_BACK = "front_back"
    CENTER_EDGES = "center_edges"
    PAIRS = "pairs"


# Predefined fixture grouping configurations
FIXTURE_GROUPING = {
    "all": FixtureGrouping.ALL,
    "left_right": FixtureGrouping.LEFT_RIGHT,
    "odd_even": FixtureGrouping.ODD_EVEN,
    "front_back": FixtureGrouping.FRONT_BACK,
    "center_edges": FixtureGrouping.CENTER_EDGES,
    "pairs": FixtureGrouping.PAIRS,
}


@dataclass
class ProMovementParams:
    """Parameters for a professional movement pattern."""
    pattern: ProMovementPattern = ProMovementPattern.STATIC

    # Speed control
    bpm: float = 128.0
    beat_divisor: float = 1.0  # 1=one cycle per beat, 0.5=one per 2 beats, 2=two per beat

    # Amplitude (degrees)
    pan_amplitude: float = 60.0
    tilt_amplitude: float = 40.0

    # Phase spread (0=unison, 1=full spread)
    phase_spread: float = 0.8

    # Grouping
    grouping: FixtureGrouping = FixtureGrouping.ALL

    # Wave shape
    wave_shape: str = "sine"  # sine, triangle, square

    # Smoothing (exponential filter factor)
    smoothing: float = 0.2

    # Direction multiplier (-1 to reverse)
    direction: float = 1.0

    # Chase tail width (number of fixtures in the fade tail behind the chase head)
    # Larger values = smoother chase, smaller = sharper
    chase_tail_width: float = 1.5

    # Snap-hold: list of target positions (pan, tilt) that cycle on each beat
    snap_positions: List[Tuple[float, float]] = field(default_factory=list)


class ProMovementEngine:
    """
    Professional movement pattern engine with BPM-locked timing,
    phase spread, and fixture grouping.
    """

    def __init__(self):
        self.params = ProMovementParams()
        self.time = 0.0
        self._delta_time = 1.0 / 60.0

        # Per-fixture smoothed output
        self._current_positions: Dict[str, Tuple[float, float]] = {}

        # Beat tracking
        self._beat_time = 0.0
        self._beat_count = 0
        self._bump_active = False
        self._bump_start = 0.0
        self._bump_direction = 1

        # Speed ramp state (for buildup acceleration)
        self._speed_ramp_active = False
        self._speed_ramp_start: float = 0.0
        self._speed_ramp_duration: float = 8.0  # seconds
        self._speed_ramp_start_mult: float = 0.25
        self._speed_ramp_end_mult: float = 2.0

        # Snap-hold state
        self._snap_position_index: int = 0

    def set_pattern(self, pattern: ProMovementPattern, **kwargs):
        """Set the current movement pattern with optional overrides."""
        self.params.pattern = pattern
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)

    def set_bpm(self, bpm: float):
        """Update BPM for speed calculation."""
        self.params.bpm = max(30.0, min(300.0, bpm))

    def trigger_beat(self):
        """Trigger beat event for beat-locked patterns."""
        self._beat_time = self.time
        self._beat_count += 1
        self._bump_active = True
        self._bump_start = self.time
        self._bump_direction *= -1

        # Advance snap-hold position on each beat
        if self.params.pattern == ProMovementPattern.SNAP_HOLD and self.params.snap_positions:
            self._snap_position_index = (self._snap_position_index + 1) % len(self.params.snap_positions)

    def start_speed_ramp(self, duration: float = 8.0,
                         start_mult: float = 0.25, end_mult: float = 2.0):
        """
        Start a speed ramp (for buildup acceleration).

        Args:
            duration: Ramp duration in seconds
            start_mult: Speed multiplier at start (e.g. 0.25 = quarter speed)
            end_mult: Speed multiplier at end (e.g. 2.0 = double speed)
        """
        self._speed_ramp_active = True
        self._speed_ramp_start = self.time
        self._speed_ramp_duration = max(0.1, duration)
        self._speed_ramp_start_mult = start_mult
        self._speed_ramp_end_mult = end_mult

    def stop_speed_ramp(self):
        """Stop the speed ramp, returning to normal speed."""
        self._speed_ramp_active = False

    def update(self, delta_time: float):
        """Update engine timing."""
        self.time += delta_time
        self._delta_time = delta_time

    def _get_bpm_speed(self) -> float:
        """Calculate speed in Hz from BPM and beat divisor, with optional ramp."""
        base_speed = (self.params.bpm / 60.0) * self.params.beat_divisor

        if self._speed_ramp_active:
            elapsed = self.time - self._speed_ramp_start
            progress = min(1.0, elapsed / self._speed_ramp_duration)
            if progress >= 1.0:
                self._speed_ramp_active = False
                return base_speed * self._speed_ramp_end_mult
            # Quadratic ease-in for natural acceleration feel
            t = progress * progress
            mult = self._speed_ramp_start_mult + (self._speed_ramp_end_mult - self._speed_ramp_start_mult) * t
            return base_speed * mult

        return base_speed

    def _wave(self, phase: float) -> float:
        """Generate wave value for given phase (0-1)."""
        phase = phase % 1.0
        shape = self.params.wave_shape
        if shape == "sine":
            return math.sin(phase * math.pi * 2)
        elif shape == "triangle":
            return 1 - 4 * abs(phase - 0.5)
        elif shape == "square":
            return 1.0 if phase < 0.5 else -1.0
        return math.sin(phase * math.pi * 2)

    def _get_fixture_phase(self, index: int, total: int,
                           fixture_x: float = 0.0) -> float:
        """
        Calculate phase offset for a fixture based on grouping mode.

        Args:
            index: Fixture index
            total: Total fixture count
            fixture_x: Fixture X position (for spatial grouping)

        Returns:
            Phase offset (0-1)
        """
        spread = self.params.phase_spread
        grouping = self.params.grouping

        if total <= 1:
            return 0.0

        if grouping == FixtureGrouping.ALL:
            return (index / total) * spread

        elif grouping == FixtureGrouping.LEFT_RIGHT:
            # Left fixtures get 0 phase, right get 0.5
            side = 0.0 if fixture_x < 0 else 0.5
            within_side = (index % max(1, total // 2)) / max(1, total // 2) * 0.5
            return (side + within_side * spread) % 1.0

        elif grouping == FixtureGrouping.ODD_EVEN:
            # Odd and even fixtures alternate
            group = 0.0 if index % 2 == 0 else 0.5
            return group * spread

        elif grouping == FixtureGrouping.CENTER_EDGES:
            # Center fixtures phase 0, edges phase spread outward
            center = (total - 1) / 2.0
            distance = abs(index - center) / center if center > 0 else 0
            return distance * spread

        elif grouping == FixtureGrouping.PAIRS:
            # Adjacent pairs share phase
            pair_index = index // 2
            total_pairs = max(1, (total + 1) // 2)
            return (pair_index / total_pairs) * spread

        elif grouping == FixtureGrouping.FRONT_BACK:
            # Based on fixture Z position (approximated by index halves)
            half = 0.0 if index < total // 2 else 0.5
            return half * spread

        return (index / total) * spread

    def get_position(self, fixture_id: str, index: int, total: int,
                     fixture_x: float = 0.0, fixture_y: float = 0.0,
                     fixture_z: float = 0.0) -> Tuple[float, float]:
        """
        Calculate pan/tilt offset for a fixture.

        Args:
            fixture_id: Unique fixture ID for smoothing state
            index: Fixture index in the rig
            total: Total fixtures
            fixture_x, y, z: Physical position

        Returns:
            (pan_offset, tilt_offset) in degrees
        """
        pattern = self.params.pattern
        if pattern == ProMovementPattern.STATIC:
            return self._smooth_output(fixture_id, 0.0, 0.0)

        speed = self._get_bpm_speed()
        t = self.time
        phase = self._get_fixture_phase(index, total, fixture_x)
        pan_amp = self.params.pan_amplitude * self.params.direction
        tilt_amp = self.params.tilt_amplitude

        pan_offset = 0.0
        tilt_offset = 0.0

        if pattern == ProMovementPattern.MIRROR_SWEEP:
            # L/R symmetrical opposite movement
            direction = -1.0 if fixture_x < 0 else 1.0
            pan_offset = self._wave(t * speed + phase) * pan_amp * direction
            tilt_offset = self._wave(t * speed * 0.5 + phase) * tilt_amp * 0.3

        elif pattern == ProMovementPattern.CENTER_OUT_WAVE:
            # Wave ripples from center to edges
            center_phase = abs(fixture_x) / 8.0 * self.params.phase_spread
            pan_offset = self._wave(t * speed - center_phase) * pan_amp * 0.5
            tilt_offset = self._wave(t * speed - center_phase) * tilt_amp

        elif pattern == ProMovementPattern.FIGURE_8:
            # Lissajous figure-8 (1:2 frequency ratio)
            pan_offset = self._wave(t * speed + phase) * pan_amp
            tilt_offset = self._wave(t * speed * 2 + phase) * tilt_amp

        elif pattern == ProMovementPattern.TRUE_CIRCLE:
            # True circular: sin for pan, cos for tilt at same frequency
            angle = (t * speed + phase) * math.pi * 2
            pan_offset = math.sin(angle) * pan_amp
            tilt_offset = math.cos(angle) * tilt_amp

        elif pattern == ProMovementPattern.HORIZONTAL_SWEEP:
            # Simple left-right pan oscillation
            pan_offset = self._wave(t * speed + phase) * pan_amp

        elif pattern == ProMovementPattern.VERTICAL_FAN:
            # Tilt spread: each fixture at different tilt, synchronized pan
            fixture_tilt_base = (index / max(1, total - 1) - 0.5) * tilt_amp
            pan_offset = self._wave(t * speed) * pan_amp * 0.5
            tilt_offset = fixture_tilt_base + self._wave(t * speed * 0.5 + phase) * tilt_amp * 0.3

        elif pattern == ProMovementPattern.BALLYHOO:
            # Classic ballyhoo: figure-8 with slight phase stagger
            ballyhoo_phase = phase * 0.25
            angle = (t * speed + ballyhoo_phase) * math.pi * 2
            pan_offset = math.sin(angle) * pan_amp
            tilt_offset = math.sin(angle * 2 + ballyhoo_phase * math.pi) * tilt_amp * 0.7

        elif pattern == ProMovementPattern.CROSS_CHASE:
            # Alternating L/R chase: odd fixtures sweep left, even sweep right
            direction = 1.0 if index % 2 == 0 else -1.0
            chase_phase = (t * speed - phase) % 1.0
            pan_offset = self._wave(chase_phase) * pan_amp * direction
            tilt_offset = self._wave(chase_phase * 0.5) * tilt_amp * 0.4

        elif pattern == ProMovementPattern.TILT_WAVE:
            # Tilt ripple traveling across the rig
            tilt_offset = self._wave(t * speed - phase) * tilt_amp
            # Slight pan coupling for visual interest
            pan_offset = self._wave(t * speed * 0.25 - phase) * pan_amp * 0.15

        # === Chase sequences ===
        elif pattern == ProMovementPattern.SEQUENTIAL_CHASE:
            # Sequential 1-2-3-4-5-6... chase with BPM-locked speed
            tail = self.params.chase_tail_width
            chase_pos = (t * speed * total) % total
            distance = abs(index - chase_pos)
            distance = min(distance, total - distance)  # Wrap
            if distance < tail:
                intensity = max(0.0, 1.0 - distance / tail)
                tilt_offset = -tilt_amp * 0.5 * intensity  # Tilt down when "active"
            else:
                tilt_offset = tilt_amp * 0.3  # Tilt up when "inactive"

        elif pattern == ProMovementPattern.BOUNCE_CHASE:
            # Bounce chase: 1-2-3-4-3-2-1 ping-pong
            tail = self.params.chase_tail_width
            cycle = (t * speed) % 2.0
            if cycle < 1.0:
                chase_pos = cycle * (total - 1)
            else:
                chase_pos = (2.0 - cycle) * (total - 1)
            distance = abs(index - chase_pos)
            if distance < tail:
                intensity = max(0.0, 1.0 - distance / tail)
                tilt_offset = -tilt_amp * 0.5 * intensity
            else:
                tilt_offset = tilt_amp * 0.3

        elif pattern == ProMovementPattern.RANDOM_CHASE:
            # Pseudo-random fixture activation, changes on each beat
            # Use beat count as seed for deterministic randomness
            seed = f"chase:{self._beat_count}:{index}"
            h = hashlib.md5(seed.encode()).hexdigest()
            rand_val = int(h[:8], 16) / 0xFFFFFFFF
            if rand_val < 0.25:  # ~25% of fixtures active at a time
                tilt_offset = -tilt_amp * 0.5
                pan_offset = self._wave(t * speed * 0.5) * pan_amp * 0.3
            else:
                tilt_offset = tilt_amp * 0.2

        elif pattern == ProMovementPattern.ODD_EVEN_CHASE:
            # Odd/even fixtures alternate on each beat
            is_odd = index % 2 == 1
            beat_phase = self._beat_count % 2 == 0
            if (is_odd and beat_phase) or (not is_odd and not beat_phase):
                tilt_offset = -tilt_amp * 0.5  # Active: tilt down
                pan_offset = self._wave(t * speed) * pan_amp * 0.3
            else:
                tilt_offset = tilt_amp * 0.3  # Inactive: tilt up

        elif pattern == ProMovementPattern.CENTER_OUT_CHASE:
            # Chase radiating from center fixture outward
            center = (total - 1) / 2.0
            fixture_dist = abs(index - center)
            max_dist = center if center > 0 else 1.0
            # Chase wave moves outward from center
            chase_wave = (t * speed) % 1.0
            target_dist = chase_wave * max_dist
            distance = abs(fixture_dist - target_dist)
            tail = self.params.chase_tail_width
            if distance < tail:
                intensity = max(0.0, 1.0 - distance / tail)
                tilt_offset = -tilt_amp * 0.5 * intensity
            else:
                tilt_offset = tilt_amp * 0.2

        elif pattern == ProMovementPattern.SNAP_HOLD:
            # Instant position jump on beat, hold until next
            if self.params.snap_positions:
                target_pan, target_tilt = self.params.snap_positions[self._snap_position_index]
                pan_offset = target_pan * pan_amp
                tilt_offset = target_tilt * tilt_amp
            else:
                # Default: cycle through predefined positions
                default_positions = [
                    (0.0, -0.5),    # Center down
                    (-0.8, 0.0),    # Far left
                    (0.8, 0.0),     # Far right
                    (0.0, 0.3),     # Center up
                ]
                pos = default_positions[self._snap_position_index % len(default_positions)]
                pan_offset = pos[0] * pan_amp
                tilt_offset = pos[1] * tilt_amp

        elif pattern == ProMovementPattern.BALLYHOO_WIDE:
            # Dramatic wide ballyhoo for large stages - bigger amplitude, slower tilt
            ballyhoo_phase = phase * 0.3
            angle = (t * speed + ballyhoo_phase) * math.pi * 2
            pan_offset = math.sin(angle) * pan_amp * 1.3  # Extra wide
            # Slower, more dramatic tilt with 3:1 ratio
            tilt_offset = math.sin(angle * 3 + ballyhoo_phase * math.pi) * tilt_amp * 0.5

        elif pattern == ProMovementPattern.SPLIT_SWEEP:
            # Left half sweeps one way, right half the other with offset timing
            is_left = fixture_x < 0
            direction = -1.0 if is_left else 1.0
            # Left side uses phase, right side uses phase + 0.5 for opposition
            side_phase = phase if is_left else phase + 0.5
            pan_offset = self._wave(t * speed + side_phase) * pan_amp * direction
            tilt_offset = self._wave(t * speed * 0.5 + side_phase) * tilt_amp * 0.4

        return self._smooth_output(fixture_id, pan_offset, tilt_offset)

    def _smooth_output(self, fixture_id: str,
                       target_pan: float, target_tilt: float) -> Tuple[float, float]:
        """Apply exponential smoothing for frame-rate-independent output."""
        if fixture_id not in self._current_positions:
            self._current_positions[fixture_id] = (target_pan, target_tilt)
            return (target_pan, target_tilt)

        current_pan, current_tilt = self._current_positions[fixture_id]

        # Frame-rate-independent smoothing
        factor = 1.0 - (1.0 - self.params.smoothing) ** (self._delta_time * 60.0)

        new_pan = current_pan + (target_pan - current_pan) * factor
        new_tilt = current_tilt + (target_tilt - current_tilt) * factor

        self._current_positions[fixture_id] = (new_pan, new_tilt)
        return (new_pan, new_tilt)

    def get_bump_offset(self) -> Tuple[float, float]:
        """
        Get bump offset for beat-triggered snap movements.
        Returns (pan_offset, tilt_offset) that should be added on top of pattern.
        """
        if not self._bump_active:
            return (0.0, 0.0)

        elapsed = self.time - self._bump_start
        attack = 0.05
        decay = 0.2

        if elapsed > attack + decay:
            self._bump_active = False
            return (0.0, 0.0)

        if elapsed < attack:
            intensity = elapsed / attack
        else:
            decay_elapsed = elapsed - attack
            intensity = 1.0 - (decay_elapsed / decay)
            intensity = max(0.0, intensity ** 2)

        pan_bump = intensity * 15.0 * self._bump_direction
        tilt_bump = intensity * 10.0

        return (pan_bump, tilt_bump)

    def get_chase_intensity(self, index: int, total: int) -> float:
        """
        Get dimmer intensity for chase patterns.

        For chase sequences, this returns a brightness value (0-1) that
        creates the visual chase effect by fading fixtures in/out as the
        chase head passes. Non-chase patterns always return 1.0.

        Args:
            index: Fixture index in the rig
            total: Total fixtures

        Returns:
            Intensity value 0.0 to 1.0
        """
        pattern = self.params.pattern
        speed = self._get_bpm_speed()
        t = self.time
        tail = self.params.chase_tail_width

        if pattern == ProMovementPattern.SEQUENTIAL_CHASE:
            chase_pos = (t * speed * total) % total
            distance = abs(index - chase_pos)
            distance = min(distance, total - distance)  # Wrap
            if distance < tail:
                return max(0.0, 1.0 - distance / tail)
            return 0.0

        elif pattern == ProMovementPattern.BOUNCE_CHASE:
            cycle = (t * speed) % 2.0
            if cycle < 1.0:
                chase_pos = cycle * (total - 1)
            else:
                chase_pos = (2.0 - cycle) * (total - 1)
            distance = abs(index - chase_pos)
            if distance < tail:
                return max(0.0, 1.0 - distance / tail)
            return 0.0

        elif pattern == ProMovementPattern.RANDOM_CHASE:
            seed = f"chase:{self._beat_count}:{index}"
            h = hashlib.md5(seed.encode()).hexdigest()
            rand_val = int(h[:8], 16) / 0xFFFFFFFF
            return 1.0 if rand_val < 0.25 else 0.0

        elif pattern == ProMovementPattern.ODD_EVEN_CHASE:
            is_odd = index % 2 == 1
            beat_phase = self._beat_count % 2 == 0
            if (is_odd and beat_phase) or (not is_odd and not beat_phase):
                return 1.0
            return 0.0

        elif pattern == ProMovementPattern.CENTER_OUT_CHASE:
            center = (total - 1) / 2.0
            fixture_dist = abs(index - center)
            max_dist = center if center > 0 else 1.0
            chase_wave = (t * speed) % 1.0
            target_dist = chase_wave * max_dist
            distance = abs(fixture_dist - target_dist)
            if distance < tail:
                return max(0.0, 1.0 - distance / tail)
            return 0.0

        # Non-chase patterns: full intensity
        return 1.0


# =============================================================================
# PATTERN PRESETS - Ready-to-use configurations
# =============================================================================

PRO_MOVEMENT_PRESETS: Dict[str, ProMovementParams] = {
    "mirror_slow": ProMovementParams(
        pattern=ProMovementPattern.MIRROR_SWEEP,
        beat_divisor=0.25,  # 1 cycle per bar
        pan_amplitude=70.0,
        tilt_amplitude=25.0,
        phase_spread=0.8,
        grouping=FixtureGrouping.LEFT_RIGHT,
        smoothing=0.15,
    ),
    "mirror_fast": ProMovementParams(
        pattern=ProMovementPattern.MIRROR_SWEEP,
        beat_divisor=1.0,
        pan_amplitude=55.0,
        tilt_amplitude=20.0,
        phase_spread=0.8,
        grouping=FixtureGrouping.LEFT_RIGHT,
        smoothing=0.25,
    ),
    "center_out_ripple": ProMovementParams(
        pattern=ProMovementPattern.CENTER_OUT_WAVE,
        beat_divisor=0.5,
        pan_amplitude=40.0,
        tilt_amplitude=35.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.CENTER_EDGES,
        smoothing=0.2,
    ),
    "figure_8_chase": ProMovementParams(
        pattern=ProMovementPattern.FIGURE_8,
        beat_divisor=0.5,
        pan_amplitude=60.0,
        tilt_amplitude=35.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.2,
    ),
    "circle_unison": ProMovementParams(
        pattern=ProMovementPattern.TRUE_CIRCLE,
        beat_divisor=0.25,
        pan_amplitude=55.0,
        tilt_amplitude=40.0,
        phase_spread=0.0,  # All in unison
        grouping=FixtureGrouping.ALL,
        smoothing=0.2,
    ),
    "circle_spread": ProMovementParams(
        pattern=ProMovementPattern.TRUE_CIRCLE,
        beat_divisor=0.25,
        pan_amplitude=55.0,
        tilt_amplitude=40.0,
        phase_spread=1.0,  # Full spread
        grouping=FixtureGrouping.ALL,
        smoothing=0.2,
    ),
    "sweep_bar": ProMovementParams(
        pattern=ProMovementPattern.HORIZONTAL_SWEEP,
        beat_divisor=0.25,
        pan_amplitude=80.0,
        tilt_amplitude=0.0,
        phase_spread=0.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.15,
    ),
    "sweep_chase": ProMovementParams(
        pattern=ProMovementPattern.HORIZONTAL_SWEEP,
        beat_divisor=0.5,
        pan_amplitude=65.0,
        tilt_amplitude=0.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
    ),
    "vertical_fan": ProMovementParams(
        pattern=ProMovementPattern.VERTICAL_FAN,
        beat_divisor=0.25,
        pan_amplitude=30.0,
        tilt_amplitude=50.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.15,
    ),
    "ballyhoo_classic": ProMovementParams(
        pattern=ProMovementPattern.BALLYHOO,
        beat_divisor=0.5,
        pan_amplitude=80.0,
        tilt_amplitude=50.0,
        phase_spread=0.3,
        grouping=FixtureGrouping.ALL,
        smoothing=0.2,
    ),
    "ballyhoo_pairs": ProMovementParams(
        pattern=ProMovementPattern.BALLYHOO,
        beat_divisor=0.5,
        pan_amplitude=70.0,
        tilt_amplitude=45.0,
        phase_spread=0.5,
        grouping=FixtureGrouping.PAIRS,
        smoothing=0.2,
    ),
    "cross_chase_fast": ProMovementParams(
        pattern=ProMovementPattern.CROSS_CHASE,
        beat_divisor=1.0,
        pan_amplitude=60.0,
        tilt_amplitude=25.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ODD_EVEN,
        smoothing=0.3,
    ),
    "tilt_wave_slow": ProMovementParams(
        pattern=ProMovementPattern.TILT_WAVE,
        beat_divisor=0.25,
        pan_amplitude=20.0,
        tilt_amplitude=45.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.15,
    ),
    "tilt_wave_fast": ProMovementParams(
        pattern=ProMovementPattern.TILT_WAVE,
        beat_divisor=0.5,
        pan_amplitude=15.0,
        tilt_amplitude=35.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
    ),

    # === Chase sequence presets ===
    "sequential_chase": ProMovementParams(
        pattern=ProMovementPattern.SEQUENTIAL_CHASE,
        beat_divisor=1.0,
        pan_amplitude=20.0,
        tilt_amplitude=45.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.3,
    ),
    "sequential_chase_fast": ProMovementParams(
        pattern=ProMovementPattern.SEQUENTIAL_CHASE,
        beat_divisor=2.0,
        pan_amplitude=15.0,
        tilt_amplitude=40.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.35,
    ),
    "bounce_chase": ProMovementParams(
        pattern=ProMovementPattern.BOUNCE_CHASE,
        beat_divisor=0.5,
        pan_amplitude=20.0,
        tilt_amplitude=45.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
    ),
    "bounce_chase_fast": ProMovementParams(
        pattern=ProMovementPattern.BOUNCE_CHASE,
        beat_divisor=1.0,
        pan_amplitude=15.0,
        tilt_amplitude=40.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.3,
    ),
    "random_chase": ProMovementParams(
        pattern=ProMovementPattern.RANDOM_CHASE,
        beat_divisor=1.0,
        pan_amplitude=25.0,
        tilt_amplitude=40.0,
        phase_spread=0.5,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
    ),
    "odd_even_chase": ProMovementParams(
        pattern=ProMovementPattern.ODD_EVEN_CHASE,
        beat_divisor=1.0,
        pan_amplitude=20.0,
        tilt_amplitude=45.0,
        phase_spread=0.5,
        grouping=FixtureGrouping.ODD_EVEN,
        smoothing=0.3,
    ),
    "center_out_chase": ProMovementParams(
        pattern=ProMovementPattern.CENTER_OUT_CHASE,
        beat_divisor=0.5,
        pan_amplitude=15.0,
        tilt_amplitude=45.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.CENTER_EDGES,
        smoothing=0.25,
    ),
    "center_out_chase_fast": ProMovementParams(
        pattern=ProMovementPattern.CENTER_OUT_CHASE,
        beat_divisor=1.0,
        pan_amplitude=15.0,
        tilt_amplitude=40.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.CENTER_EDGES,
        smoothing=0.3,
    ),

    # === New professional presets ===
    "snap_hold_quad": ProMovementParams(
        pattern=ProMovementPattern.SNAP_HOLD,
        beat_divisor=1.0,
        pan_amplitude=70.0,
        tilt_amplitude=45.0,
        smoothing=0.8,  # High smoothing = instant snap
        snap_positions=[
            (0.0, -0.5),   # Center down
            (-0.8, 0.0),   # Far left
            (0.8, 0.0),    # Far right
            (0.0, 0.3),    # Center up
        ],
    ),
    "snap_hold_lr": ProMovementParams(
        pattern=ProMovementPattern.SNAP_HOLD,
        beat_divisor=1.0,
        pan_amplitude=80.0,
        tilt_amplitude=30.0,
        smoothing=0.8,
        snap_positions=[
            (-1.0, 0.0),   # Far left
            (1.0, 0.0),    # Far right
        ],
    ),
    "ballyhoo_wide_slow": ProMovementParams(
        pattern=ProMovementPattern.BALLYHOO_WIDE,
        beat_divisor=0.25,
        pan_amplitude=95.0,
        tilt_amplitude=55.0,
        phase_spread=0.2,
        grouping=FixtureGrouping.ALL,
        smoothing=0.15,
    ),
    "ballyhoo_wide_fast": ProMovementParams(
        pattern=ProMovementPattern.BALLYHOO_WIDE,
        beat_divisor=0.5,
        pan_amplitude=85.0,
        tilt_amplitude=50.0,
        phase_spread=0.3,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
    ),
    "split_sweep_slow": ProMovementParams(
        pattern=ProMovementPattern.SPLIT_SWEEP,
        beat_divisor=0.25,
        pan_amplitude=70.0,
        tilt_amplitude=30.0,
        phase_spread=0.8,
        grouping=FixtureGrouping.LEFT_RIGHT,
        smoothing=0.15,
    ),
    "split_sweep_fast": ProMovementParams(
        pattern=ProMovementPattern.SPLIT_SWEEP,
        beat_divisor=1.0,
        pan_amplitude=55.0,
        tilt_amplitude=20.0,
        phase_spread=0.8,
        grouping=FixtureGrouping.LEFT_RIGHT,
        smoothing=0.3,
    ),
    "sequential_chase_wide_tail": ProMovementParams(
        pattern=ProMovementPattern.SEQUENTIAL_CHASE,
        beat_divisor=0.5,
        pan_amplitude=20.0,
        tilt_amplitude=45.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.25,
        chase_tail_width=3.0,  # Wide, smooth tail
    ),
    "bounce_chase_tight": ProMovementParams(
        pattern=ProMovementPattern.BOUNCE_CHASE,
        beat_divisor=1.0,
        pan_amplitude=15.0,
        tilt_amplitude=40.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.3,
        chase_tail_width=0.8,  # Tight, sharp chase
    ),
}


# =============================================================================
# GENRE-SPECIFIC SPEED DEFAULTS
# =============================================================================

GENRE_SPEED_DEFAULTS: Dict[str, Dict[str, float]] = {
    "edm": {
        "beat_divisor": 1.0,       # Fast, on-beat movement
        "pan_amplitude": 70.0,     # Wide sweeps
        "tilt_amplitude": 45.0,
        "smoothing": 0.3,          # Snappy response
    },
    "rock": {
        "beat_divisor": 0.5,       # Deliberate, half-beat movement
        "pan_amplitude": 60.0,     # Moderate sweeps
        "tilt_amplitude": 40.0,
        "smoothing": 0.2,          # Smooth transitions
    },
    "pop": {
        "beat_divisor": 0.5,       # Medium speed
        "pan_amplitude": 55.0,     # Clean, not too wide
        "tilt_amplitude": 35.0,
        "smoothing": 0.2,
    },
    "hip_hop": {
        "beat_divisor": 0.25,      # Minimal, slow movement
        "pan_amplitude": 40.0,     # Tight, focused
        "tilt_amplitude": 25.0,
        "smoothing": 0.15,         # Very smooth
    },
    "jazz": {
        "beat_divisor": 0.25,      # Slow, subtle movement
        "pan_amplitude": 35.0,     # Gentle sweeps
        "tilt_amplitude": 20.0,
        "smoothing": 0.1,          # Ultra-smooth
    },
}


def apply_genre_defaults(params: ProMovementParams, genre: str) -> ProMovementParams:
    """Apply genre-specific speed and amplitude defaults to movement parameters."""
    defaults = GENRE_SPEED_DEFAULTS.get(genre.lower())
    if defaults is None:
        return params
    params.beat_divisor = defaults["beat_divisor"]
    params.pan_amplitude = defaults["pan_amplitude"]
    params.tilt_amplitude = defaults["tilt_amplitude"]
    params.smoothing = defaults["smoothing"]
    return params


# =============================================================================
# DMX CONVERSION UTILITIES
# =============================================================================

def degrees_to_dmx_pan(degrees: float, pan_range: float = 540.0) -> int:
    """
    Convert pan angle in degrees to DMX value (0-255).

    Matches the fixture_groups.py convention:
    pan range -270 to +270 (540 degrees total) maps to DMX 0-255.

    Args:
        degrees: Pan angle in degrees (centered at 0)
        pan_range: Total pan range (default 540 for standard movers)

    Returns:
        DMX value 0-255
    """
    half_range = pan_range / 2.0
    normalized = (degrees + half_range) / pan_range
    return max(0, min(255, int(normalized * 255)))


def degrees_to_dmx_tilt(degrees: float, tilt_range: float = 270.0) -> int:
    """
    Convert tilt angle in degrees to DMX value (0-255).

    Matches the fixture_groups.py convention:
    tilt range -135 to +135 (270 degrees total) maps to DMX 0-255.

    Args:
        degrees: Tilt angle in degrees (centered at 0)
        tilt_range: Total tilt range (default 270 for standard movers)

    Returns:
        DMX value 0-255
    """
    half_range = tilt_range / 2.0
    normalized = (degrees + half_range) / tilt_range
    return max(0, min(255, int(normalized * 255)))
