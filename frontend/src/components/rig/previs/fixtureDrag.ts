// Moving a fixture in the 3D view: the geometry of a drag, snapping to what a
// room scan found, the limits a position is held to, and keyboard nudges.
//
// Pure: no three.js, no React, no server. The view turns a pointer event into
// a ray and hands it here (FixtureDragLayer.tsx); what comes back is where the
// fixture goes. docs/3D_PREVIEW.md, docs/ROOM_SCAN.md.
//
// Axes are the rig's: metres, origin at the centre of the floor, X across,
// Y up, -Z upstage.
import type { Rig, RigFixture, RoomShell } from '../../../types';

export type Point3 = { x: number; y: number; z: number };

/** A ray from the camera through the pointer. The direction need not be unit length. */
export type Ray = { origin: Point3; direction: Point3 };

/** Beyond this a hit is a grazing ray heading for the horizon, not a place in the room. */
export const MAX_DRAG_REACH_M = 200;

/** How close, on the plan, a dragged fixture has to come to a line to snap onto it. */
export const SNAP_RADIUS_M = 0.4;
/** A line is only a snap target for a fixture within this of its height. */
export const SNAP_HEIGHT_WINDOW_M = 1.5;

/** How far past the stage or the scanned room a fixture may go. The server holds the same line. */
export const OUTSIDE_MARGIN_M = 2;

/** A drag shorter than this is a click: it selects and saves nothing. */
export const MOVED_FROM_M = 0.02;

export const NUDGE_STEP_M = 0.1;
export const NUDGE_BIG_STEP_M = 1;

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

/** To the millimetre, which is what the server stores. */
export function roundMm(value: number): number {
  return Math.round(value * 1000) / 1000;
}

// ---------------------------------------------------------------------------
// Rays
// ---------------------------------------------------------------------------

/** Where a ray meets the horizontal plane at `planeY`, or null if it does not in front of the camera. */
export function rayOnHorizontalPlane(ray: Ray, planeY: number): { x: number; z: number } | null {
  const { origin, direction } = ray;
  if (Math.abs(direction.y) < 1e-6) return null;
  const along = (planeY - origin.y) / direction.y;
  if (!(along > 0)) return null;
  const length = Math.hypot(direction.x, direction.y, direction.z);
  if (!(length > 0) || along * length > MAX_DRAG_REACH_M) return null;
  return { x: origin.x + along * direction.x, z: origin.z + along * direction.z };
}

/**
 * The height on the vertical line through (x, z) that a ray passes closest
 * to: what the pointer is pointing at when a fixture is moved up and down.
 * Null when the camera looks straight along that line, or the line is behind it.
 */
export function rayHeight(ray: Ray, anchor: { x: number; z: number }): number | null {
  const { origin, direction } = ray;
  const wx = origin.x - anchor.x;
  const wz = origin.z - anchor.z;
  const a = direction.x * direction.x + direction.y * direction.y + direction.z * direction.z;
  const b = direction.y;
  const d = direction.x * wx + direction.y * origin.y + direction.z * wz;
  const e = origin.y;
  const denominator = a - b * b;
  if (!(a > 0) || denominator < 1e-6 * a) return null;
  const alongRay = (b * e - d) / denominator;
  if (!(alongRay > 0)) return null;
  const height = (a * e - b * d) / denominator;
  return Number.isFinite(height) ? height : null;
}

// ---------------------------------------------------------------------------
// A drag, step by step
// ---------------------------------------------------------------------------

export type DragMode = 'plan' | 'height';

/**
 * A drag in progress, in the scene's own coordinates: `y` is the height the
 * fixture is drawn at. The offsets are between where the pointer's ray lands
 * and where the fixture is, so a fixture picked up off-centre does not jump.
 */
export type DragState = {
  x: number;
  y: number;
  z: number;
  mode: DragMode | null;
  offX: number;
  offY: number;
  offZ: number;
};

export function beginDrag(at: Point3): DragState {
  return { x: at.x, y: at.y, z: at.z, mode: null, offX: 0, offY: 0, offZ: 0 };
}

/**
 * The drag after one pointer move. Along the plan at the fixture's height, or
 * with `heightMode` (Shift held) straight up and down where it stands.
 *
 * The first move in a mode only takes the grip: the fixture stays put and the
 * offset is remembered. A ray that misses (the plane seen edge on, the horizon)
 * leaves the drag as it was.
 */
export function dragStep(state: DragState, ray: Ray, heightMode: boolean): DragState {
  if (heightMode) {
    const height = rayHeight(ray, state);
    if (height === null) return state;
    if (state.mode !== 'height') return { ...state, mode: 'height', offY: state.y - height };
    return { ...state, y: height + state.offY };
  }
  const hit = rayOnHorizontalPlane(ray, state.y);
  if (!hit) return state;
  if (state.mode !== 'plan') return { ...state, mode: 'plan', offX: state.x - hit.x, offZ: state.z - hit.z };
  return { ...state, x: hit.x + state.offX, z: hit.z + state.offZ };
}

// ---------------------------------------------------------------------------
// Snapping to what a room scan found
// ---------------------------------------------------------------------------

/** A line on the plan at a height: a truss or bar, or one edge of a stage, riser or booth. */
export type SnapLine = {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  /** For a truss the height a fixture hangs at; for an edge the top of the raised area. */
  height: number;
  kind: 'truss' | 'edge';
  name: string;
};

/** Every line a fixture can snap to in a scanned room. Empty for any other room. */
export function snapLines(shell: RoomShell | null | undefined): SnapLine[] {
  if (!shell || shell.source !== 'scan') return [];
  const lines: SnapLine[] = [];
  (shell.truss_lines ?? []).forEach((line, index) => {
    if (![line.x1, line.z1, line.x2, line.z2, line.height].every(finite)) return;
    lines.push({
      x1: line.x1, z1: line.z1, x2: line.x2, z2: line.z2,
      height: line.height, kind: 'truss', name: line.name || `Overhead line ${index + 1}`,
    });
  });
  (shell.risers ?? []).forEach((box, index) => {
    if (![box.center_x, box.center_z, box.width, box.depth, box.height].every(finite)) return;
    if (!(box.width > 0 && box.depth > 0)) return;
    const name = box.name || `Raised area ${index + 1}`;
    const top = (finite(box.base_height) ? box.base_height : 0) + box.height;
    const x1 = box.center_x - box.width / 2;
    const x2 = box.center_x + box.width / 2;
    const z1 = box.center_z - box.depth / 2;
    const z2 = box.center_z + box.depth / 2;
    const edge = (ax: number, az: number, bx: number, bz: number, side: string): SnapLine => ({
      x1: ax, z1: az, x2: bx, z2: bz, height: top, kind: 'edge', name: `${name}, ${side} edge`,
    });
    lines.push(
      edge(x1, z1, x2, z1, 'upstage'),
      edge(x1, z2, x2, z2, 'downstage'),
      edge(x1, z1, x1, z2, 'stage right'),
      edge(x2, z1, x2, z2, 'stage left'),
    );
  });
  return lines;
}

/** The nearest point to (x, z) on a line that ends at its ends. */
export function nearestOnSegment(
  x: number, z: number, line: { x1: number; z1: number; x2: number; z2: number },
): { x: number; z: number; distance: number } {
  const dx = line.x2 - line.x1;
  const dz = line.z2 - line.z1;
  const lengthSq = dx * dx + dz * dz;
  const along = lengthSq > 0
    ? Math.max(0, Math.min(1, ((x - line.x1) * dx + (z - line.z1) * dz) / lengthSq))
    : 0;
  const px = line.x1 + along * dx;
  const pz = line.z1 + along * dz;
  return { x: px, z: pz, distance: Math.hypot(x - px, z - pz) };
}

export type Snapped = Point3 & {
  /** The line it snapped onto, or null when it is where it was put. */
  snappedTo: SnapLine | null;
};

/**
 * `point` moved onto the nearest line within reach, or left where it is.
 *
 * Only lines near the fixture's own height are tried, so a fixture on the
 * truss does not snap to the edge of the stage under it. On a truss or bar it
 * also takes the height a fixture hangs from it at; on the edge of a raised
 * area it keeps its own.
 */
export function snapToLines(
  point: Point3,
  lines: SnapLine[],
  radius = SNAP_RADIUS_M,
  heightWindow = SNAP_HEIGHT_WINDOW_M,
): Snapped {
  let best: { x: number; z: number; distance: number; line: SnapLine } | null = null;
  for (const line of lines) {
    if (Math.abs(point.y - line.height) > heightWindow) continue;
    const near = nearestOnSegment(point.x, point.z, line);
    if (near.distance > radius) continue;
    // A truss wins a tie with an edge: it is what a fixture hangs from.
    if (!best || near.distance < best.distance - 1e-9
      || (Math.abs(near.distance - best.distance) <= 1e-9 && line.kind === 'truss' && best.line.kind !== 'truss')) {
      best = { ...near, line };
    }
  }
  if (!best) return { ...point, snappedTo: null };
  return {
    x: best.x,
    y: best.line.kind === 'truss' ? best.line.height : point.y,
    z: best.z,
    snappedTo: best.line,
  };
}

// ---------------------------------------------------------------------------
// Limits
// ---------------------------------------------------------------------------

export type PositionLimits = { halfX: number; halfZ: number; top: number };

/**
 * How far out and how high a fixture may be put: the larger of the stage and
 * the scanned room, and a margin. Mirrors `position_limits` in
 * backend/app/api/endpoints/fixture_position.py, which has the last word.
 */
export function positionLimits(
  rig: Pick<Rig, 'stage_width' | 'stage_depth' | 'stage_height' | 'room_shell'>,
): PositionLimits {
  const room = rig.room_shell?.room;
  const size = (stage: number, scanned: number | undefined, fallback: number) => {
    const base = finite(stage) && stage > 0 ? stage : fallback;
    return finite(scanned) && scanned > 0 ? Math.max(base, scanned) : base;
  };
  return {
    halfX: size(rig.stage_width, room?.width, 10) / 2 + OUTSIDE_MARGIN_M,
    halfZ: size(rig.stage_depth, room?.depth, 8) / 2 + OUTSIDE_MARGIN_M,
    top: size(rig.stage_height, room?.height, 6) + OUTSIDE_MARGIN_M,
  };
}

export function clampPosition(point: Point3, limits: PositionLimits): Point3 {
  const hold = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
  return {
    x: hold(point.x, -limits.halfX, limits.halfX),
    y: hold(point.y, 0, limits.top),
    z: hold(point.z, -limits.halfZ, limits.halfZ),
  };
}

/**
 * Where a drag puts the fixture, as the rig stores it.
 *
 * `lift` is how far above its stored height the fixture is drawn (one patched
 * below its own feet is stood on the floor), so it comes off again here.
 * Snapping applies along the plan only: with the height being changed, the
 * fixture stays on the height it is dragged to.
 */
export function settleDrag(
  state: DragState,
  lift: number,
  limits: PositionLimits,
  lines: SnapLine[] | null,
): Snapped {
  const raw: Point3 = { x: state.x, y: state.y - lift, z: state.z };
  const snapped = lines && lines.length > 0 && state.mode !== 'height'
    ? snapToLines(raw, lines)
    : { ...raw, snappedTo: null };
  const held = clampPosition(snapped, limits);
  return { x: roundMm(held.x), y: roundMm(held.y), z: roundMm(held.z), snappedTo: snapped.snappedTo };
}

/** Whether two positions differ by enough to be a move and not a click. */
export function hasMoved(a: Point3, b: Point3): boolean {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) >= MOVED_FROM_M;
}

/**
 * Whether a drag has become a move worth saving.
 *
 * Two things must both be true. The pointer itself has carried the fixture
 * away from where it was drawn (`state` against `drawnStart`, both in the
 * scene's coordinates): without that a press with a pixel of wobble next to a
 * truss line would snap onto it, and a click would move and confirm a
 * fixture. And where it settled is not where it is stored, so a fixture
 * carried out and back saves nothing.
 */
export function isRealMove(state: DragState, drawnStart: Point3, settled: Point3, stored: Point3): boolean {
  return hasMoved(state, drawnStart) && hasMoved(settled, stored);
}

// ---------------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------------

/**
 * A key press as a move, or null for a key that moves nothing. Arrows move on
 * the plan in the rig's own axes (left and right across, up towards upstage),
 * Page Up and Page Down change the height. Shift takes a metre at a time.
 */
export function nudgePosition(
  position: Point3,
  key: string,
  big: boolean,
  limits: PositionLimits,
): Point3 | null {
  const step = big ? NUDGE_BIG_STEP_M : NUDGE_STEP_M;
  const moved = { ...position };
  switch (key) {
    case 'ArrowLeft': moved.x -= step; break;
    case 'ArrowRight': moved.x += step; break;
    case 'ArrowUp': moved.z -= step; break;
    case 'ArrowDown': moved.z += step; break;
    case 'PageUp': moved.y += step; break;
    case 'PageDown': moved.y -= step; break;
    default: return null;
  }
  const held = clampPosition(moved, limits);
  return { x: roundMm(held.x), y: roundMm(held.y), z: roundMm(held.z) };
}

// ---------------------------------------------------------------------------
// The rig, with one fixture moved
// ---------------------------------------------------------------------------

/** The rig with one fixture at a new position. The same rig when the fixture is not in it. */
export function withFixturePosition<R extends { fixtures: RigFixture[] }>(rig: R, fixtureId: number, to: Point3): R {
  if (!rig.fixtures.some((fixture) => fixture.id === fixtureId)) return rig;
  return {
    ...rig,
    fixtures: rig.fixtures.map((fixture) => (
      fixture.id === fixtureId
        ? { ...fixture, position_x: to.x, position_y: to.y, position_z: to.z }
        : fixture
    )),
  };
}

/**
 * The rig with one fixture as the server stored it after a drag: its position
 * (which the server may have held inside the room) and its tags, which no
 * longer say it is a guess. Everything else about the fixture, its profile
 * included, is kept as the view already has it.
 */
export function withSavedFixture<R extends { fixtures: RigFixture[] }>(
  rig: R,
  saved: Pick<RigFixture, 'id' | 'position_x' | 'position_y' | 'position_z' | 'tags'>,
): R {
  if (!rig.fixtures.some((fixture) => fixture.id === saved.id)) return rig;
  return {
    ...rig,
    fixtures: rig.fixtures.map((fixture) => (
      fixture.id === saved.id
        ? {
            ...fixture,
            position_x: saved.position_x,
            position_y: saved.position_y,
            position_z: saved.position_z,
            tags: saved.tags ?? fixture.tags,
          }
        : fixture
    )),
  };
}

/** "x -3.00, height 4.50, z 0.50 m", and what it snapped to. */
export function positionText(at: Point3, snappedTo?: SnapLine | null): string {
  const text = `x ${at.x.toFixed(2)}, height ${at.y.toFixed(2)}, z ${at.z.toFixed(2)} m`;
  return snappedTo ? `${text} - on ${snappedTo.name}` : text;
}
