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

import contextlib
from functools import lru_cache
from typing import Dict, Tuple
from unittest import mock

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


@lru_cache(maxsize=None)
def build_without_drop_track() -> SA.SyntheticTrack:
    """The drop track's build, carrying on past the boundary instead of dropping.

    The anticipation path's case is that a build projects onto the phrase grid,
    so the material that can show it is not merely guessing is a build that
    reaches that boundary and continues. Everything before
    `drop_track().drop_time` is the drop track's own audio, so the build is
    recognised in exactly the same place and the projection is made from the
    same anchor; from there the build's last bar repeats, which holds the level,
    the grid and the instrumentation and withholds only the drop.

    `drop_sample` is None on purpose: there is no drop here for anything to be
    late for, and any drop metric asked about this track has to say so.
    """
    source = SA.intro_build_drop_track()
    rate = source.sample_rate
    cut = int(source.drop_sample)
    bar = int(round(4.0 * 60.0 / source.bpm * rate))
    fade = int(round(0.005 * rate))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)

    head = np.asarray(source.samples[:cut], dtype=np.float32).copy()
    head[-fade:] *= ramp[::-1]
    loop = np.asarray(source.samples[cut - bar:cut], dtype=np.float32)
    pieces = [head]
    for _ in range(12):
        segment = loop.copy()
        segment[:fade] *= ramp
        segment[-fade:] *= ramp[::-1]
        pieces.append(segment)

    samples = np.concatenate(pieces).astype(np.float32)
    beat = int(round(60.0 / source.bpm * rate))
    lead = int(source.beat_samples[0])
    return SA.SyntheticTrack(
        name="build_without_drop",
        samples=samples,
        sample_rate=rate,
        bpm=source.bpm,
        beat_samples=tuple(range(lead, len(samples), beat)),
        downbeat_samples=tuple(range(lead, len(samples), beat * 4)),
    )


@lru_cache(maxsize=None)
def build_with_a_false_impact_track() -> SA.SyntheticTrack:
    """Build, one moderate hit on the projected downbeat, then a breakdown.

    `build_without_drop_track` withholds the boundary entirely, so it can only
    ever exercise the dip: nothing happens at bar 16 for a confirmation to look
    at. This is the material that reaches the confirmation and has to be refused
    by it — the build/impact/breakdown that is as much a part of dance music as
    the drop, and the shape a projected downbeat is most likely to be wrong
    about, because the projection is right about *when* and wrong about *what*.

    Everything is this track's own audio: the drop track's build up to the
    boundary, a fifth of a bar of its real drop at a quarter weight as the
    impact, and its intro — a pad at a tenth of full weight with one soft kick a
    bar — as the breakdown underneath. The detector never calls any of it a drop.
    """
    source = SA.intro_build_drop_track()
    rate = source.sample_rate
    cut = int(source.drop_sample)
    lead = int(source.beat_samples[0])
    bar = int(round(4.0 * 60.0 / source.bpm * rate))
    fade = int(round(0.005 * rate))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)

    head = np.asarray(source.samples[:cut], dtype=np.float32).copy()
    head[-fade:] *= ramp[::-1]
    tail = np.asarray(source.samples[lead:lead + 8 * bar], dtype=np.float32).copy()
    tail[:fade] *= ramp
    hit = np.asarray(source.samples[cut:cut + bar // 5], dtype=np.float32) * 0.25
    tail[:hit.size] += hit

    samples = np.concatenate([head, tail]).astype(np.float32)
    beat = int(round(60.0 / source.bpm * rate))
    return SA.SyntheticTrack(
        name="build_with_a_false_impact",
        samples=samples,
        sample_rate=rate,
        bpm=source.bpm,
        beat_samples=tuple(range(lead, len(samples), beat)),
        downbeat_samples=tuple(range(lead, len(samples), beat * 4)),
    )


@lru_cache(maxsize=None)
def two_drop_track() -> Tuple[SA.SyntheticTrack, SA.SyntheticTrack]:
    """The drop track played twice over, on one continuous bar clock.

    A set is not one drop, and nothing else here plays two. The first copy is
    cut on its own bar line so the second starts in phase, which is what makes
    this a test of the anticipation path rather than of the beat clock: the
    grid never moves, only the detector's idea of what is unusual on this track.

    Returned as a pair carrying the same audio and the same name — so the
    harness renders it once — labelled with the first drop and with the second,
    so every drop metric can be asked about either.
    """
    source = SA.intro_build_drop_track()
    rate = source.sample_rate
    lead = int(source.beat_samples[0])
    bar = int(round(4.0 * 60.0 / source.bpm * rate))
    cut = lead + 28 * bar
    fade = int(round(0.005 * rate))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)

    first = np.asarray(source.samples[:cut], dtype=np.float32).copy()
    first[-fade:] *= ramp[::-1]
    second = np.asarray(source.samples[lead:cut], dtype=np.float32).copy()
    second[:fade] *= ramp

    samples = np.concatenate([first, second]).astype(np.float32)
    beat = int(round(60.0 / source.bpm * rate))
    common = dict(
        name="two_drops",
        samples=samples,
        sample_rate=rate,
        bpm=source.bpm,
        beat_samples=tuple(range(lead, len(samples), beat)),
        downbeat_samples=tuple(range(lead, len(samples), beat * 4)),
    )
    return (
        SA.SyntheticTrack(drop_sample=int(source.drop_sample), **common),
        SA.SyntheticTrack(drop_sample=cut + int(source.drop_sample) - lead, **common),
    )


@contextlib.contextmanager
def anticipation_disabled():
    """Render with the drop predictor unable to publish a candidate.

    `DropPredictor.update` is the only thing that ever moves the published
    prediction off the `NO_DROP_PREDICTION` its constructor set, so patching it
    leaves the renderer reading exactly what it read before this path existed.
    Nothing else about the engine, the detector or the analyser is touched,
    which is what makes the difference between two such runs attributable to
    the anticipation path and to nothing else.
    """
    from app.services.lighting.section_manager import (
        DropPredictor, NO_DROP_PREDICTION,
    )

    with mock.patch.object(
        DropPredictor, "update", lambda self, **kwargs: NO_DROP_PREDICTION
    ):
        yield


_FOOTPRINTS: Dict[Tuple, Tuple] = {}


async def anticipation_footprint(track: SA.SyntheticTrack):
    """The same track rendered with and without anticipation, and the difference.

    Returns `(live, blind, delta)` where `delta` is per-frame, per-fixture
    emitted intensity, live minus blind. Every claim about what the
    anticipation path did — or, on material with no drop in it, did not do — is
    made against `delta` rather than against a threshold chosen by hand.
    """
    key = (track.name, round(track.gain_db, 4))
    if key not in _FOOTPRINTS:
        live = await M.run_track(track, engine=M.build_engine())
        with anticipation_disabled():
            blind = await M.run_track(track, engine=M.build_engine())
        assert live.frame_count == blind.frame_count, track.name
        _FOOTPRINTS[key] = (live, blind, live.intensity - blind.intensity)
    return _FOOTPRINTS[key]


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
    for track in (click_track(), drop_track(), sparse_track(), dense_track(),
                  tempo_track(), build_without_drop_track()):
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
    policy gate in the codebase deleted. The set is therefore first shown to
    flash under the permissive posture, and only then switched off.

    Non-vacuity is asserted over the set rather than per track. Only material
    with a real drop in it earns an accent: the dense track is twenty-four
    seconds of the same bar, and a detector that reported a drop in it would be
    flapping. Requiring every track to flash is what made this guard demand a
    detector defect in order to pass.
    """
    permissive_flashes = 0
    for track in (drop_track(), dense_track()):
        render = track.with_gain_db(9.0)

        permissive = await M.run_track(
            render, engine=M.build_venue_engine(accessibility_mode="performance")
        )
        permissive_flashes += int(M.white_flash_times(permissive).size)

        off = await M.run_track(
            render, engine=M.build_venue_engine(accessibility_mode="no_strobe")
        )
        assert M.strobe_frame_fraction(off) == 0.0, render.name
        assert M.white_flash_times(off).size == 0, render.name

    assert permissive_flashes > 0, (
        "nothing flashes anywhere even when allowed, so switching it off "
        "proves nothing"
    )


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


async def test_the_venue_cap_holds_in_the_permissive_posture_too():
    """The operator's cap is the cap, whatever posture the venue file names.

    `accessibility_mode` and `strobe_hz_cap` are independent fields, so a venue
    can run `performance` while still asking for three flashes a second. With
    the rate correction applied per posture rather than where the flash grid is
    chosen, that combination delivered four flashes inside one second on the
    drop track — the operator's own cap breached, and no test above could see
    it because every one of them runs the default posture.
    """
    cap = float(M.VENUE_ENGINE_KWARGS["strobe_hz_cap"])
    for gain_db in (0.0, 9.0):
        track = drop_track().with_gain_db(gain_db) if gain_db else drop_track()
        result = await M.run_track(
            track, engine=M.build_venue_engine(accessibility_mode="performance")
        )
        rate = M.peak_flash_rate_hz(result)
        assert rate <= cap, (
            f"{track.name} at performance: {rate} Hz exceeds the configured "
            f"{cap} Hz cap; edges {M.white_flash_times(result).tolist()}"
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


def room_tone(level_dbfs: float, seconds: float = 30.0) -> SA.SyntheticTrack:
    """A steady noise floor, the way a paused player on a mic input presents."""
    rng = np.random.default_rng(11)
    amplitude = 10.0 ** (level_dbfs / 20.0)
    n = int(seconds * SA.SAMPLE_RATE)
    return SA.SyntheticTrack(
        name=f"room_tone@{level_dbfs:g}dBFS",
        samples=(rng.standard_normal(n) * amplitude).astype(np.float32),
        sample_rate=SA.SAMPLE_RATE,
        bpm=128.0,
        beat_samples=(),
    )


async def test_a_steady_noise_floor_leaves_the_rig_dark():
    """The hazard, measured where it does harm: on the fixtures.

    An AGC normalises *any* steady input to mid scale by construction, so the
    analyser's normalised value settles at ~0.5 on room tone at or above its
    reference floor whatever that floor is set to. That is only safe while the
    value the rig renders from is not it. A paused player on a Stereo Mix or
    mic device presenting a noise floor once produced a beat-synced 158 BPM
    show with no music, and an earlier guard could not see it because it swept
    only −70 and −60 dBFS and asserted on the analyser rather than the wire.

    Silence here is a realistic noise floor, not the exact digital zeros the
    guard above uses, because multiplying by zero is the one case that rescues
    itself.
    """
    for level_dbfs in (-70.0, -60.0, -55.0, -50.0, -45.0):
        track = room_tone(level_dbfs)
        result = await M.run_track(track, engine=M.build_venue_engine())
        assert result.frame_count > 0
        assert float(result.intensity.max()) <= 0.05, (
            f"{level_dbfs} dBFS room tone lit the rig to "
            f"{float(result.intensity.max()):.4f} after 30 s of no music"
        )
        assert M.white_flash_times(result).size == 0, level_dbfs
        assert M.accent_events(result).total == 0, level_dbfs


async def test_room_tone_cannot_clear_the_drop_loudness_gate():
    """The one place the normalised value does decide something.

    It gates the drop, which is the decision that reaches the strobe. An AGC
    parks a steady input at its target by construction — so room tone sits at
    exactly `LOUDNESS_TARGET` at every level from the reference floor upwards,
    and the gate has to sit clear of that number with margin rather than
    happening to be above it.
    """
    from app.services.audio.audio_analyzer import AudioAnalyzer
    from app.services.lighting.section_manager import StreamingSectionDetector

    gate = StreamingSectionDetector._DROP_MIN_PROGRAMME
    assert gate > AudioAnalyzer.LOUDNESS_TARGET

    for level_dbfs in (-70.0, -60.0, -55.0, -50.0, -45.0, -40.0):
        analyzer = AudioAnalyzer()
        track = room_tone(level_dbfs, seconds=30.0)
        for _, chunk in SA.iter_chunks(track):
            await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32))
        assert analyzer.normalized_energy < gate, (
            f"{level_dbfs} dBFS room tone normalised to "
            f"{analyzer.normalized_energy:.4f}, at or above the {gate} drop gate"
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


@pytest.mark.parametrize("source", ["click", "structured"])
async def test_section_decisions_are_gain_invariant(source):
    """The same track at -12, 0 and +9 dB has to light the same way.

    Run on a structured track as well as the click, and the structured run has
    to visit several sections before its agreement counts. A detector wedged in
    one section agrees with itself perfectly at every gain, so on single-section
    material this measurement is 1.0000 for a detector that has stopped working
    — which is exactly what the baseline it replaced was measuring.
    """
    base = click_track() if source == "click" else drop_track()
    renders = tuple(SA.gain_sweep(base))
    runs = [await run_cached(render) for render in renders]
    labels = [f"{render.gain_db:+g}dB" for render in renders]

    if source == "structured":
        visited = {name for run in runs for name in M.section_occupancy(run)}
        assert len(visited) >= 3, (
            f"degenerate timeline, so agreement proves nothing: {visited}\n"
            + "\n".join(f"{l}: {M.section_timeline(r)}" for l, r in zip(labels, runs))
        )

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
    reason="contract 1: the click track is one bar repeated, so a detector that "
           "measures each feature against this track's own running centre reads "
           "every frame of it as normal. Occupancy on the 0 dB render: verse "
           "100%, lively 0.000 against the 0.15 target. Material with real "
           "structure does reach the high-energy sections (drop track: verse "
           "35.0 / chorus 34.0 / buildup 22.2 / drop 8.9%), so what is missing "
           "is a reading of absolute liveliness, not the detector.",
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
           "detected first. Bar phase error on the click track: mean 513.6 ms "
           "(0.274 of a bar), worst 935.8 ms.",
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


async def test_section_detector_does_not_flap():
    result = await run_cached(sparse_track())
    changes = M.section_changes_per_minute(result)
    shortest = M.shortest_section_hold_s(result)
    assert changes <= 20.0, M.section_timeline(result)
    assert shortest >= 0.75, M.section_timeline(result)


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


async def test_the_drop_lands_in_the_output():
    """The contract's headline number, on the un-accented reference engine.

    The detector still names the drop 716 ms late and is meant to: its
    hysteresis and minimum hold are what took section flapping to zero. What
    this measures is the anticipation path in front of it, which projects the
    drop onto the phrase grid and commits when the audio confirms.
    """
    track = drop_track()
    result = await run_cached(track)
    latency = M.drop_latency_ms(result, track)
    step = M.drop_intensity_step(result, track)
    assert latency is not None, f"output never moved; step was {step}"
    assert latency <= 250.0, latency
    assert step >= 0.15, step


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


async def test_the_drop_reads_as_a_sustained_lift_not_a_strobe():
    """A drop should read as the room getting bigger, not as a square wave.

    The response used to be full-on alternating with near-black across
    consecutive frames — 1.000 / 0.004 / 1.000 — which measures as a large
    "step" and as several accents while the room is, on average, no brighter
    than the build it followed. Every assertion here is therefore about the
    *floor* of the drop window rather than its peak: the dimmest frames have to
    be brighter than the build's brightest, and no fixture may be anywhere near
    black.

    The pre-drop window stops 1.2 s before the drop so that the speculative dip
    — which is deliberately darker than the build — is not what "the build's
    level" is measured from.
    """
    track = drop_track()
    cap = float(M.VENUE_ENGINE_KWARGS["strobe_hz_cap"])
    for label in ("reference", "venue"):
        result = (
            await run_cached(track) if label == "reference"
            else await M.run_track(track, engine=M.build_venue_engine())
        )
        pre = result.between(track.drop_time - 4.0, track.drop_time - 1.2)
        post = result.between(track.drop_time + 0.25, track.drop_time + 4.0)
        assert pre.frame_count > 0 and post.frame_count > 0

        quiet_after = float(np.percentile(post.rig_mean, 5))
        loud_before = float(np.percentile(pre.rig_mean, 95))
        assert quiet_after >= loud_before, (
            f"{label}: the drop oscillates rather than lifts — p5 after "
            f"{quiet_after:.4f} against p95 before {loud_before:.4f}"
        )
        assert float(post.rig_mean.mean()) >= 2.0 * float(pre.rig_mean.mean()), (
            f"{label}: mean rig level {float(post.rig_mean.mean()):.4f} after vs "
            f"{float(pre.rig_mean.mean()):.4f} before"
        )
        assert float(post.intensity.min()) >= 0.10, (
            f"{label}: a fixture went to {float(post.intensity.min()):.4f} inside "
            "the drop, which is the strobe-shaped response, not a lift"
        )
        assert M.peak_flash_rate_hz(result) <= cap, label


async def test_a_build_that_impacts_and_breaks_down_is_never_strobed():
    """The false-positive guard the contract asks for, on material that can fail it.

    This is the case the whole speculation rule exists for. The projection is
    *right* — bar 16 is where the phrase turns — and wrong about what happens
    there: one moderate hit and then the floor drops out. The confirmation is
    reached and evaluated on 42 frames here, so a gate that let it through would
    put a full-white strobe on a breakdown.

    The comparison is the whole wire against the same render with the predictor
    unable to publish anything. `delta.max() <= 0` is the load-bearing line: it
    fails the instant *any* term of the confirmation is loosened enough to
    commit, whichever term that is, because a commit can only ever add light.
    The safety counts are stated separately because they are what the failure
    would cost.
    """
    track = build_with_a_false_impact_track()
    live, blind, delta = await anticipation_footprint(track)

    assert float(delta.max()) <= 0.0, (
        f"the anticipation path put {float(delta.max()):.4f} of extra light in "
        f"the room on a build that impacted and broke down; sections "
        f"{M.section_timeline(live)}"
    )
    assert float(delta.min()) <= -0.05, (
        "nothing dipped, so this track never reached the anticipation path"
    )

    venue = await M.run_track(track, engine=M.build_venue_engine())
    assert "drop" not in M.section_names(venue), M.section_timeline(venue)
    assert M.white_flash_times(venue).size == 0, (
        f"a build that never dropped was strobed at "
        f"{M.white_flash_times(venue).tolist()}"
    )
    assert M.accent_events(venue).total == 0, M.accent_events(venue).as_dict()
    assert M.peak_flash_rate_hz(venue) <= float(M.VENUE_ENGINE_KWARGS["strobe_hz_cap"])


async def test_the_speculative_dip_has_a_floor():
    """How dark the renderer is allowed to get on a guess.

    The dip is a fraction of whatever the frame was going to be, so its cost is
    stated as a ratio to the un-anticipated render rather than as a level: on
    every frame of a build that never drops, the room keeps at least this much
    of the light it would have had. Without a bound here, deepening the dip
    turns every projected downbeat — including all the ones that never drop —
    into a near-blackout of the whole rig, and nothing else measures it.
    """
    live, blind, _ = await anticipation_footprint(build_without_drop_track())
    lit = blind.rig_mean > 0.02
    assert np.any(lit)
    kept = float((live.rig_mean[lit] / blind.rig_mean[lit]).min())
    assert kept >= 0.40, (
        f"the speculative dip took the rig to {kept:.4f} of the level it would "
        "have had, which is a blackout rather than a darkening"
    )
    assert kept <= 0.75, "the dip is too shallow to read as intent"


async def test_anticipation_stays_invisible_on_music_that_never_drops():
    """The same comparison on material with no build in it at all.

    Being faster on a drop is worth little beside not lurching on music that
    never has one. Rather than pick a threshold for "lurch", the same track is
    rendered twice — once normally and once with the predictor unable to
    publish anything — and the two DMX streams have to agree frame for frame
    and fixture for fixture.

    Note what this can and cannot see: on both tracks the predictor publishes no
    candidate on any frame, so the agreement is exact by construction and the
    confirmation is never reached. `test_a_build_that_impacts_and_breaks_down_is_never_strobed`
    is the guard that exercises it. The drop track closes the loop here: the
    identical comparison has to *disagree* there, or this test is measuring a
    comparison that cannot see anything.
    """
    for track in (sparse_track(), click_track()):
        live, blind, delta = await anticipation_footprint(track)
        worst = float(np.abs(delta).max())
        assert worst == 0.0, (
            f"{track.name}: anticipation moved the rig by {worst:.4f} on material "
            f"with no drop in it; sections {M.section_timeline(live)}"
        )
        assert M.accent_events(live).total == 0, track.name
        assert M.white_flash_times(live).size == 0, track.name

    _, _, drop_delta = await anticipation_footprint(drop_track())
    assert float(np.abs(drop_delta).max()) > 0.1, (
        "the anticipation path changes nothing even on the drop track, so the "
        "guard above would pass with the whole mechanism deleted"
    )


async def test_a_predicted_drop_that_never_arrives_costs_the_show_nothing():
    """The speculation rule, on a build that reaches the boundary and carries on.

    The dip is the part the renderer is allowed to be wrong about, and it is
    only allowed because being wrong costs light rather than adds it. Five
    separate claims, because "it recovers smoothly" hides four of them:

    * it only ever dims — no unconfirmed hit, no overshoot on release;
    * it really did dim, so nothing below is vacuous;
    * the rig comes back to exactly the frames it would have rendered with no
      prediction at all, which is what "returns to the build's level with no
      residual" means when it is measured rather than asserted;
    * it is back there again by the end of the track, so nothing is stuck;
    * and it took longer than a beat to get there, so it faded rather than
      snapped.
    """
    track = build_without_drop_track()
    boundary = drop_track().drop_time
    live, blind, delta = await anticipation_footprint(track)

    assert float(delta.max()) <= 0.0, (
        f"a drop that never arrived put {float(delta.max()):.4f} of extra light "
        "in the room"
    )
    assert float(delta.min()) <= -0.05, (
        "nothing dipped, so this track is not exercising the speculation rule"
    )

    times = live.frame_times
    settled = (times >= boundary + 3.0) & (times <= boundary + 11.0)
    assert np.any(settled)
    assert float(np.abs(delta[settled]).max()) == 0.0, (
        "the rig never came back to where the build had it"
    )
    tail = times >= track.duration_s - 5.0
    assert np.any(tail)
    assert float(np.abs(delta[tail]).max()) == 0.0, "the dip is stuck on"

    # How long the deepest point of the dip took to come back. Stated as a
    # duration rather than as a per-frame rate because the chase underneath is
    # swinging the rig by far more than the dip is, so no bound on the rig's own
    # frame-to-frame movement can resolve the release at all.
    footprint = delta.mean(axis=1)
    deepest = int(np.argmin(footprint))
    settled_at = next(
        (
            i for i in range(deepest + 1, len(footprint) - 10)
            if float(np.abs(footprint[i:i + 10]).max()) == 0.0
        ),
        None,
    )
    assert settled_at is not None, "the dip never finished being given back"
    assert times[settled_at] - times[deepest] >= 1.0, (
        f"the dip was given back over {times[settled_at] - times[deepest]:.3f} s, "
        "which is inside a beat and reads as a snap"
    )
    window = (times >= boundary - 2.5) & (times <= boundary + 3.5)
    assert float(np.max(np.diff(live.rig_mean[window]))) <= float(
        np.max(np.diff(blind.rig_mean[window]))
    ) + 1e-9, "releasing the dip is the largest jump the rig makes"


async def test_a_mispredicted_drop_does_not_flash_the_room():
    """Safety, on the machine the venue runs rather than the reference engine.

    A dip is cheap when it is wrong. An accent is not: the strobe budget, the
    Hz cap and the duty cycle exist because the cost of being wrong there is a
    person in the audience, not a dull moment in the show.
    """
    track = build_without_drop_track()
    result = await M.run_track(track, engine=M.build_venue_engine())

    assert M.white_flash_times(result).size == 0, (
        f"a build that never dropped was strobed at "
        f"{M.white_flash_times(result).tolist()}"
    )
    assert M.accent_events(result).total == 0, M.accent_events(result).as_dict()
    assert M.peak_flash_rate_hz(result) <= float(M.VENUE_ENGINE_KWARGS["strobe_hz_cap"])
    assert "drop" not in M.section_names(result), M.section_timeline(result)


async def test_the_commit_is_not_the_biggest_step_the_rig_makes():
    """The transient no strobe rule can see, measured where it is worst.

    Coming out of the dip into the drop is a rise, not a flash, so the Hz cap,
    the duty cycle, the genre budget and `no_strobe` all have nothing to say
    about it — and the dip exists precisely to make it as large as possible. In
    the accessibility posture that exists to protect photosensitive viewers, the
    rig went 0.05 to 0.80 in one 16.7 ms frame.

    The bound is the reactive path's own worst step on the same track and the
    same posture, so it cannot be satisfied by making the show duller: whatever
    the section boundary already does, anticipating it may not do more.
    """
    track = drop_track()
    for mode in ("no_strobe", "conservative"):
        live = await M.run_track(track, engine=M.build_venue_engine(accessibility_mode=mode))
        with anticipation_disabled():
            blind = await M.run_track(track, engine=M.build_venue_engine(accessibility_mode=mode))

        worst_live = float(np.diff(live.intensity, axis=0).max())
        worst_blind = float(np.diff(blind.intensity, axis=0).max())
        assert worst_live <= worst_blind + 1e-9, (
            f"{mode}: anticipating the drop stepped a fixture by {worst_live:.4f} "
            f"in one frame against {worst_blind:.4f} without it"
        )
        assert float(np.max(np.diff(live.rig_mean))) <= float(
            np.max(np.diff(blind.rig_mean))
        ) + 1e-9, mode
    assert M.white_flash_times(
        await M.run_track(track, engine=M.build_venue_engine(accessibility_mode="no_strobe"))
    ).size == 0


async def test_two_drops_in_one_session_are_both_landed():
    """Anticipation is opportunistic; the fallback underneath it is not.

    The projection is anchored on where the detector's fast rise crosses its
    gate, and that gate is measured against a spread which adapts to the track:
    on the second pass over the same audio the climb is found two bars later and
    the eight-bar projection points two bars past the drop. The candidate is
    then consumed by the detector naming the drop, so nothing lurches — the
    second drop simply falls back to the reactive path.

    Measured on the reference engine, this track: 49.7 ms on the first drop,
    499.3 ms on the second, which is the number the reactive path renders with
    the predictor silenced. Anything worse than that on the second drop means
    the mispointed candidate has started costing light rather than merely not
    saving any.
    """
    early, late = two_drop_track()
    result = await run_cached(early)

    first = M.drop_latency_ms(result, early)
    second = M.drop_latency_ms(result, late)
    assert first is not None and second is not None, (
        f"{first} / {second}; sections {M.section_timeline(result)}"
    )
    assert first <= 250.0, first
    assert second <= 1000.0, second
    assert M.section_names(result).count("drop") == 2, M.section_timeline(result)
    assert M.shortest_section_hold_s(result) >= 2.0, M.section_timeline(result)


async def test_turning_the_playback_down_never_makes_the_drop_darker():
    """The fader must not be able to turn the anticipation into a net loss.

    Every level in this renderer is a multiple of energy, so a quiet track gets
    a quiet show and the *step* the latency metric looks for shrinks with it.
    That is the zero-floor model and it is fine. What is not fine is the
    anticipation taking light away and giving none back: the dip is spent up
    front on a promise, so if the confirmation is a function of playback level
    there is a gain at which the promise is never kept and the room is darker
    through the drop than with the whole path switched off.

    Measured against the same render with the predictor silenced, across the
    contract's own gain sweep, from a quarter of a second after the drop — which
    is the far side of the confirmation window, so the dip itself is not what is
    being measured. On the rig mean, because that is how much light is in the
    room: per fixture the drop's flat bed is below the peak of the chase it
    replaced, which is a shape change and not a loss.
    """
    track = drop_track()
    for gain_db in (9.0, 0.0, -12.0):
        rendered = track if gain_db == 0.0 else track.with_gain_db(gain_db)
        live, blind, _ = await anticipation_footprint(rendered)

        after = live.frame_times >= track.drop_time + 0.25
        assert np.any(after)
        room = (live.rig_mean - blind.rig_mean)[after]
        assert float(room.min()) >= -1e-9, (
            f"{gain_db:+g} dB: the room was {-float(room.min()):.4f} darker "
            "through the drop than with anticipation switched off"
        )
        assert float(room.max()) > 0.05, f"{gain_db:+g} dB: nothing was won either"

        latency = M.drop_latency_ms(live, track)
        reactive = M.drop_latency_ms(blind, track)
        assert latency is not None, (
            f"{gain_db:+g} dB: the drop never landed; step "
            f"{M.drop_intensity_step(live, track)}"
        )
        # Either the contract's bound, or — where the rig is too quiet for a
        # 0.15 step to be reachable at all — no worse than the reactive path.
        # Measured: 49.7 ms at +9 and 0 dB, 483.0 against 949.7 at -12 dB.
        assert latency <= 250.0 or (reactive is not None and latency <= reactive), (
            f"{gain_db:+g} dB: anticipated {latency:.1f} ms against a reactive "
            f"{reactive}"
        )
        assert M.section_names(live) == M.section_names(blind), (
            f"{M.section_timeline(live)} vs {M.section_timeline(blind)}"
        )


async def test_the_metrics_the_contract_guards_have_not_moved():
    """One place to check every number the anticipation work must not disturb.

    These are the previous phase's results, quoted from the contract's own
    table. They are asserted here as bounds with the measured baseline in the
    message, so a failure says which number moved and by how much rather than
    only that something did.
    """
    sparse = await run_cached(sparse_track())
    assert M.section_changes_per_minute(sparse) == 0.0, (
        f"sparse quiet flaps again: {M.section_timeline(sparse)}"
    )
    assert M.accent_events(sparse).total == 0, M.accent_events(sparse).as_dict()

    # The sparse track never changes section at all, so its 24.0 s hold is the
    # length of the track rather than a hold anything decided. The drop track is
    # where this number is a hold: four sections, shortest 4.83 s.
    assert M.shortest_section_hold_s(sparse) >= 2.0, M.section_timeline(sparse)
    structured = await run_cached(drop_track())
    assert len(M.section_names(structured)) >= 3, M.section_timeline(structured)
    assert M.shortest_section_hold_s(structured) >= 2.0, M.section_timeline(structured)

    quiet, reference, loud = [await run_cached(render) for render in gain_renders()]
    assert M.section_agreement(reference, loud) == 1.0, "baseline 1.0000 at +9 dB"
    assert M.section_agreement(quiet, reference) == 1.0, "baseline 1.0000 at -12 dB"

    phase = M.beat_phase_error(reference, click_track())
    assert phase.mean_ms <= 8.0, f"baseline 6.32 ms: {phase.as_dict()}"
    assert phase.worst_ms <= 16.0, f"baseline 13.21 ms: {phase.as_dict()}"

    occupancy = M.section_occupancy(await run_cached(drop_track()))
    for name, baseline in (("verse", 0.350), ("chorus", 0.340),
                           ("buildup", 0.222), ("drop", 0.089)):
        assert abs(occupancy.get(name, 0.0) - baseline) <= 0.05, (
            f"{name} occupancy moved from {baseline} to "
            f"{occupancy.get(name, 0.0)}: {occupancy}"
        )


# ---------------------------------------------------------------------------
# Contract section 5: dynamics
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="contract 5: dimmer is energy times one scalar per section, so the rig "
           "has almost no contrast. p95-p5 of emitted intensity on the 0 dB drop "
           "track: 0.286 against the 0.45 target, and 0.051 on the sparse quiet "
           "track. It is also level dependent - 0.071 at -12 dB, 0.765 at +9 dB - "
           "because the rig renders from raw energy, which is what keeps a room "
           "tone floor dark.",
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
