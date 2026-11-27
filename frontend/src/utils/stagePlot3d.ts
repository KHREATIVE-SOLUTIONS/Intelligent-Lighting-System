/**
 * The stage plot underlay in the 3D view (docs/STAGE_PLOT.md, "In the 3D
 * view"): where the flat picture lies on the floor, worked out from the same
 * image-to-plan matrix the 2D plan draws it with (utils/stagePlot.ts).
 *
 * The plan's x and z are the 3D view's x and z (a fixture's position_x and
 * position_z go straight to both), with y up. So a matrix that is scale times a
 * turn, x = a*u + c*v + e and z = b*u + d*v + f, lays the image as:
 *
 * - its middle pixel at toPlan(m, W/2, H/2);
 * - W * s wide along the image's u axis and H * s deep along its v axis,
 *   where s = |(a, b)| is metres per pixel;
 * - its u axis pointing at (a, b) on the floor. Three's turn about y takes
 *   +x to (cos yaw, -sin yaw) in (x, z), so yaw = -atan2(b, a).
 *
 * The plane is a PlaneGeometry laid flat with rotation-x = -PI/2, inside a
 * group turned by yaw. Laid flat, the plane's +y (the texture's top, with
 * three's default flipY) points at -z, upstage: the image's top row is
 * upstage and its v axis runs downstage, as on the plan.
 */
import type { Matrix } from './stagePlot';
import { toPlan } from './stagePlot';

/** How far above the floor the plot lies: over the dance floor's glow strip (0.016), under the drag layer's floor ring (0.03). */
export const STAGE_PLOT_LIFT = 0.024;

export interface StagePlotPlane {
  centerX: number;
  centerZ: number;
  /** Metres, along the image's width. */
  width: number;
  /** Metres, along the image's height. */
  depth: number;
  /** Radians, the turn about y of the group the flat plane is in. */
  yaw: number;
}

/**
 * The plane for an image of widthPx x heightPx laid by matrix m, or null when
 * the matrix cannot be drawn (not finite, no size, or a mirror, which no
 * calibration makes).
 */
export function stagePlotPlane(m: Matrix, widthPx: number, heightPx: number): StagePlotPlane | null {
  if (!m.every(Number.isFinite) || !(widthPx > 0) || !(heightPx > 0)) return null;
  const [a, b, c, d] = m;
  const scale = Math.hypot(a, b);
  // A turn and a scale: (c, d) is (a, b) turned a quarter, and the same length.
  if (!(scale > 0) || Math.abs(c + b) > 1e-9 * scale || Math.abs(d - a) > 1e-9 * scale) return null;
  const centre = toPlan(m, widthPx / 2, heightPx / 2);
  return {
    centerX: centre.x,
    centerZ: centre.z,
    width: scale * widthPx,
    depth: scale * heightPx,
    yaw: -Math.atan2(b, a),
  };
}

/** The localStorage key of the "Show stage plot in 3D" choice for a rig. */
export const stagePlot3dKey = (rigId: number) => `stagePlot3d:${rigId}`;

/** The operator's choice for a rig, or null when they have made none. */
export function readStagePlot3dChoice(rigId: number): boolean | null {
  try {
    const stored = window.localStorage.getItem(stagePlot3dKey(rigId));
    return stored === 'on' ? true : stored === 'off' ? false : null;
  } catch {
    return null;
  }
}

export function writeStagePlot3dChoice(rigId: number, on: boolean): void {
  try {
    window.localStorage.setItem(stagePlot3dKey(rigId), on ? 'on' : 'off');
  } catch {
    // Private mode or a full store: the choice holds for this visit only.
  }
}
