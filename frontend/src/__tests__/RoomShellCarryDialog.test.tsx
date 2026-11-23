// The Edit Room dialog and the fixtures hung on a truss: the "Move the
// fixtures hung on it" box on a line's and a ring's row, what it sends, the
// notice that says how many moved, and the word to the editor that the rig is
// to be read again. The API is a stand-in: nothing here reaches a backend.
// docs/ROOM_SCAN.md, slice 17.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';
import { carriedCount, carriedText, carriesFixtures, withCarry } from '../utils/roomShellEdit';
import type { CarriedFixture } from '../utils/roomShellEdit';

vi.mock('../services/api', () => ({
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage, a truss across the room and a ring.
const shell = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 }],
  truss_rings: [{ name: 'Ring 1', center_x: 3, center_z: 2, radius: 1.5, height: 4.2 }],
});

const carried = (id: number, x: number, toZ: number): CarriedFixture => ({
  rig_fixture_id: id,
  name: `Spot ${id}`,
  from: { x, y: 4.2, z: -2, rotation_y: 0 },
  to: { x, y: 4.2, z: toZ, rotation_y: 0 },
});

/** The dialog over a room and an undo count that each answer replaces, as the rig editor does it. */
function Harness({ edits, onChanged, onFixturesMoved }: {
  edits: RoomShellEdits | null;
  onChanged: (next: RoomShell, undo?: RoomShellEdits) => void;
  onFixturesMoved: () => void;
}) {
  const [stored, setStored] = useState<RoomShell | null>(shell());
  const [undo, setUndo] = useState<RoomShellEdits | null>(edits);
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
      onFixturesMoved={onFixturesMoved}
    />
  );
}

const open = (edits: RoomShellEdits | null = null) => {
  const onChanged = vi.fn();
  const onFixturesMoved = vi.fn();
  render(<Harness edits={edits} onChanged={onChanged} onFixturesMoved={onFixturesMoved} />);
  return { onChanged, onFixturesMoved };
};

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const box = (title: string) => screen.getByRole('checkbox', { name: `Move the fixtures hung on ${title}` }) as HTMLInputElement;
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;

const movedTruss = (): RoomShell => {
  const after = shell();
  after.truss_lines![0] = { ...after.truss_lines![0], z1: 1, z2: 1, suggested: false, basis: 'Moved by hand.' };
  return after;
};

describe('RoomShellEditDialog: fixtures follow their truss', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('has the box on a line and a ring, ticked, and a raised area\'s is worded for what stands on it', () => {
    open();
    expect(box('Truss 1').checked).toBe(true);
    expect(box('Ring 1').checked).toBe(true);
    // Nothing hangs on a stage: its box is slice 18's (RoomShellRaisedDialog.test.tsx).
    expect(screen.queryByRole('checkbox', { name: 'Move the fixtures hung on Stage' })).toBeNull();
    expect(screen.getAllByText('Move the fixtures hung on it')).toHaveLength(2);
    // The box is not a change to save.
    fireEvent.click(box('Truss 1'));
    expect(box('Truss 1').checked).toBe(false);
    expect(button('Save Truss 1').disabled).toBe(true);
  });

  it('moves a truss with its fixtures, says how many moved, and has the rig read again', async () => {
    const after = movedTruss();
    const undo = { available: 1, label: 'Truss 1 moved, with 2 fixtures' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: after, undo,
      carry_fixtures: true, fixtures_moved: [carried(1, -2, 1), carried(2, 2, 1)],
    });
    const { onChanged, onFixturesMoved } = open();

    type('Depth of Truss 1', '1');
    fireEvent.click(button('Save Truss 1'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { center_z: 1, carry_fixtures: true });
    expect(screen.getByText('Truss 1 was moved to 0, 1. 2 fixtures hung on it moved with it.')).toBeTruthy();
    // The room first, then the word that fixtures stand somewhere new.
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    expect(onChanged.mock.invocationCallOrder[0]).toBeLessThan(onFixturesMoved.mock.invocationCallOrder[0]);
    expect(undoButton().textContent).toBe('Undo: Truss 1 moved, with 2 fixtures');
    // The box is still ticked for the next change.
    expect(box('Truss 1').checked).toBe(true);
  });

  it('says one fixture in the singular', async () => {
    const after = shell();
    after.truss_rings![0] = { ...after.truss_rings![0], radius: 2 };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_rings', index: 0, item: {}, room_shell: after, fixtures_moved: [carried(5, 4.5, 2)],
    });
    const { onFixturesMoved } = open();

    type('Radius of Ring 1', '2');
    fireEvent.click(button('Save Ring 1'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_rings', 0, { radius: 2, carry_fixtures: true });
    expect(screen.getByText(
      'Ring 1 is now a ring 4.0 m across, underside 4.20 m up. 1 fixture hung on it moved with it.',
    )).toBeTruthy();
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
  });

  it('leaves the fixtures where they are with the box unticked, and does not have the rig read again', async () => {
    const after = movedTruss();
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: after, carry_fixtures: false, fixtures_moved: [],
    });
    const { onChanged, onFixturesMoved } = open();

    fireEvent.click(box('Truss 1'));
    type('Depth of Truss 1', '1');
    fireEvent.click(button('Save Truss 1'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { center_z: 1, carry_fixtures: false });
    expect(screen.getByText('Truss 1 was moved to 0, 1. The fixtures hung on it were left where they are.')).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(onFixturesMoved).not.toHaveBeenCalled();
    // Unticked is this row's alone, and it stays unticked until the dialog is opened again.
    expect(box('Truss 1').checked).toBe(false);
    expect(box('Ring 1').checked).toBe(true);
  });

  it('says no fixture moved when none hangs on it', async () => {
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: movedTruss(), carry_fixtures: true, fixtures_moved: [],
    });
    const { onFixturesMoved } = open();

    type('Depth of Truss 1', '1');
    fireEvent.click(button('Save Truss 1'));
    await flush();

    expect(screen.getByText('Truss 1 was moved to 0, 1. No fixture was moved with it.')).toBeTruthy();
    expect(onFixturesMoved).not.toHaveBeenCalled();
  });

  it('sends no flag with a rename, and sends it with a raised area\'s height', async () => {
    const renamed = shell();
    renamed.truss_lines![0].name = 'Front truss';
    api.editShellItem.mockResolvedValueOnce({ rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: renamed });
    const { onFixturesMoved } = open();

    type('Name of Truss 1', 'Front truss');
    fireEvent.click(button('Save Truss 1'));
    await flush();
    expect(api.editShellItem).toHaveBeenLastCalledWith(7, 'truss_lines', 0, { name: 'Front truss' });

    const raised = shell();
    raised.truss_lines![0].name = 'Front truss';
    raised.risers![0].height = 0.9;
    api.editShellItem.mockResolvedValueOnce({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: raised });
    type('Height of Stage', '0.9');
    fireEvent.click(button('Save Stage'));
    await flush();
    // Since slice 18 a raised area takes what stands on it. This answer lists none, so the rig is not read again.
    expect(api.editShellItem).toHaveBeenLastCalledWith(7, 'risers', 0, { height: 0.9, carry_fixtures: true });
    expect(onFixturesMoved).not.toHaveBeenCalled();
  });

  it('shows the server\'s words when the fixtures would be carried out of the room, and changes nothing', async () => {
    const detail = 'That would carry 2 fixtures hung on Truss 1 out of the room and the 2 m round it, or through the '
      + 'floor (Spot 3 to 8.5, 4.2, -2, Spot 4 to 10.5, 4.2, -2; across, height, depth in metres). Nothing was changed.';
    api.editShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail } } });
    const { onChanged, onFixturesMoved } = open();

    type('Across of Truss 1', '7.5');
    fireEvent.click(button('Save Truss 1'));
    await flush();

    expect(screen.getByText(detail)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    expect(onFixturesMoved).not.toHaveBeenCalled();
    // What was typed is still there, to be changed or sent again with the box unticked.
    expect(field('Across of Truss 1').value).toBe('7.5');
    expect(button('Save Truss 1').disabled).toBe(false);
  });

  it('has the rig read again when an undo puts the fixtures back, and not when it moved none', async () => {
    const message = 'Undone: Truss 1 moved, with 2 fixtures. 2 fixtures put back where they hung before it.';
    api.undoShellEdit.mockResolvedValueOnce({
      rig_id: 7, undone: 'Truss 1 moved, with 2 fixtures', room_shell: shell(),
      undo: { available: 1, label: 'Stage renamed' },
      fixtures_restored: [carried(1, -2, 1), carried(2, 2, 1)], fixtures_skipped: [], message,
    });
    const { onChanged, onFixturesMoved } = open({ available: 2, label: 'Truss 1 moved, with 2 fixtures' });
    expect(undoButton().textContent).toBe('Undo: Truss 1 moved, with 2 fixtures (1 more)');
    fireEvent.click(box('Ring 1'));

    fireEvent.click(undoButton());
    await flush();

    expect(screen.getByText(message)).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    // Rows may have changed places: every box is ticked again.
    expect(box('Ring 1').checked).toBe(true);

    api.undoShellEdit.mockResolvedValueOnce({
      rig_id: 7, undone: 'Stage renamed', room_shell: shell(), undo: { available: 0, label: null },
      fixtures_restored: [], fixtures_skipped: [], message: 'Undone: Stage renamed. No fixture was moved.',
    });
    fireEvent.click(undoButton());
    await flush();

    expect(screen.getByText('Undone: Stage renamed. No fixture was moved.')).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(2);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
  });
});

describe('roomShellEdit: the words and the flag', () => {
  it('knows which kinds carry fixtures', () => {
    expect(carriesFixtures('truss_lines')).toBe(true);
    expect(carriesFixtures('truss_rings')).toBe(true);
    // Since slice 18: the fixtures standing on a raised area go with it.
    expect(carriesFixtures('risers')).toBe(true);
  });

  it('adds the flag only to a change that could move a fixture', () => {
    expect(withCarry({ kind: 'truss_lines' }, { center_x: 1 }, true)).toEqual({ center_x: 1, carry_fixtures: true });
    expect(withCarry({ kind: 'truss_rings' }, { name: 'Halo', height: 4 }, false)).toEqual({
      name: 'Halo', height: 4, carry_fixtures: false,
    });
    expect(withCarry({ kind: 'truss_lines' }, { name: 'Front' }, true)).toEqual({ name: 'Front' });
    expect(withCarry({ kind: 'risers' }, { center_x: 1, width: 3 }, true)).toEqual({
      center_x: 1, width: 3, carry_fixtures: true,
    });
  });

  it('counts what an answer says moved, and says it', () => {
    expect(carriedCount([carried(1, 0, 1)])).toBe(1);
    expect(carriedCount(undefined)).toBe(0);
    expect(carriedCount('4')).toBe(0);
    expect(carriedText('truss_lines', { moved: 4, asked: true })).toBe('4 fixtures hung on it moved with it.');
    expect(carriedText('truss_rings', { moved: 1, asked: true })).toBe('1 fixture hung on it moved with it.');
    expect(carriedText('truss_lines', { moved: 0, asked: true })).toBe('No fixture was moved with it.');
    expect(carriedText('truss_lines', { moved: 0, asked: false })).toBe('The fixtures hung on it were left where they are.');
    // A raised area's fixtures stand on it.
    expect(carriedText('risers', { moved: 0, asked: false })).toBe('The fixtures standing on it were left where they are.');
    expect(carriedText('truss_lines')).toBe('No fixture was moved with it.');
  });
});
