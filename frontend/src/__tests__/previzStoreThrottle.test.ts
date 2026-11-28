import { describe, expect, it, vi } from 'vitest';
import {
  createLightingWriter, createTrailingThrottle, sameValue,
} from '../components/rig/previs/storeThrottle';
import type { LightingSetters, ThrottleClock } from '../components/rig/previs/storeThrottle';

function fakeClock() {
  let now = 0;
  const timers: Array<{ at: number; fn: () => void; id: number }> = [];
  let nextId = 1;
  const clock: ThrottleClock = {
    now: () => now,
    setTimeout: (fn, ms) => {
      const id = nextId++;
      timers.push({ at: now + ms, fn, id });
      return id;
    },
    clearTimeout: (id) => {
      const i = timers.findIndex((t) => t.id === id);
      if (i >= 0) timers.splice(i, 1);
    },
  };
  const advance = (ms: number) => {
    const end = now + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const due = timers[0];
      if (!due || due.at > end) break;
      timers.shift();
      now = due.at;
      due.fn();
    }
    now = end;
  };
  return { clock, advance, pending: () => timers.length };
}

describe('sameValue', () => {
  it('compares plain values, arrays and objects by content', () => {
    expect(sameValue(1, 1)).toBe(true);
    expect(sameValue([1, 2, 3], [1, 2, 3])).toBe(true);
    expect(sameValue([1, 2, 3], [1, 2, 4])).toBe(false);
    expect(sameValue({ a: [1, { b: 2 }] }, { a: [1, { b: 2 }] })).toBe(true);
    expect(sameValue({ a: 1 }, { a: 1, b: 2 })).toBe(false);
    expect(sameValue(null, {})).toBe(false);
    expect(sameValue(undefined, [1])).toBe(false);
  });
});

describe('createTrailingThrottle', () => {
  it('writes the first request at once and at most once per interval after', () => {
    const { clock, advance } = fakeClock();
    const flush = vi.fn();
    const throttle = createTrailingThrottle(flush, 100, clock);
    throttle.request();
    expect(flush).toHaveBeenCalledTimes(1);
    // 30 messages a second for one second.
    for (let i = 0; i < 30; i += 1) {
      advance(33);
      throttle.request();
    }
    advance(200);
    expect(flush.mock.calls.length).toBeLessThanOrEqual(11 + 1);
    expect(flush.mock.calls.length).toBeGreaterThanOrEqual(9);
  });

  it('always makes a trailing write for the last request', () => {
    const { clock, advance } = fakeClock();
    const flush = vi.fn();
    const throttle = createTrailingThrottle(flush, 100, clock);
    throttle.request();
    advance(10);
    throttle.request();
    expect(flush).toHaveBeenCalledTimes(1);
    advance(100);
    expect(flush).toHaveBeenCalledTimes(2);
  });

  it('writes nothing after cancel', () => {
    const { clock, advance, pending } = fakeClock();
    const flush = vi.fn();
    const throttle = createTrailingThrottle(flush, 100, clock);
    throttle.request();
    advance(10);
    throttle.request();
    throttle.cancel();
    expect(pending()).toBe(0);
    advance(500);
    expect(flush).toHaveBeenCalledTimes(1);
  });
});

function setters() {
  return {
    setUniverse: vi.fn(),
    setFixtureStates: vi.fn(),
    setEffectsInfo: vi.fn(),
    setGenre: vi.fn(),
    setSection: vi.fn(),
    setActiveEffects: vi.fn(),
    setKeyLightingZones: vi.fn(),
    setEmotionVector: vi.fn(),
    setBeatPhrase: vi.fn(),
  } satisfies LightingSetters;
}

describe('createLightingWriter', () => {
  it('merges messages field by field and writes the latest of each', () => {
    const s = setters();
    const writer = createLightingWriter(s);
    writer.ingest({ genre: 'house', dmx_frames: { 0: [1, 2], 1: [3] } });
    writer.ingest({ section: 'drop', section_intensity: 0.9, dmx_frames: { 0: [5, 6] } });
    writer.flush();
    expect(s.setGenre).toHaveBeenCalledWith('house');
    expect(s.setSection).toHaveBeenCalledWith('drop', 0.9);
    expect(s.setUniverse).toHaveBeenCalledTimes(2);
    expect(s.setUniverse).toHaveBeenCalledWith(0, [5, 6]);
    expect(s.setUniverse).toHaveBeenCalledWith(1, [3]);
  });

  it('skips a setter whose value did not change', () => {
    const s = setters();
    const writer = createLightingWriter(s);
    const message = { genre: 'techno', key_zones: [{ zone: 'MSC', active: true }], dmx_frame: [1, 2, 3], dmx_universe: 0 };
    writer.ingest(message);
    expect(writer.flush()).toBe(3);
    writer.ingest(JSON.parse(JSON.stringify(message)));
    expect(writer.flush()).toBe(0);
    expect(s.setKeyLightingZones).toHaveBeenCalledTimes(1);
    writer.ingest({ ...message, dmx_frame: [1, 2, 4] });
    expect(writer.flush()).toBe(1);
    expect(s.setUniverse).toHaveBeenLastCalledWith(0, [1, 2, 4]);
  });

  it('fills the defaults the handler used to', () => {
    const s = setters();
    const writer = createLightingWriter(s);
    writer.ingest({ state: 'run', beat_phrase: 3 });
    writer.flush();
    expect(s.setEffectsInfo).toHaveBeenCalledWith('run', 'none', 'none');
    expect(s.setBeatPhrase).toHaveBeenCalledWith(3, 4);
  });
});
