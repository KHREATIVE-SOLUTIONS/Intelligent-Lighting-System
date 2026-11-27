// Editing a stored room's walls by hand: the corners as the server numbers
// them, what a corner's row and the height field would send, and the words
// for what the walls leave outside. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import {
  cornerDraftOf, outsideHeading, outsideLines, outsideOf, readCorner, readRoomHeight, roomHeight, wallCorners,
  wallsSizeText,
} from '../utils/roomWallsEdit';
import { roomOutlineCornerPath, roomOutlineCornersPath, roomOutlinePath } from '../utils/roomScan';
import type { RoomShell } from '../types';

const BOX: RoomShell = { source: 'scan', room: { width: 12, depth: 10, height: 6 } };
const L_OUTLINE = [
  { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 0 }, { x: 0, z: 0 }, { x: 0, z: 5 }, { x: -6, z: 5 },
];
const L_SHAPED: RoomShell = { source: 'scan', room: { width: 12, depth: 10, height: 6, outline: L_OUTLINE } };

describe('wallCorners', () => {
  it('gives a box room its four corners, clockwise from upstage stage right, as the plan draws them', () => {
    expect(wallCorners(BOX)).toEqual({
      corners: [{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 5 }, { x: -6, z: 5 }],
      box: true,
    });
  });

  it('gives an outlined room its own corners in the order stored', () => {
    expect(wallCorners(L_SHAPED)).toEqual({ corners: L_OUTLINE, box: false });
  });

  it('has none for no room, a room that is not from a scan, and a room with no size', () => {
    expect(wallCorners(null)).toBeNull();
    expect(wallCorners(undefined)).toBeNull();
    expect(wallCorners({ room: { width: 12, depth: 10, height: 6 } })).toBeNull();
    expect(wallCorners({ source: 'scan' })).toBeNull();
    expect(wallCorners({ source: 'scan', room: { width: 0, depth: 10, height: 6 } })).toBeNull();
  });

  it('takes an outline with a number missing for the box round it', () => {
    const broken = { source: 'scan', room: { width: 12, depth: 10, height: 6, outline: [{ x: 0, z: 0 }, { x: 1 }, { x: 1, z: 1 }] } };
    expect(wallCorners(broken as unknown as RoomShell)?.box).toBe(true);
  });
});

describe('the words for the walls', () => {
  it('says how many corners and how far wall to wall', () => {
    expect(wallsSizeText(wallCorners(BOX)!.corners, true))
      .toBe('4 corners, 12 m across and 10 m from upstage to downstage (a box)');
    expect(wallsSizeText(L_OUTLINE, false)).toBe('6 corners, 12 m across and 10 m from upstage to downstage');
  });

  it('measures walls that are not centred from the corners, not from the stored box', () => {
    const corners = [{ x: -4, z: -5 }, { x: 10, z: -5 }, { x: 10, z: 5 }, { x: -4, z: 5 }];
    expect(wallsSizeText(corners, false)).toBe('4 corners, 14 m across and 10 m from upstage to downstage');
  });

  it('reads the height of the room', () => {
    expect(roomHeight(BOX)).toBe(6);
    expect(roomHeight(null)).toBeNull();
    expect(roomHeight({ source: 'scan' })).toBeNull();
  });
});

describe('readCorner', () => {
  const corner = { x: 6, z: -5 };

  it('changes nothing for a row as it is stored', () => {
    expect(cornerDraftOf(corner)).toEqual({ x: '6', z: '-5' });
    expect(readCorner(corner, cornerDraftOf(corner))).toEqual({ changes: null, problem: null });
  });

  it('sends only the one of Across and Depth that differs', () => {
    expect(readCorner(corner, { x: '7.5', z: '-5' })).toEqual({ changes: { x: 7.5 }, problem: null });
    expect(readCorner(corner, { x: '6', z: ' -4,25 ' })).toEqual({ changes: { z: -4.25 }, problem: null });
    expect(readCorner(corner, { x: '8', z: '-6' })).toEqual({ changes: { x: 8, z: -6 }, problem: null });
  });

  it('takes a number that reads the same to the millimetre for no change', () => {
    expect(readCorner(corner, { x: '6.0', z: '-5.0004' })).toEqual({ changes: null, problem: null });
  });

  it('names the field that cannot be sent', () => {
    expect(readCorner(corner, { x: 'left', z: '-5' }).problem).toBe('Across must be a number of metres, such as -1.5.');
    expect(readCorner(corner, { x: '6', z: '' }).problem).toBe('Depth must be a number of metres, such as -1.5.');
    expect(readCorner(corner, { x: '250', z: '-5' }).problem)
      .toBe('Across can be at most 100 m from the middle of the floor.');
  });
});

describe('readRoomHeight', () => {
  it('sends a height that differs, and nothing for the one stored', () => {
    expect(readRoomHeight(6, '6')).toEqual({ height: null, problem: null });
    expect(readRoomHeight(6, '6.0')).toEqual({ height: null, problem: null });
    expect(readRoomHeight(6, '5,5')).toEqual({ height: 5.5, problem: null });
    expect(readRoomHeight(null, '4')).toEqual({ height: 4, problem: null });
  });

  it('says what a height must be', () => {
    expect(readRoomHeight(6, 'tall').problem).toBe("The room's height must be a number of metres, from 1.5 to 30.");
    expect(readRoomHeight(6, '1').problem).toBe("The room's height must be between 1.5 m and 30 m.");
    expect(readRoomHeight(6, '31').problem).toBe("The room's height must be between 1.5 m and 30 m.");
  });
});

describe('what the walls leave outside', () => {
  const report = {
    items: [
      { kind: 'truss_rings' as const, index: 0, name: 'Ring 1', reason: 'outside the walls', already_outside: false },
      { kind: 'risers' as const, index: 1, name: 'Riser', reason: 'partly outside the walls', already_outside: true },
    ],
    fixtures: [{ rig_fixture_id: 4, name: 'Spot 4', reason: 'outside the walls and above the ceiling' }],
    count: 3,
  };

  it('lists the room\'s own items first, then fixtures, and marks what was outside before', () => {
    expect(outsideLines(report)).toEqual([
      'Ring 1 (overhead ring) is outside the walls.',
      'Riser (raised area) is partly outside the walls (it was before this change).',
      'Spot 4 (fixture) is outside the walls and above the ceiling.',
    ]);
    expect(outsideHeading(report)).toBe('3 things are outside the walls or above the ceiling. None was moved:');
    expect(outsideHeading({ items: [], fixtures: report.fixtures }))
      .toBe('1 thing is outside the walls or above the ceiling. It was not moved:');
  });

  it('reads no report, and one with a list missing, as nothing outside', () => {
    expect(outsideOf(null)).toEqual({ items: [], fixtures: [], count: 0 });
    expect(outsideOf({ fixtures: report.fixtures })).toEqual({ items: [], fixtures: report.fixtures, count: 1 });
    expect(outsideLines(undefined)).toEqual([]);
  });
});

describe('the paths of the walls', () => {
  it('are under the room shell, and are not a list of it', () => {
    expect(roomOutlinePath(7)).toBe('/rigs/7/room-shell/outline');
    expect(roomOutlineCornersPath(7)).toBe('/rigs/7/room-shell/outline/corners');
    expect(roomOutlineCornerPath(7, 2)).toBe('/rigs/7/room-shell/outline/corners/2');
  });
});
