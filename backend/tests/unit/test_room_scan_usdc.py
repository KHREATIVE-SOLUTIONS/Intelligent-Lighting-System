"""
Room scan: binary USD (USDC, the "crate" format)
================================================

The files in tests/fixtures/usdc were written by Pixar's own USD library
(make_usdc_fixtures.py, run by hand outside the venv), and each has a JSON
beside it with the world-space points, the triangles, the up axis and the
units that Pixar's library computes from it. The reader here is pure Python,
so what has to hold is that it gets Pixar's numbers.

Then: the room found in a binary layer is the room found in the same stage
written as text; the two unpackers (LZ4 and USD's integer coding) against
bytes laid out by hand; value encodings no fixture holds, laid out by hand
from the format as crateFile.cpp describes it (these pin what the reader does,
not what Pixar's library does); and files that are cut short, damaged or
built to waste time, which must all be refused in plain words and quickly.
"""

import json
import random
import struct
import time
from pathlib import Path

import numpy as np
import pytest

from app.services.room_scan import RoomScanError, detect_scan_format, read_scan_file
from app.services.room_scan import usdc
from app.services.room_scan.usdc import (
    decode_integers, decompress, decompress_integers, lz4_block, parse_usdc,
)
from tests.unit.room_scan_meshes import as_scanned, room_mesh, roomplan_json, write_usda, write_zip
from tests.unit.test_room_scan import assert_the_room, scan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "usdc"
LAYERS = [
    "room_y_metres.usdc", "room_y_metres_v0_7_0.usdc", "room_y_metres_v0_10_0.usdc",
    "room_z_cm.usdc", "big_room_ring.usdc", "roomplan_like.usdz",
]


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def pixar(name: str) -> dict:
    return json.loads((FIXTURES / (name.rsplit(".", 1)[0] + ".json")).read_text())


# ---------------------------------------------------------------------------
# Against Pixar's numbers
# ---------------------------------------------------------------------------

class TestAgainstPixar:

    @pytest.mark.parametrize("name", LAYERS)
    def test_points_faces_axes_and_units_are_what_pixar_computes(self, name):
        truth = pixar(name)
        mesh = read_scan_file(name, fixture(name))

        assert mesh.format == "usdc"
        assert mesh.vertices.shape == (len(truth["points"]), 3)
        assert np.allclose(mesh.vertices, np.array(truth["points"]), atol=1e-4)
        # Meshes are read in the order USD walks the stage, so the triangles are in Pixar's order too.
        assert mesh.faces.tolist() == truth["faces"]
        assert mesh.up_axis == truth["up_axis"]
        assert mesh.metres_per_unit == pytest.approx(truth["metres_per_unit"])
        assert any(f"Read {len(truth['meshes'])} mesh" in note for note in mesh.notes)

    @pytest.mark.parametrize("name, version", [
        ("room_y_metres_v0_7_0.usdc", "0.7.0"), ("room_y_metres.usdc", "0.8.0"),
        ("room_y_metres_v0_10_0.usdc", "0.10.0"),
    ])
    def test_the_crate_version_is_in_the_notes(self, name, version):
        mesh = parse_usdc(fixture(name), name)
        assert any(f"crate version {version}" in note for note in mesh.notes)
        assert mesh.source_file == name

    def test_a_binary_file_is_known_by_its_first_bytes(self):
        content = fixture("room_y_metres.usdc")
        assert detect_scan_format("room.usdc", content) == "usdc"
        # USD lets a binary layer be called .usd, and an app may call it anything.
        assert read_scan_file("room.usd", content).format == "usdc"
        assert read_scan_file("export.bin", content).format == "usdc"

    def test_a_roomplan_shaped_usdz_is_read_prim_by_prim(self):
        """Four walls placed by 4x4 matrices, a quad floor by translate and scale,
        a table by translate, orient, scale and rotateXYZ."""
        mesh = read_scan_file("Room.usdz", fixture("roomplan_like.usdz"))
        truth = pixar("roomplan_like.usdz")

        assert len(truth["meshes"]) == 6
        assert any("Read 6 meshes" in note for note in mesh.notes)
        assert any("roomplan_like.usdc" in note and "inside the USDZ" in note for note in mesh.notes)
        # The floor is one four-sided face, cut in two round its first corner.
        floor = 4 * 8                                   # after four walls of eight corners each
        assert [floor, floor + 1, floor + 2] in mesh.faces.tolist()
        assert [floor, floor + 2, floor + 3] in mesh.faces.tolist()
        # The table: a unit box made 6 x 1 x 3, turned 30 degrees about the upright, at (0, 0.5, -3).
        table = mesh.vertices[floor + 4:]
        assert np.allclose(table.mean(axis=0), [0.0, 0.5, -3.0], atol=1e-5)
        edge = table[4] - table[0]                      # along the box's own x, 6 m long
        assert np.linalg.norm(edge) == pytest.approx(6.0, abs=1e-5)
        assert abs(edge[2]) == pytest.approx(3.0, abs=1e-4)      # 6 sin 30

    def test_roomplan_json_in_the_usdz_is_still_preferred(self):
        archive = write_zip([("room.usdc", fixture("room_y_metres.usdc")), ("room.json", roomplan_json())])
        assert read_scan_file("Room.usdz", archive).format == "roomplan"

    def test_the_first_binary_layer_that_holds_a_mesh_is_read_and_the_note_says_others_were_not(self):
        archive = write_zip([
            ("root.usdc", b"PXR-USDC" + bytes(64)), ("geometry/room.usdc", fixture("room_y_metres.usdc")),
        ])
        mesh = read_scan_file("Room.usdz", archive)
        assert mesh.format == "usdc"
        assert any("geometry/room.usdc" in note for note in mesh.notes)
        assert any("2 USD layers" in note and "only that one was read" in note for note in mesh.notes)


# ---------------------------------------------------------------------------
# The room
# ---------------------------------------------------------------------------

class TestTheRoom:

    def test_metres_y_up_gives_the_room_the_text_layer_gives(self):
        vertices, faces = room_mesh()
        text = write_usda(vertices, faces, translate=(10.0, 0.0, -2.0)).encode()

        binary_mesh = read_scan_file("room.usdc", fixture("room_y_metres.usdc"))
        text_mesh = read_scan_file("room.usda", text)
        assert np.allclose(binary_mesh.vertices, text_mesh.vertices, atol=1e-4)
        assert np.array_equal(binary_mesh.faces, text_mesh.faces)
        assert (binary_mesh.up_axis, binary_mesh.metres_per_unit) == (text_mesh.up_axis, text_mesh.metres_per_unit)

        found = scan(fixture("room_y_metres.usdc"), "room.usdc")
        same = scan(text, "room.usda")
        assert found.shell["scan"]["units"] == "m" and found.shell["scan"]["up_axis"] == "y"
        assert any("the file says so" in line for line in found.assumptions)
        assert_the_room(found.shell)
        assert found.shell["room"] == same.shell["room"]
        assert found.shell["risers"] == same.shell["risers"]
        assert found.shell["truss_lines"] == same.shell["truss_lines"]

    def test_centimetres_z_up_gives_the_room_the_text_layer_gives(self):
        vertices, faces = room_mesh()
        placed = as_scanned(vertices, 0.0, up="z", units_per_metre=100.0)
        text = write_usda(placed, faces, up="Z", metres_per_unit=0.01).encode()

        found = scan(fixture("room_z_cm.usdc"), "room.usdc")
        same = scan(text, "room.usda")
        assert found.shell["scan"]["units"] == "cm" and found.shell["scan"]["up_axis"] == "z"
        assert_the_room(found.shell)
        assert found.shell["room"] == same.shell["room"]
        assert found.shell["risers"] == same.shell["risers"]

    @pytest.mark.parametrize("name", ["room_y_metres_v0_7_0.usdc", "room_y_metres_v0_10_0.usdc"])
    def test_other_crate_versions_give_the_same_room(self, name):
        assert_the_room(scan(fixture(name), name).shell)

    def test_a_roomplan_shaped_usdz_gives_a_room_twelve_by_nine(self):
        found = scan(fixture("roomplan_like.usdz"), "Room.usdz")
        room = found.shell["room"]
        # Walls 0.1 m thick about a 12 x 9 m outline, 4 m high, with no ceiling in the file.
        assert room["width"] == pytest.approx(12.0, abs=0.2)
        assert room["depth"] == pytest.approx(9.0, abs=0.2)
        assert room["height"] == pytest.approx(4.0, abs=0.2)
        # The table, a metre high, is the one raised area.
        assert [r["height"] for r in found.shell["risers"]] == pytest.approx([1.0], abs=0.06)


# ---------------------------------------------------------------------------
# LZ4
# ---------------------------------------------------------------------------

def as_literals(data: bytes) -> bytes:
    """An LZ4 block that holds `data` as it is: one run of literals."""
    count = len(data)
    if count < 15:
        return bytes([count << 4]) + data
    head = bytes([0xF0])
    rest = count - 15
    while rest >= 255:
        head += b"\xff"
        rest -= 255
    return head + bytes([rest]) + data


class TestLz4:

    def test_literals_only(self):
        assert lz4_block(b"\x50hello", 100) == b"hello"

    def test_a_match_copies_from_what_was_written(self):
        # "abcd", then 4 bytes from 4 back, then "!" to end on.
        assert lz4_block(b"\x40abcd\x04\x00" + b"\x10!", 100) == b"abcdabcd!"

    def test_a_match_that_overlaps_its_own_output_repeats(self):
        # Two literals, then ten bytes from two back: eight of those ten did not exist when the copy began.
        assert lz4_block(b"\x26ab\x02\x00" + b"\x10c", 100) == b"ab" + b"ab" * 5 + b"c"

    def test_a_run_of_one_byte_with_a_long_match_length(self):
        # One literal, then a match one back, 15 + 5 + 4 long: 25 of the same byte.
        assert lz4_block(b"\x1fx\x01\x00\x05" + b"\x00", 100) == b"x" * 25

    def test_a_long_run_of_literals(self):
        data = bytes(range(256)) * 2
        assert lz4_block(as_literals(data), 1000) == data

    @pytest.mark.parametrize("label, block", [
        ("nothing", b""),
        ("a distance of zero", b"\x10a\x00\x00\x10b"),
        ("a distance back past the start", b"\x10a\x05\x00\x10b"),
        ("literals that are not there", b"\x90abc"),
        ("a match with no distance", b"\x10a\x01"),
        ("a length that never ends", b"\xf0\xff\xff"),
    ])
    def test_a_broken_block_is_refused(self, label, block):
        with pytest.raises(RoomScanError):
            lz4_block(block, 100)

    def test_a_block_that_unpacks_past_its_limit_is_refused(self):
        with pytest.raises(RoomScanError):
            lz4_block(b"\x1fx\x01\x00\x05" + b"\x00", 24)
        with pytest.raises(RoomScanError):
            lz4_block(b"\x50hello", 4)

    def test_one_chunk_and_several(self):
        assert decompress(b"\x00" + b"\x50hello", 100) == b"hello"
        first, second = b"\x50hello", b"\x26ab\x02\x00\x10c"
        packed = b"\x02" + struct.pack("<i", len(first)) + first + struct.pack("<i", len(second)) + second
        assert decompress(packed, 100) == b"hello" + b"ab" * 6 + b"c"

    @pytest.mark.parametrize("label, packed", [
        ("nothing", b""),
        ("a chunk with no length", b"\x01\x05\x00"),
        ("a chunk longer than what is left", b"\x01" + struct.pack("<i", 50) + b"\x50hello"),
        ("a chunk of negative length", b"\x01" + struct.pack("<i", -1) + b"\x50hello"),
    ])
    def test_broken_chunks_are_refused(self, label, packed):
        with pytest.raises(RoomScanError):
            decompress(packed, 100)

    def test_a_small_block_cannot_claim_a_huge_size(self):
        """A few bytes that say they unpack to gigabytes are held to what a few bytes could hold."""
        zeros = b"\x00" + b"\x1f\x00\x01\x00" + b"\xff" * 4000 + b"\x00" + b"\x00"   # about a megabyte of zeros
        started = time.perf_counter()
        with pytest.raises(RoomScanError):
            decompress(zeros[:200], 1 << 40)
        assert len(decompress(zeros, 1 << 40)) == 1 + 15 + 4000 * 255 + 4
        assert time.perf_counter() - started < 2.0


# ---------------------------------------------------------------------------
# USD's integer coding
# ---------------------------------------------------------------------------

# 10, 11, 12, 13, 1000, 1001, -5, 70000 as differences from the one before:
# 10, 1, 1, 1, 987, 1, -1006, 70005. The common difference is 1 (code 0); 10
# fits a byte (code 1), 987 and -1006 two bytes (code 2), 70005 four (code 3).
NARROW = (
    struct.pack("<i", 1)
    + bytes([0b00_00_00_01, 0b11_10_00_10])            # codes, four to a byte, the first in the low bits
    + struct.pack("<b", 10) + struct.pack("<h", 987) + struct.pack("<h", -1006) + struct.pack("<i", 70005)
)
NARROW_VALUES = [10, 11, 12, 13, 1000, 1001, -5, 70000]

# The 64-bit coding: two, four and eight bytes for codes 1, 2 and 3.
WIDE = (
    struct.pack("<q", 1)
    + bytes([0b11_00_00_11, 0b00_00_01_10])
    + struct.pack("<q", 5_000_000_000) + struct.pack("<q", -5_000_000_000)
    + struct.pack("<i", 40_000) + struct.pack("<h", -300)
)
WIDE_VALUES = [5_000_000_000, 5_000_000_001, 5_000_000_002, 2, 40_002, 39_702]


class TestIntegerCoding:

    def test_thirty_two_bit(self):
        values = decode_integers(NARROW, 8)
        assert values.dtype == np.dtype("<i4")
        assert values.tolist() == NARROW_VALUES

    def test_sixty_four_bit(self):
        values = decode_integers(WIDE, 6, wide=True)
        assert values.dtype == np.dtype("<i8")
        assert values.tolist() == WIDE_VALUES

    def test_every_number_the_common_difference(self):
        # 3, 6, 9 ...: nothing but the common difference and a byte of zero codes for every four.
        assert decode_integers(struct.pack("<i", 3) + bytes(3), 10).tolist() == list(range(3, 33, 3))

    def test_sums_wrap_round_as_they_do_in_usd(self):
        # An unsigned index table is stored as signed numbers: 4294967295 is a difference of -1.
        encoded = struct.pack("<i", 0) + bytes([0b00_00_01_11]) + struct.pack("<i", 2147483647) + struct.pack("<b", 1)
        values = decode_integers(encoded, 3)
        assert values.tolist() == [2147483647, -2147483648, -2147483648]
        assert decode_integers(struct.pack("<i", -1) + bytes(1), 1).view("<u4").tolist() == [4294967295]

    def test_none(self):
        assert len(decode_integers(b"", 0)) == 0
        assert len(decompress_integers(b"", 0, wide=True)) == 0

    def test_more_numbers_than_one_block_of_work(self):
        count = usdc._INTEGER_BLOCK + 10
        # Every one a difference of 1 but the last, which is a two-byte 500.
        codes = bytearray((count * 2 + 7) // 8)
        codes[(count - 1) // 4] |= 2 << (2 * ((count - 1) % 4))
        values = decode_integers(struct.pack("<i", 1) + bytes(codes) + struct.pack("<h", 500), count)
        assert values[:3].tolist() == [1, 2, 3]
        assert values[-2:].tolist() == [count - 1, count - 1 + 500]

    def test_packed_then_unpacked(self):
        assert decompress_integers(b"\x00" + as_literals(NARROW), 8).tolist() == NARROW_VALUES
        assert decompress_integers(b"\x00" + as_literals(WIDE), 6, wide=True).tolist() == WIDE_VALUES

    @pytest.mark.parametrize("label, encoded, count", [
        ("no room for the codes", struct.pack("<i", 1), 8),
        ("cut off in the differences", NARROW[:-2], 8),
        ("no common difference", b"\x01\x00", 1),
    ])
    def test_a_short_block_is_refused(self, label, encoded, count):
        with pytest.raises(RoomScanError):
            decode_integers(encoded, count)

    def test_a_count_the_bytes_could_not_hold_is_refused_before_anything_is_made(self):
        started = time.perf_counter()
        with pytest.raises(RoomScanError):
            decompress_integers(b"\x00" + as_literals(NARROW), 50_000_000)
        with pytest.raises(RoomScanError):
            decompress_integers(b"\x00" + as_literals(NARROW), 1 << 60)
        assert time.perf_counter() - started < 1.0


# ---------------------------------------------------------------------------
# Values no fixture holds, laid out by hand
# ---------------------------------------------------------------------------

def bare_crate(data: bytes, version=(0, 8, 0), tokens=("zero", "one", "two")):
    """A crate with no tables, to ask for values out of bytes laid out here."""
    crate = object.__new__(usdc._Crate)
    crate.data, crate.size, crate.version = data, len(data), version
    crate.tokens, crate.strings = list(tokens), [2, 0]
    return crate


def rep(kind: int, payload: int, array=False, inlined=False, packed=False) -> int:
    return (int(array) << 63) | (int(inlined) << 62) | (int(packed) << 61) | (kind << 48) | payload


def small(*numbers: int) -> int:
    """Up to four small whole numbers as the bytes of an inlined value."""
    return int.from_bytes(struct.pack(f"<{len(numbers)}b", *numbers).ljust(4, b"\0"), "little")


PAD = bytes(8)          # so that nothing sits at offset 0, which means "empty"
ONE_TO_TWENTY = b"\x00" + as_literals(struct.pack("<i", 1) + bytes(5))       # 20 differences of 1


class TestValues:

    def test_inlined_numbers(self):
        crate = bare_crate(PAD)
        assert crate.value(rep(usdc._INT, 0xFFFFFFFD, inlined=True)) == -3
        assert crate.value(rep(usdc._UINT, 0xFFFFFFFD, inlined=True)) == 4294967293
        assert crate.value(rep(usdc._INT64, 0xFFFFFFFD, inlined=True)) == -3
        assert crate.value(rep(usdc._BOOL, 1, inlined=True)) is True
        float_bits = struct.unpack("<I", struct.pack("<f", 1.5))[0]
        assert crate.value(rep(usdc._FLOAT, float_bits, inlined=True)) == 1.5
        # A double that a float holds exactly is kept as that float.
        assert crate.value(rep(usdc._DOUBLE, float_bits, inlined=True)) == 1.5
        half_bits = struct.unpack("<H", np.float16(0.25).tobytes())[0]
        assert crate.value(rep(usdc._HALF, half_bits, inlined=True)) == 0.25

    def test_inlined_names(self):
        crate = bare_crate(PAD)
        assert crate.value(rep(usdc._TOKEN, 1, inlined=True)) == "one"
        assert crate.value(rep(usdc._STRING, 0, inlined=True)) == "two"       # string 0 is token 2
        with pytest.raises(RoomScanError):
            crate.value(rep(usdc._TOKEN, 99, inlined=True))

    def test_an_inlined_vector_is_small_whole_numbers(self):
        crate = bare_crate(PAD)
        assert crate.value(rep(23, small(10, 0, -2), inlined=True)).tolist() == [10.0, 0.0, -2.0]     # Vec3d
        assert crate.value(rep(24, small(1, 1, 1), inlined=True)).tolist() == [1.0, 1.0, 1.0]         # Vec3f

    def test_an_inlined_matrix_is_its_diagonal(self):
        value = bare_crate(PAD).value(rep(usdc._MATRIX4D, small(2, 3, -4, 1), inlined=True))
        assert value.reshape(4, 4).tolist() == np.diag([2.0, 3.0, -4.0, 1.0]).tolist()

    def test_stored_numbers(self):
        data = PAD + struct.pack("<d", 0.01) + struct.pack("<3d", 1.5, 2.5, 3.5) + struct.pack("<16d", *range(16))
        crate = bare_crate(data)
        assert crate.value(rep(usdc._DOUBLE, 8)) == 0.01
        assert crate.value(rep(23, 16)).tolist() == [1.5, 2.5, 3.5]
        assert crate.value(rep(usdc._MATRIX4D, 40)).tolist() == [float(n) for n in range(16)]

    def test_a_quaternion_is_stored_real_part_last_and_given_real_part_first(self):
        data = PAD + struct.pack("<4f", 0.1, 0.2, 0.3, 0.9) + struct.pack("<4d", 0.1, 0.2, 0.3, 0.9)
        crate = bare_crate(data)
        assert crate.value(rep(usdc._QUATF, 8)).tolist() == pytest.approx([0.9, 0.1, 0.2, 0.3])
        assert crate.value(rep(usdc._QUATD, 24)).tolist() == [0.9, 0.1, 0.2, 0.3]

    @pytest.mark.parametrize("version, header", [
        ((0, 8, 0), struct.pack("<Q", 2)),
        ((0, 6, 0), struct.pack("<I", 2)),                          # before 0.7 the count is four bytes
        ((0, 4, 0), struct.pack("<I", 1) + struct.pack("<I", 2)),   # before 0.5 a rank comes first
    ])
    def test_an_array_header_by_version(self, version, header):
        crate = bare_crate(PAD + header + struct.pack("<2I", 1, 0), version=version)
        assert crate.value(rep(usdc._TOKEN, 8, array=True)) == ["one", "zero"]
        points = bare_crate(PAD + header + struct.pack("<6f", 1, 2, 3, 4, 5, 6), version=version)
        assert points.value(rep(24, 8, array=True)).tolist() == [[1, 2, 3], [4, 5, 6]]

    def test_an_empty_array_is_offset_zero(self):
        crate = bare_crate(PAD)
        assert crate.value(rep(usdc._TOKEN, 0, array=True)) == []
        assert crate.value(rep(24, 0, array=True)).shape == (0, 3)

    def test_half_and_double_points(self):
        halves = bare_crate(PAD + struct.pack("<Q", 1) + np.array([0.5, 1.0, -2.0], dtype="<f2").tobytes())
        assert halves.value(rep(25, 8, array=True)).tolist() == [[0.5, 1.0, -2.0]]
        doubles = bare_crate(PAD + struct.pack("<Q", 1) + struct.pack("<3d", 0.1, 0.2, 0.3))
        assert doubles.value(rep(23, 8, array=True)).tolist() == [[0.1, 0.2, 0.3]]

    def test_a_packed_array_of_whole_numbers(self):
        data = PAD + struct.pack("<Q", 20) + struct.pack("<Q", len(ONE_TO_TWENTY)) + ONE_TO_TWENTY
        assert bare_crate(data).value(rep(usdc._INT, 8, array=True, packed=True)).tolist() == list(range(1, 21))
        # Before 0.5 nothing was packed, whatever the flag says; the bytes are then the numbers themselves.
        raw = PAD + struct.pack("<II", 1, 2) + struct.pack("<2i", 7, -7)
        assert bare_crate(raw, version=(0, 4, 0)).value(rep(usdc._INT, 8, array=True, packed=True)).tolist() == [7, -7]

    def test_a_packed_array_of_sixty_four_bit_numbers(self):
        block = b"\x00" + as_literals(struct.pack("<q", 1 << 40) + bytes(5))
        data = PAD + struct.pack("<Q", 20) + struct.pack("<Q", len(block)) + block
        values = bare_crate(data).value(rep(usdc._INT64, 8, array=True, packed=True))
        assert values.tolist() == [(n + 1) << 40 for n in range(20)]

    def test_a_short_array_is_as_it_is_even_when_flagged_packed(self):
        data = PAD + struct.pack("<Q", 3) + struct.pack("<3i", 3, 4, 3)
        assert bare_crate(data).value(rep(usdc._INT, 8, array=True, packed=True)).tolist() == [3, 4, 3]

    def test_packed_floats_that_are_whole_numbers(self):
        data = PAD + struct.pack("<Q", 20) + b"i" + struct.pack("<Q", len(ONE_TO_TWENTY)) + ONE_TO_TWENTY
        values = bare_crate(data).value(rep(usdc._FLOAT, 8, array=True, packed=True))
        assert values.dtype == np.dtype("<f4")
        assert values.tolist() == [float(n) for n in range(1, 21)]

    def test_packed_floats_as_a_table_and_an_index_for_each(self):
        # Indexes 0, 1, 0, 1 ...: differences 0, then 1 and -1 by turns, a byte each.
        codes = bytes([0b01_01_01_00]) + bytes([0b01_01_01_01]) * 4
        steps = struct.pack("<19b", *[1 if n % 2 == 0 else -1 for n in range(19)])
        block = b"\x00" + as_literals(struct.pack("<i", 0) + codes + steps)
        data = (
            PAD + struct.pack("<Q", 20) + b"t" + struct.pack("<I", 2) + struct.pack("<2d", 0.25, 0.75)
            + struct.pack("<Q", len(block)) + block
        )
        crate = bare_crate(data)
        assert crate.value(rep(usdc._DOUBLE, 8, array=True, packed=True)).tolist() == [0.25, 0.75] * 10
        # An index past the end of the table is damage, not a crash.
        short = data.replace(struct.pack("<I", 2) + struct.pack("<2d", 0.25, 0.75), struct.pack("<I", 1) + struct.pack("<d", 0.25))
        with pytest.raises(RoomScanError):
            bare_crate(short).value(rep(usdc._DOUBLE, 8, array=True, packed=True))

    def test_the_first_time_sample_is_taken(self):
        float_bits = struct.unpack("<I", struct.pack("<f", 2.5))[0]
        data = (
            PAD
            + struct.pack("<q", 8)                                  # the times are 8 on from here
            + struct.pack("<Q", rep(usdc._DOUBLE_VECTOR, 0))         # the times (not read)
            + struct.pack("<q", 8)                                  # the values are 8 on from here
            + struct.pack("<Q", 2)                                  # two samples
            + struct.pack("<Q", rep(usdc._FLOAT, float_bits, inlined=True))
            + struct.pack("<Q", rep(usdc._FLOAT, 0, inlined=True))
        )
        crate = bare_crate(data)
        assert crate.value(rep(usdc._TIME_SAMPLES, 8)) == 2.5
        # Samples whose own values are samples are not followed round.
        looped = data[:32] + struct.pack("<Q", 1) + struct.pack("<Q", rep(usdc._TIME_SAMPLES, 8))
        assert bare_crate(looped).value(rep(usdc._TIME_SAMPLES, 8)) is None

    def test_what_is_not_understood_is_none_and_what_is_not_there_is_refused(self):
        crate = bare_crate(PAD + bytes(16))
        assert crate.value(rep(31, 8)) is None                      # a dictionary
        assert crate.value(rep(34, 8)) is None                      # a path list op
        assert crate.value(rep(200, 8)) is None                     # no such type
        assert crate.value(rep(200, 8, array=True)) is None
        assert crate.value(rep(usdc._QUATF, 3, inlined=True)) is None
        with pytest.raises(RoomScanError):
            crate.value(rep(23, 20))                                # a Vec3d that runs off the end
        with pytest.raises(RoomScanError):
            crate.value(rep(usdc._DOUBLE, 1 << 40))                 # an offset far outside the file
        huge = bare_crate(PAD + struct.pack("<Q", 1 << 50))
        with pytest.raises(RoomScanError):
            huge.value(rep(24, 8, array=True))                      # an array of 2^50 points


# ---------------------------------------------------------------------------
# Files that are cut short, damaged, or built to waste time
# ---------------------------------------------------------------------------

def refused(content: bytes, within: float = 2.0) -> str:
    """The plain-words refusal of a file, which must come quickly and be nothing but a RoomScanError."""
    started = time.perf_counter()
    with pytest.raises(RoomScanError) as error:
        parse_usdc(content, "room.usdc")
    assert time.perf_counter() - started < within
    message = str(error.value)
    assert "binary USD" in message and "OBJ" in message
    return message


def patched(content: bytes, at: int, layout: str, value: int) -> bytes:
    out = bytearray(content)
    struct.pack_into(layout, out, at, value)
    return bytes(out)


def sections(content: bytes) -> dict:
    toc = struct.unpack_from("<q", content, 16)[0]
    found = {}
    for n in range(struct.unpack_from("<Q", content, toc)[0]):
        name, start, size = struct.unpack_from("<16sqq", content, toc + 8 + 32 * n)
        found[name.rstrip(b"\0").decode()] = (start, size, toc + 8 + 32 * n)
    return found


class TestHostileFiles:

    ROOM = "room_y_metres.usdc"

    @pytest.mark.parametrize("length", [8, 9, 20, 87, 88, 96, 500, 2259, 2700, 3000, 3124, 3140, 3324])
    def test_cut_short(self, length):
        content = fixture(self.ROOM)
        assert length < len(content)
        refused(content[:length])

    def test_cut_short_anywhere(self):
        content = fixture(self.ROOM)
        for length in range(8, len(content), 5):
            refused(content[:length])

    def test_only_the_first_bytes(self):
        message = refused(b"PXR-USDC" + bytes(64))
        assert "Polycam" in message and "Scaniverse" in message
        refused(b"PXR-USDC")
        with pytest.raises(RoomScanError, match="PXR-USDC"):
            parse_usdc(b"not a crate file at all" + bytes(100))

    @pytest.mark.parametrize("version, says", [
        ((1, 0, 0), "newer than this reads"),
        ((7, 2, 0), "newer than this reads"),
        ((0, 3, 0), "oldest read here is 0.4.0"),
        ((0, 0, 1), "oldest read here is 0.4.0"),
        ((255, 255, 255), "newer than this reads"),
    ])
    def test_a_version_that_is_not_read(self, version, says):
        content = bytearray(fixture(self.ROOM))
        content[8:11] = bytes(version)
        message = refused(bytes(content))
        assert says in message and ".".join(str(v) for v in version) in message

    def test_a_later_minor_version_is_read_and_says_so(self):
        content = bytearray(fixture(self.ROOM))
        content[8:11] = bytes((0, 14, 0))
        mesh = parse_usdc(bytes(content))
        assert np.allclose(mesh.vertices, np.array(pixar(self.ROOM)["points"]), atol=1e-4)
        assert any("newer than the reader was written for" in note for note in mesh.notes)

    @pytest.mark.parametrize("offset", [0, 16, 87, 3324, 3325, 3326, 1 << 40, (1 << 63) - 1, -1, -(1 << 62)])
    def test_a_table_of_contents_that_is_not_where_the_header_says(self, offset):
        refused(patched(fixture(self.ROOM), 16, "<q", offset))

    def test_a_table_of_contents_pointed_at_something_else(self):
        # At the tokens: the "count" there is whatever those bytes happen to be.
        content = fixture(self.ROOM)
        refused(patched(content, 16, "<q", sections(content)["TOKENS"][0]))
        refused(patched(content, 16, "<q", 88))

    @pytest.mark.parametrize("count", [7, 65, 1 << 20, 1 << 40, (1 << 64) - 1])
    def test_a_section_count_that_is_too_big(self, count):
        content = fixture(self.ROOM)
        toc = struct.unpack_from("<q", content, 16)[0]
        refused(patched(content, toc, "<Q", count))

    def test_a_section_missing(self):
        content = fixture(self.ROOM)
        toc = struct.unpack_from("<q", content, 16)[0]
        assert "section" in refused(patched(content, toc, "<Q", 5))       # SPECS is the sixth
        assert "section" in refused(patched(content, toc, "<Q", 0))

    @pytest.mark.parametrize("name", ["TOKENS", "STRINGS", "FIELDS", "FIELDSETS", "PATHS", "SPECS"])
    @pytest.mark.parametrize("start, size", [
        (1 << 40, 10), (-5, 10), (100, 1 << 40), (100, -1), (3300, 100), ((1 << 63) - 1, (1 << 63) - 1),
    ])
    def test_a_section_that_is_not_inside_the_file(self, name, start, size):
        content = fixture(self.ROOM)
        entry = sections(content)[name][2]
        content = patched(patched(content, entry + 16, "<q", start), entry + 24, "<q", size)
        assert "not inside the file" in refused(content)

    @pytest.mark.parametrize("name", ["TOKENS", "STRINGS", "FIELDS", "FIELDSETS", "PATHS", "SPECS"])
    @pytest.mark.parametrize("count", [1 << 16, 19_999_999, 1 << 32, (1 << 64) - 1])
    def test_a_table_that_says_it_holds_more_than_it_could(self, name, count):
        """Nothing is allocated from a count the bytes behind it could not hold."""
        content = fixture(self.ROOM)
        # PATHS opens with a total, then the count of entries that follow.
        at = sections(content)[name][0] + (8 if name == "PATHS" else 0)
        refused(patched(content, at, "<Q", count), within=1.0)

    def test_a_total_of_paths_that_is_overstated_allocates_nothing(self):
        """The tree is built from the entries that are there, so the total is only a bound on them."""
        content = fixture(self.ROOM)
        start = sections(content)["PATHS"][0]
        started = time.perf_counter()
        mesh = parse_usdc(patched(content, start, "<Q", 19_999_999))
        assert time.perf_counter() - started < 1.0
        assert len(mesh.vertices) == len(pixar(self.ROOM)["points"])
        refused(patched(content, start, "<Q", 2))               # fewer than the entries point at
        refused(patched(content, start, "<Q", 1 << 40))

    @pytest.mark.parametrize("name", ["TOKENS", "STRINGS", "FIELDS", "FIELDSETS", "PATHS", "SPECS"])
    def test_a_section_that_is_empty_or_zeroed(self, name):
        content = fixture(self.ROOM)
        start, size, entry = sections(content)[name]
        refused(patched(content, entry + 24, "<q", 0))
        zeroed = bytearray(content)
        zeroed[start:start + size] = bytes(size)
        try:
            # Zeroed strings are still a table of token indexes, and the room does not use them.
            parse_usdc(bytes(zeroed))
            assert name == "STRINGS"
        except RoomScanError:
            pass

    def test_a_packed_block_that_says_it_is_huge(self):
        content = fixture(self.ROOM)
        start = sections(content)["TOKENS"][0]
        refused(patched(content, start + 8, "<Q", 1 << 50), within=1.0)       # unpacked size
        refused(patched(content, start + 16, "<Q", 1 << 50), within=1.0)      # packed size

    @pytest.mark.parametrize("name", ["room_y_metres.usdc", "big_room_ring.usdc", "room_y_metres_v0_7_0.usdc"])
    def test_damaged_bytes_give_a_mesh_or_a_plain_refusal_and_nothing_else(self, name):
        """A few hundred copies with bytes changed at random: read, or refused, never anything else, never slow."""
        content = fixture(name)
        rng = random.Random(24)
        read = 0
        for _ in range(400):
            damaged = bytearray(content)
            for _ in range(rng.choice([1, 1, 2, 8])):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
            started = time.perf_counter()
            try:
                mesh = parse_usdc(bytes(damaged), name)
            except RoomScanError as error:
                assert "binary USD" in str(error) or "mesh points" in str(error) or "usable points" in str(error) \
                    or "triangles" in str(error) or "points;" in str(error)
            else:
                read += 1
                assert mesh.format == "usdc" and len(mesh.vertices) >= 3
            assert time.perf_counter() - started < 2.0
        assert read            # a byte changed in the normals, say, changes nothing the room is read from

    def test_a_damaged_layer_in_a_usdz_is_refused_the_same_way(self):
        content = fixture(self.ROOM)
        archive = write_zip([("room.usdc", content[:1500])])
        with pytest.raises(RoomScanError, match="binary USD.*OBJ"):
            read_scan_file("Room.usdz", archive)
