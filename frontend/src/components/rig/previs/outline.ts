/**
 * The floor outline of a scanned room that is not a box, and everything the
 * view asks of it: which side of a wall a point is on, how far a point is from
 * the walls, what a line across the room passes through, where a point outside
 * is held to, and the outline with a wall moved out for a fixture beyond it.
 *
 * Pure numbers on the plan: no three.js, no React, and nothing imported at run
 * time, so the layout, the beams, the drag and the cameras can all read one
 * outline. docs/ROOM_SCAN.md.
 *
 * Axes are the rig's: metres, X across, -Z upstage. An outline is the corners
 * of the floor in order, the last joined back to the first.
 */
import type { RoomShell } from '../../../types';

const finite = (...values: unknown[]) => values.every((value) => typeof value === 'number' && Number.isFinite(value));

/**
 * The room's own box, where it is known: wall to wall and floor to ceiling,
 * centred on the origin. A room scan gives one (`room_shell.room`).
 */
export type KnownRoom = { width: number; depth: number; height: number };

/** True for a room whose three sizes are real numbers a room could have. */
export function usableRoom(room: Partial<KnownRoom> | null | undefined): room is KnownRoom {
  return Boolean(room)
    && [room!.width, room!.depth, room!.height].every((v) => typeof v === 'number' && Number.isFinite(v))
    && room!.width! >= 1 && room!.depth! >= 1 && room!.height! >= 1.5;
}

export type OutlinePoint = { x: number; z: number };

/** One wall of a room's outline, as the view stands it up. */
export type OutlineWall = {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  length: number;
  midX: number;
  midZ: number;
  /** Unit vector on the plan pointing into the room. */
  inX: number;
  inZ: number;
  /** The turn about Y that faces a wall modelled looking down +Z into the room. */
  yaw: number;
};

/** Signed area on the plan: positive for corners in clockwise order seen from above. */
export function outlineArea(outline: OutlinePoint[]): number {
  let twice = 0;
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    twice += a.x * b.z - b.x * a.z;
  }
  return twice / 2;
}

/**
 * The floor outline of a scanned room that is not a box, corners in order, or
 * null: for a box room, a shell stored before outlines were read, any shell
 * that is not a scan, and an outline that is not one (too few corners, a
 * number missing, no area). `position_outline` in
 * backend/app/api/endpoints/fixture_position.py reads it by the same rule.
 */
export function roomOutline(shell: RoomShell | null | undefined): OutlinePoint[] | null {
  if (!shell || shell.source !== 'scan') return null;
  const room = shell.room;
  if (!room || !usableRoom(room)) return null;
  const raw = room.outline;
  if (!Array.isArray(raw) || raw.length < 3) return null;
  if (!raw.every((point) => point && finite(point.x, point.z))) return null;
  const outline = raw.map((point) => ({ x: point.x, z: point.z }));
  if (!(Math.abs(outlineArea(outline)) >= 1)) return null;
  return outline;
}

/**
 * The walls of an outline: one per pair of neighbouring corners, the last
 * corner joined back to the first, each knowing which side of it the room is
 * on. The corners may come in either order round the room.
 */
export function outlineWalls(outline: OutlinePoint[]): OutlineWall[] {
  const clockwise = outlineArea(outline) > 0;
  const walls: OutlineWall[] = [];
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const length = Math.hypot(dx, dz);
    if (!(length > 0.01)) continue;
    // With the corners clockwise seen from above, the room is on the side (-dz, dx).
    const sign = clockwise ? 1 : -1;
    const inX = (-dz / length) * sign + 0;
    const inZ = (dx / length) * sign + 0;
    walls.push({
      x1: a.x, z1: a.z, x2: b.x, z2: b.z, length,
      midX: (a.x + b.x) / 2, midZ: (a.z + b.z) / 2,
      inX, inZ,
      // A turn of `a` about Y takes +Z to (sin a, cos a) on the plan.
      yaw: Math.atan2(inX, inZ),
    });
  }
  return walls;
}

/** Whether a point on the plan is on the room's side of a wall: a camera there sees the wall's face. */
export function onRoomSide(wall: OutlineWall, x: number, z: number): boolean {
  return (x - wall.midX) * wall.inX + (z - wall.midZ) * wall.inZ > 0;
}

/** Whether a point on the plan is inside an outline. */
export function insideOutline(outline: OutlinePoint[], x: number, z: number): boolean {
  let inside = false;
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    if ((a.z > z) !== (b.z > z) && x < a.x + ((z - a.z) * (b.x - a.x)) / (b.z - a.z)) inside = !inside;
  }
  return inside;
}

/** The box round an outline. */
export function outlineBox(outline: OutlinePoint[]): { xMin: number; xMax: number; zMin: number; zMax: number } {
  let xMin = Infinity;
  let xMax = -Infinity;
  let zMin = Infinity;
  let zMax = -Infinity;
  for (const point of outline) {
    xMin = Math.min(xMin, point.x);
    xMax = Math.max(xMax, point.x);
    zMin = Math.min(zMin, point.z);
    zMax = Math.max(zMax, point.z);
  }
  return { xMin, xMax, zMin, zMax };
}

/**
 * The nearest point of the outline's walls to (x, z), how far off it is, and
 * which segment it is on (the one from corner `segment` to the next). Of two
 * segments equally near, the earlier wins: the server breaks the tie the same
 * way.
 */
export function nearestOnOutline(
  outline: OutlinePoint[], x: number, z: number,
): { x: number; z: number; distance: number; segment: number } {
  let best = { x, z, distance: Infinity, segment: -1 };
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const lengthSq = dx * dx + dz * dz;
    const along = lengthSq > 0
      ? Math.max(0, Math.min(1, ((x - a.x) * dx + (z - a.z) * dz) / lengthSq))
      : 0;
    const px = a.x + along * dx;
    const pz = a.z + along * dz;
    const distance = Math.hypot(x - px, z - pz);
    if (distance < best.distance) best = { x: px, z: pz, distance, segment: i };
  }
  return best;
}

/**
 * A point held to the room: left alone inside the outline or within `margin`
 * of it, and otherwise brought straight towards the nearest point of the walls
 * until it is `margin` from it. The notch of an L is outside the room, so a
 * point deep in a notch comes back towards its walls.
 */
export function holdNearOutline(outline: OutlinePoint[], x: number, z: number, margin: number): OutlinePoint {
  if (insideOutline(outline, x, z)) return { x, z };
  const near = nearestOnOutline(outline, x, z);
  if (!(near.distance > margin)) return { x, z };
  const share = margin / near.distance;
  return { x: near.x + (x - near.x) * share, z: near.z + (z - near.z) * share };
}

/** A stretch of a straight line that is inside the room: from, to. */
export type Span = [number, number];

function crossings(outline: OutlinePoint[], at: number, alongX: boolean): Span[] {
  const hits: number[] = [];
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    // The line runs along `u` at `v = at`.
    const au = alongX ? a.x : a.z;
    const av = alongX ? a.z : a.x;
    const bu = alongX ? b.x : b.z;
    const bv = alongX ? b.z : b.x;
    if ((av > at) !== (bv > at)) hits.push(au + ((at - av) * (bu - au)) / (bv - av));
  }
  hits.sort((p, q) => p - q);
  // In at one crossing and out at the next: a room with a notch gives several stretches.
  const spans: Span[] = [];
  for (let i = 0; i + 1 < hits.length; i += 2) {
    if (hits[i + 1] > hits[i]) spans.push([hits[i], hits[i + 1]]);
  }
  return spans;
}

/** The stretches of the line across the room at depth `z` that are inside the outline, stage right to stage left. */
export function outlineSpansX(outline: OutlinePoint[], z: number): Span[] {
  return crossings(outline, z, true);
}

/** The stretches of the line up and down stage at `x` that are inside the outline, upstage to downstage. */
export function outlineSpansZ(outline: OutlinePoint[], x: number): Span[] {
  return crossings(outline, x, false);
}

/** The stretches two lists of stretches both cover. */
export function spansInBoth(a: Span[], b: Span[]): Span[] {
  const both: Span[] = [];
  for (const p of a) {
    for (const q of b) {
      const from = Math.max(p[0], q[0]);
      const to = Math.min(p[1], q[1]);
      if (to > from) both.push([from, to]);
    }
  }
  return both.sort((p, q) => p[0] - q[0]);
}

/** How far a point inside the outline is from the nearest wall; negative outside it. */
export function outlineClearance(outline: OutlinePoint[], x: number, z: number): number {
  const distance = nearestOnOutline(outline, x, z).distance;
  return insideOutline(outline, x, z) ? distance : -distance;
}

/**
 * The nearest place to (x, z) that is in the room and at least `clear` from
 * every wall: (x, z) itself when it already is. Found on a grid over the
 * outline's box, so it is as near as the grid is fine and no nearer. A room
 * with nowhere that clear gives its most open point.
 */
export function insetPoint(outline: OutlinePoint[], x: number, z: number, clear: number, step = 0.25): OutlinePoint {
  if (outlineClearance(outline, x, z) >= clear) return { x, z };
  const box = outlineBox(outline);
  let best: OutlinePoint | null = null;
  let bestDistance = Infinity;
  let open: OutlinePoint = { x, z };
  let openClearance = -Infinity;
  const nx = Math.max(1, Math.ceil((box.xMax - box.xMin) / step));
  const nz = Math.max(1, Math.ceil((box.zMax - box.zMin) / step));
  for (let i = 0; i <= nx; i += 1) {
    for (let j = 0; j <= nz; j += 1) {
      const gx = box.xMin + ((box.xMax - box.xMin) * i) / nx;
      const gz = box.zMin + ((box.zMax - box.zMin) * j) / nz;
      const clearance = outlineClearance(outline, gx, gz);
      if (clearance > openClearance) {
        openClearance = clearance;
        open = { x: gx, z: gz };
      }
      if (clearance < clear) continue;
      const distance = Math.hypot(gx - x, gz - z);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { x: gx, z: gz };
      }
    }
  }
  return best ?? open;
}

function segmentsCross(a: OutlinePoint, b: OutlinePoint, c: OutlinePoint, d: OutlinePoint): boolean {
  const side = (p: OutlinePoint, q: OutlinePoint, r: OutlinePoint) => (q.x - p.x) * (r.z - p.z) - (q.z - p.z) * (r.x - p.x);
  const d1 = side(a, b, c);
  const d2 = side(a, b, d);
  const d3 = side(c, d, a);
  const d4 = side(c, d, b);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/** Whether any two walls of an outline that are not neighbours cross. */
export function outlineCrossesItself(outline: OutlinePoint[]): boolean {
  const count = outline.length;
  for (let i = 0; i < count; i += 1) {
    for (let j = i + 1; j < count; j += 1) {
      if (j === i + 1 || (i === 0 && j === count - 1)) continue;
      if (segmentsCross(outline[i], outline[(i + 1) % count], outline[j], outline[(j + 1) % count])) return true;
    }
  }
  return false;
}

/** Where the line through `p` along `d` meets the line through `q` along `e`, or null for two that run the same way. */
function meet(p: OutlinePoint, dx: number, dz: number, q: OutlinePoint, ex: number, ez: number): OutlinePoint | null {
  const cross = dx * ez - dz * ex;
  if (Math.abs(cross) < 1e-9 * (Math.hypot(dx, dz) * Math.hypot(ex, ez) + 1e-12)) return null;
  const t = ((q.x - p.x) * ez - (q.z - p.z) * ex) / cross;
  return { x: p.x + dx * t, z: p.z + dz * t };
}

/**
 * The outline with the wall from corner `segment` to the next moved `by`
 * metres straight out of the room. Its two ends slide along the walls either
 * side, which grow or shrink to meet it; next to a wall running the same way
 * it gets a short return wall instead. Null when that is no longer a room: a
 * neighbour shrunk to nothing or turned round, or walls crossing.
 */
export function moveWallOut(outline: OutlinePoint[], segment: number, by: number): OutlinePoint[] | null {
  const count = outline.length;
  if (count < 3 || !(by > 0) || segment < 0 || segment >= count) return null;
  const area = outlineArea(outline);
  const a = outline[segment];
  const b = outline[(segment + 1) % count];
  const before = outline[(segment - 1 + count) % count];
  const after = outline[(segment + 2) % count];
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const length = Math.hypot(dx, dz);
  if (!(length > 0.01)) return null;
  // Out of the room is the other way from `outlineWalls`' inward side.
  const sign = area > 0 ? 1 : -1;
  const outX = (dz / length) * sign;
  const outZ = (-dx / length) * sign;
  const movedA = { x: a.x + outX * by, z: a.z + outZ * by };

  const newA = meet(movedA, dx, dz, before, a.x - before.x, a.z - before.z);
  const newB = meet(movedA, dx, dz, after, b.x - after.x, b.z - after.z);
  const moved: OutlinePoint[] = [];
  for (let i = 0; i < count; i += 1) {
    if (i === segment) {
      // A neighbour running the same way cannot meet the moved wall: keep the corner and step out from it.
      if (newA) moved.push(newA);
      else moved.push(a, movedA);
    } else if (i === (segment + 1) % count) {
      if (newB) moved.push(newB);
      else moved.push({ x: b.x + outX * by, z: b.z + outZ * by }, b);
    } else {
      moved.push(outline[i]);
    }
  }
  // The walls either side still run the way they did, and have not shrunk to nothing.
  if (newA) {
    const kept = (newA.x - before.x) * (a.x - before.x) + (newA.z - before.z) * (a.z - before.z);
    if (!(kept > 0) || Math.hypot(newA.x - before.x, newA.z - before.z) <= 0.01) return null;
  }
  if (newB) {
    const kept = (after.x - newB.x) * (after.x - b.x) + (after.z - newB.z) * (after.z - b.z);
    if (!(kept > 0) || Math.hypot(after.x - newB.x, after.z - newB.z) <= 0.01) return null;
  }
  const end = newB ?? { x: b.x + outX * by, z: b.z + outZ * by };
  const start = newA ?? movedA;
  if (!((end.x - start.x) * dx + (end.z - start.z) * dz > 0.01 * length)) return null;
  const movedArea = outlineArea(moved);
  if (!(movedArea * area > 0) || Math.abs(movedArea) < Math.abs(area)) return null;
  if (outlineCrossesItself(moved)) return null;
  return moved;
}

/** How far past a fixture a wall that moves out for it goes: the box's walls leave the same. */
export const WALL_PAST_FIXTURE = 0.15;

/**
 * The outline as the view draws it: the scan's, with a wall moved out for each
 * fixture standing outside the room, as the walls of a box room move out, so
 * no fixture is drawn through a wall. The wall nearest the fixture moves,
 * straight out, to `past` beyond it. A fixture a wall cannot be moved for
 * without the outline ceasing to be a room is left outside, and the walls
 * stay where the scan put them for it.
 *
 * The same array comes back when nothing had to move.
 */
export function outlineAround(
  outline: OutlinePoint[],
  points: OutlinePoint[],
  past = WALL_PAST_FIXTURE,
): OutlinePoint[] {
  let current = outline;
  for (const point of points) {
    if (!finite(point.x, point.z)) continue;
    let trial = current;
    let settled = insideOutline(trial, point.x, point.z);
    // Beyond a corner a fixture is outside two walls: one moves, then the other.
    for (let pass = 0; pass < 3 && !settled; pass += 1) {
      const clockwise = outlineArea(trial) > 0 ? 1 : -1;
      let segment = -1;
      let beyond = 0;
      let nearest = Infinity;
      for (let i = 0; i < trial.length; i += 1) {
        const a = trial[i];
        const b = trial[(i + 1) % trial.length];
        const dx = b.x - a.x;
        const dz = b.z - a.z;
        const length = Math.hypot(dx, dz);
        if (!(length > 0.01)) continue;
        // How far the point is on the outer side of this wall's line.
        const out = (((point.x - a.x) * dz - (point.z - a.z) * dx) / length) * clockwise;
        if (!(out > 0)) continue;
        const along = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.z - a.z) * dz) / (length * length)));
        const distance = Math.hypot(point.x - (a.x + along * dx), point.z - (a.z + along * dz));
        if (distance < nearest - 1e-9 || (Math.abs(distance - nearest) <= 1e-9 && out > beyond)) {
          nearest = distance;
          segment = i;
          beyond = out;
        }
      }
      if (segment < 0) break;
      const moved = moveWallOut(trial, segment, beyond + past);
      if (!moved) break;
      trial = moved;
      settled = insideOutline(trial, point.x, point.z);
    }
    if (settled) current = trial;
  }
  return current;
}
