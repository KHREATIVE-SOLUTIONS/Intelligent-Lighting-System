/**
 * Which fixtures get one of the few real spot lights.
 *
 * Pools are decals (poolLight.ts), which cast no shadows. With Shadows on, a
 * small fixed number of real, shadow-casting spot lights is handed each frame
 * to the brightest beams, and those fixtures' decals are left out so their
 * pools are not drawn twice. The number of lights never changes while Shadows
 * is on, so three.js builds its lit shaders once and not on every fade.
 *
 * A light stays with its fixture while that fixture is still lit and not far
 * dimmer than the brightest one waiting, so lights do not flick between two
 * beams of about the same level on every frame.
 */

/** How many real spot lights there are with Shadows on. */
export const REAL_POOL_LIGHTS = 4;

/** Below this level a fixture is not given a real light. */
export const REAL_POOL_LIGHT_MIN_LEVEL = 0.02;

/**
 * A light holder keeps its light unless the brightest waiting fixture is more
 * than this many times brighter.
 */
export const REAL_POOL_LIGHT_KEEP_RATIO = 1.5;

/**
 * Hand the `assignment.length` lights to fixtures. `levels[i]` is fixture i's
 * level this frame; `eligible(i)` says whether it has a pool at all (its beam
 * lands on something). `assignment` holds last frame's fixture index per light,
 * or -1, and is rewritten in place for this frame. `taken[i]` comes back 1 for
 * every fixture that holds a light; it must be at least `count` long.
 *
 * Allocates nothing: it runs every frame.
 */
export function assignPoolLights(
  levels: ArrayLike<number>,
  count: number,
  eligible: (index: number) => boolean,
  assignment: Int32Array,
  taken: Uint8Array,
  minLevel = REAL_POOL_LIGHT_MIN_LEVEL,
): void {
  taken.fill(0, 0, count);
  const usable = (i: number) => i >= 0 && i < count && levels[i] >= minLevel && eligible(i);

  // Keep last frame's holders that are still lit, for now.
  for (let slot = 0; slot < assignment.length; slot += 1) {
    const holder = assignment[slot];
    if (usable(holder) && !taken[holder]) {
      taken[holder] = 1;
    } else {
      assignment[slot] = -1;
    }
  }

  // Fill the free lights, brightest waiting fixture first; then let a much
  // brighter waiting fixture take the dimmest holder's light.
  for (;;) {
    let best = -1;
    for (let i = 0; i < count; i += 1) {
      if (taken[i] || !usable(i)) continue;
      if (best < 0 || levels[i] > levels[best]) best = i;
    }
    if (best < 0) return;

    let free = -1;
    let dimmest = -1;
    for (let slot = 0; slot < assignment.length; slot += 1) {
      const holder = assignment[slot];
      if (holder < 0) {
        free = slot;
        break;
      }
      if (dimmest < 0 || levels[holder] < levels[assignment[dimmest]]) dimmest = slot;
    }

    if (free >= 0) {
      assignment[free] = best;
      taken[best] = 1;
      continue;
    }
    if (dimmest >= 0 && levels[best] > levels[assignment[dimmest]] * REAL_POOL_LIGHT_KEEP_RATIO) {
      taken[assignment[dimmest]] = 0;
      assignment[dimmest] = best;
      taken[best] = 1;
      continue;
    }
    return;
  }
}
