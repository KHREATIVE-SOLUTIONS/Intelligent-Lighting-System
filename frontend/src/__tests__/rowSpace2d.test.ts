// Fixing a row's spacing and symmetry on the 2D plan: the spacing a row is
// laid along scanned truss at, a selection mirrored left to right, and a
// selection spaced evenly between its two ends. Numbers and words only.
// docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import { planTrussTargets, roomPlan } from '../components/rig/roomPlan2d';
import type { PlanWalls } from '../components/rig/roomPlan2d';
import { layRowOnTruss, withMoves } from '../components/rig/rowMove2d';
import {
  DEFAULT_LAY_CHOICE, LAY_MODES, LAY_MODE_LABELS, centredSpotsOn, evenMoves, evenNoticeText, layRowSpaced,
  mirrorAxis, mirrorMoves, mirrorNoticeText, parseSpacing, rowSpacing, spacedLayNoticeText,
} from '../components/rig/rowSpace2d';
import type { RoomShell } from '../types';

// 12 m by 10 m. Truss 1 straight across at z = -2, 8 m long; a truss at 45
// degrees from (-5, 1) to (-1, 5); and a ring of radius 1.5 round (3, 2).
const TRUSS_1 = { name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, across: 0.3 };
const SHELL: RoomShell = {
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  truss_lines: [
    TRUSS_1,
    { name: 'Angled', x1: -5, z1: 1, x2: -1, z2: 5, height: 5, across: 0.3, heading_deg: 45 },
  ],
  truss_rings: [{ name: 'Overhead A', center_x: 3, center_z: 2, radius: 1.5, height: 4.8, across: 0.3 }],
};
const [TRUSS, ANGLED, RING] = planTrussTargets(SHELL);
const WALLS = roomPlan(SHELL)!.walls!;

// 12 m by 10 m with x > 2, z > 1 walled off: the notch.
const L_WALLS = roomPlan({
  source: 'scan',
  room: {
    width: 12, depth: 10, height: 5,
    outline: [{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 }],
  },
})!.walls!;

const at = (x: number, z: number) => ({ x, z });
const addressed = (id: number, address: number, x: number, y: number, z: number) => ({
  id, universe: 0, dmx_address: address, position_x: x, position_y: y, position_z: z,
});

// ---------------------------------------------------------------------------
// The spacing a row is laid at
// ---------------------------------------------------------------------------

describe('the Lay on truss choice', () => {
  it('fills the truss unless something else is chosen', () => {
    expect(DEFAULT_LAY_CHOICE.mode).toBe('fill');
    expect(LAY_MODES).toEqual(['fill', 'keep', 'set']);
    expect(LAY_MODES.map((mode) => LAY_MODE_LABELS[mode])).toEqual(['Fill truss', 'Keep spacing', 'Set spacing']);
  });
});

describe('parseSpacing', () => {
  it('reads metres as they are typed', () => {
    expect(parseSpacing('1.2')).toBe(1.2);
    expect(parseSpacing(' 0.75 ')).toBe(0.75);
    expect(parseSpacing('2')).toBe(2);
    expect(parseSpacing('.5')).toBe(0.5);
    // A comma for the decimal point, and the unit written out.
    expect(parseSpacing('1,2')).toBe(1.2);
    expect(parseSpacing('1.2 m')).toBe(1.2);
    expect(parseSpacing('1.2m')).toBe(1.2);
  });

  it('is null for anything that is not a number above zero', () => {
    for (const text of ['', '  ', 'abc', '0', '0.0', '-1', '1e3', '1.2.3', 'm', '1 2']) {
      expect(parseSpacing(text)).toBeNull();
    }
  });
});

describe('rowSpacing', () => {
  it('is the row\'s length shared between its gaps, whatever order it comes in', () => {
    expect(rowSpacing([at(-2, -1), at(0, -1), at(2, -1)])).toBe(2);
    expect(rowSpacing([at(2, -1), at(-2, -1), at(0, -1)])).toBe(2);
    // Uneven gaps: 4 m between three is still 2 m each.
    expect(rowSpacing([at(-2, -1), at(1.5, -1), at(2, -1)])).toBe(2);
    // On the slant: 5 m between two.
    expect(rowSpacing([at(0, 0), at(3, 4)])).toBe(5);
  });

  it('is nothing for one fixture, or for a row all in one place', () => {
    expect(rowSpacing([])).toBe(0);
    expect(rowSpacing([at(1, 1)])).toBe(0);
    expect(rowSpacing([at(1, 1), at(1, 1), at(1, 1)])).toBe(0);
  });
});

describe('centredSpotsOn', () => {
  const row = [at(-2, -1), at(0, -1), at(2, -1)];

  it('centres the row on the middle of the truss at the spacing given', () => {
    expect(centredSpotsOn(TRUSS, row, 1)).toEqual([at(-1, -2), at(0, -2), at(1, -2)]);
    expect(centredSpotsOn(TRUSS, row, 2.5)).toEqual([at(-2.5, -2), at(0, -2), at(2.5, -2)]);
    // An even count has no fixture on the middle.
    expect(centredSpotsOn(TRUSS, [at(-1, -1), at(1, -1)], 3)).toEqual([at(-1.5, -2), at(1.5, -2)]);
  });

  it('keeps which end the first of the row is at', () => {
    const reversed = [at(2, -1), at(0, -1), at(-2, -1)];
    expect(centredSpotsOn(TRUSS, reversed, 1)).toEqual([at(1, -2), at(0, -2), at(-1, -2)]);
  });

  it('lays a row that is exactly the truss\'s length, and none longer', () => {
    expect(centredSpotsOn(TRUSS, row, 4)).toEqual([at(-4, -2), at(0, -2), at(4, -2)]);
    expect(centredSpotsOn(TRUSS, row, 4.01)).toBeNull();
    expect(centredSpotsOn(TRUSS, row, 5)).toBeNull();
  });

  it('runs along a truss at an angle', () => {
    // The middle of the line is (-3, 3); 2.83 m apart along it is 2 m each way on the plan.
    const spots = centredSpotsOn(ANGLED, [at(-4, 3), at(-2, 5)], 2 * Math.SQRT2)!;
    expect(spots[0].x).toBeCloseTo(-4);
    expect(spots[0].z).toBeCloseTo(2);
    expect(spots[1].x).toBeCloseTo(-2);
    expect(spots[1].z).toBeCloseTo(4);
  });

  it('is not for a ring, one fixture or a spacing of nothing', () => {
    expect(centredSpotsOn(RING, row, 1)).toBeNull();
    expect(centredSpotsOn(TRUSS, [at(0, -1)], 1)).toBeNull();
    expect(centredSpotsOn(TRUSS, row, 0)).toBeNull();
    expect(centredSpotsOn(TRUSS, row, -1)).toBeNull();
    expect(centredSpotsOn(TRUSS, row, Number.NaN)).toBeNull();
  });
});

describe('layRowSpaced', () => {
  // Three a metre downstage of Truss 1 at 3 m, 2 m apart, their ids not in
  // address order (by address: 2, 3, 1), and one more that is not selected.
  const rig = [
    addressed(1, 20, 2, 3, -1), addressed(2, 1, -2, 3, -1), addressed(3, 10, 0, 3, -1), addressed(4, 30, 0, 0.5, 4),
  ];
  const lay = (choice?: Parameters<typeof layRowSpaced>[6], ids = [1, 2, 3], from = rig) => (
    layRowSpaced(from, ids, SHELL, WALLS, 6, 4, choice)
  );

  it('fills the truss exactly as Lay on truss always did, when nothing else is chosen', () => {
    const filled = layRowOnTruss(rig, [1, 2, 3], SHELL, WALLS, 6, 4);
    expect(lay()).toEqual(filled);
    expect(lay({ mode: 'fill', metres: 'not read' })).toEqual(filled);
    expect(spacedLayNoticeText(lay(), 3)).toBe('Laid 3 fixtures along Truss 1, 2.67 m apart, at 4.20 m.');
  });

  it('keeps the row\'s own spacing, centred on the truss, in address order, at its height', () => {
    const kept = lay({ mode: 'keep', metres: '' });
    if (!kept.ok) throw new Error('not laid');
    expect(kept.target.name).toBe('Truss 1');
    expect(kept.spacing).toBe(2);
    expect(kept.moves).toEqual([
      { id: 2, x: -2, z: -2, y: 4.2 }, { id: 3, x: 0, z: -2, y: 4.2 }, { id: 1, x: 2, z: -2, y: 4.2 },
    ]);
    expect(spacedLayNoticeText(kept, 3)).toBe('Laid 3 fixtures along Truss 1, 2.00 m apart, at 4.20 m.');
  });

  it('centres a row that stood off to one side', () => {
    // 1 m apart, all stage left of the middle of the truss.
    const aside = [addressed(1, 1, 1, 3, -1), addressed(2, 2, 2, 3, -1), addressed(3, 3, 3, 3, -1)];
    const kept = lay({ mode: 'keep', metres: '' }, [1, 2, 3], aside);
    if (!kept.ok) throw new Error('not laid');
    expect(kept.moves.map((move) => [move.id, move.x])).toEqual([[1, -1], [2, 0], [3, 1]]);
  });

  it('lays at a typed spacing, centred', () => {
    const set = lay({ mode: 'set', metres: '1.5' });
    if (!set.ok) throw new Error('not laid');
    expect(set.spacing).toBe(1.5);
    expect(set.moves).toEqual([
      { id: 2, x: -1.5, z: -2, y: 4.2 }, { id: 3, x: 0, z: -2, y: 4.2 }, { id: 1, x: 1.5, z: -2, y: 4.2 },
    ]);
    expect(spacedLayNoticeText(set, 3)).toBe('Laid 3 fixtures along Truss 1, 1.50 m apart, at 4.20 m.');
    // Under 0.3 m apart is worth a word, as for a filled row.
    const close = lay({ mode: 'set', metres: '0.2' });
    expect(spacedLayNoticeText(close, 3))
      .toBe('Laid 3 fixtures along Truss 1, 0.20 m apart, at 4.20 m. That is close: check they fit side by side.');
  });

  it('moves nothing the second time: a row laid at its own spacing is where it would be laid', () => {
    const first = lay({ mode: 'keep', metres: '' });
    if (!first.ok) throw new Error('not laid');
    const laid = withMoves(rig, first.moves);
    expect(laid.changed).toEqual([1, 2, 3]);
    const second = lay({ mode: 'keep', metres: '' }, [1, 2, 3], laid.fixtures);
    if (!second.ok) throw new Error('not laid');
    expect(withMoves(laid.fixtures, second.moves).changed).toEqual([]);
    expect(spacedLayNoticeText(second, 0)).toBe('The 3 fixtures are already laid along Truss 1, 2.00 m apart, at 4.20 m.');
  });

  it('moves nothing when the row would be longer than the truss, and says by how much', () => {
    const long = lay({ mode: 'set', metres: '5' });
    expect(long).toMatchObject({ ok: false, why: 'too-long', spacing: 5, needs: 10, length: 8 });
    expect(spacedLayNoticeText(long))
      .toBe('At 5.00 m apart the row is 10.00 m long, and Truss 1 is 8.00 m. Nothing was moved.');
    // A row 5 m apart keeps a spacing the truss cannot take either.
    const wide = [addressed(1, 1, -5, 3, -1), addressed(2, 2, 0, 3, -1), addressed(3, 3, 5, 3, -1)];
    expect(lay({ mode: 'keep', metres: '' }, [1, 2, 3], wide)).toMatchObject({ ok: false, why: 'too-long', needs: 10 });
    // Exactly the truss's length fits.
    expect(lay({ mode: 'set', metres: '4' }).ok).toBe(true);
  });

  it('moves nothing when a place on the truss is beyond the walls', () => {
    // The same truss in a room 6 m across: it runs a metre out through each side wall.
    const narrow: RoomShell = { source: 'scan', room: { width: 6, depth: 10, height: 6 }, truss_lines: [TRUSS_1] };
    const walls = roomPlan(narrow)!.walls!;
    const out = layRowSpaced(rig, [1, 2, 3], narrow, walls, 6, 4, { mode: 'set', metres: '3.5' });
    expect(out).toMatchObject({ ok: false, why: 'beyond-walls', beyond: 2 });
    expect(spacedLayNoticeText(out))
      .toBe('Truss 1 runs beyond the walls: 2 of the row\'s places on it are outside the room. Nothing was moved.');
    // Resting on the walls is inside them.
    const on = layRowSpaced(rig, [1, 2, 3], narrow, walls, 6, 4, { mode: 'set', metres: '3' });
    if (!on.ok) throw new Error('not laid');
    expect(on.moves.map((move) => move.x)).toEqual([-3, 0, 3]);
  });

  it('says so when the typed spacing is not a number above zero', () => {
    for (const metres of ['', 'abc', '0', '-2']) {
      const bad = lay({ mode: 'set', metres });
      expect(bad).toMatchObject({ ok: false, why: 'bad-spacing' });
      expect(spacedLayNoticeText(bad)).toBe('Type a spacing in metres above zero, such as 1.2. Nothing was moved.');
    }
  });

  it('has no spacing to keep for a row all in one place', () => {
    const heap = [addressed(1, 1, 0, 3, -1), addressed(2, 2, 0, 3, -1)];
    const none = lay({ mode: 'keep', metres: '' }, [1, 2], heap);
    expect(none).toMatchObject({ ok: false, why: 'no-spacing' });
    expect(spacedLayNoticeText(none)).toContain('no spacing to keep');
    // Filled, the same two are laid.
    expect(lay({ mode: 'fill', metres: '' }, [1, 2], heap).ok).toBe(true);
  });

  it('only ever fills a ring', () => {
    const round = [addressed(1, 1, 2, 3, 2), addressed(2, 2, 4, 3, 2)];
    const kept = lay({ mode: 'keep', metres: '' }, [1, 2], round);
    expect(kept).toMatchObject({ ok: false, why: 'ring' });
    expect(spacedLayNoticeText(kept))
      .toBe('Overhead A is a ring, which is only ever filled: choose Fill truss. Nothing was moved.');
    expect(lay({ mode: 'set', metres: '1' }, [1, 2], round)).toMatchObject({ ok: false, why: 'ring' });
    expect(lay({ mode: 'fill', metres: '' }, [1, 2], round).ok).toBe(true);
  });

  it('needs two fixtures and a scanned truss, as a filled row does', () => {
    const one = lay({ mode: 'keep', metres: '' }, [2]);
    expect(one).toEqual({ ok: false, why: 'too-few' });
    expect(spacedLayNoticeText(one)).toBe('Select two or more fixtures to lay along a truss.');
    const bare: RoomShell = { source: 'scan', room: { width: 12, depth: 10, height: 6 } };
    const none = layRowSpaced(rig, [1, 2, 3], bare, roomPlan(bare)!.walls!, 6, 4, { mode: 'set', metres: '1' });
    expect(none).toEqual({ ok: false, why: 'no-truss' });
    expect(spacedLayNoticeText(none)).toBe('This rig has no scanned truss to lay a row along.');
  });
});

// ---------------------------------------------------------------------------
// A selection mirrored left to right
// ---------------------------------------------------------------------------

const placed = (id: number, x: number, z: number, y = 4) => ({ id, position_x: x, position_y: y, position_z: z });

// A room that is not centred on the stage: 10 m across from x = -2 to x = 8.
const OFF_CENTRE: PlanWalls = {
  points: [{ x: -2, z: -5 }, { x: 8, z: -5 }, { x: 8, z: 5 }, { x: -2, z: 5 }],
  outlined: true,
  tooltip: '',
};

describe('mirrorAxis', () => {
  it('is the stage centre line with no scanned room', () => {
    expect(mirrorAxis(null)).toBe(0);
    expect(mirrorAxis(undefined)).toBe(0);
  });

  it('is the middle of the scanned room\'s walls', () => {
    expect(mirrorAxis(WALLS)).toBe(0);
    // An L: the middle of the box round it.
    expect(mirrorAxis(L_WALLS)).toBe(0);
    expect(mirrorAxis(OFF_CENTRE)).toBe(3);
  });
});

describe('mirrorMoves', () => {
  const rig = [placed(1, -3, 1), placed(2, 0, 1), placed(3, 2.5, -2), placed(4, 1, 1)];

  it('puts each selected fixture as far the other side of the centre line, at its own depth', () => {
    const mirrored = mirrorMoves(rig, [1, 2, 3], null, 10, 8);
    expect(mirrored).toEqual({
      axis: 0,
      // In the rig's order; the one on the line stays on it. No height is given.
      moves: [{ id: 1, x: 3, z: 1 }, { id: 2, x: 0, z: 1 }, { id: 3, x: -2.5, z: -2 }],
      held: 0,
    });
    for (const move of mirrored.moves) expect('y' in move).toBe(false);
    // Only what moved is a change: the one on the line is not.
    const next = withMoves(rig, mirrored.moves);
    expect(next.changed).toEqual([1, 3]);
    expect(next.fixtures.map((f) => f.position_y)).toEqual([4, 4, 4, 4]);
  });

  it('mirrors one fixture, and nothing for an empty selection', () => {
    expect(mirrorMoves(rig, [4], null, 10, 8).moves).toEqual([{ id: 4, x: -1, z: 1 }]);
    expect(mirrorMoves(rig, [], null, 10, 8).moves).toEqual([]);
    expect(mirrorMoves(rig, [99], null, 10, 8).moves).toEqual([]);
  });

  it('puts everything back when done twice', () => {
    const once = withMoves(rig, mirrorMoves(rig, [1, 2, 3, 4], null, 10, 8).moves);
    const twice = withMoves(once.fixtures, mirrorMoves(once.fixtures, [1, 2, 3, 4], null, 10, 8).moves);
    expect(twice.fixtures).toEqual(rig);
  });

  it('swaps the two sides of a symmetric row', () => {
    const row = [placed(1, -2, 0), placed(2, -1, 0), placed(3, 1, 0), placed(4, 2, 0)];
    expect(mirrorMoves(row, [1, 2, 3, 4], WALLS, 10, 8).moves.map((move) => move.x)).toEqual([2, 1, -1, -2]);
  });

  it('goes by the middle of a scanned room that is not centred on the stage', () => {
    const mirrored = mirrorMoves([placed(1, 1, 0), placed(2, 7, 2)], [1, 2], OFF_CENTRE, 10, 8);
    expect(mirrored.axis).toBe(3);
    expect(mirrored.moves).toEqual([{ id: 1, x: 5, z: 0 }, { id: 2, x: -1, z: 2 }]);
    expect(mirrored.held).toBe(0);
  });

  it('holds a mirrored place that would be in the notch of an L to its wall', () => {
    // (-3, 3) mirrors to (3, 3), a metre into the notch: back to the wall at x = 2.
    // (-4, -3) mirrors to (4, -3), in the other arm, where it may stand.
    const mirrored = mirrorMoves([placed(1, -3, 3), placed(2, -4, -3)], [1, 2], L_WALLS, 10, 8);
    expect(mirrored.moves).toEqual([{ id: 1, x: 2, z: 3 }, { id: 2, x: 4, z: -3 }]);
    expect(mirrored.held).toBe(1);
  });

  it('holds to the deck with no scanned room', () => {
    // Out past the deck's edge at x = -5: its mirror is brought to the edge at 5.
    const mirrored = mirrorMoves([placed(1, -7, 0)], [1], null, 10, 8);
    expect(mirrored.moves).toEqual([{ id: 1, x: 5, z: 0 }]);
    expect(mirrored.held).toBe(1);
  });

  it('keeps positions to the millimetre', () => {
    expect(mirrorMoves([placed(1, 1.2344, 0.5)], [1], null, 10, 8).moves).toEqual([{ id: 1, x: -1.234, z: 0.5 }]);
  });
});

describe('mirrorNoticeText', () => {
  const rig = [placed(1, -3, 1), placed(2, 0, 1), placed(3, 2.5, -2)];

  it('says how many were mirrored, and about which line', () => {
    expect(mirrorNoticeText(mirrorMoves(rig, [1, 2, 3], null, 10, 8), 2, false))
      .toBe('Mirrored 3 fixtures left to right about the stage centre line.');
    expect(mirrorNoticeText(mirrorMoves(rig, [1], null, 10, 8), 1, false))
      .toBe('Mirrored 1 fixture left to right about the stage centre line.');
    expect(mirrorNoticeText(mirrorMoves([placed(1, 1, 0), placed(2, 7, 2)], [1, 2], OFF_CENTRE, 10, 8), 2, true))
      .toBe('Mirrored 2 fixtures left to right about the room\'s centre line (x = 3.00 m).');
  });

  it('says when the walls held some', () => {
    const mirrored = mirrorMoves([placed(1, -3, 3), placed(2, -4, -3)], [1, 2], L_WALLS, 10, 8);
    expect(mirrorNoticeText(mirrored, 2, true))
      .toBe('Mirrored 2 fixtures left to right about the room\'s centre line (x = 0.00 m). 1 held at the wall.');
  });

  it('says when there was nothing to mirror', () => {
    expect(mirrorNoticeText(mirrorMoves(rig, [2], null, 10, 8), 0, false))
      .toBe('The fixture is on the stage centre line: there is nothing to mirror.');
    expect(mirrorNoticeText(mirrorMoves([placed(1, 0, 0), placed(2, 0, 1)], [1, 2], null, 10, 8), 0, false))
      .toBe('The 2 fixtures are on the stage centre line: there is nothing to mirror.');
    expect(mirrorNoticeText(mirrorMoves(rig, [], null, 10, 8), 0, false)).toBe('Select one or more fixtures to mirror.');
  });
});

// ---------------------------------------------------------------------------
// A selection spaced evenly
// ---------------------------------------------------------------------------

describe('evenMoves', () => {
  // A row of five that a suggestion left uneven and a little out of line.
  const rig = [
    addressed(1, 1, -2, 4, 0), addressed(2, 2, -1.7, 4, 0.2), addressed(3, 3, 0.4, 4, -0.1),
    addressed(4, 4, 1, 4, 0), addressed(5, 5, 4, 4, 0), addressed(6, 6, 0, 2, 3),
  ];

  it('keeps the two ends and spaces the rest evenly on the line between them', () => {
    const even = evenMoves(rig, [1, 2, 3, 4, 5], null, 10, 8);
    if (!even.ok) throw new Error('not spaced');
    // 6 m between five: 1.5 m apart. The ends are not listed: they do not move.
    expect(even.spacing).toBe(1.5);
    expect(even.count).toBe(5);
    expect(even.moves).toEqual([{ id: 2, x: -0.5, z: 0 }, { id: 3, x: 1, z: 0 }, { id: 4, x: 2.5, z: 0 }]);
    for (const move of even.moves) expect('y' in move).toBe(false);
    const next = withMoves(rig, even.moves);
    expect(next.changed).toEqual([2, 3, 4]);
    expect(next.fixtures.map((f) => f.position_x)).toEqual([-2, -0.5, 1, 2.5, 4, 0]);
    expect(evenNoticeText(even, 3)).toBe('Spaced 5 fixtures evenly, 1.50 m apart, between the first and the last by address.');
  });

  it('goes by DMX address for the ends and the order, not by where the fixtures stand', () => {
    // By address: id 1 at -3, id 2 at 4, id 3 at 1. The ends are ids 1 and 3,
    // though id 2 stands furthest stage left: it is brought between them.
    const row = [addressed(1, 1, -3, 4, 0), addressed(2, 2, 4, 4, 0), addressed(3, 3, 1, 4, 0)];
    const even = evenMoves(row, [1, 2, 3], null, 10, 8);
    if (!even.ok) throw new Error('not spaced');
    expect(even.moves).toEqual([{ id: 2, x: -1, z: 0 }]);
    // And by address whatever order the rig lists them in.
    const shuffled = [addressed(7, 30, 2, 4, 2), addressed(8, 10, -2, 4, -2), addressed(9, 20, 3, 4, 3)];
    const slant = evenMoves(shuffled, [7, 8, 9], null, 10, 8);
    if (!slant.ok) throw new Error('not spaced');
    // Ends: id 8 at (-2, -2) and id 7 at (2, 2). Id 9 goes half-way.
    expect(slant.moves).toEqual([{ id: 9, x: 0, z: 0 }]);
    expect(slant.spacing).toBeCloseTo(2 * Math.SQRT2);
  });

  it('moves nothing the second time', () => {
    const first = evenMoves(rig, [1, 2, 3, 4, 5], null, 10, 8);
    if (!first.ok) throw new Error('not spaced');
    const spaced = withMoves(rig, first.moves);
    const second = evenMoves(spaced.fixtures, [1, 2, 3, 4, 5], null, 10, 8);
    if (!second.ok) throw new Error('not spaced');
    expect(withMoves(spaced.fixtures, second.moves).changed).toEqual([]);
    expect(evenNoticeText(second, 0)).toBe('The 5 fixtures are already evenly spaced, 1.50 m apart.');
  });

  it('keeps positions to the millimetre', () => {
    const row = [addressed(1, 1, 0, 4, 0), addressed(2, 2, 0, 4, 0), addressed(3, 3, 0, 4, 0), addressed(4, 4, 1, 4, 0)];
    const even = evenMoves(row, [1, 2, 3, 4], null, 10, 8);
    if (!even.ok) throw new Error('not spaced');
    expect(even.moves).toEqual([{ id: 2, x: 0.333, z: 0 }, { id: 3, x: 0.667, z: 0 }]);
  });

  it('needs three fixtures', () => {
    const two = evenMoves(rig, [1, 2], null, 10, 8);
    expect(two).toEqual({ ok: false, why: 'too-few' });
    expect(evenNoticeText(two)).toBe('Select three or more fixtures to space evenly.');
    expect(evenMoves(rig, [], null, 10, 8)).toEqual({ ok: false, why: 'too-few' });
  });

  it('has nothing to go by when the two ends are in one place', () => {
    const row = [addressed(1, 1, 1, 4, 1), addressed(2, 2, 3, 4, 0), addressed(3, 3, 1, 4, 1)];
    const none = evenMoves(row, [1, 2, 3], null, 10, 8);
    expect(none).toEqual({ ok: false, why: 'no-span' });
    expect(evenNoticeText(none)).toContain('in the same place');
  });

  it('moves nothing when the line between the ends leaves the room', () => {
    // From (1, 4) to (5, 0) across the notch of the L: half-way is (3, 2), inside it.
    const row = [addressed(1, 1, 1, 4, 4), addressed(2, 2, 0, 4, 0), addressed(3, 3, 5, 4, 0)];
    const out = evenMoves(row, [1, 2, 3], L_WALLS, 10, 8);
    expect(out).toEqual({ ok: false, why: 'beyond-walls', beyond: 1 });
    expect(evenNoticeText(out)).toBe(
      'The straight line between the first and the last by address leaves the room: 1 of the places on it are outside. Nothing was moved.',
    );
    // The same three in a box room are spaced.
    expect(evenMoves(row, [1, 2, 3], WALLS, 10, 8)).toMatchObject({ ok: true, moves: [{ id: 2, x: 3, z: 2 }] });
  });
});
