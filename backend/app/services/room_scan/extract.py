"""
Room shell from a scan
======================

Turns a scan (mesh.py, usd.py) into the `room_shell` the 3D view draws, in the
rig's own axes: metres, origin at the centre of the floor, X across, Y up, -Z
upstage.

Everything found here is a SUGGESTION. A phone scan is noisy, the rules below
are simple, and nothing has been checked against the room, so every element of
the shell is written with `suggested: true` and a `basis` that says how it was
found. The operator reads the preview and decides.

How it works, in order:

1. Points. A mesh is sampled, area-weighted, into points with the normal of the
   face each came from. A point cloud is used as it is. From here on a tidy
   12-triangle box and a million-triangle LiDAR mesh are the same thing.
2. Up. Taken from the file where it says (USD, RoomPlan) or from the caller.
   Otherwise guessed between Y and Z: the up axis is the one with most of the
   surface at its two ends (the floor and the ceiling).
3. Units. Taken from the file where it says, or from the caller. Otherwise
   guessed from the floor-to-ceiling height, the one dimension of a room that
   is tightly bounded: under 100 it is metres, under 1800 centimetres, else
   millimetres.
4. Floor and ceiling: the densest level near the bottom and near the top.
5. Walls. The scan is turned about the vertical until its walls line up with
   the axes (the turn that makes the plan's two profiles sharpest), then each
   wall is the densest plane near its side. A plane, not the furthest point:
   scans leak through doorways.
6. Raised areas (a stage, a riser, a booth): level patches between 12 cm and
   2.2 m above the floor, at least 1.5 m2. Each is measured along the room's
   axes, but for one that clearly stands turned from the walls (a rectangle,
   5 degrees or more off): that one is measured along its own sides and given
   a `heading_deg`, the heading Edit Room stores for a raised area.
7. Overhead lines (a truss, a lighting bar): long thin things hanging clear of
   the walls in the upper half of the room, grouped into hanging-height bands.
8. Which way is upstage. The walls leave four ways round. The side with the
   largest raised area becomes upstage; with no raised area the scan's own
   heading is kept. The caller can turn it further in quarter turns.

The turns are all rotations, never a mirror, so stage left stays stage left.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .mesh import RoomScanError, ScanMesh

# Points worked on. Enough that a 0.2 m cell of a large room's floor is never
# empty by chance; few enough that a scan is read in about a second.
SAMPLE_POINTS = 240_000
MAX_CLOUD_POINTS = 600_000
# Triangles looked at when sampling. A random subset of a larger mesh keeps the
# same share of area on every surface.
MAX_SAMPLED_FACES = 3_000_000

UNIT_SCALES = {"m": 1.0, "cm": 0.01, "mm": 0.001}

# A raised area: what counts as one.
RAISED_MIN_HEIGHT = 0.12
RAISED_MAX_HEIGHT = 2.2
RAISED_MIN_AREA = 1.5
RAISED_MIN_SIDE = 0.8
STAGE_MIN_AREA = 6.0
# A raised area that stands turned from the room's walls (slice 27). It is
# given a heading only when it is turned by at least this much, when its own
# box is at most this share of the box along the room's axes (a rectangle
# turned 5 degrees is under 0.86 of it), and when it fills this much of its
# own box. Anything else is measured along the room's axes, as it always was.
RAISED_TURN_MIN_DEG = 5.0
RAISED_TURN_MAX_SHARE = 0.9
RAISED_TURN_MIN_FILL = 0.8
RAISED_TURN_MIN_POINTS = 40
RAISED_TURN_SAMPLE = 4000

# An overhead line: long, thin, clear of the walls, in the upper room.
OVERHEAD_MIN_HEIGHT = 2.0
OVERHEAD_CEILING_CLEARANCE = 0.2
OVERHEAD_WALL_CLEARANCE = 0.3
LINE_MIN_LENGTH = 1.5
LINE_MAX_WIDTH = 1.2
# A line within this of the room's own axes is read as running along them.
AXIS_SNAP_DEG = 2.0

# A ring of truss: points that keep to one circle nearly all the way round.
RING_MIN_RADIUS = 0.75
RING_MAX_STRAY = 0.35           # metres off the fitted circle, either side
RING_MAX_STRAY_SHARE = 0.12     # and as a share of its radius: a square frame strays about 0.2
RING_SECTORS = 24
RING_MIN_SECTORS = 21           # 315 degrees of the way round

# The floor outline, for a room that is not a box.
OUTLINE_BOX_SHARE = 0.95        # a footprint filling this much of its box is a box
OUTLINE_MIN_SHARE = 0.35        # one filling less than this is not a room's outline
OUTLINE_MAX_CORNERS = 12


@dataclass
class ScanOptions:
    """What the caller can decide instead of the guesses."""

    units: str = "auto"       # auto, m, cm, mm
    up_axis: str = "auto"     # auto, y, z
    rotate: int = 0           # a further 0, 90, 180 or 270 degrees clockwise seen from above


@dataclass
class RoomExtraction:
    shell: Dict[str, Any]
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _r(value: float, places: int = 2) -> float:
    """Rounded for the shell, with no negative zero."""
    return round(float(value), places) + 0.0


# ---------------------------------------------------------------------------
# 1. Points
# ---------------------------------------------------------------------------

def surface_points(mesh: ScanMesh, rng: np.random.Generator) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[float]]:
    """(points, normals or None, surface area in file units or None)."""
    if mesh.is_point_cloud:
        points, normals = mesh.vertices, mesh.normals
        if len(points) > MAX_CLOUD_POINTS:
            keep = rng.choice(len(points), MAX_CLOUD_POINTS, replace=False)
            points = points[keep]
            normals = normals[keep] if normals is not None else None
        return points, normals, None

    faces = mesh.faces
    share = 1.0
    if len(faces) > MAX_SAMPLED_FACES:
        share = MAX_SAMPLED_FACES / len(faces)
        faces = faces[rng.choice(len(faces), MAX_SAMPLED_FACES, replace=False)]
    a = mesh.vertices[faces[:, 0]]
    ab = mesh.vertices[faces[:, 1]] - a
    ac = mesh.vertices[faces[:, 2]] - a
    cross = np.cross(ab, ac)
    twice_area = np.linalg.norm(cross, axis=1)
    total = float(twice_area.sum()) / 2.0
    if not total > 0:
        raise RoomScanError("The mesh's triangles have no area: there is no surface to read a room from.")

    chosen = rng.choice(len(faces), SAMPLE_POINTS, p=twice_area / twice_area.sum())
    u = rng.random(SAMPLE_POINTS)
    v = rng.random(SAMPLE_POINTS)
    over = u + v > 1.0
    u[over], v[over] = 1.0 - u[over], 1.0 - v[over]
    points = a[chosen] + ab[chosen] * u[:, None] + ac[chosen] * v[:, None]
    normals = cross[chosen] / np.maximum(twice_area[chosen], 1e-30)[:, None]
    return points, normals, total / share


# ---------------------------------------------------------------------------
# 2 and 3. Up axis and units
# ---------------------------------------------------------------------------

def _end_share(values: np.ndarray) -> Tuple[float, float]:
    """(share of points in the two end slabs of this axis, the axis's extent)."""
    low, high = np.percentile(values, [0.5, 99.5])
    extent = float(high - low)
    if extent <= 0:
        return 0.0, 0.0
    slab = 0.04 * extent
    return float(np.mean((values < low + slab) | (values > high - slab))), extent


def choose_up_axis(points: np.ndarray, mesh: ScanMesh, options: ScanOptions, assumptions: List[str]) -> str:
    if options.up_axis in ("y", "z"):
        assumptions.append(f"Read as {options.up_axis.upper()}-up, as asked.")
        return options.up_axis
    if mesh.up_axis in ("y", "z"):
        assumptions.append(f"Read as {mesh.up_axis.upper()}-up: the file says so.")
        return mesh.up_axis

    y_share, y_extent = _end_share(points[:, 1])
    z_share, z_extent = _end_share(points[:, 2])
    hint = " If the room comes out on its side, set the up axis by hand."
    if max(y_share, z_share) >= 1.3 * max(min(y_share, z_share), 1e-9):
        axis = "y" if y_share > z_share else "z"
        assumptions.append(
            f"Read as {axis.upper()}-up: most of the surface lies at the two ends of that axis, "
            "as a floor and a ceiling do." + hint
        )
        return axis
    if min(y_extent, z_extent) > 0 and max(y_extent, z_extent) >= 1.15 * min(y_extent, z_extent):
        axis = "y" if y_extent < z_extent else "z"
        assumptions.append(
            f"Read as {axis.upper()}-up: the scan is shortest along that axis, and nothing else "
            "told the floor from a wall." + hint
        )
        return axis
    assumptions.append("Read as Y-up: the scan did not show which way is up, and Y is the usual one." + hint)
    return "y"


def to_y_up(vectors: np.ndarray, axis: str) -> np.ndarray:
    """Z-up vectors in Y-up axes: (x, z, -y), a rotation, as stage_axes.z_up_to_stage."""
    if axis == "y":
        return vectors
    return np.stack([vectors[:, 0], vectors[:, 2], -vectors[:, 1]], axis=1)


def choose_units(points: np.ndarray, mesh: ScanMesh, options: ScanOptions, assumptions: List[str]) -> Tuple[float, str]:
    """(metres per file unit, the unit's name)."""
    if options.units in UNIT_SCALES:
        assumptions.append(f"Units read as {options.units}, as asked.")
        return UNIT_SCALES[options.units], options.units
    if mesh.metres_per_unit and mesh.metres_per_unit > 0:
        scale = float(mesh.metres_per_unit)
        name = next((n for n, s in UNIT_SCALES.items() if math.isclose(s, scale, rel_tol=1e-6)), f"{scale:g} m")
        assumptions.append(f"Units read as {name}: the file says so.")
        return scale, name

    low, high = np.percentile(points[:, 1], [0.5, 99.5])
    height = float(high - low)
    name = "m" if height < 100 else "cm" if height < 1800 else "mm"
    scale = UNIT_SCALES[name]
    assumptions.append(
        f"Units read as {name}: the scan is {height:g} units from bottom to top, "
        f"which is a room {height * scale:.2f} m high. Set the units by hand if that is wrong."
    )
    return scale, name


# ---------------------------------------------------------------------------
# 4. Floor and ceiling
# ---------------------------------------------------------------------------

def _densest_level(values: np.ndarray, low: float, high: float, step: float = 0.02) -> Tuple[Optional[float], int]:
    """(height of the densest `step`-thick level between low and high, points in it)."""
    inside = values[(values >= low) & (values <= high)]
    if len(inside) < 3 or high - low < step:
        return None, 0
    counts, edges = np.histogram(inside, bins=np.arange(low, high + step, step))
    wide = np.convolve(counts, np.ones(3, dtype=int), mode="same")
    k = int(np.argmax(wide))
    centre = (edges[k] + edges[k + 1]) / 2.0
    near = inside[np.abs(inside - centre) <= 1.5 * step]
    return (float(np.median(near)) if len(near) else float(centre)), int(wide[k])


def find_floor_and_ceiling(
    y: np.ndarray, level: Optional[np.ndarray], warnings: List[str],
) -> Tuple[float, float]:
    """(floor height, ceiling height) in the scan's own heights, metres.

    `level` marks the points on a roughly horizontal surface, where the scan
    has normals; with none, every point is used.
    """
    low, high = np.percentile(y, [0.5, 99.5])
    span = float(high - low)
    if span < 0.5:
        raise RoomScanError(
            f"The scan is only {span:.2f} m from bottom to top: that is not a room. "
            "Check the units and the up axis."
        )
    use = y[level] if level is not None and level.sum() >= 50 else y
    enough = max(20, int(0.01 * len(use)))

    floor_reach = max(0.3, min(0.6, 0.15 * span))
    floor, count = _densest_level(use, low - 0.05, low + floor_reach)
    if floor is None or count < enough:
        floor = float(low)
        warnings.append("No clear floor was found; the lowest part of the scan was taken as the floor.")

    ceiling, count = _densest_level(use, high - 0.25 * span, high + 0.05)
    if ceiling is None or count < enough:
        ceiling = float(high)
        warnings.append(
            "No clear flat ceiling was found; the highest part of the scan was taken as the ceiling height."
        )
    return float(floor), float(ceiling)


# ---------------------------------------------------------------------------
# 5. Walls
# ---------------------------------------------------------------------------

def _sharpness(x: np.ndarray, z: np.ndarray, angle: float, step: float) -> float:
    """How much the plan, turned by `angle`, piles up on single lines of X and of Z."""
    c, s = math.cos(angle), math.sin(angle)
    total = 0.0
    for values in (x * c - z * s, x * s + z * c):
        cells = np.floor((values - values.min()) / step).astype(np.int64)
        counts = np.bincount(cells)
        total += float(np.dot(counts, counts))
    return total


def dominant_wall_turn(x: np.ndarray, z: np.ndarray) -> float:
    """The turn about the vertical, in radians within +/-45 degrees, that squares the walls to the axes."""
    if len(x) > 40_000:
        stride = len(x) // 40_000 + 1
        x, z = x[::stride], z[::stride]
    coarse = [math.radians(a / 2.0) for a in range(0, 180)]
    best = max(coarse, key=lambda a: _sharpness(x, z, a, 0.05))
    fine = [best + math.radians(d / 20.0) for d in range(-12, 13)]
    best = max(fine, key=lambda a: _sharpness(x, z, a, 0.02))
    quarter = math.pi / 2.0
    best = (best + quarter / 2.0) % quarter - quarter / 2.0
    return best


def turn_about_vertical(vectors: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    x, z = vectors[:, 0], vectors[:, 2]
    return np.stack([x * c - z * s, vectors[:, 1], x * s + z * c], axis=1)


def _wall(values: np.ndarray, side: int, step: float = 0.05) -> Tuple[float, bool]:
    """(where the wall on this side is, whether a plane was found there)."""
    low, high = np.percentile(values, [0.5, 99.5])
    span = float(high - low)
    window = (low - step, low + 0.2 * span) if side < 0 else (high - 0.2 * span, high + step)
    near = values[(values >= window[0]) & (values <= window[1])]
    if len(near) >= 20 and window[1] - window[0] > step:
        counts, edges = np.histogram(near, bins=np.arange(window[0], window[1] + step, step))
        k = int(np.argmax(counts))
        if counts[k] >= max(10, 0.01 * len(values)):
            plane = near[(near >= edges[k] - step) & (near <= edges[k + 1] + step)]
            return float(np.median(plane)), True
    return float(low if side < 0 else high), False


# ---------------------------------------------------------------------------
# Patches on a plan grid
# ---------------------------------------------------------------------------

def _components(cells: np.ndarray) -> List[np.ndarray]:
    """Groups of (ix, iz) cells that touch, corners included."""
    remaining = {(int(i), int(j)) for i, j in cells}
    groups: List[np.ndarray] = []
    while remaining:
        start = remaining.pop()
        group = [start]
        frontier = [start]
        while frontier:
            i, j = frontier.pop()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    neighbour = (i + di, j + dj)
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        group.append(neighbour)
                        frontier.append(neighbour)
        groups.append(np.array(group, dtype=np.int64))
    return groups


def _grid(points: np.ndarray, origin: Tuple[float, float], cell: float) -> np.ndarray:
    """Each point's (ix, iz) cell on the plan."""
    return np.stack([
        np.floor((points[:, 0] - origin[0]) / cell).astype(np.int64),
        np.floor((points[:, 2] - origin[1]) / cell).astype(np.int64),
    ], axis=1)


def _patches(points: np.ndarray, cells: np.ndarray, keep: Optional[set] = None) -> List[Dict[str, Any]]:
    """Each connected patch of occupied cells, with the points in it."""
    if not len(points):
        return []
    occupied, inverse = np.unique(cells, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    index = {(int(c[0]), int(c[1])): n for n, c in enumerate(occupied)}
    usable = [c for c in index if keep is None or c in keep]
    if not usable:
        return []
    groups = _components(np.array(usable, dtype=np.int64).reshape(-1, 2))
    # Which patch each occupied cell is in, then each point through its cell.
    cell_patch = np.full(len(occupied), -1, dtype=np.int64)
    for number, group in enumerate(groups):
        for i, j in group:
            cell_patch[index[(int(i), int(j))]] = number
    point_patch = cell_patch[inverse]
    order = np.argsort(point_patch, kind="stable")
    sorted_patch = point_patch[order]
    starts = np.searchsorted(sorted_patch, np.arange(len(groups)), side="left")
    ends = np.searchsorted(sorted_patch, np.arange(len(groups)), side="right")
    return [
        {"cells": len(group), "points": points[order[starts[n]:ends[n]]]}
        for n, group in enumerate(groups)
        if ends[n] > starts[n]
    ]


# ---------------------------------------------------------------------------
# 5b. The floor outline, for a room that is not a box
# ---------------------------------------------------------------------------

def inside_outline(x: np.ndarray, z: np.ndarray, outline: np.ndarray) -> np.ndarray:
    """Which plan points lie inside a closed outline (an N by 2 array of x, z corners)."""
    inside = np.zeros(len(x), dtype=bool)
    count = len(outline)
    for k in range(count):
        ax, az = outline[k]
        bx, bz = outline[(k + 1) % count]
        if az == bz:
            continue
        crosses = (az > z) != (bz > z)
        at = ax + (z - az) * (bx - ax) / (bz - az)
        inside ^= crosses & (x < at)
    return inside


def _distance_to_segment(x: np.ndarray, z: np.ndarray, a: Sequence[float], b: Sequence[float]) -> np.ndarray:
    dx, dz = b[0] - a[0], b[1] - a[1]
    squared = dx * dx + dz * dz
    along = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / squared, 0.0, 1.0) if squared > 0 else np.zeros(len(x))
    return np.hypot(x - (a[0] + along * dx), z - (a[1] + along * dz))


def clear_of_outline(x: np.ndarray, z: np.ndarray, outline: np.ndarray, clear: float) -> np.ndarray:
    """Which plan points are inside the outline and further than `clear` from every wall of it."""
    keep = inside_outline(x, z, outline)
    for k in range(len(outline)):
        keep &= _distance_to_segment(x, z, outline[k], outline[(k + 1) % len(outline)]) > clear
    return keep


def outline_area(outline: np.ndarray) -> float:
    """Signed area on the plan: positive for corners in clockwise order seen from above (-Z at the top)."""
    x, z = outline[:, 0], outline[:, 1]
    return float(np.dot(x, np.roll(z, -1)) - np.dot(np.roll(x, -1), z)) / 2.0


def _grow(grid: np.ndarray) -> np.ndarray:
    """Every cell that touches a filled one, corners included."""
    padded = np.pad(grid, 1, constant_values=False)
    out = np.zeros_like(grid)
    for di in range(3):
        for dj in range(3):
            out |= padded[di:di + grid.shape[0], dj:dj + grid.shape[1]]
    return out


def _shrink(grid: np.ndarray) -> np.ndarray:
    """Every cell whose neighbours are all filled. The edge of the grid counts as filled: it is a wall."""
    padded = np.pad(grid, 1, constant_values=True)
    out = np.ones_like(grid)
    for di in range(3):
        for dj in range(3):
            out &= padded[di:di + grid.shape[0], dj:dj + grid.shape[1]]
    return out


def _flood(open_cells: np.ndarray, seeds: List[Tuple[int, int]]) -> np.ndarray:
    """The open cells that can be reached from the seeds, stepping side to side only."""
    reached = np.zeros_like(open_cells)
    frontier = [s for s in seeds if open_cells[s]]
    for s in frontier:
        reached[s] = True
    rows, columns = open_cells.shape
    while frontier:
        i, j = frontier.pop()
        for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= ni < rows and 0 <= nj < columns and open_cells[ni, nj] and not reached[ni, nj]:
                reached[ni, nj] = True
                frontier.append((ni, nj))
    return reached


def _footprint(x: np.ndarray, z: np.ndarray, room: Dict[str, float], cell: float) -> np.ndarray:
    """The cells of the room's box the scan has anything in, with gaps closed and the inside filled."""
    nx = max(1, int(math.ceil((room["x_max"] - room["x_min"]) / cell - 1e-6)))
    nz = max(1, int(math.ceil((room["z_max"] - room["z_min"]) / cell - 1e-6)))
    ix = np.floor((x - room["x_min"]) / cell).astype(np.int64)
    iz = np.floor((z - room["z_min"]) / cell).astype(np.int64)
    # Half a cell past a wall still belongs to it; further out is a leak through a doorway.
    near = (
        (x >= room["x_min"] - 0.5 * cell) & (x <= room["x_max"] + 0.5 * cell)
        & (z >= room["z_min"] - 0.5 * cell) & (z <= room["z_max"] + 0.5 * cell)
    )
    grid = np.zeros((nx, nz), dtype=bool)
    grid[np.clip(ix[near], 0, nx - 1), np.clip(iz[near], 0, nz - 1)] = True
    grid = _shrink(_grow(grid))

    # Whatever cannot be reached from outside is inside: floor the scan missed
    # under a stage, or a room described by its walls alone.
    padded = np.pad(~grid, 1, constant_values=True)
    border = [(i, j) for i in range(padded.shape[0]) for j in (0, padded.shape[1] - 1)]
    border += [(i, j) for j in range(padded.shape[1]) for i in (0, padded.shape[0] - 1)]
    outside = _flood(padded, border)[1:-1, 1:-1]
    filled = _grow(_shrink(~outside)) & ~outside

    # The largest piece that hangs together.
    best = np.zeros_like(filled)
    remaining = filled.copy()
    while remaining.any():
        seed = tuple(int(v) for v in np.argwhere(remaining)[0])
        piece = _flood(remaining, [seed])
        remaining &= ~piece
        if piece.sum() > best.sum():
            best = piece
    return best


def _trace(grid: np.ndarray) -> Optional[np.ndarray]:
    """The outer edge of the filled cells as corners on the grid, clockwise seen from above."""
    filled = np.pad(grid, 1, constant_values=False)
    steps: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for i, j in np.argwhere(grid):
        i, j = int(i), int(j)
        if not filled[i + 1, j]:
            steps.setdefault((i, j), []).append((i + 1, j))
        if not filled[i + 2, j + 1]:
            steps.setdefault((i + 1, j), []).append((i + 1, j + 1))
        if not filled[i + 1, j + 2]:
            steps.setdefault((i + 1, j + 1), []).append((i, j + 1))
        if not filled[i, j + 1]:
            steps.setdefault((i, j + 1), []).append((i, j))
    loops: List[np.ndarray] = []
    while steps:
        start = min(steps)
        loop = [start]
        at = start
        while True:
            onward = steps[at]
            following = onward.pop()
            if not onward:
                del steps[at]
            if following == start:
                break
            loop.append(following)
            at = following
            if at not in steps:
                loop = []
                break
        if len(loop) >= 4:
            loops.append(np.array(loop, dtype=np.float64))
    if not loops:
        return None
    return max(loops, key=lambda loop: abs(outline_area(loop)))


def _keep_corners(points: np.ndarray, tolerance: float) -> List[int]:
    """Douglas-Peucker on an open run of points: the indices worth keeping."""
    keep = [0, len(points) - 1]
    spans = [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        if last - first < 2:
            continue
        between = points[first + 1:last]
        off = _distance_to_segment(between[:, 0], between[:, 1], points[first], points[last])
        k = int(np.argmax(off))
        if off[k] > tolerance:
            keep.append(first + 1 + k)
            spans += [(first, first + 1 + k), (first + 1 + k, last)]
    return sorted(set(keep))


def _simplify(loop: np.ndarray, tolerance: float) -> np.ndarray:
    """A closed loop with the corners that do not matter taken out."""
    far = int(np.argmax(np.hypot(loop[:, 0] - loop[0, 0], loop[:, 1] - loop[0, 1])))
    first = loop[:far + 1]
    second = np.vstack([loop[far:], loop[:1]])
    corners = [first[k] for k in _keep_corners(first, tolerance)[:-1]]
    corners += [second[k] for k in _keep_corners(second, tolerance)[:-1]]
    out = np.array(corners)

    # A corner the walls barely turn at is not a corner.
    changed = True
    while changed and len(out) > 3:
        changed = False
        for k in range(len(out)):
            before, here, after = out[k - 1], out[k], out[(k + 1) % len(out)]
            a, b = here - before, after - here
            turn = abs(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
            if turn < math.radians(12.0):
                out = np.delete(out, k, axis=0)
                changed = True
                break
    return out


def _fit_wall(
    wx: np.ndarray, wz: np.ndarray, a: np.ndarray, b: np.ndarray, cell: float,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """(a point on, the direction of) the wall the scan shows along the edge a to b, or None when it shows none."""
    length = float(np.hypot(*(b - a)))
    if length < 1e-6:
        return None
    along = (b - a) / length
    across = np.array([-along[1], along[0]])
    t = (wx - a[0]) * along[0] + (wz - a[1]) * along[1]
    s = (wx - a[0]) * across[0] + (wz - a[1]) * across[1]
    margin = min(0.25 * length, max(cell, 0.3))
    near = (np.abs(s) <= 1.5 * cell) & (t >= margin) & (t <= length - margin)
    if near.sum() < 30:
        return None
    plan = np.stack([wx[near], wz[near]], axis=1)
    direction = along
    for _ in range(2):
        mean = np.median(plan, axis=0)
        if len(plan) >= 3:
            _, vectors = np.linalg.eigh(np.cov((plan - mean).T))
            direction = vectors[:, -1]
            if float(direction @ along) < 0:
                direction = -direction
        heading = math.degrees(math.atan2(direction[1], direction[0])) % 90.0
        if min(heading, 90.0 - heading) <= AXIS_SNAP_DEG:
            # Square to the room: exactly so.
            direction = np.round(direction)
        if abs(float(direction @ along)) < math.cos(math.radians(20.0)):
            return None
        off = (plan - mean) @ np.array([-direction[1], direction[0]])
        close = np.abs(off - np.median(off)) <= max(0.06, 0.4 * cell)
        if close.sum() < 20:
            return None
        plan = plan[close]
    middle = np.median(plan, axis=0)
    off = (plan - middle) @ np.array([-direction[1], direction[0]])
    return middle + np.array([-direction[1], direction[0]]) * float(np.median(off)), direction


def _crosses_itself(outline: np.ndarray) -> bool:
    def side(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    count = len(outline)
    for i in range(count):
        a, b = outline[i], outline[(i + 1) % count]
        for j in range(i + 2, count):
            if (j + 1) % count == i:
                continue
            c, d = outline[j], outline[(j + 1) % count]
            if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
                return True
    return False


def find_outline(
    points: np.ndarray, upright: np.ndarray, room: Dict[str, float], cell: float,
) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """(the floor outline as x, z corners, or None for a box; why a room that is not a box is drawn as one).

    The plan is cut into cells and the ones the scan has anything in are the
    room's footprint. Its edge is traced and straightened, and each straight
    run is then moved onto the wall the scan shows along it, so the corners are
    as good as the walls and not as coarse as the cells.
    """
    box_area = (room["x_max"] - room["x_min"]) * (room["z_max"] - room["z_min"])
    grid = _footprint(points[:, 0], points[:, 2], room, cell)
    if grid.sum() >= OUTLINE_BOX_SHARE * grid.size:
        return None, None
    unclear = (
        "The room does not fill its box, but its floor outline was not clear enough to draw "
        "({why}). It is drawn as a box."
    )
    if grid.sum() < OUTLINE_MIN_SHARE * grid.size:
        return None, unclear.format(why="the scan covers too little of the floor")
    loop = _trace(grid)
    if loop is None:
        return None, unclear.format(why="its edge could not be followed")
    rough = _simplify(loop, 1.2) * cell + np.array([room["x_min"], room["z_min"]])
    rough = np.clip(rough, [room["x_min"], room["z_min"]], [room["x_max"], room["z_max"]])
    # A run of a cell or two is the ragged end of a wall that crosses the
    # cells at an angle, not a wall: its two ends become one corner.
    stub = max(2.5 * cell, 0.4)
    shortened = True
    while shortened and len(rough) > 4:
        shortened = False
        for k in range(len(rough)):
            after = (k + 1) % len(rough)
            if float(np.hypot(*(rough[after] - rough[k]))) < stub:
                rough[k] = (rough[k] + rough[after]) / 2.0
                rough = np.delete(rough, after, axis=0)
                shortened = True
                break
    if not 4 <= len(rough) <= OUTLINE_MAX_CORNERS:
        return None, unclear.format(why=f"it came out with {len(rough)} corners")

    wx, wz = points[upright, 0], points[upright, 2]
    count = len(rough)
    walls = [_fit_wall(wx, wz, rough[k], rough[(k + 1) % count], cell) for k in range(count)]
    lengths = [float(np.hypot(*(rough[(k + 1) % count] - rough[k]))) for k in range(count)]
    bare = sum(length for wall, length in zip(walls, lengths) if wall is None)
    if bare > max(1.5, 0.1 * sum(lengths)):
        return None, unclear.format(why="too much of its edge has no wall behind it, as where a scan stops short")

    corners = []
    for k in range(count):
        before, after = walls[k - 1], walls[k]
        corner = rough[k]
        if before is not None and after is not None:
            (p, d), (q, e) = before, after
            cross = d[0] * e[1] - d[1] * e[0]
            if abs(cross) > math.sin(math.radians(8.0)):
                step = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / cross
                corner = p + d * step
        elif before is not None or after is not None:
            # One wall found: the corner slides onto it.
            p, d = before if before is not None else after
            corner = p + d * float((rough[k] - p) @ d)
        if float(np.hypot(*(corner - rough[k]))) > 2.5 * cell + 0.2:
            return None, unclear.format(why="its corners did not agree with its walls")
        corners.append(corner)
    outline = np.array(corners)

    if _crosses_itself(outline):
        return None, unclear.format(why="it crossed itself")
    area = abs(outline_area(outline))
    if area < OUTLINE_MIN_SHARE * box_area:
        return None, unclear.format(why="it is much smaller than the room")
    spans = outline.max(axis=0) - outline.min(axis=0)
    if area >= 0.97 * float(spans[0] * spans[1]):
        return None, None       # a box after all
    if outline_area(outline) < 0:
        outline = outline[::-1]
    return outline, None


# ---------------------------------------------------------------------------
# 6. Raised areas
# ---------------------------------------------------------------------------

def _level_peaks(values: np.ndarray, low: float, high: float, step: float, enough: float, apart: float) -> List[float]:
    """Heights where points pile up well above the general run, strongest first."""
    if high - low < 3 * step or len(values) < 3:
        return []
    counts, edges = np.histogram(values, bins=np.arange(low, high + step, step))
    wide = np.convolve(counts, np.ones(3), mode="same")
    excess = wide - np.median(wide)
    peaks: List[float] = []
    for k in np.argsort(excess)[::-1]:
        if excess[k] < enough:
            break
        centre = float((edges[k] + edges[k + 1]) / 2.0)
        if all(abs(centre - p) > apart for p in peaks):
            peaks.append(centre)
    return peaks


def _turned_box(px: np.ndarray, pz: np.ndarray, area: float) -> Optional[Dict[str, float]]:
    """A level patch's own box where it clearly stands turned from the room's walls, else None.

    The box round the patch is measured at every heading within 45 degrees of
    square, and the smallest is the patch's own. It is kept only when all of
    this holds, so that a patch standing square, a round one, an L and a
    corner piece are each measured along the room's axes exactly as before:

      * it is turned by RAISED_TURN_MIN_DEG or more;
      * its own box is clearly smaller than the box along the room's axes;
      * the patch fills its own box, as a rectangle does.

    `heading` is degrees clockwise from across the room seen from above, over
    -45 and up to 45; `width` runs along it and `depth` square to it, so the
    edge at +depth is the one that faces most nearly downstage.
    """
    if len(px) < RAISED_TURN_MIN_POINTS:
        return None
    step = max(1, len(px) // RAISED_TURN_SAMPLE)
    x, z = px[::step], pz[::step]

    def boxes(degrees: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        cos, sin = np.cos(np.radians(degrees))[:, None], np.sin(np.radians(degrees))[:, None]
        u, v = x[None, :] * cos + z[None, :] * sin, -x[None, :] * sin + z[None, :] * cos
        return u.min(axis=1), u.max(axis=1), v.min(axis=1), v.max(axis=1)

    def smallest(degrees: np.ndarray) -> Tuple[float, Tuple[float, float, float, float]]:
        u0, u1, v0, v1 = boxes(degrees)
        best = int(np.argmin((u1 - u0) * (v1 - v0)))
        return float(degrees[best]), (float(u0[best]), float(u1[best]), float(v0[best]), float(v1[best]))

    rough, _ = smallest(np.arange(-45.0, 45.0, 0.5))
    heading, (u0, u1, v0, v1) = smallest(np.arange(rough - 0.5, rough + 0.5001, 0.05))
    width, depth = u1 - u0, v1 - v0
    if abs(heading) < RAISED_TURN_MIN_DEG or min(width, depth) < RAISED_MIN_SIDE:
        return None
    square = float(px.max() - px.min()) * float(pz.max() - pz.min())
    if width * depth > RAISED_TURN_MAX_SHARE * square:
        return None
    if area < RAISED_TURN_MIN_FILL * width * depth:
        return None
    cos, sin = math.cos(math.radians(heading)), math.sin(math.radians(heading))
    mid_u, mid_v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    own = {
        "center_x": mid_u * cos - mid_v * sin, "center_z": mid_u * sin + mid_v * cos,
        "width": width, "depth": depth, "heading": heading,
    }
    # A stage across a corner is found at 45 or at -45 as the points fall: both
    # are the same rectangle, and it is written the one way (over -45, up to 45).
    return _turn_box(own, 0)


def _turn_box(turned: Dict[str, float], turns: int) -> Dict[str, float]:
    """A turned patch's own box after `turns` quarter turns clockwise seen from above.

    Each quarter turn adds 90 degrees to its heading. A rectangle looks the
    same after half a turn, and one at heading h with sides (w, d) is the one
    at h - 90 with sides (d, w): the heading is brought back over -45 and up
    to 45, so `depth` still runs towards the edge that faces most nearly
    downstage.
    """
    out = dict(turned)
    out["center_x"], out["center_z"] = quarter_turn(turned["center_x"], turned["center_z"], turns)
    heading = turned["heading"] + 90.0 * (turns % 4)
    heading = math.fmod(heading, 180.0)
    if heading > 90.0:
        heading -= 180.0
    if heading > 45.0:
        heading -= 90.0
        out["width"], out["depth"] = turned["depth"], turned["width"]
    elif heading <= -45.0:
        heading += 90.0
        out["width"], out["depth"] = turned["depth"], turned["width"]
    out["heading"] = heading
    return out


def find_raised_areas(
    points: np.ndarray, normals: Optional[np.ndarray], room: Dict[str, float],
    ceiling: float, density: float, cell: float, warnings: List[str],
) -> List[Dict[str, Any]]:
    """Level patches above the floor: a stage, a riser, a booth. Room-aligned, not yet centred."""
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    inside = (
        (x > room["x_min"] + 0.05) & (x < room["x_max"] - 0.05)
        & (z > room["z_min"] + 0.05) & (z < room["z_max"] - 0.05)
    )
    top = min(RAISED_MAX_HEIGHT, ceiling - 0.5)
    band = inside & (y >= RAISED_MIN_HEIGHT) & (y <= top)
    if normals is not None:
        band &= np.abs(normals[:, 1]) > 0.8
    candidates = points[band]
    enough = max(25.0, 0.5 * density * RAISED_MIN_AREA)
    peaks = _level_peaks(candidates[:, 1], RAISED_MIN_HEIGHT - 0.03, top + 0.03, 0.02, enough, 0.1)

    origin = (room["x_min"], room["z_min"])
    floor_area = (room["x_max"] - room["x_min"]) * (room["z_max"] - room["z_min"])
    found: List[Dict[str, Any]] = []
    for peak in peaks:
        slab = candidates[np.abs(candidates[:, 1] - peak) <= 0.05]
        if len(slab) < 10:
            continue
        height = float(np.median(slab[:, 1]))
        cells = _grid(slab, origin, cell)

        keep = None
        if normals is None:
            # No normals to tell a level surface from the wall behind it: a
            # cell counts when it holds far more points at this height than in
            # the half metre above and below it.
            column = points[inside & (np.abs(y - height) > 0.05) & (np.abs(y - height) <= 0.5)]
            column_cells, column_counts = np.unique(_grid(column, origin, cell), axis=0, return_counts=True)
            beside = {(int(c[0]), int(c[1])): int(n) for c, n in zip(column_cells, column_counts)}
            slab_cells, slab_counts = np.unique(cells, axis=0, return_counts=True)
            keep = {
                (int(c[0]), int(c[1])) for c, n in zip(slab_cells, slab_counts)
                if n >= 2 and n >= 2.0 * beside.get((int(c[0]), int(c[1])), 0) * (0.1 / 0.9)
            }

        for patch in _patches(slab, cells, keep):
            area = patch["cells"] * cell * cell
            if area < RAISED_MIN_AREA:
                continue
            px, pz = patch["points"][:, 0], patch["points"][:, 2]
            width, depth = float(px.max() - px.min()), float(pz.max() - pz.min())
            if min(width, depth) < RAISED_MIN_SIDE:
                continue
            if area > 0.85 * floor_area:
                warnings.append(
                    f"A level surface {height:.2f} m up covers most of the room and was not drawn as a "
                    "raised area. If that is the real floor, the floor was read too low."
                )
                continue
            fill = min(1.0, area / max(width * depth, 1e-6))
            if fill < 0.4:
                continue
            extent = {
                "x_min": float(px.min()), "x_max": float(px.max()),
                "z_min": float(pz.min()), "z_max": float(pz.max()),
            }
            # One that clearly stands turned from the walls keeps its own box
            # as well. Its extent along the room's axes is still what says
            # which wall it is nearest, and is left as the scan gave it.
            turned = _turned_box(px, pz, area)
            if turned is not None:
                found.append({**extent, "height": height, "area": area, "fill": fill, "turned": turned})
                continue
            # An edge this close to a wall is built against it.
            for key in extent:
                if abs(extent[key] - room[key]) <= 0.15:
                    extent[key] = room[key]
            found.append({**extent, "height": height, "area": area, "fill": fill})
    found.sort(key=lambda p: -p["area"])
    return found


# ---------------------------------------------------------------------------
# 7. Overhead lines
# ---------------------------------------------------------------------------

def _fit_ring(px: np.ndarray, pz: np.ndarray) -> Optional[Dict[str, float]]:
    """The circle a patch of overhead points lies on, or None when it is not a ring.

    A circle is fitted through the points by least squares. It is a ring when
    the points keep close to that circle all the way round: a square frame of
    truss strays too far from it at its corners, a panel or a cluster fills its
    middle, and an arc leaves most of the way round empty.
    """
    if len(px) < 40:
        return None
    if min(float(px.max() - px.min()), float(pz.max() - pz.min())) < 2 * RING_MIN_RADIUS:
        return None
    # x2 + z2 = 2a x + 2b z + c, with the centre at (a, b) and c = r2 - a2 - b2.
    table = np.stack([2 * px, 2 * pz, np.ones(len(px))], axis=1)
    solved, *_ = np.linalg.lstsq(table, px * px + pz * pz, rcond=None)
    cx, cz = float(solved[0]), float(solved[1])
    squared = float(solved[2]) + cx * cx + cz * cz
    if not squared > 0:
        return None
    radius = math.sqrt(squared)
    if radius < RING_MIN_RADIUS:
        return None
    reach = np.hypot(px - cx, pz - cz)
    inner, outer = np.percentile(reach, [2.0, 98.0])
    stray = max(radius - float(inner), float(outer) - radius)
    if stray > min(RING_MAX_STRAY, RING_MAX_STRAY_SHARE * radius):
        return None
    sector = np.floor((np.arctan2(pz - cz, px - cx) + math.pi) / (2 * math.pi) * RING_SECTORS).astype(np.int64)
    filled = len(np.unique(np.clip(sector, 0, RING_SECTORS - 1)))
    if filled < RING_MIN_SECTORS:
        return None
    return {"center_x": cx, "center_z": cz, "radius": radius, "across": float(outer - inner)}


def _fit_line(px: np.ndarray, pz: np.ndarray) -> Optional[Dict[str, float]]:
    """The long thin thing a patch of overhead points is, whichever way it runs on the plan, or None.

    A line within a couple of degrees of the room's own axes is measured as it
    always was, by its extent along them. Any other heading is measured along
    the patch's own long axis.
    """
    width, depth = float(px.max() - px.min()), float(pz.max() - pz.min())

    def thin(long_side: float, short_side: float) -> bool:
        return long_side >= LINE_MIN_LENGTH and short_side <= LINE_MAX_WIDTH and long_side >= 2.5 * short_side

    heading = 0.0 if width >= depth else 90.0
    along = across = None
    if len(px) >= 3:
        plan = np.stack([px, pz], axis=1)
        mean = plan.mean(axis=0)
        _, vectors = np.linalg.eigh(np.cov((plan - mean).T))
        direction = vectors[:, -1]
        if direction[0] < 0 or (abs(direction[0]) < 1e-12 and direction[1] < 0):
            direction = -direction
        along = (plan - mean) @ direction
        across = (plan - mean) @ np.array([-direction[1], direction[0]])
        heading = math.degrees(math.atan2(direction[1], direction[0]))
        if along is not None and not thin(float(along.max() - along.min()), float(across.max() - across.min())):
            along = None

    squared_up = abs(heading) <= AXIS_SNAP_DEG or abs(heading) >= 90.0 - AXIS_SNAP_DEG
    if along is None or squared_up:
        if not thin(max(width, depth), min(width, depth)):
            return None
        mid_x, mid_z = float(px.min() + px.max()) / 2.0, float(pz.min() + pz.max()) / 2.0
        if width >= depth:
            return {"x1": float(px.min()), "z1": mid_z, "x2": float(px.max()), "z2": mid_z, "across": depth}
        return {"x1": mid_x, "z1": float(pz.min()), "x2": mid_x, "z2": float(pz.max()), "across": width}

    middle = mean + np.array([-direction[1], direction[0]]) * float(across.min() + across.max()) / 2.0
    start, end = middle + direction * float(along.min()), middle + direction * float(along.max())
    return {
        "x1": float(start[0]), "z1": float(start[1]), "x2": float(end[0]), "z2": float(end[1]),
        "across": float(across.max() - across.min()), "angled": 1.0,
    }


def find_overhead(
    points: np.ndarray, room: Dict[str, float], ceiling: float, density: float, cell: float,
    outline: Optional[np.ndarray] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """(hanging-height bands with their lines and rings, other overhead objects). Room-aligned, not yet centred.

    `outline` is the floor outline where the room is not a box. Its inner walls
    stand well inside the room's box, so "clear of the walls" is then measured
    from the outline and not from the box.
    """
    low = max(OVERHEAD_MIN_HEIGHT, 0.45 * ceiling)
    high = ceiling - OVERHEAD_CEILING_CLEARANCE
    if high - low < 0.3:
        return [], 0
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    clear = OVERHEAD_WALL_CLEARANCE
    hanging = points[
        (y >= low) & (y <= high)
        & (x > room["x_min"] + clear) & (x < room["x_max"] - clear)
        & (z > room["z_min"] + clear) & (z < room["z_max"] - clear)
    ]
    if outline is not None and len(hanging):
        hanging = hanging[clear_of_outline(hanging[:, 0], hanging[:, 2], outline, clear)]
    if len(hanging) < 15:
        return [], 0

    step = 0.05
    counts, edges = np.histogram(hanging[:, 1], bins=np.arange(low, high + step, step))
    enough = max(15.0, 0.25 * density)
    busy = counts >= enough
    runs: List[Tuple[int, int]] = []
    k = 0
    while k < len(busy):
        if not busy[k]:
            k += 1
            continue
        end = k
        # A run carries on across one quiet level: a truss's chords with its bracing between.
        while end + 1 < len(busy) and (busy[end + 1] or (end + 2 < len(busy) and busy[end + 2])):
            end += 1
        runs.append((k, end))
        k = end + 1

    grid_cell = max(cell, 0.2)
    origin = (room["x_min"], room["z_min"])
    bands: List[Dict[str, Any]] = []
    others = 0
    for first, last in runs:
        in_run = hanging[(hanging[:, 1] >= edges[first]) & (hanging[:, 1] <= edges[last + 1])]
        lines: List[Dict[str, float]] = []
        rings: List[Dict[str, float]] = []
        for patch in _patches(in_run, _grid(in_run, origin, grid_cell)):
            px, py, pz = patch["points"][:, 0], patch["points"][:, 1], patch["points"][:, 2]
            levels = {"bottom": float(py.min()), "top": float(py.max())}
            ring = _fit_ring(px, pz)
            line = _fit_line(px, pz) if ring is None else None
            if ring is not None:
                rings.append({**ring, **levels})
            elif line is not None:
                lines.append({**line, **levels})
            elif patch["cells"] * grid_cell * grid_cell >= 1.0:
                others += 1
        if lines or rings:
            bands.append({
                "bottom": min(item["bottom"] for item in lines + rings),
                "top": max(item["top"] for item in lines + rings),
                "lines": lines,
                "rings": rings,
            })
    return bands, others


# ---------------------------------------------------------------------------
# 8. Which way round
# ---------------------------------------------------------------------------

def quarter_turn(x: float, z: float, turns: int) -> Tuple[float, float]:
    """A point turned `turns` quarter turns clockwise seen from above (-Z goes to +X)."""
    for _ in range(turns % 4):
        x, z = -z, x
    return x, z


def _turn_extent(item: Dict[str, float], turns: int) -> Dict[str, float]:
    """An x_min/x_max/z_min/z_max box turned in quarter turns."""
    corners = [
        quarter_turn(item["x_min"], item["z_min"], turns),
        quarter_turn(item["x_max"], item["z_max"], turns),
    ]
    out = dict(item)
    out["x_min"], out["x_max"] = sorted(c[0] for c in corners)
    out["z_min"], out["z_max"] = sorted(c[1] for c in corners)
    if "turned" in item:
        out["turned"] = _turn_box(item["turned"], turns)
    return out


def upstage_turns(stage: Optional[Dict[str, float]], half_width: float, half_depth: float) -> int:
    """Quarter turns that put the wall nearest the stage upstage (-Z)."""
    if stage is None:
        return 0
    gaps = [
        (stage["z_min"] + half_depth, 0),     # already against -Z
        (half_width - stage["x_max"], 3),     # against +X: three turns clockwise bring +X round to -Z
        (half_depth - stage["z_max"], 2),     # against +Z
        (stage["x_min"] + half_width, 1),     # against -X
    ]
    return min(gaps, key=lambda g: (round(g[0], 2), gaps.index(g)))[1]


# ---------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------

def _describe_raised(area: float, height: float) -> Tuple[str, str]:
    """(kind, name) for a raised area. A guess from its size alone."""
    if area >= STAGE_MIN_AREA:
        return "stage", "Stage"
    if height >= 0.6:
        return "booth", "Booth or counter"
    return "riser", "Riser"


def extract_room(mesh: ScanMesh, options: Optional[ScanOptions] = None) -> RoomExtraction:
    """Read a room shell out of a scan. Raises RoomScanError when there is no room in it."""
    options = options or ScanOptions()
    if options.rotate % 90:
        raise RoomScanError("The extra turn must be 0, 90, 180 or 270 degrees.")
    assumptions: List[str] = []
    warnings: List[str] = []
    rng = np.random.default_rng(0)      # fixed: the same file gives the same shell

    points, normals, area = surface_points(mesh, rng)

    up = choose_up_axis(points, mesh, options, assumptions)
    points = to_y_up(points, up)
    normals = to_y_up(normals, up) if normals is not None else None

    scale, unit = choose_units(points, mesh, options, assumptions)
    points = points * scale
    if normals is not None:
        lengths = np.linalg.norm(normals, axis=1)
        normals = normals / np.maximum(lengths, 1e-12)[:, None]

    level = np.abs(normals[:, 1]) > 0.8 if normals is not None else None
    floor, ceiling_at = find_floor_and_ceiling(points[:, 1], level, warnings)
    points = points - np.array([0.0, floor, 0.0])
    ceiling = ceiling_at - floor
    if ceiling < 1.8:
        warnings.append(
            f"The room reads as only {ceiling:.2f} m high. Check the units ({unit}) and the up axis ({up.upper()})."
        )
    elif ceiling > 40:
        warnings.append(
            f"The room reads as {ceiling:.1f} m high. Check the units ({unit}) and the up axis ({up.upper()})."
        )

    # Walls: the upright surfaces between the floor and the ceiling.
    upright = (points[:, 1] > 0.3) & (points[:, 1] < ceiling - 0.3)
    if normals is not None:
        upright &= np.abs(normals[:, 1]) < 0.3
    if upright.sum() < 200:
        upright = np.ones(len(points), dtype=bool)
        warnings.append("Few wall surfaces were found; the walls were taken from the whole scan.")
    turn = dominant_wall_turn(points[upright, 0], points[upright, 2])
    points = turn_about_vertical(points, turn)
    normals = turn_about_vertical(normals, turn) if normals is not None else None

    room: Dict[str, float] = {}
    planes = 0
    for key, column, side in (("x_min", 0, -1), ("x_max", 0, 1), ("z_min", 2, -1), ("z_max", 2, 1)):
        room[key], found = _wall(points[upright, column], side)
        planes += 1 if found else 0
    if planes < 4:
        warnings.append(
            f"Only {planes} of the 4 walls were found as flat surfaces; the others were taken from "
            "how far the scan reaches."
        )
    width, depth = room["x_max"] - room["x_min"], room["z_max"] - room["z_min"]
    if width < 1.0 or depth < 1.0:
        raise RoomScanError(
            f"The scan reads as a room {width:.2f} m by {depth:.2f} m, which is not a room. "
            "Check the units and the up axis."
        )

    # Points per square metre of surface, to set how fine a grid the scan can fill.
    if area is not None:
        density = len(points) / max(area * scale * scale, 1e-6)
    else:
        on_floor = int((np.abs(points[:, 1]) <= 0.05).sum())
        density = max(on_floor / (width * depth), len(points) / (2 * width * depth + 2 * ceiling * (width + depth)))
    cell = float(np.clip(math.sqrt(6.0 / max(density, 1e-6)), 0.1, 0.5))
    if density < 20:
        warnings.append(
            "The scan is sparse (about %d points per square metre); small features will have been missed."
            % round(density)
        )

    # A room that is not a box: its floor outline, and the box round that.
    outline, outline_note = find_outline(points, upright, room, cell)
    if outline_note:
        warnings.append(outline_note)
    if outline is not None:
        room = {
            "x_min": float(outline[:, 0].min()), "x_max": float(outline[:, 0].max()),
            "z_min": float(outline[:, 1].min()), "z_max": float(outline[:, 1].max()),
        }
        width, depth = room["x_max"] - room["x_min"], room["z_max"] - room["z_min"]
        assumptions.append(
            f"The room is not a box: its floor outline was traced as {len(outline)} walls. "
            "Its width and depth are those of the box round it."
        )

    raised = find_raised_areas(points, normals, room, ceiling, density, cell, warnings)
    bands, other_overhead = find_overhead(points, room, ceiling, density, cell, outline)

    # Centre the plan on the room, then decide which wall is upstage.
    cx, cz = (room["x_min"] + room["x_max"]) / 2.0, (room["z_min"] + room["z_max"]) / 2.0

    def centred(item: Dict[str, float]) -> Dict[str, float]:
        out = dict(item)
        out["x_min"], out["x_max"] = item["x_min"] - cx, item["x_max"] - cx
        out["z_min"], out["z_max"] = item["z_min"] - cz, item["z_max"] - cz
        if "turned" in item:
            out["turned"] = {
                **item["turned"],
                "center_x": item["turned"]["center_x"] - cx, "center_z": item["turned"]["center_z"] - cz,
            }
        return out

    raised = [centred(r) for r in raised]
    for band in bands:
        for line in band["lines"]:
            line["x1"], line["x2"] = line["x1"] - cx, line["x2"] - cx
            line["z1"], line["z2"] = line["z1"] - cz, line["z2"] - cz
        for ring in band["rings"]:
            ring["center_x"], ring["center_z"] = ring["center_x"] - cx, ring["center_z"] - cz
    if outline is not None:
        outline = outline - np.array([cx, cz])

    auto_turns = upstage_turns(raised[0] if raised else None, width / 2.0, depth / 2.0)
    if raised:
        assumptions.append(
            "The side with the largest raised area was taken as upstage (the booth end). "
            "If the room is the wrong way round, turn it in quarter turns."
        )
    else:
        assumptions.append(
            "No raised area was found to say which end is upstage, so the scan's own heading was kept. "
            "Turn it in quarter turns if the room is the wrong way round."
        )
    turns = (auto_turns + options.rotate // 90) % 4
    if options.rotate % 360:
        assumptions.append(f"Turned a further {options.rotate % 360} degrees clockwise (seen from above), as asked.")
    if turns % 2:
        width, depth = depth, width
    raised = [_turn_extent(r, turns) for r in raised]
    for band in bands:
        for line in band["lines"]:
            line["x1"], line["z1"] = quarter_turn(line["x1"], line["z1"], turns)
            line["x2"], line["z2"] = quarter_turn(line["x2"], line["z2"], turns)
            # Written from stage right to stage left, or from upstage to downstage.
            along_x = abs(line["x2"] - line["x1"]) >= abs(line["z2"] - line["z1"])
            if (line["x1"] > line["x2"]) if (along_x or line.get("angled")) else (line["z1"] > line["z2"]):
                line["x1"], line["z1"], line["x2"], line["z2"] = line["x2"], line["z2"], line["x1"], line["z1"]
        for ring in band["rings"]:
            ring["center_x"], ring["center_z"] = quarter_turn(ring["center_x"], ring["center_z"], turns)
    outline_points: List[Dict[str, float]] = []
    if outline is not None:
        turned = [quarter_turn(float(x), float(z), turns) for x, z in outline]
        # From the corner furthest upstage (then furthest stage right), clockwise seen from above.
        first = min(range(len(turned)), key=lambda k: (round(turned[k][1], 2), round(turned[k][0], 2)))
        outline_points = [{"x": _r(x), "z": _r(z)} for x, z in turned[first:] + turned[:first]]

    # --- The shell ----------------------------------------------------------
    risers = []
    named: Dict[str, int] = {}
    for patch in raised:
        kind, name = _describe_raised(patch["area"], patch["height"])
        named[kind] = named.get(kind, 0) + 1
        own = patch.get("turned")
        if own is not None and _r(own["heading"], 1) != 0.0:
            # It stands turned from the walls: its own middle and sides, and
            # the heading its width runs at (as Edit Room stores one).
            named_as = name if named[kind] == 1 else f"{name} {named[kind]}"
            risers.append({
                "center_x": _r(own["center_x"]),
                "center_z": _r(own["center_z"]),
                "width": _r(own["width"]),
                "depth": _r(own["depth"]),
                "height": _r(patch["height"]),
                "base_height": 0.0,
                "heading_deg": _r(own["heading"], 1),
                "name": named_as,
                "kind": kind,
                "suggested": True,
                "basis": (
                    f"scan: a level area of about {patch['area']:.1f} m2, {patch['height']:.2f} m above the floor, "
                    f"standing turned {abs(own['heading']):.0f} degrees from the room's walls. "
                    "What it is was guessed from its size."
                ),
            })
            assumptions.append(
                f"{named_as} stands turned {abs(own['heading']):.0f} degrees from the room's walls "
                f"({'clockwise' if own['heading'] > 0 else 'anticlockwise'} seen from above), measured from its top. "
                "Fixtures suggested onto it are turned with it. If it stands square, set its Heading to 0 in Edit Room."
            )
            continue
        risers.append({
            "center_x": _r((patch["x_min"] + patch["x_max"]) / 2.0),
            "center_z": _r((patch["z_min"] + patch["z_max"]) / 2.0),
            "width": _r(patch["x_max"] - patch["x_min"]),
            "depth": _r(patch["z_max"] - patch["z_min"]),
            "height": _r(patch["height"]),
            "base_height": 0.0,
            "name": name if named[kind] == 1 else f"{name} {named[kind]}",
            "kind": kind,
            "suggested": True,
            "basis": (
                f"scan: a level area of about {patch['area']:.1f} m2, {patch['height']:.2f} m above the floor. "
                "What it is was guessed from its size."
            ),
        })

    truss_lines = []
    truss_rings = []
    hanging_bands = []
    for band in sorted(bands, key=lambda b: b["bottom"]):
        hanging_bands.append({
            "height": _r(band["bottom"]),
            "top": _r(band["top"]),
            "lines": len(band["lines"]),
            "rings": len(band["rings"]),
            "suggested": True,
            "basis": (
                "scan: long thin objects hanging clear of the walls at this height" if band["lines"]
                else "scan: a ring hanging clear of the walls at this height"
            ),
        })
        for line in sorted(band["lines"], key=lambda l: (min(l["z1"], l["z2"]), min(l["x1"], l["x2"]))):
            run_x, run_z = line["x2"] - line["x1"], line["z2"] - line["z1"]
            angled = bool(line.get("angled"))
            along_x = abs(run_x) >= abs(run_z)
            # Clockwise from across the room, seen from above: 0 runs across, 90 upstage to downstage.
            heading = math.degrees(math.atan2(run_z, run_x)) if angled else (0.0 if along_x else 90.0)
            truss_lines.append({
                "name": f"Overhead line {len(truss_lines) + 1}",
                "x1": _r(line["x1"]), "z1": _r(line["z1"]), "x2": _r(line["x2"]), "z2": _r(line["z2"]),
                "height": _r(line["bottom"]),
                "top": _r(line["top"]),
                "length": _r(math.hypot(run_x, run_z)),
                "across": _r(line["across"]),
                "axis": "angled" if angled else "x" if along_x else "z",
                "heading_deg": _r(heading, 1),
                "suggested": True,
                "basis": (
                    "scan: a long thin object hanging clear of the walls; taken for a truss or bar"
                    + (f", running at {abs(heading):.0f} degrees to the room" if angled else "")
                ),
            })
        for ring in sorted(band["rings"], key=lambda r: (r["center_z"], r["center_x"])):
            truss_rings.append({
                "name": f"Overhead ring {len(truss_rings) + 1}",
                "center_x": _r(ring["center_x"]),
                "center_z": _r(ring["center_z"]),
                "radius": _r(ring["radius"]),
                "height": _r(ring["bottom"]),
                "top": _r(ring["top"]),
                "across": _r(ring["across"]),
                "suggested": True,
                "basis": (
                    "scan: points hanging clear of the walls that keep to one circle all the way round; "
                    "taken for a ring of truss"
                ),
            })

    counted = f"{len(mesh.vertices):,} points" + (
        "" if mesh.is_point_cloud else f", {len(mesh.faces):,} triangles"
    )
    shell: Dict[str, Any] = {
        "basis": (
            f"Suggested from a room scan ({mesh.source_file or mesh.format}, {counted}). "
            "Nothing here has been checked against the room."
        ),
        "source": "scan",
        "suggested": True,
        "room": {
            "width": _r(width),
            "depth": _r(depth),
            "height": _r(ceiling),
            "suggested": True,
            "basis": (
                f"scan: {planes} of 4 walls found as flat surfaces; "
                "floor and ceiling from the densest levels at the bottom and top"
            ),
        },
        "risers": risers,
        "truss_lines": truss_lines,
        "truss_rings": truss_rings,
        "hanging_bands": hanging_bands,
        "scan": {
            "file": mesh.source_file,
            "format": mesh.format,
            "points": int(len(mesh.vertices)),
            "triangles": 0 if mesh.is_point_cloud else int(len(mesh.faces)),
            "point_cloud": bool(mesh.is_point_cloud),
            "units": unit,
            "up_axis": up,
            "wall_turn_deg": _r(math.degrees(turn)),
            "quarter_turns": int(turns),
            "walls_found": planes,
            "other_overhead_objects": int(other_overhead),
            "objects": mesh.objects,
        },
    }
    if outline_points:
        # Only a room that is not a box carries an outline: its walls are the
        # segments between these corners, in order, the last back to the first.
        shell["room"]["outline"] = outline_points
        shell["room"]["basis"] = (
            f"scan: the floor outline traced as {len(outline_points)} walls, each moved onto the wall "
            "the scan shows along it; width and depth are the box round it; "
            "floor and ceiling from the densest levels at the bottom and top"
        )
    if other_overhead:
        warnings.append(
            f"{other_overhead} other object{'s' if other_overhead != 1 else ''} overhead "
            "(not long and thin) were seen and not drawn."
        )
    if not truss_lines and not truss_rings:
        assumptions.append(
            "No truss or bar was found overhead, so overhead fixtures keep their height unless the "
            "layout had them above the ceiling."
        )
    return RoomExtraction(
        shell=shell, assumptions=assumptions + list(mesh.notes), warnings=list(mesh.warnings) + warnings,
    )
