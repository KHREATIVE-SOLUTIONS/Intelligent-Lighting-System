"""
Room scan: reading a phone scan and finding the room in it
==========================================================

Every mesh is made in the test (room_scan_meshes.py): one lopsided room,
written as OBJ, PLY, USD text and RoomPlan JSON, in metres, centimetres and
millimetres, Y-up and Z-up, square to its axes and turned off them.

What has to hold: the same room comes back whatever the file's units, up axis
and heading; it comes back the right way round (not mirrored); everything found
is marked as a suggestion; and a file that cannot be read says what to do
instead.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.room_scan import (
    RoomScanError, ScanOptions, detect_scan_format, extract_room, read_scan_file, suggest_positions,
)
from app.services.room_scan.suggest import TAG_SCAN_HINT
from app.services.room_scan.usd import parse_usda
from tests.unit.room_scan_meshes import (
    RISER, ROOM, STAGE, TRUSS, as_scanned, box, room_mesh, roomplan_json, sample_surface,
    write_obj, write_ply, write_usda, write_zip,
)


def turned_usda(ops: str, order, points) -> str:
    """One triangle of `points` under an Xform with the given ops."""
    listed = ", ".join(f'"{name}"' for name in order)
    written = ", ".join(f"({x}, {y}, {z})" for x, y, z in points)
    return f'''#usda 1.0
def Xform "Turned"
{{
    {ops}
    uniform token[] xformOpOrder = [{listed}]
    def Mesh "M"
    {{
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [{written}]
    }}
}}
'''


def scan(content: bytes, name: str, **options):
    return extract_room(read_scan_file(name, content), ScanOptions(**options))


def stage_of(shell):
    return next(r for r in shell["risers"] if r["kind"] == "stage")


def assert_the_room(shell, tolerance=0.1, truss=True):
    """The shell describes the synthetic room, the right way round."""
    room = shell["room"]
    assert room["width"] == pytest.approx(ROOM["width"], abs=tolerance)
    assert room["depth"] == pytest.approx(ROOM["depth"], abs=tolerance)
    assert room["height"] == pytest.approx(ROOM["height"], abs=tolerance)

    stage = stage_of(shell)
    # Stage right of centre and against the upstage wall. A mirrored room
    # would put it at +1.5; a room the wrong way round, at +3.25.
    assert stage["center_x"] == pytest.approx((STAGE["x_min"] + STAGE["x_max"]) / 2, abs=tolerance)
    assert stage["center_z"] == pytest.approx((STAGE["z_min"] + STAGE["z_max"]) / 2, abs=tolerance)
    assert stage["width"] == pytest.approx(STAGE["x_max"] - STAGE["x_min"], abs=2 * tolerance)
    assert stage["depth"] == pytest.approx(STAGE["z_max"] - STAGE["z_min"], abs=2 * tolerance)
    assert stage["height"] == pytest.approx(STAGE["height"], abs=0.05)

    riser = next(r for r in shell["risers"] if r["kind"] == "riser")
    assert riser["center_x"] == pytest.approx((RISER["x_min"] + RISER["x_max"]) / 2, abs=tolerance)
    assert riser["center_z"] == pytest.approx((RISER["z_min"] + RISER["z_max"]) / 2, abs=tolerance)
    assert riser["height"] == pytest.approx(RISER["height"], abs=0.05)

    if truss:
        assert len(shell["truss_lines"]) == 1
        line = shell["truss_lines"][0]
        assert line["axis"] == "x"
        assert line["z1"] == pytest.approx(TRUSS["z"], abs=tolerance)
        assert sorted((line["x1"], line["x2"])) == pytest.approx([TRUSS["x_min"], TRUSS["x_max"]], abs=2 * tolerance)
        assert line["height"] == pytest.approx(TRUSS["bottom"], abs=tolerance)
        assert [band["height"] for band in shell["hanging_bands"]] == pytest.approx([TRUSS["bottom"]], abs=tolerance)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

class TestObj:

    def test_points_and_triangles(self):
        vertices, faces = room_mesh()
        mesh = read_scan_file("room.obj", write_obj(vertices, faces))
        assert mesh.format == "obj"
        assert np.allclose(mesh.vertices, vertices, atol=1e-5)
        assert np.array_equal(mesh.faces, faces)
        assert mesh.up_axis is None and mesh.metres_per_unit is None

    def test_polygons_slashes_and_negative_indices(self):
        text = (
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nvn 0 0 1\n"
            "f 1/1/1 2/1/1 3/1/1 4/1/1\n"     # a quad, with texture and normal indices
            "v 2 0 0\n"
            "f -1 -3 -4\n"                      # counted back from the last point read
        )
        mesh = read_scan_file("quad.obj", text.encode())
        assert mesh.faces.tolist() == [[0, 1, 2], [0, 2, 3], [4, 2, 1]]

    def test_an_obj_is_known_by_its_lines_when_its_name_does_not_say(self):
        vertices, faces = room_mesh()
        assert detect_scan_format("export.txt", write_obj(vertices, faces)) == "obj"


class TestPly:

    @pytest.mark.parametrize("fmt", ["ascii", "binary_little_endian", "binary_big_endian"])
    def test_every_encoding_reads_the_same_mesh(self, fmt):
        vertices, faces = room_mesh()
        mesh = read_scan_file("room.ply", write_ply(vertices, faces, fmt))
        assert mesh.format == "ply"
        assert np.allclose(mesh.vertices, vertices, atol=1e-4)
        assert np.array_equal(mesh.faces, faces)

    @pytest.mark.parametrize("fmt", ["ascii", "binary_little_endian"])
    def test_quads_and_mixed_faces_are_cut_into_triangles(self, fmt):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0]], dtype=float)
        mesh = read_scan_file("mixed.ply", write_ply(vertices, [[0, 1, 2, 3], [1, 4, 2]], fmt))
        assert mesh.faces.tolist() == [[0, 1, 2], [0, 2, 3], [1, 4, 2]]

    @pytest.mark.parametrize("fmt", ["ascii", "binary_little_endian"])
    def test_a_ply_with_no_faces_is_a_point_cloud_and_keeps_its_normals(self, fmt):
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
        normals = np.tile([0.0, 1.0, 0.0], (4, 1))
        mesh = read_scan_file("cloud.ply", write_ply(points, None, fmt, normals=normals))
        assert mesh.is_point_cloud
        assert np.allclose(mesh.vertices, points)
        assert np.allclose(mesh.normals, normals)
        assert any("point cloud" in note for note in mesh.notes)

    def test_a_ply_cut_short_says_so(self):
        vertices, faces = room_mesh()
        content = write_ply(vertices, faces)
        with pytest.raises(RoomScanError, match="cut short"):
            read_scan_file("room.ply", content[:len(content) // 2])


class TestUsd:

    def test_a_text_layer_gives_its_mesh_its_axes_and_its_units(self):
        vertices, faces = room_mesh()
        mesh = read_scan_file("room.usda", write_usda(vertices, faces, up="Z", metres_per_unit=0.01).encode())
        assert mesh.format == "usda"
        assert mesh.up_axis == "z"
        assert mesh.metres_per_unit == pytest.approx(0.01)
        assert np.allclose(mesh.vertices, vertices, atol=1e-5)
        assert np.array_equal(mesh.faces, faces)

    def test_a_mesh_is_placed_by_the_transform_above_it(self):
        corners, triangles = box(0, 1, 0, 1, 0, 1)
        mesh = parse_usda(write_usda(corners, triangles, translate=(10.0, 0.0, -2.0)))
        assert np.allclose(mesh.vertices, corners + np.array([10.0, 0.0, -2.0]))

    def test_transform_ops_apply_in_their_stated_order(self):
        text = '''#usda 1.0
def Xform "Outer"
{
    double3 xformOp:translate = (5, 0, 0)
    uniform token[] xformOpOrder = ["xformOp:translate"]
    def Xform "Inner"
    {
        float xformOp:rotateY = 90
        double3 xformOp:scale = (2, 2, 2)
        double3 xformOp:translate = (0, 1, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateY", "xformOp:scale"]
        def Mesh "M"
        {
            int[] faceVertexCounts = [3]
            int[] faceVertexIndices = [0, 1, 2]
            point3f[] points = [(1, 0, 0), (0, 0, 0), (0, 1, 0)]
        }
    }
}
'''
        mesh = parse_usda(text)
        # Scaled to (2,0,0), turned a quarter about Y to (0,0,-2), lifted 1, then moved 5 across.
        assert np.allclose(mesh.vertices[0], [5.0, 1.0, -2.0], atol=1e-6)
        assert np.allclose(mesh.vertices[1], [5.0, 1.0, 0.0], atol=1e-6)
        assert np.allclose(mesh.vertices[2], [5.0, 3.0, 0.0], atol=1e-6)

    def test_a_usdz_with_a_text_layer_is_read(self):
        vertices, faces = room_mesh()
        archive = write_zip([("room.usda", write_usda(vertices, faces).encode()), ("textures/a.png", b"\x89PNG")])
        mesh = read_scan_file("room.usdz", archive)
        assert mesh.format == "usda"
        assert len(mesh.vertices) == len(vertices)

    # Binary USD (USDC) is read: tests/unit/test_room_scan_usdc.py. What is
    # here is a layer that only starts like one, which is still refused, and
    # still says what to export instead.

    def test_a_usdz_whose_binary_usd_cannot_be_read_says_to_export_obj(self):
        archive = write_zip([("room.usdc", b"PXR-USDC" + bytes(64))])
        with pytest.raises(RoomScanError) as refused:
            read_scan_file("Room.usdz", archive)
        message = str(refused.value)
        assert "cannot be read" in message
        assert "OBJ" in message and "Polycam" in message and "Scaniverse" in message

    def test_a_layer_is_known_by_its_first_bytes_not_its_name(self):
        # A binary layer wearing a text layer's name is read as binary (and
        # this one, being nothing but its first bytes, refused as binary), and
        # a text layer named .usd is still read.
        with pytest.raises(RoomScanError, match="binary USD.*OBJ"):
            read_scan_file("room.usdz", write_zip([("room.usda", b"PXR-USDC" + bytes(64))]))
        vertices, faces = room_mesh()
        mesh = read_scan_file("room.usdz", write_zip([("room.usd", write_usda(vertices, faces).encode())]))
        assert len(mesh.vertices) == len(vertices)

    def test_a_bare_binary_usd_file_that_cannot_be_read_is_refused_the_same_way(self):
        with pytest.raises(RoomScanError, match="binary USD.*OBJ"):
            read_scan_file("room.usdc", b"PXR-USDC" + bytes(64))

    def test_a_text_layer_is_read_before_a_binary_one(self):
        vertices, faces = room_mesh()
        archive = write_zip([("a.usdc", b"PXR-USDC" + bytes(64)), ("b.usda", write_usda(vertices, faces).encode())])
        mesh = read_scan_file("room.usdz", archive)
        assert mesh.format == "usda"
        assert any("2 USD layers" in note for note in mesh.notes)

    def test_an_inverted_op_undoes_the_op_it_names(self):
        # How USD writes a pivot: move to it, turn, move back.
        text = '''#usda 1.0
def Xform "Pivoted"
{
    double3 xformOp:translate:pivot = (1, 0, 0)
    float xformOp:rotateY = 90
    uniform token[] xformOpOrder = ["xformOp:translate:pivot", "xformOp:rotateY", "!invert!xformOp:translate:pivot"]
    def Mesh "M"
    {
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(1, 0, 0), (2, 0, 0), (1, 1, 0)]
    }
}
'''
        mesh = parse_usda(text)
        # A quarter turn about the upright line through (1, 0, 0): that point stays, (2,0,0) swings to (1,0,-1).
        assert np.allclose(mesh.vertices, [[1, 0, 0], [1, 0, -1], [1, 1, 0]], atol=1e-6)

    @pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
    def test_a_three_axis_rotate_turns_about_its_axes_in_the_order_of_its_name(self, order):
        """rotateZYX = (x, y, z) holds the degrees about X, Y and Z in that
        order whatever the op is called, and turns about Z first, then Y, then X."""
        degrees = {"X": 10.0, "Y": 20.0, "Z": 35.0}
        value = f'({degrees["X"]}, {degrees["Y"]}, {degrees["Z"]})'
        points = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 2.0, 3.0]])
        together = parse_usda(turned_usda(
            f"float3 xformOp:rotate{order} = {value}", [f"xformOp:rotate{order}"], points))

        # Worked out here: the right-handed turn about each axis, one after the other.
        def turn(axis, p):
            a = np.radians(degrees[axis])
            c, s = np.cos(a), np.sin(a)
            x, y, z = p
            if axis == "X":
                return np.array([x, c * y - s * z, s * y + c * z])
            if axis == "Y":
                return np.array([c * x + s * z, y, -s * x + c * z])
            return np.array([c * x - s * y, s * x + c * y, z])

        expected = []
        for p in points:
            for axis in order:
                p = turn(axis, p)
            expected.append(p)
        assert np.allclose(together.vertices, expected, atol=1e-6)

        # And as three ops of one axis each. xformOpOrder is outermost first, so the first turn is listed last.
        singles = "\n    ".join(f"float xformOp:rotate{axis} = {degrees[axis]}" for axis in "XYZ")
        apart = parse_usda(turned_usda(singles, [f"xformOp:rotate{axis}" for axis in reversed(order)], points))
        assert np.allclose(together.vertices, apart.vertices, atol=1e-6)

        # The six orders are six different turns: a reader that ignored the name would fail five of these.
        if order != "XYZ":
            xyz = parse_usda(turned_usda(f"float3 xformOp:rotateXYZ = {value}", ["xformOp:rotateXYZ"], points))
            assert not np.allclose(together.vertices, xyz.vertices, atol=1e-3)

    @pytest.mark.parametrize("op", ["float2 xformOp:rotateXY = (10, 20)", "float3 xformOp:rotateXXY = (10, 20, 30)"])
    def test_a_rotate_that_is_not_one_axis_or_all_three_is_not_guessed_at(self, op):
        points = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        mesh = parse_usda(turned_usda(op, [op.split()[1]], points))
        assert np.allclose(mesh.vertices, points)
        assert any("1 transform in the USD layer could not be read" in note for note in mesh.notes)

    def test_roomplan_json_inside_a_usdz_is_preferred(self):
        archive = write_zip([("room.usdc", b"PXR-USDC" + bytes(64)), ("room.json", roomplan_json())])
        mesh = read_scan_file("Room.usdz", archive)
        assert mesh.format == "roomplan"
        assert mesh.up_axis == "y" and mesh.metres_per_unit == 1.0
        assert [o["category"] for o in mesh.objects] == ["storage"]


class TestWhatCannotBeRead:

    @pytest.mark.parametrize("name, content, says", [
        ("empty.obj", b"", "empty"),
        ("scan.glb", b"glTF" + bytes(32), "GLB"),       # the first four bytes of one, and nothing after
        ("scan.glb", b"glTF" + bytes(32), "glTF 2.0"),
        ("notes.txt", b"this is not a scan\n", "OBJ, PLY"),
        ("room.json", b'{"rooms": []}', "walls"),
        ("room.usdz", b"PK\x03\x04 not really a zip", "archive"),
        ("room.ply", b"ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nend_header\n1\n2\n", "x, y and z"),
    ])
    def test_the_message_says_what_is_wrong(self, name, content, says):
        with pytest.raises(RoomScanError) as refused:
            read_scan_file(name, content)
        assert says in str(refused.value)

    def test_a_flat_scan_is_not_a_room(self):
        corners, triangles = box(-5, 5, 0, 0.2, -4, 4)
        with pytest.raises(RoomScanError, match="not a room"):
            scan(write_obj(corners, triangles), "slab.obj", units="m", up_axis="y")


# ---------------------------------------------------------------------------
# The room
# ---------------------------------------------------------------------------

class TestRoomShell:

    @pytest.mark.parametrize("label, yaw, up, units_per_metre, unit", [
        ("metres, Y-up, square", 0.0, "y", 1.0, "m"),
        ("centimetres, Y-up", 0.0, "y", 100.0, "cm"),
        ("metres, Z-up", 0.0, "z", 1.0, "m"),
        ("centimetres, Z-up", 0.0, "z", 100.0, "cm"),
        ("millimetres, Y-up", 0.0, "y", 1000.0, "mm"),
        ("turned 25 degrees", 25.0, "y", 1.0, "m"),
        ("turned 100 degrees, Z-up, centimetres", 100.0, "z", 100.0, "cm"),
        ("turned right round", 180.0, "y", 1.0, "m"),
        ("turned 250 degrees, Z-up", 250.0, "z", 1.0, "m"),
    ])
    def test_the_same_room_whatever_the_units_axes_and_heading(self, label, yaw, up, units_per_metre, unit):
        vertices, faces = room_mesh()
        placed = as_scanned(vertices, yaw, offset=(3.2, 0.7, -8.1), up=up, units_per_metre=units_per_metre)

        found = scan(write_obj(placed, faces), "room.obj")

        assert found.shell["scan"]["units"] == unit, label
        assert found.shell["scan"]["up_axis"] == up, label
        assert_the_room(found.shell)

    @pytest.mark.parametrize("fmt", ["ascii", "binary_little_endian", "binary_big_endian"])
    def test_ply_gives_the_same_room(self, fmt):
        vertices, faces = room_mesh()
        placed = as_scanned(vertices, 25.0, offset=(1.0, 2.0, 3.0), up="z", units_per_metre=100.0)
        assert_the_room(scan(write_ply(placed, faces, fmt), "room.ply").shell)

    def test_a_point_cloud_with_no_faces_and_no_normals_gives_the_same_room(self):
        vertices, faces = room_mesh()
        placed = as_scanned(vertices, 25.0, offset=(4.0, -1.0, 2.0), up="z")
        cloud = sample_surface(placed, faces, 220_000)

        found = scan(write_ply(cloud), "cloud.ply")

        assert found.shell["scan"]["point_cloud"] is True
        assert_the_room(found.shell, tolerance=0.2)

    def test_usd_is_read_with_the_axes_and_units_it_declares(self):
        vertices, faces = room_mesh()
        placed = as_scanned(vertices, 0.0, up="z", units_per_metre=100.0)
        found = scan(write_usda(placed, faces, up="Z", metres_per_unit=0.01).encode(), "room.usda")
        assert found.shell["scan"]["units"] == "cm"
        assert found.shell["scan"]["up_axis"] == "z"
        assert any("the file says so" in line for line in found.assumptions)
        assert_the_room(found.shell)

    @pytest.mark.parametrize("with_floor", [True, False])
    def test_roomplan_walls_give_the_room_and_its_object_a_raised_area(self, with_floor):
        found = scan(roomplan_json(with_floor), "room.json")
        room = found.shell["room"]
        assert room["width"] == pytest.approx(ROOM["width"], abs=0.1)
        assert room["depth"] == pytest.approx(ROOM["depth"], abs=0.1)
        assert room["height"] == pytest.approx(ROOM["height"], abs=0.1)
        stage = stage_of(found.shell)
        assert stage["center_x"] == pytest.approx(-1.5, abs=0.1)
        assert stage["center_z"] == pytest.approx(-3.25, abs=0.1)
        assert found.shell["scan"]["objects"] == [{"category": "storage", "size": [6.0, 0.9, 2.5]}]

    def test_everything_found_is_marked_as_a_suggestion(self):
        vertices, faces = room_mesh()
        shell = scan(write_obj(vertices, faces), "room.obj").shell
        assert shell["source"] == "scan" and shell["suggested"] is True
        assert shell["room"]["suggested"] is True
        elements = shell["risers"] + shell["truss_lines"] + shell["hanging_bands"]
        assert len(elements) == 4
        for element in elements:
            assert element["suggested"] is True
            assert element["basis"].startswith("scan:")
        assert "checked against the room" in shell["basis"]

    def test_the_same_file_gives_the_same_shell(self):
        vertices, faces = room_mesh()
        content = write_obj(as_scanned(vertices, 25.0, up="z"), faces)
        assert scan(content, "room.obj").shell == scan(content, "room.obj").shell

    def test_the_guesses_are_listed_and_can_be_overridden(self):
        vertices, faces = room_mesh()
        content = write_obj(vertices, faces)

        guessed = scan(content, "room.obj")
        text = " ".join(guessed.assumptions)
        assert "Units read as m" in text and "Y-up" in text and "upstage" in text

        # Told the file is in centimetres, the 5 m room is 5 cm high: not a room.
        with pytest.raises(RoomScanError, match="not a room"):
            scan(content, "room.obj", units="cm")

        # A half turn puts the stage at the other end and the other side.
        turned = scan(content, "room.obj", rotate=180)
        stage = stage_of(turned.shell)
        assert stage["center_x"] == pytest.approx(1.5, abs=0.1)
        assert stage["center_z"] == pytest.approx(3.25, abs=0.1)

        # A quarter turn swaps the room's width and depth.
        quarter = scan(content, "room.obj", rotate=90)
        assert quarter.shell["room"]["width"] == pytest.approx(ROOM["depth"], abs=0.1)
        assert quarter.shell["room"]["depth"] == pytest.approx(ROOM["width"], abs=0.1)
        # Clockwise seen from above: upstage (-Z) goes to stage left (+X).
        stage = stage_of(quarter.shell)
        assert stage["center_x"] == pytest.approx(3.25, abs=0.1)
        assert stage["center_z"] == pytest.approx(-1.5, abs=0.1)

        with pytest.raises(RoomScanError, match="0, 90, 180 or 270"):
            scan(content, "room.obj", rotate=45)

    def test_a_bare_room_has_nothing_raised_and_nothing_overhead(self):
        vertices, faces = room_mesh(truss=False, stage=False, riser=False)
        found = scan(write_obj(as_scanned(vertices, 25.0), faces), "bare.obj")
        assert found.shell["risers"] == []
        assert found.shell["truss_lines"] == [] and found.shell["hanging_bands"] == []
        assert found.shell["room"]["width"] == pytest.approx(ROOM["width"], abs=0.1)
        text = " ".join(found.assumptions)
        assert "No raised area" in text and "No truss or bar" in text

    def test_a_scan_that_leaks_through_a_doorway_keeps_its_walls(self):
        vertices, faces = room_mesh()
        # A corridor seen through a door in the stage-left wall: 3 m of it, 1.2 m wide.
        corridor = box(6.0, 9.0, 0.0, 2.2, 1.0, 2.2)
        merged_vertices = np.vstack([vertices, corridor[0]])
        merged_faces = np.vstack([faces, corridor[1] + len(vertices)])
        found = scan(write_obj(merged_vertices, merged_faces), "leaky.obj")
        assert found.shell["room"]["width"] == pytest.approx(ROOM["width"], abs=0.15)


# ---------------------------------------------------------------------------
# Fixture positions
# ---------------------------------------------------------------------------

GUESS = ["position_source:template", "position_unconfirmed"]


def fixture(id, name, group, x, y, z, tags=None):
    return SimpleNamespace(
        id=id, name=name, group_name=group, position_x=x, position_y=y, position_z=z,
        tags=list(GUESS if tags is None else tags),
    )


@pytest.fixture(scope="module")
def shell():
    vertices, faces = room_mesh()
    return scan(write_obj(vertices, faces), "room.obj").shell


class TestSuggestedPositions:

    def test_an_overhead_row_goes_under_the_truss_as_one_piece(self, shell):
        row = [fixture(i, f"Spot {i}", "US Truss Spots", -3.0 + 2.0 * (i - 1), 6.0, -2.0) for i in range(1, 5)]
        moves, _ = suggest_positions(row, shell)

        assert [m.rig_fixture_id for m in moves] == [1, 2, 3, 4]
        for move, before in zip(moves, row):
            x, y, z = move.to_position
            assert y == pytest.approx(TRUSS["bottom"], abs=0.1)
            assert z == pytest.approx(TRUSS["z"], abs=0.1)
            # Already within the line's length: not slid along it.
            assert x == pytest.approx(before.position_x, abs=1e-6)
            assert "Overhead line 1" in move.reason
        spacing = {round(b.to_position[0] - a.to_position[0], 6) for a, b in zip(moves, moves[1:])}
        assert spacing == {2.0}

    def test_a_row_past_the_end_of_the_truss_slides_along_it(self, shell):
        row = [fixture(i, f"Wash {i}", "Wash", 2.0 + i, 6.0, 0.0) for i in range(1, 5)]     # x 3..6
        moves, _ = suggest_positions(row, shell)
        xs = [m.to_position[0] for m in moves]
        assert max(xs) == pytest.approx(TRUSS["x_max"], abs=0.2)
        assert [round(b - a, 6) for a, b in zip(xs, xs[1:])] == [1.0, 1.0, 1.0]

    def test_a_floor_row_where_the_stage_is_goes_up_onto_it(self, shell):
        row = [fixture(i, f"Par {i}", "Floor Pars", -3.0 + i, 0.2, -4.4) for i in range(1, 4)]
        moves, _ = suggest_positions(row, shell)
        assert len(moves) == 3
        for move in moves:
            x, y, z = move.to_position
            assert y == pytest.approx(0.2 + STAGE["height"], abs=0.06)
            assert STAGE["z_min"] + 0.25 <= z <= STAGE["z_max"] - 0.25
            assert "stage" in move.reason

    def test_a_floor_row_out_on_the_dance_floor_stays_put(self, shell):
        row = [fixture(i, f"Par {i}", "DS Pars", -2.0 + i, 0.2, 3.0) for i in range(1, 4)]
        assert suggest_positions(row, shell)[0] == []

    def test_a_row_outside_the_walls_comes_inside(self, shell):
        row = [fixture(i, f"Bar {i}", "Bars", 5.0 + 0.5 * i, 0.2, 4.0) for i in range(1, 4)]   # x 5.5..6.5
        moves, _ = suggest_positions(row, shell)
        assert max(m.to_position[0] for m in moves) <= ROOM["width"] / 2 - 0.15
        assert all("inside the walls" in m.reason for m in moves)

    @pytest.mark.parametrize("tags", [
        ["position_source:tap"],
        ["position_source:confirmed"],
        ["position_source:mvr"],
        ["position_source:row_fit", "position_unconfirmed"],
        ["position_source:template"],                           # confirmed some other way
        [],
    ])
    def test_only_an_unconfirmed_template_guess_is_ever_moved(self, shell, tags):
        row = [fixture(i, f"Spot {i}", "Truss", -3.0 + i, 9.0, -2.0, tags=tags) for i in range(1, 4)]
        assert suggest_positions(row, shell)[0] == []

    def test_with_nothing_overhead_a_row_only_comes_down_under_the_ceiling(self):
        vertices, faces = room_mesh(truss=False)
        bare = scan(write_obj(vertices, faces), "room.obj").shell
        high = [fixture(i, f"Spot {i}", "High", -1.0 + i, 6.5, 0.0) for i in range(1, 3)]
        low = [fixture(i + 10, f"Spot {i}", "Low", -1.0 + i, 3.5, 0.0) for i in range(1, 3)]

        moves, _ = suggest_positions(high + low, bare)

        assert {m.group for m in moves} == {"High"}
        assert all(m.to_position[1] == pytest.approx(ROOM["height"] - 0.3, abs=0.1) for m in moves)

    def test_no_shell_moves_nothing(self):
        assert suggest_positions([fixture(1, "Spot", "Truss", 0, 6, 0)], None) == ([], [])

    def test_the_hint_tag_is_spelled_in_one_place(self):
        assert TAG_SCAN_HINT == "position_hint:room_scan"
