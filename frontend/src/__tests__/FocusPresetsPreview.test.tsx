// Focus presets toward programming: the reach read again after a rig change
// (debounced), a preset previewed in the 3D view (start, switch, stop, the
// view leaving, a target going) with nothing sent anywhere but the focus
// table's own read, heads that cannot reach left at home, and the per-head
// table and its sort. docs/FOCUS_PRESETS.md, "In the app".
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const api = vi.hoisted(() => ({ get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() }));
// Anything that could reach the lights: the app's client and its rig calls. None may be called.
const output = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
  setFixtureChannels: vi.fn(), testFixture: vi.fn(), testAll: vi.fn(), setFixturePosition: vi.fn(), updateFixture: vi.fn(),
}));
vi.mock('../services/focusPresetsApi', () => ({ focusPresetsApi: api }));
vi.mock('../services/stagePlotApi', () => ({ refusalText: (_error: unknown, fallback: string) => fallback }));
vi.mock('../utils/download', () => ({ saveBlob: vi.fn() }));
vi.mock('../services/api', () => ({
  default: { get: output.get, post: output.post, put: output.put, patch: output.patch, delete: output.delete },
  rigsApi: {
    setFixtureChannels: output.setFixtureChannels, testFixture: output.testFixture, testAll: output.testAll,
    setFixturePosition: output.setFixturePosition, updateFixture: output.updateFixture,
  },
}));

import FocusPresetsPanel from '../components/rig/FocusPresetsPanel';
import FocusPreviewNotice from '../components/rig/previs/FocusPreviewNotice';
import useFocusTargets3d from '../components/rig/previs/useFocusTargets3d';
import type { FocusTargets3dState } from '../components/rig/previs/useFocusTargets3d';
import { RIG_CHANGE_DEBOUNCE_MS } from '../components/rig/useFocusPresets';
import { useFocusPreviewStore } from '../stores/focusPreviewStore';
import { focusTargets3dKey, parseFocusPresets } from '../utils/focusPresets';
import { announceFocusTargetsChange, announceRigChange } from '../utils/focusTargetsSync';
import { RIG_ID } from './focusPresetsFixture';
import { VIEW_FIXTURES, previewAnswer } from './focusPreviewFixture';
import type { PreviewAnswer } from './focusPreviewFixture';

/** What the server answers now; a test changes it to stand for a moved fixture or a removed target. */
let answer: PreviewAnswer = previewAnswer();
const fetchSpy = vi.fn();
const store = () => useFocusPreviewStore.getState();

beforeEach(() => {
  answer = previewAnswer();
  api.get.mockReset().mockImplementation(async () => parseFocusPresets(answer));
  Object.values(output).forEach((fn) => fn.mockReset());
  fetchSpy.mockReset();
  vi.stubGlobal('fetch', fetchSpy);
  window.localStorage.clear();
  useFocusPreviewStore.setState({ viewRigId: null, preview: null });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function expectNothingSent() {
  Object.entries(output).forEach(([name, fn]) => expect(fn, name).not.toHaveBeenCalled());
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(api.addTarget).not.toHaveBeenCalled();
  expect(api.removeTarget).not.toHaveBeenCalled();
}

async function renderPanel() {
  render(<FocusPresetsPanel rigId={RIG_ID} />);
  await screen.findByTestId('focus-presets-list');
}

const row = (key: string) => within(screen.getByTestId(`focus-target-${key}`));
// No jest-dom in this project: plain reads of the DOM.
const textOf = (el: HTMLElement) => el.textContent ?? '';
const disabled = (el: HTMLElement) => (el as HTMLButtonElement).disabled;

/** The 3D view's hook, held where a test can read it. */
let view: FocusTargets3dState;
function ViewProbe({ rigId }: { rigId: number | null }) {
  view = useFocusTargets3d(rigId, VIEW_FIXTURES);
  return null;
}

describe('reach read again after a rig change', () => {
  it('reads the table once the writes settle, and shows the new reach in the panel', async () => {
    await renderPanel();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(textOf(row('dance_floor').getByTestId('focus-target-reach'))).toContain('All 3 moving heads can reach it.');

    // A fixture dragged: now only one head reaches the dance floor.
    answer.targets = answer.targets.map((t) => (t.key === 'dance_floor'
      ? { ...t, reachable_count: 1, unreachable: [
        { fixture_id: 2, name: 'Spot 2', reason: 'out of travel' },
        { fixture_id: 3, name: 'Spot 3', reason: 'out of travel' },
      ] }
      : t));
    act(() => {
      announceRigChange(RIG_ID);
      announceRigChange(RIG_ID);
      announceRigChange(RIG_ID);
      announceRigChange(RIG_ID + 1);
    });
    // Debounced: nothing read straight away.
    expect(api.get).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(textOf(row('dance_floor').getByTestId('focus-target-reach'))).toContain('1 of 3 moving heads can reach it.'));
    // Four announcements, one of them another rig's: one read.
    await new Promise((resolve) => setTimeout(resolve, RIG_CHANGE_DEBOUNCE_MS + 100));
    expect(api.get).toHaveBeenCalledTimes(2);
    expectNothingSent();
  });

  it('changes the 3D markers\' look without turning them off and on', async () => {
    window.localStorage.setItem(focusTargets3dKey(RIG_ID), 'on');
    render(<ViewProbe rigId={RIG_ID} />);
    await waitFor(() => expect(view.markers.find((m) => m.key === 'dance_floor')?.style).toBe('all'));
    answer.targets = answer.targets.map((t) => (t.key === 'dance_floor'
      ? { ...t, reachable_count: 0, unreachable: [1, 2, 3].map((n) => ({ fixture_id: n, name: `Spot ${n}`, reason: 'x' })) }
      : t));
    act(() => announceRigChange(RIG_ID));
    await waitFor(() => expect(view.markers.find((m) => m.key === 'dance_floor')?.style).toBe('none'));
    expect(view.on).toBe(true);
  });
});

describe('previewing a preset in the 3D view', () => {
  it('is offered only while a 3D view shows this rig', async () => {
    await renderPanel();
    expect(disabled(row('dj_booth').getByRole('button', { name: 'Preview DJ booth' }))).toBe(true);
    // A skipped target has nothing to preview.
    expect(row('stage_front').queryByRole('button', { name: /Preview/ })).toBeNull();
    act(() => { store().attachView(RIG_ID + 1); });
    expect(disabled(row('dj_booth').getByRole('button', { name: 'Preview DJ booth' }))).toBe(true);
    act(() => { store().attachView(RIG_ID); });
    expect(disabled(row('dj_booth').getByRole('button', { name: 'Preview DJ booth' }))).toBe(false);
  });

  it('starts, switches to a second target and stops, sending nothing', async () => {
    act(() => { store().attachView(RIG_ID); });
    await renderPanel();

    fireEvent.click(row('dj_booth').getByRole('button', { name: 'Preview DJ booth' }));
    expect(store().preview).toEqual({ rigId: RIG_ID, key: 'dj_booth' });
    expect(textOf(screen.getByTestId('focus-preview-active'))).toContain('Previewing DJ booth in the 3D view. Nothing is sent to the lights.');
    expect(row('dj_booth').getByRole('button', { name: 'Stop preview' })).toBeTruthy();

    fireEvent.click(row('dance_floor').getByRole('button', { name: 'Preview Dance floor centre' }));
    expect(store().preview).toEqual({ rigId: RIG_ID, key: 'dance_floor' });
    expect(row('dj_booth').queryByRole('button', { name: 'Stop preview' })).toBeNull();
    expect(textOf(screen.getByTestId('focus-preview-active'))).toContain('Previewing Dance floor centre');

    fireEvent.click(within(screen.getByTestId('focus-preview-active')).getByRole('button', { name: 'Stop preview' }));
    expect(store().preview).toBeNull();
    expect(screen.queryByTestId('focus-preview-active')).toBeNull();

    expect(api.get).toHaveBeenCalledTimes(1);
    expectNothingSent();
  });

  it('stops when the 3D view leaves the rig, or opens another', () => {
    const leave = store().attachView(RIG_ID);
    store().start(RIG_ID, 'dj_booth');
    act(() => leave());
    expect(store().preview).toBeNull();
    expect(store().viewRigId).toBeNull();

    store().attachView(RIG_ID);
    store().start(RIG_ID, 'dj_booth');
    store().attachView(RIG_ID + 1);
    expect(store().preview).toBeNull();
  });

  it('aims the heads that reach and leaves the one that cannot at home, listed', async () => {
    store().attachView(RIG_ID);
    store().start(RIG_ID, 'dj_booth');
    // Markers off: the table is read for the preview alone.
    render(<ViewProbe rigId={RIG_ID} />);
    await waitFor(() => expect(view.preview?.aimed).toBe(2));
    expect(view.markers).toEqual([]);
    const plan = view.preview!;
    expect(plan.aims.get(101)).toEqual({ panDeg: 10, tiltDeg: -31 });
    expect(plan.aims.get(102)).toEqual({ panDeg: 20, tiltDeg: -32 });
    expect(plan.aims.get(103)).toBeNull();

    cleanup();
    const stop = vi.fn();
    render(<FocusPreviewNotice plan={plan} onStop={stop} />);
    expect(textOf(screen.getByTestId('focus-preview-notice'))).toContain('Previewing DJ booth: 2 heads aimed at it.');
    expect(textOf(screen.getByTestId('focus-preview-home'))).toContain(
      'Spot 3 stays at home: tilt would be 150 degrees; the head turns 135 each way',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Stop preview' }));
    expect(stop).toHaveBeenCalledTimes(1);
    expectNothingSent();
  });

  it('switches with the store, and stops when the previewed target is removed', async () => {
    store().attachView(RIG_ID);
    store().start(RIG_ID, 'dance_floor');
    render(<ViewProbe rigId={RIG_ID} />);
    await waitFor(() => expect(view.preview?.key).toBe('dance_floor'));
    act(() => store().start(RIG_ID, 'custom_4'));
    expect(view.preview?.key).toBe('custom_4');
    expect(view.preview?.aimed).toBe(0);

    answer.targets = answer.targets.filter((t) => t.key !== 'custom_4');
    answer.custom_targets = [];
    act(() => announceFocusTargetsChange(RIG_ID, {}));
    await waitFor(() => expect(store().preview).toBeNull());
    await waitFor(() => expect(view.preview).toBeNull());
  });

  it('ignores a preview of another rig', async () => {
    store().start(RIG_ID + 1, 'dj_booth');
    render(<ViewProbe rigId={RIG_ID} />);
    expect(view.preview).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('each head\'s pan, tilt and DMX in the panel', () => {
  it('lists every head against the target, sorted by fixture, with 16 and 8 bit DMX', async () => {
    await renderPanel();
    const booth = row('dj_booth');
    expect(booth.queryByTestId('focus-heads-dj_booth')).toBeNull();
    fireEvent.click(booth.getByRole('button', { name: 'Show pan, tilt and DMX for each head' }));
    const table = within(booth.getByTestId('focus-heads-dj_booth'));
    const rows = table.getAllByTestId('focus-head-row');
    expect(rows.map((r) => r.textContent?.match(/^\d+\. Spot \d/)?.[0])).toEqual(['1. Spot 1', '2. Spot 2', '3. Spot 3']);

    const cells = (r: HTMLElement) => within(r).getAllByRole('cell').map((c) => c.textContent);
    expect(cells(rows[0]).slice(1)).toEqual(['10.0°', '-31.0°', '131 / 64', '101 / 32']);
    expect(textOf(rows[0])).toContain('hung, 16-bit');
    expect(cells(rows[2]).slice(1)).toEqual(['-', '-', '-', '-']);
    expect(textOf(rows[2])).toContain('standing, 8-bit. Cannot reach: tilt would be 150 degrees');

    fireEvent.click(table.getByRole('button', { name: 'Fixture' }));
    expect(table.getAllByTestId('focus-head-row').map((r) => r.textContent?.match(/^\d+/)?.[0])).toEqual(['3', '2', '1']);
    fireEvent.click(table.getByRole('button', { name: 'Fixture' }));
    expect(table.getAllByTestId('focus-head-row').map((r) => r.textContent?.match(/^\d+/)?.[0])).toEqual(['1', '2', '3']);

    fireEvent.click(booth.getByRole('button', { name: 'Hide pan, tilt and DMX for each head' }));
    await waitFor(() => expect(booth.queryByTestId('focus-heads-dj_booth')).toBeNull());
    expectNothingSent();
  });

  it('shows an 8-bit head\'s DMX as one number', async () => {
    await renderPanel();
    const floor = row('dance_floor');
    fireEvent.click(floor.getByRole('button', { name: 'Show pan, tilt and DMX for each head' }));
    const spot3 = within(floor.getByTestId('focus-heads-dance_floor')).getAllByTestId('focus-head-row')[2];
    expect(within(spot3).getAllByRole('cell').map((c) => c.textContent).slice(1)).toEqual(['20.0°', '120.0°', '133', '103']);
  });
});
