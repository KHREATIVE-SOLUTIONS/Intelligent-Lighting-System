// Editing a stored room by hand: which of its items can be renamed, moved,
// resized, raised, turned or deleted, what a row of the Edit Room dialog would
// change, what its form would add, and how the dialog words it. Pure, so it
// can be tested without a server or a screen. The server makes the change
// (backend/app/services/room_scan/edit.py); docs/ROOM_SCAN.md describes both.
import type { RoomShell, RoomShellBox, RoomShellEdits, RoomShellLine, RoomShellRing } from '../types';
import { usableBox, usableLine, usableRing } from '../components/rig/previs/roomShell';
import { lineRunText } from './roomScan';

/** The list of the stored shell an item is in: what the server addresses it by. */
export type ShellItemKind = 'risers' | 'truss_lines' | 'truss_rings';

/** A size, height or heading of an item, by the name the server takes it. */
export type ShellSizeField = 'width' | 'depth' | 'length' | 'radius' | 'height' | 'heading_deg';

/** The server's own limit on a name (edit.NAME_MAX). */
export const SHELL_NAME_MAX = 60;

/**
 * The least each size can be, in metres, as the server has them (edit.py).
 * The most depends on the room, which the server checks: its answer says what
 * the room has room for.
 */
export const SHELL_LIMITS = {
  /** A raised area's width or depth. */
  side: 0.3,
  /** A raised area's deck above the floor, least and most. */
  deck: 0.05,
  deckMost: 3,
  /** A line, end to end. */
  line: 0.5,
  /** A ring, to the middle of the truss. */
  radius: 0.3,
  /** The underside of a line or ring. */
  hang: 0.5,
  /** A heading, either way round. */
  heading: 360,
} as const;

/** The size fields each kind of item has, in the order the dialog shows them. */
export const SHELL_SIZE_FIELDS: Record<ShellItemKind, ShellSizeField[]> = {
  risers: ['width', 'depth', 'height'],
  truss_lines: ['length', 'heading_deg', 'height'],
  truss_rings: ['radius', 'height'],
};

/** What a size field is called on screen. A raised area's `depth` is not the Depth it stands at. */
export const SHELL_FIELD_LABELS: Record<ShellSizeField, string> = {
  width: 'Width',
  depth: 'Front to back',
  length: 'Length',
  radius: 'Radius',
  height: 'Height',
  heading_deg: 'Heading',
};

/** One raised area, overhead line or ring of the stored room, as the dialog lists it. */
export interface ShellItem {
  kind: ShellItemKind;
  /**
   * Its place in the stored list, from 0. Not its place on the plan: the
   * views leave out what they cannot draw, and the server counts every one.
   */
  index: number;
  /** The name it has, or '' when the shell gives it none. */
  name: string;
  /** What it is called where it has no name: "Stage", "Overhead line". */
  fallbackName: string;
  /** Its size and height, in words. */
  detail: string;
  /** The middle of it on the plan, or null when its numbers are not all there. */
  centre: { x: number; z: number } | null;
  /**
   * The sizes it has stored, by the server's name for each: a raised area's
   * width, depth and height; a line's length, heading and height; a ring's
   * radius and height. One whose number is missing is left out, and cannot be
   * set from a row.
   */
  sizes: Partial<Record<ShellSizeField, number>>;
  /** Whether the 2D and 3D views draw it. One they do not can still be deleted. */
  drawn: boolean;
  /** False once somebody has moved, resized or added it: it is no longer the scan's guess. */
  suggested: boolean;
  /** What a person has done to it, for the row's chips: "Added by hand", "Moved by hand", "Resized by hand". */
  marks: string[];
}

const KIND_WORDS: Record<string, string> = {
  stage: 'Stage',
  riser: 'Riser',
  booth: 'Booth or counter',
};

const metres = (value: number) => `${value.toFixed(1)} m`;
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const named = (name: unknown): string => (typeof name === 'string' ? name.trim() : '');
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;

/** The sizes of a stored item that are numbers, by field. */
function sizesOf(stored: Record<string, unknown>, fields: ShellSizeField[]): Partial<Record<ShellSizeField, number>> {
  const sizes: Partial<Record<ShellSizeField, number>> = {};
  for (const field of fields) {
    const value = stored[field];
    if (isNumber(value)) sizes[field] = value;
  }
  return sizes;
}

/** What a person has done to a stored item, read from the marks the server leaves on it. */
function marksOf(stored: { suggested?: boolean; basis?: string; added_by_hand?: boolean }): string[] {
  const basis = typeof stored.basis === 'string' ? stored.basis : '';
  const marks: string[] = [];
  if (stored.added_by_hand === true) marks.push('Added by hand');
  if (basis.includes('Moved by hand.')) marks.push('Moved by hand');
  if (basis.includes('Resized by hand.')) marks.push('Resized by hand');
  // A shell edited before the marks were told apart says only that it is not the scan's.
  if (marks.length === 0 && stored.suggested === false) marks.push('Moved by hand');
  return marks;
}

/**
 * The heading a line's two ends give it, as the server stores one: degrees
 * clockwise from across the room seen from above, over -90 and up to 90, to a
 * tenth. Null when the ends are missing or are the same point.
 */
export function lineHeading(line: { x1: number; z1: number; x2: number; z2: number }): number | null {
  if (!isNumber(line.x1) || !isNumber(line.z1) || !isNumber(line.x2) || !isNumber(line.z2)) return null;
  const runX = line.x2 - line.x1;
  const runZ = line.z2 - line.z1;
  if (runX === 0 && runZ === 0) return null;
  let degrees = (Math.atan2(runZ, runX) * 180) / Math.PI;
  if (degrees > 90) degrees -= 180;
  else if (degrees <= -90) degrees += 180;
  return Math.round(degrees * 10) / 10 + 0;
}

/**
 * Everything in a scanned room that can be edited, in the order the dialog
 * lists it: raised areas, overhead lines, rings. Each carries its place in
 * the stored list. Empty for no shell and for one that is not from a scan (a
 * demo preset's dome and balcony are not edited here).
 */
export function shellItems(shell: RoomShell | null | undefined): ShellItem[] {
  if (!shell || shell.source !== 'scan') return [];
  const items: ShellItem[] = [];

  (Array.isArray(shell.risers) ? shell.risers : []).forEach((stored: RoomShellBox | null, index) => {
    if (!isObject(stored)) return;
    const riser = stored as unknown as RoomShellBox;
    const drawn = usableBox(riser);
    const centre = isNumber(riser.center_x) && isNumber(riser.center_z) ? { x: riser.center_x, z: riser.center_z } : null;
    items.push({
      kind: 'risers',
      index,
      name: named(riser.name),
      fallbackName: KIND_WORDS[riser.kind ?? 'riser'] ?? 'Raised area',
      detail: drawn
        ? `${metres(riser.width)} by ${metres(riser.depth)}, top ${((riser.base_height ?? 0) + riser.height).toFixed(2)} m above the floor`
        : 'Not drawn: its size is missing',
      centre,
      sizes: sizesOf(stored, SHELL_SIZE_FIELDS.risers),
      drawn,
      suggested: riser.suggested !== false,
      marks: marksOf(riser),
    });
  });

  (Array.isArray(shell.truss_lines) ? shell.truss_lines : []).forEach((stored: RoomShellLine | null, index) => {
    if (!isObject(stored)) return;
    const line = stored as unknown as RoomShellLine;
    const drawn = usableLine(line);
    const ends = isNumber(line.x1) && isNumber(line.z1) && isNumber(line.x2) && isNumber(line.z2);
    // A line's length and heading are what its two ends say, whatever else is stored.
    const sizes = sizesOf(stored, ['height']);
    if (ends) {
      sizes.length = Math.hypot(line.x2 - line.x1, line.z2 - line.z1);
      const heading = lineHeading(line);
      if (heading !== null) sizes.heading_deg = heading;
    }
    items.push({
      kind: 'truss_lines',
      index,
      name: named(line.name),
      fallbackName: 'Overhead line',
      detail: drawn
        ? `${metres(Math.hypot(line.x2 - line.x1, line.z2 - line.z1))} long, underside ${line.height.toFixed(2)} m up, ${lineRunText(line)}`
        : 'Not drawn: its ends or its height are missing, or it is too short',
      centre: ends ? { x: (line.x1 + line.x2) / 2, z: (line.z1 + line.z2) / 2 } : null,
      sizes,
      drawn,
      suggested: line.suggested !== false,
      marks: marksOf(line),
    });
  });

  (Array.isArray(shell.truss_rings) ? shell.truss_rings : []).forEach((stored: RoomShellRing | null, index) => {
    if (!isObject(stored)) return;
    const ring = stored as unknown as RoomShellRing;
    const drawn = usableRing(ring);
    const centre = isNumber(ring.center_x) && isNumber(ring.center_z) ? { x: ring.center_x, z: ring.center_z } : null;
    items.push({
      kind: 'truss_rings',
      index,
      name: named(ring.name),
      fallbackName: 'Overhead ring',
      detail: drawn
        ? `A ring ${metres(ring.radius * 2)} across, underside ${ring.height.toFixed(2)} m up`
        : 'Not drawn: its size or its height is missing',
      centre,
      sizes: sizesOf(stored, SHELL_SIZE_FIELDS.truss_rings),
      drawn,
      suggested: ring.suggested !== false,
      marks: marksOf(ring),
    });
  });

  return items;
}

/** What an item is called in a sentence: its name, or what it is. */
export function shellItemTitle(item: Pick<ShellItem, 'name' | 'fallbackName'>): string {
  return item.name || item.fallbackName;
}

/** A stable key for a row: the list and the place in it. */
export function shellItemKey(item: Pick<ShellItem, 'kind' | 'index'>): string {
  return `${item.kind}:${item.index}`;
}

/**
 * What the fields of one row hold while it is being edited: text, as typed.
 * A size left out is one the row has not touched.
 */
export interface ShellItemDraft {
  name: string;
  x: string;
  z: string;
  width?: string;
  depth?: string;
  length?: string;
  radius?: string;
  height?: string;
  heading_deg?: string;
}

/** What is sent to change an item. Anything left out is kept. */
export interface ShellItemChanges {
  name?: string;
  center_x?: number;
  center_z?: number;
  width?: number;
  depth?: number;
  length?: number;
  radius?: number;
  height?: number;
  heading_deg?: number;
}

/** A position as a field shows it: to the millimetre, with no trailing noughts and no -0. */
export function positionText(value: number): string {
  return String(Math.round(value * 1000) / 1000 + 0);
}

/** A row's fields as the stored item has them. */
export function draftOf(item: ShellItem): ShellItemDraft {
  const draft: ShellItemDraft = {
    name: item.name,
    x: item.centre ? positionText(item.centre.x) : '',
    z: item.centre ? positionText(item.centre.z) : '',
  };
  for (const field of SHELL_SIZE_FIELDS[item.kind]) {
    const stored = item.sizes[field];
    if (stored !== undefined) draft[field] = positionText(stored);
  }
  return draft;
}

/** A typed number, or null when it is not one. A comma is taken for a decimal point. */
function typedNumber(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/**
 * Why a typed size cannot be sent, or null when it can. The least sizes are
 * checked here; what the room has room for is the server's to say.
 */
export function sizeProblem(kind: ShellItemKind, field: ShellSizeField, value: number | null): string | null {
  const label = SHELL_FIELD_LABELS[field];
  if (field === 'heading_deg') {
    if (value === null) return `${label} must be a number of degrees, such as 45 or -30.`;
    if (Math.abs(value) > SHELL_LIMITS.heading) return `${label} must be between -360 and 360 degrees.`;
    return null;
  }
  const least = field === 'height'
    ? (kind === 'risers' ? SHELL_LIMITS.deck : SHELL_LIMITS.hang)
    : field === 'length' ? SHELL_LIMITS.line
      : field === 'radius' ? SHELL_LIMITS.radius
        : SHELL_LIMITS.side;
  if (value === null) return `${label} must be a number of metres, at least ${least}.`;
  if (value < least) return `${label} must be at least ${least} m.`;
  if (kind === 'risers' && field === 'height' && value > SHELL_LIMITS.deckMost) {
    return `${label} of a raised area can be at most ${SHELL_LIMITS.deckMost} m.`;
  }
  return null;
}

export interface DraftReading {
  /** What to send, or null when the fields say what is already stored. */
  changes: ShellItemChanges | null;
  /** Why the fields cannot be saved as they are, or null when they can. */
  problem: string | null;
}

/**
 * What a row's fields would change on its item. Only what differs from what
 * is stored is sent: a name that was retyped the same, or a number that reads
 * the same to the millimetre, is left out, so a rename never counts as a move
 * and a move never counts as a resize. A problem names the first field that
 * cannot be saved.
 */
export function readDraft(item: ShellItem, draft: ShellItemDraft): DraftReading {
  const changes: ShellItemChanges = {};

  const name = draft.name.split(/\s+/).filter(Boolean).join(' ');
  if (name !== item.name) {
    if (name === '') return { changes: null, problem: 'A name needs at least one letter or number.' };
    if (name.length > SHELL_NAME_MAX) {
      return { changes: null, problem: `A name can be at most ${SHELL_NAME_MAX} characters; this one is ${name.length}.` };
    }
    changes.name = name;
  }

  const before = draftOf(item);

  if (item.centre) {
    for (const [typed, shown, key] of [
      [draft.x, before.x, 'center_x'], [draft.z, before.z, 'center_z'],
    ] as Array<[string, string, 'center_x' | 'center_z']>) {
      if (typed.trim() === shown) continue;
      const value = typedNumber(typed);
      if (value === null) {
        return {
          changes: null,
          problem: `${key === 'center_x' ? 'Across' : 'Depth'} must be a number of metres, such as -1.5.`,
        };
      }
      const stored = key === 'center_x' ? item.centre.x : item.centre.z;
      if (Math.abs(value - stored) >= 0.0005) changes[key] = value;
    }
  }

  for (const field of SHELL_SIZE_FIELDS[item.kind]) {
    const stored = item.sizes[field];
    const typed = draft[field];
    // A size the item has no number for has no field; one the row has not touched is kept.
    if (stored === undefined || typed === undefined || typed.trim() === before[field]) continue;
    const value = typedNumber(typed);
    const problem = sizeProblem(item.kind, field, value);
    if (problem || value === null) return { changes: null, problem };
    if (Math.abs(value - stored) >= (field === 'heading_deg' ? 0.05 : 0.0005)) changes[field] = value;
  }

  return { changes: Object.keys(changes).length > 0 ? changes : null, problem: null };
}

/**
 * A raised area's row turned a quarter turn: its width and its front-to-back
 * change places. A raised area stands square to the room, so this is the only
 * turn it has. The row is then saved like any other change.
 */
export function quarterTurned(item: ShellItem, draft: ShellItemDraft): ShellItemDraft {
  const shown = draftOf(item);
  return { ...draft, width: draft.depth ?? shown.depth, depth: draft.width ?? shown.width };
}

/** How many edits to the room can be undone, and what the next undo takes back. */
export type ShellUndoInfo = RoomShellEdits;

/** The answer to PATCH /api/rigs/{id}/room-shell/{kind}/{index}. */
export interface ShellItemEdited {
  rig_id: number;
  kind: ShellItemKind;
  index: number;
  item: Record<string, unknown>;
  /** The whole stored room after the change. */
  room_shell: RoomShell;
  /** False when what was sent is what was stored: nothing was written and there is no step to undo. */
  changed?: boolean;
  undo?: ShellUndoInfo;
}

/** The answer to DELETE /api/rigs/{id}/room-shell/{kind}/{index}. */
export interface ShellItemDeleted {
  rig_id: number;
  kind: ShellItemKind;
  index: number;
  removed: Record<string, unknown>;
  room_shell: RoomShell;
  undo?: ShellUndoInfo;
  message: string;
}

/** The answer to POST /api/rigs/{id}/room-shell/{kind}. */
export interface ShellItemAdded {
  rig_id: number;
  kind: ShellItemKind;
  /** Its place in its list: the last. */
  index: number;
  item: Record<string, unknown>;
  room_shell: RoomShell;
  undo?: ShellUndoInfo;
  message: string;
}

/** The answer to POST /api/rigs/{id}/room-shell/undo. */
export interface ShellEditUndone {
  rig_id: number;
  /** What was taken back: "Stage renamed". */
  undone: string;
  /** The whole stored room as it was before that edit. */
  room_shell: RoomShell;
  undo: ShellUndoInfo;
  message: string;
}

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/**
 * What a saved change did, in one sentence or two. Where the item ended up is
 * read from the room the server answered with: a position beyond the room is
 * held to 2 m outside its walls, and a resized item is brought in until the
 * whole of it is; the words then say where it was put.
 */
export function editResultText(before: ShellItem, changes: ShellItemChanges, shell: RoomShell): string {
  const after = shellItems(shell).find((item) => item.kind === before.kind && item.index === before.index);
  const title = shellItemTitle(after ?? before);
  const moved = changes.center_x !== undefined || changes.center_z !== undefined;
  const renamed = changes.name !== undefined;
  const resized = SHELL_SIZE_FIELDS[before.kind].some((field) => changes[field] !== undefined);
  const parts: string[] = [];
  if (renamed) parts.push(`${shellItemTitle(before)} is now called ${title}.`);
  if (moved && after?.centre) {
    const held = (changes.center_x !== undefined && Math.abs(after.centre.x - changes.center_x) >= 0.0005)
      || (changes.center_z !== undefined && Math.abs(after.centre.z - changes.center_z) >= 0.0005);
    parts.push(
      `${title} was moved to ${positionText(after.centre.x)}, ${positionText(after.centre.z)}`
      + `${held ? ', as far as the room and 2 m round it allow' : ''}.`,
    );
  }
  if (resized && after) {
    parts.push(`${title} is now ${lowerFirst(after.detail)}.`);
    const shifted = !moved && before.centre && after.centre
      && (Math.abs(after.centre.x - before.centre.x) >= 0.00075 || Math.abs(after.centre.z - before.centre.z) >= 0.00075);
    if (shifted && after.centre) {
      parts.push(
        `Its middle was brought in to ${positionText(after.centre.x)}, ${positionText(after.centre.z)}, `
        + 'to keep the whole of it inside the room and the 2 m round it.',
      );
    }
  }
  if ((moved && after?.centre) || (resized && after)) parts.push('No fixture was moved with it.');
  return parts.join(' ') || `${title} was saved.`;
}

/** What the Delete button asks before anything is taken out. */
export function deleteQuestionText(item: ShellItem): string {
  const overhead = item.kind !== 'risers';
  return `Take ${shellItemTitle(item)} out of the stored room? `
    + (overhead ? 'Fixtures hung on it stay where they are, and nothing will snap to it or be laid along it. ' : '')
    + 'Undo here brings it back, until the scan is read again.';
}

// --- Adding an item by hand --------------------------------------------------

/** What can be added to a room by hand. */
export type NewItemWhat = 'stage' | 'riser' | 'booth' | 'truss_line' | 'truss_ring';

export const NEW_ITEM_CHOICES: Array<{ what: NewItemWhat; label: string }> = [
  { what: 'stage', label: 'Stage' },
  { what: 'riser', label: 'Riser (raised area)' },
  { what: 'booth', label: 'Booth or counter' },
  { what: 'truss_line', label: 'Truss line' },
  { what: 'truss_ring', label: 'Truss ring' },
];

/** The list of the stored room each goes in. */
export function newItemKind(what: NewItemWhat): ShellItemKind {
  if (what === 'truss_line') return 'truss_lines';
  if (what === 'truss_ring') return 'truss_rings';
  return 'risers';
}

/** What the Add form holds: text, as typed. Only the sizes of the chosen kind are read. */
export interface NewItemDraft {
  what: NewItemWhat;
  name: string;
  x: string;
  z: string;
  width: string;
  depth: string;
  length: string;
  radius: string;
  height: string;
  heading_deg: string;
}

/** A height to offer for a new truss: 4 m, or half a metre under a lower ceiling. */
function hangHeight(shell: RoomShell | null | undefined): number {
  const ceiling = shell?.room?.height;
  if (!isNumber(ceiling) || ceiling <= 0) return 4;
  return Math.max(SHELL_LIMITS.hang, Math.min(4, Math.round((ceiling - 0.5) * 10) / 10));
}

/**
 * The Add form as it starts for a kind of item: in the middle of the floor,
 * at a usual size, with no name (the server then calls it what it is).
 */
export function newItemDraft(what: NewItemWhat, shell?: RoomShell | null): NewItemDraft {
  const raised: Record<string, [string, string, string]> = {
    stage: ['4', '3', '0.6'],
    riser: ['2', '2', '0.3'],
    booth: ['2', '1', '1'],
  };
  const [width, depth, deck] = raised[what] ?? raised.riser;
  const overhead = what === 'truss_line' || what === 'truss_ring';
  return {
    what,
    name: '',
    x: '0',
    z: '0',
    width,
    depth,
    length: '6',
    radius: '1.5',
    height: overhead ? positionText(hangHeight(shell)) : deck,
    heading_deg: '0',
  };
}

/** What is sent to add an item: its centre, its sizes, and for a raised area what it is. */
export interface ShellItemAdd extends ShellItemChanges {
  center_x: number;
  center_z: number;
  height: number;
  riser_kind?: 'stage' | 'riser' | 'booth';
}

export interface NewItemReading {
  kind: ShellItemKind;
  /** What to send, or null when a field cannot be sent as it is. */
  body: ShellItemAdd | null;
  problem: string | null;
}

/** What the Add form would add. A problem names the first field that cannot be sent. */
export function readNewItem(draft: NewItemDraft): NewItemReading {
  const kind = newItemKind(draft.what);
  const refuse = (problem: string): NewItemReading => ({ kind, body: null, problem });

  const name = draft.name.split(/\s+/).filter(Boolean).join(' ');
  if (name.length > SHELL_NAME_MAX) {
    return refuse(`A name can be at most ${SHELL_NAME_MAX} characters; this one is ${name.length}.`);
  }
  const x = typedNumber(draft.x);
  if (x === null) return refuse('Across must be a number of metres, such as -1.5.');
  const z = typedNumber(draft.z);
  if (z === null) return refuse('Depth must be a number of metres, such as -1.5.');

  const body: ShellItemAdd = { center_x: x, center_z: z, height: 0 };
  // With no name typed the server calls it what it is: "Stage", "Overhead line 3".
  if (name) body.name = name;
  for (const field of SHELL_SIZE_FIELDS[kind]) {
    const value = typedNumber(draft[field]);
    const problem = sizeProblem(kind, field, value);
    if (problem || value === null) return refuse(problem ?? `${SHELL_FIELD_LABELS[field]} must be a number.`);
    body[field] = value;
  }
  if (kind === 'risers') body.riser_kind = draft.what as 'stage' | 'riser' | 'booth';
  return { kind, body, problem: null };
}

// --- Undo --------------------------------------------------------------------

/** How many edits to a rig's stored room can be undone. */
export function shellUndoCount(info: ShellUndoInfo | null | undefined): number {
  const available = info?.available;
  return isNumber(available) && available > 0 ? Math.floor(available) : 0;
}

/** The Undo button's words: what the next undo takes back, and how many there are after it. */
export function undoButtonText(info: ShellUndoInfo | null | undefined): string {
  const count = shellUndoCount(info);
  if (count === 0) return 'Nothing to undo';
  const label = typeof info?.label === 'string' && info.label.trim() ? info.label.trim() : 'the last room edit';
  return `Undo: ${label}${count > 1 ? ` (${count - 1} more)` : ''}`;
}

/**
 * The message for a refused edit. The server's own words are used wherever it
 * gave any: they say which name is too long, what the room has room for, that
 * the room was changed elsewhere, or that a locate walkthrough is running.
 */
export function shellEditErrorText(status: number | undefined, detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI's validation errors: a list of { msg }.
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === 'string') return first.msg;
  }
  if (status === 404) return 'That part of the room is no longer there. Close this and open it again.';
  if (status === 409) return 'The room cannot be changed just now. Close this and open it again.';
  if (status === 401 || status === 403) return 'Sign in again to edit the room.';
  if (status === undefined) return 'The server could not be reached. Nothing was changed.';
  return 'The room could not be changed. Nothing was stored.';
}
