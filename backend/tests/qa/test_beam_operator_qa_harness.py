"""Objective QA harness for section-aware beam operator behavior."""

from collections import defaultdict
from statistics import mean

import pytest

from .canned_audio_timelines import QA_CASES, Beat, EffectFrame, SongCase


def _nearest_downbeat_error_ms(transition_time: float, beats: list[Beat]) -> float:
    downbeats = [b.time for b in beats if b.is_downbeat]
    nearest_error_s = min(abs(transition_time - b) for b in downbeats)
    return nearest_error_s * 1000.0


def _section_means(frames: list[EffectFrame], field: str) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for frame in frames:
        grouped[frame.section].append(getattr(frame, field))
    return {section: mean(values) for section, values in grouped.items()}


def _hue_distance(h1: float, h2: float) -> float:
    delta = abs(h1 - h2)
    return min(delta, 1.0 - delta)


@pytest.mark.parametrize("case", QA_CASES, ids=[c.name for c in QA_CASES])
def test_section_contrast_ratio(case: SongCase):
    """Verse vs chorus/drop intensity contrast must clear minimum ratio."""
    means = _section_means(case.effect_frames, "intensity")

    verse_mean = means["verse"]
    chorus_ratio = means["chorus"] / verse_mean
    drop_ratio = means["drop"] / verse_mean

    assert chorus_ratio >= case.thresholds["contrast_ratio_min"]
    assert drop_ratio >= case.thresholds["contrast_ratio_min"]


@pytest.mark.parametrize("case", QA_CASES, ids=[c.name for c in QA_CASES])
def test_transition_alignment_to_downbeat(case: SongCase):
    """Section transition cues must be aligned to nearest downbeat."""
    max_allowed_ms = case.thresholds["transition_alignment_ms_max"]

    for event in case.transitions:
        error_ms = _nearest_downbeat_error_ms(event.transition_time, case.beats)
        assert error_ms <= max_allowed_ms


@pytest.mark.parametrize("case", QA_CASES, ids=[c.name for c in QA_CASES])
def test_beam_width_intent_adherence(case: SongCase):
    """Average beam width per section must stay in intent window (+/- tolerance)."""
    means = _section_means(case.effect_frames, "beam_width")
    tolerance = case.thresholds["beam_width_tolerance_deg"]

    for section_name, (target_min, target_max) in case.beam_width_targets.items():
        width = means[section_name]
        assert (target_min - tolerance) <= width <= (target_max + tolerance)


@pytest.mark.parametrize("case", QA_CASES, ids=[c.name for c in QA_CASES])
def test_strobe_budget_and_anti_fatigue(case: SongCase):
    """Total strobe usage and continuous streak length must remain safe."""
    frames = case.effect_frames
    strobe_frames = [f for f in frames if f.strobe_on]

    strobe_ratio = len(strobe_frames) / len(frames)
    assert strobe_ratio <= case.thresholds["strobe_budget_ratio_max"]

    max_contiguous = 0
    current = 0
    for frame in frames:
        if frame.strobe_on:
            current += 1
            max_contiguous = max(max_contiguous, current)
        else:
            current = 0

    # Frames are sampled every second in canned data.
    assert max_contiguous <= case.thresholds["strobe_max_continuous_seconds"]


@pytest.mark.parametrize("case", QA_CASES, ids=[c.name for c in QA_CASES])
def test_color_novelty_on_section_and_song_change(case: SongCase):
    """Section/song changes must produce perceptible hue novelty."""
    by_time = {frame.time: frame for frame in case.effect_frames}

    boundary_pairs = [
        (7.0, 8.0),   # verse -> chorus
        (15.0, 16.0),  # chorus -> drop (also song-change boundary in canned set)
    ]

    novelty_values = []
    for before_t, after_t in boundary_pairs:
        before_hue = by_time[before_t].hue
        after_hue = by_time[after_t].hue
        novelty_values.append(_hue_distance(before_hue, after_hue))

    assert min(novelty_values) >= case.thresholds["color_novelty_min"]
