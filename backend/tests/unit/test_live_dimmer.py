"""
A look's dimmer effect and chase style
======================================

The shapes themselves, with no engine: every effect the look library names is
performed, each is a different picture, left and right match, and the rule
that keeps them safe holds on every demo rig - the beams' mean never above the
ceiling they are given, no beam above one, nothing scaled up.
"""

import pytest

from app.services.demo.venue_presets import VENUE_PRESETS, create_venue_rig
from app.services.effects import live_dimmer as LD
from app.services.effects.look_library import LOOK_LIBRARY

RIGS = sorted(VENUE_PRESETS)
BEATS = [i * 0.07 for i in range(0, 260)]          # a little over 18 beats, off the grid
EVERY_LOOK = sorted({LD.dimmer_of(look) for look in LOOK_LIBRARY}, key=repr)


def beams_of(rig_name):
    manager, _ = create_venue_rig(rig_name)
    return [f for f in manager.fixtures.values()
            if "pan" in f.channels and "tilt" in f.channels and str(f.fixture_type).lower() != "wash"]


def test_every_dimmer_effect_and_chase_style_in_the_library_is_one_this_performs():
    for look in LOOK_LIBRARY:
        assert look.dimmer_effect in LD.EFFECTS, (look.name, look.dimmer_effect)
        assert look.chase_direction in LD.DIRECTIONS, (look.name, look.chase_direction)
        performed = LD.dimmer_of(look)
        assert performed.effect == look.dimmer_effect
        assert performed.beats == pytest.approx(look.chase_beats)
        assert performed.width == pytest.approx(look.chase_width)
    assert {look.dimmer_effect for look in LOOK_LIBRARY} == set(LD.EFFECTS)
    assert len(EVERY_LOOK) >= 30, "the library asks for many different ways of lighting the beams"


def test_something_unknown_is_a_level_rig_not_an_error():
    class Odd:
        dimmer_effect, chase_direction, chase_beats, chase_width = "laser_maze", "sideways", 0.0, 9.0

    assert LD.dimmer_of(None) == LD.STATIC
    odd = LD.dimmer_of(Odd())
    assert odd.effect == "static" and odd.direction == "forward"
    assert odd.beats > 0.0 and odd.width <= 1.0


@pytest.mark.parametrize("rig_name", RIGS)
def test_the_beams_never_average_more_than_their_ceiling_and_none_is_above_one(rig_name):
    places = LD.beam_places(beams_of(rig_name))
    if not places:
        pytest.skip("no beams on this rig")
    for look in EVERY_LOOK:
        for ceiling in (0.0, 0.2, 0.4, 0.56, 1.0):
            for beats in BEATS[::7]:
                out = LD.levels(look, places, beats, ceiling)
                assert set(out) == set(places)
                assert all(0.0 <= v <= 1.0 for v in out.values()), (look, beats)
                assert sum(out.values()) / len(out) <= ceiling + 1e-9, (look, ceiling, beats)


@pytest.mark.parametrize("rig_name", RIGS)
def test_a_shape_is_fitted_to_the_ceiling_and_keeps_its_picture(rig_name, monkeypatch):
    places = LD.beam_places(beams_of(rig_name))
    if not places:
        pytest.skip("no beams on this rig")
    order = sorted(places)
    for look in EVERY_LOOK:
        for beats in BEATS[::11]:
            free = [LD.share(look, places[fid], beats) for fid in order]
            for ceiling in (0.3, 0.56):
                held = LD.levels(look, places, beats, ceiling)
                # Filled or scaled, the beams' total is the ceiling: what they had before.
                assert sum(held.values()) / len(held) == pytest.approx(ceiling)
                # And a brighter beam is never made the dimmer one.
                fitted = [held[fid] for fid in order]
                for a in range(len(order)):
                    for b in range(len(order)):
                        if free[a] > free[b] + 1e-9:
                            assert fitted[a] >= fitted[b] - 1e-12
    # With no fill, a shape is only ever scaled down.
    monkeypatch.setattr(LD, "FILL", 0.0)
    for look in EVERY_LOOK:
        for beats in BEATS[::11]:
            held = LD.levels(look, places, beats, 0.3)
            for fid in order:
                assert held[fid] <= LD.share(look, places[fid], beats) + 1e-12


@pytest.mark.parametrize("rig_name", RIGS)
def test_the_two_halves_of_a_swap_are_the_same_size(rig_name):
    """So the rig's total does not blink when alternate heads swap. Counting
    alternate heads from the centre outward failed this: 8 against 4 on the club rig."""
    places = LD.beam_places(beams_of(rig_name))
    if not places:
        pytest.skip("no beams on this rig")
    rows = len({round(float(f.z), 2) for f in beams_of(rig_name)})
    ones = sum(p.step for p in places.values())
    assert abs(len(places) - 2 * ones) <= rows


@pytest.mark.parametrize("rig_name", RIGS)
def test_left_and_right_beams_are_lit_alike(rig_name):
    """Where the effect is one that opens from the centre or holds level."""
    beams = beams_of(rig_name)
    places = LD.beam_places(beams)
    pairs = [(str(a.id), str(b.id)) for a in beams for b in beams
             if abs(a.z - b.z) < 1e-6 and abs(a.y - b.y) < 1e-6 and a.x < -0.05 and abs(a.x + b.x) < 1e-6]
    if not pairs:
        pytest.skip("no mirrored beams on this rig")
    checked = 0
    for look in EVERY_LOOK:
        if look.effect in ("left_right_kick", "circular", "odd_even", "kick_clap"):
            continue      # one side then the other; round the rig; neighbours taking turns
        if look.effect == "chase" and look.direction in ("forward", "bounce"):
            continue      # a spot travelling from one end to the other
        if look.effect == "ramp" and look.direction != "center_out":
            continue
        for beats in BEATS[::9]:
            out = LD.levels(look, places, beats, 0.5)
            for left, right in pairs:
                assert out[left] == pytest.approx(out[right], abs=1e-9), (look, beats)
                checked += 1
    assert checked > 0


def test_alternating_effects_swap_on_the_beat_without_the_total_blinking():
    places = LD.beam_places(beams_of("club_night"))
    for effect in ("odd_even", "kick_clap", "left_right_kick"):
        look = LD.DimmerLook(effect=effect)
        totals = [sum(LD.share(look, p, beats) for p in places.values()) for beats in BEATS]
        assert max(totals) - min(totals) < 1e-9, effect
        assert totals[0] == pytest.approx(len(places) / 2.0)
        first = next(iter(places))
        # Mid-beat a head is fully on or fully off, and it is the other a beat later.
        on_now = LD.share(look, places[first], 0.5)
        assert on_now in (0.0, 1.0)
        assert LD.share(look, places[first], 1.5) == 1.0 - on_now
        # And it gets there over a ramp, not in one frame at 60 fps and 128 BPM.
        frame = 128.0 / 60.0 / 60.0
        steps = [abs(LD.share(look, places[first], (k + 1) * frame) - LD.share(look, places[first], k * frame))
                 for k in range(240)]
        assert 0.0 < max(steps) < 0.5
    # Kick and clap is the odd/even swap the other way round.
    for place in places.values():
        assert LD.share(LD.DimmerLook(effect="kick_clap"), place, 0.5) == \
            1.0 - LD.share(LD.DimmerLook(effect="odd_even"), place, 0.5)
    # Left and right take turns.
    sides = LD.DimmerLook(effect="left_right_kick")
    for place in places.values():
        assert LD.share(sides, place, 0.5) == (1.0 if place.side < 0 else 0.0)


def test_a_chase_travels_the_way_its_style_says():
    places = LD.beam_places(beams_of("club_night"))
    row = sorted((p for p in places.values() if p.ring < 0.5), key=lambda p: p.along)
    assert len(row) == 6

    def brightest(look, beats):
        values = [LD.share(look, p, beats) for p in row]
        return values.index(max(values))

    forward = LD.DimmerLook(effect="chase", direction="forward", beats=4.0, width=0.12)
    order = [brightest(forward, b) for b in (0.4, 1.0, 1.7, 2.4, 3.0, 3.7)]
    assert order == [0, 1, 2, 3, 4, 5]

    bounce = LD.DimmerLook(effect="chase", direction="bounce", beats=4.0, width=0.12)
    assert brightest(bounce, 0.0) == 0 and brightest(bounce, 2.0) == 5 and brightest(bounce, 3.99) == 0

    out = LD.DimmerLook(effect="chase", direction="center_out", beats=4.0, width=0.12)
    early = [LD.share(out, p, 0.8) for p in row]
    late = [LD.share(out, p, 3.9) for p in row]
    assert early[2] == pytest.approx(early[3]) and early[2] > early[0]      # the middle pair first
    assert late[0] == pytest.approx(late[5]) and late[0] > late[2]          # the ends last

    # A wide spot lights more of the truss than a narrow one.
    narrow = sum(LD.share(forward, p, 1.0) for p in row)
    wide = sum(LD.share(LD.DimmerLook(effect="chase", width=0.4), p, 1.0) for p in row)
    assert wide > narrow * 1.5
    # And a faster chase is further along at the same moment.
    assert brightest(LD.DimmerLook(effect="chase", beats=2.0, width=0.12), 1.0) > brightest(forward, 1.0)


def test_a_circular_look_goes_round_the_whole_rig():
    places = LD.beam_places(beams_of("club_night"))
    look = LD.DimmerLook(effect="circular", beats=4.0)
    ring = sorted(places.values(), key=lambda p: p.ring)
    leaders = []
    for k in range(48):
        values = [LD.share(look, p, k * 4.0 / 48) for p in ring]
        leaders.append(values.index(max(values)))
    assert set(leaders) == set(range(len(ring))), "every beam takes its turn"
    # Round the rig: the two trusses run in opposite directions.
    back = [p for p in places.values() if p.ring < 0.5]
    front = [p for p in places.values() if p.ring >= 0.5]
    assert sorted(back, key=lambda p: p.ring) == sorted(back, key=lambda p: p.along)
    assert sorted(front, key=lambda p: p.ring) == sorted(front, key=lambda p: -p.along)


def test_the_effects_are_different_pictures():
    places = LD.beam_places(beams_of("club_night"))
    pictures = {}
    for effect in LD.EFFECTS:
        look = LD.DimmerLook(effect=effect, beats=4.0, width=0.2)
        pictures[effect] = tuple(round(LD.share(look, p, beats), 3) for beats in BEATS[::5] for p in places.values())
    assert len(set(pictures.values())) == len(LD.EFFECTS)
    assert set(pictures["static"]) == {1.0}


def test_a_change_of_look_crosses_from_one_shape_to_the_other():
    places = LD.beam_places(beams_of("club_night"))
    old = LD.DimmerLook(effect="odd_even")
    new = LD.DimmerLook(effect="chase", width=0.15)
    at = 10.5
    start = LD.crossfaded(new, old, places, at, at, 0.5)
    assert start == pytest.approx(LD.levels(old, places, at, 0.5))
    done = at + LD.CROSSFADE_BEATS
    assert LD.crossfaded(new, old, places, done, at, 0.5) == LD.levels(new, places, done, 0.5)
    for k in range(1, 20):
        beats = at + LD.CROSSFADE_BEATS * k / 20.0
        mixed = LD.crossfaded(new, old, places, beats, at, 0.5)
        assert sum(mixed.values()) / len(mixed) <= 0.5 + 1e-9
        assert all(0.0 <= v <= 1.0 for v in mixed.values())
    assert LD.crossfaded(new, None, places, at, at, 0.5) == LD.levels(new, places, at, 0.5)


def test_no_beams_is_nothing_to_light():
    assert LD.beam_places([]) == {}
    assert LD.levels(LD.STATIC, {}, 1.0, 0.5) == {}
