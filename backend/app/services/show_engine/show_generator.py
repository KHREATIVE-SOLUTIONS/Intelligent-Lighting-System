"""
Show Generator
==============

Generates lighting shows from emotion/mood data.
"""

import asyncio
import colorsys
import random
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.models.show import Show, ShowCue, ShowTrack, CueType
from app.schemas.audio import MoodResponse, BeatResponse


class EmotionColorMapper:
    """Maps emotions to colors using the valence-arousal model."""

    # Color mappings for quadrants of valence-arousal space
    # Format: (valence_range, arousal_range): (hue, saturation_range)
    EMOTION_COLORS = {
        # High arousal, high valence (excited, happy)
        'excited': {'hue': 0.1, 'saturation': 0.9, 'value': 1.0},  # Yellow-orange
        'happy': {'hue': 0.15, 'saturation': 0.8, 'value': 0.95},  # Yellow

        # High arousal, low valence (angry, tense)
        'angry': {'hue': 0.0, 'saturation': 1.0, 'value': 1.0},  # Red
        'tense': {'hue': 0.95, 'saturation': 0.9, 'value': 0.9},  # Deep red

        # Low arousal, low valence (sad, depressed)
        'sad': {'hue': 0.6, 'saturation': 0.7, 'value': 0.5},  # Blue
        'melancholic': {'hue': 0.7, 'saturation': 0.6, 'value': 0.6},  # Purple

        # Low arousal, high valence (calm, relaxed)
        'calm': {'hue': 0.35, 'saturation': 0.5, 'value': 0.7},  # Green
        'relaxed': {'hue': 0.45, 'saturation': 0.4, 'value': 0.8},  # Cyan-green

        # Neutral
        'neutral': {'hue': 0.0, 'saturation': 0.0, 'value': 0.8},  # White
    }

    @classmethod
    def get_color_for_mood(cls, valence: float, arousal: float) -> Dict[str, float]:
        """
        Get HSV color for a given valence-arousal point.

        Args:
            valence: -1 (negative) to 1 (positive)
            arousal: -1 (calm) to 1 (energetic)

        Returns:
            Dictionary with hue, saturation, value
        """
        # Determine quadrant
        if arousal > 0.3:
            if valence > 0.3:
                base = cls.EMOTION_COLORS['excited']
            elif valence < -0.3:
                base = cls.EMOTION_COLORS['angry']
            else:
                # Interpolate
                if valence >= 0:
                    base = cls._interpolate(
                        cls.EMOTION_COLORS['excited'],
                        cls.EMOTION_COLORS['neutral'],
                        1 - valence / 0.3
                    )
                else:
                    base = cls._interpolate(
                        cls.EMOTION_COLORS['angry'],
                        cls.EMOTION_COLORS['neutral'],
                        1 + valence / 0.3
                    )
        elif arousal < -0.3:
            if valence > 0.3:
                base = cls.EMOTION_COLORS['calm']
            elif valence < -0.3:
                base = cls.EMOTION_COLORS['sad']
            else:
                if valence >= 0:
                    base = cls._interpolate(
                        cls.EMOTION_COLORS['calm'],
                        cls.EMOTION_COLORS['neutral'],
                        1 - valence / 0.3
                    )
                else:
                    base = cls._interpolate(
                        cls.EMOTION_COLORS['sad'],
                        cls.EMOTION_COLORS['neutral'],
                        1 + valence / 0.3
                    )
        else:
            # Middle arousal - blend between high and low
            if valence > 0.3:
                high = cls.EMOTION_COLORS['excited']
                low = cls.EMOTION_COLORS['calm']
            elif valence < -0.3:
                high = cls.EMOTION_COLORS['angry']
                low = cls.EMOTION_COLORS['sad']
            else:
                base = cls.EMOTION_COLORS['neutral']
                return base

            progress = (arousal + 0.3) / 0.6
            base = cls._interpolate(low, high, progress)

        return base

    @classmethod
    def _interpolate(
        cls,
        color1: Dict[str, float],
        color2: Dict[str, float],
        t: float
    ) -> Dict[str, float]:
        """Interpolate between two HSV colors."""
        return {
            'hue': color1['hue'] + (color2['hue'] - color1['hue']) * t,
            'saturation': color1['saturation'] + (color2['saturation'] - color1['saturation']) * t,
            'value': color1['value'] + (color2['value'] - color1['value']) * t,
        }

    @classmethod
    def hsv_to_rgb(cls, h: float, s: float, v: float) -> tuple:
        """Convert HSV to RGB (0-255)."""
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (int(r * 255), int(g * 255), int(b * 255))


class MovementGenerator:
    """Generates fixture movement patterns based on music."""

    # Movement patterns
    PATTERNS = {
        'circle': lambda t, speed: (
            50 + 40 * math.cos(t * speed),
            50 + 40 * math.sin(t * speed)
        ),
        'figure_eight': lambda t, speed: (
            50 + 40 * math.sin(t * speed),
            50 + 20 * math.sin(2 * t * speed)
        ),
        'sweep': lambda t, speed: (
            50 + 40 * math.sin(t * speed),
            50
        ),
        'tilt_sweep': lambda t, speed: (
            50,
            50 + 40 * math.sin(t * speed)
        ),
        'random': lambda t, speed: (
            50 + random.uniform(-40, 40),
            50 + random.uniform(-40, 40)
        ),
    }

    @classmethod
    def get_movement(
        cls,
        pattern: str,
        time: float,
        arousal: float
    ) -> tuple:
        """
        Get pan/tilt values for a movement pattern.

        Args:
            pattern: Pattern name
            time: Current time in seconds
            arousal: Arousal level (-1 to 1) affects speed

        Returns:
            Tuple of (pan%, tilt%) from 0-100
        """
        import math

        # Speed based on arousal (higher arousal = faster movement)
        speed = 0.5 + (arousal + 1) * 0.75  # 0.5 to 2.0

        if pattern in cls.PATTERNS:
            return cls.PATTERNS[pattern](time, speed)
        return (50, 50)  # Center position


class EffectsEngine:
    """Generates lighting effects."""

    @classmethod
    def strobe_effect(
        cls,
        time: float,
        rate: float,
        intensity: float = 1.0
    ) -> float:
        """
        Generate strobe effect value.

        Args:
            time: Current time
            rate: Strobe rate in Hz
            intensity: Maximum intensity (0-1)

        Returns:
            Intensity value (0-1)
        """
        import math
        phase = (time * rate * 2 * math.pi) % (2 * math.pi)
        return intensity if phase < math.pi * 0.1 else 0.0

    @classmethod
    def pulse_effect(
        cls,
        time: float,
        rate: float,
        min_intensity: float = 0.0,
        max_intensity: float = 1.0
    ) -> float:
        """
        Generate pulse/breathing effect.

        Args:
            time: Current time
            rate: Pulse rate in Hz
            min_intensity: Minimum intensity
            max_intensity: Maximum intensity

        Returns:
            Intensity value
        """
        import math
        value = (math.sin(time * rate * 2 * math.pi) + 1) / 2
        return min_intensity + value * (max_intensity - min_intensity)

    @classmethod
    def chase_effect(
        cls,
        time: float,
        fixture_index: int,
        total_fixtures: int,
        speed: float
    ) -> float:
        """
        Generate chase effect for a specific fixture.

        Args:
            time: Current time
            fixture_index: Index of this fixture (0-based)
            total_fixtures: Total number of fixtures in chase
            speed: Chase speed (cycles per second)

        Returns:
            Intensity value (0-1)
        """
        import math
        phase = (time * speed + fixture_index / total_fixtures) % 1.0
        # Gaussian falloff
        return math.exp(-((phase - 0.5) ** 2) / 0.02)


class ShowGenerator:
    """Generates complete lighting shows from audio analysis."""

    def __init__(self):
        """Initialize the show generator."""
        self.color_mapper = EmotionColorMapper()
        self.effects_engine = EffectsEngine()

    async def generate_show(
        self,
        name: str,
        duration: float,
        bpm: float,
        mood_data: List[MoodResponse],
        beat_data: List[BeatResponse],
        fixture_count: int = 8,
    ) -> Show:
        """
        Generate a complete show from audio analysis data.

        Args:
            name: Show name
            duration: Show duration in seconds
            bpm: Beats per minute
            mood_data: List of mood analysis results over time
            beat_data: List of beat detection results over time
            fixture_count: Number of fixtures to program

        Returns:
            Generated Show object
        """
        show = Show(
            name=name,
            duration=duration,
            bpm=bpm,
            base_valence=sum(m.valence for m in mood_data) / len(mood_data) if mood_data else 0.5,
            base_arousal=sum(m.arousal for m in mood_data) / len(mood_data) if mood_data else 0.5,
        )

        # Create tracks for different fixture groups
        tracks = [
            ShowTrack(name="Front Wash", track_type="fixture", order=0),
            ShowTrack(name="Back Light", track_type="fixture", order=1),
            ShowTrack(name="Moving Heads", track_type="fixture", order=2),
            ShowTrack(name="Effects", track_type="effect", order=3),
        ]

        # Generate cues based on mood changes
        cues = await self._generate_mood_cues(
            mood_data, duration, fixture_count
        )

        # Add beat-synced cues
        beat_cues = await self._generate_beat_cues(
            beat_data, mood_data, duration, fixture_count
        )
        cues.extend(beat_cues)

        # Sort by start time
        cues.sort(key=lambda c: c.start_time)

        show.tracks = tracks
        show.cues = cues

        return show

    async def _generate_mood_cues(
        self,
        mood_data: List[MoodResponse],
        duration: float,
        fixture_count: int
    ) -> List[ShowCue]:
        """Generate cues based on mood changes."""
        cues = []

        if not mood_data:
            return cues

        # Sample mood at regular intervals
        interval = duration / len(mood_data)

        for i, mood in enumerate(mood_data):
            start_time = i * interval

            # Get color for this mood
            color_hsv = self.color_mapper.get_color_for_mood(
                mood.valence, mood.arousal
            )
            r, g, b = self.color_mapper.hsv_to_rgb(
                color_hsv['hue'],
                color_hsv['saturation'],
                color_hsv['value']
            )

            # Intensity based on arousal
            intensity = int(128 + mood.arousal * 127)

            # Create color cue
            dmx_values = {}
            for fixture in range(fixture_count):
                base_addr = fixture * 10 + 1  # Assuming 10 channels per fixture
                dmx_values[str(base_addr)] = intensity  # Dimmer
                dmx_values[str(base_addr + 1)] = r  # Red
                dmx_values[str(base_addr + 2)] = g  # Green
                dmx_values[str(base_addr + 3)] = b  # Blue

            cue = ShowCue(
                name=f"Mood - {mood.primary_emotion}",
                cue_type=CueType.FADE,
                start_time=start_time,
                duration=interval,
                fade_in=min(interval * 0.3, 1.0),
                fade_out=0.0,
                dmx_values=dmx_values,
                valence=mood.valence,
                arousal=mood.arousal,
            )
            cues.append(cue)

        return cues

    async def _generate_beat_cues(
        self,
        beat_data: List[BeatResponse],
        mood_data: List[MoodResponse],
        duration: float,
        fixture_count: int
    ) -> List[ShowCue]:
        """Generate cues synced to beats."""
        cues = []

        if not beat_data:
            return cues

        # Get average arousal for effect intensity
        avg_arousal = sum(m.arousal for m in mood_data) / len(mood_data) if mood_data else 0.0

        # Only add beat cues for high arousal sections
        if avg_arousal < 0.3:
            return cues

        interval = duration / len(beat_data)

        for i, beat in enumerate(beat_data):
            if not beat.is_beat:
                continue

            start_time = i * interval

            # Strobe on downbeats
            if beat.is_downbeat:
                cue = ShowCue(
                    name="Downbeat Flash",
                    cue_type=CueType.EFFECT,
                    start_time=start_time,
                    duration=0.1,
                    fade_in=0.0,
                    fade_out=0.05,
                    effect_type="flash",
                    effect_params={"intensity": 1.0},
                    audio_reactive=True,
                    audio_trigger="downbeat",
                )
                cues.append(cue)

            # Bump on regular beats (for high arousal)
            elif avg_arousal > 0.6:
                cue = ShowCue(
                    name="Beat Bump",
                    cue_type=CueType.EFFECT,
                    start_time=start_time,
                    duration=0.05,
                    fade_in=0.0,
                    fade_out=0.03,
                    effect_type="bump",
                    effect_params={"intensity": 0.5},
                    audio_reactive=True,
                    audio_trigger="beat",
                )
                cues.append(cue)

        return cues

    async def generate_realtime_cue(
        self,
        mood: MoodResponse,
        beat: BeatResponse,
        frequency: Dict[str, float],
        fixture_ids: List[int],
    ) -> Dict[int, Dict[str, int]]:
        """
        Generate real-time DMX values for fixtures.

        Args:
            mood: Current mood analysis
            beat: Current beat detection
            frequency: Current frequency band energies
            fixture_ids: List of fixture IDs to control

        Returns:
            Dictionary mapping fixture ID to channel values
        """
        # Get base color from mood
        color_hsv = self.color_mapper.get_color_for_mood(
            mood.valence, mood.arousal
        )
        r, g, b = self.color_mapper.hsv_to_rgb(
            color_hsv['hue'],
            color_hsv['saturation'],
            color_hsv['value']
        )

        # Intensity from arousal and beat
        base_intensity = int(128 + mood.arousal * 100)
        if beat.is_beat:
            base_intensity = min(255, base_intensity + 50)
        if beat.is_downbeat:
            base_intensity = 255

        result = {}

        for i, fixture_id in enumerate(fixture_ids):
            # Slight color variation per fixture
            hue_offset = (i * 0.05) % 1.0
            adjusted_hue = (color_hsv['hue'] + hue_offset) % 1.0
            fr, fg, fb = self.color_mapper.hsv_to_rgb(
                adjusted_hue,
                color_hsv['saturation'],
                color_hsv['value']
            )

            # Intensity variation based on frequency bands
            if i < len(frequency):
                band_names = list(frequency.keys())
                band_energy = frequency.get(band_names[i % len(band_names)], 0.5)
                intensity = int(base_intensity * (0.5 + band_energy * 0.5))
            else:
                intensity = base_intensity

            result[fixture_id] = {
                'dimmer': intensity,
                'red': fr,
                'green': fg,
                'blue': fb,
            }

        return result


# Import math for movement patterns
import math
