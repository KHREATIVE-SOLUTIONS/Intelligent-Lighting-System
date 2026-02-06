"""
Audio Analysis Models
=====================

Database models for storing audio analysis results and fingerprints.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, JSON, Text, LargeBinary
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class AudioAnalysis(Base):
    """Stored audio analysis results."""

    __tablename__ = "audio_analyses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    source = Column(String(50), default="live")  # live, file, stream

    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)
    duration = Column(Float, nullable=True)  # seconds

    # Beat detection
    bpm = Column(Float, nullable=True)
    beat_confidence = Column(Float, nullable=True)
    beat_positions = Column(JSON, nullable=True)  # Array of beat timestamps
    downbeats = Column(JSON, nullable=True)  # Array of downbeat timestamps

    # Mood classification (valence-arousal model)
    valence = Column(Float, nullable=True)  # -1 to 1 (negative to positive)
    arousal = Column(Float, nullable=True)  # -1 to 1 (calm to energetic)
    mood_confidence = Column(Float, nullable=True)
    detected_emotions = Column(JSON, nullable=True)  # {emotion: confidence}

    # Frequency analysis
    frequency_bands = Column(JSON, nullable=True)  # {band: energy}
    spectral_centroid = Column(Float, nullable=True)
    spectral_rolloff = Column(Float, nullable=True)
    spectral_flux = Column(Float, nullable=True)

    # Energy levels
    rms_energy = Column(Float, nullable=True)
    peak_amplitude = Column(Float, nullable=True)

    # Genre/style (optional)
    detected_genre = Column(String(100), nullable=True)
    genre_confidence = Column(Float, nullable=True)

    # Raw features (for ML)
    mfcc_features = Column(JSON, nullable=True)  # Mel-frequency cepstral coefficients
    chroma_features = Column(JSON, nullable=True)

    # Link to fingerprint
    fingerprint_id = Column(Integer, ForeignKey("audio_fingerprints.id"), nullable=True)

    # Relationships
    fingerprint = relationship("AudioFingerprint", back_populates="analyses")

    def __repr__(self):
        return f"<AudioAnalysis(id={self.id}, bpm={self.bpm}, valence={self.valence})>"


class AudioFingerprint(Base):
    """Audio fingerprint for song identification."""

    __tablename__ = "audio_fingerprints"

    id = Column(Integer, primary_key=True, index=True)

    # Track identification
    track_name = Column(String(255), nullable=True)
    artist = Column(String(255), nullable=True)
    album = Column(String(255), nullable=True)
    isrc = Column(String(20), nullable=True)  # International Standard Recording Code

    # Fingerprint data
    fingerprint_hash = Column(String(64), unique=True, index=True)
    fingerprint_data = Column(LargeBinary, nullable=True)  # Compressed fingerprint

    # Audio characteristics
    duration = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    avg_bpm = Column(Float, nullable=True)
    key = Column(String(10), nullable=True)  # Musical key
    time_signature = Column(String(10), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_matched = Column(DateTime, nullable=True)
    match_count = Column(Integer, default=0)

    # Relationships
    shows = relationship("Show", back_populates="audio_fingerprint")
    analyses = relationship("AudioAnalysis", back_populates="fingerprint")

    def __repr__(self):
        return f"<AudioFingerprint(id={self.id}, track='{self.track_name}')>"
