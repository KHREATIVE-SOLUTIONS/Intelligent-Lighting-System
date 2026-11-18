/**
 * How bright a fixture's light on the room is.
 *
 * Each fixture throws a three.js spot light down its beam, and the patch that
 * light makes on the floor, a wall or the crowd is its pool. Three choices set
 * how a pool reads, and they are made together here.
 *
 * 1. No falloff with distance. A real lamp's light thins out as it travels,
 *    and so does a three.js light by default. With that left on, one setting
 *    could not suit every rig: a pool from a 9 m truss came out a third as
 *    bright as one from 4 m, and a batten a metre off the floor ten times
 *    brighter. Rigs here carry no photometric data to say how powerful their
 *    fixtures are, so a pool's brightness is made to depend on the fixture's
 *    level alone: the same level gives the same pool from any height.
 *
 * 2. The range still follows the beam, at one and a half times its throw, so
 *    the light stops a little way past where the beam lands. With no falloff
 *    that is the only thing that ends it.
 *
 * 3. Brightness is in step with the level from zero up. The light used to be
 *    off below 8 % and then come on at 8 % of full. That step could not be seen
 *    while the lights were dim; brighter, it shows as a pop in a slow fade.
 */

/**
 * The spot light's intensity at a level of 1. Chosen by eye in the club view
 * at the default quality, so that a pool shows on the dance floor at the
 * levels a show mostly runs at (0.1 to 0.3).
 *
 * At full, a white beam's pool is white: the people standing in it, and the
 * pale floor tiles under it very nearly. Pools that land on the same spot add
 * up, so a look that stacks a dozen heads on one point is white there well
 * below full. Lower this if a show sits at full for long.
 */
export const POOL_LIGHT_AT_FULL = 16;

/** three.js `decay` for the spot lights: 0 is no falloff with distance. */
export const POOL_LIGHT_DECAY = 0;

/** The light's range as a multiple of how far its beam travels. */
const RANGE_PER_THROW = 1.5;

/** Spot light intensity for a fixture level of 0 to 1. */
export function poolLightIntensity(level: number): number {
  if (!(level > 0)) return 0;
  return Math.min(1, level) * POOL_LIGHT_AT_FULL;
}

/** Spot light range for a beam that travels `throwDistance` (see `beamThrow`). */
export function poolLightRange(throwDistance: number): number {
  return throwDistance * RANGE_PER_THROW;
}
