"""
Decision Engine
State machine + Markov chain for intelligent effect selection.

6 States: Intro → Build-Up → Peak → Sustain ↔ Breakdown → Outro

Based on research:
- Energy-weighted effect selection
- Cooldown timers prevent repetition
- Surprise factor for static looks
"""

from collections import deque
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
import random
import time
import math

from .movement_patterns import MovementType, StaticLook, MOVEMENT_PRESETS
from .dimmer_effects import DimmerType, DIMMER_PRESETS, BEAT_PATTERNS
from .strobe_controller import StrobeMode, STROBE_PRESETS


class LightingState(Enum):
    """Song structure states."""
    INTRO = "intro"
    BUILDUP = "buildup"
    PEAK = "peak"         # Drop / high energy
    SUSTAIN = "sustain"   # Maintaining energy
    BREAKDOWN = "breakdown"
    OUTRO = "outro"


@dataclass
class AudioState:
    """Current audio analysis state."""
    energy: float = 0.0          # 0-1 overall energy
    bass: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    spectral_flux: float = 0.0   # Rate of change
    is_beat: bool = False
    beat_number: int = 0
    bars_elapsed: int = 0
    bpm: float = 128.0

    # Derived states
    is_buildup: bool = False     # Detected build-up
    is_drop: bool = False        # Detected drop
    is_breakdown: bool = False   # Detected breakdown

    # History
    energy_trend: float = 0.0    # Positive = rising, negative = falling


@dataclass
class EffectSelection:
    """Selected effects for current state."""
    movement: MovementType = MovementType.NONE
    movement_preset: str = "none"
    static_look: StaticLook = StaticLook.ALL_CENTER

    dimmer: DimmerType = DimmerType.NONE
    dimmer_preset: str = "none"
    beat_pattern: List[float] = field(default_factory=list)

    strobe: StrobeMode = StrobeMode.OFF
    strobe_preset: str = "none"

    # Flags
    use_static_look: bool = False
    strobe_on_drop: bool = False


class CooldownTimer:
    """Prevents effect repetition."""

    def __init__(self):
        self.timers: Dict[str, float] = {}

    def set_cooldown(self, effect_name: str, duration_bars: int, bpm: float = 128):
        """Set cooldown for an effect."""
        duration_seconds = (duration_bars * 4 * 60) / bpm
        self.timers[effect_name] = time.time() + duration_seconds

    def is_available(self, effect_name: str) -> bool:
        """Check if effect is off cooldown."""
        if effect_name not in self.timers:
            return True
        return time.time() > self.timers[effect_name]

    def update(self):
        """Clean up expired timers."""
        current = time.time()
        self.timers = {k: v for k, v in self.timers.items() if v > current}


class MarkovChain:
    """
    Markov chain for effect transitions.
    Probabilities are energy-weighted.
    """

    def __init__(self):
        # Transition probabilities: from_state -> {to_state: probability}
        self.transitions = self._build_transition_matrix()

    def _build_transition_matrix(self) -> Dict[str, Dict[str, float]]:
        """Build state transition probabilities."""
        return {
            # Movement transitions - expanded with new professional patterns
            "movement": {
                MovementType.NONE.value: {
                    MovementType.HORIZONTAL_SWEEP.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.2,
                    MovementType.PAN_CHASE.value: 0.2,
                    MovementType.MIRROR_SWEEP.value: 0.15,
                    MovementType.NONE.value: 0.25,
                },
                MovementType.HORIZONTAL_SWEEP.value: {
                    MovementType.PAN_CHASE.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.2,
                    MovementType.MIRROR_SWEEP.value: 0.15,
                    MovementType.NONE.value: 0.15,
                    MovementType.HORIZONTAL_SWEEP.value: 0.3,
                },
                MovementType.PAN_CHASE.value: {
                    MovementType.TILT_CHASE.value: 0.2,
                    MovementType.ALTERNATING.value: 0.15,
                    MovementType.CENTER_OUT_WAVE.value: 0.15,
                    MovementType.CIRCLE_CHASE.value: 0.15,
                    MovementType.NONE.value: 0.15,
                    MovementType.PAN_CHASE.value: 0.2,
                },
                MovementType.TRUE_CIRCLE.value: {
                    MovementType.CIRCLE_CHASE.value: 0.2,
                    MovementType.BALLYHOO.value: 0.2,
                    MovementType.MIRROR_SWEEP.value: 0.15,
                    MovementType.HORIZONTAL_SWEEP.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.25,
                },
                MovementType.CIRCLE_CHASE.value: {
                    MovementType.TRUE_CIRCLE.value: 0.2,
                    MovementType.COUNTER_ROTATION.value: 0.2,
                    MovementType.PAN_CHASE.value: 0.2,
                    MovementType.NONE.value: 0.15,
                    MovementType.CIRCLE_CHASE.value: 0.25,
                },
                MovementType.MIRROR_SWEEP.value: {
                    MovementType.ALTERNATING.value: 0.2,
                    MovementType.CENTER_OUT_WAVE.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.2,
                    MovementType.NONE.value: 0.15,
                    MovementType.MIRROR_SWEEP.value: 0.25,
                },
                MovementType.CENTER_OUT_WAVE.value: {
                    MovementType.OUTSIDE_IN_WAVE.value: 0.25,
                    MovementType.MIRROR_SWEEP.value: 0.2,
                    MovementType.PAN_CHASE.value: 0.2,
                    MovementType.NONE.value: 0.1,
                    MovementType.CENTER_OUT_WAVE.value: 0.25,
                },
                MovementType.ALTERNATING.value: {
                    MovementType.MIRROR_SWEEP.value: 0.2,
                    MovementType.PAN_CHASE.value: 0.2,
                    MovementType.NONE.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.15,
                    MovementType.ALTERNATING.value: 0.25,
                },
                MovementType.BALLYHOO.value: {
                    MovementType.TRUE_CIRCLE.value: 0.25,
                    MovementType.CIRCLE_CHASE.value: 0.2,
                    MovementType.HORIZONTAL_SWEEP.value: 0.2,
                    MovementType.NONE.value: 0.1,
                    MovementType.BALLYHOO.value: 0.25,
                },
                MovementType.COUNTER_ROTATION.value: {
                    MovementType.CIRCLE_CHASE.value: 0.2,
                    MovementType.ALTERNATING.value: 0.2,
                    MovementType.MIRROR_SWEEP.value: 0.2,
                    MovementType.NONE.value: 0.15,
                    MovementType.COUNTER_ROTATION.value: 0.25,
                },
                MovementType.FIGURE_8.value: {
                    MovementType.FIGURE_8_MIRROR.value: 0.2,
                    MovementType.BALLYHOO.value: 0.2,
                    MovementType.TRUE_CIRCLE.value: 0.2,
                    MovementType.NONE.value: 0.15,
                    MovementType.FIGURE_8.value: 0.25,
                },
            },

            # Dimmer transitions
            "dimmer": {
                DimmerType.NONE.value: {
                    DimmerType.SINE_PULSE.value: 0.3,
                    DimmerType.BEAT_SYNC.value: 0.4,
                    DimmerType.NONE.value: 0.3,
                },
                DimmerType.SINE_PULSE.value: {
                    DimmerType.BEAT_SYNC.value: 0.4,
                    DimmerType.TRIANGLE_PULSE.value: 0.2,
                    DimmerType.SINE_PULSE.value: 0.4,
                },
                DimmerType.BEAT_SYNC.value: {
                    DimmerType.KICK_FOLLOWER.value: 0.3,
                    DimmerType.SINE_PULSE.value: 0.2,
                    DimmerType.BEAT_SYNC.value: 0.5,
                },
            },

            # Static look transitions
            "static": {
                StaticLook.ALL_CENTER.value: {
                    StaticLook.X_PATTERN.value: 0.35,
                    StaticLook.FAN_OUT.value: 0.25,
                    StaticLook.ALL_CENTER.value: 0.4,
                },
                StaticLook.X_PATTERN.value: {
                    StaticLook.ALL_CENTER.value: 0.4,
                    StaticLook.FAN_OUT.value: 0.3,
                    StaticLook.X_PATTERN.value: 0.3,
                },
                StaticLook.FAN_OUT.value: {
                    StaticLook.ALL_CENTER.value: 0.35,
                    StaticLook.X_PATTERN.value: 0.35,
                    StaticLook.FAN_OUT.value: 0.3,
                },
            }
        }

    def get_next(
        self,
        category: str,
        current: str,
        energy: float = 0.5
    ) -> str:
        """
        Get next state based on transition probabilities.

        Args:
            category: "movement", "dimmer", or "static"
            current: Current state value
            energy: Energy level (0-1) to weight selection

        Returns:
            Next state value
        """
        if category not in self.transitions:
            return current

        category_trans = self.transitions[category]
        if current not in category_trans:
            # BUG-026 fix: graceful fallback for states not in transition matrix
            # Pick a random available state instead of always defaulting to first
            available = list(category_trans.keys())
            current = random.choice(available)

        probs = category_trans[current].copy()

        # Weight probabilities by energy
        # High energy = prefer active effects, low energy = prefer calm
        if energy > 0.7:
            # Boost active states
            for state in probs:
                if state != "none" and state != current:
                    probs[state] *= 1.5
        elif energy < 0.3:
            # Boost calm states
            if "none" in probs:
                probs["none"] *= 1.5

        # Normalize
        total = sum(probs.values())
        probs = {k: v / total for k, v in probs.items()}

        # Random selection
        rand = random.random()
        cumulative = 0
        for state, prob in probs.items():
            cumulative += prob
            if rand < cumulative:
                return state

        return current


class DecisionEngine:
    """
    Makes intelligent decisions about lighting effects based on audio.
    """

    def __init__(self):
        self.state = LightingState.INTRO
        self.previous_state = LightingState.INTRO

        self.audio = AudioState()
        self.selection = EffectSelection()

        self.cooldowns = CooldownTimer()
        self.markov = MarkovChain()

        # Timing
        self.state_start_time = time.time()
        self.bars_in_state = 0
        self.time = 0.0

        # Surprise factor for static looks
        self.last_static_time = 0.0
        self.static_probability = 0.05  # 5% base chance

        # BUG-023 fix: use deque for O(1) append/eviction instead of O(n) list pop(0)
        self.energy_window = 32  # Frames
        self.energy_history: deque = deque(maxlen=self.energy_window)

        # Cooldown durations (in bars)
        self.cooldown_bars = {
            "static_look": 16,
            "chase_movement": 24,
            "strobe_burst": 64,
            "pattern_change": 8,
        }

    def update(self, audio: AudioState, delta_time: float):
        """
        Update decision engine with new audio state.

        Args:
            audio: Current audio analysis
            delta_time: Time since last update
        """
        self.audio = audio
        self.time += delta_time

        # Update energy history and trend (BUG-023 fix: deque handles eviction automatically)
        self.energy_history.append(audio.energy)

        if len(self.energy_history) >= 2:
            recent = sum(self.energy_history[-8:]) / 8
            older = sum(self.energy_history[:-8]) / max(1, len(self.energy_history) - 8)
            audio.energy_trend = recent - older

        # Detect song structure changes
        self._detect_structure_changes()

        # Update cooldowns
        self.cooldowns.update()

        # Make effect decisions
        self._decide_effects()

    def _detect_structure_changes(self):
        """Detect build-ups, drops, breakdowns from audio."""
        audio = self.audio

        # Build-up detection: rising energy + high spectral flux
        audio.is_buildup = (
            audio.energy_trend > 0.1 and
            audio.spectral_flux > 0.3 and
            audio.energy < 0.8
        )

        # Drop detection: sudden bass spike after build-up
        audio.is_drop = (
            audio.bass > 0.8 and
            audio.spectral_flux > 0.5 and
            self.state == LightingState.BUILDUP
        )

        # Breakdown detection: significant energy drop
        audio.is_breakdown = (
            audio.energy < 0.3 and
            audio.energy_trend < -0.1 and
            self.state in [LightingState.PEAK, LightingState.SUSTAIN]
        )

        # State transitions
        new_state = self.state

        if audio.is_drop:
            new_state = LightingState.PEAK
        elif audio.is_buildup:
            new_state = LightingState.BUILDUP
        elif audio.is_breakdown:
            new_state = LightingState.BREAKDOWN
        elif self.state == LightingState.PEAK and self.bars_in_state > 8:
            new_state = LightingState.SUSTAIN
        elif self.state == LightingState.BREAKDOWN and audio.energy > 0.5:
            new_state = LightingState.BUILDUP

        if new_state != self.state:
            self.previous_state = self.state
            self.state = new_state
            self.state_start_time = time.time()
            self.bars_in_state = 0

    def _decide_effects(self):
        """Decide which effects to use based on current state."""
        state = self.state
        audio = self.audio
        selection = self.selection

        # Reset flags
        selection.use_static_look = False
        selection.strobe_on_drop = False

        if state == LightingState.INTRO:
            self._decide_intro()
        elif state == LightingState.BUILDUP:
            self._decide_buildup()
        elif state == LightingState.PEAK:
            self._decide_peak()
        elif state == LightingState.SUSTAIN:
            self._decide_sustain()
        elif state == LightingState.BREAKDOWN:
            self._decide_breakdown()
        elif state == LightingState.OUTRO:
            self._decide_outro()

        # Surprise static look check
        self._check_surprise_static()

    def _decide_intro(self):
        """Effects for intro section."""
        self.selection.movement = MovementType.NONE
        self.selection.static_look = StaticLook.ALL_CENTER
        self.selection.dimmer = DimmerType.SINE_PULSE
        self.selection.dimmer_preset = "breathing"
        self.selection.strobe = StrobeMode.OFF

    def _decide_buildup(self):
        """Effects for build-up section."""
        s = self.selection
        audio = self.audio

        # Movement: slow to fast, simple to complex
        progress = min(1.0, self.bars_in_state / 8)
        if progress < 0.3:
            # Slow sweep building tension
            s.movement = MovementType.HORIZONTAL_SWEEP
            s.movement_preset = "slow_sweep"
        elif progress < 0.6:
            # Add circular motion
            s.movement = MovementType.TRUE_CIRCLE
            s.movement_preset = "circle_slow"
        else:
            # Chase wave building to climax
            s.movement = MovementType.CENTER_OUT_WAVE
            s.movement_preset = "center_out"

        # Dimmer: ramp up
        s.dimmer = DimmerType.RAMP_UP
        s.dimmer_preset = "build_up"

        # No strobe during build-up (save for drop)
        s.strobe = StrobeMode.OFF

    def _decide_peak(self):
        """Effects for peak/drop section."""
        s = self.selection
        audio = self.audio

        # STROBE ON DROP!
        if self.bars_in_state == 0:
            s.strobe_on_drop = True
            s.strobe = StrobeMode.BURST
            s.strobe_preset = "drop_burst"

            # Static look during strobe
            s.use_static_look = True
            s.static_look = self._pick_static_look()

            # Set cooldown
            self.cooldowns.set_cooldown("strobe_burst", 64, audio.bpm)
            self.cooldowns.set_cooldown("static_look", 16, audio.bpm)

        # Movement: high energy patterns - fast chase, alternating, mirror
        if self.cooldowns.is_available("pattern_change"):
            # Prefer dramatic patterns during peak
            high_energy_patterns = [
                MovementType.BALLYHOO,
                MovementType.CIRCLE_CHASE,
                MovementType.MIRROR_SWEEP,
                MovementType.COUNTER_ROTATION,
                MovementType.ALTERNATING,
            ]
            # 60% chance to pick from high-energy list, 40% use Markov
            if random.random() < 0.6:
                s.movement = random.choice(high_energy_patterns)
                # Map to preset
                preset_map = {
                    MovementType.BALLYHOO: "ballyhoo_classic",
                    MovementType.CIRCLE_CHASE: "circle_chase",
                    MovementType.MIRROR_SWEEP: "mirror_sweep",
                    MovementType.COUNTER_ROTATION: "vortex",
                    MovementType.ALTERNATING: "alternating_sweep",
                }
                s.movement_preset = preset_map.get(s.movement, "")
            else:
                next_move = self.markov.get_next(
                    "movement",
                    s.movement.value,
                    audio.energy
                )
                s.movement = MovementType(next_move)
            self.cooldowns.set_cooldown("pattern_change", 8, audio.bpm)

        # Dimmer: beat-sync kick pattern
        s.dimmer = DimmerType.BEAT_SYNC
        s.beat_pattern = BEAT_PATTERNS["four_on_floor"]
        s.dimmer_preset = "beat_kick"

    def _decide_sustain(self):
        """Effects for sustain section (after drop)."""
        s = self.selection
        audio = self.audio

        # Movement: varied patterns using Markov chain
        if self.cooldowns.is_available("pattern_change"):
            # Sustain prefers flowing, continuous patterns
            sustain_patterns = [
                MovementType.TRUE_CIRCLE,
                MovementType.CIRCLE_CHASE,
                MovementType.PAN_CHASE,
                MovementType.TILT_CHASE,
                MovementType.HORIZONTAL_SWEEP,
                MovementType.MIRROR_SWEEP,
            ]

            if random.random() < 0.4:
                s.movement = random.choice(sustain_patterns)
                preset_map = {
                    MovementType.TRUE_CIRCLE: "circle_fast",
                    MovementType.CIRCLE_CHASE: "circle_chase",
                    MovementType.PAN_CHASE: "chase_left_right",
                    MovementType.TILT_CHASE: "tilt_wave",
                    MovementType.HORIZONTAL_SWEEP: "fast_sweep",
                    MovementType.MIRROR_SWEEP: "mirror_sweep",
                }
                s.movement_preset = preset_map.get(s.movement, "")
            else:
                next_move = self.markov.get_next(
                    "movement",
                    s.movement.value,
                    audio.energy
                )
                s.movement = MovementType(next_move)
            self.cooldowns.set_cooldown("pattern_change", 8, audio.bpm)

        # Dimmer: beat-sync
        s.dimmer = DimmerType.BEAT_SYNC
        if audio.energy > 0.7:
            s.beat_pattern = BEAT_PATTERNS["four_on_floor"]
        else:
            s.beat_pattern = BEAT_PATTERNS["half_time"]

        # Occasional strobe on strong beats
        if audio.is_beat and audio.bass > 0.9:
            if self.cooldowns.is_available("strobe_burst"):
                s.strobe = StrobeMode.BEAT_LOCKED
            else:
                s.strobe = StrobeMode.OFF
        else:
            s.strobe = StrobeMode.OFF

    def _decide_breakdown(self):
        """Effects for breakdown section."""
        s = self.selection
        audio = self.audio

        # Breakdown: calm, slow, dramatic looks
        if random.random() < 0.5:
            # Static look - dramatic positioning
            s.use_static_look = True
            s.static_look = self._pick_static_look()
            s.movement = MovementType.NONE
        else:
            # Slow, flowing movement
            breakdown_patterns = [
                (MovementType.VERTICAL_SWEEP, "gentle_tilt"),
                (MovementType.TRUE_CIRCLE, "circle_slow"),
                (MovementType.SPIRAL, "spiral_expand"),
            ]
            pattern, preset = random.choice(breakdown_patterns)
            s.movement = pattern
            s.movement_preset = preset

        # Dimmer: slow pulse
        s.dimmer = DimmerType.SINE_PULSE
        s.dimmer_preset = "breathing"

        # No strobe
        s.strobe = StrobeMode.OFF

    def _decide_outro(self):
        """Effects for outro section."""
        s = self.selection

        s.movement = MovementType.NONE
        s.static_look = StaticLook.ALL_CENTER
        s.dimmer = DimmerType.RAMP_DOWN
        s.dimmer_preset = "fade_out"
        s.strobe = StrobeMode.OFF

    def _check_surprise_static(self):
        """Check if we should surprise with a static look."""
        # Don't interrupt certain states
        if self.state in [LightingState.INTRO, LightingState.BREAKDOWN, LightingState.OUTRO]:
            return

        # Don't do if already static
        if self.selection.use_static_look:
            return

        # Check cooldown
        if not self.cooldowns.is_available("static_look"):
            return

        # Probability increases with time since last static
        time_since_static = self.time - self.last_static_time
        probability = self.static_probability * (1 + time_since_static / 60)

        if random.random() < probability:
            self.selection.use_static_look = True
            self.selection.static_look = self._pick_static_look()
            self.selection.movement = MovementType.NONE
            self.last_static_time = self.time
            self.cooldowns.set_cooldown("static_look", 16, self.audio.bpm)

    def _pick_static_look(self) -> StaticLook:
        """Pick a static look using Markov chain."""
        current = self.selection.static_look.value
        next_look = self.markov.get_next("static", current, self.audio.energy)
        return StaticLook(next_look)

    def get_selection(self) -> EffectSelection:
        """Get current effect selection."""
        return self.selection

    def force_state(self, state: LightingState):
        """Force a specific lighting state."""
        self.previous_state = self.state
        self.state = state
        self.state_start_time = time.time()
        self.bars_in_state = 0
        self._decide_effects()

    def force_static_look(self, look: StaticLook):
        """Force a specific static look."""
        self.selection.use_static_look = True
        self.selection.static_look = look
        self.selection.movement = MovementType.NONE
        self.last_static_time = self.time

    def trigger_drop(self):
        """Manually trigger a drop moment."""
        self.force_state(LightingState.PEAK)
        self.bars_in_state = 0
