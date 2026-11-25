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

/**
 * The file endings the server reads. A .usdz is read whether its layer is binary USD (USDC), text or
 * RoomPlan JSON; a .gltf sent on its own must hold its data inside it (a .glb always does). A .zip is
 * what a scan app shares when the scan is several files: a .gltf with its .bin, or an .obj with its
 * .mtl and textures. The server reads the one model in it, and a .gltf's .bin from beside it.
 */
export const ROOM_SCAN_ACCEPT = '.obj,.ply,.glb,.gltf,.usdz,.usdc,.usda,.json,.zip';

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
  /**
   * Degrees the fixture is turned with a stage that stands at a heading, clockwise seen from above.
   * The server sends it only where a fixture is turned: absent means not turned.
   */
  turn_deg?: number;
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
  /**
   * What applying would do to the DJ booth mark (slice 31). Sent with a preview only, and only
   * where the room already stored has a raised area marked as the DJ's booth.
   */
  dj_booth_mark?: {
    kept: boolean;
    dropped: boolean;
    /** Where the mark would be in the new room's raised areas, and what that one is called; null when dropped. */
    index: number | null;
    name: string | null;
    overlap?: number | null;
    /** The kind set by hand that is kept against what the scan reads there, or null. */
    kind_kept?: string | null;
    message?: string | null;
  } | null;
  /**
   * What applying would keep of the edits made by hand to the stored room's raised areas (slice 32).
   * Sent with a preview only, and only where there is something to say.
   */
  hand_edits?: RoomScanHandEdits | null;
  /** Null for a preview: nothing was written. */
  applied: null | {
    /** What was kept of the edits made by hand (slice 32). Sent only where there is something to say. */
    hand_edits?: RoomScanHandEdits | null;
    room_shell_stored: boolean;
    fixtures_moved: number;
    fixtures_still_unconfirmed: number;
    /** How many fixture moves an undo would now take back. */
    undo_available?: number;
    message: string;
    /**
     * The four below are sent only where the room this one replaced had a raised area marked as
     * the DJ's booth. Where the mark now is in the new room's raised areas, or null.
     */
    dj_booth?: number | null;
    /** True when no raised area of the new reading stands where the marked one did: the mark is gone. */
    dj_booth_dropped?: boolean;
    dj_booth_overlap?: number | null;
    /** The server's sentence for what became of the mark. */
    dj_booth_message?: string | null;
    /** Sent only where a kind set by hand was kept against what the scan read there (slice 31). */
    dj_booth_kind_kept?: string | null;
  };
}

/** An overhead line or ring spoken of in `hand_edits`: the list it is in, and its place there. */
type OverheadKind = 'truss_lines' | 'truss_rings';

/**
 * The hand edits a scan applied again keeps on the room's raised areas, and what became of the ones added by hand.
 * The five keys after `message` are for overhead lines and rings, deleted raised areas and checks (slice 33),
 * and each is sent only when it has something in it.
 */
export interface RoomScanHandEdits {
  /** How many raised areas of the new room keep a name, a height or a base height set by hand. */
  areas?: number;
  /** Each: its place in the new room's raised areas, what it is called, and which fields it keeps. */
  kept?: { index: number; name: string; edits: string[]; overlap?: number }[];
  /** Raised areas added by hand that the scan has nothing in the place of: kept as they were. */
  added_kept?: { index: number; name: string }[];
  /** Raised areas added by hand that the scan now has something in the place of. */
  added_replaced?: { name: string; by_index: number; by: string }[];
  message?: string | null;
  /** Overhead lines and rings of the new room that keep a name or a hanging height set by hand. */
  overhead_kept?: { kind: OverheadKind; index: number; name: string; edits: string[]; overlap?: number }[];
  /** Overhead lines and rings added by hand that the scan has nothing in the place of: kept as they were. */
  overhead_added_kept?: { kind: OverheadKind; index: number; name: string }[];
  /** Overhead lines and rings added by hand that the scan now has one in the place of. */
  overhead_added_replaced?: { kind: OverheadKind; name: string; by_index: number; by: string }[];
  /**
   * Scanned raised areas, overhead lines and rings deleted by hand that this scan reads again and
   * leaves out. `kind` is a raised area's kind ('stage', 'riser', 'booth'), and 'truss_lines' or
   * 'truss_rings' for a line or a ring (slice 34).
   */
  deleted_left_out?: { name: string; kind?: string | null; overlap?: number }[];
  /** Kept things the new room does not hold: above its ceiling, or outside its walls. Kept all the same. */
  warnings?: { kind: 'risers' | OverheadKind; index: number; name: string; reason: string }[];
}

const areasText = (count: number) => `${count} area${count === 1 ? '' : 's'}`;
const overheadText = (count: number) => `${count} overhead item${count === 1 ? '' : 's'}`;
/** "2 areas", "1 overhead item" or "2 areas and 1 overhead item"; empty with neither. */
const thingsText = (areas: number, overhead: number) =>
  [areas > 0 ? areasText(areas) : '', overhead > 0 ? overheadText(overhead) : ''].filter(Boolean).join(' and ');
const howMany = (list: unknown) => (Array.isArray(list) ? list.length : 0);

/**
 * The one line the dialog says about edits made by hand: "Will keep your edits on 2 areas" before
 * Apply and "Kept your edits on 2 areas" after it, with "1 area you added will be kept" and
 * "1 area you added will be replaced by the scan" joined on where there are any. Overhead lines
 * and rings are counted beside the areas ("2 areas and 1 overhead item"), what was deleted by hand
 * and the scan leaves out is said first ("will leave out 1 area and 1 overhead item you deleted"), and what the
 * new room does not hold last ("1 to check against the new room"). `replaced` is true when
 * something added by hand is lost or something is to be checked, which the dialog shows as a
 * warning. Null where the server sent nothing: no hand edit was there to keep.
 */
export function handEditsLine(
  answer: RoomScanPreview | null | undefined,
): { text: string; replaced: boolean } | null {
  if (!answer) return null;
  const done = !!answer.applied;
  const edits = done ? answer.applied?.hand_edits : answer.hand_edits;
  if (!edits) return null;
  const kept = thingsText(howMany(edits.kept), howMany(edits.overhead_kept));
  const added = thingsText(howMany(edits.added_kept), howMany(edits.overhead_added_kept));
  const replaced = thingsText(howMany(edits.added_replaced), howMany(edits.overhead_added_replaced));
  const deleted = Array.isArray(edits.deleted_left_out) ? edits.deleted_left_out : [];
  const overheadOut = deleted.filter((entry) => entry?.kind === 'truss_lines' || entry?.kind === 'truss_rings').length;
  const leftOut = thingsText(deleted.length - overheadOut, overheadOut);
  const toCheck = howMany(edits.warnings);
  const parts: string[] = [];
  if (leftOut) parts.push(`${done ? 'left' : 'will leave'} out ${leftOut} you deleted`);
  if (kept) parts.push(`${done ? 'kept' : 'will keep'} your edits on ${kept}`);
  if (added) parts.push(`${added} you added ${done ? 'kept' : 'will be kept'}`);
  if (replaced) parts.push(`${replaced} you added ${done ? 'replaced' : 'will be replaced'} by the scan`);
  if (toCheck > 0) parts.push(`${toCheck} to check against the new room`);
  if (parts.length === 0) return null;
  const text = parts.join('; ');
  return { text: text.charAt(0).toUpperCase() + text.slice(1), replaced: replaced !== '' || toCheck > 0 };
}

export const DJ_BOOTH_WILL_DROP_TEXT ='DJ booth mark will be dropped';

/**
 * The one line a preview says about the DJ booth mark before Apply: "DJ booth mark: kept on Riser",
 * or DJ_BOOTH_WILL_DROP_TEXT as a warning. A kind set by hand that is kept with it is said too:
 * "DJ booth mark: kept on Booth or counter (stays a booth, as set by hand)". Null when the stored
 * room has no marked booth (the server then sends nothing), and once the scan is applied.
 */
export function djBoothPreviewLine(
  preview: RoomScanPreview | null | undefined,
): { text: string; dropped: boolean } | null {
  const mark = preview?.dj_booth_mark;
  if (!preview || preview.applied || !mark) return null;
  if (mark.kept !== true) return mark.dropped === true ? { text: DJ_BOOTH_WILL_DROP_TEXT, dropped: true } : null;
  const name = typeof mark.name === 'string' && mark.name.trim()
    ? mark.name.trim()
    : (typeof mark.index === 'number' ? `raised area ${mark.index + 1}` : 'the same raised area');
  const kind = typeof mark.kind_kept === 'string' && mark.kind_kept.trim()
    ? ` (stays a ${mark.kind_kept.trim()}, as set by hand)`
    : '';
  return { text: `DJ booth mark: kept on ${name}${kind}`, dropped: false };
}

export const DJ_BOOTH_DROPPED_TEXT =
  'The DJ booth mark was dropped: no raised area in this scan stands where the marked one did. '
  + 'Mark the DJ booth again in Edit Room.';

/**
 * What to tell the operator when a scan applied again lost the DJ booth mark: the server's own
 * sentence, or DJ_BOOTH_DROPPED_TEXT where it sent none. '' when the mark was kept, when the room
 * had none, and for a preview: only a `dj_booth_dropped` that is exactly true is a dropped mark.
 */
export function djBoothDroppedText(applied: RoomScanPreview['applied'] | undefined): string {
  if (!applied || applied.dj_booth_dropped !== true) return '';
  const said = typeof applied.dj_booth_message === 'string' ? applied.dj_booth_message.trim() : '';
  return said || DJ_BOOTH_DROPPED_TEXT;
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

/**
 * One raised area, overhead line or ring of the stored room: the list it is
 * stored in (`risers`, `truss_lines`, `truss_rings`) and its place there, from 0.
 */
export function roomShellItemPath(rigId: number, kind: string, index: number): string {
  return `/rigs/${rigId}/room-shell/${kind}/${index}`;
}

/** One list of the stored room (`risers`, `truss_lines`, `truss_rings`): where an item is added to it. */
export function roomShellListPath(rigId: number, kind: string): string {
  return `/rigs/${rigId}/room-shell/${kind}`;
}

/** Where the latest edit made to the stored room by hand is taken back. */
export function roomShellUndoPath(rigId: number): string {
  return `/rigs/${rigId}/room-shell/undo`;
}

/** The stored room's walls: its floor outline and its height. */
export function roomOutlinePath(rigId: number): string {
  return `/rigs/${rigId}/room-shell/outline`;
}

/** Where a corner is added to the walls. */
export function roomOutlineCornersPath(rigId: number): string {
  return `/rigs/${rigId}/room-shell/outline/corners`;
}

/** One corner of the walls, by its place in the outline, from 0. */
export function roomOutlineCornerPath(rigId: number, index: number): string {
  return `/rigs/${rigId}/room-shell/outline/corners/${index}`;
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

/** The turn of a move in degrees, or 0 where it has none: absent, 0, or not a number at all. */
function turnOf(move: RoomScanMove): number {
  const turn = move.turn_deg;
  return typeof turn === 'number' && Number.isFinite(turn) ? turn : 0;
}

/** What a turn is written as where there is none. */
export const NO_TURN_TEXT = '-';

/**
 * The Turn cell of a move: "30 deg", "-12.5 deg", or a dash for a fixture that is not turned.
 * To a tenth of a degree, which is what a heading is stored to; a turn too small to show is a dash.
 */
export function turnText(move: RoomScanMove): string {
  const tenths = Math.round(turnOf(move) * 10) / 10;
  return tenths === 0 ? NO_TURN_TEXT : `${tenths} deg`;
}

/** How many of the moves turn their fixture: the ones whose Turn cell is not a dash. */
export function turnedCount(moves: RoomScanMove[] | null | undefined): number {
  return (moves ?? []).filter((move) => turnText(move) !== NO_TURN_TEXT).length;
}

/**
 * "3 of them will also be turned to face the way the stage does." for a preview, "3 of them were
 * also turned ..." once applied, and '' when no move turns anything, so a room standing square
 * reads as it always did.
 */
export function turnSummaryText(moves: RoomScanMove[] | null | undefined, applied = false): string {
  const turned = turnedCount(moves);
  if (turned === 0) return '';
  const total = (moves ?? []).length;
  const verb = applied ? (turned === 1 ? 'was' : 'were') : 'will';
  const tail = `also ${applied ? '' : 'be '}turned with the stage, which stands at a heading.`;
  if (turned < total) return `${turned} of them ${verb} ${tail}`;
  if (total === 1) return `It ${verb} ${tail}`;
  return `${total === 2 ? 'Both' : `All ${total}`} ${verb} ${tail}`;
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
 * it gave any: they say what to export instead (a USD file that cannot be read), which units to
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
