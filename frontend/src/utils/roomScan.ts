// Room scan: what the server answers and how the dialog words it.
// Pure, so it can be tested without a server. docs/ROOM_SCAN.md describes the
// scan reader itself.
import type { RoomShell } from '../types';

export type ScanUnits = 'auto' | 'm' | 'cm' | 'mm';
export type ScanUpAxis = 'auto' | 'y' | 'z';
export type ScanRotate = 0 | 90 | 180 | 270;

/** What the operator can decide instead of the reader's guesses. */
export interface RoomScanOptions {
  units: ScanUnits;
  upAxis: ScanUpAxis;
  rotate: ScanRotate;
}

export const DEFAULT_SCAN_OPTIONS: RoomScanOptions = { units: 'auto', upAxis: 'auto', rotate: 0 };

/** The file endings the server reads. A .usdz must hold a text layer or RoomPlan JSON. */
export const ROOM_SCAN_ACCEPT = '.obj,.ply,.usdz,.usda,.json';

/** The server's own limit (room_scan.MAX_UPLOAD_BYTES). Checked here first so a huge file is not sent to be refused. */
export const ROOM_SCAN_MAX_BYTES = 200 * 1024 * 1024;

export interface RoomScanPoint {
  x: number;
  y: number;
  z: number;
}

export interface RoomScanMove {
  rig_fixture_id: number;
  name: string;
  group: string;
  from: RoomScanPoint;
  to: RoomScanPoint;
  reason: string;
}

/** The answer to POST /api/rigs/{id}/room-scan, preview or applied. */
export interface RoomScanPreview {
  rig_id: number;
  rig_name: string;
  file: string;
  format: string;
  room_shell: RoomShell;
  replaces_existing_shell: boolean;
  summary: {
    width: number;
    depth: number;
    height: number;
    raised_areas: number;
    overhead_lines: number;
    hanging_heights: number[];
    units: string;
    up_axis: string;
  };
  assumptions: string[];
  warnings: string[];
  fixtures: {
    total: number;
    unconfirmed: number;
    would_move: number;
    moves: RoomScanMove[];
  };
  operator_guide: string;
  /** Null for a preview: nothing was written. */
  applied: null | {
    room_shell_stored: boolean;
    fixtures_moved: number;
    fixtures_still_unconfirmed: number;
    message: string;
  };
}

export function roomScanPath(rigId: number): string {
  return `/rigs/${rigId}/room-scan`;
}

export function roomShellPath(rigId: number): string {
  return `/rigs/${rigId}/room-shell`;
}

/**
 * Query parameters for a preview or an apply. A guess left on 'auto' is not
 * sent, so the server's own default stands.
 */
export function roomScanParams(
  options: RoomScanOptions,
  apply?: { moveFixtures: boolean },
): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  if (options.units !== 'auto') params.units = options.units;
  if (options.upAxis !== 'auto') params.up_axis = options.upAxis;
  if (options.rotate !== 0) params.rotate = options.rotate;
  if (apply) {
    params.apply = true;
    params.move_fixtures = apply.moveFixtures;
  }
  return params;
}

const metres = (value: number) => `${value.toFixed(1)} m`;
const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "12.0 m wide, 9.0 m deep, 5.0 m high". */
export function roomSizeText(preview: RoomScanPreview): string {
  const { width, depth, height } = preview.summary;
  return `${metres(width)} wide, ${metres(depth)} deep, ${metres(height)} high`;
}

/** One line per thing the scan found, in the order the room is built: raised areas, then overhead. */
export function foundLines(preview: RoomScanPreview): string[] {
  const shell = preview.room_shell;
  const lines: string[] = [];
  for (const riser of shell.risers ?? []) {
    lines.push(
      `${riser.name ?? 'Raised area'}: ${metres(riser.width)} by ${metres(riser.depth)}, `
      + `${riser.height.toFixed(2)} m high`,
    );
  }
  for (const line of shell.truss_lines ?? []) {
    const length = typeof line.length === 'number' ? line.length : Math.hypot(line.x2 - line.x1, line.z2 - line.z1);
    lines.push(
      `${line.name ?? 'Overhead line'}: ${metres(length)} long, underside ${line.height.toFixed(2)} m up, `
      + `${line.axis === 'z' ? 'running upstage to downstage' : 'running across the room'}`,
    );
  }
  if (lines.length === 0) lines.push('No stage, riser, booth, truss or bar was found: only the floor, walls and ceiling.');
  return lines;
}

/** What applying would do to the rig's fixtures, in one sentence. */
export function fixtureMoveText(preview: RoomScanPreview): string {
  const { total, unconfirmed, would_move: wouldMove } = preview.fixtures;
  if (total === 0) return 'This rig has no fixtures, so only the room would be stored.';
  if (wouldMove === 0) {
    return unconfirmed === 0
      ? `All ${count(total, 'fixture')} have a confirmed or measured position. None would be moved.`
      : `None of the ${count(unconfirmed, 'unconfirmed fixture')} would be moved: they already agree with the scan, or were placed by something a scan may not overrule.`;
  }
  const kept = total - wouldMove;
  return `${count(wouldMove, 'unconfirmed fixture')} of ${total} would be moved to agree with the scan`
    + (kept > 0 ? `; the other ${kept} stay exactly where they are.` : '.');
}

const point = (p: RoomScanPoint) => `${p.x.toFixed(2)}, ${p.y.toFixed(2)}, ${p.z.toFixed(2)}`;

/** A move as text: "(-3.00, 6.00, -1.50) to (-3.00, 4.00, 0.50)". */
export function moveText(move: RoomScanMove): string {
  return `(${point(move.from)}) to (${point(move.to)})`;
}

/** Why a file cannot be sent at all, or null when it can. */
export function fileProblem(file: { name: string; size: number }): string | null {
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > ROOM_SCAN_MAX_BYTES) {
    return `${file.name} is ${(file.size / (1024 * 1024)).toFixed(0)} MB. The limit is `
      + `${ROOM_SCAN_MAX_BYTES / (1024 * 1024)} MB: export the scan at a lower detail.`;
  }
  return null;
}

/**
 * The message for a refused request. The server's own words are used wherever
 * it gave any: they say what to export instead (a binary USDZ), which units to
 * check, or that a locate walkthrough is running.
 */
export function roomScanErrorText(status: number | undefined, detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI's validation errors: a list of { msg }.
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === 'string') return first.msg;
  }
  if (status === 413) return 'The file is too large. Export the scan at a lower detail.';
  if (status === 409) return 'A locate walkthrough is running on this rig. Finish or end it, then apply the scan.';
  if (status === 404) return 'This rig no longer exists.';
  if (status === 401 || status === 403) return 'Sign in again to read a room scan.';
  if (status === undefined) return 'The server could not be reached. Nothing was changed.';
  return 'The scan could not be read. Nothing was changed.';
}
