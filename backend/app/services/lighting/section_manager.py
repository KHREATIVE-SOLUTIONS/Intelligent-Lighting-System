"""
Section-Aware Intensity and Dynamic Range Manager
Handles song structure transitions with professional timing.

Features:
- Section-aware intensity (verse 50-70%, chorus 80-100%, drop 100%, breakdown 20-40%)
- Dynamic range management (prevents clipping and muddy looks)
- Anticipation timing (pre-loads next look 1-2 bars ahead)
- Build-up progressive ramp
- Section detection from audio energy contour
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable


# Shared musical timing rules used by section/effect systems.
ALLOWED_MUSICAL_BOUNDARIES: Tuple[int, ...] = (4, 8, 16)
IMPACT_SECTIONS = {"drop"}


def is_downbeat(beat_number: int) -> bool:
    """Return True when beat number represents a bar downbeat."""
    return beat_number > 0 and beat_number % 4 == 1


def next_musical_boundary_bar(completed_bars: int) -> int:
    """Get next allowed commit bar based on 4/8/16 phrase boundaries."""
    candidate = completed_bars + 1
    while not any(candidate % bars == 0 for bars in ALLOWED_MUSICAL_BOUNDARIES):
        candidate += 1
    return candidate


def bars_until_boundary(completed_bars: int) -> int:
    """How many bars remain until the next allowed boundary."""
    return max(0, next_musical_boundary_bar(completed_bars) - completed_bars)


def is_impact_event(section_name: str) -> bool:
    """Impact sections bypass normal boundary waiting."""
    return section_name.lower() in IMPACT_SECTIONS


class SongSection(Enum):
    """Song structure sections."""
    INTRO = "intro"
    VERSE = "verse"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    DROP = "drop"
    BREAKDOWN = "breakdown"
    BRIDGE = "bridge"
    OUTRO = "outro"
    BUILDUP = "buildup"
    UNKNOWN = "unknown"


@dataclass
class SectionConfig:
    """Configuration for a specific section."""
    # Intensity range (min, max as 0-1)
    intensity_range: Tuple[float, float] = (0.5, 0.7)

    # Movement energy multiplier
    movement_energy: float = 0.5

    # Color saturation preference (0-1)
    color_saturation: float = 0.7

    # Whether strobe is allowed in this section
    strobe_allowed: bool = False

    # Beat reactivity (how much intensity follows beats, 0-1)
    beat_reactivity: float = 0.5

    # Dimmer floor (never go below this)
    dimmer_floor: float = 0.1


# Default section configurations
DEFAULT_SECTION_CONFIGS: Dict[SongSection, SectionConfig] = {
    SongSection.INTRO: SectionConfig(
        intensity_range=(0.3, 0.5),
        movement_energy=0.2,
        color_saturation=0.5,
        strobe_allowed=False,
        beat_reactivity=0.3,
        dimmer_floor=0.15,
    ),
    SongSection.VERSE: SectionConfig(
        intensity_range=(0.6, 0.85),
        movement_energy=0.4,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.65,
        dimmer_floor=0.3,
    ),
    SongSection.PRE_CHORUS: SectionConfig(
        intensity_range=(0.7, 0.95),
        movement_energy=0.6,
        color_saturation=0.8,
        strobe_allowed=False,
        beat_reactivity=0.72,
        dimmer_floor=0.35,
    ),
    SongSection.CHORUS: SectionConfig(
        intensity_range=(0.8, 1.0),
        movement_energy=0.8,
        color_saturation=0.9,
        strobe_allowed=True,
        beat_reactivity=0.7,
        dimmer_floor=0.3,
    ),
    SongSection.DROP: SectionConfig(
        intensity_range=(0.9, 1.0),
        movement_energy=1.0,
        color_saturation=1.0,
        strobe_allowed=True,
        beat_reactivity=0.9,
        dimmer_floor=0.4,
    ),
    SongSection.BREAKDOWN: SectionConfig(
        intensity_range=(0.25, 0.55),
        movement_energy=0.15,
        color_saturation=0.4,
        strobe_allowed=False,
        beat_reactivity=0.3,
        dimmer_floor=0.18,
    ),
    SongSection.BRIDGE: SectionConfig(
        intensity_range=(0.4, 0.6),
        movement_energy=0.4,
        color_saturation=0.6,
        strobe_allowed=False,
        beat_reactivity=0.4,
        dimmer_floor=0.15,
    ),
    SongSection.OUTRO: SectionConfig(
        intensity_range=(0.2, 0.4),
        movement_energy=0.15,
        color_saturation=0.4,
        strobe_allowed=False,
        beat_reactivity=0.2,
        dimmer_floor=0.1,
    ),
    SongSection.BUILDUP: SectionConfig(
        intensity_range=(0.4, 0.9),
        movement_energy=0.7,
        color_saturation=0.8,
        strobe_allowed=True,
        beat_reactivity=0.7,
        dimmer_floor=0.2,
    ),
    SongSection.UNKNOWN: SectionConfig(
        intensity_range=(0.55, 0.8),
        movement_energy=0.5,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.6,
        dimmer_floor=0.25,
    ),
}


@dataclass
class SectionTransition:
    """Tracks an in-progress section transition."""
    from_section: SongSection
    to_section: SongSection
    start_time: float
    duration: float  # seconds
    progress: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.progress >= 1.0


class SectionManager:
    """
    Manages song section state and provides intensity/parameter
    modulation based on current section.
    """

    def __init__(self, bpm: float = 128.0):
        self._current_section = SongSection.UNKNOWN
        self._previous_section = SongSection.UNKNOWN
        self._section_configs = dict(DEFAULT_SECTION_CONFIGS)

        # Timing
        self._bpm = bpm
        self._section_start_time = time.time()
        self._bars_in_section = 0
        self._beat_count = 0

        # Transition state
        self._transition: Optional[SectionTransition] = None
        self._crossfade_duration_bars = 0.125

        # Anticipation (pre-loading next look)
        self._anticipation_bars = 1.0
        self._pending_section: Optional[SongSection] = None
        self._pending_section_time: Optional[float] = None

        # Build-up ramp state
        self._buildup_start_time: Optional[float] = None
        self._buildup_duration: float = 8.0  # beats
        self._buildup_progress: float = 0.0

        # Dynamic range state
        self._current_intensity = 0.5
        self._target_intensity = 0.5
        self._intensity_smoothing = 0.1

        # Energy tracking for auto-detection
        self._energy_history: List[float] = []
        self._bass_history: List[float] = []
        self._flux_history: List[float] = []
        self._energy_window = 64  # frames
        self._section_votes: Dict[SongSection, int] = {
            SongSection.VERSE: 0,
            SongSection.PRE_CHORUS: 0,
            SongSection.CHORUS: 0,
            SongSection.BUILDUP: 0,
            SongSection.DROP: 0,
            SongSection.BREAKDOWN: 0,
        }
        self._vote_max: int = 10
        self._auto_min_hold_s: float = 0.85
        self._drop_refractory_s: float = 2.2
        self._last_auto_drop_time: float = -999.0
        self._section_confidence_ema: Dict[SongSection, float] = {
            SongSection.VERSE: 0.0,
            SongSection.PRE_CHORUS: 0.0,
            SongSection.CHORUS: 0.0,
            SongSection.BUILDUP: 0.0,
            SongSection.DROP: 0.0,
            SongSection.BREAKDOWN: 0.0,
        }
        self._section_confidence_alpha: float = 0.22
        self._boundary_candidate: Optional[SongSection] = None
        self._boundary_candidate_frames: int = 0
        self._boundary_debounce_frames: int = 3
        self._section_min_hold_bars: int = 8
        self._last_section_commit_bar: int = 0
        self._high_conf_force_commit: float = 0.82
        self._fast_energy_ema: float = 0.0
        self._slow_energy_ema: float = 0.0
        self._fast_bass_ema: float = 0.0
        self._slow_bass_ema: float = 0.0
        self._fast_flux_ema: float = 0.0
        self._slow_flux_ema: float = 0.0
        self._boundary_prob_ema: float = 0.0
        self._last_detect_debug: Dict[str, float | str | bool] = {}

        # Callbacks
        self._on_section_change: Optional[Callable[[SongSection, SongSection], None]] = None

    @property
    def current_section(self) -> SongSection:
        return self._current_section

    @property
    def section_config(self) -> SectionConfig:
        return self._section_configs.get(self._current_section,
                                          DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN])

    def set_bpm(self, bpm: float):
        """Update BPM for timing calculations."""
        self._bpm = max(30.0, min(300.0, bpm))

    def set_section_config(self, section: SongSection, config: SectionConfig):
        """Override configuration for a section."""
        self._section_configs[section] = config

    def set_on_section_change(self, callback: Callable[[SongSection, SongSection], None]):
        """Set callback for section changes."""
        self._on_section_change = callback

    def set_crossfade_duration(self, bars: float):
        """Set crossfade duration in bars."""
        self._crossfade_duration_bars = max(0.0, bars)

    def set_anticipation(self, bars: float):
        """Set anticipation timing in bars."""
        self._anticipation_bars = max(0.0, bars)

    def _bars_to_seconds(self, bars: float) -> float:
        """Convert bars to seconds at current BPM."""
        beats_per_bar = 4
        return (bars * beats_per_bar * 60.0) / self._bpm

    def trigger_section(self, section: SongSection, immediate: bool = False):
        """
        Trigger a section change.

        Args:
            section: New section
            immediate: Skip crossfade if True
        """
        if section == self._current_section:
            return

        if immediate:
            self._execute_section_change(section)
        else:
            # Start crossfade transition
            crossfade_seconds = self._bars_to_seconds(self._crossfade_duration_bars)
            self._transition = SectionTransition(
                from_section=self._current_section,
                to_section=section,
                start_time=time.time(),
                duration=max(0.01, crossfade_seconds),
            )

    def schedule_section(self, section: SongSection, bars_ahead: float = None):
        """
        Schedule a section change with anticipation timing.

        Args:
            section: Target section
            bars_ahead: Bars ahead to trigger (uses default anticipation if None)
        """
        if bars_ahead is None:
            bars_ahead = self._anticipation_bars
        delay_seconds = self._bars_to_seconds(bars_ahead)
        self._pending_section = section
        self._pending_section_time = time.time() + delay_seconds

    def trigger_buildup(self, duration_beats: float = 8.0):
        """
        Start a build-up ramp that progressively increases intensity.

        Args:
            duration_beats: Build-up duration in beats
        """
        self._buildup_start_time = time.time()
        self._buildup_duration = duration_beats
        self._buildup_progress = 0.0
        self.trigger_section(SongSection.BUILDUP)

    def trigger_beat(self, beat_number: int):
        """Handle beat event."""
        self._beat_count = beat_number
        if beat_number % 4 == 0:
            self._bars_in_section += 1

    def _execute_section_change(self, section: SongSection):
        """Execute an immediate section change."""
        old_section = self._current_section
        self._previous_section = old_section
        self._current_section = section
        self._section_start_time = time.time()
        self._bars_in_section = 0
        self._transition = None

        if self._on_section_change:
            self._on_section_change(old_section, section)

    def update(self, delta_time: float, energy: float = 0.5, is_beat: bool = False):
        """
        Update section manager state.

        Args:
            delta_time: Time since last update
            energy: Current audio energy (0-1)
            is_beat: Whether a beat occurred this frame
        """
        current_time = time.time()

        # Track energy history
        self._energy_history.append(energy)
        if len(self._energy_history) > self._energy_window:
            self._energy_history = self._energy_history[-self._energy_window:]

        # Check pending scheduled section
        if (self._pending_section is not None and
                self._pending_section_time is not None and
                current_time >= self._pending_section_time):
            self.trigger_section(self._pending_section)
            self._pending_section = None
            self._pending_section_time = None

        # Update transition
        if self._transition is not None:
            elapsed = current_time - self._transition.start_time
            self._transition.progress = min(1.0, elapsed / self._transition.duration)
            if self._transition.is_complete:
                self._execute_section_change(self._transition.to_section)

        # Update build-up ramp
        if self._buildup_start_time is not None:
            beat_duration = 60.0 / self._bpm
            elapsed_beats = (current_time - self._buildup_start_time) / beat_duration
            self._buildup_progress = min(1.0, elapsed_beats / self._buildup_duration)
            if self._buildup_progress >= 1.0:
                self._buildup_start_time = None

        # Calculate target intensity
        self._target_intensity = self._calculate_target_intensity(energy, is_beat)

        # Smooth intensity
        blend = 1.0 - (1.0 - self._intensity_smoothing) ** (delta_time * 60.0)
        self._current_intensity += (self._target_intensity - self._current_intensity) * blend

    def _calculate_target_intensity(self, energy: float, is_beat: bool) -> float:
        """Calculate target intensity based on section and audio."""
        config = self.section_config
        min_i, max_i = config.intensity_range

        # Strongly audio-reactive base within section range.
        base = min_i + (max_i - min_i) * (0.25 + energy * 0.75)
        intensity = base

        # Beat bump
        if is_beat:
            beat_bump = config.beat_reactivity * 0.16
            intensity += beat_bump

        # Build-up ramp override
        if self._buildup_start_time is not None:
            # Progressive ramp from current min to max
            buildup_intensity = min_i + self._buildup_progress * (max_i - min_i)
            # Use quadratic ramp for more dramatic build
            ramp = self._buildup_progress ** 1.5
            buildup_intensity = min_i + ramp * (max_i - min_i)
            intensity = max(intensity, buildup_intensity)

        # Apply transition blending
        if self._transition is not None and not self._transition.is_complete:
            from_config = self._section_configs.get(
                self._transition.from_section,
                DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN]
            )
            from_min, from_max = from_config.intensity_range
            from_intensity = from_min + (from_max - from_min) * 0.5 + energy * from_config.beat_reactivity * (from_max - from_min)
            intensity = from_intensity + (intensity - from_intensity) * self._transition.progress

        # Apply dimmer floor
        intensity = max(config.dimmer_floor, intensity)

        # Clamp
        return max(0.0, min(1.0, intensity))

    def get_intensity(self) -> float:
        """Get current smoothed intensity output."""
        return self._current_intensity

    def get_intensity_range(self) -> Tuple[float, float]:
        """Get current section's intensity range."""
        return self.section_config.intensity_range

    def get_movement_energy(self) -> float:
        """Get movement energy multiplier for current section."""
        config = self.section_config

        # Apply transition blending
        if self._transition is not None and not self._transition.is_complete:
            from_config = self._section_configs.get(
                self._transition.from_section,
                DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN]
            )
            return (from_config.movement_energy +
                    (config.movement_energy - from_config.movement_energy) *
                    self._transition.progress)

        return config.movement_energy

    def get_color_saturation(self) -> float:
        """Get color saturation preference for current section."""
        return self.section_config.color_saturation

    def is_strobe_allowed(self) -> bool:
        """Check if strobe is allowed in current section."""
        return self.section_config.strobe_allowed

    def get_beat_reactivity(self) -> float:
        """Get beat reactivity for current section."""
        return self.section_config.beat_reactivity

    def get_buildup_progress(self) -> float:
        """Get current build-up progress (0-1), 0 if not in build-up."""
        if self._buildup_start_time is None:
            return 0.0
        return self._buildup_progress

    def detect_section_from_energy(
        self,
        energy: float,
        bass: float,
        spectral_flux: float,
        is_beat: bool = False,
        beat_number: int = 0,
        bars_elapsed: Optional[int] = None,
        is_downbeat_event: Optional[bool] = None,
    ) -> Optional[SongSection]:
        """
        Auto-detect song section from audio features.
        Returns suggested section or None if uncertain.

        This is a heuristic fallback when no external section data is available.
        """
        def _clamp01(v: float) -> float:
            return max(0.0, min(1.0, float(v)))

        energy = _clamp01(energy)
        bass = _clamp01(bass)
        spectral_flux = _clamp01(spectral_flux)

        # Track complementary feature history for context/debugging.
        self._bass_history.append(bass)
        self._flux_history.append(spectral_flux)
        if len(self._bass_history) > self._energy_window:
            self._bass_history = self._bass_history[-self._energy_window:]
        if len(self._flux_history) > self._energy_window:
            self._flux_history = self._flux_history[-self._energy_window:]

        # Multi-rate causal smoothing (research-aligned: fast + slow streams).
        fast_a = 0.35
        slow_a = 0.06
        self._fast_energy_ema += (energy - self._fast_energy_ema) * fast_a
        self._slow_energy_ema += (energy - self._slow_energy_ema) * slow_a
        self._fast_bass_ema += (bass - self._fast_bass_ema) * fast_a
        self._slow_bass_ema += (bass - self._slow_bass_ema) * slow_a
        self._fast_flux_ema += (spectral_flux - self._fast_flux_ema) * fast_a
        self._slow_flux_ema += (spectral_flux - self._slow_flux_ema) * slow_a

        if len(self._energy_history) < 8 or len(self._bass_history) < 8:
            return None

        recent = self._energy_history[-4:]
        older = self._energy_history[-8:-4]
        recent_bass = self._bass_history[-4:]
        older_bass = self._bass_history[-8:-4]
        recent_flux = self._flux_history[-4:]
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        trend = avg_recent - avg_older
        avg_recent_bass = sum(recent_bass) / len(recent_bass)
        avg_older_bass = sum(older_bass) / len(older_bass)
        avg_recent_flux = sum(recent_flux) / max(1, len(recent_flux))
        bass_trend = avg_recent_bass - avg_older_bass
        energy_spike = energy - avg_older
        bass_spike = bass - avg_older_bass
        now = time.time()
        on_downbeat = bool(is_downbeat_event) if is_downbeat_event is not None else is_downbeat(int(beat_number))
        completed_bars = int(bars_elapsed if bars_elapsed is not None else max(0, (int(beat_number) - 1) // 4))
        phrase_boundary = completed_bars > 0 and (completed_bars % 4 == 0)

        novelty = _clamp01(
            max(0.0, self._fast_energy_ema - self._slow_energy_ema) * 1.7
            + max(0.0, self._fast_bass_ema - self._slow_bass_ema) * 1.6
            + max(0.0, self._fast_flux_ema) * 0.9
        )
        raw_boundary_prob = _clamp01(
            0.60 * novelty
            + 0.18 * (1.0 if on_downbeat else 0.0)
            + 0.12 * (1.0 if phrase_boundary else 0.0)
            + 0.10 * max(0.0, energy_spike)
        )
        self._boundary_prob_ema += (raw_boundary_prob - self._boundary_prob_ema) * 0.28

        # Guard: avoid overly chatty section flapping unless strong impact.
        if (now - self._section_start_time) < self._auto_min_hold_s:
            drop_impact = (
                is_beat
                and energy > 0.56
                and bass > 0.60
                and (spectral_flux > 0.06 or novelty > 0.58 or energy_spike > 0.08 or bass_spike > 0.10)
            )
            if not drop_impact:
                return None

        # From-scratch section confidence model (continuous probabilities, causal).
        drop_impact = (
            is_beat
            and on_downbeat
            and energy > 0.58
            and bass > 0.62
            and (novelty > 0.56 or spectral_flux > 0.07 or energy_spike > 0.09)
        )
        p_drop = _clamp01(
            (0.45 if drop_impact else 0.0)
            + 0.25 * max(0.0, energy - 0.64)
            + 0.20 * max(0.0, bass - 0.66)
            + 0.20 * novelty
        )
        p_buildup = _clamp01(
            0.40 * max(0.0, trend)
            + 0.28 * max(0.0, bass_trend)
            + 0.20 * max(0.0, avg_recent_flux - 0.06)
            + 0.16 * max(0.0, avg_recent - 0.54)
        )
        p_chorus = _clamp01(
            0.42 * max(0.0, avg_recent - 0.58)
            + 0.28 * max(0.0, avg_recent_bass - 0.48)
            + 0.22 * max(0.0, 0.09 - abs(trend))
        )
        p_pre = _clamp01(
            0.35 * max(0.0, avg_recent - 0.48)
            + 0.25 * max(0.0, trend)
            + 0.20 * max(0.0, avg_recent_flux - 0.05)
            + 0.10 * (1.0 if phrase_boundary else 0.0)
        )
        p_breakdown = _clamp01(
            0.45 * max(0.0, 0.32 - avg_recent)
            + 0.35 * max(0.0, 0.34 - avg_recent_bass)
            + 0.20 * max(0.0, 0.06 - avg_recent_flux)
        )
        p_verse = _clamp01(
            0.30 * max(0.0, 0.70 - abs(avg_recent - 0.50))
            + 0.26 * max(0.0, 0.70 - abs(avg_recent_bass - 0.46))
            + 0.18 * max(0.0, 0.10 - abs(trend))
            + 0.10 * (1.0 if (not phrase_boundary) else 0.0)
        )

        raw_probs = {
            SongSection.DROP: p_drop,
            SongSection.BUILDUP: p_buildup,
            SongSection.CHORUS: p_chorus,
            SongSection.PRE_CHORUS: p_pre,
            SongSection.VERSE: p_verse,
            SongSection.BREAKDOWN: p_breakdown,
        }

        # Smooth probabilities and derive vote-like confidence.
        alpha = max(0.01, min(0.95, float(self._section_confidence_alpha)))
        for sec, raw_conf in raw_probs.items():
            prev = self._section_confidence_ema.get(sec, 0.0)
            smoothed = prev + (raw_conf - prev) * alpha
            self._section_confidence_ema[sec] = smoothed
            self._section_votes[sec] = int(round(smoothed * float(self._vote_max)))

        # Convert votes to smoothed confidence curves (reduces section flapping).
        ranked_conf = sorted(self._section_confidence_ema.items(), key=lambda kv: kv[1], reverse=True)
        best_section, best_conf = ranked_conf[0]
        second_conf = ranked_conf[1][1] if len(ranked_conf) > 1 else 0.0
        if best_conf < 0.38 or (best_conf - second_conf) < 0.02:
            self._boundary_candidate = None
            self._boundary_candidate_frames = 0
            self._last_detect_debug = {
                "best_section": best_section.value,
                "best_conf": round(best_conf, 4),
                "boundary_prob": round(self._boundary_prob_ema, 4),
                "commit": False,
            }
            return None
        musical_boundary = on_downbeat or phrase_boundary

        if self._boundary_candidate == best_section:
            self._boundary_candidate_frames += 1
        else:
            self._boundary_candidate = best_section
            self._boundary_candidate_frames = 1

        persist_ok = self._boundary_candidate_frames >= max(1, int(self._boundary_debounce_frames))
        boundary_ok = self._boundary_prob_ema >= 0.44 or best_section == SongSection.DROP

        if best_section == SongSection.DROP:
            if (now - self._last_auto_drop_time) < self._drop_refractory_s:
                return None
            if not (persist_ok and (drop_impact or self._boundary_prob_ema >= 0.56)):
                return None
            self._last_auto_drop_time = now
            self._last_section_commit_bar = completed_bars
            self._boundary_candidate = None
            self._boundary_candidate_frames = 0
            self._last_detect_debug = {
                "best_section": best_section.value,
                "best_conf": round(best_conf, 4),
                "boundary_prob": round(self._boundary_prob_ema, 4),
                "commit": True,
                "reason": "drop_impact",
            }
            return SongSection.DROP

        # Don't constantly demote a fresh drop.
        if self._current_section == SongSection.DROP and (now - self._section_start_time) < 1.5:
            return None

        bars_since_commit = max(0, completed_bars - int(self._last_section_commit_bar))
        hold_ok = bars_since_commit >= max(1, int(self._section_min_hold_bars))
        force_commit = best_conf >= float(self._high_conf_force_commit)
        if not (persist_ok and boundary_ok and (musical_boundary or force_commit) and (hold_ok or force_commit)):
            self._last_detect_debug = {
                "best_section": best_section.value,
                "best_conf": round(best_conf, 4),
                "boundary_prob": round(self._boundary_prob_ema, 4),
                "persist_ok": bool(persist_ok),
                "boundary_ok": bool(boundary_ok),
                "musical_boundary": bool(musical_boundary),
                "hold_ok": bool(hold_ok),
                "force_commit": bool(force_commit),
                "commit": False,
            }
            return None

        self._last_section_commit_bar = completed_bars
        self._boundary_candidate = None
        self._boundary_candidate_frames = 0
        self._last_detect_debug = {
            "best_section": best_section.value,
            "best_conf": round(best_conf, 4),
            "boundary_prob": round(self._boundary_prob_ema, 4),
            "commit": True,
        }
        return best_section

    def get_detection_debug(self) -> Dict[str, float | str | bool]:
        """Get latest streaming structure-detector debug state."""
        out: Dict[str, float | str | bool] = dict(self._last_detect_debug)
        for sec, conf in self._section_confidence_ema.items():
            out[f"p_{sec.value}"] = round(float(conf), 4)
        return out
