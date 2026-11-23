/**
 * Correcting a suggested layout on the 2D plan a row at a time: which fixtures
 * are one row, how far a row may be carried before one of them would leave
 * the room, what a snap onto scanned truss says and which of a row take its
 * height, a row laid out evenly along scanned truss, and positions put on
 * and taken back off a rig's fixtures.
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

// ---------------------------------------------------------------------------
// A row laid along scanned truss
// ---------------------------------------------------------------------------

/** A fixture with the DMX address a row is counted along a truss by. */
export type AddressedFixture = Positioned & { universe?: number | null; dmx_address?: number | null };

/** Fixtures closer than this along a line or round a ring are worth a word, as in `suggest.py`. */
export const CROWDED_UNDER_M = 0.3;

/** Universe, then address, then id: the order a room scan's suggestion counts a row in. */
export function addressOrder<F extends AddressedFixture>(row: F[]): F[] {
  return [...row].sort((a, b) => (
    (a.universe ?? 0) - (b.universe ?? 0) || (a.dmx_address ?? 0) - (b.dmx_address ?? 0) || a.id - b.id
  ));
}

/**
 * The scanned truss line or ring a row belongs on: the nearest to the middle
 * of the row on the plan, the first listed where two are as near. A row
 * drawn straight through a ring's middle belongs on the ring as much as one
 * under its arc, so a ring is as near as its centre or its circle, whichever
 * is nearer (`_nearest_shape` in `suggest.py`). Height is not asked about:
 * any truss on the plan is in reach, as for a 2D drag. Null with no truss or
 * no row.
 */
export function nearestTruss(targets: SnapLine[], row: PlanPoint[]): SnapLine | null {
  if (row.length === 0) return null;
  const x = row.reduce((sum, p) => sum + p.x, 0) / row.length;
  const z = row.reduce((sum, p) => sum + p.z, 0) / row.length;
  let best: SnapLine | null = null;
  let nearest = Infinity;
  for (const target of targets) {
    let off: number;
    if (target.ring) {
      const middle = Math.hypot(x - target.ring.centerX, z - target.ring.centerZ);
      off = Math.min(middle, Math.abs(middle - target.ring.radius));
    } else {
      off = nearestOnTarget(x, z, target)?.distance ?? Infinity;
    }
    if (off < nearest - 1e-9) {
      best = target;
      nearest = off;
    }
  }
  return best;
}

/**
 * Where each fixture of a row goes on a truss line or ring: evenly spaced,
 * in the order given, by the rule a room scan's suggestion lays a row out by
 * (`_spots_on` in `suggest.py`), so the two agree.
 *
 * Along a line the row is spread over its whole length with half a space at
 * each end, and keeps the sense it had: if the first of the row was nearer
 * the line's second end than the last was, it still is. Round a ring the
 * first is upstage and the rest follow clockwise seen from above.
 */
export function spotsOn(target: SnapLine, row: PlanPoint[]): PlanPoint[] {
  const count = row.length;
  if (target.ring) {
    const { centerX, centerZ, radius } = target.ring;
    return row.map((_, k) => ({
      x: centerX + radius * Math.sin((2 * Math.PI * k) / count) + 0,
      z: centerZ - radius * Math.cos((2 * Math.PI * k) / count) + 0,
    }));
  }
  const runX = target.x2 - target.x1;
  const runZ = target.z2 - target.z1;
  const along = row.map((p) => (p.x - target.x1) * runX + (p.z - target.z1) * runZ);
  const middle = (count - 1) / 2;
  const meanAlong = along.reduce((sum, a) => sum + a, 0) / count;
  const backwards = along.reduce((sum, a, k) => sum + (k - middle) * (a - meanAlong), 0) < -1e-9;
  return row.map((_, k) => {
    const share = backwards ? 1 - (k + 0.5) / count : (k + 0.5) / count;
    return { x: target.x1 + runX * share + 0, z: target.z1 + runZ * share + 0 };
  });
}

/** How far apart a row of `count` hangs on a truss line, or round a ring (along its circle). */
export function spacingOn(target: SnapLine, count: number): number {
  const length = target.ring
    ? 2 * Math.PI * target.ring.radius
    : Math.hypot(target.x2 - target.x1, target.z2 - target.z1);
  return count > 0 ? length / count : 0;
}

/** What laying a row along scanned truss comes to: the moves to make, or why none are made. */
export type RowLay =
  | { ok: true; target: SnapLine; moves: PlanMove[]; spacing: number }
  | {
      ok: false;
      /** `too-few`: under two fixtures. `no-truss`: no scanned truss. `beyond-walls`: a place on the truss is outside the room. */
      why: 'too-few' | 'no-truss' | 'beyond-walls';
      target?: SnapLine;
      /** For `beyond-walls`: how many of the row's places are outside. */
      beyond?: number;
    };

/**
 * Lays the fixtures `ids` along the scanned truss nearest their middle:
 * evenly spaced in address order (`spotsOn`), each at the truss's hang
 * height. This is the one move that respaces a row; a drag only carries it.
 *
 * All of the row is laid or none of it is. A truss the scan stored running
 * out through a wall may have places beyond the walls the plan holds a drag
 * to (`holdOnPlan`: the room's walls, or with no usable room the deck); the
 * row is then left where it is, not closed up to fit.
 *
 * The moves come back in address order. A fixture already on its place and
 * at the height is still listed: `withMoves` is what tells a change.
 */
export function layRowOnTruss(
  fixtures: AddressedFixture[], ids: Iterable<number>, shell: RoomShell | null | undefined,
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
): RowLay {
  const wanted = new Set(ids);
  const row = addressOrder(fixtures.filter((fixture) => wanted.has(fixture.id)));
  if (row.length < 2) return { ok: false, why: 'too-few' };
  const points = row.map((fixture) => ({ x: fixture.position_x, z: fixture.position_z }));
  const target = nearestTruss(planTrussTargets(shell), points);
  if (!target) return { ok: false, why: 'no-truss' };

  const spots = spotsOn(target, points);
  const beyond = spots.filter((spot) => {
    const held = holdOnPlan(spot.x, spot.z, stageWidth, stageDepth, walls);
    return Math.hypot(held.x - spot.x, held.z - spot.z) > INSIDE_WITHIN_M;
  }).length;
  if (beyond > 0) return { ok: false, why: 'beyond-walls', target, beyond };

  return {
    ok: true,
    target,
    moves: row.map((fixture, k) => ({ id: fixture.id, x: spots[k].x, z: spots[k].z, y: target.height })),
    spacing: spacingOn(target, row.length),
  };
}

/**
 * What to tell the person about a row that was laid, or was not: "Laid 4
 * fixtures along Truss 1, 2.00 m apart, at 4.20 m." `changed` is how many
 * of them it moved; none means the row was already there.
 */
export function layNoticeText(lay: RowLay, changed = 1): string {
  if (!lay.ok) {
    if (lay.why === 'too-few') return 'Select two or more fixtures to lay along a truss.';
    if (lay.why === 'no-truss' || !lay.target) return 'This rig has no scanned truss to lay a row along.';
    return `${targetWords(lay.target)} runs beyond the walls: ${lay.beyond} of the row's places on it are outside the room. Nothing was moved.`;
  }
  const count = lay.moves.length;
  const where = lay.target.ring ? 'round' : 'along';
  const apart = `${lay.spacing.toFixed(2)} m apart, at ${lay.target.height.toFixed(2)} m`;
  if (changed === 0) return `The ${count} fixtures are already laid ${where} ${targetWords(lay.target)}, ${apart}.`;
  const crowded = lay.spacing < CROWDED_UNDER_M ? ' That is close: check they fit side by side.' : '';
  return `Laid ${count} fixtures ${where} ${targetWords(lay.target)}, ${apart}.${crowded}`;
}

// ---------------------------------------------------------------------------
// Moves applied, and undone
// ---------------------------------------------------------------------------

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
