"""
glTF 2.0 scans
==============

Polycam, Scaniverse and most LiDAR apps hand a scan over as glTF by default:

    .glb    one binary file: a 12-byte header, a JSON part and a BIN part
    .gltf   the JSON on its own, with its buffers inside it as base64 `data:`
            URIs. A .gltf that keeps its mesh in a separate .bin is read when
            the two arrive together in a zip (bundle.py hands this reader a
            way to fetch the file a `uri` names). Sent alone it cannot be
            read: the message says to send the zip, or to export .glb.

What is read: every mesh the default scene draws, each primitive's POSITION
(float, three to a point) and its indices, with the transforms of the nodes
above it applied (a `matrix`, or translation, rotation and scale). A mesh drawn
by several nodes is read once for each. Triangles, triangle strips and triangle
fans become triangles. A file with no triangle at all is a point cloud, of the
points of its point and line primitives, as a PLY with no faces is; beside a
mesh those are left out.

What is refused, in words that say what to do: Draco and meshopt compression
(there is no decoder in the standard library), quantised positions, sparse
accessors, a file that is cut short or does not hold together, and a scan past
the limits in mesh.py.

glTF is Y-up and in metres by definition, and the mesh says so (`up_axis`,
`metres_per_unit`), as a USD layer does. Nothing else is turned or scaled
here: extract.py decides the rest, and the operator's own units and up axis
still win over the file's.

Standard library and numpy only.
"""

import base64
import binascii
import json
import struct
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from .mesh import MAX_FACES, MAX_VERTICES, RoomScanError, ScanMesh, _checked

GLB_MAGIC = b"glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942

DRACO = "KHR_draco_mesh_compression"
MESHOPT = "EXT_meshopt_compression"
QUANTIZED = "KHR_mesh_quantization"

_FLOAT = 5126
_INDEX_TYPES = {5121: "u1", 5123: "<u2", 5125: "<u4"}
_COMPONENT_NAMES = {
    5120: "BYTE", 5121: "UNSIGNED_BYTE", 5122: "SHORT", 5123: "UNSIGNED_SHORT",
    5125: "UNSIGNED_INT", 5126: "FLOAT",
}

_POINTS, _TRIANGLES, _STRIP, _FAN = 0, 4, 5, 6

# Past this many nodes the file is not a scan of a room.
MAX_NODES = 1_000_000

# Fetches the file a buffer's `uri` names, for a glTF that arrived with its neighbours.
Resolve = Callable[[str], bytes]


def _compressed_message(kind: str, what: str) -> str:
    return (
        f"This {kind} is packed with {what}, which this cannot unpack. "
        "Export the scan again without Draco or mesh compression, or export OBJ."
    )


def _damaged(kind: str, what: str) -> RoomScanError:
    return RoomScanError(
        f"The {kind} is damaged or cut short: {what}. Export the scan again, or export OBJ."
    )


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Reader:
    """One glTF document and its buffers, read into world-space triangles and points."""

    def __init__(self, doc: Any, binary: Optional[memoryview], kind: str, resolve: Optional[Resolve] = None):
        if not isinstance(doc, dict):
            raise _damaged(kind, "its JSON is not a glTF document")
        self.doc: Dict[str, Any] = doc
        self.binary = binary
        self.kind = kind
        self.resolve = resolve
        self._buffers: Dict[int, Any] = {}

        self.mesh_vertices: List[np.ndarray] = []
        self.mesh_faces: List[np.ndarray] = []
        self.mesh_points = 0          # points in the triangle primitives read so far
        self.faces = 0
        self.cloud: List[np.ndarray] = []
        self.cloud_points = 0
        self.parts = 0
        self.line_parts = 0
        self.bad_triangles = 0

    # --- the document -------------------------------------------------------

    def _list(self, name: str) -> List[Any]:
        value = self.doc.get(name)
        if value is None:
            return []
        if not isinstance(value, list):
            raise _damaged(self.kind, f"its `{name}` is not a list")
        return value

    def _item(self, name: str, index: Any) -> Dict[str, Any]:
        items = self._list(name)
        if not _whole(index) or not 0 <= index < len(items) or not isinstance(items[index], dict):
            raise _damaged(self.kind, f"it points at entry {index!r} of `{name}`, which is not in the file")
        return items[index]

    def _size(self, holder: Dict[str, Any], key: str) -> int:
        value = holder.get(key, 0)
        if not _whole(value) or value < 0:
            raise _damaged(self.kind, f"`{key}` is {value!r}, which is not a size")
        return value

    def refuse_what_cannot_be_unpacked(self) -> None:
        required = self.doc.get("extensionsRequired") or []
        if not isinstance(required, list):
            raise _damaged(self.kind, "its `extensionsRequired` is not a list")
        if DRACO in required:
            raise RoomScanError(_compressed_message(self.kind, f"Draco mesh compression ({DRACO})"))
        if MESHOPT in required:
            raise RoomScanError(_compressed_message(self.kind, f"meshopt compression ({MESHOPT})"))

    # --- buffers and accessors ----------------------------------------------

    def _buffer(self, index: Any):
        if _whole(index) and index in self._buffers:
            return self._buffers[index]
        entry = self._item("buffers", index)
        uri = entry.get("uri")
        if uri is None:
            if index != 0 or self.binary is None:
                raise _damaged(self.kind, f"buffer {index} has no data in the file")
            data: Any = self.binary
        elif not isinstance(uri, str):
            raise _damaged(self.kind, f"buffer {index} has a `uri` that is not text")
        elif uri[:5].lower() == "data:":
            head, comma, body = uri.partition(",")
            if not comma or ";base64" not in head.lower():
                raise _damaged(self.kind, f"buffer {index} is a data URI that is not base64")
            try:
                data = base64.b64decode(body, validate=False)
            except (binascii.Error, ValueError):
                raise _damaged(self.kind, f"buffer {index} is base64 that cannot be read")
        elif self.resolve is not None:
            # The file came in a zip: the buffer is another file of it.
            data = self.resolve(uri)
        else:
            name = uri if len(uri) <= 60 else uri[:57] + "..."
            raise RoomScanError(
                f"This {self.kind} keeps its mesh in a separate file ('{name}'), and only one file was "
                "sent. Zip the two together (with any other .bin beside them) and send the zip, or "
                "export the scan as .glb, which is the whole scan in one file, or export OBJ."
            )
        self._buffers[index] = data
        return data

    def _accessor(self, index: Any, width: int, dtype: str, what: str) -> np.ndarray:
        """An accessor's rows as they lie in the buffer: (count, width), not copied."""
        accessor = self._item("accessors", index)
        count = self._size(accessor, "count")
        if "bufferView" not in accessor or accessor["bufferView"] is None:
            raise _damaged(self.kind, f"the {what} have no data in the file")
        view = self._item("bufferViews", accessor["bufferView"])
        data = self._buffer(view.get("buffer"))

        kind = np.dtype(dtype)
        item = kind.itemsize * width
        stride = self._size(view, "byteStride") or item
        if stride < item:
            raise _damaged(self.kind, f"the {what} are packed closer together ({stride} bytes) than they are wide")
        view_start = self._size(view, "byteOffset")
        start = view_start + self._size(accessor, "byteOffset")
        if count == 0:
            return np.zeros((0, width), dtype=kind)
        end = start + (count - 1) * stride + item
        if end > view_start + self._size(view, "byteLength") or end > len(data):
            raise _damaged(self.kind, f"the {what} run past the end of the data")
        return np.ndarray((count, width), dtype=kind, buffer=data, offset=start, strides=(stride, kind.itemsize))

    def _positions(self, primitive: Dict[str, Any], index: Any) -> np.ndarray:
        accessor = self._item("accessors", index)
        if accessor.get("sparse") is not None:
            raise RoomScanError(
                f"This {self.kind} stores its points as a sparse accessor, which this does not read. "
                "Export the scan again as a plain .glb, or export OBJ."
            )
        extensions = primitive.get("extensions")
        if accessor.get("bufferView") is None and isinstance(extensions, dict) and DRACO in extensions:
            raise RoomScanError(_compressed_message(self.kind, f"Draco mesh compression ({DRACO})"))
        component = accessor.get("componentType")
        if accessor.get("type") != "VEC3":
            raise _damaged(self.kind, f"its points are {accessor.get('type')!r}, not three numbers each")
        if component != _FLOAT:
            name = _COMPONENT_NAMES.get(component, repr(component))
            raise RoomScanError(
                f"This {self.kind} stores its points as {name} whole numbers ({QUANTIZED}), which this does "
                "not read. Export the scan again without quantisation or mesh compression, or export OBJ."
            )
        return self._accessor(index, 3, "<f4", "points")

    def _indices(self, index: Any) -> np.ndarray:
        accessor = self._item("accessors", index)
        if accessor.get("sparse") is not None:
            raise RoomScanError(
                f"This {self.kind} stores its triangles as a sparse accessor, which this does not read. "
                "Export the scan again as a plain .glb, or export OBJ."
            )
        dtype = _INDEX_TYPES.get(accessor.get("componentType"))
        if dtype is None or accessor.get("type") != "SCALAR":
            raise _damaged(self.kind, "its triangle indices are not whole numbers of a kind glTF allows")
        return self._accessor(index, 1, dtype, "triangle indices")[:, 0].astype(np.int64)

    # --- primitives -----------------------------------------------------------

    def _primitive(self, primitive: Any, world: np.ndarray) -> None:
        if not isinstance(primitive, dict):
            raise _damaged(self.kind, "a mesh primitive is not an object")
        attributes = primitive.get("attributes")
        if not isinstance(attributes, dict) or "POSITION" not in attributes:
            return                  # nothing to place: glTF allows a primitive with no points
        mode = primitive.get("mode", _TRIANGLES)

        local = self._positions(primitive, attributes["POSITION"])
        count = len(local)
        if mode not in (_TRIANGLES, _STRIP, _FAN):
            # Points, and the ends of lines: no surface, so only their points
            # are kept, and used only when the file has no triangle at all.
            if mode != _POINTS:
                self.line_parts += 1
            self.cloud_points += count
            self._within(self.cloud_points, MAX_VERTICES, "points")
            if count:
                self.cloud.append(_placed(local, world))
            return

        if primitive.get("indices") is None:
            corners = np.arange(count, dtype=np.int64)
        else:
            corners = self._indices(primitive["indices"])
        triangles = _triangles(corners, mode)
        # Checked against this primitive's own points, before it is numbered in
        # with the rest: a bad index must not land on another part's point.
        good = (triangles < count).all(axis=1)
        self.bad_triangles += int(len(triangles) - good.sum())
        triangles = triangles[good]
        if not len(triangles):
            return

        self.faces += len(triangles)
        self._within(self.faces, MAX_FACES, "triangles")
        self._within(self.mesh_points + count, MAX_VERTICES, "points")
        self.mesh_vertices.append(_placed(local, world))
        self.mesh_faces.append(triangles + self.mesh_points)
        self.mesh_points += count
        self.parts += 1

    def _within(self, total: int, most: int, what: str) -> None:
        # Before anything is copied: a small file can draw one mesh ten thousand times.
        if total > most:
            raise RoomScanError(
                f"The scan has more than {most:,} {what}, the most this reads. Export it at a lower detail."
            )

    # --- the scene ------------------------------------------------------------

    def _roots(self) -> List[Any]:
        scenes = self._list("scenes")
        if scenes:
            chosen = self.doc.get("scene", 0)
            if chosen is None:
                chosen = 0
            roots = self._item("scenes", chosen).get("nodes") or []
            if not isinstance(roots, list):
                raise _damaged(self.kind, "its scene's `nodes` is not a list")
            return roots
        # No scene: every node that is nobody's child.
        nodes = self._list("nodes")
        children: Set[Any] = set()
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("children"), list):
                children.update(child for child in node["children"] if _whole(child))
        return [index for index in range(len(nodes)) if index not in children]

    def _local(self, node: Dict[str, Any]) -> np.ndarray:
        if node.get("matrix") is not None:
            # Sixteen numbers, column by column.
            matrix = self._numbers(node["matrix"], 16, "matrix").reshape(4, 4).T
            return matrix.copy()
        matrix = np.eye(4)
        scale = self._numbers(node.get("scale", (1.0, 1.0, 1.0)), 3, "scale")
        matrix[:3, :3] = _rotation(self._numbers(node.get("rotation", (0.0, 0.0, 0.0, 1.0)), 4, "rotation")) * scale
        matrix[:3, 3] = self._numbers(node.get("translation", (0.0, 0.0, 0.0)), 3, "translation")
        return matrix

    def _numbers(self, value: Any, count: int, what: str) -> np.ndarray:
        if (
            not isinstance(value, (list, tuple)) or len(value) != count
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        ):
            raise _damaged(self.kind, f"a node's `{what}` is not {count} numbers")
        numbers = np.array(value, dtype=np.float64)
        if not np.isfinite(numbers).all():
            raise _damaged(self.kind, f"a node's `{what}` holds a number that is not finite")
        return numbers

    def read_scene(self) -> None:
        nodes = self._list("nodes")
        if not nodes:
            # Meshes that nothing places: read where they lie.
            for mesh in self._list("meshes"):
                self._mesh(mesh, np.eye(4))
            return
        if len(nodes) > MAX_NODES:
            raise RoomScanError(
                f"The {self.kind} has {len(nodes):,} nodes, which is not a scan of a room. Export OBJ instead."
            )

        seen: Set[int] = set()
        stack: List[Tuple[Any, np.ndarray]] = [(root, np.eye(4)) for root in reversed(self._roots())]
        while stack:
            index, parent = stack.pop()
            node = self._item("nodes", index)
            if index in seen:
                # glTF's nodes are a tree. A node reached twice is a loop, or a file that is not one.
                raise _damaged(self.kind, f"node {index} is reached twice, so its nodes loop back on themselves")
            seen.add(index)
            world = parent @ self._local(node)
            if node.get("mesh") is not None:
                self._mesh(self._item("meshes", node["mesh"]), world)
            children = node.get("children") or []
            if not isinstance(children, list):
                raise _damaged(self.kind, f"node {index}'s `children` is not a list")
            stack.extend((child, world) for child in reversed(children))

    def _mesh(self, mesh: Any, world: np.ndarray) -> None:
        if not isinstance(mesh, dict):
            raise _damaged(self.kind, "a mesh is not an object")
        primitives = mesh.get("primitives") or []
        if not isinstance(primitives, list):
            raise _damaged(self.kind, "a mesh's `primitives` is not a list")
        for primitive in primitives:
            self._primitive(primitive, world)

    # --- the answer -----------------------------------------------------------

    def mesh(self, fmt: str, source_file: str) -> ScanMesh:
        notes: List[str] = []
        if self.mesh_faces:
            found = ScanMesh(
                vertices=np.concatenate(self.mesh_vertices),
                faces=np.concatenate(self.mesh_faces),
                format=fmt, source_file=source_file,
            )
            notes.append(
                f"Read {self.parts} mesh part{'s' if self.parts != 1 else ''} from the {self.kind}, "
                "each placed by the nodes above it."
            )
            if self.cloud_points:
                notes.append(
                    f"{self.cloud_points:,} loose points and line ends beside the mesh were left out."
                )
        elif self.cloud:
            found = ScanMesh(vertices=np.concatenate(self.cloud), format=fmt, source_file=source_file)
            holds = "lines" if self.line_parts and self.line_parts == len(self.cloud) else "points"
            notes.append(f"The {self.kind} has {holds} and no triangles: it was read as a point cloud.")
        else:
            raise RoomScanError(
                f"The {self.kind} holds no triangles or points: there is no room in it to read. "
                "Check that the export includes the mesh, or export OBJ."
            )
        found.up_axis = "y"
        found.metres_per_unit = 1.0
        notes.append("glTF is Y-up and in metres by definition, so it was read that way.")
        if self.bad_triangles:
            notes.append(
                f"{self.bad_triangles} triangles pointed at points their mesh part does not have and were left out."
            )
        found.notes.extend(notes)
        return _checked(found)


def _placed(local: np.ndarray, world: np.ndarray) -> np.ndarray:
    """A primitive's points where its nodes put them."""
    return local.astype(np.float64) @ world[:3, :3].T + world[:3, 3]


def _rotation(quaternion: np.ndarray) -> np.ndarray:
    """glTF's (x, y, z, w) as a 3 by 3 rotation."""
    length = float(np.linalg.norm(quaternion))
    if length < 1e-12:
        return np.eye(3)
    x, y, z, w = quaternion / length
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _triangles(corners: np.ndarray, mode: int) -> np.ndarray:
    """(M, 3) triangles out of a primitive's run of corners."""
    if mode == _TRIANGLES:
        whole = len(corners) - len(corners) % 3
        return corners[:whole].reshape(-1, 3)
    if len(corners) < 3:
        return np.zeros((0, 3), dtype=np.int64)
    if mode == _FAN:
        first = np.full(len(corners) - 2, corners[0], dtype=np.int64)
        return np.stack([first, corners[1:-1], corners[2:]], axis=1)
    # A strip: every other triangle is wound the other way round.
    triangles = np.stack([corners[:-2], corners[1:-1], corners[2:]], axis=1)
    odd = np.arange(len(triangles)) % 2 == 1
    triangles[odd] = triangles[odd][:, [1, 0, 2]]
    return triangles


def _read(build: Callable[[], ScanMesh], kind: str) -> ScanMesh:
    """Whatever goes wrong in a file that does not hold together comes out as words."""
    try:
        return build()
    except RoomScanError:
        raise
    except MemoryError:
        raise RoomScanError(f"The {kind} is too large to read. Export it at a lower detail.")
    except (
        KeyError, TypeError, IndexError, ValueError, AttributeError, OverflowError, RecursionError, struct.error,
    ):
        raise _damaged(kind, "it is not put together the way glTF 2.0 says")


def _document(text: bytes, kind: str) -> Any:
    try:
        return json.loads(text.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _damaged(kind, "its JSON cannot be read")


def _scan(
    doc: Any, binary: Optional[memoryview], kind: str, fmt: str, source_file: str, resolve: Optional[Resolve] = None,
) -> ScanMesh:
    reader = _Reader(doc, binary, kind, resolve)
    reader.refuse_what_cannot_be_unpacked()
    reader.read_scene()
    return reader.mesh(fmt, source_file)


def looks_like_gltf(content: bytes) -> bool:
    """Whether a JSON file is glTF and not RoomPlan: glTF must name its `asset`."""
    if b'"asset"' not in content:
        return False
    return any(key in content for key in (b'"accessors"', b'"meshes"', b'"buffers"', b'"scenes"', b'"nodes"'))


def parse_gltf(content: bytes, source_file: str = "", resolve: Optional[Resolve] = None) -> ScanMesh:
    """A .gltf: the JSON, with its buffers inside it as base64 data URIs.

    `resolve` is given when the file's neighbours are at hand (it came in a
    zip): called with a buffer's `uri` as the file writes it, it answers that
    file's bytes or raises a RoomScanError that says what is missing.
    """
    kind = "glTF"
    return _read(lambda: _scan(_document(content, kind), None, kind, "gltf", source_file, resolve), kind)


def parse_glb(content: bytes, source_file: str = "", resolve: Optional[Resolve] = None) -> ScanMesh:
    """A .glb: header, JSON chunk, BIN chunk. `resolve` as for parse_gltf."""
    kind = "GLB"

    def build() -> ScanMesh:
        if content[:4] != GLB_MAGIC:
            raise RoomScanError(
                "This is named as a GLB and does not start the way one does. "
                "Export the scan again as .glb, or export OBJ."
            )
        if len(content) < 12:
            raise _damaged(kind, "it ends inside its header")
        version, length = struct.unpack_from("<II", content, 4)
        if version != 2:
            raise RoomScanError(
                f"This GLB says it is glTF version {version}, and only glTF 2.0 is read. "
                "Export the scan as glTF 2.0 (.glb), or export OBJ."
            )
        if length > len(content):
            raise _damaged(kind, f"it says it is {length:,} bytes long and {len(content):,} arrived")

        whole = memoryview(content)
        text: Optional[bytes] = None
        binary: Optional[memoryview] = None
        offset = 12
        while offset + 8 <= length:
            size, chunk = struct.unpack_from("<II", content, offset)
            start = offset + 8
            if start + size > length:
                raise _damaged(kind, "one of its parts runs past the end of the file")
            if chunk == _CHUNK_JSON and text is None:
                text = bytes(whole[start:start + size])
            elif chunk == _CHUNK_BIN and binary is None:
                binary = whole[start:start + size]
            offset = start + size
        if text is None:
            raise _damaged(kind, "it has no JSON part")
        return _scan(_document(text, kind), binary, kind, "glb", source_file, resolve)

    return _read(build, kind)
