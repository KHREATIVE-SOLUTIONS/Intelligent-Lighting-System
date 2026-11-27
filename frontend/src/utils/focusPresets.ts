/**
 * Focus presets in the app (docs/FOCUS_PRESETS.md, "In the app"): the table
 * GET /api/rigs/{id}/focus-presets answers, read defensively; a custom target
 * as typed, checked the way the server checks it; and which marker the 3D view
 * draws for a target. Pure: no requests, no DOM.
 *
 * Coordinates are the rig's stage axes in metres, the same the 3D view draws
 * in: X across, Y up from the floor, -Z upstage, +Z downstage.
 */

export type Vec3 = [number, number, number];

/** point: every head on one point. line: heads spread along it. below: the floor under each head. */
export type FocusTargetKind = 'point' | 'line' | 'below';

export interface FocusUnreachable {
  fixture_id: number;
  name: string;
  reason: string;
}

export interface FocusTarget {
  key: string;
  name: string;
  kind: FocusTargetKind;
  /** Where the point came from, in words. */
  source: string;
  point: Vec3 | null;
  line: [Vec3, Vec3] | null;
  custom: boolean;
  /** Why the room could not place it; empty when it was placed. */
  skipped: string;
  reachable_count: number;
  unreachable: FocusUnreachable[];
  /** The stored id of a custom target (from its `custom_<id>` key); null for a default one. */
  customId: number | null;
}

export interface FocusLeftOut {
  fixture_id: number;
  name: string;
  reason: string;
}

export interface FocusTable {
  rigId: number | null;
  /** How many moving heads the table aims. */
  heads: number;
  leftOut: FocusLeftOut[];
  targets: FocusTarget[];
  /** How many custom targets the rig keeps. */
  customCount: number;
}

// The server's limits (backend/app/services/focus_presets/targets.py).
export const MAX_CUSTOM_TARGETS = 50;
export const MAX_NAME_LENGTH = 60;
export const MAX_COORD_M = 500;

export const focusPresetsPath = (rigId: number) => `/rigs/${rigId}/focus-presets`;
export const focusPresetsCsvPath = (rigId: number) => `/rigs/${rigId}/focus-presets.csv`;
export const focusTargetsPath = (rigId: number) => `/rigs/${rigId}/focus-presets/targets`;
export const focusTargetPath = (rigId: number, targetId: number) => `/rigs/${rigId}/focus-presets/targets/${targetId}`;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

function vec3(value: unknown): Vec3 | null {
  if (!Array.isArray(value) || value.length !== 3) return null;
  const [x, y, z] = value as unknown[];
  return finite(x) && finite(y) && finite(z) ? [x, y, z] : null;
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

/** The id in a `custom_<id>` key, or null. */
export function customIdFromKey(key: string): number | null {
  const match = /^custom_(\d+)$/.exec(key);
  return match ? Number(match[1]) : null;
}

function readFixtureList(value: unknown): FocusUnreachable[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((item) => ({
    fixture_id: finite(item.fixture_id) ? item.fixture_id : 0,
    name: text(item.name),
    reason: text(item.reason),
  }));
}

function readTarget(raw: Record<string, unknown>): FocusTarget | null {
  const key = text(raw.key);
  if (!key) return null;
  const kind: FocusTargetKind = raw.kind === 'line' ? 'line' : raw.kind === 'below' ? 'below' : 'point';
  const ends: unknown[] = Array.isArray(raw.line) && raw.line.length === 2 ? raw.line : [];
  const lineA = ends.length === 2 ? vec3(ends[0]) : null;
  const lineB = ends.length === 2 ? vec3(ends[1]) : null;
  const custom = raw.custom === true;
  return {
    key,
    name: text(raw.name) || key,
    kind,
    source: text(raw.source),
    point: vec3(raw.point),
    line: lineA && lineB ? [lineA, lineB] : null,
    custom,
    skipped: text(raw.skipped),
    reachable_count: finite(raw.reachable_count) ? raw.reachable_count : 0,
    unreachable: readFixtureList(raw.unreachable),
    customId: custom ? customIdFromKey(key) : null,
  };
}

/** The table as the panel and the 3D view use it. Anything malformed is left out, never thrown on. */
export function parseFocusPresets(raw: unknown): FocusTable {
  const data = isRecord(raw) ? raw : {};
  const targets = Array.isArray(data.targets)
    ? data.targets.filter(isRecord).map(readTarget).filter((t): t is FocusTarget => t !== null)
    : [];
  return {
    rigId: finite(data.rig_id) ? data.rig_id : null,
    heads: finite(data.heads) ? data.heads : 0,
    leftOut: readFixtureList(data.left_out),
    targets,
    customCount: Array.isArray(data.custom_targets) ? data.custom_targets.length : targets.filter((t) => t.custom).length,
  };
}

// ---------------------------------------------------------------------------
// A custom target as typed
// ---------------------------------------------------------------------------

export interface TargetDraft {
  name: string;
  x: string;
  y: string;
  z: string;
}

export const EMPTY_DRAFT: TargetDraft = { name: '', x: '', y: '', z: '' };

export interface NewTarget {
  name: string;
  x: number;
  y: number;
  z: number;
}

/** One sentence per field that is wrong; `form` for what is wrong with adding one at all. */
export type DraftErrors = Partial<Record<keyof TargetDraft | 'form', string>>;

export type DraftCheck = { ok: true; target: NewTarget } | { ok: false; errors: DraftErrors };

/** A typed number of metres: a comma is taken as the decimal point. NaN when it is not one. */
export function metres(typed: string): number {
  const cleaned = typed.trim().replace(',', '.');
  // Number('') is 0, and Number('0x10') is 16: neither is a number of metres somebody typed.
  if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(cleaned)) return Number.NaN;
  return Number(cleaned);
}

/**
 * The draft as the server takes it (real numbers, the name's spaces collapsed),
 * or a plain sentence for each field that is wrong. The same limits the server
 * holds to, so a 422 is not the first a person hears of it.
 */
export function checkDraft(draft: TargetDraft, customCount = 0): DraftCheck {
  const errors: DraftErrors = {};
  const name = draft.name.split(/\s+/).filter(Boolean).join(' ');
  if (!name) errors.name = 'Give the target a name.';
  else if (name.length > MAX_NAME_LENGTH) errors.name = `A target's name is at most ${MAX_NAME_LENGTH} characters.`;
  if (customCount >= MAX_CUSTOM_TARGETS) {
    errors.form = `A rig keeps at most ${MAX_CUSTOM_TARGETS} custom targets. Remove one first.`;
  }

  const values: Partial<Record<'x' | 'y' | 'z', number>> = {};
  for (const axis of ['x', 'y', 'z'] as const) {
    const typed = draft[axis];
    if (!typed.trim()) {
      errors[axis] = `Give ${axis} in metres.`;
      continue;
    }
    const value = metres(typed);
    if (!Number.isFinite(value)) errors[axis] = `${axis} must be a number of metres, like 1.5 or -2.`;
    else if (Math.abs(value) > MAX_COORD_M) errors[axis] = `${axis} is at most ${MAX_COORD_M} m from the middle of the room.`;
    else if (axis === 'y' && value < 0) errors[axis] = 'y is height above the floor and cannot be below it.';
    else values[axis] = value;
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, target: { name, x: values.x as number, y: values.y as number, z: values.z as number } };
}

// ---------------------------------------------------------------------------
// In words
// ---------------------------------------------------------------------------

const metresText = (value: number) => {
  const rounded = Math.round(value * 100) / 100;
  return String(Object.is(rounded, -0) ? 0 : rounded);
};

export const pointText = (p: Vec3) => `x ${metresText(p[0])}, y ${metresText(p[1])}, z ${metresText(p[2])} m`;

/** Where the target is, in a line of text. */
export function whereText(target: FocusTarget): string {
  if (target.skipped) return 'Not placed.';
  if (target.kind === 'below') return 'The floor under each head.';
  if (target.kind === 'line' && target.line) {
    return `A line from ${pointText(target.line[0])} to ${pointText(target.line[1])}, the heads spread along it.`;
  }
  return target.point ? pointText(target.point) : 'Not placed.';
}

/** How many heads reach it, in a sentence. */
export function reachText(target: FocusTarget, heads: number): string {
  if (target.skipped) return 'No preset: the room cannot place it yet.';
  if (heads <= 0) return 'No moving heads to aim at it.';
  const reach = target.reachable_count;
  if (reach >= heads) return heads === 1 ? 'The moving head can reach it.' : `All ${heads} moving heads can reach it.`;
  if (reach === 0) return heads === 1 ? 'The moving head cannot reach it.' : `None of the ${heads} moving heads can reach it.`;
  return `${reach} of ${heads} moving heads can reach it.`;
}

// ---------------------------------------------------------------------------
// In the 3D view
// ---------------------------------------------------------------------------

/** all: every head reaches it. some: some cannot. none: no head can. idle: there are no heads to aim. */
export type MarkerStyle = 'all' | 'some' | 'none' | 'idle';

export interface FocusMarker {
  key: string;
  name: string;
  style: MarkerStyle;
  /** Where the marker stands. */
  at: Vec3;
  /** The audience line's two ends, drawn as a bar between them. */
  line: [Vec3, Vec3] | null;
}

export function markerStyle(target: FocusTarget, heads: number): MarkerStyle {
  if (heads <= 0) return 'idle';
  if (target.reachable_count <= 0) return 'none';
  return target.unreachable.length > 0 || target.reachable_count < heads ? 'some' : 'all';
}

/**
 * One marker per target that is one place in the room: a point at its point,
 * a line at its middle (with the line drawn). "Straight down" is a different
 * place under every head, and a skipped target is no place, so neither gets one.
 */
export function focusMarkers(table: FocusTable | null): FocusMarker[] {
  if (!table) return [];
  const out: FocusMarker[] = [];
  for (const target of table.targets) {
    if (target.skipped) continue;
    const style = markerStyle(target, table.heads);
    if (target.kind === 'point' && target.point) {
      out.push({ key: target.key, name: target.name, style, at: target.point, line: null });
    } else if (target.kind === 'line' && target.line) {
      const [a, b] = target.line;
      const mid: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
      out.push({ key: target.key, name: target.name, style, at: mid, line: target.line });
    }
  }
  return out;
}

/** The localStorage key of the "Show focus targets in 3D" choice for a rig. */
export const focusTargets3dKey = (rigId: number) => `focusTargets3d:${rigId}`;

/** The operator's choice for a rig, or null when they have made none. */
export function readFocusTargets3dChoice(rigId: number): boolean | null {
  try {
    const stored = window.localStorage.getItem(focusTargets3dKey(rigId));
    return stored === 'on' ? true : stored === 'off' ? false : null;
  } catch {
    return null;
  }
}

export function writeFocusTargets3dChoice(rigId: number, on: boolean): void {
  try {
    window.localStorage.setItem(focusTargets3dKey(rigId), on ? 'on' : 'off');
  } catch {
    // Private mode or a full store: the choice holds for this visit only.
  }
}
