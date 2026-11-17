/**
 * The crowd on the dance floor.
 *
 * Four instanced meshes (bodies, heads, hair, arms) draw everyone in four draw
 * calls. Each frame one matrix per body, head and arm is rewritten from the
 * beat clock, which is a few hundred small matrix products: cheap enough that
 * it never shows up next to the lighting.
 *
 * People dip on the beat and rise between beats, sway over two beats, and nod.
 * As the room's energy rises more of them put their arms up, and in a drop
 * some of them jump. With no music they stand and shift about.
 */
import { memo, useLayoutEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { capsule, cylY, merge, paint, place } from './geometryKit';
import { advanceBeatClock } from './beatClock';
import type { BeatClock } from './beatClock';
import { placeCrowd } from './crowdLayout';
import type { CrowdPerson } from './crowdLayout';
import type { ClubLayout } from './layout';

/** The person model is this tall; each instance is scaled to its own height. */
const MODEL_HEIGHT = 1.72;
const NECK_Y = 1.47;
const SHOULDER_X = 0.218;
const SHOULDER_Y = 1.385;

type PersonGeometry = {
  body: THREE.BufferGeometry;
  head: THREE.BufferGeometry;
  hair: THREE.BufferGeometry;
  arm: THREE.BufferGeometry;
};
let personGeometry: PersonGeometry | null = null;

/**
 * Vertex colours here are shades, not colours: each is multiplied by the
 * instance's own colour, so one model gives everyone a different shirt with
 * darker trousers.
 */
function getPersonGeometry(): PersonGeometry {
  if (personGeometry) return personGeometry;

  const torso = cylY(0.19, 0.155, 0.56, 10);
  torso.scale(1, 1, 0.62);
  const body = merge([
    paint(capsule([-0.085, 0.09, 0], [-0.085, 0.82, 0], 0.078, 6), '#8a8a8a'),
    paint(capsule([0.085, 0.09, 0], [0.085, 0.82, 0], 0.078, 6), '#8a8a8a'),
    paint(place(torso, [0, 1.12, 0]), '#ffffff'),
    paint(capsule([-0.185, SHOULDER_Y, 0], [0.185, SHOULDER_Y, 0], 0.075, 6), '#ffffff'),
  ]);

  const skull = new THREE.SphereGeometry(0.1, 10, 8);
  skull.scale(1, 1.14, 1);
  const head = merge([
    paint(place(cylY(0.048, 0.052, 0.1, 8), [0, NECK_Y, 0]), '#ffffff'),
    paint(place(skull, [0, 1.6, 0]), '#ffffff'),
  ]);
  // Hair sits on the crown and the back of the head, tipped back so it does
  // not come down over the face.
  const hair = merge([
    paint(place(
      new THREE.SphereGeometry(0.109, 10, 5, 0, Math.PI * 2, 0, Math.PI * 0.4),
      [0, 1.618, -0.012],
      [-0.6, 0, 0],
    ), '#ffffff'),
  ]);

  // Modelled hanging from the shoulder, which is the origin.
  const arm = merge([paint(capsule([0, 0, 0], [0, -0.54, 0], 0.042, 6), '#ffffff')]);

  personGeometry = { body, head, hair, arm };
  return personGeometry;
}

const crowdMaterial = new THREE.MeshStandardMaterial({
  vertexColors: true,
  metalness: 0,
  roughness: 0.88,
});

const smoothstep = (edge0: number, edge1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
};

function CrowdInstances({ people, clock }: { people: CrowdPerson[]; clock: MutableRefObject<BeatClock> }) {
  const bodyRef = useRef<THREE.InstancedMesh>(null);
  const headRef = useRef<THREE.InstancedMesh>(null);
  const hairRef = useRef<THREE.InstancedMesh>(null);
  const armRef = useRef<THREE.InstancedMesh>(null);
  const geometry = getPersonGeometry();
  const count = people.length;

  // How far up each person's arms are, eased so they rise and fall.
  const armsUp = useMemo(() => new Float32Array(count), [count]);

  const scratch = useMemo(() => ({
    bodyMatrix: new THREE.Matrix4(),
    local: new THREE.Matrix4(),
    out: new THREE.Matrix4(),
    position: new THREE.Vector3(),
    quaternion: new THREE.Quaternion(),
    scale: new THREE.Vector3(),
    bodyEuler: new THREE.Euler(0, 0, 0, 'YXZ'),
    armEuler: new THREE.Euler(0, 0, 0, 'XYZ'),
  }), []);

  useLayoutEffect(() => {
    const color = new THREE.Color();
    people.forEach((person, i) => {
      bodyRef.current?.setColorAt(i, color.set(person.shirt));
      headRef.current?.setColorAt(i, color.set(person.skin));
      hairRef.current?.setColorAt(i, color.set(person.hair));
      const arm = person.sleeves ? person.shirt : person.skin;
      armRef.current?.setColorAt(i * 2, color.set(arm));
      armRef.current?.setColorAt(i * 2 + 1, color.set(arm));
    });
    for (const mesh of [bodyRef.current, headRef.current, hairRef.current, armRef.current]) {
      if (!mesh) continue;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }, [people]);

  useFrame((state, delta) => {
    const body = bodyRef.current;
    const head = headRef.current;
    const hair = hairRef.current;
    const arms = armRef.current;
    if (!body || !head || !hair || !arms) return;

    const beat = clock.current;
    const t = state.clock.elapsedTime;
    const energy = beat.running ? beat.energy : 0;
    const jump = smoothstep(0.82, 0.97, energy);
    const armEase = Math.min(1, delta * 4);
    const s = scratch;

    for (let i = 0; i < count; i += 1) {
      const p = people[i];
      const drive = Math.min(1.3, energy * p.amp);
      const beatPos = beat.beat * p.rate + p.phase;
      const f = beatPos - Math.floor(beatPos);
      // 1 on the beat, 0 half way to the next.
      const onBeat = (1 + Math.cos(f * Math.PI * 2)) / 2;
      // One full side-to-side every two beats.
      const swing = Math.sin(beatPos * Math.PI);

      let y = -0.05 * drive * onBeat;
      if (p.jumper && jump > 0) y += jump * 0.2 * p.amp * Math.abs(Math.sin(f * Math.PI));

      // The slow terms keep running with no music, so the room is never frozen.
      const sway = 0.04 * drive * swing + 0.012 * Math.sin(t * 0.7 + p.idle);
      const lean = 0.07 * drive * swing + 0.014 * Math.sin(t * 0.53 + p.idle * 1.7);
      const yaw = p.yaw + 0.1 * drive * Math.sin(beatPos * Math.PI + 1.3) + 0.1 * Math.sin(t * 0.21 + p.idle);

      const size = p.height / MODEL_HEIGHT;
      s.position.set(p.x + Math.cos(yaw) * sway, y, p.z - Math.sin(yaw) * sway);
      s.bodyEuler.set(0, yaw, lean);
      s.quaternion.setFromEuler(s.bodyEuler);
      s.scale.set(size * p.build, size, size * p.build);
      s.bodyMatrix.compose(s.position, s.quaternion, s.scale);
      body.setMatrixAt(i, s.bodyMatrix);

      // Head nods forward about the neck.
      const nod = 0.05 + 0.2 * drive * onBeat;
      s.local.makeRotationX(nod);
      s.local.setPosition(0, NECK_Y * (1 - Math.cos(nod)), -NECK_Y * Math.sin(nod));
      s.out.multiplyMatrices(s.bodyMatrix, s.local);
      head.setMatrixAt(i, s.out);
      hair.setMatrixAt(i, s.out);

      const wantUp = energy > p.armsAbove ? 1 : 0;
      armsUp[i] += (wantUp - armsUp[i]) * armEase;
      const up = armsUp[i];
      for (let a = 0; a < 2; a += 1) {
        const side = a === 0 ? -1 : 1;
        // Down: a small swing in time. Up: overhead and a little forward,
        // pumping on the beat.
        const restX = side * 0.16 * swing * (0.3 + drive);
        const upX = -2.75 + 0.32 * onBeat;
        s.armEuler.set(restX + (upX - restX) * up, 0, side * (0.07 + 0.2 * up));
        s.local.makeRotationFromEuler(s.armEuler);
        s.local.setPosition(side * SHOULDER_X, SHOULDER_Y, 0);
        arms.setMatrixAt(i * 2 + a, s.out.multiplyMatrices(s.bodyMatrix, s.local));
      }
    }

    body.instanceMatrix.needsUpdate = true;
    head.instanceMatrix.needsUpdate = true;
    hair.instanceMatrix.needsUpdate = true;
    arms.instanceMatrix.needsUpdate = true;
  });

  // Not frustum culled: the bounds three computes are for one person at the
  // origin, so from the cameras inside the room the whole crowd would vanish.
  return (
    <group>
      <instancedMesh ref={bodyRef} args={[geometry.body, crowdMaterial, count]} frustumCulled={false} castShadow receiveShadow dispose={null} />
      <instancedMesh ref={headRef} args={[geometry.head, crowdMaterial, count]} frustumCulled={false} castShadow dispose={null} />
      <instancedMesh ref={hairRef} args={[geometry.hair, crowdMaterial, count]} frustumCulled={false} dispose={null} />
      <instancedMesh ref={armRef} args={[geometry.arm, crowdMaterial, count * 2]} frustumCulled={false} dispose={null} />
    </group>
  );
}

/**
 * `count` is how many people the quality mode asks for; the floor's own
 * capacity caps it.
 */
export const Crowd = memo(function Crowd({
  layout,
  count,
  clock,
}: {
  layout: ClubLayout;
  count: number;
  clock: MutableRefObject<BeatClock>;
}) {
  const people = useMemo(() => placeCrowd(layout, count), [layout, count]);
  if (people.length === 0) return null;
  // Keyed on the head count: an instanced mesh cannot be resized in place.
  return <CrowdInstances key={people.length} people={people} clock={clock} />;
});

/**
 * Advances the beat clock once a frame. Mount it before anything that reads
 * the clock, so they all see the same beat.
 */
export function BeatClockTicker({ clock }: { clock: MutableRefObject<BeatClock> }) {
  useFrame((_, delta) => {
    advanceBeatClock(clock.current, delta, performance.now());
  });
  return null;
}
