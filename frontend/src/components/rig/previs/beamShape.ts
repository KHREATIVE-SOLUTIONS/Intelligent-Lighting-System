/**
 * The shape of a drawn beam.
 *
 * A beam is a tube that starts at the fixture's lit face, as wide and as deep
 * as that face, and widens steadily to where the beam lands, where it is as
 * wide as the pool of light it makes. It used to be a cone from a point at the
 * fixture's middle: a wash, a batten or a strobe showed a pencil beam leaving
 * the centre of a wide face. It used to be as long as the fixture is high
 * whichever way it pointed, so a leaning beam stopped in the air short of its
 * own pool. And it used to spread by the same few degrees whatever the
 * fixture, so its pool was up to two and a half times as wide as its end.
 *
 * Every beam is the same unit tube, shaped in the vertex shader from four
 * numbers. Nothing is rebuilt as a head moves, and all beams of one quality
 * setting share one geometry.
 */
import * as THREE from 'three';
import { BEAM_LOOK_GLSL } from './beamLook';
import type { BeamSurface } from './beamThrow';
import { getFixtureGeometry } from './fixtureGeometry';
import type { FixtureModelKind } from './fixtureSpecs';
import { createLookUniforms } from './lookUniforms';
import type { LookUniforms } from './lookUniforms';

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
 * How far along its own line an edge of the beam may be cut or run on to meet
 * the surface, as a share of its length to the flat end. An edge that would
 * have to go further (a beam skimming the floor) keeps to these and ends in
 * the air on that side.
 */
export const BEAM_EDGE_SHORTEST = 0.4;
export const BEAM_EDGE_LONGEST = 2.5;

/**
 * Shapes the unit tube. `beamNear` and `beamFar` are the half-width and
 * half-depth at the mouth and at the far end, `beamLength` the distance
 * between them along the beam.
 *
 * `beamSurface` is what the beam lands on, as a plane in the room (see
 * `BeamSurface`). Each edge of the tube is followed from the mouth until it
 * meets that plane, so the end of the beam lies on the floor, the ceiling or
 * the wall as the pool does. With no surface (all zeros) the end is flat.
 */
export const BEAM_VERTEX_SHADER = `
  uniform vec2 beamNear;
  uniform vec2 beamFar;
  uniform float beamLength;
  uniform vec4 beamSurface;
  void main() {
    vec4 place = modelMatrix * vec4(position.x * beamNear.x, 0.0, position.z * beamNear.y, 1.0);
    if (position.y < -0.5) {
      vec4 flatEnd = modelMatrix * vec4(position.x * beamFar.x, -beamLength, position.z * beamFar.y, 1.0);
      vec3 edge = flatEnd.xyz - place.xyz;
      float closing = dot(beamSurface.xyz, edge);
      float share = 1.0;
      if (abs(closing) > 0.000001) {
        float meets = (beamSurface.w - dot(beamSurface.xyz, place.xyz)) / closing;
        if (meets > 0.0) share = clamp(meets, ${BEAM_EDGE_SHORTEST.toFixed(2)}, ${BEAM_EDGE_LONGEST.toFixed(2)});
      }
      place.xyz += edge * share;
    }
    gl_Position = projectionMatrix * viewMatrix * place;
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
      beamSurface: { value: new THREE.Vector4(0, 0, 0, 0) },
    },
    transparent: true,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
}

// ---------------------------------------------------------------------------
// Every beam in one draw (docs/PREVIZ_PERFORMANCE.md)
//
// The same tube and the same shaping as above, with the six uniforms turned
// into per-instance attributes so all of a rig's beams are one InstancedMesh.
// ---------------------------------------------------------------------------

/** Per-instance attribute names, and how many floats each takes. */
export const BEAM_INSTANCE_ATTRIBUTES = {
  beamShape: 4, // near half-width, near half-depth, far half-width, far half-depth
  beamSurface: 4,
  beamPaint: 4, // r, g, b, intensity
  beamLength: 1,
} as const;

// Besides the shape, the vertex shader hands the fragment shader what the soft
// beam needs (docs/PREVIZ_LOOK.md): how far down the beam the point is, in
// metres (0 all round the mouth, the edge's own length at the far end), the
// tube's outward normal in the room (radial, from the ellipse the ring is at)
// and the way to the eye.
export const INSTANCED_BEAM_VERTEX_SHADER = `
  attribute vec4 beamShape;
  attribute vec4 beamSurface;
  attribute vec4 beamPaint;
  attribute float beamLength;
  varying vec4 vBeamPaint;
  varying float vAlong;
  varying vec3 vNormalW;
  varying vec3 vToEye;
  void main() {
    mat4 placeMatrix = modelMatrix;
    #ifdef USE_INSTANCING
      placeMatrix = modelMatrix * instanceMatrix;
    #endif
    vBeamPaint = beamPaint;
    vec4 place = placeMatrix * vec4(position.x * beamShape.x, 0.0, position.z * beamShape.y, 1.0);
    vec2 across = vec2(position.x / max(beamShape.x, 0.0001), position.z / max(beamShape.y, 0.0001));
    vAlong = 0.0;
    if (position.y < -0.5) {
      vec4 flatEnd = placeMatrix * vec4(position.x * beamShape.z, -beamLength, position.z * beamShape.w, 1.0);
      vec3 edge = flatEnd.xyz - place.xyz;
      float closing = dot(beamSurface.xyz, edge);
      float share = 1.0;
      if (abs(closing) > 0.000001) {
        float meets = (beamSurface.w - dot(beamSurface.xyz, place.xyz)) / closing;
        if (meets > 0.0) share = clamp(meets, ${BEAM_EDGE_SHORTEST.toFixed(2)}, ${BEAM_EDGE_LONGEST.toFixed(2)});
      }
      place.xyz += edge * share;
      vAlong = length(edge) * share;
      across = vec2(position.x / max(beamShape.z, 0.0001), position.z / max(beamShape.w, 0.0001));
    }
    vNormalW = mat3(placeMatrix) * vec3(across.x, 0.0, across.y);
    vToEye = cameraPosition - place.xyz;
    gl_Position = projectionMatrix * viewMatrix * place;
  }
`;

// Soft: bright at the lens, falling off down the beam, fading at the edge of
// the cone, all scaled by the haze (beamLook.ts). Flat (Soft beams off): one
// strength end to end, the beam as it was, scaled by the haze. Tone mapped and
// put in the output colour space like three's own materials (in a render
// target the two includes do nothing and OutputPass does it instead). That
// brings Bloom on and off closer, not level: the strength is in alpha, which
// the composer blends in linear light and the direct path in display space,
// so beams read brighter with Bloom on (docs/PREVIZ_LOOK.md).
export const INSTANCED_BEAM_FRAGMENT_SHADER = `
  uniform float uHaze;
  uniform float uSoftBeams;
  varying vec4 vBeamPaint;
  varying float vAlong;
  varying vec3 vNormalW;
  varying vec3 vToEye;
  ${BEAM_LOOK_GLSL}
  void main() {
    float level = vBeamPaint.a;
    float alpha;
    if (uSoftBeams > 0.5) {
      float facing = abs(dot(normalize(vNormalW), normalize(vToEye)));
      alpha = softBeamAlpha(level, vAlong, uHaze, facing);
    } else {
      alpha = flatBeamAlpha(level, uHaze);
    }
    gl_FragColor = vec4(vBeamPaint.rgb, clamp(alpha, 0.0, 1.0));
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

/**
 * The material every beam of a rig is drawn with, in one instanced draw.
 * `look` gives it the shared haze and soft-beam uniforms; without one it has
 * its own, at the defaults.
 */
export function createInstancedBeamMaterial(look: LookUniforms = createLookUniforms()): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: INSTANCED_BEAM_VERTEX_SHADER,
    fragmentShader: INSTANCED_BEAM_FRAGMENT_SHADER,
    uniforms: {
      uHaze: look.haze,
      uSoftBeams: look.softBeams,
    },
    transparent: true,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
}

/** The typed arrays one instanced beam mesh draws from. */
export type BeamInstanceArrays = {
  shape: Float32Array;
  surface: Float32Array;
  paint: Float32Array;
  length: Float32Array;
};

/**
 * Write one beam's shape and paint at instance `i`: the same numbers
 * `shapeBeam` gives the uniforms, plus its colour and intensity.
 */
export function packBeamInstance(
  out: BeamInstanceArrays,
  i: number,
  mouth: BeamMouth,
  landing: number,
  endRadius: number,
  surface: BeamSurface,
  r: number,
  g: number,
  b: number,
  intensity: number,
): void {
  const k = i * 4;
  out.shape[k] = mouth.halfX;
  out.shape[k + 1] = mouth.halfZ;
  out.shape[k + 2] = Math.max(mouth.halfX, endRadius);
  out.shape[k + 3] = Math.max(mouth.halfZ, endRadius);
  out.surface[k] = surface.x;
  out.surface[k + 1] = surface.y;
  out.surface[k + 2] = surface.z;
  out.surface[k + 3] = surface.d;
  out.paint[k] = r;
  out.paint[k + 1] = g;
  out.paint[k + 2] = b;
  out.paint[k + 3] = intensity;
  out.length[i] = beamLengthFrom(mouth, landing);
}

/**
 * Give a beam its shape for this frame: from `mouth` to where the beam lands,
 * `landing` being the distance from the light source, ending as wide as the
 * pool it makes there (`endRadius`, see `poolRadius`) and lying on `surface`.
 * It never narrows: an end smaller than the mouth is drawn as wide as the
 * mouth, as a batten a metre from its wall is.
 */
export function shapeBeam(
  material: THREE.ShaderMaterial,
  mouth: BeamMouth,
  landing: number,
  endRadius: number,
  surface: BeamSurface,
): void {
  const uniforms = material.uniforms;
  uniforms.beamNear.value.set(mouth.halfX, mouth.halfZ);
  uniforms.beamFar.value.set(Math.max(mouth.halfX, endRadius), Math.max(mouth.halfZ, endRadius));
  uniforms.beamLength.value = beamLengthFrom(mouth, landing);
  uniforms.beamSurface.value.set(surface.x, surface.y, surface.z, surface.d);
}
