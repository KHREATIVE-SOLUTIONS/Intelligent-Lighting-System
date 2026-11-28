/**
 * Previewing a focus preset in the 3D view (docs/FOCUS_PRESETS.md, "In the
 * app"): which head is aimed where, worked out from the pan and tilt the API
 * already gives. Pure: no requests, no DOM. Visual only: nothing here, nor
 * anything that reads it, sends DMX or touches the engine's output.
 *
 * The API's degrees are physical, for the head as hung or standing. The 3D
 * view draws every moving head hung (aim.py: "the 3D view does not turn a
 * floor-standing mover over"), so a standing head's angles are turned into the
 * hung head's that point the beam the same way:
 *
 *   standing (p, t)  ->  hung (180 - p, sign(t) * 180 - t)
 *
 * (the local beam (-sin t sin p, -cos t, -sin t cos p), turned over about X,
 * is the hung beam at those angles). That tilt is 180 - |t| from straight
 * down, so a standing head aimed within VIEW_MIN_STANDING_TILT of the ceiling
 * cannot be drawn inside the view's tilt travel and is left at home, listed.
 */
import type { FocusHeadAim, FocusTarget } from './focusPresets';

/** Pan and tilt in degrees from centre, as the 3D view's frame loop takes them. */
export interface ViewAim {
  panDeg: number;
  tiltDeg: number;
}

/** A moving head the preview leaves at home, and why, in words. */
export interface HomeHead {
  name: string;
  reason: string;
}

export interface FocusPreviewPlan {
  key: string;
  name: string;
  /** Rig fixture id -> where it is aimed, or null: at home (pan 0, tilt 0) and dark. */
  aims: Map<number, ViewAim | null>;
  aimed: number;
  home: HomeHead[];
}

/** The view's tilt travel is 135 each way for a 270 head: a standing head needs at least this from the ceiling. */
export const VIEW_MIN_STANDING_TILT = 45;

/** The fixture as the 3D view knows it. */
export interface ViewFixture {
  id: number;
  fixture_number?: number | null;
}

const wrap180 = (deg: number) => {
  const d = ((deg + 180) % 360 + 360) % 360 - 180;
  return Object.is(d, -0) ? 0 : d;
};

/** The hung head's pan and tilt for a head's physical ones; null when the view cannot draw it. */
export function viewAim(aim: FocusHeadAim): ViewAim | null {
  if (!aim.reachable || aim.pan_deg === null || aim.tilt_deg === null) return null;
  if (aim.mount !== 'standing') return { panDeg: aim.pan_deg, tiltDeg: aim.tilt_deg };
  const t = aim.tilt_deg;
  if (Math.abs(t) < VIEW_MIN_STANDING_TILT) return null;
  return { panDeg: wrap180(180 - aim.pan_deg), tiltDeg: (t >= 0 ? 180 : -180) - t };
}

/**
 * Every moving head the target has a row for, against the fixtures the view
 * draws. A row is matched by its rig fixture id, or by console number from an
 * older server that does not give one; a row matching nothing is listed, never
 * guessed onto another head.
 */
export function previewPlan(target: FocusTarget, fixtures: ViewFixture[]): FocusPreviewPlan {
  const ids = new Set(fixtures.map((f) => f.id));
  const byNumber = new Map<number, number>();
  for (const f of fixtures) {
    if (typeof f.fixture_number === 'number' && !byNumber.has(f.fixture_number)) byNumber.set(f.fixture_number, f.id);
  }
  const aims = new Map<number, ViewAim | null>();
  const home: HomeHead[] = [];
  let aimed = 0;
  for (const row of target.aims) {
    const id = row.rigFixtureId !== null
      ? (ids.has(row.rigFixtureId) ? row.rigFixtureId : null)
      : (byNumber.get(row.fixture_id) ?? null);
    const name = row.name || `Fixture ${row.fixture_id}`;
    if (id === null) {
      home.push({ name, reason: 'it is not in the 3D view' });
      continue;
    }
    const at = viewAim(row);
    aims.set(id, at);
    if (at) {
      aimed += 1;
    } else if (!row.reachable) {
      home.push({ name, reason: row.reason || 'it cannot reach the target' });
    } else {
      home.push({ name, reason: 'standing and aimed near the ceiling, which the 3D view cannot draw' });
    }
  }
  return { key: target.key, name: target.name, aims, aimed, home };
}

/** The line the 3D view shows while previewing. */
export function previewText(plan: FocusPreviewPlan): string {
  const lead = plan.aimed === 0
    ? `Previewing ${plan.name}: no head is aimed at it.`
    : `Previewing ${plan.name}: ${plan.aimed === 1 ? 'one head' : `${plan.aimed} heads`} aimed at it.`;
  return `${lead} In the 3D view only; nothing is sent to the lights.`;
}
