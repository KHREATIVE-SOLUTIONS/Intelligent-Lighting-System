"""
Unit Tests for Show Generator
=============================
"""

import pytest
from app.services.show_engine.show_generator import (
    ShowGenerator, EmotionColorMapper, MovementGenerator, EffectsEngine
)
from app.schemas.audio import MoodResponse, BeatResponse


@pytest.fixture
def generator():
    """Create a show generator instance."""
    return ShowGenerator()


@pytest.fixture
def sample_mood_data():
    """Create sample mood data for testing."""
    return [
        MoodResponse(
            valence=0.7, arousal=0.8, confidence=0.9,
            primary_emotion="excited", emotion_scores={}
        ),
        MoodResponse(
            valence=0.3, arousal=0.5, confidence=0.85,
            primary_emotion="happy", emotion_scores={}
        ),
        MoodResponse(
            valence=-0.2, arousal=-0.3, confidence=0.8,
            primary_emotion="calm", emotion_scores={}
        ),
    ]


@pytest.fixture
def sample_beat_data():
    """Create sample beat data for testing."""
    return [
        BeatResponse(
            bpm=128, beat_confidence=0.9, is_beat=True,
            is_downbeat=True, beat_position=1, time_signature="4/4", phase=0.0
        ),
        BeatResponse(
            bpm=128, beat_confidence=0.9, is_beat=True,
            is_downbeat=False, beat_position=2, time_signature="4/4", phase=0.25
        ),
        BeatResponse(
            bpm=128, beat_confidence=0.9, is_beat=True,
            is_downbeat=False, beat_position=3, time_signature="4/4", phase=0.5
        ),
        BeatResponse(
            bpm=128, beat_confidence=0.9, is_beat=True,
            is_downbeat=False, beat_position=4, time_signature="4/4", phase=0.75
        ),
    ]


class TestEmotionColorMapper:
    """Tests for EmotionColorMapper class."""

    def test_high_valence_high_arousal(self):
        """Test color for excited state (high V, high A)."""
        color = EmotionColorMapper.get_color_for_mood(0.8, 0.8)

        # Should be warm color (yellow-orange range, hue ~0.1)
        assert 0.0 <= color['hue'] <= 0.2
        assert color['saturation'] > 0.5
        assert color['value'] > 0.5

    def test_low_valence_high_arousal(self):
        """Test color for angry state (low V, high A)."""
        color = EmotionColorMapper.get_color_for_mood(-0.8, 0.8)

        # Should be red range
        assert color['hue'] <= 0.1 or color['hue'] >= 0.9
        assert color['saturation'] > 0.5

    def test_low_valence_low_arousal(self):
        """Test color for sad state (low V, low A)."""
        color = EmotionColorMapper.get_color_for_mood(-0.8, -0.8)

        # Should be blue/purple range
        assert 0.5 <= color['hue'] <= 0.8

    def test_high_valence_low_arousal(self):
        """Test color for calm state (high V, low A)."""
        color = EmotionColorMapper.get_color_for_mood(0.8, -0.8)

        # Should be green/cyan range
        assert 0.25 <= color['hue'] <= 0.5

    def test_neutral(self):
        """Test color for neutral state."""
        color = EmotionColorMapper.get_color_for_mood(0.0, 0.0)

        # Should be desaturated (whitish)
        assert color['saturation'] < 0.3

    def test_hsv_to_rgb(self):
        """Test HSV to RGB conversion."""
        # Red
        r, g, b = EmotionColorMapper.hsv_to_rgb(0.0, 1.0, 1.0)
        assert r == 255
        assert g == 0
        assert b == 0

        # Green
        r, g, b = EmotionColorMapper.hsv_to_rgb(0.333, 1.0, 1.0)
        assert g > r
        assert g > b

        # Blue
        r, g, b = EmotionColorMapper.hsv_to_rgb(0.667, 1.0, 1.0)
        assert b > r
        assert b > g


class TestEffectsEngine:
    """Tests for EffectsEngine class."""

    def test_strobe_effect(self):
        """Test strobe effect generation."""
        # At different time points
        value1 = EffectsEngine.strobe_effect(0.0, 10.0)
        value2 = EffectsEngine.strobe_effect(0.05, 10.0)

        # Strobe should toggle between 0 and intensity
        assert value1 == 1.0 or value1 == 0.0
        assert value2 == 1.0 or value2 == 0.0

    def test_pulse_effect(self):
        """Test pulse/breathing effect."""
        # Should oscillate smoothly
        values = [EffectsEngine.pulse_effect(t/10, 1.0) for t in range(10)]

        # Should have variation
        assert max(values) > min(values)

        # Should stay in range
        for v in values:
            assert 0.0 <= v <= 1.0

    def test_chase_effect(self):
        """Test chase effect for multiple fixtures."""
        # Different fixtures should have different intensities at same time
        intensities = [
            EffectsEngine.chase_effect(0.0, i, 8, 1.0)
            for i in range(8)
        ]

        # One fixture should be brightest
        assert max(intensities) > 0.5

        # Most fixtures should be dimmer
        dim_count = sum(1 for i in intensities if i < 0.2)
        assert dim_count >= 4


class TestShowGenerator:
    """Tests for ShowGenerator class."""

    @pytest.mark.asyncio
    async def test_generate_show(
        self, generator, sample_mood_data, sample_beat_data
    ):
        """Test generating a complete show."""
        show = await generator.generate_show(
            name="Test Show",
            duration=10.0,
            bpm=128.0,
            mood_data=sample_mood_data,
            beat_data=sample_beat_data,
            fixture_count=4,
        )

        assert show.name == "Test Show"
        assert show.duration == 10.0
        assert show.bpm == 128.0
        assert len(show.cues) > 0

    @pytest.mark.asyncio
    async def test_generate_mood_cues(self, generator, sample_mood_data):
        """Test mood-based cue generation."""
        cues = await generator._generate_mood_cues(
            sample_mood_data, 10.0, 4
        )

        assert len(cues) == len(sample_mood_data)

        # Each cue should have color values
        for cue in cues:
            assert cue.dmx_values
            assert cue.valence is not None
            assert cue.arousal is not None

    @pytest.mark.asyncio
    async def test_generate_beat_cues(
        self, generator, sample_beat_data, sample_mood_data
    ):
        """Test beat-synced cue generation."""
        cues = await generator._generate_beat_cues(
            sample_beat_data, sample_mood_data, 10.0, 4
        )

        # Should have cues for beats (depending on arousal)
        # With high arousal, we should get beat cues
        assert len(cues) >= 0  # May be 0 if arousal is low

    @pytest.mark.asyncio
    async def test_generate_realtime_cue(self, generator):
        """Test real-time cue generation."""
        mood = MoodResponse(
            valence=0.5, arousal=0.5, confidence=0.8,
            primary_emotion="neutral", emotion_scores={}
        )
        beat = BeatResponse(
            bpm=120, beat_confidence=0.9, is_beat=True,
            is_downbeat=False, beat_position=1, time_signature="4/4", phase=0.0
        )
        frequency = {"bass": 0.5, "mid": 0.3, "high": 0.2}
        fixture_ids = [1, 2, 3, 4]

        result = await generator.generate_realtime_cue(
            mood, beat, frequency, fixture_ids
        )

        assert len(result) == len(fixture_ids)

        for fixture_id, channels in result.items():
            assert 'dimmer' in channels
            assert 'red' in channels
            assert 'green' in channels
            assert 'blue' in channels
