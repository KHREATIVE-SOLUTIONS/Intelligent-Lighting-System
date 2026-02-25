"""Canned audio/effect timelines for deterministic QA regression tests."""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Section:
    name: str
    start: float
    end: float
    section_type: str


@dataclass(frozen=True)
class Beat:
    time: float
    is_downbeat: bool


@dataclass(frozen=True)
class EffectFrame:
    time: float
    section: str
    intensity: float
    beam_width: float
    strobe_on: bool
    hue: float


@dataclass(frozen=True)
class TransitionEvent:
    section: str
    transition_time: float


@dataclass(frozen=True)
class SongCase:
    name: str
    sections: List[Section]
    beats: List[Beat]
    effect_frames: List[EffectFrame]
    transitions: List[TransitionEvent]
    song_change_time: float
    thresholds: Dict[str, float]
    beam_width_targets: Dict[str, Tuple[float, float]]


def _beats_for_four_four(duration_seconds: int) -> List[Beat]:
    beats: List[Beat] = []
    for t in range(duration_seconds):
        beats.append(Beat(time=float(t), is_downbeat=(t % 4 == 0)))
    return beats


def _effect_frames() -> List[EffectFrame]:
    frames: List[EffectFrame] = []

    verse_hues = [0.58, 0.60, 0.59, 0.61, 0.58, 0.60, 0.59, 0.60]
    chorus_hues = [0.08, 0.10, 0.11, 0.09, 0.10, 0.12, 0.11, 0.09]
    drop_hues = [0.78, 0.80, 0.79, 0.81, 0.77, 0.82, 0.79, 0.80]

    # Verse 0-8s: softer, wider beams, no strobe.
    for t in range(0, 8):
        frames.append(
            EffectFrame(
                time=float(t),
                section="verse",
                intensity=0.35 + (0.02 * (t % 2)),
                beam_width=31.0 + (t % 3),
                strobe_on=False,
                hue=verse_hues[t],
            )
        )

    # Chorus 8-16s: brighter, medium beams, controlled strobes.
    strobe_chorus = {9, 11, 13}
    for t in range(8, 16):
        frames.append(
            EffectFrame(
                time=float(t),
                section="chorus",
                intensity=0.72 + (0.04 * (t % 2)),
                beam_width=22.0 + (t % 2),
                strobe_on=t in strobe_chorus,
                hue=chorus_hues[t - 8],
            )
        )

    # Drop 16-24s: highest intensity, tight beams, limited strobe windows.
    strobe_drop = {16, 17, 20, 22}
    for t in range(16, 24):
        frames.append(
            EffectFrame(
                time=float(t),
                section="drop",
                intensity=0.86 + (0.04 * (t % 2)),
                beam_width=12.0 + (t % 2),
                strobe_on=t in strobe_drop,
                hue=drop_hues[t - 16],
            )
        )

    return frames


CASE_STABLE_DANCE_TRACK = SongCase(
    name="stable-dance-track",
    sections=[
        Section(name="verse-a", start=0.0, end=8.0, section_type="verse"),
        Section(name="chorus-a", start=8.0, end=16.0, section_type="chorus"),
        Section(name="drop-a", start=16.0, end=24.0, section_type="drop"),
    ],
    beats=_beats_for_four_four(24),
    effect_frames=_effect_frames(),
    transitions=[
        TransitionEvent(section="chorus", transition_time=8.04),
        TransitionEvent(section="drop", transition_time=16.06),
    ],
    song_change_time=16.0,
    thresholds={
        "contrast_ratio_min": 1.8,
        "transition_alignment_ms_max": 120.0,
        "beam_width_tolerance_deg": 2.0,
        "strobe_budget_ratio_max": 0.35,
        "strobe_max_continuous_seconds": 2.0,
        "color_novelty_min": 0.20,
    },
    beam_width_targets={
        "verse": (30.0, 35.0),
        "chorus": (20.0, 24.0),
        "drop": (10.0, 14.0),
    },
)


QA_CASES = [CASE_STABLE_DANCE_TRACK]
