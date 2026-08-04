"""
Audio Analysis Schemas
======================

Pydantic schemas for audio analysis operations.
"""

import math
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


def engine_energy(raw_energy: Any, raw_scale: float = 2.0) -> float:
    """Overall energy the effects engine renders from.

    Deliberately the raw, uncompressed level rather than the analyser's
    loudness-normalised one. Three things downstream need the raw signal and
    break on a normalised one, all of them measured:

    * the rig's own zero floor. An AGC maps *any* steady input to mid scale by
      construction, so a paused player presenting a room-tone noise floor
      normalises to ~0.5 and lights the rig with no music playing.
    * the beat clock, which recovers phase from the positive difference of
      block loudness. A loudness-normalised input is already compressed, so the
      onset contrast the comb runs on collapses.
    * the section detector's drop test, which reads a rise in units of the
      running spread. Log-domain compression shrinks every deviation term.

    Playback-level invariance of the *decisions* comes from the detector, which
    measures every feature against its own running centre, not from normalising
    the input. `programme_level` carries the normalised value alongside.

    Called on every audio chunk, so it never raises: anything unusable is zero.
    """
    try:
        value = float(raw_energy) * float(raw_scale)
    except Exception:
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def programme_level(normalized: Any) -> Optional[float]:
    """The analyser's playback-level-invariant loudness, or None if absent.

    0.5 is "as loud as this material's own running reference", and the scale is
    30 dB wide. A source that publishes nothing usable returns None, which every
    consumer has to read as "no opinion" rather than as silence.

    Called on every audio chunk, so it never raises.
    """
    if normalized is None or isinstance(normalized, bool):
        return None
    try:
        value = float(normalized)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    return min(1.0, max(0.0, value))


class AudioStreamConfig(BaseModel):
    """Configuration for audio streaming."""
    sample_rate: int = Field(default=44100, ge=8000, le=96000)
    chunk_size: int = Field(default=2048, ge=256, le=8192)
    channels: int = Field(default=1, ge=1, le=2)
    enable_beat_detection: bool = True
    enable_mood_classification: bool = True
    enable_frequency_analysis: bool = True


class BeatResponse(BaseModel):
    """Real-time beat detection response."""
    bpm: float = Field(..., ge=0, le=300)
    beat_confidence: float = Field(..., ge=0, le=1)
    is_beat: bool = False
    is_downbeat: bool = False
    beat_position: int = Field(default=1, ge=1, le=16)  # Position in bar
    bar_count: int = Field(default=0, ge=0)
    is_bar: bool = False
    bar_phase: float = Field(default=0.0, ge=0, le=1)
    phrase_count: int = Field(default=0, ge=0)
    phrase_length_bars: int = Field(default=8, ge=1, le=32)
    is_phrase: bool = False
    is_section: bool = False
    time_signature: str = "4/4"
    phase: float = Field(default=0.0, ge=0, le=1)  # Phase within beat


class MoodResponse(BaseModel):
    """Real-time mood classification response."""
    valence: float = Field(..., ge=-1, le=1)  # Negative to positive
    arousal: float = Field(..., ge=-1, le=1)  # Calm to energetic
    confidence: float = Field(..., ge=0, le=1)
    primary_emotion: str  # happy, sad, angry, calm, energetic, etc.
    emotion_scores: Dict[str, float] = Field(default_factory=dict)


class FrequencyBand(BaseModel):
    """Individual frequency band data."""
    name: str
    frequency_range: List[float]  # [min_hz, max_hz]
    energy: float = Field(..., ge=0, le=1)
    peak_frequency: Optional[float] = None


class FrequencyResponse(BaseModel):
    """Real-time frequency analysis response."""
    bands: List[FrequencyBand]
    spectral_centroid: float
    spectral_rolloff: float
    spectral_flux: float
    rms_energy: float = Field(..., ge=0, le=1)
    peak_amplitude: float = Field(..., ge=0, le=1)
    # Loudness-normalised counterpart of rms_energy. Published alongside the raw
    # value rather than replacing it: the UI and the training recorder read
    # rms_energy and must keep seeing the raw number.
    normalized_energy: float = Field(0.0, ge=0, le=1)


class AudioAnalysisResponse(BaseModel):
    """Complete audio analysis response."""
    timestamp: datetime
    beat: BeatResponse
    mood: MoodResponse
    frequency: FrequencyResponse

    # Optional additional data
    audio_fingerprint_match: Optional[str] = None
    detected_genre: Optional[str] = None


class AudioAnalysisHistoryResponse(BaseModel):
    """Schema for audio analysis history."""
    id: int
    timestamp: datetime
    bpm: Optional[float] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    primary_emotion: Optional[str] = None
    rms_energy: Optional[float] = None

    class Config:
        from_attributes = True


class AudioFingerprintResponse(BaseModel):
    """Schema for audio fingerprint response."""
    id: int
    track_name: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[float] = None
    avg_bpm: Optional[float] = None
    key: Optional[str] = None
    match_confidence: float = Field(default=0.0, ge=0, le=1)

    class Config:
        from_attributes = True
