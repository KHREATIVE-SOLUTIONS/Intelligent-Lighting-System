// The Edit Room dialog beyond a rename and a move: a row's size, height and
// heading, a quarter turn, the form that adds what the scan missed, and Undo.
// The API is a stand-in: nothing here reaches a backend. docs/ROOM_SCAN.md.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';

vi.mock('../services/api', () => ({
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage, a truss across the room, an angled truss and a ring.
const shell = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [{ center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' }],
  truss_lines: [
    { name: 'Overhead line 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 },
    { name: 'Overhead line 2', x1: -3, z1: 1, x2: 1, z2: 4, height: 4.25 },
  ],
  truss_rings: [{ name: 'Overhead ring 1', center_x: 3, center_z: 2, radius: 1.5, height: 4.2 }],
});

/** The dialog over a room and an undo count that each answer replaces, as the rig editor does it. */
function Harness({ initial, edits, onChanged }: {
  initial: RoomShell | null;
  edits: RoomShellEdits | null;
  onChanged: (next: RoomShell, undo?: RoomShellEdits) => void;
}) {
  const [stored, setStored] = useState<RoomShell | null>(initial);
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
    />
  );
}

const open = (initial: RoomShell | null = shell(), edits: RoomShellEdits | null = null) => {
  const onChanged = vi.fn();
  render(<Harness initial={initial} edits={edits} onChanged={onChanged} />);
  return onChanged;
};

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;
const whatToAdd = () => screen.getByRole('combobox', { name: 'What to add' }) as HTMLSelectElement;

describe('RoomShellEditDialog: size, height and heading', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('shows each row its own sizes and its height', () => {
    open();
    expect(field('Width of Stage').value).toBe('6');
    expect(field('Front to back of Stage').value).toBe('3');
    expect(field('Height of Stage').value).toBe('0.6');
    expect(field('Length of Overhead line 1').value).toBe('8');
    expect(field('Heading of Overhead line 1').value).toBe('0');
    // A line's length and heading are what its two ends say: 3-4-5.
    expect(field('Length of Overhead line 2').value).toBe('5');
    expect(field('Heading of Overhead line 2').value).toBe('36.9');
    expect(field('Height of Overhead line 2').value).toBe('4.25');
    expect(field('Radius of Overhead ring 1').value).toBe('1.5');
    expect(field('Height of Overhead ring 1').value).toBe('4.2');
    // A ring has no heading, and a stage no radius.
    expect(screen.queryByLabelText('Heading of Overhead ring 1')).toBeNull();
    expect(screen.queryByLabelText('Radius of Stage')).toBeNull();
  });

  it('resizes a raised area and sends only the size that changed', async () => {
    const after = shell();
    after.risers![0] = { ...after.risers![0], width: 8, suggested: false, basis: 'scan: a level area. Resized by hand.' };
    const undo = { available: 1, label: 'Stage resized' };
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo });
    const onChanged = open();
    expect(button('Save Stage').disabled).toBe(true);

    type('Width of Stage', '8');
    expect(button('Save Stage').disabled).toBe(false);
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { width: 8 });
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(screen.getByText(
      'Stage is now 8.0 m by 3.0 m, top 0.60 m above the floor. No fixture was moved with it.',
    )).toBeTruthy();
    expect(field('Width of Stage').value).toBe('8');
    expect(screen.getByText('Resized by hand')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    // The change can be taken back.
    expect(undoButton().textContent).toBe('Undo: Stage resized');
    expect(undoButton().disabled).toBe(false);
  });

  it('turns a line, makes it shorter and lowers it in one save', async () => {
    const after = shell();
    after.truss_lines![0] = { ...after.truss_lines![0], x1: 0, z1: -5, x2: 0, z2: 1, height: 3.5 };
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'truss_lines', index: 0, item: {}, room_shell: after });
    open();

    type('Length of Overhead line 1', '6');
    type('Heading of Overhead line 1', '90');
    type('Height of Overhead line 1', '3,5');
    fireEvent.click(button('Save Overhead line 1'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_lines', 0, { length: 6, heading_deg: 90, height: 3.5 });
    expect(screen.getByText(
      'Overhead line 1 is now 6.0 m long, underside 3.50 m up, running upstage to downstage. '
      + 'No fixture was moved with it.',
    )).toBeTruthy();
    expect(field('Heading of Overhead line 1').value).toBe('90');
    expect(field('Height of Overhead line 1').value).toBe('3.5');
  });

  it('gives a ring a new radius', async () => {
    const after = shell();
    after.truss_rings![0].radius = 2;
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'truss_rings', index: 0, item: {}, room_shell: after });
    open();

    type('Radius of Overhead ring 1', '2');
    fireEvent.click(button('Save Overhead ring 1'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'truss_rings', 0, { radius: 2 });
  });

  it('turns a raised area a quarter turn by swapping its sides', async () => {
    const after = shell();
    after.risers![0] = { ...after.risers![0], width: 3, depth: 6 };
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after });
    open();

    fireEvent.click(button('Turn Stage a quarter turn'));
    // Nothing is sent by the turn itself: it is typed into the row, to be saved or not.
    expect(api.editShellItem).not.toHaveBeenCalled();
    expect(field('Width of Stage').value).toBe('3');
    expect(field('Front to back of Stage').value).toBe('6');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { width: 3, depth: 6 });
  });

  it('has no turn for a line or a ring, which have a heading or need none', () => {
    open();
    expect(screen.queryByRole('button', { name: 'Turn Overhead line 1 a quarter turn' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Turn Overhead ring 1 a quarter turn' })).toBeNull();
  });

  it('says what is wrong with a size and sends nothing', () => {
    open();
    type('Radius of Overhead ring 1', '0.1');
    expect(screen.getByText('Radius must be at least 0.3 m.')).toBeTruthy();
    expect(button('Save Overhead ring 1').disabled).toBe(true);
    type('Radius of Overhead ring 1', '1.5');
    type('Height of Stage', '3.5');
    expect(screen.getByText('Height of a raised area can be at most 3 m.')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    type('Height of Stage', '0.6');
    type('Heading of Overhead line 1', 'north');
    expect(screen.getByText('Heading must be a number of degrees, such as 45 or -30.')).toBeTruthy();
    expect(api.editShellItem).not.toHaveBeenCalled();
  });

  it('uses the server\'s words when a size does not fit the room', async () => {
    const words = 'That would make the raised area 16.5 m across, and the room and the 2 m round it have room for 16 m.';
    api.editShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail: words } } });
    const onChanged = open();

    type('Width of Stage', '16.5');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(words)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    // What was typed is still there to correct.
    expect(field('Width of Stage').value).toBe('16.5');
  });

  it('marks what was added by hand', () => {
    const added = shell();
    added.truss_rings!.push({
      name: 'Halo', center_x: 0, center_z: 0, radius: 1, height: 4, suggested: false, added_by_hand: true,
      basis: 'Added by hand.',
    });
    open(added);
    const row = field('Name of Halo').closest('tr')!;
    expect(row.textContent).toContain('Added by hand');
    // What the scan found carries no such mark.
    expect(field('Name of Stage').closest('tr')!.textContent).not.toContain('by hand');
  });
});

describe('RoomShellEditDialog: adding an item', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('offers the five things a scan can miss, starting at a riser', () => {
    open();
    expect(Array.from(whatToAdd().options).map((option) => option.value)).toEqual([
      'stage', 'riser', 'booth', 'truss_line', 'truss_ring',
    ]);
    expect(whatToAdd().value).toBe('riser');
    expect(field('Width of the new item').value).toBe('2');
    expect(field('Front to back of the new item').value).toBe('2');
    expect(field('Height of the new item').value).toBe('0.3');
    expect(field('Across of the new item').value).toBe('0');
    expect(field('Depth of the new item').value).toBe('0');
    expect(screen.queryByLabelText('Radius of the new item')).toBeNull();
  });

  it('shows the sizes of the kind chosen and keeps the name and the place typed', () => {
    open();
    type('Name of the new item', 'Halo');
    type('Across of the new item', '1.5');
    fireEvent.change(whatToAdd(), { target: { value: 'truss_ring' } });

    expect(field('Radius of the new item').value).toBe('1.5');
    expect(field('Height of the new item').value).toBe('4');
    expect(screen.queryByLabelText('Width of the new item')).toBeNull();
    expect(field('Name of the new item').value).toBe('Halo');
    expect(field('Across of the new item').value).toBe('1.5');

    fireEvent.change(whatToAdd(), { target: { value: 'truss_line' } });
    expect(field('Length of the new item').value).toBe('6');
    expect(field('Heading of the new item').value).toBe('0');
    expect(screen.queryByLabelText('Radius of the new item')).toBeNull();
  });

  it('adds a ring and lists it, marked as added by hand', async () => {
    const after = shell();
    after.truss_rings!.push({
      name: 'Halo', center_x: 1.5, center_z: -1, radius: 2, height: 4, suggested: false, added_by_hand: true,
      basis: 'Added by hand.',
    });
    const undo = { available: 1, label: 'Halo added' };
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_rings', index: 1, item: {}, room_shell: after, undo,
      message: 'Halo was added to the stored room as a overhead ring. No fixture was moved.',
    });
    const onChanged = open();

    fireEvent.change(whatToAdd(), { target: { value: 'truss_ring' } });
    type('Name of the new item', ' Halo ');
    type('Across of the new item', '1.5');
    type('Depth of the new item', '-1');
    type('Radius of the new item', '2');
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(api.addShellItem).toHaveBeenCalledTimes(1);
    expect(api.addShellItem).toHaveBeenCalledWith(7, 'truss_rings', {
      name: 'Halo', center_x: 1.5, center_z: -1, radius: 2, height: 4,
    });
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(screen.getByText('Halo was added to the stored room as a overhead ring. No fixture was moved.')).toBeTruthy();
    // It is a row like any other, at the end of its list.
    const row = field('Name of Halo').closest('tr')!;
    expect(row.getAttribute('data-testid')).toBe('room-shell-item-truss_rings:1');
    expect(row.textContent).toContain('Added by hand');
    expect(field('Radius of Halo').value).toBe('2');
    // The form is ready for another of the same kind, at its usual size.
    expect(whatToAdd().value).toBe('truss_ring');
    expect(field('Name of the new item').value).toBe('');
    expect(field('Radius of the new item').value).toBe('1.5');
    expect(undoButton().textContent).toBe('Undo: Halo added');
  });

  it('adds a stage with what it is, and no name when none is typed', async () => {
    const after = shell();
    after.risers!.push({ center_x: 0, center_z: 0, width: 4, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' });
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 1, item: {}, room_shell: after, message: 'Stage was added.',
    });
    open();

    fireEvent.change(whatToAdd(), { target: { value: 'stage' } });
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(api.addShellItem).toHaveBeenCalledWith(7, 'risers', {
      center_x: 0, center_z: 0, width: 4, depth: 3, height: 0.6, riser_kind: 'stage',
    });
  });

  it('keeps what is typed in a row when something is added', async () => {
    const after = shell();
    after.risers!.push({ center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, name: 'Riser', kind: 'riser' });
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 1, item: {}, room_shell: after, message: 'Riser was added.',
    });
    open();

    type('Name of Stage', 'Main stage');
    fireEvent.click(button('Add to the room'));
    await flush();

    // It went at the end of its list: the stage's row is where it was.
    expect(field('Name of Stage').value).toBe('Main stage');
    expect(button('Save Stage').disabled).toBe(false);
  });

  it('says what is wrong with the form and sends nothing', () => {
    open();
    type('Across of the new item', 'left');
    expect(screen.getByText('Across must be a number of metres, such as -1.5.')).toBeTruthy();
    expect(button('Add to the room').disabled).toBe(true);
    type('Across of the new item', '0');
    type('Width of the new item', '0.1');
    expect(screen.getByText('Width must be at least 0.3 m.')).toBeTruthy();
    expect(button('Add to the room').disabled).toBe(true);
    type('Width of the new item', '2');
    expect(button('Add to the room').disabled).toBe(false);
    expect(api.addShellItem).not.toHaveBeenCalled();
  });

  it('says why an item was refused and keeps the form as typed', async () => {
    const words = 'The height of a overhead line must be between 0.5 m and 6 m; 7 m is not.';
    api.addShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail: words } } });
    const onChanged = open();

    fireEvent.change(whatToAdd(), { target: { value: 'truss_line' } });
    type('Height of the new item', '7');
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(screen.getByText(words)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    expect(field('Height of the new item').value).toBe('7');
  });

  it('can add to a room the scan found nothing in, and not to a rig with no scanned room', () => {
    open({ source: 'scan', room: { width: 12, depth: 10, height: 6 } });
    expect(screen.getByTestId('room-shell-add')).toBeTruthy();
    expect(button('Add to the room').disabled).toBe(false);
    cleanup();
    open(null);
    expect(screen.queryByTestId('room-shell-add')).toBeNull();
    expect(screen.queryByTestId('room-shell-undo')).toBeNull();
  });
});

describe('RoomShellEditDialog: undo', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('has nothing to undo for a room nobody has edited', () => {
    open();
    expect(undoButton().textContent).toBe('Nothing to undo');
    expect(undoButton().disabled).toBe(true);
  });

  it('says what the next undo takes back when the dialog opens, as the rig has it', () => {
    // The steps are kept on the server: they are there after the page is loaded again.
    open(shell(), { available: 3, label: 'Overhead line 3 deleted' });
    expect(undoButton().textContent).toBe('Undo: Overhead line 3 deleted (2 more)');
    expect(undoButton().disabled).toBe(false);
  });

  it('takes back one edit for each press and shows the room as it was', async () => {
    // The room as it is: the stage renamed, then the first truss deleted.
    const now = shell();
    now.risers![0].name = 'Main stage';
    now.truss_lines = now.truss_lines!.slice(1);
    const renamed = shell();
    renamed.risers![0].name = 'Main stage';
    api.undoShellEdit
      .mockResolvedValueOnce({
        rig_id: 7, undone: 'Overhead line 1 deleted', room_shell: renamed,
        undo: { available: 1, label: 'Stage renamed' },
        message: 'Undone: Overhead line 1 deleted. No fixture was moved.',
      })
      .mockResolvedValueOnce({
        rig_id: 7, undone: 'Stage renamed', room_shell: shell(),
        undo: { available: 0, label: null },
        message: 'Undone: Stage renamed. No fixture was moved.',
      });
    const onChanged = open(now, { available: 2, label: 'Overhead line 1 deleted' });
    expect(screen.queryByLabelText('Name of Overhead line 1')).toBeNull();
    expect(undoButton().textContent).toBe('Undo: Overhead line 1 deleted (1 more)');

    fireEvent.click(undoButton());
    await flush();

    expect(api.undoShellEdit).toHaveBeenCalledTimes(1);
    expect(api.undoShellEdit).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenLastCalledWith(renamed, { available: 1, label: 'Stage renamed' });
    expect(screen.getByText('Undone: Overhead line 1 deleted. No fixture was moved.')).toBeTruthy();
    // The deleted truss is back in its old place, and the truss after it is second again.
    expect(field('Name of Overhead line 1').closest('tr')?.getAttribute('data-testid')).toBe(
      'room-shell-item-truss_lines:0',
    );
    expect(field('Name of Overhead line 2').closest('tr')?.getAttribute('data-testid')).toBe(
      'room-shell-item-truss_lines:1',
    );
    expect(undoButton().textContent).toBe('Undo: Stage renamed');

    fireEvent.click(undoButton());
    await flush();

    expect(api.undoShellEdit).toHaveBeenCalledTimes(2);
    expect(field('Name of Stage').value).toBe('Stage');
    expect(screen.getByText('Undone: Stage renamed. No fixture was moved.')).toBeTruthy();
    expect(undoButton().textContent).toBe('Nothing to undo');
    expect(undoButton().disabled).toBe(true);
    // An undo edits nothing itself.
    expect(api.editShellItem).not.toHaveBeenCalled();
    expect(api.deleteShellItem).not.toHaveBeenCalled();
  });

  it('clears what was typed, because the rows may have changed places', async () => {
    api.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Stage renamed', room_shell: shell(), undo: { available: 0, label: null },
      message: 'Undone: Stage renamed. No fixture was moved.',
    });
    open(shell(), { available: 1, label: 'Stage renamed' });

    type('Name of Overhead ring 1', 'Centre ring');
    expect(button('Save Overhead ring 1').disabled).toBe(false);
    fireEvent.click(undoButton());
    await flush();

    expect(field('Name of Overhead ring 1').value).toBe('Overhead ring 1');
    expect(button('Save Overhead ring 1').disabled).toBe(true);
  });

  it('counts a delete as a step that can be undone', async () => {
    const after = shell();
    after.truss_lines = after.truss_lines!.slice(1);
    const undo = { available: 1, label: 'Overhead line 1 deleted' };
    api.deleteShellItem.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, removed: {}, room_shell: after, undo,
      message: 'Overhead line 1 was taken out of the stored room. No fixture was moved.',
    });
    const onChanged = open();

    fireEvent.click(button('Delete Overhead line 1'));
    // The question says the delete can be taken back.
    expect(screen.getByText(/Undo here brings it back, until the scan is read again\.$/)).toBeTruthy();
    fireEvent.click(button('Delete it'));
    await flush();

    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(undoButton().textContent).toBe('Undo: Overhead line 1 deleted');
  });

  it('says why an undo was refused and changes nothing', async () => {
    const words = 'A locate walkthrough is running on this rig. Finish or end it, then undo the room edit.';
    api.undoShellEdit.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: words } } });
    const onChanged = open(shell(), { available: 1, label: 'Stage renamed' });

    fireEvent.click(undoButton());
    await flush();

    expect(screen.getByText(words)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    // The step is still there to take back once the walkthrough is over.
    expect(undoButton().textContent).toBe('Undo: Stage renamed');
    expect(undoButton().disabled).toBe(false);
  });

  it('says so when a save is refused under a locate walkthrough', async () => {
    const words = 'A locate walkthrough is running on this rig. Finish or end it, then edit the room.';
    api.editShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: words } } });
    const onChanged = open();

    type('Height of Stage', '0.9');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(words)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
