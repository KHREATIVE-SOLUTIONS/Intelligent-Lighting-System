// Editing a stored room by hand: which of its items can be renamed, moved,
// resized, raised, turned or deleted, what a row of the Edit Room dialog would
// change, what its form would add, and how the dialog words it. Pure, so it
// can be tested without a server or a screen. The server makes the change
// (backend/app/services/room_scan/edit.py); docs/ROOM_SCAN.md describes both.
import type { RoomShell, RoomShellBox, RoomShellEdits, RoomShellLine, RoomShellRing } from '../types';
import { isDjBooth } from '../components/rig/previs/boothPick';
import { boxHeading, foldHeading, headingText } from '../components/rig/previs/raisedArea';
import { usableBox, usableLine, usableRing } from '../components/rig/previs/roomShellData';
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
  /** How far above the floor a raised area's underside can float (edit.BASE_MAX_M). */
  baseMost: 10,
} as const;

/** What a raised area is. Only the first stage in the list is what a scan's suggestion puts floor lights on. */
export type RiserKind = 'stage' | 'riser' | 'booth';

/** The kinds a raised area's row offers, in the order of its selector. */
export const RISER_KIND_CHOICES: Array<{ kind: RiserKind; label: string }> = [
  { kind: 'stage', label: 'Stage' },
  { kind: 'riser', label: 'Riser' },
  { kind: 'booth', label: 'Booth or counter' },
];

/** What the base height field of a raised area's row is called. */
export const BASE_HEIGHT_LABEL = 'Base height';

/** What the box on a raised area's row that says "this one is the DJ's booth" is called. */
export const DJ_BOOTH_LABEL = 'DJ booth';

/** What that box is called for a screen reader: "DJ booth: Stage". */
export function djBoothBoxName(title: string): string {
  return `${DJ_BOOTH_LABEL}: ${title}`;
}

/** What the heading field of a raised area's row, and of the Add form, is called. */
export const AREA_HEADING_LABEL = 'Heading';

/**
 * The size fields each kind of item has, in the order the dialog shows them.
 * A raised area's heading is not among its own: one that stands square to the
 * room stores none, so its row reads it as it reads the base height
 * (`ShellItem.heading`, `headingShown`).
 */
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
  /**
   * A raised area's underside above the floor: 0 for one that stands on it,
   * or that was stored before a base could be set. Null for a line or a ring.
   */
  baseHeight: number | null;
  /**
   * The heading a raised area stands at, in degrees clockwise from across the
   * room seen from above, over -90 and up to 90: 0 for one that stands square
   * to the room, which stores none. Null for a line or a ring (a line's is in
   * `sizes`).
   */
  heading: number | null;
  /** What a raised area is, or null for a line, a ring, and one stored with no kind the row knows. */
  riserKind: RiserKind | null;
  /**
   * Whether a raised area is marked as the DJ's booth (`is_dj_booth`, slice
   * 28): at most one is. Null for a line or a ring, which cannot be.
   */
  djBooth: boolean | null;
  /** Whether the 2D and 3D views draw it. One they do not can still be deleted. */
  drawn: boolean;
  /** False once somebody has moved, resized or added it: it is no longer the scan's guess. */
  suggested: boolean;
  /** What a person has done to it, for the row's chips: "Added by hand", "Moved by hand", "Resized by hand", "Kind set by hand". */
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

/**
 * What is said after a raised area's top when it does not stand on the floor:
 * ", floating 2.70 m above it". Nothing for one that does.
 */
export function floatingText(base: number | null | undefined): string {
  return isNumber(base) && base > 0 ? `, floating ${base.toFixed(2)} m above it` : '';
}

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
  if (basis.includes('Kind set by hand.')) marks.push('Kind set by hand');
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
  // To a tenth first, so that which side of -90 it falls is not left to the last bit of a float.
  let degrees = Math.round(((Math.atan2(runZ, runX) * 180) / Math.PI) * 10) / 10;
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
    const base = isNumber(riser.base_height) && riser.base_height > 0 ? riser.base_height : 0;
    const heading = boxHeading(riser);
    items.push({
      kind: 'risers',
      index,
      name: named(riser.name),
      fallbackName: KIND_WORDS[riser.kind ?? 'riser'] ?? 'Raised area',
      detail: drawn
        ? `${metres(riser.width)} by ${metres(riser.depth)}${headingText(heading)}, `
          + `top ${(base + riser.height).toFixed(2)} m above the floor${floatingText(base)}`
        : 'Not drawn: its size is missing',
      centre,
      sizes: sizesOf(stored, SHELL_SIZE_FIELDS.risers),
      baseHeight: base,
      heading,
      riserKind: riser.kind === 'stage' || riser.kind === 'riser' || riser.kind === 'booth' ? riser.kind : null,
      djBooth: isDjBooth(riser),
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
      baseHeight: null,
      heading: null,
      riserKind: null,
      djBooth: null,
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
      baseHeight: null,
      heading: null,
      riserKind: null,
      djBooth: null,
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
  /**
   * A line's heading, as typed. A raised area's too, but left out until its
   * row's field is touched: it then shows what is stored, as the base does.
   */
  heading_deg?: string;
  /** A raised area's base height, as typed. Left out until the row's field is touched: it then shows what is stored. */
  base_height?: string;
  /** What a raised area is to be, as chosen. Left out until the row's selector is touched. */
  riser_kind?: string;
  /** Whether a raised area is to be the DJ's booth, as ticked. Left out until the row's box is touched. */
  is_dj_booth?: boolean;
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
  /** A raised area's underside above the floor, in metres: 0 stands on it. */
  base_height?: number;
  /** What a raised area is to be. Its place in the list is kept. */
  riser_kind?: RiserKind;
  /**
   * Whether a raised area is the DJ's booth. True takes the mark off every
   * other one; a change of kind sent without it takes it off this one.
   */
  is_dj_booth?: boolean;
  /**
   * Whether the fixtures hung on a line or ring, or standing on a raised
   * area, go with it when it is moved, raised, turned or resized. Left out,
   * the server takes them along.
   */
  carry_fixtures?: boolean;
}

/**
 * Whether fixtures go with this kind of item: they hang on a truss line or a
 * ring, and since slice 18 they stand on a raised area.
 */
export function carriesFixtures(kind: ShellItemKind): boolean {
  return kind === 'truss_lines' || kind === 'truss_rings' || kind === 'risers';
}

/** Whether fixtures stand on this kind of item (a raised area) rather than hang on it. */
export function stoodOn(kind: ShellItemKind): boolean {
  return kind === 'risers';
}

/** The label of the box that says whether a truss takes its fixtures along. */
export const CARRY_LABEL = 'Move the fixtures hung on it';

/** The same box on a raised area's row. */
export const CARRY_STANDING_LABEL = 'Move the fixtures standing on it';

/** The label of a row's box: fixtures hang on a truss and stand on a raised area. */
export function carryLabel(kind: ShellItemKind): string {
  return stoodOn(kind) ? CARRY_STANDING_LABEL : CARRY_LABEL;
}

/** What the box is called for a screen reader: "Move the fixtures standing on Stage". */
export function carryBoxName(kind: ShellItemKind, title: string): string {
  return `Move the fixtures ${stoodOn(kind) ? 'standing' : 'hung'} on ${title}`;
}

/**
 * What is sent for a row's changes, with whether its fixtures go along. The
 * flag goes only with a change that could move one: an item whose place,
 * size, height, base or heading changes. A rename, a change of what a
 * raised area is and the DJ booth mark are sent as they were.
 */
export function withCarry(item: Pick<ShellItem, 'kind'>, changes: ShellItemChanges, carry: boolean): ShellItemChanges {
  const reshapes = Object.keys(changes).some(
    (key) => key !== 'name' && key !== 'carry_fixtures' && key !== 'riser_kind' && key !== 'is_dj_booth',
  );
  return carriesFixtures(item.kind) && reshapes ? { ...changes, carry_fixtures: carry } : changes;
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

  // A raised area's base and kind are in the draft only once the row's field or selector was touched.
  if (item.kind === 'risers' && item.baseHeight !== null && draft.base_height !== undefined
    && draft.base_height.trim() !== positionText(item.baseHeight)) {
    const value = typedNumber(draft.base_height);
    const problem = baseHeightProblem(value);
    if (problem || value === null) return { changes: null, problem };
    if (Math.abs(value - item.baseHeight) >= 0.0005) changes.base_height = value;
  }
  // Its heading the same way. What is typed is sent as typed, and the server folds it: a rectangle
  // looks the same after half a turn, so 135 is stored as -45, and 180 on one that stands square
  // is no change at all.
  if (item.kind === 'risers' && item.heading !== null && draft.heading_deg !== undefined
    && draft.heading_deg.trim() !== positionText(item.heading)) {
    const value = typedNumber(draft.heading_deg);
    const problem = sizeProblem(item.kind, 'heading_deg', value);
    if (problem || value === null) return { changes: null, problem };
    if (Math.abs((foldHeading(value) ?? value) - item.heading) >= 0.05) changes.heading_deg = value;
  }
  if (item.kind === 'risers' && draft.riser_kind !== undefined && draft.riser_kind !== (item.riserKind ?? '')) {
    const chosen = RISER_KIND_CHOICES.find((choice) => choice.kind === draft.riser_kind);
    if (!chosen) return { changes: null, problem: 'A raised area is a stage, a riser or a booth.' };
    changes.riser_kind = chosen.kind;
  }
  // The DJ booth box the same way: in the draft only once it was touched, and sent only when it
  // differs from what is stored.
  if (item.kind === 'risers' && item.djBooth !== null) {
    const ticked = djBoothShown(item, draft);
    if (ticked !== item.djBooth) changes.is_dj_booth = ticked;
    // The server takes the mark off a raised area made another kind unless the request says it is
    // still the booth. The row shows the box ticked, so it says so.
    else if (ticked && changes.riser_kind !== undefined) changes.is_dj_booth = true;
  }

  return { changes: Object.keys(changes).length > 0 ? changes : null, problem: null };
}

/**
 * Why a typed base height cannot be sent, or null when it can: a number of
 * metres from 0 (standing on the floor) to 10. Whether the top then fits
 * under the ceiling is the server's to say.
 */
export function baseHeightProblem(value: number | null): string | null {
  if (value === null || value < 0 || value > SHELL_LIMITS.baseMost) {
    return `${BASE_HEIGHT_LABEL} must be a number of metres from 0 (on the floor) to ${SHELL_LIMITS.baseMost}.`;
  }
  return null;
}

/** What a row's base height field shows: what was typed, or what is stored. '' for a line or a ring. */
export function baseHeightShown(item: ShellItem, draft: ShellItemDraft): string {
  return draft.base_height ?? (item.baseHeight === null ? '' : positionText(item.baseHeight));
}

/** What a raised area's heading field shows: what was typed, or what is stored. '' for a line or a ring. */
export function headingShown(item: ShellItem, draft: ShellItemDraft): string {
  return draft.heading_deg ?? (item.heading === null ? '' : positionText(item.heading));
}

/** What a row's kind selector shows: what was chosen, or what is stored. '' when it has no kind the row knows. */
export function riserKindShown(item: ShellItem, draft: ShellItemDraft): string {
  return draft.riser_kind ?? item.riserKind ?? '';
}

/** Whether a row's DJ booth box is ticked: as it was last set, or as stored. False for a line or a ring. */
export function djBoothShown(item: ShellItem, draft: ShellItemDraft): boolean {
  return draft.is_dj_booth ?? item.djBooth === true;
}

/**
 * A raised area's row turned a quarter turn: its width and its front-to-back
 * change places, and its heading is left as it is. Any other turn is its
 * heading field (slice 21). The row is then saved like any other change.
 */
export function quarterTurned(item: ShellItem, draft: ShellItemDraft): ShellItemDraft {
  const shown = draftOf(item);
  return { ...draft, width: draft.depth ?? shown.depth, depth: draft.width ?? shown.width };
}

/** How many edits to the room can be undone, and what the next undo takes back. */
export type ShellUndoInfo = RoomShellEdits;

/** Where a fixture is and which way it is turned, as a carried move records it. */
export interface CarriedPlace {
  x: number;
  y: number;
  z: number;
  rotation_y?: number | null;
}

/** One fixture that went with its truss, or went back with it. */
export interface CarriedFixture {
  rig_fixture_id: number;
  name: string;
  from: CarriedPlace;
  to: CarriedPlace;
}

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
  /** For a raised area: what it now is. Null for a line or a ring. */
  riser_kind?: string | null;
  /** The place in `risers` of the room's first stage, which a scan's suggestion puts floor lights on; null with none. */
  first_stage?: number | null;
  /** Whether the fixtures hung on it, or standing on it, were to go with it. */
  carry_fixtures?: boolean;
  /**
   * The fixtures hung on a line or ring, or standing on a raised area, that
   * moved with it. The rig's positions are stale once this is not empty.
   */
  fixtures_moved?: CarriedFixture[];
  /**
   * The other raised areas that stood on a moved, raised or turned raised
   * area and went with it (a riser on a stage). `room_shell` has them where
   * they went; the fixtures standing on them are in `fixtures_moved`.
   */
  items_moved?: CarriedArea[];
  message?: string;
}

/** Where a raised area is and how big: its middle, its sides and its base. */
export interface CarriedAreaPlace {
  center_x: number;
  center_z: number;
  width: number;
  depth: number;
  base_height: number;
}

/** One raised area that went with the raised area it stands on. */
export interface CarriedArea {
  kind: 'risers';
  /** Its place in the stored list, from 0. */
  index: number;
  name: string;
  from: CarriedAreaPlace;
  to: CarriedAreaPlace;
}

/** How many fixtures an answer says moved: with their truss, or back with it. */
export function carriedCount(list: unknown): number {
  return Array.isArray(list) ? list.length : 0;
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
  /** The fixtures the undone edit had carried with a truss, put back. The rig's positions are stale once this is not empty. */
  fixtures_restored?: CarriedFixture[];
  /** The ones left where they are, because they were moved since or are no longer in the rig. */
  fixtures_skipped?: Array<{ rig_fixture_id: number; name: string; reason: string }>;
  /**
   * What the walls, as they are again, leave outside them: an undone change
   * to the walls changes that (utils/roomWallsEdit.ts `OutsideReport`).
   */
  outside?: {
    items: Array<{ kind: ShellItemKind; index: number; name: string; reason: string; already_outside?: boolean }>;
    fixtures: Array<{ rig_fixture_id: number; name: string; reason: string; already_outside?: boolean }>;
    count: number;
  };
  message: string;
}

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/**
 * What a saved change did, in one sentence or two. Where the item ended up is
 * read from the room the server answered with: a position beyond the room is
 * held to 2 m outside its walls, and a resized item is brought in until the
 * whole of it is; the words then say where it was put.
 *
 * `carried` is what became of the fixtures hung on a line or ring: how many
 * the server said moved with it, and whether they were asked to. Left out,
 * none did. Its `areas` is how many raised areas standing on a raised area
 * went with it.
 */
export function editResultText(
  before: ShellItem,
  changes: ShellItemChanges,
  shell: RoomShell,
  carried?: Carried,
): string {
  const after = shellItems(shell).find((item) => item.kind === before.kind && item.index === before.index);
  const title = shellItemTitle(after ?? before);
  const moved = changes.center_x !== undefined || changes.center_z !== undefined;
  const renamed = changes.name !== undefined;
  // A raised area's heading is not among its size fields, and a turn is told as a resize is.
  const resized = SHELL_SIZE_FIELDS[before.kind].some((field) => changes[field] !== undefined)
    || changes.base_height !== undefined || changes.heading_deg !== undefined;
  const parts: string[] = [];
  if (renamed) parts.push(`${shellItemTitle(before)} is now called ${title}.`);
  if (changes.riser_kind !== undefined) {
    const now = RISER_KIND_CHOICES.find((choice) => choice.kind === changes.riser_kind);
    // One the server renamed with its kind ("Riser" to "Stage") is named as it was, or the sentence says nothing.
    parts.push(`${renamed ? title : shellItemTitle(before)} is now a ${(now?.label ?? changes.riser_kind).toLowerCase()}.`);
  }
  // Said only where the mark changed: a change of kind that carries the mark it already had says nothing of it.
  if (changes.is_dj_booth !== undefined && before.djBooth !== null && changes.is_dj_booth !== before.djBooth) {
    parts.push(changes.is_dj_booth
      ? `${title} is now the DJ booth: the 3D view puts the decks and the DJ there, and its DJ and Floor cameras look at it.`
      : `${title} is no longer marked as the DJ booth.`);
  }
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
  if ((moved && after?.centre) || (resized && after)) parts.push(carriedText(before.kind, carried));
  return parts.join(' ') || `${title} was saved.`;
}

/**
 * What became of the fixtures hung on a changed line or ring, or standing on
 * a changed raised area, in a sentence: the moved-count notice.
 */
export function carriedText(kind: ShellItemKind, carried?: Carried): string {
  const stack = stackedText(kind, carried?.areas);
  if (carried && carriesFixtures(kind)) {
    const how = stoodOn(kind) ? 'standing on' : 'hung on';
    if (carried.moved > 0) {
      // With a stack carried, some of them stood on what stands on it.
      const where = stack ? `${how} it, or on what stands on it,` : `${how} it`;
      return `${carried.moved} fixture${carried.moved === 1 ? '' : 's'} ${where} moved with it.${stack}`;
    }
    if (!carried.asked) return `The fixtures ${how} it were left where they are.`;
  }
  return `No fixture was moved with it.${stack}`;
}

/** What became of what an item carries: how many fixtures moved, whether they were asked to, and how many raised areas. */
export interface Carried {
  moved: number;
  asked: boolean;
  /** How many raised areas standing on a raised area went with it. Left out, none. */
  areas?: number;
}

/**
 * The sentence for the raised areas that went with the one they stand on,
 * with a space before it: " 1 raised area standing on it moved with it too."
 * Nothing for none, and for a line or a ring, which nothing stands on.
 */
export function stackedText(kind: ShellItemKind, areas: number | undefined): string {
  if (!stoodOn(kind) || !areas || areas <= 0) return '';
  return ` ${areas} raised area${areas === 1 ? '' : 's'} standing on it moved with it too.`;
}

/** What the delete question says of an item the scan read: the room remembers the delete (slices 33 and 34). */
export const DELETE_STAYS_OUT_TEXT =
  'It stays deleted when the scan is applied again. Undo here brings it back, until then.';
/** What it says of one added by hand: the scan never read it, so there is nothing for a scan to bring back. */
export const DELETE_ADDED_TEXT = 'Undo here brings it back, until the scan is read again.';

/**
 * What the Delete button asks before anything is taken out. An item the scan
 * read (a raised area, a line or a ring) stays deleted when the scan is
 * applied again; the room's Undo brings it back, for as long as the delete is
 * among its steps (an applied scan empties them).
 */
export function deleteQuestionText(item: ShellItem): string {
  const overhead = item.kind !== 'risers';
  return `Take ${shellItemTitle(item)} out of the stored room? `
    + (overhead
      ? 'Fixtures hung on it stay where they are, and nothing will snap to it or be laid along it. '
      : 'Fixtures standing on it stay where they are. ')
    + (item.marks.includes('Added by hand') ? DELETE_ADDED_TEXT : DELETE_STAYS_OUT_TEXT);
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
  /**
   * A line's heading, and a raised area's: degrees clockwise from across the
   * room seen from above. '0' runs across it, or stands square to it, and for
   * a raised area so does an empty field. Not read for a ring.
   */
  heading_deg: string;
  /**
   * A raised area's base height: how far its underside is above the floor.
   * '0' stands on it, and so does an empty field. Not read for a truss.
   */
  base_height: string;
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
    base_height: '0',
  };
}

/** What is sent to add an item: its centre, its sizes, and for a raised area what it is. */
export interface ShellItemAdd extends ShellItemChanges {
  center_x: number;
  center_z: number;
  height: number;
  riser_kind?: 'stage' | 'riser' | 'booth';
  // The Add form has no DJ booth box: a new raised area is marked on its row once it is in the room.
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
  if (kind === 'risers') {
    body.riser_kind = draft.what as 'stage' | 'riser' | 'booth';
    // An empty field stands on the floor, as 0 does; the server takes one left out the same way,
    // so only a platform that floats says so.
    const typed = draft.base_height ?? '';
    const base = typed.trim() === '' ? 0 : typedNumber(typed);
    const problem = baseHeightProblem(base);
    if (problem || base === null) return refuse(problem ?? `${BASE_HEIGHT_LABEL} must be a number.`);
    if (base >= 0.0005) body.base_height = base;
    // Its heading the same way: an empty field stands square to the room, as 0 does, and only one
    // that is turned says so. The server folds what is sent (135 is stored as -45).
    const turnTyped = draft.heading_deg ?? '';
    const turn = turnTyped.trim() === '' ? 0 : typedNumber(turnTyped);
    const turnProblem = sizeProblem(kind, 'heading_deg', turn);
    if (turnProblem || turn === null) return refuse(turnProblem ?? `${AREA_HEADING_LABEL} must be a number.`);
    if (Math.abs(foldHeading(turn) ?? turn) >= 0.05) body.heading_deg = turn;
  }
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
