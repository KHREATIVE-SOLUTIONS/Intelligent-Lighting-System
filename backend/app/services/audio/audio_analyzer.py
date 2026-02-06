"""
Audio Analyzer Service
======================

Real-time audio analysis including beat detection, mood classification,
and frequency analysis.
"""

import asyncio
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from collections import deque
import scipy.signal as signal

from app.core.config import settings
from app.schemas.audio import (
    AudioStreamConfig, AudioAnalysisResponse,
    BeatResponse, MoodResponse, FrequencyResponse, FrequencyBand
)


class AudioAnalyzer:
    """Real-time audio analyzer with beat detection, mood classification, and frequency analysis."""

    # Frequency band definitions (Hz)
    FREQUENCY_BANDS = {
        "sub_bass": (20, 60),
        "bass": (60, 250),
        "low_mid": (250, 500),
        "mid": (500, 2000),
        "high_mid": (2000, 4000),
        "high": (4000, 8000),
        "brilliance": (8000, 20000),
    }

    def __init__(self, model_manager=None):
        """Initialize the audio analyzer."""
        self.model_manager = model_manager
        self.is_running = False

        # Audio configuration
        self.sample_rate = settings.AUDIO_SAMPLE_RATE
        self.chunk_size = settings.AUDIO_CHUNK_SIZE
        self.hop_length = settings.AUDIO_HOP_LENGTH

        # Analysis state
        self.buffer_size = self.sample_rate * 4  # 4 seconds buffer
        self.audio_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.buffer_index = 0

        # Beat detection state
        self.beat_history = deque(maxlen=100)
        self.onset_history = deque(maxlen=50)
        self.current_bpm = 120.0
        self.beat_confidence = 0.0
        self.last_beat_time = 0.0
        self.beat_phase = 0.0
        self.beat_position = 1

        # Mood state
        self.current_valence = 0.0
        self.current_arousal = 0.0
        self.mood_history = deque(maxlen=30)

        # Frequency state
        self.current_bands = {name: 0.0 for name in self.FREQUENCY_BANDS}
        self.spectral_centroid = 0.0
        self.spectral_rolloff = 0.0
        self.spectral_flux = 0.0
        self.previous_spectrum = None

        # Energy state
        self.rms_energy = 0.0
        self.peak_amplitude = 0.0

        # Latency tracking
        self.latency_ms = 0.0

    async def start(self):
        """Start the audio analyzer."""
        self.is_running = True

    async def stop(self):
        """Stop the audio analyzer."""
        self.is_running = False

    async def update_config(self, config: AudioStreamConfig):
        """Update analyzer configuration."""
        self.sample_rate = config.sample_rate
        self.chunk_size = config.chunk_size

    async def process_chunk(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Process an audio chunk and return analysis results.

        Args:
            audio_data: Audio samples as float32 array (-1.0 to 1.0)

        Returns:
            Dictionary containing beat, mood, and frequency analysis
        """
        start_time = datetime.utcnow()

        # Update buffer
        self._update_buffer(audio_data)

        # Run analyses
        beat_result = await self._analyze_beat(audio_data)
        frequency_result = self._analyze_frequency(audio_data)
        mood_result = await self._analyze_mood(audio_data)

        # Calculate latency
        end_time = datetime.utcnow()
        self.latency_ms = (end_time - start_time).total_seconds() * 1000

        return {
            "beat": beat_result,
            "mood": mood_result,
            "frequency": frequency_result,
            "latency_ms": self.latency_ms,
        }

    def _update_buffer(self, audio_data: np.ndarray):
        """Update the circular audio buffer."""
        # Truncate oversized chunks to fit buffer (BUG-003 fix)
        if len(audio_data) > self.buffer_size:
            audio_data = audio_data[-self.buffer_size:]

        chunk_len = len(audio_data)

        if self.buffer_index + chunk_len <= self.buffer_size:
            self.audio_buffer[self.buffer_index:self.buffer_index + chunk_len] = audio_data
            self.buffer_index += chunk_len
        else:
            # Wrap around
            remaining = self.buffer_size - self.buffer_index
            self.audio_buffer[self.buffer_index:] = audio_data[:remaining]
            overflow = chunk_len - remaining
            self.audio_buffer[:overflow] = audio_data[remaining:]
            self.buffer_index = overflow

    async def _analyze_beat(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Detect beats and estimate BPM.

        Uses onset detection and autocorrelation for BPM estimation.
        """
        # Calculate onset strength using spectral flux
        spectrum = np.abs(np.fft.rfft(audio_data))

        if self.previous_spectrum is not None:
            # Spectral flux (only positive differences)
            flux = np.sum(np.maximum(0, spectrum - self.previous_spectrum))
            self.onset_history.append(flux)

            # Detect onset (beat) with minimum interval guard
            is_beat = False
            if len(self.onset_history) > 3:
                mean_flux = np.mean(list(self.onset_history))
                threshold = mean_flux * 1.5
                is_beat = flux > threshold and (
                    datetime.utcnow().timestamp() - self.last_beat_time > 0.2
                )

                if is_beat:
                    current_time = datetime.utcnow().timestamp()
                    if self.last_beat_time > 0:
                        interval = current_time - self.last_beat_time
                        if 0.25 < interval < 2.0:  # 30-240 BPM range
                            self.beat_history.append(interval)
                    self.last_beat_time = current_time
                    self.beat_position = (self.beat_position % 4) + 1
        else:
            is_beat = False

        self.previous_spectrum = spectrum

        # Estimate BPM from beat history
        if len(self.beat_history) > 5:
            intervals = np.array(list(self.beat_history))
            # Remove outliers
            median_interval = np.median(intervals)
            valid_intervals = intervals[
                np.abs(intervals - median_interval) < median_interval * 0.3
            ]
            if len(valid_intervals) > 0:
                avg_interval = np.mean(valid_intervals)
                self.current_bpm = 60.0 / avg_interval
                self.beat_confidence = min(1.0, len(valid_intervals) / 10)

        # Calculate phase within beat
        if self.current_bpm > 0:
            beat_duration = 60.0 / self.current_bpm
            time_since_beat = datetime.utcnow().timestamp() - self.last_beat_time
            self.beat_phase = (time_since_beat / beat_duration) % 1.0

        return {
            "bpm": round(self.current_bpm, 1),
            "beat_confidence": round(self.beat_confidence, 2),
            "is_beat": is_beat,
            "is_downbeat": is_beat and self.beat_position == 1,
            "beat_position": self.beat_position,
            "time_signature": "4/4",
            "phase": round(self.beat_phase, 3),
        }

    async def _analyze_mood(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Classify mood using valence-arousal model.

        Uses spectral features to estimate emotional content.
        """
        # Use ML model if available
        if self.model_manager and self.model_manager.has_model('hubert'):
            result = await self.model_manager.classify_mood(audio_data)
            self.current_valence = result['valence']
            self.current_arousal = result['arousal']
        else:
            # Fallback: Estimate from spectral features
            spectrum = np.abs(np.fft.rfft(audio_data))
            freqs = np.fft.rfftfreq(len(audio_data), 1.0 / self.sample_rate)

            # Spectral centroid correlates with brightness (arousal)
            if np.sum(spectrum) > 0:
                spectral_centroid = np.sum(freqs * spectrum) / np.sum(spectrum)
                # Normalize to 0-1 range (assuming 0-8000 Hz range)
                self.current_arousal = np.clip(spectral_centroid / 4000 - 0.5, -1, 1)

            # High/low frequency ratio correlates with valence (positive/negative)
            low_energy = np.sum(spectrum[freqs < 500])
            high_energy = np.sum(spectrum[freqs > 2000])
            total_energy = np.sum(spectrum) + 1e-10

            ratio = (high_energy - low_energy) / total_energy
            self.current_valence = np.clip(ratio * 2, -1, 1)

        self.mood_history.append((self.current_valence, self.current_arousal))

        # Smooth values
        if len(self.mood_history) > 1:
            valences = [m[0] for m in self.mood_history]
            arousals = [m[1] for m in self.mood_history]
            smoothed_valence = np.mean(valences[-5:])
            smoothed_arousal = np.mean(arousals[-5:])
        else:
            smoothed_valence = self.current_valence
            smoothed_arousal = self.current_arousal

        # Determine primary emotion
        primary_emotion = self._get_primary_emotion(smoothed_valence, smoothed_arousal)

        return {
            "valence": round(smoothed_valence, 3),
            "arousal": round(smoothed_arousal, 3),
            "confidence": 0.7,  # Placeholder
            "primary_emotion": primary_emotion,
            "emotion_scores": self._get_emotion_scores(smoothed_valence, smoothed_arousal),
        }

    def _get_primary_emotion(self, valence: float, arousal: float) -> str:
        """Map valence-arousal to primary emotion."""
        if arousal > 0.3:
            if valence > 0.3:
                return "excited"
            elif valence < -0.3:
                return "angry"
            else:
                return "energetic"
        elif arousal < -0.3:
            if valence > 0.3:
                return "relaxed"
            elif valence < -0.3:
                return "sad"
            else:
                return "calm"
        else:
            if valence > 0.3:
                return "happy"
            elif valence < -0.3:
                return "melancholic"
            else:
                return "neutral"

    def _get_emotion_scores(self, valence: float, arousal: float) -> Dict[str, float]:
        """Calculate scores for multiple emotions."""
        emotions = {
            "happy": (0.7, 0.3),
            "excited": (0.6, 0.8),
            "energetic": (0.0, 0.8),
            "angry": (-0.6, 0.7),
            "sad": (-0.6, -0.4),
            "calm": (0.3, -0.6),
            "relaxed": (0.5, -0.5),
            "melancholic": (-0.3, -0.2),
            "neutral": (0.0, 0.0),
        }

        scores = {}
        for emotion, (ev, ea) in emotions.items():
            distance = np.sqrt((valence - ev) ** 2 + (arousal - ea) ** 2)
            scores[emotion] = round(max(0, 1 - distance / 2), 3)

        return scores

    def _analyze_frequency(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Analyze frequency content of audio."""
        # Compute FFT
        n_fft = min(len(audio_data), 4096)
        spectrum = np.abs(np.fft.rfft(audio_data, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        # Calculate energy in each frequency band
        bands = []
        total_energy = np.sum(spectrum ** 2) + 1e-10

        for name, (low, high) in self.FREQUENCY_BANDS.items():
            mask = (freqs >= low) & (freqs < high)
            band_energy = np.sum(spectrum[mask] ** 2)
            normalized_energy = band_energy / total_energy

            # Find peak frequency in band
            if np.any(mask) and np.sum(spectrum[mask]) > 0:
                band_freqs = freqs[mask]
                band_spectrum = spectrum[mask]
                peak_idx = np.argmax(band_spectrum)
                peak_freq = band_freqs[peak_idx]
            else:
                peak_freq = (low + high) / 2

            self.current_bands[name] = normalized_energy
            bands.append(FrequencyBand(
                name=name,
                frequency_range=[low, high],
                energy=round(normalized_energy, 4),
                peak_frequency=round(peak_freq, 1)
            ))

        # Spectral centroid
        if np.sum(spectrum) > 0:
            self.spectral_centroid = np.sum(freqs * spectrum) / np.sum(spectrum)

        # Spectral rolloff (95% of energy)
        cumulative_energy = np.cumsum(spectrum ** 2)
        rolloff_idx = np.searchsorted(cumulative_energy, 0.95 * cumulative_energy[-1])
        self.spectral_rolloff = freqs[min(rolloff_idx, len(freqs) - 1)]

        # Spectral flux - use the same previous_spectrum as beat detection (BUG-012 fix)
        # Note: previous_spectrum is updated in _analyze_beat which runs first
        if self.previous_spectrum is not None and len(self.previous_spectrum) == len(spectrum):
            self.spectral_flux = np.sum(np.maximum(0, spectrum - self.previous_spectrum))
        else:
            self.spectral_flux = 0.0

        # RMS energy
        self.rms_energy = np.sqrt(np.mean(audio_data ** 2))
        self.peak_amplitude = np.max(np.abs(audio_data))

        return {
            "bands": [b.model_dump() for b in bands],
            "spectral_centroid": round(self.spectral_centroid, 1),
            "spectral_rolloff": round(self.spectral_rolloff, 1),
            "spectral_flux": round(self.spectral_flux, 6),
            "rms_energy": round(self.rms_energy, 4),
            "peak_amplitude": round(self.peak_amplitude, 4),
        }

    def get_current_analysis(self) -> Optional[AudioAnalysisResponse]:
        """Get the most recent complete analysis."""
        return AudioAnalysisResponse(
            timestamp=datetime.utcnow(),
            beat=BeatResponse(
                bpm=self.current_bpm,
                beat_confidence=self.beat_confidence,
                is_beat=False,
                is_downbeat=False,
                beat_position=self.beat_position,
                time_signature="4/4",
                phase=self.beat_phase,
            ),
            mood=MoodResponse(
                valence=self.current_valence,
                arousal=self.current_arousal,
                confidence=0.7,
                primary_emotion=self._get_primary_emotion(
                    self.current_valence, self.current_arousal
                ),
                emotion_scores=self._get_emotion_scores(
                    self.current_valence, self.current_arousal
                ),
            ),
            frequency=FrequencyResponse(
                bands=[
                    FrequencyBand(
                        name=name,
                        frequency_range=list(self.FREQUENCY_BANDS[name]),
                        energy=energy,
                    )
                    for name, energy in self.current_bands.items()
                ],
                spectral_centroid=self.spectral_centroid,
                spectral_rolloff=self.spectral_rolloff,
                spectral_flux=self.spectral_flux,
                rms_energy=self.rms_energy,
                peak_amplitude=self.peak_amplitude,
            ),
        )

    def get_beat_info(self) -> BeatResponse:
        """Get current beat information."""
        return BeatResponse(
            bpm=self.current_bpm,
            beat_confidence=self.beat_confidence,
            is_beat=False,
            is_downbeat=False,
            beat_position=self.beat_position,
            time_signature="4/4",
            phase=self.beat_phase,
        )

    def get_mood_info(self) -> MoodResponse:
        """Get current mood information."""
        return MoodResponse(
            valence=self.current_valence,
            arousal=self.current_arousal,
            confidence=0.7,
            primary_emotion=self._get_primary_emotion(
                self.current_valence, self.current_arousal
            ),
            emotion_scores=self._get_emotion_scores(
                self.current_valence, self.current_arousal
            ),
        )

    def get_frequency_info(self) -> FrequencyResponse:
        """Get current frequency information."""
        return FrequencyResponse(
            bands=[
                FrequencyBand(
                    name=name,
                    frequency_range=list(self.FREQUENCY_BANDS[name]),
                    energy=energy,
                )
                for name, energy in self.current_bands.items()
            ],
            spectral_centroid=self.spectral_centroid,
            spectral_rolloff=self.spectral_rolloff,
            spectral_flux=self.spectral_flux,
            rms_energy=self.rms_energy,
            peak_amplitude=self.peak_amplitude,
        )

    def get_current_fingerprint(self) -> Optional[bytes]:
        """Generate audio fingerprint from current buffer."""
        # Simplified fingerprint using spectral peaks
        # Real implementation would use Chromaprint or similar
        spectrum = np.abs(np.fft.rfft(self.audio_buffer))
        # Find top peaks
        peak_indices = signal.find_peaks(spectrum, height=np.max(spectrum) * 0.1)[0]
        # Create simple hash from peak positions
        if len(peak_indices) > 0:
            fingerprint = peak_indices[:100].tobytes()
            return fingerprint
        return None
