// Venue handoff pack (docs/HANDOFF_PACK.md): one press downloads the zip; any failing readiness
// check shows a warning line first but never disables or blocks the download. The Readiness
// dialog shows the button even before (or without) its report. Next to it, "Open printable patch
// sheet" fetches /api/rigs/{id}/patch-sheet with the operator token and shows it in a new tab.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import HandoffPackButton from '../components/rig/HandoffPackButton';
import ReadinessDialog from '../components/rig/ReadinessDialog';
import { readinessApi } from '../services/api';
import { saveBlob } from '../utils/download';
import { handoffPackPath, handoffWarning, patchSheetPath } from '../utils/readiness';
import type { ReadinessReport } from '../utils/readiness';

vi.mock('../services/api', () => ({
  readinessApi: {
    get: vi.fn(), autoGroups: vi.fn(), readdress: vi.fn(), setModes: vi.fn(), undoFix: vi.fn(), handoffPack: vi.fn(),
    patchSheet: vi.fn(),
  },
}));
vi.mock('../utils/download', () => ({ saveBlob: vi.fn() }));

const api = vi.mocked(readinessApi);
const save = vi.mocked(saveBlob);
const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

const FAILING: ReadinessReport = {
  rig_id: 7,
  rig_name: 'Club',
  status: 'fail',
  counts: { ok: 0, warn: 0, fail: 1 },
  checks: [{
    id: 'addresses', title: 'DMX addresses', status: 'fail', message: 'Spot 1 and Spot 2 overlap.',
    fixture_ids: [1, 2], fixture_count: 2, fix: null,
  }],
  operator_guide: 'docs/READINESS.md',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.handoffPack.mockResolvedValue({ blob: new Blob(['zip']), filename: 'Club_handoff_pack.zip' });
});
afterEach(cleanup);

describe('handoffWarning', () => {
  it('is null with no fail and names the count otherwise', () => {
    expect(handoffWarning(0)).toBeNull();
    expect(handoffWarning(undefined)).toBeNull();
    expect(handoffWarning(1)).toMatch(/^1 readiness check fails\. The pack still downloads/);
    expect(handoffWarning(3)).toMatch(/^3 readiness checks fail\./);
    expect(handoffPackPath(7)).toBe('/rigs/7/handoff-pack');
  });
});

describe('HandoffPackButton', () => {
  it('downloads the pack in one press, with no warning when nothing fails', async () => {
    render(<HandoffPackButton rigId={7} failCount={0} />);
    expect(screen.queryByTestId('handoff-pack-warning')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /download handoff pack/i }));
    await flush();

    expect(api.handoffPack).toHaveBeenCalledWith(7);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][1]).toBe('Club_handoff_pack.zip');
    expect(screen.getByTestId('handoff-pack-note').textContent).toContain('Club_handoff_pack.zip downloaded.');
  });

  it('warns first when a check fails, and still downloads', async () => {
    render(<HandoffPackButton rigId={7} failCount={2} />);

    expect(screen.getByTestId('handoff-pack-warning').textContent).toContain('2 readiness checks fail');
    const button = screen.getByRole('button', { name: /download handoff pack/i });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    await flush();

    expect(api.handoffPack).toHaveBeenCalledWith(7);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('says so when the download fails, and saves nothing', async () => {
    api.handoffPack.mockRejectedValueOnce(new Error('network'));
    render(<HandoffPackButton rigId={7} />);

    fireEvent.click(screen.getByRole('button', { name: /download handoff pack/i }));
    await flush();

    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId('handoff-pack-note').textContent).toContain('did not download');
  });
});

describe('Open printable patch sheet', () => {
  // jsdom has no createObjectURL and no real window.open: a fake tab stands in.
  const tab = { location: { href: '' }, close: vi.fn() };
  const openSpy = vi.fn(() => tab as unknown as Window);
  const realOpen = window.open;
  const sheet = new Blob(['<!DOCTYPE html>'], { type: 'text/html' });

  beforeEach(() => {
    tab.location.href = '';
    window.open = openSpy as unknown as typeof window.open;
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: vi.fn(() => 'blob:sheet') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
    api.patchSheet.mockResolvedValue(sheet);
  });
  afterEach(() => { window.open = realOpen; });

  it('builds the sheet path with an optional universe', () => {
    expect(patchSheetPath(7)).toBe('/rigs/7/patch-sheet');
    expect(patchSheetPath(7, 3)).toBe('/rigs/7/patch-sheet?universe=3');
  });

  it('sits next to the pack button, opens a tab in the click and shows the fetched sheet in it', async () => {
    render(<HandoffPackButton rigId={7} failCount={2} />);

    const button = screen.getByRole('button', { name: /open printable patch sheet/i });
    expect(screen.getByTestId('handoff-pack').contains(button)).toBe(true);
    fireEvent.click(button);
    // The tab opens before the fetch resolves, so a popup blocker allows it.
    expect(openSpy).toHaveBeenCalledWith('', '_blank');
    await flush();

    expect(api.patchSheet).toHaveBeenCalledWith(7);
    expect(URL.createObjectURL).toHaveBeenCalledWith(sheet);
    expect(tab.location.href).toBe('blob:sheet');
    expect(api.handoffPack).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(screen.queryByTestId('patch-sheet-error')).toBeNull();
  });

  it('closes the empty tab and says so when the sheet does not come', async () => {
    api.patchSheet.mockRejectedValueOnce(new Error('network'));
    render(<HandoffPackButton rigId={7} />);

    fireEvent.click(screen.getByRole('button', { name: /open printable patch sheet/i }));
    await flush();

    expect(tab.close).toHaveBeenCalled();
    expect(screen.getByTestId('patch-sheet-error').textContent).toContain('did not open');
  });

  it('is in the Readiness dialog even when the checks cannot be read', async () => {
    api.get.mockRejectedValue(new Error('down'));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: /open printable patch sheet/i }));
    await flush();
    expect(api.patchSheet).toHaveBeenCalledWith(7);
  });
});

describe('in the Readiness dialog', () => {
  it('shows the button with the warning when the report has a Fail', async () => {
    api.get.mockResolvedValue(FAILING);
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    expect(screen.getByTestId('handoff-pack-warning').textContent).toContain('1 readiness check fails');
    fireEvent.click(screen.getByRole('button', { name: /download handoff pack/i }));
    await flush();
    expect(api.handoffPack).toHaveBeenCalledWith(7);
  });

  it('offers the button even when the checks cannot be read', async () => {
    api.get.mockRejectedValue(new Error('down'));
    render(<ReadinessDialog open rigId={7} rigName="Club" onClose={() => {}} />);
    await flush();

    expect(screen.getByRole('button', { name: /download handoff pack/i })).toBeTruthy();
    expect(screen.queryByTestId('handoff-pack-warning')).toBeNull();
  });
});
