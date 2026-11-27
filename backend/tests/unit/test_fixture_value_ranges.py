"""
Fixture Value Ranges
====================

A profile's `value_ranges` say which bytes open a shutter, close it and strobe
it. These pin three things: what the resolver reads out of each club profile,
that a rig built from those profiles renders the profile's bytes rather than
the fixed 255 and 0, and that a channel with no ranges is driven exactly as it
was before.

Every expected byte here is written out by hand from the profile JSON. A test
that computed them with the resolver would agree with any bug in it.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from app.api.endpoints.rig_identify import _identify_values
from app.services.dmx.channel_ranges import ChannelRangeValues, resolve_channel_ranges
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager
from app.services.fixture_test.fixture_test_service import FixtureTestService
from app.services.rig.rig_loader import build_manager_from_rig

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures"


def _definition(stem: str) -> Dict[str, Any]:
    for directory in (FIXTURE_DIR / "bundled", FIXTURE_DIR):
        path = directory / f"{stem}.json"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
    pytest.fail(f"no fixture definition named {stem}")


def _mode(stem: str, mode_name: str) -> Dict[str, Any]:
    for mode in _definition(stem)["modes"]:
        if mode["name"] == mode_name:
            return mode
    pytest.fail(f"{stem} has no mode named {mode_name}")


def _channel(stem: str, mode_name: str, number: int) -> Dict[str, Any]:
    for channel in _mode(stem, mode_name)["channels"]:
        if channel["channel_number"] == number:
            return channel
    pytest.fail(f"{stem} {mode_name} has no channel {number}")


# ---------------------------------------------------------------------------
# Open / strobe / closed, per profile
# ---------------------------------------------------------------------------

# (profile, mode, channel number, channel type, open, closed, (slowest, fastest))
# `closed` is None where the channel only rates a strobe and cannot block light.
SHUTTER_AND_STROBE = [
    # Movers. Sourced from OFL:
    ("chauvet_rogue_r2_wash", "15-Channel", 8, "shutter", 255, 0, (64, 25)),
    ("robe_robin_600_ledwash", "18-Channel", 17, "shutter", 255, 0, (64, 95)),
    ("robe_robin_t1_profile", "25-Channel", 23, "shutter", 255, 0, (64, 95)),
    # Movers. Assumed:
    ("robe_robin_pointe", "24-Channel", 22, "shutter", 255, 0, (1, 254)),
    ("robe_robin_megapointe", None, None, "shutter", 255, 0, (1, 254)),
    ("chauvet_rogue_r2_spot", None, None, "shutter", 255, 0, (1, 254)),
    ("chauvet_maverick_mk2_spot", None, None, "shutter", 255, 0, (1, 254)),
    ("chauvet_intimidator_spot_375z", None, None, "shutter", 255, 0, (1, 254)),
    ("chauvet_rogue_r3_wash", None, None, "shutter", 255, 0, (1, 254)),
    ("adj_vizi_beam_12rx", None, None, "shutter", 255, 0, (1, 254)),
    ("adj_focus_spot_5z", None, None, "shutter", 255, 0, (1, 254)),
    ("adj_hydro_wash_x7", None, None, "shutter", 255, 0, (1, 254)),
    ("martin_mac_aura_xb", None, None, "shutter", 255, 0, (1, 254)),
    ("martin_mac_quantum_profile", None, None, "shutter", 255, 0, (1, 254)),
    ("martin_rush_mh6_wash", None, None, "shutter", 255, 0, (1, 254)),
    ("elation_smarty_hybrid", None, None, "shutter", 255, 0, (1, 254)),
    ("elation_fuze_wash_500", None, None, "shutter", 255, 0, (1, 254)),
    ("elation_rayzor_760", None, None, "shutter", 255, 0, (1, 254)),
    ("elation_platinum_fwd", None, None, "shutter", 255, 0, (1, 254)),
    ("robe_robin_spikie", None, None, "shutter", 255, 0, (1, 254)),
    ("generic_moving_head", "Standard (16ch)", 7, "shutter", 255, 0, (1, 254)),
    ("generic_moving_head", "Basic (8ch)", 4, "shutter", 255, 0, (1, 254)),
    # Pars and battens. Sourced from OFL - note where 0 is "closed":
    ("adj_mega_tripar_profile", "5-Channel", 5, "strobe", 47, 0, (64, 95)),
    ("elation_sixpar_200", "10-Channel", 8, "strobe", 111, 0, (32, 95)),
    ("martin_rush_par_2_rgbw", "8-Channel", 6, "strobe", 11, 0, (16, 131)),
    ("adj_ultra_hex_bar_12", "12-Channel", 8, "strobe", 47, 0, (64, 95)),
    ("chauvet_slimpar_pro_h", "10-Channel", 8, "strobe", 0, None, (16, 255)),
    ("adj_dotz_par", "5-Channel", 5, "strobe", 0, None, (1, 255)),
    ("etc_colorsource_par", "5-Channel", 5, "strobe", 0, None, (1, 254)),
    # Pars and battens. Assumed:
    ("adj_mega_go_par", None, None, "strobe", 0, None, (1, 255)),
    ("chauvet_freedom_par_quad_4", None, None, "strobe", 0, None, (1, 255)),
    ("chauvet_colorado_pxl_bar_16", None, None, "strobe", 0, None, (1, 255)),
    ("generic_led_par", "8 Channel", 6, "strobe", 0, None, (1, 255)),
    # Dedicated strobes. Assumed:
    ("martin_rush_strobe_cw", "3-Channel", 2, "strobe", 0, None, (1, 255)),
    ("martin_rush_strobe_cw", "7-Channel", 3, "strobe", 0, None, (1, 255)),
    ("chauvet_strike_array_4", "5-Channel", 2, "strobe", 0, None, (1, 255)),
    ("chauvet_strike_array_4", "13-Channel", 5, "strobe", 0, None, (1, 255)),
    ("chauvet_strike_array_4", "13-Channel", 13, "strobe", 0, None, (1, 255)),
]


def _targets(stem, mode_name, number, kind) -> List[Dict[str, Any]]:
    """The named channel, or every coarse channel of that type in the profile."""
    if mode_name is not None:
        return [_channel(stem, mode_name, number)]
    found = [
        channel
        for mode in _definition(stem)["modes"]
        for channel in mode["channels"]
        if channel["channel_type"] == kind and not channel.get("is_fine")
    ]
    assert found, f"{stem} has no {kind} channel"
    return found


@pytest.mark.parametrize(
    "stem, mode_name, number, kind, open_value, closed_value, strobe_span",
    SHUTTER_AND_STROBE,
    ids=[f"{row[0]}:{row[1] or 'every mode'}:{row[2] or row[3]}" for row in SHUTTER_AND_STROBE],
)
def test_the_profile_names_open_strobe_and_closed(
        stem, mode_name, number, kind, open_value, closed_value, strobe_span):
    for channel in _targets(stem, mode_name, number, kind):
        assert channel["channel_type"] == kind
        assert channel.get("value_ranges"), f"{stem} {channel['name']} carries no ranges"

        values = resolve_channel_ranges(kind, channel["value_ranges"])

        assert values is not None
        assert values.open == open_value
        assert values.closed == closed_value
        assert values.strobe == strobe_span
        # The bytes a writer is handed.
        assert values.open_byte() == open_value
        assert values.strobe_byte(0.0) == open_value, "a rate of 0 is open, never a strobe byte"
        assert values.strobe_byte(1.0) == strobe_span[1]
        assert values.closed_byte() == (open_value if closed_value is None else closed_value)


DIMMERS = [
    ("robe_robin_pointe", "24-Channel", 23),
    ("chauvet_rogue_r2_wash", "15-Channel", 6),
    ("martin_mac_aura_xb", None, None),
    ("adj_mega_tripar_profile", "5-Channel", 4),
    ("chauvet_slimpar_pro_h", "10-Channel", 1),
    ("elation_sixpar_200", "10-Channel", 1),
    ("adj_ultra_hex_bar_12", "12-Channel", 7),
    ("chauvet_colorado_pxl_bar_16", None, None),
    ("chauvet_colorband_pix_m", None, None),
    ("martin_rush_strobe_cw", "3-Channel", 1),
    ("chauvet_strike_array_4", "5-Channel", 1),
    ("generic_led_par", "8 Channel", 1),
    ("generic_moving_head", "Standard (16ch)", 6),
]


@pytest.mark.parametrize("stem, mode_name, number", DIMMERS,
                         ids=[f"{row[0]}:{row[1] or 'first'}" for row in DIMMERS])
def test_the_profile_names_its_dimmer_travel(stem, mode_name, number):
    channel = _targets(stem, mode_name, number, "dimmer")[0]

    values = resolve_channel_ranges("dimmer", channel.get("value_ranges"))

    assert values is not None, f"{stem} {channel['name']} carries no dimmer range"
    assert values.dimmer == (0, 255)
    assert values.dimmer_byte(0.0) == 0
    assert values.dimmer_byte(0.25) == 63
    assert values.dimmer_byte(1.0) == 255


def test_an_assumed_range_says_so_and_a_sourced_one_does_not():
    pointe = _channel("robe_robin_pointe", "24-Channel", 22)
    rogue = _channel("chauvet_rogue_r2_wash", "15-Channel", 8)

    assert resolve_channel_ranges("shutter", pointe["value_ranges"]).assumed is True
    assert resolve_channel_ranges("shutter", rogue["value_ranges"]).assumed is False
    assert all("(assumed)" in entry["name"] for entry in pointe["value_ranges"])


# ---------------------------------------------------------------------------
# The resolver's own rules
# ---------------------------------------------------------------------------


def test_a_strobe_range_that_runs_fast_to_slow_is_read_backwards():
    ranges = [
        {"name": "Closed", "min_value": 0, "max_value": 19},
        {"name": "Open", "min_value": 20, "max_value": 24},
        {"name": "Strobe 20Hz->0Hz", "min_value": 25, "max_value": 64},
        {"name": "Open", "min_value": 245, "max_value": 255},
    ]

    values = resolve_channel_ranges("shutter", ranges)

    assert values.strobe == (64, 25)
    assert values.strobe_byte(1.0) == 25, "full rate is the fast end"
    assert values.strobe_byte(0.5) == 45
    assert 25 <= values.strobe_byte(0.01) <= 64


def test_random_pulse_ramp_and_zone_ranges_are_never_taken_for_the_strobe():
    ranges = [
        {"name": "Closed", "min_value": 0, "max_value": 31},
        {"name": "Strobe 0.3Hz->20Hz (Outer zone)", "min_value": 32, "max_value": 63},
        {"name": "Strobe 0.3Hz->20Hz", "min_value": 64, "max_value": 95},
        {"name": "Ramp up slow->fast", "min_value": 128, "max_value": 143},
        {"name": "Pulse", "min_value": 144, "max_value": 159},
        {"name": "Strobe slow->fast (random)", "min_value": 192, "max_value": 223},
        {"name": "Open", "min_value": 224, "max_value": 255},
    ]

    assert resolve_channel_ranges("shutter", ranges).strobe == (64, 95)


def test_a_shutter_whose_open_range_is_not_at_255_opens_where_the_profile_says():
    ranges = [
        {"name": "Closed", "min_value": 0, "max_value": 19},
        {"name": "Open", "min_value": 20, "max_value": 49},
        {"name": "Strobe fast->slow", "min_value": 50, "max_value": 200},
        {"name": "Strobe (random)", "min_value": 211, "max_value": 255},
    ]

    values = resolve_channel_ranges("shutter", ranges)

    assert values.open_byte() == 34, "255 is a random strobe on this fixture"
    assert values.closed_byte() == 0
    assert values.strobe == (200, 50)


def test_ranges_with_no_strobe_span_hold_the_channel_open_at_any_rate():
    ranges = [
        {"name": "Closed", "min_value": 0, "max_value": 10},
        {"name": "Open", "min_value": 11, "max_value": 255},
    ]

    values = resolve_channel_ranges("shutter", ranges)

    assert values.strobe is None
    assert values.strobe_byte(1.0) == 255
    assert values.strobe_byte(0.4) == 255


@pytest.mark.parametrize("ranges", [
    None,
    [],
    "bad",
    [None, 5, "x"],
    [{"name": "Open"}],
    [{"name": "Open", "min_value": "a", "max_value": 9}],
    [{"name": "Open", "min_value": -1, "max_value": 300}],
    [{"name": "Gobo 3", "min_value": 0, "max_value": 255}],
])
def test_ranges_that_say_nothing_usable_resolve_to_nothing(ranges):
    assert resolve_channel_ranges("shutter", ranges) is None
    assert resolve_channel_ranges("strobe", ranges) is None
    assert resolve_channel_ranges("dimmer", ranges) is None


def test_only_shutter_strobe_and_dimmer_channels_are_resolved():
    ranges = [{"name": "Open", "min_value": 0, "max_value": 255}]

    assert resolve_channel_ranges("gobo", ranges) is None
    assert resolve_channel_ranges(None, ranges) is None


@pytest.mark.parametrize("rate", [None, "fast", float("nan"), float("inf"), -1.0])
def test_a_garbage_rate_is_no_strobe(rate):
    values = ChannelRangeValues(kind="strobe", open=47, closed=0, strobe=(64, 95))

    assert values.strobe_byte(rate) == 47


# ---------------------------------------------------------------------------
# Profile -> rig loader -> engine -> DMX
# ---------------------------------------------------------------------------


def _patched(stem: str, mode_name: str, address: int = 1):
    """A rig holding one fixture, built from the bundled definition without a
    database: the loader only reads attributes."""
    data = _definition(stem)
    profile = SimpleNamespace(
        id=1, manufacturer=data["manufacturer"], model=data["model"],
        fixture_type=data.get("fixture_type"),
        pan_range=data.get("pan_range", 540.0), tilt_range=data.get("tilt_range", 270.0),
        modes=[],
    )
    mode_data = _mode(stem, mode_name)
    mode = SimpleNamespace(
        id=1, fixture_id=1, name=mode_data["name"],
        channel_count=mode_data.get("channel_count", len(mode_data["channels"])),
        channels=[
            SimpleNamespace(
                id=index, channel_number=ch["channel_number"], channel_type=ch["channel_type"],
                name=ch.get("name"), default_value=ch.get("default_value", 0),
                min_value=ch.get("min_value", 0), max_value=ch.get("max_value", 255),
                is_fine=ch.get("is_fine", False), coarse_channel=ch.get("coarse_channel"),
                value_ranges=ch.get("value_ranges"),
            )
            for index, ch in enumerate(mode_data["channels"], start=1)
        ],
    )
    profile.modes.append(mode)
    patch = SimpleNamespace(
        id=1, name="Under Test", fixture=profile, mode=mode, mode_id=1,
        dmx_address=address, universe=0, is_active=True, group_name=None, zone=None,
        position_x=0.0, position_y=0.0, position_z=0.0,
    )
    rig = SimpleNamespace(id=1, name="Value Range Rig", fixtures=[patch])

    manager = build_manager_from_rig(rig)
    fixture = manager.fixtures["rf1"]
    return manager, fixture


def _lit(fixture: Fixture, strobe: float = 0.0) -> None:
    fixture.dimmer = 1.0
    fixture.red = fixture.green = fixture.blue = 1.0
    fixture.strobe = strobe


def test_a_par_whose_strobe_channel_names_zero_closed_rests_on_open_not_zero():
    """The fixed number was 0, and on this par 0-31 is "Closed": lit by the
    engine, dark in the room."""
    manager, fixture = _patched("adj_mega_tripar_profile", "5-Channel")
    assert fixture.channels["strobe"] == 4 and fixture.channels["dimmer"] == 3

    _lit(fixture)
    frame = manager.get_dmx_frame(0)

    assert frame[0:4] == [255, 255, 255, 255], "colour and dimmer"
    assert frame[4] == 47, "the middle of the profile's first Open range, 32-63"


def test_a_par_strobes_inside_its_own_strobe_range():
    manager, fixture = _patched("adj_mega_tripar_profile", "5-Channel")

    _lit(fixture, strobe=1.0)
    assert manager.get_dmx_frame(0)[4] == 95, "fastest plain strobe, not 255 (which is Open)"

    _lit(fixture, strobe=0.5)
    assert manager.get_dmx_frame(0)[4] == 79

    _lit(fixture, strobe=0.01)
    assert manager.get_dmx_frame(0)[4] == 64, "the slow end, never a byte below the range"


def test_a_mover_with_sourced_ranges_opens_and_strobes_on_the_profiles_bytes():
    manager, fixture = _patched("chauvet_rogue_r2_wash", "15-Channel", address=101)
    assert fixture.channels["shutter"] == 7 and fixture.channels["dimmer"] == 5

    _lit(fixture)
    frame = manager.get_dmx_frame(0)
    assert frame[100 + 5] == 255
    assert frame[100 + 7] == 255, "255 sits in this profile's last Open range, so it stays"

    # The fixed mapping would send 255 (open: no strobe at all) and 127 (a
    # random-strobe slot). The profile's strobe range is 25-64, fast end first.
    _lit(fixture, strobe=1.0)
    assert manager.get_dmx_frame(0)[100 + 7] == 25
    _lit(fixture, strobe=0.5)
    assert manager.get_dmx_frame(0)[100 + 7] == 45


def test_a_mover_with_assumed_ranges_keeps_the_bytes_it_always_had_at_rest():
    manager, fixture = _patched("robe_robin_pointe", "24-Channel")
    assert fixture.channels["shutter"] == 21 and fixture.channels["dimmer"] == 22
    assert fixture.range_values["shutter"].assumed is True

    _lit(fixture)
    frame = manager.get_dmx_frame(0)
    assert frame[21] == 255, "shutter open"
    assert frame[22] == 255, "dimmer full"

    _lit(fixture, strobe=1.0)
    assert manager.get_dmx_frame(0)[21] == 254, "top of the assumed strobe range, not 255 (open)"

    fixture.dimmer = 0.25
    assert manager.get_dmx_frame(0)[22] == 63
    fixture.dimmer = 0.0
    assert manager.get_dmx_frame(0)[22] == 0


def test_a_dedicated_strobe_rates_its_flash_from_the_profile():
    manager, fixture = _patched("martin_rush_strobe_cw", "3-Channel", address=201)
    assert fixture.fixture_type == "strobe"
    assert fixture.channels["dimmer"] == 0 and fixture.channels["strobe"] == 1

    _lit(fixture)
    frame = manager.get_dmx_frame(0)
    assert frame[200] == 255
    assert frame[201] == 0, "not strobing"

    _lit(fixture, strobe=1.0)
    assert manager.get_dmx_frame(0)[201] == 255
    _lit(fixture, strobe=0.5)
    assert manager.get_dmx_frame(0)[201] == 128


def test_the_loader_carries_ranges_only_for_channels_that_have_them():
    _manager, tripar = _patched("adj_mega_tripar_profile", "5-Channel")
    assert set(tripar.range_values) == {"dimmer", "strobe"}

    _manager, bare = _patched("adj_mega_tripar_profile", "3-Channel")
    assert bare.range_values == {}

    _manager, pointe = _patched("robe_robin_pointe", "24-Channel")
    assert set(pointe.range_values) == {"dimmer", "shutter"}, "the fine dimmer byte has none"


# ---------------------------------------------------------------------------
# The same fixture, with and without ranges
# ---------------------------------------------------------------------------

CHANNELS = {'dimmer': 0, 'shutter': 1, 'strobe': 2, 'red': 3}

SHUTTER_RANGES = [
    {"name": "Closed", "min_value": 0, "max_value": 19},
    {"name": "Open", "min_value": 20, "max_value": 49},
    {"name": "Strobe slow->fast", "min_value": 50, "max_value": 200},
    {"name": "Strobe (random)", "min_value": 211, "max_value": 255},
]
STROBE_RANGES = [
    {"name": "Closed", "min_value": 0, "max_value": 31},
    {"name": "Open", "min_value": 32, "max_value": 63},
    {"name": "Strobe slow->fast", "min_value": 64, "max_value": 95},
]


def _frame(strobe: float, range_values: Optional[Dict[str, Any]] = None) -> List[int]:
    fixture = Fixture(id="f", name="F", dmx_address=1, channels=dict(CHANNELS),
                      fixture_type="wash", pan_range=0.0, tilt_range=0.0)
    if range_values is not None:
        fixture.range_values = range_values
    fixture.dimmer = 1.0
    fixture.red = 1.0
    fixture.strobe = strobe
    manager = FixtureGroupManager()
    manager.add_fixtures([fixture])
    return manager.get_dmx_frame(0)[:4]


def test_without_ranges_the_fixed_numbers_still_go_out():
    assert _frame(0.0) == [255, 255, 0, 255]
    assert _frame(1.0) == [255, 255, 255, 255]
    assert _frame(0.5) == [255, 127, 127, 255]


def test_with_ranges_the_profiles_bytes_go_out_instead():
    ranges = {
        "shutter": resolve_channel_ranges("shutter", SHUTTER_RANGES),
        "strobe": resolve_channel_ranges("strobe", STROBE_RANGES),
    }

    assert _frame(0.0, ranges) == [255, 34, 47, 255], "open, and resting on Open"
    assert _frame(1.0, ranges) == [255, 200, 95, 255]
    assert _frame(0.5, ranges) == [255, 125, 79, 255]


@pytest.mark.parametrize("range_values", [
    None, {}, "bad", {"shutter": None}, {"shutter": "bad"}, {"shutter": [0, 255]},
    {"strobe": {"open": 5}},
])
def test_malformed_range_values_fall_back_to_the_fixed_numbers(range_values):
    fixture = Fixture(id="f", name="F", dmx_address=1, channels=dict(CHANNELS),
                      fixture_type="wash", pan_range=0.0, tilt_range=0.0)
    fixture.range_values = range_values
    fixture.dimmer = 1.0
    manager = FixtureGroupManager()
    manager.add_fixtures([fixture])

    assert manager.get_dmx_frame(0)[:3] == [255, 255, 0]


def test_a_repeated_strobe_channel_answers_in_its_own_ranges():
    fixture = Fixture(id="f", name="F", dmx_address=1,
                      channels={'dimmer': 0, 'strobe': 1, 'strobe_2': 2},
                      fixture_type="strobe", pan_range=0.0, tilt_range=0.0)
    fixture.range_values = {"strobe_2": resolve_channel_ranges("strobe", STROBE_RANGES)}
    fixture.dimmer = 1.0
    manager = FixtureGroupManager()
    manager.add_fixtures([fixture])

    assert manager.get_dmx_frame(0)[:3] == [255, 0, 47]
    fixture.strobe = 1.0
    assert manager.get_dmx_frame(0)[:3] == [255, 255, 95]


# ---------------------------------------------------------------------------
# Fixture test and identify
# ---------------------------------------------------------------------------


def test_the_fixture_test_opens_light_on_the_profiles_bytes():
    service = FixtureTestService(dmx_controller=None)
    channels = _mode("adj_mega_tripar_profile", "5-Channel")["channels"]

    ch_map = service._build_channel_map(channels)
    open_values = service._build_open_values(channels)

    assert open_values == {"strobe": 47}
    values: Dict[int, int] = {}
    service._open_light(values, ch_map, open_values)
    assert values == {4: 47}, "the strobe channel is lifted off Closed"


def test_the_fixture_test_opens_a_shutter_where_the_profile_says():
    service = FixtureTestService(dmx_controller=None)
    channels = [
        {"channel_number": 1, "channel_type": "dimmer"},
        {"channel_number": 2, "channel_type": "shutter", "value_ranges": SHUTTER_RANGES},
    ]

    values: Dict[int, int] = {}
    service._open_light(values, service._build_channel_map(channels),
                        service._build_open_values(channels))

    assert values == {1: 34}


def test_the_fixture_test_keeps_its_fixed_numbers_without_ranges():
    service = FixtureTestService(dmx_controller=None)
    channels = [
        {"channel_number": 1, "channel_type": "shutter"},
        {"channel_number": 2, "channel_type": "strobe"},
    ]

    assert service._build_open_values(channels) == {}
    values: Dict[int, int] = {}
    service._open_light(values, service._build_channel_map(channels), None)
    assert values == {0: 255}, "shutter at 255, strobe channel left alone"


def _rows(channels: List[Dict[str, Any]]) -> List[SimpleNamespace]:
    return [
        SimpleNamespace(
            channel_number=ch["channel_number"], channel_type=ch["channel_type"],
            is_fine=ch.get("is_fine", False), default_value=ch.get("default_value", 0),
            value_ranges=ch.get("value_ranges"),
        )
        for ch in channels
    ]


def test_identify_rests_a_strobe_channel_on_open_and_never_inside_a_strobe_range():
    service = FixtureTestService(dmx_controller=None)
    channels = _rows(_mode("adj_mega_tripar_profile", "5-Channel")["channels"])

    values = _identify_values(channels, service._build_channel_map(channels), 200)

    assert values == {0: 200, 1: 200, 2: 200, 3: 200, 4: 47}


def test_identify_opens_a_shutter_where_the_profile_says_and_255_otherwise():
    service = FixtureTestService(dmx_controller=None)
    ranged = _rows([
        {"channel_number": 1, "channel_type": "dimmer"},
        {"channel_number": 2, "channel_type": "shutter", "value_ranges": SHUTTER_RANGES},
        {"channel_number": 3, "channel_type": "strobe"},
    ])
    bare = _rows([
        {"channel_number": 1, "channel_type": "dimmer"},
        {"channel_number": 2, "channel_type": "shutter"},
        {"channel_number": 3, "channel_type": "strobe"},
    ])

    assert _identify_values(ranged, service._build_channel_map(ranged), 255) == {0: 255, 1: 34, 2: 0}
    assert _identify_values(bare, service._build_channel_map(bare), 255) == {0: 255, 1: 255, 2: 0}
