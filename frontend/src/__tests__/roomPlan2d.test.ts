// A scanned room on the 2D layout view: the shapes its room_shell comes to on
// the plan. The shells are as backend/app/services/room_scan/extract.py writes
// them. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import { planPolygonPoints, planViewBox, roomPlan } from '../components/rig/roomPlan2d';
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

// An L: 12 m by 10 m with its downstage stage-left corner walled off.
const L_OUTLINE = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
];

describe('roomPlan: a box room', () => {
  const plan = roomPlan(BOX)!;

  it('draws four walls at half the width and half the depth from the centre of the floor', () => {
    expect(plan.walls).not.toBeNull();
    expect(plan.walls!.outlined).toBe(false);
    expect(plan.walls!.points).toEqual([
      { x: -6, z: -4.5 }, { x: 6, z: -4.5 }, { x: 6, z: 4.5 }, { x: -6, z: 4.5 },
    ]);
    expect(plan.walls!.tooltip).toBe('Scanned room: 12.0 m wide, 9.0 m deep, 5.0 m high');
    expect(plan.bounds).toEqual({ xMin: -6, xMax: 6, zMin: -4.5, zMax: 4.5 });
  });

  it('draws each raised area from its upstage stage right corner, named and with its height', () => {
    expect(plan.raised).toHaveLength(3);
    const [stage, riser, booth] = plan.raised;
    expect(stage).toMatchObject({ x: -4, z: -4.5, width: 8, depth: 3, centerX: 0, centerZ: -3, kind: 'stage' });
    expect(stage.label).toBe('Stage · 0.90 m high');
    expect(stage.tooltip).toBe('Stage: 8.0 m by 3.0 m, top 0.90 m above the floor');
    // With no name of its own, one is taken from what its size suggests it is.
    expect(riser.label).toBe('Riser · 0.30 m high');
    expect(booth.label).toBe('Booth or counter · 1.00 m high');
  });

  it('measures a raised area standing on another from the floor', () => {
    const stacked = roomPlan({
      source: 'scan',
      risers: [{ center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, base_height: 0.9, kind: 'riser' }],
    })!;
    expect(stacked.raised[0].top).toBeCloseTo(1.2);
    expect(stacked.raised[0].label).toBe('Riser · 1.20 m high');
  });

  it('draws a truss across the room with the height it hangs at', () => {
    expect(plan.trussLines).toHaveLength(1);
    const [line] = plan.trussLines;
    expect(line).toMatchObject({ x1: -4, z1: -2, x2: 4, z2: -2, across: 0.3, height: 4.2 });
    expect(line.label).toBe('Truss 1 · hangs at 4.20 m');
    expect(line.tooltip).toBe('Truss 1: 8.0 m long, underside 4.20 m up, running across the room');
    expect(plan.trussRings).toEqual([]);
  });
});

describe('roomPlan: a room that is not a box', () => {
  const plan = roomPlan({ source: 'scan', room: { width: 12, depth: 10, height: 5, outline: L_OUTLINE } })!;

  it('draws the floor outline, corner for corner, in place of the box', () => {
    expect(plan.walls!.outlined).toBe(true);
    expect(plan.walls!.points).toEqual(L_OUTLINE);
    expect(plan.walls!.tooltip).toBe('Scanned room: 6 walls, 12.0 m wide, 10.0 m deep, 5.0 m high (the box round it)');
    expect(plan.bounds).toEqual({ xMin: -6, xMax: 6, zMin: -5, zMax: 5 });
  });

  it('falls back to the box for an outline that is not one', () => {
    const broken = roomPlan({
      source: 'scan',
      room: { width: 12, depth: 10, height: 5, outline: [{ x: 0, z: 0 }, { x: 1, z: 0 }] },
    })!;
    expect(broken.walls!.outlined).toBe(false);
    expect(broken.walls!.points).toHaveLength(4);
  });
});

describe('roomPlan: truss at an angle', () => {
  const half = Math.sqrt(3) * 2;
  const shell: RoomShell = {
    source: 'scan',
    room: { width: 12, depth: 10, height: 6 },
    truss_lines: [
      { name: 'Truss A', x1: -half, z1: -2, x2: half, z2: 2, height: 5.25, across: 0.4, axis: 'angled', heading_deg: 30 },
    ],
  };

  it('draws the line between its two ends and says how it runs', () => {
    const [line] = roomPlan(shell)!.trussLines;
    expect(line.x1).toBeCloseTo(-half);
    expect(line.z1).toBe(-2);
    expect(line.x2).toBeCloseTo(half);
    expect(line.z2).toBe(2);
    expect(line.across).toBe(0.4);
    expect(line.label).toBe('Truss A · hangs at 5.25 m');
    expect(line.tooltip).toBe('Truss A: 8.0 m long, underside 5.25 m up, running at 30 degrees to the room');
  });

  it('goes by the two ends alone: a shell stored before headings were written draws the same', () => {
    const old: RoomShell = {
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      truss_lines: [{ x1: 3, z1: -4, x2: 3, z2: 4, height: 5 }],
    };
    const plan = roomPlan(old)!;
    const [line] = plan.trussLines;
    expect(line).toMatchObject({ x1: 3, z1: -4, x2: 3, z2: 4, across: 0.3 });
    expect(line.label).toBe('Overhead line · hangs at 5.00 m');
    expect(line.tooltip).toContain('running upstage to downstage');
    expect(plan.trussRings).toEqual([]);
    expect(plan.walls!.outlined).toBe(false);
  });

  it('leaves out a line that cannot be drawn', () => {
    const plan = roomPlan({
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      truss_lines: [
        { x1: 0, z1: 0, x2: 0.1, z2: 0, height: 5 },
        { x1: 0, z1: 0, x2: Number.NaN, z2: 0, height: 5 },
      ],
    })!;
    expect(plan.trussLines).toEqual([]);
  });
});

describe('roomPlan: a ring of truss', () => {
  const shell: RoomShell = {
    source: 'scan',
    room: { width: 6, depth: 6, height: 6 },
    truss_rings: [{ name: 'Ring 1', center_x: 1, center_z: -1, radius: 2, height: 4.8, across: 0.3 }],
  };
  const plan = roomPlan(shell)!;

  it('draws a circle at its centre and radius with the height it hangs at', () => {
    expect(plan.trussRings).toHaveLength(1);
    const [ring] = plan.trussRings;
    expect(ring).toMatchObject({ centerX: 1, centerZ: -1, radius: 2, across: 0.3, height: 4.8 });
    expect(ring.label).toBe('Ring 1 · hangs at 4.80 m');
    expect(ring.tooltip).toBe('Ring 1: a ring 4.0 m across, underside 4.80 m up');
  });

  it('counts a ring that reaches beyond the walls in the bounds', () => {
    // The ring's outside edge is at x = 1 + 2 + 0.15, beyond the wall at 3.
    expect(plan.bounds.xMax).toBeCloseTo(3.15);
    expect(plan.bounds.zMin).toBeCloseTo(-3.15);
    expect(plan.bounds.xMin).toBe(-3);
    expect(plan.bounds.zMax).toBe(3);
  });
});

describe('roomPlan: nothing to draw', () => {
  it('is null with no shell', () => {
    expect(roomPlan(null)).toBeNull();
    expect(roomPlan(undefined)).toBeNull();
    expect(roomPlan({})).toBeNull();
  });

  it('is null for a shell that is not from a scan, whatever it carries', () => {
    const preset: RoomShell = {
      dome: { radius: 8, center_x: 0, center_z: 0, rim_height: 6, apex_height: 9 },
      dj_booth: { center_x: 0, center_z: -4, width: 3, depth: 1, height: 1 },
      room: { width: 12, depth: 9, height: 5 },
      risers: [{ center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3 }],
    };
    expect(roomPlan(preset)).toBeNull();
  });

  it('is null for a scan shell with nothing usable in it', () => {
    expect(roomPlan({ source: 'scan' })).toBeNull();
    expect(roomPlan({
      source: 'scan', room: { width: 0, depth: 9, height: 5 }, risers: [], truss_lines: [], truss_rings: [],
    })).toBeNull();
  });

  it('still draws what was found when the room itself cannot be drawn', () => {
    const plan = roomPlan({
      source: 'scan',
      room: null,
      risers: [{ center_x: 0, center_z: -2, width: 4, depth: 2, height: 0.6, kind: 'stage' }],
    })!;
    expect(plan.walls).toBeNull();
    expect(plan.raised).toHaveLength(1);
    expect(plan.bounds).toEqual({ xMin: -2, xMax: 2, zMin: -3, zMax: -1 });
  });
});

describe('planViewBox', () => {
  it('is the stage and its margin with no room', () => {
    expect(planViewBox(10, 8, 1, null)).toEqual({ minX: 0, minY: 0, width: 12, height: 10 });
    expect(planViewBox(10, 8, 1, undefined)).toEqual({ minX: 0, minY: 0, width: 12, height: 10 });
  });

  it('is unchanged by a room that fits inside the stage', () => {
    expect(planViewBox(10, 8, 1, { xMin: -4, xMax: 4, zMin: -3, zMax: 3 }))
      .toEqual({ minX: 0, minY: 0, width: 12, height: 10 });
  });

  it('grows to take in a room larger than the stage, with the same margin round it', () => {
    // A 20 m by 16 m room round a 10 m by 8 m stage: the wall at x = -10 is at
    // -4 in the view's units (x + 5 + 1), and the view starts a metre before it.
    expect(planViewBox(10, 8, 1, { xMin: -10, xMax: 10, zMin: -8, zMax: 8 }))
      .toEqual({ minX: -5, minY: -4, width: 22, height: 18 });
  });

  it('grows only on the sides the room reaches past', () => {
    expect(planViewBox(10, 8, 1, { xMin: -5, xMax: 9, zMin: -4, zMax: 4 }))
      .toEqual({ minX: 0, minY: 0, width: 16, height: 10 });
  });
});

describe('planPolygonPoints', () => {
  it('writes the corners in the view\'s units', () => {
    const points = planPolygonPoints([{ x: -6, z: -4.5 }, { x: 6, z: 4.5 }], (x) => x + 6, (z) => z + 5);
    expect(points).toBe('0,0.5 12,9.5');
  });
});
