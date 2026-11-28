/**
 * The pools of light the beams make where they land, drawn as soft additive
 * discs on the floor, ceiling or wall: one instanced draw for every fixture,
 * and no light for any surface to loop over (docs/PREVIZ_PERFORMANCE.md).
 *
 * The frame loop that moves the fixtures writes one slot per fixture into a
 * `PoolBuffer`; `updatePools` turns that into the decals (and, with Shadows on,
 * points the few real spot lights). Size and brightness come from poolLight.ts,
 * the same numbers the spot lights were driven by.
 *
 * What a decal cannot do: light the crowd, the risers or the DJ the beam passes
 * through, or catch a gloss highlight on the dance floor. With Shadows on, the
 * brightest few beams get a real light again and do all of that.
 */
import { memo, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import * as THREE from 'three';
import {
  POOL_DECAL_LIFT,
  POOL_LIGHT_DECAY,
  POOL_LIGHT_PENUMBRA,
  poolDecal,
  poolDecalStrength,
  poolLightIntensity,
  poolLightRange,
} from './poolLight';
import { REAL_POOL_LIGHTS, assignPoolLights } from './poolPick';
import {
  GOBO_ATLAS_CELLS, GOBO_ATLAS_INSET, GOBO_CELL_PX, GOBO_FILL, GOBO_POOL_SPAN, buildGoboAtlasPixels,
} from './gobo';
import { createLookUniforms } from './lookUniforms';
import type { LookUniforms } from './lookUniforms';

/**
 * One slot per fixture, written by the fixtures' frame loop. Plain typed
 * arrays, so nothing is allocated per frame and nothing goes through React.
 */
export type PoolBuffer = {
  capacity: number;
  /** 1 when the slot was written this frame and the beam lands on a surface. */
  active: Uint8Array;
  /** The fixture's level this frame, strobe included: 0 to 1. */
  level: Float32Array;
  /** Its colour, linear 0 to 1, three per slot. */
  color: Float32Array;
  /** Where its light comes from (the fixture's own position, lifted if it stands), three per slot. */
  origin: Float32Array;
  /** Which way the beam points, a unit vector, three per slot. */
  dir: Float32Array;
  /** Distance along the beam from `origin` to where it lands. */
  reach: Float32Array;
  /** How far down the beam from `origin` the light sits (the lens). */
  lightDepth: Float32Array;
  /** The light's cone, radians either side of its axis. */
  cone: Float32Array;
  /** Normal of the surface it lands on, three per slot. All zero: it lands on nothing. */
  normal: Float32Array;
  /** The gobo in the beam, as an atlas pattern (gobo.ts); 0 is an open pool. */
  gobo: Float32Array;
  /** The gobo's turn, radians. */
  goboAngle: Float32Array;
};

export function createPoolBuffer(capacity: number): PoolBuffer {
  const n = Math.max(0, Math.floor(capacity));
  return {
    capacity: n,
    active: new Uint8Array(n),
    level: new Float32Array(n),
    color: new Float32Array(n * 3),
    origin: new Float32Array(n * 3),
    dir: new Float32Array(n * 3),
    reach: new Float32Array(n),
    lightDepth: new Float32Array(n),
    cone: new Float32Array(n),
    normal: new Float32Array(n * 3),
    gobo: new Float32Array(n),
    goboAngle: new Float32Array(n),
  };
}

/** Write one fixture's pool for this frame. */
export function writePoolSlot(
  buffer: PoolBuffer,
  index: number,
  level: number,
  r: number,
  g: number,
  b: number,
  originX: number,
  originY: number,
  originZ: number,
  dir: { x: number; y: number; z: number },
  reach: number,
  lightDepth: number,
  coneRad: number,
  surface: { x: number; y: number; z: number },
  gobo = 0,
  goboAngle = 0,
): void {
  if (index < 0 || index >= buffer.capacity) return;
  buffer.gobo[index] = gobo;
  buffer.goboAngle[index] = goboAngle;
  const k = index * 3;
  const lands = surface.x !== 0 || surface.y !== 0 || surface.z !== 0;
  buffer.active[index] = lands && level > 0 ? 1 : 0;
  buffer.level[index] = level;
  buffer.color[k] = r;
  buffer.color[k + 1] = g;
  buffer.color[k + 2] = b;
  buffer.origin[k] = originX;
  buffer.origin[k + 1] = originY;
  buffer.origin[k + 2] = originZ;
  buffer.dir[k] = dir.x;
  buffer.dir[k + 1] = dir.y;
  buffer.dir[k + 2] = dir.z;
  buffer.reach[index] = reach;
  buffer.lightDepth[index] = lightDepth;
  buffer.cone[index] = coneRad;
  buffer.normal[k] = surface.x;
  buffer.normal[k + 1] = surface.y;
  buffer.normal[k + 2] = surface.z;
}

/** A grazing beam's pool is drawn at most this many times longer than it is wide. */
const MAX_STRETCH = 5;

/**
 * Pack one decal: its matrix (16 floats at `matrixOut[matrixOffset]`) and its
 * colour and inner fade (4 floats at `paintOut[paintOffset]`). Returns false
 * when the slot has no pool to draw. Pure arithmetic; exported for tests.
 *
 * The decal is a 2 x 2 quad in its own XY plane. It is laid on the surface,
 * centred where the beam lands, as wide as the pool across the beam and
 * stretched along it by how obliquely the beam meets the surface.
 */
export function packPoolDecal(
  buffer: PoolBuffer,
  index: number,
  matrixOut: Float32Array,
  matrixOffset: number,
  paintOut: Float32Array,
  paintOffset: number,
  /** Where to write the gobo pattern and its turn (2 floats), if anywhere. */
  goboOut?: Float32Array | null,
  goboOffset = 0,
): boolean {
  if (!buffer.active[index]) return false;
  const k = index * 3;
  let nx = buffer.normal[k];
  let ny = buffer.normal[k + 1];
  let nz = buffer.normal[k + 2];
  const dx = buffer.dir[k];
  const dy = buffer.dir[k + 1];
  const dz = buffer.dir[k + 2];
  const along = dx * nx + dy * ny + dz * nz;
  const cosIncidence = Math.abs(along);
  if (!(cosIncidence > 0.02)) return false;
  // The surface's normal turned to face the light.
  if (along > 0) {
    nx = -nx;
    ny = -ny;
    nz = -nz;
  }

  const reach = buffer.reach[index];
  const { outer, innerFrac } = poolDecal(reach - buffer.lightDepth[index], buffer.cone[index]);
  const strength = poolDecalStrength(buffer.level[index]) * cosIncidence;
  if (!(outer > 0) || !(strength > 0)) return false;

  // u: the beam's heading along the surface; v: across it.
  let ux = dx - along * buffer.normal[k];
  let uy = dy - along * buffer.normal[k + 1];
  let uz = dz - along * buffer.normal[k + 2];
  let ul = Math.hypot(ux, uy, uz);
  if (ul < 1e-5) {
    // Square on: any direction in the surface will do.
    if (Math.abs(nx) < 0.9) {
      ux = 0; uy = -nz; uz = ny;
    } else {
      ux = nz; uy = 0; uz = -nx;
    }
    ul = Math.hypot(ux, uy, uz);
  }
  ux /= ul;
  uy /= ul;
  uz /= ul;
  const vx = ny * uz - nz * uy;
  const vy = nz * ux - nx * uz;
  const vz = nx * uy - ny * ux;

  const stretch = Math.min(MAX_STRETCH, 1 / cosIncidence);
  const major = outer * stretch;
  const px = buffer.origin[k] + dx * reach + nx * POOL_DECAL_LIFT;
  const py = buffer.origin[k + 1] + dy * reach + ny * POOL_DECAL_LIFT;
  const pz = buffer.origin[k + 2] + dz * reach + nz * POOL_DECAL_LIFT;

  // Column-major, as three.js stores a Matrix4.
  const m = matrixOut;
  const o = matrixOffset;
  m[o] = ux * major; m[o + 1] = uy * major; m[o + 2] = uz * major; m[o + 3] = 0;
  m[o + 4] = vx * outer; m[o + 5] = vy * outer; m[o + 6] = vz * outer; m[o + 7] = 0;
  m[o + 8] = nx; m[o + 9] = ny; m[o + 10] = nz; m[o + 11] = 0;
  m[o + 12] = px; m[o + 13] = py; m[o + 14] = pz; m[o + 15] = 1;

  paintOut[paintOffset] = buffer.color[k] * strength;
  paintOut[paintOffset + 1] = buffer.color[k + 1] * strength;
  paintOut[paintOffset + 2] = buffer.color[k + 2] * strength;
  paintOut[paintOffset + 3] = innerFrac;
  if (goboOut) {
    goboOut[goboOffset] = buffer.gobo[index];
    goboOut[goboOffset + 1] = buffer.goboAngle[index];
  }
  return true;
}

const POOL_VERTEX_SHADER = `
  attribute vec4 poolPaint;
  attribute vec2 poolGobo;
  varying vec2 vDisc;
  varying vec4 vPaint;
  varying vec2 vGobo;
  void main() {
    vDisc = position.xy;
    vPaint = poolPaint;
    vGobo = poolGobo;
    vec4 place = vec4(position, 1.0);
    #ifdef USE_INSTANCING
      place = instanceMatrix * place;
    #endif
    gl_Position = projectionMatrix * viewMatrix * modelMatrix * place;
  }
`;

// Full inside the inner cone, nothing at the edge, a smoothstep on the squared
// radius between: see poolDecal. With a gobo in (and Gobos on), the pattern
// from the atlas, turned by the gobo's angle, across GOBO_POOL_SPAN of the
// decal, under the same soft fall-off, so the pool keeps its soft edge and
// its colour. Open pools never read the atlas and draw as before.
const POOL_FRAGMENT_SHADER = `
  uniform sampler2D uGoboAtlas;
  uniform float uGobos;
  varying vec2 vDisc;
  varying vec4 vPaint;
  varying vec2 vGobo;
  void main() {
    float r2 = dot(vDisc, vDisc);
    if (r2 >= 1.0) discard;
    float inner2 = vPaint.w * vPaint.w;
    float fall = 1.0 - smoothstep(inner2, 1.0, r2);
    float pattern = 1.0;
    if (uGobos > 0.5 && vGobo.x > 0.5) {
      float c = cos(vGobo.y);
      float s = sin(vGobo.y);
      vec2 g = vec2(c * vDisc.x - s * vDisc.y, s * vDisc.x + c * vDisc.y) / ${GOBO_POOL_SPAN.toFixed(3)};
      vec2 cell = clamp(g * 0.5 + 0.5, ${GOBO_ATLAS_INSET.toFixed(5)}, ${(1 - GOBO_ATLAS_INSET).toFixed(5)});
      float through = texture2D(uGoboAtlas, vec2((floor(vGobo.x + 0.5) + cell.x) / ${GOBO_ATLAS_CELLS.toFixed(1)}, cell.y)).r;
      through *= step(dot(g, g), 1.0);
      pattern = mix(${GOBO_FILL.toFixed(3)}, 1.0, through);
    }
    gl_FragColor = vec4(vPaint.rgb * fall * pattern, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

let goboAtlas: THREE.DataTexture | null = null;

/** The gobo atlas (gobo.ts), made on first use and kept. */
function goboAtlasTexture(): THREE.DataTexture {
  if (!goboAtlas) {
    goboAtlas = new THREE.DataTexture(
      new Uint8Array(buildGoboAtlasPixels()), GOBO_ATLAS_CELLS * GOBO_CELL_PX, GOBO_CELL_PX, THREE.RGBAFormat,
    );
    goboAtlas.magFilter = THREE.LinearFilter;
    goboAtlas.minFilter = THREE.LinearMipmapLinearFilter;
    goboAtlas.generateMipmaps = true;
    goboAtlas.needsUpdate = true;
  }
  return goboAtlas;
}

function createPoolMaterial(look: LookUniforms): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: POOL_VERTEX_SHADER,
    fragmentShader: POOL_FRAGMENT_SHADER,
    uniforms: {
      uGoboAtlas: { value: goboAtlasTexture() },
      uGobos: look.gobos,
    },
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
  });
}

/** One real spot light and its target, both in the scene so three works out where it points. */
type RealLight = { light: THREE.SpotLight; target: THREE.Object3D };

/** What `updatePools` drives. Made by `FloorPools`. */
export type PoolRenderer = {
  mesh: THREE.InstancedMesh | null;
  paint: THREE.InstancedBufferAttribute | null;
  /** Each drawn pool's gobo pattern and turn. */
  gobo: THREE.InstancedBufferAttribute | null;
  lights: RealLight[];
  assignment: Int32Array;
  taken: Uint8Array;
};

/**
 * Draw this frame's pools from `buffer`, for the first `count` slots. Called
 * once a frame by whatever wrote the buffer, after it wrote it.
 */
export function updatePools(renderer: PoolRenderer, buffer: PoolBuffer, count: number): void {
  const n = Math.min(count, buffer.capacity);
  const { lights, assignment, taken } = renderer;

  if (lights.length > 0) {
    if (taken.length < n) renderer.taken = new Uint8Array(buffer.capacity);
    assignPoolLights(buffer.level, n, (i) => buffer.active[i] === 1, assignment, renderer.taken);
    for (let slot = 0; slot < lights.length; slot += 1) {
      const { light, target } = lights[slot];
      const i = assignment[slot];
      if (i < 0) {
        light.intensity = 0;
        continue;
      }
      const k = i * 3;
      const depth = buffer.lightDepth[i];
      const dx = buffer.dir[k];
      const dy = buffer.dir[k + 1];
      const dz = buffer.dir[k + 2];
      light.position.set(buffer.origin[k] + dx * depth, buffer.origin[k + 1] + dy * depth, buffer.origin[k + 2] + dz * depth);
      target.position.set(light.position.x + dx, light.position.y + dy, light.position.z + dz);
      light.color.setRGB(buffer.color[k], buffer.color[k + 1], buffer.color[k + 2]);
      light.intensity = poolLightIntensity(buffer.level[i]);
      light.angle = buffer.cone[i];
      light.distance = poolLightRange(buffer.reach[i]);
    }
  }

  const mesh = renderer.mesh;
  const paint = renderer.paint;
  if (!mesh || !paint) return;
  const matrices = mesh.instanceMatrix.array as Float32Array;
  const paints = paint.array as Float32Array;
  const gobo = renderer.gobo;
  const gobos = gobo ? (gobo.array as Float32Array) : null;
  const limit = Math.min(n, paint.count, gobo ? gobo.count : paint.count);
  const realTaken = lights.length > 0 ? renderer.taken : null;
  let drawn = 0;
  for (let i = 0; i < limit; i += 1) {
    if (realTaken && realTaken[i]) continue;
    if (packPoolDecal(buffer, i, matrices, drawn * 16, paints, drawn * 4, gobos, drawn * 2)) drawn += 1;
  }
  mesh.count = drawn;
  if (drawn > 0) {
    mesh.instanceMatrix.needsUpdate = true;
    paint.needsUpdate = true;
    if (gobo) gobo.needsUpdate = true;
  }
}

/** The unit disc every pool is drawn from: a 2 x 2 quad, faded to a disc in its shader. */
const poolQuad = new THREE.PlaneGeometry(2, 2);

/**
 * The decal pools and, with `realLights` on, the few shadow-casting spot
 * lights. `renderer` is filled in here and read by `updatePools`.
 */
export const FloorPools = memo(function FloorPools({
  capacity,
  realLights,
  renderer,
  look,
}: {
  capacity: number;
  realLights: boolean;
  renderer: MutableRefObject<PoolRenderer>;
  /** The shared look uniforms (Gobos on or off). Without them, gobos are on. */
  look?: LookUniforms;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const uniforms = useMemo(() => look ?? createLookUniforms(), [look]);
  const material = useMemo(() => createPoolMaterial(uniforms), [uniforms]);
  useEffect(() => () => material.dispose(), [material]);

  // The quad with one paint slot per instance, its own copy so the attribute
  // is not left on a shared geometry.
  const size = Math.max(1, capacity);
  const built = useMemo(() => {
    const geometry = poolQuad.clone();
    const paint = new THREE.InstancedBufferAttribute(new Float32Array(size * 4), 4);
    paint.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('poolPaint', paint);
    const gobo = new THREE.InstancedBufferAttribute(new Float32Array(size * 2), 2);
    gobo.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('poolGobo', gobo);
    return { geometry, paint, gobo };
  }, [size]);
  useEffect(() => () => built.geometry.dispose(), [built]);

  const lights = useMemo<RealLight[]>(() => {
    if (!realLights) return [];
    return Array.from({ length: REAL_POOL_LIGHTS }, () => {
      const light = new THREE.SpotLight(0xffffff, 0, 10, 0.3, POOL_LIGHT_PENUMBRA, POOL_LIGHT_DECAY);
      light.castShadow = true;
      light.shadow.mapSize.set(512, 512);
      const target = new THREE.Object3D();
      light.target = target;
      return { light, target };
    });
  }, [realLights]);
  useEffect(() => () => lights.forEach(({ light }) => light.dispose()), [lights]);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (mesh) {
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.count = 0;
    }
    renderer.current = {
      mesh,
      paint: built.paint,
      gobo: built.gobo,
      lights,
      assignment: new Int32Array(lights.length).fill(-1),
      taken: new Uint8Array(size),
    };
  }, [renderer, built, lights, size]);

  return (
    <>
      {/* Not culled: the bounds three works out are for one quad at the origin. */}
      <instancedMesh
        key={size}
        ref={meshRef}
        args={[built.geometry, material, size]}
        frustumCulled={false}
        renderOrder={2}
        dispose={null}
      />
      {lights.map(({ light, target }, index) => (
        <group key={index}>
          <primitive object={light} />
          <primitive object={target} />
        </group>
      ))}
    </>
  );
});

/** A renderer with nothing to draw into yet: what the ref starts as. */
export function emptyPoolRenderer(): PoolRenderer {
  return { mesh: null, paint: null, gobo: null, lights: [], assignment: new Int32Array(0), taken: new Uint8Array(0) };
}
