"""
Training Data Builder
=====================

Builds paired (audio features, lighting state) training datasets
from multiple sources:
1. Operator recordings (TrainingRecorder)
2. Video analysis (VideoAnalyzerPipeline)
3. Synthetic generation (rule-based)

Exports to PyTorch Dataset format for model training.
"""

import json
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import logging
import time

from app.models.ald import AbstractLightingState, ALDTimeline

logger = logging.getLogger(__name__)


@dataclass
class AudioFeatures:
    """Audio feature vector for a single training frame."""
    timestamp: float = 0.0

    # Basic features (from audio_analyzer)
    bpm: float = 120.0
    energy: float = 0.0
    bass: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    spectral_flux: float = 0.0
    spectral_centroid: float = 0.0

    # Beat info
    is_beat: bool = False
    is_downbeat: bool = False
    beat_position: int = 1
    beat_phase: float = 0.0

    # Emotion (from MERT)
    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    tension: float = 0.0
    groove: float = 0.0
    darkness: float = 0.0

    # Structure (from music_structure)
    section_label: str = "unknown"
    section_progress: float = 0.0
    bars_to_transition: int = 0

    # Genre
    genre: str = "unknown"

    # MERT embeddings (optional, for training)
    mert_embedding: Optional[List[float]] = None

    def to_array(self, include_embedding: bool = False) -> np.ndarray:
        """Convert to flat numpy array for model input."""
        features = [
            self.bpm / 200.0,           # Normalize BPM
            self.energy,
            self.bass,
            self.mid,
            self.high,
            self.spectral_flux,
            self.spectral_centroid / 8000.0,  # Normalize
            float(self.is_beat),
            float(self.is_downbeat),
            self.beat_position / 4.0,
            self.beat_phase,
            self.valence,
            self.arousal,
            self.dominance,
            self.tension,
            self.groove,
            self.darkness,
            self.section_progress,
            self.bars_to_transition / 16.0,  # Normalize
        ]

        if include_embedding and self.mert_embedding:
            features.extend(self.mert_embedding)

        return np.array(features, dtype=np.float32)


@dataclass
class LightingTarget:
    """Lighting state target for a single training frame."""
    timestamp: float = 0.0
    ald_state: Optional[AbstractLightingState] = None

    # Flattened representation for training
    master_intensity: float = 0.5
    primary_hue: float = 0.0
    primary_saturation: float = 1.0
    secondary_hue: float = 180.0
    coverage: float = 0.5
    movement_speed: float = 0.0
    movement_type_idx: int = 0     # Index into MovementType enum
    beat_response: float = 0.5
    strobe_active: bool = False
    effect_type_idx: int = 0       # Index into EffectType enum

    def to_array(self) -> np.ndarray:
        """Convert to flat numpy array for model output target."""
        return np.array([
            self.master_intensity,
            self.primary_hue / 360.0,
            self.primary_saturation,
            self.secondary_hue / 360.0,
            self.coverage,
            self.movement_speed,
            self.movement_type_idx / 14.0,  # Normalize by enum size
            self.beat_response,
            float(self.strobe_active),
            self.effect_type_idx / 11.0,
        ], dtype=np.float32)

    @classmethod
    def from_ald_state(cls, state: AbstractLightingState) -> "LightingTarget":
        """Create from an ALD state."""
        from app.models.ald import MovementType, EffectType
        movement_types = list(MovementType)
        effect_types = list(EffectType)

        return cls(
            timestamp=state.timestamp,
            ald_state=state,
            master_intensity=state.master_intensity,
            primary_hue=state.primary_color.hue,
            primary_saturation=state.primary_color.saturation,
            secondary_hue=state.secondary_color.hue,
            coverage=state.coverage,
            movement_speed=state.movement.speed,
            movement_type_idx=movement_types.index(state.movement.movement_type)
            if state.movement.movement_type in movement_types else 0,
            beat_response=state.beat_response,
            strobe_active=any(
                e.effect_type == EffectType.STROBE for e in state.effects
            ),
            effect_type_idx=effect_types.index(state.effects[0].effect_type)
            if state.effects and state.effects[0].effect_type in effect_types else 0,
        )


@dataclass
class TrainingPair:
    """A single audio-lighting training pair."""
    audio: AudioFeatures
    lighting: LightingTarget
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON export."""
        return {
            "timestamp": self.audio.timestamp,
            "audio": {
                "bpm": self.audio.bpm,
                "energy": self.audio.energy,
                "bass": self.audio.bass,
                "mid": self.audio.mid,
                "high": self.audio.high,
                "spectral_flux": self.audio.spectral_flux,
                "spectral_centroid": self.audio.spectral_centroid,
                "is_beat": self.audio.is_beat,
                "is_downbeat": self.audio.is_downbeat,
                "beat_position": self.audio.beat_position,
                "beat_phase": self.audio.beat_phase,
                "valence": self.audio.valence,
                "arousal": self.audio.arousal,
                "dominance": self.audio.dominance,
                "tension": self.audio.tension,
                "groove": self.audio.groove,
                "darkness": self.audio.darkness,
                "section_label": self.audio.section_label,
                "section_progress": self.audio.section_progress,
                "genre": self.audio.genre,
            },
            "lighting": {
                "master_intensity": self.lighting.master_intensity,
                "primary_hue": self.lighting.primary_hue,
                "primary_saturation": self.lighting.primary_saturation,
                "secondary_hue": self.lighting.secondary_hue,
                "coverage": self.lighting.coverage,
                "movement_speed": self.lighting.movement_speed,
                "movement_type_idx": self.lighting.movement_type_idx,
                "beat_response": self.lighting.beat_response,
                "strobe_active": self.lighting.strobe_active,
                "effect_type_idx": self.lighting.effect_type_idx,
            },
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingPair":
        """Deserialize from dictionary."""
        audio_data = data.get("audio", {})
        lighting_data = data.get("lighting", {})

        audio = AudioFeatures(
            timestamp=data.get("timestamp", 0.0),
            bpm=audio_data.get("bpm", 120.0),
            energy=audio_data.get("energy", 0.0),
            bass=audio_data.get("bass", 0.0),
            mid=audio_data.get("mid", 0.0),
            high=audio_data.get("high", 0.0),
            spectral_flux=audio_data.get("spectral_flux", 0.0),
            spectral_centroid=audio_data.get("spectral_centroid", 0.0),
            is_beat=audio_data.get("is_beat", False),
            is_downbeat=audio_data.get("is_downbeat", False),
            beat_position=audio_data.get("beat_position", 1),
            beat_phase=audio_data.get("beat_phase", 0.0),
            valence=audio_data.get("valence", 0.0),
            arousal=audio_data.get("arousal", 0.0),
            dominance=audio_data.get("dominance", 0.0),
            tension=audio_data.get("tension", 0.0),
            groove=audio_data.get("groove", 0.0),
            darkness=audio_data.get("darkness", 0.0),
            section_label=audio_data.get("section_label", "unknown"),
            section_progress=audio_data.get("section_progress", 0.0),
            genre=audio_data.get("genre", "unknown"),
        )

        lighting = LightingTarget(
            timestamp=data.get("timestamp", 0.0),
            master_intensity=lighting_data.get("master_intensity", 0.5),
            primary_hue=lighting_data.get("primary_hue", 0.0),
            primary_saturation=lighting_data.get("primary_saturation", 1.0),
            secondary_hue=lighting_data.get("secondary_hue", 180.0),
            coverage=lighting_data.get("coverage", 0.5),
            movement_speed=lighting_data.get("movement_speed", 0.0),
            movement_type_idx=lighting_data.get("movement_type_idx", 0),
            beat_response=lighting_data.get("beat_response", 0.5),
            strobe_active=lighting_data.get("strobe_active", False),
            effect_type_idx=lighting_data.get("effect_type_idx", 0),
        )

        return cls(
            audio=audio,
            lighting=lighting,
            metadata=data.get("metadata", {}),
        )


class DatasetBuilder:
    """Builds training datasets from multiple sources.

    Collects TrainingPairs and exports them in formats suitable
    for PyTorch training.
    """

    def __init__(self, output_dir: str = "data/training"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pairs: List[TrainingPair] = []
        self.metadata: Dict[str, Any] = {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sources": [],
        }

    def add_pair(self, pair: TrainingPair):
        """Add a single training pair."""
        self.pairs.append(pair)

    def add_pairs(self, pairs: List[TrainingPair], source: str = "unknown"):
        """Add multiple training pairs from a source."""
        self.pairs.extend(pairs)
        self.metadata["sources"].append({
            "name": source,
            "count": len(pairs),
            "added": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        logger.info("Added %d pairs from source '%s' (total: %d)",
                     len(pairs), source, len(self.pairs))

    def import_recording_session(
        self, jsonl_path: str, operator_id: str = "unknown"
    ) -> int:
        """Import training data from a TrainingRecorder JSONL export.

        Args:
            jsonl_path: Path to the JSONL file
            operator_id: Identifier for the operator

        Returns:
            Number of pairs imported
        """
        path = Path(jsonl_path)
        if not path.exists():
            logger.error("Recording file not found: %s", jsonl_path)
            return 0

        count = 0
        with open(path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    audio_data = data.get("audio", {})
                    lighting_data = data.get("lighting", {})

                    audio = AudioFeatures(
                        timestamp=data.get("timestamp", 0.0),
                        bpm=audio_data.get("bpm", 120.0),
                        energy=audio_data.get("energy", 0.0),
                        bass=audio_data.get("bass", 0.0),
                        mid=audio_data.get("mid", 0.0),
                        high=audio_data.get("high", 0.0),
                        valence=audio_data.get("valence", 0.0),
                        arousal=audio_data.get("arousal", 0.0),
                        spectral_flux=audio_data.get("spectral_flux", 0.0),
                        is_beat=audio_data.get("is_beat", False),
                        beat_position=audio_data.get("beat_position", 1),
                    )

                    # Extract lighting from raw fixture data
                    fixtures = lighting_data.get("fixtures", [])
                    if fixtures:
                        avg_dimmer = np.mean([f.get("dimmer", 0.5) for f in fixtures])
                        avg_r = np.mean([f.get("r", 1.0) for f in fixtures])
                        avg_g = np.mean([f.get("g", 1.0) for f in fixtures])
                        avg_b = np.mean([f.get("b", 1.0) for f in fixtures])
                    else:
                        avg_dimmer = 0.5
                        avg_r = avg_g = avg_b = 1.0

                    # Convert RGB to hue
                    import colorsys
                    h, s, v = colorsys.rgb_to_hsv(avg_r, avg_g, avg_b)

                    lighting = LightingTarget(
                        timestamp=data.get("timestamp", 0.0),
                        master_intensity=float(avg_dimmer),
                        primary_hue=float(h * 360),
                        primary_saturation=float(s),
                    )

                    pair = TrainingPair(
                        audio=audio,
                        lighting=lighting,
                        metadata={"source": "recording", "operator": operator_id},
                    )
                    self.pairs.append(pair)
                    count += 1
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping malformed line: %s", e)

        self.metadata["sources"].append({
            "name": f"recording:{operator_id}:{path.stem}",
            "count": count,
        })
        logger.info("Imported %d pairs from recording %s", count, jsonl_path)
        return count

    def export_jsonl(self, filename: str = "training_data.jsonl") -> str:
        """Export dataset as JSONL (one JSON per line)."""
        filepath = self.output_dir / filename
        with open(filepath, "w") as f:
            for pair in self.pairs:
                f.write(json.dumps(pair.to_dict()) + "\n")

        # Export metadata
        meta_path = self.output_dir / f"{Path(filename).stem}_meta.json"
        self.metadata["total_pairs"] = len(self.pairs)
        self.metadata["exported"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(meta_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

        logger.info("Exported %d pairs to %s", len(self.pairs), filepath)
        return str(filepath)

    def export_numpy(self, filename: str = "training_data") -> Tuple[str, str]:
        """Export as numpy arrays for direct training use.

        Returns:
            Tuple of (audio_features_path, lighting_targets_path)
        """
        if not self.pairs:
            logger.warning("No pairs to export")
            return ("", "")

        audio_arrays = np.stack([p.audio.to_array() for p in self.pairs])
        lighting_arrays = np.stack([p.lighting.to_array() for p in self.pairs])

        audio_path = self.output_dir / f"{filename}_audio.npy"
        lighting_path = self.output_dir / f"{filename}_lighting.npy"

        np.save(str(audio_path), audio_arrays)
        np.save(str(lighting_path), lighting_arrays)

        logger.info(
            "Exported numpy arrays: audio %s, lighting %s",
            audio_arrays.shape, lighting_arrays.shape,
        )
        return (str(audio_path), str(lighting_path))

    def export_pytorch_dataset(self, filename: str = "training_data.pt") -> str:
        """Export as a PyTorch-compatible dataset file.

        Creates a dict with 'audio' and 'lighting' tensors.
        """
        try:
            import torch
        except ImportError:
            logger.error("PyTorch not installed, cannot export dataset")
            return ""

        if not self.pairs:
            logger.warning("No pairs to export")
            return ""

        audio_arrays = np.stack([p.audio.to_array() for p in self.pairs])
        lighting_arrays = np.stack([p.lighting.to_array() for p in self.pairs])

        dataset = {
            "audio": torch.from_numpy(audio_arrays),
            "lighting": torch.from_numpy(lighting_arrays),
            "metadata": self.metadata,
        }

        filepath = self.output_dir / filename
        torch.save(dataset, str(filepath))
        logger.info("Exported PyTorch dataset: %d pairs to %s", len(self.pairs), filepath)
        return str(filepath)

    def get_stats(self) -> Dict[str, Any]:
        """Get dataset statistics."""
        if not self.pairs:
            return {"total_pairs": 0}

        genres = {}
        sections = {}
        for pair in self.pairs:
            genres[pair.audio.genre] = genres.get(pair.audio.genre, 0) + 1
            sections[pair.audio.section_label] = sections.get(pair.audio.section_label, 0) + 1

        return {
            "total_pairs": len(self.pairs),
            "sources": self.metadata.get("sources", []),
            "genre_distribution": genres,
            "section_distribution": sections,
            "duration_sec": self.pairs[-1].audio.timestamp - self.pairs[0].audio.timestamp
            if len(self.pairs) > 1 else 0,
        }
