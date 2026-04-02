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
import math
import time
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass

from .fixture_groups import (
    Fixture, FixtureGroup, FixtureGroupManager, create_demo_rig
)
from ..demo.venue_presets import create_venue_rig
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
from .gobo_engine import GoboEngine
from .decision_engine import (
    DecisionEngine, LightingState, AudioState, EffectSelection
)
from .lfo_engine import LFOEngine
from ..lighting.section_templates import get_section_template
from ..lighting.fixture_capabilities import get_capability_profile_for_fixture
from ..lighting.movement_patterns import PRO_MOVEMENT_PRESETS

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
    accessibility_mode: str = "performance"     # no_strobe | conservative | performance
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


class EffectsEngine:
    """
    Main effects engine coordinating all layers.
    """

    def __init__(self, config: EffectsConfig = None):
        self.config = config or EffectsConfig()

        # Initialize components
        manager, preset = create_venue_rig("bigroom_edm")
        if manager:
            self.fixtures = manager
        else:
            self.fixtures = create_demo_rig()
        self.movement = MovementEngine()
        self.dimmer = DimmerEngine()
        self.strobe = StrobeController()
        self.color = ColorMapper(self.config.palette)
        self.decision = DecisionEngine()

        # Gobo choreography engine
        self.gobo = GoboEngine()

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

        # Beat tracking
        self.beat_count = 0
        self.last_beat_time = 0.0

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
        self._rebuild_section: str = "verse"
        self._rebuild_section_changed_at: float = 0.0
        self._rebuild_drop_until: float = -999.0
        self._rebuild_last_impact: float = -999.0
        self._rebuild_prev_energy: float = 0.0
        self._rebuild_prev_bass: float = 0.0
        self._rebuild_manual_hold_until: float = -999.0  # API section override hold
        self._rebuild_color_hold_until: float = 0.0
        self._rebuild_base_color: RGB = RGB(1.0, 1.0, 1.0)
        self._rebuild_snare_strobe_until: float = -999.0
        self._rebuild_snare_last_trigger: float = -999.0
        self._rebuild_active_pattern: str = "tilt_cross"
        self._rebuild_pattern_hold_until_bar: int = 0

        # ── Confidence-gated section state machine (from song structure research) ──
        # Multi-rate streaming analysis: fast onset stream + slow section stream
        self._section_energy_history: list = []   # rolling window of (time, energy, bass, mid, high, flux) tuples
        self._section_energy_window: float = 8.0  # seconds of history to keep (longer for stability)
        self._section_min_hold_bars: int = 8      # minimum BARS in a section before changing (research: ≥8 bars)
        self._section_min_hold_s: float = 3.0     # absolute minimum seconds (fallback for slow BPM)
        self._section_buildup_ramp_start: float = -999.0
        # Section probabilities (continuous, not discrete — per research §4)
        self._section_probs: dict = {"breakdown": 0.0, "verse": 0.5, "buildup": 0.0, "chorus": 0.0, "drop": 0.0}
        self._section_confidence: float = 0.5     # confidence in current section label
        self._section_stable: bool = True          # is section state stable? (for "soft landing")
        # Boundary detection with N-of-M confirmation (research §4: debounce + persistence)
        self._boundary_prob_history: list = []     # recent boundary probability values
        self._boundary_confirm_threshold: int = 3  # need 3 of last 5 frames above threshold
        self._boundary_confirm_window: int = 5
        self._boundary_last_confirmed: float = -999.0
        # Spectral flux onset detection (research §3: onset envelope + peak picking)
        self._onset_envelope: float = 0.0          # smoothed onset strength
        self._onset_peak_threshold: float = 0.02   # adaptive threshold for onset peaks
        self._onset_last_peak_time: float = -999.0
        self._onset_cooldown_s: float = 0.15       # minimum time between onset triggers
        # Running spectral flux for onset detection
        self._prev_spectral_frame: list = [0.0] * 5  # previous [e, b, m, h, f] for flux calc
        self._spectral_flux_running: float = 0.0

        # ── Position-aware fixture grouping (built on first update) ──
        self._rig_groups_built: bool = False
        self._rig_beam_movers: list = []      # beam_up fixtures sorted L→R
        self._rig_mid_movers: list = []       # mover_mid fixtures sorted L→R
        self._rig_washes: list = []           # wash_ds fixtures sorted L→R
        self._rig_floor_bars: list = []       # bar_floor sorted L→R
        self._rig_rear_bars: list = []        # bar_rear sorted L→R
        self._rig_strobes: list = []          # strobe fixtures
        self._rig_blinders: list = []         # blinder fixtures
        self._rig_spots: list = []            # spot fixtures
        self._rig_all_movers: list = []       # all movers sorted L→R
        self._rig_fixture_norm_x: dict = {}   # fixture_id → normalized x position (-1=left, +1=right)
        self._rig_fixture_sym_phase: dict = {} # fixture_id → symmetric phase (0=outside, 1=center)

        # ── Busking layer state (from research doc) ──
        # Bump layer: short intensity spikes on beats/downbeats
        self._bump_decay: float = 0.0          # current bump intensity (decays each frame)
        self._bump_last_beat_time: float = -999.0
        self._bump_last_downbeat_time: float = -999.0
        # FX accent layer: onset-triggered color hits + audience pops
        self._fx_onset_flash: float = 0.0      # onset flash intensity (decays)
        self._fx_last_onset_time: float = -999.0
        self._fx_onset_color: tuple = (1.0, 1.0, 1.0)  # color of current flash
        # Drop moment state
        self._drop_white_flash: float = 0.0    # white flash intensity at drop start (decays fast)
        self._drop_start_time: float = -999.0
        # Smoothed energy for layer density decisions (1-3s smoothing per research)
        self._smoothed_sig: float = 0.0
        # Dark-move prepositioning (programming research: "mark cue / move-in-black")
        self._dark_move_active: bool = False       # currently executing a dark move
        self._dark_move_start_time: float = -999.0
        self._dark_move_duration: float = 0.45     # seconds to complete dark move
        self._dark_move_prev_pattern: str = ""     # previous movement pattern
        self._dark_move_dim_suppress: float = 0.0  # dimmer suppression during dark move (0-1)
        # Strobe safety (programming research: Ofcom guidance: ≤3 flashes/sec audience-facing)
        self._strobe_flash_count: int = 0          # flashes in current 1-second window
        self._strobe_window_start: float = 0.0     # start of current counting window
        self._strobe_max_rate_hz: float = 3.0      # max flashes per second (Ofcom limit)
        self._strobe_last_flash_time: float = -999.0
        # Perceptual dimmer curve (programming research: non-linear for smooth fades)
        self._perceptual_gamma: float = 2.2        # gamma curve for perceptual dimmer

        # ── Look library (mood-tagged effect presets for variety) ──
        from .look_library import LookSelector
        self._look_selector = LookSelector()
        self._active_look = None       # current LookPreset
        self._look_last_bar: int = -1  # last bar we checked for a look change

        # ── Vocal analyzer integration ──
        self._vocal_analyzer = None  # set via set_vocal_analyzer()
        self._vocal_movement_mod: dict = {
            "bounce_intensity": 0.0,
            "tilt_accent": 0.0,
            "speed_modifier": 1.0,
            "amplitude_modifier": 1.0,
            "ethereal_slowdown": 1.0,
        }
        self._lyric_color_theme: dict = {}  # from vocal analyzer keyword matching

        # Pro lighting integration enabled flag
        self._pro_lighting_enabled = False

        # ML emotion mapping state (set by _apply_ml_data)
        self._ml_emotion_mapping = None

        # Confidence gates for ML-driven target switching
        self._ml_genre_gate = _TargetGateState(
            current=self.genre_manager.current_genre.value,
            current_confidence=1.0,
        )
        self._ml_section_gate = _TargetGateState(
            current=self.section_manager.current_section.value,
            current_confidence=1.0,
        )

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
        """Set rebuilt busker section and sync section manager immediately."""
        section_name = (section_name or "verse").lower()
        if section_name == self._rebuild_section:
            return
        self._rebuild_section = section_name
        self._rebuild_section_changed_at = self.time
        if self._pro_lighting_enabled:
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

    def _rebuild_update_intent(self, delta_time: float):
        """Confidence-gated section state machine with boundary probability.

        Based on song structure research (streaming Transformer + probabilistic
        post-processing design), implements a multi-rate analysis stack:

        FAST STREAM (every frame):
        - Spectral flux onset envelope for beat/accent triggers
        - Running energy/bass/mid/high for absolute tier
        - Onset peak picking with adaptive threshold and hysteresis

        SLOW STREAM (section analysis):
        - Continuous section probabilities (not discrete labels)
        - Boundary probability with N-of-M frame confirmation
        - ≥8 bar minimum dwell time (research: "enforce minimum dwell time")
        - "Soft landing": hold current look when confidence drops
        - Energy-gated bar cycling (standard 48-bar EDM structure)

        KEY PRINCIPLES FROM RESEARCH:
        - "Confidence-gated state + smoothing, not fire on argmax"
        - "Section probabilities feeding a conservative state machine"
        - "Soft landing on uncertainty: keep current look family"
        - "Boundary detection evaluated at tight tolerance (±0.5s not ±3s)"
        - "Minimum dwell time ≥8 bars unless confidence is very high"
        """
        if self.time < self._rebuild_manual_hold_until:
            return

        now = self.time
        dt = max(0.001, delta_time)
        e = float(self.audio_features.energy)
        b = float(self.audio_features.bass)
        m = float(self.audio_features.mid) if hasattr(self.audio_features, 'mid') else 0.0
        h = float(self.audio_features.high)
        f = float(getattr(self.audio_state, "spectral_flux", 0.0) or 0.0)
        beat = bool(self.audio_features.is_beat)
        bpm = max(60.0, float(self._smoothed_movement_bpm))
        beats_per_sec = bpm / 60.0
        bar_clock = int(now * beats_per_sec / 4.0)
        bars_in_section = int((now - self._rebuild_section_changed_at) * beats_per_sec / 4.0)

        # ══════════════════════════════════════════════════════════════
        #  FAST STREAM: Spectral flux onset envelope
        # ══════════════════════════════════════════════════════════════
        # Compute spectral flux as sum of positive differences (half-wave rectified)
        # This is the "onset strength / spectral flux" from research §3
        prev = self._prev_spectral_frame
        flux_raw = max(0.0, e - prev[0]) + max(0.0, b - prev[1]) + \
                   max(0.0, m - prev[2]) * 0.6 + max(0.0, h - prev[3]) * 0.3
        self._prev_spectral_frame = [e, b, m, h, f]

        # Smooth onset envelope with fast attack / slow decay (research §3)
        attack_rate = 25.0   # fast attack: ~40ms
        decay_rate = 4.0     # slow decay: ~250ms
        if flux_raw > self._onset_envelope:
            self._onset_envelope += (flux_raw - self._onset_envelope) * min(1.0, dt * attack_rate)
        else:
            self._onset_envelope *= max(0.0, 1.0 - dt * decay_rate)

        # Adaptive threshold: running mean of onset envelope + margin
        self._onset_peak_threshold += (self._onset_envelope * 0.6 - self._onset_peak_threshold) * min(1.0, dt * 1.5)
        self._onset_peak_threshold = max(0.008, self._onset_peak_threshold)

        # Peak picking with cooldown (research: "hysteresis + peak picking")
        is_onset_peak = (
            self._onset_envelope > self._onset_peak_threshold * 1.8 and
            (now - self._onset_last_peak_time) > self._onset_cooldown_s
        )
        if is_onset_peak:
            self._onset_last_peak_time = now

        # Smooth spectral flux for section analysis
        self._spectral_flux_running += (flux_raw - self._spectral_flux_running) * min(1.0, dt * 2.0)

        # ══════════════════════════════════════════════════════════════
        #  Rolling energy history (for slow-stream section analysis)
        # ══════════════════════════════════════════════════════════════
        self._section_energy_history.append((now, e, b, m, h, flux_raw))
        cutoff = now - self._section_energy_window
        self._section_energy_history = [
            x for x in self._section_energy_history if x[0] >= cutoff
        ]
        hist = self._section_energy_history
        n = len(hist)

        # ══════════════════════════════════════════════════════════════
        #  ABSOLUTE energy tier (composite signal weighted toward mid)
        # ══════════════════════════════════════════════════════════════
        sig = max(e, m * 0.55, 0.30 * e + 0.20 * b + 0.40 * m + 0.10 * h)
        if sig < 0.03 and m < 0.1:
            abs_tier = "silent"
        elif sig < 0.15 or m < 0.3:
            abs_tier = "low"
        elif sig < 0.35 or m < 0.6:
            abs_tier = "medium"
        elif sig < 0.55 or m < 0.8:
            abs_tier = "high"
        else:
            abs_tier = "peak"

        # ══════════════════════════════════════════════════════════════
        #  RELATIVE change detection (for boundary + drop impulse)
        # ══════════════════════════════════════════════════════════════
        de = e - self._rebuild_prev_energy
        db = b - self._rebuild_prev_bass
        dm = m - (hist[-2][3] if n >= 2 else m)

        # Impulse detection: large positive energy jump = potential drop
        impulse = max(de, db, dm * 0.5)
        has_impulse = impulse > 0.015 and sig > 0.1

        # Rising trend: compare old third vs new third of history
        rising = False
        falling = False
        if n >= 12:
            third = n // 3
            old_avg = sum(x[3] for x in hist[:third]) / max(1, third)
            new_avg = sum(x[3] for x in hist[2*third:]) / max(1, n - 2*third)
            diff = new_avg - old_avg
            rising = diff > 0.025
            falling = diff < -0.025

        # ══════════════════════════════════════════════════════════════
        #  BOUNDARY PROBABILITY (N-of-M frame confirmation)
        # ══════════════════════════════════════════════════════════════
        # Boundary = significant change in spectral character
        # Uses spectral flux running + energy delta as boundary signal
        boundary_signal = self._spectral_flux_running * 2.0 + abs(de) + abs(db)
        boundary_prob = min(1.0, boundary_signal / 0.15)  # normalize to 0-1
        self._boundary_prob_history.append(boundary_prob)
        if len(self._boundary_prob_history) > self._boundary_confirm_window:
            self._boundary_prob_history = self._boundary_prob_history[-self._boundary_confirm_window:]

        # N-of-M confirmation: need 3 of last 5 frames with boundary_prob > 0.5
        frames_above = sum(1 for p in self._boundary_prob_history if p > 0.5)
        boundary_confirmed = (
            frames_above >= self._boundary_confirm_threshold and
            (now - self._boundary_last_confirmed) > 2.0  # 2s debounce between boundaries
        )
        if boundary_confirmed:
            self._boundary_last_confirmed = now

        # ══════════════════════════════════════════════════════════════
        #  SECTION PROBABILITIES (continuous, research §4)
        # ══════════════════════════════════════════════════════════════
        # Compute raw "evidence" for each section based on audio features
        probs = {"breakdown": 0.0, "verse": 0.0, "buildup": 0.0, "chorus": 0.0, "drop": 0.0}

        # Breakdown evidence: low energy, falling trend
        probs["breakdown"] = max(0.0, 0.3 * (1.0 - sig / 0.3) + 0.3 * (1 if falling else 0) + 0.2 * (1 if abs_tier in {"silent", "low"} else 0))

        # Verse evidence: medium energy, stable
        probs["verse"] = max(0.0, 0.4 * (1.0 - abs(sig - 0.35) / 0.35) + 0.2 * (1 if not rising and not falling else 0) + 0.2 * (1 if abs_tier == "medium" else 0))

        # Buildup evidence: rising trend, medium-high energy
        probs["buildup"] = max(0.0, 0.5 * (1 if rising else 0) + 0.3 * (1 if abs_tier in {"medium", "high"} else 0) + 0.2 * min(1.0, self._spectral_flux_running / 0.05))

        # Chorus evidence: high energy, high onset density, stable
        probs["chorus"] = max(0.0, 0.4 * min(1.0, sig / 0.55) + 0.3 * (1 if abs_tier in {"high", "peak"} else 0) + 0.2 * (1 if not rising else 0))

        # Drop evidence: impulse + very high energy + bass
        probs["drop"] = max(0.0, 0.4 * (1 if has_impulse else 0) + 0.3 * min(1.0, sig / 0.6) + 0.3 * min(1.0, b / 0.5))

        # Normalize probabilities (softmax-like)
        total_p = sum(probs.values())
        if total_p > 0:
            for k in probs:
                probs[k] /= total_p

        # Smooth section probabilities (EMA, research: "stability requires smoothing")
        smooth_rate = 1.5  # ~700ms smoothing constant
        for k in probs:
            self._section_probs[k] += (probs[k] - self._section_probs[k]) * min(1.0, dt * smooth_rate)

        # ══════════════════════════════════════════════════════════════
        #  BAR-LOCKED CYCLING (standard 48-bar EDM structure)
        # ══════════════════════════════════════════════════════════════
        cycle_pos = bar_clock % 48
        if cycle_pos < 16:
            cycle_section = "verse"
        elif cycle_pos < 24:
            cycle_section = "buildup"
        elif cycle_pos < 40:
            cycle_section = "chorus"
        else:
            cycle_section = "breakdown"

        # ══════════════════════════════════════════════════════════════
        #  SECTION DECISION: confidence-gated state machine
        # ══════════════════════════════════════════════════════════════
        current = self._rebuild_section or "verse"
        time_in_current = now - self._rebuild_section_changed_at

        # Minimum hold: ≥8 bars OR absolute minimum seconds (whichever is longer)
        bar_duration = 4.0 / beats_per_sec  # seconds per bar
        min_hold_time = max(self._section_min_hold_s, self._section_min_hold_bars * bar_duration)

        # Find the winner from smoothed probabilities
        prob_winner = max(self._section_probs, key=self._section_probs.get)
        prob_confidence = self._section_probs.get(prob_winner, 0.0)

        # Section confidence = how dominant the winner is
        sorted_probs = sorted(self._section_probs.values(), reverse=True)
        margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else sorted_probs[0]
        self._section_confidence = margin
        self._section_stable = margin > 0.15  # stable if winner has >15% margin

        # ── DROP: impulse-triggered, overrides minimum hold ──
        if has_impulse and abs_tier in {"high", "peak"} and (now - self._rebuild_last_impact) > 3.0:
            self._rebuild_last_impact = now
            self._rebuild_drop_until = now + 4.0  # 4 bars of drop minimum
            target = "drop"
        elif now < self._rebuild_drop_until:
            target = "drop"
        # ── SILENT: always breakdown ──
        elif abs_tier == "silent":
            target = "breakdown"
        # ── RESPECT MINIMUM HOLD (unless confidence is very high) ──
        elif time_in_current < min_hold_time and prob_confidence < 0.55:
            target = current  # "soft landing": hold current section
        # ── BOUNDARY CONFIRMED + stable new section: transition ──
        elif boundary_confirmed and self._section_stable and prob_winner != current:
            target = prob_winner
        # ── HIGH CONFIDENCE winner (>55%): allow transition even without boundary ──
        elif prob_confidence > 0.55 and time_in_current >= min_hold_time and prob_winner != current:
            target = prob_winner
        # ── RISING TREND: override to buildup ──
        elif rising and abs_tier in {"medium", "high"} and time_in_current >= min_hold_time:
            target = "buildup"
        # ── LOW CONFIDENCE: use energy-gated bar cycling (conservative) ──
        elif not self._section_stable and time_in_current >= min_hold_time:
            # Gate cycle by absolute tier
            if abs_tier == "low":
                target = "breakdown" if cycle_section == "breakdown" else "verse"
            elif abs_tier == "medium":
                target = "verse" if cycle_section in {"chorus", "drop"} else cycle_section
            else:
                target = cycle_section
        else:
            target = current  # hold current (soft landing on uncertainty)

        # Track buildup ramp timing
        if target == "buildup" and current != "buildup":
            self._section_buildup_ramp_start = now
        elif target != "buildup":
            self._section_buildup_ramp_start = -999.0

        self._rebuild_set_section(target)
        self._rebuild_prev_energy = e
        self._rebuild_prev_bass = b

    # ──────────────────────────────────────────────────────────────────
    #  POSITION-AWARE RIG GROUPING
    # ──────────────────────────────────────────────────────────────────

    def _build_rig_groups(self):
        """Build position-aware fixture groups from the rig layout.

        Computes for each fixture:
        - norm_x: normalized x position (-1.0=far left, +1.0=far right)
        - sym_phase: symmetric phase (0.0=outermost, 1.0=center)
          This is the KEY to symmetric movement — left and right fixtures
          with the same sym_phase will mirror each other perfectly.
        """
        all_fixtures = self.fixtures.get_fixtures_in_group("all")

        def _sort_by_x(fixtures):
            return sorted(fixtures, key=lambda f: float(getattr(f, 'x', 0.0) or 0.0))

        def _is_mover(fx):
            ftype = str(getattr(fx, "fixture_type", "") or "").lower()
            return ftype in {"mover", "moving_head", "beam", "spot", "wash", "profile", "hybrid"}

        # Group by fixture ID prefix
        for f in all_fixtures:
            fid = str(getattr(f, "id", "") or "").lower()
            if fid.startswith("beam_up"):
                self._rig_beam_movers.append(f)
            elif fid.startswith("mover_mid"):
                self._rig_mid_movers.append(f)
            elif fid.startswith("wash_ds"):
                self._rig_washes.append(f)
            elif fid.startswith("bar_floor"):
                self._rig_floor_bars.append(f)
            elif fid.startswith("bar_rear"):
                self._rig_rear_bars.append(f)
            elif fid.startswith("strobe"):
                self._rig_strobes.append(f)
            elif fid.startswith("blinder"):
                self._rig_blinders.append(f)
            elif fid.startswith("spot"):
                self._rig_spots.append(f)

        # Sort each group left-to-right by x position
        self._rig_beam_movers = _sort_by_x(self._rig_beam_movers)
        self._rig_mid_movers = _sort_by_x(self._rig_mid_movers)
        self._rig_washes = _sort_by_x(self._rig_washes)
        self._rig_floor_bars = _sort_by_x(self._rig_floor_bars)
        self._rig_rear_bars = _sort_by_x(self._rig_rear_bars)
        self._rig_strobes = _sort_by_x(self._rig_strobes)
        self._rig_blinders = _sort_by_x(self._rig_blinders)
        self._rig_spots = _sort_by_x(self._rig_spots)

        # All movers = beams + mids + washes + spots (anything that pans/tilts)
        self._rig_all_movers = _sort_by_x([
            f for f in all_fixtures if _is_mover(f)
        ])

        # Compute normalized x and symmetric phase for ALL fixtures
        # Find stage bounds from all fixture positions
        all_x = [float(getattr(f, 'x', 0.0) or 0.0) for f in all_fixtures]
        if all_x:
            x_min = min(all_x)
            x_max = max(all_x)
            x_range = max(0.01, x_max - x_min)
            x_center = (x_min + x_max) / 2.0
        else:
            x_min = x_max = x_center = 0.0
            x_range = 1.0

        for f in all_fixtures:
            fid = str(getattr(f, "id", "") or "")
            fx = float(getattr(f, 'x', 0.0) or 0.0)

            # norm_x: -1 (far left) to +1 (far right)
            norm_x = (fx - x_center) / (x_range / 2.0) if x_range > 0.01 else 0.0
            norm_x = max(-1.0, min(1.0, norm_x))
            self._rig_fixture_norm_x[fid] = norm_x

            # sym_phase: 0.0 = outermost edge, 1.0 = center
            # abs(norm_x) = 0 at center, 1 at edge → sym_phase = 1 - abs(norm_x)
            self._rig_fixture_sym_phase[fid] = 1.0 - abs(norm_x)

        self._rig_groups_built = True

    def _compute_group_symmetric_phase(self, fixture, group_list):
        """Compute symmetric phase offset for a fixture within its sorted group.

        For a group sorted L→R: [L4, L3, L2, L1, R1, R2, R3, R4]
        Returns phase offsets that make left and right mirror each other:
        L4=0.0, L3=0.143, L2=0.286, L1=0.429, R1=0.429, R2=0.286, R3=0.143, R4=0.0

        This is how MA2 does it: the symmetric phase creates identical motion
        on both sides, with center fixtures leading and edges following.
        """
        if not group_list:
            return 0.5
        n = len(group_list)
        try:
            idx = group_list.index(fixture)
        except ValueError:
            return 0.5
        # Position 0..1 within the group
        frac = idx / max(1, n - 1) if n > 1 else 0.5
        # Mirror: fold around center → 0=edge, 1=center
        mirror = 1.0 - abs(2.0 * frac - 1.0)
        return mirror

    # ──────────────────────────────────────────────────────────────────
    #  BPM-LOCKED SYMMETRIC MOVEMENT PATTERNS
    # ──────────────────────────────────────────────────────────────────

    def _bpm_phase(self, bpm, beats=1.0, offset=0.0):
        """Get a 0→1 phase that cycles exactly every N beats at the current BPM.

        This is the fundamental building block: ALL movement timing comes from
        this function, ensuring everything locks to the music's tempo.
        """
        beats_elapsed = self.time * (bpm / 60.0)
        return ((beats_elapsed / beats) + offset) % 1.0

    def _symmetric_pan_tilt(self, norm_x, sym_phase, bpm, pattern, section, section_time):
        """Compute symmetric pan/tilt for a fixture based on its stage position.

        norm_x: -1 (far left) to +1 (far right) — determines mirror direction
        sym_phase: 0 (edge) to 1 (center) — determines phase offset
        bpm: current tempo
        pattern: which movement pattern to use
        section: current song section (affects amplitude/speed)
        section_time: seconds since section started (for buildups)

        Returns (pan_degrees, tilt_degrees)

        KEY PRINCIPLE: Left fixtures (norm_x < 0) get NEGATED pan vs right fixtures,
        creating perfect left-right symmetry. The sym_phase offsets create the
        "wave" effect where center leads and edges follow (or vice versa).
        """
        # Section-based amplitude and speed multipliers
        amp_mult = {"breakdown": 0.5, "verse": 0.7, "buildup": 0.85, "chorus": 1.0, "drop": 1.0}.get(section, 0.7)
        speed_mult = {"breakdown": 0.5, "verse": 0.75, "buildup": 1.0, "chorus": 1.0, "drop": 1.2}.get(section, 0.75)

        # Buildup acceleration: speed increases over time during buildup
        if section == "buildup":
            buildup_t = min(1.0, section_time / 16.0)
            speed_mult = 0.6 + 0.8 * buildup_t  # 0.6x → 1.4x over 16 seconds
            amp_mult = 0.6 + 0.5 * buildup_t     # 0.6x → 1.1x

        # Vocal cadence modulation: singing controls bounce & amplitude
        vmod = self._vocal_movement_mod
        speed_mult *= vmod.get("speed_modifier", 1.0)
        amp_mult *= vmod.get("amplitude_modifier", 1.0)

        # Mirror sign: left side pans opposite to right side
        mirror = 1.0 if norm_x >= 0 else -1.0

        # Phase offset based on symmetric position (center leads)
        # center_lead: center fixtures are ahead in the cycle
        center_lead = sym_phase * 0.25  # center is 1/4 cycle ahead of edges

        if pattern == "sync_sweep":
            # All fixtures sweep together L→R in unison, perfectly synchronized
            # The simplest and most powerful EDM pattern
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult)
            pan = 70.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = -10.0 + 25.0 * amp_mult * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "mirror_sweep":
            # Left and right sweep in opposite directions (crossing in center)
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult)
            pan = mirror * 65.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = -5.0 + 30.0 * amp_mult * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "symmetric_fan":
            # Fixtures fan out from center, then back in — like opening/closing hands
            # Center fixtures have small swing, edges have large swing
            edge_factor = 1.0 - sym_phase  # 0 at center, 1 at edges
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult)
            swing = math.sin(2.0 * math.pi * phase)
            pan = mirror * 75.0 * amp_mult * edge_factor * swing
            tilt = -15.0 + 20.0 * amp_mult * (0.5 + 0.5 * swing)
            return (pan, tilt)

        elif pattern == "tilt_wave":
            # Pan stays in symmetric fan position, tilt does a wave from center→edges
            edge_factor = 1.0 - sym_phase
            pan = mirror * 40.0 * amp_mult * edge_factor
            phase = self._bpm_phase(bpm, beats=2.0 / speed_mult, offset=center_lead)
            tilt = -10.0 + 45.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "symmetric_circle":
            # All fixtures do circles, but left mirrors right for perfect symmetry
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult, offset=center_lead)
            pan = mirror * 60.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = 0.0 + 40.0 * amp_mult * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "cross_tilt":
            # Odd fixtures tilt up while even tilt down, then swap — "crossing" effect
            # Pan stays in symmetric spread
            edge_factor = 1.0 - sym_phase
            pan = mirror * 50.0 * amp_mult * edge_factor
            # Use norm_x sign for odd/even determination (left=down first, right=up first)
            cross_sign = 1.0 if norm_x >= 0 else -1.0
            phase = self._bpm_phase(bpm, beats=2.0 / speed_mult)
            tilt = 5.0 + cross_sign * 35.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "ballyhoo":
            # Figure-8 pattern with symmetric mirroring — the classic "big show" look
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult, offset=center_lead)
            pan = mirror * 80.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = 5.0 + 45.0 * amp_mult * math.sin(4.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "center_burst":
            # Drop pattern: all fixtures point center then EXPLODE outward on beat
            phase = self._bpm_phase(bpm, beats=1.0 / speed_mult)
            # Sharp triangle wave: snap to center then sweep out
            tri = abs(2.0 * phase - 1.0)  # 0→1→0 triangle
            pan = mirror * 90.0 * amp_mult * tri * (1.0 - sym_phase + 0.3)
            tilt = 15.0 - 40.0 * amp_mult * (1.0 - tri)
            return (pan, tilt)

        elif pattern == "fly_out":
            # ETHEREAL fly-out: fixtures slowly sweep to extreme positions
            # Very slow (8-16 bars per cycle), wide amplitude, dreamy
            phase = self._bpm_phase(bpm, beats=16.0 / speed_mult, offset=center_lead * 0.5)
            pan = mirror * 120.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = -25.0 + 55.0 * amp_mult * (0.5 + 0.5 * math.cos(2.0 * math.pi * phase * 0.5))
            return (pan, tilt)

        elif pattern == "slow_breathe":
            # Ethereal breathing: all fixtures gently rise and fall in tilt
            # Pan stays wide and static, tilt oscillates very slowly
            edge_factor = 1.0 - sym_phase
            pan = mirror * 80.0 * amp_mult * edge_factor  # wide static spread
            phase = self._bpm_phase(bpm, beats=8.0 / speed_mult, offset=center_lead)
            # Sinusoidal breathing: slow up/down like lungs
            tilt = -20.0 + 50.0 * amp_mult * (0.5 + 0.5 * math.sin(2.0 * math.pi * phase))
            return (pan, tilt)

        elif pattern == "cascade":
            # Cascade: fixtures sweep one after another from center outward
            # Creates a "ripple" or "waterfall" effect
            # Edge fixtures are delayed behind center ones
            delay = (1.0 - sym_phase) * 0.4  # edges are 40% cycle behind center
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult, offset=delay)
            pan = mirror * 55.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = -5.0 + 35.0 * amp_mult * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "figure_eight_wide":
            # Wide figure-8 with staggered phase — more organic than ballyhoo
            phase = self._bpm_phase(bpm, beats=8.0 / speed_mult, offset=center_lead * 0.6)
            pan = mirror * 100.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = 10.0 + 35.0 * amp_mult * math.sin(4.0 * math.pi * phase + 0.5)
            return (pan, tilt)

        elif pattern == "stagger_sweep":
            # Left→right stagger: each fixture starts its sweep slightly after its neighbor
            # Creates a "wave" that travels across the rig
            position_delay = abs(norm_x) * 0.35  # further from center = more delay
            phase = self._bpm_phase(bpm, beats=4.0 / speed_mult, offset=position_delay)
            pan = mirror * 60.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = -10.0 + 30.0 * amp_mult * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

        elif pattern == "snap_look":
            # Snap to discrete positions on beat boundaries (like MA2 position presets)
            # Moves between 4 "look" positions, snapping on each beat
            beat_idx = int(self._bpm_phase(bpm, beats=1.0) * 0.99)
            bar_idx = int(self._bpm_phase(bpm, beats=4.0) * 4.0) % 4
            looks = [
                (mirror * 60.0 * amp_mult, -15.0),   # wide out
                (mirror * 20.0 * amp_mult, 25.0),     # center-ish, up
                (mirror * -30.0 * amp_mult, -5.0),    # cross-over
                (0.0, 35.0 * amp_mult),                # straight up
            ]
            target_pan, target_tilt = looks[bar_idx]
            # Smooth the snap with a fast interpolation
            snap_speed = 0.15  # fast but not instant
            current_phase = self._bpm_phase(bpm, beats=1.0)
            if current_phase < snap_speed:
                # In snap zone: interpolate
                t = current_phase / snap_speed
                prev_idx = (bar_idx - 1) % 4
                prev_pan, prev_tilt = looks[prev_idx]
                pan = prev_pan + (target_pan - prev_pan) * t
                tilt = prev_tilt + (target_tilt - prev_tilt) * t
            else:
                pan = target_pan
                tilt = target_tilt
            return (pan, tilt)

        elif pattern == "audience_scan":
            # Slow scan across the audience area (low tilt, wide pan)
            # Perfect for washes during verses — makes the crowd feel included
            phase = self._bpm_phase(bpm, beats=8.0 / speed_mult, offset=center_lead * 0.3)
            pan = mirror * 70.0 * amp_mult * math.sin(2.0 * math.pi * phase)
            tilt = 30.0 + 15.0 * amp_mult * math.cos(2.0 * math.pi * phase * 2.0)
            return (pan, tilt)

        else:
            # Default: gentle symmetric sweep
            phase = self._bpm_phase(bpm, beats=8.0)
            pan = mirror * 30.0 * math.sin(2.0 * math.pi * phase)
            tilt = -10.0 + 15.0 * math.cos(2.0 * math.pi * phase)
            return (pan, tilt)

    # ──────────────────────────────────────────────────────────────────
    #  MAIN FIXTURE UPDATE (position-aware, BPM-locked, symmetric)
    # ──────────────────────────────────────────────────────────────────

    def _update_fixtures_rebuild(self, delta_time: float):
        """Layered busking engine following professional lighting research.

        Architecture (from Intelligent Busking Lighting Research Pack):
        - Layer 1: BASE WASH — mood color field, slow fades between color schemes
        - Layer 2: AERIAL MOVEMENT — symmetric BPM-locked patterns for movers
        - Layer 3: CHASE — traveling dimmer across fixture lines at BPM rate
        - Layer 4: BUMP — short beat-quantized intensity spikes on downbeats
        - Layer 5: AUDIENCE — blinders/strobes for big moments only
        - Layer 6: FX ACCENT — onset-triggered color hits, drop white-flash

        Key principles:
        - Change ONE thing at a time, let it breathe for a musical unit
        - Land changes on downbeats and phrase boundaries
        - Breakdown is DARK so drops feel HUGE (contrast = drama)
        - Use hysteresis: turn on at threshold, don't turn off until lower threshold
        - Color SCHEMES not single colors: warm/cool contrast, neon pairs
        - Spectral centroid → color temperature (bright timbre = cooler/sharper)
        """
        all_fixtures = self.fixtures.get_fixtures_in_group("all")
        total = len(all_fixtures)
        if total <= 0:
            self._fixture_state_snapshot = []
            return

        if not self._rig_groups_built:
            self._build_rig_groups()

        section = (self._rebuild_section or "verse").lower()
        bpm = max(60.0, min(190.0, float(self._smoothed_movement_bpm)))
        energy = max(0.0, min(1.0, float(self.audio_features.energy)))
        bass = max(0.0, min(1.0, float(self.audio_features.bass)))
        mid = max(0.0, min(1.0, float(self.audio_features.mid)))
        high = max(0.0, min(1.0, float(self.audio_features.high)))
        beat = bool(self.audio_features.is_beat)
        now = self.time
        dt = delta_time
        section_time = now - self._rebuild_section_changed_at

        # BPM-derived clocks (ALL timing from these)
        beats_elapsed = now * (bpm / 60.0)
        beat_phase = beats_elapsed % 1.0
        bar_phase = (beats_elapsed / 4.0) % 1.0
        bar_clock = int(beats_elapsed / 4.0)
        phrase_clock = bar_clock // 4           # 4-bar phrase
        sixteenth_phase = (beats_elapsed * 4.0) % 1.0
        eighth_phase = (beats_elapsed * 2.0) % 1.0

        # Effective energy (scaled up for weak browser audio)
        eff_energy = max(energy, mid * 0.4)
        eff_bass = max(bass, mid * 0.12)

        # Smooth signal for layer density (1-3s smoothing per research §6.2)
        self._smoothed_sig += (eff_energy - self._smoothed_sig) * min(1.0, dt * 0.5)

        # ══════════════════════════════════════════════════════════════
        #  LAYER 4: BUMP — beat-quantized intensity spikes
        # ══════════════════════════════════════════════════════════════
        # Research: "Land bumps on downbeats; require higher confidence
        #  than beat for downbeat accent; reduce to subtle intensity
        #  modulation if beat confidence low"
        is_beat_start = beat_phase < 0.08  # first 8% of beat (wider gate for reliability)
        is_downbeat = bar_phase < 0.02     # first beat of bar
        is_phrase_start = bar_phase < 0.02 and (bar_clock % 4 == 0)

        # Bump intensity varies by section — breakdown ZERO for contrast
        bump_strength = {
            "breakdown": 0.0, "verse": 0.15, "buildup": 0.22,
            "chorus": 0.30, "drop": 0.40
        }.get(section, 0.15)
        downbeat_extra = 0.20 if section in {"chorus", "drop"} else 0.10
        phrase_extra = 0.10 if section in {"chorus", "drop"} else 0.05

        if is_phrase_start:
            self._bump_decay = bump_strength + downbeat_extra + phrase_extra
        elif is_downbeat:
            self._bump_decay = bump_strength + downbeat_extra
        elif is_beat_start:
            self._bump_decay = max(self._bump_decay, bump_strength)
        # Fast exponential decay (~80ms half-life for tight bumps)
        self._bump_decay *= max(0.0, 1.0 - dt * 22.0)

        # Onset bump: spectral flux onset peaks also trigger bumps
        # (research: "onset strength drives bumps" — complementary to beat)
        onset_is_peak = (
            self._onset_envelope > self._onset_peak_threshold * 1.8 and
            (now - self._onset_last_peak_time) < 0.03  # just peaked
        )
        if onset_is_peak and section in {"chorus", "drop", "buildup"}:
            onset_bump = 0.15 if section == "drop" else 0.08
            self._bump_decay = max(self._bump_decay, onset_bump)

        # ══════════════════════════════════════════════════════════════
        #  LAYER 6: FX ACCENT — onset-triggered color hits + drop flash
        # ══════════════════════════════════════════════════════════════
        # Research: "Short sparkles, audience blinders; cooldowns to
        #  avoid seizure-risk patterns"
        # Use spectral flux onset envelope (not raw energy delta) for triggers
        onset_strong = (
            self._onset_envelope > self._onset_peak_threshold * 2.5 and
            (now - self._fx_last_onset_time) > 0.35  # 350ms debounce
        )
        if onset_strong and section in {"chorus", "drop", "buildup"}:
            self._fx_last_onset_time = now
            self._fx_onset_flash = 0.7 if section == "drop" else 0.4
            self._fx_onset_color = (1.0, 1.0, 1.0)  # white flash on onset

        # Decay onset flash (fast: ~125ms)
        self._fx_onset_flash *= max(0.0, 1.0 - dt * 8.0)

        # Drop white flash: fires ONCE at drop start, decays over ~1.2s
        if section == "drop" and section_time < 0.05:
            self._drop_white_flash = 1.0
            self._drop_start_time = now
        self._drop_white_flash *= max(0.0, 1.0 - dt * 2.5)

        # ══════════════════════════════════════════════════════════════
        #  LAYER 5: STROBE / AUDIENCE policy with SAFETY RATE CAP
        # ══════════════════════════════════════════════════════════════
        # Programming research: "Ofcom guidance: >3 flashes/second in certain
        #  conditions prohibited; encode as hard constraint for audience-facing strobes"
        policy = str(getattr(self.config, "accessibility_mode", "performance") or "performance").lower()
        venue_mode = str(getattr(self.config, "venue_mode", "concert") or "concert").lower()
        camera_mode = bool(getattr(self.config, "camera_mode", False))
        visibility_first = venue_mode in {"theatre", "broadcast", "corporate"}
        strobe_ok = (policy not in {"no_strobe", "off"}) and (not camera_mode) and (not visibility_first)
        strobe_enabled = bool(self.config.strobe_enabled) and strobe_ok

        # Safety rate cap: count flashes in 1-second sliding window
        if now - self._strobe_window_start > 1.0:
            self._strobe_flash_count = 0
            self._strobe_window_start = now

        # Drop strobe: 8th-note BPM-locked flashing, GATED by safety cap
        # (research: "not 16th — too fast; 8th note keeps it musical and safe")
        drop_strobe_on = strobe_enabled and section == "drop"
        raw_flash = eighth_phase < 0.25
        # Apply safety rate cap: suppress flash if we've hit the limit
        if raw_flash and self._strobe_flash_count >= int(self._strobe_max_rate_hz):
            raw_flash = False  # suppress — too many flashes this second
        if raw_flash and drop_strobe_on and (now - self._strobe_last_flash_time) > 0.08:
            self._strobe_flash_count += 1
            self._strobe_last_flash_time = now
        drop_strobe_flash = drop_strobe_on and raw_flash

        # ══════════════════════════════════════════════════════════════
        #  LAYER 3: CHASE + DIMMER EFFECTS (multiple types)
        # ══════════════════════════════════════════════════════════════
        # look is set by _active_look from look library (may be None)
        look = self._active_look
        look_chase_dir = look.chase_direction if look is not None else "forward"
        if look is not None and hasattr(look, 'chase_beats'):
            chase_beats = look.chase_beats
            chase_width = look.chase_width
            chase_intensity = look.chase_intensity
        else:
            chase_beats = {"breakdown": 8.0, "verse": 4.0, "buildup": 2.0, "chorus": 2.0, "drop": 1.0}.get(section, 4.0)
            chase_width = {"breakdown": 0.35, "verse": 0.22, "buildup": 0.18, "chorus": 0.15, "drop": 0.12}.get(section, 0.22)
            chase_intensity = {"breakdown": 0.20, "verse": 0.35, "buildup": 0.45, "chorus": 0.50, "drop": 0.55}.get(section, 0.35)
        if section == "buildup":
            buildup_t = min(1.0, section_time / 16.0)
            chase_beats = max(0.5, chase_beats - chase_beats * 0.6 * buildup_t)
        chase_pos = self._bpm_phase(bpm, beats=chase_beats)

        # Detect ethereal sub-state (from vocal analyzer or audio character)
        # Must be computed BEFORE dimmer effect selection and movement selection
        is_ethereal_state = getattr(getattr(self, '_vocal_analyzer', None), 'state', None)
        ethereal_active = False
        if is_ethereal_state and is_ethereal_state.is_ethereal:
            ethereal_active = True
        elif section == "breakdown":
            if eff_bass < 0.10 and self._onset_envelope < 0.015 and high > mid * 0.3:
                ethereal_active = True

        # Dimmer effect type rotates every 4 bars for variety
        # Types: "chase" (traveling gaussian), "odd_even" (alternating),
        #        "circular" (wraps around), "ramp" (gradual rise/fall)
        dimmer_effect_types = ["chase", "odd_even", "circular", "ramp"]
        dimmer_effect_idx = (bar_clock // 4) % len(dimmer_effect_types)
        dimmer_effect_type = dimmer_effect_types[dimmer_effect_idx]
        # During breakdowns and ethereal, skip dimmer effects
        if section in {"breakdown"} or ethereal_active:
            dimmer_effect_type = "none"

        # ══════════════════════════════════════════════════════════════
        #  LAYER 2: MOVEMENT PATTERN selection (rotate every 8 bars)
        #  + DARK-MOVE prepositioning on pattern change
        # ══════════════════════════════════════════════════════════════
        # Programming research: "mark cue = preposition with dark move
        #  before intensity rise; execute non-intensity changes while
        #  intensity is zero"

        effective_section = "ethereal" if ethereal_active and section == "breakdown" else section

        # ── LOOK LIBRARY: select a mood-appropriate look ──
        # Get current mood from lyric theme (or default to section-derived mood)
        lyric_mood = self._lyric_color_theme.get("mood", "")
        if not lyric_mood:
            lyric_mood = {"breakdown": "ethereal", "verse": "chill", "buildup": "party",
                          "chorus": "party", "drop": "aggressive", "ethereal": "ethereal"}.get(effective_section, "")

        # Check for new look on section change or every 8 bars
        force_new_look = (bar_clock != self._look_last_bar and bar_clock % 8 == 0)
        section_just_changed = (now - self._rebuild_section_changed_at) < 0.1
        if section_just_changed:
            force_new_look = True
        self._look_last_bar = bar_clock

        new_look = self._look_selector.select_look(
            section=effective_section, energy=eff_energy,
            mood=lyric_mood, bar_clock=bar_clock, force_new=force_new_look
        )
        if new_look is not None:
            self._active_look = new_look

        # Use look parameters if available, fallback to defaults
        look = self._active_look
        if look is not None:
            active_pattern = look.movement_pattern
            chase_beats = look.chase_beats
            chase_width = look.chase_width
            chase_intensity = look.chase_intensity
            bump_strength_override = look.bump_strength
            look_chase_dir = look.chase_direction
        else:
            # Fallback: section-based pattern selection (original behavior)
            section_patterns = {
                "breakdown":  ["slow_breathe", "fly_out", "tilt_wave"],
                "ethereal":   ["fly_out", "slow_breathe", "audience_scan"],
                "verse":      ["mirror_sweep", "symmetric_fan", "tilt_wave", "audience_scan", "cascade"],
                "buildup":    ["symmetric_circle", "cross_tilt", "mirror_sweep", "stagger_sweep"],
                "chorus":     ["ballyhoo", "symmetric_circle", "mirror_sweep", "symmetric_fan",
                               "figure_eight_wide", "cascade", "snap_look"],
                "drop":       ["center_burst", "ballyhoo", "sync_sweep", "stagger_sweep"],
            }
            patterns = section_patterns.get(effective_section, ["sync_sweep"])
            pattern_idx = (bar_clock // 8) % len(patterns)
            active_pattern = patterns[pattern_idx]
            look_chase_dir = "forward"

        # Dark-move: when pattern changes, briefly suppress dimmer so
        # movers reposition without visible motion artifacts
        if active_pattern != self._dark_move_prev_pattern and self._dark_move_prev_pattern != "":
            self._dark_move_active = True
            self._dark_move_start_time = now
            self._dark_move_dim_suppress = 0.6  # suppress 60% of dimmer during move
        self._dark_move_prev_pattern = active_pattern

        # Dark move fades out over duration
        if self._dark_move_active:
            move_progress = (now - self._dark_move_start_time) / self._dark_move_duration
            if move_progress >= 1.0:
                self._dark_move_active = False
                self._dark_move_dim_suppress = 0.0
            else:
                # Cosine fade: smooth 0→1 suppress then release
                self._dark_move_dim_suppress = 0.5 * (1.0 + math.cos(math.pi * move_progress))

        # ══════════════════════════════════════════════════════════════
        #  LAYER 1: COLOR SCHEME — mood-aware, spectral-centroid-driven
        # ══════════════════════════════════════════════════════════════
        # "Pick schemes (pairs/triads) not single colors; manage dominance
        #  and contrast" (§2.1, Rutherford 2020)
        #
        # Color temperature from spectral centroid:
        # high frequencies bright → cooler/sharper colors
        # low frequencies dominant → warmer colors
        spectral_balance = (high - bass)  # positive = bright timbre, negative = warm
        warmth = max(0.0, min(1.0, 0.5 - spectral_balance * 2.0))  # 0=cool, 1=warm

        # 6 color SCHEMES (pairs), rotate every 8 bars
        # Each scheme has a dominant + accent following Rutherford's color theory
        color_schemes = [
            # Scheme 0: Cyan dominant / Hot pink accent (cool, high-energy)
            (RGB(0.0, 0.85, 1.0), RGB(1.0, 0.0, 0.55)),
            # Scheme 1: Deep blue dominant / Emerald accent (cool, mysterious)
            (RGB(0.0, 0.25, 1.0), RGB(0.0, 1.0, 0.45)),
            # Scheme 2: Red-orange dominant / Gold accent (warm, aggressive)
            (RGB(1.0, 0.1, 0.0), RGB(1.0, 0.7, 0.0)),
            # Scheme 3: Violet dominant / Cyan accent (cool, ethereal)
            (RGB(0.55, 0.0, 1.0), RGB(0.0, 0.9, 1.0)),
            # Scheme 4: Magenta dominant / Electric blue accent (neon pair)
            (RGB(1.0, 0.0, 0.55), RGB(0.0, 0.15, 1.0)),
            # Scheme 5: Lime dominant / Amber accent (warm, festival)
            (RGB(0.3, 1.0, 0.0), RGB(1.0, 0.8, 0.0)),
        ]
        scheme_idx = (bar_clock // 8) % len(color_schemes)
        color_dominant, color_accent = color_schemes[scheme_idx]

        # ── LYRIC THEME OVERRIDE ──
        # If Whisper detected keywords (e.g. "girls"→pink, "sad"→blue),
        # blend the lyric-driven colors over the default scheme
        lyric_theme = self._lyric_color_theme
        lyric_confidence = float(lyric_theme.get("confidence", 0.0))
        if lyric_confidence > 0.15:
            lyric_dom = lyric_theme.get("dominant", (1.0, 1.0, 1.0))
            lyric_acc = lyric_theme.get("accent", (1.0, 1.0, 1.0))
            lyric_rgb_dom = RGB(lyric_dom[0], lyric_dom[1], lyric_dom[2])
            lyric_rgb_acc = RGB(lyric_acc[0], lyric_acc[1], lyric_acc[2])
            # Blend strength proportional to confidence (max 70% override)
            blend = min(0.70, lyric_confidence * 0.8)
            color_dominant = color_dominant.blend(lyric_rgb_dom, blend)
            color_accent = color_accent.blend(lyric_rgb_acc, blend)
            # Also adjust warmth from lyric theme
            warmth = warmth * (1.0 - blend) + lyric_theme.get("warmth", 0.5) * blend

        # Adjust color temperature based on spectral centroid
        # Warm timbre → push dominant toward warmer hue
        if warmth > 0.6:
            color_dominant = color_dominant.blend(RGB(1.0, 0.4, 0.0), (warmth - 0.6) * 0.5)
        elif warmth < 0.3:
            color_dominant = color_dominant.blend(RGB(0.0, 0.5, 1.0), (0.3 - warmth) * 0.5)

        # Section mood overlay (the "emotion" of the section)
        section_mood = {
            "breakdown": RGB(0.03, 0.08, 0.5),   # deep dark blue — VERY dim
            "verse":     RGB(0.0, 0.55, 0.5),     # teal — cool and composed
            "buildup":   RGB(0.5, 0.0, 0.85),     # violet — tension
            "chorus":    RGB(1.0, 0.0, 0.6),      # hot pink — maximum energy
            "drop":      RGB(1.0, 1.0, 1.0),      # white — impact
        }.get(section, RGB(0.5, 0.5, 1.0))

        # ══════════════════════════════════════════════════════════════
        #  UPDATE GOBO ENGINE
        # ══════════════════════════════════════════════════════════════
        self.gobo.update(
            delta_time=dt, bpm=bpm, energy=energy, bass=bass,
            section=section, bar_clock=bar_clock, beat_phase=beat_phase,
        )

        # ══════════════════════════════════════════════════════════════
        #  PER-FIXTURE RENDERING
        # ══════════════════════════════════════════════════════════════
        # Section-level base intensity (the KEY to contrast/drama)
        # "Restraint: keep some tools in reserve so the show can build" (§1.1)
        section_base_dim = {
            "breakdown": 0.15,    # VERY dark — reserve for impact
            "verse":     0.50,    # moderate — comfortable
            "buildup":   0.60,    # rising
            "chorus":    0.80,    # bright
            "drop":      0.95,    # MAXIMUM
        }.get(section, 0.50)

        snapshot = []

        for i, fixture in enumerate(all_fixtures):
            fid = str(getattr(fixture, "id", "") or "")
            fid_lower = fid.lower()
            ftype = str(getattr(fixture, "fixture_type", "") or "").lower()
            is_mover = ftype in {"mover", "moving_head", "beam", "spot", "wash", "profile", "hybrid"}
            is_bar = "bar" in fid_lower
            is_strobe_fix = "strobe" in fid_lower
            is_blinder = "blinder" in fid_lower
            is_wash = "wash" in fid_lower
            is_beam = "beam" in fid_lower

            norm_x = self._rig_fixture_norm_x.get(fid, 0.0)
            sym_phase = self._rig_fixture_sym_phase.get(fid, 0.5)

            # ── LAYER 2: MOVEMENT (symmetric, BPM-locked) ────────────
            if is_mover:
                if fixture in self._rig_beam_movers:
                    gp = self._compute_group_symmetric_phase(fixture, self._rig_beam_movers)
                elif fixture in self._rig_mid_movers:
                    gp = self._compute_group_symmetric_phase(fixture, self._rig_mid_movers)
                elif fixture in self._rig_washes:
                    gp = self._compute_group_symmetric_phase(fixture, self._rig_washes)
                elif fixture in self._rig_spots:
                    gp = self._compute_group_symmetric_phase(fixture, self._rig_spots)
                else:
                    gp = sym_phase

                pan, tilt = self._symmetric_pan_tilt(
                    norm_x, gp, bpm, active_pattern, section, section_time
                )
                # Vocal cadence: add bounce/tilt accent from singing rhythm
                vocal_bounce = self._vocal_movement_mod.get("bounce_intensity", 0.0)
                vocal_tilt_accent = self._vocal_movement_mod.get("tilt_accent", 0.0)
                if vocal_bounce > 0.01:
                    # Bounce: quick tilt pop on vocal rhythm, scaled by beat phase
                    bounce_wave = math.sin(2.0 * math.pi * beat_phase * 2.0) * vocal_bounce * 8.0
                    tilt += bounce_wave
                if abs(vocal_tilt_accent) > 0.01:
                    # Rising melody → fixtures look up; falling → look down
                    tilt += vocal_tilt_accent * 12.0

                fixture.pan = max(-270.0, min(270.0, float(pan)))
                fixture.tilt = max(-135.0, min(135.0, float(tilt)))
            else:
                fixture.pan = 0.0
                fixture.tilt = 0.0

            # ── DIMMER: combine layers ────────────────────────────────
            # Layer 1: Section base intensity
            dim = section_base_dim

            # Layer 3: DIMMER EFFECTS — multiple types for variety
            fixture_position = i / max(1, total - 1)  # 0.0=first fixture, 1.0=last
            dimmer_fx_val = 0.0

            if dimmer_effect_type == "chase":
                # CHASE: traveling gaussian spotlight LEFT→RIGHT through rig
                # Direction from look or cycling
                chase_dir = look_chase_dir if look is not None else ["forward", "bounce", "center_out"][(bar_clock // 4) % 3]
                if chase_dir == "bounce":
                    cp = chase_pos * 2.0
                    cp = cp if cp <= 1.0 else (2.0 - cp)
                elif chase_dir == "center_out":
                    fp = abs(fixture_position - 0.5) * 2.0
                    cp = chase_pos
                    fixture_position_local = fp
                else:
                    cp = chase_pos
                if chase_dir == "center_out":
                    cd = abs(fixture_position_local - cp)
                else:
                    cd = abs(fixture_position - cp)
                cd = min(cd, 1.0 - cd)
                dimmer_fx_val = math.exp(-(cd ** 2) / (2.0 * chase_width ** 2)) * chase_intensity

            elif dimmer_effect_type == "odd_even":
                # ODD/EVEN: alternating fixtures flash on/off on beat
                # Even fixtures bright on beat 1&3, odd on beat 2&4
                is_even = (i % 2 == 0)
                beat_idx = int(beats_elapsed % 4.0)
                if is_even:
                    dimmer_fx_val = chase_intensity * (0.8 if beat_idx in (0, 2) else 0.15)
                else:
                    dimmer_fx_val = chase_intensity * (0.8 if beat_idx in (1, 3) else 0.15)

            elif dimmer_effect_type == "circular":
                # CIRCULAR CHASE: wraps around the rig continuously
                # Circular = chase wraps from last fixture back to first
                wrap_pos = (chase_pos + fixture_position) % 1.0
                # Use triangle wave for smooth wrap
                circular_val = 1.0 - abs(2.0 * wrap_pos - 1.0)
                dimmer_fx_val = (circular_val ** 2) * chase_intensity

            elif dimmer_effect_type == "ramp":
                # RAMP UP/DOWN: gradual intensity rise from L→R then R→L
                # Creates a "wave" of brightness across the rig
                ramp_phase = self._bpm_phase(bpm, beats=chase_beats * 2.0)
                if ramp_phase < 0.5:
                    # Ramp up L→R: fixture position determines when it lights
                    progress = ramp_phase * 2.0  # 0→1 over half cycle
                    dimmer_fx_val = chase_intensity * max(0.0, 1.0 - abs(fixture_position - progress) * 3.0)
                else:
                    # Ramp down R→L
                    progress = (1.0 - ramp_phase) * 2.0
                    dimmer_fx_val = chase_intensity * max(0.0, 1.0 - abs(fixture_position - progress) * 3.0)

            dim += dimmer_fx_val

            # Layer 4: BUMP — traveling bump through fixtures (not all-at-once!)
            # The bump "travels" from left to right across the rig on each beat,
            # so fixtures light up in sequence creating a "bump wave"
            if self._bump_decay > 0.01:
                # Bump travels across the rig in ~80ms (one bump width)
                bump_travel_speed = 12.0  # how fast the bump travels
                bump_center = (beat_phase * bump_travel_speed) % 1.0
                bump_dist = abs(fixture_position - bump_center)
                bump_dist = min(bump_dist, 1.0 - bump_dist)
                bump_width = 0.15  # narrow gaussian = visible traveling bump
                bump_val = math.exp(-(bump_dist ** 2) / (2.0 * bump_width ** 2))
                dim += self._bump_decay * bump_val
            # Downbeat bump hits ALL fixtures simultaneously (for impact)
            if is_downbeat and section in {"chorus", "drop"}:
                dim += downbeat_extra

            # Layer 6: Onset flash (additive, all fixtures)
            dim += self._fx_onset_flash * 0.3

            # Drop white flash: FULL white at drop start
            if self._drop_white_flash > 0.1:
                dim = max(dim, self._drop_white_flash)

            # Buildup progressive rise
            if section == "buildup":
                buildup_t = min(1.0, section_time / 16.0)
                dim += 0.25 * buildup_t  # slowly rise over 16s

            # Ethereal: keep dim but with gentle pulsing
            if ethereal_active:
                ethereal_pulse = 0.5 + 0.15 * math.sin(2.0 * math.pi * self._bpm_phase(bpm, beats=8.0))
                dim = min(dim, ethereal_pulse)

            # ── LAYER 5: Strobe fixtures (override) ───────────────────
            # Strobes fire on HIGH ENERGY parts: drop always, chorus on downbeats,
            # buildup with accelerating rate
            if is_strobe_fix:
                if section == "drop":
                    # 8th-note strobe locked to BPM
                    dim = 1.0 if eighth_phase < 0.25 else 0.0
                elif section == "chorus" and eff_energy > 0.5:
                    # Flash on downbeat AND phrase starts during high-energy chorus
                    dim = 1.0 if (is_downbeat or is_phrase_start) else 0.0
                elif section == "buildup":
                    buildup_t = min(1.0, section_time / 16.0)
                    # Accelerating rate: starts slow, gets frantic
                    subdiv = 1.0 + 7.0 * (buildup_t ** 2)  # quadratic acceleration
                    dim = 1.0 if (beats_elapsed * subdiv) % 1.0 < 0.08 else 0.0
                else:
                    dim = 0.0

            # ── LAYER 5: Blinder fixtures (audience layer) ────────────
            if is_blinder:
                if section == "drop":
                    # Slam on every beat, stay bright between
                    dim = 0.95 if is_beat_start else 0.7
                elif section == "chorus" and eff_energy > 0.4:
                    # Flash on downbeat — big moments only
                    dim = 0.9 if is_downbeat else 0.0
                elif section == "buildup":
                    buildup_t = min(1.0, section_time / 16.0)
                    rate = 0.5 + 3.5 * buildup_t
                    dim = buildup_t * 0.7 if (beats_elapsed * rate) % 1.0 < 0.06 else 0.0
                else:
                    dim = 0.0

            # Drop strobe override for ALL fixtures
            if drop_strobe_flash and not is_bar:
                dim = 1.0 if eighth_phase < 0.25 else 0.15

            # Dark-move dimmer suppression (only for movers during pattern transition)
            if self._dark_move_active and is_mover and not is_strobe_fix and not is_blinder:
                dim *= max(0.0, 1.0 - self._dark_move_dim_suppress * 0.7)

            # Perceptual gamma curve (programming research: "non-linear curve
            # for perceptually smooth fades; avoids steppy low-end")
            dim = max(0.0, min(1.0, dim))
            dim = dim ** (1.0 / self._perceptual_gamma) if dim > 0.0 else 0.0

            fixture.dimmer = max(0.0, min(1.0, dim))

            # Audience intensity cap
            audience_cap = max(0.0, min(1.0, float(self.config.audience_intensity_cap)))
            if fixture.dimmer > audience_cap:
                self._record_safety_event(
                    "audience_intensity_clamped",
                    {"fixture_id": fixture.id,
                     "requested": round(float(fixture.dimmer), 3),
                     "applied": round(float(audience_cap), 3)},
                    throttle_s=1.0, throttle_key="audience_intensity_clamped",
                )
            fixture.dimmer = min(fixture.dimmer, audience_cap)
            if visibility_first and (not drop_strobe_on):
                fixture.dimmer = max(fixture.dimmer, 0.48)

            # ── COLOR: layered scheme + mood + onset flash ────────────
            if (drop_strobe_flash and not is_bar) or self._drop_white_flash > 0.5:
                # White flash on strobe or drop impact
                fixture.red = 1.0
                fixture.green = 1.0
                fixture.blue = 1.0
            else:
                # Base color from scheme: dominant on left/odd, accent on right/even
                if i % 2 == 0:
                    base = color_dominant
                else:
                    base = color_accent

                # Blend with section mood (how much mood controls the color)
                mood_blend = {
                    "breakdown": 0.65, "verse": 0.30, "buildup": 0.35,
                    "chorus": 0.20, "drop": 0.10
                }.get(section, 0.30)
                final = base.blend(section_mood, mood_blend)

                # Buildup: warm shift over time
                if section == "buildup":
                    buildup_t = min(1.0, section_time / 16.0)
                    final = final.blend(RGB(1.0, 0.5, 0.05), 0.15 + 0.25 * buildup_t)

                # Drop: fade from white to vivid color over 2s
                if section == "drop" and section_time < 2.0:
                    white_fade = max(0.0, 1.0 - section_time / 1.5)
                    final = final.blend(RGB(1.0, 1.0, 1.0), white_fade * 0.6)

                # Onset color hit overlay
                if self._fx_onset_flash > 0.1:
                    flash_rgb = RGB(*self._fx_onset_color)
                    final = final.blend(flash_rgb, self._fx_onset_flash * 0.5)

                # LED bars: solid mood color (consistent anchor)
                if is_bar:
                    final = section_mood.blend(color_dominant, 0.25)
                # Washes: softer, wider blend for fill
                elif is_wash:
                    final = color_dominant.blend(section_mood, 0.45)

                fixture.red = max(0.0, min(1.0, final.r))
                fixture.green = max(0.0, min(1.0, final.g))
                fixture.blue = max(0.0, min(1.0, final.b))

            # Strobe value
            fixture.strobe = fixture.dimmer if (is_strobe_fix or is_blinder) else 0.0

            # Gobo
            if is_mover:
                self.gobo.apply_to_fixture(fixture, i, energy=energy, bass=bass, beat_phase=beat_phase)

            snapshot.append({
                'id': fixture.id,
                'dmx_address': int(getattr(fixture, 'dmx_address', 0) or 0),
                'pan': fixture.pan,
                'tilt': fixture.tilt,
                'dimmer': fixture.dimmer,
                'r': fixture.red,
                'g': fixture.green,
                'b': fixture.blue,
                'gobo': getattr(fixture, 'gobo_index', 0.0),
                'gobo_rotation': getattr(fixture, 'gobo_rotation', 0.0),
                'zoom': getattr(fixture, 'zoom', 0.5),
                'iris': getattr(fixture, 'iris', 1.0),
                'frost': getattr(fixture, 'frost', 0.0),
                'prism': getattr(fixture, 'prism', 0.0),
            })

        self._fixture_state_snapshot = snapshot

    def _rebuild_get_emotional_color(self, section: str) -> RGB:
        """Return section-specific emotional color for MA2-style looks.

        Simpler than before - just returns the look's color modified by section.
        Drop gets white tint, breakdown gets cooler/darker, buildup warms.
        """
        bpm = max(60.0, float(self._smoothed_movement_bpm))
        bar_clock = int(self.time * (bpm / 60.0) / 4.0)

        # Color palette rotation
        edm_palettes = [
            [RGB(0.0, 0.8, 1.0), RGB(1.0, 0.0, 0.6)],
            [RGB(0.0, 0.4, 1.0), RGB(0.0, 1.0, 0.5)],
            [RGB(0.9, 0.0, 0.3), RGB(1.0, 0.5, 0.0)],
            [RGB(0.5, 0.0, 1.0), RGB(0.0, 0.8, 1.0)],
            [RGB(1.0, 0.0, 0.4), RGB(0.0, 0.2, 1.0)],
            [RGB(0.0, 1.0, 0.6), RGB(1.0, 0.8, 0.0)],
        ]
        palette_idx = (bar_clock // 8) % len(edm_palettes)
        palette = edm_palettes[palette_idx]

        beat_phase = (self.time * (bpm / 60.0)) % 1.0
        color_blend = 0.5 + 0.3 * math.sin(2.0 * math.pi * beat_phase * 0.25)
        base = palette[0].blend(palette[1], color_blend)

        section = (section or "verse").lower()
        if section in {"breakdown", "bridge"}:
            # Cooler, darker version
            return base.blend(RGB(0.15, 0.25, 0.65), 0.40)
        elif section == "buildup":
            # Warm toward amber as buildup progresses
            buildup_t = min(1.0, (self.time - self._rebuild_section_changed_at) / 8.0)
            return base.blend(RGB(1.0, 0.7, 0.3), 0.20 + 0.25 * buildup_t)
        elif section in {"drop", "chorus"}:
            # White tint for intensity
            return base.blend(RGB(1.0, 1.0, 1.0), 0.12)
        return base

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
        """BPM-locked bump envelope for active chase steps (keeps them alive, not static)."""
        bpm = max(60.0, min(200.0, float(self._smoothed_movement_bpm)))
        beat_phase = (self.time * (bpm / 60.0)) % 1.0
        # Fast peak at beat start, then smooth decay.
        if beat_phase < 0.22:
            peak = 1.0 - (beat_phase / 0.22)
            return 0.72 + 0.28 * peak
        return 0.72

    def set_dmx_callback(self, callback: Callable[[int, List[int]], None]):
        """
        Set callback for DMX output.

        Args:
            callback: Function(universe, dmx_frame) to send DMX data
        """
        self._dmx_callback = callback

    def set_vocal_analyzer(self, vocal_analyzer):
        """Set the vocal analyzer for lyric-aware lighting.

        The vocal analyzer provides two layers:
        1. Vocal cadence → movement bounce modulation
        2. Lyric keywords → color theme selection
        """
        self._vocal_analyzer = vocal_analyzer

    def _update_vocal_integration(self, dt: float):
        """Pull latest vocal analysis state into effects engine.

        Called each frame from the main update loop.
        """
        va = self._vocal_analyzer
        if va is None:
            return

        # Get movement modulation from vocal cadence
        self._vocal_movement_mod = va.get_movement_modulation()

        # Get lyric-driven color theme (if any)
        theme = va.get_color_theme()
        if theme is not None:
            self._lyric_color_theme = theme
        elif self._lyric_color_theme.get("confidence", 0.0) > 0.01:
            # Fade out old theme gradually
            self._lyric_color_theme["confidence"] = self._lyric_color_theme.get("confidence", 0.0) * 0.98

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

    def set_genre(self, genre, crossfade: bool = True):
        """Set the active genre profile."""
        from ..lighting.movement_patterns import apply_genre_defaults
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
        section_str = section.value if hasattr(section, 'value') else str(section)
        self.decision.set_section(section_str)
        # Sync to rebuild pipeline (drives gobo engine, movement, dimmer effects)
        self._rebuild_set_section(section_str.lower())
        # Hold manual section for 30s so auto-detection doesn't override it
        self._rebuild_manual_hold_until = self.time + 30.0

    def update_audio(
        self,
        energy: float = 0.5,
        bass: float = 0.5,
        mid: float = 0.5,
        high: float = 0.5,
        is_beat: bool = False,
        beat_number: int = 0,
        valence: float = 0.5,
        arousal: float = 0.5,
        spectral_flux: float = 0.0,
        bpm: float = 128.0,
        ml_data: dict = None,
    ):
        """
        Update audio state from audio analyzer.

        Args:
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
        """
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

        # Update BPM (raw for reactive layers)
        self.config.bpm = bpm

        # Smooth BPM for non-reactive movement clock to avoid jitter from detector noise.
        target_bpm = max(60.0, min(200.0, float(bpm)))
        if self.config.movement_music_reactive:
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
            safe_boundary = is_boundary or phrase_boundary or section in {"intro", "outro", "breakdown"}
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

    def _on_song_change(self):
        """Handle song change - pick new color palette and reset ML state."""
        # Cycle to next palette
        self._palette_index = (self._palette_index + 1) % len(self._available_palettes)
        self._current_song_palette = self._available_palettes[self._palette_index]
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

        # Reset section-template "home" state and MIB transitions for next song
        self._song_home_section = None
        self._song_home_template = None
        self._current_section_template_key = None
        self._mib_states.clear()

        print(f"[Effects] Song changed! New palette: {self._current_song_palette.value}")

    def _get_palette_narrative_variant(self, section: str) -> Dict[str, float]:
        """Section-aware palette narrative — keep colors vivid for EDM."""
        section = (section or "unknown").lower()
        if section in {"intro", "verse"}:
            return {
                "accent_swap": 0.5,   # Alternate colors between fixtures
                "sat_mult": 1.15,     # Slightly boosted saturation
                "white_mix": 0.0,
                "color_count": 3.0,
            }
        if section in {"chorus", "drop", "peak"}:
            return {
                "accent_swap": 1.0,   # Strong fixture color alternation
                "sat_mult": 1.3,      # Maximum saturation boost
                "white_mix": 0.0,
                "color_count": 3.0,
            }
        if section in {"breakdown", "bridge"}:
            return {
                "accent_swap": 0.0,
                "sat_mult": 0.85,     # Slightly cooler but still vivid
                "white_mix": 0.05,    # Tiny white for ethereal feel
                "color_count": 2.0,   # Keep at least 2 colors
            }
        if section == "buildup":
            return {
                "accent_swap": 0.5,
                "sat_mult": 1.2,
                "white_mix": 0.0,
                "color_count": 3.0,
            }
        return {
            "accent_swap": 0.5,
            "sat_mult": 1.1,
            "white_mix": 0.0,
            "color_count": 3.0,
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
        if genre_data:
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
                    self.set_genre(genre_enum)
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
            self._update_vocal_integration(delta_time)
            self._rebuild_update_intent(delta_time)
            self._update_fixtures_rebuild(delta_time)
            if self._dmx_callback:
                frame = self.fixtures.get_dmx_frame(universe=0)
                self._dmx_callback(0, frame)
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
        if self._dmx_callback:
            frame = self.fixtures.get_dmx_frame(universe=0)
            self._dmx_callback(0, frame)

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
                    # Layer 1: Base intensity from audio energy
                    base_intensity = 0.3 + self.audio_features.energy * 0.7

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
                                fixture.dimmer *= max(0.05, chase_dim)  # Floor at 5% to avoid full blackout

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
                            low_sections = {"breakdown", "bridge", "outro"}
                            chase_off_level = 0.08 if section in low_sections else 0.5
                            # Explicit linear chase: one fixture head ON moving down each row.
                            if linear_chase_level_by_id.get(fixture.id, 0.0) >= 0.5:
                                fixture.dimmer = max(
                                    fixture.dimmer,
                                    1.0 * self._get_chase_bump_level()
                                )
                            else:
                                fixture.dimmer = max(fixture.dimmer, chase_off_level)
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
                            # base_intensity modulates overall dimmer
                            fixture.dimmer *= 0.5 + em.get("base_intensity", 0.5) * 0.5
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

            # Keep non-breakdown busking visibly bright; only breakdown family should feel truly dim.
            if self._pro_lighting_enabled and (not self.config.movement_music_reactive):
                if section not in {"breakdown", "bridge", "outro"}:
                    fixture.dimmer = max(fixture.dimmer, 0.45)

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
            if self._pro_lighting_enabled and (not self.config.movement_music_reactive):
                if section not in {"breakdown", "bridge", "outro"}:
                    fixture.dimmer = max(0.38, min(1.0, fixture.dimmer * 1.9))

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
                'pan': fixture.pan,
                'tilt': fixture.tilt,
                'dimmer': fixture.dimmer,
                'r': fixture.red,
                'g': fixture.green,
                'b': fixture.blue,
                'gobo': getattr(fixture, 'gobo_index', 0.0),
                'gobo_rotation': getattr(fixture, 'gobo_rotation', 0.0),
                'zoom': getattr(fixture, 'zoom', 0.5),
                'iris': getattr(fixture, 'iris', 1.0),
                'frost': getattr(fixture, 'frost', 0.0),
                'prism': getattr(fixture, 'prism', 0.0),
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
        """Blackout all fixtures."""
        for fixture in self.fixtures.fixtures.values():
            fixture.dimmer = 0
        self.strobe.stop()

    def restore(self):
        """Restore from blackout."""
        # Will naturally restore on next update
        pass

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

        while self.running:
            try:
                self.update()
            except Exception as e:
                # Keep loop alive in live use; one bad frame should not kill output.
                print(f"[EffectsEngine] update error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the effects engine."""
        self.running = False
        self.blackout()

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
