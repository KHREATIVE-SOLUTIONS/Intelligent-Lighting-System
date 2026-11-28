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
import type { RoomShell, RoomShellBox, RoomShellLine, RoomShellRing } from '../../../types';
import { box, cylZ, merge, paint, place, strut, tubeY } from './geometryKit';
import { usableRoom } from './layout';
import type { Hanger, KnownRoom, TrussRow } from './layout';
import { outlineBox, outlineSpansX, outlineSpansZ, spansInBoth } from './outline';
import { boxHeading } from './raisedArea';
import type { OutlinePoint } from './outline';
import { finite, scanRings, usableLine } from './roomShellData';

// The shell checks with no three.js in them live in roomShellData.ts, so the
// 2D plan can read them without loading three.js.
export { scanRings, scanRisers, usableBox, usableLine, usableRing } from './roomShellData';

// The outline's own maths has no three.js in it and lives in outline.ts, where
// the layout, the beams and the drag can read it too.
export {
  insideOutline, onRoomSide, outlineArea, outlineWalls, roomOutline,
} from './outline';
export type { OutlinePoint, OutlineWall } from './outline';

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

/** Risers and other solid boxes, merged. Null when there are none. */
export function buildRisers(shapes: RoomShellBox[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const shape of shapes) {
    const base = shape.base_height ?? 0;
    // A raised area at a heading (slice 21). The box is made with its width along X, and a turn of `a`
    // about Y takes +X to (cos a, -sin a) on the plan, so a heading towards +Z is the turn the other
    // way: what `buildOverheadLines` does for a line. One with no heading is not turned at all.
    const heading = boxHeading(shape);
    const turn: [number, number, number] | undefined = heading === 0 ? undefined : [0, -(heading * Math.PI) / 180, 0];
    parts.push(
      paint(
        place(box(shape.width, shape.height, shape.depth), [shape.center_x, base + shape.height / 2, shape.center_z], turn),
        RISER,
      ),
      paint(
        place(
          box(shape.width + 0.04, 0.03, shape.depth + 0.04),
          [shape.center_x, base + shape.height + 0.015, shape.center_z],
          turn,
        ),
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

/** A line within this of straight across the room is one the view's own truss can stand in for. */
const ACROSS_WITHIN_DEG = 2;

/**
 * Whether a line runs straight across the room (along X), read from its two
 * ends: a shell stored before headings were written says nothing else.
 */
export function runsAcross(line: RoomShellLine): boolean {
  return Math.abs(line.z2 - line.z1) <= Math.abs(line.x2 - line.x1) * Math.tan(ACROSS_WITHIN_DEG * DEG);
}

/**
 * The trusses of a scanned room that the view's own truss cannot stand in
 * for: lines that do not run straight across the room, and rings. Fixtures
 * hang from these as the room has them (`buildVenue`'s `hangers`).
 */
export function scanHangers(shell: RoomShell | null | undefined): Hanger[] {
  if (!shell || shell.source !== 'scan') return [];
  const hangers: Hanger[] = [];
  for (const line of (shell.truss_lines ?? []).filter(usableLine)) {
    if (runsAcross(line)) continue;
    hangers.push({ kind: 'line', x1: line.x1, z1: line.z1, x2: line.x2, z2: line.z2, height: line.height });
  }
  for (const ring of scanRings(shell)) {
    hangers.push({ kind: 'ring', centerX: ring.center_x, centerZ: ring.center_z, radius: ring.radius, height: ring.height });
  }
  return hangers;
}

/**
 * Whether the truss the view already hangs over a row of fixtures is this
 * line. Once a scan's suggestion is applied the fixtures hang under the line
 * it found, and the view builds a truss over them: drawing the scan's bar as
 * well would put two trusses in one place. The view's truss only runs
 * straight across the room, so a line at any other heading is never it.
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

/** How wide and how thick to draw a scanned truss: what the scan measured, or 0.3 m of each. */
function barSection(shape: { height: number; top?: number; across?: number }): { across: number; thickness: number } {
  const across = Math.min(1.2, Math.max(0.05, typeof shape.across === 'number' && finite(shape.across) ? shape.across : 0.3));
  const top = typeof shape.top === 'number' && finite(shape.top) && shape.top > shape.height ? shape.top : shape.height + 0.3;
  return { across, thickness: Math.max(0.05, top - shape.height) };
}

/**
 * The overhead lines a scan found, as plain bars at their own height, each
 * turned to the heading it runs at on the plan. Null when there are none.
 */
export function buildOverheadLines(lines: RoomShellLine[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const line of lines) {
    const length = Math.hypot(line.x2 - line.x1, line.z2 - line.z1);
    const { across, thickness } = barSection(line);
    const centre: [number, number, number] = [
      (line.x1 + line.x2) / 2, line.height + thickness / 2, (line.z1 + line.z2) / 2,
    ];
    // The bar is made along X. A turn of `a` about Y takes +X to (cos a, -sin a)
    // on the plan, so a line heading towards +Z needs the turn the other way.
    const turn = -Math.atan2(line.z2 - line.z1, line.x2 - line.x1);
    parts.push(paint(place(box(length, thickness, across), centre, [0, turn, 0]), SCAN_LINE));
  }
  return parts.length ? merge(parts) : null;
}

/** The rings of truss a scan found, as plain flat rings at their own height. Null when there are none. */
export function buildTrussRings(rings: RoomShellRing[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const ring of rings) {
    const { across, thickness } = barSection(ring);
    const half = Math.min(across / 2, ring.radius * 0.9);
    const segments = Math.max(32, Math.min(96, Math.round(ring.radius * 16)));
    parts.push(paint(
      place(
        tubeY(ring.radius + half, ring.radius - half, thickness, segments),
        [ring.center_x, ring.height + thickness / 2, ring.center_z],
      ),
      SCAN_LINE,
    ));
  }
  return parts.length ? merge(parts) : null;
}

// ---------------------------------------------------------------------------
// A scanned room that is not a box: its floor outline, and the walls along it.
// ---------------------------------------------------------------------------

/** The floor or the ceiling of an outlined room: the outline itself, flat, at height `y`. */
export function buildOutlineFlat(outline: OutlinePoint[], y: number, color: THREE.ColorRepresentation): THREE.BufferGeometry {
  const shape = new THREE.Shape();
  outline.forEach((point, index) => {
    if (index === 0) shape.moveTo(point.x, point.z);
    else shape.lineTo(point.x, point.z);
  });
  shape.closePath();
  // Drawn in XY, laid flat: the shape's Y becomes the room's Z.
  const flat = new THREE.ShapeGeometry(shape).rotateX(Math.PI / 2);
  return merge([paint(place(flat, [0, y, 0]), color)]);
}

/** The club room's ceiling beam and duct colours (ClubRoom.tsx), so an outlined room's ceiling matches a box one's. */
const CEILING_BEAM = '#3a3c44';
const CEILING_DUCT = '#666a75';
const CEILING_BEAM_DEPTH = 0.16;
const CEILING_DUCT_RADIUS = 0.15;

/** Where the ceiling beams of an outlined room run: across the room at `z`, from `xMin` to `xMax`. */
export function outlineBeamRuns(outline: OutlinePoint[]): Array<{ z: number; xMin: number; xMax: number }> {
  const { zMin, zMax } = outlineBox(outline);
  const length = zMax - zMin;
  const half = CEILING_BEAM_DEPTH / 2;
  const count = Math.max(2, Math.round(length / 2.4));
  const runs: Array<{ z: number; xMin: number; xMax: number }> = [];
  for (let i = 0; i <= count; i += 1) {
    // The first and the last lie along the end walls, just inside them.
    const z = Math.min(zMax - half - 0.01, Math.max(zMin + half + 0.01, zMin + (length * i) / count));
    // Each beam stops where either of its edges meets a wall, so it ends at
    // the notch of an L and is cut short by a wall that runs at an angle.
    for (const [xMin, xMax] of spansInBoth(outlineSpansX(outline, z - half), outlineSpansX(outline, z + half))) {
      if (xMax - xMin > 0.05) runs.push({ z, xMin, xMax });
    }
  }
  return runs;
}

/** Where the air duct of an outlined room runs: down one side at `x`, from `zMin` to `zMax`. */
export function outlineDuctRuns(outline: OutlinePoint[]): Array<{ x: number; zMin: number; zMax: number }> {
  const box = outlineBox(outline);
  // Where the box room hangs it: a sixth of the way in from the stage right wall.
  const x = box.xMin + (box.xMax - box.xMin) * 0.17;
  const spans = spansInBoth(
    outlineSpansZ(outline, x - CEILING_DUCT_RADIUS),
    outlineSpansZ(outline, x + CEILING_DUCT_RADIUS),
  );
  const runs: Array<{ x: number; zMin: number; zMax: number }> = [];
  for (const [from, to] of spans) {
    // It stops short of the walls at both ends, as the box room's does.
    const trim = (to - from) * 0.07;
    if (to - from - trim * 2 > 0.3) runs.push({ x, zMin: from + trim, zMax: to - trim });
  }
  return runs;
}

/**
 * The beams and the air duct under the ceiling of an outlined room, as the box
 * room has them, kept inside the outline. Hangs from height `y`. Null for a
 * room with space for neither.
 */
export function buildOutlineCeilingDressing(outline: OutlinePoint[], y: number): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = [];
  for (const run of outlineBeamRuns(outline)) {
    parts.push(paint(
      place(box(run.xMax - run.xMin, 0.2, CEILING_BEAM_DEPTH), [(run.xMin + run.xMax) / 2, y - 0.1, run.z]),
      CEILING_BEAM,
    ));
  }
  for (const run of outlineDuctRuns(outline)) {
    parts.push(paint(
      place(cylZ(CEILING_DUCT_RADIUS, run.zMax - run.zMin, 14), [run.x, y - 0.18, (run.zMin + run.zMax) / 2]),
      CEILING_DUCT,
    ));
  }
  return parts.length ? merge(parts) : null;
}
