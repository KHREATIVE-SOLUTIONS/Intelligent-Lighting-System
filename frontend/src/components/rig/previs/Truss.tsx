/**
 * Box truss over each line of hung fixtures.
 *
 * Four chords with zigzag lacing on all four faces, the way aluminium box
 * truss is actually built. Every run in the rig is merged into one geometry,
 * so the whole lot is a single draw call.
 */
import { memo, useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { box, cylX, merge, paint, place, strut } from './geometryKit';
import type { Vec3 } from './geometryKit';
import { TRUSS_CHORD_RADIUS, TRUSS_SECTION } from './layout';
import type { TrussRow } from './layout';
import { bodyMaterial } from './materials';

const ALUMINIUM = '#b1b6be';
const LACING = '#9ba0a8';
const HOIST = '#2a2c31';
const BAY = 0.5;

function buildTruss(rows: TrussRow[], hangTo: number | undefined): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];

  for (const row of rows) {
    const length = row.xMax - row.xMin;
    if (!(length > 0.2)) continue;
    const centreX = (row.xMin + row.xMax) / 2;

    // The fixtures hang from the downstage bottom chord, so the box sits
    // upstage of the line they are on.
    const corners: Array<[number, number]> = [
      [row.chordY, row.z],
      [row.chordY, row.z - TRUSS_SECTION],
      [row.chordY + TRUSS_SECTION, row.z - TRUSS_SECTION],
      [row.chordY + TRUSS_SECTION, row.z],
    ];
    for (const [y, z] of corners) {
      parts.push(paint(place(cylX(TRUSS_CHORD_RADIUS, length, 10), [centreX, y, z]), ALUMINIUM));
    }

    // Lacing: one diagonal per bay on each face, alternating to make a zigzag.
    const bays = Math.max(1, Math.round(length / BAY));
    const bay = length / bays;
    for (let face = 0; face < 4; face += 1) {
      const [ay, az] = corners[face];
      const [by, bz] = corners[(face + 1) % 4];
      for (let i = 0; i < bays; i += 1) {
        const x0 = row.xMin + i * bay;
        const x1 = x0 + bay;
        const flip = (i + face) % 2 === 0;
        const from: Vec3 = flip ? [x0, ay, az] : [x0, by, bz];
        const to: Vec3 = flip ? [x1, by, bz] : [x1, ay, az];
        parts.push(paint(strut(from, to, 0.011, 5), LACING));
      }
    }

    // Square frames closing each end.
    for (const x of [row.xMin, row.xMax]) {
      for (let face = 0; face < 4; face += 1) {
        const [ay, az] = corners[face];
        const [by, bz] = corners[(face + 1) % 4];
        parts.push(paint(strut([x, ay, az], [x, by, bz], 0.014, 6), ALUMINIUM));
      }
    }

    // Hoists up to the ceiling, when there is a ceiling to hang from.
    if (hangTo !== undefined) {
      const top = row.chordY + TRUSS_SECTION + TRUSS_CHORD_RADIUS;
      const inset = Math.min(1.2, length * 0.2);
      const points = length > 8 ? [row.xMin + inset, centreX, row.xMax - inset] : [row.xMin + inset, row.xMax - inset];
      for (const x of points) {
        const z = row.z - TRUSS_SECTION / 2;
        parts.push(paint(place(box(0.14, 0.2, 0.14), [x, top + 0.1, z]), HOIST));
        if (hangTo > top + 0.2) {
          parts.push(paint(strut([x, top + 0.2, z], [x, hangTo, z], 0.008, 5), HOIST));
        }
      }
    }
  }

  return parts.length ? merge(parts) : null;
}

/**
 * `hangTo` is the ceiling height. Leave it out for a bare rig, where there is
 * no ceiling and hoist chains would end in mid-air.
 */
export const RigTruss = memo(function RigTruss({ rows, hangTo }: { rows: TrussRow[]; hangTo?: number }) {
  const geometry = useMemo(() => buildTruss(rows, hangTo), [rows, hangTo]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  if (!geometry) return null;
  return <mesh geometry={geometry} material={bodyMaterial} castShadow dispose={null} />;
});
