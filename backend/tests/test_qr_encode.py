"""
QR encoder known-answer tests (app/services/qr_encode.py)
=========================================================

Reed-Solomon against the published HELLO WORLD 1-M example (thonky.com QR
tutorial), the block tables against the module count, format and version
information against the standard's tables, the fixed patterns in place, and,
where OpenCV is importable, a round trip through a real decoder.
"""

import pytest

from app.services import qr_encode as q


# --- Reed-Solomon ----------------------------------------------------------------

def test_reed_solomon_matches_the_hello_world_1m_example():
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    assert q.rs_remainder(data, 10) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


def test_generator_polynomial_for_ten_ec_codewords():
    # thonky.com: x^10 + a^251 x^9 + a^67 x^8 + a^46 x^7 + a^61 x^6 + a^118 x^5
    #             + a^70 x^4 + a^64 x^3 + a^94 x^2 + a^32 x + a^45
    exps = [0, 251, 67, 46, 61, 118, 70, 64, 94, 32, 45]
    assert q.rs_generator(10) == [q._EXP[e] for e in exps]


def test_header_terminator_and_pad_bytes():
    words = q.data_codewords(b"", 1, "M")
    # mode 0100, count 00000000, terminator 0000, then EC 11 EC 11 ...
    assert words[:3] == [0b01000000, 0b00000000, 0xEC]
    assert words[3:5] == [0x11, 0xEC]
    assert len(words) == 16


# --- Tables ----------------------------------------------------------------------

@pytest.mark.parametrize("version", range(1, q.MAX_VERSION + 1))
def test_block_table_fills_exactly_the_free_modules(version):
    grid = q._Grid(version)
    grid.draw_function_patterns()
    free = sum(1 for row in grid.function for f in row if not f)
    remainder = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}[version]
    assert free % 8 == remainder
    for ecc in "LMQH":
        ec, groups = q.EC_BLOCKS[version][ecc]
        assert free // 8 == sum(n * (k + ec) for n, k in groups), (version, ecc)


@pytest.mark.parametrize("version", range(1, q.MAX_VERSION + 1))
def test_matrix_size_per_version(version):
    m = q.encode(b"x", "M", version=version)
    assert len(m) == 21 + 4 * (version - 1)
    assert all(len(row) == len(m) for row in m)


def test_smallest_version_is_picked_including_the_wider_count_at_version_10():
    assert len(q.encode(b"A" * 14, "M")) == 21          # 1-M holds 14 bytes
    assert len(q.encode(b"A" * 15, "M")) == 25          # one more needs version 2
    # 9-M: 182 data codewords, 8-bit count: 180 bytes fit, 181 do not.
    assert len(q.encode(b"A" * 180, "M")) == q.size_for(9)
    # 10-M: 216 data codewords with a 16-bit count: 213 bytes is the most.
    assert len(q.encode(b"A" * 181, "M")) == q.size_for(10)
    assert len(q.encode(b"A" * 213, "M")) == q.size_for(10)
    with pytest.raises(ValueError):
        q.encode(b"A" * 214, "M")


def test_too_long_for_a_forced_version_is_refused():
    with pytest.raises(ValueError):
        q.encode(b"A" * 15, "M", version=1)


# --- Fixed patterns -----------------------------------------------------------------

FINDER = [
    "#######",
    "#.....#",
    "#.###.#",
    "#.###.#",
    "#.###.#",
    "#.....#",
    "#######",
]


def _block(m, x0, y0, w, h):
    return ["".join("#" if m[y][x] else "." for x in range(x0, x0 + w)) for y in range(y0, y0 + h)]


@pytest.mark.parametrize("version", [1, 3, 7, 10])
def test_finders_separators_and_timing(version):
    m = q.encode(b"labels", "M", version=version)
    n = len(m)
    for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)):
        assert _block(m, x0, y0, 7, 7) == FINDER
    # Separators: the light ring just inside the quiet zone.
    assert not any(m[7][x] for x in range(8)) and not any(m[y][7] for y in range(8))
    assert not any(m[7][x] for x in range(n - 8, n))
    assert not any(m[n - 8][x] for x in range(8))
    # Timing patterns alternate, dark on even indexes.
    for i in range(8, n - 8):
        assert m[6][i] == (i % 2 == 0)
        assert m[i][6] == (i % 2 == 0)
    assert m[n - 8][8] is True  # the dark module


def test_alignment_pattern_at_version_2():
    m = q.encode(b"x", "M", version=2)
    assert _block(m, 16, 16, 5, 5) == ["#####", "#...#", "#.#.#", "#...#", "#####"]


# --- Format and version information -------------------------------------------------

def _read_format(m):
    """Both copies of the 15-bit format string, most significant bit first."""
    n = len(m)
    first = [m[8][x] for x in (0, 1, 2, 3, 4, 5, 7, 8)] + [m[y][8] for y in (7, 5, 4, 3, 2, 1, 0)]
    second = [m[y][8] for y in range(n - 1, n - 8, -1)] + [m[8][x] for x in range(n - 8, n)]
    as_int = lambda bits: int("".join("1" if b else "0" for b in bits), 2)
    # The bits run from 14 (first read) down to 0.
    return as_int(first), as_int(second)


def _decode_format(bits):
    """(level, mask) for a 15-bit format string, by nearest valid code."""
    best = min(
        ((ecc, mask) for ecc in "LMQH" for mask in range(8)),
        key=lambda c: bin(q.format_bits(*c) ^ bits).count("1"),
    )
    return best


def test_level_m_mask_0_format_string_is_the_xor_mask_itself():
    assert q.format_bits("M", 0) == 0b101010000010010
    m = q.encode(b"hello", "M", mask=0)
    assert _read_format(m) == (0b101010000010010, 0b101010000010010)


@pytest.mark.parametrize("ecc", "LMQH")
@pytest.mark.parametrize("mask", range(8))
def test_format_bits_decode_to_the_level_and_mask(ecc, mask):
    m = q.encode(b"fixture 12", ecc, mask=mask)
    first, second = _read_format(m)
    assert first == second == q.format_bits(ecc, mask)
    assert _decode_format(first) == (ecc, mask)


def test_published_format_strings():
    # ISO/IEC 18004 Table C.1 rows (masked).
    assert q.format_bits("L", 0) == 0b111011111000100
    assert q.format_bits("H", 7) == 0b000100000111011
    assert q.format_bits("Q", 3) == 0b011101000000110


def test_automatic_mask_is_the_lowest_penalty():
    data = b'{"fixture_id": 12, "rig_fixture_id": 345}'
    chosen = q.encode(data, "M")
    scores = {mask: q.penalty(q.encode(data, "M", mask=mask)) for mask in range(8)}
    assert q.penalty(chosen) == min(scores.values())


@pytest.mark.parametrize("version,expected", [
    (7, 0x07C94), (8, 0x085BC), (9, 0x09A99), (10, 0x0A4D3),
])
def test_version_information_matches_the_published_table(version, expected):
    assert q.version_bits(version) == expected
    m = q.encode(b"x", "M", version=version)
    n = len(m)
    # Bit i sits at (row i//3, column n-11+i%3) and mirrored.
    top_right = sum(m[i // 3][n - 11 + i % 3] << i for i in range(18))
    bottom_left = sum(m[n - 11 + i % 3][i // 3] << i for i in range(18))
    assert top_right == bottom_left == expected


def test_no_version_information_below_7():
    m = q.encode(b"x", "M", version=6)
    grid = q._Grid(6)
    grid.draw_function_patterns()
    n = len(m)
    assert not any(grid.function[i // 3][n - 11 + i % 3] for i in range(18))


# --- Image -------------------------------------------------------------------------

def test_image_has_a_four_module_quiet_zone():
    m = q.encode(b"x", "M")
    img = q.to_image(m, module_px=3)
    assert img.size == ((21 + 8) * 3, (21 + 8) * 3)
    px = img.load()
    assert all(px[i, j] for i in range(12) for j in range(img.height))  # left margin light
    assert px[12, 12] == 0  # finder corner dark


# --- Round trip through a real decoder ------------------------------------------------

def _decodes(img, expected):
    """True if either OpenCV detector reads `expected`, at any quarter turn.

    The classic detector misses a few valid codes at some orientations; the
    Aruco-based one reads all of them. Either reading the exact text is proof.
    """
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    arr = np.array(img.convert("L"))
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    for turn in range(4):
        rotated = np.ascontiguousarray(np.rot90(arr, turn))
        for det in detectors:
            if det.detectAndDecode(rotated)[0] == expected:
                return True
    return False


@pytest.mark.parametrize("version", range(1, q.MAX_VERSION + 1))
@pytest.mark.parametrize("ecc", "LMQH")
def test_round_trip_through_opencv(version, ecc):
    pytest.importorskip("cv2")
    overhead = 2 if version <= 9 else 3
    payload = "".join(chr((i * 7 + 65) % 94 + 32) for i in range(q.data_capacity(version, ecc) - overhead))
    m = q.encode(payload, ecc, version=version)
    assert _decodes(q.to_image(m, 6), payload)


def test_round_trip_of_the_label_payload():
    pytest.importorskip("cv2")
    payload = '{"fixture_id": 12, "rig_fixture_id": 345}'
    assert _decodes(q.to_image(q.encode(payload), 6), payload)
