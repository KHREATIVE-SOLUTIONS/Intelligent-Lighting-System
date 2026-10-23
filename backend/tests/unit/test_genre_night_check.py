"""
Unit Tests for the Genre Night Check
====================================

Before the genre model may steer a show it is checked on real nights: its
answers are logged with clips of what it heard, the operator marks what was
really playing, and the night is scored. During a check the model only
listens unless the box was set to let it steer.
"""

import asyncio
import json
import wave

import numpy as np
import pytest

from app.services.effects import effects_engine as E
from app.services.ml import genre_night_check as G
from app.services.ml.genre_classifier import GenreResult
from tests.musical import metrics as M


def _result(style, confidence=0.8):
    return GenreResult(genre=style, genre_confidence=confidence, genre_scores={style: 0.5})


def _night(tmp_path, clip_every_s=60.0):
    check = G.GenreNightCheck(data_dir=tmp_path, clip_every_s=clip_every_s)
    check.start(now=1000.0)
    return check


def test_the_adoption_rule_matches_the_engines():
    assert G.ADOPT_MIN_CONFIDENCE == E._CLUB_STYLE_MIN_CONFIDENCE
    assert G.ADOPT_VOTES == E._CLUB_STYLE_VOTES


def test_guesses_and_marks_are_logged_in_order(tmp_path):
    check = _night(tmp_path)
    check.mark("house", now=1001.0)
    check.record(_result("house"), mood={"label": "happy"}, now=1005.0)
    check.mark("techno", since_s=30.0, now=1100.0)
    check.stop(now=1200.0)

    entries = G.read_log(tmp_path / "genre_check" / check_night(tmp_path))
    kinds = [e["kind"] for e in entries]
    assert kinds == ["start", "mark", "guess", "mark", "stop"]
    assert entries[3]["t"] == pytest.approx(1070.0)  # backdated
    assert entries[2]["mood"] == {"label": "happy"}


def check_night(tmp_path):
    return G.list_nights(tmp_path)[-1]


def test_a_mark_cannot_be_backdated_more_than_ten_minutes(tmp_path):
    check = _night(tmp_path)
    entry = check.mark("house", since_s=10_000, now=5000.0)
    assert entry["t"] == pytest.approx(5000.0 - G.MAX_BACKDATE_S)


def test_only_known_styles_can_be_marked(tmp_path):
    check = _night(tmp_path)
    with pytest.raises(ValueError):
        check.mark("polka")
    check.mark("not_music")
    check.mark("other")


def test_marking_needs_a_running_check(tmp_path):
    check = G.GenreNightCheck(data_dir=tmp_path)
    with pytest.raises(RuntimeError):
        check.mark("house")


def test_clips_are_saved_now_and_then_not_every_guess(tmp_path):
    check = _night(tmp_path, clip_every_s=60.0)
    window = (0.1 * np.sin(np.linspace(0, 2000, 44100 * 10))).astype(np.float32)
    clipped = [
        "clip" in check.record(_result("house"), window=window, rate=44100, now=1000.0 + 5 * i)
        for i in range(30)
    ]
    assert clipped.count(True) == 3  # 0 s, 60 s and 120 s of 150 s

    clips = sorted((tmp_path / "genre_check" / check.night / "clips").iterdir())
    with wave.open(str(clips[0])) as w:
        assert w.getframerate() == G.CLIP_RATE
        assert w.getnchannels() == 1
        assert w.getnframes() == G.CLIP_RATE * 10


def test_a_torn_last_line_does_not_stop_the_night_being_scored(tmp_path):
    check = _night(tmp_path)
    check.mark("house", now=1001.0)
    check.record(_result("house"), now=1005.0)
    with open(check.path / "log.jsonl", "a") as f:
        f.write('{"t": 1010, "kind": "gu')
    assert G.score(G.read_log(check.path))["judged"] == 1


def _entries(*items):
    """("mark", style) or ("guess", style, confidence), five seconds apart."""
    out = []
    for i, item in enumerate(items):
        if item[0] == "mark":
            out.append({"t": i * 5.0, "kind": "mark", "style": item[1]})
        else:
            out.append({"t": i * 5.0, "kind": "guess", "style": item[1], "confidence": item[2]})
    return out


def test_guesses_are_judged_against_the_latest_mark():
    report = G.score(_entries(
        ("guess", "house", 0.9),              # before any mark: not judged
        ("mark", "house"),
        ("guess", "house", 0.9),
        ("guess", "techno", 0.9),
        ("mark", "techno"),
        ("guess", "techno", 0.6),
        ("guess", "unknown", 0.0),
        ("mark", "not_music"),
        ("guess", "lounge", 0.9),             # under not_music: not judged
    ))
    assert report["guesses"] == 6
    assert report["judged"] == 4
    assert report["not_judged"] == 2
    assert report["accuracy"] == pytest.approx(0.5)
    assert report["by_style"]["house"] == {"marked": 2, "right": 1, "accuracy": 0.5}
    assert report["mistakes"] == {"house -> techno": 1, "techno -> unknown": 1}


def test_show_accuracy_follows_the_engines_three_vote_rule():
    report = G.score(_entries(
        ("mark", "techno"),
        ("guess", "house", 0.7), ("guess", "house", 0.7), ("guess", "house", 0.7),  # adopts house
        ("guess", "techno", 0.9),                                                  # still house
        ("guess", "techno", 0.4),                                                  # unsure: resets
        ("guess", "techno", 0.9), ("guess", "techno", 0.9), ("guess", "techno", 0.9),  # adopts techno
    ))
    # Judged from the first adoption on: house five times (the unsure answer
    # resets the vote but keeps the show in house), then techno once.
    assert report["show_judged"] == 6
    assert report["show_accuracy"] == pytest.approx(1 / 6, abs=1e-3)


def test_engine_and_scorer_adopt_the_same_style_on_the_same_answers():
    from app.services.lighting.genre_profiles import Genre

    answers = [("house", 0.7)] * 2 + [("techno", 0.9)] + [("house", 0.7)] * 3 + \
        [("techno", 0.4)] + [("techno", 0.9)] * 3 + [("lounge", 0.5)] * 4
    engine = M.build_engine()
    engine.set_genre(Genre.EDM, pin=False)
    adopted_by_engine = []
    for seq, (style, conf) in enumerate(answers, start=1):
        engine._apply_ml_data({"genre": {"genre": style, "genre_confidence": conf,
                                         "source": "model", "seq": seq}})
        adopted_by_engine.append(engine._club_style)

    entries = [{"t": 0, "kind": "mark", "style": "techno"}] + [
        {"t": i + 1, "kind": "guess", "style": s, "confidence": c} for i, (s, c) in enumerate(answers)
    ]
    report = G.score(entries)
    right_by_engine = sum(1 for s in adopted_by_engine if s == "techno")
    judged_by_engine = sum(1 for s in adopted_by_engine if s is not None)
    assert report["show_judged"] == judged_by_engine
    assert report["show_accuracy"] == pytest.approx(right_by_engine / judged_by_engine, abs=1e-3)


# --- Listening only -------------------------------------------------------

def test_a_shadow_answer_never_changes_the_show():
    from app.services.lighting.genre_profiles import Genre

    engine = M.build_engine()
    engine.set_genre(Genre.EDM, pin=False)
    palette = engine._current_song_palette
    for seq in range(1, 10):
        engine._apply_ml_data({"genre": {"genre": "rock", "genre_confidence": 0.95,
                                         "source": "shadow", "seq": seq}})
        engine.update(1.0 / 60)
    assert engine._club_style is None
    assert engine.genre_manager.current_genre == Genre.EDM
    assert engine._current_song_palette == palette


class _ListeningModel:
    HEURISTIC_ONLY = False
    steers = False
    interval_s = 0.0
    last_mood = {"label": "exciting", "valence": 0.4, "arousal": 0.7}

    def __init__(self):
        self.last_window = (np.zeros(32000, np.float32), 32000)

    def feed_audio(self, audio, sample_rate):
        pass

    async def classify(self, audio_buffer=None, sample_rate=None):
        return GenreResult(genre="techno", genre_confidence=0.8)


def _chunk(seconds=0.05, rate=44100):
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


async def test_the_analyser_labels_a_listening_model_shadow_and_logs_it(tmp_path):
    from app.services.audio.audio_analyzer import AudioAnalyzer

    check = G.GenreNightCheck(data_dir=tmp_path)
    check.start()
    analyzer = AudioAnalyzer()
    analyzer.set_ml_models(genre_classifier=_ListeningModel())
    analyzer.night_check = check

    await analyzer.process_chunk(_chunk())
    await asyncio.sleep(0.05)
    result = await analyzer.process_chunk(_chunk())
    await asyncio.sleep(0.1)  # the log write runs on a worker thread

    assert result["ml"]["genre"]["source"] == "shadow"
    assert check.guesses == 1
    assert check.last_guess["style"] == "techno"
    assert check.last_guess.get("clip")
    if analyzer._genre_task is not None:
        analyzer._genre_task.cancel()


# --- The API ---------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.endpoints import genre_check
    from app.core.config import settings
    from app.services.audio.audio_analyzer import AudioAnalyzer
    from app.services.ml.club_genre import ClubGenreModel

    weights = tmp_path / "w.pt"
    monkeypatch.setattr(settings, "GENRE_MODEL_PATH", str(weights))
    monkeypatch.setattr(settings, "GENRE_MODEL_ENABLED", False)
    monkeypatch.setattr(G, "_root", lambda data_dir=None: tmp_path / "genre_check")

    def fake_load(self):
        self.loaded = True

    monkeypatch.setattr(ClubGenreModel, "_load_sync", fake_load)
    app = FastAPI()
    app.include_router(genre_check.router, prefix="/api")
    app.state.audio_analyzer = AudioAnalyzer()
    app.state.genre_night_check = G.GenreNightCheck(data_dir=tmp_path)
    client = TestClient(app)
    client.weights = weights
    client.app_state = app.state
    return client


def test_starting_without_the_model_downloaded_says_so(api):
    response = api.post("/api/genre-check/start")
    assert response.status_code == 409
    assert "download_genre_model" in response.json()["detail"]


def test_a_night_through_the_api(api):
    api.weights.write_bytes(b"x")
    status = api.post("/api/genre-check/start").json()
    assert status["active"] and status["model_running"]
    assert status["steering"] is False

    assert api.post("/api/genre-check/mark", json={"style": "house"}).status_code == 200
    assert api.post("/api/genre-check/mark", json={"style": "polka"}).status_code == 422
    assert api.post("/api/genre-check/mark", json={"style": "house", "since_s": 9999}).status_code == 422

    check = api.app_state.genre_night_check
    check.record(_result("house"))
    stopped = api.post("/api/genre-check/stop").json()
    assert stopped["active"] is False
    assert stopped["report"]["judged"] == 1
    assert stopped["report"]["accuracy"] == 1.0
    # The model was only loaded to listen: the analyser gets its old slot back.
    assert not stopped["model_running"]

    nights = api.get("/api/genre-check/nights").json()["nights"]
    assert len(nights) == 1
    assert api.get("/api/genre-check/report").json()["night"] == nights[0]
    assert api.get("/api/genre-check/report", params={"night": "../../etc"}).status_code == 404


def test_marking_before_starting_is_refused(api):
    assert api.post("/api/genre-check/mark", json={"style": "house"}).status_code == 409
