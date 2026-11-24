"""
Room scan: a stage that stands turned from the room's walls (slice 27).

No scan format names a stage or gives one a yaw: a raised area is a level
patch found in the scan's points. What is checked, on rooms built in code:

  * a stage built at 30 or at -20 degrees comes back with that heading, its
    own middle and its own two sides, and corners where they were built;
  * a quarter turn of the room turns it with the room, and its heading is
    still within 45 degrees of square, so its depth still runs downstage;
  * a stage built square, one turned a degree or two, a round riser, an
    L-shaped stage and a corner piece are measured along the room's axes as
    they always were, with no heading;
  * a point cloud of the same room gives the same heading;
  * a scan's own suggestion then lays a floor row on the turned stage, turned.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.room_scan import ScanOptions, extract_room, read_scan_file, suggest_positions
from app.services.room_scan.carry import _across_and_back
from app.services.room_scan.edit import area_corners
from app.services.room_scan.extract import _turn_box, _turned_box, quarter_turn
from tests.unit.room_scan_meshes import (
    BIG_ROOM, as_scanned, box, merge, prism, sample_surface, turned_box, write_obj, write_ply,
)

GUESS = ["position_source:template", "position_unconfirmed"]
# The stage: its middle, its two sides and its top.
CENTRE = (1.0, -3.0)
WIDTH, DEPTH, TOP = 6.0, 3.0, 0.9


def room_with(parts):
    half_w, half_d = BIG_ROOM["width"] / 2.0, BIG_ROOM["depth"] / 2.0
    return merge([box(-half_w, half_w, 0.0, BIG_ROOM["height"], -half_d, half_d), *parts])


def turned_stage_mesh(heading):
    return room_with([turned_box(CENTRE[0], CENTRE[1], WIDTH, DEPTH, 0.0, TOP, heading)])


def scan(vertices, faces, **options):
    return extract_room(read_scan_file("room.obj", write_obj(vertices, faces)), ScanOptions(**options))


def stage_of(shell):
    return next(r for r in shell["risers"] if r["kind"] == "stage")


def built_corners(heading, centre=CENTRE):
    radians = math.radians(heading)
    cos, sin = math.cos(radians), math.sin(radians)
    return [
        (centre[0] + u * cos - v * sin, centre[1] + u * sin + v * cos)
        for u, v in ((-3.0, -1.5), (3.0, -1.5), (3.0, 1.5), (-3.0, 1.5))
    ]


def same_corners(found, built, tolerance=0.15):
    """Whether two sets of four corners are the same four places, in whatever order."""
    return all(min(math.hypot(fx - bx, fz - bz) for bx, bz in built) <= tolerance for fx, fz in found) and all(
        min(math.hypot(fx - bx, fz - bz) for fx, fz in found) <= tolerance for bx, bz in built
    )


class TestAStageTurnedFromTheWalls:

    @pytest.mark.parametrize("heading", [30.0, -20.0, 10.0, 44.0])
    def test_it_comes_back_at_its_heading_with_its_own_sides(self, heading):
        found = scan(*turned_stage_mesh(heading))
        stage = stage_of(found.shell)

        assert stage["heading_deg"] == pytest.approx(heading, abs=1.0)
        assert stage["width"] == pytest.approx(WIDTH, abs=0.15)
        assert stage["depth"] == pytest.approx(DEPTH, abs=0.15)
        assert (stage["center_x"], stage["center_z"]) == pytest.approx(CENTRE, abs=0.1)
        assert stage["height"] == pytest.approx(TOP, abs=0.05)
        assert same_corners(area_corners(stage), built_corners(heading))
        assert "standing turned" in stage["basis"]
        assert any("stands turned" in line and "Heading to 0" in line for line in found.assumptions)

    @pytest.mark.parametrize("heading", [45.0, -45.0])
    def test_a_stage_across_a_corner_is_found_turned_whichever_way_its_sides_are_told(self, heading):
        # At 45 degrees it is as much 6 by 3 at 45 as 3 by 6 at -45: the corners say which rectangle it is.
        stage = stage_of(scan(*turned_stage_mesh(heading)).shell)
        assert abs(stage["heading_deg"]) == pytest.approx(45.0, abs=1.0)
        assert -45.0 < stage["heading_deg"] <= 45.0
        assert sorted((stage["width"], stage["depth"])) == pytest.approx([DEPTH, WIDTH], abs=0.15)
        assert same_corners(area_corners(stage), built_corners(heading))

    def test_the_scan_is_read_the_same_whichever_way_the_phone_held_it(self):
        vertices, faces = turned_stage_mesh(30.0)
        moved = as_scanned(vertices, yaw_deg=90.0, offset=(3.0, 0.5, -2.0))
        stage = stage_of(scan(moved, faces).shell)
        assert abs(stage["heading_deg"]) == pytest.approx(30.0, abs=1.0)
        assert sorted((stage["width"], stage["depth"])) == pytest.approx([DEPTH, WIDTH], abs=0.15)

    @pytest.mark.parametrize("rotate", [90, 180, 270])
    def test_a_turn_of_the_room_turns_it_with_the_room(self, rotate):
        vertices, faces = turned_stage_mesh(30.0)
        plain, turned = stage_of(scan(vertices, faces).shell), stage_of(scan(vertices, faces, rotate=rotate).shell)

        want = [quarter_turn(x, z, rotate // 90) for x, z in area_corners(plain)]
        assert same_corners(area_corners(turned), want, tolerance=0.05)
        # Still within 45 degrees of square, so its depth still runs to the edge nearest downstage.
        assert -45.0 < turned["heading_deg"] <= 45.0
        if rotate == 180:
            assert turned["heading_deg"] == plain["heading_deg"]
            assert (turned["width"], turned["depth"]) == (plain["width"], plain["depth"])
        else:
            # 30 and a quarter turn is 120, which is the same rectangle as 30 with its sides changed places.
            assert turned["heading_deg"] == plain["heading_deg"]
            assert (turned["width"], turned["depth"]) == (plain["depth"], plain["width"])

    def test_a_point_cloud_gives_the_same_heading(self):
        vertices, faces = turned_stage_mesh(30.0)
        cloud = sample_surface(vertices, faces, 400_000)
        found = extract_room(read_scan_file("room.ply", write_ply(cloud)), ScanOptions())
        stage = stage_of(found.shell)
        assert stage["heading_deg"] == pytest.approx(30.0, abs=2.0)
        assert same_corners(area_corners(stage), built_corners(30.0), tolerance=0.3)


class TestWhatIsStillMeasuredAlongTheRoom:

    @pytest.mark.parametrize("heading", [0.0, 1.0, -2.0, 3.0])
    def test_a_stage_square_or_nearly_square_has_no_heading(self, heading):
        stage = stage_of(scan(*turned_stage_mesh(heading)).shell)
        assert "heading_deg" not in stage
        assert "turned" not in stage["basis"]

    def test_a_stage_built_square_is_the_shell_it_always_was(self):
        square = scan(*room_with([box(-2.0, 4.0, 0.0, TOP, -4.5, -1.5)]))
        stage = stage_of(square.shell)
        assert set(stage) == {
            "center_x", "center_z", "width", "depth", "height", "base_height", "name", "kind", "suggested", "basis",
        }
        assert (stage["center_x"], stage["center_z"], stage["width"], stage["depth"]) == pytest.approx(
            (1.0, -3.0, 6.0, 3.0), abs=0.1
        )
        assert not any("stands turned" in line for line in square.assumptions)

    def test_an_l_shaped_stage_and_a_corner_piece_have_no_heading(self):
        l_stage = prism(
            [(-3.0, -5.0), (3.0, -5.0), (3.0, -1.0), (0.0, -1.0), (0.0, -3.0), (-3.0, -3.0)], 0.0, TOP,
            [[(-3.0, -5.0), (3.0, -5.0), (3.0, -3.0), (-3.0, -3.0)], [(0.0, -3.0), (3.0, -3.0), (3.0, -1.0), (0.0, -1.0)]],
        )
        corner = prism([(-2.0, -5.0), (3.0, -5.0), (-2.0, 0.0)], 0.0, TOP)
        for part in (l_stage, corner):
            found = scan(*room_with([part]))
            assert found.shell["risers"], "the raised area was found"
            assert all("heading_deg" not in riser for riser in found.shell["risers"])

    def test_the_gates_on_a_patch_of_points(self):
        rng = np.random.default_rng(3)

        def patch(heading, count=6000):
            u, v = rng.uniform(-3.0, 3.0, count), rng.uniform(-1.5, 1.5, count)
            radians = math.radians(heading)
            return u * math.cos(radians) - v * math.sin(radians), u * math.sin(radians) + v * math.cos(radians)

        found = _turned_box(*patch(25.0), area=18.0)
        assert found["heading"] == pytest.approx(25.0, abs=0.5)
        assert (found["width"], found["depth"]) == pytest.approx((6.0, 3.0), abs=0.05)
        # Too little turned, too few points, and a patch that does not fill its own box.
        assert _turned_box(*patch(4.0), area=18.0) is None
        assert _turned_box(*patch(25.0, count=30), area=18.0) is None
        assert _turned_box(*patch(25.0), area=9.0) is None
        # A round riser is as small a box at every heading.
        angle, reach = rng.uniform(0.0, 2.0 * math.pi, 6000), 2.0 * np.sqrt(rng.uniform(0.0, 1.0, 6000))
        assert _turned_box(reach * np.cos(angle), reach * np.sin(angle), area=12.5) is None

    def test_a_turned_box_is_the_same_rectangle_after_each_quarter_turn(self):
        own = {"center_x": 1.0, "center_z": -3.0, "width": 6.0, "depth": 3.0, "heading": 30.0}
        once = _turn_box(own, 1)
        assert (once["center_x"], once["center_z"]) == (3.0, 1.0)
        assert (once["width"], once["depth"], once["heading"]) == (3.0, 6.0, pytest.approx(30.0))
        assert _turn_box(own, 2)["heading"] == pytest.approx(30.0)
        assert _turn_box(own, 2)["width"] == 6.0
        assert _turn_box(_turn_box(_turn_box(_turn_box(own, 1), 1), 1), 1) == pytest.approx(own)
        other = _turn_box({**own, "heading": -30.0}, 1)
        assert (other["width"], other["depth"], other["heading"]) == (3.0, 6.0, pytest.approx(-30.0))


class TestTheScansOwnSuggestion:

    def test_a_floor_row_is_laid_on_the_turned_stage_the_scan_found(self):
        shell = scan(*turned_stage_mesh(30.0)).shell
        stage = stage_of(shell)
        row = [
            SimpleNamespace(
                id=i, name=f"Par {i}", group_name="Floor Pars", position_x=-1.0 + i, position_y=0.2,
                position_z=-3.5, rotation_y=0.0, tags=list(GUESS), universe=0, dmx_address=i * 10 + 1,
            )
            for i in range(5)
        ]

        moves, notes = suggest_positions(row, shell)

        assert len(moves) == 5 and notes == []
        assert all(move.turn_deg == stage["heading_deg"] for move in moves)
        heading = math.radians(stage["heading_deg"])
        for a, b in zip(moves, moves[1:]):
            step = (b.to_position[0] - a.to_position[0], b.to_position[2] - a.to_position[2])
            assert step == pytest.approx((math.cos(heading), math.sin(heading)), abs=0.003)
        for move in moves:
            across, back = _across_and_back(stage, move.to_position[0], move.to_position[2])
            assert abs(across) <= stage["width"] / 2.0 - 0.29 and abs(back) <= stage["depth"] / 2.0 - 0.29
            assert move.to_position[1] == pytest.approx(0.2 + stage["height"])
