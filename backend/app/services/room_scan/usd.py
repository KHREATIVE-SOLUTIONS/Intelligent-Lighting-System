"""
USD and RoomPlan
================

A USDZ is a ZIP. What can be read out of one without Pixar's USD library:

    a USDA layer    USD as text. Its meshes are read, placed by the transforms
                    of the prims above them, with the layer's own `upAxis` and
                    `metersPerUnit`.
    RoomPlan JSON   Apple's CapturedRoom written as JSON: walls, floors and
                    objects, each a size and a 4x4 transform. Each becomes a
                    box, so the room is found the same way as in any mesh.

A USDC layer is USD's binary form. Reading it needs the USD library, which is
not a dependency here, so a USDZ that holds only USDC is refused with a message
that says what to export instead. That is what Apple's RoomPlan and most phone
apps write, so for now USDZ mostly ends at that message.

The RoomPlan JSON reader follows Apple's published field names (`walls`,
`floors`, `objects`, `dimensions`, `transform`, `category`). It has NOT been
run against a file from a real device; it is written to skip what it does not
recognise rather than fail on it.
"""

import io
import json
import math
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .mesh import RoomScanError, ScanMesh, _checked, fan

USDA_MAGIC = b"#usda"
USDC_MAGIC = b"PXR-USDC"
# Uncompressed bytes read out of an archive, in total. A scan is far smaller;
# this is the limit a deliberately swollen ZIP runs into.
MAX_ARCHIVE_BYTES = 400 * 1024 * 1024

CONVERT_MESSAGE = (
    "This USDZ holds only binary USD (USDC), which cannot be read here. "
    "Export the scan as OBJ (or PLY) instead: in Polycam use Export > OBJ, in Scaniverse "
    "use Share > Export Model > OBJ. From RoomPlan, send the CapturedRoom JSON."
)


# ---------------------------------------------------------------------------
# USDA (text)
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_XFORM_OP = r"xformOp:(?:transform|translate|scale|orient|rotate[XYZ]{1,3})(?::\w+)?"
_SCAN = re.compile(
    r'(?P<prim>\b(?:def|over|class)\b(?:\s+\w+)?\s*"(?P<name>[^"]*)")'
    r'|(?P<string>"(?:\\.|[^"\\])*")'
    r"|(?P<open>\{)"
    r"|(?P<close>\})"
    r"|(?P<attr>\b(?:point3[fdh]\[\]\s+points|int\[\]\s+faceVertexIndices|int\[\]\s+faceVertexCounts"
    r"|uniform\s+token\[\]\s+xformOpOrder|token\[\]\s+xformOpOrder"
    r"|\w+\s+" + _XFORM_OP + r"))\s*=\s*"
)


def _value_end(text: str, start: int) -> int:
    """Index just past the bracketed (or bare) value that starts at `start`."""
    if start >= len(text):
        return start
    opener = text[start]
    if opener not in "[(":
        end = text.find("\n", start)
        return len(text) if end < 0 else end
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _skip_metadata(text: str, start: int) -> int:
    """Index past a prim's `( ... )` metadata, if it has any.

    The metadata can hold dictionaries in braces, which must not be taken for
    the prim's own body.
    """
    at = start
    while at < len(text) and text[at].isspace():
        at += 1
    if at >= len(text) or text[at] != "(":
        return start
    depth = 0
    in_string = False
    while at < len(text):
        ch = text[at]
        if in_string:
            if ch == "\\":
                at += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return at + 1
        at += 1
    return len(text)


def _numbers(value: str) -> np.ndarray:
    return np.array([float(n) for n in _NUMBER.findall(value)], dtype=np.float64)


def _rotation(axis: str, degrees: float) -> np.ndarray:
    """A turn about one axis as USD writes matrices: a point is a row, p' = p M."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    m = np.eye(4)
    if axis == "X":
        m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, s, -s, c
    elif axis == "Y":
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, -s, s, c
    else:
        m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, s, -s, c
    return m


def _op_matrix(name: str, value: str) -> Optional[np.ndarray]:
    """One xformOp as a 4x4 in USD's row-vector form, or None if it cannot be read."""
    numbers = _numbers(value)
    kind = name.split(":")[1]
    if kind == "transform" and len(numbers) == 16:
        return numbers.reshape(4, 4)
    if kind == "translate" and len(numbers) == 3:
        m = np.eye(4)
        m[3, :3] = numbers
        return m
    if kind == "scale" and len(numbers) == 3:
        return np.diag([numbers[0], numbers[1], numbers[2], 1.0])
    if kind == "orient" and len(numbers) == 4:
        w, x, y, z = numbers
        norm = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
        w, x, y, z = w / norm, x / norm, y / norm, z / norm
        column_form = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        m = np.eye(4)
        m[:3, :3] = column_form.T
        return m
    if kind.startswith("rotate"):
        axes = kind[len("rotate"):]
        if len(numbers) == len(axes):
            m = np.eye(4)
            # rotateXYZ turns about X first; with row vectors that is Rx Ry Rz.
            for axis, degrees in zip(axes, numbers):
                m = m @ _rotation(axis, float(degrees))
            return m
    return None


class _Prim:
    def __init__(self, name: str, parent: Optional["_Prim"]):
        self.name = name
        self.parent = parent
        self.ops: Dict[str, np.ndarray] = {}
        self.order: Optional[List[str]] = None
        self.points: Optional[np.ndarray] = None
        self.indices: Optional[np.ndarray] = None
        self.counts: Optional[np.ndarray] = None
        self.unread_ops = 0

    def local(self) -> np.ndarray:
        """This prim's own transform. xformOpOrder lists the ops outermost first."""
        names = self.order if self.order is not None else list(self.ops)
        m = np.eye(4)
        for name in names:
            op = self.ops.get(name)
            if op is not None:
                m = op @ m
        return m

    def world(self) -> np.ndarray:
        m = self.local()
        parent = self.parent
        while parent is not None:
            m = m @ parent.local()
            parent = parent.parent
        return m


def parse_usda(text: str, source_file: str = "") -> ScanMesh:
    """The meshes of a USDA layer, in the layer's own units and axes."""
    header_end = text.find("def ")
    header = text[:header_end if header_end >= 0 else len(text)]
    up = re.search(r'upAxis\s*=\s*"([YZyz])"', header)
    units = re.search(r"metersPerUnit\s*=\s*(" + _NUMBER.pattern + ")", header)

    prims: List[_Prim] = []
    stack: List[Optional[_Prim]] = []
    pending: Optional[str] = None
    at = 0
    while True:
        match = _SCAN.search(text, at)
        if match is None:
            break
        at = match.end()
        if match.group("prim"):
            pending = match.group("name")
            at = _skip_metadata(text, at)
        elif match.group("open"):
            if pending is not None:
                parent = next((p for p in reversed(stack) if p is not None), None)
                prim = _Prim(pending, parent)
                prims.append(prim)
                stack.append(prim)
                pending = None
            else:
                stack.append(None)      # a dictionary value, not a prim
        elif match.group("close"):
            if stack:
                stack.pop()
        elif match.group("attr"):
            end = _value_end(text, at)
            value = text[at:end]
            at = end
            prim = next((p for p in reversed(stack) if p is not None), None)
            if prim is None:
                continue
            words = match.group("attr").split()
            name = words[-1]
            if name == "points":
                prim.points = _numbers(value).reshape(-1, 3) if len(_numbers(value)) % 3 == 0 else None
            elif name == "faceVertexIndices":
                prim.indices = _numbers(value).astype(np.int64)
            elif name == "faceVertexCounts":
                prim.counts = _numbers(value).astype(np.int64)
            elif name == "xformOpOrder":
                prim.order = re.findall(r'"([^"]+)"', value)
            else:
                op = _op_matrix(name, value)
                if op is None:
                    prim.unread_ops += 1
                else:
                    prim.ops[name] = op

    vertices: List[np.ndarray] = []
    faces: List[Tuple[int, int, int]] = []
    offset = 0
    meshes = 0
    unread = sum(p.unread_ops for p in prims)
    for prim in prims:
        if prim.points is None or not len(prim.points):
            continue
        meshes += 1
        world = prim.world()
        placed = np.hstack([prim.points, np.ones((len(prim.points), 1))]) @ world
        vertices.append(placed[:, :3])
        if prim.indices is not None and prim.counts is not None and prim.counts.sum() == len(prim.indices):
            cursor = 0
            for count in prim.counts:
                corners = [int(i) + offset for i in prim.indices[cursor:cursor + count]]
                cursor += count
                if count >= 3:
                    faces.extend(fan(corners))
        offset += len(prim.points)

    if not vertices:
        raise RoomScanError(
            "The USD text layer holds no mesh points. Export the scan as OBJ (or PLY) instead."
        )
    mesh = ScanMesh(
        vertices=np.vstack(vertices),
        faces=np.array(faces, dtype=np.int64) if faces else None,
        format="usda",
        source_file=source_file,
        # USD's default is Y-up when a layer does not say.
        up_axis=(up.group(1).lower() if up else "y"),
        metres_per_unit=(float(units.group(1)) if units else None),
    )
    mesh.notes.append(f"Read {meshes} mesh{'es' if meshes != 1 else ''} from the USD text layer.")
    if not up:
        mesh.notes.append("The USD layer does not name its up axis; USD's default, Y, was used.")
    if unread:
        mesh.notes.append(
            f"{unread} transform{'s' if unread != 1 else ''} in the USD layer could not be read; "
            "what they place may be in the wrong position."
        )
    return _checked(mesh)


# ---------------------------------------------------------------------------
# RoomPlan JSON
# ---------------------------------------------------------------------------

_ROOMPLAN_SURFACES = ("walls", "floors", "objects")
_BOX_CORNERS = np.array(
    [[sx, sy, sz] for sx in (-0.5, 0.5) for sy in (-0.5, 0.5) for sz in (-0.5, 0.5)]
)
# Corner n is (x, y, z) low/high in binary: bit 2 = x, bit 1 = y, bit 0 = z.
_BOX_QUADS = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def _vector3(value: Any) -> Optional[np.ndarray]:
    if isinstance(value, dict):
        value = [value.get(k) for k in ("x", "y", "z")]
    try:
        vector = np.array(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    return vector[:3] if len(vector) >= 3 and np.isfinite(vector[:3]).all() else None


def _transform(value: Any) -> Optional[np.ndarray]:
    """A simd 4x4 as written by Codable: sixteen numbers, column by column."""
    if isinstance(value, dict):
        value = value.get("columns") or value.get("matrix")
    try:
        flat = np.array(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if len(flat) != 16 or not np.isfinite(flat).all():
        return None
    return flat.reshape(4, 4).T      # columns in the file become columns here


def _category(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value:
        return str(next(iter(value)))
    return ""


def looks_like_roomplan(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("walls"), list)


def parse_roomplan(data: Dict[str, Any], source_file: str = "") -> ScanMesh:
    """A CapturedRoom written as JSON: each wall, floor and object as a box."""
    vertices: List[np.ndarray] = []
    faces: List[Tuple[int, int, int]] = []
    objects: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    skipped = 0

    for key in _ROOMPLAN_SURFACES:
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                skipped += 1
                continue
            size = _vector3(item.get("dimensions"))
            transform = _transform(item.get("transform"))
            if size is None or transform is None:
                skipped += 1
                continue
            corners = (_BOX_CORNERS * size) @ transform[:3, :3].T + transform[:3, 3]
            base = sum(len(v) for v in vertices)
            vertices.append(corners)
            for quad in _BOX_QUADS:
                faces.extend(fan([base + i for i in quad]))
            counts[key] = counts.get(key, 0) + 1
            if key == "objects":
                objects.append({
                    "category": _category(item.get("category")) or "object",
                    "size": [round(float(s), 3) for s in size],
                })

    if not counts.get("walls"):
        raise RoomScanError("The RoomPlan file describes no walls that could be read.")
    mesh = ScanMesh(
        vertices=np.vstack(vertices),
        faces=np.array(faces, dtype=np.int64),
        format="roomplan",
        source_file=source_file,
        up_axis="y",
        metres_per_unit=1.0,
        objects=objects,
    )
    mesh.notes.append(
        "Read RoomPlan data: "
        + ", ".join(f"{counts.get(key, 0)} {key}" for key in _ROOMPLAN_SURFACES) + "."
    )
    if not counts.get("floors"):
        mesh.notes.append("The RoomPlan file has no floor; the floor was taken as the foot of the walls.")
    if skipped:
        mesh.notes.append(f"{skipped} RoomPlan entries had no readable size or transform and were left out.")
    return _checked(mesh)


def parse_roomplan_bytes(content: bytes, source_file: str = "") -> ScanMesh:
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise RoomScanError("The file is not readable JSON.")
    if not looks_like_roomplan(data):
        raise RoomScanError(
            "The JSON is not a RoomPlan room: it has no `walls` list. "
            "Send the CapturedRoom JSON, or an OBJ or PLY export of the scan."
        )
    return parse_roomplan(data, source_file)


# ---------------------------------------------------------------------------
# USDZ
# ---------------------------------------------------------------------------

def parse_usdz(content: bytes, source_file: str = "") -> ScanMesh:
    """Whatever in a USDZ can be read: RoomPlan JSON first, then a USDA layer."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise RoomScanError("The USDZ is not a readable archive.")

    with archive:
        budget = MAX_ARCHIVE_BYTES
        saw_usdc = False
        text_layers: List[Tuple[str, bytes]] = []
        for info in archive.infolist():
            name = info.filename
            lower = name.lower()
            if info.is_dir() or not lower.endswith((".json", ".usda", ".usd", ".usdc")):
                continue
            if info.file_size > budget:
                raise RoomScanError("The USDZ unpacks to more than this will read.")
            budget -= info.file_size
            try:
                data = archive.read(info)
            except (zipfile.BadZipFile, RuntimeError, OSError):
                continue
            if lower.endswith(".json"):
                try:
                    parsed = json.loads(data.decode("utf-8-sig"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if looks_like_roomplan(parsed):
                    mesh = parse_roomplan(parsed, source_file)
                    mesh.notes.append(f"Read from '{name}' inside the USDZ.")
                    return mesh
            elif data.lstrip()[:len(USDA_MAGIC)] == USDA_MAGIC:
                text_layers.append((name, data))
            elif data[:len(USDC_MAGIC)] == USDC_MAGIC:
                saw_usdc = True

    last_error: Optional[RoomScanError] = None
    for name, data in text_layers:
        try:
            mesh = parse_usda(data.decode("utf-8", errors="replace"), source_file)
        except RoomScanError as error:
            last_error = error
            continue
        mesh.notes.append(f"Read from '{name}' inside the USDZ.")
        return mesh

    if saw_usdc:
        raise RoomScanError(CONVERT_MESSAGE)
    if last_error is not None:
        raise last_error
    raise RoomScanError(
        "The USDZ holds no USD layer or RoomPlan JSON that could be read. "
        "Export the scan as OBJ (or PLY) instead."
    )
