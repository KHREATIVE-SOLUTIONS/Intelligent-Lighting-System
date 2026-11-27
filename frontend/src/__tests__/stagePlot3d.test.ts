// The stage plot in the 3D view: the flat plane worked out from the 2D plan's
// image-to-plan matrix lies where the plan draws the image. docs/STAGE_PLOT.md.
import { afterEach, describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { calibrationTransform, toPlan } from '../utils/stagePlot';
import type { Matrix } from '../utils/stagePlot';
import {
  STAGE_PLOT_LIFT, readStagePlot3dChoice, stagePlot3dKey, stagePlotPlane, writeStagePlot3dChoice,
} from '../utils/stagePlot3d';

/** The plane as the 3D view builds it: a group turned by yaw, a flat PlaneGeometry inside. */
function built(m: Matrix, widthPx: number, heightPx: number) {
  const plane = stagePlotPlane(m, widthPx, heightPx)!;
  const group = new THREE.Group();
  group.position.set(plane.centerX, STAGE_PLOT_LIFT, plane.centerZ);
  group.rotation.y = plane.yaw;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(plane.width, plane.depth));
  mesh.rotation.x = -Math.PI / 2;
  group.add(mesh);
  group.updateMatrixWorld(true);
  return mesh;
}

/**
 * Where three draws image pixel (u, v): the plane's vertex at the matching
 * texture coordinate. With TextureLoader's default flipY, uv (0, 1) is the
 * image's top-left pixel.
 */
function cornerIn3d(mesh: THREE.Mesh, u01: number, v01: number) {
  const uv = mesh.geometry.getAttribute('uv');
  const position = mesh.geometry.getAttribute('position');
  for (let i = 0; i < uv.count; i += 1) {
    if (Math.abs(uv.getX(i) - u01) < 1e-9 && Math.abs(uv.getY(i) - (1 - v01)) < 1e-9) {
      return new THREE.Vector3().fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld);
    }
  }
  throw new Error(`no vertex at uv ${u01}, ${1 - v01}`);
}

const CORNERS: Array<[number, number]> = [[0, 0], [1, 0], [0, 1], [1, 1]];

function expectAgreesWithPlan(m: Matrix, widthPx: number, heightPx: number) {
  const mesh = built(m, widthPx, heightPx);
  for (const [u01, v01] of CORNERS) {
    const on2d = toPlan(m, u01 * widthPx, v01 * heightPx);
    const on3d = cornerIn3d(mesh, u01, v01);
    // Three keeps vertex positions in float32: agreement to 10 micrometres.
    expect(on3d.x).toBeCloseTo(on2d.x, 5);
    expect(on3d.z).toBeCloseTo(on2d.z, 5);
    expect(on3d.y).toBeCloseTo(STAGE_PLOT_LIFT, 5);
  }
}

describe('stagePlotPlane', () => {
  it('lays an identity matrix with its top-left pixel on the middle of the stage', () => {
    const plane = stagePlotPlane([1, 0, 0, 1, 0, 0], 4, 2)!;
    expect(plane.centerX).toBeCloseTo(2, 9);
    expect(plane.centerZ).toBeCloseTo(1, 9);
    expect(plane.width).toBeCloseTo(4, 9);
    expect(plane.depth).toBeCloseTo(2, 9);
    expect(plane.yaw).toBeCloseTo(0, 9);
    expectAgreesWithPlan([1, 0, 0, 1, 0, 0], 4, 2);
  });

  it('scales the image to metres', () => {
    // 0.025 m a pixel, fitted: a 400 x 200 px image over a 10 m stage.
    const m: Matrix = [0.025, 0, 0, 0.025, -5, -2.5];
    const plane = stagePlotPlane(m, 400, 200)!;
    expect(plane.width).toBeCloseTo(10, 9);
    expect(plane.depth).toBeCloseTo(5, 9);
    expect(plane.centerX).toBeCloseTo(0, 9);
    expect(plane.centerZ).toBeCloseTo(0, 9);
    expectAgreesWithPlan(m, 400, 200);
  });

  it('turns the image 90 degrees clockwise on the plan, as the docs example does', () => {
    // docs/STAGE_PLOT.md: A (100,100), B (300,100), 4 m, origin (200,300), 90 degrees.
    const t = calibrationTransform({
      point_a: { x: 100, y: 100 }, point_b: { x: 300, y: 100 }, distance_m: 4,
      origin: { x: 200, y: 300 }, rotation_deg: 90, opacity: 0.4,
    });
    const expected: Matrix = [0, 0.02, -0.02, 0, 6, -4];
    t.matrix.forEach((n, i) => expect(n).toBeCloseTo(expected[i], 9));
    const plane = stagePlotPlane(t.matrix, 600, 400)!;
    // The image's u axis points downstage (+z): a quarter turn the other way about y.
    expect(plane.yaw).toBeCloseTo(-Math.PI / 2, 9);
    expect(plane.width).toBeCloseTo(12, 9);
    expect(plane.depth).toBeCloseTo(8, 9);
    expectAgreesWithPlan(t.matrix, 600, 400);
  });

  it('puts the origin pixel on the middle of the stage', () => {
    const t = calibrationTransform({
      point_a: { x: 0, y: 0 }, point_b: { x: 100, y: 0 }, distance_m: 2,
      origin: { x: 50, y: 150 }, rotation_deg: 0, opacity: 0.5,
    });
    const plane = stagePlotPlane(t.matrix, 200, 300)!;
    // The image's middle (100, 150) is 50 px right of the origin: 1 m across, on the centre line.
    expect(plane.centerX).toBeCloseTo(1, 9);
    expect(plane.centerZ).toBeCloseTo(0, 9);
    expect(plane.yaw).toBeCloseTo(0, 9);
    expectAgreesWithPlan(t.matrix, 200, 300);
  });

  it('agrees with the plan at every corner for an awkward turn', () => {
    for (const rotation of [-135, -30, 45, 180]) {
      const t = calibrationTransform({
        point_a: { x: 10, y: 20 }, point_b: { x: 130, y: 70 }, distance_m: 3.3,
        origin: { x: 80, y: 40 }, rotation_deg: rotation, opacity: 0.5,
      });
      expectAgreesWithPlan(t.matrix, 320, 180);
    }
  });

  it('refuses what cannot be drawn', () => {
    expect(stagePlotPlane([Number.NaN, 0, 0, 1, 0, 0], 4, 2)).toBeNull();
    expect(stagePlotPlane([1, 0, 0, 1, 0, 0], 0, 2)).toBeNull();
    expect(stagePlotPlane([0, 0, 0, 0, 0, 0], 4, 2)).toBeNull();
    // A mirror: no calibration makes one, and a flat plane cannot show one.
    expect(stagePlotPlane([1, 0, 0, -1, 0, 0], 4, 2)).toBeNull();
  });
});

describe('the "Show stage plot in 3D" choice', () => {
  afterEach(() => window.localStorage.clear());

  it('is remembered per rig, and is no choice until one is made', () => {
    expect(readStagePlot3dChoice(7)).toBeNull();
    writeStagePlot3dChoice(7, false);
    expect(readStagePlot3dChoice(7)).toBe(false);
    expect(readStagePlot3dChoice(8)).toBeNull();
    writeStagePlot3dChoice(7, true);
    expect(window.localStorage.getItem(stagePlot3dKey(7))).toBe('on');
    expect(readStagePlot3dChoice(7)).toBe(true);
  });
});
