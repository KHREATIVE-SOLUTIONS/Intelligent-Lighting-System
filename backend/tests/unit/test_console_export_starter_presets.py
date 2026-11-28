"""
grandMA2 starter presets (services/console_export/starter_presets.py)
=====================================================================

The palette maths per colour system, the wheel's nearest slot, why a fixture
is left out, the fixed pool slots and labels, and beam presets that only use
the ranges a profile names. Rows are plain namespaces, as in
test_console_export.py: nothing touches a database, a desk or the wire.
"""

from types import SimpleNamespace

import pytest

from app.services.console_export.model import from_rig
from app.services.console_export.starter_presets import (
    BEAM_POOL, COLOUR_POOL, DIMMER_POOL, NO_MODE, PALETTE, additive_mix, build_starter_presets,
    nearest_slot, starter_presets_script, subtractive_mix, wheel_slots,
)


def colour(name):
    return next(c for c in PALETTE if c.name == name)


def ch(number, kind, ranges=None, fine=False):
    return SimpleNamespace(channel_number=number, channel_type=kind, name=kind.title(),
                           value_ranges=ranges, is_fine=fine)


def row(row_id, channels):
    mode = SimpleNamespace(name="Std", channel_count=len(channels or []), channels=channels) if channels is not None else None
    return SimpleNamespace(
        id=row_id, fixture_number=row_id, name=f"Fixture {row_id}", universe=0, dmx_address=row_id * 20,
        position_x=0.0, position_y=5.0, position_z=0.0, rotation_x=0.0, rotation_y=0.0, rotation_z=0.0,
        group_name="All", tags=[], is_active=True,
        fixture=SimpleNamespace(manufacturer="Acme", model=f"Type {row_id}", gdtf_file=None), mode=mode,
    )


WHEEL = [
    {"name": "Open", "min_value": 0, "max_value": 9},
    {"name": "Red", "min_value": 10, "max_value": 19},
    {"name": "Blue", "min_value": 20, "max_value": 29},
    {"name": "Congo Blue", "min_value": 30, "max_value": 39},
    {"name": "Green", "min_value": 40, "max_value": 49},
    {"name": "Red / Yellow", "min_value": 50, "max_value": 59},
    {"name": "Rotation CW fast to slow", "min_value": 128, "max_value": 255},
]
SHUTTER = [
    {"name": "Closed", "min_value": 0, "max_value": 7},
    {"name": "Open", "min_value": 8, "max_value": 15},
    {"name": "Strobe slow to fast", "min_value": 16, "max_value": 131},
    {"name": "Random strobe", "min_value": 132, "max_value": 255},
]


def rig(rows):
    export = from_rig(SimpleNamespace(id=1, name="Starter"), rows)
    return export, build_starter_presets(rows, export)


def test_rgb_mix_is_the_palette_colour():
    assert additive_mix(colour("Red"), ["red", "green", "blue"]) == {"red": 100, "green": 0, "blue": 0}
    assert additive_mix(colour("Light Blue"), ["red", "green", "blue"]) == {"red": 40, "green": 70, "blue": 100}


def test_rgbw_takes_the_white_out_of_the_mix():
    have = ["red", "green", "blue", "white"]
    assert additive_mix(colour("White"), have) == {"red": 0, "green": 0, "blue": 0, "white": 100}
    assert additive_mix(colour("Warm White"), have) == {"red": 50, "green": 28, "blue": 0, "white": 50}
    assert additive_mix(colour("Red"), have)["white"] == 0


def test_rgba_makes_orange_mostly_from_amber():
    assert additive_mix(colour("Orange"), ["red", "green", "blue", "amber"]) == {
        "red": 33, "green": 0, "blue": 0, "amber": 67}


def test_uv_is_used_for_congo_only():
    have = ["red", "green", "blue", "uv"]
    assert additive_mix(colour("Congo"), have)["uv"] == 100
    assert additive_mix(colour("Blue"), have)["uv"] == 0


def test_cmy_is_subtractive():
    assert subtractive_mix(colour("Red")) == {"cyan": 0, "magenta": 100, "yellow": 100}
    assert subtractive_mix(colour("White")) == {"cyan": 0, "magenta": 0, "yellow": 0}
    assert subtractive_mix(colour("Light Blue")) == {"cyan": 60, "magenta": 30, "yellow": 0}


def test_wheel_slots_skip_splits_and_rotation():
    names = [s.name for s in wheel_slots(WHEEL)]
    assert names == ["Open", "Red", "Blue", "Congo Blue", "Green"]


def test_wheel_picks_the_nearest_slot_by_hue():
    slots = wheel_slots(WHEEL)
    assert nearest_slot(colour("Red"), slots)[0].dmx == 14
    assert nearest_slot(colour("Congo"), slots)[0].name == "Congo Blue"
    assert nearest_slot(colour("Blue"), slots)[0].name == "Blue"
    assert nearest_slot(colour("White"), slots)[0].name == "Open"


def test_wheel_with_no_close_slot_says_why():
    slots = wheel_slots(WHEEL)
    slot, why = nearest_slot(colour("Pink"), slots)
    assert slot is None and "no wheel slot is close to Pink" in why
    slot, why = nearest_slot(colour("Warm White"), slots)
    assert slot is None and "CTO" in why
    assert nearest_slot(colour("Red"), wheel_slots(None)) == (None, "its colour wheel names no colour slots")


def test_each_fixture_gets_colour_its_own_way_and_skips_are_listed():
    rows = [
        row(1, [ch(1, "dimmer"), ch(2, "red"), ch(3, "green"), ch(4, "blue"), ch(5, "white")]),
        row(2, [ch(1, "dimmer"), ch(2, "cyan"), ch(3, "magenta"), ch(4, "yellow")]),
        row(3, [ch(1, "dimmer"), ch(2, "color_wheel", WHEEL)]),
        row(4, [ch(1, "dimmer")]),
        row(5, None),
        row(6, [ch(1, "red"), ch(2, "blue")]),
    ]
    _, table = rig(rows)
    red = table.table()["Red"]
    assert red[1] == {"red": 100, "green": 0, "blue": 0, "white": 0}
    assert red[2] == {"cyan": 0, "magenta": 100, "yellow": 100}
    assert red[3] == {"color_wheel": 5.5}
    assert table.preset("Red").dmx[3] == {"color_wheel": 14}
    assert set(red) == {1, 2, 3}
    pink = table.preset("Pink")
    assert 3 not in pink.values and "Pink" in pink.skipped[3]
    reasons = {item["fixture_id"]: item["reason"] for item in table.no_colour}
    assert reasons == {4: "it has no colour control", 5: NO_MODE,
                       6: "it has part of a colour mix only (red, blue)"}


def test_pool_numbers_and_labels_are_fixed():
    rows = [row(1, [ch(1, "dimmer"), ch(2, "red"), ch(3, "green"), ch(4, "blue")])]
    export, table = rig(rows)
    numbers = {p.name: p.number for p in table.presets}
    assert numbers["Full"] == f"{DIMMER_POOL}.1" == "1.1"
    assert numbers["Out"] == "1.5"
    assert numbers["White"] == f"{COLOUR_POOL}.1" == "4.1"
    assert numbers["Red"] == "4.3"
    assert numbers["Pink"] == "4.13"
    assert numbers["Shutter Open"] == f"{BEAM_POOL}.1" == "5.1"
    assert numbers["Zoom Wide"] == "5.5"
    text = starter_presets_script(export, table)
    assert "Store Preset 4.3\nLabel Preset 4.3 \"Red\"" in text
    assert "Store Preset 1.1\nLabel Preset 1.1 \"Full\"" in text
    assert 'Attribute "Dim" At 75' in text
    # No beam channel: the beam slots are named in notes and nothing is stored there.
    assert "Store Preset 5." not in text
    assert "# Preset 5.2 Strobe Slow: not stored." in text
    commands = starter_presets_script(export, table, notes=False)
    assert not any(line.startswith("#") for line in commands.splitlines())


def test_beam_uses_the_profile_ranges():
    rows = [row(1, [ch(1, "dimmer"), ch(2, "shutter", SHUTTER),
                    ch(3, "zoom", [{"name": "Narrow to wide", "min_value": 0, "max_value": 255}])])]
    _, table = rig(rows)
    assert table.preset("Shutter Open").dmx[1] == {"shutter": 11}
    assert table.preset("Strobe Slow").dmx[1] == {"shutter": 27}
    assert table.preset("Strobe Fast").dmx[1] == {"shutter": 119}
    assert table.preset("Zoom Narrow").dmx[1] == {"zoom": 0}
    assert table.preset("Zoom Wide").dmx[1] == {"zoom": 255}
    assert not table.preset("Zoom Wide").assumed


def test_no_strobe_range_means_no_strobe_preset():
    rows = [row(1, [ch(1, "dimmer"), ch(2, "shutter"), ch(3, "zoom")]),
            row(2, [ch(1, "dimmer"), ch(2, "strobe")])]
    _, table = rig(rows)
    for name in ("Strobe Slow", "Strobe Fast"):
        preset = table.preset(name)
        assert preset.values == {}
        assert preset.skipped == {1: "its profile names no strobe range", 2: "its profile names no strobe range"}
    shutter = table.preset("Shutter Open")
    assert shutter.dmx == {1: {"shutter": 255}} and "255 taken as open" in shutter.assumed[1]
    assert 2 in shutter.skipped
    assert "0 taken as narrow" in table.preset("Zoom Narrow").assumed[1]


def test_dimmer_presets_go_by_the_dimmer_channel():
    rows = [row(1, [ch(1, "dimmer")]), row(2, [ch(1, "red"), ch(2, "green"), ch(3, "blue")]), row(3, None)]
    _, table = rig(rows)
    assert table.table()["50"] == {1: {"dimmer": 50.0}, 3: {"dimmer": 50.0}}
    assert table.preset("Out").skipped == {2: "it has no dimmer channel"}
    assert NO_MODE in table.preset("Full").assumed[3]


@pytest.mark.parametrize("name", [c.name for c in PALETTE])
def test_every_palette_colour_mixes_inside_0_to_100(name):
    for have in (["red", "green", "blue"], ["red", "green", "blue", "white", "amber", "uv"]):
        assert all(0 <= v <= 100 for v in additive_mix(colour(name), have).values())
