"""
Professional Strobe, Chase, Color Wash, and Build-Up Effects
Concert-quality effect primitives for the ILS effects engine.

Features:
- Professional strobes: BURST, BEAT_LOCKED, CONTINUOUS, BLINDER, PROGRESSIVE
- Genre-aware strobe budget (EDM=frequent, Rock=2-3/song, Pop=1-2, Hip-Hop=rare, Jazz=never)
- Color wash system with smooth palette cycling and complementary color pairing
- Color temperature management (warm for intimacy, cool for energy)
- Chase effects with BPM-locked speed (1/4 note, 1/2 note, full bar)
- Build-up effects with progressive fixture reveal and snap-to-full
- Pre-drop blackout and flash-blackout-flash patterns
- Blackout/flash timing with OSHA-compliant safety limits
"""

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..effects.color_mapper import RGB


# =============================================================================
# PROFESSIONAL STROBE SYSTEM
# =============================================================================

class ProStrobeMode(Enum):
    """Professional strobe modes."""
    OFF = "off"
    BURST = "burst"              # Short high-frequency burst
    BEAT_LOCKED = "beat_locked"  # Flash exactly on beat
    CONTINUOUS = "continuous"    # Steady rate strobe
    BLINDER = "blinder"         # Full white wall of light
    PROGRESSIVE = "progressive"  # Increasing frequency (build-up)
    CHASE_STROBE = "chase_strobe"  # Traveling strobe across rig


@dataclass
class ProStrobeParams:
    """Parameters for professional strobe effects."""
    mode: ProStrobeMode = ProStrobeMode.OFF

    # Frequency settings (Hz)
    frequency: float = 4.0        # Continuous rate
    burst_frequency: float = 12.0 # Burst rate
    burst_duration: float = 2.0   # Burst length (seconds)

    # Progressive strobe
    progressive_start_hz: float = 1.0
    progressive_end_hz: float = 15.0
    progressive_duration: float = 4.0  # Seconds to ramp

    # Beat-locked
    flash_duration: float = 0.06  # Seconds per flash
    flash_beats: List[int] = field(default_factory=lambda: [0])  # Which beats (0-3) to flash

    # Blinder
    blinder_duration: float = 0.15  # Seconds
    blinder_intensity: float = 1.0

    # Chase
    chase_width: int = 2   # Fixtures wide
    chase_speed: float = 2.0  # Fixtures per second

    # Safety
    max_continuous_hz: float = 4.0
    max_burst_hz: float = 15.0
    max_burst_seconds: float = 4.0

    # Intensity
    intensity: float = 1.0


class ProStrobe:
    """
    Professional strobe controller with safety limits and multiple modes.
    Includes genre-aware strobe budgeting to enforce per-song limits.
    """

    # Genre strobe budget: max bursts allowed per song
    GENRE_STROBE_BUDGET = {
        "edm": 999,       # Frequent, no practical limit
        "rock": 3,         # 2-3 per song
        "pop": 2,          # 1-2 max
        "hip_hop": 1,      # Rare
        "jazz": 0,          # Never
    }

    def __init__(self):
        self.params = ProStrobeParams()
        self.time = 0.0

        self._burst_start: Optional[float] = None
        self._progressive_start: Optional[float] = None
        self._beat_flash_time: float = -1.0
        self._blinder_start: Optional[float] = None
        self._last_beat: int = -1
        self._current_beat_in_bar: int = 0

        # Safety
        self._safety_cooldown: float = 0.0

        # Genre-aware strobe budget
        self._genre: str = "edm"
        self._strobe_count_this_song: int = 0
        self._strobe_budget: int = 999

    def set_genre(self, genre: str):
        """Set genre for strobe budget enforcement."""
        self._genre = genre.lower()
        self._strobe_budget = self.GENRE_STROBE_BUDGET.get(self._genre, 999)

    def reset_song_budget(self):
        """Reset strobe count for new song."""
        self._strobe_count_this_song = 0

    @property
    def strobe_budget_remaining(self) -> int:
        return max(0, self._strobe_budget - self._strobe_count_this_song)

    def set_mode(self, mode: ProStrobeMode, **kwargs):
        """Set strobe mode with safety checks and genre budget enforcement."""
        # Genre budget check for burst/blinder modes
        if mode in (ProStrobeMode.BURST, ProStrobeMode.BLINDER, ProStrobeMode.PROGRESSIVE):
            if self._strobe_count_this_song >= self._strobe_budget:
                return  # Budget exhausted, silently refuse

        self.params.mode = mode
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)
        self._enforce_safety()

        if mode == ProStrobeMode.BURST:
            self._burst_start = self.time
            self._strobe_count_this_song += 1
        elif mode == ProStrobeMode.PROGRESSIVE:
            self._progressive_start = self.time
            self._strobe_count_this_song += 1
        elif mode == ProStrobeMode.BLINDER:
            self._blinder_start = self.time
            self._strobe_count_this_song += 1

    def _enforce_safety(self):
        """Enforce OSHA-compliant frequency limits."""
        p = self.params
        if p.mode == ProStrobeMode.CONTINUOUS:
            p.frequency = min(p.frequency, p.max_continuous_hz)
        elif p.mode == ProStrobeMode.BURST:
            p.burst_frequency = min(p.burst_frequency, p.max_burst_hz)
            p.burst_duration = min(p.burst_duration, p.max_burst_seconds)

    def trigger_beat(self, beat_number: int):
        """Handle beat event."""
        if beat_number != self._last_beat:
            self._last_beat = beat_number
            self._current_beat_in_bar = beat_number % 4
            if self._current_beat_in_bar in self.params.flash_beats:
                self._beat_flash_time = self.time

    def trigger_burst(self, duration: float = 2.0, frequency: float = 12.0):
        """Trigger a strobe burst."""
        self.set_mode(ProStrobeMode.BURST,
                      burst_duration=duration,
                      burst_frequency=frequency)

    def trigger_blinder(self, duration: float = 0.15):
        """Trigger a blinder flash."""
        self.set_mode(ProStrobeMode.BLINDER, blinder_duration=duration)

    def stop(self):
        """Stop all strobe effects."""
        self.params.mode = ProStrobeMode.OFF

    def update(self, delta_time: float):
        """Update strobe state."""
        self.time += delta_time

        # Safety cooldown
        if self._safety_cooldown > 0:
            self._safety_cooldown -= delta_time

        # Burst expiration
        if self.params.mode == ProStrobeMode.BURST and self._burst_start is not None:
            if self.time - self._burst_start > self.params.burst_duration:
                self.params.mode = ProStrobeMode.OFF
                self._burst_start = None
                self._safety_cooldown = 2.0

        # Blinder expiration
        if self.params.mode == ProStrobeMode.BLINDER and self._blinder_start is not None:
            if self.time - self._blinder_start > self.params.blinder_duration:
                self.params.mode = ProStrobeMode.OFF
                self._blinder_start = None

        # Progressive expiration
        if self.params.mode == ProStrobeMode.PROGRESSIVE and self._progressive_start is not None:
            if self.time - self._progressive_start > self.params.progressive_duration:
                # Auto-trigger burst at end of progressive
                self.trigger_burst(duration=1.5, frequency=self.params.progressive_end_hz)

    def get_value(self, fixture_index: int = 0, total_fixtures: int = 1,
                  phase_offset: float = 0.0) -> float:
        """
        Get strobe intensity for a fixture.

        Returns:
            0.0 = off, up to 1.0 = full flash
        """
        mode = self.params.mode
        if mode == ProStrobeMode.OFF:
            return 0.0

        if self._safety_cooldown > 0 and mode == ProStrobeMode.BURST:
            return 0.0

        if mode == ProStrobeMode.CONTINUOUS:
            phase = (self.time * self.params.frequency + phase_offset) % 1.0
            return self.params.intensity if phase < 0.5 else 0.0

        elif mode == ProStrobeMode.BURST:
            if self._burst_start is None:
                return 0.0
            phase = (self.time * self.params.burst_frequency + phase_offset) % 1.0
            return self.params.intensity if phase < 0.5 else 0.0

        elif mode == ProStrobeMode.BEAT_LOCKED:
            elapsed = self.time - self._beat_flash_time
            if elapsed < self.params.flash_duration:
                fade = 1.0 - (elapsed / self.params.flash_duration)
                return self.params.intensity * fade
            return 0.0

        elif mode == ProStrobeMode.BLINDER:
            return self.params.blinder_intensity

        elif mode == ProStrobeMode.PROGRESSIVE:
            if self._progressive_start is None:
                return 0.0
            elapsed = self.time - self._progressive_start
            progress = min(1.0, elapsed / self.params.progressive_duration)
            # Quadratic frequency ramp for dramatic build
            current_freq = (self.params.progressive_start_hz +
                          (self.params.progressive_end_hz - self.params.progressive_start_hz) *
                          progress ** 2)
            phase = (self.time * current_freq + phase_offset) % 1.0
            return self.params.intensity * progress if phase < 0.5 else 0.0

        elif mode == ProStrobeMode.CHASE_STROBE:
            chase_pos = (self.time * self.params.chase_speed) % total_fixtures
            distance = abs(fixture_index - chase_pos)
            distance = min(distance, total_fixtures - distance)
            if distance < self.params.chase_width:
                # Strobe the active fixtures
                strobe_phase = (self.time * self.params.frequency) % 1.0
                if strobe_phase < 0.5:
                    return self.params.intensity * (1.0 - distance / self.params.chase_width)
            return 0.0

        return 0.0

    def is_active(self) -> bool:
        return self.params.mode != ProStrobeMode.OFF


# =============================================================================
# COLOR WASH SYSTEM
# =============================================================================

# Complementary color pairs for professional palette generation
COMPLEMENTARY_PAIRS: List[Tuple[RGB, RGB]] = [
    (RGB.from_hsv(190, 1.0, 1.0), RGB.from_hsv(310, 1.0, 1.0)),   # Cyan + Magenta
    (RGB.from_hsv(220, 1.0, 0.9), RGB.from_hsv(30, 1.0, 1.0)),    # Blue + Orange
    (RGB.from_hsv(270, 0.9, 0.9), RGB.from_hsv(60, 1.0, 1.0)),    # Purple + Yellow
    (RGB.from_hsv(0, 1.0, 1.0), RGB.from_hsv(160, 1.0, 0.9)),     # Red + Teal
    (RGB.from_hsv(120, 0.9, 0.8), RGB.from_hsv(300, 0.9, 1.0)),   # Green + Pink
]


class ColorTemperature(Enum):
    """Color temperature presets for mood control."""
    WARM = "warm"           # Amber/orange tint for intimacy (2700K-3500K feel)
    NEUTRAL = "neutral"     # Balanced white
    COOL = "cool"           # Blue tint for energy (5500K-7000K feel)
    COLD = "cold"           # Deep blue for tension


# Color temperature tint overlays (applied as blend)
COLOR_TEMP_TINTS = {
    ColorTemperature.WARM: RGB(1.0, 0.85, 0.6),
    ColorTemperature.NEUTRAL: RGB(1.0, 1.0, 1.0),
    ColorTemperature.COOL: RGB(0.8, 0.9, 1.0),
    ColorTemperature.COLD: RGB(0.6, 0.7, 1.0),
}


@dataclass
class WashColor:
    """A color with transition metadata."""
    color: RGB
    hold_bars: float = 2.0  # Bars to hold this color
    fade_bars: float = 1.0  # Bars to fade to next color


class ProColorWash:
    """
    Professional color wash system with palette cycling,
    complementary color pairing, color temperature management,
    and smooth transitions at phrase boundaries.
    """

    def __init__(self, bpm: float = 128.0):
        self._bpm = bpm
        self._colors: List[WashColor] = []
        self._current_index = 0
        self._time = 0.0
        self._cycle_time = 0.0

        # Output state
        self._current_color = RGB(1.0, 1.0, 1.0)
        self._fixture_colors: Dict[int, RGB] = {}

        # Spatial offset for fixture variation
        self._fixture_phase_spread: float = 0.0  # 0=all same, 1=full spread

        # Color temperature
        self._color_temperature = ColorTemperature.NEUTRAL
        self._temp_blend: float = 0.0  # 0=no tint, 1=full tint

        # Snap transition state
        self._snap_active = False
        self._snap_color: Optional[RGB] = None
        self._snap_start: float = 0.0
        self._snap_hold: float = 0.0

    def set_bpm(self, bpm: float):
        self._bpm = max(30.0, min(300.0, bpm))

    def set_palette(self, colors: List[RGB], hold_bars: float = 2.0,
                    fade_bars: float = 1.0):
        """Set color wash palette."""
        self._colors = [WashColor(c, hold_bars, fade_bars) for c in colors]
        self._current_index = 0
        self._cycle_time = 0.0

    def set_fixture_spread(self, spread: float):
        """Set phase spread across fixtures (0=unison, 1=full offset)."""
        self._fixture_phase_spread = max(0.0, min(1.0, spread))

    def set_complementary_palette(self, pair_index: int = 0,
                                   hold_bars: float = 2.0,
                                   fade_bars: float = 1.0):
        """Set palette from pre-defined complementary color pairs."""
        pair = COMPLEMENTARY_PAIRS[pair_index % len(COMPLEMENTARY_PAIRS)]
        self.set_palette(list(pair), hold_bars, fade_bars)

    def set_color_temperature(self, temp: ColorTemperature, blend: float = 0.3):
        """Set color temperature tint overlay."""
        self._color_temperature = temp
        self._temp_blend = max(0.0, min(1.0, blend))

    def trigger_snap_to_color(self, color: RGB, hold_bars: float = 0.5):
        """Snap instantly to a color (blackout-to-color transition for impact)."""
        self._snap_active = True
        self._snap_color = color
        self._snap_start = self._time
        self._snap_hold = self._bars_to_seconds(hold_bars)

    def trigger_rainbow_cycle(self, cycle_bars: float = 2.0):
        """Trigger a rainbow/color cycle effect for peak moments."""
        rainbow = [
            RGB.from_hsv(0, 1.0, 1.0),    # Red
            RGB.from_hsv(30, 1.0, 1.0),    # Orange
            RGB.from_hsv(60, 1.0, 1.0),    # Yellow
            RGB.from_hsv(120, 1.0, 1.0),   # Green
            RGB.from_hsv(190, 1.0, 1.0),   # Cyan
            RGB.from_hsv(240, 1.0, 1.0),   # Blue
            RGB.from_hsv(280, 1.0, 1.0),   # Purple
            RGB.from_hsv(320, 1.0, 1.0),   # Pink
        ]
        hold_per_color = cycle_bars / len(rainbow)
        self.set_palette(rainbow, hold_bars=hold_per_color, fade_bars=hold_per_color * 0.5)
        self.set_fixture_spread(1.0)  # Full spread for rainbow effect

    def _bars_to_seconds(self, bars: float) -> float:
        return (bars * 4 * 60.0) / self._bpm

    def update(self, delta_time: float):
        """Update color wash state."""
        self._time += delta_time

        # Snap transition expiration
        if self._snap_active and self._snap_start > 0:
            if self._time - self._snap_start > self._snap_hold:
                self._snap_active = False
                self._snap_color = None

        if not self._colors:
            return

        self._cycle_time += delta_time

        # Calculate total cycle duration for current color
        current_wash = self._colors[self._current_index % len(self._colors)]
        total_duration = self._bars_to_seconds(current_wash.hold_bars + current_wash.fade_bars)

        if total_duration <= 0:
            return

        if self._cycle_time >= total_duration:
            self._cycle_time -= total_duration
            self._current_index = (self._current_index + 1) % len(self._colors)

    def get_color(self, fixture_index: int = 0, total_fixtures: int = 1) -> RGB:
        """Get current color for a fixture, with temperature tint applied."""
        # Snap override takes priority
        if self._snap_active and self._snap_color is not None:
            return self._apply_temperature(self._snap_color)

        if not self._colors:
            return self._apply_temperature(RGB(1.0, 1.0, 1.0))

        # Phase offset for this fixture
        phase_offset = 0.0
        if total_fixtures > 1 and self._fixture_phase_spread > 0:
            phase_offset = (fixture_index / total_fixtures) * self._fixture_phase_spread

        # Offset the cycle time for this fixture
        current_wash = self._colors[self._current_index % len(self._colors)]
        hold_sec = self._bars_to_seconds(current_wash.hold_bars)
        fade_sec = self._bars_to_seconds(current_wash.fade_bars)
        total_sec = hold_sec + fade_sec

        offset_time = (self._cycle_time + phase_offset * total_sec) % total_sec

        idx = self._current_index % len(self._colors)
        next_idx = (idx + 1) % len(self._colors)
        current_color = self._colors[idx].color
        next_color = self._colors[next_idx].color

        if offset_time < hold_sec:
            color = current_color
        else:
            blend = (offset_time - hold_sec) / max(0.01, fade_sec)
            blend = max(0.0, min(1.0, blend))
            color = current_color.blend(next_color, blend)

        return self._apply_temperature(color)

    def _apply_temperature(self, color: RGB) -> RGB:
        """Apply color temperature tint to a color."""
        if self._temp_blend <= 0.0 or self._color_temperature == ColorTemperature.NEUTRAL:
            return color
        tint = COLOR_TEMP_TINTS[self._color_temperature]
        return RGB(
            color.r * (1.0 - self._temp_blend) + color.r * tint.r * self._temp_blend,
            color.g * (1.0 - self._temp_blend) + color.g * tint.g * self._temp_blend,
            color.b * (1.0 - self._temp_blend) + color.b * tint.b * self._temp_blend,
        )


# =============================================================================
# CHASE EFFECTS
# =============================================================================

class ChaseDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    BOUNCE = "bounce"
    CENTER_OUT = "center_out"
    RANDOM = "random"


class ChaseSpeed(Enum):
    """BPM-locked chase speed notation."""
    QUARTER_NOTE = 0.25    # 1/4 note - one fixture per beat
    HALF_NOTE = 0.5        # 1/2 note - one fixture per 2 beats
    WHOLE_NOTE = 1.0       # Full bar - one fixture per bar (4 beats)
    EIGHTH_NOTE = 0.125    # 1/8 note - two fixtures per beat
    SIXTEENTH_NOTE = 0.0625  # 1/16 note - four fixtures per beat


@dataclass
class ProChaseParams:
    """Parameters for chase effects."""
    direction: ChaseDirection = ChaseDirection.FORWARD
    speed_bpm_fraction: float = 1.0  # Speed as fraction of BPM
    width: int = 2  # How many fixtures wide the chase head is
    tail_length: int = 3  # Fade tail length in fixtures
    intensity: float = 1.0
    color: Optional[RGB] = None  # None = use existing color


class ProChase:
    """
    Professional chase effect with direction control,
    variable width, and configurable fade tails.
    """

    def __init__(self, bpm: float = 128.0):
        self._bpm = bpm
        self.params = ProChaseParams()
        self._time = 0.0
        self._bounce_direction = 1.0

    def set_bpm(self, bpm: float):
        self._bpm = max(30.0, min(300.0, bpm))

    def set_params(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)

    def set_bpm_locked_speed(self, note_value: ChaseSpeed):
        """Set chase speed using BPM-locked note values."""
        self.params.speed_bpm_fraction = note_value.value

    def update(self, delta_time: float):
        self._time += delta_time

    def get_intensity(self, fixture_index: int, total_fixtures: int) -> float:
        """
        Get chase intensity for a fixture.

        Returns:
            0.0 to 1.0 intensity multiplier
        """
        if total_fixtures <= 0:
            return 0.0

        speed_hz = (self._bpm / 60.0) * self.params.speed_bpm_fraction
        # Position of chase head (in fixture units)
        raw_pos = self._time * speed_hz * total_fixtures / max(1, total_fixtures)

        direction = self.params.direction
        if direction == ChaseDirection.FORWARD:
            chase_pos = raw_pos % total_fixtures
        elif direction == ChaseDirection.BACKWARD:
            chase_pos = (total_fixtures - raw_pos % total_fixtures) % total_fixtures
        elif direction == ChaseDirection.BOUNCE:
            cycle = raw_pos % (total_fixtures * 2)
            if cycle < total_fixtures:
                chase_pos = cycle
            else:
                chase_pos = total_fixtures * 2 - cycle
        elif direction == ChaseDirection.CENTER_OUT:
            center = total_fixtures / 2.0
            spread = (raw_pos % total_fixtures) / total_fixtures
            dist_from_center = abs(fixture_index - center)
            max_dist = center
            if max_dist > 0:
                target_dist = spread * max_dist
                if abs(dist_from_center - target_dist) < self.params.width:
                    return self.params.intensity
            return 0.0
        elif direction == ChaseDirection.RANDOM:
            # Pseudo-random based on time and fixture
            seed = int(self._time * speed_hz * 10)
            if (seed + fixture_index) % total_fixtures < self.params.width:
                return self.params.intensity
            return 0.0
        else:
            chase_pos = raw_pos % total_fixtures

        # Calculate distance from chase head
        distance = abs(fixture_index - chase_pos)
        distance = min(distance, total_fixtures - distance)  # Wrap

        # Chase head
        if distance < self.params.width:
            return self.params.intensity

        # Tail fade
        tail_distance = distance - self.params.width
        if tail_distance < self.params.tail_length and self.params.tail_length > 0:
            fade = 1.0 - (tail_distance / self.params.tail_length)
            return self.params.intensity * fade * 0.6

        return 0.0


# =============================================================================
# BUILD-UP EFFECTS
# =============================================================================

class ProBuildEffect:
    """
    Professional build-up effect for creating tension before drops.

    Combines:
    - Progressive intensity ramp
    - Increasing strobe frequency
    - Narrowing movement (converges to center)
    - Color desaturation toward white
    """

    def __init__(self, bpm: float = 128.0):
        self._bpm = bpm
        self._active = False
        self._start_time = 0.0
        self._duration_beats = 16.0
        self._time = 0.0

        # Ramp curves
        self._intensity_curve = "quadratic"  # linear, quadratic, exponential

    def set_bpm(self, bpm: float):
        self._bpm = max(30.0, min(300.0, bpm))

    def trigger(self, duration_beats: float = 16.0, curve: str = "quadratic"):
        """Start a build-up effect."""
        self._active = True
        self._start_time = self._time
        self._duration_beats = max(1.0, duration_beats)
        self._intensity_curve = curve

    def stop(self):
        self._active = False

    def update(self, delta_time: float):
        self._time += delta_time

        if self._active:
            beat_duration = 60.0 / self._bpm
            elapsed_beats = (self._time - self._start_time) / beat_duration
            if elapsed_beats >= self._duration_beats:
                self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def progress(self) -> float:
        """Get build-up progress (0-1)."""
        if not self._active:
            return 0.0
        beat_duration = 60.0 / self._bpm
        elapsed_beats = (self._time - self._start_time) / beat_duration
        raw = min(1.0, elapsed_beats / self._duration_beats)

        if self._intensity_curve == "linear":
            return raw
        elif self._intensity_curve == "quadratic":
            return raw ** 2
        elif self._intensity_curve == "exponential":
            return (math.exp(raw * 3) - 1) / (math.exp(3) - 1)
        return raw

    def get_intensity_multiplier(self) -> float:
        """Get intensity multiplier for build-up (0.3 to 1.0)."""
        if not self._active:
            return 1.0
        return 0.3 + 0.7 * self.progress

    def get_strobe_frequency(self) -> float:
        """Get strobe frequency for build-up (1Hz to 12Hz)."""
        if not self._active:
            return 0.0
        return 1.0 + 11.0 * self.progress

    def get_movement_scale(self) -> float:
        """Get movement amplitude scale (1.0 narrowing to 0.2)."""
        if not self._active:
            return 1.0
        return 1.0 - 0.8 * self.progress

    def get_color_desaturation(self) -> float:
        """Get color desaturation amount (0=full color, 1=white)."""
        if not self._active:
            return 0.0
        return self.progress * 0.6  # Max 60% desaturation

    def get_fixture_reveal_mask(self, fixture_index: int, total_fixtures: int) -> float:
        """
        Get fixture reveal multiplier for progressive build-up.
        During build, fixtures light up one by one from center outward.

        Returns:
            1.0 if fixture should be on, 0.0 if not yet revealed
        """
        if not self._active or total_fixtures <= 0:
            return 1.0
        # Number of fixtures currently revealed
        revealed = max(1, int(self.progress * total_fixtures))
        # Reveal from center outward
        center = total_fixtures / 2.0
        distance_from_center = abs(fixture_index - center)
        max_distance = center
        # Fixtures closer to center are revealed first
        if max_distance <= 0:
            return 1.0
        fixture_threshold = distance_from_center / max_distance
        reveal_threshold = self.progress
        return 1.0 if fixture_threshold <= reveal_threshold else 0.0

    def get_saturation_increase(self) -> float:
        """Get color saturation multiplier (increases during build)."""
        if not self._active:
            return 1.0
        # Start at 50% saturation, ramp to 100%
        return 0.5 + 0.5 * self.progress


# =============================================================================
# BLACKOUT / FLASH TIMING SEQUENCES
# =============================================================================

class BlackoutSequenceStep(Enum):
    """Steps within a blackout/flash sequence."""
    IDLE = "idle"
    BLACKOUT = "blackout"
    FLASH = "flash"


@dataclass
class BlackoutSequence:
    """Timed blackout and flash-blackout-flash patterns.

    Sequences are defined as a list of (step_type, duration_seconds) pairs.
    The sequence plays through once, then returns to IDLE.
    """
    steps: List[Tuple[BlackoutSequenceStep, float]] = field(default_factory=list)
    _current_step: int = 0
    _step_elapsed: float = 0.0
    _active: bool = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def current_state(self) -> BlackoutSequenceStep:
        if not self._active or self._current_step >= len(self.steps):
            return BlackoutSequenceStep.IDLE
        return self.steps[self._current_step][0]

    def start(self):
        """Start the sequence from the beginning."""
        if not self.steps:
            return
        self._current_step = 0
        self._step_elapsed = 0.0
        self._active = True

    def stop(self):
        """Stop the sequence immediately."""
        self._active = False
        self._current_step = 0
        self._step_elapsed = 0.0

    def update(self, delta_time: float):
        """Advance the sequence."""
        if not self._active or self._current_step >= len(self.steps):
            self._active = False
            return

        self._step_elapsed += delta_time
        step_duration = self.steps[self._current_step][1]

        if self._step_elapsed >= step_duration:
            self._step_elapsed -= step_duration
            self._current_step += 1
            if self._current_step >= len(self.steps):
                self._active = False

    def get_dimmer_override(self) -> Optional[float]:
        """Get dimmer override from the current sequence step.

        Returns:
            None if idle (no override), 0.0 for blackout, 1.0 for flash.
        """
        state = self.current_state
        if state == BlackoutSequenceStep.BLACKOUT:
            return 0.0
        elif state == BlackoutSequenceStep.FLASH:
            return 1.0
        return None


def create_pre_drop_blackout(duration: float = 0.75) -> BlackoutSequence:
    """Create a pre-drop blackout sequence (0.5-1s darkness before drop).

    Classic concert LD trick: total darkness right before the drop so the
    explosion of light feels even more dramatic.
    """
    return BlackoutSequence(steps=[
        (BlackoutSequenceStep.BLACKOUT, duration),
    ])


def create_flash_blackout_flash(
    flash_dur: float = 0.08,
    blackout_dur: float = 0.15,
) -> BlackoutSequence:
    """Create a flash-blackout-flash emphasis pattern.

    Used for big hits: flash -> brief darkness -> flash. Creates a visual
    double-take that punctuates key musical moments.
    """
    return BlackoutSequence(steps=[
        (BlackoutSequenceStep.FLASH, flash_dur),
        (BlackoutSequenceStep.BLACKOUT, blackout_dur),
        (BlackoutSequenceStep.FLASH, flash_dur),
    ])


def create_section_transition_blackout(duration: float = 0.3) -> BlackoutSequence:
    """Create a clean section transition via momentary blackout.

    Brief darkness to reset the audience's visual palette between
    song sections (e.g. verse -> chorus).
    """
    return BlackoutSequence(steps=[
        (BlackoutSequenceStep.BLACKOUT, duration),
    ])


# =============================================================================
# COMBINED PRO EFFECTS MANAGER
# =============================================================================

class ProEffects:
    """
    Unified manager for all professional effects.
    Coordinates strobe, wash, chase, build-up, and blackout sequence effects.
    """

    def __init__(self, bpm: float = 128.0):
        self.strobe = ProStrobe()
        self.wash = ProColorWash(bpm)
        self.chase = ProChase(bpm)
        self.build = ProBuildEffect(bpm)
        self._bpm = bpm

        # Blackout/flash sequence state
        self._blackout_seq: Optional[BlackoutSequence] = None

    def set_bpm(self, bpm: float):
        """Set BPM for all sub-effects."""
        self._bpm = bpm
        self.wash.set_bpm(bpm)
        self.chase.set_bpm(bpm)
        self.build.set_bpm(bpm)

    def set_genre(self, genre: str):
        """Propagate genre to sub-effects that need it."""
        self.strobe.set_genre(genre)

    def trigger_beat(self, beat_number: int):
        """Forward beat to all effects that need it."""
        self.strobe.trigger_beat(beat_number)

    def update(self, delta_time: float):
        """Update all effects."""
        self.strobe.update(delta_time)
        self.wash.update(delta_time)
        self.chase.update(delta_time)
        self.build.update(delta_time)

        # Update blackout sequence
        if self._blackout_seq is not None and self._blackout_seq.is_active:
            self._blackout_seq.update(delta_time)
            if not self._blackout_seq.is_active:
                self._blackout_seq = None

    def get_blackout_override(self) -> Optional[float]:
        """Get dimmer override from active blackout/flash sequence.

        Returns None if no sequence is active. Otherwise returns
        0.0 (blackout) or 1.0 (flash).
        """
        if self._blackout_seq is not None and self._blackout_seq.is_active:
            return self._blackout_seq.get_dimmer_override()
        return None

    def trigger_pre_drop_blackout(self, duration: float = 0.75):
        """Trigger a pre-drop blackout (0.5-1s darkness before drop).

        Call this 0.5-1s before the drop hits, then trigger_drop() when
        the drop arrives for maximum impact.
        """
        self._blackout_seq = create_pre_drop_blackout(duration)
        self._blackout_seq.start()

    def trigger_flash_blackout_flash(
        self, flash_dur: float = 0.08, blackout_dur: float = 0.15
    ):
        """Trigger flash-blackout-flash emphasis pattern.

        Use on big musical moments (drop hits, key changes, final note).
        """
        self._blackout_seq = create_flash_blackout_flash(flash_dur, blackout_dur)
        self._blackout_seq.start()

    def trigger_section_blackout(self, duration: float = 0.3):
        """Trigger a clean section transition blackout."""
        self._blackout_seq = create_section_transition_blackout(duration)
        self._blackout_seq.start()

    def trigger_drop(self):
        """Full drop sequence: flash-blackout-flash + burst strobe.

        Combines the flash pattern with a strobe burst for maximum
        visual impact on the drop downbeat.
        """
        self.trigger_flash_blackout_flash()
        self.strobe.trigger_burst(duration=2.0, frequency=12.0)

    def get_fixture_output(self, fixture_index: int, total_fixtures: int,
                           phase_offset: float = 0.0) -> Dict:
        """
        Get combined effect output for a fixture.

        Returns dict with keys:
        - strobe_value: 0-1 strobe intensity
        - wash_color: RGB color from wash
        - chase_intensity: 0-1 chase multiplier
        - build_intensity: 0-1 build-up intensity multiplier
        - build_movement_scale: 0-1 movement scale from build-up
        - build_desaturation: 0-1 color desaturation from build-up
        - blackout_override: None or 0.0/1.0 from blackout sequence
        """
        return {
            "strobe_value": self.strobe.get_value(fixture_index, total_fixtures, phase_offset),
            "wash_color": self.wash.get_color(fixture_index, total_fixtures),
            "chase_intensity": self.chase.get_intensity(fixture_index, total_fixtures),
            "build_intensity": self.build.get_intensity_multiplier(),
            "build_movement_scale": self.build.get_movement_scale(),
            "build_desaturation": self.build.get_color_desaturation(),
            "blackout_override": self.get_blackout_override(),
        }

    def blackout(self):
        """Kill all effects."""
        self.strobe.stop()
        self.build.stop()
        if self._blackout_seq is not None:
            self._blackout_seq.stop()
            self._blackout_seq = None

    def flash(self, duration: float = 0.1):
        """Quick white flash (blinder)."""
        self.strobe.trigger_blinder(duration)
