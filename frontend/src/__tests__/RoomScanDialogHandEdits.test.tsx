// A scan previewed over a room a person has corrected in Edit Room: the Room
// Scan dialog says in one line what will be kept of those edits, and after
// Apply what was (docs/ROOM_SCAN.md, slice 32).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import { handEditsLine } from '../utils/roomScan';
import type { RoomScanHandEdits, RoomScanPreview } from '../utils/roomScan';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const KEPT: RoomScanHandEdits = {
  areas: 2,
  kept: [
    { index: 0, name: 'Main stage', edits: ['name'], overlap: 1 },
    { index: 1, name: 'Drum riser', edits: ['name', 'height'], overlap: 0.92 },
  ],
  added_kept: [],
  added_replaced: [],
  message: 'Will keep your edits on 2 raised areas: Main stage (name), Drum riser (name, height).',
};
const ADDED: RoomScanHandEdits = {
  areas: 0, kept: [], added_kept: [{ index: 2, name: 'Podium' }], added_replaced: [],
};
const REPLACED: RoomScanHandEdits = {
  areas: 1,
  kept: [{ index: 0, name: 'Main stage', edits: ['name'] }],
  added_kept: [{ index: 2, name: 'Podium' }],
  added_replaced: [{ name: 'Bar top', by_index: 1, by: 'Riser' }],
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
  expect(api.apply).not.toHaveBeenCalled();
}

const line = () => screen.queryByTestId('room-scan-hand-edits');

describe('kept hand edits in the Room Scan preview', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('says on how many areas the edits will be kept, and not as a warning', async () => {
    await previewScan(scan(KEPT));
    expect(line()?.textContent).toBe('Will keep your edits on 2 areas');
    expect(line()?.closest('[role="alert"]')).toBeNull();
  });

  it('says an area added by hand will be kept', async () => {
    await previewScan(scan(ADDED));
    expect(line()?.textContent).toBe('1 area you added will be kept');
    expect(line()?.closest('[role="alert"]')).toBeNull();
  });

  it('warns where the scan replaces an area added by hand', async () => {
    await previewScan(scan(REPLACED));
    expect(line()?.textContent).toBe(
      'Will keep your edits on 1 area; 1 area you added will be kept; 1 area you added will be replaced by the scan',
    );
    expect(line()?.getAttribute('role')).toBe('alert');
  });

  it('says nothing where the server sent nothing', async () => {
    await previewScan(scan());
    expect(line()).toBeNull();
    expect(screen.queryByText(/your edits/i)).toBeNull();
  });

  it('says what was kept once the scan is applied', async () => {
    await previewScan(scan(KEPT));
    api.apply.mockResolvedValue(scan(undefined, { ...STORED, hand_edits: KEPT }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(line()?.textContent).toBe('Kept your edits on 2 areas');
  });
});

describe('handEditsLine', () => {
  it('counts the areas the server lists, before Apply and after it', () => {
    expect(handEditsLine(scan(KEPT))).toEqual({ text: 'Will keep your edits on 2 areas', replaced: false });
    expect(handEditsLine(scan(undefined, { ...STORED, hand_edits: REPLACED }))).toEqual({
      text: 'Kept your edits on 1 area; 1 area you added kept; 1 area you added replaced by the scan',
      replaced: true,
    });
  });

  it('reads the applied answer once there is one, not the preview beside it', () => {
    expect(handEditsLine(scan(KEPT, STORED))).toBeNull();
  });

  it('is nothing with no answer, nothing sent, or lists that are all empty', () => {
    expect(handEditsLine(null)).toBeNull();
    expect(handEditsLine(undefined)).toBeNull();
    expect(handEditsLine(scan())).toBeNull();
    expect(handEditsLine(scan(null))).toBeNull();
    expect(handEditsLine(scan({ areas: 0, kept: [], added_kept: [], added_replaced: [] }))).toBeNull();
    expect(handEditsLine(scan({}))).toBeNull();
  });
});
