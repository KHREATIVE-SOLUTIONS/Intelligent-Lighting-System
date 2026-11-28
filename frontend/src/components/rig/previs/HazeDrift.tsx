/**
 * The drifting haze (docs/PREVIZ_LOOK.md): a handful of large soft puffs, one
 * instanced draw, always turned to the camera, drifting slowly and glowing
 * faintly with the rig's light. Additive, no depth write, no lighting: what
 * they cost is fill rate, a few screens' worth of one texture read.
 *
 * Each puff fades out near the camera (so walking the camera into one shows
 * no flat sheet), at the floor and at the ceiling (so where a quad passes
 * through either there is no hard line).
 */
import { memo, useEffect, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { hazeNoisePixels, layoutHazePuffs } from './hazeDrift';
import type { HazeBounds } from './hazeDrift';
import type { LookUniforms } from './lookUniforms';

/** How much the puffs show of their own (a dark blue-grey) and of the rig's light. */
export const HAZE_PUFF_BASE: [number, number, number] = [0.018, 0.022, 0.03];
export const HAZE_PUFF_GLOW = 0.5;

let noiseTexture: THREE.DataTexture | null = null;

/** The puff texture, made on first use and kept: one 128 x 128 texture for every view. */
function hazeNoiseTexture(): THREE.DataTexture {
  if (!noiseTexture) {
    const size = 128;
    noiseTexture = new THREE.DataTexture(hazeNoisePixels(size), size, size, THREE.RGBAFormat);
    noiseTexture.magFilter = THREE.LinearFilter;
    noiseTexture.minFilter = THREE.LinearMipmapLinearFilter;
    noiseTexture.generateMipmaps = true;
    noiseTexture.needsUpdate = true;
  }
  return noiseTexture;
}

const VERTEX_SHADER = `
  attribute vec4 puff;
  attribute vec2 puffSeed;
  uniform float uTime;
  varying vec2 vUv;
  varying float vFade;
  varying float vHeight;
  void main() {
    vec3 centre = puff.xyz;
    float phase = puffSeed.x * 6.2832;
    centre.x += sin(uTime * 0.045 + phase) * 1.6;
    centre.z += cos(uTime * 0.037 + phase * 1.3) * 1.2;
    centre.y += sin(uTime * 0.06 + phase * 2.0) * 0.25;
    vec3 right = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
    vec3 up = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
    float turn = puffSeed.y * 6.2832 + uTime * 0.03 * (puffSeed.x - 0.5);
    float c = cos(turn);
    float s = sin(turn);
    vec2 corner = vec2(c * position.x - s * position.y, s * position.x + c * position.y);
    vec3 world = centre + (right * corner.x + up * corner.y) * puff.w;
    vec4 view = viewMatrix * vec4(world, 1.0);
    vUv = uv;
    vHeight = world.y;
    vFade = smoothstep(0.6, 4.0, -view.z);
    gl_Position = projectionMatrix * view;
  }
`;

const FRAGMENT_SHADER = `
  uniform sampler2D uNoise;
  uniform float uHaze;
  uniform vec3 uGlow;
  uniform vec3 uBase;
  uniform float uGlowGain;
  uniform vec2 uFloorCeiling;
  varying vec2 vUv;
  varying float vFade;
  varying float vHeight;
  void main() {
    float cloud = texture2D(uNoise, vUv).r;
    float inRoom = smoothstep(uFloorCeiling.x, uFloorCeiling.x + 1.2, vHeight)
      * (1.0 - smoothstep(uFloorCeiling.y - 0.8, uFloorCeiling.y, vHeight));
    float amount = cloud * vFade * inRoom * clamp(uHaze, 0.0, 1.0);
    gl_FragColor = vec4((uBase + uGlow * uGlowGain) * amount, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

const puffQuad = new THREE.PlaneGeometry(1, 1);

export const HazeDrift = memo(function HazeDrift({
  look,
  count,
  bounds,
}: {
  look: LookUniforms;
  count: number;
  bounds: HazeBounds;
}) {
  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uNoise: { value: hazeNoiseTexture() },
      uHaze: look.haze,
      uTime: look.time,
      uGlow: look.rigGlow,
      uBase: { value: new THREE.Color(HAZE_PUFF_BASE[0], HAZE_PUFF_BASE[1], HAZE_PUFF_BASE[2]) },
      uGlowGain: { value: HAZE_PUFF_GLOW },
      uFloorCeiling: { value: new THREE.Vector2(bounds.floorY, bounds.ceilingY) },
    },
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  }), [look, bounds.floorY, bounds.ceilingY]);
  useEffect(() => () => material.dispose(), [material]);

  const { xMin, xMax, zMin, zMax, floorY, ceilingY } = bounds;
  const geometry = useMemo(() => {
    const puffs = layoutHazePuffs(count, { xMin, xMax, zMin, zMax, floorY, ceilingY });
    const g = puffQuad.clone();
    g.setAttribute('puff', new THREE.InstancedBufferAttribute(puffs.puff, 4));
    g.setAttribute('puffSeed', new THREE.InstancedBufferAttribute(puffs.seed, 2));
    return g;
  }, [count, xMin, xMax, zMin, zMax, floorY, ceilingY]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame((_, delta) => {
    look.time.value += Math.min(delta, 0.1);
  });

  if (count <= 0) return null;
  return (
    // Not culled: the puffs are placed in the shader. Drawn after the beams and pools.
    <instancedMesh
      key={count}
      args={[geometry, material, count]}
      frustumCulled={false}
      renderOrder={3}
      dispose={null}
    />
  );
});
