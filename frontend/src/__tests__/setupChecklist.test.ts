import { describe, expect, it } from 'vitest';
import type { EffectsStatus } from '../services/api';
import { buildSetupSteps, isReadyForShow } from '../utils/setupChecklist';
import type { HealthReading } from '../utils/showHealth';

const ok: HealthReading = { level: 'ok', label: 'ok', detail: 'fine' };
const down: HealthReading = { level: 'down', label: 'off', detail: 'No audio feed is being captured.' };

const effects = (over: Partial<EffectsStatus> = {}): EffectsStatus => ({
  running: true,
  auto_mode: true,
  current_state: 'sustain',
  bpm: 124,
  palette: 'house',
  strobe_enabled: true,
  movement_enabled: true,
  dimmer_enabled: true,
  color_enabled: true,
  live_rig_id: 3,
  live_rig_name: 'Main room',
  live_rig_demo: false,
  live_rig_fixtures: 24,
  ...over,
});

const stepFor = (key: string, steps: ReturnType<typeof buildSetupSteps>) => steps.find((s) => s.key === key)!;

describe('buildSetupSteps', () => {
  it('is ready when rig, output, audio and autopilot are all good', () => {
    const steps = buildSetupSteps({ effects: effects(), activeRig: { id: 3, name: 'Main room' }, dmx: ok, audio: ok });
    expect(isReadyForShow(steps)).toBe(true);
    expect(stepFor('rig', steps).detail).toBe('Main room, 24 fixtures.');
  });

  it('sends a fresh install to the rig wizard while the demo rig runs', () => {
    const steps = buildSetupSteps({ effects: effects({ live_rig_demo: true }), activeRig: null, dmx: ok, audio: ok });
    const rig = stepFor('rig', steps);
    expect(rig.state).toBe('todo');
    expect(rig.link?.to).toBe('/rigs/new/wizard');
    expect(isReadyForShow(steps)).toBe(false);
  });

  it('says a restart is needed when the active rig is not the one the engine runs', () => {
    const steps = buildSetupSteps({
      effects: effects(),
      activeRig: { id: 9, name: 'Patio' },
      dmx: ok,
      audio: ok,
    });
    const rig = stepFor('rig', steps);
    expect(rig.state).toBe('warn');
    expect(rig.detail).toContain('Restart the box');
  });

  it('points at the audio input when no feed is captured', () => {
    const steps = buildSetupSteps({ effects: effects(), activeRig: null, dmx: ok, audio: down });
    expect(stepFor('audio', steps)).toMatchObject({ state: 'todo' });
    expect(stepFor('audio', steps).detail).toContain('Audio input');
  });

  it('flags manual mode as not ready', () => {
    const steps = buildSetupSteps({ effects: effects({ auto_mode: false }), activeRig: null, dmx: ok, audio: ok });
    expect(stepFor('autopilot', steps).state).toBe('warn');
  });
});
