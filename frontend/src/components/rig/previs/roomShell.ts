/**
 * The room a rig says it stands in: a dome, a round dance floor, a balcony,
 * risers and LED walls, built from the rig's `room_shell`. A shell read from a
 * room scan says other things (the room's own box, raised areas, overhead
 * lines); those are at the end of this file.
 *
 * Scenery only, as the shell's own definition says: nothing here stops a beam.
 * Every shape is made in code from the numbers in the shell, so there are no
 * model files and nothing is fetched.
 *
 * Angles are the shell's: degrees clockwise from upstage seen from above, so
 * 0 is -Z (the booth), 90 is +X and 180 is +Z.
 */
import * as THREE from 'three';
import type { RoomShell, RoomShellBox, RoomShellLine } from '../../../types';
import { box, merge, paint, place, strut, tubeY } from './geometryKit';
import { usableRoom } from './layout';
import type { KnownRoom, TrussRow } from './layout';

type Dome = NonNullable<RoomShell['dome']>;
type Disc = NonNullable<RoomShell['dance_floor']>;
type Balcony = NonNullable<RoomShell['balcony']>;

const DOME = '#33353e';
const DOME_RIB = '#4a4d59';
const DOME_RIM = '#5d6170';
const SOFFIT = '#2a2b31';
const DISC_A = '#565966';
const DISC_TRIM = '#7b808b';
const BALCONY_DECK = '#3f414b';
const BALCONY_FASCIA = '#565a68';
const BALCONY_SOFFIT = '#2c2d34';
const RISER = '#3a3c45';
const RISER_TOP = '#4b4e59';
const LED_FRAME = '#15161a';
/** An LED wall showing nothing: a dark panel with a little of its own light. */
export const LED_IDLE = '#16224a';

const DEG = Math.PI / 180;
const finite = (...values: unknown[]) => values.every((value) => typeof value === 'number' && Number.isFinite(value));

/** A point on the plan at `deg` clockwise from upstage: [x, z]. */
export function ringPoint(centerX: number, centerZ: number, radius: number, deg: number): [number, number] {
  return [centerX + radius * Math.sin(deg * DEG), centerZ - radius * Math.cos(deg * DEG)];
}

/** Radius of the sphere a dome is a cap of. */
function domeSphere(dome: Dome): number {
  const rise = Math.max(1e-3, dome.apex_height - dome.rim_height);
  return (dome.radius * dome.radius + rise * rise) / (2 * rise);
}

/** Height of the dome's surface this far out from its centre line. */
export function domeHeightAt(dome: Dome, distance: number): number {
  const sphere = domeSphere(dome);
  const reach = Math.min(Math.abs(distance), dome.radius);
  return dome.apex_height - (sphere - Math.sqrt(sphere * sphere - reach * reach));
}

/** True for a point inside the room and under the dome's surface: a camera there is indoors. */
export function underDome(dome: Dome, x: number, y: number, z: number): boolean {
  const distance = Math.hypot(x - dome.center_x, z - dome.center_z);
  return distance <= dome.radius && y < domeHeightAt(dome, distance);
}

export function usableDome(dome: RoomShell['dome']): dome is Dome {
  return Boolean(dome) && finite(dome!.radius, dome!.center_x, dome!.center_z, dome!.rim_height, dome!.apex_height)
    && dome!.radius > 0 && dome!.apex_height > dome!.rim_height;
}

/** The dome: a spherical cap with ribs to its apex and a ring at its rim. */
export function buildDome(dome: Dome, ribs = 16): THREE.BufferGeometry {
  const sphere = domeSphere(dome);
  const halfAngle = Math.asin(Math.min(1, dome.radius / sphere));
  const cap = new THREE.SphereGeometry(sphere, 48, 8, 0, Math.PI * 2, 0, halfAngle);
  const parts: THREE.BufferGeometry[] = [
    paint(place(cap, [dome.center_x, dome.apex_height - sphere, dome.center_z]), DOME),
    paint(
      place(tubeY(dome.radius, dome.radius - 0.14, 0.16, 48), [dome.center_x, dome.rim_height, dome.center_z]),
      DOME_RIM,
    ),
  ];
  // Ribs just under the surface, so a dark dome still shows its curve.
  const steps = 6;
  for (let rib = 0; rib < ribs; rib += 1) {
    const deg = (rib * 360) / ribs;
    for (let step = 0; step < steps; step += 1) {
      const r0 = (dome.radius * step) / steps;
      const r1 = (dome.radius * (step + 1)) / steps;
      const [x0, z0] = ringPoint(dome.center_x, dome.center_z, r0, deg);
      const [x1, z1] = ringPoint(dome.center_x, dome.center_z, r1, deg);
      parts.push(paint(
        strut([x0, domeHeightAt(dome, r0) - 0.04, z0], [x1, domeHeightAt(dome, r1) - 0.04, z1], 0.03, 5),
        DOME_RIB,
      ));
    }
  }
  return merge(parts);
}

/**
 * The flat ceiling between the dome's rim and the walls: a rectangle with the
 * dome's circle cut out of it, at rim height. Null when the dome covers the room.
 */
export function buildDomeSurround(
  dome: Dome,
  walls: { xMin: number; xMax: number; zMin: number; zMax: number },
): THREE.BufferGeometry | null {
  const corner = Math.max(
    Math.hypot(walls.xMin - dome.center_x, walls.zMin - dome.center_z),
    Math.hypot(walls.xMax - dome.center_x, walls.zMax - dome.center_z),
  );
  if (!(corner > dome.radius)) return null;
  const outline = new THREE.Shape();
  outline.moveTo(walls.xMin, walls.zMin);
  outline.lineTo(walls.xMax, walls.zMin);
  outline.lineTo(walls.xMax, walls.zMax);
  outline.lineTo(walls.xMin, walls.zMax);
  outline.closePath();
  const hole = new THREE.Path();
  hole.absarc(dome.center_x, dome.center_z, dome.radius, 0, Math.PI * 2, true);
  outline.holes.push(hole);
  // Drawn in XY, laid flat: the shape's Y becomes the room's Z.
  const flat = new THREE.ShapeGeometry(outline, 48).rotateX(Math.PI / 2);
  return merge([paint(place(flat, [0, dome.rim_height, 0]), SOFFIT)]);
}

export function usableDisc(disc: RoomShell['dance_floor']): disc is Disc {
  return Boolean(disc) && finite(disc!.center_x, disc!.center_z, disc!.radius) && disc!.radius > 0;
}

/** The round dance floor, with a trim ring at its edge. */
export function buildDanceDisc(disc: Disc): THREE.BufferGeometry {
  return merge([
    paint(
      place(new THREE.CircleGeometry(disc.radius, 64).rotateX(-Math.PI / 2), [disc.center_x, 0.006, disc.center_z]),
      DISC_A,
    ),
    paint(
      place(tubeY(disc.radius + 0.06, disc.radius, 0.016, 64), [disc.center_x, 0.008, disc.center_z]),
      DISC_TRIM,
    ),
  ]);
}

export function usableBalcony(balcony: RoomShell['balcony']): balcony is Balcony {
  return Boolean(balcony)
    && finite(
      balcony!.center_x, balcony!.center_z, balcony!.inner_radius, balcony!.outer_radius,
      balcony!.soffit_height, balcony!.deck_height, balcony!.start_deg, balcony!.end_deg,
    )
    && balcony!.outer_radius > balcony!.inner_radius
    && balcony!.end_deg !== balcony!.start_deg;
}

/**
 * The balcony: a slab between its soffit and its deck over an arc of a ring,
 * with a fascia and an upstand along its inner edge and its two ends closed.
 */
export function buildBalcony(balcony: Balcony): THREE.BufferGeometry {
  const sweep = balcony.end_deg - balcony.start_deg;
  const steps = Math.max(2, Math.ceil(Math.abs(sweep) / 7.5));
  const upstand = balcony.deck_height + 0.95;
  const { center_x: cx, center_z: cz, inner_radius: ri, outer_radius: ro } = balcony;
  const low = balcony.soffit_height;
  const high = balcony.deck_height;

  const positions: number[] = [];
  const colors: number[] = [];
  const tint = new THREE.Color();
  const quad = (a: number[], b: number[], c: number[], d: number[], color: string) => {
    tint.set(color);
    for (const point of [a, b, c, a, c, d]) {
      positions.push(point[0], point[1], point[2]);
      colors.push(tint.r, tint.g, tint.b);
    }
  };
  const at = (radius: number, deg: number, y: number) => {
    const [x, z] = ringPoint(cx, cz, radius, deg);
    return [x, y, z];
  };

  for (let i = 0; i < steps; i += 1) {
    const d0 = balcony.start_deg + (sweep * i) / steps;
    const d1 = balcony.start_deg + (sweep * (i + 1)) / steps;
    quad(at(ri, d0, high), at(ro, d0, high), at(ro, d1, high), at(ri, d1, high), BALCONY_DECK);
    quad(at(ri, d0, low), at(ri, d1, low), at(ro, d1, low), at(ro, d0, low), BALCONY_SOFFIT);
    quad(at(ri, d0, low), at(ri, d0, upstand), at(ri, d1, upstand), at(ri, d1, low), BALCONY_FASCIA);
  }
  for (const deg of [balcony.start_deg, balcony.end_deg]) {
    quad(at(ri, deg, low), at(ro, deg, low), at(ro, deg, high), at(ri, deg, high), BALCONY_FASCIA);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  geometry.computeBoundingBox();
  return geometry;
}

export function usableBox(shape: RoomShellBox | null | undefined): shape is RoomShellBox {
  return Boolean(shape) && finite(shape!.center_x, shape!.center_z, shape!.width, shape!.depth, shape!.height)
    && shape!.width > 0 && shape!.depth > 0 && shape!.height > 0;
}

/** Risers and other solid boxes, merged. Null when there are none. */
export function buildRisers(shapes: RoomShellBox[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const shape of shapes) {
    const base = shape.base_height ?? 0;
    parts.push(
      paint(place(box(shape.width, shape.height, shape.depth), [shape.center_x, base + shape.height / 2, shape.center_z]), RISER),
      paint(
        place(box(shape.width + 0.04, 0.03, shape.depth + 0.04), [shape.center_x, base + shape.height + 0.015, shape.center_z]),
        RISER_TOP,
      ),
    );
  }
  return parts.length ? merge(parts) : null;
}

/** LED walls: a dark frame and, a little proud of it on both faces, the lit panel. */
export function buildLedWalls(shapes: RoomShellBox[]): { frames: THREE.BufferGeometry; panels: THREE.BufferGeometry } | null {
  const frames: THREE.BufferGeometry[] = [];
  const panels: THREE.BufferGeometry[] = [];
  for (const shape of shapes) {
    const y = (shape.base_height ?? 0) + shape.height / 2;
    frames.push(paint(place(box(shape.width + 0.1, shape.height + 0.1, shape.depth), [shape.center_x, y, shape.center_z]), LED_FRAME));
    // Its broad face is across whichever of X and Z it is wider in.
    const acrossX = shape.width >= shape.depth;
    const panel = acrossX
      ? box(shape.width, shape.height, shape.depth + 0.02)
      : box(shape.width + 0.02, shape.height, shape.depth);
    panels.push(paint(place(panel, [shape.center_x, y, shape.center_z]), LED_IDLE));
  }
  return frames.length ? { frames: merge(frames), panels: merge(panels) } : null;
}

/**
 * Whether the shell's DJ booth is the one the view already builds from the
 * stage size, desk, decks and DJ included. When it is, drawing the shell's
 * plain box as well would put two booths in one place.
 */
export function boothAlreadyDrawn(
  shellBooth: RoomShellBox,
  drawn: { width: number; fasciaZ: number; backZ: number },
  tolerance = 0.35,
): boolean {
  const front = shellBooth.center_z + shellBooth.depth / 2;
  const back = shellBooth.center_z - shellBooth.depth / 2;
  return Math.abs(shellBooth.center_x) <= tolerance
    && Math.abs(front - drawn.fasciaZ) <= tolerance
    && Math.abs(back - drawn.backZ) <= tolerance
    && Math.abs(shellBooth.width - drawn.width) <= tolerance * 2;
}

// ---------------------------------------------------------------------------
// A scanned room (docs/ROOM_SCAN.md): its own box, its raised areas and the
// trusses or bars found overhead. All of it is a suggestion.
// ---------------------------------------------------------------------------

/** A truss or bar a scan found, drawn as a plain bar: nobody has said what it is. */
const SCAN_LINE = '#737a87';

/**
 * The room's own box, when the shell was read from a scan and says one. A demo
 * preset's shell has none: its room is still worked out from the stage box.
 */
export function scannedRoom(shell: RoomShell | null | undefined): KnownRoom | null {
  if (!shell || shell.source !== 'scan') return null;
  const room = shell.room;
  if (!usableRoom(room)) return null;
  return { width: room.width, depth: room.depth, height: room.height };
}

/** The raised areas a scan found that can be drawn: stage, risers, booth. */
export function scanRisers(shell: RoomShell | null | undefined): RoomShellBox[] {
  return (shell?.risers ?? []).filter(usableBox);
}

export function usableLine(line: RoomShellLine | null | undefined): line is RoomShellLine {
  return Boolean(line) && finite(line!.x1, line!.z1, line!.x2, line!.z2, line!.height)
    && line!.height > 0
    && Math.hypot(line!.x2 - line!.x1, line!.z2 - line!.z1) > 0.2;
}

/** Whether a line runs across the room (along X) rather than up and down it. */
function runsAcross(line: RoomShellLine): boolean {
  return Math.abs(line.x2 - line.x1) >= Math.abs(line.z2 - line.z1);
}

/**
 * Whether the truss the view already hangs over a row of fixtures is this
 * line. Once a scan's suggestion is applied the fixtures hang under the line
 * it found, and the view builds a truss over them: drawing the scan's bar as
 * well would put two trusses in one place.
 */
export function lineAlreadyDrawn(line: RoomShellLine, rows: TrussRow[], tolerance = 0.6): boolean {
  if (!runsAcross(line)) return false;
  const xMin = Math.min(line.x1, line.x2);
  const xMax = Math.max(line.x1, line.x2);
  const z = (line.z1 + line.z2) / 2;
  return rows.some((row) =>
    Math.abs(row.z - z) <= tolerance
    && row.xMin <= xMax && row.xMax >= xMin
    // The chord is above the fixtures, which hang at the line's underside.
    && row.chordY >= line.height - 0.3 && row.chordY <= line.height + 1.5);
}

/** The overhead lines a scan found, as plain bars at their own height. Null when there are none. */
export function buildOverheadLines(lines: RoomShellLine[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const line of lines) {
    const length = Math.hypot(line.x2 - line.x1, line.z2 - line.z1);
    const across = Math.min(1.2, Math.max(0.05, typeof line.across === 'number' && finite(line.across) ? line.across : 0.3));
    const top = typeof line.top === 'number' && finite(line.top) && line.top > line.height ? line.top : line.height + 0.3;
    const thickness = Math.max(0.05, top - line.height);
    const centre: [number, number, number] = [
      (line.x1 + line.x2) / 2, line.height + thickness / 2, (line.z1 + line.z2) / 2,
    ];
    const bar = runsAcross(line) ? box(length, thickness, across) : box(across, thickness, length);
    parts.push(paint(place(bar, centre), SCAN_LINE));
  }
  return parts.length ? merge(parts) : null;
}
