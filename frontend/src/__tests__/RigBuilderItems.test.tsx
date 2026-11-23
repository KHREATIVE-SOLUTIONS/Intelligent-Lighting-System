// The rig editor with Edit Room's "Arrange room items on the plan" in it:
// the dialog hands the room's items to the plan, a raised area, truss line
// or ring dragged there (or nudged with an arrow key) is one PATCH and one
// step of the room's own undo, its fixtures go with it as its box says, the
// rig is read again when they did, and a refused change goes back with the
// server's words. The panels round the plan are left out and the API is a
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

/**
 * A scanned box room 12 m by 10 m round a 10 m by 8 m stage: a stage
 * upstage, and 8 m of truss across the room at 4.2 m with its middle at
 * (`trussX`, `trussZ`).
 */
const SHELL = (trussX = 0, trussZ = 1, length = 8): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_lines: [{
    name: 'Truss 1', x1: trussX - length / 2, z1: trussZ, x2: trussX + length / 2, z2: trussZ, height: 4.2, across: 0.3,
  }],
});

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
async function editor(first: Rig, again: Rig = first) {
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

/** What the server answers a change to the truss with. */
const edited = (shell: RoomShell, label: string, carried: number[] = []) => ({
  rig_id: 7, kind: 'truss_lines' as const, index: 0, item: {}, room_shell: shell, changed: true,
  undo: { available: 1, label },
  carry_fixtures: carried.length > 0,
  fixtures_moved: carried.map((id) => ({
    rig_fixture_id: id, name: `Spot ${id}`,
    from: { x: 0, y: 4.2, z: 1, rotation_y: 0 }, to: { x: 0, y: 4.2, z: 3, rotation_y: 0 },
  })),
});

const refusal = (status: number, detail: string) => ({ isAxiosError: true, response: { status, data: { detail } } });

// The toolbar's button carries its tooltip as its label, so it is found by its words.
const editRoomButton = () => screen.queryByText('Edit Room')?.closest('button') ?? null;
const strip = () => screen.queryByTestId('items-mode');
const shape = (key: string) => screen.getByTestId(`room-item-shape-${key}`);
const grip = (name: string) => screen.getByTestId(`room-item-handle-${name}`);
const undoSteps = () => useRigEditorStore.getState().undoStack.length;
// A fixture at (x, z) in this room is drawn at (x + 6, z + 5).
const drawnAt = (name: string) => screen.getByText(name).parentElement!.getAttribute('transform');
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

/** Opens Edit Room and presses "Arrange room items on the plan". */
async function arrange(before: () => void = () => {}) {
  fireEvent.click(editRoomButton()!);
  await flush();
  before();
  fireEvent.click(screen.getByRole('button', { name: 'Arrange room items on the plan' }));
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

/** Drags what is under `from` to `to` and waits for the answer. */
async function drag(target: Element, from: [number, number], to: [number, number]) {
  const svg = planSvg();
  fireEvent.mouseDown(target, inRoom(...from));
  fireEvent.mouseMove(svg, inRoom(...to));
  fireEvent.mouseUp(svg, inRoom(...to));
  // The request is answered, the rig read again where it has to be, and the plan lets go of the drop.
  for (let turn = 0; turn < 4; turn += 1) await flush();
}

/** A press and release on an item: it is selected, and nothing is sent. */
function pick(key: string, where: [number, number]) {
  const svg = planSvg();
  fireEvent.mouseDown(shape(key), inRoom(...where));
  fireEvent.mouseUp(svg, inRoom(...where));
}

describe('RigBuilder: arranging the items of a scanned room on the plan', () => {
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

  it('has nothing to pick up until Edit Room hands the items to the plan', async () => {
    await editor(rigAt(1, SHELL()));
    expect(screen.queryByTestId('room-items')).toBeNull();
    expect(strip()).toBeNull();

    await arrange();

    expect(screen.getByTestId('room-item-risers-0')).toBeTruthy();
    expect(screen.getByTestId('room-item-truss_lines-0')).toBeTruthy();
    expect(strip()!.textContent).toContain('Arranging the room: drag a raised area, a truss line or a ring to move it');
    // Walls mode is not on with it.
    expect(screen.queryByTestId('wall-corners')).toBeNull();
    expect(screen.queryByTestId('walls-mode')).toBeNull();
  });

  it('moves a truss with one request and one undo step, takes its fixtures along and reads the rig again', async () => {
    const label = 'Truss 1 moved, with 2 fixtures';
    roomApi.editShellItem.mockResolvedValue(edited(SHELL(0, 3), label, [1, 2]));
    await editor(rigAt(1, SHELL()), rigAt(3, SHELL(0, 3), { room_shell_edits: { available: 1, label } }));
    expect(drawnAt('Spot 2')).toBe('translate(8, 6)');
    await arrange();

    await drag(shape('truss_lines-0'), [0, 1], [0, 3]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(
      7, 'truss_lines', 0, { center_x: 0, center_z: 3, carry_fixtures: true },
    );
    // The truss is drawn where the server put it, and the fixtures where it carried them.
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('8');
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(drawnAt('Spot 1')).toBe('translate(4, 8)');
    expect(drawnAt('Spot 2')).toBe('translate(8, 8)');
    expect(strip()!.textContent).toContain('Truss 1 was moved to 0, 3. 2 fixtures hung on it moved with it.');
    expect(screen.getByTestId('items-mode-undo').textContent).toBe(`Undo: ${label}`);
    // The room has the step; the editor's own undo has none, and nothing was saved through it.
    expect(undoSteps()).toBe(0);
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
  });

  it('moves a raised area the same way, and reads nothing again when no fixture stood on it', async () => {
    const moved = SHELL();
    moved.risers![0] = { ...moved.risers![0], center_x: 1.5, center_z: -2.5 };
    roomApi.editShellItem.mockResolvedValue({
      ...edited(moved, 'Stage moved'), kind: 'risers', carry_fixtures: true,
    });
    await editor(rigAt(1, SHELL()));
    await arrange();

    // Picked up half a metre off its middle, and dropped off the grid: it goes to the grid.
    await drag(shape('risers-0'), [0.5, -3.5], [2.1, -2.4]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(
      7, 'risers', 0, { center_x: 1.5, center_z: -2.5, carry_fixtures: true },
    );
    expect(shape('risers-0').getAttribute('x')).toBe('4.5');
    expect(strip()!.textContent).toContain('Stage was moved to 1.5, -2.5. No fixture was moved with it.');
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('sends nothing for a press on an item that stays within 5 pixels', async () => {
    await editor(rigAt(1, SHELL()));
    await arrange();
    const svg = planSvg();
    fireEvent.mouseDown(shape('truss_lines-0'), inRoom(0, 1));
    fireEvent.mouseMove(svg, { clientX: 73, clientY: 72 });
    fireEvent.mouseUp(svg, { clientX: 73, clientY: 72 });
    await flush();
    expect(roomApi.editShellItem).not.toHaveBeenCalled();
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('6');
    // The press selected it all the same.
    expect(screen.getByTestId('room-item-truss_lines-0').getAttribute('data-selected')).toBe('true');
  });

  it('leaves the fixtures behind when the item\'s box was unticked in the dialog', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(SHELL(0, 3), 'Truss 1 moved'));
    await editor(rigAt(1, SHELL()));
    await arrange(() => {
      fireEvent.click(screen.getByRole('checkbox', { name: 'Move the fixtures hung on Truss 1' }));
    });

    await drag(shape('truss_lines-0'), [0, 1], [0, 3]);

    expect(roomApi.editShellItem).toHaveBeenCalledWith(
      7, 'truss_lines', 0, { center_x: 0, center_z: 3, carry_fixtures: false },
    );
    expect(strip()!.textContent).toContain('The fixtures hung on it were left where they are.');
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(drawnAt('Spot 1')).toBe('translate(4, 6)');
  });

  it('has the selected item\'s box in the strip, ticked to start with, and goes by it', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(SHELL(0, 3), 'Truss 1 moved'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    expect(screen.queryByTestId('items-mode-selected')).toBeNull();

    pick('truss_lines-0', [0, 1]);
    // Found in the strip itself: the dialog that was put away may still be leaving the page.
    const box = screen.getByTestId('items-mode-selected').querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(box.getAttribute('aria-label')).toBe('Move the fixtures hung on Truss 1');
    expect(box.checked).toBe(true);
    expect(screen.getByTestId('items-mode-selected').textContent).toContain('Truss 1 is selected.');
    fireEvent.click(box);

    await drag(shape('truss_lines-0'), [0, 1], [0, 3]);

    expect(roomApi.editShellItem).toHaveBeenCalledWith(
      7, 'truss_lines', 0, { center_x: 0, center_z: 3, carry_fixtures: false },
    );
  });

  it('puts a refused move back and shows the server\'s words (422)', async () => {
    const detail = 'Truss 1 was not moved: it would carry Spot 2 out of the room, to 2.00, 9.00.';
    roomApi.editShellItem.mockRejectedValue(refusal(422, detail));
    await editor(rigAt(1, SHELL()));
    await arrange();

    await drag(shape('truss_lines-0'), [0, 1], [0, 4.5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(strip()!.textContent).toContain(detail);
    // Back where the room has it, and no fixture moved or read again.
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('6');
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
    expect(drawnAt('Spot 1')).toBe('translate(4, 6)');
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('puts a move back when a locate walkthrough is running (409)', async () => {
    const detail = 'The room cannot be edited while Identify Lights is running on this rig. Finish or end it first.';
    roomApi.editShellItem.mockRejectedValue(refusal(409, detail));
    await editor(rigAt(1, SHELL()));
    await arrange();

    await drag(shape('risers-0'), [0, -3.5], [2, -3.5]);

    expect(strip()!.textContent).toContain(detail);
    expect(shape('risers-0').getAttribute('x')).toBe('3');
  });

  it('sends one request for each arrow key press, each built on the one before it', async () => {
    const answers: Array<(value: unknown) => void> = [];
    roomApi.editShellItem.mockImplementation(() => new Promise((resolve) => { answers.push(resolve); }) as never);
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    // Two presses before the first is answered.
    press('ArrowRight');
    press('ArrowRight');
    await flush();
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { center_x: 0.5, carry_fixtures: true });

    await act(async () => { answers[0](edited(SHELL(0.5, 1), 'Truss 1 moved')); });
    await flush();
    // The second goes from where the first left the truss, not from where it was pressed.
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(2);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { center_x: 1, carry_fixtures: true });

    await act(async () => { answers[1](edited(SHELL(1, 1), 'Truss 1 moved')); });
    await flush();
    expect(shape('truss_lines-0').getAttribute('x1')).toBe('3');
    expect(strip()!.textContent).toContain('Truss 1 was moved to 1, 1.');
  });

  it('nudges ten steps with Shift, up the plan for upstage, and not at all for a key held down', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(SHELL(0, -4), 'Truss 1 moved'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    // With nothing selected an arrow key moves nothing.
    press('ArrowUp');
    await flush();
    expect(roomApi.editShellItem).not.toHaveBeenCalled();

    pick('truss_lines-0', [0, 1]);
    press('ArrowUp', { repeat: true });
    await flush();
    expect(roomApi.editShellItem).not.toHaveBeenCalled();

    press('ArrowUp', { shiftKey: true });
    await flush();
    await flush();
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { center_z: -4, carry_fixtures: true });
    // No fixture was nudged by the key: the plan's own keys are off here.
    expect(api.batchUpdateFixtures).not.toHaveBeenCalled();
  });

  it('changes a truss\'s length from its end handle and its heading from its rotate handle, one request each', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(SHELL(0, 1, 10), 'Truss 1 resized'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    await drag(grip('length'), [4, 1], [5, 1]);
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { length: 10, carry_fixtures: true });
    // The handle is on the end the server answered with.
    expect(grip('length').getAttribute('transform')).toBe('translate(11, 6)');

    // Now 10 m long: its rotate handle stands 0.6 m past the end at -5.
    await drag(grip('rotate'), [-5.6, 1], [0, -2]);
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(2);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { heading_deg: 90, carry_fixtures: true });
  });

  it('changes a ring\'s radius from its handle', async () => {
    const ringed = (radius: number): RoomShell => ({
      ...SHELL(), truss_rings: [{ name: 'Ring 1', center_x: 3, center_z: 3, radius, height: 4 }],
    });
    roomApi.editShellItem.mockResolvedValue({ ...edited(ringed(2), 'Ring 1 resized'), kind: 'truss_rings' });
    await editor(rigAt(1, ringed(1)));
    await arrange();
    pick('truss_rings-0', [4, 3]);

    await drag(grip('radius'), [4, 3], [5, 3]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_rings', 0, { radius: 2, carry_fixtures: true });
    expect(shape('truss_rings-0').getAttribute('r')).toBe('2');
  });

  it('takes the change back with the room\'s Undo from the strip, fixtures and all', async () => {
    const label = 'Truss 1 moved, with 2 fixtures';
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: label, room_shell: SHELL(), undo: { available: 0, label: null },
      fixtures_restored: [1, 2].map((id) => ({
        rig_fixture_id: id, name: `Spot ${id}`,
        from: { x: 0, y: 4.2, z: 3, rotation_y: 0 }, to: { x: 0, y: 4.2, z: 1, rotation_y: 0 },
      })),
      fixtures_skipped: [],
      message: `Undone: ${label}. 2 fixtures put back where they hung before it.`,
    });
    await editor(rigAt(3, SHELL(0, 3), { room_shell_edits: { available: 1, label } }), rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 3]);
    expect(screen.getByTestId('items-mode-undo').textContent).toBe(`Undo: ${label}`);

    fireEvent.click(screen.getByTestId('items-mode-undo'));
    await flush();
    await flush();

    expect(roomApi.undoShellEdit).toHaveBeenCalledWith(7);
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('6');
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(drawnAt('Spot 1')).toBe('translate(4, 6)');
    expect(strip()!.textContent).toContain('2 fixtures put back where they hung before it.');
    expect(screen.getByTestId('items-mode-undo').textContent).toBe('Nothing to undo');
    // An undo may change which item is which: the selection is let go.
    expect(screen.getByTestId('room-item-truss_lines-0').getAttribute('data-selected')).toBe('false');
  });

  it('carries no fixture while items are arranged, and carries them again when done', async () => {
    await editor(rigAt(1, SHELL()));
    await arrange();
    const svg = planSvg();
    const grab = () => screen.getByText('Spot 1').parentElement!;

    fireEvent.mouseDown(grab(), inRoom(-2, 1));
    fireEvent.mouseMove(svg, inRoom(-4, 3));
    fireEvent.mouseUp(svg, inRoom(-4, 3));
    await flush();
    expect(grab().getAttribute('transform')).toBe('translate(4, 6)');
    expect(undoSteps()).toBe(0);
    expect(roomApi.editShellItem).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('Done arranging'));
    await flush();
    expect(screen.queryByTestId('room-items')).toBeNull();
    expect(strip()).toBeNull();

    fireEvent.mouseDown(grab(), inRoom(-2, 1));
    fireEvent.mouseMove(svg, inRoom(-4, 3));
    fireEvent.mouseUp(svg, inRoom(-4, 3));
    await flush();
    expect(grab().getAttribute('transform')).toBe('translate(2, 8)');
    expect(undoSteps()).toBe(1);
  });

  it('goes back to Edit Room from the strip', async () => {
    await editor(rigAt(1, SHELL()));
    await arrange();
    fireEvent.click(screen.getByText('Back to Edit Room'));
    await flush();
    expect(screen.queryByTestId('room-items')).toBeNull();
    expect(screen.getByLabelText('Across of Truss 1')).toBeTruthy();
  });
});
