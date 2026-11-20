import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import FixtureSetupChecks from '../components/rig/FixtureSetupChecks';
import PatchTable from '../components/rig/PatchTable';
import { setupChecksApi } from '../services/api';
import type { RigFixture } from '../types';
import {
  countOutstanding,
  summariseChecks,
  type SetupCheck,
  type SetupCheckFixture,
  type SetupCheckState,
} from '../utils/fixtureSetupChecks';

vi.mock('../services/api', () => ({
  setupChecksApi: {
    list: vi.fn(),
    show: vi.fn(),
    heartbeat: vi.fn(),
    release: vi.fn(),
    recordResult: vi.fn(),
    releaseOnUnload: vi.fn(),
  },
}));

const api = vi.mocked(setupChecksApi);
const flush = () => act(async () => {});

const check = (over: Partial<SetupCheck> & Pick<SetupCheck, 'check'>): SetupCheck => ({
  available: true,
  looks: [],
  reason: null,
  result: null,
  ...over,
});

const mover = (over: Partial<SetupCheckFixture> = {}): SetupCheckFixture => ({
  fixture_id: 7,
  label: 'Spot 1',
  universe: 0,
  dmx_address: 1,
  channel_count: 16,
  has_shutter: true,
  shutter_open_value: 14,
  no_response: false,
  output_blocked_reason: null,
  checks: [
    check({ check: 'flash', looks: ['white'] }),
    check({ check: 'colour', looks: ['red', 'green', 'blue'] }),
    check({ check: 'pan', looks: ['centre', 'pan_low', 'pan_high'] }),
    check({ check: 'tilt', looks: ['centre', 'tilt_low', 'tilt_high'] }),
  ],
  ...over,
});

const withResults = (results: Partial<Record<string, 'ok' | 'fail'>>, over: Partial<SetupCheckFixture> = {}) => {
  const base = mover(over);
  return { ...base, checks: base.checks.map((c) => ({ ...c, result: results[c.check] ?? null })) };
};

const state = (over: Partial<SetupCheckState> = {}): SetupCheckState => ({
  rig_id: 3,
  active: null,
  output_blocked_reason: null,
  hold_max_s: 90,
  heartbeat_timeout_s: 30,
  ...over,
});

const holding = (look: string, checkName: 'flash' | 'colour' | 'pan' | 'tilt' = 'flash') =>
  state({ active: { rig_id: 3, fixture_id: 7, label: 'Spot 1', check: checkName, look, seconds_left: 90 } });

describe('summariseChecks', () => {
  it('counts only the checks the fixture supports', () => {
    const par = mover({
      checks: [
        check({ check: 'flash', looks: ['white'], result: 'ok' }),
        check({ check: 'colour', looks: ['red', 'green', 'blue'], result: 'ok' }),
        check({ check: 'pan', available: false, reason: 'This light does not move.' }),
        check({ check: 'tilt', available: false, reason: 'This light does not move.' }),
      ],
    });
    expect(summariseChecks(par)).toMatchObject({ state: 'passed', answered: 2, total: 2 });
  });

  it('reads a single failure as failed, however much else passed', () => {
    const summary = summariseChecks(withResults({ flash: 'ok', colour: 'fail', pan: 'ok' }));
    expect(summary.state).toBe('failed');
    expect(summary.label).toMatch(/colours/i);
  });

  it('keeps a light the walkthrough never saw as failed until a flash passes', () => {
    expect(summariseChecks(mover({ no_response: true })).state).toBe('failed');
    expect(summariseChecks(withResults({ flash: 'ok' }, { no_response: true })).state).toBe('partial');
  });

  it('says why a fixture with no mode cannot be checked', () => {
    const reason = 'This light has no mode set, so we do not know its channel layout.';
    const none = mover({ checks: mover().checks.map((c) => ({ ...c, available: false, looks: [], reason })) });
    expect(summariseChecks(none)).toMatchObject({ state: 'blocked', label: reason });
  });

  it('is unchecked before the records have loaded', () => {
    expect(summariseChecks(undefined).state).toBe('unchecked');
    expect(countOutstanding([mover(), withResults({ flash: 'fail' })])).toEqual({ failed: 1, unchecked: 1 });
  });
});

describe('PatchTable setup checks', () => {
  afterEach(cleanup);

  const patched = { id: 7, universe: 0, dmx_address: 1, name: 'Spot 1', tags: [] } as unknown as RigFixture;

  it('shows each row where it stands and opens the checks for it', () => {
    const onCheck = vi.fn();
    render(
      <PatchTable
        fixtures={[patched]}
        setupChecks={[withResults({ flash: 'ok', colour: 'fail' })]}
        onCheckFixture={onCheck}
      />
    );
    const button = screen.getByTestId('patch-check-7');
    expect(button.getAttribute('data-check-state')).toBe('failed');
    expect(button.getAttribute('aria-label')).toMatch(/Spot 1.*Failed: colours/);
    expect(screen.getByTestId('patch-check-summary').textContent).toMatch(/1 light failed a check/);

    fireEvent.click(button);
    expect(onCheck).toHaveBeenCalledWith(7);
  });

  it('has no check column where nothing can open it', () => {
    render(<PatchTable fixtures={[patched]} />);
    expect(screen.queryByTestId('patch-check-7')).toBeNull();
  });
});

describe('FixtureSetupChecks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.release.mockResolvedValue(state());
    api.heartbeat.mockResolvedValue(holding('white'));
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  const open = (fixture = mover(), props: Partial<Parameters<typeof FixtureSetupChecks>[0]> = {}) => {
    const onClose = vi.fn();
    const onRecorded = vi.fn();
    render(
      <FixtureSetupChecks rigId={3} fixture={fixture} onClose={onClose} onRecorded={onRecorded} {...props} />
    );
    return { onClose, onRecorded };
  };

  it('lights nothing until a look is pressed', async () => {
    open();
    await flush();
    expect(api.show).not.toHaveBeenCalled();
    expect((screen.getByRole('button', { name: /stop the light/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('holds the look that was pressed and releases it on stop', async () => {
    api.show.mockResolvedValue(holding('red', 'colour'));
    open();

    fireEvent.click(within(screen.getByTestId('setup-check-colour')).getByRole('button', { name: 'Red' }));
    await flush();
    expect(api.show).toHaveBeenCalledWith(3, 7, 'colour', 'red');

    fireEvent.click(screen.getByRole('button', { name: /stop the light/i }));
    await flush();
    expect(api.release).toHaveBeenCalledWith(3);
  });

  it('pressing the look that is already up does not send it again or turn it off', async () => {
    api.show.mockResolvedValue(holding('white'));
    open();
    const light = within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Light it' });

    fireEvent.click(light);
    await flush();
    fireEvent.click(light);
    await flush();
    expect(api.show).toHaveBeenCalledTimes(1);
    expect(api.release).not.toHaveBeenCalled();
  });

  it('shows the box’s reason when the light is refused, such as a blackout', async () => {
    api.show.mockRejectedValue({
      response: { data: { detail: 'Blackout is on, so a test light would stay dark.' } },
    });
    open();
    fireEvent.click(within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Light it' }));
    await flush();
    expect(screen.getByRole('alert').textContent).toMatch(/Blackout is on/);
    expect((screen.getByRole('button', { name: /stop the light/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('warns before anything is pressed when the output would keep it dark', async () => {
    open(mover(), { rigBlockedReason: 'The grand master is at zero, so a test light would stay dark.' });
    await flush();
    expect(screen.getByTestId('setup-check-blocked').textContent).toMatch(/grand master/);
  });

  it('records yes and no, and a second press takes the answer back', async () => {
    api.recordResult.mockResolvedValue(withResults({ flash: 'ok' }));
    const { onRecorded } = open();
    const flash = within(screen.getByTestId('setup-check-flash'));

    fireEvent.click(flash.getByRole('button', { name: 'Yes' }));
    await flush();
    expect(api.recordResult).toHaveBeenCalledWith(3, 7, 'flash', true);
    expect(onRecorded).toHaveBeenCalledWith(withResults({ flash: 'ok' }));

    cleanup();
    open(withResults({ flash: 'ok' }));
    fireEvent.click(within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Yes' }));
    await flush();
    expect(api.recordResult).toHaveBeenLastCalledWith(3, 7, 'flash', null);

    fireEvent.click(within(screen.getByTestId('setup-check-tilt')).getByRole('button', { name: 'No' }));
    await flush();
    expect(api.recordResult).toHaveBeenLastCalledWith(3, 7, 'tilt', false);
  });

  it('offers no buttons for a check the fixture cannot do, and says why', async () => {
    const par = mover({
      checks: [
        check({ check: 'flash', looks: ['white'] }),
        check({ check: 'pan', available: false, reason: 'This light does not move.' }),
      ],
    });
    open(par);
    const pan = within(screen.getByTestId('setup-check-pan'));
    expect(pan.getByText('This light does not move.')).toBeTruthy();
    expect(pan.queryByRole('button')).toBeNull();
  });

  it('releases the light when the dialog is closed while holding', async () => {
    api.show.mockResolvedValue(holding('white'));
    const { onClose } = open();
    fireEvent.click(within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Light it' }));
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    await flush();
    expect(api.release).toHaveBeenCalledWith(3);
    expect(onClose).toHaveBeenCalled();
  });

  it('releases on the way out if the page goes away mid-hold', async () => {
    api.show.mockResolvedValue(holding('white'));
    open();
    fireEvent.click(within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Light it' }));
    await flush();

    window.dispatchEvent(new Event('pagehide'));
    expect(api.releaseOnUnload).toHaveBeenCalledWith(3);
  });

  it('heartbeats while holding and says so when the box has let go', async () => {
    vi.useFakeTimers();
    api.show.mockResolvedValue(holding('white'));
    api.heartbeat.mockResolvedValue(state());
    open();
    fireEvent.click(within(screen.getByTestId('setup-check-flash')).getByRole('button', { name: 'Light it' }));
    await flush();
    expect(api.heartbeat).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8100);
    });
    expect(api.heartbeat).toHaveBeenCalledWith(3);
    expect(screen.getByRole('alert').textContent).toMatch(/switched off/);
    expect((screen.getByRole('button', { name: /stop the light/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
