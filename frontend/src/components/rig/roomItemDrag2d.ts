/**
 * Arranging the items of a scanned room on the 2D plan (Edit Room's "Arrange
 * room items on the plan"): which raised areas, truss lines and rings can be
 * picked up, where their handles sit, and what a drag of one, or an arrow
 * key, asks the server to change.
 *
 * Numbers and words only: no React and no drawing. Each item is known by the
 * list it is stored in and its place there (`shellItems`), never by its place
 * on the plan, which leaves out what cannot be drawn. The server makes the
 * change and has the last word on where an item may go
 * (PATCH /api/rigs/{id}/room-shell/{kind}/{index}); docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import {
  SHELL_LIMITS, lineHeading, positionText, shellItemKey, shellItemTitle, shellItems,
} from '../../utils/roomShellEdit';
import type { ShellItemChanges, ShellItemKind } from '../../utils/roomShellEdit';
import { boxHeading, foldHeading } from './previs/raisedArea';
import type { PlanPoint } from './roomPlan2d';
import { snapToRoomGrid } from './roomPlan2d';

/** What is drawn of an item while it is arranged: its footprint on the plan. */
export type ItemShape =
  /**
   * A raised area. `heading` is how far it is turned about its middle, in
   * degrees clockwise as the plan is drawn; left out for one that stands
   * square to the room. While its rotate handle is dragged it is not folded,
   * so that the handle stays on the pointer's side.
   */
  | { type: 'box'; centerX: number; centerZ: number; width: number; depth: number; heading?: number }
  | { type: 'line'; x1: number; z1: number; x2: number; z2: number }
  | { type: 'ring'; centerX: number; centerZ: number; radius: number };

/** One raised area, truss line or ring that can be picked up on the plan. */
export interface PlanItem {
  /** The list and the place in it: `shellItemKey`. */
  key: string;
  kind: ShellItemKind;
  /** Its place in the stored list, from 0: what the server knows it by. */
  index: number;
  /** Its name, or what it is. */
  title: string;
  shape: ItemShape;
}

/**
 * What a press on the plan has hold of: the item itself (a move), the end of
 * a line (its length), the stalk past its other end (its heading), the
 * side of a ring (its radius), a corner or an edge of a raised area (its
 * width, its front to back, or both), or the stalk past a raised area's
 * upstage edge (its heading, slice 21).
 */
export type ItemGrip = 'move' | 'length' | 'rotate' | 'radius' | BoxGrip;

/**
 * A corner or the middle of an edge of a raised area, by the compass of the
 * plan as it is drawn: `n` is the upstage edge (the top of the plan), `e`
 * the stage left one. On one at a heading they are its own sides, turned
 * with it: `n` is the side that was upstage before it was turned.
 */
export type BoxGrip = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

/** Which way each of a raised area's grips pulls: -1, 0 or 1 across the room and from upstage to downstage. */
const BOX_PULL: Record<BoxGrip, { x: -1 | 0 | 1; z: -1 | 0 | 1 }> = {
  nw: { x: -1, z: -1 },
  n: { x: 0, z: -1 },
  ne: { x: 1, z: -1 },
  e: { x: 1, z: 0 },
  se: { x: 1, z: 1 },
  s: { x: 0, z: 1 },
  sw: { x: -1, z: 1 },
  w: { x: -1, z: 0 },
};
const BOX_GRIPS = Object.keys(BOX_PULL) as BoxGrip[];

/** Whether a grip is one of a raised area's corners or edges. */
export function isBoxGrip(grip: ItemGrip): grip is BoxGrip {
  return grip in BOX_PULL;
}

/** How far past a line's first end its rotate handle stands, in metres. */
export const ROTATE_STALK_M = 0.6;
/** A heading goes to this many degrees while the snap is on. */
export const HEADING_SNAP_DEG = 5;
/** And to this many while Shift is held, whatever the snap is set to. */
export const HEADING_SHIFT_SNAP_DEG = 15;
/** No item's middle is sent further out than this: the server holds it to the room anyway. */
const REACH_M = 200;

const roundMm = (value: number) => Math.round(value * 1000) / 1000 + 0;
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

/**
 * The items of a scanned room that the plan draws and can therefore pick up,
 * in the order they are drawn: raised areas, then lines, then rings. One the
 * views cannot draw (a size or an end missing) is left to Edit Room's rows.
 */
export function planItems(shell: RoomShell | null | undefined): PlanItem[] {
  const items: PlanItem[] = [];
  for (const item of shellItems(shell)) {
    if (!item.drawn || !item.centre) continue;
    const base = { key: shellItemKey(item), kind: item.kind, index: item.index, title: shellItemTitle(item) };
    if (item.kind === 'risers') {
      const { width, depth } = item.sizes;
      if (!isNumber(width) || !isNumber(depth)) continue;
      const shape: ItemShape = { type: 'box', centerX: item.centre.x, centerZ: item.centre.z, width, depth };
      // One that stands square to the room says nothing of a heading, as before there was one.
      const heading = boxHeading(shell?.risers?.[item.index]);
      if (heading !== 0) shape.heading = heading;
      items.push({ ...base, shape });
    } else if (item.kind === 'truss_lines') {
      const line = shell?.truss_lines?.[item.index];
      if (!line) continue;
      items.push({ ...base, shape: { type: 'line', x1: line.x1, z1: line.z1, x2: line.x2, z2: line.z2 } });
    } else {
      const { radius } = item.sizes;
      if (!isNumber(radius)) continue;
      items.push({ ...base, shape: { type: 'ring', centerX: item.centre.x, centerZ: item.centre.z, radius } });
    }
  }
  return items;
}

/** The middle of a shape: a box's or a ring's own centre, and half way along a line. */
export function shapeCentre(shape: ItemShape): PlanPoint {
  if (shape.type === 'line') return { x: (shape.x1 + shape.x2) / 2, z: (shape.z1 + shape.z2) / 2 };
  return { x: shape.centerX, z: shape.centerZ };
}

/** A line's length and the way it runs from its first end to its second, as a unit step. */
function lineRun(shape: Extract<ItemShape, { type: 'line' }>) {
  const length = Math.hypot(shape.x2 - shape.x1, shape.z2 - shape.z1);
  return { length, ux: length > 0 ? (shape.x2 - shape.x1) / length : 1, uz: length > 0 ? (shape.z2 - shape.z1) / length : 0 };
}

/** A line of this length through `centre`, running `degrees` clockwise from across the room. */
function lineThrough(centre: PlanPoint, length: number, degrees: number): Extract<ItemShape, { type: 'line' }> {
  const turn = (degrees * Math.PI) / 180;
  const hx = (Math.cos(turn) * length) / 2;
  const hz = (Math.sin(turn) * length) / 2;
  return { type: 'line', x1: centre.x - hx, z1: centre.z - hz, x2: centre.x + hx, z2: centre.z + hz };
}

type BoxShape = Extract<ItemShape, { type: 'box' }>;

/**
 * The way a raised area's width runs and the way its front to back runs, as
 * unit steps on the plan: across the room and downstage for one that stands
 * square, and turned with it for one at a heading.
 */
function boxAxes(shape: BoxShape): { ux: number; uz: number; vx: number; vz: number } {
  const heading = shape.heading ?? 0;
  if (heading === 0) return { ux: 1, uz: 0, vx: 0, vz: 1 };
  const turn = (heading * Math.PI) / 180;
  return { ux: Math.cos(turn), uz: Math.sin(turn), vx: -Math.sin(turn), vz: Math.cos(turn) };
}

/** A place of a raised area's own, along its width and along its front to back from its middle, on the plan. */
function boxPlace(shape: BoxShape, across: number, back: number): PlanPoint {
  if (!shape.heading) return { x: shape.centerX + across, z: shape.centerZ + back };
  const { ux, uz, vx, vz } = boxAxes(shape);
  return { x: shape.centerX + across * ux + back * vx, z: shape.centerZ + across * uz + back * vz };
}

/** The handles a selected item has besides itself, and where each stands. */
export function itemHandles(shape: ItemShape): Array<{ grip: Exclude<ItemGrip, 'move'>; x: number; z: number }> {
  if (shape.type === 'line') {
    const { ux, uz } = lineRun(shape);
    return [
      { grip: 'length', x: shape.x2, z: shape.z2 },
      { grip: 'rotate', x: shape.x1 - ux * ROTATE_STALK_M, z: shape.z1 - uz * ROTATE_STALK_M },
    ];
  }
  // On the stage left side of the ring.
  if (shape.type === 'ring') return [{ grip: 'radius', x: shape.centerX + shape.radius, z: shape.centerZ }];
  // A raised area: its four corners and the middle of each edge, where they stand at its heading,
  // and a rotate handle on a stalk past the middle of the edge that is upstage when it stands square.
  const grips: Array<{ grip: Exclude<ItemGrip, 'move'>; x: number; z: number }> = BOX_GRIPS.map((grip) => ({
    grip,
    ...boxPlace(shape, (BOX_PULL[grip].x * shape.width) / 2, (BOX_PULL[grip].z * shape.depth) / 2),
  }));
  grips.push({ grip: 'rotate', ...boxPlace(shape, 0, -(shape.depth / 2 + ROTATE_STALK_M)) });
  return grips;
}

/** What a drag has an item at: the shape to draw, what to send for it, and the words over it. */
export interface ItemDrag {
  shape: ItemShape;
  /** What to send, or null when the drag has it where and as it already is. */
  changes: ShellItemChanges | null;
  readout: string;
}

/** How a drag snaps: the grid's step, or none of it (snap mode None, or Alt held). */
export interface ItemSnap {
  on: boolean;
  gridSize: number;
  /**
   * Shift is held: a rotate handle turns in steps of 15 degrees, with the
   * snap on or off. Nothing else reads it.
   */
  coarse?: boolean;
}

/** A heading under a rotate handle, to the step the drag snaps to: 15 degrees with Shift, 5 with the snap on. */
function toHeadingStep(degrees: number, snap: ItemSnap): number {
  const step = snap.coarse ? HEADING_SHIFT_SNAP_DEG : snap.on ? HEADING_SNAP_DEG : 0;
  return step > 0 ? Math.round(degrees / step) * step : degrees;
}

const toStep = (value: number, snap: ItemSnap) =>
  (snap.on && snap.gridSize > 0 ? Math.round(value / snap.gridSize) * snap.gridSize : value);

/**
 * Where a drag of one grip has its item, with the pointer (the grip's offset
 * from it already taken off) at `at`.
 *
 * - **move**: the middle goes to `at`, on the grid when the snap is on. Only
 *   the middle is sent: a line keeps its length and heading.
 * - **length**: a line is made longer or shorter about its middle, along the
 *   way it runs: twice how far along it the pointer is from the middle, to
 *   the grid's step, and never under the least a line can be.
 * - **rotate**: a line is turned about its middle to point at the pointer,
 *   to 5 degrees with the snap on and to a tenth without, and to 15 with
 *   Shift held either way; a line has no front, so the heading is folded as
 *   the server stores it.
 * - **radius**: a ring's radius is how far the pointer is from its middle,
 *   to the grid's step, and never under the least a ring can be.
 * - **a corner or an edge of a raised area**: its width, its front to back
 *   or both, about its middle, which stays where it is: twice how far the
 *   pointer is from the middle along each axis the grip pulls, to the grid's
 *   step, and never under the least a side can be. An edge changes one of
 *   the two and a corner both; only what changed is sent. On one at a
 *   heading the two axes are its own, turned with it.
 * - **rotate** on a raised area: it is turned about its middle so that the
 *   handle, which stands past its upstage edge, points at the pointer, to 5
 *   degrees with the snap on and to a tenth without, and to 15 with Shift
 *   held either way; the heading is folded as the server stores it (a
 *   rectangle looks the same after half a turn).
 *
 * A grip that is not this shape's changes nothing.
 */
export function dragItem(item: PlanItem, grip: ItemGrip, at: PlanPoint, snap: ItemSnap): ItemDrag {
  const { shape } = item;
  const centre = shapeCentre(shape);
  const same: ItemDrag = { shape, changes: null, readout: '' };

  if (grip === 'move') {
    const snapped = snap.on ? snapToRoomGrid(at.x, at.z, snap.gridSize) : at;
    const held = (value: number) => roundMm(Math.min(Math.max(value, -REACH_M), REACH_M));
    const to = { x: held(snapped.x), z: held(snapped.z) };
    const dx = to.x - centre.x;
    const dz = to.z - centre.z;
    const moved = Math.abs(dx) >= 0.0005 || Math.abs(dz) >= 0.0005;
    const next: ItemShape = shape.type === 'line'
      ? { type: 'line', x1: shape.x1 + dx, z1: shape.z1 + dz, x2: shape.x2 + dx, z2: shape.z2 + dz }
      : { ...shape, centerX: to.x, centerZ: to.z };
    return {
      shape: moved ? next : shape,
      changes: moved ? { center_x: to.x, center_z: to.z } : null,
      readout: `${to.x.toFixed(2)}, ${to.z.toFixed(2)}`,
    };
  }

  if (shape.type === 'line' && grip === 'length') {
    const { length, ux, uz } = lineRun(shape);
    const along = Math.abs((at.x - centre.x) * ux + (at.z - centre.z) * uz);
    const next = roundMm(Math.max(SHELL_LIMITS.line, toStep(along * 2, snap)));
    const changed = Math.abs(next - length) >= 0.0005;
    return {
      shape: changed
        ? {
            type: 'line',
            x1: centre.x - (ux * next) / 2, z1: centre.z - (uz * next) / 2,
            x2: centre.x + (ux * next) / 2, z2: centre.z + (uz * next) / 2,
          }
        : shape,
      changes: changed ? { length: next } : null,
      readout: `${next.toFixed(2)} m long`,
    };
  }

  if (shape.type === 'line' && grip === 'rotate') {
    const { length } = lineRun(shape);
    const dx = at.x - centre.x;
    const dz = at.z - centre.z;
    // On the middle itself the pointer says nothing about a heading.
    if (Math.hypot(dx, dz) < 1e-6) return same;
    const stored = lineHeading(shape) ?? 0;
    const degrees = toHeadingStep((Math.atan2(dz, dx) * 180) / Math.PI, snap);
    // Folded as the server stores a heading: over -90 and up to 90, to a tenth.
    const heading = lineHeading(lineThrough({ x: 0, z: 0 }, 1, degrees)) ?? stored;
    const changed = Math.abs(heading - stored) >= 0.05;
    return {
      // Drawn with its first end, which the handle stands past, on the
      // pointer's side: the folded heading alone would put the handle on the
      // far end once the pointer is stage left of the middle.
      shape: changed ? lineThrough(centre, length, degrees + 180) : shape,
      changes: changed ? { heading_deg: heading } : null,
      readout: `${positionText(heading)} deg`,
    };
  }

  if (shape.type === 'ring' && grip === 'radius') {
    const out = Math.hypot(at.x - centre.x, at.z - centre.z);
    const next = roundMm(Math.max(SHELL_LIMITS.radius, toStep(out, snap)));
    const changed = Math.abs(next - shape.radius) >= 0.0005;
    return {
      shape: changed ? { ...shape, radius: next } : shape,
      changes: changed ? { radius: next } : null,
      readout: `radius ${next.toFixed(2)} m`,
    };
  }

  if (shape.type === 'box' && grip === 'rotate') {
    const dx = at.x - centre.x;
    const dz = at.z - centre.z;
    // On the middle itself the pointer says nothing about a heading.
    if (Math.hypot(dx, dz) < 1e-6) return same;
    const stored = foldHeading(shape.heading ?? 0) ?? 0;
    // The handle stands straight upstage of the middle of one that is square to the room, which is
    // a quarter turn back from the way its width runs: the heading is the pointer's bearing and 90.
    const degrees = toHeadingStep((Math.atan2(dz, dx) * 180) / Math.PI + 90, snap);
    // Folded as the server stores a raised area's heading: over -90 and up to 90, to a tenth.
    const heading = foldHeading(degrees) ?? stored;
    const changed = Math.abs(heading - stored) >= 0.05;
    return {
      // Drawn at the turn the pointer has it, not folded: folded, the handle would jump to the far
      // side of the area once the pointer is downstage of its middle.
      shape: changed ? { ...shape, heading: degrees } : shape,
      changes: changed ? { heading_deg: heading } : null,
      readout: `${positionText(heading)} deg`,
    };
  }

  if (shape.type === 'box' && isBoxGrip(grip)) {
    const pull = BOX_PULL[grip];
    const side = (pulled: number, stored: number, out: number) =>
      (pulled === 0 ? stored : roundMm(Math.max(SHELL_LIMITS.side, toStep(Math.abs(out) * 2, snap))));
    // How far the pointer is from the middle along the area's own width and its own front to
    // back, which are the room's only for one that stands square to it.
    const { ux, uz, vx, vz } = boxAxes(shape);
    const out = { x: at.x - centre.x, z: at.z - centre.z };
    const width = side(pull.x, shape.width, shape.heading ? out.x * ux + out.z * uz : out.x);
    const depth = side(pull.z, shape.depth, shape.heading ? out.x * vx + out.z * vz : out.z);
    const changes: ShellItemChanges = {};
    if (Math.abs(width - shape.width) >= 0.0005) changes.width = width;
    if (Math.abs(depth - shape.depth) >= 0.0005) changes.depth = depth;
    const changed = Object.keys(changes).length > 0;
    return {
      shape: changed ? { ...shape, width, depth } : shape,
      changes: changed ? changes : null,
      readout: `${width.toFixed(2)} by ${depth.toFixed(2)} m`,
    };
  }

  return same;
}

/**
 * What an arrow key asks for: the item's middle shifted by `dx` and `dz`.
 * Only the axis that moves is sent. Null for a shift that is no move.
 */
export function nudgeItem(item: PlanItem, dx: number, dz: number): ShellItemChanges | null {
  const centre = shapeCentre(item.shape);
  const changes: ShellItemChanges = {};
  if (Math.abs(dx) >= 0.0005) changes.center_x = roundMm(centre.x + dx);
  if (Math.abs(dz) >= 0.0005) changes.center_z = roundMm(centre.z + dz);
  return Object.keys(changes).length > 0 ? changes : null;
}

/**
 * The pointer over a handle: a turn for a rotate handle, and for a corner or
 * an edge of a raised area the way it pulls. `heading` is the raised area's:
 * turned, its stage left edge no longer pulls across the room, and the arrow
 * that is nearest the way it does pull is shown (each stands for 45 degrees).
 */
export function gripCursor(grip: ItemGrip, heading = 0): string {
  if (grip === 'rotate') return 'alias';
  if (!isBoxGrip(grip)) return 'pointer';
  const pull = BOX_PULL[grip];
  // The way the grip pulls on the plan as it is drawn, clockwise from stage left, in eighths of a turn.
  const bearing = (Math.atan2(pull.z, pull.x) * 180) / Math.PI + (Number.isFinite(heading) ? heading : 0);
  const eighth = ((Math.round(bearing / 45) % 4) + 4) % 4;
  return ['ew-resize', 'nwse-resize', 'ns-resize', 'nesw-resize'][eighth];
}

/** What a grip is for, for its tooltip. */
export function gripHint(grip: ItemGrip, title: string): string {
  switch (grip) {
    case 'length': return `${title}: drag this end to make it longer or shorter about its middle`;
    case 'rotate': return `${title}: drag to turn it about its middle (hold Shift for steps of 15 degrees)`;
    case 'radius': return `${title}: drag to change its radius`;
    case 'e':
    case 'w': return `${title}: drag this edge to make it wider or narrower about its middle`;
    case 'n':
    case 's': return `${title}: drag this edge to change its front to back about its middle`;
    case 'nw':
    case 'ne':
    case 'se':
    case 'sw': return `${title}: drag this corner to change its width and its front to back about its middle`;
    default: return `${title}: drag to move it, or press an arrow key`;
  }
}
