// A scan previewed over a room with a marked DJ booth: the Room Scan dialog says
// before Apply whether the mark will be kept, and on which raised area, or
// dropped (docs/ROOM_SCAN.md, slice 31).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import { DJ_BOOTH_WILL_DROP_TEXT, djBoothPreviewLine } from '../utils/roomScan';
import type { RoomScanPreview } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
  // The dialog asks which video tools the server has when it opens; no answer keeps that section quiet.
  roomVideoApi: { tools: () => new Promise(() => {}), stop: () => Promise.resolve() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

type Mark = NonNullable<RoomScanPreview['dj_booth_mark']>;

const KEPT: Mark = {
  kept: true, dropped: false, index: 1, name: 'Riser', overlap: 0.91, kind_kept: null,
  message: 'The DJ booth mark will be kept on Riser.',
};
const DROPPED: Mark = {
  kept: false, dropped: true, index: null, name: null, overlap: null, kind_kept: null,
  message: 'The DJ booth mark will be dropped: no raised area in this scan stands where DJ does.',
};

function scan(mark?: Mark | null, applied: RoomScanPreview['applied'] = null): RoomScanPreview {
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
    ...(mark === undefined ? {} : { dj_booth_mark: mark }),
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

const line = () => screen.queryByTestId('room-scan-dj-booth-preview');

describe('the DJ booth mark in the Room Scan preview', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('says on which raised area the mark will be kept, and not as a warning', async () => {
    await previewScan(scan(KEPT));
    expect(line()?.textContent).toBe('DJ booth mark: kept on Riser');
    expect(line()?.getAttribute('role')).toBeNull();
    expect(line()?.closest('[role="alert"]')).toBeNull();
  });

  it('warns that the mark will be dropped', async () => {
    await previewScan(scan(DROPPED));
    expect(line()?.textContent).toBe('DJ booth mark will be dropped');
    expect(line()?.getAttribute('role')).toBe('alert');
    expect(line()?.className).toMatch(/Warning/i);
  });

  it('says a kind set by hand stays what it was made', async () => {
    await previewScan(scan({ ...KEPT, name: 'Booth or counter', kind_kept: 'booth' }));
    expect(line()?.textContent).toBe('DJ booth mark: kept on Booth or counter (stays a booth, as set by hand)');
  });

  it('says nothing where the stored room has no marked booth', async () => {
    await previewScan(scan());
    expect(line()).toBeNull();
    expect(screen.queryByText(/DJ booth/)).toBeNull();
  });

  it('is gone once the scan is applied: the answer speaks for itself then', async () => {
    await previewScan(scan(KEPT));
    expect(line()).not.toBeNull();
    api.apply.mockResolvedValue(scan(undefined, {
      room_shell_stored: true, fixtures_moved: 0, fixtures_still_unconfirmed: 0, message: 'The room is stored.',
      dj_booth: 1, dj_booth_dropped: false,
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(line()).toBeNull();
  });
});

describe('djBoothPreviewLine', () => {
  it('is the kept line with the name the server gives, or the place where it gives none', () => {
    expect(djBoothPreviewLine(scan(KEPT))).toEqual({ text: 'DJ booth mark: kept on Riser', dropped: false });
    expect(djBoothPreviewLine(scan({ ...KEPT, name: '  ' }))?.text).toBe('DJ booth mark: kept on raised area 2');
    expect(djBoothPreviewLine(scan({ ...KEPT, name: null, index: null }))?.text)
      .toBe('DJ booth mark: kept on the same raised area');
  });

  it('is the dropped warning', () => {
    expect(djBoothPreviewLine(scan(DROPPED))).toEqual({ text: DJ_BOOTH_WILL_DROP_TEXT, dropped: true });
    expect(DJ_BOOTH_WILL_DROP_TEXT).toBe('DJ booth mark will be dropped');
  });

  it('is nothing with no mark, no preview, an applied answer, or an answer that says neither', () => {
    expect(djBoothPreviewLine(scan())).toBeNull();
    expect(djBoothPreviewLine(scan(null))).toBeNull();
    expect(djBoothPreviewLine(null)).toBeNull();
    expect(djBoothPreviewLine(undefined)).toBeNull();
    expect(djBoothPreviewLine(scan(KEPT, {
      room_shell_stored: true, fixtures_moved: 0, fixtures_still_unconfirmed: 0, message: 'Stored.',
    }))).toBeNull();
    expect(djBoothPreviewLine(scan({ ...KEPT, kept: false, dropped: false }))).toBeNull();
  });
});
