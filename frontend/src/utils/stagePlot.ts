/**
 * Stage plot underlay: the maths that lays an image's pixels onto the plan
 * (docs/STAGE_PLOT.md). The same conventions as the server
 * (backend/app/services/stage_plot.py), which is what a calibration is stored
 * by; this copy draws the live preview while the operator is calibrating.
 *
 * - Image pixels: u right, v down, (0, 0) the top-left corner.
 * - The plan: metres, x across, z downstage (down the plan).
 * - Rotation: degrees, positive turns the image clockwise on the plan.
 * - room = s * R(rotation) * (pixel - origin); the origin lands on (0, 0).
 * - A matrix is SVG's matrix(a b c d e f): x = a*u + c*v + e, z = b*u + d*v + f.
 */

export type Matrix = [number, number, number, number, number, number];

export interface ImagePoint { x: number; y: number }

export interface StagePlotCalibration {
  point_a: ImagePoint;
  point_b: ImagePoint;
  distance_m: number;
  origin: ImagePoint;
  rotation_deg: number;
  opacity: number;
}

export interface StagePlotTransform {
  scale_m_per_px: number;
  rotation_deg: number;
  offset_x: number;
  offset_z: number;
  matrix: Matrix;
}

/** What the server keeps about a rig's stage plot (GET .../stage-plot/info). */
export interface StagePlotInfo {
  rig_id: number;
  present: boolean;
  filename?: string | null;
  content_type?: string;
  byte_size?: number;
  width_px?: number;
  height_px?: number;
  calibration?: StagePlotCalibration | null;
  transform?: StagePlotTransform | null;
}

export const DEFAULT_OPACITY = 0.5;

/** The same turn, within (-180, 180]. */
export function normaliseRotation(degrees: number): number {
  let turned = degrees % 360;
  if (turned > 180) turned -= 360;
  else if (turned <= -180) turned += 360;
  return turned;
}

/** Why a calibration cannot be used, in a sentence, or null when it can. */
export function calibrationProblem(c: StagePlotCalibration): string | null {
  const numbers = [c.point_a.x, c.point_a.y, c.point_b.x, c.point_b.y, c.origin.x, c.origin.y,
    c.distance_m, c.rotation_deg, c.opacity];
  if (numbers.some((n) => typeof n !== 'number' || !Number.isFinite(n))) return 'Every number must be a finite number.';
  if (Math.hypot(c.point_b.x - c.point_a.x, c.point_b.y - c.point_a.y) < 2) {
    return 'The two points are on top of each other. Click two points further apart.';
  }
  if (!(c.distance_m > 0 && c.distance_m <= 1000)) return 'The distance must be more than 0 and at most 1000 metres.';
  if (!(c.opacity >= 0 && c.opacity <= 1)) return 'The opacity must be between 0 and 1.';
  return null;
}

/** The image-to-plan transform of a calibration (as the server works it out). */
export function calibrationTransform(c: StagePlotCalibration): StagePlotTransform {
  const scale = c.distance_m / Math.hypot(c.point_b.x - c.point_a.x, c.point_b.y - c.point_a.y);
  const rotation = normaliseRotation(c.rotation_deg);
  const theta = (rotation * Math.PI) / 180;
  const a = scale * Math.cos(theta);
  const b = scale * Math.sin(theta);
  const cc = -scale * Math.sin(theta);
  const d = scale * Math.cos(theta);
  const e = -(a * c.origin.x + cc * c.origin.y);
  const f = -(b * c.origin.x + d * c.origin.y);
  return { scale_m_per_px: scale, rotation_deg: rotation, offset_x: e, offset_z: f, matrix: [a, b, cc, d, e, f] };
}

/** A pixel of the image on the plan. */
export function toPlan(m: Matrix, u: number, v: number): { x: number; z: number } {
  return { x: m[0] * u + m[2] * v + m[4], z: m[1] * u + m[3] * v + m[5] };
}

/** A point on the plan as a pixel of the image: the inverse of `toPlan`. */
export function toImage(m: Matrix, x: number, z: number): ImagePoint {
  const [a, b, c, d, e, f] = m;
  const det = a * d - b * c;
  const dx = x - e;
  const dz = z - f;
  return { x: (d * dx - c * dz) / det, y: (-b * dx + a * dz) / det };
}

/**
 * Where an image not calibrated yet is drawn: as wide as the stage (or as deep,
 * whichever fits), unturned, its middle on the middle of the stage.
 */
export function fitTransform(widthPx: number, heightPx: number, stageWidth: number, stageDepth: number): Matrix {
  const scale = Math.min(stageWidth / widthPx, stageDepth / heightPx);
  return [scale, 0, 0, scale, -(scale * widthPx) / 2, -(scale * heightPx) / 2];
}

/** The SVG transform attribute for a matrix. */
export function svgMatrix(m: Matrix): string {
  return `matrix(${m.map((n) => +n.toFixed(9)).join(' ')})`;
}

/** The fixture tag a guessed position carries until a person places it (docs/ROOM_SCAN.md). */
export const UNCONFIRMED_TAG = 'position_unconfirmed';

export function isGuessed(tags: readonly string[] | null | undefined): boolean {
  return (tags ?? []).includes(UNCONFIRMED_TAG);
}
