// A scan applied again over a room with a marked DJ booth: the Room Scan dialog
// says so when the mark was dropped, and says nothing when it was kept or the
// room had none (docs/ROOM_SCAN.md, slice 30).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import { DJ_BOOTH_DROPPED_TEXT, djBoothDroppedText } from '../utils/roomScan';
import type { RoomScanPreview } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
  // The dialog asks which video tools the server has when it opens; no answer keeps that section quiet.
  roomVideoApi: { tools: () => new Promise(() => {}), stop: () => Promise.resolve() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

type Applied = NonNullable<RoomScanPreview['applied']>;

const STORED: Applied = {
  room_shell_stored: true, fixtures_moved: 0, fixtures_still_unconfirmed: 0, message: 'The room is stored.',
};
const SERVER_SENTENCE =
  'The DJ booth mark was dropped: no raised area in this scan stands where DJ did. '
  + 'Mark the DJ booth again in Edit Room.';

function scan(applied: RoomScanPreview['applied'] = null): RoomScanPreview {
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
    applied,
  };
}

/** Opens the dialog on a rig that has a room, chooses a file, and applies it with the answer given. */
async function applyScan(applied: Applied) {
  api.preview.mockResolvedValue(scan());
  api.apply.mockResolvedValue(scan(applied));
  render(<RoomScanDialog open rigId={7} rigName="Club" hasRoom onClose={vi.fn()} onChanged={vi.fn()} />);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).toBeTruthy();
  fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
  await flush();
  // A preview says nothing of the mark: nothing has been stored.
  expect(screen.queryByTestId('room-scan-dj-booth-dropped')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
  await flush();
  expect(api.apply).toHaveBeenCalledTimes(1);
}

const dropped = () => screen.queryByTestId('room-scan-dj-booth-dropped');

describe('the dropped DJ booth mark in the Room Scan dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('says the mark was dropped, in the server sentence, beside the stored message', async () => {
    await applyScan({
      ...STORED, dj_booth: null, dj_booth_dropped: true, dj_booth_overlap: null, dj_booth_message: SERVER_SENTENCE,
    });
    expect(dropped()?.textContent).toBe(SERVER_SENTENCE);
    // The message that was always shown is still there, and is not the warning.
    expect(screen.getByText('The room is stored.')).toBeTruthy();
    expect(screen.getAllByText(SERVER_SENTENCE)).toHaveLength(1);
  });

  it('has its own words where the server sends no sentence', async () => {
    await applyScan({ ...STORED, dj_booth: null, dj_booth_dropped: true });
    expect(dropped()?.textContent).toBe(DJ_BOOTH_DROPPED_TEXT);
  });

  it('says nothing where the mark was kept', async () => {
    await applyScan({
      ...STORED, dj_booth: 1, dj_booth_dropped: false, dj_booth_overlap: 0.91,
      dj_booth_message: 'The DJ booth mark was kept on Booth or counter.',
    });
    expect(dropped()).toBeNull();
    expect(screen.queryByText(/DJ booth/)).toBeNull();
  });

  it('says nothing where the room had no marked booth', async () => {
    await applyScan(STORED);
    expect(dropped()).toBeNull();
    expect(screen.queryByText(/DJ booth/)).toBeNull();
  });
});

describe('djBoothDroppedText', () => {
  it('is the server sentence, or the fallback, only for a mark that was dropped', () => {
    expect(djBoothDroppedText({ ...STORED, dj_booth_dropped: true, dj_booth_message: SERVER_SENTENCE })).toBe(SERVER_SENTENCE);
    expect(djBoothDroppedText({ ...STORED, dj_booth_dropped: true })).toBe(DJ_BOOTH_DROPPED_TEXT);
    expect(djBoothDroppedText({ ...STORED, dj_booth_dropped: true, dj_booth_message: '  ' })).toBe(DJ_BOOTH_DROPPED_TEXT);
    expect(djBoothDroppedText({ ...STORED, dj_booth_dropped: true, dj_booth_message: null })).toBe(DJ_BOOTH_DROPPED_TEXT);
  });

  it('is empty for a kept mark, no mark, a preview and anything that is not exactly true', () => {
    expect(djBoothDroppedText({ ...STORED, dj_booth: 2, dj_booth_dropped: false, dj_booth_message: 'Kept.' })).toBe('');
    expect(djBoothDroppedText(STORED)).toBe('');
    expect(djBoothDroppedText(null)).toBe('');
    expect(djBoothDroppedText(undefined)).toBe('');
    expect(djBoothDroppedText({ ...STORED, dj_booth_dropped: 'yes' as unknown as boolean })).toBe('');
  });
});
