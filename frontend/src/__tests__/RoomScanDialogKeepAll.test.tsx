// "Keep all", and the carry-over list that outlives the dialog (docs/ROOM_SCAN.md, slice 37): with two or
// more `carry_over` entries the dialog has a "Keep all" button that sends every one not yet kept in one
// request (POST /room-scan/carry-over/all); each "Keep" button finds its warning by the warning's `id`; and
// the dialog opened again with no scan on screen shows the entries kept with the stored room.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import {
  carryOverKey, handEditWarningEntries, keepAllButtonText, pendingCarryOverOf, roomScanCarryOverAllPath,
} from '../utils/roomScan';
import type { RoomScanCarryOver, RoomScanHandEdits, RoomScanPreview } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: {
    preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn(), carryOver: vi.fn(), carryOverAll: vi.fn(),
  },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const NOTHING = { areas: 0, kept: [], added_kept: [], added_replaced: [] };
const RETRIM = 'The scan read a truss at 2.8 m where Front truss was, against its trim of 3.5 m: '
  + 'more than 1 m from where the scan read it before, so its name and trim were not kept.';
const BESIDE = 'The scan read Booth or counter 1 m from where The bar was, sharing 33% of the plan with it '
  + 'where half is needed, so its name and height were not kept.';
// The server's places are 1 and 2 (a warning it gives first is passed over by the dialog, having no words);
// the places are given crossed here, so only the ids put each button in its own warning.
const LINE: RoomScanCarryOver = {
  kind: 'truss_lines', old_name: 'Front truss', old_trim_or_height: 3.5, edits: ['name', 'height'],
  new_index: 0, new_name: 'Overhead line 1', reason: 'hanging height', warning: 2, warning_id: 'lost-0',
};
const BAR: RoomScanCarryOver = {
  kind: 'risers', old_name: 'The bar', old_trim_or_height: 1.2, edits: ['name', 'height'],
  new_index: 1, new_name: 'Booth or counter', reason: 'read beside', warning: 1, warning_id: 'lost-1',
};
const TWO: RoomScanHandEdits = {
  ...NOTHING,
  warnings: [
    { kind: 'truss_lines', name: '', reason: '' },
    { kind: 'truss_lines', name: 'Front truss', reason: 'hanging height', message: RETRIM, id: 'lost-0' },
    { kind: 'risers', name: 'The bar', reason: 'read beside', message: BESIDE, id: 'lost-1' },
  ],
  carry_over: [LINE, BAR],
};
const STORED = {
  room_shell_stored: true, fixtures_moved: 0, fixtures_still_unconfirmed: 0, message: 'The room is stored.',
};

function scan(edits?: RoomScanHandEdits | null, applied: RoomScanPreview['applied'] = null): RoomScanPreview {
  return {
    rig_id: 7,
    rig_name: 'Club',
    file: 'club.obj',
    format: 'obj',
    room_shell: { room: { width: 12, depth: 9, height: 5 }, risers: [], truss_lines: [] } as RoomScanPreview['room_shell'],
    replaces_existing_shell: true,
    summary: {
      width: 12, depth: 9, height: 5, raised_areas: 2, overhead_lines: 1,
      hanging_heights: [4], units: 'm', up_axis: 'y',
    },
    assumptions: ['Units read as m.'],
    warnings: [],
    fixtures: { total: 6, unconfirmed: 0, would_move: 0, moves: [] },
    operator_guide: 'docs/ROOM_SCAN.md',
    ...(edits === undefined ? {} : { hand_edits: edits }),
    applied,
  };
}

async function applyScan(answer: RoomScanPreview, onChanged = vi.fn()) {
  api.preview.mockResolvedValue(scan(TWO));
  api.apply.mockResolvedValue(answer);
  render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={onChanged} />);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
  await flush();
  fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
  await flush();
  return onChanged;
}

const buttons = () => screen.queryAllByTestId('room-scan-carry-over');
const keepAll = () => screen.queryByTestId('room-scan-carry-over-all') as HTMLButtonElement | null;
const KEPT_BOTH = {
  rig_id: 7, changed: true,
  carried: [
    { warning_id: 'lost-0', kind: 'truss_lines', index: 0, old_name: 'Front truss', changed: true, fixtures_moved: 0, message: 'a' },
    { warning_id: 'lost-1', kind: 'risers', index: 1, old_name: 'The bar', changed: true, fixtures_moved: 0, message: 'b' },
  ],
  message: 'Kept 2 of 2 from the last scan, as one step of Undo.',
  pending_carry_over: [],
};

describe('"Keep all" in the Room Scan dialog after Apply', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('puts each button in its own warning by id, not by place', async () => {
    await applyScan(scan(undefined, { ...STORED, hand_edits: TWO }));
    const warnings = screen.getAllByTestId('room-scan-hand-edit-warning');
    expect(warnings).toHaveLength(2);
    const [line, bar] = buttons();
    expect(line.textContent).toBe('Keep Front truss on this one');
    expect(bar.textContent).toBe('Keep The bar on this one');
    expect(warnings[0].textContent).toContain('Front truss was');
    expect(warnings[0].contains(line)).toBe(true);
    expect(warnings[1].contains(bar)).toBe(true);
  });

  it('sends every entry in one request, then says so and cannot be pressed again', async () => {
    const onChanged = await applyScan(scan(undefined, { ...STORED, hand_edits: TWO }));
    expect(keepAll()?.textContent).toBe('Keep all 2');
    api.carryOverAll.mockResolvedValue(KEPT_BOTH);

    fireEvent.click(keepAll()!);
    await flush();

    expect(api.carryOverAll).toHaveBeenCalledTimes(1);
    expect(api.carryOverAll).toHaveBeenCalledWith(7, [LINE, BAR]);
    expect(api.carryOver).not.toHaveBeenCalled();
    expect(screen.getByText(/Kept 2 of 2 from the last scan/)).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(2);
    expect(keepAll()?.textContent).toBe('Kept all');
    expect(keepAll()?.disabled).toBe(true);
    expect(buttons().map((b) => b.textContent)).toEqual([
      'Kept Front truss on Overhead line 1', 'Kept The bar on Booth or counter',
    ]);
  });

  it('sends only the ones not yet kept one at a time', async () => {
    await applyScan(scan(undefined, { ...STORED, hand_edits: TWO }));
    api.carryOver.mockResolvedValue({ rig_id: 7, kind: 'truss_lines', index: 0, changed: true, message: 'Kept one.' });
    fireEvent.click(buttons()[0]);
    await flush();
    expect(keepAll()?.textContent).toBe('Keep all 1');
    api.carryOverAll.mockResolvedValue({ ...KEPT_BOTH, carried: [KEPT_BOTH.carried[1]] });

    fireEvent.click(keepAll()!);
    await flush();

    expect(api.carryOverAll).toHaveBeenCalledWith(7, [BAR]);
  });

  it('shows the refusal and leaves every button to try again: all or none', async () => {
    await applyScan(scan(undefined, { ...STORED, hand_edits: TWO }));
    const stale = 'The room has changed since the scan was applied.';
    api.carryOverAll.mockRejectedValue(Object.assign(new Error('409'), {
      isAxiosError: true, response: { status: 409, data: { detail: stale } },
    }));

    fireEvent.click(keepAll()!);
    await flush();

    expect(screen.getByText(stale)).toBeTruthy();
    expect(keepAll()?.disabled).toBe(false);
    expect(buttons().every((b) => !(b as HTMLButtonElement).disabled)).toBe(true);
  });

  it('is not shown for a single entry', async () => {
    await applyScan(scan(undefined, { ...STORED, hand_edits: { ...TWO, carry_over: [LINE] } }));
    expect(buttons()).toHaveLength(1);
    expect(keepAll()).toBeNull();
  });
});

describe('the Room Scan dialog opened again', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  const PENDING = [{ ...LINE, message: RETRIM }, { ...BAR, message: BESIDE }];

  it('shows the buttons kept with the stored room, each with its sentence, and "Keep all"', async () => {
    render(
      <RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} pendingCarryOver={PENDING} />,
    );
    const shown = screen.getAllByTestId('room-scan-pending-warning');
    expect(shown).toHaveLength(2);
    expect(shown[0].textContent).toContain(RETRIM);
    expect(shown[1].textContent).toContain(BESIDE);
    expect(buttons().map((b) => b.textContent)).toEqual(['Keep Front truss on this one', 'Keep The bar on this one']);
    expect(shown[0].contains(buttons()[0])).toBe(true);
    expect(keepAll()?.textContent).toBe('Keep all 2');
    // Nothing was asked of the server to show them: they came with the rig.
    expect(api.preview).not.toHaveBeenCalled();
  });

  it('sends one stored entry as it is, and all of them with "Keep all"', async () => {
    const onChanged = vi.fn();
    render(
      <RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={onChanged} pendingCarryOver={PENDING} />,
    );
    api.carryOver.mockResolvedValue({ rig_id: 7, kind: 'risers', index: 1, changed: true, message: 'Kept the bar.' });
    fireEvent.click(buttons()[1]);
    await flush();
    expect(api.carryOver).toHaveBeenCalledWith(7, PENDING[1]);
    expect(onChanged).toHaveBeenCalledTimes(1);

    api.carryOverAll.mockResolvedValue(KEPT_BOTH);
    fireEvent.click(keepAll()!);
    await flush();
    expect(api.carryOverAll).toHaveBeenCalledWith(7, [PENDING[0]]);
  });

  it('shows nothing of it with none stored, or once a scan file is chosen', async () => {
    render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.queryByTestId('room-scan-pending-carry-over')).toBeNull();
    cleanup();

    api.preview.mockResolvedValue(scan(TWO));
    render(
      <RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} pendingCarryOver={PENDING} />,
    );
    expect(screen.getByTestId('room-scan-pending-carry-over')).toBeTruthy();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
    await flush();
    expect(screen.queryByTestId('room-scan-pending-carry-over')).toBeNull();
    // A preview has no buttons: nothing is stored to put them on.
    expect(buttons()).toEqual([]);
  });
});

describe('the slice 37 helpers', () => {
  it('reads the list kept with the stored room, passing over what is not an entry', () => {
    expect(pendingCarryOverOf({ pending_carry_over: [LINE, null, { ...BAR, new_index: '1' }, BAR] })).toEqual([LINE, BAR]);
    expect(pendingCarryOverOf({})).toEqual([]);
    expect(pendingCarryOverOf(null)).toEqual([]);
    expect(pendingCarryOverOf({ pending_carry_over: 'x' })).toEqual([]);
  });

  it('keys an entry by its warning id, or by its item without one', () => {
    expect(carryOverKey(LINE)).toBe('lost-0');
    expect(carryOverKey({ ...LINE, warning_id: undefined })).toBe('truss_lines:0:Front truss');
  });

  it('gives each warning its id and the server\'s place', () => {
    const entries = handEditWarningEntries(scan(TWO));
    expect(entries.map((w) => [w.id, w.place])).toEqual([['lost-0', 1], ['lost-1', 2]]);
  });

  it('words the button and names the route', () => {
    expect(keepAllButtonText(3)).toBe('Keep all 3');
    expect(roomScanCarryOverAllPath(7)).toBe('/rigs/7/room-scan/carry-over/all');
  });
});
