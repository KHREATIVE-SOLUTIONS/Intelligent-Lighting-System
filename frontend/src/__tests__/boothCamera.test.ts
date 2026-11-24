// The DJ and Floor cameras in a scanned room (docs/ROOM_SCAN.md, slice 28):
// they go by the booth that is drawn, at its heading; a booth standing where
// the view's own would stand has the cameras the view always had; and every
// other camera, and a room with no booth, is left exactly as it was.
import { describe, expect, it } from 'vitest';
import {
  DJ_CAMERA_ABOVE, FLOOR_CAMERA_FROM_WALL, boothCameraPreset, boothFloorStand, distanceToWall,
} from '../components/rig/previs/boothCamera';
import { CAMERA_WALL_CLEARANCE, buildVenue, cameraPreset } from '../components/rig/previs/layout';
import type { CameraMode, CameraPreset } from '../components/rig/previs/layout';
import { outlineClearance } from '../components/rig/previs/outline';
import type { OutlinePoint } from '../components/rig/previs/outline';
import { boxFloor, placeScanBooth } from '../components/rig/previs/scanFloor';
import type { ScanBooth } from '../components/rig/previs/scanFloor';
import type { RoomShellBox } from '../types';

// A box room 10 m across and 12 m deep.
const ROOM = boxFloor(-5, 5, -6, 6);

/** A booth on a platform 1.3 m out from the upstage wall, on the centre line, facing downstage. */
const booth = (over: Partial<ScanBooth> = {}): ScanBooth => ({
  source: 'scan',
  riser: 0,
  x: 0,
  z: -4.7,
  faceX: 0,
  faceZ: 1,
  yaw: 0,
  heading: 0,
  width: 3,
  desk: true,
  deskTopY: 1.25,
  baseY: 0.3,
  deskDepth: 0.55,
  gearBack: 0.275,
  dj: { x: 0, y: 0.3, z: -5.5, back: 0.8 },
  clear: { xMin: -1.5, xMax: 1.5, zMin: -4.7, zMax: -3.7 },
  strip: null,
  ...over,
});

// What `cameraPreset` might give: only its height, field of view and tilt limit are kept.
const FLOOR: CameraPreset = { position: [0, 2.3, 3], target: [0, 2.8, -5], maxPolar: 2.2, fov: 66 };
const DJ: CameraPreset = { position: [0.95, 2.6, -7], target: [-0.1, 1.2, 0], maxPolar: 2.2, fov: 58 };

/** A point of the plan turned about the origin, clockwise seen from above, as a heading turns one. */
const turn = (degrees: number) => {
  const cos = Math.cos((degrees * Math.PI) / 180);
  const sin = Math.sin((degrees * Math.PI) / 180);
  return (x: number, z: number): [number, number] => [x * cos - z * sin, x * sin + z * cos];
};

/** The booth and the room turned together about the middle of the room. */
function turned(degrees: number, from: ScanBooth, room: OutlinePoint[]): { booth: ScanBooth; room: OutlinePoint[] } {
  const at = turn(degrees);
  const [x, z] = at(from.x, from.z);
  const [faceX, faceZ] = at(from.faceX, from.faceZ);
  const dj = from.dj ? { ...from.dj, x: at(from.dj.x, from.dj.z)[0], z: at(from.dj.x, from.dj.z)[1] } : null;
  return {
    booth: { ...from, x, z, faceX, faceZ, yaw: Math.atan2(faceX, faceZ), heading: degrees, dj },
    room: room.map((point) => ({ x: at(point.x, point.z)[0], z: at(point.x, point.z)[1] })),
  };
}

const dot = (a: [number, number], b: [number, number]) => a[0] * b[0] + a[1] * b[1];

describe('distanceToWall', () => {
  it('is how far it is to the first wall that way', () => {
    expect(distanceToWall(ROOM, 0, -4.7, 0, 1)).toBeCloseTo(10.7);
    expect(distanceToWall(ROOM, 0, -4.7, 0, -1)).toBeCloseTo(1.3);
    expect(distanceToWall(ROOM, 2, 0, 1, 0)).toBeCloseTo(3);
    expect(distanceToWall(ROOM, 2, 0, -1, 0)).toBeCloseTo(7);
    // At an angle: from the middle to a corner of a 10 by 12 room.
    const corner = Math.hypot(5, 6);
    expect(distanceToWall(ROOM, 0, 0, 5 / corner, 6 / corner)).toBeCloseTo(corner);
  });

  it('is the nearer wall of a notch, and nothing where no wall lies that way', () => {
    // An L: x > 2, z > 1 is walled off.
    const ell = [{ x: -5, z: -6 }, { x: 5, z: -6 }, { x: 5, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 6 }, { x: -5, z: 6 }];
    expect(distanceToWall(ell, 3, -4, 0, 1)).toBeCloseTo(5);
    expect(distanceToWall(ell, 0, -4, 0, 1)).toBeCloseTo(10);
    expect(distanceToWall([], 0, 0, 0, 1)).toBe(Infinity);
    // From outside the room, looking away from it.
    expect(distanceToWall(ROOM, 0, 7, 0, 1)).toBe(Infinity);
  });
});

describe('the cameras that do not go by the booth', () => {
  it('are given back as they are: every mode but DJ and Floor', () => {
    for (const mode of ['iso', 'top', 'front', 'audience'] as CameraMode[]) {
      expect(boothCameraPreset(mode, FLOOR, booth(), ROOM)).toBe(FLOOR);
    }
  });

  it('are given back as they are in a room with no booth, or with no floor', () => {
    expect(boothCameraPreset('dj', DJ, null, ROOM)).toBe(DJ);
    expect(boothCameraPreset('floor', FLOOR, null, ROOM)).toBe(FLOOR);
    expect(boothCameraPreset('floor', FLOOR, booth(), [])).toBe(FLOOR);
  });
});

describe('the Floor camera and the booth that is drawn', () => {
  it('stands at the far end of the floor the booth faces and looks at the booth', () => {
    const preset = boothCameraPreset('floor', FLOOR, booth(), ROOM);
    // The wall it faces is 10.7 m from its front; the camera is 0.85 m short of that.
    expect(preset.position[0]).toBeCloseTo(0);
    expect(preset.position[1]).toBe(2.3);
    expect(preset.position[2]).toBeCloseTo(6 - FLOOR_CAMERA_FROM_WALL);
    expect(preset.target[0]).toBeCloseTo(0);
    expect(preset.target[1]).toBeCloseTo(1.25 + 1.55);
    expect(preset.target[2]).toBeCloseTo(-4.7);
    expect([preset.fov, preset.maxPolar]).toEqual([66, 2.2]);
  });

  it('goes with a booth that stands elsewhere and faces another way', () => {
    // Out on the floor by the stage left wall, facing stage right.
    const side = booth({ x: 2, z: 0, faceX: -1, faceZ: 0, dj: { x: 2.8, y: 0, z: 0, back: 0.8 }, deskTopY: 1, baseY: 0 });
    const preset = boothCameraPreset('floor', FLOOR, side, ROOM);
    // 7 m of floor in front of it: the camera is 6.15 m out, 0.85 m from the stage right wall.
    expect(preset.position[0]).toBeCloseTo(-4.15);
    expect(preset.position[2]).toBeCloseTo(0);
    expect(preset.target[0]).toBeCloseTo(2);
    expect(preset.target[1]).toBeCloseTo(2.55);
    expect(preset.target[2]).toBeCloseTo(0);
    expect(boothFloorStand(side, ROOM)).toEqual({ x: preset.position[0], z: preset.position[2] });
  });

  it('comes back towards the booth off a raised area at the far end', () => {
    const riser: RoomShellBox = { kind: 'riser', center_x: 0, center_z: 5, width: 4, depth: 2, height: 0.4 };
    const stand = boothFloorStand(booth(), ROOM, [riser])!;
    // The riser's near edge is at z = 4: the first place a tenth of a metre at a time that is off it.
    expect(stand.x).toBeCloseTo(0);
    expect(stand.z).toBeCloseTo(3.95);
    expect(stand.z).toBeLessThan(4);
  });

  it('keeps where it stood, turned to the booth, when the booth faces a wall', () => {
    const cornered = booth({ z: 4.8, dj: null });
    expect(boothFloorStand(cornered, ROOM)).toBeNull();
    const preset = boothCameraPreset('floor', FLOOR, cornered, ROOM);
    expect(preset.position).toBe(FLOOR.position);
    expect(preset.target[2]).toBeCloseTo(4.8);
  });
});

describe('the DJ camera and the booth that is drawn', () => {
  it('stands a metre behind the wall at the DJ\'s back, to one side, and looks out over the decks', () => {
    const preset = boothCameraPreset('dj', DJ, booth(), ROOM);
    // The wall is 1.3 m behind the booth's front: no room for a camera between it and the DJ.
    expect(preset.position[0]).toBeCloseTo(0.95);
    expect(preset.position[1]).toBeCloseTo(0.3 + DJ_CAMERA_ABOVE);
    expect(preset.position[2]).toBeCloseTo(-7);
    // 0.375 m and 0.35 of the 10.7 m of floor in front of the booth: 4.12 m out.
    expect(preset.target[0]).toBeCloseTo(-0.1);
    expect(preset.target[1]).toBeCloseTo(1.2);
    expect(preset.target[2]).toBeCloseTo(-0.58);
    expect([preset.fov, preset.maxPolar]).toEqual([58, 2.2]);
  });

  it('stands in the room behind a DJ who has room behind', () => {
    const side = booth({ x: 2, z: 0, faceX: -1, faceZ: 0, dj: { x: 2.8, y: 0, z: 0, back: 0.8 }, deskTopY: 1, baseY: 0 });
    const preset = boothCameraPreset('dj', DJ, side, ROOM);
    // 0.8 m to the DJ and 1.25 m more: 2.05 m behind the front, 0.95 m short of the wall.
    expect(preset.position[0]).toBeCloseTo(4.05);
    expect(preset.position[1]).toBeCloseTo(DJ_CAMERA_ABOVE);
    // To its right as it faces stage right, which is downstage.
    expect(preset.position[2]).toBeCloseTo(0.95);
    expect(outlineClearance(ROOM, preset.position[0], preset.position[2])).toBeGreaterThan(0.9);
    // 0.375 + 0.35 * 7 = 2.825 m in front of it.
    expect(preset.target[0]).toBeCloseTo(-0.825);
    expect(preset.target[2]).toBeCloseTo(-0.1);
  });

  it('goes by the gear where no DJ is drawn', () => {
    const empty = booth({ dj: null, baseY: 0.3, gearBack: 0.275 });
    const preset = boothCameraPreset('dj', DJ, empty, ROOM);
    // Still behind the wall at its back, at the height of what the desk stands on.
    expect(preset.position[2]).toBeCloseTo(-7);
    expect(preset.position[1]).toBeCloseTo(0.3 + DJ_CAMERA_ABOVE);
  });
});

describe('a booth at a heading', () => {
  for (const degrees of [30, -60, 90]) {
    it(`has both cameras turned ${degrees} degrees with it`, () => {
      const square = booth();
      const { booth: swung, room } = turned(degrees, square, ROOM);
      const at = turn(degrees);
      for (const [mode, preset] of [['floor', FLOOR], ['dj', DJ]] as Array<[CameraMode, CameraPreset]>) {
        const flat = boothCameraPreset(mode, preset, square, ROOM);
        const got = boothCameraPreset(mode, preset, swung, room);
        // Worked out here from the angle alone: the camera of the booth standing square, turned about the room's middle.
        const position = at(flat.position[0], flat.position[2]);
        const target = at(flat.target[0], flat.target[2]);
        expect(got.position[0]).toBeCloseTo(position[0], 6);
        expect(got.position[2]).toBeCloseTo(position[1], 6);
        expect(got.position[1]).toBeCloseTo(flat.position[1], 6);
        expect(got.target[0]).toBeCloseTo(target[0], 6);
        expect(got.target[2]).toBeCloseTo(target[1], 6);
        expect(got.target[1]).toBeCloseTo(flat.target[1], 6);
      }
    });
  }

  it('looks along the booth\'s own facing, not along the room', () => {
    const { booth: swung, room } = turned(30, booth(), ROOM);
    const face: [number, number] = [swung.faceX, swung.faceZ];
    const floor = boothCameraPreset('floor', FLOOR, swung, room);
    const dj = boothCameraPreset('dj', DJ, swung, room);
    // The Floor camera is straight out in front of the booth, looking back at it.
    const out: [number, number] = [floor.position[0] - swung.x, floor.position[2] - swung.z];
    expect(dot(out, face)).toBeCloseTo(Math.hypot(out[0], out[1]));
    expect([floor.target[0], floor.target[2]]).toEqual([swung.x, swung.z]);
    // The DJ camera is behind it, and what it looks at is in front.
    expect(dot([dj.position[0] - swung.x, dj.position[2] - swung.z], face)).toBeLessThan(-1);
    expect(dot([dj.target[0] - swung.x, dj.target[2] - swung.z], face)).toBeGreaterThan(1);
  });
});

describe('the cameras of a booth that scanFloor placed', () => {
  const stage: RoomShellBox = { kind: 'stage', center_x: 0, center_z: -4.5, width: 6, depth: 3, height: 1, base_height: 0 };
  const bar: RoomShellBox = { kind: 'booth', center_x: 3.5, center_z: 3, width: 2, depth: 1, height: 1.1, base_height: 0 };
  const decks: RoomShellBox = {
    kind: 'booth', center_x: -3, center_z: 1, width: 2, depth: 1, height: 1, base_height: 0, heading_deg: 30, is_dj_booth: true,
  };

  it('aim at the marked booth, turned as it is, and not at the bar or the upstage wall', () => {
    const risers = [stage, bar, decks];
    const placed = placeScanBooth(ROOM, risers)!;
    expect(placed.source).toBe('marked');
    expect(placed.riser).toBe(2);
    expect(placed.heading).toBeCloseTo(30);
    const face: [number, number] = [placed.faceX, placed.faceZ];

    const floor = boothCameraPreset('floor', FLOOR, placed, ROOM, risers);
    expect([floor.target[0], floor.target[2]]).toEqual([placed.x, placed.z]);
    expect(floor.target[1]).toBeCloseTo(placed.deskTopY + 1.55);
    // It stands in the room, clear of the walls, straight out along the booth's turned facing.
    const out: [number, number] = [floor.position[0] - placed.x, floor.position[2] - placed.z];
    expect(dot(out, face)).toBeCloseTo(Math.hypot(out[0], out[1]));
    expect(Math.hypot(out[0], out[1])).toBeGreaterThanOrEqual(1);
    expect(outlineClearance(ROOM, floor.position[0], floor.position[2])).toBeGreaterThanOrEqual(CAMERA_WALL_CLEARANCE - 1e-9);

    const dj = boothCameraPreset('dj', DJ, placed, ROOM, risers);
    expect(dot([dj.position[0] - placed.x, dj.position[2] - placed.z], face)).toBeLessThan(-1);
    expect(dot([dj.target[0] - placed.x, dj.target[2] - placed.z], face)).toBeGreaterThan(1);
    expect(outlineClearance(ROOM, dj.target[0], dj.target[2])).toBeGreaterThanOrEqual(CAMERA_WALL_CLEARANCE - 1e-9);
  });

  it('aim at the guess on the stage when the room has no booth', () => {
    const placed = placeScanBooth(ROOM, [stage])!;
    expect(placed.source).toBe('guess');
    const floor = boothCameraPreset('floor', FLOOR, placed, ROOM, [stage]);
    expect([floor.target[0], floor.target[2]]).toEqual([placed.x, placed.z]);
    // Downstage of the stage's front edge, at the far end of the floor.
    expect(floor.position[0]).toBeCloseTo(0);
    expect(floor.position[2]).toBeCloseTo(6 - FLOOR_CAMERA_FROM_WALL);
  });
});

describe('a booth standing where the view\'s own would', () => {
  // The room as measured: 10 m by 12 m, 5 m high, round a 10 m by 8 m stage box.
  const { layout } = buildVenue({ width: 10, depth: 8, height: 4 }, [], { width: 10, depth: 12, height: 5 });
  const outline = boxFloor(-layout.wallX, layout.wallX, layout.backZ, layout.houseZ);
  const own = booth({
    x: 0,
    z: layout.booth.fasciaZ,
    deskTopY: layout.booth.deskTopY,
    baseY: layout.booth.riserHeight,
    dj: { x: 0, y: layout.booth.riserHeight, z: layout.booth.djZ, back: layout.booth.fasciaZ - layout.booth.djZ },
  });

  for (const mode of ['floor', 'dj'] as CameraMode[]) {
    it(`has the ${mode} camera the view always had`, () => {
      const always = cameraPreset(mode, layout);
      const got = boothCameraPreset(mode, always, own, outline);
      for (const axis of [0, 1, 2]) {
        expect(got.position[axis]).toBeCloseTo(always.position[axis], 6);
        expect(got.target[axis]).toBeCloseTo(always.target[axis], 6);
      }
      expect([got.fov, got.maxPolar]).toEqual([always.fov, always.maxPolar]);
    });
  }
});

describe('a room with no scan', () => {
  it('keeps every camera position it had: the presets are not touched', () => {
    const { layout } = buildVenue({ width: 12, depth: 10, height: 4.5 }, []);
    const { booth: own, danceFloor, floorCamera } = layout;
    expect(cameraPreset('dj', layout)).toEqual({
      position: [0.95, own.riserHeight + 2.3, layout.backZ - 1.0],
      target: [-0.1, 1.2, danceFloor.zMin + (danceFloor.zMax - danceFloor.zMin) * 0.35],
      maxPolar: Math.PI * 0.72,
      fov: 58,
    });
    expect(cameraPreset('floor', layout)).toEqual({
      position: [floorCamera.x, floorCamera.y, floorCamera.z],
      target: [0, own.deskTopY + 1.55, own.fasciaZ],
      maxPolar: Math.PI * 0.72,
      fov: 66,
    });
    // And with no booth to go by, the booth's cameras are those, the very same objects.
    for (const mode of ['iso', 'top', 'front', 'audience', 'dj', 'floor'] as CameraMode[]) {
      const preset = cameraPreset(mode, layout);
      expect(boothCameraPreset(mode, preset, null, [])).toBe(preset);
    }
  });
});
