// The Edit Room dialog and a raised area (a stage, a riser, a booth, a
// platform that floats): the "Move the fixtures standing on it" box, the kind
// selector and the base height field on its row, what each sends, and the
// notice that says how many fixtures moved. Then the helpers under them, the
// 2D plan's tooltip and the 3D view's box. The API is a stand-in: nothing here
// reaches a backend. docs/ROOM_SCAN.md, slice 18.
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomShellEditDialog from '../components/rig/RoomShellEditDialog';
import { buildRisers } from '../components/rig/previs/roomShell';
import { roomPlan } from '../components/rig/roomPlan2d';
import { roomScanApi } from '../services/api';
import type { RoomShell, RoomShellEdits } from '../types';
import {
  BASE_HEIGHT_LABEL, CARRY_LABEL, CARRY_STANDING_LABEL, RISER_KIND_CHOICES, baseHeightProblem, baseHeightShown,
  carriedText, carryBoxName, carryLabel, deleteQuestionText, draftOf, editResultText, floatingText, readDraft,
  riserKindShown, shellItems, stoodOn, withCarry,
} from '../utils/roomShellEdit';
import type { CarriedFixture, ShellItem, ShellItemKind } from '../utils/roomShellEdit';

vi.mock('../services/api', () => ({
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

// A stage, a drum riser and a truss across the room.
const shell = (): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [
    { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage' },
    // Stored before a base could be set: it has none, and stands on the floor.
    { center_x: 4, center_z: 2, width: 2, depth: 2, height: 0.3, name: 'Drum riser', kind: 'riser' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 }],
  truss_rings: [],
});

const carried = (id: number, x: number, toZ: number): CarriedFixture => ({
  rig_fixture_id: id,
  name: `Par ${id}`,
  from: { x, y: 0.8, z: -3.5, rotation_y: 0 },
  to: { x, y: 0.8, z: toZ, rotation_y: 0 },
});

/** The dialog over a room and an undo count that each answer replaces, as the rig editor does it. */
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
const box = (title: string) =>
  screen.getByRole('checkbox', { name: `Move the fixtures standing on ${title}` }) as HTMLInputElement;
const kindOf = (title: string) => screen.getByRole('combobox', { name: `Kind of ${title}` }) as HTMLSelectElement;
const undoButton = () => screen.getByTestId('room-shell-undo') as HTMLButtonElement;

const item = (kind: ShellItemKind, index: number, from: RoomShell = shell()): ShellItem => {
  const found = shellItems(from).find((entry) => entry.kind === kind && entry.index === index);
  if (!found) throw new Error(`no ${kind} ${index}`);
  return found;
};

const movedStage = (): RoomShell => {
  const after = shell();
  after.risers![0] = { ...after.risers![0], center_z: -3, suggested: false, basis: 'Moved by hand.' };
  return after;
};

describe('RoomShellEditDialog: a raised area and the fixtures standing on it', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('has the box on each raised area, worded for standing fixtures and ticked', () => {
    open();
    expect(box('Stage').checked).toBe(true);
    expect(box('Drum riser').checked).toBe(true);
    expect(screen.getAllByText('Move the fixtures standing on it')).toHaveLength(2);
    // A truss keeps its own words.
    expect(screen.getAllByText('Move the fixtures hung on it')).toHaveLength(1);
    expect(screen.queryByRole('checkbox', { name: 'Move the fixtures standing on Truss 1' })).toBeNull();
    // The box is not a change to save.
    fireEvent.click(box('Stage'));
    expect(box('Stage').checked).toBe(false);
    expect(button('Save Stage').disabled).toBe(true);
  });

  it('shows what each raised area is and its base height, and neither on a truss', () => {
    open();
    expect(kindOf('Stage').value).toBe('stage');
    expect(kindOf('Drum riser').value).toBe('riser');
    expect(Array.from(kindOf('Stage').options).map((option) => [option.value, option.textContent])).toEqual([
      ['stage', 'Stage'], ['riser', 'Riser'], ['booth', 'Booth or counter'],
    ]);
    expect(field('Base height of Stage').value).toBe('0');
    // One stored with no base stands on the floor.
    expect(field('Base height of Drum riser').value).toBe('0');
    expect(screen.queryByLabelText('Base height of Truss 1')).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Kind of Truss 1' })).toBeNull();
    // Nothing is a change until something is.
    expect(button('Save Stage').disabled).toBe(true);
    expect(button('Save Drum riser').disabled).toBe(true);
  });

  it('moves a stage with the fixtures standing on it, says how many moved, and has the rig read again', async () => {
    const after = movedStage();
    const undo = { available: 1, label: 'Stage moved, with 2 fixtures' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo,
      carry_fixtures: true, fixtures_moved: [carried(1, -2, -3), carried(2, 2, -3)],
    });
    const { onChanged, onFixturesMoved } = open();

    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { center_z: -3, carry_fixtures: true });
    expect(screen.getByText('Stage was moved to 0, -3. 2 fixtures standing on it moved with it.')).toBeTruthy();
    // The room first, then the word that fixtures stand somewhere new.
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    expect(onChanged.mock.invocationCallOrder[0]).toBeLessThan(onFixturesMoved.mock.invocationCallOrder[0]);
    expect(undoButton().textContent).toBe('Undo: Stage moved, with 2 fixtures');
    expect(box('Stage').checked).toBe(true);
  });

  it('leaves the fixtures where they are with the box unticked, and does not have the rig read again', async () => {
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: movedStage(), carry_fixtures: false, fixtures_moved: [],
    });
    const { onChanged, onFixturesMoved } = open();

    fireEvent.click(box('Stage'));
    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { center_z: -3, carry_fixtures: false });
    expect(screen.getByText(
      'Stage was moved to 0, -3. The fixtures standing on it were left where they are.',
    )).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(onFixturesMoved).not.toHaveBeenCalled();
    // Unticked is this row's alone.
    expect(box('Stage').checked).toBe(false);
    expect(box('Drum riser').checked).toBe(true);
  });

  it('makes a riser a stage from its selector, with no word about fixtures', async () => {
    const after = shell();
    after.risers![1] = { ...after.risers![1], kind: 'stage', suggested: false, basis: 'Kind set by hand.' };
    const undo = { available: 1, label: 'Drum riser made a stage' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 1, item: {}, room_shell: after, undo,
      riser_kind: 'stage', first_stage: 0, carry_fixtures: true, fixtures_moved: [],
    });
    const { onChanged, onFixturesMoved } = open();

    fireEvent.change(kindOf('Drum riser'), { target: { value: 'stage' } });
    expect(button('Save Drum riser').disabled).toBe(false);
    fireEvent.click(button('Save Drum riser'));
    await flush();

    // A kind is not a place: the flag that would move fixtures is not sent, and its place in the list is the one it had.
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 1, { riser_kind: 'stage' });
    expect(screen.getByText('Drum riser is now a stage.')).toBeTruthy();
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(onFixturesMoved).not.toHaveBeenCalled();
    expect(kindOf('Drum riser').value).toBe('stage');
    expect(screen.getByText('Kind set by hand')).toBeTruthy();
    expect(button('Save Drum riser').disabled).toBe(true);
    expect(undoButton().textContent).toBe('Undo: Drum riser made a stage');
  });

  it('choosing the kind it already is is no change', () => {
    open();
    fireEvent.change(kindOf('Stage'), { target: { value: 'booth' } });
    expect(button('Save Stage').disabled).toBe(false);
    fireEvent.change(kindOf('Stage'), { target: { value: 'stage' } });
    expect(button('Save Stage').disabled).toBe(true);
  });

  it('floats a raised area on a base height and takes what stands on it up with it', async () => {
    const after = shell();
    after.risers![1] = { ...after.risers![1], base_height: 2.7, suggested: false, basis: 'Resized by hand.' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 1, item: {}, room_shell: after,
      undo: { available: 1, label: 'Drum riser raised, with 1 fixture' },
      carry_fixtures: true, fixtures_moved: [carried(9, 4, 2)],
    });
    const { onFixturesMoved } = open();

    type('Base height of Drum riser', '2,7');
    fireEvent.click(button('Save Drum riser'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 1, { base_height: 2.7, carry_fixtures: true });
    expect(screen.getByText(
      'Drum riser is now 2.0 m by 2.0 m, top 3.00 m above the floor, floating 2.70 m above it. '
      + '1 fixture standing on it moved with it.',
    )).toBeTruthy();
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    expect(field('Base height of Drum riser').value).toBe('2.7');
    expect(screen.getByText('2.0 m by 2.0 m, top 3.00 m above the floor, floating 2.70 m above it')).toBeTruthy();
    expect(undoButton().textContent).toBe('Undo: Drum riser raised, with 1 fixture');
  });

  it('sends a kind, a base and a height in one save, with the flag', async () => {
    api.editShellItem.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: shell() });
    open();

    fireEvent.change(kindOf('Stage'), { target: { value: 'booth' } });
    type('Base height of Stage', '1');
    type('Height of Stage', '0.9');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledWith(
      7, 'risers', 0, { height: 0.9, base_height: 1, riser_kind: 'booth', carry_fixtures: true },
    );
  });

  it('says what is wrong with a base height and sends nothing', () => {
    open();
    const problem = 'Base height must be a number of metres from 0 (on the floor) to 10.';
    for (const wrong of ['-1', '10.5', 'high', '']) {
      type('Base height of Stage', wrong);
      expect(screen.getByText(problem)).toBeTruthy();
      expect(button('Save Stage').disabled).toBe(true);
    }
    type('Base height of Stage', '10');
    expect(screen.queryByText(problem)).toBeNull();
    expect(button('Save Stage').disabled).toBe(false);
    // Back to what is stored: nothing to save.
    type('Base height of Stage', '0');
    expect(button('Save Stage').disabled).toBe(true);
    expect(api.editShellItem).not.toHaveBeenCalled();
  });

  it('shows the server\'s words when the fixtures would be carried out of the room, and changes nothing', async () => {
    const detail = 'That would carry 1 fixture standing on Stage out of the room and the 2 m round it, or through the '
      + 'floor (Par 3 to 9, 1.1, -4.2; across, height, depth in metres). Nothing was changed.';
    api.editShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail } } });
    const { onChanged, onFixturesMoved } = open();

    type('Across of Stage', '7.5');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(detail)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    expect(onFixturesMoved).not.toHaveBeenCalled();
    // What was typed is still there, to be changed or sent again with the box unticked.
    expect(field('Across of Stage').value).toBe('7.5');
    expect(button('Save Stage').disabled).toBe(false);
  });

  it('has the rig read again when an undo puts back what stood on a raised area', async () => {
    const message = 'Undone: Stage moved, with 2 fixtures. 2 fixtures put back where they stood before it.';
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: movedStage(),
      undo: { available: 1, label: 'Stage moved, with 2 fixtures' },
      carry_fixtures: true, fixtures_moved: [carried(1, -2, -3), carried(2, 2, -3)],
    });
    api.undoShellEdit.mockResolvedValue({
      rig_id: 7, undone: 'Stage moved, with 2 fixtures', room_shell: shell(), undo: { available: 0, label: null },
      fixtures_restored: [carried(1, -2, -3), carried(2, 2, -3)], fixtures_skipped: [], message,
    });
    const { onFixturesMoved } = open();
    type('Depth of Stage', '-3');
    fireEvent.click(button('Save Stage'));
    await flush();
    fireEvent.click(box('Drum riser'));

    fireEvent.click(undoButton());
    await flush();

    expect(screen.getByText(message)).toBeTruthy();
    expect(onFixturesMoved).toHaveBeenCalledTimes(2);
    expect(field('Depth of Stage').value).toBe('-3.5');
    // Rows may have changed places: every box is ticked again.
    expect(box('Drum riser').checked).toBe(true);
  });
});

describe('roomShellEdit: a raised area\'s words, flag, base and kind', () => {
  it('words the box for what stands on a raised area and what hangs on a truss', () => {
    expect(stoodOn('risers')).toBe(true);
    expect(stoodOn('truss_lines')).toBe(false);
    expect(CARRY_STANDING_LABEL).toBe('Move the fixtures standing on it');
    expect(carryLabel('risers')).toBe(CARRY_STANDING_LABEL);
    expect(carryLabel('truss_lines')).toBe(CARRY_LABEL);
    expect(carryLabel('truss_rings')).toBe(CARRY_LABEL);
    expect(carryBoxName('risers', 'Stage')).toBe('Move the fixtures standing on Stage');
    expect(carryBoxName('truss_rings', 'Ring 1')).toBe('Move the fixtures hung on Ring 1');
  });

  it('adds the flag to a raised area\'s change of place, size, height or base, and not to its name or kind', () => {
    expect(withCarry({ kind: 'risers' }, { center_x: 1 }, true)).toEqual({ center_x: 1, carry_fixtures: true });
    expect(withCarry({ kind: 'risers' }, { base_height: 2 }, false)).toEqual({ base_height: 2, carry_fixtures: false });
    expect(withCarry({ kind: 'risers' }, { width: 3, depth: 6 }, true)).toEqual({ width: 3, depth: 6, carry_fixtures: true });
    expect(withCarry({ kind: 'risers' }, { riser_kind: 'stage' }, true)).toEqual({ riser_kind: 'stage' });
    expect(withCarry({ kind: 'risers' }, { name: 'Deck', riser_kind: 'booth' }, true)).toEqual({
      name: 'Deck', riser_kind: 'booth',
    });
    expect(withCarry({ kind: 'risers' }, { riser_kind: 'booth', height: 1 }, true)).toEqual({
      riser_kind: 'booth', height: 1, carry_fixtures: true,
    });
  });

  it('says how many standing fixtures moved', () => {
    expect(carriedText('risers', { moved: 3, asked: true })).toBe('3 fixtures standing on it moved with it.');
    expect(carriedText('risers', { moved: 1, asked: true })).toBe('1 fixture standing on it moved with it.');
    expect(carriedText('risers', { moved: 0, asked: true })).toBe('No fixture was moved with it.');
    expect(carriedText('risers', { moved: 0, asked: false })).toBe('The fixtures standing on it were left where they are.');
    expect(carriedText('risers')).toBe('No fixture was moved with it.');
    expect(carriedText('truss_lines', { moved: 2, asked: true })).toBe('2 fixtures hung on it moved with it.');
  });

  it('lists a raised area with its kind and its base, and a truss with neither', () => {
    expect(item('risers', 0)).toMatchObject({ baseHeight: 0, riserKind: 'stage' });
    // Stored with no base: it stands on the floor.
    expect(item('risers', 1)).toMatchObject({ baseHeight: 0, riserKind: 'riser' });
    expect(item('truss_lines', 0)).toMatchObject({ baseHeight: null, riserKind: null });

    const floating = shell();
    floating.risers![1] = { ...floating.risers![1], base_height: 2.7, kind: 'balcony' };
    const balcony = item('risers', 1, floating);
    expect(balcony.baseHeight).toBe(2.7);
    // A kind the row does not know is none of its three.
    expect(balcony.riserKind).toBeNull();
    expect(balcony.detail).toBe('2.0 m by 2.0 m, top 3.00 m above the floor, floating 2.70 m above it');
    // The base is not one of the sizes: those are what the Add form and the size fields go by.
    expect(balcony.sizes).toEqual({ width: 2, depth: 2, height: 0.3 });
    // A base that is not a number, or is under the floor, is the floor.
    floating.risers![1] = { ...floating.risers![1], base_height: -1 };
    expect(item('risers', 1, floating).baseHeight).toBe(0);
    expect(item('risers', 1, floating).detail).toBe('2.0 m by 2.0 m, top 0.30 m above the floor');
  });

  it('says how far above the floor a raised area floats, and nothing for one that stands on it', () => {
    expect(floatingText(2.7)).toBe(', floating 2.70 m above it');
    expect(floatingText(0)).toBe('');
    expect(floatingText(undefined)).toBe('');
    expect(floatingText(null)).toBe('');
    expect(floatingText(Number.NaN)).toBe('');
  });

  it('leaves the base and the kind out of a row\'s draft until they are touched, and shows what is stored', () => {
    const stage = item('risers', 0);
    const draft = draftOf(stage);
    expect(draft.base_height).toBeUndefined();
    expect(draft.riser_kind).toBeUndefined();
    expect(baseHeightShown(stage, draft)).toBe('0');
    expect(riserKindShown(stage, draft)).toBe('stage');
    expect(baseHeightShown(stage, { ...draft, base_height: '1.5' })).toBe('1.5');
    expect(riserKindShown(stage, { ...draft, riser_kind: 'booth' })).toBe('booth');
    const truss = item('truss_lines', 0);
    expect(baseHeightShown(truss, draftOf(truss))).toBe('');
    expect(riserKindShown(truss, draftOf(truss))).toBe('');
  });

  it('reads a base height and a kind from a row, and only what differs from what is stored', () => {
    const stage = item('risers', 0);
    const draft = draftOf(stage);
    expect(readDraft(stage, draft)).toEqual({ changes: null, problem: null });
    expect(readDraft(stage, { ...draft, base_height: '0', riser_kind: 'stage' })).toEqual({ changes: null, problem: null });
    expect(readDraft(stage, { ...draft, base_height: '1,5' }).changes).toEqual({ base_height: 1.5 });
    expect(readDraft(stage, { ...draft, riser_kind: 'booth' }).changes).toEqual({ riser_kind: 'booth' });
    expect(readDraft(stage, { ...draft, name: 'Deck', base_height: '2', riser_kind: 'riser', width: '8' }).changes).toEqual({
      name: 'Deck', width: 8, base_height: 2, riser_kind: 'riser',
    });
    // A base that reads the same to the millimetre is not a change.
    expect(readDraft(stage, { ...draft, base_height: '0.0001' }).changes).toBeNull();
    // One stored with no base can be given one.
    const riser = item('risers', 1);
    expect(readDraft(riser, { ...draftOf(riser), base_height: '0.6' }).changes).toEqual({ base_height: 0.6 });
    // A truss has neither, whatever its draft holds.
    const truss = item('truss_lines', 0);
    expect(readDraft(truss, { ...draftOf(truss), base_height: '2', riser_kind: 'stage' }).changes).toBeNull();
  });

  it('refuses a base height that is not a number from 0 to 10, and a kind that is not one', () => {
    const problem = 'Base height must be a number of metres from 0 (on the floor) to 10.';
    expect(BASE_HEIGHT_LABEL).toBe('Base height');
    expect(baseHeightProblem(null)).toBe(problem);
    expect(baseHeightProblem(-0.01)).toBe(problem);
    expect(baseHeightProblem(10.01)).toBe(problem);
    expect(baseHeightProblem(0)).toBeNull();
    expect(baseHeightProblem(10)).toBeNull();
    const stage = item('risers', 0);
    for (const wrong of ['', 'high', '-1', '11', 'Infinity', 'NaN']) {
      expect(readDraft(stage, { ...draftOf(stage), base_height: wrong })).toEqual({ changes: null, problem });
    }
    expect(readDraft(stage, { ...draftOf(stage), riser_kind: 'balcony' })).toEqual({
      changes: null, problem: 'A raised area is a stage, a riser or a booth.',
    });
    expect(RISER_KIND_CHOICES.map((choice) => choice.kind)).toEqual(['stage', 'riser', 'booth']);
  });

  it('says what a kind change and a base height did', () => {
    const kinded = shell();
    kinded.risers![1] = { ...kinded.risers![1], kind: 'booth' };
    expect(editResultText(item('risers', 1), { riser_kind: 'booth' }, kinded)).toBe('Drum riser is now a booth or counter.');

    // The server calls a riser still named "Riser" a "Stage" when it is made one: the sentence names it as it was.
    const plain = shell();
    plain.risers![1] = { ...plain.risers![1], name: 'Riser' };
    const renamedByServer = shell();
    renamedByServer.risers![1] = { ...renamedByServer.risers![1], name: 'Stage', kind: 'stage' };
    expect(editResultText(item('risers', 1, plain), { riser_kind: 'stage' }, renamedByServer)).toBe('Riser is now a stage.');

    const floated = shell();
    floated.risers![0] = { ...floated.risers![0], base_height: 1.5 };
    expect(editResultText(item('risers', 0), { base_height: 1.5 }, floated, { moved: 3, asked: true })).toBe(
      'Stage is now 6.0 m by 3.0 m, top 2.10 m above the floor, floating 1.50 m above it. '
      + '3 fixtures standing on it moved with it.',
    );
    const both = shell();
    both.risers![0] = { ...both.risers![0], name: 'Deck', kind: 'riser', center_x: 1 };
    expect(editResultText(
      item('risers', 0), { name: 'Deck', riser_kind: 'riser', center_x: 1 }, both, { moved: 0, asked: false },
    )).toBe(
      'Stage is now called Deck. Deck is now a riser. Deck was moved to 1, -3.5. '
      + 'The fixtures standing on it were left where they are.',
    );
  });

  it('says that a deleted raised area leaves what stands on it', () => {
    const stage = deleteQuestionText(item('risers', 0));
    expect(stage).toBe(
      'Take Stage out of the stored room? Fixtures standing on it stay where they are. '
      + 'It stays deleted when the scan is applied again. Undo here brings it back, until then.',
    );
    expect(deleteQuestionText(item('truss_lines', 0))).not.toContain('standing on it');
  });

  it('marks a raised area whose kind a person set', () => {
    const kinded = shell();
    kinded.risers![1] = { ...kinded.risers![1], kind: 'stage', suggested: false, basis: 'scan: a level area. Kind set by hand.' };
    expect(item('risers', 1, kinded).marks).toEqual(['Kind set by hand']);
  });
});

describe('a floating raised area in the views', () => {
  const floating = (): RoomShell => ({
    source: 'scan',
    room: { width: 12, depth: 10, height: 6 },
    risers: [
      { center_x: 0, center_z: 3, width: 4, depth: 2, height: 0.3, base_height: 2.7, name: 'Balcony', kind: 'riser' },
      { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage' },
    ],
  });

  it('says in the 2D plan\'s tooltip how far above the floor it floats, and nothing new for one that stands on it', () => {
    const plan = roomPlan(floating())!;
    const [balcony, stage] = plan.raised;
    expect(balcony.top).toBeCloseTo(3);
    expect(balcony.label).toBe('Balcony · 3.00 m high');
    expect(balcony.tooltip).toBe('Balcony: 4.0 m by 2.0 m, top 3.00 m above the floor, floating 2.70 m above it');
    expect(stage.tooltip).toBe('Stage: 6.0 m by 3.0 m, top 0.60 m above the floor');
  });

  it('is drawn in the 3D view from its base up, not from the floor', () => {
    const shapes = floating().risers!;
    const lifted = buildRisers([shapes[0]])!;
    lifted.computeBoundingBox();
    expect(lifted.boundingBox!.min.y).toBeCloseTo(2.7);
    // The deck, and the thin top plate drawn over it.
    expect(lifted.boundingBox!.max.y).toBeCloseTo(3.03);
    const standing = buildRisers([shapes[1]])!;
    standing.computeBoundingBox();
    expect(standing.boundingBox!.min.y).toBeCloseTo(0);
  });
});

// Slice 21: a raised area stands at any heading.
describe('RoomShellEditDialog: a raised area\'s heading', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  const turnedStage = (heading: number): RoomShell => {
    const after = shell();
    after.risers![0] = {
      ...after.risers![0], heading_deg: heading, suggested: false, basis: 'Resized by hand.',
    };
    return after;
  };

  it('has a heading field on each raised area, at 0 for one that stands square, and is no change until typed in', () => {
    open();
    expect(field('Heading of Stage').value).toBe('0');
    expect(field('Heading of Drum riser').value).toBe('0');
    // A truss keeps the heading field it always had.
    expect(field('Heading of Truss 1').value).toBe('0');
    expect(button('Save Stage').disabled).toBe(true);
    type('Heading of Stage', '30');
    expect(button('Save Stage').disabled).toBe(false);
    type('Heading of Stage', '0');
    expect(button('Save Stage').disabled).toBe(true);
  });

  it('turns a stage with the fixtures standing on it, and says what it now is', async () => {
    const after = turnedStage(30);
    const undo = { available: 1, label: 'Stage turned, with 1 fixture' };
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: after, undo,
      carry_fixtures: true, fixtures_moved: [carried(1, -2, -3)],
    });
    const { onChanged, onFixturesMoved } = open();

    type('Heading of Stage', '30');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(api.editShellItem).toHaveBeenCalledTimes(1);
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 30, carry_fixtures: true });
    expect(screen.getByText(
      'Stage is now 6.0 m by 3.0 m, turned 30 degrees, top 0.60 m above the floor. '
      + '1 fixture standing on it moved with it.',
    )).toBeTruthy();
    expect(onChanged).toHaveBeenCalledWith(after, undo);
    expect(onFixturesMoved).toHaveBeenCalledTimes(1);
    // The row shows what is stored.
    expect(field('Heading of Stage').value).toBe('30');
    expect(button('Save Stage').disabled).toBe(true);
  });

  it('leaves what stands on it with the box unticked, and shows a heading as the server folded it', async () => {
    api.editShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 0, item: {}, room_shell: turnedStage(-45),
      carry_fixtures: false, fixtures_moved: [],
    });
    const { onFixturesMoved } = open();

    fireEvent.click(box('Stage'));
    type('Heading of Stage', '135');
    fireEvent.click(button('Save Stage'));
    await flush();

    // Sent as typed.
    expect(api.editShellItem).toHaveBeenCalledWith(7, 'risers', 0, { heading_deg: 135, carry_fixtures: false });
    expect(onFixturesMoved).not.toHaveBeenCalled();
    expect(field('Heading of Stage').value).toBe('-45');
  });

  it('says what is wrong with a heading and sends nothing', () => {
    open();
    type('Heading of Stage', 'sideways');
    expect(screen.getByText('Heading must be a number of degrees, such as 45 or -30.')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    type('Heading of Stage', '400');
    expect(screen.getByText('Heading must be between -360 and 360 degrees.')).toBeTruthy();
    expect(button('Save Stage').disabled).toBe(true);
    expect(api.editShellItem).not.toHaveBeenCalled();
  });

  it('shows the server\'s words when a turn is refused, and changes nothing', async () => {
    const detail = 'That would carry 1 fixture standing on Stage out of the room and the 2 m round it. Nothing was changed.';
    api.editShellItem.mockRejectedValue({ isAxiosError: true, response: { status: 422, data: { detail } } });
    const { onChanged } = open();

    type('Heading of Stage', '60');
    fireEvent.click(button('Save Stage'));
    await flush();

    expect(screen.getByText(detail)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
    // What was typed is kept, to be put right.
    expect(field('Heading of Stage').value).toBe('60');
  });

  it('has a heading field on the Add form for a raised area, and sends it only when it is turned', async () => {
    api.addShellItem.mockResolvedValue({
      rig_id: 7, kind: 'risers', index: 2, item: {}, room_shell: shell(), message: 'Riser was added.',
    });
    open();
    // The form starts at a riser, square to the room.
    expect(field('Heading of the new item').value).toBe('0');
    fireEvent.click(button('Add to the room'));
    await flush();
    expect(api.addShellItem).toHaveBeenLastCalledWith(7, 'risers', {
      center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser',
    });

    type('Heading of the new item', '30');
    fireEvent.click(button('Add to the room'));
    await flush();
    expect(api.addShellItem).toHaveBeenLastCalledWith(7, 'risers', {
      center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, riser_kind: 'riser', heading_deg: 30,
    });
  });

  it('will not add a raised area at a heading that is not one, and has no heading for a ring', () => {
    open();
    type('Heading of the new item', 'round');
    expect(button('Add to the room').disabled).toBe(true);
    fireEvent.change(screen.getByRole('combobox', { name: 'What to add' }), { target: { value: 'truss_ring' } });
    expect(screen.queryByLabelText('Heading of the new item')).toBeNull();
    expect(button('Add to the room').disabled).toBe(false);
  });
});
