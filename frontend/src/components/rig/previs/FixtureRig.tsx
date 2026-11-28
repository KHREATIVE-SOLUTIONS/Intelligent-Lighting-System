/**
 * Every fixture of the rig, drawn through a handful of instanced meshes and
 * moved by one frame callback (docs/PREVIZ_PERFORMANCE.md).
 *
 * Before, each fixture was its own component with its own frame callback and
 * five to eight meshes: about 800 draw calls for a 131-fixture rig. Now each
 * distinct geometry across the rig is one InstancedMesh: supports, drop pipes,
 * wall arms and plinths (written once per rig), yokes, housings and lenses per
 * model kind, all beams in one, all floor pools in one.
 *
 * The frame callback reads only refs: the output feed, and the per-fixture
 * runtime objects (fixtureRuntime.ts), which keep the beam reading, the
 * smoothing and the pan/tilt motion exactly as the component had them.
 *
 * Nothing is picked here: in Move fixtures mode FixtureDragLayer puts a handle
 * on every fixture, and those are what the pointer hits.
 */
import { memo, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import type { RigFixture } from '../../../types';
import {
  BEAM_INSTANCE_ATTRIBUTES, beamTube, createInstancedBeamMaterial, packBeamInstance,
} from './beamShape';
import type { BeamInstanceArrays } from './beamShape';
import type { BeamRoom } from './beamThrow';
import { getFixtureGeometry } from './fixtureGeometry';
import { supportParts, yokeGeometry } from './FixtureBody';
import { BEAM_VISIBLE_FROM, debugSnapshot, stepFixture, syncFixtureRuntime } from './fixtureRuntime';
import type { BeamDebugSnapshot, FixtureRuntime } from './fixtureRuntime';
import { FloorPools, createPoolBuffer, emptyPoolRenderer, updatePools, writePoolSlot } from './FloorPools';
import type { PoolRenderer } from './FloorPools';
import type { FixtureMount } from './layout';
import { bodyMaterial } from './materials';
import type { OutputFeed } from './outputFeed';

// A fixture not in the venue layout still has to draw: treat it as hung, with no pipe.
const DEFAULT_MOUNT: FixtureMount = { type: 'truss', drop: 0 };

/**
 * The lens: unlit, coloured per instance. Dark glass when the fixture is off,
 * its own colour three times over (clipped) when it is lit: what the lit
 * material with an emissive of three gave, without the per-pixel lighting.
 */
const lensMaterial = new THREE.MeshBasicMaterial({ toneMapped: false });
/** How much of the dark glass's own colour shows with no light on it: the room's ambient. */
const LENS_AMBIENT = 0.6;

export type RigPart = 'support' | 'yoke' | 'shell' | 'lens';

/** One instanced draw: a geometry, and every fixture part drawn with it. */
export type RigBatch = {
  key: string;
  part: RigPart;
  geometry: THREE.BufferGeometry;
  /** The fixture (index into the runtimes) and, for a support part, where it sits in the support frame. */
  members: Array<{ index: number; local: THREE.Matrix4 | null }>;
};

/**
 * Group a rig's parts into instanced draws, one per distinct geometry and part.
 * Pure: exported for tests.
 */
export function buildRigBatches(runtimes: readonly FixtureRuntime[]): RigBatch[] {
  const batches = new Map<string, RigBatch>();
  const add = (part: RigPart, geometry: THREE.BufferGeometry | null, index: number, local: THREE.Matrix4 | null) => {
    if (!geometry) return;
    const key = `${part}:${geometry.uuid}`;
    let batch = batches.get(key);
    if (!batch) {
      batch = { key, part, geometry, members: [] };
      batches.set(key, batch);
    }
    batch.members.push({ index, local });
  };
  runtimes.forEach((rt, index) => {
    for (const piece of supportParts(rt.modelKind, rt.mount, rt.bodyYawRad)) add('support', piece.geometry, index, piece.local);
    if (rt.isMovingHead) add('yoke', yokeGeometry(rt.modelKind, rt.mount.type === 'stand'), index, null);
    const geometry = getFixtureGeometry(rt.modelKind);
    add('shell', geometry.shell, index, null);
    add('lens', geometry.emitter, index, null);
  });
  return [...batches.values()];
}

const scratch = new THREE.Matrix4();

export const FixtureRig = memo(function FixtureRig({
  fixtures,
  mounts,
  feed,
  room,
  longestThrow,
  beamSegments,
  shadows,
  showLabels,
  debug,
  debugBuffer,
}: {
  fixtures: RigFixture[];
  mounts: Map<number, FixtureMount>;
  /** The frames the engine outputs, read in the frame loop. Never written. */
  feed: MutableRefObject<OutputFeed>;
  room: BeamRoom;
  longestThrow: number;
  beamSegments: number;
  /** Shadows on: the brightest few beams get a real, shadow-casting spot light. */
  shadows: boolean;
  showLabels: boolean;
  debug: boolean;
  debugBuffer: MutableRefObject<Record<number, BeamDebugSnapshot>>;
}) {
  // Runtimes by fixture id, kept across rigs so an edit that makes a new rig
  // (a drag, a nudge, an activation) does not snap every head back to centre.
  const states = useRef(new Map<number, FixtureRuntime>());
  const runtimes = useMemo(() => {
    const next = fixtures.map((fixture) => (
      syncFixtureRuntime(states.current.get(fixture.id), fixture, mounts.get(fixture.id) ?? DEFAULT_MOUNT)
    ));
    const keep = new Set(fixtures.map((fixture) => fixture.id));
    for (const id of [...states.current.keys()]) if (!keep.has(id)) states.current.delete(id);
    next.forEach((rt) => states.current.set(rt.id, rt));
    return next;
  }, [fixtures, mounts]);
  const count = runtimes.length;

  const batches = useMemo(() => buildRigBatches(runtimes), [runtimes]);
  const meshes = useRef(new Map<string, THREE.InstancedMesh>());

  // The supports do not move: written once per rig.
  useLayoutEffect(() => {
    for (const batch of batches) {
      if (batch.part !== 'support') continue;
      const mesh = meshes.current.get(batch.key);
      if (!mesh) continue;
      const array = mesh.instanceMatrix.array as Float32Array;
      batch.members.forEach((member, j) => {
        scratch.multiplyMatrices(runtimes[member.index].supportMatrix, member.local ?? scratch.identity());
        scratch.toArray(array, j * 16);
      });
      mesh.instanceMatrix.needsUpdate = true;
    }
  }, [batches, runtimes]);

  // All the beams: one tube with its shaping as per-instance attributes.
  const beamMaterial = useMemo(() => createInstancedBeamMaterial(), []);
  useEffect(() => () => beamMaterial.dispose(), [beamMaterial]);
  const beams = useMemo(() => {
    const size = Math.max(1, count);
    const geometry = beamTube(beamSegments).clone();
    const arrays: BeamInstanceArrays = {
      shape: new Float32Array(size * BEAM_INSTANCE_ATTRIBUTES.beamShape),
      surface: new Float32Array(size * BEAM_INSTANCE_ATTRIBUTES.beamSurface),
      paint: new Float32Array(size * BEAM_INSTANCE_ATTRIBUTES.beamPaint),
      length: new Float32Array(size * BEAM_INSTANCE_ATTRIBUTES.beamLength),
    };
    const attributes = [
      new THREE.InstancedBufferAttribute(arrays.shape, 4),
      new THREE.InstancedBufferAttribute(arrays.surface, 4),
      new THREE.InstancedBufferAttribute(arrays.paint, 4),
      new THREE.InstancedBufferAttribute(arrays.length, 1),
    ];
    const names = ['beamShape', 'beamSurface', 'beamPaint', 'beamLength'];
    attributes.forEach((attribute, i) => {
      attribute.setUsage(THREE.DynamicDrawUsage);
      geometry.setAttribute(names[i], attribute);
    });
    return { size, geometry, arrays, attributes };
  }, [beamSegments, count]);
  useEffect(() => () => beams.geometry.dispose(), [beams]);
  const beamMesh = useRef<THREE.InstancedMesh>(null);

  // The floor pools, one slot per fixture.
  const poolBuffer = useMemo(() => createPoolBuffer(count), [count]);
  const poolRenderer = useRef<PoolRenderer>(emptyPoolRenderer());

  useFrame((_, rawDelta) => {
    const now = performance.now();
    const frames = feed.current.frames;

    for (let i = 0; i < count; i += 1) {
      const rt = runtimes[i];
      stepFixture(rt, frames.get(rt.universe), rawDelta, now, room, longestThrow);
      const s = rt.smoothed;
      writePoolSlot(
        poolBuffer, i, rt.effectiveIntensity, s.r, s.g, s.b,
        rt.fixture.position_x, rt.sourceY, rt.fixture.position_z,
        rt.pointing, rt.reach, rt.lightDepth, rt.coneRad, rt.surface,
      );
      if (debug) debugBuffer.current[rt.id] = debugSnapshot(rt);
    }

    for (const batch of batches) {
      if (batch.part === 'support') continue;
      const mesh = meshes.current.get(batch.key);
      if (!mesh) continue;
      const array = mesh.instanceMatrix.array as Float32Array;
      const members = batch.members;
      for (let j = 0; j < members.length; j += 1) {
        const rt = runtimes[members[j].index];
        (batch.part === 'yoke' ? rt.yokeMatrix : rt.headMatrix).toArray(array, j * 16);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (batch.part === 'lens' && mesh.instanceColor) {
        const colors = mesh.instanceColor.array as Float32Array;
        for (let j = 0; j < members.length; j += 1) {
          const rt = runtimes[members[j].index];
          const s = rt.smoothed;
          const glow = rt.effectiveIntensity * 3;
          // Dark glass when the fixture is off, taking its colour as it comes up.
          const tint = 0.5 * Math.min(1, s.intensity * 4);
          colors[j * 3] = (0.045 + s.r * tint) * LENS_AMBIENT + s.r * glow;
          colors[j * 3 + 1] = (0.05 + s.g * tint) * LENS_AMBIENT + s.g * glow;
          colors[j * 3 + 2] = (0.06 + s.b * tint) * LENS_AMBIENT + s.b * glow;
        }
        mesh.instanceColor.needsUpdate = true;
      }
    }

    // Beams: only the lit ones, packed to the front, so a dark rig draws none.
    const mesh = beamMesh.current;
    if (mesh) {
      const array = mesh.instanceMatrix.array as Float32Array;
      let drawn = 0;
      for (let i = 0; i < count && drawn < beams.size; i += 1) {
        const rt = runtimes[i];
        if (rt.effectiveIntensity < BEAM_VISIBLE_FROM) continue;
        rt.beamMatrix.toArray(array, drawn * 16);
        const c = rt.beamColor;
        packBeamInstance(beams.arrays, drawn, rt.mouth, rt.reach, rt.endRadius, rt.surface, c.r, c.g, c.b, rt.effectiveIntensity);
        drawn += 1;
      }
      mesh.count = drawn;
      if (drawn > 0) {
        mesh.instanceMatrix.needsUpdate = true;
        for (const attribute of beams.attributes) attribute.needsUpdate = true;
      }
    }

    updatePools(poolRenderer.current, poolBuffer, count);
  });

  return (
    <>
      {/* Not culled: the bounds three works out are for one part at the origin. */}
      {batches.map((batch) => (
        <instancedMesh
          key={`${batch.key}:${batch.members.length}`}
          ref={(mesh: THREE.InstancedMesh | null) => {
            if (!mesh) return;
            meshes.current.set(batch.key, mesh);
            if (batch.part !== 'support') mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
            if (batch.part === 'lens' && (!mesh.instanceColor || mesh.instanceColor.count !== batch.members.length)) {
              mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(batch.members.length * 3), 3);
              mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
            }
          }}
          args={[batch.geometry, batch.part === 'lens' ? lensMaterial : bodyMaterial, batch.members.length]}
          castShadow={batch.part !== 'lens'}
          frustumCulled={false}
          dispose={null}
        />
      ))}
      <instancedMesh
        key={`beams:${beams.size}:${beamSegments}`}
        ref={beamMesh}
        args={[beams.geometry, beamMaterial, beams.size]}
        frustumCulled={false}
        renderOrder={1}
        dispose={null}
      />
      <FloorPools capacity={count} realLights={shadows} renderer={poolRenderer} />
      {showLabels && <FixtureLabels runtimes={runtimes} />}
    </>
  );
});

const labelStyle = {
  padding: '2px 6px',
  borderRadius: 4,
  background: 'rgba(0,0,0,0.65)',
  color: '#f0f4ff',
  fontSize: '10px',
  fontFamily: 'Consolas, monospace',
  lineHeight: 1.1,
  whiteSpace: 'nowrap' as const,
  border: '1px solid rgba(255,255,255,0.2)',
};

/** Fixture ID labels for quick patch/debug identification. Each is an HTML element: off by default on a big rig. */
function FixtureLabels({ runtimes }: { runtimes: FixtureRuntime[] }) {
  return (
    <>
      {runtimes.map((rt) => (
        <Html
          key={rt.id}
          position={[rt.fixture.position_x, rt.sourceY + 0.55, rt.fixture.position_z]}
          center
          occlude={false}
          distanceFactor={12}
          style={{ pointerEvents: 'none' }}
        >
          <div style={labelStyle}>{rt.fixture.id}</div>
        </Html>
      ))}
    </>
  );
}
