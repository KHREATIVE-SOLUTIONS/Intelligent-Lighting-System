/**
 * Correcting a suggested layout on the 2D plan quickly and safely: when a
 * press becomes a drag, which fixtures a selection box takes in, how far an
 * arrow key carries the selection, and when a key belongs to something else
 * on the page.
 *
 * Numbers and words only: no React and no drawing. docs/ROOM_SCAN.md.
 */
import { roundMm } from './previs/fixtureDrag';
import type { PlanPoint, PlanWalls } from './roomPlan2d';
import { holdRowShift } from './rowMove2d';
import type { PlanMove, RowShift } from './rowMove2d';

// ---------------------------------------------------------------------------
// When a press becomes a drag
// ---------------------------------------------------------------------------

/** A press becomes a drag once the pointer is this many screen pixels from where it went down. */
export const DRAG_THRESHOLD_PX = 5;

/** A place on the screen, in pixels, as a pointer event gives it. */
export type ScreenPoint = { clientX: number; clientY: number };

/**
 * Whether the pointer has gone far enough from where it was pressed for the
 * press to be a drag: `threshold` pixels or more, in any direction. Under
 * that it is a click, or the wobble of one, and moves nothing.
 */
export function pastDragThreshold(
  down: ScreenPoint, now: ScreenPoint, threshold: number = DRAG_THRESHOLD_PX,
): boolean {
  return Math.hypot(now.clientX - down.clientX, now.clientY - down.clientY) >= threshold;
}

// ---------------------------------------------------------------------------
// A selection box
// ---------------------------------------------------------------------------

/** A box on the plan with its corners in order, whichever way it was dragged. */
export type PlanBox = { minX: number; maxX: number; minZ: number; maxZ: number };

/** The box between two corners, given in any order. */
export function boxBetween(a: PlanPoint, b: PlanPoint): PlanBox {
  return {
    minX: Math.min(a.x, b.x) + 0,
    maxX: Math.max(a.x, b.x) + 0,
    minZ: Math.min(a.z, b.z) + 0,
    maxZ: Math.max(a.z, b.z) + 0,
  };
}

type Placed = { id: number; position_x: number; position_z: number };

/**
 * The fixtures whose marker centre is inside the box dragged from `a` to `b`,
 * in the order they were given. The corners may come in any order, so a box
 * dragged up and to the left takes in what one dragged down and to the right
 * does. A centre on the box's edge is inside it.
 */
export function fixturesInBox(fixtures: Placed[], a: PlanPoint, b: PlanPoint): number[] {
  const box = boxBetween(a, b);
  return fixtures
    .filter((f) => (
      f.position_x >= box.minX && f.position_x <= box.maxX
      && f.position_z >= box.minZ && f.position_z <= box.maxZ
    ))
    .map((f) => f.id);
}

/**
 * What a finished box selects: the fixtures in it, or with Shift, Ctrl or
 * Cmd held those added to what was selected already. Nothing is ever taken
 * out of the selection by an additive box.
 */
export function boxSelection(current: Iterable<number>, boxed: number[], additive: boolean): number[] {
  if (!additive) return boxed;
  return [...new Set([...current, ...boxed])];
}

// ---------------------------------------------------------------------------
// Arrow keys
// ---------------------------------------------------------------------------

/** With Shift held an arrow key goes this many grid steps. */
export const NUDGE_SHIFT_STEPS = 10;

/**
 * The shift on the plan an arrow key asks for: one grid step, ten with
 * Shift. Left and right are stage right and stage left as the plan draws
 * them; up is upstage (-Z), at the top of the plan. Null for any other key.
 */
export function nudgeShift(key: string, gridSize: number, shiftKey = false): RowShift | null {
  const step = gridSize * (shiftKey ? NUDGE_SHIFT_STEPS : 1);
  if (!(step > 0)) return null;
  switch (key) {
    case 'ArrowLeft': return { dx: -step, dz: 0 };
    case 'ArrowRight': return { dx: step, dz: 0 };
    case 'ArrowUp': return { dx: 0, dz: -step };
    case 'ArrowDown': return { dx: 0, dz: step };
    default: return null;
  }
}

/** A shift shorter than this is no move at all. */
const NO_MOVE_M = 1e-6;

/**
 * Where the fixtures `ids` go when nudged by `shift`: every one by the same
 * shift, cut short where any of them would leave the room, exactly as a row
 * drag is (`holdRowShift`): the walls a scanned room draws, or with none the
 * stage deck. Spacing is never changed.
 *
 * Positions are to the millimetre, as they are stored. No height is given: a
 * nudge never changes one. Empty when nothing is selected or the selection
 * is already against the wall it is pushed at; a fixture already outside the
 * walls is not held until a nudge has brought it inside, as in a row drag.
 */
export function nudgeMoves(
  fixtures: Placed[], ids: Iterable<number>, shift: RowShift,
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
): PlanMove[] {
  const wanted = new Set(ids);
  const picked = fixtures.filter((f) => wanted.has(f.id));
  if (picked.length === 0) return [];
  const held = holdRowShift(
    walls, stageWidth, stageDepth,
    picked.map((f) => ({ x: f.position_x, z: f.position_z })),
    { dx: 0, dz: 0 }, shift,
  );
  if (Math.hypot(held.dx, held.dz) <= NO_MOVE_M) return [];
  // `+ 0` so a position brought back to a line through the origin is 0, not -0.
  return picked.map((f) => ({
    id: f.id, x: roundMm(f.position_x + held.dx) + 0, z: roundMm(f.position_z + held.dz) + 0,
  }));
}

// ---------------------------------------------------------------------------
// Whose key it is
// ---------------------------------------------------------------------------

/**
 * Somewhere a key is typed into, or already means something: a text field, a
 * drop-down (the browser's own or one drawn as a combobox, list or menu,
 * where arrows choose), and anything in a dialog, which is in front of the
 * plan.
 */
const KEYS_TAKEN_BY = [
  'input', 'textarea', 'select',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="textbox"]', '[role="combobox"]', '[role="listbox"]', '[role="menu"]', '[role="dialog"]',
].join(', ');

/**
 * Whether a key pressed with the focus on `target` is not the plan's to act
 * on: it is being typed into a field, or is in a drop-down or a dialog.
 * False for anything that is not an element (no focus, or the page itself).
 */
export function keysBelongElsewhere(target: unknown): boolean {
  if (typeof Element === 'undefined' || !(target instanceof Element)) return false;
  return target.closest(KEYS_TAKEN_BY) !== null;
}
