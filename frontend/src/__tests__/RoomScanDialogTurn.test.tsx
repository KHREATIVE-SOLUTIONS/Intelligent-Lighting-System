// The Room Scan dialog's table of fixture moves says how far each fixture is
// turned with a stage that stands at a heading (docs/ROOM_SCAN.md, slice 29).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import RoomScanDialog from '../components/rig/RoomScanDialog';
import { roomScanApi } from '../services/api';
import type { RoomScanMove, RoomScanPreview } from '../utils/roomScan';

// Each test renders the full dialog: they pass alone, but in a full parallel run on a
// busy machine some went past the 5 s default (Nov 2026). See docs/TESTING.md.
vi.setConfig({ testTimeout: 30_000 });

vi.mock('../services/api', () => ({
  roomScanApi: { preview: vi.fn(), apply: vi.fn(), remove: vi.fn(), undoMoves: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const REASON_TURNED = 'Moved onto Stage, which stands turned 30 degrees and turned with it.';
const REASON_SQUARE = 'Moved under Overhead line 1 at 4.00 m.';

function move(id: number, turn?: number): RoomScanMove {
  return {
    rig_fixture_id: id,
    name: `Par ${id}`,
    group: turn ? 'Floor Pars' : 'Truss Spots',
    from: { x: id, y: 0, z: 0 },
    to: { x: id, y: 0.9, z: -3 },
    reason: turn ? REASON_TURNED : REASON_SQUARE,
    suggested: true,
    // The server leaves the key out where a fixture is not turned.
    ...(turn === undefined ? {} : { turn_deg: turn }),
  };
}

function scan(moves: RoomScanMove[], applied: RoomScanPreview['applied'] = null): RoomScanPreview {
  return {
    rig_id: 7,
    rig_name: 'Club',
    file: 'club.obj',
    format: 'obj',
    room_shell: { room: { width: 12, depth: 9, height: 5 }, risers: [], truss_lines: [] } as RoomScanPreview['room_shell'],
    replaces_existing_shell: false,
    summary: {
      width: 12, depth: 9, height: 5, raised_areas: 1, overhead_lines: 1,
      hanging_heights: [4], units: 'm', up_axis: 'y',
    },
    assumptions: ['Units read as m.'],
    warnings: [],
    fixtures: { total: 6, unconfirmed: moves.length, would_move: moves.length, moves },
    operator_guide: 'docs/ROOM_SCAN.md',
    applied,
  };
}

/** Opens the dialog and chooses a file, so the mocked preview is on screen. */
async function showPreview(answer: RoomScanPreview) {
  api.preview.mockResolvedValue(answer);
  render(
    <RoomScanDialog open rigId={7} rigName="Club" hasRoom={false} onClose={vi.fn()} onChanged={vi.fn()} />,
  );
  // The dialog is drawn in a portal on the body, not in the render's container.
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).toBeTruthy();
  fireEvent.change(input, { target: { files: [new File(['v 0 0 0'], 'club.obj')] } });
  await flush();
}

const headers = () => screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim());
const turnCell = (id: number) => screen.getByTestId(`room-scan-turn-${id}`).textContent?.trim();
const summary = () => screen.getByTestId('room-scan-move-summary').textContent ?? '';

describe('the Turn column of the Room Scan dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('has a Turn column between the positions and the reason', async () => {
    await showPreview(scan([move(1, 30), move(2)]));
    expect(api.preview).toHaveBeenCalledTimes(1);
    expect(headers()).toEqual(['Fixture', 'Group', 'From x, y, z to x, y, z (m)', 'Turn', 'Why']);
  });

  it('shows each move turn in its own row, and a dash for 0 or none', async () => {
    await showPreview(scan([move(1, 30), move(2, -12.5), move(3, 0), move(4)]));
    expect(turnCell(1)).toBe('30 deg');
    expect(turnCell(2)).toBe('-12.5 deg');
    expect(turnCell(3)).toBe('-');
    expect(turnCell(4)).toBe('-');
    // The cell is the fourth of its fixture's row, under the Turn header.
    const row = screen.getByText('Par 1').closest('tr') as HTMLElement;
    const cells = within(row).getAllByRole('cell').map((cell) => cell.textContent?.trim());
    expect(cells).toEqual(['Par 1', 'Floor Pars', '(1.00, 0.00, 0.00) to (1.00, 0.90, -3.00)', '30 deg', REASON_TURNED]);
    const plain = screen.getByText('Par 4').closest('tr') as HTMLElement;
    expect(within(plain).getAllByRole('cell')[3].textContent?.trim()).toBe('-');
  });

  it('says in the summary how many fixtures will be turned', async () => {
    await showPreview(scan([move(1, 30), move(2, 30), move(3, 0), move(4)]));
    expect(summary()).toContain('4 unconfirmed fixtures of 6 would be moved to agree with the scan');
    expect(summary()).toContain('2 of them will also be turned with the stage, which stands at a heading.');
    // The sentence that was always last is still there, after it.
    expect(summary()).toMatch(/stands at a heading\. Positions that were tapped, confirmed/);
  });

  it('says nothing of a turn when no fixture is turned', async () => {
    await showPreview(scan([move(1), move(2, 0)]));
    expect(turnCell(1)).toBe('-');
    expect(turnCell(2)).toBe('-');
    expect(summary()).not.toMatch(/turned/);
    expect(summary()).toBe(
      '2 unconfirmed fixtures of 6 would be moved to agree with the scan; the other 4 stay exactly where they are. '
      + 'Positions that were tapped, confirmed, measured in a file or fitted between tapped ends are never moved.',
    );
  });

  it('says all of them where every move turns', async () => {
    await showPreview(scan([move(1, 30), move(2, 30), move(3, 30)]));
    expect(summary()).toContain('All 3 will also be turned with the stage, which stands at a heading.');
  });

  it('keeps the column once applied, and says how many were turned', async () => {
    const moves = [move(1, 30), move(2, 30), move(3)];
    await showPreview(scan(moves));
    api.apply.mockResolvedValue(scan(moves, {
      room_shell_stored: true, fixtures_moved: 3, fixtures_still_unconfirmed: 3, message: 'Stored.',
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room and move 3 fixtures' }));
    await flush();
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(api.apply.mock.calls[0][3]).toBe(true);
    expect(turnCell(1)).toBe('30 deg');
    expect(turnCell(3)).toBe('-');
    expect(summary()).toContain('3 moved.');
    expect(summary()).toContain('2 of them were also turned with the stage, which stands at a heading.');
    expect(summary()).not.toMatch(/will also be turned/);
  });

  it('does not say fixtures were turned when only the room was stored', async () => {
    const moves = [move(1, 30), move(2, 30)];
    await showPreview(scan(moves));
    api.apply.mockResolvedValue(scan(moves, {
      room_shell_stored: true, fixtures_moved: 0, fixtures_still_unconfirmed: 2, message: 'Stored.',
    }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Store the room' }));
    await flush();
    expect(api.apply.mock.calls[0][3]).toBe(false);
    expect(summary()).toContain('0 moved.');
    expect(summary()).not.toMatch(/turned/);
    // No fixture moved, so there is no table of moves and no turn in it.
    expect(screen.queryByTestId('room-scan-turn-1')).toBeNull();
  });
});
