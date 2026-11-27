/**
 * Venue readiness: what GET /api/rigs/{id}/readiness answers and the few
 * words the panel puts around it. The backend writes every sentence; this
 * file only orders, counts and labels. See docs/READINESS.md.
 */

export type ReadinessStatus = 'ok' | 'warn' | 'fail';

export interface ReadinessCheck {
  id: string;
  title: string;
  status: ReadinessStatus;
  message: string;
  /** The first 50 fixtures the check is about; `fixture_count` has them all. */
  fixture_ids: number[];
  fixture_count: number;
  /** The fix the backend offers for this check, e.g. "auto-groups". */
  fix: string | null;
}

export interface ReadinessReport {
  rig_id: number;
  rig_name: string;
  status: ReadinessStatus;
  counts: Record<ReadinessStatus, number>;
  checks: ReadinessCheck[];
  operator_guide: string;
}

/** What Undo would take back: the last fix that changed the rig. */
export interface ReadinessUndo {
  fix: string;
  /** "Undo Make groups", "Undo Re-address". */
  label: string;
  count: number;
}

export interface UndoFixResult {
  rig_id: number;
  /** The fix taken back; null when there was nothing to undo. */
  fix: string | null;
  restored: { id: number; name: string; from: Record<string, unknown>; to: Record<string, unknown> }[];
  undo: null;
  message: string;
}

export interface AutoGroupsResult {
  rig_id: number;
  created: { name: string; fixture_ids: number[] }[];
  /** Groups of exactly the name Make groups writes that ungrouped fixtures joined. */
  added?: { name: string; fixture_ids: number[] }[];
  skipped: { name: string; fixture_ids: number[] }[];
  unplaced_ids: number[];
  changed: { id: number; name: string; group_before: string | null; group_name: string }[];
  /** The rig's undo after this call: this fix if it changed something, else the one before (or null). */
  undo?: ReadinessUndo | null;
  message: string;
}

export interface ReaddressMove {
  id: number;
  name: string;
  reason: 'overlap' | 'past_end';
  clashes_with: number[];
  channel_count: number;
  /** The fixture has no DMX mode: the footprint is a guess and so may the clash be. */
  guessed: boolean;
  from_universe: number;
  from_address: number;
  to_universe: number;
  to_address: number;
  /** "4.337": universe counted from 1, then the address. */
  from_label: string;
  to_label: string;
}

export interface ReaddressResult {
  rig_id: number;
  dry_run: boolean;
  moves: ReaddressMove[];
  /** Fixtures that clash but were not moved (address locked, or no room), each with its reason. */
  left: { id: number; name: string; reason: string; clashes_with: number[]; message: string }[];
  conflicts_after: number;
  past_end_after: number;
  undo?: ReadinessUndo | null;
  message: string;
}

export interface ModeChoice {
  id: number;
  name: string;
  channel_count: number;
}

interface SetModesFixture {
  id: number;
  name: string;
  /** "guessed": it has no mode; "foreign": its mode is not one of its profile's. */
  problem: 'guessed' | 'foreign';
  mode_id_before: number | null;
  mode_name_before: string | null;
  /** The footprint the addresses check counts now (16 when it is guessed). */
  channel_count_before: number;
}

export interface SetModesProposal extends SetModesFixture {
  /** Why this mode and no other: the profile's only one, or the one of that many channels. */
  reason: 'only_mode' | 'footprint' | 'address_span';
  mode_id: number;
  mode_name: string;
  channel_count: number;
}

export interface SetModesByHand extends SetModesFixture {
  candidates: ModeChoice[];
  why: string;
}

export interface SetModesResult {
  rig_id: number;
  dry_run: boolean;
  proposals: SetModesProposal[];
  /** Fixtures with more than one possible mode, or none: never changed. */
  by_hand: SetModesByHand[];
  /** Overlaps or runs past 512 the new footprints make. No address is moved. */
  clashes: { kind: 'overlap' | 'past_end'; fixture_ids: number[]; names: string[]; message: string }[];
  undo?: ReadinessUndo | null;
  message: string;
}

export const FIX_AUTO_GROUPS = 'auto-groups';
export const FIX_READDRESS = 'readdress';
export const FIX_SET_MODES = 'set-modes';
export const FIX_LOCATE = 'locate';

export const readinessPath = (rigId: number) => `/rigs/${rigId}/readiness`;
export const autoGroupsPath = (rigId: number) => `/rigs/${rigId}/readiness/fix/auto-groups`;
export const readdressPath = (rigId: number) => `/rigs/${rigId}/readiness/fix/readdress`;
export const setModesPath = (rigId: number) => `/rigs/${rigId}/readiness/fix/set-modes`;
export const undoFixPath = (rigId: number) => `/rigs/${rigId}/readiness/fix/undo`;

/** "only mode", "matches its 24ch footprint": why Set modes chose this mode. */
export function modeReasonText(p: SetModesProposal): string {
  if (p.reason === 'only_mode') return "the profile's only mode";
  if (p.reason === 'footprint') return `the only mode of its present ${p.channel_count}ch footprint`;
  return `the only mode that fills its ${p.channel_count}-channel address span`;
}

const RANK: Record<ReadinessStatus, number> = { fail: 0, warn: 1, ok: 2 };

/** Failures first, then warnings, then the checks that passed; the backend's order within each. */
export function sortedChecks(checks: ReadinessCheck[]): ReadinessCheck[] {
  return checks
    .map((check, index) => ({ check, index }))
    .sort((a, b) => RANK[a.check.status] - RANK[b.check.status] || a.index - b.index)
    .map(({ check }) => check);
}

/** The one line at the top of the panel. */
export function headline(report: ReadinessReport): string {
  const { fail = 0, warn = 0 } = report.counts;
  if (report.status === 'ok') return 'Ready to program: every check passed.';
  const parts: string[] = [];
  if (fail) parts.push(`${fail} ${fail === 1 ? 'check fails' : 'checks fail'}`);
  if (warn) parts.push(`${warn} ${warn === 1 ? 'check warns' : 'checks warn'}`);
  return report.status === 'fail'
    ? `Not ready: ${parts.join(', ')}. Fix the failures before programming.`
    : `Ready with warnings: ${parts.join(', ')}.`;
}

/** "3 fixtures", or "50 of 60 fixtures shown" when the backend capped the list. */
export function fixturesText(check: ReadinessCheck): string {
  const n = check.fixture_count;
  if (n === 0) return '';
  const noun = n === 1 ? 'fixture' : 'fixtures';
  return check.fixture_ids.length < n ? `${n} ${noun} (first ${check.fixture_ids.length} listed)` : `${n} ${noun}`;
}

export const FIX_LABELS: Record<string, string> = {
  [FIX_AUTO_GROUPS]: 'Make groups',
  [FIX_READDRESS]: 'Re-address',
  [FIX_SET_MODES]: 'Set modes',
  [FIX_LOCATE]: 'Locate these',
};

/** "Locate these", or "Locate the first 50" when the backend capped the list. */
export function locateLabel(check: ReadinessCheck): string {
  return check.fixture_ids.length < check.fixture_count
    ? `Locate the first ${check.fixture_ids.length}`
    : FIX_LABELS[FIX_LOCATE];
}

/** The short line the export dialogs show: overall status and how many checks warn or fail. */
export function exportSummaryText(report: ReadinessReport): string {
  const { fail = 0, warn = 0 } = report.counts;
  if (report.status === 'ok') return 'Readiness: every check passed.';
  const parts: string[] = [];
  if (fail) parts.push(`${fail} ${fail === 1 ? 'check fails' : 'checks fail'}`);
  if (warn) parts.push(`${warn} ${warn === 1 ? 'check warns' : 'checks warn'}`);
  const word = report.status === 'fail' ? 'not ready' : 'ready with warnings';
  return `Readiness: ${word}, ${parts.join(', ')}. You can still export.`;
}
