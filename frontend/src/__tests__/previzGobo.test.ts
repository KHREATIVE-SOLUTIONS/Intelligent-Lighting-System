import { describe, expect, it } from 'vitest';
import {
  ENGINE_GOBO_SLOTS,
  GOBO_ATLAS_CELLS,
  GOBO_CELL_PX,
  GOBO_OPEN,
  GOBO_PATTERNS,
  buildGoboAtlasPixels,
  goboAtlasUv,
  goboFromName,
  goboFromValue,
  goboIndex,
  goboIndexOf,
  goboPatternAt,
  goboRotation,
} from '../components/rig/previs/gobo';
import type { GoboTurn } from '../components/rig/previs/gobo';
import { buildBeamProfile, readBeamState } from '../components/rig/previs/beamState';
import { createPoolBuffer, packPoolDecal, writePoolSlot } from '../components/rig/previs/FloorPools';

const turn = (): GoboTurn => ({ goboIndexed: true, goboAngle: 0, goboSpin: 0 });

describe('gobo atlas', () => {
  it('puts each pattern in its own cell, held inside it', () => {
    const [u0, v0] = goboAtlasUv(0, 0, 0);
    expect(u0).toBeGreaterThan(0);
    expect(v0).toBeGreaterThan(0);
    const [u1] = goboAtlasUv(1, 0.5, 0.5);
    expect(u1).toBeCloseTo(1.5 / GOBO_ATLAS_CELLS, 9);
    const [uEnd] = goboAtlasUv(2, 1, 1);
    expect(uEnd).toBeLessThan(3 / GOBO_ATLAS_CELLS);
    expect(uEnd).toBeGreaterThan(2 / GOBO_ATLAS_CELLS);
    // Out of range indices and coordinates are held to the atlas.
    expect(goboAtlasUv(99, 2, -1)[0]).toBeLessThan(1);
    expect(goboAtlasUv(-3, 0.5, 0.5)[0]).toBeCloseTo(0.5 / GOBO_ATLAS_CELLS, 9);
  });

  it('draws every pattern with light through it and a dark border', () => {
    const width = GOBO_ATLAS_CELLS * GOBO_CELL_PX;
    const pixels = buildGoboAtlasPixels();
    expect(pixels.length).toBe(width * GOBO_CELL_PX * 4);
    for (let cell = 0; cell < GOBO_PATTERNS.length; cell += 1) {
      let through = 0;
      let blocked = 0;
      for (let y = 0; y < GOBO_CELL_PX; y += 1) {
        for (let x = 0; x < GOBO_CELL_PX; x += 1) {
          const v = pixels[(y * width + cell * GOBO_CELL_PX + x) * 4];
          if (v > 200) through += 1;
          if (v < 50) blocked += 1;
        }
        // Left and right edges of the cell are dark, so mipmaps do not bleed.
        expect(pixels[(y * width + cell * GOBO_CELL_PX) * 4]).toBe(0);
        expect(pixels[(y * width + cell * GOBO_CELL_PX + GOBO_CELL_PX - 1) * 4]).toBe(0);
      }
      expect(through).toBeGreaterThan(50);
      expect(blocked).toBeGreaterThan(50);
    }
  });

  it('lets the open pattern through everywhere inside the disc', () => {
    expect(goboPatternAt(GOBO_OPEN, 0.3, -0.4)).toBe(1);
    expect(goboPatternAt(goboIndexOf('ring'), 0, 0.67)).toBe(1);
    expect(goboPatternAt(goboIndexOf('ring'), 0, 0.35)).toBe(0);
    expect(goboPatternAt(goboIndexOf('dots'), 0, 0)).toBe(1);
  });
});

describe('gobo index from the wheel', () => {
  it('reads the engine slot positions where the profile names nothing', () => {
    expect(goboFromValue(0)).toBe(GOBO_OPEN);
    expect(goboFromValue(10)).toBe(GOBO_OPEN);
    for (const [at, pattern] of ENGINE_GOBO_SLOTS) {
      expect(goboFromValue(Math.round(at * 255))).toBe(goboIndexOf(pattern));
    }
    expect(goboFromValue(Number.NaN)).toBe(GOBO_OPEN);
  });

  it('reads named slots by what they are called, then by their place', () => {
    expect(goboFromName('Open', 0)).toBe(GOBO_OPEN);
    expect(goboFromName('', 3)).toBe(GOBO_OPEN);
    expect(goboFromName('Star burst', 0)).toBe(goboIndexOf('star'));
    expect(goboFromName('Dots', 4)).toBe(goboIndexOf('dots'));
    expect(goboFromName('Leaves breakup', 0)).toBe(goboIndexOf('breakup'));
    expect(goboFromName('Gobo 1', 0)).toBe(1);
    expect(goboFromName('Gobo 2', 1)).toBe(2);
    expect(goboFromName('Gobo 6', 5)).toBe(1);
  });

  it('goes by the named range a value falls in', () => {
    const ranges = [
      { name: 'Open', min_value: 0, max_value: 7 },
      { name: 'Gobo 1', min_value: 8, max_value: 15 },
      { name: 'Gobo 2', min_value: 16, max_value: 23 },
      { name: 'Ring', min_value: 24, max_value: 31 },
    ];
    expect(goboIndex(ranges, 3)).toBe(GOBO_OPEN);
    expect(goboIndex(ranges, 10)).toBe(1);
    expect(goboIndex(ranges, 20)).toBe(2);
    expect(goboIndex(ranges, 30)).toBe(goboIndexOf('ring'));
    // Past the named ranges: the engine's slots.
    expect(goboIndex(ranges, 133)).toBe(goboIndexOf('lines'));
    expect(goboIndex(undefined, 31)).toBe(goboIndexOf('dots'));
  });
});

describe('gobo rotation', () => {
  it('is the wheel angle where the profile names nothing, as the engine writes it', () => {
    const out = goboRotation(undefined, 64, turn());
    expect(out.goboIndexed).toBe(true);
    expect(out.goboAngle).toBeCloseTo((64 / 255) * Math.PI * 2, 9);
    expect(out.goboSpin).toBe(0);
  });

  it('turns either way, stops or holds an index by the range names', () => {
    const ranges = [
      { name: 'Index', min_value: 0, max_value: 127 },
      { name: 'Rotation CW slow to fast', min_value: 128, max_value: 191 },
      { name: 'Stop', min_value: 192, max_value: 195 },
      { name: 'Rotation CCW slow to fast', min_value: 196, max_value: 255 },
    ];
    const index = goboRotation(ranges, 127, turn());
    expect(index.goboIndexed).toBe(true);
    expect(index.goboAngle).toBeCloseTo(Math.PI * 2, 9);
    const cw = goboRotation(ranges, 191, turn());
    expect(cw.goboIndexed).toBe(false);
    expect(cw.goboSpin).toBeGreaterThan(goboRotation(ranges, 130, turn()).goboSpin);
    expect(goboRotation(ranges, 200, turn()).goboSpin).toBeLessThan(0);
    const stop = goboRotation(ranges, 193, turn());
    expect(stop.goboIndexed).toBe(false);
    expect(stop.goboSpin).toBe(0);
  });
});

describe('a gobo from the frame to the pool', () => {
  const fixture = {
    fixture: {
      fixture_type: 'spot',
      modes: [{
        id: 1,
        channels: [
          { channel_number: 1, channel_type: 'gobo', name: 'Gobo' },
          { channel_number: 2, channel_type: 'gobo_rotation', name: 'Gobo Rotation' },
          { channel_number: 3, channel_type: 'dimmer', name: 'Dimmer' },
        ],
      }],
    },
  };

  it('is read out of the frame, and open with no frame or no channel', () => {
    const profile = buildBeamProfile(fixture);
    const state = readBeamState(profile, [31, 64, 255], 1);
    expect(state.gobo).toBe(goboIndexOf('dots'));
    expect(state.goboValue).toBe(31);
    expect(state.goboIndexed).toBe(true);
    expect(state.goboAngle).toBeCloseTo((64 / 255) * Math.PI * 2, 9);
    expect(readBeamState(profile, null, 1).gobo).toBe(GOBO_OPEN);
    const plain = buildBeamProfile({ fixture: { modes: [{ channels: [{ channel_number: 1, channel_type: 'dimmer' }] }] } });
    expect(readBeamState(plain, [255], 1).gobo).toBe(GOBO_OPEN);
  });

  it('rides with its pool into the decal', () => {
    const buffer = createPoolBuffer(1);
    writePoolSlot(
      buffer, 0, 1, 1, 1, 1, 0, 5, 0, { x: 0, y: -1, z: 0 }, 5, 0.2, 0.2, { x: 0, y: 1, z: 0 }, 3, 1.25,
    );
    const m = new Float32Array(16);
    const p = new Float32Array(4);
    const g = new Float32Array(2);
    expect(packPoolDecal(buffer, 0, m, 0, p, 0, g, 0)).toBe(true);
    expect(g[0]).toBe(3);
    expect(g[1]).toBeCloseTo(1.25, 6);
    // A slot written without one is open.
    writePoolSlot(buffer, 0, 1, 1, 1, 1, 0, 5, 0, { x: 0, y: -1, z: 0 }, 5, 0.2, 0.2, { x: 0, y: 1, z: 0 });
    packPoolDecal(buffer, 0, m, 0, p, 0, g, 0);
    expect(g[0]).toBe(GOBO_OPEN);
  });
});
