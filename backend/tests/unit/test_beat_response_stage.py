"""
The beat response stage of the live renderer
============================================

Beat pulse plus output make-up gain, the last stage of the dimmer chain in
`EffectsEngine._update_fixtures_rebuild`. These drive the engine directly with
hand-made analysis frames (no analyser, no audio, no DMX) and read the fixture
levels it renders. The full analyser-to-light measurement on a generated track
is tests/musical/test_beat_response.py.
"""

import numpy as np

from app.services.demo.venue_presets import create_venue_rig
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine

FPS = 60
DT = 1.0 / FPS


def _engine(**overrides) -> EffectsEngine:
    kwargs = dict(fps=60.0, auto_mode=True, movement_enabled=True, dimmer_enabled=True,
                  strobe_enabled=False, accessibility_mode="conservative", strobe_hz_cap=3.0)
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    engine.enable_pro_lighting(True)
    return engine


def _run(engine, seconds, *, energy=0.3, beat_every=28, section="verse", audio=True):
    """Feed a block of analysis every frame with a beat every `beat_every` frames.

    Returns (rig mean per frame, per-fixture dimmers per frame).
    """
    engine._force_section(section, 1e9)
    means, levels = [], []
    start = int(round(engine.time * FPS))
    for k in range(int(round(seconds * FPS))):
        i = start + k
        if audio:
            engine.update_audio(energy=energy, bass=energy, mid=energy * 0.8, high=energy * 0.5,
                                is_beat=(energy > 0 and i % beat_every == 0),
                                beat_number=i // beat_every, bpm=60.0 * FPS / beat_every)
        engine.update(delta_time=DT)
        row = [f.dimmer for f in engine.fixtures.fixtures.values()]
        levels.append(row)
        means.append(float(np.mean(row)))
    return np.asarray(means), np.asarray(levels)


def _per_beat_swing(means, beat_every):
    swings = []
    for s in range(0, len(means) - beat_every, beat_every):
        window = means[s:s + beat_every]
        swings.append(float(window.max() - window.min()))
    return np.asarray(swings)


def test_the_stage_lifts_the_rig_and_puts_the_beat_in_it():
    off = _engine(beat_pulse_enabled=False, output_makeup_gain_enabled=False)
    on = _engine()
    off_means, _ = _run(off, 12.0)
    on_means, _ = _run(on, 12.0)
    tail = slice(8 * FPS, None)

    assert on_means[tail].mean() > off_means[tail].mean() * 1.5, (
        on_means[tail].mean(), off_means[tail].mean())
    assert on_means[tail].mean() <= on.config.makeup_target + 0.1
    assert np.median(_per_beat_swing(on_means[tail], 28)) > 1.5 * np.median(_per_beat_swing(off_means[tail], 28))
    assert on.beat_pulse_count > 0
    assert 1.0 < on.makeup_gain_applied <= on.config.makeup_gain_max


def test_switched_off_the_stage_does_nothing():
    engine = _engine(beat_pulse_enabled=False, output_makeup_gain_enabled=False)
    _run(engine, 6.0)
    assert engine.beat_pulse_count == 0
    assert engine.beat_pulse_depth == 0.0
    assert engine.makeup_gain_applied == 1.0


def test_the_gain_is_bounded():
    engine = _engine(makeup_gain_max=2.0)
    _run(engine, 10.0, energy=0.05)
    assert 1.0 <= engine.makeup_gain_applied <= 2.0 + 1e-9


def test_silence_gets_no_gain_and_no_pulse():
    engine = _engine()
    _run(engine, 6.0)
    means, _ = _run(engine, 4.0, energy=0.0)
    assert engine._makeup_mix == 0.0
    assert engine.makeup_gain_applied == 1.0
    assert engine.beat_pulse_depth == 0.0
    assert float(means[2 * FPS:].max()) == 0.0


def test_a_paused_feed_stands_the_stage_down():
    """WASAPI loopback sends no blocks at all while nothing plays."""
    engine = _engine()
    _run(engine, 6.0)
    # The locked beat clock may still land the one beat it had already
    # predicted inside the freshness window; after that nothing fires.
    count = engine.beat_pulse_count
    _run(engine, 0.5, audio=False)
    assert engine.beat_pulse_count <= count + 1
    count = engine.beat_pulse_count
    _run(engine, 1.5, audio=False)
    assert engine._makeup_mix == 0.0
    assert engine.beat_pulse_count == count


def test_pulses_never_exceed_three_a_second_even_at_double_time():
    engine = _engine(strobe_hz_cap=24.0)
    fired = []
    engine._force_section("drop", 1e9)
    last = engine.beat_pulse_count
    for i in range(10 * FPS):
        # 240 BPM of beats.
        engine.update_audio(energy=0.4, bass=0.4, mid=0.3, high=0.2, is_beat=(i % 15 == 0),
                            beat_number=i // 15, bpm=240.0)
        engine.update(delta_time=DT)
        if engine.beat_pulse_count != last:
            fired.append(engine._pulse_fired_at)
            last = engine.beat_pulse_count
    assert len(fired) >= 10, "the pulse stopped altogether instead of halving"
    gaps = np.diff(fired)
    assert gaps.min() >= 1.0 / 3.0, gaps.min()
    times = np.asarray(fired)
    assert max(int(np.count_nonzero((times >= t) & (times < t + 1.0))) for t in times) <= 3


def test_no_strobe_pulse_stays_under_the_flash_threshold():
    """Gentle: the pulse alone can never move a fixture by a flash's worth."""
    engine = _engine(accessibility_mode="no_strobe")
    _run(engine, 8.0, energy=0.5, section="drop")
    assert 0.0 < engine.beat_pulse_depth <= EffectsEngine._PULSE_GENTLE_MAX_DEPTH
    assert engine.beat_pulse_count > 0


def test_breakdown_pulse_is_smaller_than_the_drop_pulse():
    a = _engine()
    _run(a, 6.0, section="breakdown")
    b = _engine()
    _run(b, 6.0, section="drop")
    assert 0.0 < a.beat_pulse_depth < b.beat_pulse_depth


def test_the_beat_meter_reports_the_beat():
    engine = _engine()
    _run(engine, 3.0)
    meter = engine.beat_meter()
    assert meter["beat_count"] > 0
    assert meter["bpm"] > 0
    assert meter["seconds_since_beat"] is not None and meter["seconds_since_beat"] < 1.0
    assert meter["pulse_count"] == engine.beat_pulse_count
