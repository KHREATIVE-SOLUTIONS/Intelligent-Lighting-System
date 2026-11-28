/**
 * Writing the analysis stream into the zustand store at most a few times a
 * second (docs/PREVIZ_PERFORMANCE.md).
 *
 * The socket sends about 30 messages a second. The 3D view reads the output
 * frames through a ref (outputFeed.ts) on every message, so it does not need
 * the store to keep up; the store feeds text readouts and other pages. Every
 * store write makes every subscriber compare its slice, and a slice that is a
 * new array or object each time re-renders whether it changed or not.
 *
 * So each message is merged into what is waiting to be written, field by field
 * (messages carry different subsets), and the waiting values are written at
 * most once per interval, with a trailing write so the last message is never
 * lost. A value equal to the last one written is not written again.
 */

/** Structural equality for the plain JSON-ish values the socket sends. */
export function sameValue(a: unknown, b: unknown, depth = 6): boolean {
  if (Object.is(a, b)) return true;
  if (depth <= 0 || a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  const aList = Array.isArray(a) || ArrayBuffer.isView(a);
  const bList = Array.isArray(b) || ArrayBuffer.isView(b);
  if (aList !== bList) return false;
  if (aList) {
    const x = a as ArrayLike<unknown>;
    const y = b as ArrayLike<unknown>;
    if (x.length !== y.length) return false;
    for (let i = 0; i < x.length; i += 1) {
      if (!sameValue(x[i], y[i], depth - 1)) return false;
    }
    return true;
  }
  const xKeys = Object.keys(a as object);
  const yKeys = Object.keys(b as object);
  if (xKeys.length !== yKeys.length) return false;
  for (const key of xKeys) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) return false;
    if (!sameValue((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key], depth - 1)) return false;
  }
  return true;
}

export type ThrottleClock = {
  now: () => number;
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
};

const realClock: ThrottleClock = {
  now: () => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** At most 10 store writes a second. */
export const STORE_WRITE_INTERVAL_MS = 100;

export type TrailingThrottle = {
  /** Something is waiting: write now if the interval has passed, else once it has. */
  request: () => void;
  /** Drop a pending write (unmount). */
  cancel: () => void;
};

/**
 * Calls `flush` at most once per `intervalMs`: straight away when the last
 * call was long enough ago, otherwise once, at the end of the interval.
 */
export function createTrailingThrottle(
  flush: () => void,
  intervalMs = STORE_WRITE_INTERVAL_MS,
  clock: ThrottleClock = realClock,
): TrailingThrottle {
  let last = -Infinity;
  let timer: unknown = null;
  const run = () => {
    timer = null;
    last = clock.now();
    flush();
  };
  return {
    request: () => {
      if (timer !== null) return;
      const wait = last + intervalMs - clock.now();
      if (wait <= 0) run();
      else timer = clock.setTimeout(run, wait);
    },
    cancel: () => {
      if (timer !== null) clock.clearTimeout(timer);
      timer = null;
    },
  };
}

/** The store setters the analysis stream feeds. */
export type LightingSetters = {
  setUniverse: (universe: number, data: number[]) => void;
  setFixtureStates: (fixtures: any[]) => void;
  setEffectsInfo: (state: string, movement: string, dimmer: string) => void;
  setGenre: (genre: any) => void;
  setSection: (section: any, intensity: number) => void;
  setActiveEffects: (effects: any) => void;
  setKeyLightingZones: (zones: any[]) => void;
  setEmotionVector: (emotion: any) => void;
  setBeatPhrase: (phrase: number, beatsPerPhrase: number) => void;
};

type FieldName = 'fixtures' | 'effects' | 'genre' | 'section' | 'proEffects' | 'keyZones' | 'emotion' | 'beatPhrase';

export type LightingWriter = {
  /** Merge one message's `lighting` block into what is waiting to be written. */
  ingest: (lighting: any) => void;
  /** Write what is waiting and has changed. Returns how many setters were called. */
  flush: () => number;
};

/**
 * Collects the `lighting` blocks of analysis messages and writes them to the
 * store through `setters`, skipping any value equal to the last one written.
 */
export function createLightingWriter(setters: LightingSetters): LightingWriter {
  const pending = new Map<FieldName, unknown>();
  const pendingUniverses = new Map<number, number[]>();
  const written = new Map<FieldName, unknown>();
  const writtenUniverses = new Map<number, number[]>();

  return {
    ingest: (l) => {
      if (!l || typeof l !== 'object') return;
      if (l.dmx_frames && typeof l.dmx_frames === 'object') {
        for (const [universe, frame] of Object.entries(l.dmx_frames)) {
          pendingUniverses.set(Number(universe) || 0, frame as number[]);
        }
      } else if (l.dmx_frame) {
        pendingUniverses.set(Number(l.dmx_universe) || 0, l.dmx_frame);
      }
      if (l.fixtures) pending.set('fixtures', l.fixtures);
      if (l.state) pending.set('effects', [l.state, l.movement || 'none', l.dimmer || 'none']);
      if (l.genre) pending.set('genre', l.genre);
      if (l.section) pending.set('section', [l.section, l.section_intensity ?? 0]);
      if (l.pro_effects) pending.set('proEffects', l.pro_effects);
      if (l.key_zones) pending.set('keyZones', l.key_zones);
      if (l.emotion_vector) pending.set('emotion', l.emotion_vector);
      if (l.beat_phrase !== undefined) pending.set('beatPhrase', [l.beat_phrase, l.beats_per_phrase ?? 4]);
    },
    flush: () => {
      let calls = 0;
      for (const [universe, frame] of pendingUniverses) {
        if (!sameValue(writtenUniverses.get(universe), frame, 1)) {
          setters.setUniverse(universe, frame);
          writtenUniverses.set(universe, frame);
          calls += 1;
        }
      }
      pendingUniverses.clear();
      for (const [field, value] of pending) {
        if (sameValue(written.get(field), value)) continue;
        written.set(field, value);
        calls += 1;
        const pair = value as [any, any, any];
        switch (field) {
          case 'fixtures': setters.setFixtureStates(value as any[]); break;
          case 'effects': setters.setEffectsInfo(pair[0], pair[1], pair[2]); break;
          case 'genre': setters.setGenre(value); break;
          case 'section': setters.setSection(pair[0], pair[1]); break;
          case 'proEffects': setters.setActiveEffects(value); break;
          case 'keyZones': setters.setKeyLightingZones(value as any[]); break;
          case 'emotion': setters.setEmotionVector(value); break;
          case 'beatPhrase': setters.setBeatPhrase(pair[0], pair[1]); break;
          default: break;
        }
      }
      pending.clear();
      return calls;
    },
  };
}
