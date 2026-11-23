/**
 * Correcting a suggested layout on the 2D plan a row at a time: which fixtures
 * are one row, how far a row may be carried before one of them would leave
 * the room, what a snap onto scanned truss says and which of a row take its
 * height, and positions put on and taken back off a rig's fixtures.
 *
 * Numbers and words only: no React and no drawing. docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import type { FixturePositionSnapshot } from '../../stores/rigEditorStore';
import { nearestOnTarget } from './previs/fixtureDrag';
import type { SnapLine } from './previs/fixtureDrag';
import { HANGER_HEIGHT_WINDOW, HANGER_REACH } from './previs/layout';
import { holdOnPlan, planTrussTargets } from './roomPlan2d';
import type { PlanPoint, PlanWalls } from './roomPlan2d';

// ---------------------------------------------------------------------------
// What a snap onto scanned truss says
// ---------------------------------------------------------------------------

/** A position this near a truss line or ring on the plan is on it. */
export const ON_TRUSS_M = 0.05;

/** Whether a position on the plan is on a scanned truss line or ring. */
export function onPlanTarget(target: SnapLine, x: number, z: number): boolean {
  const near = nearestOnTarget(x, z, target);
  return !!near && near.distance <= ON_TRUSS_M;
}

/** "Truss 1", or "Overhead A (ring)" for a ring whose name does not say it is one. */
function targetWords(target: SnapLine): string {
  return target.ring && !/ring/i.test(target.name) ? `${target.name} (ring)` : target.name;
}

/** "On Truss 1 · hangs at 4.20 m": what a dragged or dropped fixture snapped to. */
export function snapReadoutText(target: SnapLine): string {
  return `On ${targetWords(target)} · hangs at ${target.height.toFixed(2)} m`;
}

/**
 * The same for a row carried together: "Row of 4 on Truss 1 · hangs at
 * 4.20 m" when every one of them is on it, "2 of 4 on Truss 1 · ..." when
 * only some are (a row longer than the truss, or not lying along it).
 */
export function rowReadoutText(target: SnapLine, on: number, total: number): string {
  if (total <= 1) return snapReadoutText(target);
  const count = on >= total ? `Row of ${total}` : `${on} of ${total}`;
  return `${count} on ${targetWords(target)} · hangs at ${target.height.toFixed(2)} m`;
}

// ---------------------------------------------------------------------------
// Which fixtures are one row
// ---------------------------------------------------------------------------

export interface RowFixture {
  id: number;
  position_x: number;
  position_y: number;
  position_z: number;
  group_name?: string | null;
}

const groupOf = (fixture: RowFixture) => (fixture.group_name ?? '').trim();

/** One height and depth, to the 0.1 m a room scan's suggestion goes by. */
const levelKey = (fixture: RowFixture) =>
  `${Math.round(fixture.position_y * 10)} ${Math.round(fixture.position_z * 10)}`;

/** Whether a fixture hangs from a scanned truss line or ring, by the 3D view's own reach. */
function hangsOn(target: SnapLine, fixture: RowFixture): boolean {
  if (Math.abs(fixture.position_y - target.height) > HANGER_HEIGHT_WINDOW) return false;
  const near = nearestOnTarget(fixture.position_x, fixture.position_z, target);
  return !!near && near.distance <= HANGER_REACH;
}

/**
 * The fixtures in the same row as fixture `id`, itself included, in the
 * order they were given. A row is what a room scan's suggestion moves as one
 * piece (`suggest.py`), read in the same order:
 *
 * - every fixture of its **group**, when it has one;
 * - else the ungrouped fixtures hanging from the **same scanned truss line
 *   or ring** (the first it hangs from), which is how a row laid along an
 *   angled truss or round a ring is found again;
 * - else the ungrouped fixtures at the **same height and depth**, to 0.1 m.
 *
 * Empty for an id that is not in the rig.
 */
export function rowOf(fixtures: RowFixture[], id: number, shell: RoomShell | null | undefined): number[] {
  const picked = fixtures.find((fixture) => fixture.id === id);
  if (!picked) return [];
  const group = groupOf(picked);
  if (group) return fixtures.filter((fixture) => groupOf(fixture) === group).map((fixture) => fixture.id);

  const loose = fixtures.filter((fixture) => !groupOf(fixture));
  const truss = planTrussTargets(shell).find((target) => hangsOn(target, picked));
  if (truss) return loose.filter((fixture) => hangsOn(truss, fixture)).map((fixture) => fixture.id);

  const level = levelKey(picked);
  return loose.filter((fixture) => levelKey(fixture) === level).map((fixture) => fixture.id);
}

// ---------------------------------------------------------------------------
// How far a row may be carried
// ---------------------------------------------------------------------------

/** One shift on the plan, the same for every fixture of a row. */
export type RowShift = { dx: number; dz: number };

/** A position this near the walls counts as inside them: resting on a wall is in the room. */
const INSIDE_WITHIN_M = 1e-6;
const HOLD_PASSES = 8;

/**
 * The shift nearest `to` that a row may take, as one piece, without any of
 * its fixtures leaving the room: the walls a scanned room draws (its floor
 * outline, or its box), or with no room the stage deck. Spacing is never
 * changed: every fixture gets the same shift or none does.
 *
 * `starts` is where each fixture stood when the row was picked up and `from`
 * the shift it has now, which is where the row stays if no shift towards
 * `to` fits (a row wider than the room is across).
 *
 * A fixture that is already outside the walls at `from` is not held: it
 * comes along with the row and is held from the moment the row brings it
 * inside. Holding it at once would mean breaking the row's spacing or
 * refusing to move a row that somebody is trying to bring in.
 */
export function holdRowShift(
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
  starts: PlanPoint[], from: RowShift, to: RowShift,
): RowShift {
  // How far a position is from where it would be held to.
  const back = (x: number, z: number) => {
    const held = holdOnPlan(x, z, stageWidth, stageDepth, walls);
    return { dx: held.x - x, dz: held.z - z };
  };
  const outside = (c: RowShift) => Math.hypot(c.dx, c.dz) > INSIDE_WITHIN_M;
  const held = starts.filter((p) => !outside(back(p.x + from.dx, p.z + from.dz)));

  let { dx, dz } = to;
  for (let pass = 0; pass <= HOLD_PASSES; pass += 1) {
    let pulled = false;
    for (const p of held) {
      const c = back(p.x + dx, p.z + dz);
      if (!outside(c)) continue;
      // Past the last pass this is only the check that the row fits.
      if (pass === HOLD_PASSES) return from;
      dx += c.dx;
      dz += c.dz;
      pulled = true;
    }
    if (!pulled) return { dx: dx + 0, dz: dz + 0 };
  }
  return from;
}

// ---------------------------------------------------------------------------
// Positions put on a rig's fixtures, and taken back off
// ---------------------------------------------------------------------------

/** Where one fixture goes on the plan. `y` is given only when its height changes too. */
export type PlanMove = { id: number; x: number; z: number; y?: number };

type Positioned = { id: number; position_x: number; position_y: number; position_z: number };

/**
 * Fixtures with `moves` applied, and the ids of those that changed: what to
 * save. A move to where a fixture already is changes nothing, so a press
 * that goes nowhere leaves nothing to save or undo.
 */
export function withMoves<F extends Positioned>(fixtures: F[], moves: PlanMove[]): { fixtures: F[]; changed: number[] } {
  const byId = new Map(moves.map((move) => [move.id, move]));
  const changed: number[] = [];
  const next = fixtures.map((fixture) => {
    const move = byId.get(fixture.id);
    if (!move) return fixture;
    const y = move.y ?? fixture.position_y;
    if (move.x === fixture.position_x && move.z === fixture.position_z && y === fixture.position_y) return fixture;
    changed.push(fixture.id);
    return { ...fixture, position_x: move.x, position_y: y, position_z: move.z };
  });
  return { fixtures: next, changed };
}

/**
 * Every fixture's place on the plan, to step back to. A height is kept only
 * for the fixtures in `withHeights`: those whose height the drag being
 * undone changed, by a snap onto scanned truss. Every other fixture's height
 * is none of an undo's business (it may have been set in the properties
 * panel since), which is how it has always been.
 */
export function snapshotPositions(fixtures: Positioned[], withHeights?: Iterable<number>): FixturePositionSnapshot[] {
  const heights = new Set(withHeights ?? []);
  return fixtures.map((f) => (
    heights.has(f.id)
      ? { id: f.id, position_x: f.position_x, position_y: f.position_y, position_z: f.position_z }
      : { id: f.id, position_x: f.position_x, position_z: f.position_z }
  ));
}

/** The fixtures a snapshot keeps a height for. */
export function heightIdsOf(snapshot: FixturePositionSnapshot[] | undefined): number[] {
  return (snapshot ?? []).filter((entry) => entry.position_y !== undefined).map((entry) => entry.id);
}

/**
 * The heights a set of moves is about to change, as they are now: what an
 * undo of those moves has to put back. Empty for moves that give no height
 * or give the one a fixture already has.
 */
export function heightsBefore(fixtures: Positioned[], moves: PlanMove[]): Array<{ id: number; position_y: number }> {
  const byId = new Map(fixtures.map((fixture) => [fixture.id, fixture]));
  const before: Array<{ id: number; position_y: number }> = [];
  for (const move of moves) {
    const fixture = byId.get(move.id);
    if (!fixture || move.y === undefined || move.y === fixture.position_y) continue;
    before.push({ id: fixture.id, position_y: fixture.position_y });
  }
  return before;
}

/**
 * Fixtures put back where a snapshot has them, and the ids of those that
 * changed. A fixture the snapshot keeps no height for keeps the height it
 * has.
 */
export function withSnapshot<F extends Positioned>(
  fixtures: F[], snapshot: FixturePositionSnapshot[],
): { fixtures: F[]; changed: number[] } {
  return withMoves(fixtures, snapshot.map((s) => ({ id: s.id, x: s.position_x, z: s.position_z, y: s.position_y })));
}
