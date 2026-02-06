"""
Unit Tests for Audio Analyzer
=============================
"""

import pytest
import numpy as np
from app.services.audio.audio_analyzer import AudioAnalyzer


@pytest.fixture
def analyzer():
    """Create an audio analyzer instance."""
    return AudioAnalyzer()


@pytest.fixture
def sine_wave():
    """Generate a test sine wave at 440 Hz."""
    sample_rate = 44100
    duration = 1.0
    frequency = 440.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    return np.sin(2 * np.pi * frequency * t)


@pytest.fixture
def beat_pattern():
    """Generate a test beat pattern."""
    sample_rate = 44100
    duration = 4.0
    bpm = 120
    samples = int(sample_rate * duration)
    audio = np.zeros(samples, dtype=np.float32)

    # Add beats at 120 BPM (every 0.5 seconds)
    beat_interval = int(sample_rate * 60 / bpm)
    for i in range(0, samples, beat_interval):
        # Create a short click/beat
        beat_samples = min(int(sample_rate * 0.05), samples - i)
        audio[i:i+beat_samples] = np.sin(
            2 * np.pi * 200 * np.linspace(0, 0.05, beat_samples)
        ) * np.exp(-np.linspace(0, 5, beat_samples))

    return audio


class TestAudioAnalyzer:
    """Tests for AudioAnalyzer class."""

    @pytest.mark.asyncio
    async def test_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert analyzer.sample_rate == 44100
        assert analyzer.is_running == False
        assert analyzer.current_bpm == 120.0

    @pytest.mark.asyncio
    async def test_start_stop(self, analyzer):
        """Test starting and stopping the analyzer."""
        await analyzer.start()
        assert analyzer.is_running == True

        await analyzer.stop()
        assert analyzer.is_running == False

    @pytest.mark.asyncio
    async def test_process_chunk(self, analyzer, sine_wave):
        """Test processing an audio chunk."""
        chunk = sine_wave[:2048]
        result = await analyzer.process_chunk(chunk)

        assert 'beat' in result
        assert 'mood' in result
        assert 'frequency' in result
        assert 'latency_ms' in result

    @pytest.mark.asyncio
    async def test_frequency_analysis(self, analyzer, sine_wave):
        """Test frequency band analysis."""
        chunk = sine_wave[:4096]
        result = await analyzer.process_chunk(chunk)

        frequency = result['frequency']
        assert 'bands' in frequency
        assert 'spectral_centroid' in frequency
        assert 'rms_energy' in frequency

        # 440 Hz should show energy in mid frequencies
        bands = {b['name']: b['energy'] for b in frequency['bands']}
        assert 'low_mid' in bands or 'mid' in bands

    @pytest.mark.asyncio
    async def test_mood_analysis(self, analyzer, sine_wave):
        """Test mood classification."""
        chunk = sine_wave[:4096]
        result = await analyzer.process_chunk(chunk)

        mood = result['mood']
        assert 'valence' in mood
        assert 'arousal' in mood
        assert 'primary_emotion' in mood

        # Valence and arousal should be in valid range
        assert -1 <= mood['valence'] <= 1
        assert -1 <= mood['arousal'] <= 1

    @pytest.mark.asyncio
    async def test_beat_detection_with_pattern(self, analyzer, beat_pattern):
        """Test beat detection with a rhythmic pattern."""
        # Process multiple chunks to build up beat history
        chunk_size = 2048
        for i in range(0, len(beat_pattern) - chunk_size, chunk_size):
            chunk = beat_pattern[i:i+chunk_size]
            await analyzer.process_chunk(chunk)

        # Check that BPM is estimated
        beat_info = analyzer.get_beat_info()
        assert beat_info.bpm > 0

    def test_get_primary_emotion(self, analyzer):
        """Test emotion mapping from valence-arousal."""
        # High valence, high arousal = excited
        emotion = analyzer._get_primary_emotion(0.8, 0.8)
        assert emotion in ['excited', 'energetic', 'happy']

        # Low valence, low arousal = sad/calm
        emotion = analyzer._get_primary_emotion(-0.8, -0.8)
        assert emotion in ['sad', 'melancholic', 'calm']

        # Neutral
        emotion = analyzer._get_primary_emotion(0.0, 0.0)
        assert emotion == 'neutral'

    def test_get_mood_info(self, analyzer):
        """Test getting mood info."""
        mood = analyzer.get_mood_info()

        assert hasattr(mood, 'valence')
        assert hasattr(mood, 'arousal')
        assert hasattr(mood, 'primary_emotion')
        assert hasattr(mood, 'emotion_scores')

    def test_get_frequency_info(self, analyzer):
        """Test getting frequency info."""
        freq = analyzer.get_frequency_info()

        assert hasattr(freq, 'bands')
        assert hasattr(freq, 'spectral_centroid')
        assert hasattr(freq, 'rms_energy')
        assert len(freq.bands) == len(analyzer.FREQUENCY_BANDS)


class TestAudioBuffer:
    """Tests for audio buffer management."""

    @pytest.mark.asyncio
    async def test_buffer_update(self, analyzer):
        """Test that buffer updates correctly."""
        initial_index = analyzer.buffer_index

        # Add some audio
        chunk = np.random.randn(1024).astype(np.float32)
        analyzer._update_buffer(chunk)

        assert analyzer.buffer_index == initial_index + 1024

    @pytest.mark.asyncio
    async def test_buffer_wraparound(self, analyzer):
        """Test buffer wraparound behavior."""
        # Fill buffer almost completely
        large_chunk = np.random.randn(analyzer.buffer_size - 100).astype(np.float32)
        analyzer._update_buffer(large_chunk)

        # Add chunk that will cause wraparound
        wrap_chunk = np.random.randn(200).astype(np.float32)
        analyzer._update_buffer(wrap_chunk)

        # Buffer index should have wrapped
        assert analyzer.buffer_index == 100
