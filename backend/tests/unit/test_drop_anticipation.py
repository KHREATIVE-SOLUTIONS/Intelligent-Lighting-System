"""The anticipation path, tested where being wrong would cost something.

The reactive detector names a drop 716 ms after it lands. `DropPredictor`
projects the drop onto the phrase grid instead, and the renderer splits its
response by what a wrong projection costs: a speculative dip before the
projected downbeat, and full level only once the audio confirms.

That split is the thing under test here. The dangerous failure is not a late
drop — that is the behaviour this path replaces and the fallback it degrades
to. The dangerous failures are a prediction that fires on music with no drop
in it, a dip that never lets go, and anything in either path that raises
inside the 60 fps loop. Every test below is written so that it fails on one of
those rather than on a slow drop.

`tests/musical` measures the same behaviour end to end through the real
analyser and real DMX. These are the fast, exact guards: the predictor is
driven with numbers, and the renderer is driven with a scripted prediction so
the mispredicted case can be produced on demand instead of waited for.
"""

import contextlib
import importlib
from unittest import mock

import numpy as np
import pytest

from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.lighting.genre_profiles import Genre
from app.services.lighting.section_manager import (
    DropPrediction,
    DropPredictor,
    NO_DROP_PREDICTION,
    SectionManager,
)

FPS = 60.0
DT = 1.0 / FPS
BPM = 128.0
BEAT_S = 60.0 / BPM
BAR_S = 4.0 * BEAT_S

# The confidence the renderer demands before it will dip at all. Stated here
# rather than imported: a guard that reads the threshold it is measuring can be
# satisfied by moving the threshold.
RENDERER_DIP_CONFIDENCE = 0.50


# ---------------------------------------------------------------------------
# Driving the predictor
# ---------------------------------------------------------------------------


def drive(
    predictor: DropPredictor,
    seconds: float,
    *,
    section="buildup",
    rise=0.5,
    start_s: float = 0.0,
    start_bar: float = 0.0,
    clock_locked: bool = True,
    clock_confidence: float = 0.9,
    bar_seconds: float = BAR_S,
    with_clock: bool = True,
):
    """Run `seconds` of a locked 128 BPM bar clock through the predictor.

    `section` and `rise` may be constants or callables of time, which is how a
    build that stops building is expressed. Returns one
    `(time, bar, prediction)` per frame so a test can assert on the shape of
    the whole run rather than on its last value.
    """
    out = []
    for i in range(int(round(seconds / DT))):
        t = start_s + i * DT
        bar = start_bar + (t - start_s) / bar_seconds
        prediction = predictor.update(
            section=section(t) if callable(section) else section,
            rise_fast=rise(t) if callable(rise) else rise,
            bar_position=(bar if with_clock else None),
            clock_locked=clock_locked,
            clock_confidence=clock_confidence,
            bar_seconds=bar_seconds,
            now=t,
        )
        out.append((t, bar, prediction))
    return out


def resume(predictor, previous, seconds, **kwargs):
    """Continue a run from where `previous` left off, on the same timeline."""
    last_t, last_bar, _ = previous[-1]
    kwargs.setdefault("bar_seconds", BAR_S)
    return drive(
        predictor,
        seconds,
        start_s=last_t + DT,
        start_bar=last_bar + DT / kwargs["bar_seconds"],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The predictor: what it will and will not offer
# ---------------------------------------------------------------------------


def test_a_build_projects_onto_the_next_phrase_boundary():
    """Eight bars from the bar line the climb started on, to the millisecond.

    The whole case for anticipating rather than detecting faster is that the
    bar clock is accurate to a few milliseconds, so the projected instant is a
    target and not a guess. This asserts the projection actually lands on the
    phrase boundary: `seconds_to_drop` has to reach zero at bar 8, not near it.
    """
    predictor = DropPredictor()
    trace = drive(predictor, 8.5 * BAR_S)

    pending = [entry for entry in trace if entry[2].pending]
    assert len(pending) == len(trace), "the build was not recognised throughout"
    assert {entry[2].target_bar for entry in pending} == {8.0}
    assert {entry[2].phrase_bars for entry in pending} == {8}
    assert {entry[2].anchor_bar for entry in pending} == {0.0}

    arrived = [entry for entry in pending if entry[2].seconds_to_drop <= 0.0]
    assert arrived, "the projected instant never arrived"
    t_arrive, bar_arrive, _ = arrived[0]
    assert bar_arrive == pytest.approx(8.0, abs=0.02)
    assert t_arrive == pytest.approx(8.0 * BAR_S, abs=DT)

    for _, bar, prediction in pending:
        assert prediction.bars_to_drop == pytest.approx(8.0 - bar, abs=1e-9)
        assert prediction.seconds_to_drop == pytest.approx(
            prediction.bars_to_drop * BAR_S, abs=1e-9
        )


def test_confidence_is_bounded_and_only_ever_grows_as_the_drop_nears():
    """The renderer commits by degrees, so the number it reads has to be sane.

    Confidence that fell as the candidate approached would arm the dip early
    and disarm it at the moment of the hit, which is the one place a dip has to
    be holding.
    """
    predictor = DropPredictor()
    trace = drive(predictor, 8.0 * BAR_S)
    confidences = [entry[2].confidence for entry in trace if entry[2].pending]

    assert confidences
    assert all(0.0 <= c <= 1.0 for c in confidences)
    assert all(
        confidences[i + 1] >= confidences[i] - 1e-9 for i in range(len(confidences) - 1)
    ), "confidence fell while the projected drop got closer"
    assert confidences[0] < RENDERER_DIP_CONFIDENCE, (
        "a candidate is trusted enough to dip on the frame it is born"
    )
    assert confidences[-1] > RENDERER_DIP_CONFIDENCE


def test_a_clock_the_renderer_cannot_trust_earns_no_confidence_at_all():
    """A projected downbeat is only as good as the phase it is projected from.

    At the clock-confidence floor the candidate may still exist — the detector
    said "build" and the grid says "eight bars" — but nothing may be spent on
    it. Exact zero rather than "small", so the renderer's dip threshold cannot
    be reached by any arithmetic downstream.
    """
    predictor = DropPredictor()
    trace = drive(predictor, 6.0 * BAR_S, clock_confidence=0.30)
    confidences = [entry[2].confidence for entry in trace]

    assert max(confidences) == 0.0
    assert max(confidences) < RENDERER_DIP_CONFIDENCE


def test_without_a_bar_clock_there_is_no_candidate():
    """No grid, no projection. This is the state a caller that never passes a
    clock stays in for the whole run, and it is what predates the predictor."""
    predictor = DropPredictor()
    trace = drive(predictor, 6.0, with_clock=False)

    assert not any(entry[2].pending for entry in trace)
    assert {entry[2].reason for entry in trace} == {"no_bar_clock"}

    unlocked = DropPredictor()
    trace = drive(unlocked, 6.0, clock_locked=False)
    assert not any(entry[2].pending for entry in trace)


def test_nothing_is_offered_outside_a_build():
    """The build is the warning. Without one there is nothing to anticipate."""
    for section in ("verse", "chorus", "breakdown", "intro", ""):
        predictor = DropPredictor()
        trace = drive(predictor, 4.0 * BAR_S, section=section)
        assert not any(entry[2].pending for entry in trace), section


def test_a_build_that_stops_building_expires_its_candidate():
    """Not every build drops; some just fade out, and that has to be survivable."""
    predictor = DropPredictor()
    built = drive(predictor, 3.0 * BAR_S)
    assert built[-1][2].pending

    faded = resume(predictor, built, 2.0, rise=0.02)
    assert not faded[-1][2].pending
    assert faded[-1][2].reason == "build_faded"

    expired_at = next(t for t, _, p in faded if not p.pending)
    assert expired_at - faded[0][0] <= 1.5, "the candidate outlived the build"


def test_losing_the_bar_clock_drops_the_candidate_rather_than_keeping_a_stale_one():
    """Every figure in a prediction is expressed on the caller's bar clock.

    A clock that drops out and comes back is a different origin, so a candidate
    carried across the gap would be pointing at an instant that no longer means
    anything. It has to be re-anchored on the clock that came back.
    """
    predictor = DropPredictor()
    built = drive(predictor, 3.0 * BAR_S)
    assert built[-1][2].pending
    stale_target = built[-1][2].target_bar

    gap = resume(predictor, built, 1.0, with_clock=False)
    assert not any(entry[2].pending for entry in gap)

    after = resume(predictor, gap, 4.0 * BAR_S)
    revived = [entry for entry in after if entry[2].pending]
    assert revived, "the predictor never recovered after the clock returned"
    _, bar_back, prediction = revived[0]
    assert prediction.target_bar != stale_target
    assert prediction.anchor_bar >= bar_back - 1.0


def test_a_missed_phrase_is_reprojected_once_and_then_abandoned():
    """Eight bars is the guess an eight-bar build is most often wrong about.

    So one re-projection to sixteen is worth making. A second miss means this
    material is not on the grid from this anchor, and continuing to offer
    instants would be guessing rather than projecting.
    """
    predictor = DropPredictor()
    trace = drive(predictor, 20.0 * BAR_S)

    phrases = [entry[2].phrase_bars for entry in trace if entry[2].pending]
    assert phrases[0] == 8
    assert 16 in phrases, "an unconfirmed eight-bar guess was never re-projected"

    reprojected = [entry for entry in trace if entry[2].pending and entry[2].phrase_bars == 16]
    assert reprojected[0][1] == pytest.approx(9.0, abs=0.05), (
        "re-projection happened somewhere other than one bar past the miss"
    )

    tail = [entry for entry in trace if entry[1] > 17.5]
    assert tail, "the run was too short to reach the second miss"
    assert not any(entry[2].pending for entry in tail)
    assert {entry[2].reason for entry in tail} <= {"grid_missed", "stale_anchor"}


def test_the_candidate_is_consumed_the_moment_the_detector_confirms():
    predictor = DropPredictor()
    built = drive(predictor, 4.0 * BAR_S)
    assert built[-1][2].pending

    confirmed = resume(predictor, built, 1.0, section="drop")
    assert not any(entry[2].pending for entry in confirmed)
    assert confirmed[0][2].reason == "confirmed"


def test_reset_forgets_the_candidate():
    predictor = DropPredictor()
    drive(predictor, 4.0 * BAR_S)
    assert predictor.prediction.pending

    predictor.reset()
    assert predictor.prediction == NO_DROP_PREDICTION
    assert not predictor.prediction.pending


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(section=None, rise_fast=float("nan"), bar_position=float("nan"),
             clock_locked=True, clock_confidence=float("inf"), bar_seconds=0.0,
             now=float("nan")),
        dict(section="buildup", rise_fast=float("inf"), bar_position=1e300,
             clock_locked=True, clock_confidence=-5.0, bar_seconds=1e9, now=1e9),
        dict(section="buildup", rise_fast=0.5, bar_position=None, clock_locked=True,
             clock_confidence=0.9, bar_seconds=None, now=None),
        dict(section=123, rise_fast="x", bar_position="y", clock_locked="z",
             clock_confidence=None, bar_seconds="w", now="v"),
        dict(section="buildup", rise_fast=0.5, bar_position=3.0, clock_locked=True,
             clock_confidence=0.9, bar_seconds=-1.0, now=0.0),
    ],
)
def test_no_input_makes_the_predictor_raise_or_invent_a_candidate(kwargs):
    """It runs inside the 60 fps path, so an absent prediction is the only
    failure mode it is allowed to have."""
    predictor = DropPredictor()
    prediction = predictor.update(**kwargs)

    assert isinstance(prediction, DropPrediction)
    assert not prediction.pending
    assert prediction.confidence == 0.0


def test_the_bar_clock_arguments_change_no_section_decision():
    """The detector's certainty is the previous phase's biggest result.

    Hysteresis and minimum hold took section flapping from 77.5 changes/min to
    0.00 and the shortest hold from 0.033 s to 24 s. The anticipation path is
    only allowed to run *beside* that, so handing the manager a bar clock has
    to leave every section decision it makes bit-identical.
    """
    with_clock = SectionManager()
    without_clock = SectionManager()

    programme = []
    for i in range(int(round(30.0 / DT))):
        t = i * DT
        loud = t >= 12.0
        beat = (i % int(round(BEAT_S / DT))) == 0
        programme.append(dict(
            energy=0.60 if loud else 0.18,
            bass=0.70 if loud else 0.10,
            spectral_flux=0.30 if loud else 0.05,
            is_beat=beat,
            beat_number=i // int(round(BEAT_S / DT)),
            bpm=BPM,
            programme_level=0.75 if loud else 0.45,
            now=t,
        ))

    a, b = [], []
    for i, frame in enumerate(programme):
        bar = (frame["now"]) / BAR_S
        a.append(with_clock.update_section_from_audio(
            DT, bar_position=bar, clock_locked=True, clock_confidence=0.9,
            bar_seconds=BAR_S, **frame))
        b.append(without_clock.update_section_from_audio(DT, **frame))

    assert a == b, (
        "the bar clock moved a section decision; the predictor is not running "
        "beside the detector, it is running inside it"
    )
    assert len(set(a)) > 1, "single-section material, so agreement proves nothing"


# ---------------------------------------------------------------------------
# Driving the renderer
# ---------------------------------------------------------------------------

_CLOCK_MODULES = (
    "app.services.effects.effects_engine",
    "app.services.effects.decision_engine",
    "app.services.effects.lfo_engine",
    "app.services.lighting.section_manager",
    "app.services.lighting.beam_look_scheduler",
)


class _TimeShim:
    def __init__(self, clock, real):
        self._clock = clock
        self._real = real

    def time(self):
        return self._clock[0]

    def monotonic(self):
        return self._clock[0]

    def perf_counter(self):
        return self._clock[0]

    def __getattr__(self, name):
        return getattr(self._real, name)


@contextlib.contextmanager
def frame_clock():
    """Point the render path's wall clocks at the frame counter.

    Two renders of the same frames have to be comparable to the last bit for
    the differential assertions below to mean anything, and several timers in
    this path read `time.time()` directly. `tests/musical/metrics.py` does the
    same thing for the same reason.
    """
    clock = [0.0]
    patched = []
    try:
        for name in _CLOCK_MODULES:
            module = importlib.import_module(name)
            real = getattr(module, "time", None)
            if real is None:
                continue
            patched.append((module, real))
            module.time = _TimeShim(clock, real)
        yield clock
    finally:
        for module, real in reversed(patched):
            module.time = real


def build_engine(**overrides) -> EffectsEngine:
    kwargs = dict(fps=FPS, auto_mode=True, movement_enabled=True,
                  dimmer_enabled=True, strobe_enabled=False)
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.EDM)
    return engine


def rig_level(engine: EffectsEngine) -> float:
    fixtures = engine.fixtures.get_fixtures_in_group("all")
    if not fixtures:
        return 0.0
    return float(np.mean([float(getattr(f, "dimmer", 0.0)) for f in fixtures]))


BUILD = dict(energy=0.45, bass=0.20, mid=0.35, high=0.55, spectral_flux=0.25,
             programme_level=0.72, valence=0.2, arousal=0.6)
DROP = dict(energy=0.90, bass=0.95, mid=0.70, high=0.75, spectral_flux=0.40,
            programme_level=0.85, valence=0.4, arousal=0.9)
DARK = dict(energy=0.0, bass=0.0, mid=0.0, high=0.0, spectral_flux=0.0,
            programme_level=0.0)

# When the scripted prediction says the drop will land.
T_HIT = 8.0


def render(seconds: float, programme, prediction=None, **engine_overrides):
    """Render at 60 fps with the prediction the renderer reads scripted.

    `prediction` is patched in at `SectionManager.drop_prediction`, the
    property the renderer actually reads, so the mispredicted case can be
    produced deliberately rather than waited for. `None` means no candidate
    ever, which is the show as it behaved before this path existed and is the
    reference every differential below is taken against.
    """
    times, levels, dips, hits = [], [], [], []
    published = {"value": NO_DROP_PREDICTION}
    beat_frames = max(1, int(round(BEAT_S * FPS)))

    with frame_clock() as clock:
        engine = build_engine(**engine_overrides)
        with mock.patch.object(
            SectionManager, "drop_prediction",
            property(lambda self: published["value"]),
        ):
            for i in range(int(round(seconds * FPS))):
                t = i * DT
                clock[0] = t
                published["value"] = (
                    NO_DROP_PREDICTION if prediction is None else prediction(t)
                )
                engine.update_audio(
                    is_beat=(i % beat_frames == 0), beat_number=i // beat_frames,
                    bpm=BPM, **programme(t),
                )
                engine.update(delta_time=DT)
                times.append(float(engine.time))
                levels.append(rig_level(engine))
                dips.append(float(engine._drop_dip))
                hits.append(float(engine._drop_hit_until))

    return (np.asarray(times), np.asarray(levels), np.asarray(dips),
            np.asarray(hits))


def armed(t: float) -> DropPrediction:
    """A confident candidate counting down to `T_HIT` and then past it."""
    if t < 4.0:
        return NO_DROP_PREDICTION
    return DropPrediction(
        pending=True, seconds_to_drop=T_HIT - t, bars_to_drop=(T_HIT - t) / BAR_S,
        confidence=0.9, target_bar=8.0, anchor_bar=0.0, phrase_bars=8,
        reason="armed",
    )


def steady(features):
    return lambda t: dict(features)


def build_then_drop(t):
    return dict(DROP) if t >= T_HIT else dict(BUILD)


# ---------------------------------------------------------------------------
# The renderer: what a wrong prediction costs
# ---------------------------------------------------------------------------


def test_a_prediction_that_never_confirms_only_ever_dims_the_rig():
    """The speculation rule, measured on the fixtures.

    The dip is the part the renderer is allowed to be wrong about, and the
    reason it is allowed is that being wrong only ever costs light. If a
    mispredicted downbeat could *raise* the rig — an unconfirmed hit, a
    released dip that overshoots — the whole split between speculative and
    confirmed would be decorative.
    """
    times, blind, _, _ = render(14.0, steady(BUILD), None)
    _, live, dips, hits = render(14.0, steady(BUILD), armed)

    assert float((live - blind).max()) <= 0.0, (
        "a drop that never arrived still put light in the room"
    )
    assert float(hits.max()) < 0.0, "the renderer committed to an unconfirmed drop"
    assert float(dips.max()) > 0.2, "no dip happened, so this proves nothing"
    assert float((live - blind).min()) <= -0.05


def test_a_prediction_that_never_confirms_returns_the_rig_to_the_build_level():
    """No snap, no residual, no stuck state — each stated separately.

    The build carries on unchanged either side of the projected instant, so
    "returned to the build level" has an exact meaning here: the rig is back to
    the same frames it would have rendered with no prediction at all.
    """
    times, blind, _, _ = render(14.0, steady(BUILD), None)
    _, live, dips, _ = render(14.0, steady(BUILD), armed)

    recovered = times >= T_HIT + 2.5
    assert np.any(recovered)
    assert np.allclose(live[recovered], blind[recovered], atol=1e-9), (
        "the rig never came back to where the build had it"
    )
    assert float(dips[-1]) == 0.0, "the dip is stuck on"

    release = -np.diff(dips)
    assert float(release.max()) <= 0.01, (
        f"the dip was released at {release.max() * FPS:.2f} per second, which "
        "returns the whole dip inside a beat and reads as a snap"
    )
    assert float(np.max(np.diff(live))) <= float(np.max(np.diff(blind))) + 1e-9, (
        "recovering from the dip is the largest jump the rig makes"
    )

    dipping = (times >= T_HIT - 1.0) & (times <= T_HIT)
    assert float(live[dipping].min()) < 0.75 * float(blind[dipping].min()), (
        "the dip was too shallow to read as intent"
    )


def test_a_confirmed_prediction_lands_the_hit_on_the_projected_downbeat():
    """The whole point: the rig is at drop level well inside the contract's bound.

    Not within one frame, and deliberately so. The confirmation has to persist
    for `_DROP_CONFIRM_DWELL_S` before anything commits, and the rig then crosses
    to the drop bed at a bounded rate rather than stepping; both cost time on
    purpose. What is asserted is the thing the contract asks for — the whole
    response inside 250 ms of the projected downbeat — measured against the
    reactive path rendered beside it from the same audio.
    """
    times, anticipated, _, hits = render(14.0, build_then_drop, armed)
    _, reactive, _, no_hits = render(14.0, build_then_drop, None)

    landed = (times >= T_HIT) & (times <= T_HIT + 0.25)
    assert np.any(landed)
    assert float(anticipated[landed].max()) >= float(reactive[landed].max()) + 0.20, (
        f"anticipated {anticipated[landed].max():.3f} vs reactive "
        f"{reactive[landed].max():.3f} inside 250 ms of the projected downbeat"
    )
    assert float(hits.max()) > T_HIT
    assert float(no_hits.max()) < 0.0

    target = float(anticipated[landed].max())
    reached_late = times[reactive >= target]
    assert reached_late.size == 0 or float(reached_late[0]) > T_HIT + 0.25, (
        "the reactive path was already at drop level, so nothing was won"
    )


def test_one_frame_of_a_transient_is_not_a_drop():
    """A lone kick over a quiet pad reads as ~93% bass balance while it rings.

    That is not a drop, and a single 60 fps sample of it must not be able to
    latch the drop look. The confirmation has to still be true a few frames
    later, which a decaying transient is not.
    """
    def spike(t):
        return dict(DROP) if abs(t - T_HIT) < DT * 0.5 else dict(BUILD)

    _, levels, _, hits = render(14.0, spike, armed)
    _, blind, _, _ = render(14.0, spike, None)

    assert float(hits.max()) < 0.0, "one frame of evidence opened the drop look"
    assert float((levels - blind).max()) <= 0.0


def test_an_anticipated_window_closes_when_the_audio_stops_agreeing():
    """The window is opened on evidence the detector has not seen, so it is
    re-asked every frame. A build that impacts and then breaks down has to put
    the rig back down, not hold it up for the rest of the window."""
    def impact_then_breakdown(t):
        if t < T_HIT:
            return dict(BUILD)
        if t < T_HIT + 0.30:
            return dict(DROP)
        return dict(BUILD, energy=0.05, bass=0.05, programme_level=0.40)

    times, levels, _, hits = render(14.0, impact_then_breakdown, armed)
    _, blind, _, no_hits = render(14.0, impact_then_breakdown, None)
    assert float(hits.max()) > T_HIT, "nothing committed, so this proves nothing"
    assert float(no_hits.max()) < 0.0

    held = float(hits.max())
    after = (times >= T_HIT + 0.45) & (times <= held)
    assert np.any(after), "the window had already run out on its own"
    assert np.allclose(levels[after], blind[after], atol=1e-9), (
        f"the rig was rendering a drop {float(np.abs(levels[after] - blind[after]).max()):.4f} "
        "away from the breakdown underneath it, because a window opened 0.3 s "
        "earlier was never re-checked"
    )


def test_the_dip_cannot_step_the_rig_in_a_single_frame():
    """The projected instant is not a continuous function of time.

    `_clock_bar_offset` may move three beats once every eight bars, which shifts
    `seconds_to_drop` by more than a second between adjacent frames; confidence
    crossing the arming threshold is another such edge. Neither may be allowed to
    reach the fixtures as a step.
    """
    def lurching(t):
        if t < T_HIT - 0.50:
            return NO_DROP_PREDICTION
        # A candidate that appears already halfway through its own approach —
        # which is what confidence crossing the arming threshold looks like from
        # here — and is then moved a quarter of a second closer.
        seconds = (T_HIT - t) - (0.25 if t >= T_HIT - 0.30 else 0.0)
        return DropPrediction(
            pending=True, seconds_to_drop=seconds, bars_to_drop=seconds / BAR_S,
            confidence=0.9, target_bar=8.0, anchor_bar=0.0, phrase_bars=8,
            reason="armed",
        )

    times, levels, dips, hits = render(14.0, steady(BUILD), lurching)
    _, blind, _, _ = render(14.0, steady(BUILD), None)

    assert float(dips.max()) > 0.2, "nothing dipped, so this proves nothing"
    assert float(hits.max()) < 0.0
    onset = np.diff(dips)
    assert float(onset.max()) <= 0.011, (
        f"the dip deepened by {onset.max():.4f} in one frame, which takes "
        f"{onset.max() * 100:.1f}% off the whole rig inside 17 ms"
    )
    footprint = np.diff(levels - blind)
    assert float(footprint.min()) >= -0.02, (
        f"the anticipation path took {-footprint.min():.4f} off the rig in one frame"
    )


def test_a_build_that_already_has_its_low_end_needs_a_real_step():
    """The cue is the size of the move, not the level it moves to.

    A build that has kept its bass in is the case where a fixed threshold would
    be cleared by the build itself. What separates the drop is that it puts the
    low end back by `AccentPosture.bass_step`, so the gate has to be the build's
    own reference plus that step, and a hit that only creeps over the build is
    refused.
    """
    heavy_build = dict(BUILD, bass=0.60)

    def creeping_hit(t):
        return dict(DROP, bass=0.80) if t >= T_HIT else dict(heavy_build)

    times, levels, _, hits = render(14.0, creeping_hit, armed)
    _, blind, _, _ = render(14.0, creeping_hit, None)

    assert float(hits.max()) < 0.0, "a hit 0.20 over the build bought the drop look"
    assert float((levels - blind).max()) <= 0.0


def test_the_confirmation_reads_the_same_at_every_playback_level():
    """The fader is not a musical decision.

    `energy` is a plain multiple of the input level, so any absolute term in the
    confirmation makes the whole anticipation path a function of how loud the
    operator is running. Bass balance and programme level are normalised and do
    not move with gain, so scaling only `energy` reproduces exactly what a gain
    change presents to the renderer.

    The quietest setting here puts the drop's own energy at 0.1125, under the
    accent floor of 0.12 that this confirmation used to read: a level at which a
    real drop landed, the anticipation refused it, and the dip it had already
    taken stayed on through the impact.
    """
    commits = {}
    for gain in (0.125, 0.5, 1.0):
        def scaled(t, gain=gain):
            frame = build_then_drop(t)
            return dict(frame, energy=min(1.0, frame["energy"] * gain))

        _, _, _, hits = render(14.0, scaled, armed)
        commits[gain] = round(float(hits.max()), 3)

    assert len(set(commits.values())) == 1, commits
    assert commits[1.0] > T_HIT, commits


def test_silence_stays_dark_through_a_confident_prediction():
    """The zero-floor model outranks the anticipation path.

    A dip is a fraction of the frame and the drop bed is a multiple of energy,
    so both are zero when there is no music. A drop bed that was a constant
    would light a silent room the instant a prediction confirmed.
    """
    always_sure = lambda t: DropPrediction(
        pending=True, seconds_to_drop=max(-1.0, 3.0 - t), bars_to_drop=0.0,
        confidence=1.0, target_bar=8.0, anchor_bar=0.0, phrase_bars=8,
        reason="armed",
    )
    _, levels, _, _ = render(6.0, steady(DARK), always_sure)
    assert float(levels.max()) == 0.0

    loud_but_silent = dict(DARK, bass=1.0, programme_level=1.0)
    _, levels, _, hits = render(6.0, steady(loud_but_silent), always_sure)
    assert float(levels.max()) == 0.0
    assert float(hits.max()) < 0.0


def test_room_tone_cannot_confirm_a_predicted_drop():
    """An AGC parks any steady input at its target, so a paused player presents
    a mid-scale programme level forever. It must not be able to buy a hit."""
    room_tone = dict(energy=0.08, bass=0.9, mid=0.05, high=0.05,
                     spectral_flux=0.01, programme_level=0.50)
    _, levels, _, hits = render(12.0, steady(room_tone), armed)

    assert float(hits.max()) < 0.0
    assert float(levels.max()) <= 0.25


def test_a_confirmed_prediction_never_opens_the_strobe_window():
    """Where the two halves of the speculation rule are separated.

    The confirmation is a cheap question asked inside a window the projection
    chose; it is not the detector's drop rule, which weighs level, fast-band
    z-score, rise and a refractory against the track's own running centre and
    spread. So what it is allowed to buy is a sustained level and nothing more.
    `_rebuild_drop_until` is what arms the white accents, and if the anticipation
    can raise it then a wrong projection puts a strobe on a breakdown — which is
    exactly what it did.

    The detector is held at `buildup` for the whole run, so any strobe window
    opened here was opened by the anticipation path.
    """
    beat_frames = max(1, int(round(BEAT_S * FPS)))
    windows, hits = [], []
    with frame_clock() as clock:
        engine = build_engine(strobe_enabled=True)
        published = {"value": NO_DROP_PREDICTION}
        with mock.patch.object(SectionManager, "drop_prediction",
                               property(lambda self: published["value"])), \
             mock.patch.object(SectionManager, "update_section_from_audio",
                               lambda self, *a, **k: "buildup"):
            for i in range(int(round(12.0 * FPS))):
                t = i * DT
                clock[0] = t
                published["value"] = armed(t)
                engine.update_audio(is_beat=(i % beat_frames == 0),
                                    beat_number=i // beat_frames, bpm=BPM,
                                    **build_then_drop(t))
                engine.update(delta_time=DT)
                windows.append(float(engine._rebuild_drop_until))
                hits.append(float(engine._drop_hit_until))

    assert max(hits) > T_HIT, "nothing committed, so this proves nothing"
    assert max(windows) < 0.0, (
        f"the anticipation path opened the strobe window to {max(windows):.3f} "
        "on material the detector never called a drop"
    )


def test_a_predictor_that_raises_does_not_take_the_frame_with_it():
    """A dark rig with no traceback is the worst outcome in this codebase.

    A fault in the anticipation path has to degrade to the show that predates
    it, which means the frames still render and they render at the level the
    reactive path would have chosen.
    """
    def explode(self):
        raise RuntimeError("predictor fault")

    times, blind, _, _ = render(8.0, steady(BUILD), None)

    published = {"value": NO_DROP_PREDICTION}
    levels = []
    beat_frames = max(1, int(round(BEAT_S * FPS)))
    with frame_clock() as clock:
        engine = build_engine()
        with mock.patch.object(SectionManager, "drop_prediction", property(explode)):
            for i in range(int(round(8.0 * FPS))):
                clock[0] = i * DT
                engine.update_audio(is_beat=(i % beat_frames == 0),
                                    beat_number=i // beat_frames, bpm=BPM, **BUILD)
                engine.update(delta_time=DT)
                levels.append(rig_level(engine))

    faulted = np.asarray(levels)
    assert faulted.shape == blind.shape
    assert float(faulted.max()) > 0.0, "the fault left the rig dark"
    assert np.allclose(faulted, blind, atol=1e-9), (
        "a faulting predictor changed what the rig rendered"
    )
    assert published["value"] is NO_DROP_PREDICTION


def test_a_section_detector_that_raises_leaves_no_dip_armed():
    """The dip is released by the same frame that would arm it.

    A frame that dies before reaching the anticipation step would otherwise
    leave whatever dip was in force holding the rig down for as long as the
    fault lasted, which is a darkened room caused by an exception.
    """
    with frame_clock() as clock:
        engine = build_engine()
        published = {"value": armed(T_HIT - 0.4)}
        with mock.patch.object(SectionManager, "drop_prediction",
                               property(lambda self: published["value"])):
            beat_frames = max(1, int(round(BEAT_S * FPS)))
            for i in range(int(round(8.0 * FPS))):
                clock[0] = i * DT
                engine.update_audio(is_beat=(i % beat_frames == 0),
                                    beat_number=i // beat_frames, bpm=BPM, **BUILD)
                engine.update(delta_time=DT)
            assert engine._drop_dip > 0.0, "no dip to lose, so this proves nothing"

            with mock.patch.object(
                SectionManager, "update_section_from_audio",
                side_effect=RuntimeError("detector fault"),
            ):
                for i in range(30):
                    clock[0] = 8.0 + i * DT
                    engine.update(delta_time=DT)

            assert engine._drop_dip == 0.0
            assert rig_level(engine) > 0.0
