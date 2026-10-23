"""
Audio Analyzer Service
======================

Real-time audio analysis including beat detection, mood classification,
frequency analysis, and ML pipeline integration (MERT, structure, genre).
"""

import asyncio
import math
import numpy as np
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from collections import deque
import scipy.signal as signal

from app.core.config import settings
from app.services.audio.tempo_tracker import TempoTracker
from app.services.audio.track_change import TrackChangeDetector
from app.schemas.audio import (
    AudioStreamConfig, AudioAnalysisResponse,
    BeatResponse, MoodResponse, FrequencyResponse, FrequencyBand
)

logger = logging.getLogger(__name__)


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

    # Loudness normalisation. The reference is seeded from the audio itself, so
    # over most of the range scaling the input scales the reference by the same
    # factor and the normalised value is unchanged. That invariance is close but
    # NOT exact: the gate is computed from the instantaneous chunk RMS against
    # absolute constants, and the reference only adapts while the envelope is
    # above GATE_HIGH, so on quiet material the ends of the gain sweep differ
    # (sparse track, analyser-level max |delta| vs 0 dB: 0.13 at -6 dB, 0.28 at
    # -12 dB). GATE and REF_FLOOR are the absolute levels in the stage and exist
    # so that a noise floor stays dark instead of being normalised up to mid
    # scale, which is what an AGC does to any steady input by construction.
    LOUDNESS_ENV_RELEASE_S = 0.18
    LOUDNESS_ACQUIRE_TAU_S = 0.5
    LOUDNESS_TAU_UP_S = 60.0
    LOUDNESS_TAU_DOWN_S = 30.0
    LOUDNESS_RANGE_DB = 30.0
    LOUDNESS_TARGET = 0.5
    LOUDNESS_GATE_LOW = 0.0002
    LOUDNESS_GATE_HIGH = 0.0008
    # -45 dBFS. An AGC normalises *any* steady input to mid scale, so this floor
    # is the only thing deciding what counts as programme at all: below it the
    # reference stops following and the output falls away instead of amplifying
    # a noise floor up to 0.5. It sits just under the quietest real material in
    # the harness (the sparse track at -12 dB, -45.7 dBFS) so the gain sweep is
    # not clamped, and 11.5 dB above the old value, which put -60 dBFS room tone
    # at 0.387 and anything from -55 dBFS up at a permanent 0.502.
    LOUDNESS_REF_FLOOR = 0.0056

    # Beat-detector noise gates. These are NOT the loudness gate and must not be
    # pointed at it: they are the last thing stopping the onset detector from
    # locking onto a room-tone noise floor, and dropping them ~10 dB measurably
    # degrades beat timing on quiet material (sparse track at -12 dB: mean beat
    # error 37.0 -> 83.5 ms, worst 58.5 -> 221.0 ms) while changing nothing at
    # 0 dB, where the median-relative term dominates instead.
    BEAT_RMS_GATE = 0.0025
    BEAT_CLOCK_RMS_GATE = 0.002

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
        self.rms_history = deque(maxlen=64)
        self.bass_history = deque(maxlen=64)
        self.current_bpm = 120.0
        self.beat_confidence = 0.0
        # The tempo a lighting operator would count, from the drums themselves.
        # Supersedes the beat-interval estimate below whenever it is confident.
        self._tempo = TempoTracker(self.sample_rate, hop=self.hop_length)
        # Which record is playing, so a DJ mix is not one six-hour song.
        self._track = TrackChangeDetector(self.sample_rate)
        self.tempo_confidence = 0.0
        self.last_beat_time = 0.0
        self.beat_phase = 0.0
        self.beat_position = 1
        self.current_is_beat = False
        self.current_is_downbeat = False
        self.current_is_bar = False
        self.current_bar_count = 0
        self.bar_phase = 0.0
        self.current_is_phrase = False
        self.current_is_section = False
        self.phrase_count = 0
        self.phrase_length_bars = 8

        # Mood state
        self.current_valence = 0.0
        self.current_arousal = 0.0
        self.mood_history = deque(maxlen=30)

        # Frequency state
        self.current_bands = {name: 0.0 for name in self.FREQUENCY_BANDS}
        self.spectral_centroid = 0.0
        self.spectral_rolloff = 0.0
        self.spectral_flux = 0.0
        self.previous_beat_spectrum = None
        self.previous_flux_spectrum = None
        self.previous_bass_energy = 0.0

        # Energy state
        self.rms_energy = 0.0
        self.peak_amplitude = 0.0
        self.beat_count = 0

        # Loudness normalisation state
        self.rms_envelope = 0.0
        self.normalized_energy = 0.0
        self.loudness_reference = 0.0
        self.loudness_rel_db = -self.LOUDNESS_RANGE_DB
        self._loudness_ref_db = None
        self._loudness_active_s = 0.0

        # Latency tracking
        self.latency_ms = 0.0

        # ML pipeline components (set via set_ml_models)
        self._mert_model = None
        self._structure_analyzer = None
        self._genre_classifier = None

        # ML pipeline state / rate limiting
        self._last_mert_time = 0.0
        self._mert_interval = 0.5          # 2Hz (every 500ms)
        self._last_genre_time = 0.0
        self._genre_interval = 10.0        # Every 10 seconds
        self._last_structure_analysis = None
        self._last_emotion_vector = None
        self._last_emotion_mapping = None
        self._last_genre_result = None

    def set_ml_models(self, mert_model=None, structure_analyzer=None, genre_classifier=None):
        """Set ML model references from model_manager.

        Called during startup after models are loaded.
        """
        self._mert_model = mert_model
        self._structure_analyzer = structure_analyzer
        self._genre_classifier = genre_classifier
        logger.info(
            "ML models wired into audio analyzer: mert=%s, structure=%s, genre=%s",
            mert_model is not None,
            structure_analyzer is not None,
            genre_classifier is not None,
        )

    async def start(self):
        """Start the audio analyzer."""
        self.is_running = True

    async def stop(self):
        """Stop the audio analyzer."""
        self.is_running = False

    async def update_config(self, config: AudioStreamConfig):
        """Update analyzer configuration."""
        self.set_sample_rate(config.sample_rate)
        self.chunk_size = config.chunk_size

    def set_sample_rate(self, sample_rate: int):
        """Follow the capture device's actual rate.

        Every band edge, the spectral centroid and the beat detector's bass
        mask are derived from this value, so a device running at 48000 while
        this still says 44100 puts every edge ~9% high.
        """
        try:
            rate = int(sample_rate)
        except (TypeError, ValueError):
            return
        if rate <= 0 or rate == self.sample_rate:
            return
        self.sample_rate = rate
        self.buffer_size = rate * 4
        self.audio_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.buffer_index = 0
        self.previous_beat_spectrum = None
        self.previous_flux_spectrum = None
        self._tempo.set_sample_rate(rate)
        self._track.set_sample_rate(rate)
        logger.info("Audio analyzer sample rate set to %d Hz", rate)

    def _sanitize_chunk(self, audio_data) -> np.ndarray:
        """A chunk every analysis stage can take.

        Live input is not trusted: a dropout can deliver an empty buffer, a bad
        driver or client can deliver NaN/inf, and an int16 stream can arrive
        unscaled. Any of those used to raise inside the FFT or the result schema
        (taking the audio connection down) or poison the median-based beat
        history for seconds. Empty becomes one chunk of silence.
        """
        data = np.asarray(audio_data, dtype=np.float32).reshape(-1)
        if data.size == 0:
            return np.zeros(max(1, int(self.chunk_size)), dtype=np.float32)
        if not np.all(np.isfinite(data)):
            data = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=-1.0)
        return np.clip(data, -1.0, 1.0)

    async def process_chunk(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Process an audio chunk and return analysis results.

        Args:
            audio_data: Audio samples as float32 array (-1.0 to 1.0)

        Returns:
            Dictionary containing beat, mood, frequency, and ML pipeline analysis
        """
        start_time = datetime.utcnow()

        audio_data = self._sanitize_chunk(audio_data)

        # Update buffer
        self._update_buffer(audio_data)
        self._tempo.push(audio_data)

        # Normalise loudness before anything reads a level-based threshold
        self._update_loudness(audio_data)

        # Run core analyses
        beat_result = await self._analyze_beat(audio_data)
        frequency_result = self._analyze_frequency(audio_data)
        mood_result = await self._analyze_mood(audio_data)

        result = {
            "beat": beat_result,
            "mood": mood_result,
            "frequency": frequency_result,
            "track": self._analyze_track(audio_data),
        }

        # Run ML pipeline models (MERT, structure, genre)
        ml_result = await self._run_ml_pipeline(audio_data, beat_result, frequency_result)
        if ml_result:
            result["ml"] = ml_result

        # Calculate latency
        end_time = datetime.utcnow()
        self.latency_ms = (end_time - start_time).total_seconds() * 1000
        result["latency_ms"] = self.latency_ms

        return result

    def _analyze_track(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Which record is playing: see `TrackChangeDetector`.

        Never raises. A fault here costs the set its track boundaries, which is
        how it behaved before this existed, and must not cost it the analysis.
        """
        detector = self._track
        try:
            trusted = self._tempo_is_trusted()
            detector.push(
                audio_data,
                bpm=self._tempo.bpm if trusted else None,
                tempo_confidence=self._tempo.confidence if trusted else 0.0,
            )
        except Exception:
            detector.changed = False
        return {
            "id": int(detector.track_id),
            "changed": bool(detector.changed),
            "transition": round(float(detector.transition), 3),
        }

    def _update_loudness(self, audio_data: np.ndarray) -> float:
        """Track programme loudness and derive a playback-level-invariant energy.

        A running reference follows the smoothed loudness of the material with
        a growing memory: it converges within the first second of audio, then
        settles to a minute-scale constant so a sustained chorus is not
        normalised back down into a verse. The published value is the current
        envelope expressed relative to that reference, so the same performance
        played 12 dB quieter or 9 dB louder produces the same number.
        """
        try:
            n = int(len(audio_data)) if audio_data is not None else 0
            if n > 0:
                rms = float(np.sqrt(np.mean(np.square(np.asarray(audio_data, dtype=np.float64)))))
            else:
                rms = 0.0
        except Exception:
            n, rms = 0, 0.0
        if not math.isfinite(rms) or rms < 0.0:
            rms = 0.0

        rate = float(self.sample_rate) if self.sample_rate else 44100.0
        dt = min(1.0, max(1e-4, (n / rate) if rate > 0 else 1e-2))

        if rms > self.rms_envelope:
            self.rms_envelope = rms
        else:
            release = 1.0 - math.exp(-dt / self.LOUDNESS_ENV_RELEASE_S)
            self.rms_envelope += (rms - self.rms_envelope) * release
        if not math.isfinite(self.rms_envelope) or self.rms_envelope < 0.0:
            self.rms_envelope = 0.0
        envelope = self.rms_envelope

        gate_span = self.LOUDNESS_GATE_HIGH - self.LOUDNESS_GATE_LOW
        gate = (rms - self.LOUDNESS_GATE_LOW) / gate_span if gate_span > 0 else 0.0
        gate = min(1.0, max(0.0, gate))

        if envelope > self.LOUDNESS_GATE_HIGH:
            envelope_db = 20.0 * math.log10(envelope)
            if self._loudness_ref_db is None:
                self._loudness_ref_db = envelope_db
            self._loudness_active_s = min(1e6, self._loudness_active_s + dt)
            settled = (
                self.LOUDNESS_TAU_UP_S if envelope_db > self._loudness_ref_db
                else self.LOUDNESS_TAU_DOWN_S
            )
            tau = min(settled, self.LOUDNESS_ACQUIRE_TAU_S + self._loudness_active_s)
            self._loudness_ref_db += (envelope_db - self._loudness_ref_db) * (
                1.0 - math.exp(-dt / max(1e-3, tau))
            )

        if self._loudness_ref_db is None or gate <= 0.0 or envelope <= 0.0:
            self.normalized_energy = 0.0
            self.loudness_rel_db = -self.LOUDNESS_RANGE_DB
            return 0.0

        reference_db = max(
            self._loudness_ref_db, 20.0 * math.log10(self.LOUDNESS_REF_FLOOR)
        )
        self.loudness_reference = 10.0 ** (reference_db / 20.0)
        rel_db = 20.0 * math.log10(max(envelope, 1e-12)) - reference_db
        self.loudness_rel_db = max(-120.0, min(60.0, rel_db))
        level = self.LOUDNESS_TARGET + rel_db / self.LOUDNESS_RANGE_DB
        self.normalized_energy = min(1.0, max(0.0, level)) * gate
        return self.normalized_energy

    async def _run_ml_pipeline(
        self, audio_data: np.ndarray, beat_result: Dict, frequency_result: Dict
    ) -> Optional[Dict[str, Any]]:
        """Run MERT, structure analyzer, and genre classifier.

        Each model has its own rate limit:
        - MERT: 2Hz (every 500ms)
        - Structure: on every downbeat
        - Genre: every 10 seconds
        """
        current_time = time.time()
        ml_output: Dict[str, Any] = {}

        # --- MERT emotion recognition (2Hz) ---
        if self._mert_model is not None:
            self._mert_model.feed_audio(audio_data, self.sample_rate)
            if current_time - self._last_mert_time >= self._mert_interval:
                self._last_mert_time = current_time
                try:
                    emotion = await self._mert_model.get_emotion()
                    self._last_emotion_vector = emotion
                    self._last_emotion_mapping = self._mert_model.map_to_lighting(emotion)
                except Exception as e:
                    logger.warning("MERT inference error: %s", e)

        if self._last_emotion_vector is not None:
            ev = self._last_emotion_vector
            ml_output["emotion_vector"] = {
                "valence": ev.valence,
                "arousal": ev.arousal,
                "dominance": ev.dominance,
                "tension": ev.tension,
                "energy_trajectory": ev.energy_trajectory,
                "groove": ev.groove,
                "darkness": ev.darkness,
                "confidence": ev.confidence,
            }
        if self._last_emotion_mapping is not None:
            em = self._last_emotion_mapping
            ml_output["emotion_mapping"] = {
                "color_temp_k": em.color_temp_k,
                "base_intensity": em.base_intensity,
                "movement_speed": em.movement_speed,
                "strobe_probability": em.strobe_probability,
                "chase_complexity": em.chase_complexity,
                "color_saturation": em.color_saturation,
                "palette_warmth": em.palette_warmth,
                "coverage": em.coverage,
                "pulse_depth": em.pulse_depth,
            }

        # --- Music structure analyzer (on downbeats) ---
        if self._structure_analyzer is not None:
            is_beat = beat_result.get("is_beat", False)
            is_downbeat = beat_result.get("is_downbeat", False)
            bpm = beat_result.get("bpm", 120.0)
            normalized_energy = frequency_result.get("normalized_energy", 0.0)
            spectral_flux = frequency_result.get("spectral_flux", 0.0)
            spectral_centroid = frequency_result.get("spectral_centroid", 0.0)

            bands = {}
            for b in frequency_result.get("bands", []):
                bands[b["name"]] = b["energy"]
            bass_energy = bands.get("bass", 0) + bands.get("sub_bass", 0)

            try:
                analysis = self._structure_analyzer.update_beat(
                    is_beat=is_beat,
                    is_downbeat=is_downbeat,
                    bpm=bpm,
                    energy=min(1.0, max(0.0, float(normalized_energy))),
                    bass=min(1.0, bass_energy),
                    spectral_flux=spectral_flux,
                    spectral_centroid=spectral_centroid,
                )
                self._last_structure_analysis = analysis
            except Exception as e:
                logger.warning("Structure analysis error: %s", e)

        if self._last_structure_analysis is not None:
            sa = self._last_structure_analysis
            ml_output["structure"] = {
                "section": sa.current_section.section_type.value,
                "section_confidence": sa.current_section.confidence,
                "section_progress": sa.current_section.progress,
                "bars_elapsed": sa.current_section.bars_elapsed,
                "bars_remaining": sa.current_section.estimated_bars_remaining,
                "phrase_position": sa.current_section.phrase_position,
                "phrase_length": sa.current_section.phrase_length,
                "is_section_boundary": sa.current_section.is_section_boundary,
                "transition": {
                    "predicted_next": sa.transition.predicted_next_section.value,
                    "bars_until": sa.transition.bars_until_transition,
                    "confidence": sa.transition.transition_confidence,
                    "is_buildup": sa.transition.is_buildup,
                    "buildup_progress": sa.transition.buildup_progress,
                    "type": sa.transition.transition_type,
                },
                "bar_number": sa.bar_number,
                "beat_in_bar": sa.beat_in_bar,
            }

        # --- Genre classifier (every 10 seconds) ---
        if self._genre_classifier is not None:
            if current_time - self._last_genre_time >= self._genre_interval:
                self._last_genre_time = current_time
                try:
                    genre_result = await self._genre_classifier.classify(
                        self.audio_buffer, self.sample_rate
                    )
                    self._last_genre_result = genre_result
                except Exception as e:
                    logger.warning("Genre classification error: %s", e)

        if self._last_genre_result is not None:
            gr = self._last_genre_result
            ml_output["genre"] = {
                "top_level": gr.top_level,
                "genre": gr.genre,
                "genre_confidence": gr.genre_confidence,
                "subgenre": gr.subgenre,
                "genre_scores": gr.genre_scores,
            }

        return ml_output if ml_output else None

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
        # Calculate onset strength using beat-detection spectrum deltas
        spectrum = np.abs(np.fft.rfft(audio_data))
        frame_rms = float(np.sqrt(np.mean(audio_data ** 2)))
        self.rms_history.append(frame_rms)
        current_time = datetime.utcnow().timestamp()
        is_beat = False

        # Bass-domain detector for kick-heavy material
        freqs = np.fft.rfftfreq(len(audio_data), d=1.0 / self.sample_rate)
        bass_mask = (freqs >= 35) & (freqs <= 220)
        bass_energy = float(np.mean(spectrum[bass_mask])) if np.any(bass_mask) else 0.0
        self.bass_history.append(bass_energy)

        if self.previous_beat_spectrum is not None and len(self.previous_beat_spectrum) == len(spectrum):
            # Normalized positive spectral change for onset detection
            delta = np.maximum(0, spectrum - self.previous_beat_spectrum)
            flux = float(np.sum(delta) / (np.sum(self.previous_beat_spectrum) + 1e-8))
            self.onset_history.append(flux)

            # Adaptive onset detection: combine flux and RMS rise.
            if len(self.onset_history) >= 8 and len(self.rms_history) >= 8:
                flux_hist = np.array(self.onset_history, dtype=np.float32)
                rms_hist = np.array(self.rms_history, dtype=np.float32)

                median_flux = float(np.median(flux_hist))
                mad_flux = float(np.median(np.abs(flux_hist - median_flux))) + 1e-9
                median_rms = float(np.median(rms_hist))
                mad_rms = float(np.median(np.abs(rms_hist - median_rms))) + 1e-9

                flux_z = (flux - median_flux) / (2.0 * mad_flux)
                rms_z = (frame_rms - median_rms) / (2.5 * mad_rms)
                onset_score = max(0.0, float(flux_z)) + max(0.0, float(rms_z))

                bass_peak = False
                if len(self.bass_history) >= 8:
                    bass_hist = np.array(self.bass_history, dtype=np.float32)
                    bass_med = float(np.median(bass_hist))
                    bass_mad = float(np.median(np.abs(bass_hist - bass_med))) + 1e-9
                    bass_rise = bass_energy - self.previous_bass_energy
                    bass_peak = (
                        bass_energy > (bass_med + 2.2 * bass_mad)
                        and bass_rise > max(1e-6, 0.8 * bass_mad)
                    )

                if len(self.beat_history) >= 3:
                    median_interval = float(np.median(np.array(self.beat_history, dtype=np.float32)))
                else:
                    median_interval = 60.0 / max(60.0, float(self.current_bpm))
                min_beat_interval = max(0.22, median_interval * 0.75)
                is_beat = (
                    (onset_score > 1.0 or bass_peak)
                    and frame_rms > max(self.BEAT_RMS_GATE, median_rms * 0.9)
                    and (current_time - self.last_beat_time > min_beat_interval)
                )

                # Track a coarse confidence value for UI/logic gates.
                self.beat_confidence = float(np.clip(onset_score / 3.0, 0.0, 1.0))

        self.previous_beat_spectrum = spectrum
        self.previous_bass_energy = bass_energy

        self.current_is_bar = False
        self.current_is_phrase = False
        self.current_is_section = False

        if is_beat:
            if self.last_beat_time > 0:
                interval = current_time - self.last_beat_time
                if 0.25 < interval < 2.0:  # 30-240 BPM range
                    self.beat_history.append(interval)
            self.last_beat_time = current_time
            self.beat_position = (self.beat_position % 4) + 1
            self.beat_count += 1
            self.current_is_bar = self.beat_position == 1
            if self.current_is_bar:
                self.current_bar_count += 1
                bars_per_phrase = max(1, int(self.phrase_length_bars))
                self.current_is_phrase = (self.current_bar_count - 1) % bars_per_phrase == 0
                # Slowest hierarchy: section/look family cadence every 2 phrases (16 bars by default)
                section_bars = max(1, bars_per_phrase * 2)
                self.current_is_section = (self.current_bar_count - 1) % section_bars == 0
                if self.current_is_phrase:
                    self.phrase_count += 1

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
                self.beat_confidence = max(self.beat_confidence, min(1.0, len(valid_intervals) / 10))

        self.tempo_confidence = float(self._tempo.confidence) if self._tempo_is_trusted() else 0.0

        # Fallback beat clock: keep beat-reactive systems alive when onset misses.
        if (
            not is_beat
            and frame_rms > self.BEAT_CLOCK_RMS_GATE
            and self.current_bpm > 0
            and self.beat_confidence > 0.15
        ):
            beat_duration = 60.0 / self.current_bpm
            if self.last_beat_time > 0 and (current_time - self.last_beat_time >= beat_duration):
                is_beat = True
                self.last_beat_time = current_time
                self.beat_position = (self.beat_position % 4) + 1
                self.beat_count += 1
                self.current_is_bar = self.beat_position == 1
                if self.current_is_bar:
                    self.current_bar_count += 1
                    bars_per_phrase = max(1, int(self.phrase_length_bars))
                    self.current_is_phrase = (self.current_bar_count - 1) % bars_per_phrase == 0
                    section_bars = max(1, bars_per_phrase * 2)
                    self.current_is_section = (self.current_bar_count - 1) % section_bars == 0
                    if self.current_is_phrase:
                        self.phrase_count += 1

        # Calculate phase within beat
        if self.current_bpm > 0:
            beat_duration = 60.0 / self.current_bpm
            time_since_beat = current_time - self.last_beat_time
            self.beat_phase = (time_since_beat / beat_duration) % 1.0

        self.current_is_beat = bool(is_beat)
        self.current_is_downbeat = bool(is_beat and self.beat_position == 1)
        self.current_is_bar = bool(self.current_is_bar)
        self.bar_phase = ((max(self.beat_position - 1, 0) + self.beat_phase) / 4.0) % 1.0

        return {
            "bpm": round(self.tempo_bpm, 1),
            "beat_confidence": round(self.beat_confidence, 2),
            "tempo_confidence": round(self.tempo_confidence, 2),
            "is_beat": self.current_is_beat,
            "is_downbeat": self.current_is_downbeat,
            "beat_position": self.beat_position,
            "beat_count": self.beat_count,
            "is_bar": self.current_is_bar,
            "bar_count": self.current_bar_count,
            "bar_phase": round(self.bar_phase, 3),
            "is_phrase": bool(self.current_is_phrase),
            "is_section": bool(self.current_is_section),
            "phrase_count": self.phrase_count,
            "phrase_length_bars": self.phrase_length_bars,
            "time_signature": "4/4",
            "phase": round(self.beat_phase, 3),
        }

    @property
    def tempo_bpm(self) -> float:
        """The tempo this analyser publishes.

        The gaps between detected beats (`current_bpm`) cannot tell 87 from
        174, or 174 from its 3/4; the drum-aware tracker can, so it is
        published whenever it is sure. `current_bpm` itself is left alone: it
        paces this detector's own fallback beats, whose count the engine reads
        the bar line from, and that count is its own contract.
        """
        if self._tempo_is_trusted():
            return float(self._tempo.bpm)
        return float(self.current_bpm)

    def _tempo_is_trusted(self) -> bool:
        tracker = self._tempo
        return tracker.bpm is not None and tracker.confidence >= tracker.MIN_CONFIDENCE

    async def _analyze_mood(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Classify mood using valence-arousal model.

        Uses spectral features to estimate emotional content.
        """
        # Use ML model if available (prefer MERT over HuBERT)
        if self.model_manager and (
            self.model_manager.has_model('mert') or self.model_manager.has_model('hubert')
        ):
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

        # Spectral flux on its own history (do not share with beat detector state)
        if self.previous_flux_spectrum is not None and len(self.previous_flux_spectrum) == len(spectrum):
            delta = np.maximum(0, spectrum - self.previous_flux_spectrum)
            mean_delta = float(np.mean(delta))
            mean_prev = float(np.mean(self.previous_flux_spectrum)) + 1e-8
            self.spectral_flux = min(1.0, (mean_delta / mean_prev) * 20.0)
        else:
            self.spectral_flux = 0.0
        self.previous_flux_spectrum = spectrum

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
            "normalized_energy": round(float(self.normalized_energy), 4),
            "loudness_reference": round(float(self.loudness_reference), 6),
            "loudness_rel_db": round(float(self.loudness_rel_db), 2),
        }

    def get_current_analysis(self) -> Optional[AudioAnalysisResponse]:
        """Get the most recent complete analysis."""
        return AudioAnalysisResponse(
            timestamp=datetime.utcnow(),
            beat=BeatResponse(
                bpm=self.tempo_bpm,
                beat_confidence=self.beat_confidence,
                is_beat=self.current_is_beat,
                is_downbeat=self.current_is_downbeat,
                beat_position=self.beat_position,
                bar_count=self.current_bar_count,
                is_bar=self.current_is_bar,
                bar_phase=self.bar_phase,
                phrase_count=self.phrase_count,
                phrase_length_bars=self.phrase_length_bars,
                is_phrase=self.current_is_phrase,
                is_section=self.current_is_section,
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
                normalized_energy=min(1.0, max(0.0, float(self.normalized_energy))),
            ),
        )

    def get_beat_info(self) -> BeatResponse:
        """Get current beat information."""
        return BeatResponse(
            bpm=self.tempo_bpm,
            beat_confidence=self.beat_confidence,
            is_beat=self.current_is_beat,
            is_downbeat=self.current_is_downbeat,
            beat_position=self.beat_position,
            bar_count=self.current_bar_count,
            is_bar=self.current_is_bar,
            bar_phase=self.bar_phase,
            phrase_count=self.phrase_count,
            phrase_length_bars=self.phrase_length_bars,
            is_phrase=self.current_is_phrase,
            is_section=self.current_is_section,
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
            normalized_energy=min(1.0, max(0.0, float(self.normalized_energy))),
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
