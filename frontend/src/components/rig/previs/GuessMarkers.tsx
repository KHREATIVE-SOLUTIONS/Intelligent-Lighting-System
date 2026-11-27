/**
 * Marks the fixtures whose position is a guess.
 *
 * A patch sheet with no positions is laid out on a stage template, and every
 * fixture placed that way carries the tag `position_unconfirmed` until someone
 * taps where it really is (docs/FLASH_AND_TAP.md). A beam drawn from a guessed
 * position is drawn in the wrong place with full confidence, so the view says
 * which ones they are: an amber ring round the fixture, a marker above it and
 * a line down to the floor under it.
 *
 * All of them are one merged geometry and one unlit material: one draw call,
 * whatever the size of the rig, and no change to the light count.
 */
import { memo, useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { merge, paint, place, strut, tubeY } from './geometryKit';
import { glowMaterial } from './materials';

/** The amber the identify walkthrough draws a guess in. */
export const GUESS_COLOR = '#ffb74d';

const RING_RADIUS = 0.46;

export type GuessPoint = { x: number; y: number; z: number };

/** One geometry marking every guessed position. Null when there are none. */
export function buildGuessMarkers(points: GuessPoint[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const point of points) {
    if (![point.x, point.y, point.z].every(Number.isFinite)) continue;
    parts.push(
      // The ring round the fixture.
      paint(place(tubeY(RING_RADIUS, RING_RADIUS - 0.05, 0.03, 28), [point.x, point.y, point.z]), GUESS_COLOR),
      // A diamond above it, seen from the floor and from the top view alike.
      paint(place(new THREE.OctahedronGeometry(0.11), [point.x, point.y + 0.72, point.z]), GUESS_COLOR),
    );
    // A broken line down to the floor: where on the plan the guess puts it.
    const dash = 0.22;
    for (let top = point.y - 0.45; top > 0.05; top -= dash * 2) {
      const bottom = Math.max(0.02, top - dash);
      parts.push(paint(strut([point.x, top, point.z], [point.x, bottom, point.z], 0.012, 4), GUESS_COLOR));
    }
    // And a small ring on the floor where that line lands.
    parts.push(paint(place(tubeY(0.2, 0.16, 0.012, 20), [point.x, 0.02, point.z]), GUESS_COLOR));
  }
  return parts.length ? merge(parts) : null;
}

export const GuessMarkers = memo(function GuessMarkers({ points }: { points: GuessPoint[] }) {
  const geometry = useMemo(() => buildGuessMarkers(points), [points]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  if (!geometry) return null;
  // Not culled as one: the markers are spread over the whole rig.
  return <mesh geometry={geometry} material={glowMaterial} frustumCulled={false} dispose={null} />;
});
