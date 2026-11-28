import { describe, expect, it } from 'vitest';
import { dbToFraction, meterFromMessage, meterHint } from '../components/common/levelMeterLogic';

describe('level meter logic', () => {
  it('reads the meter block out of an analysis message', () => {
    expect(meterFromMessage({ type: 'analysis', meter: { rms: 0.2, running: true } })).toEqual({
      rms: 0.2,
      running: true,
    });
    expect(meterFromMessage({ type: 'analysis' })).toBeNull();
    expect(meterFromMessage(null)).toBeNull();
  });

  it('maps dBFS onto the bar', () => {
    expect(dbToFraction(0)).toBe(1);
    expect(dbToFraction(-60)).toBe(0);
    expect(dbToFraction(-120)).toBe(0);
    expect(dbToFraction(-30)).toBeCloseTo(0.5);
    expect(dbToFraction(undefined)).toBe(0);
  });

  it('says why there is nothing to see', () => {
    expect(meterHint(null, null, 0)).toMatch(/waiting/i);
    expect(meterHint({ running: false }, null, 0)).toMatch(/not running/i);
    expect(meterHint({ running: true }, 0, 500)).toBeNull();
    expect(meterHint({ running: true }, 0, 2000)).toMatch(/signal too low/i);
    expect(meterHint({ running: true }, null, 2000)).toBeNull();
  });
});
