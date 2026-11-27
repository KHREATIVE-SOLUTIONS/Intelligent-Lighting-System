"""
Synthetic rooms for the room-scan tests
=======================================

One known room, built in code, written out the ways a phone app would write
it. Nothing is read from disk: every mesh is made in the test that uses it.

The room is deliberately lopsided. A square room with a stage on its centre
line reads the same after a mirror or a swap of two axes, so it could not show
either mistake. This one is 12 m across and 9 m deep, with its stage hard
against the upstage wall and off to stage right, a small riser downstage left
and one truss across the room.

    stage axes: metres, origin at the centre of the floor, X across, Y up,
                -Z upstage
"""

import base64
import io
import json
import math
import struct
import zipfile
from typing import List, Optional, Sequence, Tuple

import numpy as np

ROOM = {"width": 12.0, "depth": 9.0, "height": 5.0}
# x_min, x_max, z_min, z_max, top
STAGE = {"x_min": -4.5, "x_max": 1.5, "z_min": -4.5, "z_max": -2.0, "height": 0.9}
RISER = {"x_min": 3.5, "x_max": 5.5, "z_min": 2.0, "z_max": 3.5, "height": 0.3}
TRUSS = {"x_min": -4.0, "x_max": 4.0, "z": 0.5, "bottom": 4.0, "top": 4.3, "across": 0.3}

_QUADS = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Tuple[np.ndarray, np.ndarray]:
    """(8 corners, 12 triangles) of a box."""
    corners = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=np.float64)
    triangles = []
    for a, b, c, d in _QUADS:
        triangles += [(a, b, c), (a, c, d)]
    return corners, np.array(triangles, dtype=np.int64)


def merge(parts: Sequence[Tuple[np.ndarray, np.ndarray]]) -> Tuple[np.ndarray, np.ndarray]:
    vertices, faces, offset = [], [], 0
    for corners, triangles in parts:
        vertices.append(corners)
        faces.append(triangles + offset)
        offset += len(corners)
    return np.vstack(vertices), np.vstack(faces)


def room_mesh(truss: bool = True, stage: bool = True, riser: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """The room in stage axes, metres."""
    half_w, half_d = ROOM["width"] / 2.0, ROOM["depth"] / 2.0
    parts = [box(-half_w, half_w, 0.0, ROOM["height"], -half_d, half_d)]
    if stage:
        parts.append(box(STAGE["x_min"], STAGE["x_max"], 0.0, STAGE["height"], STAGE["z_min"], STAGE["z_max"]))
    if riser:
        parts.append(box(RISER["x_min"], RISER["x_max"], 0.0, RISER["height"], RISER["z_min"], RISER["z_max"]))
    if truss:
        half = TRUSS["across"] / 2.0
        parts.append(box(
            TRUSS["x_min"], TRUSS["x_max"], TRUSS["bottom"], TRUSS["top"], TRUSS["z"] - half, TRUSS["z"] + half,
        ))
    return merge(parts)


# --- Rooms that are not boxes, and truss that is not square to the room ------
#
# A bigger room than the one above, so a ring of truss 4 m in radius hangs well
# clear of every wall. Its stage is against the upstage wall, which settles
# which way round the room comes back.

BIG_ROOM = {"width": 16.0, "depth": 14.0, "height": 6.0}
BIG_STAGE = {"x_min": -3.0, "x_max": 3.0, "z_min": -7.0, "z_max": -5.0, "height": 0.8}
RING = {"center_x": 0.5, "center_z": 1.0, "radius": 4.0, "across": 0.3, "bottom": 4.8, "top": 5.1}
# Centre, length and heading on the plan: clockwise from across the room, seen from above.
ANGLED_TRUSS = {"center_x": 1.0, "center_z": 0.5, "length": 8.0, "heading_deg": 30.0,
                "across": 0.3, "bottom": 4.0, "top": 4.3}

# An L: the 12 by 10 room with its downstage stage-left corner (4 by 4) walled off.
# Corners in order, clockwise seen from above, starting upstage stage right.
L_ROOM = [(-6.0, -5.0), (6.0, -5.0), (6.0, 1.0), (2.0, 1.0), (2.0, 5.0), (-6.0, 5.0)]
L_ROOM_PIECES = [
    [(-6.0, -5.0), (6.0, -5.0), (6.0, 1.0), (-6.0, 1.0)],
    [(-6.0, 1.0), (2.0, 1.0), (2.0, 5.0), (-6.0, 5.0)],
]
L_STAGE = {"x_min": -3.0, "x_max": 3.0, "z_min": -5.0, "z_max": -3.0, "height": 0.8}
# The same 12 by 10 room with its downstage stage-left corner cut off at an angle.
CUT_ROOM = [(-6.0, -5.0), (6.0, -5.0), (6.0, 1.0), (2.0, 5.0), (-6.0, 5.0)]


def prism(
    outline: Sequence[Tuple[float, float]], y0: float, y1: float,
    pieces: Optional[Sequence[Sequence[Tuple[float, float]]]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """A room with any floor outline: its walls, and its floor and ceiling.

    The floor and ceiling are fans, so they need convex shapes: `pieces` cuts an
    outline that is not convex into ones that are. The walls follow the outline
    only, so the cuts leave no wall inside the room.
    """
    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    count = len(outline)
    for k in range(count):
        (ax, az), (bx, bz) = outline[k], outline[(k + 1) % count]
        base = len(vertices)
        vertices += [(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)]
        faces += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    for piece in pieces or [outline]:
        for y in (y0, y1):
            base = len(vertices)
            vertices += [(x, y, z) for x, z in piece]
            faces += [(base, base + k, base + k + 1) for k in range(1, len(piece) - 1)]
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int64)


def turned_box(
    center_x: float, center_z: float, length: float, across: float, y0: float, y1: float, heading_deg: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """A bar on the plan at any heading: clockwise from across the room, seen from above."""
    corners, triangles = box(-length / 2.0, length / 2.0, y0, y1, -across / 2.0, across / 2.0)
    c, s = math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg))
    x, z = corners[:, 0], corners[:, 2]
    turned = np.stack([center_x + x * c - z * s, corners[:, 1], center_z + x * s + z * c], axis=1)
    return turned, triangles


def ring(
    center_x: float, center_z: float, radius: float, across: float, y0: float, y1: float, segments: int = 72,
) -> Tuple[np.ndarray, np.ndarray]:
    """A ring of truss: a flat band round a circle, with its four faces."""
    inner, outer = radius - across / 2.0, radius + across / 2.0
    vertices = []
    for k in range(segments):
        angle = 2.0 * math.pi * k / segments
        c, s = math.cos(angle), math.sin(angle)
        vertices += [
            (center_x + inner * c, y0, center_z + inner * s), (center_x + outer * c, y0, center_z + outer * s),
            (center_x + outer * c, y1, center_z + outer * s), (center_x + inner * c, y1, center_z + inner * s),
        ]
    faces = []
    for k in range(segments):
        a, b = 4 * k, 4 * ((k + 1) % segments)
        for i in range(4):
            j = (i + 1) % 4
            faces += [(a + i, a + j, b + j), (a + i, b + j, b + i)]
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int64)


def big_room_mesh(with_ring: bool = False, with_angled_truss: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """The bigger room in stage axes, with its stage and whatever is asked for overhead."""
    half_w, half_d = BIG_ROOM["width"] / 2.0, BIG_ROOM["depth"] / 2.0
    parts = [
        box(-half_w, half_w, 0.0, BIG_ROOM["height"], -half_d, half_d),
        box(BIG_STAGE["x_min"], BIG_STAGE["x_max"], 0.0, BIG_STAGE["height"], BIG_STAGE["z_min"], BIG_STAGE["z_max"]),
    ]
    if with_ring:
        parts.append(ring(RING["center_x"], RING["center_z"], RING["radius"], RING["across"],
                          RING["bottom"], RING["top"]))
    if with_angled_truss:
        t = ANGLED_TRUSS
        parts.append(turned_box(t["center_x"], t["center_z"], t["length"], t["across"],
                                t["bottom"], t["top"], t["heading_deg"]))
    return merge(parts)


def shaped_room_mesh(
    outline: Sequence[Tuple[float, float]] = L_ROOM,
    pieces: Optional[Sequence[Sequence[Tuple[float, float]]]] = L_ROOM_PIECES,
    height: float = 5.0, stage: bool = True, truss: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """A room with a floor outline that is not a box, its stage against the upstage wall."""
    parts = [prism(outline, 0.0, height, pieces)]
    if stage:
        parts.append(box(L_STAGE["x_min"], L_STAGE["x_max"], 0.0, L_STAGE["height"],
                         L_STAGE["z_min"], L_STAGE["z_max"]))
    if truss:
        parts.append(box(-4.0, 0.0, 4.0, 4.3, -0.65, -0.35))
    return merge(parts)


def as_scanned(
    vertices: np.ndarray,
    yaw_deg: float = 0.0,
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    up: str = "y",
    units_per_metre: float = 1.0,
) -> np.ndarray:
    """The room as a scanning app would hand it over: turned, moved, in its own axes and units.

    Every step is a rotation or a shift, never a mirror, so a reader that gets
    the room back the right way round has not mirrored it either.
    """
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    x, y, z = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    turned = np.stack([x * c - z * s, y, x * s + z * c], axis=1) + np.array(offset, dtype=np.float64)
    if up == "z":
        # Stage (x, y, z) in Z-up axes: (x, -z, y). The inverse of the importer's z_up_to_stage.
        turned = np.stack([turned[:, 0], -turned[:, 2], turned[:, 1]], axis=1)
    return turned * units_per_metre


def sample_surface(vertices: np.ndarray, faces: np.ndarray, count: int, seed: int = 7) -> np.ndarray:
    """Points scattered over the mesh, as a LiDAR point cloud has them."""
    rng = np.random.default_rng(seed)
    a = vertices[faces[:, 0]]
    ab = vertices[faces[:, 1]] - a
    ac = vertices[faces[:, 2]] - a
    areas = np.linalg.norm(np.cross(ab, ac), axis=1)
    chosen = rng.choice(len(faces), count, p=areas / areas.sum())
    u, v = rng.random(count), rng.random(count)
    over = u + v > 1
    u[over], v[over] = 1 - u[over], 1 - v[over]
    return a[chosen] + ab[chosen] * u[:, None] + ac[chosen] * v[:, None]


# --- Writers ---------------------------------------------------------------

def write_obj(vertices: np.ndarray, faces: np.ndarray) -> bytes:
    lines = ["# synthetic room", "o room"]
    lines += [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    return ("\n".join(lines) + "\n").encode()


def write_ply(
    vertices: np.ndarray,
    faces: Optional[np.ndarray] = None,
    fmt: str = "binary_little_endian",
    normals: Optional[np.ndarray] = None,
) -> bytes:
    header = ["ply", f"format {fmt} 1.0", "comment synthetic room", f"element vertex {len(vertices)}"]
    header += ["property float x", "property float y", "property float z"]
    if normals is not None:
        header += ["property float nx", "property float ny", "property float nz"]
    if faces is not None:
        header += [f"element face {len(faces)}", "property list uchar int vertex_indices"]
    header.append("end_header")
    out = io.BytesIO()
    out.write(("\n".join(header) + "\n").encode())

    table = vertices if normals is None else np.hstack([vertices, normals])
    if fmt == "ascii":
        for row in table:
            out.write((" ".join(f"{value:.6f}" for value in row) + "\n").encode())
        for face in faces if faces is not None else []:
            out.write((f"{len(face)} " + " ".join(str(int(i)) for i in face) + "\n").encode())
        return out.getvalue()

    order = "<" if fmt == "binary_little_endian" else ">"
    out.write(table.astype(order + "f4").tobytes())
    for face in faces if faces is not None else []:
        out.write(struct.pack(f"{order}B{len(face)}i", len(face), *[int(i) for i in face]))
    return out.getvalue()


def write_usda(vertices: np.ndarray, faces: np.ndarray, up: str = "Y", metres_per_unit: float = 1.0,
               translate: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> str:
    """One mesh under one Xform. `vertices` are written as they are; the Xform moves them."""
    points = ", ".join(f"({x:.6f}, {y:.6f}, {z:.6f})" for x, y, z in vertices)
    counts = ", ".join("3" for _ in faces)
    indices = ", ".join(str(int(i)) for face in faces for i in face)
    return f'''#usda 1.0
(
    defaultPrim = "Room"
    metersPerUnit = {metres_per_unit}
    upAxis = "{up}"
    customLayerData = {{
        string creator = "synthetic"
    }}
)

def Xform "Room" (
    customData = {{
        string note = "a brace in the metadata {{ must not open the prim"
    }}
)
{{
    double3 xformOp:translate = ({translate[0]}, {translate[1]}, {translate[2]})
    uniform token[] xformOpOrder = ["xformOp:translate"]

    def Mesh "Scan"
    {{
        int[] faceVertexCounts = [{counts}]
        int[] faceVertexIndices = [{indices}]
        point3f[] points = [{points}]
    }}
}}
'''


GLTF_INDEX_TYPES = {"B": 5121, "H": 5123, "I": 5125}


def gltf_scene(
    parts: Sequence[Tuple[np.ndarray, np.ndarray, dict]],
    indexed: bool = True,
    interleaved: bool = False,
    index_format: str = "I",
    mode: int = 4,
) -> Tuple[dict, bytes]:
    """(the glTF JSON as a dict, its one buffer) for a scene of meshes.

    Each part is (points, triangles, node): one mesh with one primitive, drawn
    by one node at the top of the scene. `node` is what places it (`matrix`,
    or `translation`, `rotation` and `scale`), or {} to leave it where it is.
    The points are written as they are given: glTF's own axes are Y-up, metres.

    `indexed=False` writes each triangle's three corners out in turn, with no
    index list. `interleaved=True` writes each point after twelve bytes of a
    made-up normal, so its buffer view has a byteStride of 24 and its accessor
    a byteOffset of 12. A test changes the dict to make a file that is wrong.
    """
    doc = {
        "asset": {"version": "2.0", "generator": "synthetic room"},
        "scene": 0, "scenes": [{"nodes": []}],
        "nodes": [], "meshes": [], "accessors": [], "bufferViews": [], "buffers": [],
    }
    data = bytearray()

    def view(raw: bytes, stride: Optional[int] = None) -> int:
        while len(data) % 4:
            data.append(0)
        entry = {"buffer": 0, "byteOffset": len(data), "byteLength": len(raw)}
        if stride:
            entry["byteStride"] = stride
        data.extend(raw)
        doc["bufferViews"].append(entry)
        return len(doc["bufferViews"]) - 1

    for number, (vertices, faces, node) in enumerate(parts):
        points = np.asarray(vertices, dtype=np.float64)
        triangles = np.asarray(faces, dtype=np.int64)
        if not indexed:
            points = points[triangles.reshape(-1)]
        primitive = {"attributes": {}, "mode": mode}

        low, high = points.min(axis=0).tolist(), points.max(axis=0).tolist()
        accessor = {"componentType": 5126, "count": len(points), "type": "VEC3", "min": low, "max": high}
        if interleaved:
            table = np.zeros((len(points), 6), dtype="<f4")
            table[:, 1] = 1.0
            table[:, 3:] = points
            accessor.update(bufferView=view(table.tobytes(), stride=24), byteOffset=12)
        else:
            accessor["bufferView"] = view(points.astype("<f4").tobytes())
        doc["accessors"].append(accessor)
        primitive["attributes"]["POSITION"] = len(doc["accessors"]) - 1

        if indexed:
            flat = [int(i) for i in triangles.reshape(-1)]
            raw = struct.pack(f"<{len(flat)}{index_format}", *flat)
            doc["accessors"].append({
                "bufferView": view(raw), "componentType": GLTF_INDEX_TYPES[index_format],
                "count": len(flat), "type": "SCALAR",
            })
            primitive["indices"] = len(doc["accessors"]) - 1

        doc["meshes"].append({"name": f"part {number}", "primitives": [primitive]})
        doc["nodes"].append({"name": f"node {number}", "mesh": number, **node})
        doc["scenes"][0]["nodes"].append(number)

    doc["buffers"].append({"byteLength": len(data)})
    return doc, bytes(data)


def write_glb(doc: dict, data: bytes = b"") -> bytes:
    """A .glb: the 12-byte header, the JSON chunk padded with spaces, the BIN chunk padded with zeros."""
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text
    if data:
        padded = data + bytes(-len(data) % 4)
        chunks += struct.pack("<II", len(padded), 0x004E4942) + padded
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def write_gltf(doc: dict, data: bytes = b"") -> bytes:
    """A .gltf with its buffer inside it as a base64 data URI. `doc` is not changed.

    A buffer the test has already given a `uri` keeps it.
    """
    whole = json.loads(json.dumps(doc))
    if data and "uri" not in whole["buffers"][0]:
        whole["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(data).decode()
    return json.dumps(whole, indent=1).encode()


def write_zip(members: Sequence[Tuple[str, bytes]], compression: int = zipfile.ZIP_STORED) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return out.getvalue()


def _simd(columns: Sequence[Sequence[float]]) -> List[float]:
    """A simd 4x4 as Codable writes it: sixteen numbers, column by column."""
    return [float(value) for column in columns for value in column]


def roomplan_json(with_floor: bool = True) -> bytes:
    """The room's four walls, floor and stage as RoomPlan would describe them (metres, Y-up)."""
    half_w, half_d, height = ROOM["width"] / 2.0, ROOM["depth"] / 2.0, ROOM["height"]
    identity = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0))
    # A wall's own X runs along it; this turns that to run along the room's Z.
    quarter = ((0, 0, -1, 0), (0, 1, 0, 0), (1, 0, 0, 0))

    def surface(size, basis, at, category):
        return {
            "category": {category: {}},
            "confidence": {"high": {}},
            "dimensions": list(size),
            "transform": _simd([*basis, (at[0], at[1], at[2], 1)]),
        }

    room = {
        "walls": [
            surface((ROOM["width"], height, 0.0), identity, (0, height / 2, -half_d), "wall"),
            surface((ROOM["width"], height, 0.0), identity, (0, height / 2, half_d), "wall"),
            surface((ROOM["depth"], height, 0.0), quarter, (-half_w, height / 2, 0), "wall"),
            surface((ROOM["depth"], height, 0.0), quarter, (half_w, height / 2, 0), "wall"),
        ],
        "doors": [], "windows": [], "openings": [],
        "objects": [
            surface(
                (STAGE["x_max"] - STAGE["x_min"], STAGE["height"], STAGE["z_max"] - STAGE["z_min"]),
                identity,
                ((STAGE["x_min"] + STAGE["x_max"]) / 2, STAGE["height"] / 2, (STAGE["z_min"] + STAGE["z_max"]) / 2),
                "storage",
            ),
        ],
    }
    if with_floor:
        # RoomPlan's floor is a flat rectangle in its own XY, laid down by its transform.
        laid_flat = ((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0))
        room["floors"] = [surface((ROOM["width"], ROOM["depth"], 0.0), laid_flat, (0, 0, 0), "floor")]
    return json.dumps(room).encode()
