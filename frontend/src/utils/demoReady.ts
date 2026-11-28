import type { AudioCaptureDevice } from '../services/api';
import type { ReadinessReport } from './readiness';
import { FIX_AUTO_GROUPS, FIX_LABELS, FIX_LOCATE, FIX_READDRESS, FIX_SET_MODES } from './readiness';
import type { BoxHealthPayload, DmxStatusPayload } from './showHealth';
import type { SetupRig } from './venueSetupChecklist';

// Get demo-ready: the one-click plan on the New venue setup checklist
// (docs/VENUE_SETUP.md). Planned from what the box already reports, shown to
// the operator, and only run on confirm. Free of React and of the network, so
// what it would do for any state can be tested from plain data.
//
// It never changes the output target, never starts output, never flashes a
// fixture and never sends Art-Net or DMX. The steps that would (locate, output
// target, export) are always handed back to the operator as manual steps.

export const DEMO_PRESET = 'liv_miami_approx';
export const DEMO_PRESET_LABEL = 'LIV Miami (approximate recreation)';

/**
 * Every kind of action Get demo-ready may take. Nothing outside this list is
 * ever planned; the tests hold the planner to it.
 */
export const DEMO_ACTION_KINDS = ['loadDemo', 'readiness', 'makeGroups', 'audioInput', 'focus'] as const;
export type DemoActionKind = (typeof DEMO_ACTION_KINDS)[number];

/**
 * The readiness fixes Get demo-ready applies by itself. Make groups only adds:
 * it gives each placed fixture that is in no group a group, takes no fixture
 * out of one and leaves every address and mode alone. Re-address and Set modes
 * change the patch, which then has to be set on each fixture by hand, and
 * Locate flashes fixtures; those stay with the operator.
 */
export const AUTO_READINESS_FIXES: ReadonlySet<string> = new Set([FIX_AUTO_GROUPS]);

export interface DemoAction {
  kind: DemoActionKind;
  label: string;
  /** What it will do, in one line, before it runs. */
  detail: string;
  /** audioInput: the capture device to start. */
  deviceIndex?: number;
}

export interface DemoManualStep {
  key: string;
  label: string;
  /** Why it is left to the operator. */
  detail: string;
}

export interface DemoReadyPlan {
  /** What will run on confirm, in order. */
  actions: DemoAction[];
  /** What stays with the operator. Always holds locate, output and export. */
  manual: DemoManualStep[];
  /** What it looked at and left alone, and why (already fine, nothing to do). */
  skipped: { kind: DemoActionKind; label: string; detail: string }[];
}

export interface DemoReadyAudio {
  /** Capture is running on the box. */
  running: boolean;
  /** The capture devices the chooser would offer (already through sortCaptureDevices). */
  inputs: AudioCaptureDevice[];
  loopback: AudioCaptureDevice[];
  /** The device the box remembers, whichever browser picked it. */
  remembered?: { name?: string | null; hostapi?: string | null } | null;
  /** The device this browser last started. */
  browserName?: string | null;
}

export interface DemoReadyInput {
  /** The rig the checklist is open on; null when none is. */
  rig: SetupRig | null;
  /** The engine is running a built-in demo preset. */
  demoRunning: boolean | null;
  /** True only when output is verifiably not sending (see outputVerifiablyIdle). */
  outputIdle: boolean;
  /** The readiness report read when the plan was made; null when there is none or it failed. */
  readiness: ReadinessReport | null;
  /** The box's audio capture, read when the plan was made; null when it could not be read. */
  audio: DemoReadyAudio | null;
}

/**
 * Whether frames are verifiably not going out: output not set up, not
 * connected, or held until a rig is patched. Anything else, including a box
 * that cannot be reached, counts as maybe sending.
 */
export function outputVerifiablyIdle(
  dmx: DmxStatusPayload | null,
  reachable: boolean,
  box: BoxHealthPayload | null,
): boolean {
  if (!reachable) return false;
  if (box?.dmx_detail?.output_held_until_rig_patched) return true;
  if (!dmx || dmx.status === 'not_initialized') return true;
  return dmx.connected === false || dmx.status === 'disconnected';
}

/**
 * The device Get demo-ready would start: the one the box remembers, else the
 * one this browser last started, else the first loopback (this computer's own
 * audio). Never a line input nobody picked; null when there is nothing to pick.
 */
export function pickDemoAudioDevice(audio: DemoReadyAudio): AudioCaptureDevice | null {
  const all = [...audio.inputs, ...audio.loopback];
  const byName = (name?: string | null) => (name ? all.filter((d) => d.name === name) : []);
  const onBox = byName(audio.remembered?.name);
  return (
    onBox.find((d) => d.hostapi === audio.remembered?.hostapi) ??
    onBox[0] ??
    byName(audio.browserName)[0] ??
    audio.loopback[0] ??
    null
  );
}

const activeCount = (rig: SetupRig | null) => (rig ? rig.fixtures.filter((f) => f.is_active !== false).length : 0);

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The steps Get demo-ready never takes, whatever the state. */
const ALWAYS_MANUAL: DemoManualStep[] = [
  {
    key: 'locate',
    label: 'Locate (flash and tap)',
    detail: 'Flashes each fixture on the rig, so it is only ever started by hand.',
  },
  {
    key: 'output',
    label: 'Output target',
    detail: 'Choosing where Art-Net goes and starting output is the operator’s call.',
  },
  {
    key: 'export',
    label: 'Export to console',
    detail: 'Take the MA2 or MVR file and the handoff pack when the rig is final.',
  },
];

export function planDemoReady(input: DemoReadyInput): DemoReadyPlan {
  const actions: DemoAction[] = [];
  const manual: DemoManualStep[] = [];
  const skipped: DemoReadyPlan['skipped'] = [];
  const { rig } = input;
  const useRig = rig !== null && activeCount(rig) > 0;

  // 1. A rig to show: this one when it has fixtures, else the LIV demo.
  if (useRig) {
    skipped.push({ kind: 'loadDemo', label: 'Demo rig', detail: `Using "${rig.name}", ${plural(activeCount(rig), 'fixture')}.` });
  } else if (input.demoRunning) {
    skipped.push({ kind: 'loadDemo', label: 'Demo rig', detail: 'A demo rig is already running on the box.' });
  } else if (!input.outputIdle) {
    // The demo swaps the engine's fixtures: with output possibly live, its
    // patch would go out to whatever is on the wire.
    manual.push({
      key: 'loadDemo',
      label: `Load the ${DEMO_PRESET_LABEL} demo`,
      detail: 'Output may be sending, so loading a demo rig could drive the venue’s fixtures. Load it from the demo view.',
    });
  } else {
    actions.push({
      kind: 'loadDemo',
      label: `Load the ${DEMO_PRESET_LABEL} demo`,
      detail: 'Puts the demo rig on the engine. Output stays as it is: nothing is sent.',
    });
  }

  // 2 and 3. Readiness, and the fixes it may make by itself.
  if (!rig) {
    skipped.push({ kind: 'readiness', label: 'Readiness checks', detail: 'The demo rig is a built-in preset, not a saved rig: there are no checks to run.' });
  } else {
    actions.push({
      kind: 'readiness',
      label: 'Run the readiness checks',
      detail: input.readiness
        ? `Read now: ${input.readiness.counts.fail} failing, ${input.readiness.counts.warn} warnings. The checklist reads them again when it is done.`
        : 'Reads every check on the rig. Writes nothing.',
    });
    for (const check of input.readiness?.checks ?? []) {
      if (check.status === 'ok' || !check.fix) continue;
      if (AUTO_READINESS_FIXES.has(check.fix)) {
        actions.push({
          kind: 'makeGroups',
          label: FIX_LABELS[check.fix] ?? 'Make groups',
          detail:
            `${check.title}: ${plural(check.fixture_count, 'fixture')}. Gives each placed fixture that is in no group a group ` +
            'named for where it hangs and what it is. No fixture is taken out of a group and no address or mode changes; ' +
            'Undo Make groups in the readiness checks puts them back.',
        });
      } else {
        manual.push({
          key: `fix-${check.id}`,
          label: `${check.title}: ${FIX_LABELS[check.fix] ?? check.fix}`,
          detail: MANUAL_FIX_REASON[check.fix] ?? 'Open the readiness checks to review it.',
        });
      }
    }
  }

  // 4. Audio: start the remembered or loopback input when nothing is captured.
  if (!input.audio) {
    manual.push({ key: 'audio', label: 'Audio input', detail: 'Could not read the box’s audio devices. Pick the input by hand.' });
  } else if (input.audio.running) {
    skipped.push({ kind: 'audioInput', label: 'Audio input', detail: 'Audio is already being captured.' });
  } else {
    const device = pickDemoAudioDevice(input.audio);
    if (device) {
      actions.push({
        kind: 'audioInput',
        label: 'Start the audio input',
        detail: `Starts capture from "${device.name}"${device.is_loopback ? ' (this computer’s audio)' : ''}.`,
        deviceIndex: device.index,
      });
    } else {
      manual.push({ key: 'audio', label: 'Audio input', detail: 'No remembered input and no loopback device: pick the desk feed by hand.' });
    }
  }

  // 5. Focus presets: read again so the checklist shows them.
  if (rig) {
    actions.push({ kind: 'focus', label: 'Refresh the focus presets', detail: 'Reads the focus preset table. Writes nothing.' });
  } else {
    skipped.push({ kind: 'focus', label: 'Focus presets', detail: 'The demo rig is a built-in preset, not a saved rig: there is no focus table.' });
  }

  manual.push(...ALWAYS_MANUAL);
  return { actions, manual, skipped };
}

const MANUAL_FIX_REASON: Record<string, string> = {
  [FIX_READDRESS]: 'Moves addresses, which then have to be set on each fixture by hand. Review its plan in the readiness checks.',
  [FIX_SET_MODES]: 'Changes DMX modes, which have to match the mode set on each fixture. Review its plan in the readiness checks.',
  [FIX_LOCATE]: 'Flashes the fixtures it names, so it is only started by hand.',
};

// Running the plan.

export type DemoOutcome = 'done' | 'skipped' | 'failed';

export interface DemoActionResult {
  kind: DemoActionKind;
  label: string;
  outcome: DemoOutcome;
  /** What happened, or the error text. */
  message: string;
}

/** The calls the plan makes. The panel passes the real API; tests pass stand-ins. */
export interface DemoReadyDeps {
  applyDemoPreset: (name: string) => Promise<unknown>;
  readReadiness: (rigId: number) => Promise<ReadinessReport>;
  makeGroups: (rigId: number) => Promise<{ changed: unknown[]; message: string }>;
  startCapture: (deviceIndex: number) => Promise<unknown>;
  readFocus: (rigId: number) => Promise<{ heads: number; targets: unknown[] }>;
}

/** The backend's words when it gives them (detail as a string or {message}), else the error's own. */
export function errorText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  const message = (detail as { message?: unknown } | undefined)?.message;
  if (typeof message === 'string' && message) return message;
  if (e instanceof Error && e.message) return e.message;
  return 'Failed with no error text.';
}

async function runOne(action: DemoAction, rigId: number | null, deps: DemoReadyDeps): Promise<Omit<DemoActionResult, 'kind' | 'label'>> {
  switch (action.kind) {
    case 'loadDemo':
      await deps.applyDemoPreset(DEMO_PRESET);
      return { outcome: 'done', message: `The ${DEMO_PRESET_LABEL} demo is on the engine.` };
    case 'readiness': {
      if (rigId === null) return { outcome: 'skipped', message: 'No saved rig to check.' };
      const report = await deps.readReadiness(rigId);
      return { outcome: 'done', message: `${report.counts.fail} failing, ${report.counts.warn} warnings, ${report.counts.ok} passing.` };
    }
    case 'makeGroups': {
      if (rigId === null) return { outcome: 'skipped', message: 'No saved rig to group.' };
      const result = await deps.makeGroups(rigId);
      return { outcome: result.changed.length > 0 ? 'done' : 'skipped', message: result.message };
    }
    case 'audioInput':
      if (action.deviceIndex === undefined) return { outcome: 'skipped', message: 'No device to start.' };
      await deps.startCapture(action.deviceIndex);
      return { outcome: 'done', message: 'Capture started.' };
    case 'focus': {
      if (rigId === null) return { outcome: 'skipped', message: 'No saved rig.' };
      const focus = await deps.readFocus(rigId);
      return { outcome: 'done', message: `${plural(focus.targets.length, 'focus target')} for ${plural(focus.heads, 'moving head')}.` };
    }
  }
}

/**
 * Runs each action in order. A failure is recorded with its error text and
 * the next action still runs: none of them depends on another's answer.
 */
export async function runDemoReadyPlan(
  plan: DemoReadyPlan,
  rigId: number | null,
  deps: DemoReadyDeps,
  onResult?: (result: DemoActionResult) => void,
): Promise<DemoActionResult[]> {
  const results: DemoActionResult[] = [];
  for (const action of plan.actions) {
    let result: DemoActionResult;
    try {
      result = { kind: action.kind, label: action.label, ...(await runOne(action, rigId, deps)) };
    } catch (e) {
      result = { kind: action.kind, label: action.label, outcome: 'failed', message: errorText(e) };
    }
    results.push(result);
    onResult?.(result);
  }
  return results;
}
