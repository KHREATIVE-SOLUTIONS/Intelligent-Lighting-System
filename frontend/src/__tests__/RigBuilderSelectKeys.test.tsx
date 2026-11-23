// The rig editor with the 2D plan in it: what a click, a drag, a selection
// box and the keys leave in the editor's undo history and send to the
// server. The panels round the plan are left out and the API is a stand-in:
// nothing here reaches a backend, and nothing is sent to a light.
// docs/ROOM_SCAN.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RigBuilder from '../components/rig/RigBuilder';
import { rigsApi } from '../services/api';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig } from '../types';

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

const px = (clientX: number, clientY: number) => ({ clientX, clientY });
const onDeck = (x: number, z: number) => px((x + 6) * 10, (z + 5) * 10);
const grab = (name: string) => screen.getByText(name).parentElement!;
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

const history = () => useRigEditorStore.getState().undoStack.length;
const selected = () => [...useRigEditorStore.getState().selectedFixtureIds].sort((a, b) => a - b);

/** A click on a fixture, with no move at all. */
function click(name: string, at: { clientX: number; clientY: number }, svg: SVGSVGElement) {
  fireEvent.mouseDown(grab(name), at);
  fireEvent.mouseUp(svg, at);
}

/** What the nth batch-update sent, as [id, x, y, z] for each fixture. */
const sent = (n: number) => api.batchUpdateFixtures.mock.calls[n][1]
  .map((f) => [f.id, f.position_x, f.position_y, f.position_z]);

describe('RigBuilder: correcting fixtures on the 2D plan', () => {
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

  it('adds no undo step and saves nothing for a click, or a press that wobbles', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(63, 52));
    fireEvent.mouseMove(svg, px(57, 49));
    fireEvent.mouseUp(svg, px(57, 49));
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(selected()).toEqual([2]);
  });

  it('adds one undo step and sends one batch-update for a drag, however many moves it took', async () => {
    const svg = await editor();
    fireEvent.mouseDown(grab('Spot 2'), px(60, 50));
    fireEvent.mouseMove(svg, px(70, 50));
    fireEvent.mouseMove(svg, px(80, 50));
    fireEvent.mouseMove(svg, px(80, 60));
    fireEvent.mouseUp(svg, px(80, 60));
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures.mock.calls[0][0]).toBe(7);
    expect(sent(0)).toEqual([[2, 2, 4, 1]]);
  });

  it('selects with a box over empty floor, and adds to the selection with Shift', async () => {
    const svg = await editor();
    fireEvent.mouseDown(svg, onDeck(-1.5, -1));
    fireEvent.mouseMove(svg, onDeck(0.5, 1));
    fireEvent.mouseUp(svg, onDeck(0.5, 1));
    fireEvent.click(svg);
    expect(selected()).toEqual([1, 2]);
    fireEvent.mouseDown(svg, { ...onDeck(0.5, -1), shiftKey: true });
    fireEvent.mouseMove(svg, onDeck(1.5, 1));
    fireEvent.mouseUp(svg, onDeck(1.5, 1));
    fireEvent.click(svg);
    expect(selected()).toEqual([1, 2, 3]);
    // Selecting moved nothing.
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    // A plain click on empty floor still clears it.
    fireEvent.mouseDown(svg, px(20, 80));
    fireEvent.mouseUp(svg, px(20, 80));
    fireEvent.click(svg);
    expect(selected()).toEqual([]);
  });

  it('clears the selection on Escape', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    expect(selected()).toEqual([2]);
    press('Escape');
    expect(selected()).toEqual([]);
  });

  it('nudges a fixture with an arrow key: one undo step and one batch-update for each press', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    press('ArrowRight');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[2, 0.5, 4, 0]]);
    // The next press goes on from where the first left it.
    press('ArrowDown');
    await flush();
    expect(history()).toBe(2);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual([[2, 0.5, 4, 0.5]]);
  });

  it('selects the row on R and nudges it whole, held at the deck\'s edge, in one step and one request', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    press('r');
    expect(selected()).toEqual([1, 2, 3]);
    // Ten steps is 5 m; the deck ends at x = 5, so the row goes 4 m and keeps its spacing.
    press('ArrowRight', { shiftKey: true });
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual([[1, 3, 4, 0], [2, 4, 4, 0], [3, 5, 4, 0]]);
    // Against the edge: another press moves nothing, saves nothing and adds no step.
    press('ArrowRight', { shiftKey: true });
    press('ArrowRight');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
  });

  it('puts a nudged row back with one Undo', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    press('r');
    press('ArrowUp');
    await flush();
    expect(sent(0)).toEqual([[1, -1, 4, -0.5], [2, 0, 4, -0.5], [3, 1, 4, -0.5]]);
    fireEvent.click(screen.getByTestId('UndoIcon').closest('button')!);
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual([[1, -1, 4, 0], [2, 0, 4, 0], [3, 1, 4, 0]]);
  });

  it('ignores the keys while the rig\'s name is being typed', async () => {
    const svg = await editor();
    click('Spot 2', px(60, 50), svg);
    const name = screen.getByDisplayValue('Test Rig');
    name.focus();
    for (const key of ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'r', 'Escape']) {
      fireEvent.keyDown(name, { key });
    }
    await flush();
    expect(history()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(selected()).toEqual([2]);
    // Out of the field, the plan has the keyboard again.
    name.blur();
    press('ArrowRight');
    await flush();
    expect(history()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
  });
});
