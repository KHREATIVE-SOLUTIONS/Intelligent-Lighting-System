// Arranging a scanned room's items on the 2D plan, as numbers: which items
// can be picked up and by what place the server knows them, where the
// handles stand, and what a drag of each grip, or an arrow key, would send.
// docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import {
  ROTATE_STALK_M, dragItem, gripHint, isBoxGrip, itemHandles, nudgeItem, planItems, shapeCentre,
} from '../components/rig/roomItemDrag2d';
import type { ItemGrip, PlanItem } from '../components/rig/roomItemDrag2d';
import type { RoomShell } from '../types';

const SHELL: RoomShell = {
  source: 'scan',
  room: { width: 20, depth: 16, height: 6 },
  risers: [
    // Not drawn: its size is missing. It still has a place in the stored list.
    { center_x: 0, center_z: 0, name: 'Ghost' } as never,
    { center_x: 0, center_z: -5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: 2, x2: 4, z2: 2, height: 4.2 }],
  truss_rings: [{ name: 'Ring 1', center_x: 6, center_z: -4, radius: 1.5, height: 4 }],
};

const item = (key: string): PlanItem => planItems(SHELL).find((entry) => entry.key === key)!;
const GRID = { on: true, gridSize: 0.5 };
const FREE = { on: false, gridSize: 0.5 };

describe('planItems', () => {
  it('lists what the plan draws, each by its place in the stored list', () => {
    expect(planItems(SHELL).map((entry) => [entry.key, entry.kind, entry.index, entry.title])).toEqual([
      ['risers:1', 'risers', 1, 'Stage'],
      ['truss_lines:0', 'truss_lines', 0, 'Truss 1'],
      ['truss_rings:0', 'truss_rings', 0, 'Ring 1'],
    ]);
  });

  it('has nothing for no room, or one that is not from a scan', () => {
    expect(planItems(null)).toEqual([]);
    expect(planItems({ ...SHELL, source: 'preset' })).toEqual([]);
  });

  it('gives each its footprint', () => {
    expect(item('risers:1').shape).toEqual({ type: 'box', centerX: 0, centerZ: -5, width: 6, depth: 3 });
    expect(item('truss_lines:0').shape).toEqual({ type: 'line', x1: -4, z1: 2, x2: 4, z2: 2 });
    expect(item('truss_rings:0').shape).toEqual({ type: 'ring', centerX: 6, centerZ: -4, radius: 1.5 });
    expect(shapeCentre(item('truss_lines:0').shape)).toEqual({ x: 0, z: 2 });
  });
});

describe('itemHandles', () => {
  it('puts a length handle on a line\'s second end and a rotate handle past its first', () => {
    const handles = itemHandles(item('truss_lines:0').shape);
    expect(handles.map((handle) => handle.grip)).toEqual(['length', 'rotate']);
    expect(handles[0]).toMatchObject({ x: 4, z: 2 });
    expect(handles[1].x).toBeCloseTo(-4 - ROTATE_STALK_M);
    expect(handles[1].z).toBeCloseTo(2);
  });

  it('puts a radius handle on the stage left side of a ring', () => {
    expect(itemHandles(item('truss_rings:0').shape)).toEqual([{ grip: 'radius', x: 7.5, z: -4 }]);
  });

  it('puts a handle on each corner and each edge of a raised area', () => {
    // A stage 6 m by 3 m about (0, -5): upstage is the top of the plan.
    expect(itemHandles(item('risers:1').shape)).toEqual([
      { grip: 'nw', x: -3, z: -6.5 },
      { grip: 'n', x: 0, z: -6.5 },
      { grip: 'ne', x: 3, z: -6.5 },
      { grip: 'e', x: 3, z: -5 },
      { grip: 'se', x: 3, z: -3.5 },
      { grip: 's', x: 0, z: -3.5 },
      { grip: 'sw', x: -3, z: -3.5 },
      { grip: 'w', x: -3, z: -5 },
    ]);
  });

  it('knows a raised area\'s grips from the others, and words each', () => {
    expect(['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].every((grip) => isBoxGrip(grip as ItemGrip))).toBe(true);
    expect((['move', 'length', 'rotate', 'radius'] as ItemGrip[]).some(isBoxGrip)).toBe(false);
    expect(gripHint('e', 'Stage')).toBe('Stage: drag this edge to make it wider or narrower about its middle');
    expect(gripHint('n', 'Stage')).toBe('Stage: drag this edge to change its front to back about its middle');
    expect(gripHint('sw', 'Stage')).toBe(
      'Stage: drag this corner to change its width and its front to back about its middle',
    );
  });
});

describe('dragItem: a raised area\'s corners and edges', () => {
  const stage = () => item('risers:1');

  it('makes it wider from either side edge, about its middle: twice how far out the pointer is', () => {
    const dragged = dragItem(stage(), 'e', { x: 4.1, z: -5 }, GRID);
    expect(dragged.changes).toEqual({ width: 8 });
    expect(dragged.shape).toEqual({ type: 'box', centerX: 0, centerZ: -5, width: 8, depth: 3 });
    expect(dragged.readout).toBe('8.00 by 3.00 m');
    // The other side, pulled in: the pointer's depth says nothing to a side edge.
    expect(dragItem(stage(), 'w', { x: -2, z: 9 }, GRID).changes).toEqual({ width: 4 });
  });

  it('changes its front to back from the upstage or downstage edge', () => {
    expect(dragItem(stage(), 's', { x: 7, z: -3 }, GRID).changes).toEqual({ depth: 4 });
    const dragged = dragItem(stage(), 'n', { x: 0, z: -6 }, GRID);
    expect(dragged.changes).toEqual({ depth: 2 });
    expect(dragged.shape).toEqual({ type: 'box', centerX: 0, centerZ: -5, width: 6, depth: 2 });
  });

  it('changes both from a corner, in one change, and sends only the one that changed', () => {
    expect(dragItem(stage(), 'se', { x: 4, z: -3 }, GRID).changes).toEqual({ width: 8, depth: 4 });
    expect(dragItem(stage(), 'nw', { x: -2, z: -6 }, GRID).changes).toEqual({ width: 4, depth: 2 });
    // Dragged along the upstage edge: the front to back is what it was.
    expect(dragItem(stage(), 'ne', { x: 4, z: -6.5 }, GRID).changes).toEqual({ width: 8 });
  });

  it('never sends the middle: the server resizes about it', () => {
    for (const grip of ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'] as const) {
      const changes = dragItem(stage(), grip, { x: 5, z: -1 }, GRID).changes ?? {};
      expect(Object.keys(changes).every((key) => key === 'width' || key === 'depth')).toBe(true);
    }
  });

  it('goes to the grid\'s step with the snap on and to the millimetre with it off', () => {
    expect(dragItem(stage(), 'e', { x: 3.3, z: -5 }, GRID).changes).toEqual({ width: 6.5 });
    expect(dragItem(stage(), 'e', { x: 3.2504, z: -5 }, FREE).changes).toEqual({ width: 6.501 });
  });

  it('never makes a side shorter than a side can be', () => {
    expect(dragItem(stage(), 'e', { x: 0.05, z: -5 }, FREE).changes).toEqual({ width: 0.3 });
    expect(dragItem(stage(), 'se', { x: 0, z: -5 }, GRID).changes).toEqual({ width: 0.3, depth: 0.3 });
  });

  it('sends nothing for a handle let go where it stood', () => {
    const held = stage();
    const still = dragItem(held, 'e', { x: 3.1, z: -5 }, GRID);
    expect(still.changes).toBeNull();
    expect(still.shape).toBe(held.shape);
    expect(dragItem(stage(), 'sw', { x: -3, z: -3.5 }, FREE).changes).toBeNull();
  });

  it('is not a grip of a line or a ring', () => {
    expect(dragItem(item('truss_lines:0'), 'e', { x: 9, z: 9 }, GRID).changes).toBeNull();
    expect(dragItem(item('truss_rings:0'), 'nw', { x: 9, z: 9 }, GRID).changes).toBeNull();
  });
});

describe('dragItem', () => {
  it('moves the middle to the grid and sends the middle alone', () => {
    const dragged = dragItem(item('risers:1'), 'move', { x: 2.2, z: -3.9 }, GRID);
    expect(dragged.changes).toEqual({ center_x: 2, center_z: -4 });
    expect(dragged.shape).toEqual({ type: 'box', centerX: 2, centerZ: -4, width: 6, depth: 3 });
    expect(dragged.readout).toBe('2.00, -4.00');
  });

  it('lets go of the grid with the snap off, to the millimetre', () => {
    const dragged = dragItem(item('risers:1'), 'move', { x: 2.2004, z: -3.9 }, FREE);
    expect(dragged.changes).toEqual({ center_x: 2.2, center_z: -3.9 });
  });

  it('keeps a moved line\'s length and heading: both ends take the shift', () => {
    const dragged = dragItem(item('truss_lines:0'), 'move', { x: 1, z: 3 }, GRID);
    expect(dragged.changes).toEqual({ center_x: 1, center_z: 3 });
    expect(dragged.shape).toEqual({ type: 'line', x1: -3, z1: 3, x2: 5, z2: 3 });
  });

  it('sends nothing for a drag that ends where it began', () => {
    const dragged = dragItem(item('risers:1'), 'move', { x: 0.1, z: -5.1 }, GRID);
    expect(dragged.changes).toBeNull();
    expect(dragged.shape).toEqual(item('risers:1').shape);
  });

  it('makes a line longer about its middle: twice how far along it the pointer is', () => {
    const dragged = dragItem(item('truss_lines:0'), 'length', { x: 5, z: 2.3 }, GRID);
    expect(dragged.changes).toEqual({ length: 10 });
    expect(dragged.shape).toEqual({ type: 'line', x1: -5, z1: 2, x2: 5, z2: 2 });
    expect(dragged.readout).toBe('10.00 m long');
  });

  it('never makes a line shorter than a line can be', () => {
    expect(dragItem(item('truss_lines:0'), 'length', { x: 0.05, z: 2 }, FREE).changes).toEqual({ length: 0.5 });
  });

  it('turns a line about its middle to point at the pointer, folded as the server stores a heading', () => {
    // Straight upstage of the middle: -90, which a line with no front stores as 90.
    const upstage = dragItem(item('truss_lines:0'), 'rotate', { x: 0, z: -3 }, GRID);
    expect(upstage.changes).toEqual({ heading_deg: 90 });
    expect(upstage.readout).toBe('90 deg');
    // Up and to stage right: -135, stored as 45.
    const angled = dragItem(item('truss_lines:0'), 'rotate', { x: -3, z: -1 }, GRID);
    expect(angled.changes).toEqual({ heading_deg: 45 });
    const shape = angled.shape as { x1: number; z1: number; x2: number; z2: number };
    expect(Math.hypot(shape.x2 - shape.x1, shape.z2 - shape.z1)).toBeCloseTo(8);
    expect((shape.x1 + shape.x2) / 2).toBeCloseTo(0);
    expect((shape.z1 + shape.z2) / 2).toBeCloseTo(2);
  });

  it('goes to 5 degrees with the snap on and to a tenth with it off', () => {
    // Stage right of the middle and 0.7 m upstage of it: -170.1 degrees round, which is a line at 9.9.
    const at = { x: -4, z: 1.3 };
    expect(dragItem(item('truss_lines:0'), 'rotate', at, GRID).changes).toEqual({ heading_deg: 10 });
    expect(dragItem(item('truss_lines:0'), 'rotate', at, FREE).changes).toEqual({ heading_deg: 9.9 });
  });

  it('turns nothing for a pointer still on the handle, or on the middle', () => {
    expect(dragItem(item('truss_lines:0'), 'rotate', { x: -4.6, z: 2 }, GRID).changes).toBeNull();
    expect(dragItem(item('truss_lines:0'), 'rotate', { x: 0, z: 2 }, GRID).changes).toBeNull();
  });

  it('sets a ring\'s radius to how far out the pointer is, never under the least', () => {
    const dragged = dragItem(item('truss_rings:0'), 'radius', { x: 8.2, z: -4 }, GRID);
    expect(dragged.changes).toEqual({ radius: 2 });
    expect(dragged.shape).toEqual({ type: 'ring', centerX: 6, centerZ: -4, radius: 2 });
    expect(dragged.readout).toBe('radius 2.00 m');
    expect(dragItem(item('truss_rings:0'), 'radius', { x: 6.1, z: -4 }, FREE).changes).toEqual({ radius: 0.3 });
  });

  it('changes nothing for a grip the shape does not have', () => {
    expect(dragItem(item('risers:1'), 'radius', { x: 9, z: 9 }, GRID).changes).toBeNull();
    expect(dragItem(item('truss_rings:0'), 'length', { x: 9, z: 9 }, GRID).changes).toBeNull();
  });
});

describe('nudgeItem', () => {
  it('sends only the axis that moves', () => {
    expect(nudgeItem(item('risers:1'), 0.5, 0)).toEqual({ center_x: 0.5 });
    expect(nudgeItem(item('truss_lines:0'), 0, -5)).toEqual({ center_z: -3 });
    expect(nudgeItem(item('risers:1'), 0, 0)).toBeNull();
  });
});
