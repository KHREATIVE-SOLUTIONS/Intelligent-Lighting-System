import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomScanUndoButton, { undoErrorText } from '../components/rig/RoomScanUndoButton';
import { roomScanApi } from '../services/api';
import {
  removeResultText,
  roomScanUndoPath,
  fixturePositionPath,
  skippedText,
  undoButtonText,
  undoCount,
  undoResultText,
} from '../utils/roomScan';
import type { RoomScanUndoResult } from '../utils/roomScan';

vi.mock('../services/api', () => ({
  roomScanApi: { undoMoves: vi.fn() },
}));

const api = vi.mocked(roomScanApi);
const flush = () => act(async () => {});

const point = { x: 0, y: 4, z: 0 };
const result: RoomScanUndoResult = {
  rig_id: 7,
  restored: 2,
  skipped: 1,
  restored_fixtures: [
    { rig_fixture_id: 1, name: 'Spot 1', from: point, to: point },
    { rig_fixture_id: 2, name: 'Spot 2', from: point, to: point },
  ],
  skipped_fixtures: [{ rig_fixture_id: 3, name: 'Par 3', reason: 'it was dragged into place since' }],
  message: '2 fixtures were put back where they stood before the scan.',
};

describe('RoomScanUndoButton', () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);

  it('draws nothing when the rig has no moves to undo', () => {
    const { container } = render(<RoomScanUndoButton rigId={7} moves={0} onDone={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('asks before it does anything', () => {
    render(<RoomScanUndoButton rigId={7} moves={3} onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: undoButtonText(3) }));
    expect(api.undoMoves).not.toHaveBeenCalled();
    expect(screen.getByText(/Put the 3 fixtures the room scan moved back/)).toBeTruthy();
    // Cancel takes the question away again, still without a request.
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.undoMoves).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: undoButtonText(3) })).toBeTruthy();
  });

  it('undoes on the backend and hands the answer on, skipped fixtures included', async () => {
    api.undoMoves.mockResolvedValue(result);
    const onDone = vi.fn();
    const onBefore = vi.fn();
    render(<RoomScanUndoButton rigId={7} moves={3} onBefore={onBefore} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: undoButtonText(3) }));
    fireEvent.click(screen.getByRole('button', { name: 'Put them back' }));
    await flush();
    expect(onBefore).toHaveBeenCalledTimes(1);
    expect(api.undoMoves).toHaveBeenCalledTimes(1);
    expect(api.undoMoves).toHaveBeenCalledWith(7);
    expect(onDone).toHaveBeenCalledWith(result);
    // What the caller shows names the fixture the undo left alone, and why.
    const shown = undoResultText(onDone.mock.calls[0][0]);
    expect(shown).toContain('2 fixtures were put back');
    expect(shown).toContain('Left alone: Par 3 (it was dragged into place since).');
  });

  it('says why an undo was refused and offers another go', async () => {
    api.undoMoves.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: {} } });
    const onDone = vi.fn();
    const onError = vi.fn();
    render(<RoomScanUndoButton rigId={7} moves={1} onDone={onDone} onError={onError} />);
    fireEvent.click(screen.getByRole('button', { name: undoButtonText(1) }));
    fireEvent.click(screen.getByRole('button', { name: 'Put them back' }));
    await flush();
    expect(onDone).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('locate walkthrough'));
    expect(screen.getByText(/locate walkthrough is running/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });
});

describe('undo wording and paths', () => {
  it('uses the server detail when there is one', () => {
    expect(undoErrorText({ isAxiosError: true, response: { status: 400, data: { detail: 'No.' } } })).toBe('No.');
    expect(undoErrorText(new Error('x'))).toMatch(/could not be reached/);
  });

  it('counts the moves in the undo record', () => {
    expect(undoCount(null)).toBe(0);
    expect(undoCount({ room_scan_undo: null })).toBe(0);
    expect(undoCount({ room_scan_undo: { moves: [{}, {}] } })).toBe(2);
  });

  it('names the routes', () => {
    expect(roomScanUndoPath(7)).toBe('/rigs/7/room-scan/undo');
    expect(fixturePositionPath(7, 12)).toBe('/rigs/7/fixtures/12/position');
  });

  it('lists at most six skipped fixtures and counts the rest', () => {
    expect(skippedText([])).toBe('');
    const many = Array.from({ length: 8 }, (_, i) => ({ rig_fixture_id: i, name: `F${i}`, reason: 'moved' }));
    expect(skippedText(many)).toMatch(/F5 \(moved\); and 2 more\.$/);
  });

  it('says what removing the room did to the fixtures', () => {
    expect(removeResultText({ rig_id: 1, removed: true, undo_available: 2 })).toMatch(/still puts them back/);
    expect(removeResultText({ rig_id: 1, removed: true })).toMatch(/left where they are\.$/);
    expect(removeResultText({
      rig_id: 1, removed: true, fixtures_restored: 1, message: '1 put back.',
      skipped_fixtures: [{ rig_fixture_id: 3, name: 'Par 3', reason: 'tapped' }],
    })).toBe('The stored room was taken off this rig. 1 put back. Left alone: Par 3 (tapped).');
  });
});
