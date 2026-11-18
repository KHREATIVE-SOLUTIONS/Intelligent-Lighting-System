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
 */
export function beamRise(tiltRad: number): number {
  return -Math.cos(tiltRad);
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
