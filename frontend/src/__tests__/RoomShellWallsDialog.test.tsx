// The Edit Room dialog's Walls section: a row for each corner of the room's
// floor, a corner added or taken out, the room's height, the list of what the
// walls leave outside, and the button that hands the corners to the plan.
// The API is a stand-in: nothing here reaches a backend. docs/ROOM_SCAN.md.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';
import type { OutlineAnswer, OutsideReport } from '../utils/roomWallsEdit';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: {
    editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn(),
    getOutline: vi.fn(), setOutline: vi.fn(), moveOutlineCorner: vi.fn(), addOutlineCorner: vi.fn(),
    deleteOutlineCorner: vi.fn(),
  },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const NOTHING_OUTSIDE: OutsideReport = { items: [], fixtures: [], count: 0 };

// A 12 m by 10 m by 6 m box room with a stage and a ring.
const shell = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_rings: [{ name: 'Ring 1', center_x: 3, center_z: 2, radius: 1.5, height: 4.2 }],
});

const outlined = (outline: Array<{ x: number; z: number }>, more: Partial<NonNullable<RoomShell['room']>> = {}): RoomShell => ({
  ...shell(),
  room: { width: 12, depth: 10, height: 6, outline, ...more },
});

const answer = (room_shell: RoomShell, label: string, outside: OutsideReport = NOTHING_OUTSIDE): OutlineAnswer => ({
  rig_id: 7,
  room_shell,
  outline: room_shell.room?.outline ?? [],
  box: !room_shell.room?.outline,
  changed: true,
  undo: { available: 1, label },
  outside,
  message: `${label}. Nothing in the room or the rig is outside the walls.`,
});

/** The dialog over a room and an undo count that each answer replaces, as the rig editor does it. */
function Harness({ initial, onChanged, onDragWalls }: {
  initial: RoomShell | null;
  onChanged: (next: RoomShell, undo?: RoomShellEdits) => void;
  onDragWalls?: () => void;
}) {
  const [stored, setStored] = useState<RoomShell | null>(initial);
  const [undo, setUndo] = useState<RoomShellEdits | null>(null);
  return (
    <RoomShellEditDialog
      open
      rigId={7}
      rigName="Club"
      shell={stored}
      undo={undo}
      onClose={() => {}}
      onChanged={(next, after) => {
        setStored(next);
        if (after) setUndo(after);
        onChanged(next, after);
      }}
      onDragWalls={onDragWalls}
    />
  );
}

const open = async (initial: RoomShell | null = shell(), onDragWalls?: () => void) => {
  const onChanged = vi.fn();
  render(<Harness initial={initial} onChanged={onChanged} onDragWalls={onDragWalls} />);
  await flush();
  return onChanged;
};

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const corners = () => within(screen.getByTestId('room-shell-corners')).getAllByRole('row').length - 1;
const outsideList = () => screen.queryByTestId('room-shell-outside');

describe('RoomShellEditDialog: the walls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getOutline.mockResolvedValue({ rig_id: 7, outline: [], box: true, outside: NOTHING_OUTSIDE });
  });
  afterEach(cleanup);

  it('lists the four corners of a box room, its height, and nothing outside', async () => {
    await open();
    expect(corners()).toBe(4);
    expect([field('Across of corner 1').value, field('Depth of corner 1').value]).toEqual(['-6', '-5']);
    expect([field('Across of corner 3').value, field('Depth of corner 3').value]).toEqual(['6', '5']);
    expect(field('Height of the room').value).toBe('6');
    expect(screen.getByTestId('room-shell-walls').textContent)
      .toContain('4 corners, 12 m across and 10 m from upstage to downstage (a box)');
    expect(api.getOutline).toHaveBeenCalledWith(7);
    expect(outsideList()).toBeNull();
    // Nothing is typed yet: there is nothing to save.
    expect(button('Save corner 1').disabled).toBe(true);
    expect(button('Save the height of the room').disabled).toBe(true);
  });

  it('lists the corners of an outlined room in the order stored', async () => {
    await open(outlined([
      { x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 0 }, { x: 0, z: 0 }, { x: 0, z: 5 }, { x: -6, z: 5 },
    ]));
    expect(corners()).toBe(6);
    expect([field('Across of corner 4').value, field('Depth of corner 4').value]).toEqual(['0', '0']);
  });

  it('has no Walls section for a rig with no scanned room', async () => {
    await open(null);
    expect(screen.queryByTestId('room-shell-walls')).toBeNull();
    expect(api.getOutline).not.toHaveBeenCalled();
  });

  it('shows what is outside the walls when it is opened', async () => {
    api.getOutline.mockResolvedValue({
      rig_id: 7, outline: [], box: true,
      outside: {
        items: [{ kind: 'truss_rings', index: 0, name: 'Ring 1', reason: 'above the ceiling' }],
        fixtures: [{ rig_fixture_id: 4, name: 'Spot 4', reason: 'outside the walls' }],
        count: 2,
      },
    });
    await open();
    expect(outsideList()!.textContent).toContain('2 things are outside the walls or above the ceiling. None was moved:');
    expect(screen.getByText('Ring 1 (overhead ring) is above the ceiling.')).toBeTruthy();
    expect(screen.getByText('Spot 4 (fixture) is outside the walls.')).toBeTruthy();
  });

  it('moves a corner, sends only what changed, and lists what the new walls leave outside', async () => {
    const after = outlined([{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 2, z: 5 }, { x: -6, z: 5 }]);
    const outside: OutsideReport = {
      items: [{ kind: 'truss_rings', index: 0, name: 'Ring 1', reason: 'partly outside the walls', already_outside: false }],
      fixtures: [{ rig_fixture_id: 4, name: 'Spot 4', reason: 'outside the walls', already_outside: true }],
      count: 2,
    };
    api.moveOutlineCorner.mockResolvedValue({
      ...answer(after, 'Walls: corner 3 moved', outside),
      message: 'Walls: corner 3 moved. 2 things are now outside the walls or above the ceiling (1 of them since this change). Nothing was moved: check them.',
    });
    const onChanged = await open();

    type('Across of corner 3', '2');
    expect(button('Save corner 3').disabled).toBe(false);
    fireEvent.click(button('Save corner 3'));
    await flush();

    expect(api.moveOutlineCorner).toHaveBeenCalledTimes(1);
    expect(api.moveOutlineCorner).toHaveBeenCalledWith(7, 2, { x: 2 });
    expect(onChanged).toHaveBeenCalledWith(after, { available: 1, label: 'Walls: corner 3 moved' });
    expect(field('Across of corner 3').value).toBe('2');
    expect(screen.getByText(/^Walls: corner 3 moved\. 2 things are now outside/)).toBeTruthy();
    expect(screen.getByText('Ring 1 (overhead ring) is partly outside the walls.')).toBeTruthy();
    expect(screen.getByText('Spot 4 (fixture) is outside the walls (it was before this change).')).toBeTruthy();
    expect(screen.getByTestId('room-shell-undo').textContent).toBe('Undo: Walls: corner 3 moved');
    // No item of the room was edited on the way.
    expect(api.editShellItem).not.toHaveBeenCalled();
  });

  it('says why a corner cannot be saved, and does not send it', async () => {
    await open();
    type('Depth of corner 2', 'back');
    expect(screen.getByText('Depth must be a number of metres, such as -1.5.')).toBeTruthy();
    expect(button('Save corner 2').disabled).toBe(true);
    fireEvent.click(button('Save corner 2'));
    expect(api.moveOutlineCorner).not.toHaveBeenCalled();
  });

  it('shows the server\'s words for walls it refuses, and keeps what was typed', async () => {
    api.moveOutlineCorner.mockRejectedValue({
      isAxiosError: true,
      response: { status: 422, data: { detail: 'The walls would cross: the wall from corner 2 to corner 3 would meet the wall from corner 4 to corner 1. A room\'s walls cannot cross or touch each other.' } },
    });
    const onChanged = await open();
    type('Across of corner 3', '-9');
    type('Depth of corner 3', '-9');
    fireEvent.click(button('Save corner 3'));
    await flush();

    expect(api.moveOutlineCorner).toHaveBeenCalledWith(7, 2, { x: -9, z: -9 });
    expect(screen.getByText(/^The walls would cross: the wall from corner 2 to corner 3/)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    expect(field('Across of corner 3').value).toBe('-9');
  });

  it('adds a corner after one, and clears what was typed against the old places', async () => {
    const after = outlined([{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 6, z: 0 }, { x: 6, z: 5 }, { x: -6, z: 5 }]);
    api.addOutlineCorner.mockResolvedValue({ ...answer(after, 'Walls: corner added after corner 2'), index: 2 });
    await open();
    // Typed against corner 3, which is about to become corner 4.
    type('Across of corner 3', '9');

    fireEvent.click(button('Add a corner after corner 2'));
    await flush();

    expect(api.addOutlineCorner).toHaveBeenCalledWith(7, 1);
    expect(corners()).toBe(5);
    expect([field('Across of corner 3').value, field('Depth of corner 3').value]).toEqual(['6', '0']);
    expect([field('Across of corner 4').value, field('Depth of corner 4').value]).toEqual(['6', '5']);
  });

  it('deletes a corner, and not the third from last', async () => {
    const triangle = outlined([{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: -6, z: 5 }]);
    api.deleteOutlineCorner.mockResolvedValue({ ...answer(triangle, 'Walls: corner 3 deleted'), index: 2 });
    await open();
    expect(button('Delete corner 3').disabled).toBe(false);

    fireEvent.click(button('Delete corner 3'));
    await flush();

    expect(api.deleteOutlineCorner).toHaveBeenCalledWith(7, 2);
    expect(corners()).toBe(3);
    // A room keeps at least three corners.
    expect(button('Delete corner 1').disabled).toBe(true);
    expect(button('Delete corner 3').disabled).toBe(true);
  });

  it('sets the room height, and says what one must be', async () => {
    const after = shell();
    after.room!.height = 4;
    const outside: OutsideReport = {
      items: [{ kind: 'truss_rings', index: 0, name: 'Ring 1', reason: 'above the ceiling', already_outside: false }],
      fixtures: [],
      count: 1,
    };
    api.setOutline.mockResolvedValue(answer(after, 'Room height set to 4 m', outside));
    const onChanged = await open();

    type('Height of the room', '1');
    expect(screen.getByText("The room's height must be between 1.5 m and 30 m.")).toBeTruthy();
    expect(button('Save the height of the room').disabled).toBe(true);

    type('Height of the room', '4');
    fireEvent.click(button('Save the height of the room'));
    await flush();

    expect(api.setOutline).toHaveBeenCalledTimes(1);
    expect(api.setOutline).toHaveBeenCalledWith(7, { height: 4 });
    expect(onChanged).toHaveBeenCalledWith(after, { available: 1, label: 'Room height set to 4 m' });
    expect(field('Height of the room').value).toBe('4');
    expect(outsideList()!.textContent).toContain('1 thing is outside the walls or above the ceiling. It was not moved:');
    expect(screen.getByText('Ring 1 (overhead ring) is above the ceiling.')).toBeTruthy();
  });

  it('takes a change to the walls back with the room\'s Undo, and the list with it', async () => {
    const after = outlined([{ x: -6, z: -5 }, { x: 6, z: -5 }, { x: 2, z: 5 }, { x: -6, z: 5 }]);
    api.moveOutlineCorner.mockResolvedValue(answer(after, 'Walls: corner 3 moved', {
      items: [{ kind: 'truss_rings', index: 0, name: 'Ring 1', reason: 'partly outside the walls' }], fixtures: [], count: 1,
    }));
    api.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Walls: corner 3 moved', room_shell: shell(), undo: { available: 0, label: null },
      outside: NOTHING_OUTSIDE, message: 'Undone: Walls: corner 3 moved. No fixture was moved.',
    });
    await open();
    type('Across of corner 3', '2');
    fireEvent.click(button('Save corner 3'));
    await flush();
    expect(outsideList()).not.toBeNull();

    fireEvent.click(screen.getByTestId('room-shell-undo'));
    await flush();

    expect(api.undoShellEdit).toHaveBeenCalledWith(7);
    expect(field('Across of corner 3').value).toBe('6');
    expect(outsideList()).toBeNull();
    expect(screen.getByText('Undone: Walls: corner 3 moved. No fixture was moved.')).toBeTruthy();
  });

  it('hands the corners to the plan where the editor can take them, and has no button where it cannot', async () => {
    const onDragWalls = vi.fn();
    await open(shell(), onDragWalls);
    fireEvent.click(button('Drag corners on the plan'));
    expect(onDragWalls).toHaveBeenCalledTimes(1);
    cleanup();

    await open();
    expect(screen.queryByRole('button', { name: 'Drag corners on the plan' })).toBeNull();
  });

  it('works without the list when what is outside cannot be read', async () => {
    api.getOutline.mockRejectedValue(new Error('offline'));
    await open();
    expect(corners()).toBe(4);
    expect(outsideList()).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
