/**
 * A scanned room on the 2D layout view: what the rig's `room_shell` says, as
 * shapes on the plan. Walls (the box, or the floor outline of a room that is
 * not one), raised areas, truss lines at whatever heading they run and rings
 * of truss, each with the words for its label and tooltip. Also where a drag
 * or a palette drop is held to in that room, what the plan's own labels are
 * set against, and where the room's labels go so they stay readable.
 *
 * Numbers and words only: no React and no drawing. Coordinates are the rig's,
 * as the 3D view reads them: metres, origin at the centre of the floor, X
 * across, -Z upstage. Which shapes are fit to draw is decided by the same
 * rules the 3D view uses (previs/outline.ts, previs/roomShell.ts).
 * docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import { lineRunText } from '../../utils/roomScan';
import { holdNearOutline, outlineBox, roomOutline, usableRoom } from './previs/outline';
import { scanRings, scanRisers, usableLine } from './previs/roomShell';

export type PlanPoint = { x: number; z: number };
export type PlanBounds = { xMin: number; xMax: number; zMin: number; zMax: number };

export interface PlanWalls {
  /** Corners in order, the last joined back to the first. */
  points: PlanPoint[];
  /** True when these are the scan's floor outline, false for the room's box. */
  outlined: boolean;
  tooltip: string;
}

export interface PlanRaised {
  /** The corner nearest upstage stage right: least x and least z. */
  x: number;
  z: number;
  width: number;
  depth: number;
  centerX: number;
  centerZ: number;
  /** Its top above the floor. */
  top: number;
  kind: string;
  label: string;
  tooltip: string;
}

export interface PlanTrussLine {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  /** How wide to draw it across the line. */
  across: number;
  /** Height of its underside: where a fixture hangs from. */
  height: number;
  label: string;
  tooltip: string;
}

export interface PlanTrussRing {
  centerX: number;
  centerZ: number;
  radius: number;
  across: number;
  height: number;
  label: string;
  tooltip: string;
}

export interface RoomPlan {
  /** Null when the shell has things in it but no room that can be drawn. */
  walls: PlanWalls | null;
  raised: PlanRaised[];
  trussLines: PlanTrussLine[];
  trussRings: PlanTrussRing[];
  /** The box round everything above. */
  bounds: PlanBounds;
}

const metres = (value: number) => `${value.toFixed(1)} m`;

const KIND_WORDS: Record<string, string> = {
  stage: 'Stage',
  riser: 'Riser',
  booth: 'Booth or counter',
};

/** How wide a truss is drawn on the plan: what the scan measured, or 0.3 m. */
function drawnAcross(across: number | undefined): number {
  const measured = typeof across === 'number' && Number.isFinite(across) ? across : 0.3;
  return Math.min(1.2, Math.max(0.1, measured));
}

/**
 * The scanned room of a rig as shapes on the plan, or null when there is
 * nothing to draw: no shell, a shell that is not from a scan (a demo preset's
 * dome and balcony are the 3D view's), or a scan shell with nothing usable.
 */
export function roomPlan(shell: RoomShell | null | undefined): RoomPlan | null {
  if (!shell || shell.source !== 'scan') return null;

  let walls: PlanWalls | null = null;
  const room = shell.room;
  if (room && usableRoom(room)) {
    const outline = roomOutline(shell);
    const size = `${metres(room.width)} wide, ${metres(room.depth)} deep, ${metres(room.height)} high`;
    if (outline) {
      walls = {
        points: outline,
        outlined: true,
        tooltip: `Scanned room: ${outline.length} walls, ${size} (the box round it)`,
      };
    } else {
      const halfW = room.width / 2;
      const halfD = room.depth / 2;
      walls = {
        // Clockwise seen from above, from upstage stage right, as an outline is.
        points: [
          { x: -halfW, z: -halfD }, { x: halfW, z: -halfD }, { x: halfW, z: halfD }, { x: -halfW, z: halfD },
        ],
        outlined: false,
        tooltip: `Scanned room: ${size}`,
      };
    }
  }

  const raised: PlanRaised[] = scanRisers(shell).map((riser) => {
    const top = (riser.base_height ?? 0) + riser.height;
    const kind = riser.kind ?? 'riser';
    const name = riser.name ?? KIND_WORDS[kind] ?? 'Raised area';
    return {
      x: riser.center_x - riser.width / 2,
      z: riser.center_z - riser.depth / 2,
      width: riser.width,
      depth: riser.depth,
      centerX: riser.center_x,
      centerZ: riser.center_z,
      top,
      kind,
      label: `${name} · ${top.toFixed(2)} m high`,
      tooltip: `${name}: ${metres(riser.width)} by ${metres(riser.depth)}, top ${top.toFixed(2)} m above the floor`,
    };
  });

  // A line is drawn from its two ends, which every stored shell has: one
  // stored before headings were written says nothing else.
  const trussLines: PlanTrussLine[] = (shell.truss_lines ?? []).filter(usableLine).map((line) => {
    const name = line.name ?? 'Overhead line';
    const length = Math.hypot(line.x2 - line.x1, line.z2 - line.z1);
    return {
      x1: line.x1,
      z1: line.z1,
      x2: line.x2,
      z2: line.z2,
      across: drawnAcross(line.across),
      height: line.height,
      label: `${name} · hangs at ${line.height.toFixed(2)} m`,
      tooltip: `${name}: ${metres(length)} long, underside ${line.height.toFixed(2)} m up, ${lineRunText(line)}`,
    };
  });

  const trussRings: PlanTrussRing[] = scanRings(shell).map((ring) => {
    const name = ring.name ?? 'Overhead ring';
    return {
      centerX: ring.center_x,
      centerZ: ring.center_z,
      radius: ring.radius,
      across: Math.min(drawnAcross(ring.across), ring.radius * 1.8),
      height: ring.height,
      label: `${name} · hangs at ${ring.height.toFixed(2)} m`,
      tooltip: `${name}: a ring ${metres(ring.radius * 2)} across, underside ${ring.height.toFixed(2)} m up`,
    };
  });

  if (!walls && raised.length + trussLines.length + trussRings.length === 0) return null;

  const xs: number[] = [];
  const zs: number[] = [];
  for (const point of walls?.points ?? []) { xs.push(point.x); zs.push(point.z); }
  for (const area of raised) { xs.push(area.x, area.x + area.width); zs.push(area.z, area.z + area.depth); }
  for (const line of trussLines) { xs.push(line.x1, line.x2); zs.push(line.z1, line.z2); }
  for (const ring of trussRings) {
    const reach = ring.radius + ring.across / 2;
    xs.push(ring.centerX - reach, ring.centerX + reach);
    zs.push(ring.centerZ - reach, ring.centerZ + reach);
  }
  const bounds = { xMin: Math.min(...xs), xMax: Math.max(...xs), zMin: Math.min(...zs), zMax: Math.max(...zs) };

  return { walls, raised, trussLines, trussRings, bounds };
}

export interface PlanViewBox {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

/**
 * The part of the plan the 2D view shows, in its SVG units: metres, with the
 * stage's upstage stage right corner at (padding, padding). With no room it
 * is the stage and its margin, from the origin, as the view has always been.
 * A room that reaches beyond that grows it to take the room in, with the same
 * margin round it; a room inside it changes nothing.
 */
export function planViewBox(
  stageWidth: number, stageDepth: number, padding: number, bounds: PlanBounds | null | undefined,
): PlanViewBox {
  const stage = { minX: 0, minY: 0, width: stageWidth + padding * 2, height: stageDepth + padding * 2 };
  if (!bounds) return stage;
  // A room corner at x sits at x + stageWidth / 2 + padding, and wants
  // `padding` clear of it on the outside.
  const minX = Math.min(0, bounds.xMin + stageWidth / 2);
  const minY = Math.min(0, bounds.zMin + stageDepth / 2);
  const maxX = Math.max(stage.width, bounds.xMax + stageWidth / 2 + padding * 2);
  const maxY = Math.max(stage.height, bounds.zMax + stageDepth / 2 + padding * 2);
  return { minX, minY, width: maxX - minX, height: maxY - minY };
}

// ---------------------------------------------------------------------------
// Where a fixture may be put on the plan
// ---------------------------------------------------------------------------

/**
 * A position held to the scanned room as the plan draws it: left alone inside
 * the walls, and otherwise brought to the nearest point of them. In a room
 * with a floor outline that is the outline itself, so the notch of an L is
 * outside like anywhere else beyond a wall (`holdNearOutline`, which the 3D
 * view's drag uses with a margin; here there is none). In a box room it is the
 * box.
 */
export function holdToWalls(walls: PlanWalls, x: number, z: number): PlanPoint {
  if (walls.outlined) return holdNearOutline(walls.points, x, z, 0);
  const box = outlineBox(walls.points);
  return {
    x: Math.min(Math.max(x, box.xMin), box.xMax),
    z: Math.min(Math.max(z, box.zMin), box.zMax),
  };
}

/**
 * Where a drag or a palette drop may land on the plan. With a scanned room
 * drawn, anywhere inside its walls. With none, the stage deck and only the
 * deck, as it has always been.
 */
export function holdOnPlan(
  x: number, z: number, stageWidth: number, stageDepth: number, walls: PlanWalls | null | undefined,
): PlanPoint {
  if (walls) return holdToWalls(walls, x, z);
  return {
    x: Math.min(Math.max(x, -stageWidth / 2), stageWidth / 2),
    z: Math.min(Math.max(z, -stageDepth / 2), stageDepth / 2),
  };
}

/**
 * The nearest grid point, out in the room as on the deck: the grid's lines
 * carried on past the deck's edge, with no last line to stop at. Holding the
 * result to the walls is the caller's (`holdOnPlan`), and may leave it on a
 * wall between two lines.
 */
export function snapToRoomGrid(x: number, z: number, gridSize: number): PlanPoint {
  if (!(gridSize > 0)) return { x, z };
  // `+ 0` so a position just short of a line through the origin is 0, not -0.
  return { x: Math.round(x / gridSize) * gridSize + 0, z: Math.round(z / gridSize) * gridSize + 0 };
}

// ---------------------------------------------------------------------------
// The plan's own labels: UPSTAGE, AUDIENCE and the scale bar
// ---------------------------------------------------------------------------

/** The edges the plan's own labels are set against, in the view's SVG units. */
export interface PlanFrame {
  left: number;
  right: number;
  top: number;
  bottom: number;
  centreX: number;
}

/**
 * What UPSTAGE, AUDIENCE and the scale bar go by. With no room drawn it is
 * the deck. With one, it is the outer of the deck and the room's walls on
 * each side, so the labels stand outside the scanned floor and UPSTAGE reads
 * against the wall that really is the back one.
 */
export function planFrame(
  stageWidth: number, stageDepth: number, padding: number, walls: PlanWalls | null | undefined,
): PlanFrame {
  const deck = {
    left: padding,
    right: stageWidth + padding,
    top: padding,
    bottom: stageDepth + padding,
    centreX: stageWidth / 2 + padding,
  };
  if (!walls) return deck;
  const box = outlineBox(walls.points);
  const left = Math.min(deck.left, box.xMin + stageWidth / 2 + padding);
  const right = Math.max(deck.right, box.xMax + stageWidth / 2 + padding);
  return {
    left,
    right,
    top: Math.min(deck.top, box.zMin + stageDepth / 2 + padding),
    bottom: Math.max(deck.bottom, box.zMax + stageDepth / 2 + padding),
    centreX: (left + right) / 2,
  };
}

// ---------------------------------------------------------------------------
// Labels of the room layer, laid out so they do not print over each other
// ---------------------------------------------------------------------------

export const RAISED_LABEL_SIZE = 0.24;
export const TRUSS_LABEL_SIZE = 0.22;
/** A line within this of straight across the room keeps a level label. */
const LEVEL_WITHIN_DEG = 1;
/** Glyphs are taken as this share of the font size wide: nothing here can measure text. */
const GLYPH_WIDTH = 0.55;
/** Clear space kept between two labels, in metres. */
const LABEL_GAP = 0.04;
/** How far a label steps each time it is nudged, in font sizes. */
const LABEL_STEP = 1.4;

export interface PlanLabel {
  text: string;
  /** The middle of the text's baseline, on the plan. */
  x: number;
  z: number;
  /**
   * Degrees the text is turned, clockwise as the plan is drawn; 0 is level.
   * Always from -90 up to but not including 90, so it never reads upside down.
   */
  angle: number;
  size: number;
  /** True when it was moved off its usual place to clear another label. */
  nudged: boolean;
}

export interface PlanLabels {
  raised: PlanLabel[];
  trussLines: PlanLabel[];
  trussRings: PlanLabel[];
}

type LabelBox = { cx: number; cz: number; hw: number; hh: number; ux: number; uz: number; vx: number; vz: number };

/** The rectangle a label covers: along its baseline and up from it. */
function labelBox(text: string, x: number, z: number, angle: number, size: number): LabelBox {
  const turn = (angle * Math.PI) / 180;
  const ux = Math.cos(turn);
  const uz = Math.sin(turn);
  // Up for the text, on a plan drawn with z downwards.
  const vx = Math.sin(turn);
  const vz = -Math.cos(turn);
  return {
    cx: x + vx * size * 0.3,
    cz: z + vz * size * 0.3,
    hw: (text.length * size * GLYPH_WIDTH) / 2,
    hh: size / 2,
    ux, uz, vx, vz,
  };
}

/** Whether two turned rectangles come within `gap` of each other. */
function boxesOverlap(a: LabelBox, b: LabelBox, gap: number): boolean {
  const dx = b.cx - a.cx;
  const dz = b.cz - a.cz;
  const reach = (box: LabelBox, ax: number, az: number) =>
    box.hw * Math.abs(box.ux * ax + box.uz * az) + box.hh * Math.abs(box.vx * ax + box.vz * az);
  // Apart along any one of the four edge directions is apart.
  for (const [ax, az] of [[a.ux, a.uz], [a.vx, a.vz], [b.ux, b.uz], [b.vx, b.vz]]) {
    if (Math.abs(dx * ax + dz * az) >= reach(a, ax, az) + reach(b, ax, az) + gap) return false;
  }
  return true;
}

/**
 * The turn that lays text along a line from (x1, z1) to (x2, z2) and keeps it
 * the right way up: 0 for a line across the room, whichever end it is written
 * from, and otherwise from -90 (reading up the plan) to just under 90.
 */
export function labelAngle(x1: number, z1: number, x2: number, z2: number): number {
  let angle = (Math.atan2(z2 - z1, x2 - x1) * 180) / Math.PI;
  if (angle >= 90) angle -= 180;
  if (angle < -90) angle += 180;
  if (Math.abs(angle) < LEVEL_WITHIN_DEG) return 0;
  if (angle > 90 - LEVEL_WITHIN_DEG) return -90;
  return Math.round(angle * 10) / 10 + 0;
}

/**
 * Where each label of the room layer goes. Each starts at its usual place: a
 * raised area's in its middle, a truss line's over the middle of the line and
 * turned to lie along it, a ring's over its upstage side. Then, in that order,
 * one that would print over a label already placed is stepped away from its
 * shape, to the far side of it, and further each way, until it is clear. The
 * earlier label keeps its place. One with nowhere clear stays where it began.
 */
export function planLabels(plan: RoomPlan): PlanLabels {
  const placed: LabelBox[] = [];

  const place = (
    text: string, x: number, z: number, angle: number, size: number, across: number,
  ): PlanLabel => {
    const turn = (angle * Math.PI) / 180;
    const upX = Math.sin(turn);
    const upZ = -Math.cos(turn);
    const step = size * LABEL_STEP;
    // Stepped away from its shape, then to the far side of it, then further each way.
    const offsets = [0, step, -across, 2 * step, -across - step, 3 * step, -across - 2 * step];
    for (const offset of offsets) {
      const lx = x + upX * offset;
      const lz = z + upZ * offset;
      const box = labelBox(text, lx, lz, angle, size);
      if (placed.some((other) => boxesOverlap(box, other, LABEL_GAP))) continue;
      placed.push(box);
      return { text, x: lx + 0, z: lz + 0, angle, size, nudged: offset !== 0 };
    }
    placed.push(labelBox(text, x, z, angle, size));
    return { text, x, z, angle, size, nudged: false };
  };

  const raised = plan.raised.map((area) =>
    // Inside its own rectangle, so "the far side" is only a step down.
    place(area.label, area.centerX, area.centerZ + 0.08, 0, RAISED_LABEL_SIZE, RAISED_LABEL_SIZE * LABEL_STEP));

  const trussLines = plan.trussLines.map((line) => {
    const angle = labelAngle(line.x1, line.z1, line.x2, line.z2);
    const turn = (angle * Math.PI) / 180;
    const off = line.across / 2 + 0.1;
    return place(
      line.label,
      (line.x1 + line.x2) / 2 + Math.sin(turn) * off,
      (line.z1 + line.z2) / 2 - Math.cos(turn) * off,
      angle,
      TRUSS_LABEL_SIZE,
      // Across the line's drawn width and the text's own height, to sit under it.
      line.across + 0.2 + TRUSS_LABEL_SIZE * 0.7,
    );
  });

  const trussRings = plan.trussRings.map((ring) =>
    place(
      ring.label,
      ring.centerX,
      ring.centerZ - ring.radius - ring.across / 2 - 0.1,
      0,
      TRUSS_LABEL_SIZE,
      ring.across + 0.2 + TRUSS_LABEL_SIZE * 0.7,
    ));

  return { raised, trussLines, trussRings };
}

/** The `points` of an SVG polygon for corners on the plan. */
export function planPolygonPoints(points: PlanPoint[], toSvgX: (x: number) => number, toSvgY: (z: number) => number): string {
  return points.map((point) => `${toSvgX(point.x)},${toSvgY(point.z)}`).join(' ');
}
