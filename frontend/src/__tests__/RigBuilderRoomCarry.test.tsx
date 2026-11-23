// The rig editor when a truss edited in Edit Room takes its fixtures along:
// the rig is read again, so the plan draws them where the server put them,
// and the editor's own undo steps, which hold the old positions, are dropped.
// A change that moved no fixture reads nothing again. The same for the room's
// Undo, from the dialog and from the strip over the plan in walls mode. The
// panels round the plan are left out and the API is a stand-in: nothing here
// reaches a backend. docs/ROOM_SCAN.md, slice 17.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RigBuilder from '../components/rig/RigBuilder';
import { rigsApi, roomScanApi } from '../services/api';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig, RoomShell } from '../types';

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
  roomScanApi: {
    editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn(),
    getOutline: vi.fn(), setOutline: vi.fn(), moveOutlineCorner: vi.fn(), addOutlineCorner: vi.fn(),
    deleteOutlineCorner: vi.fn(),
  },
}));

// The panels round the plan have nothing to do with the room.
vi.mock('../components/rig/FixturePalette', () => ({ default: () => null }));
vi.mock('../components/rig/PatchTable', () => ({ default: () => null }));
vi.mock('../components/rig/FixtureProperties', () => ({ default: () => null }));
vi.mock('../components/rig/IdentifyWalkthrough', () => ({ default: () => null }));
vi.mock('../components/rig/RoomScanDialog', () => ({ default: () => null }));

const api = vi.mocked(rigsApi);
const roomApi = vi.mocked(roomScanApi);
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

// A scanned room 12 m by 10 m with 8 m of truss across it at 4.2 m, 2 m upstage of the middle...
const SHELL = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, across: 0.3 }],
});

// ...and the same truss moved 3 m downstage.
const MOVED = (): RoomShell => {
  const after = SHELL();
  after.truss_lines![0] = { ...after.truss_lines![0], z1: 1, z2: 1, suggested: false, basis: 'Moved by hand.' };
  return after;
};

/** The rig with its two spots hung on the truss at depth `z`. */
const rigAt = (z: number, shell: RoomShell, more: Record<string, unknown> = {}) => ({
  id: 7,
  name: 'Test Rig',
  stage_width: 10,
  stage_depth: 8,
  stage_height: 5,
  universes: [],
  created_at: '',
  updated_at: '',
  is_active: true,
  fixtures: [spot(1, 1, -2, 4.2, z), spot(2, 17, 2, 4.2, z)],
  room_shell: shell,
  ...more,
}) as unknown as Rig;

/** The editor with the rig loaded, and what a second read of the rig will answer. */
async function editor(first: Rig, again: Rig) {
  api.get.mockResolvedValueOnce(first).mockResolvedValue(again);
  render(
    <MemoryRouter initialEntries={['/rigs/7']}>
      <Routes>
        <Route path="/rigs/:id" element={<RigBuilder />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText('Spot 2');
}

const moves = (toZ: number) => [1, 2].map((id) => ({
  rig_fixture_id: id,
  name: `Spot ${id}`,
  from: { x: id === 1 ? -2 : 2, y: 4.2, z: toZ === 1 ? -2 : 1, rotation_y: 0 },
  to: { x: id === 1 ? -2 : 2, y: 4.2, z: toZ, rotation_y: 0 },
}));

// The toolbar's button carries its tooltip as its label, so it is found by its words.
const editRoomButton = () => screen.queryByText('Edit Room')?.closest('button') ?? null;
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;
const press = (key: string) => fireEvent.keyDown(document.body, { key });
const select = (ids: number[]) => act(() => { useRigEditorStore.getState().selectFixtures(ids); });
const undoSteps = () => useRigEditorStore.getState().undoStack.length;
// A fixture at (x, z) in this room is drawn at (x + 6, z + 5).
const drawnAt = (name: string) => screen.getByText(name).parentElement!.getAttribute('transform');

async function openRoom() {
  fireEvent.click(editRoomButton()!);
  await flush();
  expect(screen.getByText('Edit the room of Test Rig')).toBeTruthy();
}

describe('RigBuilder: Edit Room, fixtures following their truss', () => {
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

  it('reads the rig again after a truss took its fixtures along, and drops the editor\'s stale undo steps', async () => {
    roomApi.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: MOVED(),
      undo: { available: 1, label: 'Truss 1 moved, with 2 fixtures' },
      carry_fixtures: true, fixtures_moved: moves(1),
    });
    await editor(
      rigAt(-2, SHELL()),
      rigAt(1, MOVED(), { room_shell_edits: { available: 1, label: 'Truss 1 moved, with 2 fixtures' } }),
    );
    expect(drawnAt('Spot 2')).toBe('translate(8, 3)');
    // A nudge first: one step of the editor's own undo, which holds where Spot 2 was.
    select([2]);
    press('ArrowLeft');
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    await openRoom();

    fireEvent.change(field('Depth of Truss 1'), { target: { value: '1' } });
    fireEvent.click(button('Save Truss 1'));
    await flush();
    await flush();

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { center_z: 1, carry_fixtures: true });
    expect(screen.getByText('Truss 1 was moved to 0, 1. 2 fixtures hung on it moved with it.')).toBeTruthy();
    // The rig was read again: the plan draws the fixtures where the server carried them.
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(drawnAt('Spot 1')).toBe('translate(4, 6)');
    expect(drawnAt('Spot 2')).toBe('translate(8, 6)');
    // The step that would have written an old position back is gone, and the carry saved nothing itself.
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(undoButton().textContent).toBe('Undo: Truss 1 moved, with 2 fixtures');
    // The dialog is still open over the room as it now is.
    expect(field('Depth of Truss 1').value).toBe('1');
  });

  it('reads nothing again when the truss was told to go alone', async () => {
    roomApi.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: MOVED(),
      undo: { available: 1, label: 'Truss 1 moved' }, carry_fixtures: false, fixtures_moved: [],
    });
    await editor(rigAt(-2, SHELL()), rigAt(1, MOVED()));
    select([2]);
    press('ArrowLeft');
    await flush();
    await openRoom();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Move the fixtures hung on Truss 1' }));
    fireEvent.change(field('Depth of Truss 1'), { target: { value: '1' } });
    fireEvent.click(button('Save Truss 1'));
    await flush();
    await flush();

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { center_z: 1, carry_fixtures: false });
    expect(screen.getByText('Truss 1 was moved to 0, 1. The fixtures hung on it were left where they are.')).toBeTruthy();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(drawnAt('Spot 1')).toBe('translate(4, 3)');
    expect(undoSteps()).toBe(1);
  });

  it('reads the rig again when the room\'s Undo puts the fixtures back', async () => {
    const label = 'Truss 1 moved, with 2 fixtures';
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: label, room_shell: SHELL(), undo: { available: 0, label: null },
      fixtures_restored: moves(-2), fixtures_skipped: [],
      message: `Undone: ${label}. 2 fixtures put back where they hung before it.`,
    });
    await editor(rigAt(1, MOVED(), { room_shell_edits: { available: 1, label } }), rigAt(-2, SHELL()));
    expect(drawnAt('Spot 1')).toBe('translate(4, 6)');
    await openRoom();
    expect(undoButton().textContent).toBe(`Undo: ${label}`);

    fireEvent.click(undoButton());
    await flush();
    await flush();

    expect(screen.getByText(`Undone: ${label}. 2 fixtures put back where they hung before it.`)).toBeTruthy();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(drawnAt('Spot 1')).toBe('translate(4, 3)');
    expect(drawnAt('Spot 2')).toBe('translate(8, 3)');
    expect(undoButton().textContent).toBe('Nothing to undo');
  });

  it('reads the rig again when the Undo is pressed on the strip over the plan in walls mode', async () => {
    const label = 'Truss 1 moved, with 2 fixtures';
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: label, room_shell: SHELL(), undo: { available: 0, label: null },
      fixtures_restored: moves(-2), fixtures_skipped: [], outside: { items: [], fixtures: [], count: 0 },
      message: `Undone: ${label}. 2 fixtures put back where they hung before it.`,
    });
    await editor(rigAt(1, MOVED(), { room_shell_edits: { available: 1, label } }), rigAt(-2, SHELL()));
    fireEvent.click(editRoomButton()!);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Drag corners on the plan' }));
    await flush();

    fireEvent.click(screen.getByTestId('walls-mode-undo'));
    await flush();
    await flush();

    expect(roomApi.undoShellEdit).toHaveBeenCalledWith(7);
    expect(screen.getByTestId('walls-mode').textContent).toContain('2 fixtures put back where they hung before it.');
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(drawnAt('Spot 1')).toBe('translate(4, 3)');
  });
});
