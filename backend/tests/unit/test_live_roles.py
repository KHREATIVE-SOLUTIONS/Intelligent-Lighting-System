"""
Fixture roles
=============

Beams chase, washes and pars are a steady bed in a second colour, bars run
their own pattern, strobes wait for the drop. And none of that is allowed to
make the rig flash more than it did.
"""

import colorsys
import math

import pytest

from app.services.demo.venue_presets import create_venue_rig
from app.services.effects import live_roles
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine


def test_each_kind_of_fixture_gets_its_part():
    assert live_roles.role_for("strobe", False, True) == live_roles.ACCENT
    assert live_roles.role_for("bar", False, True) == live_roles.BAR
    assert live_roles.role_for("mover", True, True) == live_roles.BEAM
    assert live_roles.role_for("wash", True, True) == live_roles.WASH
    assert live_roles.role_for("wash", False, True) == live_roles.BED


def test_moving_washes_carry_the_chase_when_nothing_else_can():
    """A rig whose only moving lights are washes must not lose its chase."""
    assert live_roles.role_for("wash", True, False) == live_roles.BEAM


@pytest.mark.parametrize("section", ["verse", "buildup", "chorus", "drop", "breakdown"])
def test_a_role_only_ever_takes_level_away(section):
    """Redistribute, never add: no shape exceeds the level the fixture had."""
    for beats in [i * 0.13 for i in range(200)]:
        for u in (-1.0, -0.33, 0.0, 0.33, 1.0):
            for row in (0, 1):
                assert 0.0 <= live_roles.bar_shape(u, row, beats, section) <= 1.0 + 1e-9
        for row in (0, 1, 2):
            assert 0.0 < live_roles.bed_shape(row, beats) <= 1.0 + 1e-9
    assert live_roles.WASH_LEVEL <= 1.0


def test_the_bar_pattern_is_mirrored_and_actually_moves():
    values = [live_roles.bar_shape(0.33, 0, b * 0.1, "chorus") for b in range(40)]
    assert max(values) - min(values) > 0.5
    for beats in (0.0, 0.7, 1.9):
        assert live_roles.bar_shape(-1.0, 0, beats, "chorus") == pytest.approx(
            live_roles.bar_shape(1.0, 0, beats, "chorus"))


def test_the_bed_breathes_without_changing_its_total():
    """Alternate rows move against each other, so two rows always sum the same."""
    for beats in [i * 0.21 for i in range(80)]:
        total = live_roles.bed_shape(0, beats) + live_roles.bed_shape(1, beats)
        assert total == pytest.approx(2.0 * (1.0 - live_roles.BED_BREATH))


def test_the_second_colour_keeps_saturation_and_brightness():
    h, s, v = colorsys.rgb_to_hsv(0.9, 0.2, 0.4)
    r, g, b = live_roles.secondary_colour(0.9, 0.2, 0.4, "drop")
    h2, s2, v2 = colorsys.rgb_to_hsv(r, g, b)
    assert s2 == pytest.approx(s) and v2 == pytest.approx(v)
    assert ((h2 - h) % 1.0) == pytest.approx(0.5)


def test_mirrored_fixtures_get_opposite_places():
    manager, _ = create_venue_rig("club_night")
    bars = [f for f in manager.fixtures.values() if f.fixture_type == "bar"]
    places = live_roles.truss_places(bars)
    by_id = {f.id: f for f in bars}
    assert len({row for _, row in places.values()}) == 2, "booth bars and wall bars are two rows"
    for fid, (u, row) in places.items():
        mirror = next(o for o in bars if abs(o.z - by_id[fid].z) < 1e-6 and abs(o.x + by_id[fid].x) < 1e-6)
        assert places[mirror.id][0] == pytest.approx(-u)


def _run(engine, frames, section):
    # Held the way an operator's button holds it: the detector publishes its
    # own section every frame, and would overwrite one simply written here.
    engine._force_section(section, 1e9)
    out = []
    for i in range(frames):
        engine.update_audio(energy=0.6, bass=0.5, mid=0.3, high=0.2, is_beat=(i % 28 == 0),
                            beat_number=i // 28, bpm=128.0)
        engine.update(delta_time=1.0 / 60.0)
        assert engine._rebuild_section == section
        out.append({f.id: (f.dimmer, f.red, f.green, f.blue) for f in engine.fixtures.fixtures.values()})
    return out


def _club_engine() -> EffectsEngine:
    engine = EffectsEngine(EffectsConfig(fps=60.0, auto_mode=True, movement_enabled=True,
                                         dimmer_enabled=True, strobe_enabled=False,
                                         # Role shaping is measured before the beat
                                         # response stage scales it.
                                         beat_pulse_enabled=False,
                                         output_makeup_gain_enabled=False))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    return engine


def test_on_the_club_rig_each_family_does_its_own_thing():
    engine = _club_engine()
    frames = _run(engine, 480, "chorus")[120:]
    ids = list(frames[0])

    def family(prefix):
        return [i for i in ids if i.startswith(prefix)]

    # Strobes are dark outside the drop.
    assert max(f[i][0] for f in frames for i in family("strobe")) == 0.0
    # Moving washes are steady across the truss; the beams are not.
    assert max(max(f[i][0] for i in family("wash_f")) - min(f[i][0] for i in family("wash_f")) for f in frames) < 1e-9
    assert max(max(f[i][0] for i in family("beam_b")) - min(f[i][0] for i in family("beam_b")) for f in frames) > 0.1
    # Bars run a pattern: at some moment they differ from each other.
    assert max(max(f[i][0] for i in family("bar_")) - min(f[i][0] for i in family("bar_")) for f in frames) > 0.1
    # The bed is a different colour from the beams.
    beam = frames[-1][family("beam_b")[0]][1:]
    bed = frames[-1][family("par_")[0]][1:]
    assert math.dist(beam, bed) > 0.05


def test_no_static_fixture_is_brighter_than_it_used_to_be():
    """Every role's level is at most energy times the section's floor."""
    engine = _club_engine()
    for section in ("verse", "buildup", "chorus"):
        for frame in _run(engine, 240, section)[60:]:
            for fid, (dimmer, *_rgb) in frame.items():
                if fid.startswith(("bar_", "par_", "wash_f", "strobe")):
                    assert dimmer <= 0.6 * 0.78 + 1e-6, (section, fid, dimmer)
