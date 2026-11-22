// A scanned room that is not a box, truss at an angle and rings of truss:
// how the 3D view draws them and how a dragged fixture snaps to them.
// The shells are as backend/app/services/room_scan/extract.py writes them for
// the rooms backend/tests/unit/room_scan_meshes.py builds. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { buildVenue, hangerDistance, hangsFrom } from '../components/rig/previs/layout';
import type { Hanger, LayoutFixture } from '../components/rig/previs/layout';
import {
  buildOutlineFlat,
  buildOverheadLines,
  buildTrussRings,
  insideOutline,
  lineAlreadyDrawn,
  onRoomSide,
  outlineArea,
  outlineWalls,
  roomOutline,
  runsAcross,
  scanHangers,
  scanRings,
  scannedRoom,
  usableRing,
} from '../components/rig/previs/roomShell';
import {
  SNAP_RADIUS_M,
  beginDrag,
  nearestOnRing,
  nearestOnTarget,
  positionText,
  settleDrag,
  snapLines,
  snapToLines,
} from '../components/rig/previs/fixtureDrag';
import { foundLines, lineRunText } from '../utils/roomScan';
import type { RoomScanPreview } from '../utils/roomScan';
import type { RoomShell, RoomShellLine, RoomShellRing } from '../types';

// An L: 12 m by 10 m with its downstage stage-left corner (4 m by 4 m) walled
// off. Corners clockwise seen from above, from upstage stage right.
const L_OUTLINE = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];
const L_AREA = 12 * 10 - 4 * 4;

// 8 m long, 30 degrees clockwise from across the room, centred on (1, 0.5).
const HALF_X = 4 * Math.cos(Math.PI / 6);
const HALF_Z = 4 * Math.sin(Math.PI / 6);
const ANGLED: RoomShellLine = {
  name: 'Overhead line 1',
  x1: 1 - HALF_X, z1: 0.5 - HALF_Z, x2: 1 + HALF_X, z2: 0.5 + HALF_Z,
  height: 4, top: 4.3, length: 8, across: 0.3, axis: 'angled', heading_deg: 30, suggested: true,
};
const RING: RoomShellRing = {
  name: 'Overhead ring 1', center_x: 0.5, center_z: 1, radius: 4, height: 4.8, top: 5.1, across: 0.3, suggested: true,
};

const SHAPED: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 16, depth: 14, height: 6, suggested: true },
  risers: [],
  truss_lines: [ANGLED],
  truss_rings: [RING],
  hanging_bands: [{ height: 4, lines: 1, rings: 0 }, { height: 4.8, lines: 0, rings: 1 }],
};
const L_ROOM: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 10, height: 5, outline: L_OUTLINE, suggested: true },
  risers: [],
  truss_lines: [],
  truss_rings: [],
};
// As stored before any of this was read: no outline, no rings, no heading.
const OLD: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 9, height: 5, suggested: true },
  risers: [{ center_x: -1.5, center_z: -3.25, width: 6, depth: 2.5, height: 0.9, name: 'Stage', kind: 'stage' }],
  truss_lines: [{ name: 'Overhead line 1', x1: -4, z1: 0.5, x2: 4, z2: 0.5, height: 4, top: 4.3, length: 8, across: 0.3, axis: 'x' }],
  hanging_bands: [{ height: 4, top: 4.3, lines: 1 }],
};

const STAGE_BOX = { width: 12, depth: 10, height: 8 };

function vertices(geometry: THREE.BufferGeometry): THREE.Vector3[] {
  const position = geometry.getAttribute('position');
  return Array.from({ length: position.count }, (_, i) => new THREE.Vector3().fromBufferAttribute(position, i));
}

function bounds(geometry: THREE.BufferGeometry): THREE.Box3 {
  geometry.computeBoundingBox();
  return geometry.boundingBox as THREE.Box3;
}

/** The area of a flat geometry, from its triangles. */
function triangleArea(geometry: THREE.BufferGeometry): number {
  const points = vertices(geometry);
  let area = 0;
  for (let i = 0; i + 2 < points.length; i += 3) {
    area += new THREE.Triangle(points[i], points[i + 1], points[i + 2]).getArea();
  }
  return area;
}

function preview(shell: RoomShell): RoomScanPreview {
  return {
    rig_id: 7, rig_name: 'Club', file: 'club.obj', format: 'obj', room_shell: shell,
    replaces_existing_shell: false,
    summary: {
      width: 16, depth: 14, height: 6, raised_areas: 0, overhead_lines: 1, overhead_rings: 1, walls: 4,
      hanging_heights: [4, 4.8], units: 'm', up_axis: 'y',
    },
    assumptions: [], warnings: [],
    fixtures: { total: 0, unconfirmed: 0, would_move: 0, moves: [] },
    operator_guide: 'docs/ROOM_SCAN.md', applied: null,
  };
}

describe('a truss at an angle in the 3D view', () => {
  it('draws the bar along the line it was found on, not along the room', () => {
    const bar = buildOverheadLines([ANGLED]) as THREE.BufferGeometry;
    const length = Math.hypot(ANGLED.x2 - ANGLED.x1, ANGLED.z2 - ANGLED.z1);
    const alongX = (ANGLED.x2 - ANGLED.x1) / length;
    const alongZ = (ANGLED.z2 - ANGLED.z1) / length;
    let nearStart = Infinity;
    let nearEnd = Infinity;
    for (const v of vertices(bar)) {
      // Every corner of the bar is within half its width of the line. A bar
      // turned the other way round has the same bounding box and fails this.
      const off = Math.abs((v.x - ANGLED.x1) * -alongZ + (v.z - ANGLED.z1) * alongX);
      expect(off).toBeLessThan(0.15 + 1e-4);
      expect(v.y).toBeGreaterThan(4 - 1e-4);
      expect(v.y).toBeLessThan(4.3 + 1e-4);
      nearStart = Math.min(nearStart, Math.hypot(v.x - ANGLED.x1, v.z - ANGLED.z1));
      nearEnd = Math.min(nearEnd, Math.hypot(v.x - ANGLED.x2, v.z - ANGLED.z2));
    }
    expect(nearStart).toBeCloseTo(0.15, 3);
    expect(nearEnd).toBeCloseTo(0.15, 3);
  });

  it('draws it the same whichever end the line is written from', () => {
    const forwards = bounds(buildOverheadLines([ANGLED]) as THREE.BufferGeometry);
    const backwards = bounds(buildOverheadLines([
      { ...ANGLED, x1: ANGLED.x2, z1: ANGLED.z2, x2: ANGLED.x1, z2: ANGLED.z1 },
    ]) as THREE.BufferGeometry);
    expect(backwards.min.distanceTo(forwards.min)).toBeLessThan(1e-4);
    expect(backwards.max.distanceTo(forwards.max)).toBeLessThan(1e-4);
  });

  it('is never taken for the truss the view hangs across the room', () => {
    expect(runsAcross(ANGLED)).toBe(false);
    // Ten degrees off: its run in X is still far the longer, and it is still not across.
    const shallow: RoomShellLine = { x1: -4, z1: 0, x2: 4, z2: 1.41, height: 4 };
    expect(runsAcross(shallow)).toBe(false);
    const under = { z: 0.7, chordY: 4.45, xMin: -3.5, xMax: 3.5 };
    expect(lineAlreadyDrawn(shallow, [under])).toBe(false);
    expect(lineAlreadyDrawn(ANGLED, [{ ...under, z: 0.5 }])).toBe(false);
    // One degree off is a truss across the room that the scan read a little crooked.
    expect(runsAcross({ x1: -4, z1: 0.5, x2: 4, z2: 0.64, height: 4 })).toBe(true);
  });

  it('clamps the fixtures under it to it, with no truss of the view\'s own', () => {
    const fixtures: LayoutFixture[] = [0.125, 0.375, 0.625, 0.875].map((share, index) => ({
      id: index + 1,
      x: ANGLED.x1 + (ANGLED.x2 - ANGLED.x1) * share,
      y: 4,
      z: ANGLED.z1 + (ANGLED.z2 - ANGLED.z1) * share,
      kind: 'moving_head',
      hasPanTilt: true,
    }));
    const room = scannedRoom(SHAPED);
    // Without the room's own truss the view hangs one short run across the room over each.
    expect(buildVenue(STAGE_BOX, fixtures, room).trussRows.length).toBeGreaterThan(1);
    const hung = buildVenue(STAGE_BOX, fixtures, room, scanHangers(SHAPED));
    expect(hung.trussRows).toEqual([]);
    expect(fixtures.map((f) => hung.mounts.get(f.id))).toEqual(Array(4).fill({ type: 'truss', drop: 0 }));
  });
});

describe('a ring of truss in the 3D view', () => {
  it('draws a flat ring where the scan found one', () => {
    const ring = buildTrussRings([RING]) as THREE.BufferGeometry;
    for (const v of vertices(ring)) {
      const out = Math.hypot(v.x - RING.center_x, v.z - RING.center_z);
      expect(out).toBeGreaterThan(3.85 - 1e-3);
      expect(out).toBeLessThan(4.15 + 1e-3);
      expect(v.y).toBeGreaterThan(4.8 - 1e-4);
      expect(v.y).toBeLessThan(5.1 + 1e-4);
    }
    const box = bounds(ring);
    expect(box.min.x).toBeCloseTo(0.5 - 4.15, 2);
    expect(box.max.x).toBeCloseTo(0.5 + 4.15, 2);
    expect(box.min.z).toBeCloseTo(1 - 4.15, 2);
    expect(box.max.z).toBeCloseTo(1 + 4.15, 2);
    expect(buildTrussRings([])).toBeNull();
  });

  it('draws a ring with no width or top given, and passes over one that is not a ring', () => {
    const plain = bounds(buildTrussRings([{ center_x: 0, center_z: 0, radius: 2, height: 3 }]) as THREE.BufferGeometry);
    expect(plain.min.y).toBeCloseTo(3, 4);
    expect(plain.max.y).toBeCloseTo(3.3, 4);
    expect(plain.max.x).toBeCloseTo(2.15, 2);
    expect(usableRing(RING)).toBe(true);
    expect(usableRing({ ...RING, radius: 0 })).toBe(false);
    expect(usableRing({ ...RING, height: Number.NaN })).toBe(false);
    expect(usableRing(undefined)).toBe(false);
    expect(scanRings({ ...SHAPED, truss_rings: [RING, { ...RING, radius: -1 }] })).toEqual([RING]);
    expect(scanRings(OLD)).toEqual([]);
  });

  it('clamps the fixtures round it to it, with no truss of the view\'s own', () => {
    const fixtures: LayoutFixture[] = Array.from({ length: 8 }, (_, k) => ({
      id: k + 1,
      x: RING.center_x + RING.radius * Math.sin((k * Math.PI) / 4),
      y: RING.height,
      z: RING.center_z - RING.radius * Math.cos((k * Math.PI) / 4),
      kind: 'moving_head' as const,
      hasPanTilt: true,
    }));
    const room = scannedRoom(SHAPED);
    expect(buildVenue(STAGE_BOX, fixtures, room).trussRows.length).toBeGreaterThan(2);
    const hung = buildVenue(STAGE_BOX, fixtures, room, scanHangers(SHAPED));
    expect(hung.trussRows).toEqual([]);
    expect(hung.mounts.get(1)).toEqual({ type: 'truss', drop: 0 });

    // A fixture in the middle of the ring is not on it, and gets the view's truss as before.
    const middle: LayoutFixture = { id: 99, x: 0.5, y: 4.8, z: 1, kind: 'moving_head', hasPanTilt: true };
    const mixed = buildVenue(STAGE_BOX, [...fixtures, middle], room, scanHangers(SHAPED));
    expect(mixed.trussRows).toHaveLength(1);
    // Nor is one under the ring but far below it.
    const low: LayoutFixture = { ...fixtures[0], id: 98, y: 3.5 };
    expect(buildVenue(STAGE_BOX, [low], room, scanHangers(SHAPED)).trussRows).toHaveLength(1);
  });

  it('measures how far a fixture is from a hanger', () => {
    const [line, ring] = scanHangers(SHAPED);
    expect(line.kind).toBe('line');
    expect(ring).toEqual({ kind: 'ring', centerX: 0.5, centerZ: 1, radius: 4, height: 4.8 });
    expect(hangerDistance(ring, 0.5, 1)).toBeCloseTo(4, 6);
    expect(hangerDistance(ring, 4.7, 1)).toBeCloseTo(0.2, 6);
    expect(hangerDistance(line, 1, 0.5)).toBeCloseTo(0, 6);
    // Past the end of the line the distance is to its end.
    expect(hangerDistance(line, ANGLED.x2 + 3, ANGLED.z2)).toBeCloseTo(3, 6);
    expect(hangsFrom([ring], { x: 4.5, y: 4.8, z: 1 })).toBe(true);
    expect(hangsFrom([ring], { x: 4.5, y: 3.9, z: 1 })).toBe(false);
    expect(hangsFrom([], { x: 4.5, y: 4.8, z: 1 })).toBe(false);
  });

  it('offers no hangers for a room that was not scanned, or one with only truss across it', () => {
    expect(scanHangers(null)).toEqual([]);
    expect(scanHangers({ ...SHAPED, source: 'preset' })).toEqual([]);
    expect(scanHangers(OLD)).toEqual([]);
    const none: Hanger[] = [];
    const fixture: LayoutFixture = { id: 1, x: 0, y: 4, z: 0.5, kind: 'moving_head', hasPanTilt: true };
    expect(buildVenue(STAGE_BOX, [fixture], scannedRoom(OLD), none))
      .toEqual(buildVenue(STAGE_BOX, [fixture], scannedRoom(OLD)));
  });
});

describe('a scanned room that is not a box', () => {
  it('has an outline only when the scan wrote a real one', () => {
    expect(roomOutline(L_ROOM)).toEqual(L_OUTLINE);
    expect(roomOutline(OLD)).toBeNull();
    expect(roomOutline(SHAPED)).toBeNull();
    expect(roomOutline(null)).toBeNull();
    expect(roomOutline({ ...L_ROOM, source: 'preset' })).toBeNull();
    const withOutline = (outline: unknown): RoomShell => (
      { ...L_ROOM, room: { ...L_ROOM.room!, outline: outline as typeof L_OUTLINE } }
    );
    expect(roomOutline(withOutline([]))).toBeNull();
    expect(roomOutline(withOutline(L_OUTLINE.slice(0, 2)))).toBeNull();
    expect(roomOutline(withOutline([...L_OUTLINE.slice(0, 5), { x: Number.NaN, z: 5 }]))).toBeNull();
    expect(roomOutline(withOutline([{ x: 0, z: 0 }, { x: 5, z: 0 }, { x: 10, z: 0 }]))).toBeNull();
    expect(roomOutline(withOutline('L'))).toBeNull();
    // The box round it is still the room every other reader sees.
    expect(scannedRoom(L_ROOM)).toEqual({ width: 12, depth: 10, height: 5 });
  });

  it('stands one wall on each segment of the outline, facing into the room', () => {
    for (const outline of [L_OUTLINE, [...L_OUTLINE].reverse()]) {
      const walls = outlineWalls(outline);
      expect(walls).toHaveLength(6);
      expect(walls.map((wall) => wall.length).sort((a, b) => a - b)).toEqual([4, 4, 6, 8, 10, 12]);
      for (const wall of walls) {
        expect(Math.hypot(wall.inX, wall.inZ)).toBeCloseTo(1, 6);
        expect(insideOutline(outline, wall.midX + 0.1 * wall.inX, wall.midZ + 0.1 * wall.inZ)).toBe(true);
        expect(insideOutline(outline, wall.midX - 0.1 * wall.inX, wall.midZ - 0.1 * wall.inZ)).toBe(false);
        // The view's wall is modelled facing +Z; turned by `yaw` it faces into the room.
        const facing = new THREE.Vector3(0, 0, 1).applyAxisAngle(new THREE.Vector3(0, 1, 0), wall.yaw);
        expect(facing.x).toBeCloseTo(wall.inX, 6);
        expect(facing.z).toBeCloseTo(wall.inZ, 6);
        // And its length runs along the segment.
        const along = new THREE.Vector3(1, 0, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), wall.yaw);
        expect(Math.abs(along.x * (wall.x2 - wall.x1) + along.z * (wall.z2 - wall.z1))).toBeCloseTo(wall.length, 6);
      }
    }
    expect(outlineArea(L_OUTLINE)).toBeCloseTo(L_AREA, 6);
    expect(outlineArea([...L_OUTLINE].reverse())).toBeCloseTo(-L_AREA, 6);
  });

  it('gives the inner walls of the L their own faces', () => {
    const walls = outlineWalls(L_OUTLINE);
    // (6, 1) to (2, 1): the wall across the notch, facing upstage into the room.
    const notch = walls[2];
    expect([notch.x1, notch.z1, notch.x2, notch.z2]).toEqual([6, 1, 2, 1]);
    expect([notch.inX, notch.inZ]).toEqual([0, -1]);
    // (2, 1) to (2, 5): the wall down the notch, facing stage right.
    expect([walls[3].inX, walls[3].inZ]).toEqual([-1, 0]);
  });

  it('shows a wall only to a camera on the room\'s side of it', () => {
    const notch = outlineWalls(L_OUTLINE)[2];
    expect(onRoomSide(notch, 0, 0)).toBe(true);
    expect(onRoomSide(notch, 4, 3)).toBe(false);
    // Outside the room altogether, beyond the upstage wall, it is still facing the camera.
    expect(onRoomSide(notch, 4, -20)).toBe(true);
  });

  it('draws a wall at an angle as one wall', () => {
    const cut = [{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 }];
    const walls = outlineWalls(cut);
    expect(walls).toHaveLength(5);
    const angled = walls[2];
    expect(angled.length).toBeCloseTo(Math.hypot(4, 4), 6);
    expect(angled.inX).toBeCloseTo(-Math.SQRT1_2, 6);
    expect(angled.inZ).toBeCloseTo(-Math.SQRT1_2, 6);
  });

  it('cuts the floor and the ceiling to the outline', () => {
    const floor = buildOutlineFlat(L_OUTLINE, 0, '#333333');
    const box = bounds(floor);
    expect([box.min.x, box.max.x, box.min.z, box.max.z]).toEqual([-6, 6, -5, 5]);
    expect(box.min.y).toBeCloseTo(0, 6);
    expect(box.max.y).toBeCloseTo(0, 6);
    // The notch is not floored over: 104 m2, not the 120 of the box.
    expect(triangleArea(floor)).toBeCloseTo(L_AREA, 3);
    const ceiling = bounds(buildOutlineFlat(L_OUTLINE, 5, '#222222'));
    expect(ceiling.min.y).toBeCloseTo(5, 6);
    expect(ceiling.max.y).toBeCloseTo(5, 6);
  });

  it('tells inside the room from the notch', () => {
    expect(insideOutline(L_OUTLINE, 0, 0)).toBe(true);
    expect(insideOutline(L_OUTLINE, 4, 0)).toBe(true);
    expect(insideOutline(L_OUTLINE, 4, 3)).toBe(false);
    expect(insideOutline(L_OUTLINE, 7, 0)).toBe(false);
  });
});

describe('snapping a dragged fixture to angled truss and rings', () => {
  const targets = snapLines(SHAPED);

  it('offers the angled line and the ring', () => {
    expect(targets.map((target) => target.name)).toEqual(['Overhead line 1', 'Overhead ring 1']);
    expect(targets[1].ring).toEqual({ centerX: 0.5, centerZ: 1, radius: 4 });
    expect(targets[1].kind).toBe('truss');
    // A room with a ring and nothing else still has something to snap to.
    expect(snapLines({ ...SHAPED, truss_lines: [] })).toHaveLength(1);
    expect(snapLines({ ...SHAPED, truss_rings: [{ ...RING, radius: 0 }], truss_lines: [] })).toEqual([]);
  });

  it('puts a fixture dropped beside the angled line onto it, at its height', () => {
    // 0.2 m off the middle of the line, square to it.
    const offX = -Math.sin(Math.PI / 6) * 0.2;
    const offZ = Math.cos(Math.PI / 6) * 0.2;
    const snapped = snapToLines({ x: 1 + offX, y: 4.4, z: 0.5 + offZ }, targets);
    expect(snapped.snappedTo?.name).toBe('Overhead line 1');
    expect(snapped.x).toBeCloseTo(1, 6);
    expect(snapped.z).toBeCloseTo(0.5, 6);
    expect(snapped.y).toBe(4);
    // Where the same offset the other way round would put a mirrored line, nothing is near.
    expect(snapToLines({ x: 1 + HALF_X, y: 4.4, z: 0.5 - HALF_Z }, targets).snappedTo).toBeNull();
  });

  it('puts a fixture dropped just inside or outside the ring onto it, at its height', () => {
    const inside = snapToLines({ x: 0.5 + 3.8, y: 5, z: 1 }, targets);
    expect(inside.snappedTo?.name).toBe('Overhead ring 1');
    expect([inside.x, inside.y, inside.z]).toEqual([4.5, 4.8, 1]);

    // Out along the diagonal, towards downstage stage right.
    const reach = 4.3 * Math.SQRT1_2;
    const outside = snapToLines({ x: 0.5 - reach, y: 4.6, z: 1 + reach }, targets);
    expect(outside.snappedTo?.name).toBe('Overhead ring 1');
    expect(Math.hypot(outside.x - 0.5, outside.z - 1)).toBeCloseTo(4, 6);
    expect(outside.x).toBeCloseTo(0.5 - 4 * Math.SQRT1_2, 6);
    expect(outside.z).toBeCloseTo(1 + 4 * Math.SQRT1_2, 6);
  });

  it('leaves a fixture alone that is too far from the ring, at its centre, or at another height', () => {
    const far = { x: 0.5 + 4 + SNAP_RADIUS_M + 0.05, y: 4.8, z: 1 };
    expect(snapToLines(far, [targets[1]])).toEqual({ ...far, snappedTo: null });
    const centre = { x: 0.5, y: 4.8, z: 1 };
    expect(snapToLines(centre, [targets[1]], 10)).toEqual({ ...centre, snappedTo: null });
    expect(nearestOnRing(0.5, 1, targets[1].ring!)).toBeNull();
    const low = { x: 4.4, y: 2, z: 1 };
    expect(snapToLines(low, [targets[1]]).snappedTo).toBeNull();
  });

  it('measures to a ring or a line through one helper', () => {
    expect(nearestOnTarget(4.7, 1, targets[1])).toEqual({ x: 4.5, z: 1, distance: expect.closeTo(0.2, 6) });
    const onLine = nearestOnTarget(1, 0.5, targets[0]);
    expect(onLine?.distance).toBeCloseTo(0, 6);
  });

  it('settles a drag onto the ring and says so', () => {
    const limits = { halfX: 10, halfZ: 9, top: 8 };
    const state = { ...beginDrag({ x: 0.5, y: 4.9, z: 1 - 4.2 }), mode: 'plan' as const };
    const settled = settleDrag(state, 0, limits, targets);
    expect([settled.x, settled.y, settled.z]).toEqual([0.5, 4.8, -3]);
    expect(positionText(settled, settled.snappedTo)).toBe('x 0.50, height 4.80, z -3.00 m - on Overhead ring 1');
    // With snapping off the fixture stays where it was put.
    expect(settleDrag(state, 0, limits, null).z).toBe(-3.2);
  });
});

describe('a shell stored before outlines, headings and rings', () => {
  it('draws and snaps exactly as it did', () => {
    expect(roomOutline(OLD)).toBeNull();
    expect(scanRings(OLD)).toEqual([]);
    expect(scanHangers(OLD)).toEqual([]);
    expect(buildTrussRings(scanRings(OLD))).toBeNull();
    expect(scannedRoom(OLD)).toEqual({ width: 12, depth: 9, height: 5 });

    const bar = bounds(buildOverheadLines(OLD.truss_lines!) as THREE.BufferGeometry);
    expect([bar.min.x, bar.max.x]).toEqual([-4, 4]);
    expect(bar.min.z).toBeCloseTo(0.35, 6);
    expect(bar.max.z).toBeCloseTo(0.65, 6);
    expect(bar.min.y).toBeCloseTo(4, 6);
    expect(bar.max.y).toBeCloseTo(4.3, 6);
    expect(lineAlreadyDrawn(OLD.truss_lines![0], [{ z: 0.5, chordY: 4.45, xMin: -3.5, xMax: 3.5 }])).toBe(true);

    const targets = snapLines(OLD);
    expect(targets.map((target) => target.name)).toEqual([
      'Overhead line 1', 'Stage, upstage edge', 'Stage, downstage edge', 'Stage, stage right edge', 'Stage, stage left edge',
    ]);
    expect(targets.every((target) => target.ring === undefined)).toBe(true);
    expect(snapToLines({ x: 1, y: 4.2, z: 0.7 }, targets)).toEqual({ x: 1, y: 4, z: 0.5, snappedTo: targets[0] });
  });
});

describe('wording for the shapes a scan found', () => {
  it('says which way a line runs from its two ends', () => {
    expect(lineRunText({ x1: -4, z1: 0.5, x2: 4, z2: 0.5 })).toBe('running across the room');
    expect(lineRunText({ x1: 2, z1: -3, x2: 2, z2: 3 })).toBe('running upstage to downstage');
    expect(lineRunText(ANGLED)).toBe('running at 30 degrees to the room');
    // Written from the other end, or leaning the other way, it is the same angle to the room.
    expect(lineRunText({ x1: ANGLED.x2, z1: ANGLED.z2, x2: ANGLED.x1, z2: ANGLED.z1 })).toBe('running at 30 degrees to the room');
    expect(lineRunText({ x1: ANGLED.x1, z1: ANGLED.z2, x2: ANGLED.x2, z2: ANGLED.z1 })).toBe('running at 30 degrees to the room');
    // An old shell's word for it is not needed, and is not trusted over the ends.
    expect(lineRunText({ x1: -4, z1: 0.5, x2: 4, z2: 0.5, axis: 'z' })).toBe('running across the room');
    expect(lineRunText({ x1: 1, z1: 1, x2: 1, z2: 1, axis: 'z' })).toBe('running upstage to downstage');
  });

  it('lists an angled line, a ring and a room that is not a box', () => {
    expect(foundLines(preview(SHAPED))).toEqual([
      'Overhead line 1: 8.0 m long, underside 4.00 m up, running at 30 degrees to the room',
      'Overhead ring 1: a ring 8.0 m across, underside 4.80 m up',
    ]);
    expect(foundLines(preview(L_ROOM))).toEqual([
      'The room is not a box: its floor outline has 6 walls. The size above is the box round it.',
      'No stage, riser, booth, truss or bar was found: only the floor, walls and ceiling.',
    ]);
    expect(foundLines(preview(OLD))).toEqual([
      'Stage: 6.0 m by 2.5 m, 0.90 m high',
      'Overhead line 1: 8.0 m long, underside 4.00 m up, running across the room',
    ]);
  });
});
