// The booth and the crowd in a scanned room (docs/ROOM_SCAN.md, slice 23):
// where the booth goes and which way it faces, and that the crowd stands only
// on open floor, the same people every time. A raised area at a heading
// (slice 21) is read as it stands turned.
import { describe, expect, it } from 'vitest';
import { insideOutline, outlineClearance } from '../components/rig/previs/outline';
import type { OutlinePoint } from '../components/rig/previs/outline';
import { boxCorners } from '../components/rig/previs/raisedArea';
import type { Footprint } from '../components/rig/previs/raisedArea';
import {
  BOOTH_FRONT_CLEAR, RAISED_CLEAR, WALL_CLEAR,
  areaDistance, boxFloor, facingOpenFloor, footprint, openFloorAt, openFloorCells, placeScanBooth, placeScanCrowd,
  rectDistance, scanCrowdCapacity,
} from '../components/rig/previs/scanFloor';
import type { RoomShellBox } from '../types';

const area = (
  kind: string, center_x: number, center_z: number, width: number, depth: number, height: number, base_height = 0,
): RoomShellBox => ({ kind, center_x, center_z, width, depth, height, base_height });

// A box room 12 m by 10 m, and the same room with x > 2, z > 1 walled off.
const ROOM = boxFloor(-6, 6, -5, 5);
const L_ROOM: OutlinePoint[] = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];
// A stage against the upstage wall, and a riser out on the floor downstage left.
const STAGE = area('stage', 0, -3.5, 8, 3, 1);
const RISER = area('riser', 4, 3, 2, 2, 0.4);

const EPS = 1e-9;

describe('rectDistance', () => {
  const rect = { xMin: -1, xMax: 1, zMin: 0, zMax: 2 };

  it('is 0 inside, and the straight distance off a side or a corner', () => {
    expect(rectDistance(rect, 0, 1)).toBe(0);
    expect(rectDistance(rect, 1, 2)).toBe(0);
    expect(rectDistance(rect, 3, 1)).toBeCloseTo(2);
    expect(rectDistance(rect, 0, -0.5)).toBeCloseTo(0.5);
    expect(rectDistance(rect, 4, 6)).toBeCloseTo(5);
  });
});

describe('the booth of a scanned room', () => {
  it('is not made up for a room with no booth and no stage', () => {
    expect(placeScanBooth(ROOM, [])).toBeNull();
    expect(placeScanBooth(ROOM, [RISER])).toBeNull();
    expect(placeScanBooth([], [STAGE])).toBeNull();
  });

  it('is a guess at the downstage middle of the first stage when the room has no booth', () => {
    const booth = placeScanBooth(ROOM, [RISER, STAGE, area('stage', -4, 3, 3, 2.5, 0.5)])!;
    expect(booth.source).toBe('guess');
    expect(booth.riser).toBe(1);
    expect([booth.faceX, booth.faceZ]).toEqual([0, 1]);
    expect(booth.yaw).toBeCloseTo(0);
    expect(booth.x).toBeCloseTo(0);
    // Just inside the stage's downstage edge, which is at z = -2.
    expect(booth.z).toBeCloseTo(-2.05);
    // A desk standing on the stage, half as wide as it.
    expect(booth.desk).toBe(true);
    expect(booth.baseY).toBeCloseTo(1);
    expect(booth.deskTopY).toBeCloseTo(1.95);
    expect(booth.width).toBeCloseTo(4);
    // The DJ on the stage, behind the desk.
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.y).toBeCloseTo(1);
    expect(booth.dj!.x).toBeCloseTo(0);
    expect(booth.dj!.z).toBeCloseTo(-2.85);
    // And a metre of floor kept clear in front of the stage, as wide as the desk.
    expect(booth.clear.xMin).toBeCloseTo(-2);
    expect(booth.clear.xMax).toBeCloseTo(2);
    expect(booth.clear.zMin).toBeCloseTo(-2);
    expect(booth.clear.zMax).toBeCloseTo(-2 + BOOTH_FRONT_CLEAR);
  });

  it('keeps a guessed booth downstage on a stage in a corner, whichever way most of the floor is', () => {
    // Upstage right: more of the open floor is across the room than downstage of it.
    const booth = placeScanBooth(ROOM, [area('stage', -4, -3.5, 3, 3, 1)])!;
    expect(booth.source).toBe('guess');
    expect([booth.faceX, booth.faceZ]).toEqual([0, 1]);
    expect(booth.x).toBeCloseTo(-4);
    expect(booth.z).toBeCloseTo(-2.05);
  });

  it('turns a guessed booth to the open floor only when a wall is right in front of the stage', () => {
    // Against the rear wall: z from 2 to 5, so downstage of it is the wall.
    const booth = placeScanBooth(ROOM, [area('stage', 0, 3.5, 8, 3, 1)])!;
    expect(booth.source).toBe('guess');
    expect([booth.faceX, booth.faceZ]).toEqual([0, -1]);
    expect(booth.z).toBeCloseTo(2.05);
  });

  it('draws no DJ where a riser stands on the stage behind the desk', () => {
    const drums = area('riser', 0, -2.9, 1, 1, 0.3, 1);
    expect(placeScanBooth(ROOM, [STAGE, drums])!.dj).toBeNull();
  });

  it('stands on the raised area the room calls a booth, not on the stage', () => {
    const booth = placeScanBooth(ROOM, [STAGE, area('booth', 0, 3, 3, 1, 1), area('booth', -5, 0, 1, 2, 1.1)])!;
    expect(booth.source).toBe('scan');
    expect(booth.riser).toBe(1);
  });

  it('takes a booth of desk height for the counter itself, facing the floor and away from the wall', () => {
    // Against the upstage wall: z from -5 to -4.
    const booth = placeScanBooth(ROOM, [area('booth', 0, -4.5, 3, 1, 1)])!;
    expect(booth.source).toBe('scan');
    expect([booth.faceX, booth.faceZ]).toEqual([0, 1]);
    expect(booth.x).toBeCloseTo(0);
    expect(booth.z).toBeCloseTo(-4);
    expect(booth.desk).toBe(false);
    expect(booth.deskTopY).toBeCloseTo(1);
    expect(booth.baseY).toBeCloseTo(0);
    expect(booth.width).toBeCloseTo(3);
    // The wall is right behind it: nowhere for a DJ to stand.
    expect(booth.dj).toBeNull();
    expect(booth.clear).toEqual({ xMin: -1.5, xMax: 1.5, zMin: -4, zMax: -3 });
  });

  it('stands the DJ on the floor behind a counter that is out from the wall', () => {
    const booth = placeScanBooth(ROOM, [area('booth', 0, -3, 3, 1, 1)])!;
    expect(booth.z).toBeCloseTo(-2.5);
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.y).toBeCloseTo(0);
    expect(booth.dj!.x).toBeCloseTo(0);
    // Behind the counter's back face, which is at z = -3.5.
    expect(booth.dj!.z).toBeCloseTo(-3.75);
    // The decks are on the DJ's side of the counter.
    expect(booth.z - booth.gearBack).toBeCloseTo(-3.2);
  });

  it('turns a booth on a side wall to face across the room', () => {
    // Against the stage left wall: x from 5 to 6.
    const booth = placeScanBooth(ROOM, [area('booth', 5.5, 0, 1, 3, 1)])!;
    expect([booth.faceX, booth.faceZ]).toEqual([-1, 0]);
    expect(booth.yaw).toBeCloseTo(-Math.PI / 2);
    expect(booth.x).toBeCloseTo(5);
    expect(booth.z).toBeCloseTo(0);
    // Its long side is its front.
    expect(booth.width).toBeCloseTo(3);
    expect(booth.clear.xMin).toBeCloseTo(4);
    expect(booth.clear.xMax).toBeCloseTo(5);
    expect(booth.clear.zMin).toBeCloseTo(-1.5);
    expect(booth.clear.zMax).toBeCloseTo(1.5);
  });

  it('faces the floor that is open, not a wall close in front of it', () => {
    // In the arm of the L, with the notch's wall (x = 2) on one side.
    const booth = area('booth', 1, 4.5, 1.5, 1, 1);
    const [faceX, faceZ] = facingOpenFloor(L_ROOM, booth, openFloorCells(L_ROOM, [booth]).cells);
    // Not downstage into the rear wall, and not into the notch.
    expect([faceX, faceZ]).not.toEqual([0, 1]);
    expect([faceX, faceZ]).not.toEqual([1, 0]);
  });

  it('stands a desk and the DJ on a low booth platform', () => {
    // 3 m by 1.5 m and 0.3 m high: z from -4.75 to -3.25.
    const booth = placeScanBooth(ROOM, [area('booth', 0, -4, 3, 1.5, 0.3)])!;
    expect(booth.source).toBe('scan');
    expect(booth.desk).toBe(true);
    expect(booth.baseY).toBeCloseTo(0.3);
    expect(booth.deskTopY).toBeCloseTo(1.25);
    expect(booth.width).toBeCloseTo(2.8);
    expect(booth.z).toBeCloseTo(-3.3);
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.y).toBeCloseTo(0.3);
    expect(booth.dj!.z).toBeCloseTo(-4.1);
  });

  it('faces downstage when there is no open floor to face', () => {
    const tight = boxFloor(-2, 2, -2, 2);
    const booth = placeScanBooth(tight, [area('stage', 0, 0, 3.6, 3.6, 1)])!;
    expect([booth.faceX, booth.faceZ]).toEqual([0, 1]);
  });
});

describe('the open floor of a scanned room', () => {
  it('is the floor inside the walls, less a margin', () => {
    expect(openFloorAt(ROOM, [], 0, 0)).toBe(true);
    expect(openFloorAt(ROOM, [], 5.4, 0)).toBe(true);
    expect(openFloorAt(ROOM, [], 5.6, 0)).toBe(false);
    expect(openFloorAt(ROOM, [], 7, 0)).toBe(false);
    // The notch of an L is outside the room, and its walls have a margin too.
    expect(openFloorAt(L_ROOM, [], 4, 3)).toBe(false);
    expect(openFloorAt(L_ROOM, [], 1.7, 3)).toBe(false);
    expect(openFloorAt(L_ROOM, [], 1.4, 3)).toBe(true);
  });

  it('is not on a raised area, nor within half a metre of one', () => {
    expect(openFloorAt(ROOM, [STAGE, RISER], 0, -3)).toBe(false);
    expect(openFloorAt(ROOM, [STAGE, RISER], 0, -1.7)).toBe(false);
    expect(openFloorAt(ROOM, [STAGE, RISER], 0, -1.4)).toBe(true);
    expect(openFloorAt(ROOM, [STAGE, RISER], 4, 3)).toBe(false);
    expect(openFloorAt(ROOM, [STAGE, RISER], 2.6, 3)).toBe(false);
    expect(openFloorAt(ROOM, [STAGE, RISER], 2.4, 3)).toBe(true);
  });

  it('measures an L-shaped room without its notch', () => {
    const capacity = scanCrowdCapacity(openFloorCells(L_ROOM, []));
    // 104 m2 of floor, about 83 m2 of it half a metre from a wall, at 4 people a square metre.
    expect(capacity).toBeGreaterThan(290);
    expect(capacity).toBeLessThan(345);
    expect(capacity).toBeLessThan(scanCrowdCapacity(openFloorCells(ROOM, [])));
  });
});

describe('the crowd of a scanned room', () => {
  it('is the same crowd every time, and another one once the room is edited', () => {
    const booth = placeScanBooth(ROOM, [STAGE, RISER]);
    const first = placeScanCrowd(ROOM, [STAGE, RISER], booth, 120);
    expect(first.length).toBeGreaterThan(0);
    expect(placeScanCrowd(ROOM, [STAGE, RISER], booth, 120)).toEqual(first);

    const moved = [STAGE, { ...RISER, center_x: 3 }];
    expect(placeScanCrowd(ROOM, moved, placeScanBooth(ROOM, moved), 120)).not.toEqual(first);
  });

  it('fills an L-shaped room and stays out of its notch', () => {
    const people = placeScanCrowd(L_ROOM, [], null, 60);
    expect(people.length).toBe(60);
    for (const person of people) {
      expect(insideOutline(L_ROOM, person.x, person.z)).toBe(true);
      expect(outlineClearance(L_ROOM, person.x, person.z)).toBeGreaterThanOrEqual(WALL_CLEAR - EPS);
      expect(person.x > 2 && person.z > 1).toBe(false);
    }
    // Both arms of the L have people in them.
    expect(people.some((person) => person.x > 2)).toBe(true);
    expect(people.some((person) => person.z > 1)).toBe(true);
  });

  it('never holds more than was asked for or than the floor has room for', () => {
    const open = openFloorCells(L_ROOM, []);
    expect(placeScanCrowd(L_ROOM, [], null, 5000).length).toBeLessThanOrEqual(scanCrowdCapacity(open));
    expect(placeScanCrowd(L_ROOM, [], null, 25).length).toBeLessThanOrEqual(25);
    expect(placeScanCrowd(L_ROOM, [], null, 0)).toEqual([]);
    expect(placeScanCrowd(L_ROOM, [], null, Number.NaN)).toEqual([]);
  });

  it('stands round a stage and a riser, not on them, and clear of them and of each other', () => {
    const risers = [STAGE, RISER];
    const booth = placeScanBooth(ROOM, risers)!;
    const people = placeScanCrowd(ROOM, risers, booth, 80);
    expect(people.length).toBe(80);
    for (const person of people) {
      expect(outlineClearance(ROOM, person.x, person.z)).toBeGreaterThanOrEqual(WALL_CLEAR - EPS);
      for (const riser of risers) {
        expect(rectDistance(footprint(riser), person.x, person.z)).toBeGreaterThanOrEqual(RAISED_CLEAR - EPS);
      }
    }
    for (let i = 0; i < people.length; i += 1) {
      for (let j = i + 1; j < people.length; j += 1) {
        expect(Math.hypot(people[i].x - people[j].x, people[i].z - people[j].z)).toBeGreaterThan(0.4);
      }
    }
  });

  it('is denser near the booth and faces it', () => {
    const risers = [STAGE, RISER];
    const booth = placeScanBooth(ROOM, risers)!;
    const people = placeScanCrowd(ROOM, risers, booth, 80);
    const away = (point: { x: number; z: number }) => Math.hypot(point.x - booth.x, point.z - booth.z);

    // More than half of them stand on the half of the floor nearer the booth.
    const distances = openFloorCells(ROOM, risers, booth).cells.map(away).sort((a, b) => a - b);
    const half = distances[Math.floor(distances.length / 2)];
    const near = people.filter((person) => away(person) < half).length;
    expect(near).toBeGreaterThan(people.length - near);

    for (const person of people) {
      const toBooth = [(booth.x - person.x) / away(person), (booth.z - person.z) / away(person)];
      // Yaw 0 faces +Z: within a quarter of a radian of straight at the booth.
      expect(Math.sin(person.yaw) * toBooth[0] + Math.cos(person.yaw) * toBooth[1]).toBeGreaterThan(0.95);
    }
  });

  it('keeps a metre in front of the booth clear, and room round the DJ', () => {
    const risers = [area('booth', 0, -3, 3, 1, 1)];
    const booth = placeScanBooth(ROOM, risers)!;
    const people = placeScanCrowd(ROOM, risers, booth, 200);
    expect(people.length).toBeGreaterThan(100);
    for (const person of people) {
      // The counter's front is at z = -2.5: nobody in the strip out to z = -1.5.
      expect(Math.abs(person.x) <= 1.5 && person.z >= -2.5 && person.z <= -1.5).toBe(false);
      expect(rectDistance(booth.clear, person.x, person.z)).toBeGreaterThan(0);
      expect(rectDistance(footprint(risers[0]), person.x, person.z)).toBeGreaterThanOrEqual(RAISED_CLEAR - EPS);
      expect(Math.hypot(person.x - booth.dj!.x, person.z - booth.dj!.z)).toBeGreaterThanOrEqual(0.9 - EPS);
    }
    // Without the booth's strip there is floor there to stand on.
    expect(openFloorAt(ROOM, risers, 0, -1.9)).toBe(true);
    expect(openFloorAt(ROOM, risers, 0, -1.9, booth)).toBe(false);
    expect(openFloorAt(ROOM, risers, 0, -1.4, booth)).toBe(true);
  });

  it('leaves the floor camera room to stand', () => {
    const camera = { x: 0, z: 2, clearRadius: 1.1 };
    const people = placeScanCrowd(ROOM, [], null, 150, camera);
    expect(people.length).toBeGreaterThan(75);
    for (const person of people) {
      expect(Math.hypot(person.x - camera.x, person.z - camera.z)).toBeGreaterThanOrEqual(camera.clearRadius - EPS);
    }
  });

  it('is nobody in a room with no floor left', () => {
    const tight = boxFloor(-2, 2, -2, 2);
    const risers = [area('stage', 0, 0, 3.6, 3.6, 1)];
    expect(openFloorCells(tight, risers).cells).toEqual([]);
    expect(scanCrowdCapacity(openFloorCells(tight, risers))).toBe(0);
    expect(placeScanCrowd(tight, risers, placeScanBooth(tight, risers), 180)).toEqual([]);
  });
});

// A raised area at a heading (slice 21): degrees clockwise seen from above,
// its width along the heading and its depth square to it, about its middle.
const turned = (shape: RoomShellBox, heading_deg: number): RoomShellBox => ({ ...shape, heading_deg });

// Worked out here from the angle alone, not by the code under test: how far
// (x, z) is from a box that stands at a heading. 0 on it.
function turnedDistance(shape: Footprint, x: number, z: number): number {
  const turn = ((shape.heading_deg ?? 0) * Math.PI) / 180;
  const dx = x - shape.center_x;
  const dz = z - shape.center_z;
  const across = dx * Math.cos(turn) + dz * Math.sin(turn);
  const back = -dx * Math.sin(turn) + dz * Math.cos(turn);
  return Math.hypot(Math.max(Math.abs(across) - shape.width / 2, 0), Math.max(Math.abs(back) - shape.depth / 2, 0));
}

const SIN30 = 0.5;
const COS30 = Math.sqrt(3) / 2;
// A stage 6 m by 2 m out on the floor, turned 30 degrees: its downstage side
// faces (-sin 30, cos 30), downstage and a little to stage right.
const STAGE_30 = turned(area('stage', 0, -1, 6, 2, 1), 30);
// A counter 3 m by 1 m turned the same way, upstage left of the middle.
const BOOTH_30 = turned(area('booth', 3, -2, 3, 1, 1), 30);

describe('a raised area at a heading', () => {
  it('is measured as it stands turned, and as it always was when it is not', () => {
    // On the turned stage and a metre outside the square one; and the other way round.
    expect(areaDistance(STAGE_30, 2, 1)).toBe(0);
    expect(rectDistance(footprint(STAGE_30), 2, 1)).toBeCloseTo(1);
    expect(areaDistance(STAGE_30, 2.6, -1.6)).toBeCloseTo(turnedDistance(STAGE_30, 2.6, -1.6));
    expect(areaDistance(STAGE_30, 2.6, -1.6)).toBeGreaterThan(RAISED_CLEAR);
    expect(rectDistance(footprint(STAGE_30), 2.6, -1.6)).toBe(0);
    // Off a side and off a corner.
    expect(areaDistance(STAGE_30, -4, 3)).toBeCloseTo(turnedDistance(STAGE_30, -4, 3));
    expect(areaDistance(STAGE_30, 5, 2)).toBeCloseTo(turnedDistance(STAGE_30, 5, 2));
    // No heading and a heading of 0 are the plain rectangle, to the last bit.
    for (const [x, z] of [[0, -3], [0, -1.7], [4.3, -2.1], [-5, 4]]) {
      expect(areaDistance(STAGE, x, z)).toBe(rectDistance(footprint(STAGE), x, z));
      expect(areaDistance(turned(STAGE, 0), x, z)).toBe(rectDistance(footprint(STAGE), x, z));
    }
  });

  it('changes nothing when the heading is 0', () => {
    const plain = [STAGE, RISER];
    const zero = [turned(STAGE, 0), turned(RISER, 0)];
    const booth = placeScanBooth(ROOM, plain)!;
    expect(placeScanBooth(ROOM, zero)).toEqual(booth);
    expect(booth.heading).toBe(0);
    expect(booth.strip).toBeNull();
    expect(openFloorCells(ROOM, zero, booth)).toEqual(openFloorCells(ROOM, plain, booth));
    expect(placeScanCrowd(ROOM, zero, booth, 120)).toEqual(placeScanCrowd(ROOM, plain, booth, 120));

    const counter = area('booth', 5.5, 0, 1, 3, 1);
    expect(placeScanBooth(ROOM, [turned(counter, 0)])).toEqual(placeScanBooth(ROOM, [counter]));
  });

  it('puts a guessed booth at the downstage edge of a stage turned 30 degrees', () => {
    const booth = placeScanBooth(ROOM, [STAGE_30])!;
    expect(booth.source).toBe('guess');
    expect(booth.heading).toBe(30);
    // It faces the way the stage's downstage side does, and is turned with the stage.
    expect(booth.faceX).toBeCloseTo(-SIN30);
    expect(booth.faceZ).toBeCloseTo(COS30);
    expect(booth.yaw).toBeCloseTo(-Math.PI / 6);
    // 0.05 m inside the middle of that side, which is 1 m from the stage's middle.
    expect(booth.x).toBeCloseTo(0 - SIN30 * 0.95);
    expect(booth.z).toBeCloseTo(-1 + COS30 * 0.95);
    // A desk half as wide as the stage is along its heading.
    expect(booth.desk).toBe(true);
    expect(booth.width).toBeCloseTo(3);
    // The DJ on the stage, 0.8 m behind the desk's front along the same line.
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.y).toBeCloseTo(1);
    expect(booth.dj!.x).toBeCloseTo(0 - SIN30 * 0.15);
    expect(booth.dj!.z).toBeCloseTo(-1 + COS30 * 0.15);
    expect(turnedDistance(STAGE_30, booth.dj!.x, booth.dj!.z)).toBe(0);
    // The metre kept clear in front is a box at the stage's heading, as wide as the desk.
    expect(booth.strip).not.toBeNull();
    expect(booth.strip!.heading_deg).toBe(30);
    expect(booth.strip!.width).toBeCloseTo(3);
    expect(booth.strip!.depth).toBeCloseTo(BOOTH_FRONT_CLEAR);
    expect(booth.strip!.center_x).toBeCloseTo(0 - SIN30 * 1.5);
    expect(booth.strip!.center_z).toBeCloseTo(-1 + COS30 * 1.5);
    // `clear` is the box round it.
    const xs = boxCorners(booth.strip!).map((corner) => corner.x);
    const zs = boxCorners(booth.strip!).map((corner) => corner.z);
    expect(booth.clear.xMin).toBeCloseTo(Math.min(...xs));
    expect(booth.clear.xMax).toBeCloseTo(Math.max(...xs));
    expect(booth.clear.zMin).toBeCloseTo(Math.min(...zs));
    expect(booth.clear.zMax).toBeCloseTo(Math.max(...zs));
  });

  it('puts a guessed booth on a stage turned 90 degrees where the same stage standing square has it', () => {
    // 3 m along its heading, which now runs up and down stage, and 8 m square to it: STAGE on the plan.
    const quarter = turned(area('stage', 0, -3.5, 3, 8, 1), 90);
    const booth = placeScanBooth(ROOM, [quarter])!;
    const square = placeScanBooth(ROOM, [STAGE])!;
    expect(booth.source).toBe('guess');
    expect(booth.heading).toBe(90);
    expect(booth.faceX).toBeCloseTo(0);
    expect(booth.faceZ).toBeCloseTo(1);
    expect(booth.yaw).toBeCloseTo(0);
    expect(booth.x).toBeCloseTo(square.x);
    expect(booth.z).toBeCloseTo(-2.05);
    expect(booth.width).toBeCloseTo(4);
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.x).toBeCloseTo(square.dj!.x);
    expect(booth.dj!.z).toBeCloseTo(square.dj!.z);
    expect(booth.clear.xMin).toBeCloseTo(square.clear.xMin);
    expect(booth.clear.xMax).toBeCloseTo(square.clear.xMax);
    expect(booth.clear.zMin).toBeCloseTo(square.clear.zMin);
    expect(booth.clear.zMax).toBeCloseTo(square.clear.zMax);
    // And the floor round it is the floor round the square one.
    const cells = openFloorCells(ROOM, [quarter], booth).cells;
    expect(cells.length).toBe(openFloorCells(ROOM, [STAGE], square).cells.length);
    for (const cell of cells) {
      expect(rectDistance(footprint(STAGE), cell.x, cell.z)).toBeGreaterThanOrEqual(RAISED_CLEAR - 1e-6);
    }
  });

  it('takes an end of the width for the downstage edge once a stage is turned past 45 degrees', () => {
    // 2 m along a heading of -60 and 6 m square to it stands where STAGE_30 does.
    const booth = placeScanBooth(ROOM, [turned(area('stage', 0, -1, 2, 6, 1), -60)])!;
    const same = placeScanBooth(ROOM, [STAGE_30])!;
    expect(booth.heading).toBe(-60);
    expect(booth.faceX).toBeCloseTo(same.faceX);
    expect(booth.faceZ).toBeCloseTo(same.faceZ);
    expect(booth.x).toBeCloseTo(same.x);
    expect(booth.z).toBeCloseTo(same.z);
    expect(booth.width).toBeCloseTo(same.width);
    expect(booth.yaw).toBeCloseTo(same.yaw);
  });

  it('turns a guessed booth off the downstage edge of a turned stage only for a wall in front of it', () => {
    // A small stage against the rear wall: its downstage side looks into the wall.
    const booth = placeScanBooth(ROOM, [turned(area('stage', 0, 3.6, 2, 2, 1), 30)])!;
    expect(booth.source).toBe('guess');
    expect(booth.faceX).toBeCloseTo(SIN30);
    expect(booth.faceZ).toBeCloseTo(-COS30);
    // The same stage a metre and a half up the room has floor in front of it.
    const clear = placeScanBooth(ROOM, [turned(area('stage', 0, 2.1, 2, 2, 1), 30)])!;
    expect(clear.faceX).toBeCloseTo(-SIN30);
    expect(clear.faceZ).toBeCloseTo(COS30);
  });

  it('draws a booth the room has at its own heading, facing the floor', () => {
    const booth = placeScanBooth(ROOM, [BOOTH_30])!;
    expect(booth.source).toBe('scan');
    expect(booth.heading).toBe(30);
    expect(booth.faceX).toBeCloseTo(-SIN30);
    expect(booth.faceZ).toBeCloseTo(COS30);
    // The turn the 3D view gives the counter's own box (buildRisers): minus its heading about Y.
    expect(booth.yaw).toBeCloseTo((-30 * Math.PI) / 180);
    // The middle of the counter's front face, half its depth from its middle.
    expect(booth.x).toBeCloseTo(3 - SIN30 * 0.5);
    expect(booth.z).toBeCloseTo(-2 + COS30 * 0.5);
    expect(booth.desk).toBe(false);
    expect(booth.width).toBeCloseTo(3);
    // The DJ on the floor 0.25 m behind its back face, on the same line.
    expect(booth.dj).not.toBeNull();
    expect(booth.dj!.y).toBeCloseTo(0);
    expect(booth.dj!.x).toBeCloseTo(3 + SIN30 * 0.75);
    expect(booth.dj!.z).toBeCloseTo(-2 - COS30 * 0.75);
    expect(turnedDistance(BOOTH_30, booth.dj!.x, booth.dj!.z)).toBeCloseTo(0.25);
    // A metre of floor in front of it, as wide as it and turned with it.
    expect(booth.strip).not.toBeNull();
    expect(booth.strip!.heading_deg).toBe(30);
    expect(booth.strip!.width).toBeCloseTo(3);
    expect(booth.strip!.depth).toBeCloseTo(BOOTH_FRONT_CLEAR);
    expect(booth.strip!.center_x).toBeCloseTo(3 - SIN30 * 1);
    expect(booth.strip!.center_z).toBeCloseTo(-2 + COS30 * 1);
  });

  it('turns a counter given a quarter turn on a side wall to face across the room', () => {
    // 3 m along the stage left wall and 1 m out from it: x from 5 to 6.
    const booth = placeScanBooth(ROOM, [turned(area('booth', 5.5, 0, 3, 1, 1), 90)])!;
    expect(booth.heading).toBe(90);
    expect(booth.faceX).toBeCloseTo(-1);
    expect(booth.faceZ).toBeCloseTo(0);
    expect(booth.yaw).toBeCloseTo(-Math.PI / 2);
    expect(booth.x).toBeCloseTo(5);
    expect(booth.z).toBeCloseTo(0);
    expect(booth.width).toBeCloseTo(3);
    expect(booth.clear.xMin).toBeCloseTo(4);
    expect(booth.clear.xMax).toBeCloseTo(5);
    expect(booth.clear.zMin).toBeCloseTo(-1.5);
    expect(booth.clear.zMax).toBeCloseTo(1.5);
  });

  it('keeps the open floor off a turned stage and on the floor it turned away from', () => {
    // On the turned stage, though a metre outside where it would stand square.
    expect(openFloorAt(ROOM, [STAGE_30], 2, 1)).toBe(false);
    // 0.3 m off its turned downstage side, and well clear of the square one.
    expect(turnedDistance(STAGE_30, 1.515, 1.376)).toBeCloseTo(0.3, 2);
    expect(openFloorAt(ROOM, [STAGE_30], 1.515, 1.376)).toBe(false);
    // Floor the square stage would cover.
    expect(openFloorAt(ROOM, [STAGE_30], 2.6, -1.6)).toBe(true);
    // The strip in front of the booth is turned too: 0.8 m out from the front it is kept clear, 1.2 m out it is not.
    const booth = placeScanBooth(ROOM, [STAGE_30])!;
    const out = (metres: number): [number, number] => [0 - SIN30 * (1 + metres), -1 + COS30 * (1 + metres)];
    expect(openFloorAt(ROOM, [STAGE_30], ...out(0.8))).toBe(true);
    expect(openFloorAt(ROOM, [STAGE_30], ...out(0.8), booth)).toBe(false);
    expect(openFloorAt(ROOM, [STAGE_30], ...out(1.2), booth)).toBe(true);
  });

  it('stands the crowd round a turned stage, a turned riser and a turned booth, inside the room', () => {
    const risers = [STAGE_30, turned(area('riser', -4, -3, 2, 2, 0.4), -40), turned(area('booth', -4, 3, 2, 1, 1), 60)];
    const booth = placeScanBooth(L_ROOM, risers)!;
    expect(booth.source).toBe('scan');
    expect(booth.riser).toBe(2);
    expect(booth.strip).not.toBeNull();
    const people = placeScanCrowd(L_ROOM, risers, booth, 320);
    expect(people.length).toBeGreaterThan(100);
    for (const person of people) {
      expect(insideOutline(L_ROOM, person.x, person.z)).toBe(true);
      expect(outlineClearance(L_ROOM, person.x, person.z)).toBeGreaterThanOrEqual(WALL_CLEAR - EPS);
      for (const riser of risers) {
        expect(turnedDistance(riser, person.x, person.z)).toBeGreaterThanOrEqual(RAISED_CLEAR - 1e-6);
      }
      expect(turnedDistance(booth.strip!, person.x, person.z)).toBeGreaterThan(0);
    }
    // Somebody stands where the stage would be if it stood square to the room.
    expect(people.some((person) => rectDistance(footprint(STAGE_30), person.x, person.z) === 0)).toBe(true);
  });

  it('is another crowd once a raised area is turned', () => {
    const risers = [STAGE, RISER];
    const booth = placeScanBooth(ROOM, risers);
    // A riser 2 m square covers the same floor after a quarter turn, and it is still an edit to the room.
    const turnedRisers = [STAGE, turned(RISER, 90)];
    expect(placeScanCrowd(ROOM, turnedRisers, placeScanBooth(ROOM, turnedRisers), 120))
      .not.toEqual(placeScanCrowd(ROOM, risers, booth, 120));
  });
});
