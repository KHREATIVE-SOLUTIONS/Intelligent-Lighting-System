import { describe, expect, it } from 'vitest';
import type { HealthReading } from '../utils/showHealth';
import {
  STEP_ACTIONS,
  VENUE_STEP_ORDER,
  buildVenueSetupSteps,
  loadSkipped,
  nextVenueStep,
  saveSkipped,
  skippedStorageKey,
  summarizeVenueSetup,
  toggleSkipped,
  venueSetupProgress,
} from '../utils/venueSetupChecklist';
import type {
  KeyValueStore,
  SetupFixture,
  SetupRig,
  VenueActionKey,
  VenueSetupInput,
  VenueStepKey,
} from '../utils/venueSetupChecklist';

const ok = (detail = 'fine'): HealthReading => ({ level: 'ok', label: 'ok', detail });
const down = (detail: string): HealthReading => ({ level: 'down', label: 'off', detail });
const warn = (detail: string): HealthReading => ({ level: 'warn', label: 'warn', detail });

const ALL_ACTIONS = new Set<VenueActionKey>(Object.values(STEP_ACTIONS).flat());

const fixture = (over: Partial<SetupFixture> = {}): SetupFixture => ({
  universe: 0,
  dmx_address: 1,
  is_active: true,
  tags: [],
  ...over,
});

const rig = (fixtures: SetupFixture[], over: Partial<SetupRig> = {}): SetupRig => ({
  id: 7,
  name: 'Main room',
  fixtures,
  hasScannedRoom: false,
  ...over,
});

const input = (over: Partial<VenueSetupInput> = {}): VenueSetupInput => ({
  rig: null,
  audio: down('No audio feed is being captured.'),
  output: down('DMX output is not set up on the box.'),
  available: ALL_ACTIONS,
  ...over,
});

const step = (key: VenueStepKey, over: Partial<VenueSetupInput> = {}) =>
  buildVenueSetupSteps(input(over)).find((s) => s.key === key)!;

describe('buildVenueSetupSteps', () => {
  it('lists the nine steps in order, numbered from one', () => {
    const steps = buildVenueSetupSteps(input());
    expect(steps.map((s) => s.key)).toEqual([...VENUE_STEP_ORDER]);
    expect(steps.map((s) => s.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it('starts an empty box at step 1 with every rig step waiting on it', () => {
    const steps = buildVenueSetupSteps(input());
    expect(steps[0]).toMatchObject({ key: 'venue', status: 'not_started' });
    expect(steps[0].detail).toContain('LIV demo');
    for (const key of ['patch', 'layout', 'locate', 'readiness', 'focus', 'export'] as const) {
      expect(steps.find((s) => s.key === key)!.detail).toContain('step 1');
    }
    expect(summarizeVenueSetup(steps).next?.key).toBe('venue');
  });

  it('says the demo is already showing when no rig is open', () => {
    expect(step('venue', { demoRunning: true }).detail).toContain('can show the owner');
  });

  it('flags a rig with no fixtures', () => {
    expect(step('venue', { rig: rig([]) }).status).toBe('attention');
    expect(step('patch', { rig: rig([]) }).status).toBe('not_started');
  });

  it('counts only active fixtures', () => {
    const r = rig([fixture(), fixture({ is_active: false, dmx_address: 0 })]);
    expect(step('venue', { rig: r }).detail).toBe('"Main room", 1 fixture.');
    expect(step('patch', { rig: r }).status).toBe('done');
  });

  describe('patch', () => {
    it('needs attention for fixtures without a DMX address', () => {
      const s = step('patch', { rig: rig([fixture(), fixture({ dmx_address: 0 }), fixture({ dmx_address: null })]) });
      expect(s.status).toBe('attention');
      expect(s.detail).toContain('2 fixtures have no DMX address');
    });

    it('needs attention for address clashes', () => {
      const s = step('patch', { rig: rig([fixture(), fixture()]), conflictCount: 1 });
      expect(s.status).toBe('attention');
      expect(s.detail).toContain('1 address clash ');
    });

    it('is done when everything is addressed with no clashes', () => {
      const s = step('patch', { rig: rig([fixture(), fixture({ universe: 1 })]), conflictCount: 0 });
      expect(s).toMatchObject({ status: 'done', detail: 'All 2 fixtures addressed over 2 universes, no clashes.' });
    });
  });

  describe('layout', () => {
    const r = rig([fixture()]);
    it('has not started with no scan and no plot', () => {
      expect(step('layout', { rig: r }).status).toBe('not_started');
    });
    it('is done with a scanned room', () => {
      expect(step('layout', { rig: { ...r, hasScannedRoom: true } }).status).toBe('done');
    });
    it('is done with a calibrated stage plot', () => {
      expect(step('layout', { rig: r, stagePlot: { present: true, calibrated: true } }).status).toBe('done');
    });
    it('needs attention for a plot that is not calibrated', () => {
      const s = step('layout', { rig: r, stagePlot: { present: true, calibrated: false } });
      expect(s.status).toBe('attention');
      expect(s.detail).toContain('not calibrated');
    });
  });

  describe('locate', () => {
    const unconfirmed = () => fixture({ tags: ['position_unconfirmed'] });
    it('has not started when no position is confirmed', () => {
      expect(step('locate', { rig: rig([unconfirmed(), unconfirmed()]) }).status).toBe('not_started');
    });
    it('needs attention partway through', () => {
      const s = step('locate', { rig: rig([unconfirmed(), fixture(), fixture()]) });
      expect(s).toMatchObject({ status: 'attention', detail: '1 of 3 positions still unconfirmed. Flash and tap them.' });
    });
    it('is done when every position is confirmed', () => {
      expect(step('locate', { rig: rig([fixture(), fixture()]) }).status).toBe('done');
    });
    it('ignores an inactive unconfirmed fixture', () => {
      const s = step('locate', { rig: rig([fixture(), { ...unconfirmed(), is_active: false }]) });
      expect(s.status).toBe('done');
    });
  });

  describe('readiness', () => {
    const r = rig([fixture()]);
    it('has not started until the report is read', () => {
      expect(step('readiness', { rig: r, readiness: null }).status).toBe('not_started');
    });
    it('needs attention for any failing check', () => {
      const s = step('readiness', { rig: r, readiness: { ok: 5, warn: 2, fail: 1 } });
      expect(s.status).toBe('attention');
      expect(s.detail).toContain('1 check fails and 2 warnings');
    });
    it('is done with warnings only, and says so', () => {
      const s = step('readiness', { rig: r, readiness: { ok: 5, warn: 2, fail: 0 } });
      expect(s).toMatchObject({ status: 'done', detail: 'No failures. 2 warnings worth a look.' });
    });
  });

  describe('focus presets', () => {
    const r = rig([fixture()]);
    it('is done when there are no moving heads to aim', () => {
      expect(step('focus', { rig: r, focus: { heads: 0, targets: 0 } }).status).toBe('done');
    });
    it('needs attention for heads with no targets', () => {
      expect(step('focus', { rig: r, focus: { heads: 4, targets: 0 } }).status).toBe('attention');
    });
    it('is done with targets', () => {
      expect(step('focus', { rig: r, focus: { heads: 4, targets: 6 } }).detail).toBe('6 focus targets for 4 moving heads.');
    });
  });

  describe('audio', () => {
    it('has not started with no capture', () => {
      const s = step('audio');
      expect(s.status).toBe('not_started');
      expect(s.detail).toContain('Pick the desk feed');
    });
    it('needs attention for a silent feed', () => {
      expect(step('audio', { audio: warn('Capturing from USB but the feed is silent.') }).status).toBe('attention');
    });
    it('is done with signal, and gives the beat', () => {
      const s = step('audio', { audio: ok('Hearing USB.'), bpm: 123.6 });
      expect(s).toMatchObject({ status: 'done', detail: 'Hearing USB. Beat at about 124 BPM.' });
    });
  });

  describe('output target', () => {
    it('follows the status bar reading', () => {
      expect(step('output', { output: ok('Sending ArtNet to 10.0.0.5.') }).status).toBe('done');
      expect(step('output', { output: warn('Waiting for a rig to be patched.') }).status).toBe('attention');
      expect(step('output', { output: down('ArtNet is not connected.') }).status).toBe('not_started');
    });
  });

  describe('export', () => {
    const r = rig([fixture()]);
    it('never claims to be done, because nothing records an export', () => {
      const s = step('export', { rig: r, readiness: { ok: 9, warn: 0, fail: 0 } });
      expect(s.status).toBe('not_started');
      expect(s.detail).toContain('Ready to export');
    });
    it('needs attention while readiness fails', () => {
      expect(step('export', { rig: r, readiness: { ok: 1, warn: 0, fail: 2 } }).status).toBe('attention');
    });
  });

  describe('availability', () => {
    it('lists only the actions the host can open, and names the rest as missing', () => {
      const available = new Set<VenueActionKey>(['autoPatch']);
      const s = step('patch', { available, rig: rig([fixture({ dmx_address: 0 })]) });
      expect(s.actions).toEqual(['autoPatch']);
      expect(s.missing).toEqual(['patchSheetImport']);
      expect(s.status).toBe('attention');
    });

    it('marks a step with nothing to open and nothing done as not available yet', () => {
      const s = step('output', { available: new Set() });
      expect(s.status).toBe('unavailable');
      expect(s.detail).toMatch(/^Not available yet/);
      expect(s.actions).toEqual([]);
    });

    it('with no rig open, says a rig step waits on step 1 rather than calling it missing', () => {
      const s = step('locate', { available: new Set<VenueActionKey>(['openDemo']) });
      expect(s.status).toBe('not_started');
      expect(s.detail).toContain('step 1');
      expect(s.detail).not.toMatch(/Not available yet/);
      // A step that means something without a rig still says it is missing.
      expect(step('output', { available: new Set<VenueActionKey>(['openDemo']) }).status).toBe('unavailable');
    });

    it('still reports a done step as done when its action is missing', () => {
      expect(step('output', { available: new Set(), output: ok('Sending ArtNet.') }).status).toBe('done');
    });
  });

  describe('skipping', () => {
    it('shows a skipped step as skipped, and moves next past it', () => {
      const steps = buildVenueSetupSteps(input({ skipped: new Set<VenueStepKey>(['venue']) }));
      expect(steps[0].status).toBe('skipped');
      const summary = summarizeVenueSetup(steps);
      expect(summary.skipped).toBe(1);
      expect(summary.next?.key).not.toBe('venue');
    });

    it('never hides a done step behind a skip', () => {
      const s = step('audio', { audio: ok('Hearing USB.'), skipped: new Set<VenueStepKey>(['audio']) });
      expect(s.status).toBe('done');
    });
  });
});

describe('summarizeVenueSetup', () => {
  it('counts done and attention steps', () => {
    const steps = buildVenueSetupSteps(
      input({
        rig: rig([fixture(), fixture({ tags: ['position_unconfirmed'] })], { hasScannedRoom: true }),
        conflictCount: 0,
        readiness: { ok: 3, warn: 0, fail: 0 },
        focus: { heads: 0, targets: 0 },
        audio: ok('Hearing USB.'),
        output: ok('Sending ArtNet.'),
      }),
    );
    const summary = summarizeVenueSetup(steps);
    expect(summary.total).toBe(9);
    // venue, patch, layout, readiness, focus, audio, output
    expect(summary.done).toBe(7);
    expect(summary.attention).toBe(1);
    expect(summary.next?.key).toBe('locate');
  });
});

describe('nextVenueStep', () => {
  const nearlyReady = (over: Partial<VenueSetupInput> = {}) =>
    input({
      rig: rig([fixture(), fixture({ tags: ['position_unconfirmed'] })], { hasScannedRoom: true }),
      conflictCount: 0,
      readiness: { ok: 3, warn: 0, fail: 0 },
      focus: { heads: 0, targets: 0 },
      audio: ok('Hearing USB.'),
      output: ok('Sending ArtNet.'),
      ...over,
    });

  it('is the first step that is not done, needing attention or not started alike', () => {
    expect(nextVenueStep(buildVenueSetupSteps(nearlyReady()))?.key).toBe('locate');
    expect(nextVenueStep(buildVenueSetupSteps(input()))?.key).toBe('venue');
  });

  it('passes over a skipped step', () => {
    const steps = buildVenueSetupSteps(nearlyReady({ skipped: new Set<VenueStepKey>(['locate']) }));
    expect(nextVenueStep(steps)?.key).toBe('export');
  });

  it('passes over a step that is not available yet, which has nothing to press', () => {
    const available = new Set<VenueActionKey>(ALL_ACTIONS);
    available.delete('locate');
    const steps = buildVenueSetupSteps(nearlyReady({ available }));
    expect(steps.find((s) => s.key === 'locate')!.status).toBe('attention');
    expect(steps.find((s) => s.key === 'locate')!.actions).toEqual([]);
    expect(nextVenueStep(steps)?.key).toBe('export');

    const noOutput = buildVenueSetupSteps(
      nearlyReady({ output: down('DMX output is not set up on the box.'), available: new Set<VenueActionKey>(['locate']) }),
    );
    expect(noOutput.find((s) => s.key === 'output')!.status).toBe('unavailable');
    expect(nextVenueStep(noOutput)?.key).toBe('locate');
  });

  it('is null once every step is done or skipped', () => {
    const steps = buildVenueSetupSteps(nearlyReady({ skipped: new Set<VenueStepKey>(['locate', 'export']) }));
    expect(nextVenueStep(steps)).toBeNull();
  });

  it('is what the summary reports as next', () => {
    const steps = buildVenueSetupSteps(nearlyReady());
    expect(summarizeVenueSetup(steps).next).toBe(nextVenueStep(steps));
  });
});

describe('venueSetupProgress', () => {
  const summary = (done: number, attention = 0, skipped = 0) => ({ total: 9, done, attention, skipped, next: null });

  it('says how many of the nine are done', () => {
    expect(venueSetupProgress(summary(6))).toBe('6 of 9 done.');
  });

  it('adds what needs attention and what was skipped', () => {
    expect(venueSetupProgress(summary(6, 1, 1))).toBe('6 of 9 done, 1 needs attention, 1 skipped.');
    expect(venueSetupProgress(summary(0, 2))).toBe('0 of 9 done, 2 need attention.');
  });
});

describe('skipped storage', () => {
  const memoryStore = (): KeyValueStore & { data: Map<string, string> } => {
    const data = new Map<string, string>();
    return {
      data,
      getItem: (k) => data.get(k) ?? null,
      setItem: (k, v) => { data.set(k, v); },
      removeItem: (k) => { data.delete(k); },
    };
  };

  it('round-trips per rig', () => {
    const store = memoryStore();
    saveSkipped(store, 7, new Set<VenueStepKey>(['focus', 'layout']));
    expect([...loadSkipped(store, 7)].sort()).toEqual(['focus', 'layout']);
    expect(loadSkipped(store, 8).size).toBe(0);
    expect(store.data.get(skippedStorageKey(7))).toBe('["layout","focus"]');
  });

  it('removes the entry when nothing is skipped', () => {
    const store = memoryStore();
    saveSkipped(store, 7, new Set<VenueStepKey>(['focus']));
    saveSkipped(store, 7, new Set());
    expect(store.data.has(skippedStorageKey(7))).toBe(false);
  });

  it('keys the no-rig checklist apart from any rig', () => {
    expect(skippedStorageKey(null)).toBe('venueSetup.skipped.none');
  });

  it('reads a corrupt or foreign entry as nothing skipped, keeping valid keys', () => {
    const store = memoryStore();
    store.setItem(skippedStorageKey(1), '{not json');
    expect(loadSkipped(store, 1).size).toBe(0);
    store.setItem(skippedStorageKey(2), JSON.stringify(['audio', 'bogus', 3]));
    expect([...loadSkipped(store, 2)]).toEqual(['audio']);
  });

  it('survives a store that throws', () => {
    const throwing: KeyValueStore = {
      getItem: () => { throw new Error('denied'); },
      setItem: () => { throw new Error('quota'); },
      removeItem: () => { throw new Error('denied'); },
    };
    expect(loadSkipped(throwing, 1).size).toBe(0);
    expect(() => saveSkipped(throwing, 1, new Set<VenueStepKey>(['audio']))).not.toThrow();
    expect(loadSkipped(null, 1).size).toBe(0);
  });

  it('toggles a step in and out', () => {
    const once = toggleSkipped(new Set(), 'audio');
    expect(once.has('audio')).toBe(true);
    expect(toggleSkipped(once, 'audio').has('audio')).toBe(false);
  });
});
