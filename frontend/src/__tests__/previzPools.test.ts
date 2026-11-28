import { describe, expect, it } from 'vitest';
import {
  POOL_DECAL_GAIN,
  POOL_DECAL_LIFT,
  POOL_LIGHT_AT_FULL,
  poolConeDeg,
  poolDecal,
  poolDecalHalfFrac,
  poolDecalStrength,
  poolLightIntensity,
  poolRadius,
} from '../components/rig/previs/poolLight';
import { createPoolBuffer, packPoolDecal, writePoolSlot } from '../components/rig/previs/FloorPools';
import { REAL_POOL_LIGHTS, assignPoolLights } from '../components/rig/previs/poolPick';

const deg = (d: number) => (d * Math.PI) / 180;

describe('decal pools agree with the spot light they replace', () => {
  it('puts the half-way ring where poolRadius does, across the zoom range', () => {
    for (const spot of [false, true]) {
      for (const zoom of [0, 0.5, 1]) {
        const cone = deg(poolConeDeg(spot, zoom));
        const throwDistance = 6;
        const { outer, innerFrac } = poolDecal(throwDistance, cone);
        const half = outer * poolDecalHalfFrac(innerFrac);
        expect(half / poolRadius(throwDistance, cone)).toBeCloseTo(1, 1);
        expect(Math.abs(half / poolRadius(throwDistance, cone) - 1)).toBeLessThan(0.03);
      }
    }
  });

  it('grows with the throw and is nothing at no throw', () => {
    const cone = deg(8);
    expect(poolDecal(8, cone).outer).toBeCloseTo(poolDecal(4, cone).outer * 2, 6);
    expect(poolDecal(0, cone).outer).toBe(0);
    expect(poolDecal(-1, cone).outer).toBe(0);
  });

  it('is as bright as the spot light, in step with the level', () => {
    expect(poolDecalStrength(0)).toBe(0);
    expect(poolDecalStrength(1)).toBeCloseTo(POOL_DECAL_GAIN, 6);
    expect(poolDecalStrength(0.25)).toBeCloseTo((poolLightIntensity(0.25) / POOL_LIGHT_AT_FULL) * POOL_DECAL_GAIN, 6);
    expect(poolDecalStrength(2)).toBeCloseTo(POOL_DECAL_GAIN, 6);
  });
});

describe('packPoolDecal', () => {
  const down = { x: 0, y: -1, z: 0 };
  const floor = { x: 0, y: 1, z: 0 };

  it('lays a beam pointing straight down on the floor under it', () => {
    const buffer = createPoolBuffer(1);
    writePoolSlot(buffer, 0, 1, 1, 0.5, 0.25, 2, 5, -1, down, 5, 0.2, deg(10), floor);
    const m = new Float32Array(16);
    const p = new Float32Array(4);
    expect(packPoolDecal(buffer, 0, m, 0, p, 0)).toBe(true);
    // Centre on the floor below the fixture, lifted off it toward the light.
    expect(m[12]).toBeCloseTo(2, 6);
    expect(m[13]).toBeCloseTo(POOL_DECAL_LIFT, 6);
    expect(m[14]).toBeCloseTo(-1, 6);
    // Square on: as wide one way as the other, and as wide as poolDecal says.
    const { outer, innerFrac } = poolDecal(5 - 0.2, deg(10));
    const a = Math.hypot(m[0], m[1], m[2]);
    const b = Math.hypot(m[4], m[5], m[6]);
    expect(a).toBeCloseTo(outer, 5);
    expect(b).toBeCloseTo(outer, 5);
    // Its own Z is the floor's normal, facing the light.
    expect(m[9]).toBeCloseTo(1, 6);
    // Colour times strength, and the inner fade.
    expect(p[0]).toBeCloseTo(1 * POOL_DECAL_GAIN, 5);
    expect(p[1]).toBeCloseTo(0.5 * POOL_DECAL_GAIN, 5);
    expect(p[2]).toBeCloseTo(0.25 * POOL_DECAL_GAIN, 5);
    expect(p[3]).toBeCloseTo(innerFrac, 6);
  });

  it('stretches a leaning beam along its heading and dims it by the angle', () => {
    const buffer = createPoolBuffer(1);
    const lean = deg(45);
    const dir = { x: Math.sin(lean), y: -Math.cos(lean), z: 0 };
    writePoolSlot(buffer, 0, 1, 1, 1, 1, 0, 4, 0, dir, 4 / Math.cos(lean), 0.2, deg(8), floor);
    const m = new Float32Array(16);
    const p = new Float32Array(4);
    expect(packPoolDecal(buffer, 0, m, 0, p, 0)).toBe(true);
    const major = Math.hypot(m[0], m[1], m[2]);
    const minor = Math.hypot(m[4], m[5], m[6]);
    expect(major / minor).toBeCloseTo(1 / Math.cos(lean), 4);
    // Its long axis runs along +X, the way the beam heads.
    expect(Math.abs(m[0])).toBeCloseTo(major, 4);
    // Lands where the beam does: 4 m out along X.
    expect(m[12]).toBeCloseTo(4, 4);
    expect(p[0]).toBeCloseTo(POOL_DECAL_GAIN * Math.cos(lean), 4);
  });

  it('draws nothing for a dark fixture or a beam that lands on nothing', () => {
    const buffer = createPoolBuffer(2);
    writePoolSlot(buffer, 0, 0, 1, 1, 1, 0, 4, 0, down, 4, 0.2, deg(8), floor);
    writePoolSlot(buffer, 1, 1, 1, 1, 1, 0, 4, 0, down, 4, 0.2, deg(8), { x: 0, y: 0, z: 0 });
    const m = new Float32Array(32);
    const p = new Float32Array(8);
    expect(packPoolDecal(buffer, 0, m, 0, p, 0)).toBe(false);
    expect(packPoolDecal(buffer, 1, m, 16, p, 4)).toBe(false);
  });

  it('ignores a slot past the end of the buffer', () => {
    const buffer = createPoolBuffer(1);
    writePoolSlot(buffer, 3, 1, 1, 1, 1, 0, 4, 0, down, 4, 0.2, deg(8), floor);
    expect(buffer.active[0]).toBe(0);
  });
});

describe('assignPoolLights', () => {
  const all = () => true;

  it('gives the lights to the brightest fixtures', () => {
    const levels = new Float32Array([0.1, 0.9, 0.5, 0.0, 0.7, 0.3]);
    const assignment = new Int32Array(3).fill(-1);
    const taken = new Uint8Array(levels.length);
    assignPoolLights(levels, levels.length, all, assignment, taken);
    expect(Array.from(assignment).sort()).toEqual([1, 2, 4]);
    expect(Array.from(taken)).toEqual([0, 1, 1, 0, 1, 0]);
  });

  it('gives no light to a dark or ineligible fixture', () => {
    const levels = new Float32Array([0.0, 0.8, 0.6]);
    const assignment = new Int32Array(REAL_POOL_LIGHTS).fill(-1);
    const taken = new Uint8Array(3);
    assignPoolLights(levels, 3, (i) => i !== 1, assignment, taken);
    expect(Array.from(assignment).filter((i) => i >= 0)).toEqual([2]);
  });

  it('keeps a light with its fixture against one about as bright', () => {
    const levels = new Float32Array([0.5, 0.6]);
    const assignment = new Int32Array([0]);
    const taken = new Uint8Array(2);
    assignPoolLights(levels, 2, all, assignment, taken);
    expect(assignment[0]).toBe(0);
  });

  it('hands it over to one much brighter', () => {
    const levels = new Float32Array([0.2, 0.9]);
    const assignment = new Int32Array([0]);
    const taken = new Uint8Array(2);
    assignPoolLights(levels, 2, all, assignment, taken);
    expect(assignment[0]).toBe(1);
    expect(Array.from(taken)).toEqual([0, 1]);
  });

  it('frees a light whose fixture went dark', () => {
    const levels = new Float32Array([0.0, 0.0]);
    const assignment = new Int32Array([1, 0]);
    const taken = new Uint8Array(2);
    assignPoolLights(levels, 2, all, assignment, taken);
    expect(Array.from(assignment)).toEqual([-1, -1]);
  });
});
