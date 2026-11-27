// A scanned room that is not a box, as everything in the 3D view but its
// walls sees it: where a beam lands, where a fixture is bracketed and a truss
// stops, how far a drag may go, where the cameras stand, the beams and duct
// under its ceiling, and its walls moving out for a fixture beyond them.
// docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { beamLanding } from '../components/rig/previs/beamThrow';
import type { BeamRoom, BeamSurface } from '../components/rig/previs/beamThrow';
import {
  CAMERA_WALL_CLEARANCE, beamRoom, buildVenue, cameraPreset, roomSpan,
} from '../components/rig/previs/layout';
import type { CameraMode, LayoutFixture } from '../components/rig/previs/layout';
import {
  holdNearOutline,
  insetPoint,
  insideOutline,
  moveWallOut,
  nearestOnOutline,
  outlineArea,
  outlineAround,
  outlineBox,
  outlineClearance,
  outlineCrossesItself,
  outlineSpansX,
  outlineSpansZ,
  outlineWalls,
  spansInBoth,
} from '../components/rig/previs/outline';
import type { OutlinePoint } from '../components/rig/previs/outline';
import {
  buildOutlineCeilingDressing, outlineBeamRuns, outlineDuctRuns, roomOutline, scannedRoom,
} from '../components/rig/previs/roomShell';
import {
  OUTSIDE_MARGIN_M, beginDrag, clampPosition, nudgePosition, positionLimits, settleDrag,
} from '../components/rig/previs/fixtureDrag';
import type { RoomShell } from '../types';

// An L: 12 m by 10 m with its downstage stage-left corner (4 m by 4 m) walled
// off. Corners clockwise seen from above, from upstage stage right.
const L_OUTLINE: OutlinePoint[] = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];
const L_ROOM: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 10, height: 5, outline: L_OUTLINE, suggested: true },
  risers: [],
  truss_lines: [],
  truss_rings: [],
};
// The same room with the corner cut off at an angle instead.
const CUT_OUTLINE: OutlinePoint[] = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];
// 16 m by 14 m with a notch 10 m by 8 m: deep enough that its middle is more
// than 2 m from every wall, and wide enough that the middle of the room's box,
// (0, 0), is in it. The same room as backend/tests/unit/test_fixture_position_outline.py.
const DEEP_OUTLINE: OutlinePoint[] = [
  { x: -8, z: -7 }, { x: 8, z: -7 }, { x: 8, z: -1 }, { x: -2, z: -1 }, { x: -2, z: 7 }, { x: -8, z: 7 },
];
const DEEP_ROOM: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 16, depth: 14, height: 6, outline: DEEP_OUTLINE, suggested: true },
  risers: [],
  truss_lines: [],
  truss_rings: [],
};
// A U: two wings downstage either side of a notch in the middle.
const U_OUTLINE: OutlinePoint[] = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 5 }, { x: 2, z: 5 },
  { x: 2, z: 0 }, { x: -2, z: 0 }, { x: -2, z: 5 }, { x: -6, z: 5 },
];

const STAGE_BOX = { width: 12, depth: 10, height: 8 };
const DEEP_STAGE = { width: 16, depth: 14, height: 6 };

const head = (id: number, x: number, y: number, z: number): LayoutFixture => (
  { id, x, y, z, kind: 'moving_head', hasPanTilt: true }
);

function lVenue(fixtures: LayoutFixture[] = []) {
  return buildVenue(STAGE_BOX, fixtures, scannedRoom(L_ROOM), [], roomOutline(L_ROOM));
}

function vertices(geometry: THREE.BufferGeometry): THREE.Vector3[] {
  const position = geometry.getAttribute('position');
  return Array.from({ length: position.count }, (_, i) => new THREE.Vector3().fromBufferAttribute(position, i));
}

describe('the outline on the plan', () => {
  it('says what a line across the room passes through', () => {
    expect(outlineSpansX(L_OUTLINE, 0)).toEqual([[-6, 6]]);
    // Downstage of the notch's wall the room stops at it.
    expect(outlineSpansX(L_OUTLINE, 3)).toEqual([[-6, 2]]);
    expect(outlineSpansZ(L_OUTLINE, 0)).toEqual([[-5, 5]]);
    expect(outlineSpansZ(L_OUTLINE, 4)).toEqual([[-5, 1]]);
    // Outside the room altogether there is nothing.
    expect(outlineSpansX(L_OUTLINE, 9)).toEqual([]);
    // A room with a notch in the middle is crossed twice.
    expect(outlineSpansX(U_OUTLINE, 3)).toEqual([[-6, -2], [2, 6]]);
    expect(outlineSpansX([...U_OUTLINE].reverse(), 3)).toEqual([[-6, -2], [2, 6]]);
    // A wall at an angle is met where it is at that depth.
    expect(outlineSpansX(CUT_OUTLINE, 3)).toEqual([[-6, 4]]);
  });

  it('finds what two lots of stretches both cover', () => {
    expect(spansInBoth([[-6, 2]], [[-6, 6]])).toEqual([[-6, 2]]);
    expect(spansInBoth([[-6, -2], [2, 6]], [[-3, 3]])).toEqual([[-3, -2], [2, 3]]);
    expect(spansInBoth([[0, 1]], [[2, 3]])).toEqual([]);
  });

  it('measures to the nearest wall, inside and out', () => {
    expect(nearestOnOutline(L_OUTLINE, 0, 4)).toEqual({ x: 0, z: 5, distance: 1, segment: 4 });
    // In the notch, nearest the wall across it.
    expect(nearestOnOutline(L_OUTLINE, 4, 2)).toEqual({ x: 4, z: 1, distance: 1, segment: 2 });
    // Beyond a corner, the corner itself.
    expect(nearestOnOutline(L_OUTLINE, -9, -9)).toMatchObject({ x: -6, z: -5, distance: 5 });
    expect(outlineClearance(L_OUTLINE, 0, 4)).toBeCloseTo(1, 9);
    expect(outlineClearance(L_OUTLINE, 4, 2)).toBeCloseTo(-1, 9);
    expect(outlineBox(L_OUTLINE)).toEqual({ xMin: -6, xMax: 6, zMin: -5, zMax: 5 });
  });

  it('finds the nearest place that is clear of the walls', () => {
    // Already clear: the very same place.
    expect(insetPoint(L_OUTLINE, 0, 0, 0.6)).toEqual({ x: 0, z: 0 });
    // The middle of the deep room's box is in its notch. The nearest clear
    // place is upstage of the wall across the notch.
    const inside = insetPoint(DEEP_OUTLINE, 0, 0, 0.6);
    expect(inside).toEqual({ x: 0, z: -1.75 });
    expect(outlineClearance(DEEP_OUTLINE, inside.x, inside.z)).toBeGreaterThanOrEqual(0.6);
    // A room with nowhere that clear gives its most open point, which is in it.
    const tight = insetPoint(L_OUTLINE, 4, 3, 50);
    expect(insideOutline(L_OUTLINE, tight.x, tight.z)).toBe(true);
  });

  it('knows an outline that crosses itself', () => {
    expect(outlineCrossesItself(L_OUTLINE)).toBe(false);
    expect(outlineCrossesItself(U_OUTLINE)).toBe(false);
    expect(outlineCrossesItself([{ x: 0, z: 0 }, { x: 4, z: 4 }, { x: 4, z: 0 }, { x: 0, z: 4 }])).toBe(true);
  });
});

describe('where a beam lands in a room that is not a box', () => {
  const venue = lVenue();
  const room = beamRoom(venue.layout, true, venue.outlineWalls);
  const box = beamRoom(venue.layout, true);
  const longest = roomSpan(venue.layout);
  const level = (x: number, z: number) => {
    const length = Math.hypot(x, z);
    return { x: x / length, y: 0, z: z / length };
  };

  it('stops on the wall of the notch, where the box let it through', () => {
    const surface: BeamSurface = { x: 9, y: 9, z: 9, d: 9 };
    // Downstage of the notch's wall, heading stage left: the wall down the notch is 2 m off.
    expect(beamLanding(0, 4, 3, level(1, 0), room, longest, surface)).toBeCloseTo(2, 9);
    expect(surface).toEqual({ x: -1, y: 0, z: 0, d: -2 });
    expect(beamLanding(0, 4, 3, level(1, 0), box, longest)).toBeCloseTo(6, 9);
    // Upstage of it, heading downstage: the wall across the notch is 1 m off.
    expect(beamLanding(4, 4, 0, level(0, 1), room, longest, surface)).toBeCloseTo(1, 9);
    expect(surface).toEqual({ x: 0, y: 0, z: -1, d: -1 });
    expect(beamLanding(4, 4, 0, level(0, 1), box, longest)).toBeCloseTo(5, 9);
  });

  it('passes the end of a wall it is not heading for', () => {
    // Heading stage left upstage of the notch: the line of the wall down the
    // notch is crossed where that wall is not, so the beam carries on.
    expect(beamLanding(0, 4, 0, level(1, 0), room, longest)).toBeCloseTo(6, 9);
    // And it lands on the outer walls exactly where the box had them.
    expect(beamLanding(0, 4, 0, level(-1, 0), room, longest)).toBeCloseTo(6, 9);
    expect(beamLanding(0, 4, 0, level(0, -1), room, longest)).toBeCloseTo(5, 9);
    expect(beamLanding(0, 4, 0, level(0, 1), room, longest)).toBeCloseTo(5, 9);
  });

  it('lands on a wall when aimed dead at the corner of the notch', () => {
    // From (0, -1) towards (2, 1): the corner where the two walls of the notch meet.
    const surface: BeamSurface = { x: 0, y: 0, z: 0, d: 0 };
    expect(beamLanding(0, 4, -1, level(1, 1), room, longest, surface)).toBeCloseTo(Math.hypot(2, 2), 6);
    expect(Math.abs(surface.x) + Math.abs(surface.z)).toBe(1);
    // And at every outer corner.
    for (const corner of L_OUTLINE) {
      const reach = beamLanding(-1, 4, -1, level(corner.x + 1, corner.z + 1), room, 1000);
      expect(reach).toBeLessThanOrEqual(Math.hypot(corner.x + 1, corner.z + 1) + 1e-6);
    }
  });

  it('lands on the floor and the ceiling as it always did', () => {
    const surface: BeamSurface = { x: 0, y: 0, z: 0, d: 0 };
    expect(beamLanding(0, 4, 3, { x: 0, y: -1, z: 0 }, room, longest, surface)).toBeCloseTo(4, 9);
    expect(surface).toEqual({ x: 0, y: 1, z: 0, d: 0 });
    expect(beamLanding(0, 4, 3, { x: 0, y: 1, z: 0 }, room, longest, surface)).toBeCloseTo(venue.layout.ceilingY - 4, 9);
    expect(surface).toEqual({ x: 0, y: 1, z: 0, d: venue.layout.ceilingY });
    // Leaning towards the notch's wall but meeting the floor first.
    const leaning = { x: 0.3, y: -Math.sqrt(1 - 0.09), z: 0 };
    expect(beamLanding(0, 4, 3, leaning, room, longest, surface)).toBeCloseTo(4 / Math.sqrt(1 - 0.09), 9);
    expect(surface).toEqual({ x: 0, y: 1, z: 0, d: 0 });
  });

  it('puts the end of the beam on the plane of the wall it met', () => {
    const cut = buildVenue(STAGE_BOX, [], scannedRoom(L_ROOM), [], CUT_OUTLINE);
    const cutRoom = beamRoom(cut.layout, true, cut.outlineWalls);
    const surface: BeamSurface = { x: 0, y: 0, z: 0, d: 0 };
    // Straight at the wall across the cut corner, which runs at 45 degrees.
    const pointing = level(1, 1);
    const reach = beamLanding(0, 4, 0, pointing, cutRoom, 1000, surface);
    // That wall is the line x + z = 7.
    expect(reach).toBeCloseTo(7 / Math.SQRT2, 9);
    expect(surface.x).toBeCloseTo(-Math.SQRT1_2, 9);
    expect(surface.z).toBeCloseTo(-Math.SQRT1_2, 9);
    expect(surface.y).toBe(0);
    const end = { x: pointing.x * reach, z: pointing.z * reach };
    expect(surface.x * end.x + surface.z * end.z).toBeCloseTo(surface.d, 9);
  });

  it('lets a fixture standing in the notch shine in through the wall in front of it', () => {
    // As with the box: only a wall the beam goes out through stops it.
    expect(beamLanding(4, 4, 3, level(-1, 0), room, 1000)).toBeCloseTo(10, 9);
    // Heading away from the room it meets no wall at all.
    expect(beamLanding(4, 4, 3, level(1, 0), room, 19)).toBe(19);
  });

  it('has no walls to land on with the venue hidden', () => {
    const open = beamRoom(venue.layout, false, venue.outlineWalls);
    expect(open.walls).toBeNull();
    expect(open.outline).toBeUndefined();
    expect(beamLanding(0, 4, 3, level(1, 0), open, 19)).toBe(19);
    // And a box room's beams know nothing of an outline.
    expect(box.outline).toBeUndefined();
    expect(beamRoom(venue.layout, true, [])).toEqual(box);
  });

  it('lands exactly where the box does when the outline is a box', () => {
    // The strongest check that the two ways of meeting a wall agree: a room
    // whose outline is its own box, tried from many places in it in many
    // directions. Inside the room only: from outside, the box takes each wall
    // for a plane with no ends, and a beam can land on one beyond where the
    // wall is; an outline's wall ends at its corners.
    const { wallX, backZ, houseZ } = venue.layout;
    const square = outlineWalls([
      { x: -wallX, z: backZ }, { x: wallX, z: backZ }, { x: wallX, z: houseZ }, { x: -wallX, z: houseZ },
    ]);
    const asOutline: BeamRoom = { ...box, outline: square };
    const a: BeamSurface = { x: 0, y: 0, z: 0, d: 0 };
    const b: BeamSurface = { x: 0, y: 0, z: 0, d: 0 };
    let compared = 0;
    for (const x of [-5.9, -5.5, -2, 0, 3.3, 5.9]) {
      for (const z of [-4.9, -3, -1, 0, 2.2, 4.4]) {
        for (let turn = 0; turn < 360; turn += 17) {
          for (const tilt of [-80, -30, -5, 0, 4, 40]) {
            const lean = Math.cos((tilt * Math.PI) / 180);
            const pointing = {
              x: lean * Math.sin((turn * Math.PI) / 180),
              y: Math.sin((tilt * Math.PI) / 180),
              z: lean * Math.cos((turn * Math.PI) / 180),
            };
            const want = beamLanding(x, 3, z, pointing, box, 1000, a);
            const got = beamLanding(x, 3, z, pointing, asOutline, 1000, b);
            expect(got).toBeCloseTo(want, 9);
            // The same plane, whichever way its normal is written.
            const flip = a.x * b.x + a.y * b.y + a.z * b.z < 0 ? -1 : 1;
            expect(b.x * flip).toBeCloseTo(a.x, 9);
            expect(b.y * flip).toBeCloseTo(a.y, 9);
            expect(b.z * flip).toBeCloseTo(a.z, 9);
            expect(b.d * flip).toBeCloseTo(a.d, 9);
            compared += 1;
          }
        }
      }
    }
    expect(compared).toBeGreaterThan(4000);
  });
});

describe('the layout of a room that is not a box', () => {
  it('carries one outline for everything to read, and none for a box', () => {
    const venue = lVenue();
    expect(venue.outline).toEqual(L_OUTLINE);
    expect(venue.outlineWalls).toHaveLength(6);
    // The box round it is the room's box, as it was.
    expect([venue.layout.wallX, venue.layout.backZ, venue.layout.houseZ]).toEqual([6, -5, 5]);
    const box = buildVenue(STAGE_BOX, [], scannedRoom(L_ROOM));
    expect(box.outline).toBeNull();
    expect(box.outlineWalls).toEqual([]);
    expect(box.layout).toEqual(venue.layout);
    // An outline is the outline of a known room: with no room there is none.
    expect(buildVenue(STAGE_BOX, [], null, [], L_OUTLINE).outline).toBeNull();
    expect(buildVenue(STAGE_BOX, [], scannedRoom(L_ROOM), [], []).outline).toBeNull();
  });

  it('brackets a fixture to the wall of the notch it is against', () => {
    // 0.1 m off the wall down the notch, which the box knows nothing of.
    const against = head(1, 1.9, 3, 3);
    expect(lVenue([against]).mounts.get(1)).toEqual({ type: 'wall', dirX: 1, dirZ: 0, reach: expect.closeTo(0.1, 9) });
    expect(buildVenue(STAGE_BOX, [against], scannedRoom(L_ROOM)).mounts.get(1)?.type).not.toBe('wall');
    // And to the wall across it, facing downstage.
    expect(lVenue([head(2, 4, 3, 0.85)]).mounts.get(2)).toEqual({ type: 'wall', dirX: 0, dirZ: 1, reach: expect.closeTo(0.15, 9) });
    // The outer walls still take one, the downstage wall now among them.
    expect(lVenue([head(3, -5.9, 3, 0)]).mounts.get(3)).toMatchObject({ type: 'wall', dirX: -1, dirZ: 0 });
    expect(lVenue([head(4, 0, 3, 4.9)]).mounts.get(4)).toMatchObject({ type: 'wall', dirX: 0, dirZ: 1 });
    // Level with a wall but past its end, a fixture is not against it.
    expect(lVenue([head(5, 1.9, 3, 0)]).mounts.get(5)?.type).not.toBe('wall');
  });

  it('stops a truss at the wall of the notch', () => {
    const row = [head(1, -3, 4, 3), head(2, -1, 4, 3), head(3, 1.6, 4, 3)];
    const [truss] = lVenue(row).trussRows;
    expect(truss.xMin).toBeCloseTo(-3.5, 9);
    // 0.05 m short of the wall at x = 2, where the box ran it on half a metre.
    expect(truss.xMax).toBeCloseTo(1.95, 9);
    expect(buildVenue(STAGE_BOX, row, scannedRoom(L_ROOM)).trussRows[0].xMax).toBeCloseTo(2.1, 9);
    // Upstage of the notch it runs on to the outer wall as before.
    const upstage = row.map((fixture) => ({ ...fixture, z: -2, x: fixture.x + 4 }));
    expect(lVenue(upstage).trussRows[0].xMax).toBeCloseTo(5.95, 9);
  });
});

describe('walls moving out for a fixture beyond them', () => {
  it('moves one wall straight out, its ends sliding along the walls either side', () => {
    // The wall across the notch, a metre further downstage.
    expect(moveWallOut(L_OUTLINE, 2, 1)).toEqual([
      { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 2 }, { x: 2, z: 2 }, { x: 2, z: 5 }, { x: -6, z: 5 },
    ]);
    // The same wall with the corners written the other way round.
    const backwards = [...L_OUTLINE].reverse();
    const moved = moveWallOut(backwards, 2, 1) as OutlinePoint[];
    expect(outlineArea(moved)).toBeCloseTo(-(104 + 4), 9);
    expect(insideOutline(moved, 4, 1.5)).toBe(true);
    // An outer wall: the room grows.
    expect(outlineBox(moveWallOut(L_OUTLINE, 0, 2) as OutlinePoint[]).zMin).toBe(-7);
    // A wall at an angle moves square to itself.
    const cut = moveWallOut(CUT_OUTLINE, 2, Math.SQRT2) as OutlinePoint[];
    expect(cut[2].x).toBeCloseTo(6, 9);
    expect(cut[2].z).toBeCloseTo(3, 9);
    expect(cut[3].x).toBeCloseTo(4, 9);
    expect(cut[3].z).toBeCloseTo(5, 9);
  });

  it('steps out beside a wall that runs the same way', () => {
    // A square with a corner half way along its downstage wall.
    const square = [{ x: 0, z: 0 }, { x: 4, z: 0 }, { x: 4, z: 4 }, { x: 2, z: 4 }, { x: 0, z: 4 }];
    expect(moveWallOut(square, 2, 1)).toEqual([
      { x: 0, z: 0 }, { x: 4, z: 0 }, { x: 4, z: 5 }, { x: 2, z: 5 }, { x: 2, z: 4 }, { x: 0, z: 4 },
    ]);
  });

  it('refuses a move that would leave no room', () => {
    // The wall down the notch is 4 m long: the wall across it cannot go that far.
    expect(moveWallOut(L_OUTLINE, 2, 4)).toBeNull();
    expect(moveWallOut(L_OUTLINE, 2, 6)).toBeNull();
    expect(moveWallOut(L_OUTLINE, 2, 0)).toBeNull();
    expect(moveWallOut(L_OUTLINE, 9, 1)).toBeNull();
    // The cut corner can be moved out until it is a corner, and no further.
    expect(moveWallOut(CUT_OUTLINE, 2, 3)).toBeNull();
  });

  it('leaves the outline alone when every fixture is inside it', () => {
    const inside = [{ x: 0, z: 0 }, { x: -5.9, z: 4.9 }, { x: 5, z: 0 }];
    expect(outlineAround(L_OUTLINE, inside)).toBe(L_OUTLINE);
    expect(outlineAround(L_OUTLINE, [])).toBe(L_OUTLINE);
    expect(outlineAround(L_OUTLINE, [{ x: Number.NaN, z: 0 }])).toBe(L_OUTLINE);
  });

  it('moves the nearest wall out to just past a fixture outside the room', () => {
    // 0.5 m into the notch from the wall across it.
    const around = outlineAround(L_OUTLINE, [{ x: 4, z: 1.5 }]);
    expect(around).toEqual([
      { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1.65 }, { x: 2, z: 1.65 }, { x: 2, z: 5 }, { x: -6, z: 5 },
    ]);
    // Beyond an outer wall, as the box's wall moves.
    const wide = outlineAround(L_OUTLINE, [{ x: -7, z: 0 }]);
    expect(outlineBox(wide).xMin).toBeCloseTo(-7.15, 9);
    // Beyond a corner it is outside two walls, and both move.
    const corner = outlineAround(L_OUTLINE, [{ x: -6.5, z: -5.5 }]);
    expect(outlineBox(corner).xMin).toBeCloseTo(-6.65, 9);
    expect(outlineBox(corner).zMin).toBeCloseTo(-5.65, 9);
    expect(insideOutline(corner, -6.5, -5.5)).toBe(true);
    // Every one of them is still a room, and holds the fixture.
    for (const moved of [around, wide, corner]) {
      expect(outlineCrossesItself(moved)).toBe(false);
      expect(outlineArea(moved)).toBeGreaterThan(104);
    }
  });

  it('leaves a fixture outside when no wall can be moved for it', () => {
    // Right in the cut-off corner: the angled wall would have to go past where
    // the walls either side of it meet.
    expect(outlineAround(CUT_OUTLINE, [{ x: 5.9, z: 4.9 }])).toBe(CUT_OUTLINE);
    // And it does not stop the walls moving for another fixture.
    const mixed = outlineAround(CUT_OUTLINE, [{ x: 5.9, z: 4.9 }, { x: -7, z: 0 }]);
    expect(outlineBox(mixed).xMin).toBeCloseTo(-7.15, 9);
    expect(insideOutline(mixed, 5.9, 4.9)).toBe(false);
  });

  it('is the outline the whole venue then goes by', () => {
    // A fixture half a metre into the notch.
    const fixture = head(1, 4, 4, 1.5);
    const venue = lVenue([fixture]);
    expect(venue.outline).toEqual(outlineAround(L_OUTLINE, [{ x: 4, z: 1.5 }]));
    expect(insideOutline(venue.outline as OutlinePoint[], 4, 1.5)).toBe(true);
    // The scan's own outline is not changed by it.
    expect(roomOutline(L_ROOM)).toEqual(L_OUTLINE);
    // A beam from upstage now lands on the wall where it was moved to.
    const room = beamRoom(venue.layout, true, venue.outlineWalls);
    expect(beamLanding(4, 4, 0, { x: 0, y: 0, z: 1 }, room, 1000)).toBeCloseTo(1.65, 9);
    // The fixture is 0.15 m from that wall, and is bracketed to it.
    expect(venue.mounts.get(1)).toEqual({ type: 'wall', dirX: 0, dirZ: 1, reach: expect.closeTo(0.15, 9) });
    // A fixture beyond the box moves the box's wall too, so the two agree.
    const wide = lVenue([head(2, -7, 4, 0)]);
    expect(wide.layout.wallX).toBeCloseTo(7.15, 9);
    expect(outlineBox(wide.outline as OutlinePoint[]).xMin).toBeCloseTo(-7.15, 9);
  });

  it('does not move a wall the scan measured for a position nobody has confirmed', () => {
    // A scan's suggestion brings a row inside the room's box, which can leave
    // a guess in the notch. It is drawn there, outside the wall, as a guess.
    const guess = { ...head(1, 4, 4, 1.5), guess: true };
    const venue = lVenue([guess]);
    expect(venue.outline).toEqual(L_OUTLINE);
    const room = beamRoom(venue.layout, true, venue.outlineWalls);
    expect(beamLanding(4, 4, 0, { x: 0, y: 0, z: 1 }, room, 1000)).toBeCloseTo(1, 9);
    // The same fixture once somebody has confirmed where it is.
    expect(lVenue([{ ...guess, guess: false }]).outline).not.toEqual(L_OUTLINE);
    // With a confirmed fixture beside it, the wall moves for that one only.
    const both = lVenue([guess, head(2, 3, 4, 1.2)]);
    expect(both.outline).toEqual(outlineAround(L_OUTLINE, [{ x: 3, z: 1.2 }]));
    expect(insideOutline(both.outline as OutlinePoint[], 4, 1.5)).toBe(false);
  });
});

describe('how far a fixture may be dragged in a room that is not a box', () => {
  const rig = { stage_width: 16, stage_depth: 14, stage_height: 6, room_shell: DEEP_ROOM };
  const limits = positionLimits(rig);

  // (put at) -> (held at), x and z. The same table as
  // backend/tests/unit/test_fixture_position_outline.py: change one, change
  // both, or a fixture jumps when it is dropped.
  const HELD: Array<[[number, number], [number, number]]> = [
    // Inside the room: left alone.
    [[-5, 3], [-5, 3]],
    [[6, -4], [6, -4]],
    // In the notch but within 2 m of a wall of it: left alone.
    [[0, 0], [0, 0]],
    [[-0.5, 6], [-0.5, 6]],
    // Deep in the notch: back to 2 m from the nearest wall of it.
    [[4, 4], [4, 1]],
    [[7, 6.5], [7, 1]],
    [[3, 5], [0, 5]],
    // Beyond the outer walls: 2 m out, as for a box.
    [[-20, 0], [-10, 0]],
    [[0, -30], [0, -9]],
    // Beyond an outer corner: 2 m from the corner itself.
    [[20, -19], [9.414, -8.414]],
  ];

  it('carries the outline in the limits, and none for a box room', () => {
    expect(limits).toEqual({ halfX: 10, halfZ: 9, top: 8, outline: DEEP_OUTLINE });
    const box = positionLimits({ ...rig, room_shell: { ...DEEP_ROOM, room: { width: 16, depth: 14, height: 6 } } });
    expect(box).toEqual({ halfX: 10, halfZ: 9, top: 8 });
    expect('outline' in box).toBe(false);
  });

  it('holds a position to within the margin of the room itself', () => {
    expect(OUTSIDE_MARGIN_M).toBe(2);
    for (const [[x, z], [heldX, heldZ]] of HELD) {
      const held = clampPosition({ x, y: 4, z }, limits);
      expect(held.x).toBeCloseTo(heldX, 3);
      expect(held.z).toBeCloseTo(heldZ, 3);
      expect(held.y).toBe(4);
      // Held, it is never more than the margin from the room.
      expect(outlineClearance(DEEP_OUTLINE, held.x, held.z)).toBeGreaterThanOrEqual(-OUTSIDE_MARGIN_M - 1e-9);
      // And holding it again moves it no further.
      const again = clampPosition(held, limits);
      expect(again.x).toBeCloseTo(held.x, 9);
      expect(again.z).toBeCloseTo(held.z, 9);
    }
  });

  it('holds it the same with the corners written the other way round', () => {
    const backwards = { ...limits, outline: [...DEEP_OUTLINE].reverse() };
    for (const [[x, z], [heldX, heldZ]] of HELD) {
      const held = clampPosition({ x, y: 4, z }, backwards);
      expect(held.x).toBeCloseTo(heldX, 3);
      expect(held.z).toBeCloseTo(heldZ, 3);
    }
  });

  it('where the box alone let the fixture stay deep in the notch', () => {
    const box = { halfX: limits.halfX, halfZ: limits.halfZ, top: limits.top };
    expect(clampPosition({ x: 4, y: 4, z: 4 }, box)).toEqual({ x: 4, y: 4, z: 4 });
    expect(holdNearOutline(DEEP_OUTLINE, 4, 4, 2)).toEqual({ x: 4, z: 1 });
    expect(holdNearOutline(DEEP_OUTLINE, 4, 4, 0.5)).toEqual({ x: 4, z: -0.5 });
  });

  it('holds a drag and a nudge alike, and the height as before', () => {
    const state = { ...beginDrag({ x: 4, y: 4, z: 4 }), mode: 'plan' as const };
    expect(settleDrag(state, 0, limits, null)).toMatchObject({ x: 4, y: 4, z: 1 });
    // Nudged a metre further into the notch from 2 m in, it stays 2 m in.
    expect(nudgePosition({ x: 4, y: 4, z: 1 }, 'ArrowDown', true, limits)).toEqual({ x: 4, y: 4, z: 1 });
    // Along the wall it is free to go.
    expect(nudgePosition({ x: 4, y: 4, z: 1 }, 'ArrowRight', true, limits)).toEqual({ x: 5, y: 4, z: 1 });
    expect(clampPosition({ x: 0, y: 99, z: 0 }, limits).y).toBe(8);
    expect(clampPosition({ x: 0, y: -1, z: 0 }, limits).y).toBe(0);
  });

  it('leaves every part of a 4 m notch within reach, being within 2 m of a wall', () => {
    // Said plainly, because it is easy to expect otherwise: the margin is 2 m
    // each side of every wall, so a notch 4 m across is all within it.
    const small = positionLimits({ stage_width: 12, stage_depth: 10, stage_height: 5, room_shell: L_ROOM });
    expect(clampPosition({ x: 4, y: 3, z: 3 }, small)).toEqual({ x: 4, y: 3, z: 3 });
  });
});

describe('the cameras in a room that is not a box', () => {
  const MODES: CameraMode[] = ['iso', 'top', 'front', 'audience', 'dj', 'floor'];

  it('leaves every preset as it was where it is already inside the room', () => {
    // The middle of the L and its dance floor are in the room.
    const { layout, outline } = lVenue();
    for (const mode of MODES) {
      expect(cameraPreset(mode, layout, outline)).toEqual(cameraPreset(mode, layout));
    }
    // And a box room is given no outline at all.
    expect(cameraPreset('floor', layout, null)).toEqual(cameraPreset('floor', layout));
  });

  const deep = buildVenue(DEEP_STAGE, [], scannedRoom(DEEP_ROOM), [], roomOutline(DEEP_ROOM));
  const outline = deep.outline as OutlinePoint[];

  it('looks at a point in the room, not in the notch', () => {
    for (const mode of ['iso', 'front', 'audience', 'dj', 'floor'] as CameraMode[]) {
      const boxed = cameraPreset(mode, deep.layout);
      const preset = cameraPreset(mode, deep.layout, outline);
      if (mode === 'floor') {
        // It looks at the upstage wall, which is in the room: the same point as before.
        expect(preset.target).toEqual(boxed.target);
      } else {
        // The box's own target is in the notch, outside the walls.
        expect(insideOutline(outline, boxed.target[0], boxed.target[2])).toBe(false);
      }
      expect(outlineClearance(outline, preset.target[0], preset.target[2])).toBeGreaterThanOrEqual(CAMERA_WALL_CLEARANCE);
      // Its height, lens and tilt limit are the box preset's.
      expect(preset.target[1]).toBe(boxed.target[1]);
      expect(preset.position[1]).toBe(boxed.position[1]);
      expect([preset.fov, preset.maxPolar]).toEqual([boxed.fov, boxed.maxPolar]);
    }
  });

  it('carries the camera along with what it looks at, so the view is the same view', () => {
    for (const mode of ['iso', 'front', 'audience'] as CameraMode[]) {
      const boxed = cameraPreset(mode, deep.layout);
      const preset = cameraPreset(mode, deep.layout, outline);
      for (const axis of [0, 1, 2]) {
        expect(preset.position[axis] - preset.target[axis]).toBeCloseTo(boxed.position[axis] - boxed.target[axis], 9);
      }
    }
  });

  it('stands the dance-floor camera in the room', () => {
    const boxed = cameraPreset('floor', deep.layout);
    expect(insideOutline(outline, boxed.position[0], boxed.position[2])).toBe(false);
    const preset = cameraPreset('floor', deep.layout, outline);
    expect(outlineClearance(outline, preset.position[0], preset.position[2])).toBeGreaterThanOrEqual(CAMERA_WALL_CLEARANCE);
  });

  it('stands the DJ camera a metre behind the wall upstage of what it looks at', () => {
    const preset = cameraPreset('dj', deep.layout, outline);
    const [x, , z] = preset.position;
    expect(insideOutline(outline, x, z)).toBe(false);
    // A metre downstage of it is the wall, and the room is beyond that.
    expect(nearestOnOutline(outline, x, z).distance).toBeCloseTo(1, 9);
    expect(insideOutline(outline, x, z + 1.5)).toBe(true);
    expect(preset.target[2]).toBeGreaterThan(z + 1);
  });

  it('leaves the top view over the middle of the room\'s box', () => {
    expect(cameraPreset('top', deep.layout, outline)).toEqual(cameraPreset('top', deep.layout));
  });
});

describe('the ceiling of a room that is not a box', () => {
  it('runs its beams across the room and stops them at the notch', () => {
    const runs = outlineBeamRuns(L_OUTLINE);
    // Five beams over 10 m, as the box room has: the first and last along the end walls.
    expect(runs.map((run) => run.z)).toEqual([-4.91, -2.5, 0, 2.5, 4.91]);
    expect(runs.map((run) => [run.xMin, run.xMax])).toEqual([[-6, 6], [-6, 6], [-6, 6], [-6, 2], [-6, 2]]);
  });

  it('cuts a beam short where a wall runs at an angle, by its nearer edge', () => {
    const runs = outlineBeamRuns(CUT_OUTLINE);
    const downstage = runs.find((run) => run.z === 2.5)!;
    // The cut wall is x + z = 7; the beam's downstage edge, at z = 2.58, meets it first.
    expect(downstage.xMax).toBeCloseTo(7 - 2.58, 9);
    for (const run of runs) {
      for (const z of [run.z - 0.079, run.z + 0.079]) {
        expect(insideOutline(CUT_OUTLINE, run.xMin + 1e-6, z)).toBe(true);
        expect(insideOutline(CUT_OUTLINE, run.xMax - 1e-6, z)).toBe(true);
      }
    }
  });

  it('runs a beam in two parts either side of a notch in the middle', () => {
    const downstage = outlineBeamRuns(U_OUTLINE).filter((run) => run.z === 2.5);
    expect(downstage.map((run) => [run.xMin, run.xMax])).toEqual([[-6, -2], [2, 6]]);
  });

  it('hangs the duct down one side, short of the walls at both ends', () => {
    const [duct, ...more] = outlineDuctRuns(L_OUTLINE);
    expect(more).toEqual([]);
    expect(duct.x).toBeCloseTo(-3.96, 9);
    expect(duct.zMin).toBeCloseTo(-4.3, 9);
    expect(duct.zMax).toBeCloseTo(4.3, 9);
  });

  it('builds them under the ceiling and inside the walls', () => {
    const dressing = buildOutlineCeilingDressing(L_OUTLINE, 5) as THREE.BufferGeometry;
    const points = vertices(dressing);
    expect(points.length).toBeGreaterThan(100);
    for (const v of points) {
      expect(v.y).toBeLessThanOrEqual(5 + 1e-6);
      expect(v.y).toBeGreaterThan(5 - 0.34);
      expect(Math.abs(v.x)).toBeLessThanOrEqual(6 + 1e-6);
      expect(Math.abs(v.z)).toBeLessThanOrEqual(5 + 1e-6);
      // Nothing hangs in the notch.
      expect(v.x > 2 + 1e-4 && v.z > 1 + 1e-4).toBe(false);
    }
    // A room too small for either has none.
    expect(buildOutlineCeilingDressing([{ x: 0, z: 0 }, { x: 0.04, z: 0 }, { x: 0.04, z: 0.04 }], 3)).toBeNull();
  });
});
