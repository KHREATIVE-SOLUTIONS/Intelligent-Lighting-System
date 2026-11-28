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
 * is the hung beam at those angles, exactly, at every tilt and under any yaw
 * or lean). That tilt is 180 - |t| from straight down, so a standing head
 * aimed within 45 degrees of the ceiling is past the hung head's 135 each way:
 * the frame loop lets a previewed head go past its travel to get there
 * (viewTravelLimit), and its beam is drawn where the real one points.
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

/** The fixture as the 3D view knows it. */
export interface ViewFixture {
  id: number;
  fixture_number?: number | null;
}

const wrap180 = (deg: number) => {
  const d = ((deg + 180) % 360 + 360) % 360 - 180;
  return Object.is(d, -0) ? 0 : d;
};

/**
 * The hung head's pan and tilt for a head's physical ones; null when it
 * cannot reach. A standing head's tilt can be past the hung head's travel
 * (up to 180, straight up): see viewTravelLimit.
 */
export function viewAim(aim: FocusHeadAim): ViewAim | null {
  if (!aim.reachable || aim.pan_deg === null || aim.tilt_deg === null) return null;
  if (aim.mount !== 'standing') return { panDeg: aim.pan_deg, tiltDeg: aim.tilt_deg };
  const t = aim.tilt_deg;
  return { panDeg: wrap180(180 - aim.pan_deg), tiltDeg: (t >= 0 ? 180 : -180) - t };
}

/**
 * How far from centre the 3D view lets a head's pan or tilt go on this step
 * (any unit, the caller's). Its own travel, `half` either way; further for a
 * previewed aim past it (a standing head aimed near the ceiling, drawn on the
 * hung head); and, once a preview stops, as far as the head already is, so it
 * eases back into its travel instead of jumping there in one frame. With no
 * preview and the head inside its travel, this is the travel.
 */
export function viewTravelLimit(half: number, previous: number, previewTarget: number | null): number {
  return Math.max(half, Math.abs(previous), previewTarget === null ? 0 : Math.abs(previewTarget));
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
    } else {
      home.push({ name, reason: row.reason || 'it cannot reach the target' });
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
