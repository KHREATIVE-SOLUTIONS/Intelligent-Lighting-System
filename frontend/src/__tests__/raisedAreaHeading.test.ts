// A raised area at a heading (slice 21), as numbers and words: how a heading
// is folded, where the corners of a turned stage stand, what the 2D plan, the
// 3D view and the 3D drag's snap lines make of it, where its handles stand on
// the plan and what a drag of each sends, and what its row in Edit Room and
// the Add form read and send. Nothing here draws or reaches a backend.
// docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import { snapLines } from '../components/rig/previs/fixtureDrag';
import {
  boxCorners, boxHeading, boxPoint, foldHeading, headingText, sideFacing,
} from '../components/rig/previs/raisedArea';
import { buildRisers } from '../components/rig/previs/roomShell';
import {
  HEADING_SHIFT_SNAP_DEG, HEADING_SNAP_DEG, ROTATE_STALK_M, dragItem, gripCursor, gripHint, itemHandles, planItems,
} from '../components/rig/roomItemDrag2d';
import type { PlanItem } from '../components/rig/roomItemDrag2d';
import { roomPlan } from '../components/rig/roomPlan2d';
import type { RoomShell } from '../types';
import {
  AREA_HEADING_LABEL, draftOf, editResultText, headingShown, newItemDraft, readDraft, readNewItem, shellItems,
  withCarry,
} from '../utils/roomShellEdit';
import type { ShellItem, ShellItemKind } from '../utils/roomShellEdit';

// A stage that stands square to the room, a deck turned a quarter turn, and a truss.
const SHELL = (deckHeading = 90): RoomShell => ({
  source: 'scan',
  room: { width: 20, depth: 16, height: 6 },
  risers: [
    { center_x: 0, center_z: -5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' },
    { center_x: 4, center_z: 3, width: 4, depth: 2, height: 0.3, heading_deg: deckHeading, name: 'Deck', kind: 'riser' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: 2, x2: 4, z2: 2, height: 4.2 }],
  truss_rings: [{ name: 'Ring 1', center_x: -6, center_z: 4, radius: 1.5, height: 4 }],
});

const planItem = (key: string, shell: RoomShell = SHELL()): PlanItem =>
  planItems(shell).find((entry) => entry.key === key)!;
const row = (kind: ShellItemKind, index: number, shell: RoomShell = SHELL()): ShellItem =>
  shellItems(shell).find((entry) => entry.kind === kind && entry.index === index)!;
const GRID = { on: true, gridSize: 0.5 };
const FREE = { on: false, gridSize: 0.5 };

describe('a heading as a raised area stores one', () => {
  it('is folded over -90 and up to 90, to a tenth: a rectangle looks the same after half a turn', () => {
    expect(foldHeading(0)).toBe(0);
    expect(foldHeading(30)).toBe(30);
    expect(foldHeading(90)).toBe(90);
    expect(foldHeading(-90)).toBe(90);
    expect(foldHeading(135)).toBe(-45);
    expect(foldHeading(-135)).toBe(45);
    expect(foldHeading(180)).toBe(0);
    // Never -0, which a field would show as "-0".
    expect(Object.is(foldHeading(-180), 0)).toBe(true);
    expect(foldHeading(270)).toBe(90);
    expect(foldHeading(30.04)).toBe(30);
    expect(foldHeading(44.96)).toBe(45);
  });

  it('is nothing for what is not a heading', () => {
    expect(foldHeading(360.5)).toBeNull();
    expect(foldHeading(Number.NaN)).toBeNull();
    expect(foldHeading('30')).toBeNull();
    expect(foldHeading(undefined)).toBeNull();
  });

  it('is 0, square to the room, for a box that stores none or stores nonsense', () => {
    expect(boxHeading({})).toBe(0);
    expect(boxHeading(null)).toBe(0);
    expect(boxHeading({ heading_deg: null })).toBe(0);
    expect(boxHeading({ heading_deg: 400 })).toBe(0);
    expect(boxHeading({ heading_deg: '30' as never })).toBe(0);
    expect(boxHeading({ heading_deg: 30 })).toBe(30);
    expect(boxHeading({ heading_deg: 135 })).toBe(-45);
  });

  it('is said after the size only when it is not 0', () => {
    expect(headingText(0)).toBe('');
    expect(headingText(null)).toBe('');
    expect(headingText(30)).toBe(', turned 30 degrees');
    expect(headingText(1)).toBe(', turned 1 degree');
    expect(headingText(-22.5)).toBe(', turned -22.5 degrees');
  });
});

describe('the footprint of a raised area', () => {
  it('has the corners the plain sums always gave for one that stands square', () => {
    expect(boxCorners({ center_x: 0, center_z: -5, width: 6, depth: 3 })).toEqual([
      { x: -3, z: -6.5 }, { x: 3, z: -6.5 }, { x: 3, z: -3.5 }, { x: -3, z: -3.5 },
    ]);
    expect(boxPoint({ center_x: 1, center_z: 2, width: 4, depth: 2 }, 0.5, -1)).toEqual({ x: 1.5, z: 1 });
  });

  it('is turned clockwise about its middle seen from above, as the server turns it', () => {
    // 4 m by 2 m about (1, 2), a quarter turn: its width now runs upstage to downstage.
    const corners = boxCorners({ center_x: 1, center_z: 2, width: 4, depth: 2, heading_deg: 90 });
    const expected = [[2, 0], [2, 4], [0, 4], [0, 0]];
    corners.forEach((corner, index) => {
      expect(corner.x).toBeCloseTo(expected[index][0]);
      expect(corner.z).toBeCloseTo(expected[index][1]);
    });
    // At 30 degrees the end of its width is along the heading from its middle.
    const end = boxPoint({ center_x: 0, center_z: 0, width: 4, depth: 2, heading_deg: 30 }, 2, 0);
    expect(end.x).toBeCloseTo(Math.sqrt(3));
    expect(end.z).toBeCloseTo(1);
  });

  it('names each side by the way it faces, and no two the same at 45 degrees', () => {
    expect(sideFacing(0, -1, true)).toBe('upstage');
    expect(sideFacing(0, 1, true)).toBe('downstage');
    expect(sideFacing(-1, 0, false)).toBe('stage right');
    expect(sideFacing(1, 0, false)).toBe('stage left');
    expect(sideFacing(1, 1, true)).toBe('downstage');
    expect(sideFacing(1, 1, false)).toBe('stage left');
  });
});

describe('a turned raised area in the views', () => {
  it('is on the 2D plan with its heading, its corners and the words for it', () => {
    const plan = roomPlan(SHELL(30))!;
    const [stage, deck] = plan.raised;
    // One that stands square says nothing new.
    expect('heading' in stage).toBe(false);
    expect('corners' in stage).toBe(false);
    expect(stage.tooltip).toBe('Stage: 6.0 m by 3.0 m, top 0.60 m above the floor');
    // The turned one is the same rectangle, to be drawn turned about its middle.
    expect(deck).toMatchObject({ x: 2, z: 2, width: 4, depth: 2, centerX: 4, centerZ: 3, heading: 30 });
    expect(deck.corners).toHaveLength(4);
    expect(deck.label).toBe('Deck · 0.30 m high');
    expect(deck.tooltip).toBe('Deck: 4.0 m by 2.0 m, turned 30 degrees, top 0.30 m above the floor');
  });

  it('makes the plan as big as its corners reach', () => {
    // 6 m by 2 m against the downstage wall of a 16 m deep room: square, it ends at the wall.
    const against = (heading?: number): RoomShell => ({
      source: 'scan',
      room: { width: 20, depth: 16, height: 6 },
      risers: [{ center_x: 0, center_z: 7, width: 6, depth: 2, height: 0.6, heading_deg: heading, name: 'Stage' }],
    });
    expect(roomPlan(against())!.bounds.zMax).toBeCloseTo(8);
    // A quarter turn stands its 6 m front to back: 3 m either side of its middle.
    expect(roomPlan(against(90))!.bounds.zMax).toBeCloseTo(10);
  });

  it('is built turned in the 3D view, the same way round as on the plan', () => {
    const square = buildRisers([{ center_x: 0, center_z: -5, width: 6, depth: 2, height: 0.6 }])!;
    square.computeBoundingBox();
    // The deck, and the top plate that overhangs it by 0.02 m.
    expect(square.boundingBox!.max.x).toBeCloseTo(3.02);
    expect(square.boundingBox!.max.z).toBeCloseTo(-3.98);

    const quarter = buildRisers([{ center_x: 0, center_z: -5, width: 6, depth: 2, height: 0.6, heading_deg: 90 }])!;
    quarter.computeBoundingBox();
    expect(quarter.boundingBox!.max.x).toBeCloseTo(1.02);
    expect(quarter.boundingBox!.min.x).toBeCloseTo(-1.02);
    expect(quarter.boundingBox!.max.z).toBeCloseTo(-1.98);
    expect(quarter.boundingBox!.min.z).toBeCloseTo(-8.02);
    // Still a deck 0.6 m high on the floor.
    expect(quarter.boundingBox!.min.y).toBeCloseTo(0);

    // At 30 degrees the corner furthest stage left is the upstage one: clockwise seen from above.
    // Turned the other way it would be the downstage one, at a depth of about -5.63.
    const turned = buildRisers([{ center_x: 0, center_z: -5, width: 6, depth: 2, height: 0.6, heading_deg: 30 }])!;
    const position = turned.getAttribute('position');
    let furthest = 0;
    for (let index = 1; index < position.count; index += 1) {
      if (position.getX(index) > position.getX(furthest)) furthest = index;
    }
    const plate = boxPoint({ center_x: 0, center_z: -5, width: 6.04, depth: 2.04, heading_deg: 30 }, 3.02, -1.02);
    expect(position.getX(furthest)).toBeCloseTo(plate.x, 3);
    expect(position.getZ(furthest)).toBeCloseTo(plate.z, 3);
    expect(plate.z).toBeCloseTo(-4.373, 2);
  });

  it('offers the 3D drag its four edges where they stand, each called by the way it faces', () => {
    const shell = {
      source: 'scan',
      room: { width: 20, depth: 12, height: 7 },
      risers: [{ center_x: 0, center_z: -3, width: 6, depth: 2, height: 1, heading_deg: 90, name: 'Stage' }],
    } as unknown as RoomShell;
    const lines = snapLines(shell);
    expect(lines.map((line) => line.name).sort()).toEqual([
      'Stage, downstage edge', 'Stage, stage left edge', 'Stage, stage right edge', 'Stage, upstage edge',
    ]);
    // A quarter turn: 2 m across and 6 m front to back, so its downstage edge is at 0 and 2 m long.
    const downstage = lines.find((line) => line.name === 'Stage, downstage edge')!;
    expect(downstage.z1).toBeCloseTo(0);
    expect(downstage.z2).toBeCloseTo(0);
    expect(Math.abs(downstage.x2 - downstage.x1)).toBeCloseTo(2);
    expect(downstage).toMatchObject({ height: 1, kind: 'edge' });
    const left = lines.find((line) => line.name === 'Stage, stage left edge')!;
    expect(left.x1).toBeCloseTo(1);
    expect(left.x2).toBeCloseTo(1);
    expect(Math.abs(left.z2 - left.z1)).toBeCloseTo(6);

    // At 45 degrees each side faces two ways as much: still four names.
    const diamond = { ...shell, risers: [{ ...shell.risers![0], heading_deg: 45 }] } as RoomShell;
    expect(new Set(snapLines(diamond).map((line) => line.name)).size).toBe(4);
  });
});

describe('a raised area\'s handles on the plan', () => {
  it('gives the plan its heading only when it is turned', () => {
    expect(planItem('risers:0').shape).toEqual({ type: 'box', centerX: 0, centerZ: -5, width: 6, depth: 3 });
    expect('heading' in planItem('risers:0').shape).toBe(false);
    expect(planItem('risers:1').shape).toEqual({ type: 'box', centerX: 4, centerZ: 3, width: 4, depth: 2, heading: 90 });
  });

  it('has a rotate handle on a stalk past the upstage edge, after the eight that resize it', () => {
    const handles = itemHandles(planItem('risers:0').shape);
    expect(handles.map((handle) => handle.grip)).toEqual(['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w', 'rotate']);
    expect(handles[8].x).toBeCloseTo(0);
    expect(handles[8].z).toBeCloseTo(-6.5 - ROTATE_STALK_M);
    expect(gripHint('rotate', 'Stage')).toBe(
      'Stage: drag to turn it about its middle (hold Shift for steps of 15 degrees)',
    );
  });

  it('stands every handle on the area as it is turned', () => {
    // The deck is 4 m by 2 m about (4, 3), a quarter turn: its own stage left edge is now downstage.
    const handles = itemHandles(planItem('risers:1').shape);
    const where = (grip: string) => handles.find((handle) => handle.grip === grip)!;
    expect(where('e').x).toBeCloseTo(4);
    expect(where('e').z).toBeCloseTo(5);
    expect(where('n').x).toBeCloseTo(5);
    expect(where('n').z).toBeCloseTo(3);
    expect(where('se').x).toBeCloseTo(3);
    expect(where('se').z).toBeCloseTo(5);
    expect(where('rotate').x).toBeCloseTo(5 + ROTATE_STALK_M);
    expect(where('rotate').z).toBeCloseTo(3);
  });

  it('shows the arrow for the way each handle pulls, turned with the area', () => {
    expect(gripCursor('rotate')).toBe('alias');
    expect(gripCursor('length')).toBe('pointer');
    expect(gripCursor('move')).toBe('pointer');
    // Square to the room: as the plan's compass has them.
    expect(['e', 'w'].map((grip) => gripCursor(grip as never))).toEqual(['ew-resize', 'ew-resize']);
    expect(['n', 's'].map((grip) => gripCursor(grip as never))).toEqual(['ns-resize', 'ns-resize']);
    expect(['nw', 'se'].map((grip) => gripCursor(grip as never))).toEqual(['nwse-resize', 'nwse-resize']);
    expect(['ne', 'sw'].map((grip) => gripCursor(grip as never))).toEqual(['nesw-resize', 'nesw-resize']);
    // A quarter turn swaps the edges' arrows, and 45 degrees gives an edge a corner's.
    expect(gripCursor('e', 90)).toBe('ns-resize');
    expect(gripCursor('n', 90)).toBe('ew-resize');
    expect(gripCursor('nw', 90)).toBe('nesw-resize');
    expect(gripCursor('e', 45)).toBe('nwse-resize');
    expect(gripCursor('e', -45)).toBe('nesw-resize');
    // The nearest of the four: 20 degrees is still mostly across the room.
    expect(gripCursor('e', 20)).toBe('ew-resize');
  });
});

describe('dragItem: a raised area\'s rotate handle', () => {
  const stage = () => planItem('risers:0');

  it('turns it about its middle so that the handle points at the pointer', () => {
    // The stage's middle is (0, -5). Up and stage left of it is 45 degrees clockwise.
    const turned = dragItem(stage(), 'rotate', { x: 3, z: -8 }, GRID);
    expect(turned.changes).toEqual({ heading_deg: 45 });
    expect(turned.shape).toEqual({ type: 'box', centerX: 0, centerZ: -5, width: 6, depth: 3, heading: 45 });
    expect(turned.readout).toBe('45 deg');
    // The handle is then where the pointer has it: on the pointer's side of the middle.
    const handle = itemHandles(turned.shape).find((entry) => entry.grip === 'rotate')!;
    expect(handle.x).toBeGreaterThan(0);
    expect(handle.z).toBeLessThan(-5);
    // Straight stage left of the middle is a quarter turn.
    expect(dragItem(stage(), 'rotate', { x: 3, z: -5 }, GRID).changes).toEqual({ heading_deg: 90 });
  });

  it('sends the heading folded, and draws the turn the pointer has it at', () => {
    // Downstage and stage left of the middle: 135 degrees round, which is the same rectangle as -45.
    const turned = dragItem(stage(), 'rotate', { x: 3, z: -2 }, GRID);
    expect(turned.changes).toEqual({ heading_deg: -45 });
    expect(turned.shape).toMatchObject({ heading: 135 });
    expect(turned.readout).toBe('-45 deg');
  });

  it('sends nothing where the pointer has it as it already stands, or says nothing', () => {
    // Straight upstage, where the handle is; straight downstage, half a turn on; and on the middle itself.
    expect(dragItem(stage(), 'rotate', { x: 0, z: -8 }, GRID).changes).toBeNull();
    expect(dragItem(stage(), 'rotate', { x: 0, z: -2 }, GRID).changes).toBeNull();
    expect(dragItem(stage(), 'rotate', { x: 0, z: -5 }, GRID).changes).toBeNull();
    // The deck stands at 90: its handle is straight stage left of its middle, (4, 3).
    expect(dragItem(planItem('risers:1'), 'rotate', { x: 6, z: 3 }, GRID).changes).toBeNull();
    expect(dragItem(planItem('risers:1'), 'rotate', { x: 6, z: 5 }, GRID).changes).toEqual({ heading_deg: -45 });
  });

  it('goes to 5 degrees with the snap on, a tenth without, and 15 with Shift either way', () => {
    expect(HEADING_SNAP_DEG).toBe(5);
    expect(HEADING_SHIFT_SNAP_DEG).toBe(15);
    // 18.4 degrees clockwise of straight upstage.
    const at = { x: 1, z: -8 };
    expect(dragItem(stage(), 'rotate', at, GRID).changes).toEqual({ heading_deg: 20 });
    expect(dragItem(stage(), 'rotate', at, FREE).changes).toEqual({ heading_deg: 18.4 });
    const shifted = dragItem(stage(), 'rotate', at, { ...GRID, coarse: true });
    expect(shifted.changes).toEqual({ heading_deg: 15 });
    expect(shifted.readout).toBe('15 deg');
    expect(dragItem(stage(), 'rotate', at, { ...FREE, coarse: true }).changes).toEqual({ heading_deg: 15 });
  });

  it('turns a truss line in steps of 15 degrees with Shift too', () => {
    // The truss's middle is (0, 2). The pointer is 161.6 degrees round from stage left of it.
    const at = { x: -3, z: 1 };
    expect(dragItem(planItem('truss_lines:0'), 'rotate', at, GRID).changes).toEqual({ heading_deg: 20 });
    expect(dragItem(planItem('truss_lines:0'), 'rotate', at, { ...GRID, coarse: true }).changes).toEqual({
      heading_deg: 15,
    });
  });
});

describe('dragItem: resizing a raised area that is turned', () => {
  const deck = () => planItem('risers:1');

  it('pulls an edge along the area\'s own width, not across the room', () => {
    // A quarter turn: the deck's width runs downstage, and its 'e' edge is at (4, 5).
    const wider = dragItem(deck(), 'e', { x: 4, z: 6 }, GRID);
    expect(wider.changes).toEqual({ width: 6 });
    expect(wider.shape).toEqual({ type: 'box', centerX: 4, centerZ: 3, width: 6, depth: 2, heading: 90 });
    expect(wider.readout).toBe('6.00 by 2.00 m');
    // Carried across the room instead, the edge is no further along its own width.
    expect(dragItem(deck(), 'e', { x: 7, z: 5 }, GRID).changes).toBeNull();
  });

  it('pulls the other pair of edges along its own front to back', () => {
    // Its 'n' edge is at (5, 3), stage left of its middle.
    expect(dragItem(deck(), 'n', { x: 6.5, z: 3 }, GRID).changes).toEqual({ depth: 5 });
    expect(dragItem(deck(), 's', { x: 2, z: 9 }, GRID).changes).toEqual({ depth: 4 });
  });

  it('changes both from a corner, each along its own side', () => {
    // Its 'se' corner is at (3, 5).
    const dragged = dragItem(deck(), 'se', { x: 2, z: 6 }, GRID);
    expect(dragged.changes).toEqual({ width: 6, depth: 4 });
    expect(dragged.shape).toMatchObject({ width: 6, depth: 4, heading: 90 });
  });

  it('measures along the heading at any angle', () => {
    const angled: PlanItem = {
      ...planItem('risers:0'),
      shape: { type: 'box', centerX: 0, centerZ: 0, width: 6, depth: 3, heading: 30 },
    };
    // 4 m from the middle along 30 degrees: 8 m wide.
    const at = { x: 4 * Math.cos(Math.PI / 6), z: 4 * Math.sin(Math.PI / 6) };
    expect(dragItem(angled, 'e', at, FREE).changes).toEqual({ width: 8 });
    // The same pointer says nothing to the edge that pulls square to that.
    expect(dragItem(angled, 'n', at, FREE).changes).toEqual({ depth: 0.3 });
  });
});

describe('roomShellEdit: a raised area\'s heading', () => {
  it('lists a raised area with the heading it stands at, and a truss or a ring with none', () => {
    expect(row('risers', 0).heading).toBe(0);
    expect(row('risers', 1, SHELL(30)).heading).toBe(30);
    expect(row('truss_lines', 0).heading).toBeNull();
    expect(row('truss_rings', 0).heading).toBeNull();
    // Its size fields are what they were: the heading is not among them.
    expect(row('risers', 1, SHELL(30)).sizes).toEqual({ width: 4, depth: 2, height: 0.3 });
    expect(row('risers', 0).detail).toBe('6.0 m by 3.0 m, top 0.60 m above the floor');
    expect(row('risers', 1, SHELL(30)).detail).toBe('4.0 m by 2.0 m, turned 30 degrees, top 0.30 m above the floor');
  });

  it('leaves the heading out of a row\'s draft until it is touched, and shows what is stored', () => {
    const stage = row('risers', 0);
    const deck = row('risers', 1, SHELL(30));
    expect(draftOf(stage).heading_deg).toBeUndefined();
    expect(headingShown(stage, draftOf(stage))).toBe('0');
    expect(headingShown(deck, draftOf(deck))).toBe('30');
    expect(headingShown(stage, { ...draftOf(stage), heading_deg: '12.5' })).toBe('12.5');
    expect(headingShown(row('truss_rings', 0), draftOf(row('truss_rings', 0)))).toBe('');
    expect(AREA_HEADING_LABEL).toBe('Heading');
  });

  it('reads a heading from a row, and only one that differs from what is stored', () => {
    const stage = row('risers', 0);
    const deck = row('risers', 1, SHELL(30));
    expect(readDraft(stage, draftOf(stage))).toEqual({ changes: null, problem: null });
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '30' }).changes).toEqual({ heading_deg: 30 });
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '22,5' }).changes).toEqual({ heading_deg: 22.5 });
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: ' 0 ' })).toEqual({ changes: null, problem: null });
    // Sent as typed: the server folds it.
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '135' }).changes).toEqual({ heading_deg: 135 });
    // Half a turn is the same rectangle, and so is what reads the same to a tenth.
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '180' })).toEqual({ changes: null, problem: null });
    expect(readDraft(deck, { ...draftOf(deck), heading_deg: '30.04' })).toEqual({ changes: null, problem: null });
    expect(readDraft(deck, { ...draftOf(deck), heading_deg: '210' })).toEqual({ changes: null, problem: null });
    // Stood square again.
    expect(readDraft(deck, { ...draftOf(deck), heading_deg: '0' }).changes).toEqual({ heading_deg: 0 });
    // With whatever else the row changes, in one reading.
    expect(readDraft(stage, { ...draftOf(stage), width: '8', heading_deg: '-15' }).changes).toEqual({
      width: 8, heading_deg: -15,
    });
  });

  it('says what is wrong with a heading and sends nothing', () => {
    const stage = row('risers', 0);
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: 'left' })).toEqual({
      changes: null, problem: 'Heading must be a number of degrees, such as 45 or -30.',
    });
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '' }).problem).toBe(
      'Heading must be a number of degrees, such as 45 or -30.',
    );
    expect(readDraft(stage, { ...draftOf(stage), heading_deg: '400' })).toEqual({
      changes: null, problem: 'Heading must be between -360 and 360 degrees.',
    });
  });

  it('sends the flag with a turn, which swings what stands on it', () => {
    expect(withCarry(row('risers', 0), { heading_deg: 30 }, true)).toEqual({ heading_deg: 30, carry_fixtures: true });
    expect(withCarry(row('risers', 0), { heading_deg: 30 }, false)).toEqual({ heading_deg: 30, carry_fixtures: false });
  });

  it('says what a turn did, and what became of the fixtures standing on it', () => {
    const after = SHELL();
    after.risers![0] = { ...after.risers![0], heading_deg: 30 };
    expect(editResultText(row('risers', 0), { heading_deg: 30 }, after, { moved: 2, asked: true })).toBe(
      'Stage is now 6.0 m by 3.0 m, turned 30 degrees, top 0.60 m above the floor. '
      + '2 fixtures standing on it moved with it.',
    );
    expect(editResultText(row('risers', 0), { heading_deg: 30 }, after, { moved: 0, asked: false })).toBe(
      'Stage is now 6.0 m by 3.0 m, turned 30 degrees, top 0.60 m above the floor. '
      + 'The fixtures standing on it were left where they are.',
    );
  });

  it('adds a raised area at a heading, and says nothing of one that stands square', () => {
    expect(newItemDraft('stage').heading_deg).toBe('0');
    const square = readNewItem(newItemDraft('stage'));
    expect(square.problem).toBeNull();
    expect(square.body).toEqual({ center_x: 0, center_z: 0, width: 4, depth: 3, height: 0.6, riser_kind: 'stage' });
    expect(readNewItem({ ...newItemDraft('stage'), heading_deg: '' }).body).toEqual(square.body);
    expect(readNewItem({ ...newItemDraft('stage'), heading_deg: '180' }).body).toEqual(square.body);

    const turned = readNewItem({ ...newItemDraft('riser'), heading_deg: '30', base_height: '0.6' });
    expect(turned.kind).toBe('risers');
    expect(turned.body).toEqual({
      center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser', base_height: 0.6, heading_deg: 30,
    });
    expect(readNewItem({ ...newItemDraft('booth'), heading_deg: '-45' }).body).toMatchObject({ heading_deg: -45 });
  });

  it('refuses a heading that is not one on the Add form, and does not read it for a ring', () => {
    expect(readNewItem({ ...newItemDraft('stage'), heading_deg: 'round' })).toMatchObject({
      body: null, problem: 'Heading must be a number of degrees, such as 45 or -30.',
    });
    expect(readNewItem({ ...newItemDraft('stage'), heading_deg: '361' })).toMatchObject({
      body: null, problem: 'Heading must be between -360 and 360 degrees.',
    });
    const ring = readNewItem({ ...newItemDraft('truss_ring'), heading_deg: 'round' });
    expect(ring.problem).toBeNull();
    expect(ring.body).not.toHaveProperty('heading_deg');
    // A line's heading is one of its sizes, as it was: sent even at 0.
    expect(readNewItem(newItemDraft('truss_line')).body).toMatchObject({ heading_deg: 0 });
  });
});
