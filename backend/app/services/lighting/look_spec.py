"""
Lighting Look Spec Builder
==========================

Builds a typed beam/spot intent payload from current effects engine state.
"""

from datetime import datetime

from app.schemas.lighting_look import (
    BeamLookParams,
    ColorLookParams,
    FixtureCapabilityProfile,
    LightingLookSpec,
    SpotLookParams,
    TransitionLookParams,
)
from app.services.lighting.beam_choreography import compute_beam_width_target
from app.services.lighting.fixture_capabilities import DEFAULT_CAPABILITY_PROFILES
from app.services.lighting.section_templates import get_section_template


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _section_and_genre(engine) -> tuple[str, str]:
    section = "unknown"
    genre = "unknown"

    try:
        if getattr(engine, "_pro_lighting_enabled", False):
            section = engine.section_manager.current_section.value
            genre = engine.genre_manager.current_genre.value
        else:
            section = engine.decision.state.value
    except Exception:
        pass

    return section, genre


def _palette_colors(palette_id: str) -> tuple[str, str]:
    palette_map = {
        "edm": ("cyan", "magenta"),
        "rock": ("red", "white"),
        "ambient": ("deep_blue", "lavender"),
        "warm": ("amber", "orange"),
        "cool": ("blue", "teal"),
        "sunset": ("orange", "pink"),
        "forest": ("green", "amber"),
    }
    return palette_map.get(palette_id, ("blue", "amber"))


def _beat_number_from_engine(engine) -> int:
    beat_number = 0
    try:
        beat_number = int(getattr(engine.audio_state, "beat_number", 0) or 0)
    except Exception:
        beat_number = 0
    if beat_number <= 0:
        beat_number = int(getattr(engine, "beat_count", 0) or 0)
    return max(1, beat_number)


def build_lighting_look_spec(engine) -> LightingLookSpec:
    """
    Create a typed look spec from the current engine state.

    Phase 1 goal: establish stable contract fields for downstream visualizers.
    """
    section, genre = _section_and_genre(engine)

    energy = _clamp01(getattr(engine.audio_state, "energy", 0.0))
    bpm = float(getattr(engine.config, "bpm", 0.0) or 0.0)

    movement_pattern = "none"
    movement_speed = 0.0
    strobe_mode = "off"
    palette_id = "unknown"
    palette_version = int(getattr(engine, "_palette_version", 1) or 1)
    palette_locked = bool(getattr(engine, "_palette_locked", False))
    try:
        movement_pattern = engine.movement.params.pattern.value
        movement_speed = max(
            float(getattr(engine.movement.params, "pan_speed", 0.0)),
            float(getattr(engine.movement.params, "tilt_speed", 0.0)),
        )
        strobe_mode = engine.strobe.params.mode.value
        palette_id = getattr(getattr(engine, "_current_song_palette", None), "value", None) or engine.config.palette.value
    except Exception:
        pass

    beat_number = _beat_number_from_engine(engine)
    buildup_progress = 0.0
    if getattr(engine, "_pro_lighting_enabled", False):
        try:
            buildup_progress = float(engine.section_manager.get_buildup_progress())
        except Exception:
            buildup_progress = 0.0

    beam_width_target = compute_beam_width_target(
        section=section,
        beat_number=beat_number,
        buildup_progress=buildup_progress,
    )

    dominant_color, accent_color = _palette_colors(palette_id)
    beam_density = _clamp01(0.35 + energy * 0.65)
    template = get_section_template(genre, section)

    focus_mode = "performer" if section in {"verse", "bridge", "outro"} else "texture"
    gobo_mode = "texture" if section in {"chorus", "drop", "peak"} else "clean"
    zoom = _clamp01(0.2 + energy * 0.6)
    iris = _clamp01(0.7 - energy * 0.45)
    key_priority = 0.9 if section in {"verse", "bridge", "outro"} else 0.6

    section_saturation_mult = 1.0
    section_white_offset = 0.0
    if section in {"chorus", "drop", "peak"}:
        section_saturation_mult = 1.2
        section_white_offset = -0.04
    elif section in {"breakdown", "bridge"}:
        section_saturation_mult = 0.75
        section_white_offset = 0.08

    transition_ms = 260 if section in {"chorus", "drop", "peak"} else 700
    blackout_policy = template.blackout_policy if template else ("button" if section in {"outro", "peak"} else "phrase_boundary")

    return LightingLookSpec(
        timestamp=datetime.utcnow(),
        section=section,
        genre=genre,
        energy=energy,
        bpm=bpm,
        palette_version=palette_version,
        palette_locked=palette_locked,
        beam=BeamLookParams(
            beam_angle_deg=beam_width_target.beam_angle_deg,
            beam_width_normalized=beam_width_target.normalized_width,
            beam_width_profile=beam_width_target.beam_width_profile,
            phrase_phase=beam_width_target.phrase_phase,
            density=beam_density,
            strobe_mode=strobe_mode,
            movement_pattern=movement_pattern,
            movement_speed_hz=movement_speed,
        ),
        spot=SpotLookParams(
            focus_mode=focus_mode,
            gobo_mode=gobo_mode,
            zoom=zoom,
            iris=iris,
            key_priority=key_priority,
        ),
        color=ColorLookParams(
            palette_id=palette_id,
            dominant_color=dominant_color,
            accent_color=accent_color,
            saturation=_clamp01((0.35 + energy * 0.6) * section_saturation_mult),
            white_level=_clamp01(0.15 + energy * 0.35 + section_white_offset),
        ),
        transition=TransitionLookParams(
            mib_enabled=template.enable_mib if template else True,
            transition_ms=transition_ms,
            blackout_policy=blackout_policy,
        ),
        fixture_capabilities={
            key: FixtureCapabilityProfile.model_validate(profile.model_dump())
            for key, profile in DEFAULT_CAPABILITY_PROFILES.items()
        },
    )
