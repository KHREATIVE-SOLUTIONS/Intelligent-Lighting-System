// Correcting a suggested layout quickly and safely, with no drawing: when a
// press becomes a drag, what a selection box takes in, how far an arrow key
// carries the selection, and whose key it is. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it } from 'vitest';
import {
  DRAG_THRESHOLD_PX, boxBetween, boxSelection, fixturesInBox, keysBelongElsewhere, nudgeMoves, nudgeShift,
  pastDragThreshold,
} from '../components/rig/planSelect2d';
import { roomPlan } from '../components/rig/roomPlan2d';
import type { RoomShell } from '../types';

const at = (id: number, x: number, z: number) => ({ id, position_x: x, position_z: z });

// ---------------------------------------------------------------------------
// When a press becomes a drag
// ---------------------------------------------------------------------------

describe('pastDragThreshold', () => {
  const down = { clientX: 100, clientY: 200 };

  it('is five screen pixels', () => {
    expect(DRAG_THRESHOLD_PX).toBe(5);
  });

  it('is not a drag where the pointer has not moved, or has moved under five pixels', () => {
    expect(pastDragThreshold(down, down)).toBe(false);
    expect(pastDragThreshold(down, { clientX: 104, clientY: 200 })).toBe(false);
    expect(pastDragThreshold(down, { clientX: 100, clientY: 196 })).toBe(false);
    // 3 across and 3 down is 4.24 pixels away.
    expect(pastDragThreshold(down, { clientX: 103, clientY: 203 })).toBe(false);
  });

  it('is a drag at five pixels and beyond, in any direction', () => {
    expect(pastDragThreshold(down, { clientX: 105, clientY: 200 })).toBe(true);
    expect(pastDragThreshold(down, { clientX: 95, clientY: 200 })).toBe(true);
    expect(pastDragThreshold(down, { clientX: 100, clientY: 205 })).toBe(true);
    expect(pastDragThreshold(down, { clientX: 100, clientY: 195 })).toBe(true);
    // 3 across and 4 up is exactly 5 pixels away.
    expect(pastDragThreshold(down, { clientX: 103, clientY: 196 })).toBe(true);
    // 4 across and 4 down is 5.66.
    expect(pastDragThreshold(down, { clientX: 96, clientY: 204 })).toBe(true);
  });

  it('goes by the threshold it is given', () => {
    expect(pastDragThreshold(down, { clientX: 108, clientY: 200 }, 10)).toBe(false);
    expect(pastDragThreshold(down, { clientX: 110, clientY: 200 }, 10)).toBe(true);
    expect(pastDragThreshold(down, down, 0)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// A selection box
// ---------------------------------------------------------------------------

describe('fixturesInBox', () => {
  const rig = [at(1, -2, -1), at(2, 0, 0), at(3, 2, 1), at(4, 4, 3)];

  it('puts a box\'s corners in order, whichever way it was dragged', () => {
    const want = { minX: -1, maxX: 3, minZ: -2, maxZ: 2 };
    expect(boxBetween({ x: -1, z: -2 }, { x: 3, z: 2 })).toEqual(want);
    expect(boxBetween({ x: 3, z: 2 }, { x: -1, z: -2 })).toEqual(want);
    expect(boxBetween({ x: -1, z: 2 }, { x: 3, z: -2 })).toEqual(want);
    expect(boxBetween({ x: 3, z: -2 }, { x: -1, z: 2 })).toEqual(want);
  });

  it('takes in the fixtures whose centre is inside, in the order they were given', () => {
    expect(fixturesInBox(rig, { x: -1, z: -2 }, { x: 3, z: 2 })).toEqual([2, 3]);
    expect(fixturesInBox(rig, { x: -5, z: -5 }, { x: 5, z: 5 })).toEqual([1, 2, 3, 4]);
  });

  it('takes in the same fixtures dragged in any of the four directions', () => {
    const corners = [
      [{ x: -1, z: -2 }, { x: 3, z: 2 }],
      [{ x: 3, z: 2 }, { x: -1, z: -2 }],
      [{ x: -1, z: 2 }, { x: 3, z: -2 }],
      [{ x: 3, z: -2 }, { x: -1, z: 2 }],
    ];
    for (const [a, b] of corners) expect(fixturesInBox(rig, a, b)).toEqual([2, 3]);
  });

  it('counts a centre on the box\'s edge as inside, and one just beyond it as outside', () => {
    expect(fixturesInBox(rig, { x: 0, z: 0 }, { x: 2, z: 1 })).toEqual([2, 3]);
    expect(fixturesInBox(rig, { x: 0.01, z: 0 }, { x: 1.99, z: 1 })).toEqual([]);
  });

  it('takes in nothing where there is nothing, and with no fixtures', () => {
    expect(fixturesInBox(rig, { x: 10, z: 10 }, { x: 12, z: 12 })).toEqual([]);
    expect(fixturesInBox([], { x: -5, z: -5 }, { x: 5, z: 5 })).toEqual([]);
  });
});

describe('boxSelection', () => {
  it('is what the box took in, in place of what was selected', () => {
    expect(boxSelection(new Set([1, 4]), [2, 3], false)).toEqual([2, 3]);
    expect(boxSelection(new Set([1, 4]), [], false)).toEqual([]);
  });

  it('adds what the box took in to what was selected, each fixture once', () => {
    expect(boxSelection(new Set([1, 2]), [2, 3], true)).toEqual([1, 2, 3]);
    // An additive box over empty floor takes nothing out.
    expect(boxSelection(new Set([1, 2]), [], true)).toEqual([1, 2]);
    expect(boxSelection(new Set<number>(), [3], true)).toEqual([3]);
  });
});

// ---------------------------------------------------------------------------
// Arrow keys
// ---------------------------------------------------------------------------

describe('nudgeShift', () => {
  it('is one grid step: left and right across the plan, up upstage, down downstage', () => {
    expect(nudgeShift('ArrowLeft', 0.5)).toEqual({ dx: -0.5, dz: 0 });
    expect(nudgeShift('ArrowRight', 0.5)).toEqual({ dx: 0.5, dz: 0 });
    expect(nudgeShift('ArrowUp', 0.5)).toEqual({ dx: 0, dz: -0.5 });
    expect(nudgeShift('ArrowDown', 0.5)).toEqual({ dx: 0, dz: 0.5 });
    expect(nudgeShift('ArrowRight', 0.25)).toEqual({ dx: 0.25, dz: 0 });
  });

  it('is ten grid steps with Shift', () => {
    expect(nudgeShift('ArrowLeft', 0.5, true)).toEqual({ dx: -5, dz: 0 });
    expect(nudgeShift('ArrowDown', 0.25, true)).toEqual({ dx: 0, dz: 2.5 });
  });

  it('is nothing for any other key, or with no grid step', () => {
    expect(nudgeShift('r', 0.5)).toBeNull();
    expect(nudgeShift('Escape', 0.5)).toBeNull();
    expect(nudgeShift('Enter', 0.5, true)).toBeNull();
    expect(nudgeShift('ArrowLeft', 0)).toBeNull();
    expect(nudgeShift('ArrowLeft', Number.NaN)).toBeNull();
  });
});

// 20 m by 16 m round a 10 m by 8 m deck.
const BOX_ROOM: RoomShell = { source: 'scan', suggested: true, room: { width: 20, depth: 16, height: 6 } };
// The same room as an L: x > 4 with z > 2 is walled off.
const L_ROOM: RoomShell = {
  ...BOX_ROOM,
  room: {
    width: 20, depth: 16, height: 6,
    outline: [
      { x: -10, z: -8 }, { x: 10, z: -8 }, { x: 10, z: 2 }, { x: 4, z: 2 }, { x: 4, z: 8 }, { x: -10, z: 8 },
    ],
  },
};
const boxWalls = roomPlan(BOX_ROOM)!.walls;
const lWalls = roomPlan(L_ROOM)!.walls;

/** The moves as [id, x, z], with no height among them. */
function places(moves: ReturnType<typeof nudgeMoves>) {
  for (const move of moves) expect('y' in move).toBe(false);
  return moves.map((move) => [move.id, move.x, move.z]);
}

describe('nudgeMoves', () => {
  const row = [at(1, -1, 0), at(2, 0, 0), at(3, 1, 0), at(4, 3, 3)];

  it('has a room to hold to in these tests', () => {
    expect(boxWalls).toBeTruthy();
    expect(lWalls!.outlined).toBe(true);
  });

  it('moves one selected fixture by the shift and no other', () => {
    expect(places(nudgeMoves(row, [2], { dx: 0.5, dz: 0 }, null, 10, 8))).toEqual([[2, 0.5, 0]]);
    expect(places(nudgeMoves(row, [2], { dx: 0, dz: -0.5 }, null, 10, 8))).toEqual([[2, 0, -0.5]]);
  });

  it('moves every selected fixture by the same shift, in the rig\'s order', () => {
    expect(places(nudgeMoves(row, new Set([3, 1, 2]), { dx: 0, dz: 0.5 }, null, 10, 8)))
      .toEqual([[1, -1, 0.5], [2, 0, 0.5], [3, 1, 0.5]]);
  });

  it('moves nothing with nothing selected, or for an id that is not in the rig', () => {
    expect(nudgeMoves(row, [], { dx: 0.5, dz: 0 }, null, 10, 8)).toEqual([]);
    expect(nudgeMoves(row, [99], { dx: 0.5, dz: 0 }, null, 10, 8)).toEqual([]);
  });

  it('cuts the whole selection\'s shift short at the deck\'s edge, keeping its spacing', () => {
    // The deck ends at x = 5. Five metres stage left would take Spot 3 to 6.
    expect(places(nudgeMoves(row, [1, 2, 3], { dx: 5, dz: 0 }, null, 10, 8)))
      .toEqual([[1, 3, 0], [2, 4, 0], [3, 5, 0]]);
    // And upstage the deck ends at z = -4.
    expect(places(nudgeMoves(row, [1, 2, 3], { dx: 0, dz: -5 }, null, 10, 8)))
      .toEqual([[1, -1, -4], [2, 0, -4], [3, 1, -4]]);
  });

  it('brings a fixture short of the edge onto it, to the millimetre', () => {
    expect(places(nudgeMoves([at(1, 4.8, 0)], [1], { dx: 0.5, dz: 0 }, null, 10, 8))).toEqual([[1, 5, 0]]);
  });

  it('moves nothing when the selection is already against the edge it is pushed at', () => {
    const atEdge = [at(1, 3, 0), at(2, 5, 0)];
    expect(nudgeMoves(atEdge, [1, 2], { dx: 0.5, dz: 0 }, null, 10, 8)).toEqual([]);
    // Along the edge, and away from it, it still goes.
    expect(places(nudgeMoves(atEdge, [1, 2], { dx: 0, dz: 0.5 }, null, 10, 8)))
      .toEqual([[1, 3, 0.5], [2, 5, 0.5]]);
    expect(places(nudgeMoves(atEdge, [1, 2], { dx: -0.5, dz: 0 }, null, 10, 8)))
      .toEqual([[1, 2.5, 0], [2, 4.5, 0]]);
  });

  it('carries on past the deck in a scanned room, and is held at its walls', () => {
    const out = [at(1, 5, 0), at(2, 6, 0)];
    expect(places(nudgeMoves(out, [1, 2], { dx: 0.5, dz: 0 }, boxWalls, 10, 8)))
      .toEqual([[1, 5.5, 0], [2, 6.5, 0]]);
    // The wall is at x = 10: Spot 2 stops on it and Spot 1 stays a metre behind.
    expect(places(nudgeMoves(out, [1, 2], { dx: 5, dz: 0 }, boxWalls, 10, 8)))
      .toEqual([[1, 9, 0], [2, 10, 0]]);
  });

  it('is held at the wall of an L\'s notch', () => {
    const inArm = [at(1, 2, 5), at(2, 3, 5)];
    // The notch's wall is at x = 4: two and a half metres stage left would
    // put both of them past it.
    expect(places(nudgeMoves(inArm, [1, 2], { dx: 2.5, dz: 0 }, lWalls, 10, 8)))
      .toEqual([[1, 3, 5], [2, 4, 5]]);
    expect(nudgeMoves([at(1, 3, 5), at(2, 4, 5)], [1, 2], { dx: 0.5, dz: 0 }, lWalls, 10, 8)).toEqual([]);
  });

  it('gives no height, so a nudge never changes one', () => {
    const moves = nudgeMoves(row, [1, 2, 3], { dx: 0.5, dz: 0 }, boxWalls, 10, 8);
    expect(moves).toHaveLength(3);
    for (const move of moves) expect(move.y).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Whose key it is
// ---------------------------------------------------------------------------

describe('keysBelongElsewhere', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  const made = (html: string) => {
    document.body.innerHTML = html;
    return document.body.querySelector('#it')!;
  };

  it('is true in an input, a textarea, a select and a contenteditable element', () => {
    expect(keysBelongElsewhere(made('<input id="it" />'))).toBe(true);
    expect(keysBelongElsewhere(made('<textarea id="it"></textarea>'))).toBe(true);
    expect(keysBelongElsewhere(made('<select id="it"><option>a</option></select>'))).toBe(true);
    expect(keysBelongElsewhere(made('<div id="it" contenteditable="true"></div>'))).toBe(true);
    expect(keysBelongElsewhere(made('<div id="it" contenteditable=""></div>'))).toBe(true);
    // And in anything inside one.
    expect(keysBelongElsewhere(made('<div contenteditable="true"><b id="it">x</b></div>'))).toBe(true);
  });

  it('is true in a drawn drop-down, its list, a menu and a dialog', () => {
    expect(keysBelongElsewhere(made('<div id="it" role="combobox" tabindex="0"></div>'))).toBe(true);
    expect(keysBelongElsewhere(made('<ul role="listbox"><li id="it" role="option">Grid</li></ul>'))).toBe(true);
    expect(keysBelongElsewhere(made('<ul role="menu"><li id="it" role="menuitem">Cut</li></ul>'))).toBe(true);
    expect(keysBelongElsewhere(made('<div role="dialog"><button id="it">Close</button></div>'))).toBe(true);
  });

  it('is false on a button, the page, an element that is not editable, and nothing at all', () => {
    expect(keysBelongElsewhere(made('<button id="it">Select row</button>'))).toBe(false);
    expect(keysBelongElsewhere(made('<div id="it" contenteditable="false"></div>'))).toBe(false);
    expect(keysBelongElsewhere(document.body)).toBe(false);
    expect(keysBelongElsewhere(null)).toBe(false);
    expect(keysBelongElsewhere(undefined)).toBe(false);
    expect(keysBelongElsewhere(document)).toBe(false);
    expect(keysBelongElsewhere(window)).toBe(false);
  });
});
