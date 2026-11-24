/**
 * A raised area at a heading: the footprint of a stage, riser or booth that
 * does not stand square to the room (docs/ROOM_SCAN.md, slice 21).
 *
 * A box of a room's shell may store `heading_deg`: degrees clockwise from
 * across the room seen from above, as a truss line's is. Its `width` then runs
 * along that heading and its `depth` square to it. One that stores none stands
 * square to the room, as every raised area did before a heading could be set,
 * and everything here then gives exactly what the plain sums always gave.
 *
 * Numbers only: no React, no drawing and no three.js, so the 2D plan, the 3D
 * view's drag and the tests can all read a footprint the same way. The server
 * reads it the same way too (backend/app/services/room_scan/edit.py,
 * `area_heading` and `area_corners`).
 */

export type FootprintPoint = { x: number; z: number };

/** What of a box says where it stands on the plan. */
export interface Footprint {
  center_x: number;
  center_z: number;
  width: number;
  depth: number;
  heading_deg?: number | null;
}

const HEADING_LIMIT_DEG = 360;

/**
 * A heading as a raised area stores one: over -90 and up to 90 degrees, to a
 * tenth. A rectangle looks the same after half a turn, so 135 is -45 and -90
 * is 90. Null for what is not a heading (not a number, or past a whole turn).
 */
export function foldHeading(degrees: unknown): number | null {
  if (typeof degrees !== 'number' || !Number.isFinite(degrees) || Math.abs(degrees) > HEADING_LIMIT_DEG) return null;
  let heading = degrees % 180;
  if (heading > 90) heading -= 180;
  else if (heading <= -90) heading += 180;
  return Math.round(heading * 10) / 10 + 0;
}

/** The heading a box stands at: 0, square to the room, for one that stores none or stores nonsense. */
export function boxHeading(box: { heading_deg?: number | null } | null | undefined): number {
  return foldHeading(box?.heading_deg) ?? 0;
}

/** The way a box's width runs and the way its depth runs, as unit steps on the plan. */
function boxAxes(heading: number): { ux: number; uz: number; vx: number; vz: number } {
  if (heading === 0) return { ux: 1, uz: 0, vx: 0, vz: 1 };
  const turn = (heading * Math.PI) / 180;
  const cos = Math.cos(turn);
  const sin = Math.sin(turn);
  return { ux: cos, uz: sin, vx: -sin, vz: cos };
}

/**
 * A point of the box's own, `across` metres along its width and `back` along
 * its depth from its middle, as a place on the plan.
 */
export function boxPoint(box: Footprint, across: number, back: number): FootprintPoint {
  const heading = boxHeading(box);
  if (heading === 0) return { x: box.center_x + across, z: box.center_z + back };
  const { ux, uz, vx, vz } = boxAxes(heading);
  return { x: box.center_x + across * ux + back * vx, z: box.center_z + across * uz + back * vz };
}

/**
 * The four corners of a box where it stands, in order round it: from the one
 * that is upstage stage right when it stands square, clockwise seen from
 * above (as the plan is drawn: top left, top right, bottom right, bottom left).
 */
export function boxCorners(box: Footprint): [FootprintPoint, FootprintPoint, FootprintPoint, FootprintPoint] {
  const halfW = box.width / 2;
  const halfD = box.depth / 2;
  return [
    boxPoint(box, -halfW, -halfD),
    boxPoint(box, halfW, -halfD),
    boxPoint(box, halfW, halfD),
    boxPoint(box, -halfW, halfD),
  ];
}

/**
 * What is said after a raised area's size when it does not stand square to
 * the room: ", turned 30 degrees". Nothing for one that does.
 */
export function headingText(heading: number | null | undefined): string {
  if (typeof heading !== 'number' || !Number.isFinite(heading) || heading === 0) return '';
  const shown = String(Math.round(heading * 10) / 10 + 0);
  return `, turned ${shown} degree${Math.abs(heading) === 1 ? '' : 's'}`;
}

/**
 * Which way a side of a box faces from its middle, in the room's words, by
 * where the middle of that side is. `depthSide` is true for the two sides
 * its depth runs between: at exactly 45 degrees, where a side faces two ways
 * as much, those keep "upstage" and "downstage" and the other two keep
 * "stage right" and "stage left", so no two sides are called the same.
 */
export function sideFacing(dx: number, dz: number, depthSide: boolean): 'upstage' | 'downstage' | 'stage right' | 'stage left' {
  const bias = depthSide ? 1e-9 : -1e-9;
  if (Math.abs(dz) + bias >= Math.abs(dx)) return dz < 0 ? 'upstage' : 'downstage';
  return dx < 0 ? 'stage right' : 'stage left';
}
