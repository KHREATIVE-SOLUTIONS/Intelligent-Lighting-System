import { afterEach, describe, expect, it } from 'vitest';
import {
  DPR_CAP,
  LABELS_DEFAULT_MAX_FIXTURES,
  PREVIZ_SHADOWS_KEY,
  defaultShowLabels,
  previzDpr,
  readViewToggle,
  writeViewToggle,
} from '../components/rig/previs/viewSettings';

describe('previzDpr', () => {
  it('caps each quality at its own ratio', () => {
    expect(previzDpr('balanced', 3)).toBe(1.5);
    expect(previzDpr('performance', 3)).toBe(1.25);
    expect(previzDpr('ultra', 3)).toBe(2);
    expect(DPR_CAP.balanced).toBe(1.5);
  });

  it('never draws more pixels than the screen has', () => {
    expect(previzDpr('ultra', 1)).toBe(1);
    expect(previzDpr('balanced', 1.25)).toBe(1.25);
  });

  it('treats a missing or broken ratio as 1 and never goes below 1', () => {
    expect(previzDpr('balanced', undefined)).toBe(1);
    expect(previzDpr('balanced', Number.NaN)).toBe(1);
    expect(previzDpr('balanced', 0)).toBe(1);
    expect(previzDpr('balanced', 0.5)).toBe(1);
  });
});

describe('defaultShowLabels', () => {
  it('is off in the club view whatever the rig', () => {
    expect(defaultShowLabels(true, 4)).toBe(false);
  });

  it('is on for a small bare rig and off for a big one', () => {
    expect(defaultShowLabels(false, 12)).toBe(true);
    expect(defaultShowLabels(false, LABELS_DEFAULT_MAX_FIXTURES)).toBe(true);
    expect(defaultShowLabels(false, LABELS_DEFAULT_MAX_FIXTURES + 1)).toBe(false);
    expect(defaultShowLabels(false, 131)).toBe(false);
  });
});

describe('view toggles in localStorage', () => {
  afterEach(() => window.localStorage.removeItem(PREVIZ_SHADOWS_KEY));

  it('reads null until a choice is written, then the choice', () => {
    window.localStorage.removeItem(PREVIZ_SHADOWS_KEY);
    expect(readViewToggle(PREVIZ_SHADOWS_KEY)).toBeNull();
    writeViewToggle(PREVIZ_SHADOWS_KEY, true);
    expect(readViewToggle(PREVIZ_SHADOWS_KEY)).toBe(true);
    writeViewToggle(PREVIZ_SHADOWS_KEY, false);
    expect(readViewToggle(PREVIZ_SHADOWS_KEY)).toBe(false);
  });

  it('ignores a value it did not write', () => {
    window.localStorage.setItem(PREVIZ_SHADOWS_KEY, 'maybe');
    expect(readViewToggle(PREVIZ_SHADOWS_KEY)).toBeNull();
  });
});
