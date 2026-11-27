/**
 * Fixing a suggested row's spacing and symmetry on the 2D plan: how far apart
 * a row is laid along scanned truss (the whole truss shared out, the row's
 * own spacing, or one typed in metres), a selection mirrored left to right
 * about the centre line, and a selection spaced evenly between its two ends.
 *
 * Numbers and words only: no React and no drawing. None of it gives a
 * height except a row laid on truss, and none of it touches a tag.
 * docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import { roundMm } from './previs/fixtureDrag';
import type { SnapLine } from './previs/fixtureDrag';
import { holdOnPlan, planTrussTargets } from './roomPlan2d';
import type { PlanPoint, PlanWalls } from './roomPlan2d';
import { addressOrder, layNoticeText, layRowOnTruss, nearestTruss, spotsOn } from './rowMove2d';
import type { AddressedFixture, PlanMove, RowLay } from './rowMove2d';

/** A place this near the walls counts as inside them, as for a row drag. */
const INSIDE_WITHIN_M = 1e-6;
/** A row may be this much longer than its truss and still be on it: rounding, not overhang. */
const FITS_WITHIN_M = 1e-6;

/** To the millimetre, as positions are stored, and never -0. */
const mm = (value: number) => roundMm(value) + 0;

const beyondPlan = (
  spot: PlanPoint, walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
) => {
  const held = holdOnPlan(spot.x, spot.z, stageWidth, stageDepth, walls);
  return Math.hypot(held.x - spot.x, held.z - spot.z) > INSIDE_WITHIN_M;
};

// ---------------------------------------------------------------------------
// How far apart a row is laid on a truss
// ---------------------------------------------------------------------------

/**
 * `fill`: the whole truss shared out, half a space at each end (what Lay on
 * truss always did). `keep`: the row's own spacing, centred on the middle of
 * the truss. `set`: a spacing typed in metres, centred the same way.
 */
export type LayMode = 'fill' | 'keep' | 'set';

/** The choice next to Lay on truss: the mode, and the metres as they were typed. */
export interface LayChoice {
  mode: LayMode;
  metres: string;
}

export const DEFAULT_LAY_CHOICE: LayChoice = { mode: 'fill', metres: '1' };

export const LAY_MODES: LayMode[] = ['fill', 'keep', 'set'];

/** What each mode is called in the choice. */
export const LAY_MODE_LABELS: Record<LayMode, string> = {
  fill: 'Fill truss',
  keep: 'Keep spacing',
  set: 'Set spacing',
};

/**
 * A typed spacing in metres: "1.2", " 0.75 ", "1,2" or "1.2 m". Null for
 * anything that is not a number above zero.
 */
export function parseSpacing(text: string): number | null {
  const cleaned = text.trim().replace(/\s*m$/i, '').replace(',', '.');
  if (!/^(\d+\.?\d*|\.\d+)$/.test(cleaned)) return null;
  const metres = Number(cleaned);
  return Number.isFinite(metres) && metres > 0 ? metres : null;
}

/**
 * A row's own spacing: the distance on the plan between the two of it that
 * are furthest apart, shared between the gaps. For a straight row that is its
 * average spacing whatever order the fixtures come in. 0 for under two, or
 * for a row all in one place.
 */
export function rowSpacing(row: PlanPoint[]): number {
  if (row.length < 2) return 0;
  let span = 0;
  for (let i = 0; i < row.length; i += 1) {
    for (let j = i + 1; j < row.length; j += 1) {
      span = Math.max(span, Math.hypot(row[j].x - row[i].x, row[j].z - row[i].z));
    }
  }
  return span / (row.length - 1);
}

/**
 * Where each fixture of a row goes on a truss line at a given spacing: the
 * row centred on the middle of the line, in the order given, keeping the
 * sense it had as a filled row does (`spotsOn`). Null when the row is longer
 * than the line, for a ring, for under two and for a spacing that is not
 * above zero.
 */
export function centredSpotsOn(target: SnapLine, row: PlanPoint[], spacing: number): PlanPoint[] | null {
  const count = row.length;
  if (target.ring || count < 2 || !(spacing > 0)) return null;
  const runX = target.x2 - target.x1;
  const runZ = target.z2 - target.z1;
  const length = Math.hypot(runX, runZ);
  if (!(length > 0) || spacing * (count - 1) > length + FITS_WITHIN_M) return null;
  // The way a filled row would run says which end the first of the row is at.
  const filled = spotsOn(target, row);
  const forwards = (filled[count - 1].x - filled[0].x) * runX + (filled[count - 1].z - filled[0].z) * runZ >= 0;
  const sense = forwards ? 1 : -1;
  const midX = (target.x1 + target.x2) / 2;
  const midZ = (target.z1 + target.z2) / 2;
  return row.map((_, k) => {
    const along = (k - (count - 1) / 2) * spacing * sense;
    return { x: midX + (runX / length) * along + 0, z: midZ + (runZ / length) * along + 0 };
  });
}

/** What laying a row at a chosen spacing comes to: as `RowLay`, with the ways a spacing can fail. */
export type SpacedLay =
  | RowLay
  | {
      ok: false;
      /**
       * `bad-spacing`: the typed spacing is not a number above zero.
       * `no-spacing`: the row is all in one place, so it has no spacing to keep.
       * `ring`: a ring is only ever filled.
       * `too-long`: at that spacing the row is longer than the truss.
       */
      why: 'bad-spacing' | 'no-spacing' | 'ring' | 'too-long';
      target?: SnapLine;
      /** For `too-long`: the spacing asked for, the length the row needs and the truss's. */
      spacing?: number;
      needs?: number;
      length?: number;
    };

/**
 * Lays the fixtures `ids` along the scanned truss nearest their middle, at
 * the spacing chosen. `fill` is `layRowOnTruss` itself. `keep` and `set`
 * centre the row on the middle of the truss line, in address order, each at
 * the truss's hang height.
 *
 * All of the row is laid or none of it is: a row longer than the truss is
 * not closed up or left overhanging, and a place beyond the walls the plan
 * holds a drag to moves nothing, as for a filled row.
 */
export function layRowSpaced(
  fixtures: AddressedFixture[], ids: Iterable<number>, shell: RoomShell | null | undefined,
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
  choice: LayChoice = DEFAULT_LAY_CHOICE,
): SpacedLay {
  if (choice.mode === 'fill') return layRowOnTruss(fixtures, ids, shell, walls, stageWidth, stageDepth);

  const wanted = new Set(ids);
  const row = addressOrder(fixtures.filter((fixture) => wanted.has(fixture.id)));
  if (row.length < 2) return { ok: false, why: 'too-few' };
  const points = row.map((fixture) => ({ x: fixture.position_x, z: fixture.position_z }));
  const target = nearestTruss(planTrussTargets(shell), points);
  if (!target) return { ok: false, why: 'no-truss' };
  if (target.ring) return { ok: false, why: 'ring', target };

  // The row's own spacing to the millimetre, so a row laid at it and laid
  // again is where it would be laid.
  const spacing = choice.mode === 'keep' ? roundMm(rowSpacing(points)) : parseSpacing(choice.metres);
  if (spacing === null) return { ok: false, why: 'bad-spacing', target };
  if (!(spacing > 0)) return { ok: false, why: 'no-spacing', target };

  const length = Math.hypot(target.x2 - target.x1, target.z2 - target.z1);
  const spots = centredSpotsOn(target, points, spacing);
  if (!spots) return { ok: false, why: 'too-long', target, spacing, needs: spacing * (row.length - 1), length };

  const beyond = spots.filter((spot) => beyondPlan(spot, walls, stageWidth, stageDepth)).length;
  if (beyond > 0) return { ok: false, why: 'beyond-walls', target, beyond };

  return {
    ok: true,
    target,
    moves: row.map((fixture, k) => ({
      id: fixture.id, x: mm(spots[k].x), z: mm(spots[k].z), y: roundMm(target.height),
    })),
    spacing,
  };
}

/** What to tell the person about a row laid at a chosen spacing, or not laid. */
export function spacedLayNoticeText(lay: SpacedLay, changed = 1): string {
  if (lay.ok) return layNoticeText(lay, changed);
  switch (lay.why) {
    case 'bad-spacing':
      return 'Type a spacing in metres above zero, such as 1.2. Nothing was moved.';
    case 'no-spacing':
      return 'These fixtures are all in one place, so there is no spacing to keep. Choose Fill truss or set a spacing. Nothing was moved.';
    case 'ring':
      return `${lay.target?.name ?? 'This truss'} is a ring, which is only ever filled: choose Fill truss. Nothing was moved.`;
    case 'too-long': {
      const name = lay.target?.name ?? 'the truss';
      return `At ${(lay.spacing ?? 0).toFixed(2)} m apart the row is ${(lay.needs ?? 0).toFixed(2)} m long, and ${name} is ${(lay.length ?? 0).toFixed(2)} m. Nothing was moved.`;
    }
    default:
      return layNoticeText(lay, changed);
  }
}

// ---------------------------------------------------------------------------
// A selection mirrored left to right
// ---------------------------------------------------------------------------

type Placed = { id: number; position_x: number; position_z: number };

/**
 * The line a selection is mirrored about, as an x: the middle of the scanned
 * room's walls (of the box round its floor outline), or with no room drawn
 * the stage centre line, x = 0.
 */
export function mirrorAxis(walls: PlanWalls | null | undefined): number {
  if (!walls || walls.points.length === 0) return 0;
  const xs = walls.points.map((point) => point.x);
  return (Math.min(...xs) + Math.max(...xs)) / 2 + 0;
}

/** A selection mirrored: the line it was mirrored about, where each goes, and how many the walls held. */
export interface Mirrored {
  axis: number;
  /** One for each selected fixture, in the order given. No height: a mirror keeps heights. */
  moves: PlanMove[];
  /** How many mirrored places were outside the room and were brought to its wall. */
  held: number;
}

/**
 * The fixtures `ids` mirrored left to right about the centre line
 * (`mirrorAxis`): each goes as far the other side of it as it was this side,
 * at the depth it had. A place that would be outside the room (the notch of
 * an L, or beyond the deck with no room) is held to the wall as a dragged
 * fixture is (`holdOnPlan`).
 *
 * To the millimetre. A fixture on the line stays where it is; `withMoves`
 * is what tells a change.
 */
export function mirrorMoves(
  fixtures: Placed[], ids: Iterable<number>,
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
): Mirrored {
  const wanted = new Set(ids);
  const axis = mirrorAxis(walls);
  let held = 0;
  const moves = fixtures.filter((fixture) => wanted.has(fixture.id)).map((fixture): PlanMove => {
    const across = { x: 2 * axis - fixture.position_x, z: fixture.position_z };
    const place = holdOnPlan(across.x, across.z, stageWidth, stageDepth, walls);
    if (Math.hypot(place.x - across.x, place.z - across.z) > INSIDE_WITHIN_M) held += 1;
    return { id: fixture.id, x: mm(place.x), z: mm(place.z) };
  });
  return { axis, moves, held };
}

/** "Mirrored 4 fixtures left to right about the stage centre line." `changed` is how many it moved. */
export function mirrorNoticeText(mirrored: Mirrored, changed: number, hasRoom: boolean): string {
  const count = mirrored.moves.length;
  if (count === 0) return 'Select one or more fixtures to mirror.';
  const line = hasRoom
    ? `the room's centre line (x = ${mirrored.axis.toFixed(2)} m)`
    : 'the stage centre line';
  const things = count === 1 ? 'fixture' : 'fixtures';
  if (changed === 0) {
    return count === 1
      ? `The fixture is on ${line}: there is nothing to mirror.`
      : `The ${count} fixtures are on ${line}: there is nothing to mirror.`;
  }
  const held = mirrored.held > 0 ? ` ${mirrored.held} held at the wall.` : '';
  return `Mirrored ${count} ${things} left to right about ${line}.${held}`;
}

// ---------------------------------------------------------------------------
// A selection spaced evenly between its two ends
// ---------------------------------------------------------------------------

/** What spacing a selection evenly comes to: the moves to make, or why none are made. */
export type EvenSpace =
  | {
      ok: true;
      /** The fixtures between the two ends, in address order. The ends are not moved and not listed. */
      moves: PlanMove[];
      /** How many fixtures the row has, ends included. */
      count: number;
      spacing: number;
    }
  | {
      ok: false;
      /**
       * `too-few`: under three fixtures. `no-span`: the two ends are in one
       * place. `beyond-walls`: a place between the ends is outside the room.
       */
      why: 'too-few' | 'no-span' | 'beyond-walls';
      beyond?: number;
    };

/**
 * Spaces the fixtures `ids` evenly: the first and the last **by DMX address**
 * (`addressOrder`) stay where they are, and the rest go at equal steps along
 * the straight line between them, in address order. A stray guess in the
 * middle of a row is so brought back into line. No height is given.
 *
 * All or none: where the straight line between the ends leaves the room
 * (across the notch of an L), nothing moves.
 */
export function evenMoves(
  fixtures: AddressedFixture[], ids: Iterable<number>,
  walls: PlanWalls | null | undefined, stageWidth: number, stageDepth: number,
): EvenSpace {
  const wanted = new Set(ids);
  const row = addressOrder(fixtures.filter((fixture) => wanted.has(fixture.id)));
  const count = row.length;
  if (count < 3) return { ok: false, why: 'too-few' };
  const first = row[0];
  const last = row[count - 1];
  const runX = last.position_x - first.position_x;
  const runZ = last.position_z - first.position_z;
  const span = Math.hypot(runX, runZ);
  if (!(span > INSIDE_WITHIN_M)) return { ok: false, why: 'no-span' };

  const spots = row.slice(1, -1).map((_, k) => ({
    x: first.position_x + (runX * (k + 1)) / (count - 1),
    z: first.position_z + (runZ * (k + 1)) / (count - 1),
  }));
  const beyond = spots.filter((spot) => beyondPlan(spot, walls, stageWidth, stageDepth)).length;
  if (beyond > 0) return { ok: false, why: 'beyond-walls', beyond };

  return {
    ok: true,
    moves: row.slice(1, -1).map((fixture, k) => ({ id: fixture.id, x: mm(spots[k].x), z: mm(spots[k].z) })),
    count,
    spacing: span / (count - 1),
  };
}

/** "Spaced 5 fixtures evenly, 1.25 m apart, between the first and the last by address." */
export function evenNoticeText(even: EvenSpace, changed = 1): string {
  if (!even.ok) {
    if (even.why === 'too-few') return 'Select three or more fixtures to space evenly.';
    if (even.why === 'no-span') {
      return 'The first and the last of these by address are in the same place: move one of them first. Nothing was moved.';
    }
    return `The straight line between the first and the last by address leaves the room: ${even.beyond} of the places on it are outside. Nothing was moved.`;
  }
  const apart = `${even.spacing.toFixed(2)} m apart`;
  if (changed === 0) return `The ${even.count} fixtures are already evenly spaced, ${apart}.`;
  return `Spaced ${even.count} fixtures evenly, ${apart}, between the first and the last by address.`;
}
