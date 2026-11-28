// Edit Room's "DJ booth" box on a raised area's row (docs/ROOM_SCAN.md, slice
// 28): what it shows, what it sends, that one row at a time is the booth, and
// that the room's own Undo takes it back. Then the helpers under it. The API
// is a stand-in: nothing here reaches a backend. The tag the 2D plan prints on
// the booth is in StageView2DDjBooth.test.tsx.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';
import {
  DJ_BOOTH_LABEL, djBoothBoxName, djBoothShown, draftOf, editResultText, readDraft, shellItems, withCarry,
} from '../utils/roomShellEdit';
import type { ShellItem, ShellItemKind } from '../utils/roomShellEdit';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: {
    editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn(), getOutline: vi.fn(),
  },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage, the bar (which the scan called a booth), the DJ's own booth and a truss.
const shell = (booth: number | null = null): RoomShell => {
  const room: RoomShell = {
    source: 'scan',
    room: { width: 12, depth: 10, height: 6 },
    risers: [
      { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage' },
      { center_x: 4, center_z: 3, width: 2, depth: 1, height: 1.1, base_height: 0, name: 'Bar', kind: 'booth' },
      { center_x: -4, center_z: 0, width: 1, depth: 2, height: 1, base_height: 0, name: 'Decks', kind: 'booth' },
    ],
    truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 }],
    truss_rings: [],
  };
  if (booth !== null) room.risers![booth] = { ...room.risers![booth], is_dj_booth: true };
  return room;
};

/** The dialog over a room and an undo count that each answer replaces, as the rig editor does it. */
function Harness({ start, onChanged, onFixturesMoved }: {
  start: RoomShell;
  onChanged: (next: RoomShell, undo?: RoomShellEdits) => void;
  onFixturesMoved: () => void;
}) {
  const [stored, setStored] = useState<RoomShell | null>(start);
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
      onFixturesMoved={onFixturesMoved}
    />
  );
}

const open = (start: RoomShell = shell()) => {
  const onChanged = vi.fn();
  const onFixturesMoved = vi.fn();
  render(<Harness start={start} onChanged={onChanged} onFixturesMoved={onFixturesMoved} />);
  return { onChanged, onFixturesMoved };
};

const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const djBox = (title: string) => screen.getByRole('checkbox', { name: `DJ booth: ${title}` }) as HTMLInputElement;
const kindOf = (title: string) => screen.getByRole('combobox', { name: `Kind of ${title}` }) as HTMLSelectElement;
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;

const item = (kind: ShellItemKind, index: number, from: RoomShell = shell()): ShellItem => {
  const found = shellItems(from).find((entry) => entry.kind === kind && entry.index === index);
  if (!found) throw new Error(`no ${kind} ${index}`);
  return found;
};

/** What the server answers a saved row with. */
const edited = (room: RoomShell, label: string, available = 1) => ({
  rig_id: 7, kind: 'risers' as const, index: 0, item: {}, room_shell: room, changed: true,
  undo: { available, label }, fixtures_moved: [], items_moved: [],
});

describe('RoomShellEditDialog: the DJ booth box', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('is on each raised area and on no truss, and unticked in a room nobody marked one in', () => {
    open();
    expect(djBox('Stage').checked).toBe(false);
    expect(djBox('Bar').checked).toBe(false);
    expect(djBox('Decks').checked).toBe(false);
    expect(screen.getAllByText(DJ_BOOTH_LABEL)).toHaveLength(3);
    expect(screen.queryByRole('checkbox', { name: 'DJ booth: Truss 1' })).toBeNull();
    // Nothing is a change until something is.
    expect(button('Save Decks').disabled).toBe(true);
  });

  it('shows the one that is stored as the booth', () => {
    open(shell(2));
    expect(djBox('Decks').checked).toBe(true);
    expect(djBox('Bar').checked).toBe(false);
    expect(djBox('Stage').checked).toBe(false);
    expect(button('Save Decks').disabled).toBe(true);
  });

  it('sends the mark with the row\'s Save, and moves no fixture', async () => {
    api.editShellItem.mockResolvedValue(edited(shell(2), 'Decks marked as the DJ booth'));
    const { onChanged, onFixturesMoved } = open();

    fireEvent.click(djBox('Decks'));
    expect(djBox('Decks').checked).toBe(true);
    // Ticked is typed, not saved: nothing is sent until Save.
    expect(api.editShellItem).not.toHaveBeenCalled();
    expect(button('Save Decks').disabled).toBe(false);
    fireEvent.click(button('Save Decks'));
    await flush();

    // The mark alone: it is not a move, so it says nothing about carrying fixtures.
    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 2, { is_dj_booth: true });
    expect(onChanged).toHaveBeenCalledWith(shell(2), { available: 1, label: 'Decks marked as the DJ booth' });
    expect(onFixturesMoved).not.toHaveBeenCalled();
    expect(djBox('Decks').checked).toBe(true);
    expect(button('Save Decks').disabled).toBe(true);
    expect(screen.getByText(/Decks is now the DJ booth/)).toBeTruthy();
    expect(undoButton().textContent).toContain('Decks marked as the DJ booth');
  });

  it('is taken back by the room\'s own Undo', async () => {
    api.editShellItem.mockResolvedValue(edited(shell(2), 'Decks marked as the DJ booth'));
    api.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Decks marked as the DJ booth', room_shell: shell(), undo: { available: 0, label: null },
      fixtures_restored: [], fixtures_skipped: [], message: 'Undone: Decks marked as the DJ booth.',
    });
    open();
    fireEvent.click(djBox('Decks'));
    fireEvent.click(button('Save Decks'));
    await flush();
    expect(djBox('Decks').checked).toBe(true);

    fireEvent.click(undoButton());
    await flush();

    expect(api.undoShellEdit).toHaveBeenCalledWith(7);
    expect(djBox('Decks').checked).toBe(false);
    expect(djBox('Bar').checked).toBe(false);
  });

  it('takes the mark off: unticking the booth sends false', async () => {
    api.editShellItem.mockResolvedValue(edited(shell(), 'Decks no longer marked as the DJ booth'));
    open(shell(2));

    fireEvent.click(djBox('Decks'));
    fireEvent.click(button('Save Decks'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 2, { is_dj_booth: false });
    expect(djBox('Decks').checked).toBe(false);
    expect(screen.getByText(/Decks is no longer marked as the DJ booth/)).toBeTruthy();
  });

  it('has one booth at a time: marking another unticks the one that was', async () => {
    api.editShellItem.mockResolvedValue(edited(shell(0), 'Stage marked as the DJ booth'));
    open(shell(2));

    fireEvent.click(djBox('Stage'));
    fireEvent.click(button('Save Stage'));
    await flush();

    // Only the row that was ticked is sent: the server takes the mark off the other.
    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { is_dj_booth: true });
    expect(djBox('Stage').checked).toBe(true);
    expect(djBox('Decks').checked).toBe(false);
    expect(button('Save Decks').disabled).toBe(true);
  });

  it('lets go of a box ticked on another row and not saved, once a row is saved as the booth', async () => {
    api.editShellItem.mockResolvedValue(edited(shell(2), 'Decks marked as the DJ booth'));
    open();

    fireEvent.click(djBox('Bar'));
    fireEvent.click(djBox('Decks'));
    fireEvent.click(button('Save Decks'));
    await flush();

    expect(djBox('Decks').checked).toBe(true);
    expect(djBox('Bar').checked).toBe(false);
    expect(button('Save Bar').disabled).toBe(true);
  });

  it('says the booth is still the booth when its kind is changed, so the server keeps the mark', async () => {
    const riser = shell(2);
    riser.risers![2] = { ...riser.risers![2], kind: 'riser' };
    api.editShellItem.mockResolvedValue(edited(riser, 'Decks made a riser'));
    open(shell(2));

    fireEvent.change(kindOf('Decks'), { target: { value: 'riser' } });
    fireEvent.click(button('Save Decks'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 2, { riser_kind: 'riser', is_dj_booth: true });
    expect(djBox('Decks').checked).toBe(true);
  });

  it('goes with a move in the same save, which still carries the fixtures', async () => {
    const moved = shell(2);
    moved.risers![2] = { ...moved.risers![2], center_x: -3.5 };
    api.editShellItem.mockResolvedValue(edited(moved, 'Decks moved and marked as the DJ booth'));
    open();

    fireEvent.change(screen.getByLabelText('Across of Decks'), { target: { value: '-3.5' } });
    fireEvent.click(djBox('Decks'));
    fireEvent.click(button('Save Decks'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(
      7, 'risers', 2, { center_x: -3.5, is_dj_booth: true, carry_fixtures: true },
    );
  });
});

describe('the DJ booth box, read from a row', () => {
  it('knows which raised area is the booth, and that a truss cannot be', () => {
    expect(item('risers', 2).djBooth).toBe(false);
    expect(item('risers', 2, shell(2)).djBooth).toBe(true);
    expect(item('risers', 1, shell(2)).djBooth).toBe(false);
    expect(item('truss_lines', 0, shell(2)).djBooth).toBeNull();
    expect(djBoothBoxName('Decks')).toBe('DJ booth: Decks');
  });

  it('shows what was ticked, or what is stored', () => {
    const plain = item('risers', 2);
    const booth = item('risers', 2, shell(2));
    expect(djBoothShown(plain, draftOf(plain))).toBe(false);
    expect(djBoothShown(booth, draftOf(booth))).toBe(true);
    expect(djBoothShown(plain, { ...draftOf(plain), is_dj_booth: true })).toBe(true);
    expect(djBoothShown(booth, { ...draftOf(booth), is_dj_booth: false })).toBe(false);
    const truss = item('truss_lines', 0);
    expect(djBoothShown(truss, draftOf(truss))).toBe(false);
  });

  it('sends the mark only when it differs from what is stored', () => {
    const plain = item('risers', 2);
    const booth = item('risers', 2, shell(2));
    expect(readDraft(plain, draftOf(plain)).changes).toBeNull();
    expect(readDraft(booth, draftOf(booth)).changes).toBeNull();
    expect(readDraft(plain, { ...draftOf(plain), is_dj_booth: true }).changes).toEqual({ is_dj_booth: true });
    expect(readDraft(booth, { ...draftOf(booth), is_dj_booth: false }).changes).toEqual({ is_dj_booth: false });
    // Ticked and unticked again is no change.
    expect(readDraft(plain, { ...draftOf(plain), is_dj_booth: false }).changes).toBeNull();
    expect(readDraft(booth, { ...draftOf(booth), is_dj_booth: true }).changes).toBeNull();
    // A truss has no such box, whatever its draft holds.
    const truss = item('truss_lines', 0);
    expect(readDraft(truss, { ...draftOf(truss), is_dj_booth: true }).changes).toBeNull();
  });

  it('carries the mark along with a change of kind, and not when the box is unticked with it', () => {
    const plain = item('risers', 2);
    const booth = item('risers', 2, shell(2));
    expect(readDraft(booth, { ...draftOf(booth), riser_kind: 'stage' }).changes)
      .toEqual({ riser_kind: 'stage', is_dj_booth: true });
    expect(readDraft(booth, { ...draftOf(booth), riser_kind: 'stage', is_dj_booth: false }).changes)
      .toEqual({ riser_kind: 'stage', is_dj_booth: false });
    // One that is not the booth changes kind as it always did.
    expect(readDraft(plain, { ...draftOf(plain), riser_kind: 'stage' }).changes).toEqual({ riser_kind: 'stage' });
    // And a rename of the booth says nothing of the mark: nothing would take it off.
    expect(readDraft(booth, { ...draftOf(booth), name: 'DJ booth' }).changes).toEqual({ name: 'DJ booth' });
  });

  it('is not a change that carries fixtures', () => {
    expect(withCarry({ kind: 'risers' }, { is_dj_booth: true }, true)).toEqual({ is_dj_booth: true });
    expect(withCarry({ kind: 'risers' }, { is_dj_booth: true, riser_kind: 'booth', name: 'Decks' }, false))
      .toEqual({ is_dj_booth: true, riser_kind: 'booth', name: 'Decks' });
    expect(withCarry({ kind: 'risers' }, { is_dj_booth: true, height: 1.2 }, false))
      .toEqual({ is_dj_booth: true, height: 1.2, carry_fixtures: false });
  });

  it('says what the mark did, and nothing when a change of kind only kept it', () => {
    const plain = item('risers', 2);
    const booth = item('risers', 2, shell(2));
    expect(editResultText(plain, { is_dj_booth: true }, shell(2))).toBe(
      'Decks is now the DJ booth: the 3D view puts the decks and the DJ there, and its DJ and Floor cameras look at it.',
    );
    expect(editResultText(booth, { is_dj_booth: false }, shell())).toBe('Decks is no longer marked as the DJ booth.');
    const staged = shell(2);
    staged.risers![2] = { ...staged.risers![2], kind: 'stage' };
    expect(editResultText(booth, { riser_kind: 'stage', is_dj_booth: true }, staged)).toBe('Decks is now a stage.');
  });
});
