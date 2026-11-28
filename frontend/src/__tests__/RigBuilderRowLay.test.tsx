// The rig editor with the 2D plan in it: a whole row dragged, and a row laid
// along scanned truss, each saved in one batch-update and one undo step, put
// back by one Undo and made again by one Redo. The panels round the plan are
// left out and the API is a stand-in: nothing here reaches a backend, and
// nothing is sent to a light. docs/ROOM_SCAN.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RigBuilder from '../components/rig/RigBuilder';
import { rigsApi } from '../services/api';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig } from '../types';

// Each test renders the whole RigBuilder: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
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

const spot = (id: number, address: number, x: number, y: number, z: number) => ({
  id,
  rig_id: 7,
  fixture_id: 1,
  name: `Spot ${id}`,
  universe: 0,
  dmx_address: address,
  position_x: x,
  position_y: y,
  position_z: z,
  rotation_x: 0,
  rotation_y: 0,
  rotation_z: 0,
  tags: ['position_unconfirmed'],
  is_active: true,
  is_inverted: false,
  is_address_locked: false,
});

const rigWith = (fixtures: ReturnType<typeof spot>[], more: Record<string, unknown> = {}) => ({
  id: 7,
  name: 'Test Rig',
  stage_width: 10,
  stage_depth: 8,
  stage_height: 5,
  universes: [],
  created_at: '',
  updated_at: '',
  is_active: true,
  fixtures,
  ...more,
}) as unknown as Rig;

// A 10 m by 8 m deck with no scanned room, and a row of three a metre apart at 4 m.
const DECK_RIG = () => rigWith([spot(1, 1, -1, 4, 0), spot(2, 2, 0, 4, 0), spot(3, 3, 1, 4, 0)]);

// The same deck in a scanned room 12 m by 10 m, with 8 m of truss across it
// at 4.2 m, 2 m upstage. Three fixtures a metre downstage of it at 3 m, their
// ids not in address order: by address they run Spot 2, Spot 3, Spot 1.
const TRUSS_RIG = () => rigWith(
  [spot(1, 20, 2, 3, -1), spot(2, 1, -2, 3, -1), spot(3, 10, 0, 3, -1)],
  {
    room_shell: {
      source: 'scan',
      room: { width: 12, depth: 10, height: 6 },
      truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, across: 0.3 }],
    },
  },
);

/** The editor with the rig loaded. */
async function editor() {
  render(
    <MemoryRouter initialEntries={['/rigs/7']}>
      <Routes>
        <Route path="/rigs/:id" element={<RigBuilder />} />
      </Routes>
    </MemoryRouter>,
  );
  // The plan is the drawing the fixture's name is in: the toolbar's icons are drawings too.
  return (await screen.findByText('Spot 2')).closest('svg') as SVGSVGElement;
}

/** The deck rig's plan, drawn at 10 pixels to the metre. */
async function deckEditor() {
  const svg = await editor();
  // The view is 12 m by 10 m from the origin: centre stage is at (60, 50).
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: 120, bottom: 100, width: 120, height: 100, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

const px = (clientX: number, clientY: number) => ({ clientX, clientY });
const grab = (name: string) => screen.getByText(name).parentElement!;
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

const undoSteps = () => useRigEditorStore.getState().undoStack.length;
const redoSteps = () => useRigEditorStore.getState().redoStack.length;
const selected = () => [...useRigEditorStore.getState().selectedFixtureIds].sort((a, b) => a - b);
const select = (ids: number[]) => act(() => { useRigEditorStore.getState().selectFixtures(ids); });

const undoButton = () => screen.getByTestId('UndoIcon').closest('button')!;
const redoButton = () => screen.getByTestId('RedoIcon').closest('button')!;

/** What the nth batch-update sent, as [id, x, y, z] for each fixture. */
const sent = (n: number) => api.batchUpdateFixtures.mock.calls[n][1]
  .map((f) => [f.id, f.position_x, f.position_y, f.position_z]);

const ROW_BEFORE = [[1, -1, 4, 0], [2, 0, 4, 0], [3, 1, 4, 0]];
// Carried a metre stage left and two downstage.
const ROW_AFTER = [[1, 0, 4, 2], [2, 1, 4, 2], [3, 2, 4, 2]];

// 8 m shared between three: 2.667 m apart and 1.333 m in from each end, in
// address order (Spot 2, Spot 3, Spot 1), on the truss and at its height.
const LAID = [[1, 2.667, 4.2, -2], [2, -2.667, 4.2, -2], [3, 0, 4.2, -2]];
const NOT_LAID = [[1, 2, 3, -1], [2, -2, 3, -1], [3, 0, 3, -1]];

describe('RigBuilder: a row moved on the 2D plan', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(cleanup);

  /** Selects the row with R, then drags it by Spot 2: two downstage, then one stage left. */
  async function dragRow(svg: SVGSVGElement) {
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseUp(svg, px(60, 50));
    press('r');
    expect(selected()).toEqual([1, 2, 3]);
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(60, 70));
    fireEvent.mouseMove(svg, px(70, 70));
    fireEvent.mouseUp(svg, px(70, 70));
    // The click a browser sends after the drag lands on the floor behind the row.
    fireEvent.click(svg);
    await flush();
  }

  it('saves a dragged row in one batch-update and one undo step, however many moves it took', async () => {
    api.get.mockResolvedValue(DECK_RIG());
    const svg = await deckEditor();
    await dragRow(svg);
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures.mock.calls[0][0]).toBe(7);
    // The whole row by the one shift: its spacing is kept, and no height changed.
    expect(sent(0)).toEqual(ROW_AFTER);
    // The row is still what is selected.
    expect(selected()).toEqual([1, 2, 3]);
  });

  it('puts a dragged row back with one Undo, and carries it again with one Redo', async () => {
    api.get.mockResolvedValue(DECK_RIG());
    const svg = await deckEditor();
    await dragRow(svg);

    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(redoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual(ROW_BEFORE);

    fireEvent.click(redoButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(3);
    expect(sent(2)).toEqual(ROW_AFTER);

    // And back once more: the step Redo left is the whole row's too.
    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(4);
    expect(sent(3)).toEqual(ROW_BEFORE);
  });

  it('has nothing to redo once a new move is made after an Undo', async () => {
    api.get.mockResolvedValue(DECK_RIG());
    const svg = await deckEditor();
    await dragRow(svg);
    fireEvent.click(undoButton());
    await flush();
    expect(redoSteps()).toBe(1);
    // The row is still selected: one step upstage.
    press('ArrowUp');
    await flush();
    expect(redoSteps()).toBe(0);
    expect(undoSteps()).toBe(1);
    expect(sent(2)).toEqual([[1, -1, 4, -0.5], [2, 0, 4, -0.5], [3, 1, 4, -0.5]]);
    expect((redoButton() as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('RigBuilder: Lay on truss', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(cleanup);

  const layButton = () => screen.getByText('Lay on truss').closest('button') as HTMLButtonElement;

  it('is offered only in a rig whose scan found truss, and needs two fixtures', async () => {
    api.get.mockResolvedValue(DECK_RIG());
    await editor();
    select([1, 2, 3]);
    expect(screen.queryByText('Lay on truss')).toBeNull();
    cleanup();
    // The selection is the store's, and outlives the editor that made it.
    useRigEditorStore.setState({ selectedFixtureIds: new Set() });

    api.get.mockResolvedValue(TRUSS_RIG());
    await editor();
    expect(layButton().disabled).toBe(true);
    select([2]);
    expect(layButton().disabled).toBe(true);
    select([1, 2]);
    expect(layButton().disabled).toBe(false);
  });

  it('saves the laid row in one batch-update and one undo step, at the truss\'s height', async () => {
    api.get.mockResolvedValue(TRUSS_RIG());
    await editor();
    select([1, 2, 3]);
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures.mock.calls[0][0]).toBe(7);
    expect(sent(0)).toEqual(LAID);
    expect(screen.getByText('Laid 3 fixtures along Truss 1, 2.67 m apart, at 4.20 m.')).toBeTruthy();
    // Laying is not selecting: the row is still what is selected.
    expect(selected()).toEqual([1, 2, 3]);
  });

  it('puts the row back with one Undo, heights and all, and lays it again with one Redo', async () => {
    api.get.mockResolvedValue(TRUSS_RIG());
    await editor();
    select([1, 2, 3]);
    fireEvent.click(layButton());
    await flush();

    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(redoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    // Off the truss again and back down at 3 m.
    expect(sent(1)).toEqual(NOT_LAID);

    fireEvent.click(redoButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(3);
    expect(sent(2)).toEqual(LAID);

    // The step Redo left knows the heights too.
    fireEvent.click(undoButton());
    await flush();
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(4);
    expect(sent(3)).toEqual(NOT_LAID);
  });

  it('moves nothing, saves nothing and adds no step when pressed again on a row already laid', async () => {
    api.get.mockResolvedValue(TRUSS_RIG());
    await editor();
    select([1, 2, 3]);
    fireEvent.click(layButton());
    await flush();
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(screen.getByText('The 3 fixtures are already laid along Truss 1, 2.67 m apart, at 4.20 m.')).toBeTruthy();
  });

  it('lays the row from the nudge pad\'s button as the toolbar\'s does, in one step', async () => {
    api.get.mockResolvedValue(TRUSS_RIG());
    await editor();
    select([1, 2, 3]);
    const pad = within(screen.getByTestId('nudge-pad'));
    fireEvent.click(pad.getByRole('button', { name: 'Lay the selection on the nearest truss' }));
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(LAID);
    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(sent(1)).toEqual(NOT_LAID);
  });
});
