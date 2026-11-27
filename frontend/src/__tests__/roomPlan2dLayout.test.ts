// The 2D layout view in a scanned room: where a drag or a palette drop may
// land, what the plan's own labels are set against, and the room layer's
// labels kept off each other. Numbers only, no drawing. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import {
  holdOnPlan, holdToWalls, insideWalls, labelAngle, paletteClickSpot, planFrame, planGrid, planLabels,
  planTrussTargets, roomPlan, snapToRoomGrid, snapToScannedTruss,
} from '../components/rig/roomPlan2d';
import type { PlanGridLine } from '../components/rig/roomPlan2d';
import { outlineClearance } from '../components/rig/previs/outline';
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

// ---------------------------------------------------------------------------
// Snapping a drag to the truss a scan found
// ---------------------------------------------------------------------------

// A truss straight across, one at 45 degrees, a ring, and a stage whose edges
// are not truss.
const TRUSSED: RoomShell = {
  source: 'scan',
  room: { width: 20, depth: 16, height: 6 },
  risers: [{ center_x: 0, center_z: -6, width: 8, depth: 3, height: 0.9, name: 'Stage', kind: 'stage' }],
  truss_lines: [
    { name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 },
    { name: 'Truss 2', x1: -6, z1: 0, x2: -2, z2: 4, height: 5, across: 0.3, heading_deg: 45 },
  ],
  truss_rings: [{ name: 'Ring 1', center_x: 5, center_z: -2, radius: 2, height: 4.8, across: 0.3 }],
};

describe('planTrussTargets', () => {
  it('offers the scan\'s truss lines and rings, and not the edges of its raised areas', () => {
    const targets = planTrussTargets(TRUSSED);
    expect(targets.map((target) => target.name)).toEqual(['Truss 1', 'Truss 2', 'Ring 1']);
    expect(targets.every((target) => target.kind === 'truss')).toBe(true);
    expect(targets[2].ring).toEqual({ centerX: 5, centerZ: -2, radius: 2 });
  });

  it('offers nothing with no scanned room', () => {
    expect(planTrussTargets(null)).toEqual([]);
    expect(planTrussTargets(undefined)).toEqual([]);
    // A demo preset's shell, and the same truss in a shell that is not a scan.
    expect(planTrussTargets({ dome: { radius: 8, center_x: 0, center_z: 0, rim_height: 6, apex_height: 9 } })).toEqual([]);
    expect(planTrussTargets({ ...TRUSSED, source: undefined })).toEqual([]);
    expect(planTrussTargets({ source: 'scan', room: { width: 12, depth: 9, height: 5 } })).toEqual([]);
  });
});

describe('snapToScannedTruss', () => {
  const targets = planTrussTargets(TRUSSED);

  it('puts a position within reach of a truss line onto it, where it is along the line', () => {
    const snapped = snapToScannedTruss(1.2, -2.7, targets);
    expect(snapped.x).toBeCloseTo(1.2);
    expect(snapped.z).toBeCloseTo(-3);
    expect(snapped.snappedTo?.name).toBe('Truss 1');
  });

  it('leaves a position beyond 0.4 m of any truss where it is', () => {
    expect(snapToScannedTruss(1.2, -2.5, targets)).toEqual({ x: 1.2, z: -2.5, snappedTo: null });
    // Beyond the end of the line as well: 0.5 m past it.
    expect(snapToScannedTruss(4.5, -3, targets)).toEqual({ x: 4.5, z: -3, snappedTo: null });
  });

  it('snaps to the end of a line from just past it', () => {
    const snapped = snapToScannedTruss(4.3, -3, targets);
    expect(snapped.x).toBeCloseTo(4);
    expect(snapped.z).toBeCloseTo(-3);
  });

  it('snaps square onto a line at an angle', () => {
    // 0.28 m off the middle of Truss 2 at (-4, 2), square to it.
    const snapped = snapToScannedTruss(-3.8, 1.8, targets);
    expect(snapped.x).toBeCloseTo(-4);
    expect(snapped.z).toBeCloseTo(2);
    expect(snapped.snappedTo?.name).toBe('Truss 2');
  });

  it('snaps onto a ring from outside it and from inside it, and not from its centre', () => {
    // The ring's downstage side is at (5, 0).
    const outside = snapToScannedTruss(5, 0.3, targets);
    expect(outside.x).toBeCloseTo(5);
    expect(outside.z).toBeCloseTo(0);
    expect(outside.snappedTo?.name).toBe('Ring 1');
    const inside = snapToScannedTruss(5, -0.3, targets);
    expect(inside.x).toBeCloseTo(5);
    expect(inside.z).toBeCloseTo(0);
    expect(snapToScannedTruss(5, -2, targets)).toEqual({ x: 5, z: -2, snappedTo: null });
  });

  it('takes the nearer of two trusses in reach', () => {
    const two = planTrussTargets({
      source: 'scan',
      truss_lines: [
        { name: 'Back', x1: -4, z1: -3, x2: 4, z2: -3, height: 4, across: 0.3 },
        { name: 'Front', x1: -4, z1: -2.5, x2: 4, z2: -2.5, height: 9, across: 0.3 },
      ],
    });
    expect(snapToScannedTruss(0, -2.7, two).snappedTo?.name).toBe('Front');
    expect(snapToScannedTruss(0, -2.8, two).snappedTo?.name).toBe('Back');
  });

  it('goes by the plan alone: a truss at any height is in reach', () => {
    // The 3D drag only offers truss within 1.5 m of the fixture's height. The plan has no height.
    const high = planTrussTargets({
      source: 'scan',
      truss_lines: [{ name: 'High', x1: -4, z1: 1, x2: 4, z2: 1, height: 12, across: 0.3 }],
    });
    expect(snapToScannedTruss(0, 1.2, high).snappedTo?.name).toBe('High');
  });

  it('leaves a position alone when there is no truss, or a radius of none', () => {
    expect(snapToScannedTruss(1.2, -2.9, [])).toEqual({ x: 1.2, z: -2.9, snappedTo: null });
    expect(snapToScannedTruss(1.2, -2.9, targets, 0)).toEqual({ x: 1.2, z: -2.9, snappedTo: null });
  });
});

// ---------------------------------------------------------------------------
// The snap grid, drawn across the room
// ---------------------------------------------------------------------------

/** A grid line as [x1, z1, x2, z2], tidied so 2 and 2.0000000001 (and 0 and -0) read the same. */
const ends = (line: PlanGridLine) => [line.x1, line.z1, line.x2, line.z2].map((v) => Math.round(v * 1000) / 1000 + 0);
const upAndDownAt = (lines: PlanGridLine[], x: number) =>
  lines.filter((line) => Math.abs(line.x1 - x) < 1e-6 && Math.abs(line.x2 - x) < 1e-6 && line.z1 !== line.z2);
const acrossAt = (lines: PlanGridLine[], z: number) =>
  lines.filter((line) => Math.abs(line.z1 - z) < 1e-6 && Math.abs(line.z2 - z) < 1e-6 && line.x1 !== line.x2);
/** Whether any line of the grid runs through a point, ends not counted. */
const drawnThrough = (lines: PlanGridLine[], x: number, z: number) => lines.some((line) => {
  const onX = Math.abs(line.x1 - x) < 1e-6 && Math.abs(line.x2 - x) < 1e-6
    && Math.min(line.z1, line.z2) < z && z < Math.max(line.z1, line.z2);
  const onZ = Math.abs(line.z1 - z) < 1e-6 && Math.abs(line.z2 - z) < 1e-6
    && Math.min(line.x1, line.x2) < x && x < Math.max(line.x1, line.x2);
  return onX || onZ;
});

describe('planGrid: in a box room', () => {
  // 12 m by 9 m.
  const walls = roomPlan(BOX)!.walls!;

  it('runs each line from wall to wall, well beyond a deck inside the room', () => {
    const lines = planGrid(walls, 6, 4, 1);
    // The deck ends at x = 3 and z = 2.
    expect(upAndDownAt(lines, 5).map(ends)).toEqual([[5, -4.5, 5, 4.5]]);
    expect(upAndDownAt(lines, 0).map(ends)).toEqual([[0, -4.5, 0, 4.5]]);
    expect(acrossAt(lines, 4).map(ends)).toEqual([[-6, 4, 6, 4]]);
    expect(acrossAt(lines, 0).map(ends)).toEqual([[-6, 0, 6, 0]]);
    // Nothing beyond the walls at x = 6 and z = 4.5.
    expect(upAndDownAt(lines, 7)).toEqual([]);
    expect(acrossAt(lines, 5)).toEqual([]);
  });

  it('is on the multiples of the grid size a drag snaps to, whole metres drawn heavier', () => {
    const lines = planGrid(walls, 6, 4, 0.5);
    expect(upAndDownAt(lines, 2.5)).toHaveLength(1);
    expect(upAndDownAt(lines, 2.5)[0].major).toBe(false);
    expect(upAndDownAt(lines, 2)[0].major).toBe(true);
    expect(acrossAt(lines, -3.5)[0].major).toBe(false);
    expect(upAndDownAt(lines, 2.25)).toEqual([]);
    const snapped = snapToRoomGrid(5.3, -3.6, 0.5);
    expect(upAndDownAt(lines, snapped.x)).toHaveLength(1);
    expect(acrossAt(lines, snapped.z)).toHaveLength(1);
  });

  it('carries on over a deck that reaches beyond the room', () => {
    // A 16 m wide deck in the 12 m wide room.
    const lines = planGrid(walls, 16, 4, 1);
    expect(acrossAt(lines, 0).map(ends)).toEqual([[-8, 0, 8, 0]]);
    // Off the deck, which ends at z = 2, a line across stops at the walls.
    expect(acrossAt(lines, 3).map(ends)).toEqual([[-6, 3, 6, 3]]);
    // Beyond the wall there is only the deck to draw on.
    expect(upAndDownAt(lines, 7).map(ends)).toEqual([[7, -2, 7, 2]]);
  });

  it('draws nothing for a grid that is not one', () => {
    expect(planGrid(walls, 6, 4, 0)).toEqual([]);
    expect(planGrid(walls, 6, 4, -1)).toEqual([]);
    expect(planGrid(walls, 6, 4, Number.NaN)).toEqual([]);
  });
});

describe('planGrid: in an L-shaped room', () => {
  // The notch is x > 2 with z > 1. A 4 m by 2 m deck, well inside the room.
  const walls = roomPlan(L_ROOM)!.walls!;
  const lines = planGrid(walls, 4, 2, 1);

  it('runs a line the whole depth of the room where there is no notch', () => {
    expect(upAndDownAt(lines, 0).map(ends)).toEqual([[0, -5, 0, 5]]);
    expect(acrossAt(lines, 0).map(ends)).toEqual([[-6, 0, 6, 0]]);
  });

  it('stops a line at the notch\'s wall', () => {
    expect(upAndDownAt(lines, 4).map(ends)).toEqual([[4, -5, 4, 1]]);
    expect(acrossAt(lines, 3).map(ends)).toEqual([[-6, 3, 2, 3]]);
  });

  it('draws nothing in the notch, which is outside the walls', () => {
    for (const [x, z] of [[4, 3], [3, 2], [5, 4], [3.5, 3], [4, 2.5]]) {
      expect(drawnThrough(lines, x, z)).toBe(false);
    }
    // And does draw through the floor either side of it.
    expect(drawnThrough(lines, 4, 0)).toBe(true);
    expect(drawnThrough(lines, 1, 3)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Where a fixture clicked in the palette goes
// ---------------------------------------------------------------------------

describe('paletteClickSpot: with no scanned room', () => {
  it('is centre stage when nothing stands there', () => {
    expect(paletteClickSpot(10, 8, null, [], 0.6)).toEqual({ x: 0, z: 0 });
    expect(paletteClickSpot(10, 8, undefined, [{ x: 3, z: 1 }], 0.6)).toEqual({ x: 0, z: 0 });
  });

  it('steps clear of a fixture at centre stage, stage left first, as it always has', () => {
    expect(paletteClickSpot(10, 8, null, [{ x: 0, z: 0 }], 0.6)).toEqual({ x: 0.6, z: 0 });
    expect(paletteClickSpot(10, 8, null, [{ x: 0, z: 0 }, { x: 0.6, z: 0 }], 0.6)).toEqual({ x: -0.6, z: 0 });
    expect(paletteClickSpot(10, 8, null, [{ x: 0, z: 0 }, { x: 0.6, z: 0 }, { x: -0.6, z: 0 }], 0.6))
      .toEqual({ x: 0, z: 0.6 });
  });

  it('keeps each step on the deck', () => {
    // A 1 m square deck: every step straight out is held at 0.5 m, too close; the corner is clear.
    expect(paletteClickSpot(1, 1, null, [{ x: 0, z: 0 }], 0.6)).toEqual({ x: 0.5, z: 0.5 });
  });

  it('gives centre stage when there is nowhere clear', () => {
    expect(paletteClickSpot(0, 0, null, [{ x: 0, z: 0 }], 0.6)).toEqual({ x: 0, z: 0 });
  });

  it('is what a scan with truss and no room to hold to gets', () => {
    const walls = roomPlan({
      source: 'scan',
      truss_lines: [{ name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 }],
    })!.walls;
    expect(walls).toBeNull();
    expect(paletteClickSpot(1, 1, walls, [{ x: 0, z: 0 }], 0.6)).toEqual({ x: 0.5, z: 0.5 });
  });
});

describe('paletteClickSpot: in a scanned room', () => {
  // 12 m by 9 m.
  const box = roomPlan(BOX)!.walls!;

  it('is centre stage when the stage is inside the room', () => {
    expect(paletteClickSpot(6, 4, box, [], 0.6)).toEqual({ x: 0, z: 0 });
    expect(paletteClickSpot(6, 4, roomPlan(L_ROOM)!.walls, [], 0.6)).toEqual({ x: 0, z: 0 });
  });

  it('steps clear of other fixtures by the room\'s walls, not the deck\'s edge', () => {
    // The same 1 m square deck as above, in the 12 m wide room: a step is no longer held at 0.5 m.
    expect(paletteClickSpot(1, 1, box, [{ x: 0, z: 0 }], 0.6)).toEqual({ x: 0.6, z: 0 });
    const cross = [{ x: 0, z: 0 }, { x: 0.6, z: 0 }, { x: -0.6, z: 0 }, { x: 0, z: 0.6 }, { x: 0, z: -0.6 }];
    expect(paletteClickSpot(1, 1, box, cross, 0.6)).toEqual({ x: 0.6, z: 0.6 });
  });

  // An L whose notch takes in centre stage: x > -1 with z > -1 is outside the room.
  const AROUND = [
    { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: -1 }, { x: -1, z: -1 }, { x: -1, z: 5 }, { x: -6, z: 5 },
  ];
  const around = roomPlan({ source: 'scan', room: { width: 12, depth: 10, height: 5, outline: AROUND } })!.walls!;

  it('goes to the middle of the room\'s floor when centre stage is outside the walls', () => {
    expect(insideWalls(around, 0, 0)).toBe(false);
    const spot = paletteClickSpot(6, 4, around, [], 0.6);
    expect(insideWalls(around, spot.x, spot.z)).toBe(true);
    // A fixture's width clear of the walls, so its icon does not sit on one.
    expect(outlineClearance(AROUND, spot.x, spot.z)).toBeGreaterThanOrEqual(0.6 - 1e-9);
    // The floor's middle by area is at (-1.35, -1.08), just round the notch's corner.
    expect(Math.hypot(spot.x + 1.346, spot.z + 1.077)).toBeLessThan(0.6);
  });

  it('steps clear of a fixture already there, and stays inside the walls', () => {
    const first = paletteClickSpot(6, 4, around, [], 0.6);
    const second = paletteClickSpot(6, 4, around, [first], 0.6);
    expect(Math.hypot(second.x - first.x, second.z - first.z)).toBeGreaterThanOrEqual(0.6 - 1e-9);
    expect(insideWalls(around, second.x, second.z) || outlineClearance(AROUND, second.x, second.z) > -1e-9).toBe(true);
    const third = paletteClickSpot(6, 4, around, [first, second], 0.6);
    expect(Math.hypot(third.x - first.x, third.z - first.z)).toBeGreaterThanOrEqual(0.6 - 1e-9);
    expect(Math.hypot(third.x - second.x, third.z - second.z)).toBeGreaterThanOrEqual(0.6 - 1e-9);
  });

  it('says a position on a box room\'s wall is inside it, and one beyond is not', () => {
    expect(insideWalls(box, 6, 4.5)).toBe(true);
    expect(insideWalls(box, 6.01, 0)).toBe(false);
    expect(insideWalls(roomPlan(L_ROOM)!.walls!, 4, 3)).toBe(false);
  });
});
