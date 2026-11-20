// Per-fixture setup checks: the wording and the roll-up shown in the patch.
// Kept free of React so both can be tested. Which checks a fixture supports is
// decided by the box from the fixture's profile, never worked out here.

export type SetupCheckName = 'flash' | 'colour' | 'pan' | 'tilt';
export type SetupCheckResult = 'ok' | 'fail' | null;

export interface SetupCheck {
  check: SetupCheckName;
  available: boolean;
  /** The looks this check can hold on the fixture, in the order to offer them. */
  looks: string[];
  /** Why the check is not available, in words for the operator. */
  reason: string | null;
  result: SetupCheckResult;
}

export interface SetupCheckFixture {
  fixture_id: number;
  label: string;
  universe: number;
  dmx_address: number;
  channel_count: number;
  has_shutter: boolean;
  shutter_open_value: number | null;
  /** Marked as never having lit, here or in the identify walkthrough. */
  no_response: boolean;
  /** Something outside the fixture that keeps it dark, such as the strobe switch. */
  output_blocked_reason: string | null;
  checks: SetupCheck[];
}

export interface SetupCheckActive {
  rig_id: number;
  fixture_id: number;
  label: string;
  check: SetupCheckName;
  look: string;
  seconds_left: number;
  output_blocked_reason?: string | null;
}

export interface SetupCheckState {
  rig_id: number;
  active: SetupCheckActive | null;
  /** Rig-wide: blackout latched, or the grand master at zero. */
  output_blocked_reason: string | null;
  hold_max_s: number;
  heartbeat_timeout_s: number;
  released?: boolean;
}

export interface SetupCheckListing extends SetupCheckState {
  fixtures: SetupCheckFixture[];
}

export interface CheckCopy {
  title: string;
  /** What to do and what to look for. */
  question: string;
  /** Extra line when the fixture has a shutter channel. */
  shutterNote?: string;
}

export const CHECK_COPY: Record<SetupCheckName, CheckCopy> = {
  flash: {
    title: 'Lights up',
    question: 'Does this light, and only this light, come on and stay on steadily?',
    shutterNote: 'It has a shutter: a light that flickers or stays dark here usually means the wrong mode.',
  },
  colour: {
    title: 'Colours',
    question: 'Press each colour. Does the light show the colour on the button?',
  },
  pan: {
    title: 'Pan',
    question: 'Press Lower, then Higher. Does the head turn side to side, a little each way?',
  },
  tilt: {
    title: 'Tilt',
    question: 'Press Lower, then Higher. Does the head nod up and down, a little each way?',
  },
};

const LOOK_LABELS: Record<string, string> = {
  white: 'Light it',
  red: 'Red',
  green: 'Green',
  blue: 'Blue',
  white_emitter: 'White',
  centre: 'Centre',
  pan_low: 'Lower',
  pan_high: 'Higher',
  tilt_low: 'Lower',
  tilt_high: 'Higher',
};

export const lookLabel = (look: string): string => LOOK_LABELS[look] ?? look;

export type CheckSummaryState = 'unchecked' | 'partial' | 'passed' | 'failed' | 'blocked';

export interface CheckSummary {
  state: CheckSummaryState;
  /** Checks answered either way, out of the ones this fixture supports. */
  answered: number;
  total: number;
  label: string;
}

/** One line for a patch row: where this fixture stands. */
export function summariseChecks(fixture: SetupCheckFixture | undefined): CheckSummary {
  if (!fixture) {
    return { state: 'unchecked', answered: 0, total: 0, label: 'Not checked yet' };
  }
  const usable = fixture.checks.filter((c) => c.available);
  const total = usable.length;
  if (total === 0) {
    const reason = fixture.checks.find((c) => c.reason)?.reason;
    return { state: 'blocked', answered: 0, total, label: reason ?? 'This light cannot be checked from here.' };
  }

  const failed = usable.filter((c) => c.result === 'fail');
  const passed = usable.filter((c) => c.result === 'ok');
  const answered = failed.length + passed.length;
  const flash = usable.find((c) => c.check === 'flash');

  // A light the walkthrough marked as never lighting is a failure until a
  // flash check here says otherwise.
  if (fixture.no_response && flash?.result !== 'ok') {
    return { state: 'failed', answered, total, label: 'Did not light when tested' };
  }
  if (failed.length > 0) {
    const names = failed.map((c) => CHECK_COPY[c.check].title.toLowerCase()).join(', ');
    return { state: 'failed', answered, total, label: `Failed: ${names}` };
  }
  if (passed.length === total) {
    return { state: 'passed', answered, total, label: total === 1 ? 'Checked' : `All ${total} checks passed` };
  }
  if (answered > 0) {
    return { state: 'partial', answered, total, label: `${answered} of ${total} checked` };
  }
  return { state: 'unchecked', answered, total, label: 'Not checked yet' };
}

/** How many fixtures in a rig still need looking at, for a header line. */
export function countOutstanding(fixtures: SetupCheckFixture[]): { failed: number; unchecked: number } {
  let failed = 0;
  let unchecked = 0;
  for (const fixture of fixtures) {
    const { state } = summariseChecks(fixture);
    if (state === 'failed') failed += 1;
    else if (state === 'unchecked' || state === 'partial') unchecked += 1;
  }
  return { failed, unchecked };
}
