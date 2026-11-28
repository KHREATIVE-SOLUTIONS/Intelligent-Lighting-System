// Get demo-ready's planner and runner (docs/VENUE_SETUP.md): what it plans for
// an empty box, the LIV demo, a ready rig and the states between, that the
// output steps are always the operator's, and that one failure does not stop
// the rest. Plain data and stand-in calls: nothing here reaches a backend.
import { describe, expect, it, vi } from 'vitest';
import type { AudioCaptureDevice } from '../services/api';
import {
  DEMO_ACTION_KINDS,
  DEMO_PRESET,
  errorText,
  outputVerifiablyIdle,
  pickDemoAudioDevice,
  planDemoReady,
  runDemoReadyPlan,
} from '../utils/demoReady';
import type { DemoReadyAudio, DemoReadyDeps, DemoReadyInput } from '../utils/demoReady';
import type { ReadinessCheck, ReadinessReport } from '../utils/readiness';
import type { SetupRig } from '../utils/venueSetupChecklist';

const device = (over: Partial<AudioCaptureDevice>): AudioCaptureDevice => ({
  index: 0, name: 'Device', max_input_channels: 2, max_output_channels: 0, hostapi: 'Windows WASAPI', is_loopback: false, ...over,
});
const LINE_IN = device({ index: 3, name: 'Line In (Desk)' });
const LOOPBACK = device({ index: 7, name: 'Speakers [Loopback]', is_loopback: true, device_type: 'pyaudio_loopback' });

const audioOff = (over: Partial<DemoReadyAudio> = {}): DemoReadyAudio => ({
  running: false, inputs: [LINE_IN], loopback: [LOOPBACK], remembered: null, browserName: null, ...over,
});

const RIG: SetupRig = {
  id: 4, name: 'Main room', hasScannedRoom: false,
  fixtures: [{ universe: 0, dmx_address: 1, is_active: true }, { universe: 0, dmx_address: 17, is_active: true }],
};
const EMPTY_RIG: SetupRig = { id: 5, name: 'Empty room', fixtures: [], hasScannedRoom: false };

const check = (over: Partial<ReadinessCheck>): ReadinessCheck => ({
  id: 'x', title: 'Check', status: 'ok', message: '', fixture_ids: [], fixture_count: 0, fix: null, ...over,
});
const report = (checks: ReadinessCheck[]): ReadinessReport => ({
  rig_id: 4, rig_name: 'Main room', status: 'ok', operator_guide: 'docs/READINESS.md', checks,
  counts: {
    ok: checks.filter((c) => c.status === 'ok').length,
    warn: checks.filter((c) => c.status === 'warn').length,
    fail: checks.filter((c) => c.status === 'fail').length,
  },
});

const input = (over: Partial<DemoReadyInput> = {}): DemoReadyInput => ({
  rig: null, demoRunning: false, outputIdle: true, readiness: null, audio: audioOff(), ...over,
});

const kinds = (plan: ReturnType<typeof planDemoReady>) => plan.actions.map((a) => a.kind);
const manualKeys = (plan: ReturnType<typeof planDemoReady>) => plan.manual.map((m) => m.key);

describe('planDemoReady', () => {
  it('on an empty box loads the LIV demo and starts loopback, and skips the saved-rig reads', () => {
    const plan = planDemoReady(input());
    expect(kinds(plan)).toEqual(['loadDemo', 'audioInput']);
    expect(plan.actions[1].deviceIndex).toBe(LOOPBACK.index);
    expect(plan.skipped.map((s) => s.kind)).toEqual(['readiness', 'focus']);
  });

  it('with the LIV demo already running and audio on, has nothing left to do but the manual steps', () => {
    const plan = planDemoReady(input({ demoRunning: true, audio: audioOff({ running: true }) }));
    expect(plan.actions).toEqual([]);
    expect(plan.skipped.map((s) => s.kind)).toEqual(['loadDemo', 'readiness', 'audioInput', 'focus']);
  });

  it('loads the demo for an open rig with no fixtures, then checks that rig', () => {
    const plan = planDemoReady(input({ rig: EMPTY_RIG }));
    expect(kinds(plan)).toEqual(['loadDemo', 'readiness', 'audioInput', 'focus']);
  });

  it('on a ready rig uses that rig: reads its checks and focus presets, loads no demo', () => {
    const plan = planDemoReady(input({ rig: RIG, readiness: report([check({ id: 'a' })]), audio: audioOff({ running: true }) }));
    expect(kinds(plan)).toEqual(['readiness', 'focus']);
    expect(plan.skipped[0]).toMatchObject({ kind: 'loadDemo', detail: expect.stringContaining('Main room') });
  });

  it('applies Make groups by itself, and leaves Re-address, Set modes and Locate with the operator', () => {
    const plan = planDemoReady(input({
      rig: RIG,
      readiness: report([
        check({ id: 'groups', title: 'Groups', status: 'warn', fix: 'auto-groups', fixture_count: 6 }),
        check({ id: 'addresses', title: 'Addresses', status: 'fail', fix: 'readdress' }),
        check({ id: 'modes', title: 'Modes', status: 'warn', fix: 'set-modes' }),
        check({ id: 'positions', title: 'Positions', status: 'warn', fix: 'locate' }),
        check({ id: 'done', title: 'Already fine', status: 'ok', fix: 'auto-groups' }),
      ]),
    }));
    expect(kinds(plan)).toEqual(['readiness', 'makeGroups', 'audioInput', 'focus']);
    expect(plan.actions[1].detail).toMatch(/6 fixtures/);
    expect(manualKeys(plan)).toEqual(expect.arrayContaining(['fix-addresses', 'fix-modes', 'fix-positions']));
  });

  it('never loads a demo while output may be sending: that becomes a manual step', () => {
    const plan = planDemoReady(input({ outputIdle: false }));
    expect(kinds(plan)).not.toContain('loadDemo');
    expect(manualKeys(plan)).toContain('loadDemo');
  });

  it('hands audio back when nothing is remembered and there is no loopback', () => {
    const plan = planDemoReady(input({ audio: audioOff({ loopback: [] }) }));
    expect(kinds(plan)).not.toContain('audioInput');
    expect(manualKeys(plan)).toContain('audio');
    expect(manualKeys(planDemoReady(input({ audio: null })))).toContain('audio');
  });

  it('only ever plans allowed kinds, and always leaves locate, output and export manual', () => {
    const states: DemoReadyInput[] = [
      input(),
      input({ outputIdle: false }),
      input({ rig: EMPTY_RIG, outputIdle: false, audio: null }),
      input({ rig: RIG, demoRunning: true, readiness: report([check({ status: 'fail', fix: 'locate' })]) }),
      input({ rig: RIG, audio: audioOff({ running: true }) }),
    ];
    for (const state of states) {
      const plan = planDemoReady(state);
      for (const action of plan.actions) expect(DEMO_ACTION_KINDS).toContain(action.kind);
      expect(manualKeys(plan)).toEqual(expect.arrayContaining(['locate', 'output', 'export']));
    }
  });
});

describe('pickDemoAudioDevice', () => {
  it('prefers the box’s remembered device, then this browser’s, then loopback; never an unpicked line input', () => {
    expect(pickDemoAudioDevice(audioOff({ remembered: { name: 'Line In (Desk)' } }))).toBe(LINE_IN);
    expect(pickDemoAudioDevice(audioOff({ browserName: 'Line In (Desk)' }))).toBe(LINE_IN);
    expect(pickDemoAudioDevice(audioOff())).toBe(LOOPBACK);
    expect(pickDemoAudioDevice(audioOff({ loopback: [] }))).toBeNull();
  });
});

describe('outputVerifiablyIdle', () => {
  it('is true only when output is held, not set up or not connected', () => {
    expect(outputVerifiablyIdle(null, true, null)).toBe(false);
    expect(outputVerifiablyIdle(null, true, { dmx_detail: { output_held_until_rig_patched: true } })).toBe(true);
    expect(outputVerifiablyIdle({ status: 'not_initialized' }, true, null)).toBe(true);
    expect(outputVerifiablyIdle({ status: 'running', connected: false }, true, null)).toBe(true);
    expect(outputVerifiablyIdle({ status: 'running', connected: true }, true, { dmx_detail: { output_held_until_rig_patched: true } } as never)).toBe(true);
    expect(outputVerifiablyIdle({ status: 'running', connected: true, transmitting: true }, true, null)).toBe(false);
    expect(outputVerifiablyIdle(null, false, null)).toBe(false);
  });
});

describe('runDemoReadyPlan', () => {
  const deps = (over: Partial<DemoReadyDeps> = {}): DemoReadyDeps => ({
    applyDemoPreset: vi.fn().mockResolvedValue({}),
    readReadiness: vi.fn().mockResolvedValue(report([check({})])),
    makeGroups: vi.fn().mockResolvedValue({ changed: [{}], message: 'Grouped 6 fixtures.' }),
    startCapture: vi.fn().mockResolvedValue({}),
    readFocus: vi.fn().mockResolvedValue({ heads: 2, targets: [{}] }),
    ...over,
  });

  it('records a failure with its error text and still runs the actions after it', async () => {
    const plan = planDemoReady(input({
      rig: EMPTY_RIG,
      readiness: report([check({ id: 'g', status: 'warn', fix: 'auto-groups', fixture_count: 1 })]),
    }));
    const d = deps({
      makeGroups: vi.fn().mockRejectedValue({ response: { status: 409, data: { detail: { message: 'Rig changed.' } } } }),
    });
    const results = await runDemoReadyPlan(plan, EMPTY_RIG.id, d);
    expect(results.map((r) => [r.kind, r.outcome])).toEqual([
      ['loadDemo', 'done'], ['readiness', 'done'], ['makeGroups', 'failed'], ['audioInput', 'done'], ['focus', 'done'],
    ]);
    expect(results[2].message).toBe('Rig changed.');
    expect(d.applyDemoPreset).toHaveBeenCalledWith(DEMO_PRESET);
    expect(d.startCapture).toHaveBeenCalledWith(LOOPBACK.index);
  });

  it('calls Make groups skipped when it changed nothing', async () => {
    const plan = planDemoReady(input({ rig: RIG, readiness: report([check({ status: 'warn', fix: 'auto-groups' })]) }));
    const results = await runDemoReadyPlan(plan, RIG.id, deps({ makeGroups: vi.fn().mockResolvedValue({ changed: [], message: 'Nothing to group.' }) }));
    expect(results.find((r) => r.kind === 'makeGroups')).toMatchObject({ outcome: 'skipped', message: 'Nothing to group.' });
  });
});

describe('errorText', () => {
  it('reads a string detail, a {message} detail, then the error itself', () => {
    expect(errorText({ response: { data: { detail: 'Refused.' } } })).toBe('Refused.');
    expect(errorText({ response: { data: { detail: { message: 'Changed since.' } } } })).toBe('Changed since.');
    expect(errorText(new Error('Network Error'))).toBe('Network Error');
  });
});
