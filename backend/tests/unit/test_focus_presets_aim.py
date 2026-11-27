"""Aiming maths for focus presets (services/focus_presets/aim.py).

The forward model in this file is ported line for line from the 3D view
(frontend/src/components/rig/previs/beamThrow.ts beamDirection and hangBeam,
beamState.ts readBeamState's pan/tilt decoding), and does not import the module
under test: a focus is right when the view, sent its DMX, draws the beam
through the target.
"""

import math
import random

import pytest

from app.services.focus_presets.aim import Head, aim


# --- The view, ported -------------------------------------------------------

def view_beam_direction(tilt_rad, turn_rad):
    lean = math.sin(tilt_rad)
    return [-lean * math.sin(turn_rad), -math.cos(tilt_rad), -lean * math.cos(turn_rad)]


def view_hang_beam(d, rx_rad, rz_rad, yaw_rad):
    x, y, z = d
    if rz_rad:
        c, s = math.cos(rz_rad), math.sin(rz_rad)
        x, y = x * c - y * s, x * s + y * c
    if rx_rad:
        c, s = math.cos(rx_rad), math.sin(rx_rad)
        y, z = y * c - z * s, y * s + z * c
    if yaw_rad:
        c, s = math.cos(yaw_rad), math.sin(yaw_rad)
        x, z = x * c + z * s, -x * s + z * c
    return [x, y, z]


def view_decode(coarse, fine, travel, inverted):
    norm = ((coarse << 8) | fine) / 65535 if fine is not None else coarse / 255
    deg = (norm - 0.5) * travel
    return -deg if inverted else deg


def drawn_direction(head: Head, result):
    """Send the result's DMX to the view's head and read where the beam goes."""
    pan_ch = (result.pan_dmx, result.pan_fine_dmx)
    tilt_ch = (result.tilt_dmx, result.tilt_fine_dmx)
    if head.swap:
        # The pan channel carries the tilt axis, over the tilt travel, and the other way round.
        tilt = view_decode(*pan_ch, head.tilt_range, head.tilt_invert)
        pan = view_decode(*tilt_ch, head.pan_range, head.pan_invert)
    else:
        pan = view_decode(*pan_ch, head.pan_range, head.pan_invert)
        tilt = view_decode(*tilt_ch, head.tilt_range, head.tilt_invert)
    local = view_beam_direction(math.radians(tilt), math.radians(pan))
    if head.standing:
        # A standing head: the hung head turned half over about X.
        local = view_hang_beam(local, math.pi, 0, 0)
    rx, yaw, rz = head.rotation
    return view_hang_beam(local, math.radians(rx), math.radians(rz), math.radians(yaw))


def miss_m(head: Head, target, result):
    """How far from the target the drawn beam passes, in metres."""
    d = drawn_direction(head, result)
    v = [target[i] - head.position[i] for i in range(3)]
    along = sum(v[i] * d[i] for i in range(3))
    assert along > 0, "the beam points away from the target"
    return math.sqrt(max(0.0, sum(c * c for c in v) - along * along))


# --- Hung and standing ------------------------------------------------------

def test_a_hung_head_straight_above_its_target_sits_at_centre():
    head = Head(position=(0.0, 6.0, 0.0))
    result = aim(head, (0.0, 0.0, 0.0))
    assert result.reachable
    assert result.pan_deg == 0 and result.tilt_deg == 0
    # 0.5 of 65535 rounds to 32768: 128 and 0.
    assert (result.pan_dmx, result.pan_fine_dmx, result.tilt_dmx, result.tilt_fine_dmx) == (128, 0, 128, 0)


def test_a_hung_head_leans_downstage_with_negative_tilt_and_no_pan():
    head = Head(position=(0.0, 6.0, 0.0))
    result = aim(head, (0.0, 0.0, 6.0))  # 45 degrees toward the audience (+Z)
    assert result.reachable
    assert result.pan_deg == 0
    assert result.tilt_deg == pytest.approx(-45.0)


def test_a_standing_head_points_up_at_tilt_zero_and_cannot_point_into_the_floor():
    head = Head(position=(2.0, 0.3, 1.0), standing=True)
    up = aim(head, (2.0, 6.0, 1.0))
    assert up.reachable and up.tilt_deg == 0 and up.pan_deg == 0
    down = aim(head, (2.0, 0.0, 1.0))
    assert not down.reachable
    assert "tilt 180.0" in down.reason and "135.0" in down.reason


def test_hung_and_standing_heads_answer_the_same_point_differently_and_both_land():
    target = (1.0, 1.7, 4.0)
    hung = Head(position=(-3.0, 6.0, -2.0))
    standing = Head(position=(-3.0, 0.4, -2.0), standing=True)
    a, b = aim(hung, target), aim(standing, target)
    assert a.reachable and b.reachable
    assert (a.pan_deg, a.tilt_deg) != (b.pan_deg, b.tilt_deg)
    assert miss_m(hung, target, a) < 0.005
    assert miss_m(standing, target, b) < 0.005


def test_a_head_hung_at_a_yaw_takes_the_yaw_off_its_pan():
    target = (4.0, 0.0, 0.0)
    plain = aim(Head(position=(0.0, 4.0, 0.0)), target)
    turned_head = Head(position=(0.0, 4.0, 0.0), rotation=(0.0, 90.0, 0.0))
    turned = aim(turned_head, target)
    assert plain.reachable and turned.reachable
    assert abs(plain.tilt_deg) == pytest.approx(45.0)
    assert miss_m(turned_head, target, turned) < 0.005
    assert (plain.pan_deg, plain.tilt_deg) != (turned.pan_deg, turned.tilt_deg)


# --- Invert and swap --------------------------------------------------------

def test_pan_invert_mirrors_the_pan_channel_and_nothing_else():
    target = (3.0, 0.0, 2.0)
    plain_head = Head(position=(0.0, 5.0, 0.0))
    inverted_head = Head(position=(0.0, 5.0, 0.0), pan_invert=True)
    plain, inverted = aim(plain_head, target), aim(inverted_head, target)
    assert (plain.pan_deg, plain.tilt_deg) == (inverted.pan_deg, inverted.tilt_deg)
    assert inverted.pan_attr_deg == pytest.approx(-plain.pan_attr_deg)
    assert inverted.tilt_attr_deg == plain.tilt_attr_deg
    assert (inverted.tilt_dmx, inverted.tilt_fine_dmx) == (plain.tilt_dmx, plain.tilt_fine_dmx)
    assert miss_m(inverted_head, target, inverted) < 0.005


def test_tilt_invert_mirrors_the_tilt_channel():
    target = (0.0, 0.0, 5.0)
    head = Head(position=(0.0, 5.0, 0.0), tilt_invert=True)
    result = aim(head, target)
    assert result.tilt_deg == pytest.approx(-45.0)
    assert result.tilt_attr_deg == pytest.approx(45.0)
    assert miss_m(head, target, result) < 0.005


def test_swap_puts_the_tilt_axis_on_the_pan_channel_over_the_tilt_travel():
    target = (2.0, 0.0, 3.0)
    plain = aim(Head(position=(0.0, 5.0, 0.0)), target)
    head = Head(position=(0.0, 5.0, 0.0), swap=True)
    swapped = aim(head, target)
    assert (swapped.pan_deg, swapped.tilt_deg) == (plain.pan_deg, plain.tilt_deg)
    # The pan channel carries what the tilt channel did, and the other way round.
    assert (swapped.pan_dmx, swapped.pan_fine_dmx) == (plain.tilt_dmx, plain.tilt_fine_dmx)
    assert (swapped.tilt_dmx, swapped.tilt_fine_dmx) == (plain.pan_dmx, plain.pan_fine_dmx)
    # In degrees, each over its own channel's travel: tilt's fraction of 270 is
    # sent as the same fraction of 540 on the pan channel.
    assert swapped.pan_attr_deg == pytest.approx(plain.tilt_attr_deg * 540 / 270)
    assert miss_m(head, target, swapped) < 0.005


# --- Ranges and choice ------------------------------------------------------

def test_a_point_above_the_horizon_is_out_of_reach_for_a_hung_head_with_180_of_tilt():
    head = Head(position=(0.0, 4.0, 0.0), tilt_range=180.0)
    level = aim(head, (0.0, 4.0, 5.0))
    assert level.reachable and abs(level.tilt_deg) == pytest.approx(90.0)
    above = aim(head, (0.0, 6.0, 5.0))
    assert not above.reachable
    assert "tilt" in above.reason and "90.0" in above.reason
    assert above.pan_dmx is None


def test_a_head_with_little_pan_cannot_turn_to_the_side():
    head = Head(position=(0.0, 4.0, 0.0), pan_range=90.0)
    ahead = aim(head, (0.0, 0.0, 3.0))
    assert ahead.reachable
    side = aim(head, (4.0, 0.0, 0.0))  # needs pan 90 either way: past 45
    assert not side.reachable
    assert "pan 90.0" in side.reason and "45.0" in side.reason


def test_no_travel_and_no_throw_are_plain_reasons():
    assert "no pan or no tilt" in aim(Head(position=(0, 4, 0), pan_range=0.0), (0, 0, 0)).reason
    assert "where the fixture is" in aim(Head(position=(1, 2, 3)), (1, 2, 3)).reason


def test_the_solution_nearest_pan_centre_is_chosen():
    head = Head(position=(0.0, 4.0, 0.0))
    # Upstage and a little to the side: one answer pans about 170, the other about -10.
    result = aim(head, (0.5, 0.0, -3.0))
    assert result.reachable
    assert abs(result.pan_deg) < 15
    assert miss_m(head, target=(0.5, 0.0, -3.0), result=result) < 0.005


def test_sixteen_bit_and_eight_bit_values():
    head16 = Head(position=(0.0, 5.0, 0.0))
    head8 = Head(position=(0.0, 5.0, 0.0), pan_fine=False, tilt_fine=False)
    target = (0.0, 0.0, 5.0)  # tilt -45 of 270: norm 0.5 - 45/270 = 0.33333
    a, b = aim(head16, target), aim(head8, target)
    value = round((0.5 - 45 / 270) * 65535)
    assert (a.tilt_dmx, a.tilt_fine_dmx) == (value >> 8, value & 255)
    assert (b.tilt_dmx, b.tilt_fine_dmx) == (round((0.5 - 45 / 270) * 255), None)
    assert b.pan_fine_dmx is None


@pytest.mark.parametrize("seed", range(6))
def test_every_reachable_answer_lands_on_its_target_in_the_view(seed):
    rng = random.Random(seed)
    landed = 0
    for _ in range(150):
        standing = rng.random() < 0.3
        head = Head(
            position=(rng.uniform(-8, 8), rng.uniform(0.2, 1.0) if standing else rng.uniform(3, 9), rng.uniform(-6, 6)),
            rotation=(rng.choice([0.0, 0.0, 15.0, -30.0]), rng.uniform(-180, 180), rng.choice([0.0, 0.0, 10.0])),
            standing=standing,
            pan_range=rng.choice([540.0, 360.0, 630.0]),
            tilt_range=rng.choice([270.0, 240.0, 265.0]),
            pan_invert=rng.random() < 0.5,
            tilt_invert=rng.random() < 0.5,
            swap=rng.random() < 0.3,
            pan_fine=rng.random() < 0.8,
            tilt_fine=rng.random() < 0.8,
        )
        target = (rng.uniform(-10, 10), rng.uniform(0, 4), rng.uniform(-8, 8))
        result = aim(head, target)
        if not result.reachable:
            continue
        landed += 1
        throw = math.dist(head.position, target)
        # 8-bit pan over 630 degrees is about 2.5 degrees a step: allow that.
        step = max(head.pan_range / (255 if not (head.pan_fine and head.tilt_fine) else 65535),
                   head.tilt_range / (255 if not (head.pan_fine and head.tilt_fine) else 65535))
        assert miss_m(head, target, result) <= throw * math.radians(step) + 0.002
        assert abs(result.pan_deg) <= head.pan_range / 2 + 1e-6
        assert abs(result.tilt_deg) <= head.tilt_range / 2 + 1e-6
    assert landed > 100
