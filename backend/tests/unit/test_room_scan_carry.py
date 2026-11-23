"""
Fixtures that follow their truss: the geometry
==============================================

services/room_scan/carry.py works out which fixtures hang on a line or ring of
a stored room and where they go when it is moved, raised, turned or resized.
docs/ROOM_SCAN.md.

What has to hold: a fixture is hung by the views' own reach (0.3 m on the plan,
0.6 m in height) and on the nearer of two trusses; each kind of change keeps a
fixture's place on its truss; a turn is the smaller of the two that give the
heading, whichever way the line's ends are stored, and a light square to the
truss stays square to it; one carried out of the room refuses the edit; and an
undo puts back only what still stands where the edit left it.

No database and no device: the fixtures are plain objects.
"""

import math
from types import SimpleNamespace

import pytest

from app.services.fixture_library.stage_axes import stage_rotation_matrix
from app.services.room_scan.carry import (
    apply_moves, carried_moves, carried_words, hangs_on, hung_fixtures, line_turn, put_back, put_back_words,
    refuse_outside,
)
from app.services.room_scan.edit import ShellEditError, edit_item

PATCH = {"dmx_address": 17, "universe": 1, "mode_id": 3, "tags": ["position_source:template", "position_unconfirmed"]}


def light(fixture_id, x, y, z, heading=0.0, name=None):
    return SimpleNamespace(
        id=fixture_id, name=name or f"Spot {fixture_id}", position_x=x, position_y=y, position_z=z,
        rotation_y=heading, **{key: (list(value) if isinstance(value, list) else value) for key, value in PATCH.items()},
    )


def room(lines=None, rings=None):
    """A 12 m by 10 m by 6 m room with one 8 m truss across it at 4 m, unless told otherwise."""
    return {
        "source": "scan",
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0},
        "risers": [],
        "truss_lines": lines if lines is not None else [
            {"name": "Truss 1", "x1": -4.0, "z1": -1.0, "x2": 4.0, "z2": -1.0, "height": 4.0, "top": 4.3},
        ],
        "truss_rings": rings if rings is not None else [],
        "hanging_bands": [{"height": 4.0, "top": 4.3, "lines": 1, "rings": 0}],
    }


def carried(shell, kind, index, fixtures, **changes):
    """The edit, and the moves it would carry: (shell after, item after, moves)."""
    after, item = edit_item(shell, kind, index, **changes)
    return after, item, carried_moves(shell, kind, index, item, fixtures)


def to_of(moves):
    return {move["rig_fixture_id"]: (move["to"]["x"], move["to"]["y"], move["to"]["z"]) for move in moves}


class TestWhatHangsOnIt:

    def test_a_fixture_within_reach_on_the_plan_and_in_height_hangs_on_a_line(self):
        line = room()["truss_lines"][0]
        assert hangs_on("truss_lines", line, light(1, 0.0, 4.0, -1.0))
        # 0.3 m off to the side and 0.6 m under it is still on it; a little more is not.
        assert hangs_on("truss_lines", line, light(2, 2.0, 3.4, -0.7))
        assert not hangs_on("truss_lines", line, light(3, 2.0, 4.0, -0.69))
        assert not hangs_on("truss_lines", line, light(4, 2.0, 3.39, -1.0))
        # Past an end it is the distance to the end that counts.
        assert hangs_on("truss_lines", line, light(5, 4.25, 4.0, -1.0))
        assert not hangs_on("truss_lines", line, light(6, 4.35, 4.0, -1.0))

    def test_a_fixture_near_the_circle_hangs_on_a_ring_and_one_at_its_middle_does_not(self):
        ring = {"center_x": 1.0, "center_z": 2.0, "radius": 1.5, "height": 4.5}
        assert hangs_on("truss_rings", ring, light(1, 2.5, 4.5, 2.0))
        assert hangs_on("truss_rings", ring, light(2, 1.0, 4.2, 0.75))
        assert not hangs_on("truss_rings", ring, light(3, 1.0, 4.5, 2.0))

    def test_a_fixture_with_no_position_or_a_truss_with_no_numbers_hangs_nothing(self):
        line = room()["truss_lines"][0]
        assert not hangs_on("truss_lines", line, light(1, None, 4.0, -1.0))
        assert not hangs_on("truss_lines", {**line, "height": None}, light(1, 0.0, 4.0, -1.0))
        assert not hangs_on("truss_lines", {**line, "x2": -3.9}, light(1, -4.0, 4.0, -1.0))
        assert hung_fixtures(None, "truss_lines", 0, [light(1, 0.0, 4.0, -1.0)]) == []
        assert hung_fixtures(room(), "risers", 0, [light(1, 0.0, 4.0, -1.0)]) == []

    def test_where_two_trusses_cross_each_keeps_its_own_lights(self):
        shell = room(lines=[
            {"name": "Across", "x1": -4.0, "z1": 0.0, "x2": 4.0, "z2": 0.0, "height": 4.0},
            {"name": "Down", "x1": 0.0, "z1": -3.0, "x2": 0.0, "z2": 3.0, "height": 4.0},
        ])
        on_across, on_down, at_the_cross = light(1, 0.2, 4.0, 0.05), light(2, 0.05, 4.0, 0.2), light(3, 0.1, 4.0, 0.1)
        lights = [on_across, on_down, at_the_cross]
        # Each is within reach of both; the nearer has it, and the first listed when they are as near.
        assert hung_fixtures(shell, "truss_lines", 0, lights) == [on_across, at_the_cross]
        assert hung_fixtures(shell, "truss_lines", 1, lights) == [on_down]


class TestWhereTheyGo:

    def test_a_move_shifts_each_by_what_the_middle_shifted(self):
        shell = room()
        lights = [light(1, -3.0, 3.8, -1.1), light(2, 3.0, 4.0, -1.0), light(3, 0.0, 1.0, 3.0, name="Floor")]
        _, _, moves = carried(shell, "truss_lines", 0, lights, center_x=0.5, center_z=1.0)
        assert to_of(moves) == {1: (-2.5, 3.8, 0.9), 2: (3.5, 4.0, 1.0)}
        # From is what the fixture had, and its heading is not touched by a move.
        assert moves[0]["from"] == {"x": -3.0, "y": 3.8, "z": -1.1, "rotation_y": 0.0}
        assert moves[0]["to"]["rotation_y"] == 0.0 and moves[0]["name"] == "Spot 1"

    def test_a_height_keeps_how_far_under_the_truss_each_hangs(self):
        lights = [light(1, -3.0, 3.8, -1.0), light(2, 3.0, 4.0, -1.0)]
        _, _, moves = carried(room(), "truss_lines", 0, lights, height=5.25)
        assert to_of(moves) == {1: (-3.0, 5.05, -1.0), 2: (3.0, 5.25, -1.0)}

    def test_a_length_spreads_places_along_the_line_and_keeps_the_offset_to_the_side(self):
        lights = [light(1, -3.0, 4.0, -1.0), light(2, 1.0, 4.0, -0.8), light(3, 0.0, 4.0, -1.0)]
        _, item, moves = carried(room(), "truss_lines", 0, lights, length=4.0)
        assert (item["x1"], item["x2"]) == (-2.0, 2.0)
        # The one in the middle has nowhere to go.
        assert to_of(moves) == {1: (-1.5, 4.0, -1.0), 2: (0.5, 4.0, -0.8)}

    def test_a_turn_swings_each_about_the_middle_and_turns_its_heading_with_it(self):
        lights = [light(1, -3.0, 4.0, -1.0, heading=0.0), light(2, 2.0, 4.0, -0.8, heading=170.0)]
        _, item, moves = carried(room(), "truss_lines", 0, lights, heading_deg=90)
        assert (item["x1"], item["z1"], item["x2"], item["z2"]) == (0.0, -5.0, 0.0, 3.0)
        # A quarter turn clockwise seen from above: stage right goes upstage, and 0.2 m downstage of it goes 0.2 m stage right.
        assert to_of(moves) == {1: (0.0, 4.0, -4.0), 2: (-0.2, 4.0, 1.0)}
        assert [move["to"]["rotation_y"] for move in moves] == [-90.0, 80.0]

    @pytest.mark.parametrize("heading", [30.0, 90.0, -45.0, 80.0])
    def test_a_light_square_to_the_truss_is_still_square_to_it_after_a_turn(self, heading):
        """rotation_y turns the other way round from a line's heading: this pins the sign."""
        shell = room()
        spot = light(1, 2.0, 4.0, -1.0, heading=0.0)  # aims downstage, square to a truss across the room
        _, item, moves = carried(shell, "truss_lines", 0, [spot], heading_deg=heading)
        apply_moves([spot], moves)
        aim = [row[2] for row in stage_rotation_matrix(0.0, spot.rotation_y, 0.0)]  # where its +Z points
        run = (item["x2"] - item["x1"], item["z2"] - item["z1"])
        # The line's ends are stored to the millimetre, so square is square to that.
        assert aim[0] * run[0] + aim[2] * run[1] == pytest.approx(0.0, abs=1e-3)
        assert spot.rotation_y == pytest.approx(-heading, abs=0.05)
        # And it is still on the truss, as far from the middle as it was.
        assert hangs_on("truss_lines", item, spot)
        assert math.hypot(spot.position_x, spot.position_z + 1.0) == pytest.approx(2.0, abs=0.002)

    def test_a_turn_is_the_smaller_one_whichever_way_the_ends_are_stored(self):
        """80 degrees to -80 is 20 degrees on, not 160 back: the ends are written the other way round after it."""
        steep = {"x1": -0.5, "z1": -2.836, "x2": 0.5, "z2": 2.836, "height": 4.0}
        other = {"x1": -0.5, "z1": 2.836, "x2": 0.5, "z2": -2.836, "height": 4.0}
        assert line_turn(steep, other) == pytest.approx(20.0, abs=0.05)
        assert line_turn(other, steep) == pytest.approx(-20.0, abs=0.05)
        # The same line with its ends swapped has not turned at all.
        swapped = {"x1": 0.5, "z1": 2.836, "x2": -0.5, "z2": -2.836, "height": 4.0}
        assert line_turn(steep, swapped) == 0.0

        shell = room(lines=[{"name": "Steep", **steep}])
        top = light(1, 0.5, 4.0, 2.836)
        _, item, moves = carried(shell, "truss_lines", 0, [top], heading_deg=-80)
        # It went 20 degrees on round, to the downstage end of the line as it now runs.
        assert to_of(moves)[1] == pytest.approx((-0.5, 4.0, 2.836), abs=0.01)
        assert hangs_on("truss_lines", item, SimpleNamespace(position_x=-0.5, position_y=4.0, position_z=2.836))
        assert moves[0]["to"]["rotation_y"] == pytest.approx(-20.0, abs=0.05)

    def test_a_ring_keeps_each_ones_angle_and_how_far_off_the_truss_it_is(self):
        shell = room(lines=[], rings=[{"name": "Ring", "center_x": 0.0, "center_z": 1.0, "radius": 1.0, "height": 4.5}])
        lights = [light(1, 1.0, 4.5, 1.0), light(2, 0.0, 4.3, 0.0), light(3, -0.8, 4.5, 1.0), light(4, 0.0, 4.5, 2.25)]
        _, _, moves = carried(shell, "truss_rings", 0, lights, radius=2.0)
        assert to_of(moves) == {1: (2.0, 4.5, 1.0), 2: (0.0, 4.3, -1.0), 3: (-1.8, 4.5, 1.0), 4: (0.0, 4.5, 3.25)}
        _, _, moves = carried(shell, "truss_rings", 0, lights, center_x=1.0, height=4.0)
        assert to_of(moves) == {1: (2.0, 4.0, 1.0), 2: (1.0, 3.8, 0.0), 3: (0.2, 4.0, 1.0), 4: (1.0, 4.0, 2.25)}
        assert all(move["to"]["rotation_y"] == 0.0 for move in moves)

    def test_they_follow_the_middle_the_edit_stored_not_the_one_asked_for(self):
        # 12 m across and 2 m round it: a middle asked for at 9 m is held at 8 m.
        _, item, moves = carried(room(), "truss_lines", 0, [light(1, 0.0, 4.0, -1.0)], center_x=9.0)
        assert (item["x1"] + item["x2"]) / 2 == 8.0
        assert to_of(moves) == {1: (8.0, 4.0, -1.0)}

    def test_a_rename_a_raised_area_and_an_edit_that_changes_nothing_carry_nothing(self):
        shell = {**room(), "risers": [{"name": "Stage", "center_x": 0.0, "center_z": -1.0, "width": 6.0, "depth": 2.0, "height": 0.6}]}
        lights = [light(1, 0.0, 4.0, -1.0), light(2, 0.0, 0.6, -1.0)]
        assert carried(shell, "truss_lines", 0, lights, name="Front truss")[2] == []
        assert carried(shell, "truss_lines", 0, lights, height=4.0, center_x=0.0)[2] == []
        assert carried(shell, "risers", 0, lights, center_x=2.0, height=1.0)[2] == []

    def test_only_a_position_and_a_heading_are_written(self):
        shell = room()
        spot, other = light(1, 2.0, 4.0, -1.0, heading=10.0), light(2, 0.0, 1.0, 3.0)
        _, _, moves = carried(shell, "truss_lines", 0, [spot, other], center_z=0.0, heading_deg=45, height=3.5)
        apply_moves([spot, other], moves)
        assert {key: getattr(spot, key) for key in PATCH} == PATCH
        assert (other.position_x, other.position_y, other.position_z, other.rotation_y) == (0.0, 1.0, 3.0, 0.0)
        assert spot.position_y == 3.5 and spot.rotation_y == -35.0


class TestOutOfTheRoom:

    def test_a_fixture_carried_past_the_margin_refuses_the_edit_and_names_it(self):
        shell = room()
        lights = [light(n, x, 4.0, -1.0) for n, x in enumerate((-3.0, -1.0, 1.0, 3.0), start=1)]
        # A plain move holds the truss's middle only: its stage-left end, and the lights on it, go past 8 m.
        after, item, moves = carried(shell, "truss_lines", 0, lights, center_x=7.5)
        with pytest.raises(ShellEditError) as refused:
            refuse_outside(after, "truss_lines", item, moves)
        assert refused.value.status == 422
        detail = refused.value.detail
        assert "That would carry 2 fixtures hung on Truss 1 out of the room and the 2 m round it" in detail
        assert "Spot 3 to 8.5, 4, -1" in detail and "Spot 4 to 10.5, 4, -1" in detail
        # One that stops on the margin itself is still inside it.
        on_the_line = carried(shell, "truss_lines", 0, lights[:3], center_x=7.0)
        refuse_outside(on_the_line[0], "truss_lines", on_the_line[1], on_the_line[2])
        assert "Nothing was changed" in detail and "carry_fixtures false" in detail
        # Nothing was written to a fixture by working that out.
        assert [spot.position_x for spot in lights] == [-3.0, -1.0, 1.0, 3.0]

    def test_one_through_the_floor_or_far_over_the_ceiling_refuses_it_and_one_inside_does_not(self):
        shell = room()
        low = light(1, 0.0, 3.4, -1.0)
        after, item, moves = carried(shell, "truss_lines", 0, [low], height=0.5)
        with pytest.raises(ShellEditError):
            refuse_outside(after, "truss_lines", item, moves)
        after, item, moves = carried(shell, "truss_lines", 0, [low], center_x=3.0, height=6.0)
        refuse_outside(after, "truss_lines", item, moves)
        refuse_outside({**after, "room": {}}, "truss_lines", item, [{**moves[0], "to": {"x": 90.0, "y": 50.0, "z": 0.0}}])
        with pytest.raises(ShellEditError):
            refuse_outside(after, "truss_lines", item, [{**moves[0], "name": "High", "to": {"x": 0.0, "y": 8.01, "z": 0.0}}])


class TestPutBack:

    def test_an_undo_puts_each_back_exactly_and_leaves_one_moved_since(self):
        shell = room()
        lights = [light(1, -3.0, 3.8123456, -1.0, heading=5.0), light(2, 3.0, 4.0, -1.0), light(3, 0.0, 4.0, -1.0)]
        _, _, moves = carried(shell, "truss_lines", 0, lights, center_z=1.0, heading_deg=30)
        apply_moves(lights, moves)
        # Somebody drags one of them afterwards, and one is taken out of the rig.
        lights[1].position_x = 0.75
        restored, skipped = put_back(lights[:2], moves)

        assert [entry["rig_fixture_id"] for entry in restored] == [1]
        assert (lights[0].position_x, lights[0].position_y, lights[0].position_z, lights[0].rotation_y) == (
            -3.0, 3.8123456, -1.0, 5.0,
        )
        assert skipped == [
            {"rig_fixture_id": 2, "name": "Spot 2", "reason": "it was moved since"},
            {"rig_fixture_id": 3, "name": "Spot 3", "reason": "it is no longer in the rig"},
        ]
        assert lights[1].position_x == 0.75
        assert {key: getattr(lights[0], key) for key in PATCH} == PATCH

    def test_a_record_that_cannot_be_read_moves_nothing(self):
        spot = light(1, 0.0, 4.0, 0.0)
        assert put_back([spot], None) == ([], [])
        restored, skipped = put_back([spot], ["?", {"rig_fixture_id": 1, "from": {"x": 1.0}, "to": None}])
        assert restored == [] and skipped[0]["reason"] == "the record of its move cannot be read"
        assert spot.position_x == 0.0


class TestWords:

    def test_what_an_edit_and_an_undo_say_about_the_fixtures(self):
        truss = {"name": "Truss 1"}
        assert carried_words("truss_lines", truss, 4, True) == "4 fixtures hung on Truss 1 moved with it."
        assert carried_words("truss_rings", {"name": "Ring"}, 1, True) == "1 fixture hung on Ring moved with it."
        assert carried_words("truss_lines", truss, 0, True) == "No fixture was moved: none that hangs on it had to move."
        assert carried_words("truss_lines", truss, 0, False) == (
            "The fixtures hung on Truss 1 were left where they are, as asked."
        )
        assert carried_words("risers", {"name": "Stage"}, 0, True) == "No fixture was moved."
        assert put_back_words(0, 0) == "No fixture was moved."
        assert put_back_words(4, 0) == "4 fixtures put back where they hung before it."
        assert put_back_words(1, 2) == (
            "1 fixture put back where it hung before it. 2 fixtures left alone, because they have been moved since."
        )
        assert put_back_words(0, 1) == "No fixture was put back. 1 fixture left alone, because it has been moved since."
