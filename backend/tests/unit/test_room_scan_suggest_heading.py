"""
Room scan: a suggestion for a stage that stands at a heading (slice 27).

A stage, as slice 21 stores one, can stand at any heading (`heading_deg`,
degrees clockwise from across the room seen from above). What is checked:

  * a floor row goes onto a stage at 30, 90 and -60 degrees where the rule for
    a stage standing square would put it, swung about the stage's middle by
    the heading: parallel to the turned edges, as far in from them, its
    spacing kept, and each fixture turned as far;
  * a row drawn at the front of the stage ends at the turned front;
  * nothing is swung twice: the same scan read again moves nothing;
  * a stage at heading 0, at 180, or with a heading that cannot be read, moves
    fixtures exactly as one with no heading does;
  * in a box room and in an L-shaped room no fixture is ever left outside the
    walls or in the drop under the ceiling, whatever the heading and wherever
    the stage stands;
  * undoing the scan's moves turns the fixtures back.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.room_scan import suggest_positions
from app.services.room_scan.carry import _across_and_back
from app.services.room_scan.extract import clear_of_outline
from app.services.room_scan.suggest import (
    CEILING_DROP, STAGE_EDGE_CLEARANCE, TAG_SCAN_HINT, WALL_CLEARANCE, turned_rotation,
)
from app.services.room_scan.undo import plan_undo, record_moves, restore
from tests.unit.room_scan_meshes import L_ROOM

GUESS = ["position_source:template", "position_unconfirmed"]
HEADINGS = [30.0, 90.0, -60.0]


def fixture(id, x, y, z, group="Floor Pars", tags=None, rotation_y=0.0):
    return SimpleNamespace(
        id=id, name=f"Par {id}", group_name=group, position_x=x, position_y=y, position_z=z,
        rotation_y=rotation_y, tags=list(GUESS if tags is None else tags),
        universe=0, dmx_address=id * 10 + 1,
    )


def apply(fixtures, moves, file="room.obj", record=None):
    """What the endpoint does with the moves. Returns the undo record it would keep."""
    by_id = {f.id: f for f in fixtures}
    moved = []
    for move in moves:
        f = by_id[move.rig_fixture_id]
        entry = {
            "rig_fixture_id": f.id, "name": move.name, "from": move.from_position, "to": move.to_position,
            "tags_before": list(f.tags),
        }
        f.position_x, f.position_y, f.position_z = move.to_position
        if TAG_SCAN_HINT not in f.tags:
            f.tags = [*f.tags, TAG_SCAN_HINT]
        if move.turn_deg:
            entry["rotation_y_before"] = f.rotation_y
            f.rotation_y = turned_rotation(f.rotation_y, move.turn_deg)
            entry["rotation_y_after"] = f.rotation_y
        moved.append(entry)
    return record_moves(record, moved, file)


def stage(heading=None, center_x=0.0, center_z=-2.0, width=8.0, depth=4.0, height=1.0):
    item = {
        "center_x": center_x, "center_z": center_z, "width": width, "depth": depth, "height": height,
        "base_height": 0.0, "name": "Stage", "kind": "stage", "suggested": True,
    }
    if heading is not None:
        item["heading_deg"] = heading
    return item


def box_shell(the_stage, width=20.0, depth=16.0, height=5.0):
    return {
        "source": "scan", "suggested": True,
        "room": {"width": width, "depth": depth, "height": height},
        "risers": [the_stage], "truss_lines": [], "truss_rings": [], "hanging_bands": [],
    }


def l_shell(the_stage):
    """The 12 by 10 L-shaped room of the other tests: its notch is x > 2 with z > 1."""
    shell = box_shell(the_stage, width=12.0, depth=10.0)
    shell["room"]["outline"] = [{"x": x, "z": z} for x, z in L_ROOM]
    return shell


def swung(x, z, about, degrees):
    """A point turned about another, clockwise seen from above (+X towards +Z): worked out here, not by the code under test."""
    radians = math.radians(degrees)
    off_x, off_z = x - about[0], z - about[1]
    return (
        about[0] + off_x * math.cos(radians) - off_z * math.sin(radians),
        about[1] + off_x * math.sin(radians) + off_z * math.cos(radians),
    )


def places(fixtures):
    return [(f.position_x, f.position_y, f.position_z) for f in fixtures]


def back_row():
    """Five pars drawn across the room, upstage of the stage's middle and off to stage left of it."""
    return [fixture(i, -1.0 + i, 0.2, -3.9) for i in range(5)]


class TestARowOnATurnedStage:

    @pytest.mark.parametrize("heading", HEADINGS)
    def test_it_goes_where_the_square_rule_puts_it_swung_about_the_stages_middle(self, heading):
        square, turned = back_row(), back_row()
        square_moves, _ = suggest_positions(square, box_shell(stage()))
        apply(square, square_moves)
        # The square rule did something worth turning: lifted the row, and brought it in from the edge.
        assert places(square) == [(-1.0 + i, 1.2, -3.7) for i in range(5)]

        moves, notes = suggest_positions(turned, box_shell(stage(heading)))

        assert [m.rig_fixture_id for m in moves] == [0, 1, 2, 3, 4]
        assert notes == []
        for move, (x, y, z) in zip(moves, places(square)):
            want_x, want_z = swung(x, z, (0.0, -2.0), heading)
            assert move.to_position == pytest.approx((want_x, y, want_z), abs=0.002)
            assert move.turn_deg == heading
            assert move.to_dict()["turn_deg"] == heading
            assert f"turned {heading:g} degrees" in move.reason and "stage" in move.reason

    @pytest.mark.parametrize("heading", HEADINGS)
    def test_the_row_is_parallel_to_the_turned_edges_and_keeps_its_spacing(self, heading):
        row = back_row()
        the_stage = stage(heading)
        moves, _ = suggest_positions(row, box_shell(the_stage))
        apply(row, moves)

        along = (math.cos(math.radians(heading)), math.sin(math.radians(heading)))
        for a, b in zip(row, row[1:]):
            step = (b.position_x - a.position_x, b.position_z - a.position_z)
            # A metre apart still, and each step along the stage's width.
            assert math.hypot(*step) == pytest.approx(1.0, abs=0.003)
            assert step[0] * along[0] + step[1] * along[1] == pytest.approx(1.0, abs=0.003)
        # On the deck, and in from every turned edge.
        for f in row:
            across, back = _across_and_back(the_stage, f.position_x, f.position_z)
            assert abs(across) <= 4.0 - STAGE_EDGE_CLEARANCE + 0.002
            assert abs(back) <= 2.0 - STAGE_EDGE_CLEARANCE + 0.002
            assert f.position_y == pytest.approx(1.2)
        # As far to stage left of the stage's middle, along its width, as it was drawn.
        mean_across = sum(_across_and_back(the_stage, f.position_x, f.position_z)[0] for f in row) / 5
        assert mean_across == pytest.approx(1.0, abs=0.003)

    @pytest.mark.parametrize("heading", HEADINGS)
    def test_each_fixture_is_turned_with_the_stage(self, heading):
        row = back_row()
        row[2].rotation_y = 170.0
        row[3].rotation_y = None
        moves, _ = suggest_positions(row, box_shell(stage(heading)))
        apply(row, moves)
        # rotation_y runs the other way round from a heading, so the turn comes off it.
        assert row[0].rotation_y == pytest.approx(-heading)
        assert row[3].rotation_y == pytest.approx(-heading)
        wrapped = 170.0 - heading
        assert row[2].rotation_y == pytest.approx(wrapped - 360.0 if wrapped > 180.0 else wrapped)

    @pytest.mark.parametrize("heading", HEADINGS)
    def test_a_row_drawn_at_the_front_ends_at_the_turned_front(self, heading):
        # Downstage of the stage's front edge at z = 0 it would not be the stage's: this one is just behind it.
        row = [fixture(i, -2.0 + i, 0.2, -0.1) for i in range(5)]
        the_stage = stage(heading)
        moves, _ = suggest_positions(row, box_shell(the_stage))
        apply(row, moves)
        for f in row:
            back = _across_and_back(the_stage, f.position_x, f.position_z)[1]
            assert back == pytest.approx(2.0 - STAGE_EDGE_CLEARANCE, abs=0.003)
        # The front of a stage turned clockwise is downstage swung clockwise: towards stage right.
        front = swung(0.0, 1.0, (0.0, 0.0), heading)
        middle = row[2]
        assert (middle.position_x - 0.0) * front[0] + (middle.position_z + 2.0) * front[1] == pytest.approx(1.7, abs=0.003)

    @pytest.mark.parametrize("heading", HEADINGS)
    @pytest.mark.parametrize("count", [1, 5])
    def test_the_same_scan_again_moves_nothing(self, heading, count):
        row = back_row()[:count]
        shell = box_shell(stage(heading))
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == count
        apply(row, moves)
        before, facing = places(row), [f.rotation_y for f in row]

        assert suggest_positions(row, shell)[0] == []
        assert places(row) == before and [f.rotation_y for f in row] == facing

    def test_a_row_a_scan_has_moved_is_fitted_and_never_swung_again(self):
        # Laid on a stage at 30 degrees, which the next scan finds three metres further upstage.
        row = back_row()
        apply(row, suggest_positions(row, box_shell(stage(30.0)))[0])
        facing = [f.rotation_y for f in row]
        moved_stage = stage(30.0, center_z=-5.0)

        moves, _ = suggest_positions(row, box_shell(moved_stage))

        assert moves and all(m.turn_deg == 0.0 and "turn_deg" not in m.to_dict() for m in moves)
        apply(row, moves)
        assert [f.rotation_y for f in row] == facing
        for f in row:
            across, back = _across_and_back(moved_stage, f.position_x, f.position_z)
            assert abs(across) <= 4.0 - STAGE_EDGE_CLEARANCE + 0.006
            assert abs(back) <= 2.0 - STAGE_EDGE_CLEARANCE + 0.006

    def test_a_row_that_is_not_the_stages_is_left_to_the_old_rule(self):
        # Downstage of the turned stage's front, out on the floor: nothing to do with it.
        row = [fixture(i, -2.0 + i, 0.2, 5.0) for i in range(5)]
        assert suggest_positions(row, box_shell(stage(30.0)))[0] == []
        # Overhead rows never read the stage, turned or not.
        high = [fixture(i, -2.0 + i, 4.0, -3.0, group="Truss") for i in range(5)]
        assert suggest_positions(high, box_shell(stage(30.0))) == suggest_positions(high, box_shell(stage()))

    def test_settled_positions_never_move(self):
        tapped = [fixture(i, -1.0 + i, 0.2, -3.9, tags=["position_source:tap"]) for i in range(3)]
        assert suggest_positions(tapped, box_shell(stage(30.0)))[0] == []

    def test_a_row_wider_than_the_turned_stage_is_left_overhanging_with_a_note(self):
        row = [fixture(i, -5.0 + i, 0.2, -2.0) for i in range(11)]
        moves, notes = suggest_positions(row, box_shell(stage(30.0)))
        assert len(moves) == 11
        assert any("wider than the stage" in note for note in notes)


class TestAStageThatStandsSquare:
    """Heading 0, or none, is the rule there always was."""

    @pytest.mark.parametrize("heading", [None, 0, 0.0, 180, -180.0, 360, "30", True, 1000.0, float("nan")])
    def test_it_moves_fixtures_exactly_as_a_stage_with_no_heading_does(self, heading):
        rows = lambda: back_row() + [fixture(10 + i, -6.0 + i, 0.2, -1.0, group="Wide") for i in range(13)]
        plain_moves, plain_notes = suggest_positions(rows(), box_shell(stage()))
        the_stage = stage()
        the_stage["heading_deg"] = heading
        moves, notes = suggest_positions(rows(), box_shell(the_stage))

        assert moves == plain_moves and notes == plain_notes
        assert [m.to_dict() for m in moves] == [m.to_dict() for m in plain_moves]
        assert all(m.turn_deg == 0.0 and "turn_deg" not in m.to_dict() for m in moves)

    def test_what_the_old_rule_gives_is_pinned(self):
        moves, notes = suggest_positions(back_row(), box_shell(stage()))
        assert notes == []
        assert [m.to_dict() for m in moves] == [
            {
                "rig_fixture_id": i, "name": f"Par {i}", "group": "Floor Pars",
                "from": {"x": -1.0 + i, "y": 0.2, "z": -3.9},
                "to": {"x": -1.0 + i, "y": 1.2, "z": -3.7},
                "reason": "Moved onto the stage (1.00 m up).",
                "suggested": True,
            }
            for i in range(5)
        ]

    def test_a_stage_with_a_number_missing_is_not_turned(self):
        broken = stage(30.0)
        broken["heading_deg"] = 30.0
        del broken["base_height"]
        # No base height is a stage on the floor, and is still turned.
        assert all(m.turn_deg == 30.0 for m in suggest_positions(back_row(), box_shell(broken))[0])


def inside_box(shell, fixtures, slack=0.002):
    half_w, half_d = shell["room"]["width"] / 2.0, shell["room"]["depth"] / 2.0
    return all(
        abs(f.position_x) <= half_w - WALL_CLEARANCE + slack and abs(f.position_z) <= half_d - WALL_CLEARANCE + slack
        for f in fixtures
    )


def inside_outline(shell, fixtures, clear=0.19):
    outline = np.array([(p["x"], p["z"]) for p in shell["room"]["outline"]])
    x = np.array([f.position_x for f in fixtures], dtype=float)
    z = np.array([f.position_z for f in fixtures], dtype=float)
    return bool(clear_of_outline(x, z, outline, clear).all())


# Every heading a raised area can store, five degrees apart, and none that is square.
EVERY_HEADING = [float(h) for h in range(-85, 91, 5) if h != 0]


class TestNothingIsLeftOutsideTheRoom:

    @pytest.mark.parametrize("center", [(0.0, -2.0), (-7.5, -6.0), (8.0, -6.5), (9.0, 6.0), (0.0, 7.0)])
    def test_in_a_box_room_whatever_the_heading_and_wherever_the_stage_stands(self, center):
        for heading in EVERY_HEADING:
            for count in (1, 4, 7):
                the_stage = stage(heading, center_x=center[0], center_z=center[1])
                shell = box_shell(the_stage)
                row = [fixture(i, center[0] - 3.0 + i, 0.2, center[1] - 1.0) for i in range(count)]
                moves, _ = suggest_positions(row, shell)
                apply(row, moves)
                assert inside_box(shell, row), (heading, count, places(row))
                assert all(0.0 <= f.position_y <= 5.0 - CEILING_DROP for f in row)
                # And it is settled: the same scan again moves nothing.
                assert suggest_positions(row, shell)[0] == [], (heading, count)

    @pytest.mark.parametrize("center", [(-2.0, -3.0), (3.5, -1.0), (1.0, 2.0), (-4.0, 3.5), (5.0, -4.0)])
    def test_in_an_l_shaped_room_whatever_the_heading_and_wherever_the_stage_stands(self, center):
        for heading in EVERY_HEADING:
            for count in (1, 4, 7):
                the_stage = stage(heading, center_x=center[0], center_z=center[1], width=6.0, depth=3.0)
                shell = l_shell(the_stage)
                row = [fixture(i, center[0] - 2.4 + 0.8 * i, 0.2, center[1] - 0.5) for i in range(count)]
                moves, _ = suggest_positions(row, shell)
                apply(row, moves)
                # Inside the walls. (Only a row that had to be brought inside is also
                # put 0.2 m clear of them: the rule for a stage standing square.)
                assert inside_outline(shell, row, clear=0.0), (heading, count, places(row))
                assert inside_box(shell, row), (heading, count, places(row))
                assert suggest_positions(row, shell)[0] == [], (heading, count)

    def test_a_row_swung_into_the_notch_of_an_l_comes_inside_as_one_piece(self):
        # A stage beside the notch (x > 2, z > 1), turned so that its stage-left end is in it.
        the_stage = stage(60.0, center_x=1.0, center_z=0.5, width=6.0, depth=2.0)
        shell = l_shell(the_stage)
        row = [fixture(i, 1.0 + i, 0.2, 0.5) for i in range(5)]
        # Fitted to the stage (its last fixture 0.3 m in from the stage-left end) and swung, and
        # nothing more, the row's stage-left end would stand in the notch, outside the walls.
        swung_only = [swung(1.0 - 1.3 + i, 0.5, (1.0, 0.5), 60.0) for i in range(5)]
        assert sum(1 for x, z in swung_only if x > 2.0 and z > 1.0) >= 1

        moves, notes = suggest_positions(row, shell)

        assert len(moves) == 5 and notes == []
        assert all("inside the walls" in m.reason for m in moves)
        apply(row, moves)
        assert inside_outline(shell, row)
        # Still one straight row a metre apart, at the stage's heading.
        for a, b in zip(row, row[1:]):
            step = (b.position_x - a.position_x, b.position_z - a.position_z)
            assert step == pytest.approx((math.cos(math.radians(60.0)), math.sin(math.radians(60.0))), abs=0.003)

    def test_a_row_too_long_for_the_room_is_brought_inside_a_fixture_at_a_time(self):
        the_stage = stage(45.0, center_x=0.0, center_z=0.0, width=40.0, depth=4.0)
        shell = box_shell(the_stage, width=6.0, depth=6.0)
        row = [fixture(i, -9.0 + i, 0.2, 0.0) for i in range(19)]
        moves, notes = suggest_positions(row, shell)
        apply(row, moves)
        assert inside_box(shell, row)
        assert any("longer than the room" in note for note in notes)

    def test_a_row_is_never_lifted_into_the_drop_under_the_ceiling(self):
        # A stage whose top is 2.9 m up in a room 3 m high: a par 0.2 m tall cannot stand on it.
        the_stage = stage(30.0, height=2.9)
        shell = box_shell(the_stage, height=3.0)
        row = back_row()
        moves, _ = suggest_positions(row, shell)
        apply(row, moves)
        assert all(f.position_y == pytest.approx(3.0 - CEILING_DROP) for f in row)
        assert all("under the 3.00 m ceiling" in m.reason for m in moves)
        assert suggest_positions(row, shell)[0] == []


class TestUndoingTheScanTurnsThemBack:

    def test_an_undo_puts_back_where_each_stood_and_the_way_it_faced(self):
        row = back_row()
        row[1].rotation_y = 45.0
        row[2].rotation_y = None
        before, facing, tags = places(row), [f.rotation_y for f in row], [list(f.tags) for f in row]
        record = apply(row, suggest_positions(row, box_shell(stage(30.0)))[0])
        assert [f.rotation_y for f in row] == [-30.0, 15.0, -30.0, -30.0, -30.0]

        plan = plan_undo(row, record)
        assert len(plan.restores) == 5 and plan.skipped == []
        restore(plan)

        assert places(row) == before
        assert [f.rotation_y for f in row] == facing
        assert [f.tags for f in row] == tags

    def test_a_fixture_somebody_has_turned_since_keeps_the_way_it_faces(self):
        row = back_row()
        record = apply(row, suggest_positions(row, box_shell(stage(30.0)))[0])
        row[0].rotation_y = 90.0
        restore(plan_undo(row, record))
        assert row[0].rotation_y == 90.0
        assert row[1].rotation_y == 0.0
        assert (row[0].position_x, row[0].position_y, row[0].position_z) == (-1.0, 0.2, -3.9)

    def test_a_second_scan_over_the_first_still_turns_them_all_the_way_back(self):
        row = back_row()
        record = apply(row, suggest_positions(row, box_shell(stage(30.0)))[0])
        again = suggest_positions(row, box_shell(stage(30.0, center_z=-5.0)))[0]
        assert again
        record = apply(row, again, record=record)
        restore(plan_undo(row, record))
        assert places(row) == [(-1.0 + i, 0.2, -3.9) for i in range(5)]
        assert [f.rotation_y for f in row] == [0.0] * 5

    def test_a_move_that_turned_nothing_keeps_the_record_it_always_had(self):
        row = back_row()
        record = apply(row, suggest_positions(row, box_shell(stage()))[0])
        assert all(set(entry) == {"rig_fixture_id", "name", "from", "to", "tags_before"} for entry in record["moves"])
        row[0].rotation_y = 12.0
        restore(plan_undo(row, record))
        assert row[0].rotation_y == 12.0
