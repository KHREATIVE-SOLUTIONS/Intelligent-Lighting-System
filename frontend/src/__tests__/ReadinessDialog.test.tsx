// Venue readiness panel (docs/READINESS.md): every check the backend sends is shown worst first with its
// status in words (OK / Warn / Fail), not colour alone; "Select on plan" hands the check's fixture ids to
// the editor; "Make groups" asks first, then posts the auto-groups fix, tells the editor the rig changed
// and reads the checks again.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import ReadinessDialog from '../components/rig/ReadinessDialog';
import { readinessApi } from '../services/api';
import { exportSummaryText, fixturesText, headline, sortedChecks } from '../utils/readiness';
import type {
  AutoGroupsResult, ReaddressMove, ReaddressResult, ReadinessCheck, ReadinessReport,
} from '../utils/readiness';

vi.mock('../services/api', () => ({
  readinessApi: { get: vi.fn(), autoGroups: vi.fn(), readdress: vi.fn(), undoFix: vi.fn() },
}));

const api = vi.mocked(readinessApi);
// A macrotask tick: the fix awaits the post and then the second read, which one empty act may not drain.
const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

const check = (over: Partial<ReadinessCheck> & Pick<ReadinessCheck, 'id' | 'status'>): ReadinessCheck => ({
  title: over.id, message: `${over.id} message`, fixture_ids: [], fixture_count: 0, fix: null, ...over,
});

const POSITIONS = check({
  id: 'positions', title: 'Positions', status: 'ok', message: 'Every fixture has a position.',
});
const ADDRESSES = check({
  id: 'addresses', title: 'DMX addresses', status: 'fail',
  message: 'Spot 1 and Spot 2 overlap at 1.1-1.16.', fixture_ids: [11, 12], fixture_count: 2,
});
const GROUPS = check({
  id: 'groups', title: 'Groups', status: 'warn',
  message: '3 fixtures are in no group.', fixture_ids: [11, 12, 13], fixture_count: 3, fix: 'auto-groups',
});

function report(checks: ReadinessCheck[]): ReadinessReport {
  const counts = { ok: 0, warn: 0, fail: 0 };
  checks.forEach((c) => { counts[c.status] += 1; });
  const status = counts.fail ? 'fail' : counts.warn ? 'warn' : 'ok';
  return { rig_id: 7, rig_name: 'Club', status, counts, checks, operator_guide: 'docs/READINESS.md' };
}

const FIXED: AutoGroupsResult = {
  rig_id: 7,
  created: [{ name: 'Front truss Spots', fixture_ids: [11, 12, 13] }],
  skipped: [],
  unplaced_ids: [],
  changed: [11, 12, 13].map((id) => ({ id, name: `Spot ${id}`, group_before: null, group_name: 'Front truss Spots' })),
  message: 'Made 1 group for 3 fixtures.',
};

const CLASH = { ...ADDRESSES, fix: 'readdress' };
const GUESSES = check({
  id: 'positions', title: 'Positions', status: 'warn',
  message: '2 fixtures sit where we guessed.', fixture_ids: [21, 22], fixture_count: 2, fix: 'locate',
});

const MOVE: ReaddressMove = {
  id: 12, name: 'Spot 2', reason: 'overlap', clashes_with: [11], channel_count: 16, guessed: false,
  from_universe: 0, from_address: 5, to_universe: 0, to_address: 17, from_label: '1.005', to_label: '1.017',
};
const PLAN: ReaddressResult = {
  rig_id: 7, dry_run: true, moves: [MOVE], left: [], conflicts_after: 0, past_end_after: 0,
  message: 'Would move 1 fixture: Spot 2 1.005 to 1.017.',
};

beforeEach(() => {
  api.get.mockReset();
  api.autoGroups.mockReset();
  api.readdress.mockReset();
  api.undoFix.mockReset();
});
afterEach(cleanup);

describe('ReadinessDialog', () => {
  it('shows every check worst first, each with its status in words', async () => {
    api.get.mockResolvedValue(report([POSITIONS, ADDRESSES, GROUPS]));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    expect(api.get).toHaveBeenCalledWith(7);
    expect(screen.getByTestId('readiness-headline').textContent).toContain('Not ready: 1 check fails, 1 check warns');

    const rows = screen.getAllByTestId(/^readiness-check-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'readiness-check-addresses', 'readiness-check-groups', 'readiness-check-positions',
    ]);
    expect(within(rows[0]).getByText('Fail')).toBeTruthy();
    expect(within(rows[0]).getByText('Spot 1 and Spot 2 overlap at 1.1-1.16.')).toBeTruthy();
    expect(within(rows[0]).getByText('2 fixtures')).toBeTruthy();
    expect(within(rows[1]).getByText('Warn')).toBeTruthy();
    expect(within(rows[2]).getByText('OK')).toBeTruthy();
    // A check that passed names no fixtures and offers nothing to press.
    expect(within(rows[2]).queryByRole('button')).toBeNull();
  });

  it('shows the DMX modes check like any other, with no fix to press', async () => {
    const MODES = check({
      id: 'modes', title: 'DMX modes', status: 'fail',
      message: 'Spot 3 is set to mode "Basic", which its profile does not have.', fixture_ids: [13], fixture_count: 1,
    });
    api.get.mockResolvedValue(report([POSITIONS, MODES]));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    const row = screen.getByTestId('readiness-check-modes');
    expect(within(row).getByText('DMX modes')).toBeTruthy();
    expect(within(row).getByText('Fail')).toBeTruthy();
    expect(within(row).getByText(/its profile does not have/)).toBeTruthy();
    expect(within(row).queryByRole('button', { name: /Make groups|Re-address/ })).toBeNull();
  });

  it('hands the fixtures a check names to the editor', async () => {
    api.get.mockResolvedValue(report([ADDRESSES]));
    const onSelectFixtures = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onSelectFixtures={onSelectFixtures} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Select on plan' }));
    expect(onSelectFixtures).toHaveBeenCalledWith([11, 12]);
  });

  it('leaves Select on plan out when the editor gives no way to select', async () => {
    api.get.mockResolvedValue(report([ADDRESSES]));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();
    expect(screen.queryByRole('button', { name: 'Select on plan' })).toBeNull();
  });

  it('Make groups asks first, then calls the fix, says what it did and checks again', async () => {
    api.get
      .mockResolvedValueOnce(report([POSITIONS, GROUPS]))
      .mockResolvedValueOnce(report([POSITIONS, { ...GROUPS, status: 'ok', message: 'Every fixture is in a group.', fix: null }]));
    api.autoGroups.mockResolvedValue(FIXED);
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    // Nothing is written until the operator says so.
    expect(api.autoGroups).not.toHaveBeenCalled();
    expect(screen.getByText(/Undo puts them all back in one step/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Make them' }));
    await flush();

    expect(api.autoGroups).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Made 1 group for 3 fixtures.')).toBeTruthy();
    expect(screen.getByTestId('readiness-headline').textContent).toBe('Ready to program: every check passed.');
    expect(screen.queryByRole('button', { name: 'Make groups' })).toBeNull();
  });

  it('Cancel writes nothing', async () => {
    api.get.mockResolvedValue(report([GROUPS]));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.autoGroups).not.toHaveBeenCalled();
    expect(screen.queryByText(/Undo puts them all back/)).toBeNull();
  });

  it('a fix that fails says nothing was changed and does not tell the editor to reload', async () => {
    api.get.mockResolvedValue(report([GROUPS]));
    api.autoGroups.mockRejectedValue(new Error('500'));
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Make them' }));
    await flush();

    expect(screen.getByText(/Make groups did not run: nothing was changed/)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('Re-address shows the dry-run plan, moves nothing until asked, then applies and checks again', async () => {
    api.get
      .mockResolvedValueOnce(report([CLASH]))
      .mockResolvedValueOnce(report([{ ...CLASH, status: 'ok', message: 'No clashes.', fix: null, fixture_ids: [], fixture_count: 0 }]));
    api.readdress
      .mockResolvedValueOnce(PLAN)
      .mockResolvedValueOnce({ ...PLAN, dry_run: false, message: 'Moved 1 fixture: Spot 2 1.005 to 1.017.' });
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Re-address' }));
    await flush();

    expect(api.readdress).toHaveBeenCalledTimes(1);
    expect(api.readdress).toHaveBeenLastCalledWith(7, true);
    const plan = screen.getByTestId('readiness-readdress-plan');
    expect(within(plan).getByText('Spot 2: 1.005 to 1.017')).toBeTruthy();
    expect(within(plan).getByText(/on the fixture itself/)).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Move 1' }));
    await flush();

    expect(api.readdress).toHaveBeenCalledTimes(2);
    expect(api.readdress).toHaveBeenLastCalledWith(7, false);
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Moved 1 fixture: Spot 2 1.005 to 1.017.')).toBeTruthy();
    expect(screen.getByTestId('readiness-headline').textContent).toBe('Ready to program: every check passed.');
  });

  it('Re-address Cancel after the plan writes nothing', async () => {
    api.get.mockResolvedValue(report([CLASH]));
    api.readdress.mockResolvedValue(PLAN);
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Re-address' }));
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(api.readdress).toHaveBeenCalledTimes(1);
    expect(api.readdress).toHaveBeenCalledWith(7, true);
    expect(screen.queryByTestId('readiness-readdress-plan')).toBeNull();
  });

  it('a plan that moves nothing offers nothing to apply and names what was left', async () => {
    api.get.mockResolvedValue(report([CLASH]));
    api.readdress.mockResolvedValue({
      ...PLAN, moves: [], conflicts_after: 1,
      left: [{ id: 12, name: 'Spot 2', reason: 'locked', clashes_with: [11], message: 'Spot 2 has a locked address, so it was not moved.' }],
      message: 'Spot 2 has a locked address, so it was not moved.',
    });
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Re-address' }));
    await flush();

    const plan = screen.getByTestId('readiness-readdress-plan');
    expect(within(plan).getByText(/locked address/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Move/ })).toBeNull();
  });

  it('offers Undo after a fix; Undo takes it back in one step, tells the editor and checks again', async () => {
    api.get
      .mockResolvedValueOnce(report([GROUPS]))
      .mockResolvedValueOnce(report([{ ...GROUPS, status: 'ok', fix: null }]))
      .mockResolvedValueOnce(report([GROUPS]));
    api.autoGroups.mockResolvedValue({ ...FIXED, undo: { fix: 'auto-groups', label: 'Undo Make groups', count: 3 } });
    api.undoFix.mockResolvedValue({
      rig_id: 7, fix: 'auto-groups', undo: null,
      restored: [11, 12, 13].map((id) => ({ id, name: `Spot ${id}`, from: { group_name: 'Front truss Spots' }, to: { group_name: null } })),
      message: 'Undid Make groups: 3 fixtures back in no group.',
    });
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();
    // Nothing to undo before a fix.
    expect(screen.queryByTestId('readiness-undo')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Make them' }));
    await flush();
    expect(api.undoFix).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Undo Make groups' }));
    await flush();

    expect(api.undoFix).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenCalledTimes(3);
    expect(screen.getByText('Undid Make groups: 3 fixtures back in no group.')).toBeTruthy();
    expect(screen.queryByTestId('readiness-undo')).toBeNull();
    expect(screen.getByRole('button', { name: 'Make groups' })).toBeTruthy();
  });

  it('Undo refused because the rig changed since says why and does not tell the editor to reload', async () => {
    api.get.mockResolvedValue(report([CLASH]));
    api.readdress
      .mockResolvedValueOnce(PLAN)
      .mockResolvedValueOnce({
        ...PLAN, dry_run: false, message: 'Moved 1 fixture.', undo: { fix: 'readdress', label: 'Undo Re-address', count: 1 },
      });
    const refused = 'Cannot undo Re-address: 1 of the fixtures it changed has been changed or removed since (Spot 2).';
    api.undoFix.mockRejectedValue({ response: { status: 409, data: { detail: { message: refused, stale: [] } } } });
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Re-address' }));
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Move 1' }));
    await flush();
    expect(onChanged).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Undo Re-address' }));
    await flush();

    expect(screen.getByText(refused)).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('readiness-undo')).toBeNull();
  });

  it('Undo that fails for another reason says nothing changed and keeps the button to try again', async () => {
    api.get.mockResolvedValue(report([GROUPS]));
    api.autoGroups.mockResolvedValue({ ...FIXED, undo: { fix: 'auto-groups', label: 'Undo Make groups', count: 3 } });
    api.undoFix.mockRejectedValue({ response: { status: 500 } });
    const onChanged = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onChanged={onChanged} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Make them' }));
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Undo Make groups' }));
    await flush();

    expect(screen.getByText('Undo did not run: nothing was changed. Try again.')).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Undo Make groups' })).toBeTruthy();
  });

  it('a fix with no undo to offer shows no Undo button', async () => {
    api.get.mockResolvedValue(report([GROUPS]));
    api.autoGroups.mockResolvedValue({ ...FIXED, changed: [], undo: null, message: 'No group was needed.' });
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Make groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Make them' }));
    await flush();

    expect(screen.getByText('No group was needed.')).toBeTruthy();
    expect(screen.queryByTestId('readiness-undo')).toBeNull();
  });

  it('Locate these hands exactly the named fixtures to the walkthrough and writes nothing', async () => {
    api.get.mockResolvedValue(report([GUESSES]));
    const onLocate = vi.fn();
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onLocate={onLocate} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Locate these' }));
    expect(onLocate).toHaveBeenCalledWith([21, 22]);
    expect(api.readdress).not.toHaveBeenCalled();
    expect(api.autoGroups).not.toHaveBeenCalled();
  });

  it('Locate says when only the first fixtures are handed over, and is left out with no walkthrough', async () => {
    api.get.mockResolvedValue(report([{ ...GUESSES, fixture_count: 80 }]));
    const { unmount } = render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} onLocate={() => {}} />);
    await flush();
    expect(screen.getByRole('button', { name: 'Locate the first 2' })).toBeTruthy();
    unmount();

    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();
    expect(screen.queryByRole('button', { name: /^Locate/ })).toBeNull();
  });
});

describe('readiness helpers', () => {
  it('keeps the backend order within each status', () => {
    const a = check({ id: 'a', status: 'warn' });
    const b = check({ id: 'b', status: 'ok' });
    const c = check({ id: 'c', status: 'warn' });
    expect(sortedChecks([a, b, c]).map((x) => x.id)).toEqual(['a', 'c', 'b']);
  });

  it('says when the backend capped the fixture list', () => {
    expect(fixturesText(check({ id: 'x', status: 'fail', fixture_ids: [1, 2], fixture_count: 60 })))
      .toBe('60 fixtures (first 2 listed)');
    expect(fixturesText(check({ id: 'x', status: 'fail', fixture_ids: [1], fixture_count: 1 }))).toBe('1 fixture');
    expect(fixturesText(POSITIONS)).toBe('');
  });

  it('words a rig that only warns as ready with warnings', () => {
    expect(headline(report([POSITIONS, GROUPS]))).toBe('Ready with warnings: 1 check warns.');
  });

  it('words the export summary with the status and the warn and fail counts', () => {
    expect(exportSummaryText(report([POSITIONS]))).toBe('Readiness: every check passed.');
    expect(exportSummaryText(report([ADDRESSES, GROUPS, GUESSES])))
      .toBe('Readiness: not ready, 1 check fails, 2 checks warn. You can still export.');
    expect(exportSummaryText(report([GROUPS]))).toBe('Readiness: ready with warnings, 1 check warns. You can still export.');
  });
});
