/**
 * The parts of a fixture model that hold it up, as a list of (geometry,
 * matrix) pairs for the instanced fixture rig (FixtureRig.tsx).
 *
 * These used to be React components, one mesh tree per fixture. They are now
 * plain data: every part with the same geometry, across the whole rig, is one
 * instanced draw. The matrices are in the fixture's support frame (its
 * position and yaw), exactly where the old JSX put each mesh.
 */
import * as THREE from 'three';
import { box, cylY, merge, paint, place } from './geometryKit';
import { getFixtureGeometry } from './fixtureGeometry';
import { FIXTURE_SPECS } from './fixtureSpecs';
import type { FixtureModelKind } from './fixtureSpecs';
import type { FixtureMount } from './layout';

// Unit-sized parts, stretched per fixture: a pipe and a block 1 m tall, and a
// wall arm 1 m long with its plate at the far end.
export const unitPipe = paint(place(cylY(0.022, 0.022, 1, 10), [0, 0.5, 0]), '#8f949c');
export const unitBlock = paint(place(box(1, 1, 1), [0, 0.5, 0]), '#1d1e22');
export const unitArm = paint(place(box(1, 0.03, 0.03), [0.5, 0, 0]), '#8f949c');
export const wallPlate = merge([
  paint(place(box(0.035, 0.16, 0.1), [-0.0175, -0.03, 0]), '#8f949c'),
]);
export const poleFoot = merge([
  paint(place(cylY(0.16, 0.2, 0.03, 20), [0, 0.015, 0]), '#1d1e22'),
]);

/** Above this a floor fixture is on a pole rather than a block. */
const POLE_ABOVE = 0.5;

/** One part of a fixture's support: its geometry and where it sits in the support frame. */
export type SupportPart = { geometry: THREE.BufferGeometry; local: THREE.Matrix4 };

const unitScale = new THREE.Vector3(1, 1, 1);
const noTurn = new THREE.Quaternion();

function at(x: number, y: number, z: number, sx = 1, sy = 1, sz = 1): THREE.Matrix4 {
  return new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), noTurn, new THREE.Vector3(sx, sy, sz));
}

/**
 * Whatever holds the fixture up: its base or bracket, plus the pipe, wall arm
 * or plinth that reaches the truss, wall or floor.
 *
 * `bodyYaw` is the fixture's own rotation about the vertical. A wall arm has
 * to reach the wall whichever way the fixture is turned, so it is turned back.
 */
export function supportParts(kind: FixtureModelKind, mount: FixtureMount, bodyYaw: number): SupportPart[] {
  const geometry = getFixtureGeometry(kind);
  const spec = FIXTURE_SPECS[kind];
  const standing = mount.type === 'stand';
  const parts: SupportPart[] = [
    { geometry: standing ? geometry.supportStand : geometry.supportHang, local: new THREE.Matrix4() },
  ];

  // Pipe above the clamp: up to the truss chord, or up to the ceiling.
  const drop = mount.type === 'truss' || mount.type === 'ceiling' ? mount.drop : 0;
  if (drop > 0.01) {
    for (const x of geometry.clampXs) parts.push({ geometry: unitPipe, local: at(x, spec.hangHeight, 0, 1, drop, 1) });
  }

  if (mount.type === 'wall') {
    const turn = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.atan2(-mount.dirZ, mount.dirX) - bodyYaw);
    for (const x of geometry.clampXs) {
      const arm = new THREE.Matrix4().compose(new THREE.Vector3(x, spec.hangHeight, 0), turn, unitScale);
      parts.push({ geometry: unitArm, local: arm.clone().multiply(at(0, 0, 0, mount.reach, 1, 1)) });
      parts.push({ geometry: wallPlate, local: arm.clone().multiply(at(mount.reach, 0, 0)) });
    }
  }

  if (mount.type === 'stand' && mount.plinth > 0.02) {
    const y = -spec.standHeight - mount.plinth;
    if (mount.plinth > POLE_ABOVE) {
      parts.push({ geometry: unitPipe, local: at(0, y, 0, 1, mount.plinth, 1) });
      parts.push({ geometry: poleFoot, local: at(0, y, 0) });
    } else {
      parts.push({ geometry: unitBlock, local: at(0, y, 0, 0.42, mount.plinth, 0.42) });
    }
  }
  return parts;
}

/** The yoke arms of a moving head, hanging or standing; null for a fixed body. */
export function yokeGeometry(kind: FixtureModelKind, standing: boolean): THREE.BufferGeometry | null {
  const geometry = getFixtureGeometry(kind);
  return standing ? geometry.yokeStand : geometry.yokeHang;
}
