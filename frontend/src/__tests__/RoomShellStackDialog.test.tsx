// The Edit Room dialog and slice 20: the base height field of the "Add what
// the scan missed" form, what it sends and what it refuses, and the notice
// that says a riser standing on a stage went with the stage. Then the helpers
// under them. The API is a stand-in: nothing here reaches a backend.
// docs/ROOM_SCAN.md, slice 20.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';
import {
  carriedText, editResultText, newItemDraft, readNewItem, shellItems, stackedText,
} from '../utils/roomShellEdit';
import type { CarriedArea, CarriedFixture } from '../utils/roomShellEdit';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage with a drum riser standing on it, and a truss across the room.
const shell = (stageZ = -3.5): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [
    { center_x: 0, center_z: stageZ, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage' },
    { center_x: 1, center_z: stageZ, width: 2, depth: 2, height: 0.3, base_height: 0.6, name: 'Drum riser', kind: 'riser' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 }],
  truss_rings: [],
});

const carried = (id: number): CarriedFixture => ({
  rig_fixture_id: id,
  name: `Par ${id}`,
  from: { x: 0, y: 0.8, z: -3.5, rotation_y: 0 },
  to: { x: 0, y: 0.8, z: -3, rotation_y: 0 },
});

const drumMoved: CarriedArea = {
  kind: 'risers',
  index: 1,
  name: 'Drum riser',
  from: { center_x: 1, center_z: -3.5, width: 2, depth: 2, base_height: 0.6 },
  to: { center_x: 1, center_z: -3, width: 2, depth: 2, base_height: 0.6 },
};

function Harness({ onChanged, onFixturesMoved }: {
  onChanged: (next: RoomShell, undo?: RoomShellEdits) => void;
  onFixturesMoved: () => void;
}) {
  const [stored, setStored] = useState<RoomShell | null>(shell());
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

const open = () => {
  const onChanged = vi.fn();
  const onFixturesMoved = vi.fn();
  render(<Harness onChanged={onChanged} onFixturesMoved={onFixturesMoved} />);
  return { onChanged, onFixturesMoved };
};

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const whatToAdd = () => screen.getByRole('combobox', { name: 'What to add' }) as HTMLSelectElement;
const NEW_BASE = 'Base height of the new item';
const BASE_PROBLEM = 'Base height must be a number of metres from 0 (on the floor) to 10.';

describe('RoomShellEditDialog: the base height of an added raised area', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('has the field for a stage, a riser and a booth, starting on the floor, and not for a truss or a ring', () => {
    open();
    expect(whatToAdd().value).toBe('riser');
    expect(field(NEW_BASE).value).toBe('0');
    for (const what of ['stage', 'booth']) {
      fireEvent.change(whatToAdd(), { target: { value: what } });
      expect(field(NEW_BASE).value).toBe('0');
    }
    for (const what of ['truss_line', 'truss_ring']) {
      fireEvent.change(whatToAdd(), { target: { value: what } });
      expect(screen.queryByLabelText(NEW_BASE)).toBeNull();
    }
  });

  it('sends the base with a platform that floats', async () => {
    const after = shell();
    after.risers!.push({
      center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, base_height: 2.7, name: 'Balcony', kind: 'riser',
    });
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 2, item: {}, room_shell: after, message: 'Balcony was added.',
    });
    const { onChanged } = open();

    type('Name of the new item', 'Balcony');
    // A comma is a decimal point, as in every other field.
    type(NEW_BASE, '2,7');
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(api.addShellItem).toHaveBeenCalledTimes(1);
    expect(api.addShellItem).toHaveBeenCalledWith(7, 'risers', {
      name: 'Balcony', center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser', base_height: 2.7,
    });
    expect(onChanged).toHaveBeenCalledWith(after, undefined);
    // Its row shows the base it was given, and the form starts on the floor again.
    expect(field('Base height of Balcony').value).toBe('2.7');
    expect(field(NEW_BASE).value).toBe('0');
  });

  it('sends no base for one that stands on the floor, typed as 0 or left empty', async () => {
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 2, item: {}, room_shell: shell(), message: 'Riser was added.',
    });
    open();

    for (const typed of ['0', '', '0.0']) {
      type(NEW_BASE, typed);
      expect(screen.queryByText(BASE_PROBLEM)).toBeNull();
      fireEvent.click(button('Add to the room'));
      await flush();
      expect(api.addShellItem).toHaveBeenLastCalledWith(7, 'risers', {
        center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser',
      });
    }
  });

  it('says what is wrong with a base height and sends nothing', () => {
    open();
    for (const wrong of ['-1', '10.5', 'high']) {
      type(NEW_BASE, wrong);
      expect(screen.getByText(BASE_PROBLEM)).toBeTruthy();
      expect(button('Add to the room').disabled).toBe(true);
    }
    type(NEW_BASE, '10');
    expect(screen.queryByText(BASE_PROBLEM)).toBeNull();
    expect(button('Add to the room').disabled).toBe(false);
    expect(api.addShellItem).not.toHaveBeenCalled();
  });

  it('keeps the base typed from one raised kind to another, and a wrong one does not hold up a truss', () => {
    open();
    type(NEW_BASE, '1.2');
    fireEvent.change(whatToAdd(), { target: { value: 'stage' } });
    expect(field(NEW_BASE).value).toBe('1.2');
    type(NEW_BASE, 'high');
    expect(button('Add to the room').disabled).toBe(true);
    fireEvent.change(whatToAdd(), { target: { value: 'truss_line' } });
    expect(screen.queryByText(BASE_PROBLEM)).toBeNull();
    expect(button('Add to the room').disabled).toBe(false);
  });

  it('shows the server\'s words when the top would be above the ceiling, and keeps the form as typed', async () => {
    const words = 'That would put the top of the raised area 6.1 m above the floor (a base of 5.8 m and a height of '
      + '0.3 m), and the ceiling is at 6 m. Give it a lower base or a lower height.';
    api.addShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail: words } } });
    const { onChanged } = open();

    type(NEW_BASE, '5.8');
    fireEvent.click(button('Add to the room'));
    await flush();

    expect(screen.getByText(words)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    expect(field(NEW_BASE).value).toBe('5.8');
  });
});

describe('RoomShellEditDialog: a riser standing on a stage goes with the stage', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('says that the riser moved too, shows it where the server put it, and has the rig read again', async () => {
    const after = shell(-3);
    const undo = { available: 1, label: 'Stage moved, with 1 raised area and 3 fixtures' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo,
      carry_fixtures: true, fixtures_moved: [carried(1), carried(2), carried(3)], items_moved: [drumMoved],
    });
    const { onChanged, onFixturesMoved } = open();

    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();

    // One request for the stage: the server carries the riser.
    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { center_z: -3, carry_fixtures: true });
    expect(screen.getByText(
      'Stage was moved to 0, -3. 3 fixtures standing on it, or on what stands on it, moved with it. '
      + '1 raised area standing on it moved with it too.',
    )).toBeTruthy();
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    expect(field('Depth of Drum riser').value).toBe('-3');
  });

  it('lets go of what was typed in the carried riser\'s row, and keeps what was typed in any other', async () => {
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: shell(-3),
      carry_fixtures: true, fixtures_moved: [], items_moved: [drumMoved],
    });
    open();

    // A name typed in the riser's row holds its place as it was, -3.5, with it.
    type('Name of Drum riser', 'Drums');
    type('Name of Truss 1', 'Front truss');
    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();

    // The riser's row shows where the server put it: saving it now cannot send it back.
    expect(field('Depth of Drum riser').value).toBe('-3');
    expect(field('Name of Drum riser').value).toBe('Drum riser');
    expect(button('Save Drum riser').disabled).toBe(true);
    expect(field('Name of Truss 1').value).toBe('Front truss');
  });

  it('says so when the riser moved and no fixture did, and does not have the rig read again', async () => {
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: shell(-3),
      carry_fixtures: true, fixtures_moved: [], items_moved: [drumMoved],
    });
    const { onFixturesMoved } = open();

    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(
      'Stage was moved to 0, -3. No fixture was moved with it. 1 raised area standing on it moved with it too.',
    )).toBeTruthy();
    expect(onFixturesMoved).not.toHaveBeenCalled();
  });
});

describe('roomShellEdit: an added base height and a carried stack', () => {
  it('starts the Add form on the floor for every kind', () => {
    for (const what of ['stage', 'riser', 'booth', 'truss_line', 'truss_ring'] as const) {
      expect(newItemDraft(what).base_height).toBe('0');
    }
  });

  it('reads a base height into what is sent only when the platform floats', () => {
    expect('base_height' in (readNewItem(newItemDraft('stage')).body ?? {})).toBe(false);
    expect('base_height' in (readNewItem({ ...newItemDraft('riser'), base_height: '  ' }).body ?? {})).toBe(false);
    expect(readNewItem({ ...newItemDraft('riser'), base_height: '2.7' }).body).toEqual({
      center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser', base_height: 2.7,
    });
    expect(readNewItem({ ...newItemDraft('booth'), base_height: '10' }).body?.base_height).toBe(10);
  });

  it('refuses a base height that is not a number from 0 to 10, for a raised area only', () => {
    for (const wrong of ['-0.1', '10.01', 'high', '1e999']) {
      const reading = readNewItem({ ...newItemDraft('stage'), base_height: wrong });
      expect(reading.body).toBeNull();
      expect(reading.problem).toBe('Base height must be a number of metres from 0 (on the floor) to 10.');
    }
    // A truss has no base: what the field last held is neither checked nor sent.
    for (const what of ['truss_line', 'truss_ring'] as const) {
      const reading = readNewItem({ ...newItemDraft(what), base_height: 'high' });
      expect(reading.problem).toBeNull();
      expect('base_height' in (reading.body ?? {})).toBe(false);
    }
  });

  it('says how many raised areas went with the one they stand on', () => {
    expect(stackedText('risers', 1)).toBe(' 1 raised area standing on it moved with it too.');
    expect(stackedText('risers', 2)).toBe(' 2 raised areas standing on it moved with it too.');
    expect(stackedText('risers', 0)).toBe('');
    expect(stackedText('risers', undefined)).toBe('');
    // Nothing stands on a truss.
    expect(stackedText('truss_lines', 2)).toBe('');
    expect(carriedText('risers', { moved: 2, asked: true, areas: 1 })).toBe(
      '2 fixtures standing on it, or on what stands on it, moved with it. 1 raised area standing on it moved with it too.',
    );
    expect(carriedText('risers', { moved: 0, asked: true, areas: 2 })).toBe(
      'No fixture was moved with it. 2 raised areas standing on it moved with it too.',
    );
    // As it was with none carried.
    expect(carriedText('risers', { moved: 2, asked: true, areas: 0 })).toBe('2 fixtures standing on it moved with it.');
    expect(carriedText('truss_lines', { moved: 2, asked: true, areas: 3 })).toBe('2 fixtures hung on it moved with it.');
  });

  it('puts the stack into what a saved change says', () => {
    const stage = shellItems(shell()).find((entry) => entry.kind === 'risers' && entry.index === 0)!;
    expect(editResultText(stage, { height: 0.9 }, shell(), { moved: 0, asked: true, areas: 1 })).toContain(
      'No fixture was moved with it. 1 raised area standing on it moved with it too.',
    );
  });
});
