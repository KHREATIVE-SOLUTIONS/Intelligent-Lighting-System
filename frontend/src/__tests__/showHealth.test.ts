import { describe, expect, it } from 'vitest';
import {
  ANALYSIS_STALE_MS,
  readAudioHealth,
  readDmxHealth,
  readLinkHealth,
} from '../utils/showHealth';

describe('readDmxHealth', () => {
  it('reports frames per second when ArtNet is flowing', () => {
    const reading = readDmxHealth(
      { status: 'connected', connected: true, transmitting: true, fps: 43.7, target_ip: '2.0.0.10' },
      true
    );
    expect(reading.level).toBe('ok');
    expect(reading.label).toBe('DMX 44 fps');
    expect(reading.detail).toContain('2.0.0.10');
  });

  it('flags a connected node that has stopped receiving frames', () => {
    const reading = readDmxHealth({ status: 'connected', connected: true, transmitting: false }, true);
    expect(reading.level).toBe('warn');
    expect(reading.label).toBe('DMX stalled');
  });

  it('names the failing universe on a send error', () => {
    const reading = readDmxHealth(
      { connected: true, transmitting: false, last_send_error: 'Network unreachable', failing_universes: [2] },
      true
    );
    expect(reading.level).toBe('down');
    expect(reading.detail).toContain('universe 2');
    expect(reading.detail).toContain('Network unreachable');
  });

  it('says it does not know rather than claiming DMX is off when the box is unreachable', () => {
    expect(readDmxHealth(null, false).level).toBe('unknown');
  });
});

describe('readAudioHealth', () => {
  const now = 100_000;

  it('is live with signal and fresh analysis', () => {
    const reading = readAudioHealth(
      { available: true, running: true, last_rms: 0.2, device_name: 'Desk L/R' },
      true,
      now - 100,
      now
    );
    expect(reading.level).toBe('ok');
    expect(reading.detail).toContain('Desk L/R');
  });

  it('warns on a silent feed', () => {
    const reading = readAudioHealth({ available: true, running: true, last_rms: 0 }, true, now, now);
    expect(reading).toMatchObject({ level: 'warn', label: 'No signal' });
  });

  it('warns when analysis stops updating even though capture runs', () => {
    const reading = readAudioHealth(
      { available: true, running: true, last_rms: 0.3 },
      true,
      now - ANALYSIS_STALE_MS - 1,
      now
    );
    expect(reading).toMatchObject({ level: 'warn', label: 'Audio stalled' });
  });

  it('is down when nothing is being captured', () => {
    expect(readAudioHealth({ available: true, running: false }, true, null, now).level).toBe('down');
  });
});

describe('readLinkHealth', () => {
  it('reports the box offline before anything about the socket', () => {
    expect(readLinkHealth('connected', false)).toMatchObject({ level: 'down', label: 'Box offline' });
  });

  it('distinguishes a blip from a lost link', () => {
    expect(readLinkHealth('reconnecting', true).level).toBe('warn');
    expect(readLinkHealth('lost', true).level).toBe('down');
    expect(readLinkHealth('connected', true).level).toBe('ok');
  });
});
