"""Musically-aware beam-width choreography utilities."""

from dataclasses import dataclass
from typing import Union

from .section_manager import SongSection


PHRASE_BARS = 8
BEATS_PER_BAR = 4
BEATS_PER_PHRASE = PHRASE_BARS * BEATS_PER_BAR

# 0.0 = tight beam, 1.0 = very wide
MIN_BEAM_ANGLE_DEG = 2.5
MAX_BEAM_ANGLE_DEG = 11.5


@dataclass(frozen=True)
class BeamWidthTarget:
    """Computed beam-width state for a phrase position."""

    normalized_width: float
    beam_angle_deg: float
    beam_width_profile: str
    phrase_phase: float
    bar_in_phrase: int


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _as_section_value(section: Union[str, SongSection]) -> str:
    if isinstance(section, SongSection):
        return section.value
    return str(section or "unknown")


def _phrase_position(beat_number: int) -> tuple[float, int]:
    beat_index = max(0, int(beat_number) - 1)
    beat_in_phrase = beat_index % BEATS_PER_PHRASE
    phrase_phase = beat_in_phrase / float(BEATS_PER_PHRASE)
    bar_in_phrase = (beat_in_phrase // BEATS_PER_BAR) + 1
    return phrase_phase, bar_in_phrase


def _base_profile_for_section(section: str) -> tuple[str, float]:
    if section in {"drop", "peak"}:
        return "drop_snap_open", 0.16
    if section in {"pre_chorus", "buildup"}:
        return "narrowing_ramp", 0.68
    if section == "verse":
        return "verse_windows", 0.56
    if section in {"breakdown", "outro"}:
        return "sparse_wide_frost", 0.82
    if section in {"intro", "bridge"}:
        return "gentle_wide", 0.66
    if section == "chorus":
        return "chorus_tight_drive", 0.34
    return "balanced", 0.52


def compute_beam_width_target(
    section: Union[str, SongSection],
    beat_number: int,
    buildup_progress: float = 0.0,
) -> BeamWidthTarget:
    """Return beam-width target for section + phrase position."""
    section_value = _as_section_value(section)
    phrase_phase, bar_in_phrase = _phrase_position(beat_number)
    profile, width = _base_profile_for_section(section_value)

    if profile == "verse_windows":
        # Verse: medium with wider windows around bars 2-3 and phrase tail.
        if bar_in_phrase in {2, 3, 7}:
            width = 0.70
        elif bar_in_phrase in {4, 8}:
            width = 0.62
        else:
            width = 0.54
    elif profile == "narrowing_ramp":
        # Build/pre-chorus: deterministic narrowing through phrase.
        width = 0.74 - (0.42 * phrase_phase)
        width -= 0.12 * _clamp01(buildup_progress)
    elif profile == "drop_snap_open":
        # Drop hit: snap tight for first half-bar then controlled open.
        if phrase_phase < 0.0625:
            width = 0.08
        else:
            open_phase = (phrase_phase - 0.0625) / (1.0 - 0.0625)
            width = 0.12 + (0.44 * (open_phase ** 0.85))
    elif profile == "sparse_wide_frost":
        # Breakdown: sparse/wide with subtle breathing texture.
        pulse = 0.03 if bar_in_phrase in {1, 5} else -0.02
        width = 0.84 + pulse
    elif profile == "chorus_tight_drive":
        width = 0.30 + (0.08 if bar_in_phrase in {4, 8} else 0.0)

    width = _clamp01(width)
    beam_angle = MIN_BEAM_ANGLE_DEG + width * (MAX_BEAM_ANGLE_DEG - MIN_BEAM_ANGLE_DEG)

    return BeamWidthTarget(
        normalized_width=width,
        beam_angle_deg=beam_angle,
        beam_width_profile=profile,
        phrase_phase=phrase_phase,
        bar_in_phrase=bar_in_phrase,
    )

