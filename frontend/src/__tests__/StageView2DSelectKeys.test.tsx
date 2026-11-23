// The 2D layout view, correcting guessed fixtures quickly and safely: a press
// is a drag only from 5 screen pixels on, a drag over empty floor draws a
// selection box, and R, the arrow keys and Escape act on the selection.
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

// 20 m by 16 m round a 10 m by 8 m stage.
const SCANNED: RoomShell = { source: 'scan', suggested: true, room: { width: 20, depth: 16, height: 6 } };
// The same room as an L: x > 4 with z > 2 is walled off.
const L_SHAPED: RoomShell = {
  ...SCANNED,
  room: {
    width: 20, depth: 16, height: 6,
    outline: [
      { x: -10, z: -8 }, { x: 10, z: -8 }, { x: 10, z: 2 }, { x: 4, z: 2 }, { x: 4, z: 8 }, { x: -10, z: 8 },
    ],
  },
};

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

// With no room the view is 12 m by 10 m from the origin: stage (x, z) is at
// ((x + 6) * 10, (z + 5) * 10) on screen, so centre stage is at (60, 50).
const onDeck = (x: number, z: number) => ({ clientX: (x + 6) * 10, clientY: (z + 5) * 10 });
const px = (clientX: number, clientY: number) => ({ clientX, clientY });

const grab = (name: string) => screen.getByText(name).parentElement!;
const box = () => screen.queryByTestId('selection-box');

const ROW = [spot(1, -1, 0), spot(2, 0, 0), spot(3, 1, 0)];
const ROW_AND_ONE = [...ROW, spot(4, 3, 3)];

// ---------------------------------------------------------------------------
// A press is a drag only from 5 pixels on
// ---------------------------------------------------------------------------

describe('StageView2D: the drag threshold', () => {
  afterEach(cleanup);

  it('moves nothing on a click, or on a press that wobbles under 5 pixels', () => {
    const onFixtureDrag = vi.fn();
    const onFixturesDrag = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, { snapMode: 'none', onFixtureDrag, onFixturesDrag, onFixtureClick });
    // A plain click.
    fireEvent.mouseDown(grab('Spot 1'), px(60, 50));
    fireEvent.mouseUp(svg, px(60, 50));
    // 4 pixels across, then 3 across and 3 down (4.24 pixels), then back.
    fireEvent.mouseDown(grab('Spot 1'), px(60, 50));
    fireEvent.mouseMove(svg, px(64, 50));
    fireEvent.mouseMove(svg, px(63, 53));
    fireEvent.mouseMove(svg, px(60, 50));
    fireEvent.mouseUp(svg, px(60, 50));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixturesDrag).not.toHaveBeenCalled();
    // Each press still selected the fixture, as a click does.
    expect(onFixtureClick.mock.calls).toEqual([[1, false], [1, false]]);
  });

  it('is a drag from exactly 5 pixels, in any direction', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(undefined, { snapMode: 'none', onFixtureDrag });
    fireEvent.mouseDown(grab('Spot 1'), px(60, 50));
    // 3 across and 4 down is 5 pixels: 0.3 m and 0.4 m on the plan.
    fireEvent.mouseMove(svg, px(63, 54));
    expect(onFixtureDrag).toHaveBeenCalledTimes(1);
    const [id, x, z] = onFixtureDrag.mock.calls[0];
    expect(id).toBe(1);
    expect(x).toBeCloseTo(0.3);
    expect(z).toBeCloseTo(0.4);
    cleanup();

    const upstage = vi.fn();
    const again = plan(undefined, { snapMode: 'none', onFixtureDrag: upstage });
    fireEvent.mouseDown(grab('Spot 1'), px(60, 50));
    fireEvent.mouseMove(again, px(60, 45));
    expect(upstage).toHaveBeenCalledTimes(1);
    expect(upstage.mock.calls[0][2]).toBeCloseTo(-0.5);
  });

  it('follows the pointer everywhere once it is a drag, back near where it began too', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(undefined, { snapMode: 'none', onFixtureDrag });
    fireEvent.mouseDown(grab('Spot 1'), px(60, 50));
    fireEvent.mouseMove(svg, px(62, 50));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    fireEvent.mouseMove(svg, px(70, 50));
    // A pixel from where it was pressed: still the same drag.
    fireEvent.mouseMove(svg, px(61, 50));
    expect(onFixtureDrag).toHaveBeenCalledTimes(2);
    expect(onFixtureDrag.mock.calls[0][1]).toBeCloseTo(1);
    expect(onFixtureDrag.mock.calls[1][1]).toBeCloseTo(0.1);
  });

  it('does not put an off-grid guess on the grid when a double-click slips', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureSelectRow = vi.fn();
    // Grid snap, the default: any move at all would take it to the grid.
    const svg = plan(undefined, { fixtures: [spot(1, 0.2, 0.3)], onFixtureDrag, onFixtureSelectRow });
    fireEvent.mouseDown(grab('Spot 1'), px(62, 53));
    fireEvent.mouseMove(svg, px(64, 55));
    fireEvent.mouseUp(svg, px(64, 55));
    fireEvent.mouseDown(grab('Spot 1'), px(64, 55));
    fireEvent.mouseMove(svg, px(62, 54));
    fireEvent.mouseUp(svg, px(62, 54));
    fireEvent.doubleClick(grab('Spot 1'));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixtureSelectRow.mock.calls).toEqual([[1]]);
  });

  it('does not move a selected row on a press that wobbles, and selects the fixture alone as a click does', () => {
    const onFixturesDrag = vi.fn();
    const onFixtureDrag = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1, 2, 3]), onFixturesDrag, onFixtureDrag, onFixtureClick,
    });
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(63, 52));
    fireEvent.mouseUp(svg, px(63, 52));
    expect(onFixturesDrag).not.toHaveBeenCalled();
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixtureClick.mock.calls).toEqual([[2, false]]);
  });

  it('carries a selected row once the pointer is 5 pixels away', () => {
    const onFixturesDrag = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', onFixturesDrag,
    });
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(60, 54));
    expect(onFixturesDrag).not.toHaveBeenCalled();
    fireEvent.mouseMove(svg, px(60, 60));
    expect(onFixturesDrag).toHaveBeenCalledTimes(1);
    const moves = onFixturesDrag.mock.calls[0][0] as PlanMove[];
    expect(moves.map((move) => move.id)).toEqual([1, 2, 3]);
    for (const move of moves) expect(move.z).toBeCloseTo(1);
  });

  it('leaves a palette drop as it was: no press, no threshold', () => {
    const onDropFromPalette = vi.fn();
    const svg = plan(undefined, { onDropFromPalette });
    const where = onDeck(1.2, -2.7);
    const event = createEvent.drop(svg, { dataTransfer: { types: [FIXTURE_DRAG_MIME], getData: () => '7' } });
    Object.defineProperty(event, 'clientX', { value: where.clientX });
    Object.defineProperty(event, 'clientY', { value: where.clientY });
    fireEvent(svg, event);
    expect(onDropFromPalette.mock.calls[0]).toEqual([7, 1, -2.5]);
  });
});

// ---------------------------------------------------------------------------
// A selection box over empty floor
// ---------------------------------------------------------------------------

describe('StageView2D: box selection', () => {
  afterEach(cleanup);

  it('selects every fixture whose centre is inside the box, when it is let go', () => {
    const onSelectFixtures = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, onSelectFixtures, onFixtureClick });
    expect(box()).toBeNull();
    // From (-1.5, -1) to (0.5, 1): Spot 1 and Spot 2 are inside.
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    expect(onSelectFixtures).not.toHaveBeenCalled();
    // Drawn 2 m by 2 m from (-1.5, -1), which is (4.5, 4) in the view's units.
    const drawn = box()!;
    expect(Number(drawn.getAttribute('x'))).toBeCloseTo(4.5);
    expect(Number(drawn.getAttribute('y'))).toBeCloseTo(4);
    expect(Number(drawn.getAttribute('width'))).toBeCloseTo(2);
    expect(Number(drawn.getAttribute('height'))).toBeCloseTo(2);
    fireEvent.mouseUp(svg, onDeck(0.5, 1));
    expect(onSelectFixtures.mock.calls).toEqual([[[1, 2]]]);
    expect(box()).toBeNull();
    // The click that ends the drag does not clear what was just selected.
    fireEvent.click(svg);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('takes in the same fixtures whichever way the box is dragged', () => {
    const corners: Array<[[number, number], [number, number]]> = [
      [[-1.5, -1], [0.5, 1]],
      [[0.5, 1], [-1.5, -1]],
      [[-1.5, 1], [0.5, -1]],
      [[0.5, -1], [-1.5, 1]],
    ];
    for (const [from, to] of corners) {
      const onSelectFixtures = vi.fn();
      const svg = plan(undefined, { fixtures: ROW_AND_ONE, onSelectFixtures });
      fireEvent.mouseDown(svg, onDeck(from[0], from[1]));
      fireEvent.mouseMove(svg, onDeck(to[0], to[1]));
      const drawn = box()!;
      expect(Number(drawn.getAttribute('x'))).toBeCloseTo(4.5);
      expect(Number(drawn.getAttribute('y'))).toBeCloseTo(4);
      expect(Number(drawn.getAttribute('width'))).toBeCloseTo(2);
      expect(Number(drawn.getAttribute('height'))).toBeCloseTo(2);
      fireEvent.mouseUp(svg);
      expect(onSelectFixtures.mock.calls).toEqual([[[1, 2]]]);
      cleanup();
    }
  });

  it('replaces the selection with a plain box', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures });
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    fireEvent.mouseUp(svg);
    expect(onSelectFixtures.mock.calls).toEqual([[[1, 2]]]);
  });

  it('adds to the selection with Shift, Ctrl or Cmd held at the press', () => {
    for (const key of [{ shiftKey: true }, { ctrlKey: true }, { metaKey: true }]) {
      const onSelectFixtures = vi.fn();
      const svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4, 2]), onSelectFixtures });
      fireEvent.mouseDown(svg, { ...onDeck(-1.5, -1), ...key });
      fireEvent.mouseMove(svg, onDeck(0.5, 1));
      fireEvent.mouseUp(svg);
      // What was selected, then what the box added: Spot 2 was in both.
      expect(onSelectFixtures.mock.calls).toEqual([[[4, 2, 1]]]);
      cleanup();
    }
  });

  it('selects nothing with a plain box over empty floor, and keeps the selection with an additive one', () => {
    const plain = vi.fn();
    let svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures: plain });
    fireEvent.mouseDown(svg, onDeck(-4, 2));
    fireEvent.mouseMove(svg, onDeck(-3, 3));
    fireEvent.mouseUp(svg);
    expect(plain.mock.calls).toEqual([[[]]]);
    cleanup();

    const additive = vi.fn();
    svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures: additive });
    fireEvent.mouseDown(svg, { ...onDeck(-4, 2), shiftKey: true });
    fireEvent.mouseMove(svg, onDeck(-3, 3));
    fireEvent.mouseUp(svg);
    expect(additive.mock.calls).toEqual([[[4]]]);
  });

  it('is still a click under 5 pixels: no box, and the selection is cleared as before', () => {
    const onSelectFixtures = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW_AND_ONE, selectedIds: new Set([1]), onSelectFixtures, onFixtureClick,
    });
    // A plain click on empty floor.
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseUp(svg, px(20, 80));
    fireEvent.click(svg);
    // And one that wobbles 4 pixels.
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseMove(svg, px(24, 80));
    expect(box()).toBeNull();
    fireEvent.mouseUp(svg, px(24, 80));
    fireEvent.click(svg);
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(onFixtureClick.mock.calls).toEqual([[-1, false], [-1, false]]);
  });

  it('starts a box at exactly 5 pixels', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, onSelectFixtures });
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseMove(svg, px(23, 84));
    expect(box()).not.toBeNull();
    fireEvent.mouseUp(svg);
    expect(onSelectFixtures.mock.calls).toEqual([[[]]]);
  });

  it('lets a later click on empty floor clear the selection again', () => {
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, onSelectFixtures: vi.fn(), onFixtureClick });
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    fireEvent.mouseUp(svg);
    fireEvent.click(svg);
    expect(onFixtureClick).not.toHaveBeenCalled();
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseUp(svg, px(20, 80));
    fireEvent.click(svg);
    expect(onFixtureClick.mock.calls).toEqual([[-1, false]]);
  });

  it('takes what it holds when the pointer is carried off the plan', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, onSelectFixtures });
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    fireEvent.mouseLeave(svg);
    expect(onSelectFixtures.mock.calls).toEqual([[[1, 2]]]);
    expect(box()).toBeNull();
  });

  it('does not start from a press on a fixture', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, snapMode: 'none', onSelectFixtures, onFixtureDrag: vi.fn() });
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(80, 70));
    expect(box()).toBeNull();
    fireEvent.mouseUp(svg);
    expect(onSelectFixtures).not.toHaveBeenCalled();
  });

  it('draws no box where a selection cannot be set, or the plan is read-only', () => {
    const tries: Array<Partial<Props>> = [{}, { readonly: true, onSelectFixtures: vi.fn() }];
    for (const extra of tries) {
      const svg = plan(undefined, { fixtures: ROW_AND_ONE, ...extra });
      fireEvent.mouseDown(svg, onDeck(-1.5, -1));
      fireEvent.mouseMove(svg, onDeck(0.5, 1));
      expect(box()).toBeNull();
      fireEvent.mouseUp(svg);
      if (extra.onSelectFixtures) expect(extra.onSelectFixtures).not.toHaveBeenCalled();
      cleanup();
    }
  });

  it('works out in a scanned room, where the view has grown', () => {
    const onSelectFixtures = vi.fn();
    // The view is 22 m by 18 m from (-5, -4): stage (x, z) is at ((x + 11) * 10, (z + 9) * 10).
    const inRoom = (x: number, z: number) => ({ clientX: (x + 11) * 10, clientY: (z + 9) * 10 });
    const svg = plan(SCANNED, { fixtures: [...ROW, spot(4, 8, 6), spot(5, 9, 7)], onSelectFixtures });
    fireEvent.mouseDown(svg, inRoom(7.5, 5.5));
    fireEvent.mouseMove(svg, inRoom(9.5, 7.5));
    fireEvent.mouseUp(svg);
    expect(onSelectFixtures.mock.calls).toEqual([[[4, 5]]]);
  });
});

// ---------------------------------------------------------------------------
// The keyboard
// ---------------------------------------------------------------------------

/** Callbacks that note the order they were called in. */
function recorded() {
  const log: Array<[string, unknown]> = [];
  return {
    log,
    onFixtureDragStart: vi.fn((id: number) => { log.push(['start', id]); }),
    onFixturesDrag: vi.fn((moves: PlanMove[]) => { log.push(['moves', moves]); }),
    onFixtureDragEnd: vi.fn((id: number) => { log.push(['end', id]); }),
  };
}

const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

describe('StageView2D: Escape and R', () => {
  afterEach(cleanup);

  it('clears the selection on Escape', () => {
    const onFixtureClick = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2]), keyboard: true, onFixtureClick });
    press('Escape');
    expect(onFixtureClick.mock.calls).toEqual([[-1, false]]);
  });

  it('does nothing on Escape with nothing selected', () => {
    const onFixtureClick = vi.fn();
    plan(undefined, { fixtures: ROW, keyboard: true, onFixtureClick });
    press('Escape');
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('lets go of a box being drawn on Escape, and leaves the selection as it was', () => {
    const onFixtureClick = vi.fn();
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW_AND_ONE, selectedIds: new Set([4]), keyboard: true, onFixtureClick, onSelectFixtures,
    });
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    expect(box()).not.toBeNull();
    press('Escape');
    expect(box()).toBeNull();
    fireEvent.mouseUp(svg);
    fireEvent.click(svg);
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('selects the row of the selected fixture on R, small or capital', () => {
    for (const key of ['r', 'R']) {
      const onFixtureSelectRow = vi.fn();
      plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureSelectRow });
      press(key);
      expect(onFixtureSelectRow.mock.calls).toEqual([[2]]);
      cleanup();
    }
  });

  it('goes by the first selected fixture in the rig\'s order, as the Select row button does', () => {
    const onFixtureSelectRow = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([3, 2]), keyboard: true, onFixtureSelectRow });
    press('r');
    expect(onFixtureSelectRow.mock.calls).toEqual([[2]]);
  });

  it('does nothing on R with nothing selected, or with Ctrl, Cmd or Alt held', () => {
    const onFixtureSelectRow = vi.fn();
    plan(undefined, { fixtures: ROW, keyboard: true, onFixtureSelectRow });
    press('r');
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureSelectRow });
    // Ctrl+R reloads the page: that is the browser's key.
    expect(press('r', { ctrlKey: true })).toBe(true);
    press('r', { metaKey: true });
    press('r', { altKey: true });
    expect(onFixtureSelectRow).not.toHaveBeenCalled();
  });
});

describe('StageView2D: arrow keys', () => {
  afterEach(cleanup);

  it('nudges the selected fixture one grid step, reported as one drag from start to end', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    press('ArrowRight');
    expect(calls.log).toEqual([['start', 2], ['moves', [{ id: 2, x: 0.5, z: 0 }]], ['end', 2]]);
  });

  it('goes left and right across the plan, up upstage and down downstage', () => {
    const tries: Array<[string, number, number]> = [
      ['ArrowLeft', -0.5, 0], ['ArrowRight', 0.5, 0], ['ArrowUp', 0, -0.5], ['ArrowDown', 0, 0.5],
    ];
    for (const [key, x, z] of tries) {
      const calls = recorded();
      plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
      press(key);
      expect(calls.onFixturesDrag.mock.calls).toEqual([[[{ id: 2, x, z }]]]);
      cleanup();
    }
  });

  it('goes by the grid step it is given, and ten steps with Shift', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), gridSize: 0.25, keyboard: true, ...calls });
    press('ArrowDown');
    press('ArrowLeft', { shiftKey: true });
    expect(calls.onFixturesDrag.mock.calls).toEqual([
      [[{ id: 2, x: 0, z: 0.25 }]],
      [[{ id: 2, x: -2.5, z: 0 }]],
    ]);
  });

  it('moves the whole selection by one shift, in one report and one drag', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([1, 2, 3]), keyboard: true, ...calls });
    press('ArrowUp');
    expect(calls.log).toEqual([
      ['start', 1],
      ['moves', [{ id: 1, x: -1, z: -0.5 }, { id: 2, x: 0, z: -0.5 }, { id: 3, x: 1, z: -0.5 }]],
      ['end', 1],
    ]);
  });

  it('reports no height, so a nudge leaves heights alone', () => {
    const calls = recorded();
    plan(SCANNED, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), keyboard: true, ...calls });
    press('ArrowRight');
    const moves = calls.onFixturesDrag.mock.calls[0][0];
    expect(moves).toHaveLength(3);
    for (const move of moves) expect('y' in move).toBe(false);
  });

  it('holds the whole selection at the deck\'s edge, keeping its spacing', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), keyboard: true, ...calls });
    // Ten steps is 5 m; the deck ends at x = 5, a metre short of where Spot 3 would go.
    press('ArrowRight', { shiftKey: true });
    expect(calls.onFixturesDrag.mock.calls).toEqual([
      [[{ id: 1, x: 3, z: 0 }, { id: 2, x: 4, z: 0 }, { id: 3, x: 5, z: 0 }]],
    ]);
  });

  it('carries on past the deck in a scanned room, and is held at its wall', () => {
    const calls = recorded();
    const row = [spot(1, 4, 0), spot(2, 5, 0), spot(3, 6, 0)];
    plan(SCANNED, { fixtures: row, selectedIds: new Set([1, 2, 3]), keyboard: true, ...calls });
    press('ArrowRight');
    // The wall is at x = 10: 5 m would take Spot 3 to 11.
    press('ArrowRight', { shiftKey: true });
    expect(calls.onFixturesDrag.mock.calls).toEqual([
      [[{ id: 1, x: 4.5, z: 0 }, { id: 2, x: 5.5, z: 0 }, { id: 3, x: 6.5, z: 0 }]],
      [[{ id: 1, x: 8, z: 0 }, { id: 2, x: 9, z: 0 }, { id: 3, x: 10, z: 0 }]],
    ]);
  });

  it('is held at the wall of an L\'s notch', () => {
    const calls = recorded();
    const row = [spot(1, 2, 5), spot(2, 3, 5)];
    plan(L_SHAPED, { fixtures: row, selectedIds: new Set([1, 2]), gridSize: 0.25, keyboard: true, ...calls });
    // 2.5 m stage left; the notch's wall is at x = 4.
    press('ArrowRight', { shiftKey: true });
    expect(calls.onFixturesDrag.mock.calls).toEqual([[[{ id: 1, x: 3, z: 5 }, { id: 2, x: 4, z: 5 }]]]);
  });

  it('reports nothing at all when the selection is already against the edge it is pushed at', () => {
    const calls = recorded();
    plan(undefined, { fixtures: [spot(1, 3, 0), spot(2, 5, 0)], selectedIds: new Set([1, 2]), keyboard: true, ...calls });
    // Still the plan's key: the page must not scroll.
    expect(press('ArrowRight')).toBe(false);
    expect(calls.log).toEqual([]);
  });

  it('is one drag for each press, and none for a key held down', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    press('ArrowRight');
    press('ArrowRight', { repeat: true });
    press('ArrowRight', { repeat: true });
    press('ArrowDown');
    expect(calls.log.map(([what]) => what)).toEqual(['start', 'moves', 'end', 'start', 'moves', 'end']);
  });

  it('reports a single fixture through onFixtureDrag where no row can be carried', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureDragStart = vi.fn();
    const onFixtureDragEnd = vi.fn();
    plan(undefined, {
      fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureDrag, onFixtureDragStart, onFixtureDragEnd,
    });
    press('ArrowLeft');
    expect(onFixtureDrag.mock.calls).toEqual([[2, -0.5, 0]]);
    expect(onFixtureDragStart).toHaveBeenCalledTimes(1);
    expect(onFixtureDragEnd).toHaveBeenCalledTimes(1);
  });

  it('leaves an arrow key to the page with nothing selected', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, keyboard: true, ...calls });
    // Not prevented: the page may scroll.
    expect(press('ArrowDown')).toBe(true);
    expect(calls.log).toEqual([]);
  });

  it('leaves an arrow key alone with Ctrl, Cmd or Alt held', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    // Alt+Left is the browser's Back.
    expect(press('ArrowLeft', { altKey: true })).toBe(true);
    press('ArrowLeft', { ctrlKey: true });
    press('ArrowLeft', { metaKey: true });
    expect(calls.log).toEqual([]);
  });

  it('does not nudge while a fixture is held by the pointer', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    calls.log.length = 0;
    press('ArrowRight');
    expect(calls.log).toEqual([]);
  });
});

describe('StageView2D: when the keys are not the plan\'s', () => {
  const added: Element[] = [];
  afterEach(() => {
    cleanup();
    added.splice(0).forEach((element) => element.remove());
  });

  /** An element on the page, outside the plan, with the focus in it. */
  function focused(html: string): HTMLElement {
    const holder = document.createElement('div');
    holder.innerHTML = html;
    document.body.appendChild(holder);
    added.push(holder);
    const element = holder.querySelector<HTMLElement>('#it')!;
    element.focus();
    return element;
  }

  const FIELDS = [
    '<input id="it" />',
    '<textarea id="it"></textarea>',
    '<select id="it"><option>Grid</option></select>',
    '<div id="it" contenteditable="true" tabindex="0"></div>',
  ];

  it('ignores every key typed in an input, a textarea, a select or a contenteditable element', () => {
    for (const html of FIELDS) {
      const calls = recorded();
      const onFixtureClick = vi.fn();
      const onFixtureSelectRow = vi.fn();
      plan(undefined, {
        fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureClick, onFixtureSelectRow, ...calls,
      });
      const field = focused(html);
      for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'r', 'R', 'Escape']) {
        // Not prevented either: the key is the field's to use.
        expect(fireEvent.keyDown(field, { key })).toBe(true);
      }
      fireEvent.keyDown(field, { key: 'ArrowRight', shiftKey: true });
      expect(calls.log).toEqual([]);
      expect(onFixtureSelectRow).not.toHaveBeenCalled();
      expect(onFixtureClick).not.toHaveBeenCalled();
      cleanup();
      added.splice(0).forEach((element) => element.remove());
    }
  });

  it('ignores keys while the focus is in a field, wherever the key event lands', () => {
    const calls = recorded();
    const onFixtureClick = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureClick, ...calls });
    const field = focused('<input id="it" />');
    expect(document.activeElement).toBe(field);
    press('ArrowRight');
    press('Escape');
    expect(calls.log).toEqual([]);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('acts again once the focus has left the field', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    const field = focused('<input id="it" />');
    press('ArrowRight');
    expect(calls.log).toEqual([]);
    field.blur();
    press('ArrowRight');
    expect(calls.onFixturesDrag).toHaveBeenCalledTimes(1);
  });

  it('acts with the focus on a button, such as Select row after it was pressed', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    const button = focused('<button id="it">Select row</button>');
    fireEvent.keyDown(button, { key: 'ArrowRight' });
    expect(calls.onFixturesDrag).toHaveBeenCalledTimes(1);
  });

  it('ignores keys in a dialog in front of the plan', () => {
    const calls = recorded();
    const onFixtureClick = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureClick, ...calls });
    const button = focused('<div role="dialog"><button id="it">Close</button></div>');
    fireEvent.keyDown(button, { key: 'ArrowRight' });
    fireEvent.keyDown(button, { key: 'Escape' });
    expect(calls.log).toEqual([]);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('takes no key unless the keyboard is asked for: a plan that is not the one shown', () => {
    const calls = recorded();
    const onFixtureClick = vi.fn();
    const onFixtureSelectRow = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), onFixtureClick, onFixtureSelectRow, ...calls });
    for (const key of ['ArrowRight', 'r', 'Escape']) expect(press(key)).toBe(true);
    expect(calls.log).toEqual([]);
    expect(onFixtureSelectRow).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('takes no key on a read-only plan, or once the plan is gone', () => {
    const calls = recorded();
    const onFixtureClick = vi.fn();
    plan(undefined, {
      fixtures: ROW, selectedIds: new Set([2]), keyboard: true, readonly: true, onFixtureClick, ...calls,
    });
    press('ArrowRight');
    press('Escape');
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, onFixtureClick, ...calls });
    cleanup();
    press('ArrowRight');
    press('Escape');
    expect(calls.log).toEqual([]);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });
});
