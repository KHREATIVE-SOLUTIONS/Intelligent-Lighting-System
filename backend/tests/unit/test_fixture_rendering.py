"""
Fixture Rendering Unit Tests
============================

Exact DMX bytes produced by FixtureGroupManager for profile-driven channel maps.
"""

from app.services.effects.fixture_groups import (
    Fixture,
    FixtureGroupManager,
    create_demo_rig,
)


MOVER_FINE_CHANNELS = {
    'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
    'dimmer': 4, 'shutter': 5,
    'red': 6, 'green': 7, 'blue': 8, 'white': 9,
}

MOVER_COARSE_CHANNELS = {
    'pan': 0, 'tilt': 1,
    'dimmer': 2, 'shutter': 3,
    'red': 4, 'green': 5, 'blue': 6,
}

# -154 deg of 540 and +77 deg of 270 are picked because the 8-bit scale and the high
# byte of the 16-bit scale disagree there, so a coarse-only channel that emits a
# 16-bit high byte is distinguishable from one that emits a true 8-bit value.
PAN_ANGLE = -154.0
TILT_ANGLE = 77.0
PAN_COARSE_16, PAN_FINE_16 = 54, 254
TILT_COARSE_16, TILT_FINE_16 = 201, 1
PAN_8 = 55
TILT_8 = 200


def _manager(*fixtures) -> FixtureGroupManager:
    manager = FixtureGroupManager()
    manager.add_fixtures(list(fixtures))
    return manager


def test_moving_head_with_fine_channels_emits_16_bit_pan_and_tilt():
    fixture = Fixture(
        id="mh1",
        name="MH 1",
        dmx_address=1,
        channels=dict(MOVER_FINE_CHANNELS),
        fixture_type="mover",
    )
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == PAN_COARSE_16
    assert frame[1] == PAN_FINE_16
    assert frame[2] == TILT_COARSE_16
    assert frame[3] == TILT_FINE_16


def test_moving_head_without_fine_channels_emits_8_bit_coarse_only():
    fixture = Fixture(
        id="mh2",
        name="MH 2",
        dmx_address=1,
        channels=dict(MOVER_COARSE_CHANNELS),
        fixture_type="mover",
    )
    fixture.pan = PAN_ANGLE
    fixture.tilt = TILT_ANGLE

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == PAN_8
    assert frame[1] == TILT_8


def test_non_default_pan_range_changes_the_emitted_pan_byte():
    narrow = Fixture(
        id="mh540",
        name="MH 540",
        dmx_address=1,
        channels=dict(MOVER_COARSE_CHANNELS),
        fixture_type="mover",
        pan_range=540.0,
    )
    wide = Fixture(
        id="mh630",
        name="MH 630",
        dmx_address=11,
        channels=dict(MOVER_COARSE_CHANNELS),
        fixture_type="mover",
        pan_range=630.0,
    )
    narrow.pan = PAN_ANGLE
    wide.pan = PAN_ANGLE

    frame = _manager(narrow, wide).get_dmx_frame(0)

    assert frame[0] == 55
    assert frame[10] == 65


def test_zero_pan_range_fixture_emits_no_movement():
    fixture = Fixture(
        id="par_static",
        name="Static Par",
        dmx_address=1,
        channels={'pan': 0, 'tilt': 1, 'dimmer': 2},
        fixture_type="wash",
        pan_range=0.0,
        tilt_range=0.0,
    )
    fixture.pan = 90.0
    fixture.tilt = 45.0
    fixture.dimmer = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 0
    assert frame[1] == 0
    assert frame[2] == 255


def test_virtual_dimmer_scales_colour_when_profile_has_no_dimmer():
    fixture = Fixture(
        id="par_nodim",
        name="Par No Dimmer",
        dmx_address=1,
        channels={'red': 0, 'green': 1, 'blue': 2, 'white': 3},
        fixture_type="wash",
    )
    fixture.dimmer = 0.5
    fixture.red = 1.0
    fixture.green = 0.0
    fixture.blue = 0.0
    fixture.white = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] in (127, 128)
    assert frame[1] == 0
    assert frame[2] == 0
    assert frame[3] in (127, 128)


def test_virtual_dimmer_at_zero_blacks_out_colour():
    fixture = Fixture(
        id="par_nodim_off",
        name="Par No Dimmer Off",
        dmx_address=1,
        channels={'red': 0, 'green': 1, 'blue': 2},
        fixture_type="wash",
    )
    fixture.dimmer = 0.0
    fixture.red = 1.0
    fixture.green = 1.0
    fixture.blue = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 0
    assert frame[1] == 0
    assert frame[2] == 0


def test_dimmer_channel_present_does_not_double_scale_colour():
    fixture = Fixture(
        id="par_dim",
        name="Par With Dimmer",
        dmx_address=1,
        channels={'dimmer': 0, 'red': 1, 'green': 2, 'blue': 3},
        fixture_type="wash",
    )
    fixture.dimmer = 0.5
    fixture.red = 1.0
    fixture.green = 1.0
    fixture.blue = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 127
    assert frame[1] == 255
    assert frame[2] == 255
    assert frame[3] == 255


def test_other_channels_are_never_written():
    fixture = Fixture(
        id="with_other",
        name="With Other",
        dmx_address=1,
        channels={'dimmer': 0, 'other': 1, 'red': 2},
        fixture_type="wash",
    )
    fixture.dimmer = 1.0
    fixture.red = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 255
    assert frame[1] == 0
    assert frame[2] == 255


def test_shutter_defaults_to_open_when_not_strobing():
    fixture = Fixture(
        id="shutter_fix",
        name="Shutter Fixture",
        dmx_address=1,
        channels={'dimmer': 0, 'shutter': 1},
        fixture_type="mover",
    )
    fixture.dimmer = 1.0
    fixture.strobe = 0.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[1] == 255


def test_shutter_carries_the_strobe_rate_while_strobing():
    fixture = Fixture(
        id="shutter_strobing",
        name="Shutter Strobing",
        dmx_address=1,
        channels={'dimmer': 0, 'shutter': 1},
        fixture_type="mover",
    )
    fixture.dimmer = 1.0
    fixture.strobe = 0.5

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[1] == 127


def test_dedicated_strobe_channel_is_zero_when_not_strobing():
    fixture = Fixture(
        id="strobe_ch",
        name="Strobe Channel",
        dmx_address=1,
        channels={'dimmer': 0, 'strobe': 1},
        fixture_type="bar",
    )
    fixture.dimmer = 1.0
    fixture.strobe = 0.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 255
    assert frame[1] == 0


def test_profile_channels_outside_the_core_set_are_emitted():
    fixture = Fixture(
        id="rich",
        name="Rich Profile",
        dmx_address=1,
        channels={
            'dimmer': 0, 'amber': 1, 'uv': 2, 'zoom': 3, 'focus': 4,
            'gobo': 5, 'gobo_rotation': 6, 'prism': 7, 'color_wheel': 8,
        },
        fixture_type="mover",
    )
    fixture.dimmer = 1.0
    fixture.amber = 1.0
    fixture.uv = 1.0
    fixture.zoom = 1.0
    fixture.focus = 1.0
    fixture.gobo = 1.0
    fixture.gobo_rotation = 1.0
    fixture.prism = 1.0
    fixture.color_wheel = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0:9] == [255] * 9


def test_channel_limits_clamp_emitted_values():
    fixture = Fixture(
        id="limited",
        name="Limited",
        dmx_address=1,
        channels={'dimmer': 0, 'red': 1},
        fixture_type="wash",
        channel_limits={'dimmer': (0, 200), 'red': (10, 255)},
    )
    fixture.dimmer = 1.0
    fixture.red = 0.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[0] == 200
    # A profile floor describes a channel's usable range, not a mandatory output. It
    # must not apply at zero, or the fixture could never reach true black.
    assert frame[1] == 0

    fixture.red = 0.01
    frame = _manager(fixture).get_dmx_frame(0)
    assert frame[1] == 10


def test_fixture_writes_at_its_absolute_dmx_address():
    fixture = Fixture(
        id="addr100",
        name="Addr 100",
        dmx_address=100,
        channels={'dimmer': 0, 'red': 1},
        fixture_type="wash",
    )
    fixture.dimmer = 1.0
    fixture.red = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[99] == 255
    assert frame[100] == 255
    assert frame[98] == 0
    assert frame[101] == 0


def test_fixture_overrunning_the_universe_does_not_corrupt_the_frame():
    overrun = Fixture(
        id="overrun",
        name="Overrun",
        dmx_address=510,
        channels={'dimmer': 0, 'red': 1, 'green': 2, 'blue': 3},
        fixture_type="wash",
    )
    beyond = Fixture(
        id="beyond",
        name="Beyond",
        dmx_address=600,
        channels={'dimmer': 0, 'red': 1},
        fixture_type="wash",
    )
    for fixture in (overrun, beyond):
        fixture.dimmer = 1.0
        fixture.red = 1.0
        fixture.green = 1.0
        fixture.blue = 1.0

    frame = _manager(overrun, beyond).get_dmx_frame(0)

    assert len(frame) == 512
    assert frame[509] == 255
    assert frame[510] == 255
    assert frame[511] == 255
    assert all(0 <= value <= 255 for value in frame)
    assert sum(frame[:509]) == 0


def test_multi_universe_frames_do_not_bleed():
    u0 = Fixture(
        id="u0",
        name="U0",
        dmx_address=1,
        channels={'dimmer': 0},
        fixture_type="wash",
        universe=0,
    )
    u1 = Fixture(
        id="u1",
        name="U1",
        dmx_address=100,
        channels={'dimmer': 0},
        fixture_type="wash",
        universe=1,
    )
    u3 = Fixture(
        id="u3",
        name="U3",
        dmx_address=200,
        channels={'dimmer': 0},
        fixture_type="wash",
        universe=3,
    )
    u0.dimmer = 1.0
    u1.dimmer = 0.5
    u3.dimmer = 1.0

    manager = _manager(u0, u1, u3)
    frames = manager.get_dmx_frames()

    assert manager.get_universes() == [0, 1, 3]
    assert sorted(frames.keys()) == [0, 1, 3]
    assert all(len(frame) == 512 for frame in frames.values())

    assert frames[0][0] == 255
    assert sum(frames[0][1:]) == 0

    assert frames[1][99] == 127
    assert sum(frames[1]) == 127

    assert frames[3][199] == 255
    assert sum(frames[3]) == 255

    assert frames[1] == manager.get_dmx_frame(1)


def test_has_channel_reports_profile_channels():
    fixture = Fixture(
        id="probe",
        name="Probe",
        dmx_address=1,
        channels={'dimmer': 0, 'red': 1},
        fixture_type="wash",
    )

    assert fixture.has_channel('dimmer')
    assert fixture.has_channel('red')
    assert not fixture.has_channel('pan')


def test_empty_manager_renders_a_blank_frame():
    manager = FixtureGroupManager()

    frame = manager.get_dmx_frame(0)

    assert len(frame) == 512
    assert max(frame) == 0
    assert manager.get_universes() == []
    assert manager.get_dmx_frames() == {}


def test_adding_a_fixture_does_not_wipe_custom_groups():
    manager = create_demo_rig()

    assert len(manager.get_fixtures_in_group("movers")) == 8
    assert len(manager.get_fixtures_in_group("washes")) == 6

    manager.add_fixture(Fixture(
        id="late",
        name="Late Arrival",
        dmx_address=300,
        channels={'dimmer': 0},
        fixture_type="wash",
    ))

    assert len(manager.get_fixtures_in_group("movers")) == 8
    assert len(manager.get_fixtures_in_group("washes")) == 6
    assert len(manager.get_fixtures_in_group("all")) == 19


def test_adding_a_fixture_does_not_wipe_custom_phase_offsets():
    manager = create_demo_rig()
    first_two = [f.id for f in manager.get_fixtures_in_group("movers")[:2]]

    manager.create_custom_group("pair", first_two, phase_offsets=[0.0, 0.75])
    assert manager.get_group("pair").phase_offsets == [0.0, 0.75]

    manager.add_fixture(Fixture(
        id="late",
        name="Late Arrival",
        dmx_address=300,
        channels={'dimmer': 0},
        fixture_type="wash",
    ))

    # The trailing phase-offset pass in _update_group_assignments recomputes
    # evenly-spaced offsets for every group, silently discarding the explicit
    # ones the caller supplied. Guarding fixture_ids alone does not fix this.
    assert manager.get_group("pair").phase_offsets == [0.0, 0.75]


def test_demo_rig_still_renders():
    manager = create_demo_rig()

    assert len(manager.fixtures) == 18

    for fixture in manager.fixtures.values():
        fixture.dimmer = 1.0

    frame = manager.get_dmx_frame(0)

    assert len(frame) == 512
    assert frame[5] == 255
    assert frame[212] == 255


CMY_SPOT_CHANNELS = {
    'dimmer': 0, 'cyan': 1, 'magenta': 2, 'yellow': 3,
    'cto': 4, 'ctb': 5, 'iris': 6, 'frost': 7,
    'gobo': 8, 'gobo2': 9, 'gobo2_rotation': 10, 'animation': 11, 'framing': 12,
}

# An RGB+ LED engine whose cyan is an emitter, not a subtractive flag.
ADDITIVE_LED_CHANNELS = {
    'dimmer': 0, 'red': 1, 'green': 2, 'blue': 3,
    'lime': 4, 'indigo': 5, 'cyan': 6,
}


def _cmy_fixture(**overrides) -> Fixture:
    fixture = Fixture(
        id="cmy1",
        name="CMY 1",
        dmx_address=1,
        channels=dict(CMY_SPOT_CHANNELS),
        fixture_type="mover",
        pan_range=0.0,
        tilt_range=0.0,
    )
    for name, value in overrides.items():
        setattr(fixture, name, value)
    return fixture


def test_a_subtractive_flag_is_open_when_its_colour_is_wanted():
    fixture = _cmy_fixture(dimmer=1.0, red=1.0, green=0.0, blue=0.0)

    frame = _manager(fixture).get_dmx_frame(0)

    # Cyan absorbs red, so full red means cyan out of the beam and the other
    # two flags fully in.
    assert frame[1] == 0
    assert frame[2] == 255
    assert frame[3] == 255


def _dimmerless_cmy(**overrides) -> Fixture:
    """A CMY head whose profile declares no intensity channel."""
    channels = {name: offset for name, offset in CMY_SPOT_CHANNELS.items()
                if name != 'dimmer'}
    fixture = Fixture(
        id="cmy2",
        name="CMY 2",
        dmx_address=1,
        channels=channels,
        fixture_type="mover",
        pan_range=0.0,
        tilt_range=0.0,
    )
    for name, value in overrides.items():
        setattr(fixture, name, value)
    return fixture


def test_a_blackout_does_not_open_every_subtractive_flag_to_white():
    lit = _manager(_dimmerless_cmy(dimmer=1.0, red=1.0, green=1.0, blue=1.0)).get_dmx_frame(0)
    dark = _manager(_dimmerless_cmy(dimmer=0.0, red=1.0, green=1.0, blue=1.0)).get_dmx_frame(0)

    # Without an intensity channel the flags carry the intensity, so open at full
    # white and fully closed at blackout - never the other way round.
    assert lit[1:4] == [0, 0, 0]
    assert dark[1:4] == [255, 255, 255]


def test_an_additive_cyan_emitter_is_not_driven_by_the_subtractive_complement():
    fixture = Fixture(
        id="led1",
        name="LED 1",
        dmx_address=1,
        channels=dict(ADDITIVE_LED_CHANNELS),
        fixture_type="wash",
        pan_range=0.0,
        tilt_range=0.0,
    )
    fixture.dimmer = 0.0
    fixture.red = 1.0
    fixture.green = 1.0
    fixture.blue = 1.0

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[6] == 0, (
        "this fixture declares red/green/blue emitters, so its cyan is an emitter "
        "too; complementing it lights the cyan LED fully at blackout"
    )


def test_lime_and_indigo_emitters_carry_their_own_state():
    fixture = Fixture(
        id="led2",
        name="LED 2",
        dmx_address=1,
        channels=dict(ADDITIVE_LED_CHANNELS),
        fixture_type="wash",
        pan_range=0.0,
        tilt_range=0.0,
    )
    fixture.dimmer = 1.0
    fixture.lime = 1.0
    fixture.indigo = 0.5

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[4] == 255
    assert frame[5] == 127


def test_mechanical_flags_rest_out_of_the_beam():
    frame = _manager(_cmy_fixture(dimmer=1.0)).get_dmx_frame(0)

    # 0 is iris open, frost and colour correction out. Nothing drives these, so
    # a fixture at full must not have them inserted.
    assert [frame[4], frame[5], frame[6], frame[7]] == [0, 0, 0, 0]


def test_a_second_gobo_wheel_is_addressed_separately_from_the_first():
    fixture = _cmy_fixture(dimmer=1.0, gobo=0.25, gobo2=0.75, gobo2_rotation=0.5)

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[8] == 63
    assert frame[9] == 191
    assert frame[10] == 127


def test_a_channel_the_engine_never_drives_parks_at_its_profile_home():
    fixture = _cmy_fixture(dimmer=1.0)
    # A blade rotation's zero is a mechanical end stop, which is why five of the
    # bundled profiles declare 128 as its home.
    fixture.channel_defaults = {'framing': 128}

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[12] == 128


def test_a_repeated_mechanical_channel_follows_its_own_home():
    fixture = _cmy_fixture(dimmer=1.0)
    fixture.channels['framing_2'] = 13
    fixture.channel_defaults = {'framing': 128, 'framing_2': 64}

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[12] == 128
    assert frame[13] == 64


def test_a_commanded_level_still_beats_the_profile_home():
    fixture = _cmy_fixture(dimmer=1.0, gobo=1.0)
    fixture.channel_defaults = {'gobo': 128}

    frame = _manager(fixture).get_dmx_frame(0)

    assert frame[8] == 255
