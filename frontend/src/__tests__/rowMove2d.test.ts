// Correcting a suggested layout a row at a time, with no drawing: which
// fixtures are one row, how far a row may be carried, what a snap onto
// scanned truss says, and a row move put on a rig and undone in one step.
// docs/ROOM_SCAN.md.
import { beforeEach, describe, expect, it } from 'vitest';
import { planTrussTargets, roomPlan } from '../components/rig/roomPlan2d';
import {
  heightIdsOf, heightsBefore, holdRowShift, onPlanTarget, rowOf, rowReadoutText, snapReadoutText, snapshotPositions,
  withMoves, withSnapshot,
} from '../components/rig/rowMove2d';
import type { RowFixture } from '../components/rig/rowMove2d';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { RoomShell } from '../types';

// 12 m by 10 m. Truss 1 straight across at z = -2, a truss at 45 degrees
// from (-5, 1) to (-1, 5), and a ring of radius 1.5 round (3, 2).
const SHELL: RoomShell = {
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  truss_lines: [
    { name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, across: 0.3 },
    { name: 'Angled', x1: -5, z1: 1, x2: -1, z2: 5, height: 5, across: 0.3, heading_deg: 45 },
  ],
  truss_rings: [{ name: 'Overhead A', center_x: 3, center_z: 2, radius: 1.5, height: 4.8, across: 0.3 }],
};
const [TRUSS, , RING] = planTrussTargets(SHELL);

// ---------------------------------------------------------------------------
// What a snap says
// ---------------------------------------------------------------------------

describe('the snap readout', () => {
  it('names the truss line and the height it hangs at', () => {
    expect(snapReadoutText(TRUSS)).toBe('On Truss 1 · hangs at 4.20 m');
  });

  it('says a ring is a ring when its name does not', () => {
    expect(snapReadoutText(RING)).toBe('On Overhead A (ring) · hangs at 4.80 m');
    expect(snapReadoutText({ ...RING, name: 'Ring 1' })).toBe('On Ring 1 · hangs at 4.80 m');
  });

  it('counts a row: all of it on the truss, or how many of it are', () => {
    expect(rowReadoutText(TRUSS, 3, 3)).toBe('Row of 3 on Truss 1 · hangs at 4.20 m');
    expect(rowReadoutText(TRUSS, 2, 4)).toBe('2 of 4 on Truss 1 · hangs at 4.20 m');
    expect(rowReadoutText(TRUSS, 1, 1)).toBe(snapReadoutText(TRUSS));
  });

  it('takes a position as on a truss within 5 cm of it, and not past its end', () => {
    expect(onPlanTarget(TRUSS, 1, -2)).toBe(true);
    expect(onPlanTarget(TRUSS, 1, -2.04)).toBe(true);
    expect(onPlanTarget(TRUSS, 1, -2.1)).toBe(false);
    expect(onPlanTarget(TRUSS, 4.5, -2)).toBe(false);
  });

  it('takes a position on a ring\'s circle as on it, and its centre as not', () => {
    expect(onPlanTarget(RING, 3, 3.5)).toBe(true);
    expect(onPlanTarget(RING, 3, 3)).toBe(false);
    expect(onPlanTarget(RING, 3, 2)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Which fixtures are one row
// ---------------------------------------------------------------------------

const fx = (id: number, x: number, y: number, z: number, group?: string): RowFixture => ({
  id, position_x: x, position_y: y, position_z: z, group_name: group,
});

const RIG: RowFixture[] = [
  fx(1, -2, 4.2, -2, 'Front'),
  fx(2, 0, 4.2, -2, 'Front'),
  // Of the group, though it stands somewhere else altogether.
  fx(3, 2, 1, 3, ' Front '),
  // No group, hanging from Truss 1.
  fx(4, -3, 4.2, -2),
  // 0.2 m off the truss and 0.1 m off its height: still hanging from it.
  fx(5, 3, 4.3, -2.2),
  // A metre off Truss 1: on nothing.
  fx(6, 3, 4.2, -1),
  // On the angled truss.
  fx(7, -3, 5, 3),
  fx(8, -4, 5, 2),
  // On the floor, at one depth to within 0.1 m.
  fx(9, 0, 0.5, 4),
  fx(10, 2, 0.5, 4.04),
  fx(11, 4, 0.5, 3),
  // Round the ring.
  fx(12, 3, 4.8, 0.5),
  fx(13, 4.5, 4.8, 2),
];

describe('rowOf', () => {
  it('is the whole group of a fixture that has one, wherever its members stand', () => {
    expect(rowOf(RIG, 1, SHELL)).toEqual([1, 2, 3]);
    expect(rowOf(RIG, 3, SHELL)).toEqual([1, 2, 3]);
  });

  it('is the ungrouped fixtures hanging from the same scanned truss line', () => {
    expect(rowOf(RIG, 4, SHELL)).toEqual([4, 5]);
    expect(rowOf(RIG, 5, SHELL)).toEqual([4, 5]);
  });

  it('finds a row laid along an angled truss, and one round a ring', () => {
    expect(rowOf(RIG, 7, SHELL)).toEqual([7, 8]);
    expect(rowOf(RIG, 13, SHELL)).toEqual([12, 13]);
  });

  it('is else the ungrouped fixtures at the same height and depth', () => {
    expect(rowOf(RIG, 9, SHELL)).toEqual([9, 10]);
    expect(rowOf(RIG, 11, SHELL)).toEqual([11]);
    expect(rowOf(RIG, 6, SHELL)).toEqual([6]);
  });

  it('goes by group, then height and depth, where there is no scanned room', () => {
    for (const shell of [null, undefined, { dome: { radius: 8, center_x: 0, center_z: 0, rim_height: 6, apex_height: 9 } }]) {
      expect(rowOf(RIG, 1, shell as RoomShell | null | undefined)).toEqual([1, 2, 3]);
      expect(rowOf(RIG, 9, shell as RoomShell | null | undefined)).toEqual([9, 10]);
      // Fixture 5 is 0.1 m higher and 0.2 m downstage: not level with 4.
      expect(rowOf(RIG, 4, shell as RoomShell | null | undefined)).toEqual([4]);
    }
  });

  it('is empty for a fixture that is not in the rig', () => {
    expect(rowOf(RIG, 99, SHELL)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// How far a row may be carried
// ---------------------------------------------------------------------------

const STILL = { dx: 0, dz: 0 };
const across = (z: number, ...xs: number[]) => xs.map((x) => ({ x, z }));

describe('holdRowShift: on the deck, with no scanned room', () => {
  // A 10 m by 8 m deck.
  it('leaves a shift that keeps the row on the deck as it is', () => {
    expect(holdRowShift(null, 10, 8, across(0, -1, 0, 1), STILL, { dx: 2, dz: 1 })).toEqual({ dx: 2, dz: 1 });
  });

  it('stops the whole row when its leading fixture reaches the deck\'s edge', () => {
    const shift = holdRowShift(null, 10, 8, across(0, -1, 0, 1), STILL, { dx: 9, dz: 0 });
    // The row's last fixture, at x = 1, stops at the edge at x = 5.
    expect(shift.dx).toBeCloseTo(4);
    expect(shift.dz).toBeCloseTo(0);
  });

  it('lets a row as wide as the deck move up and down stage but not across', () => {
    const shift = holdRowShift(undefined, 10, 8, across(0, -5, 0, 5), STILL, { dx: 1, dz: 2 });
    expect(shift.dx).toBeCloseTo(0);
    expect(shift.dz).toBeCloseTo(2);
  });
});

describe('holdRowShift: in a box room', () => {
  // 12 m by 10 m: walls at x = -6 and 6, z = -5 and 5.
  const walls = roomPlan(SHELL)!.walls!;

  it('lets the row go beyond the deck, out in the room', () => {
    expect(holdRowShift(walls, 6, 4, across(0, -1, 0, 1), STILL, { dx: 4, dz: 3 })).toEqual({ dx: 4, dz: 3 });
  });

  it('holds the row in a corner without closing it up', () => {
    const shift = holdRowShift(walls, 6, 4, across(0, -1, 0, 1), STILL, { dx: 10, dz: -7 });
    expect(shift.dx).toBeCloseTo(5);
    expect(shift.dz).toBeCloseTo(-5);
  });
});

describe('holdRowShift: in an L-shaped room', () => {
  // 12 m by 10 m with x > 2, z > 1 walled off: the notch.
  const L_OUTLINE = [
    { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 },
  ];
  const walls = roomPlan({ source: 'scan', room: { width: 12, depth: 10, height: 5, outline: L_OUTLINE } })!.walls!;

  it('stops the whole row when its leading fixture reaches the notch\'s wall', () => {
    const shift = holdRowShift(walls, 6, 4, across(3, -1, 0, 1), STILL, { dx: 3, dz: 0 });
    // The fixture at x = 1 stops on the wall at x = 2; the others keep their metre.
    expect(shift.dx).toBeCloseTo(1);
    expect(shift.dz).toBeCloseTo(0);
  });

  it('lets the row into the other arm of the L', () => {
    expect(holdRowShift(walls, 6, 4, across(3, -1, 0, 1), { dx: 1, dz: 0 }, { dx: 5, dz: -3 }))
      .toEqual({ dx: 5, dz: -3 });
  });

  it('does not hold a fixture that is already outside, until the row brings it in', () => {
    // The second stands in the notch.
    const starts = [{ x: 1, z: 3 }, { x: 3, z: 3 }];
    // Further into the notch: only the first is held, and it has room.
    expect(holdRowShift(walls, 6, 4, starts, STILL, { dx: 0.5, dz: 0 })).toEqual({ dx: 0.5, dz: 0 });
    // Once both are inside, both are held: the second stops on the notch's wall.
    const shift = holdRowShift(walls, 6, 4, starts, { dx: -1.5, dz: 0 }, STILL);
    expect(shift.dx).toBeCloseTo(-1);
    expect(shift.dz).toBeCloseTo(0);
  });
});

// ---------------------------------------------------------------------------
// A row move put on a rig, and undone
// ---------------------------------------------------------------------------

describe('withMoves', () => {
  const rig = [fx(1, -1, 4, 0), fx(2, 0, 4, 0), fx(3, 1, 4, 0)];

  it('moves the fixtures named and says which changed', () => {
    const next = withMoves(rig, [{ id: 1, x: 1, z: 2 }, { id: 3, x: 3, z: 2 }]);
    expect(next.changed).toEqual([1, 3]);
    expect(next.fixtures).toEqual([fx(1, 1, 4, 2), fx(2, 0, 4, 0), fx(3, 3, 4, 2)]);
  });

  it('changes a height only when the move gives one', () => {
    const next = withMoves(rig, [{ id: 2, x: 0, z: 0, y: 4.2 }]);
    expect(next.changed).toEqual([2]);
    expect(next.fixtures[1].position_y).toBe(4.2);
  });

  it('changes nothing for a move to where a fixture already is', () => {
    const next = withMoves(rig, [{ id: 1, x: -1, z: 0 }, { id: 2, x: 0, z: 0, y: 4 }]);
    expect(next.changed).toEqual([]);
    expect(next.fixtures[0]).toBe(rig[0]);
    expect(next.fixtures[1]).toBe(rig[1]);
  });
});

describe('the editor\'s selection and undo, for a row', () => {
  const store = () => useRigEditorStore.getState();

  beforeEach(() => {
    useRigEditorStore.setState({ selectedFixtureIds: new Set(), undoStack: [], redoStack: [] });
  });

  it('builds a selection one fixture at a time, and takes one back out', () => {
    store().selectFixture(1);
    store().selectFixture(2, true);
    store().selectFixture(3, true);
    expect([...store().selectedFixtureIds]).toEqual([1, 2, 3]);
    store().selectFixture(2, true);
    expect([...store().selectedFixtureIds]).toEqual([1, 3]);
    // Without a modifier it is that fixture alone.
    store().selectFixture(2);
    expect([...store().selectedFixtureIds]).toEqual([2]);
  });

  it('selects a whole row at once, in place of what was selected', () => {
    store().selectFixture(9);
    store().selectFixtures(rowOf(RIG, 4, SHELL));
    expect([...store().selectedFixtureIds]).toEqual([4, 5]);
  });

  it('undoes a row move in one step, heights and all, and redoes it', () => {
    const before = [fx(1, -1, 4, 0), fx(2, 0, 4, 0), fx(3, 1, 4, 0), fx(4, 3, 1, 3)];
    // One snapshot for the whole drag, as the editor takes on its first move.
    store().pushUndo(snapshotPositions(before));
    // The row carried onto a truss at z = -2 that hangs at 4.2 m, in two steps of the pointer.
    const first = [{ id: 1, x: -0.9, z: -1 }, { id: 2, x: 0.1, z: -1 }, { id: 3, x: 1.1, z: -1 }];
    store().noteUndoHeights(heightsBefore(before, first));
    const partWay = withMoves(before, first);
    const second = [
      { id: 1, x: -0.8, z: -2, y: 4.2 }, { id: 2, x: 0.2, z: -2, y: 4.2 }, { id: 3, x: 1.2, z: -2, y: 4.2 },
    ];
    store().noteUndoHeights(heightsBefore(partWay.fixtures, second));
    const after = withMoves(partWay.fixtures, second);
    expect(after.changed).toEqual([1, 2, 3]);
    expect(store().undoStack).toHaveLength(1);
    // The step knows the three heights the snap changed, and not the fourth fixture's.
    expect(heightIdsOf(store().undoStack[0])).toEqual([1, 2, 3]);

    const previous = store().undo(snapshotPositions(after.fixtures, heightIdsOf(store().undoStack[0])));
    const undone = withSnapshot(after.fixtures, previous!);
    // The three that moved are what is saved again, in one batch; the fourth never changed.
    expect(undone.changed).toEqual([1, 2, 3]);
    expect(undone.fixtures).toEqual(before);
    expect(store().undoStack).toHaveLength(0);

    const next = store().redo(snapshotPositions(undone.fixtures, heightIdsOf(store().redoStack[0])));
    const redone = withSnapshot(undone.fixtures, next!);
    expect(redone.changed).toEqual([1, 2, 3]);
    expect(redone.fixtures).toEqual(after.fixtures);
  });

  it('keeps the height from before the drag, not one from part way through it', () => {
    const before = [fx(1, 0, 4, 0)];
    store().pushUndo(snapshotPositions(before));
    // Onto a truss at 4.2 m, off it again, and onto one at 5 m.
    store().noteUndoHeights(heightsBefore(before, [{ id: 1, x: 0, z: -2, y: 4.2 }]));
    const onFirst = withMoves(before, [{ id: 1, x: 0, z: -2, y: 4.2 }]);
    store().noteUndoHeights(heightsBefore(onFirst.fixtures, [{ id: 1, x: 0, z: 3, y: 5 }]));
    expect(store().undoStack[0]).toEqual([{ id: 1, position_x: 0, position_y: 4, position_z: 0 }]);
  });

  it('leaves heights out of an undo when the drag changed none, as it always did', () => {
    const before = [fx(1, 0, 4, 0), fx(2, 2, 4, 0)];
    store().pushUndo(snapshotPositions(before));
    const move = [{ id: 1, x: 1, z: 1 }];
    store().noteUndoHeights(heightsBefore(before, move));
    expect(heightIdsOf(store().undoStack[0])).toEqual([]);
    // Both heights are then changed some other way: in the properties panel, say.
    const moved = withMoves(before, move).fixtures.map((f) => ({ ...f, position_y: 6 }));
    const previous = store().undo(snapshotPositions(moved, heightIdsOf(store().undoStack[0])));
    const undone = withSnapshot(moved, previous!);
    expect(undone.changed).toEqual([1]);
    expect(undone.fixtures).toEqual([fx(1, 0, 6, 0), fx(2, 2, 6, 0)]);
  });

  it('does not take back a height set on a fixture the row move did not carry', () => {
    const before = [fx(1, -1, 4, 0), fx(2, 0, 4, 0), fx(3, 3, 1, 3)];
    store().pushUndo(snapshotPositions(before));
    const move = [{ id: 1, x: -1, z: -2, y: 4.2 }, { id: 2, x: 0, z: -2, y: 4.2 }];
    store().noteUndoHeights(heightsBefore(before, move));
    // Fixture 3 is raised in the properties panel after the row was moved.
    const after = withMoves(withMoves(before, move).fixtures, [{ id: 3, x: 3, z: 3, y: 2.5 }]).fixtures;
    const previous = store().undo(snapshotPositions(after, heightIdsOf(store().undoStack[0])));
    const undone = withSnapshot(after, previous!);
    expect(undone.changed).toEqual([1, 2]);
    expect(undone.fixtures).toEqual([fx(1, -1, 4, 0), fx(2, 0, 4, 0), fx(3, 3, 2.5, 3)]);
  });

  it('leaves a height alone when a snapshot has none', () => {
    const back = withSnapshot([fx(1, 2, 4.2, 2)], [{ id: 1, position_x: 0, position_z: 0 }]);
    expect(back.changed).toEqual([1]);
    expect(back.fixtures).toEqual([fx(1, 0, 4.2, 0)]);
  });
});
