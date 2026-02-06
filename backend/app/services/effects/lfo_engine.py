"""
LFO-Based Effects Engine - grandMA2/MA3 Style

Implements professional lighting effects using Low Frequency Oscillators (LFOs)
with waveforms, phase distribution, and grouping modes matching grandMA2/MA3.

Based on MA Lighting Effects Engine technical documentation.
"""

import hashlib
import math
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any


class WaveformType(Enum):
    """Available waveform types."""
    SINE = "sine"
    COSINE = "cosine"
    TRIANGLE = "triangle"
    SQUARE = "square"
    RAMP_UP = "ramp_up"      # Sawtooth up
    RAMP_DOWN = "ramp_down"  # Sawtooth down
    PWM = "pwm"              # Pulse width modulation
    RANDOM = "random"


class PhaseDistribution(Enum):
    """Phase distribution modes across fixtures."""
    LINEAR = "linear"       # Even spread 0-360°
    GROUPS = "groups"       # Divide into N groups
    BLOCKS = "blocks"       # Sequential blocks
    WINGS = "wings"         # Symmetric from edges inward
    SHUFFLE = "shuffle"     # Random order


class EffectDirection(Enum):
    """Effect playback direction."""
    FORWARD = "forward"
    BACKWARD = "backward"
    BOUNCE = "bounce"


class EffectAttribute(Enum):
    """Attributes that can be affected."""
    DIMMER = "dimmer"
    PAN = "pan"
    TILT = "tilt"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    WHITE = "white"
    ZOOM = "zoom"
    FOCUS = "focus"
    SHUTTER = "shutter"


@dataclass
class LFOConfig:
    """Configuration for a single LFO effect."""
    # Waveform
    waveform: WaveformType = WaveformType.SINE

    # Value range
    low_value: float = 0.0      # Minimum output (0-1 normalized)
    high_value: float = 1.0     # Maximum output (0-1 normalized)

    # Timing
    speed_bpm: float = 120.0    # Base speed in BPM
    rate_multiplier: float = 1.0  # Speed multiplier (0.125 to 8.0)

    # Phase distribution
    phase_start: float = 0.0    # Starting phase in degrees
    phase_end: float = 360.0    # Ending phase in degrees
    distribution: PhaseDistribution = PhaseDistribution.LINEAR
    distribution_param: int = 1  # Groups count, block size, etc.

    # Direction
    direction: EffectDirection = EffectDirection.FORWARD

    # PWM specific
    pwm_width: float = 50.0     # Duty cycle percentage for PWM

    # Fade envelope
    attack_ms: float = 0.0      # Fade in time
    decay_ms: float = 0.0       # Fade out time

    # Target attribute
    attribute: EffectAttribute = EffectAttribute.DIMMER


@dataclass
class EffectPreset:
    """A complete effect with multiple LFOs for different attributes."""
    name: str
    lfo_configs: List[LFOConfig] = field(default_factory=list)
    description: str = ""


class Waveforms:
    """Static waveform generator functions."""

    @staticmethod
    def sine(progress: float, low: float, high: float) -> float:
        """Sine wave: smooth oscillation."""
        center = (low + high) / 2
        amplitude = (high - low) / 2
        return center + amplitude * math.sin(2 * math.pi * progress)

    @staticmethod
    def cosine(progress: float, low: float, high: float) -> float:
        """Cosine wave: sine shifted 90°."""
        center = (low + high) / 2
        amplitude = (high - low) / 2
        return center + amplitude * math.cos(2 * math.pi * progress)

    @staticmethod
    def triangle(progress: float, low: float, high: float) -> float:
        """Triangle wave: linear ramp up then down."""
        if progress < 0.5:
            return low + (high - low) * (2 * progress)
        else:
            return high - (high - low) * (2 * (progress - 0.5))

    @staticmethod
    def square(progress: float, low: float, high: float) -> float:
        """Square wave: on/off."""
        return high if progress < 0.5 else low

    @staticmethod
    def ramp_up(progress: float, low: float, high: float) -> float:
        """Ramp up (sawtooth): linear increase then snap back."""
        return low + (high - low) * progress

    @staticmethod
    def ramp_down(progress: float, low: float, high: float) -> float:
        """Ramp down: linear decrease then snap back."""
        return high - (high - low) * progress

    @staticmethod
    def pwm(progress: float, low: float, high: float, duty_cycle: float = 50.0) -> float:
        """Pulse width modulation: variable on/off ratio."""
        return high if progress < (duty_cycle / 100) else low

    @staticmethod
    def random(progress: float, low: float, high: float, seed: int = 0) -> float:
        """Pseudo-random value, deterministic per beat."""
        # BUG-025 fix: hashlib moved to module-level import
        h = hashlib.md5(f"{seed}:{int(progress * 1000)}".encode()).hexdigest()
        rand_val = int(h[:8], 16) / 0xFFFFFFFF
        return low + (high - low) * rand_val

    @classmethod
    def get_waveform(cls, waveform_type: WaveformType) -> Callable:
        """Get waveform function by type."""
        mapping = {
            WaveformType.SINE: cls.sine,
            WaveformType.COSINE: cls.cosine,
            WaveformType.TRIANGLE: cls.triangle,
            WaveformType.SQUARE: cls.square,
            WaveformType.RAMP_UP: cls.ramp_up,
            WaveformType.RAMP_DOWN: cls.ramp_down,
            WaveformType.PWM: cls.pwm,
            WaveformType.RANDOM: cls.random,
        }
        return mapping.get(waveform_type, cls.sine)


class PhaseDistributor:
    """Calculates phase offsets for fixtures based on distribution mode."""

    @staticmethod
    def get_wings_order(total: int) -> List[int]:
        """Get fixture indices reordered for wings distribution."""
        reordered = []
        left, right = 0, total - 1
        while left <= right:
            reordered.append(left)
            if left != right:
                reordered.append(right)
            left += 1
            right -= 1
        return reordered

    @staticmethod
    def get_wings_order_index(original_index: int, total: int) -> int:
        """Get the position of a fixture in wings order.

        BUG-024 fix: O(1) direct computation instead of O(n) list build + O(n) search.
        Wings order interleaves from edges: [0, n-1, 1, n-2, 2, n-3, ...]
        """
        if total <= 1:
            return 0
        half = (total - 1) / 2.0
        if original_index <= half:
            return original_index * 2
        else:
            return (total - 1 - original_index) * 2 + 1

    @classmethod
    def distribute(cls, fixture_index: int, total_fixtures: int,
                   phase_start: float, phase_end: float,
                   mode: PhaseDistribution, param: int = 1) -> float:
        """
        Calculate phase offset for a fixture.

        Args:
            fixture_index: Index of fixture in selection order
            total_fixtures: Total number of selected fixtures
            phase_start: Starting phase in degrees
            phase_end: Ending phase in degrees
            mode: Distribution mode
            param: Mode-specific parameter (group count, block size, etc.)

        Returns:
            Phase offset in degrees (0-360)
        """
        if total_fixtures <= 1:
            return phase_start

        if mode == PhaseDistribution.LINEAR:
            # Even spread across phase range
            phase_range = phase_end - phase_start
            return (phase_start + (phase_range / total_fixtures) * fixture_index) % 360

        elif mode == PhaseDistribution.GROUPS:
            # Divide into N groups, each group has same phase
            num_groups = max(1, param)
            group_size = total_fixtures / num_groups
            group_index = int(fixture_index / group_size)
            return ((360 / num_groups) * group_index) % 360

        elif mode == PhaseDistribution.BLOCKS:
            # Sequential blocks of fixtures
            block_size = max(1, param)
            block_index = int(fixture_index / block_size)
            total_blocks = math.ceil(total_fixtures / block_size)
            return ((360 / total_blocks) * block_index) % 360

        elif mode == PhaseDistribution.WINGS:
            # Symmetric from edges inward
            reordered_index = cls.get_wings_order_index(fixture_index, total_fixtures)
            return ((360 / total_fixtures) * reordered_index) % 360

        elif mode == PhaseDistribution.SHUFFLE:
            # BUG-025 fix: hashlib moved to module-level import
            h = hashlib.md5(f"shuffle:{fixture_index}".encode()).hexdigest()
            rand_val = int(h[:8], 16) / 0xFFFFFFFF
            return rand_val * 360

        return phase_start


class LFOEngine:
    """
    Main LFO-based effects engine.

    Manages multiple LFO effects and calculates output values per fixture per frame.
    """

    def __init__(self):
        self.effects: Dict[str, EffectPreset] = {}
        self.active_effects: List[str] = []
        self.start_time: float = time.time()
        self.master_bpm: float = 120.0
        self.master_speed: float = 1.0  # Speed master (0-2)

        # Fixture management
        self.fixture_count: int = 8
        self.fixture_order: List[int] = []  # Selection order

        # Output storage
        self._outputs: Dict[int, Dict[str, float]] = {}  # fixture_id -> attribute -> value

        # Initialize default effects library
        self._init_default_effects()

    def _init_default_effects(self):
        """Initialize library of common effects."""

        # Dimmer Pulse - all fixtures pulsing together
        self.effects["dimmer_pulse"] = EffectPreset(
            name="Dimmer Pulse",
            description="All fixtures pulse together on beat",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.DIMMER,
                    low_value=0.2,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=0,  # All same phase
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Dimmer Chase - wave across fixtures
        self.effects["dimmer_chase"] = EffectPreset(
            name="Dimmer Chase",
            description="Dimmer wave traveling across fixtures",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.DIMMER,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Dimmer Odd/Even - alternating groups
        self.effects["dimmer_odd_even"] = EffectPreset(
            name="Dimmer Odd/Even",
            description="Odd and even fixtures alternate",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.DIMMER,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.GROUPS,
                    distribution_param=2,  # 2 groups
                )
            ]
        )

        # Circle Movement - pan/tilt circle
        self.effects["circle"] = EffectPreset(
            name="Circle",
            description="Circular pan/tilt movement",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.PAN,
                    low_value=-0.15,  # -15% of range (about -25°)
                    high_value=0.15,   # +15% of range (about +25°)
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                ),
                LFOConfig(
                    waveform=WaveformType.COSINE,  # 90° offset from pan
                    attribute=EffectAttribute.TILT,
                    low_value=-0.1,
                    high_value=0.1,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Circle Wings - symmetric circle from edges
        self.effects["circle_wings"] = EffectPreset(
            name="Circle Wings",
            description="Symmetric circular movement from edges",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.PAN,
                    low_value=-0.2,
                    high_value=0.2,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.WINGS,
                ),
                LFOConfig(
                    waveform=WaveformType.COSINE,
                    attribute=EffectAttribute.TILT,
                    low_value=-0.12,
                    high_value=0.12,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.WINGS,
                )
            ]
        )

        # Figure 8 / Ballyhoo
        self.effects["ballyhoo"] = EffectPreset(
            name="Ballyhoo",
            description="Figure-8 movement pattern",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.PAN,
                    low_value=-0.2,
                    high_value=0.2,
                    phase_start=0,
                    phase_end=360,
                    rate_multiplier=1.0,
                    distribution=PhaseDistribution.LINEAR,
                ),
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.TILT,
                    low_value=-0.15,
                    high_value=0.15,
                    phase_start=180,  # 180° offset creates figure-8
                    phase_end=540,
                    rate_multiplier=2.0,  # Tilt at 2x speed
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Horizontal Sweep
        self.effects["pan_sweep"] = EffectPreset(
            name="Pan Sweep",
            description="Horizontal sweeping movement",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.TRIANGLE,
                    attribute=EffectAttribute.PAN,
                    low_value=-0.25,
                    high_value=0.25,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                    rate_multiplier=0.5,  # Slow sweep
                )
            ]
        )

        # Vertical Tilt
        self.effects["tilt_sweep"] = EffectPreset(
            name="Tilt Sweep",
            description="Vertical tilting movement",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.TRIANGLE,
                    attribute=EffectAttribute.TILT,
                    low_value=-0.2,
                    high_value=0.2,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                    rate_multiplier=0.5,
                )
            ]
        )

        # Color Chase - RGB cycling
        self.effects["color_chase"] = EffectPreset(
            name="Color Chase",
            description="RGB color chase across fixtures",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.RED,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=360,
                    distribution=PhaseDistribution.LINEAR,
                ),
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.GREEN,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=120,  # 120° offset
                    phase_end=480,
                    distribution=PhaseDistribution.LINEAR,
                ),
                LFOConfig(
                    waveform=WaveformType.SINE,
                    attribute=EffectAttribute.BLUE,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=240,  # 240° offset
                    phase_end=600,
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Strobe
        self.effects["strobe"] = EffectPreset(
            name="Strobe",
            description="Fast strobe effect",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.SQUARE,
                    attribute=EffectAttribute.DIMMER,
                    low_value=0.0,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=0,
                    rate_multiplier=4.0,  # 4x BPM
                    distribution=PhaseDistribution.LINEAR,
                )
            ]
        )

        # Random Flicker
        self.effects["flicker"] = EffectPreset(
            name="Flicker",
            description="Random flickering effect",
            lfo_configs=[
                LFOConfig(
                    waveform=WaveformType.RANDOM,
                    attribute=EffectAttribute.DIMMER,
                    low_value=0.3,
                    high_value=1.0,
                    phase_start=0,
                    phase_end=360,
                    rate_multiplier=2.0,
                    distribution=PhaseDistribution.SHUFFLE,
                )
            ]
        )

    def set_fixture_count(self, count: int):
        """Set number of fixtures."""
        self.fixture_count = count
        self.fixture_order = list(range(count))

    def set_fixture_order(self, order: List[int]):
        """Set custom fixture selection order."""
        self.fixture_order = order
        self.fixture_count = len(order)

    def set_master_bpm(self, bpm: float):
        """Set master BPM for all effects."""
        self.master_bpm = max(1, min(300, bpm))

    def set_master_speed(self, speed: float):
        """Set master speed multiplier (0-2)."""
        self.master_speed = max(0, min(2, speed))

    def activate_effect(self, effect_name: str):
        """Activate an effect."""
        if effect_name in self.effects and effect_name not in self.active_effects:
            self.active_effects.append(effect_name)

    def deactivate_effect(self, effect_name: str):
        """Deactivate an effect."""
        if effect_name in self.active_effects:
            self.active_effects.remove(effect_name)

    def deactivate_all(self):
        """Deactivate all effects."""
        self.active_effects.clear()

    def set_single_effect(self, effect_name: str):
        """Set a single active effect (deactivates others)."""
        self.active_effects.clear()
        if effect_name in self.effects:
            self.active_effects.append(effect_name)

    def create_custom_effect(self, name: str, lfo_configs: List[LFOConfig],
                            description: str = ""):
        """Create a custom effect."""
        self.effects[name] = EffectPreset(
            name=name,
            lfo_configs=lfo_configs,
            description=description
        )

    def calculate_lfo_output(self, lfo: LFOConfig, fixture_index: int,
                            current_time_ms: float) -> float:
        """
        Calculate LFO output for a single fixture.

        Args:
            lfo: LFO configuration
            fixture_index: Index in fixture order
            current_time_ms: Current time in milliseconds

        Returns:
            Output value (typically 0-1 for normalized, or actual degrees for pan/tilt)
        """
        # Calculate effective speed
        effective_bpm = lfo.speed_bpm * lfo.rate_multiplier * self.master_speed
        if effective_bpm <= 0:
            return (lfo.low_value + lfo.high_value) / 2

        # Calculate period and progress
        speed_hz = effective_bpm / 60
        period_ms = 1000 / speed_hz
        time_in_period = current_time_ms % period_ms
        progress = time_in_period / period_ms  # 0.0 to 1.0

        # Calculate phase offset for this fixture
        phase_offset_deg = PhaseDistributor.distribute(
            fixture_index,
            self.fixture_count,
            lfo.phase_start,
            lfo.phase_end,
            lfo.distribution,
            lfo.distribution_param
        )

        # Apply phase offset to progress
        phase_angle_deg = (progress * 360 + phase_offset_deg) % 360
        waveform_input = phase_angle_deg / 360  # Back to 0-1

        # Apply direction
        if lfo.direction == EffectDirection.BACKWARD:
            waveform_input = 1.0 - waveform_input
        elif lfo.direction == EffectDirection.BOUNCE:
            if waveform_input < 0.5:
                waveform_input = waveform_input * 2.0
            else:
                waveform_input = (1.0 - waveform_input) * 2.0

        # Get waveform output
        waveform_func = Waveforms.get_waveform(lfo.waveform)

        if lfo.waveform == WaveformType.PWM:
            output = Waveforms.pwm(waveform_input, lfo.low_value, lfo.high_value, lfo.pwm_width)
        elif lfo.waveform == WaveformType.RANDOM:
            # Use fixture index and beat number as seed for deterministic randomness
            beat_num = int(current_time_ms / period_ms)
            output = Waveforms.random(waveform_input, lfo.low_value, lfo.high_value,
                                     seed=fixture_index * 1000 + beat_num)
        else:
            output = waveform_func(waveform_input, lfo.low_value, lfo.high_value)

        # Apply fade envelope if configured
        if lfo.attack_ms > 0 or lfo.decay_ms > 0:
            fade = self._calculate_fade_envelope(
                time_in_period, period_ms, lfo.attack_ms, lfo.decay_ms
            )
            # Fade affects amplitude, not center
            center = (lfo.low_value + lfo.high_value) / 2
            output = center + (output - center) * fade

        return output

    def _calculate_fade_envelope(self, time_in_period: float, period_ms: float,
                                 attack_ms: float, decay_ms: float) -> float:
        """Calculate fade envelope multiplier."""
        if time_in_period < attack_ms:
            return time_in_period / attack_ms
        elif time_in_period > period_ms - decay_ms:
            return (period_ms - time_in_period) / decay_ms
        return 1.0

    def update(self, current_time: float = None) -> Dict[int, Dict[str, float]]:
        """
        Update all effects and return output values.

        Args:
            current_time: Current time in seconds (uses system time if None)

        Returns:
            Dict mapping fixture_index -> attribute_name -> value
        """
        if current_time is None:
            current_time = time.time()

        current_time_ms = (current_time - self.start_time) * 1000

        # Clear outputs
        self._outputs = {i: {} for i in range(self.fixture_count)}

        # Process each active effect
        for effect_name in self.active_effects:
            if effect_name not in self.effects:
                continue

            effect = self.effects[effect_name]

            # Process each LFO in the effect
            for lfo in effect.lfo_configs:
                attr_name = lfo.attribute.value

                # Calculate output for each fixture
                for fixture_idx in range(self.fixture_count):
                    output = self.calculate_lfo_output(lfo, fixture_idx, current_time_ms)

                    # Store output (LTP for most attributes)
                    if attr_name == "dimmer":
                        # HTP for dimmer - take highest value
                        current = self._outputs[fixture_idx].get(attr_name, 0)
                        self._outputs[fixture_idx][attr_name] = max(current, output)
                    else:
                        # LTP for other attributes
                        self._outputs[fixture_idx][attr_name] = output

        return self._outputs

    def get_fixture_output(self, fixture_index: int) -> Dict[str, float]:
        """Get current output values for a fixture."""
        return self._outputs.get(fixture_index, {})

    def get_effect_names(self) -> List[str]:
        """Get list of available effect names."""
        return list(self.effects.keys())

    def get_active_effects(self) -> List[str]:
        """Get list of active effect names."""
        return self.active_effects.copy()

    def get_effect_info(self, effect_name: str) -> Optional[Dict[str, Any]]:
        """Get information about an effect."""
        if effect_name not in self.effects:
            return None

        effect = self.effects[effect_name]
        return {
            "name": effect.name,
            "description": effect.description,
            "lfo_count": len(effect.lfo_configs),
            "attributes": [lfo.attribute.value for lfo in effect.lfo_configs],
            "waveforms": [lfo.waveform.value for lfo in effect.lfo_configs],
        }


# Convenience function to create common effects
def create_circle_effect(pan_amplitude: float = 0.15, tilt_amplitude: float = 0.1,
                         rate: float = 1.0, distribution: PhaseDistribution = PhaseDistribution.LINEAR,
                         phase_spread: float = 360.0) -> EffectPreset:
    """Create a circle movement effect."""
    return EffectPreset(
        name="Custom Circle",
        description=f"Circle with {pan_amplitude*100:.0f}% pan, {tilt_amplitude*100:.0f}% tilt",
        lfo_configs=[
            LFOConfig(
                waveform=WaveformType.SINE,
                attribute=EffectAttribute.PAN,
                low_value=-pan_amplitude,
                high_value=pan_amplitude,
                phase_start=0,
                phase_end=phase_spread,
                rate_multiplier=rate,
                distribution=distribution,
            ),
            LFOConfig(
                waveform=WaveformType.COSINE,
                attribute=EffectAttribute.TILT,
                low_value=-tilt_amplitude,
                high_value=tilt_amplitude,
                phase_start=0,
                phase_end=phase_spread,
                rate_multiplier=rate,
                distribution=distribution,
            )
        ]
    )


def create_dimmer_chase(low: float = 0.0, high: float = 1.0,
                        rate: float = 1.0,
                        distribution: PhaseDistribution = PhaseDistribution.LINEAR,
                        waveform: WaveformType = WaveformType.SINE) -> EffectPreset:
    """Create a dimmer chase effect."""
    return EffectPreset(
        name="Custom Dimmer Chase",
        description=f"Dimmer chase {low*100:.0f}%-{high*100:.0f}%",
        lfo_configs=[
            LFOConfig(
                waveform=waveform,
                attribute=EffectAttribute.DIMMER,
                low_value=low,
                high_value=high,
                phase_start=0,
                phase_end=360,
                rate_multiplier=rate,
                distribution=distribution,
            )
        ]
    )
