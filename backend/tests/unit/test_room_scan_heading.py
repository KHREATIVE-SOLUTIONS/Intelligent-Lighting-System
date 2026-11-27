"""
Raised areas at any heading
===========================

A stage, riser or booth of a stored room can stand at a heading
(`heading_deg`: degrees clockwise from across the room seen from above, its
width along it and its depth square to it). services/room_scan/edit.py stores
it, services/room_scan/carry.py swings what stands on the area with it, and
services/room_scan/outline_edit.py asks the walls about its corners where they
are. docs/ROOM_SCAN.md, slice 21.

What has to hold: a raised area that stores no heading stands square to the
room and reads exactly as it did; a heading is folded as a line's is; the
whole of a turned area is held to the room by how far it reaches as it
stands; "standing on it" and "a share of the footprint" go by the area's own
width and depth; a turn to 90 puts everything exactly where the older
sides-swapped quarter turn puts it; a turn and the turn back return
everything to the millimetre; and a riser on a turned stage turns with it.

No database and no device: the fixtures are plain objects.
"""

import copy
import math
from types import SimpleNamespace

import pytest

from app.services.room_scan.carry import (
    apply_moves, area_turn, carried_area_moves, carried_areas, carried_moves, standing_fixtures, stands_on,
    stood_areas,
)
from app.services.room_scan.edit import (
    MOVED_BY_HAND, RESIZED_BY_HAND, ShellEditError, add_item, area_corners, area_heading, area_reach, edit_item,
    edit_words,
)
from app.services.room_scan.outline_edit import outside_report


def light(fixture_id, x, y, z, heading=0.0):
    return SimpleNamespace(
        id=fixture_id, name=f"Par {fixture_id}", position_x=x, position_y=y, position_z=z, rotation_y=heading,
    )


def room(stage=None, extra=None):
    """A 12 m by 10 m by 6 m room: a 6 by 3 stage 0.6 m high upstage, storing no heading, and what is added."""
    first = {"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6, "base_height": 0.0,
             "name": "Stage", "kind": "stage", "suggested": True}
    first.update(stage or {})
    return {
        "source": "scan",
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0},
        "risers": [first] + list(extra or []),
        "truss_lines": [],
        "truss_rings": [],
        "hanging_bands": [],
    }


DRUM = {"center_x": 1.0, "center_z": -3.5, "width": 2.0, "depth": 1.0, "height": 0.3, "base_height": 0.6,
        "name": "Drum riser", "kind": "riser", "suggested": False}


def carried(shell, fixtures, **changes):
    """The edit of the stage, and the moves it would carry: (shell after, item after, moves)."""
    after, item = edit_item(shell, "risers", 0, **changes)
    return after, item, carried_moves(shell, "risers", 0, item, fixtures)


def to_of(moves):
    return {move["rig_fixture_id"]: (move["to"]["x"], move["to"]["y"], move["to"]["z"]) for move in moves}


def turned_to(moves):
    return {move["rig_fixture_id"]: move["to"]["rotation_y"] for move in moves}


def refused(call):
    with pytest.raises(ShellEditError) as error:
        call()
    assert error.value.status == 422
    return error.value.detail


def about(x, z, degrees, cx=0.0, cz=-3.5):
    """A point swung clockwise seen from above (+X towards +Z) about a middle."""
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return cx + (x - cx) * cos - (z - cz) * sin, cz + (x - cx) * sin + (z - cz) * cos


class TestAHeadingIsStored:

    def test_one_that_stores_none_stands_square_and_a_heading_of_nothing_changes_nothing(self):
        shell = room()
        assert area_heading(shell["risers"][0]) == 0.0
        after, item = edit_item(shell, "risers", 0, heading_deg=0.0)
        assert item == shell["risers"][0] and "heading_deg" not in item
        assert edit_words("risers", shell["risers"][0], item) is None
        # What cannot be read as a heading is none.
        for junk in (None, "east", True, float("nan"), 720.0):
            assert area_heading({"heading_deg": junk}) == 0.0
        assert area_heading(None) == 0.0

    def test_it_is_stored_folded_as_a_lines_is_and_marked_as_set_by_hand(self):
        shell = room()
        for given, stored in ((30, 30.0), (-30, -30.0), (135, -45.0), (-90, 90.0), (90, 90.0), (210, 30.0),
                              (12.34, 12.3)):
            after, item = edit_item(shell, "risers", 0, heading_deg=given)
            assert item["heading_deg"] == stored, given
            assert item["suggested"] is False and RESIZED_BY_HAND in item["basis"]
            assert MOVED_BY_HAND not in item["basis"]
            # Its middle and its sides are what they were, and the room given is not changed.
            assert [item[key] for key in ("center_x", "center_z", "width", "depth")] == [0.0, -3.5, 6.0, 3.0]
            assert shell == room()
            assert edit_words("risers", shell["risers"][0], item) == "Stage turned"

    def test_half_a_turn_is_no_turn_and_a_tenth_is_the_least(self):
        angled = room(stage={"heading_deg": 30.0})
        for same in (30, 210, -150, 30.04):
            _, item = edit_item(angled, "risers", 0, heading_deg=same)
            assert item == angled["risers"][0], same
        _, item = edit_item(angled, "risers", 0, heading_deg=30.1)
        assert item["heading_deg"] == 30.1
        # Back to square: 0 is then what it says.
        _, item = edit_item(angled, "risers", 0, heading_deg=0)
        assert item["heading_deg"] == 0.0 and area_heading(item) == 0.0

    def test_what_is_not_a_heading_is_refused(self):
        assert "between -360 and 360" in refused(lambda: edit_item(room(), "risers", 0, heading_deg=400))
        assert "number of degrees" in refused(lambda: edit_item(room(), "risers", 0, heading_deg=float("inf")))

    def test_a_turn_is_said_with_whatever_else_was_done(self):
        shell = room()
        _, item = edit_item(shell, "risers", 0, name="Deck", center_x=1.0, heading_deg=20, height=0.9)
        assert edit_words("risers", shell["risers"][0], item) == "Stage renamed, moved, resized and turned"


class TestTheWholeOfItIsHeldToTheRoom:

    def test_how_far_it_reaches_as_it_stands(self):
        assert area_reach(6.0, 3.0, 0.0) == (3.0, 1.5)
        assert area_reach(6.0, 3.0, 90.0) == (pytest.approx(1.5), pytest.approx(3.0))
        reach = (6.0 + 3.0) / 2.0 * math.cos(math.radians(45))
        assert area_reach(6.0, 3.0, 45.0) == (pytest.approx(reach), pytest.approx(reach))
        assert area_reach(6.0, 3.0, -30.0) == area_reach(6.0, 3.0, 30.0)

    def test_its_corners_are_where_the_heading_puts_them(self):
        square = area_corners(room()["risers"][0])
        assert square == [(-3.0, -5.0), (3.0, -5.0), (3.0, -2.0), (-3.0, -2.0)]
        turned = area_corners(room(stage={"heading_deg": 90.0})["risers"][0])
        wanted = [(1.5, -6.5), (1.5, -0.5), (-1.5, -0.5), (-1.5, -6.5)]
        for got, want in zip(turned, wanted):
            assert got == (pytest.approx(want[0]), pytest.approx(want[1]))
        # Clockwise seen from above: each corner of a square one, swung about the middle.
        for got, was in zip(area_corners(room(stage={"heading_deg": 30.0})["risers"][0]), square):
            assert got == tuple(pytest.approx(value) for value in about(was[0], was[1], 30))

    def test_a_turn_brings_the_middle_in_until_the_rest_fits(self):
        # Upstage as far as a plain move lets its middle go, then turned end on: it reaches 3 m either way
        # in depth, and the room and the 2 m round it end 7 m from the middle.
        _, moved = edit_item(room(), "risers", 0, center_z=-6.5)
        assert moved["center_z"] == -6.5
        shell = room(stage={"center_z": -6.5})
        _, item = edit_item(shell, "risers", 0, heading_deg=90)
        assert item["center_z"] == -4.0 and item["heading_deg"] == 90.0
        assert MOVED_BY_HAND in item["basis"] and RESIZED_BY_HAND in item["basis"]
        assert edit_words("risers", shell["risers"][0], item) == "Stage moved and turned"

    def test_one_too_long_for_the_room_the_way_it_would_stand_is_refused(self):
        long = room(stage={"width": 15.0, "center_z": 0.0})
        # 15 m fits across (12 m and the 2 m each side), and not from upstage to downstage (10 m and the same).
        said = refused(lambda: edit_item(long, "risers", 0, heading_deg=90))
        assert "15 m from upstage to downstage" in said and "14 m" in said
        _, item = edit_item(long, "risers", 0, heading_deg=10)
        assert item["heading_deg"] == 10.0

    def test_a_resize_of_a_turned_one_goes_by_its_reach_as_it_stands(self):
        end_on = room(stage={"heading_deg": 90.0})
        # Its width runs upstage to downstage now: 9 m of it reaches 4.5 m, and the middle comes in to fit.
        _, item = edit_item(end_on, "risers", 0, width=9.0)
        assert item["center_z"] == -2.5 and item["width"] == 9.0 and item["heading_deg"] == 90.0


class TestAddingOneAtAHeading:

    BASE = {"center_x": 0.0, "center_z": 2.0, "width": 2.0, "depth": 1.0, "height": 0.3}

    def test_an_added_one_stores_its_heading(self):
        after, item, index = add_item(room(), "risers", heading_deg=135, **self.BASE)
        assert item["heading_deg"] == -45.0 and index == 1
        assert after["risers"][1] == item and item["added_by_hand"] is True

    def test_one_added_square_says_nothing_as_it_always_did(self):
        for heading in ({}, {"heading_deg": 0}, {"heading_deg": 180}, {"heading_deg": None}):
            _, item, _ = add_item(room(), "risers", **heading, **self.BASE)
            assert "heading_deg" not in item, heading

    def test_the_whole_of_it_is_held_as_it_stands_and_a_wrong_heading_is_refused(self):
        # Against the stage left wall, end on to it: it reaches 1 m across, not half a metre.
        _, item, _ = add_item(room(), "risers", heading_deg=90, **{**self.BASE, "center_x": 7.9, "depth": 2.0,
                                                                  "width": 1.0})
        assert item["center_x"] == 7.0
        assert "between -360 and 360" in refused(lambda: add_item(room(), "risers", heading_deg=361, **self.BASE))


class TestWhatStandsOnATurnedArea:

    def test_over_its_footprint_is_over_it_as_it_stands(self):
        end_on = room(stage={"heading_deg": 90.0})["risers"][0]
        square = room()["risers"][0]
        # Downstage of the middle: on the one that stands end on, off the one that stands across.
        assert stands_on(end_on, light(1, 0.0, 0.6, -1.0)) and not stands_on(square, light(1, 0.0, 0.6, -1.0))
        # Stage left of the middle: the other way round.
        assert stands_on(square, light(2, 2.5, 0.6, -3.5)) and not stands_on(end_on, light(2, 2.5, 0.6, -3.5))
        # The 0.15 m round it goes round it as it stands.
        assert stands_on(end_on, light(3, 1.6, 0.6, -3.5)) and not stands_on(end_on, light(3, 1.7, 0.6, -3.5))

    def test_a_corner_of_one_at_an_angle(self):
        angled = room(stage={"heading_deg": 45.0})
        corner = about(2.9, -2.1, 45)
        lights = [light(1, corner[0], 0.6, corner[1]), light(2, 2.9, 0.6, -4.9)]
        # The corner it has, and the corner it would have had standing square.
        assert [fixture.id for fixture in standing_fixtures(angled, 0, lights)] == [1]
        assert [fixture.id for fixture in standing_fixtures(room(), 0, lights)] == [2]

    def test_a_riser_stands_on_it_where_its_footprint_is(self):
        def riser(x, z):
            return {**DRUM, "center_x": x, "center_z": z}

        end_on = {"heading_deg": 90.0}
        assert stood_areas(room(stage=end_on, extra=[riser(0.0, -1.0)]), 0) == [1]
        assert stood_areas(room(extra=[riser(0.0, -1.0)]), 0) == []
        assert stood_areas(room(stage=end_on, extra=[riser(2.5, -3.5)]), 0) == []
        assert stood_areas(room(extra=[riser(2.5, -3.5)]), 0) == [1]


class TestATurnSwingsWhatStandsOnIt:

    def lights(self):
        return [light(1, 2.0, 0.6, -3.5), light(2, -2.5, 0.7, -4.5, heading=10.0), light(3, 0.0, 0.6, -3.5)]

    def test_each_is_swung_about_the_middle_and_its_own_heading_turns_the_other_way(self):
        shell = room()
        _, item, moves = carried(shell, self.lights(), heading_deg=30)
        # The one at the very middle does not shift, and still turns.
        assert sorted(to_of(moves)) == [1, 2, 3]
        went = to_of(moves)
        for fixture in self.lights():
            x, z = about(fixture.position_x, fixture.position_z, 30)
            assert went[fixture.id] == (pytest.approx(x, abs=0.0006), fixture.position_y, pytest.approx(z, abs=0.0006))
        # 2 m stage left of the middle goes downstage: clockwise seen from above.
        assert went[1] == (1.732, 0.6, -2.5)
        # rotation_y runs the other way round from a heading.
        assert turned_to(moves) == {1: -30.0, 2: -20.0, 3: -30.0}

    def test_a_turn_to_90_is_the_quarter_turn_the_sides_have_always_told(self):
        shell = room()
        _, by_heading, a = carried(shell, self.lights(), heading_deg=90)
        _, by_sides, b = carried(shell, self.lights(), width=3.0, depth=6.0)
        assert to_of(a) == to_of(b) and turned_to(a) == turned_to(b) == {1: -90.0, 2: -80.0, 3: -90.0}
        assert area_turn(shell["risers"][0], by_heading) == area_turn(shell["risers"][0], by_sides) == 90.0
        # The same footprint, said two ways.
        for got, want in zip(sorted(area_corners(by_heading)), sorted(area_corners(by_sides))):
            assert got == (pytest.approx(want[0]), pytest.approx(want[1]))

    def test_a_turn_and_the_turn_back_put_everything_back_to_the_millimetre(self):
        shell, fixtures = room(), self.lights()
        there, item, moves = carried(shell, fixtures, heading_deg=30)
        apply_moves(fixtures, moves)
        back, again, moves = carried(there, fixtures, heading_deg=0)
        apply_moves(fixtures, moves)
        assert area_heading(again) == 0.0
        for now, was in zip(fixtures, self.lights()):
            assert now.position_x == pytest.approx(was.position_x, abs=0.001)
            assert now.position_z == pytest.approx(was.position_z, abs=0.001)
            assert now.position_y == was.position_y and now.rotation_y == was.rotation_y

    def test_a_change_of_heading_is_the_smaller_of_the_two_turns_that_give_it(self):
        def turn(was, now):
            stage = room(stage={"heading_deg": was})["risers"][0]
            return area_turn(stage, {**stage, "heading_deg": now})

        assert turn(80.0, -80.0) == pytest.approx(20.0)
        assert turn(-80.0, 80.0) == pytest.approx(-20.0)
        assert turn(0.0, 90.0) == 90.0 and turn(90.0, 0.0) == -90.0
        assert turn(30.0, 30.0) == 0.0 and turn(30.0, 30.04) == 0.0
        # A quarter turn is as far either way: it goes the way the heading went, so the turn back takes it back.
        assert turn(-45.0, 45.0) == 90.0 and turn(45.0, -45.0) == -90.0

    def test_a_quarter_turn_by_the_heading_and_back_puts_everything_back(self):
        shell, fixtures = room(), self.lights()
        there, _, moves = carried(shell, fixtures, heading_deg=90)
        apply_moves(fixtures, moves)
        _, _, moves = carried(there, fixtures, heading_deg=0)
        apply_moves(fixtures, moves)
        for now, was in zip(fixtures, self.lights()):
            assert (now.position_x, now.position_y, now.position_z, now.rotation_y) == (
                was.position_x, was.position_y, was.position_z, was.rotation_y,
            )

    def test_sides_swapped_and_a_heading_changed_in_one_request_are_both_turns(self):
        shell = room()
        # A quarter turn by the sides and another by the heading: half a turn. The footprint is the one
        # it was; what stands on it is swapped end for end and faces the other way.
        _, item, moves = carried(shell, self.lights(), width=3.0, depth=6.0, heading_deg=90)
        assert area_turn(shell["risers"][0], item) == 180.0
        for got, want in zip(sorted(area_corners(item)), sorted(area_corners(shell["risers"][0]))):
            assert got == (pytest.approx(want[0]), pytest.approx(want[1]))
        assert to_of(moves)[1] == (-2.0, 0.6, -3.5)
        assert turned_to(moves) == {1: 180.0, 2: -170.0, 3: 180.0}
        # A quarter turn by the sides taken back by the heading cannot be said: -90 is stored as 90.
        _, item, _ = carried(shell, self.lights(), width=3.0, depth=6.0, heading_deg=-90)
        assert item["heading_deg"] == 90.0 and area_turn(shell["risers"][0], item) == 180.0

    def test_a_move_and_a_height_with_a_turn_are_all_followed(self):
        shell = room()
        _, item, moves = carried(shell, self.lights(), center_x=1.0, center_z=-3.0, height=0.9, heading_deg=-90)
        # -90 is stored as 90: a quarter turn clockwise, about the middle, to where the middle went.
        assert item["heading_deg"] == 90.0
        assert to_of(moves)[1] == (1.0, pytest.approx(0.9), -1.0)
        assert to_of(moves)[3] == (1.0, pytest.approx(0.9), -3.0)

    def test_left_where_they_are_when_nothing_about_it_turned_or_moved(self):
        angled = room(stage={"heading_deg": 30.0})
        _, item, moves = carried(angled, self.lights(), name="Deck")
        assert moves == []
        _, item, moves = carried(angled, self.lights(), heading_deg=210)
        assert moves == []


class TestAShareOfATurnedFootprint:

    def test_a_resize_keeps_each_at_its_share_along_the_areas_own_sides(self):
        end_on = room(stage={"heading_deg": 90.0})
        # 2 m along its width, which runs downstage; 1 m off to the side of that, which is stage right.
        fixtures = [light(1, 0.0, 0.6, -1.5), light(2, -1.0, 0.6, -3.5)]
        _, item, moves = carried(end_on, fixtures, width=7.0)
        assert item["center_z"] == -3.5
        # Along the width it is spread; across it, it stays.
        assert to_of(moves) == {1: (0.0, 0.6, pytest.approx(-3.5 + 2.0 * 7.0 / 6.0, abs=0.0006))}
        _, item, moves = carried(end_on, fixtures, depth=6.0)
        assert to_of(moves) == {2: (pytest.approx(-2.0, abs=0.0006), 0.6, -3.5)}
        assert turned_to(moves) == {2: 0.0}

    def test_at_an_angle(self):
        angled = room(stage={"heading_deg": 30.0})
        x, z = about(2.0, -3.5, 30)
        _, item, moves = carried(angled, [light(1, x, 0.6, z)], width=7.0)
        assert (item["center_x"], item["center_z"]) == (0.0, -3.5)
        want = about(2.0 * 7.0 / 6.0, -3.5, 30)
        assert to_of(moves)[1] == (pytest.approx(want[0], abs=0.0006), 0.6, pytest.approx(want[1], abs=0.0006))

    def test_a_quarter_turn_of_a_turned_area_swings_them_about_its_middle(self):
        angled = room(stage={"heading_deg": 30.0})
        x, z = about(2.0, -3.5, 30)
        _, item, moves = carried(angled, [light(1, x, 0.6, z)], width=3.0, depth=6.0)
        want = about(2.0, -3.5, 120)
        assert item["heading_deg"] == 30.0
        assert to_of(moves)[1] == (pytest.approx(want[0], abs=0.0006), 0.6, pytest.approx(want[1], abs=0.0006))
        assert turned_to(moves) == {1: -90.0}


class TestARiserOnATurnedStage:

    def stack(self):
        box = {"center_x": 1.0, "center_z": -3.5, "width": 0.5, "depth": 0.5, "height": 0.2, "base_height": 0.9,
               "name": "Box", "kind": "riser", "suggested": False}
        return room(extra=[copy.deepcopy(DRUM), box])

    def lights(self):
        """One on the stage, one on the drum riser, one on the box."""
        return [light(1, -2.0, 0.6, -3.5), light(2, 1.8, 0.9, -3.3), light(3, 1.0, 1.1, -3.5)]

    def test_it_is_swung_about_the_stages_middle_and_turned_with_it(self):
        shell, fixtures = self.stack(), self.lights()
        _, item = edit_item(shell, "risers", 0, heading_deg=30)
        stacked = carried_areas(shell, 0, item)

        assert [entry["index"] for entry in stacked] == [1, 2]
        drum = stacked[0]
        assert drum["turned"] is True and drum["turn"] == 30.0
        assert (drum["item"]["center_x"], drum["item"]["center_z"]) == (0.866, -3.0)
        # Its sides are its own; its heading is the stage's turn on what it had.
        assert (drum["item"]["width"], drum["item"]["depth"], drum["item"]["heading_deg"]) == (2.0, 1.0, 30.0)
        assert MOVED_BY_HAND in drum["item"]["basis"]
        assert drum["from"] == {"center_x": 1.0, "center_z": -3.5, "width": 2.0, "depth": 1.0, "base_height": 0.6,
                                "heading_deg": 0.0}
        assert drum["to"] == {"center_x": 0.866, "center_z": -3.0, "width": 2.0, "depth": 1.0, "base_height": 0.6,
                              "heading_deg": 30.0}
        assert stacked[1]["item"]["heading_deg"] == 30.0
        # Nothing given was changed.
        assert shell == self.stack()

        # The lights on each go round the stage's middle with what they stand on.
        moves = carried_area_moves(shell, stacked, fixtures)
        assert [sorted(to_of(theirs)) for theirs in moves] == [[2], [3]]
        for theirs in moves:
            for move in theirs:
                was = move["from"]
                x, z = about(was["x"], was["z"], 30)
                assert (move["to"]["x"], move["to"]["z"]) == (pytest.approx(x, abs=0.0015), pytest.approx(z, abs=0.0015))
                assert move["to"]["rotation_y"] == -30.0 and move["to"]["y"] == was["y"]
        # And the one on the stage itself, with the stage.
        assert sorted(to_of(carried_moves(shell, "risers", 0, item, fixtures))) == [1]

    def test_a_turn_to_90_carries_the_stack_where_the_quarter_turn_does(self):
        shell, fixtures = self.stack(), self.lights()

        def carry(**changes):
            _, item = edit_item(shell, "risers", 0, **changes)
            stacked = carried_areas(shell, 0, item)
            return stacked, carried_area_moves(shell, stacked, fixtures)

        by_heading, a = carry(heading_deg=90)
        by_sides, b = carry(width=3.0, depth=6.0)
        for one, other in zip(by_heading, by_sides):
            assert (one["item"]["center_x"], one["item"]["center_z"]) == (other["item"]["center_x"], other["item"]["center_z"])
            for got, want in zip(sorted(area_corners(one["item"])), sorted(area_corners(other["item"]))):
                assert got == (pytest.approx(want[0]), pytest.approx(want[1]))
        assert [to_of(theirs) for theirs in a] == [to_of(theirs) for theirs in b]
        assert [turned_to(theirs) for theirs in a] == [turned_to(theirs) for theirs in b]
        # Said by the sides, a riser's own sides change places and no heading is written, as before.
        assert "heading_deg" not in by_sides[0]["item"] and "heading_deg" not in by_sides[0]["to"]
        assert (by_sides[0]["item"]["width"], by_sides[0]["item"]["depth"]) == (1.0, 2.0)
        assert by_heading[0]["item"]["heading_deg"] == 90.0

    def test_one_already_at_a_heading_keeps_how_far_off_square_it_was(self):
        shell = self.stack()
        shell["risers"][1]["heading_deg"] = 80.0
        _, item = edit_item(shell, "risers", 0, heading_deg=30)
        drum = carried_areas(shell, 0, item)[0]
        # 110 is stored as -70: a rectangle looks the same after half a turn.
        assert drum["item"]["heading_deg"] == -70.0 and drum["from"]["heading_deg"] == 80.0

    def test_a_turn_and_the_turn_back_leave_the_stack_as_it_was(self):
        shell = self.stack()
        there, item = edit_item(shell, "risers", 0, heading_deg=30)
        for entry in carried_areas(shell, 0, item):
            there["risers"][entry["index"]] = entry["item"]
        back, item = edit_item(there, "risers", 0, heading_deg=0)
        stacked = carried_areas(there, 0, item)
        assert [entry["index"] for entry in stacked] == [1, 2]
        for entry in stacked:
            was = shell["risers"][entry["index"]]
            assert entry["item"]["center_x"] == pytest.approx(was["center_x"], abs=0.001)
            assert entry["item"]["center_z"] == pytest.approx(was["center_z"], abs=0.001)
            assert area_heading(entry["item"]) == 0.0

    def test_a_moved_turned_stage_carries_its_stack_as_any_does(self):
        angled = self.stack()
        angled["risers"][0]["heading_deg"] = 90.0
        angled["risers"][1].update({"center_x": 0.0, "center_z": -1.5})
        angled["risers"][2].update({"center_x": 0.0, "center_z": -1.5})
        _, item = edit_item(angled, "risers", 0, center_x=1.0)
        stacked = carried_areas(angled, 0, item)
        assert [(entry["item"]["center_x"], entry["item"]["center_z"]) for entry in stacked] == [(1.0, -1.5)] * 2
        assert all("heading_deg" not in entry["item"] and entry["turn"] == 0.0 for entry in stacked)


class TestTheWallsAreAskedAboutItAsItStands:

    def test_a_turned_area_past_a_wall_is_listed_and_a_square_one_is_not(self):
        assert outside_report(room())["items"] == []
        end_on = outside_report(room(stage={"heading_deg": 90.0}))["items"]
        assert [(entry["kind"], entry["index"], entry["reason"]) for entry in end_on] == [
            ("risers", 0, "partly outside the walls"),
        ]
        # Turned in a corner: the box it would fill standing square is inside, and a corner of it is not.
        corner = room(stage={"center_x": -4.4, "center_z": -3.4, "width": 3.0, "depth": 3.0})
        assert outside_report(corner)["items"] == []
        corner["risers"][0]["heading_deg"] = 45.0
        assert [entry["reason"] for entry in outside_report(corner)["items"]] == ["partly outside the walls"]
