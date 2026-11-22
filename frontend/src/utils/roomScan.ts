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
  /** Always true: the fixture goes from one guess to a better one, and stays unconfirmed. */
  suggested?: boolean;
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
    /** Rings of truss found overhead. Absent from an older server's answer. */
    overhead_rings?: number;
    /** 4 for a box; the number of outline segments for a room that is not one. */
    walls?: number;
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
    /** How many fixture moves an undo would now take back. */
    undo_available?: number;
    message: string;
  };
}

/** A fixture an undo left alone, and why: a person has placed, confirmed or moved it since. */
export interface RoomScanSkipped {
  rig_fixture_id: number;
  name: string;
  reason: string;
}

/** The answer to POST /api/rigs/{id}/room-scan/undo. */
export interface RoomScanUndoResult {
  rig_id: number;
  restored: number;
  skipped: number;
  restored_fixtures: Array<{ rig_fixture_id: number; name: string; from: RoomScanPoint; to: RoomScanPoint }>;
  skipped_fixtures: RoomScanSkipped[];
  message: string;
}

/** The answer to DELETE /api/rigs/{id}/room-shell. The fixture fields are there only when asked to restore. */
export interface RoomShellRemoved {
  rig_id: number;
  removed: boolean;
  /** Moves that can still be undone afterwards. */
  undo_available?: number;
  fixtures_restored?: number;
  fixtures_skipped?: number;
  skipped_fixtures?: RoomScanSkipped[];
  message?: string;
}

/** How many fixture moves the rig's undo record holds. */
export function undoCount(rig: { room_scan_undo?: { moves?: unknown[] | null } | null } | null | undefined): number {
  return rig?.room_scan_undo?.moves?.length ?? 0;
}

export function roomScanPath(rigId: number): string {
  return `/rigs/${rigId}/room-scan`;
}

export function roomShellPath(rigId: number): string {
  return `/rigs/${rigId}/room-shell`;
}

export function roomScanUndoPath(rigId: number): string {
  return `/rigs/${rigId}/room-scan/undo`;
}

/** Where a drag in the 3D view saves a fixture's position, which also confirms it. */
export function fixturePositionPath(rigId: number, fixtureId: number): string {
  return `/rigs/${rigId}/fixtures/${fixtureId}/position`;
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

/**
 * Which way an overhead line runs, in words, read from its two ends: a shell
 * stored before headings were written has nothing else to go by. Within two
 * degrees of the room's own axes it runs along them.
 */
export function lineRunText(line: { x1: number; z1: number; x2: number; z2: number; axis?: string }): string {
  const runX = Math.abs(line.x2 - line.x1);
  const runZ = Math.abs(line.z2 - line.z1);
  if (!(runX > 0 || runZ > 0)) {
    return line.axis === 'z' ? 'running upstage to downstage' : 'running across the room';
  }
  const degrees = (Math.atan2(runZ, runX) * 180) / Math.PI;
  if (degrees <= 2) return 'running across the room';
  if (degrees >= 88) return 'running upstage to downstage';
  return `running at ${Math.round(degrees)} degrees to the room`;
}

/**
 * One line per thing the scan found, in the order the room is built: the
 * walls when the room is not a box, raised areas, then overhead.
 */
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
      + lineRunText(line),
    );
  }
  for (const ring of shell.truss_rings ?? []) {
    lines.push(
      `${ring.name ?? 'Overhead ring'}: a ring ${metres(ring.radius * 2)} across, `
      + `underside ${ring.height.toFixed(2)} m up`,
    );
  }
  if (lines.length === 0) lines.push('No stage, riser, booth, truss or bar was found: only the floor, walls and ceiling.');
  const corners = shell.room?.outline?.length ?? 0;
  if (corners >= 3) {
    lines.unshift(`The room is not a box: its floor outline has ${corners} walls. The size above is the box round it.`);
  }
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

/** "7 fixtures" / "1 fixture". */
export function fixtureCountText(n: number): string {
  return count(n, 'fixture');
}

/** The label of the undo button: "Undo room scan moves (7)". */
export function undoButtonText(moves: number): string {
  return `Undo room scan moves (${moves})`;
}

/** What the undo button asks before it does anything. */
export function undoQuestionText(moves: number): string {
  return `Put ${moves === 1 ? 'the 1 fixture' : `the ${moves} fixtures`} the room scan moved back where `
    + `${moves === 1 ? 'it' : 'they'} stood before it? Any you have tapped, confirmed, dragged or moved since `
    + 'are left where they are.';
}

/** "Left alone: Spot 1 (it was tapped or dragged into place since); Par 3 (...)." or '' when none were. */
export function skippedText(skipped: RoomScanSkipped[] | undefined): string {
  if (!skipped || skipped.length === 0) return '';
  const shown = skipped.slice(0, 6).map((item) => `${item.name} (${item.reason})`);
  const more = skipped.length - shown.length;
  return `Left alone: ${shown.join('; ')}${more > 0 ? `; and ${more} more` : ''}.`;
}

/** What an undo did, in the server's words, with the fixtures it left alone named. */
export function undoResultText(result: RoomScanUndoResult): string {
  return [result.message, skippedText(result.skipped_fixtures)].filter(Boolean).join(' ');
}

/** What removing the stored room did, with or without putting fixtures back. */
export function removeResultText(result: RoomShellRemoved): string {
  const room = result.removed ? 'The stored room was taken off this rig.' : 'This rig had no stored room.';
  if (result.fixtures_restored === undefined) {
    const later = (result.undo_available ?? 0) > 0
      ? ' Fixtures were left where they are; Undo room scan moves still puts them back.'
      : ' Fixtures were left where they are.';
    return room + later;
  }
  return [room, result.message, skippedText(result.skipped_fixtures)].filter(Boolean).join(' ');
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
