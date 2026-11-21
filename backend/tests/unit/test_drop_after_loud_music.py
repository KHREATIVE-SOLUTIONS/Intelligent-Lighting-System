"""The drop has to be caught whatever was played before it.

The November 2026 assessment (finding D2) lost the drop whenever the track
followed loud music: every gate in `StreamingSectionDetector` weighed the moment
against half a minute of running history, and after a loud record a drop is no
longer unusual. The detector now has a second way in - the low end returning at
the top of a build, measured against the build itself - and these tests hold it
there. See docs/DROP_DETECTION_BENCH.md.

Two layers. The first drives the detector with hand-made features, so each rule
is tested on its own and in milliseconds. The second plays real synthesised
audio through the analyser and the venue engine in one continuous run, which is
the only way to see history at all: a fresh engine per track cannot.
"""
from __future__ import annotations

from typing import Callable, List, Tuple

import numpy as np
import pytest

from app.services.lighting.section_manager import StreamingSectionDetector
from tests.musical import metrics as M
from tests.musical import synthetic_audio as SA

FPS = 60.0
BEAT_S = 60.0 / 128.0

# (seconds, energy, bass share, programme loudness); a value may be a (from, to) ramp.
Segment = Tuple[float, object, object, object]

LOUD: Segment = (20.0, 0.22, 0.90, 0.50)
INTRO: Segment = (8.0, 0.03, 0.90, 0.45)
BUILD: Segment = (12.0, (0.03, 0.25), (0.90, 0.30), 0.85)
DROP: Segment = (8.0, 0.21, 0.90, 0.85)


def _at(value, x: float) -> float:
    if isinstance(value, tuple):
        return value[0] + (value[1] - value[0]) * x
    return float(value)


def play(segments: List[Segment], detector: StreamingSectionDetector | None = None):
    """Feed the detector frame by frame. Returns (times of drop commits, segment starts)."""
    detector = detector or StreamingSectionDetector(now=0.0)
    dt = 1.0 / FPS
    t = 0.0
    beat = 0
    next_beat = 0.0
    drops: List[float] = []
    starts: List[float] = []
    was = detector.section
    for seconds, energy, bass, programme in segments:
        starts.append(t)
        frames = int(round(seconds * FPS))
        for i in range(frames):
            t += dt
            x = i / max(1, frames - 1)
            is_beat = t >= next_beat
            if is_beat:
                beat += 1
                next_beat += BEAT_S
            decision = detector.update(
                dt, energy=_at(energy, x), bass=_at(bass, x), programme_level=_at(programme, x),
                is_beat=is_beat, beat_number=beat, bpm=128.0, now=t,
            )
            if decision.section == "drop" and was != "drop":
                drops.append(t)
            was = decision.section
    return drops, starts


def without_release_path() -> StreamingSectionDetector:
    """The detector as it was: no bass jump is ever large enough."""
    detector = StreamingSectionDetector(now=0.0)
    detector._RELEASE_MIN_JUMP = 9.0
    return detector


# ---------------------------------------------------------------------------
# Detector, on hand-made features
# ---------------------------------------------------------------------------

def test_a_drop_after_loud_music_is_caught():
    drops, starts = play([LOUD, INTRO, BUILD, DROP])
    assert len(drops) == 1, f"expected one drop, got {drops}"
    assert 0.0 <= drops[0] - starts[3] <= 1.5, f"drop named {drops[0] - starts[3]:+.2f} s from the real one"


def test_that_drop_was_missed_before_the_release_path():
    """The reason the path exists. If this starts passing a drop, the old gates
    have changed and the release path should be looked at again."""
    drops, _ = play([LOUD, INTRO, BUILD, DROP], without_release_path())
    assert drops == []


def test_a_cold_drop_is_still_caught_once():
    drops, starts = play([INTRO, BUILD, DROP])
    assert len(drops) == 1
    assert 0.0 <= drops[0] - starts[2] <= 1.5


@pytest.mark.parametrize("gain", [0.25, 1.0, 2.0])
def test_the_answer_does_not_move_with_the_fader(gain: float):
    scale = lambda seg: (seg[0], tuple(v * gain for v in seg[1]) if isinstance(seg[1], tuple) else seg[1] * gain,
                         seg[2], seg[3])
    drops, starts = play([scale(s) for s in (LOUD, INTRO, BUILD, DROP)])
    assert len(drops) == 1 and 0.0 <= drops[0] - starts[3] <= 1.5


def test_two_drops_back_to_back_are_both_caught():
    drops, starts = play([LOUD, INTRO, BUILD, DROP, LOUD, INTRO, BUILD, DROP])
    assert len(drops) == 2, drops
    assert 0.0 <= drops[0] - starts[3] <= 1.5
    assert 0.0 <= drops[1] - starts[7] <= 1.5


def test_a_cut_from_a_thin_quiet_record_to_a_loud_one_is_not_a_drop():
    """Level and bass both jump, but nothing was building: no climb is two bars
    old on the frame the bass comes back."""
    thin_quiet: Segment = (12.0, 0.06, 0.30, 0.40)
    drops, _ = play([LOUD, thin_quiet, (12.0, 0.22, 0.90, 0.85)])
    assert drops == []


def test_a_build_that_never_releases_is_not_a_drop():
    top_of_build: Segment = (12.0, 0.25, 0.30, 0.85)
    drops, _ = play([LOUD, INTRO, BUILD, top_of_build])
    assert drops == []


def test_a_build_that_falls_into_a_breakdown_is_not_a_drop():
    """The bass share comes back - a pad is nearly all bass - but the level does
    not hold and the programme is no longer loud."""
    breakdown: Segment = (10.0, 0.03, 0.90, 0.30)
    drops, _ = play([LOUD, INTRO, BUILD, breakdown])
    assert drops == []


def test_a_quiet_build_and_release_is_not_a_drop():
    """The strobe follows this decision, so it still has to be loud."""
    quiet_build: Segment = (12.0, (0.03, 0.25), (0.90, 0.30), 0.45)
    quiet_drop: Segment = (8.0, 0.21, 0.90, 0.45)
    drops, _ = play([LOUD, INTRO, quiet_build, quiet_drop])
    assert drops == []


def test_a_steady_groove_whose_bass_comes_and_goes_is_not_a_drop():
    phrases: List[Segment] = []
    for i in range(12):
        phrases.append((4.0, 0.22, 0.85 if i % 2 else 0.55, 0.50))
    drops, _ = play(phrases)
    assert drops == []


def test_the_release_path_respects_the_refractory():
    """A second bass return inside the refractory cannot re-trigger."""
    again: List[Segment] = [(1.0, 0.25, 0.30, 0.85), (2.0, 0.21, 0.90, 0.85)]
    drops, _ = play([LOUD, INTRO, BUILD, (1.5, 0.21, 0.90, 0.85)] + again)
    assert len(drops) == 1


# ---------------------------------------------------------------------------
# Real audio, one continuous run through the analyser and the venue engine
# ---------------------------------------------------------------------------

def _sequence(name: str, parts: List[SA.SyntheticTrack]) -> Tuple[SA.SyntheticTrack, List[float]]:
    """Tracks back to back as one track, and where each true drop falls."""
    chunks, drops, offset = [], [], 0
    for part in parts:
        n = (len(part.samples) // SA.CHUNK_SIZE) * SA.CHUNK_SIZE
        chunks.append(np.asarray(part.samples[:n], dtype=np.float32))
        if part.drop_sample is not None:
            drops.append((offset + int(part.drop_sample)) / float(part.sample_rate))
        offset += n
    track = SA.SyntheticTrack(
        name=name, samples=np.concatenate(chunks), sample_rate=parts[0].sample_rate,
        bpm=parts[0].bpm, beat_samples=(),
    )
    return track, drops


def _drop_entries(result: M.RunResult) -> List[float]:
    return [t for t, name in M.section_timeline(result) if name == "drop"]


async def _run(name: str, parts: List[SA.SyntheticTrack]):
    track, drops = _sequence(name, parts)
    result = await M.run_track(track, engine=M.build_venue_engine())
    return _drop_entries(result), drops


def _caught(entries: List[float], drop: float) -> bool:
    return any(drop - 1.0 <= t < drop + 4.0 for t in entries)


async def test_the_drop_track_after_dense_music_is_caught_in_the_engine():
    """The assessment's miss: 14 s of loud music on a fresh boot, then the drop."""
    entries, drops = await _run(
        "dense_then_drop",
        [SA.dense_loud_track(bpm=128.0, duration_s=14.0), SA.intro_build_drop_track()],
    )
    assert _caught(entries, drops[0]), f"drop at {drops[0]:.1f} s; engine named drops at {entries}"
    assert all(_caught([t], drops[0]) for t in entries), f"a drop that is not there: {entries}"


async def test_a_short_build_at_another_tempo_after_dense_music_is_caught():
    entries, drops = await _run(
        "dense_then_short_build",
        [SA.dense_loud_track(bpm=128.0, duration_s=20.0), SA.intro_build_drop_track(bpm=100.0, build_bars=8)],
    )
    assert _caught(entries, drops[0]), f"drop at {drops[0]:.1f} s; engine named drops at {entries}"


async def test_dense_and_quiet_material_without_a_build_draws_no_drop():
    entries, _ = await _run(
        "dense_quiet_dense",
        [SA.dense_loud_track(bpm=128.0, duration_s=20.0), SA.sparse_quiet_track(),
         SA.dense_loud_track(bpm=128.0, duration_s=20.0)],
    )
    assert entries == []
