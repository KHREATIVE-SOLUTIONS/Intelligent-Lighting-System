"""
Genre-Specific Lighting Profiles
Professional concert lighting behavior for EDM, Rock, Pop, Hip-Hop, and Jazz.

Each genre defines:
- Color palettes (primary, secondary, accent)
- Movement speeds and amplitude ranges
- Beat pattern emphasis (kick, snare, hi-hat)
- Strobe behavior and limits
- Section intensity curves
- Preferred movement patterns per section
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional

from ..effects.color_mapper import RGB, ColorPalette
from ..effects.movement_patterns import MovementType, StaticLook
from ..effects.strobe_controller import StrobeMode
from ..effects.dimmer_effects import DimmerType


class Genre(Enum):
    EDM = "edm"
    ROCK = "rock"
    POP = "pop"
    HIP_HOP = "hip_hop"
    JAZZ = "jazz"


@dataclass
class ColorScheme:
    """Genre color palette with primary, secondary, and accent colors."""
    primary: List[RGB] = field(default_factory=list)
    secondary: List[RGB] = field(default_factory=list)
    accent: List[RGB] = field(default_factory=list)
    # When to use accent (beat intensity threshold 0-1)
    accent_threshold: float = 0.8
    # Color transition speed (0=instant, 1=very slow)
    transition_speed: float = 0.1


@dataclass
class MovementProfile:
    """Genre movement behavior."""
    # Speed ranges (Hz) for different energy levels
    low_energy_speed: float = 0.15
    mid_energy_speed: float = 0.3
    high_energy_speed: float = 0.6

    # Amplitude ranges (degrees)
    pan_amplitude_range: Tuple[float, float] = (30.0, 80.0)
    tilt_amplitude_range: Tuple[float, float] = (20.0, 50.0)

    # Phase spread preference (0=unison, 1=full spread)
    default_phase_spread: float = 0.8

    # Preferred patterns per section
    intro_patterns: List[MovementType] = field(default_factory=list)
    verse_patterns: List[MovementType] = field(default_factory=list)
    chorus_patterns: List[MovementType] = field(default_factory=list)
    drop_patterns: List[MovementType] = field(default_factory=list)
    breakdown_patterns: List[MovementType] = field(default_factory=list)

    # BPM lock behavior
    bpm_lock: bool = True
    beat_divisor: float = 1.0  # 1=every beat, 0.5=every 2 beats


@dataclass
class StrobeProfile:
    """Genre strobe behavior."""
    # Whether genre uses strobe at all
    enabled: bool = True

    # Maximum continuous frequency (Hz)
    max_continuous_hz: float = 4.0

    # Burst behavior
    burst_on_drop: bool = True
    burst_frequency: float = 12.0
    burst_duration: float = 2.0

    # Beat-locked strobe
    beat_locked_enabled: bool = True
    beat_locked_beats: List[int] = field(default_factory=lambda: [0])  # Which beats (0-3)

    # Blinder behavior
    blinder_on_climax: bool = True
    blinder_duration: float = 0.1


@dataclass
class TimingProfile:
    """Genre timing behavior."""
    # Typical BPM range
    bpm_range: Tuple[float, float] = (120.0, 140.0)

    # Anticipation (bars ahead to pre-load next look)
    anticipation_bars: float = 1.0

    # Minimum bars before effect change
    min_effect_duration_bars: int = 4

    # Beat emphasis weights (kick, snare, hi-hat, open-hat)
    beat_weights: Tuple[float, float, float, float] = (1.0, 0.8, 0.3, 0.5)

    # Section transition style
    # "cut" = instant change, "crossfade" = smooth blend, "bump" = flash then new
    transition_style: str = "crossfade"
    crossfade_bars: float = 0.5


@dataclass
class SectionIntensity:
    """Intensity ranges per song section."""
    intro: Tuple[float, float] = (0.3, 0.5)
    verse: Tuple[float, float] = (0.5, 0.7)
    pre_chorus: Tuple[float, float] = (0.6, 0.8)
    chorus: Tuple[float, float] = (0.8, 1.0)
    drop: Tuple[float, float] = (0.9, 1.0)
    breakdown: Tuple[float, float] = (0.2, 0.4)
    bridge: Tuple[float, float] = (0.4, 0.6)
    outro: Tuple[float, float] = (0.2, 0.4)


@dataclass
class GenreProfile:
    """Complete lighting profile for a music genre."""
    genre: Genre
    name: str
    description: str

    colors: ColorScheme
    movement: MovementProfile
    strobe: StrobeProfile
    timing: TimingProfile
    intensity: SectionIntensity

    # Preferred color palette from existing system
    color_palette: ColorPalette = ColorPalette.EDM

    # Preferred static looks
    preferred_static_looks: List[StaticLook] = field(default_factory=lambda: [
        StaticLook.ALL_CENTER, StaticLook.X_PATTERN, StaticLook.FAN_OUT
    ])

    # Front light color temperature (warm/cool/neutral)
    front_light_style: str = "cool"

    # Haze/fog preference (0-1)
    haze_level: float = 0.7


# =============================================================================
# GENRE DEFINITIONS
# =============================================================================

_EDM_PROFILE = GenreProfile(
    genre=Genre.EDM,
    name="Electronic Dance Music",
    description="High-energy strobe-heavy lighting with cyan/magenta palette, "
                "fast movement on drops, slow circles during breakdowns.",
    colors=ColorScheme(
        primary=[
            RGB.from_hsv(190, 1.0, 1.0),   # Cyan
            RGB.from_hsv(280, 0.9, 1.0),    # Magenta
            RGB.from_hsv(240, 1.0, 0.9),    # Deep blue
        ],
        secondary=[
            RGB.from_hsv(270, 1.0, 0.8),    # Purple
            RGB.from_hsv(160, 0.9, 0.9),    # Teal
        ],
        accent=[
            RGB(1.0, 1.0, 1.0),             # White (strobe flash)
            RGB.from_hsv(50, 1.0, 1.0),     # Gold (rare accents)
        ],
        accent_threshold=0.85,
        transition_speed=0.08,
    ),
    movement=MovementProfile(
        low_energy_speed=0.15,
        mid_energy_speed=0.35,
        high_energy_speed=0.7,
        pan_amplitude_range=(40.0, 90.0),
        tilt_amplitude_range=(25.0, 55.0),
        default_phase_spread=1.0,
        intro_patterns=[MovementType.TRUE_CIRCLE, MovementType.VERTICAL_SWEEP],
        verse_patterns=[MovementType.HORIZONTAL_SWEEP, MovementType.TRUE_CIRCLE, MovementType.MIRROR_SWEEP],
        chorus_patterns=[MovementType.CIRCLE_CHASE, MovementType.BALLYHOO, MovementType.COUNTER_ROTATION],
        drop_patterns=[MovementType.ALTERNATING, MovementType.MIRROR_SWEEP, MovementType.CENTER_OUT_WAVE],
        breakdown_patterns=[MovementType.TRUE_CIRCLE, MovementType.SPIRAL, MovementType.VERTICAL_SWEEP],
        bpm_lock=True,
        beat_divisor=1.0,
    ),
    strobe=StrobeProfile(
        enabled=True,
        max_continuous_hz=4.0,
        burst_on_drop=True,
        burst_frequency=15.0,
        burst_duration=2.0,
        beat_locked_enabled=True,
        beat_locked_beats=[0],
        blinder_on_climax=True,
        blinder_duration=0.08,
    ),
    timing=TimingProfile(
        bpm_range=(120.0, 150.0),
        anticipation_bars=1.0,
        min_effect_duration_bars=4,
        beat_weights=(1.0, 0.5, 0.3, 0.6),  # Kick-heavy
        transition_style="bump",
        crossfade_bars=0.25,
    ),
    intensity=SectionIntensity(
        intro=(0.3, 0.5),
        verse=(0.5, 0.7),
        pre_chorus=(0.6, 0.85),
        chorus=(0.85, 1.0),
        drop=(0.95, 1.0),
        breakdown=(0.15, 0.35),
        bridge=(0.4, 0.6),
        outro=(0.2, 0.4),
    ),
    color_palette=ColorPalette.EDM,
    preferred_static_looks=[StaticLook.X_PATTERN, StaticLook.FAN_OUT, StaticLook.ALL_CENTER],
    front_light_style="cool",
    haze_level=0.9,
)


_ROCK_PROFILE = GenreProfile(
    genre=Genre.ROCK,
    name="Rock / Metal",
    description="Aggressive red/amber lighting with strong snare hits, "
                "dramatic tilt bumps, and punchy movements.",
    colors=ColorScheme(
        primary=[
            RGB.from_hsv(0, 1.0, 1.0),      # Red
            RGB.from_hsv(30, 1.0, 1.0),      # Orange/amber
            RGB.from_hsv(220, 0.9, 0.8),     # Deep blue
        ],
        secondary=[
            RGB.from_hsv(45, 1.0, 1.0),      # Gold
            RGB.from_hsv(0, 0.8, 0.5),       # Dark red
        ],
        accent=[
            RGB(1.0, 1.0, 1.0),              # White (guitar solo)
            RGB.from_hsv(270, 1.0, 0.9),     # Purple (power moment)
        ],
        accent_threshold=0.8,
        transition_speed=0.05,  # Fast transitions
    ),
    movement=MovementProfile(
        low_energy_speed=0.1,
        mid_energy_speed=0.25,
        high_energy_speed=0.5,
        pan_amplitude_range=(35.0, 75.0),
        tilt_amplitude_range=(30.0, 60.0),
        default_phase_spread=0.6,  # Less spread, more unified power
        intro_patterns=[MovementType.VERTICAL_SWEEP, MovementType.NONE],
        verse_patterns=[MovementType.HORIZONTAL_SWEEP, MovementType.TILT_CHASE],
        chorus_patterns=[MovementType.BALLYHOO, MovementType.ALTERNATING, MovementType.MIRROR_SWEEP],
        drop_patterns=[MovementType.TILT_BUMP, MovementType.PAN_BUMP, MovementType.COUNTER_ROTATION],
        breakdown_patterns=[MovementType.NONE, MovementType.VERTICAL_SWEEP],
        bpm_lock=True,
        beat_divisor=1.0,
    ),
    strobe=StrobeProfile(
        enabled=True,
        max_continuous_hz=3.0,
        burst_on_drop=True,
        burst_frequency=12.0,
        burst_duration=1.5,
        beat_locked_enabled=True,
        beat_locked_beats=[0, 2],  # Kick and snare
        blinder_on_climax=True,
        blinder_duration=0.1,
    ),
    timing=TimingProfile(
        bpm_range=(100.0, 180.0),
        anticipation_bars=0.5,
        min_effect_duration_bars=4,
        beat_weights=(0.9, 1.0, 0.2, 0.4),  # Snare-heavy
        transition_style="cut",
        crossfade_bars=0.25,
    ),
    intensity=SectionIntensity(
        intro=(0.3, 0.5),
        verse=(0.5, 0.7),
        pre_chorus=(0.65, 0.85),
        chorus=(0.8, 1.0),
        drop=(0.9, 1.0),
        breakdown=(0.2, 0.4),
        bridge=(0.5, 0.7),
        outro=(0.3, 0.5),
    ),
    color_palette=ColorPalette.ROCK,
    preferred_static_looks=[StaticLook.ALL_CENTER, StaticLook.X_PATTERN, StaticLook.OPPOSING_CORNERS],
    front_light_style="warm",
    haze_level=0.6,
)


_POP_PROFILE = GenreProfile(
    genre=Genre.POP,
    name="Pop",
    description="Colorful, dynamic lighting with wide color spectrum, "
                "smooth movements, and audience-friendly brightness.",
    colors=ColorScheme(
        primary=[
            RGB.from_hsv(300, 0.8, 1.0),    # Pink
            RGB.from_hsv(200, 0.9, 1.0),    # Sky blue
            RGB.from_hsv(60, 1.0, 1.0),     # Yellow
        ],
        secondary=[
            RGB.from_hsv(150, 0.8, 0.9),    # Mint green
            RGB.from_hsv(30, 0.9, 1.0),     # Peach
            RGB.from_hsv(270, 0.7, 1.0),    # Lavender
        ],
        accent=[
            RGB(1.0, 1.0, 1.0),             # White
            RGB.from_hsv(330, 1.0, 1.0),    # Hot pink
        ],
        accent_threshold=0.75,
        transition_speed=0.12,
    ),
    movement=MovementProfile(
        low_energy_speed=0.2,
        mid_energy_speed=0.35,
        high_energy_speed=0.5,
        pan_amplitude_range=(35.0, 70.0),
        tilt_amplitude_range=(20.0, 45.0),
        default_phase_spread=0.8,
        intro_patterns=[MovementType.TRUE_CIRCLE, MovementType.HORIZONTAL_SWEEP],
        verse_patterns=[MovementType.MIRROR_SWEEP, MovementType.TRUE_CIRCLE, MovementType.PAN_CHASE],
        chorus_patterns=[MovementType.BALLYHOO, MovementType.CIRCLE_CHASE, MovementType.CENTER_OUT_WAVE],
        drop_patterns=[MovementType.ALTERNATING, MovementType.MIRROR_SWEEP],
        breakdown_patterns=[MovementType.TRUE_CIRCLE, MovementType.SPIRAL],
        bpm_lock=True,
        beat_divisor=1.0,
    ),
    strobe=StrobeProfile(
        enabled=True,
        max_continuous_hz=3.0,
        burst_on_drop=False,  # Less aggressive strobe
        burst_frequency=8.0,
        burst_duration=1.0,
        beat_locked_enabled=True,
        beat_locked_beats=[0],
        blinder_on_climax=True,
        blinder_duration=0.08,
    ),
    timing=TimingProfile(
        bpm_range=(100.0, 130.0),
        anticipation_bars=1.0,
        min_effect_duration_bars=8,
        beat_weights=(0.8, 0.9, 0.4, 0.5),  # Balanced
        transition_style="crossfade",
        crossfade_bars=1.0,
    ),
    intensity=SectionIntensity(
        intro=(0.4, 0.6),
        verse=(0.5, 0.7),
        pre_chorus=(0.65, 0.8),
        chorus=(0.8, 1.0),
        drop=(0.85, 1.0),
        breakdown=(0.3, 0.5),
        bridge=(0.5, 0.7),
        outro=(0.3, 0.5),
    ),
    color_palette=ColorPalette.POP,
    preferred_static_looks=[StaticLook.FAN_OUT, StaticLook.ALL_CENTER, StaticLook.CIRCLE_FLOOR],
    front_light_style="neutral",
    haze_level=0.5,
)


_HIP_HOP_PROFILE = GenreProfile(
    genre=Genre.HIP_HOP,
    name="Hip-Hop / R&B",
    description="Purple/gold palette with strong bass response, "
                "slow dramatic movements, and punchy beat accents.",
    colors=ColorScheme(
        primary=[
            RGB.from_hsv(270, 0.9, 0.9),    # Purple
            RGB.from_hsv(45, 1.0, 1.0),      # Gold
            RGB.from_hsv(0, 1.0, 0.8),       # Red
        ],
        secondary=[
            RGB.from_hsv(290, 0.8, 0.7),     # Dark purple
            RGB.from_hsv(200, 0.8, 0.9),     # Steel blue
        ],
        accent=[
            RGB(1.0, 1.0, 1.0),              # White
            RGB.from_hsv(30, 1.0, 1.0),      # Amber
        ],
        accent_threshold=0.8,
        transition_speed=0.06,
    ),
    movement=MovementProfile(
        low_energy_speed=0.1,
        mid_energy_speed=0.2,
        high_energy_speed=0.4,
        pan_amplitude_range=(25.0, 60.0),
        tilt_amplitude_range=(20.0, 45.0),
        default_phase_spread=0.5,
        intro_patterns=[MovementType.NONE, MovementType.VERTICAL_SWEEP],
        verse_patterns=[MovementType.HORIZONTAL_SWEEP, MovementType.TILT_CHASE],
        chorus_patterns=[MovementType.MIRROR_SWEEP, MovementType.BALLYHOO, MovementType.PAN_CHASE],
        drop_patterns=[MovementType.TILT_BUMP, MovementType.CENTER_OUT_WAVE],
        breakdown_patterns=[MovementType.NONE, MovementType.SPIRAL],
        bpm_lock=True,
        beat_divisor=0.5,  # Half-time feel
    ),
    strobe=StrobeProfile(
        enabled=True,
        max_continuous_hz=3.0,
        burst_on_drop=True,
        burst_frequency=10.0,
        burst_duration=1.5,
        beat_locked_enabled=True,
        beat_locked_beats=[0, 2],  # Kick emphasis
        blinder_on_climax=True,
        blinder_duration=0.1,
    ),
    timing=TimingProfile(
        bpm_range=(80.0, 110.0),
        anticipation_bars=1.0,
        min_effect_duration_bars=4,
        beat_weights=(1.0, 0.6, 0.5, 0.3),  # Bass-heavy
        transition_style="crossfade",
        crossfade_bars=0.5,
    ),
    intensity=SectionIntensity(
        intro=(0.3, 0.5),
        verse=(0.5, 0.65),
        pre_chorus=(0.6, 0.75),
        chorus=(0.75, 0.95),
        drop=(0.9, 1.0),
        breakdown=(0.2, 0.4),
        bridge=(0.4, 0.6),
        outro=(0.2, 0.4),
    ),
    color_palette=ColorPalette.HIP_HOP,
    preferred_static_looks=[StaticLook.ALL_CENTER, StaticLook.OPPOSING_CORNERS, StaticLook.STAGGERED_HEIGHTS],
    front_light_style="warm",
    haze_level=0.6,
)


_JAZZ_PROFILE = GenreProfile(
    genre=Genre.JAZZ,
    name="Jazz / Blues",
    description="Warm, subtle lighting with amber/blue palette, "
                "minimal movement, and emphasis on performer illumination.",
    colors=ColorScheme(
        primary=[
            RGB.from_hsv(35, 0.8, 0.9),     # Warm amber
            RGB.from_hsv(220, 0.6, 0.7),    # Soft blue
            RGB.from_hsv(15, 0.7, 0.8),     # Warm white/cream
        ],
        secondary=[
            RGB.from_hsv(45, 0.5, 0.8),     # Pale gold
            RGB.from_hsv(200, 0.4, 0.6),    # Muted blue
        ],
        accent=[
            RGB.from_hsv(0, 0.6, 0.7),      # Muted red (solo)
            RGB.from_hsv(270, 0.4, 0.6),    # Soft lavender
        ],
        accent_threshold=0.7,
        transition_speed=0.2,  # Very slow, subtle transitions
    ),
    movement=MovementProfile(
        low_energy_speed=0.05,
        mid_energy_speed=0.1,
        high_energy_speed=0.2,
        pan_amplitude_range=(10.0, 30.0),
        tilt_amplitude_range=(8.0, 20.0),
        default_phase_spread=0.3,
        intro_patterns=[MovementType.NONE],
        verse_patterns=[MovementType.NONE, MovementType.VERTICAL_SWEEP],
        chorus_patterns=[MovementType.TRUE_CIRCLE, MovementType.HORIZONTAL_SWEEP],
        drop_patterns=[MovementType.HORIZONTAL_SWEEP],  # Jazz doesn't really "drop"
        breakdown_patterns=[MovementType.NONE],
        bpm_lock=False,  # Jazz is more free-form
        beat_divisor=0.5,
    ),
    strobe=StrobeProfile(
        enabled=False,  # No strobe for jazz
        max_continuous_hz=0.0,
        burst_on_drop=False,
        burst_frequency=0.0,
        burst_duration=0.0,
        beat_locked_enabled=False,
        beat_locked_beats=[],
        blinder_on_climax=False,
        blinder_duration=0.0,
    ),
    timing=TimingProfile(
        bpm_range=(60.0, 180.0),  # Wide range for jazz
        anticipation_bars=2.0,
        min_effect_duration_bars=8,
        beat_weights=(0.6, 0.5, 0.7, 0.3),  # Hi-hat swing emphasis
        transition_style="crossfade",
        crossfade_bars=2.0,
    ),
    intensity=SectionIntensity(
        intro=(0.3, 0.45),
        verse=(0.4, 0.55),
        pre_chorus=(0.45, 0.6),
        chorus=(0.55, 0.7),
        drop=(0.6, 0.75),
        breakdown=(0.25, 0.4),
        bridge=(0.4, 0.55),
        outro=(0.2, 0.35),
    ),
    color_palette=ColorPalette.AMBIENT,
    preferred_static_looks=[StaticLook.ALL_CENTER, StaticLook.STAGGERED_HEIGHTS],
    front_light_style="warm",
    haze_level=0.2,
)


# Registry of all genre profiles
GENRE_PROFILES: Dict[Genre, GenreProfile] = {
    Genre.EDM: _EDM_PROFILE,
    Genre.ROCK: _ROCK_PROFILE,
    Genre.POP: _POP_PROFILE,
    Genre.HIP_HOP: _HIP_HOP_PROFILE,
    Genre.JAZZ: _JAZZ_PROFILE,
}


class GenreProfileManager:
    """
    Manages genre profiles and provides real-time parameter lookup
    for the effects engine.
    """

    def __init__(self, default_genre: Genre = Genre.EDM):
        self._current_genre = default_genre
        self._profile = GENRE_PROFILES[default_genre]
        self._blend_factor = 0.0
        self._blend_target: Optional[GenreProfile] = None
        self._blend_speed = 0.02  # Per frame blend increment

    @property
    def current_genre(self) -> Genre:
        return self._current_genre

    @property
    def profile(self) -> GenreProfile:
        return self._profile

    def set_genre(self, genre: Genre, crossfade: bool = True):
        """Switch to a new genre profile."""
        if genre == self._current_genre:
            return
        if genre not in GENRE_PROFILES:
            return

        if crossfade:
            self._blend_target = GENRE_PROFILES[genre]
            self._blend_factor = 0.0
        else:
            self._profile = GENRE_PROFILES[genre]
            self._blend_target = None

        self._current_genre = genre

    def update(self, delta_time: float):
        """Update genre blending."""
        if self._blend_target is not None:
            self._blend_factor += self._blend_speed * delta_time * 60.0
            if self._blend_factor >= 1.0:
                self._profile = self._blend_target
                self._blend_target = None
                self._blend_factor = 0.0

    def get_movement_speed(self, energy: float) -> float:
        """Get movement speed for current energy level."""
        m = self._profile.movement
        if energy < 0.33:
            return m.low_energy_speed
        elif energy < 0.66:
            return m.mid_energy_speed + (energy - 0.33) / 0.33 * (m.high_energy_speed - m.mid_energy_speed)
        else:
            return m.high_energy_speed

    def get_pan_amplitude(self, energy: float) -> float:
        """Get pan amplitude for current energy level."""
        low, high = self._profile.movement.pan_amplitude_range
        return low + energy * (high - low)

    def get_tilt_amplitude(self, energy: float) -> float:
        """Get tilt amplitude for current energy level."""
        low, high = self._profile.movement.tilt_amplitude_range
        return low + energy * (high - low)

    def get_intensity_range(self, section: str) -> Tuple[float, float]:
        """Get intensity range for a song section."""
        intensity = self._profile.intensity
        return getattr(intensity, section, (0.5, 0.7))

    def get_section_patterns(self, section: str) -> List[MovementType]:
        """Get preferred movement patterns for a section."""
        m = self._profile.movement
        patterns_map = {
            "intro": m.intro_patterns,
            "verse": m.verse_patterns,
            "chorus": m.chorus_patterns,
            "drop": m.drop_patterns,
            "breakdown": m.breakdown_patterns,
        }
        return patterns_map.get(section, m.verse_patterns)

    def get_primary_colors(self) -> List[RGB]:
        """Get primary colors for current genre."""
        return self._profile.colors.primary

    def get_color_for_energy(self, energy: float, phase: float = 0.0) -> RGB:
        """Get appropriate color based on energy level and phase."""
        colors = self._profile.colors
        if energy > colors.accent_threshold and colors.accent:
            color_list = colors.accent
        elif energy > 0.5:
            color_list = colors.primary
        else:
            color_list = colors.secondary if colors.secondary else colors.primary

        if not color_list:
            return RGB(1.0, 1.0, 1.0)

        # Use phase to select and blend between colors
        idx = phase * len(color_list)
        idx_int = int(idx) % len(color_list)
        next_idx = (idx_int + 1) % len(color_list)
        blend = idx - int(idx)

        return color_list[idx_int].blend(color_list[next_idx], blend)

    def should_strobe(self) -> bool:
        """Check if current genre allows strobe."""
        return self._profile.strobe.enabled

    def get_strobe_params(self) -> StrobeProfile:
        """Get strobe parameters for current genre."""
        return self._profile.strobe

    def get_beat_weights(self) -> Tuple[float, float, float, float]:
        """Get beat emphasis weights (kick, snare, hi-hat, open-hat)."""
        return self._profile.timing.beat_weights
