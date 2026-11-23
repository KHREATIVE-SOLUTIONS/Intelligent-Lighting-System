"""
Room scan: rooms that are not boxes, truss at an angle, and rings of truss.

Every scan is built in code (room_scan_meshes.py). What is checked:

  * an L-shaped room and a room with a corner cut off come back as their floor
    outline, and a box room still comes back as a box with no outline;
  * a truss 30 degrees off the room's axes comes back as a line at 30 degrees,
    and a truss square to the room exactly as it always did;
  * a ring of truss 4 m in radius comes back as a ring, and a square frame of
    truss does not;
  * unconfirmed template guesses are laid along an angled line or round a ring,
    evenly, in address order, and nothing else is ever moved;
  * a shell stored before any of this still moves fixtures as it did;
  * in a room with a floor outline a suggested row ends inside the outline,
    not only inside its box, as one piece where it fits; a box room, and an
    outline that is not one, move a row exactly as before.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.room_scan import ScanOptions, extract_room, read_scan_file, suggest_positions
from app.services.room_scan.extract import clear_of_outline, inside_outline, outline_area
from tests.unit.room_scan_meshes import (
    ANGLED_TRUSS, BIG_ROOM, CUT_ROOM, L_ROOM, RING, ROOM, TRUSS,
    as_scanned, big_room_mesh, box, merge, room_mesh, sample_surface, shaped_room_mesh,
    write_obj, write_ply,
)


def scan(vertices, faces, name="room.obj", **options):
    return extract_room(read_scan_file(name, write_obj(vertices, faces)), ScanOptions(**options))


def corners(shell):
    return [(p["x"], p["z"]) for p in shell["room"]["outline"]]


def assert_corners(found, expected, tolerance=0.1):
    assert len(found) == len(expected)
    for (fx, fz), (ex, ez) in zip(found, expected):
        assert fx == pytest.approx(ex, abs=tolerance)
        assert fz == pytest.approx(ez, abs=tolerance)


# ---------------------------------------------------------------------------
# The floor outline
# ---------------------------------------------------------------------------

class TestFloorOutline:

    @pytest.mark.parametrize("label, yaw, up, units_per_metre", [
        ("as built", 0.0, "y", 1.0),
        ("turned 25 degrees, Z-up, centimetres", 25.0, "z", 100.0),
        ("turned 100 degrees", 100.0, "y", 1.0),
    ])
    def test_an_l_shaped_room_comes_back_as_its_six_walls(self, label, yaw, up, units_per_metre):
        vertices, faces = shaped_room_mesh()
        placed = as_scanned(vertices, yaw, offset=(3.0, 1.0, -2.0), up=up, units_per_metre=units_per_metre)

        found = scan(placed, faces)
        room = found.shell["room"]

        # In order, clockwise seen from above, from the corner furthest upstage and stage right.
        assert_corners(corners(found.shell), L_ROOM)
        assert outline_area(np.array(corners(found.shell))) > 0
        # The box round the outline is still the room's size, as every reader of it expects.
        assert room["width"] == pytest.approx(12.0, abs=0.1), label
        assert room["depth"] == pytest.approx(10.0, abs=0.1), label
        assert room["suggested"] is True and "outline" in room["basis"]
        assert any("not a box" in line and "6 walls" in line for line in found.assumptions)
        assert found.warnings == []

    def test_a_wall_at_an_angle_is_one_straight_wall(self):
        vertices, faces = shaped_room_mesh(CUT_ROOM, None)
        found = scan(as_scanned(vertices, 100.0, offset=(3.0, 1.0, -2.0)), faces)
        assert_corners(corners(found.shell), CUT_ROOM)

    def test_a_box_room_has_no_outline_and_the_shell_it_always_had(self):
        vertices, faces = room_mesh()
        shell = scan(as_scanned(vertices, 25.0, up="z"), faces).shell
        assert "outline" not in shell["room"]
        assert set(shell["room"]) == {"width", "depth", "height", "suggested", "basis"}
        assert shell["truss_rings"] == []
        line = shell["truss_lines"][0]
        assert (line["axis"], line["heading_deg"]) == ("x", 0.0)
        assert line["z1"] == line["z2"]

    def test_the_inner_walls_of_an_l_are_not_taken_for_truss(self):
        vertices, faces = shaped_room_mesh()
        shell = scan(vertices, faces).shell
        assert shell["truss_lines"] == [] and shell["truss_rings"] == []
        assert shell["scan"]["other_overhead_objects"] == 0

    def test_a_truss_in_an_l_shaped_room_is_still_found(self):
        vertices, faces = shaped_room_mesh(truss=True)
        shell = scan(vertices, faces).shell
        assert len(shell["truss_lines"]) == 1
        line = shell["truss_lines"][0]
        assert line["axis"] == "x"
        assert (line["x1"], line["x2"]) == pytest.approx((-4.0, 0.0), abs=0.2)
        assert line["z1"] == pytest.approx(-0.5, abs=0.1)

    def test_a_point_cloud_of_an_l_shaped_room_gives_the_same_outline(self):
        vertices, faces = shaped_room_mesh()
        cloud = sample_surface(as_scanned(vertices, 25.0, up="z"), faces, 200_000)
        found = extract_room(read_scan_file("cloud.ply", write_ply(cloud)), ScanOptions())
        assert_corners(corners(found.shell), L_ROOM, tolerance=0.2)

    def test_a_quarter_turn_turns_the_outline_with_the_room(self):
        vertices, faces = shaped_room_mesh()
        turned = scan(vertices, faces, rotate=90).shell
        assert turned["room"]["width"] == pytest.approx(10.0, abs=0.1)
        assert turned["room"]["depth"] == pytest.approx(12.0, abs=0.1)
        # Clockwise seen from above: (x, z) goes to (-z, x). Still clockwise, never mirrored.
        expected = {(-z, x) for x, z in L_ROOM}
        assert {(round(x), round(z)) for x, z in corners(turned)} == expected
        assert outline_area(np.array(corners(turned))) > 0

    def test_a_scan_that_stops_short_is_drawn_as_a_box_and_says_so(self):
        # A box room whose scan never reached one corner: floor and ceiling
        # stop on a diagonal with no wall there. Not a room with a cut corner.
        half_w, half_d, height = 6.0, 5.0, 5.0
        walls = [
            box(-half_w, half_w, 0.0, height, -half_d, -half_d),      # upstage
            box(-half_w, -half_w, 0.0, height, -half_d, half_d),      # stage right
            box(half_w, half_w, 0.0, height, -half_d, -1.0),          # stage left, part of the way
            box(-half_w, 0.0, 0.0, height, half_d, half_d),           # downstage, part of the way
        ]
        cut = [(-half_w, -half_d), (half_w, -half_d), (half_w, -1.0), (0.0, half_d), (-half_w, half_d)]
        flats = []
        for y in (0.0, height):
            flats.append((
                np.array([(x, y, z) for x, z in cut], dtype=np.float64),
                np.array([(0, k, k + 1) for k in range(1, len(cut) - 1)], dtype=np.int64),
            ))
        vertices, faces = merge(walls + flats)

        found = scan(vertices, faces)

        assert "outline" not in found.shell["room"]
        assert found.shell["room"]["width"] == pytest.approx(12.0, abs=0.15)
        assert any("drawn as a box" in line for line in found.warnings)

    def test_inside_and_clear_of_an_outline(self):
        outline = np.array(L_ROOM)
        x = np.array([0.0, 4.0, 4.0, 1.9, -5.9])
        z = np.array([0.0, 0.0, 3.0, 3.0, 4.9])
        assert inside_outline(x, z, outline).tolist() == [True, True, False, True, True]
        # Within 0.3 m of the inner wall at x = 2, and of the corner at (-6, 5): not clear.
        assert clear_of_outline(x, z, outline, 0.3).tolist() == [True, True, False, False, False]


# ---------------------------------------------------------------------------
# Truss at an angle, and rings
# ---------------------------------------------------------------------------

class TestOverheadShapes:

    @pytest.mark.parametrize("yaw, up", [(0.0, "y"), (25.0, "z"), (250.0, "y")])
    def test_a_truss_at_30_degrees_is_a_line_at_30_degrees(self, yaw, up):
        vertices, faces = big_room_mesh(with_angled_truss=True)
        shell = scan(as_scanned(vertices, yaw, offset=(2.0, 0.5, -1.0), up=up), faces).shell

        assert shell["truss_rings"] == []
        assert len(shell["truss_lines"]) == 1
        line = shell["truss_lines"][0]
        t = ANGLED_TRUSS
        reach_x = t["length"] / 2.0 * math.cos(math.radians(t["heading_deg"]))
        reach_z = t["length"] / 2.0 * math.sin(math.radians(t["heading_deg"]))
        assert line["axis"] == "angled"
        assert line["heading_deg"] == pytest.approx(30.0, abs=1.0)
        # Written from stage right to stage left. A mirrored room would run it the other way in Z.
        assert (line["x1"], line["z1"]) == pytest.approx((t["center_x"] - reach_x, t["center_z"] - reach_z), abs=0.15)
        assert (line["x2"], line["z2"]) == pytest.approx((t["center_x"] + reach_x, t["center_z"] + reach_z), abs=0.15)
        assert line["length"] == pytest.approx(t["length"], abs=0.2)
        assert line["across"] == pytest.approx(t["across"], abs=0.1)
        assert line["height"] == pytest.approx(t["bottom"], abs=0.1)
        assert line["suggested"] is True and "30 degrees" in line["basis"]
        assert shell["room"]["width"] == pytest.approx(BIG_ROOM["width"], abs=0.1)

    @pytest.mark.parametrize("yaw, up", [(0.0, "y"), (25.0, "z")])
    def test_a_ring_of_truss_4_m_in_radius_is_a_ring(self, yaw, up):
        vertices, faces = big_room_mesh(with_ring=True)
        found = scan(as_scanned(vertices, yaw, offset=(2.0, 0.5, -1.0), up=up), faces)
        shell = found.shell

        assert shell["truss_lines"] == []
        assert len(shell["truss_rings"]) == 1
        ring = shell["truss_rings"][0]
        assert ring["name"] == "Overhead ring 1"
        assert ring["radius"] == pytest.approx(RING["radius"], abs=0.1)
        assert ring["center_x"] == pytest.approx(RING["center_x"], abs=0.1)
        assert ring["center_z"] == pytest.approx(RING["center_z"], abs=0.1)
        assert ring["height"] == pytest.approx(RING["bottom"], abs=0.1)
        assert ring["across"] == pytest.approx(RING["across"], abs=0.1)
        assert ring["suggested"] is True and ring["basis"].startswith("scan:")
        assert [(b["lines"], b["rings"]) for b in shell["hanging_bands"]] == [(0, 1)]
        assert shell["scan"]["other_overhead_objects"] == 0
        assert not any("No truss or bar" in line for line in found.assumptions)

    def test_a_ring_and_an_angled_truss_at_two_heights_are_both_found(self):
        vertices, faces = big_room_mesh(with_ring=True, with_angled_truss=True)
        shell = scan(vertices, faces).shell
        assert len(shell["truss_lines"]) == 1 and len(shell["truss_rings"]) == 1
        assert [b["height"] for b in shell["hanging_bands"]] == pytest.approx(
            [ANGLED_TRUSS["bottom"], RING["bottom"]], abs=0.1)

    def test_a_square_frame_of_truss_is_not_a_ring(self):
        vertices, faces = big_room_mesh()
        frame = [
            box(-2.0, 2.0, 4.8, 5.1, -2.15, -1.85), box(-2.0, 2.0, 4.8, 5.1, 1.85, 2.15),
            box(-2.15, -1.85, 4.8, 5.1, -2.0, 2.0), box(1.85, 2.15, 4.8, 5.1, -2.0, 2.0),
        ]
        vertices, faces = merge([(vertices, faces)] + frame)
        assert scan(vertices, faces).shell["truss_rings"] == []

    def test_a_truss_square_to_the_room_is_read_exactly_as_before(self):
        vertices, faces = room_mesh()
        line = scan(vertices, faces).shell["truss_lines"][0]
        assert line == {
            "name": "Overhead line 1",
            "x1": line["x1"], "z1": line["z1"], "x2": line["x2"], "z2": line["z1"],
            "height": line["height"], "top": line["top"], "length": line["length"], "across": line["across"],
            "axis": "x", "heading_deg": 0.0, "suggested": True,
            "basis": "scan: a long thin object hanging clear of the walls; taken for a truss or bar",
        }
        assert sorted((line["x1"], line["x2"])) == pytest.approx([TRUSS["x_min"], TRUSS["x_max"]], abs=0.2)
        assert line["x1"] < line["x2"]


# ---------------------------------------------------------------------------
# Fixture positions on those shapes
# ---------------------------------------------------------------------------

GUESS = ["position_source:template", "position_unconfirmed"]


def fixture(id, name, group, x, y, z, tags=None, address=None, universe=0):
    return SimpleNamespace(
        id=id, name=name, group_name=group, position_x=x, position_y=y, position_z=z,
        tags=list(GUESS if tags is None else tags),
        universe=universe, dmx_address=address if address is not None else id * 10,
    )


def apply(fixtures, moves):
    """What the endpoint does with the moves: the fixtures stand where they were sent."""
    by_id = {f.id: f for f in fixtures}
    for move in moves:
        f = by_id[move.rig_fixture_id]
        f.position_x, f.position_y, f.position_z = move.to_position


@pytest.fixture(scope="module")
def ring_shell():
    vertices, faces = big_room_mesh(with_ring=True)
    return scan(vertices, faces).shell


@pytest.fixture(scope="module")
def angled_shell():
    vertices, faces = big_room_mesh(with_angled_truss=True)
    return scan(vertices, faces).shell


class TestPositionsOnShapes:

    def test_a_row_goes_round_the_ring_evenly_in_address_order(self, ring_shell):
        # Drawn by the template as a straight row through the middle of the ring.
        row = [fixture(i, f"Spot {i}", "Ring Spots", -3.0 + i, 7.0, 1.0) for i in range(8)]
        moves, notes = suggest_positions(row, ring_shell)
        ring = ring_shell["truss_rings"][0]

        assert [m.rig_fixture_id for m in moves] == list(range(8))
        bearings = []
        for move in moves:
            x, y, z = move.to_position
            assert math.hypot(x - ring["center_x"], z - ring["center_z"]) == pytest.approx(ring["radius"], abs=0.01)
            assert y == pytest.approx(ring["height"], abs=0.01)
            assert "Overhead ring 1" in move.reason and "address order" in move.reason
            # Clockwise from upstage, seen from above: 0 is -Z, 90 is +X.
            bearings.append(math.degrees(math.atan2(x - ring["center_x"], -(z - ring["center_z"]))) % 360.0)
        assert bearings == pytest.approx([45.0 * k for k in range(8)], abs=0.5)
        assert notes == []

    def test_address_order_is_universe_then_address_whatever_order_they_are_listed_in(self, ring_shell):
        row = [
            fixture(1, "C", "Ring", 0.0, 7.0, 1.0, address=1, universe=1),
            fixture(2, "B", "Ring", 0.0, 7.0, 1.0, address=200, universe=0),
            fixture(3, "A", "Ring", 0.0, 7.0, 1.0, address=5, universe=0),
            fixture(4, "D", "Ring", 0.0, 7.0, 1.0, address=9, universe=1),
        ]
        moves, _ = suggest_positions(row, ring_shell)
        ring = ring_shell["truss_rings"][0]
        bearing = {
            m.name: round(math.degrees(math.atan2(
                m.to_position[0] - ring["center_x"], -(m.to_position[2] - ring["center_z"]))) % 360.0)
            for m in moves
        }
        assert bearing == {"A": 0, "B": 90, "C": 180, "D": 270}

    def test_a_row_goes_along_the_angled_truss_evenly_and_keeps_its_sense(self, angled_shell):
        line = angled_shell["truss_lines"][0]
        # Addresses running from stage left to stage right, as the template drew them.
        row = [fixture(i, f"Wash {i}", "Angled Wash", 4.0 - 2.0 * i, 7.0, 0.5) for i in range(4)]
        moves, _ = suggest_positions(row, angled_shell)

        assert len(moves) == 4
        run = (line["x2"] - line["x1"], line["z2"] - line["z1"])
        for k, move in enumerate(moves):
            share = 1.0 - (k + 0.5) / 4.0
            x, y, z = move.to_position
            assert x == pytest.approx(line["x1"] + run[0] * share, abs=0.01)
            assert z == pytest.approx(line["z1"] + run[1] * share, abs=0.01)
            assert y == pytest.approx(line["height"], abs=0.01)
            assert "Overhead line 1" in move.reason
        steps = [math.dist(a.to_position, b.to_position) for a, b in zip(moves, moves[1:])]
        assert steps == pytest.approx([line["length"] / 4.0] * 3, abs=0.02)

    @pytest.mark.parametrize("which", ["ring", "angled"])
    @pytest.mark.parametrize("group", ["Rig", ""])
    def test_applying_the_same_scan_again_moves_nothing(self, ring_shell, angled_shell, which, group):
        shell = ring_shell if which == "ring" else angled_shell
        row = [fixture(i, f"Spot {i}", group, -3.0 + i, 7.0, 1.0) for i in range(6)]
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == 6
        apply(row, moves)
        assert suggest_positions(row, shell)[0] == []

    @pytest.mark.parametrize("tags", [
        ["position_source:tap"],
        ["position_source:confirmed"],
        ["position_source:mvr"],
        ["position_source:row_fit", "position_unconfirmed"],
        ["position_source:template"],
        [],
    ])
    @pytest.mark.parametrize("which", ["ring", "angled"])
    def test_a_position_a_person_or_a_file_settled_never_moves(self, ring_shell, angled_shell, which, tags):
        shell = ring_shell if which == "ring" else angled_shell
        row = [fixture(i, f"Spot {i}", "Rig", -3.0 + i, 7.0, 1.0, tags=tags) for i in range(6)]
        assert suggest_positions(row, shell)[0] == []

    def test_guesses_are_laid_round_a_tapped_fixture_which_keeps_its_place_in_the_count(self, ring_shell):
        ring = ring_shell["truss_rings"][0]
        row = [fixture(i, f"Spot {i}", "Ring", -1.0 + i, 7.0, 1.0) for i in range(4)]
        row[1].tags = ["position_source:tap"]
        row[1].position_x, row[1].position_y, row[1].position_z = 4.4, 4.8, 1.3
        moves, _ = suggest_positions(row, ring_shell)

        assert [m.rig_fixture_id for m in moves] == [0, 2, 3]
        assert (row[1].position_x, row[1].position_y, row[1].position_z) == (4.4, 4.8, 1.3)
        bearings = [
            round(math.degrees(math.atan2(
                m.to_position[0] - ring["center_x"], -(m.to_position[2] - ring["center_z"]))) % 360.0)
            for m in moves
        ]
        # Four places round the ring; the tapped fixture's, at 90 degrees, is left for it.
        assert bearings == [0, 180, 270]

    def test_a_row_nearer_a_truss_across_the_room_still_goes_under_it_as_one_piece(self, angled_shell):
        shell = dict(angled_shell)
        across = {"name": "Front bar", "x1": -5.0, "z1": 5.0, "x2": 5.0, "z2": 5.0, "height": 4.0, "axis": "x"}
        shell["truss_lines"] = angled_shell["truss_lines"] + [across]
        row = [fixture(i, f"Par {i}", "Front", -3.0 + 2.0 * i, 6.5, 4.6) for i in range(4)]
        moves, _ = suggest_positions(row, shell)
        assert all("Front bar" in m.reason for m in moves)
        assert [m.to_position[0] for m in moves] == [-3.0, -1.0, 1.0, 3.0]
        assert {m.to_position[2] for m in moves} == {5.0}

    def test_a_floor_row_is_not_sent_up_to_a_ring(self, ring_shell):
        row = [fixture(i, f"Par {i}", "Floor", -1.0 + i, 0.2, 2.0) for i in range(3)]
        assert suggest_positions(row, ring_shell)[0] == []

    def test_a_crowded_ring_is_worth_a_note(self):
        shell = {
            "room": {"width": 10.0, "depth": 10.0, "height": 5.0},
            "truss_rings": [{"name": "Small ring", "center_x": 0.0, "center_z": 0.0, "radius": 0.5, "height": 4.0}],
        }
        row = [fixture(i, f"Pixel {i}", "Pixels", -1.0 + 0.1 * i, 4.5, 0.0) for i in range(20)]
        moves, notes = suggest_positions(row, shell)
        assert len(moves) == 20
        assert any("Small ring" in note and "apart" in note for note in notes)

    def test_a_shell_stored_before_rings_and_headings_moves_fixtures_as_it_did(self):
        # As extract.py wrote it before this slice: no heading, no rings, no outline.
        old = {
            "source": "scan", "suggested": True,
            "room": {"width": ROOM["width"], "depth": ROOM["depth"], "height": ROOM["height"]},
            "risers": [],
            "truss_lines": [
                {"name": "Overhead line 1", "x1": -4.0, "z1": 0.5, "x2": 4.0, "z2": 0.5,
                 "height": 4.0, "top": 4.3, "length": 8.0, "across": 0.3, "axis": "x"},
                {"name": "Overhead line 2", "x1": 5.0, "z1": -3.0, "x2": 5.0, "z2": 3.0,
                 "height": 4.0, "top": 4.3, "length": 6.0, "across": 0.3, "axis": "z"},
            ],
            "hanging_bands": [{"height": 4.0, "top": 4.3, "lines": 2}],
        }
        row = [fixture(i, f"Spot {i}", "Truss", -3.0 + 2.0 * i, 6.0, -2.0) for i in range(4)]
        moves, _ = suggest_positions(row, old)
        assert [m.to_position for m in moves] == [(-3.0 + 2.0 * i, 4.0, 0.5) for i in range(4)]
        assert all("under Overhead line 1" in m.reason for m in moves)

    def test_broken_shapes_in_a_stored_shell_are_passed_over(self):
        shell = {
            "room": {"width": 10.0, "depth": 10.0, "height": 5.0},
            "truss_lines": [{"x1": 0.0, "z1": 0.0, "x2": "?", "z2": 1.0, "height": 4.0}, None],
            "truss_rings": [{"center_x": 0.0, "center_z": 0.0, "radius": 0.0, "height": 4.0}, "ring"],
        }
        row = [fixture(i, f"Spot {i}", "Truss", -1.0 + i, 4.0, 0.0) for i in range(3)]
        assert suggest_positions(row, shell)[0] == []


# ---------------------------------------------------------------------------
# Guesses held inside a floor outline, not only inside the box round it
# ---------------------------------------------------------------------------

def outlined_shell(outline=L_ROOM, **more):
    """A stored shell for a 12 by 10 room with a floor outline. The notch of L_ROOM is x > 2 with z > 1."""
    shell = {
        "source": "scan", "suggested": True,
        "room": {"width": 12.0, "depth": 10.0, "height": 5.0,
                 "outline": [{"x": x, "z": z} for x, z in outline]},
        "risers": [], "truss_lines": [], "truss_rings": [], "hanging_bands": [],
    }
    shell.update(more)
    return shell


def stands_inside(shell, fixtures, clear=0.19):
    """Whether every fixture is inside the shell's floor outline and that far from its walls."""
    outline = np.array([(p["x"], p["z"]) for p in shell["room"]["outline"]])
    x = np.array([f.position_x for f in fixtures], dtype=float)
    z = np.array([f.position_z for f in fixtures], dtype=float)
    return bool(clear_of_outline(x, z, outline, clear).all())


class TestGuessesInsideAnOutline:

    def test_a_floor_row_in_the_notch_of_an_l_comes_inside_as_one_piece(self):
        shell = outlined_shell()
        # Inside the room's box, and outside its walls.
        row = [fixture(i, f"Par {i}", "Floor", 3.0 + i, 0.2, 3.0) for i in range(3)]
        assert not stands_inside(shell, row, clear=0.0)

        moves, notes = suggest_positions(row, shell)

        assert [m.rig_fixture_id for m in moves] == [0, 1, 2]
        # The least shift that clears the notch: 2.2 m upstage, to 0.2 m off its wall at z = 1.
        assert [m.to_position for m in moves] == [(3.0 + i, 0.2, 0.8) for i in range(3)]
        assert all(m.reason == "Moved inside the walls." for m in moves)
        assert all(m.to_dict()["suggested"] is True for m in moves)
        assert notes == []
        apply(row, moves)
        assert stands_inside(shell, row)
        # Still the guesses they were: nothing here confirms a position.
        assert all(f.tags == GUESS for f in row)

    def test_the_row_keeps_its_spacing_and_its_height(self):
        shell = outlined_shell()
        row = [fixture(i, f"Par {i}", "Floor", 2.5 + 0.7 * i, 0.2 + 0.1 * i, 2.0 + 0.5 * i) for i in range(4)]
        before = [(f.position_x, f.position_y, f.position_z) for f in row]
        moves, _ = suggest_positions(row, shell)
        apply(row, moves)
        after = [(f.position_x, f.position_y, f.position_z) for f in row]
        assert stands_inside(shell, row)
        shifts = {(round(a[0] - b[0], 3), round(a[1] - b[1], 3), round(a[2] - b[2], 3)) for a, b in zip(after, before)}
        assert len(shifts) == 1
        assert next(iter(shifts))[1] == 0.0

    @pytest.mark.parametrize("label, y, more", [
        ("a floor row", 0.2, {}),
        ("an overhead row brought down to the hanging height", 6.0,
         {"hanging_bands": [{"height": 4.0, "top": 4.3, "lines": 0}]}),
    ])
    def test_applying_the_same_scan_again_moves_nothing(self, label, y, more):
        shell = outlined_shell(**more)
        row = [fixture(i, f"Spot {i}", "Rig", 3.0 + i, y, 3.0) for i in range(3)]
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == 3, label
        apply(row, moves)
        assert stands_inside(shell, row), label
        assert suggest_positions(row, shell)[0] == [], label

    def test_a_row_overhanging_its_truss_into_the_notch_comes_inside_and_stays_put(self):
        # A truss across the downstage arm of the L, shorter than the row drawn for it.
        truss = {"name": "Overhead line 1", "x1": -5.0, "z1": 3.0, "x2": 1.0, "z2": 3.0,
                 "height": 4.0, "top": 4.3, "length": 6.0, "across": 0.3, "axis": "x", "heading_deg": 0.0}
        shell = outlined_shell(truss_lines=[truss], hanging_bands=[{"height": 4.0, "top": 4.3, "lines": 1}])
        row = [fixture(i, f"Spot {i}", "Truss", -4.0 + 2.0 * i, 6.0, -2.0) for i in range(5)]

        moves, notes = suggest_positions(row, shell)
        assert len(moves) == 5
        assert any("overhangs" in note for note in notes)
        assert all("inside the walls" in m.reason for m in moves)
        apply(row, moves)
        assert stands_inside(shell, row)
        assert {f.position_y for f in row} == {4.0}
        steps = [round(b.position_x - a.position_x, 3) for a, b in zip(row, row[1:])]
        assert steps == [2.0] * 4 and len({f.position_z for f in row}) == 1
        assert suggest_positions(row, shell)[0] == []

    @pytest.mark.parametrize("tags", [
        ["position_source:tap"],
        ["position_source:confirmed"],
        ["position_source:mvr"],
        ["position_source:row_fit", "position_unconfirmed"],
    ])
    def test_a_placed_fixture_standing_in_the_notch_is_left_there(self, tags):
        shell = outlined_shell()
        row = [fixture(i, f"Par {i}", "Floor", 3.0 + i, 0.2, 3.0) for i in range(3)]
        row[1].tags = list(tags)
        moves, _ = suggest_positions(row, shell)
        assert [m.rig_fixture_id for m in moves] == [0, 2]
        assert (row[1].position_x, row[1].position_y, row[1].position_z) == (4.0, 0.2, 3.0)
        assert row[1].tags == tags

    def test_a_row_already_inside_the_outline_is_left_alone(self):
        shell = outlined_shell()
        # Close to the notch's walls, in both arms of the L, and inside the room.
        row = [fixture(i, f"Par {i}", "", -1.0 + i, 0.2, 1.1) for i in range(3)]
        row += [fixture(10 + i, f"Wash {i}", "", 3.0 + i, 0.2, 0.9) for i in range(3)]
        assert suggest_positions(row, shell) == ([], [])

    def test_a_guess_beyond_a_wall_at_an_angle_comes_inside_it(self):
        shell = outlined_shell(CUT_ROOM)
        # The cut corner runs from (6, 1) to (2, 5): (4.5, 3.5) is a metre beyond it, inside the box.
        row = [fixture(1, "Par 1", "", 4.5, 0.2, 3.5)]
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == 1
        apply(row, moves)
        assert stands_inside(shell, row)
        # Brought the short way in, not across the room.
        assert math.dist(moves[0].from_position, moves[0].to_position) < 1.2
        assert suggest_positions(row, shell)[0] == []

    def test_a_row_that_fits_nowhere_in_one_piece_has_its_guesses_brought_in_one_by_one(self):
        shell = outlined_shell()
        # Corner to corner of the box: its downstage stage-left end is always in the notch.
        row = [fixture(i, f"Par {i}", "Diagonal", -5.5 + 2.75 * i, 0.2, -4.5 + 2.25 * i) for i in range(5)]
        moves, notes = suggest_positions(row, shell)
        assert [m.rig_fixture_id for m in moves] == [3, 4]
        assert any("Diagonal" in note and "one piece" in note for note in notes)
        apply(row, moves)
        assert stands_inside(shell, row)
        assert suggest_positions(row, shell)[0] == []

    def test_a_scanned_l_shaped_room_holds_its_guesses_as_a_stored_one_does(self):
        vertices, faces = shaped_room_mesh()
        shell = scan(vertices, faces).shell
        row = [fixture(i, f"Par {i}", "Floor", 3.0 + i, 0.2, 3.0) for i in range(3)]
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == 3
        apply(row, moves)
        assert stands_inside(shell, row, clear=0.1)
        assert suggest_positions(row, shell)[0] == []

    def test_a_box_room_moves_a_row_exactly_as_it_did(self):
        box_shell = {"room": {"width": 12.0, "depth": 10.0, "height": 5.0}}
        row = [fixture(i, f"Par {i}", "Floor", 3.0 + 1.5 * i, 0.2, 3.0) for i in range(3)]
        moves, notes = suggest_positions(row, box_shell)
        # 6.0 is on the wall: the row comes 0.2 m in from it, and stays at its depth.
        assert [m.to_position for m in moves] == [(2.8 + 1.5 * i, 0.2, 3.0) for i in range(3)]
        assert all(m.reason == "Moved inside the walls." for m in moves)
        assert notes == []

    @pytest.mark.parametrize("outline", [
        [],
        [{"x": 0.0, "z": 0.0}, {"x": 1.0, "z": 0.0}],
        [{"x": -6.0, "z": -5.0}, {"x": 6.0, "z": -5.0}, {"x": "?", "z": 1.0}, {"x": -6.0, "z": 5.0}],
        [{"x": 0.0, "z": 0.0}, {"x": 0.5, "z": 0.0}, {"x": 0.5, "z": 0.5}],
        "an outline",
    ])
    def test_an_outline_that_is_not_one_is_a_box(self, outline):
        shell = {"room": {"width": 12.0, "depth": 10.0, "height": 5.0, "outline": outline}}
        # In what would be the notch of the L: inside the box, so nothing to do.
        row = [fixture(i, f"Par {i}", "Floor", 3.0 + i, 0.2, 3.0) for i in range(3)]
        assert suggest_positions(row, shell) == ([], [])

    def test_a_spot_on_a_ring_that_reaches_into_the_notch_comes_inside(self):
        # A stored ring the outline cuts through: a scan would not find one hanging there.
        ring = {"name": "Overhead ring 1", "center_x": 1.0, "center_z": 0.0, "radius": 2.0, "height": 4.0}
        shell = outlined_shell(truss_rings=[ring])
        row = [fixture(i, f"Spot {i}", "Ring", 0.0 + 0.5 * i, 4.5, 0.0) for i in range(8)]
        moves, _ = suggest_positions(row, shell)
        apply(row, moves)
        assert stands_inside(shell, row, clear=0.0)
        brought_in = [m for m in moves if "then inside the walls" in m.reason]
        # Of the eight places round it, only the one in the notch (downstage stage left) is off the ring.
        assert len(brought_in) == 1
        assert suggest_positions(row, shell)[0] == []
