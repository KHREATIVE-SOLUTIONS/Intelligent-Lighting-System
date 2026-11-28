// The rig editor with the Edit Room dialog in it: what the scan found is
// renamed and deleted, the plan draws the room as it now is, and no fixture,
// save or undo step is touched on the way. The panels round the plan are left
// out and the API is a stand-in: nothing here reaches a backend.
// docs/ROOM_SCAN.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RigBuilder from '../components/rig/RigBuilder';
import { rigsApi, roomScanApi } from '../services/api';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig, RoomShell } from '../types';

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
const press = (key: string) => fireEvent.keyDown(document.body, { key });
const select = (ids: number[]) => act(() => { useRigEditorStore.getState().selectFixtures(ids); });
const undoSteps = () => useRigEditorStore.getState().undoStack.length;
const planTruss = () => screen.queryAllByTestId('room-plan-truss-line');
const planRaised = () => screen.queryAllByTestId('room-plan-raised');

async function openRoom() {
  fireEvent.click(editRoomButton()!);
  await flush();
  expect(screen.getByText('Edit the room of Test Rig')).toBeTruthy();
}

describe('RigBuilder: Edit Room', () => {
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

  it('is offered only for a rig with a scanned room', async () => {
    await editor(rigWith());
    expect(editRoomButton()).toBeNull();
    cleanup();
    await editor(rigWith({ room_shell: SHELL() }));
    expect(editRoomButton()).not.toBeNull();
  });

  it('is not offered for a room that did not come from a scan', async () => {
    await editor(rigWith({ room_shell: { dome: { radius: 9, center_x: 0, center_z: 0, rim_height: 5, apex_height: 8 } } }));
    expect(editRoomButton()).toBeNull();
  });

  it('lists what the scan found', async () => {
    await editor(rigWith({ room_shell: SHELL() }));
    await openRoom();
    expect(field('Name of Stage').value).toBe('Stage');
    expect(field('Name of Truss 1').value).toBe('Truss 1');
    expect(field('Depth of Truss 1').value).toBe('-2');
  });

  it('renames a truss on the plan without loading the rig again or saving a fixture', async () => {
    const after = SHELL();
    after.truss_lines![0].name = 'Front truss';
    roomApi.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: after });
    await editor(rigWith({ room_shell: SHELL() }));
    expect(screen.getByText(/^Truss 1 . hangs at 4\.20 m$/)).toBeTruthy();
    await openRoom();

    fireEvent.change(field('Name of Truss 1'), { target: { value: 'Front truss' } });
    fireEvent.click(button('Save Truss 1'));
    await flush();

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { name: 'Front truss' });
    // The plan under the dialog draws the room as the server answered it.
    expect(screen.getByText(/^Front truss . hangs at 4\.20 m$/)).toBeTruthy();
    expect(screen.queryByText(/^Truss 1 . hangs at 4\.20 m$/)).toBeNull();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
    expect(undoSteps()).toBe(0);
  });

  it('takes a deleted truss off the plan, and Lay on truss with it', async () => {
    const after = SHELL();
    after.truss_lines = [];
    roomApi.deleteShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, removed: {}, room_shell: after,
      message: 'Truss 1 was taken out of the stored room. No fixture was moved.',
    });
    await editor(rigWith({ room_shell: SHELL() }));
    expect(planTruss()).toHaveLength(1);
    expect(screen.queryByText('Lay on truss')).not.toBeNull();
    await openRoom();

    fireEvent.click(button('Delete Truss 1'));
    expect(roomApi.deleteShellItem).not.toHaveBeenCalled();
    fireEvent.click(button('Delete it'));
    await flush();

    expect(roomApi.deleteShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0);
    expect(planTruss()).toHaveLength(0);
    // The stage is still there, and so is the room: only the truss went.
    expect(planRaised()).toHaveLength(1);
    expect(screen.getByTestId('room-plan-walls')).toBeTruthy();
    // With no scanned truss left there is nothing to lay a row along.
    expect(screen.queryByText('Lay on truss')).toBeNull();
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('leaves a fixture move and its undo step as they were', async () => {
    const after = SHELL();
    after.risers![0].name = 'Main stage';
    roomApi.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after });
    await editor(rigWith({ room_shell: SHELL() }));
    // Spot 1 nudged half a metre stage left: one save and one undo step.
    select([1]);
    press('ArrowRight');
    await flush();
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    const spotOne = () => screen.getByText('Spot 1').parentElement!.getAttribute('transform');
    const moved = spotOne();

    await openRoom();
    fireEvent.change(field('Name of Stage'), { target: { value: 'Main stage' } });
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(/^Main stage . 0\.60 m high$/)).toBeTruthy();
    // The fixture is where the nudge left it, and the step that undoes it is still there.
    expect(spotOne()).toBe(moved);
    expect(undoSteps()).toBe(1);
    expect(api.batchUpdateFixtures).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});
