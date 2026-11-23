"""
Editing a stored room's walls by hand (services/room_scan/outline_edit.py)
==========================================================================

What has to hold: the walls asked for are the walls stored, as corners the
readers take for an outline; the room's box is the one centred on the origin
that holds them; a box is still stored as a box; walls that are not a room
are refused in a sentence and the shell given is never changed; and what the
new walls leave outside is reported and not moved. docs/ROOM_SCAN.md.
"""

import copy
from types import SimpleNamespace

import pytest

from app.services.room_scan.edit import ShellEditError
from app.services.room_scan.outline_edit import (
    check_walls, clean_corners, crossing_walls, delete_corner, insert_corner, move_corner, outline_area,
    outside_report, outside_words, room_corners, set_outline, within_walls,
)


def box_shell() -> dict:
    """A 12 m by 10 m by 6 m box room with a stage, a truss across it and a ring."""
    return {
        "source": "scan", "suggested": True,
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0, "suggested": True, "basis": "scan: 4 of 4 walls found"},
        "risers": [{"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6,
                    "base_height": 0.0, "name": "Stage", "kind": "stage"}],
        "truss_lines": [{"name": "Truss 1", "x1": -4.0, "z1": -2.0, "x2": 4.0, "z2": -2.0, "height": 4.2, "top": 4.5}],
        "truss_rings": [{"name": "Ring 1", "center_x": 3.0, "center_z": 2.0, "radius": 1.5, "height": 4.2, "top": 4.5}],
        "hanging_bands": [{"height": 4.2, "top": 4.5, "lines": 1, "rings": 1, "suggested": True, "basis": "scan"}],
    }


# An L: the box with its downstage stage left quarter cut out.
L_CORNERS = [[-6, -5], [6, -5], [6, 0], [0, 0], [0, 5], [-6, 5]]


def l_shell() -> dict:
    shell, _ = set_outline(box_shell(), corners=L_CORNERS)
    return shell


def refused(call, status: int, words: str) -> None:
    with pytest.raises(ShellEditError) as error:
        call()
    assert error.value.status == status, error.value.detail
    assert words in error.value.detail, error.value.detail


def light(fixture_id: int, x: float, y: float, z: float, name: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=fixture_id, name=name or f"Spot {fixture_id}", position_x=x, position_y=y, position_z=z)


class TestReadingTheWalls:

    def test_a_box_room_has_four_corners_in_the_order_the_plan_draws_them(self):
        corners, box = room_corners(box_shell())
        assert box is True
        assert corners == [(-6.0, -5.0), (6.0, -5.0), (6.0, 5.0), (-6.0, 5.0)]
        assert outline_area(corners) > 0

    def test_a_stored_outline_is_read_as_it_is(self):
        corners, box = room_corners(l_shell())
        assert box is False and corners == [tuple(map(float, corner)) for corner in L_CORNERS]

    def test_no_scanned_room_and_no_size_are_refused(self):
        refused(lambda: room_corners(None), 404, "no scanned room")
        refused(lambda: room_corners({"source": "preset", "room": {"width": 5, "depth": 5}}), 404, "no scanned room")
        refused(lambda: room_corners({"source": "scan", "room": {"height": 5}}), 409, "has no size")
        refused(lambda: room_corners({"source": "scan"}), 409, "has no size")


class TestRedrawingTheWalls:

    def test_an_outline_is_stored_as_corners_with_the_box_round_it(self):
        before = box_shell()
        untouched = copy.deepcopy(before)

        shell, done = set_outline(before, corners=L_CORNERS)

        assert done == "Walls redrawn"
        assert before == untouched
        room = shell["room"]
        assert room["outline"] == [{"x": float(x), "z": float(z)} for x, z in L_CORNERS]
        assert (room["width"], room["depth"], room["height"]) == (12.0, 10.0, 6.0)
        assert room["suggested"] is False and room["basis"].endswith("Walls set by hand.")
        # Nothing else in the room is touched, and the hanging heights stand.
        for key in ("risers", "truss_lines", "truss_rings", "hanging_bands"):
            assert shell[key] == before[key]

    def test_the_box_is_centred_on_the_origin_which_does_not_move(self):
        # A room that runs from 4 m stage right to 10 m stage left of where the origin stays.
        shell, _ = set_outline(box_shell(), corners=[[-4, -5], [10, -5], [10, 5], [-4, 5]])
        room = shell["room"]
        assert len(room["outline"]) == 4
        assert (room["width"], room["depth"]) == (20.0, 10.0)

    def test_a_box_is_still_stored_as_a_box(self):
        shell, done = set_outline(box_shell(), corners=[[-7, -4], [7, -4], [7, 4], [-7, 4]])
        assert done == "Walls redrawn"
        assert "outline" not in shell["room"]
        assert (shell["room"]["width"], shell["room"]["depth"]) == (14.0, 8.0)
        # And an outline made a box again loses its corners.
        again, _ = set_outline(l_shell(), corners=[[-6, -5], [6, -5], [6, 5], [-6, 5]])
        assert "outline" not in again["room"] and (again["room"]["width"], again["room"]["depth"]) == (12.0, 10.0)

    def test_the_same_walls_change_nothing(self):
        before = box_shell()
        for corners in ([[-6, -5], [6, -5], [6, 5], [-6, 5]], [[6, 5], [-6, 5], [-6, -5], [6, -5]]):
            shell, done = set_outline(before, corners=corners)
            assert done is None and shell == before
        shell, done = set_outline(l_shell(), corners=L_CORNERS, height=6.0)
        assert done is None and shell == l_shell()

    def test_corners_are_taken_as_pairs_or_as_x_and_z_and_kept_to_the_millimetre(self):
        shell, _ = set_outline(box_shell(), corners=[{"x": -6.00049, "z": -5}, [6, -5], (6, 0.25), [-6, 5.0004]])
        assert shell["room"]["outline"] == [
            {"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": 6.0, "z": 0.25}, {"x": -6.0, "z": 5.0},
        ]

    def test_corners_given_anticlockwise_are_turned_clockwise_from_the_same_first_corner(self):
        shell, _ = set_outline(box_shell(), corners=list(reversed(L_CORNERS)))
        corners, _ = room_corners(shell)
        assert corners[0] == (-6.0, 5.0)
        assert outline_area(corners) > 0
        assert sorted(corners) == sorted(tuple(map(float, corner)) for corner in L_CORNERS)

    def test_the_height_is_set_alone_or_with_the_walls(self):
        shell, done = set_outline(box_shell(), height=5.25)
        assert done == "Room height set to 5.25 m"
        assert shell["room"]["height"] == 5.25 and "outline" not in shell["room"]
        assert shell["room"]["basis"].endswith("Height set by hand.")
        assert (shell["room"]["width"], shell["room"]["depth"]) == (12.0, 10.0)

        both, done = set_outline(box_shell(), corners=L_CORNERS, height=7)
        assert done == "Walls redrawn and room height set to 7 m"
        assert both["room"]["height"] == 7.0 and len(both["room"]["outline"]) == 6

    @pytest.mark.parametrize("corners, words", [
        ("walls", "must be a list of corners"),
        ([[0, 0], [4, 0]], "between 3 and 64 corners; 2 were given"),
        ([[0, 0]] * 65, "between 3 and 64 corners"),
        ([[0, 0], [4, 0], [4]], "Corner 3 must be two numbers"),
        ([[0, 0], [4, 0], [4, "far"]], "Corner 3 must be two numbers"),
        ([[0, 0], [4, 0], [4, float("nan")]], "Corner 3 must be two numbers"),
        ([[0, 0], [float("inf"), 0], [4, 4]], "Corner 2 must be two numbers"),
        ([[0, 0], [4, 0], [4, True]], "Corner 3 must be two numbers"),
        ([[0, 0], [4, 0], [4, 150]], "Corner 3 would be 150 m from the middle"),
        ([[0, 0], [4, 0], [4.05, 0], [4, 4]], "Corners 2 and 3 would be 0.05 m apart"),
        # A bow tie.
        ([[-3, -3], [3, 3], [3, -3], [-3, 3]], "The walls would cross"),
        # A corner laid on a wall it is not an end of.
        ([[-3, -3], [3, -3], [3, 3], [0, -3], [-3, 3]], "The walls would cross"),
        # A spike that doubles back along its own wall.
        ([[-3, -3], [3, -3], [0, -3], [0, 3], [-3, 3]], "The walls would cross"),
        # Wide enough each way, and still no floor to speak of.
        ([[0, 0], [1.2, 0], [0, 1.2]], "at least 1 m2"),
        ([[0, 0], [0.8, 0], [0.8, 3], [0, 3]], "0.8 m across"),
        ([[0, 0], [3, 0], [3, 0.9], [0, 0.9]], "0.9 m from upstage to downstage"),
    ])
    def test_walls_that_are_not_a_room_are_refused_in_a_sentence(self, corners, words):
        before = box_shell()
        untouched = copy.deepcopy(before)
        refused(lambda: set_outline(before, corners=corners), 422, words)
        assert before == untouched

    @pytest.mark.parametrize("height, words", [
        (1.2, "between 1.5 m and 30 m; 1.2 m is not"), (31, "between 1.5 m and 30 m"),
        (float("nan"), "must be a number of metres"), (float("inf"), "must be a number of metres"),
        ("high", "must be a number of metres"), (True, "must be a number of metres"),
    ])
    def test_a_height_no_room_has_is_refused(self, height, words):
        refused(lambda: set_outline(box_shell(), height=height), 422, words)

    def test_nothing_given_is_refused_and_so_is_a_rig_with_no_scanned_room(self):
        refused(lambda: set_outline(box_shell()), 422, "Nothing to change")
        refused(lambda: set_outline(None, height=5), 404, "no scanned room")
        refused(lambda: set_outline({"source": "preset", "room": {}}, height=5), 404, "no scanned room")

    def test_three_corners_in_a_line_are_two_walls_end_to_end(self):
        corners = [(-6.0, -5.0), (0.0, -5.0), (6.0, -5.0), (6.0, 5.0), (-6.0, 5.0)]
        assert crossing_walls(corners) is None
        assert check_walls(corners) == corners
        assert crossing_walls([(0.0, 0.0), (4.0, 0.0), (0.0, 3.0)]) is None

    def test_clean_corners_reads_and_rounds_without_judging_the_room(self):
        assert clean_corners([[0, 0], [1.23456, 0], [0, 1]]) == [(0.0, 0.0), (1.235, 0.0), (0.0, 1.0)]


class TestOneCorner:

    def test_a_corner_of_a_box_room_is_moved_and_the_room_becomes_an_outline(self):
        before = box_shell()
        shell, done, index = move_corner(before, 2, x=8, z=6)
        assert (done, index) == ("Walls: corner 3 moved", 2)
        assert shell["room"]["outline"] == [
            {"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": 8.0, "z": 6.0}, {"x": -6.0, "z": 5.0},
        ]
        assert (shell["room"]["width"], shell["room"]["depth"]) == (16.0, 12.0)
        assert before == box_shell()

    def test_one_of_x_and_z_keeps_the_other(self):
        shell, _, _ = move_corner(l_shell(), 3, x=1.5)
        assert shell["room"]["outline"][3] == {"x": 1.5, "z": 0.0}
        shell, _, _ = move_corner(l_shell(), 3, z=-1)
        assert shell["room"]["outline"][3] == {"x": 0.0, "z": -1.0}

    def test_a_corner_moved_to_where_it_is_changes_nothing(self):
        shell, done, index = move_corner(l_shell(), 3, x=0, z=0.0004)
        assert done is None and index == 3 and shell == l_shell()

    def test_a_move_that_crosses_the_walls_is_refused(self):
        refused(lambda: move_corner(l_shell(), 3, x=-8, z=8), 422, "The walls would cross")
        refused(lambda: move_corner(l_shell(), 3, x=float("nan")), 422, "must be a number of metres")
        refused(lambda: move_corner(l_shell(), 3), 422, "Nothing to change")
        refused(lambda: move_corner(l_shell(), 6, x=1), 404, "no corner number 7 (it has 6)")
        refused(lambda: move_corner(l_shell(), -1, x=1), 404, "no corner number 0")

    def test_a_corner_is_added_half_way_along_a_wall_and_changes_no_wall(self):
        shell, done, index = insert_corner(box_shell(), 1)
        assert (done, index) == ("Walls: corner added after corner 2", 2)
        assert shell["room"]["outline"] == [
            {"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": 6.0, "z": 0.0}, {"x": 6.0, "z": 5.0}, {"x": -6.0, "z": 5.0},
        ]
        assert (shell["room"]["width"], shell["room"]["depth"]) == (12.0, 10.0)
        # After the last corner is on the wall back to the first.
        shell, _, index = insert_corner(l_shell(), 5)
        assert index == 6 and shell["room"]["outline"][6] == {"x": -6.0, "z": 0.0}

    def test_a_corner_is_added_at_a_place_given(self):
        shell, _, index = insert_corner(box_shell(), 1, x=8, z=0)
        assert shell["room"]["outline"][index] == {"x": 8.0, "z": 0.0}
        assert shell["room"]["width"] == 16.0
        refused(lambda: insert_corner(box_shell(), 1, x=8), 422, "both x and z")
        refused(lambda: insert_corner(box_shell(), 1, x=8, z=float("inf")), 422, "must be a number of metres")
        refused(lambda: insert_corner(box_shell(), 4), 404, "no corner number 5")

    def test_a_room_holds_no_more_than_64_corners(self):
        shell = box_shell()
        # A comb along the upstage wall would be simpler to read; a many-sided room is simpler to build.
        import math
        ring = [[round(8 * math.cos(2 * math.pi * k / 64), 3), round(8 * math.sin(2 * math.pi * k / 64), 3)] for k in range(64)]
        full, _ = set_outline(shell, corners=ring)
        refused(lambda: insert_corner(full, 0), 409, "already has 64 corners")

    def test_a_corner_is_deleted_and_the_rest_move_up(self):
        shell, done = delete_corner(l_shell(), 3)
        assert done == "Walls: corner 4 deleted"
        assert shell["room"]["outline"] == [
            {"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": 6.0, "z": 0.0}, {"x": 0.0, "z": 5.0}, {"x": -6.0, "z": 5.0},
        ]

    def test_a_room_keeps_at_least_three_corners(self):
        triangle, _ = set_outline(box_shell(), corners=[[-6, -5], [6, -5], [0, 5]])
        refused(lambda: delete_corner(triangle, 0), 409, "at least 3 corners")
        refused(lambda: delete_corner(l_shell(), 9), 404, "no corner number 10")

    def test_a_triangle_turned_inside_out_is_renumbered_clockwise(self):
        triangle, _ = set_outline(box_shell(), corners=[[-6, -5], [6, -5], [0, 5]])
        shell, done, index = move_corner(triangle, 2, x=0, z=-9)
        corners, _ = room_corners(shell)
        assert done == "Walls: corner 3 moved"
        assert outline_area(corners) > 0 and corners[0] == (-6.0, -5.0)
        assert corners[index] == (0.0, -9.0) and index == 1


class TestWhatIsLeftOutside:

    def test_nothing_is_outside_a_room_that_holds_everything(self):
        report = outside_report(box_shell(), [light(1, 0, 4, 0), light(2, -6, 4, 5)])
        assert report == {"items": [], "fixtures": [], "count": 0}
        assert outside_words(report) == "Nothing in the room or the rig is outside the walls."

    def test_on_a_wall_is_inside(self):
        corners, _ = room_corners(l_shell())
        assert within_walls(corners, 6, -2) and within_walls(corners, 0, 2.5) and within_walls(corners, 0.009, 2.5)
        assert not within_walls(corners, 0.02, 2.5)

    def test_what_the_notch_of_an_l_cuts_off_is_listed_and_nothing_is_moved(self):
        before = box_shell()
        lights = [light(1, 3, 4, 3, "In the notch"), light(2, -3, 4, 3, "Inside"), light(3, 0, 4, 2.5, "On the wall")]
        shell = l_shell()
        was = outside_report(before, lights)

        report = outside_report(shell, lights, before=was)

        # The whole ring at (3, 2) with a 1.5 m radius is in the notch; the stage and the truss upstage are not.
        assert report["items"] == [{
            "kind": "truss_rings", "index": 0, "name": "Ring 1", "reason": "outside the walls",
            "already_outside": False,
        }]
        assert report["fixtures"] == [{
            "rig_fixture_id": 1, "name": "In the notch", "position": {"x": 3, "y": 4, "z": 3},
            "reason": "outside the walls", "already_outside": False,
        }]
        assert report["count"] == 2
        assert "2 things are now outside the walls or above the ceiling (2 of them since this change)" in outside_words(report)
        assert shell["truss_rings"] == before["truss_rings"]

    def test_all_of_an_item_outside_and_part_of_one_are_told_apart(self):
        # Walls drawn in to 1 m stage left and 3 m upstage of the middle: the ring
        # (1.5 to 4.5 m across) is beyond them, the stage and the truss reach past them.
        shell, _ = set_outline(box_shell(), corners=[[-6, -5], [1, -5], [1, -3], [-6, -3]])
        report = outside_report(shell)
        by_name = {entry["name"]: entry["reason"] for entry in report["items"]}
        assert by_name == {"Stage": "partly outside the walls", "Truss 1": "outside the walls", "Ring 1": "outside the walls"}

    def test_a_lowered_ceiling_lists_what_is_above_it(self):
        shell, _ = set_outline(box_shell(), height=4)
        report = outside_report(shell, [light(1, 0, 4.2, 0), light(2, 0, 4.0, 0), light(3, 9, 5, 0)])
        assert [(entry["name"], entry["reason"]) for entry in report["items"]] == [
            ("Truss 1", "above the ceiling"), ("Ring 1", "above the ceiling"),
        ]
        assert [(entry["rig_fixture_id"], entry["reason"]) for entry in report["fixtures"]] == [
            (1, "above the ceiling"), (3, "outside the walls and above the ceiling"),
        ]

    def test_what_was_outside_before_is_marked(self):
        lights = [light(1, 9, 4, 0)]
        was = outside_report(box_shell(), lights)
        assert [entry["already_outside"] for entry in was["fixtures"]] == [False]
        shell, _ = set_outline(box_shell(), height=5.5)
        report = outside_report(shell, lights, before=was)
        assert [entry["already_outside"] for entry in report["fixtures"]] == [True]
        assert outside_words(report) == (
            "1 thing is now outside the walls or above the ceiling, as before the change. Nothing was moved."
        )

    def test_a_rig_with_no_scanned_room_has_nothing_outside(self):
        assert outside_report(None, [light(1, 99, 99, 99)])["count"] == 0
        assert outside_report({"source": "preset"}, [light(1, 99, 99, 99)])["count"] == 0

    def test_an_item_with_numbers_missing_is_left_out(self):
        shell = l_shell()
        shell["truss_lines"].append({"name": "Broken", "x1": 3, "z1": 3})
        shell["risers"].append(None)
        assert [entry["name"] for entry in outside_report(shell)["items"]] == ["Ring 1"]
