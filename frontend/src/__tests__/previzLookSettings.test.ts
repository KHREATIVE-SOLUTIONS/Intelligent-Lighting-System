import { afterEach, describe, expect, it } from 'vitest';
import { DEFAULT_HAZE } from '../components/rig/previs/beamLook';
import {
  DEFAULT_EXPOSURE,
  DEFAULT_LOOK,
  EXPOSURE_MAX,
  EXPOSURE_MIN,
  PREVIZ_LOOK_KEY,
  bloomFor,
  canvasExposure,
  defaultBloom,
  fogDensity,
  parseLookSettings,
  readLookSettings,
  staticHazeStrength,
  withBloom,
  writeLookSettings,
} from '../components/rig/previs/lookSettings';
import { hazeNoisePixels, layoutHazePuffs, seededRandom } from '../components/rig/previs/hazePuffs';

describe('look settings', () => {
  afterEach(() => window.localStorage.removeItem(PREVIZ_LOOK_KEY));

  it('starts at the defaults with nothing stored, or something unreadable', () => {
    window.localStorage.removeItem(PREVIZ_LOOK_KEY);
    expect(readLookSettings()).toEqual(DEFAULT_LOOK);
    for (const raw of [null, '', 'not json', '42', 'null', '[]']) expect(parseLookSettings(raw)).toEqual(DEFAULT_LOOK);
  });

  it('keeps what was chosen across a reload', () => {
    const chosen = withBloom({ ...DEFAULT_LOOK, haze: 0.8, exposure: 1.5, softBeams: false, gobos: false, hazeDrift: false }, 'ultra', false);
    writeLookSettings(chosen);
    expect(readLookSettings()).toEqual(chosen);
  });

  it('holds stored numbers to their range and ignores the wrong kinds', () => {
    const parsed = parseLookSettings(JSON.stringify({
      haze: 7, exposure: -1, softBeams: 'yes', gobos: 0, hazeDrift: true, bloom: { balanced: false, ultra: 'on', nonsense: true },
    }));
    expect(parsed.haze).toBe(1);
    expect(parsed.exposure).toBe(EXPOSURE_MIN);
    expect(parsed.softBeams).toBe(DEFAULT_LOOK.softBeams);
    expect(parsed.gobos).toBe(DEFAULT_LOOK.gobos);
    expect(parsed.hazeDrift).toBe(true);
    expect(parsed.bloom).toEqual({ balanced: false });
    expect(parseLookSettings(JSON.stringify({ exposure: 99 })).exposure).toBe(EXPOSURE_MAX);
    expect(parseLookSettings(JSON.stringify({ haze: Number.NaN })).haze).toBe(DEFAULT_HAZE);
  });

  it('has bloom on except in Perf until chosen, and remembers the choice per quality', () => {
    expect(defaultBloom('performance')).toBe(false);
    expect(defaultBloom('balanced')).toBe(true);
    expect(defaultBloom('ultra')).toBe(true);
    const off = withBloom(DEFAULT_LOOK, 'balanced', false);
    expect(bloomFor(off, 'balanced')).toBe(false);
    expect(bloomFor(off, 'ultra')).toBe(true);
    expect(bloomFor(off, 'performance')).toBe(false);
    // The defaults themselves are left alone.
    expect(DEFAULT_LOOK.bloom).toEqual({});
  });

  it('draws at the exposure and fog the view always had, at the defaults', () => {
    expect(canvasExposure(DEFAULT_EXPOSURE, 'balanced')).toBeCloseTo(1.2, 9);
    expect(canvasExposure(DEFAULT_EXPOSURE, 'ultra')).toBeCloseTo(1.32, 9);
    expect(fogDensity(DEFAULT_HAZE)).toBeCloseTo(0.006, 9);
    expect(fogDensity(0)).toBeLessThan(fogDensity(1));
    expect(fogDensity(0)).toBeGreaterThan(0);
    expect(staticHazeStrength(DEFAULT_HAZE)).toBeCloseTo(1, 9);
    expect(staticHazeStrength(0)).toBe(0);
  });
});

describe('drifting haze', () => {
  it('is the same haze every load', () => {
    const a = seededRandom(3);
    const b = seededRandom(3);
    for (let i = 0; i < 5; i += 1) expect(a()).toBe(b());
    expect(Array.from(hazeNoisePixels(16, 5))).toEqual(Array.from(hazeNoisePixels(16, 5)));
  });

  it('is a soft cloud that never shows the edge of its square', () => {
    const size = 64;
    const pixels = hazeNoisePixels(size);
    expect(pixels.length).toBe(size * size * 4);
    const at = (x: number, y: number) => pixels[(y * size + x) * 4];
    for (let i = 0; i < size; i += 1) {
      expect(at(i, 0)).toBe(0);
      expect(at(0, i)).toBe(0);
      expect(at(i, size - 1)).toBe(0);
      expect(at(size - 1, i)).toBe(0);
    }
    let lit = 0;
    for (let k = 0; k < pixels.length; k += 4) if (pixels[k] > 0) lit += 1;
    expect(lit).toBeGreaterThan(size * size * 0.1);
  });

  it('hangs its puffs in the air of the room', () => {
    const bounds = { xMin: -8, xMax: 8, zMin: -6, zMax: 10, floorY: 0, ceilingY: 6 };
    const { puff, seed } = layoutHazePuffs(8, bounds);
    expect(puff.length).toBe(32);
    expect(seed.length).toBe(16);
    for (let i = 0; i < 8; i += 1) {
      expect(puff[i * 4]).toBeGreaterThanOrEqual(bounds.xMin);
      expect(puff[i * 4]).toBeLessThanOrEqual(bounds.xMax);
      expect(puff[i * 4 + 1]).toBeGreaterThanOrEqual(1.4);
      expect(puff[i * 4 + 1]).toBeLessThanOrEqual(bounds.ceilingY - 0.6);
      expect(puff[i * 4 + 2]).toBeGreaterThanOrEqual(bounds.zMin);
      expect(puff[i * 4 + 2]).toBeLessThanOrEqual(bounds.zMax);
      expect(puff[i * 4 + 3]).toBeGreaterThan(0);
    }
    expect(layoutHazePuffs(0, bounds).puff.length).toBe(0);
  });
});
