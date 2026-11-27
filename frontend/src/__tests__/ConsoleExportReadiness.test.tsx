// The MA2 / MVR export (one section serves both): a readiness summary at the top with the overall status and
// the count of checks that warn or fail, a button that opens the Readiness panel, and the downloads never
// blocked by it. A preset has no rig to check, so it shows none. See docs/READINESS.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ConsoleExportSection } from '../components/rig/ConsoleExportSection';
import { consoleExportApi, readinessApi } from '../services/api';
import type { ReadinessReport } from '../utils/readiness';

vi.mock('../services/api', () => ({
  consoleExportApi: { summary: vi.fn(), download: vi.fn() },
  readinessApi: { get: vi.fn(), autoGroups: vi.fn(), readdress: vi.fn() },
}));

const exportApi = vi.mocked(consoleExportApi);
const readiness = vi.mocked(readinessApi);
const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

const REPORT: ReadinessReport = {
  rig_id: 7, rig_name: 'Club', status: 'fail', counts: { ok: 3, warn: 2, fail: 1 },
  checks: [{
    id: 'addresses', title: 'DMX addresses', status: 'fail', message: 'Spot 1 and Spot 2 overlap.',
    fixture_ids: [1, 2], fixture_count: 2, fix: 'readdress',
  }],
  operator_guide: 'docs/READINESS.md',
};

beforeEach(() => {
  exportApi.summary.mockReset();
  exportApi.summary.mockRejectedValue(new Error('not needed here'));
  exportApi.download.mockReset();
  readiness.get.mockReset();
});
afterEach(cleanup);

describe('readiness summary in the console export', () => {
  it('shows the status and the warn and fail counts, and opens the Readiness panel', async () => {
    readiness.get.mockResolvedValue(REPORT);
    render(<ConsoleExportSection target={{ rigId: 7 }} />);
    await flush();

    expect(readiness.get).toHaveBeenCalledWith(7);
    expect(screen.getByTestId('export-readiness-summary').textContent)
      .toContain('Readiness: not ready, 1 check fails, 2 checks warn. You can still export.');
    // Not blocked: every download button can still be pressed.
    const downloads = screen.getAllByRole('button').filter((b) => /grandMA2|MVR/.test(b.textContent ?? ''));
    expect(downloads).toHaveLength(3);
    downloads.forEach((b) => expect((b as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(screen.getByRole('button', { name: 'Open Readiness' }));
    await flush();
    expect(screen.getByText('Venue readiness: Club')).toBeTruthy();
    expect(screen.getByText('Spot 1 and Spot 2 overlap.')).toBeTruthy();
  });

  it('is left out when readiness cannot be read, and the export still works', async () => {
    readiness.get.mockRejectedValue(new Error('500'));
    render(<ConsoleExportSection target={{ rigId: 7 }} />);
    await flush();

    expect(screen.queryByTestId('export-readiness-summary')).toBeNull();
    expect(screen.getByText('Export to a console')).toBeTruthy();
  });

  it('a preset has no rig to check, so there is no summary', async () => {
    render(<ConsoleExportSection target={{ preset: 'liv_miami' }} />);
    await flush();

    expect(readiness.get).not.toHaveBeenCalled();
    expect(screen.queryByTestId('export-readiness-summary')).toBeNull();
  });
});
