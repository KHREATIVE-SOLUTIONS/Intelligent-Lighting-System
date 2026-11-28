"""
QR Code encoder (ISO/IEC 18004), pure Python
============================================

Small enough to read, no third-party QR library: the label sheet needs
scannable codes and neither `qrcode` nor `reportlab` is installed.

- Byte mode only (the label payload is a short JSON string).
- Error correction levels L, M, Q, H; versions 1 to 10.
- The smallest version that holds the data is picked, unless one is asked for.
- Reed-Solomon over GF(256) (polynomial 0x11D), blocks interleaved as the
  standard lays out.
- All eight masks are tried and the one with the lowest penalty (the four
  standard rules) is kept, unless one is asked for.
- Format information on every version, version information from version 7.

`encode()` returns the matrix as rows of booleans (True = dark), with no quiet
zone. `to_image()` draws it with Pillow, four modules of quiet zone around it.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

Matrix = List[List[bool]]

MAX_VERSION = 10

# Format bits for each level (the standard's table: L=01, M=00, Q=11, H=10).
ECC_FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

# Per version and level: (EC codewords per block, [(block count, data codewords per block), ...]).
# Checked against the module count in tests/test_qr_encode.py, which would
# catch a mistyped row.
EC_BLOCKS = {
    1: {"L": (7, [(1, 19)]), "M": (10, [(1, 16)]), "Q": (13, [(1, 13)]), "H": (17, [(1, 9)])},
    2: {"L": (10, [(1, 34)]), "M": (16, [(1, 28)]), "Q": (22, [(1, 22)]), "H": (28, [(1, 16)])},
    3: {"L": (15, [(1, 55)]), "M": (26, [(1, 44)]), "Q": (18, [(2, 17)]), "H": (22, [(2, 13)])},
    4: {"L": (20, [(1, 80)]), "M": (18, [(2, 32)]), "Q": (26, [(2, 24)]), "H": (16, [(4, 9)])},
    5: {"L": (26, [(1, 108)]), "M": (24, [(2, 43)]), "Q": (18, [(2, 15), (2, 16)]),
        "H": (22, [(2, 11), (2, 12)])},
    6: {"L": (18, [(2, 68)]), "M": (16, [(4, 27)]), "Q": (24, [(4, 19)]), "H": (28, [(4, 15)])},
    7: {"L": (20, [(2, 78)]), "M": (18, [(4, 31)]), "Q": (18, [(2, 14), (4, 15)]),
        "H": (26, [(4, 13), (1, 14)])},
    8: {"L": (24, [(2, 97)]), "M": (22, [(2, 38), (2, 39)]), "Q": (22, [(4, 18), (2, 19)]),
        "H": (26, [(4, 14), (2, 15)])},
    9: {"L": (30, [(2, 116)]), "M": (22, [(3, 36), (2, 37)]), "Q": (20, [(4, 16), (4, 17)]),
        "H": (24, [(4, 12), (4, 13)])},
    10: {"L": (18, [(2, 68), (2, 69)]), "M": (26, [(4, 43), (1, 44)]), "Q": (24, [(6, 19), (2, 20)]),
         "H": (28, [(6, 15), (2, 16)])},
}

# Alignment pattern centres (rows and columns alike) per version.
ALIGNMENT_CENTRES = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

FORMAT_GENERATOR = 0x537   # BCH(15,5)
FORMAT_XOR = 0x5412
VERSION_GENERATOR = 0x1F25  # BCH(18,6)


# --- GF(256) and Reed-Solomon ------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def rs_generator(degree: int) -> List[int]:
    """Coefficients of prod(x - a^i) for i < degree, highest power first, leading 1 included."""
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            nxt[j] ^= c
            nxt[j + 1] ^= gf_mul(c, _EXP[i])
        poly = nxt
    return poly


def rs_remainder(data: Sequence[int], degree: int) -> List[int]:
    """The `degree` error correction codewords for `data`."""
    gen = rs_generator(degree)[1:]
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for j, g in enumerate(gen):
            rem[j] ^= gf_mul(g, factor)
    return rem


# --- Capacity and codewords -----------------------------------------------------

def size_for(version: int) -> int:
    return 21 + 4 * (version - 1)


def data_capacity(version: int, ecc: str) -> int:
    """Data codewords (bytes) a version and level hold."""
    _, groups = EC_BLOCKS[version][ecc]
    return sum(n * k for n, k in groups)


def _count_bits(version: int) -> int:
    return 8 if version <= 9 else 16


def _fits(length: int, version: int, ecc: str) -> bool:
    return 4 + _count_bits(version) + 8 * length <= 8 * data_capacity(version, ecc)


def data_codewords(data: bytes, version: int, ecc: str) -> List[int]:
    """Mode, count, bytes, terminator and padding: the data codewords, before EC."""
    capacity_bits = 8 * data_capacity(version, ecc)
    bits: List[int] = []

    def put(value: int, width: int) -> None:
        bits.extend((value >> (width - 1 - i)) & 1 for i in range(width))

    put(0b0100, 4)
    put(len(data), _count_bits(version))
    for b in data:
        put(b, 8)
    if len(bits) > capacity_bits:
        raise ValueError("data too long for this version")
    bits.extend([0] * min(4, capacity_bits - len(bits)))
    bits.extend([0] * (-len(bits) % 8))
    out = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    while len(out) < capacity_bits // 8:
        out.append(pad[(len(out) - len(bits) // 8) % 2])
    return out


def interleave(codewords: Sequence[int], version: int, ecc: str) -> List[int]:
    """Split into blocks, add EC to each, and interleave as the standard lays out."""
    ec_len, groups = EC_BLOCKS[version][ecc]
    blocks, pos = [], 0
    for count, length in groups:
        for _ in range(count):
            blocks.append(list(codewords[pos:pos + length]))
            pos += length
    ecs = [rs_remainder(b, ec_len) for b in blocks]
    out: List[int] = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(e[i] for e in ecs)
    return out


# --- Matrix ------------------------------------------------------------------------

def format_bits(ecc: str, mask: int) -> int:
    """The 15-bit format string, masked, for a level and mask pattern."""
    data = (ECC_FORMAT_BITS[ecc] << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * FORMAT_GENERATOR)
    return ((data << 10) | rem) ^ FORMAT_XOR


def version_bits(version: int) -> int:
    """The 18-bit version information (used from version 7)."""
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * VERSION_GENERATOR)
    return (version << 12) | rem


class _Grid:
    def __init__(self, version: int):
        self.version = version
        self.size = size_for(version)
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.function[y][x] = True

    def draw_function_patterns(self) -> None:
        n = self.size
        for i in range(n):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.set(x, y, d not in (2, 4))
        centres = ALIGNMENT_CENTRES[self.version]
        last = len(centres) - 1
        for i, cy in enumerate(centres):
            for j, cx in enumerate(centres):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        # Reserve the format areas (drawn properly once the mask is chosen).
        self.draw_format(0)
        if self.version >= 7:
            bits = version_bits(self.version)
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def draw_format(self, bits: int) -> None:
        n = self.size

        def bit(i: int) -> bool:
            return (bits >> i) & 1 == 1

        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)  # the dark module

    def place_data(self, codewords: Sequence[int]) -> None:
        n = self.size
        total = len(codewords) * 8
        i = 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(n):
                y = n - 1 - vert if upward else vert
                for j in range(2):
                    x = right - j
                    if not self.function[y][x]:
                        if i < total:
                            self.dark[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                            i += 1
                        # Remainder bits stay light.
            right -= 2


def _mask_fn(mask: int):
    return [
        lambda x, y: (x + y) % 2 == 0,
        lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: (x * y) % 2 + (x * y) % 3 == 0,
        lambda x, y: ((x * y) % 2 + (x * y) % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + (x * y) % 3) % 2 == 0,
    ][mask]


def _apply_mask(grid: _Grid, mask: int) -> Matrix:
    fn = _mask_fn(mask)
    n = grid.size
    return [
        [grid.dark[y][x] != (not grid.function[y][x] and fn(x, y)) for x in range(n)]
        for y in range(n)
    ]


_FINDER_LIKE = ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1])


def penalty(m: Matrix) -> int:
    """The four standard mask penalty rules, summed."""
    n = len(m)
    score = 0
    lines = [row for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
    for line in lines:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, prev = 1, v
        if run >= 5:
            score += 3 + run - 5
        ints = [1 if v else 0 for v in line]
        for i in range(n - 10):
            window = ints[i:i + 11]
            if window in _FINDER_LIKE:
                score += 40
    for y in range(n - 1):
        for x in range(n - 1):
            v = m[y][x]
            if v == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(sum(row) for row in m)
    percent = dark * 100 / (n * n)
    score += 10 * int(abs(percent - 50) // 5)
    return score


def encode(
    data: bytes | str,
    ecc: str = "M",
    version: Optional[int] = None,
    mask: Optional[int] = None,
) -> Matrix:
    """Encode `data` as a QR Code matrix (True = dark), without the quiet zone."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    ecc = ecc.upper()
    if ecc not in EC_BLOCKS[1]:
        raise ValueError(f"unknown error correction level {ecc!r}")
    if version is None:
        version = next((v for v in range(1, MAX_VERSION + 1) if _fits(len(data), v, ecc)), None)
        if version is None:
            raise ValueError(
                f"{len(data)} bytes do not fit a version {MAX_VERSION} QR code at level {ecc}"
            )
    elif not 1 <= version <= MAX_VERSION:
        raise ValueError(f"version must be 1 to {MAX_VERSION}")
    elif not _fits(len(data), version, ecc):
        raise ValueError(f"{len(data)} bytes do not fit version {version} at level {ecc}")

    grid = _Grid(version)
    grid.draw_function_patterns()
    grid.place_data(interleave(data_codewords(data, version, ecc), version, ecc))

    best: Optional[Matrix] = None
    best_score = None
    for m in ([mask] if mask is not None else range(8)):
        grid.draw_format(format_bits(ecc, m))
        candidate = _apply_mask(grid, m)
        if mask is not None:
            return candidate
        s = penalty(candidate)
        if best_score is None or s < best_score:
            best, best_score = candidate, s
    assert best is not None
    return best


def to_image(matrix: Matrix, module_px: int = 10, quiet: int = 4):
    """Draw the matrix as a 1-bit Pillow image, `quiet` light modules around it."""
    from PIL import Image

    n = len(matrix)
    side = n + 2 * quiet
    img = Image.new("1", (side, side), 1)
    px = img.load()
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                px[x + quiet, y + quiet] = 0
    if module_px != 1:
        img = img.resize((side * module_px, side * module_px), Image.NEAREST)
    return img
