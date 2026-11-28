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

  it('resizes a raised area from an edge handle and a corner handle, one request each, with the flag', async () => {
    const sized = (width: number, depth: number): RoomShell => {
      const next = SHELL();
      next.risers![0] = { ...next.risers![0], width, depth };
      return next;
    };
    roomApi.editShellItem.mockResolvedValueOnce({
      ...edited(sized(8, 3), 'Stage resized'), kind: 'risers', carry_fixtures: true,
    });
    await editor(rigAt(1, SHELL()));
    await arrange();
    // The stage is 6 m by 3 m about (0, -3.5): its stage left edge is at 3.
    pick('risers-0', [0, -3.5]);

    await drag(grip('e'), [3, -3.5], [4.1, -3.5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    // The width alone, about the middle: no centre is sent, and its fixtures are asked to go with it.
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'risers', 0, { width: 8, carry_fixtures: true });
    expect(shape('risers-0').getAttribute('width')).toBe('8');
    expect(grip('e').getAttribute('transform')).toBe('translate(10, 1.5)');
    expect(strip()!.textContent).toContain('Stage is now 8.0 m by 3.0 m');
    expect(screen.queryByTestId('room-item-readout')).toBeNull();

    roomApi.editShellItem.mockResolvedValueOnce({
      ...edited(sized(10, 4), 'Stage resized'), kind: 'risers', carry_fixtures: true,
    });
    // Now 8 m wide: its downstage stage left corner is at (4, -2).
    await drag(grip('se'), [4, -2], [5, -1.5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(2);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(
      7, 'risers', 0, { width: 10, depth: 4, carry_fixtures: true },
    );
    expect(shape('risers-0').getAttribute('height')).toBe('4');
  });

  it('leaves the fixtures where they are when a resized raised area\'s box is unticked', async () => {
    roomApi.editShellItem.mockResolvedValue({ ...edited(SHELL(), 'Stage resized'), kind: 'risers' });
    await editor(rigAt(1, SHELL()));
    await arrange(() => {
      fireEvent.click(screen.getByRole('checkbox', { name: 'Move the fixtures standing on Stage' }));
    });
    pick('risers-0', [0, -3.5]);

    await drag(grip('s'), [0, -2], [0, -1.5]);

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { depth: 4, carry_fixtures: false });
  });

  it('sends nothing for a press on a resize handle that stays within 5 pixels', async () => {
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);
    const svg = planSvg();
    // The east handle is at (100, 25) on screen.
    fireEvent.mouseDown(grip('e'), inRoom(3, -3.5));
    fireEvent.mouseMove(svg, { clientX: 103, clientY: 27 });
    fireEvent.mouseUp(svg, { clientX: 103, clientY: 27 });
    await flush();
    expect(roomApi.editShellItem).not.toHaveBeenCalled();
    expect(shape('risers-0').getAttribute('width')).toBe('6');
  });

  it('puts a refused resize back and shows the server\'s words (422, and 409 during a walkthrough)', async () => {
    const detail = 'That would carry 1 fixture standing on Stage out of the room and the 2 m round it, or through the '
      + 'floor (Par 3 to 9, 1.1, -4.2; across, height, depth in metres). Nothing was changed.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(422, detail));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);

    await drag(grip('e'), [3, -3.5], [6, -3.5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { width: 12, carry_fixtures: true });
    expect(strip()!.textContent).toContain(detail);
    // Back as the room has it, handles and all, and nothing read again.
    expect(shape('risers-0').getAttribute('width')).toBe('6');
    expect(shape('risers-0').getAttribute('x')).toBe('3');
    expect(grip('e').getAttribute('transform')).toBe('translate(9, 1.5)');
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
    expect(api.get).toHaveBeenCalledTimes(1);

    const running = 'The room cannot be edited while Identify Lights is running on this rig. Finish or end it first.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(409, running));
    await drag(grip('nw'), [-3, -5], [-4, -5.5]);
    expect(strip()!.textContent).toContain(running);
    expect(shape('risers-0').getAttribute('width')).toBe('6');
    expect(shape('risers-0').getAttribute('height')).toBe('3');
  });

  it('says that a riser standing on a moved stage went with it', async () => {
    const stacked = (stageZ: number): RoomShell => {
      const next = SHELL();
      next.risers![0] = { ...next.risers![0], center_z: stageZ };
      next.risers!.push({
        center_x: 1, center_z: stageZ, width: 2, depth: 2, height: 0.3, base_height: 0.6, name: 'Drum riser', kind: 'riser',
      });
      return next;
    };
    roomApi.editShellItem.mockResolvedValue({
      ...edited(stacked(-3), 'Stage moved, with 1 raised area'), kind: 'risers', carry_fixtures: true,
      items_moved: [{
        kind: 'risers', index: 1, name: 'Drum riser',
        from: { center_x: 1, center_z: -3.5, width: 2, depth: 2, base_height: 0.6 },
        to: { center_x: 1, center_z: -3, width: 2, depth: 2, base_height: 0.6 },
      }],
    });
    await editor(rigAt(1, stacked(-3.5)));
    await arrange();

    // Picked up by the stage where the riser does not cover it.
    await drag(shape('risers-0'), [-2, -3.5], [-2, -3]);

    // One request, for the stage: the server carries the riser, and the plan draws it where it went.
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { center_x: 0, center_z: -3, carry_fixtures: true });
    expect(shape('risers-1').getAttribute('y')).toBe('1');
    expect(strip()!.textContent).toContain(
      'Stage was moved to 0, -3. No fixture was moved with it. 1 raised area standing on it moved with it too.',
    );
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

  // Slice 21: a raised area's rotate handle. The stage is 6 m by 3 m about (0, -3.5), drawn about
  // (6, 1.5), and its rotate handle stands 0.6 m past its upstage edge, at (0, -5.6).
  const turnedTo = (heading: number): RoomShell => {
    const next = SHELL();
    next.risers![0] = { ...next.risers![0], heading_deg: heading };
    return next;
  };
  const handleAt = (name: string) =>
    grip(name).getAttribute('transform')!.match(/-?\d+(\.\d+)?/g)!.map(Number);

  it('turns a raised area from its rotate handle: one request with the heading and the flag', async () => {
    roomApi.editShellItem.mockResolvedValueOnce({
      ...edited(turnedTo(45), 'Stage turned'), kind: 'risers', carry_fixtures: true,
    });
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);

    // Up and stage left of its middle by as much: 45 degrees clockwise.
    await drag(grip('rotate'), [0, -5.6], [1.5, -5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 45, carry_fixtures: true });
    // Drawn as the room now has it, with its handle round with it and no readout left over.
    expect(shape('risers-0').getAttribute('transform')).toBe('rotate(45 6 1.5)');
    expect(handleAt('rotate')[0]).toBeGreaterThan(6);
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
    expect(strip()!.textContent).toContain(
      'Stage is now 6.0 m by 3.0 m, turned 45 degrees, top 0.60 m above the floor. No fixture was moved with it.',
    );
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('turns in steps of 15 degrees with Shift held', async () => {
    roomApi.editShellItem.mockResolvedValueOnce({
      ...edited(turnedTo(15), 'Stage turned'), kind: 'risers', carry_fixtures: true,
    });
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);
    const svg = planSvg();

    // 18.4 degrees clockwise of straight upstage: 20 on the grid's 5, 15 with Shift.
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -5.6));
    fireEvent.mouseMove(svg, { ...inRoom(0.5, -5), shiftKey: true });
    fireEvent.mouseUp(svg, { ...inRoom(0.5, -5), shiftKey: true });
    for (let turn = 0; turn < 4; turn += 1) await flush();

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 15, carry_fixtures: true });
    expect(shape('risers-0').getAttribute('transform')).toBe('rotate(15 6 1.5)');
  });

  it('leaves what stands on a turned raised area where it is when its box is unticked', async () => {
    roomApi.editShellItem.mockResolvedValue({ ...edited(turnedTo(45), 'Stage turned'), kind: 'risers' });
    await editor(rigAt(1, SHELL()));
    await arrange(() => {
      fireEvent.click(screen.getByRole('checkbox', { name: 'Move the fixtures standing on Stage' }));
    });
    pick('risers-0', [0, -3.5]);

    await drag(grip('rotate'), [0, -5.6], [1.5, -5]);

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 45, carry_fixtures: false });
    expect(strip()!.textContent).toContain('The fixtures standing on it were left where they are.');
  });

  it('reads the rig again when the fixtures standing on a turned raised area swung with it', async () => {
    roomApi.editShellItem.mockResolvedValueOnce({
      ...edited(turnedTo(45), 'Stage turned, with 2 fixtures', [1, 2]), kind: 'risers',
    });
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);

    await drag(grip('rotate'), [0, -5.6], [1.5, -5]);

    expect(strip()!.textContent).toContain('2 fixtures standing on it moved with it.');
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('puts a refused turn back and shows the server\'s words (422, and 409 during a walkthrough)', async () => {
    const detail = 'That would carry 1 fixture standing on Stage out of the room and the 2 m round it, or through the '
      + 'floor (Par 3 to 9, 1.1, -4.2; across, height, depth in metres). Nothing was changed.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(422, detail));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);

    await drag(grip('rotate'), [0, -5.6], [1.5, -5]);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 45, carry_fixtures: true });
    expect(strip()!.textContent).toContain(detail);
    // Square to the room again, its handle upstage of it, and nothing read again.
    expect(shape('risers-0').getAttribute('transform')).toBeNull();
    expect(handleAt('rotate')[0]).toBeCloseTo(6);
    expect(handleAt('rotate')[1]).toBeCloseTo(-0.6);
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
    expect(api.get).toHaveBeenCalledTimes(1);

    const running = 'The room cannot be edited while Identify Lights is running on this rig. Finish or end it first.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(409, running));
    await drag(grip('rotate'), [0, -5.6], [2, -3.5]);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'risers', 0, { heading_deg: 90, carry_fixtures: true });
    expect(strip()!.textContent).toContain(running);
    expect(shape('risers-0').getAttribute('transform')).toBeNull();
  });
});

// Slice 22: the height strip beside the plan. A handle dragged there is one
// PATCH with `height` or `base_height`, through what the plan's handles go
// through: the carry box, a refusal in the strip over the plan, the undo.
describe('RigBuilder: setting the heights of a scanned room\'s items by dragging', () => {
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

  /** The room with its truss hung at `trim`, its stage's deck `deck` high and its base `base` above the floor. */
  const raised = (trim = 4.2, deck = 0.6, base = 0): RoomShell => {
    const shell = SHELL();
    shell.truss_lines![0].height = trim;
    shell.risers![0].height = deck;
    if (base > 0) shell.risers![0].base_height = base;
    return shell;
  };

  const heightStrip = () => screen.queryByTestId('item-height-strip');
  const heightHandle = (name: string) => screen.getByTestId(`item-height-handle-${name}`);
  const heightAt = (name: string) => Number(heightHandle(name).getAttribute('data-value'));
  // The strip shows this 6 m room over 272 drawing units, and with no layout a unit is a pixel.
  const PX_PER_M = 272 / 6;

  /** A pointer event built by hand, as the strip's own tests build one. */
  function pointer(type: string, target: Element | Window, clientY: number, more: { shiftKey?: boolean } = {}) {
    const event = new MouseEvent(type, {
      bubbles: true, cancelable: true, clientX: 50, clientY, shiftKey: more.shiftKey ?? false,
    });
    Object.defineProperty(event, 'pointerType', { value: 'mouse' });
    Object.defineProperty(event, 'pointerId', { value: 1 });
    return fireEvent(target as Element, event);
  }

  /** Drags a height handle `metres` up (down for less than 0), lets go and waits for the answer. */
  async function lift(name: string, metres: number, more: { shiftKey?: boolean } = {}) {
    pointer('pointerdown', heightHandle(name), 200, more);
    pointer('pointermove', window, 200 - metres * PX_PER_M, more);
    pointer('pointerup', window, 200 - metres * PX_PER_M, more);
    for (let turn = 0; turn < 4; turn += 1) await flush();
  }

  it('has the strip beside the plan for the whole of the mode, with handles once an item is selected', async () => {
    await editor(rigAt(1, SHELL()));
    expect(heightStrip()).toBeNull();

    await arrange();
    // There before anything is selected, so the plan does not change size under a press.
    expect(heightStrip()).toBeTruthy();
    expect(screen.getByTestId('item-height-empty')).toBeTruthy();
    expect(strip()!.textContent).toContain('The strip beside the plan sets the selected item\'s height');

    pick('truss_lines-0', [0, 1]);
    expect(screen.getByTestId('item-height-title').textContent).toBe('Height: Truss 1');
    expect(heightAt('trim')).toBe(4.2);

    pick('risers-0', [0, -3.5]);
    expect(heightAt('top')).toBe(0.6);
    expect(heightAt('base')).toBe(0);
    expect(screen.queryByTestId('item-height-handle-trim')).toBeNull();

    // Found by its words, as the tests above find it: the dialog that was put away may still be leaving the page.
    fireEvent.click(screen.getByText('Done arranging'));
    await flush();
    expect(heightStrip()).toBeNull();
  });

  it('raises a truss with one request and one undo step, takes its fixtures up and reads the rig again', async () => {
    const after = raised(4.5);
    const label = 'Truss 1 resized, with 2 fixtures';
    roomApi.editShellItem.mockResolvedValue(edited(after, label, [1, 2]));
    await editor(rigAt(1, SHELL()), rigAt(1, after, { room_shell_edits: { available: 1, label } }));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    await lift('trim', 0.3);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { height: 4.5, carry_fixtures: true });
    // The strip draws the room that was answered, and the truss is still selected.
    expect(heightAt('trim')).toBe(4.5);
    expect(screen.getByTestId('room-item-truss_lines-0').getAttribute('data-selected')).toBe('true');
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(strip()!.textContent).toContain('underside 4.50 m up');
    expect(strip()!.textContent).toContain('2 fixtures hung on it moved with it.');
    expect(screen.getByTestId('items-mode-undo').textContent).toBe(`Undo: ${label}`);
    // The room's own step, not one of the editor's.
    expect(undoSteps()).toBe(0);
  });

  it('snaps to 0.25 m with Shift held', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(raised(4.5), 'Truss 1 resized'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    await lift('trim', 0.4, { shiftKey: true });

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { height: 4.5, carry_fixtures: true });
  });

  it('leaves the fixtures where they hang when the item\'s box is unticked', async () => {
    roomApi.editShellItem.mockResolvedValue(edited(raised(4.5), 'Truss 1 resized'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);
    fireEvent.click(screen.getByTestId('items-mode-selected').querySelector('input[type="checkbox"]')!);

    await lift('trim', 0.3);

    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { height: 4.5, carry_fixtures: false });
    expect(strip()!.textContent).toContain('The fixtures hung on it were left where they are.');
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('sets a raised area\'s deck from its top handle and floats it from its base handle, one request each', async () => {
    const answer = (shell: RoomShell, label: string) => ({ ...edited(shell, label), kind: 'risers' as const });
    roomApi.editShellItem.mockResolvedValueOnce(answer(raised(4.2, 1), 'Stage resized'));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('risers-0', [0, -3.5]);

    await lift('top', 0.4);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'risers', 0, { height: 1, carry_fixtures: true });
    expect(heightAt('top')).toBe(1);
    expect(strip()!.textContent).toContain('top 1.00 m above the floor');

    roomApi.editShellItem.mockResolvedValueOnce(answer(raised(4.2, 1, 2), 'Stage raised'));
    await lift('base', 2);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'risers', 0, { base_height: 2, carry_fixtures: true });
    expect(roomApi.editShellItem).toHaveBeenCalledTimes(2);
    expect(heightAt('base')).toBe(2);
    expect(heightAt('top')).toBe(3);
    expect(strip()!.textContent).toContain('floating 2.00 m above it');
  });

  it('sends nothing for a press on a height handle that stays within 5 pixels', async () => {
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    pointer('pointerdown', heightHandle('trim'), 200);
    pointer('pointermove', window, 197);
    pointer('pointerup', window, 197);
    await flush();

    expect(roomApi.editShellItem).not.toHaveBeenCalled();
    expect(heightAt('trim')).toBe(4.2);
  });

  it('puts a refused height back and shows the server\'s words (422, and 409 during a walkthrough)', async () => {
    const detail = 'That would carry 2 fixtures hung on Truss 1 out of the room and the 2 m round it, or through the '
      + 'floor (Spot 1 to -2, 8.5, 1; across, height, depth in metres). Nothing was changed.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(422, detail));
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);

    await lift('trim', 1.5);

    expect(roomApi.editShellItem).toHaveBeenCalledTimes(1);
    expect(roomApi.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { height: 5.7, carry_fixtures: true });
    expect(strip()!.textContent).toContain(detail);
    // Back where the room has it, and nothing read again.
    expect(heightAt('trim')).toBe(4.2);
    expect(screen.getByTestId('item-height-readout').textContent).toBe('Drag a handle up or down');
    expect(api.get).toHaveBeenCalledTimes(1);

    const running = 'The room cannot be edited while Identify Lights is running on this rig. Finish or end it first.';
    roomApi.editShellItem.mockRejectedValueOnce(refusal(409, running));
    await lift('trim', -1);
    expect(roomApi.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { height: 3.2, carry_fixtures: true });
    expect(strip()!.textContent).toContain(running);
    expect(heightAt('trim')).toBe(4.2);
  });

  it('takes a height back with the room\'s Undo from the strip over the plan', async () => {
    // The truss went up alone here, so the rig is not read again either way.
    const label = 'Truss 1 resized';
    roomApi.editShellItem.mockResolvedValue(edited(raised(4.5), label));
    roomApi.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: label, room_shell: SHELL(), undo: { available: 0, label: null },
      fixtures_restored: [], fixtures_skipped: [],
      message: `Undone: ${label}.`,
    });
    await editor(rigAt(1, SHELL()));
    await arrange();
    pick('truss_lines-0', [0, 1]);
    await lift('trim', 0.3);
    expect(heightAt('trim')).toBe(4.5);
    expect(screen.getByTestId('items-mode-undo').textContent).toBe(`Undo: ${label}`);

    fireEvent.click(screen.getByTestId('items-mode-undo'));
    for (let turn = 0; turn < 4; turn += 1) await flush();

    expect(roomApi.undoShellEdit).toHaveBeenCalledWith(7);
    expect(strip()!.textContent).toContain(`Undone: ${label}.`);
    expect(screen.getByTestId('items-mode-undo').textContent).toBe('Nothing to undo');
    // An undo lets go of the selection, so the strip has nothing to show; picked again, it is back at 4.2.
    expect(screen.getByTestId('item-height-empty')).toBeTruthy();
    pick('truss_lines-0', [0, 1]);
    expect(heightAt('trim')).toBe(4.2);
  });
});
