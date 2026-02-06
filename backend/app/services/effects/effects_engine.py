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
        self._available_palettes = list(ColorPalette)
        self._palette_index = 0

        # White strobe flash state
        self._white_strobe_flash = False
        self._white_strobe_decay = 0.0

        # Thread-safe fixture state snapshot for WebSocket readers
        self._fixture_state_lock = asyncio.Lock()
        self._fixture_state_snapshot: List[Dict] = []

        # LFO Engine (grandMA2-style effects) - initialized separately via set_lfo_engine
        self._lfo_engine: Optional[LFOEngine] = None

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
        bpm: float = 128.0
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
            self._detect_song_change(energy)

    def _detect_song_change(self, energy: float):
        """Detect song changes via silence and switch color palette."""
        current_time = self.time

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
        """Handle song change - pick new color palette."""
        # Cycle to next palette
        self._palette_index = (self._palette_index + 1) % len(self._available_palettes)
        self._current_song_palette = self._available_palettes[self._palette_index]
        self._palette_locked = False  # Will lock on next audio

        # Apply the new palette
        self.color.set_palette(self._current_song_palette)
        self.config.palette = self._current_song_palette

        print(f"[Effects] Song changed! New palette: {self._current_song_palette.value}")

    def _on_beat(self, beat_number: int):
        """Handle beat event."""
        # Trigger dimmer beat sync
        self.dimmer.trigger_beat(beat_number)

        # Trigger strobe beat if in beat-locked mode
        self.strobe.trigger_beat(beat_number)

        # Trigger movement beat (for bump patterns and beat-locked effects)
        self.movement.trigger_beat()

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

        # Update decision engine (disabled for now - using fixed movement pattern)
        # if self.config.auto_mode:
        #     self.decision.update(self.audio_state, delta_time)
        #     selection = self.decision.get_selection()
        #     self._apply_selection(selection)

        # Sync BPM to movement engine for beat-locked patterns
        self.movement.params.bpm = self.config.bpm

        # Update all layers
        self.movement.update(delta_time)
        self.dimmer.update(delta_time)
        self.strobe.update(delta_time)
        self.color.update(delta_time)

        # Update drop sequence if active
        if self.drop_sequence.is_active():
            self.drop_sequence.update()

        # Generate DMX frame
        self._update_fixtures(delta_time)

        # Output DMX
        if self._dmx_callback:
            frame = self.fixtures.get_dmx_frame(universe=0)
            self._dmx_callback(0, frame)

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
                    if self.config.movement_enabled and fixture.fixture_type in ["mover", "wash"]:
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
            self.update()
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
