// After a scan applied again, each warning of what was lost that has an item of
// the new room behind it gets a "Keep <old name> on this one" button, which sends
// that `hand_edits.carry_over` entry as it is to POST /room-scan/carry-over
// (docs/ROOM_SCAN.md, slice 36).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import { carryOverButtonText, handEditCarryOver, roomScanCarryOverPath } from '../utils/roomScan';
import type { RoomScanCarryOver, RoomScanHandEdits, RoomScanPreview } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn(), carryOver: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const NOTHING = { areas: 0, kept: [], added_kept: [], added_replaced: [] };
const RETRIM = 'The scan read a truss at 2.8 m where Front truss was, against its trim of 3.5 m '
  + '(the scan read it at 4 m before): more than 1 m from where the scan read it before, '
  + 'so its name and trim were not kept.';
const ENTRY: RoomScanCarryOver = {
  kind: 'truss_lines', old_name: 'Front truss', old_trim_or_height: 3.5, edits: ['name', 'height'],
  new_index: 0, new_name: 'Overhead line 1', reason: 'hanging height', warning: 0,
};
const LOST: RoomScanHandEdits = {
  ...NOTHING,
  warnings: [{ kind: 'truss_lines', name: 'Front truss', reason: 'hanging height', message: RETRIM }],
  carry_over: [ENTRY],
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

/** Opens the dialog, chooses a file and applies it, so the applied answer given is on screen. */
async function applyScan(answer: RoomScanPreview, onChanged = vi.fn()) {
  api.preview.mockResolvedValue(scan(LOST));
  api.apply.mockResolvedValue(answer);
  render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={onChanged} />);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
  await flush();
  fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
  await flush();
  expect(api.apply).toHaveBeenCalledTimes(1);
  return onChanged;
}

const buttons = () => screen.queryAllByTestId('room-scan-carry-over');

describe('the "Keep <old name> on this one" button in the Room Scan dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('is not shown before Apply: nothing is stored to put it on', async () => {
    api.preview.mockResolvedValue(scan(LOST));
    render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
    await flush();
    expect(screen.getAllByTestId('room-scan-hand-edit-warning')).toHaveLength(1);
    expect(buttons()).toEqual([]);
  });

  it('sits in its warning after Apply and sends the entry as it is, then says what was done', async () => {
    const onChanged = await applyScan(scan(undefined, { ...STORED, hand_edits: LOST }));
    const [button] = buttons();
    expect(button.textContent).toBe('Keep Front truss on this one');
    expect(screen.getByTestId('room-scan-hand-edit-warning').contains(button)).toBe(true);
    api.carryOver.mockResolvedValue({
      rig_id: 7, kind: 'truss_lines', index: 0, changed: true,
      message: 'Overhead line 1 given the name and trim of Front truss. No fixture was hung on it.',
    });

    fireEvent.click(button);
    await flush();

    expect(api.carryOver).toHaveBeenCalledTimes(1);
    expect(api.carryOver).toHaveBeenCalledWith(7, ENTRY);
    expect(screen.getByText(/given the name and trim of Front truss/)).toBeTruthy();
    // The rig changed: once for the apply, once for the carry-over.
    expect(onChanged).toHaveBeenCalledTimes(2);
    // Done once: the button says so and cannot be pressed again.
    expect(buttons()[0].textContent).toBe('Kept Front truss on Overhead line 1');
    expect((buttons()[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows the server\'s words where the room has changed since, and can be tried again', async () => {
    await applyScan(scan(undefined, { ...STORED, hand_edits: LOST }));
    const stale = 'The room has changed since the scan was applied: overhead line 0 is not Overhead line 1 any more.';
    api.carryOver.mockRejectedValue(Object.assign(new Error('409'), {
      isAxiosError: true, response: { status: 409, data: { detail: stale } },
    }));

    fireEvent.click(buttons()[0]);
    await flush();

    expect(screen.getByText(stale)).toBeTruthy();
    expect((buttons()[0] as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('handEditCarryOver and its path', () => {
  it('reads the applied answer only, and passes over an entry that is not one', () => {
    expect(handEditCarryOver(scan(LOST))).toEqual([]);
    expect(handEditCarryOver(scan(undefined, { ...STORED, hand_edits: LOST }))).toEqual([ENTRY]);
    const odd = [null, { ...ENTRY, old_name: '' }, { ...ENTRY, new_index: '0' }, ENTRY];
    expect(handEditCarryOver(scan(undefined, {
      ...STORED, hand_edits: { ...NOTHING, carry_over: odd as unknown as RoomScanCarryOver[] },
    }))).toEqual([ENTRY]);
    expect(handEditCarryOver(null)).toEqual([]);
  });

  it('words the button and names the route', () => {
    expect(carryOverButtonText(ENTRY)).toBe('Keep Front truss on this one');
    expect(roomScanCarryOverPath(7)).toBe('/rigs/7/room-scan/carry-over');
  });
});
