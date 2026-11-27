"""
Room scan: a scan in a zip
==========================

Polycam and Scaniverse often share a scan as a zip: a .gltf with its .bin and
textures, or an .obj with its .mtl and textures. Every zip here is built in the
test with zipfile, and the ones zipfile will not write (a password, a size that
lies, a compression it does not know) are made by changing bytes of one it did.

What has to hold: the scan in the zip is the mesh the same file gives on its
own; a .gltf finds its .bin beside it, by the name it gives; one of several
models is chosen in a fixed order and the report says which; and a zip that is
not a scan export, or is built to hurt, is refused in words before it is
unpacked. Nothing is written to disk by the reader or by these tests.
"""

import io
import json
import struct
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.services.room_scan import RoomScanError, ScanOptions, detect_scan_format, extract_room, read_scan_file
from app.services.room_scan import bundle
from app.services.room_scan.bundle import MAX_ZIP_ENTRIES, PREFERENCE, parse_zip
from tests.unit.room_scan_meshes import (
    ROOM, as_scanned, box, gltf_scene, room_mesh, roomplan_json, write_glb, write_gltf, write_obj, write_ply,
    write_usda, write_zip,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "usdc"

SMALL = box(0.0, 2.0, 0.0, 1.0, 0.0, 3.0)
PNG = b"\x89PNG\r\n\x1a\n" + bytes(200)
MTL = b"newmtl wall\nKd 0.8 0.8 0.8\nmap_Kd textures/wall.png\n"


def gltf_beside(uri: str = "scene.bin", mesh=SMALL):
    """(a .gltf that names its buffer as a file, that buffer)."""
    doc, data = gltf_scene([(mesh[0], mesh[1], {})])
    doc["buffers"][0]["uri"] = uri
    return write_gltf(doc), data


def small_obj() -> bytes:
    return write_obj(*SMALL)


def refused(archive: bytes, name: str = "scan.zip", **limits) -> str:
    """The plain-words refusal of a zip: nothing but a RoomScanError, and soon."""
    started = time.perf_counter()
    with pytest.raises(RoomScanError) as error:
        if limits:
            parse_zip(archive, name, **limits)
        else:
            read_scan_file(name, archive)
    assert time.perf_counter() - started < 5.0
    return str(error.value)


# --- zips zipfile will not write -------------------------------------------

def directory_line(archive: bytes, name: str) -> int:
    """Where the zip's directory has its line for a file."""
    at = archive.find(b"PK\x01\x02")
    while at >= 0:
        (length,) = struct.unpack_from("<H", archive, at + 28)
        if archive[at + 46:at + 46 + length] == name.encode():
            return at
        at = archive.find(b"PK\x01\x02", at + 4)
    raise AssertionError(f"{name} is not in the zip")


def forged(archive: bytes, name: str, flags: int = None, method: int = None, size: int = None) -> bytes:
    """The zip with one file's flags, compression method or stated size changed, in both of its headers."""
    out = bytearray(archive)
    line = directory_line(archive, name)
    (header,) = struct.unpack_from("<I", archive, line + 42)
    assert archive[header:header + 4] == b"PK\x03\x04"
    # (offset in the directory's line, offset in the file's own header)
    for value, layout, in_line, in_header in ((flags, "<H", 8, 6), (method, "<H", 10, 8), (size, "<I", 24, 22)):
        if value is not None:
            struct.pack_into(layout, out, line + in_line, value)
            struct.pack_into(layout, out, header + in_header, value)
    return bytes(out)


# ---------------------------------------------------------------------------
# A .gltf with its .bin
# ---------------------------------------------------------------------------

class TestGltfWithItsBin:

    def test_a_gltf_and_its_bin_in_a_zip_are_the_mesh_the_glb_is(self):
        vertices, faces = room_mesh()
        doc, data = gltf_scene([(vertices, faces, {})])
        glb = read_scan_file("club.glb", write_glb(doc, data))
        doc["buffers"][0]["uri"] = "scene.bin"
        archive = write_zip([
            ("scene.gltf", write_gltf(doc)), ("scene.bin", data),
            ("textures/wall.png", PNG), ("textures/floor.jpg", b"\xff\xd8\xff" + bytes(50)),
        ])

        assert detect_scan_format("club.zip", archive) == "zip"
        mesh = read_scan_file("club.zip", archive)

        assert mesh.format == "gltf" and mesh.source_file == "club.zip"
        assert np.array_equal(mesh.vertices, glb.vertices)
        assert np.array_equal(mesh.faces, glb.faces)
        assert (mesh.up_axis, mesh.metres_per_unit) == ("y", 1.0)
        assert mesh.notes[0] == "Read 'scene.gltf' from the zip."
        # Textures are not models, and nothing is said about them.
        assert not any("also holds" in note or "png" in note for note in mesh.notes)

    def test_a_compressed_zip_reads_the_same(self):
        text, data = gltf_beside()
        stored = read_scan_file("a.zip", write_zip([("scene.gltf", text), ("scene.bin", data)]))
        packed = read_scan_file(
            "a.zip", write_zip([("scene.gltf", text), ("scene.bin", data)], compression=zipfile.ZIP_DEFLATED),
        )
        assert np.array_equal(stored.vertices, packed.vertices) and np.array_equal(stored.faces, packed.faces)

    @pytest.mark.parametrize("gltf_at, uri, bin_at", [
        ("scan/scene.gltf", "scene.bin", "scan/scene.bin"),                      # a folder round both
        ("scan/model/scene.gltf", "../buffers/scene.bin", "scan/buffers/scene.bin"),   # up and across, still inside
        ("scene.gltf", "./scene.bin", "scene.bin"),
        ("scene.gltf", "my%20scan%20%281%29.bin", "my scan (1).bin"),            # a URI is percent-encoded
        ("scene.gltf", "my scan.bin", "my scan.bin"),                            # and some apps do not encode
        ("scene.gltf", "100%25.bin", "100%.bin"),
        ("scene.gltf", "a%20b.bin", "a%20b.bin"),                                # a file really named that
        ("scene.gltf", "Scene.BIN", "scene.bin"),                                # capitals, as Windows lets off
        ("scan/scene.gltf", "buffers\\scene.bin", "scan/buffers/scene.bin"),      # a backslash from a Windows export
    ])
    def test_the_bin_is_found_by_the_name_the_gltf_gives(self, gltf_at, uri, bin_at):
        text, data = gltf_beside(uri)
        mesh = read_scan_file("scan.zip", write_zip([(gltf_at, text), (bin_at, data)]))
        assert np.allclose(mesh.vertices, SMALL[0], atol=1e-6)
        assert np.array_equal(mesh.faces, SMALL[1])
        assert mesh.notes[0] == f"Read '{gltf_at}' from the zip."

    def test_two_bin_files_are_both_fetched(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        # Points in one file, indices in another: bufferView 1 starts where the points end.
        cut = doc["bufferViews"][1]["byteOffset"]
        doc["bufferViews"][1].update(buffer=1, byteOffset=0)
        doc["buffers"] = [
            {"byteLength": cut, "uri": "points.bin"}, {"byteLength": len(data) - cut, "uri": "indices.bin"},
        ]
        archive = write_zip([("scene.gltf", write_gltf(doc)), ("points.bin", data[:cut]), ("indices.bin", data[cut:])])

        mesh = read_scan_file("scan.zip", archive)

        assert np.allclose(mesh.vertices, SMALL[0], atol=1e-6) and np.array_equal(mesh.faces, SMALL[1])

    def test_a_gltf_with_its_data_inside_it_needs_nothing_beside_it(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        whole = write_gltf(doc, data)
        in_a_zip = read_scan_file("scan.zip", write_zip([("scene.gltf", whole), ("thumb.png", PNG)]))
        alone = read_scan_file("scene.gltf", whole)
        assert np.array_equal(in_a_zip.vertices, alone.vertices) and np.array_equal(in_a_zip.faces, alone.faces)

    def test_a_glb_in_a_zip_can_keep_a_buffer_beside_it(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["buffers"][0]["uri"] = "scene.bin"
        mesh = read_scan_file("scan.zip", write_zip([("scene.glb", write_glb(doc)), ("scene.bin", data)]))
        assert mesh.format == "glb" and np.array_equal(mesh.faces, SMALL[1])

    def test_a_missing_bin_is_named(self):
        text, _ = gltf_beside("scene.bin")
        said = refused(write_zip([("scan/scene.gltf", text), ("scan/texture.png", PNG)]))
        assert "'scan/scene.gltf' in the zip could not be read" in said
        assert "needs 'scene.bin'" in said and "not in the zip" in said and ".glb" in said

    def test_a_bin_that_is_cut_short_is_refused_in_words(self):
        text, data = gltf_beside()
        said = refused(write_zip([("scene.gltf", text), ("scene.bin", data[: len(data) // 2])]))
        assert "run past the end of the data" in said

    @pytest.mark.parametrize("uri, words", [
        ("../scene.bin", "outside the zip"),
        ("../../etc/passwd", "outside the zip"),
        ("/scene.bin", "not a file in the zip"),
        ("\\\\server\\share\\scene.bin", "not a file in the zip"),
        ("C:\\scans\\scene.bin", "not a file in the zip"),
        ("file:///scene.bin", "not a file in the zip"),
        ("https://example.invalid/scene.bin", "not a file in the zip"),
    ])
    def test_a_buffer_is_never_fetched_from_outside_the_zip(self, uri, words):
        text, data = gltf_beside(uri)
        # The .bin is in the zip, beside the .gltf at the top; the .gltf points somewhere else.
        said = refused(write_zip([("scene.gltf", text), ("scene.bin", data), ("etc/passwd", data)]))
        assert words in said

    def test_a_gltf_sent_alone_with_a_bin_elsewhere_says_to_send_the_zip(self):
        text, _ = gltf_beside("scene.bin")
        with pytest.raises(RoomScanError) as error:
            read_scan_file("scene.gltf", text)
        said = str(error.value)
        assert "'scene.bin'" in said and "only one file was sent" in said
        assert "send the zip" in said and ".glb" in said and "OBJ" in said


# ---------------------------------------------------------------------------
# An .obj with its .mtl and textures, and the other formats
# ---------------------------------------------------------------------------

class TestWhatIsInTheZip:

    def test_an_obj_with_its_mtl_and_textures(self):
        vertices, faces = room_mesh()
        scanned = as_scanned(vertices, 25.0, offset=(2.0, 0.5, -3.0))
        obj = write_obj(scanned, faces)
        archive = write_zip([
            ("export/model.obj", obj), ("export/model.mtl", MTL),
            ("export/textures/wall.png", PNG), ("export/textures/floor.jpg", b"\xff\xd8\xff" + bytes(50)),
        ], compression=zipfile.ZIP_DEFLATED)

        mesh = read_scan_file("polycam.zip", archive)
        alone = read_scan_file("model.obj", obj)

        assert mesh.format == "obj"
        assert np.array_equal(mesh.vertices, alone.vertices) and np.array_equal(mesh.faces, alone.faces)
        assert mesh.notes == ["Read 'export/model.obj' from the zip."]

        # And the room in it is the room the .obj gives, with the zip named as where it came from.
        found = extract_room(mesh, ScanOptions())
        expected = extract_room(alone, ScanOptions())
        assert found.shell["room"] == expected.shell["room"]
        assert found.shell["room"]["width"] == pytest.approx(ROOM["width"], abs=0.1)
        assert found.shell["risers"] == expected.shell["risers"]
        assert found.shell["scan"]["file"] == "polycam.zip" and found.shell["scan"]["format"] == "obj"
        assert "Read 'export/model.obj' from the zip." in found.assumptions

    @pytest.mark.parametrize("name, fmt", [
        ("room.glb", "glb"), ("room.gltf", "gltf"), ("room.usdz", "usda"), ("room.usdc", "usdc"),
        ("room.usda", "usda"), ("room.obj", "obj"), ("room.ply", "ply"), ("room.json", "roomplan"),
    ])
    def test_each_kind_of_scan_is_read_from_a_zip(self, name, fmt):
        mesh = read_scan_file("scan.zip", write_zip([("notes.txt", b"scanned on a phone"), (name, MODELS[name])]))
        assert mesh.format == fmt
        assert mesh.notes[0] == f"Read '{name}' from the zip."

    def test_a_usdz_given_the_name_zip_is_still_read(self):
        """A USDZ is a zip of a USD layer and its textures: named .zip, the layer in it is the scan."""
        archive = write_zip([("Room.usdc", (FIXTURES / "room_y_metres.usdc").read_bytes()), ("0/tex.png", PNG)])
        as_usdz = read_scan_file("Room.usdz", archive)
        as_zip = read_scan_file("Room.zip", archive)
        assert as_zip.format == as_usdz.format == "usdc"
        assert np.array_equal(as_zip.vertices, as_usdz.vertices)

    def test_an_archive_named_usdz_goes_where_it_always_did(self):
        text, data = gltf_beside()
        archive = write_zip([("scene.gltf", text), ("scene.bin", data)])
        assert detect_scan_format("Room.usdz", archive) == "usdz"
        assert detect_scan_format("Room.USDZ", archive) == "usdz"
        for name in ("Room.zip", "Room.ZIP", "Room", "Room.bin"):
            assert detect_scan_format(name, archive) == "zip"
        with pytest.raises(RoomScanError, match="USDZ holds no USD layer"):
            read_scan_file("Room.usdz", archive)

    def test_a_binary_layer_named_usda_is_read_by_its_first_bytes(self):
        archive = write_zip([("room.usda", (FIXTURES / "room_y_metres.usdc").read_bytes())])
        assert read_scan_file("scan.zip", archive).format == "usdc"

    def test_a_layer_named_usd_is_read_whichever_form_it_is(self):
        """As it was when every archive went to the USDZ reader, which takes a .usd of either form."""
        text = write_zip([("room.usd", write_usda(*SMALL).encode())])
        binary = write_zip([("room.usd", (FIXTURES / "room_y_metres.usdc").read_bytes())])
        assert read_scan_file("Room.zip", text).format == "usda"
        assert read_scan_file("Room.zip", binary).format == "usdc"
        assert read_scan_file("Room", text).notes[0] == "Read 'room.usd' from the zip."

    def test_a_gltf_named_json_is_read_with_its_bin(self):
        text, data = gltf_beside()
        mesh = read_scan_file("scan.zip", write_zip([("scene.json", text), ("scene.bin", data)]))
        assert mesh.format == "gltf" and np.array_equal(mesh.faces, SMALL[1])

    def test_a_zip_inside_the_zip_is_not_opened(self):
        inner = write_zip([("model.obj", small_obj())])
        said = refused(write_zip([("inner.zip", inner)]))
        assert "holds no scan this can read" in said and "'inner.zip'" in said

    def test_a_model_that_is_itself_an_archive_is_not_read_as_one(self):
        """A file named .glb that holds a zip goes to the GLB reader and is refused there: no way back in."""
        inner = write_zip([("model.obj", small_obj())])
        said = refused(write_zip([("model.glb", inner)]))
        assert "'model.glb' in the zip could not be read" in said and "named as a GLB" in said


def _usdz() -> bytes:
    return write_zip([("room.usda", write_usda(*SMALL).encode())])


def _models() -> dict:
    doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
    return {
        "room.glb": write_glb(doc, data),
        "room.gltf": write_gltf(doc, data),
        "room.usdz": _usdz(),
        "room.usdc": (FIXTURES / "room_y_metres.usdc").read_bytes(),
        "room.usda": write_usda(*SMALL).encode(),
        "room.obj": small_obj(),
        "room.ply": write_ply(*SMALL),
        "room.json": roomplan_json(),
    }


MODELS = _models()


# ---------------------------------------------------------------------------
# Several models
# ---------------------------------------------------------------------------

class TestWhichModel:

    def test_the_order_is_the_one_the_doc_gives(self):
        assert PREFERENCE == ("glb", "gltf", "usdz", "usdc", "usda", "obj", "ply", "json")
        assert list(MODELS) == [f"room.{kind}" for kind in PREFERENCE]

    @pytest.mark.parametrize("first, second", list(zip(list(MODELS), list(MODELS)[1:])))
    def test_of_two_models_the_one_earlier_in_the_order_is_read(self, first, second):
        # The later one comes first in the archive, so the archive's order is not what decides.
        mesh = read_scan_file("scan.zip", write_zip([(second, MODELS[second]), (first, MODELS[first])]))
        assert mesh.notes[0] == f"Read '{first}' from the zip."
        assert f"The zip also holds '{second}', which was not read" in mesh.notes[1]

    def test_all_of_them_at_once(self):
        archive = write_zip([(name, MODELS[name]) for name in reversed(list(MODELS))])
        mesh = read_scan_file("scan.zip", archive)
        assert mesh.format == "glb"
        assert mesh.notes[0] == "Read 'room.glb' from the zip."
        # The others in the order they would have been tried, the first five by name.
        assert mesh.notes[1].startswith(
            "The zip also holds 'room.gltf', 'room.usdz', 'room.usdc', 'room.usda', 'room.obj' and 2 more, "
            "which were not read"
        )

    def test_of_two_of_a_kind_the_one_nearer_the_top_then_the_first_in_the_zip(self):
        far = write_obj(*box(0.0, 9.0, 0.0, 1.0, 0.0, 3.0))
        archive = write_zip([("a/b/deep.obj", far), ("second.obj", far), ("a/mid.obj", far)])
        assert read_scan_file("s.zip", archive).notes[0] == "Read 'second.obj' from the zip."
        archive = write_zip([("z.obj", small_obj()), ("a.obj", far)])
        mesh = read_scan_file("s.zip", archive)
        assert mesh.notes[0] == "Read 'z.obj' from the zip." and mesh.vertices[:, 0].max() == 2.0

    def test_a_model_that_cannot_be_read_gives_way_to_the_next(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["extensionsUsed"] = doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]
        archive = write_zip([("scan.glb", write_glb(doc, data)), ("scan.obj", small_obj()), ("scan.ply", MODELS["room.ply"])])

        mesh = read_scan_file("scan.zip", archive)

        assert mesh.format == "obj"
        assert mesh.notes[0] == "Read 'scan.obj' from the zip."
        assert mesh.notes[1].startswith("'scan.glb' in the zip was tried first and could not be read.")
        assert "Draco" in mesh.notes[1]
        assert "also holds 'scan.ply'" in mesh.notes[2] and "scan.glb" not in mesh.notes[2]

    def test_a_gltf_without_its_bin_gives_way_to_the_obj_beside_it(self):
        text, _ = gltf_beside("scene.bin")
        mesh = read_scan_file("scan.zip", write_zip([("scene.gltf", text), ("scene.obj", small_obj())]))
        assert mesh.format == "obj" and "needs 'scene.bin'" in mesh.notes[1]

    def test_when_none_can_be_read_the_first_one_tried_says_why(self):
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        doc["extensionsUsed"] = doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]
        said = refused(write_zip([("scan.obj", b"# nothing in it\n"), ("scan.glb", write_glb(doc, data))]))
        assert said.startswith("'scan.glb' in the zip could not be read.") and "Draco" in said

    def test_an_empty_model_is_said_to_be_empty(self):
        assert "'scan.obj' in the zip could not be read. The file is empty." == refused(write_zip([("scan.obj", b"")]))

    def test_an_apps_own_json_is_not_taken_for_the_scan(self):
        notes = json.dumps({"app": "Polycam", "captured": "2026-11-20", "frames": 412}).encode()
        mesh = read_scan_file("scan.zip", write_zip([("mesh_info.json", notes), ("model.obj", small_obj())]))
        assert mesh.notes == ["Read 'model.obj' from the zip."]

        said = refused(write_zip([("mesh_info.json", notes), ("thumb.png", PNG)]))
        assert "holds no scan this can read" in said
        assert ".glb" in said and "RoomPlan .json" in said and "'mesh_info.json' and 'thumb.png'" in said

    def test_a_roomplan_json_beside_a_model_is_named_as_left_alone(self):
        mesh = read_scan_file("scan.zip", write_zip([("Room.json", roomplan_json()), ("Room.obj", small_obj())]))
        assert mesh.format == "obj" and "also holds 'Room.json'" in mesh.notes[1]


# ---------------------------------------------------------------------------
# What macOS and other tools leave in a zip
# ---------------------------------------------------------------------------

class TestJunk:

    def test_macos_copies_and_hidden_files_are_not_the_scan_and_not_mentioned(self):
        text, data = gltf_beside()
        archive = write_zip([
            ("__MACOSX/._scene.gltf", b"\x00\x05\x16\x07" + bytes(60)),
            ("__MACOSX/scan/._model.obj", b"\x00\x05\x16\x07" + bytes(60)),
            ("__MACOSX/scan/model.glb", b"not a glb"),
            (".DS_Store", bytes(40)),
            ("scan/.DS_Store", bytes(40)),
            ("scan/._scene.gltf", b"\x00\x05\x16\x07" + bytes(60)),
            (".cache/old.obj", small_obj()),
            ("scan/scene.gltf", text), ("scan/scene.bin", data),
            ("Thumbs.db", bytes(30)), ("scan/", b""),
        ])

        mesh = read_scan_file("scan.zip", archive)

        assert mesh.format == "gltf" and np.array_equal(mesh.faces, SMALL[1])
        assert mesh.notes[0] == "Read 'scan/scene.gltf' from the zip."
        assert not any("also holds" in note or "MACOSX" in note for note in mesh.notes)

    def test_a_zip_of_nothing_but_junk_holds_no_scan(self):
        said = refused(write_zip([("__MACOSX/._a.obj", small_obj()), (".hidden.obj", small_obj())]))
        assert "The zip is empty" in said
        assert "The zip is empty" in refused(write_zip([]))
        assert "The zip is empty" in refused(write_zip([("scan/", b"")]))

    def test_a_bin_is_not_fetched_from_a_hidden_folder(self):
        text, data = gltf_beside("scene.bin")
        said = refused(write_zip([("scene.gltf", text), ("__MACOSX/scene.bin", data), (".scene.bin", data)]))
        assert "needs 'scene.bin'" in said


# ---------------------------------------------------------------------------
# A zip that is not what it says
# ---------------------------------------------------------------------------

class TestNamesThatPointOutside:

    @pytest.mark.parametrize("name", [
        "../evil.obj", "scan/../../evil.obj", "scan/..", "/etc/evil.obj", "C:/scans/evil.obj",
        "..\\evil.obj", "\\\\server\\share\\evil.obj", "c:evil.obj",
    ])
    def test_such_a_name_refuses_the_whole_zip(self, name):
        # With a good scan beside it: nothing of such a zip is read.
        said = refused(write_zip([("model.obj", small_obj()), (name, b"v 0 0 0\n")]))
        assert "points outside the zip" in said and "nothing in it was read" in said

    def test_two_dots_inside_a_name_are_only_a_name(self):
        mesh = read_scan_file("s.zip", write_zip([("my..scan/model..v2.obj", small_obj())]))
        assert mesh.notes[0] == "Read 'my..scan/model..v2.obj' from the zip."


class TestTooManyFiles:

    def test_the_most_files_a_zip_may_hold(self):
        files = [(f"textures/{n}.png", b"") for n in range(MAX_ZIP_ENTRIES - 1)]
        at_the_limit = write_zip(files + [("model.obj", small_obj())])
        assert read_scan_file("s.zip", at_the_limit).format == "obj"

        over = write_zip(files + [("model.obj", small_obj()), ("one_more.png", b"")])
        said = refused(over)
        assert f"more than {MAX_ZIP_ENTRIES:,} files" in said and "not a scan export" in said

    def test_the_limit_can_be_set(self):
        archive = write_zip([("model.obj", small_obj()), ("a.png", PNG), ("b.png", PNG)])
        assert parse_zip(archive, "s.zip", max_entries=3).format == "obj"
        assert "more than 2 files" in refused(archive, max_entries=2)

    def test_a_count_in_the_last_record_is_believed_before_the_list_is_read(self, monkeypatch):
        archive = bytearray(write_zip([("model.obj", small_obj())]))
        end = archive.rfind(b"PK\x05\x06")
        assert bundle._directory(bytes(archive)) == (1, struct.unpack_from("<I", archive, end + 12)[0])
        struct.pack_into("<HH", archive, end + 8, 60000, 60000)

        def never(*args, **kwargs):
            raise AssertionError("the zip was opened")

        monkeypatch.setattr(bundle.zipfile, "ZipFile", never)
        assert "more than" in refused(bytes(archive), max_entries=MAX_ZIP_ENTRIES)

    def test_a_directory_too_long_for_its_files_is_refused_before_it_is_read(self, monkeypatch):
        # Three files whose names alone come to more than three files' share of a directory.
        archive = write_zip([(f"{'n' * 5000}{n}.png", b"") for n in range(3)])
        monkeypatch.setattr(bundle.zipfile, "ZipFile", lambda *a, **k: pytest.fail("the zip was opened"))
        assert "more than 3 files" in refused(archive, max_entries=3)

    def test_a_zip_of_more_files_than_the_short_record_can_count(self):
        """Past 65,535 files the count is in the longer (zip64) record, which is read too."""
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
            for n in range(65_540):
                archive.writestr(f"{n}.png", b"")
        content = out.getvalue()
        files, size = bundle._directory(content)
        assert files == 65_540 and size > 65_540 * 46
        assert "more than" in refused(content)


class TestTooBig:

    def test_what_the_zip_says_it_unpacks_to_is_added_up_before_anything_is_unpacked(self, monkeypatch):
        obj = small_obj()
        # Five megabytes of nothing pack down to a few kilobytes.
        archive = write_zip([("model.obj", obj), ("textures/big.png", bytes(5_000_000))], zipfile.ZIP_DEFLATED)
        assert len(archive) < 20_000

        monkeypatch.setattr(bundle._Zip, "read", lambda *a, **k: pytest.fail("a file was unpacked"))
        said = refused(archive, max_bytes=1024 * 1024)
        assert "unpacks to more than 1 MB" in said and "lower detail" in said

    def test_the_limit_is_on_every_file_together_and_is_exact(self):
        obj = small_obj()
        archive = write_zip([("model.obj", obj), ("a.png", bytes(1000)), ("__MACOSX/._a.png", bytes(1000))])
        total = len(obj) + 2000
        assert parse_zip(archive, "s.zip", max_bytes=total).format == "obj"
        assert f"unpacks to more than {total - 1:,} bytes" in refused(archive, max_bytes=total - 1)

    def test_the_limit_is_the_upload_limit(self):
        from app.api.endpoints import room_scan
        from app.services.room_scan.mesh import MAX_UPLOAD_BYTES

        assert room_scan.MAX_UPLOAD_BYTES == MAX_UPLOAD_BYTES == 200 * 1024 * 1024
        assert parse_zip.__defaults__ == ("", MAX_UPLOAD_BYTES, MAX_ZIP_ENTRIES)

    @pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
    def test_a_file_that_holds_more_than_the_zip_says_is_not_unpacked_past_what_it_says(self, compression):
        """The swollen zip: a file said to be a few bytes that unpacks to megabytes."""
        swollen = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n" + b"# padding\n" * 300_000
        archive = forged(write_zip([("model.obj", swollen)], compression), "model.obj", size=32)
        said = refused(archive, max_bytes=1024)
        assert "The zip is damaged" in said and "'model.obj'" in said

    @pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
    def test_a_file_that_holds_less_than_the_zip_says_is_refused(self, compression):
        obj = small_obj()
        archive = forged(write_zip([("model.obj", obj)], compression), "model.obj", size=len(obj) + 500)
        said = refused(archive)
        assert "The zip is damaged" in said and "'model.obj'" in said

    def test_many_names_for_one_file_are_unpacked_once(self):
        """Every directory line pointing at the same packed bytes: the sizes are still added up for each."""
        archive = bytearray(write_zip([("a.obj", small_obj()), ("b.obj", small_obj())]))
        first, second = directory_line(bytes(archive), "a.obj"), directory_line(bytes(archive), "b.obj")
        archive[second + 42:second + 46] = archive[first + 42:first + 46]
        said = refused(bytes(archive), max_bytes=len(small_obj()) * 2 - 1)
        assert "unpacks to more than" in said


class TestLockedOrBroken:

    def test_a_password_refuses_the_zip(self):
        archive = forged(write_zip([("model.obj", small_obj()), ("a.png", PNG)]), "a.png", flags=0x1)
        said = refused(archive)
        assert "locked with a password" in said and "'a.png' is encrypted" in said and "without a password" in said

    def test_a_compression_this_cannot_unpack_is_said(self):
        archive = forged(write_zip([("model.obj", small_obj())]), "model.obj", method=99)
        said = refused(archive)
        assert "'model.obj' is packed in the zip in a way this cannot unpack" in said and "deflate" in said

    def test_a_texture_packed_some_other_way_does_not_matter(self):
        archive = forged(write_zip([("model.obj", small_obj()), ("a.png", PNG)]), "a.png", method=99)
        assert read_scan_file("s.zip", archive).format == "obj"

    def test_something_that_only_starts_like_a_zip(self):
        assert "damaged or cut short" in refused(b"PK\x03\x04 not really a zip")
        assert "damaged or cut short" in refused(b"PK\x05\x06" + bytes(10))
        # Named a zip, with its first bytes gone: still said to be a damaged zip, not "not a scan".
        whole = write_zip([("model.obj", small_obj())])
        assert detect_scan_format("scan.zip", b"\x00\x00" + whole[2:]) == "zip"
        assert "damaged or cut short" in refused(bytes(40))
        # What it holds still decides where it can: a GLB that was given the wrong name is a GLB.
        doc, data = gltf_scene([(SMALL[0], SMALL[1], {})])
        assert read_scan_file("scan.zip", write_glb(doc, data)).format == "glb"

    def test_a_zip_cut_short_anywhere_is_refused_in_words(self):
        text, data = gltf_beside()
        whole = write_zip([("scene.gltf", text), ("scene.bin", data), ("a.png", PNG)], zipfile.ZIP_DEFLATED)
        for length in range(4, len(whole), 7):
            refused(whole[:length])

    def test_a_changed_byte_in_the_scan_is_caught(self):
        obj = small_obj()
        archive = bytearray(write_zip([("model.obj", obj)]))
        at = archive.find(obj) + 20
        archive[at] ^= 0x01
        said = refused(bytes(archive))
        assert "The zip is damaged: 'model.obj' could not be unpacked" in said

    def test_bytes_changed_at_random_never_get_past_the_refusal(self):
        text, data = gltf_beside()
        whole = write_zip([("scan/scene.gltf", text), ("scan/scene.bin", data), ("a.png", PNG)], zipfile.ZIP_DEFLATED)
        rng = np.random.default_rng(26)
        for _ in range(400):
            damaged = bytearray(whole)
            for at in rng.integers(0, len(whole), size=int(rng.integers(1, 6))):
                damaged[at] = int(rng.integers(0, 256))
            try:
                read_scan_file("scan.zip", bytes(damaged))
            except RoomScanError:
                pass
