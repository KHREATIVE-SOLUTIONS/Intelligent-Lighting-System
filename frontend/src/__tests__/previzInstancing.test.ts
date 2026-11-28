import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import type { RigFixture } from '../types';
import {
  beamMouth, createBeamMaterial, packBeamInstance, shapeBeam,
} from '../components/rig/previs/beamShape';
import type { BeamInstanceArrays } from '../components/rig/previs/beamShape';
import { beamDirection, hangBeam } from '../components/rig/previs/beamThrow';
import type { BeamRoom } from '../components/rig/previs/beamThrow';
import { getFixtureGeometry } from '../components/rig/previs/fixtureGeometry';
import { supportParts, unitPipe } from '../components/rig/previs/FixtureBody';
import { buildRigBatches } from '../components/rig/previs/FixtureRig';
import {
  BEAM_VISIBLE_FROM, describeFixture, placeParts, stepFixture, syncFixtureRuntime,
} from '../components/rig/previs/fixtureRuntime';
import type { FixtureMount } from '../components/rig/previs/layout';

const room: BeamRoom = { ceilingY: 8, walls: { xMin: -10, xMax: 10, zMin: -10, zMax: 10 } };

function mover(id: number, extra: Partial<Record<string, unknown>> = {}): RigFixture {
  return {
    id,
    name: `Head ${id}`,
    universe: 0,
    dmx_address: 1,
    position_x: 1,
    position_y: 5,
    position_z: -2,
    rotation_x: 0,
    rotation_y: 0,
    rotation_z: 0,
    fixture: {
      fixture_type: 'moving_head',
      modes: [{
        id: 1,
        channels: [
          { channel_number: 1, channel_type: 'dimmer', name: 'Dimmer' },
          { channel_number: 2, channel_type: 'pan', name: 'Pan' },
          { channel_number: 3, channel_type: 'tilt', name: 'Tilt' },
        ],
      }],
    },
    ...extra,
  } as unknown as RigFixture;
}

const hung: FixtureMount = { type: 'truss', drop: 0.4 } as FixtureMount;

describe('packBeamInstance', () => {
  it('gives each instance the numbers shapeBeam gives the uniforms', () => {
    const mouth = beamMouth('beam');
    const surface = { x: 0, y: 1, z: 0, d: 0 };
    const material = createBeamMaterial();
    shapeBeam(material, mouth, 6.5, 0.4, surface);
    const arrays: BeamInstanceArrays = {
      shape: new Float32Array(8), surface: new Float32Array(8), paint: new Float32Array(8), length: new Float32Array(2),
    };
    packBeamInstance(arrays, 1, mouth, 6.5, 0.4, surface, 0.1, 0.2, 0.3, 0.7);
    const u = material.uniforms;
    expect(arrays.shape[4]).toBeCloseTo(u.beamNear.value.x, 6);
    expect(arrays.shape[5]).toBeCloseTo(u.beamNear.value.y, 6);
    expect(arrays.shape[6]).toBeCloseTo(u.beamFar.value.x, 6);
    expect(arrays.shape[7]).toBeCloseTo(u.beamFar.value.y, 6);
    expect(arrays.length[1]).toBeCloseTo(u.beamLength.value, 6);
    expect(Array.from(arrays.surface.slice(4, 8))).toEqual([0, 1, 0, 0]);
    expect(arrays.paint[7]).toBeCloseTo(0.7, 6);
    // Instance 0 untouched.
    expect(arrays.shape[0]).toBe(0);
  });
});

describe('fixture runtime', () => {
  it('draws the head along the direction the beam is worked out from', () => {
    const fixture = mover(1, { rotation_y: 30, rotation_x: 12, rotation_z: -8 });
    const rt = syncFixtureRuntime(undefined, fixture, hung);
    rt.panRad = 0.6;
    rt.tiltRad = -0.4;
    placeParts(rt);
    const drawn = new THREE.Vector3(0, -1, 0).transformDirection(rt.headMatrix);
    const worked = hangBeam(beamDirection(rt.tiltRad, rt.panRad, false, { x: 0, y: 0, z: 0 }), rt.hangRx, rt.hangRz, rt.bodyYawRad);
    expect(drawn.x).toBeCloseTo(worked.x, 5);
    expect(drawn.y).toBeCloseTo(worked.y, 5);
    expect(drawn.z).toBeCloseTo(worked.z, 5);
    // The head sits where the rig says the fixture is.
    const at = new THREE.Vector3().setFromMatrixPosition(rt.headMatrix);
    expect(at.x).toBeCloseTo(1, 6);
    expect(at.y).toBeCloseTo(5, 6);
    expect(at.z).toBeCloseTo(-2, 6);
  });

  it('is dark with no frame and lights and moves toward the frame it is sent', () => {
    const rt = syncFixtureRuntime(undefined, mover(1), hung);
    stepFixture(rt, undefined, 1 / 60, 0, room, 30);
    expect(rt.effectiveIntensity).toBe(0);
    expect(rt.effectiveIntensity < BEAM_VISIBLE_FROM).toBe(true);

    const frame = new Array(512).fill(0);
    frame[0] = 255;
    frame[1] = 200;
    frame[2] = 60;
    for (let i = 0; i < 240; i += 1) stepFixture(rt, frame, 1 / 60, i * 16.7, room, 30);
    expect(rt.effectiveIntensity).toBeGreaterThan(0.9);
    expect(Math.abs(rt.motion.targetPanDeg)).toBeGreaterThan(1);
    expect(rt.motion.currentPanDeg).toBeCloseTo(rt.motion.targetPanDeg, 0);
    expect(rt.motion.currentTiltDeg).toBeCloseTo(rt.motion.targetTiltDeg, 0);
    expect(rt.reach).toBeGreaterThan(0);
    expect(rt.endRadius).toBeGreaterThan(0);
  });

  it('keeps its motion state when the rig is replaced with an edited copy', () => {
    const first = syncFixtureRuntime(undefined, mover(7), hung);
    first.orientation.currentPanRad = 0.5;
    const edited = mover(7, { position_x: 3 });
    const again = syncFixtureRuntime(first, edited, hung);
    expect(again).toBe(first);
    expect(again.orientation.currentPanRad).toBe(0.5);
    expect(new THREE.Vector3().setFromMatrixPosition(again.supportMatrix).x).toBeCloseTo(3, 6);
  });

  it('agrees with describeFixture on the model', () => {
    const fixture = mover(2);
    expect(syncFixtureRuntime(undefined, fixture, hung).modelKind).toBe(describeFixture(fixture).modelKind);
  });
});

describe('instanced batches', () => {
  it('draws every part of the same geometry in one batch', () => {
    const runtimes = [1, 2, 3].map((id) => syncFixtureRuntime(undefined, mover(id), hung));
    const batches = buildRigBatches(runtimes);
    const geometry = getFixtureGeometry(runtimes[0].modelKind);
    const shell = batches.find((b) => b.part === 'shell' && b.geometry === geometry.shell);
    const lens = batches.find((b) => b.part === 'lens' && b.geometry === geometry.emitter);
    const yoke = batches.find((b) => b.part === 'yoke');
    const pipes = batches.find((b) => b.part === 'support' && b.geometry === unitPipe);
    expect(shell?.members.length).toBe(3);
    expect(lens?.members.length).toBe(3);
    expect(yoke?.members.length).toBe(3);
    // Two clamps each, a drop pipe on each.
    expect(pipes?.members.length).toBe(3 * geometry.clampXs.length);
    // Five draws for three heads, whatever the number of heads.
    expect(batches.length).toBe(5);
  });

  it('lists the support parts the old components drew', () => {
    const kind = 'beam';
    expect(supportParts(kind, { type: 'truss', drop: 0 } as FixtureMount, 0)).toHaveLength(1);
    expect(supportParts(kind, hung, 0)).toHaveLength(1 + getFixtureGeometry(kind).clampXs.length);
  });
});
