"""
Focus presets: targets, the table and the grandMA2 presets
==========================================================

The aiming maths for one head and one point is in test_focus_presets_aim.py.
Here: the targets a room gives and the ones a person adds, which rig rows are
taken as moving heads and how their tags reach the maths (hung or standing,
invert, swap, 8 or 16 bit), the CSV, and the Position presets the MA2 script
stores. All pure: SimpleNamespace rows, no database. docs/FOCUS_PRESETS.md.
"""

import csv
import io
import random
from types import SimpleNamespace

import pytest

from app.services.console_export.ma2 import ma2_script
from app.services.console_export.model import from_rig
from app.services.focus_presets.aim import Head, aim
from app.services.focus_presets.table import CSV_COLUMNS, build_table, focus_csv, table_dict
from app.services.focus_presets.targets import (
    MAX_CUSTOM_TARGETS,
    TargetError,
    add_custom,
    all_targets,
    default_targets,
    remove_custom,
    stored_custom,
)

DEFAULT_KEYS = ["dj_booth", "dance_floor", "audience", "stage_front", "straight_down"]

ROOM = {
    "room": {"width": 12.0, "depth": 10.0, "height": 6.0},
    "risers": [
        {"kind": "stage", "center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6},
        {"is_dj_booth": True, "center_x": 0.0, "center_z": -4.0, "width": 2.0, "depth": 1.0,
         "base_height": 0.6, "height": 0.4},
    ],
}


def channels(*types):
    return [SimpleNamespace(channel_type=t) for t in types]


MOVER_16 = channels("pan", "pan_fine", "tilt", "tilt_fine", "dimmer")
MOVER_8 = channels("pan", "tilt", "dimmer")
PAR = channels("red", "green", "blue", "dimmer")


def row(row_id, number, name, position, *, tags=("position_source:mvr",), chans=MOVER_16, kind="moving_head",
        rotation=(0.0, 0.0, 0.0), pan_range=540.0, tilt_range=270.0, inverted=False, address=None):
    return SimpleNamespace(
        id=row_id, fixture_number=number, name=name, universe=0, dmx_address=address or (1 + 20 * row_id),
        position_x=position[0], position_y=position[1], position_z=position[2],
        rotation_x=rotation[0], rotation_y=rotation[1], rotation_z=rotation[2],
        group_name="Movers", tags=list(tags), is_active=True, is_inverted=inverted,
        fixture=SimpleNamespace(manufacturer="Acme", model="Mover", gdtf_file=None, fixture_type=kind,
                                pan_range=pan_range, tilt_range=tilt_range),
        mode=SimpleNamespace(name="Std", channel_count=len(chans), channels=chans),
    )


def rig(shell=ROOM, custom=None):
    return SimpleNamespace(id=3, name="Focus rig", room_shell=shell, focus_targets=custom)


def standard_rows():
    return [
        row(1, 1, "Spot L", (-3.0, 6.0, -1.0)),
        row(2, 2, "Spot R", (3.0, 6.0, -1.0), tags=["position_source:mvr", "position_unconfirmed"]),
        row(3, 3, "Floor Beam", (0.0, 0.3, 2.0), chans=MOVER_8),
        row(4, 4, "Par", (0.0, 5.0, 0.0), chans=PAR, kind="par"),
    ]


def table_for(rows, shell=ROOM, custom=None):
    r = rig(shell, custom)
    return build_table(r, rows, from_rig(r, rows))


def entry(table, key, number):
    target = next(t for t in table.targets if t.target.key == key)
    return next(e for e in target.entries if e.fixture.number == number)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

class TestDefaultTargets:

    def test_five_defaults_in_a_fixed_order_all_placed_in_a_full_room(self):
        targets = default_targets(ROOM)
        assert [t.key for t in targets] == DEFAULT_KEYS
        assert not any(t.skipped for t in targets)
        booth = targets[0]
        # The marked booth riser: deck top 1.0 m, the DJ 1.2 m above it.
        assert booth.point == (0.0, 2.2, -4.0)
        assert "DJ booth" in booth.source

    def test_an_empty_room_skips_what_it_cannot_place_and_says_why(self):
        targets = {t.key: t for t in default_targets(None)}
        assert set(targets) == set(DEFAULT_KEYS)
        for key in ("dj_booth", "dance_floor", "audience", "stage_front"):
            assert targets[key].skipped, key
            assert targets[key].points_for([(0.0, 6.0, 0.0)]) == [None]
        assert not targets["straight_down"].skipped

    def test_straight_down_is_the_floor_under_each_head(self):
        down = default_targets({})[-1]
        assert down.points_for([(1.0, 6.0, 2.0), (-2.0, 4.0, 0.5)]) == [(1.0, 0.0, 2.0), (-2.0, 0.0, 0.5)]

    def test_the_audience_line_spreads_heads_in_order_across_x(self):
        audience = default_targets(ROOM)[2]
        points = audience.points_for([(3.0, 6.0, 0.0), (-3.0, 6.0, 0.0), (0.0, 6.0, 0.0)])
        xs = [p[0] for p in points]
        assert xs[1] < xs[2] < xs[0]
        assert all(p[1] == pytest.approx(1.7) for p in points)

    def test_a_dance_floor_disc_wins_over_the_room(self):
        shell = dict(ROOM, dance_floor={"center_x": 1.0, "center_z": 2.0, "radius": 3.0})
        assert default_targets(shell)[1].point == (1.0, 0.0, 2.0)


class TestCustomTargets:

    def test_add_gives_the_next_id_and_leaves_the_stored_list_alone(self):
        stored = [{"id": 4, "name": "Mirror ball", "x": 0, "y": 5, "z": 0}]
        targets, item = add_custom(stored, "  Bar   top ", 2, 1.1, 3)
        assert item == {"id": 5, "name": "Bar top", "x": 2.0, "y": 1.1, "z": 3.0}
        assert len(targets) == 2 and len(stored) == 1

    @pytest.mark.parametrize("name,x,y,z", [
        ("", 0, 0, 0), ("x" * 61, 0, 0, 0), ("A", "two", 0, 0), ("A", 0, -0.1, 0), ("A", 501, 0, 0),
        ("A", True, 0, 0), ("A", float("nan"), 0, 0),
    ])
    def test_bad_input_is_refused_in_words(self, name, x, y, z):
        with pytest.raises(TargetError):
            add_custom([], name, x, y, z)

    def test_a_rig_keeps_at_most_the_limit(self):
        stored = [{"id": i + 1, "name": f"T{i}", "x": 0, "y": 0, "z": 0} for i in range(MAX_CUSTOM_TARGETS)]
        with pytest.raises(TargetError):
            add_custom(stored, "One more", 0, 0, 0)

    def test_remove_and_a_missing_id(self):
        stored = [{"id": 1, "name": "A", "x": 0, "y": 0, "z": 0}, {"id": 2, "name": "B", "x": 0, "y": 0, "z": 0}]
        assert [t["id"] for t in remove_custom(stored, 1)] == [2]
        assert remove_custom(stored, 9) is None

    def test_malformed_stored_entries_are_left_out(self):
        stored = [{"id": 1, "name": "A", "x": 0, "y": 0, "z": 0}, {"id": "2", "name": "B"}, "junk",
                  {"id": 3, "name": "", "x": 0, "y": 0, "z": 0}]
        assert [t["id"] for t in stored_custom(stored)] == [1]
        assert stored_custom("not a list") == []

    def test_custom_targets_follow_the_defaults(self):
        targets = all_targets(ROOM, [{"id": 7, "name": "Bar", "x": 4, "y": 1, "z": 3}])
        assert [t.key for t in targets] == DEFAULT_KEYS + ["custom_7"]
        assert targets[-1].custom and targets[-1].point == (4.0, 1.0, 3.0)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

class TestTheTable:

    def test_movers_are_the_heads_with_pan_or_tilt_and_a_par_is_not(self):
        table = table_for(standard_rows())
        assert [h.number for h in table.heads] == [1, 2, 3]
        assert len(table.targets) == 5
        assert all(len(t.entries) == 3 for t in table.targets)

    def test_a_mode_with_no_channel_list_is_taken_by_type_and_written_8_bit(self):
        spot = row(1, 1, "Spot", (0.0, 6.0, 0.0), chans=[], kind="spot")
        par = row(2, 2, "Par", (1.0, 6.0, 0.0), chans=[], kind="par")
        table = table_for([spot, par])
        assert [h.number for h in table.heads] == [1]
        down = entry(table, "straight_down", 1).aim
        assert down.pan_fine_dmx is None and down.tilt_fine_dmx is None and down.pan_dmx == 128

    def test_16_bit_when_the_mode_has_fine_channels(self):
        table = table_for(standard_rows())
        assert entry(table, "straight_down", 1).aim.pan_fine_dmx is not None
        assert entry(table, "straight_down", 3).aim.tilt_fine_dmx is None

    def test_hung_or_standing_from_tags_else_assumed_from_height(self):
        rows = [
            row(1, 1, "High", (0.0, 6.0, 0.0)),
            row(2, 2, "Low", (1.0, 0.4, 0.0)),
            row(3, 3, "Tagged floor", (2.0, 3.0, 0.0), tags=["standing"]),
            row(4, 4, "Low but hung", (3.0, 0.8, 0.0), tags=["hung"]),
        ]
        heads = {h.number: h for h in table_for(rows).heads}
        assert (heads[1].mount, heads[1].mount_assumed) == ("hung", True)
        assert (heads[2].mount, heads[2].mount_assumed) == ("standing", True)
        assert (heads[3].mount, heads[3].mount_assumed) == ("standing", False)
        assert (heads[4].mount, heads[4].mount_assumed) == ("hung", False)

    def test_invert_and_swap_tags_reach_the_head_and_is_inverted_flips_pan_again(self):
        rows = [
            row(1, 1, "Pan inv", (0.0, 6.0, 0.0), tags=["pan_invert"]),
            row(2, 2, "Both", (1.0, 6.0, 0.0), tags=["pan_invert"], inverted=True),
            row(3, 3, "Tilt inv swap", (2.0, 6.0, 0.0), tags=["tilt_invert", "pan_tilt_swap"]),
        ]
        heads = {h.number: h.head for h in table_for(rows).heads}
        assert heads[1].pan_invert and not heads[2].pan_invert
        assert heads[3].tilt_invert and heads[3].swap

    def test_pan_invert_mirrors_the_pan_value_against_the_same_head_without(self):
        point = (3.0, 0.0, 3.0)
        plain = aim(Head(position=(0.0, 6.0, 0.0)), point)
        inverted = aim(Head(position=(0.0, 6.0, 0.0), pan_invert=True), point)
        assert inverted.pan_deg == plain.pan_deg
        assert inverted.pan_attr_deg == pytest.approx(-plain.pan_attr_deg)
        assert inverted.tilt_attr_deg == pytest.approx(plain.tilt_attr_deg)

    def test_a_head_with_no_position_is_left_out_and_said(self):
        rows = standard_rows() + [row(5, 5, "Nowhere", (0.0, 0.0, 0.0), tags=["unplaced"])]
        table = table_for(rows)
        assert table.left_out == [{"fixture_id": 5, "name": "Nowhere", "reason": "it has no position in the rig"}]
        assert 5 not in [h.number for h in table.heads]

    def test_a_point_the_head_cannot_reach_is_kept_with_its_reason(self):
        # A hung head with 180 of tilt cannot reach a custom point above it at its side.
        rows = [row(1, 1, "Short tilt", (0.0, 3.0, 0.0), tilt_range=180.0)]
        table = table_for(rows, custom=[{"id": 1, "name": "Ceiling", "x": 4.0, "y": 5.0, "z": 0.0}])
        e = entry(table, "custom_1", 1)
        assert not e.aim.reachable and e.aim.reason
        assert table.targets[-1].unreachable == [e]

    def test_the_same_rig_in_any_row_order_gives_the_same_csv(self):
        rows = standard_rows() + [row(5, 5, "Nowhere", (0, 0, 0), tags=["unplaced"]),
                                  row(6, 6, "Nowhere 2", (0, 0, 0), tags=["unplaced"])]
        first = focus_csv(table_for(rows))
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            again = table_for(shuffled)
            assert focus_csv(again) == first
            assert [x["fixture_id"] for x in again.left_out] == [5, 6]


class TestTheCsv:

    def test_columns_and_one_row_per_target_and_head(self):
        text = focus_csv(table_for(standard_rows(), custom=[{"id": 1, "name": "Bar", "x": 4, "y": 1, "z": 3}]))
        reader = list(csv.reader(io.StringIO(text)))
        assert reader[0] == CSV_COLUMNS
        rows = [dict(zip(CSV_COLUMNS, r)) for r in reader[1:]]
        assert len(rows) == 6 * 3
        spot_r = [r for r in rows if r["fixture_id"] == "2"]
        assert all(r["position"] == "guessed" for r in spot_r)
        assert {r["position"] for r in rows if r["fixture_id"] == "1"} == {"confirmed"}
        assert {r["mount"] for r in rows if r["fixture_id"] == "3"} == {"standing (assumed)"}

    def test_a_skipped_target_is_one_row_with_its_reason(self):
        text = focus_csv(table_for(standard_rows(), shell=None))
        rows = [dict(zip(CSV_COLUMNS, r)) for r in list(csv.reader(io.StringIO(text)))[1:]]
        booth = [r for r in rows if r["target"] == "dj_booth"]
        assert len(booth) == 1 and booth[0]["fixture_id"] == "" and booth[0]["reason"]

    def test_table_dict_names_the_guide(self):
        out = table_dict(table_for(standard_rows()))
        assert out["heads"] == 3 and out["operator_guide"] == "docs/FOCUS_PRESETS.md"
        assert [t["key"] for t in out["targets"]] == DEFAULT_KEYS


# ---------------------------------------------------------------------------
# The MA2 script
# ---------------------------------------------------------------------------

def script(rows, shell=ROOM, custom=None, **kw):
    r = rig(shell, custom)
    export = from_rig(r, rows)
    return ma2_script(export, focus=build_table(r, rows, export), **kw)


def commands(text):
    return [line for line in text.splitlines() if line and not line.startswith("#")]


class TestTheMa2Presets:

    def test_one_position_preset_per_target_with_pan_and_tilt_for_each_head(self):
        text = script(standard_rows())
        cmds = commands(text)
        stores = [c for c in cmds if c.startswith("Store Preset")]
        assert stores == [f"Store Preset 2.{n}" for n in range(1, 6)]
        assert 'Label Preset 2.1 "Focus DJ booth"' in cmds
        assert 'Label Preset 2.5 "Focus Straight down"' in cmds
        # Straight down: every hung head at centre.
        block = cmds[cmds.index("Store Preset 2.4") + 2:cmds.index("Store Preset 2.5")]
        assert block[:5] == ["ClearAll", "ClearSelection", "Fixture 1", 'Attribute "Pan" At 0', 'Attribute "Tilt" At 0']
        assert cmds[-1] == "ClearAll"

    def test_a_guessed_position_is_marked_in_the_notes(self):
        text = script(standard_rows())
        assert "# Position guessed, not checked against the room: fixture 2." in text
        assert "#   fixture 2: position guessed (unconfirmed), check this one first" in text
        assert "fixture 1: position guessed" not in text

    def test_first_preset_moves_every_slot(self):
        cmds = commands(script(standard_rows(), first_preset=101))
        assert [c for c in cmds if c.startswith("Store Preset")] == [f"Store Preset 2.{n}" for n in range(101, 106)]

    def test_a_skipped_target_keeps_its_slot_and_stores_nothing(self):
        text = script(standard_rows(), shell=None)
        cmds = commands(text)
        assert [c for c in cmds if c.startswith("Store Preset")] == ["Store Preset 2.5"]
        assert "# Preset 2.1 Focus DJ booth: not stored." in text

    def test_a_target_no_head_can_reach_is_not_stored(self):
        rows = [row(1, 1, "Short tilt", (0.0, 3.0, 0.0), tilt_range=180.0)]
        text = script(rows, custom=[{"id": 1, "name": "Ceiling", "x": 4.0, "y": 5.0, "z": 0.0}])
        assert "Store Preset 2.6" not in text
        assert "# Preset 2.6 Focus Ceiling: not stored. No moving head can reach it." in text

    def test_a_rig_with_no_movers_has_no_preset_commands(self):
        rows = [row(4, 4, "Par", (0.0, 5.0, 0.0), chans=PAR, kind="par")]
        text = script(rows)
        assert "# Focus presets: none. The rig has no moving heads." in text
        assert not any("Preset" in c or c == "ClearAll" for c in commands(text))

    def test_without_notes_it_is_commands_only_and_the_same_commands(self):
        with_notes, without = script(standard_rows()), script(standard_rows(), notes=False)
        assert not any(line.startswith("#") for line in without.splitlines())
        assert commands(with_notes) == commands(without)

    def test_the_same_rig_gives_the_same_bytes(self):
        assert script(standard_rows()) == script(list(reversed(standard_rows())))

    def test_no_focus_given_leaves_the_script_as_it_was(self):
        r = rig()
        export = from_rig(r, standard_rows())
        assert "Preset" not in ma2_script(export)
