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
import type { PlanPoint } from './roomPlan2d';
import { snapToRoomGrid } from './roomPlan2d';

/** What is drawn of an item while it is arranged: its footprint on the plan. */
export type ItemShape =
  | { type: 'box'; centerX: number; centerZ: number; width: number; depth: number }
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
 * a line (its length), the stalk past its other end (its heading), or the
 * side of a ring (its radius).
 */
export type ItemGrip = 'move' | 'length' | 'rotate' | 'radius';

/** How far past a line's first end its rotate handle stands, in metres. */
export const ROTATE_STALK_M = 0.6;
/** A heading goes to this many degrees while the snap is on. */
export const HEADING_SNAP_DEG = 5;
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
      items.push({ ...base, shape: { type: 'box', centerX: item.centre.x, centerZ: item.centre.z, width, depth } });
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
  return [];
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
 *   to 5 degrees with the snap on and to a tenth without; a line has no
 *   front, so the heading is folded as the server stores it.
 * - **radius**: a ring's radius is how far the pointer is from its middle,
 *   to the grid's step, and never under the least a ring can be.
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
    let degrees = (Math.atan2(dz, dx) * 180) / Math.PI;
    if (snap.on) degrees = Math.round(degrees / HEADING_SNAP_DEG) * HEADING_SNAP_DEG;
    // Folded as the server stores a heading: over -90 and up to 90, to a tenth.
    const heading = lineHeading(lineThrough({ x: 0, z: 0 }, 1, degrees)) ?? stored;
    const changed = Math.abs(heading - stored) >= 0.05;
    return {
      shape: changed ? lineThrough(centre, length, heading) : shape,
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

/** What a grip is for, for its tooltip. */
export function gripHint(grip: ItemGrip, title: string): string {
  switch (grip) {
    case 'length': return `${title}: drag this end to make it longer or shorter about its middle`;
    case 'rotate': return `${title}: drag to turn it about its middle`;
    case 'radius': return `${title}: drag to change its radius`;
    default: return `${title}: drag to move it, or press an arrow key`;
  }
}
