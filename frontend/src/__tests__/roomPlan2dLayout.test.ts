// The 2D layout view in a scanned room: where a drag or a palette drop may
// land, what the plan's own labels are set against, and the room layer's
// labels kept off each other. Numbers only, no drawing. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import {
  holdOnPlan, holdToWalls, labelAngle, planFrame, planLabels, roomPlan, snapToRoomGrid,
} from '../components/rig/roomPlan2d';
import type { RoomShell } from '../types';

const BOX: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 9, height: 5 },
  risers: [
    { center_x: 0, center_z: -3, width: 8, depth: 3, height: 0.9, name: 'Stage', kind: 'stage' },
    { center_x: 4, center_z: 2, width: 2, depth: 1.5, height: 0.3, kind: 'riser' },
    { center_x: -4, center_z: 2, width: 2, depth: 1, height: 1.0, kind: 'booth' },
  ],
  truss_lines: [
    { name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, top: 4.5, across: 0.3, axis: 'x', heading_deg: 0 },
  ],
};

// An L: 12 m by 10 m with its downstage stage-left corner walled off. The
// notch is x > 2 with z > 1: outside the room, inside its box.
const L_OUTLINE = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];
const L_ROOM: RoomShell = { source: 'scan', room: { width: 12, depth: 10, height: 5, outline: L_OUTLINE } };

// ---------------------------------------------------------------------------
// Where a drag or a palette drop may land
// ---------------------------------------------------------------------------

describe('holdOnPlan: with no scanned room', () => {
  it('holds a position to the stage deck, as it always has', () => {
    expect(holdOnPlan(7, -6, 10, 8, null)).toEqual({ x: 5, z: -4 });
    expect(holdOnPlan(-7, 6, 10, 8, undefined)).toEqual({ x: -5, z: 4 });
    expect(holdOnPlan(2, 1, 10, 8, null)).toEqual({ x: 2, z: 1 });
  });
});

describe('holdOnPlan: in a box room', () => {
  // 12 m by 9 m, round a 6 m by 4 m deck.
  const walls = roomPlan(BOX)!.walls!;

  it('leaves a position beyond the deck where it is', () => {
    expect(holdOnPlan(5, 4, 6, 4, walls)).toEqual({ x: 5, z: 4 });
    expect(holdOnPlan(-5.5, -4.25, 6, 4, walls)).toEqual({ x: -5.5, z: -4.25 });
  });

  it('holds a position beyond a wall to the wall', () => {
    expect(holdOnPlan(8, 0, 6, 4, walls)).toEqual({ x: 6, z: 0 });
    expect(holdOnPlan(-8, 7, 6, 4, walls)).toEqual({ x: -6, z: 4.5 });
  });

  it('goes by the room even where the deck reaches past it', () => {
    // A deck wider than the room: the wall, not the deck's edge, is the limit.
    expect(holdOnPlan(7, 0, 16, 4, walls)).toEqual({ x: 6, z: 0 });
  });
});

describe('holdOnPlan: in an L-shaped room', () => {
  const walls = roomPlan(L_ROOM)!.walls!;

  it('leaves a position inside the outline where it is', () => {
    expect(holdToWalls(walls, 0, 0)).toEqual({ x: 0, z: 0 });
    expect(holdToWalls(walls, -5, 4)).toEqual({ x: -5, z: 4 });
    expect(holdToWalls(walls, 5, -4)).toEqual({ x: 5, z: -4 });
  });

  it('brings a position in the notch back to the nearest wall of it', () => {
    // 2 m from the wall at x = 2, 3 m from the wall at z = 1.
    const side = holdToWalls(walls, 4, 4);
    expect(side.x).toBeCloseTo(2);
    expect(side.z).toBeCloseTo(4);
    // 1 m from the wall at z = 1, 3 m from the wall at x = 2.
    const back = holdToWalls(walls, 5, 2);
    expect(back.x).toBeCloseTo(5);
    expect(back.z).toBeCloseTo(1);
  });

  it('holds a position beyond the box to the wall, and beyond a corner to the corner', () => {
    const wall = holdToWalls(walls, 8, -2);
    expect(wall.x).toBeCloseTo(6);
    expect(wall.z).toBeCloseTo(-2);
    const corner = holdToWalls(walls, 9, -7);
    expect(corner.x).toBeCloseTo(6);
    expect(corner.z).toBeCloseTo(-5);
  });

  it('is what holdOnPlan uses when the room has an outline', () => {
    const held = holdOnPlan(4, 4, 6, 4, walls);
    expect(held.x).toBeCloseTo(2);
    expect(held.z).toBeCloseTo(4);
  });
});

describe('snapToRoomGrid', () => {
  it('rounds to the grid with no deck edge to stop at', () => {
    expect(snapToRoomGrid(8.3, 5.8, 0.5)).toEqual({ x: 8.5, z: 6 });
    expect(snapToRoomGrid(-9.74, -7.26, 0.5)).toEqual({ x: -9.5, z: -7.5 });
  });

  it('gives 0, not -0, just short of the lines through the origin', () => {
    const snapped = snapToRoomGrid(-0.2, -0.1, 0.5);
    expect(Object.is(snapped.x, 0)).toBe(true);
    expect(Object.is(snapped.z, 0)).toBe(true);
  });

  it('leaves the position alone for a grid that is not one', () => {
    expect(snapToRoomGrid(1.23, 4.56, 0)).toEqual({ x: 1.23, z: 4.56 });
  });
});

// ---------------------------------------------------------------------------
// The plan's own labels
// ---------------------------------------------------------------------------

describe('planFrame', () => {
  const wallsOf = (xMin: number, xMax: number, zMin: number, zMax: number) => ({
    points: [{ x: xMin, z: zMin }, { x: xMax, z: zMin }, { x: xMax, z: zMax }, { x: xMin, z: zMax }],
    outlined: false,
    tooltip: '',
  });

  it('is the deck with no room', () => {
    expect(planFrame(10, 8, 1, null)).toEqual({ left: 1, right: 11, top: 1, bottom: 9, centreX: 6 });
    expect(planFrame(10, 8, 1, undefined)).toEqual({ left: 1, right: 11, top: 1, bottom: 9, centreX: 6 });
  });

  it('is the room\'s walls when they stand beyond the deck', () => {
    // A 20 m by 16 m room: its walls at x + 5 + 1 and z + 4 + 1 in the view's units.
    expect(planFrame(10, 8, 1, wallsOf(-10, 10, -8, 8)))
      .toEqual({ left: -4, right: 16, top: -3, bottom: 13, centreX: 6 });
  });

  it('stays on the deck for a room inside it', () => {
    expect(planFrame(10, 8, 1, wallsOf(-3, 3, -2, 2)))
      .toEqual({ left: 1, right: 11, top: 1, bottom: 9, centreX: 6 });
  });

  it('is centred on what it spans when the room reaches past one side only', () => {
    expect(planFrame(10, 8, 1, wallsOf(-5, 9, -4, 4)))
      .toEqual({ left: 1, right: 15, top: 1, bottom: 9, centreX: 8 });
  });

  it('goes by the box round an outline', () => {
    // Round a 6 m by 4 m deck: x + 3 + 1 and z + 2 + 1.
    expect(planFrame(6, 4, 1, roomPlan(L_ROOM)!.walls))
      .toEqual({ left: -2, right: 10, top: -2, bottom: 8, centreX: 4 });
  });
});

// ---------------------------------------------------------------------------
// The room layer's labels
// ---------------------------------------------------------------------------

describe('labelAngle', () => {
  it('is level for a line across the room, whichever end it is written from', () => {
    expect(labelAngle(-4, -2, 4, -2)).toBe(0);
    expect(labelAngle(4, -2, -4, -2)).toBe(0);
    expect(labelAngle(-4, -2, 4, -1.95)).toBe(0);
  });

  it('lies along an angled line and reads the right way up from either end', () => {
    const half = Math.sqrt(3) * 2;
    expect(labelAngle(-half, -2, half, 2)).toBe(30);
    expect(labelAngle(half, 2, -half, -2)).toBe(30);
    expect(labelAngle(-4, 4, 4, -4)).toBe(-45);
    expect(labelAngle(4, -4, -4, 4)).toBe(-45);
  });

  it('reads up the plan along a line running upstage to downstage', () => {
    expect(labelAngle(3, -4, 3, 4)).toBe(-90);
    expect(labelAngle(3, 4, 3, -4)).toBe(-90);
  });
});

describe('planLabels', () => {
  it('leaves every label at its usual place when none would overlap', () => {
    const labels = planLabels(roomPlan(BOX)!);
    expect(labels.raised.map((label) => label.text))
      .toEqual(['Stage · 0.90 m high', 'Riser · 0.30 m high', 'Booth or counter · 1.00 m high']);
    // A raised area's in its middle, just under centre.
    expect(labels.raised[0]).toMatchObject({ x: 0, angle: 0, size: 0.24, nudged: false });
    expect(labels.raised[0].z).toBeCloseTo(-2.92);
    expect(labels.raised[1]).toMatchObject({ x: 4, nudged: false });
    expect(labels.raised[2]).toMatchObject({ x: -4, nudged: false });
    // A truss line's over its middle: half its width and 0.1 m clear of it.
    expect(labels.trussLines[0])
      .toMatchObject({ text: 'Truss 1 · hangs at 4.20 m', x: 0, angle: 0, size: 0.22, nudged: false });
    expect(labels.trussLines[0].z).toBeCloseTo(-2.25);
    expect(labels.trussRings).toEqual([]);
  });

  it('nudges the second of two labels that would print over each other', () => {
    // Two trusses 0.2 m apart: their labels would sit 0.2 m apart, and are 0.22 m high.
    const labels = planLabels(roomPlan({
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      truss_lines: [
        { name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 5, across: 0.3 },
        { name: 'Truss 2', x1: -4, z1: -3.2, x2: 4, z2: -3.2, height: 5, across: 0.3 },
      ],
    })!);
    const [first, second] = labels.trussLines;
    // The first keeps its place.
    expect(first.nudged).toBe(false);
    expect(first.x).toBeCloseTo(0);
    expect(first.z).toBeCloseTo(-3.25);
    // The second steps away from its line by 1.4 font sizes: -3.45 - 0.308.
    expect(second.nudged).toBe(true);
    expect(second.x).toBeCloseTo(0);
    expect(second.z).toBeCloseTo(-3.758);
    // Now more than a label's height apart.
    expect(Math.abs(second.z - first.z)).toBeGreaterThan(0.22);
  });

  it('nudges a raised area\'s label off the one on the area it stands on', () => {
    const labels = planLabels(roomPlan({
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      risers: [
        { center_x: 0, center_z: -3, width: 8, depth: 3, height: 0.9, kind: 'stage' },
        { center_x: 0, center_z: -3, width: 2, depth: 2, height: 0.3, base_height: 0.9, kind: 'riser' },
      ],
    })!);
    expect(labels.raised).toHaveLength(2);
    expect(labels.raised[0].nudged).toBe(false);
    expect(labels.raised[0].z).toBeCloseTo(-2.92);
    // 1.4 font sizes of 0.24 up the plan.
    expect(labels.raised[1].nudged).toBe(true);
    expect(labels.raised[1].z).toBeCloseTo(-3.256);
  });

  it('does not nudge two labels that are side by side', () => {
    const labels = planLabels(roomPlan({
      source: 'scan',
      room: { width: 20, depth: 10, height: 6 },
      truss_lines: [
        { name: 'Truss 1', x1: -8, z1: -3, x2: -2, z2: -3, height: 5, across: 0.3 },
        { name: 'Truss 2', x1: 2, z1: -3, x2: 8, z2: -3, height: 5, across: 0.3 },
      ],
    })!);
    expect(labels.trussLines.map((label) => label.nudged)).toEqual([false, false]);
    expect(labels.trussLines[0].x).toBeCloseTo(-5);
    expect(labels.trussLines[1].x).toBeCloseTo(5);
  });

  it('turns a truss label along an angled line, on the upper side of it', () => {
    const half = Math.sqrt(3) * 2;
    const [label] = planLabels(roomPlan({
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      truss_lines: [{ name: 'Truss A', x1: -half, z1: -2, x2: half, z2: 2, height: 5.25, across: 0.4 }],
    })!).trussLines;
    expect(label.angle).toBe(30);
    expect(label.nudged).toBe(false);
    // 0.3 m off the middle of the line, square to it: (sin 30, -cos 30) * 0.3.
    expect(label.x).toBeCloseTo(0.15);
    expect(label.z).toBeCloseTo(-0.2598, 3);
  });

  it('puts a ring\'s label over its upstage side, level', () => {
    const [label] = planLabels(roomPlan({
      source: 'scan',
      room: { width: 6, depth: 6, height: 6 },
      truss_rings: [{ name: 'Ring 1', center_x: 1, center_z: -1, radius: 2, height: 4.8, across: 0.3 }],
    })!).trussRings;
    expect(label).toMatchObject({ text: 'Ring 1 · hangs at 4.80 m', x: 1, angle: 0, nudged: false });
    expect(label.z).toBeCloseTo(-3.25);
  });
});
