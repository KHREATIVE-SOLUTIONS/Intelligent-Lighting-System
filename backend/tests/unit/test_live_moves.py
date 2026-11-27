"""
The slew limit
==============

The last step before a pan and tilt reach a fixture: never a bigger move in
one frame than a head can make. The looks themselves are tested in
test_live_looks.py.
"""

import pytest

from app.services.effects import live_moves


def test_slew_never_exceeds_the_rate():
    assert live_moves.slew(0.0, 90.0, 240.0, 1 / 60) == pytest.approx(4.0)
    assert live_moves.slew(0.0, -90.0, 180.0, 1 / 60) == pytest.approx(-3.0)
    assert live_moves.slew(10.0, 11.0, 240.0, 1 / 60) == 11.0


def test_a_nonsense_frame_time_is_one_frame_not_a_free_jump():
    assert live_moves.slew(0.0, 90.0, 240.0, 0.0) == pytest.approx(4.0)
    assert live_moves.slew(0.0, 90.0, 240.0, 5.0) == pytest.approx(4.0)
    assert live_moves.slew(0.0, 90.0, 240.0, -1.0) == pytest.approx(4.0)


def test_the_rates_are_what_a_moving_head_can_do():
    """A full 540 degree pan in a little over two seconds; tilt somewhat slower."""
    assert 150.0 <= live_moves.MAX_PAN_DEG_PER_S <= 300.0
    assert 100.0 <= live_moves.MAX_TILT_DEG_PER_S <= live_moves.MAX_PAN_DEG_PER_S
