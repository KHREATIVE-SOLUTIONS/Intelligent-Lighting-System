// Editing a stored room by hand: which of its items can be renamed, moved or
// deleted, what a row of the Edit Room dialog would change, and how the
// dialog words it. Pure, so it can be tested without a server or a screen.
// The server makes the change (backend/app/services/room_scan/edit.py);
// docs/ROOM_SCAN.md describes both.
import type { RoomShell, RoomShellBox, RoomShellLine, RoomShellRing } from '../types';
import { usableBox, usableLine, usableRing } from '../components/rig/previs/roomShell';
import { lineRunText } from './roomScan';

/** The list of the stored shell an item is in: what the server addresses it by. */
export type ShellItemKind = 'risers' | 'truss_lines' | 'truss_rings';

/** The server's own limit on a name (edit.NAME_MAX). */
export const SHELL_NAME_MAX = 60;

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
  /** Whether the 2D and 3D views draw it. One they do not can still be deleted. */
  drawn: boolean;
  /** False once somebody has moved it: it is no longer the scan's guess. */
  suggested: boolean;
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
      drawn,
      suggested: riser.suggested !== false,
    });
  });

  (Array.isArray(shell.truss_lines) ? shell.truss_lines : []).forEach((stored: RoomShellLine | null, index) => {
    if (!isObject(stored)) return;
    const line = stored as unknown as RoomShellLine;
    const drawn = usableLine(line);
    const ends = isNumber(line.x1) && isNumber(line.z1) && isNumber(line.x2) && isNumber(line.z2);
    items.push({
      kind: 'truss_lines',
      index,
      name: named(line.name),
      fallbackName: 'Overhead line',
      detail: drawn
        ? `${metres(Math.hypot(line.x2 - line.x1, line.z2 - line.z1))} long, underside ${line.height.toFixed(2)} m up, ${lineRunText(line)}`
        : 'Not drawn: its ends or its height are missing, or it is too short',
      centre: ends ? { x: (line.x1 + line.x2) / 2, z: (line.z1 + line.z2) / 2 } : null,
      drawn,
      suggested: line.suggested !== false,
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
      drawn,
      suggested: ring.suggested !== false,
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

/** What the fields of one row hold while it is being edited: text, as typed. */
export interface ShellItemDraft {
  name: string;
  x: string;
  z: string;
}

/** What is sent to change an item. Anything left out is kept. */
export interface ShellItemChanges {
  name?: string;
  center_x?: number;
  center_z?: number;
}

/** A position as a field shows it: to the millimetre, with no trailing noughts and no -0. */
export function positionText(value: number): string {
  return String(Math.round(value * 1000) / 1000 + 0);
}

/** A row's fields as the stored item has them. */
export function draftOf(item: ShellItem): ShellItemDraft {
  return {
    name: item.name,
    x: item.centre ? positionText(item.centre.x) : '',
    z: item.centre ? positionText(item.centre.z) : '',
  };
}

/** A typed position in metres, or null when it is not a number. A comma is taken for a decimal point. */
function typedMetres(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

export interface DraftReading {
  /** What to send, or null when the fields say what is already stored. */
  changes: ShellItemChanges | null;
  /** Why the fields cannot be saved as they are, or null when they can. */
  problem: string | null;
}

/**
 * What a row's fields would change on its item. Only what differs from what
 * is stored is sent: a name that was retyped the same, or a position that
 * reads the same to the millimetre, is left out, so a rename never counts as
 * a move. A problem names the first field that cannot be saved.
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

  if (item.centre) {
    const before = draftOf(item);
    for (const [typed, shown, key] of [
      [draft.x, before.x, 'center_x'], [draft.z, before.z, 'center_z'],
    ] as Array<[string, string, 'center_x' | 'center_z']>) {
      if (typed.trim() === shown) continue;
      const value = typedMetres(typed);
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

  return { changes: Object.keys(changes).length > 0 ? changes : null, problem: null };
}

/** The answer to PATCH /api/rigs/{id}/room-shell/{kind}/{index}. */
export interface ShellItemEdited {
  rig_id: number;
  kind: ShellItemKind;
  index: number;
  item: Record<string, unknown>;
  /** The whole stored room after the change. */
  room_shell: RoomShell;
}

/** The answer to DELETE /api/rigs/{id}/room-shell/{kind}/{index}. */
export interface ShellItemDeleted {
  rig_id: number;
  kind: ShellItemKind;
  index: number;
  removed: Record<string, unknown>;
  room_shell: RoomShell;
  message: string;
}

/**
 * What a saved change did, in one sentence. Where the item ended up is read
 * from the room the server answered with: a position beyond the room is held
 * to 2 m outside its walls, and the sentence then says where it was put.
 */
export function editResultText(before: ShellItem, changes: ShellItemChanges, shell: RoomShell): string {
  const after = shellItems(shell).find((item) => item.kind === before.kind && item.index === before.index);
  const title = shellItemTitle(after ?? before);
  const moved = changes.center_x !== undefined || changes.center_z !== undefined;
  const renamed = changes.name !== undefined;
  const parts: string[] = [];
  if (renamed) parts.push(`${shellItemTitle(before)} is now called ${title}.`);
  if (moved && after?.centre) {
    const held = (changes.center_x !== undefined && Math.abs(after.centre.x - changes.center_x) >= 0.0005)
      || (changes.center_z !== undefined && Math.abs(after.centre.z - changes.center_z) >= 0.0005);
    parts.push(
      `${title} was moved to ${positionText(after.centre.x)}, ${positionText(after.centre.z)}`
      + `${held ? ', as far as the room and 2 m round it allow' : ''}. No fixture was moved with it.`,
    );
  }
  return parts.join(' ') || `${title} was saved.`;
}

/** What the Delete button asks before anything is taken out. */
export function deleteQuestionText(item: ShellItem): string {
  const overhead = item.kind !== 'risers';
  return `Take ${shellItemTitle(item)} out of the stored room? `
    + (overhead ? 'Fixtures hung on it stay where they are, and nothing will snap to it or be laid along it. ' : '')
    + 'This cannot be undone here: reading the scan again brings it back, and replaces every other change you have made to the room.';
}

/**
 * The message for a refused edit. The server's own words are used wherever it
 * gave any: they say which name is too long, or that the room was changed
 * elsewhere.
 */
export function shellEditErrorText(status: number | undefined, detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI's validation errors: a list of { msg }.
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === 'string') return first.msg;
  }
  if (status === 404) return 'That part of the room is no longer there. Close this and open it again.';
  if (status === 401 || status === 403) return 'Sign in again to edit the room.';
  if (status === undefined) return 'The server could not be reached. Nothing was changed.';
  return 'The room could not be changed. Nothing was stored.';
}
