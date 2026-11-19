/**
 * Sizes of the generic fixture models, in metres.
 *
 * These are not any one manufacturer's fixture: each is a typical example of
 * its type, sized like the real thing so a rig reads at the right scale.
 *
 * Every model is built around the point the light comes from. For a moving
 * head that is where the pan and tilt axes cross, and it is also where the rig
 * says the fixture is (`position_x/y/z`), so the beam starts exactly where the
 * engine's aiming maths assumes it does. The clamp and base sit above that
 * point on a hung fixture and below it on one standing on the floor.
 */

export type FixtureModelKind =
  | 'moving_head'
  | 'beam'
  | 'spot'
  | 'wash'
  | 'led_par'
  | 'led_bar'
  | 'strobe'
  | 'other';

export type MoverDims = {
  /** Barrel radius, and how far it reaches behind and in front of the pivot. */
  barrelRadius: number;
  barrelRear: number;
  barrelFront: number;
  /** Length of the taper at the front, from barrel radius down to the bezel. */
  nose: number;
  lensRadius: number;
  /** Yoke arms: distance from the pan axis, and the pivot-to-crossbar height. */
  armX: number;
  armDrop: number;
  armWidth: number;
  armThick: number;
  baseWidth: number;
  baseHeight: number;
  baseDepth: number;
  roundBase: boolean;
  /** Flat LED face (a wash) instead of a single lens. */
  cellFace: boolean;
};

export type FixtureSpec = {
  kind: FixtureModelKind;
  /** Pan/tilt yoke model. False for the fixed-body types. */
  mover: MoverDims | null;
  /** Light source up to the truss chord the clamp grips. */
  hangHeight: number;
  /** Light source down to the underside of the feet, when standing. */
  standHeight: number;
  /** How far in front of the light source the lens face is. */
  lensOffset: number;
};

/** Yoke crossbar thickness plus the pan bearing between yoke and base. */
export const YOKE_TOP_ALLOWANCE = 0.08;
/** Top of the base to the centre of the truss chord in the clamp. */
export const CLAMP_HEIGHT = 0.07;
/** Rubber feet under a base standing on the floor. */
export const FOOT_HEIGHT = 0.012;

function moverSpec(kind: FixtureModelKind, dims: MoverDims): FixtureSpec {
  const yokeTop = dims.armDrop + YOKE_TOP_ALLOWANCE;
  return {
    kind,
    mover: dims,
    hangHeight: yokeTop + dims.baseHeight + CLAMP_HEIGHT,
    standHeight: yokeTop + dims.baseHeight + FOOT_HEIGHT,
    lensOffset: dims.barrelFront,
  };
}

export const FIXTURE_SPECS: Record<FixtureModelKind, FixtureSpec> = {
  // Mid-size hybrid moving head, about 0.7 m from clamp to lens.
  moving_head: moverSpec('moving_head', {
    barrelRadius: 0.125, barrelRear: 0.16, barrelFront: 0.2, nose: 0.05, lensRadius: 0.095,
    armX: 0.168, armDrop: 0.24, armWidth: 0.11, armThick: 0.042,
    baseWidth: 0.36, baseHeight: 0.11, baseDepth: 0.27, roundBase: false, cellFace: false,
  }),
  // Beam: a compact head with a narrow barrel and lens on a round base.
  beam: moverSpec('beam', {
    barrelRadius: 0.092, barrelRear: 0.13, barrelFront: 0.19, nose: 0.035, lensRadius: 0.07,
    armX: 0.128, armDrop: 0.2, armWidth: 0.09, armThick: 0.036,
    baseWidth: 0.3, baseHeight: 0.1, baseDepth: 0.3, roundBase: true, cellFace: false,
  }),
  // Spot: the long barrel that holds the gobo and zoom optics.
  spot: moverSpec('spot', {
    barrelRadius: 0.12, barrelRear: 0.19, barrelFront: 0.27, nose: 0.09, lensRadius: 0.082,
    armX: 0.162, armDrop: 0.275, armWidth: 0.115, armThick: 0.042,
    baseWidth: 0.38, baseHeight: 0.12, baseDepth: 0.29, roundBase: false, cellFace: false,
  }),
  // Wash: a short, wide drum with a flat face of LED cells.
  wash: moverSpec('wash', {
    barrelRadius: 0.16, barrelRear: 0.085, barrelFront: 0.105, nose: 0, lensRadius: 0.142,
    armX: 0.2, armDrop: 0.215, armWidth: 0.09, armThick: 0.036,
    baseWidth: 0.31, baseHeight: 0.09, baseDepth: 0.23, roundBase: false, cellFace: true,
  }),
  // LED par: a short can in a double bracket.
  led_par: {
    kind: 'led_par', mover: null, hangHeight: 0.27, standHeight: 0.3, lensOffset: 0.1,
  },
  // One-metre LED batten.
  led_bar: {
    kind: 'led_bar', mover: null, hangHeight: 0.18, standHeight: 0.075, lensOffset: 0.048,
  },
  // Strobe panel.
  strobe: {
    kind: 'strobe', mover: null, hangHeight: 0.24, standHeight: 0.2, lensOffset: 0.055,
  },
  // Anything else: a small flood.
  other: {
    kind: 'other', mover: null, hangHeight: 0.22, standHeight: 0.19, lensOffset: 0.07,
  },
};

/**
 * Which model draws a fixture.
 *
 * `fixtureType` is whatever the profile says; only eight types reach the view
 * from the demo rigs but a patched rig can carry others. Anything with pan and
 * tilt gets a yoke, whatever it calls itself.
 */
export function resolveModelKind(fixtureType: string | undefined, hasPanTilt: boolean): FixtureModelKind {
  const type = String(fixtureType || 'other').toLowerCase();
  if (type === 'beam') return 'beam';
  if (type === 'spot' || type === 'profile') return 'spot';
  if (type === 'wash') return 'wash';
  if (type === 'moving_head' || type === 'mover' || type === 'hybrid') return 'moving_head';
  if (hasPanTilt) return 'moving_head';
  if (type === 'led_par' || type === 'par') return 'led_par';
  if (type === 'led_bar' || type === 'bar' || type === 'batten') return 'led_bar';
  if (type === 'strobe') return 'strobe';
  return 'other';
}
