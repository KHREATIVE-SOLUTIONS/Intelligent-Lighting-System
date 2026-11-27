/**
 * The DJ and Floor cameras in a scanned room (docs/ROOM_SCAN.md, slice 28).
 *
 * The presets in layout.ts are worked out for the booth the view makes up:
 * against the upstage wall, on the centre line. A scanned room's booth is
 * wherever the room has it, facing whichever way it faces (scanFloor.ts), so
 * those two cameras are worked out again here from the booth that is drawn:
 *
 * - the Floor camera stands out on the floor in front of the booth, as far
 *   back as the room goes that way, and looks at the booth;
 * - the DJ camera stands behind the DJ, a little to one side, and looks out
 *   over the decks the way the booth faces.
 *
 * Everything is measured in the booth's own frame: forward is the way it
 * faces, `(faceX, faceZ)`, and right is `(faceZ, -faceX)`, which is +X for a
 * booth facing downstage. The distances are the ones the made-up booth's
 * presets come to, read from the room instead of from the layout, so a booth
 * standing where the view's own would stand has the cameras the view always
 * had.
 *
 * Pure numbers: no React, and nothing drawn. A room with no scan, and a
 * scanned room with no booth, never come here: `cameraPreset` is left alone.
 */
import type { RoomShellBox } from '../../../types';
import { CAMERA_WALL_CLEARANCE } from './layout';
import type { CameraMode, CameraPreset } from './layout';
import { insetPoint, outlineClearance } from './outline';
import type { OutlinePoint } from './outline';
import { areaDistance } from './scanFloor';
import type { ScanBooth } from './scanFloor';

/** How far from the wall the booth faces the Floor camera stands: where the made-up room has it. */
export const FLOOR_CAMERA_FROM_WALL = 0.85;
/** How far above the top of the decks the Floor camera looks. */
export const FLOOR_CAMERA_LOOKS_ABOVE = 1.55;
/** How far behind the DJ the DJ camera stands, where there is room for it. */
export const DJ_CAMERA_BEHIND = 1.25;
/** A wall nearer than this behind where the DJ camera would stand has the camera stand behind it instead. */
export const DJ_CAMERA_WALL_NEAR = 0.3;
/** How far behind that wall. It is not drawn from its outer side, so the camera looks straight in. */
export const DJ_CAMERA_BEHIND_WALL = 1.0;
/** How far to the DJ's side the camera stands, and how far the other way it looks. */
export const DJ_CAMERA_SIDE = 0.95;
export const DJ_CAMERA_LOOKS_SIDE = -0.1;
/** How far above what the DJ stands on the camera is, and how high it looks. */
export const DJ_CAMERA_ABOVE = 2.3;
export const DJ_CAMERA_LOOKS_AT_Y = 1.2;
/**
 * How far in front of the booth the DJ camera looks: this much, and this
 * share of the floor between the booth and the wall it faces.
 */
const DJ_LOOKS_AHEAD = 0.375;
const DJ_LOOKS_AHEAD_SHARE = 0.35;
/** Where no wall is found in front of a booth, the floor is taken to go on this far. */
const OPEN_FLOOR_FALLBACK = 8;
/** How far behind the front face the DJ is taken to be where none is drawn. */
const NO_DJ_BEHIND_GEAR = 0.5;

/**
 * How far it is from a point on the plan to the first wall of the outline in
 * a direction (`dx, dz`, a unit vector). Infinity when no wall lies that way.
 */
export function distanceToWall(outline: OutlinePoint[], x: number, z: number, dx: number, dz: number): number {
  let best = Infinity;
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    const ex = b.x - a.x;
    const ez = b.z - a.z;
    const cross = dx * ez - dz * ex;
    // Along the wall: never met.
    if (Math.abs(cross) < 1e-12) continue;
    const along = ((a.x - x) * ez - (a.z - z) * ex) / cross;
    const onWall = ((a.x - x) * dz - (a.z - z) * dx) / cross;
    if (along > 1e-6 && onWall >= -1e-9 && onWall <= 1 + 1e-9 && along < best) best = along;
  }
  return best;
}

/** Whether a camera can stand at a point of the floor: clear of the walls, and not over a raised area. */
function canStand(outline: OutlinePoint[], risers: RoomShellBox[], x: number, z: number): boolean {
  if (!(outlineClearance(outline, x, z) >= CAMERA_WALL_CLEARANCE)) return false;
  return !risers.some((riser) => areaDistance(riser, x, z) === 0);
}

/**
 * Where the Floor camera stands for a booth: on the line straight out from
 * the middle of its front face, `FLOOR_CAMERA_FROM_WALL` short of the wall it
 * faces. Where that spot is too near another wall, or is over a raised area,
 * it comes back towards the booth a tenth of a metre at a time until it is
 * neither. Null where there is no such place (a booth facing a wall, or with
 * a raised area all the way along that line): the caller keeps its own.
 */
export function boothFloorStand(
  booth: ScanBooth, outline: OutlinePoint[], risers: RoomShellBox[] = [],
): { x: number; z: number } | null {
  if (outline.length < 3) return null;
  const reach = distanceToWall(outline, booth.x, booth.z, booth.faceX, booth.faceZ);
  if (!Number.isFinite(reach)) return null;
  // Never nearer the booth than the floor the crowd leaves empty in front of it.
  for (let out = reach - FLOOR_CAMERA_FROM_WALL; out >= 1; out -= 0.1) {
    const x = booth.x + booth.faceX * out;
    const z = booth.z + booth.faceZ * out;
    if (canStand(outline, risers, x, z)) return { x, z };
  }
  return null;
}

/**
 * A camera preset fitted to the booth a scanned room is drawn with. `preset`
 * is what `cameraPreset` gives for the mode, and comes back as it is (the
 * same object) for every mode but the DJ and Floor cameras, and for a room
 * with no booth. Those two keep its field of view, its tilt limit and, for
 * the Floor camera, its height.
 *
 * `outline` is the room's floor (its four corners for a box, `boxFloor`), and
 * `risers` the raised areas the Floor camera is kept off.
 */
export function boothCameraPreset(
  mode: CameraMode,
  preset: CameraPreset,
  booth: ScanBooth | null,
  outline: OutlinePoint[],
  risers: RoomShellBox[] = [],
): CameraPreset {
  if (!booth || outline.length < 3 || (mode !== 'dj' && mode !== 'floor')) return preset;
  const { faceX, faceZ } = booth;
  // To the booth's right as it faces: +X for one that faces downstage.
  const rightX = faceZ;
  const rightZ = 0 - faceX;

  if (mode === 'floor') {
    const stand = boothFloorStand(booth, outline, risers);
    return {
      ...preset,
      // With nowhere to stand in front of it, where the camera already stood, turned to the booth.
      position: stand ? [stand.x, preset.position[1], stand.z] : preset.position,
      target: [booth.x, booth.deskTopY + FLOOR_CAMERA_LOOKS_ABOVE, booth.z],
    };
  }

  // The DJ camera: behind the DJ, or a metre behind the wall at the DJ's back where there is no room.
  const djBack = booth.dj ? booth.dj.back : booth.gearBack + NO_DJ_BEHIND_GEAR;
  const standY = booth.dj ? booth.dj.y : booth.baseY;
  const wallBehind = distanceToWall(outline, booth.x, booth.z, 0 - faceX, 0 - faceZ);
  let back = djBack + DJ_CAMERA_BEHIND;
  if (wallBehind < back + DJ_CAMERA_WALL_NEAR) back = wallBehind + DJ_CAMERA_BEHIND_WALL;

  const wallAhead = distanceToWall(outline, booth.x, booth.z, faceX, faceZ);
  const ahead = DJ_LOOKS_AHEAD + DJ_LOOKS_AHEAD_SHARE * (Number.isFinite(wallAhead) ? wallAhead : OPEN_FLOOR_FALLBACK);
  // What it looks at and turns about is kept in the room, as every other camera's is.
  const looks = insetPoint(
    outline,
    booth.x + faceX * ahead + rightX * DJ_CAMERA_LOOKS_SIDE,
    booth.z + faceZ * ahead + rightZ * DJ_CAMERA_LOOKS_SIDE,
    CAMERA_WALL_CLEARANCE,
  );

  return {
    ...preset,
    position: [
      booth.x - faceX * back + rightX * DJ_CAMERA_SIDE,
      standY + DJ_CAMERA_ABOVE,
      booth.z - faceZ * back + rightZ * DJ_CAMERA_SIDE,
    ],
    target: [looks.x, DJ_CAMERA_LOOKS_AT_Y, looks.z],
  };
}
