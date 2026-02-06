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
        intensity_range=(0.5, 0.7),
        movement_energy=0.4,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.5,
        dimmer_floor=0.2,
    ),
    SongSection.PRE_CHORUS: SectionConfig(
        intensity_range=(0.6, 0.8),
        movement_energy=0.6,
        color_saturation=0.8,
        strobe_allowed=False,
        beat_reactivity=0.6,
        dimmer_floor=0.25,
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
        intensity_range=(0.2, 0.4),
        movement_energy=0.15,
        color_saturation=0.4,
        strobe_allowed=False,
        beat_reactivity=0.2,
        dimmer_floor=0.1,
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
        intensity_range=(0.5, 0.7),
        movement_energy=0.5,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.5,
        dimmer_floor=0.2,
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
        self._crossfade_duration_bars = 0.5

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
        self._energy_window = 64  # frames

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

        # Base intensity from section range
        base = min_i + (max_i - min_i) * 0.5

        # Modulate with audio energy
        energy_contribution = energy * config.beat_reactivity * (max_i - min_i)
        intensity = base + energy_contribution

        # Beat bump
        if is_beat:
            beat_bump = config.beat_reactivity * 0.1
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

    def detect_section_from_energy(self, energy: float, bass: float,
                                    spectral_flux: float) -> Optional[SongSection]:
        """
        Auto-detect song section from audio features.
        Returns suggested section or None if uncertain.

        This is a heuristic fallback when no external section data is available.
        """
        if len(self._energy_history) < 16:
            return None

        recent = self._energy_history[-8:]
        older = self._energy_history[-16:-8]
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        trend = avg_recent - avg_older

        # Drop detection: sudden high energy after low
        if avg_recent > 0.85 and avg_older < 0.5 and bass > 0.8:
            return SongSection.DROP

        # Build-up detection: rising energy + high spectral flux
        if trend > 0.1 and spectral_flux > 0.3 and avg_recent < 0.8:
            return SongSection.BUILDUP

        # Breakdown: sustained low energy
        if avg_recent < 0.3 and trend < -0.05:
            return SongSection.BREAKDOWN

        # Chorus: high sustained energy
        if avg_recent > 0.75 and abs(trend) < 0.05:
            return SongSection.CHORUS

        # Verse: moderate energy
        if 0.35 < avg_recent < 0.65 and abs(trend) < 0.05:
            return SongSection.VERSE

        return None
