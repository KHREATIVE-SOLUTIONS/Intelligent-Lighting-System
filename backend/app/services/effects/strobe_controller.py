"""
Strobe Controller (Layer 4)
Safe strobe patterns with OSHA-compliant frequency limits.

Safety Guidelines:
- 4Hz continuous = medical safety standard
- 5-30Hz = highest seizure risk (avoid extended use)
- Mitigation: Randomization, staggering, burst limits
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
import time
import random
import math


class StrobeMode(Enum):
    """Strobe effect modes."""
    OFF = "off"
    CONTINUOUS = "continuous"      # Steady strobe at set frequency
    BURST = "burst"                # Short burst then stop
    BEAT_LOCKED = "beat_locked"    # Flash on beat
    CHASE_STROBE = "chase_strobe"  # Traveling strobe wave
    RANDOM = "random"              # Chaotic strobe
    BLINDER = "blinder"            # Full white flash


@dataclass
class StrobeParams:
    """Strobe effect parameters."""
    mode: StrobeMode = StrobeMode.OFF

    # Frequency (Hz) - SAFETY: Max 4Hz for extended, up to 15Hz for bursts
    frequency: float = 4.0

    # Duty cycle (0-1) - how long light is ON per cycle
    duty_cycle: float = 0.5

    # Burst parameters
    burst_duration: float = 2.0    # Seconds
    burst_frequency: float = 12.0  # Hz during burst (higher allowed for short duration)

    # Safety limits
    max_continuous_hz: float = 4.0
    max_burst_hz: float = 15.0
    max_burst_duration: float = 4.0  # Max seconds at high frequency

    # Chase parameters
    chase_speed: float = 1.0       # Fixtures per second

    # Intensity
    strobe_intensity: float = 1.0


class StrobeController:
    """
    Safe strobe controller with automatic frequency limiting.
    """

    def __init__(self):
        self.params = StrobeParams()
        self.time = 0.0
        self._delta_time = 1.0 / 60.0  # BUG-030 fix: store for frame-rate-independent probability

        # State tracking
        self._strobe_state: Dict[str, bool] = {}  # Current on/off per fixture
        self._burst_start: Optional[float] = None
        self._beat_flash_time: float = 0.0
        self._last_beat: int = -1

        # Safety tracking
        self._high_freq_start: Optional[float] = None
        self._safety_cooldown: float = 0.0

    def set_mode(self, mode: StrobeMode, **kwargs):
        """Set strobe mode with safety checks."""
        self.params.mode = mode

        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)

        # Apply safety limits
        self._apply_safety_limits()

        # Reset burst state
        if mode == StrobeMode.BURST:
            self._burst_start = self.time

    def _apply_safety_limits(self):
        """Enforce safety frequency limits."""
        if self.params.mode == StrobeMode.CONTINUOUS:
            # Continuous strobe limited to 4Hz
            if not (self.params.frequency >= 0):  # negative or NaN
                self.params.frequency = 0.0
            if self.params.frequency > self.params.max_continuous_hz:
                self.params.frequency = self.params.max_continuous_hz

        elif self.params.mode == StrobeMode.BURST:
            # Burst strobe limited to 15Hz and 4 seconds
            if self.params.burst_frequency > self.params.max_burst_hz:
                self.params.burst_frequency = self.params.max_burst_hz
            if self.params.burst_duration > self.params.max_burst_duration:
                self.params.burst_duration = self.params.max_burst_duration

    def trigger_beat(self, beat_number: int):
        """Trigger beat for beat-locked strobe."""
        if beat_number != self._last_beat:
            self._last_beat = beat_number
            self._beat_flash_time = self.time

    def trigger_burst(self, duration: float = None, frequency: float = None):
        """Trigger a strobe burst (e.g., on drop)."""
        self.params.mode = StrobeMode.BURST
        if duration:
            self.params.burst_duration = min(duration, self.params.max_burst_duration)
        if frequency:
            self.params.burst_frequency = min(frequency, self.params.max_burst_hz)
        self._burst_start = self.time
        self._apply_safety_limits()

    def stop(self):
        """Stop all strobing."""
        self.params.mode = StrobeMode.OFF

    def update(self, delta_time: float):
        """Update strobe state."""
        self.time += delta_time
        self._delta_time = delta_time  # BUG-030 fix: store for frame-rate-independent probability

        # Check burst expiration
        if self.params.mode == StrobeMode.BURST:
            if self._burst_start is not None:
                elapsed = self.time - self._burst_start
                if elapsed > self.params.burst_duration:
                    self.params.mode = StrobeMode.OFF
                    self._burst_start = None
                    # Start cooldown after high-frequency burst
                    self._safety_cooldown = 2.0

        # Decrement safety cooldown
        if self._safety_cooldown > 0:
            self._safety_cooldown -= delta_time

    def get_strobe_value(
        self,
        fixture_id: str,
        index: int,
        total_fixtures: int,
        phase_offset: float = 0.0
    ) -> float:
        """
        Get strobe intensity for a fixture.

        Returns:
            0.0 = off, 1.0 = full strobe flash
        """
        mode = self.params.mode

        # Safety cooldown check
        if self._safety_cooldown > 0 and mode != StrobeMode.OFF:
            # During cooldown, only allow slow strobe
            if mode == StrobeMode.BURST:
                return 0.0

        if mode == StrobeMode.OFF:
            return 0.0

        elif mode == StrobeMode.CONTINUOUS:
            return self._continuous_strobe(phase_offset)

        elif mode == StrobeMode.BURST:
            return self._burst_strobe(phase_offset)

        elif mode == StrobeMode.BEAT_LOCKED:
            return self._beat_strobe()

        elif mode == StrobeMode.CHASE_STROBE:
            return self._chase_strobe(index, total_fixtures)

        elif mode == StrobeMode.RANDOM:
            return self._random_strobe(fixture_id)

        elif mode == StrobeMode.BLINDER:
            return self.params.strobe_intensity

        return 0.0

    def _continuous_strobe(self, phase_offset: float) -> float:
        """Continuous strobe at set frequency."""
        freq = self.params.frequency
        duty = self.params.duty_cycle

        phase = (self.time * freq + phase_offset) % 1.0
        if phase < duty:
            return self.params.strobe_intensity
        return 0.0

    def _burst_strobe(self, phase_offset: float) -> float:
        """Burst strobe with automatic end."""
        if self._burst_start is None:
            return 0.0

        freq = self.params.burst_frequency
        duty = self.params.duty_cycle

        phase = (self.time * freq + phase_offset) % 1.0
        if phase < duty:
            return self.params.strobe_intensity
        return 0.0

    def _beat_strobe(self) -> float:
        """Flash on beat."""
        # Flash duration based on frequency setting
        flash_duration = 1.0 / max(1, self.params.frequency)

        elapsed = self.time - self._beat_flash_time
        if elapsed < flash_duration:
            # Fade out over flash duration
            fade = 1.0 - (elapsed / flash_duration)
            return self.params.strobe_intensity * fade
        return 0.0

    def _chase_strobe(self, index: int, total_fixtures: int) -> float:
        """Traveling strobe wave."""
        # Which fixture should be lit
        chase_pos = (self.time * self.params.chase_speed) % total_fixtures
        distance = abs(index - chase_pos)
        distance = min(distance, total_fixtures - distance)  # Wrap around

        # Flash if close to chase position
        if distance < 1.0:
            return self.params.strobe_intensity * (1.0 - distance)
        return 0.0

    def _random_strobe(self, fixture_id: str) -> float:
        """Random chaotic strobe."""
        # BUG-030 fix: use actual delta_time instead of hardcoded 0.016 (60fps assumption)
        probability = self.params.frequency * self._delta_time
        if random.random() < probability:
            return self.params.strobe_intensity
        return 0.0

    def is_active(self) -> bool:
        """Check if strobe is currently active."""
        return self.params.mode != StrobeMode.OFF


# Preset strobe configurations
STROBE_PRESETS = {
    "slow_safe": StrobeParams(
        mode=StrobeMode.CONTINUOUS,
        frequency=2.0,
        duty_cycle=0.3
    ),
    "medium_safe": StrobeParams(
        mode=StrobeMode.CONTINUOUS,
        frequency=4.0,
        duty_cycle=0.4
    ),
    "drop_burst": StrobeParams(
        mode=StrobeMode.BURST,
        burst_frequency=12.0,
        burst_duration=2.0,
        duty_cycle=0.5
    ),
    "impact_burst": StrobeParams(
        mode=StrobeMode.BURST,
        burst_frequency=15.0,
        burst_duration=1.0,
        duty_cycle=0.4
    ),
    "beat_flash": StrobeParams(
        mode=StrobeMode.BEAT_LOCKED,
        frequency=8.0,  # Flash decay rate
        strobe_intensity=1.0
    ),
    "chase_fast": StrobeParams(
        mode=StrobeMode.CHASE_STROBE,
        chase_speed=4.0,
        strobe_intensity=1.0
    ),
    "chase_slow": StrobeParams(
        mode=StrobeMode.CHASE_STROBE,
        chase_speed=1.0,
        strobe_intensity=1.0
    ),
    "chaos": StrobeParams(
        mode=StrobeMode.RANDOM,
        frequency=10.0,
        strobe_intensity=0.9
    ),
    "blinder": StrobeParams(
        mode=StrobeMode.BLINDER,
        strobe_intensity=1.0
    )
}


class DropStrobeSequence:
    """
    Specialized sequence for drop moments.

    Sequence:
    1. Build-up: Slow strobe increasing in frequency
    2. Impact: Fast burst strobe
    3. Decay: Transition to beat-locked
    """

    def __init__(self, strobe_controller: StrobeController):
        self.controller = strobe_controller
        self.phase = "idle"
        self.start_time = 0.0
        self.bpm = 128.0

    def trigger_buildup(self, duration: float = 4.0):
        """Start build-up phase before drop."""
        self.phase = "buildup"
        self.start_time = self.controller.time
        # A zero length divided by zero every frame from then on, and a negative
        # one never ended and drove the strobe rate negative.
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = 4.0
        self.buildup_duration = duration if math.isfinite(duration) and duration >= 0.5 else 0.5
        self.controller.set_mode(
            StrobeMode.CONTINUOUS,
            frequency=1.0
        )

    def trigger_drop(self):
        """Trigger drop impact."""
        self.phase = "impact"
        self.start_time = self.controller.time
        self.controller.trigger_burst(
            duration=2.0,
            frequency=15.0
        )

    def update(self):
        """Update sequence state."""
        elapsed = self.controller.time - self.start_time

        if self.phase == "buildup":
            # Increase frequency during buildup
            progress = elapsed / self.buildup_duration
            if progress < 1.0:
                freq = 1.0 + progress * 3.0  # 1Hz to 4Hz
                self.controller.params.frequency = freq
            else:
                # Auto-trigger drop at end of buildup
                self.trigger_drop()

        elif self.phase == "impact":
            # Check if burst ended
            if self.controller.params.mode == StrobeMode.OFF:
                self.phase = "sustain"
                self.start_time = self.controller.time
                self.controller.set_mode(StrobeMode.BEAT_LOCKED)

        elif self.phase == "sustain":
            # Sustain beat-locked strobe for a while
            if elapsed > 8.0:  # 8 seconds
                self.phase = "idle"
                self.controller.stop()

    def is_active(self) -> bool:
        return self.phase != "idle"
