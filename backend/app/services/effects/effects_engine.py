"""
ILS Intelligent Effects Engine
Main coordinator for all 4 layers:
- Layer 1: Base Intensity (from audio energy)
- Layer 2: Movement (pan/tilt patterns)
- Layer 3: Dimmer Effects (intensity modulation)
- Layer 4: Strobe Effects

Outputs DMX values combining all layers.
"""

import asyncio
import copy
import logging
import math
import time
from typing import Dict, List, Optional, Callable, Set, Tuple
from dataclasses import dataclass

import numpy as np

from .fixture_groups import (
    Fixture, FixtureGroup, FixtureGroupManager, create_demo_rig
)
from .movement_patterns import (
    MovementEngine, MovementType, StaticLook, MovementParams, MOVEMENT_PRESETS
)
from .dimmer_effects import (
    DimmerEngine, DimmerType, DimmerParams, DIMMER_PRESETS, BEAT_PATTERNS
)
from .strobe_controller import (
    StrobeController, StrobeMode, StrobeParams, STROBE_PRESETS, DropStrobeSequence
)
from .color_mapper import (
    ColorMapper, ColorPalette, AudioFeatures, RGB, COLOR_PRESETS
)
from .decision_engine import (
    DecisionEngine, LightingState, AudioState, EffectSelection
)
from .lfo_engine import LFOEngine
from ..lighting.section_templates import get_section_template
from ..lighting.fixture_capabilities import get_capability_profile_for_fixture
from ..lighting.movement_patterns import PRO_MOVEMENT_PRESETS

logger = logging.getLogger(__name__)

# Professional lighting modules - imported lazily in __init__ to avoid circular imports
# (lighting modules import from effects submodules, which triggers effects/__init__.py,
#  which imports effects_engine, creating a cycle)


@dataclass
class EffectsConfig:
    """
    Configuration for the effects engine.

    AI BUSKER MODE: By default, auto_mode is enabled so the decision engine
    drives show behavior directly from live audio analysis.
    """
    # Update rate
    fps: float = 60.0

    # Auto-pilot mode (use decision engine)
    auto_mode: bool = True

    # Manual overrides
    manual_movement: Optional[MovementType] = None
    manual_dimmer: Optional[DimmerType] = None
    manual_strobe: Optional[StrobeMode] = None
    manual_static_look: Optional[StaticLook] = None

    # BPM (from audio or manual)
    bpm: float = 128.0

    # Color palette
    palette: ColorPalette = ColorPalette.EDM

    # Enable layers
    movement_enabled: bool = True
    dimmer_enabled: bool = True
    strobe_enabled: bool = True
    color_enabled: bool = True
    movement_music_reactive: bool = False
    movement_rotation_bars: int = 16

    # Color stability - lock palette per song
    lock_palette_per_song: bool = True
    silence_threshold: float = 0.02  # RMS below this = silence
    silence_duration_for_song_change: float = 1.5  # Seconds of silence = new song

    # Move-In-Black (MIB)
    mib_enabled: bool = True
    mib_transition_ms: int = 450
    mib_pan_tilt_threshold: float = 28.0  # DMX-value delta threshold

    # ML target gating for section/genre driven movement target changes
    # (stabilizes pan/tilt target behavior when confidence jitters)
    ml_target_gating_enabled: bool = True

    # Genre switch gate
    ml_genre_confidence_on: float = 0.48
    ml_genre_confidence_off: float = 0.40
    ml_genre_consecutive_frames: int = 3
    ml_genre_min_hold_ms: int = 600
    ml_genre_min_confidence_delta: float = 0.08

    # Section switch gate
    ml_section_confidence_on: float = 0.58
    ml_section_confidence_off: float = 0.50
    ml_section_consecutive_frames: int = 2
    ml_section_min_hold_ms: int = 350
    ml_section_min_confidence_delta: float = 0.06

    # Safety constraints (research-aligned defaults, runtime configurable)
    strobe_hz_cap: float = 24.0
    strobe_max_duty_cycle: float = 0.42
    strobe_burst_max_s: float = 0.70
    strobe_refractory_s: float = 0.16
    audience_intensity_cap: float = 1.00
    movement_when_bright: bool = True
    bright_movement_dimmer_threshold: float = 0.82
    bright_movement_pan_tilt_cap_deg: float = 55.0

    # Research-pack runtime context flags
    accessibility_mode: str = "no_strobe"     # no_strobe | conservative | performance
    venue_mode: str = "concert"               # theatre | broadcast | corporate | concert | club
    camera_mode: bool = False
    major_change_min_bars: int = 2


@dataclass
class _TargetGateState:
    """Runtime gating state for categorical ML targets (genre/section)."""

    current: Optional[str] = None
    current_confidence: float = 0.0
    pending: Optional[str] = None
    pending_count: int = 0
    last_accept_time: float = -999.0


def _travel(fixture, attribute: str) -> float:
    """Degrees of travel on an axis; 0 means the fixture cannot move it."""
    try:
        return float(getattr(fixture, attribute, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


# === Phase-locked musical clock ============================================
# Tempo hypotheses for the onset-envelope comb, spaced 0.6% apart across the
# range the renderer is willing to run its motion at.
_CLOCK_MIN_BPM = 60.0
_CLOCK_MAX_BPM = 190.0
_CLOCK_CAND_BPM = _CLOCK_MIN_BPM * np.power(
    1.006, np.arange(int(math.log(_CLOCK_MAX_BPM / _CLOCK_MIN_BPM) / math.log(1.006)) + 1)
)
_CLOCK_CAND_F = _CLOCK_CAND_BPM / 60.0
_CLOCK_LOG_CAND = np.log(_CLOCK_CAND_BPM)
# Human tempo preference curve: without it a strongly accented backbeat wins the
# comb at half the real tempo and the whole show runs in double time.
_CLOCK_PRIOR = np.exp(-0.5 * ((_CLOCK_LOG_CAND - math.log(124.0)) / 0.55) ** 2)

_CLOCK_COMB_TAU = 2.0        # s, memory of the tempo comb
_CLOCK_PHASE_TAU = 2.0       # s, memory of the phase detector
_CLOCK_KP = 0.40             # share of the phase error corrected per beat
_CLOCK_KI = 0.10             # share of the phase error fed to the period per beat
_CLOCK_MAX_SLEW = 0.5        # correction may not exceed half the nominal rate,
                             # which is what keeps the clock monotonic
_CLOCK_CONF_MIN = 0.08
_CLOCK_CONF_GOOD = 0.35
_CLOCK_ACQUIRE_FLOOR = 0.12
_CLOCK_EVIDENCE_S = 2.0
_CLOCK_CHALLENGE_RATIO = 1.10
_CLOCK_CHALLENGE_S = 0.20
_CLOCK_HARMONIC = 0.50
_CLOCK_REPORTED_WEIGHT = 0.12
# When the analyser publishes a confidence with its tempo it has heard the drums
# (`TempoTracker`) and is saying which metrical level the music is at, which a
# loudness comb cannot tell: two-step drum and bass reads at 3/4 of its tempo
# here and hip-hop at double. It then picks the level; see `_beat_clock_observe`.
_CLOCK_TEMPO_WIDTH = 0.03    # natural-log units, about 3%
# Metrical relatives of the comb's own tempo the analyser may move it to, and
# how close (natural log) one must be to the analyser's tempo to count.
_CLOCK_LEVEL_RATIOS = (1.0, 2.0, 0.5, 4.0 / 3.0, 0.75, 1.5, 2.0 / 3.0)
_CLOCK_LEVEL_MATCH = 0.06
# The comb must hear at least this share of its strongest pulse at the level the
# analyser names before the clock takes its phase from there.
_CLOCK_LEVEL_MIN_SHARE = 0.25


def _clock_relative(a: float, b: float) -> bool:
    """Whether two tempi are metrical levels of one another."""
    return any(abs(math.log(a / (b * r))) < _CLOCK_TEMPO_WIDTH for r in _CLOCK_LEVEL_RATIOS)
_CLOCK_LOG_GAIN = 40.0
# Section detection is deliberately level-invariant, so a ballad has the same relative
# dynamics as a club track and would earn the same accents. Absolute level is what
# separates them: measured across the synthetic material, sparse acoustic playing peaks
# near 0.08 of full scale here and dance material sits above 0.25.
ACCENT_ABSOLUTE_FLOOR = 0.12
# One analysis block of RMS is a boxcar ending at the callback, and a percussive
# attack spills into the block after the one it starts in, so the positive
# difference of two blocks reports an attack about 0.7 of a block late.
_CLOCK_ONSET_LEAD = 0.20

# How long the drop look may hold the white strobe open once a drop commits.
# Shorter than the detector's own drop hold, so the flash is the front of the
# drop rather than the whole of it. It is still clamped by `strobe_hz_cap` and
# only reaches a fixture while the accent governor has strobing armed.
_SECTION_DROP_STROBE_S = 1.55

# `strobe_hz_cap` is a promise about flashes per second, and the grid frequency
# is not the same number. The flash predicate is `(t * hz) % 1 < duty` gated by
# a window that opens on a musical event, so the partial flash at the moment the
# window opens is an onset the grid never scheduled: a window opening just
# before a grid edge delivers `1 + floor(hz + duty)` onsets in its first second.
# Driven at a nominal 3.0 Hz with a 0.34 duty the rig measured four flashes in
# one second on the drop track - the general-audience limit, breached. Keeping
# `hz + duty` strictly under the cap keeps the delivered count inside it.
_STROBE_HZ_STRICT_MARGIN = 0.06

# Drop anticipation. The build is recognised many bars before the drop lands and
# dance music puts the drop on a phrase boundary, so `SectionManager.drop_prediction`
# can name the instant long before the reactive detector is willing to. The
# response is split by what being wrong costs.
#
# The dip is speculative. A short darkening a beat or two before the projected
# downbeat reads as musical intent when no drop arrives, and it is the contrast
# that makes a real one land.
_DROP_DIP_LEAD_BEATS = 2.0
_DROP_DIP_DEPTH = 0.55
_DROP_DIP_MIN_CONFIDENCE = 0.50
# Confirmation that never comes gives the build its level back over a bar, which
# is a fade rather than a snap.
_DROP_DIP_RECOVER_BARS = 1.0
# The dip may not deepen faster than its own approach ramp - full depth over the
# two beats of lead. Without a bound in this direction any discontinuity in the
# projected instant, or confidence crossing the arming threshold, steps the whole
# rig in a single frame; `_clock_bar_offset` is allowed to move three beats once
# every eight bars, which is exactly such a discontinuity.
_DROP_DIP_ONSET_LEAD_BEATS = _DROP_DIP_LEAD_BEATS

# The hit is confirmed. Full level waits for the audio to agree, inside this much
# either side of the projected downbeat, and to keep agreeing for `DWELL`. One
# 60 fps sample of a decaying transient is not a drop: a lone kick over a quiet
# pad reads as almost pure bass for exactly as long as the kick rings, and
# measures 0.98 on the harness's own build/impact/breakdown.
_DROP_CONFIRM_WINDOW_S = 0.35
_DROP_CONFIRM_DWELL_S = 0.05
# What agreement means. Every term is measured against something this programme
# is already doing, so all of them read the same at -12 dB as at +9 dB:
#
# * the low end the build filtered out is back, against the build's own bass
#   reference. A build whose low end is already up moves it a couple of
#   hundredths across its own phrase boundary; only a drop moves it by
#   `AccentPosture.bass_step`, the same jump the accent governor calls a drop.
# * the moment is louder than this build has been. Measured as a ratio to the
#   build's own energy rather than against an absolute floor: `energy` is a
#   multiple of the input level, so any absolute term makes the confirmation a
#   function of the fader position. Measured across the harness drop track the
#   real drop steps the build's energy by 1.42x at -12, -6 and 0 dB and by 1.26x
#   at +9 dB, where the analyser's own ceiling compresses it; a moderate one-shot
#   over a decaying build reaches 1.07x.
# * the programme is loud in its own normalised terms.
#
# None of that is the detector's drop rule, which also weighs level, fast-band
# z-score, rise and a refractory against its running centre and spread. This is
# a narrower, cheaper question - "did the thing the projection predicted actually
# happen?" - asked only inside a window the projection already chose, and its
# answer opens a sustained level and nothing else. Accents stay with the detector.
_DROP_CONFIRM_BASS_STEP = 0.25
_DROP_CONFIRM_HEADROOM = 0.45
_DROP_CONFIRM_BASS_FLOOR = 0.45
_DROP_CONFIRM_ENERGY_STEP = 1.15
# How fast those references forget a peak, in level per second.
_DROP_BASS_REF_DECAY = 0.25
_DROP_ENERGY_REF_DECAY = 0.25
# `StreamingSectionDetector._DROP_MIN_PROGRAMME`, restated so the render path
# refuses a confirmation the detector itself would refuse on this term. A steady
# noise floor normalises to 0.5 whatever its level, so it never clears this. It
# is also re-asked on every frame of the anticipated window: a window opened by
# evidence has to close when the evidence goes away, and a build that impacts and
# then breaks down falls back under this within a few frames.
_DROP_CONFIRM_MIN_PROGRAMME = 0.60

# The drop bed. Every level in this renderer is a multiple of energy, and energy
# peaks near a third of full scale on real programme, so a drop rendered as
# `energy x 1.0` was no brighter than the verse it followed - which is why the
# drop used to read as a strobe rather than as a bigger room. This is the
# multiple that makes it bigger; the ceiling leaves the accents somewhere to go.
_DROP_SUSTAIN_GAIN = 2.6
_DROP_SUSTAIN_CEILING = 0.80
# How fast the rig crosses from the section's own level to that bed. The dip is
# there to make the contrast as large as possible, so without a bound the
# dip-to-commit step is the largest luminance transient the show makes - and it
# is one no strobe rule can see, because it is not a flash. At this rate the
# crossing takes an eighth of a second and no single frame moves the rig further
# than the reactive path already does at its own section boundary.
_DROP_BED_RISE_PER_S = 8.0

# Looks change on phrase lines rather than on a bar-count modulo. A phrase is
# counted from the last section change, because the section detector commits
# on bar lines and dance music changes section on phrase lines; without a
# locked clock there is no grid and the old two-bar rotation stands.
_PHRASE_BARS = 8
_PHRASE_BAR_LEAD = 0.1

# Audio loss. Music that was playing and then stops arriving at all (device
# unplugged, capture thread dead, analyser stalled) is not the end of the night,
# so the room crosses to a dim ambient look instead of freezing on stale
# analysis or going black. Digital silence that keeps arriving is different: it
# is the music stopping, and the zero floor still takes the rig dark.
_AUDIO_LOSS_AFTER_S = 2.0
_AMBIENT_HOLD_LEVEL = 0.30
_AMBIENT_FADE_IN_S = 3.0
_AMBIENT_FADE_OUT_S = 1.0
_AMBIENT_DRIFT_HZ = 0.05      # one slow sweep every twenty seconds
_AMBIENT_PAN_DEG = 10.0
_AMBIENT_TILT_DEG = 6.0

# Club style, from the trained genre model. Energy and sections still decide how
# big, how bright and how fast the show is; a style only leans the colours and
# the character of the movement, the way an operator plays a techno room colder
# and tighter than a house room. `speed` and `amp` scale the section's own
# movement speed and size, `patterns` narrows the section's pattern pool (when
# at least two survive), `palettes` are the song palettes cycled through.
_CLUB_STYLE_LOOKS = {
    "house": {"palettes": (ColorPalette.HOUSE, ColorPalette.POP), "speed": 1.0, "amp": 1.0,
              "patterns": ("circle", "figure8", "pan_wave", "tilt_circle")},
    "techno": {"palettes": (ColorPalette.TECHNO, ColorPalette.EDM), "speed": 1.15, "amp": 0.85,
               "patterns": ("tilt_cross", "odd_even", "tilt_circle", "circle")},
    "dnb": {"palettes": (ColorPalette.DUBSTEP, ColorPalette.TECHNO), "speed": 1.25, "amp": 1.1,
            "patterns": ("odd_even", "tilt_cross", "figure8", "tilt_circle")},
    "trance": {"palettes": (ColorPalette.EDM, ColorPalette.AMBIENT), "speed": 0.9, "amp": 1.15,
               "patterns": ("circle", "tilt_circle", "pan_wave", "figure8")},
    "edm": {"palettes": (ColorPalette.EDM, ColorPalette.DUBSTEP), "speed": 1.0, "amp": 1.0,
            "patterns": None},
    "hip_hop": {"palettes": (ColorPalette.HIP_HOP, ColorPalette.ROCK), "speed": 0.8, "amp": 0.85,
                "patterns": ("tilt_cross", "odd_even", "pan_wave")},
    "latin": {"palettes": (ColorPalette.HOUSE, ColorPalette.POP), "speed": 0.9, "amp": 1.05,
              "patterns": ("figure8", "pan_wave", "circle")},
    "afro": {"palettes": (ColorPalette.HOUSE, ColorPalette.HIP_HOP), "speed": 0.9, "amp": 1.0,
             "patterns": ("pan_wave", "figure8", "circle")},
    "open_format": {"palettes": (ColorPalette.POP, ColorPalette.HOUSE), "speed": 1.0, "amp": 1.0,
                    "patterns": None},
    "rock": {"palettes": (ColorPalette.ROCK, ColorPalette.POP), "speed": 1.05, "amp": 1.0,
             "patterns": ("tilt_cross", "odd_even", "pan_wave", "circle")},
    "lounge": {"palettes": (ColorPalette.AMBIENT, ColorPalette.HOUSE), "speed": 0.7, "amp": 0.7,
               "patterns": ("pan_wave", "circle", "tilt_circle")},
}
# A style is adopted after this many fresh, agreeing answers at or above this
# confidence (the model answers every 5 s, so about 15 s of agreement). A
# DJ blend or one odd window does not recolour the room.
_CLUB_STYLE_MIN_CONFIDENCE = 0.55
_CLUB_STYLE_VOTES = 3


class EffectsEngine:
    """
    Main effects engine coordinating all layers.
    """

    def __init__(self, config: EffectsConfig = None):
        self.config = config or EffectsConfig()

        # Initialize components
        self.fixtures = create_demo_rig()
        self.movement = MovementEngine()
        self.dimmer = DimmerEngine()
        self.strobe = StrobeController()
        self.color = ColorMapper(self.config.palette)
        self.decision = DecisionEngine()

        # Drop sequence handler
        self.drop_sequence = DropStrobeSequence(self.strobe)

        # State
        self.running = False
        self.time = 0.0
        self.last_update = time.time()

        # Audio state
        self.audio_features = AudioFeatures()
        self.audio_state = AudioState()

        # DMX output callback
        self._dmx_callback: Optional[Callable[[int, List[int]], None]] = None
        self._emitted_universes: Set[int] = set()
        # Operator intensity controls. Both are applied at the render step, after
        # every effect layer has written its levels, so nothing the show does
        # can outvote them: a latched blackout stays black until it is released.
        self._grand_master: float = 1.0
        self._blackout_latched: bool = False

        # Beat tracking
        self.beat_count = 0
        self.last_beat_time = 0.0

        # Phase-locked musical clock. `beat_phase` is 0 on the beat and
        # `bar_phase` 0 on the downbeat; both are published for readers.
        self.beat_phase = 0.0
        self.bar_phase = 0.0
        self._clock_beats = 0.0
        self._clock_period = 60.0 / max(1.0, float(self.config.bpm))
        self._clock_locked = False
        self._clock_conf = 0.0
        self._clock_pending = 0.0
        self._clock_absorbed = 0.0
        self._clock_hop = 1.0 / 21.5
        self._clock_last_audio_t: Optional[float] = None
        self._clock_prev_loudness = 0.0
        self._clock_evidence = 0.0
        self._clock_challenge = 0.0
        self._clock_comb = np.zeros(len(_CLOCK_CAND_F), dtype=np.complex128)
        self._clock_comb2 = np.zeros(len(_CLOCK_CAND_F), dtype=np.complex128)
        self._clock_comb_norm = 1e-9
        self._clock_zp = 0j
        self._clock_zp_norm = 1e-9
        self._clock_bar_offset = 0
        self._clock_bar_votes = [0.0, 0.0, 0.0, 0.0]
        self._reported_tempo_confidence: Optional[float] = None
        self._clock_bar_moved_at = -1.0e9
        self._clock_last_beat_number: Optional[int] = None

        # Song change detection for color palette locking
        self._silence_start_time: Optional[float] = None
        self._current_song_palette: ColorPalette = self.config.palette
        self._palette_locked: bool = False
        self._palette_version: int = 1
        self._available_palettes = list(ColorPalette)
        self._palette_index = 0
        self._song_transition_marker: Optional[str] = None
        self._pending_palette_reseed: bool = False
        self._pending_palette_reseed_at: float = 0.0
        self._last_palette_reseed_time: float = -999.0

        # White strobe flash state
        self._white_strobe_flash = False
        self._white_strobe_decay = 0.0
        self._last_drop_strobe_time: float = -999.0
        self._safety_events: List[Dict] = []
        self._safety_event_last_time: Dict[str, float] = {}

        # Section template engine
        self._section_templates_enabled = True
        self._current_section_template_key: Optional[str] = None
        self._current_section_intensity_scale: float = 1.0
        self._song_home_section: Optional[str] = None
        self._song_home_template = None

        # True backend MIB state machine (per fixture)
        self._mib_states: Dict[str, Dict] = {}

        # Thread-safe fixture state snapshot for WebSocket readers
        self._fixture_state_lock = asyncio.Lock()
        self._fixture_state_snapshot: List[Dict] = []

        # LFO Engine (grandMA2-style effects) - initialized separately via set_lfo_engine
        self._lfo_engine: Optional[LFOEngine] = None

        # Professional lighting modules (lazy imports to avoid circular dependency)
        from ..lighting.genre_profiles import GenreProfileManager
        from ..lighting.section_manager import SectionManager
        from ..lighting.movement_patterns import ProMovementEngine
        from ..lighting.pro_effects import ProEffects
        from ..lighting.key_lighting import KeyLightingManager
        from ..lighting.beam_pattern_library import (
            BeamPatternName,
            FOCUS_POINT_ANCHORS,
            SymmetryMode,
            build_pattern_params,
        )
        from ..lighting.beam_scene_state_machine import BeamSceneStateMachine
        from ..lighting.beam_look_scheduler import BeamLookScheduler, BEAM_LOOK_LIBRARY

        self.genre_manager = GenreProfileManager()
        self.section_manager = SectionManager(bpm=self.config.bpm)
        self.pro_movement = ProMovementEngine()
        self.pro_effects = ProEffects(bpm=self.config.bpm)
        self.key_lighting = KeyLightingManager()

        # Beam pattern library + scene timing state machine (pro movement layer)
        self._beam_pattern_enum = BeamPatternName
        self._beam_symmetry_enum = SymmetryMode
        self._beam_focus_anchors = FOCUS_POINT_ANCHORS
        self._beam_scene_machine = BeamSceneStateMachine(initial_pattern=BeamPatternName.CENTER_FOCUS_HOLD)
        self._beam_look_scheduler = BeamLookScheduler()
        self._beam_look_library = BEAM_LOOK_LIBRARY
        self._active_beam_look = self._beam_look_scheduler.active_look
        self._build_pattern_params = build_pattern_params
        self._clocked_symmetry_look_cycle = ["opposing_sweeps", "fan", "crisscross"]
        self._clocked_symmetry_preset_cycle = [
            "mirror_slow",
            "split_sweep_slow",
            "tilt_cross_home",
            "figure_8_chase",
            "circle_spread",
            "tilt_wave_slow",
            "mirror_fast",
        ]
        self._clocked_symmetry_active_preset: Optional[str] = None
        self._clocked_chase_cycle = [
            ("forward", "whole", 1, 0, 0.88),
            ("backward", "whole", 1, 0, 0.88),
            ("forward", "half", 1, 0, 0.92),
            ("backward", "half", 1, 0, 0.92),
        ]
        self._clocked_chase_active_index: int = -1
        self._clocked_chase_last_intensity: float = -1.0
        self._smoothed_movement_bpm: float = float(self.config.bpm)
        self._smoothed_valence: float = 0.5
        self._smoothed_arousal: float = 0.5
        self._white_accent_level: float = 0.0
        self._drop_candidate_frames: int = 0
        self._last_forced_drop_time: float = -999.0
        self._prev_energy: float = 0.0
        self._prev_bass: float = 0.0
        self._busker_section_hint: str = "verse"
        self._busker_drop_until: float = -999.0
        self._busker_last_section_change_time: float = -999.0
        self._busker_low_energy_accum: float = 0.0
        self._rebuild_busker_enabled: bool = True
        self._programme_level: Optional[float] = None
        self._rebuild_section: str = "verse"
        self._rebuild_section_changed_at: float = 0.0
        self._rebuild_drop_until: float = -999.0
        self._rebuild_color_hold_until: float = 0.0
        self._rebuild_base_color: RGB = RGB(1.0, 1.0, 1.0)
        self._rebuild_snare_strobe_until: float = -999.0
        self._rebuild_snare_last_trigger: float = -999.0
        self._rebuild_active_pattern: str = "tilt_cross"
        # Bar zero is a real bar on the locked clock, so the hold has to start
        # before any bar the clock can report.
        self._rebuild_pattern_hold_until_bar: int = -(10 ** 9)
        # Phrase grid for look changes; see `_phrase_index`.
        self._phrase_origin_bar: Optional[int] = None
        self._rebuild_pattern_key: Optional[Tuple[str, int]] = None
        self._rebuild_pattern_index: int = 0
        self._rebuild_color_key: Optional[Tuple[str, int]] = None

        # Which record is playing, as the analyser reports it.
        self._reported_track_id: Optional[int] = None
        self._track_id: Optional[int] = None
        self._track_transition: float = 0.0

        # Audio loss: see `_audio_loss_check`.
        self._last_audio_t: Optional[float] = None
        self._music_heard: bool = False
        self._audio_lost: bool = False
        self._ambient_mix: float = 0.0

        # Drop anticipation: speculative dip, confirmed hit.
        self._drop_dip: float = 0.0
        self._drop_armed: bool = False
        self._drop_confirm_gate: float = 1.0
        self._drop_confirm_energy_gate: float = 1.0
        self._drop_confirm_held: float = 0.0
        self._drop_bass_ref: float = 0.0
        self._drop_energy_ref: float = 0.0
        self._drop_hit_until: float = -999.0
        self._drop_bed_mix: float = 0.0

        # Pro lighting integration enabled flag
        self._pro_lighting_enabled = False

        # ML emotion mapping state (set by _apply_ml_data)
        self._ml_emotion_mapping = None

        # Confidence gates for ML-driven target switching. The starting genre is
        # a default, not a detection, so it carries no confidence: seeded at
        # 1.0 it could never be beaten and detection never changed the genre.
        self._ml_genre_gate = _TargetGateState(
            current=self.genre_manager.current_genre.value,
            current_confidence=0.0,
        )
        self._ml_section_gate = _TargetGateState(
            current=self.section_manager.current_section.value,
            current_confidence=1.0,
        )
        # Club style from the trained genre model (see _CLUB_STYLE_LOOKS).
        self._genre_operator_pinned = False
        self._club_style: Optional[str] = None
        self._club_style_candidate: Optional[str] = None
        self._club_style_votes = 0
        self._club_style_seq: Optional[int] = None
        # The style's movement character in force, taken on a pattern change
        # only: speed scales a beat-locked phase, so changing it mid-pattern
        # would jump the heads.
        self._rebuild_style_speed = 1.0
        self._rebuild_style_amp = 1.0

        # Fixture phase choreography controls
        self._leader_follower_enabled: bool = True
        self._leader_follower_delay: float = 0.08  # phase cycles per follower step

        # Base layer home look; pro movement layer provides the live symmetric motion.
        self.movement.set_pattern(
            MovementType.NONE,
            base_look=StaticLook.ALL_CENTER,
        )

    def _select_clocked_symmetric_look(self):
        """Select a symmetric movement look by bar clock, not music energy/section."""
        bars = max(0, int(getattr(self.audio_state, "bars_elapsed", 0) or 0))
        stride = max(4, int(self.config.movement_rotation_bars or 16))
        idx = (bars // stride) % len(self._clocked_symmetry_look_cycle)
        name = self._clocked_symmetry_look_cycle[idx]
        return self._beam_look_library.get(name, self._active_beam_look)

    def _apply_clocked_symmetric_preset(self):
        """Apply a strict BPM-locked symmetric movement preset rotation."""
        bars = max(0, int(getattr(self.audio_state, "bars_elapsed", 0) or 0))
        stride = max(4, int(self.config.movement_rotation_bars or 16))
        idx = (bars // stride) % len(self._clocked_symmetry_preset_cycle)
        preset_name = self._clocked_symmetry_preset_cycle[idx]
        if preset_name == self._clocked_symmetry_active_preset:
            return
        preset = PRO_MOVEMENT_PRESETS.get(preset_name)
        if preset is None:
            return
        self._clocked_symmetry_active_preset = preset_name
        self.pro_movement.set_pattern(
            preset.pattern,
            beat_divisor=max(0.125, preset.beat_divisor),
            pan_amplitude=preset.pan_amplitude,
            tilt_amplitude=preset.tilt_amplitude,
            phase_spread=preset.phase_spread,
            grouping=preset.grouping,
            smoothing=max(0.12, min(0.22, preset.smoothing)),
            snap_positions=list(preset.snap_positions),
        )

    def _compute_clocked_chase_intensity(self) -> float:
        """Return a musical chase intensity for non-reactive busking mode."""
        section = self._busker_section_hint or "unknown"
        if self._pro_lighting_enabled:
            section = (self._busker_section_hint or str(self.section_manager.current_section.value or "unknown")).lower()

        energy = max(0.0, min(1.0, float(self.audio_features.energy)))
        # Section rules requested:
        # - verse: chase on
        # - buildup/pre-chorus: chase on stronger
        # - drop: no chase (strobe owns drop accents)
        # - breakdown: no chase (slow/emotional)
        if section in {"breakdown", "bridge", "intro", "outro"}:
            return 0.0
        if section in {"drop", "peak"}:
            return 0.0
        if section in {"unknown"}:
            return 0.72 if energy > 0.3 else 0.62
        if section in {"buildup", "pre_chorus"}:
            return 0.90 if energy > 0.45 else 0.80
        if section in {"verse"}:
            return 0.78 if energy > 0.35 else 0.68
        if section in {"chorus"}:
            return 0.62 if energy > 0.5 else 0.52
        return 0.0

    def _update_busker_section_intent(self, delta_time: float):
        """Fast reactive section intent: verse/buildup/drop/breakdown with musical hysteresis."""
        energy = float(self.audio_features.energy)
        bass = float(self.audio_features.bass)
        flux = float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0)
        is_beat = bool(self.audio_features.is_beat)
        now = self.time

        energy_delta = energy - self._prev_energy
        bass_delta = bass - self._prev_bass

        # High-impact downbeat detector -> short protected DROP window.
        impact_drop = (
            is_beat
            and energy > 0.52
            and bass > 0.60
            and (flux > 0.055 or energy_delta > 0.055 or bass_delta > 0.08)
        )
        if impact_drop:
            self._busker_drop_until = now + 1.5

        if energy < 0.24 and bass < 0.30:
            self._busker_low_energy_accum += max(0.0, float(delta_time))
        else:
            self._busker_low_energy_accum = max(0.0, self._busker_low_energy_accum - max(0.0, float(delta_time)) * 0.5)

        if now < self._busker_drop_until:
            target = "drop"
        elif self._busker_low_energy_accum > 1.2:
            target = "breakdown"
        elif energy > 0.62 and (flux > 0.07 or energy_delta > 0.03):
            target = "buildup"
        elif energy > 0.68 and bass > 0.52:
            target = "chorus"
        else:
            target = "verse"

        # Short hold to prevent jittery thrashing.
        min_hold = 0.45 if target == "drop" else 0.85
        if target != self._busker_section_hint and (now - self._busker_last_section_change_time) >= min_hold:
            self._busker_section_hint = target
            self._busker_last_section_change_time = now

            if self._pro_lighting_enabled:
                from ..lighting.section_manager import SongSection
                map_section = {
                    "verse": SongSection.VERSE,
                    "buildup": SongSection.BUILDUP,
                    "chorus": SongSection.CHORUS,
                    "drop": SongSection.DROP,
                    "breakdown": SongSection.BREAKDOWN,
                }
                s = map_section.get(self._busker_section_hint)
                if s is not None:
                    self.section_manager.trigger_section(s, immediate=True)

        self._prev_energy = energy
        self._prev_bass = bass

    def _apply_non_reactive_strobe(self, chase_intensity: float = 0.0):
        """Use strobe only on drops, never during chase/breakdown."""
        from ..lighting.pro_effects import ProStrobeMode

        # Hard separation: no strobe while chase is active.
        if float(chase_intensity) > 0.01:
            self.pro_effects.strobe.set_mode(
                ProStrobeMode.OFF,
                frequency=0.1,
                intensity=0.0,
            )
            return

        section = (self._busker_section_hint or str(self.section_manager.current_section.value or "unknown")).lower()
        if section in {"drop"}:
            # Aggressive white drop strobe only for high-energy drops.
            in_fresh_drop_window = (time.time() - self.section_manager._section_start_time) < 1.25
            if in_fresh_drop_window or self.audio_features.energy >= 0.58 or self.audio_features.bass >= 0.62:
                self.pro_effects.strobe.set_mode(
                    ProStrobeMode.CONTINUOUS,
                    frequency=20.0,
                    intensity=1.0,
                )
            else:
                self.pro_effects.strobe.set_mode(
                    ProStrobeMode.OFF,
                    frequency=0.1,
                    intensity=0.0,
                )
            return
        self.pro_effects.strobe.set_mode(
            ProStrobeMode.OFF,
            frequency=0.1,
            intensity=0.0,
        )

    def _rebuild_set_section(self, section_name: str):
        """Set rebuilt busker section and sync section manager immediately.

        The sync is by comparison rather than on change, because the manager
        starts at `unknown` and can be put back there by a song change: the
        detector may legitimately hold one section for minutes, and a
        change-triggered sync would leave everything reading the manager —
        the cue templates and the decision engine — looking at `unknown` for
        all of it.
        """
        section_name = (section_name or "verse").lower()
        if section_name != self._rebuild_section:
            self._rebuild_section = section_name
            self._rebuild_section_changed_at = self.time
            # Read a little early: the detector commits on the bar line give or
            # take an analysis block, and a commit read as the tail of the
            # previous bar would start every phrase a bar late.
            self._phrase_origin_bar = self._phrase_bar(_PHRASE_BAR_LEAD)
        if (
            self._pro_lighting_enabled
            and self.section_manager.current_section.value != section_name
        ):
            from ..lighting.section_manager import SongSection
            section_map = {
                "verse": SongSection.VERSE,
                "buildup": SongSection.BUILDUP,
                "chorus": SongSection.CHORUS,
                "drop": SongSection.DROP,
                "breakdown": SongSection.BREAKDOWN,
            }
            s = section_map.get(section_name, SongSection.VERSE)
            self.section_manager.trigger_section(s, immediate=True)

    def _phrase_bar(self, lead: float = 0.0) -> Optional[int]:
        """The bar the locked clock is in, or None without a lock."""
        if not self._clock_locked:
            return None
        bars = self._beat_clock_bars()
        if not (-1.0e9 < bars < 1.0e9):
            return None
        return int(math.floor(bars + lead))

    def _phrase_index(self) -> Optional[int]:
        """Which phrase the clock is in, counted from the last section change.

        None without a locked clock, which means no phrase grid: callers fall
        back to their time-based behaviour. The origin is the bar the section
        changed on; with no section change yet heard on this clock, it is the
        first bar asked about.
        """
        bar = self._phrase_bar()
        if bar is None:
            return None
        if self._phrase_origin_bar is None:
            self._phrase_origin_bar = bar
        # A commit read early sits just before its own origin; it is phrase 0.
        return max(0, (bar - self._phrase_origin_bar) // _PHRASE_BARS)

    def _rebuild_downbeat_event(self) -> bool:
        """Is the beat the analyser is reporting right now a usable bar line?

        The analyser only counts beats, and its count is seeded by whichever
        onset it happened to detect first, so which beat is beat one has to come
        from the locked clock instead. `_beat_clock_bars` is aligned to the
        voted downbeat and good to a few milliseconds, so rounding its fraction
        to the nearest quarter identifies the beat within the bar even though
        the analyser's event arrives up to one analysis block late.

        Every bar line is offered rather than only four-bar phrase lines.
        Skipping bars to hold out for a phrase leaves a two-bar gap, and the
        detector will not wait more than one and a half bars for a boundary, so
        holding out is what puts a commit *off* the grid rather than on a better
        one.

        Without a lock there is no trustworthy bar line at all, so nothing is
        offered and the detector falls back to that bounded wait.
        """
        if not self._clock_locked:
            return False
        bars = self._beat_clock_bars()
        if not (-1.0e9 < bars < 1.0e9):
            return False
        return int(math.floor((bars % 1.0) * 4.0 + 0.5)) % 4 == 0

    def _strobe_cap_hz(self) -> float:
        """The venue's flash-rate cap, or zero if it cannot be read as one."""
        try:
            cap = float(self.config.strobe_hz_cap)
        except (TypeError, ValueError):
            return 0.0
        return cap if cap > 0.0 else 0.0

    def _strobe_grid_hz(self, target_hz: float, duty: float) -> float:
        """Grid rate that delivers no more flashes per second than the cap.

        Returns 0.0 when the cap leaves no room, and 0.0 means *no strobe*:
        the flash predicate is permanently true at zero, so a caller that ran
        the grid anyway would hold the rig at full white.
        """
        try:
            allowed = self._strobe_cap_hz() - float(duty) - _STROBE_HZ_STRICT_MARGIN
            target = float(target_hz)
        except (TypeError, ValueError):
            return 0.0
        if not (allowed > 0.0):
            return 0.0
        return min(allowed, max(0.0, target))

    def _rebuild_update_intent(self, delta_time: float):
        """Advance the live section detector and publish its answer.

        Classification, hysteresis, minimum hold, bar-line commit and the drop
        refractory all live in `StreamingSectionDetector`; this supplies the
        frame's features, the bar line and the engine clock, and does nothing
        else. Thresholds are not restated here: the detector measures every
        feature against its own running centre and spread, so it is scale free
        and a threshold written against absolute energy would undo that.

        `now` is the engine's own clock rather than the wall clock. The
        detector's filters advance on `delta_time` while its dwell, hold and
        refractory timers used to read `time.time()`, so any caller stepping the
        engine at other than real speed - the demo endpoint's fixed 1/60 per
        HTTP tick, an offline render - folded minutes of audio into a detector
        that believed it was still warming up.

        The bar clock is handed over as well. It feeds the drop predictor only -
        the section returned here is the same one it would be without it - and
        without it there is no grid to project a drop onto and no anticipation
        at all.

        Runs at 60 fps and must not raise: keeping the previous section is
        always better than dropping the frame.
        """
        bar_seconds = self._clock_period * 4.0
        try:
            section = self.section_manager.update_section_from_audio(
                delta_time,
                energy=float(self.audio_features.energy),
                bass=float(self.audio_features.bass),
                spectral_flux=float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0),
                is_beat=bool(self.audio_features.is_beat),
                beat_number=int(getattr(self.audio_state, "beat_number", 0) or 0),
                bpm=float(self._smoothed_movement_bpm),
                is_downbeat_event=self._rebuild_downbeat_event(),
                programme_level=self._programme_level,
                now=float(self.time),
                bar_position=self._beat_clock_bars(),
                clock_locked=bool(self._clock_locked),
                clock_confidence=float(self._clock_conf),
                bar_seconds=bar_seconds,
            )
        except Exception:
            # No section this frame means no candidate either, and a dip left
            # armed by a frame that never finished would hold the rig down for
            # as long as the fault lasted.
            self._drop_dip = 0.0
            self._drop_armed = False
            self._drop_confirm_held = 0.0
            return

        self._drop_anticipation_update(delta_time, section, bar_seconds)

        # The strobe window stays where it always was: on the detector's own drop
        # decision. The anticipation path opens a sustained level and nothing
        # else, so a projection that turns out to be wrong cannot place an accent.
        if section == "drop" and self._rebuild_section != "drop":
            self._rebuild_drop_until = self.time + _SECTION_DROP_STROBE_S
        self._rebuild_set_section(section)

    def _drop_anticipation_update(self, delta_time: float, section: str, bar_seconds: float):
        """Act on the projected drop: dip on speculation, commit on confirmation.

        Runs at 60 fps and must not raise. Every failure path here leaves the dip
        at zero and the hit in the past, which is exactly the behaviour that
        predates the predictor: the reactive detector still names the drop and
        the render still responds to it, only later.
        """
        try:
            self._drop_anticipation_step(delta_time, section, bar_seconds)
        except Exception:
            self._drop_dip = 0.0
            self._drop_armed = False
            self._drop_confirm_held = 0.0
            self._drop_hit_until = -999.0

    def _drop_anticipation_step(self, delta_time: float, section: str, bar_seconds: float):
        dt = float(delta_time) if delta_time else 0.0
        if not (0.0 < dt <= 0.25):
            dt = 1.0 / 60.0
        bar_s = float(bar_seconds)
        if not (0.8 <= bar_s <= 5.0):
            bar_s = 4.0 * 60.0 / 128.0
        now = float(self.time)

        energy = max(0.0, min(1.0, float(self.audio_features.energy)))
        bass = max(0.0, min(1.0, float(self.audio_features.bass)))
        self._drop_bass_ref = max(bass, self._drop_bass_ref - _DROP_BASS_REF_DECAY * dt)
        self._drop_energy_ref = max(energy, self._drop_energy_ref - _DROP_ENERGY_REF_DECAY * dt)

        # An anticipated window is open on the strength of evidence the detector
        # has not seen. Ask again every frame: a build that impacts and then
        # breaks down stops being a drop long before the window would have run
        # out, and holding the rig up through the breakdown is the loudest way to
        # be wrong.
        if now < self._drop_hit_until and not self._drop_sustains():
            self._drop_hit_until = -999.0

        # Nothing holds the rig back through a drop, whether this path called it
        # or the detector did.
        if now < self._drop_hit_until or (section or "").lower() == "drop":
            self._drop_dip = 0.0
            self._drop_armed = False
            self._drop_confirm_held = 0.0
            return

        prediction = getattr(self.section_manager, "drop_prediction", None)
        seconds_to = float(getattr(prediction, "seconds_to_drop", 0.0) or 0.0)
        lead = _DROP_DIP_LEAD_BEATS * (bar_s * 0.25)
        armed = (
            prediction is not None
            and bool(getattr(prediction, "pending", False))
            and float(getattr(prediction, "confidence", 0.0) or 0.0) >= _DROP_DIP_MIN_CONFIDENCE
            and -_DROP_CONFIRM_WINDOW_S <= seconds_to <= lead
        )

        if armed:
            if not self._drop_armed:
                # Frozen at arming, so the drop's own low end and its own level
                # cannot raise the bar they have to clear.
                self._drop_armed = True
                self._drop_confirm_held = 0.0
                self._drop_confirm_gate = max(
                    _DROP_CONFIRM_BASS_FLOOR,
                    self._drop_bass_ref + _DROP_CONFIRM_BASS_STEP,
                    self._drop_bass_ref + (1.0 - self._drop_bass_ref) * _DROP_CONFIRM_HEADROOM,
                )
                self._drop_confirm_energy_gate = self._drop_energy_ref * _DROP_CONFIRM_ENERGY_STEP
            if abs(seconds_to) <= _DROP_CONFIRM_WINDOW_S and self._drop_confirms(energy, bass):
                self._drop_confirm_held += dt
            else:
                self._drop_confirm_held = 0.0
            if self._drop_confirm_held >= _DROP_CONFIRM_DWELL_S:
                self._drop_commit(now)
                return
            # Past the projected instant the dip has already bought all the
            # contrast it is going to; from there it is only a hole in the light,
            # so it starts being given back at the instant rather than at the end
            # of the confirmation window.
            if seconds_to >= 0.0:
                ramp = (lead - seconds_to) / lead
            else:
                ramp = 1.0 + seconds_to / _DROP_CONFIRM_WINDOW_S
            target = _DROP_DIP_DEPTH * max(0.0, min(1.0, ramp))
        else:
            self._drop_armed = False
            self._drop_confirm_held = 0.0
            target = 0.0

        if target >= self._drop_dip:
            onset = _DROP_DIP_DEPTH / max(0.05, _DROP_DIP_ONSET_LEAD_BEATS * bar_s * 0.25)
            self._drop_dip = min(target, self._drop_dip + onset * dt)
        else:
            recover = _DROP_DIP_DEPTH / max(0.5, _DROP_DIP_RECOVER_BARS * bar_s)
            self._drop_dip = max(target, self._drop_dip - recover * dt)

    def _drop_sustains(self) -> bool:
        """Is the audio still behaving like the drop this path committed to?

        Cheap and level-free on purpose: it is asked on every frame of the
        anticipated window, and the one thing a build/impact/breakdown stops
        doing immediately is being loud in its own normalised terms.
        """
        programme = self._programme_level
        if programme is None:
            return False
        return float(programme) >= _DROP_CONFIRM_MIN_PROGRAMME

    def _drop_confirms(self, energy: float, bass: float) -> bool:
        """Has the audio agreed that the projected drop actually landed?

        Three refusals, and a mispredicted downbeat trips all of them: the low
        end the build filtered out has to be back, the moment has to be louder
        than this build has been, and the programme has to be loud in its own
        normalised terms. Every one is a ratio or a normalised measure, so the
        answer does not move with the fader.
        """
        if energy <= 0.0 or energy < self._drop_confirm_energy_gate:
            return False
        if not self._drop_sustains():
            return False
        return bass >= self._drop_confirm_gate

    def _drop_commit(self, now: float):
        """The audio agreed: release the dip and open the sustained drop level.

        Deliberately not the strobe window. `_rebuild_drop_until` is what arms
        the white accents, and that stays with the detector, which weighs level,
        fast-band z-score, rise and its own refractory against this track's
        running centre and spread. Being wrong here costs a second of extra
        light; being wrong there costs a flash in someone's face.
        """
        self._drop_dip = 0.0
        self._drop_armed = False
        self._drop_confirm_held = 0.0
        self._drop_hit_until = now + _SECTION_DROP_STROBE_S

    def _reset_drop_anticipation(self):
        """Forget the candidate; a new song is a new grid."""
        self._drop_dip = 0.0
        self._drop_armed = False
        self._drop_confirm_gate = 1.0
        self._drop_confirm_energy_gate = 1.0
        self._drop_confirm_held = 0.0
        self._drop_bass_ref = 0.0
        self._drop_energy_ref = 0.0
        self._drop_hit_until = -999.0
        self._drop_bed_mix = 0.0
        try:
            self.section_manager.reset_drop_prediction()
        except Exception:
            pass

    def _update_fixtures_rebuild(self, delta_time: float):
        """Scratch-built pro busker rendering pipeline (single source of truth)."""
        all_fixtures = self.fixtures.get_fixtures_in_group("all")
        total = len(all_fixtures)
        if total <= 0:
            self._fixture_state_snapshot = []
            return

        section = (self._rebuild_section or "verse").lower()
        bpm = max(60.0, min(190.0, float(self._smoothed_movement_bpm)))
        energy = max(0.0, min(1.0, float(self.audio_features.energy)))
        bass = max(0.0, min(1.0, float(self.audio_features.bass)))
        high = max(0.0, min(1.0, float(self.audio_features.high)))
        flux = float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0)
        beat = bool(self.audio_features.is_beat)
        beats = float(self._clock_beats)
        beat_phase = float(self.beat_phase)

        def _is_motion_capable(fx: Fixture) -> bool:
            channels = getattr(fx, "channels", {}) or {}
            can_pan = "pan" in channels and _travel(fx, "pan_range") > 0.0
            can_tilt = "tilt" in channels and _travel(fx, "tilt_range") > 0.0
            if not (can_pan or can_tilt):
                return False
            ftype = str(getattr(fx, "fixture_type", "") or "").lower()
            if ftype in {"mover", "moving_head", "beam", "spot", "wash", "profile", "hybrid"}:
                return True
            return can_pan and can_tilt

        movers = [f for f in all_fixtures if _is_motion_capable(f)]
        if not movers:
            movers = all_fixtures

        # Use all truss rows so every motion-capable fixture participates.
        row_map: Dict[float, List[Fixture]] = {}
        for f in movers:
            row_map.setdefault(round(float(getattr(f, "z", 0.0)), 2), []).append(f)
        row_keys = sorted(row_map.keys())
        selected_rows: Dict[int, List[Fixture]] = {}
        for ridx, rk in enumerate(row_keys):
            selected_rows[ridx] = sorted(
                row_map[rk],
                key=lambda x: (float(getattr(x, "x", 0.0)), str(getattr(x, "id", ""))),
            )

        # Precompute stable membership so paired fixtures always get distinct phase slots.
        row_membership: Dict[str, Tuple[int, int, int]] = {}
        for row_i, row_fixtures in selected_rows.items():
            count = len(row_fixtures)
            for local_i, fx in enumerate(row_fixtures):
                row_membership[str(fx.id)] = (row_i, local_i, count)

        # Stable fixture order for MA-style linear chase.
        chase_order: List[Fixture] = []
        for ridx in sorted(selected_rows.keys()):
            chase_order.extend(selected_rows[ridx])
        chase_index = {fx.id: idx for idx, fx in enumerate(chase_order)}

        # Movement patterns are beat-locked and section-aware, with circle-heavy busker looks.
        bar_clock = int(math.floor(self._beat_clock_bars()))
        section_pattern_pool = {
            "breakdown": ["pan_wave", "tilt_circle", "circle"],
            "verse": ["tilt_cross", "circle", "pan_wave", "figure8"],
            "buildup": ["tilt_circle", "circle", "figure8", "odd_even"],
            "chorus": ["circle", "tilt_circle", "figure8", "pan_wave"],
            "drop": ["tilt_circle", "circle", "odd_even", "figure8"],
        }
        pattern_pool = section_pattern_pool.get(section, ["tilt_cross", "circle", "pan_wave", "figure8", "odd_even"])
        style_look = _CLUB_STYLE_LOOKS.get(self._club_style or "")
        if style_look and style_look["patterns"]:
            narrowed = [p for p in pattern_pool if p in style_look["patterns"]]
            if len(narrowed) >= 2:
                pattern_pool = narrowed
        style_speed = float(style_look["speed"]) if style_look else 1.0
        style_amp = float(style_look["amp"]) if style_look else 1.0
        phrase = self._phrase_index()
        if phrase is None:
            # No phrase grid without a locked clock: rotate every few bars.
            target_pattern = pattern_pool[bar_clock % len(pattern_pool)]
            if bar_clock >= self._rebuild_pattern_hold_until_bar:
                if target_pattern != self._rebuild_active_pattern:
                    self._rebuild_active_pattern = target_pattern
                    self._rebuild_style_speed = style_speed
                    self._rebuild_style_amp = style_amp
                hold_bars = max(1, int(getattr(self.config, "major_change_min_bars", 2) or 2))
                self._rebuild_pattern_hold_until_bar = bar_clock + hold_bars
        elif (section, phrase) != self._rebuild_pattern_key:
            # A new section or a new phrase: the next movement in this section's
            # pool, never the one already running.
            self._rebuild_pattern_key = (section, phrase)
            for _ in range(len(pattern_pool)):
                self._rebuild_pattern_index += 1
                candidate = pattern_pool[self._rebuild_pattern_index % len(pattern_pool)]
                if candidate != self._rebuild_active_pattern or len(pattern_pool) == 1:
                    break
            self._rebuild_active_pattern = candidate
            self._rebuild_style_speed = style_speed
            self._rebuild_style_amp = style_amp
        pattern = self._rebuild_active_pattern

        pan_amp = 22.0
        tilt_amp = 12.0
        move_speed = 0.45
        base_floor = 0.62
        chase_floor = 0.26
        chase_steps_per_beat = 1.5
        chase_heads = 2
        chase_falloff = 0.26

        if section == "breakdown":
            pan_amp = 12.0
            tilt_amp = 9.0
            move_speed = 0.28
            base_floor = 0.26
            chase_floor = 0.18
            chase_steps_per_beat = 1.0
            chase_heads = 1
            chase_falloff = 0.22
        elif section == "verse":
            pan_amp = 20.0
            tilt_amp = 14.0
            move_speed = 0.42
            base_floor = 0.68
            chase_floor = 0.24
            chase_steps_per_beat = 1.8
            chase_heads = 2
            chase_falloff = 0.24
        elif section == "buildup":
            pan_amp = 30.0
            tilt_amp = 22.0
            move_speed = 0.70
            base_floor = 0.74
            chase_floor = 0.20
            chase_steps_per_beat = 3.0
            chase_heads = 3
            chase_falloff = 0.20
        elif section == "chorus":
            pan_amp = 26.0
            tilt_amp = 19.0
            move_speed = 0.60
            base_floor = 0.78
            chase_floor = 0.22
            chase_steps_per_beat = 2.4
            chase_heads = 3
            chase_falloff = 0.22
        elif section == "drop":
            pan_amp = 34.0
            tilt_amp = 25.0
            move_speed = 0.85
            base_floor = 1.0

        # The club style's movement character, on top of the section's.
        pan_amp *= self._rebuild_style_amp
        tilt_amp *= self._rebuild_style_amp
        move_speed *= self._rebuild_style_speed

        # The drop look, whether the detector named it or the anticipation path
        # committed to it a beat earlier. It is one sustained level across the
        # whole rig with the accents as punctuation on top, not a square wave
        # between full and black; and it is still a multiple of energy, so
        # silence is still darkness.
        #
        # The rig crosses to that bed from wherever the section had it, at a
        # bounded rate. The dip exists to make this step as large as it can be,
        # and a step is not a flash, so no strobe rule sees it: without the bound
        # it is the largest luminance transient in the show and `no_strobe` does
        # nothing about it.
        drop_look = section == "drop" or self.time < self._drop_hit_until
        if drop_look:
            step = float(delta_time) if delta_time else 0.0
            if not (0.0 < step <= 0.25):
                step = 1.0 / 60.0
            self._drop_bed_mix = min(1.0, self._drop_bed_mix + _DROP_BED_RISE_PER_S * step)
        else:
            self._drop_bed_mix = 0.0
        drop_target = min(_DROP_SUSTAIN_CEILING, energy * _DROP_SUSTAIN_GAIN)
        # Never start the crossing above where it is going. On a saturated input
        # the ceiling sits below `energy x base_floor`, and a crossing that began
        # there would read as the rig dimming into the drop.
        drop_from = min(energy * base_floor, drop_target)
        drop_bed = drop_from + (drop_target - drop_from) * self._drop_bed_mix

        # Drop strobes: pure white only, gated by safety policy.
        policy = str(getattr(self.config, "accessibility_mode", "performance") or "performance").lower()
        venue_mode = str(getattr(self.config, "venue_mode", "concert") or "concert").lower()
        camera_mode = bool(getattr(self.config, "camera_mode", False))
        visibility_first_mode = venue_mode in {"theatre", "broadcast", "corporate"}
        strobe_allowed_by_policy = (policy not in {"no_strobe", "off"}) and (not camera_mode) and (not visibility_first_mode)
        strobe_enabled_runtime = bool(self.config.strobe_enabled) and strobe_allowed_by_policy
        strobe_duty = max(0.15, min(float(self.config.strobe_max_duty_cycle), 0.75))
        drop_strobe_target_freq = 22.0 if energy > 0.65 else 18.0
        drop_strobe_freq = self._strobe_grid_hz(drop_strobe_target_freq, strobe_duty)
        drop_strobe_on = (
            strobe_enabled_runtime
            and drop_strobe_freq > 0.0
            and section == "drop"
            and self.time < self._rebuild_drop_until
        )
        if drop_strobe_freq < drop_strobe_target_freq:
            self._record_safety_event(
                "strobe_frequency_clamped",
                {
                    "section": section,
                    "requested_hz": round(drop_strobe_target_freq, 3),
                    "applied_hz": round(drop_strobe_freq, 3),
                    "cap_hz": round(self._strobe_cap_hz(), 3),
                },
                throttle_s=1.0,
                throttle_key="strobe_frequency_clamped_drop",
            )
        drop_strobe_flash = drop_strobe_on and ((self.time * drop_strobe_freq) % 1.0) < strobe_duty

        # Snare strobe: very short fast white bursts on bright/transient hits.
        # `high` and `flux` are measured against the programme's own level, so a brushed
        # cymbal in a ballad reads as bright as a snare in a club. The absolute floor is
        # what keeps quiet material from strobing: sparse acoustic material peaks around
        # 0.08 here, while anything a room is dancing to sits above 0.25.
        snare_trigger = (
            (section in {"verse", "buildup", "chorus", "drop"})
            and energy > ACCENT_ABSOLUTE_FLOOR
            and high > 0.58
            and flux > 0.055
            and (beat or high > 0.72)
        )
        now = self.time
        if snare_trigger and (now - self._rebuild_snare_last_trigger) > max(0.05, float(self.config.strobe_refractory_s)):
            self._rebuild_snare_last_trigger = now
            snare_burst_s = min(0.11, max(0.05, float(self.config.strobe_burst_max_s)))
            self._rebuild_snare_strobe_until = now + snare_burst_s
        snare_strobe_target_freq = 30.0 if high > 0.72 else 24.0
        snare_strobe_freq = self._strobe_grid_hz(snare_strobe_target_freq, strobe_duty)
        snare_strobe_on = (
            strobe_enabled_runtime
            and snare_strobe_freq > 0.0
            and (not drop_strobe_on)
            and (now < self._rebuild_snare_strobe_until)
        )
        if snare_strobe_freq < snare_strobe_target_freq:
            self._record_safety_event(
                "strobe_frequency_clamped",
                {
                    "section": section,
                    "requested_hz": round(snare_strobe_target_freq, 3),
                    "applied_hz": round(snare_strobe_freq, 3),
                    "cap_hz": round(self._strobe_cap_hz(), 3),
                },
                throttle_s=1.0,
                throttle_key="strobe_frequency_clamped_snare",
            )
        snare_strobe_flash = snare_strobe_on and ((now * snare_strobe_freq) % 1.0) < strobe_duty

        strobe_on = drop_strobe_on or snare_strobe_on
        strobe_flash = drop_strobe_flash or snare_strobe_flash

        # Hold base color for musical phrases so mood color is stable: a new
        # colour on a section change or a phrase line, and none at all while a
        # DJ is blending into the next record (that gets one when it lands).
        if phrase is None:
            recolour = self.time >= self._rebuild_color_hold_until
        else:
            recolour = (section, phrase) != self._rebuild_color_key
        if self._track_transition > 0.0 and self._rebuild_color_key is not None:
            recolour = False
        if recolour:
            self._rebuild_color_key = (section, phrase) if phrase is not None else None
            palette_color = self.color.get_color(self.audio_features, 0, 0.0)
            emotional_color = self._rebuild_get_emotional_color(section)
            section_emotion_mix = {
                "breakdown": 0.66,
                "verse": 0.36,
                "buildup": 0.48,
                "chorus": 0.56,
                "drop": 0.62,
            }.get(section, 0.42)
            self._rebuild_base_color = palette_color.blend(emotional_color, section_emotion_mix)
            phrase_s = max(2.4, min(6.0, (8.0 * 60.0) / max(60.0, bpm)))
            self._rebuild_color_hold_until = self.time + phrase_s

        # Gentle continuous blend toward current emotional target avoids abrupt color jumps.
        live_emotional = self._rebuild_get_emotional_color(section)
        self._rebuild_base_color = self._rebuild_base_color.blend(live_emotional, 0.018)
        base_color = self._rebuild_base_color
        white_accent = 0.0
        if not strobe_on:
            # Decay persistent accent envelope (lets bass hits "hang" briefly).
            self._white_accent_level = max(0.0, self._white_accent_level - max(0.0, float(delta_time)) * 1.9)
            if beat and section in {"verse", "buildup", "chorus"}:
                white_accent = 0.16 if section == "buildup" else 0.10
            # Bass-driven punch: more white on hard low-end hits.
            if bass >= 0.62:
                bass_punch = (min(1.0, bass) - 0.62) / 0.38
                bass_hit = 0.10 + 0.24 * bass_punch
                if beat:
                    bass_hit += 0.08
                self._white_accent_level = max(self._white_accent_level, min(0.42, bass_hit))
            # Extra "pro busker" white lift on high-energy movement peaks.
            # Keeps color identity while adding punch in energetic phrases.
            if section in {"buildup", "chorus", "drop"} and energy > 0.68:
                motion_peak = 0.5 + 0.5 * math.sin(2.0 * math.pi * beat_phase)
                white_accent += 0.04 + 0.10 * motion_peak
            white_accent += self._white_accent_level
            white_accent = max(0.0, min(0.40, white_accent))

        chase_active = section in {"verse", "buildup", "chorus"}
        chase_head = -1
        chase_dir = 1
        if chase_active and chase_order:
            chase_len = len(chase_order)
            chase_tick = int(math.floor(beats * chase_steps_per_beat))
            # Reverse direction every 2 bars for a busker-style sweep/bounce feel.
            chase_dir = -1 if (bar_clock % 4) >= 2 else 1
            chase_head = chase_tick % chase_len if chase_dir > 0 else (chase_len - 1 - (chase_tick % chase_len))

        snapshot = []
        for i, fixture in enumerate(all_fixtures):
            ftype = str(getattr(fixture, "fixture_type", "") or "").lower()
            is_mover = _is_motion_capable(fixture)

            # Symmetric BPM movement around home look (pan=0, tilt=0/down-home).
            if is_mover:
                ridx, local_idx, row_count = row_membership.get(str(fixture.id), (0, 0, 1))

                # Global phase slot prevents "every other pair looks static" artifacts.
                global_idx = chase_index.get(fixture.id, local_idx)
                global_count = max(1, len(chase_order))
                global_frac = (global_idx / max(1, global_count - 1)) if global_count > 1 else 0.5
                frac = global_frac
                row_sign = -1.0 if ridx % 2 == 0 else 1.0
                phase = ((beats * move_speed) + frac) % 1.0

                pan = 0.0
                tilt = 0.0
                if pattern == "tilt_cross":
                    pan = row_sign * (8.0 + pan_amp * (2.0 * frac - 1.0)) * math.sin(2.0 * math.pi * phase)
                    tilt = tilt_amp * math.sin(2.0 * math.pi * phase + (0.0 if ridx == 0 else math.pi))
                elif pattern == "pan_wave":
                    pan = row_sign * pan_amp * math.sin(2.0 * math.pi * phase)
                    tilt = tilt_amp * (0.42 + 0.33 * math.cos(2.0 * math.pi * phase))
                elif pattern == "circle":
                    pan = row_sign * pan_amp * math.sin(2.0 * math.pi * phase)
                    tilt = tilt_amp * (0.25 + 0.75 * math.cos(2.0 * math.pi * phase))
                elif pattern == "tilt_circle":
                    pan = row_sign * (pan_amp * 0.65) * math.sin(2.0 * math.pi * phase)
                    tilt = (tilt_amp * 1.25) * (0.15 + 0.85 * math.cos(2.0 * math.pi * phase))
                elif pattern == "figure8":
                    pan = row_sign * pan_amp * math.sin(2.0 * math.pi * phase)
                    tilt = tilt_amp * math.sin(4.0 * math.pi * phase)
                else:  # odd_even
                    parity_phase = phase if (local_idx % 2 == 0) else (phase + 0.5)
                    pan = row_sign * pan_amp * math.sin(2.0 * math.pi * parity_phase)
                    tilt = tilt_amp * math.cos(2.0 * math.pi * parity_phase)

                fixture.pan = max(-270.0, min(270.0, float(pan)))
                fixture.tilt = max(-135.0, min(135.0, float(tilt)))
            else:
                fixture.pan = 0.0
                fixture.tilt = 0.0

            # Dimmer policy: chase in verse/buildup/chorus, strobe on drop, calm breakdown.
            # All paths scale from zero when no audio — beams form on activation.
            if section == "breakdown":
                dim = energy * 0.40
            elif drop_look:
                dim = 1.0 if strobe_flash else drop_bed
            elif snare_strobe_on:
                dim = 1.0 if snare_strobe_flash else energy * 0.16
            elif chase_active and is_mover and chase_head >= 0 and fixture.id in chase_index:
                idx = chase_index[fixture.id]
                chase_len = max(1, len(chase_order))
                # Multi-head chase with short tails for stronger fixture-to-fixture bumps.
                best_peak = 0.0
                spacing = max(1, chase_len // max(1, chase_heads))
                for h in range(max(1, chase_heads)):
                    head = (chase_head + (h * spacing * chase_dir)) % chase_len
                    dist = min((idx - head) % chase_len, (head - idx) % chase_len)
                    peak = max(0.0, 1.0 - dist * chase_falloff)
                    if peak > best_peak:
                        best_peak = peak
                beat_bump = 0.88 + 0.22 * (0.5 + 0.5 * math.sin(2.0 * math.pi * beat_phase))
                dim = min(1.0, best_peak * beat_bump * energy)
            else:
                dim = energy * base_floor
            # The speculative dip, applied as a fraction of whatever the frame
            # was going to be so a dip at zero energy is still zero.
            dim *= 1.0 - self._drop_dip
            fixture.dimmer = max(0.0, min(1.0, dim))
            audience_cap = max(0.0, min(1.0, float(self.config.audience_intensity_cap)))
            if fixture.dimmer > audience_cap:
                self._record_safety_event(
                    "audience_intensity_clamped",
                    {
                        "fixture_id": fixture.id,
                        "requested": round(float(fixture.dimmer), 3),
                        "applied": round(float(audience_cap), 3),
                    },
                    throttle_s=1.0,
                    throttle_key="audience_intensity_clamped",
                )
            fixture.dimmer = min(fixture.dimmer, audience_cap)

            # Optional "move-in-brightness restraint" policy for cleaner live looks.
            if (
                not self.config.movement_when_bright
                and (not strobe_on)
                and fixture.dimmer >= float(self.config.bright_movement_dimmer_threshold)
            ):
                cap = max(0.0, float(self.config.bright_movement_pan_tilt_cap_deg))
                fixture.pan = max(-cap, min(cap, fixture.pan))
                fixture.tilt = max(-cap, min(cap, fixture.tilt))

            # Color policy: stable mood color + beat accents, pure white only on strobe flash.
            if strobe_on and strobe_flash:
                fixture.red = 1.0
                fixture.green = 1.0
                fixture.blue = 1.0
            else:
                fixture.red = max(0.0, min(1.0, base_color.r * (1.0 - white_accent) + white_accent))
                fixture.green = max(0.0, min(1.0, base_color.g * (1.0 - white_accent) + white_accent))
                fixture.blue = max(0.0, min(1.0, base_color.b * (1.0 - white_accent) + white_accent))
                # Apply section narrative shaping (saturation/whiteness/accent behavior).
                self._apply_palette_narrative_to_fixture(fixture, i, section)

            snapshot.append({
                'id': fixture.id,
                'dmx_address': int(getattr(fixture, 'dmx_address', 0) or 0),
                'universe': int(getattr(fixture, 'universe', 0) or 0),
                'pan': fixture.pan,
                'tilt': fixture.tilt,
                'dimmer': fixture.dimmer,
                'r': fixture.red,
                'g': fixture.green,
                'b': fixture.blue,
            })
        self._fixture_state_snapshot = snapshot

    # Audio older than this is treated as lost.
    AUDIO_STALE_S = _AUDIO_LOSS_AFTER_S
    # Where the analysed levels settle while the feed is gone, for renderers
    # that read them directly: a calm, lit room rather than a dark one (the
    # cable may be the only thing that stopped) and rather than the last beat
    # replayed for ever. The rebuild renderer shows the ambient hold instead.
    AUDIO_IDLE_LEVEL = 0.25
    AUDIO_IDLE_SETTLE_S = 3.0

    @property
    def audio_age(self) -> Optional[float]:
        """Seconds since the last audio update, or None before any arrived."""
        if self._last_audio_t is None:
            return None
        return max(0.0, self.time - self._last_audio_t)

    def _settle_if_audio_lost(self, delta_time: float) -> None:
        """Stop following music that is no longer arriving, on every renderer.

        Nothing refreshed the audio state when the feed died (capture thread
        gone, cable out, sender crashed), so the show kept dancing to the last
        chunk all night: energy frozen, and is_beat stuck on, which also counted
        a new bar every frame and broke every bar-based hold.
        """
        age = self.audio_age
        if age is None or age < self.AUDIO_STALE_S:
            return
        self.audio_features.is_beat = False
        self.audio_features.beat_intensity = 0.0
        self.audio_state.is_beat = False
        # A room that never heard music before the feed went has nothing to
        # hold, and stays dark, the same rule as the ambient hold.
        idle = self.AUDIO_IDLE_LEVEL if self._music_heard else 0.0
        pull = min(1.0, max(0.0, float(delta_time or 0.0)) / self.AUDIO_IDLE_SETTLE_S)
        for target in (self.audio_features, self.audio_state):
            for band in ("energy", "bass", "mid", "high"):
                value = float(getattr(target, band, 0.0) or 0.0)
                setattr(target, band, value + (idle - value) * pull)
        if hasattr(self.audio_state, "spectral_flux"):
            self.audio_state.spectral_flux = 0.0

    def _audio_loss_check(self) -> None:
        """Notice audio that was playing and has stopped arriving at all.

        Only after music has been heard: a rig with no audio source yet, or one
        the operator stopped, has nothing to hold. Only when nothing arrives:
        silence that keeps arriving is music that stopped, and stays dark.
        """
        if self._audio_lost or not self._music_heard or self._last_audio_t is None:
            return
        if (self.time - self._last_audio_t) < _AUDIO_LOSS_AFTER_S:
            return
        self._audio_lost = True
        logger.warning(
            "No audio for %.1f s after music was playing; holding an ambient look",
            self.time - self._last_audio_t,
        )
        # The last analysis frame is stale. Nothing may fire from it: no beat,
        # no accent window, no drop dip left half applied.
        self.audio_features.is_beat = False
        self.audio_state.is_beat = False
        self._rebuild_drop_until = -999.0
        self._rebuild_snare_strobe_until = -999.0
        self._drop_hit_until = -999.0
        self._drop_dip = 0.0
        self._drop_armed = False

    def _apply_ambient_hold(self, delta_time: float) -> None:
        """Cross the rendered frame to the ambient look while audio is lost.

        The look is the song's current colour at a fixed low level, with movers
        drifting slowly around home: what an operator would leave up while the
        DJ fixes a cable. It fades in over `_AMBIENT_FADE_IN_S` and back out over
        `_AMBIENT_FADE_OUT_S` once audio returns. Blackout and the grand master
        still apply on top, at the render step.
        """
        dt = float(delta_time) if delta_time else 0.0
        if not (0.0 < dt <= 0.25):
            dt = 1.0 / 60.0
        if self._audio_lost:
            self._ambient_mix = min(1.0, self._ambient_mix + dt / _AMBIENT_FADE_IN_S)
        else:
            self._ambient_mix = max(0.0, self._ambient_mix - dt / _AMBIENT_FADE_OUT_S)
        mix = self._ambient_mix
        if mix <= 0.0:
            return

        fixtures = self.fixtures.get_fixtures_in_group("all")
        base = self._rebuild_base_color
        audience_cap = max(0.0, min(1.0, float(self.config.audience_intensity_cap)))
        level = min(_AMBIENT_HOLD_LEVEL, audience_cap)
        drift = 2.0 * math.pi * _AMBIENT_DRIFT_HZ * self.time
        count = max(1, len(fixtures))
        by_id = {}
        for i, fixture in enumerate(fixtures):
            offset = 2.0 * math.pi * i / count
            fixture.dimmer = max(0.0, min(1.0, fixture.dimmer + (level - fixture.dimmer) * mix))
            fixture.red = fixture.red + (base.r - fixture.red) * mix
            fixture.green = fixture.green + (base.g - fixture.green) * mix
            fixture.blue = fixture.blue + (base.b - fixture.blue) * mix
            if "pan" in (getattr(fixture, "channels", {}) or {}):
                pan = _AMBIENT_PAN_DEG * math.sin(drift + offset)
                tilt = _AMBIENT_TILT_DEG * math.sin(0.5 * drift + offset)
                fixture.pan = fixture.pan + (pan - fixture.pan) * mix
                fixture.tilt = fixture.tilt + (tilt - fixture.tilt) * mix
            by_id[fixture.id] = fixture
        for entry in self._fixture_state_snapshot or []:
            fixture = by_id.get(entry.get("id"))
            if fixture is None:
                continue
            entry.update(
                pan=fixture.pan, tilt=fixture.tilt, dimmer=fixture.dimmer,
                r=fixture.red, g=fixture.green, b=fixture.blue,
            )

    @property
    def audio_input_lost(self) -> bool:
        """True while music has stopped arriving and the ambient look holds."""
        return bool(self._audio_lost)

    def audio_input_stopped(self) -> None:
        """The operator stopped the audio input on purpose: hold nothing.

        Without this, stopping capture from the UI would read as a lost cable
        and light the room two seconds later. The last analysis frame is
        replaced with silence too, so the rig does not keep rendering it.
        """
        try:
            self.update_audio()
        except Exception:
            pass
        self._music_heard = False
        self._last_audio_t = None
        self._audio_lost = False
        self._ambient_mix = 0.0
        # Whatever plays next may come from another input at another level.
        self.decision.reset_dynamics()

    def _rebuild_get_emotional_color(self, section: str) -> RGB:
        """Return mood color from valence/arousal with section-aware warmth/coolth shaping."""
        v = max(0.0, min(1.0, float(self.audio_features.valence)))
        a = max(0.0, min(1.0, float(self.audio_features.arousal)))

        calm_sad = RGB(0.24, 0.22, 0.48)      # cool violet
        calm_happy = RGB(0.30, 0.56, 0.94)    # airy blue
        hype_sad = RGB(0.92, 0.22, 0.34)      # tense red
        hype_happy = RGB(0.98, 0.52, 0.20)    # euphoric amber

        low = calm_sad.blend(calm_happy, v)
        high = hype_sad.blend(hype_happy, v)
        mood = low.blend(high, a)

        section = (section or "verse").lower()
        if section in {"breakdown", "bridge"}:
            return mood.blend(RGB(0.85, 0.88, 1.0), 0.14)
        if section in {"buildup"}:
            return mood.blend(RGB(1.0, 0.62, 0.26), 0.08)
        if section in {"drop", "chorus"}:
            return mood.blend(RGB(1.0, 0.92, 0.86), 0.05)
        return mood

    def _apply_clocked_chase_pattern(self, chase_intensity: float = 0.0):
        """Apply deterministic, in-order fixture chases for non-reactive busking mode."""
        bars = max(0, int(getattr(self.audio_state, "bars_elapsed", 0) or 0))
        stride = max(4, int(self.config.movement_rotation_bars or 16) // 2)
        idx = (bars // stride) % len(self._clocked_chase_cycle)

        direction_name, speed_name, width, tail, intensity = self._clocked_chase_cycle[idx]
        from ..lighting.pro_effects import ChaseDirection, ChaseSpeed

        direction_map = {
            "forward": ChaseDirection.FORWARD,
            "backward": ChaseDirection.BACKWARD,
            "bounce": ChaseDirection.BOUNCE,
            "center_out": ChaseDirection.CENTER_OUT,
        }
        speed_map = {
            "quarter": ChaseSpeed.QUARTER_NOTE,
            "eighth": ChaseSpeed.EIGHTH_NOTE,
            "half": ChaseSpeed.HALF_NOTE,
            "whole": ChaseSpeed.WHOLE_NOTE,
        }

        idx_changed = idx != self._clocked_chase_active_index
        if idx_changed:
            self._clocked_chase_active_index = idx
            self.pro_effects.chase.set_params(
                direction=direction_map.get(direction_name, ChaseDirection.FORWARD),
                width=int(width),
                tail_length=int(tail),
            )
            self.pro_effects.chase.set_bpm_locked_speed(
                speed_map.get(speed_name, ChaseSpeed.QUARTER_NOTE)
            )

        target_intensity = max(0.0, min(1.0, float(chase_intensity) * float(intensity)))
        if idx_changed or abs(target_intensity - self._clocked_chase_last_intensity) > 0.01:
            self._clocked_chase_last_intensity = target_intensity
            self.pro_effects.chase.set_params(intensity=target_intensity)

    def _get_chase_bump_level(self) -> float:
        """Beat-locked bump envelope for active chase steps (keeps them alive, not static)."""
        beat_phase = float(self.beat_phase)
        # Fast peak at beat start, then smooth decay.
        if beat_phase < 0.22:
            peak = 1.0 - (beat_phase / 0.22)
            return 0.72 + 0.28 * peak
        return 0.72

    # === Phase-locked musical clock ===

    def _beat_clock_advance(self, delta_time: float):
        """Advance the musical clock by one render frame.

        Runs inside the 60 fps path and must never raise: every branch here is
        a guard against a value that would otherwise poison the whole frame.
        """
        period = self._clock_period
        if not (0.02 < period < 4.0):
            period = 60.0 / 128.0
            self._clock_period = period

        dt = delta_time if delta_time else 0.0
        if not (0.0 < dt < 1.0):
            dt = 0.0
        step = dt / period

        pending = self._clock_pending
        if pending:
            if -1.0 < pending < 1.0:
                cap = _CLOCK_MAX_SLEW * step
                absorb = max(-cap, min(cap, pending))
                self._clock_pending = pending - absorb
                self._clock_absorbed += absorb
                step += absorb
            else:
                self._clock_pending = 0.0

        beats = self._clock_beats + step
        if not (-1.0e9 < beats < 1.0e9):
            beats = 0.0
            self._clock_pending = 0.0
            self._clock_absorbed = 0.0
            self._clock_locked = False
        self._clock_beats = beats
        self.beat_phase = beats % 1.0
        self.bar_phase = ((beats - self._clock_bar_offset) * 0.25) % 1.0

    def _beat_clock_bars(self) -> float:
        """Bars elapsed on the locked clock, aligned to the detected downbeat."""
        return (self._clock_beats - self._clock_bar_offset) * 0.25

    def _beat_clock_reset(self):
        """Forget everything the clock believes; the audio stream restarted."""
        self._clock_comb[:] = 0.0
        self._clock_comb2[:] = 0.0
        self._clock_comb_norm = 1e-9
        self._clock_zp = 0j
        self._clock_zp_norm = 1e-9
        self._clock_locked = False
        self._clock_conf = 0.0
        self._clock_pending = 0.0
        self._clock_absorbed = 0.0
        self._clock_evidence = 0.0
        self._clock_challenge = 0.0
        self._clock_prev_loudness = 0.0

    def _beat_clock_observe(self, energy: float, bpm: float, is_beat: bool, beat_number: int):
        """Fold one analysis block into the musical clock.

        The engine never sees audio, only one loudness value per analysis block
        (~21 Hz). That is still far above the beat rate, so the positive
        difference of block loudness is an onset envelope, and a complex comb
        over it recovers tempo and phase to a few milliseconds — much finer than
        the block grid the analyser's own beat events are quantised to.
        """
        now = float(self.time) + (time.time() - float(self.last_update))
        if not (float(self.time) - 1.0 < now < float(self.time) + 1.0):
            now = float(self.time)

        last = self._clock_last_audio_t
        self._clock_last_audio_t = now
        if last is not None:
            gap = now - last
            if 0.004 < gap < 0.5:
                self._clock_hop += (gap - self._clock_hop) * 0.25
            elif gap <= 0.0 or gap > 2.0:
                self._beat_clock_reset()
        hop = self._clock_hop

        level = max(0.0, min(4.0, float(energy)))
        loudness = math.log1p(level * _CLOCK_LOG_GAIN)
        onset = loudness - self._clock_prev_loudness
        self._clock_prev_loudness = loudness
        if onset < 0.0:
            onset = 0.0

        t = now - (0.5 + _CLOCK_ONSET_LEAD) * hop

        if self._clock_absorbed:
            # The phase reference moved under the accumulator; rotate what it
            # already holds so the next error is measured against the new phase.
            turn = -2.0 * math.pi * self._clock_absorbed
            self._clock_zp *= complex(math.cos(turn), math.sin(turn))
            self._clock_absorbed = 0.0

        decay_comb = math.exp(-hop / _CLOCK_COMB_TAU)
        decay_phase = math.exp(-hop / _CLOCK_PHASE_TAU)
        self._clock_comb *= decay_comb
        self._clock_comb2 *= decay_comb
        self._clock_comb_norm *= decay_comb
        self._clock_zp *= decay_phase
        self._clock_zp_norm *= decay_phase

        if onset > 1e-7:
            self._clock_comb += onset * np.exp(-2j * math.pi * _CLOCK_CAND_F * t)
            self._clock_comb2 += onset * np.exp(-4j * math.pi * _CLOCK_CAND_F * t)
            self._clock_comb_norm += onset
            lead = max(-hop, min(hop, t - float(self.time)))
            phi = -2.0 * math.pi * (self._clock_beats + lead / self._clock_period)
            self._clock_zp += onset * complex(math.cos(phi), math.sin(phi))
            self._clock_zp_norm += onset

        if level > 1e-4:
            self._clock_evidence = min(30.0, self._clock_evidence + hop)
        else:
            self._clock_evidence = max(0.0, self._clock_evidence - hop)

        self._clock_conf = abs(self._clock_zp) / max(1e-9, self._clock_zp_norm)
        self._beat_clock_align_bar(is_beat, beat_number)

        if self._clock_comb_norm < 1e-6 or self._clock_evidence < 0.2:
            return

        score = (np.abs(self._clock_comb) + _CLOCK_HARMONIC * np.abs(self._clock_comb2))
        score = score / self._clock_comb_norm
        weight = _CLOCK_PRIOR
        reported = float(bpm)
        tempo_confidence = self._reported_tempo_confidence
        if 40.0 <= reported <= 260.0 and not tempo_confidence:
            log_reported = math.log(reported)
            bump = np.zeros_like(weight)
            for octave in (1.0, 0.5, 2.0):
                bump += np.exp(
                    -0.5 * ((_CLOCK_LOG_CAND - (log_reported + math.log(octave))) / 0.10) ** 2
                )
            weight = weight * (1.0 + _CLOCK_REPORTED_WEIGHT * bump)
        total = score * weight
        best = int(np.argmax(total))

        # The comb owns the tempo; a confident analyser only says which metrical
        # level of it the music is at. It is consulted at the two moments the
        # clock takes a tempo (acquiring, and a challenge that succeeds) and to
        # refuse a challenger that is only another level of the tempo already
        # held. It never pulls the clock anywhere the comb does not hear a
        # pulse, so while a DJ changes tempo and the analyser lags behind, the
        # new tempo is not a relative of the old, and the comb follows it alone.
        levels = bool(tempo_confidence) and 40.0 <= reported <= 260.0
        if levels:
            best = self._beat_clock_level(best, score, reported)

        if not self._clock_locked:
            if self._clock_evidence >= _CLOCK_EVIDENCE_S and score[best] >= _CLOCK_ACQUIRE_FLOOR:
                self._beat_clock_adopt(best, t, snap=True)
            return

        held_bpm = 60.0 / self._clock_period
        here = int(np.argmin(np.abs(_CLOCK_LOG_CAND - math.log(held_bpm))))
        same_tempo_other_level = (
            levels
            and abs(math.log(held_bpm / reported)) < _CLOCK_LEVEL_MATCH
            and _clock_relative(float(_CLOCK_CAND_BPM[best]), held_bpm)
        )
        # And the other way round: the clock locked before the analyser was
        # sure (it needs a few bars) and holds a relative of the right tempo.
        corrected = here
        if (levels
                and abs(math.log(held_bpm / reported)) >= _CLOCK_LEVEL_MATCH
                and _clock_relative(reported, held_bpm)):
            corrected = self._beat_clock_level(here, score, reported)
        if corrected != here:
            challenger = corrected
        elif not same_tempo_other_level and total[best] > total[here] * _CLOCK_CHALLENGE_RATIO:
            challenger = best
        else:
            challenger = None
        if challenger is not None:
            self._clock_challenge += hop
            if self._clock_challenge >= _CLOCK_CHALLENGE_S:
                self._clock_challenge = 0.0
                self._beat_clock_adopt(challenger, t, snap=False)
                return
        else:
            self._clock_challenge = max(0.0, self._clock_challenge - hop)

        gain = (self._clock_conf - _CLOCK_CONF_MIN) / max(1e-6, _CLOCK_CONF_GOOD - _CLOCK_CONF_MIN)
        gain = max(0.0, min(1.0, gain))
        if gain <= 0.0:
            return

        error = -math.atan2(self._clock_zp.imag, self._clock_zp.real) / (2.0 * math.pi)
        error = (error + 0.5) % 1.0 - 0.5
        loop = gain * min(1.0, hop / self._clock_period)
        self._clock_pending -= error * _CLOCK_KP * loop
        period = self._clock_period * (1.0 + _CLOCK_KI * error * loop)
        self._clock_period = min(60.0 / _CLOCK_MIN_BPM, max(60.0 / _CLOCK_MAX_BPM, period))

    def _beat_clock_level(self, index: int, score: np.ndarray, reported: float) -> int:
        """The comb peak at the relative of `index` the analyser counts, if any.

        Returns `index` unchanged when no relative of its tempo is the
        analyser's, or when the comb hears too little at that relative to take
        a phase from it.
        """
        bpm = float(_CLOCK_CAND_BPM[index])
        for ratio in _CLOCK_LEVEL_RATIOS:
            target = bpm * ratio
            if not (_CLOCK_MIN_BPM <= target <= _CLOCK_MAX_BPM):
                continue
            if abs(math.log(target / reported)) >= _CLOCK_LEVEL_MATCH:
                continue
            window = np.abs(_CLOCK_LOG_CAND - math.log(target)) < _CLOCK_TEMPO_WIDTH
            if not np.any(window):
                return index
            candidates = np.flatnonzero(window)
            peak = int(candidates[np.argmax(score[candidates])])
            if score[peak] < _CLOCK_LEVEL_MIN_SHARE * score[index]:
                return index
            return peak
        return index

    def _beat_clock_adopt(self, index: int, t: float, snap: bool):
        """Take tempo and phase from the comb's best hypothesis."""
        f = float(_CLOCK_CAND_F[index])
        self._clock_period = 1.0 / f
        arg = math.atan2(self._clock_comb[index].imag, self._clock_comb[index].real)
        target = (f * t + arg / (2.0 * math.pi)) % 1.0
        here = self._clock_beats + (t - float(self.time)) / self._clock_period
        delta = (target - here + 0.5) % 1.0 - 0.5
        if snap:
            # Only while there is no lock at all, so nothing on stage is moving
            # to the old phase yet.
            self._clock_beats += delta
            self._clock_pending = 0.0
        else:
            self._clock_pending = delta
        self._clock_zp = 0j
        self._clock_zp_norm = 1e-9
        self._clock_absorbed = 0.0
        self._clock_locked = True

    def _beat_clock_align_bar(self, is_beat: bool, beat_number: int):
        """Vote the four-beat bar into line with the analyser's downbeat count.

        Deliberately indirect: the engine cannot see the audio, so which beat is
        beat one has to come from the analyser. Votes decay, and the incumbent
        has to be clearly beaten, so a run of missed or doubled beats cannot
        shift the bar line under a running phrase.
        """
        if not is_beat or not self._clock_locked:
            return
        number = int(beat_number)
        if number == self._clock_last_beat_number:
            return
        self._clock_last_beat_number = number

        index = int(math.floor(self._clock_beats + 0.3))
        slot = (index - number) % 4
        votes = self._clock_bar_votes
        for i in range(4):
            votes[i] *= 0.97
        votes[slot] += 1.0

        best = max(range(4), key=lambda i: votes[i])
        if best == self._clock_bar_offset:
            return
        if votes[best] <= votes[self._clock_bar_offset] * 2.0 + 1.0:
            return
        # Moving the bar line moves every phrase boundary with it, so it may not
        # happen inside a phrase.
        if (self._clock_beats * 0.25) - self._clock_bar_moved_at < 8.0:
            return
        self._clock_bar_offset = best
        self._clock_bar_moved_at = self._clock_beats * 0.25

    def set_dmx_callback(self, callback: Callable[[int, List[int]], None]):
        """
        Set callback for DMX output.

        Args:
            callback: Function(universe, dmx_frame) to send DMX data
        """
        self._dmx_callback = callback

    def _emit_dmx(self):
        """Send one DMX frame per universe that currently holds fixtures."""
        callback = self._dmx_callback
        if callback is None:
            return

        master = self.output_master
        get_frames = getattr(self.fixtures, "get_dmx_frames", None)
        if get_frames is None:
            callback(0, self.fixtures.get_dmx_frame(universe=0, master=master))
            return

        for universe, frame in get_frames(master=master).items():
            self._emitted_universes.add(universe)
            callback(universe, frame)

    @staticmethod
    def _manager_universes(manager: FixtureGroupManager) -> List[int]:
        """List the universes a fixture manager occupies."""
        get_universes = getattr(manager, "get_universes", None)
        if get_universes is not None:
            return list(get_universes())
        return sorted({int(getattr(f, "universe", 0) or 0) for f in manager.fixtures.values()})

    def set_fixture_manager(self, manager: FixtureGroupManager) -> None:
        """
        Replace the active rig at runtime.

        Universes the outgoing rig occupied but the incoming rig does not are
        blacked out first; without that they would never receive another frame
        and their fixtures would stay latched at their last values.
        """
        outgoing = self._manager_universes(self.fixtures)
        incoming = set(self._manager_universes(manager))

        if self._dmx_callback is not None:
            for universe in outgoing:
                if universe in incoming or universe not in self._emitted_universes:
                    continue
                self._dmx_callback(universe, [0] * 512)
                self._emitted_universes.discard(universe)

        self.fixtures = manager

        self._mib_states.clear()
        self._fixture_state_snapshot = []
        for cache in (
            self.movement._fixture_targets,
            self.movement._fixture_current,
            self.movement._random_targets,
            self.movement._fixture_positions,
            self.movement._position_phase_cache,
            self.pro_movement._current_positions,
            self.pro_movement._rate_limited_positions,
        ):
            cache.clear()

        retain = getattr(self.key_lighting, "retain_fixtures", None)
        if callable(retain):
            retain(manager.fixtures.keys())

        if self._lfo_engine is not None:
            self._lfo_engine.set_fixture_count(len(manager.fixtures))

    def set_lfo_engine(self, lfo_engine: LFOEngine):
        """
        Set the LFO engine for grandMA2-style effects.

        Args:
            lfo_engine: LFOEngine instance
        """
        self._lfo_engine = lfo_engine
        # Sync fixture count
        fixture_count = len(self.fixtures.fixtures)
        lfo_engine.set_fixture_count(fixture_count)

    def get_lfo_engine(self) -> Optional[LFOEngine]:
        """Get the LFO engine instance."""
        return self._lfo_engine

    def enable_pro_lighting(self, enabled: bool = True):
        """Enable professional lighting integration."""
        self._pro_lighting_enabled = enabled

    def set_genre(self, genre, crossfade: bool = True, pin: Optional[bool] = True):
        """Set the active genre profile.

        `pin` says how firmly genre detection may move it afterwards. True (an
        operator's choice) holds it against detection; False (a startup
        default) lets the first confident detection replace it; None leaves the
        detection gate as it is, for detection's own switches.
        """
        from ..lighting.movement_patterns import apply_genre_defaults
        if pin is not None:
            self._genre_operator_pinned = bool(pin)
            self._ml_genre_gate.current = genre.value
            self._ml_genre_gate.current_confidence = 1.0 if pin else 0.0
            self._ml_genre_gate.pending = None
            self._ml_genre_gate.pending_count = 0
        self.genre_manager.set_genre(genre, crossfade)
        self.key_lighting.set_genre(genre.value)
        # Apply genre speed defaults to pro movement
        apply_genre_defaults(self.pro_movement.params, genre.value)
        # Sync genre to pro strobe budget and decision engine
        self.pro_effects.strobe.set_genre(genre.value)
        self.decision.set_genre(genre.value)

    def set_section(self, section, immediate: bool = False):
        """Manually trigger a song section change."""
        self.section_manager.trigger_section(section, immediate)
        # Sync to decision engine
        self.decision.set_section(section.value if hasattr(section, 'value') else str(section))

    def update_audio(
        self,
        energy: float = 0.0,
        bass: float = 0.0,
        mid: float = 0.0,
        high: float = 0.0,
        is_beat: bool = False,
        beat_number: int = 0,
        valence: float = 0.5,
        arousal: float = 0.5,
        spectral_flux: float = 0.0,
        bpm: float = 128.0,
        ml_data: dict = None,
        programme_level: Optional[float] = None,
        tempo_confidence: Optional[float] = None,
        track_id: Optional[int] = None,
        track_transition: Optional[float] = None,
    ):
        """
        Update audio state from audio analyzer.

        Args:
            programme_level: Loudness relative to this material's own running
                reference (0.5 = the reference), or None when the source
                publishes none. Playback-level invariant, and used only where
                that invariance is what is wanted - it is deliberately not the
                energy the rig renders from; see `schemas.audio.engine_energy`.
            energy: Overall RMS energy (0-1)
            bass: Bass band energy (0-1)
            mid: Mid band energy (0-1)
            high: High band energy (0-1)
            is_beat: Beat detected this frame
            beat_number: Current beat count
            valence: Mood valence (0=sad, 1=happy)
            arousal: Mood arousal (0=calm, 1=excited)
            spectral_flux: Rate of spectral change
            bpm: Detected BPM
            ml_data: ML pipeline output (emotion_vector, emotion_mapping, structure, genre)
            tempo_confidence: The analyser's 0-1 confidence that `bpm` is the
                tempo an operator would count, or None when the source has no
                drum-aware tempo. When given, it decides the clock's metrical
                level; see `_beat_clock_level`.
            track_id: Which record is playing, from the analyser's track-change
                detector, or None when the source has none. A change starts a
                new song (palette, drop history) on the next bar line, with no
                silence needed; see `_detect_song_change`.
            track_transition: 0..1, how far a DJ blend into a new record has
                got. While it is above zero the colour holds.
        """
        # Any call at all means audio is arriving; see `_audio_loss_check`.
        self._last_audio_t = self.time
        if self._audio_lost:
            self._audio_lost = False
            logger.info("Audio input is back; leaving the ambient hold")
        try:
            if float(energy) >= float(self.config.silence_threshold):
                self._music_heard = True
        except (TypeError, ValueError):
            pass
        try:
            self._reported_track_id = int(track_id) if track_id is not None else None
        except (TypeError, ValueError):
            self._reported_track_id = None
        try:
            blend = float(track_transition) if track_transition is not None else 0.0
        except (TypeError, ValueError):
            blend = 0.0
        self._track_transition = blend if 0.0 <= blend <= 1.0 else 0.0

        try:
            conf = float(tempo_confidence) if tempo_confidence is not None else None
        except (TypeError, ValueError):
            conf = None
        if conf is not None and not (0.0 <= conf <= 1.0):
            conf = None
        self._reported_tempo_confidence = conf

        # Mood values may arrive as either [0..1] or [-1..1] depending on source.
        # Normalize once here so color logic is stable and explicit.
        raw_valence = float(valence)
        raw_arousal = float(arousal)
        if isinstance(ml_data, dict):
            ev = ml_data.get("emotion_vector", {})
            if isinstance(ev, dict):
                raw_valence = float(ev.get("valence", raw_valence))
                raw_arousal = float(ev.get("arousal", raw_arousal))

        def _norm_mood(v: float) -> float:
            if v < -0.01 or v > 1.01:
                v = (v + 1.0) * 0.5
            return max(0.0, min(1.0, v))

        norm_valence = _norm_mood(raw_valence)
        norm_arousal = _norm_mood(raw_arousal)

        # If upstream mood is flat/absent, derive a gentle fallback so colors still move.
        if abs(raw_valence) < 1e-6 and abs(raw_arousal) < 1e-6:
            norm_arousal = max(norm_arousal, min(1.0, 0.25 + energy * 0.7))
            spectral_balance = high - bass
            norm_valence = max(0.0, min(1.0, 0.5 + spectral_balance * 0.35 + (mid - 0.5) * 0.1))

        # Stabilize base song color identity: heavy smoothing + deadband on mood axes.
        valence_diff = norm_valence - self._smoothed_valence
        if abs(valence_diff) > 0.015:
            self._smoothed_valence += valence_diff * 0.03
        arousal_diff = norm_arousal - self._smoothed_arousal
        if abs(arousal_diff) > 0.015:
            self._smoothed_arousal += arousal_diff * 0.05

        # Update audio features for color mapping
        self.audio_features = AudioFeatures(
            energy=energy,
            bass=bass,
            mid=mid,
            high=high,
            valence=max(0.0, min(1.0, self._smoothed_valence)),
            arousal=max(0.0, min(1.0, self._smoothed_arousal)),
            is_beat=is_beat,
            beat_intensity=bass if is_beat else 0.0
        )

        # Update audio state for decision engine
        self.audio_state.energy = energy
        self.audio_state.bass = bass
        self.audio_state.mid = mid
        self.audio_state.high = high
        self.audio_state.spectral_flux = spectral_flux
        self.audio_state.is_beat = is_beat
        self.audio_state.beat_number = beat_number
        self.audio_state.bpm = bpm
        self._programme_level = programme_level

        # Update BPM (raw for reactive layers)
        self.config.bpm = bpm

        # Phase-lock the musical clock to this block. Wrapped because it runs on
        # the audio callback: a bad frame of analysis must not stop the show.
        try:
            self._beat_clock_observe(energy, bpm, is_beat, beat_number)
        except Exception:
            pass
        self._sync_section_manager_tempo(bpm)

        # Smooth BPM for non-reactive movement clock to avoid jitter from detector noise.
        target_bpm = max(60.0, min(200.0, float(bpm)))
        if self._clock_locked:
            # The locked clock is the engine's tempo; the reported BPM is only
            # the fallback for material it cannot find a pulse in.
            self._smoothed_movement_bpm = max(60.0, min(200.0, 60.0 / self._clock_period))
        elif self.config.movement_music_reactive:
            self._smoothed_movement_bpm = target_bpm
        else:
            # Heavy low-pass keeps movement steady while still following long-term tempo drift.
            self._smoothed_movement_bpm += (target_bpm - self._smoothed_movement_bpm) * 0.02

        # Handle beat triggers
        if is_beat and beat_number != self.beat_count:
            self.beat_count = beat_number
            self.last_beat_time = self.time
            self._on_beat(beat_number)

        # Song change detection for palette locking
        if self.config.lock_palette_per_song:
            self._detect_song_change(energy, ml_data)

        # Process ML pipeline data when pro lighting is enabled
        if ml_data and self._pro_lighting_enabled:
            self._apply_ml_data(ml_data)

    def _detect_song_change(self, energy: float, ml_data: dict = None):
        """Detect song changes (silence + ML transition cues) and switch color palette."""
        current_time = self.time

        # --- The analyser's track-change detector: a DJ mix has no silence ---
        track_id = self._reported_track_id
        if track_id is not None:
            if self._track_id is not None and track_id != self._track_id:
                self._pending_palette_reseed = True
                self._pending_palette_reseed_at = current_time
            self._track_id = track_id
        # The clock's own bar line is the safe place to change looks; the ML
        # structure data, when there is any, can add its boundaries to it.
        safe_boundary = self._rebuild_downbeat_event()

        # --- ML-aware song transition detection (preferred over silence heuristics) ---
        structure_data = ml_data.get("structure", {}) if isinstance(ml_data, dict) else {}
        if structure_data:
            section = str(structure_data.get("section", "unknown")).lower()
            is_boundary = bool(structure_data.get("is_section_boundary", False))
            transition = structure_data.get("transition", {}) if isinstance(structure_data.get("transition", {}), dict) else {}
            transition_window_s = float(structure_data.get("transition_window_s", transition.get("window_s", 1.25)) or 1.25)
            transition_prob = float(
                structure_data.get("song_transition_probability",
                structure_data.get("transition_probability",
                transition.get("song_change_probability", 0.0))) or 0.0
            )
            explicit_transition = bool(
                structure_data.get("is_song_transition")
                or structure_data.get("new_song")
                or transition.get("is_song_transition")
            )
            song_marker = structure_data.get("song_id") or structure_data.get("track_id")
            marker_changed = bool(song_marker and song_marker != self._song_transition_marker)
            transition_candidate = explicit_transition or transition_prob >= 0.8 or marker_changed

            if song_marker:
                self._song_transition_marker = song_marker

            if transition_candidate:
                self._pending_palette_reseed = True
                self._pending_palette_reseed_at = current_time + max(0.3, transition_window_s)

            phrase_boundary = (self.audio_state.beat_number > 0 and self.audio_state.beat_number % 16 == 0)
            safe_boundary = safe_boundary or is_boundary or phrase_boundary or section in {"intro", "outro", "breakdown"}

        if self._pending_palette_reseed and (
            (current_time >= self._pending_palette_reseed_at and safe_boundary)
            or current_time >= self._pending_palette_reseed_at + 0.75
        ):
            if current_time - self._last_palette_reseed_time > 2.0:
                self._pending_palette_reseed = False
                self._last_palette_reseed_time = current_time
                self._on_song_change()
                return

        if energy < self.config.silence_threshold:
            # Audio is silent
            if self._silence_start_time is None:
                self._silence_start_time = current_time
            elif current_time - self._silence_start_time >= self.config.silence_duration_for_song_change:
                # Silence long enough - song changed!
                if self._palette_locked:
                    self._on_song_change()
        else:
            # Audio playing
            self._silence_start_time = None
            if not self._palette_locked:
                # First audio after startup or song change - lock this palette
                self._palette_locked = True
                print(f"[Effects] Palette locked: {self._current_song_palette.value}")

    def _sync_section_manager_tempo(self, bpm: float) -> None:
        """Give the section manager the tempo the show is counting.

        It times its crossfades, anticipation and build-up ramps in bars, and
        it never heard a tempo after construction, so every song ran on the
        default 128 BPM: a 2-bar build at 87 BPM ended a bar and a half early.
        The locked clock's tempo is preferred over the raw detector's.
        """
        try:
            if self._clock_locked and self._clock_period > 0:
                tempo = 60.0 / self._clock_period
            else:
                tempo = float(bpm)
            if math.isfinite(tempo) and tempo > 0:
                self.section_manager.set_bpm(tempo)
        except Exception:
            pass

    def _observe_club_style(self, genre_data: Dict) -> None:
        """Count the genre model's fresh answers and adopt a style they agree on.

        The analyser repeats its last answer on every block, so only a new
        `seq` is a vote. Unsure or non-music answers keep the style in force: a
        breakdown or a talk-over says nothing about what the room is playing.
        An operator's genre choice wins and the model is not followed.
        """
        seq = genre_data.get("seq")
        if seq is not None and seq == self._club_style_seq:
            return
        self._club_style_seq = seq
        if self._genre_operator_pinned:
            return
        style = str(genre_data.get("genre") or "").lower()
        try:
            confidence = float(genre_data.get("genre_confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if style not in _CLUB_STYLE_LOOKS or confidence < _CLUB_STYLE_MIN_CONFIDENCE:
            self._club_style_candidate = None
            self._club_style_votes = 0
            return
        if style == self._club_style:
            self._club_style_candidate = None
            self._club_style_votes = 0
            return
        if style == self._club_style_candidate:
            self._club_style_votes += 1
        else:
            self._club_style_candidate = style
            self._club_style_votes = 1
        if self._club_style_votes >= _CLUB_STYLE_VOTES:
            self._adopt_club_style(style)

    def _adopt_club_style(self, style: str) -> None:
        """Take a new club style. Colour follows on the next phrase line and
        movement on the next pattern change, so nothing jumps."""
        self._club_style = style
        self._club_style_candidate = None
        self._club_style_votes = 0
        palettes = _CLUB_STYLE_LOOKS[style]["palettes"]
        if self._current_song_palette not in palettes:
            self._palette_index = 0
            self._current_song_palette = palettes[0]
            self.color.set_palette(self._current_song_palette)
            self.config.palette = self._current_song_palette
            self._palette_version += 1
        logger.info("Club style now %s", style)

    def _on_song_change(self):
        """Handle song change - pick new color palette and reset ML state."""
        # Cycle to next palette, within the club style's palettes once one is known
        look = _CLUB_STYLE_LOOKS.get(self._club_style or "")
        palettes = list(look["palettes"]) if look else self._available_palettes
        self._palette_index = (self._palette_index + 1) % len(palettes)
        self._current_song_palette = palettes[self._palette_index]
        self._palette_locked = False  # Will lock on next audio
        self._palette_version += 1
        self._pending_palette_reseed = False

        # Apply the new palette
        self.color.set_palette(self._current_song_palette)
        self.config.palette = self._current_song_palette

        # Reset pro lighting state for new song
        if self._pro_lighting_enabled:
            from ..lighting.section_manager import SongSection
            self.pro_effects.strobe.reset_song_budget()
            self.section_manager.trigger_section(SongSection.UNKNOWN, immediate=True)
            self.pro_effects.build.stop()
            self._ml_emotion_mapping = None

        self._reset_drop_anticipation()

        # A new record has its own loudness: the last one's reference would
        # squash a quieter intro or clip a hotter master.
        self.decision.reset_dynamics()

        # Reset section-template "home" state and MIB transitions for next song
        self._song_home_section = None
        self._song_home_template = None
        self._current_section_template_key = None
        self._mib_states.clear()

        # A new record is a new phrase grid and a fresh look.
        self._phrase_origin_bar = None
        self._rebuild_pattern_key = None
        self._rebuild_color_key = None
        self._rebuild_color_hold_until = 0.0

        print(f"[Effects] Song changed! New palette: {self._current_song_palette.value}")

    def _get_palette_narrative_variant(self, section: str) -> Dict[str, float]:
        """Section-aware palette narrative controls for one-song palette identity."""
        section = (section or "unknown").lower()
        base_variant = {
            "accent_swap": 0.0,
            "sat_mult": 1.0,
            "white_mix": 0.03,
            "color_count": 3.0,
        }
        if section in {"intro", "verse"}:
            return base_variant
        if section in {"chorus", "drop", "peak"}:
            return {
                "accent_swap": 1.0,
                "sat_mult": 1.2,
                "white_mix": 0.02,
                "color_count": 3.0,
            }
        if section in {"breakdown", "bridge"}:
            return {
                "accent_swap": 0.0,
                "sat_mult": 0.75,
                "white_mix": 0.12,
                "color_count": 1.0,
            }
        return {
            "accent_swap": 0.0,
            "sat_mult": 0.92,
            "white_mix": 0.06,
            "color_count": 2.0,
        }

    def _apply_palette_narrative_to_fixture(self, fixture: Fixture, fixture_index: int, section: str):
        """Apply section-level palette variants while preserving song-level palette identity."""
        variant = self._get_palette_narrative_variant(section)

        r, g, b = fixture.red, fixture.green, fixture.blue
        avg = (r + g + b) / 3.0

        sat_mult = max(0.0, float(variant["sat_mult"]))
        r = avg + (r - avg) * sat_mult
        g = avg + (g - avg) * sat_mult
        b = avg + (b - avg) * sat_mult

        if variant["color_count"] <= 1.0:
            r = g = b = avg
        elif variant["color_count"] <= 2.0:
            if fixture_index % 2:
                r, b = b, r

        if variant["accent_swap"] >= 0.5 and fixture_index % 2:
            r, b = b, r

        white_mix = max(0.0, min(0.4, float(variant["white_mix"])))
        r = r * (1.0 - white_mix) + white_mix
        g = g * (1.0 - white_mix) + white_mix
        b = b * (1.0 - white_mix) + white_mix

        fixture.red = max(0.0, min(1.0, r))
        fixture.green = max(0.0, min(1.0, g))
        fixture.blue = max(0.0, min(1.0, b))

    def _gate_target_switch(
        self,
        gate: _TargetGateState,
        *,
        candidate: str,
        confidence: float,
        confidence_on: float,
        confidence_off: float,
        consecutive_frames: int,
        min_hold_ms: int,
        min_confidence_delta: float,
    ) -> bool:
        """Return True when a candidate passes confidence/hold/hysteresis gates."""
        if not candidate:
            gate.pending = None
            gate.pending_count = 0
            return False

        confidence = float(confidence)
        now = self.time
        min_hold_s = max(0, int(min_hold_ms)) / 1000.0
        required_frames = max(1, int(consecutive_frames))

        # Keep current target when candidate is effectively the same/too weak.
        if gate.current == candidate:
            if confidence >= confidence_off:
                gate.current_confidence = max(gate.current_confidence * 0.9, confidence)
            gate.pending = None
            gate.pending_count = 0
            return False

        if confidence < confidence_off:
            gate.pending = None
            gate.pending_count = 0
            return False

        # Minimum hold duration before accepting another major target change.
        if now - gate.last_accept_time < min_hold_s:
            return False

        # Hysteresis: require meaningful confidence margin over current target.
        if gate.current is not None and confidence < (gate.current_confidence + min_confidence_delta):
            gate.pending = None
            gate.pending_count = 0
            return False

        # Require a strong candidate for N consecutive frames.
        if confidence >= confidence_on:
            if gate.pending == candidate:
                gate.pending_count += 1
            else:
                gate.pending = candidate
                gate.pending_count = 1
        else:
            gate.pending = None
            gate.pending_count = 0
            return False

        if gate.pending_count < required_frames:
            return False

        gate.current = candidate
        gate.current_confidence = confidence
        gate.last_accept_time = now
        gate.pending = None
        gate.pending_count = 0
        return True

    def _apply_ml_data(self, ml_data: dict):
        """Apply ML pipeline data (MERT emotion, structure, genre) to pro lighting modules.

        This is the core wiring that makes the system fully automatic:
        audio -> ML models -> lighting parameter modulation.
        """
        from ..lighting.genre_profiles import Genre
        from ..lighting.section_manager import SongSection
        from ..lighting.pro_effects import ColorTemperature

        # --- Genre auto-switching ---
        genre_data = ml_data.get("genre")
        # A heuristic guess is shown, never obeyed: it would retune the whole
        # show to the wrong genre (it reads club music as ambient). A "shadow"
        # answer is the trained model being checked on a real night: logged,
        # never obeyed. The trained
        # model's answer is a club style, which leans palette and movement only
        # and leaves strobe budget, dynamics and sections alone.
        if genre_data and genre_data.get("source") == "model":
            self._observe_club_style(genre_data)
        elif genre_data and genre_data.get("source") not in ("heuristic", "shadow"):
            detected_genre = genre_data.get("genre", "").lower()
            confidence = genre_data.get("genre_confidence", 0.0)
            gate_passed = (
                self._gate_target_switch(
                    self._ml_genre_gate,
                    candidate=detected_genre,
                    confidence=confidence,
                    confidence_on=self.config.ml_genre_confidence_on,
                    confidence_off=self.config.ml_genre_confidence_off,
                    consecutive_frames=self.config.ml_genre_consecutive_frames,
                    min_hold_ms=self.config.ml_genre_min_hold_ms,
                    min_confidence_delta=self.config.ml_genre_min_confidence_delta,
                )
                if self.config.ml_target_gating_enabled
                else confidence >= self.config.ml_genre_confidence_on
            )
            if gate_passed:
                genre_map = {
                    "edm": Genre.EDM,
                    "rock": Genre.ROCK,
                    "metal": Genre.ROCK,
                    "pop": Genre.POP,
                    "hip_hop": Genre.HIP_HOP,
                    "jazz": Genre.JAZZ,
                    "classical": Genre.JAZZ,
                    "ambient": Genre.JAZZ,
                }
                genre_enum = genre_map.get(detected_genre)
                if genre_enum and genre_enum != self.genre_manager.current_genre:
                    self.set_genre(genre_enum, pin=None)
                    # Reset strobe budget for genre change
                    self.pro_effects.strobe.set_genre(detected_genre)
                    self.pro_effects.strobe.reset_song_budget()
                    print(f"[ML] Genre auto-switched to {detected_genre} (conf={confidence:.2f})")

        # --- Structure-driven section changes ---
        structure_data = ml_data.get("structure")
        if structure_data:
            detected_section = structure_data.get("section", "unknown")
            section_confidence = structure_data.get("section_confidence", 0.0)
            is_boundary = structure_data.get("is_section_boundary", False)

            gate_passed = (
                self._gate_target_switch(
                    self._ml_section_gate,
                    candidate=detected_section,
                    confidence=section_confidence,
                    confidence_on=self.config.ml_section_confidence_on,
                    confidence_off=self.config.ml_section_confidence_off,
                    consecutive_frames=self.config.ml_section_consecutive_frames,
                    min_hold_ms=self.config.ml_section_min_hold_ms,
                    min_confidence_delta=self.config.ml_section_min_confidence_delta,
                )
                if self.config.ml_target_gating_enabled
                else section_confidence >= self.config.ml_section_confidence_on
            )

            if gate_passed:
                section_map = {
                    "intro": SongSection.INTRO,
                    "verse": SongSection.VERSE,
                    "chorus": SongSection.CHORUS,
                    "bridge": SongSection.BRIDGE,
                    "drop": SongSection.DROP,
                    "breakdown": SongSection.BREAKDOWN,
                    "build_up": SongSection.BUILDUP,
                    "outro": SongSection.OUTRO,
                    "instrumental": SongSection.VERSE,
                    "solo": SongSection.CHORUS,
                }
                section_enum = section_map.get(detected_section)
                if section_enum and section_enum != self.section_manager.current_section:
                    # Use immediate transition on section boundaries, crossfade otherwise
                    self.section_manager.trigger_section(section_enum, immediate=is_boundary)

            # Handle buildup->drop anticipation from transition predictions
            transition = structure_data.get("transition", {})
            if transition.get("is_buildup") and transition.get("buildup_progress", 0) > 0:
                buildup_progress = transition["buildup_progress"]
                if not self.pro_effects.build.is_active and buildup_progress < 0.3:
                    # Start build effect for the buildup section
                    bars_until = transition.get("bars_until", 8)
                    self.pro_effects.build.trigger(
                        duration_beats=max(4.0, bars_until * 4),
                        curve="quadratic",
                    )
                # Pre-drop blackout: trigger 0.75s before the drop hits
                if buildup_progress > 0.85 and transition.get("bars_until", 4) <= 1:
                    if self.pro_effects.get_blackout_override() is None:
                        self.pro_effects.trigger_pre_drop_blackout(duration=0.75)

        # --- MERT emotion -> lighting parameter modulation ---
        emotion_mapping = ml_data.get("emotion_mapping")
        if emotion_mapping:
            # Color temperature from valence
            warmth = emotion_mapping.get("palette_warmth", 0.5)
            if warmth > 0.65:
                self.pro_effects.wash.set_color_temperature(ColorTemperature.WARM, blend=0.25)
            elif warmth < 0.35:
                self.pro_effects.wash.set_color_temperature(ColorTemperature.COOL, blend=0.25)
            else:
                self.pro_effects.wash.set_color_temperature(ColorTemperature.NEUTRAL, blend=0.1)

            # Coverage -> fixture spread on wash
            coverage = emotion_mapping.get("coverage", 0.5)
            self.pro_effects.wash.set_fixture_spread(1.0 - coverage)

            # Store emotion mapping for use in _update_fixtures
            self._ml_emotion_mapping = emotion_mapping

    def _on_beat(self, beat_number: int):
        """Handle beat event."""
        # Trigger dimmer beat sync
        self.dimmer.trigger_beat(beat_number)

        # Trigger strobe beat if in beat-locked mode
        self.strobe.trigger_beat(beat_number)

        # Trigger movement beat (for bump patterns and beat-locked effects)
        self.movement.trigger_beat()

        # Forward beat to pro lighting modules
        if self._pro_lighting_enabled:
            if self.config.movement_music_reactive:
                self.pro_movement.trigger_beat()
            self.pro_effects.trigger_beat(beat_number)
            self.section_manager.trigger_beat(beat_number)

        # White strobe flash ONLY on extreme high energy moments (drops, climaxes)
        # Must be: every 16th beat (start of 4-bar phrase) + very high energy + high bass
        is_phrase_start = beat_number % 16 == 0
        extreme_energy = self.audio_features.energy > 0.85 and self.audio_features.bass > 0.85

        if is_phrase_start and extreme_energy:
            # Trigger a short white strobe burst on drops/climaxes
            self._white_strobe_flash = True
            self._white_strobe_decay = 0.08  # 80ms flash

        # Subtle reactive white accent (LD-style): brief beat lift, never full-time white.
        # Keep white accents subtle so base color remains dominant.
        accent = 0.0
        if self.audio_features.bass > 0.72:
            accent += 0.03
        if self.audio_features.energy > 0.82:
            accent += 0.03
        if beat_number % 4 == 0 and self.audio_features.energy > 0.7:
            accent += 0.02
        self._white_accent_level = max(self._white_accent_level, min(0.08, accent))

        # Update bars counter
        if beat_number % 4 == 0:
            self.decision.bars_in_state += 1
            self.audio_state.bars_elapsed += 1

    def update(self, delta_time: float = None):
        """
        Update all effect layers and generate DMX output.

        Args:
            delta_time: Time since last update (auto-calculated if None)
        """
        current_time = time.time()
        if delta_time is None:
            delta_time = current_time - self.last_update
        self.last_update = current_time
        self.time += delta_time
        self._beat_clock_advance(delta_time)
        # Every renderer, not only the rebuild path, has to stop following a
        # feed that is no longer arriving.
        self._audio_loss_check()
        self._settle_if_audio_lost(delta_time)

        # Update decision engine - genre-aware mode when pro lighting is active
        if self.config.auto_mode and self._pro_lighting_enabled:
            # Sync genre and section from pro lighting modules to decision engine
            self.decision.set_genre(self.genre_manager.current_genre.value)
            self.decision.set_section(self.section_manager.current_section.value)
            self.decision.update(self.audio_state, delta_time)
            selection = self.decision.get_selection()
            self._apply_selection(selection)

            # Transition flash/blackout effects are only for reactive mode.
            if self.config.movement_music_reactive:
                self._trigger_pro_effects_from_decision()
        elif self.config.auto_mode:
            self.decision.update(self.audio_state, delta_time)
            selection = self.decision.get_selection()
            self._apply_selection(selection)

        # Apply section/genre cue templates before layer engines update.
        self._apply_section_template()

        # Sync BPM to movement engine for beat-locked patterns
        self.movement.params.bpm = self.config.bpm

        # Update all layers
        self.movement.update(delta_time)
        self.dimmer.update(delta_time)
        self.strobe.update(delta_time)
        self.color.update(delta_time)

        # Clean-slate runtime path: one renderer only, avoids conflicting overlays.
        # Respect auto/manual mode so manual controls still work when auto is disabled.
        if self.config.auto_mode and self._rebuild_busker_enabled:
            if not self._audio_lost:
                # With no audio arriving the section would be decided on stale
                # analysis; it holds where it was instead.
                self._rebuild_update_intent(delta_time)
            self._update_fixtures_rebuild(delta_time)
            self._apply_ambient_hold(delta_time)
            self._emit_dmx()
            return

        # Update pro lighting modules
        if self._pro_lighting_enabled:
            self.genre_manager.update(delta_time)
            self.section_manager.update(
                delta_time,
                energy=self.audio_features.energy,
                is_beat=self.audio_features.is_beat,
            )
            movement_bpm = self.config.bpm if self.config.movement_music_reactive else self._smoothed_movement_bpm
            self.pro_movement.set_bpm(movement_bpm)

            if self.config.movement_music_reactive:
                section_key = self.section_manager.current_section.value
                active_look = self._beam_look_scheduler.select_look(
                    section=section_key,
                    energy=self.audio_features.energy,
                    bpm=self.config.bpm,
                    bars_elapsed=self.audio_state.bars_elapsed,
                )
                self._active_beam_look = active_look
                self._beam_scene_machine.request_transition(active_look.pattern)
                scene_output = self._beam_scene_machine.update(delta_time)
                params = self._build_pattern_params(
                    scene_output.active_pattern,
                    symmetry_mode=active_look.symmetry,
                    focus_anchor=self._beam_focus_anchors[active_look.focus_anchor_name],
                    amplitude_scale=scene_output.amplitude_scale * active_look.speed_multiplier,
                )
                self.pro_movement.set_pattern(
                    params.pattern,
                    beat_divisor=max(0.125, params.beat_divisor * active_look.speed_multiplier),
                    pan_amplitude=params.pan_amplitude,
                    tilt_amplitude=params.tilt_amplitude,
                    phase_spread=params.phase_spread,
                    grouping=params.grouping,
                    smoothing=params.smoothing,
                    snap_positions=list(params.snap_positions),
                )
                self._apply_beam_look_effects(active_look)
            else:
                # Strict BPM-clocked symmetry presets; no audio-energy/section movement selection.
                self._update_busker_section_intent(delta_time)
                self._apply_clocked_symmetric_preset()
                chase_intensity = self._compute_clocked_chase_intensity()
                self._apply_clocked_chase_pattern(
                    chase_intensity=chase_intensity
                )
                # Keep non-reactive busking clean: no lingering build modulation.
                self.pro_effects.build.stop()
                self._apply_non_reactive_strobe(chase_intensity=chase_intensity)
                active_look = self._select_clocked_symmetric_look()
                self._active_beam_look = active_look
            self.pro_movement.update(delta_time)
            pro_effects_bpm = self.config.bpm if self.config.movement_music_reactive else self._smoothed_movement_bpm
            self.pro_effects.set_bpm(pro_effects_bpm)
            self.pro_effects.update(delta_time)

            # Auto-detect section from audio if no external section data.
            # Section data can still drive dimmer/effect dynamics while movement stays clocked.
            beat_number = int(getattr(self.audio_state, "beat_number", 0) or 0)
            bars_elapsed = int(getattr(self.audio_state, "bars_elapsed", 0) or 0)
            detected = self.section_manager.detect_section_from_energy(
                self.audio_features.energy,
                self.audio_features.bass,
                getattr(self.audio_state, 'spectral_flux', 0.0),
                is_beat=bool(self.audio_features.is_beat),
                beat_number=beat_number,
                bars_elapsed=bars_elapsed,
                is_downbeat_event=bool(self.audio_features.is_beat and beat_number > 0 and beat_number % 4 == 1),
                programme_level=self._programme_level,
                now=float(self.time),
            )

            # Fallback structure detector for purely reactive mode:
            # if auto/ML structure is weak, still catch drops and avoid lingering "unknown".
            from ..lighting.section_manager import SongSection
            spectral_flux = float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0)
            strong_impact = (
                self.audio_features.energy > 0.56
                and self.audio_features.bass > 0.62
                and (self.audio_features.is_beat or spectral_flux > 0.05)
            )
            if strong_impact:
                self._drop_candidate_frames += 1
            else:
                self._drop_candidate_frames = max(0, self._drop_candidate_frames - 1)

            if (
                detected is None
                and self._drop_candidate_frames >= 2
                and (self.time - self._last_forced_drop_time) > 3.0
            ):
                detected = SongSection.DROP
                self._last_forced_drop_time = self.time
                self._drop_candidate_frames = 0

            if detected is None and self.section_manager.current_section == SongSection.UNKNOWN:
                if self.audio_features.energy > 0.66:
                    detected = SongSection.CHORUS
                elif self.audio_features.energy > 0.35:
                    detected = SongSection.VERSE
                elif self.audio_features.energy < 0.22:
                    detected = SongSection.BREAKDOWN

            # Direct impact detector for reactive drop triggering (beat + bass/energy onset).
            spectral_flux = float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0)
            energy_delta = float(self.audio_features.energy - self._prev_energy)
            bass_delta = float(self.audio_features.bass - self._prev_bass)
            direct_impact_drop = (
                bool(self.audio_features.is_beat)
                and self.audio_features.energy > 0.48
                and self.audio_features.bass > 0.56
                and (energy_delta > 0.06 or bass_delta > 0.08 or spectral_flux > 0.05)
            )
            if (
                direct_impact_drop
                and (self.time - self._last_forced_drop_time) > 2.5
                and self.section_manager.current_section.value != "drop"
            ):
                detected = SongSection.DROP
                self._last_forced_drop_time = self.time
                self._drop_candidate_frames = 0

            if detected is not None:
                current_section = self.section_manager.current_section
                # Keep drop look alive long enough to read visually before auto-demotion.
                if (
                    current_section.value == "drop"
                    and detected.value != "drop"
                    and (time.time() - self.section_manager._section_start_time) < 2.0
                ):
                    detected = None
            if detected is not None:
                self.section_manager.trigger_section(
                    detected,
                    immediate=detected.value in {"drop", "buildup", "breakdown"},
                )

            self._prev_energy = float(self.audio_features.energy)
            self._prev_bass = float(self.audio_features.bass)

            # Sync section and genre to decision engine
            self.decision.set_genre(self.genre_manager.current_genre.value)
            self.decision.set_section(self.section_manager.current_section.value)

        # Update drop sequence if active
        if self.drop_sequence.is_active():
            self.drop_sequence.update()

        # Generate DMX frame
        self._update_fixtures(delta_time)

        # Output DMX
        self._emit_dmx()

    def _apply_beam_look_effects(self, active_look):
        """Apply scheduler-selected look parameters as a coordinated bundle."""
        self._current_section_intensity_scale = max(0.05, min(1.25, active_look.intensity_scale))

        from ..lighting.pro_effects import ProStrobeMode

        strobe_map = {
            "off": ProStrobeMode.OFF,
            "beat_locked": ProStrobeMode.BEAT_LOCKED,
            "continuous": ProStrobeMode.CONTINUOUS,
            "burst": ProStrobeMode.BURST,
        }
        self.pro_effects.strobe.set_mode(
            strobe_map.get(active_look.strobe_mode, ProStrobeMode.OFF),
            frequency=max(0.1, active_look.strobe_frequency_hz),
            intensity=max(0.0, min(1.0, active_look.strobe_intensity)),
        )

    def _resolve_section_genre(self) -> Tuple[str, str]:
        """Resolve current section/genre for template selection."""
        section = "unknown"
        genre = "edm"
        try:
            if self._pro_lighting_enabled:
                section = self.section_manager.current_section.value
                genre = self.genre_manager.current_genre.value
            else:
                section = self.decision.state.value
                genre = getattr(self.decision, "_genre", "edm")
        except Exception:
            pass
        return section, genre

    def _apply_section_template(self):
        """Apply genre+section templates with song-home tracking."""
        if not self._section_templates_enabled:
            return

        section, genre = self._resolve_section_genre()
        template = get_section_template(genre, section)

        # Song "home" look: first intro/verse template anchors the song identity.
        if self._song_home_template is None and section in ("intro", "verse"):
            self._song_home_section = section
            self._song_home_template = template

        # Outro returns toward home identity before fade-out if available.
        if section == "outro" and self._song_home_template is not None:
            template = type(template)(
                movement_preset=self._song_home_template.movement_preset,
                dimmer_preset=template.dimmer_preset,
                strobe_preset="off",
                base_intensity_scale=min(template.base_intensity_scale, 0.45),
                blackout_policy=template.blackout_policy,
                enable_mib=template.enable_mib,
            )

        key = f"{genre}:{section}:{template.movement_preset}:{template.dimmer_preset}:{template.strobe_preset}"
        self._current_section_intensity_scale = max(0.0, min(1.25, template.base_intensity_scale))
        self.config.mib_enabled = bool(template.enable_mib)
        if key == self._current_section_template_key:
            return
        self._current_section_template_key = key

        if (
            self.config.movement_enabled
            and self.config.movement_music_reactive
            and template.movement_preset in MOVEMENT_PRESETS
        ):
            self.movement.params = MOVEMENT_PRESETS[template.movement_preset]

        if self.config.dimmer_enabled and template.dimmer_preset in DIMMER_PRESETS:
            self.dimmer.params = DIMMER_PRESETS[template.dimmer_preset]

        if self.config.strobe_enabled:
            strobe_map = {
                "off": None,
                "beat_lock": "beat_flash",
                "drop_burst": "drop_burst",
            }
            strobe_key = strobe_map.get(template.strobe_preset, template.strobe_preset)
            if strobe_key is None:
                self.strobe.stop()
            elif strobe_key in STROBE_PRESETS:
                self.strobe.params = STROBE_PRESETS[strobe_key]

    def _apply_mib_transition(self, fixture: Fixture, desired_dimmer: float) -> float:
        """Per-fixture move-in-black state machine for large pan/tilt moves."""
        # In strict non-reactive busking mode we prioritize visible output over travel blackouts.
        if not self.config.movement_music_reactive:
            return desired_dimmer
        if not self.config.mib_enabled:
            return desired_dimmer

        fid = fixture.id
        state = self._mib_states.get(fid)
        if state is None:
            state = {
                "active": False,
                "end_time": 0.0,
                "last_pan": float(fixture.pan),
                "last_tilt": float(fixture.tilt),
            }

        pan = float(fixture.pan)
        tilt = float(fixture.tilt)
        delta = abs(pan - state["last_pan"]) + abs(tilt - state["last_tilt"])

        if (not state["active"]) and delta >= float(self.config.mib_pan_tilt_threshold):
            state["active"] = True
            state["end_time"] = self.time + max(0.05, self.config.mib_transition_ms / 1000.0)

        if state["active"]:
            if self.time < state["end_time"]:
                desired_dimmer = min(float(desired_dimmer), 0.02)
            else:
                state["active"] = False

        state["last_pan"] = pan
        state["last_tilt"] = tilt
        self._mib_states[fid] = state
        return desired_dimmer

    def _apply_selection(self, selection: EffectSelection):
        """Apply decision engine selection to effect layers."""
        # Movement
        if self.config.movement_enabled and self.config.movement_music_reactive:
            if selection.use_static_look:
                self.movement.set_pattern(
                    MovementType.NONE,
                    base_look=selection.static_look
                )
            elif selection.movement_preset in MOVEMENT_PRESETS:
                preset = MOVEMENT_PRESETS[selection.movement_preset]
                self.movement.params = preset
            else:
                self.movement.params.pattern = selection.movement
        elif self.config.movement_enabled:
            # Keep base movement parked at home; pro movement layer handles symmetric motion.
            self.movement.set_pattern(MovementType.NONE, base_look=StaticLook.ALL_CENTER)

        # Dimmer
        if self.config.dimmer_enabled:
            if selection.dimmer_preset in DIMMER_PRESETS:
                preset = DIMMER_PRESETS[selection.dimmer_preset]
                self.dimmer.params = preset
            else:
                self.dimmer.params.effect_type = selection.dimmer

            if selection.beat_pattern:
                self.dimmer.params.beat_pattern = selection.beat_pattern

        # Strobe
        if self.config.strobe_enabled:
            if selection.strobe_on_drop:
                self.trigger_drop_strobe()
            elif selection.strobe_preset in STROBE_PRESETS:
                preset = STROBE_PRESETS[selection.strobe_preset]
                self.strobe.params = preset
            else:
                self.strobe.params.mode = selection.strobe

    def _trigger_pro_effects_from_decision(self):
        """Trigger pro effects when the decision engine detects state transitions."""
        current_state = self.decision.state
        previous_state = self.decision.previous_state

        # Only trigger on actual transitions
        if current_state == previous_state:
            return

        from ..lighting.pro_effects import ProStrobeMode

        if current_state == LightingState.PEAK:
            # Drop detected - trigger full drop sequence (flash-blackout-flash + burst)
            self.pro_effects.trigger_drop()
            # Scale build-up intensity variation for anti-fatigue
            intensity_scale = self.decision.get_dynamic_intensity_scale()
            self.decision.track_intensity(intensity_scale)

        elif current_state == LightingState.BUILDUP:
            # Build-up - trigger progressive build effect and movement speed ramp
            self.pro_effects.build.trigger(duration_beats=16.0, curve="quadratic")
            self.pro_effects.strobe.stop()
            # Accelerate movement during buildup (quarter speed -> double speed)
            buildup_secs = 16.0 * 60.0 / max(60, self.config.bpm)
            self.pro_movement.start_speed_ramp(
                duration=buildup_secs, start_mult=0.25, end_mult=2.0
            )

        elif current_state == LightingState.BREAKDOWN:
            # Breakdown - clean transition via momentary blackout, kill strobe, stop builds
            self.pro_effects.trigger_section_blackout(duration=0.3)
            self.pro_effects.strobe.stop()
            self.pro_effects.build.stop()
            self.pro_movement.stop_speed_ramp()

        elif current_state == LightingState.OUTRO:
            # Outro - stop all pro effects
            self.pro_effects.blackout()

    def _build_fixture_phase_offsets(self, fixtures: List[Fixture]) -> Dict[str, Tuple[float, float]]:
        """Build coordinated per-fixture phase offsets for motion and effect layers."""
        total = len(fixtures)
        if total <= 0:
            return {}

        mover_indices = [i for i, fx in enumerate(fixtures) if getattr(fx, "fixture_type", "mover") == "mover"]
        if not mover_indices:
            mover_indices = list(range(total))

        movers = [fixtures[i] for i in mover_indices]
        mover_count = len(movers)
        if mover_count <= 0:
            return {}

        phase_map: Dict[str, Tuple[float, float]] = {}
        quad_template = (0.0, 0.25, 0.5, 0.75)

        center_x = sum(fx.x for fx in movers) / mover_count
        left = [fx for fx in movers if fx.x < center_x]
        right = [fx for fx in movers if fx.x >= center_x]
        left_sorted = sorted(left, key=lambda fx: abs(fx.x - center_x))
        right_sorted = sorted(right, key=lambda fx: abs(fx.x - center_x))
        left_rank = {fx.id: idx for idx, fx in enumerate(left_sorted)}
        right_rank = {fx.id: idx for idx, fx in enumerate(right_sorted)}
        side_size = max(1, max(len(left_sorted), len(right_sorted)))

        leader = min(movers, key=lambda fx: (abs(fx.x - center_x), fx.id))
        follower_sorted = sorted(movers, key=lambda fx: (abs(fx.x - leader.x), fx.id))
        follower_rank = {fx.id: idx for idx, fx in enumerate(follower_sorted)}

        for local_idx, fx in enumerate(movers):
            base_phase = local_idx / mover_count

            if fx.id in left_rank:
                rank = left_rank[fx.id]
                mirror_phase = (rank / side_size) * 0.5
            else:
                rank = right_rank.get(fx.id, 0)
                mirrored_rank = max(0, side_size - 1 - rank)
                mirror_phase = (mirrored_rank / side_size) * 0.5 + 0.5

            template_phase = quad_template[local_idx % 4]
            odd_even_phase = 0.25 if local_idx % 2 else 0.0
            motion_phase = (0.35 * base_phase + 0.35 * mirror_phase + 0.30 * template_phase + odd_even_phase) % 1.0

            if self._leader_follower_enabled:
                motion_phase = (motion_phase + follower_rank[fx.id] * self._leader_follower_delay) % 1.0

            effect_phase = (motion_phase + 0.125 + template_phase * 0.5 + (0.125 if local_idx % 2 else 0.0)) % 1.0
            phase_map[fx.id] = (motion_phase, effect_phase)

        for i, fx in enumerate(fixtures):
            if fx.id not in phase_map:
                base = i / total
                phase_map[fx.id] = (base, (base + 0.125) % 1.0)

        return phase_map

    def _update_fixtures(self, delta_time: float):
        """Update all fixture values from effect layers."""
        all_fixtures = self.fixtures.get_fixtures_in_group("all")
        total = len(all_fixtures)
        phase_offsets = self._build_fixture_phase_offsets(all_fixtures)
        linear_chase_level_by_id: Dict[str, float] = {}

        # Build an explicit linear chase map (full ON/OFF alternating) for non-reactive mode.
        if (
            self._pro_lighting_enabled
            and (not self.config.movement_music_reactive)
            and self._clocked_chase_last_intensity > 0.01
        ):
            chase_idx = self._clocked_chase_active_index if self._clocked_chase_active_index >= 0 else 0
            _, speed_name, _, _, _ = self._clocked_chase_cycle[chase_idx]
            steps_per_beat = {
                "whole": 0.5,   # advance every 2 beats
                "half": 1.0,    # advance every beat
                "quarter": 2.0, # advance every 1/2 beat
                "eighth": 4.0,  # advance every 1/4 beat
            }.get(speed_name, 1.0)
            step = int(
                math.floor(
                    self.time * (max(60.0, min(200.0, float(self._smoothed_movement_bpm))) / 60.0) * steps_per_beat
                )
            )

            mover_like_types = {"mover", "moving_head", "beam", "spot"}
            rows: Dict[float, List[Fixture]] = {}
            for fixture in all_fixtures:
                ftype = str(getattr(fixture, "fixture_type", "") or "").lower()
                if ftype in mover_like_types:
                    row_key = round(float(getattr(fixture, "z", 0.0)), 2)
                    rows.setdefault(row_key, []).append(fixture)

            sorted_row_keys = sorted(rows.keys())
            for row_idx, row_key in enumerate(sorted_row_keys):
                row_fixtures = rows[row_key]
                ordered = sorted(
                    row_fixtures,
                    key=lambda f: (float(getattr(f, "x", 0.0)), str(getattr(f, "id", ""))),
                )
                row_len = len(ordered)
                if row_len == 0:
                    continue

                # True traveling chase head by fixture ID order (MA-style linear chase).
                # Alternate row direction for mirrored looks across the two trusses.
                if row_idx % 2 == 0:
                    head_idx = step % row_len
                else:
                    head_idx = (row_len - 1 - (step % row_len)) % row_len

                head_fixture = ordered[head_idx]
                linear_chase_level_by_id[head_fixture.id] = 1.0

        # =====================================================================
        # TRAINING MODE: LFO Engine takes priority for manual control
        # =====================================================================
        lfo_outputs = {}
        if self._lfo_engine:
            # Sync BPM to LFO engine
            self._lfo_engine.set_master_bpm(self.config.bpm)
            # Ensure fixture count matches
            if self._lfo_engine.fixture_count != total:
                self._lfo_engine.set_fixture_count(total)
            # Get LFO outputs for all fixtures
            lfo_outputs = self._lfo_engine.update()

        section, _ = self._resolve_section_genre()
        for i, fixture in enumerate(all_fixtures):
            strobe_white_override = False
            motion_phase_offset, effect_phase_offset = phase_offsets.get(
                fixture.id, (i / max(1, total), i / max(1, total))
            )

            # Check if LFO has output for this fixture
            lfo_vals = lfo_outputs.get(i, {})
            has_lfo_control = bool(lfo_vals)

            if has_lfo_control:
                # LFO CONTROL MODE (training) - LFO values take priority
                if 'dimmer' in lfo_vals:
                    fixture.dimmer = max(0, min(1, lfo_vals['dimmer']))
                else:
                    fixture.dimmer = 1.0  # Default full brightness

                if 'pan' in lfo_vals:
                    # Internal pan/tilt units are degrees, not DMX bytes.
                    fixture.pan = max(-270.0, min(270.0, float(lfo_vals['pan']) * 270.0))
                if 'tilt' in lfo_vals:
                    fixture.tilt = max(-135.0, min(135.0, float(lfo_vals['tilt']) * 135.0))

                if 'red' in lfo_vals:
                    fixture.red = max(0, min(1, lfo_vals['red']))
                if 'green' in lfo_vals:
                    fixture.green = max(0, min(1, lfo_vals['green']))
                if 'blue' in lfo_vals:
                    fixture.blue = max(0, min(1, lfo_vals['blue']))

                # If no color from LFO, keep current or default to white
                if 'red' not in lfo_vals and 'green' not in lfo_vals and 'blue' not in lfo_vals:
                    if fixture.red == 0 and fixture.green == 0 and fixture.blue == 0:
                        fixture.red = 1.0
                        fixture.green = 1.0
                        fixture.blue = 1.0

            else:
                # FALLBACK MODE - use old layer system or defaults
                # Check if in training mode (all layers disabled) - set defaults
                training_mode = not (self.config.movement_enabled or
                                     self.config.dimmer_enabled or
                                     self.config.strobe_enabled)

                if training_mode:
                    # Training mode with no LFO active - show fixtures at defaults
                    fixture.dimmer = 1.0
                    fixture.pan = 0.0
                    fixture.tilt = 0.0
                    # Keep existing color or set to white
                    if fixture.red == 0 and fixture.green == 0 and fixture.blue == 0:
                        fixture.red = 1.0
                        fixture.green = 1.0
                        fixture.blue = 1.0
                else:
                    # Layer 1: Base intensity driven purely by audio energy
                    base_intensity = self.audio_features.energy

                    # Layer 2: Movement (pan/tilt)
                    if self.config.movement_enabled:
                        pan, tilt = self.movement.get_position(
                            fixture.id,
                            fixture.x, fixture.y, fixture.z,
                            i, motion_phase_offset
                        )
                        fixture.pan = pan
                        fixture.tilt = tilt

                    # Layer 3: Dimmer effect
                    dimmer_multiplier = 1.0
                    if self.config.dimmer_enabled:
                        dimmer_multiplier = self.dimmer.get_intensity(
                            fixture.id, i, effect_phase_offset,
                            energy=self.audio_features.energy
                        )

                    # Layer 4: Strobe
                    strobe_value = 0.0
                    if self.config.strobe_enabled and self.strobe.is_active():
                        strobe_value = self.strobe.get_strobe_value(
                            fixture.id, i, total, effect_phase_offset
                        )

                    # Combine layers for final intensity
                    if strobe_value > 0:
                        fixture.dimmer = strobe_value * base_intensity
                    else:
                        fixture.dimmer = base_intensity * dimmer_multiplier

                    # Color from audio (using locked palette)
                    if self.config.color_enabled:
                        color = self.color.get_color(
                            self.audio_features, i, effect_phase_offset
                        )
                        fixture.red = color.r
                        fixture.green = color.g
                        fixture.blue = color.b

                    # === Professional Lighting Layers ===
                    if self._pro_lighting_enabled:
                        # Section intensity modulation
                        section_intensity = self.section_manager.get_intensity()
                        fixture.dimmer *= section_intensity

                        # Pro movement (adds to existing movement)
                        if self.config.movement_enabled:
                            profile = get_capability_profile_for_fixture(
                                getattr(fixture, "fixture_type", None)
                            )
                            pan_off, tilt_off = self.pro_movement.get_position(
                                fixture.id,
                                i,
                                total,
                                fixture.x,
                                fixture.y,
                                fixture.z,
                                role=profile.role,
                                movement_speed_class=profile.movement_speed_class,
                            )
                            # Movement can run in strict BPM-clock mode (non-reactive),
                            # while dimmer/color continue reacting to music.
                            if self.config.movement_music_reactive:
                                move_energy = self.section_manager.get_movement_energy()
                                if self._ml_emotion_mapping is not None:
                                    ml_move = self._ml_emotion_mapping.get("movement_speed", 0.5)
                                    move_energy *= 0.5 + ml_move  # 0.5x-1.5x range
                            else:
                                move_energy = 1.0
                            pan_off *= move_energy
                            tilt_off *= move_energy
                            # Beat-hit bumps are only for reactive movement mode.
                            if self.config.movement_music_reactive:
                                bump_pan, bump_tilt = self.pro_movement.get_bump_offset()
                                pan_off += bump_pan
                                tilt_off += bump_tilt
                            # Apply as degree offsets (internal units are degrees).
                            fixture.pan = max(-270.0, min(270.0, float(fixture.pan) + float(pan_off)))
                            fixture.tilt = max(-135.0, min(135.0, float(fixture.tilt) + float(tilt_off)))

                        # Pro movement chase dimmer (chases control brightness too)
                        if self.config.movement_music_reactive:
                            chase_dim = self.pro_movement.get_chase_intensity(i, total)
                            if chase_dim < 1.0:
                                fixture.dimmer *= chase_dim  # Allow full blackout for non-active chase fixtures

                        # Pro strobe overlay
                        if self.section_manager.is_strobe_allowed():
                            pro_strobe = self.pro_effects.strobe.get_value(i, total, effect_phase_offset)
                            if pro_strobe > 0:
                                fixture.dimmer = max(fixture.dimmer, pro_strobe)
                                # Defer hard white override until end of pipeline so no later layer repaints it.
                                strobe_white_override = True

                        # Pro color wash overlay
                        wash_color = self.pro_effects.wash.get_color(i, total)
                        if wash_color and self.pro_effects.wash._colors:
                            # Blend wash color with current color
                            sat = self.section_manager.get_color_saturation()
                            fixture.red = fixture.red * (1 - sat * 0.3) + wash_color.r * sat * 0.3
                            fixture.green = fixture.green * (1 - sat * 0.3) + wash_color.g * sat * 0.3
                            fixture.blue = fixture.blue * (1 - sat * 0.3) + wash_color.b * sat * 0.3

                        # Pro chase intensity overlay
                        chase_val = self.pro_effects.chase.get_intensity(i, total)
                        if (
                            (not self.config.movement_music_reactive)
                            and self._clocked_chase_last_intensity > 0.01
                        ):
                            # Explicit linear chase: active head ON, others stay dark
                            if linear_chase_level_by_id.get(fixture.id, 0.0) >= 0.5:
                                fixture.dimmer = max(
                                    fixture.dimmer,
                                    1.0 * self._get_chase_bump_level()
                                )
                        elif chase_val > 0:
                            fixture.dimmer = max(fixture.dimmer, chase_val * section_intensity)

                        # Build-up effect modulation
                        if self.pro_effects.build.is_active:
                            fixture.dimmer *= self.pro_effects.build.get_intensity_multiplier()
                            # Fixture reveal mask (progressive center-out reveal)
                            reveal = self.pro_effects.build.get_fixture_reveal_mask(i, total)
                            fixture.dimmer *= reveal
                            desat = self.pro_effects.build.get_color_desaturation()
                            if desat > 0:
                                avg = (fixture.red + fixture.green + fixture.blue) / 3.0
                                fixture.red = fixture.red + (avg - fixture.red) * desat
                                fixture.green = fixture.green + (avg - fixture.green) * desat
                                fixture.blue = fixture.blue + (avg - fixture.blue) * desat

                        # MERT emotion modulation (when ML pipeline is active)
                        if self._ml_emotion_mapping is not None:
                            em = self._ml_emotion_mapping
                            # base_intensity modulates overall dimmer (no additive floor)
                            fixture.dimmer *= em.get("base_intensity", 1.0)
                            # color_saturation deepens or lightens colors
                            ml_sat = em.get("color_saturation", 0.7)
                            if ml_sat < 0.5:
                                # Desaturate toward white
                                desat_amount = (0.5 - ml_sat) * 0.4
                                avg = (fixture.red + fixture.green + fixture.blue) / 3.0
                                fixture.red += (avg - fixture.red) * desat_amount
                                fixture.green += (avg - fixture.green) * desat_amount
                                fixture.blue += (avg - fixture.blue) * desat_amount
                            # pulse_depth modulates beat response depth
                            # (applied via section beat_reactivity scaling already)

                        # Blackout/flash sequence override
                        blackout_val = self.pro_effects.get_blackout_override()
                        if blackout_val is not None and self.config.movement_music_reactive:
                            if blackout_val == 0.0:
                                # Blackout - all dark
                                fixture.dimmer = 0.0
                            else:
                                # Flash - full white
                                fixture.dimmer = 1.0
                                fixture.red = 1.0
                                fixture.green = 1.0
                                fixture.blue = 1.0

                        # Key lighting final pass (ensure performers always visible)
                        # In non-reactive chase mode, do not flatten chase with key-light floors.
                        if not (
                            (not self.config.movement_music_reactive)
                            and self._clocked_chase_last_intensity > 0.01
                        ):
                            key_override = self.key_lighting.get_key_light_override(
                                fixture.id, fixture.dimmer,
                                fixture.red, fixture.green, fixture.blue,
                            )
                            if key_override is not None:
                                fixture.dimmer = key_override["dimmer"]
                                fixture.red = key_override["r"]
                                fixture.green = key_override["g"]
                                fixture.blue = key_override["b"]

                    # Song-level palette lock with section-level narrative variants
                    if self.config.color_enabled:
                        self._apply_palette_narrative_to_fixture(fixture, i, section)
                        if self._white_accent_level > 0.0 and not self._white_strobe_flash:
                            accent = max(0.0, min(0.2, self._white_accent_level))
                            fixture.red = fixture.red * (1.0 - accent) + accent
                            fixture.green = fixture.green * (1.0 - accent) + accent
                            fixture.blue = fixture.blue * (1.0 - accent) + accent

            # Apply section template intensity scale across all non-training paths
            fixture.dimmer *= self._current_section_intensity_scale

            # Busking brightness: only boost if there's actual audio energy driving the system.
            if self._pro_lighting_enabled and (not self.config.movement_music_reactive):
                if section not in {"breakdown", "bridge", "outro"} and self.audio_features.energy > 0.05:
                    fixture.dimmer = max(fixture.dimmer, 0.45 * self.audio_features.energy)

            # True backend move-in-black: hide major reposition travel
            if fixture.fixture_type != "bar" and fixture.id and (hasattr(fixture, "pan") and hasattr(fixture, "tilt")):
                fixture.dimmer = self._apply_mib_transition(fixture, float(fixture.dimmer))

            # Dynamic range enforcement (anti-fatigue)
            if self._pro_lighting_enabled:
                if self.config.movement_music_reactive:
                    intensity_scale = self.decision.get_dynamic_intensity_scale()
                    if intensity_scale < 1.0:
                        fixture.dimmer *= intensity_scale
                self.decision.track_intensity(fixture.dimmer)

            # Final master brightness lift for non-reactive busking (except breakdown family).
            # Only apply when audio is present to avoid idle glow.
            if self._pro_lighting_enabled and (not self.config.movement_music_reactive):
                if section not in {"breakdown", "bridge", "outro"} and self.audio_features.energy > 0.05:
                    fixture.dimmer = min(1.0, fixture.dimmer * 1.9)

            # FINAL pro strobe override: pure bright white must win over all color/dimmer layers.
            if strobe_white_override:
                fixture.dimmer = 1.0
                fixture.red = 1.0
                fixture.green = 1.0
                fixture.blue = 1.0

            # White strobe flash override - full white, full intensity
            if self._white_strobe_flash and self._white_strobe_decay > 0:
                fixture.dimmer = 1.0  # Full brightness
                fixture.red = 1.0    # White
                fixture.green = 1.0
                fixture.blue = 1.0

        # Decay white strobe flash
        if self._white_strobe_decay > 0:
            self._white_strobe_decay -= delta_time
            if self._white_strobe_decay <= 0:
                self._white_strobe_flash = False
                self._white_strobe_decay = 0

        # Keep white accent very short so base song color remains dominant.
        if self._white_accent_level > 0:
            self._white_accent_level = max(0.0, self._white_accent_level - delta_time * 4.0)

        # Build atomic snapshot for concurrent WebSocket readers (BUG-001 fix)
        snapshot = []
        for fixture in all_fixtures:
            snapshot.append({
                'id': fixture.id,
                'dmx_address': int(getattr(fixture, 'dmx_address', 0) or 0),
                'universe': int(getattr(fixture, 'universe', 0) or 0),
                'pan': fixture.pan,
                'tilt': fixture.tilt,
                'dimmer': fixture.dimmer,
                'r': fixture.red,
                'g': fixture.green,
                'b': fixture.blue,
            })
        self._fixture_state_snapshot = snapshot

    def get_fixture_state_snapshot(self) -> List[Dict]:
        """
        Get an atomic snapshot of all fixture states.
        Safe to call from WebSocket handlers concurrently with update().
        """
        return self._fixture_state_snapshot

    def get_pro_lighting_state(self) -> Dict:
        """Get current professional lighting state for API/WebSocket."""
        if not self._pro_lighting_enabled:
            return {"enabled": False}
        timing_debug = self.decision.get_transition_debug()
        state = {
            "enabled": True,
            "genre": self.genre_manager.current_genre.value,
            "club_style": self._club_style,
            "section": self.section_manager.current_section.value,
            "palette_version": self._palette_version,
            "palette_locked": self._palette_locked,
            "palette": self._current_song_palette.value,
            "section_intensity": round(self.section_manager.get_intensity(), 3),
            "movement_energy": round(self.section_manager.get_movement_energy(), 3),
            "strobe_allowed": self.section_manager.is_strobe_allowed(),
            "buildup_progress": round(self.section_manager.get_buildup_progress(), 3),
            "pro_movement_pattern": self.pro_movement.params.pattern.value,
            "pro_strobe_active": self.pro_effects.strobe.is_active(),
            "pro_build_active": self.pro_effects.build.is_active,
            "key_lighting_zones": [z.value for z in self.key_lighting.get_active_zones()],
            "strobe_budget_remaining": self.pro_effects.strobe.strobe_budget_remaining,
            "pending_effect": timing_debug["pending_effect"],
            "commit_in_bars": timing_debug["commit_in_bars"],
            "last_commit_bar": timing_debug["last_commit_bar"],
            "pre_cue_active": timing_debug["pre_cue_active"],
            "constraints": {
                "strobe_hz_cap": float(self.config.strobe_hz_cap),
                "strobe_max_duty_cycle": float(self.config.strobe_max_duty_cycle),
                "strobe_burst_max_s": float(self.config.strobe_burst_max_s),
                "strobe_refractory_s": float(self.config.strobe_refractory_s),
                "audience_intensity_cap": float(self.config.audience_intensity_cap),
                "movement_when_bright": bool(self.config.movement_when_bright),
                "accessibility_mode": str(self.config.accessibility_mode),
                "camera_mode": bool(self.config.camera_mode),
                "venue_mode": str(self.config.venue_mode),
            },
        }
        # Include ML emotion data if available
        if self._ml_emotion_mapping is not None:
            state["emotion_mapping"] = self._ml_emotion_mapping
        return state

    def _record_safety_event(
        self,
        event_type: str,
        details: Dict,
        throttle_s: float = 0.0,
        throttle_key: Optional[str] = None,
    ):
        """Append a bounded in-memory safety/audit event log."""
        key = throttle_key or event_type
        now = float(self.time)
        if throttle_s > 0:
            last = self._safety_event_last_time.get(key, -999.0)
            if (now - last) < throttle_s:
                return
            self._safety_event_last_time[key] = now

        self._safety_events.append(
            {
                "time_s": round(now, 3),
                "event_type": str(event_type),
                "details": dict(details or {}),
            }
        )
        if len(self._safety_events) > 300:
            self._safety_events = self._safety_events[-300:]

    def get_safety_events(self, limit: int = 50) -> List[Dict]:
        """Return most recent safety policy/clamp events."""
        n = max(1, min(300, int(limit or 50)))
        return list(self._safety_events[-n:])

    def _commit_strobe_intent(self) -> None:
        """Tell the accent governor that these two fields were set deliberately.

        The governor owns `strobe_enabled` and `audience_intensity_cap` on every
        frame, so a value it happens to have written itself is invisible to it
        when something else writes the same value — an operator switching strobe
        off between accents, or a profile tightening the cap to a number the
        build ramp already produced. Anything that means the change to *last*
        routes through here. Never raises: it sits on the operator's path, and
        a failed hand-off must not take the show down.
        """
        governor = getattr(self, "accent_governor", None)
        if governor is None:
            return
        try:
            governor.set_enabled(bool(self.config.strobe_enabled))
            governor.set_nominal_cap(float(self.config.audience_intensity_cap))
        except Exception:
            pass

    def set_strobe_layer_enabled(self, enabled: bool) -> bool:
        """Operator-level strobe switch. Durable against the accent governor."""
        self.config.strobe_enabled = bool(enabled)
        self._commit_strobe_intent()
        return bool(enabled)

    def set_safety_profile(self, profile: str, camera_mode: Optional[bool] = None, venue_mode: Optional[str] = None) -> Dict:
        """Apply research-pack safety profile presets."""
        p = str(profile or "performance").lower()
        if p in {"no_strobe", "nostrobe", "safe"}:
            self.config.accessibility_mode = "no_strobe"
            self.config.strobe_enabled = False
            self.config.strobe_hz_cap = 2.0
            self.config.strobe_max_duty_cycle = 0.30
            self.config.strobe_burst_max_s = 0.08
            self.config.strobe_refractory_s = 0.30
            self.config.audience_intensity_cap = min(self.config.audience_intensity_cap, 0.85)
        elif p in {"conservative", "broadcast"}:
            self.config.accessibility_mode = "conservative"
            self.config.strobe_enabled = True
            self.config.strobe_hz_cap = 3.0
            self.config.strobe_max_duty_cycle = 0.34
            self.config.strobe_burst_max_s = 0.10
            self.config.strobe_refractory_s = 0.22
            self.config.audience_intensity_cap = min(self.config.audience_intensity_cap, 0.90)
        else:
            self.config.accessibility_mode = "performance"
            self.config.strobe_enabled = True
            self.config.strobe_hz_cap = max(self.config.strobe_hz_cap, 18.0)
            self.config.strobe_max_duty_cycle = max(self.config.strobe_max_duty_cycle, 0.40)
            self.config.strobe_burst_max_s = max(self.config.strobe_burst_max_s, 0.11)
            self.config.strobe_refractory_s = min(self.config.strobe_refractory_s, 0.16)

        if camera_mode is not None:
            self.config.camera_mode = bool(camera_mode)
            if self.config.camera_mode:
                self.config.accessibility_mode = "conservative"
                self.config.strobe_hz_cap = min(self.config.strobe_hz_cap, 3.0)
                self.config.strobe_max_duty_cycle = min(self.config.strobe_max_duty_cycle, 0.34)

        if venue_mode is not None:
            self.config.venue_mode = str(venue_mode).lower()
            if self.config.venue_mode in {"theatre", "broadcast", "corporate"}:
                self.config.audience_intensity_cap = min(self.config.audience_intensity_cap, 0.85)

        self._commit_strobe_intent()

        self._record_safety_event(
            "safety_profile_applied",
            {
                "profile": p,
                "camera_mode": bool(self.config.camera_mode),
                "venue_mode": str(self.config.venue_mode),
                "strobe_enabled": bool(self.config.strobe_enabled),
                "strobe_hz_cap": float(self.config.strobe_hz_cap),
                "audience_intensity_cap": float(self.config.audience_intensity_cap),
            },
        )

        return {
            "accessibility_mode": self.config.accessibility_mode,
            "camera_mode": self.config.camera_mode,
            "venue_mode": self.config.venue_mode,
            "strobe_enabled": self.config.strobe_enabled,
            "strobe_hz_cap": self.config.strobe_hz_cap,
            "strobe_max_duty_cycle": self.config.strobe_max_duty_cycle,
            "audience_intensity_cap": self.config.audience_intensity_cap,
        }

    def clean_stage(self):
        """Research-pack 'clean stage' macro: stop risky FX and return safe readable base."""
        self._rebuild_set_section("verse")
        self._rebuild_drop_until = -999.0
        self._rebuild_snare_strobe_until = -999.0
        self._white_strobe_flash = False
        self._white_strobe_decay = 0.0
        self._white_accent_level = 0.0
        self.config.strobe_enabled = False
        self._commit_strobe_intent()
        self.pro_effects.strobe.stop()
        self.pro_effects.build.stop()
        self.pro_effects.chase.stop()
        self._rebuild_base_color = RGB(0.95, 0.95, 0.95)
        self._rebuild_color_hold_until = self.time + 1.0

    # === Manual Controls ===

    def set_movement(
        self,
        pattern: MovementType,
        base_look: StaticLook = StaticLook.ALL_CENTER,
        **kwargs
    ):
        """Manually set movement pattern."""
        self.movement.set_pattern(pattern, base_look, **kwargs)
        self.config.manual_movement = pattern

    def set_static_look(self, look: StaticLook):
        """Set a static look (stops movement)."""
        self.movement.set_pattern(MovementType.NONE, base_look=look)
        self.config.manual_static_look = look

    def set_dimmer_effect(self, effect: DimmerType, **kwargs):
        """Manually set dimmer effect."""
        self.dimmer.set_effect(effect, **kwargs)
        self.config.manual_dimmer = effect

    def set_beat_pattern(self, pattern_name: str):
        """Set beat pattern by name."""
        if pattern_name in BEAT_PATTERNS:
            self.dimmer.params.beat_pattern = BEAT_PATTERNS[pattern_name]
            self.dimmer.params.effect_type = DimmerType.BEAT_SYNC

    def set_strobe(self, mode: StrobeMode, **kwargs):
        """Manually set strobe mode."""
        self.strobe.set_mode(mode, **kwargs)
        self.config.manual_strobe = mode

    def trigger_strobe_burst(self, duration: float = 2.0, frequency: float = 12.0):
        """Trigger a strobe burst."""
        self.strobe.trigger_burst(duration, frequency)

    def trigger_drop_strobe(self):
        """Trigger full drop strobe sequence."""
        self.drop_sequence.trigger_drop()

    def trigger_buildup(self, duration: float = 4.0):
        """Trigger build-up sequence."""
        self.drop_sequence.trigger_buildup(duration)
        self.decision.force_state(LightingState.BUILDUP)

    def set_color_palette(self, palette: ColorPalette):
        """Set color palette."""
        self.color.set_palette(palette)
        self.config.palette = palette

    def blackout(self):
        """Latch an operator blackout.

        Intensity goes to zero on every fixture and stays there, whatever the
        show is doing, until restore() releases it. Heads keep their position,
        so nothing swings while the room is dark.
        """
        self._blackout_latched = True
        self._zero_dimmers()
        self._emit_dmx()

    def restore(self):
        """Release an operator blackout; the show comes back on the next frame."""
        self._blackout_latched = False

    @property
    def blackout_active(self) -> bool:
        return self._blackout_latched

    def set_grand_master(self, level: float) -> float:
        """Set the grand master (0-1). Scales intensity only, never position."""
        try:
            value = float(level)
        except (TypeError, ValueError):
            raise ValueError("grand master must be a number between 0 and 1")
        if value != value:  # NaN
            raise ValueError("grand master must be a number between 0 and 1")
        self._grand_master = max(0.0, min(1.0, value))
        return self._grand_master

    @property
    def grand_master(self) -> float:
        return self._grand_master

    @property
    def output_master(self) -> float:
        """The intensity scale actually applied to the next frame."""
        return 0.0 if self._blackout_latched else self._grand_master

    def _zero_dimmers(self):
        for fixture in self.fixtures.fixtures.values():
            fixture.dimmer = 0
        self.strobe.stop()

    # === State Control ===

    def set_auto_mode(self, enabled: bool):
        """Enable/disable auto-pilot mode."""
        self.config.auto_mode = enabled

    def force_state(self, state: LightingState):
        """Force a specific lighting state."""
        self.decision.force_state(state)

    def get_state(self) -> LightingState:
        """Get current lighting state."""
        return self.decision.state

    # === Async Loop ===

    async def run(self):
        """Run the effects engine loop."""
        self.running = True
        interval = 1.0 / self.config.fps
        loop = asyncio.get_running_loop()
        next_frame = loop.time()
        error_logged = False

        while self.running:
            try:
                self.update()
                error_logged = False
            except Exception:
                # Keep loop alive in live use; one bad frame should not kill output.
                # Logged once per failure streak, not 60 times a second.
                if not error_logged:
                    logger.exception("EffectsEngine update error (suppressing repeats)")
                    error_logged = True
            # Pace against a deadline: sleeping a whole interval after update()
            # added the frame's own cost to every frame and ran below rate.
            next_frame += interval
            delay = next_frame - loop.time()
            if delay < -interval:
                next_frame = loop.time()
            # Always yield a little: an overloaded frame must not starve the API.
            await asyncio.sleep(max(0.002, delay))

    def stop(self):
        """Stop the effects engine."""
        self.running = False
        # Not the operator blackout: stopping must not leave a latch behind
        # that keeps the room dark when the engine is started again.
        self._zero_dimmers()

    # === Presets ===

    def load_preset(self, preset_name: str):
        """Load a combined effect preset."""
        presets = {
            "chill": {
                "movement": ("slow_sweep", {"base_look": StaticLook.FAN_OUT}),
                "dimmer": "breathing",
                "strobe": None,
                "palette": ColorPalette.AMBIENT
            },
            "hype": {
                "movement": ("chase_left_right", {"base_look": StaticLook.X_PATTERN}),
                "dimmer": "beat_kick",
                "strobe": "slow_safe",
                "palette": ColorPalette.EDM
            },
            "drop": {
                "movement": (None, {"base_look": StaticLook.X_PATTERN}),
                "dimmer": "beat_kick",
                "strobe": "drop_burst",
                "palette": ColorPalette.EDM
            },
            "breakdown": {
                "movement": (None, {"base_look": StaticLook.ALL_CENTER}),
                "dimmer": "breathing",
                "strobe": None,
                "palette": ColorPalette.AMBIENT
            }
        }

        if preset_name not in presets:
            return

        preset = presets[preset_name]

        # Movement
        if preset["movement"]:
            move_preset, move_kwargs = preset["movement"]
            if move_preset and move_preset in MOVEMENT_PRESETS:
                self.movement.params = MOVEMENT_PRESETS[move_preset]
            self.movement.params.base_look = move_kwargs.get("base_look", StaticLook.ALL_CENTER)

        # Dimmer
        if preset["dimmer"] and preset["dimmer"] in DIMMER_PRESETS:
            self.dimmer.params = DIMMER_PRESETS[preset["dimmer"]]

        # Strobe
        if preset["strobe"] and preset["strobe"] in STROBE_PRESETS:
            self.strobe.params = STROBE_PRESETS[preset["strobe"]]
        else:
            self.strobe.stop()

        # Palette
        if preset["palette"]:
            self.color.set_palette(preset["palette"])
