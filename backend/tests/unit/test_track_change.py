"""
Unit Tests for Track-Change Detection
=====================================

A DJ mix never goes silent, so a new record has to be heard in the music:
its key, or a tempo that moves and stays moved. A breakdown or a same-key
chorus inside one record must not count.
"""

import numpy as np
import pytest

from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.audio.tempo_tracker import TempoTracker
from app.services.audio.track_change import TrackChangeDetector
from tests.musical import synthetic_audio as SA


def _changes(track, chunk=SA.CHUNK_SIZE):
    detector = TrackChangeDetector(track.sample_rate)
    tempo = TempoTracker(track.sample_rate)
    times = []
    for start in range(0, len(track.samples) - chunk + 1, chunk):
        block = track.samples[start:start + chunk]
        tempo.push(block)
        detector.push(block, tempo.bpm, tempo.confidence)
        if detector.changed:
            times.append((start + chunk) / track.sample_rate)
    return times, detector


def _blend_end_s(track, blend_bars=16, outgoing_bars=40):
    bar_s = 4 * 60.0 / track.bpm
    return SA.LEAD_IN_S + (outgoing_bars + blend_bars) * bar_s


def test_a_blend_into_a_new_key_is_one_new_track():
    track = SA.dj_mix_track()
    times, detector = _changes(track)

    assert len(times) == 1, times
    assert detector.track_id == 1
    # Called by the time the outgoing record has gone, not a phrase later.
    assert track.tempo_change_sample / track.sample_rate < times[0] <= _blend_end_s(track) + 2.0


def test_a_long_blend_is_still_caught_before_it_ends():
    track = SA.dj_mix_track(blend_bars=32)
    times, _ = _changes(track)

    assert len(times) == 1, times
    assert times[0] <= _blend_end_s(track, blend_bars=32)


def test_a_tempo_change_between_records_is_a_new_track():
    track = SA.dj_mix_track(incoming="a_minor_chorus", incoming_bpm=134.0, name="mix_same_key_new_tempo")
    times, _ = _changes(track)

    assert len(times) == 1, times


def test_a_breakdown_and_a_same_key_chorus_are_the_same_track():
    track = SA.song_track(bars=96, breakdown=(40, 56), chorus_bars=(64, 80))
    times, detector = _changes(track)

    assert times == []
    assert detector.track_id == 0


@pytest.mark.parametrize("style", ["house", "hiphop", "dnb"])
def test_drums_with_no_harmony_never_change_track(style):
    times, _ = _changes(SA.drum_pattern_track(style, bars=48))
    assert times == []


def test_quiet_playback_finds_the_same_change():
    track = SA.dj_mix_track().with_gain_db(-12.0)
    times, _ = _changes(track)
    assert len(times) == 1


def test_works_at_48_khz():
    track = SA.dj_mix_track(sample_rate=48000)
    times, _ = _changes(track)
    assert len(times) == 1


def test_transition_rises_before_the_change_is_called():
    track = SA.dj_mix_track()
    detector = TrackChangeDetector(track.sample_rate)
    seen = []
    for start in range(0, len(track.samples) - SA.CHUNK_SIZE + 1, SA.CHUNK_SIZE):
        detector.push(track.samples[start:start + SA.CHUNK_SIZE])
        if detector.changed:
            break
        seen.append(detector.transition)
    assert 0.0 < max(seen) < 1.0


async def test_the_analyzer_publishes_the_track():
    track = SA.dj_mix_track()
    analyzer = AudioAnalyzer()
    ids = set()
    for _, chunk in SA.iter_chunks(track):
        result = await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32))
        ids.add(result["track"]["id"])
    assert ids == {0, 1}
