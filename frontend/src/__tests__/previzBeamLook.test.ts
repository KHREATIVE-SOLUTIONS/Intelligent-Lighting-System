import { describe, expect, it } from 'vitest';
import {
  BEAM_EDGE_FLOOR,
  BEAM_FALLOFF_FLOOR,
  BEAM_FALLOFF_HALF_M,
  BEAM_LENS_GLOW,
  BEAM_LOOK_GLSL,
  DEFAULT_HAZE,
  FLAT_BEAM_ALPHA,
  beamEdge,
  beamFalloff,
  flatBeamAlpha,
  lensGlow,
  softBeamAlpha,
} from '../components/rig/previs/beamLook';
import { createInstancedBeamMaterial } from '../components/rig/previs/beamShape';
import { createLookUniforms } from '../components/rig/previs/lookUniforms';

describe('beam falloff along its length', () => {
  it('is full at the mouth, half way to its floor at the half distance, and falls steadily', () => {
    expect(beamFalloff(0)).toBeCloseTo(1, 9);
    expect(beamFalloff(BEAM_FALLOFF_HALF_M)).toBeCloseTo((1 + BEAM_FALLOFF_FLOOR) / 2, 9);
    let last = Infinity;
    for (let d = 0; d <= 30; d += 0.5) {
      const now = beamFalloff(d);
      expect(now).toBeLessThan(last);
      last = now;
    }
  });

  it('never goes below its soft floor, and treats a point behind the mouth as at it', () => {
    expect(beamFalloff(1000)).toBeGreaterThan(BEAM_FALLOFF_FLOOR);
    expect(beamFalloff(1000)).toBeCloseTo(BEAM_FALLOFF_FLOOR, 3);
    expect(beamFalloff(-2)).toBe(beamFalloff(0));
  });

  it('falls roughly as an inverse square well past the half distance', () => {
    const far = (d: number) => beamFalloff(d) - BEAM_FALLOFF_FLOOR;
    expect(far(20) / far(40)).toBeCloseTo(4, 0);
  });
});

describe('beam alpha in haze', () => {
  it('in clean air shows only the lens glow, gone a metre out', () => {
    expect(softBeamAlpha(1, 0, 0, 1)).toBeCloseTo(BEAM_LENS_GLOW, 9);
    expect(softBeamAlpha(1, 1.5, 0, 1)).toBeLessThan(0.01);
    expect(lensGlow(1.5)).toBeLessThan(0.01);
    expect(flatBeamAlpha(1, 0)).toBe(0);
  });

  it('rises with the haze and with the level', () => {
    expect(softBeamAlpha(1, 3, 0.8, 1)).toBeGreaterThan(softBeamAlpha(1, 3, 0.3, 1));
    expect(softBeamAlpha(0.5, 3, 0.5, 1)).toBeCloseTo(softBeamAlpha(1, 3, 0.5, 1) / 2, 9);
    expect(softBeamAlpha(0, 0, 1, 1)).toBe(0);
  });

  it('fades to a soft edge across the cone and never vanishes end on', () => {
    expect(beamEdge(1)).toBeCloseTo(1, 9);
    expect(beamEdge(-1)).toBeCloseTo(1, 9);
    expect(beamEdge(0)).toBeCloseTo(BEAM_EDGE_FLOOR, 9);
    expect(beamEdge(0.2)).toBeGreaterThan(beamEdge(0.1));
    expect(softBeamAlpha(1, 2, 0.5, 0)).toBeGreaterThan(0);
  });

  it('draws the flat beam as it always was at the default haze', () => {
    expect(flatBeamAlpha(1, DEFAULT_HAZE)).toBeCloseTo(FLAT_BEAM_ALPHA, 9);
    expect(flatBeamAlpha(0.5, DEFAULT_HAZE)).toBeCloseTo(FLAT_BEAM_ALPHA / 2, 9);
  });
});

describe('the beam shader', () => {
  it('carries the same functions and shares the look uniforms', () => {
    for (const name of ['beamFalloff', 'lensGlow', 'beamEdge', 'softBeamAlpha', 'flatBeamAlpha']) {
      expect(BEAM_LOOK_GLSL).toContain(`float ${name}(`);
    }
    expect(BEAM_LOOK_GLSL).toContain(BEAM_FALLOFF_HALF_M.toFixed(4));
    const look = createLookUniforms();
    const material = createInstancedBeamMaterial(look);
    expect(material.uniforms.uHaze).toBe(look.haze);
    expect(material.uniforms.uSoftBeams).toBe(look.softBeams);
    expect(material.fragmentShader).toContain('softBeamAlpha(level, vAlong, uHaze, facing)');
    expect(material.fragmentShader).toContain('#include <tonemapping_fragment>');
    expect(material.vertexShader).toContain('vAlong = length(edge) * share');
    expect(material.depthWrite).toBe(false);
    material.dispose();
  });
});
