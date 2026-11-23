// The rig editor with Edit Room's walls mode in it: the dialog hands the
// corners to the plan, a corner dragged there is one request and one step of
// the room's own undo, the plan draws the walls the server answered with, a
// refused move goes back, and no fixture, save or editor undo step is touched
// on the way. The panels round the plan are left out and the API is a
// stand-in: nothing here reaches a backend. docs/ROOM_SCAN.md.
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

// A scanned box room 12 m by 10 m round a 10 m by 8 m stage.
const SHELL = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
});

// The same room with its downstage stage left corner pulled out to 8 m across.
const PULLED = (): RoomShell => ({
  ...SHELL(),
  room: {
    width: 16, depth: 10, height: 6,
    outline: [{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 8, z: 5 }, { x: -6, z: 5 }],
  },
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
  room_shell: SHELL(),
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
const handles = () => screen.queryAllByTestId(/^wall-corner-\d+$/);
const handle = (index: number) => screen.getByTestId(`wall-corner-${index}`);
const wallsDrawn = () => screen.getByTestId('room-plan-walls').getAttribute('points');
const strip = () => screen.queryByTestId('walls-mode');
const undoSteps = () => useRigEditorStore.getState().undoStack.length;

/** Opens Edit Room and presses "Drag corners on the plan". */
async function wallsMode() {
  fireEvent.click(editRoomButton()!);
  await flush();
  fireEvent.click(screen.getByRole('button', { name: 'Drag corners on the plan' }));
  await flush();
}

/**
 * The plan at 10 pixels to the metre. With the 12 m by 10 m room the view
 * is 14 m by 12 m from (-1, -1): stage (x, z) is at ((x + 7) * 10, (z + 6) * 10).
 */
function planSvg() {
  const svg = screen.getByTestId('room-plan-walls').closest('svg')!;
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: w * 10, bottom: h * 10, width: w * 10, height: h * 10, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}
const inRoom = (x: number, z: number) => ({ clientX: (x + 7) * 10, clientY: (z + 6) * 10 });

/** Drags corner `index` from where it is to (x, z). */
async function dragCorner(index: number, from: [number, number], to: [number, number]) {
  const svg = planSvg();
  fireEvent.mouseDown(handle(index), inRoom(...from));
  fireEvent.mouseMove(svg, inRoom(...to));
  fireEvent.mouseUp(svg, inRoom(...to));
  // The request is answered, and then the plan lets go of where the corner was dropped.
  await flush();
  await flush();
}

// A corner at (x, z) is drawn at (x + 6, z + 5).
const BOX_DRAWN = '0,0 12,0 12,10 0,10';

describe('RigBuilder: dragging the walls of a scanned room on the plan', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    api.batchUpdateFixtures.mockResolvedValue(undefined as never);
    roomApi.getOutline.mockResolvedValue({
      rig_id: 7, outline: [], box: true, outside: { items: [], fixtures: [], count: 0 },
    });
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });
  afterEach(cleanup);

  it('has no corner handles until Edit Room hands the walls to the plan', async () => {
    await editor(rigWith());
    expect(handles()).toHaveLength(0);
    expect(strip()).toBeNull();

    await wallsMode();

    expect(handles()).toHaveLength(4);
    expect(strip()!.textContent).toContain('Dragging the walls: drag a numbered corner to move it.');
    expect(wallsDrawn()).toBe(BOX_DRAWN);
  });

  it('moves a corner with one request and one step of the room\'s undo, and draws the walls answered', async () => {
    roomApi.moveOutlineCorner.mockResolvedValue({
      rig_id: 7, room_shell: PULLED(), outline: PULLED().room!.outline!, box: false, changed: true, index: 2,
      undo: { available: 1, label: 'Walls: corner 3 moved' },
      outside: { items: [], fixtures: [], count: 0 },
      message: 'Walls: corner 3 moved. Nothing in the room or the rig is outside the walls.',
    });
    await editor(rigWith());
    await wallsMode();

    await dragCorner(2, [6, 5], [8, 5]);

    expect(roomApi.moveOutlineCorner).toHaveBeenCalledTimes(1);
    const [rigId, index, to] = roomApi.moveOutlineCorner.mock.calls[0];
    expect([rigId, index]).toEqual([7, 2]);
    expect(to.x).toBeCloseTo(8);
    expect(to.z).toBeCloseTo(5);
    // The plan draws the room as the server answered it, with no reload.
    expect(wallsDrawn()).toBe('0,0 12,0 14,10 0,10');
    expect(screen.getByTestId('room-plan-walls').getAttribute('data-outlined')).toBe('true');
    expect(handle(2).getAttribute('transform')).toBe('translate(14, 10)');
    expect(strip()!.textContent).toContain('Walls: corner 3 moved. Nothing in the room or the rig is outside the walls.');
    expect(screen.getByTestId('walls-mode-undo').textContent).toBe('Undo: Walls: corner 3 moved');
    expect(api.get).toHaveBeenCalledTimes(1);
    // No fixture was saved, and the editor's own undo has no step for a wall.
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
    expect(undoSteps()).toBe(0);
  });

  it('sends nothing for a press on a corner that stays within 5 pixels', async () => {
    await editor(rigWith());
    await wallsMode();
    const svg = planSvg();
    fireEvent.mouseDown(handle(2), inRoom(6, 5));
    fireEvent.mouseMove(svg, { clientX: 133, clientY: 112 });
    fireEvent.mouseUp(svg, { clientX: 133, clientY: 112 });
    await flush();
    expect(roomApi.moveOutlineCorner).not.toHaveBeenCalled();
    expect(wallsDrawn()).toBe(BOX_DRAWN);
  });

  it('lists what the new walls leave outside, and moves none of it', async () => {
    roomApi.moveOutlineCorner.mockResolvedValue({
      rig_id: 7, room_shell: PULLED(), outline: PULLED().room!.outline!, box: false, changed: true, index: 2,
      undo: { available: 1, label: 'Walls: corner 3 moved' },
      outside: {
        items: [{ kind: 'risers', index: 0, name: 'Stage', reason: 'partly outside the walls', already_outside: false }],
        fixtures: [{ rig_fixture_id: 2, name: 'Spot 2', reason: 'outside the walls', already_outside: false }],
        count: 2,
      },
      message: 'Walls: corner 3 moved. 2 things are now outside the walls or above the ceiling (2 of them since this change). Nothing was moved: check them.',
    });
    await editor(rigWith());
    const spotTwo = () => screen.getByText('Spot 2').parentElement!.getAttribute('transform');
    const before = spotTwo();
    await wallsMode();

    await dragCorner(2, [6, 5], [8, 5]);

    const listed = screen.getByTestId('walls-mode-outside').textContent;
    expect(listed).toContain('Stage (raised area) is partly outside the walls.');
    expect(listed).toContain('Spot 2 (fixture) is outside the walls.');
    expect(spotTwo()).toBe(before);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('puts a refused corner back and shows the server\'s words', async () => {
    roomApi.moveOutlineCorner.mockRejectedValue({
      isAxiosError: true,
      response: { status: 422, data: { detail: 'The walls would cross: the wall from corner 2 to corner 3 would meet the wall from corner 4 to corner 1.' } },
    });
    await editor(rigWith());
    await wallsMode();

    await dragCorner(2, [6, 5], [-5, -4]);

    expect(roomApi.moveOutlineCorner).toHaveBeenCalledTimes(1);
    expect(strip()!.textContent).toContain('The walls would cross: the wall from corner 2 to corner 3');
    expect(wallsDrawn()).toBe(BOX_DRAWN);
    expect(handle(2).getAttribute('transform')).toBe('translate(12, 10)');
  });

  it('takes the drag back with the room\'s Undo from the strip', async () => {
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Walls: corner 3 moved', room_shell: SHELL(), undo: { available: 0, label: null },
      outside: { items: [], fixtures: [], count: 0 },
      message: 'Undone: Walls: corner 3 moved. No fixture was moved.',
    });
    await editor(rigWith({ room_shell: PULLED(), room_shell_edits: { available: 1, label: 'Walls: corner 3 moved' } }));
    await wallsMode();
    expect(wallsDrawn()).toBe('0,0 12,0 14,10 0,10');

    fireEvent.click(screen.getByTestId('walls-mode-undo'));
    await flush();

    expect(roomApi.undoShellEdit).toHaveBeenCalledWith(7);
    expect(wallsDrawn()).toBe(BOX_DRAWN);
    expect(strip()!.textContent).toContain('Undone: Walls: corner 3 moved. No fixture was moved.');
    expect(screen.getByTestId('walls-mode-undo').textContent).toBe('Nothing to undo');
    expect(undoSteps()).toBe(0);
  });

  it('carries no fixture while the walls are being dragged, and carries them again when done', async () => {
    await editor(rigWith());
    await wallsMode();
    const svg = planSvg();
    const grab = () => screen.getByText('Spot 1').parentElement!;

    fireEvent.mouseDown(grab(), inRoom(-1, 0));
    fireEvent.mouseMove(svg, inRoom(-3, 0));
    fireEvent.mouseUp(svg, inRoom(-3, 0));
    await flush();
    expect(grab().getAttribute('transform')).toBe('translate(5, 5)');
    expect(undoSteps()).toBe(0);

    // By its words: the dialog that was put away may still be leaving the page.
    fireEvent.click(screen.getByText('Done with walls'));
    await flush();
    expect(handles()).toHaveLength(0);
    expect(strip()).toBeNull();

    fireEvent.mouseDown(grab(), inRoom(-1, 0));
    fireEvent.mouseMove(svg, inRoom(-3, 0));
    fireEvent.mouseUp(svg, inRoom(-3, 0));
    await flush();
    expect(grab().getAttribute('transform')).toBe('translate(3, 5)');
    expect(undoSteps()).toBe(1);
  });

  it('goes back to Edit Room from the strip', async () => {
    await editor(rigWith());
    await wallsMode();
    fireEvent.click(screen.getByText('Back to Edit Room'));
    await flush();
    expect(handles()).toHaveLength(0);
    expect(screen.getByLabelText('Across of corner 1')).toBeTruthy();
  });
});
