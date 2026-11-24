"""
Scan Meshes
===========

Reads what a phone scanning app exports into one shape: points, the triangles
between them where the file has any, and whatever the file itself says about
its axes and units.

    OBJ    text; `v` and `f` lines. Polygons are cut into triangles.
    PLY    ASCII, binary little-endian and binary big-endian. A PLY with no
           faces is a point cloud and is read as one.

USD and RoomPlan are in usd.py, binary USD in usdc.py. Everything is numpy and the standard library:
no mesh library is needed for the little that is read here.

Nothing is turned, scaled or moved in this module. The file's own axes and
units are kept, and extract.py decides what they are.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# A phone scan of a large room is a few million points. Past this the file is
# not a room scan, and the arrays would not fit beside a running show.
MAX_VERTICES = 20_000_000
MAX_FACES = 40_000_000


class RoomScanError(ValueError):
    """The file cannot be read as a room scan. The message is for the operator."""


@dataclass
class ScanMesh:
    """A scan as read: the file's own axes and units."""

    vertices: np.ndarray                       # (N, 3) float64
    faces: Optional[np.ndarray] = None         # (M, 3) int64 triangles, or None for a point cloud
    normals: Optional[np.ndarray] = None       # (N, 3) per-vertex, where a point cloud carries them
    format: str = ""
    source_file: str = ""
    # What the file declares, where it declares anything. OBJ and PLY do not.
    up_axis: Optional[str] = None              # "y" or "z"
    metres_per_unit: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    # Things the file names outright (RoomPlan's objects), for the report.
    objects: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_point_cloud(self) -> bool:
        return self.faces is None or len(self.faces) == 0


def _checked(mesh: ScanMesh) -> ScanMesh:
    """The mesh with unusable rows dropped, or an error if nothing is left."""
    vertices = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3)
    if len(vertices) > MAX_VERTICES:
        raise RoomScanError(
            f"The scan has {len(vertices):,} points; the most this reads is {MAX_VERTICES:,}. "
            "Export it at a lower detail."
        )
    finite = np.isfinite(vertices).all(axis=1)
    faces = mesh.faces
    if faces is not None and len(faces):
        faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
        if len(faces) > MAX_FACES:
            raise RoomScanError(
                f"The scan has {len(faces):,} triangles; the most this reads is {MAX_FACES:,}. "
                "Export it at a lower detail."
            )
        in_range = ((faces >= 0) & (faces < len(vertices))).all(axis=1)
        usable = in_range.copy()
        usable[in_range] = finite[faces[in_range]].all(axis=1)
        dropped = int(len(faces) - usable.sum())
        if dropped:
            mesh.notes.append(f"{dropped} triangles pointed at missing or unreadable points and were left out.")
        faces = faces[usable]
        if not len(faces):
            faces = None
    else:
        faces = None

    if faces is None:
        # A point cloud: only the readable points count.
        if mesh.normals is not None and len(mesh.normals) == len(vertices):
            mesh.normals = np.asarray(mesh.normals, dtype=np.float64)[finite]
        else:
            mesh.normals = None
        vertices = vertices[finite]
    elif mesh.normals is not None and len(mesh.normals) != len(vertices):
        mesh.normals = None

    if len(vertices) < 3:
        raise RoomScanError("The file holds no usable points: there is no room in it to read.")
    mesh.vertices = vertices
    mesh.faces = faces
    return mesh


def fan(indices: List[int]) -> List[Tuple[int, int, int]]:
    """A polygon as triangles round its first corner."""
    return [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]


# ---------------------------------------------------------------------------
# OBJ
# ---------------------------------------------------------------------------

def parse_obj(content: bytes, source_file: str = "") -> ScanMesh:
    """Wavefront OBJ: `v x y z` and `f a b c ...` (with or without /vt/vn)."""
    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    bad_lines = 0
    for line in content.splitlines():
        if line.startswith(b"v "):
            parts = line.split()
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except (IndexError, ValueError):
                bad_lines += 1
        elif line.startswith(b"f "):
            parts = line.split()[1:]
            try:
                corners = []
                for part in parts:
                    index = int(part.split(b"/", 1)[0])
                    # Counted from 1; a negative index counts back from the last point read.
                    corners.append(index - 1 if index > 0 else len(vertices) + index)
            except ValueError:
                bad_lines += 1
                continue
            if len(corners) >= 3:
                faces.extend(fan(corners))

    if not vertices:
        raise RoomScanError("No `v` lines were found: this is not an OBJ mesh.")
    mesh = ScanMesh(
        vertices=np.array(vertices, dtype=np.float64),
        faces=np.array(faces, dtype=np.int64) if faces else None,
        format="obj",
        source_file=source_file,
    )
    if bad_lines:
        mesh.notes.append(f"{bad_lines} lines of the OBJ could not be read and were left out.")
    return _checked(mesh)


# ---------------------------------------------------------------------------
# PLY
# ---------------------------------------------------------------------------

_PLY_TYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
    "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
    "float": "f4", "float32": "f4", "double": "f8", "float64": "f8",
}


@dataclass
class _PlyProperty:
    name: str
    dtype: str                      # numpy code without byte order
    count_dtype: Optional[str] = None   # set for a list property


@dataclass
class _PlyElement:
    name: str
    count: int
    properties: List[_PlyProperty] = field(default_factory=list)

    @property
    def has_list(self) -> bool:
        return any(p.count_dtype for p in self.properties)


def _ply_header(content: bytes) -> Tuple[str, List[_PlyElement], int]:
    """(format, elements, offset of the first byte after the header)."""
    marker = content.find(b"end_header")
    if not content.startswith(b"ply") or marker < 0:
        raise RoomScanError("The PLY header is missing or cut short.")
    end = content.find(b"\n", marker)
    if end < 0:
        raise RoomScanError("The PLY ends at its header: it holds no points.")
    header = content[:marker].decode("ascii", errors="replace")

    fmt = ""
    elements: List[_PlyElement] = []
    for raw in header.splitlines()[1:]:
        words = raw.split()
        if not words or words[0] in ("comment", "obj_info"):
            continue
        if words[0] == "format" and len(words) >= 2:
            fmt = words[1]
        elif words[0] == "element" and len(words) >= 3:
            try:
                elements.append(_PlyElement(words[1], int(words[2])))
            except ValueError:
                raise RoomScanError(f"The PLY header has an element count that is not a number: '{raw.strip()}'.")
        elif words[0] == "property" and elements:
            try:
                if words[1] == "list":
                    elements[-1].properties.append(
                        _PlyProperty(words[4], _PLY_TYPES[words[3]], _PLY_TYPES[words[2]])
                    )
                else:
                    elements[-1].properties.append(_PlyProperty(words[2], _PLY_TYPES[words[1]]))
            except (IndexError, KeyError):
                raise RoomScanError(f"The PLY header has a property this cannot read: '{raw.strip()}'.")

    if fmt not in ("ascii", "binary_little_endian", "binary_big_endian"):
        raise RoomScanError(f"The PLY says its format is '{fmt or 'nothing'}', which this cannot read.")
    return fmt, elements, end + 1


def _vertex_columns(element: _PlyElement, table: np.ndarray) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """(positions, normals or None) out of a vertex table with named columns."""
    names = [p.name for p in element.properties]
    if not all(axis in names for axis in ("x", "y", "z")):
        raise RoomScanError("The PLY's vertices have no x, y and z properties.")
    positions = np.stack([np.asarray(table[axis], dtype=np.float64) for axis in ("x", "y", "z")], axis=1)
    normals = None
    if all(axis in names for axis in ("nx", "ny", "nz")):
        normals = np.stack([np.asarray(table[axis], dtype=np.float64) for axis in ("nx", "ny", "nz")], axis=1)
    return positions, normals


def _ply_binary(content: bytes, offset: int, elements: List[_PlyElement], order: str):
    positions = normals = None
    faces: Optional[np.ndarray] = None
    for element in elements:
        if not element.has_list:
            dtype = np.dtype([(p.name, order + p.dtype) for p in element.properties])
            size = dtype.itemsize * element.count
            if offset + size > len(content):
                raise RoomScanError(f"The PLY is cut short: its '{element.name}' data runs past the end of the file.")
            if element.name == "vertex":
                table = np.frombuffer(content, dtype=dtype, count=element.count, offset=offset)
                positions, normals = _vertex_columns(element, table)
            offset += size
            continue

        triangles, offset = _ply_binary_lists(content, offset, element, order)
        if element.name == "face":
            faces = triangles
    return positions, normals, faces


def _ply_binary_lists(content: bytes, offset: int, element: _PlyElement, order: str):
    """Read an element that holds a list (the faces). Returns (triangles, new offset).

    A scan's faces are nearly always all triangles, which is a fixed-size
    record numpy can read in one go. Anything else is walked a face at a time.
    """
    lists = [p for p in element.properties if p.count_dtype]
    if len(lists) == 1 and element.count:
        for corners in (3, 4):
            fields = []
            for p in element.properties:
                if p.count_dtype:
                    fields.append(("n", order + p.count_dtype))
                    fields.append(("v", order + p.dtype, (corners,)))
                else:
                    fields.append((p.name, order + p.dtype))
            dtype = np.dtype(fields)
            size = dtype.itemsize * element.count
            if offset + size > len(content):
                continue
            table = np.frombuffer(content, dtype=dtype, count=element.count, offset=offset)
            if (table["n"] == corners).all():
                found = np.asarray(table["v"], dtype=np.int64)
                if corners == 4:
                    found = np.concatenate([found[:, [0, 1, 2]], found[:, [0, 2, 3]]])
                return found, offset + size

    triangles: List[Tuple[int, int, int]] = []
    for _ in range(element.count):
        for p in element.properties:
            if not p.count_dtype:
                offset += np.dtype(p.dtype).itemsize
                continue
            count_type = np.dtype(order + p.count_dtype)
            if offset + count_type.itemsize > len(content):
                raise RoomScanError("The PLY is cut short in its face list.")
            n = int(np.frombuffer(content, dtype=count_type, count=1, offset=offset)[0])
            offset += count_type.itemsize
            item = np.dtype(order + p.dtype)
            if offset + item.itemsize * n > len(content):
                raise RoomScanError("The PLY is cut short in its face list.")
            corners = np.frombuffer(content, dtype=item, count=n, offset=offset)
            offset += item.itemsize * n
            if p is lists[0] and n >= 3:
                triangles.extend(fan([int(c) for c in corners]))
    return (np.array(triangles, dtype=np.int64) if triangles else None), offset


def _ply_ascii(content: bytes, offset: int, elements: List[_PlyElement]):
    lines = content[offset:].decode("ascii", errors="replace").splitlines()
    positions = normals = None
    faces: List[Tuple[int, int, int]] = []
    at = 0
    for element in elements:
        rows = lines[at:at + element.count]
        at += element.count
        if len(rows) < element.count:
            raise RoomScanError(f"The PLY is cut short: its '{element.name}' data runs past the end of the file.")
        if element.name == "vertex":
            if element.has_list:
                raise RoomScanError("The PLY's vertices hold a list property, which this cannot read.")
            width = len(element.properties)
            try:
                flat = np.array(" ".join(rows).split(), dtype=np.float64)
                table_rows = flat.reshape(element.count, width)
            except ValueError:
                raise RoomScanError("The PLY's vertex rows do not match its header.")
            table = {p.name: table_rows[:, i] for i, p in enumerate(element.properties)}
            positions, normals = _vertex_columns(element, table)  # type: ignore[arg-type]
        elif element.name == "face":
            # The first list on the row is the corners; that is how every exporter writes it.
            lead = 0
            for p in element.properties:
                if p.count_dtype:
                    break
                lead += 1
            for row in rows:
                words = row.split()
                try:
                    n = int(words[lead])
                    corners = [int(float(w)) for w in words[lead + 1:lead + 1 + n]]
                except (IndexError, ValueError):
                    continue
                if len(corners) >= 3:
                    faces.extend(fan(corners))
    return positions, normals, (np.array(faces, dtype=np.int64) if faces else None)


def parse_ply(content: bytes, source_file: str = "") -> ScanMesh:
    """Stanford PLY, ASCII or binary, with or without faces."""
    fmt, elements, offset = _ply_header(content)
    if not any(e.name == "vertex" for e in elements):
        raise RoomScanError("The PLY has no vertex element: it holds no points.")
    for element in elements:
        if element.count < 0 or element.count > max(MAX_VERTICES, MAX_FACES):
            raise RoomScanError(f"The PLY says it holds {element.count:,} '{element.name}' rows, which this cannot read.")

    if fmt == "ascii":
        positions, normals, faces = _ply_ascii(content, offset, elements)
    else:
        order = "<" if fmt == "binary_little_endian" else ">"
        positions, normals, faces = _ply_binary(content, offset, elements, order)

    if positions is None or not len(positions):
        raise RoomScanError("The PLY holds no points.")
    mesh = ScanMesh(
        vertices=positions, faces=faces, normals=normals,
        format="ply", source_file=source_file,
    )
    if faces is None:
        mesh.notes.append("The PLY has no faces: it was read as a point cloud.")
    return _checked(mesh)
