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

export interface AutoGroupsResult {
  rig_id: number;
  created: { name: string; fixture_ids: number[] }[];
  skipped: { name: string; fixture_ids: number[] }[];
  unplaced_ids: number[];
  changed: { id: number; name: string; group_before: string | null; group_name: string }[];
  message: string;
}

export const FIX_AUTO_GROUPS = 'auto-groups';

export const readinessPath = (rigId: number) => `/rigs/${rigId}/readiness`;
export const autoGroupsPath = (rigId: number) => `/rigs/${rigId}/readiness/fix/auto-groups`;

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
};
