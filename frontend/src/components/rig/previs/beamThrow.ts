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
 * What a beam can land on. The floor is at 0. `walls` is null when no walls
 * are drawn (the venue is hidden): a beam then ends only on the floor or the
 * ceiling height, however far out that is.
 */
export type BeamRoom = {
  ceilingY: number;
  walls: { xMin: number; xMax: number; zMin: number; zMax: number } | null;
};

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
  if (walls) {
    reach = Math.min(
      reach,
      toWall(x, direction.x, walls.xMin, walls.xMax),
      toWall(z, direction.z, walls.zMin, walls.zMax),
    );
  }
  reach = Math.max(SHORTEST_THROW, reach);
  if (surface) surfaceUnder(surface, x, y, z, direction, reach, room);
  return reach;
}

