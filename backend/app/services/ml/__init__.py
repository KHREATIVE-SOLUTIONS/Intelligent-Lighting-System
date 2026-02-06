"""Machine learning services."""

from .training_recorder import (
    TrainingRecorder,
    ManualLightingController,
    TrainingFrame,
    AudioFrame,
    LightingFrame,
    get_recorder,
    set_recorder
)
from .mert_model import MERTModel, EmotionVector, LightingEmotionMapping
from .music_structure import MusicStructureAnalyzer, SectionType, StructureAnalysis
from .genre_classifier import GenreClassifier, GenreResult
