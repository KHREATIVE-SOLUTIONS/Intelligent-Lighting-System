import { describe, expect, it } from 'vitest';
import type { BoxHealthPayload } from '../utils/showHealth';
import { readAudioHealth, readDatabaseHealth, readDmxHealth } from '../utils/showHealth';
import { buildSetupSteps } from '../utils/setupChecklist';
import { useHealthStore } from '../stores/healthStore';

const held: BoxHealthPayload = {
  status: 'healthy',
  services: { database: 'connected', audio_input: 'live' },
  dmx_detail: { connected: true, transmitting: false, output_held_until_rig_patched: true },
};

const capturing = { available: true, running: true, last_rms: 0.2, device_name: 'Desk feed' };

describe('box health report', () => {
  it('says the box is waiting for a rig instead of calling held output stalled', () => {
    const reading = readDmxHealth({ status: 'connected', connected: true, transmitting: false }, true, held);
    expect(reading.level).toBe('warn');
    expect(reading.label).toBe('Waiting for rig');
    expect(reading.detail).toContain('Waiting for a rig to be patched');
  });

  it('still calls it stalled once a real rig is patched', () => {
    const live = { ...held, dmx_detail: { output_held_until_rig_patched: false } };
    const reading = readDmxHealth({ status: 'connected', connected: true, transmitting: false }, true, live);
    expect(reading.label).toBe('DMX stalled');
  });

  it('marks audio lost when the engine stops hearing it, even with capture running', () => {
    const lost = { ...held, services: { ...held.services, audio_input: 'lost' as const } };
    const reading = readAudioHealth(capturing, true, Date.now(), Date.now(), lost);
    expect(reading.level).toBe('down');
    expect(reading.label).toBe('Audio lost');
    expect(reading.detail).toContain('Desk feed');
  });

  it('counts a feed sent to the box as live even with no local capture', () => {
    const reading = readAudioHealth({ available: true, running: false }, true, Date.now(), Date.now(), held);
    expect(reading.level).toBe('ok');
  });

  it('reads as before when the box does not send the report', () => {
    expect(readAudioHealth(capturing, true, Date.now(), Date.now(), null).label).toBe('Audio live');
    expect(readDatabaseHealth(null, true)).toBeNull();
  });

  it('raises a missing database and points the rig step at a restart', () => {
    const noDb = { ...held, services: { ...held.services, database: 'unavailable' as const } };
    expect(readDatabaseHealth(noDb, true)?.level).toBe('down');
    expect(readDatabaseHealth(noDb, false)).toBeNull();

    const ok = { level: 'ok' as const, label: 'ok', detail: 'fine' };
    const steps = buildSetupSteps({ effects: null, activeRig: null, dmx: ok, audio: ok, database: 'unavailable' });
    const rig = steps.find((s) => s.key === 'rig')!;
    expect(rig.state).toBe('todo');
    expect(rig.detail).toContain('Restart the box');
    expect(rig.link).toBeUndefined();
  });

  it('keeps the last report through one missed health read', () => {
    useHealthStore.setState({ box: null });
    const base = { reachable: true, dmx: null, capture: null, effects: null };
    useHealthStore.getState().setPoll({ ...base, box: held });
    useHealthStore.getState().setPoll({ ...base, box: null });
    expect(useHealthStore.getState().box).toBe(held);
  });
});
