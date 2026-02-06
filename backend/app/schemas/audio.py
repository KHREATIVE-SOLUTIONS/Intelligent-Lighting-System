"""
Audio Analysis Schemas
======================

Pydantic schemas for audio analysis operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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
