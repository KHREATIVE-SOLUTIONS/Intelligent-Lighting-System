import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import MasterControl from '../components/dashboard/MasterControl';
import { masterApi } from '../services/api';

vi.mock('../services/api', () => ({
  masterApi: {
    get: vi.fn(),
    setGrandMaster: vi.fn(),
    blackout: vi.fn(),
    restore: vi.fn(),
  },
}));

const api = vi.mocked(masterApi);
const flush = () => act(async () => {});

describe('MasterControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.blackout.mockResolvedValue(undefined);
    api.restore.mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it('keeps blackout pressable when the engine did not answer', async () => {
    api.get.mockRejectedValue(new Error('offline'));
    render(<MasterControl />);
    await flush();

    const button = screen.getByRole('button', { name: /blackout/i });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole('alert').textContent).toMatch(/not reachable/i);

    fireEvent.click(button);
    await flush();
    // Unknown state: the safe guess is to go dark, never to restore.
    expect(api.blackout).toHaveBeenCalledTimes(1);
    expect(api.restore).not.toHaveBeenCalled();
  });

  it('toggles blackout with the B key, but not while typing', async () => {
    api.get.mockResolvedValue({ grand_master: 1, blackout: false, output_master: 1 });
    render(
      <>
        <input aria-label="notes" />
        <MasterControl />
      </>
    );
    await flush();

    fireEvent.keyDown(screen.getByLabelText('notes'), { key: 'b' });
    await flush();
    expect(api.blackout).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'b' });
    await flush();
    expect(api.blackout).toHaveBeenCalledTimes(1);
  });

  it('shows the latched state clearly and releases it', async () => {
    api.get.mockResolvedValue({ grand_master: 0.6, blackout: true, output_master: 0 });
    render(<MasterControl />);
    await flush();

    expect(screen.getByText('BLACKOUT ON')).toBeTruthy();
    expect(screen.getByTestId('grand-master-level').textContent).toBe('60%');
    const release = screen.getByRole('button', { name: /release blackout/i });
    expect(release.getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(release);
    await flush();
    expect(api.restore).toHaveBeenCalledTimes(1);
  });

  it('picks up a blackout set from another screen', async () => {
    vi.useFakeTimers();
    try {
      api.get.mockResolvedValueOnce({ grand_master: 1, blackout: false, output_master: 1 });
      render(<MasterControl />);
      await act(async () => {});
      expect(screen.queryByText('BLACKOUT ON')).toBeNull();

      api.get.mockResolvedValue({ grand_master: 1, blackout: true, output_master: 0 });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(screen.getByText('BLACKOUT ON')).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
