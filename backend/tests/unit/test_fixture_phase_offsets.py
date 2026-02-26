from app.services.effects.effects_engine import EffectsEngine
from app.services.effects.fixture_groups import Fixture


def _fixtures():
    return [
        Fixture(id="f0", name="m0", dmx_address=1, x=-3.0, fixture_type="mover"),
        Fixture(id="f1", name="m1", dmx_address=17, x=-1.0, fixture_type="mover"),
        Fixture(id="f2", name="m2", dmx_address=33, x=1.0, fixture_type="mover"),
        Fixture(id="f3", name="m3", dmx_address=49, x=3.0, fixture_type="mover"),
    ]


def test_phase_offsets_apply_left_right_mirror_and_template_distribution():
    engine = EffectsEngine()
    engine._leader_follower_enabled = False

    offsets = engine._build_fixture_phase_offsets(_fixtures())
    motion = {fixture_id: phase_pair[0] for fixture_id, phase_pair in offsets.items()}

    # Left side stays in lower half; right side in upper half (mirrored grouping split).
    assert motion["f0"] < 0.5
    assert motion["f1"] < 0.5
    assert motion["f2"] >= 0.5
    assert motion["f3"] >= 0.5

    # Inner fixtures are phase-shifted relative to outer fixtures on each side.
    assert motion["f1"] > motion["f0"]
    assert motion["f3"] > motion["f2"]


def test_phase_offsets_apply_odd_even_alternation_and_effect_decorrelation():
    engine = EffectsEngine()
    engine._leader_follower_enabled = False

    offsets = engine._build_fixture_phase_offsets(_fixtures())
    m0, e0 = offsets["f0"]
    m1, e1 = offsets["f1"]
    m2, e2 = offsets["f2"]
    m3, e3 = offsets["f3"]

    # Odd fixtures are pushed later in phase than adjacent even fixtures.
    assert m1 > m0
    assert m3 > m2

    # Effects receive additional phase offset so they don't fully lock with movement.
    assert e0 != m0
    assert e1 != m1
    assert e2 != m2
    assert e3 != m3


def test_phase_offsets_support_optional_leader_follower_delay():
    fixtures = _fixtures()

    engine = EffectsEngine()
    engine._leader_follower_enabled = False
    baseline = engine._build_fixture_phase_offsets(fixtures)

    engine._leader_follower_enabled = True
    engine._leader_follower_delay = 0.1
    delayed = engine._build_fixture_phase_offsets(fixtures)

    # Leader remains nearest baseline; followers are phase-delayed.
    leader_id = "f1"
    assert abs(delayed[leader_id][0] - baseline[leader_id][0]) < 1e-9

    follower_ids = ["f2", "f0", "f3"]
    for fixture_id in follower_ids:
        assert delayed[fixture_id][0] != baseline[fixture_id][0]
