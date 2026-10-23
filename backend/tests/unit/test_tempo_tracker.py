"""
Unit Tests for the Tempo Tracker
================================

The tracker has to count the tempo an operator would count, on the drum
patterns that used to read at the wrong metrical level, and has to stay quiet
when there is nothing to count.
"""

import numpy as np
import pytest

from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.audio.tempo_tracker import TempoTracker
from tests.musical import synthetic_audio as SA


def _stream(tracker: TempoTracker, samples: np.ndarray, chunk: int = SA.CHUNK_SIZE):
    for start in range(0, len(samples) - chunk + 1, chunk):
        tracker.push(samples[start:start + chunk])
    return tracker.bpm, tracker.confidence


@pytest.mark.parametrize("style", sorted(SA.DRUM_PATTERNS))
def test_counts_the_operator_tempo(style):
    track = SA.drum_pattern_track(style, bars=16)
    bpm, confidence = _stream(TempoTracker(track.sample_rate), track.samples)

    assert bpm is not None, f"{style}: no tempo published"
    assert abs(bpm / track.bpm - 1.0) < 0.03, f"{style}: {bpm:.1f} for {track.bpm:.1f}"
    assert confidence >= TempoTracker.MIN_CONFIDENCE


def test_works_at_48_khz():
    track = SA.drum_pattern_track("dnb", bars=16, sample_rate=48000)
    bpm, _ = _stream(TempoTracker(48000), track.samples)

    assert bpm is not None
    assert abs(bpm / track.bpm - 1.0) < 0.03


def test_a_pad_with_no_drums_publishes_no_tempo():
    rng = SA._rng(3)
    pad = SA._normalise(SA._pad(SA.SAMPLE_RATE * 12, SA.SAMPLE_RATE, rng))
    bpm, confidence = _stream(TempoTracker(), pad.astype(np.float32))

    assert bpm is None
    assert confidence == 0.0


def test_noise_publishes_no_tempo():
    noise = np.random.default_rng(11).normal(0.0, 0.1, SA.SAMPLE_RATE * 12)
    bpm, _ = _stream(TempoTracker(), noise.astype(np.float32))

    assert bpm is None


def test_silence_publishes_no_tempo():
    bpm, confidence = _stream(TempoTracker(), np.zeros(SA.SAMPLE_RATE * 10, dtype=np.float32))

    assert bpm is None
    assert confidence == 0.0


def test_reset_forgets_the_tempo():
    track = SA.drum_pattern_track("house", bars=12)
    tracker = TempoTracker(track.sample_rate)
    _stream(tracker, track.samples)
    assert tracker.bpm is not None

    tracker.reset()

    assert tracker.bpm is None
    assert tracker.confidence == 0.0


def test_a_short_break_does_not_move_the_tempo():
    track = SA.drum_pattern_track("hiphop", bars=16)
    tracker = TempoTracker(track.sample_rate)
    _stream(tracker, track.samples)
    held = tracker.bpm

    # One second of a different, faster pattern: a fill, not a new song.
    fill = SA.drum_pattern_track("dnb", bars=1).samples[: SA.SAMPLE_RATE]
    _stream(tracker, fill)

    assert tracker.bpm == pytest.approx(held, rel=0.03)


async def test_the_analyzer_publishes_the_tracked_tempo_and_its_confidence():
    track = SA.drum_pattern_track("hiphop", bars=16)
    analyzer = AudioAnalyzer()
    beat = None
    for _, chunk in SA.iter_chunks(track):
        beat = (await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32)))["beat"]

    assert beat["bpm"] == pytest.approx(track.bpm, rel=0.03)
    assert beat["tempo_confidence"] >= TempoTracker.MIN_CONFIDENCE
