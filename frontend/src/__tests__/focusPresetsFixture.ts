// A focus presets answer shaped as GET /api/rigs/{id}/focus-presets gives it
// (backend/app/services/focus_presets/table.py, table_dict): three heads, one
// of which cannot reach the DJ booth; a skipped stage front; one custom target.

export const RIG_ID = 7;

export function focusAnswer(overrides: Record<string, unknown> = {}) {
  return {
    rig_id: RIG_ID,
    heads: 3,
    left_out: [{ fixture_id: 9, name: 'Spot 9', reason: 'it has no position in the rig' }],
    targets: [
      {
        key: 'dj_booth', name: 'DJ booth', kind: 'point', source: 'the rig\'s DJ booth, at the top of the booth',
        point: [0, 2.2, -3.5], line: null, custom: false, skipped: '',
        reachable_count: 2,
        unreachable: [{ fixture_id: 3, name: 'Spot 3', reason: 'tilt would be 150 degrees; the head turns 135 each way' }],
        fixtures: [],
      },
      {
        key: 'dance_floor', name: 'Dance floor centre', kind: 'point', source: 'the centre of the dance floor, on the floor',
        point: [0, 0, 1.5], line: null, custom: false, skipped: '',
        reachable_count: 3, unreachable: [], fixtures: [],
      },
      {
        key: 'audience', name: 'Audience', kind: 'line', source: 'a line across the dance floor at 1.7 m',
        point: null, line: [[-3, 1.7, 1.5], [3, 1.7, 1.5]], custom: false, skipped: '',
        reachable_count: 3, unreachable: [], fixtures: [],
      },
      {
        key: 'stage_front', name: 'Stage front', kind: 'point', source: '', point: null, line: null, custom: false,
        skipped: 'The room has no stage and no DJ booth. Add the stage as a raised area of kind stage.',
        reachable_count: 0, unreachable: [], fixtures: [],
      },
      {
        key: 'straight_down', name: 'Straight down', kind: 'below', source: 'the floor under each head',
        point: null, line: null, custom: false, skipped: '',
        reachable_count: 3, unreachable: [], fixtures: [],
      },
      {
        key: 'custom_4', name: 'Mirror ball', kind: 'point', source: 'a point added by hand',
        point: [1, 4.5, 0], line: null, custom: true, skipped: '',
        reachable_count: 0,
        unreachable: [
          { fixture_id: 1, name: 'Spot 1', reason: 'the point is above the head' },
          { fixture_id: 2, name: 'Spot 2', reason: 'the point is above the head' },
          { fixture_id: 3, name: 'Spot 3', reason: 'the point is above the head' },
        ],
        fixtures: [],
      },
    ],
    custom_targets: [{ id: 4, name: 'Mirror ball', x: 1, y: 4.5, z: 0 }],
    operator_guide: 'docs/FOCUS_PRESETS.md',
    ...overrides,
  };
}

/** A rig with no moving heads: the targets are still listed, nobody aims at them. */
export function noHeadsAnswer() {
  const answer = focusAnswer({ heads: 0, left_out: [] });
  answer.targets = answer.targets.map((t) => ({ ...t, reachable_count: 0, unreachable: [] }));
  return answer;
}
