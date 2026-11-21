"""
The look library on the live renderer
=====================================

The library's own selector chooses the look; this checks the join: every one
of its looks can be performed, the selector is told the truth about the music,
it does not repeat itself, and - for now - choosing a look changes how the rig
moves and nothing about how bright it is.
"""

import pytest

from app.services.demo.venue_presets import create_venue_rig
from app.services.effects import live_dimmer as LD
from app.services.effects import live_library as LB
from app.services.effects import live_looks as LL
from app.services.effects import live_moves
from app.services.effects.effects_engine import _CLUB_STYLE_LOOKS, EffectsConfig, EffectsEngine
from app.services.effects.look_library import LOOK_LIBRARY
from tests.musical import metrics as M

ENGINE_SECTIONS = ("breakdown", "verse", "buildup", "chorus", "drop")


def test_every_look_in_the_library_can_be_performed():
    assert len(LOOK_LIBRARY) == 67
    for look in LOOK_LIBRARY:
        movement, speed, amp = LB.movement_of(look)
        assert look.movement_pattern in LB.MOVEMENT_TO_LOOK, look.name
        assert movement in LL.LOOKS, (look.name, movement)
        assert 0.1 <= speed <= 2.0 and 0.1 <= amp <= 2.0, look.name
    # Fifteen movements in the library, each with its own place.
    assert len(set(LB.MOVEMENT_TO_LOOK.values())) == len(LB.MOVEMENT_TO_LOOK) == 15


def test_no_look_can_be_asked_for_and_not_exist():
    assert LB.movement_of(None) == (LL.DEFAULT_LOOK, 1.0, 1.0)
    assert LB.look_named("predrop_freeze") is not None
    assert LB.look_named("no_such_look") is None


def test_energy_is_the_sections_place_moved_by_how_loud_the_moment_is():
    """So a drop offers drop looks at any playback level, and a loud verse differs from a quiet one."""
    assert LB.look_energy("drop", None) == pytest.approx(0.85)
    assert LB.look_energy("drop", 0.5) == pytest.approx(0.85)
    assert LB.look_energy("verse", 0.9) > LB.look_energy("verse", 0.5) > LB.look_energy("verse", 0.1)
    assert 0.0 <= LB.look_energy("breakdown", 0.0) <= LB.look_energy("drop", 1.0) <= 1.0
    # Every section has library looks at its own level.
    for section in ENGINE_SECTIONS:
        energy = LB.look_energy(section, 0.5)
        fits = [l for l in LOOK_LIBRARY if section in l.sections and l.energy_min <= energy <= l.energy_max]
        assert len(fits) >= 4, (section, len(fits))


def test_mood_comes_from_valence_and_arousal():
    assert LB.mood_of(0.8, 0.1) == "ethereal" and LB.mood_of(0.2, 0.1) == "ambient"
    assert LB.mood_of(0.8, 0.35) == "chill" and LB.mood_of(0.2, 0.35) == "dark"
    assert LB.mood_of(0.8, 0.6) == "party" and LB.mood_of(0.2, 0.6) == "driving"
    assert LB.mood_of(0.8, 0.9) == "euphoric" and LB.mood_of(0.2, 0.9) == "aggressive"
    moods = {m for look in LOOK_LIBRARY for m in look.moods}
    for valence in (0.1, 0.9):
        for arousal in (0.1, 0.3, 0.6, 0.9):
            assert LB.mood_of(valence, arousal) in moods


def test_only_audio_tags_the_engine_can_stand_behind_are_claimed():
    known = {tag for look in LOOK_LIBRARY for tag in look.audio_characters}
    loud = LB.audio_characters(energy=0.9, bass=0.8, flux=0.7, section="drop", programme_level=0.7, impact=True)
    assert set(loud) == {"heavy_bass", "full_wall", "fast_transients", "impact"}
    assert set(loud) <= known
    quiet = LB.audio_characters(energy=0.1, bass=0.1, flux=0.0, section="breakdown", programme_level=0.2, impact=False)
    assert quiet == ["sparse_ambient"]
    # Things nothing here can detect are never claimed.
    for tag in ("vocal_heavy", "synth_lead", "drum_breakdown", "noise_riser", "snare_roll"):
        assert tag not in loud and tag not in quiet


def _night(seed, picks_per_section=6, rounds=4):
    chooser = LB.LibraryChooser(seed=seed)
    out = []
    bar = 0
    for _ in range(rounds):
        for section in ENGINE_SECTIONS:
            for _ in range(picks_per_section):
                look = chooser.choose(section=section, energy=LB.look_energy(section, 0.5), mood="driving", bar=bar)
                out.append((section, look))
                bar += 8
    return out


def test_the_library_never_hands_back_the_look_already_running():
    night = _night(seed=3)
    names = [look.name for _, look in night]
    assert all(a != b for a, b in zip(names, names[1:]))
    assert len(set(names)) >= 35, "a night should use a large share of the library"


def test_a_look_is_not_reused_while_it_is_still_recent():
    """The selector keeps its last four out of the running, where the section has enough looks."""
    for section in ("verse", "chorus", "drop"):
        chooser = LB.LibraryChooser(seed=11)
        names = [chooser.choose(section=section, energy=LB.look_energy(section, 0.5), mood="party", bar=i * 8).name
                 for i in range(60)]
        for i in range(len(names) - 4):
            window = names[i:i + 5]
            assert len(set(window)) == 5, (section, window)


def test_every_look_chosen_is_one_tagged_for_the_section():
    for section, look in _night(seed=5):
        assert section in look.sections, (section, look.name)


def test_a_seed_replays_the_same_night_and_another_seed_does_not():
    first = [look.name for _, look in _night(seed=21)]
    again = [look.name for _, look in _night(seed=21)]
    other = [look.name for _, look in _night(seed=22)]
    assert first == again
    assert first != other


def _style_share(style_movements, leaning, seed, picks=400):
    """How often a drop's look moves one of `style_movements`' ways, and every way seen."""
    chooser = LB.LibraryChooser(seed=seed)
    moves = [LB.MOVEMENT_TO_LOOK[chooser.choose(section="drop", energy=0.85, mood="aggressive", bar=i,
                                                style_movements=style_movements if leaning else None
                                                ).movement_pattern] for i in range(picks)]
    return sum(m in style_movements for m in moves) / len(moves), set(moves)


def test_a_club_style_leans_the_choice_without_narrowing_it():
    style = ("fan_sweep_unison", "cross_circle_rows")
    for seed in (2, 3, 4):
        plain, _ = _style_share(style, False, seed)
        leaned, seen = _style_share(style, True, seed)
        assert leaned > plain * 1.25, (seed, plain, leaned)
        # A lean, not a rule: the other ways of moving are all still there.
        assert len(seen - set(style)) >= 5, (seed, seen)


def test_every_club_style_leans_toward_movements_the_library_uses():
    """A movement no look performs would lean toward nothing."""
    used = set(LB.MOVEMENT_TO_LOOK.values())
    for style, spec in _CLUB_STYLE_LOOKS.items():
        if spec["patterns"] is None:
            continue
        assert set(spec["patterns"]) <= used, (style, set(spec["patterns"]) - used)
        # And it has something to lean toward in most of the song.
        reached = [s for s in ENGINE_SECTIONS
                   if any(s in l.sections and LB.MOVEMENT_TO_LOOK[l.movement_pattern] in spec["patterns"]
                          for l in LOOK_LIBRARY)]
        assert len(reached) >= 4, (style, reached)


def test_a_night_under_a_club_style_repeats_itself_no_more_than_one_without():
    """The selector's rule - not one of the last four - holds under every style."""
    for style, spec in _CLUB_STYLE_LOOKS.items():
        for section in ("verse", "chorus", "drop"):
            chooser = LB.LibraryChooser(seed=6)
            names = [chooser.choose(section=section, energy=LB.look_energy(section, 0.5), mood="party",
                                    bar=i * 8, style_movements=spec["patterns"]).name for i in range(40)]
            for i in range(len(names) - 4):
                assert len(set(names[i:i + 5])) == 5, (style, section, names[i:i + 5])


def test_the_running_look_is_never_handed_back_even_when_nothing_else_fits():
    """An energy no drop look is tagged for: the last resort still moves on."""
    chooser = LB.LibraryChooser(seed=9)
    names = [chooser.choose(section="drop", energy=0.0, mood="chill", bar=i).name for i in range(40)]
    assert all(a != b for a, b in zip(names, names[1:]))
    assert all("drop" in LB.look_named(name).sections for name in names)


def test_a_section_the_library_does_not_know_falls_back():
    chooser = LB.LibraryChooser(seed=1)
    assert chooser.choose(section="intermission", energy=0.4, mood="chill") is None


def _rig(name="club_night"):
    manager, _ = create_venue_rig(name)
    return LL.build_rig([f for f in manager.fixtures.values() if "pan" in f.channels and "tilt" in f.channels])


def _fit(movement, rig, motion, speed, amp, bpm):
    return LL.speed_fit(movement, rig, motion, speed=speed, amp=amp, bpm=bpm,
                        max_pan_deg_per_s=live_moves.MAX_PAN_DEG_PER_S,
                        max_tilt_deg_per_s=live_moves.MAX_TILT_DEG_PER_S)


def _asks_too_much(bpm, style_speed=1.0, style_amp=1.0, fitted=False, rig_name="club_night"):
    """Library looks that ask a head for more than it has, at this tempo.

    `fitted` runs each look at the speed the engine would give it: its own,
    times the club style's, times the fit to the tempo."""
    rig = _rig(rig_name)
    beats_per_frame = bpm / 60.0 / 60.0
    step = 3
    max_pan = step * live_moves.MAX_PAN_DEG_PER_S / 60.0
    max_tilt = step * live_moves.MAX_TILT_DEG_PER_S / 60.0
    heads = rig.heads[::4]
    over = set()
    for look in LOOK_LIBRARY:
        movement, speed, amp = LB.movement_of(look)
        speed, amp = speed * style_speed, amp * style_amp
        for section in look.sections:
            motion = LL.SECTION_MOTION.get(section)
            if motion is None:
                continue  # predrop and ethereal are not sections this engine names yet
            run_speed = speed * (_fit(movement, rig, motion, speed, amp, bpm) if fitted else 1.0)
            frames = int(2.0 * motion.cycle_beats / max(0.1, run_speed) / beats_per_frame) + step
            for head in heads:
                last = None
                for i in range(0, frames, step):
                    now = LL.head_pan_tilt(movement, head, rig, i * beats_per_frame, motion, run_speed, amp)
                    if last is not None and (abs(now[0] - last[0]) > max_pan or abs(now[1] - last[1]) > max_tilt):
                        over.add((look.name, section))
                    last = now
    return sorted(over)


@pytest.mark.parametrize("bpm", [128.0, 174.0])
def test_every_look_moves_no_faster_than_a_head_can_up_to_drum_and_bass_tempo(bpm):
    """Each look's own speed and size, on the club rig, with no club style."""
    assert _asks_too_much(bpm) == []


def test_without_the_fit_the_quickest_looks_do_outrun_a_head():
    """What the fit is for. If this stops being true the fit has nothing to do."""
    fastest = max(spec["speed"] for spec in _CLUB_STYLE_LOOKS.values())
    biggest = max(spec["amp"] for spec in _CLUB_STYLE_LOOKS.values())
    assert _asks_too_much(190.0) != []
    assert _asks_too_much(174.0, fastest, biggest) != []


def test_no_look_outruns_a_head_at_any_tempo_or_under_any_club_style():
    """Each look at the speed the engine gives it: fitted to the tempo when it is taken."""
    fastest = max(spec["speed"] for spec in _CLUB_STYLE_LOOKS.values())
    biggest = max(spec["amp"] for spec in _CLUB_STYLE_LOOKS.values())
    assert _asks_too_much(190.0, fitted=True) == []
    assert _asks_too_much(174.0, fastest, biggest, fitted=True) == []
    assert _asks_too_much(240.0, fastest, biggest, fitted=True) == []
    # And on the biggest and the smallest rooms, not only the reference rig.
    for rig_name in ("pro_beam_room", "small_nightclub"):
        assert _asks_too_much(190.0, fastest, biggest, fitted=True, rig_name=rig_name) == []


def test_the_fit_leaves_every_look_alone_at_an_ordinary_tempo():
    """At 128 BPM with no club style nothing is too fast, so nothing is slowed."""
    rig = _rig()
    for look in LOOK_LIBRARY:
        movement, speed, amp = LB.movement_of(look)
        for section in look.sections:
            motion = LL.SECTION_MOTION.get(section)
            if motion is not None:
                assert _fit(movement, rig, motion, speed, amp, 128.0) == 1.0, (look.name, section)


def test_the_fit_only_ever_slows_a_look_and_only_as_far_as_it_must():
    rig = _rig()
    motion = LL.SECTION_MOTION["drop"]
    slowed = 0
    for movement in sorted(set(LB.MOVEMENT_TO_LOOK.values())):
        pan_per_beat, tilt_per_beat = LL.peak_rates(movement, rig, motion, 1.2)
        for bpm in (100.0, 150.0, 200.0, 240.0):
            fit = _fit(movement, rig, motion, 1.5, 1.2, bpm)
            assert 0.0 < fit <= 1.0
            beats_per_s = bpm / 60.0 * 1.5 * fit
            assert pan_per_beat * beats_per_s <= live_moves.MAX_PAN_DEG_PER_S
            assert tilt_per_beat * beats_per_s <= live_moves.MAX_TILT_DEG_PER_S
            if fit < 1.0:
                slowed += 1
                # Slowed to the limit less the headroom, not further.
                nearest = max(pan_per_beat * beats_per_s / live_moves.MAX_PAN_DEG_PER_S,
                              tilt_per_beat * beats_per_s / live_moves.MAX_TILT_DEG_PER_S)
                assert nearest == pytest.approx(LL.SPEED_HEADROOM)
    assert slowed > 0
    # A look that does not move has nothing to slow.
    assert LL.peak_rates("cross_hold", rig, motion) == (0.0, 0.0)
    assert _fit("cross_hold", rig, motion, 1.5, 1.2, 240.0) == 1.0


# ---------------------------------------------------------------------------
# Through the engine
# ---------------------------------------------------------------------------

def _engine(seed, look_dimmer_effects=True):
    engine = EffectsEngine(EffectsConfig(fps=60.0, auto_mode=True, movement_enabled=True, dimmer_enabled=True,
                                         strobe_enabled=False, look_seed=seed,
                                         look_dimmer_effects=look_dimmer_effects))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    return engine


def _run(engine, plan, frames_each=180, energy=0.6, bpm=128.0, each_frame=None):
    """Step the live renderer through sections; returns look names and dimmer levels per frame.

    Two things a test has to do to mean what it says. The beat clock places
    each audio block inside its frame by the wall clock, so a run is only
    repeatable on the virtual one. And the detector publishes its own section
    every frame, so the section is held the way an operator's button holds it.
    """
    looks, levels, sections = [], [], []
    clock = M._Clock()
    i = 0
    beat_frames = max(1, int(round(3600.0 / bpm)))
    with M.virtual_clock(clock):
        for section in plan:
            engine._force_section(section, 1e9)
            for _ in range(frames_each):
                clock.t = (i + 1) / 60.0
                engine.update_audio(energy=energy, bass=0.5 if energy else 0.0, mid=0.3 if energy else 0.0,
                                    high=0.2 if energy else 0.0, is_beat=(i % beat_frames == 0),
                                    beat_number=i // beat_frames, bpm=bpm)
                engine.update(delta_time=1.0 / 60.0)
                if each_frame is not None:
                    each_frame(engine)
                looks.append(engine._rebuild_active_pattern)
                sections.append(engine._rebuild_section)
                levels.append(tuple(round(f.dimmer, 6) for f in engine.fixtures.fixtures.values()))
                i += 1
    assert [s for k, s in enumerate(sections) if k == 0 or sections[k - 1] != s] == list(plan)
    return looks, levels


PLAN = ["verse", "buildup", "drop", "chorus", "breakdown", "verse", "buildup", "drop", "chorus", "drop"]


def test_the_engine_runs_looks_from_the_library_and_does_not_repeat_them():
    looks, _ = _run(_engine(seed=4), PLAN)
    changes = [looks[0]] + [b for a, b in zip(looks, looks[1:]) if a != b]
    assert all(LB.look_named(name) is not None for name in changes), changes
    assert len(changes) >= len(PLAN), "a new section is a new look"
    assert len(set(changes)) >= 8, changes
    # The look running at the end of each section is one tagged for it.
    for k, section in enumerate(PLAN):
        look = LB.look_named(looks[(k + 1) * 180 - 1])
        assert section in look.sections, (section, look.name)


def test_the_engine_moves_as_the_chosen_look_says():
    engine = _engine(seed=4)
    _run(engine, ["drop"], frames_each=30)
    look = LB.look_named(engine._rebuild_active_pattern)
    assert look is not None and "drop" in look.sections
    assert engine._rebuild_look_movement == LB.MOVEMENT_TO_LOOK[look.movement_pattern]
    assert engine._rebuild_look_speed == pytest.approx(look.speed_factor)
    assert engine._rebuild_look_amp == pytest.approx(look.amplitude_factor)
    # The club style's own lean is a separate thing, and there is none here.
    assert engine._rebuild_style_speed == 1.0 and engine._rebuild_style_amp == 1.0
    # And it says so, to whoever is watching the show.
    state = engine.get_pro_lighting_state()
    assert state["look"] == look.name
    assert state["look_movement"] == LB.MOVEMENT_TO_LOOK[look.movement_pattern]


def test_the_engine_fits_a_look_to_the_tempo_it_is_taken_at():
    """A fast club style at a fast tempo: the looks that would outrun a head are slowed, and say so."""
    engine = _engine(seed=4)
    engine._club_style = "dnb"
    rig = _rig()
    seen = {}

    def note(e):
        key = (e._rebuild_active_pattern, e._rebuild_section)
        if key not in seen:
            motion = LL.SECTION_MOTION[e._rebuild_section]
            speed = e._rebuild_style_speed * e._rebuild_look_speed
            amp = e._rebuild_style_amp * e._rebuild_look_amp
            pan, tilt = LL.peak_rates(e._rebuild_look_movement, rig, motion, amp)
            beats_per_s = speed * e._rebuild_speed_fit / e._clock_period
            seen[key] = (e._rebuild_speed_fit, pan * beats_per_s, tilt * beats_per_s)
        # Stepped by hand the beat clock never locks, so it is held at the
        # tempo here: 190 BPM is what the clock would be running at.
        e._clock_period = 60.0 / 190.0

    engine._clock_period = 60.0 / 190.0
    _run(engine, ["drop", "chorus", "drop", "chorus", "drop", "chorus"], frames_each=240, bpm=190.0,
         each_frame=note)
    assert engine._rebuild_style_speed == pytest.approx(_CLUB_STYLE_LOOKS["dnb"]["speed"])
    fits = [fit for fit, _, _ in seen.values()]
    assert all(0.0 < fit <= 1.0 for fit in fits)
    assert min(fits) < 1.0, "at this tempo and style something has to be slowed"
    for key, (_, pan_rate, tilt_rate) in seen.items():
        # Within a head's reach at the tempo the clock was running when it was taken.
        assert pan_rate <= live_moves.MAX_PAN_DEG_PER_S * 1.02, (key, pan_rate)
        assert tilt_rate <= live_moves.MAX_TILT_DEG_PER_S * 1.02, (key, tilt_rate)
    assert engine.get_pro_lighting_state()["look_speed_fit"] == pytest.approx(engine._rebuild_speed_fit, abs=1e-3)


def _beam_columns(engine):
    """Which columns of a `_run` level frame are beams: the heads that carry the look's dimmer effect."""
    fixtures = list(engine.fixtures.fixtures.values())
    return [k for k, f in enumerate(fixtures)
            if "pan" in f.channels and str(f.fixture_type).lower() not in ("wash", "strobe", "bar", "led_bar", "par")]


def test_a_looks_dimmer_effect_moves_light_between_beams_and_never_adds_any():
    """Stage two of bringing the library back: a look now chooses how the beams
    are lit as well as how they move. Against the same night lit by the
    renderer's one chase, on every frame: every other fixture is exactly as it
    was, the drop is exactly as it was, and the beams together are never
    brighter. Strobe modes, bumps, base levels and colour are still not
    performed; when they are, this is the test that has to change."""
    with_looks = _engine(seed=1)
    looks_a, levels_a = _run(with_looks, PLAN)
    looks_b, levels_b = _run(_engine(seed=1, look_dimmer_effects=False), PLAN)
    assert looks_a == looks_b, "the same seed chooses the same looks either way"
    beams = _beam_columns(with_looks)
    assert len(beams) == 12
    others = [k for k in range(len(levels_a[0])) if k not in beams]
    changed = 0
    for n, (a, b) in enumerate(zip(levels_a, levels_b)):
        section = PLAN[n // 180]
        assert [a[k] for k in others] == [b[k] for k in others], (n, section)
        if section == "drop":
            assert a == b, (n, "the drop is one sustained level, whatever the look")
            continue
        # Levels are recorded to six places; twelve of them are summed.
        assert sum(a[k] for k in beams) <= sum(b[k] for k in beams) + 1e-5, (n, section, looks_a[n])
        assert max(a[k] for k in beams) <= 0.6 + 1e-6, (n, "no beam above the moment's energy")
        changed += a != b
    assert changed > 600, "and the looks really are lit differently from the one chase"


def test_two_nights_are_lit_differently_and_the_same_seed_is_the_same_night():
    looks_a, levels_a = _run(_engine(seed=1), PLAN)
    looks_b, levels_b = _run(_engine(seed=2), PLAN)
    looks_c, levels_c = _run(_engine(seed=1), PLAN)
    assert looks_a == looks_c and levels_a == levels_c, "the same seed is the same night"
    assert looks_a != looks_b and levels_a != levels_b
    assert max(max(frame) for frame in levels_a) > 0.3, "and the rig was actually lit"


def test_a_looks_dimmer_effect_is_dark_in_silence():
    _, levels = _run(_engine(seed=3), ["verse", "chorus", "breakdown", "buildup"], energy=0.0)
    assert max(max(frame) for frame in levels) == 0.0


def test_the_engine_lights_the_beams_as_the_chosen_look_says():
    engine = _engine(seed=4)
    _run(engine, ["verse"], frames_each=200)
    look = LB.look_named(engine._rebuild_active_pattern)
    # At the tempo the look was taken at: its own shape, slowed only if it had to be.
    assert engine._rebuild_dimmer == LD.fit_to_tempo(LD.dimmer_of(look), 60.0 / engine._clock_period)
    assert engine._rebuild_dimmer.effect == look.dimmer_effect


# ---------------------------------------------------------------------------
# The speed limit, measured on what the engine sends
# ---------------------------------------------------------------------------

FAST_PLAN = ["verse", "chorus", "buildup", "chorus", "verse", "buildup"]


def _busiest_beam(levels, beams, window=120, rise_at=0.7, fall_at=0.3):
    """The most times any one beam goes from dark to bright in two seconds.

    Counted from the dimmer levels the engine set, frame by frame: a rise is
    the level coming up through 70% of that beam's range after being under
    30% of it. A ripple that does not cross both is not a flash.
    """
    worst = 0
    for k in beams:
        series = [frame[k] for frame in levels]
        low, high = min(series), max(series)
        if high - low < 0.05:
            continue
        rise, fall = low + rise_at * (high - low), low + fall_at * (high - low)
        lit, rises = series[0] >= rise, []
        for n, value in enumerate(series):
            if not lit and value >= rise:
                lit = True
                rises.append(n)
            elif lit and value <= fall:
                lit = False
        for i, start in enumerate(rises):
            worst = max(worst, sum(1 for n in rises[i:] if n < start + window))
    return worst


# At the limit a beam rises at most this often in a two-second window: one at
# the start of it and then one every 1 / MAX_CYCLES_PER_S seconds.
_MOST_RISES = int(2.0 * LD.MAX_CYCLES_PER_S) + 1


def _fast_night(monkeypatch, bpm, look_dimmer_effects=True, tempo_of=None, seed=5, style=None):
    """A night at a fast tempo, with no fill, so every chase is at full contrast.

    Returns the engine, the dimmer levels, the looks as fitted, and the
    largest pan and tilt step any head was sent in one frame.
    """
    monkeypatch.setattr(LD, "FILL", 0.0)
    engine = _engine(seed=seed, look_dimmer_effects=look_dimmer_effects)
    if style:
        engine._club_style = style
    seen, steps, last, frame = [], [0.0, 0.0], {}, [0]

    def hold(e):
        # Stepped by hand the beat clock never locks, so it is held at the tempo.
        frame[0] += 1
        e._clock_period = 60.0 / (tempo_of(frame[0]) if tempo_of else bpm)
        if e._rebuild_dimmer is not None and e._rebuild_dimmer not in seen:
            seen.append(e._rebuild_dimmer)
        for f in e.fixtures.fixtures.values():
            if "pan" in f.channels:
                was = last.get(f.id)
                if was is not None:
                    steps[0] = max(steps[0], abs(f.pan - was[0]))
                    steps[1] = max(steps[1], abs(f.tilt - was[1]))
                last[f.id] = (f.pan, f.tilt)

    engine._clock_period = 60.0 / (tempo_of(0) if tempo_of else bpm)
    _, levels = _run(engine, FAST_PLAN, frames_each=300, bpm=bpm, each_frame=hold)
    return engine, levels, seen, steps


@pytest.mark.parametrize("bpm", [190.0, 240.0])
def test_at_a_fast_tempo_no_beam_is_chased_and_no_head_is_turned_faster_than_the_limit(bpm, monkeypatch):
    engine, levels, seen, steps = _fast_night(monkeypatch, bpm, style="dnb")
    assert _busiest_beam(levels, _beam_columns(engine)) <= _MOST_RISES
    # The looks were slowed to do it, each to within the limit at this tempo.
    assert any(look.beats > 1.0 and LD.cycles_per_beat(look) * bpm / 60.0 > LD.MAX_CYCLES_PER_S / 2.0
               for look in seen), seen
    for look in seen:
        assert LD.cycles_per_beat(look) * bpm / 60.0 <= LD.MAX_CYCLES_PER_S, look
    # And the heads: no frame asks one for more than it can turn in a sixtieth of a second.
    assert steps[0] <= live_moves.MAX_PAN_DEG_PER_S / 60.0 + 1e-6
    assert steps[1] <= live_moves.MAX_TILT_DEG_PER_S / 60.0 + 1e-6
    assert steps[0] > 0.5, "and they were moving"


def test_the_limit_holds_when_the_tempo_doubles_under_a_look(monkeypatch):
    """A look fitted at 120 BPM, and the beat clock then running at 240 and at 480."""
    def tempo_of(n):
        return (120.0, 240.0, 120.0, 480.0)[(n // 45) % 4]

    engine, levels, seen, steps = _fast_night(monkeypatch, 120.0, tempo_of=tempo_of)
    assert _busiest_beam(levels, _beam_columns(engine)) <= _MOST_RISES
    assert steps[0] <= live_moves.MAX_PAN_DEG_PER_S / 60.0 + 1e-6
    assert steps[1] <= live_moves.MAX_TILT_DEG_PER_S / 60.0 + 1e-6


def test_the_dimmer_clock_alone_holds_the_limit_if_the_fit_is_wrong(monkeypatch):
    """The fit trusts the tempo. With it taken away entirely the clock still holds."""
    monkeypatch.setattr(LD, "fit_to_tempo", lambda look, bpm: look)
    engine, levels, seen, _ = _fast_night(monkeypatch, 240.0)
    assert any(LD.cycles_per_beat(look) * 4.0 > LD.MAX_CYCLES_PER_S for look in seen), "nothing was too fast"
    assert _busiest_beam(levels, _beam_columns(engine)) <= _MOST_RISES


def _own_chase_rate(monkeypatch, bpm):
    """How often a second the renderer's own chase passes its busiest beam, over a whole night.

    Its heads have tails, so a beam between two of them only falls to about
    half: a pass is counted from 60% to 80% of the beam's range. Counted over
    the whole run, because the chase also turns round every two bars, which
    is a step of its own and not a matter of how fast it runs.
    """
    engine, levels, _, _ = _fast_night(monkeypatch, bpm, look_dimmer_effects=False)
    passes = _busiest_beam(levels, _beam_columns(engine), window=10 ** 9, rise_at=0.8, fall_at=0.6)
    return passes * 60.0 / len(levels)


def test_the_renderers_own_chase_is_held_to_the_same_limit(monkeypatch):
    """With the looks' dimmer effects off, or no look to take, the one chase lights the beams.

    It passes a beam 2.4 times a second in a chorus at 240 BPM and 3 in a
    build, so it is only just over. At 320 - a tempo estimate that doubled -
    it would be 4."""
    assert _own_chase_rate(monkeypatch, 320.0) <= LD.MAX_CYCLES_PER_S * 1.02


def test_without_the_limit_a_fast_tempo_does_chase_the_beams_too_fast(monkeypatch):
    """What the limit is for. If this stops being true the tests above prove nothing."""
    monkeypatch.setattr(LD, "MAX_CYCLES_PER_S", 1000.0)
    engine, levels, _, _ = _fast_night(monkeypatch, 240.0)
    assert _busiest_beam(levels, _beam_columns(engine)) > _MOST_RISES
    assert _own_chase_rate(monkeypatch, 320.0) > 2.5 * 1.2


def test_at_an_ordinary_tempo_the_limit_changes_nothing_the_one_chase_does(monkeypatch):
    """128 BPM with the looks' dimmer effects off: frame for frame what it was with no limit at all."""
    _, with_limit = _run(_engine(seed=1, look_dimmer_effects=False), PLAN)
    monkeypatch.setattr(LD, "MAX_CYCLES_PER_S", 1000.0)
    _, without = _run(_engine(seed=1, look_dimmer_effects=False), PLAN)
    assert with_limit == without


def test_a_look_is_fitted_again_when_the_rig_changes_under_it():
    engine = _engine(seed=4)
    _run(engine, ["chorus"], frames_each=30)
    key = engine._rebuild_fit_key
    manager, _ = create_venue_rig("pro_beam_room")
    engine.set_fixture_manager(manager)
    engine._rebuild_pattern_hold_until_bar = 10 ** 9      # no new look: the same one, on a new rig
    engine.update(delta_time=1.0 / 60.0)
    assert engine._rebuild_fit_key != key
    assert len(engine._rebuild_fit_key[2]) != len(key[2])
