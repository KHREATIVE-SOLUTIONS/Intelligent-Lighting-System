"""
Unit Tests for the Audio-Loss Hold
==================================

Music that stops *arriving* (cable pulled, capture thread dead) holds a dim
ambient look. Music that stops *playing* (silence still arriving) stays dark,
and an operator who stops the input on purpose gets no hold either.
"""

import numpy as np
import pytest

from app.services.effects import effects_engine as E
from tests.musical import metrics as M

FPS = 60
DT = 1.0 / FPS


def _engine():
    engine = M.build_engine()
    assert engine.fixtures.get_fixtures_in_group("all"), "harness engine has no fixtures"
    return engine


def _play(engine, seconds, energy=0.5, audio=True):
    """Step the engine; feed one analysis block every third frame when `audio`."""
    frames = int(round(seconds * FPS))
    dimmers = []
    for i in range(frames):
        if audio and i % 3 == 0:
            beat = (i // 3) % 10 == 0
            engine.update_audio(
                energy=energy, bass=energy, mid=energy, high=energy * 0.6,
                is_beat=beat, beat_number=i // 30, bpm=128.0,
                programme_level=0.5 if energy > 0 else 0.0,
            )
        engine.update(DT)
        dimmers.append([f.dimmer for f in engine.fixtures.get_fixtures_in_group("all")])
    return np.asarray(dimmers)


def test_losing_the_audio_mid_show_holds_an_ambient_look():
    engine = _engine()
    _play(engine, 6.0)
    assert not engine.audio_input_lost

    held = _play(engine, 6.0, audio=False)

    assert engine.audio_input_lost
    settled = held[-60:]
    assert np.allclose(settled, E._AMBIENT_HOLD_LEVEL, atol=0.02), settled.max()
    # Nothing flashes on the way in: no frame above the stale music's own level.
    assert held.max() <= 1.0
    assert np.all(settled <= E._AMBIENT_HOLD_LEVEL + 0.02)


def test_the_hold_starts_only_after_the_audio_has_been_gone_a_while():
    engine = _engine()
    _play(engine, 6.0)
    _play(engine, E._AUDIO_LOSS_AFTER_S * 0.5, audio=False)
    assert not engine.audio_input_lost


def test_the_show_comes_back_when_the_audio_does():
    engine = _engine()
    _play(engine, 6.0)
    _play(engine, 6.0, audio=False)
    assert engine.audio_input_lost

    _play(engine, E._AMBIENT_FADE_OUT_S + 0.5)

    assert not engine.audio_input_lost
    assert engine._ambient_mix == 0.0


def test_silence_that_keeps_arriving_is_not_a_lost_input():
    engine = _engine()
    _play(engine, 6.0)
    quiet = _play(engine, 6.0, energy=0.0)

    assert not engine.audio_input_lost
    assert quiet[-60:].max() == 0.0


def test_no_hold_before_any_music_was_heard():
    engine = _engine()
    frames = _play(engine, 6.0, audio=False)

    assert not engine.audio_input_lost
    assert frames.max() == 0.0


def test_stopping_the_input_on_purpose_takes_the_room_dark_not_ambient():
    engine = _engine()
    _play(engine, 6.0)

    engine.audio_input_stopped()
    after = _play(engine, 6.0, audio=False)

    assert not engine.audio_input_lost
    assert after[-60:].max() == 0.0


def test_blackout_still_wins_over_the_hold():
    engine = _engine()
    frames = []
    engine.set_dmx_callback(lambda universe, frame: frames.append(list(frame)))
    _play(engine, 6.0)
    _play(engine, 6.0, audio=False)
    assert engine.audio_input_lost

    engine.blackout()
    frames.clear()
    _play(engine, 0.5, audio=False)

    assert frames
    assert engine.output_master == 0.0
