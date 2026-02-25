"""
Professional Lighting Services
Concert-quality lighting modules for the ILS effects engine.
"""

from .genre_profiles import GenreProfile, GenreProfileManager, GENRE_PROFILES
from .section_manager import SectionManager, SongSection, SectionConfig
from .movement_patterns import (
    ProMovementEngine, ProMovementPattern, ProMovementParams,
    FixtureGrouping, FIXTURE_GROUPING, PRO_MOVEMENT_PRESETS,
    GENRE_SPEED_DEFAULTS, apply_genre_defaults,
    degrees_to_dmx_pan, degrees_to_dmx_tilt,
)
from .pro_effects import ProEffects, ProStrobe, ProColorWash, ProChase, ProBuildEffect
from .key_lighting import KeyLightingManager, PerformerZone, KeyLightConfig
from .beam_choreography import BeamWidthTarget, compute_beam_width_target

__all__ = [
    'GenreProfile', 'GenreProfileManager', 'GENRE_PROFILES',
    'SectionManager', 'SongSection', 'SectionConfig',
    'ProMovementEngine', 'ProMovementPattern', 'ProMovementParams',
    'FixtureGrouping', 'FIXTURE_GROUPING', 'PRO_MOVEMENT_PRESETS',
    'GENRE_SPEED_DEFAULTS', 'apply_genre_defaults',
    'degrees_to_dmx_pan', 'degrees_to_dmx_tilt',
    'ProEffects', 'ProStrobe', 'ProColorWash', 'ProChase', 'ProBuildEffect',
    'KeyLightingManager', 'PerformerZone', 'KeyLightConfig',
    'BeamWidthTarget', 'compute_beam_width_target',
]
