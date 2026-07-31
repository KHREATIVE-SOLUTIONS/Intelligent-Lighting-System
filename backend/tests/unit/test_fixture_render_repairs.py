"""
Fixture Rendering - Hot-Path Safety
===================================

The renderer runs 30-60 times a second with no try/except above it: anything it
raises is a silently dark rig, not a traceback. These pin the inputs that reach
it from adapters and profiles rather than from the engine's own state.
"""

import pytest

from app.services.effects.fixture_groups import (
    Fixture,
    FixtureGroupManager,
    canonical_channel_name,
    create_demo_rig,
)


ALL_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'dimmer': 4, 'shutter': 5, 'strobe': 6,
    'red': 7, 'green': 8, 'blue': 9, 'white': 10, 'amber': 11, 'uv': 12,
    'zoom': 13, 'focus': 14, 'gobo': 15, 'gobo_rotation': 16,
    'prism': 17, 'color_wheel': 18, 'speed': 19,
}


def _manager(*fixtures) -> FixtureGroupManager:
    manager = FixtureGroupManager()
    manager.add_fixtures(list(fixtures))
    return manager


def _fixture(**overrides) -> Fixture:
    fixture = Fixture(
        id="f1",
        name="F1",
        dmx_address=1,
        channels=dict(ALL_CHANNELS),
        fixture_type="mover",
    )
    for name, value in overrides.items():
        setattr(fixture, name, value)
    return fixture


@pytest.mark.parametrize("attribute", [
    "pan_range", "tilt_range", "channel_limits",
    "dimmer", "pan", "tilt", "strobe", "red", "green", "blue", "white",
    "amber", "uv", "zoom", "focus", "gobo", "gobo_rotation", "prism", "color_wheel",
])
def test_a_none_on_any_state_field_still_renders(attribute):
    """pan_range/tilt_range/channel_limits are set by adapters after construction,
    and the profile columns behind them are nullable."""
    fixture = _fixture(**{attribute: None})

    frame = _manager(fixture).get_dmx_frame(0)

    assert len(frame) == 512
    assert all(0 <= value <= 255 for value in frame)


@pytest.mark.parametrize("limits", [
    None,
    {},
    {'dimmer': None},
    {'dimmer': ()},
    {'dimmer': (10,)},
    {'dimmer': 5},
    {'dimmer': "bad"},
    {'dimmer': [0, 200]},
])
def test_malformed_channel_limits_do_not_break_the_frame(limits):
    fixture = _fixture(dimmer=1.0, channel_limits=limits)

    frame = _manager(fixture).get_dmx_frame(0)

    assert len(frame) == 512
    assert frame[4] in (200, 255)


def test_zero_pan_range_parks_tilt_as_well():
    """A pan_range of 0 marks a fixture that cannot move. Gating per axis leaves a
    static wash latched against its pan end stop, nodding."""
    fixture = Fixture(
        id="static_wash",
        name="Static Wash",
        dmx_address=1,
        channels={'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4},
        fixture_type="wash",
        pan_range=0.0,
        tilt_range=270.0,
    )
    fixture.pan = 60.0
    fixture.tilt = 30.0
    fixture.dimmer = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0:4] == [0, 0, 0, 0]
    assert frame[4] == 255


def test_zero_tilt_range_still_allows_pan():
    fixture = Fixture(
        id="pan_only",
        name="Pan Only",
        dmx_address=1,
        channels={'pan': 0, 'tilt': 1},
        fixture_type="mover",
        pan_range=540.0,
        tilt_range=0.0,
    )
    fixture.pan = 135.0
    fixture.tilt = 60.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 191
    assert frame[1] == 0


def test_repeated_channels_carry_the_canonical_value():
    """Per-cell dimmers ("Cell 1".."Cell 4") share one channel type. Left at 0 the
    fixture emits nothing while its master channel reads full."""
    fixture = Fixture(
        id="cells",
        name="Cell Fixture",
        dmx_address=1,
        channels={'dimmer': 0, 'dimmer_2': 1, 'dimmer_3': 2, 'dimmer_4': 3},
        fixture_type="effect",
    )
    fixture.dimmer = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0:4] == [255, 255, 255, 255]

    fixture.dimmer = 0.0
    assert max(_manager(fixture).get_dmx_frame(0)) == 0


def test_repeated_colour_channels_track_the_first_zone():
    fixture = Fixture(
        id="zones",
        name="Zoned Wash",
        dmx_address=1,
        channels={'dimmer': 0, 'red': 1, 'green': 2, 'blue': 3,
                  'red_2': 4, 'green_2': 5, 'blue_2': 6},
        fixture_type="wash",
    )
    fixture.dimmer = 1.0
    fixture.red = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[1] == 255
    assert frame[4] == 255
    assert frame[2] == frame[5] == 0


def test_a_fine_duplicate_is_not_mirrored():
    """A second channel of the same type that the profile marks as fine is aliased
    under a name the renderer never emits; 0 is the safe fine value."""
    fixture = Fixture(
        id="finedup",
        name="Fine Duplicate",
        dmx_address=1,
        channels={'dimmer': 0, 'dimmer_fine_2': 1},
        fixture_type="wash",
    )
    fixture.dimmer = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 255
    assert frame[1] == 0


def test_an_other_alias_is_never_written():
    fixture = Fixture(
        id="others",
        name="Others",
        dmx_address=1,
        channels={'dimmer': 0, 'other': 1, 'other_2': 2},
        fixture_type="wash",
    )
    fixture.dimmer = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 255
    assert frame[1] == 0
    assert frame[2] == 0


@pytest.mark.parametrize("name,expected", [
    ('dimmer', 'dimmer'),
    ('dimmer_2', 'dimmer'),
    ('pan_fine', 'pan_fine'),
    ('pan_fine_2', 'pan_fine'),
    ('dimmer_fine_2', 'dimmer_fine'),
    ('gobo_rotation', 'gobo_rotation'),
])
def test_canonical_channel_name(name, expected):
    assert canonical_channel_name(name) == expected


def test_demo_rig_bytes_are_pinned():
    """Every non-zero byte the demo rig emits at full dimmer, so a renderer change
    that moves output onto another channel cannot pass unnoticed."""
    manager = create_demo_rig()
    for fixture in manager.fixtures.values():
        fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    # 8 movers on 16 channels from 1, 6 washes on 14 from 129, 4 bars on 12 from 213.
    for base in (0, 16, 32, 48, 64, 80, 96, 112):
        assert frame[base + 0] == 128, "pan centred"
        assert frame[base + 1] == 0
        assert frame[base + 2] == 128, "tilt centred"
        assert frame[base + 3] == 0
        assert frame[base + 5] == 255, "dimmer"
        assert frame[base + 6] == 255, "shutter open"
        assert frame[base + 15] == 127, "focus mid-scale"
        assert sum(frame[base + 7:base + 15]) == 0

    for base in (128, 142, 156, 170, 184, 198):
        assert frame[base + 0] == 128
        assert frame[base + 2] == 128
        assert frame[base + 5] == 255
        assert frame[base + 6] == 255
        assert frame[base + 11] == 127, "zoom mid-scale"
        assert frame[base + 12] == 0, "unknown channel types are never written"
        assert frame[base + 13] == 0

    for base in (212, 224, 236, 248):
        assert frame[base + 0] == 255, "dimmer"
        assert sum(frame[base + 1:base + 12]) == 0

    assert sum(1 for value in frame if value) == 74
