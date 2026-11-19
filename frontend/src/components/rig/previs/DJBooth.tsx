/**
 * The DJ booth: a low riser against the upstage wall, the desk at its front
 * edge with two decks and a mixer, the DJ behind it, and a speaker stack
 * either side.
 *
 * Everything that does not move is merged into two geometries, one solid and
 * one for the parts that light up. The DJ is two more, so the head can nod.
 */
import { memo, useEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { box, capsule, cylX, cylY, merge, paint, place, tubeY } from './geometryKit';
import type { Vec3 } from './geometryKit';
import type { BeatClock } from './beatClock';
import type { ClubLayout } from './layout';
import { glowMaterial, mattMaterial } from './materials';

const CASE = '#2c2e35';
const DESK = '#4a4d57';
const FASCIA = '#3a3c45';
const SLAT = '#585b67';
const RISER = '#34363d';
const GRILLE = '#16171a';
const CONE = '#5a5e69';
const KNOB = '#a3a8b0';

const DECK_SPACING = 0.44;
/** Height of the DJ's neck above their feet: the head nods about it. */
const NECK_Y = 1.49;

/** Ring facing +Z: the surround of a speaker cone. */
function coneRing(radius: number): THREE.BufferGeometry {
  return tubeY(radius, radius * 0.84, 0.012, 22).rotateX(Math.PI / 2);
}

function buildSpeakerStack(x: number, z: number, width: number, depth: number): THREE.BufferGeometry[] {
  const front = z + depth / 2;
  const parts: THREE.BufferGeometry[] = [];
  // Two subs.
  for (let i = 0; i < 2; i += 1) {
    const y = 0.29 + i * 0.58;
    parts.push(
      paint(place(box(width, 0.575, depth), [x, y, z]), CASE),
      paint(place(box(width - 0.1, 0.475, 0.012), [x, y, front + 0.004]), GRILLE),
      paint(place(coneRing(0.2), [x, y, front + 0.014]), CONE),
    );
  }
  // Mid/high box on top.
  const topY = 1.16 + 0.46;
  const topFront = front - 0.12;
  parts.push(
    paint(place(box(width * 0.66, 0.92, depth * 0.62), [x, topY, topFront - depth * 0.31]), CASE),
    paint(place(box(width * 0.66 - 0.08, 0.84, 0.012), [x, topY, topFront + 0.004]), GRILLE),
    paint(place(box(width * 0.4, 0.13, 0.014), [x, topY + 0.26, topFront + 0.012]), CONE),
    paint(place(coneRing(0.16), [x, topY - 0.14, topFront + 0.014]), CONE),
  );
  return parts;
}

function buildBooth(layout: ClubLayout): { solid: THREE.BufferGeometry; glow: THREE.BufferGeometry } {
  const { booth, backZ, speakers } = layout;
  const W = booth.width;
  const fz = booth.fasciaZ;
  const top = booth.deskTopY;
  const rh = booth.riserHeight;
  const dd = booth.deskDepth;
  const deskZ = fz - dd / 2;

  const solid: THREE.BufferGeometry[] = [
    paint(place(box(W + 0.3, rh, fz - backZ), [0, rh / 2, (fz + backZ) / 2]), RISER),
    paint(place(box(W, top, 0.05), [0, top / 2, fz - 0.025]), FASCIA),
    paint(place(box(W + 0.04, 0.045, dd + 0.04), [0, top - 0.0225, deskZ]), DESK),
    paint(place(box(0.05, top - rh, dd), [-(W / 2 - 0.025), rh + (top - rh) / 2, deskZ]), FASCIA),
    paint(place(box(0.05, top - rh, dd), [W / 2 - 0.025, rh + (top - rh) / 2, deskZ]), FASCIA),
  ];
  // Vertical slats down the booth front.
  const slats = Math.max(4, Math.round(W / 0.3));
  for (let i = 0; i <= slats; i += 1) {
    const x = -W / 2 + 0.06 + ((W - 0.12) * i) / slats;
    solid.push(paint(place(box(0.05, top - 0.14, 0.016), [x, (top - 0.14) / 2 + 0.03, fz + 0.008]), SLAT));
  }

  const glow: THREE.BufferGeometry[] = [];

  // Two decks. The jog wheel is nearest the DJ and the screen tilts back
  // toward them.
  for (const side of [-1, 1]) {
    const x = side * DECK_SPACING;
    solid.push(
      paint(place(box(0.32, 0.085, 0.4), [x, top + 0.0425, deskZ]), CASE),
      paint(place(cylY(0.098, 0.098, 0.016, 28), [x, top + 0.093, deskZ - 0.075]), GRILLE),
      paint(place(cylY(0.07, 0.07, 0.004, 24), [x, top + 0.103, deskZ - 0.075]), CONE),
      paint(place(box(0.21, 0.012, 0.1), [x, top + 0.112, deskZ + 0.125], [-0.5, 0, 0]), CASE),
    );
    glow.push(
      paint(place(tubeY(0.106, 0.099, 0.005, 28), [x, top + 0.088, deskZ - 0.075]), '#b9cdf5'),
      paint(place(box(0.18, 0.002, 0.078), [x, top + 0.12, deskZ + 0.121], [-0.5, 0, 0]), '#2f78c8'),
      paint(place(cylY(0.013, 0.013, 0.004, 12), [x - 0.11, top + 0.088, deskZ - 0.165]), '#d8701c'),
      paint(place(cylY(0.013, 0.013, 0.004, 12), [x - 0.075, top + 0.088, deskZ - 0.165]), '#2fbd5c'),
    );
  }

  // Mixer between them.
  solid.push(paint(place(box(0.32, 0.08, 0.4), [0, top + 0.04, deskZ]), '#191a1f'));
  for (let c = 0; c < 4; c += 1) {
    const x = -0.105 + c * 0.07;
    for (let r = 0; r < 3; r += 1) {
      solid.push(paint(place(cylY(0.009, 0.009, 0.016, 8), [x, top + 0.088, deskZ + 0.15 - r * 0.055]), KNOB));
    }
    solid.push(paint(place(box(0.012, 0.012, 0.03), [x, top + 0.086, deskZ - 0.07 - (c % 2) * 0.03]), '#d5d8dd'));
  }
  solid.push(paint(place(box(0.03, 0.012, 0.012), [0.02, top + 0.086, deskZ - 0.165]), '#d5d8dd'));
  // Level meters.
  for (const side of [-1, 1]) {
    for (let i = 0; i < 7; i += 1) {
      const color = i < 4 ? '#2fbd5c' : i < 6 ? '#d8a31c' : '#d83a2a';
      glow.push(paint(place(box(0.012, 0.003, 0.012), [side * 0.014 + 0.14, top + 0.082, deskZ - 0.02 + i * 0.019]), color));
    }
  }

  // Laptop, open toward the DJ.
  const laptopX = Math.min(1.05, W / 2 - 0.5);
  if (laptopX > DECK_SPACING + 0.4) {
    solid.push(
      paint(place(box(0.33, 0.014, 0.23), [laptopX, top + 0.007, deskZ - 0.02]), '#3b3e46'),
      paint(place(box(0.33, 0.21, 0.008), [laptopX, top + 0.115, deskZ + 0.12], [0.26, 0, 0]), '#3b3e46'),
    );
    glow.push(paint(place(box(0.3, 0.18, 0.002), [laptopX, top + 0.115, deskZ + 0.114], [0.26, 0, 0]), '#3d5a86'));
  }

  // Booth monitors on the ends of the desk, turned in toward the DJ.
  const monitorX = W / 2 - 0.42;
  if (monitorX > laptopX + 0.45) {
    for (const side of [-1, 1]) {
      const turn = side * 0.55;
      const parts = [
        paint(place(box(0.3, 0.46, 0.28), [0, 0.23, 0]), CASE),
        paint(place(box(0.24, 0.4, 0.012), [0, 0.23, -0.144]), GRILLE),
        paint(place(coneRing(0.085), [0, 0.17, -0.152]), CONE),
      ];
      for (const part of parts) {
        solid.push(place(part, [side * monitorX, top, deskZ + 0.02], [0, turn, 0]));
      }
    }
  }

  if (speakers.present) {
    solid.push(
      ...buildSpeakerStack(-speakers.x, speakers.z, speakers.width, speakers.depth),
      ...buildSpeakerStack(speakers.x, speakers.z, speakers.width, speakers.depth),
    );
  }

  return { solid: merge(solid), glow: merge(glow) };
}

/**
 * The DJ, standing with feet at the origin and facing +Z. `leftHand` and
 * `rightHand` are where the hands rest, in the same space.
 */
function buildDJ(leftHand: Vec3, rightHand: Vec3): { body: THREE.BufferGeometry; head: THREE.BufferGeometry } {
  const TROUSERS = '#23252c';
  const SHIRT = '#8f939c';
  const SKIN = '#b98a6c';
  const SHOE = '#0d0d10';

  const body: THREE.BufferGeometry[] = [];
  for (const side of [-1, 1]) {
    body.push(
      paint(capsule([side * 0.09, 0.1, 0], [side * 0.09, 0.84, 0], 0.078), TROUSERS),
      paint(place(box(0.1, 0.07, 0.25), [side * 0.09, 0.035, 0.04]), SHOE),
    );
  }
  const torso = cylY(0.2, 0.165, 0.58, 12);
  torso.scale(1, 1, 0.62);
  body.push(
    paint(place(torso, [0, 1.13, 0]), SHIRT),
    paint(capsule([-0.19, 1.39, 0], [0.19, 1.39, 0], 0.075), SHIRT),
    paint(place(cylY(0.05, 0.055, 0.1, 10), [0, 1.47, 0]), SKIN),
  );
  // Arms reaching forward to the decks: shoulder, a dropped elbow, the hand.
  const arms: Array<{ shoulder: Vec3; hand: Vec3 }> = [
    { shoulder: [-0.23, 1.38, 0.01], hand: leftHand },
    { shoulder: [0.23, 1.38, 0.01], hand: rightHand },
  ];
  for (const { shoulder, hand } of arms) {
    const elbow: Vec3 = [
      shoulder[0] + (hand[0] - shoulder[0]) * 0.4 + Math.sign(shoulder[0]) * 0.06,
      shoulder[1] + (hand[1] - shoulder[1]) * 0.62,
      shoulder[2] + (hand[2] - shoulder[2]) * 0.38,
    ];
    body.push(
      paint(capsule(shoulder, elbow, 0.048), SHIRT),
      paint(capsule(elbow, hand, 0.04), SKIN),
      paint(place(new THREE.SphereGeometry(0.048, 8, 6), hand), SKIN),
    );
  }

  // Head, modelled about the neck so it can nod.
  const skull = new THREE.SphereGeometry(0.102, 14, 10);
  skull.scale(1, 1.14, 1);
  const hair = new THREE.SphereGeometry(0.108, 14, 6, 0, Math.PI * 2, 0, Math.PI * 0.42);
  const band = new THREE.TorusGeometry(0.116, 0.013, 6, 16, Math.PI);
  const head = merge([
    paint(place(skull, [0, 0.125, 0]), SKIN),
    paint(place(hair, [0, 0.14, -0.012], [-0.55, 0, 0]), '#1c1512'),
    paint(place(band, [0, 0.13, 0]), '#101013'),
    paint(place(cylX(0.045, 0.036, 14), [-0.118, 0.12, 0]), '#101013'),
    paint(place(cylX(0.045, 0.036, 14), [0.118, 0.12, 0]), '#101013'),
  ]);

  return { body: merge(body), head };
}

export const DJBooth = memo(function DJBooth({
  layout,
  clock,
}: {
  layout: ClubLayout;
  clock: MutableRefObject<BeatClock>;
}) {
  const djRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Mesh>(null);

  const built = useMemo(() => {
    const { booth } = layout;
    const deskZ = booth.fasciaZ - booth.deskDepth / 2;
    // Hands, relative to the DJ's feet: left on the left jog wheel, right on
    // the mixer.
    const handY = booth.deskTopY - booth.riserHeight + 0.125;
    const reachZ = deskZ - booth.djZ;
    const leftHand: Vec3 = [-DECK_SPACING + 0.02, handY, reachZ - 0.075];
    const rightHand: Vec3 = [0.1, handY, reachZ - 0.1];
    return { booth: buildBooth(layout), dj: buildDJ(leftHand, rightHand) };
  }, [layout]);

  useEffect(() => () => {
    built.booth.solid.dispose();
    built.booth.glow.dispose();
    built.dj.body.dispose();
    built.dj.head.dispose();
  }, [built]);

  useFrame(({ clock: three }) => {
    const beat = clock.current;
    const t = three.elapsedTime;
    const phase = beat.beat - Math.floor(beat.beat);
    // 1 on the beat, 0 half way to the next.
    const onBeat = (1 + Math.cos(phase * Math.PI * 2)) / 2;
    const drive = beat.running ? 0.35 + beat.energy * 0.65 : 0;
    if (djRef.current) {
      djRef.current.position.y = layout.booth.riserHeight - 0.022 * onBeat * drive;
    }
    if (headRef.current) {
      headRef.current.rotation.x = 0.06 + 0.2 * onBeat * drive;
      // With nothing playing the DJ just looks about.
      headRef.current.rotation.y = Math.sin(t * 0.45) * 0.22 * (1 - drive);
    }
  });

  return (
    <group>
      <mesh geometry={built.booth.solid} material={mattMaterial} castShadow receiveShadow dispose={null} />
      <mesh geometry={built.booth.glow} material={glowMaterial} dispose={null} />
      <group ref={djRef} position={[0, layout.booth.riserHeight, layout.booth.djZ]}>
        <mesh geometry={built.dj.body} material={mattMaterial} castShadow dispose={null} />
        <mesh ref={headRef} geometry={built.dj.head} material={mattMaterial} position={[0, NECK_Y, 0]} castShadow dispose={null} />
      </group>
    </group>
  );
});
