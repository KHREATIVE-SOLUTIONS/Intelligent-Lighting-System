/**
 * The drifting haze: where its few large puffs hang and the soft noise they
 * are drawn with (docs/PREVIZ_LOOK.md). Pure: numbers in, numbers out, made in
 * code with a seeded generator, so nothing is downloaded and every load looks
 * the same.
 */

/** A small seeded generator (mulberry32): the same seed, the same haze. */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const smooth = (t: number) => t * t * (3 - 2 * t);

/**
 * A soft cloud: value noise over a few octaves, faded to nothing well inside
 * the square's edge so a puff never shows its quad. RGBA, every channel the
 * same, `size` x `size`.
 */
export function hazeNoisePixels(size = 128, seed = 7): Uint8Array {
  const random = seededRandom(seed);
  const octaves = [4, 8, 16, 32];
  const weights = [0.5, 0.27, 0.15, 0.08];
  const grids = octaves.map((n) => Float32Array.from({ length: n * n }, () => random()));
  const out = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const u = (x + 0.5) / size;
      const v = (y + 0.5) / size;
      let value = 0;
      octaves.forEach((n, o) => {
        const grid = grids[o];
        const gx = u * n;
        const gy = v * n;
        const x0 = Math.floor(gx) % n;
        const y0 = Math.floor(gy) % n;
        const x1 = (x0 + 1) % n;
        const y1 = (y0 + 1) % n;
        const fx = smooth(gx - Math.floor(gx));
        const fy = smooth(gy - Math.floor(gy));
        const top = grid[y0 * n + x0] * (1 - fx) + grid[y0 * n + x1] * fx;
        const bottom = grid[y1 * n + x0] * (1 - fx) + grid[y1 * n + x1] * fx;
        value += weights[o] * (top * (1 - fy) + bottom * fy);
      });
      // Distance from the middle, 1 at the middle of each edge.
      const r = Math.hypot(u - 0.5, v - 0.5) * 2;
      const fade = r >= 0.95 ? 0 : 1 - smooth(Math.min(1, Math.max(0, (r - 0.2) / 0.75)));
      const level = Math.max(0, Math.min(1, (value - 0.25) * 1.6)) * fade;
      const byte = Math.round(level * 255);
      const k = (y * size + x) * 4;
      out[k] = byte;
      out[k + 1] = byte;
      out[k + 2] = byte;
      out[k + 3] = byte;
    }
  }
  return out;
}

export type HazeBounds = {
  xMin: number;
  xMax: number;
  zMin: number;
  zMax: number;
  /** The floor and the ceiling of the room the haze fills. */
  floorY: number;
  ceilingY: number;
};

export type HazePuffs = {
  /** x, y, z of each puff's middle and its size (metres across), four per puff. */
  puff: Float32Array;
  /** Two numbers 0-1 per puff, its phase in the drift and the turn of its cloud. */
  seed: Float32Array;
};

/**
 * Where `count` puffs hang in `bounds`: spread over the room, in the air
 * between head height and the ceiling, each a good share of the room across.
 */
export function layoutHazePuffs(count: number, bounds: HazeBounds, seedValue = 11): HazePuffs {
  const n = Math.max(0, Math.floor(count));
  const random = seededRandom(seedValue);
  const puff = new Float32Array(n * 4);
  const seed = new Float32Array(n * 2);
  const width = Math.max(1, bounds.xMax - bounds.xMin);
  const depth = Math.max(1, bounds.zMax - bounds.zMin);
  const low = bounds.floorY + 1.4;
  const high = Math.max(low, bounds.ceilingY - 0.6);
  const across = Math.min(14, Math.max(width, depth));
  for (let i = 0; i < n; i += 1) {
    // Stratified along X so they do not bunch up.
    const sx = (i + 0.2 + random() * 0.6) / Math.max(1, n);
    puff[i * 4] = bounds.xMin + sx * width;
    puff[i * 4 + 1] = low + random() * (high - low);
    puff[i * 4 + 2] = bounds.zMin + random() * depth;
    puff[i * 4 + 3] = across * (0.45 + random() * 0.3);
    seed[i * 2] = random();
    seed[i * 2 + 1] = random();
  }
  return { puff, seed };
}
