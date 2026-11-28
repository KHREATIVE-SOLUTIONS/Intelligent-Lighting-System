import { describe, expect, it } from 'vitest';
import { createStatsAccumulator, formatStats, recordFrame } from '../components/rig/previs/PrevizStats';

describe('recordFrame', () => {
  it('only starts the clock on the first frame', () => {
    const acc = createStatsAccumulator();
    expect(recordFrame(acc, 1000, 50, 1000, 3, 4)).toBeNull();
    expect(acc.frames).toBe(0);
  });

  it('averages a 500 ms window of 60 fps frames', () => {
    const acc = createStatsAccumulator();
    recordFrame(acc, 0, 0, 0, 0, 0);
    let sample = null;
    for (let i = 1; i <= 30 && !sample; i += 1) {
      sample = recordFrame(acc, i * (1000 / 60), 40 + (i % 2) * 2, 200000, 12, 5);
    }
    expect(sample).not.toBeNull();
    expect(sample!.fps).toBeCloseTo(60, 5);
    expect(sample!.frameMs).toBeCloseTo(1000 / 60, 5);
    expect(sample!.calls).toBe(41);
    expect(sample!.triangles).toBe(200000);
    expect(sample!.geometries).toBe(12);
    expect(sample!.textures).toBe(5);
    // A new window starts.
    expect(acc.frames).toBe(0);
    expect(recordFrame(acc, 501, 1, 1, 1, 1)).toBeNull();
  });
});

describe('formatStats', () => {
  it('writes one readable line', () => {
    const line = formatStats({ fps: 59.6, frameMs: 16.78, calls: 42, triangles: 1_020_000, geometries: 30, textures: 4 });
    expect(line).toContain('60 fps');
    expect(line).toContain('16.8 ms');
    expect(line).toContain('42 calls');
    expect(line).toContain('1.02M tris');
  });
});
