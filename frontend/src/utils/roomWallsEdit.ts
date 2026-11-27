// Editing a stored room's walls by hand: the corners the Edit Room dialog
// lists and the 2D plan lets you drag, what a row of the dialog would send,
// and how what the new walls leave outside is worded. Pure, so it can be
// tested without a server or a screen. The server makes the change and says
// what is outside (backend/app/services/room_scan/outline_edit.py);
// docs/ROOM_SCAN.md describes both.
import type { RoomShell, RoomShellEdits } from '../types';
import { positionText } from './roomShellEdit';

export type WallCorner = { x: number; z: number };

/** The server's limits on a room's walls and height (outline_edit.py). */
export const WALL_LIMITS = {
  cornersMin: 3,
  cornersMax: 64,
  /** How far from the middle of the floor a corner may be, in metres. */
  reach: 100,
  heightMin: 1.5,
  heightMax: 30,
} as const;

const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

/**
 * The corners of a scanned room's floor in the order the server numbers
 * them, and whether the room is a box. A box room's are its four, clockwise
 * seen from above from upstage stage right, which is also the order the 2D
 * plan draws them in: corner 2 in the dialog is corner 2 on the plan and
 * corner 2 to the server (`room_corners`). Null for no shell, one that is
 * not from a scan, and a room with neither an outline nor a size.
 */
export function wallCorners(shell: RoomShell | null | undefined): { corners: WallCorner[]; box: boolean } | null {
  if (!shell || shell.source !== 'scan' || !shell.room) return null;
  const room = shell.room;
  const raw = room.outline;
  if (Array.isArray(raw) && raw.length >= WALL_LIMITS.cornersMin
    && raw.every((point) => point && isNumber(point.x) && isNumber(point.z))) {
    return { corners: raw.map((point) => ({ x: point.x, z: point.z })), box: false };
  }
  if (!isNumber(room.width) || !isNumber(room.depth) || room.width <= 0 || room.depth <= 0) return null;
  const halfW = room.width / 2;
  const halfD = room.depth / 2;
  return {
    corners: [{ x: -halfW, z: -halfD }, { x: halfW, z: -halfD }, { x: halfW, z: halfD }, { x: -halfW, z: halfD }],
    box: true,
  };
}

/** The room's height as stored, or null when it has none. */
export function roomHeight(shell: RoomShell | null | undefined): number | null {
  const height = shell?.room?.height;
  return isNumber(height) && height > 0 ? height : null;
}

/**
 * How big the walls are, in words: wall to wall each way, measured from the
 * corners themselves and not from the stored box, which is centred on the
 * middle of the floor and so is wider than a room that is not.
 */
export function wallsSizeText(corners: WallCorner[], box: boolean): string {
  const xs = corners.map((corner) => corner.x);
  const zs = corners.map((corner) => corner.z);
  const across = Math.max(...xs) - Math.min(...xs);
  const deep = Math.max(...zs) - Math.min(...zs);
  return `${corners.length} corners, ${positionText(across)} m across and ${positionText(deep)} m from upstage to downstage`
    + (box ? ' (a box)' : '');
}

/** A typed number, or null when it is not one. A comma is taken for a decimal point. */
function typedNumber(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** What the two fields of a corner's row hold while it is being edited: text, as typed. */
export interface CornerDraft {
  x: string;
  z: string;
}

export function cornerDraftOf(corner: WallCorner): CornerDraft {
  return { x: positionText(corner.x), z: positionText(corner.z) };
}

export interface CornerReading {
  /** Where to send the corner, or null when the fields say where it already is. */
  changes: { x?: number; z?: number } | null;
  /** Why the fields cannot be saved as they are, or null when they can. */
  problem: string | null;
}

/**
 * What a corner's row would change. Only the one of Across and Depth that
 * differs from what is stored is sent. Whether the walls still make a room
 * (none crossing another, none too short) is the server's to say.
 */
export function readCorner(corner: WallCorner, draft: CornerDraft): CornerReading {
  const changes: { x?: number; z?: number } = {};
  const shown = cornerDraftOf(corner);
  for (const [typed, was, key, label] of [
    [draft.x, shown.x, 'x', 'Across'], [draft.z, shown.z, 'z', 'Depth'],
  ] as Array<[string, string, 'x' | 'z', string]>) {
    if (typed.trim() === was) continue;
    const value = typedNumber(typed);
    if (value === null) return { changes: null, problem: `${label} must be a number of metres, such as -1.5.` };
    if (Math.abs(value) > WALL_LIMITS.reach) {
      return { changes: null, problem: `${label} can be at most ${WALL_LIMITS.reach} m from the middle of the floor.` };
    }
    if (Math.abs(value - corner[key]) >= 0.0005) changes[key] = value;
  }
  return { changes: Object.keys(changes).length > 0 ? changes : null, problem: null };
}

export interface HeightReading {
  /** The height to send, or null when the field says what is stored. */
  height: number | null;
  problem: string | null;
}

/** What the room height field would change. */
export function readRoomHeight(stored: number | null, typed: string): HeightReading {
  if (stored !== null && typed.trim() === positionText(stored)) return { height: null, problem: null };
  const value = typedNumber(typed);
  if (value === null) {
    return { height: null, problem: `The room's height must be a number of metres, from ${WALL_LIMITS.heightMin} to ${WALL_LIMITS.heightMax}.` };
  }
  if (value < WALL_LIMITS.heightMin || value > WALL_LIMITS.heightMax) {
    return { height: null, problem: `The room's height must be between ${WALL_LIMITS.heightMin} m and ${WALL_LIMITS.heightMax} m.` };
  }
  if (stored !== null && Math.abs(value - stored) < 0.0005) return { height: null, problem: null };
  return { height: value, problem: null };
}

// --- What the walls leave outside ----------------------------------------------

/** One raised area, overhead line or ring beyond a wall or above the ceiling. */
export interface OutsideItem {
  kind: 'risers' | 'truss_lines' | 'truss_rings';
  /** Its place in the stored list, from 0. */
  index: number;
  name: string;
  /** "outside the walls", "partly outside the walls", "above the ceiling", or two of them joined. */
  reason: string;
  /** True when it was outside before the change this report came with. */
  already_outside?: boolean;
}

/** One fixture beyond a wall or above the ceiling. */
export interface OutsideFixture {
  rig_fixture_id: number;
  name: string;
  position?: { x: number; y: number; z: number };
  reason: string;
  already_outside?: boolean;
}

/** What the room's walls and ceiling leave outside, as the server lists it. Nothing in it was moved. */
export interface OutsideReport {
  items: OutsideItem[];
  fixtures: OutsideFixture[];
  count: number;
}

const KIND_WORDS: Record<string, string> = {
  risers: 'raised area',
  truss_lines: 'overhead line',
  truss_rings: 'overhead ring',
};

/** A report read safely: an answer from an older server, or none, is an empty one. */
export function outsideOf(report: Partial<OutsideReport> | null | undefined): OutsideReport {
  const items = Array.isArray(report?.items) ? report!.items! : [];
  const fixtures = Array.isArray(report?.fixtures) ? report!.fixtures! : [];
  return { items, fixtures, count: items.length + fixtures.length };
}

/**
 * The warning list: one line for each thing outside, the room's own items
 * first. One that was outside before the change says so, so what the change
 * itself put outside stands out.
 */
export function outsideLines(report: Partial<OutsideReport> | null | undefined): string[] {
  const { items, fixtures } = outsideOf(report);
  const before = (entry: { already_outside?: boolean }) => (entry.already_outside ? ' (it was before this change)' : '');
  return [
    ...items.map((item) => `${item.name} (${KIND_WORDS[item.kind] ?? 'part of the room'}) is ${item.reason}${before(item)}.`),
    ...fixtures.map((fixture) => `${fixture.name} (fixture) is ${fixture.reason}${before(fixture)}.`),
  ];
}

/** The heading over the warning list. */
export function outsideHeading(report: Partial<OutsideReport> | null | undefined): string {
  const { count } = outsideOf(report);
  return count === 1
    ? '1 thing is outside the walls or above the ceiling. It was not moved:'
    : `${count} things are outside the walls or above the ceiling. None was moved:`;
}

/** What is sent to redraw the walls, set the height, or both. */
export interface OutlineChanges {
  /** Every corner of the floor in order, each [x, z] in metres. */
  corners?: Array<[number, number]>;
  height?: number;
}

/** The answer to a change to the walls, and (without `changed`, `undo` and `message`) to reading them. */
export interface OutlineAnswer {
  rig_id: number;
  /** The whole stored room after the change. */
  room_shell: RoomShell;
  /** The corners as they now are; a box room's four. */
  outline: WallCorner[];
  box: boolean;
  height?: number | null;
  width?: number | null;
  depth?: number | null;
  /** False when what was sent is what was stored: nothing was written and there is no step to undo. */
  changed: boolean;
  undo?: RoomShellEdits;
  outside: OutsideReport;
  message: string;
  /** For a corner moved, added or deleted: its place afterwards. */
  index?: number;
}

/** The answer to GET /api/rigs/{id}/room-shell/outline. */
export interface OutlineRead {
  rig_id: number;
  outline: WallCorner[];
  box: boolean;
  height?: number | null;
  width?: number | null;
  depth?: number | null;
  outside: OutsideReport;
}
