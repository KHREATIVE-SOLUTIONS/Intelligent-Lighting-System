/**
 * How bright a beam looks in haze, along its length and across it
 * (docs/PREVIZ_LOOK.md).
 *
 * A beam in haze is light scattered back off the haze it passes through. Near
 * the lens it is dense and bright; further out the same light is spread over a
 * wider cone, so each bit of it is dimmer, roughly as the inverse square of the
 * distance, but never quite nothing (the haze keeps catching some). Seen side
 * on, the middle of the cone has more haze in the line of sight than its edge,
 * so the edge fades out instead of ending in a hard rim.
 *
 * The numbers live here once: the JS functions are what the tests read, and
 * BEAM_LOOK_GLSL writes the same functions, with the same constants, into the
 * beam shader. Pure: no three, no DOM.
 */

/** What the beam keeps of its brightness however far it goes. */
export const BEAM_FALLOFF_FLOOR = 0.2;
/** Metres from the mouth at which the beam is half way between full and its floor. */
export const BEAM_FALLOFF_HALF_M = 3;
/** The glow right at the lens, there even in clean air. */
export const BEAM_LENS_GLOW = 0.35;
/** How quickly the lens glow dies away, in metres. */
export const BEAM_LENS_GLOW_M = 0.35;
/** How much of the beam the haze shows at full haze. */
export const BEAM_HAZE_GAIN = 1.2;
/** A beam seen end on still shows this much: it must not vanish when you look up it. */
export const BEAM_EDGE_FLOOR = 0.12;
/** How far round the cone (as |cos| of the view angle) the soft edge reaches full strength. */
export const BEAM_EDGE_WIDTH = 0.7;
/** The flat beam's alpha at the default haze: what every beam was drawn at before. */
export const FLAT_BEAM_ALPHA = 0.42;
/** The haze the view starts at. The flat beam at this haze is the beam as it always was. */
export const DEFAULT_HAZE = 0.5;

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value);

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3 - 2 * t);
}

/**
 * Share of the beam's brightness left `distance` metres from its mouth: 1 at
 * the mouth, falling as an inverse square with a soft floor.
 */
export function beamFalloff(distance: number): number {
  const d = Math.max(0, distance) / BEAM_FALLOFF_HALF_M;
  return BEAM_FALLOFF_FLOOR + (1 - BEAM_FALLOFF_FLOOR) / (1 + d * d);
}

/** The glow at the lens, `distance` metres out. Independent of haze. */
export function lensGlow(distance: number): number {
  return BEAM_LENS_GLOW * Math.exp(-Math.max(0, distance) / BEAM_LENS_GLOW_M);
}

/** How much of the beam haze at `haze` (0 clean air, 1 thick) shows. */
export function beamHazeGain(haze: number): number {
  return BEAM_HAZE_GAIN * clamp01(haze);
}

/**
 * The soft edge across the cone. `facing` is the cosine between the beam
 * surface's normal and the eye (either sign: both walls of the tube draw):
 * 1 looking straight through the middle, 0 at the silhouette.
 */
export function beamEdge(facing: number): number {
  return BEAM_EDGE_FLOOR + (1 - BEAM_EDGE_FLOOR) * smoothstep(0, BEAM_EDGE_WIDTH, Math.abs(facing));
}

/** A soft beam's alpha: its level, the haze, how far from the lens and where across the cone. */
export function softBeamAlpha(level: number, distance: number, haze: number, facing: number): number {
  return level * (beamHazeGain(haze) * beamFalloff(distance) + lensGlow(distance)) * beamEdge(facing);
}

/** The flat beam (Soft beams off): one strength end to end, scaled by the haze. */
export function flatBeamAlpha(level: number, haze: number): number {
  return level * FLAT_BEAM_ALPHA * (clamp01(haze) / DEFAULT_HAZE);
}

const f = (value: number) => value.toFixed(4);

/** The functions above, in GLSL, for the beam fragment shader. */
export const BEAM_LOOK_GLSL = `
  float beamFalloff(float distance) {
    float d = max(distance, 0.0) / ${f(BEAM_FALLOFF_HALF_M)};
    return ${f(BEAM_FALLOFF_FLOOR)} + ${f(1 - BEAM_FALLOFF_FLOOR)} / (1.0 + d * d);
  }
  float lensGlow(float distance) {
    return ${f(BEAM_LENS_GLOW)} * exp(-max(distance, 0.0) / ${f(BEAM_LENS_GLOW_M)});
  }
  float beamEdge(float facing) {
    return ${f(BEAM_EDGE_FLOOR)} + ${f(1 - BEAM_EDGE_FLOOR)} * smoothstep(0.0, ${f(BEAM_EDGE_WIDTH)}, abs(facing));
  }
  float softBeamAlpha(float level, float distance, float haze, float facing) {
    float gain = ${f(BEAM_HAZE_GAIN)} * clamp(haze, 0.0, 1.0);
    return level * (gain * beamFalloff(distance) + lensGlow(distance)) * beamEdge(facing);
  }
  float flatBeamAlpha(float level, float haze) {
    return level * ${f(FLAT_BEAM_ALPHA)} * (clamp(haze, 0.0, 1.0) / ${f(DEFAULT_HAZE)});
  }
`;
