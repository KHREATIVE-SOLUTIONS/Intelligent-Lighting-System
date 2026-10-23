import { beforeEach, describe, expect, it } from 'vitest';
import { normalizeGenre, normalizeSection, useDMXStore } from '../stores/dmxStore';

describe('engine value normalization', () => {
  it('maps the engine enum values to the UI keys', () => {
    expect(normalizeSection('verse')).toBe('VERSE');
    expect(normalizeSection('pre_chorus')).toBe('PRE_CHORUS');
    expect(normalizeGenre('hip_hop')).toBe('HIP_HOP');
  });

  it('falls back instead of showing garbage', () => {
    expect(normalizeSection('waltz')).toBe('UNKNOWN');
    expect(normalizeSection(undefined)).toBe('UNKNOWN');
    expect(normalizeGenre('polka')).toBeNull();
  });
});

describe('section history', () => {
  beforeEach(() => useDMXStore.getState().clearAll());

  it('records a section once, not once per frame', () => {
    const { setSection } = useDMXStore.getState();
    for (let i = 0; i < 30; i++) setSection('verse', 0.4);
    setSection('chorus', 0.8);
    for (let i = 0; i < 30; i++) setSection('chorus', 0.9);

    const { proLighting } = useDMXStore.getState();
    expect(proLighting.sectionHistory.map((e) => e.section)).toEqual(['VERSE', 'CHORUS']);
    expect(proLighting.section).toBe('CHORUS');
    expect(proLighting.sectionIntensity).toBe(0.9);
    expect(proLighting.sectionHistory[0].endTime).toBeDefined();
  });
});
