/**
 * Gobos in the pools of light (docs/PREVIZ_LOOK.md): which pattern a fixture
 * has in, how it is turned, and the small atlas of patterns the pool shader
 * reads. Pure: no three, no DOM. The atlas is drawn here into plain pixels
 * (FloorPools makes the texture from them), so nothing is downloaded and the
 * tests can look at it.
 *
 * What the 3D view knows of a gobo is what the output frame says on the
 * fixture's gobo and gobo rotation channels. Where the profile names its
 * ranges ("Gobo 3", "Dots", "Open", "Rotation CW slow to fast"...) those names
 * decide. Where it does not, the values are read the way the engine writes
 * them (backend/app/services/effects/gobo_engine.py): the wheel at the slot
 * positions of GOBO_SLOTS, and the rotation channel as the wheel's angle,
 * 0 to 255 for one full turn.
 */

/** The patterns in the atlas, in cell order. 0 is open: nothing in the beam. */
export const GOBO_PATTERNS = ['open', 'dots', 'breakup', 'star', 'ring', 'lines'] as const;
export type GoboPattern = (typeof GOBO_PATTERNS)[number];
export const GOBO_OPEN = 0;

/** Cells across the atlas (a power of two; the last two are empty) and pixels per cell. */
export const GOBO_ATLAS_CELLS = 8;
export const GOBO_CELL_PX = 64;

/** How much of the pool (as a share of its decal's radius) the gobo image spans. */
export const GOBO_POOL_SPAN = 0.85;
/** Light that gets through the dark parts of a gobo in a soft-focused previs: a little. */
export const GOBO_FILL = 0.06;

const TWO_PI = Math.PI * 2;
const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value);

export function goboIndexOf(pattern: GoboPattern): number {
  return GOBO_PATTERNS.indexOf(pattern);
}

/**
 * Where in the atlas a point of a gobo is: `u` and `v` 0-1 across the gobo's
 * own square. Held half a texel inside its cell so a neighbour never bleeds in.
 */
export function goboAtlasUv(index: number, u: number, v: number): [number, number] {
  const cell = Math.max(0, Math.min(GOBO_ATLAS_CELLS - 1, Math.round(index)));
  const inset = 0.5 / GOBO_CELL_PX;
  const cu = Math.min(1 - inset, Math.max(inset, u));
  const cv = Math.min(1 - inset, Math.max(inset, v));
  return [(cell + cu) / GOBO_ATLAS_CELLS, cv];
}

/** The half-texel inset goboAtlasUv keeps to, for the shader. */
export const GOBO_ATLAS_INSET = 0.5 / GOBO_CELL_PX;

/**
 * How much light a pattern lets through at (x, y), both -1 to 1 across the
 * gobo: 1 open, 0 blocked. Everything outside radius 0.95 is blocked, so each
 * cell's border is dark and the atlas's mipmaps do not bleed between cells.
 */
export function goboPatternAt(index: number, x: number, y: number): number {
  const r = Math.hypot(x, y);
  if (r > 0.95) return 0;
  const pattern = GOBO_PATTERNS[index];
  switch (pattern) {
    case 'open':
      return 1;
    case 'dots': {
      if (r < 0.17) return 1;
      for (let k = 0; k < 6; k += 1) {
        const a = (k * TWO_PI) / 6;
        if (Math.hypot(x - 0.58 * Math.cos(a), y - 0.58 * Math.sin(a)) < 0.17) return 1;
      }
      return 0;
    }
    case 'breakup': {
      const s = Math.sin(5.1 * x + 1.3) * Math.sin(4.3 * y - 0.7)
        + 0.6 * Math.sin(9.7 * (x + y) + 2.1) * Math.sin(8.1 * (x - y));
      return s > 0.12 ? 1 : 0;
    }
    case 'star': {
      const edge = 0.3 + 0.62 * Math.abs(Math.cos(2.5 * Math.atan2(y, x))) ** 4;
      return r < edge ? 1 : 0;
    }
    case 'ring':
      return (r > 0.55 && r < 0.8) || r < 0.14 ? 1 : 0;
    case 'lines':
      return Math.cos(y * Math.PI * 4) > -0.15 ? 1 : 0;
    default:
      return 0;
  }
}

/**
 * The atlas: GOBO_ATLAS_CELLS cells side by side, each GOBO_CELL_PX square,
 * RGBA with every channel the same. Each pixel is the average of 3 x 3
 * samples, so the patterns' edges are smooth.
 */
export function buildGoboAtlasPixels(): Uint8Array {
  const width = GOBO_ATLAS_CELLS * GOBO_CELL_PX;
  const height = GOBO_CELL_PX;
  const out = new Uint8Array(width * height * 4);
  for (let cell = 0; cell < GOBO_PATTERNS.length; cell += 1) {
    for (let py = 0; py < height; py += 1) {
      for (let px = 0; px < GOBO_CELL_PX; px += 1) {
        let sum = 0;
        for (let sy = 0; sy < 3; sy += 1) {
          for (let sx = 0; sx < 3; sx += 1) {
            const x = ((px + (sx + 0.5) / 3) / GOBO_CELL_PX) * 2 - 1;
            const y = ((py + (sy + 0.5) / 3) / GOBO_CELL_PX) * 2 - 1;
            sum += goboPatternAt(cell, x, y);
          }
        }
        const byte = Math.round((sum / 9) * 255);
        const k = (py * width + cell * GOBO_CELL_PX + px) * 4;
        out[k] = byte;
        out[k + 1] = byte;
        out[k + 2] = byte;
        out[k + 3] = 255;
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Reading the gobo channels
// ---------------------------------------------------------------------------

/** A named span of a channel's values, as beamState has them. */
type Range = { name?: string | null; min_value: number; max_value: number };

/** The engine's wheel positions (gobo_engine.GOBO_SLOTS, 0-1) and the pattern drawn for each. */
export const ENGINE_GOBO_SLOTS: Array<[number, GoboPattern]> = [
  [0.12, 'dots'],
  [0.22, 'star'],
  [0.32, 'ring'], // spiral
  [0.42, 'breakup'], // organic breakup
  [0.52, 'lines'],
  [0.62, 'lines'], // grid
  [0.72, 'ring'], // broken circle
  [0.82, 'star'], // sharp cone
  [0.92, 'dots'], // tight spot
];
/** Below this (0-255) the wheel is open, as the engine's 0.0 "open" slot is. */
export const GOBO_OPEN_BELOW = 15;

/** The pattern for a gobo wheel value with no names to go by: the engine's nearest slot. */
export function goboFromValue(value: number): number {
  if (!(value >= GOBO_OPEN_BELOW)) return GOBO_OPEN;
  const at = value / 255;
  let best = ENGINE_GOBO_SLOTS[0];
  for (const slot of ENGINE_GOBO_SLOTS) if (Math.abs(slot[0] - at) < Math.abs(best[0] - at)) best = slot;
  return goboIndexOf(best[1]);
}

const NAMED: Array<[RegExp, GoboPattern]> = [
  [/star|cone|triangle|flower|burst/, 'star'],
  [/ring|circle|spiral|tunnel|donut/, 'ring'],
  [/dot|bubble|spot|hole/, 'dots'],
  [/line|bar|grid|stripe|grate|slat/, 'lines'],
  [/break|leaf|leaves|branch|organic|cloud|water|flame|fire|texture|foliage/, 'breakup'],
];

/**
 * The pattern for a named slot. Open (or no gobo) is open; a name that says
 * what it looks like gets that; any other ("Gobo 4") a pattern of its own by
 * its place on the wheel, so neighbouring slots look different.
 */
export function goboFromName(name: string | null | undefined, ordinal: number): number {
  const text = String(name ?? '').toLowerCase();
  if (!text.trim() || /open|no\s*gobo|white/.test(text)) return GOBO_OPEN;
  for (const [pattern, gobo] of NAMED) if (pattern.test(text)) return goboIndexOf(gobo);
  const others = GOBO_PATTERNS.length - 1;
  return 1 + (Math.max(0, Math.floor(ordinal)) % others);
}

function rangeIndex(ranges: Range[] | undefined, value: number): number {
  if (!ranges) return -1;
  for (let i = 0; i < ranges.length; i += 1) {
    if (value >= ranges[i].min_value && value <= ranges[i].max_value) return i;
  }
  return -1;
}

/** The atlas pattern for a gobo wheel at `value` (0-255), named ranges first. */
export function goboIndex(ranges: Range[] | undefined, value: number): number {
  const i = rangeIndex(ranges, value);
  if (i >= 0 && ranges![i].name) {
    // Ordinal among the slots that are not open, so the first gobo is pattern 1.
    let ordinal = 0;
    for (let j = 0; j < i; j += 1) if (goboFromName(ranges![j].name, 0) !== GOBO_OPEN) ordinal += 1;
    return goboFromName(ranges![i].name, ordinal);
  }
  return goboFromValue(value);
}

/** What the rotation channel says: a fixed angle, or a turning speed. */
export type GoboTurn = {
  /** True: the wheel is held at `goboAngle`. False: it turns at `goboSpin` (0 holds where it is). */
  goboIndexed: boolean;
  /** Radians. */
  goboAngle: number;
  /** Radians a second, signed. */
  goboSpin: number;
};

/** The fastest a gobo is drawn turning: one turn a second. */
export const GOBO_MAX_SPIN = TWO_PI;

/**
 * Read the gobo rotation channel at `value` (0-255) into `out`. With a range
 * named for turning (clockwise, counter-clockwise, stop, index) that decides;
 * otherwise it is the angle, as the engine writes it.
 */
export function goboRotation(ranges: Range[] | undefined, value: number, out: GoboTurn): GoboTurn {
  const i = rangeIndex(ranges, value);
  const range = i >= 0 ? ranges![i] : null;
  const name = String(range?.name ?? '').toLowerCase();
  const span = range ? range.max_value - range.min_value : 0;
  const along = range && span > 0 ? clamp01((value - range.min_value) / span) : 1;
  const speed = GOBO_MAX_SPIN * (0.05 + 0.95 * along);
  out.goboSpin = 0;
  if (name && /stop|no\s*rot|hold/.test(name)) {
    out.goboIndexed = false;
  } else if (name && /ccw|counter|anti|left|reverse|backward/.test(name)) {
    out.goboIndexed = false;
    out.goboSpin = -speed;
  } else if (name && /cw|clockwise|rotat|spin|forward|right/.test(name) && !/index|position|angle/.test(name)) {
    out.goboIndexed = false;
    out.goboSpin = speed;
  } else if (name && /index|position|angle/.test(name)) {
    out.goboIndexed = true;
    out.goboAngle = along * TWO_PI;
  } else {
    out.goboIndexed = true;
    out.goboAngle = (clamp01(value / 255)) * TWO_PI;
  }
  return out;
}
