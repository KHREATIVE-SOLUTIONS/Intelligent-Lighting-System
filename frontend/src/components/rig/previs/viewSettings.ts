/**
 * View settings for the 3D previz that are pure choices: how many pixels the
 * canvas draws, whether fixture labels show before the operator picks, and the
 * on/off toggles kept in localStorage (docs/PREVIZ_PERFORMANCE.md).
 */

export type PrevizQuality = 'performance' | 'balanced' | 'ultra';

/** The most device pixels per CSS pixel each quality draws. */
export const DPR_CAP: Record<PrevizQuality, number> = {
  performance: 1.25,
  balanced: 1.5,
  ultra: 2,
};

/**
 * The canvas pixel ratio for a quality on a screen of `deviceRatio`. Never more
 * than the screen has (no point drawing pixels nobody sees), never more than
 * the quality's cap (a 4K monitor at 150 % scaling would otherwise ask for
 * twice the pixels of 1440p), and never below 1. A ratio the browser does not
 * give, or gives as nonsense, counts as 1.
 */
export function previzDpr(quality: PrevizQuality, deviceRatio: number | undefined): number {
  const screen = typeof deviceRatio === 'number' && Number.isFinite(deviceRatio) && deviceRatio > 0 ? deviceRatio : 1;
  const cap = DPR_CAP[quality] ?? DPR_CAP.balanced;
  return Math.max(1, Math.min(screen, cap));
}

/** Above this many fixtures the ID labels start off, even on the bare rig. */
export const LABELS_DEFAULT_MAX_FIXTURES = 40;

/**
 * Whether fixture ID labels show before the operator has chosen. Each label is
 * an HTML element moved by the frame loop, so on a big rig they cost more than
 * the fixtures do. Off in the club view, as before; on for the bare rig only
 * when the rig is small enough for them to be readable and cheap.
 */
export function defaultShowLabels(showVenue: boolean, fixtureCount: number): boolean {
  return !showVenue && fixtureCount <= LABELS_DEFAULT_MAX_FIXTURES;
}

/** localStorage keys for the previz's own view toggles. Not per rig: they are about the machine. */
export const PREVIZ_SHADOWS_KEY = 'previz:shadows';
export const PREVIZ_STATS_KEY = 'previz:stats';

/** A stored on/off choice, or null when none was made (or storage is not there). */
export function readViewToggle(key: string): boolean | null {
  try {
    const stored = window.localStorage.getItem(key);
    return stored === 'on' ? true : stored === 'off' ? false : null;
  } catch {
    return null;
  }
}

export function writeViewToggle(key: string, on: boolean): void {
  try {
    window.localStorage.setItem(key, on ? 'on' : 'off');
  } catch {
    // Private mode or a full store: the choice holds for this visit only.
  }
}
