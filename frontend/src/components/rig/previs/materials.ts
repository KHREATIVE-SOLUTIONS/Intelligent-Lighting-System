/**
 * Materials shared by the previs models.
 *
 * Models carry their colours per vertex, so a handful of materials cover
 * everything. Keeping the set small matters more than it looks: three.js
 * recompiles every lit material each time the number of spot lights changes,
 * and that number changes whenever a fixture fades in or out.
 *
 * Metalness is kept low on purpose. With no environment map a metallic surface
 * has nothing to reflect and renders near-black, which is why the old fixture
 * boxes vanished whenever the rig was dark.
 */
import * as THREE from 'three';

/** Fixture housings, brackets and truss. */
export const bodyMaterial = new THREE.MeshStandardMaterial({
  vertexColors: true,
  metalness: 0.3,
  roughness: 0.52,
  side: THREE.DoubleSide,
});

/** Walls, floor, furniture, people's clothes: matt. */
export const mattMaterial = new THREE.MeshStandardMaterial({
  vertexColors: true,
  metalness: 0.04,
  roughness: 0.86,
  side: THREE.DoubleSide,
});

/** The dance floor: glossy enough to catch a highlight under the beams. */
export const glossMaterial = new THREE.MeshStandardMaterial({
  vertexColors: true,
  metalness: 0.35,
  roughness: 0.3,
  side: THREE.DoubleSide,
});

/**
 * Things that give off their own light: deck screens, meter LEDs, the edge of
 * the dance floor. Unlit, so it does not depend on the light count at all.
 */
export const glowMaterial = new THREE.MeshBasicMaterial({
  vertexColors: true,
  toneMapped: false,
});
