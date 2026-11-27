// Venue readiness panel (docs/READINESS.md): every check the backend sends is shown worst first with its
// status in words (OK / Warn / Fail), not colour alone; "Select on plan" hands the check's fixture ids to
// the editor; "Make groups" asks first, then posts the auto-groups fix, tells the editor the rig changed
// and reads the checks again.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import ReadinessDialog from '../components/rig/ReadinessDialog';
import { readinessApi } from '../services/api';
import { fixturesText, headline, sortedChecks } from '../utils/readiness';
import type { AutoGroupsResult, ReadinessCheck, ReadinessReport } from '../utils/readiness';

vi.mock('../services/api', () => ({
  readinessApi: { get: vi.fn(), autoGroups: vi.fn() },
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

beforeEach(() => {
  api.get.mockReset();
  api.autoGroups.mockReset();
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
    // Nothing is written until the operator says so: there is no undo for groups.
    expect(api.autoGroups).not.toHaveBeenCalled();
    expect(screen.getByText(/There is no undo for this/)).toBeTruthy();

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
    expect(screen.queryByText(/There is no undo for this/)).toBeNull();
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
});
