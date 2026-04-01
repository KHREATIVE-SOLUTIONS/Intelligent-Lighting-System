"""
Dimmer Effects Engine
Controls intensity/brightness for fixtures (Layer 3)

10 Dimmer Effect Types
"""

from enum import Enum
from typing import Dict, List, Optional, Callable
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
