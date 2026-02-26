"""
Color Mapper
Maps audio features to colors based on color psychology research.

Research basis:
- Lightness = Valence (happiness)
- Saturation = Arousal (energy)
- Hue = Genre/mood specific
"""

from enum import Enum
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
import math
import random


class ColorPalette(Enum):
    """Genre-specific color palettes."""
    EDM = "edm"                # Cyan, Magenta, UV
    ROCK = "rock"              # Red, Amber, Deep Blue
    AMBIENT = "ambient"        # Light Blue, Pale Green
    HIP_HOP = "hip_hop"        # Purple, Gold, Red
    POP = "pop"                # Bright multi-color
    TECHNO = "techno"          # Cold white, Blue, Green
    HOUSE = "house"            # Warm colors, Orange, Yellow
    DUBSTEP = "dubstep"        # Purple, Green, White strobes


@dataclass
class RGB:
    """RGB color (0-1 range)."""
    r: float
    g: float
    b: float

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.r, self.g, self.b)

    def to_int_tuple(self) -> Tuple[int, int, int]:
        return (int(self.r * 255), int(self.g * 255), int(self.b * 255))

    @classmethod
    def from_hsv(cls, h: float, s: float, v: float) -> 'RGB':
        """Create RGB from HSV (h: 0-360, s: 0-1, v: 0-1)."""
        h = h % 360
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return cls(r + m, g + m, b + m)

    def blend(self, other: 'RGB', factor: float) -> 'RGB':
        """Blend with another color."""
        return RGB(
            self.r + (other.r - self.r) * factor,
            self.g + (other.g - self.g) * factor,
            self.b + (other.b - self.b) * factor
        )


@dataclass
class AudioFeatures:
    """Audio features for color mapping."""
    energy: float = 0.5          # Overall RMS energy (0-1)
    bass: float = 0.5            # Bass band energy (0-1)
    mid: float = 0.5             # Mid band energy (0-1)
    high: float = 0.5            # High band energy (0-1)
    valence: float = 0.5         # Mood: 0=sad, 1=happy
    arousal: float = 0.5         # Energy: 0=calm, 1=excited
    is_beat: bool = False        # Beat detected this frame
    beat_intensity: float = 0.0  # Beat strength (0-1)


class ColorMapper:
    """
    Maps audio features to fixture colors based on psychology research.
    """

    def __init__(self, palette: ColorPalette = ColorPalette.EDM):
        self.palette = palette
        self.time = 0.0

        # Color transition state
        self._current_color = RGB(1, 1, 1)
        self._target_color = RGB(1, 1, 1)
        self._transition_speed = 0.1  # Blend factor at 60fps baseline
        self._delta_time = 1.0 / 60.0  # BUG-021 fix: store delta_time for frame-rate independence

        # Beat color flash
        self._beat_color: Optional[RGB] = None
        self._beat_flash_time = 0.0

        # Palette definitions (hue ranges in degrees)
        self._palette_hues = {
            ColorPalette.EDM: [(180, 270), (300, 360)],       # Cyan-Blue, Magenta
            ColorPalette.ROCK: [(0, 30), (200, 240)],         # Red-Orange, Blue
            ColorPalette.AMBIENT: [(180, 220), (80, 140)],    # Cyan, Green
            ColorPalette.HIP_HOP: [(270, 310), (40, 60)],     # Purple, Gold
            ColorPalette.POP: [(0, 360)],                     # Full spectrum
            ColorPalette.TECHNO: [(180, 240), (100, 140)],    # Cyan-Blue, Green
            ColorPalette.HOUSE: [(20, 60), (0, 30)],          # Orange-Yellow, Red
            ColorPalette.DUBSTEP: [(270, 300), (100, 140)],   # Purple, Green
        }

    def set_palette(self, palette: ColorPalette):
        """Set the color palette."""
        self.palette = palette

    def update(self, delta_time: float):
        """Update color state."""
        self.time += delta_time
        self._delta_time = delta_time

        # BUG-021 fix: frame-rate-independent smoothing using exponential decay
        # At 60fps (dt=0.0167), factor ≈ _transition_speed (preserves original feel)
        blend_factor = 1.0 - (1.0 - self._transition_speed) ** (delta_time * 60.0)

        # Smooth color transition
        self._current_color = self._current_color.blend(
            self._target_color,
            blend_factor
        )

    def get_color(
        self,
        features: AudioFeatures,
        fixture_index: int = 0,
        phase_offset: float = 0.0
    ) -> RGB:
        """
        Calculate color based on audio features.

        Args:
            features: Current audio analysis
            fixture_index: Fixture index for variation
            phase_offset: Phase offset for color chase

        Returns:
            RGB color
        """
        # Get base hue from palette and energy
        hue = self._get_palette_hue(features, fixture_index, phase_offset)

        # Saturation from arousal (energy level)
        # High energy = high saturation, low energy = desaturated
        saturation = 0.4 + features.arousal * 0.6

        # Value (brightness) from energy and valence
        # Happy + energetic = bright, sad + calm = dim
        value = 0.3 + (features.valence * 0.3 + features.energy * 0.4)

        # Create color from HSV
        color = RGB.from_hsv(hue, saturation, value)

        # Apply beat flash
        if features.is_beat and features.beat_intensity > 0.5:
            # Flash toward white on strong beats
            flash_amount = features.beat_intensity * 0.5
            color = color.blend(RGB(1, 1, 1), flash_amount)

        self._target_color = color
        # BUG-015 fix: apply smoothing toward new target before returning
        # BUG-021 fix: frame-rate-independent blend factor
        blend_factor = 1.0 - (1.0 - self._transition_speed) ** (self._delta_time * 60.0)
        self._current_color = self._current_color.blend(
            self._target_color,
            blend_factor
        )
        return self._current_color

    def _get_palette_hue(
        self,
        features: AudioFeatures,
        fixture_index: int,
        phase_offset: float
    ) -> float:
        """Get hue value from palette based on audio."""
        hue_ranges = self._palette_hues.get(
            self.palette,
            [(0, 360)]
        )

        # Select hue range based on audio features
        if len(hue_ranges) == 1:
            hue_min, hue_max = hue_ranges[0]
        else:
            # Two-color discipline: alternate fixture families between primary/secondary
            # and bias toward primary on stronger musical moments.
            primary_on = features.bass > 0.6 or features.energy > 0.72
            use_primary = primary_on if (fixture_index % 2 == 0) else (not primary_on)
            hue_min, hue_max = hue_ranges[0] if use_primary else hue_ranges[-1]

        # Map valence to position within hue range for mood-driven shifts
        hue_range = hue_max - hue_min
        energy_hue = hue_min + features.valence * hue_range

        # Keep drift subtle to avoid random rainbow noise.
        drift = math.sin(self.time * 0.12 + phase_offset * math.pi * 2) * 4
        hue = (energy_hue + drift) % 360
        return hue

    def get_bass_color(self, bass_energy: float) -> RGB:
        """Get color specifically driven by bass."""
        # Bass = warm colors (red, orange, amber)
        hue = 30 - bass_energy * 30  # 30 (orange) to 0 (red)
        saturation = 0.8 + bass_energy * 0.2
        value = 0.5 + bass_energy * 0.5
        return RGB.from_hsv(hue, saturation, value)

    def get_mid_color(self, mid_energy: float) -> RGB:
        """Get color driven by mids."""
        # Mids = greens and yellows
        hue = 60 + mid_energy * 60  # 60 (yellow) to 120 (green)
        saturation = 0.7 + mid_energy * 0.3
        value = 0.5 + mid_energy * 0.5
        return RGB.from_hsv(hue, saturation, value)

    def get_high_color(self, high_energy: float) -> RGB:
        """Get color driven by highs."""
        # Highs = cool colors (cyan, blue, white)
        hue = 180 + high_energy * 60  # 180 (cyan) to 240 (blue)
        saturation = 0.6 - high_energy * 0.4  # More white at high energy
        value = 0.6 + high_energy * 0.4
        return RGB.from_hsv(hue, saturation, value)

    def get_frequency_split_colors(
        self,
        features: AudioFeatures
    ) -> Tuple[RGB, RGB, RGB]:
        """
        Get three colors for bass/mid/high frequency split lighting.

        Returns:
            Tuple of (bass_color, mid_color, high_color)
        """
        return (
            self.get_bass_color(features.bass),
            self.get_mid_color(features.mid),
            self.get_high_color(features.high)
        )


class ColorChase:
    """
    Color chase effect across fixtures.
    """

    def __init__(
        self,
        colors: List[RGB] = None,
        speed: float = 1.0,
        blend: bool = True
    ):
        """
        Args:
            colors: List of colors to chase
            speed: Chase speed (cycles per second)
            blend: Blend between colors vs hard cuts
        """
        self.colors = colors or [
            RGB.from_hsv(0, 1, 1),    # Red
            RGB.from_hsv(120, 1, 1),  # Green
            RGB.from_hsv(240, 1, 1),  # Blue
        ]
        self.speed = speed
        self.blend = blend
        self.time = 0.0

    def update(self, delta_time: float):
        self.time += delta_time

    def get_color(self, index: int, total_fixtures: int) -> RGB:
        """Get color for fixture at index."""
        num_colors = len(self.colors)

        # Calculate position in color cycle
        cycle_pos = (self.time * self.speed) % 1.0
        fixture_phase = index / total_fixtures

        color_pos = (cycle_pos + fixture_phase) * num_colors

        if self.blend:
            # Smooth blend between colors
            color_idx = int(color_pos) % num_colors
            next_idx = (color_idx + 1) % num_colors
            blend_factor = color_pos % 1.0

            return self.colors[color_idx].blend(
                self.colors[next_idx],
                blend_factor
            )
        else:
            # Hard color cuts
            color_idx = int(color_pos) % num_colors
            return self.colors[color_idx]


# Preset color palettes
COLOR_PRESETS = {
    "rgb_chase": [
        RGB.from_hsv(0, 1, 1),
        RGB.from_hsv(120, 1, 1),
        RGB.from_hsv(240, 1, 1)
    ],
    "warm": [
        RGB.from_hsv(0, 1, 1),
        RGB.from_hsv(30, 1, 1),
        RGB.from_hsv(60, 1, 1)
    ],
    "cool": [
        RGB.from_hsv(180, 1, 1),
        RGB.from_hsv(210, 1, 1),
        RGB.from_hsv(240, 1, 1)
    ],
    "purple_gold": [
        RGB.from_hsv(280, 0.9, 1),
        RGB.from_hsv(45, 1, 1)
    ],
    "fire": [
        RGB.from_hsv(0, 1, 1),
        RGB.from_hsv(30, 1, 1),
        RGB.from_hsv(45, 0.9, 1)
    ],
    "ocean": [
        RGB.from_hsv(180, 0.8, 0.9),
        RGB.from_hsv(200, 0.9, 1),
        RGB.from_hsv(220, 1, 0.8)
    ],
    "neon": [
        RGB.from_hsv(300, 1, 1),
        RGB.from_hsv(180, 1, 1),
        RGB.from_hsv(60, 1, 1)
    ],
    "white_strobe": [
        RGB(1, 1, 1)
    ],
    "uv_purple": [
        RGB.from_hsv(270, 0.9, 0.9),
        RGB.from_hsv(280, 1, 1),
        RGB.from_hsv(290, 0.85, 0.95)
    ]
}


# Mood-to-color mapping based on psychology research
MOOD_COLORS = {
    # Valence (x-axis: negative to positive)
    # Arousal (y-axis: low to high)

    # Low arousal, low valence (sad, depressed)
    "sad": RGB.from_hsv(240, 0.6, 0.4),  # Dark blue

    # Low arousal, high valence (calm, relaxed)
    "calm": RGB.from_hsv(180, 0.5, 0.6),  # Soft cyan

    # High arousal, low valence (angry, tense)
    "angry": RGB.from_hsv(0, 0.9, 0.8),  # Intense red

    # High arousal, high valence (happy, excited)
    "happy": RGB.from_hsv(50, 0.9, 1.0),  # Bright yellow-orange

    # Neutral
    "neutral": RGB.from_hsv(0, 0, 0.7),  # Neutral white
}
