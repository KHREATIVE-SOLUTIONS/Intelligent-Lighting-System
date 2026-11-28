// The rig editor with the 2D plan in it: a selection mirrored, a selection
// spaced evenly, and a row laid on truss at a chosen spacing, each saved in
// one batch-update and one undo step. The panels round the plan are left out
// and the API is a stand-in: nothing here reaches a backend, and nothing is
// sent to a light. docs/ROOM_SCAN.md.
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
  // A guess, and one head set to run its pan the other way.
  tags: id === 1 ? ['position_unconfirmed', 'pan_invert'] : ['position_unconfirmed'],
  is_active: true,
  is_inverted: id === 3,
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

// A 10 m by 8 m deck with no scanned room. One fixture stage right, one on
// the centre line, and one stage left at another height and depth.
const MIRROR_RIG = () => rigWith([spot(1, 1, -3, 4, 1), spot(2, 2, 0, 4, 1), spot(3, 3, 2, 3, -2)]);
const UNMIRRORED = [[1, -3, 4, 1], [3, 2, 3, -2]];
// Each as far the other side of x = 0; the one on the line is not sent at all.
const MIRRORED = [[1, 3, 4, 1], [3, -2, 3, -2]];

// The same deck in an L-shaped scanned room, 12 m by 10 m with x > 2, z > 1 walled off.
const L_RIG = () => rigWith(
  [spot(1, 1, -3, 4, 3), spot(2, 2, -4, 4, -3)],
  {
    room_shell: {
      source: 'scan',
      room: {
        width: 12, depth: 10, height: 6,
        outline: [{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 1 }, { x: 2, z: 1 }, { x: 2, z: 5 }, { x: -6, z: 5 }],
      },
    },
  },
);

// A row of four by address that a suggestion left uneven, one of them low and out of line.
const EVEN_RIG = () => rigWith([
  spot(1, 1, -2, 4, 0), spot(2, 2, -1.5, 3.5, 0.5), spot(3, 3, 0.5, 4, 0), spot(4, 4, 4, 4, 0),
]);
const UNEVEN = [[2, -1.5, 3.5, 0.5], [3, 0.5, 4, 0]];
// 6 m between four: 2 m apart on the line between the ends. Heights as they were.
const EVENED = [[2, 0, 3.5, 0], [3, 2, 4, 0]];

// The deck in a scanned room 12 m by 10 m, with 8 m of truss across it at
// 4.2 m, 2 m upstage. Three fixtures a metre downstage of it at 3 m, 2 m
// apart, their ids not in address order: by address they run Spot 2, 3, 1.
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
const NOT_LAID = [[1, 2, 3, -1], [2, -2, 3, -1], [3, 0, 3, -1]];
// The whole truss shared out, as Lay on truss always did.
const FILLED = [[1, 2.667, 4.2, -2], [2, -2.667, 4.2, -2], [3, 0, 4.2, -2]];
// Their own 2 m, centred on the middle of the truss.
const KEPT = [[1, 2, 4.2, -2], [2, -2, 4.2, -2], [3, 0, 4.2, -2]];
// 1.5 m apart, centred.
const SET = [[1, 1.5, 4.2, -2], [2, -1.5, 4.2, -2], [3, 0, 4.2, -2]];

/** The editor with the rig loaded. */
async function editor(rig: Rig) {
  api.get.mockResolvedValue(rig);
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

const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

const undoSteps = () => useRigEditorStore.getState().undoStack.length;
const redoSteps = () => useRigEditorStore.getState().redoStack.length;
const selected = () => [...useRigEditorStore.getState().selectedFixtureIds].sort((a, b) => a - b);
const select = (ids: number[]) => act(() => { useRigEditorStore.getState().selectFixtures(ids); });

const undoButton = () => screen.getByTestId('UndoIcon').closest('button')!;
const redoButton = () => screen.getByTestId('RedoIcon').closest('button')!;
// The toolbar's buttons are named by their words; the pad's by a longer label.
const mirrorButton = () => screen.getByRole('button', { name: 'Mirror' }) as HTMLButtonElement;
const evenButton = () => screen.getByText('Space evenly').closest('button') as HTMLButtonElement;
const layButton = () => screen.getByText('Lay on truss').closest('button') as HTMLButtonElement;
const layChoice = () => screen.getByLabelText('Lay on truss spacing') as HTMLSelectElement;
const layMetres = () => screen.queryByLabelText('Spacing in metres') as HTMLInputElement | null;
const pad = () => within(screen.getByTestId('nudge-pad'));

/** What the nth batch-update sent, as [id, x, y, z] for each fixture. */
const sent = (n: number) => api.batchUpdateFixtures.mock.calls[n][1]
  .map((f) => [f.id, f.position_x, f.position_y, f.position_z]);

/** Every field the batch-updates sent, across all of them. */
const sentFields = () => [...new Set(
  api.batchUpdateFixtures.mock.calls.flatMap((call) => call[1].flatMap((f) => Object.keys(f))),
)].sort();
const POSITION_ONLY = ['id', 'position_x', 'position_y', 'position_z'];

const reset = () => {
  vi.clearAllMocks();
  api.getConflicts.mockResolvedValue({ conflicts: [] });
  api.batchUpdateFixtures.mockResolvedValue(undefined as never);
  useRigEditorStore.setState({
    viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
    selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
  });
};

describe('RigBuilder: Mirror', () => {
  beforeEach(reset);
  afterEach(cleanup);

  it('needs something selected', async () => {
    await editor(MIRROR_RIG());
    expect(mirrorButton().disabled).toBe(true);
    select([3]);
    expect(mirrorButton().disabled).toBe(false);
  });

  it('mirrors the selection about the stage centre line in one batch-update and one undo step', async () => {
    await editor(MIRROR_RIG());
    select([1, 2, 3]);
    fireEvent.click(mirrorButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures.mock.calls[0][0]).toBe(7);
    // Heights and depths as they were; the fixture on the line did not move.
    expect(sent(0)).toEqual(MIRRORED);
    expect(screen.getByText('Mirrored 3 fixtures left to right about the stage centre line.')).toBeTruthy();
    // Mirroring is not selecting.
    expect(selected()).toEqual([1, 2, 3]);
  });

  it('sends positions and nothing else: guesses stay guesses, and no invert is swapped', async () => {
    await editor(MIRROR_RIG());
    select([1, 2, 3]);
    fireEvent.click(mirrorButton());
    await flush();
    expect(sentFields()).toEqual(POSITION_ONLY);
    // Nothing was written fixture by fixture either: no tag, no flag.
    expect(api.updateFixture).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
  });

  it('puts the selection back with one Undo, and mirrors it again with one Redo', async () => {
    await editor(MIRROR_RIG());
    select([1, 2, 3]);
    fireEvent.click(mirrorButton());
    await flush();

    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(redoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual(UNMIRRORED);

    fireEvent.click(redoButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(3);
    expect(sent(2)).toEqual(MIRRORED);
  });

  it('does the same for the M key, one step for each press', async () => {
    await editor(MIRROR_RIG());
    select([1, 2, 3]);
    press('m');
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(MIRRORED);
    // A key held down is still one mirror.
    press('m', { repeat: true });
    await flush();
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    // Pressed again it is mirrored back, as a step of its own.
    press('M', { shiftKey: true });
    await flush();
    expect(undoSteps()).toBe(2);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual(UNMIRRORED);
  });

  it('does the same from the nudge pad', async () => {
    await editor(MIRROR_RIG());
    select([1, 3]);
    fireEvent.click(pad().getByRole('button', { name: 'Mirror the selection left to right' }));
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(MIRRORED);
    expect(screen.getByText('Mirrored 2 fixtures left to right about the stage centre line.')).toBeTruthy();
  });

  it('leaves M alone with nothing selected, and while the rig\'s name is typed', async () => {
    await editor(MIRROR_RIG());
    press('m');
    select([1, 3]);
    const name = screen.getByDisplayValue('Test Rig');
    name.focus();
    fireEvent.keyDown(name, { key: 'm' });
    await flush();
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('moves nothing, saves nothing and adds no step for a fixture on the centre line', async () => {
    await editor(MIRROR_RIG());
    select([2]);
    fireEvent.click(mirrorButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(screen.getByText('The fixture is on the stage centre line: there is nothing to mirror.')).toBeTruthy();
  });

  it('mirrors one fixture alone, with no scanned room', async () => {
    await editor(MIRROR_RIG());
    select([3]);
    fireEvent.click(mirrorButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(sent(0)).toEqual([[3, -2, 3, -2]]);
    expect(screen.getByText('Mirrored 1 fixture left to right about the stage centre line.')).toBeTruthy();
  });

  it('goes by the scanned room, and holds a place in the notch of an L at its wall', async () => {
    await editor(L_RIG());
    select([1, 2]);
    fireEvent.click(mirrorButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    // (-3, 3) would mirror into the notch at (3, 3): it stops on the wall at x = 2.
    expect(sent(0)).toEqual([[1, 2, 4, 3], [2, 4, 4, -3]]);
    expect(screen.getByText(
      'Mirrored 2 fixtures left to right about the room\'s centre line (x = 0.00 m). 1 held at the wall.',
    )).toBeTruthy();
  });
});

describe('RigBuilder: Space evenly', () => {
  beforeEach(reset);
  afterEach(cleanup);

  it('needs three fixtures selected', async () => {
    await editor(EVEN_RIG());
    expect(evenButton().disabled).toBe(true);
    select([1, 2]);
    expect(evenButton().disabled).toBe(true);
    select([1, 2, 3]);
    expect(evenButton().disabled).toBe(false);
  });

  it('spaces the row between its ends in one batch-update and one undo step, keeping heights', async () => {
    await editor(EVEN_RIG());
    select([1, 2, 3, 4]);
    fireEvent.click(evenButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures.mock.calls[0][0]).toBe(7);
    // The two ends are not sent: they did not move.
    expect(sent(0)).toEqual(EVENED);
    expect(sentFields()).toEqual(POSITION_ONLY);
    expect(api.updateFixture).not.toHaveBeenCalled();
    expect(screen.getByText('Spaced 4 fixtures evenly, 2.00 m apart, between the first and the last by address.'))
      .toBeTruthy();
    expect(selected()).toEqual([1, 2, 3, 4]);
  });

  it('puts the row back with one Undo, and spaces it again with one Redo', async () => {
    await editor(EVEN_RIG());
    select([1, 2, 3, 4]);
    fireEvent.click(evenButton());
    await flush();

    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(redoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual(UNEVEN);

    fireEvent.click(redoButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(redoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(3);
    expect(sent(2)).toEqual(EVENED);
  });

  it('moves nothing, saves nothing and adds no step when pressed again on an even row', async () => {
    await editor(EVEN_RIG());
    select([1, 2, 3, 4]);
    fireEvent.click(evenButton());
    await flush();
    fireEvent.click(evenButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(screen.getByText('The 4 fixtures are already evenly spaced, 2.00 m apart.')).toBeTruthy();
  });

  it('does the same from the nudge pad, which also needs three', async () => {
    await editor(EVEN_RIG());
    select([1, 2]);
    const two = pad().getByRole('button', { name: 'Space the selection evenly' }) as HTMLButtonElement;
    expect(two.disabled).toBe(true);
    select([1, 2, 3, 4]);
    fireEvent.click(pad().getByRole('button', { name: 'Space the selection evenly' }));
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(EVENED);
  });
});

describe('RigBuilder: the spacing Lay on truss lays a row at', () => {
  beforeEach(reset);
  afterEach(cleanup);

  it('is offered only where Lay on truss is', async () => {
    await editor(MIRROR_RIG());
    select([1, 2, 3]);
    expect(screen.queryByLabelText('Lay on truss spacing')).toBeNull();
    expect(pad().queryByLabelText('Spacing on the truss')).toBeNull();
  });

  it('fills the truss until something else is chosen', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    expect(layChoice().value).toBe('fill');
    expect(layMetres()).toBeNull();
    fireEvent.click(layButton());
    await flush();
    expect(sent(0)).toEqual(FILLED);
  });

  it('keeps the row\'s spacing, centred on the truss, in one batch-update and one undo step', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    fireEvent.change(layChoice(), { target: { value: 'keep' } });
    expect(layChoice().value).toBe('keep');
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(KEPT);
    expect(sentFields()).toEqual(POSITION_ONLY);
    expect(screen.getByText('Laid 3 fixtures along Truss 1, 2.00 m apart, at 4.20 m.')).toBeTruthy();

    // One Undo puts them back, heights and all.
    fireEvent.click(undoButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(sent(1)).toEqual(NOT_LAID);
  });

  it('lays at a typed spacing, centred', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    fireEvent.change(layChoice(), { target: { value: 'set' } });
    fireEvent.change(layMetres()!, { target: { value: '1.5' } });
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(SET);
    expect(screen.getByText('Laid 3 fixtures along Truss 1, 1.50 m apart, at 4.20 m.')).toBeTruthy();
  });

  it('moves nothing and says why when the row would be longer than the truss', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    fireEvent.change(layChoice(), { target: { value: 'set' } });
    fireEvent.change(layMetres()!, { target: { value: '5' } });
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(screen.getByText('At 5.00 m apart the row is 10.00 m long, and Truss 1 is 8.00 m. Nothing was moved.'))
      .toBeTruthy();
  });

  it('moves nothing and says why when the spacing typed is not a number', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    fireEvent.change(layChoice(), { target: { value: 'set' } });
    fireEvent.change(layMetres()!, { target: { value: 'wide' } });
    fireEvent.click(layButton());
    await flush();
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(screen.getByText('Type a spacing in metres above zero, such as 1.2. Nothing was moved.')).toBeTruthy();
  });

  it('is one choice, shared by the toolbar and the nudge pad', async () => {
    await editor(TRUSS_RIG());
    select([1, 2, 3]);
    const padChoice = () => pad().getByLabelText('Spacing on the truss') as HTMLSelectElement;
    expect(padChoice().value).toBe('fill');
    fireEvent.change(padChoice(), { target: { value: 'keep' } });
    expect(layChoice().value).toBe('keep');
    expect(padChoice().value).toBe('keep');
    // The pad's own button then lays the row at the spacing it has.
    fireEvent.click(pad().getByRole('button', { name: 'Lay the selection on the nearest truss' }));
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual(KEPT);
  });
});
