"""
Per-Fixture Pan/Tilt Invert and Swap
====================================

A rig is rarely hung the way the software assumes. One head of a mirrored pair
goes up the other way round and pans against its partner; a unit clamped on its
side has its two axes exchanged. The patch records that with three flags, and
the engine applies them at the one place a logical pan/tilt becomes DMX, so no
look has to know how any particular light is hung.

The symmetry tests model the hardware independently of the code under test: a
head whose motor really runs backwards, or which really is turned round on its
clamp. A mirrored look has to land mirrored on the floor with the flag set, and
must not without it.
"""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

from app.api.endpoints.websocket import apply_reactive_lighting
from app.schemas.rig import RigFixtureCreate, RigFixtureResponse, RigFixtureUpdate
from app.services.effects import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import (
    Fixture,
    FixtureGroupManager,
    create_demo_rig,
)


FINE = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4}
COARSE = {'pan': 0, 'tilt': 1, 'dimmer': 2}
# 16-bit pan beside 8-bit tilt: a swap has to requantise, not move bytes across.
MIXED = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'dimmer': 3}

# -154 of 540 and +77 of 270: the 8-bit value and the high byte of the 16-bit
# value disagree there, so the two resolutions cannot be mistaken for each other.
PAN_ANGLE, TILT_ANGLE = -154.0, 77.0
PAN_16, TILT_16 = (54, 254), (201, 1)
PAN_8, TILT_8 = 55, 200

# A second pair whose normalised positions do not add up to one, so "inverted"
# and "swapped" cannot produce the same bytes by coincidence.
PAN_B, TILT_B = 100.0, -40.0
PAN_B_16, TILT_B_16 = (175, 104), (90, 19)

FLAGS = ('pan_invert', 'tilt_invert', 'pan_tilt_swap')


def _mover(fixture_id="mh", channels=FINE, address=1, **kwargs) -> Fixture:
    return Fixture(
        id=fixture_id, name=fixture_id, dmx_address=address,
        channels=dict(channels), fixture_type="mover", **kwargs,
    )


def _frame(*fixtures):
    manager = FixtureGroupManager()
    manager.add_fixtures(list(fixtures))
    return manager.get_dmx_frame(0)


def _aimed(pan, tilt, channels=FINE, **flags):
    fixture = _mover(channels=channels, **flags)
    fixture.pan, fixture.tilt = pan, tilt
    return _frame(fixture)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_a_fixture_is_hung_the_ordinary_way_unless_told_otherwise():
    fixture = _mover()

    assert (fixture.pan_invert, fixture.tilt_invert, fixture.pan_tilt_swap) == (False, False, False)


def test_unset_flags_leave_the_output_exactly_as_it_was():
    assert tuple(_aimed(PAN_ANGLE, TILT_ANGLE)[0:4]) == PAN_16 + TILT_16
    assert tuple(_aimed(PAN_ANGLE, TILT_ANGLE, channels=COARSE)[0:2]) == (PAN_8, TILT_8)


# ---------------------------------------------------------------------------
# Invert
# ---------------------------------------------------------------------------

def test_pan_invert_reverses_pan_and_leaves_tilt_alone_16_bit():
    frame = _aimed(PAN_ANGLE, TILT_ANGLE, pan_invert=True)

    # 14078 -> 65535 - 14078 = 51457 = 0xC901.
    assert tuple(frame[0:2]) == (201, 1)
    assert tuple(frame[2:4]) == TILT_16


def test_tilt_invert_reverses_tilt_and_leaves_pan_alone_16_bit():
    frame = _aimed(PAN_ANGLE, TILT_ANGLE, tilt_invert=True)

    assert tuple(frame[0:2]) == PAN_16
    assert tuple(frame[2:4]) == (54, 254)


def test_invert_on_a_coarse_only_fixture_is_an_8_bit_complement():
    assert tuple(_aimed(PAN_ANGLE, TILT_ANGLE, channels=COARSE, pan_invert=True)[0:2]) == (255 - PAN_8, TILT_8)
    assert tuple(_aimed(PAN_ANGLE, TILT_ANGLE, channels=COARSE, tilt_invert=True)[0:2]) == (PAN_8, 255 - TILT_8)


def test_the_fine_byte_belongs_to_the_same_inverted_position_as_the_coarse_byte():
    """A fine byte left behind while the coarse byte is flipped puts the head
    up to a whole coarse step away from where it was sent, and it jitters as
    the fine byte wraps."""
    for pan in (-270.0, -200.3, -154.0, -0.4, 0.0, 12.7, 133.3, 269.9, 270.0):
        plain = _aimed(pan, 0.0)
        inverted = _aimed(pan, 0.0, pan_invert=True)

        assert inverted[0] * 256 + inverted[1] == 65535 - (plain[0] * 256 + plain[1]), pan


@pytest.mark.parametrize("channels,top", [(FINE, 65535), (COARSE, 255)])
@pytest.mark.parametrize("pan", [-231.0, -90.0, -17.5, 44.0, 180.0])
def test_inverting_pan_is_the_same_as_asking_for_the_opposite_angle(channels, top, pan):
    def word(frame):
        return frame[0] * 256 + frame[1] if top == 65535 else frame[0]

    inverted = word(_aimed(pan, 0.0, channels=channels, pan_invert=True))
    opposite = word(_aimed(-pan, 0.0, channels=channels))

    # One step of slack: the centre of an even-sized scale falls between two values.
    assert abs(inverted - opposite) <= 1


def test_a_fixture_that_cannot_move_is_not_driven_by_an_invert():
    """255 - 0 is 255: an invert applied to an axis that is not being driven
    would slam a static fixture's pan channel against its end stop."""
    static = _mover(channels=FINE, pan_range=0.0, tilt_range=0.0,
                    pan_invert=True, tilt_invert=True, pan_tilt_swap=True)

    assert _frame(static)[0:4] == [0, 0, 0, 0]


# ---------------------------------------------------------------------------
# Swap
# ---------------------------------------------------------------------------

def test_swap_sends_pan_to_the_tilt_channels_and_tilt_to_the_pan_channels():
    frame = _aimed(PAN_B, TILT_B, pan_tilt_swap=True)

    assert tuple(frame[0:2]) == TILT_B_16
    assert tuple(frame[2:4]) == PAN_B_16


def test_swap_requantises_for_the_channel_that_carries_the_value():
    """16-bit pan beside 8-bit tilt. The tilt position has to arrive on the pan
    pair as a real 16-bit value, and pan on the lone tilt channel as a true
    8-bit value - not the high byte of a 16-bit one."""
    frame = _aimed(PAN_ANGLE, TILT_ANGLE, channels=MIXED, pan_tilt_swap=True)

    assert tuple(frame[0:2]) == TILT_16
    assert frame[2] == PAN_8
    assert frame[3] == 0, "a swap must not write past the channels the profile declares"


def test_invert_applies_to_the_logical_axis_whichever_motor_carries_it():
    pan_inverted = _aimed(PAN_B, TILT_B, pan_tilt_swap=True, pan_invert=True)
    assert tuple(pan_inverted[0:2]) == TILT_B_16
    assert tuple(pan_inverted[2:4]) == (255 - PAN_B_16[0], 255 - PAN_B_16[1])

    tilt_inverted = _aimed(PAN_B, TILT_B, pan_tilt_swap=True, tilt_invert=True)
    assert tuple(tilt_inverted[0:2]) == (255 - TILT_B_16[0], 255 - TILT_B_16[1])
    assert tuple(tilt_inverted[2:4]) == PAN_B_16


def test_swap_does_nothing_on_a_fixture_with_only_one_axis():
    pan_only = _mover(channels={'pan': 0, 'dimmer': 1}, pan_tilt_swap=True)
    pan_only.pan = PAN_ANGLE

    assert _frame(pan_only)[0:2] == [PAN_8, 0]

    no_tilt_travel = _mover(channels=COARSE, tilt_range=0.0, pan_tilt_swap=True)
    no_tilt_travel.pan, no_tilt_travel.tilt = PAN_ANGLE, TILT_ANGLE

    assert _frame(no_tilt_travel)[0:2] == [PAN_8, 0], (
        "pan was sent to a tilt axis the profile says has no travel"
    )


# ---------------------------------------------------------------------------
# Mirror symmetry, against an independent model of the hardware
# ---------------------------------------------------------------------------

def _motor_degrees(frame, fixture, axis):
    """Where a motor is, read off the wire the way the fixture reads it."""
    base = fixture.dmx_address - 1
    coarse = frame[base + fixture.channels[axis]]
    fine_offset = fixture.channels.get(f"{axis}_fine")
    travel = fixture.pan_range if axis == 'pan' else fixture.tilt_range
    if fine_offset is not None:
        position = (coarse * 256 + frame[base + fine_offset]) / 65535.0
    else:
        position = coarse / 255.0
    return (position - 0.5) * travel


def _beam(frame, fixture, hang="ordinary"):
    """Unit vector the light leaves a hanging head along. x is stage left/right.

    hang:
      ordinary       - as the software assumes
      pan_reversed   - this unit's pan motor turns the other way for the same value
      turned_round   - the whole unit is clamped on rotated half a turn
    """
    pan = math.radians(_motor_degrees(frame, fixture, 'pan'))
    tilt = math.radians(_motor_degrees(frame, fixture, 'tilt'))
    if hang == "pan_reversed":
        pan = -pan
    x = math.sin(tilt) * math.sin(pan)
    y = -math.cos(tilt)
    z = math.sin(tilt) * math.cos(pan)
    if hang == "turned_round":
        x, z = -x, -z
    return x, y, z


def _mirror_error(left, right):
    """0 when `right` is `left` reflected in the centre line of the stage."""
    return max(abs(left[0] + right[0]), abs(left[1] - right[1]), abs(left[2] - right[2]))


MIRRORED_LOOKS = [(60.0, 40.0), (-35.0, 25.0), (120.0, -50.0), (10.0, 70.0)]


@pytest.mark.parametrize("channels", [FINE, COARSE], ids=["16-bit", "8-bit"])
@pytest.mark.parametrize("hang,flag", [
    ("pan_reversed", "pan_invert"),
    ("turned_round", "tilt_invert"),
])
def test_a_pair_hung_in_mixed_orientation_throws_mirrored_beams(channels, hang, flag):
    for pan, tilt in MIRRORED_LOOKS:
        left = _mover("left", channels, address=1, x=-3.0)
        right = _mover("right", channels, address=21, x=3.0)
        # What every mirrored look asks for: equal and opposite pan, same tilt.
        left.pan, left.tilt = pan, tilt
        right.pan, right.tilt = -pan, tilt

        frame = _frame(left, right)
        assert _mirror_error(_beam(frame, left), _beam(frame, right, hang)) > 0.25, (
            f"the {hang} head already mirrors its partner at pan {pan}, tilt {tilt}; "
            "this look cannot show whether the flag does anything"
        )

        setattr(right, flag, True)
        frame = _frame(left, right)
        error = _mirror_error(_beam(frame, left), _beam(frame, right, hang))

        assert error < 0.02, (
            f"with {flag} set the {hang} head is {error:.3f} off its partner's "
            f"mirror image at pan {pan}, tilt {tilt}"
        )


def test_a_correctly_hung_pair_is_still_mirrored():
    for pan, tilt in MIRRORED_LOOKS:
        left = _mover("left", FINE, address=1, x=-3.0)
        right = _mover("right", FINE, address=21, x=3.0)
        left.pan, left.tilt = pan, tilt
        right.pan, right.tilt = -pan, tilt

        frame = _frame(left, right)

        assert _mirror_error(_beam(frame, left), _beam(frame, right)) < 0.002


# ---------------------------------------------------------------------------
# Every look goes through the same mapping
# ---------------------------------------------------------------------------

def test_the_running_engine_honours_a_flag_on_every_frame_it_renders():
    """Whatever the show decides - look, movement, position preset - the frame
    it sends for a flagged head is the unflagged frame with that one axis
    reversed, and nothing else on the rig moves."""
    manager = create_demo_rig()
    engine = EffectsEngine(EffectsConfig())
    engine.set_fixture_manager(manager)

    mover = manager.fixtures["mover_r1"]
    base = mover.dmx_address - 1
    pan, pan_fine = base + mover.channels['pan'], base + mover.channels['pan_fine']

    for step in range(180):
        engine.update_audio(
            energy=0.8, bass=0.8, mid=0.5, high=0.4,
            is_beat=(step % 28 == 0), beat_number=step // 28, bpm=128.0,
        )
        engine.update(delta_time=1.0 / 60.0)

        plain = manager.get_dmx_frame(0)
        mover.pan_invert = True
        flagged = manager.get_dmx_frame(0)
        mover.pan_invert = False

        assert flagged[pan] * 256 + flagged[pan_fine] == 65535 - (plain[pan] * 256 + plain[pan_fine]), step
        rest = [i for i in range(512) if i not in (pan, pan_fine)]
        assert [flagged[i] for i in rest] == [plain[i] for i in rest], step


# ---------------------------------------------------------------------------
# The reactive path writes position bytes itself
# ---------------------------------------------------------------------------

REACTIVE_ANALYSIS = {
    'beat': {
        'is_beat': True, 'beat_position': 1, 'beat_count': 4, 'bpm': 128,
        'bar_count': 2, 'is_bar': True, 'is_phrase': True, 'is_section': True,
    },
    'mood': {'valence': 0.7, 'arousal': 0.9},
    'frequency': {
        'rms_energy': 0.6, 'spectral_flux': 0.05,
        'bands': [
            {'name': 'bass', 'energy': 0.7},
            {'name': 'mid', 'energy': 0.5},
            {'name': 'high', 'energy': 0.4},
        ],
    },
    'ml': {'structure': {'section': 'chorus'}},
}


class _Controller:
    def __init__(self):
        self.writes = {}

    async def set_channel(self, universe, address, value):
        self.writes[address] = value


async def test_the_reactive_path_honours_the_flags_too(monkeypatch):
    # The path keeps its smoothing state on the function between calls. Start
    # it fresh so the positions it sends here do not depend on test order.
    monkeypatch.setattr(apply_reactive_lighting, "_state", None, raising=False)

    channels = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 5}
    # All three on the centre line, so the path mirrors none of them and gives
    # each the same position: any difference on the wire is the flags.
    plain = _mover("plain", channels, address=100, x=0.0)
    inverted = _mover("inverted", channels, address=200, x=0.0, pan_invert=True)
    swapped = _mover("swapped", channels, address=300, x=0.0, pan_tilt_swap=True)
    manager = FixtureGroupManager()
    manager.add_fixtures([plain, inverted, swapped])
    controller = _Controller()

    await apply_reactive_lighting(controller, REACTIVE_ANALYSIS, fixtures=manager)

    pan, tilt = controller.writes[100], controller.writes[102]
    assert abs(pan - tilt) > 4, "pan and tilt landed together; a swap could not be seen"
    assert abs(pan - 127.5) > 1, "pan sat at centre; an invert could not be seen"

    # The path truncates to a byte after inverting, hence the step of slack.
    assert 254 <= controller.writes[200] + pan <= 255
    assert controller.writes[202] == tilt

    assert controller.writes[300] == tilt
    assert controller.writes[302] == pan


# ---------------------------------------------------------------------------
# The look bench reads the wire and has to undo the same mapping
# ---------------------------------------------------------------------------

LOOK_BENCH = Path(__file__).resolve().parents[3] / "scripts" / "look_bench" / "look_bench.py"


@pytest.fixture(scope="module")
def look_bench():
    spec = importlib.util.spec_from_file_location("look_bench_under_test", LOOK_BENCH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.mark.parametrize("channels", [FINE, COARSE, MIXED], ids=["16-bit", "8-bit", "mixed"])
@pytest.mark.parametrize("combo", range(8))
def test_the_look_bench_reports_where_the_beam_points_whatever_the_hang(look_bench, channels, combo):
    flags = {name: bool(combo >> bit & 1) for bit, name in enumerate(FLAGS)}
    fixture = _mover("mh", channels, **flags)
    fixture.pan, fixture.tilt = PAN_B, TILT_B
    manager = FixtureGroupManager()
    manager.add_fixtures([fixture])

    taps = look_bench.build_taps(manager)
    _, _, pan, tilt = look_bench.decode(taps, {0: manager.get_dmx_frame(0)})

    # An 8-bit channel carries the position to within a step of 1/255.
    slack = 4e-5 if channels is FINE else 5e-3
    assert float(pan[0]) == pytest.approx((PAN_B + 270.0) / 540.0, abs=slack), flags
    assert float(tilt[0]) == pytest.approx((TILT_B + 135.0) / 270.0, abs=slack), flags


def test_the_look_bench_scores_a_mixed_hang_pair_as_mirrored(look_bench):
    """mirror_symmetry_pan compares left and right pan; read raw off the wire, a
    correctly flagged pair would score as two heads moving as one."""
    left = _mover("mover_1", FINE, address=1, x=-3.0)
    right = _mover("mover_2", FINE, address=21, x=3.0, pan_invert=True)
    manager = FixtureGroupManager()
    manager.add_fixtures([left, right])
    taps = look_bench.build_taps(manager)
    by_id = {tap.fid: index for index, tap in enumerate(taps)}

    for pan in (-120.0, -40.0, 15.0, 90.0):
        left.pan, right.pan = pan, -pan
        _, _, decoded, _ = look_bench.decode(taps, {0: manager.get_dmx_frame(0)})

        offset_left = float(decoded[by_id["mover_1"]]) - 0.5
        offset_right = float(decoded[by_id["mover_2"]]) - 0.5
        assert offset_left == pytest.approx(-offset_right, abs=4e-5), pan
        assert abs(offset_left) > 0.02, "the pair sat at centre; nothing was compared"


# ---------------------------------------------------------------------------
# The API schemas
# ---------------------------------------------------------------------------

def test_a_patch_that_names_no_flags_gets_all_three_off():
    created = RigFixtureCreate(fixture_id=1, dmx_address=1)

    assert (created.pan_invert, created.tilt_invert, created.pan_tilt_swap) == (False, False, False)


def test_a_stored_row_with_no_value_reads_back_as_off_rather_than_failing():
    """One NULL in one row must not turn listing the whole rig into a 500."""
    response = RigFixtureResponse.model_validate({
        "id": 7, "rig_id": 1, "fixture_id": 1, "dmx_address": 1,
        "pan_invert": None, "tilt_invert": None, "pan_tilt_swap": None,
    })

    assert (response.pan_invert, response.tilt_invert, response.pan_tilt_swap) == (False, False, False)


def test_an_update_only_carries_the_flags_it_was_sent():
    update = RigFixtureUpdate(tilt_invert=True)

    assert update.model_dump(exclude_unset=True) == {"tilt_invert": True}
