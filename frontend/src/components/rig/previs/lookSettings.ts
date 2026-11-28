/**
 * The look controls of the 3D previz: haze, bloom, exposure, soft beams,
 * gobos and the drifting haze (docs/PREVIZ_LOOK.md). Pure choices and the
 * numbers they turn into, kept in localStorage like the other view toggles:
 * they are about the machine and the operator's taste, not the rig.
 */
import { DEFAULT_HAZE } from './beamLook';
import type { PrevizQuality } from './viewSettings';

export const PREVIZ_LOOK_KEY = 'previz:look';

export const EXPOSURE_MIN = 0.4;
export const EXPOSURE_MAX = 2.5;
/** What the view was always drawn at (Ultra a tenth brighter, see canvasExposure). */
export const DEFAULT_EXPOSURE = 1.2;

export type LookSettings = {
  /** 0 clean air to 1 thick haze. */
  haze: number;
  /** Tone mapping exposure, before the Ultra lift. */
  exposure: number;
  softBeams: boolean;
  gobos: boolean;
  /** The few large drifting haze puffs. */
  hazeDrift: boolean;
  /** Bloom per quality, where the operator has chosen; the rest follow defaultBloom. */
  bloom: Partial<Record<PrevizQuality, boolean>>;
};

export const DEFAULT_LOOK: LookSettings = {
  haze: DEFAULT_HAZE,
  exposure: DEFAULT_EXPOSURE,
  softBeams: true,
  gobos: true,
  hazeDrift: true,
  bloom: {},
};

const QUALITIES: PrevizQuality[] = ['performance', 'balanced', 'ultra'];

/** Bloom starts on except in Perf, where every millisecond is the point. */
export function defaultBloom(quality: PrevizQuality): boolean {
  return quality !== 'performance';
}

export function bloomFor(settings: LookSettings, quality: PrevizQuality): boolean {
  return settings.bloom[quality] ?? defaultBloom(quality);
}

/** The settings with bloom turned `on` for `quality` only. */
export function withBloom(settings: LookSettings, quality: PrevizQuality, on: boolean): LookSettings {
  return { ...settings, bloom: { ...settings.bloom, [quality]: on } };
}

const clamp = (value: number, lo: number, hi: number) => (value < lo ? lo : value > hi ? hi : value);

function number(value: unknown, fallback: number, lo: number, hi: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? clamp(value, lo, hi) : fallback;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

/**
 * Settings from what was stored. Anything missing, of the wrong kind or out
 * of range falls back to (or is held to) the default, so an old or hand-edited
 * entry can never leave the view unusable.
 */
export function parseLookSettings(raw: string | null | undefined): LookSettings {
  if (!raw) return { ...DEFAULT_LOOK, bloom: {} };
  let stored: unknown;
  try {
    stored = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_LOOK, bloom: {} };
  }
  if (!stored || typeof stored !== 'object') return { ...DEFAULT_LOOK, bloom: {} };
  const s = stored as Record<string, unknown>;
  const bloom: Partial<Record<PrevizQuality, boolean>> = {};
  if (s.bloom && typeof s.bloom === 'object') {
    const b = s.bloom as Record<string, unknown>;
    for (const quality of QUALITIES) if (typeof b[quality] === 'boolean') bloom[quality] = b[quality] as boolean;
  }
  return {
    haze: number(s.haze, DEFAULT_LOOK.haze, 0, 1),
    exposure: number(s.exposure, DEFAULT_LOOK.exposure, EXPOSURE_MIN, EXPOSURE_MAX),
    softBeams: flag(s.softBeams, DEFAULT_LOOK.softBeams),
    gobos: flag(s.gobos, DEFAULT_LOOK.gobos),
    hazeDrift: flag(s.hazeDrift, DEFAULT_LOOK.hazeDrift),
    bloom,
  };
}

export function readLookSettings(): LookSettings {
  try {
    return parseLookSettings(window.localStorage.getItem(PREVIZ_LOOK_KEY));
  } catch {
    return parseLookSettings(null);
  }
}

export function writeLookSettings(settings: LookSettings): void {
  try {
    window.localStorage.setItem(PREVIZ_LOOK_KEY, JSON.stringify(settings));
  } catch {
    // Private mode or a full store: the choice holds for this visit only.
  }
}

/** The renderer's exposure: the setting, Ultra a tenth brighter as it always was. */
export function canvasExposure(exposure: number, quality: PrevizQuality): number {
  return exposure * (quality === 'ultra' ? 1.1 : 1);
}

/** Scene fog (FogExp2) density: a trace in clean air, the old 0.006 at the default haze. */
export const FOG_CLEAR_AIR = 0.0015;
export const FOG_PER_HAZE = 0.009;
export function fogDensity(haze: number): number {
  return FOG_CLEAR_AIR + FOG_PER_HAZE * clamp(Number.isFinite(haze) ? haze : 0, 0, 1);
}

/**
 * How strongly the old static haze (the faint sheets and the specks) draws:
 * 1 at the default haze, as it always was; nothing in clean air.
 */
export function staticHazeStrength(haze: number): number {
  return clamp(Number.isFinite(haze) ? haze : 0, 0, 1) / DEFAULT_HAZE;
}

/** Drifting haze puffs per quality. Each is a big additive quad: fill rate, not draw calls. */
export const HAZE_DRIFT_COUNT: Record<PrevizQuality, number> = {
  performance: 5,
  balanced: 8,
  ultra: 12,
};

/** MSAA samples for the bloom render target: none in Perf, where bloom starts off anyway. */
export const BLOOM_SAMPLES: Record<PrevizQuality, number> = {
  performance: 0,
  balanced: 4,
  ultra: 4,
};
