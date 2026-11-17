/**
 * Small helpers for building models out of three.js primitives.
 *
 * Every previs model is made here in code: there are no model files and
 * nothing is fetched, so the view works on a box with no internet.
 *
 * A model is a list of primitives, each painted one colour and moved into
 * place, then merged into a single geometry. One geometry with per-vertex
 * colours is one draw call and one shared material, however many parts the
 * model has. That matters because a rig is dozens of fixtures.
 */
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const scratchColor = new THREE.Color();
const scratchMatrix = new THREE.Matrix4();
const scratchQuat = new THREE.Quaternion();
const scratchEuler = new THREE.Euler();
const scratchPos = new THREE.Vector3();
const UNIT_SCALE = new THREE.Vector3(1, 1, 1);
const UP = new THREE.Vector3(0, 1, 0);

export type Vec3 = [number, number, number];

/** Paint every vertex of a geometry one colour. */
export function paint<T extends THREE.BufferGeometry>(geometry: T, color: THREE.ColorRepresentation): T {
  scratchColor.set(color);
  const count = geometry.getAttribute('position').count;
  const data = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    data[i * 3] = scratchColor.r;
    data[i * 3 + 1] = scratchColor.g;
    data[i * 3 + 2] = scratchColor.b;
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(data, 3));
  return geometry;
}

/** Move a geometry to a position, optionally turning it first (XYZ Euler, radians). */
export function place<T extends THREE.BufferGeometry>(geometry: T, position: Vec3, rotation?: Vec3): T {
  scratchEuler.set(rotation?.[0] ?? 0, rotation?.[1] ?? 0, rotation?.[2] ?? 0);
  scratchQuat.setFromEuler(scratchEuler);
  scratchPos.set(position[0], position[1], position[2]);
  geometry.applyMatrix4(scratchMatrix.compose(scratchPos, scratchQuat, UNIT_SCALE));
  return geometry;
}

/**
 * Merge painted parts into one geometry and free the parts.
 *
 * Everything is flattened to non-indexed triangles first: mergeGeometries
 * refuses a mix of indexed and non-indexed input, and the primitives are not
 * consistent about which they are.
 */
export function merge(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const prepared = parts.map((part) => {
    const flat = part.index ? part.toNonIndexed() : part;
    if (flat !== part) part.dispose();
    if (!flat.getAttribute('color')) paint(flat, '#ffffff');
    return flat;
  });
  const merged = mergeGeometries(prepared, false);
  prepared.forEach((part) => part.dispose());
  if (!merged) throw new Error('previs: could not merge model parts');
  merged.computeBoundingSphere();
  merged.computeBoundingBox();
  return merged;
}

// ---------------------------------------------------------------------------
// Primitives. Each returns a fresh geometry centred on the origin.
// ---------------------------------------------------------------------------

export function box(width: number, height: number, depth: number): THREE.BufferGeometry {
  return new THREE.BoxGeometry(width, height, depth);
}

/** Cylinder along Y. `radiusTop` is the +Y end. */
export function cylY(radiusTop: number, radiusBottom: number, height: number, segments = 20, open = false): THREE.BufferGeometry {
  return new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments, 1, open);
}

/** Cylinder along X. */
export function cylX(radius: number, length: number, segments = 16): THREE.BufferGeometry {
  return new THREE.CylinderGeometry(radius, radius, length, segments).rotateZ(Math.PI / 2);
}

/** Cylinder along Z. */
export function cylZ(radius: number, length: number, segments = 16): THREE.BufferGeometry {
  return new THREE.CylinderGeometry(radius, radius, length, segments).rotateX(Math.PI / 2);
}

/** Flat disc in the XZ plane, facing -Y (down the beam). */
export function discDown(radius: number, segments = 24): THREE.BufferGeometry {
  return new THREE.CircleGeometry(radius, segments).rotateX(Math.PI / 2);
}

/** Flat rectangle in the XZ plane, facing -Y. */
export function rectDown(width: number, depth: number): THREE.BufferGeometry {
  return new THREE.PlaneGeometry(width, depth).rotateX(Math.PI / 2);
}

/**
 * A shallow dome whose rim sits at y = 0 and which bulges toward -Y: the front
 * element of a lens, or one cell of an LED face.
 */
export function domeDown(radius: number, bulge: number, segments = 18): THREE.BufferGeometry {
  const depth = Math.max(1e-4, Math.min(bulge, radius));
  const sphereRadius = (radius * radius + depth * depth) / (2 * depth);
  const halfAngle = Math.asin(Math.min(1, radius / sphereRadius));
  const cap = new THREE.SphereGeometry(sphereRadius, segments, 4, 0, Math.PI * 2, Math.PI - halfAngle, halfAngle);
  cap.translate(0, sphereRadius - depth, 0);
  return cap;
}

/** Ring with a rectangular section, along Y: a lens bezel, a hood. */
export function tubeY(outerRadius: number, innerRadius: number, height: number, segments = 24): THREE.BufferGeometry {
  const half = height / 2;
  const profile = [
    new THREE.Vector2(innerRadius, -half),
    new THREE.Vector2(outerRadius, -half),
    new THREE.Vector2(outerRadius, half),
    new THREE.Vector2(innerRadius, half),
    new THREE.Vector2(innerRadius, -half),
  ];
  return new THREE.LatheGeometry(profile, segments);
}

/** Round bar from one point to another: truss lacing, a limb, a stand leg. */
export function strut(from: Vec3, to: Vec3, radius: number, segments = 6): THREE.BufferGeometry {
  const a = new THREE.Vector3(from[0], from[1], from[2]);
  const b = new THREE.Vector3(to[0], to[1], to[2]);
  const length = a.distanceTo(b);
  const geometry = new THREE.CylinderGeometry(radius, radius, length, segments);
  const direction = b.clone().sub(a).normalize();
  const quat = new THREE.Quaternion().setFromUnitVectors(UP, direction);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  geometry.applyMatrix4(new THREE.Matrix4().compose(mid, quat, UNIT_SCALE));
  return geometry;
}

/** Capsule between two points, for limbs and bodies. */
export function capsule(from: Vec3, to: Vec3, radius: number, radialSegments = 8): THREE.BufferGeometry {
  const a = new THREE.Vector3(from[0], from[1], from[2]);
  const b = new THREE.Vector3(to[0], to[1], to[2]);
  const length = a.distanceTo(b);
  const geometry = new THREE.CapsuleGeometry(radius, length, 3, radialSegments);
  const direction = b.clone().sub(a).normalize();
  const quat = new THREE.Quaternion().setFromUnitVectors(UP, direction);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  geometry.applyMatrix4(new THREE.Matrix4().compose(mid, quat, UNIT_SCALE));
  return geometry;
}

/** Centres of a hexagonal pack of `rings` rings around a middle cell. */
export function hexCells(pitch: number, rings: number): Array<[number, number]> {
  const cells: Array<[number, number]> = [[0, 0]];
  for (let ring = 1; ring <= rings; ring += 1) {
    // Walk the six sides of the ring, `ring` cells to a side.
    let q = ring;
    let r = 0;
    const steps: Array<[number, number]> = [[-1, 1], [-1, 0], [0, -1], [1, -1], [1, 0], [0, 1]];
    for (const [dq, dr] of steps) {
      for (let i = 0; i < ring; i += 1) {
        cells.push([pitch * (q + r / 2), pitch * (r * Math.sqrt(3)) / 2]);
        q += dq;
        r += dr;
      }
    }
  }
  return cells;
}

/** Deterministic random numbers, so a layout is the same on every render. */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
