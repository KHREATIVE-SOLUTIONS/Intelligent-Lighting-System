"""Do the lights answer the beat, and how late?

A deterministic dense test track is generated in code (no downloads): 128 BPM
four-on-the-floor kick, offbeat hats, an offbeat bass line and a sustained
pad, 48 kHz, 20 s. It is fed in 2048-sample chunks through the real
`AudioAnalyzer.process_chunk`, the same analysis-to-engine mapping main.py
uses, and a real `EffectsEngine` in the venue posture (main.py's config, the
accent governor, the LIV demo rig) with the beat response stage on. The engine
is stepped at 60 fps on a virtual clock, so the run is deterministic and fast.

Causality. A chunk covering samples [i, i+2048) only exists once its last
sample has been captured, at (i+2048)/48000 s. Every engine frame up to that
instant is rendered *before* the chunk is handed to the analyser, so no frame
ever sees audio from its future. `metrics.run_track` renders those frames after
the update and would make latency look up to one chunk better than it is.

What is measured
----------------
* inherent block duration: 2048 / 48000 = 42.7 ms. A kick anywhere inside a
  chunk is not available to the backend until that chunk completes. This is
  reported, never subtracted or hidden.
* added latency: from the moment the chunk containing the kick onset completes
  (the audio becomes available) to the first engine frame where the rig-mean
  pulse is at least half its height. With the beat clock locked the pulse is
  predictive (the clock runs ahead on the tempo it has learned) and this can
  be negative: the light lands on the kick, before the block holding it is
  even complete.
"""

from __future__ import annotations

import os
import time as _walltime
from typing import Dict, List, Optional

import numpy as np
import pytest

from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.demo.venue_presets import create_venue_rig
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine

from . import metrics as M

SR = 48000
CHUNK = 2048
BPM = 128.0
DURATION_S = 20.0
LEAD_IN_S = 0.25
FPS = 60.0
LOCK_IN_S = 4.0
BLOCK_MS = CHUNK / SR * 1000.0

# main.py's posture with the stage on: what the venue runs after this change.
VENUE_REACTIVE = dict(M.VENUE_ENGINE_KWARGS)
VENUE_REACTIVE.update(beat_pulse_enabled=True, output_makeup_gain_enabled=True)


# ---------------------------------------------------------------------------
# The test track
# ---------------------------------------------------------------------------


def dense_track(seed: int = 128128):
    """Samples and kick-onset sample indices. Deterministic, royalty free."""
    rng = np.random.default_rng(seed)
    n = int(DURATION_S * SR)
    out = np.zeros(n, dtype=np.float64)
    beat = 60.0 / BPM
    t_kick = np.arange(int(0.30 * SR)) / SR
    # Kick: a pitch-swept sine with a click.
    sweep = 48.0 + 110.0 * np.exp(-t_kick / 0.035)
    phase = 2.0 * np.pi * np.cumsum(sweep) / SR
    kick = np.sin(phase) * np.exp(-t_kick / 0.16)
    kick[: int(0.002 * SR)] += np.linspace(0.6, 0.0, int(0.002 * SR))
    # Hat: differentiated noise (bright), short.
    t_hat = np.arange(int(0.05 * SR)) / SR
    hat_noise = np.diff(rng.standard_normal(len(t_hat) + 1))
    hat = hat_noise * np.exp(-t_hat / 0.012) * 0.5
    # Bass: a low saw-ish note on each offbeat, ducked under the kick.
    t_bass = np.arange(int(0.22 * SR)) / SR
    notes = (55.0, 55.0, 65.41, 49.0)

    kicks: List[int] = []
    k = 0
    while True:
        t0 = LEAD_IN_S + k * beat
        s0 = int(round(t0 * SR))
        if s0 + len(kick) >= n:
            break
        kicks.append(s0)
        out[s0:s0 + len(kick)] += 0.85 * kick
        off = int(round((t0 + beat / 2.0) * SR))
        if off + len(hat) < n:
            out[off:off + len(hat)] += 0.35 * hat
        if off + len(t_bass) < n:
            f = notes[(k // 4) % len(notes)]
            saw = 2.0 * ((f * t_bass) % 1.0) - 1.0
            env = np.minimum(1.0, t_bass / 0.01) * np.exp(-t_bass / 0.15)
            out[off:off + len(t_bass)] += 0.30 * saw * env
        k += 1
    # Pad: a sustained minor chord with slow movement, under everything.
    t = np.arange(n) / SR
    pad = sum(np.sin(2.0 * np.pi * f * t + p) for f, p in ((220.0, 0.0), (261.63, 1.0), (329.63, 2.0)))
    out += 0.06 * pad * (0.8 + 0.2 * np.sin(2.0 * np.pi * 0.1 * t))
    out *= 0.66 / max(1e-9, float(np.max(np.abs(out))))
    return out.astype(np.float32), np.asarray(kicks, dtype=np.int64)


# ---------------------------------------------------------------------------
# Causal run
# ---------------------------------------------------------------------------


def _venue_engine(**overrides) -> EffectsEngine:
    kwargs = dict(VENUE_REACTIVE)
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    manager, _ = create_venue_rig("liv_miami_approx")
    engine.set_fixture_manager(manager)
    engine.enable_pro_lighting(True)
    from app.services.lighting.genre_profiles import Genre
    engine.set_genre(Genre.EDM)
    from app.services.lighting.pro_effects import attach_accent_governor
    attach_accent_governor(engine)
    return engine


async def run_causal(samples: np.ndarray, *, keep_frames: bool = False, measure_wall: bool = False,
                     **overrides) -> Dict:
    engine = _venue_engine(**overrides)
    analyzer = AudioAnalyzer()
    analyzer.sample_rate = SR
    taps = M._build_taps(engine)
    captured: Dict[int, List[int]] = {}
    engine.set_dmx_callback(lambda u, f: captured.__setitem__(int(u), list(f)))

    clock = M._Clock()
    dt = 1.0 / FPS
    engine_time = 0.0
    times, means, pulse_env, raw_frames = [], [], [], []
    wall_ms: List[float] = []

    with M.virtual_clock(clock):
        for start in range(0, (len(samples) // CHUNK) * CHUNK, CHUNK):
            available_at = (start + CHUNK) / SR
            # Every frame up to the instant this chunk exists, without it.
            while engine_time + dt <= available_at + 1e-9:
                engine_time += dt
                clock.t = engine_time
                captured.clear()
                engine.update(delta_time=dt)
                level, _white = M._read_frame(taps, captured)
                times.append(engine_time)
                means.append(float(level.mean()))
                pulse_env.append(float(engine.beat_pulse_level))
                if keep_frames:
                    raw_frames.append({u: list(f) for u, f in captured.items()})
            clock.t = available_at
            chunk = np.asarray(samples[start:start + CHUNK], dtype=np.float32)
            w0 = _walltime.perf_counter()
            analysis = await analyzer.process_chunk(chunk)
            engine.update_audio(**M.analysis_to_engine_kwargs(analysis))
            if measure_wall:
                wall_ms.append((_walltime.perf_counter() - w0) * 1000.0)

    return {
        "engine": engine,
        "taps": taps,
        "times": np.asarray(times),
        "means": np.asarray(means),
        "pulse_env": np.asarray(pulse_env),
        "frames": raw_frames,
        "wall_ms": np.asarray(wall_ms),
    }


def per_beat(times: np.ndarray, means: np.ndarray, kick_samples: np.ndarray) -> Dict[str, np.ndarray]:
    """For each kick after lock-in: local peak?, swing, latency from availability."""
    beat = 60.0 / BPM
    peaks, swings, latency = [], [], []
    for s in kick_samples:
        onset = s / SR
        if onset < LOCK_IN_S or onset + beat / 2.0 > times[-1]:
            continue
        available = (s // CHUNK + 1) * CHUNK / SR
        hood = (times >= onset - beat / 2.0) & (times < onset + beat / 2.0)
        if not np.any(hood):
            continue
        idx = np.nonzero(hood)[0]
        seg = means[idx]
        i_peak = idx[int(np.argmax(seg))]
        near = onset - 0.06 <= times[i_peak] <= onset + 0.15
        swing = float(seg.max() - seg.min())
        peaks.append(bool(near and swing >= 0.05))
        swings.append(swing)
        # Trough before the peak, then the first frame at half height.
        before = idx[idx <= i_peak]
        i_trough = before[int(np.argmin(means[before]))]
        half = means[i_trough] + 0.5 * (means[i_peak] - means[i_trough])
        rise = np.arange(i_trough, i_peak + 1)
        i_half = rise[np.nonzero(means[rise] >= half)[0][0]]
        latency.append((times[i_half] - available) * 1000.0)
    return {"peak": np.asarray(peaks), "swing": np.asarray(swings), "latency_ms": np.asarray(latency)}


_CACHE: Dict[str, Dict] = {}


async def _measured() -> Dict:
    if "run" not in _CACHE:
        samples, kicks = dense_track()
        run = await run_causal(samples, keep_frames=True)
        run["kicks"] = kicks
        run["beats"] = per_beat(run["times"], run["means"], kicks)
        _CACHE["run"] = run
    return _CACHE["run"]


def _report(run) -> str:
    b = run["beats"]
    lat = b["latency_ms"]
    tail = run["means"][run["times"] >= LOCK_IN_S]
    return (
        f"beats={len(lat)} local_peaks={b['peak'].mean():.3f} "
        f"swing median={np.median(b['swing']):.3f} p10={np.percentile(b['swing'], 10):.3f} "
        f"inherent_block={BLOCK_MS:.1f}ms added_latency median={np.median(lat):.1f}ms "
        f"p90={np.percentile(lat, 90):.1f}ms worst={lat.max():.1f}ms "
        f"rig_mean={tail.mean():.3f} gain={run['engine'].makeup_gain_applied:.2f} "
        f"locked={run['engine']._clock_locked} section={run['engine']._rebuild_section}"
    )


# ---------------------------------------------------------------------------
# The beat, in the light
# ---------------------------------------------------------------------------


def test_the_test_track_is_dense_and_deterministic():
    a, kicks = dense_track()
    b, _ = dense_track()
    assert np.array_equal(a, b)
    assert len(a) == int(DURATION_S * SR)
    assert float(np.max(np.abs(a))) <= 0.67
    assert 0.08 < float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) < 0.35
    assert len(kicks) >= int((DURATION_S - 1.0) * BPM / 60.0)


async def test_the_rig_peaks_on_every_kick():
    run = await _measured()
    print("\n" + _report(run))
    assert len(run["beats"]["peak"]) > 25, _report(run)
    assert run["beats"]["peak"].mean() >= 0.90, _report(run)


async def test_every_beat_swings_the_rig_by_at_least_a_fifth():
    run = await _measured()
    swing = run["beats"]["swing"]
    assert np.mean(swing >= 0.2) >= 0.90, _report(run)


async def test_added_latency_is_under_fifty_ms():
    run = await _measured()
    lat = run["beats"]["latency_ms"]
    print(f"\ninherent block duration {BLOCK_MS:.1f} ms (2048/48000), not included below")
    print(f"added latency median {np.median(lat):.1f} ms, p90 {np.percentile(lat, 90):.1f} ms")
    assert np.mean(lat < 50.0) >= 0.90, _report(run)


async def test_dense_music_lands_in_the_middle_of_the_range():
    run = await _measured()
    tail = run["means"][run["times"] >= 8.0]
    assert 0.30 <= float(tail.mean()) <= 0.70, _report(run)
    assert float(np.percentile(tail, 95) - np.percentile(tail, 5)) >= 0.2, _report(run)


async def test_the_pulse_survives_the_output_stage_flash_limiter():
    """The wire stage (bytes only, nothing sent) must not flatten the beat."""
    from app.services.dmx.output_stage import OutputStage

    run = await _measured()
    engine = run["engine"]
    stage = OutputStage()
    stage.set_flash_policy(*engine.flash_policy())
    stage.set_patch(engine.fixtures.light_patch(), engine.fixtures.strobe_patch())
    staged_means = []
    for t, frames in zip(run["times"], run["frames"]):
        out = stage.process(frames, now=float(t))
        level, _ = M._read_frame(run["taps"], {u: list(f) for u, f in out.items()})
        staged_means.append(float(level.mean()))
    staged = per_beat(run["times"], np.asarray(staged_means), run["kicks"])
    assert np.median(staged["swing"]) >= 0.15, (np.median(staged["swing"]), _report(run))
    assert staged["peak"].mean() >= 0.80


# ---------------------------------------------------------------------------
# The stage, in the venue posture, on the safety properties
# ---------------------------------------------------------------------------


async def test_silence_stays_dark_with_the_stage_on():
    run = await run_causal(np.zeros(int(4.0 * SR), dtype=np.float32))
    assert float(run["means"].max()) == 0.0
    assert run["engine"].beat_pulse_count == 0


async def test_a_noise_floor_stays_dark_with_the_stage_on():
    rng = np.random.default_rng(7)
    for dbfs in (-70.0, -60.0):
        noise = rng.standard_normal(int(6.0 * SR)) * (10.0 ** (dbfs / 20.0))
        run = await run_causal(noise.astype(np.float32))
        assert float(run["means"].max()) <= 0.05, dbfs
        assert run["engine"].makeup_gain_applied == pytest.approx(1.0, abs=1e-6), dbfs


async def test_no_strobe_keeps_the_pulse_below_a_flash():
    samples, _ = dense_track()
    run = await run_causal(samples[: int(8.0 * SR)], accessibility_mode="no_strobe", strobe_enabled=False)
    engine = run["engine"]
    assert engine.beat_pulse_depth <= EffectsEngine._PULSE_GENTLE_MAX_DEPTH + 1e-9
    assert engine.beat_pulse_count > 0


async def test_pulses_respect_the_venue_flash_cap():
    run = await _measured()
    engine = run["engine"]
    env = run["pulse_env"]
    times = run["times"]
    # Rising edges of the envelope are the pulses.
    starts = times[1:][(env[1:] > 0.5) & (env[:-1] <= 0.5)]
    for t in starts:
        assert int(np.count_nonzero((starts >= t) & (starts < t + 1.0))) <= 3
    assert engine.beat_pulse_count > 20


# ---------------------------------------------------------------------------
# Real processing time on this machine
# ---------------------------------------------------------------------------


@pytest.mark.skipif(bool(os.environ.get("SKIP_PERF_TESTS")), reason="wall-clock test; set SKIP_PERF_TESTS on slow CI")
async def test_processing_a_chunk_takes_under_twenty_ms():
    samples, _ = dense_track()
    run = await run_causal(samples[: int(10.0 * SR)], measure_wall=True)
    wall = run["wall_ms"][20:]   # past the analyser's warm-up
    print(f"\nprocess_chunk + update_audio wall time: median {np.median(wall):.2f} ms, "
          f"p95 {np.percentile(wall, 95):.2f} ms")
    assert float(np.median(wall)) < 20.0
