/**
 * How far a fixture's light travels before it meets the room.
 *
 * Each fixture's light on the floor is a three.js spot light, and a spot light
 * has a range: it fades as it nears that range and is gone at it. The range
 * used to be 1.5 times the fixture's height, which suits a beam pointing
 * straight down and no other. A beam leaning 40 degrees has a third further to
 * go and reached the floor with under a third of the light a vertical one
 * keeps; past 48 degrees it did not reach the floor at all. So the range is
 * worked out from where the beam is pointing, every frame.
 */

/** Nothing is lit from closer than this, and a range must never be zero. */
const SHORTEST_THROW = 0.25;
/** Used only if the room's own size is unusable. */
const FALLBACK_LONGEST_THROW = 30;

/**
 * The vertical part of the beam's direction: -1 straight down, 0 level, +1
 * straight up.
 *
 * Only tilt sets it. The head is turned tilt first and pan second (rotation
 * order 'YXZ'), and pan and the body's yaw are both turns about the vertical,
 * so neither changes how steeply the beam runs.
 *
 * `lensUp` is a fixed-body fixture standing on the floor, turned over to face
 * the ceiling. Its beam is turned over with it.
 */
export function beamRise(tiltRad: number, lensUp = false): number {
  const down = -Math.cos(tiltRad);
  return lensUp ? -down : down;
}

/**
 * Distance along the beam from the light to the floor, or to the ceiling for a
 * beam pointing above level.
 *
 * `sourceY` is the light's height, `rise` comes from `beamRise`, and `longest`
 * is the furthest any beam can travel in this room. A level beam meets neither
 * floor nor ceiling, and a light with no usable height has nothing to measure
 * from: both get `longest`.
 *
 * The answer is always a positive, finite number. three.js reads a range of 0
 * as "no limit", so a zero or a not-a-number here would light the whole room
 * where it should light nothing.
 */
export function beamThrow(sourceY: number, rise: number, ceilingY: number, longest: number): number {
  const cap = Number.isFinite(longest) && longest > SHORTEST_THROW ? longest : FALLBACK_LONGEST_THROW;
  const clearance = rise < 0 ? sourceY : ceilingY - sourceY;
  const distance = clearance / Math.abs(rise);
  if (!Number.isFinite(distance)) return cap;
  return Math.min(cap, Math.max(SHORTEST_THROW, distance));
}

/** A direction or a place in the room: x across, y up, z toward the audience. */
export type BeamVector = { x: number; y: number; z: number };

/**
 * Which way a fixture's beam points in the room, as a unit vector.
 *
 * `tiltRad` is the head's tilt. `turnRad` is everything that turns the head
 * about the vertical: its pan plus the yaw its body is hung at. The head is
 * turned tilt first and that turn second, so this is straight down, tilted
 * about X and then turned about Y. A fixture standing lens-up points the
 * opposite way.
 *
 * Writes into `out` and returns it, so the frame loop makes no garbage: this
 * runs for every fixture on every frame.
 */
export function beamDirection(tiltRad: number, turnRad: number, lensUp: boolean, out: BeamVector): BeamVector {
  const way = lensUp ? -1 : 1;
  const lean = Math.sin(tiltRad);
  out.x = way * -lean * Math.sin(turnRad);
  out.y = way * -Math.cos(tiltRad);
  out.z = way * -lean * Math.cos(turnRad);
  return out;
}

/**
 * Turn a beam's direction by the way its fixture is hung.
 *
 * `direction` is the beam in the fixture's own frame: `beamDirection` with the
 * head's tilt and pan and no yaw. `rxRad` and `rzRad` are the rig's
 * rotation_x and rotation_z (a fixture hung on its side, or leaning), and
 * `yawRad` its rotation_y. They are applied Z, then X, then Y, so the yaw is
 * always a turn about the room's vertical whatever the lean. In the scene that
 * is a group turned [rx, 0, rz] inside one turned [0, yaw, 0].
 *
 * With no lean this is `beamDirection(tilt, pan + yaw)`. Works in place.
 */
export function hangBeam(direction: BeamVector, rxRad: number, rzRad: number, yawRad: number): BeamVector {
  let { x, y, z } = direction;
  if (rzRad !== 0) {
    const c = Math.cos(rzRad);
    const s = Math.sin(rzRad);
    const nx = x * c - y * s;
    y = x * s + y * c;
    x = nx;
  }
  if (rxRad !== 0) {
    const c = Math.cos(rxRad);
    const s = Math.sin(rxRad);
    const ny = y * c - z * s;
    z = y * s + z * c;
    y = ny;
  }
  if (yawRad !== 0) {
    const c = Math.cos(yawRad);
    const s = Math.sin(yawRad);
    const nx = x * c + z * s;
    z = -x * s + z * c;
    x = nx;
  }
  direction.x = x;
  direction.y = y;
  direction.z = z;
  return direction;
}

/**
 * What a beam can land on. The floor is at 0. `walls` is null when no walls
 * are drawn (the venue is hidden): a beam then ends only on the floor or the
 * ceiling height, however far out that is.
 */
export type BeamRoom = {
  ceilingY: number;
  walls: { xMin: number; xMax: number; zMin: number; zMax: number } | null;
  /**
   * The walls of a room that is not a box, each from one corner of its floor
   * outline to the next. Given (and with `walls` not null), a beam ends on
   * these and not on the box: so one aimed into the notch of an L stops on
   * the notch's wall.
   */
  outline?: readonly BeamWall[] | null;
};

/**
 * One wall of a room that is not a box, on the plan: its two ends, its length
 * and the unit vector pointing from it into the room. `OutlineWall` in
 * outline.ts is one.
 */
export type BeamWall = {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  length: number;
  inX: number;
  inZ: number;
};

/**
 * A beam aimed dead at a corner must land on one of the two walls that meet
 * there, whatever the rounding, so a wall is taken to run this far past each
 * of its ends.
 */
const PAST_WALL_END = 1e-6;

/** Which wall `toOutline` last found, or -1 for none. Read straight after the call. */
let hitWall = -1;

/**
 * Distance along a beam on the plan from (x, z) to the first wall of an
 * outline it goes out through; which wall that is goes in `hitWall`. Infinity
 * and -1 when it meets none. Only a wall the beam crosses from the room's
 * side counts, as with the box: a fixture standing outside the room shines in
 * through the wall in front of it. Unlike the box's walls, which are taken
 * for planes with no ends, a wall here ends at its corners. Allocates
 * nothing: it runs for every fixture on every frame.
 */
function toOutline(x: number, z: number, headingX: number, headingZ: number, walls: readonly BeamWall[]): number {
  let nearest = Infinity;
  hitWall = -1;
  for (let i = 0; i < walls.length; i += 1) {
    const wall = walls[i];
    const closing = headingX * wall.inX + headingZ * wall.inZ;
    if (!(closing < 0)) continue;
    const distance = ((wall.x1 - x) * wall.inX + (wall.z1 - z) * wall.inZ) / closing;
    if (!(distance > 0) || distance >= nearest) continue;
    // Where it meets the wall's line has to be between the wall's two ends:
    // in a room with a notch, the line of one wall runs on across the room.
    const along = ((x + headingX * distance - wall.x1) * (wall.x2 - wall.x1)
      + (z + headingZ * distance - wall.z1) * (wall.z2 - wall.z1)) / wall.length;
    if (along < -PAST_WALL_END || along > wall.length + PAST_WALL_END) continue;
    nearest = distance;
    hitWall = i;
  }
  return nearest;
}

/** Distance along one axis to the wall a beam is heading for; none if it is heading away from both. */
function toWall(from: number, heading: number, low: number, high: number): number {
  const distance = heading > 0 ? (high - from) / heading : heading < 0 ? (low - from) / heading : Infinity;
  return distance > 0 ? distance : Infinity;
}

/**
 * The flat surface a beam lands on, as a plane: a point p is on it when
 * x * p.x + y * p.y + z * p.z = d. All four are 0 when the beam's end is on
 * nothing: it ran out at the longest throw, or started past the surface.
 *
 * The drawn beam is cut to this plane. A beam that leans meets the floor
 * sooner on one side than the other, and a flat end left one edge of it
 * hanging in the air over its own pool.
 */
export type BeamSurface = { x: number; y: number; z: number; d: number };

/** How near a surface the beam's end must be to count as on it, in metres. */
const ON_SURFACE = 1e-6;

/** Which surface the point `reach` along the beam is on, if any. */
function surfaceUnder(
  out: BeamSurface,
  x: number,
  y: number,
  z: number,
  direction: BeamVector,
  reach: number,
  room: BeamRoom,
  wall: BeamWall | null,
): void {
  out.x = 0;
  out.y = 0;
  out.z = 0;
  out.d = 0;
  const on = (from: number, heading: number, at: number) => Math.abs(from + heading * reach - at) < ON_SURFACE;
  if (direction.y < 0 && on(y, direction.y, 0)) {
    out.y = 1;
  } else if (direction.y > 0 && on(y, direction.y, room.ceilingY)) {
    out.y = 1;
    out.d = room.ceilingY;
  } else if (room.walls && room.outline) {
    // A room that is not a box: the wall of its outline the beam went out through.
    if (wall) {
      const off = (x + direction.x * reach - wall.x1) * wall.inX + (z + direction.z * reach - wall.z1) * wall.inZ;
      if (Math.abs(off) < ON_SURFACE) {
        out.x = wall.inX;
        out.z = wall.inZ;
        out.d = wall.x1 * wall.inX + wall.z1 * wall.inZ;
      }
    }
  } else if (room.walls) {
    const walls = room.walls;
    const wallX = direction.x > 0 ? walls.xMax : walls.xMin;
    const wallZ = direction.z > 0 ? walls.zMax : walls.zMin;
    if (direction.x !== 0 && on(x, direction.x, wallX)) {
      out.x = 1;
      out.d = wallX;
    } else if (direction.z !== 0 && on(z, direction.z, wallZ)) {
      out.z = 1;
      out.d = wallZ;
    }
  }
}

/**
 * Distance along the beam from the light at (x, y, z) to the first thing it
 * meets: the floor, the ceiling or a wall. This is where its pool is and
 * where the drawn beam ends.
 *
 * As `beamThrow`, the answer is always a positive, finite number. Given a
 * `surface`, it is filled in with what the beam landed on.
 */
export function beamLanding(
  x: number,
  y: number,
  z: number,
  direction: BeamVector,
  room: BeamRoom,
  longest: number,
  surface?: BeamSurface,
): number {
  let reach = beamThrow(y, direction.y, room.ceilingY, longest);
  const walls = room.walls;
  let wall: BeamWall | null = null;
  if (walls && room.outline) {
    // A room that is not a box: its own walls, and not the box round them.
    reach = Math.min(reach, toOutline(x, z, direction.x, direction.z, room.outline));
    if (hitWall >= 0) wall = room.outline[hitWall];
  } else if (walls) {
    reach = Math.min(
      reach,
      toWall(x, direction.x, walls.xMin, walls.xMax),
      toWall(z, direction.z, walls.zMin, walls.zMax),
    );
  }
  reach = Math.max(SHORTEST_THROW, reach);
  if (surface) surfaceUnder(surface, x, y, z, direction, reach, room, wall);
  return reach;
}

