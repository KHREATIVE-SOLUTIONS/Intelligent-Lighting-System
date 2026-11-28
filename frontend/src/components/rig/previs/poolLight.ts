/**
 * How bright and how wide a fixture's light on the room is.
 *
 * Each fixture throws a three.js spot light down its beam, and the patch that
 * light makes on the floor, a wall or the crowd is its pool. Three choices set
 * how bright a pool reads, and they are made together here. How wide it is
 * comes last, and the drawn beam takes its width from the same numbers.
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
 * After each fixture's floor light was aimed down its own beam, the one
 * stacked-bright pool at stage centre went away and each pool was about a
 * thirtieth as bright, hard to see on the dark floor. The owner chose to
 * brighten them (Q3). 48 is three times the previous 16: enough for a single
 * pool to read at show levels, without restoring the old all-lights-on-one-
 * spot blow-out (that would be about 30 times).
 *
 * At full, a white beam's pool is white: the people standing in it, and the
 * pale floor tiles under it very nearly. Pools that land on the same spot add
 * up, so a look that stacks a dozen heads on one point is white there well
 * below full. Lower this if a show sits at full for long.
 */
export const POOL_LIGHT_AT_FULL = 48;

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

/**
 * How wide a fixture's light is: the spot light's cone in degrees either side
 * of its axis, for a zoom of 0 (tightest) to 1 (widest). The zoom is the
 * fixture's zoom channel, or its profile's beam angle if it has none.
 *
 * The light is nothing at the cone's edge and at half some way inside it (see
 * `poolRadius`), so the width a fixture is said to have, its beam angle, is
 * about three quarters of this, doubled.
 *
 * A spot's cone runs from 6 to 18 degrees. It used to run from 10 to 50: at
 * the middle of its zoom a spot lit a patch 46 degrees across from a beam
 * drawn 18 across. 6 to 18 puts the middle of the zoom at that drawn beam.
 * Every other fixture runs from 2.5 to 11.5, as it always has.
 */
export function poolConeDeg(spot: boolean, zoom: number): number {
  const amount = zoom > 0 ? Math.min(1, zoom) : 0;
  return spot ? 6 + amount * 12 : 2.5 + amount * 9;
}

/**
 * three.js `penumbra` for the spot lights: how soft a pool's edge is. The
 * light is full inside the inner 40 % of its cone and fades to nothing at the
 * cone's edge.
 */
export const POOL_LIGHT_PENUMBRA = 0.6;

/**
 * Radius of a pool on a surface square to the beam, `throwDistance` from the
 * light whose cone is `coneRad` either side of its axis: the ring where the
 * light has fallen to half. The drawn beam ends this wide, so a beam and the
 * pool it makes are the same size where they meet. The pool goes on, fading,
 * for about a third as far again outside it.
 *
 * three.js fades a spot light with a smoothstep on the cosine of the angle off
 * its axis, between the cone's edge and the inner cone, so half falls where
 * that cosine is midway between the two.
 */
export function poolRadius(throwDistance: number, coneRad: number): number {
  const edge = Math.cos(coneRad);
  const inner = Math.cos(coneRad * (1 - POOL_LIGHT_PENUMBRA));
  const half = (edge + inner) / 2;
  return (throwDistance * Math.sqrt(Math.max(0, 1 - half * half))) / half;
}

// ---------------------------------------------------------------------------
// Pools drawn as decals (docs/PREVIZ_PERFORMANCE.md)
//
// A three.js spot light per fixture made every lit surface loop over every
// light for every pixel: 24 lights on a canvas of several million pixels. The
// pools are now drawn as soft discs laid on the surface each beam lands on,
// all of them in one instanced draw, with no light at all. Their size and
// brightness come from the numbers above, so a decal pool and the spot light
// it replaces agree on where, how wide and how bright.
// ---------------------------------------------------------------------------

/**
 * How bright a decal pool at full is, as a share of white added to the
 * surface. With the spot lights, a white beam at full lit the floor very nearly
 * white (see POOL_LIGHT_AT_FULL); 1 gives the same. Tune here.
 */
export const POOL_DECAL_GAIN = 1;

/** How far off its surface a decal pool is drawn: over the stage plot (0.024), so it is not hidden by it. */
export const POOL_DECAL_LIFT = 0.028;

/** Decal brightness for a fixture level of 0 to 1: in step with the spot light it replaces. */
export function poolDecalStrength(level: number): number {
  return (poolLightIntensity(level) / POOL_LIGHT_AT_FULL) * POOL_DECAL_GAIN;
}

/**
 * The disc a decal pool is drawn as, on a surface square to the beam,
 * `throwDistance` from the light whose cone is `coneRad` either side of its
 * axis: `outer`, where the light ends (the cone's edge), and `innerFrac`, the
 * share of that radius inside which it is full (the inner cone).
 *
 * The decal fades with the square of the distance from its centre between the
 * two, which puts its half-way ring where `poolRadius` puts the spot light's,
 * so the drawn beam still ends as wide as its pool.
 */
export function poolDecal(throwDistance: number, coneRad: number): { outer: number; innerFrac: number } {
  const throwSafe = throwDistance > 0 ? throwDistance : 0;
  const cone = Math.min(Math.max(coneRad, 1e-4), Math.PI / 2 - 1e-3);
  const outerTan = Math.tan(cone);
  const innerTan = Math.tan(cone * (1 - POOL_LIGHT_PENUMBRA));
  return { outer: throwSafe * outerTan, innerFrac: innerTan / outerTan };
}

/**
 * Where a decal's fade is at half, as a share of its outer radius: the fade is
 * a smoothstep on the squared radius from innerFrac² to 1.
 */
export function poolDecalHalfFrac(innerFrac: number): number {
  return Math.sqrt((innerFrac * innerFrac + 1) / 2);
}
