// The 2D layout view, correcting a suggested layout quickly: a snap onto
// scanned truss takes the truss's height and says so, a palette drop snaps
// the same way, and several selected fixtures are carried as one row, held to
// the room. With no scanned room and one fixture nothing is different.
// docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, createEvent, fireEvent, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { PlanMove } from '../components/rig/rowMove2d';
import { FIXTURE_DRAG_MIME } from '../stores/rigEditorStore';
import type { RigFixture, RoomShell } from '../types';

const spot = (id: number, x: number, z: number, y = 4) => ({
  id,
  name: `Spot ${id}`,
  dmx_address: id,
  position_x: x,
  position_y: y,
  position_z: z,
  rotation_y: 0,
}) as unknown as RigFixture;

// 20 m by 16 m round a 10 m by 8 m stage. Truss 1 straight across at z = -3
// from x = -4 to 4, Truss 2 from (-6, 0) to (-2, 4), Ring 1 of radius 2
// round (5, -2).
const SCANNED: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 20, depth: 16, height: 6 },
  truss_lines: [
    { name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 },
    { name: 'Truss 2', x1: -6, z1: 0, x2: -2, z2: 4, height: 5, across: 0.3, heading_deg: 45 },
  ],
  truss_rings: [{ name: 'Ring 1', center_x: 5, center_z: -2, radius: 2, height: 4.8, across: 0.3 }],
};

// The same room as an L: x > 4 with z > 2 is walled off.
const OUTLINE = [
  { x: -10, z: -8 }, { x: 10, z: -8 }, { x: 10, z: 2 }, { x: 4, z: 2 }, { x: 4, z: 8 }, { x: -10, z: 8 },
];
const L_SHAPED: RoomShell = { ...SCANNED, room: { width: 20, depth: 16, height: 6, outline: OUTLINE } };

type Props = Parameters<typeof StageView2D>[0];

/** The plan drawn at 10 pixels to the metre, so a pointer position is easy to read. */
function plan(roomShell: RoomShell | null | undefined, extra: Partial<Props> = {}) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [spot(1, 0, 0)], selectedIds: new Set<number>(), ...extra };
  const { container } = roomShell === undefined
    ? render(<StageView2D {...props} />)
    : render(<StageView2D {...props} roomShell={roomShell} />);
  const svg = container.querySelector('svg')!;
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: w * 10, bottom: h * 10, width: w * 10, height: h * 10, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

// With the scanned room the view is 22 m by 18 m from (-5, -4).
const inRoom = (x: number, z: number) => ({ clientX: (x + 11) * 10, clientY: (z + 9) * 10 });
// With no room it is 12 m by 10 m from the origin.
const onDeck = (x: number, z: number) => ({ clientX: (x + 6) * 10, clientY: (z + 5) * 10 });

const grab = (name: string) => screen.getByText(name).parentElement!;

/** A palette drag or drop over the plan, with the pointer position set on the event itself. */
function paletteEvent(
  kind: 'drop' | 'dragOver', svg: SVGSVGElement, where: { clientX: number; clientY: number }, altKey = false,
) {
  const event = createEvent[kind](svg, {
    dataTransfer: { types: [FIXTURE_DRAG_MIME], getData: () => '7' },
  });
  Object.defineProperty(event, 'clientX', { value: where.clientX });
  Object.defineProperty(event, 'clientY', { value: where.clientY });
  Object.defineProperty(event, 'altKey', { value: altKey });
  fireEvent(svg, event);
}

const readout = () => screen.queryByTestId('snap-readout');

// ---------------------------------------------------------------------------
// A snap onto scanned truss takes its height, and says what it is on
// ---------------------------------------------------------------------------

describe('StageView2D: a drag that snaps to scanned truss', () => {
  afterEach(cleanup);

  it('takes the hang height of the truss line it snaps onto', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(SCANNED, { onFixtureDrag });
    fireEvent.mouseDown(grab('Spot 1'), inRoom(0, 0));
    // 0.3 m downstage of Truss 1, which hangs at 4.2 m. The fixture is at 4 m.
    fireEvent.mouseMove(svg, inRoom(1.2, -2.7));
    const call = onFixtureDrag.mock.calls[0];
    expect(call).toHaveLength(4);
    expect(call[0]).toBe(1);
    expect(call[1]).toBeCloseTo(1.2);
    expect(call[2]).toBeCloseTo(-3);
    expect(call[3]).toBe(4.2);
  });

  it('takes the hang height of a ring', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(SCANNED, { onFixtureDrag });
    fireEvent.mouseDown(grab('Spot 1'), inRoom(0, 0));
    // 0.3 m outside Ring 1's downstage side at (5, 0).
    fireEvent.mouseMove(svg, inRoom(5, 0.3));
    const call = onFixtureDrag.mock.calls[0];
    expect(call[1]).toBeCloseTo(5);
    expect(call[2]).toBeCloseTo(0);
    expect(call[3]).toBe(4.8);
  });

  it('reports no height beyond a truss\'s reach, with Alt held, or with snapping off', () => {
    const tries: Array<[Partial<Props>, { clientX: number; clientY: number }, boolean]> = [
      [{}, inRoom(1.2, -2.4), false],
      [{}, inRoom(1.2, -2.7), true],
      [{ snapMode: 'none' }, inRoom(1.2, -2.7), false],
    ];
    for (const [extra, to, altKey] of tries) {
      const onFixtureDrag = vi.fn();
      const svg = plan(SCANNED, { ...extra, onFixtureDrag });
      fireEvent.mouseDown(grab('Spot 1'), inRoom(0, 0));
      fireEvent.mouseMove(svg, { ...to, altKey });
      expect(onFixtureDrag.mock.calls[0]).toHaveLength(3);
      expect(readout()).toBeNull();
      cleanup();
    }
  });

  it('gives the fixture back the height it was picked up at when it leaves the truss', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(SCANNED, { onFixtureDrag });
    fireEvent.mouseDown(grab('Spot 1'), inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(1.2, -2.7));
    expect(onFixtureDrag.mock.calls[0][3]).toBe(4.2);
    // Two metres off Truss 1: on the grid again.
    fireEvent.mouseMove(svg, inRoom(1.2, -1));
    const call = onFixtureDrag.mock.calls[1];
    expect(call[1]).toBeCloseTo(1);
    expect(call[2]).toBeCloseTo(-1);
    expect(call[3]).toBe(4);
  });

  it('says what it snapped to and the height, by the fixture, and stops saying it', () => {
    const svg = plan(SCANNED, { onFixtureDrag: vi.fn() });
    expect(readout()).toBeNull();
    fireEvent.mouseDown(grab('Spot 1'), inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(1.2, -2.7));
    expect(readout()!.textContent).toBe('On Truss 1 · hangs at 4.20 m');
    // Over the snapped position (1.2, -3): 7.2 across and 2 down the view, less 0.55.
    expect(Number(readout()!.getAttribute('x'))).toBeCloseTo(7.2);
    expect(Number(readout()!.getAttribute('y'))).toBeCloseTo(1.45);
    fireEvent.mouseMove(svg, inRoom(5, 0.3));
    expect(readout()!.textContent).toBe('On Ring 1 · hangs at 4.80 m');
    fireEvent.mouseMove(svg, inRoom(1.2, -1));
    expect(readout()).toBeNull();
    fireEvent.mouseMove(svg, inRoom(1.2, -2.7));
    expect(readout()).not.toBeNull();
    fireEvent.mouseUp(svg);
    expect(readout()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// A palette drop snaps the same way
// ---------------------------------------------------------------------------

describe('StageView2D: a palette drop near scanned truss', () => {
  afterEach(cleanup);

  it('lands on the truss, at the height it hangs at', () => {
    const onDropFromPalette = vi.fn();
    const svg = plan(SCANNED, { onDropFromPalette });
    paletteEvent('drop', svg, inRoom(1.2, -2.7));
    const call = onDropFromPalette.mock.calls[0];
    expect(call).toHaveLength(4);
    expect(call[0]).toBe(7);
    expect(call[1]).toBeCloseTo(1.2);
    expect(call[2]).toBeCloseTo(-3);
    expect(call[3]).toBe(4.2);
  });

  it('lands on a ring, at the height it hangs at', () => {
    const onDropFromPalette = vi.fn();
    const svg = plan(SCANNED, { onDropFromPalette });
    paletteEvent('drop', svg, inRoom(5, 0.3));
    const call = onDropFromPalette.mock.calls[0];
    expect(call[1]).toBeCloseTo(5);
    expect(call[2]).toBeCloseTo(0);
    expect(call[3]).toBe(4.8);
  });

  it('lands on the grid with no height beyond the truss\'s reach, with Alt held, or with snapping off', () => {
    const tries: Array<[Partial<Props>, number, number, boolean, number, number]> = [
      // 0.6 m from Truss 1.
      [{}, 1.2, -2.4, false, 1, -2.5],
      [{}, 1.2, -2.7, true, 1, -2.5],
      [{ snapMode: 'none' }, 1.2, -2.7, false, 1.2, -2.7],
    ];
    for (const [extra, x, z, altKey, wantX, wantZ] of tries) {
      const onDropFromPalette = vi.fn();
      const svg = plan(SCANNED, { ...extra, onDropFromPalette });
      paletteEvent('drop', svg, inRoom(x, z), altKey);
      const call = onDropFromPalette.mock.calls[0];
      expect(call).toHaveLength(3);
      expect(call[1]).toBeCloseTo(wantX);
      expect(call[2]).toBeCloseTo(wantZ);
      cleanup();
    }
  });

  it('says what it would land on while the fixture is held over the truss', () => {
    const svg = plan(SCANNED, { onDropFromPalette: vi.fn() });
    paletteEvent('dragOver', svg, inRoom(1.2, -2.7));
    expect(screen.getByText('1.2, -3.0')).toBeTruthy();
    expect(readout()!.textContent).toBe('On Truss 1 · hangs at 4.20 m');
    // Away from it there is only the landing spot.
    paletteEvent('dragOver', svg, inRoom(1.2, -1));
    expect(readout()).toBeNull();
  });

  it('is held to the deck, with no height, where there is no scanned room', () => {
    const onDropFromPalette = vi.fn();
    const svg = plan(undefined, { onDropFromPalette });
    paletteEvent('drop', svg, onDeck(1.2, -2.7));
    expect(onDropFromPalette.mock.calls[0]).toEqual([7, 1, -2.5]);
  });
});

// ---------------------------------------------------------------------------
// Building a selection
// ---------------------------------------------------------------------------

const ROW = [spot(1, -1, 0), spot(2, 0, 0), spot(3, 1, 0)];

describe('StageView2D: selecting more than one fixture', () => {
  afterEach(cleanup);

  it('adds to the selection with Shift, Ctrl or Cmd, and selects one alone without', () => {
    const onFixtureClick = vi.fn();
    plan(undefined, { fixtures: ROW, onFixtureClick, onFixturesDrag: vi.fn() });
    fireEvent.mouseDown(grab('Spot 1'), { ...onDeck(-1, 0), shiftKey: true });
    fireEvent.mouseDown(grab('Spot 2'), { ...onDeck(0, 0), ctrlKey: true });
    fireEvent.mouseDown(grab('Spot 3'), { ...onDeck(1, 0), metaKey: true });
    fireEvent.mouseDown(grab('Spot 2'), onDeck(0, 0));
    expect(onFixtureClick.mock.calls).toEqual([[1, true], [2, true], [3, true], [2, false]]);
  });

  it('keeps the selection on a press on one of several selected, and selects it alone if let go unmoved', () => {
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixtureClick, onFixturesDrag: vi.fn(),
    });
    fireEvent.mouseDown(grab('Spot 2'), onDeck(0, 0));
    expect(onFixtureClick).not.toHaveBeenCalled();
    fireEvent.mouseUp(svg);
    expect(onFixtureClick.mock.calls).toEqual([[2, false]]);
  });

  it('takes a fixture out of the selection with a modifier, and then carries nothing', () => {
    const onFixtureClick = vi.fn();
    const onFixtureDrag = vi.fn();
    const onFixturesDrag = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', onFixtureClick, onFixtureDrag, onFixturesDrag,
    });
    fireEvent.mouseDown(grab('Spot 2'), { ...onDeck(0, 0), shiftKey: true });
    expect(onFixtureClick.mock.calls).toEqual([[2, true]]);
    fireEvent.mouseMove(svg, onDeck(1, 1));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixturesDrag).not.toHaveBeenCalled();
  });

  it('carries a fixture just added to the selection along with the rest', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1]), snapMode: 'none', onFixturesDrag,
    });
    fireEvent.mouseDown(grab('Spot 2'), { ...onDeck(0, 0), shiftKey: true });
    fireEvent.mouseMove(svg, onDeck(0, 1));
    const moves = onFixturesDrag.mock.calls[0][0] as PlanMove[];
    expect(moves.map((move) => move.id)).toEqual([1, 2]);
  });

  it('asks for the whole row on a double-click', () => {
    const onFixtureSelectRow = vi.fn();
    plan(undefined, { fixtures: ROW, onFixtureSelectRow });
    fireEvent.doubleClick(grab('Spot 2'));
    expect(onFixtureSelectRow.mock.calls).toEqual([[2]]);
  });
});

// ---------------------------------------------------------------------------
// Carrying a row
// ---------------------------------------------------------------------------

/** What the last row move reported, by fixture id. */
function lastMoves(onFixturesDrag: ReturnType<typeof vi.fn>) {
  const calls = onFixturesDrag.mock.calls;
  const moves = calls[calls.length - 1][0] as PlanMove[];
  return new Map(moves.map((move) => [move.id, move]));
}

describe('StageView2D: dragging a selected row', () => {
  afterEach(cleanup);

  it('moves every selected fixture by the same shift, and no other', () => {
    const onFixtureDrag = vi.fn();
    const onFixturesDrag = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(SCANNED, {
      fixtures: [...ROW, spot(4, 3, 3)],
      selectedIds: new Set([1, 2, 3]),
      snapMode: 'none',
      onFixtureDrag, onFixturesDrag, onFixtureClick,
    });
    fireEvent.mouseDown(grab('Spot 2'), inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(2.5, 1.5));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
    const moves = lastMoves(onFixturesDrag);
    expect([...moves.keys()]).toEqual([1, 2, 3]);
    // A metre apart before, and a metre apart after.
    expect(moves.get(1)!.x).toBeCloseTo(1.5);
    expect(moves.get(2)!.x).toBeCloseTo(2.5);
    expect(moves.get(3)!.x).toBeCloseTo(3.5);
    for (const move of moves.values()) {
      expect(move.z).toBeCloseTo(1.5);
      // No truss was met, so no height is reported.
      expect('y' in move).toBe(false);
    }
    expect(readout()).toBeNull();
  });

  it('snaps the row onto a truss line with the fixture under the pointer, each taking its height', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(SCANNED, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixturesDrag });
    fireEvent.mouseDown(grab('Spot 2'), inRoom(0, 0));
    // 0.2 m downstage of Truss 1 at z = -3.
    fireEvent.mouseMove(svg, inRoom(0.2, -2.8));
    const moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(-0.8);
    expect(moves.get(2)!.x).toBeCloseTo(0.2);
    expect(moves.get(3)!.x).toBeCloseTo(1.2);
    for (const move of moves.values()) {
      expect(move.z).toBeCloseTo(-3);
      expect(move.y).toBe(4.2);
    }
    expect(readout()!.textContent).toBe('Row of 3 on Truss 1 · hangs at 4.20 m');
  });

  it('gives the truss\'s height only to the fixtures that are on it', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(SCANNED, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixturesDrag });
    fireEvent.mouseDown(grab('Spot 2'), inRoom(0, 0));
    // Truss 1 ends at x = 4: Spot 3 comes to 4.5, half a metre past its end.
    fireEvent.mouseMove(svg, inRoom(3.5, -2.9));
    const moves = lastMoves(onFixturesDrag);
    expect(moves.get(3)!.x).toBeCloseTo(4.5);
    expect(moves.get(1)!.y).toBe(4.2);
    expect(moves.get(2)!.y).toBe(4.2);
    expect(moves.get(3)!.y).toBe(4);
    expect(readout()!.textContent).toBe('2 of 3 on Truss 1 · hangs at 4.20 m');
  });

  it('holds the whole row at the wall of an L\'s notch, keeping its spacing', () => {
    const onFixturesDrag = vi.fn();
    const row = [spot(1, 1, 5), spot(2, 2, 5), spot(3, 3, 5)];
    const svg = plan(L_SHAPED, { fixtures: row, selectedIds: new Set([1, 2, 3]), snapMode: 'none', onFixturesDrag });
    fireEvent.mouseDown(grab('Spot 1'), inRoom(1, 5));
    // Three metres stage left would put Spot 2 and Spot 3 in the notch, past its wall at x = 4.
    fireEvent.mouseMove(svg, inRoom(4, 5));
    let moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(2);
    expect(moves.get(2)!.x).toBeCloseTo(3);
    expect(moves.get(3)!.x).toBeCloseTo(4);
    for (const move of moves.values()) expect(move.z).toBeCloseTo(5);
    // Into the other arm of the L the row follows the pointer.
    fireEvent.mouseMove(svg, inRoom(7, -1));
    moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(7);
    expect(moves.get(2)!.x).toBeCloseTo(8);
    expect(moves.get(3)!.x).toBeCloseTo(9);
    for (const move of moves.values()) expect(move.z).toBeCloseTo(-1);
  });

  it('holds the whole row at the wall of a box room', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(SCANNED, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', onFixturesDrag });
    fireEvent.mouseDown(grab('Spot 2'), inRoom(0, 0));
    // Past the wall at x = 10 and the one at z = 8.
    fireEvent.mouseMove(svg, inRoom(10.5, 8.6));
    const moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(8);
    expect(moves.get(2)!.x).toBeCloseTo(9);
    expect(moves.get(3)!.x).toBeCloseTo(10);
    for (const move of moves.values()) expect(move.z).toBeCloseTo(8);
  });

  it('holds a row to the deck, on its grid, where there is no scanned room', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixturesDrag });
    fireEvent.mouseDown(grab('Spot 2'), onDeck(0, 0));
    // Past the deck's edge at x = 5.
    fireEvent.mouseMove(svg, onDeck(5.9, 0.2));
    const moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(3);
    expect(moves.get(2)!.x).toBeCloseTo(4);
    expect(moves.get(3)!.x).toBeCloseTo(5);
    for (const move of moves.values()) {
      expect(move.z).toBeCloseTo(0);
      expect('y' in move).toBe(false);
    }
    expect(readout()).toBeNull();
  });

  it('does not snap a row to its own depth in the Truss snap mode', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(undefined, {
      fixtures: [...ROW, spot(4, -2, -2), spot(5, 2, -2)],
      selectedIds: new Set([1, 2, 3]),
      snapMode: 'truss',
      onFixturesDrag,
    });
    fireEvent.mouseDown(grab('Spot 2'), onDeck(0, 0));
    // Nearer the row's own depth than the other two fixtures' truss at z = -2.
    fireEvent.mouseMove(svg, onDeck(0.3, -0.6));
    const moves = lastMoves(onFixturesDrag);
    expect(moves.get(1)!.x).toBeCloseTo(-0.7);
    expect(moves.get(2)!.x).toBeCloseTo(0.3);
    expect(moves.get(3)!.x).toBeCloseTo(1.3);
    for (const move of moves.values()) expect(move.z).toBeCloseTo(-2);
  });

  it('leaves the row selected when it is let go over the background', () => {
    const onFixtureClick = vi.fn();
    const svg = plan(SCANNED, {
      fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', onFixtureClick, onFixturesDrag: vi.fn(),
    });
    fireEvent.mouseDown(grab('Spot 2'), inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(2, 2));
    fireEvent.mouseUp(svg);
    fireEvent.click(svg);
    expect(onFixtureClick).not.toHaveBeenCalled();
    // The next click on the background deselects, as it always did.
    fireEvent.click(svg);
    expect(onFixtureClick.mock.calls).toEqual([[-1, false]]);
  });
});

// ---------------------------------------------------------------------------
// With no scanned room and no multi-selection, nothing is different
// ---------------------------------------------------------------------------

describe('StageView2D: one fixture and no scanned room', () => {
  afterEach(cleanup);

  it('reports a drag as it always did, whether or not a row could be carried', () => {
    for (const selectedIds of [new Set<number>(), new Set([1])]) {
      const onFixtureDrag = vi.fn();
      const onFixturesDrag = vi.fn();
      const onFixtureClick = vi.fn();
      const svg = plan(undefined, { selectedIds, onFixtureDrag, onFixturesDrag, onFixtureClick });
      fireEvent.mouseDown(grab('Spot 1'), onDeck(0, 0));
      expect(onFixtureClick.mock.calls).toEqual([[1, false]]);
      // Into the margin beyond the deck's edges at x = 5 and z = 4.
      fireEvent.mouseMove(svg, onDeck(5.9, 4.9));
      expect(onFixtureDrag.mock.calls[0]).toEqual([1, 5, 4]);
      expect(onFixturesDrag).not.toHaveBeenCalled();
      expect(readout()).toBeNull();
      fireEvent.mouseUp(svg);
      // Letting go selects nothing more and deselects nothing.
      expect(onFixtureClick.mock.calls).toEqual([[1, false]]);
      cleanup();
    }
  });

  it('drags one of several selected fixtures alone where no row can be carried', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixtureDrag, onFixtureClick });
    fireEvent.mouseDown(grab('Spot 2'), onDeck(0, 0));
    expect(onFixtureClick.mock.calls).toEqual([[2, false]]);
    fireEvent.mouseMove(svg, onDeck(2, 1));
    expect(onFixtureDrag.mock.calls[0]).toEqual([2, 2, 1]);
  });

  it('still drags a fixture with Shift held, as it did, where no row can be carried', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), onFixtureDrag, onFixtureClick });
    fireEvent.mouseDown(grab('Spot 2'), { ...onDeck(0, 0), shiftKey: true });
    expect(onFixtureClick.mock.calls).toEqual([[2, true]]);
    fireEvent.mouseMove(svg, onDeck(2, 1));
    expect(onFixtureDrag.mock.calls[0]).toEqual([2, 2, 1]);
  });
});
