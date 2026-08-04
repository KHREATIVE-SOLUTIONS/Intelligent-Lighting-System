"""What the show does, measured rather than asserted from memory.

Two kinds of test live here.

**Guards** pass today and must keep passing. They protect the properties the
rest of this phase is most likely to break by accident: silence stays dark,
nothing raises inside the 60 fps path, `no_strobe` remains a complete off
switch, and the harness is genuinely coupled to the engine rather than
modelling it.

**Contract targets** are marked xfail with the measured baseline in the reason.
They encode the behaviour the contract asks for and they fail on today's code.
`xfail_strict` is on (pytest.ini), so a target that starts passing turns the
suite RED until its marker is deleted. That is deliberate: a non-strict marker
makes the acceptance unfalsifiable in both directions — it cannot tell you the
fix landed, and it silently re-absorbs the regression if the fix is later
undone.

Run `pytest tests/musical -s -k baseline_table` to print the whole metric table.
"""

from functools import lru_cache
from typing import Dict, Tuple

import numpy as np
import pytest

from . import metrics as M
from . import synthetic_audio as SA

# Runs are the expensive part (real analyser plus real 60 fps render), so each
# distinct (track, engine configuration) pair is played exactly once.
_RUNS: Dict[Tuple, M.RunResult] = {}


async def run_cached(track: SA.SyntheticTrack, **overrides) -> M.RunResult:
    key = (track.name, round(track.gain_db, 4), tuple(sorted(overrides.items())))
    if key not in _RUNS:
        _RUNS[key] = await M.run_track(track, **overrides)
    return _RUNS[key]


@lru_cache(maxsize=None)
def click_track() -> SA.SyntheticTrack:
    return SA.click_track()


@lru_cache(maxsize=None)
def gain_renders() -> Tuple[SA.SyntheticTrack, ...]:
    return tuple(SA.gain_sweep(click_track()))


@lru_cache(maxsize=None)
def drop_track() -> SA.SyntheticTrack:
    return SA.intro_build_drop_track()


@lru_cache(maxsize=None)
def sparse_track() -> SA.SyntheticTrack:
    return SA.sparse_quiet_track()


@lru_cache(maxsize=None)
def dense_track() -> SA.SyntheticTrack:
    return SA.dense_loud_track()


@lru_cache(maxsize=None)
def tempo_track() -> SA.SyntheticTrack:
    return SA.tempo_change_track()


# ---------------------------------------------------------------------------
# Guards: the harness itself
# ---------------------------------------------------------------------------


def test_synthetic_material_is_reproducible_and_clip_free():
    """Two calls give the same samples, and the whole gain sweep fits."""
    first = SA.click_track()
    second = SA.click_track()
    assert np.array_equal(first.samples, second.samples)
    assert first.beat_samples == second.beat_samples

    for render in SA.gain_sweep(first):
        assert render.peak <= 1.0, f"{render.name} clips at {render.peak:.3f}"
        assert render.beat_samples == first.beat_samples

    loud = first.with_gain_db(9.0)
    assert loud.peak == pytest.approx(first.peak * 10 ** (9.0 / 20.0), rel=1e-4)


def test_gain_renders_are_the_same_performance():
    """The sweep changes level only; the music underneath is identical."""
    quiet, reference, loud = SA.gain_sweep(click_track())
    ratio = 10 ** (-12.0 / 20.0)
    assert np.allclose(quiet.samples, reference.samples * ratio, atol=1e-6)
    assert quiet.beat_times.tolist() == loud.beat_times.tolist()


def test_sparse_and_dense_material_differ_in_programme_loudness():
    """The quiet/dense pair has to differ in RMS, not just in peak."""
    sparse, dense = sparse_track(), dense_track()
    assert dense.rms > sparse.rms * 4.0
    assert dense.peak > sparse.peak


async def test_run_is_deterministic():
    """Same track, two independent runs, identical output on the wire."""
    track = dense_track()
    first = await M.run_track(track)
    second = await M.run_track(track)
    assert first.frame_count == second.frame_count
    assert first.sections == second.sections
    assert np.array_equal(first.intensity, second.intensity)


async def test_harness_reads_the_real_engine_not_a_model():
    """Tightening a real engine limit has to show up in the measured DMX.

    Without this the whole harness could drift into modelling the engine, which
    is how the existing tests/qa harness ended up asserting hand-written
    literals against no engine at all.
    """
    track = dense_track()
    normal = await run_cached(track)
    capped = await run_cached(track, audience_intensity_cap=0.25)

    assert M.dimmer_dynamic_range(normal).p95 > 0.25
    assert float(capped.intensity.max()) <= 0.25 + 1.0 / 255.0
    assert capped.frame_count == normal.frame_count


async def test_every_track_renders_without_raising_in_the_update_path():
    """A dark rig with no traceback is the worst outcome in this codebase."""
    for track in (click_track(), drop_track(), sparse_track(), dense_track(), tempo_track()):
        result = await run_cached(track)
        assert result.frame_count > 0, track.name
        assert result.intensity.shape[1] == len(result.fixture_ids)
        assert np.all(np.isfinite(result.intensity)), track.name
        assert float(result.intensity.min()) >= 0.0
        assert float(result.intensity.max()) <= 1.0


# ---------------------------------------------------------------------------
# Guards: zero floor and strobe safety
# ---------------------------------------------------------------------------


async def test_silence_leaves_the_rig_completely_dark():
    """No input, no light. The zero-floor model is deliberate."""
    result = await run_cached(SA.silence_track())
    assert result.frame_count > 0
    assert float(result.intensity.max()) == 0.0


async def test_silence_after_music_returns_the_rig_to_dark():
    """A running normalisation must not invent light out of digital silence."""
    track = SA.with_silence_tail(click_track(), seconds=3.0)
    result = await run_cached(track)
    music_end = click_track().duration_s
    tail = result.frame_times >= music_end + 1.5
    assert np.any(tail)
    assert float(result.intensity[tail].max()) == 0.0


async def test_no_strobe_is_a_complete_off_switch():
    """Photosensitive epilepsy is a real hazard; this switch cannot be advisory.

    Run on the governed venue engine, because the governor is the thing that
    would re-arm the flag if the switch were only advisory.

    The gain matters. At 0 dB these tracks produce no white flashes under *any*
    posture, so a no_strobe assertion there is vacuous — it passes with every
    policy gate in the codebase deleted. Each track is therefore first shown to
    flash under the permissive posture, and only then switched off.
    """
    for track in (drop_track(), dense_track()):
        render = track.with_gain_db(9.0)

        permissive = await M.run_track(
            render, engine=M.build_venue_engine(accessibility_mode="performance")
        )
        assert M.white_flash_times(permissive).size > 0, (
            f"{render.name}: nothing flashes even when allowed, so switching it "
            f"off proves nothing"
        )

        off = await M.run_track(
            render, engine=M.build_venue_engine(accessibility_mode="no_strobe")
        )
        assert M.strobe_frame_fraction(off) == 0.0, render.name
        assert M.white_flash_times(off).size == 0, render.name


async def test_strobe_never_exceeds_the_venue_hz_cap():
    """Standing bound on flash rate, on the machine the venue actually runs.

    Measured against `VENUE_ENGINE_KWARGS["strobe_hz_cap"]` (3.0 Hz, what
    main.py configures) rather than `EffectsConfig()`'s 24.0 Hz default, and
    through the accent governor. Asserting the default would have let the venue
    posture drift 8x without a test noticing.
    """
    cap = float(M.VENUE_ENGINE_KWARGS["strobe_hz_cap"])
    for track in (drop_track(), dense_track(), click_track(), tempo_track()):
        for gain_db in (0.0, 9.0):
            render = track.with_gain_db(gain_db) if gain_db else track
            result = await M.run_track(render, engine=M.build_venue_engine())
            rate = M.peak_flash_rate_hz(result)
            assert rate <= cap, (
                f"{render.name}: {rate} Hz exceeds the configured {cap} Hz cap"
            )


async def test_an_unrecognised_accessibility_posture_fails_closed():
    """A typo in a venue file must not buy a higher flash ceiling.

    `accessibility_mode` is a free-text field. An unknown value used to fall
    through to the 24 Hz hard ceiling — the most permissive posture — so an
    empty string, a trailing space or a name from a newer build silently
    granted 8x the conservative limit.
    """
    from app.services.effects.effects_engine import EffectsConfig
    from app.services.lighting.pro_effects import AccentGovernor, ProStrobe

    conservative_hz = 3.0
    conservative_duty = 0.34
    for mode in ("", "  ", "reduced_flash", "CONSERVATIVE ", "typo_mode", None):
        config = EffectsConfig(
            strobe_enabled=True, accessibility_mode=mode, strobe_hz_cap=999.0,
            strobe_max_duty_cycle=0.99,
        )
        governor = AccentGovernor(ProStrobe())
        governor.tick(now=0.0, delta_time=1 / 60.0, energy=0.5, bass=0.5,
                      section="verse", config=config)
        assert config.strobe_hz_cap <= conservative_hz, (
            f"posture {mode!r} allowed {config.strobe_hz_cap} Hz"
        )
        assert config.strobe_max_duty_cycle <= conservative_duty, (
            f"posture {mode!r} allowed duty {config.strobe_max_duty_cycle}"
        )
        assert governor.telemetry.faults == 0


async def test_a_steady_noise_floor_is_not_normalised_up_to_mid_scale():
    """An AGC normalises *any* steady input to mid scale by construction.

    The reference floor is the only thing that decides what counts as programme
    at all, so with it set too low a paused player on a Stereo Mix or mic device
    presents a room-tone noise floor and the normalised value settles at ~0.5 —
    a fully lit rig with no music. Silence here is a realistic noise floor, not
    the exact digital zeros the guard above uses, because multiplying by zero is
    the one case that rescues itself.
    """
    from app.services.audio.audio_analyzer import AudioAnalyzer

    analyzer = AudioAnalyzer()
    rng = np.random.default_rng(11)
    chunk_n = SA.CHUNK_SIZE
    for level_dbfs in (-70.0, -60.0):
        analyzer = AudioAnalyzer()
        amplitude = 10.0 ** (level_dbfs / 20.0)
        for _ in range(int(30.0 * analyzer.sample_rate / chunk_n)):
            noise = (rng.standard_normal(chunk_n) * amplitude).astype(np.float32)
            await analyzer.process_chunk(noise)
        assert analyzer.normalized_energy <= 0.05, (
            f"{level_dbfs} dBFS room tone normalised to "
            f"{analyzer.normalized_energy:.3f} after 30 s of no music"
        )


async def test_beat_timing_survives_quiet_material():
    """The beat detector's RMS gate is a noise gate, not the loudness gate.

    Pointing it at LOUDNESS_GATE_HIGH drops it ~10 dB and lets junk onsets
    through on quiet input. It is a no-op at 0 dB, where the median-relative
    term dominates, so a test written only at 0 dB cannot see the regression.
    """
    for track, gain_db, worst_bound in (
        (sparse_track(), -12.0, 90.0),
        (click_track(), -24.0, 90.0),
    ):
        render = track.with_gain_db(gain_db)
        result = await run_cached(render)
        error = M.detected_beat_error(result, render, warmup_s=6.0)
        assert error.count > 20, error.as_dict()
        assert error.worst_ms <= worst_bound, (
            f"{render.name}: {error.as_dict()}"
        )


# ---------------------------------------------------------------------------
# Contract section 1: loudness normalisation
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="contract 1: section decisions are level-driven. Baseline frame-wise "
           "agreement on the click track: -12 vs 0 dB = 1.000, 0 vs +9 dB = 0.577, "
           "-12 vs +9 dB = 0.577. Remove this marker when normalisation lands.",
)
async def test_section_decisions_are_gain_invariant():
    """The same track at -12, 0 and +9 dB has to light the same way."""
    runs = [await run_cached(render) for render in gain_renders()]
    labels = [f"{render.gain_db:+g}dB" for render in gain_renders()]

    agreements = {}
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            agreements[f"{labels[i]} vs {labels[j]}"] = M.section_agreement(runs[i], runs[j])

    worst = min(agreements.values())
    assert worst >= 0.95, (
        f"section decisions move with level: {agreements}\n"
        + "\n".join(f"{label}: {M.section_timeline(run)}" for label, run in zip(labels, runs))
    )


async def test_normalised_loudness_is_published_alongside_the_raw_value():
    result = await run_cached(click_track())
    assert result.normalised_energy is not None
    assert np.nanmax(result.normalised_energy) > 0.0


async def test_normalised_loudness_reaches_the_ui_and_recorder_payloads():
    """The internal process_chunk dict is not the path anything reads.

    `get_frequency_info()` is the /audio/frequency body and
    `get_current_analysis()` is what main.py broadcasts to the UI. A value that
    only exists on the internal dict is not published, so this asserts on the
    two schema objects rather than on the dict the test above sees.
    """
    from app.services.audio.audio_analyzer import AudioAnalyzer

    analyzer = AudioAnalyzer()
    track = click_track()
    analyzer.sample_rate = track.sample_rate
    for _, chunk in SA.iter_chunks(track):
        await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32))

    freq = analyzer.get_frequency_info()
    assert hasattr(freq, "normalized_energy"), "FrequencyResponse drops the normalised value"
    assert freq.normalized_energy > 0.0
    assert freq.rms_energy > 0.0
    # Published alongside, not instead of: the recorder still reads rms_energy.
    assert freq.normalized_energy != freq.rms_energy

    analysis = analyzer.get_current_analysis()
    assert analysis.frequency.normalized_energy > 0.0


@pytest.mark.xfail(
    reason="contract 1: with raw RMS driving the ladder the engine never reaches the "
           "buildup threshold (0.58) on a mastered reference render. Baseline energy "
           "on the 0 dB click track: p50 0.069, p95 0.384.",
)
async def test_a_mastered_reference_render_reaches_the_high_energy_sections():
    """Verse for the whole night is the complaint; this is the measurement."""
    result = await run_cached(click_track())
    occupancy = M.section_occupancy(result)
    lively = sum(occupancy.get(name, 0.0) for name in ("buildup", "chorus", "drop"))
    assert lively >= 0.15, f"section occupancy {occupancy}"


# ---------------------------------------------------------------------------
# Contract section 2: phase lock
# ---------------------------------------------------------------------------


async def test_engine_beat_phase_tracks_the_real_beat():
    result = await run_cached(click_track())
    error = M.beat_phase_error(result, click_track())
    assert error.count > 20
    assert error.mean_ms <= 25.0, error.as_dict()
    assert error.worst_ms <= 60.0, error.as_dict()


@pytest.mark.xfail(
    reason="contract 2: the downbeat is a counter seeded by whichever onset was "
           "detected first. Baseline bar phase error on the click track: mean "
           "495.6 ms (0.272 of a bar), worst 767.6 ms.",
)
async def test_bar_phase_lands_on_real_downbeats():
    """The louder kick on beat one makes the true downbeat inferable from audio."""
    result = await run_cached(click_track())
    error = M.bar_phase_error(result, click_track())
    assert error.count > 5
    assert error.mean_ms <= 60.0, error.as_dict()


async def test_beat_phase_survives_a_tempo_change():
    """Phase is re-acquired after a tempo change.

    Scoped to two seconds after the change, which is the re-lock allowance.
    The excursion *inside* that allowance is a separate measurement below, so
    the number this test excludes is not left unstated.
    """
    track = tempo_track()
    result = await run_cached(track)
    change_s = track.tempo_change_sample / track.sample_rate
    error = M.beat_phase_error(result, track, warmup_s=change_s + 2.0)
    assert error.count > 5
    assert error.mean_ms <= 25.0, error.as_dict()
    assert error.worst_ms <= 60.0, error.as_dict()


@pytest.mark.xfail(
    reason="contract 2: the clock re-locks after a tempo change but overshoots "
           "during it, and the acceptance bound is stated for the whole track. "
           "Baseline on the 128->150 BPM track measured across the change: mean "
           "16.1 ms, worst 128.6 ms against the 60 ms bound; the worst beat lies "
           "in the two seconds at the change that the scoped test above skips.",
)
async def test_beat_phase_holds_through_the_tempo_change_itself():
    track = tempo_track()
    result = await run_cached(track)
    error = M.beat_phase_error(result, track)
    assert error.count > 5
    assert error.worst_ms <= 60.0, error.as_dict()


# ---------------------------------------------------------------------------
# Contract section 3: one section detector
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="contract 3: the live ladder has no hysteresis or minimum hold. Baseline "
           "on the sparse quiet track: 77.5 section changes per minute, shortest "
           "hold 0.033 s (two frames).",
)
async def test_section_detector_does_not_flap():
    result = await run_cached(sparse_track())
    changes = M.section_changes_per_minute(result)
    shortest = M.shortest_section_hold_s(result)
    assert changes <= 20.0, M.section_timeline(result)
    assert shortest >= 0.75, M.section_timeline(result)


@pytest.mark.xfail(
    reason="contract 3: on a quiet-intro/build/drop track the live detector reports "
           "verse for 99.5% of the run and never reaches drop or buildup.",
)
async def test_intro_build_drop_is_reported_as_that_shape():
    track = drop_track()
    result = await run_cached(track)
    latency = M.drop_section_latency_ms(result, track, targets=("drop", "chorus"))
    occupancy = M.section_occupancy(result)

    assert latency is not None, M.section_timeline(result)
    assert latency <= 2000.0, latency
    assert occupancy.get("buildup", 0.0) > 0.02, occupancy


# ---------------------------------------------------------------------------
# Contract section 4: drops have to land
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="contract 4: the drop never produces a material step in emitted level. "
           "Baseline on the drop track: no 0.15 step ever occurs, and the largest "
           "rise in the two seconds after the drop is 0.077.",
)
async def test_the_drop_lands_in_the_output():
    track = drop_track()
    result = await run_cached(track)
    latency = M.drop_latency_ms(result, track)
    step = M.drop_intensity_step(result, track)
    assert latency is not None, f"output never moved; step was {step}"
    assert latency <= 250.0, latency


@pytest.mark.xfail(
    reason="contract 4: strobe is disabled in three places, so a drop is the same "
           "colour and the same chase with the dimmer slightly higher. Baseline "
           "accent count in the four seconds after the drop: 0.",
)
async def test_the_drop_gets_an_accent():
    """An accent means something discrete: a flash, a bump or a hole in the light."""
    track = drop_track()
    result = await run_cached(track)
    window = result.between(track.drop_time, track.drop_time + 4.0)
    assert window.frame_count > 0

    accents = M.accent_events(window)
    assert accents.total >= 1, (
        f"the drop is rendered as more of the same: {accents.as_dict()}, "
        f"peak rig level {float(window.rig_mean.max()):.3f}"
    )


# ---------------------------------------------------------------------------
# Contract section 5: dynamics
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="contract 5: dimmer is energy times one scalar per section, so the rig "
           "has almost no contrast. Baseline p95-p5 of emitted intensity: 0.224 on "
           "the drop track, 0.051 on the sparse quiet track.",
)
async def test_dimmer_dynamic_range_is_wide_enough_to_read():
    result = await run_cached(drop_track())
    spread = M.dimmer_dynamic_range(result)
    assert spread.spread >= 0.45, spread.as_dict()


@pytest.mark.xfail(
    reason="contract 5: a quiet passage gets no shaping of its own, only a smaller "
           "multiple of a small energy. Baseline p95-p5 on the sparse quiet track: "
           "0.051.",
)
async def test_a_quiet_passage_still_has_internal_contrast():
    result = await run_cached(sparse_track())
    spread = M.dimmer_dynamic_range(result)
    assert spread.spread >= 0.20, spread.as_dict()


# ---------------------------------------------------------------------------
# The table every later claim cites
# ---------------------------------------------------------------------------


async def test_baseline_table():
    """Print every headline metric for every track, and check they are real.

    This is the report, not a threshold. It exists so that anyone changing the
    engine can run one command and put the same numbers next to the ones in
    this phase's baseline.
    """
    cases = [(render, {}) for render in gain_renders()]
    cases += [
        (drop_track(), {}),
        (sparse_track(), {}),
        (dense_track(), {}),
        (tempo_track(), {}),
    ]

    print()
    for track, overrides in cases:
        result = await run_cached(track, **overrides)
        summary = M.summarise(result, track)
        print(M.format_summary(summary))

        assert summary["frames"] > 0
        assert summary["fixtures"] > 0
        assert np.isfinite(summary["beat_phase_error"]["mean_ms"])
        assert np.isfinite(summary["dynamic_range"]["p95"])
        assert summary["section_changes_per_min"] >= 0.0
