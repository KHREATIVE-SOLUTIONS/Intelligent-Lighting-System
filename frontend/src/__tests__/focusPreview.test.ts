// Previewing a focus preset, the pure part (utils/focusPreview.ts), the per-head
// helpers (utils/focusPresets.ts) and which requests count as a rig change
// (utils/focusTargetsSync.ts). docs/FOCUS_PRESETS.md, "In the app".
import { describe, expect, it } from 'vitest';
import { aimBits, degreesText, dmxText, parseFocusPresets, sortAims } from '../utils/focusPresets';
import type { FocusHeadAim } from '../utils/focusPresets';
import { VIEW_MIN_STANDING_TILT, previewPlan, previewText, viewAim } from '../utils/focusPreview';
import { rigChangedBy } from '../utils/focusTargetsSync';
import { VIEW_FIXTURES, previewAnswer } from './focusPreviewFixture';

const table = () => parseFocusPresets(previewAnswer());
const target = (key: string) => table().targets.find((t) => t.key === key)!;

const aim = (over: Partial<FocusHeadAim>): FocusHeadAim => ({
  fixture_id: 1, rigFixtureId: 101, name: 'Spot 1', mount: 'hung', reachable: true, reason: '',
  pan_deg: 0, tilt_deg: 0, pan_dmx: 128, pan_fine_dmx: null, tilt_dmx: 128, tilt_fine_dmx: null, ...over,
});

/** The view's beam for hung pan and tilt (aim.py local_beam), before the body's turns. */
const hungBeam = (p: number, t: number) => {
  const pr = (p * Math.PI) / 180;
  const tr = (t * Math.PI) / 180;
  return [-Math.sin(tr) * Math.sin(pr), -Math.cos(tr), -Math.sin(tr) * Math.cos(pr)];
};
/** A standing head's beam: the hung one turned over about X. */
const standingBeam = (p: number, t: number) => {
  const [x, y, z] = hungBeam(p, t);
  return [x, -y, -z];
};

describe('parsing the per-head rows', () => {
  it('keeps every row with its rig fixture id, mount and DMX', () => {
    const booth = target('dj_booth');
    expect(booth.aims.map((a) => a.rigFixtureId)).toEqual([102, 101, 103]);
    const spot1 = booth.aims.find((a) => a.fixture_id === 1)!;
    expect(spot1).toMatchObject({ mount: 'hung', reachable: true, pan_deg: 10, tilt_deg: -31, pan_dmx: 131, pan_fine_dmx: 64 });
    const spot3 = booth.aims.find((a) => a.fixture_id === 3)!;
    expect(spot3).toMatchObject({ mount: 'standing', reachable: false, pan_deg: null, pan_dmx: null });
  });

  it('gives a target with no rows, or rows that are not objects, an empty list', () => {
    const parsed = parseFocusPresets({ heads: 1, targets: [{ key: 'x', fixtures: 'nope' }, { key: 'y', fixtures: [1, null] }] });
    expect(parsed.targets.map((t) => t.aims)).toEqual([[], []]);
  });

  it('takes a head with no angles as one that cannot be aimed', () => {
    const parsed = parseFocusPresets({ heads: 1, targets: [{ key: 'x', fixtures: [{ fixture_id: 1, reachable: true }] }] });
    expect(parsed.targets[0].aims[0].reachable).toBe(false);
  });
});

describe('the angles the 3D view is given', () => {
  it('passes a hung head the API degrees as they are', () => {
    expect(viewAim(aim({ pan_deg: 12.5, tilt_deg: -38.2 }))).toEqual({ panDeg: 12.5, tiltDeg: -38.2 });
  });

  it('turns a standing head into the hung head that points its beam the same way', () => {
    for (const [p, t] of [[20, 120], [-75, 60], [170, -100], [0, 90], [-200, -50]]) {
      const view = viewAim(aim({ mount: 'standing', pan_deg: p, tilt_deg: t }))!;
      expect(view).not.toBeNull();
      expect(Math.abs(view.tiltDeg)).toBeLessThanOrEqual(135);
      expect(Math.abs(view.panDeg)).toBeLessThanOrEqual(180);
      const want = standingBeam(p, t);
      const got = hungBeam(view.panDeg, view.tiltDeg);
      got.forEach((v, i) => expect(v).toBeCloseTo(want[i], 9));
    }
  });

  it('leaves a standing head aimed near the ceiling at home', () => {
    expect(viewAim(aim({ mount: 'standing', tilt_deg: VIEW_MIN_STANDING_TILT - 1 }))).toBeNull();
  });

  it('leaves a head that cannot reach at home', () => {
    expect(viewAim(aim({ reachable: false, pan_deg: null, tilt_deg: null }))).toBeNull();
  });
});

describe('the preview plan', () => {
  it('aims every head that reaches, by its rig fixture id', () => {
    const plan = previewPlan(target('dance_floor'), VIEW_FIXTURES);
    expect(plan.aimed).toBe(3);
    expect(plan.home).toEqual([]);
    expect(plan.aims.get(101)).toEqual({ panDeg: 10, tiltDeg: -31 });
    expect(plan.aims.get(102)).toEqual({ panDeg: 20, tiltDeg: -32 });
    expect(plan.aims.get(103)).toEqual({ panDeg: 160, tiltDeg: 60 });
    expect(previewText(plan)).toBe(
      'Previewing Dance floor centre: 3 heads aimed at it. In the 3D view only; nothing is sent to the lights.',
    );
  });

  it('keeps a head that cannot reach at home, and says why', () => {
    const plan = previewPlan(target('dj_booth'), VIEW_FIXTURES);
    expect(plan.aimed).toBe(2);
    expect(plan.aims.has(103)).toBe(true);
    expect(plan.aims.get(103)).toBeNull();
    expect(plan.home).toEqual([{ name: 'Spot 3', reason: 'tilt would be 150 degrees; the head turns 135 each way' }]);
  });

  it('aims nobody at a target nobody reaches', () => {
    const plan = previewPlan(target('custom_4'), VIEW_FIXTURES);
    expect(plan.aimed).toBe(0);
    expect([...plan.aims.values()]).toEqual([null, null, null]);
    expect(previewText(plan)).toMatch(/no head is aimed at it/);
  });

  it('matches by console number when the server gives no rig fixture id, and never guesses', () => {
    const t = target('dance_floor');
    const old = { ...t, aims: t.aims.map((a) => ({ ...a, rigFixtureId: null })) };
    const plan = previewPlan(old, [{ id: 101, fixture_number: 1 }, { id: 102, fixture_number: 2 }]);
    expect([...plan.aims.keys()].sort()).toEqual([101, 102]);
    expect(plan.home).toEqual([{ name: 'Spot 3', reason: 'it is not in the 3D view' }]);

    const stale = previewPlan(t, [{ id: 999, fixture_number: 1 }]);
    expect(stale.aims.size).toBe(0);
    expect(stale.home).toHaveLength(3);
  });
});

describe('the per-head table helpers', () => {
  it('writes degrees and DMX as the API gives them', () => {
    expect(degreesText(12.345)).toBe('12.3°');
    expect(degreesText(-0.01)).toBe('0.0°');
    expect(degreesText(null)).toBe('-');
    expect(dmxText(131, null)).toBe('131');
    expect(dmxText(131, 64)).toBe('131 / 64');
    expect(dmxText(null, null)).toBe('-');
    expect(aimBits(aim({ pan_fine_dmx: 3 }))).toBe(16);
    expect(aimBits(aim({}))).toBe(8);
  });

  it('sorts by fixture both ways without changing the list it was given', () => {
    const rows = target('dj_booth').aims;
    expect(sortAims(rows).map((a) => a.fixture_id)).toEqual([1, 2, 3]);
    expect(sortAims(rows, 'desc').map((a) => a.fixture_id)).toEqual([3, 2, 1]);
    expect(rows.map((a) => a.fixture_id)).toEqual([2, 1, 3]);
  });
});

describe('which requests change a rig', () => {
  it('takes writes to the rig, its fixtures and its room', () => {
    expect(rigChangedBy('put', '/rigs/7')).toBe(7);
    expect(rigChangedBy('put', '/rigs/7/fixtures/12/position')).toBe(7);
    expect(rigChangedBy('PUT', '/rigs/7/fixtures/12')).toBe(7);
    expect(rigChangedBy('post', '/rigs/7/fixtures')).toBe(7);
    expect(rigChangedBy('delete', '/rigs/7/fixtures/12')).toBe(7);
    expect(rigChangedBy('patch', '/rigs/7/room-shell/risers/0')).toBe(7);
    expect(rigChangedBy('put', 'http://box:8000/api/rigs/7/fixtures/batch-update')).toBe(7);
  });

  it('leaves out reads, other routes and writes that move nothing', () => {
    expect(rigChangedBy('get', '/rigs/7')).toBeNull();
    expect(rigChangedBy(undefined, '/rigs/7')).toBeNull();
    expect(rigChangedBy('post', '/shows/7')).toBeNull();
    expect(rigChangedBy('delete', '/rigs/7')).toBeNull();
    expect(rigChangedBy('post', '/rigs/7/fixtures/3/test')).toBeNull();
    expect(rigChangedBy('post', '/rigs/7/fixtures/3/set-channels')).toBeNull();
    expect(rigChangedBy('post', '/rigs/7/test-all/stop')).toBeNull();
    expect(rigChangedBy('post', '/rigs/7/identify/abc/heartbeat')).toBeNull();
    expect(rigChangedBy('post', '/rigs/7/focus-presets/targets')).toBeNull();
    expect(rigChangedBy('put', '/rigs/7/stage-plot/calibration')).toBeNull();
  });
});
