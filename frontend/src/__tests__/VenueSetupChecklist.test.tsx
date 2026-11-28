// The New venue setup checklist panel (docs/VENUE_SETUP.md): what each of the
// nine steps says for an empty rig and a nearly ready one, what its buttons
// open, what Skip remembers, and the Rig builder button that opens it. The API
// is a stand-in and the health store is set by hand: nothing here reaches a
// backend, and nothing sends DMX.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import VenueSetupChecklist from '../components/setup/VenueSetupChecklist';
import type { VenueActionHandlers } from '../components/setup/VenueSetupChecklist';
import RigBuilder from '../components/rig/RigBuilder';
import { readinessApi, rigsApi } from '../services/api';
import { focusPresetsApi } from '../services/focusPresetsApi';
import { useHealthStore } from '../stores/healthStore';
import { useRigEditorStore } from '../stores/rigEditorStore';
import type { Rig } from '../types';
import type { SetupRig, VenueStepKey } from '../utils/venueSetupChecklist';

vi.mock('../services/api', () => ({
  rigsApi: {
    get: vi.fn(),
    getConflicts: vi.fn(),
    batchUpdateFixtures: vi.fn(),
    update: vi.fn(),
    updateFixture: vi.fn(),
    autoPatch: vi.fn(),
    testAll: vi.fn(),
    getNextAddress: vi.fn(),
    addFixture: vi.fn(),
  },
  fixturesApi: { get: vi.fn() },
  roomScanApi: { editShellItem: vi.fn(), deleteShellItem: vi.fn(), addShellItem: vi.fn(), undoShellEdit: vi.fn() },
  readinessApi: { get: vi.fn(), autoGroups: vi.fn(), readdress: vi.fn(), setModes: vi.fn(), undoFix: vi.fn() },
}));
vi.mock('../services/focusPresetsApi', () => ({
  focusPresetsApi: { get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() },
}));

// The dialogs the steps open have tests of their own.
vi.mock('../components/rig/FocusPresetsPanel', () => ({ default: () => null }));
vi.mock('../components/rig/ConsoleExportSection', () => ({ default: () => null }));
vi.mock('../components/common/AudioDeviceChooser', () => ({ default: () => null }));
// The panels round the Rig builder's plan have nothing to do with the checklist.
vi.mock('../components/rig/FixturePalette', () => ({ default: () => null }));
vi.mock('../components/rig/PatchTable', () => ({ default: () => null }));
vi.mock('../components/rig/FixtureProperties', () => ({ default: () => null }));
vi.mock('../components/rig/IdentifyWalkthrough', () => ({ default: () => null }));
vi.mock('../components/rig/RoomScanDialog', () => ({ default: () => null }));

const readiness = vi.mocked(readinessApi);
const focus = vi.mocked(focusPresetsApi);
const rigs = vi.mocked(rigsApi);
const flush = () => act(async () => {});

const EMPTY_RIG: SetupRig = { id: 1, name: 'Empty room', fixtures: [], hasScannedRoom: false };

// Two lights addressed in a scanned room, one position still to confirm.
const NEARLY_READY: SetupRig = {
  id: 2,
  name: 'Main room',
  fixtures: [
    { universe: 0, dmx_address: 1, is_active: true, tags: [] },
    { universe: 0, dmx_address: 17, is_active: true, tags: ['position_unconfirmed'] },
  ],
  hasScannedRoom: true,
};

const HOST_HANDLERS = (): Required<Pick<VenueActionHandlers, 'autoPatch' | 'locate' | 'readiness' | 'roomScan' | 'stagePlot'>> => ({
  autoPatch: vi.fn(),
  locate: vi.fn(),
  readiness: vi.fn(),
  roomScan: vi.fn(),
  stagePlot: vi.fn(),
});

const quietBox = () =>
  useHealthStore.setState({ reachable: true, dmx: null, capture: null, effects: null, box: null, lastAnalysisAt: null });

// Audio heard from the desk and ArtNet going out, as the status bar would read them.
const liveBox = () =>
  useHealthStore.setState({
    reachable: true,
    dmx: { status: 'running', connected: true, transmitting: true, fps: 40, target_ip: '2.0.0.10' },
    capture: { running: true, available: true, device_name: 'Desk feed', last_rms: 0.2 },
    effects: null,
    box: null,
    lastAnalysisAt: null,
  });

function panel(rig: SetupRig | null, props: { handlers?: VenueActionHandlers; onClose?: () => void; conflictCount?: number } = {}) {
  return render(
    <MemoryRouter>
      <VenueSetupChecklist
        open
        onClose={props.onClose ?? (() => {})}
        rig={rig}
        conflictCount={props.conflictCount ?? 0}
        stagePlot={{ present: false, calibrated: false }}
        handlers={props.handlers}
      />
    </MemoryRouter>,
  );
}

const row = (key: VenueStepKey) => screen.getByTestId(`venue-step-${key}`);
const statusOf = (key: VenueStepKey) => row(key).getAttribute('data-status');
const nextRows = () =>
  screen.getAllByTestId(/^venue-step-/)
    .filter((el) => el.getAttribute('data-next') === 'true')
    .map((el) => el.getAttribute('data-testid')!.replace('venue-step-', ''));
const statuses = () =>
  Object.fromEntries(
    (['venue', 'patch', 'layout', 'locate', 'readiness', 'focus', 'audio', 'output', 'export'] as const).map((k) => [k, statusOf(k)]),
  );

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  quietBox();
  // A bare mock would fulfil with undefined; the panel reads .counts off it.
  readiness.get.mockRejectedValue(new Error('not fetched'));
  focus.get.mockRejectedValue(new Error('not fetched'));
});

afterEach(() => {
  cleanup();
});

describe('VenueSetupChecklist', () => {
  it('shows a fresh empty rig at step 1, with the steps it cannot open yet marked as such', async () => {
    panel(EMPTY_RIG);
    await flush();
    expect(screen.getAllByTestId(/^venue-step-/)).toHaveLength(9);
    expect(statuses()).toEqual({
      venue: 'attention',
      patch: 'not_started',
      layout: 'unavailable',
      locate: 'unavailable',
      readiness: 'unavailable',
      focus: 'not_started',
      audio: 'not_started',
      output: 'unavailable',
      export: 'not_started',
    });
    expect(within(row('venue')).getByText(/has no fixtures yet/)).toBeTruthy();
    expect(screen.getByTestId('venue-setup-progress').textContent).toBe('"Empty room": 0 of 9 done, 1 needs attention.');
    expect(screen.getByTestId('venue-setup-next').textContent).toBe('Next: 1. Venue and rig');
    expect(nextRows()).toEqual(['venue']);
  });

  it('shows a nearly ready rig with only the unconfirmed position and the export left', async () => {
    liveBox();
    readiness.get.mockResolvedValue({ counts: { ok: 6, warn: 0, fail: 0 } } as never);
    focus.get.mockResolvedValue({ heads: 2, targets: [{ name: 'Stage' }, { name: 'Booth' }] } as never);
    panel(NEARLY_READY, { handlers: HOST_HANDLERS() });
    await waitFor(() => expect(statusOf('readiness')).toBe('done'));
    expect(readiness.get).toHaveBeenCalledWith(2);
    expect(focus.get).toHaveBeenCalledWith(2);
    expect(statuses()).toEqual({
      venue: 'done',
      patch: 'done',
      layout: 'done',
      locate: 'attention',
      readiness: 'done',
      focus: 'done',
      audio: 'done',
      output: 'done',
      export: 'not_started',
    });
    expect(within(row('locate')).getByText(/1 of 2 positions still unconfirmed/)).toBeTruthy();
    expect(within(row('output')).getByText(/Sending ArtNet to 2\.0\.0\.10/)).toBeTruthy();
    expect(screen.getByTestId('venue-setup-progress').textContent).toBe('"Main room": 7 of 9 done, 1 needs attention.');
    expect(screen.getByTestId('venue-setup-next').textContent).toBe('Next: 4. Locate');
  });

  it('marks the first step not done or skipped as Next, with its buttons filled', async () => {
    panel(NEARLY_READY, { handlers: HOST_HANDLERS() });
    await flush();
    // Readiness was not fetched, so locate is the first step still to do.
    expect(nextRows()).toEqual(['locate']);
    expect(within(row('locate')).getByText('Next')).toBeTruthy();
    expect(screen.getAllByTestId('venue-setup-next-chip')).toHaveLength(1);
    const flash = within(row('locate')).getByRole('button', { name: 'Flash and tap' });
    expect(flash.className).toContain('MuiButton-contained');
    // Every other step's buttons stay outlined.
    const runChecks = within(row('readiness')).getByRole('button', { name: 'Readiness checks' });
    expect(runChecks.className).toContain('MuiButton-outlined');

    // Skipping it moves Next on, and the progress line counts the skip.
    fireEvent.click(within(row('locate')).getByRole('button', { name: 'Skip' }));
    expect(nextRows()).toEqual(['readiness']);
    expect(within(row('readiness')).getByRole('button', { name: 'Readiness checks' }).className).toContain('MuiButton-contained');
    expect(screen.getByTestId('venue-setup-progress').textContent).toBe('"Main room": 3 of 9 done, 1 skipped.');
  });

  it('runs a step button’s handler, stepping the checklist aside for a page dialog', async () => {
    const handlers = HOST_HANDLERS();
    const onClose = vi.fn();
    panel(NEARLY_READY, { handlers, onClose });
    await flush();
    fireEvent.click(within(row('locate')).getByRole('button', { name: 'Flash and tap' }));
    expect(handlers.locate).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(within(row('patch')).getByRole('button', { name: 'Auto patch addresses' }));
    expect(handlers.autoPatch).toHaveBeenCalledTimes(1);
  });

  it('shows a step with nothing to open as Not available yet, with no action button', async () => {
    panel(EMPTY_RIG);
    await flush();
    const output = row('output');
    expect(output.getAttribute('data-status')).toBe('unavailable');
    expect(within(output).getAllByText(/Not available yet/).length).toBeGreaterThan(0);
    expect(within(output).getByText('Set output target: not available yet')).toBeTruthy();
    expect(within(output).queryByRole('button', { name: 'Set output target' })).toBeNull();
    // Skip is the only button the row keeps.
    expect(within(output).getAllByRole('button').map((b) => b.textContent)).toEqual(['Skip']);
  });

  it('remembers a skip for the same rig across a remount, and not for another rig', async () => {
    const first = panel(EMPTY_RIG);
    await flush();
    fireEvent.click(within(row('venue')).getByRole('button', { name: 'Skip' }));
    expect(statusOf('venue')).toBe('skipped');
    expect(within(row('venue')).getByRole('button', { name: 'Unskip' })).toBeTruthy();
    first.unmount();

    const again = panel(EMPTY_RIG);
    await flush();
    expect(statusOf('venue')).toBe('skipped');
    again.unmount();

    panel({ ...EMPTY_RIG, id: 99, name: 'Other room' });
    await flush();
    expect(statusOf('venue')).toBe('attention');
  });
});

describe('Rig builder: Venue Setup button', () => {
  const spot = (id: number, address: number) => ({
    id,
    rig_id: 7,
    fixture_id: 1,
    name: `Spot ${id}`,
    universe: 0,
    dmx_address: address,
    position_x: id,
    position_y: 3,
    position_z: 0,
    rotation_x: 0,
    rotation_y: 0,
    rotation_z: 0,
    tags: ['position_unconfirmed'],
    is_active: true,
    is_inverted: false,
    is_address_locked: false,
  });

  const RIG = {
    id: 7,
    name: 'Test Rig',
    stage_width: 10,
    stage_depth: 8,
    stage_height: 5,
    universes: [],
    created_at: '',
    updated_at: '',
    is_active: true,
    fixtures: [spot(1, 1), spot(2, 2)],
  } as unknown as Rig;

  beforeEach(() => {
    rigs.getConflicts.mockResolvedValue({ conflicts: [] } as never);
    rigs.batchUpdateFixtures.mockResolvedValue(undefined as never);
    useRigEditorStore.setState({
      viewMode: '2d', snapMode: 'grid', gridSize: 0.5,
      selectedFixtureIds: new Set(), undoStack: [], redoStack: [],
    });
  });

  it('opens the checklist for the rig being edited', async () => {
    rigs.get.mockResolvedValue(RIG as never);
    render(
      <MemoryRouter initialEntries={['/rigs/7']}>
        <Routes>
          <Route path="/rigs/:id" element={<RigBuilder />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText('Spot 2');
    expect(screen.queryByTestId('venue-setup-checklist')).toBeNull();

    // The toolbar's button carries its tooltip as its label, so it is found by its words.
    fireEvent.click(screen.getByText('Venue Setup').closest('button')!);
    await flush();
    expect(screen.getByTestId('venue-setup-checklist')).toBeTruthy();
    expect(screen.getByText('New venue setup')).toBeTruthy();
    expect(readiness.get).toHaveBeenCalledWith(7);
    expect(statusOf('venue')).toBe('done');
    expect(statusOf('locate')).toBe('not_started');
  });
});
