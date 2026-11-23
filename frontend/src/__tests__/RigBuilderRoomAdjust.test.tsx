// The rig editor with the Edit Room dialog in it, beyond a rename and a
// delete: a resized or raised item and an added truss drawn on the plan with
// no reload, and the room's own Undo, whose count comes with the rig and is
// kept on it between openings of the dialog. No fixture, save or editor undo
// step is touched on the way. The panels round the plan are left out and the
// API is a stand-in: nothing here reaches a backend. docs/ROOM_SCAN.md.
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
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
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

// A scanned room 12 m by 10 m: a stage, and 8 m of truss across it at 4.2 m.
const SHELL = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2, across: 0.3 }],
});

const rigWith = (more: Record<string, unknown> = {}) => ({
  id: 7,
  name: 'Test Rig',
  stage_width: 10,
  stage_depth: 8,
  stage_height: 5,
  universes: [],
  created_at: '',
  updated_at: '',
  is_active: true,
  fixtures: [spot(1, 1, -1, 3, 0), spot(2, 2, 1, 3, 0)],
  ...more,
}) as unknown as Rig;

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
  await screen.findByText('Spot 2');
}

// The toolbar's button carries its tooltip as its label, so it is found by its words.
const editRoomButton = () => screen.queryByText('Edit Room')?.closest('button') ?? null;
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;
const press = (key: string) => fireEvent.keyDown(document.body, { key });
const select = (ids: number[]) => act(() => { useRigEditorStore.getState().selectFixtures(ids); });
const undoSteps = () => useRigEditorStore.getState().undoStack.length;
const planTruss = () => screen.queryAllByTestId('room-plan-truss-line');

async function openRoom() {
  fireEvent.click(editRoomButton()!);
  await flush();
  expect(screen.getByText('Edit the room of Test Rig')).toBeTruthy();
}

// A second truss, added by hand downstage of the first.
const withBackTruss = (): RoomShell => {
  const after = SHELL();
  after.truss_lines!.push({
    name: 'Back truss', x1: -3, z1: 2, x2: 3, z2: 2, height: 4, across: 0.3, suggested: false, added_by_hand: true,
    basis: 'Added by hand.',
  });
  return after;
};

describe('RigBuilder: Edit Room, sizes, adding and undo', () => {
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

  it('shows the room\'s sizes and has nothing to undo for a room nobody has edited', async () => {
    await editor(rigWith({ room_shell: SHELL() }));
    await openRoom();
    expect(field('Width of Stage').value).toBe('6');
    expect(field('Length of Truss 1').value).toBe('8');
    expect(field('Height of Truss 1').value).toBe('4.2');
    expect(undoButton().textContent).toBe('Nothing to undo');
    expect(undoButton().disabled).toBe(true);
  });

  it('offers the undo the rig came with: the steps are kept on the server', async () => {
    await editor(rigWith({ room_shell: SHELL(), room_shell_edits: { available: 2, label: 'Stage renamed' } }));
    await openRoom();
    expect(undoButton().textContent).toBe('Undo: Stage renamed (1 more)');
    expect(undoButton().disabled).toBe(false);
  });

  it('draws a raised stage on the plan without loading the rig again or saving a fixture', async () => {
    const after = SHELL();
    after.risers![0].height = 0.9;
    roomApi.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo: { available: 1, label: 'Stage resized' },
    });
    await editor(rigWith({ room_shell: SHELL() }));
    expect(screen.getByText(/^Stage . 0\.60 m high$/)).toBeTruthy();
    await openRoom();

    fireEvent.change(field('Height of Stage'), { target: { value: '0.9' } });
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { height: 0.9 });
    // The plan under the dialog draws the room as the server answered it.
    expect(screen.getByText(/^Stage . 0\.90 m high$/)).toBeTruthy();
    expect(screen.queryByText(/^Stage . 0\.60 m high$/)).toBeNull();
    expect(undoButton().textContent).toBe('Undo: Stage resized');
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
    // The room's undo is its own: the editor's stack has no step for it.
    expect(undoSteps()).toBe(0);
  });

  it('puts a truss added by hand on the plan', async () => {
    roomApi.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 1, item: {}, room_shell: withBackTruss(),
      undo: { available: 1, label: 'Back truss added' },
      message: 'Back truss was added to the stored room as a overhead line. No fixture was moved.',
    });
    await editor(rigWith({ room_shell: SHELL() }));
    expect(planTruss()).toHaveLength(1);
    await openRoom();

    fireEvent.change(screen.getByRole('combobox', { name: 'What to add' }), { target: { value: 'truss_line' } });
    fireEvent.change(field('Name of the new item'), { target: { value: 'Back truss' } });
    fireEvent.change(field('Depth of the new item'), { target: { value: '2' } });
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(roomApi.addShellItem).toHaveBeenCalledWith(7, 'truss_lines', {
      name: 'Back truss', center_x: 0, center_z: 2, length: 6, heading_deg: 0, height: 4,
    });
    expect(planTruss()).toHaveLength(2);
    expect(field('Name of Back truss').value).toBe('Back truss');
    expect(undoButton().textContent).toBe('Undo: Back truss added');
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(undoSteps()).toBe(0);
  });

  it('takes a room edit back with the room\'s own Undo, and leaves the editor\'s undo alone', async () => {
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Back truss added', room_shell: SHELL(), undo: { available: 0, label: null },
      message: 'Undone: Back truss added. No fixture was moved.',
    });
    await editor(rigWith({
      room_shell: withBackTruss(), room_shell_edits: { available: 1, label: 'Back truss added' },
    }));
    expect(planTruss()).toHaveLength(2);
    // Spot 1 nudged half a metre stage left: one save and one undo step of the editor's own.
    select([1]);
    press('ArrowRight');
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    const spotOne = () => screen.getByText('Spot 1').parentElement!.getAttribute('transform');
    const moved = spotOne();
    await openRoom();
    expect(undoButton().textContent).toBe('Undo: Back truss added');

    fireEvent.click(undoButton());
    await flush();

    expect(roomApi.undoShellEdit).toHaveBeenCalledTimes(1);
    expect(roomApi.undoShellEdit).toHaveBeenCalledWith(7);
    // The plan draws the room as it was before the truss was added.
    expect(planTruss()).toHaveLength(1);
    expect(screen.queryByLabelText('Name of Back truss')).toBeNull();
    expect(screen.getByText('Undone: Back truss added. No fixture was moved.')).toBeTruthy();
    expect(undoButton().textContent).toBe('Nothing to undo');
    // The fixture is where the nudge left it, and the step that undoes the nudge is still there.
    expect(spotOne()).toBe(moved);
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('keeps what can be undone on the rig when the dialog is closed and opened again', async () => {
    const after = SHELL();
    after.risers![0].width = 8;
    roomApi.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo: { available: 1, label: 'Stage resized' },
    });
    await editor(rigWith({ room_shell: SHELL() }));
    await openRoom();
    fireEvent.change(field('Width of Stage'), { target: { value: '8' } });
    fireEvent.click(button('Save Stage'));
    await flush();
    expect(undoButton().textContent).toBe('Undo: Stage resized');

    // By its words: the notice above the rows has a close button of its own, named Close too.
    fireEvent.click(screen.getByText('Close'));
    await flush();
    await openRoom();

    expect(field('Width of Stage').value).toBe('8');
    expect(undoButton().textContent).toBe('Undo: Stage resized');
    expect(undoButton().disabled).toBe(false);
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});
