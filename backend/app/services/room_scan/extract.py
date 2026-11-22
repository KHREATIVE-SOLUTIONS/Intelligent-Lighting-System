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
   2.2 m above the floor, at least 1.5 m2.
7. Overhead lines (a truss, a lighting bar): long thin things hanging clear of
   the walls in the upper half of the room, grouped into hanging-height bands.
8. Which way is upstage. The walls leave four ways round. The side with the
   largest raised area becomes upstage; with no raised area the scan's own
   heading is kept. The caller can turn it further in quarter turns.

The turns are all rotations, never a mirror, so stage left stays stage left.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

# An overhead line: long, thin, clear of the walls, in the upper room.
OVERHEAD_MIN_HEIGHT = 2.0
OVERHEAD_CEILING_CLEARANCE = 0.2
OVERHEAD_WALL_CLEARANCE = 0.3
LINE_MIN_LENGTH = 1.5
LINE_MAX_WIDTH = 1.2


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

def find_overhead(
    points: np.ndarray, room: Dict[str, float], ceiling: float, density: float, cell: float,
) -> Tuple[List[Dict[str, Any]], int]:
    """(hanging-height bands with their lines, other overhead objects). Room-aligned, not yet centred."""
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
        lines = []
        for patch in _patches(in_run, _grid(in_run, origin, grid_cell)):
            px, py, pz = patch["points"][:, 0], patch["points"][:, 1], patch["points"][:, 2]
            width, depth = float(px.max() - px.min()), float(pz.max() - pz.min())
            long_side, short_side = max(width, depth), min(width, depth)
            if long_side >= LINE_MIN_LENGTH and short_side <= LINE_MAX_WIDTH and long_side >= 2.5 * short_side:
                lines.append({
                    "x_min": float(px.min()), "x_max": float(px.max()),
                    "z_min": float(pz.min()), "z_max": float(pz.max()),
                    "bottom": float(py.min()), "top": float(py.max()),
                })
            elif patch["cells"] * grid_cell * grid_cell >= 1.0:
                others += 1
        if lines:
            bands.append({
                "bottom": min(line["bottom"] for line in lines),
                "top": max(line["top"] for line in lines),
                "lines": lines,
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

    raised = find_raised_areas(points, normals, room, ceiling, density, cell, warnings)
    bands, other_overhead = find_overhead(points, room, ceiling, density, cell)

    # Centre the plan on the room, then decide which wall is upstage.
    cx, cz = (room["x_min"] + room["x_max"]) / 2.0, (room["z_min"] + room["z_max"]) / 2.0

    def centred(item: Dict[str, float]) -> Dict[str, float]:
        out = dict(item)
        out["x_min"], out["x_max"] = item["x_min"] - cx, item["x_max"] - cx
        out["z_min"], out["z_max"] = item["z_min"] - cz, item["z_max"] - cz
        return out

    raised = [centred(r) for r in raised]
    for band in bands:
        band["lines"] = [centred(line) for line in band["lines"]]

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
        band["lines"] = [_turn_extent(line, turns) for line in band["lines"]]

    # --- The shell ----------------------------------------------------------
    risers = []
    named: Dict[str, int] = {}
    for patch in raised:
        kind, name = _describe_raised(patch["area"], patch["height"])
        named[kind] = named.get(kind, 0) + 1
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
    hanging_bands = []
    for band in sorted(bands, key=lambda b: b["bottom"]):
        hanging_bands.append({
            "height": _r(band["bottom"]),
            "top": _r(band["top"]),
            "lines": len(band["lines"]),
            "suggested": True,
            "basis": "scan: long thin objects hanging clear of the walls at this height",
        })
        for line in sorted(band["lines"], key=lambda l: (l["z_min"], l["x_min"])):
            along_x = (line["x_max"] - line["x_min"]) >= (line["z_max"] - line["z_min"])
            mid_x, mid_z = (line["x_min"] + line["x_max"]) / 2.0, (line["z_min"] + line["z_max"]) / 2.0
            ends = (
                (line["x_min"], mid_z, line["x_max"], mid_z) if along_x
                else (mid_x, line["z_min"], mid_x, line["z_max"])
            )
            length = (line["x_max"] - line["x_min"]) if along_x else (line["z_max"] - line["z_min"])
            across = (line["z_max"] - line["z_min"]) if along_x else (line["x_max"] - line["x_min"])
            truss_lines.append({
                "name": f"Overhead line {len(truss_lines) + 1}",
                "x1": _r(ends[0]), "z1": _r(ends[1]), "x2": _r(ends[2]), "z2": _r(ends[3]),
                "height": _r(line["bottom"]),
                "top": _r(line["top"]),
                "length": _r(length),
                "across": _r(across),
                "axis": "x" if along_x else "z",
                "suggested": True,
                "basis": "scan: a long thin object hanging clear of the walls; taken for a truss or bar",
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
    if other_overhead:
        warnings.append(
            f"{other_overhead} other object{'s' if other_overhead != 1 else ''} overhead "
            "(not long and thin) were seen and not drawn."
        )
    if not truss_lines:
        assumptions.append(
            "No truss or bar was found overhead, so overhead fixtures keep their height unless the "
            "layout had them above the ceiling."
        )
    return RoomExtraction(
        shell=shell, assumptions=assumptions + list(mesh.notes), warnings=list(mesh.warnings) + warnings,
    )
