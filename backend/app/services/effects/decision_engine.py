"""
Decision Engine v2
Genre-aware, section-driven state machine with professional timing rules.

6 States: Intro → Build-Up → Peak → Sustain ↔ Breakdown → Outro

Features:
- Genre-specific transition weights (EDM/Rock/Pop/Hip-Hop/Jazz)
- Section-driven effect selection (not random timers)
- Bar/phrase boundary timing (changes only on 4/8/16 bar lines)
- Dynamic range enforcement with anti-fatigue
- Anticipation system for pre-loading next looks
- Key lighting integration
"""

from collections import deque
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
import copy
import random
import time
import math

from .movement_patterns import MovementType, StaticLook, MOVEMENT_PRESETS
from ..lighting.section_manager import (
    DEFAULT_SECTION_CONFIGS,
    SongSection,
    bars_until_boundary,
    is_downbeat,
    is_impact_event,
    next_musical_boundary_bar,
)
from .dimmer_effects import (
    DimmerType,
    DIMMER_PRESETS,
    BEAT_PATTERNS,
    DynamicsFrame,
    DynamicsShaper,
)
from .strobe_controller import StrobeMode, STROBE_PRESETS


# Genre-specific preferred effects for each section
GENRE_SECTION_EFFECTS: Dict[str, Dict[str, Dict[str, list]]] = {
    "edm": {
        "intro": {
            "movement": [MovementType.TRUE_CIRCLE, MovementType.VERTICAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "verse": {
            "movement": [MovementType.HORIZONTAL_SWEEP, MovementType.MIRROR_SWEEP, MovementType.TRUE_CIRCLE],
            "dimmer": [DimmerType.BEAT_SYNC, DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "chorus": {
            "movement": [MovementType.CIRCLE_CHASE, MovementType.BALLYHOO, MovementType.COUNTER_ROTATION],
            "dimmer": [DimmerType.BEAT_SYNC, DimmerType.KICK_FOLLOWER],
            "strobe": [StrobeMode.BEAT_LOCKED],
        },
        "drop": {
            "movement": [MovementType.ALTERNATING, MovementType.MIRROR_SWEEP, MovementType.CENTER_OUT_WAVE],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.BURST],
        },
        "breakdown": {
            "movement": [MovementType.TRUE_CIRCLE, MovementType.SPIRAL],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
    },
    "rock": {
        "intro": {
            "movement": [MovementType.VERTICAL_SWEEP, MovementType.NONE],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "verse": {
            "movement": [MovementType.HORIZONTAL_SWEEP, MovementType.TILT_CHASE],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.OFF],
        },
        "chorus": {
            "movement": [MovementType.BALLYHOO, MovementType.MIRROR_SWEEP, MovementType.ALTERNATING],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.BEAT_LOCKED],
        },
        "drop": {
            "movement": [MovementType.TILT_BUMP, MovementType.PAN_BUMP, MovementType.COUNTER_ROTATION],
            "dimmer": [DimmerType.KICK_FOLLOWER],
            "strobe": [StrobeMode.BURST],
        },
        "breakdown": {
            "movement": [MovementType.NONE, MovementType.VERTICAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
    },
    "pop": {
        "intro": {
            "movement": [MovementType.TRUE_CIRCLE, MovementType.HORIZONTAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "verse": {
            "movement": [MovementType.MIRROR_SWEEP, MovementType.TRUE_CIRCLE, MovementType.PAN_CHASE],
            "dimmer": [DimmerType.SINE_PULSE, DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.OFF],
        },
        "chorus": {
            "movement": [MovementType.BALLYHOO, MovementType.CIRCLE_CHASE, MovementType.CENTER_OUT_WAVE],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.BEAT_LOCKED],
        },
        "drop": {
            "movement": [MovementType.ALTERNATING, MovementType.MIRROR_SWEEP],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.BURST],
        },
        "breakdown": {
            "movement": [MovementType.TRUE_CIRCLE, MovementType.SPIRAL],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
    },
    "hip_hop": {
        "intro": {
            "movement": [MovementType.NONE, MovementType.VERTICAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "verse": {
            "movement": [MovementType.HORIZONTAL_SWEEP, MovementType.TILT_CHASE],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.OFF],
        },
        "chorus": {
            "movement": [MovementType.MIRROR_SWEEP, MovementType.BALLYHOO],
            "dimmer": [DimmerType.BEAT_SYNC],
            "strobe": [StrobeMode.BEAT_LOCKED],
        },
        "drop": {
            "movement": [MovementType.TILT_BUMP, MovementType.CENTER_OUT_WAVE],
            "dimmer": [DimmerType.KICK_FOLLOWER],
            "strobe": [StrobeMode.BURST],
        },
        "breakdown": {
            "movement": [MovementType.NONE, MovementType.SPIRAL],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
    },
    "jazz": {
        "intro": {
            "movement": [MovementType.NONE],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "verse": {
            "movement": [MovementType.NONE, MovementType.VERTICAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "chorus": {
            "movement": [MovementType.TRUE_CIRCLE, MovementType.HORIZONTAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "drop": {
            "movement": [MovementType.HORIZONTAL_SWEEP],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
        "breakdown": {
            "movement": [MovementType.NONE],
            "dimmer": [DimmerType.SINE_PULSE],
            "strobe": [StrobeMode.OFF],
        },
    },
}

# Successive drops are stepped down slightly so the fourth one still reads as an
# event. Deterministic on purpose: this scales the rendered rig level, and the
# render path has to produce the same frames for the same audio.
DROP_FATIGUE_CYCLE: Tuple[float, ...] = (0.0, 0.10, 0.04, 0.14)

# Renderer sections that are not SongSection members, mapped onto the table that
# carries the intensity ranges.
SECTION_RANGE_ALIASES: Dict[str, str] = {
    "build_up": "buildup",
    "pre-chorus": "pre_chorus",
    "prechorus": "pre_chorus",
    "break": "breakdown",
    "hook": "chorus",
}


def section_intensity_range(section: str) -> Tuple[float, float]:
    """The (min, max) intensity band a section is meant to occupy."""
    name = SECTION_RANGE_ALIASES.get(str(section or "").lower(), str(section or "").lower())
    try:
        key = SongSection(name)
    except ValueError:
        key = SongSection.UNKNOWN
    config = DEFAULT_SECTION_CONFIGS.get(key, DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN])
    return config.intensity_range


# Minimum bars between effect changes per genre
GENRE_MIN_CHANGE_BARS: Dict[str, int] = {
    "edm": 4,
    "rock": 4,
    "pop": 8,
    "hip_hop": 4,
    "jazz": 8,
}


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
    Genre-aware, section-driven, with professional timing rules.
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
        self.static_probability = 0.05  # per second
        self._last_delta_time = 1.0 / 60.0

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

        # v2: Genre awareness
        self._genre: str = "edm"
        self._section: str = "unknown"

        # v2: Bar/phrase boundary timing
        self._total_bars: int = 0
        self._last_effect_change_bar: int = 0
        self._last_movement_change_bar: int = 0
        self._last_color_change_bar: int = 0

        # v2: Dynamic range enforcement
        self._intensity_history: deque = deque(maxlen=1800)  # ~30s at 60fps
        self._drop_count: int = 0
        self._drop_intensity_variation: float = 0.0  # Anti-fatigue offset

        # Live dynamics
        self._dynamics = DynamicsShaper()
        self._dynamics_section: str = "unknown"

        # Bumped on every state entry; decisions that belong to a state latch on it
        # instead of re-rolling on every one of the 60 frames the state spans.
        self._state_serial: int = 0
        self._state_entry_time: float = 0.0
        self._state_edge_unseen: bool = False
        self._breakdown_look_serial: int = -1
        self._breakdown_use_static: bool = False
        self._breakdown_static_look: StaticLook = StaticLook.ALL_CENTER
        self._breakdown_pattern: Tuple[MovementType, str] = (MovementType.TRUE_CIRCLE, "circle_slow")
        self._drop_accent_serial: int = -1
        self._drop_static_look: StaticLook = StaticLook.ALL_CENTER

        # v2: Anticipation
        self._anticipation_active: bool = False
        self._anticipation_target_state: Optional[LightingState] = None
        self._pre_drop_blackout_triggered: bool = False

        # Boundary-based pre-cue/commit state
        self._pending_selection: Optional[EffectSelection] = None
        self._pending_effect_name: Optional[str] = None
        self._pending_commit_bar: Optional[int] = None
        self._pending_section: Optional[str] = None
        self._pending_state: Optional[LightingState] = None
        self._pre_cue_active: bool = False
        self._last_commit_bar: int = 0

    def set_genre(self, genre: str):
        """Set the active genre for decision weighting."""
        self._genre = genre.lower()

    def set_section(self, section: str):
        """Set the current song section (from SectionManager)."""
        normalized = section.lower()
        old_section = self._section
        if old_section == normalized:
            return

        self._section = normalized
        self._on_section_change(old_section, normalized)

    def _resolve_state_for_section(self, section: str) -> LightingState:
        """Map section names to lighting states."""
        section_state_map = {
            "intro": LightingState.INTRO,
            "verse": LightingState.SUSTAIN,
            "pre_chorus": LightingState.BUILDUP,
            "chorus": LightingState.PEAK,
            "drop": LightingState.PEAK,
            "breakdown": LightingState.BREAKDOWN,
            "bridge": LightingState.SUSTAIN,
            "outro": LightingState.OUTRO,
            "buildup": LightingState.BUILDUP,
        }
        return section_state_map.get(section, self.state)

    def _on_section_change(self, old_section: str, new_section: str):
        """Handle section transition with boundary commit + pre-cue staging."""
        new_state = self._resolve_state_for_section(new_section)
        impact_event = is_impact_event(new_section)

        if impact_event:
            self._clear_pending_transition()
            self._commit_section_change(new_section, new_state)
            return

        commit_bar = next_musical_boundary_bar(self._total_bars)
        self._pending_selection = self._build_genre_selection(new_section)
        self._pending_effect_name = self._pending_selection.movement.value
        self._pending_commit_bar = commit_bar
        self._pending_section = new_section
        self._pending_state = new_state
        self._pre_cue_active = bars_until_boundary(self._total_bars) <= 1

    def _enter_state(self, new_state: LightingState):
        """Single entry point for state changes, so per-state latches stay honest."""
        self.previous_state = self.state
        self.state = new_state
        self.state_start_time = time.time()
        self._state_entry_time = self.time
        self.bars_in_state = 0
        self._state_serial += 1
        self._state_edge_unseen = True

        if new_state == LightingState.PEAK:
            self._drop_count += 1
            self._drop_intensity_variation = DROP_FATIGUE_CYCLE[
                (self._drop_count - 1) % len(DROP_FATIGUE_CYCLE)
            ]

    def _commit_section_change(self, section: str, new_state: LightingState):
        """Commit pending/immediate section transitions."""
        if new_state != self.state:
            self._enter_state(new_state)

        if self._pending_selection is not None:
            self.selection = copy.deepcopy(self._pending_selection)
        else:
            self.selection = self._build_genre_selection(section)

        self._last_effect_change_bar = self._total_bars
        self._last_movement_change_bar = self._total_bars
        self._last_color_change_bar = self._total_bars
        self._last_commit_bar = self._total_bars + 1 if self.audio.is_beat and is_downbeat(self.audio.beat_number) else self._total_bars
        self._clear_pending_transition()

    def _clear_pending_transition(self):
        self._pending_selection = None
        self._pending_effect_name = None
        self._pending_commit_bar = None
        self._pending_section = None
        self._pending_state = None
        self._pre_cue_active = False

    def _update_pre_cue_state(self):
        if self._pending_commit_bar is None:
            self._pre_cue_active = False
            return
        self._pre_cue_active = (self._pending_commit_bar - self._total_bars) <= 1

    def _commit_pending_on_downbeat(self):
        if self._pending_commit_bar is None:
            return
        if not (self.audio.is_beat and is_downbeat(self.audio.beat_number)):
            return

        current_bar = self._total_bars + 1
        if current_bar >= self._pending_commit_bar and self._pending_state is not None and self._pending_section is not None:
            self._commit_section_change(self._pending_section, self._pending_state)

    def _is_phrase_boundary(self) -> bool:
        current_bar = self._total_bars + 1
        return any(current_bar % size == 0 for size in (4, 8, 16))

    def _can_change_effect(self, change_type: str = "general") -> bool:
        """Check if effect change is allowed at current bar/phrase boundary."""
        min_bars = GENRE_MIN_CHANGE_BARS.get(self._genre, 4)
        if not self._is_phrase_boundary():
            return False

        if change_type == "movement":
            return (self._total_bars - self._last_movement_change_bar) >= max(min_bars, 8)
        if change_type == "color":
            return (self._total_bars - self._last_color_change_bar) >= max(min_bars, 8)
        if change_type == "strobe":
            return (self._total_bars - self._last_effect_change_bar) >= min_bars
        return (self._total_bars - self._last_effect_change_bar) >= min_bars

    def _genre_allows_strobe(self) -> bool:
        """Does this genre's palette contain a strobe anywhere at all?

        Read off `GENRE_SECTION_EFFECTS` rather than naming jazz again, so the
        table stays the one place the restraint is written down. Jazz lists OFF
        in every section, which is the whole of "jazz never strobes".
        """
        genre_effects = GENRE_SECTION_EFFECTS.get(self._genre, GENRE_SECTION_EFFECTS["edm"])
        return any(
            mode is not StrobeMode.OFF
            for section in genre_effects.values()
            for mode in section.get("strobe", ())
        )

    def _build_genre_selection(self, section: str) -> EffectSelection:
        """Build effect selection from genre-specific palettes for a section."""
        selection = copy.deepcopy(self.selection)
        genre_effects = GENRE_SECTION_EFFECTS.get(self._genre, GENRE_SECTION_EFFECTS["edm"])
        section_effects = genre_effects.get(section, genre_effects.get("verse", {}))

        movement_options = section_effects.get("movement", [MovementType.NONE])
        dimmer_options = section_effects.get("dimmer", [DimmerType.SINE_PULSE])
        strobe_options = section_effects.get("strobe", [StrobeMode.OFF])

        selection.movement = random.choice(movement_options) if movement_options else MovementType.NONE
        selection.dimmer = random.choice(dimmer_options) if dimmer_options else DimmerType.SINE_PULSE
        selection.strobe = random.choice(strobe_options) if strobe_options else StrobeMode.OFF

        preset_map = {
            MovementType.HORIZONTAL_SWEEP: "slow_sweep",
            MovementType.TRUE_CIRCLE: "circle_slow",
            MovementType.MIRROR_SWEEP: "mirror_sweep",
            MovementType.BALLYHOO: "ballyhoo_classic",
            MovementType.CIRCLE_CHASE: "circle_chase",
            MovementType.CENTER_OUT_WAVE: "center_out",
            MovementType.PAN_CHASE: "chase_left_right",
            MovementType.COUNTER_ROTATION: "vortex",
            MovementType.ALTERNATING: "alternating_sweep",
            MovementType.TILT_CHASE: "tilt_wave",
        }
        selection.movement_preset = preset_map.get(selection.movement, "")

        dimmer_preset_map = {
            DimmerType.SINE_PULSE: "breathing",
            DimmerType.BEAT_SYNC: "beat_kick",
            DimmerType.KICK_FOLLOWER: "beat_kick",
            DimmerType.RAMP_UP: "build_up",
            DimmerType.RAMP_DOWN: "fade_out",
        }
        selection.dimmer_preset = dimmer_preset_map.get(selection.dimmer, "breathing")

        if selection.dimmer in (DimmerType.BEAT_SYNC, DimmerType.KICK_FOLLOWER):
            selection.beat_pattern = BEAT_PATTERNS.get("four_on_floor", []) if section in ("drop", "chorus") else BEAT_PATTERNS.get("half_time", [])

        # `strobe_on_drop` is checked before `selection.strobe` downstream, so a
        # genre with OFF in every section still got a drop burst through it.
        if section == "drop" and self._genre_allows_strobe():
            selection.strobe_on_drop = True
            selection.strobe_preset = "drop_burst"
        else:
            selection.strobe_on_drop = False
            selection.strobe_preset = "none"

        selection.use_static_look = False
        if section in ("breakdown", "intro"):
            selection.use_static_look = random.random() < 0.5
            if selection.use_static_look:
                selection.static_look = self._pick_static_look()
                selection.movement = MovementType.NONE

        return selection

    def get_transition_debug(self) -> Dict[str, Optional[object]]:
        """Expose pending/commit timing for UI debug overlays."""
        commit_in_bars = None
        if self._pending_commit_bar is not None:
            commit_in_bars = max(0, self._pending_commit_bar - self._total_bars)
        return {
            "pending_effect": self._pending_effect_name,
            "commit_in_bars": commit_in_bars,
            "last_commit_bar": self._last_commit_bar,
            "pre_cue_active": self._pre_cue_active,
        }

    def get_dynamic_intensity_scale(self) -> float:
        """Get intensity scale factor for dynamic range enforcement.

        Prevents fatigue by scaling down when average intensity is too high.
        Also applies anti-fatigue variation on drops.
        """
        if len(self._intensity_history) < 60:
            return 1.0

        avg_intensity = sum(self._intensity_history) / len(self._intensity_history)

        # If average > 85%, scale down to create headroom
        if avg_intensity > 0.85:
            scale = 0.85 / avg_intensity
            return max(0.7, scale)

        # Anti-fatigue on drops
        if self.state == LightingState.PEAK:
            return 1.0 - self._drop_intensity_variation

        return 1.0

    def track_intensity(self, intensity: float):
        """Track output intensity for dynamic range enforcement."""
        self._intensity_history.append(intensity)

    def update_dynamics(
        self,
        energy: float,
        section: str,
        delta_time: float,
        bass: float = 0.0,
        is_beat: bool = False,
    ) -> DynamicsFrame:
        """Shape one frame of intensity. Call exactly once per rendered frame.

        `frame.level` is a 0-1 drive level that replaces bare `energy` wherever
        the renderer scales a dimmer by it: it carries the same zero floor
        (silent in, black out) but has contrast inside a section instead of one
        scalar for the whole of it.
        """
        # Nothing in here may raise: a dark rig with no traceback is worse than
        # a frame of the old flat behaviour.
        try:
            name = str(section or "unknown").lower()
            self._dynamics_section = name
            frame = self._dynamics.update(
                energy=energy,
                delta_time=delta_time,
                intensity_range=section_intensity_range(name),
                bass=bass,
                is_beat=is_beat,
                scale=self.get_dynamic_intensity_scale(),
            )
            self._intensity_history.append(frame.level)
            return frame
        except Exception:
            safe = 0.0
            try:
                safe = min(1.0, max(0.0, float(energy)))
            except (TypeError, ValueError):
                safe = 0.0
            return DynamicsFrame(
                level=safe, contrast=safe, accent=0.0, reference=0.0, scale=1.0, ratio=0.0
            )

    def get_dynamics(self) -> DynamicsFrame:
        """The last shaped frame, for UI and debug readouts."""
        return self._dynamics.last

    def reset_dynamics(self):
        """Forget the loudness reference (new song, new input device)."""
        self._dynamics.reset()
        self._intensity_history.clear()

    def update(self, audio: AudioState, delta_time: float):
        """
        Update decision engine with new audio state.

        Args:
            audio: Current audio analysis
            delta_time: Time since last update
        """
        self.audio = audio
        self.time += delta_time
        self._last_delta_time = max(0.0, min(0.25, delta_time))

        # Update energy history and trend (BUG-023 fix: deque handles eviction automatically)
        self.energy_history.append(audio.energy)

        if len(self.energy_history) >= 2:
            # Deques don't support slicing - use list conversion for trend calc
            history = list(self.energy_history)
            recent = sum(history[-8:]) / min(8, len(history))
            older_count = max(1, len(history) - 8)
            older = sum(history[:-8]) / older_count if older_count > 0 else recent
            audio.energy_trend = recent - older

        # Track total bars
        if audio.is_beat and audio.beat_number % 4 == 0:
            self._total_bars += 1

        # Pre-cue stage starts one bar before commit; actual commit only on downbeat.
        self._update_pre_cue_state()
        self._commit_pending_on_downbeat()

        # Detect song structure changes
        self._detect_structure_changes()

        # Update cooldowns
        self.cooldowns.update()

        # Make effect decisions
        self._decide_effects()

        # `previous_state` is the only edge a consumer has. Left latched it makes
        # every edge-triggered effect re-fire on every frame the state persists,
        # so its envelope restarts and never completes.
        if self._state_edge_unseen:
            self._state_edge_unseen = False
        else:
            self.previous_state = self.state

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

        if new_state != self.state and self._state_change_allowed(new_state):
            self._enter_state(new_state)

    def _state_change_allowed(self, new_state: LightingState) -> bool:
        """Hold a state for at least a bar so it cannot flap at frame rate.

        A drop is exempt: an impact that waits for a hold has already missed.
        """
        if new_state == LightingState.PEAK and self.audio.is_drop:
            return True
        bpm = self.audio.bpm if self.audio.bpm and self.audio.bpm > 0 else 128.0
        min_hold_s = max(0.8, min(3.0, (4.0 * 60.0) / bpm))
        return (self.time - self._state_entry_time) >= min_hold_s

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
        # Keep subtle movement in intro so rigs are visibly alive during startup.
        self.selection.movement = MovementType.TRUE_CIRCLE
        self.selection.movement_preset = "circle_slow"
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

        # v2 Anticipation: pre-drop signal when build-up is nearly done
        if progress > 0.9 and not self._pre_drop_blackout_triggered:
            self._pre_drop_blackout_triggered = True
            self._anticipation_active = True
            self._anticipation_target_state = LightingState.PEAK

    def _decide_peak(self):
        """Effects for peak/drop section with genre awareness."""
        s = self.selection
        audio = self.audio

        # Reset anticipation state
        self._pre_drop_blackout_triggered = False
        self._anticipation_active = False

        # STROBE ON DROP! (genre-dependent)
        if self.bars_in_state == 0 and self._genre_allows_strobe():
            # The first bar of a drop spans ~120 frames; arming the burst once per
            # entry is what lets its envelope run instead of restarting each frame.
            if self._drop_accent_serial != self._state_serial:
                self._drop_accent_serial = self._state_serial
                self._drop_static_look = self._pick_static_look()
                self.cooldowns.set_cooldown("strobe_burst", 64, audio.bpm)
                self.cooldowns.set_cooldown("static_look", 16, audio.bpm)

            s.strobe_on_drop = True
            s.strobe = StrobeMode.BURST
            s.strobe_preset = "drop_burst"

            # Static look during strobe
            s.use_static_look = True
            s.static_look = self._drop_static_look

        # Movement: genre-specific high energy patterns (bar-boundary check)
        if self.cooldowns.is_available("pattern_change") and self._can_change_effect("movement"):
            # Use genre-specific drop patterns
            genre_effects = GENRE_SECTION_EFFECTS.get(self._genre, GENRE_SECTION_EFFECTS["edm"])
            high_energy_patterns = genre_effects.get("drop", {}).get("movement", [
                MovementType.BALLYHOO,
                MovementType.CIRCLE_CHASE,
                MovementType.MIRROR_SWEEP,
                MovementType.COUNTER_ROTATION,
                MovementType.ALTERNATING,
            ])
            # 60% chance to pick from genre list, 40% use Markov
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
            self._last_movement_change_bar = self._total_bars
            self._last_effect_change_bar = self._total_bars

        # Dimmer: beat-sync kick pattern
        s.dimmer = DimmerType.BEAT_SYNC
        s.beat_pattern = BEAT_PATTERNS["four_on_floor"]
        s.dimmer_preset = "beat_kick"

    def _decide_sustain(self):
        """Effects for sustain section (after drop) with genre awareness."""
        s = self.selection
        audio = self.audio

        # Movement: genre-specific patterns with bar-boundary timing
        if self.cooldowns.is_available("pattern_change") and self._can_change_effect("movement"):
            # Use genre-specific chorus/verse patterns for sustain
            genre_effects = GENRE_SECTION_EFFECTS.get(self._genre, GENRE_SECTION_EFFECTS["edm"])
            sustain_patterns = genre_effects.get("chorus", {}).get("movement", [
                MovementType.TRUE_CIRCLE,
                MovementType.CIRCLE_CHASE,
                MovementType.PAN_CHASE,
                MovementType.TILT_CHASE,
                MovementType.HORIZONTAL_SWEEP,
                MovementType.MIRROR_SWEEP,
            ])

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
            self._last_movement_change_bar = self._total_bars
            self._last_effect_change_bar = self._total_bars

        # Dimmer: beat-sync
        s.dimmer = DimmerType.BEAT_SYNC
        if audio.energy > 0.7:
            s.beat_pattern = BEAT_PATTERNS["four_on_floor"]
        else:
            s.beat_pattern = BEAT_PATTERNS["half_time"]

        # Occasional strobe on strong beats
        if audio.is_beat and audio.bass > 0.9 and self._genre_allows_strobe():
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

        # Breakdown: calm, slow, dramatic looks. Chosen once per breakdown; a
        # re-roll every frame is a look that changes 60 times a second.
        if self._breakdown_look_serial != self._state_serial:
            self._breakdown_look_serial = self._state_serial
            self._breakdown_use_static = random.random() < 0.5
            if self._breakdown_use_static:
                self._breakdown_static_look = self._pick_static_look()
            else:
                self._breakdown_pattern = random.choice([
                    (MovementType.VERTICAL_SWEEP, "gentle_tilt"),
                    (MovementType.TRUE_CIRCLE, "circle_slow"),
                    (MovementType.SPIRAL, "spiral_expand"),
                ])

        if self._breakdown_use_static:
            s.use_static_look = True
            s.static_look = self._breakdown_static_look
            s.movement = MovementType.NONE
        else:
            s.movement, s.movement_preset = self._breakdown_pattern

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

        # Probability increases with time since last static. `static_probability`
        # is per second: as a per-frame chance it fires within a third of a second.
        time_since_static = self.time - self.last_static_time
        probability = self.static_probability * (1 + time_since_static / 60) * self._last_delta_time

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
        self._enter_state(state)
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
