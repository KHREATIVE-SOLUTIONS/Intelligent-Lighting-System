"""
ILS Intelligent Effects Engine
4-Layer Architecture: Movement, Dimmer, Strobe, Color
+ LFO Engine for grandMA2-style effects
"""

from .fixture_groups import FixtureGroup, FixtureGroupManager
from .movement_patterns import MovementParams, MovementEngine, MovementType, StaticLook, MOVEMENT_PRESETS, MovementOrchestrator
from .dimmer_effects import DimmerParams, DimmerEngine, DimmerType, DIMMER_PRESETS, BEAT_PATTERNS
from .strobe_controller import StrobeController, StrobeMode, StrobeParams, STROBE_PRESETS
from .color_mapper import COLOR_PRESETS, MOOD_COLORS
from .color_mapper import ColorMapper, ColorPalette
from .decision_engine import DecisionEngine, LightingState
from .effects_engine import EffectsEngine, EffectsConfig
from .lfo_engine import (
    LFOEngine, LFOConfig, EffectPreset,
    WaveformType, PhaseDistribution, EffectDirection, EffectAttribute,
    Waveforms, PhaseDistributor,
    create_circle_effect, create_dimmer_chase
)

__all__ = [
    'FixtureGroup',
    'FixtureGroupManager',
    'MovementParams',
    'MovementEngine',
    'MovementType',
    'MovementOrchestrator',
    'StaticLook',
    # BUG-046 fix: export preset dicts so consumers can import them
    'MOVEMENT_PRESETS',
    'DimmerParams',
    'DimmerEngine',
    'DimmerType',
    'DIMMER_PRESETS',
    'BEAT_PATTERNS',
    'StrobeController',
    'StrobeMode',
    'StrobeParams',
    'STROBE_PRESETS',
    'ColorMapper',
    'ColorPalette',
    'COLOR_PRESETS',
    'MOOD_COLORS',
    'DecisionEngine',
    'LightingState',
    'EffectsEngine',
    'EffectsConfig',
    # LFO Engine (grandMA2-style)
    'LFOEngine',
    'LFOConfig',
    'EffectPreset',
    'WaveformType',
    'PhaseDistribution',
    'EffectDirection',
    'EffectAttribute',
    'Waveforms',
    'PhaseDistributor',
    'create_circle_effect',
    'create_dimmer_chase',
]
