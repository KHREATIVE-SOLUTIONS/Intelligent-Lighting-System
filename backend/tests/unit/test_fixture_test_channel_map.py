"""
Fixture Identify Channel-Map Tests
==================================

The identify/test feature flashes a single fixture so an operator can find it on a
truss. It resolves channels by type, and only pan and tilt have dedicated fine types -
every other 16-bit channel repeats its coarse type. A naive map therefore ends up
pointing at the low byte, the coarse byte stays at zero, and the fixture does not light.
The operator's reasonable conclusion is that the light is broken.
"""

from app.services.fixture_test.fixture_test_service import FixtureTestService


def _service():
    return FixtureTestService(dmx_controller=None)


def _ch(number, ctype, is_fine=False, coarse=None):
    return {
        "channel_number": number,
        "channel_type": ctype,
        "is_fine": is_fine,
        "coarse_channel": coarse,
    }


def test_a_sixteen_bit_dimmer_resolves_to_its_coarse_byte():
    """The Chauvet Rogue R2 Spot 19-channel case: ch15 dimmer, ch16 Dimmer Fine."""
    channels = [
        _ch(15, "dimmer"),
        _ch(16, "dimmer", is_fine=True, coarse=15),
    ]

    ch_map = _service()._build_channel_map(channels)

    assert ch_map["dimmer"] == 14, (
        "identify would drive the fine byte and leave the fixture dark"
    )


def test_pan_and_tilt_keep_their_dedicated_fine_types():
    channels = [
        _ch(1, "pan"), _ch(2, "pan_fine", is_fine=True, coarse=1),
        _ch(3, "tilt"), _ch(4, "tilt_fine", is_fine=True, coarse=3),
    ]

    ch_map = _service()._build_channel_map(channels)

    assert ch_map["pan"] == 0
    assert ch_map["pan_fine"] == 1
    assert ch_map["tilt"] == 2
    assert ch_map["tilt_fine"] == 3


def test_repeated_coarse_channels_resolve_to_the_first():
    """Two gobo wheels: the first is the one an operator means by "gobo"."""
    channels = [_ch(7, "gobo"), _ch(9, "gobo")]

    assert _service()._build_channel_map(channels)["gobo"] == 6


def test_a_fine_only_channel_is_still_reachable():
    """Nothing sensible to prefer, so it should not vanish from the map."""
    channels = [_ch(5, "zoom", is_fine=True, coarse=None)]

    assert _service()._build_channel_map(channels)["zoom"] == 4


def test_channel_order_in_the_profile_does_not_change_the_result():
    """Profiles are not guaranteed to arrive sorted by channel number."""
    forward = [_ch(15, "dimmer"), _ch(16, "dimmer", is_fine=True, coarse=15)]
    reversed_rows = list(reversed(forward))

    svc = _service()
    assert svc._build_channel_map(forward) == svc._build_channel_map(reversed_rows)


def test_model_objects_and_dicts_agree():
    """The map accepts ORM rows as well as dicts; both must resolve identically."""
    class Row:
        def __init__(self, number, ctype, is_fine):
            self.channel_number = number
            self.channel_type = ctype
            self.is_fine = is_fine

    rows = [Row(15, "dimmer", False), Row(16, "dimmer", True)]
    dicts = [_ch(15, "dimmer"), _ch(16, "dimmer", is_fine=True, coarse=15)]

    svc = _service()
    assert svc._build_channel_map(rows) == svc._build_channel_map(dicts)
