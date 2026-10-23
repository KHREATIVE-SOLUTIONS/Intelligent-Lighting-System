"""
Overnight: Lost Audio, the Demo Rig on a Real Patch, and Silent Failures
========================================================================

/health could not say whether audio was still arriving. A fresh
install sent the demo show to whatever fixtures the venue had on the network.
/health said "healthy" with no database, so the venue could not patch its rig
and nobody was told. And a training session left recording grew without limit.
"""

import time
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import main
from app.core.config import settings
from app.services.dmx.dmx_controller import DMXController
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.ml.training_recorder import TrainingRecorder


def run(engine, seconds, audio=False):
    for frame in range(int(seconds * 60)):
        if audio:
            engine.update_audio(energy=0.9, bass=0.9, is_beat=frame % 30 == 0,
                                beat_number=frame // 30, bpm=120)
        engine.update(1 / 60)


def test_audio_age_is_unknown_until_audio_arrives():
    engine = EffectsEngine()
    run(engine, 1)
    assert engine.audio_age is None


def test_live_audio_is_followed():
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    run(engine, 5, audio=True)
    assert engine.audio_age < EffectsEngine.AUDIO_STALE_S
    assert engine.audio_state.energy > 0.8


def test_lost_audio_is_reported_and_stops_replaying_the_last_beat():
    # The look itself is the ambient hold (test_audio_loss_hold.py); this
    # checks the age /health reads agrees with it.
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    run(engine, 1, audio=True)
    engine.update_audio(energy=1.0, bass=1.0, is_beat=True, bpm=120)

    run(engine, 10)

    assert engine.audio_age > EffectsEngine.AUDIO_STALE_S
    assert engine.audio_input_lost is True
    assert engine.audio_state.is_beat is False


def test_audio_age_resets_when_audio_returns():
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    run(engine, 1, audio=True)
    run(engine, 10)
    run(engine, 1, audio=True)
    assert engine.audio_age < EffectsEngine.AUDIO_STALE_S
    assert engine.audio_input_lost is False


def fake_app():
    return SimpleNamespace(state=SimpleNamespace(effects_engine=None, dmx_controller=DMXController()))


def test_the_demo_rig_stays_off_the_wire(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_RIG_DMX_OUTPUT", False)
    app = fake_app()
    main._install_fixture_manager(app, object(), demo=True)

    main._send_engine_frame(app, 1, [255] * 512)

    assert app.state.dmx_output_held is True
    assert 1 not in app.state.dmx_controller.universes


def test_a_patched_rig_releases_the_hold(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_RIG_DMX_OUTPUT", False)
    app = fake_app()
    main._install_fixture_manager(app, object(), demo=True)
    main._install_fixture_manager(app, object())

    main._send_engine_frame(app, 1, [255] * 512)

    assert app.state.dmx_output_held is False
    assert app.state.dmx_controller.universes[1].data == [255] * 512


def test_the_demo_can_be_sent_on_purpose(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_RIG_DMX_OUTPUT", True)
    app = fake_app()
    main._install_fixture_manager(app, object(), demo=True)
    assert app.state.dmx_output_held is False


@pytest.fixture
def health(monkeypatch):
    monkeypatch.setattr(main, "request_is_authenticated", lambda request: True)
    state = main.app.state
    monkeypatch.setattr(state, "audio_analyzer", object(), raising=False)
    monkeypatch.setattr(state, "effects_engine", SimpleNamespace(
        running=True, _pro_lighting_enabled=False, audio_age=None,
        AUDIO_STALE_S=EffectsEngine.AUDIO_STALE_S), raising=False)
    monkeypatch.setattr(state, "dmx_controller", None, raising=False)
    monkeypatch.setattr(state, "dmx_output_held", False, raising=False)

    def check(database_ready, audio_age=None):
        monkeypatch.setattr(state, "database_ready", database_ready, raising=False)
        state.effects_engine.audio_age = audio_age
        return TestClient(main.app).get("/health")

    return check


def test_health_reports_a_missing_database(health):
    response = health(database_ready=False)
    assert response.status_code == 503
    assert response.json()["services"]["database"] == "unavailable"


def test_health_is_green_with_a_database(health):
    response = health(database_ready=True)
    assert response.status_code == 200
    assert response.json()["services"]["database"] == "connected"


@pytest.mark.parametrize("age,state", [(None, "waiting"), (0.1, "live"), (30.0, "lost")])
def test_health_says_whether_audio_is_arriving(health, age, state):
    assert health(database_ready=True, audio_age=age).json()["services"]["audio_input"] == state


def test_a_forgotten_recording_stops_growing(tmp_path):
    recorder = TrainingRecorder(output_dir=str(tmp_path))
    recorder.MAX_FRAMES = 5
    recorder.start_recording("all_night")
    try:
        for _ in range(12):
            recorder.record_audio(bpm=120, energy=0.5, bass=0.5, mid=0.5, high=0.5)
            recorder.record_lighting(fixtures=[])
            time.sleep(0.002)
        recorder._record_queue.join()
    finally:
        recorder.stop_recording()

    stats = recorder.get_stats()
    assert len(recorder.frames) == 5
    assert stats["full"] is True
    assert stats["dropped_frames"] > 0
