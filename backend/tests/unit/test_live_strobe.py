"""
A look's strobe mode
====================

A mode may slow the renderer's own drop strobe to a musical rate and may do
nothing else. Checked on the pure rate, and then on what the engine sets,
frame by frame: never more flashes than the venue's limit in any second,
never more than the renderer's own strobe gave, never a flash outside the
window the renderer already strobes in, and nothing at all when strobing is
off. No DMX, Art-Net or sACN is involved: the engine is stepped by hand and
its fixtures are read back.
"""

import dataclasses

import pytest

from app.services.effects import live_strobe as LS
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.look_library import LOOK_LIBRARY
from app.services.demo.venue_presets import create_venue_rig
from tests.unit.test_live_library import _run

MUSICAL = sorted(LS.FLASHES_PER_BEAT)
LEFT_ALONE = ("none", "fast_synth", "random_burst", "buildup_accel")
TEMPOS = (100.0, 128.0, 150.0, 174.0, 200.0, 240.0)


# ---------------------------------------------------------------------------
# The rate a mode names
# ---------------------------------------------------------------------------

def test_every_strobe_mode_in_the_library_is_one_this_knows_about():
    modes = {LS.mode_of(look) for look in LOOK_LIBRARY}
    assert modes <= set(MUSICAL) | set(LEFT_ALONE), modes - set(MUSICAL) - set(LEFT_ALONE)
    assert modes & set(MUSICAL), "and some of them name a musical rate"
    assert LS.mode_of(None) == "none"


@pytest.mark.parametrize("allowed", [2.6, 5.0, 23.6])
def test_a_mode_names_a_division_of_the_tempo_that_fits_under_the_limit(allowed):
    for mode in MUSICAL:
        for bpm in TEMPOS:
            hz = LS.mode_hz(mode, bpm, allowed)
            assert hz is not None and 0.0 < hz <= allowed, (mode, bpm, hz)
            # Its own rate, halved as often as it had to be and no more.
            halvings = LS.FLASHES_PER_BEAT[mode] * bpm / 60.0 / hz
            assert halvings == pytest.approx(2.0 ** round(__import__("math").log2(halvings)))
            assert halvings >= 1.0 - 1e-9
            if halvings > 1.5:
                assert hz * 2.0 > allowed, (mode, bpm, "slowed further than the limit asked")


def test_what_a_beat_and_an_eighth_come_to():
    assert LS.mode_hz("beat_pulse", 120.0, 23.6) == pytest.approx(2.0)
    assert LS.mode_hz("eighth_note", 120.0, 23.6) == pytest.approx(4.0)
    assert LS.mode_hz("snare_locked", 120.0, 23.6) == pytest.approx(1.0)
    # Under the general-audience limit eighths at 120 do not fit, and become beats.
    assert LS.mode_hz("eighth_note", 120.0, 2.6) == pytest.approx(2.0)
    # At 174 BPM a flash a beat is 2.9 a second: every other beat.
    assert LS.mode_hz("beat_pulse", 174.0, 2.6) == pytest.approx(1.45)


def test_a_mode_that_names_no_rate_or_has_no_room_leaves_the_strobe_alone():
    for mode in LEFT_ALONE + ("", None, "laser_maze"):
        assert LS.mode_hz(mode, 128.0, 23.6) is None
    assert LS.mode_hz("beat_pulse", 128.0, 0.0) is None          # the limit leaves no room
    assert LS.mode_hz("beat_pulse", 128.0, 0.05) is None         # nor for one flash in eight beats
    assert LS.mode_hz("beat_pulse", 0.0, 2.6) is None
    assert LS.mode_hz("beat_pulse", float("nan"), 2.6) is None
    assert LS.mode_hz("beat_pulse", 128.0, float("inf")) is None
    assert LS.mode_hz("beat_pulse", "fast", 2.6) is None


# ---------------------------------------------------------------------------
# Through the engine
# ---------------------------------------------------------------------------

_DROP_LOOK = next(look for look in LOOK_LIBRARY if "drop" in look.sections)
PLAN = ["verse", "drop", "chorus", "drop"]
FRAMES = 150            # two and a half seconds a section; the strobe window is 1.55


def _night(mode, bpm=128.0, cap=3.0, modes_on=True, **config):
    """A night where every look taken has this strobe mode. Returns the engine and per-frame facts."""
    settings = dict(fps=60.0, auto_mode=True, movement_enabled=True, dimmer_enabled=True,
                    strobe_enabled=True, strobe_hz_cap=cap, strobe_max_duty_cycle=0.34,
                    accessibility_mode="performance",      # the default is no_strobe: nothing flashes

                    look_seed=7, look_strobe_modes=modes_on)
    settings.update(config)
    engine = EffectsEngine(EffectsConfig(**settings))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    look = dataclasses.replace(_DROP_LOOK, strobe_mode=mode)
    engine._look_library.choose = lambda **_: look
    frames = []

    def note(e):
        # Stepped by hand the beat clock never locks, so it is held at the tempo.
        e._clock_period = 60.0 / bpm
        fixtures = list(e.fixtures.fixtures.values())
        flash = any(f.red == f.green == f.blue == 1.0 and f.dimmer > 0.9 for f in fixtures)
        in_window = e._rebuild_section == "drop" and e.time < e._rebuild_drop_until
        frames.append((flash, in_window, e._rebuild_strobe_mode_hz))

    engine._clock_period = 60.0 / bpm
    _, levels = _run(engine, PLAN, frames_each=FRAMES, bpm=bpm, each_frame=note)
    return engine, frames, levels


def _onsets(frames):
    return [n for n, (flash, _, _) in enumerate(frames) if flash and (n == 0 or not frames[n - 1][0])]


def _most_in_a_second(frames):
    onsets = _onsets(frames)
    return max((sum(1 for n in onsets[i:] if n < start + 60) for i, start in enumerate(onsets)), default=0)


@pytest.mark.parametrize("cap", [3.0, 24.0])
@pytest.mark.parametrize("mode", MUSICAL)
def test_no_mode_at_any_tempo_flashes_more_than_the_limit_or_more_than_the_strobe_did(mode, cap):
    for bpm in TEMPOS:
        engine, frames, _ = _night(mode, bpm, cap)
        _, own, _ = _night(mode, bpm, cap, modes_on=False)
        assert len(_onsets(own)) > 0, "the renderer's own strobe ran, or this compares nothing"
        # The promise that matters: never more flashes in any one second than the venue allows.
        assert _most_in_a_second(frames) <= cap, (mode, bpm, cap)
        assert _most_in_a_second(own) <= cap, (bpm, cap)
        # A lower rate, so no more flashes than the renderer's own strobe gave -
        # give or take one a window, for where the grid happens to fall when the
        # window opens (150 BPM under a limit of 3: 2.5 a second against 2.6,
        # and nine flashes against eight).
        assert 0 < len(_onsets(frames)) <= len(_onsets(own)) + PLAN.count("drop"), (mode, bpm, cap)
        # Only ever where the renderer already strobes: the front of a drop.
        assert all(in_window for flash, in_window, _ in frames if flash), (mode, bpm, cap)
        # The rate it ran at is the mode's, as the limit allowed it.
        allowed = cap - 0.34 - 0.06
        named = [hz for _, in_window, hz in frames if in_window]
        assert named and all(hz == pytest.approx(LS.mode_hz(mode, bpm, allowed)) for hz in named)
        # And the limit and the switch are whoever's they were: not this module's to write.
        assert engine.config.strobe_hz_cap == cap and engine.config.strobe_enabled is True


def _longest_and_white(frames):
    """The longest run of flash frames, and how many frames were a flash at all."""
    longest = run = white = 0
    for flash, _, _ in frames:
        run = run + 1 if flash else 0
        longest = max(longest, run)
        white += 1 if flash else 0
    return longest, white


@pytest.mark.parametrize("cap", [3.0, 24.0])
@pytest.mark.parametrize("mode", MUSICAL)
def test_a_slower_strobe_is_not_a_longer_flash_or_more_white_light(mode, cap):
    """A flash lasts duty / rate. Slowed at the same duty, a snare_locked drop
    held the rig at full white for 24 frames at a time, where the renderer's
    own strobe holds it for 2 (limit 24) to 8 (limit 3)."""
    for bpm in TEMPOS:
        _, frames, _ = _night(mode, bpm, cap)
        _, own, _ = _night(mode, bpm, cap, modes_on=False)
        longest, white = _longest_and_white(frames)
        own_longest, own_white = _longest_and_white(own)
        # A frame either way is where the sixtieths of a second fall on the grid.
        assert 0 < longest <= own_longest + 1, (mode, bpm, cap, longest, own_longest)
        assert white <= own_white, (mode, bpm, cap, white, own_white)


def test_only_a_look_made_for_the_drop_names_the_drops_strobe_rate():
    """Without a phrase grid a chorus look can still be running when the drop lands."""
    chorus_look = next(look for look in LOOK_LIBRARY if "drop" not in look.sections)
    engine = EffectsEngine(EffectsConfig(fps=60.0, auto_mode=True, strobe_enabled=True, strobe_hz_cap=24.0,
                                         accessibility_mode="performance", look_seed=7))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    look = dataclasses.replace(chorus_look, strobe_mode="beat_pulse")
    engine._look_library.choose = lambda **_: look
    named = []
    _run(engine, ["chorus", "drop"], frames_each=FRAMES,
         each_frame=lambda e: named.append((e._rebuild_strobe_mode, e._rebuild_strobe_mode_hz)))
    assert set(named) == {("none", None)}


def test_a_beat_pulse_drop_flashes_about_once_a_beat_not_as_fast_as_the_venue_allows():
    _, frames, _ = _night("beat_pulse", bpm=120.0, cap=24.0)
    _, own, _ = _night("beat_pulse", bpm=120.0, cap=24.0, modes_on=False)
    # Two strobe windows of 1.55 s at two flashes a second, against 18 a second.
    assert 4 <= len(_onsets(frames)) <= 8
    assert len(_onsets(own)) > 3 * len(_onsets(frames))


@pytest.mark.parametrize("mode", LEFT_ALONE)
def test_a_mode_that_names_no_rate_is_the_renderers_own_strobe_frame_for_frame(mode):
    _, frames, levels = _night(mode)
    _, own, own_levels = _night(mode, modes_on=False)
    assert levels == own_levels
    assert [flash for flash, _, _ in frames] == [flash for flash, _, _ in own]
    assert all(hz is None for _, _, hz in frames)


def test_switched_off_every_look_strobes_as_it_did_whatever_its_mode():
    _, with_mode, levels_a = _night("beat_pulse", modes_on=False)
    _, without, levels_b = _night("none", modes_on=False)
    assert levels_a == levels_b
    assert [flash for flash, _, _ in with_mode] == [flash for flash, _, _ in without]
    assert len(_onsets(with_mode)) > 0


@pytest.mark.parametrize("config", [
    dict(strobe_enabled=False),
    dict(accessibility_mode="no_strobe"),
    dict(accessibility_mode="off"),
    dict(camera_mode=True),
    dict(venue_mode="theatre"),
    dict(strobe_hz_cap=0.0),
    dict(strobe_hz_cap=0.3),            # under the duty: the clamp leaves no room at all
])
def test_a_mode_cannot_strobe_where_strobing_is_off(config):
    for mode in MUSICAL:
        _, frames, _ = _night(mode, **config)
        assert _onsets(frames) == [], (mode, config)


def test_a_mode_is_taken_once_for_a_strobe_window_and_does_not_follow_the_tempo_inside_it():
    """The flash grid is time x rate, so a rate that drifted with the tempo would slide it."""
    engine, frames, _ = _night("beat_pulse", bpm=128.0, cap=24.0)
    wobbling = []
    count = [0]

    def wobble(e):
        count[0] += 1
        e._clock_period = 60.0 / (128.0 + 20.0 * ((count[0] % 7) - 3))
        wobbling.append((e._rebuild_section == "drop" and e.time < e._rebuild_drop_until,
                         e._rebuild_strobe_mode_hz))

    _run(engine, ["verse", "drop"], frames_each=FRAMES, bpm=128.0, each_frame=wobble)
    held = {hz for in_window, hz in wobbling if in_window}
    assert len(held) == 1 and None not in held
