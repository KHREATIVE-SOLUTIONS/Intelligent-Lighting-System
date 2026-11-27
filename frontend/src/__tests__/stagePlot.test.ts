// The stage plot underlay's maths (utils/stagePlot.ts). The rotated example is
// the one the server is tested with (backend/tests/unit/test_stage_plot.py), so
// the plan's live preview and the stored transform cannot drift. docs/STAGE_PLOT.md.
import { describe, expect, it } from 'vitest';
import {
  calibrationProblem, calibrationTransform, fitTransform, isGuessed, normaliseRotation, svgMatrix, toImage, toPlan,
} from '../utils/stagePlot';
import type { Matrix, StagePlotCalibration } from '../utils/stagePlot';

const ROTATED: StagePlotCalibration = {
  point_a: { x: 100, y: 100 }, point_b: { x: 300, y: 100 }, distance_m: 4,
  origin: { x: 200, y: 300 }, rotation_deg: 90, opacity: 0.4,
};
const ROTATED_MATRIX: Matrix = [0, 0.02, -0.02, 0, 6, -4];

const closeTo = (actual: number[], expected: number[]) => {
  expect(actual).toHaveLength(expected.length);
  actual.forEach((n, i) => expect(n).toBeCloseTo(expected[i], 9));
};

describe('stage plot calibration maths', () => {
  it('gives the rotated example the same transform as the server', () => {
    const t = calibrationTransform(ROTATED);
    expect(t.scale_m_per_px).toBeCloseTo(0.02, 12);
    expect(t.rotation_deg).toBe(90);
    closeTo(t.matrix, ROTATED_MATRIX);
    expect(t.offset_x).toBeCloseTo(6, 9);
    expect(t.offset_z).toBeCloseTo(-4, 9);
    // The origin is the middle of the stage; point B, right of it on the image, is downstage of it.
    const origin = toPlan(t.matrix, 200, 300);
    closeTo([origin.x, origin.z], [0, 0]);
    const b = toPlan(t.matrix, 300, 100);
    closeTo([b.x, b.z], [4, 2]);
  });

  it('keeps the measured distance and the origin at any turn', () => {
    for (const rotation of [0, 30, -45, 135, 271]) {
      const m = calibrationTransform({
        point_a: { x: 12.5, y: 40 }, point_b: { x: 212.5, y: 190 }, distance_m: 7.5,
        origin: { x: 60, y: 70 }, rotation_deg: rotation, opacity: 0.5,
      }).matrix;
      const a = toPlan(m, 12.5, 40);
      const b = toPlan(m, 212.5, 190);
      expect(Math.hypot(b.x - a.x, b.z - a.z)).toBeCloseTo(7.5, 9);
      const o = toPlan(m, 60, 70);
      closeTo([o.x, o.z], [0, 0]);
    }
  });

  it('turns a point on the plan back into the pixel it came from', () => {
    const m = calibrationTransform({ ...ROTATED, rotation_deg: 37 }).matrix;
    const there = toPlan(m, 321, 123);
    const back = toImage(m, there.x, there.z);
    closeTo([back.x, back.y], [321, 123]);
    const pixel = toImage(ROTATED_MATRIX, 4, 2);
    closeTo([pixel.x, pixel.y], [300, 100]);
  });

  it('fits an image not calibrated yet to the stage, its middle on the middle', () => {
    // 1000 x 500 px onto 10 x 8 m: as wide as the stage, 0.01 m a pixel.
    const m = fitTransform(1000, 500, 10, 8);
    closeTo(m, [0.01, 0, 0, 0.01, -5, -2.5]);
    const middle = toPlan(m, 500, 250);
    closeTo([middle.x, middle.z], [0, 0]);
    // A tall image is held to the depth instead.
    closeTo(fitTransform(100, 400, 10, 8), [0.02, 0, 0, 0.02, -1, -4]);
  });

  it('gives a rotation back within a half turn either way', () => {
    expect(normaliseRotation(270)).toBe(-90);
    expect(normaliseRotation(-180)).toBe(180);
    expect(normaliseRotation(540)).toBe(180);
    expect(calibrationTransform({ ...ROTATED, rotation_deg: 450 }).rotation_deg).toBe(90);
  });

  it('says in a sentence why a calibration cannot be used', () => {
    expect(calibrationProblem(ROTATED)).toBeNull();
    expect(calibrationProblem({ ...ROTATED, point_b: { x: 100, y: 101 } })).toMatch(/on top of each other/);
    expect(calibrationProblem({ ...ROTATED, distance_m: 0 })).toMatch(/distance/);
    expect(calibrationProblem({ ...ROTATED, distance_m: 5000 })).toMatch(/distance/);
    expect(calibrationProblem({ ...ROTATED, opacity: 2 })).toMatch(/opacity/);
    expect(calibrationProblem({ ...ROTATED, distance_m: Number.NaN })).toMatch(/finite/);
  });

  it('writes a matrix as an SVG transform without float noise', () => {
    expect(svgMatrix([1, 0, 0, 1, 2, 3])).toBe('matrix(1 0 0 1 2 3)');
    expect(svgMatrix(calibrationTransform(ROTATED).matrix)).toBe('matrix(0 0.02 -0.02 0 6 -4)');
  });

  it('knows a guessed position by its tag', () => {
    expect(isGuessed(['position_unconfirmed', 'position_source:template'])).toBe(true);
    expect(isGuessed(['position_source:tap'])).toBe(false);
    expect(isGuessed(undefined)).toBe(false);
  });
});
