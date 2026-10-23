"""
Operator Blackout and Grand Master
==================================

The two controls an operator must be able to trust without looking: blackout
stays black until it is released, and the grand master scales light, never
position. Both used to be overwritten by the next engine frame within ~16ms.
"""

import math

import pytest

from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager

MOVER = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4,
         'red': 5, 'green': 6, 'blue': 7}
PAR_NO_DIMMER = {'red': 0, 'green': 1, 'blue': 2}


def _rig():
    manager = FixtureGroupManager()
    mover = Fixture(id="mh1", name="MH 1", dmx_address=1, channels=dict(MOVER),
                    fixture_type="mover")
    par = Fixture(id="par1", name="Par 1", dmx_address=101,
                  channels=dict(PAR_NO_DIMMER), fixture_type="par")
    manager.add_fixtures([mover, par])
    return manager, mover, par


def _light(mover, par):
    mover.dimmer = 1.0
    mover.pan = 40.0
    mover.tilt = -20.0
    mover.red = mover.green = mover.blue = 1.0
    par.dimmer = 1.0
    par.red = 1.0


@pytest.fixture
def engine():
    eng = EffectsEngine(EffectsConfig())
    manager, mover, par = _rig()
    eng.set_fixture_manager(manager)
    frames = {}
    eng.set_dmx_callback(lambda universe, frame: frames.__setitem__(universe, list(frame)))
    eng.test_frames = frames
    eng.test_fixtures = (mover, par)
    return eng


def _emit(engine):
    _light(*engine.test_fixtures)
    engine._emit_dmx()
    return engine.test_frames[0]


def test_grand_master_scales_intensity_and_leaves_position_alone(engine):
    full = _emit(engine)
    engine.set_grand_master(0.5)
    half = _emit(engine)

    assert full[4] == 255
    assert half[4] == 127, "the mover's dimmer channel should follow the master"
    assert half[100] == 127, "a par with no dimmer carries intensity in its colour"
    assert half[0:4] == full[0:4], "pulling the master down must never move a head"


def test_blackout_latches_until_restore(engine):
    engine.blackout()
    for _ in range(5):
        frame = _emit(engine)
        assert frame[4] == 0 and frame[100] == 0, "the show relit a latched blackout"
    assert engine.blackout_active
    assert engine.output_master == 0.0

    engine.restore()
    assert _emit(engine)[4] == 255


def test_blackout_goes_out_immediately_not_on_the_next_frame(engine):
    _emit(engine)
    _light(*engine.test_fixtures)
    engine.blackout()
    frame = engine.test_frames[0]
    assert frame[4] == 0 and frame[100:103] == [0, 0, 0]


def test_the_engine_loop_still_runs_under_a_latch(engine):
    """update() keeps rendering (positions, timing) while the room is held dark."""
    engine.blackout()
    for _ in range(30):
        engine.update(1 / 60)
    frame = engine.test_frames[0]
    assert frame[4] == 0 and frame[100:103] == [0, 0, 0]


def test_blackout_keeps_heads_where_they_are(engine):
    lit = _emit(engine)
    engine.blackout()
    dark = _emit(engine)
    assert dark[0:4] == lit[0:4]


def test_stopping_the_engine_does_not_leave_a_latch_behind(engine):
    engine.stop()
    assert not engine.blackout_active
    assert _emit(engine)[4] == 255


@pytest.mark.parametrize("bad", [math.nan, "loud", None])
def test_grand_master_rejects_nonsense(engine, bad):
    with pytest.raises(ValueError):
        engine.set_grand_master(bad)
    assert engine.grand_master == 1.0


def test_grand_master_clamps_to_range(engine):
    assert engine.set_grand_master(1.7) == 1.0
    assert engine.set_grand_master(-0.2) == 0.0
