/**
 * The shape of a drawn beam.
 *
 * A beam is a tube that starts at the fixture's lit face, as wide and as deep
 * as that face, and widens steadily to where the beam lands. It used to be a
 * cone from a point at the fixture's middle: a wash, a batten or a strobe
 * showed a pencil beam leaving the centre of a wide face. And it used to be as
 * long as the fixture is high whichever way it pointed, so a leaning beam
 * stopped in the air short of its own pool.
 *
 * Every beam is the same unit tube, shaped in the vertex shader from three
 * numbers. Nothing is rebuilt as a head moves, and all beams of one quality
 * setting share one geometry.
 */
import * as THREE from 'three';
import { getFixtureGeometry } from './fixtureGeometry';
import type { FixtureModelKind } from './fixtureSpecs';

/** Where a fixture's beam leaves it, and its half-width and half-depth there. */
export type BeamMouth = {
  halfX: number;
  halfZ: number;
  /** How far down the beam from the light source the lit face is. */
  offset: number;
};

const mouths = new Map<FixtureModelKind, BeamMouth>();

/**
 * The mouth of the beam for a kind of fixture: the lit face of its model,
 * measured from the model itself so the two cannot disagree.
 */
export function beamMouth(kind: FixtureModelKind): BeamMouth {
  let mouth = mouths.get(kind);
  if (!mouth) {
    const emitter = getFixtureGeometry(kind).emitter;
    if (!emitter.boundingBox) emitter.computeBoundingBox();
    const box = emitter.boundingBox!;
    mouth = {
      halfX: (box.max.x - box.min.x) / 2,
      halfZ: (box.max.z - box.min.z) / 2,
      // The lit face looks down the model's -Y; its outermost point is the mouth.
      offset: Math.max(0, -box.min.y),
    };
    mouths.set(kind, mouth);
  }
  return mouth;
}

/** The beam is never drawn shorter than this, so it cannot turn inside out. */
const SHORTEST_BEAM = 0.05;

/** Length of the drawn beam: from its mouth to where the beam lands. */
export function beamLengthFrom(mouth: BeamMouth, landing: number): number {
  const length = landing - mouth.offset;
  return length > SHORTEST_BEAM ? length : SHORTEST_BEAM;
}

/** How much wider the beam is, on each side, at its far end than at its mouth. */
export function beamWidening(length: number, spreadHalfAngleDeg: number): number {
  return length * Math.tan((spreadHalfAngleDeg * Math.PI) / 180);
}

const tubes = new Map<number, THREE.BufferGeometry>();

/**
 * The unit tube every beam is drawn from: an open cylinder of radius 1 running
 * from y = 0 (the mouth) down to y = -1 (the far end). One per segment count.
 */
export function beamTube(segments: number): THREE.BufferGeometry {
  let tube = tubes.get(segments);
  if (!tube) {
    tube = new THREE.CylinderGeometry(1, 1, 1, segments, 1, true).translate(0, -0.5, 0);
    tubes.set(segments, tube);
  }
  return tube;
}

/**
 * Shapes the unit tube: `beamNear` and `beamFar` are the half-width and
 * half-depth at the mouth and at the far end, `beamLength` the distance
 * between them.
 */
export const BEAM_VERTEX_SHADER = `
  uniform vec2 beamNear;
  uniform vec2 beamFar;
  uniform float beamLength;
  void main() {
    float along = -position.y;
    vec2 halfSize = mix(beamNear, beamFar, along);
    vec3 shaped = vec3(position.x * halfSize.x, -along * beamLength, position.z * halfSize.y);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(shaped, 1.0);
  }
`;

/** One strength from the mouth to the far end. */
export const BEAM_FRAGMENT_SHADER = `
  uniform vec3 beamColor;
  uniform float beamIntensity;
  void main() {
    gl_FragColor = vec4(beamColor, beamIntensity * 0.42);
  }
`;

/** The material a beam is drawn with. One per fixture, for as long as it is drawn. */
export function createBeamMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: BEAM_VERTEX_SHADER,
    fragmentShader: BEAM_FRAGMENT_SHADER,
    uniforms: {
      beamColor: { value: new THREE.Color(1, 1, 1) },
      beamIntensity: { value: 0 },
      beamNear: { value: new THREE.Vector2(0.05, 0.05) },
      beamFar: { value: new THREE.Vector2(0.05, 0.05) },
      beamLength: { value: 1 },
    },
    transparent: true,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
}

/**
 * Give a beam its shape for this frame: from `mouth`, widening by
 * `spreadHalfAngleDeg` either side, to where the beam lands, `landing` being
 * the distance from the light source.
 */
export function shapeBeam(
  material: THREE.ShaderMaterial,
  mouth: BeamMouth,
  landing: number,
  spreadHalfAngleDeg: number,
): void {
  const length = beamLengthFrom(mouth, landing);
  const widening = beamWidening(length, spreadHalfAngleDeg);
  const uniforms = material.uniforms;
  uniforms.beamNear.value.set(mouth.halfX, mouth.halfZ);
  uniforms.beamFar.value.set(mouth.halfX + widening, mouth.halfZ + widening);
  uniforms.beamLength.value = length;
}
