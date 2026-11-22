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


def write_zip(members: Sequence[Tuple[str, bytes]]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
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
