/**
 * A scanned room on the 2D layout view: what the rig's `room_shell` says, as
 * shapes on the plan. Walls (the box, or the floor outline of a room that is
 * not one), raised areas, truss lines at whatever heading they run and rings
 * of truss, each with the words for its label and tooltip.
 *
 * Numbers and words only: no React and no drawing. Coordinates are the rig's,
 * as the 3D view reads them: metres, origin at the centre of the floor, X
 * across, -Z upstage. Which shapes are fit to draw is decided by the same
 * rules the 3D view uses (previs/outline.ts, previs/roomShell.ts).
 * docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import { lineRunText } from '../../utils/roomScan';
import { roomOutline, usableRoom } from './previs/outline';
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

/** The `points` of an SVG polygon for corners on the plan. */
export function planPolygonPoints(points: PlanPoint[], toSvgX: (x: number) => number, toSvgY: (z: number) => number): string {
  return points.map((point) => `${toSvgX(point.x)},${toSvgY(point.z)}`).join(' ');
}
