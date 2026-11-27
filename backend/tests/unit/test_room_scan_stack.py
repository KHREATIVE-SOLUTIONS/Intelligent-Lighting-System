"""
Raised areas standing on a raised area, and an added platform's base height
===========================================================================

services/room_scan/carry.py works out which other raised areas stand on one
(a drum riser on a stage) and where they, and the fixtures standing on them,
go when the one under them is moved, raised or given a quarter turn.
services/room_scan/edit.py adds a raised area on a base height.
docs/ROOM_SCAN.md, slice 20.

What has to hold: an area stands on another when its middle is inside the
other's footprint and its base is within 0.1 m of the other's top; the whole
stack above goes as one piece; a resize alone carries none of it; a square
platform turns with what is under it; one carried out of the room, or above
the ceiling, refuses the edit; and nothing given is changed in place.

No database and no device: the fixtures are plain objects.
"""

import copy
import math
from types import SimpleNamespace

import pytest

from app.services.room_scan.carry import (
    apply_areas, areas_report, carried_area_moves, carried_areas, carried_moves, carried_words,
    refuse_areas_outside, standing_fixtures, stood_areas,
)
from app.services.room_scan.edit import MOVED_BY_HAND, RESIZED_BY_HAND, ShellEditError, add_item, edit_item


def light(fixture_id, x, y, z, heading=0.0):
    return SimpleNamespace(
        id=fixture_id, name=f"Par {fixture_id}", position_x=x, position_y=y, position_z=z, rotation_y=heading,
    )


def room(extra=None):
    """A 12 m by 10 m by 6 m room.

    0: a 6 by 3 stage 0.6 m high upstage. 1: a riser on the floor downstage.
    2: a square 2 by 2 drum riser on the stage, 1 m stage left of its middle.
    3: a 1 by 1 box on the drum riser.
    """
    return {
        "source": "scan",
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0},
        "risers": [
            {"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6, "base_height": 0.0,
             "name": "Stage", "kind": "stage", "suggested": True},
            {"center_x": 4.0, "center_z": 2.0, "width": 2.0, "depth": 2.0, "height": 0.3,
             "name": "Riser", "kind": "riser", "suggested": True},
            {"center_x": 1.0, "center_z": -3.5, "width": 2.0, "depth": 2.0, "height": 0.3, "base_height": 0.6,
             "name": "Drum riser", "kind": "riser", "suggested": False},
            {"center_x": 1.0, "center_z": -3.5, "width": 1.0, "depth": 1.0, "height": 0.2, "base_height": 0.9,
             "name": "Box", "kind": "riser", "suggested": False},
        ] + list(extra or []),
        "truss_lines": [],
        "truss_rings": [],
        "hanging_bands": [],
    }


def lights():
    """One on the stage, one on the drum riser, one on the box, one on the floor riser."""
    return [light(1, -2.0, 0.6, -3.5), light(2, 1.8, 0.9, -3.0), light(3, 1.0, 1.1, -3.5), light(4, 4.0, 0.3, 2.0)]


def stacked(shell, index, fixtures, **changes):
    """The edit and what it carries: (item after, the carried areas, the fixture moves of each)."""
    _, item = edit_item(shell, "risers", index, **changes)
    carried = carried_areas(shell, index, item)
    return item, carried, carried_area_moves(shell, carried, fixtures)


def to_of(moves):
    return {move["rig_fixture_id"]: (move["to"]["x"], move["to"]["y"], move["to"]["z"]) for move in moves}


class TestWhatStandsOnARaisedArea:

    def test_the_whole_stack_above_stands_on_it_and_never_itself(self):
        shell = room()
        assert stood_areas(shell, 0) == [2, 3]
        assert stood_areas(shell, 2) == [3]
        assert stood_areas(shell, 3) == []
        # On the floor beside the stage: on nothing, and nothing on it.
        assert stood_areas(shell, 1) == []

    def test_its_base_is_within_a_tenth_of_a_metre_of_the_top(self):
        def over(base):
            return {"center_x": -2.0, "center_z": -3.5, "width": 1.0, "depth": 1.0, "height": 0.3, "base_height": base}

        for base, stands in ((0.6, True), (0.7, True), (0.5, True), (0.71, False), (0.49, False), (0.0, False)):
            assert (4 in stood_areas(room(extra=[over(base)]), 0)) is stands, base

    def test_its_middle_is_inside_the_footprint(self):
        def at(x, z):
            return {"center_x": x, "center_z": z, "width": 2.0, "depth": 2.0, "height": 0.3, "base_height": 0.6}

        # On the edge it is on it; a little past, overhanging by nearly half of itself, it is not.
        assert 4 in stood_areas(room(extra=[at(3.0, -2.0)]), 0)
        assert 4 not in stood_areas(room(extra=[at(3.05, -3.5)]), 0)
        assert 4 not in stood_areas(room(extra=[at(0.0, -1.95)]), 0)

    def test_one_with_a_number_missing_stands_on_nothing_and_a_place_that_is_not_there_has_nothing(self):
        broken = {"center_x": 0.0, "center_z": -3.5, "width": 1.0, "height": 0.3, "base_height": 0.6}
        assert stood_areas(room(extra=[broken, None]), 0) == [2, 3]
        assert stood_areas(room(), 9) == [] and stood_areas(room(), -1) == [] and stood_areas(None, 0) == []
        assert stood_areas({"risers": "no"}, 0) == []

    def test_two_thin_areas_that_each_stand_on_the_other_do_not_go_round_for_ever(self):
        shell = room()
        shell["risers"] = [
            {"center_x": 0.0, "center_z": 0.0, "width": 2.0, "depth": 2.0, "height": 0.05, "base_height": 0.0},
            {"center_x": 0.0, "center_z": 0.0, "width": 2.0, "depth": 2.0, "height": 0.05, "base_height": 0.05},
        ]
        assert stood_areas(shell, 0) == [1] and stood_areas(shell, 1) == [0]

    def test_each_fixture_stands_on_one_area_of_the_stack(self):
        shell, fixtures = room(), lights()
        assert [f.id for f in standing_fixtures(shell, 0, fixtures)] == [1]
        assert [f.id for f in standing_fixtures(shell, 2, fixtures)] == [2]
        assert [f.id for f in standing_fixtures(shell, 3, fixtures)] == [3]


class TestWhereTheStackGoes:

    def test_a_move_shifts_every_area_above_and_what_stands_on_each(self):
        shell, fixtures = room(), lights()
        given = copy.deepcopy(shell)

        item, carried, moves = stacked(shell, 0, fixtures, center_x=1.0, center_z=-3.0)

        assert [entry["index"] for entry in carried] == [2, 3]
        assert [entry["name"] for entry in carried] == ["Drum riser", "Box"]
        drum, box = carried[0]["item"], carried[1]["item"]
        assert (drum["center_x"], drum["center_z"], drum["base_height"]) == (2.0, -3.0, 0.6)
        assert (box["center_x"], box["center_z"], box["base_height"]) == (2.0, -3.0, 0.9)
        assert (drum["width"], drum["depth"], drum["height"]) == (2.0, 2.0, 0.3)
        assert MOVED_BY_HAND in drum["basis"] and RESIZED_BY_HAND not in drum["basis"] and drum["suggested"] is False
        assert carried[0]["from"] == {"center_x": 1.0, "center_z": -3.5, "width": 2.0, "depth": 2.0, "base_height": 0.6}
        assert carried[0]["to"] == {"center_x": 2.0, "center_z": -3.0, "width": 2.0, "depth": 2.0, "base_height": 0.6}
        # The fixture on each goes with it, and the one on the stage is the stage's own.
        assert [to_of(theirs) for theirs in moves] == [{2: (2.8, 0.9, -2.5)}, {3: (2.0, 1.1, -3.0)}]
        assert to_of(carried_moves(shell, "risers", 0, item, fixtures)) == {1: (-1.0, 0.6, -3.0)}
        # Nothing given was changed, and no fixture was written.
        assert shell == given and fixtures[1].position_x == 1.8

    def test_a_higher_deck_and_a_base_height_raise_the_bases_above_by_what_the_top_moved(self):
        shell, fixtures = room(), lights()

        _, carried, moves = stacked(shell, 0, fixtures, height=0.9)

        assert [entry["item"]["base_height"] for entry in carried] == [0.9, 1.2]
        assert all(RESIZED_BY_HAND in entry["item"]["basis"] for entry in carried)
        assert carried[0]["item"]["center_x"] == 1.0 and MOVED_BY_HAND not in carried[0]["item"]["basis"]
        assert [to_of(theirs) for theirs in moves] == [{2: (1.8, 1.2, -3.0)}, {3: (1.0, 1.4, -3.5)}]

        _, floated, moves = stacked(shell, 0, fixtures, base_height=2.0)
        assert [entry["item"]["base_height"] for entry in floated] == [2.6, 2.9]
        assert to_of(moves[0]) == {2: (1.8, 2.9, -3.0)}

    def test_a_lowered_deck_never_puts_a_base_under_the_floor(self):
        low = {"center_x": -2.0, "center_z": -3.5, "width": 1.0, "depth": 1.0, "height": 0.3, "base_height": 0.5}
        shell = room(extra=[low])
        _, item = edit_item(shell, "risers", 0, height=0.05)
        bases = {entry["index"]: entry["item"]["base_height"] for entry in carried_areas(shell, 0, item)}
        assert bases[4] == 0.0 and bases[2] == pytest.approx(0.05)

    def test_a_quarter_turn_swings_the_stack_about_the_middle_and_turns_a_square_platform_with_it(self):
        shell, fixtures = room(), lights()
        fixtures[1].rotation_y = 30.0

        item, carried, moves = stacked(shell, 0, fixtures, width=3.0, depth=6.0)

        assert (item["center_x"], item["center_z"]) == (0.0, -3.5)
        drum = carried[0]["item"]
        # What was 1 m stage left of the middle is 1 m downstage of it.
        assert (drum["center_x"], drum["center_z"]) == (0.0, -2.5)
        assert (drum["width"], drum["depth"]) == (2.0, 2.0) and carried[0]["turned"] is True
        assert MOVED_BY_HAND in drum["basis"]
        # The fixture on the square drum riser swings with the stage, though the riser's sizes say no turn:
        # 1.8 left and 0.5 down of the stage's middle goes to 0.5 right... clockwise seen from above.
        assert to_of(moves[0]) == {2: (-0.5, 0.9, -1.7)}
        assert moves[0][0]["to"]["rotation_y"] == -60.0
        assert to_of(moves[1]) == {3: (0.0, 1.1, -2.5)}
        assert moves[1][0]["to"]["rotation_y"] == -90.0

    def test_a_platform_that_is_not_square_has_its_sides_swapped_by_the_turn(self):
        long = {"center_x": -1.0, "center_z": -3.0, "width": 2.0, "depth": 1.0, "height": 0.3, "base_height": 0.6,
                "name": "Keys"}
        shell = room(extra=[long])
        _, item = edit_item(shell, "risers", 0, width=3.0, depth=6.0)
        keys = next(entry for entry in carried_areas(shell, 0, item) if entry["index"] == 4)["item"]
        assert (keys["width"], keys["depth"]) == (1.0, 2.0)
        assert (keys["center_x"], keys["center_z"]) == (-0.5, -4.5)

    def test_a_resize_alone_a_rename_and_a_kind_carry_none_of_it(self):
        shell = room()
        for changes in ({"width": 5.0}, {"depth": 2.5, "width": 5.5}, {"name": "Main stage"}, {"riser_kind": "riser"}):
            _, item = edit_item(shell, "risers", 0, **changes)
            assert carried_areas(shell, 0, item) == [], changes

    def test_a_resize_that_brings_the_middle_in_shifts_the_stack_by_as_much(self):
        shell = room()
        shell["risers"][0]["center_x"] = 5.5
        shell["risers"][2]["center_x"] = 6.5
        shell["risers"][3]["center_x"] = 6.5
        # 12 m across and 2 m round it: a 7 m stage's middle can be no further than 4.5 m out.
        _, item = edit_item(shell, "risers", 0, width=7.0)
        assert item["center_x"] == 4.5
        assert [entry["item"]["center_x"] for entry in carried_areas(shell, 0, item)] == [5.5, 5.5]

    def test_the_area_under_it_is_not_carried_by_the_one_on_top(self):
        shell, fixtures = room(), lights()
        _, carried, moves = stacked(shell, 2, fixtures, center_x=0.0)
        assert [entry["index"] for entry in carried] == [3]
        assert to_of(moves[0]) == {3: (0.0, 1.1, -3.5)}

    def test_nothing_stands_on_an_area_that_cannot_be_stood_on(self):
        shell = room()
        _, item = edit_item(shell, "risers", 0, center_x=1.0)
        del shell["risers"][0]["height"]
        assert carried_areas(shell, 0, item) == []
        assert carried_areas(None, 0, item) == [] and carried_areas(room(), 7, item) == []


class TestOutOfTheRoom:

    def test_an_area_carried_past_the_room_and_its_margin_refuses_the_edit(self):
        shell = room()
        # The stage's own middle may go to 8 m; the drum riser, 1 m stage left of it, would be at 8.5 m.
        after, item = edit_item(shell, "risers", 0, center_x=7.5)
        carried = carried_areas(shell, 0, item)

        with pytest.raises(ShellEditError) as refused:
            refuse_areas_outside(after, item, carried)

        assert refused.value.status == 422
        assert "2 raised areas standing on Stage out of the room and the 2 m round it" in refused.value.detail
        assert "Drum riser to 8.5, -3.5" in refused.value.detail and "Nothing was changed" in refused.value.detail

        # Just inside, it goes.
        after, item = edit_item(shell, "risers", 0, center_x=7.0)
        refuse_areas_outside(after, item, carried_areas(shell, 0, item))

    def test_a_top_carried_above_the_ceiling_refuses_the_edit(self):
        shell = room()
        # The stage's own top is at 5.7 m under a 6 m ceiling; the box on the drum riser would top out at 6.2 m.
        after, item = edit_item(shell, "risers", 0, base_height=5.1)
        with pytest.raises(ShellEditError) as refused:
            refuse_areas_outside(after, item, carried_areas(shell, 0, item))
        assert refused.value.status == 422 and "above the ceiling" in refused.value.detail
        assert "Box" in refused.value.detail and "top 6.2 m up" in refused.value.detail

    def test_nothing_carried_refuses_nothing(self):
        refuse_areas_outside(room(), room()["risers"][0], [])


class TestStoringAndWords:

    def test_the_room_given_is_not_changed_and_the_new_one_has_each_area_where_it_went(self):
        shell = room()
        after, item = edit_item(shell, "risers", 0, center_z=-3.0)
        carried = carried_areas(shell, 0, item)
        given = copy.deepcopy(after)

        stored = apply_areas(after, carried)

        assert after == given and stored is not after
        assert [area["center_z"] for area in stored["risers"]] == [-3.0, 2.0, -3.0, -3.0]
        assert stored["risers"][1] == shell["risers"][1]
        # A list to put in a JSON column: nothing in it is the entry's own object.
        stored["risers"][2]["center_z"] = 99.0
        assert carried[0]["item"]["center_z"] == -3.0
        assert apply_areas(after, []) is after

    def test_the_answer_lists_each_area_with_where_it_was_and_went(self):
        shell = room()
        _, item = edit_item(shell, "risers", 0, center_z=-3.0)
        report = areas_report(carried_areas(shell, 0, item))
        assert [set(entry) for entry in report] == [{"kind", "index", "name", "from", "to"}] * 2
        assert report[1]["kind"] == "risers" and report[1]["index"] == 3 and report[1]["name"] == "Box"
        assert report[1]["from"]["center_z"] == -3.5 and report[1]["to"]["center_z"] == -3.0

    def test_the_sentence_says_how_many_areas_went_and_is_what_it_was_with_none(self):
        stage = room()["risers"][0]
        assert carried_words("risers", stage, 3, True) == "3 fixtures standing on Stage moved with it."
        assert carried_words("risers", stage, 4, True, areas=1) == (
            "4 fixtures standing on Stage, or on what stands on it, moved with it. "
            "1 raised area standing on it moved with it too."
        )
        assert carried_words("risers", stage, 0, True, areas=2) == (
            "2 raised areas standing on Stage moved with it. No fixture had to move."
        )
        assert carried_words("risers", stage, 0, False, areas=0) == (
            "The fixtures standing on Stage were left where they are, as asked."
        )


class TestAnAddedPlatformsBaseHeight:
    """What the Add form's base height field sends: validated as an edited base is."""

    SIZES = {"center_x": 3.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3}

    def test_left_out_it_stands_on_the_floor(self):
        _, item, _ = add_item(room(), "risers", **self.SIZES)
        assert item["base_height"] == 0.0
        _, item, _ = add_item(room(), "risers", base_height=0, **self.SIZES)
        assert item["base_height"] == 0.0

    def test_given_it_floats_and_is_stored_to_the_millimetre(self):
        _, item, _ = add_item(room(), "risers", base_height=2.7004, **self.SIZES)
        assert item["base_height"] == 2.7 and item["height"] == 0.3

    def test_it_is_a_finite_number_from_nothing_to_ten_metres(self):
        for wrong in (-0.1, 10.5):
            with pytest.raises(ShellEditError) as refused:
                add_item(room(), "risers", base_height=wrong, **self.SIZES)
            assert refused.value.status == 422
            assert "base height of a raised area must be between 0 m and 10 m" in refused.value.detail
        for wrong in (math.inf, math.nan, True):
            with pytest.raises(ShellEditError) as refused:
                add_item(room(), "risers", base_height=wrong, **self.SIZES)
            assert "base height must be a number" in refused.value.detail

    def test_a_top_above_the_ceiling_is_refused_in_the_words_an_edited_base_is(self):
        with pytest.raises(ShellEditError) as refused:
            add_item(room(), "risers", base_height=5.8, **self.SIZES)
        assert refused.value.status == 422
        assert "the ceiling is at 6 m" in refused.value.detail and "a base of 5.8 m" in refused.value.detail
        # The same words the row's base height field is refused in.
        with pytest.raises(ShellEditError) as edited:
            edit_item(room(), "risers", 1, base_height=5.8)
        assert "the ceiling is at 6 m" in edited.value.detail
        # Right up to the ceiling it is taken.
        _, item, _ = add_item(room(), "risers", base_height=5.7, **self.SIZES)
        assert item["base_height"] == 5.7

    def test_a_deck_is_still_held_to_what_a_deck_can_be(self):
        for wrong in (0.01, 3.5):
            with pytest.raises(ShellEditError) as refused:
                add_item(room(), "risers", **{**self.SIZES, "height": wrong})
            assert "height of a raised area must be between 0.05 m and 3 m" in refused.value.detail

    def test_a_truss_and_a_ring_have_none(self):
        for kind, sizes in (("truss_lines", {"length": 4.0}), ("truss_rings", {"radius": 1.0})):
            with pytest.raises(ShellEditError) as refused:
                add_item(room(), kind, center_x=0.0, center_z=0.0, height=4.0, base_height=1.0, **sizes)
            assert "no base height to set" in refused.value.detail
