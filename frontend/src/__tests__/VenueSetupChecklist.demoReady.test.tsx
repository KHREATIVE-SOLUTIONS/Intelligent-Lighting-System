// Get demo-ready on the New venue setup checklist (docs/VENUE_SETUP.md): the
// plan it shows before anything runs, a run on confirm with one line per
// action, a failure that does not stop the rest, and the statuses read again
// after. The API is a stand-in: nothing here reaches a backend or sends DMX.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import VenueSetupChecklist from '../components/setup/VenueSetupChecklist';
import { audioApi, demoApi, readinessApi, rigsApi } from '../services/api';
import { focusPresetsApi } from '../services/focusPresetsApi';
import { useHealthStore } from '../stores/healthStore';
import type { ReadinessReport } from '../utils/readiness';
import type { SetupRig } from '../utils/venueSetupChecklist';

vi.mock('../services/api', () => ({
  rigsApi: { activate: vi.fn(), autoPatch: vi.fn(), testAll: vi.fn() },
  readinessApi: { get: vi.fn(), autoGroups: vi.fn(), readdress: vi.fn(), setModes: vi.fn(), undoFix: vi.fn() },
  audioApi: { getCaptureStatus: vi.fn(), getCaptureDevices: vi.fn(), startCapture: vi.fn(), stopCapture: vi.fn() },
  demoApi: { applyPreset: vi.fn(), getRig: vi.fn(), listPresets: vi.fn() },
}));
vi.mock('../services/focusPresetsApi', () => ({
  focusPresetsApi: { get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() },
}));
vi.mock('../components/rig/FocusPresetsPanel', () => ({ default: () => null }));
vi.mock('../components/rig/ConsoleExportSection', () => ({ default: () => null }));
// The chooser's device sorting is real; only its screen is left out.
vi.mock('../components/common/AudioDeviceChooser', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../components/common/AudioDeviceChooser')>()),
  default: () => null,
}));

const readiness = vi.mocked(readinessApi);
const audio = vi.mocked(audioApi);
const demo = vi.mocked(demoApi);
const rigs = vi.mocked(rigsApi);
const focus = vi.mocked(focusPresetsApi);
const flush = () => act(async () => {});

const EMPTY_RIG: SetupRig = { id: 1, name: 'Empty room', fixtures: [], hasScannedRoom: false };

const REPORT: ReadinessReport = {
  rig_id: 1, rig_name: 'Empty room', status: 'warn', operator_guide: 'docs/READINESS.md',
  counts: { ok: 3, warn: 1, fail: 0 },
  checks: [{ id: 'groups', title: 'Groups', status: 'warn', message: '', fixture_ids: [], fixture_count: 4, fix: 'auto-groups' }],
};

const LOOPBACK = {
  index: 7, name: 'Speakers [Loopback]', max_input_channels: 2, max_output_channels: 0,
  hostapi: 'Windows WASAPI', is_loopback: true, device_type: 'pyaudio_loopback', platform: 'win32',
};

function panel(rig: SetupRig | null) {
  return render(
    <MemoryRouter>
      <VenueSetupChecklist open onClose={() => {}} rig={rig} conflictCount={0} stagePlot={{ present: false, calibrated: false }} />
    </MemoryRouter>,
  );
}

const dialog = () => screen.getByTestId('demo-ready-dialog');

async function openPlan(rig: SetupRig | null) {
  panel(rig);
  await flush();
  fireEvent.click(screen.getByTestId('venue-setup-demo-ready'));
  await waitFor(() => expect(screen.getByTestId('demo-ready-plan')).toBeTruthy());
}

beforeEach(() => {
  // A fresh box: output held until a rig is patched, no audio captured.
  useHealthStore.setState({
    reachable: true, dmx: { status: 'running', connected: true }, capture: null, effects: null,
    box: { dmx_detail: { output_held_until_rig_patched: true } }, lastAnalysisAt: null,
  });
  readiness.get.mockResolvedValue(REPORT);
  readiness.autoGroups.mockResolvedValue({ rig_id: 1, created: [], skipped: [], unplaced_ids: [], changed: [{ id: 1, name: 'A', group_before: null, group_name: 'Front Spots' }], message: 'Grouped 4 fixtures.' });
  focus.get.mockResolvedValue({ heads: 2, targets: [{}] } as never);
  audio.getCaptureStatus.mockResolvedValue({ running: false, device_index: null, device_name: null, capture_method: 'none', available: true });
  audio.getCaptureDevices.mockResolvedValue([LOOPBACK]);
  audio.startCapture.mockResolvedValue({ status: 'started' });
  demo.applyPreset.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Get demo-ready', () => {
  it('shows what it will do and what stays manual, and runs nothing until confirmed', async () => {
    await openPlan(EMPTY_RIG);
    const plan = within(dialog());
    expect(plan.getByTestId('demo-ready-action-loadDemo').textContent).toMatch(/LIV Miami/);
    expect(plan.getByTestId('demo-ready-action-readiness')).toBeTruthy();
    expect(plan.getByTestId('demo-ready-action-makeGroups').textContent).toMatch(/4 fixtures/);
    expect(plan.getByTestId('demo-ready-action-audioInput').textContent).toMatch(/Speakers \[Loopback\]/);
    expect(plan.getByTestId('demo-ready-action-focus')).toBeTruthy();
    for (const key of ['locate', 'output', 'export']) expect(plan.getByTestId(`demo-ready-manual-${key}`)).toBeTruthy();

    expect(demo.applyPreset).not.toHaveBeenCalled();
    expect(readiness.autoGroups).not.toHaveBeenCalled();
    expect(audio.startCapture).not.toHaveBeenCalled();

    fireEvent.click(plan.getByText('Cancel'));
    await flush();
    expect(demo.applyPreset).not.toHaveBeenCalled();
  });

  it('runs every action on confirm, shows a line for each, and reads the statuses again', async () => {
    await openPlan(EMPTY_RIG);
    const readsBefore = readiness.get.mock.calls.length;
    const focusBefore = focus.get.mock.calls.length;
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());

    for (const kind of ['loadDemo', 'readiness', 'makeGroups', 'audioInput', 'focus']) {
      expect(screen.getByTestId(`demo-ready-result-${kind}`).getAttribute('data-outcome')).toBe('done');
    }
    expect(demo.applyPreset).toHaveBeenCalledWith('liv_miami_approx');
    expect(readiness.autoGroups).toHaveBeenCalledWith(1);
    expect(audio.startCapture).toHaveBeenCalledWith(7);
    // Readiness is read again at confirm (the re-check), once by the run, and
    // once more by the checklist's refresh; focus once by the run and once by the refresh.
    await waitFor(() => expect(readiness.get.mock.calls.length).toBe(readsBefore + 3));
    expect(focus.get.mock.calls.length).toBe(focusBefore + 2);
    // Never puts a rig on the show or touches output.
    expect(rigs.activate).not.toHaveBeenCalled();
    expect(readiness.readdress).not.toHaveBeenCalled();
    expect(readiness.setModes).not.toHaveBeenCalled();
  });

  it('records a failure with its error text and still runs the actions after it', async () => {
    demo.applyPreset.mockRejectedValue({ response: { status: 409, data: { detail: 'A patched rig is live.' } } });
    await openPlan(EMPTY_RIG);
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());

    const failed = screen.getByTestId('demo-ready-result-loadDemo');
    expect(failed.getAttribute('data-outcome')).toBe('failed');
    expect(failed.textContent).toMatch(/Failed\. A patched rig is live\./);
    expect(screen.getByTestId('demo-ready-result-audioInput').getAttribute('data-outcome')).toBe('done');
    expect(screen.getByTestId('demo-ready-result-focus').getAttribute('data-outcome')).toBe('done');
    expect(audio.startCapture).toHaveBeenCalledWith(7);
  });

  it('leaves loading the demo to the operator while output may be sending', async () => {
    useHealthStore.setState({
      reachable: true,
      dmx: { status: 'running', connected: true, transmitting: true, fps: 40, target_ip: '2.0.0.10' },
      capture: null, effects: null, box: null, lastAnalysisAt: null,
    });
    await openPlan(null);
    expect(screen.queryByTestId('demo-ready-action-loadDemo')).toBeNull();
    expect(screen.getByTestId('demo-ready-manual-loadDemo')).toBeTruthy();
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());
    expect(demo.applyPreset).not.toHaveBeenCalled();
    expect(screen.getByTestId('demo-ready-result-audioInput').getAttribute('data-outcome')).toBe('done');
  });

  it('re-reads on confirm and, when the plan changed, runs nothing and shows the new plan to confirm', async () => {
    await openPlan(EMPTY_RIG);
    expect(screen.getByTestId('demo-ready-action-loadDemo')).toBeTruthy();
    // Output goes live between showing the plan and confirming it.
    act(() => {
      useHealthStore.setState({
        reachable: true,
        dmx: { status: 'running', connected: true, transmitting: true, fps: 40, target_ip: '2.0.0.10' },
        box: null,
      });
    });
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-changes')).toBeTruthy());

    expect(demo.applyPreset).not.toHaveBeenCalled();
    expect(readiness.autoGroups).not.toHaveBeenCalled();
    expect(audio.startCapture).not.toHaveBeenCalled();
    expect(screen.queryByTestId('demo-ready-results')).toBeNull();
    const changes = screen.getByTestId('demo-ready-changes').textContent ?? '';
    expect(changes).toMatch(/Nothing ran/);
    expect(changes).toMatch(/No longer does: Load the LIV Miami/);
    expect(changes).toMatch(/Now left to you: Load the LIV Miami/);
    expect(screen.queryByTestId('demo-ready-action-loadDemo')).toBeNull();
    expect(screen.getByTestId('demo-ready-manual-loadDemo')).toBeTruthy();

    // Confirming the new plan runs it, without the demo.
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());
    expect(demo.applyPreset).not.toHaveBeenCalled();
    expect(readiness.autoGroups).toHaveBeenCalledWith(1);
    expect(audio.startCapture).toHaveBeenCalledWith(7);
    expect(screen.queryByTestId('demo-ready-result-loadDemo')).toBeNull();
  });

  it('offers Undo for the Make groups it applied, and shows it undone and reads the statuses again', async () => {
    readiness.undoFix.mockResolvedValue({ rig_id: 1, fix: 'auto-groups', restored: [], undo: null, message: 'Took back Make groups on 4 fixtures.' });
    await openPlan(EMPTY_RIG);
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());
    await flush();
    const readsBefore = readiness.get.mock.calls.length;

    const line = screen.getByTestId('demo-ready-result-makeGroups');
    fireEvent.click(within(line).getByTestId('demo-ready-undo-groups'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-undo-result')).toBeTruthy());

    expect(readiness.undoFix).toHaveBeenCalledTimes(1);
    expect(readiness.undoFix).toHaveBeenCalledWith(1);
    const result = screen.getByTestId('demo-ready-undo-result');
    expect(result.getAttribute('data-state')).toBe('done');
    expect(result.textContent).toMatch(/Undone\. Took back Make groups on 4 fixtures\./);
    expect(screen.queryByTestId('demo-ready-undo-groups')).toBeNull();
    await waitFor(() => expect(readiness.get.mock.calls.length).toBe(readsBefore + 1));
  });

  it('shows the error text when Undo fails and keeps the button', async () => {
    readiness.undoFix.mockRejectedValue({ response: { status: 409, data: { detail: 'The rig changed since the fix.' } } });
    await openPlan(EMPTY_RIG);
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());

    fireEvent.click(screen.getByTestId('demo-ready-undo-groups'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-undo-result')).toBeTruthy());
    const result = screen.getByTestId('demo-ready-undo-result');
    expect(result.getAttribute('data-state')).toBe('failed');
    expect(result.textContent).toBe('The rig changed since the fix.');
    expect(screen.getByTestId('demo-ready-undo-groups')).toBeTruthy();
  });

  it('offers no Undo when Make groups had nothing to group', async () => {
    readiness.autoGroups.mockResolvedValue({ rig_id: 1, created: [], skipped: [], unplaced_ids: [], changed: [], message: 'Every placed fixture is already in a group.' });
    await openPlan(EMPTY_RIG);
    fireEvent.click(screen.getByTestId('demo-ready-confirm'));
    await waitFor(() => expect(screen.getByTestId('demo-ready-close')).toBeTruthy());

    expect(screen.getByTestId('demo-ready-result-makeGroups').getAttribute('data-outcome')).toBe('skipped');
    expect(screen.queryByTestId('demo-ready-undo-groups')).toBeNull();
    expect(readiness.undoFix).not.toHaveBeenCalled();
  });
});
