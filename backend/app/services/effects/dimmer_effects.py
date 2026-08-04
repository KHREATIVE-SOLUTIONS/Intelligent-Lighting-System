"""
Dimmer Effects Engine
Controls intensity/brightness for fixtures (Layer 3)

10 Dimmer Effect Types
"""

from enum import Enum
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass
import math
import random


class DimmerType(Enum):
    """Dimmer effect types."""
    NONE = "none"                    # Static intensity
    SINE_PULSE = "sine_pulse"        # Smooth breathing (0.5-2 Hz)
    TRIANGLE_PULSE = "triangle"      # Linear up/down
    SQUARE_PULSE = "square"          # Binary on/off
    BEAT_SYNC = "beat_sync"          # Rhythmic pattern lookup
    KICK_FOLLOWER = "kick_follower"  # Flash on kick + decay
    RAMP_UP = "ramp_up"              # Linear increase (build-ups)
    RAMP_DOWN = "ramp_down"          # Linear decrease (breakdowns)
    EXPONENTIAL_DECAY = "exp_decay"  # Smooth fade
    RANDOM_FLICKER = "flicker"       # Chaotic (10-60 Hz)
    GAUSSIAN_NOISE = "gaussian"      # Organic variation


@dataclass
class DimmerParams:
    """Parameters for dimmer effects."""
    effect_type: DimmerType = DimmerType.NONE

    # Base intensity (0-1)
    base_intensity: float = 1.0

    # Minimum intensity (floor)
    min_intensity: float = 0.0

    # Speed (Hz for oscillating effects)
    speed: float = 1.0

    # Phase spread for chase effects (0-1)
    phase_spread: float = 1.0

    # Beat-sync pattern (list of intensity values)
    beat_pattern: List[float] = None

    # Kick follower parameters
    attack_time: float = 0.01       # Seconds to reach peak
    decay_time: float = 0.2         # Decay time constant (tau)
    kick_intensity: float = 1.0     # Peak on kick

    # Ramp parameters
    ramp_duration: float = 4.0      # Seconds for full ramp

    # Flicker parameters
    flicker_min: float = 0.3
    flicker_rate: float = 30.0      # Hz

    # Noise parameters
    noise_amount: float = 0.2       # Standard deviation

    def __post_init__(self):
        if self.beat_pattern is None:
            self.beat_pattern = [1.0, 0.5, 1.0, 0.5]  # Default 4-beat pattern


class DimmerEngine:
    """
    Generates intensity values for fixtures based on dimmer effects.
    """

    def __init__(self):
        self.params = DimmerParams()
        self.time = 0.0
        self._delta_time = 1.0 / 60.0  # BUG-031 fix: store for frame-rate-independent flicker

        # Per-fixture state
        self._fixture_intensity: Dict[str, float] = {}

        # Kick follower state
        self._kick_triggered = False
        self._kick_time = 0.0

        # Ramp state
        self._ramp_start_time: Optional[float] = None
        self._ramp_start_value: float = 0.0

        # Beat state
        self._current_beat: int = 0
        self._last_beat_time: float = 0.0

    def set_effect(self, effect_type: DimmerType, **kwargs):
        """Set the current dimmer effect."""
        self.params.effect_type = effect_type

        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)

    def trigger_kick(self):
        """Trigger kick follower effect."""
        self._kick_triggered = True
        self._kick_time = self.time

    def trigger_beat(self, beat_number: int):
        """Trigger beat for beat-sync pattern."""
        self._current_beat = beat_number % len(self.params.beat_pattern)
        self._last_beat_time = self.time

    def start_ramp(self, direction: str = "up"):
        """Start a ramp effect."""
        self._ramp_start_time = self.time
        if direction == "up":
            self.params.effect_type = DimmerType.RAMP_UP
            self._ramp_start_value = self.params.min_intensity
        else:
            self.params.effect_type = DimmerType.RAMP_DOWN
            self._ramp_start_value = self.params.base_intensity

    def update(self, delta_time: float):
        """Update dimmer state."""
        self.time += delta_time
        self._delta_time = delta_time  # BUG-031 fix: store for frame-rate-independent flicker

    def get_intensity(
        self,
        fixture_id: str,
        index: int,
        phase_offset: float,
        energy: float = 1.0
    ) -> float:
        """
        Calculate intensity for a fixture.

        Args:
            fixture_id: Unique fixture identifier
            index: Fixture index in group
            phase_offset: Phase offset (0-1) for chase effects
            energy: Audio energy (0-1) for modulation

        Returns:
            Intensity value (0-1)
        """
        effect = self.params.effect_type
        base = self.params.base_intensity
        minimum = self.params.min_intensity
        t = self.time
        phase = phase_offset * self.params.phase_spread

        intensity = base

        if effect == DimmerType.NONE:
            intensity = base

        elif effect == DimmerType.SINE_PULSE:
            # Smooth breathing: 0.5 + 0.5 * sin(2*pi*f*t)
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * self.params.speed * t + phase * math.pi * 2)
            intensity = minimum + (base - minimum) * wave

        elif effect == DimmerType.TRIANGLE_PULSE:
            # Linear up/down: 1 - 2|2(ft mod 1) - 1|
            phase_t = (self.params.speed * t + phase) % 1.0
            wave = 1 - 2 * abs(2 * phase_t - 1)
            wave = (wave + 1) / 2  # Normalize to 0-1
            intensity = minimum + (base - minimum) * wave

        elif effect == DimmerType.SQUARE_PULSE:
            # Binary on/off
            phase_t = (self.params.speed * t + phase) % 1.0
            wave = 1.0 if phase_t < 0.5 else 0.0
            intensity = minimum + (base - minimum) * wave

        elif effect == DimmerType.BEAT_SYNC:
            # Pattern lookup based on beat
            pattern = self.params.beat_pattern
            beat_idx = self._current_beat % len(pattern)
            intensity = minimum + (base - minimum) * pattern[beat_idx]

        elif effect == DimmerType.KICK_FOLLOWER:
            # Flash on kick + exponential decay
            if self._kick_triggered:
                elapsed = t - self._kick_time
                if elapsed < self.params.attack_time:
                    # Attack phase
                    attack_progress = elapsed / self.params.attack_time
                    intensity = minimum + (self.params.kick_intensity - minimum) * attack_progress
                else:
                    # Decay phase: A * e^(-t/tau)
                    decay_elapsed = elapsed - self.params.attack_time
                    decay = math.exp(-decay_elapsed / self.params.decay_time)
                    intensity = minimum + (self.params.kick_intensity - minimum) * decay

        elif effect == DimmerType.RAMP_UP:
            # Linear increase
            if self._ramp_start_time is not None:
                elapsed = t - self._ramp_start_time
                progress = min(1.0, elapsed / self.params.ramp_duration)
                intensity = self._ramp_start_value + (base - self._ramp_start_value) * progress
            else:
                intensity = minimum

        elif effect == DimmerType.RAMP_DOWN:
            # Linear decrease
            if self._ramp_start_time is not None:
                elapsed = t - self._ramp_start_time
                progress = min(1.0, elapsed / self.params.ramp_duration)
                intensity = self._ramp_start_value - (self._ramp_start_value - minimum) * progress
            else:
                intensity = base

        elif effect == DimmerType.EXPONENTIAL_DECAY:
            # Smooth decay: e^(-t/tau)
            if self._ramp_start_time is not None:
                elapsed = t - self._ramp_start_time
                decay = math.exp(-elapsed / self.params.decay_time)
                intensity = minimum + (base - minimum) * decay
            else:
                intensity = base

        elif effect == DimmerType.RANDOM_FLICKER:
            # BUG-031 fix: use actual delta_time instead of hardcoded 0.016 (60fps assumption)
            if random.random() < self.params.flicker_rate * self._delta_time:
                intensity = random.uniform(self.params.flicker_min, base)
            else:
                intensity = self._fixture_intensity.get(fixture_id, base)

        elif effect == DimmerType.GAUSSIAN_NOISE:
            # Organic variation: 1 + N(0, sigma)
            noise = random.gauss(0, self.params.noise_amount)
            intensity = base + noise
            intensity = max(minimum, min(1.0, intensity))

        # Apply energy modulation — beams form from zero on audio activation
        intensity *= energy

        # Clamp and store
        intensity = max(0.0, min(1.0, intensity))
        self._fixture_intensity[fixture_id] = intensity

        return intensity


class ChasePattern:
    """
    Specialized chase pattern for dimmer effects.
    Creates traveling wave of intensity across fixtures.
    """

    def __init__(
        self,
        pattern: List[float] = None,
        speed: float = 1.0,
        direction: int = 1
    ):
        """
        Args:
            pattern: Intensity pattern (default: [1, 0.7, 0.4, 0.1])
            speed: Chase speed in Hz
            direction: 1 = forward, -1 = reverse
        """
        self.pattern = pattern or [1.0, 0.7, 0.4, 0.1, 0.0]
        self.speed = speed
        self.direction = direction
        self.time = 0.0

    def update(self, delta_time: float):
        self.time += delta_time

    def get_intensity(self, index: int, total_fixtures: int) -> float:
        """Get intensity for fixture at given index."""
        # Calculate which pattern position this fixture should show
        pattern_length = len(self.pattern)
        cycle_position = (self.time * self.speed) % 1.0

        if self.direction < 0:
            cycle_position = 1.0 - cycle_position

        # Map fixture index to pattern
        fixture_phase = index / total_fixtures
        pattern_pos = (cycle_position - fixture_phase) % 1.0
        pattern_index = int(pattern_pos * pattern_length) % pattern_length

        return self.pattern[pattern_index]


# Preset dimmer configurations
DIMMER_PRESETS = {
    "breathing": DimmerParams(
        effect_type=DimmerType.SINE_PULSE,
        speed=0.5,
        min_intensity=0.2,
        base_intensity=1.0
    ),
    "fast_pulse": DimmerParams(
        effect_type=DimmerType.SINE_PULSE,
        speed=2.0,
        min_intensity=0.3,
        base_intensity=1.0
    ),
    "strobe_slow": DimmerParams(
        effect_type=DimmerType.SQUARE_PULSE,
        speed=4.0,
        min_intensity=0.0,
        base_intensity=1.0
    ),
    "beat_kick": DimmerParams(
        effect_type=DimmerType.BEAT_SYNC,
        beat_pattern=[1.0, 0.3, 0.8, 0.3],
        base_intensity=1.0
    ),
    "beat_offbeat": DimmerParams(
        effect_type=DimmerType.BEAT_SYNC,
        beat_pattern=[0.3, 1.0, 0.3, 1.0],
        base_intensity=1.0
    ),
    "kick_flash": DimmerParams(
        effect_type=DimmerType.KICK_FOLLOWER,
        attack_time=0.01,
        decay_time=0.15,
        kick_intensity=1.0,
        min_intensity=0.1
    ),
    "kick_sustain": DimmerParams(
        effect_type=DimmerType.KICK_FOLLOWER,
        attack_time=0.02,
        decay_time=0.4,
        kick_intensity=1.0,
        min_intensity=0.2
    ),
    "build_up": DimmerParams(
        effect_type=DimmerType.RAMP_UP,
        ramp_duration=8.0,
        min_intensity=0.1,
        base_intensity=1.0
    ),
    "fade_out": DimmerParams(
        effect_type=DimmerType.RAMP_DOWN,
        ramp_duration=4.0,
        base_intensity=1.0,
        min_intensity=0.0
    ),
    "tension_flicker": DimmerParams(
        effect_type=DimmerType.RANDOM_FLICKER,
        flicker_min=0.2,
        flicker_rate=40.0,
        base_intensity=0.9
    ),
    "organic_ambient": DimmerParams(
        effect_type=DimmerType.GAUSSIAN_NOISE,
        noise_amount=0.15,
        base_intensity=0.7
    ),
    "triangle_chase": DimmerParams(
        effect_type=DimmerType.TRIANGLE_PULSE,
        speed=1.0,
        phase_spread=1.0,
        min_intensity=0.1
    )
}


# Beat pattern library
BEAT_PATTERNS = {
    "four_on_floor": [1.0, 0.5, 0.8, 0.5],
    "backbeat": [0.5, 1.0, 0.5, 1.0],
    "downbeat_only": [1.0, 0.2, 0.2, 0.2],
    "syncopated": [1.0, 0.3, 0.7, 0.3, 0.9, 0.3, 0.6, 0.3],
    "buildup_8": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    "drop_impact": [1.0, 1.0, 0.8, 0.6],
    "half_time": [1.0, 0.2, 0.8, 0.2, 0.6, 0.2, 1.0, 0.2],
    "triplet": [1.0, 0.6, 0.6],
    "alternating": [1.0, 0.0, 1.0, 0.0],
    "chase_4": [1.0, 0.0, 0.0, 0.0],
    "chase_8": [1.0, 0.7, 0.4, 0.1, 0.0, 0.0, 0.0, 0.0]
}


# ---------------------------------------------------------------------------
# Dynamics: contrast inside a section, not only between sections
# ---------------------------------------------------------------------------


def _finite(value, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def soft_knee(x: float, lo: float, hi: float) -> float:
    """Expander curve: at or below `lo` is black, at or above `hi` is full."""
    if not (hi > lo):
        return 1.0 if x >= hi else 0.0
    u = (x - lo) / (hi - lo)
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return u * u * (3.0 - 2.0 * u)


@dataclass(frozen=True)
class DynamicsFrame:
    """One frame of shaped intensity, plus the terms that produced it."""

    level: float        # 0-1 drive level for the renderer's dimmer policy
    contrast: float     # expander output before accent and fatigue scaling
    accent: float       # transient lift, already folded into `level`
    reference: float    # loudness this frame was judged against
    scale: float        # anti-fatigue scalar, already folded into `level`
    ratio: float        # energy / reference, before the knee


_NEUTRAL_RANGE: Tuple[float, float] = (0.55, 0.8)


class DynamicsShaper:
    """Turn a flat energy stream into an intensity envelope that has shape.

    `energy * one_scalar_per_section` gives every moment inside a section the
    same relative level, so a quiet bar in a loud chorus reads as only slightly
    less bright. This judges each frame against a rolling reference of how loud
    the passage has actually been, then expands that ratio through a soft knee
    whose corners come from the section's intensity range.

    The expander is driven by the instantaneous energy and never by a smoothed
    copy of it: digital silence has to emit exactly 0.0, and a decaying
    envelope never reaches zero.
    """

    # A new loud passage is accepted over a phrase; the memory of it fades over
    # a section, which is what makes a quiet bar inside a loud one go dark.
    REFERENCE_ATTACK_S = 1.2
    REFERENCE_RELEASE_S = 12.0
    # Under this the room is genuinely quiet. Without it any whisper normalises
    # to a full rig, which is a different statement from "silence is dark".
    REFERENCE_FLOOR = 0.06
    # Headroom above the reference, so a hit that is genuinely louder than the
    # passage still has somewhere to go instead of saturating with it.
    RATIO_MAX = 2.5

    KNEE_BLACK_GAIN = 0.35      # how far into black a section is allowed to go
    KNEE_WIDTH_MIN = 1.00
    KNEE_WIDTH_GAIN = 2.10

    ACCENT_DECAY_S = 0.16
    ACCENT_GAIN = 0.12
    ACCENT_KNEE = 0.70          # bass under this fraction of its own reference is not a hit

    MAX_DELTA_S = 0.25

    def __init__(self):
        self._reference = 0.0
        self._bass_reference = 0.0
        self._accent = 0.0
        self._last = DynamicsFrame(0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    def reset(self):
        self.__init__()

    @property
    def last(self) -> DynamicsFrame:
        return self._last

    @staticmethod
    def _follow(current: float, target: float, delta_time: float, attack_s: float, release_s: float) -> float:
        tau = attack_s if target > current else release_s
        if tau <= 0.0:
            return target
        alpha = 1.0 - math.exp(-delta_time / tau)
        return current + (target - current) * alpha

    @classmethod
    def knee_for_range(cls, intensity_range: Tuple[float, float]) -> Tuple[float, float]:
        """Where black ends and full begins, for a section's intensity range.

        A high ceiling means the section should reach full readily and rarely
        drop out; a low floor means it is allowed to breathe down to nothing.
        """
        try:
            raw_lo, raw_hi = intensity_range[0], intensity_range[1]
        except (TypeError, IndexError, KeyError):
            raw_lo, raw_hi = _NEUTRAL_RANGE
        lo_range = min(1.0, max(0.0, _finite(raw_lo, _NEUTRAL_RANGE[0])))
        hi_range = min(1.0, max(lo_range, _finite(raw_hi, _NEUTRAL_RANGE[1])))
        knee_lo = cls.KNEE_BLACK_GAIN * (1.0 - hi_range)
        knee_hi = knee_lo + cls.KNEE_WIDTH_MIN + cls.KNEE_WIDTH_GAIN * (1.0 - lo_range)
        return knee_lo, min(cls.RATIO_MAX, knee_hi)

    def update(
        self,
        energy: float,
        delta_time: float,
        intensity_range: Tuple[float, float] = _NEUTRAL_RANGE,
        bass: float = 0.0,
        is_beat: bool = False,
        scale: float = 1.0,
    ) -> DynamicsFrame:
        """Advance the envelope one frame and return the shaped level."""
        e = min(1.0, max(0.0, _finite(energy)))
        b = min(1.0, max(0.0, _finite(bass)))
        dt = min(self.MAX_DELTA_S, max(0.0, _finite(delta_time)))
        gain = min(1.0, max(0.0, _finite(scale, 1.0)))

        if dt > 0.0:
            self._reference = self._follow(
                self._reference, e, dt, self.REFERENCE_ATTACK_S, self.REFERENCE_RELEASE_S
            )
            self._bass_reference = self._follow(
                self._bass_reference, b, dt, self.REFERENCE_ATTACK_S, self.REFERENCE_RELEASE_S
            )
            self._accent *= math.exp(-dt / self.ACCENT_DECAY_S)

        reference = max(self.REFERENCE_FLOOR, self._reference)
        ratio = min(self.RATIO_MAX, e / reference) if reference > 0.0 else 0.0

        knee_lo, knee_hi = self.knee_for_range(intensity_range)
        contrast = soft_knee(ratio, knee_lo, knee_hi)

        if is_beat and self._bass_reference > 0.0:
            hit = soft_knee(b / max(self.REFERENCE_FLOOR, self._bass_reference), self.ACCENT_KNEE, 1.0)
            self._accent = max(self._accent, hit * self.ACCENT_GAIN)

        level = contrast * (1.0 + self._accent) * gain
        level = min(1.0, max(0.0, level))

        self._last = DynamicsFrame(
            level=level,
            contrast=contrast,
            accent=self._accent,
            reference=reference,
            scale=gain,
            ratio=ratio,
        )
        return self._last
