/**
 * The parts of a fixture model, as React components.
 *
 * `Fixture3D` re-renders every frame (it keeps beam intensity in state), so
 * these are memoised and take only props that stay the same from frame to
 * frame. Each is one or two meshes over shared geometry: `dispose={null}`
 * stops react-three-fiber freeing that geometry when one fixture unmounts.
 */
import { forwardRef, memo } from 'react';
import type { Ref } from 'react';
import * as THREE from 'three';
import { box, cylY, merge, paint, place } from './geometryKit';
import { getFixtureGeometry } from './fixtureGeometry';
import { FIXTURE_SPECS } from './fixtureSpecs';
import type { FixtureModelKind } from './fixtureSpecs';
import type { FixtureMount } from './layout';
import { bodyMaterial } from './materials';

// Unit-sized parts, stretched per fixture: a pipe and a block 1 m tall, and a
// wall arm 1 m long with its plate at the far end.
const unitPipe = paint(place(cylY(0.022, 0.022, 1, 10), [0, 0.5, 0]), '#8f949c');
const unitBlock = paint(place(box(1, 1, 1), [0, 0.5, 0]), '#1d1e22');
const unitArm = paint(place(box(1, 0.03, 0.03), [0.5, 0, 0]), '#8f949c');
const wallPlate = merge([
  paint(place(box(0.035, 0.16, 0.1), [-0.0175, -0.03, 0]), '#8f949c'),
]);
const poleFoot = merge([
  paint(place(cylY(0.16, 0.2, 0.03, 20), [0, 0.015, 0]), '#1d1e22'),
]);

/** Above this a floor fixture is on a pole rather than a block. */
const POLE_ABOVE = 0.5;

/**
 * Whatever holds the fixture up: its base or bracket, plus the pipe, wall arm
 * or plinth that reaches the truss, wall or floor.
 *
 * `bodyYaw` is the fixture's own rotation about the vertical. A wall arm has
 * to reach the wall whichever way the fixture is turned, so it is turned back.
 */
export const FixtureSupport = memo(function FixtureSupport({
  kind,
  mount,
  bodyYaw,
}: {
  kind: FixtureModelKind;
  mount: FixtureMount;
  bodyYaw: number;
}) {
  const geometry = getFixtureGeometry(kind);
  const spec = FIXTURE_SPECS[kind];
  const standing = mount.type === 'stand';

  return (
    <>
      <mesh
        geometry={standing ? geometry.supportStand : geometry.supportHang}
        material={bodyMaterial}
        castShadow
        dispose={null}
      />

      {mount.type === 'truss' && mount.drop > 0.01 && geometry.clampXs.map((x) => (
        <mesh
          key={`drop-${x}`}
          geometry={unitPipe}
          material={bodyMaterial}
          position={[x, spec.hangHeight, 0]}
          scale={[1, mount.drop, 1]}
          dispose={null}
        />
      ))}

      {mount.type === 'wall' && geometry.clampXs.map((x) => (
        <group
          key={`arm-${x}`}
          position={[x, spec.hangHeight, 0]}
          rotation={[0, Math.atan2(-mount.dirZ, mount.dirX) - bodyYaw, 0]}
        >
          <mesh geometry={unitArm} material={bodyMaterial} scale={[mount.reach, 1, 1]} dispose={null} />
          <mesh geometry={wallPlate} material={bodyMaterial} position={[mount.reach, 0, 0]} dispose={null} />
        </group>
      ))}

      {mount.type === 'stand' && mount.plinth > 0.02 && (
        mount.plinth > POLE_ABOVE ? (
          <group position={[0, -spec.standHeight - mount.plinth, 0]}>
            <mesh geometry={unitPipe} material={bodyMaterial} scale={[1, mount.plinth, 1]} dispose={null} />
            <mesh geometry={poleFoot} material={bodyMaterial} dispose={null} />
          </group>
        ) : (
          <mesh
            geometry={unitBlock}
            material={bodyMaterial}
            position={[0, -spec.standHeight - mount.plinth, 0]}
            scale={[0.42, mount.plinth, 0.42]}
            dispose={null}
          />
        )
      )}
    </>
  );
});

/**
 * The yoke arms of a moving head. Takes the pan: the caller turns this group
 * about Y by the same angle it gives the head.
 */
export const FixtureYoke = memo(forwardRef(function FixtureYoke(
  { kind, standing }: { kind: FixtureModelKind; standing: boolean },
  ref: Ref<THREE.Group>,
) {
  const geometry = getFixtureGeometry(kind);
  const yoke = standing ? geometry.yokeStand : geometry.yokeHang;
  if (!yoke) return null;
  return (
    <group ref={ref}>
      <mesh geometry={yoke} material={bodyMaterial} castShadow dispose={null} />
    </group>
  );
}));

/**
 * The head: housing plus the lit lens or LED cells.
 *
 * `lensRef` is the lit mesh. It has its own material so each fixture can glow
 * its own colour; the caller drives that material every frame.
 *
 * The lit face is on the -Y side, the side the caller's beam leaves from.
 * Which way that side faces is the caller's business: it turns this, the beam
 * and the spot light together, in one group, so they cannot point apart.
 */
export const FixtureHead = memo(function FixtureHead({
  kind,
  lensRef,
}: {
  kind: FixtureModelKind;
  lensRef: Ref<THREE.Mesh>;
}) {
  const geometry = getFixtureGeometry(kind);
  return (
    <>
      <mesh geometry={geometry.shell} material={bodyMaterial} castShadow dispose={null} />
      <mesh ref={lensRef} geometry={geometry.emitter} dispose={null}>
        <meshStandardMaterial color="#111" emissive="#000000" roughness={0.25} metalness={0} toneMapped={false} />
      </mesh>
    </>
  );
});
