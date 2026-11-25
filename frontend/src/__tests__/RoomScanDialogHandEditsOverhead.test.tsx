// A scan applied again also keeps a name and a hanging height set by hand on an
// overhead line or ring, leaves out a raised area deleted by hand, and flags
// what the new room does not hold. The Room Scan dialog's one line counts
// those too (docs/ROOM_SCAN.md, slice 33).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import { handEditsLine } from '../utils/roomScan';
import type { RoomScanHandEdits, RoomScanPreview } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const NOTHING = { areas: 0, kept: [], added_kept: [], added_replaced: [] };

const LINE_KEPT: RoomScanHandEdits = {
  ...NOTHING,
  overhead_kept: [{ kind: 'truss_lines', index: 0, name: 'Front truss', edits: ['name', 'height'], overlap: 1 }],
};
const LEFT_OUT: RoomScanHandEdits = {
  ...NOTHING,
  deleted_left_out: [{ name: 'Riser', kind: 'riser', overlap: 1 }],
};
const EVERYTHING: RoomScanHandEdits = {
  areas: 2,
  kept: [
    { index: 0, name: 'Main stage', edits: ['name'] },
    { index: 1, name: 'Drum riser', edits: ['height'] },
  ],
  added_kept: [{ index: 2, name: 'Podium' }],
  added_replaced: [],
  overhead_kept: [{ kind: 'truss_rings', index: 0, name: 'Halo', edits: ['height'] }],
  overhead_added_kept: [
    { kind: 'truss_lines', index: 1, name: 'Front pipe' },
    { kind: 'truss_lines', index: 2, name: 'Back pipe' },
  ],
  overhead_added_replaced: [{ kind: 'truss_lines', name: 'Side pipe', by_index: 0, by: 'Overhead line 1' }],
  deleted_left_out: [{ name: 'Riser' }, { name: 'Booth or counter' }],
  warnings: [{ kind: 'truss_lines', index: 2, name: 'Back pipe', reason: 'above the ceiling' }],
};
const TO_CHECK: RoomScanHandEdits = {
  ...NOTHING,
  added_kept: [{ index: 2, name: 'Podium' }],
  warnings: [{ kind: 'risers', index: 2, name: 'Podium', reason: 'outside the walls' }],
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

/** Opens the dialog on a rig that has a room and chooses a file, so the preview given is on screen. */
async function previewScan(preview: RoomScanPreview) {
  api.preview.mockResolvedValue(preview);
  render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} />);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).toBeTruthy();
  fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
  await flush();
  expect(api.preview).toHaveBeenCalledTimes(1);
}

const line = () => screen.queryByTestId('room-scan-hand-edits');

describe('overhead lines, deleted areas and checks in the Room Scan line', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('counts an overhead line whose edits will be kept, and not as a warning', async () => {
    await previewScan(scan(LINE_KEPT));
    expect(line()?.textContent).toBe('Will keep your edits on 1 overhead item');
    expect(line()?.closest('[role="alert"]')).toBeNull();
  });

  it('says a raised area deleted by hand will be left out, and not as a warning', async () => {
    await previewScan(scan(LEFT_OUT));
    expect(line()?.textContent).toBe('Will leave out 1 area you deleted');
    expect(line()?.closest('[role="alert"]')).toBeNull();
  });

  it('warns where something kept is to be checked against the new room', async () => {
    await previewScan(scan(TO_CHECK));
    expect(line()?.textContent).toBe('1 area you added will be kept; 1 to check against the new room');
    expect(line()?.getAttribute('role')).toBe('alert');
  });

  it('says what was left out and kept once the scan is applied', async () => {
    await previewScan(scan(EVERYTHING));
    api.apply.mockResolvedValue(scan(undefined, { ...STORED, hand_edits: EVERYTHING }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(line()?.textContent).toBe(
      'Left out 2 areas you deleted; kept your edits on 2 areas and 1 overhead item; '
      + '1 area and 2 overhead items you added kept; 1 overhead item you added replaced by the scan; '
      + '1 to check against the new room',
    );
    expect(line()?.getAttribute('role')).toBe('alert');
  });
});

describe('handEditsLine with the slice 33 keys', () => {
  it('counts areas and overhead items together, before Apply', () => {
    expect(handEditsLine(scan(EVERYTHING))).toEqual({
      text:
        'Will leave out 2 areas you deleted; will keep your edits on 2 areas and 1 overhead item; '
        + '1 area and 2 overhead items you added will be kept; '
        + '1 overhead item you added will be replaced by the scan; 1 to check against the new room',
      replaced: true,
    });
  });

  it('is a plain line for kept overhead items and a left-out area, and a warning for one replaced', () => {
    expect(handEditsLine(scan(LINE_KEPT))?.replaced).toBe(false);
    expect(handEditsLine(scan(LEFT_OUT))?.replaced).toBe(false);
    expect(handEditsLine(scan({
      ...NOTHING,
      overhead_added_replaced: [{ kind: 'truss_rings', name: 'Halo', by_index: 0, by: 'Overhead ring 1' }],
    }))).toEqual({ text: '1 overhead item you added will be replaced by the scan', replaced: true });
  });

  it('is nothing where the new lists are all empty', () => {
    expect(handEditsLine(scan({
      ...NOTHING, overhead_kept: [], overhead_added_kept: [], overhead_added_replaced: [],
      deleted_left_out: [], warnings: [],
    }))).toBeNull();
  });
});
