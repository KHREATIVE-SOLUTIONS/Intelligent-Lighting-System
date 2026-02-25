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
import time
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass

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

# Professional lighting modules - imported lazily in __init__ to avoid circular imports
# (lighting modules import from effects submodules, which triggers effects/__init__.py,
#  which imports effects_engine, creating a cycle)


@dataclass
class EffectsConfig:
    """
    Configuration for the effects engine.

    TRAINING MODE: By default, auto_mode is disabled. The system learns
    from human operators using the LFO effects and manual controls.
    Audio analysis is captured for training data but doesn't control lights.
    """
    # Update rate
    fps: float = 60.0

    # Auto-pilot mode (use decision engine) - DISABLED for training
    auto_mode: bool = False

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

    # Color stability - lock palette per song
    lock_palette_per_song: bool = True
    silence_threshold: float = 0.02  # RMS below this = silence
    silence_duration_for_song_change: float = 1.5  # Seconds of silence = new song

    # Move-In-Black (MIB)
    mib_enabled: bool = True
    mib_transition_ms: int = 450
    mib_pan_tilt_threshold: float = 28.0  # DMX-value delta threshold


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

        self.genre_manager = GenreProfileManager()
        self.section_manager = SectionManager(bpm=self.config.bpm)
        self.pro_movement = ProMovementEngine()
        self.pro_effects = ProEffects(bpm=self.config.bpm)
        self.key_lighting = KeyLightingManager()

        # Pro lighting integration enabled flag
        self._pro_lighting_enabled = False

        # ML emotion mapping state (set by _apply_ml_data)
        self._ml_emotion_mapping = None

        # Set default movement pattern - visible circular motion
        self.movement.set_pattern(
            MovementType.TRUE_CIRCLE,
            base_look=StaticLook.ALL_CENTER,
            pan_amplitude=60.0,   # Wider pan sweep
            tilt_amplitude=40.0,  # More tilt movement
            pan_speed=0.25,       # Faster, more visible
            tilt_speed=0.25,
            phase_spread=1.0,
            smoothing=0.15        # Faster response
        )

    def set_dmx_callback(self, callback: Callable[[int, List[int]], None]):
        """
        Set callback for DMX output.

        Args:
            callback: Function(universe, dmx_frame) to send DMX data
        """
        self._dmx_callback = callback

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
        self.decision.set_section(section.value if hasattr(section, 'value') else str(section))

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
        # Update audio features for color mapping
        self.audio_features = AudioFeatures(
            energy=energy,
            bass=bass,
            mid=mid,
            high=high,
            valence=valence,
            arousal=arousal,
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

        # Update BPM
        self.config.bpm = bpm

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
        """Section-aware palette narrative controls for one-song palette identity."""
        section = (section or "unknown").lower()
        base_variant = {
            "accent_swap": 0.0,
            "sat_mult": 1.0,
            "white_mix": 0.08,
            "color_count": 3.0,
        }
        if section in {"intro", "verse"}:
            return base_variant
        if section in {"chorus", "drop", "peak"}:
            return {
                "accent_swap": 1.0,
                "sat_mult": 1.2,
                "white_mix": 0.04,
                "color_count": 3.0,
            }
        if section in {"breakdown", "bridge"}:
            return {
                "accent_swap": 0.0,
                "sat_mult": 0.75,
                "white_mix": 0.18,
                "color_count": 1.0,
            }
        return {
            "accent_swap": 0.0,
            "sat_mult": 0.92,
            "white_mix": 0.11,
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
            # Only switch if confidence is reasonable
            if confidence >= 0.4:
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

            if section_confidence >= 0.5:
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

            # Trigger pro effects based on section transitions
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

        # Update pro lighting modules
        if self._pro_lighting_enabled:
            self.genre_manager.update(delta_time)
            self.section_manager.update(
                delta_time,
                energy=self.audio_features.energy,
                is_beat=self.audio_features.is_beat,
            )
            self.pro_movement.set_bpm(self.config.bpm)
            self.pro_movement.update(delta_time)
            self.pro_effects.set_bpm(self.config.bpm)
            self.pro_effects.update(delta_time)

            # Auto-detect section from audio if no external section data
            detected = self.section_manager.detect_section_from_energy(
                self.audio_features.energy,
                self.audio_features.bass,
                getattr(self.audio_state, 'spectral_flux', 0.0),
            )
            if detected is not None:
                self.section_manager.trigger_section(detected)

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

        if self.config.movement_enabled and template.movement_preset in MOVEMENT_PRESETS:
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
        if self.config.movement_enabled:
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

    def _update_fixtures(self, delta_time: float):
        """Update all fixture values from effect layers."""
        all_fixtures = self.fixtures.get_fixtures_in_group("all")
        total = len(all_fixtures)

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
            phase_offset = i / max(1, total)

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
                    # LFO pan is relative offset (-0.2 to +0.2), scale to pan degrees
                    fixture.pan = max(0, min(255, 128 + lfo_vals['pan'] * 255))
                if 'tilt' in lfo_vals:
                    fixture.tilt = max(0, min(255, 128 + lfo_vals['tilt'] * 255))

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
                    fixture.pan = 128  # Center
                    fixture.tilt = 128
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
                            i, phase_offset
                        )
                        fixture.pan = pan
                        fixture.tilt = tilt

                    # Layer 3: Dimmer effect
                    dimmer_multiplier = 1.0
                    if self.config.dimmer_enabled:
                        dimmer_multiplier = self.dimmer.get_intensity(
                            fixture.id, i, phase_offset,
                            energy=self.audio_features.energy
                        )

                    # Layer 4: Strobe
                    strobe_value = 0.0
                    if self.config.strobe_enabled and self.strobe.is_active():
                        strobe_value = self.strobe.get_strobe_value(
                            fixture.id, i, total, phase_offset
                        )

                    # Combine layers for final intensity
                    if strobe_value > 0:
                        fixture.dimmer = strobe_value * base_intensity
                    else:
                        fixture.dimmer = base_intensity * dimmer_multiplier

                    # Color from audio (using locked palette)
                    if self.config.color_enabled:
                        color = self.color.get_color(
                            self.audio_features, i, phase_offset
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
                            pan_off, tilt_off = self.pro_movement.get_position(
                                fixture.id, i, total,
                                fixture.x, fixture.y, fixture.z,
                            )
                            # Scale by section movement energy
                            move_energy = self.section_manager.get_movement_energy()
                            # Modulate with MERT movement_speed if available
                            if self._ml_emotion_mapping is not None:
                                ml_move = self._ml_emotion_mapping.get("movement_speed", 0.5)
                                move_energy *= 0.5 + ml_move  # 0.5x-1.5x range
                            pan_off *= move_energy
                            tilt_off *= move_energy
                            # Add bump offset
                            bump_pan, bump_tilt = self.pro_movement.get_bump_offset()
                            pan_off += bump_pan
                            tilt_off += bump_tilt
                            # Apply as degree offsets (pan/tilt are in DMX 0-255)
                            fixture.pan = max(0, min(255, fixture.pan + pan_off * 255 / 540))
                            fixture.tilt = max(0, min(255, fixture.tilt + tilt_off * 255 / 270))

                        # Pro movement chase dimmer (chases control brightness too)
                        chase_dim = self.pro_movement.get_chase_intensity(i, total)
                        if chase_dim < 1.0:
                            fixture.dimmer *= max(0.05, chase_dim)  # Floor at 5% to avoid full blackout

                        # Pro strobe overlay
                        if self.section_manager.is_strobe_allowed():
                            pro_strobe = self.pro_effects.strobe.get_value(i, total, phase_offset)
                            if pro_strobe > 0:
                                fixture.dimmer = max(fixture.dimmer, pro_strobe)

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
                        if chase_val > 0:
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
                        if blackout_val is not None:
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

            # Apply section template intensity scale across all non-training paths
            fixture.dimmer *= self._current_section_intensity_scale

            # True backend move-in-black: hide major reposition travel
            if fixture.fixture_type != "bar" and fixture.id and (hasattr(fixture, "pan") and hasattr(fixture, "tilt")):
                fixture.dimmer = self._apply_mib_transition(fixture, float(fixture.dimmer))

            # Dynamic range enforcement (anti-fatigue)
            if self._pro_lighting_enabled:
                intensity_scale = self.decision.get_dynamic_intensity_scale()
                if intensity_scale < 1.0:
                    fixture.dimmer *= intensity_scale
                self.decision.track_intensity(fixture.dimmer)

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

        # Build atomic snapshot for concurrent WebSocket readers (BUG-001 fix)
        snapshot = []
        for fixture in all_fixtures:
            snapshot.append({
                'id': fixture.id,
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
        }
        # Include ML emotion data if available
        if self._ml_emotion_mapping is not None:
            state["emotion_mapping"] = self._ml_emotion_mapping
        return state

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
