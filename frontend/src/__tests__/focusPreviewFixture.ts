// A focus presets answer with each head's row filled in, as table.py's
// _entry_dict gives it: Spot 1 and Spot 2 hung and 16-bit, Spot 3 standing and
// 8-bit. Spot 3 cannot reach the DJ booth. The rig fixture ids (101-103) are
// not the console numbers (1-3), as in a real rig.
import { focusAnswer } from './focusPresetsFixture';

export const VIEW_FIXTURES = [
  { id: 101, fixture_number: 1 },
  { id: 102, fixture_number: 2 },
  { id: 103, fixture_number: 3 },
];

type Row = Record<string, unknown>;

export function head(id: number, rig: number | null, name: string, mount: string, over: Row = {}): Row {
  const sixteen = mount === 'hung';
  return {
    fixture_id: id, rig_fixture_id: rig, name, mount, mount_assumed: false, position_unconfirmed: false,
    point: [0, 0, 0], reachable: true, reason: '', throw_m: 5,
    pan_deg: 10 * id, tilt_deg: -30 - id, pan_attr_deg: 10 * id, tilt_attr_deg: -30 - id,
    pan_dmx: 130 + id, pan_fine_dmx: sixteen ? 64 : null, tilt_dmx: 100 + id, tilt_fine_dmx: sixteen ? 32 : null,
    ...over,
  };
}

const UNREACHABLE = {
  reachable: false, reason: 'tilt would be 150 degrees; the head turns 135 each way',
  pan_deg: null, tilt_deg: null, pan_attr_deg: null, tilt_attr_deg: null,
  pan_dmx: null, pan_fine_dmx: null, tilt_dmx: null, tilt_fine_dmx: null,
};

export function previewAnswer() {
  const answer = focusAnswer();
  answer.targets = answer.targets.map((t) => {
    if (t.skipped) return t;
    if (t.key === 'dj_booth') {
      return {
        ...t,
        fixtures: [
          // Out of order on purpose: the panel sorts by fixture.
          head(2, 102, 'Spot 2', 'hung'),
          head(1, 101, 'Spot 1', 'hung'),
          head(3, 103, 'Spot 3', 'standing', UNREACHABLE),
        ],
      };
    }
    if (t.key === 'custom_4') {
      return { ...t, fixtures: [1, 2, 3].map((n) => head(n, 100 + n, `Spot ${n}`, 'hung', UNREACHABLE)) };
    }
    return {
      ...t,
      fixtures: [
        head(1, 101, 'Spot 1', 'hung'),
        head(2, 102, 'Spot 2', 'hung'),
        // Standing, aimed well off the ceiling: drawable on the view's hung head.
        head(3, 103, 'Spot 3', 'standing', { pan_deg: 20, tilt_deg: 120 }),
      ],
    };
  });
  return answer;
}
