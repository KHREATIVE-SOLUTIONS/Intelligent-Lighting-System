// The pure side of focus presets in the app (docs/FOCUS_PRESETS.md, "In the app"):
// reading the table, checking a typed custom target as the server does, the
// sentences the panel shows, and which marker the 3D view draws for a target.
import { beforeEach, describe, expect, it } from 'vitest';
import {
  EMPTY_DRAFT, MAX_CUSTOM_TARGETS, checkDraft, customIdFromKey, focusMarkers, focusPresetsCsvPath, focusPresetsPath,
  focusTargetPath, focusTargets3dKey, focusTargetsPath, markerStyle, metres, parseFocusPresets, reachText,
  readFocusTargets3dChoice, whereText, writeFocusTargets3dChoice,
} from '../utils/focusPresets';
import { focusAnswer, noHeadsAnswer } from './focusPresetsFixture';

describe('parseFocusPresets', () => {
  it('reads every target with its kind, place, reach and custom id', () => {
    const table = parseFocusPresets(focusAnswer());
    expect(table.rigId).toBe(7);
    expect(table.heads).toBe(3);
    expect(table.customCount).toBe(1);
    expect(table.leftOut).toEqual([{ fixture_id: 9, name: 'Spot 9', reason: 'it has no position in the rig' }]);
    expect(table.targets.map((t) => t.key)).toEqual([
      'dj_booth', 'dance_floor', 'audience', 'stage_front', 'straight_down', 'custom_4',
    ]);
    const [booth, , audience, front, down, mirror] = table.targets;
    expect(booth.point).toEqual([0, 2.2, -3.5]);
    expect(booth.unreachable).toHaveLength(1);
    expect(booth.customId).toBeNull();
    expect(audience.kind).toBe('line');
    expect(audience.line).toEqual([[-3, 1.7, 1.5], [3, 1.7, 1.5]]);
    expect(front.skipped).toMatch(/no stage/);
    expect(down.kind).toBe('below');
    expect(mirror.custom).toBe(true);
    expect(mirror.customId).toBe(4);
  });

  it('never throws on a malformed answer, and leaves out what it cannot read', () => {
    expect(parseFocusPresets(null)).toEqual({ rigId: null, heads: 0, leftOut: [], targets: [], customCount: 0 });
    expect(parseFocusPresets('nonsense').targets).toEqual([]);
    const table = parseFocusPresets({
      heads: 'two',
      targets: [null, { name: 'no key' }, { key: 'k', point: [1, 'a', 2], line: [[0, 0]], kind: 'weird' }],
    });
    expect(table.heads).toBe(0);
    expect(table.targets).toHaveLength(1);
    expect(table.targets[0]).toMatchObject({ key: 'k', name: 'k', kind: 'point', point: null, line: null, skipped: '' });
  });

  it('takes the custom id from the key only', () => {
    expect(customIdFromKey('custom_12')).toBe(12);
    expect(customIdFromKey('custom_')).toBeNull();
    expect(customIdFromKey('dj_booth')).toBeNull();
  });

  it('builds the routes', () => {
    expect(focusPresetsPath(7)).toBe('/rigs/7/focus-presets');
    expect(focusPresetsCsvPath(7)).toBe('/rigs/7/focus-presets.csv');
    expect(focusTargetsPath(7)).toBe('/rigs/7/focus-presets/targets');
    expect(focusTargetPath(7, 4)).toBe('/rigs/7/focus-presets/targets/4');
  });
});

describe('checkDraft', () => {
  const draft = (over: Partial<typeof EMPTY_DRAFT>) => ({ name: 'Mirror ball', x: '1', y: '4.5', z: '-2', ...over });

  it('gives the server real numbers and a tidy name', () => {
    expect(checkDraft(draft({ name: '  Mirror   ball ', x: '1,25' }))).toEqual({
      ok: true, target: { name: 'Mirror ball', x: 1.25, y: 4.5, z: -2 },
    });
  });

  it('says what is wrong with each field in a sentence', () => {
    const result = checkDraft(EMPTY_DRAFT);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.errors).toEqual({
      name: 'Give the target a name.',
      x: 'Give x in metres.',
      y: 'Give y in metres.',
      z: 'Give z in metres.',
    });
  });

  it('refuses what the server refuses', () => {
    const errors = (over: Partial<typeof EMPTY_DRAFT>) => {
      const result = checkDraft(draft(over));
      return result.ok ? {} : result.errors;
    };
    expect(errors({ name: 'x'.repeat(61) }).name).toBe("A target's name is at most 60 characters.");
    expect(errors({ name: 'x'.repeat(60) }).name).toBeUndefined();
    expect(errors({ x: 'abc' }).x).toBe('x must be a number of metres, like 1.5 or -2.');
    expect(errors({ x: '0x10' }).x).toMatch(/must be a number/);
    expect(errors({ z: '500.1' }).z).toBe('z is at most 500 m from the middle of the room.');
    expect(errors({ z: '-500' }).z).toBeUndefined();
    expect(errors({ y: '-0.1' }).y).toBe('y is height above the floor and cannot be below it.');
    expect(errors({ y: '0' }).y).toBeUndefined();
  });

  it('refuses a fifty-first custom target', () => {
    const result = checkDraft(draft({}), MAX_CUSTOM_TARGETS);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.form).toBe('A rig keeps at most 50 custom targets. Remove one first.');
    expect(checkDraft(draft({}), MAX_CUSTOM_TARGETS - 1).ok).toBe(true);
  });

  it('reads metres as typed', () => {
    expect(metres(' 2.5 ')).toBe(2.5);
    expect(metres('-3')).toBe(-3);
    expect(metres('.5')).toBe(0.5);
    expect(metres('1e2')).toBe(100);
    expect(Number.isNaN(metres(''))).toBe(true);
    expect(Number.isNaN(metres('1.2.3'))).toBe(true);
    expect(Number.isNaN(metres('Infinity'))).toBe(true);
  });
});

describe('in words', () => {
  const table = parseFocusPresets(focusAnswer());
  const [booth, floor, audience, front, down, mirror] = table.targets;

  it('says where each kind of target is', () => {
    expect(whereText(booth)).toBe('x 0, y 2.2, z -3.5 m');
    expect(whereText(audience)).toBe('A line from x -3, y 1.7, z 1.5 m to x 3, y 1.7, z 1.5 m, the heads spread along it.');
    expect(whereText(down)).toBe('The floor under each head.');
    expect(whereText(front)).toBe('Not placed.');
  });

  it('says how many heads reach it', () => {
    expect(reachText(booth, 3)).toBe('2 of 3 moving heads can reach it.');
    expect(reachText(floor, 3)).toBe('All 3 moving heads can reach it.');
    expect(reachText(mirror, 3)).toBe('None of the 3 moving heads can reach it.');
    expect(reachText(front, 3)).toBe('No preset: the room cannot place it yet.');
    expect(reachText(floor, 0)).toBe('No moving heads to aim at it.');
    expect(reachText({ ...floor, reachable_count: 1 }, 1)).toBe('The moving head can reach it.');
  });
});

describe('markers for the 3D view', () => {
  it('picks a look by who can reach it', () => {
    const [booth, floor, , , , mirror] = parseFocusPresets(focusAnswer()).targets;
    expect(markerStyle(floor, 3)).toBe('all');
    expect(markerStyle(booth, 3)).toBe('some');
    expect(markerStyle(mirror, 3)).toBe('none');
    // No heads: nobody fails to reach it, and nobody reaches it either.
    expect(markerStyle(floor, 0)).toBe('idle');
  });

  it('puts one marker on each placed point or line, none for straight down or a skipped target', () => {
    const markers = focusMarkers(parseFocusPresets(focusAnswer()));
    expect(markers.map((m) => [m.key, m.style])).toEqual([
      ['dj_booth', 'some'], ['dance_floor', 'all'], ['audience', 'all'], ['custom_4', 'none'],
    ]);
    const audience = markers.find((m) => m.key === 'audience')!;
    expect(audience.at).toEqual([0, 1.7, 1.5]);
    expect(audience.line).toEqual([[-3, 1.7, 1.5], [3, 1.7, 1.5]]);
    expect(markers.find((m) => m.key === 'dj_booth')!.at).toEqual([0, 2.2, -3.5]);
  });

  it('draws idle markers on a rig with no heads, and nothing with no table', () => {
    expect(focusMarkers(parseFocusPresets(noHeadsAnswer())).every((m) => m.style === 'idle')).toBe(true);
    expect(focusMarkers(null)).toEqual([]);
  });
});

describe('the "Show focus targets in 3D" choice', () => {
  beforeEach(() => window.localStorage.clear());

  it('is kept per rig under focusTargets3d:{rigId}', () => {
    expect(focusTargets3dKey(7)).toBe('focusTargets3d:7');
    expect(readFocusTargets3dChoice(7)).toBeNull();
    writeFocusTargets3dChoice(7, true);
    expect(window.localStorage.getItem('focusTargets3d:7')).toBe('on');
    expect(readFocusTargets3dChoice(7)).toBe(true);
    expect(readFocusTargets3dChoice(8)).toBeNull();
    writeFocusTargets3dChoice(7, false);
    expect(readFocusTargets3dChoice(7)).toBe(false);
  });
});
