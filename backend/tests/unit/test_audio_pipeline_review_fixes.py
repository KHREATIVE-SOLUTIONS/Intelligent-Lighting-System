"""
Unit Tests for the Audio Pipeline Review Fixes
==============================================

Bugs the review found in the audio path, each of which would quietly spoil an
unattended night: models handed over before they had loaded, MERT inference
holding the event loop, websocket audio analysed at the wrong rate, and a
section manager that never heard the tempo or a new song.
"""

import asyncio
import time

import numpy as np
import pytest

from app.api.endpoints.websocket import _follow_sender_rate
from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.ml.genre_classifier import GenreResult
from app.services.ml.mert_model import EmotionVector, MERTModel
from tests.musical import metrics as M
from tests.musical import synthetic_audio as SA


def _chunk(seconds=0.05, rate=44100):
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class _LoadingManager:
    """A model manager whose models arrive after the analyser was built."""

    loaded = False
    mert_model = None
    structure_analyzer = None
    genre_classifier = None

    def has_model(self, name):
        return False


class _Genre:
    def __init__(self):
        self.calls = 0

    async def classify(self, audio, sample_rate):
        self.calls += 1
        return GenreResult(top_level="electronic", genre="hip_hop", genre_confidence=0.9)


async def test_models_that_finish_loading_after_startup_are_used():
    manager = _LoadingManager()
    analyzer = AudioAnalyzer(manager)

    first = await analyzer.process_chunk(_chunk())
    assert "genre" not in (first.get("ml") or {})

    manager.genre_classifier = _Genre()
    manager.loaded = True
    result = await analyzer.process_chunk(_chunk())

    assert manager.genre_classifier.calls == 1
    assert result["ml"]["genre"]["genre"] == "hip_hop"


class _SlowMert:
    loaded = True

    def __init__(self, seconds):
        self.seconds = seconds

    def feed_audio(self, audio, sample_rate):
        pass

    async def get_emotion(self):
        await asyncio.sleep(self.seconds)
        return EmotionVector(valence=0.7, arousal=0.4)

    def map_to_lighting(self, emotion):
        return None


async def test_mert_inference_never_holds_up_an_audio_block():
    analyzer = AudioAnalyzer()
    analyzer.set_ml_models(mert_model=_SlowMert(0.6))

    started = time.monotonic()
    await analyzer.process_chunk(_chunk())
    assert time.monotonic() - started < 0.3

    await asyncio.sleep(0.8)
    await analyzer.process_chunk(_chunk())
    result = await analyzer.process_chunk(_chunk())

    assert result["ml"]["emotion_vector"]["valence"] == pytest.approx(0.7)
    assert analyzer.current_valence == pytest.approx(0.7)
    if analyzer._mert_task is not None:
        analyzer._mert_task.cancel()


class _BlockingSession:
    def run(self, outputs, feeds):
        time.sleep(0.4)  # a CPU forward pass, holding the GIL-free C side
        return [[np.array([0.5, 0.2, 0.0, 0.1, 0.0, 0.3, 0.2])]]


async def test_mert_inference_runs_off_the_event_loop():
    model = MERTModel()
    model.loaded = True
    model.onnx_session = _BlockingSession()
    ticks = []

    async def ticker():
        end = time.monotonic() + 0.35
        while time.monotonic() < end:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.02)

    emotion, _ = await asyncio.gather(model.get_emotion(), ticker())

    assert emotion.valence == pytest.approx(0.5)
    # The loop kept turning while the model ran.
    assert len(ticks) >= 8


def test_websocket_audio_is_analysed_at_the_rate_the_sender_gives():
    track = SA.drum_pattern_track("house", bars=16, sample_rate=48000)
    analyzer = AudioAnalyzer()
    _follow_sender_rate(analyzer, 48000)

    async def run():
        beat = None
        for _, chunk in SA.iter_chunks(track):
            beat = (await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32)))["beat"]
        return beat

    beat = asyncio.run(run())

    assert analyzer.sample_rate == 48000
    assert beat["bpm"] == pytest.approx(track.bpm, rel=0.03)


@pytest.mark.parametrize("bad", [None, "fast", 0, -44100, 10 ** 9])
def test_an_implausible_sender_rate_is_ignored(bad):
    analyzer = AudioAnalyzer()
    before = analyzer.sample_rate
    _follow_sender_rate(analyzer, bad)
    assert analyzer.sample_rate == before


def test_the_section_manager_counts_the_show_tempo():
    engine = M.build_engine()
    for i in range(20):
        engine.update_audio(energy=0.5, bass=0.5, is_beat=i % 4 == 0, bpm=87.0)
        engine.update(1.0 / 60)

    assert engine.section_manager._bpm == pytest.approx(87.0, rel=0.02)


def test_a_new_song_and_a_stopped_input_forget_the_loudness_reference():
    engine = M.build_engine()
    resets = []
    engine.decision.reset_dynamics = lambda: resets.append(1)

    engine._on_song_change()
    engine.audio_input_stopped()

    assert len(resets) == 2


def test_a_heuristic_genre_guess_is_shown_but_does_not_retune_the_show():
    from app.services.lighting.genre_profiles import Genre

    engine = M.build_engine()
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.EDM)
    guess = {"genre": "ambient", "genre_confidence": 0.95, "source": "heuristic"}
    for _ in range(120):
        engine._apply_ml_data({"genre": guess})
        engine.update(1.0 / 60)

    assert engine.genre_manager.current_genre == Genre.EDM


async def test_the_analyser_labels_the_spectral_genre_guess_as_heuristic():
    from app.services.ml.genre_classifier import GenreClassifier

    classifier = GenreClassifier()
    analyzer = AudioAnalyzer()
    analyzer.set_ml_models(genre_classifier=classifier)
    result = await analyzer.process_chunk(_chunk(seconds=0.5))

    assert result["ml"]["genre"]["source"] == "heuristic"


def _detect(engine, genre, seconds=2.0):
    # A detector that names a genre profile outright. The trained club model
    # names a style instead, which leans palette and movement only; see
    # test_club_genre.py.
    guess = {"genre": genre, "genre_confidence": 0.9}
    for _ in range(int(seconds * 60)):
        engine._apply_ml_data({"genre": guess})
        engine.update(1.0 / 60)


def test_a_detected_genre_replaces_the_startup_default():
    from app.services.lighting.genre_profiles import Genre

    engine = M.build_engine()
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.EDM, pin=False)
    _detect(engine, "rock")

    assert engine.genre_manager.current_genre == Genre.ROCK


def test_a_genre_the_operator_picked_is_not_overridden_by_detection():
    from app.services.lighting.genre_profiles import Genre

    engine = M.build_engine()
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.HIP_HOP)
    _detect(engine, "rock")

    assert engine.genre_manager.current_genre == Genre.HIP_HOP
