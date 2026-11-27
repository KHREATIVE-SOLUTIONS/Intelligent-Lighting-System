// The 2D layout view under a finger or a pen: a long-press is the touch for
// Shift (on a fixture, and on empty floor before a box), the keys are also
// buttons over the plan, and the plan says when the keys are going somewhere
// else. docs/ROOM_SCAN.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { PlanMove } from '../components/rig/rowMove2d';
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
type At = { clientX: number; clientY: number };
const onDeck = (x: number, z: number): At => ({ clientX: (x + 6) * 10, clientY: (z + 5) * 10 });
const px = (clientX: number, clientY: number): At => ({ clientX, clientY });

const grab = (name: string) => screen.getByText(name).parentElement!;
const box = () => screen.queryByTestId('selection-box');
const mark = () => screen.queryByTestId('long-press-mark');
const hint = () => screen.queryByTestId('plan-keys-hint');
const pad = () => screen.queryByTestId('nudge-pad');
const padButton = (name: string) => within(pad()!).getByRole('button', { name });

const ROW = [spot(1, -1, 0), spot(2, 0, 0), spot(3, 1, 0)];
const ROW_AND_ONE = [...ROW, spot(4, 3, 3)];

/**
 * A pointer event as a finger sends it. Built by hand, with the pointer's
 * own fields written onto it, so it reads the same whether or not the test
 * environment knows what a PointerEvent is. Answers false when the plan
 * prevented it, as it does for a finger's press.
 */
function pointer(
  type: 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel',
  target: Element, at: At, more: { pointerType?: string; pointerId?: number; isPrimary?: boolean } = {},
) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: at.clientX, clientY: at.clientY });
  Object.defineProperty(event, 'pointerType', { value: more.pointerType ?? 'touch' });
  Object.defineProperty(event, 'pointerId', { value: more.pointerId ?? 1 });
  Object.defineProperty(event, 'isPrimary', { value: more.isPrimary ?? true });
  return fireEvent(target, event);
}

/** Lets the clock run with the finger held where it is. */
const hold = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });

/** Callbacks that note the order they were called in. */
function recorded() {
  const log: Array<[string, unknown]> = [];
  return {
    log,
    onFixtureClick: vi.fn((id: number, multi: boolean) => { log.push(['click', [id, multi]]); }),
    onFixtureDragStart: vi.fn((id: number) => { log.push(['start', id]); }),
    onFixtureDrag: vi.fn((id: number, x: number, z: number) => { log.push(['move', [id, x, z]]); }),
    onFixturesDrag: vi.fn((moves: PlanMove[]) => { log.push(['moves', moves]); }),
    onFixtureDragEnd: vi.fn((id: number) => { log.push(['end', id]); }),
  };
}

const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

// ---------------------------------------------------------------------------
// A long-press on a fixture: the touch for Shift-click
// ---------------------------------------------------------------------------

describe('StageView2D: a long-press on a fixture', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('adds the fixture to the selection once it has been held for 500 ms, and not before', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2]), ...calls });
    // The press is the plan's: the browser is to send no mouse events after it.
    expect(pointer('pointerdown', grab('Spot 3'), onDeck(1, 0))).toBe(false);
    expect(calls.log).toEqual([]);
    hold(499);
    expect(calls.log).toEqual([]);
    hold(1);
    // As Shift-click asks: this one too, and what was selected is kept.
    expect(calls.log).toEqual([['click', [3, true]]]);
    pointer('pointerup', svg, onDeck(1, 0));
    expect(calls.log).toEqual([['click', [3, true]]]);
  });

  it('takes a selected fixture back out', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), ...calls });
    pointer('pointerdown', grab('Spot 2'), onDeck(0, 0));
    hold(500);
    pointer('pointerup', svg, onDeck(0, 0));
    expect(calls.log).toEqual([['click', [2, true]]]);
  });

  it('never moves anything and reports no drag, wherever the finger goes afterwards', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', ...calls });
    pointer('pointerdown', grab('Spot 2'), onDeck(0, 0));
    hold(500);
    pointer('pointermove', svg, px(90, 70));
    pointer('pointermove', svg, px(20, 20));
    hold(2000);
    pointer('pointerup', svg, px(20, 20));
    expect(calls.log).toEqual([['click', [2, true]]]);
    expect(calls.onFixtureDragStart).not.toHaveBeenCalled();
    expect(calls.onFixtureDrag).not.toHaveBeenCalled();
    expect(calls.onFixturesDrag).not.toHaveBeenCalled();
    expect(calls.onFixtureDragEnd).not.toHaveBeenCalled();
  });

  it('is still a long-press with a wobble under 5 pixels', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1]), ...calls });
    pointer('pointerdown', grab('Spot 2'), px(60, 50));
    // 3 across and 2 down is 3.6 pixels.
    pointer('pointermove', svg, px(63, 52));
    hold(500);
    pointer('pointerup', svg, px(63, 52));
    expect(calls.log).toEqual([['click', [2, true]]]);
  });

  it('is a drag, and never a long-press, once the finger has gone 5 pixels', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, snapMode: 'none', ...calls, onFixturesDrag: undefined });
    pointer('pointerdown', grab('Spot 2'), px(60, 50));
    pointer('pointermove', svg, px(70, 50));
    // Selected alone and picked up as a mouse press would have, then moved a metre.
    expect(calls.log.map(([what]) => what)).toEqual(['click', 'start', 'move']);
    expect(calls.log[0]).toEqual(['click', [2, false]]);
    expect(calls.log[1]).toEqual(['start', 2]);
    const [id, x, z] = calls.log[2][1] as [number, number, number];
    expect(id).toBe(2);
    expect(x).toBeCloseTo(1);
    expect(z).toBeCloseTo(0);
    // Held there for as long as you like: it is a drag.
    hold(2000);
    pointer('pointerup', svg, px(70, 50));
    expect(calls.log.map(([what]) => what)).toEqual(['click', 'start', 'move', 'end']);
  });

  it('selects the fixture alone on a tap, and reports no drag', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), ...calls });
    pointer('pointerdown', grab('Spot 2'), onDeck(0, 0));
    // Nothing until the finger has shown what it is doing.
    expect(calls.log).toEqual([]);
    hold(300);
    pointer('pointerup', svg, onDeck(0, 0));
    expect(calls.log).toEqual([['click', [2, false]]]);
    // The timer went with the finger.
    hold(2000);
    expect(calls.log).toEqual([['click', [2, false]]]);
  });

  it('carries a selected row under a finger, as a mouse does', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), snapMode: 'none', ...calls });
    pointer('pointerdown', grab('Spot 2'), px(60, 50));
    pointer('pointermove', svg, px(60, 54));
    expect(calls.log).toEqual([]);
    pointer('pointermove', svg, px(60, 60));
    pointer('pointerup', svg, px(60, 60));
    // The selection is kept, so nothing is clicked.
    expect(calls.log.map(([what]) => what)).toEqual(['start', 'moves', 'end']);
    const moves = calls.log[1][1] as PlanMove[];
    expect(moves.map((move) => move.id)).toEqual([1, 2, 3]);
    for (const move of moves) expect(move.z).toBeCloseTo(1);
  });

  it('answers a pen as it does a finger', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1]), ...calls });
    pointer('pointerdown', grab('Spot 3'), onDeck(1, 0), { pointerType: 'pen' });
    hold(500);
    pointer('pointerup', svg, onDeck(1, 0), { pointerType: 'pen' });
    expect(calls.log).toEqual([['click', [3, true]]]);
  });

  it('leaves a mouse to the mouse events, however long its button is held', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1]), ...calls });
    // Not prevented, and not acted on.
    expect(pointer('pointerdown', grab('Spot 3'), onDeck(1, 0), { pointerType: 'mouse' })).toBe(true);
    hold(2000);
    pointer('pointermove', svg, px(90, 70), { pointerType: 'mouse' });
    pointer('pointerup', svg, px(90, 70), { pointerType: 'mouse' });
    expect(calls.log).toEqual([]);
    // The mouse's own press is what it always was: selected at once, and picked up.
    fireEvent.mouseDown(grab('Spot 3'), onDeck(1, 0));
    hold(2000);
    fireEvent.mouseUp(svg, onDeck(1, 0));
    expect(calls.log).toEqual([['click', [3, false]], ['start', 3], ['end', 3]]);
  });

  it('takes no notice of a second finger', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), ...calls });
    pointer('pointerdown', grab('Spot 3'), onDeck(1, 0));
    pointer('pointerdown', grab('Spot 1'), onDeck(-1, 0), { pointerId: 2, isPrimary: false });
    pointer('pointermove', svg, px(10, 10), { pointerId: 2, isPrimary: false });
    pointer('pointerup', svg, px(10, 10), { pointerId: 2, isPrimary: false });
    hold(500);
    pointer('pointerup', svg, onDeck(1, 0));
    expect(calls.log).toEqual([['click', [3, true]]]);
  });

  it('does nothing for a press the browser takes away', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2]), ...calls });
    pointer('pointerdown', grab('Spot 3'), onDeck(1, 0));
    hold(200);
    pointer('pointercancel', svg, onDeck(1, 0));
    hold(2000);
    expect(calls.log).toEqual([]);
  });

  it('does nothing on a read-only plan, or once the plan is gone', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([1]), readonly: true, ...calls });
    expect(pointer('pointerdown', grab('Spot 3'), onDeck(1, 0))).toBe(true);
    hold(2000);
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([1]), ...calls });
    pointer('pointerdown', grab('Spot 3'), onDeck(1, 0));
    cleanup();
    hold(2000);
    expect(calls.log).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// A long-press on empty floor: the touch for a Shift-drag
// ---------------------------------------------------------------------------

describe('StageView2D: a long-press on empty floor', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('starts a box that adds to the selection', () => {
    const onSelectFixtures = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures, onFixtureClick,
    });
    expect(pointer('pointerdown', svg, onDeck(-1.5, -1))).toBe(false);
    hold(499);
    expect(mark()).toBeNull();
    hold(1);
    // Marked where the finger is: (-1.5, -1) is (4.5, 4) in the view's units.
    const shown = mark()!;
    expect(Number(shown.getAttribute('cx'))).toBeCloseTo(4.5);
    expect(Number(shown.getAttribute('cy'))).toBeCloseTo(4);
    pointer('pointermove', svg, onDeck(0.5, 1));
    expect(box()).not.toBeNull();
    expect(mark()).toBeNull();
    expect(onSelectFixtures).not.toHaveBeenCalled();
    pointer('pointerup', svg, onDeck(0.5, 1));
    // What was selected, then Spot 1 and Spot 2 from the box.
    expect(onSelectFixtures.mock.calls).toEqual([[[4, 1, 2]]]);
    expect(box()).toBeNull();
    // The click that may follow clears nothing.
    fireEvent.click(svg);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('draws a plain box for a finger dragged without the wait, as a mouse does', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures });
    pointer('pointerdown', svg, onDeck(-1.5, -1));
    pointer('pointermove', svg, onDeck(0.5, 1));
    // Past 5 pixels the long-press is off: waiting now changes nothing.
    hold(2000);
    expect(mark()).toBeNull();
    pointer('pointerup', svg, onDeck(0.5, 1));
    expect(onSelectFixtures.mock.calls).toEqual([[[1, 2]]]);
  });

  it('changes nothing when the finger is lifted without drawing a box', () => {
    const onSelectFixtures = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures, onFixtureClick,
    });
    pointer('pointerdown', svg, px(20, 80));
    hold(500);
    expect(mark()).not.toBeNull();
    pointer('pointerup', svg, px(20, 80));
    expect(mark()).toBeNull();
    fireEvent.click(svg);
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('still clears the selection on a tap, as a click does', () => {
    const onSelectFixtures = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan(undefined, {
      fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures, onFixtureClick,
    });
    pointer('pointerdown', svg, px(20, 80));
    hold(200);
    pointer('pointerup', svg, px(20, 80));
    fireEvent.click(svg);
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(onFixtureClick.mock.calls).toEqual([[-1, false]]);
    // And after a long-press that drew nothing, the next tap clears it again.
    pointer('pointerdown', svg, px(20, 80));
    hold(500);
    pointer('pointerup', svg, px(20, 80));
    fireEvent.click(svg);
    pointer('pointerdown', svg, px(20, 80));
    pointer('pointerup', svg, px(20, 80));
    fireEvent.click(svg);
    expect(onFixtureClick.mock.calls).toEqual([[-1, false], [-1, false]]);
  });

  it('selects nothing when the browser takes the finger away half-way through a box', () => {
    const onSelectFixtures = vi.fn();
    const svg = plan(undefined, { fixtures: ROW_AND_ONE, selectedIds: new Set([4]), onSelectFixtures });
    pointer('pointerdown', svg, onDeck(-1.5, -1));
    hold(500);
    pointer('pointermove', svg, onDeck(0.5, 1));
    expect(box()).not.toBeNull();
    pointer('pointercancel', svg, onDeck(0.5, 1));
    expect(box()).toBeNull();
    expect(mark()).toBeNull();
    expect(onSelectFixtures).not.toHaveBeenCalled();
  });

  it('marks nothing where a selection cannot be set, or the plan is read-only', () => {
    const tries: Array<Partial<Props>> = [{}, { readonly: true, onSelectFixtures: vi.fn() }];
    for (const extra of tries) {
      const svg = plan(undefined, { fixtures: ROW_AND_ONE, ...extra });
      pointer('pointerdown', svg, onDeck(-1.5, -1));
      hold(500);
      expect(mark()).toBeNull();
      pointer('pointermove', svg, onDeck(0.5, 1));
      expect(box()).toBeNull();
      pointer('pointerup', svg, onDeck(0.5, 1));
      if (extra.onSelectFixtures) expect(extra.onSelectFixtures).not.toHaveBeenCalled();
      cleanup();
    }
  });
});

// ---------------------------------------------------------------------------
// The nudge pad
// ---------------------------------------------------------------------------

describe('StageView2D: the nudge pad', () => {
  afterEach(cleanup);

  it('is shown only where it is asked for, on a plan that can be edited, with something selected', () => {
    // Not asked for: as the plan always was.
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]) });
    expect(pad()).toBeNull();
    cleanup();
    plan(undefined, { fixtures: ROW, nudgePad: true });
    expect(pad()).toBeNull();
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true, readonly: true });
    expect(pad()).toBeNull();
    cleanup();
    // A selection of something that is not in the rig is no selection.
    plan(undefined, { fixtures: ROW, selectedIds: new Set([99]), nudgePad: true });
    expect(pad()).toBeNull();
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true });
    expect(pad()).not.toBeNull();
  });

  it('comes after the plan in its box, so the plan is still the first drawing there', () => {
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true });
    expect(svg.parentElement).toBe(pad()!.parentElement);
    expect(svg.compareDocumentPosition(pad()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(pad()!.querySelector('svg')).toBeNull();
  });

  it('names every button and makes each at least 44 pixels each way', () => {
    plan(undefined, {
      fixtures: ROW, selectedIds: new Set([1, 2]), nudgePad: true, onFixtureSelectRow: vi.fn(), onLayRow: vi.fn(),
    });
    const buttons = within(pad()!).getAllByRole('button') as HTMLButtonElement[];
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Nudge upstage', 'Nudge left', 'Nudge right', 'Nudge downstage', 'Ten grid steps for each tap',
      'Select the whole row', 'Lay the selection on the nearest truss',
    ]);
    for (const button of buttons) {
      expect(parseFloat(button.style.minWidth)).toBeGreaterThanOrEqual(44);
      expect(parseFloat(button.style.minHeight)).toBeGreaterThanOrEqual(44);
    }
  });

  it('nudges one grid step for a tap, reported as one drag from start to end', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true, ...calls });
    fireEvent.click(padButton('Nudge right'));
    expect(calls.log).toEqual([['start', 2], ['moves', [{ id: 2, x: 0.5, z: 0 }]], ['end', 2]]);
  });

  it('does with each arrow exactly what the matching key does', () => {
    const tries: Array<[string, string, number, number]> = [
      ['Nudge left', 'ArrowLeft', -0.5, 0], ['Nudge right', 'ArrowRight', 0.5, 0],
      ['Nudge upstage', 'ArrowUp', 0, -0.5], ['Nudge downstage', 'ArrowDown', 0, 0.5],
    ];
    for (const [name, key, x, z] of tries) {
      const calls = recorded();
      plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true, keyboard: true, ...calls });
      fireEvent.click(padButton(name));
      const tapped = [...calls.log];
      calls.log.length = 0;
      press(key);
      expect(tapped).toEqual([['start', 2], ['moves', [{ id: 2, x, z }]], ['end', 2]]);
      expect(calls.log).toEqual(tapped);
      cleanup();
    }
  });

  it('goes ten steps with the switch at 10x, and one again with it back at 1x', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), gridSize: 0.25, nudgePad: true, ...calls });
    const tenfold = padButton('Ten grid steps for each tap');
    expect(tenfold.textContent).toBe('1x');
    expect(tenfold.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(tenfold);
    expect(padButton('Ten grid steps for each tap').textContent).toBe('10x');
    expect(padButton('Ten grid steps for each tap').getAttribute('aria-pressed')).toBe('true');
    // Switching moves nothing.
    expect(calls.log).toEqual([]);
    fireEvent.click(padButton('Nudge left'));
    fireEvent.click(padButton('Ten grid steps for each tap'));
    fireEvent.click(padButton('Nudge downstage'));
    expect(calls.onFixturesDrag.mock.calls).toEqual([
      [[{ id: 2, x: -2.5, z: 0 }]],
      [[{ id: 2, x: 0, z: 0.25 }]],
    ]);
  });

  it('holds the whole selection at the deck\'s edge, keeping its spacing, in one report', () => {
    const calls = recorded();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2, 3]), nudgePad: true, ...calls });
    fireEvent.click(padButton('Ten grid steps for each tap'));
    // Ten steps is 5 m; the deck ends at x = 5, a metre short of where Spot 3 would go.
    fireEvent.click(padButton('Nudge right'));
    expect(calls.log).toEqual([
      ['start', 1],
      ['moves', [{ id: 1, x: 3, z: 0 }, { id: 2, x: 4, z: 0 }, { id: 3, x: 5, z: 0 }]],
      ['end', 1],
    ]);
  });

  it('carries on past the deck in a scanned room, and is held at its wall', () => {
    const calls = recorded();
    const row = [spot(1, 4, 0), spot(2, 5, 0), spot(3, 6, 0)];
    plan(SCANNED, { fixtures: row, selectedIds: new Set([1, 2, 3]), nudgePad: true, ...calls });
    fireEvent.click(padButton('Nudge right'));
    fireEvent.click(padButton('Ten grid steps for each tap'));
    // The wall is at x = 10: 5 m would take Spot 3 to 11.
    fireEvent.click(padButton('Nudge right'));
    expect(calls.onFixturesDrag.mock.calls).toEqual([
      [[{ id: 1, x: 4.5, z: 0 }, { id: 2, x: 5.5, z: 0 }, { id: 3, x: 6.5, z: 0 }]],
      [[{ id: 1, x: 8, z: 0 }, { id: 2, x: 9, z: 0 }, { id: 3, x: 10, z: 0 }]],
    ]);
    // No height is given: a tap leaves heights alone, as a key does.
    for (const [moves] of calls.onFixturesDrag.mock.calls) {
      for (const move of moves) expect('y' in move).toBe(false);
    }
  });

  it('reports nothing at all when the selection is already against the edge it is pushed at', () => {
    const calls = recorded();
    plan(undefined, { fixtures: [spot(1, 3, 0), spot(2, 5, 0)], selectedIds: new Set([1, 2]), nudgePad: true, ...calls });
    fireEvent.click(padButton('Nudge right'));
    expect(calls.log).toEqual([]);
  });

  it('selects the row of the first selected fixture, as R does', () => {
    const onFixtureSelectRow = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([3, 2]), nudgePad: true, onFixtureSelectRow });
    fireEvent.click(padButton('Select the whole row'));
    expect(onFixtureSelectRow.mock.calls).toEqual([[2]]);
    cleanup();
    // Left out where a row cannot be selected.
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true });
    expect(within(pad()!).queryByRole('button', { name: 'Select the whole row' })).toBeNull();
  });

  it('offers Lay on truss only where it is given, and only for two or more', () => {
    const onLayRow = vi.fn();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true });
    expect(within(pad()!).queryByRole('button', { name: 'Lay the selection on the nearest truss' })).toBeNull();
    cleanup();

    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), nudgePad: true, onLayRow });
    const one = padButton('Lay the selection on the nearest truss') as HTMLButtonElement;
    expect(one.disabled).toBe(true);
    fireEvent.click(one);
    expect(onLayRow).not.toHaveBeenCalled();
    cleanup();

    plan(undefined, { fixtures: ROW, selectedIds: new Set([1, 2]), nudgePad: true, onLayRow });
    const two = padButton('Lay the selection on the nearest truss') as HTMLButtonElement;
    expect(two.disabled).toBe(false);
    fireEvent.click(two);
    expect(onLayRow).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// The focus cue
// ---------------------------------------------------------------------------

describe('StageView2D: the focus cue', () => {
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
    act(() => { element.focus(); });
    return element;
  }

  it('says to click the plan while the focus is in a field, and stops when it leaves', () => {
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true });
    expect(hint()).toBeNull();
    const field = focused('<input id="it" />');
    expect(hint()!.textContent).toBe('Click the plan to use the keys');
    act(() => { field.blur(); });
    expect(hint()).toBeNull();
  });

  it('says so after a snap mode is chosen, when the focus is left on the drop-down', () => {
    plan(undefined, { fixtures: ROW, keyboard: true });
    focused('<div id="it" role="combobox" tabindex="0">Grid</div>');
    expect(hint()).not.toBeNull();
  });

  it('says so from the start when the plan is drawn with the focus already in a field', () => {
    focused('<input id="it" />');
    plan(undefined, { fixtures: ROW, keyboard: true });
    expect(hint()).not.toBeNull();
  });

  it('says nothing with the focus on a button, or in a dialog in front of the plan', () => {
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true });
    focused('<button id="it">Select row</button>');
    expect(hint()).toBeNull();
    focused('<div role="dialog"><input id="it" /></div>');
    expect(hint()).toBeNull();
  });

  it('says nothing on a plan that does not answer the keyboard, or is read-only', () => {
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]) });
    focused('<input id="it" />');
    expect(hint()).toBeNull();
    cleanup();
    plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, readonly: true });
    expect(hint()).toBeNull();
  });

  it('takes the focus when the plan is clicked, so the keys are the plan\'s again', () => {
    const calls = recorded();
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true, ...calls });
    const field = focused('<input id="it" />');
    expect(document.activeElement).toBe(field);
    press('ArrowRight');
    expect(calls.log).toEqual([]);
    // A click on empty floor, off every fixture.
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseUp(svg, px(20, 80));
    expect(document.activeElement).toBe(svg.parentElement);
    expect(hint()).toBeNull();
    press('ArrowRight');
    expect(calls.log).toEqual([['start', 2], ['moves', [{ id: 2, x: 0.5, z: 0 }]], ['end', 2]]);
  });

  it('takes the focus under a finger too, and on a press on a fixture', () => {
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]), keyboard: true });
    focused('<input id="it" />');
    pointer('pointerdown', svg, px(20, 80));
    pointer('pointerup', svg, px(20, 80));
    expect(document.activeElement).toBe(svg.parentElement);
    expect(hint()).toBeNull();

    focused('<input id="it" />');
    expect(hint()).not.toBeNull();
    fireEvent.mouseDown(grab('Spot 1'), onDeck(-1, 0));
    fireEvent.mouseUp(svg, onDeck(-1, 0));
    expect(document.activeElement).toBe(svg.parentElement);
    expect(hint()).toBeNull();
  });

  it('does not take the focus on a plan that does not answer the keyboard', () => {
    const svg = plan(undefined, { fixtures: ROW, selectedIds: new Set([2]) });
    const field = focused('<input id="it" />');
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseUp(svg, px(20, 80));
    expect(document.activeElement).toBe(field);
    // Nor can it: it is not something the focus can be given to.
    expect(svg.parentElement!.hasAttribute('tabindex')).toBe(false);
  });

  it('lets a click on the cue itself through to the plan', () => {
    plan(undefined, { fixtures: ROW, keyboard: true });
    focused('<input id="it" />');
    expect(hint()!.style.pointerEvents).toBe('none');
  });
});
