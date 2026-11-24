"""
Room scan: glTF 2.0 (.glb and .gltf)
====================================

Polycam, Scaniverse and most LiDAR apps export glTF by default. Every file
here is built in the test (room_scan_meshes.py: `gltf_scene`, `write_glb`,
`write_gltf`), with struct and json, and nothing is read from disk.

What has to hold: a .glb and a .gltf of the same scene are the same mesh; the
nodes above a mesh place it (matrix, or translation, rotation and scale, nested);
indexed and non-indexed primitives, every index width and an interleaved buffer
all read; the room comes back the right way round through the same extraction
an OBJ goes through; and a file that cannot be read says what to do instead,
never a traceback.

The expected positions are worked out here from an axis and an angle
(Rodrigues' formula), not from the quaternion formula the reader uses.
"""

import json
import math
import struct

import numpy as np
import pytest

from app.services.room_scan import RoomScanError, ScanOptions, detect_scan_format, extract_room, read_scan_file
from app.services.room_scan import gltf as gltf_reader
from tests.unit.room_scan_meshes import (
    ROOM, as_scanned, box, gltf_scene, room_mesh, roomplan_json, sample_surface, write_glb, write_gltf, write_obj,
)
from tests.unit.test_room_scan import assert_the_room


def turn(axis, degrees) -> np.ndarray:
    """A rotation about an axis, by Rodrigues' formula."""
    k = np.array(axis, dtype=np.float64)
    k = k / np.linalg.norm(k)
    a = math.radians(degrees)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * cross + (1 - math.cos(a)) * (cross @ cross)


def quaternion(axis, degrees) -> list:
    """The same rotation as glTF writes it: (x, y, z, w)."""
    k = np.array(axis, dtype=np.float64)
    k = k / np.linalg.norm(k)
    half = math.radians(degrees) / 2.0
    return [*(k * math.sin(half)).tolist(), math.cos(half)]


def column_major(rotation: np.ndarray, translation) -> list:
    """A 4 by 4 as glTF's `matrix` has it: sixteen numbers, column by column."""
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix.T.reshape(-1).tolist()


SMALL = box(0.0, 2.0, 0.0, 1.0, 0.0, 3.0)      # 8 points, 12 triangles: every index fits in a byte


def small_glb(node=None, **how) -> bytes:
    doc, data = gltf_scene([(SMALL[0], SMALL[1], node or {})], **how)
    return write_glb(doc, data)


# ---------------------------------------------------------------------------
# The same mesh, whichever way it is written
# ---------------------------------------------------------------------------

class TestGlbAndGltf:

    def test_a_glb_and_a_gltf_of_one_scene_are_the_same_mesh(self):
        vertices, faces = room_mesh()
        doc, data = gltf_scene([(vertices, faces, {})])

        glb = read_scan_file("club.glb", write_glb(doc, data))
        text = read_scan_file("club.gltf", write_gltf(doc, data))

        assert (glb.format, text.format) == ("glb", "gltf")
        assert np.allclose(glb.vertices, vertices, atol=1e-5)
        assert np.array_equal(glb.faces, faces)
        assert np.array_equal(text.vertices, glb.vertices)
        assert np.array_equal(text.faces, glb.faces)

    def test_gltf_says_its_axes_and_units(self):
        mesh = read_scan_file("club.glb", small_glb())
        assert mesh.up_axis == "y" and mesh.metres_per_unit == 1.0
        assert any("Y-up and in metres" in note for note in mesh.notes)

    def test_which_reader_a_file_goes_to(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        # A GLB by its first four bytes, whatever it is called.
        assert detect_scan_format("export.bin", write_glb(doc, data)) == "glb"
        assert detect_scan_format("club.glb", write_glb(doc, data)) == "glb"
        # A .gltf is JSON, as RoomPlan's file is: told apart by its name, or by its `asset`.
        assert detect_scan_format("club.gltf", write_gltf(doc, data)) == "gltf"
        assert detect_scan_format("club.json", write_gltf(doc, data)) == "gltf"
        assert detect_scan_format("Room.json", roomplan_json()) == "roomplan"

    def test_a_gltf_named_json_is_read(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        mesh = read_scan_file("club.json", write_gltf(doc, data))
        assert mesh.format == "gltf" and len(mesh.faces) == 12

    def test_a_glb_whose_buffer_is_a_data_uri_is_read(self):
        """Some exporters write a .glb with no BIN part and the buffer inside the JSON."""
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        inside = json.loads(write_gltf(doc, data))
        mesh = read_scan_file("club.glb", write_glb(inside))
        assert np.allclose(mesh.vertices, SMALL[0])


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

class TestNodeTransforms:

    def test_translation_rotation_and_scale(self):
        """Scaled first, then turned, then moved. The axis and the scale are lopsided on purpose."""
        axis, degrees, scale, move = (1.0, 2.0, -0.5), 40.0, (2.0, 0.5, 3.0), (4.0, -1.0, 2.5)
        node = {"translation": list(move), "rotation": quaternion(axis, degrees), "scale": list(scale)}

        mesh = read_scan_file("turned.glb", small_glb(node))

        expected = (SMALL[0] * np.array(scale)) @ turn(axis, degrees).T + np.array(move)
        assert np.allclose(mesh.vertices, expected, atol=1e-5)

    def test_a_matrix_is_read_column_by_column(self):
        rotation, move = turn((0.3, 1.0, 0.2), 65.0), (-3.0, 0.75, 6.0)
        mesh = read_scan_file("turned.glb", small_glb({"matrix": column_major(rotation, move)}))
        assert np.allclose(mesh.vertices, SMALL[0] @ rotation.T + np.array(move), atol=1e-5)

    def test_a_node_under_a_node(self):
        """parent (a matrix) times child (translation, rotation, scale), in that order."""
        parent_turn, parent_move = turn((0.0, 1.0, 0.0), 35.0), (2.0, 0.5, -3.0)
        child_axis, child_degrees, child_scale, child_move = (1.0, 0.0, 1.0), -70.0, (1.5, 1.0, 0.5), (0.0, 2.0, 1.0)
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {
            "translation": list(child_move), "rotation": quaternion(child_axis, child_degrees),
            "scale": list(child_scale),
        })])
        doc["nodes"].append({"name": "parent", "matrix": column_major(parent_turn, parent_move), "children": [0]})
        doc["scenes"][0]["nodes"] = [1]

        expected = (SMALL[0] * np.array(child_scale)) @ turn(child_axis, child_degrees).T + np.array(child_move)
        expected = expected @ parent_turn.T + np.array(parent_move)
        for content, name in ((write_glb(doc, data), "nested.glb"), (write_gltf(doc, data), "nested.gltf")):
            assert np.allclose(read_scan_file(name, content).vertices, expected, atol=1e-5)

    def test_a_mesh_drawn_by_two_nodes_is_read_twice(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["nodes"].append({"mesh": 0, "translation": [10.0, 0.0, 0.0]})
        doc["scenes"][0]["nodes"].append(1)

        mesh = read_scan_file("twice.glb", write_glb(doc, data))

        assert len(mesh.vertices) == 16 and len(mesh.faces) == 24
        assert np.allclose(mesh.vertices[8:], SMALL[0] + np.array([10.0, 0.0, 0.0]))
        assert np.array_equal(mesh.faces[12:], SMALL[1] + 8)

    def test_only_the_default_scene_is_read(self):
        far = box(100.0, 101.0, 0.0, 1.0, 100.0, 101.0)
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {}), (far[0], far[1], {})])
        doc["scenes"] = [{"nodes": [1]}, {"nodes": [0]}]
        doc["scene"] = 1
        mesh = read_scan_file("scenes.glb", write_glb(doc, data))
        assert np.allclose(mesh.vertices, SMALL[0])

    def test_with_no_scene_every_node_that_is_nobodys_child_is_read(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {"translation": [1.0, 0.0, 0.0]})])
        doc["nodes"].append({"children": [0], "translation": [0.0, 5.0, 0.0]})
        del doc["scenes"], doc["scene"]
        mesh = read_scan_file("bare.glb", write_glb(doc, data))
        assert np.allclose(mesh.vertices, SMALL[0] + np.array([1.0, 5.0, 0.0]))


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

class TestPrimitives:

    @pytest.mark.parametrize("index_format", ["B", "H", "I"])
    def test_every_index_width(self, index_format):
        mesh = read_scan_file("box.glb", small_glb(index_format=index_format))
        assert np.array_equal(mesh.faces, SMALL[1])
        assert np.allclose(mesh.vertices, SMALL[0])

    def test_no_indices_is_three_corners_to_a_triangle_in_turn(self):
        mesh = read_scan_file("soup.glb", small_glb(indexed=False))
        assert len(mesh.vertices) == 36 and len(mesh.faces) == 12
        assert np.array_equal(mesh.faces, np.arange(36).reshape(12, 3))
        assert np.allclose(mesh.vertices[mesh.faces], SMALL[0][SMALL[1]])

    def test_an_interleaved_buffer_is_read_by_its_stride_and_offsets(self):
        """byteStride 24, the accessor 12 bytes into each row, the view part-way into the buffer."""
        other = box(5.0, 6.0, 0.0, 2.0, 5.0, 7.0)
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {}), (other[0], other[1], {})], interleaved=True)
        position = doc["accessors"][doc["meshes"][1]["primitives"][0]["attributes"]["POSITION"]]
        view = doc["bufferViews"][position["bufferView"]]
        assert view["byteStride"] == 24 and view["byteOffset"] > 0 and position["byteOffset"] == 12

        mesh = read_scan_file("interleaved.glb", write_glb(doc, data))

        assert np.allclose(mesh.vertices, np.vstack([SMALL[0], other[0]]))
        assert np.array_equal(mesh.faces, np.vstack([SMALL[1], other[1] + 8]))

    def test_strips_and_fans_become_triangles(self):
        square = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1], [1, 0, 1]], dtype=np.float64)
        run = np.array([[0, 1, 2], [3, 0, 0]])           # written out as the corners 0 1 2 3 0 0
        doc, data = gltf_scene([(square, run, {})], mode=5)
        doc["accessors"][1]["count"] = 4
        strip = read_scan_file("strip.glb", write_glb(doc, data))
        assert strip.faces.tolist() == [[0, 1, 2], [2, 1, 3]]

        doc, data = gltf_scene([(square, np.array([[0, 1, 3], [2, 0, 0]]), {})], mode=6)
        doc["accessors"][1]["count"] = 4
        fan = read_scan_file("fan.glb", write_glb(doc, data))
        assert fan.faces.tolist() == [[0, 1, 3], [0, 3, 2]]

    def test_points_alone_are_a_point_cloud(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {"translation": [0.0, 1.0, 0.0]})], indexed=False, mode=0)
        mesh = read_scan_file("cloud.glb", write_glb(doc, data))
        assert mesh.is_point_cloud and len(mesh.vertices) == 36
        assert np.allclose(mesh.vertices, SMALL[0][SMALL[1].reshape(-1)] + np.array([0.0, 1.0, 0.0]))
        assert any("point cloud" in note for note in mesh.notes)

    def test_lines_beside_a_mesh_are_left_out_and_said_to_be(self):
        wire = box(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {}), (wire[0], wire[1], {})])
        doc["meshes"][1]["primitives"][0]["mode"] = 1
        mesh = read_scan_file("wire.glb", write_glb(doc, data))
        assert len(mesh.vertices) == 8 and len(mesh.faces) == 12
        assert any("line ends beside the mesh were left out" in note for note in mesh.notes)

    @pytest.mark.parametrize("mode", [1, 2, 3])
    def test_lines_alone_give_their_points_as_a_point_cloud(self, mode):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {"translation": [0.0, 0.0, 2.0]})], mode=mode)
        mesh = read_scan_file("wire.glb", write_glb(doc, data))
        assert mesh.is_point_cloud
        assert np.allclose(mesh.vertices, SMALL[0] + np.array([0.0, 0.0, 2.0]))
        assert any("lines and no triangles" in note for note in mesh.notes)

    def test_a_point_cloud_in_a_glb_is_read_for_its_room(self):
        """A LiDAR app's point export: the room's surface as loose points, no triangles."""
        vertices, faces = room_mesh()
        points = sample_surface(vertices, faces, 60_000)
        doc, data = gltf_scene([(points, np.arange(len(points)).reshape(-1, 3), {})], indexed=False, mode=0)
        found = extract_room(read_scan_file("cloud.glb", write_glb(doc, data)), ScanOptions())
        for key in ("width", "depth", "height"):
            assert found.shell["room"][key] == pytest.approx(ROOM[key], abs=0.15)

    def test_a_bad_index_never_lands_on_another_parts_point(self):
        other = box(5.0, 6.0, 0.0, 2.0, 5.0, 7.0)
        wrong = SMALL[1].copy()
        wrong[0] = (0, 1, 9)            # there are 8 points in this part; 9 is one of the next part's
        doc, data = gltf_scene([(SMALL[0], wrong, {}), (other[0], other[1], {})])
        mesh = read_scan_file("wrong.glb", write_glb(doc, data))
        assert len(mesh.faces) == 23
        assert np.array_equal(mesh.faces[:11], SMALL[1][1:])
        assert any("left out" in note for note in mesh.notes)


# ---------------------------------------------------------------------------
# The room
# ---------------------------------------------------------------------------

class TestTheRoomInAGltf:

    @pytest.mark.parametrize("write, name, fmt", [(write_glb, "club.glb", "glb"), (write_gltf, "club.gltf", "gltf")])
    def test_the_room_comes_back_the_right_way_round(self, write, name, fmt):
        """Turned 25 degrees and moved off its origin, as a phone hands a scan over."""
        vertices, faces = room_mesh()
        doc, data = gltf_scene([(as_scanned(vertices, 25.0, offset=(2.0, 0.5, -3.0)), faces, {})])

        found = extract_room(read_scan_file(name, write(doc, data)), ScanOptions())

        assert_the_room(found.shell)
        scan = found.shell["scan"]
        assert (scan["format"], scan["units"], scan["up_axis"]) == (fmt, "m", "y")
        assert any("the file says so" in line for line in found.assumptions)

    def test_a_z_up_mesh_stood_up_by_its_node(self):
        """An app that scans Z-up writes its mesh that way and turns it with a node: -90 degrees about X."""
        vertices, faces = room_mesh()
        lying = as_scanned(vertices, 25.0, offset=(2.0, 0.5, -3.0), up="z")
        doc, data = gltf_scene([(lying, faces, {"rotation": quaternion((1.0, 0.0, 0.0), -90.0)})])

        found = extract_room(read_scan_file("club.glb", write_glb(doc, data)), ScanOptions())

        assert_the_room(found.shell)

    def test_the_same_room_as_the_obj_gives(self):
        vertices, faces = room_mesh()
        scanned = as_scanned(vertices, 25.0, offset=(2.0, 0.5, -3.0))
        doc, data = gltf_scene([(scanned, faces, {})])

        from_obj = extract_room(read_scan_file("club.obj", write_obj(scanned, faces)), ScanOptions()).shell
        from_glb = extract_room(read_scan_file("club.glb", write_glb(doc, data)), ScanOptions()).shell

        for key in ("width", "depth", "height"):
            assert from_glb["room"][key] == pytest.approx(from_obj["room"][key], abs=0.02)
        assert len(from_glb["risers"]) == len(from_obj["risers"])
        for ours, theirs in zip(from_glb["risers"], from_obj["risers"]):
            assert ours["kind"] == theirs["kind"]
            for key in ("center_x", "center_z", "width", "depth", "height"):
                assert ours[key] == pytest.approx(theirs[key], abs=0.02)
        assert len(from_glb["truss_lines"]) == len(from_obj["truss_lines"]) == 1

    def test_what_the_operator_says_still_wins_over_the_file(self):
        vertices, faces = room_mesh()
        doc, data = gltf_scene([(vertices * 100.0, faces, {})])       # an exporter that wrote centimetres
        found = extract_room(read_scan_file("club.glb", write_glb(doc, data)), ScanOptions(units="cm"))
        assert found.shell["room"]["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert any("as asked" in line for line in found.assumptions)


# ---------------------------------------------------------------------------
# What cannot be read
# ---------------------------------------------------------------------------

def refused(name: str, content: bytes) -> str:
    with pytest.raises(RoomScanError) as error:
        read_scan_file(name, content)
    return str(error.value)


class TestWhatCannotBeRead:

    @pytest.mark.parametrize("extension, word", [
        ("KHR_draco_mesh_compression", "Draco"), ("EXT_meshopt_compression", "meshopt"),
    ])
    @pytest.mark.parametrize("write, name", [(write_glb, "club.glb"), (write_gltf, "club.gltf")])
    def test_compression_says_to_export_without_it(self, extension, word, write, name):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["extensionsUsed"] = [extension]
        doc["extensionsRequired"] = [extension]
        said = refused(name, write(doc, data))
        assert word in said and "without Draco or mesh compression" in said and "OBJ" in said

    def test_draco_that_is_not_marked_required_is_still_named(self):
        """The points are only in the Draco data: the accessor has no buffer view to fall back on."""
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["extensionsUsed"] = ["KHR_draco_mesh_compression"]
        doc["meshes"][0]["primitives"][0]["extensions"] = {
            "KHR_draco_mesh_compression": {"bufferView": 0, "attributes": {"POSITION": 0}},
        }
        del doc["accessors"][0]["bufferView"]
        assert "Draco" in refused("club.glb", write_glb(doc, data))

    def test_a_required_extension_that_is_not_about_the_mesh_is_no_reason_to_refuse(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["extensionsRequired"] = ["KHR_texture_basisu"]
        doc["images"] = [{"uri": "texture.ktx2"}]
        assert len(read_scan_file("club.glb", write_glb(doc, data)).faces) == 12

    @pytest.mark.parametrize("write, name", [(write_glb, "club.glb"), (write_gltf, "club.gltf")])
    def test_a_separate_bin_file_says_to_export_glb(self, write, name):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["buffers"][0]["uri"] = "club.bin"
        said = refused(name, write(doc))
        assert "club.bin" in said and ".glb" in said and "one file" in said

    def test_sparse_and_quantised_points_are_refused_in_words(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["accessors"][0]["sparse"] = {"count": 1, "indices": {}, "values": {}}
        assert "sparse" in refused("club.glb", write_glb(doc, data))

        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["accessors"][0]["componentType"] = 5123
        said = refused("club.glb", write_glb(doc, data))
        assert "UNSIGNED_SHORT" in said and "OBJ" in said

    def test_a_file_with_no_mesh_in_it(self):
        doc = {"asset": {"version": "2.0"}, "scenes": [{"nodes": [0]}], "nodes": [{"name": "camera"}]}
        for content, name in ((write_glb(doc), "empty.glb"), (write_gltf(doc), "empty.gltf")):
            assert "no triangles or points" in refused(name, content)

    def test_an_older_gltf_and_a_file_only_named_glb(self):
        content = bytearray(small_glb())
        struct.pack_into("<I", content, 4, 1)
        assert "version 1" in refused("old.glb", bytes(content))
        assert "GLB" in refused("scan.glb", b"this is not a glb at all")

    def test_a_glb_cut_short_anywhere_is_refused_in_words(self):
        """Every length from one byte to one short of the whole file: an upload that stopped part-way."""
        whole = small_glb()
        for length in range(1, len(whole)):
            said = refused("club.glb", whole[:length])
            assert "Export" in said, length

    def test_a_glb_cut_short_whose_header_was_made_to_agree(self):
        """The same cuts with the header's length rewritten to match: a file damaged, not just short."""
        whole = small_glb()
        for length in range(12, len(whole)):
            content = bytearray(whole[:length])
            struct.pack_into("<I", content, 8, length)
            said = refused("club.glb", bytes(content))
            assert "Export" in said, length

    def test_a_gltf_cut_short_is_refused_in_words(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        whole = write_gltf(doc, data)
        for length in range(1, len(whole) - 1, 7):
            assert "cut short" in refused("club.gltf", whole[:length]), length

    def test_base64_cut_short_inside_a_gltf_that_still_parses(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        whole = json.loads(write_gltf(doc, data))
        whole["buffers"][0]["uri"] = whole["buffers"][0]["uri"][:80]
        assert "cut short" in refused("club.gltf", json.dumps(whole).encode())

    @pytest.mark.parametrize("damage", [
        lambda doc: doc.update(accessors={}),
        lambda doc: doc.update(meshes="none"),
        lambda doc: doc["meshes"][0]["primitives"][0]["attributes"].update(POSITION="0"),
        lambda doc: doc["meshes"][0]["primitives"][0].update(indices=99),
        lambda doc: doc["meshes"][0].update(primitives=[7]),
        lambda doc: doc["accessors"][0].update(bufferView=99),
        lambda doc: doc["accessors"][0].update(count=-1),
        lambda doc: doc["accessors"][0].update(count=10 ** 12),
        lambda doc: doc["accessors"][0].update(count=True),
        lambda doc: doc["accessors"][0].update(byteOffset=10 ** 6),
        lambda doc: doc["accessors"][0].update(type="VEC2"),
        lambda doc: doc["accessors"][1].update(componentType=5126),
        lambda doc: doc["bufferViews"][0].update(byteStride=4),
        lambda doc: doc["bufferViews"][0].update(byteLength=5),
        lambda doc: doc["bufferViews"][0].update(buffer=3),
        lambda doc: doc["buffers"][0].update(uri=5),
        lambda doc: doc["nodes"][0].update(mesh=7),
        lambda doc: doc["nodes"][0].update(children=[0]),
        lambda doc: doc["nodes"][0].update(children="all"),
        lambda doc: doc["nodes"][0].update(matrix=[1.0] * 15),
        lambda doc: doc["nodes"][0].update(rotation="north"),
        lambda doc: doc["nodes"][0].update(translation=[0.0, float("nan"), 0.0]),
        lambda doc: doc.update(scene=5),
        lambda doc: doc["scenes"][0].update(nodes=[42]),
    ])
    def test_a_file_that_does_not_hold_together(self, damage):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        damage(doc)
        for content, name in ((write_glb(doc, data), "club.glb"), (write_gltf(doc, data), "club.gltf")):
            assert "Export" in refused(name, content)

    def test_json_that_is_not_an_object_or_not_a_scan(self):
        assert "Export" in refused("club.gltf", b"[1, 2, 3]")
        assert "Export" in refused("club.gltf", b'{"asset": {"version": "2.0"}, "nodes": 3}')

    def test_too_many_points_or_triangles(self, monkeypatch):
        monkeypatch.setattr(gltf_reader, "MAX_VERTICES", 7)
        assert "lower detail" in refused("club.glb", small_glb())
        monkeypatch.setattr(gltf_reader, "MAX_VERTICES", 20_000_000)
        monkeypatch.setattr(gltf_reader, "MAX_FACES", 11)
        assert "lower detail" in refused("club.glb", small_glb())

    def test_a_small_file_that_draws_one_mesh_a_great_many_times(self, monkeypatch):
        """Refused from the running count, before the copies are made."""
        monkeypatch.setattr(gltf_reader, "MAX_VERTICES", 1000)
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["nodes"] += [{"mesh": 0, "translation": [float(n), 0.0, 0.0]} for n in range(1, 5000)]
        doc["scenes"][0]["nodes"] = list(range(5000))
        assert "lower detail" in refused("many.glb", write_glb(doc, data))
