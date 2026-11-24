"""
Binary USD (USDC, the "crate" format)
=====================================

What Apple's RoomPlan, Polycam, Scaniverse and most phone apps put inside a
USDZ. Read here with numpy and the standard library only: Pixar's USD library
is not a dependency, and nor is an LZ4 package.

A crate file is a small database, not a list of meshes:

    header       `PXR-USDC`, three version bytes, where the table of contents is
    TOKENS       every name in the file, once
    STRINGS      strings, as indexes into the tokens
    FIELDS       (name, value) pairs; a value is 64 bits, a "ValueRep"
    FIELDSETS    runs of field indexes, one run per spec
    PATHS        the tree of prim and property paths
    SPECS        (path, field set, kind) for every prim and attribute

The tables are packed with LZ4, and the tables of whole numbers with USD's own
integer coding first (differences from the number before, in as few bytes as
each one needs). Both are undone here: `lz4_block`, `decompress`,
`decode_integers`.

A ValueRep's top bits say whether it is an array, whether the value is held in
the 64 bits themselves ("inlined") and whether an array is packed; one byte
says the type; the low 48 bits are the value or where in the file it is. Only
the values a room needs are ever decoded: a stage's `upAxis` and
`metersPerUnit`, each prim's type and children, and a mesh's `points`,
`faceVertexCounts`, `faceVertexIndices` and transform ops. Normals, texture
coordinates, materials and everything else are stepped over without being
looked at.

The prims, their transforms and the mesh are put together by the same code as
a USD text layer (usd.py), so a text layer and a binary layer of the same stage
give the same ScanMesh.

Read: crate versions 0.4.0 to 0.12. The version 0.7, 0.8 and 0.10 files in
tests/fixtures/usdc were written by Pixar's library, and what it computes from
them is what the tests compare with. NOT run against a Pixar-written file:
versions 0.4 to 0.6 (a shorter array header), arrays of floats packed as whole
numbers or as a lookup table, 64-bit packed arrays, LZ4 in more than one
chunk, time samples, and points held as halves or doubles. No file from a real
phone has been read by it yet.

Not read: what a layer brings in from another layer (references, payloads,
sublayers), variants, instances and their prototypes, and animation (of a
value with only time samples, the first is taken).

A file is not trusted. Every count and offset is checked against the bytes
that are there before anything is allocated or read, nothing recurses, and
whatever goes wrong comes out as a RoomScanError in plain words.
"""

import math
import struct
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .mesh import RoomScanError, ScanMesh
from .usd import CONVERT_MESSAGE, MAX_ARCHIVE_BYTES, USDC_MAGIC, _mesh_from_prims, _op_matrix_numbers, _Prim

OLDEST_VERSION = (0, 4, 0)
# The newest crate version this was written against. A later 0.x is still
# read, with a note: what it adds are value types, which are stepped over.
NEWEST_VERSION = (0, 12, 0)

HEADER_BYTES = 88
MAX_SECTIONS = 64
# The most bytes any one packed block may unpack to.
MAX_DECODED_BYTES = MAX_ARCHIVE_BYTES
# Entries in any one table (tokens, fields, paths, specs). A phone scan has a
# few hundred; RoomPlan a few thousand.
MAX_TABLE_ITEMS = 20_000_000
# Entries in any one array value: three corners each for 20 million triangles.
MAX_ARRAY_ITEMS = 60_000_000
# LZ4 cannot make a block more than 255 times smaller, so a block of n bytes
# that claims to unpack to more than this is lying.
_LZ4_RATIO = 255
# Below this many entries USD writes an array as it is, even when flagged packed.
_MIN_PACKED_ARRAY = 16

_SECTIONS = ("TOKENS", "STRINGS", "FIELDS", "FIELDSETS", "PATHS", "SPECS")
_END_OF_FIELD_SET = 0xFFFFFFFF

# SdfSpecType
_SPEC_ATTRIBUTE = 1
_SPEC_PRIM = 6
_SPEC_PSEUDO_ROOT = 7
# SdfSpecifier: def is 0.
_SPECIFIER_OVER = 1
_SPECIFIER_CLASS = 2

# The crate's type numbers (USD's crateDataTypes.h).
_BOOL, _UCHAR, _INT, _UINT, _INT64, _UINT64, _HALF, _FLOAT, _DOUBLE = range(1, 10)
_STRING, _TOKEN, _ASSET_PATH = 10, 11, 12
_MATRIX2D, _MATRIX3D, _MATRIX4D = 13, 14, 15
_QUATD, _QUATF, _QUATH = 16, 17, 18
_TOKEN_VECTOR = 41
_SPECIFIER, _PERMISSION, _VARIABILITY = 42, 43, 44
_TIME_SAMPLES = 46
_DOUBLE_VECTOR = 48
_STRING_VECTOR = 50

# type: (numpy type of one number, how many numbers make one value)
_NUMBERS: Dict[int, Tuple[str, int]] = {
    _BOOL: ("u1", 1), _UCHAR: ("u1", 1),
    _INT: ("<i4", 1), _UINT: ("<u4", 1), _INT64: ("<i8", 1), _UINT64: ("<u8", 1),
    _HALF: ("<f2", 1), _FLOAT: ("<f4", 1), _DOUBLE: ("<f8", 1),
    _MATRIX2D: ("<f8", 4), _MATRIX3D: ("<f8", 9), _MATRIX4D: ("<f8", 16),
    _QUATD: ("<f8", 4), _QUATF: ("<f4", 4), _QUATH: ("<f2", 4),
    19: ("<f8", 2), 20: ("<f4", 2), 21: ("<f2", 2), 22: ("<i4", 2),     # Vec2 d f h i
    23: ("<f8", 3), 24: ("<f4", 3), 25: ("<f2", 3), 26: ("<i4", 3),     # Vec3
    27: ("<f8", 4), 28: ("<f4", 4), 29: ("<f2", 4), 30: ("<i4", 4),     # Vec4
}
_MATRIX_SIDE = {_MATRIX2D: 2, _MATRIX3D: 3, _MATRIX4D: 4}
_QUATERNIONS = (_QUATD, _QUATF, _QUATH)
_PACKED_INTEGERS = (_INT, _UINT, _INT64, _UINT64)
_PACKED_FLOATS = (_HALF, _FLOAT, _DOUBLE)

_MESH_ATTRIBUTES = ("points", "faceVertexCounts", "faceVertexIndices", "xformOpOrder")

# What can go wrong inside numpy or struct on bytes that are not what they say.
_DECODE_ERRORS = (
    struct.error, IndexError, KeyError, ValueError, TypeError, OverflowError, ArithmeticError,
    MemoryError, RecursionError,
)


def unreadable(reason: str) -> RoomScanError:
    """Why a binary USD layer could not be read, and what to export instead."""
    return RoomScanError(f"This binary USD (USDC) file cannot be read: {reason} {CONVERT_MESSAGE}")


def _damaged() -> RoomScanError:
    return unreadable("it is damaged or cut short.")


# ---------------------------------------------------------------------------
# LZ4, and USD's integer coding
# ---------------------------------------------------------------------------

def lz4_block(source: bytes, max_size: int) -> bytes:
    """One LZ4 block unpacked; an error if it runs past `max_size` or off its own ends.

    A block is a run of sequences: a token byte (high half the count of
    literal bytes, low half the match length less 4; 15 in either means more
    count bytes follow), the literals, then a two-byte distance back into what
    has been written so far to copy the match from. The last sequence is
    literals only. A match may reach into the bytes it is itself writing,
    which is how a repeat is stored.
    """
    source = bytes(source)
    end = len(source)
    out = bytearray()
    at = 0
    while True:
        if at >= end:
            raise _damaged()
        token = source[at]
        at += 1

        run = token >> 4
        if run == 15:
            while True:
                if at >= end:
                    raise _damaged()
                more = source[at]
                at += 1
                run += more
                if more != 255:
                    break
        if at + run > end or len(out) + run > max_size:
            raise _damaged()
        out += source[at:at + run]
        at += run
        if at >= end:
            return bytes(out)

        if at + 2 > end:
            raise _damaged()
        distance = source[at] | (source[at + 1] << 8)
        at += 2
        if distance == 0 or distance > len(out):
            raise _damaged()
        length = token & 15
        if length == 15:
            while True:
                if at >= end:
                    raise _damaged()
                more = source[at]
                at += 1
                length += more
                if more != 255:
                    break
        length += 4
        if len(out) + length > max_size:
            raise _damaged()
        start = len(out) - distance
        if distance >= length:
            out += out[start:start + length]
        else:
            # The match overlaps what it writes: the last `distance` bytes, over and over.
            pattern = bytes(out[start:])
            out += (pattern * (length // distance + 1))[:length]


def decompress(source: bytes, max_size: int) -> bytes:
    """A block as USD packs it (TfFastCompression), unpacked to at most `max_size` bytes.

    The first byte is a count of chunks. 0 is the usual case, one LZ4 block;
    otherwise that many blocks follow, each after its own four-byte length.
    """
    source = bytes(source)
    if not source:
        raise _damaged()
    # No more than these bytes could unpack to, whatever size is claimed for them.
    max_size = min(max_size, MAX_DECODED_BYTES, _LZ4_RATIO * len(source) + 64)
    chunks = source[0]
    if chunks == 0:
        return lz4_block(source[1:], max_size)
    parts: List[bytes] = []
    total = 0
    at = 1
    for _ in range(chunks):
        if at + 4 > len(source):
            raise _damaged()
        size = struct.unpack_from("<i", source, at)[0]
        at += 4
        if size < 0 or at + size > len(source):
            raise _damaged()
        part = lz4_block(source[at:at + size], max_size - total)
        at += size
        total += len(part)
        parts.append(part)
    return b"".join(parts)


_CODE_SHIFTS = np.array([0, 2, 4, 6], dtype=np.uint8)
# How many numbers are decoded at a time: a multiple of 4, so each lot starts on a code byte.
_INTEGER_BLOCK = 1 << 20


def decode_integers(encoded: bytes, count: int, wide: bool = False) -> np.ndarray:
    """`count` whole numbers out of USD's integer coding (already LZ4-unpacked).

    The coding stores each number as its difference from the one before
    (the first, from 0). It opens with the most common difference, then two
    bits for each number, four to a byte from the low bits up, then the
    differences that were not the common one:

        code   32-bit numbers    64-bit numbers (`wide`)
        0      the common one    the common one
        1      one byte          two bytes
        2      two bytes         four bytes
        3      four bytes        eight bytes

    all signed and little-endian. Sums wrap round, as they do in USD.
    """
    word = 8 if wide else 4
    result = np.dtype("<i8" if wide else "<i4")
    if count <= 0:
        return np.zeros(0, dtype=result)
    encoded = bytes(encoded)
    code_bytes = (count * 2 + 7) // 8
    if len(encoded) < word + code_bytes:
        raise _damaged()
    common = int.from_bytes(encoded[:word], "little", signed=True)
    data = np.frombuffer(encoded, dtype=np.uint8)
    widths = np.array([0, 2, 4, 8] if wide else [0, 1, 2, 4], dtype=np.int64)
    kinds = ("<i2", "<i4", "<i8") if wide else ("i1", "<i2", "<i4")

    out = np.empty(count, dtype=np.int64)
    at = word + code_bytes
    previous = np.int64(0)
    with np.errstate(over="ignore"):
        for begin in range(0, count, _INTEGER_BLOCK):
            size = min(_INTEGER_BLOCK, count - begin)
            packed = data[word + begin // 4: word + (begin + size + 3) // 4]
            codes = ((packed[:, None] >> _CODE_SHIFTS) & 3).reshape(-1)[:size]
            width = widths[codes]
            ends = np.cumsum(width)
            used = int(ends[-1])
            if at + used > len(encoded):
                raise _damaged()
            starts = ends - width + at
            deltas = np.full(size, common, dtype=np.int64)
            for code in (1, 2, 3):
                chosen = codes == code
                if chosen.any():
                    positions = starts[chosen][:, None] + np.arange(int(widths[code]))
                    raw = np.ascontiguousarray(data[positions])
                    deltas[chosen] = raw.view(kinds[code - 1]).reshape(-1)
            values = np.cumsum(deltas, dtype=np.int64)
            values += previous
            previous = values[-1]
            out[begin:begin + size] = values
            at += used
    return out if wide else out.astype(result)


def decompress_integers(source: bytes, count: int, wide: bool = False) -> np.ndarray:
    """`count` whole numbers from a block as a crate file holds them: integer coding, then LZ4."""
    word = 8 if wide else 4
    if count <= 0:
        return np.zeros(0, dtype="<i8" if wide else "<i4")
    # Every number costs at least two bits before LZ4, and LZ4 saves at most 255 to 1.
    if count > MAX_ARRAY_ITEMS or count > 4 * (_LZ4_RATIO * len(source) + 64):
        raise _damaged()
    working = word + (count * 2 + 7) // 8 + count * word
    return decode_integers(decompress(source, working), count, wide)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

class _Cursor:
    """A place in the file, read forwards. Nothing is read past `end`."""

    def __init__(self, data: bytes, at: int, end: int):
        if at < 0 or at > end or end > len(data):
            raise _damaged()
        self.data = data
        self.at = at
        self.end = end

    def seek(self, at: int) -> None:
        if at < 0 or at > self.end:
            raise _damaged()
        self.at = at

    def take(self, size: int) -> bytes:
        if size < 0 or size > self.end - self.at:
            raise _damaged()
        chunk = self.data[self.at:self.at + size]
        self.at += size
        return chunk

    def _number(self, layout: str, size: int) -> int:
        if size > self.end - self.at:
            raise _damaged()
        value = struct.unpack_from(layout, self.data, self.at)[0]
        self.at += size
        return value

    def u32(self) -> int:
        return self._number("<I", 4)

    def u64(self) -> int:
        return self._number("<Q", 8)

    def i64(self) -> int:
        return self._number("<q", 8)

    def array(self, dtype: str, count: int) -> np.ndarray:
        """`count` numbers straight from the file (not copied, not writable)."""
        size = np.dtype(dtype).itemsize
        if count < 0 or count > (self.end - self.at) // size:
            raise _damaged()
        values = np.frombuffer(self.data, dtype=dtype, count=count, offset=self.at)
        self.at += count * size
        return values

    def integers(self, count: int, wide: bool = False) -> np.ndarray:
        """Packed whole numbers: eight bytes of length, then the block."""
        return decompress_integers(self.take(self.u64()), count, wide)


def _version_words(version: Tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


class _Crate:
    """The tables of a crate file, unpacked. Values are decoded only when asked for."""

    def __init__(self, data: bytes):
        self.data = data
        self.size = len(data)
        if data[:len(USDC_MAGIC)] != USDC_MAGIC:
            raise unreadable("it does not start with PXR-USDC.")
        if self.size < HEADER_BYTES:
            raise _damaged()
        self.version: Tuple[int, int, int] = (data[8], data[9], data[10])
        said = _version_words(self.version)
        if self.version < OLDEST_VERSION:
            raise unreadable(
                f"it says it is crate version {said}, and the oldest read here is "
                f"{_version_words(OLDEST_VERSION)}."
            )
        if self.version[0] != 0:
            raise unreadable(
                f"it is crate version {said}, newer than this reads "
                f"({_version_words(OLDEST_VERSION)} to 0.{NEWEST_VERSION[1]})."
            )

        sections = self._contents()
        self.tokens = self._tokens(self._section(sections, "TOKENS"))
        self.strings = self._strings(self._section(sections, "STRINGS"))
        self._fields(self._section(sections, "FIELDS"))
        self._field_sets(self._section(sections, "FIELDSETS"))
        self._paths(self._section(sections, "PATHS"))
        self._specs(self._section(sections, "SPECS"))
        self._field_cache: Dict[int, Dict[str, int]] = {}
        # Field sets do not overlap in a real file, so reading every one of
        # them visits each entry once. A file built to make them overlap runs
        # out of this instead of running for hours.
        self._field_visits = 4 * len(self.field_sets) + 1024

    # -- tables -------------------------------------------------------------

    def _contents(self) -> Dict[str, Tuple[int, int]]:
        toc = struct.unpack_from("<q", self.data, 16)[0]
        if toc < HEADER_BYTES or toc > self.size - 8:
            raise unreadable("its table of contents is not where its header says: it is damaged or cut short.")
        cursor = _Cursor(self.data, toc, self.size)
        count = cursor.u64()
        if count > MAX_SECTIONS:
            raise unreadable("its table of contents lists more sections than a USD file has: it is damaged.")
        sections: Dict[str, Tuple[int, int]] = {}
        for _ in range(count):
            name = cursor.take(16).split(b"\0", 1)[0].decode("ascii", errors="replace")
            start, size = cursor.i64(), cursor.i64()
            if start < 0 or size < 0 or start + size > self.size:
                raise unreadable(
                    f"its {name or 'unnamed'} section is not inside the file: it is damaged or cut short."
                )
            sections.setdefault(name, (start, size))
        return sections

    def _section(self, sections: Dict[str, Tuple[int, int]], name: str) -> _Cursor:
        if name not in sections:
            raise unreadable(f"it has no {name} section.")
        start, size = sections[name]
        return _Cursor(self.data, start, start + size)

    @staticmethod
    def _table_size(count: int) -> int:
        if count > MAX_TABLE_ITEMS:
            raise unreadable("one of its tables is larger than this will read.")
        return count

    def _tokens(self, cursor: _Cursor) -> List[str]:
        count = self._table_size(cursor.u64())
        unpacked, packed = cursor.u64(), cursor.u64()
        # Every token ends in a zero byte, so there cannot be more of them than bytes.
        if unpacked > MAX_DECODED_BYTES or count > unpacked:
            raise _damaged()
        names = decompress(cursor.take(packed), unpacked).split(b"\0")
        if len(names) < count:
            raise _damaged()
        return [name.decode("utf-8", errors="replace") for name in names[:count]]

    def _strings(self, cursor: _Cursor) -> List[int]:
        return cursor.array("<u4", self._table_size(cursor.u64())).tolist()

    def _fields(self, cursor: _Cursor) -> None:
        count = self._table_size(cursor.u64())
        names = cursor.integers(count).view("<u4")
        if count and int(names.max()) >= len(self.tokens):
            raise _damaged()
        reps = decompress(cursor.take(cursor.u64()), count * 8)
        if len(reps) < count * 8:
            raise _damaged()
        self.field_names: List[int] = names.tolist()
        self.field_reps: List[int] = np.frombuffer(reps, dtype="<u8", count=count).tolist()

    def _field_sets(self, cursor: _Cursor) -> None:
        count = self._table_size(cursor.u64())
        self.field_sets: List[int] = cursor.integers(count).view("<u4").tolist()

    def _paths(self, cursor: _Cursor) -> None:
        """The path tree, as three lists by path index: parent, name and whether it is a property.

        The file holds the tree flattened parent-first. Each entry has a jump:
        -2 a leaf, -1 its first child is next, 0 its next sibling is next, and
        above 0 its first child is next and its next sibling is that many
        entries on. USD walks it by calling itself; a deep file would run a
        Python reader out of stack, so here the siblings wait in a list.
        """
        total = self._table_size(cursor.u64())
        entries = self._table_size(cursor.u64())
        indexes = cursor.integers(entries).view("<u4").tolist()
        elements = cursor.integers(entries).tolist()
        jumps = cursor.integers(entries).tolist()

        # Keyed by path index and filled only for the entries that are there:
        # the count the file gives is not taken on trust as a size to allocate.
        self.parent: Dict[int, int] = {}
        self.name: Dict[int, str] = {}
        self.is_property: Dict[int, bool] = {}
        self.children: Dict[int, List[int]] = {}
        self.root = -1
        tokens = self.tokens
        placed = 0
        waiting: List[Tuple[int, int]] = [(0, -1)] if entries else []
        while waiting:
            at, parent = waiting.pop()
            while True:
                if at < 0 or at >= entries:
                    raise _damaged()
                placed += 1
                if placed > entries:        # an entry reached twice: the jumps go round in a ring
                    raise _damaged()
                this = at
                at += 1
                path = indexes[this]
                if path >= total:
                    raise _damaged()
                if parent < 0:
                    self.root = path
                    self.parent[path], self.name[path], self.is_property[path] = -1, "", False
                else:
                    element = elements[this]
                    token = abs(element)
                    if token >= len(tokens):
                        raise _damaged()
                    self.parent[path] = parent
                    self.name[path] = tokens[token]
                    self.is_property[path] = element < 0
                    if element >= 0:
                        self.children.setdefault(parent, []).append(path)
                jump = jumps[this]
                has_child = jump > 0 or jump == -1
                has_sibling = jump >= 0
                if has_child:
                    if has_sibling:
                        waiting.append((this + jump, parent))
                    parent = path
                if not (has_child or has_sibling):
                    break

    def _specs(self, cursor: _Cursor) -> None:
        count = self._table_size(cursor.u64())
        paths = cursor.integers(count).view("<u4").tolist()
        field_sets = cursor.integers(count).view("<u4").tolist()
        kinds = cursor.integers(count).view("<u4").tolist()
        # path index -> (where its field set starts, what kind of spec it is)
        self.specs: Dict[int, Tuple[int, int]] = {}
        for path, field_set, kind in zip(paths, field_sets, kinds):
            if path in self.parent:
                self.specs.setdefault(path, (field_set, kind))

    # -- fields and values --------------------------------------------------

    def fields(self, start: int) -> Dict[str, int]:
        """The fields of the set that starts at `start`: name -> ValueRep."""
        cached = self._field_cache.get(start)
        if cached is not None:
            return cached
        found: Dict[str, int] = {}
        at = start
        while 0 <= at < len(self.field_sets):
            field = self.field_sets[at]
            if field == _END_OF_FIELD_SET:
                break
            if field >= len(self.field_names):
                raise _damaged()
            self._field_visits -= 1
            if self._field_visits < 0:
                raise _damaged()
            found[self.tokens[self.field_names[field]]] = self.field_reps[field]
            at += 1
        self._field_cache[start] = found
        return found

    def token(self, index: int) -> str:
        if index < 0 or index >= len(self.tokens):
            raise _damaged()
        return self.tokens[index]

    def string(self, index: int) -> str:
        if index < 0 or index >= len(self.strings):
            raise _damaged()
        return self.token(self.strings[index])

    def value(self, rep: int, nested: bool = False) -> Any:
        """What a ValueRep holds, or None for a type that is not read here.

        Numbers come back as Python numbers, vectors and matrices as float
        arrays (a quaternion as w, x, y, z, the order USD text writes), arrays
        as numpy arrays, tokens and strings as str, lists of them as lists.
        """
        kind = (rep >> 48) & 0xFF
        payload = rep & 0xFFFFFFFFFFFF
        if rep >> 63:
            return self._array(kind, payload, bool((rep >> 61) & 1))
        if (rep >> 62) & 1:
            return self._inlined(kind, payload & 0xFFFFFFFF)
        return self._stored(kind, payload, nested)

    def _inlined(self, kind: int, bits: int) -> Any:
        """A value small enough to be held in the ValueRep itself."""
        signed = bits - (1 << 32) if bits & 0x80000000 else bits
        if kind == _BOOL:
            return bool(bits & 1)
        if kind == _UCHAR:
            return bits & 0xFF
        if kind in (_INT, _INT64):
            return signed
        if kind in (_UINT, _UINT64, _SPECIFIER, _PERMISSION, _VARIABILITY):
            return bits
        if kind == _HALF:
            return float(np.frombuffer(struct.pack("<H", bits & 0xFFFF), dtype="<f2")[0])
        if kind in (_FLOAT, _DOUBLE):
            # A double is inlined only when a float holds it exactly, and is held as that float.
            return struct.unpack("<f", struct.pack("<I", bits))[0]
        if kind in (_TOKEN, _ASSET_PATH):
            return self.token(bits)
        if kind == _STRING:
            return self.string(bits)
        if kind in _MATRIX_SIDE:
            # A matrix with small whole numbers down its diagonal and nothing else: one byte each.
            side = _MATRIX_SIDE[kind]
            diagonal = np.frombuffer(struct.pack("<I", bits), dtype="i1")[:side].astype(np.float64)
            return np.diag(diagonal).reshape(-1)
        if kind in _NUMBERS and kind not in _QUATERNIONS:
            # A vector of small whole numbers: one signed byte each.
            parts = _NUMBERS[kind][1]
            return np.frombuffer(struct.pack("<I", bits), dtype="i1")[:parts].astype(np.float64)
        return None

    def _stored(self, kind: int, payload: int, nested: bool) -> Any:
        """A value held somewhere in the file; `payload` is where."""
        cursor = _Cursor(self.data, payload, self.size)
        if kind in (_INT64, _UINT64, _DOUBLE):
            return cursor.array(_NUMBERS[kind][0], 1)[0].item()
        if kind in _NUMBERS and _NUMBERS[kind][1] > 1:
            dtype, parts = _NUMBERS[kind]
            numbers = cursor.array(dtype, parts).astype(np.float64)
            if kind in _QUATERNIONS:
                # In the file the real part is last; USD text writes it first.
                numbers = np.roll(numbers, 1)
            return numbers
        if kind == _TOKEN_VECTOR:
            return [self.token(i) for i in cursor.array("<u4", self._array_size(cursor.u64())).tolist()]
        if kind == _STRING_VECTOR:
            return [self.string(i) for i in cursor.array("<u4", self._array_size(cursor.u64())).tolist()]
        if kind == _DOUBLE_VECTOR:
            return cursor.array("<f8", self._array_size(cursor.u64()))
        if kind == _TIME_SAMPLES and not nested:
            return self._first_sample(cursor)
        return None

    def _first_sample(self, cursor: _Cursor) -> Any:
        """The first of a value's time samples.

        Written as: how far on the times are, the times (one ValueRep), how far
        on the values are, how many there are, then a ValueRep for each.
        """
        start = cursor.at
        cursor.seek(start + cursor.i64())
        cursor.u64()                        # the times: not needed
        start = cursor.at
        cursor.seek(start + cursor.i64())
        if cursor.u64() == 0:
            return None
        return self.value(cursor.u64(), nested=True)

    @staticmethod
    def _array_size(count: int) -> int:
        if count > MAX_ARRAY_ITEMS:
            raise unreadable("an array in it is larger than this will read.")
        return count

    def _array(self, kind: int, payload: int, packed: bool) -> Any:
        row = _NUMBERS.get(kind)
        if payload == 0:                    # how an empty array is written
            if kind == _TOKEN:
                return []
            if row is None:
                return None
            return np.zeros((0, row[1]) if row[1] > 1 else 0, dtype=row[0])
        if kind != _TOKEN and row is None:
            return None

        cursor = _Cursor(self.data, payload, self.size)
        if self.version < (0, 5, 0):
            cursor.u32()                    # an array's rank, which was always 1
        count = self._array_size(cursor.u32() if self.version < (0, 7, 0) else cursor.u64())
        if kind == _TOKEN:
            return [self.token(i) for i in cursor.array("<u4", count).tolist()]

        dtype, parts = row
        if packed and count >= _MIN_PACKED_ARRAY:
            if kind in _PACKED_INTEGERS and self.version >= (0, 5, 0):
                return cursor.integers(count, wide=kind in (_INT64, _UINT64)).view(dtype)
            if kind in _PACKED_FLOATS and self.version >= (0, 6, 0):
                how = cursor.take(1)
                if how == b"i":             # every one a whole number: packed as integers
                    return cursor.integers(count).astype(dtype)
                if how == b"t":             # few different values: a table of them, and an index for each
                    table = cursor.array(dtype, cursor.u32())
                    picks = cursor.integers(count).view("<u4")
                    if not len(table) or int(picks.max()) >= len(table):
                        raise _damaged()
                    return table[picks]
                raise _damaged()
        if count * parts > MAX_ARRAY_ITEMS * 4:
            raise unreadable("an array in it is larger than this will read.")
        numbers = cursor.array(dtype, count * parts)
        return numbers.reshape(count, parts) if parts > 1 else numbers


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

def _quiet(crate: _Crate, rep: Optional[int]) -> Any:
    """A value, or None when there is none or it cannot be read. Never an error."""
    if rep is None:
        return None
    try:
        return crate.value(rep)
    except _DECODE_ERRORS:
        return None


def _attribute(crate: _Crate, field_set: int) -> Any:
    """An attribute's value: its default, or with none its first time sample."""
    fields = crate.fields(field_set)
    rep = fields.get("default")
    value = _quiet(crate, rep)
    if value is None:
        value = _quiet(crate, fields.get("timeSamples"))
    return value


def _fill(prim: _Prim, crate: _Crate, attributes: Dict[str, int]) -> bool:
    """Give a prim its points, faces and transform ops. False if it has points that could not be read."""
    readable = True
    for name, field_set in attributes.items():
        value = _attribute(crate, field_set)
        if name == "points":
            if isinstance(value, np.ndarray) and value.ndim == 2 and value.shape[1] == 3:
                prim.points = value.astype(np.float64)
            else:
                readable = False
        elif name in ("faceVertexIndices", "faceVertexCounts"):
            if isinstance(value, np.ndarray) and value.ndim == 1 and value.dtype.kind in "iu":
                if name == "faceVertexIndices":
                    prim.indices = value.astype(np.int64)
                else:
                    prim.counts = value.astype(np.int64)
        elif name == "xformOpOrder":
            if isinstance(value, list):
                prim.order = [str(item) for item in value]
        else:
            op = None
            if value is not None and not isinstance(value, (str, list)):
                try:
                    numbers = np.asarray(value, dtype=np.float64).reshape(-1)
                    op = _op_matrix_numbers(name, numbers) if np.isfinite(numbers).all() else None
                except _DECODE_ERRORS:
                    op = None
            if op is None:
                prim.unread_ops += 1
            else:
                prim.ops[name] = op
    return readable


def _read(content: bytes, source_file: str) -> ScanMesh:
    crate = _Crate(content)

    # Which attributes of which prim are wanted: the mesh's own and the transform ops.
    wanted: Dict[int, Dict[str, int]] = {}
    for path, (field_set, kind) in crate.specs.items():
        if kind != _SPEC_ATTRIBUTE or not crate.is_property[path]:
            continue
        name = crate.name[path]
        if name in _MESH_ATTRIBUTES or name.startswith("xformOp:"):
            wanted.setdefault(crate.parent[path], {})[name] = field_set

    root = crate.root
    root_fields = crate.fields(crate.specs[root][0]) if root in crate.specs else {}
    up = _quiet(crate, root_fields.get("upAxis"))
    up_axis = up.lower() if isinstance(up, str) and up.lower() in ("y", "z") else None
    units = _quiet(crate, root_fields.get("metersPerUnit"))
    metres_per_unit = (
        float(units) if isinstance(units, (int, float)) and not isinstance(units, bool)
        and math.isfinite(units) and units > 0 else None
    )

    def children(path: int, fields: Dict[str, int]) -> List[int]:
        """A prim's children in the order the file gives them (`primChildren`)."""
        names = _quiet(crate, fields.get("primChildren"))
        below = crate.children.get(path, [])
        if not isinstance(names, list):
            return below
        by_name = {crate.name[child]: child for child in below}
        return [by_name[name] for name in names if name in by_name]

    prims: List[_Prim] = []
    meshes: List[_Prim] = []
    unreadable_meshes = 0
    seen = set()
    # Depth first, as USD walks a stage, with the prims still to visit in a list.
    waiting: List[Tuple[int, Optional[_Prim]]] = (
        [(child, None) for child in reversed(children(root, root_fields))] if root >= 0 else []
    )
    while waiting:
        path, parent = waiting.pop()
        if path in seen:
            continue
        seen.add(path)
        spec = crate.specs.get(path)
        if spec is None or spec[1] != _SPEC_PRIM:
            continue
        fields = crate.fields(spec[0])
        # Left out, as USD leaves them out of a stage: a prim that is not
        # defined here (`over`, `class`) or is switched off. Only when the file
        # says so outright; a prim that does not say is read.
        if _quiet(crate, fields.get("specifier")) in (_SPECIFIER_OVER, _SPECIFIER_CLASS):
            continue
        if _quiet(crate, fields.get("active")) is False:
            continue
        prim = _Prim(crate.name[path], parent)
        if not _fill(prim, crate, wanted.get(path, {})):
            unreadable_meshes += 1
        prims.append(prim)
        if _quiet(crate, fields.get("typeName")) == "Mesh":
            meshes.append(prim)
        waiting.extend((child, prim) for child in reversed(children(path, fields)))

    # The prims typed Mesh. A layer with none of those that holds points (a
    # point cloud, say) has whatever holds them read instead.
    holders = [prim for prim in meshes if prim.points is not None and len(prim.points)] or prims
    if unreadable_meshes and not any(prim.points is not None and len(prim.points) for prim in holders):
        raise unreadable("the points of its meshes could not be read.")

    mesh = _mesh_from_prims(
        holders, sum(prim.unread_ops for prim in prims), "usdc", "binary USD layer", source_file,
        up_axis, metres_per_unit,
    )
    mesh.notes.append(f"The layer is USD crate version {_version_words(crate.version)}.")
    if crate.version[:2] > NEWEST_VERSION[:2]:
        mesh.notes.append(
            f"That is newer than the reader was written for (0.{NEWEST_VERSION[1]}); "
            "check the room against the venue."
        )
    if unreadable_meshes:
        mesh.notes.append(
            f"{unreadable_meshes} mesh{'es' if unreadable_meshes != 1 else ''} in the layer had points "
            "that could not be read and were left out."
        )
    return mesh


def parse_usdc(content: bytes, source_file: str = "") -> ScanMesh:
    """The meshes of a binary USD (crate) layer, in the layer's own units and axes."""
    try:
        return _read(content, source_file)
    except RoomScanError:
        raise
    except _DECODE_ERRORS:
        raise _damaged() from None
