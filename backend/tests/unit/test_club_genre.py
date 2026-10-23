"""
Unit Tests for the Club Genre Model
===================================

The trained genre model (EfficientAT mn10_as, vendored) replaces the spectral
guess the show ignores. It is off by default, runs off the event loop, and what
it names is a club style that leans palette and movement only: energy and
sections still run the show, and strobe, dynamics and the genre profile are
left alone.
"""

import asyncio
import os
import threading
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from app.services.audio.audio_analyzer import AudioAnalyzer  # noqa: E402
from app.services.effects import effects_engine as E  # noqa: E402
from app.services.effects.color_mapper import ColorPalette  # noqa: E402
from app.services.ml import club_genre as CG  # noqa: E402
from app.services.ml.efficientat import MelFrontend, build_mn, count_parameters  # noqa: E402
from app.services.ml.efficientat.frontend import kaldi_mel_banks  # noqa: E402
from app.services.ml.genre_classifier import GenreClassifier, GenreResult  # noqa: E402
from tests.musical import metrics as M  # noqa: E402

WEIGHTS = Path(os.environ.get("GENRE_MODEL_TEST_WEIGHTS", "data/models/efficientat/mn10_as_mAP_471.pt"))


# --- The vendored network --------------------------------------------------

def test_the_mel_filters_match_torchaudios_kaldi_banks():
    kaldi = pytest.importorskip("torchaudio.compliance.kaldi")
    theirs, _ = kaldi.get_mel_banks(128, 1024, 32000, 0.0, 15000, 100.0, -500.0, 1.0)
    assert torch.allclose(kaldi_mel_banks(128, 1024, 32000, 0.0, 15000), theirs, atol=1e-6)


def test_the_network_is_the_published_mn10_as_shape():
    model = build_mn().eval()
    assert count_parameters(model) == 4_876_831
    frontend = MelFrontend().eval()
    with torch.inference_mode():
        spec = frontend(torch.zeros(1, 32000 * 2))
        logits = model(spec.unsqueeze(1))
    assert spec.shape == (1, 128, 200)
    assert logits.shape == (1, 527)


@pytest.mark.skipif(not WEIGHTS.is_file(), reason="genre model weights not downloaded")
def test_the_published_checkpoint_loads_strictly_and_noise_is_not_music():
    model = CG.ClubGenreModel(WEIGHTS)
    asyncio.run(model.load())
    noise = np.random.default_rng(0).normal(0, 0.1, 44100 * 10).astype(np.float32)
    result = model._classify_sync(noise, 44100)
    assert result.genre == "unknown"


# --- Folding AudioSet tags into club styles ---------------------------------

def _probs(**tags):
    p = np.zeros(527, dtype=np.float32)
    p[CG.MUSIC_CLASS] = tags.pop("music", 0.9)
    for index, value in tags.items():
        p[int(index.lstrip("c"))] = value
    return p


def test_a_named_electronic_style_wins_over_generic_electronic():
    # House record: tagged Electronic 0.5 and House 0.3.
    scores = CG.style_scores(_probs(c239=0.5, c240=0.3))
    style, confidence = CG.pick_style(scores, 0.9)
    assert style == "house"
    assert confidence > 0.9  # generic Electronic is not a rival of house


def test_generic_electronic_stays_generic_without_a_clear_subgenre():
    scores = CG.style_scores(_probs(c239=0.5, c240=0.1))
    assert CG.pick_style(scores, 0.9)[0] == "edm"


def test_dubstep_and_drum_and_bass_are_one_bass_style():
    assert CG.pick_style(CG.style_scores(_probs(c242=0.4)), 0.9)[0] == "dnb"
    assert CG.pick_style(CG.style_scores(_probs(c243=0.4)), 0.9)[0] == "dnb"


def test_two_close_styles_give_a_low_confidence():
    scores = CG.style_scores(_probs(c217=0.3, c248=0.28))
    style, confidence = CG.pick_style(scores, 0.9)
    assert style == "hip_hop"
    assert confidence < E._CLUB_STYLE_MIN_CONFIDENCE


def test_no_style_is_named_for_what_is_not_music():
    scores = CG.style_scores(_probs(c240=0.6))
    assert CG.pick_style(scores, 0.1) == ("unknown", 0.0)
    assert CG.pick_style(CG.style_scores(_probs()), 0.9) == ("unknown", 0.0)


def test_mood_tags_become_valence_and_arousal():
    mood = CG.mood_from_probs(_probs(c280=0.6, c276=0.2))
    assert mood["label"] == "exciting"
    assert mood["valence"] > 0 and mood["arousal"] > 0.5
    sad = CG.mood_from_probs(_probs(c278=0.5))
    assert sad["valence"] < 0 and sad["arousal"] < 0


# --- The live model wrapper -------------------------------------------------

class _Loaded(CG.ClubGenreModel):
    """The wrapper with the network replaced by fixed tags."""

    def __init__(self, probs):
        super().__init__("unused.pt")
        self.loaded = True
        self.fixed = probs
        self.threads = []

    def _probs(self, window, rate):
        self.threads.append(threading.get_ident())
        return self.fixed


def _feed(model, seconds, rate=44100, level=0.2):
    block = np.full(2048, level, dtype=np.float32)
    for _ in range(int(seconds * rate / 2048)):
        model.feed_audio(block, rate)


def test_nothing_is_named_before_a_window_has_filled():
    model = _Loaded(_probs(c240=0.6))
    _feed(model, 1.0)
    assert asyncio.run(model.classify()) is None


def test_the_window_keeps_only_the_last_ten_seconds():
    model = _Loaded(_probs(c240=0.6))
    _feed(model, 25.0)
    assert len(model._buffer) == int(model.WINDOW_S * 44100)


async def test_inference_runs_off_the_event_loop():
    model = _Loaded(_probs(c240=0.6))
    _feed(model, 5.0)
    result = await model.classify()
    assert result.genre == "house"
    assert model.threads and model.threads[0] != threading.get_ident()


def test_silence_names_nothing_and_does_not_disturb_the_smoothing():
    model = _Loaded(_probs(c241=0.6))
    _feed(model, 5.0)
    asyncio.run(model.classify())
    before = model._smoothed.copy()
    model._buffer[:] = 0.0
    assert asyncio.run(model.classify()).genre == "unknown"
    assert np.array_equal(model._smoothed, before)


def test_without_weights_the_model_refuses_to_load(tmp_path):
    model = CG.ClubGenreModel(tmp_path / "missing.pt")
    with pytest.raises(FileNotFoundError):
        asyncio.run(model.load())
    assert not model.loaded


# --- Off by default ---------------------------------------------------------

def _manager(monkeypatch, enabled, path):
    from app.core.config import settings
    from app.services.ml.model_manager import ModelManager

    monkeypatch.setattr(settings, "GENRE_MODEL_ENABLED", enabled)
    monkeypatch.setattr(settings, "GENRE_MODEL_PATH", str(path))
    manager = ModelManager()
    asyncio.run(manager._load_genre_classifier())
    return manager


def test_the_flag_is_off_by_default():
    from app.core.config import Settings

    assert Settings.model_fields["GENRE_MODEL_ENABLED"].default is False


def test_with_the_flag_off_the_model_is_never_loaded(monkeypatch, tmp_path):
    loads = []
    monkeypatch.setattr(CG.ClubGenreModel, "_load_sync", lambda self: loads.append(1))
    manager = _manager(monkeypatch, False, tmp_path / "w.pt")
    assert isinstance(manager.genre_classifier, GenreClassifier)
    assert loads == []


def test_with_the_flag_on_but_no_weights_the_heuristic_stays(monkeypatch, tmp_path):
    manager = _manager(monkeypatch, True, tmp_path / "missing.pt")
    assert isinstance(manager.genre_classifier, GenreClassifier)


def test_with_the_flag_on_and_weights_the_model_is_used(monkeypatch, tmp_path):
    def fake_load(self):
        self.loaded = True

    monkeypatch.setattr(CG.ClubGenreModel, "_load_sync", fake_load)
    manager = _manager(monkeypatch, True, tmp_path / "w.pt")
    assert isinstance(manager.genre_classifier, CG.ClubGenreModel)


# --- The analyser -----------------------------------------------------------

class _SlowModel:
    HEURISTIC_ONLY = False
    interval_s = 0.0
    last_mood = {"label": "exciting", "valence": 0.4, "arousal": 0.7}

    def __init__(self):
        self.fed = 0
        self.calls = 0

    def feed_audio(self, audio, sample_rate):
        self.fed += len(audio)

    async def classify(self, audio_buffer=None, sample_rate=None):
        self.calls += 1
        await asyncio.sleep(0.05)
        return GenreResult(top_level="electronic", genre="techno", genre_confidence=0.8)


def _chunk(seconds=0.05, rate=44100):
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


async def test_the_analyser_never_waits_for_the_genre_model():
    model = _SlowModel()
    analyzer = AudioAnalyzer()
    analyzer.set_ml_models(genre_classifier=model)

    first = await analyzer.process_chunk(_chunk())
    assert analyzer._genre_task is not None and model.fed > 0
    assert "genre" not in (first.get("ml") or {})

    await asyncio.sleep(0.1)
    assert model.calls == 1
    result = await analyzer.process_chunk(_chunk())
    genre = result["ml"]["genre"]
    assert genre["genre"] == "techno"
    assert genre["source"] == "model"
    assert genre["seq"] == 1
    assert genre["mood"]["label"] == "exciting"
    analyzer._genre_task.cancel()


# --- The engine: palette and movement only ----------------------------------

def _engine():
    from app.services.lighting.genre_profiles import Genre

    engine = M.build_engine()
    engine.set_genre(Genre.EDM, pin=False)
    return engine


def _answer(engine, style, seq, confidence=0.8):
    engine._apply_ml_data(
        {"genre": {"genre": style, "genre_confidence": confidence, "source": "model", "seq": seq}}
    )


def test_a_style_is_taken_only_after_three_fresh_agreeing_answers():
    engine = _engine()
    _answer(engine, "techno", 1)
    for _ in range(50):  # the same answer repeated on every block is one vote
        _answer(engine, "techno", 2)
    assert engine._club_style is None

    _answer(engine, "techno", 3)
    assert engine._club_style == "techno"
    assert engine._current_song_palette in E._CLUB_STYLE_LOOKS["techno"]["palettes"]


def test_unsure_answers_neither_take_nor_drop_a_style():
    engine = _engine()
    for seq in (1, 2, 3):
        _answer(engine, "house", seq)
    assert engine._club_style == "house"

    for seq in range(4, 10):
        _answer(engine, "techno", seq, confidence=0.4)
        _answer(engine, "unknown", seq + 100, confidence=0.0)
    assert engine._club_style == "house"


def test_a_style_changes_nothing_but_palette_and_movement():
    engine = _engine()
    genre = engine.genre_manager.current_genre
    strobe_genre = getattr(engine.pro_effects.strobe, "_genre", None)
    decision_genre = getattr(engine.decision, "_genre", None)
    strobe_enabled = engine.config.strobe_enabled

    for seq in (1, 2, 3):
        _answer(engine, "hip_hop", seq)

    assert engine._club_style == "hip_hop"
    assert engine.genre_manager.current_genre == genre
    assert getattr(engine.pro_effects.strobe, "_genre", None) == strobe_genre
    assert getattr(engine.decision, "_genre", None) == decision_genre
    assert engine.config.strobe_enabled == strobe_enabled


def test_an_operators_genre_choice_is_not_overridden_by_the_style():
    from app.services.lighting.genre_profiles import Genre

    engine = _engine()
    engine.set_genre(Genre.ROCK)
    palette = engine._current_song_palette
    for seq in (1, 2, 3):
        _answer(engine, "lounge", seq)
    assert engine._club_style is None
    assert engine._current_song_palette == palette


def test_a_new_song_picks_from_the_styles_own_palettes():
    engine = _engine()
    for seq in (1, 2, 3):
        _answer(engine, "techno", seq)
    seen = set()
    for _ in range(4):
        engine._on_song_change()
        seen.add(engine._current_song_palette)
    assert seen == set(E._CLUB_STYLE_LOOKS["techno"]["palettes"])


def test_without_a_style_songs_cycle_every_palette_as_before():
    engine = _engine()
    seen = set()
    for _ in range(len(ColorPalette)):
        engine._on_song_change()
        seen.add(engine._current_song_palette)
    assert seen == set(ColorPalette)


def _run(engine, seconds, bpm=124.0, energy=0.6):
    fps = 60
    beat_s = 60.0 / bpm
    for i in range(int(seconds * fps)):
        t = i / fps
        beat = (t % beat_s) < (1.0 / fps)
        if i % 3 == 0:
            engine.update_audio(energy=energy, bass=energy, mid=energy, high=energy * 0.5,
                                is_beat=beat, beat_number=int(t / beat_s), bpm=bpm,
                                programme_level=0.5)
        engine.update(1.0 / fps)


def test_the_styles_movement_takes_over_at_the_next_pattern_change():
    engine = _engine()
    _run(engine, 4.0)
    assert engine._rebuild_style_speed == 1.0

    for seq in (1, 2, 3):
        _answer(engine, "lounge", seq)
    # Nothing jumps the moment the style is taken.
    assert engine._rebuild_style_speed == 1.0

    look = E._CLUB_STYLE_LOOKS["lounge"]
    _run(engine, 40.0)
    assert engine._rebuild_style_speed == pytest.approx(look["speed"])
    assert engine._rebuild_style_amp == pytest.approx(look["amp"])
