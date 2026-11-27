/**
 * The DJ booth and the crowd in a scanned room (docs/ROOM_SCAN.md, slice 23).
 *
 * A room the view makes up has its booth against the upstage wall and a square
 * dance floor in front of it. A scanned room has neither: it has a floor of its
 * own shape, and a stage, risers and a booth wherever the scan found them. So
 * the booth goes on the raised area that is one, and the crowd fills whatever
 * floor is left open round all of it.
 *
 * A raised area may stand at a heading (`heading_deg`, raisedArea.ts): it is
 * then read as it stands, turned about its middle, and the booth on it faces
 * the way one of its own sides does. One with no heading is read by the plain
 * sums it always was, so a room with nothing turned comes out exactly the same.
 *
 * Pure numbers on the plan: no React, and nothing drawn here. Axes are the
 * rig's: metres, X across, -Z upstage.
 */
import type { RoomShellBox } from '../../../types';
import { pickDjBooth } from './boothPick';
import type { BoothSource } from './boothPick';
import {
  MAX_DENSITY, SPACING_AT_BACK_MAX, SPACING_AT_BACK_MIN, SPACING_AT_BOOTH, crowdPerson,
} from './crowdLayout';
import type { CrowdPerson } from './crowdLayout';
import { seededRandom } from './geometryKit';
import { DESK_DEPTH, DESK_HEIGHT } from './layout';
import { insideOutline, nearestOnOutline, outlineBox, outlineClearance } from './outline';
import type { OutlinePoint } from './outline';
import { boxAxes, boxCorners, boxHeading, sideFacing } from './raisedArea';
import type { Footprint } from './raisedArea';

/** Nobody stands nearer a wall than this. */
export const WALL_CLEAR = 0.5;
/** Nor nearer a stage, a riser or a booth. */
export const RAISED_CLEAR = 0.5;
/** The strip of floor in front of the booth that is kept empty. */
export const BOOTH_FRONT_CLEAR = 1;
/** Nor nearer a DJ standing on the floor behind a counter. */
const DJ_CLEAR = 0.9;

/**
 * A booth this tall or taller is the counter itself: the decks go on its top
 * and the DJ stands behind it. A lower one is a platform, with a desk on it.
 * It is the height from which a scan calls a small raised area a booth, so
 * every booth a scan found is a counter; a platform is one made lower by hand.
 */
export const COUNTER_MIN_HEIGHT = 0.6;
/** Nobody is drawn working at a counter taller than this. */
const COUNTER_MAX_HEIGHT = 1.3;
/** How far behind a desk or a counter the DJ stands. */
const DJ_BEHIND = 0.25;
/** The narrowest desk two decks and a mixer fit on. */
const DESK_MIN_WIDTH = 1.3;
const DESK_MAX_WIDTH = 6.5;

/** The grid the open floor is measured on, and how many cells of it a huge room may have. */
const CELL = 0.25;
const MAX_CELLS = 40000;

export type FloorRect = { xMin: number; xMax: number; zMin: number; zMax: number };

/** The floor of a box room as an outline: its four corners, clockwise seen from above. */
export function boxFloor(xMin: number, xMax: number, zMin: number, zMax: number): OutlinePoint[] {
  return [{ x: xMin, z: zMin }, { x: xMax, z: zMin }, { x: xMax, z: zMax }, { x: xMin, z: zMax }];
}

/** The footprint on the plan of a raised area that stands square to the room. */
export function footprint(shape: Footprint): FloorRect {
  return {
    xMin: shape.center_x - shape.width / 2,
    xMax: shape.center_x + shape.width / 2,
    zMin: shape.center_z - shape.depth / 2,
    zMax: shape.center_z + shape.depth / 2,
  };
}

/** How far a point on the plan is from a rectangle: 0 inside it. */
export function rectDistance(rect: FloorRect, x: number, z: number): number {
  const dx = Math.max(rect.xMin - x, 0, x - rect.xMax);
  const dz = Math.max(rect.zMin - z, 0, z - rect.zMax);
  return Math.hypot(dx, dz);
}

/**
 * How far a point on the plan is from a raised area as it stands: 0 on it.
 * One at a heading is measured to its turned corners (`boxCorners`); one
 * square to the room by its plain rectangle, as before a heading could be set.
 */
export function areaDistance(shape: Footprint, x: number, z: number): number {
  if (boxHeading(shape) === 0) return rectDistance(footprint(shape), x, z);
  const corners = boxCorners(shape);
  return insideOutline(corners, x, z) ? 0 : nearestOnOutline(corners, x, z).distance;
}

const topOf = (shape: RoomShellBox) => (shape.base_height ?? 0) + shape.height;

/** How high the surface under a point is: the top of the tallest raised area it is on, or the floor. */
function standingHeight(risers: RoomShellBox[], x: number, z: number): number {
  let height = 0;
  for (const riser of risers) {
    if (areaDistance(riser, x, z) === 0) height = Math.max(height, topOf(riser));
  }
  return height;
}

/**
 * Where the booth is in a scanned room, and how it is drawn there.
 *
 * The booth is worked out in a frame of its own: `x, z` is the middle of its
 * front face on the plan, it faces `faceX, faceZ`, and everything else is so
 * far behind that face. `yaw` is the turn about Y that takes +Z to the facing.
 */
export type ScanBooth = {
  /**
   * 'marked': it stands on the raised area somebody said is the DJ's booth.
   * 'scan': nobody said, and it stands on the first one the stored room calls a booth.
   * 'guess': the room has none, and it was put on the first stage. Only a
   * guess is drawn with the amber mark (boothPick.ts).
   */
  source: BoothSource;
  /** Which of the raised areas it stands on. */
  riser: number;
  x: number;
  z: number;
  faceX: number;
  faceZ: number;
  yaw: number;
  /** The heading of the raised area it stands on, in degrees: 0 for one square to the room. */
  heading: number;
  /** Along the front face. */
  width: number;
  /**
   * True for a desk standing on the raised area (a platform). False where the
   * raised area is itself the counter the decks are on.
   */
  desk: boolean;
  /** The top of the desk or counter: what the decks sit on. */
  deskTopY: number;
  /** What the desk stands on: the top of its platform. For a counter, the counter's own base. */
  baseY: number;
  deskDepth: number;
  /** How far behind the front face the middle of the decks is. */
  gearBack: number;
  /** Where the DJ stands, feet at `y`, `back` behind the front face. Null where there is nowhere to stand. */
  dj: { x: number; y: number; z: number; back: number } | null;
  /**
   * The floor in front of it that the crowd keeps out of. For a booth at a
   * heading this is only the box round that floor: `strip` is the floor itself.
   */
  clear: FloorRect;
  /** That floor as a box at the booth's heading. Null for a booth square to the room: `clear` is it. */
  strip: Footprint | null;
};

/** Downstage first: the way a booth faces when nothing says otherwise. */
const FACINGS: Array<[number, number]> = [[0, 1], [0, -1], [1, 0], [-1, 0]];
/** A wall this close in front of a raised area's edge means it does not face that way. */
const FRONT_PROBE = 0.75;

/** A side of a raised area: the way it faces on the plan, and how far from the middle it is. */
type Side = {
  fx: number;
  fz: number;
  half: number;
  /** True for the two sides the depth runs between: the front and back of one that stands square. */
  depthSide: boolean;
};

/**
 * The four sides of a raised area as it stands, the downstage one first. One
 * square to the room faces straight down, up and across the room (`FACINGS`).
 * One at a heading faces along its own width and depth (`boxAxes`), and its
 * downstage side is the one `sideFacing` calls that: past 45 degrees it is an
 * end of its width.
 */
function sidesOf(shape: RoomShellBox): Side[] {
  const heading = boxHeading(shape);
  if (heading === 0) {
    return FACINGS.map(([fx, fz]) => ({
      fx, fz, half: (fz !== 0 ? shape.depth : shape.width) / 2, depthSide: fz !== 0,
    }));
  }
  const { ux, uz, vx, vz } = boxAxes(heading);
  const sides: Side[] = [
    { fx: vx, fz: vz, half: shape.depth / 2, depthSide: true },
    { fx: 0 - vx, fz: 0 - vz, half: shape.depth / 2, depthSide: true },
    { fx: ux, fz: uz, half: shape.width / 2, depthSide: false },
    { fx: 0 - ux, fz: 0 - uz, half: shape.width / 2, depthSide: false },
  ];
  const down = sides.findIndex((side) => sideFacing(side.fx, side.fz, side.depthSide) === 'downstage');
  if (down > 0) sides.unshift(...sides.splice(down, 1));
  return sides;
}

/** The side of a raised area that faces the open floor (see `facingOpenFloor`). */
function sideToOpenFloor(outline: OutlinePoint[], shape: RoomShellBox, open: OutlinePoint[]): Side {
  let towardX = 0;
  let towardZ = 0;
  if (open.length > 0) {
    for (const cell of open) {
      towardX += cell.x;
      towardZ += cell.z;
    }
    towardX = towardX / open.length - shape.center_x;
    towardZ = towardZ / open.length - shape.center_z;
  } else {
    const wall = nearestOnOutline(outline, shape.center_x, shape.center_z);
    towardX = shape.center_x - wall.x;
    towardZ = shape.center_z - wall.z;
  }
  const sides = sidesOf(shape);
  let best = sides[0];
  let bestScore = -Infinity;
  let bestBlocked = true;
  for (const side of sides) {
    const { fx, fz } = side;
    const reach = side.half + FRONT_PROBE;
    const blocked = !(outlineClearance(outline, shape.center_x + fx * reach, shape.center_z + fz * reach) > 0);
    const score = towardX * fx + towardZ * fz;
    const better = bestBlocked !== blocked ? !blocked : score > bestScore + 1e-9;
    if (better) {
      best = side;
      bestScore = score;
      bestBlocked = blocked;
    }
  }
  return best;
}

/**
 * Which way a raised area faces: towards the open floor. It faces the way one
 * of its four sides does: straight along or across the room when it stands
 * square to it, and along its own width or depth when it is at a heading. The
 * side that looks most nearly at the middle of the open floor wins, unless a
 * wall stands right in front of it; with no open floor at all, the one away
 * from the nearest wall. Of two the same, downstage first.
 */
export function facingOpenFloor(
  outline: OutlinePoint[],
  shape: RoomShellBox,
  open: OutlinePoint[],
): [number, number] {
  const side = sideToOpenFloor(outline, shape, open);
  return [side.fx, side.fz];
}

/**
 * The booth of a scanned room. On the raised area somebody marked as the
 * DJ's booth ('marked', `is_dj_booth`); with none marked, on the first raised
 * area the room calls a booth, facing the open floor ('scan'). A room with
 * neither has no booth made up for it, unless it has a stage: then the booth
 * goes at the middle of the front edge of the first one ('guess'). Null for a
 * room with none of them (`pickDjBooth`).
 *
 * A marked raised area is drawn as what it is: a stage like a guessed booth
 * on one (a desk at its downstage edge), anything else like a booth the room
 * has (a counter from 0.6 m, a platform under that, facing the open floor).
 *
 * A raised area at a heading has its booth at that heading: on the side of it
 * that faces the open floor, or, for a guess, on its downstage side, both as
 * it stands turned.
 *
 * `outline` is the room's floor and `risers` its raised areas that can be
 * drawn (`scanRisers`). Any other booth or counter is left as the scan found it.
 */
export function placeScanBooth(outline: OutlinePoint[], risers: RoomShellBox[]): ScanBooth | null {
  if (outline.length < 3) return null;
  const pick = pickDjBooth(risers);
  if (!pick) return null;
  const { index, source } = pick;
  const shape = risers[index];
  const heading = boxHeading(shape);
  // How it is drawn goes by what the raised area is, not by how it was chosen. A stage is played
  // from its downstage edge with a desk on it; anything else is a booth facing the open floor. With
  // nobody having marked one, a guess is always on a stage and a scan's booth never is, so a room
  // with no mark comes out exactly as it did.
  const staged = shape.kind === 'stage';

  // A booth put on a stage goes at the stage's downstage edge, as a stage is
  // played: only a wall right in front of that edge turns it to the open floor.
  const downstage = sidesOf(shape)[0];
  // Out to the edge and then past it, in that order: the sum a square stage always had.
  const downstageOpen = outlineClearance(
    outline,
    shape.center_x + downstage.fx * downstage.half + downstage.fx * FRONT_PROBE,
    shape.center_z + downstage.fz * downstage.half + downstage.fz * FRONT_PROBE,
  ) > 0;
  const side = staged && downstageOpen
    ? downstage
    : sideToOpenFloor(outline, shape, openFloorCells(outline, risers).cells);
  const faceX = side.fx;
  const faceZ = side.fz;
  const deep = side.depthSide ? shape.depth : shape.width;
  const wide = side.depthSide ? shape.width : shape.depth;
  const base = shape.base_height ?? 0;
  const top = topOf(shape);
  // The middle of the raised area's own front face.
  const frontX = shape.center_x + faceX * (deep / 2);
  const frontZ = shape.center_z + faceZ * (deep / 2);

  const counter = !staged && shape.height >= COUNTER_MIN_HEIGHT;
  let width: number;
  let inset: number;
  let gearBack: number;
  let djBack: number;
  let standY: number;
  if (counter) {
    // The counter is the desk: decks on its top, on the DJ's side of it.
    width = Math.min(wide, DESK_MAX_WIDTH);
    inset = 0;
    gearBack = deep - Math.min(deep / 2, 0.3);
    djBack = Math.max(gearBack + 0.5, deep + DJ_BEHIND);
    standY = base;
  } else {
    // A platform: the desk stands at its front edge and the DJ behind the desk.
    const wanted = staged
      ? Math.min(Math.max(wide * 0.5, 2.2), wide - 0.3)
      : wide - 0.2;
    width = Math.min(DESK_MAX_WIDTH, Math.max(DESK_MIN_WIDTH, wanted));
    inset = 0.05;
    gearBack = DESK_DEPTH / 2;
    djBack = DESK_DEPTH + DJ_BEHIND;
    standY = top;
  }
  const x = frontX - faceX * inset;
  const z = frontZ - faceZ * inset;

  // The DJ needs somewhere to stand: in the room, clear of its walls, and on
  // a surface at the height the booth expects (the platform, or the floor the
  // counter stands on), with nothing else standing there.
  const djX = x - faceX * djBack;
  const djZ = z - faceZ * djBack;
  const onPlatform = counter || inset + djBack + 0.1 <= deep;
  const canStand = onPlatform
    && (!counter || shape.height <= COUNTER_MAX_HEIGHT)
    && outlineClearance(outline, djX, djZ) >= 0.1
    && Math.abs(standingHeight(risers, djX, djZ) - standY) <= 0.1;

  // The strip in front: as wide as a booth, or as the desk on a stage.
  const half = (staged ? width : Math.max(wide, width)) / 2;
  const aheadX = frontX + faceX * BOOTH_FRONT_CLEAR;
  const aheadZ = frontZ + faceZ * BOOTH_FRONT_CLEAR;
  let clear: FloorRect;
  let strip: Footprint | null = null;
  if (heading === 0) {
    clear = faceZ !== 0
      ? { xMin: frontX - half, xMax: frontX + half, zMin: Math.min(frontZ, aheadZ), zMax: Math.max(frontZ, aheadZ) }
      : { xMin: Math.min(frontX, aheadX), xMax: Math.max(frontX, aheadX), zMin: frontZ - half, zMax: frontZ + half };
  } else {
    // A box of its own at the raised area's heading, a metre out from the front face.
    strip = {
      center_x: (frontX + aheadX) / 2,
      center_z: (frontZ + aheadZ) / 2,
      width: side.depthSide ? half * 2 : BOOTH_FRONT_CLEAR,
      depth: side.depthSide ? BOOTH_FRONT_CLEAR : half * 2,
      heading_deg: heading,
    };
    clear = outlineBox(boxCorners(strip));
  }

  return {
    source,
    riser: index,
    x,
    z,
    faceX,
    faceZ,
    // A turn of `a` about Y takes +Z to (sin a, cos a) on the plan.
    yaw: Math.atan2(faceX, faceZ),
    heading,
    width,
    desk: !counter,
    deskTopY: counter ? top : top + DESK_HEIGHT,
    baseY: counter ? base : top,
    deskDepth: counter ? Math.min(DESK_DEPTH, deep) : DESK_DEPTH,
    gearBack,
    dj: canStand ? { x: djX, y: standY, z: djZ, back: djBack } : null,
    clear,
    strip,
  };
}

/** Where a camera stands on the floor: the crowd leaves it some room. */
export type FloorCamera = { x: number; z: number; clearRadius: number };

/**
 * Whether somebody can stand at a point: on the floor, inside the outline,
 * `WALL_CLEAR` from every wall and `RAISED_CLEAR` from every raised area as it
 * stands (turned, if it is at a heading), out of the strip in front of the booth, and not on top of the DJ or the camera.
 */
export function openFloorAt(
  outline: OutlinePoint[],
  risers: RoomShellBox[],
  x: number,
  z: number,
  booth: ScanBooth | null = null,
  camera: FloorCamera | null = null,
): boolean {
  if (!(outlineClearance(outline, x, z) >= WALL_CLEAR)) return false;
  for (const riser of risers) {
    if (areaDistance(riser, x, z) < RAISED_CLEAR) return false;
  }
  if (booth) {
    if ((booth.strip ? areaDistance(booth.strip, x, z) : rectDistance(booth.clear, x, z)) === 0) return false;
    if (booth.dj && Math.hypot(booth.dj.x - x, booth.dj.z - z) < DJ_CLEAR) return false;
  }
  if (camera && Math.hypot(camera.x - x, camera.z - z) < camera.clearRadius) return false;
  return true;
}

/**
 * The open floor as the middles of the squares of a grid that somebody can
 * stand at, and the side of a square. A quarter of a metre, coarser in a room
 * so big that it would be more squares than are worth counting.
 */
export function openFloorCells(
  outline: OutlinePoint[],
  risers: RoomShellBox[],
  booth: ScanBooth | null = null,
  camera: FloorCamera | null = null,
): { cells: OutlinePoint[]; step: number } {
  if (outline.length < 3) return { cells: [], step: CELL };
  const box = outlineBox(outline);
  const width = box.xMax - box.xMin;
  const depth = box.zMax - box.zMin;
  if (!(width > 0) || !(depth > 0) || !Number.isFinite(width * depth)) return { cells: [], step: CELL };
  const step = Math.max(CELL, Math.sqrt((width * depth) / MAX_CELLS));
  const cells: OutlinePoint[] = [];
  const nx = Math.ceil(width / step);
  const nz = Math.ceil(depth / step);
  for (let i = 0; i < nx; i += 1) {
    for (let j = 0; j < nz; j += 1) {
      const x = box.xMin + (i + 0.5) * step;
      const z = box.zMin + (j + 0.5) * step;
      if (openFloorAt(outline, risers, x, z, booth, camera)) cells.push({ x, z });
    }
  }
  return { cells, step };
}

/** How many people the open floor holds, whatever the quality mode asks for: the template crowd's density. */
export function scanCrowdCapacity(open: { cells: OutlinePoint[]; step: number }): number {
  return Math.max(0, Math.floor(open.cells.length * open.step * open.step * MAX_DENSITY));
}

/** A seed from the room itself, to the centimetre: the same room is the same crowd, an edited one is not. */
function seedOf(values: number[]): number {
  let hash = 0x811c9dc5;
  for (const value of values) {
    hash ^= Math.round(value * 100) | 0;
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * Who stands where in a scanned room: on the open floor (`openFloorAt`), at
 * the template crowd's spacing, tightest in front of the booth and thinning
 * out away from it, everybody facing it. With no booth they are spread evenly
 * and face every way. Seeded from the room, so nobody jumps to a new spot on
 * a re-render, and never more than `requested` or than the floor holds.
 */
export function placeScanCrowd(
  outline: OutlinePoint[],
  risers: RoomShellBox[],
  booth: ScanBooth | null,
  requested: number,
  camera: FloorCamera | null = null,
): CrowdPerson[] {
  const open = openFloorCells(outline, risers, booth, camera);
  const count = open.cells.length;
  const target = Math.min(Math.max(0, Math.floor(requested) || 0), scanCrowdCapacity(open));
  if (target === 0 || count === 0) return [];

  const seedValues: number[] = [];
  for (const point of outline) seedValues.push(point.x, point.z);
  for (const riser of risers) {
    seedValues.push(riser.center_x, riser.center_z, riser.width, riser.depth, riser.height, riser.base_height ?? 0);
    // Only one that is turned adds its heading: a room with nothing turned keeps the crowd it had.
    const heading = boxHeading(riser);
    if (heading !== 0) seedValues.push(heading);
  }
  if (booth) seedValues.push(booth.x, booth.z, booth.faceX, booth.faceZ);
  const random = seededRandom(seedOf(seedValues));

  // Nearest the booth first: a place in this list is how far back it is.
  let cells = open.cells;
  if (booth) {
    cells = open.cells
      .map((cell, index) => ({ cell, index, distance: Math.hypot(cell.x - booth.x, cell.z - booth.z) }))
      .sort((a, b) => a.distance - b.distance || a.index - b.index)
      .map((entry) => entry.cell);
  }

  const density = target / (count * open.step * open.step);
  const spacingAtBack = Math.min(
    SPACING_AT_BACK_MAX,
    Math.max(SPACING_AT_BACK_MIN, SPACING_AT_BACK_MAX - 0.14 * density),
  );
  const people: CrowdPerson[] = [];

  for (let attempt = 0; attempt < target * 60 && people.length < target; attempt += 1) {
    const pick = random();
    // Biased toward the booth, as the template crowd is toward its own.
    const along = booth ? Math.pow(pick, 1.9) : pick;
    const cell = cells[Math.min(count - 1, Math.floor(along * count))];
    const x = cell.x + (random() - 0.5) * open.step;
    const z = cell.z + (random() - 0.5) * open.step;
    // The middle of the square is open; a step off it may not be.
    if (!openFloorAt(outline, risers, x, z, booth, camera)) continue;

    const spacing = SPACING_AT_BOOTH + (spacingAtBack - SPACING_AT_BOOTH) * (booth ? along : 0.5);
    let clear = true;
    for (const other of people) {
      if (Math.abs(other.x - x) < spacing && Math.abs(other.z - z) < spacing
        && Math.hypot(other.x - x, other.z - z) < spacing) {
        clear = false;
        break;
      }
    }
    if (!clear) continue;

    const yaw = booth
      ? Math.atan2(booth.x - x, booth.z - z) + (random() - 0.5) * 0.5
      : random() * Math.PI * 2;
    people.push(crowdPerson(random, x, z, yaw));
  }

  return people;
}
