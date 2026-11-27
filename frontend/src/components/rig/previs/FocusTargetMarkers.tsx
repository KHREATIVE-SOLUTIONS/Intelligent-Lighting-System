/**
 * The focus targets in the 3D view (docs/FOCUS_PRESETS.md, "In the app"): a
 * small marker at each point the focus presets aim at, its look saying who
 * can reach it, so it reads in colour and in shape alike:
 *
 * - all: every moving head reaches it. A cyan ball in a ring.
 * - some: some heads cannot. An orange turned cube in a ring.
 * - none: no head can. A red cross.
 * - idle: the rig has no moving heads to aim. A small grey ball.
 *
 * The audience line is drawn as a thin bar between its ends, its marker at the
 * middle. A target on the floor is lifted a little so it is not lost in it.
 *
 * One merged geometry and one unlit material per look: at most four draw
 * calls, whatever the number of targets. None of them is ever hit by a ray, so
 * a fixture drag and a click go through them as if they were not there.
 */
import { memo, useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { FocusMarker, MarkerStyle } from '../../../utils/focusPresets';
import { merge, paint, place, strut, tubeY } from './geometryKit';
import { glowMaterial } from './materials';

export const FOCUS_MARKER_COLORS: Record<MarkerStyle, string> = {
  all: '#4dd0e1',
  some: '#ff9800',
  none: '#ef5350',
  idle: '#9e9e9e',
};

export const FOCUS_MARKER_STYLES: MarkerStyle[] = ['all', 'some', 'none', 'idle'];

/** The lowest a marker is drawn: a point on the floor sits just above it. */
export const FOCUS_MARKER_MIN_Y = 0.1;

type V3 = [number, number, number];

function markerParts(marker: FocusMarker): THREE.BufferGeometry[] {
  const color = FOCUS_MARKER_COLORS[marker.style];
  const [x, rawY, z] = marker.at;
  const y = Math.max(FOCUS_MARKER_MIN_Y, rawY);
  const at: V3 = [x, y, z];
  const parts: THREE.BufferGeometry[] = [];
  if (marker.style === 'all') {
    parts.push(paint(place(new THREE.SphereGeometry(0.09, 12, 8), at), color));
  } else if (marker.style === 'some') {
    parts.push(paint(place(new THREE.BoxGeometry(0.13, 0.13, 0.13), at, [Math.PI / 4, Math.PI / 4, 0]), color));
  } else if (marker.style === 'none') {
    const r = 0.12;
    // Upright for the side cameras, and flat for the Top one, where an upright cross is edge-on.
    parts.push(
      paint(strut([x - r, y - r, z], [x + r, y + r, z], 0.02, 4), color),
      paint(strut([x - r, y + r, z], [x + r, y - r, z], 0.02, 4), color),
      paint(strut([x - r, y, z - r], [x + r, y, z + r], 0.02, 4), color),
      paint(strut([x - r, y, z + r], [x + r, y, z - r], 0.02, 4), color),
    );
  } else {
    parts.push(paint(place(new THREE.SphereGeometry(0.06, 10, 6), at), color));
  }
  if (marker.style === 'all' || marker.style === 'some') {
    parts.push(paint(place(tubeY(0.2, 0.17, 0.015, 24), at), color));
  }
  if (marker.line) {
    const [a, b] = marker.line;
    const lift = (p: V3): V3 => [p[0], Math.max(FOCUS_MARKER_MIN_Y, p[1]), p[2]];
    parts.push(paint(strut(lift(a), lift(b), 0.012, 4), color));
  }
  return parts;
}

/** One geometry per look, or null for a look no marker has. */
export function buildFocusMarkers(markers: FocusMarker[]): Record<MarkerStyle, THREE.BufferGeometry | null> {
  const out: Record<MarkerStyle, THREE.BufferGeometry | null> = { all: null, some: null, none: null, idle: null };
  for (const style of FOCUS_MARKER_STYLES) {
    const parts = markers
      .filter((m) => m.style === style && m.at.every(Number.isFinite))
      .flatMap(markerParts);
    out[style] = parts.length ? merge(parts) : null;
  }
  return out;
}

/** Takes no hits: a ray goes through a marker to whatever is behind it. */
const noRaycast = () => undefined;

export const FocusTargetMarkers = memo(function FocusTargetMarkers({ markers }: { markers: FocusMarker[] }) {
  const geometries = useMemo(() => buildFocusMarkers(markers), [markers]);
  useEffect(() => () => {
    FOCUS_MARKER_STYLES.forEach((style) => geometries[style]?.dispose());
  }, [geometries]);
  return (
    <group name="focus-targets">
      {FOCUS_MARKER_STYLES.map((style) => {
        const geometry = geometries[style];
        if (!geometry) return null;
        return (
          <mesh
            key={style}
            name={`focus-targets-${style}`}
            geometry={geometry}
            material={glowMaterial}
            raycast={noRaycast}
            frustumCulled={false}
            dispose={null}
          />
        );
      })}
    </group>
  );
});
