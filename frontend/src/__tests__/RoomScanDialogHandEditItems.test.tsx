// A scan applied again says by name what it kept, left out and lost. Under the
// Room Scan dialog's one line of counts is the list of each thing and what
// happened to it (the first five, until "Show all"), and each warning of
// `hand_edits` is shown as the scan's own warnings are (docs/ROOM_SCAN.md,
// slice 35).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import {
  HAND_EDIT_ITEMS_SHOWN, handEditItems, handEditItemText, handEditWarnings, handEditsLine,
} from '../utils/roomScan';
import type { RoomScanHandEditItem, RoomScanHandEdits, RoomScanPreview } from '../utils/roomScan';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const NOTHING = { areas: 0, kept: [], added_kept: [], added_replaced: [] };

const KEPT = 'kept your edits';
const LEFT_OUT = 'left out (you deleted it)';
const REPLACED = 'replaced (a scanned item overlaps it)';
const ADDED = 'added by hand, kept';

const FOUR: RoomScanHandEditItem[] = [
  { kind: 'raised area', name: 'Riser', outcome: LEFT_OUT },
  { kind: 'line', name: 'Front truss', outcome: KEPT },
  { kind: 'ring', name: 'Halo', outcome: ADDED },
  { kind: 'line', name: 'Side pipe', outcome: REPLACED },
];
const FOUR_TEXT = [
  'Riser (raised area): left out (you deleted it)',
  'Front truss (line): kept your edits',
  'Halo (ring): added by hand, kept',
  'Side pipe (line): replaced (a scanned item overlaps it)',
];
const SEVEN: RoomScanHandEditItem[] = [
  ...FOUR,
  { kind: 'raised area', name: 'Podium', outcome: ADDED },
  { kind: 'line', name: 'Back truss', outcome: KEPT },
  // The same name and outcome twice: both are listed.
  { kind: 'line', name: 'Back truss', outcome: KEPT },
];

const RETRIM = 'The scan read a truss at 2.8 m where Front truss was, against its trim of 3.5 m '
  + '(the scan read it at 4 m before): more than 1 m from where the scan read it before, '
  + 'so its name and trim will not be kept.';
const DROPPED = 'The scan did not see Riser; the record that keeps it deleted will be dropped, '
  + 'so it may come back on a later scan.';

const LISTED: RoomScanHandEdits = {
  ...NOTHING,
  overhead_kept: [{ kind: 'truss_lines', index: 0, name: 'Front truss', edits: ['name'], overlap: 1 }],
  overhead_added_kept: [{ kind: 'truss_rings', index: 0, name: 'Halo' }],
  overhead_added_replaced: [{ kind: 'truss_lines', name: 'Side pipe', by_index: 0, by: 'Front truss' }],
  deleted_left_out: [{ name: 'Riser', kind: 'riser', overlap: 1 }],
  items: FOUR,
};
const LOST: RoomScanHandEdits = {
  ...NOTHING,
  warnings: [
    {
      kind: 'truss_lines', name: 'Front truss', reason: 'hanging height', edits: ['name', 'height'],
      read_height: 2.8, trim: 3.5, scan_height: 4, message: RETRIM,
    },
    { kind: 'risers', name: 'Riser', reason: 'record dropped', message: DROPPED },
  ],
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
const list = () => screen.queryByTestId('room-scan-hand-edit-items');
const listed = () => Array.from(list()?.querySelectorAll('li') ?? []).map((item) => item.textContent);
const toggle = () => screen.queryByTestId('room-scan-hand-edit-items-toggle');
const warnings = () => screen.queryAllByTestId('room-scan-hand-edit-warning').map((alert) => alert.textContent);

describe('the list of what a scan applied again did, in the Room Scan dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('lists each thing by name under the line of counts, which is what it was', async () => {
    await previewScan(scan(LISTED));
    expect(line()?.textContent).toBe(
      'Will leave out 1 area you deleted; will keep your edits on 1 overhead item; '
      + '1 overhead item you added will be kept; 1 overhead item you added will be replaced by the scan',
    );
    expect(listed()).toEqual(FOUR_TEXT);
    // Under the line, and not part of it.
    expect(line()?.contains(list())).toBe(false);
    expect(line()!.compareDocumentPosition(list()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('has no toggle for five or fewer', async () => {
    await previewScan(scan({ ...LISTED, items: SEVEN.slice(0, HAND_EDIT_ITEMS_SHOWN) }));
    expect(listed()).toHaveLength(5);
    expect(toggle()).toBeNull();
  });

  it('shows the first five of a longer list, all of it when asked, and five again', async () => {
    await previewScan(scan({ ...LISTED, items: SEVEN }));
    expect(listed()).toEqual([...FOUR_TEXT, 'Podium (raised area): added by hand, kept']);
    expect(toggle()?.textContent).toBe('Show all 7');
    expect(toggle()?.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle()!);
    expect(listed()).toEqual([
      ...FOUR_TEXT, 'Podium (raised area): added by hand, kept',
      'Back truss (line): kept your edits', 'Back truss (line): kept your edits',
    ]);
    expect(toggle()?.textContent).toBe('Show fewer');
    expect(toggle()?.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(toggle()!);
    expect(listed()).toHaveLength(5);
    expect(toggle()?.textContent).toBe('Show all 7');
  });

  it('shows no list where the server sent none, or nothing about hand edits at all', async () => {
    await previewScan(scan({ ...LISTED, items: undefined }));
    expect(line()).not.toBeNull();
    expect(list()).toBeNull();
    cleanup();
    vi.clearAllMocks();
    await previewScan(scan());
    expect(list()).toBeNull();
    expect(warnings()).toEqual([]);
  });

  it('lists what was done once the scan is applied, still showing all of it as asked', async () => {
    await previewScan(scan({ ...LISTED, items: SEVEN }));
    fireEvent.click(toggle()!);
    expect(listed()).toHaveLength(7);
    api.apply.mockResolvedValue(scan(undefined, { ...STORED, hand_edits: { ...LISTED, items: SEVEN } }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(line()?.textContent?.startsWith('Left out 1 area you deleted')).toBe(true);
    expect(listed().slice(0, 4)).toEqual(FOUR_TEXT);
    expect(listed()).toHaveLength(7);
  });
});

describe('the warnings of hand_edits in the Room Scan dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('shows what was lost in the server\'s words, each as a warning, with no line of counts and no list', async () => {
    await previewScan(scan(LOST));
    expect(warnings()).toEqual([RETRIM, DROPPED]);
    screen.queryAllByTestId('room-scan-hand-edit-warning').forEach((alert) => {
      expect(alert.getAttribute('role')).toBe('alert');
    });
    // Nothing was kept, left out or replaced, and nothing is in the new room to check.
    expect(line()).toBeNull();
    expect(list()).toBeNull();
  });

  it('says in full what is to be checked against the new room, beside the count', async () => {
    await previewScan(scan({
      ...NOTHING,
      added_kept: [{ index: 2, name: 'Podium' }],
      items: [{ kind: 'raised area', name: 'Podium', outcome: ADDED }],
      warnings: [
        { kind: 'risers', index: 2, name: 'Podium', reason: 'outside the walls' },
        { kind: 'risers', name: 'Riser', reason: 'record dropped', message: DROPPED },
      ],
    }));
    // What was lost is not something "to check against the new room": the count is of the first only.
    expect(line()?.textContent).toBe('1 area you added will be kept; 1 to check against the new room');
    expect(line()?.getAttribute('role')).toBe('alert');
    expect(warnings()).toEqual([
      'Check Podium: it is outside the walls of the room as this scan reads it.', DROPPED,
    ]);
    expect(listed()).toEqual(['Podium (raised area): added by hand, kept']);
  });

  it('shows the warnings of the applied answer once the scan is applied', async () => {
    await previewScan(scan(LOST));
    const was = DROPPED.replace('will be dropped', 'was dropped');
    api.apply.mockResolvedValue(scan(undefined, {
      ...STORED,
      hand_edits: { ...NOTHING, warnings: [{ kind: 'risers', name: 'Riser', reason: 'record dropped', message: was }] },
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(warnings()).toEqual([was]);
  });
});

describe('handEditItems, handEditItemText and handEditWarnings', () => {
  it('reads the list of a preview, and of the applied answer once there is one', () => {
    expect(handEditItems(scan(LISTED))).toEqual(FOUR);
    expect(handEditItems(scan(LISTED, { ...STORED, hand_edits: { ...NOTHING, items: FOUR.slice(0, 1) } })))
      .toEqual(FOUR.slice(0, 1));
    expect(handEditItems(scan(LISTED, STORED))).toEqual([]);
  });

  it('is empty with no answer, no hand edits or no list, and passes over an entry with no name or outcome', () => {
    expect(handEditItems(null)).toEqual([]);
    expect(handEditItems(scan())).toEqual([]);
    expect(handEditItems(scan(null))).toEqual([]);
    expect(handEditItems(scan(NOTHING))).toEqual([]);
    const odd = [null, { kind: 'line', name: '', outcome: KEPT }, { kind: 'line', name: 'A' }, FOUR[1]];
    expect(handEditItems(scan({ ...NOTHING, items: odd as unknown as RoomScanHandEditItem[] }))).toEqual([FOUR[1]]);
  });

  it('says one thing as its name, what it is and what happened', () => {
    expect(FOUR.map(handEditItemText)).toEqual(FOUR_TEXT);
    expect(handEditItemText({ kind: '', name: 'Halo', outcome: KEPT })).toBe('Halo: kept your edits');
  });

  it('gives each warning as a sentence: the server\'s, or the check worded as the server words it', () => {
    expect(handEditWarnings(scan(LOST))).toEqual([RETRIM, DROPPED]);
    expect(handEditWarnings(scan({
      ...NOTHING,
      warnings: [{ kind: 'truss_lines', index: 2, name: 'Back pipe', reason: 'above the ceiling' }],
    }))).toEqual(['Check Back pipe: it is above the ceiling of the room as this scan reads it.']);
    expect(handEditWarnings(scan(NOTHING))).toEqual([]);
    expect(handEditWarnings(null)).toEqual([]);
  });

  it('leaves what was lost out of the count of things to check, so a line of only that is no line', () => {
    expect(handEditsLine(scan(LOST))).toBeNull();
    expect(handEditsLine(scan({
      ...LOST, warnings: [...LOST.warnings!, { kind: 'risers', index: 0, name: 'Stage', reason: 'above the ceiling' }],
    }))).toEqual({ text: '1 to check against the new room', replaced: true });
  });
});
