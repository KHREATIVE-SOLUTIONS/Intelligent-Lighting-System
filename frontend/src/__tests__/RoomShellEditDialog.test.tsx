// The Edit Room dialog: one row for each raised area, overhead line and ring
// of the stored room, saved or deleted one at a time. The API is a stand-in:
// nothing here reaches a backend. docs/ROOM_SCAN.md.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell } from '../types';

vi.mock('../services/api', () => ({
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage, a truss across the room, a stub too short to draw, an angled truss and a ring.
const shell = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_lines: [
    { name: 'Overhead line 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 },
    { name: 'Stub', x1: 0, z1: 0, x2: 0.1, z2: 0, height: 4.2 },
    { name: 'Overhead line 3', x1: -3, z1: 1, x2: 1, z2: 4, height: 4.25 },
  ],
  truss_rings: [{ name: 'Overhead ring 1', center_x: 3, center_z: 2, radius: 1.5, height: 4.2 }],
});

/** The dialog over a room that is replaced by each answer, as the rig editor does it. */
function Harness({ initial, onChanged }: { initial: RoomShell | null; onChanged: (next: RoomShell) => void }) {
  const [stored, setStored] = useState<RoomShell | null>(initial);
  return (
    <RoomShellEditDialog
      open
      rigId={7}
      rigName="Club"
      shell={stored}
      onClose={() => {}}
      onChanged={(next) => {
        setStored(next);
        onChanged(next);
      }}
    />
  );
}

const open = (initial: RoomShell | null = shell()) => {
  const onChanged = vi.fn();
  render(<Harness initial={initial} onChanged={onChanged} />);
  return onChanged;
};

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });

describe('RoomShellEditDialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('lists every stored item with its name and where its middle is', () => {
    open();
    expect(screen.getByText('Edit the room of Club')).toBeTruthy();
    for (const key of ['risers:0', 'truss_lines:0', 'truss_lines:1', 'truss_lines:2', 'truss_rings:0']) {
      expect(screen.getByTestId(`room-shell-item-${key}`)).toBeTruthy();
    }
    expect(field('Name of Stage').value).toBe('Stage');
    expect(field('Across of Stage').value).toBe('0');
    expect(field('Depth of Stage').value).toBe('-3.5');
    // A line's middle, half way between its ends.
    expect(field('Across of Overhead line 3').value).toBe('-1');
    expect(field('Depth of Overhead line 3').value).toBe('2.5');
    expect(screen.getByText('6.0 m by 3.0 m, top 0.60 m above the floor')).toBeTruthy();
    // The stub is not drawn in either view, and is listed all the same.
    expect(screen.getByText(/^Not drawn: its ends or its height are missing/)).toBeTruthy();
  });

  it('has nothing to save until a row is changed', () => {
    open();
    expect(button('Save Stage').disabled).toBe(true);
    type('Name of Stage', 'Main stage');
    expect(button('Save Stage').disabled).toBe(false);
    // The other rows are as they were.
    expect(button('Save Overhead line 1').disabled).toBe(true);
    type('Name of Stage', 'Stage');
    expect(button('Save Stage').disabled).toBe(true);
  });

  it('renames an item and hands the stored room on', async () => {
    const after = shell();
    after.risers![0].name = 'Main stage';
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after });
    const onChanged = open();

    type('Name of Stage', '  Main stage ');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { name: 'Main stage' });
    expect(onChanged.mock.calls[0][0]).toBe(after);
    expect(screen.getByText('Stage is now called Main stage.')).toBeTruthy();
    // The row shows what is stored, and has nothing more to save.
    expect(field('Name of Main stage').value).toBe('Main stage');
    expect(button('Save Main stage').disabled).toBe(true);
  });

  it('moves an item by its place in the stored list, not its place on the plan', async () => {
    const after = shell();
    after.truss_lines![2] = { ...after.truss_lines![2], x1: 0, x2: 4, suggested: false };
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'truss_lines', index: 2, item: {}, room_shell: after });
    const onChanged = open();

    type('Across of Overhead line 3', '2');
    fireEvent.click(button('Save Overhead line 3'));
    await flush();

    // The third stored line, though the plan draws it second: the stub is left out there.
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 2, { center_x: 2 });
    expect(onChanged.mock.calls[0][0]).toBe(after);
    expect(screen.getByText('Overhead line 3 was moved to 2, 2.5. No fixture was moved with it.')).toBeTruthy();
    expect(field('Across of Overhead line 3').value).toBe('2');
    expect(screen.getByText('Moved by hand')).toBeTruthy();
  });

  it('says what is wrong with a field and sends nothing', () => {
    open();
    type('Depth of Stage', 'upstage');
    expect(screen.getByText('Depth must be a number of metres, such as -1.5.')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    type('Depth of Stage', '-3.5');
    type('Name of Stage', '  ');
    expect(screen.getByText('A name needs at least one letter or number.')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    expect(api.editShellItem).not.toHaveBeenCalled();
  });

  it('keeps what is typed in another row when one row is saved', async () => {
    const after = shell();
    after.risers![0].name = 'Main stage';
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after });
    open();

    type('Name of Overhead ring 1', 'Centre ring');
    type('Name of Stage', 'Main stage');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(field('Name of Overhead ring 1').value).toBe('Centre ring');
    expect(button('Save Overhead ring 1').disabled).toBe(false);
  });

  it('asks before it deletes anything', () => {
    open();
    fireEvent.click(button('Delete Overhead line 1'));
    expect(api.deleteShellItem).not.toHaveBeenCalled();
    expect(screen.getByText(/^Take Overhead line 1 out of the stored room\?/)).toBeTruthy();
    // Keeping it takes the question away again, still without a request.
    fireEvent.click(button('Keep it'));
    expect(screen.queryByText(/^Take Overhead line 1 out of the stored room\?/)).toBeNull();
    expect(api.deleteShellItem).not.toHaveBeenCalled();
  });

  it('deletes an item and lists what is left', async () => {
    const after = shell();
    after.truss_lines = after.truss_lines!.slice(1);
    api.deleteShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, removed: {}, room_shell: after,
      message: 'Overhead line 1 was taken out of the stored room. No fixture was moved.',
    });
    const onChanged = open();

    fireEvent.click(button('Delete Overhead line 1'));
    fireEvent.click(button('Delete it'));
    await flush();

    expect(api.deleteShellItem).toHaveBeenCalledTimes(1);
    expect(api.deleteShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0);
    expect(onChanged.mock.calls[0][0]).toBe(after);
    expect(screen.getByText('Overhead line 1 was taken out of the stored room. No fixture was moved.')).toBeTruthy();
    expect(screen.queryByLabelText('Name of Overhead line 1')).toBeNull();
    // The lines after it have each moved up a place.
    expect(screen.queryByTestId('room-shell-item-truss_lines:2')).toBeNull();
    expect(field('Name of Overhead line 3').closest('tr')?.getAttribute('data-testid')).toBe(
      'room-shell-item-truss_lines:1',
    );
  });

  it('says why a change was refused and changes nothing', async () => {
    api.editShellItem.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { detail: 'The stored room has no raised area number 1 (it has 0).' } },
    });
    const onChanged = open();

    type('Name of Stage', 'Main stage');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByText('The stored room has no raised area number 1 (it has 0).')).toBeTruthy();
    // What was typed is still there to send again.
    expect(field('Name of Stage').value).toBe('Main stage');
    expect(button('Save Stage').disabled).toBe(false);
  });

  it('says so when there is nothing to edit', () => {
    open({ source: 'scan', room: { width: 12, depth: 10, height: 6 } });
    expect(screen.getByText(/no stage, riser, booth, truss or ring left in it/)).toBeTruthy();
    cleanup();
    open(null);
    expect(screen.getByText(/no scanned room stored/)).toBeTruthy();
  });

  it('draws nothing while it is closed', () => {
    render(
      <RoomShellEditDialog open={false} rigId={7} rigName="Club" shell={shell()} onClose={() => {}} onChanged={() => {}} />,
    );
    expect(screen.queryByText('Edit the room of Club')).toBeNull();
  });
});
