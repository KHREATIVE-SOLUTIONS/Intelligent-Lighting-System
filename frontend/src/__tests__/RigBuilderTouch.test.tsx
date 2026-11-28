// The rig editor with the 2D plan in it, used from a phone or a tablet: what
// a long-press, a finger's drag and a tap on the nudge pad leave in the
// editor's undo history and send to the server, and the cue that says the
// keys are going to a field. The panels round the plan are left out and the
// API is a stand-in: nothing here reaches a backend, and nothing is sent to
// a light. docs/ROOM_SCAN.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RigBuilder from '../components/rig/RigBuilder';
import { rigsApi } from '../services/api';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig } from '../types';

// Each test renders the whole RigBuilder: alone they take 1-3 s, but in a full parallel run
// on a busy machine they can pass the 5 s default. See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  rigsApi: {
    get: vi.fn(),
    getConflicts: vi.fn(),
    batchUpdateFixtures: vi.fn(),
    update: vi.fn(),
    updateFixture: vi.fn(),
    autoPatch: vi.fn(),
    testAll: vi.fn(),
    getNextAddress: vi.fn(),
    addFixture: vi.fn(),
  },
  fixturesApi: { get: vi.fn() },
}));

// The panels round the plan have nothing to do with moving a fixture on it.
vi.mock('../components/rig/FixturePalette', () => ({ default: () => null }));
vi.mock('../components/rig/PatchTable', () => ({ default: () => null }));
vi.mock('../components/rig/FixtureProperties', () => ({ default: () => null }));
vi.mock('../components/rig/IdentifyWalkthrough', () => ({ default: () => null }));
vi.mock('../components/rig/RoomScanDialog', () => ({ default: () => null }));

const api = vi.mocked(rigsApi);
const flush = () => act(async () => {});

const spot = (id: number, x: number) => ({
  id,
  rig_id: 7,
  fixture_id: 1,
  name: `Spot ${id}`,
  universe: 0,
  dmx_address: id,
  position_x: x,
  position_y: 4,
  position_z: 0,
  rotation_x: 0,
  rotation_y: 0,
  rotation_z: 0,
  tags: ['position_unconfirmed'],
  is_active: true,
  is_inverted: false,
  is_address_locked: false,
});

// A 10 m by 8 m deck with no scanned room, and a row of three a metre apart.
const rig = () => ({
  id: 7,
  name: 'Test Rig',
  stage_width: 10,
  stage_depth: 8,
  stage_height: 5,
  universes: [],
  created_at: '',
  updated_at: '',
  is_active: true,
  fixtures: [spot(1, -1), spot(2, 0), spot(3, 1)],
}) as unknown as Rig;

/** The editor with the rig loaded, and its plan drawn at 10 pixels to the metre. */
async function editor() {
  render(
    <MemoryRouter initialEntries={['/rigs/7']}>
      <Routes>
        <Route path="/rigs/:id" element={<RigBuilder />} />
      </Routes>
    </MemoryRouter>,
  );
  // The plan is the drawing the fixture's name is in: the toolbar's icons are drawings too.
  const svg = (await screen.findByText('Spot 2')).closest('svg') as SVGSVGElement;
  // The view is 12 m by 10 m from the origin: centre stage is at (60, 50).
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: 120, bottom: 100, width: 120, height: 100, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

type At = { clientX: number; clientY: number };
const px = (clientX: number, clientY: number): At => ({ clientX, clientY });
const onDeck = (x: number, z: number): At => px((x + 6) * 10, (z + 5) * 10);
const grab = (name: string) => screen.getByText(name).parentElement!;
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

const history = () => useRigEditorStore.getState().undoStack.length;
const selected = () => [...useRigEditorStore.getState().selectedFixtureIds].sort((a, b) => a - b);

/** A click on a fixture with a mouse, with no move at all. */
function click(name: string, at: At, svg: SVGSVGElement) {
  fireEvent.mouseDown(grab(name), at);
  fireEvent.mouseUp(svg, at);
}

/**
 * A pointer event as a finger sends it, built by hand so it reads the same
 * whether or not the test environment knows what a PointerEvent is.
 */
function touch(type: 'pointerdown' | 'pointermove' | 'pointerup', target: Element, at: At) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: at.clientX, clientY: at.clientY });
  Object.defineProperty(event, 'pointerType', { value: 'touch' });
  Object.defineProperty(event, 'pointerId', { value: 1 });
  Object.defineProperty(event, 'isPrimary', { value: true });
  return fireEvent(target, event);
}

/**
 * A finger held still on `target` for half a second, then moved to each of
 * `then` and lifted. The clock is a stand-in only for as long as the finger
 * is down: the editor loads, and saves, on the real one.
 */
function longPress(target: Element, at: At, svg: SVGSVGElement, then: At[] = []) {
  vi.useFakeTimers();
  try {
    touch('pointerdown', target, at);
    act(() => { vi.advanceTimersByTime(500); });
    for (const next of then) touch('pointermove', svg, next);
    touch('pointerup', svg, then.length > 0 ? then[then.length - 1] : at);
  } finally {
    vi.useRealTimers();
  }
}

const pad = () => screen.queryByTestId('nudge-pad');
const tap = (name: string) => fireEvent.click(within(pad()!).getByRole('button', { name }));

/** What the nth batch-update sent, as [id, x, y, z] for each fixture. */
const sent = (n: number) => api.batchUpdateFixtures.mock.calls[n][1]
  .map((f) => [f.id, f.position_x, f.position_y, f.position_z]);

describe('RigBuilder: the 2D plan under a finger', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(rig());
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('adds a fixture to the selection on a long-press, and takes it out on another', async () => {
    const svg = await editor();
    click('Spot 1', onDeck(-1, 0), svg);
    expect(selected()).toEqual([1]);
    longPress(grab('Spot 3'), onDeck(1, 0), svg);
    expect(selected()).toEqual([1, 3]);
    longPress(grab('Spot 1'), onDeck(-1, 0), svg);
    expect(selected()).toEqual([3]);
    // Selecting moved nothing.
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('moves nothing and adds no undo step for a long-press, wherever the finger then goes', async () => {
    const svg = await editor();
    click('Spot 1', onDeck(-1, 0), svg);
    // Held on Spot 3, then dragged three metres across and two down before lifting.
    longPress(grab('Spot 3'), onDeck(1, 0), svg, [px(85, 60), px(100, 70)]);
    await flush();
    expect(selected()).toEqual([1, 3]);
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    // And the next move is a step of its own, not one left armed by the press.
    press('ArrowRight');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[1, -0.5, 4, 0], [3, 1.5, 4, 0]]);
  });

  it('adds what a box takes in to the selection after a long-press on empty floor', async () => {
    const svg = await editor();
    click('Spot 3', onDeck(1, 0), svg);
    expect(selected()).toEqual([3]);
    // Held at (-1.5, -1), then a box out to (0.5, 1): Spot 1 and Spot 2 are in it.
    longPress(svg, onDeck(-1.5, -1), svg, [onDeck(0.5, 1)]);
    fireEvent.click(svg);
    expect(selected()).toEqual([1, 2, 3]);
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('keeps the selection when a long-press on empty floor is lifted without a box', async () => {
    const svg = await editor();
    click('Spot 3', onDeck(1, 0), svg);
    longPress(svg, px(20, 80), svg);
    fireEvent.click(svg);
    expect(selected()).toEqual([3]);
  });

  it('moves a fixture under a finger in one undo step and one batch-update', async () => {
    const svg = await editor();
    touch('pointerdown', grab('Spot 2'), px(60, 50));
    touch('pointermove', svg, px(70, 50));
    touch('pointermove', svg, px(80, 50));
    touch('pointermove', svg, px(80, 60));
    touch('pointerup', svg, px(80, 60));
    await flush();
    expect(selected()).toEqual([2]);
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[2, 2, 4, 1]]);
  });

  it('selects a fixture on a tap, and adds no undo step', async () => {
    const svg = await editor();
    touch('pointerdown', grab('Spot 2'), px(60, 50));
    touch('pointerup', svg, px(60, 50));
    await flush();
    expect(selected()).toEqual([2]);
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });
});

describe('RigBuilder: the nudge pad', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(rig());
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(cleanup);

  it('is there while something is selected, and gone when nothing is', async () => {
    const svg = await editor();
    expect(pad()).toBeNull();
    click('Spot 2', px(60, 50), svg);
    expect(pad()).not.toBeNull();
    press('Escape');
    expect(pad()).toBeNull();
  });

  it('has no Lay on truss in a rig with no scanned truss', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    expect(within(pad()!).queryByRole('button', { name: 'Lay the selection on the nearest truss' })).toBeNull();
    expect(within(pad()!).getByRole('button', { name: 'Select the whole row' })).toBeTruthy();
  });

  it('nudges with each tap: one undo step and one batch-update for each', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    tap('Nudge right');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[2, 0.5, 4, 0]]);
    // The next tap goes on from where the first left it.
    tap('Nudge downstage');
    await flush();
    expect(history()).toBe(2);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual([[2, 0.5, 4, 0.5]]);
    tap('Nudge left');
    tap('Nudge upstage');
    await flush();
    expect(history()).toBe(4);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(4);
    expect(sent(3)).toEqual([[2, 0, 4, 0]]);
  });

  it('saves exactly what the matching key saves', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    tap('Nudge right');
    await flush();
    // Back where it was, then the key.
    fireEvent.click(screen.getByTestId('UndoIcon').closest('button')!);
    await flush();
    press('ArrowRight');
    await flush();
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(3);
    expect(sent(2)).toEqual(sent(0));
    expect(history()).toBe(1);
  });

  it('selects the row and nudges it whole at 10x, held at the deck\'s edge, in one step and one request', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    tap('Select the whole row');
    expect(selected()).toEqual([1, 2, 3]);
    tap('Ten grid steps for each tap');
    // Switching the step moves nothing.
    await flush();
    expect(history()).toBe(0);
    // Ten steps is 5 m; the deck ends at x = 5, so the row goes 4 m and keeps its spacing.
    tap('Nudge right');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[1, 3, 4, 0], [2, 4, 4, 0], [3, 5, 4, 0]]);
    // Against the edge: another tap moves nothing, saves nothing and adds no step.
    tap('Nudge right');
    tap('Ten grid steps for each tap');
    tap('Nudge right');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
  });

  it('puts a row nudged from the pad back with one Undo', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    tap('Select the whole row');
    tap('Nudge upstage');
    await flush();
    expect(sent(0)).toEqual([[1, -1, 4, -0.5], [2, 0, 4, -0.5], [3, 1, 4, -0.5]]);
    fireEvent.click(screen.getByTestId('UndoIcon').closest('button')!);
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual([[1, -1, 4, 0], [2, 0, 4, 0], [3, 1, 4, 0]]);
  });
});

describe('RigBuilder: the focus cue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(rig());
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(cleanup);

  const hint = () => screen.queryByTestId('plan-keys-hint');

  it('says to click the plan while the rig\'s name is being typed, and a click on the plan brings the keys back', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    expect(hint()).toBeNull();
    const name = screen.getByDisplayValue('Test Rig');
    act(() => { name.focus(); });
    expect(hint()!.textContent).toBe('Click the plan to use the keys');
    // The keys are the field's: nothing moves.
    fireEvent.keyDown(name, { key: 'ArrowRight' });
    await flush();
    expect(history()).toBe(0);

    // A press on the fixture that is selected: the plan takes the focus, and nothing else changes.
    click('Spot 2', px(60, 50), svg);
    expect(document.activeElement).toBe(svg.parentElement);
    expect(hint()).toBeNull();
    expect(selected()).toEqual([2]);
    press('ArrowRight');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[2, 0.5, 4, 0]]);
  });

  it('says nothing after a toolbar button is pressed: the keys are still the plan\'s', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    const selectRow = screen.getByText('Select row').closest('button')!;
    act(() => { selectRow.focus(); });
    expect(hint()).toBeNull();
  });
});
